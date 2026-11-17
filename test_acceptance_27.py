"""第 27 項（安全邊界）計算核心的驗收測試，依 docs/specs/SPEC-v40.md 第 4.1 節的合約撰寫。

只透過合約裡的公開介面（engine.SolveResult、engine.solve_for、engine.sensitivity_grid）
與既有的 engine.run_summary 檢查行為，不依賴實作細節。全部使用合成資料，可離線執行。
"""
import dataclasses
import math
import re
import time
import unittest
from unittest.mock import patch

import numpy as np

import engine as E
from test_engine import market, params

CJK = re.compile(r"[一-鿿]")
FALLBACK_SEED = 42
TOL = 1e-9


def harsh(**overrides):
    """破產率會隨本金與自掏上限明顯變化的設定（合成行情每年再扣 15% 報酬）。"""
    base = dict(mc_paths=300, structural_discount_pct=15, salary_cap=20_000.0, seed=42)
    base.update(overrides)
    return params(**base)


def seeded(p):
    return p if p.seed is not None else dataclasses.replace(p, seed=FALLBACK_SEED)


_ruin_cache = {}


def ruin(df, p, **changes):
    """run_summary 的蒙地卡羅破產率；seed 為 None 時依 SPEC 用 42。"""
    q = seeded(dataclasses.replace(p, **changes))
    key = (id(df), q)
    if key not in _ruin_cache:
        _ruin_cache[key] = float(E.run_summary(df, q).mc["Is_Ruined"].mean())
    return _ruin_cache[key]


def candidates(lo, hi, step):
    """SPEC 4.1／D1：value 是 lo + k*step（不超過 hi）或 hi。"""
    k_max = int(math.floor((hi - lo) / step + TOL))
    values = [lo + k * step for k in range(k_max + 1)]
    if hi - values[-1] > TOL * max(1.0, abs(hi)):
        values.append(hi)
    return values


def eval_limit(lo, hi, step):
    """D2：evaluations 不可超過 max(2, ceil(log2((hi - lo) / step)) + 3)；lo == hi 只評估 1 次。"""
    span = (hi - lo) / step
    if span <= 0:
        return 1
    return max(2, math.ceil(math.log2(span)) + 3)


def brute_force(df, p, field, target, lo, hi, step):
    """逐一跑 run_summary，依 SPEC 的定義算出正確答案 (status, value, ruin_rate)。"""
    grid = candidates(lo, hi, step)
    rates = {v: ruin(df, p, **{field: v}) for v in grid}
    meets = [v for v in grid if rates[v] <= target]
    lo, hi = grid[0], grid[-1]
    if field == "principal":
        if rates[hi] <= target:
            return "all_meet", hi, rates[hi], rates
        if rates[lo] > target:
            return "none_meet", None, rates[lo], rates
        best = max(meets)
    else:
        if rates[lo] <= target:
            return "all_meet", lo, rates[lo], rates
        if rates[hi] > target:
            return "none_meet", None, rates[hi], rates
        best = min(meets)
    return "ok", best, rates[best], rates


