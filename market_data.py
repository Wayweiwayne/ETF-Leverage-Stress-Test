"""Market-data loading, repair and calendar-month alignment, independent of the UI."""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # the in-browser build has no live source: only stored copies and the mirror
    yf = None

from version import SOURCE_URL

_HERE = os.path.dirname(os.path.abspath(__file__))
_TICKER_RE = re.compile(r"[A-Z0-9.\-^=]{1,20}")

# The last successful download of each ticker is kept on disk and used when the live source fails.
SNAPSHOT_DIR = os.environ.get("ETF_SNAPSHOT_DIR", os.path.join(_HERE, ".yf_cache"))
# Optional snapshots shipped with the app; read-only, consulted last.
SEED_DIR = os.path.join(_HERE, "data", "snapshots")
# Snapshots of the most used tickers, refreshed daily by a scheduled job and published on a branch
# of the source repository. Reading them keeps ordinary visits away from the live source, which
# throttles shared hosting addresses. Set ETF_SNAPSHOT_MIRROR to another base URL, or to "" to turn it off.
MIRROR_BRANCH = "market-data"
MIRROR_URL = os.environ.get(
    "ETF_SNAPSHOT_MIRROR", SOURCE_URL.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/" + MIRROR_BRANCH)
# A stored copy fetched within this many hours is used as it is, without contacting the live source.
SNAPSHOT_MAX_AGE_HOURS = 36
_MIRROR_MISS_SECONDS = 3600
_mirror_misses = {}
# The mirror also publishes index.csv: every ticker it carries, with its name and listing date.
INDEX_FILE = "index.csv"
_index_cache = {"at": float("-inf"), "entries": None}
# Official list of every ETF listed on the Taiwan Stock Exchange (market 1 = listed, issue type I = ETF).
LISTED_ETF_URL = ("https://isin.twse.com.tw/isin/class_main.jsp?owncode=&stockname=&isincode="
                  "&market=1&issuetype=I&industry_code=&Page=1&chklike=Y")
_live_requests = set()
_state_lock = threading.Lock()

# Taiwan Stock Exchange: official, but one month per request and a firewall that rejects anything
# faster than a request every several seconds. Far too slow for a whole history, so it can only
# bring a stored snapshot up to date when the main source is down.
# Off unless ETF_TWSE_TOP_UP=1: from cloud hosts the firewall also refuses requests at random, and
# the path has not yet completed end to end against the real exchange.
TWSE_TOP_UP = os.environ.get("ETF_TWSE_TOP_UP") == "1"
TWSE_URL = "https://www.twse.com.tw/rwd/zh"
_TWSE_INTERVAL = 10.0
_TWSE_ATTEMPTS = 3
_TWSE_MAX_MONTHS = 3
_TWSE_FRESH_DAYS = 3
_TWSE_CACHE_SECONDS = 3600
_twse_lock = threading.Lock()
_twse_state = {"last_call": float("-inf"), "dividends": {}}

# A split the source never back-adjusted shows up as a one-day move this large or larger.
_SEAM_RATIO = 1.9
_SEAM_TOLERANCE = 0.15
# Daily moves beyond max(_ANOMALY_FLOOR, _ANOMALY_SIGMAS x typical daily move) are reported to the user.
_ANOMALY_FLOOR = 0.25
_ANOMALY_SIGMAS = 12
_DIVIDEND_YIELD_CEILING = 0.15
# A regular payer whose record starts with this many dividend-free months probably has a gap at the source.
_DIVIDEND_GAP_MONTHS = 24
_MIN_PAYOUTS_FOR_GAP_CHECK = 4

# Days on which the source shows a permanent level shift that is neither a split nor a market move.
# 2015-08-24: 00631L closes -33.6% and 00632R +42.6% while their underlying (0050) moves -3.9%, and
# both stay displaced from it afterwards, which a 2x / -1x fund cannot do.
KNOWN_BAD_DAYS = {
    "00631L.TW": ("2015-08-24",),
    "00632R.TW": ("2015-08-24",),
}


def normalize_ticker(raw):
    ticker = str(raw).strip().upper()
    if not ticker:
        raise ValueError("請輸入 Yahoo Finance 代號，例如 0056.TW、00679B.TWO 或 SPY。")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"代號「{ticker}」格式不正確：只能包含英數字與 . - ^ = 符號，最長 20 個字元。")
    return ticker


