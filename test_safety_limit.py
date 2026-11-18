import dataclasses
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import engine as E
import safety_limit as S
from test_engine import market, params


def solved(field, status, value, rate, target=0.05):
    return E.SolveResult(field, value, rate, target, status, 3)


def record(principal=None, salary="default", target="5", grid=None, cur_principal=5_000_000.0, cur_salary=25_000.0,
           lo=100_000.0, hi=50_000_000.0, paths=2000, seed_is_random=False, salary_in_order=True):
    principals, caps = S.map_axes(cur_principal, cur_salary)
    if grid is None:
        grid = pd.DataFrame(0.01, index=principals, columns=caps)
    return {"target": target, "paths": paths, "seed_is_random": seed_is_random, "salary_in_order": salary_in_order,
            "principal": principal or solved("principal", "ok", 6_600_000.0, 0.0495),
            "salary": solved("salary_cap", "ok", 19_000.0, 0.0495) if salary == "default" else salary,
            "lo": lo, "hi": hi, "current_principal": cur_principal, "current_salary": cur_salary, "grid": grid}


class SearchRangeTests(unittest.TestCase):
    def test_principal_range_follows_the_loan_and_the_fee(self):
        self.assertEqual(S.principal_bounds(5_000_000, 0), (100_000.0, 50_000_000.0))
        self.assertEqual(S.principal_bounds(5_000_000, 6_000), (100_000.0, 50_000_000.0))
        self.assertEqual(S.principal_bounds(5_000_000, 100_000), (200_000.0, 50_000_000.0))
        self.assertEqual(S.principal_bounds(5_000_000, 150_000), (200_000.0, 50_000_000.0))
        self.assertEqual(S.principal_bounds(20_000_000, 0), (100_000.0, 100_000_000.0))     # capped at 1 億
        self.assertEqual(S.principal_bounds(10_000, 0), (100_000.0, 100_000.0))             # never below lo
        for fee in (0, 1, 99_999, 100_000, 3_000_000, 4_999_999):
            lo, hi = S.principal_bounds(5_000_000, fee)
            self.assertGreater(lo, fee)
            self.assertEqual(lo % 100_000, 0)
            self.assertGreaterEqual(hi, lo)

    def test_map_axes_scale_the_current_values(self):
        principals, caps = S.map_axes(5_000_000, 25_000)
        self.assertEqual(principals, [2_500_000, 3_750_000, 5_000_000, 6_250_000, 7_500_000, 10_000_000])
        self.assertEqual(caps, [12_500, 18_750, 25_000, 31_250, 37_500, 50_000])
        self.assertEqual(S.map_axes(5_000_000, 0)[1], [0, 5_000, 10_000, 20_000, 30_000, 50_000])
        self.assertEqual(S.map_axes(5_000_000, 25_001)[1][0], 12_501)                     # 12,500.5 rounds up
        self.assertEqual(S.map_axes(5_000_000, 1)[1], [1, 2])                             # repeats are dropped


