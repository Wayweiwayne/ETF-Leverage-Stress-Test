import unittest

import numpy as np
import pandas as pd

import engine as E


def market(n=120, seed=1, with_b=True, flat=False):
    """Aligned monthly data in the shape market_data.align_months produces."""
    rng = np.random.RandomState(seed)
    ret_a = np.zeros(n) if flat else rng.normal(0.006, 0.05, n)
    data = {
        'Close_A': 20 * np.cumprod(1 + ret_a),
        'Price_Return_A': ret_a,
        'Div_Yield_A': np.zeros(n) if flat else np.where(np.arange(n) % 3 == 0, 0.015, 0.0),
    }
    if with_b:
        ret_b = 2 * ret_a + (0 if flat else rng.normal(0, 0.01, n))
        data.update({'Close_B': 30 * np.cumprod(1 + ret_b), 'Price_Return_B': ret_b})
    return pd.DataFrame(data, index=pd.date_range('2010-01-01', periods=n, freq='MS'))


def params(**overrides):
    base = dict(principal=5_000_000.0, annual_rate_pct=3.5, total_months=84, reinvest=True,
                reinvest_ratio_b=0.5, salary_cap=25_000.0, mc_paths=200, seed=42)
    base.update(overrides)
    return E.SimParams(**base)


def one_path(returns, payments, order, salary_cap=0.0, div_yield=0.0, **kwargs):
    """Single leveraged path, no second asset, starting price 100."""
    months = len(returns)
    col = lambda v: np.full((months, 1), float(v)) if np.isscalar(v) else np.asarray(v, float).reshape(-1, 1)
    defaults = dict(principal=1_000_000.0, buffer_cash=0.0, fee=0.0, reinvest=False, ratio_b=0.0)
    defaults.update(kwargs)
    return E.simulate_paths(col(returns), np.zeros((months, 1)), col(div_yield), np.array([100.0]),
                            np.array([1.0]), np.asarray(payments, float), order=order,
                            salary_cap=col(salary_cap), record=True, **defaults)


class LoanScheduleTests(unittest.TestCase):
    def test_level_payment_matches_annuity_formula_and_clears_the_loan(self):
        s = E.build_loan_schedule(1_000_000, 6.0, 120)
        r = 0.06 / 12
        expected = 1_000_000 * r / (1 - (1 + r) ** -120)
        np.testing.assert_allclose(s.payments, expected)
        self.assertAlmostEqual(s.end_balance[-1], 0.0, places=4)
        self.assertEqual(s.start_balance[0], 1_000_000)

    def test_grace_period_is_interest_only_then_payment_jumps(self):
        s = E.build_loan_schedule(1_000_000, 6.0, 120, grace_months=36)
        np.testing.assert_allclose(s.payments[:36], 1_000_000 * 0.005)
        np.testing.assert_allclose(s.end_balance[:36], 1_000_000)
        self.assertGreater(s.payments[36], s.payments[35] * 2)
        self.assertAlmostEqual(s.end_balance[-1], 0.0, places=4)

    def test_rate_shock_raises_payment_and_still_clears_the_loan(self):
        base = E.build_loan_schedule(1_000_000, 3.0, 120)
        shocked = E.build_loan_schedule(1_000_000, 3.0, 120, shock_year=4, shock_delta_pct=2.0)
        np.testing.assert_allclose(shocked.payments[:36], base.payments[:36])
        self.assertTrue((shocked.payments[36:] > base.payments[36:]).all())
        self.assertAlmostEqual(shocked.monthly_rates[36], 0.05 / 12)
        self.assertAlmostEqual(shocked.end_balance[-1], 0.0, places=4)

    def test_rate_shock_inside_grace_raises_the_interest_only_payment(self):
        s = E.build_loan_schedule(1_000_000, 3.0, 120, grace_months=36, shock_year=2, shock_delta_pct=1.0)
        self.assertAlmostEqual(s.payments[11], 1_000_000 * 0.03 / 12)
        self.assertAlmostEqual(s.payments[12], 1_000_000 * 0.04 / 12)
        self.assertAlmostEqual(s.end_balance[-1], 0.0, places=4)

    def test_zero_rate_loan(self):
        s = E.build_loan_schedule(1_200_000, 0.0, 12)
        np.testing.assert_allclose(s.payments, 100_000)
        self.assertAlmostEqual(s.end_balance[-1], 0.0)

    def test_grace_must_be_shorter_than_the_loan(self):
        # A grace period covering the whole term would mean the principal is never repaid.
        with self.assertRaises(ValueError):
            E.build_loan_schedule(1_000_000, 3.0, 36, grace_months=36)
        with self.assertRaises(ValueError):
            E.build_loan_schedule(1_000_000, 3.0, 12, grace_months=36)

    def test_buffer_is_capped_at_the_principal(self):
        s = E.build_loan_schedule(1_000_000, 3.0, 12)
        self.assertEqual(E.buffer_cash_for(s, 0, 12, 1_000_000), 1_000_000)
        self.assertAlmostEqual(E.buffer_cash_for(s, 0, 3, 1_000_000), 3 * s.payments[0])


