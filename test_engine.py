import dataclasses
import math
import unittest
from unittest import mock

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


class ReturnAndRangeTests(unittest.TestCase):
    def test_irr_recovers_a_known_rate(self):
        monthly = 1.01                                              # 1% a month
        paid = np.full((24, 1), 1_000.0)
        final = (1_000.0 * monthly ** np.arange(23, -1, -1)).sum()   # each payment grows until the end
        self.assertAlmostEqual(E.annual_irr(paid, np.array([final]))[0], monthly ** 12 - 1, places=6)

    def test_irr_handles_the_edge_cases(self):
        paid = np.column_stack([np.full(12, 100.0), np.full(12, 100.0), np.zeros(12), np.full(12, 100.0)])
        out = E.annual_irr(paid, np.array([1_200.0, 0.0, 500.0, 600.0]))
        self.assertAlmostEqual(out[0], 0.0, places=6)               # got back exactly what went in
        self.assertEqual(out[1], -1.0)                              # nothing left
        self.assertTrue(np.isnan(out[2]))                           # nothing paid in
        self.assertLess(out[3], -0.5)                               # half lost within a year

    def test_irr_ranks_paths_like_their_outcomes(self):
        paid = np.full((36, 3), 1_000.0)
        out = E.annual_irr(paid, np.array([30_000.0, 36_000.0, 45_000.0]))
        self.assertTrue(out[0] < 0 < out[2])
        self.assertAlmostEqual(out[1], 0.0, places=6)

    def test_out_of_pocket_totals_are_tracked_for_both_strategies(self):
        res = one_path([0.0] * 5, [10_000] * 5, (E.SALARY, E.SELL), salary_cap=4_000)
        self.assertAlmostEqual(res.out_of_pocket[0], 20_000)
        self.assertAlmostEqual(res.dca_invested[0], 20_000)
        full = one_path([0.0] * 5, [10_000] * 5, (E.SALARY, E.SELL), salary_cap=4_000, dca_mode=E.DCA_FULL_PAYMENT)
        self.assertAlmostEqual(full.dca_invested[0], 50_000)

    def test_monthly_quantiles_and_flows_are_returned_on_request(self):
        months, n = 6, 5
        ret = np.tile(np.array([-0.5, -0.1, 0.0, 0.1, 0.5]), (months, 1)) * (np.arange(months)[:, None] == 0)
        res = E.simulate_paths(ret, np.zeros((months, n)), np.zeros((months, n)), np.full(n, 100.0), np.ones(n),
                               np.full(months, 1_000.0), principal=1_000_000.0, buffer_cash=0.0, fee=0.0,
                               reinvest=False, ratio_b=0.0, order=(E.SALARY,), salary_cap=np.full((months, n), 1_000.0),
                               quantiles=(0.0, 0.5, 1.0), keep_flows=True)
        np.testing.assert_allclose(res.value_quantiles["lev"][0], [500_000, 1_000_000, 1_500_000])
        np.testing.assert_allclose(res.value_quantiles["alive"], 1.0)
        self.assertEqual(res.flows["salary"].shape, (months, n))
        np.testing.assert_allclose(res.flows["salary"], 1_000.0)
        plain = one_path([0.0], [0.0], (E.SALARY,))
        self.assertIsNone(plain.value_quantiles)
        self.assertIsNone(plain.flows)

    def test_ruined_paths_count_as_zero_in_the_range(self):
        ret = np.zeros((3, 4))
        caps = np.tile(np.array([0.0, 0.0, 5_000.0, 5_000.0]), (3, 1))      # two paths cannot pay at all
        res = E.simulate_paths(ret, ret, ret, np.full(4, 100.0), np.ones(4), np.full(3, 1_000.0),
                               principal=1_000_000.0, buffer_cash=0.0, fee=0.0, reinvest=False, ratio_b=0.0,
                               order=(E.SALARY,), salary_cap=caps, quantiles=(0.0, 1.0))
        np.testing.assert_allclose(res.value_quantiles["lev"][:, 0], 0.0)
        np.testing.assert_allclose(res.value_quantiles["lev"][:, 1], 1_000_000)
        np.testing.assert_allclose(res.value_quantiles["alive"], 0.5)

    def test_summary_carries_the_range_and_the_returns(self):
        res = E.run_summary(market(), params(salary_cap=8_000.0, swan_month=6, swan_drop=0.3))
        fan, mc = res.mc_fan, res.mc
        self.assertEqual(len(fan), 84)
        self.assertEqual(fan['month'].tolist(), list(range(1, 85)))
        ordered = fan[['lev_p5', 'lev_p25', 'lev_p50', 'lev_p75', 'lev_p95']].to_numpy()
        self.assertTrue((np.diff(ordered, axis=1) >= 0).all())
        np.testing.assert_allclose(fan['loan_balance'], res.schedule.end_balance)
        self.assertAlmostEqual(fan['alive'].iloc[-1], 1 - mc['Is_Ruined'].mean())
        self.assertAlmostEqual(fan['lev_p50'].iloc[-1], mc['Lev_Final'].median(), delta=1.0)
        self.assertTrue((np.diff(fan['alive']) <= 1e-12).all())            # ruin is permanent
        self.assertTrue((mc['Out_Of_Pocket'] <= 8_000.0 * 84 + 1e-6).all())
        self.assertTrue((mc.loc[mc['Is_Ruined'] & (mc['Out_Of_Pocket'] > 0), 'Lev_IRR'] == -1.0).all())
        survivors = mc[~mc['Is_Ruined']]
        self.assertGreater(np.corrcoef(survivors['Lev_Final'], survivors['Lev_IRR'])[0, 1], 0.5)

    def test_no_range_without_a_monte_carlo(self):
        res = E.run_summary(market(n=1), params(total_months=12))
        self.assertIsNone(res.mc_fan)
        self.assertIn('Lev_IRR', res.mc.columns)


