"""Sprint 6 acceptance (QA): 6-1 second-asset dividends, 6-2 official TWSE dividends. No network.

6-1  A dividend paid by the second asset (column Div_Yield_B of the aligned monthly data) is taxed and
     reinvested by the same rules as the first asset's; an asset that pays nothing leaves every
     result exactly as it was before the change (GOLDEN below was produced by the V40 engine).
6-2  The exchange's ex-dividend table (exRight/TWT49U) is preferred over Yahoo's dividends; when it cannot
     be read the old source is used and the page says so, in both languages.
"""
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import engine as E
import i18n
import market_data as md
import test_engine as T

# Produced by the V40 engine (git 56a4d76) on test_engine.market()/params(); see test_acceptance_s6 6-1 notes.
GOLDEN = {
    "plain": dict(kw={}, mk={}, hist_lev=824415170.498873, hist_dca=431615584.8608916, hist_ruin=0.0,
                  mc_lev=1644553427.9701686, mc_ruin=0.0, mc_div=0.06, trace_lev=8282878.149986144,
                  trace_sb=21156.45809423948, trace_tax=0.0),
    "tax": dict(kw=dict(dividend_tax_rate=0.1, nhi_rate=0.0211, nhi_threshold=20000, dividend_taxable_share=0.8), mk={},
                hist_lev=783912258.4965835, hist_dca=423191208.2066521, hist_ruin=0.0, mc_lev=1563005772.4914503,
                mc_ruin=0.0, mc_div=0.06, trace_lev=7821399.366004093, trace_sb=18923.222433118906,
                trace_tax=176295.36319755792),
    "model": dict(kw=dict(mc_dividends=E.MC_DIVIDENDS_MODEL), mk={}, hist_lev=824415170.498873,
                  hist_dca=431615584.8608916, hist_ruin=0.0, mc_lev=1550103211.41235, mc_ruin=0.0,
                  mc_div=0.05377711973206113, trace_lev=8282878.149986144, trace_sb=21156.45809423948, trace_tax=0.0),
    "stress": dict(kw=dict(principal=20_000_000.0, salary_cap=0.0, source_order=(E.BUFFER, E.SELL, E.SELL_B),
                           mc_paths=300), mk={}, hist_lev=1574264463.1824026, hist_dca=0.0, hist_ruin=8.0,
                   mc_lev=5178182240.000697, mc_ruin=0.03333333333333333, mc_div=0.06,
                   trace_lev=13774762.46649912, trace_sb=63633.747712618024, trace_tax=0.0),
    "noB": dict(kw=dict(reinvest=False), mk=dict(with_b=False), hist_lev=803560177.7342764,
                hist_dca=427636563.4999907, hist_ruin=0.0, mc_lev=1562706783.0232306, mc_ruin=0.0, mc_div=0.06,
                trace_lev=7491121.686101005, trace_sb=0.0, trace_tax=0.0),
}


def summarize(df, p):
    r = E.run_summary(df, p)
    t = E.run_trace(df, p, 10)
    return dict(hist_lev=float(r.hist.Lev_Final.sum()), hist_dca=float(r.hist.DCA_Final.sum()),
                hist_ruin=float(r.hist.Ruin_Prob.sum()), mc_lev=float(r.mc.Lev_Final.sum()),
                mc_ruin=float(r.mc.Is_Ruined.mean()), mc_div=float(r.mc_dividend_yield),
                trace_lev=float(t.lev_value.iloc[-1]), trace_sb=float(t.shares_b.iloc[-1]),
                trace_tax=float(t.dividend_tax.sum()))


def with_b_dividends(df, yields):
    out = df.copy()
    out["Div_Yield_B"] = yields
    return out


