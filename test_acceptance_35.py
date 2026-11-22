"""衝刺 3 第 35 項「開始計算按鈕」的驗收測試。

依據（優先順序由高到低）：
  1. SPEC-v40 第 10 節決議 D11（按鈕只放側欄最上方、主頁只有提示文字）、D13、D16、D17；
  2. SPEC-v40 第 6 節與最後一條驗收要求（用 mock 計數 engine.run_summary）；
  3. DESIGN-v40 第 3 節 R-01～R-60（R-21 的主頁按鈕已被 D11 取代：主頁不放按鈕）；
  4. 與故事 46 的關係：inc／udebt／mult／pmax／lmode／貸款種類都算進快照；L-08、L-09 立即顯示並停用按鈕；
     結果頁最上方的額度提示（L-01、L-03…）過期時顯示上一次的版本。
用 AppTest 離線跑整個 App（假行情）。計算次數用 spy 包住 engine.run_summary 計數（照常執行原函式）。
文案比對時忽略空白。
"""
import unittest
from contextlib import contextmanager
from unittest.mock import PropertyMock, patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import market_data
from test_acceptance_27_ui import BUTTON_KEY as SAFE_KEY
from test_acceptance_27_ui import STALE as SAFE_STALE
from test_acceptance_27_ui import SafetyHarness, shown, spy_everywhere
from test_acceptance_helpers import APP, Recorder
from test_acceptance_s46 import TYPE_LOAN, TYPE_MORTGAGE, S46Harness, l01a, l02, l03, norm

RUN_KEY = "run_sidebar"
RELOAD = "重新載入行情"
HINT = "⚠️ 設定已變更，結果尚未更新。下面還是上一次計算的結果，按側欄最上方的「開始計算」更新。"   # D11
SIDE_STALE = "⚠️ 設定已變更，結果尚未更新"                                                       # R-13
SIDE_FRESH = "✓ 結果對應目前的設定"                                                              # R-13
SIDE_AUTO = "自動重算已開啟：每次調整都會重新計算。"                                              # R-16
TOAST = "設定已變更。調好後按「開始計算」更新結果。"                                              # R-24
REPORT_STALE = "⚠️ 設定已變更：報告內容是上一次計算的結果。"                                      # R-25
NEEDS_RUN = "請先按「開始計算」更新上方結果，再計算安全邊界。"                                      # R-33
ERR_TOP = "❌ 參數有誤，請先修正"                                                                 # R-51
STALE_TARGET = "⚠️ 你改了能接受的破產機率，下面還是 5% 的結果。按「計算安全邊界」重新計算。"       # R-32
CUSTOM_SCENARIO = "自訂年度報酬率路徑"
KINDS = ("warning", "info", "error", "caption", "success", "markdown")


def qp(at, key):
    """AppTest 的 query_params 值是 list；取第一個。"""
    value = at.query_params[key]
    return value[0] if isinstance(value, list) else value


class Watch:
    """一次 App 執行期間的計數與記錄：engine.run_summary／run_trace／solve_for／sensitivity_grid 的呼叫次數。"""

    def __init__(self, summary, trace, solve, grid, rec):
        self.summary, self.trace, self.solve, self.grid, self.rec = summary, trace, solve, grid, rec

    @property
    def runs(self):
        return self.summary.call_count

    def reset(self):
        for mock in (self.summary, self.trace, self.solve, self.grid):
            mock.reset_mock()
        self.rec.reports.clear()
        self.rec.downloads.clear()
        self.rec.summaries.clear()