class ContractChecks:
    """每個 solve_for 結果都要符合的合約。"""

    def solve(self, df, p, field, target, lo, hi, step):
        before = dataclasses.replace(p)
        df_before = df.copy()
        real_run_summary = E.run_summary
        with patch.object(E, "run_summary", wraps=real_run_summary) as spy:
            res = E.solve_for(df, p, field, target, lo, hi, step)
        self.assertEqual(p, before, "solve_for 不可修改傳入的 params")
        self.assertTrue(df.equals(df_before), "solve_for 不可修改傳入的行情資料")
        self.check_contract(res, df, p, field, target, lo, hi, step)
        if spy.call_count:
            self.assertEqual(spy.call_count, res.evaluations, "evaluations 應等於實際跑模擬的次數")
        return res

    def check_contract(self, res, df, p, field, target, lo, hi, step):
        self.assertIsInstance(res, E.SolveResult)
        self.assertEqual(res.field, field)
        self.assertAlmostEqual(res.target, target)
        self.assertIn(res.status, ("ok", "all_meet", "none_meet"))
        self.assertIsInstance(res.evaluations, int)
        self.assertGreaterEqual(res.evaluations, 1)
        self.assertLessEqual(res.evaluations, eval_limit(lo, hi, step),
                             f"評估次數 {res.evaluations} 超過上限（lo={lo}, hi={hi}, step={step}）")
        self.assertGreaterEqual(res.ruin_rate, 0.0)
        self.assertLessEqual(res.ruin_rate, 1.0)

        if res.status == "none_meet":
            self.assertIsNone(res.value)
            self.assertGreater(res.ruin_rate, target)
            nearest = lo if field == "principal" else hi
            self.assertAlmostEqual(res.ruin_rate, ruin(df, p, **{field: nearest}), delta=1e-12,
                                   msg="none_meet 時 ruin_rate 應是最接近達標那一端的破產率")
            return

        self.assertIsNotNone(res.value)
        self.assertTrue(any(abs(res.value - v) <= TOL * max(1.0, abs(v)) for v in candidates(lo, hi, step)),
                        f"value={res.value} 不在 lo + k*step 格點上，也不等於 hi")
        self.assertLessEqual(res.ruin_rate, target)
        self.assertAlmostEqual(res.ruin_rate, ruin(df, p, **{field: float(res.value)}), delta=1e-12,
                               msg="ruin_rate 應等於 run_summary 在 value 的蒙地卡羅破產率")
        if res.status == "all_meet":
            self.assertAlmostEqual(res.value, hi if field == "principal" else lo)
        else:
            self.assertNotAlmostEqual(res.value, hi if field == "principal" else lo)
            self.check_local_boundary(res, df, p, field, target, lo, hi, step)

    def check_local_boundary(self, res, df, p, field, target, lo, hi, step):
        """與破產率是否單調無關的性質：value 達標，而往不安全方向的下一個候選值不達標。"""
        grid = candidates(lo, hi, step)
        i = min(range(len(grid)), key=lambda j: abs(grid[j] - res.value))
        neighbour = grid[i + 1] if field == "principal" else grid[i - 1]
        self.assertGreater(ruin(df, p, **{field: neighbour}), target,
                           f"{field}={neighbour} 也達標，value={res.value} 不是邊界")


