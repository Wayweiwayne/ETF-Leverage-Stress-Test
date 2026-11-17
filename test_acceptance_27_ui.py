"""第 27 項（安全邊界）畫面的驗收測試。

依據：SPEC-v40 4.2 與決議 D4、D6、D7、D12、D13、D16、D17；DESIGN-v40 第 2 節（S-xx）與 R-30～R-32、R-35。
用 AppTest 離線跑整個 App（假行情）。計算核心照常執行，只有測試各種結論句時用固定的 SolveResult 代替。
"""
import dataclasses
import json
import re
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

import engine as E
from test_acceptance_helpers import AppHarness, Recorder, figure_texts, strip_markup, visible_texts

HEADER = "🛡️ 安全邊界：最多能借多少？"
BUTTON_KEY = "safe_run"
TARGET_LABEL = "你能接受的破產機率最多多少"
NOT_YET = "還沒有計算。按「計算安全邊界」開始。"
INTRO = ("用蒙地卡羅模擬反過來找：其他設定都不變的情況下，貸款本金最多可以多少、每月最少要能自掏多少，"
         "破產機率才不會超過你能接受的上限。要跑幾十次模擬，所以按按鈕才會計算。")
MAP_TITLE = "破產機率地圖：借多少 × 每月自掏多少"
STALE = "⚠️ 設定已變更，下面的安全邊界是用舊設定算的。按「計算安全邊界」重新計算。"
MULTIPLIERS = (0.5, 0.75, 1, 1.25, 1.5, 2)
ZERO_CAPS = [0.0, 5_000.0, 10_000.0, 20_000.0, 30_000.0, 50_000.0]
PCT = re.compile(r"(\d+(?:\.\d+)?)%")


@contextmanager
def spy_everywhere(name, side_effect=None):
    """把 engine.<name> 換成可計數的替身；其他模組用 from engine import 取得的同一個函式也一起換。"""
    real = getattr(E, name)
    mock = MagicMock(side_effect=side_effect or real)
    replaced = [m for m in list(sys.modules.values()) if getattr(m, name, None) is real]
    for module in replaced:
        setattr(module, name, mock)
    try:
        yield mock
    finally:
        for module in list(sys.modules.values()):
            if getattr(module, name, None) is mock:
                setattr(module, name, real)


def shown(element):
    """畫面上實際看到的文字：Markdown 的 \\$ 跳脫還原成 $，警示框的 icon 參數接在前面。"""
    body = element.value.replace("\\$", "$")
    icon = getattr(element.proto, "icon", "") if hasattr(element, "proto") else ""
    return f"{icon} {body}" if icon and not body.startswith(icon) else body


def shown_all(elements):
    return [shown(e) for e in elements]


def call_arg(call, index, name):
    return call.kwargs[name] if name in call.kwargs else call.args[index]


def solve_calls(mock):
    """[(field, target, lo, hi, step, params)]"""
    return [(call_arg(c, 2, "field"), call_arg(c, 3, "target_ruin"), call_arg(c, 4, "lo"), call_arg(c, 5, "hi"),
             call_arg(c, 6, "step"), call_arg(c, 1, "params")) for c in mock.call_args_list]


def fake_solver(results):
    """依 field 回傳指定的 (value, ruin_rate, status)。"""
    def solve(df, params, field, target_ruin, lo, hi, step):
        value, rate, status = results[field]
        if value == "hi":
            value = hi
        return E.SolveResult(field=field, value=value, ruin_rate=rate, target=target_ruin, status=status,
                             evaluations=5)
    return solve


