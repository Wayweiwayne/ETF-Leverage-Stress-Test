"""Market-data loading and calendar-month alignment, independent of the UI."""
import time

import numpy as np
import pandas as pd
import yfinance as yf


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


def load_history(ticker):
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("請輸入 Yahoo Finance 代號，例如 0056.TW、00679B.TWO 或 SPY。")
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
            return df
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise ValueError(
        f"暫時無法取得 {ticker} 的完整歷史資料（已嘗試 3 次）。"
        "這不代表代號不存在，也可能是來源暫時異常或限制連線；"
        "請稍後按「重新載入行情」，並檢查代號。"
    ) from last_error


def monthly_data(df, pay_day):
    validate_history(df)
    if not isinstance(pay_day, (int, np.integer)) or not 1 <= pay_day <= 31:
        raise ValueError("每月扣款日必須介於 1 至 31 日。")
    df = df.copy().sort_index()
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    df['Dividends'] = pd.to_numeric(df['Dividends'], errors='coerce')
    df.index = pd.to_datetime(df.index).tz_localize(None)
    dividends = df['Dividends'].groupby(df.index.to_period('M')).sum()
    prices = df[['Close']].dropna()
    if prices.empty or (prices['Close'] <= 0).any():
        raise ValueError("歷史價格為空或含非正價格，無法回測。")
    selected = []
    for _, group in prices.groupby(prices.index.to_period('M')):
        eligible = group[group.index.day >= pay_day]
        selected.append(eligible.index[0] if not eligible.empty else group.index[-1])
    monthly = prices.loc[selected].copy()
    monthly['Quote_Date'] = monthly.index
    monthly.index = monthly.index.to_period('M')
    expected = pd.period_range(monthly.index.min(), monthly.index.max(), freq='M')
    if not monthly.index.equals(expected):
        raise ValueError("歷史價格有缺漏月份，無法將跨月變動當作單月報酬；請重新載入行情。")
    monthly['YYYYMM'] = monthly.index
    monthly['Monthly_Div'] = dividends.reindex(monthly.index, fill_value=0.0)
    monthly['Price_Return'] = monthly['Close'].pct_change(fill_method=None)
    monthly['Div_Yield'] = monthly['Monthly_Div'] / monthly['Close'].shift(1)
    monthly = monthly.dropna(subset=['Price_Return'])
    if monthly.empty:
        raise ValueError("至少需要兩個月份的價格才能計算月報酬。")
    monthly.attrs['source_start'] = prices.index.min().strftime('%Y-%m-%d')
    monthly.attrs['source_end'] = prices.index.max().strftime('%Y-%m-%d')
    return monthly


def align_months(df_a, df_b=None):
    sources = [dict(df_a.attrs)]
    if df_b is not None:
        sources.append(dict(df_b.attrs))
        merged = df_a.join(df_b, lsuffix='_A', rsuffix='_B', how='inner')
    else:
        merged = df_a.rename(columns={c: f'{c}_A' for c in df_a if c != 'YYYYMM'})
    if merged.empty:
        raise ValueError("兩檔標的沒有共同可回測月份，請更換標的。")
    expected = pd.period_range(merged.index.min(), merged.index.max(), freq='M')
    if not merged.index.equals(expected):
        raise ValueError("共同資料有缺漏月份，無法安全執行逐月回測。")
    merged.index = merged.index.to_timestamp()
    merged.attrs['sources'] = sources
    return merged