class WaterfallTests(unittest.TestCase):
    def test_sources_are_used_in_order_up_to_their_limits(self):
        res = one_path([0.0] * 3, [10_000] * 3, (E.SALARY, E.BUFFER, E.SELL), salary_cap=4_000, buffer_cash=9_000)
        led = res.ledger
        np.testing.assert_allclose(led['from_salary'][:, 0], [4_000, 4_000, 4_000])
        np.testing.assert_allclose(led['from_buffer'][:, 0], [6_000, 3_000, 0])
        np.testing.assert_allclose(led['from_sell'][:, 0], [0, 3_000, 6_000])
        self.assertFalse(res.ruined[0])
        # 991,000 invested at 100, then 9,000 of it sold
        self.assertAlmostEqual(res.lev_final[0], 991_000 - 9_000)

    def test_dividend_pool_pays_before_salary_when_ranked_first(self):
        res = one_path([0.0] * 2, [10_000] * 2, (E.DIVIDEND, E.SALARY), salary_cap=10_000, div_yield=0.004)
        np.testing.assert_allclose(res.ledger['from_dividend'][:, 0], [4_000, 4_000])
        np.testing.assert_allclose(res.ledger['from_salary'][:, 0], [6_000, 6_000])

    def test_source_left_out_of_the_order_is_never_touched(self):
        res = one_path([0.0] * 2, [10_000] * 2, (E.SALARY,), salary_cap=4_000)
        self.assertTrue(res.ruined[0])
        self.assertTrue(res.ledger['defaulted'][0, 0])
        self.assertEqual(res.ledger['from_sell'].sum(), 0)
        self.assertEqual(res.lev_final[0], 0)

    def test_repeated_source_counts_once(self):
        a = one_path([0.01] * 6, [10_000] * 6, (E.SALARY, E.SALARY, E.SELL), salary_cap=4_000)
        b = one_path([0.01] * 6, [10_000] * 6, (E.SALARY, E.SELL), salary_cap=4_000)
        np.testing.assert_allclose(a.lev_final, b.lev_final)
        np.testing.assert_allclose(a.ledger['from_salary'], b.ledger['from_salary'])

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            one_path([0.0], [1.0], ("lottery",))

    def test_ruin_is_permanent_even_if_the_market_recovers(self):
        res = one_path([-0.99, 5.0, 5.0], [600_000, 10, 10], (E.SELL,))
        self.assertTrue(res.ruined[0])
        np.testing.assert_array_equal(res.ledger['defaulted'][:, 0], [True, False, False])
        self.assertEqual(res.lev_final[0], 0)

    def test_crash_haircut_forces_more_shares_to_be_sold(self):
        kwargs = dict(returns=[-0.3], payments=[70_000], order=(E.SELL,))
        plain = one_path(**kwargs)
        hit = one_path(haircut_trigger=0.2, haircut_penalty=0.1, **kwargs)
        self.assertAlmostEqual(plain.ledger['shares_a'][0, 0], 10_000 - 1_000)
        self.assertAlmostEqual(hit.ledger['shares_a'][0, 0], 10_000 - 70_000 / 0.9 / 70)
        self.assertAlmostEqual(plain.ledger['from_sell'][0, 0], hit.ledger['from_sell'][0, 0])

    def test_haircut_does_not_apply_below_the_trigger(self):
        kwargs = dict(returns=[-0.1], payments=[9_000], order=(E.SELL,))
        np.testing.assert_allclose(one_path(**kwargs).lev_final,
                                   one_path(haircut_trigger=0.2, haircut_penalty=0.1, **kwargs).lev_final)


