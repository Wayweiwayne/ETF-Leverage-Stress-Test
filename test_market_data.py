import os
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error
from unittest.mock import patch

import numpy as np
import pandas as pd

import market_data
from market_data import (align_months, backfill_with_proxy, find_anomalies, load_history, monthly_data,
                         read_snapshot, repair_history, save_snapshot)


def history(dates, prices=None):
    return pd.DataFrame({'Close': prices or [100.0] * len(dates),
                         'Dividends': [0.0] * len(dates)}, index=pd.to_datetime(dates))


def daily(start, end, price=100.0, seed=0, vol=0.004):
    """Business-day history with small random moves around a level."""
    days = pd.bdate_range(start, end)
    rng = np.random.RandomState(seed)
    close = price * np.cumprod(1 + rng.normal(0, vol, len(days)))
    return pd.DataFrame({'Close': close, 'Dividends': 0.0}, index=days)


def split_at(df, day, ratio):
    """Leave everything before `day` in pre-split units, the way the source does."""
    df = df.copy()
    df.loc[df.index < pd.Timestamp(day), 'Close'] *= ratio
    return df


def pay(df, day, amount):
    ts = df.index[df.index.searchsorted(pd.Timestamp(day))]
    df.loc[ts, 'Dividends'] = amount
    return ts


def yearly_yields(df):
    paid = df['Dividends'] > 0
    y = df.loc[paid, 'Dividends'] / df['Close'].shift(1)[paid]
    return y.groupby(y.index.year).sum()