class FloatingRateTests(unittest.TestCase):
    def test_rate_path_changes_apply_from_the_second_year_and_accumulate(self):
        rates = E.annual_rate_path(3.0, 60, rate_path_pct=(0.25, 0.25, -0.75))
        np.testing.assert_allclose(rates[[0, 11, 12, 23, 24, 35, 36, 59]], [3, 3, 3.25, 3.25, 3.5, 3.5, 2.75, 2.75])

    def test_rate_path_adds_to_a_one_off_shock_and_never_goes_negative(self):
        rates = E.annual_rate_path(1.0, 48, shock_year=2, shock_delta_pct=1.0, rate_path_pct=(0.5, -5.0))
        np.testing.assert_allclose(rates[[0, 12, 24, 47]], [1.0, 2.5, 0.0, 0.0])

    def test_payment_is_reset_when_the_rate_moves_and_the_loan_still_clears(self):
        fixed = E.build_loan_schedule(1_000_000, 3.0, 120)
        floating = E.build_loan_schedule(1_000_000, 3.0, 120, rate_path_pct=(0.5, 0.5, 0.0, -0.25))
        np.testing.assert_allclose(floating.payments[:12], fixed.payments[:12])
        steps = floating.payments[[12, 24, 36, 48]] - floating.payments[[11, 23, 35, 47]]
        self.assertTrue(steps[0] > 0 and steps[1] > 0 and abs(steps[2]) < 1e-6 and steps[3] < 0)
        for year in range(10):                                   # level within every loan year
            np.testing.assert_allclose(floating.payments[year * 12:(year + 1) * 12], floating.payments[year * 12])
        self.assertAlmostEqual(floating.end_balance[-1], 0.0, places=4)
        np.testing.assert_allclose(floating.monthly_rates[12] * 1200, 3.5)

    def test_rising_rate_during_grace_raises_the_interest_only_payment(self):
        s = E.build_loan_schedule(1_000_000, 3.0, 120, grace_months=36, rate_path_pct=(1.0,))
        self.assertAlmostEqual(s.payments[11], 1_000_000 * 0.03 / 12)
        self.assertAlmostEqual(s.payments[12], 1_000_000 * 0.04 / 12)
        self.assertAlmostEqual(s.end_balance[-1], 0.0, places=4)

    def test_each_path_gets_its_own_schedule(self):
        rates = np.column_stack([np.full(60, 3.0), E.annual_rate_path(3.0, 60, rate_path_pct=(1.0, 1.0))])
        both = E.schedule_from_rates(500_000, rates, 0)
        np.testing.assert_allclose(both.payments[:, 0], E.build_loan_schedule(500_000, 3.0, 60).payments)
        np.testing.assert_allclose(both.payments[:, 1],
                                   E.build_loan_schedule(500_000, 3.0, 60, rate_path_pct=(1.0, 1.0)).payments)
        np.testing.assert_allclose(both.end_balance[-1], 0.0, atol=1e-4)

    def test_random_rate_paths_wander_around_the_set_path(self):
        p = params(total_months=120, annual_rate_pct=3.0, rate_path_pct=(0.5,), rate_volatility_pct=0.25)
        rates = E.monte_carlo_rate_paths(p, np.random.RandomState(0), 20_000)
        base = E.annual_rate_path(3.0, 120, rate_path_pct=(0.5,))
        self.assertEqual(rates.shape, (120, 20_000))
        np.testing.assert_allclose(rates[:12], 3.0)                       # the first year's rate is the contract rate
        self.assertTrue((rates[12:24] == rates[12]).all())                # one move per loan year
        self.assertAlmostEqual(rates[-1].mean(), base[-1], delta=0.02)
        self.assertAlmostEqual(rates[-1].std(), 0.25 * 9 ** 0.5, delta=0.02)   # nine yearly moves accumulate
        self.assertGreater((rates[12] != rates[24]).mean(), 0.99)

    def test_without_volatility_there_is_one_shared_path(self):
        rates = E.monte_carlo_rate_paths(params(rate_path_pct=(0.25,)), np.random.RandomState(0), 50)
        np.testing.assert_allclose(rates, E.annual_rate_path(3.5, 84, rate_path_pct=(0.25,)))

    def test_random_rates_never_go_below_zero(self):
        p = params(annual_rate_pct=0.5, rate_volatility_pct=2.0)
        self.assertGreaterEqual(E.monte_carlo_rate_paths(p, np.random.RandomState(1), 2_000).min(), 0.0)

    def test_rate_randomness_reaches_only_the_monte_carlo(self):
        df = market()
        calm = E.run_summary(df, params(salary_cap=10_000.0))
        wild = E.run_summary(df, params(salary_cap=10_000.0, rate_volatility_pct=1.5))
        pd.testing.assert_frame_equal(calm.hist, wild.hist)
        self.assertFalse(calm.mc['Lev_Final'].equals(wild.mc['Lev_Final']))
        self.assertEqual(calm.mc_final_rate_p5, calm.mc_final_rate_p95)
        self.assertLess(wild.mc_final_rate_p5, 3.5)
        self.assertGreater(wild.mc_final_rate_p95, 3.5)
        pd.testing.assert_frame_equal(wild.mc, E.run_summary(df, params(salary_cap=10_000.0, rate_volatility_pct=1.5)).mc)

    def test_rising_rates_cannot_make_things_safer(self):
        df = market()
        stressed = dict(salary_cap=8_000.0, swan_month=6, swan_drop=0.3)
        flat = E.run_summary(df, params(**stressed))
        rising = E.run_summary(df, params(rate_path_pct=(1.0, 1.0, 1.0), **stressed))
        self.assertTrue((rising.hist['Ruin_Prob'] >= flat.hist['Ruin_Prob']).all())
        self.assertGreater(rising.mc['Is_Ruined'].mean(), flat.mc['Is_Ruined'].mean())
        self.assertGreater(rising.schedule.payments[-1], flat.schedule.payments[-1])

    def test_ledger_shows_the_rate_of_each_month(self):
        trace = E.run_trace(market(), params(salary_cap=1e9, rate_path_pct=(0.5,)), 5)
        np.testing.assert_allclose(trace['annual_rate_pct'].iloc[[0, 11, 12, 83]], [3.5, 3.5, 4.0, 4.0])

    def test_rate_path_text(self):
        self.assertEqual(E.parse_rate_path("0.25, 0.25,-0.125"), (0.25, 0.25, -0.125))
        self.assertEqual(E.parse_rate_path(" "), ())
        for bad in ("up", "0.25, x", "50", "nan"):
            with self.assertRaises(ValueError, msg=bad):
                E.parse_rate_path(bad)