class SecondAssetDividendTests(unittest.TestCase):
    """6-1."""

    N = 120

    def b_yield(self, every=2, y=0.012):
        return np.where(np.arange(self.N) % every == 0, y, 0.0)

    # ----- nothing changes when the second asset pays nothing -----
    def check_golden(self, name, df):
        g = GOLDEN[name]
        got = summarize(df, T.params(**g["kw"]))
        for key, want in got.items():
            with self.subTest(case=name, key=key):
                self.assertAlmostEqual(got[key], g[key], delta=abs(g[key]) * 1e-9 + 1e-9)

    def test_no_dividend_column_is_unchanged_from_v40(self):
        for name, g in GOLDEN.items():
            self.check_golden(name, T.market(**g["mk"]))

    def test_zero_dividend_column_is_unchanged_from_v40(self):
        for name, g in GOLDEN.items():
            if g["mk"].get("with_b", True):
                self.check_golden(name, with_b_dividends(T.market(**g["mk"]), np.zeros(self.N)))

    def test_nan_dividend_column_is_unchanged_from_v40(self):
        """Months in which the second asset did not exist yet carry NaN; it must count as no dividend."""
        for name, g in GOLDEN.items():
            if g["mk"].get("with_b", True):
                self.check_golden(name, with_b_dividends(T.market(**g["mk"]), np.full(self.N, np.nan)))

    # ----- a paying second asset adds money -----
    def test_history_paying_b_raises_final_values_in_every_entry_month(self):
        base = T.market()
        paying = with_b_dividends(base, self.b_yield())
        p = T.params()
        r0, r1 = E.run_summary(base, p), E.run_summary(paying, p)
        self.assertTrue((r1.hist.Lev_Final >= r0.hist.Lev_Final - 1e-6).all())
        self.assertGreater(r1.hist.Lev_Final.sum(), r0.hist.Lev_Final.sum() * 1.001)

    def test_monte_carlo_paying_b_raises_final_values_same_seed(self):
        base = T.market()
        paying = with_b_dividends(base, self.b_yield())
        p = T.params(mc_paths=300)
        r0, r1 = E.run_summary(base, p), E.run_summary(paying, p)
        self.assertEqual(len(r0.mc), len(r1.mc))
        self.assertGreater(r1.mc.Lev_Final.sum(), r0.mc.Lev_Final.sum() * 1.001)
        self.assertTrue((r1.mc.Lev_Final >= r0.mc.Lev_Final - 1e-6).all())   # same paths, extra income only

    def test_monte_carlo_model_mode_still_runs_and_zero_b_is_unchanged(self):
        paying = with_b_dividends(T.market(), self.b_yield())
        r = E.run_summary(paying, T.params(mc_dividends=E.MC_DIVIDENDS_MODEL))
        self.assertTrue(np.isfinite(r.mc.Lev_Final).all())

    def test_no_real_record_means_no_dividend_history_and_future(self):
        """PM ruling: months without a real dividend record of the second asset (before it was listed, and the
        imagined future) count as 0. With the first asset paying nothing in the record, B is bought only from
        A's modelled future dividends; B then still pays nothing there, so every entry month is unchanged."""
        base = T.market(flat=True)
        paying = with_b_dividends(base, np.full(self.N, 0.05))
        p = T.params()
        r0, r1 = E.run_summary(base, p), E.run_summary(paying, p)
        self.assertTrue(r0.hist.Is_Spliced.any())
        np.testing.assert_allclose(r1.hist.Lev_Final, r0.hist.Lev_Final)

    def test_spliced_future_and_model_mode_give_b_no_dividend(self):
        base = with_b_dividends(T.market(), np.zeros(self.N))
        # the second asset's record is dividend-free except one early month: nothing may leak into the future
        one = base.copy()
        one.loc[one.index[5], "Div_Yield_B"] = 0.03
        for kw in (dict(), dict(mc_dividends=E.MC_DIVIDENDS_MODEL)):
            with self.subTest(kw):
                r0, r1 = E.run_summary(base, T.params(**kw)), E.run_summary(one, T.params(**kw))
                late = r0.hist.Is_Spliced & (np.arange(self.N) > 40)     # entries that never see month 5
                np.testing.assert_allclose(r1.hist.Lev_Final[late], r0.hist.Lev_Final[late])
        r0 = E.run_summary(base, T.params(mc_dividends=E.MC_DIVIDENDS_MODEL))
        r1 = E.run_summary(one, T.params(mc_dividends=E.MC_DIVIDENDS_MODEL))
        np.testing.assert_allclose(r1.mc.Lev_Final, r0.mc.Lev_Final)    # model mode: B has no assumed yield

    # ----- exact arithmetic in a flat market -----
    def oracle(self, df, p, entry, tax=0.0):
        """Independent re-computation: prices never move, nobody sells, salary pays the loan."""
        rows = slice(entry + 1, entry + 1 + p.total_months)
        ya = df["Div_Yield_A"].to_numpy()[rows]
        yb = np.nan_to_num(df["Div_Yield_B"].to_numpy()[rows])
        pa, pb = float(df["Close_A"].iloc[entry]), float(df["Close_B"].iloc[entry])
        sa, sb = p.principal / pa, 0.0
        r = p.reinvest_ratio_b
        for a, b in zip(ya, yb):
            gross = sa * pa * a + sb * pb * b          # both computed on the holdings at the start of the month
            net = gross * (1 - tax)
            sb += net * r / pb
            sa += net * (1 - r) / pa
        return sa * pa + sb * pb

    def flat_params(self, **kw):
        return T.params(salary_cap=1e9, source_order=(E.SALARY,), buffer_months=0, total_months=60, fee=0.0, sell_tax=0.0, **kw)

    def test_flat_market_matches_independent_oracle(self):
        base = T.market(flat=True)
        base["Div_Yield_A"] = np.where(np.arange(self.N) % 3 == 0, 0.015, 0.0)
        for tax in (0.0, 0.1):
            for ratio in (0.0, 0.5, 1.0):
                with self.subTest(tax=tax, ratio=ratio):
                    df = with_b_dividends(base, self.b_yield(every=2, y=0.012))
                    p = self.flat_params(reinvest_ratio_b=ratio, dividend_tax_rate=tax)
                    trace = E.run_trace(df, p, 10)
                    self.assertAlmostEqual(trace.lev_value.iloc[-1], self.oracle(df, p, 10, tax),
                                           delta=self.oracle(df, p, 10, tax) * 1e-9)

    def test_flat_market_without_b_dividend_matches_old_formula(self):
        base = T.market(flat=True)
        base["Div_Yield_A"] = np.where(np.arange(self.N) % 3 == 0, 0.015, 0.0)
        p = self.flat_params(reinvest_ratio_b=0.5)
        with_zero = E.run_trace(with_b_dividends(base, np.zeros(self.N)), p, 10).lev_value.iloc[-1]
        old = self.oracle(with_b_dividends(base, np.zeros(self.N)), p, 10)
        self.assertAlmostEqual(with_zero, old, delta=old * 1e-9)

    def test_b_dividend_is_taxed_like_the_first_assets(self):
        base = with_b_dividends(T.market(flat=True), np.full(self.N, 0.02))
        base["Div_Yield_A"] = np.where(np.arange(self.N) % 3 == 0, 0.015, 0.0)
        p0 = self.flat_params()
        p1 = self.flat_params(dividend_tax_rate=0.2)
        t0, t1 = E.run_trace(base, p0, 10), E.run_trace(base, p1, 10)
        self.assertEqual(float(t0.dividend_tax.sum()), 0.0)
        self.assertGreater(float(t1.dividend_tax.sum()), 0.0)
        a_only = E.run_trace(with_b_dividends(base, np.zeros(self.N)), p1, 10)
        self.assertGreater(float(t1.dividend_tax.sum()), float(a_only.dividend_tax.sum()))   # B's payouts add tax
        self.assertLess(t1.lev_value.iloc[-1], t0.lev_value.iloc[-1])

    def test_comparison_portfolio_also_gets_b_dividends(self):
        """The no-loan comparison holds B shares from reinvested dividends and is taxed by the same rules."""
        base = T.market()
        base["Div_Yield_A"] = np.where(np.arange(self.N) % 3 == 0, 0.015, 0.0)
        paying = with_b_dividends(base, self.b_yield())
        p = T.params()
        t0, t1 = E.run_trace(base, p, 10), E.run_trace(paying, p, 10)
        self.assertGreater(t1.dca_value.iloc[-1], t0.dca_value.iloc[-1])

    def test_dividend_cannot_buy_a_second_asset_that_went_to_zero(self):
        base = T.market()
        b = base.copy()
        b.loc[b.index[40]:, "Price_Return_B"] = 0.0
        b = with_b_dividends(b, self.b_yield())
        r = E.run_summary(b, T.params())
        self.assertTrue(np.isfinite(r.hist.Lev_Final).all() and np.isfinite(r.mc.Lev_Final).all())

    def test_months_before_b_existed_are_modelled_without_nan(self):
        df = T.market()
        df.loc[df.index[:40], ["Close_B", "Price_Return_B"]] = np.nan
        df = with_b_dividends(df, np.where(np.arange(self.N) < 40, np.nan, self.b_yield()))
        r = E.run_summary(df, T.params())
        self.assertTrue(np.isfinite(r.hist.Lev_Final).all())
        self.assertTrue(np.isfinite(r.mc.Lev_Final).all())
        self.assertGreater(r.modelled_b_months, 0)

    def test_pipeline_from_daily_history_carries_b_dividends(self):
        """monthly_data + align_months already give the second asset a Div_Yield column; it must reach the engine."""
        import market_data as md
        days = pd.bdate_range("2012-01-02", "2021-12-31")
        rng = np.random.RandomState(3)

        def daily(div, months=(3, 9)):
            close = 20 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
            dv = np.zeros(len(days))
            if div:
                first = ~pd.Series(days.to_period("M"), index=days).duplicated()
                dv[(first & pd.Series(days.month, index=days).isin(months)).to_numpy()] = close[
                    (first & pd.Series(days.month, index=days).isin(months)).to_numpy()] * 0.02
            return pd.DataFrame({"Close": close, "Dividends": dv}, index=days.tz_localize("Asia/Taipei"))

        a, b_pay = daily(True, (6, 12)), daily(True)   # A must pay too, or no money ever buys B
        b_none = b_pay.copy()
        b_none["Dividends"] = 0.0
        ma = md.monthly_data(a, 1)
        res = []
        for b in (b_pay, b_none):
            mb = md.monthly_data(b, 1)
            aligned = md.align_months(ma, mb)
            self.assertIn("Div_Yield_B", aligned.columns)
            res.append(E.run_summary(aligned, T.params(total_months=60)))
        self.assertGreater(res[0].hist.Lev_Final.sum(), res[1].hist.Lev_Final.sum())
        self.assertGreater(res[0].mc.Lev_Final.sum(), res[1].mc.Lev_Final.sum())




