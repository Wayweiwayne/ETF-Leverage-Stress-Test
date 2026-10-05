import unittest
from unittest.mock import patch

import pandas as pd

from market_data import load_history, monthly_data, align_months


def history(dates, prices=None):
    return pd.DataFrame({'Close': prices or [100.0] * len(dates),
                         'Dividends': [0.0] * len(dates)}, index=pd.to_datetime(dates))


class MarketDataTests(unittest.TestCase):
    def test_same_month_different_trading_days(self):
        a = monthly_data(history(['2024-01-10', '2024-02-15', '2024-03-11']), 10)
        b = monthly_data(history(['2024-01-10', '2024-02-16', '2024-03-12']), 10)
        self.assertEqual(len(align_months(a, b)), 2)
        self.assertEqual(align_months(a, b).index[0], pd.Timestamp('2024-02-01'))

    def test_missing_month_rejected(self):
        with self.assertRaises(ValueError):
            monthly_data(history(['2024-01-10', '2024-03-10']), 10)

    def test_dividends_and_price_returns(self):
        df = history(['2024-01-10', '2024-02-10', '2024-02-20'], [100, 110, 112])
        df.loc['2024-02-20', 'Dividends'] = 2
        result = monthly_data(df, 10)
        self.assertAlmostEqual(result.iloc[0]['Price_Return'], 0.1)
        self.assertAlmostEqual(result.iloc[0]['Div_Yield'], 0.02)

    def test_no_overlap_rejected(self):
        a = monthly_data(history(['2024-01-10', '2024-02-10']), 10)
        b = monthly_data(history(['2025-01-10', '2025-02-10']), 10)
        with self.assertRaises(ValueError):
            align_months(a, b)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_empty_response_retried(self, ticker, sleep):
        valid = history(['2024-01-10', '2024-02-10'])
        ticker.return_value.history.side_effect = [pd.DataFrame(), valid]
        pd.testing.assert_frame_equal(load_history('00878.tw'), valid)
        self.assertEqual(ticker.return_value.history.call_count, 2)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_missing_dividends_not_silently_zeroed(self, ticker, sleep):
        ticker.return_value.history.return_value = history(['2024-01-10']).drop(columns='Dividends')
        with self.assertRaises(ValueError):
            load_history('00878.TW')
        self.assertEqual(ticker.return_value.history.call_count, 3)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_explicit_start_fallback(self, ticker, sleep):
        valid = history(['2024-01-10', '2024-02-10'])
        ticker.return_value.history.side_effect = [TimeoutError(), pd.DataFrame(), valid]
        load_history('00878.TW')
        self.assertEqual(ticker.return_value.history.call_args.kwargs['start'], '1900-01-01')

    def test_no_dividend_asset_is_supported(self):
        result = monthly_data(history(['2024-01-10', '2024-02-10']), 10)
        self.assertEqual(result.iloc[0]['Div_Yield'], 0)

    def test_invalid_price_or_dividend_rejected(self):
        for column, value in [('Close', float('inf')), ('Close', -1),
                              ('Dividends', float('nan')), ('Dividends', float('inf'))]:
            with self.subTest(column=column, value=value):
                df = history(['2024-01-10', '2024-02-10'])
                df.loc['2024-02-10', column] = value
                with self.assertRaises(ValueError):
                    monthly_data(df, 10)

    def test_duplicate_dates_rejected(self):
        with self.assertRaises(ValueError):
            monthly_data(history(['2024-01-10', '2024-01-10']), 10)

    def test_timezone_and_month_end(self):
        df = history(['2024-01-30', '2024-02-28'])
        df.index = df.index.tz_localize('America/New_York')
        result = monthly_data(df, 31)
        self.assertEqual(result.iloc[0]['Quote_Date'], pd.Timestamp('2024-02-28'))

    def test_short_history_rejected(self):
        with self.assertRaises(ValueError):
            monthly_data(history(['2024-01-10']), 10)

    @patch('market_data.yf.Ticker')
    def test_blank_symbol_never_requests_network(self, ticker):
        with self.assertRaises(ValueError):
            load_history('  ')
        ticker.assert_not_called()

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_symbols_not_restricted_to_specific_etfs(self, ticker, sleep):
        ticker.return_value.history.return_value = history(['2024-01-10', '2024-02-10'])
        for symbol in [' spy ', 'brk-b', '00679b.two', '0700.hk', '^gspc', 'btc-usd']:
            load_history(symbol)
            ticker.assert_called_with(symbol.strip().upper())


if __name__ == '__main__':
    unittest.main()