class SolveResultShapeTests(unittest.TestCase):
    def test_is_a_frozen_dataclass_with_the_agreed_fields(self):
        self.assertTrue(dataclasses.is_dataclass(E.SolveResult))
        names = [f.name for f in dataclasses.fields(E.SolveResult)]
        self.assertEqual(names, ["field", "value", "ruin_rate", "target", "status", "evaluations"])
        res = E.SolveResult(field="principal", value=1.0, ruin_rate=0.0, target=0.05, status="ok", evaluations=1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.value = 2.0


class SolvePrincipalTests(ContractChecks, unittest.TestCase):
    df = market(n=226)

    def test_matches_brute_force_for_several_targets(self):
        p = harsh()
        lo, hi, step = 1_000_000.0, 8_000_000.0, 500_000.0
        for target in (0.01, 0.02, 0.05, 0.10, 0.15):
            with self.subTest(target=target):
                status, value, rate, rates = brute_force(self.df, p, "principal", target, lo, hi, step)
                self.assertEqual(status, "ok", "測試前提：答案應在範圍內部")
                res = self.solve(self.df, p, "principal", target, lo, hi, step)
                self.assertEqual(res.status, status)
                self.assertAlmostEqual(res.value, value)
                self.assertAlmostEqual(res.ruin_rate, rate, delta=1e-12)

    def test_matches_brute_force_on_a_fine_grid(self):
        p = harsh()
        lo, hi, step = 3_000_000.0, 5_000_000.0, 100_000.0
        for target in (0.02, 0.05):
            with self.subTest(target=target):
                status, value, _, rates = brute_force(self.df, p, "principal", target, lo, hi, step)
                ordered = [rates[v] for v in sorted(rates)]
                self.assertTrue(np.all(np.diff(ordered) >= 0), "測試前提：這段範圍的破產率應隨本金單調")
                res = self.solve(self.df, p, "principal", target, lo, hi, step)
                self.assertEqual((res.status, res.value), (status, value))

    def test_target_is_inclusive(self):
        p = harsh()
        lo, hi, step = 1_000_000.0, 8_000_000.0, 500_000.0
        target = ruin(self.df, p, principal=4_000_000.0)  # 恰好等於 400 萬的破產率
        self.assertTrue(0 < target < 1)
        status, value, _, _ = brute_force(self.df, p, "principal", target, lo, hi, step)
        res = self.solve(self.df, p, "principal", target, lo, hi, step)
        self.assertEqual((res.status, res.value), (status, value))
        self.assertGreaterEqual(res.value, 4_000_000.0)

    def test_hi_off_the_grid_is_also_checked(self):
        p = harsh()
        # 100 萬～825 萬、單位 50 萬：格點到 800 萬為止，825 萬本身也要檢查。
        lo, hi, step = 1_000_000.0, 8_250_000.0, 500_000.0
        target = ruin(self.df, p, principal=hi)
        self.assertGreater(target, ruin(self.df, p, principal=8_000_000.0), "測試前提")
        res = self.solve(self.df, p, "principal", target, lo, hi, step)
        self.assertEqual(res.status, "all_meet")
        self.assertAlmostEqual(res.value, hi)

    def test_hi_off_the_grid_that_fails_returns_a_grid_point(self):
        p = harsh()
        lo, hi, step = 1_000_000.0, 4_750_000.0, 500_000.0  # 格點到 450 萬，475 萬本身不達標
        status, value, _, _ = brute_force(self.df, p, "principal", 0.05, lo, hi, step)
        self.assertEqual((status, value), ("ok", 4_000_000.0), "測試前提")
        res = self.solve(self.df, p, "principal", 0.05, lo, hi, step)
        self.assertEqual((res.status, res.value), ("ok", 4_000_000.0))

    def test_whole_range_safe_is_all_meet_at_hi(self):
        p = harsh()
        res = self.solve(self.df, p, "principal", 0.05, 100_000.0, 2_000_000.0, 100_000.0)
        self.assertEqual(res.status, "all_meet")
        self.assertEqual(res.value, 2_000_000.0)

    def test_whole_range_unsafe_is_none_meet(self):
        p = harsh()
        res = self.solve(self.df, p, "principal", 0.05, 7_000_000.0, 10_000_000.0, 100_000.0)
        self.assertEqual(res.status, "none_meet")
        self.assertIsNone(res.value)
        self.assertAlmostEqual(res.ruin_rate, ruin(self.df, p, principal=7_000_000.0), delta=1e-12)

    def test_range_narrower_than_one_step(self):
        p = harsh()
        # 只有 lo 一個格點，加上不在格點上的 hi；上限公式給 2 次評估。
        res = self.solve(self.df, p, "principal", 0.05, 4_000_000.0, 4_050_000.0, 100_000.0)
        status, value, _, _ = brute_force(self.df, p, "principal", 0.05, 4_000_000.0, 4_050_000.0, 100_000.0)
        self.assertEqual((res.status, res.value), (status, value))

    def test_single_point_range(self):
        p = harsh()
        meets = self.solve(self.df, p, "principal", 0.05, 4_000_000.0, 4_000_000.0, 100_000.0)
        self.assertEqual((meets.status, meets.value, meets.evaluations), ("all_meet", 4_000_000.0, 1))
        fails = self.solve(self.df, p, "principal", 0.05, 5_000_000.0, 5_000_000.0, 100_000.0)
        self.assertEqual((fails.status, fails.value, fails.evaluations), ("none_meet", None, 1))
        for cap, status in ((40_000.0, "all_meet"), (0.0, "none_meet")):
            res = self.solve(self.df, p, "salary_cap", 0.05, cap, cap, 1_000.0)
            self.assertEqual((res.status, res.evaluations), (status, 1))

    def test_app_sized_search_stays_within_the_evaluation_limit(self):
        # 衝刺 2 畫面的範圍：10 萬～目前本金的 10 倍，單位 10 萬（約 500 個格點）。
        p = harsh(mc_paths=200)
        res = self.solve(self.df, p, "principal", 0.05, 100_000.0, 50_000_000.0, 100_000.0)
        self.assertLessEqual(res.evaluations, math.ceil(math.log2(499)) + 3)

    def test_higher_target_never_allows_a_smaller_loan(self):
        p = harsh()
        values = []
        for target in (0.01, 0.03, 0.05, 0.08, 0.12, 0.2):
            res = self.solve(self.df, p, "principal", target, 500_000.0, 9_000_000.0, 250_000.0)
            values.append(-math.inf if res.value is None else res.value)
        self.assertEqual(values, sorted(values))

    def test_other_seeds_and_settings(self):
        cases = [harsh(seed=7), harsh(seed=123, annual_rate_pct=5.0), harsh(salary_cap=10_000.0, grace_months=12),
                 harsh(nhi_rate=0.0211, sell_tax=0.001, dividend_tax_rate=0.05)]
        for p in cases:
            for target in (0.03, 0.1):
                with self.subTest(seed=p.seed, target=target):
                    status, value, _, _ = brute_force(self.df, p, "principal", target, 500_000.0, 9_000_000.0,
                                                      500_000.0)
                    res = self.solve(self.df, p, "principal", target, 500_000.0, 9_000_000.0, 500_000.0)
                    self.assertEqual((res.status, res.value), (status, value))


class SolveSalaryCapTests(ContractChecks, unittest.TestCase):
    df = market(n=226)

    def test_matches_brute_force_for_several_targets(self):
        p = harsh()
        lo, hi, step = 0.0, 45_000.0, 2_500.0
        for target in (0.01, 0.04, 0.05, 0.10, 0.2):
            with self.subTest(target=target):
                status, value, rate, _ = brute_force(self.df, p, "salary_cap", target, lo, hi, step)
                self.assertEqual(status, "ok", "測試前提：答案應在範圍內部")
                res = self.solve(self.df, p, "salary_cap", target, lo, hi, step)
                self.assertEqual(res.status, status)
                self.assertAlmostEqual(res.value, value)
                self.assertAlmostEqual(res.ruin_rate, rate, delta=1e-12)

    def test_matches_brute_force_on_a_fine_grid(self):
        p = harsh()
        lo, hi, step = 15_000.0, 30_000.0, 500.0
        for target in (0.03, 0.05, 0.1):
            with self.subTest(target=target):
                status, value, _, rates = brute_force(self.df, p, "salary_cap", target, lo, hi, step)
                ordered = [rates[v] for v in sorted(rates)]
                self.assertTrue(np.all(np.diff(ordered) <= 0), "測試前提：破產率應隨自掏上限單調不升")
                res = self.solve(self.df, p, "salary_cap", target, lo, hi, step)
                self.assertEqual((res.status, res.value), (status, value))

    def test_app_sized_search(self):
        # 衝刺 2 畫面的範圍：0～50 萬，單位 1,000 元。
        p = harsh(mc_paths=200)
        status, value, _, _ = brute_force(self.df, p, "salary_cap", 0.05, 0.0, 60_000.0, 1_000.0)
        res = self.solve(self.df, p, "salary_cap", 0.05, 0.0, 500_000.0, 1_000.0)
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.value, value)
        self.assertLessEqual(res.evaluations, math.ceil(math.log2(500)) + 3)

    def test_safe_at_lo_is_all_meet_at_lo(self):
        res = self.solve(self.df, harsh(), "salary_cap", 0.05, 40_000.0, 80_000.0, 1_000.0)
        self.assertEqual((res.status, res.value), ("all_meet", 40_000.0))

    def test_zero_lo_is_allowed_and_can_be_the_answer(self):
        p = params(mc_paths=300)  # 沒有額外扣報酬的設定，完全不自掏也幾乎不會破產
        self.assertLessEqual(ruin(self.df, p, salary_cap=0.0), 0.05, "測試前提")
        res = self.solve(self.df, p, "salary_cap", 0.05, 0.0, 50_000.0, 1_000.0)
        self.assertEqual((res.status, res.value), ("all_meet", 0.0))

    def test_unsafe_at_hi_is_none_meet(self):
        p = harsh()
        res = self.solve(self.df, p, "salary_cap", 0.05, 0.0, 5_000.0, 1_000.0)
        self.assertEqual(res.status, "none_meet")
        self.assertIsNone(res.value)
        self.assertAlmostEqual(res.ruin_rate, ruin(self.df, p, salary_cap=5_000.0), delta=1e-12)

    def test_hi_off_the_grid_is_also_checked(self):
        p = harsh()
        lo, hi, step = 0.0, 23_750.0, 2_500.0  # 格點到 22,500，23,750 本身也要檢查
        target = ruin(self.df, p, salary_cap=hi)
        self.assertLess(target, ruin(self.df, p, salary_cap=22_500.0), "測試前提")
        res = self.solve(self.df, p, "salary_cap", target, lo, hi, step)
        self.assertEqual((res.status, res.value), ("ok", hi))

    def test_higher_target_never_needs_more_salary(self):
        p = harsh()
        values = []
        for target in (0.01, 0.03, 0.05, 0.08, 0.12, 0.2):
            res = self.solve(self.df, p, "salary_cap", target, 0.0, 60_000.0, 1_000.0)
            values.append(math.inf if res.value is None else res.value)
        self.assertEqual(values, sorted(values, reverse=True))