class IsolatedSnapshots(unittest.TestCase):
    """Keep every test away from the real snapshot folders."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache_dir = os.path.join(tmp.name, "cache")
        self.seed_dir = os.path.join(tmp.name, "seed")
        # No mirror, and no stored copy counts as recent: every load asks the (mocked) live source,
        # unless a test about freshness says otherwise.
        for name, value in (("SNAPSHOT_DIR", self.cache_dir), ("SEED_DIR", self.seed_dir),
                            ("MIRROR_URL", ""), ("SNAPSHOT_MAX_AGE_HOURS", -1)):
            patcher = patch.object(market_data, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        market_data._mirror_misses.clear()
        market_data._live_requests.clear()
        market_data._index_cache.update(at=float("-inf"), entries=None)
        # No test may reach the exchange; those about it replace this with canned answers.
        patcher = patch.object(market_data, "_twse_get", side_effect=ConnectionError("no network in tests"))
        self.twse_get = patcher.start()
        self.addCleanup(patcher.stop)
        market_data._twse_state["dividends"].clear()


class MarketDataTests(IsolatedSnapshots):
    def test_same_month_different_trading_days(self):
        a = monthly_data(history(['2024-01-10', '2024-02-15', '2024-03-11']), 10)
        b = monthly_data(history(['2024-01-10', '2024-02-16', '2024-03-12']), 10)
        self.assertEqual(len(align_months(a, b)), 2)
        self.assertEqual(align_months(a, b).index[0], pd.Timestamp('2024-02-01'))

    def test_missing_month_rejected(self):
        with self.assertRaises(ValueError):
            monthly_data(history(['2024-01-10', '2024-03-10']), 10)

    def test_dividends_and_price_returns(self):
        df = history(['2024-01-10', '2024-02-05', '2024-02-10'], [100, 108, 110])
        df.loc['2024-02-05', 'Dividends'] = 2
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

    @patch('market_data.yf.Ticker')
    def test_malformed_symbol_never_requests_network(self, ticker):
        for symbol in ('../etc/passwd', 'A B', 'x' * 21, '0050.TW;rm'):
            with self.assertRaises(ValueError, msg=symbol):
                load_history(symbol)
        ticker.assert_not_called()

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_symbols_not_restricted_to_specific_etfs(self, ticker, sleep):
        ticker.return_value.history.return_value = history(['2024-01-10', '2024-02-10'])
        for symbol in [' spy ', 'brk-b', '00679b.two', '0700.hk', '^gspc', 'btc-usd']:
            load_history(symbol)
            ticker.assert_called_with(symbol.strip().upper())


class DividendTimingTests(unittest.TestCase):
    def setUp(self):
        self.df = history(['2024-01-10', '2024-01-25', '2024-02-12', '2024-02-20', '2024-03-11', '2024-03-20'])

    def result(self):
        return monthly_data(self.df, 10)['Monthly_Div'].tolist()  # rows: February, March

    def test_ex_date_after_the_monthly_quote_counts_in_the_next_period(self):
        # The price sampled on 12 Feb has not gone ex yet; the drop lands in the March return.
        self.df.loc['2024-02-20', 'Dividends'] = 3
        self.assertEqual(self.result(), [0, 3])

    def test_ex_date_before_the_monthly_quote_counts_in_that_period(self):
        self.df.loc['2024-01-25', 'Dividends'] = 3
        self.assertEqual(self.result(), [3, 0])

    def test_ex_date_on_the_quote_day_counts_in_that_period(self):
        self.df.loc['2024-02-12', 'Dividends'] = 3
        self.assertEqual(self.result(), [3, 0])

    def test_dividend_after_the_latest_quote_waits_for_the_next_month(self):
        self.df.loc['2024-03-20', 'Dividends'] = 3
        self.assertEqual(self.result(), [0, 0])

    def test_yield_uses_the_previous_quote(self):
        df = history(['2024-01-10', '2024-01-25', '2024-02-12'], [50, 55, 60])
        df.loc['2024-01-25', 'Dividends'] = 1
        self.assertAlmostEqual(monthly_data(df, 10)['Div_Yield'].iloc[0], 1 / 50)


class SplitRepairTests(unittest.TestCase):
    def test_unadjusted_forward_split_is_removed(self):
        raw = split_at(daily('2019-01-01', '2021-12-31'), '2020-06-01', 4)
        self.assertLess(monthly_data(raw, 10, repair=False)['Price_Return'].min(), -0.7)
        fixed = monthly_data(raw, 10)
        self.assertGreater(fixed['Price_Return'].min(), -0.1)
        self.assertEqual(len(fixed.attrs['repairs']), 1)
        self.assertIn('1 股拆成 4 股', fixed.attrs['repairs'][0])
        self.assertEqual(fixed.attrs['anomalies'], [])

    def test_repaired_series_matches_the_true_one(self):
        truth = daily('2019-01-01', '2021-12-31')
        fixed, _ = repair_history(split_at(truth, '2020-06-01', 22))
        np.testing.assert_allclose(fixed['Close'], truth['Close'])

    def test_unadjusted_reverse_split_is_removed(self):
        truth = daily('2019-01-01', '2021-12-31')
        fixed, notes = repair_history(split_at(truth, '2020-06-01', 1 / 7))
        np.testing.assert_allclose(fixed['Close'], truth['Close'])
        self.assertIn('7 股併成 1 股', notes[0])

    def test_two_seams_are_both_removed(self):
        truth = daily('2015-01-01', '2021-12-31')
        raw = split_at(split_at(truth, '2020-06-01', 4), '2017-03-01', 5)
        fixed, notes = repair_history(raw)
        np.testing.assert_allclose(fixed['Close'], truth['Close'])
        self.assertEqual(len(notes), 2)

    def assert_dividends_restored(self, seam, ratio, payouts, stale_years, expected_note):
        """`payouts` maps year -> true dividend; those in `stale_years` reach us in pre-split units."""
        truth = daily('2010-01-01', '2020-12-31', price=20.0)
        raw = split_at(truth, seam, ratio)
        for year, amount in payouts.items():
            pay(truth, f'{year}-05-10', amount)
            pay(raw, f'{year}-05-10', amount * (ratio if year in stale_years else 1))
        fixed, notes = repair_history(raw)
        np.testing.assert_allclose(fixed['Close'], truth['Close'])
        np.testing.assert_allclose(fixed['Dividends'], truth['Dividends'])
        if expected_note:
            self.assertIn(expected_note, notes[0])
        else:
            self.assertNotIn('配息', notes[0])

    def test_stale_dividends_on_either_side_of_the_seam_are_rescaled(self):
        # Prices adjusted back to 2014, dividends only back to 2015: the 2014 payout is four times too big.
        self.assert_dividends_restored('2014-01-02', 4, {y: 0.5 for y in range(2010, 2021)},
                                       stale_years=range(2010, 2015), expected_note='5 筆配息')

    def test_dividends_the_source_already_adjusted_are_left_alone(self):
        # Prices never adjusted, dividends adjusted back to 2013: only the 2011 payout is stale.
        self.assert_dividends_restored('2019-06-03', 7, {y: 0.5 for y in (2011, *range(2013, 2021))},
                                       stale_years=(2011,), expected_note='1 筆配息')

    def test_uneven_payouts_do_not_confuse_the_cut_off(self):
        payouts = {2011: 0.5, 2012: 0.3, 2013: 0.6, 2014: 0.7, 2015: 0.9, 2016: 0.3, 2017: 0.6, 2018: 0.5,
                   2019: 0.15, 2020: 0.6}
        self.assert_dividends_restored('2016-03-01', 4, payouts, stale_years=(2011, 2012, 2013),
                                       expected_note='3 筆配息')

    def test_consistent_dividends_are_not_touched(self):
        self.assert_dividends_restored('2019-06-03', 7, {y: 0.5 for y in range(2011, 2021)},
                                       stale_years=(), expected_note=None)

    def test_dividends_in_old_units_throughout_are_rescaled_when_only_that_is_believable(self):
        # No payout since the split to compare with: 30% a year is not believable, 3% is.
        self.assert_dividends_restored('2020-06-01', 10, {y: 0.6 for y in range(2015, 2020)},
                                       stale_years=range(2015, 2020), expected_note='5 筆配息')

    def test_ticker_with_reported_splits_is_not_second_guessed(self):
        # The source knows this ticker's splits, so a halving is taken as a real crash.
        raw = split_at(daily('2019-01-01', '2021-12-31'), '2020-06-01', 2)
        raw['Stock Splits'] = 0.0
        raw.iloc[30, raw.columns.get_loc('Stock Splits')] = 2.0
        fixed, notes = repair_history(raw)
        self.assertEqual(notes, [])
        pd.testing.assert_series_equal(fixed['Close'], raw['Close'])
        self.assertEqual(len(find_anomalies(fixed)), 1)

    def test_jump_that_is_not_a_whole_ratio_is_reported_not_repaired(self):
        raw = split_at(daily('2019-01-01', '2021-12-31'), '2020-06-01', 2.5)
        fixed = monthly_data(raw, 10)
        self.assertEqual(fixed.attrs['repairs'], [])
        self.assertEqual(len(fixed.attrs['anomalies']), 1)
        self.assertIn('2020-06-01 單日 -60', fixed.attrs['anomalies'][0])

    def test_known_bad_day_is_flattened_for_the_listed_ticker_only(self):
        truth = daily('2015-01-01', '2016-12-31')
        raw = split_at(truth, '2015-08-24', 1.4)
        fixed, notes = repair_history(raw, '00631L.TW')
        pos = fixed.index.get_loc(pd.Timestamp('2015-08-24'))
        self.assertAlmostEqual(fixed['Close'].iloc[pos] / fixed['Close'].iloc[pos - 1], 1.0)
        self.assertEqual(len(notes), 1)
        untouched, notes = repair_history(raw, '0056.TW')
        self.assertEqual(notes, [])
        pd.testing.assert_series_equal(untouched['Close'], raw['Close'])

    def test_ticker_is_read_from_the_downloaded_frame(self):
        raw = split_at(daily('2015-01-01', '2016-12-31'), '2015-08-24', 1.4)
        raw.attrs['ticker'] = '00631L.TW'
        self.assertEqual(len(monthly_data(raw, 10).attrs['repairs']), 1)


class AnomalyTests(unittest.TestCase):
    def test_quiet_history_has_none(self):
        self.assertEqual(find_anomalies(daily('2019-01-01', '2021-12-31')), [])

    def test_threshold_scales_with_the_assets_own_volatility(self):
        calm = daily('2019-01-01', '2021-12-31', vol=0.004)
        wild = daily('2019-01-01', '2021-12-31', vol=0.035)
        for df in (calm, wild):
            df.iloc[300:, df.columns.get_loc('Close')] *= 0.70
        self.assertEqual(len(find_anomalies(calm)), 1)
        self.assertEqual(find_anomalies(wild), [])

    def test_only_the_most_extreme_are_listed(self):
        df = daily('2015-01-01', '2021-12-31')
        for k in range(8):
            df.iloc[100 * (k + 1):, df.columns.get_loc('Close')] *= 0.6
        notes = find_anomalies(df, limit=3)
        self.assertEqual(len(notes), 4)
        self.assertEqual(notes[-1], '另有 5 筆')

    def test_long_dividend_free_start_of_a_regular_payer_is_reported(self):
        df = daily('2010-01-01', '2020-12-31')
        for year in range(2014, 2021):
            pay(df, f'{year}-06-20', 2.0)
        notes = monthly_data(df, 10).attrs['anomalies']
        self.assertEqual(len(notes), 1)
        self.assertIn('2010-02 至 2014-06 沒有任何配息紀錄', notes[0])

    def test_new_fund_and_non_payer_are_not_reported_for_missing_dividends(self):
        new_fund = daily('2018-01-01', '2020-12-31')
        for day in ('2018-11-20', '2019-05-20', '2019-11-20', '2020-05-20'):
            pay(new_fund, day, 1.0)
        self.assertEqual(monthly_data(new_fund, 10).attrs['anomalies'], [])
        self.assertEqual(monthly_data(daily('2010-01-01', '2020-12-31'), 10).attrs['anomalies'], [])

    def test_implausible_dividend_is_reported(self):
        df = daily('2019-01-01', '2020-12-31')
        pay(df, '2019-06-03', 30.0)
        notes = monthly_data(df, 10).attrs['anomalies']
        self.assertEqual(len(notes), 1)
        self.assertIn('2019-06 配息相當於股價的', notes[0])


class SnapshotTests(IsolatedSnapshots):
    def fetch(self, ticker_mock, responses):
        ticker_mock.return_value.history.side_effect = responses
        return load_history('0056.TW')

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_last_good_download_is_used_when_the_source_fails(self, ticker, sleep):
        good = daily('2023-01-01', '2023-06-30')
        pay(good, '2023-03-15', 1.2)
        good.index = good.index.tz_localize('Asia/Taipei')
        live = self.fetch(ticker, [good])
        self.assertEqual(live.attrs['data_source'], 'live')

        stale = self.fetch(ticker, [TimeoutError()] * 3)     # this suite treats every stored copy as old
        self.assertEqual(stale.attrs['data_source'], 'snapshot')
        self.assertEqual(stale.attrs['fetched_at'], live.attrs['fetched_at'])
        np.testing.assert_allclose(stale['Close'], good['Close'])
        np.testing.assert_allclose(stale['Dividends'], good['Dividends'])
        pd.testing.assert_frame_equal(monthly_data(stale, 10)[['Close', 'Monthly_Div']],
                                      monthly_data(good, 10)[['Close', 'Monthly_Div']])

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_no_snapshot_means_the_failure_is_reported(self, ticker, sleep):
        with self.assertRaises(ValueError):
            self.fetch(ticker, [TimeoutError()] * 3)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_shipped_snapshot_is_the_last_resort(self, ticker, sleep):
        seed = daily('2022-01-01', '2022-06-30')
        seed.attrs['fetched_at'] = '2022-07-01T00:00:00Z'
        save_snapshot(seed, '0056.TW', self.seed_dir)
        result = self.fetch(ticker, [TimeoutError()] * 3)
        self.assertEqual(result.attrs['fetched_at'], '2022-07-01T00:00:00Z')
        self.assertEqual(len(result), len(seed))

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_newer_local_snapshot_wins_over_the_shipped_one(self, ticker, sleep):
        save_snapshot(daily('2022-01-01', '2022-06-30'), '0056.TW', self.seed_dir)
        fresh = daily('2023-01-01', '2023-06-30')
        self.fetch(ticker, [fresh])
        self.assertEqual(len(self.fetch(ticker, [TimeoutError()] * 3)), len(fresh))

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_corrupt_snapshot_is_ignored(self, ticker, sleep):
        os.makedirs(self.cache_dir)
        with open(os.path.join(self.cache_dir, '0056.TW.csv'), 'w') as fh:
            fh.write("# fetched_at=x\nDate,Close,Dividends\n2023-01-02,-5,0\n")
        with self.assertRaises(ValueError):
            self.fetch(ticker, [TimeoutError()] * 3)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_unwritable_snapshot_folder_does_not_break_a_download(self, ticker, sleep):
        with open(self.cache_dir, 'w') as fh:   # a file where the folder should be
            fh.write('x')
        self.assertEqual(self.fetch(ticker, [daily('2023-01-01', '2023-03-31')]).attrs['data_source'], 'live')

    def test_split_records_survive_the_round_trip(self):
        df = daily('2023-01-01', '2023-03-31')
        df['Stock Splits'] = 0.0
        df.iloc[5, df.columns.get_loc('Stock Splits')] = 2.0
        save_snapshot(df, 'AAPL')
        self.assertEqual(read_snapshot('AAPL')['Stock Splits'].sum(), 2.0)

    def test_snapshot_path_cannot_leave_the_folder(self):
        with self.assertRaises(ValueError):
            save_snapshot(daily('2023-01-01', '2023-03-31'), '../escape')
        with self.assertRaises(ValueError):
            read_snapshot('../escape')


def copy_fetched(hours_ago, end='2023-06-30', ticker='0056.TW'):
    """A history that says it was downloaded `hours_ago` hours ago."""
    df = daily('2023-01-02', end)
    stamp = pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=hours_ago)
    df.attrs.update(ticker=ticker, fetched_at=stamp.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return df


def as_csv(df):
    with tempfile.TemporaryDirectory() as folder:
        with open(save_snapshot(df, df.attrs['ticker'], folder), encoding="utf-8") as fh:
            return fh.read()


class FreshCopyTests(IsolatedSnapshots):
    """Stored copies up to 36 hours old are used in place of the live source."""

    def setUp(self):
        super().setUp()
        self.mirror = {}                                   # ticker -> csv text published on the mirror
        for target, value in (("SNAPSHOT_MAX_AGE_HOURS", 36), ("MIRROR_URL", "https://mirror.test/data")):
            patcher = patch.object(market_data, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(market_data, "_http_get_text", side_effect=self.serve)
        self.http = patcher.start()
        self.addCleanup(patcher.stop)
        for target in ("market_data.time.sleep", "market_data.yf.Ticker"):
            patcher = patch(target)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
        self.yahoo = mock.return_value.history
        self.yahoo.return_value = daily('2023-01-02', '2023-12-29')

    def serve(self, url, timeout=8):
        self.assertTrue(url.startswith("https://mirror.test/data/"))
        name = url.rsplit("/", 1)[1]
        if name not in self.mirror:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return self.mirror[name]

    def test_recent_local_copy_needs_no_network_at_all(self):
        save_snapshot(copy_fetched(2), '0056.TW')
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'cache')
        self.yahoo.assert_not_called()
        self.http.assert_not_called()

    def test_recent_mirror_copy_replaces_an_old_local_one(self):
        save_snapshot(copy_fetched(100, end='2023-05-31'), '0056.TW')
        self.mirror['0056.TW.csv'] = as_csv(copy_fetched(5))
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'mirror')
        self.assertEqual(out.index.max(), pd.Timestamp('2023-06-30'))
        self.yahoo.assert_not_called()
        again = load_history('0056.TW')                     # now kept locally: no second download
        self.assertEqual(again.attrs['data_source'], 'cache')
        self.assertEqual(self.http.call_count, 1)

    def test_old_mirror_copy_is_not_good_enough(self):
        self.mirror['0056.TW.csv'] = as_csv(copy_fetched(100))
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'live')
        self.assertEqual(out.index.max(), pd.Timestamp('2023-12-29'))
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'cache')

    def test_ticker_the_mirror_does_not_carry_is_asked_for_once_an_hour(self):
        self.assertIsNone(market_data.fetch_mirror('2330.TW'))
        self.assertIsNone(market_data.fetch_mirror('2330.TW'))
        self.assertEqual(self.http.call_count, 1)
        self.assertEqual(load_history('2330.TW').attrs['data_source'], 'live')

    def test_unusable_mirror_file_is_ignored(self):
        self.mirror['0056.TW.csv'] = "<html>Not what was asked for</html>"
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'live')

    def test_symbols_are_escaped_in_the_mirror_address(self):
        market_data.fetch_mirror('^GSPC')
        self.assertEqual(self.http.call_args.args[0], "https://mirror.test/data/%5EGSPC.csv")

    def test_mirror_can_be_switched_off(self):
        with patch.object(market_data, "MIRROR_URL", ""):
            self.assertEqual(load_history('0056.TW').attrs['data_source'], 'live')
        self.http.assert_not_called()

    def test_reload_request_goes_to_the_live_source_once(self):
        save_snapshot(copy_fetched(2), '0056.TW')
        self.mirror['0056.TW.csv'] = as_csv(copy_fetched(1))
        market_data.request_live('0056.tw')
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'live')
        self.http.assert_not_called()
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'cache')
        self.assertEqual(self.yahoo.call_count, 1)

    def test_when_the_live_source_fails_the_newest_copy_is_used_and_flagged(self):
        self.yahoo.side_effect = TimeoutError()
        save_snapshot(copy_fetched(200, end='2023-03-31'), '0056.TW')
        self.mirror['0056.TW.csv'] = as_csv(copy_fetched(60, end='2023-06-30'))
        save_snapshot(copy_fetched(120, end='2023-05-31'), '0056.TW', self.seed_dir)
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'snapshot')
        self.assertEqual(out.index.max(), pd.Timestamp('2023-06-30'))

    def test_failed_reload_still_falls_back_to_what_is_stored(self):
        self.yahoo.side_effect = TimeoutError()
        save_snapshot(copy_fetched(2), '0056.TW')
        market_data.request_live('0056.TW')
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'snapshot')

    def test_copy_without_a_download_time_is_never_treated_as_recent(self):
        os.makedirs(self.cache_dir)
        with open(os.path.join(self.cache_dir, '0056.TW.csv'), 'w') as fh:
            fh.write("Date,Close,Dividends\n2023-01-02,10,0\n2023-01-03,11,0\n")
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'live')

    def test_refresh_writes_live_data_and_keeps_the_old_copy_of_a_ticker_that_failed(self):
        published = copy_fetched(30, end='2023-06-30', ticker='00878.TW')
        self.mirror['00878.TW.csv'] = as_csv(published)
        good = daily('2023-01-02', '2023-12-29')
        self.yahoo.side_effect = lambda **kwargs: good
        calls = {"n": 0}

        def flaky(symbol):
            ticker = unittest.mock.MagicMock()
            ticker.history.side_effect = (lambda **kw: good) if symbol == '0056.TW' else TimeoutError()
            calls["n"] += 1
            return ticker

        with patch('market_data.yf.Ticker', side_effect=flaky), tempfile.TemporaryDirectory() as out:
            live = market_data.refresh_snapshots(['0056.TW', '00878.TW', '9999.TW'], out)
            self.assertEqual(live, 1)
            self.assertEqual(sorted(os.listdir(out)), ['0056.TW.csv', '00878.TW.csv'])
            kept = market_data._stored(out, '00878.TW')
            self.assertEqual(kept.attrs['fetched_at'], published.attrs['fetched_at'])   # its age stays honest
            self.assertEqual(market_data._stored(out, '0056.TW').index.max(), pd.Timestamp('2023-12-29'))

    def test_refresh_reports_when_nothing_could_be_downloaded(self):
        self.yahoo.side_effect = TimeoutError()
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(market_data.refresh_snapshots(['0056.TW'], out), 0)
            self.assertEqual(os.listdir(out), [])


class WithoutLiveSourceTests(IsolatedSnapshots):
    """The in-browser build: no yfinance, so only stored copies and the mirror."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(market_data, "yf", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stored_copy_of_any_age_is_used(self):
        save_snapshot(copy_fetched(500), '0056.TW', self.seed_dir)
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'snapshot')
        self.assertFalse(market_data.live_source_available())

    def test_unknown_ticker_explains_what_is_available(self):
        # (falls back to the shipped files when the mirror's index cannot be read)
        save_snapshot(copy_fetched(500), '0056.TW', self.seed_dir)
        with patch.object(market_data, "_HERE", os.path.dirname(self.seed_dir)), \
                patch.object(market_data, "time") as clock:
            clock.monotonic.return_value = 0.0
            with self.assertRaises(ValueError) as ctx:
                load_history('2330.TW')
            clock.sleep.assert_not_called()                     # no pointless retries
        self.assertIn("單機版無法即時查詢行情，只能使用台灣上市的 ETF（目前 1 檔", str(ctx.exception))

    def test_reload_request_falls_back_to_stored_copies(self):
        save_snapshot(copy_fetched(500), '0056.TW', self.seed_dir)
        market_data.request_live('0056.TW')
        self.assertEqual(load_history('0056.TW').attrs['data_source'], 'snapshot')

    def test_available_tickers_combine_shipped_files_and_the_mirror_list(self):
        root = os.path.dirname(self.seed_dir)
        os.makedirs(os.path.join(root, "data"))
        with open(os.path.join(root, "data", "mirror_tickers.txt"), "w") as fh:
            fh.write("# list\n00878.TW\n0056.TW  # dup\n")
        save_snapshot(copy_fetched(1), '0050.TW', self.seed_dir)
        with patch.object(market_data, "_HERE", root):
            self.assertEqual(market_data.available_snapshots(), ['0050.TW', '0056.TW', '00878.TW'])

    def test_browser_uses_its_own_http_client(self):
        fake = unittest.mock.MagicMock()
        fake.http.open_url.return_value.read.return_value = "text"
        with patch.object(market_data, "IN_BROWSER", True), patch.dict(sys.modules, {"pyodide": fake, "pyodide.http": fake.http}):
            self.assertEqual(market_data._http_get_text("https://example.test/a.csv"), "text")
        fake.http.open_url.assert_called_once_with("https://example.test/a.csv")


