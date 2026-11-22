import unittest

import credit_limit as cl
import safety_limit as safe


class LimitFormulas(unittest.TestCase):
    def test_default_income_gives_100_approvable_and_110_legal(self):
        c = cl.assess(5)
        self.assertEqual((c.regulatory, c.approvable, c.cap), (110, 100, 110))

    def test_multiple_changes_only_the_estimate(self):
        c = cl.assess(10, multiple=16)
        self.assertEqual((c.regulatory, c.approvable, c.cap), (220, 160, 220))

    def test_product_maximum_caps_both(self):
        c = cl.assess(50)
        self.assertEqual((c.regulatory, c.approvable, c.cap), (1100, 500, 500))
        self.assertTrue(c.capped_by_product)

    def test_existing_debt_is_subtracted_from_both(self):
        c = cl.assess(5, debt=50)
        self.assertEqual((c.regulatory, c.approvable, c.cap), (60, 50, 60))

    def test_debt_above_the_limit_leaves_nothing(self):
        c = cl.assess(5, debt=200)
        self.assertEqual((c.regulatory, c.approvable, c.cap), (0, 0, 0))

    def test_no_income_means_no_check(self):
        self.assertIsNone(cl.assess(0))
        self.assertEqual(cl.adopted_principal(None, 500), 500)

    def test_adopted_principal(self):
        c = cl.assess(5)
        self.assertEqual(cl.adopted_principal(c, 100), 100)
        self.assertEqual(cl.adopted_principal(c, 300), 110)
        self.assertEqual(cl.adopted_principal(c, 300, estimated=True), 100)


class LegacyLinks(unittest.TestCase):
    def test_loan_without_income_on_a_personal_loan_is_legacy(self):
        self.assertTrue(cl.is_legacy_link({"loan": "800"}))
        self.assertTrue(cl.is_legacy_link({"loan": "800", "type": "1"}))
        self.assertTrue(cl.is_legacy_link({"loan": "800", "type": "x"}))

    def test_other_links_are_not(self):
        self.assertFalse(cl.is_legacy_link({}))
        self.assertFalse(cl.is_legacy_link({"loan": "800", "inc": "5"}))
        self.assertFalse(cl.is_legacy_link({"loan": "800", "type": "0"}))
        self.assertFalse(cl.is_legacy_link({"rate": "4"}))


class Sentences(unittest.TestCase):
    def test_amount_format(self):
        self.assertEqual(cl.wan(110), "110 萬")
        self.assertEqual(cl.wan(5.5), "5.5 萬")
        self.assertEqual(cl.wan(1100), "1,100 萬")
        self.assertEqual(cl.wan(0), "0 萬")

    def test_summary(self):
        self.assertEqual(cl.summary(cl.assess(5)),
                         "依平均月收入 5 萬：法規上限 110 萬、一般可核貸約 100 萬（估計）、產品最高額度 500 萬。"
                         "你的可借上限是 110 萬。")
        self.assertTrue(cl.summary(cl.assess(5, debt=50)).endswith("已扣掉既有無擔保債務 50 萬。"))

    def test_clamp_notice_names_the_binding_limit(self):
        self.assertIn("平均月收入的 22 倍", cl.clamp_notice(cl.assess(5), 300))
        self.assertIn("以下結果以 110 萬計算", cl.clamp_notice(cl.assess(5), 300))
        self.assertIn("產品最高額度是 500 萬", cl.clamp_notice(cl.assess(50), 800))

    def test_ratio_thresholds(self):
        self.assertIsNone(cl.ratio_notice(1 / 3, 10_000))
        self.assertIn("偏高", cl.ratio_notice(0.362, 18_100))
        self.assertIn("36.2%", cl.ratio_notice(0.362, 18_100))
        self.assertIn("多數銀行可能婉拒", cl.ratio_notice(0.71, 35_500))
        self.assertNotIn("偏高", cl.ratio_notice(0.71, 35_500))

    def test_income_threshold(self):
        self.assertIn("年收入約 24 萬", cl.income_notice(cl.assess(2)))
        self.assertIsNone(cl.income_notice(cl.assess(2.5)))

    def test_estimate_warning_only_between_estimate_and_cap(self):
        c = cl.assess(5)
        self.assertIn("銀行可能只核給較低的額度", cl.above_estimate_notice(c, 105))
        self.assertIsNone(cl.above_estimate_notice(c, 100))
        self.assertIsNone(cl.above_estimate_notice(c, 111))


class SearchBounds(unittest.TestCase):
    def test_cap_lowers_the_top_to_a_multiple_of_100k(self):
        self.assertEqual(safe.principal_bounds(5_000_000, 0, 1_210_000), (100_000.0, 1_200_000.0))

    def test_cap_never_raises_the_top(self):
        self.assertEqual(safe.principal_bounds(100_000, 0, 5_000_000), (100_000.0, 1_000_000.0))

    def test_no_cap_is_unchanged(self):
        self.assertEqual(safe.principal_bounds(1_000_000, 0), (100_000.0, 10_000_000.0))


if __name__ == "__main__":
    unittest.main()