class DcaComparisonTests(unittest.TestCase):
    def test_matched_mode_invests_exactly_what_salary_paid(self):
        res = one_path([0.01] * 12, [10_000] * 12, (E.SALARY, E.SELL), salary_cap=4_000)
        np.testing.assert_allclose(res.ledger['dca_contribution'], res.ledger['from_salary'])
        self.assertAlmostEqual(res.ledger['dca_contribution'].sum(), 48_000)

    def test_full_mode_invests_the_whole_payment(self):
        res = one_path([0.01] * 12, [10_000] * 12, (E.SALARY, E.SELL), salary_cap=4_000,
                       dca_mode=E.DCA_FULL_PAYMENT)
        self.assertAlmostEqual(res.ledger['dca_contribution'].sum(), 120_000)

    def test_modes_agree_when_salary_covers_every_payment(self):
        kwargs = dict(returns=[0.01, -0.05, 0.03] * 4, payments=[10_000] * 12, order=(E.SALARY, E.SELL),
                      salary_cap=10_000)
        np.testing.assert_allclose(one_path(**kwargs).dca_final,
                                   one_path(dca_mode=E.DCA_FULL_PAYMENT, **kwargs).dca_final)

    def test_no_salary_used_means_nothing_invested(self):
        res = one_path([0.0] * 3, [10_000] * 3, (E.SELL, E.SALARY), salary_cap=10_000)
        self.assertEqual(res.ledger['dca_contribution'].sum(), 0)
        self.assertEqual(res.dca_final[0], 0)

    def test_after_ruin_the_comparison_keeps_investing_what_salary_could_cover(self):
        res = one_path([0.0] * 3, [10_000] * 3, (E.SALARY,), salary_cap=4_000)
        np.testing.assert_allclose(res.ledger['dca_contribution'][:, 0], [4_000, 4_000, 4_000])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            one_path([0.0], [1.0], (E.SALARY,), dca_mode="everything")