class TaxAndFeeTests(unittest.TestCase):
    """10,000 shares bought at 100; a 2% yield pays 20,000."""

    def test_sales_pay_the_transaction_tax_on_top_of_the_fee(self):
        res = one_path([0.0], [9_000], (E.SELL,), fee=0.002, sell_tax=0.001)
        bought = 1_000_000 * (1 - 0.002) / 100                         # buying pays the fee only
        self.assertAlmostEqual(res.ledger['shares_a'][0, 0], bought - 9_000 / (1 - 0.003) / 100)
        self.assertAlmostEqual(res.lev_final[0], res.ledger['shares_a'][0, 0] * 100 * (1 - 0.003))

    def test_dividend_income_tax_is_withheld_from_every_payout(self):
        res = one_path([0.0], [0.0], (E.SALARY,), div_yield=0.02, dividend_tax_rate=0.035)
        self.assertAlmostEqual(res.ledger['dividend_tax'][0, 0], 700)
        self.assertAlmostEqual(res.lev_final[0], 1_000_000 + 20_000 - 700)

    def test_health_levy_applies_only_from_the_threshold_up(self):
        at = one_path([0.0], [0.0], (E.SALARY,), div_yield=0.02, nhi_rate=0.0211, nhi_threshold=20_000)
        below = one_path([0.0], [0.0], (E.SALARY,), div_yield=0.0199, nhi_rate=0.0211, nhi_threshold=20_000)
        self.assertAlmostEqual(at.ledger['dividend_tax'][0, 0], 20_000 * 0.0211)
        self.assertEqual(below.ledger['dividend_tax'][0, 0], 0)

    def test_only_the_dividend_income_part_of_a_payout_is_taxed(self):
        res = one_path([0.0], [0.0], (E.SALARY,), div_yield=0.03, dividend_tax_rate=0.10, nhi_rate=0.0211,
                       nhi_threshold=20_000, dividend_taxable_share=0.5)
        self.assertAlmostEqual(res.ledger['dividend_tax'][0, 0], 15_000 * 0.10)   # 15,000 taxable: under the levy threshold

    def test_reinvested_dividends_are_reinvested_net_of_tax(self):
        res = one_path([0.0], [0.0], (E.SALARY,), div_yield=0.02, dividend_tax_rate=0.5, reinvest=True, ratio_b=0.0)
        self.assertAlmostEqual(res.ledger['shares_a'][0, 0], 10_000 + 10_000 / 100)

    def test_comparison_portfolio_is_taxed_on_its_own_smaller_payouts(self):
        # It invests 4,000 a month, so its dividends stay far below the levy threshold; the leveraged side's do not.
        kwargs = dict(returns=[0.0] * 6, payments=[10_000] * 6, order=(E.SALARY, E.SELL), salary_cap=4_000, div_yield=0.02)
        plain = one_path(**kwargs)
        levied = one_path(nhi_rate=0.0211, nhi_threshold=20_000, **kwargs)
        np.testing.assert_allclose(levied.dca_final, plain.dca_final)
        self.assertLess(levied.lev_final[0], plain.lev_final[0])
        taxed = one_path(dividend_tax_rate=0.2, **kwargs)
        self.assertLess(taxed.dca_final[0], plain.dca_final[0])

    def test_loan_fee_comes_out_of_what_is_invested(self):
        res = one_path([0.0], [0.0], (E.SALARY,), loan_fee=6_000, buffer_cash=100_000)
        self.assertAlmostEqual(res.ledger['shares_a'][0, 0], (1_000_000 - 100_000 - 6_000) / 100)

    def test_buffer_cannot_exceed_the_loan_less_the_fee(self):
        res = E.run_summary(market(n=30), params(total_months=12, buffer_months=12, loan_fee=50_000.0, principal=1_000_000.0))
        self.assertAlmostEqual(res.buffer_cash, 950_000)

    def test_taxes_lower_the_outcome_for_both_strategies(self):
        df = market()
        free = E.run_summary(df, params())
        taxed = E.run_summary(df, params(sell_tax=0.001, dividend_tax_rate=0.035, nhi_rate=0.0211))
        self.assertLess(taxed.mc['Lev_Final'].median(), free.mc['Lev_Final'].median())
        self.assertLess(taxed.mc['DCA_Final'].median(), free.mc['DCA_Final'].median())
        self.assertGreaterEqual(taxed.mc['Is_Ruined'].mean(), free.mc['Is_Ruined'].mean())

    def test_ledger_records_what_each_payout_lost(self):
        trace = E.run_trace(market(with_b=False), params(reinvest=False, dividend_tax_rate=0.10, salary_cap=1e9,
                                                          source_order=(E.SALARY,)), 8)
        paying = trace['dividend_tax'] > 0
        self.assertEqual(int(paying.sum()), 28)                         # the fixture pays every third month
        self.assertTrue((trace.loc[~paying, 'dividend_tax'] == 0).all())