class SafetyHarness(AppHarness):
    def control(self, at):
        for kind in ("segmented_control", "radio"):
            for w in getattr(at, kind):
                if w.label == TARGET_LABEL:
                    return w
        self.fail(f"找不到「{TARGET_LABEL}」")

    def set_target(self, at, text):
        widget = self.control(at)
        for raw in (text, text.rstrip("%"), int(text.rstrip("%")), int(text.rstrip("%")) / 100):
            try:
                if widget.format_func(raw) == text:
                    return widget.set_value(raw)
            except Exception:  # noqa: BLE001 - try the next way the option may be stored
                continue
        self.fail(f"目標破產率沒有「{text}」這個選項")

    def press(self, at, solver=None, rec=None):
        with spy_everywhere("solve_for", solver) as solve, spy_everywhere("sensitivity_grid") as grid:
            if rec is None:
                at = self.ok(at.button(key=BUTTON_KEY).click().run())
            else:
                with rec:
                    at = self.ok(at.button(key=BUTTON_KEY).click().run())
        return at, solve, grid

    def section_texts(self, at):
        return [strip_markup(t) for _, t in visible_texts(at)]

    def map_table(self, at):
        """S-39a：「用表格看這張地圖」裡的表（列＝本金標籤、欄＝自掏標籤）。"""
        for exp in at.expander:
            if exp.label == "用表格看這張地圖":
                tables = exp.table
                self.assertEqual(len(tables), 1)
                return tables[0].value
        self.fail("找不到「用表格看這張地圖」")

    def heatmap(self, at):
        for node in at.get("plotly_chart"):
            spec = json.loads(node.proto.spec)
            if any(trace.get("type") == "heatmap" for trace in spec["data"]):
                return spec
        self.fail("找不到熱圖")


class TriggerAndPlacementTests(SafetyHarness, unittest.TestCase):
    def test_nothing_is_solved_until_the_button_is_pressed(self):
        with spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid:
            at = self.start()
            self.assertIn(NOT_YET, shown_all(at.caption))                               # S-12
            at = self.ok(at.number_input(key="salary").set_value(30_000).run())                 # 改設定也不算（D17）
            at = self.ok(at.slider(key="rate").set_value(4.0).run())
        self.assertEqual((solve.call_count, grid.call_count), (0, 0))
        self.assertFalse(any(MAP_TITLE in t for t in self.section_texts(at)))

        at, solve, grid = self.press(at)
        self.assertEqual(sorted(field for field, *_ in solve_calls(solve)), ["principal", "salary_cap"])
        self.assertEqual(grid.call_count, 1)
        self.assertNotIn(NOT_YET, shown_all(at.caption))

    def test_results_stay_when_only_the_entry_month_changes(self):
        at, _, _ = self.press(self.start())
        before = [(m.label, m.value) for m in at.metric]
        with spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid:
            at = self.ok(at.selectbox(key="m").set_value(at.selectbox(key="m").options[5]).run())  # R-02
        self.assertEqual((solve.call_count, grid.call_count), (0, 0))
        self.assertEqual([(m.label, m.value) for m in at.metric], before)
        self.assertNotIn(STALE, shown_all(at.warning))

    def test_section_sits_right_below_the_two_result_columns(self):
        at = self.start()
        order = []

        def walk(node):
            kind = getattr(node, "type", "")
            if kind in ("header", "metric", "plotly_chart"):
                order.append((kind, getattr(node, "value", None) if kind == "header" else None))
            for child in getattr(node, "children", {}).values():
                walk(child)

        walk(at.main)
        heads = [i for i, (kind, value) in enumerate(order) if kind == "header" and value == HEADER]
        self.assertEqual(len(heads), 1, "S-03：標題應出現一次")
        metrics = [i for i, (kind, _) in enumerate(order) if kind == "metric"]
        charts = [i for i, (kind, _) in enumerate(order) if kind == "plotly_chart"]
        self.assertGreater(heads[0], max(metrics), "D12／S-01：在兩欄主要結果之後")
        self.assertLess(heads[0], min(charts), "S-01：在第一張結果圖之前")
        header = next(h for h in at.header if h.value == HEADER)
        self.assertEqual(header.proto.anchor, "safe-limit")                                      # S-03

    def test_intro_link_and_controls(self):
        at = self.start()
        captions = shown_all(at.caption)
        self.assertIn(INTRO, captions)                                                            # S-10
        self.assertIn("想知道最多能借多少？看下方的[安全邊界](#safe-limit)。", captions)              # S-04
        control = self.control(at)
        self.assertEqual(control.options, ["1%", "5%", "10%"])                                    # S-11
        self.assertEqual(control.format_func(control.value), "5%")
        self.assertIn("每 20 種可能的未來裡，最多只有 1 種會繳不出貸款", control.help)
        button = at.button(key=BUTTON_KEY)
        self.assertEqual(button.label, "🛡️ 計算安全邊界")
        self.assertEqual(button.proto.type, "secondary")


