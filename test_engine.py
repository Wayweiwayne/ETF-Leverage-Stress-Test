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

    def test_initial_purchase_pays_the_trading_fee(self):
        res = one_path([0.0], [0.0], (E.SALARY,), fee=0.01, buffer_cash=100_000)
        self.assertAlmostEqual(res.ledger['shares_a'][0, 0], 900_000 * 0.99 / 100)
        # bought net of the fee, valued net of the fee to sell, plus the untouched buffer
        self.assertAlmostEqual(res.lev_final[0], 900_000 * 0.99 * 0.99 + 100_000)

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
        self.assertEqual(int((~trace['projected']).sum()), 9)
        self.assertEqual(trace['date'].iloc[0], df.index[31])
        self.assertEqual(trace['date'].iloc[9], df.index[-1] + pd.DateOffset(months=1))

    def test_entry_buys_at_that_months_price_and_earns_the_following_months(self):
        # Month 5 itself gained 50%; someone entering at the end of it must not be credited with that.
        df = market(flat=True, with_b=False)
        ret = np.zeros(len(df))
        ret[5], ret[6], ret[7] = 0.50, 0.10, -0.20
        df['Price_Return_A'] = ret
        df['Close_A'] = 20 * np.cumprod(1 + ret)
        p = params(reinvest=False, salary_cap=1e9, source_order=(E.SALARY,), fee=0.0)
        trace = E.run(df, p, anchor_idx=5).trace
        np.testing.assert_allclose(trace['lev_value'].iloc[:3], [5_500_000, 4_400_000, 4_400_000])
        self.assertEqual(trace['date'].iloc[0], df.index[6])
        np.testing.assert_allclose(E.run(df, p, anchor_idx=4).trace['lev_value'].iloc[:2], [7_500_000, 8_250_000])

    def test_latest_month_can_be_an_entry_and_is_all_scenario(self):
        df = market(n=100)
        res = E.run(df, params(), anchor_idx=99)
        self.assertEqual(len(res.hist), 100)
        self.assertEqual(int((~res.hist['Is_Spliced']).sum()), 100 - 84)   # entries with 84 real months ahead
        self.assertTrue(res.trace['projected'].all())
        self.assertEqual(res.trace['date'].iloc[0], df.index[-1] + pd.DateOffset(months=1))

    def test_summary_does_not_depend_on_the_entry_month_being_traced(self):
        df = market()
        a, b = E.run(df, params(), 5), E.run(df, params(), 60)
        pd.testing.assert_frame_equal(a.mc, b.mc)
        pd.testing.assert_frame_equal(a.hist, b.hist)
        self.assertFalse(a.trace['lev_value'].equals(b.trace['lev_value']))
        self.assertIsNone(E.run_summary(df, params()).trace)

    def test_monte_carlo_ignores_the_price_level(self):
        df = market()
        scaled = df.assign(Close_A=df['Close_A'] * 37, Close_B=df['Close_B'] / 11)
        pd.testing.assert_frame_equal(E.run_summary(df, params()).mc, E.run_summary(scaled, params()).mc,
                                      check_exact=False, rtol=1e-9)

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