class FormattingTests(unittest.TestCase):
    def test_rates_get_a_second_decimal_only_near_the_target(self):
        self.assertEqual(S.ruin_text(0.026, "5"), "2.6%")
        self.assertEqual(S.ruin_text(0.0495, "5"), "4.95%")
        self.assertEqual(S.ruin_text(0.05, "5"), "5.00%")
        self.assertEqual(S.ruin_text(0.0502, "5"), "5.02%")
        self.assertEqual(S.ruin_text(0.051, "5"), "5.1%")
        self.assertEqual(S.ruin_text(0.0095, "1"), "0.95%")
        self.assertEqual(S.ruin_text(0.0095, "5"), "0.9%")
        self.assertEqual(S.ruin_text(float("nan"), "5"), "—")

    def test_amounts(self):
        self.assertEqual(S.wan(6_600_000), "660")
        self.assertEqual(S.wan(100_000_000), "10,000")
        self.assertEqual(S.wan(2_497_500), "249.75")
        self.assertEqual(S.dollars(19_000), "$19,000")

    def test_dollar_signs_are_escaped_for_streamlit_and_bold_is_dropped_for_the_report(self):
        text = "最少要能自掏 **$19,000**（你目前設定 $25,000）。"
        self.assertEqual(S.markdown(text), "最少要能自掏 **\\$19,000**（你目前設定 \\$25,000）。")
        self.assertEqual(S.plain(text), "最少要能自掏 $19,000（你目前設定 $25,000）。")

    def test_bands_put_a_rate_on_a_boundary_in_the_safer_band(self):
        rates = [0.0, 0.025, 0.0251, 0.05, 0.0501, 0.1, 0.1001, 1.0, float("nan")]
        out = S.bands(rates, "5")
        np.testing.assert_array_equal(out[:-1], [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertTrue(np.isnan(out[-1]))
        np.testing.assert_array_equal(S.bands([0.005, 0.01, 0.02, 0.021], "1"), [0, 1, 2, 3])


class AnswerTests(unittest.TestCase):
    def test_principal_ok_above_and_below_the_current_loan(self):
        view = S.principal_view(record())
        self.assertEqual((view["label"], view["value"]), ("最多可以借", "660 萬"))
        self.assertEqual((view["delta"], view["delta_color"], view["style"]), ("+160 萬（比目前）", "normal", "success"))
        self.assertEqual(view["sentence"],
                         "以目前其他設定，要讓破產機率在 5% 以下，最多可以借 **660 萬**（你目前設定 500 萬）。")
        self.assertEqual(view["captions"], ["借 660 萬時，破產機率約 4.95%（2,000 次模擬）。"])

        view = S.principal_view(record(principal=solved("principal", "ok", 3_000_000.0, 0.04)))
        self.assertEqual((view["delta"], view["style"]), ("-200 萬（比目前）", "warning"))
        self.assertEqual(view["captions"][1], "⚠️ 你目前設定的 500 萬已經超過這個上限。")

        view = S.principal_view(record(principal=solved("principal", "ok", 5_000_000.0, 0.04)))
        self.assertEqual((view["delta"], view["delta_color"], view["style"]), ("和目前相同", "off", "success"))

    def test_principal_whole_range_or_nothing(self):
        view = S.principal_view(record(principal=solved("principal", "all_meet", 50_000_000.0, 0.018)))
        self.assertEqual((view["value"], view["delta"], view["style"]), ("5,000 萬以上", None, "success"))
        self.assertEqual(view["sentence"], "以目前其他設定，就算借到搜尋上限 **5,000 萬**，破產機率也只有 1.8%，"
                                           "仍在 5% 以下（你目前設定 500 萬）。")
        self.assertEqual(view["captions"], [
            "借越多，每月還款和買進的資產都會等比例變大，每月自掏那筆固定的錢就越不夠看，所以破產機率不會一直升高，"
            "而是慢慢接近「完全不自掏」時的水準；這個水準在 5% 以下，所以整個搜尋範圍都達標。"
            "破產機率低不代表風險小：借越多，一旦出事賠得也越多。"])

        view = S.principal_view(record(principal=solved("principal", "none_meet", None, 0.12), lo=200_000.0))
        self.assertEqual((view["value"], view["delta"], view["style"]), ("不到 20 萬", None, "error"))
        self.assertEqual(view["sentence"], "以目前其他設定，就算只借 **20 萬**，破產機率也有 12.0%，達不到 5% 以下。")
        self.assertEqual(view["captions"], ["問題可能不在借多少，而是利率、年限、每月自掏的錢或還款的順序；可以看看下面的地圖。"])

    def test_without_salary_to_fall_back_on_the_answer_is_one_end_of_the_range(self):
        why = ("你沒有用薪水補貼還款。這時借多借少，每月還款和買進的資產都等比例變大或變小，破產機率幾乎不變，"
               "所以「最多可以借」不是「5,000 萬以上」就是「不到 10 萬」，不會落在中間。")
        for no_salary in (dict(salary_in_order=False), dict(cur_salary=0.0)):
            view = S.principal_view(record(principal=solved("principal", "all_meet", 5e7, 0.03), **no_salary))
            self.assertEqual(view["captions"], [why + "這次的破產機率在 5% 以下，所以整個搜尋範圍都達標。"
                                                      "破產機率低不代表風險小：借越多，一旦出事賠得也越多。"])
            view = S.principal_view(record(principal=solved("principal", "none_meet", None, 0.2), **no_salary))
            self.assertEqual(view["captions"], [why + "這次的破產機率超過 5%，調整本金沒有用；要從利率、年限、還款的順序或每月自掏的錢下手。"])
        self.assertEqual(S.map_salary_note(record(salary_in_order=False, cur_salary=0.0)), S.MAP_NOTE_NO_SALARY)
        self.assertEqual(S.map_salary_note(record(cur_salary=0.0)), S.MAP_NOTE_ZERO_SALARY)
        self.assertIsNone(S.map_salary_note(record()))
        self.assertTrue(S.MAP_NOTE_NO_SALARY.startswith("你沒有把薪水排進還款順位，所以地圖上每一格幾乎都一樣"))
        self.assertTrue(S.MAP_NOTE_ZERO_SALARY.startswith("你的每月最多自掏是 0，所以最左邊「$0」那一欄上下幾乎都一樣"))

    def test_salary_answers(self):
        view = S.salary_view(record())
        self.assertEqual((view["label"], view["value"]), ("每月最少要自掏", "$19,000"))
        self.assertEqual((view["delta"], view["delta_color"], view["style"]), ("-$6,000（比目前）", "inverse", "success"))
        self.assertEqual(view["sentence"],
                         "以目前其他設定，要讓破產機率在 5% 以下，每月最少要能自掏 **$19,000**（你目前設定 $25,000）。")
        self.assertEqual(view["captions"], ["每月最多自掏 $19,000 時，破產機率約 4.95%（2,000 次模擬）。"])

        view = S.salary_view(record(salary=solved("salary_cap", "ok", 31_000.0, 0.05)))
        self.assertEqual((view["delta"], view["style"]), ("+$6,000（比目前）", "warning"))
        self.assertEqual(view["captions"][1], "⚠️ 你目前設定的 $25,000 不夠，每月還差 $6,000。")

        view = S.salary_view(record(salary=solved("salary_cap", "all_meet", 0.0, 0.03)))
        self.assertEqual((view["value"], view["style"]), ("$0", "success"))
        self.assertEqual(view["sentence"], "以目前其他設定，就算每月完全不自掏，破產機率也只有 3.0%，仍在 5% 以下。")

        view = S.salary_view(record(salary=solved("salary_cap", "none_meet", None, 0.3)))
        self.assertEqual((view["value"], view["style"]), ("超過 $500,000", "error"))
        self.assertEqual(view["sentence"], "以目前其他設定，就算每月最多自掏到 **$500,000**，破產機率仍有 30.0%，達不到 5% 以下。")
        self.assertIsNone(S.salary_view(record(salary=None)))

    def test_report_rows(self):
        self.assertEqual(S.report_group(record(target="1")), "安全邊界（破產機率 ≤ 1%）")
        self.assertEqual(S.report_rows(record()), [
            ("最多可以借", "660 萬（目前 500 萬）"), ("借 660 萬時的破產機率", "4.95%"),
            ("每月最少要自掏", "$19,000（目前 $25,000）"), ("每月自掏 $19,000 時的破產機率", "4.95%")])
        self.assertEqual(S.report_rows(record(principal=solved("principal", "all_meet", 5e7, 0.01), salary=None)), [
            ("最多可以借", "5,000 萬以上"), ("借到 5,000 萬時的破產機率", "1.0%"),
            ("每月最少要自掏", "不計算（薪水沒有排進還款順位）")])
        self.assertEqual(S.report_rows(record(principal=solved("principal", "none_meet", None, 0.2), lo=200_000.0,
                                              salary=solved("salary_cap", "all_meet", 0.0, 0.03)))[1:], [
            ("只借 20 萬時的破產機率", "20.0%"), ("每月最少要自掏", "$0"), ("完全不自掏時的破產機率", "3.0%")])
        self.assertEqual(S.report_rows(record(salary=solved("salary_cap", "none_meet", None, 0.3)))[2:], [
            ("每月最少要自掏", "超過 $500,000"), ("每月自掏 $500,000 時的破產機率", "30.0%")])
        note = S.report_table_note(record())
        self.assertIn("最多可以借 660 萬（你目前設定 500 萬）", note)
        self.assertIn("每月最少要能自掏 $19,000", note)
        self.assertIn("藍色是在你選的上限（5%）以內", note)
        self.assertNotIn("**", note)


class MapTests(unittest.TestCase):
    def test_current_cell_is_found_by_value_and_framed(self):
        for cur_salary, column in ((25_000.0, 2), (0.0, 0)):
            rec = record(cur_salary=cur_salary)
            fig = S.map_figure(rec)
            self.assertEqual((fig.layout.xaxis.type, fig.layout.yaxis.type), ("category", "category"))
            text = fig.data[0].text
            marked = [(i, j) for i, row in enumerate(text) for j, cell in enumerate(row) if "◆ 目前" in cell]
            self.assertEqual(marked, [(2, column)])
            self.assertEqual([(s.x0, s.x1, s.y0, s.y1) for s in fig.layout.shapes], [(column - 0.5, column + 0.5, 1.5, 2.5)] * 2)
            self.assertEqual([s.line.color for s in fig.layout.shapes], ["#ffffff", "#0b0b0b"])
            table = S.map_table(rec)
            self.assertEqual(table.iloc[2, column], "◆ 1.0%")
            self.assertEqual((table == "◆ 1.0%").to_numpy().sum(), 1)

    def test_labels_colours_and_hover(self):
        rec = record(target="10")
        fig = S.map_figure(rec)
        heat = fig.data[0]
        self.assertEqual(list(heat.x), ["$12,500", "$18,750", "$25,000", "$31,250", "$37,500", "$50,000"])
        self.assertEqual(list(heat.y), ["250 萬", "375 萬", "500 萬", "625 萬", "750 萬", "1,000 萬"])
        self.assertEqual(list(heat.colorbar.ticktext),
                         ["很安全（≤ 5%）", "達標（5%–10%）", "超過（10%–20%）", "危險（> 20%）"])
        self.assertEqual((heat.zmin, heat.zmax, heat.xgap, heat.ygap), (-0.5, 3.5, 2, 2))
        self.assertEqual([c for _, c in heat.colorscale], ["#1c5cab"] * 2 + ["#86b6ef"] * 2 + ["#f0938f"] * 2 + ["#b8322f"] * 2)
        self.assertEqual(heat.hovertemplate,
                         "貸款本金 %{y}｜每月最多自掏 %{x}<br>破產機率 %{customdata}（2,000 次模擬）<extra></extra>")
        self.assertEqual((fig.layout.height, fig.layout.margin.t, fig.layout.margin.b), (400, 30, 10))
        self.assertEqual(len(fig.data), 1)                                    # no grey layer without blank cells
        self.assertEqual(list(S.map_figure(record(target="1")).data[0].colorbar.ticktext)[1], "達標（0.5%–1%）")

    def test_cells_that_could_not_be_computed_show_a_dash(self):
        rec = record()
        rec["grid"].iloc[0] = np.nan
        fig = S.map_figure(rec)
        grey, heat = fig.data                                                  # grey first, so it lies underneath
        self.assertEqual(list(grey.text[0]), ["—"] * 6)
        self.assertEqual(list(grey.text[1]), [""] * 6)
        self.assertEqual(list(grey.z[0]), [0] * 6)
        self.assertEqual(list(grey.z[1]), [None] * 6)
        self.assertEqual([c for _, c in grey.colorscale], ["#a3a29c", "#a3a29c"])
        self.assertEqual((grey.textfont.color, grey.showscale, grey.xgap, grey.ygap), ("#0b0b0b", False, 2, 2))
        self.assertEqual(grey.hovertemplate, "貸款本金 %{y} 不比開辦費多，無法計算<extra></extra>")
        self.assertEqual(list(heat.text[0]), [""] * 6)
        self.assertEqual(list(heat.z[0]), [None] * 6)
        self.assertFalse(heat.hoverongaps)
        self.assertEqual(list(S.map_table(rec).iloc[0]), ["—"] * 6)
        self.assertTrue(S.has_blank_cells(rec))
        self.assertIn(S.MAP_NOTE_FEE, S.report_table_note(rec))


class ComputeTests(unittest.TestCase):
    df = market()

    def test_both_limits_and_the_map_match_the_engine(self):
        p = params(annual_rate_pct=10.0, principal=10_000_000.0, seed=None, mc_paths=200)
        steps = []
        rec = S.compute(self.df, p, "5", on_step=lambda done, text: steps.append((done, text)))
        self.assertEqual(steps, [(0.0, "（1/3）找最多能借多少…"), (1 / 3, "（2/3）找每月最少要自掏多少…"),
                                 (2 / 3, "（3/3）畫破產機率地圖（36 格）…")])
        self.assertEqual(rec["principal"], E.solve_for(self.df, p, "principal", 0.05, 100_000.0, 1e8, 100_000))
        self.assertEqual(rec["salary"], E.solve_for(self.df, p, "salary_cap", 0.05, 0.0, 500_000.0, 1_000))
        self.assertTrue(rec["seed_is_random"])
        self.assertEqual(rec["grid"].shape, (6, 6))
        # The current cell equals the main Monte Carlo result with the same number of paths (D6).
        main = E.run_summary(self.df, dataclasses.replace(p, seed=42)).mc["Is_Ruined"].mean()
        self.assertEqual(rec["grid"].loc[p.principal, p.salary_cap], main)

    def test_salary_is_not_searched_when_it_is_not_a_source(self):
        p = params(source_order=(E.SELL, E.SELL_B), mc_paths=100)
        with mock.patch.object(E, "solve_for", wraps=E.solve_for) as solve:
            rec = S.compute(self.df, p, "10")
        self.assertEqual([call.args[2] for call in solve.call_args_list], ["principal"])
        self.assertIsNone(rec["salary"])
        self.assertEqual(rec["target"], "10")

    def test_loans_the_fee_would_swallow_are_left_blank(self):
        p = params(loan_fee=3_000_000.0, mc_paths=100)
        rec = S.compute(self.df, p, "5")
        self.assertEqual(rec["lo"], 3_100_000.0)
        grid = rec["grid"]
        self.assertTrue(grid.loc[2_500_000.0].isna().all())
        self.assertFalse(grid.loc[3_750_000.0].isna().any())


if __name__ == "__main__":
    unittest.main()
