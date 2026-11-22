"""Compare Yahoo and official (TWSE TWT49U) dividends for 0050, 0056 and 00878, and time the official fetch.

Run from the repository root on a machine the exchange does not block (GitHub Actions):
    python compare_dividends.py [output_dir]
Does a full from-scratch fetch of every year since 2003 (about 24 requests, 10 s apart), writes
dividends_twse.csv to output_dir (default ./official_out), then compares.
"""
import os, sys, time
sys.path.insert(0, os.getcwd())
import pandas as pd
import market_data as M

out = sys.argv[1] if len(sys.argv) > 1 else "official_out"
M.MIRROR_URL = ""          # force a from-scratch fetch rather than starting from the published table
M.SNAPSHOT_DIR = os.path.join(out, "cache")

t0 = time.monotonic()
table, years = M.fetch_twse_events()
fetch_seconds = time.monotonic() - t0
M.write_dividend_events(table, years, out)
print(f"official fetch: {len(years)} years, {len(table)} ETF events, {fetch_seconds:.0f} s "
      f"({fetch_seconds / max(1, len(years)):.1f} s per year); years missing: "
      f"{sorted(set(range(2003, pd.Timestamp.now().year + 1)) - set(years)) or 'none'}")
M._events_cache.update(at=time.monotonic(), table=M.parse_dividend_events(open(os.path.join(out, M.DIVIDENDS_FILE), encoding="utf-8").read()))

pd.set_option("display.width", 200)
for ticker in ("0050.TW", "0056.TW", "00878.TW"):
    t1 = time.monotonic()
    raw = M.load_history(ticker)
    code = ticker[:-3]
    ev = table[(table["Code"] == code) & (table["Kind"] != "權")]
    yahoo_raw = raw.loc[raw["Dividends"] > 0, "Dividends"].groupby(raw.index[raw["Dividends"] > 0].year).sum()
    official_raw = ev.groupby(ev["Date"].dt.year)["Cash"].sum()
    # the same on the price basis the app uses (split-repaired / split-adjusted)
    yahoo_app = M.monthly_data(raw, 1)
    official_app = M.monthly_data(M.attach_official_dividends(raw, ticker), 1)
    ya = yahoo_app.groupby(yahoo_app.index.year)["Monthly_Div"].sum()
    oa = official_app.groupby(official_app.index.year)["Monthly_Div"].sum()
    frame = pd.DataFrame({"yahoo_as_quoted": yahoo_raw, "official_as_quoted": official_raw,
                          "yahoo_app_basis": ya, "official_app_basis": oa}).fillna(0.0)
    frame["diff_app_basis"] = frame["official_app_basis"] - frame["yahoo_app_basis"]
    print(f"\n=== {ticker}  (source {official_app.attrs['dividend_source']}, "
          f"{len(ev)} official events, Yahoo history {raw.index.min():%Y-%m-%d}..{raw.index.max():%Y-%m-%d}, "
          f"{time.monotonic() - t1:.0f} s) ===")
    print(frame.round(4).to_string())
    print("totals:", frame.sum().round(4).to_dict())
print(f"\ntotal time {time.monotonic() - t0:.0f} s")