LISTING_PAGE = """<html><body><table>
<tr><td>頁面編號</td><td>國際證券編碼</td><td>有價證券代號</td><td>有價證券名稱</td><td>市場別</td><td>有價證券別</td>
<td>產業別</td><td>公開發行/上市(櫃)/發行日</td><td>CFICode</td><td>備註</td></tr>
<tr><td>1</td><td>TW0000050004</td><td>0050</td><td>元大台灣50</td><td>上市</td><td>ETF</td><td></td><td>2003/06/30</td><td>CEOGEU</td><td></td></tr>
<tr><td>2</td><td>TW00000631L5</td><td>00631L</td><td>元大台灣50正2</td><td>上市</td><td>ETF</td><td></td><td>2014/10/31</td><td>CEOGLU</td><td></td></tr>
<tr><td>3</td><td>TW00000679B0</td><td>00679B</td><td>元大美債20年</td><td>上櫃</td><td>ETF</td><td></td><td>2017/01/17</td><td>CEOIBU</td><td></td></tr>
<tr><td>4</td><td>TW0002330008</td><td>2330</td><td>台積電</td><td>上市</td><td>股票</td><td>24</td><td>1994/09/05</td><td>ESVUFR</td><td></td></tr>
<tr><td>5</td><td>TW00000413A2</td><td>00413a</td><td>主動玉山&nbsp;關鍵科技</td><td>上市</td><td>ETF</td><td></td><td>2026/11/11</td><td>CEOJEU</td><td></td></tr>
</table></body></html>"""