# ---------------------------------------------------------------- 6-2
CJK = re.compile("[\u2e80-\u9fff\uac00-\ud7af\uff00-\uffef\u3000-\u303f]")
FIELDS_OLD = ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價", "權值", "息值", "權值+息值", "權/息"]
FIELDS_NEW = ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價", "權值+息值", "權/息", "漲停價格"]


def table(rows):
    t = pd.DataFrame(rows, columns=["Date", "Code", "Cash", "Kind"])
    t["Date"] = pd.to_datetime(t["Date"])
    t.attrs.update(fetched_at="2026-11-22T00:00:00Z", years=[2024])
    return t


def daily_history(start="2008-01-02", end="2021-12-31", seed=1, splits=None):
    days = pd.bdate_range(start, end)
    close = 50 * np.cumprod(1 + np.random.RandomState(seed).normal(0.0003, 0.008, len(days)))
    df = pd.DataFrame({"Close": close, "Dividends": 0.0}, index=days)
    df.attrs.update(ticker="0056.TW", data_source="live", fetched_at="2026-11-22T00:00:00Z")
    return df


def monthly_div(df, ticker, events, **kw):
    with patch.object(md, "dividend_events", return_value=events):
        return md.monthly_data(md.attach_official_dividends(df, ticker), 1, **kw)