class RunButtonHarness(S46Harness, SafetyHarness):
    BASE_QUERY = {}   # 衝刺 2.5 之後預設值：信貸、本金 100 萬、平均月收入 5 萬

    def setUp(self):
        super().setUp()
        self.addCleanup(market_data._live_requests.clear)

    @contextmanager
    def watching(self):
        with spy_everywhere("run_summary") as summary, spy_everywhere("run_trace") as trace, \
                spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid, Recorder() as rec:
            yield Watch(summary, trace, solve, grid, rec)

    # ----- 讀畫面 -----

    def shown_in(self, block, kinds=KINDS):
        return [norm(shown(e)) for kind in kinds for e in getattr(block, kind)]

    def in_main(self, at, sentence):
        return any(norm(sentence) in t for t in self.shown_in(at.main))

    def in_side(self, at, sentence):
        return any(norm(sentence) in t for t in self.shown_in(at.sidebar))

    def run_button(self, at):
        found = [b for b in at.sidebar.button if b.key == RUN_KEY]
        self.assertEqual(len(found), 1, "側欄最上方要有一顆「開始計算」（key=run_sidebar）")
        return found[0]

    def press(self, at):
        return self.ok(self.run_button(at).click().run())

    def reload_button(self, at):
        found = [b for b in at.sidebar.button if b.label == RELOAD]
        self.assertEqual(len(found), 1)
        return found[0]

    def auto_toggle(self, at):
        found = [t for t in at.sidebar.toggle if t.label == "自動重算"]
        self.assertEqual(len(found), 1, "側欄要有「自動重算」開關（st.toggle）")
        return found[0]

    def change(self, at, key, value, kind="number_input"):
        getattr(at, kind)(key=key).set_value(value)
        return self.ok(at.run())

    def assertStale(self, at, msg=""):
        """過期：主頁提示、側欄 caption、側欄按鈕 primary 且可按；D11：主頁沒有任何「開始計算」按鈕。"""
        self.assertTrue(self.in_main(at, HINT), f"主頁沒有過期提示 {msg}")
        self.assertTrue(self.in_side(at, SIDE_STALE), f"側欄沒有過期 caption {msg}")
        self.assertFalse(self.in_side(at, SIDE_FRESH))
        button = self.run_button(at)
        self.assertEqual(button.proto.type, "primary")
        self.assertFalse(button.disabled)
        self.assertEqual(button.label, "開始計算")
        self.assertNoMainButton(at)

    def assertFresh(self, at, msg=""):
        """最新：主頁沒有任何過期提示、側欄 secondary 且可按（R-12）。"""
        self.assertFalse(self.in_main(at, SIDE_STALE), f"主頁不該有過期提示 {msg}")
        self.assertFalse(self.in_side(at, SIDE_STALE))
        self.assertTrue(self.in_side(at, SIDE_FRESH), f"側欄沒有「結果對應目前的設定」 {msg}")
        button = self.run_button(at)
        self.assertEqual(button.proto.type, "secondary")
        self.assertFalse(button.disabled)
        self.assertNoMainButton(at)

    def assertNoMainButton(self, at):
        keys = [getattr(b, "key", None) for b in at.main.button]
        self.assertNotIn("run_main", keys)
        self.assertEqual([b.label for b in at.main.button if "開始計算" in b.label], [], "D11：主頁不放按鈕")

    def metric_pairs(self, at):
        return [(m.label, m.value) for m in at.main.metric]


# ---------- TC-35-01、03、04：第一次打開、過期、按一次 ----------

class FirstOpenTests(RunButtonHarness, unittest.TestCase):
    def test_default_open_runs_once_and_is_fresh(self):
        with self.watching() as w:
            at = self.start()
        self.assertEqual(w.runs, 1, "第一次打開算 1 次")
        self.assertFresh(at)
        self.assertTrue(at.main.metric, "要看得到結果")

    def test_share_link_open_runs_once(self):
        with self.watching() as w:
            at = self.start(salary="30000", rate="4", loan="200", inc="0")
        self.assertEqual(w.runs, 1)
        self.assertFresh(at)
        self.assertEqual(at.number_input(key="salary").value, 30000)

    def test_run_button_is_the_first_thing_in_the_sidebar_and_toggle_follows(self):
        at = self.start()
        keys = [getattr(w, "key", None) for w in at.sidebar if getattr(w, "type", "") in ("button", "toggle")]
        self.assertEqual(keys[0], RUN_KEY, "R-10：按鈕在側欄最上方")
        self.assertEqual(keys[1], "auto", "R-14：自動重算開關在按鈕正下方")
        self.assertEqual(self.run_button(at).proto.icon if hasattr(self.run_button(at).proto, "icon") else ":material/play_arrow:",
                         ":material/play_arrow:")

    def test_auto_switch_default_off_and_help(self):
        at = self.start()
        toggle = self.auto_toggle(at)
        self.assertFalse(toggle.value)
        self.assertIn("打開後，每次調整設定都會立刻重新計算", toggle.help)
        self.assertNotIn("auto", at.query_params)

    def test_first_open_with_input_error_does_not_run_and_disables_button(self):
        with self.watching() as w:
            at = self.start(inc="5", udebt="120")
        self.assertEqual(w.runs, 0)
        self.assertTrue(self.run_button(at).disabled)
        self.assertTrue(self.in_main(at, ERR_TOP))


class FirstRunLaterTests(RunButtonHarness, unittest.TestCase):
    def test_fixing_the_first_input_error_runs_once_without_a_hint(self):
        """R-40：session 裡還沒有任何結果時，自動算一次，不顯示過期提示。"""
        with self.watching() as w:
            at = self.start(inc="5", udebt="120")
            self.assertEqual(w.runs, 0)
            at = self.change(at, "udebt", 0)
            self.assertEqual(w.runs, 1)
            self.assertFresh(at)


