"""Market-data loading, repair and calendar-month alignment, independent of the UI."""
import os
import re
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

_HERE = os.path.dirname(os.path.abspath(__file__))
_TICKER_RE = re.compile(r"[A-Z0-9.\-^=]{1,20}")

# The last successful download of each ticker is kept on disk and used when the live source fails.
SNAPSHOT_DIR = os.environ.get("ETF_SNAPSHOT_DIR", os.path.join(_HERE, ".yf_cache"))
# Optional snapshots shipped with the app; read-only, consulted last.
SEED_DIR = os.path.join(_HERE, "data", "snapshots")

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


def read_snapshot(ticker):
    """Most recent stored history for the ticker, or None."""
    ticker = normalize_ticker(ticker)
    for directory in (SNAPSHOT_DIR, SEED_DIR):
        if not directory:
            continue
        path = os.path.join(directory, f"{ticker}.csv")
        try:
            with open(path, encoding="utf-8") as fh:
                first = fh.readline().strip()
            df = pd.read_csv(path, comment="#", index_col="Date", parse_dates=["Date"])
            validate_history(df)
        except (OSError, ValueError, KeyError):
            continue
        fetched_at = first.split("=", 1)[1] if first.startswith("# fetched_at=") else ""
        df.attrs.update(ticker=ticker, data_source="snapshot", fetched_at=fetched_at)
        return df
    return None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_history(ticker):
    """Full daily history. Falls back to the stored snapshot when the live source cannot be reached."""
    ticker = normalize_ticker(ticker)
    last_error = None
    # Fetch prices and corporate actions together; a failed dividend request
    # must not silently turn an income strategy into a zero-dividend strategy.
    for attempt in range(3):
        try:
            kwargs = {"period": "max"} if attempt < 2 else {"start": "1900-01-01"}
            df = yf.Ticker(ticker).history(
                **kwargs, auto_adjust=False, actions=True, timeout=20
            )
            validate_history(df)
            df.attrs.update(ticker=ticker, data_source="live", fetched_at=_now())
            try:
                save_snapshot(df, ticker)
            except OSError:
                pass  # a read-only disk must not stop a successful download from being used
            return df
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    snapshot = read_snapshot(ticker)
    if snapshot is not None:
        return snapshot
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
def monthly_data(df, pay_day, repair=True):
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
    monthly = monthly.dropna(subset=['Price_Return'])
    if monthly.empty:
        raise ValueError("至少需要兩個月份的價格才能計算月報酬。")

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
        source_start=df.index.min().strftime('%Y-%m-%d'),
        source_end=df.index.max().strftime('%Y-%m-%d'),
        repairs=repairs,
        anomalies=anomalies,
    )
    return monthly


def backfill_with_proxy(asset, proxy):
    """Extend a short monthly history backwards with another asset's returns and dividend yields.

    Months before the asset existed take the proxy's price return and dividend yield unchanged;
    prices are chained backwards from the asset's first real quote so the series stays continuous.
    Backfilled rows are marked in the `Synthetic` column. Returns the asset untouched when the
    proxy does not reach back further or leaves a gap before the asset starts.
    """
    asset = asset.copy()
    asset['Synthetic'] = False
    first = asset.index[0]
    earlier = proxy[proxy.index < first]
    if earlier.empty or earlier.index[-1] != first - 1:
        return asset

    returns = earlier['Price_Return'].to_numpy()
    close = np.empty(len(earlier))
    close[-1] = asset['Close'].iloc[0] / (1 + asset['Price_Return'].iloc[0])
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

    out = pd.concat([filled, asset[filled.columns]])
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


if __name__ == "__main__":
    # python market_data.py 0050.TW 0056.TW [--dir data/snapshots]
    args = sys.argv[1:]
    target = None
    if "--dir" in args:
        target = args[args.index("--dir") + 1]
        args = [a for i, a in enumerate(args) if a != "--dir" and (i == 0 or args[i - 1] != "--dir")]
    for symbol in args:
        history = load_history(symbol)
        print(symbol, history.attrs.get("data_source"), save_snapshot(history, symbol, target))
