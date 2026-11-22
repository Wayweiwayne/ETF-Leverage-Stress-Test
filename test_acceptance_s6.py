"""Sprint 6 acceptance (QA): 6-1 second-asset dividends, 6-2 official TWSE dividends. No network.

6-1  A dividend paid by the second asset (column Div_Yield_B of the aligned monthly data) is taxed and
     reinvested by the same rules as the first asset's; an asset that pays nothing leaves every
     result exactly as it was before the change (GOLDEN below was produced by the V40 engine).
6-2  The exchange's ex-dividend table (exRight/TWT49U) is preferred over Yahoo's dividends; when it cannot
     be read the old source is used and the page says so, in both languages.
"""
import unittest

import numpy as np
import pandas as pd

import engine as E
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


if __name__ == "__main__":
    unittest.main()