class ResampleTests(RunButtonHarness, unittest.TestCase):
    def test_press_with_fixed_seed_off_draws_again(self):
        """R-12：關閉「固定亂數」時，再按一次代表「重新抽樣」，所以每按一次都要真的重新計算。"""
        with self.watching() as w:
            at = self.start(seed="0")
            self.assertEqual(w.runs, 1)
            w.reset()
            at = self.press(at)
            self.assertEqual(w.runs, 1, "按鈕沒有重新抽樣（run_summary 的 st.cache_data 對 seed=None 命中快取）")


class StaleTests(RunButtonHarness, unittest.TestCase):
    def three_changes(self, at):
        at = self.change(at, "salary", 30000)
        at = self.change(at, "fee", 0.2)
        at = self.change(at, "buf", 3, kind="slider")
        return at

    def test_three_changes_run_zero_times_and_keep_old_results(self):
        with self.watching() as w:
            at = self.start()
            before = self.metric_pairs(at)
            w.reset()
            at = self.change(at, "salary", 30000)
            self.assertStale(at, "改 1 個")
            at = self.change(at, "fee", 0.2)
            self.assertStale(at, "改 2 個")
            at = self.change(at, "buf", 3, kind="slider")
            self.assertStale(at, "改 3 個")
            self.assertEqual(w.runs, 0, "連續改三個設定算 0 次")
            self.assertEqual(self.metric_pairs(at), before, "畫面保留上一次的指標")
            self.assertEqual(w.solve.call_count + w.grid.call_count, 0)

    def test_hint_is_exact_and_not_a_button(self):
        at = self.start()
        at = self.change(at, "salary", 30000)
        self.assertTrue(any(norm(HINT) in t for t in self.shown_in(at.main, ("warning",))), "提示用 st.warning")
        self.assertStale(at)

    def test_hint_sits_at_the_top_of_the_results(self):
        """R-20、DESIGN 8.2：提示在標題之下、額度提示與所有結果之上。"""
        at = self.start()
        at = self.change(at, "salary", 30000)
        texts = [norm(shown(e)) for e in at.main if getattr(e, "type", "") in ("warning", "markdown", "caption", "info", "header", "subheader", "metric")]
        hint_at = next(i for i, t in enumerate(texts) if norm(HINT) in t)
        first_result = next(i for i, t in enumerate(texts) if "依平均月收入" in t or "歷史回測" in t)
        self.assertLess(hint_at, first_result)

    def test_toast_only_on_the_fresh_to_stale_transition(self):
        at = self.start()
        at = self.change(at, "salary", 30000)
        self.assertTrue(any(norm(TOAST) in norm(t.value) for t in at.toast), "R-24：剛過期那一次跳 toast")
        at = self.change(at, "fee", 0.2)
        self.assertFalse(any("設定已變更" in t.value for t in at.toast), "連續改第二個不再跳")

    def test_press_once_runs_once_and_clears_the_hint(self):
        with self.watching() as w:
            at = self.start()
            before = self.metric_pairs(at)
            at = self.change(at, "rate", 6.0, kind="slider")
            at = self.change(at, "loan", 90)
            w.reset()
            at = self.press(at)
            self.assertEqual(w.runs, 1, "按一次按鈕算 1 次")
            self.assertFresh(at)
            self.assertNotEqual(self.metric_pairs(at), before, "結果更新")
            self.assertEqual(w.rec.summaries[-1][0].annual_rate_pct, 6.0)
            self.assertEqual(w.rec.summaries[-1][0].principal, 900_000)

    def test_press_again_when_fresh_is_allowed(self):
        at = self.start()
        self.assertFalse(self.run_button(at).disabled, "R-12：最新時按鈕不 disabled（關閉固定亂數時代表重新抽樣）")
        at = self.press(at)
        self.assertFresh(at)

    def test_back_to_the_original_value_is_not_stale(self):
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.change(at, "salary", 30000)
            self.assertStale(at)
            at = self.change(at, "salary", 25000)
            self.assertFresh(at, "改回原值")
            self.assertEqual(w.runs, 0)

    def test_back_for_one_of_two_changes_is_still_stale(self):
        at = self.start()
        at = self.change(at, "salary", 30000)
        at = self.change(at, "fee", 0.2)
        at = self.change(at, "salary", 25000)
        self.assertStale(at)
        at = self.change(at, "fee", 0.1425)
        self.assertFresh(at)

    def test_each_kind_of_input_counts_as_a_change(self):
        """R-01：側欄所有輸入都算，包括代號、扣款日、自動還原分割。"""
        cases = [("a", "0056.TW", "text_input"), ("proxy", "", "text_input"), ("payday", 20, "selectbox"),
                 ("fix", False, "checkbox"), ("reinv", False, "checkbox"), ("years", 5, "slider"),
                 ("dca", "每月投入整筆應繳金額 (舊版算法)", "selectbox"), ("paths", 5000, "selectbox")]
        for key, value, kind in cases:
            with self.subTest(key=key):
                with self.watching() as w:
                    at = self.start()
                    w.reset()
                    at = self.change(at, key, value, kind=kind)
                    self.assertEqual(w.runs, 0)
                    self.assertStale(at, key)

    def test_changing_ticker_keeps_old_results_on_screen(self):
        at = self.start()
        before = self.metric_pairs(at)
        at = self.change(at, "a", "0056.TW", kind="text_input")
        self.assertStale(at)
        self.assertEqual(self.metric_pairs(at), before)

    def test_fields_that_appear_with_a_checkbox_still_work(self):
        """TC-35-11：不用 st.form，依勾選出現的欄位立即出現。"""
        with self.watching() as w:
            at = self.start()
            self.assertTrue([t for t in at.text_input if t.key == "b"])
            w.reset()
            at = self.change(at, "reinv", False, kind="checkbox")
            self.assertEqual([t for t in at.text_input if t.key == "b"], [])
            self.assertEqual(w.runs, 0)
            self.assertStale(at)
            at = self.change(at, "reinv", True, kind="checkbox")
            self.assertTrue([t for t in at.text_input if t.key == "b"])
            self.assertFresh(at)

    def test_hidden_scenario_field_appears_immediately(self):
        at = self.start()
        at = self.change(at, "scen", CUSTOM_SCENARIO, kind="selectbox")
        self.assertTrue([t for t in at.text_input if t.key == "path"])
        self.assertStale(at)