class TargetTests(SafetyHarness, unittest.TestCase):
    """S-11、D16：目標破產率 1%／5%／10%，網址參數 tgt。"""

    def test_link_value_sets_the_target(self):
        for tgt, text, target in (("1", "1%", 0.01), ("5", "5%", 0.05), ("10", "10%", 0.10)):
            with self.subTest(tgt=tgt):
                at = self.start(tgt=tgt)
                control = self.control(at)
                self.assertEqual(control.format_func(control.value), text)
                at, solve, _ = self.press(at)
                self.assertEqual({round(t, 6) for _, t, *_ in solve_calls(solve)}, {target})

    def test_bad_link_value_falls_back_to_five_percent(self):
        for bad in ("7", "abc", "", "0.05"):
            with self.subTest(tgt=bad):
                at = self.start(tgt=bad)
                control = self.control(at)
                self.assertEqual(control.format_func(control.value), "5%")

    def test_choice_is_written_to_the_address_and_default_is_left_out(self):
        at = self.start()
        self.assertNotIn("tgt", at.query_params)
        self.set_target(at, "10%")
        at = self.ok(at.run())
        self.assertEqual(at.query_params["tgt"], ["10"])
        self.set_target(at, "5%")
        at = self.ok(at.run())
        self.assertNotIn("tgt", at.query_params)

    def test_changing_the_target_marks_the_old_answer_stale(self):
        at, _, _ = self.press(self.start())
        self.set_target(at, "1%")
        at = self.ok(at.run())
        self.assertIn("⚠️ 你改了能接受的破產機率，下面還是 5% 的結果。按「計算安全邊界」重新計算。",
                      shown_all(at.warning))                                              # R-32

    def test_changing_a_setting_marks_the_old_answer_stale(self):
        at, _, _ = self.press(self.start())
        self.assertNotIn(STALE, shown_all(at.warning))
        at = self.ok(at.number_input(key="salary").set_value(30_000).run())
        self.assertIn(STALE, shown_all(at.warning))                                       # R-31
        self.assertTrue(any(MAP_TITLE in t for t in self.section_texts(at)), "R-31：舊的結果與熱圖照樣顯示")


class SearchRangeTests(SafetyHarness, unittest.TestCase):
    """SPEC 4.2、D4、D6、D7：搜尋範圍、單位與使用的設定。"""

    def solve_for_link(self, **query):
        with Recorder() as rec:
            at = self.start(**query)
        main_params = rec.summaries[0][0]
        at, solve, grid = self.press(at)
        return at, main_params, {field: rest for field, *rest in solve_calls(solve)}, grid

    def assertRange(self, call, target, lo, hi, step):
        got_target, got_lo, got_hi, got_step, _ = call
        self.assertAlmostEqual(got_target, target)
        self.assertEqual((float(got_lo), float(got_hi), float(got_step)), (lo, hi, step))

    def test_default_ranges(self):
        _, main, calls, _ = self.solve_for_link()
        self.assertRange(calls["principal"], 0.05, 100_000.0, 50_000_000.0, 100_000.0)
        self.assertRange(calls["salary_cap"], 0.05, 0.0, 500_000.0, 1_000.0)

    def test_upper_limit_is_one_hundred_million(self):
        _, _, calls, _ = self.solve_for_link(loan="2000")
        self.assertRange(calls["principal"], 0.05, 100_000.0, 100_000_000.0, 100_000.0)

    def test_tiny_loan_searches_a_single_point(self):
        _, _, calls, _ = self.solve_for_link(loan="1")     # 1 萬 × 10 = 10 萬，上限不可低於下限（D4）
        self.assertRange(calls["principal"], 0.05, 100_000.0, 100_000.0, 100_000.0)

    def test_loan_fee_raises_the_lower_limit(self):
        _, _, calls, _ = self.solve_for_link(lfee="100000")
        self.assertRange(calls["principal"], 0.05, 200_000.0, 50_000_000.0, 100_000.0)
        _, _, calls, _ = self.solve_for_link(loan="50", lfee="300000")
        self.assertRange(calls["principal"], 0.05, 400_000.0, 5_000_000.0, 100_000.0)

    def test_loan_fee_that_is_not_a_round_amount(self):
        # PO 補充：下限 = (開辦費 + 10 萬) 無條件捨去到 10 萬，也就是比開辦費大的最小 10 萬倍數。
        for fee, lo in (("6000", 100_000.0), ("150000", 200_000.0), ("199000", 200_000.0)):
            with self.subTest(fee=fee):
                _, _, calls, _ = self.solve_for_link(lfee=fee)
                self.assertEqual(float(calls["principal"][1]), lo)

    def test_uses_the_same_settings_and_paths_as_the_main_result(self):
        for query in ({}, {"paths": "1"}, {"seed": "0"}, {"type": "0", "jl": "1", "swan": "1"}):
            with self.subTest(**query):
                _, main, calls, grid = self.solve_for_link(**query)
                for field, call in calls.items():
                    used = call[4]
                    self.assertEqual(dataclasses.replace(used, seed=0, **{field: 1.0}),
                                     dataclasses.replace(main, seed=0, **{field: 1.0}),
                                     "R-33／D6：用主要結果那組設定（含路徑數）")
                    self.assertIn(used.seed, (None, 42), "D7：固定亂數時是 42；沒勾時交給引擎改用 42")
                    if main.seed is not None:
                        self.assertEqual(used.seed, main.seed)
                grid_call = grid.call_args
                self.assertEqual(call_arg(grid_call, 4, "mc_paths"), main.mc_paths, "D6／S-38：熱圖路徑數同主要結果")