class SeedAndInputTests(ContractChecks, unittest.TestCase):
    df = market(n=226)

    def test_missing_seed_uses_42_and_stays_missing(self):
        p = harsh(seed=None)
        for field, lo, hi, step in (("principal", 1e6, 8e6, 5e5), ("salary_cap", 0.0, 45_000.0, 2_500.0)):
            with self.subTest(field=field):
                res = self.solve(self.df, p, field, 0.05, lo, hi, step)
                self.assertIsNone(p.seed)
                fixed = E.solve_for(self.df, harsh(seed=42), field, 0.05, lo, hi, step)
                self.assertEqual(res, fixed)
                again = E.solve_for(self.df, p, field, 0.05, lo, hi, step)
                self.assertEqual(res, again, "seed 為 None 時結果也必須可重現")

    def test_given_seed_is_used(self):
        p = harsh(seed=7)
        res = self.solve(self.df, p, "principal", 0.05, 1e6, 8e6, 5e5)
        self.assertAlmostEqual(res.ruin_rate, float(E.run_summary(self.df, dataclasses.replace(
            p, principal=float(res.value))).mc["Is_Ruined"].mean()), delta=1e-12)

    def test_other_settings_are_carried_over(self):
        base = harsh()
        dearer = harsh(annual_rate_pct=6.0)
        a = self.solve(self.df, base, "principal", 0.05, 5e5, 9e6, 2.5e5)
        b = self.solve(self.df, dearer, "principal", 0.05, 5e5, 9e6, 2.5e5)
        self.assertLess(b.value, a.value, "利率較高時能借的應較少：表示 annual_rate_pct 有被沿用")