# ---------- 故事 46：信貸欄位算進快照 ----------

class CreditSnapshotTests(RunButtonHarness, unittest.TestCase):
    def test_every_credit_field_counts(self):
        """inc、udebt、mult、pmax、lmode、貸款種類都是會影響計算的設定。"""
        cases = [("inc", 6, "number_input"), ("udebt", 10, "number_input"), ("mult", 18, "number_input"),
                 ("pmax", 300, "number_input"), ("lmode", "用估計的可核貸金額", "radio"), ("type", TYPE_MORTGAGE, "radio")]
        for key, value, kind in cases:
            with self.subTest(key=key):
                with self.watching() as w:
                    at = self.start()
                    w.reset()
                    widget = getattr(at, kind)(key=key)
                    if kind == "radio" and key == "lmode":
                        value = next(o for o in widget.options if "估計" in o)
                    at = self.change(at, key, value, kind=kind)
                    self.assertEqual(w.runs, 0)
                    self.assertStale(at, key)

    def test_credit_fields_back_to_original_not_stale(self):
        at = self.start()
        at = self.change(at, "udebt", 10)
        self.assertStale(at)
        at = self.change(at, "udebt", 0)
        self.assertFresh(at)

    def test_main_notice_keeps_old_version_while_sidebar_updates_at_once(self):
        """側欄的 L-02／L-04 立即顯示；結果頁最上方的 L-03 仍是上一次的版本，L-01a 要等按下按鈕才出現。"""
        with self.watching() as w:
            at = self.start()
            old_l03 = l03(5, 110, 100, 500, 110)
            self.assertTrue(self.in_main(at, old_l03))
            w.reset()
            at = self.change(at, "udebt", 60)
            self.assertEqual(w.runs, 0)
            self.assertTrue(self.in_side(at, l02(50)), "L-02 立即顯示在側欄")
            self.assertTrue(self.in_main(at, old_l03), "結果頁最上方還是上一次的額度提示")
            self.assertFalse(self.in_main(at, "最多只能借"), "L-01a 還沒有")
            self.assertStale(at)
            at = self.press(at)
            self.assertEqual(w.runs, 1)
            self.assertTrue(self.in_main(at, l01a(100, 50)))
            self.assertTrue(self.in_main(at, l03(5, 50, 40, 500, 50, 60)))
            self.assertFalse(self.in_main(at, old_l03))
            self.assertEqual(w.rec.summaries[-1][0].principal, 500_000, "以可借上限 50 萬計算")

    def test_l08_shows_at_once_and_disables_the_button(self):
        with self.watching() as w:
            at = self.start()
            before = self.metric_pairs(at)
            w.reset()
            at = self.change(at, "udebt", 120)
            self.assertEqual(w.runs, 0)
            self.assertTrue(self.in_side(at, "已經用完法規上限"), "L-08 立即顯示")
            button = self.run_button(at)
            self.assertTrue(button.disabled, "L-08：開始計算停用")
            self.assertTrue(self.in_main(at, ERR_TOP))
            self.assertTrue(self.in_main(at, "信貸額度：既有無擔保債務已用完法規上限，無法再借"))
            self.assertEqual(self.metric_pairs(at), before, "R-51：上一次的結果仍留在下面")
            self.assertTrue(self.in_main(at, HINT), "R-51：照樣標示過期")
            self.assertNoMainButton(at)
            at = self.change(at, "udebt", 0)
            self.assertFalse(self.run_button(at).disabled)
            self.assertFresh(at)

    def test_l09_disables_the_button(self):
        at = self.start()
        at = self.change(at, "udebt", 110)   # 估計可核貸 = 5×20−110 < 0，可借上限 0
        at = self.change(at, "udebt", 100)   # 可借上限 10 萬，估計 0
        at = self.change(at, "lmode", next(o for o in at.radio(key="lmode").options if "估計" in o), kind="radio")
        self.assertTrue(self.in_side(at, "用估計的可核貸金額算出來是 0 萬，無法計算"))
        self.assertTrue(self.run_button(at).disabled)

    def test_report_settings_are_from_the_last_run(self):
        """報告的設定表（含額度列）在過期期間和上一次計算時完全一樣。"""
        with self.watching() as w:
            at = self.start()
            first = list(w.rec.last_report()["settings"])
            w.reset()
            at = self.change(at, "udebt", 60)
            at = self.change(at, "inc", 8)
            self.assertEqual(list(w.rec.last_report()["settings"]), first)