class SecondAssetModelTests(unittest.TestCase):
    """Months in which the second asset has no real data: before it existed and in the scenario."""

    def paired(self, n=120, alpha=0.02, missing=0, noise=0.0):
        df = market(n=n)
        rng = np.random.RandomState(9)
        ret_b = 2 * df['Price_Return_A'] + alpha + rng.normal(0, noise, n)
        df['Price_Return_B'] = ret_b
        df['Close_B'] = 30 * np.cumprod(1 + ret_b)
        if missing:
            df.iloc[:missing, [df.columns.get_loc('Price_Return_B'), df.columns.get_loc('Close_B')]] = np.nan
        return df

    def test_linear_form_is_beta_times_the_main_asset(self):
        r = np.array([-0.2, 0.0, 0.1])
        np.testing.assert_allclose(E.modelled_second_asset_return(r, 0.0, 2.0, 0.0, False), [-0.4, 0.0, 0.2])

    def test_compounding_form_follows_the_leveraged_fund_formula(self):
        r = np.array([-0.2, 0.0, 0.1])
        out = E.modelled_second_asset_return(r, 0.0, 2.0, 0.003, True)
        np.testing.assert_allclose(out, (1 + r) ** 2 * np.exp(-0.003) - 1)
        self.assertLess(out[1], 0)                    # a flat month costs the decay
        self.assertGreater(out[0], -0.4)              # a 20% fall costs less than twice 20%

    def test_modelled_return_never_goes_below_total_loss(self):
        out = E.modelled_second_asset_return(np.array([-0.9, -1.0]), np.array([-0.5, 0.0]), 2.0, 0.0, False)
        np.testing.assert_array_equal(out, [-1.0, -1.0])

    def test_decay_is_half_beta_beta_minus_one_times_variance(self):
        df = self.paired()
        res = E.run_summary(df, params())
        self.assertAlmostEqual(res.beta_b, 2.0, places=6)
        self.assertAlmostEqual(res.vol_drag, 0.5 * 2.0 * 1.0 * df['Price_Return_A'].var(), places=10)
        self.assertEqual(E.run_summary(df, params(vol_drag=False)).vol_drag, 0)

    def test_no_decay_for_an_unleveraged_second_asset(self):
        df = market()
        df['Price_Return_B'] = 0.8 * df['Price_Return_A']
        df['Close_B'] = 30 * np.cumprod(1 + df['Price_Return_B'])
        self.assertEqual(E.run_summary(df, params()).vol_drag, 0)

    def test_sample_outperformance_is_not_projected_into_the_scenario(self):
        # The second asset beat twice the first by 2% a month in the record. In a flat scenario
        # it must stay flat rather than keep that edge.
        df = self.paired(alpha=0.02)
        p = params(vol_drag=False, future_annual_returns=(0.0,))
        m = E._prepare_market(df, p)
        ret_a, ret_b, _, win_lens, _ = E._history_paths(m, p)
        last = len(df) - 1                              # entering in the latest month: all scenario
        self.assertEqual(win_lens[last], 0)
        np.testing.assert_allclose(ret_a[:, last], 0, atol=1e-12)
        np.testing.assert_allclose(ret_b[:, last], 0, atol=1e-9)

    def test_scenario_months_with_decay_lose_exactly_the_decay(self):
        df = self.paired()
        p = params(future_annual_returns=(0.0,))
        m = E._prepare_market(df, p)
        _, ret_b, _, _, _ = E._history_paths(m, p)
        np.testing.assert_allclose(ret_b[:, -1], np.exp(-m.decay) - 1, atol=1e-9)

    def test_months_before_the_second_asset_existed_are_modelled_from_the_first(self):
        df = self.paired(missing=40)
        p = params(vol_drag=False)
        m = E._prepare_market(df, p)
        self.assertEqual(m.modelled_b_months, 40)
        np.testing.assert_allclose(m.ret_b[:40], 2 * m.ret_a[:40], atol=1e-9)
        np.testing.assert_allclose(m.ret_b[40:], df['Price_Return_B'].iloc[40:])
        res = E.run(df, p, 3)
        self.assertEqual(res.modelled_b_months, 40)
        self.assertEqual(len(res.hist), len(df))
        self.assertFalse(res.hist.drop(columns='Lev_Final_Survivors').isna().any().any())
        self.assertFalse(res.mc.isna().any().any())
        self.assertFalse(res.trace.isna().any().any())

    def test_modelled_months_scatter_like_the_real_relationship(self):
        df = self.paired(missing=60, noise=0.03)
        m = E._prepare_market(df, params(vol_drag=False))
        self.assertAlmostEqual(m.resid_std_b, 0.03, delta=0.008)
        self.assertAlmostEqual(np.std(m.ret_b[:60] - m.beta_b * m.ret_a[:60]), 0.03, delta=0.01)

    def test_too_little_overlap_falls_back_to_tracking_one_for_one(self):
        df = self.paired(missing=115)
        m = E._prepare_market(df, params())
        self.assertEqual((m.beta_b, m.resid_std_b, m.decay), (1.0, 0.0, 0.0))

    def test_second_asset_with_no_data_at_all_is_ignored(self):
        df = self.paired(missing=120)
        res = E.run(df, params(), 5)
        self.assertEqual(res.trace['shares_b'].abs().sum(), 0)
        self.assertEqual(res.modelled_b_months, 0)

    def test_entry_months_relying_on_proxy_data_are_marked(self):
        df = market(n=100)
        df['Synthetic_A'] = np.arange(100) < 30          # the first 30 months come from a proxy
        hist = E.run_summary(df, params(total_months=12)).hist
        # entries 0..29 start on a proxied price; later ones use only real months
        self.assertEqual(hist['Is_Backfilled'].tolist(), [True] * 30 + [False] * 70)


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

    def test_history_averages_many_unemployment_draws_per_entry_month(self):
        # Salary is the only source, so an entry month fails exactly when a job loss lands on it.
        df = market(n=50, with_b=False)
        job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.10, mean_duration=3.0)
        p = params(reinvest=False, salary_cap=1e9, source_order=(E.SALARY,), job_loss=job, total_months=24)
        res = E.run_summary(df, p)
        self.assertEqual(res.hist_replicates, 100)
        prob = res.hist['Ruin_Prob']
        expected = 1 - 0.9 ** 2                           # at least one spell in two years
        self.assertTrue(((prob > 0) & (prob < 1)).all())
        self.assertAlmostEqual(prob.mean(), expected, delta=0.03)
        self.assertLess(prob.std(), 0.08)                 # no entry month hinges on a single draw
        pd.testing.assert_frame_equal(res.hist, E.run_summary(df, p).hist)

    def test_replicates_are_capped_by_total_paths(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.10)
        self.assertEqual(E.run_summary(market(n=250), params(job_loss=job)).hist_replicates, 40)

    def test_without_random_job_loss_each_entry_month_is_simulated_once(self):
        res = E.run_summary(market(), params(salary_cap=20_000.0, swan_month=6, swan_drop=0.3))
        self.assertEqual(res.hist_replicates, 1)
        self.assertTrue(res.hist['Ruin_Prob'].isin([0.0, 1.0]).all())
        self.assertTrue(res.hist['Lev_Win'].isin([0.0, 1.0]).all())
        survived = ~res.hist['Is_Ruined']
        np.testing.assert_allclose(res.hist.loc[survived, 'Lev_Final_Survivors'], res.hist.loc[survived, 'Lev_Final'])
        self.assertTrue(res.hist.loc[~survived, 'Lev_Final_Survivors'].isna().all())

    def test_ledger_follows_one_of_the_unemployment_draws(self):
        job = E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.3, mean_duration=4.0, unemployed_salary=1_000.0)
        trace = E.run(market(), params(job_loss=job, salary_cap=30_000.0, source_order=(E.SALARY, E.SELL)), 10).trace
        self.assertTrue(trace['from_salary'].isin([1_000.0, 30_000.0]).all())
        self.assertTrue((trace['from_salary'] == 1_000.0).any())

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
