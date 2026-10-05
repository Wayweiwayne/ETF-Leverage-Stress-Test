import unittest
from unittest.mock import patch, MagicMock

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
        self.assertEqual(ticker.return_value.history.call_args.kwargs['start'], '1990-01-01')


if __name__ == '__main__':
    unittest.main()