# ---------- TC-35-06、R-16、R-17：自動重算 ----------

class AutoTests(RunButtonHarness, unittest.TestCase):
    def test_auto_link_recalculates_after_every_change(self):
        with self.watching() as w:
            at = self.start(auto="1")
            self.assertEqual(w.runs, 1)
            self.assertTrue(self.auto_toggle(at).value)
            self.assertEqual(qp(at, "auto"), "1")
            w.reset()
            at = self.change(at, "salary", 30000)
            self.assertEqual(w.runs, 1)
            at = self.change(at, "fee", 0.2)
            self.assertEqual(w.runs, 2)
            at = self.change(at, "rate", 5.0, kind="slider")
            self.assertEqual(w.runs, 3)
            self.assertEqual(w.rec.summaries[-1][0].annual_rate_pct, 5.0)
            self.assertFalse(self.in_main(at, SIDE_STALE), "R-16：主頁沒有過期提示")

    def test_auto_on_hides_the_run_button_and_shows_caption(self):
        at = self.start(auto="1")
        self.assertEqual([b for b in at.sidebar.button if b.key == RUN_KEY], [], "R-16：自動重算開啟時沒有按鈕")
        self.assertTrue(self.in_side(at, SIDE_AUTO))
        self.assertFalse(self.in_side(at, SIDE_FRESH))
        self.assertFalse(self.in_side(at, SIDE_STALE))

    def test_switching_on_while_stale_runs_once_immediately(self):
        with self.watching() as w:
            at = self.start()
            at = self.change(at, "salary", 30000)
            at = self.change(at, "rate", 5.0, kind="slider")
            self.assertStale(at)
            w.reset()
            toggle = self.auto_toggle(at)
            at = self.ok(toggle.set_value(True).run())
            self.assertEqual(w.runs, 1, "R-17：切到開啟時結果過期，立刻算一次")
            self.assertEqual(w.rec.summaries[-1][0].salary_cap, 30000)
            self.assertFalse(self.in_main(at, SIDE_STALE))
            self.assertEqual(qp(at, "auto"), "1")
            self.assertTrue(self.in_side(at, SIDE_AUTO))

    def test_switching_on_while_fresh_does_not_mark_stale_or_need_a_run(self):
        at = self.start()
        at = self.ok(self.auto_toggle(at).set_value(True).run())
        self.assertFalse(self.in_main(at, SIDE_STALE))
        self.assertTrue(self.in_side(at, SIDE_AUTO))

    def test_switching_off_goes_back_to_the_button(self):
        with self.watching() as w:
            at = self.start(auto="1")
            at = self.ok(self.auto_toggle(at).set_value(False).run())
            self.assertNotIn("auto", at.query_params, "關閉是預設，不寫進網址")
            self.assertFresh(at)
            w.reset()
            at = self.change(at, "salary", 30000)
            self.assertEqual(w.runs, 0)
            self.assertStale(at)

    def test_toggle_itself_is_not_a_settings_change(self):
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.ok(self.auto_toggle(at).set_value(True).run())
            at = self.ok(self.auto_toggle(at).set_value(False).run())
            self.assertEqual(w.runs, 0)
            self.assertFresh(at)

    def test_auto_on_never_computes_the_safety_limit(self):
        """D17、R-34：安全邊界永遠按按鈕才算，自動重算只讓它過期。"""
        with self.watching() as w:
            at = self.start(auto="1")
            at = self.ok(at.button(key=SAFE_KEY).click().run())
            self.assertGreater(w.solve.call_count, 0)
            w.reset()
            at = self.change(at, "salary", 30000)
            self.assertEqual(w.runs, 1)
            self.assertEqual(w.solve.call_count, 0, "自動重算不重算安全邊界")
            self.assertEqual(w.grid.call_count, 0)
            self.assertTrue(self.in_main(at, SAFE_STALE), "只標示過期")