class ListedEtfTests(IsolatedSnapshots):
    def test_listing_page_yields_listed_etfs_only(self):
        entries = market_data.parse_listed_etfs(LISTING_PAGE)
        self.assertEqual(entries, {
            "0050.TW": {"name": "元大台灣50", "listed": "2003-06-30"},
            "00631L.TW": {"name": "元大台灣50正2", "listed": "2014-10-31"},
            "00413A.TW": {"name": "主動玉山關鍵科技", "listed": "2026-11-11"},
        })

    def respond(self, body, encoding="cp950"):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = body.encode(encoding)
        return response

    def full_page(self, count=60):
        rows = "".join(f"<tr><td>{i}</td><td>X</td><td>{9000 + i}</td><td>ETF {i}</td><td>上市</td><td>ETF</td><td></td>"
                       f"<td>2020/01/01</td><td>CE</td><td></td></tr>" for i in range(count))
        return f"<table><tr><td>h</td></tr>{rows}</table>"

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_firewall_refusals_are_retried(self, urlopen, sleep):
        refusal = self.respond("<html>FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.</html>", "utf-8")
        urlopen.side_effect = [refusal, OSError("reset"), self.respond(self.full_page())]
        self.assertEqual(len(market_data.fetch_listed_etfs(attempts=5, pause=40)), 60)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [40, 40])

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_a_list_that_never_arrives_is_an_error(self, urlopen, sleep):
        urlopen.return_value = self.respond(self.full_page(count=3))   # far too short to be the real list
        with self.assertRaises(ConnectionError):
            market_data.fetch_listed_etfs(attempts=2, pause=1)
        self.assertEqual(urlopen.call_count, 2)

    def test_index_round_trip(self):
        entries = {"0056.TW": {"name": "元大高股息", "listed": "2007-12-26"}, "0050.TW": {"name": "元大台灣50", "listed": ""}}
        with tempfile.TemporaryDirectory() as folder:
            with open(market_data.write_index(entries, folder), encoding="utf-8") as fh:
                text = fh.read()
        self.assertTrue(text.startswith("ticker,name,listed\n0050.TW,"))
        self.assertEqual(market_data.parse_index(text), entries)
        with self.assertRaises(ValueError):
            market_data.parse_index("<html>Not Found</html>")

    def test_index_is_read_from_the_mirror_once_an_hour(self):
        text = "ticker,name,listed\n0056.TW,元大高股息,2007-12-26\n00878.TW,國泰永續高股息,2020-07-20\n"
        with patch.object(market_data, "MIRROR_URL", "https://mirror.test/data"), \
                patch.object(market_data, "_listed_extras", return_value=set()), \
                patch.object(market_data, "_http_get_text", return_value=text) as get:
            self.assertEqual(market_data.listing_info("0056.tw"), {"name": "元大高股息", "listed": "2007-12-26"})
            self.assertEqual(market_data.listing_info("2330.TW"), {})
            self.assertEqual(market_data.available_snapshots(), ["0056.TW", "00878.TW"])
        get.assert_called_once_with("https://mirror.test/data/index.csv")

    def test_unreadable_index_means_no_listing_information(self):
        with patch.object(market_data, "MIRROR_URL", "https://mirror.test/data"), \
                patch.object(market_data, "_http_get_text", side_effect=OSError("404")):
            self.assertEqual(market_data.mirror_index(), {})
            self.assertEqual(market_data.listing_info("0056.TW"), {})

    def test_universe_is_every_listed_etf_plus_the_extra_list(self):
        listed = market_data.parse_listed_etfs(LISTING_PAGE)
        with patch.object(market_data, "fetch_listed_etfs", return_value=dict(listed)):
            universe = market_data.mirror_universe(["0050.TW", "spy"])
        self.assertEqual(sorted(universe), ["00413A.TW", "0050.TW", "00631L.TW", "SPY"])
        self.assertEqual(universe["0050.TW"]["name"], "元大台灣50")       # the exchange's entry is kept
        self.assertEqual(universe["SPY"], {"name": "", "listed": ""})

    def test_universe_falls_back_to_the_published_index(self):
        previous = {"0056.TW": {"name": "元大高股息", "listed": "2007-12-26"}}
        with patch.object(market_data, "fetch_listed_etfs", side_effect=ConnectionError("refused")), \
                patch.object(market_data, "mirror_index", return_value=previous):
            self.assertEqual(sorted(market_data.mirror_universe(["0050.TW"])), ["0050.TW", "0056.TW"])