def validate_history(df):
    if df is None or df.empty:
        raise ValueError("資料來源回傳空值")
    if not {"Close", "Dividends"}.issubset(df.columns):
        raise ValueError("資料缺少價格或配息欄位")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans or df.index.has_duplicates:
        raise ValueError("行情日期格式異常或包含重複日期")
    prices = pd.to_numeric(df['Close'], errors='coerce').dropna()
    dividends = pd.to_numeric(df['Dividends'], errors='coerce')
    if prices.empty or not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("歷史價格為空或含無效價格")
    if not np.isfinite(dividends).all() or (dividends < 0).any():
        raise ValueError("配息資料含缺值或無效數值，無法可靠計算現金流")


# ------------------------------------------------------------------
# Snapshots
# ------------------------------------------------------------------
def save_snapshot(df, ticker, directory=None):
    """Write the raw history as CSV. Dates are stored as exchange-local calendar days."""
    directory = directory or SNAPSHOT_DIR
    if not directory:
        return None
    ticker = normalize_ticker(ticker)
    columns = [c for c in ("Close", "Dividends", "Stock Splits") if c in df.columns]
    out = df[columns].copy()
    out.index = pd.DatetimeIndex(out.index).tz_localize(None).normalize()
    out.index.name = "Date"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{ticker}.csv")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"# fetched_at={df.attrs.get('fetched_at') or _now()}\n")
        out.to_csv(fh)
    os.replace(tmp, path)
    return path