# ---------- TC-35-07、R-02、R-60：不影響計算的操作；過期期間都是上一次的版本 ----------

class NoEffectTests(RunButtonHarness, unittest.TestCase):
    def other_month(self, at):
        select = at.selectbox(key="m")
        return next(o for o in select.options if o != select.value)

    def test_month_change_is_instant_and_not_stale(self):
        with self.watching() as w:
            at = self.start()
            before = self.metric_pairs(at)
            w.reset()
            month = self.other_month(at)
            at = self.change(at, "m", month, kind="selectbox")
            self.assertEqual(w.runs, 0, "進場月份不重新計算")
            self.assertFresh(at)
            self.assertEqual(self.metric_pairs(at), before)
            self.assertEqual(qp(at, "m"), month)
            self.assertTrue(self.in_main(at, f"{month} 進場"), "逐月明細立刻換成新月份")
            self.assertGreater(w.trace.call_count, 0)

    def test_month_change_while_stale_stays_stale_and_uses_old_settings(self):
        """R-60：逐月明細用快照的 params，不是目前的。"""
        with self.watching() as w:
            at = self.start()
            at = self.change(at, "salary", 30000)
            self.assertStale(at)
            w.reset()
            month = self.other_month(at)
            at = self.change(at, "m", month, kind="selectbox")
            self.assertEqual(w.runs, 0)
            self.assertStale(at)
            self.assertTrue(self.in_main(at, f"{month} 進場"))
            self.assertGreater(w.trace.call_count, 0, "逐月明細要重算（換月份）")
            for call in w.trace.call_args_list:
                self.assertEqual(call.args[1].salary_cap, 25000, "逐月明細用上一次計算的設定")

    def test_target_change_alone_does_not_stale_main_results(self):
        """D16：只改目標破產率，主要結果不過期。"""
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.ok(self.set_target(at, "10%").run())
            self.assertEqual(w.runs, 0)
            self.assertFresh(at)


class OldSettingsTests(RunButtonHarness, unittest.TestCase):
    """R-60：過期期間畫面上、報告裡的每樣東西都是上一次計算的版本。"""

    def test_report_and_share_link_use_the_last_run(self):
        url = patch.object(type(st.context), "url", new_callable=PropertyMock, return_value="http://qa.test/app")
        with url, self.watching() as w:
            at = self.start(salary="20000")
            self.assertIn("salary=20000", w.rec.last_report()["share_url"])
            w.reset()
            at = self.change(at, "salary", 30000)
            at = self.change(at, "rate", 6.0, kind="slider")
            self.assertStale(at)
            kwargs = w.rec.last_report()
            self.assertIsNotNone(kwargs, "過期時報告仍照常產生（對應上一次的結果）")
            rows = dict(kwargs["settings"])
            self.assertEqual(rows["每月最多自掏"], "$20,000")
            self.assertIn("3.5%", rows["貸款"])
            self.assertNotIn("6%", rows["貸款"])
            self.assertIn("salary=20000", kwargs["share_url"], "分享連結用快照當時的網址參數")
            self.assertNotIn("salary=30000", kwargs["share_url"])
            self.assertNotIn("rate=6", kwargs["share_url"])
            self.assertEqual(w.runs, 0)

    def test_report_after_pressing_uses_the_new_settings(self):
        url = patch.object(type(st.context), "url", new_callable=PropertyMock, return_value="http://qa.test/app")
        with url, self.watching() as w:
            at = self.start(salary="20000")
            at = self.change(at, "salary", 30000)
            at = self.press(at)
            kwargs = w.rec.last_report()
            self.assertEqual(dict(kwargs["settings"])["每月最多自掏"], "$30,000")
            self.assertIn("salary=30000", kwargs["share_url"])

    def test_report_caption_warns_while_stale(self):
        at = self.start()
        self.assertFalse(self.in_main(at, REPORT_STALE))
        at = self.change(at, "salary", 30000)
        self.assertTrue(self.in_main(at, REPORT_STALE), "R-25")

    def test_csv_downloads_keep_the_last_run(self):
        with self.watching() as w:
            self.start()
            first = [(n, f.copy()) for _, n, f in w.rec.csv_frames()]
            at = self.start()
            w.reset()
            at = self.change(at, "salary", 30000)
            at = self.change(at, "rate", 6.0, kind="slider")
            stale = [(n, f) for _, n, f in w.rec.csv_frames()]
            self.assertTrue(stale)
            for (n1, f1), (n2, f2) in zip(first, stale):
                self.assertEqual(n1, n2)
                pd.testing.assert_frame_equal(f1, f2)

    def test_loan_type_notice_and_report_row_come_from_the_snapshot(self):
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.change(at, "type", TYPE_MORTGAGE, kind="radio")
            self.assertStale(at)
            self.assertEqual(w.runs, 0)
            self.assertTrue(self.in_main(at, l03(5, 110, 100, 500, 110)), "額度提示仍是信貸的")
            rows = dict(w.rec.last_report()["settings"])
            self.assertIn(TYPE_LOAN.split("（")[0], rows["貸款"])
            self.assertNotIn(TYPE_MORTGAGE.split("（")[0], rows["貸款"])

    def test_old_results_come_back_when_switching_back(self):
        at = self.start()
        before = self.metric_pairs(at)
        at = self.change(at, "type", TYPE_MORTGAGE, kind="radio")
        at = self.change(at, "type", TYPE_LOAN, kind="radio")
        self.assertFresh(at)
        self.assertEqual(self.metric_pairs(at), before)