class DividendFrequencyTests(unittest.TestCase):
    def test_lumping_moves_the_same_cash_into_fewer_payouts(self):
        np.testing.assert_allclose(E.lump_dividends(np.ones(7), 3), [0, 0, 3, 0, 0, 3, 0])
        np.testing.assert_allclose(E.lump_dividends(np.ones(12), 12), [0] * 11 + [12])
        monthly = np.arange(1.0, 7.0)
        self.assertIs(E.lump_dividends(monthly, 1), monthly)

    def test_lumping_works_across_many_paths(self):
        out = E.lump_dividends(np.arange(12.0).reshape(6, 2), 6)
        np.testing.assert_allclose(out[:5], 0)
        np.testing.assert_allclose(out[5], [60, 66])

    def test_frequency_is_read_from_the_latest_record(self):
        def record(every, months=60):
            y = np.zeros(months)
            y[every - 1::every] = 0.01
            return y
        self.assertEqual([E.infer_dividend_interval(record(k)) for k in (1, 3, 6, 12)], [1, 3, 6, 12])
        self.assertEqual(E.infer_dividend_interval(np.zeros(60)), 1)
        switched = np.concatenate([record(12, 120), record(3, 36)])     # went quarterly three years ago
        self.assertEqual(E.infer_dividend_interval(switched), 3)

    def test_modelled_yield_pays_the_same_per_year_at_any_frequency(self):
        flat = np.full((24, 1), 50.0)
        totals = [E.dividend_model_yields(flat, 50.0, 0.06, 0.0, interval=k).sum() for k in (1, 3, 6, 12)]
        np.testing.assert_allclose(totals, 0.12)
        quarterly = E.dividend_model_yields(flat, 50.0, 0.06, 0.0, interval=3)[:, 0]
        np.testing.assert_allclose(quarterly[:6], [0, 0, 0.015, 0, 0, 0.015])

    def test_scenario_months_follow_the_chosen_frequency(self):
        df = market(n=40)
        for interval in (1, 3, 6, 12):
            p = params(dividend_interval_months=interval, future_annual_returns=(0.0,))
            m = E._prepare_market(df, p)
            _, _, div_a, win_lens, _ = E._history_paths(m, p)
            scenario = div_a[:, -1]                                  # entering in the latest month: all scenario
            self.assertEqual(win_lens[-1], 0)
            self.assertEqual(int((scenario > 0).sum()), 84 // interval)
            self.assertAlmostEqual(scenario[:12 * (84 // 12)].sum() / 7, 0.06, places=6)

    def test_automatic_frequency_matches_the_asset(self):
        df = market()                                                # pays every third month
        self.assertEqual(E.run_summary(df, params(dividend_interval_months=0)).dividend_interval, 3)
        self.assertEqual(E.run_summary(df, params(dividend_interval_months=6)).dividend_interval, 6)
        self.assertEqual(E.run_summary(df, params()).dividend_interval, 1)

    def test_assumed_yield_monte_carlo_follows_the_frequency_too(self):
        df = market()
        p = params(mc_dividends=E.MC_DIVIDENDS_MODEL, dividend_interval_months=3)
        _, _, div_a = E.monte_carlo_inputs(E._prepare_market(df, p), p, np.random.RandomState(0))
        self.assertTrue((div_a[[0, 1, 3, 4]] == 0).all())
        self.assertTrue((div_a[[2, 5]] > 0).all())

    def test_bigger_payouts_cross_the_health_levy_threshold(self):
        monthly = one_path([0.0] * 3, [0.0] * 3, (E.SALARY,), div_yield=0.015, nhi_rate=0.0211, nhi_threshold=20_000)
        quarterly = one_path([0.0] * 3, [0.0] * 3, (E.SALARY,), div_yield=[0.0, 0.0, 0.045],
                             nhi_rate=0.0211, nhi_threshold=20_000)
        self.assertEqual(monthly.ledger['dividend_tax'].sum(), 0)                 # 15,000 a month stays under
        self.assertAlmostEqual(quarterly.ledger['dividend_tax'].sum(), 45_000 * 0.0211)


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

    def test_dividend_cash_does_not_depend_on_the_months_price_move(self):
        # 10,000 shares bought at 100 with a 2% payout: 20,000 in cash whether the price then rises or falls.
        for move in (0.5, 0.0, -0.5):
            res = one_path([move], [25_000], (E.DIVIDEND, E.SALARY), salary_cap=1e9, div_yield=0.02)
            self.assertAlmostEqual(res.ledger['from_dividend'][0, 0], 20_000, msg=move)
            self.assertAlmostEqual(res.ledger['from_salary'][0, 0], 5_000, msg=move)

    def test_month_of_ruin_is_recorded(self):
        res = one_path([0.0] * 4, [3_000, 3_000, 9_000, 3_000], (E.SALARY,), salary_cap=4_000)
        self.assertEqual(res.ruin_month[0], 3)
        self.assertEqual(one_path([0.0] * 4, [3_000] * 4, (E.SALARY,), salary_cap=4_000).ruin_month[0], 0)

    def second_asset_path(self, order, returns=(0.0, 0.0), payment=15_000, **kwargs):
        """All dividends (2% a month = 20,000) are reinvested into the second asset, priced at 1."""
        return one_path(list(returns), [payment] * len(returns), order, div_yield=0.02,
                        reinvest=True, ratio_b=1.0, **kwargs)

    def test_second_asset_is_sold_when_ranked(self):
        res = self.second_asset_path((E.SELL_B,))
        self.assertFalse(res.ruined[0])
        np.testing.assert_allclose(res.ledger['from_sell_b'][:, 0], [15_000, 15_000])
        np.testing.assert_allclose(res.ledger['shares_b'][:, 0], [5_000, 10_000])   # +20,000 bought, -15,000 sold
        np.testing.assert_allclose(res.ledger['shares_a'][:, 0], 10_000)            # main asset untouched

    def test_second_asset_left_out_of_the_order_is_not_sold_even_at_ruin(self):
        res = self.second_asset_path((E.SALARY,), salary_cap=0.0)
        self.assertTrue(res.ruined[0])
        self.assertEqual(res.ledger['from_sell_b'].sum(), 0)
        self.assertAlmostEqual(res.ledger['shares_b'][0, 0], 20_000)

    def test_main_asset_goes_first_when_ranked_ahead_of_the_second(self):
        res = self.second_asset_path((E.SELL, E.SELL_B))
        np.testing.assert_allclose(res.ledger['from_sell'][:, 0], [15_000, 15_000])
        self.assertEqual(res.ledger['from_sell_b'].sum(), 0)

    def test_second_asset_covers_what_the_first_sources_cannot(self):
        res = self.second_asset_path((E.SALARY, E.SELL_B), salary_cap=4_000)
        np.testing.assert_allclose(res.ledger['from_salary'][:, 0], [4_000, 4_000])
        np.testing.assert_allclose(res.ledger['from_sell_b'][:, 0], [11_000, 11_000])

    def test_second_asset_running_out_is_ruin(self):
        res = self.second_asset_path((E.SELL_B,), payment=25_000)      # only 20,000 arrives each month
        self.assertTrue(res.ruined[0])
        self.assertEqual(res.ruin_month[0], 1)

    def test_crash_haircut_applies_to_the_second_asset_too(self):
        plain = self.second_asset_path((E.SELL_B,), returns=(-0.3,), payment=9_000)
        hit = self.second_asset_path((E.SELL_B,), returns=(-0.3,), payment=9_000,
                                     haircut_trigger=0.2, haircut_penalty=0.1)
        self.assertAlmostEqual(plain.ledger['shares_b'][0, 0], 20_000 - 9_000)
        self.assertAlmostEqual(hit.ledger['shares_b'][0, 0], 20_000 - 9_000 / 0.9)

    def test_dividends_meant_for_a_wiped_out_second_asset_buy_the_first_instead(self):
        months = 3
        col = lambda v: np.full((months, 1), float(v))
        ret_b = np.array([[-1.0], [0.0], [0.0]])            # the second asset goes to zero in month one
        res = E.simulate_paths(col(0.0), ret_b, col(0.02), np.array([100.0]), np.array([1.0]), np.zeros(months),
                               principal=1_000_000.0, buffer_cash=0.0, fee=0.0, reinvest=True, ratio_b=0.5,
                               order=(E.SALARY,), salary_cap=col(0.0), record=True)
        self.assertEqual(res.ledger['shares_b'].sum(), 0)
        # 2% of the holding is reinvested each month, all of it into the first asset: nothing vanishes
        np.testing.assert_allclose(res.ledger['shares_a'][:, 0], 10_000 * 1.02 ** np.arange(1, 4))
        self.assertAlmostEqual(res.lev_final[0], 1_000_000 * 1.02 ** 3)

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
            paid = trace[['from_dividend', 'from_buffer', 'from_sell', 'from_sell_b', 'from_salary']].sum(axis=1)
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

    def test_historical_dividends_are_paid_at_their_recorded_amount(self):
        # Entering at month 10's price, the first dividend is month 11's yield on that entry price,
        # however far the price moved during month 11.
        df = market(with_b=False)
        p = params(reinvest=False, salary_cap=1e9, source_order=(E.SALARY,), fee=0.0)
        for anchor in (8, 11, 14):
            trace = E.run_trace(df, p, anchor)
            shares = 5_000_000 / df['Close_A'].iloc[anchor]
            expected = shares * df['Div_Yield_A'].iloc[anchor + 1] * df['Close_A'].iloc[anchor]
            cash = trace['lev_value'].iloc[0] - shares * df['Close_A'].iloc[anchor + 1]
            self.assertAlmostEqual(cash, expected, places=4)
        self.assertGreater(df['Div_Yield_A'].iloc[9], 0)   # the fixture does pay in the months checked

    def test_modelled_dividend_yield_is_relative_to_the_previous_price(self):
        path = np.array([[110.0], [121.0]])
        yields = E.dividend_model_yields(path, 100.0, base_ann_yield=0.12, beta=0.0)   # 1.0 a month in cash
        np.testing.assert_allclose(yields[:, 0], [1 / 100, 1 / 110])

    def test_monte_carlo_records_when_each_path_failed(self):
        mc = E.run_summary(market(), params(salary_cap=5_000.0)).mc
        self.assertTrue(mc['Is_Ruined'].any() and (~mc['Is_Ruined']).any())
        self.assertTrue(((mc['Ruin_Month'] > 0) == mc['Is_Ruined']).all())
        self.assertTrue(mc['Ruin_Month'].between(0, 84).all())

    def test_selling_the_second_asset_can_only_reduce_ruin(self):
        df = market()
        without = (E.SALARY, E.DIVIDEND, E.BUFFER, E.SELL)
        stressed = dict(salary_cap=5_000.0, swan_month=6, swan_drop=0.3)
        old = E.run_summary(df, params(source_order=without, **stressed))
        new = E.run_summary(df, params(**stressed))                     # default order ends with the second asset
        self.assertEqual(params().source_order[-1], E.SELL_B)
        self.assertTrue((new.hist['Ruin_Prob'] <= old.hist['Ruin_Prob']).all())
        self.assertFalse((new.mc['Is_Ruined'] & ~old.mc['Is_Ruined']).any())
        self.assertLess(new.mc['Is_Ruined'].mean(), old.mc['Is_Ruined'].mean())
        self.assertGreater(old.mc['Is_Ruined'].mean(), 0.05)

    def test_ledger_shows_the_second_asset_being_sold_after_the_first_runs_out(self):
        df = market()
        # A 45% crash in the main asset alone leaves too little of it to see the loan through.
        df['Price_Return_A'] = df['Price_Return_A'].where(np.arange(len(df)) != 14, -0.45)
        df['Close_A'] = 20 * np.cumprod(1 + df['Price_Return_A'])
        p = params(salary_cap=0.0, source_order=(E.SELL, E.SELL_B), reinvest_ratio_b=1.0)
        trace = E.run_trace(df, p, 10)
        sold_b = trace['from_sell_b'] > 0
        self.assertTrue(sold_b.any())
        first = int(np.argmax(sold_b.to_numpy()))
        self.assertTrue((trace['from_sell'].iloc[first + 1:] < 1e-6).all())     # nothing left of the main asset
        self.assertAlmostEqual(trace['shares_a'].iloc[first], 0, places=6)

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


class BootstrapTests(unittest.TestCase):
    def test_shape_and_range(self):
        idx = E.bootstrap_indices(np.random.RandomState(0), n=50, block=12, months=84, n_paths=30)
        self.assertEqual(idx.shape, (84, 30))
        self.assertTrue(((idx >= 0) & (idx < 50)).all())

    def test_blocks_are_consecutive_months_wrapping_at_the_end(self):
        idx = E.bootstrap_indices(np.random.RandomState(1), n=50, block=12, months=84, n_paths=200)
        steps = np.diff(idx, axis=0) % 50
        within_block = np.ones(83, dtype=bool)
        within_block[11::12] = False                       # rows where one block ends and the next begins
        self.assertTrue((steps[within_block] == 1).all())
        self.assertTrue((idx[:-1][within_block] == 49).any(), "some block should run past the last month")

    def test_every_month_is_equally_likely_including_the_first_and_last(self):
        idx = E.bootstrap_indices(np.random.RandomState(2), n=40, block=12, months=120, n_paths=4000)
        counts = np.bincount(idx.ravel(), minlength=40)
        self.assertLess(counts.max() / counts.min(), 1.06)
        edges, middle = counts[[0, 1, 38, 39]].mean(), counts[15:25].mean()
        self.assertAlmostEqual(edges / middle, 1.0, delta=0.03)

    def test_block_longer_than_the_term_is_cut_to_the_term(self):
        self.assertEqual(E.bootstrap_indices(np.random.RandomState(3), 30, 24, 10, 5).shape, (10, 5))


class MonteCarloDividendTests(unittest.TestCase):
    def inputs(self, df, **overrides):
        p = params(**overrides)
        m = E._prepare_market(df, p)
        return m, E.monte_carlo_inputs(m, p, np.random.RandomState(0))

    def test_each_resampled_month_keeps_its_own_dividend(self):
        df = market(with_b=False)
        df['Div_Yield_A'] = np.linspace(0.001, 0.02, len(df))        # every month identifiable by its payout
        m, (ret_a, _, div_a) = self.inputs(df, reinvest=False)
        recorded = {round(r, 12): d for r, d in zip(m.ret_a, m.div_a)}
        expected = np.vectorize(lambda r: recorded[round(r, 12)])(ret_a)
        np.testing.assert_allclose(div_a, expected)
        self.assertEqual(div_a.shape, (84, 200))

    def test_default_is_the_recorded_dividend_and_ignores_the_assumed_yield(self):
        df = market()
        self.assertEqual(params().mc_dividends, E.MC_DIVIDENDS_HISTORY)
        low, high = (E.run_summary(df, params(base_div_yield=y)) for y in (0.0, 0.12))
        pd.testing.assert_frame_equal(low.mc, high.mc)
        self.assertAlmostEqual(low.mc_dividend_yield, df['Div_Yield_A'].mean() * 12, delta=0.004)

    def test_asset_that_never_paid_gets_no_dividends(self):
        df = market(with_b=False)
        df['Div_Yield_A'] = 0.0
        res = E.run_summary(df, params(reinvest=False, base_div_yield=0.06))
        self.assertEqual(res.mc_dividend_yield, 0.0)
        modelled = E.run_summary(df, params(reinvest=False, base_div_yield=0.06, mc_dividends=E.MC_DIVIDENDS_MODEL))
        self.assertGreater(modelled.mc_dividend_yield, 0.04)
        self.assertGreater(modelled.mc['Lev_Final'].median(), res.mc['Lev_Final'].median())

    def test_assumed_yield_mode_follows_the_slider(self):
        df = market()
        low, high = (E.run_summary(df, params(base_div_yield=y, mc_dividends=E.MC_DIVIDENDS_MODEL)) for y in (0.02, 0.10))
        self.assertLess(low.mc_dividend_yield, high.mc_dividend_yield)
        self.assertLess(low.mc['Lev_Final'].median(), high.mc['Lev_Final'].median())

    def test_scenario_beyond_the_record_still_uses_the_assumed_yield(self):
        # Entry months that run past the data are filled with the scenario, dividends included.
        df = market(n=40)
        low, high = (E.run_summary(df, params(base_div_yield=y)).hist for y in (0.0, 0.12))
        self.assertTrue(low['Is_Spliced'].all())
        self.assertLess(low['Lev_Final'].median(), high['Lev_Final'].median())

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            E.run_summary(market(n=30), params(mc_dividends="guess"))


class ValidationTests(unittest.TestCase):
    def test_sensible_settings_pass(self):
        E.validate_params(params())
        E.validate_params(params(job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.05)))

    def test_nonsense_is_rejected_before_anything_runs(self):
        bad = [
            dict(principal=0), dict(principal=-5e6), dict(principal=float('nan')), dict(annual_rate_pct=-1),
            dict(rate_shock_delta_pct=-10), dict(total_months=0), dict(grace_months=84), dict(grace_months=-1),
            dict(reinvest_ratio_b=1.5), dict(reinvest_ratio_b=-0.1), dict(fee=1.0), dict(fee=-0.01),
            dict(salary_cap=-1), dict(haircut_penalty=1.0), dict(swan_drop=1.5), dict(base_div_yield=-0.01),
            dict(future_annual_returns=()), dict(future_annual_returns=(5, -100)), dict(mc_paths=0),
            dict(mc_paths=10**7), dict(block_size=0), dict(dca_mode="all"), dict(source_order=("lottery",)),
            dict(rate_path_pct=(50.0,)), dict(rate_volatility_pct=-1), dict(rate_volatility_pct=9), dict(sell_tax=1.0),
            dict(dividend_tax_rate=1.2), dict(nhi_rate=-0.1), dict(dividend_tax_rate=0.6, nhi_rate=0.6),
            dict(dividend_taxable_share=1.5), dict(loan_fee=-1), dict(loan_fee=5e6), dict(dividend_interval_months=4),
            dict(job_loss=E.JobLossParams(mode="sometimes")),
            dict(job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=1.2)),
            dict(job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.1, mean_duration=0)),
            dict(job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.1, crash_extra_low=0.5,
                                          crash_extra_high=0.2)),
        ]
        df = market(n=30)
        for overrides in bad:
            with self.subTest(overrides), self.assertRaises(ValueError):
                E.run_summary(df, params(**overrides))


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