class RunTests(unittest.TestCase):
    def test_black_swan_is_applied_exactly_once_in_the_ledger(self):
        # Flat market, no dividends, salary pays everything: the only thing moving the portfolio is the crash.
        df = market(flat=True, with_b=False)
        p = params(reinvest=False, salary_cap=1e9, source_order=(E.SALARY,), fee=0.0,
                   swan_month=12, swan_drop=0.40)
        trace = E.run(df, p, anchor_idx=10).trace
        np.testing.assert_allclose(trace['lev_value'].iloc[:11], 5_000_000)
        np.testing.assert_allclose(trace['lev_value'].iloc[11:], 5_000_000 * 0.60)

    def test_ledger_agrees_with_the_summary_for_every_start_month(self):
        df = market()
        p = params(salary_cap=20_000.0, swan_month=6, swan_drop=0.3, haircut_trigger=0.1, haircut_penalty=0.05,
                   buffer_months=2, rate_shock_year=3, rate_shock_delta_pct=1.5)
        seen_ruin = seen_survivor = False
        for anchor in range(0, len(df), 7):
            res = E.run(df, p, anchor)
            row, trace = res.hist.iloc[anchor], res.trace
            self.assertEqual(bool(trace['defaulted'].iloc[-1]), bool(row['Is_Ruined']))
            self.assertEqual(int(trace['defaulted'].sum()), int(row['Is_Ruined']))
            if row['Is_Ruined']:
                seen_ruin = True
                self.assertLess(len(trace), p.total_months + 1)
            else:
                seen_survivor = True
                self.assertEqual(len(trace), p.total_months)
                self.assertAlmostEqual(trace['lev_value'].iloc[-1], row['Lev_Final'], places=4)
                self.assertAlmostEqual(trace['dca_value'].iloc[-1], row['DCA_Final'], places=4)
                self.assertAlmostEqual(trace['loan_balance'].iloc[-1], 0.0, places=3)
            paid = trace[['from_dividend', 'from_buffer', 'from_sell', 'from_salary']].sum(axis=1)
            ok = ~trace['defaulted']
            np.testing.assert_allclose(paid[ok], trace['payment'][ok])
        self.assertTrue(seen_ruin and seen_survivor, "fixture should exercise both outcomes")

    def test_ledger_marks_months_beyond_real_history_as_projected(self):
        df = market(n=40)
        trace = E.run(df, params(), anchor_idx=30).trace
        self.assertEqual(int((~trace['projected']).sum()), 10)
        self.assertEqual(trace['date'].iloc[0], df.index[30])
        self.assertEqual(trace['date'].iloc[10], df.index[-1] + pd.DateOffset(months=1))

    def test_fixed_seed_is_reproducible_and_seeds_differ(self):
        df = market()
        a, b = E.run(df, params(), 20).mc, E.run(df, params(), 20).mc
        pd.testing.assert_frame_equal(a, b)
        c = E.run(df, params(seed=7), 20).mc
        self.assertFalse(np.allclose(a['Lev_Final'], c['Lev_Final']))

    def test_engine_leaves_numpy_global_random_state_alone(self):
        df = market()
        np.random.seed(123)
        expected = np.random.random(3)
        np.random.seed(123)
        E.run(df, params(job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.2)), 20)
        np.testing.assert_array_equal(np.random.random(3), expected)

    def test_monte_carlo_size_and_block_clamping(self):
        res = E.run(market(n=8), params(mc_paths=150, block_size=24, total_months=24), 2)
        self.assertEqual(len(res.mc), 150)
        self.assertEqual(res.block_size, 8)
        self.assertTrue(res.mc_ok)

    def test_single_month_of_history_skips_monte_carlo(self):
        res = E.run(market(n=1), params(total_months=12), 0)
        self.assertFalse(res.mc_ok)
        self.assertTrue(res.mc.empty)
        self.assertEqual(len(res.hist), 1)

    def test_reinvesting_without_a_second_asset_puts_everything_in_the_first(self):
        res = E.run(market(with_b=False), params(reinvest_ratio_b=0.5), 20)
        self.assertEqual(res.trace['shares_b'].abs().sum(), 0)
        self.assertEqual(res.vol_drag, 0.0)

    def test_extreme_crash_never_produces_negative_values(self):
        # The second asset takes the crash times its beta (about 2 here), which would exceed -100%.
        res = E.run(market(), params(swan_month=3, swan_drop=0.6, salary_cap=1e9), 20)
        self.assertTrue((res.hist['Lev_Final'] >= 0).all())
        self.assertTrue((res.mc['Lev_Final'] >= 0).all())
        self.assertTrue((res.trace['lev_value'] >= 0).all())

    def test_injected_crash_is_floored_at_total_loss(self):
        ret_a = np.array([[0.02, -0.50], [0.01, 0.01]])
        ret_b = np.array([[0.04, -0.70], [0.02, 0.02]])
        E._inject_swan(ret_a, ret_b, month=1, drop=0.6, beta_b=2.0, has_b=True)
        np.testing.assert_allclose(ret_a[0], [-0.58, -1.0])
        np.testing.assert_allclose(ret_b[0], [-1.0, -1.0])
        np.testing.assert_allclose(ret_a[1], [0.01, 0.01])

    def test_volatility_drag_only_when_enabled_with_a_second_asset(self):
        df = market()
        self.assertGreater(E.run(df, params(), 20).vol_drag, 0)
        self.assertEqual(E.run(df, params(vol_drag=False), 20).vol_drag, 0)

    def test_higher_salary_support_never_increases_ruin(self):
        df = market()
        rates = [E.run(df, params(salary_cap=float(cap)), 20).mc['Is_Ruined'].mean()
                 for cap in (0, 20_000, 40_000, 200_000)]
        self.assertEqual(rates, sorted(rates, reverse=True))
        self.assertEqual(rates[-1], 0.0)

    def test_anchor_must_be_inside_the_data(self):
        with self.assertRaises(ValueError):
            E.run(market(), params(), 500)