# ---------- TC-35-08：輸入錯誤 ----------

class InputErrorTests(RunButtonHarness, unittest.TestCase):
    def test_bad_custom_path_shows_at_once_and_disables_the_button(self):
        with self.watching() as w:
            at = self.start(scen="3")
            before = self.metric_pairs(at)
            w.reset()
            at = self.change(at, "path", "abc", kind="text_input")
            self.assertEqual(w.runs, 0)
            self.assertTrue(at.sidebar.error, "欄位下方的錯誤立即顯示")
            self.assertTrue(self.in_main(at, ERR_TOP))
            self.assertTrue(self.in_main(at, "自訂年度報酬率路徑："))
            button = self.run_button(at)
            self.assertTrue(button.disabled, "R-51：有輸入錯誤時按鈕停用")
            self.assertIn("請先修正上面的錯誤", button.help)
            self.assertEqual(self.metric_pairs(at), before, "上一次的結果仍留在下面")
            self.assertNoMainButton(at)
            at = self.change(at, "path", "5, 10, -20, 15, 5", kind="text_input")
            self.assertFalse(self.run_button(at).disabled)
            self.assertFalse(self.in_main(at, ERR_TOP))
            self.assertFresh(at)

    def test_bad_path_with_auto_on_does_not_run(self):
        with self.watching() as w:
            at = self.start(scen="3", auto="1")
            w.reset()
            at = self.change(at, "path", "abc", kind="text_input")
            self.assertEqual(w.runs, 0)
            self.assertTrue(self.in_main(at, ERR_TOP))

    def test_ticker_format_error_shows_without_a_run(self):
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.change(at, "a", "ab cd!!", kind="text_input")
            self.assertEqual(w.runs, 0)
            self.assertStale(at)


# ---------- TC-35-09：網址列 ----------

class UrlTests35(RunButtonHarness, unittest.TestCase):
    def test_address_bar_follows_inputs_before_any_run(self):
        with self.watching() as w:
            at = self.start()
            w.reset()
            at = self.change(at, "salary", 30000)
            at = self.change(at, "rate", 5.0, kind="slider")
            self.assertEqual(w.runs, 0)
            self.assertEqual(qp(at, "salary"), "30000")
            self.assertEqual(qp(at, "rate"), "5")

    def test_refresh_runs_once_with_current_inputs(self):
        with self.watching() as w:
            at = self.start()
            at = self.change(at, "salary", 30000)
            at = self.change(at, "rate", 5.0, kind="slider")
            link = {k: at.query_params[k] for k in at.query_params}
            w.reset()
            fresh = AppTest.from_file(APP, default_timeout=180)
            for key, value in link.items():
                fresh.query_params[key] = value
            fresh = self.ok(fresh.run())
            self.assertEqual(w.runs, 1, "重新整理＝用目前的輸入自動算一次")
            self.assertEqual(w.rec.summaries[-1][0].salary_cap, 30000)
            self.assertEqual(w.rec.summaries[-1][0].annual_rate_pct, 5.0)
            self.assertFresh(fresh)

    def test_auto_param_in_link_only_when_on(self):
        at = self.start()
        self.assertNotIn("auto", at.query_params)
        at = self.ok(self.auto_toggle(at).set_value(True).run())
        self.assertEqual(qp(at, "auto"), "1")


# ---------- TC-35-10：安全邊界 ----------