class HeatmapTests(SafetyHarness, unittest.TestCase):
    def test_axes_follow_the_current_settings(self):
        at, _, grid = self.press(self.start())
        call = grid.call_args
        principals = [float(v) for v in call_arg(call, 2, "principals")]
        caps = [float(v) for v in call_arg(call, 3, "salary_caps")]
        self.assertEqual(principals, [round(5_000_000 * m) for m in MULTIPLIERS])               # S-31
        self.assertEqual(caps, [round(25_000 * m) for m in MULTIPLIERS])

    def test_zero_salary_cap_uses_the_fixed_columns(self):
        at, _, grid = self.press(self.start(salary="0"))
        caps = [float(v) for v in call_arg(grid.call_args, 3, "salary_caps")]
        self.assertEqual(caps, ZERO_CAPS)
        table = self.map_table(at)
        current = [(r, c) for r in table.index for c in table.columns if str(table.loc[r, c]).startswith("◆ ")]
        self.assertEqual(current, [("500 萬", "$0")], "S-35：自掏為 0 時目前格在第一欄")

    def test_table_has_36_cells_and_marks_the_current_one(self):
        with Recorder() as rec:
            at = self.start()
        main_rate = float(rec.summaries[0][1].mc["Is_Ruined"].mean())
        at, _, _ = self.press(at)
        table = self.map_table(at)                                                                # S-39a
        self.assertEqual(table.shape, (6, 6))
        self.assertEqual(sorted(table.index, key=lambda s: float(s.replace(",", "").split()[0])),
                         ["250 萬", "375 萬", "500 萬", "625 萬", "750 萬", "1,000 萬"])          # S-32
        self.assertEqual(sorted(table.columns, key=lambda s: float(s.strip("$").replace(",", ""))),
                         ["$12,500", "$18,750", "$25,000", "$31,250", "$37,500", "$50,000"])
        cells = {(r, c): str(table.loc[r, c]) for r in table.index for c in table.columns}
        self.assertTrue(all(PCT.fullmatch(v.removeprefix("◆ ")) for v in cells.values()), cells)
        current = [k for k, v in cells.items() if v.startswith("◆ ")]
        self.assertEqual(current, [("500 萬", "$25,000")])
        shown = float(PCT.fullmatch(cells[current[0]].removeprefix("◆ ")).group(1))
        self.assertAlmostEqual(shown, main_rate * 100, delta=0.051,
                               msg="D6／S-38：目前格的破產率要和上方主要結果相同")

    def test_figure(self):
        at, _, _ = self.press(self.start())
        self.assertTrue(any(MAP_TITLE in t for t in self.section_texts(at)))                     # S-30
        spec = self.heatmap(at)
        trace = next(t for t in spec["data"] if t.get("type") == "heatmap")
        self.assertEqual((len(trace["z"]), len(trace["z"][0])), (6, 6))
        self.assertEqual(spec["layout"]["xaxis"].get("type"), "category")                         # S-32
        self.assertEqual(spec["layout"]["yaxis"].get("type"), "category")
        texts = figure_texts(spec)
        self.assertIn("每月最多自掏（元）", texts)
        self.assertIn("貸款本金", texts)
        self.assertEqual(sum("◆ 目前" in t for t in texts if isinstance(t, str)), 1, "S-33：目前那格多一行「◆ 目前」")
        self.assertTrue(any(s.get("type") == "rect" for s in spec["layout"].get("shapes", [])), "S-35：目前格外框")
        self.assertIn("破產機率", " ".join(texts), "S-34：色標標題")

    def test_cells_at_or_below_the_loan_fee_show_a_dash(self):
        at, solve, grid = self.press(self.start(loan="50", lfee="300000"))
        for call in grid.call_args_list:
            self.assertTrue(all(float(p) > 300_000 for p in call_arg(call, 2, "principals")),
                            "D4：本金不大於開辦費的格子不能送去計算")
        table = self.map_table(at)
        self.assertEqual(table.shape, (6, 6))
        self.assertEqual([str(v) for v in table.loc["25 萬"]], ["—"] * 6)                         # D4
        others = [str(table.loc[r, c]) for r in table.index if r != "25 萬" for c in table.columns]
        self.assertTrue(all(PCT.search(v) for v in others))
        texts = figure_texts(self.heatmap(at))
        self.assertIn("—", texts)