def roc(ts, style="/"):
    y, m, d = ts.year - 1911, ts.month, ts.day
    return f"{y}/{m:02d}/{d:02d}" if style == "/" else f"{y}年{m:02d}月{d:02d}日"


class ExchangeTopUpTests(IsolatedSnapshots):
    """Yahoo is down; the snapshot ends 2024-03-15 and today is 2024-05-09.

    The exchange serves data up to the previous day, 2024-05-08.
    """

    def setUp(self):
        super().setUp()
        self.truth = daily('2023-01-02', '2024-05-08', price=100.0)
        self.ex_date = pay(self.truth, '2024-04-18', 1.5)
        self.snapshot = self.truth[self.truth.index <= '2024-03-15'].copy()
        self.snapshot.attrs.update(ticker='0056.TW', data_source='snapshot', fetched_at='2024-03-15T10:00:00Z')
        patcher = patch.object(market_data, "_today", return_value=pd.Timestamp('2024-05-09'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []
        self.twse_get.side_effect = self.answer
        patcher = patch.object(market_data, "TWSE_TOP_UP", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.events = [(self.ex_date, '0056', '1.500000', '息'), (self.ex_date, '2330', '4.000000', '息')]
        self.price_shift = 1.0

    def answer(self, path, **params):
        self.calls.append((path, params))
        if path == "afterTrading/STOCK_DAY":
            self.assertEqual(params["stockNo"], "0056")
            month = self.truth[self.truth.index.to_period('M') == pd.Period(params["date"][:6], 'M')]
            rows = [[roc(ts), "1,234", "5,678", "0", "0", "0", f"{close * self.price_shift:,.2f}", "+0.1", "9", ""]
                    for ts, close in month['Close'].items()]
            rows.insert(1, ["113/01/01", "0", "0", "--", "--", "--", "--", "0", "0", ""])   # a no-trade day
            if month.index.max() == self.truth.index.max():                              # today's close is already posted
                rows.append(["113/05/09", "1", "1", "0", "0", "0", "55.55", "0", "1", ""])
            return {"stat": "OK", "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價",
                                             "漲跌價差", "成交筆數", "註記"], "data": rows}
        month = pd.Period(params["startDate"][:6], 'M')
        self.assertEqual(params["endDate"], min(month.end_time.normalize(), pd.Timestamp('2024-05-08')).strftime("%Y%m%d"))
        self.assertLess(params["endDate"], "20240509", "the exchange refuses a range that reaches today")
        rows = [[roc(d, "年"), code, "名稱", "0", "0", value, kind]
                for d, code, value, kind in self.events if d.to_period('M') == month]
        return {"stat": "OK", "fields": ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價",
                                         "權值+息值", "權/息"], "data": rows}

    def test_snapshot_is_extended_with_prices_and_dividends(self):
        out = market_data.top_up_from_twse(self.snapshot, '0056.TW')
        self.assertEqual(out.index.max(), pd.Timestamp('2024-05-08'))
        self.assertEqual(len(out), len(self.truth))
        np.testing.assert_allclose(out['Close'], self.truth['Close'], atol=0.006)   # the exchange quotes two decimals
        np.testing.assert_allclose(out['Dividends'], self.truth['Dividends'])
        self.assertEqual((out.attrs['data_source'], out.attrs['topped_up_to'], out.attrs['fetched_at']),
                         ('snapshot+twse', '2024-05-08', '2024-03-15T10:00:00Z'))
        # one price request per month in the gap, one distribution request per month, nothing else
        self.assertEqual([c[0] for c in self.calls].count("afterTrading/STOCK_DAY"), 3)
        self.assertEqual([c[0] for c in self.calls].count("exRight/TWT49U"), 3)

    def test_monthly_series_matches_a_live_download(self):
        topped = monthly_data(market_data.top_up_from_twse(self.snapshot, '0056.TW'), 10)
        live = monthly_data(self.truth, 10)
        np.testing.assert_allclose(topped['Price_Return'], live['Price_Return'], atol=2e-4)
        np.testing.assert_allclose(topped['Monthly_Div'], live['Monthly_Div'])
        self.assertEqual(topped.attrs['topped_up_to'], '2024-05-08')

    def test_distribution_table_is_fetched_once_for_several_tickers(self):
        market_data.top_up_from_twse(self.snapshot, '0056.TW')
        before = [c[0] for c in self.calls].count("exRight/TWT49U")
        market_data.top_up_from_twse(self.snapshot, '0056.TW')
        self.assertEqual([c[0] for c in self.calls].count("exRight/TWT49U"), before)

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_load_history_tops_up_when_the_live_source_is_down(self, ticker, sleep):
        save_snapshot(self.snapshot, '0056.TW')
        ticker.return_value.history.side_effect = TimeoutError()
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'snapshot+twse')
        self.assertEqual(out.index.max(), pd.Timestamp('2024-05-08'))

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_blocked_exchange_leaves_the_plain_snapshot(self, ticker, sleep):
        save_snapshot(self.snapshot, '0056.TW')
        ticker.return_value.history.side_effect = TimeoutError()
        self.twse_get.side_effect = [self.answer("afterTrading/STOCK_DAY", date="20240301", stockNo="0056"),
                                     ConnectionError("HTTP 307")]
        out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'snapshot')
        self.assertEqual(out.index.max(), pd.Timestamp('2024-03-15'))

    @patch('market_data.time.sleep')
    @patch('market_data.yf.Ticker')
    def test_exchange_is_not_contacted_unless_switched_on(self, ticker, sleep):
        save_snapshot(self.snapshot, '0056.TW')
        ticker.return_value.history.side_effect = TimeoutError()
        with patch.object(market_data, "TWSE_TOP_UP", False):
            out = load_history('0056.TW')
        self.assertEqual(out.attrs['data_source'], 'snapshot')
        self.assertEqual(self.calls, [])

    def test_disagreement_on_the_shared_day_is_refused(self):
        self.price_shift = 0.25    # the exchange is on a different share basis than the snapshot
        with self.assertRaises(ValueError):
            market_data.top_up_from_twse(self.snapshot, '0056.TW')

    def test_rights_issue_in_the_gap_is_refused(self):
        self.events.append((pd.Timestamp('2024-04-25'), '0056', '3.2', '權'))
        with self.assertRaises(ValueError):
            market_data.top_up_from_twse(self.snapshot, '0056.TW')

    def test_nothing_is_requested_when_it_cannot_help(self):
        cases = {
            'other exchange': ('0056.TWO', self.snapshot),
            'foreign ticker': ('SPY', self.snapshot),
            'snapshot already fresh': ('0056.TW', self.truth[self.truth.index <= '2024-05-06']),
            'snapshot from yesterday': ('0056.TW', self.truth),
            'snapshot too old': ('0056.TW', self.truth[self.truth.index <= '2024-01-15']),
        }
        for name, (symbol, snapshot) in cases.items():
            with self.subTest(name):
                self.assertIs(market_data.top_up_from_twse(snapshot, symbol), snapshot)
        self.assertEqual(self.calls, [])

    def test_republic_calendar_dates(self):
        self.assertEqual(market_data._roc_date('114/06/02'), pd.Timestamp('2025-06-02'))
        self.assertEqual(market_data._roc_date('101年10月24日'), pd.Timestamp('2012-10-24'))