class SafetyStaleTests(RunButtonHarness, unittest.TestCase):
    def computed(self, w, **query):
        at = self.start(**query)
        at = self.ok(at.button(key=SAFE_KEY).click().run())
        self.assertGreater(w.solve.call_count, 0)
        w.reset()
        return at

    def test_safety_button_blocked_while_main_results_are_stale(self):
        """D13、R-33：主要結果過期時停用，並說明要先按「開始計算」。"""
        with self.watching() as w:
            at = self.computed(w)
            self.assertFalse(at.button(key=SAFE_KEY).disabled)
            at = self.change(at, "salary", 30000)
            self.assertStale(at)
            self.assertTrue(at.button(key=SAFE_KEY).disabled)
            self.assertTrue(self.in_main(at, NEEDS_RUN))
            self.assertTrue(self.in_main(at, SAFE_STALE), "R-31：安全邊界標示過期，舊結果照樣顯示")
            self.assertTrue(any("破產率" in m.label or "借" in m.label for m in at.main.metric))
            self.assertEqual(w.solve.call_count, 0)

    def test_blocked_even_before_the_first_safety_run(self):
        at = self.start()
        at = self.change(at, "salary", 30000)
        self.assertTrue(at.button(key=SAFE_KEY).disabled)
        self.assertTrue(self.in_main(at, NEEDS_RUN))

    def test_after_run_button_the_safety_block_is_stale_but_enabled(self):
        with self.watching() as w:
            at = self.computed(w)
            at = self.change(at, "salary", 30000)
            at = self.press(at)
            self.assertFresh(at)
            self.assertFalse(at.button(key=SAFE_KEY).disabled)
            self.assertFalse(self.in_main(at, NEEDS_RUN))
            self.assertTrue(self.in_main(at, SAFE_STALE), "安全邊界是用舊設定算的")
            self.assertEqual(w.solve.call_count, 0, "按「開始計算」不會順便算安全邊界")
            at = self.ok(at.button(key=SAFE_KEY).click().run())
            self.assertFalse(self.in_main(at, SAFE_STALE))
            self.assertEqual(w.solve.call_args_list[0].args[1].salary_cap, 30000, "安全邊界用主結果那組設定")

    def test_target_only_change_text(self):
        """R-32、D16：只改目標破產率，用專屬文字；主結果不過期；按鈕可按。"""
        with self.watching() as w:
            at = self.computed(w)
            at = self.ok(self.set_target(at, "10%").run())
            self.assertEqual(w.runs, 0)
            self.assertFresh(at)
            self.assertTrue(self.in_main(at, STALE_TARGET))
            self.assertFalse(self.in_main(at, SAFE_STALE))
            self.assertFalse(at.button(key=SAFE_KEY).disabled)
            self.assertFalse(self.in_main(at, NEEDS_RUN))

    def test_target_change_back_is_current_again(self):
        with self.watching() as w:
            at = self.computed(w)
            at = self.ok(self.set_target(at, "10%").run())
            at = self.ok(self.set_target(at, "5%").run())
            self.assertFalse(self.in_main(at, STALE_TARGET))
            self.assertFalse(self.in_main(at, SAFE_STALE))

    def test_settings_and_target_changed_together_use_the_settings_text(self):
        with self.watching() as w:
            at = self.computed(w)
            at = self.change(at, "salary", 30000)
            at = self.ok(self.set_target(at, "10%").run())
            self.assertTrue(self.in_main(at, SAFE_STALE))
            self.assertFalse(self.in_main(at, STALE_TARGET))

    def test_safety_result_is_not_in_the_report_when_stale(self):
        with self.watching() as w:
            at = self.computed(w)
            w.reset()
            at = self.change(at, "salary", 30000)
            rows = dict(w.rec.last_report()["settings"])
            self.assertEqual(rows.get("安全邊界"), "這次沒有計算", "S-40：過期的安全邊界不寫進報告")


# ---------- R-43：重新載入行情 ----------

class ReloadTests(RunButtonHarness, unittest.TestCase):
    def test_reload_runs_at_once_even_when_stale(self):
        with self.watching() as w:
            at = self.start()
            at = self.change(at, "salary", 30000)
            self.assertStale(at)
            w.reset()
            at = self.ok(self.reload_button(at).click().run())
            self.assertEqual(w.runs, 1, "重新載入行情本身就是明確的操作，立刻計算")
            self.assertFresh(at)
            self.assertEqual(w.rec.summaries[-1][0].salary_cap, 30000)

    def test_reload_is_not_disabled_by_input_errors(self):
        at = self.start(inc="5", udebt="120")
        self.assertFalse(self.reload_button(at).disabled)


if __name__ == "__main__":
    unittest.main()