def mc_ruin(df, p, **overrides):
    """Monte Carlo ruin rate that run_summary reports for `p` with `overrides`."""
    return float(E.run_summary(df, dataclasses.replace(p, **overrides)).mc["Is_Ruined"].mean())


def evaluation_budget(lo, hi, step):
    return math.ceil(math.log2((hi - lo) / step)) + 3


def candidates(lo, hi, step):
    """Every value solve_for may return: the grid lo + k*step up to hi, then hi itself."""
    values = [lo + k * step for k in range(int((hi - lo) / step + 1e-9) + 1)]
    return values if math.isclose(values[-1], hi) else values + [hi]


class SolveForTests(unittest.TestCase):
    # At a 10% loan rate and 25,000 a month the safe loan sits around 10 million.
    df = market()
    p = params(annual_rate_pct=10.0)

    def test_largest_safe_principal_is_on_the_grid_and_one_step_more_is_unsafe(self):
        lo, hi, step = 1_000_000.0, 30_000_000.0, 1_000_000.0
        res = E.solve_for(self.df, self.p, "principal", 0.05, lo, hi, step)
        self.assertEqual((res.field, res.status, res.target), ("principal", "ok", 0.05))
        self.assertTrue(lo < res.value < hi)
        self.assertAlmostEqual((res.value - lo) / step, round((res.value - lo) / step))
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, self.p, principal=res.value))
        self.assertLessEqual(res.ruin_rate, 0.05)
        self.assertGreater(mc_ruin(self.df, self.p, principal=res.value + step), 0.05)
        self.assertLessEqual(res.evaluations, evaluation_budget(lo, hi, step))

    def test_smallest_safe_salary_cap_is_on_the_grid_and_one_step_less_is_unsafe(self):
        p = dataclasses.replace(self.p, principal=10_000_000.0)
        lo, hi, step = 0.0, 100_000.0, 1_000.0
        res = E.solve_for(self.df, p, "salary_cap", 0.05, lo, hi, step)
        self.assertEqual((res.field, res.status), ("salary_cap", "ok"))
        self.assertTrue(lo < res.value < hi)
        self.assertEqual(res.value % step, 0)
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, p, salary_cap=res.value))
        self.assertLessEqual(res.ruin_rate, 0.05)
        self.assertGreater(mc_ruin(self.df, p, salary_cap=res.value - step), 0.05)
        self.assertLessEqual(res.evaluations, evaluation_budget(lo, hi, step))

    def test_whole_range_meeting_the_target(self):
        res = E.solve_for(self.df, self.p, "principal", 0.5, 1_000_000.0, 30_000_000.0, 1_000_000.0)
        self.assertEqual((res.status, res.value, res.evaluations), ("all_meet", 30_000_000.0, 1))
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, self.p, principal=30_000_000.0))
        res = E.solve_for(self.df, self.p, "salary_cap", 0.5, 0.0, 100_000.0, 1_000.0)
        self.assertEqual((res.status, res.value, res.evaluations), ("all_meet", 0.0, 1))
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, self.p, salary_cap=0.0))

    def test_nothing_in_range_meets_the_target(self):
        poor = dataclasses.replace(self.p, salary_cap=0.0)
        res = E.solve_for(self.df, poor, "principal", 0.05, 1_000_000.0, 30_000_000.0, 1_000_000.0)
        self.assertEqual((res.status, res.value), ("none_meet", None))
        # The rate reported is that of the end closest to meeting the target: the smallest loan.
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, poor, principal=1_000_000.0))
        self.assertGreater(res.ruin_rate, 0.05)
        self.assertEqual(res.evaluations, 2)
        big = dataclasses.replace(self.p, principal=50_000_000.0)
        res = E.solve_for(self.df, big, "salary_cap", 0.01, 0.0, 50_000.0, 1_000.0)
        self.assertEqual((res.status, res.value), ("none_meet", None))
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, big, salary_cap=50_000.0))
        self.assertEqual(res.evaluations, 2)

    def test_answer_is_a_grid_point_counted_from_lo(self):
        lo, hi, step = 1_234_567.0, 29_000_000.0, 700_000.0
        res = E.solve_for(self.df, self.p, "principal", 0.05, lo, hi, step)
        self.assertEqual(res.status, "ok")
        k = (res.value - lo) / step
        self.assertAlmostEqual(k, round(k), places=9)
        self.assertGreater(mc_ruin(self.df, self.p, principal=res.value + step), 0.05)

    def test_hi_off_the_grid_is_checked_too(self):
        # Principal: 1, 4 and 7 million are on the grid; 8.5 million is not but still meets the target.
        res = E.solve_for(self.df, self.p, "principal", 0.5, 1_000_000.0, 8_500_000.0, 3_000_000.0)
        self.assertEqual((res.status, res.value), ("all_meet", 8_500_000.0))
        # Salary: only hi itself, past the last grid point, is enough.
        p = dataclasses.replace(self.p, principal=10_000_000.0)
        below, at_hi = mc_ruin(self.df, p, salary_cap=40_000.0), mc_ruin(self.df, p, salary_cap=50_000.0)
        self.assertGreater(below, at_hi)
        res = E.solve_for(self.df, p, "salary_cap", (below + at_hi) / 2, 0.0, 50_000.0, 20_000.0)
        self.assertEqual((res.status, res.value, res.ruin_rate), ("ok", 50_000.0, at_hi))
        # And when hi fails, the answer is the last grid point below it.
        on_grid = mc_ruin(self.df, self.p, principal=10_000_000.0)
        off_grid = mc_ruin(self.df, self.p, principal=10_500_000.0)
        self.assertLess(on_grid, off_grid)
        res = E.solve_for(self.df, self.p, "principal", (on_grid + off_grid) / 2, 1_000_000.0, 10_500_000.0, 1_000_000.0)
        self.assertEqual((res.status, res.value, res.ruin_rate), ("ok", 10_000_000.0, on_grid))

    def test_evaluations_stay_within_the_budget_and_are_counted_exactly(self):
        for lo, hi, step in ((100_000.0, 100_000_000.0, 100_000.0), (0.0, 500_000.0, 1_000.0),
                             (1_000_000.0, 1_500_000.0, 1_000_000.0), (100_000.0, 30_150_000.0, 100_000.0)):
            for field_name, flip in (("principal", False), ("salary_cap", True)):
                for cut in np.linspace(lo, hi, 7):
                    def fake(df, p, cut=cut, flip=flip, field_name=field_name):
                        return 0.2 if (getattr(p, field_name) <= cut) != flip else 0.8
                    with mock.patch.object(E, "_mc_ruin_rate", side_effect=fake) as calls:
                        res = E.solve_for(self.df, self.p, field_name, 0.5, max(lo, 1.0) if field_name == "principal"
                                          else lo, hi, step)
                    self.assertEqual(res.evaluations, calls.call_count)
                    self.assertLessEqual(res.evaluations, evaluation_budget(max(lo, 1.0), hi, step))

    def test_binary_search_finds_the_same_answer_as_trying_every_value(self):
        rng = np.random.RandomState(0)
        for _ in range(300):
            step = float(rng.choice([1.0, 7.0, 1_000.0, 100_000.0, 0.25]))
            lo = step * rng.randint(1, 50) + float(rng.choice([0.0, 0.5 * step]))
            hi = lo + step * rng.randint(0, 600) + float(rng.choice([0.0, 0.3 * step]))
            cut = rng.uniform(lo - (hi - lo) * 0.2 - step, hi + (hi - lo) * 0.2 + step)
            values = candidates(lo, hi, step)
            for field_name in ("principal", "salary_cap"):
                safe = [v for v in values if (v <= cut if field_name == "principal" else v >= cut)]
                with mock.patch.object(E, "_mc_ruin_rate",
                                       side_effect=lambda df, p, f=field_name: 0.0 if getattr(p, f) in safe else 1.0):
                    res = E.solve_for(self.df, self.p, field_name, 0.5, lo, hi, step)
                msg = (field_name, lo, hi, step, cut)
                if not safe:
                    self.assertEqual((res.status, res.value, res.ruin_rate), ("none_meet", None, 1.0), msg)
                    continue
                best = max(safe) if field_name == "principal" else min(safe)
                whole = len(safe) == len(values)
                self.assertEqual(res.status, "all_meet" if whole else "ok", msg)
                self.assertEqual(res.value, best, msg)
                self.assertEqual(res.ruin_rate, 0.0, msg)
                if hi > lo:
                    self.assertLessEqual(res.evaluations, evaluation_budget(lo, hi, step), msg)

    def test_parameters_passed_in_are_left_alone(self):
        p = params(annual_rate_pct=10.0, seed=None, mc_paths=100)
        before = dataclasses.replace(p)
        E.solve_for(self.df, p, "principal", 0.05, 1_000_000.0, 30_000_000.0, 1_000_000.0)
        E.solve_for(self.df, p, "salary_cap", 0.05, 0.0, 100_000.0, 1_000.0)
        E.sensitivity_grid(self.df, p, [1e6, 2e6], [0.0, 1e4], mc_paths=50)
        self.assertEqual(p, before)
        self.assertIsNone(p.seed)

    def test_every_evaluation_draws_the_same_paths(self):
        for seed, expected in ((None, 42), (7, 7)):
            seen = []
            with mock.patch.object(E, "_mc_ruin_rate", side_effect=lambda df, p: seen.append(p) or 0.1):
                E.solve_for(self.df, params(seed=seed), "salary_cap", 0.05, 0.0, 100_000.0, 1_000.0)
                E.solve_for(self.df, params(seed=seed), "principal", 0.05, 1e6, 1e7, 1e6)
                E.sensitivity_grid(self.df, params(seed=seed), [1e6, 2e6], [0.0, 1e4])
            self.assertEqual({q.seed for q in seen}, {expected})
        unseeded = params(annual_rate_pct=10.0, seed=None, mc_paths=100)
        res = E.solve_for(self.df, unseeded, "principal", 0.05, 1_000_000.0, 30_000_000.0, 1_000_000.0)
        self.assertEqual(res, E.solve_for(self.df, dataclasses.replace(unseeded, seed=42), "principal", 0.05,
                                          1_000_000.0, 30_000_000.0, 1_000_000.0))
        self.assertEqual(res.ruin_rate, mc_ruin(self.df, unseeded, principal=res.value, seed=42))

    def test_other_settings_come_from_the_parameters(self):
        seen = []
        p = params(seed=3, mc_paths=123, annual_rate_pct=7.0, buffer_months=6)
        with mock.patch.object(E, "_mc_ruin_rate", side_effect=lambda df, q: seen.append(q) or 0.01):
            res = E.solve_for(self.df, p, "principal", 0.05, 1e6, 1e7, 1e6)
        self.assertEqual(res.value, 1e7)
        self.assertEqual(seen, [dataclasses.replace(p, principal=1e7)])

    def test_bad_requests_are_rejected_in_chinese(self):
        bad = [
            dict(field="loan"), dict(field="Principal"),
            dict(target_ruin=0.0), dict(target_ruin=1.0), dict(target_ruin=-0.1), dict(target_ruin=float("nan")),
            dict(lo=2e6, hi=1e6), dict(step=0.0), dict(step=-1e5), dict(step=float("nan")),
            dict(lo=-1.0), dict(lo=0.0), dict(hi=float("inf")),
            dict(field="salary_cap", lo=-1_000.0, hi=10_000.0, step=1_000.0),
            dict(df=self.df.iloc[:1]), dict(df=self.df.iloc[:0]),
        ]
        for overrides in bad:
            args = dict(df=self.df, params=self.p, field="principal", target_ruin=0.05, lo=1e6, hi=2e6, step=1e5)
            args.update(overrides)
            with mock.patch.object(E, "_mc_ruin_rate", return_value=0.0) as calls:
                with self.assertRaises(ValueError, msg=overrides) as ctx:
                    E.solve_for(**args)
            self.assertRegex(str(ctx.exception), r"[一-鿿]", overrides)
            self.assertEqual(calls.call_count, 0, overrides)
        # A salary search may start from nothing at all.
        res = E.solve_for(self.df, self.p, "salary_cap", 0.5, 0.0, 10_000.0, 1_000.0)
        self.assertEqual(res.value, 0.0)
        with self.assertRaises(ValueError):
            E.sensitivity_grid(self.df.iloc[:1], self.p, [1e6], [0.0])
        with self.assertRaisesRegex(ValueError, "蒙地卡羅次數"):
            E.sensitivity_grid(self.df, self.p, [1e6], [0.0], mc_paths=0)

    def test_lo_equal_to_hi_is_one_evaluation(self):
        res = E.solve_for(self.df, self.p, "principal", 0.5, 5e6, 5e6, 1e6)
        self.assertEqual((res.status, res.value, res.evaluations), ("all_meet", 5e6, 1))
        res = E.solve_for(self.df, self.p, "salary_cap", 1e-6, 0.0, 0.0, 1_000.0)
        self.assertEqual((res.status, res.value, res.evaluations), ("none_meet", None, 1))