class ConclusionTests(SafetyHarness, unittest.TestCase):
    """S-21、S-22、S-23：兩個答案的數字、結論句與顏色（用固定的 SolveResult）。"""

    def run_with(self, principal, salary_cap, **query):
        results = {"principal": principal, "salary_cap": salary_cap}
        at, _, _ = self.press(self.start(**query), solver=fake_solver(results))
        return at

    def metric(self, at, label):
        found = [m for m in at.metric if m.label == label]
        self.assertEqual(len(found), 1, label)
        return found[0].value, found[0].proto.delta

    def assertBox(self, at, kind, sentence):
        bodies = shown_all(getattr(at, kind)) + [e.value.replace("\\$", "$") for e in getattr(at, kind)]
        self.assertIn(sentence, bodies, f"S-23：應以 st.{kind} 顯示")

    def captions(self, at):
        return "\n".join(shown_all(at.caption))

    def test_both_answers_inside_the_boundary(self):
        at = self.run_with((6_600_000.0, 0.0466, "ok"), (19_000.0, 0.0466, "ok"))
        self.assertEqual(self.metric(at, "最多可以借"), ("660 萬", "+160 萬（比目前）"))
        self.assertEqual(self.metric(at, "每月最少要自掏"), ("$19,000", "-$6,000（比目前）"))
        self.assertBox(at, "success", "以目前其他設定，要讓破產機率在 5% 以下，最多可以借 **660 萬**（你目前設定 500 萬）。")
        self.assertBox(at, "success",
                       "以目前其他設定，要讓破產機率在 5% 以下，每月最少要能自掏 **$19,000**（你目前設定 $25,000）。")
        captions = self.captions(at)
        self.assertRegex(captions, r"借 660 萬時，破產機率約 4\.7%（2,?000 次模擬）。")
        self.assertRegex(captions, r"每月最多自掏 \$19,000 時，破產機率約 4\.7%（2,?000 次模擬）。")

    def test_current_settings_outside_the_boundary(self):
        at = self.run_with((3_000_000.0, 0.0495, "ok"), (30_000.0, 0.048, "ok"))
        self.assertEqual(self.metric(at, "最多可以借"), ("300 萬", "-200 萬（比目前）"))
        self.assertEqual(self.metric(at, "每月最少要自掏"), ("$30,000", "+$5,000（比目前）"))
        self.assertBox(at, "warning", "以目前其他設定，要讓破產機率在 5% 以下，最多可以借 **300 萬**（你目前設定 500 萬）。")
        self.assertBox(at, "warning",
                       "以目前其他設定，要讓破產機率在 5% 以下，每月最少要能自掏 **$30,000**（你目前設定 $25,000）。")
        captions = self.captions(at)
        self.assertIn("借 300 萬時，破產機率約 4.95%", captions, "G-4：離目標不到 0.1 個百分點時用兩位小數")
        self.assertIn("⚠️ 你目前設定的 500 萬已經超過這個上限。", captions)
        self.assertIn("⚠️ 你目前設定的 $25,000 不夠，每月還差 $5,000。", captions)

    def test_same_as_current(self):
        at = self.run_with((5_000_000.0, 0.03, "ok"), (25_000.0, 0.03, "ok"))
        self.assertEqual(self.metric(at, "最多可以借"), ("500 萬", "和目前相同"))
        self.assertEqual(self.metric(at, "每月最少要自掏"), ("$25,000", "和目前相同"))
        self.assertEqual(len(at.success), 2)

    def test_whole_range_meets_the_target(self):
        at = self.run_with(("hi", 0.012, "all_meet"), (0.0, 0.01, "all_meet"))
        self.assertEqual(self.metric(at, "最多可以借")[0], "5,000 萬以上")
        self.assertEqual(self.metric(at, "每月最少要自掏")[0], "$0")
        self.assertBox(at, "success", "以目前其他設定，就算借到搜尋上限 **5,000 萬**，破產機率也只有 1.2%，仍在 5% 以下"
                                      "（你目前設定 500 萬）。")
        self.assertBox(at, "success", "以目前其他設定，就算每月完全不自掏，破產機率也只有 1.0%，仍在 5% 以下。")
        self.assertIn("這通常代表每月自掏的上限設得很高，幾乎一直有薪水撐著；可以調低「每月最多自掏多少」再算一次。",
                      self.captions(at))

    def test_nothing_in_range_meets_the_target(self):
        at = self.run_with((None, 0.083, "none_meet"), (None, 0.072, "none_meet"))
        self.assertEqual(self.metric(at, "最多可以借")[0], "不到 10 萬")
        self.assertEqual(self.metric(at, "每月最少要自掏")[0], "超過 $500,000")
        self.assertBox(at, "error", "以目前其他設定，就算只借 **10 萬**，破產機率也有 8.3%，達不到 5% 以下。")
        self.assertBox(at, "error", "以目前其他設定，就算每月最多自掏到 **$500,000**，破產機率仍有 7.2%，達不到 5% 以下。")
        captions = self.captions(at)
        self.assertIn("問題可能不在借多少，而是利率、年限、每月自掏的錢或還款的順序；可以看看下面的地圖。", captions)
        self.assertIn("光靠多掏錢救不回來，可以試著降低貸款本金再算一次。", captions)

    def test_lower_limit_raised_by_the_loan_fee_is_quoted(self):
        # PO 補充：「不到 X 萬」與結論句用實際的搜尋下限（開辦費 30 萬 → 40 萬）。
        at = self.run_with((None, 0.6, "none_meet"), (4_000.0, 0.04, "ok"), loan="50", lfee="300000")
        self.assertEqual(self.metric(at, "最多可以借")[0], "不到 40 萬")
        self.assertBox(at, "error", "以目前其他設定，就算只借 **40 萬**，破產機率也有 60.0%，達不到 5% 以下。")

    def test_sentence_uses_the_chosen_target(self):
        at = self.run_with((6_600_000.0, 0.09, "ok"), (19_000.0, 0.09, "ok"), tgt="10")
        self.assertBox(at, "success", "以目前其他設定，要讓破產機率在 10% 以下，最多可以借 **660 萬**（你目前設定 500 萬）。")

    def test_salary_not_in_the_repayment_order(self):
        query = dict(p1="3", p2="5", p3="4", p4="4", p5="4")
        with spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid:
            at = self.start(**query)
            at = self.ok(at.button(key=BUTTON_KEY).click().run())
        self.assertEqual([field for field, *_ in solve_calls(solve)], ["principal"], "S-24：不跑自掏的求解")
        self.assertEqual(grid.call_count, 1, "S-24：熱圖照常畫")
        self.assertIn("你沒有把「薪水（自掏腰包）」排進還款順位，所以每月自掏多少都不影響結果，這一項不計算。",
                      shown_all(at.info))

    def test_unfixed_random_numbers_are_explained(self):
        at, _, _ = self.press(self.start(seed="0"))
        self.assertIn("你關閉了「固定亂數」，安全邊界固定用同一組抽樣計算，所以數字可能和上方的破產機率略有不同。",
                      shown_all(at.caption))                                              # S-25、D7
        at, _, _ = self.press(self.start())
        self.assertNotIn("你關閉了「固定亂數」", "\n".join(shown_all(at.caption)))