class SolveValidationTests(unittest.TestCase):
    df = market(n=226)

    def assertChineseValueError(self, *args):
        with self.assertRaises(ValueError) as ctx:
            E.solve_for(*args)
        self.assertRegex(str(ctx.exception), CJK, "ValueError 應附中文訊息")

    def test_unknown_field(self):
        for field in ("rate", "Principal", "", None):
            with self.subTest(field=field):
                self.assertChineseValueError(self.df, harsh(), field, 0.05, 1e6, 8e6, 5e5)

    def test_target_outside_the_open_unit_interval(self):
        for target in (0.0, 1.0, -0.05, 1.5):
            for field, lo, hi, step in (("principal", 1e6, 8e6, 5e5), ("salary_cap", 0.0, 45_000.0, 2_500.0)):
                with self.subTest(target=target, field=field):
                    self.assertChineseValueError(self.df, harsh(), field, target, lo, hi, step)

    def test_lo_above_hi(self):
        self.assertChineseValueError(self.df, harsh(), "principal", 0.05, 8e6, 1e6, 5e5)
        self.assertChineseValueError(self.df, harsh(), "salary_cap", 0.05, 45_000.0, 0.0, 2_500.0)

    def test_step_not_positive(self):
        for step in (0.0, -500_000.0):
            with self.subTest(step=step):
                self.assertChineseValueError(self.df, harsh(), "principal", 0.05, 1e6, 8e6, step)
                self.assertChineseValueError(self.df, harsh(), "salary_cap", 0.05, 0.0, 45_000.0, step)

    def test_negative_lo(self):
        self.assertChineseValueError(self.df, harsh(), "principal", 0.05, -100_000.0, 8e6, 100_000.0)
        self.assertChineseValueError(self.df, harsh(), "salary_cap", 0.05, -1_000.0, 45_000.0, 1_000.0)

    def test_principal_search_cannot_start_at_zero(self):
        self.assertChineseValueError(self.df, harsh(), "principal", 0.05, 0.0, 8e6, 100_000.0)

    def test_too_little_data_for_monte_carlo(self):
        for n in (0, 1):
            for field, lo, hi, step in (("principal", 1e6, 8e6, 5e5), ("salary_cap", 0.0, 45_000.0, 2_500.0)):
                with self.subTest(n=n, field=field):
                    self.assertChineseValueError(self.df.iloc[:n], harsh(), field, 0.05, lo, hi, step)