class ExchangeRequestTests(unittest.TestCase):
    def setUp(self):
        market_data._twse_state["last_call"] = float("-inf")
        self.addCleanup(market_data._twse_state.__setitem__, "last_call", float("-inf"))

    def respond(self, body):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = body.encode("utf-8")
        return response

    @patch('market_data.time.sleep')
    @patch('market_data.time.monotonic')
    @patch('market_data.urllib.request.urlopen')
    def test_requests_are_spaced_out(self, urlopen, monotonic, sleep):
        urlopen.return_value = self.respond('{"stat": "OK", "fields": [], "data": []}')
        monotonic.side_effect = [100.0, 100.5, 103.0, 103.2]   # check, stamp, check, stamp
        market_data._twse_get("afterTrading/STOCK_DAY", date="20240301", stockNo="0056")
        sleep.assert_not_called()
        market_data._twse_get("afterTrading/STOCK_DAY", date="20240401", stockNo="0056")
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 100.5 + market_data._TWSE_INTERVAL - 103.0)
        url = urlopen.call_args.args[0].full_url
        self.assertTrue(url.startswith("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?"))
        self.assertIn("stockNo=0056", url)

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_no_data_is_an_empty_answer_but_other_statuses_fail(self, urlopen, sleep):
        urlopen.return_value = self.respond('{"stat": "很抱歉，沒有符合條件的資料!"}')
        self.assertEqual(market_data._twse_get("exRight/TWT49U", startDate="20240301", endDate="20240331")["data"], [])
        urlopen.return_value = self.respond('{"stat": "查詢日期大於今日，請重新查詢!"}')
        with self.assertRaises(ValueError):
            market_data._twse_get("exRight/TWT49U", startDate="20990301", endDate="20990331")

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_firewall_refusal_is_retried_then_reported(self, urlopen, sleep):
        urlopen.return_value = self.respond('<html>FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.</html>')
        with self.assertRaises(ConnectionError):
            market_data._twse_get("afterTrading/STOCK_DAY", date="20240301", stockNo="0056")
        self.assertEqual(urlopen.call_count, market_data._TWSE_ATTEMPTS)
        self.assertEqual(sleep.call_count, market_data._TWSE_ATTEMPTS - 1)   # paused before every retry

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_request_succeeds_after_a_refusal(self, urlopen, sleep):
        refused = urllib.error.HTTPError("https://www.twse.com.tw", 307, "Temporary Redirect", None, None)
        urlopen.side_effect = [refused, self.respond('{"stat": "OK", "fields": ["日期"], "data": [["113/03/01"]]}')]
        self.assertEqual(market_data._twse_get("afterTrading/STOCK_DAY", date="20240301", stockNo="0056")["data"],
                         [["113/03/01"]])
        self.assertEqual(urlopen.call_count, 2)

    @patch('market_data.time.sleep')
    @patch('market_data.urllib.request.urlopen')
    def test_error_status_from_the_exchange_is_not_retried(self, urlopen, sleep):
        urlopen.return_value = self.respond('{"stat": "查詢日期大於今日，請重新查詢!"}')
        with self.assertRaises(ValueError):
            market_data._twse_get("exRight/TWT49U", startDate="20990301", endDate="20990331")
        self.assertEqual(urlopen.call_count, 1)