class SensitivityGridTests(unittest.TestCase):
    df = market()
    p = params(annual_rate_pct=10.0, principal=10_000_000.0)

    def test_rows_and_columns_keep_the_order_given(self):
        principals = [20_000_000.0, 5_000_000.0, 10_000_000.0]
        caps = [50_000.0, 0.0, 25_000.0, 10_000.0]
        grid = E.sensitivity_grid(self.df, self.p, principals, caps, mc_paths=200)
        self.assertEqual(grid.shape, (3, 4))
        self.assertEqual(list(grid.index), principals)
        self.assertEqual(list(grid.columns), caps)
        self.assertTrue(((grid >= 0) & (grid <= 1)).all().all())
        for pr, cap in ((20_000_000.0, 0.0), (5_000_000.0, 50_000.0), (10_000_000.0, 10_000.0)):
            self.assertEqual(grid.loc[pr, cap], mc_ruin(self.df, self.p, principal=pr, salary_cap=cap, mc_paths=200))

    def test_current_settings_cell_matches_the_summary(self):
        settings = [
            self.p,
            dataclasses.replace(self.p, seed=None),
            dataclasses.replace(self.p, seed=11, rate_volatility_pct=1.0, mc_dividends=E.MC_DIVIDENDS_MODEL,
                                job_loss=E.JobLossParams(mode=E.JOB_LOSS_RANDOM, annual_prob=0.2, crash_linked=True)),
            dataclasses.replace(self.p, nhi_rate=0.0211, dividend_tax_rate=0.05, buffer_months=6, loan_fee=10_000.0,
                                grace_months=12, job_loss=E.JobLossParams(mode=E.JOB_LOSS_MANUAL, start_month=5,
                                                                          duration_months=12)),
        ]
        for p in settings:
            grid = E.sensitivity_grid(self.df, p, [5e6, p.principal], [0.0, p.salary_cap], mc_paths=p.mc_paths)
            seeded = dataclasses.replace(p, seed=42 if p.seed is None else p.seed)
            self.assertEqual(grid.loc[p.principal, p.salary_cap], mc_ruin(self.df, seeded))

    def test_ruin_falls_with_more_support_and_rises_with_a_bigger_loan(self):
        p = dataclasses.replace(self.p, seed=None, nhi_rate=0.0211, dividend_interval_months=3)
        grid = E.sensitivity_grid(self.df, p, [2e6, 5e6, 8e6, 12e6, 20e6, 40e6],
                                  [0.0, 10_000.0, 25_000.0, 50_000.0, 100_000.0], mc_paths=300)
        values = grid.to_numpy()
        self.assertTrue((np.diff(values, axis=1) <= 0).all())
        self.assertTrue((np.diff(values, axis=0) >= -0.01).all())
        self.assertGreater(values[-1, 1], values[0, 1])        # the grid is not flat

    def test_empty_axes_give_an_empty_table(self):
        self.assertEqual(E.sensitivity_grid(self.df, self.p, [], [0.0]).shape, (0, 1))
        self.assertEqual(E.sensitivity_grid(self.df, self.p, [1e6], []).shape, (1, 0))


if __name__ == '__main__':
    unittest.main()