def _parse_snapshot(source, ticker):
    """A stored history from a path or an open text stream, or None if it is unusable."""
    try:
        if isinstance(source, str):
            with open(source, encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = source.read()
        first = text.split("\n", 1)[0].strip()
        df = pd.read_csv(io.StringIO(text), comment="#", index_col="Date", parse_dates=["Date"])
        validate_history(df)
    except (OSError, ValueError, KeyError):
        return None
    fetched_at = first.split("=", 1)[1] if first.startswith("# fetched_at=") else ""
    df.attrs.update(ticker=ticker, data_source="snapshot", fetched_at=fetched_at)
    return df


def _stored(directory, ticker):
    return _parse_snapshot(os.path.join(directory, f"{ticker}.csv"), ticker) if directory else None


def read_snapshot(ticker):
    """A stored history for the ticker, the local copy before the shipped one, or None."""
    ticker = normalize_ticker(ticker)
    for directory in (SNAPSHOT_DIR, SEED_DIR):
        df = _stored(directory, ticker)
        if df is not None:
            return df
    return None


IN_BROWSER = sys.platform == "emscripten"


def live_source_available():
    return yf is not None


def _listed_extras():
    names = set()
    if os.path.isdir(SEED_DIR):
        names |= {f[:-4] for f in os.listdir(SEED_DIR) if f.endswith(".csv")}
    listing = os.path.join(_HERE, "data", "mirror_tickers.txt")
    if os.path.exists(listing):
        with open(listing, encoding="utf-8") as fh:
            names |= {line.split("#")[0].strip() for line in fh if line.split("#")[0].strip()}
    return names


def available_snapshots():
    """Tickers the app can load without the live source: the mirror's index when it can be read,
    otherwise the shipped snapshots and the extra list."""
    index = mirror_index()
    return sorted(set(index) | _listed_extras()) if index else sorted(_listed_extras())


def _http_get_text(url, timeout=8):
    if IN_BROWSER:  # no sockets in the browser; a synchronous request from the worker instead
        from pyodide.http import open_url
        return open_url(url).read()
    request = urllib.request.Request(url, headers={"User-Agent": "etf-stress-test"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def parse_index(text):
    """index.csv -> {ticker: {"name": ..., "listed": ...}}."""
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    if "ticker" not in frame.columns:
        raise ValueError("清單格式不正確")
    return {row["ticker"]: {"name": row.get("name", ""), "listed": row.get("listed", "")}
            for _, row in frame.iterrows() if row["ticker"]}


def write_index(entries, directory):
    """Write {ticker: {"name", "listed"}} as index.csv, sorted by ticker."""
    rows = [{"ticker": t, "name": e.get("name", ""), "listed": e.get("listed", "")} for t, e in sorted(entries.items())]
    path = os.path.join(directory, INDEX_FILE)
    os.makedirs(directory, exist_ok=True)
    pd.DataFrame(rows, columns=["ticker", "name", "listed"]).to_csv(path, index=False)
    return path


def mirror_index():
    """The mirror's index of tickers it carries, or {} when it cannot be read. Cached for an hour."""
    if not MIRROR_URL:
        return {}
    with _state_lock:
        if time.monotonic() - _index_cache["at"] < _MIRROR_MISS_SECONDS:
            return dict(_index_cache["entries"] or {})
    try:
        entries = parse_index(_http_get_text(f"{MIRROR_URL}/{INDEX_FILE}"))
    except (OSError, ValueError):
        entries = {}
    with _state_lock:
        _index_cache.update(at=time.monotonic(), entries=entries)
    return dict(entries)


def listing_info(ticker):
    """Name and official listing date of a ticker when the mirror's index knows it, else {}."""
    return mirror_index().get(normalize_ticker(ticker), {})


def parse_listed_etfs(html):
    """The exchange's ETF listing page -> {ticker: {"name", "listed"}} for listed ('上市') ETFs."""
    entries = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>|&nbsp;", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(cells) < 8 or cells[4] != "上市" or cells[5] != "ETF":
            continue
        code = cells[2].upper()
        if re.fullmatch(r"[0-9A-Z]{4,8}", code):
            entries[f"{code}.TW"] = {"name": cells[3], "listed": cells[7].replace("/", "-")}
    return entries


def fetch_listed_etfs(attempts=5, pause=40):
    """Every ETF listed on the Taiwan Stock Exchange, from the exchange's own list.

    Its firewall turns away a share of ordinary requests from cloud hosts with a short HTML page,
    so a refusal is retried after a pause. Raises if every attempt is refused or the list is empty.
    """
    last = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(pause)
        try:
            request = urllib.request.Request(LISTED_ETF_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
        except OSError as exc:
            last = exc
            continue
        for encoding in ("utf-8", "cp950"):
            try:
                html = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            html = raw.decode("cp950", errors="replace")
        entries = parse_listed_etfs(html)
        if len(entries) >= 50:          # a refusal page, or a page cut short, has none or very few
            return entries
        last = ValueError(f"清單只有 {len(entries)} 檔，可能被拒絕或不完整")
    raise ConnectionError(f"無法取得上市 ETF 清單：{last}")


def fetch_mirror(ticker):
    """The daily published snapshot of a ticker, or None. A miss is remembered for an hour."""
    if not MIRROR_URL:
        return None
    with _state_lock:
        if time.monotonic() - _mirror_misses.get(ticker, float("-inf")) < _MIRROR_MISS_SECONDS:
            return None
    try:
        text = _http_get_text(f"{MIRROR_URL}/{urllib.parse.quote(ticker)}.csv")
        df = _parse_snapshot(io.StringIO(text), ticker)
    except (OSError, ValueError):
        df = None
    if df is None:
        with _state_lock:
            _mirror_misses[ticker] = time.monotonic()
    return df


def _age_hours(df):
    """Hours since the copy was fetched from the live source; infinite when unknown."""
    try:
        fetched = datetime.strptime(df.attrs.get("fetched_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 3600


def request_live(ticker):
    """Make the next load of this ticker go to the live source even if a recent copy is stored."""
    with _state_lock:
        _live_requests.add(normalize_ticker(ticker))
        _mirror_misses.pop(normalize_ticker(ticker), None)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _twse_get(path, **params):
    """One throttled request to the exchange, retried when its firewall turns it away.

    The firewall rejects a share of perfectly ordinary requests from cloud addresses, so a
    refusal is retried after the usual pause. Raises if every attempt fails or the exchange
    answers with an error status.
    """
    url = f"{TWSE_URL}/{path}?" + urllib.parse.urlencode({"response": "json", **params})
    last_error = None
    with _twse_lock:
        for _ in range(_TWSE_ATTEMPTS):
            wait = _twse_state["last_call"] + _TWSE_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except (OSError, ValueError) as exc:  # refused, unreachable, or the firewall's HTML page
                last_error = exc
            finally:
                _twse_state["last_call"] = time.monotonic()
        else:
            raise ConnectionError(f"證交所沒有正常回應：{last_error}") from last_error
    if payload.get("stat") != "OK":
        if "沒有符合條件" in str(payload.get("stat", "")):
            return {"fields": [], "data": []}
        raise ValueError(f"證交所回應異常：{payload.get('stat')}")
    return payload


def _roc_date(text):
    """'114/06/02' or '114年06月02日' (Republic of China calendar) -> Timestamp."""
    year, month, day = (int(x) for x in re.findall(r"\d+", text)[:3])
    return pd.Timestamp(year + 1911, month, day)


def twse_month_closes(stock_no, period):
    """Closing prices actually traded on the exchange during one calendar month."""
    payload = _twse_get("afterTrading/STOCK_DAY", date=f"{period.year}{period.month:02d}01", stockNo=stock_no)
    if not payload["data"]:
        return pd.Series(dtype=float)
    date_col, close_col = payload["fields"].index("日期"), payload["fields"].index("收盤價")
    closes = {}
    for row in payload["data"]:
        try:
            closes[_roc_date(row[date_col])] = float(str(row[close_col]).replace(",", ""))
        except ValueError:
            continue  # "--": listed but not traded that day
    return pd.Series(closes, dtype=float).sort_index()


def twse_month_distributions(period, through):
    """Ex-dividend and ex-rights events of every listed security in one month, up to `through`.

    Returns (date, code, value, kind) tuples. The exchange rejects ranges longer than about a
    month and ranges that reach the current day.
    """
    end = min(period.end_time.normalize(), through)
    cached = _twse_state["dividends"].get((period, end))
    if cached and time.monotonic() - cached[0] < _TWSE_CACHE_SECONDS:
        return cached[1]
    payload = _twse_get("exRight/TWT49U", startDate=f"{period.year}{period.month:02d}01",
                        endDate=end.strftime("%Y%m%d"))
    events = []
    if payload["data"]:
        f = payload["fields"]
        cols = [f.index(name) for name in ("資料日期", "股票代號", "權值+息值", "權/息")]
        for row in payload["data"]:
            date, code, value, kind = (row[c] for c in cols)
            events.append((_roc_date(date), str(code).strip(), float(str(value).replace(",", "")), str(kind).strip()))
    _twse_state["dividends"][(period, end)] = (time.monotonic(), events)
    return events


def _today():
    return pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None).normalize()


def top_up_from_twse(snapshot, ticker):
    """Extend a stored snapshot with exchange data. Returns the snapshot itself if there is nothing to add.

    Only for Taiwan Stock Exchange listings (.TW) and gaps of a few months, and only up to the
    previous day, the latest for which the exchange serves its distribution table. The exchange
    and the snapshot must agree on the snapshot's last day, and a failure anywhere raises, so
    the result is never a partial update.
    """
    if not ticker.endswith(".TW"):
        return snapshot
    stock_no = ticker[:-3]
    last = snapshot.index.max()
    through = _today() - pd.Timedelta(days=1)
    if (through - last).days <= _TWSE_FRESH_DAYS:
        return snapshot
    months = pd.period_range(last, through, freq="M")
    if len(months) > _TWSE_MAX_MONTHS:
        return snapshot

    closes = pd.concat([twse_month_closes(stock_no, m) for m in months])
    if last not in closes.index or abs(closes[last] / snapshot.loc[last, "Close"] - 1) > 0.01:
        raise ValueError("證交所與存檔在同一天的價格不一致，不合併")
    new = closes[(closes.index > last) & (closes.index <= through)]
    if new.empty:
        return snapshot

    added = pd.DataFrame({"Close": new, "Dividends": 0.0}, index=new.index)
    for month in months:
        for date, code, value, kind in twse_month_distributions(month, through):
            if code != stock_no or date not in added.index:
                continue
            if kind != "息":
                raise ValueError("補齊期間有除權，價格需要另外還原，不合併")
            added.loc[date, "Dividends"] += value
    if "Stock Splits" in snapshot.columns:
        added["Stock Splits"] = 0.0
    out = pd.concat([snapshot, added[snapshot.columns]])
    validate_history(out)
    out.attrs = dict(snapshot.attrs)
    out.attrs.update(data_source="snapshot+twse", topped_up_to=new.index.max().strftime("%Y-%m-%d"))
    return out


def _save_quietly(df, ticker):
    try:
        save_snapshot(df, ticker)
    except OSError:
        pass  # a read-only disk must not stop usable data from being used


def load_history(ticker):
    """Full daily history, from the nearest place that has a recent copy.

    A copy fetched within SNAPSHOT_MAX_AGE_HOURS is used directly: the local one first, then
    the daily published mirror. Otherwise the live source is asked. If that fails, the newest
    stored copy of any age is returned, marked as a snapshot and brought up to date from the
    exchange where that is switched on. request_live() skips the stored copies once.
    """
    ticker = normalize_ticker(ticker)
    with _state_lock:
        forced = ticker in _live_requests
        _live_requests.discard(ticker)

    local = mirror = None
    if not forced:
        local = _stored(SNAPSHOT_DIR, ticker)
        if local is not None and _age_hours(local) <= SNAPSHOT_MAX_AGE_HOURS:
            local.attrs["data_source"] = "cache"
            return local
        mirror = fetch_mirror(ticker)
        if mirror is not None and _age_hours(mirror) <= SNAPSHOT_MAX_AGE_HOURS:
            mirror.attrs["data_source"] = "mirror"
            _save_quietly(mirror, ticker)
            return mirror

    last_error = None
    # Fetch prices and corporate actions together; a failed dividend request
    # must not silently turn an income strategy into a zero-dividend strategy.
    for attempt in range(3 if yf is not None else 0):
        try:
            kwargs = {"period": "max"} if attempt < 2 else {"start": "1900-01-01"}
            df = yf.Ticker(ticker).history(
                **kwargs, auto_adjust=False, actions=True, timeout=20
            )
            validate_history(df)
            df.attrs.update(ticker=ticker, data_source="live", fetched_at=_now())
            _save_quietly(df, ticker)
            return df
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)

    if forced:
        local, mirror = _stored(SNAPSHOT_DIR, ticker), fetch_mirror(ticker)
    copies = [c for c in (local, mirror, _stored(SEED_DIR, ticker)) if c is not None]
    if copies:
        snapshot = min(copies, key=_age_hours)   # ties keep the order above: local, mirror, shipped
        snapshot.attrs["data_source"] = "snapshot"
        if not TWSE_TOP_UP:
            return snapshot
        try:
            return top_up_from_twse(snapshot, ticker)
        except Exception:
            return snapshot  # a stale but whole snapshot beats a half-merged one
    if yf is None:
        known = available_snapshots()
        raise ValueError(
            f"單機版無法即時查詢行情，只能使用台灣上市的 ETF（目前 {len(known)} 檔，每天自動更新），沒有 {ticker} 的資料。"
            "請確認代號是否正確，例如 0056.TW、00878.TW。要測試其他商品，請使用網頁版。")
    raise ValueError(
        f"暫時無法取得 {ticker} 的完整歷史資料（已嘗試 3 次），也沒有先前存檔的資料可用。"
        "這不代表代號不存在，也可能是來源暫時異常或限制連線；"
        "請稍後按「重新載入行情」，並檢查代號。"
    ) from last_error


# ------------------------------------------------------------------
# Repair
# ------------------------------------------------------------------
def _split_factor(ratio):
    """(scale for earlier prices, human label) if a one-day price ratio looks like an unadjusted split."""
    if ratio <= 1 / _SEAM_RATIO:
        n = round(1 / ratio)
        if n >= 2 and abs(ratio * n - 1) <= _SEAM_TOLERANCE:
            return 1 / n, f"1 股拆成 {n} 股"
    elif ratio >= _SEAM_RATIO:
        n = round(ratio)
        if n >= 2 and abs(ratio / n - 1) <= _SEAM_TOLERANCE:
            return float(n), f"{n} 股併成 1 股"
    return None


def _fix_dividend_units(df, scale, seam_date):
    """Bring dividends still quoted in pre-split units onto the repaired price basis.

    The source back-adjusts prices and dividends to different dates, so the seam in the prices
    says nothing about which dividends are stale. Stale ones are always the oldest, and they make
    the yield jump by the split ratio, so the cut-off is the one that makes yearly yields most
    alike. When every year looks alike the dividends are assumed consistent, unless only the
    rescaled yield is believable. With very uneven payouts next to the cut-off (a stale year that
    paid unusually little, or a good year that paid several times the norm) it can land a year or
    two off.
    """
    paid = df['Dividends'] > 0
    if not paid.any():
        return None
    prev_close = df['Close'].shift(1).fillna(df['Close'])
    yearly = (df.loc[paid, 'Dividends'] / prev_close[paid]).groupby(df.index[paid].year).sum()
    years = list(yearly.index)
    logs = np.log(yearly.to_numpy())
    shift = np.log(scale)

    def spread(n_scaled):
        x = logs.copy()
        x[:n_scaled] += shift
        return np.abs(x - np.median(x)).sum()

    costs = [spread(n) for n in range(len(years))]
    best = int(np.argmin(costs))
    stale = None
    if best > 0 and costs[0] - costs[best] >= 0.5 * abs(shift):
        stale = paid & (df.index.year <= years[best - 1])
    else:
        typical = float(np.median(yearly))
        if not 0.002 <= typical <= 0.20 and 0.002 <= typical * scale <= 0.20:
            stale = paid & (df.index < seam_date)
    if stale is None or not stale.any():
        return None
    df.loc[stale, 'Dividends'] *= scale
    dates = df.index[stale]
    return f"其中 {int(stale.sum())} 筆配息（{dates[0]:%Y-%m-%d} 至 {dates[-1]:%Y-%m-%d}）仍是分割前的單位，已一併換算"


def repair_history(df, ticker=""):
    """Undo price seams the source left in. Returns the repaired frame and a note per repair.

    Handles (1) splits that were never back-adjusted, recognised as a one-day jump of a whole
    ratio in a ticker for which the source reports no split events at all, and (2) the curated
    KNOWN_BAD_DAYS. A ticker whose split events are reported is left alone: there a large move
    is more likely real, and it is surfaced by find_anomalies instead.
    """
    df = df.copy()
    notes = []

    for day in KNOWN_BAD_DAYS.get(ticker, ()):
        ts = pd.Timestamp(day)
        if ts in df.index and df.index.get_loc(ts) > 0:
            pos = df.index.get_loc(ts)
            ratio = df['Close'].iloc[pos] / df['Close'].iloc[pos - 1]
            before = df.index < ts
            df.loc[before, ['Close', 'Dividends']] *= ratio
            notes.append(f"{ts:%Y-%m-%d} 來源價格出現 {ratio - 1:+.1%} 的永久位移，與標的指數走勢不符，"
                         "已視為資料錯誤並把當日漲跌當作 0。")

    splits = df['Stock Splits'] if 'Stock Splits' in df.columns else None
    if splits is not None and (pd.to_numeric(splits, errors='coerce').fillna(0) != 0).any():
        return df, notes

    ratios = df['Close'] / df['Close'].shift(1)
    jumps = ratios[(ratios <= 1 / _SEAM_RATIO) | (ratios >= _SEAM_RATIO)]
    for ts in sorted(jumps.index, reverse=True):
        pos = df.index.get_loc(ts)
        ratio = df['Close'].iloc[pos] / df['Close'].iloc[pos - 1]
        found = _split_factor(ratio)
        if found is None:
            continue
        scale, label = found
        df.loc[df.index < ts, 'Close'] *= scale
        note = f"{ts:%Y-%m-%d} 的價格跳動（{ratio - 1:+.1%}）符合{label}的股票分割，而來源沒有還原；已把這天之前的價格換算成同一基準"
        dividend_note = _fix_dividend_units(df, scale, ts)
        notes.append(note + ("，" + dividend_note if dividend_note else "") + "。")
    return df, notes


def find_anomalies(df, limit=5):
    """Daily moves far outside the asset's own normal range: bad data or a genuine extreme, worth a look either way."""
    ratios = (df['Close'] / df['Close'].shift(1)).dropna()
    if len(ratios) < 20:
        return []
    logs = np.log(ratios)
    sigma = 1.4826 * float(np.median(np.abs(logs - np.median(logs))))
    threshold = -np.log(1 - max(_ANOMALY_FLOOR, min(0.9, _ANOMALY_SIGMAS * sigma)))
    flagged = logs[logs.abs() > threshold]
    worst = flagged.reindex(flagged.abs().sort_values(ascending=False).index[:limit]).sort_index()
    notes = [f"{ts:%Y-%m-%d} 單日 {np.expm1(v):+.1%}" for ts, v in worst.items()]
    if len(flagged) > limit:
        notes.append(f"另有 {len(flagged) - limit} 筆")
    return notes


# ------------------------------------------------------------------
# Monthly series
# ------------------------------------------------------------------
def monthly_data(df, pay_day, repair=True, allow_short=False):
    """One row per calendar month, priced on the first trading day on or after `pay_day`.

    A dividend belongs to the period in which the price went ex-dividend: the first monthly
    quote on or after its ex-date. Dividends after the latest quote wait for the next one.
    """
    validate_history(df)
    if not isinstance(pay_day, (int, np.integer)) or not 1 <= pay_day <= 31:
        raise ValueError("每月扣款日必須介於 1 至 31 日。")
    source = dict(df.attrs)
    df = df.copy().sort_index()
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    df['Dividends'] = pd.to_numeric(df['Dividends'], errors='coerce')
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.dropna(subset=['Close'])
    if df.empty or (df['Close'] <= 0).any():
        raise ValueError("歷史價格為空或含非正價格，無法回測。")

    repairs = []
    if repair:
        df, repairs = repair_history(df, source.get('ticker', ''))
    anomalies = find_anomalies(df)

    selected = []
    for _, group in df.groupby(df.index.to_period('M')):
        eligible = group[group.index.day >= pay_day]
        selected.append(eligible.index[0] if not eligible.empty else group.index[-1])
    quotes = pd.DatetimeIndex(selected)
    monthly = df.loc[quotes, ['Close']].copy()
    monthly['Quote_Date'] = quotes
    monthly.index = quotes.to_period('M')
    expected = pd.period_range(monthly.index.min(), monthly.index.max(), freq='M')
    if not monthly.index.equals(expected):
        raise ValueError("歷史價格有缺漏月份，無法將跨月變動當作單月報酬；請重新載入行情。")

    paid = df.loc[df['Dividends'] > 0, 'Dividends']
    period = quotes.searchsorted(paid.index, side='left')
    in_range = period < len(quotes)
    per_period = paid[in_range].groupby(period[in_range]).sum()
    monthly_div = np.zeros(len(quotes))
    monthly_div[per_period.index.to_numpy()] = per_period.to_numpy()

    monthly['YYYYMM'] = monthly.index
    monthly['Monthly_Div'] = monthly_div
    monthly['Price_Return'] = monthly['Close'].pct_change(fill_method=None)
    monthly['Div_Yield'] = monthly['Monthly_Div'] / monthly['Close'].shift(1)
    base_month, base_close = monthly.index[0], float(monthly['Close'].iloc[0])
    monthly = monthly.dropna(subset=['Price_Return'])
    if monthly.empty and not allow_short:
        raise too_short_error(source.get('ticker', '') or "這檔標的", df.index.min(), base_month)

    rich = monthly['Div_Yield'] > _DIVIDEND_YIELD_CEILING
    anomalies += [f"{m} 配息相當於股價的 {y:.1%}" for m, y in monthly.loc[rich, 'Div_Yield'].items()]
    payers = monthly.index[monthly['Monthly_Div'] > 0]
    if len(payers) >= _MIN_PAYOUTS_FOR_GAP_CHECK and (payers[0] - monthly.index[0]).n >= _DIVIDEND_GAP_MONTHS:
        anomalies.append(f"{monthly.index[0]} 至 {payers[0] - 1} 沒有任何配息紀錄，之後才開始有。"
                         "如果它當時其實有配息，就是來源缺漏；這段期間的配息以 0 計")

    monthly.attrs.update(
        ticker=source.get('ticker', ''),
        data_source=source.get('data_source', 'live'),
        fetched_at=source.get('fetched_at', ''),
        topped_up_to=source.get('topped_up_to', ''),
        source_start=df.index.min().strftime('%Y-%m-%d'),
        source_end=df.index.max().strftime('%Y-%m-%d'),
        repairs=repairs,
        anomalies=anomalies,
        base_month=str(base_month),
        base_close=base_close,
    )
    return monthly


def too_short_error(ticker, first_day, base_month):
    """Why a history with a single month of prices cannot be tested yet, and what can be done."""
    return ValueError(
        f"{ticker} 的第一筆價格在 {pd.Timestamp(first_day):%Y-%m-%d}，目前只有一個月份的價格，還無法計算月報酬；"
        f"沒有指定替身時，最早要等到 {pd.Period(base_month, freq='M') + 1} 有了第二筆月價才能進場。"
        "如果想現在就測試，可以在側欄「上市前的歷史用哪一檔代替」指定一檔上市更久的 ETF，用它的舊資料補上。")


def backfill_with_proxy(asset, proxy):
    """Extend a short monthly history backwards with another asset's returns and dividend yields.

    Months before the asset existed take the proxy's price return and dividend yield unchanged;
    prices are chained backwards from the asset's first real quote so the series stays continuous.
    Backfilled rows are marked in the `Synthetic` column. Returns the asset untouched when the
    proxy does not reach back further or leaves a gap before the asset starts.
    """
    asset = asset.copy()
    asset['Synthetic'] = False
    # The asset's first price month: before its first return, or its only month when it has none yet.
    base = pd.Period(asset.attrs['base_month'], freq='M') if 'base_month' in asset.attrs else asset.index[0] - 1
    earlier = proxy[proxy.index <= base]
    if earlier.empty or earlier.index[-1] != base:
        return asset

    returns = earlier['Price_Return'].to_numpy()
    close = np.empty(len(earlier))
    close[-1] = (asset.attrs['base_close'] if 'base_close' in asset.attrs
                 else asset['Close'].iloc[0] / (1 + asset['Price_Return'].iloc[0]))
    for i in range(len(earlier) - 1, 0, -1):
        close[i - 1] = close[i] / (1 + returns[i])
    previous_close = close / (1 + returns)

    filled = pd.DataFrame({
        'Close': close,
        'Quote_Date': earlier['Quote_Date'].to_numpy(),
        'YYYYMM': earlier.index,
        'Monthly_Div': earlier['Div_Yield'].to_numpy() * previous_close,
        'Price_Return': returns,
        'Div_Yield': earlier['Div_Yield'].to_numpy(),
        'Synthetic': True,
    }, index=earlier.index)

    overlap = asset[['Price_Return']].join(proxy[['Price_Return']], rsuffix='_proxy', how='inner')
    correlation = float(overlap.corr().iloc[0, 1]) if len(overlap) >= 12 else float('nan')

    out = pd.concat([filled, asset[filled.columns]]) if not asset.empty else filled
    out.attrs = dict(asset.attrs)
    out.attrs['backfill'] = {
        'proxy': proxy.attrs.get('ticker', ''),
        'months': len(filled),
        'start': str(filled.index[0]),
        'end': str(filled.index[-1]),
        'overlap_months': len(overlap),
        'correlation': correlation,
    }
    return out


def align_months(df_a, df_b=None):
    """Join the main asset with the optional second asset on calendar months.

    The result covers the main asset's months up to the last month both have. Months before the
    second asset existed are kept, with its columns empty, for the engine to model.
    """
    sources = [dict(df_a.attrs)]
    if df_b is not None:
        sources.append(dict(df_b.attrs))
        end = min(df_a.index.max(), df_b.index.max())
        a, b = df_a[df_a.index <= end], df_b[df_b.index <= end]
        if a.empty or b.empty or b.index.min() > end or len(a.index.intersection(b.index)) == 0:
            raise ValueError("兩檔標的沒有共同可回測月份，請更換標的。")
        merged = a.join(b, lsuffix='_A', rsuffix='_B', how='left')
        merged = merged.rename(columns={c: f'{c}_A' for c in ('Synthetic',) if c in merged.columns})
    else:
        merged = df_a.rename(columns={c: f'{c}_A' for c in df_a if c != 'YYYYMM'})
    if merged.empty:
        raise ValueError("兩檔標的沒有共同可回測月份，請更換標的。")
    expected = pd.period_range(merged.index.min(), merged.index.max(), freq='M')
    if not merged.index.equals(expected):
        raise ValueError("共同資料有缺漏月份，無法安全執行逐月回測。")
    if 'Synthetic_A' not in merged.columns:
        merged['Synthetic_A'] = False
    merged.index = merged.index.to_timestamp()
    merged.attrs['sources'] = sources
    return merged


def refresh_snapshots(tickers, directory, pause=0.2):
    """Download each ticker from the live source into `directory`. Returns how many came back live.

    A ticker the live source refuses keeps its newest stored copy, so one bad day does not drop
    it from the published set.
    """
    live = 0
    for position, symbol in enumerate(tickers):
        if position and pause:
            time.sleep(pause)
        try:
            request_live(symbol)
            history = load_history(symbol)
        except ValueError as exc:
            print(f"{symbol}: FAILED ({exc})")
            continue
        live += history.attrs.get("data_source") == "live"
        print(f"{symbol}: {history.attrs.get('data_source')} {history.attrs.get('fetched_at')} -> "
              f"{save_snapshot(history, symbol, directory)}")
    return live


def mirror_universe(extra):
    """What the daily refresh publishes: every listed ETF plus `extra`, as {ticker: {"name", "listed"}}.

    When the exchange's list cannot be fetched, the previously published index stands in, so a
    bad day does not shrink the set.
    """
    try:
        entries = fetch_listed_etfs()
        print(f"listed ETFs from the exchange: {len(entries)}")
    except ConnectionError as exc:
        entries = mirror_index()
        print(f"{exc}; using the previously published index ({len(entries)} tickers)")
    for symbol in extra:
        entries.setdefault(normalize_ticker(symbol), {"name": "", "listed": ""})
    return entries


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download market-data snapshots from the live source.")
    parser.add_argument("tickers", nargs="*", help="Yahoo Finance symbols, e.g. 0050.TW 0056.TW")
    parser.add_argument("--file", help="text file with one symbol per line (# starts a comment)")
    parser.add_argument("--listed-etfs", action="store_true",
                        help="also every ETF listed on the Taiwan Stock Exchange, and write index.csv")
    parser.add_argument("--dir", default=SEED_DIR, help="folder to write to (default: data/snapshots)")
    cli = parser.parse_args()
    symbols = list(cli.tickers)
    if cli.file:
        with open(cli.file, encoding="utf-8") as fh:
            symbols += [line.split("#")[0].strip() for line in fh if line.split("#")[0].strip()]
    if cli.listed_etfs:
        universe = mirror_universe(symbols)
        symbols = sorted(universe)
    if not symbols:
        parser.error("no tickers given")
    succeeded = refresh_snapshots(symbols, cli.dir)
    if cli.listed_etfs:
        published = {t: e for t, e in universe.items() if os.path.exists(os.path.join(cli.dir, f"{t}.csv"))}
        print(f"index: {len(published)} tickers -> {write_index(published, cli.dir)}")
    sys.exit(0 if succeeded else 1)