class JobLossTests(unittest.TestCase):
    def test_manual_window_lowers_the_cap_only_inside_it(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_MANUAL, unemployed_salary=1_000, start_month=3, duration_months=2)
        caps = E.salary_cap_schedule(30_000, job, 6)
        np.testing.assert_array_equal(caps, [30_000, 30_000, 1_000, 1_000, 30_000, 30_000])

    def test_manual_window_is_clipped_to_the_loan_term(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_MANUAL, start_month=5, duration_months=10)
        np.testing.assert_array_equal(E.salary_cap_schedule(100, job, 6), [100, 100, 100, 100, 0, 0])

    def test_zero_probability_means_never_unemployed(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.0)
        caps = E.simulate_unemployment(np.zeros((60, 500)), 30_000, job, np.random.RandomState(0))
        self.assertTrue((caps == 30_000).all())

    def test_unemployment_frequency_tracks_the_annual_probability(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.10, mean_duration=1.0, duration_sigma=0.05)
        caps = E.simulate_unemployment(np.zeros((12, 20_000)), 30_000, job, np.random.RandomState(0))
        hit_within_a_year = (caps < 30_000).any(axis=0).mean()
        self.assertAlmostEqual(hit_within_a_year, 0.10, delta=0.01)

    def test_crash_link_raises_unemployment_in_crash_months(self):
        rets = np.zeros((24, 20_000))
        rets[5, :] = -0.30
        base = dict(mode=E.JOB_LOSS_RANDOM, annual_prob=0.02, mean_duration=3.0)
        calm = E.simulate_unemployment(rets, 1.0, E.JobLossParams(**base), np.random.RandomState(1))
        linked = E.simulate_unemployment(
            rets, 1.0, E.JobLossParams(crash_linked=True, crash_threshold=0.15, crash_extra_low=0.3,
                                       crash_extra_high=0.4, **base), np.random.RandomState(1))
        self.assertGreater((linked[5] < 1).mean(), (calm[5] < 1).mean() * 3)

    def test_spells_last_at_least_one_month_for_both_distributions(self):
        for dist in ("lognormal", "poisson"):
            job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.5, mean_duration=1.0, distribution=dist)
            caps = E.simulate_unemployment(np.zeros((36, 2_000)), 1.0, job, np.random.RandomState(2))
            self.assertGreater((caps < 1).sum(), 0, dist)


class ScenarioParsingTests(unittest.TestCase):
    def test_parses_comma_separated_percentages(self):
        self.assertEqual(E.parse_annual_returns("5, 10,-20 , 1.5"), (5.0, 10.0, -20.0, 1.5))

    def test_rejects_garbage_empty_and_total_loss(self):
        for bad in ("abc", "", " , ", "5, x", "-100", "nan", "inf"):
            with self.assertRaises(ValueError, msg=bad):
                E.parse_annual_returns(bad)

    def test_future_path_repeats_its_last_year_to_fill_the_term(self):
        monthly = E._future_monthly_returns((12.0, -6.0), 40)
        self.assertEqual(len(monthly), 48)
        self.assertAlmostEqual(np.prod(1 + monthly[:12]), 1.12)
        np.testing.assert_allclose(monthly[24:36], monthly[12:24])


if __name__ == '__main__':
    unittest.main()