class SensitivityGridTests(unittest.TestCase):
    df = market(n=226)

    def test_shape_and_order_follow_the_inputs(self):
        principals = [3e6, 1e6, 5e6, 2e6]
        caps = [20_000.0, 0.0, 10_000.0]
        grid = E.sensitivity_grid(self.df, harsh(), principals, caps, mc_paths=200)
        self.assertEqual(grid.shape, (4, 3))
        self.assertEqual(list(grid.index), principals)
        self.assertEqual(list(grid.columns), caps)
        values = grid.to_numpy(dtype=float)
        self.assertFalse(np.isnan(values).any())
        self.assertTrue(((values >= 0) & (values <= 1)).all())

    def test_current_cell_equals_run_summary(self):
        for seed in (42, 7, None):
            with self.subTest(seed=seed):
                p = harsh(seed=seed, principal=4_000_000.0, salary_cap=20_000.0)
                grid = E.sensitivity_grid(self.df, p, [2e6, 4e6, 6e6], [10_000.0, 20_000.0, 30_000.0],
                                          mc_paths=p.mc_paths)
                expected = E.run_summary(self.df, seeded(p)).mc["Is_Ruined"].mean()
                self.assertAlmostEqual(grid.loc[4e6, 20_000.0], expected, delta=1e-12)

    def test_default_path_count_is_1000(self):
        p = harsh(principal=4_000_000.0, salary_cap=20_000.0)  # params 本身是 300 條路徑
        grid = E.sensitivity_grid(self.df, p, [4e6], [20_000.0])
        expected = E.run_summary(self.df, dataclasses.replace(p, mc_paths=1000)).mc["Is_Ruined"].mean()
        self.assertAlmostEqual(grid.loc[4e6, 20_000.0], expected, delta=1e-12)

    def test_every_cell_changes_only_principal_and_cap(self):
        p = harsh(seed=None, annual_rate_pct=4.5, grace_months=12, nhi_rate=0.0211)
        principals, caps = [2.5e6, 5e6], [0.0, 15_000.0, 30_000.0]
        grid = E.sensitivity_grid(self.df, p, principals, caps, mc_paths=250)
        for pr in principals:
            for cap in caps:
                expected = ruin(self.df, p, principal=pr, salary_cap=cap, mc_paths=250)
                self.assertAlmostEqual(grid.loc[pr, cap], expected, delta=1e-12, msg=f"({pr}, {cap})")

    def test_missing_seed_uses_42_and_is_repeatable(self):
        args = ([2e6, 4e6, 6e6], [10_000.0, 25_000.0])
        unseeded = E.sensitivity_grid(self.df, harsh(seed=None), *args, mc_paths=300)
        fixed = E.sensitivity_grid(self.df, harsh(seed=42), *args, mc_paths=300)
        again = E.sensitivity_grid(self.df, harsh(seed=None), *args, mc_paths=300)
        np.testing.assert_array_equal(unseeded.to_numpy(), fixed.to_numpy())
        np.testing.assert_array_equal(unseeded.to_numpy(), again.to_numpy())

    def test_invalid_axes_raise(self):
        # D5：空的軸、本金 <= 0、自掏上限 < 0 丟 ValueError（中文訊息，D8）。
        p = harsh()
        cases = {"本金軸是空的": ([], [0.0]), "自掏軸是空的": ([1e6], []), "本金為 0": ([0.0, 1e6], [0.0]),
                 "本金為負": ([-1e6], [0.0]), "自掏上限為負": ([1e6], [10_000.0, -1.0])}
        for name, (principals, caps) in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError) as ctx:
                    E.sensitivity_grid(self.df, p, principals, caps, mc_paths=50)
                self.assertRegex(str(ctx.exception), CJK)

    def test_too_little_data_raises(self):
        with self.assertRaises(ValueError):
            E.sensitivity_grid(self.df.iloc[:1], harsh(), [1e6], [0.0], mc_paths=50)

    def test_duplicate_values_are_allowed(self):
        # D5：重複值允許；每個重複的列／欄都照傳入順序出現，值相同。
        grid = E.sensitivity_grid(self.df, harsh(), [2e6, 4e6, 2e6], [0.0, 20_000.0, 0.0], mc_paths=200)
        self.assertEqual(grid.shape, (3, 3))
        self.assertEqual(list(grid.index), [2e6, 4e6, 2e6])
        self.assertEqual(list(grid.columns), [0.0, 20_000.0, 0.0])
        values = grid.to_numpy(dtype=float)
        np.testing.assert_array_equal(values[0], values[2])
        np.testing.assert_array_equal(values[:, 0], values[:, 2])

    def test_params_are_not_modified(self):
        p = harsh(seed=None)
        before = dataclasses.replace(p)
        E.sensitivity_grid(self.df, p, [1e6, 2e6], [0.0, 10_000.0], mc_paths=100)
        self.assertEqual(p, before)
        self.assertIsNone(p.seed)

    def test_monotone_in_salary_cap_and_nearly_monotone_in_principal(self):
        # 台灣稅費（含補充保費門檻）是 SPEC 提到可能造成極小例外的情況。
        p = harsh(principal=5e6, salary_cap=20_000.0, nhi_rate=0.0211, sell_tax=0.001, dividend_tax_rate=0.05)
        principals = [m * 5e6 for m in (0.5, 0.75, 1, 1.25, 1.5, 2)]
        caps = [m * 20_000.0 for m in (0.5, 0.75, 1, 1.25, 1.5, 2)]
        # 以打亂的順序傳入，排序後檢查，以免單調性檢查依賴傳入順序。
        grid = E.sensitivity_grid(self.df, p, principals[::-1], caps[3:] + caps[:3], mc_paths=1000)
        grid = grid.sort_index().sort_index(axis=1)
        values = grid.to_numpy(dtype=float)
        self.assertTrue((np.diff(values, axis=1) <= 1e-12).all(), f"同一列自掏上限越高破產率不可升：\n{grid}")
        self.assertTrue((np.diff(values, axis=0) >= -0.01).all(), f"同一欄本金越高破產率不可降超過 0.01：\n{grid}")
        self.assertGreater(values.max() - values.min(), 0.1, "測試前提：熱圖應有明顯變化")

    def test_six_by_six_with_1000_paths_finishes_within_ten_seconds(self):
        df = market(n=226)
        p = params(total_months=84, mc_paths=1000, seed=None, nhi_rate=0.0211, sell_tax=0.001)
        principals = [m * p.principal for m in (0.5, 0.75, 1, 1.25, 1.5, 2)]
        caps = [m * p.salary_cap for m in (0.5, 0.75, 1, 1.25, 1.5, 2)]
        start = time.perf_counter()
        grid = E.sensitivity_grid(df, p, principals, caps, mc_paths=1000)
        elapsed = time.perf_counter() - start
        self.assertEqual(grid.shape, (6, 6))
        self.assertLess(elapsed, 10.0, f"6×6 熱圖花了 {elapsed:.1f} 秒")


if __name__ == "__main__":
    unittest.main()