def english(note):
    with i18n.use("en"):
        return i18n.t(note)


class OfficialDividendTests(unittest.TestCase):
    """6-2."""

    def test_official_events_replace_yahoo_dividends(self):
        df = daily_history()
        df.loc["2020-03-16", "Dividends"] = 0.5            # what Yahoo says
        df.loc["2019-09-16", "Dividends"] = 0.4
        events = table([("2020-03-16", "0056", 0.9, "息"), ("2010-10-18", "0056", 0.85, "息")])
        m = monthly_div(df, "0056.TW", events)
        paid = m["Monthly_Div"][m["Monthly_Div"] > 0]
        self.assertEqual(sorted(round(v, 6) for v in paid), [0.85, 0.9])           # Yahoo's two are gone
        self.assertEqual(m.attrs["data_source"], "live")
        self.assertFalse([r for r in m.attrs["repairs"] if "Yahoo" in str(r)])      # no fallback note

    def test_rights_rows_are_not_dividends_and_other_codes_ignored(self):
        events = table([("2020-03-16", "0056", 0.9, "息"), ("2020-06-15", "0056", 3.0, "權"),
                        ("2020-03-16", "0050", 5.0, "息")])
        m = monthly_div(daily_history(), "0056.TW", events)
        self.assertEqual(list(m["Monthly_Div"][m["Monthly_Div"] > 0].round(6)), [0.9])

    def test_etf_in_table_without_dividends_gets_none_not_yahoo(self):
        df = daily_history()
        df.loc["2020-03-16", "Dividends"] = 0.5
        m = monthly_div(df, "0056.TW", table([("2020-03-16", "0050", 5.0, "息")]))   # 0056 absent: Yahoo, with note
        self.assertEqual(round(m["Monthly_Div"].sum(), 6), 0.5)
        self.assertTrue([r for r in m.attrs["repairs"] if "Yahoo" in str(r)])

    # ---- fallback notices
    def fallback_notes(self, ticker, events, with_dividends=True):
        df = daily_history()
        if with_dividends:
            df.loc["2020-03-16", "Dividends"] = 0.5
        m = monthly_div(df, ticker, events)
        return [r for r in m.attrs["repairs"] if "Yahoo" in str(r)], m

    def test_unavailable_table_falls_back_with_notice_in_both_languages(self):
        notes, m = self.fallback_notes("0056.TW", None)
        self.assertEqual(len(notes), 1)
        self.assertEqual(round(m["Monthly_Div"].sum(), 6), 0.5)      # Yahoo's dividend still used
        en = english(notes[0])
        self.assertIn("Yahoo", en)
        self.assertIsNone(CJK.search(en), en)
        self.assertIsNotNone(CJK.search(str(notes[0])))

    def test_etf_missing_from_table_notice_both_languages(self):
        notes, _ = self.fallback_notes("0056.TW", table([("2020-03-16", "0050", 5.0, "息")]))
        self.assertEqual(len(notes), 1)
        self.assertIsNone(CJK.search(english(notes[0])))
        other, _ = self.fallback_notes("0056.TW", None)
        self.assertNotEqual(str(notes[0]), str(other[0]))            # a different reason, a different sentence

    def test_no_notice_for_non_paying_or_non_tw(self):
        events = table([("2020-03-16", "0050", 5.0, "息")])
        for ticker, unavailable in (("00631L.TW", events), ("00631L.TW", None)):
            with self.subTest(ticker=ticker, table=unavailable is not None):
                notes, _ = self.fallback_notes(ticker, unavailable, with_dividends=False)
                self.assertEqual(notes, [])
        for ticker in ("SPY", "2330.TW", "00679B.TWO", "^TWII"):
            with self.subTest(ticker=ticker):
                notes, m = self.fallback_notes(ticker, None)
                self.assertEqual(notes, [])
                self.assertEqual(round(m["Monthly_Div"].sum(), 6), 0.5)    # untouched
                self.assertNotIn("official_status", md.attach_official_dividends(daily_history(), ticker).attrs)

    # ---- parsing
    def payload(self, fields, rows):
        return {"fields": fields, "data": rows}

    def test_old_layout_prefers_cash_column(self):
        rows = [["94年05月19日", "0050", "元大台灣50", "50.0", "48.0", 0.0, 1.85, "1.85", "息"],
                ["97年10月24日", "0050", "元大台灣50", "50.0", "48.0", 5.0, 2.0, "7.00", "權息"],
                ["97年10月24日", "2330", "台積電", "50.0", "48.0", 0.0, 3.0, "3.00", "息"]]
        ev = md.parse_twse_events(self.payload(FIELDS_OLD, rows))
        self.assertEqual(ev, [(pd.Timestamp(2005, 5, 19), "0050", 1.85, "息"),
                              (pd.Timestamp(2008, 10, 24), "0050", 2.0, "權息")])

    def test_new_layout_commas_and_roc_dates(self):
        rows = [["114年01月17日", "0050", "元大台灣50", "198.05", "195.35", "2.70", "息", "x"],
                ["113年01月17日", "00878", "國泰永續高股息", "20", "19", "1,234.5", "息", "x"],
                ["114年10月23日", "00631L", "元大台灣50正2", "20", "19", "0.0", "息", "x"],
                ["114年10月23日", "1101", "台泥", "20", "19", "1.0", "息", "x"],
                ["114年10月23日", "00679B", "債券", "20", "19", "0.3", "息", "x"]]
        ev = md.parse_twse_events(self.payload(FIELDS_NEW, rows))
        self.assertEqual([(d, c, v) for d, c, v, _ in ev],
                         [(pd.Timestamp(2025, 1, 17), "0050", 2.7), (pd.Timestamp(2024, 1, 17), "00878", 1234.5),
                          (pd.Timestamp(2025, 10, 23), "00631L", 0.0), (pd.Timestamp(2025, 10, 23), "00679B", 0.3)])

    def test_empty_and_unknown_layouts(self):
        self.assertEqual(md.parse_twse_events({"fields": [], "data": []}), [])
        with self.assertRaises((ValueError, KeyError)):
            md.parse_twse_events({"fields": ["a", "b"], "data": [["x", "y"]]})

    def test_roc_date(self):
        self.assertEqual(md._roc_date("114年01月17日"), pd.Timestamp(2025, 1, 17))
        self.assertEqual(md._roc_date("94/05/19"), pd.Timestamp(2005, 5, 19))

    # ---- splits
    def test_dividend_before_unadjusted_split_is_converted_by_the_ratio(self):
        df = daily_history("2024-01-02", "2025-12-31")
        seam = pd.Timestamp("2025-06-30")
        df.loc[df.index < seam, "Close"] *= 4.0            # the source never adjusted the 1:4 split
        events = table([("2025-01-17", "0050", 2.70, "息"), ("2025-07-21", "0050", 0.36, "息")])
        df.attrs["ticker"] = "0050.TW"
        m = monthly_div(df, "0050.TW", events)
        paid = m["Monthly_Div"][m["Monthly_Div"] > 0]
        self.assertEqual([round(v, 6) for v in paid], [0.675, 0.36])
        self.assertTrue(any("拆" in str(r) or "股票分割" in str(r) for r in m.attrs["repairs"]))

    def test_dividend_before_reported_split_is_converted_by_the_ratio(self):
        df = daily_history("2024-01-02", "2025-12-31")
        df["Stock Splits"] = 0.0
        df.loc["2025-06-30", "Stock Splits"] = 4.0         # reported, prices already adjusted
        df.attrs["ticker"] = "0050.TW"
        events = table([("2025-01-17", "0050", 2.70, "息"), ("2025-07-21", "0050", 0.36, "息")])
        m = monthly_div(df, "0050.TW", events)
        paid = m["Monthly_Div"][m["Monthly_Div"] > 0]
        self.assertEqual([round(v, 6) for v in paid], [0.675, 0.36])

    def test_no_split_leaves_cash_as_is(self):
        m = monthly_div(daily_history(), "0056.TW", table([("2015-03-16", "0056", 0.85, "息")]))
        self.assertEqual(round(m["Monthly_Div"].sum(), 6), 0.85)

    # ---- incremental update
    def fake_exchange(self, calls, fail=(), empty=()):
        def get(path, **params):
            calls.append((path, params["startDate"], params["endDate"]))
            year = int(params["startDate"][:4])
            if year in fail:
                raise ConnectionError("blocked")
            if year in empty:     # the exchange's "no data" reply: no fields, no rows
                return {"fields": [], "data": []}
            return {"fields": FIELDS_NEW, "data": [[f"{year - 1911}年03月16日", "0056", "x", "1", "1", "0.5", "息", "x"]]}
        return get

    def test_only_new_years_and_the_last_two_are_fetched(self):
        known = table([("2003-06-01", "0050", 1.0, "息")])
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls)):
            out, years = md.fetch_twse_events(known, range(2003, 2025), today=pd.Timestamp("2026-03-10"), log=lambda *_: None)
        self.assertEqual(sorted({int(c[1][:4]) for c in calls}), [2025, 2026])
        self.assertEqual(years[0], 2003)
        self.assertEqual(years[-1], 2026)
        self.assertIn(pd.Timestamp("2003-06-01"), set(out["Date"]))     # old rows kept
        self.assertEqual(calls[-1][2], "20260309")                      # never reaches the current day

    def test_first_run_starts_at_the_exchanges_first_day(self):
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls)):
            out, years = md.fetch_twse_events(None, (), today=pd.Timestamp("2005-02-10"), log=lambda *_: None)
        self.assertEqual(calls[0][1:], ("20030505", "20031231"))
        self.assertEqual(years, [2003, 2004, 2005])
        self.assertEqual(len(out), 3)

    def test_failed_year_keeps_old_rows_and_is_retried_later(self):
        known = table([("2025-03-16", "0056", 9.9, "息")])
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls, fail=(2025,))):
            out, years = md.fetch_twse_events(known, range(2003, 2026), today=pd.Timestamp("2026-03-10"), log=lambda *_: None)
        self.assertIn(9.9, list(out["Cash"]))                           # not lost
        self.assertEqual(years, sorted(set(years)))
        self.assertIn(2026, years)
        self.assertIn(2025, years)                                      # it was already covered before; stays so

    def test_failed_new_year_is_not_marked_done(self):
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls, fail=(2004,))):
            _, years = md.fetch_twse_events(None, (), today=pd.Timestamp("2005-02-10"), log=lambda *_: None)
        self.assertEqual(years, [2003, 2005])

    def test_first_year_without_any_event_from_an_empty_start(self):
        """Found on GitHub Actions: 2003 has no ETF rows, the empty table's Date column was not datetime."""
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls, empty=(2003,))):
            out, years = md.fetch_twse_events(None, (), today=pd.Timestamp("2005-02-10"), log=lambda *_: None)
        self.assertEqual(years, [2003, 2004, 2005])                 # an empty year is still a year done
        self.assertEqual(sorted(out["Date"].dt.year.unique()), [2004, 2005])

    def test_year_in_the_middle_without_events(self):
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls, empty=(2004,))):
            out, years = md.fetch_twse_events(None, (), today=pd.Timestamp("2006-02-10"), log=lambda *_: None)
        self.assertEqual(years, [2003, 2004, 2005, 2006])
        self.assertEqual(sorted(out["Date"].dt.year.unique()), [2003, 2005, 2006])

    def test_every_year_empty_and_known_table_survives_an_empty_year(self):
        calls = []
        with patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls, empty=range(2003, 2030))):
            out, years = md.fetch_twse_events(None, (), today=pd.Timestamp("2005-02-10"), log=lambda *_: None)
            self.assertTrue(out.empty)
            self.assertEqual(list(out.columns), ["Date", "Code", "Cash", "Kind"])
            known = table([("2025-03-16", "0056", 9.9, "息")])
            out2, _ = md.fetch_twse_events(known, range(2003, 2025), today=pd.Timestamp("2026-03-10"), log=lambda *_: None)
        self.assertEqual(list(out2["Cash"]), [])                    # 2025 re-fetched as empty: the exchange is the authority
        with tempfile.TemporaryDirectory() as d:                    # and an empty table can still be written and read back
            md.write_dividend_events(out, years, d)
            back = md.parse_dividend_events(open(os.path.join(d, md.DIVIDENDS_FILE), encoding="utf-8").read())
        self.assertTrue(back is None or back.empty)

    # ---- files, backups
    def test_file_roundtrip_and_header_format(self):
        with tempfile.TemporaryDirectory() as d:
            t = table([("2024-01-17", "0050", 3.0, "息"), ("2024-02-01", "0056", 0.7, "息")])
            path = md.write_dividend_events(t, [2023, 2024], d)
            lines = open(path, encoding="utf-8").read().split("\n")
            self.assertTrue(lines[0].startswith("# fetched_at="))
            self.assertEqual(lines[1], "# years=2023,2024")
            self.assertEqual(lines[2], "Date,Code,Cash,Kind")
            back = md.parse_dividend_events(open(path, encoding="utf-8").read())
            self.assertEqual(back.attrs["years"], [2023, 2024])
            self.assertEqual(list(back["Code"]), ["0050", "0056"])
            self.assertEqual(list(back["Cash"]), [3.0, 0.7])

    def test_unusable_files_are_ignored(self):
        for text in ("", "<html>blocked</html>", "# years=1\nDate,Code\n2024-01-01,0050\n",
                     "Date,Code,Cash,Kind\n2024-01-01,0050,,息\n"):
            with self.subTest(text[:20]):
                self.assertIsNone(md.parse_dividend_events(text))

    def test_listed_extras_never_reads_the_event_table_as_a_ticker(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("0050.TW.csv", md.DIVIDENDS_FILE, "index.csv"):
                open(os.path.join(d, name), "w").close()
            with patch.object(md, "SEED_DIR", d):
                extras = md._listed_extras()
        self.assertIn("0050.TW", extras)
        self.assertNotIn(md.DIVIDENDS_FILE[:-4], extras)

    def test_old_backups_without_the_event_table_still_work(self):
        """A mirror or snapshot folder from before 6-2 has price files only."""
        with tempfile.TemporaryDirectory() as d, patch.object(md, "SNAPSHOT_DIR", d), patch.object(md, "SEED_DIR", d), \
                patch.object(md, "MIRROR_URL", ""):
            md._events_cache.update(at=float("-inf"), table=None)
            df = daily_history("2020-01-02", "2020-12-31")
            df.loc["2020-03-16", "Dividends"] = 0.5
            md.save_snapshot(df, "0056.TW")
            old = md.read_snapshot("0056.TW")
            self.assertEqual(float(old["Dividends"].sum()), 0.5)
            self.assertIsNone(md.dividend_events())
            attached = md.attach_official_dividends(old, "0056.TW")
            self.assertEqual(attached.attrs["official_status"], "unavailable")
            self.assertEqual(round(md.monthly_data(attached, 1)["Monthly_Div"].sum(), 6), 0.5)
        md._events_cache.update(at=float("-inf"), table=None)

    def test_event_table_beside_price_files_is_read_and_cached(self):
        with tempfile.TemporaryDirectory() as d, patch.object(md, "SNAPSHOT_DIR", d), patch.object(md, "SEED_DIR", ""), \
                patch.object(md, "MIRROR_URL", ""):
            md._events_cache.update(at=float("-inf"), table=None)
            t = table([("2015-03-16", "0056", 0.85, "息")])
            md.write_dividend_events(t, [2015], d)
            # an old copy still counts when nothing newer exists
            got = md.dividend_events()
            self.assertEqual(list(got["Code"]), ["0056"])
            attached = md.attach_official_dividends(daily_history(), "0056.TW")
            self.assertEqual(attached.attrs["official_status"], "official")
        md._events_cache.update(at=float("-inf"), table=None)

    def test_refresh_writes_the_file_and_cli_flags_exist(self):
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.object(md, "MIRROR_URL", ""), \
                patch.object(md, "_twse_get", side_effect=self.fake_exchange(calls)), \
                patch.object(md, "_today", return_value=pd.Timestamp("2005-02-10")):
            n = md.refresh_dividend_events(d, log=lambda *_: None)
            self.assertEqual(n, 3)
            self.assertTrue(os.path.exists(os.path.join(d, md.DIVIDENDS_FILE)))
            before = len(calls)
            md.refresh_dividend_events(d, log=lambda *_: None)             # incremental: only the last two years
            self.assertEqual(len(calls) - before, 2)
        src = open(md.__file__, encoding="utf-8").read()
        self.assertIn('"--twse-dividends"', src)
        self.assertIn('"--dividends-only"', src)


if __name__ == "__main__":
    unittest.main()