class ReportTests(SafetyHarness, unittest.TestCase):
    """S-40：算過且沒有過期才寫進報告。"""

    GROUP = "安全邊界（破產機率 ≤ 5%）"

    def test_not_calculated(self):
        with Recorder() as rec:
            self.start()
        parts = rec.last_report()
        self.assertEqual(dict(parts["settings"]).get("安全邊界"), "這次沒有計算")
        self.assertFalse(any(group.startswith("安全邊界") for group, _ in parts["summaries"]))
        self.assertNotIn(MAP_TITLE, [h for h, _, _ in parts["tables"]] + [h for h, _, _ in parts["figures"]])

    def test_calculated_results_are_in_the_report(self):
        rec = Recorder()
        at, _, _ = self.press(self.start(), solver=fake_solver({"principal": (6_600_000.0, 0.0466, "ok"),
                                                                "salary_cap": (19_000.0, 0.0466, "ok")}), rec=rec)
        parts = rec.last_report()
        settings = dict(parts["settings"])
        self.assertEqual(settings.get("安全邊界的目標"), "破產機率 ≤ 5%")
        self.assertNotIn("安全邊界", settings)
        groups = dict(parts["summaries"])
        self.assertIn(self.GROUP, groups)
        rows = dict(groups[self.GROUP])
        self.assertEqual(list(rows), ["最多可以借", "借到上限時的破產機率", "每月最少要自掏", "自掏到下限時的破產機率"])
        self.assertEqual(rows["最多可以借"], "660 萬（目前 500 萬）")
        self.assertEqual(rows["每月最少要自掏"], "$19,000（目前 $25,000）")
        self.assertEqual(rows["借到上限時的破產機率"], "4.7%")
        tables = {h: (frame, note) for h, frame, note in parts["tables"]}
        self.assertIn(MAP_TITLE, tables)
        frame, note = tables[MAP_TITLE]
        self.assertEqual(frame.shape, (6, 6))
        self.assertRegex(note, r"最多可以借 (\*\*)?660 萬(\*\*)?", "S-40：表下 caption 放兩句結論句")
        self.assertRegex(note, r"每月最少要能自掏 (\*\*)?\$19,000(\*\*)?")
        self.assertIn(MAP_TITLE, [h for h, _, _ in parts["figures"]])
        shown = {m.label: m.value for m in at.metric}
        reported = {label: value for group, rows in parts["summaries"] if group != self.GROUP for label, value in rows}
        self.assertTrue(set(reported) <= set(shown))

    def test_stale_results_are_left_out(self):
        at, _, _ = self.press(self.start())
        with Recorder() as rec:
            at = self.ok(at.number_input(key="salary").set_value(30_000).run())
        parts = rec.last_report()
        self.assertEqual(dict(parts["settings"]).get("安全邊界"), "這次沒有計算")
        self.assertFalse(any(group.startswith("安全邊界") for group, _ in parts["summaries"]))

    def test_salary_not_in_the_order_is_reported(self):
        rec = Recorder()
        self.press(self.start(p1="3", p2="5", p3="4", p4="4", p5="4"), rec=rec)
        rows = dict(dict(rec.last_report()["summaries"])[self.GROUP])
        self.assertEqual(rows["每月最少要自掏"], "不計算（薪水沒有排進還款順位）")


if __name__ == "__main__":
    unittest.main()