def monthly(start, months, seed, ticker, dividend=0.0):
    rng = np.random.RandomState(seed)
    days = pd.date_range(start, periods=months + 1, freq='MS') + pd.Timedelta(days=9)
    df = pd.DataFrame({'Close': 50 * np.cumprod(1 + rng.normal(0.005, 0.04, months + 1)),
                       'Dividends': dividend}, index=days)
    df.attrs['ticker'] = ticker
    return monthly_data(df, 10)


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.asset = monthly('2020-01-01', 24, 1, 'NEW', dividend=0.3)     # rows 2020-02 .. 2022-01
        self.proxy = monthly('2012-01-01', 130, 2, 'OLD', dividend=0.2)    # rows 2012-02 .. 2022-11

    def test_earlier_months_take_the_proxys_returns_and_yields(self):
        out = backfill_with_proxy(self.asset, self.proxy)
        self.assertEqual(out.index[0], self.proxy.index[0])
        self.assertEqual(out.index[-1], self.asset.index[-1])
        early = out[out['Synthetic']]
        self.assertEqual(len(early), 96)
        self.assertEqual(early.index[-1], self.asset.index[0] - 1)
        pd.testing.assert_series_equal(early['Price_Return'], self.proxy.loc[early.index, 'Price_Return'])
        pd.testing.assert_series_equal(early['Div_Yield'], self.proxy.loc[early.index, 'Div_Yield'])

    def test_real_months_are_unchanged(self):
        out = backfill_with_proxy(self.asset, self.proxy)
        real = out[~out['Synthetic']]
        pd.testing.assert_frame_equal(real[['Close', 'Price_Return', 'Div_Yield', 'Monthly_Div']],
                                      self.asset[['Close', 'Price_Return', 'Div_Yield', 'Monthly_Div']])

    def test_prices_and_dividends_stay_internally_consistent(self):
        out = backfill_with_proxy(self.asset, self.proxy)
        np.testing.assert_allclose(out['Close'].pct_change().iloc[1:], out['Price_Return'].iloc[1:])
        np.testing.assert_allclose((out['Monthly_Div'] / out['Close'].shift(1)).iloc[1:], out['Div_Yield'].iloc[1:])
        self.assertTrue((out['Close'] > 0).all())

    def test_summary_describes_what_was_filled(self):
        info = backfill_with_proxy(self.asset, self.proxy).attrs['backfill']
        self.assertEqual((info['proxy'], info['months'], info['start'], info['end']), ('OLD', 96, '2012-02', '2020-01'))
        self.assertEqual(info['overlap_months'], 24)
        self.assertTrue(-1 <= info['correlation'] <= 1)

    def test_just_listed_asset_with_one_month_of_prices(self):
        days = pd.bdate_range('2022-01-11', '2022-01-20')
        raw = pd.DataFrame({'Close': np.linspace(10, 11, len(days)), 'Dividends': 0.0}, index=days)
        raw.attrs['ticker'] = 'NEW.TW'
        with self.assertRaises(ValueError) as ctx:
            monthly_data(raw, 10)
        self.assertIn("NEW.TW 的第一筆價格在 2022-01-11", str(ctx.exception))
        self.assertIn("最早要等到 2022-02 有了第二筆月價才能進場", str(ctx.exception))

        short = monthly_data(raw, 10, allow_short=True)
        self.assertTrue(short.empty)
        self.assertEqual((short.attrs['base_month'], short.attrs['base_close']), ('2022-01', 10.0))

        out = backfill_with_proxy(short, self.proxy)
        self.assertTrue(out['Synthetic'].all())
        self.assertEqual(out.index[-1], pd.Period('2022-01', freq='M'))      # the asset's own price month
        self.assertAlmostEqual(out['Close'].iloc[-1], 10.0)                   # anchored on its real price
        pd.testing.assert_series_equal(out['Price_Return'], self.proxy.loc[out.index, 'Price_Return'])
        self.assertEqual(out.attrs['backfill']['months'], len(out))
        merged = align_months(out)
        self.assertEqual(len(merged), len(out))

    def test_proxy_that_is_no_older_changes_nothing(self):
        out = backfill_with_proxy(self.proxy, self.asset)
        self.assertFalse(out['Synthetic'].any())
        self.assertNotIn('backfill', out.attrs)
        self.assertEqual(len(out), len(self.proxy))

    def test_proxy_ending_before_the_asset_starts_is_not_used(self):
        gap = self.proxy[self.proxy.index < '2019-06']
        out = backfill_with_proxy(self.asset, gap)
        self.assertFalse(out['Synthetic'].any())

    def test_backfilled_months_flow_through_alignment(self):
        merged = align_months(backfill_with_proxy(self.asset, self.proxy))
        self.assertEqual(int(merged['Synthetic_A'].sum()), 96)
        self.assertEqual(len(merged), 120)


class AlignmentTests(unittest.TestCase):
    def test_months_before_the_second_asset_are_kept_with_it_empty(self):
        a = monthly('2015-01-01', 60, 1, 'A')
        b = monthly('2018-01-01', 24, 2, 'B')
        merged = align_months(a, b)
        self.assertEqual(merged.index[0], pd.Timestamp('2015-02-01'))
        self.assertEqual(int(merged['Price_Return_B'].isna().sum()), 36)
        self.assertFalse(merged['Price_Return_A'].isna().any())
        self.assertFalse(merged['Synthetic_A'].any())

    def test_range_ends_where_either_asset_ends(self):
        a = monthly('2015-01-01', 60, 1, 'A')
        b = monthly('2014-01-01', 40, 2, 'B')
        merged = align_months(a, b)
        self.assertEqual(merged.index[-1], pd.Timestamp('2017-05-01'))
        self.assertFalse(merged['Price_Return_B'].isna().any())

    def test_single_asset_gets_the_synthetic_flag_too(self):
        self.assertFalse(align_months(monthly('2015-01-01', 12, 1, 'A'))['Synthetic_A'].any())


if __name__ == '__main__':
    unittest.main()
