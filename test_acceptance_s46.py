"""衝刺 2.5 故事 46「信貸可貸額度」的驗收測試。

依據：SPEC-v40 第 12.4 節（驗收條件）與 12.5 節（產品決定，含舊連結規則）；DESIGN-v40 第 8 節（L-xx 文案、B-xx 規則）。
用 AppTest 離線跑整個 App（假行情）。額度的數字一律透過畫面上的文案與送進引擎的本金驗證，不依賴 RD 的函式名稱。
文案比對時忽略空白（中文與數字之間的空格不重要）。
"""
import json
import os
import re
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from test_acceptance_27_ui import BUTTON_KEY, call_arg, shown, solve_calls, spy_everywhere
from test_acceptance_helpers import (DETAILS_PAGE, HERE, AppHarness, Recorder, report_texts, strip_markup,
                                     visible_texts)

TYPE_LOAN = "一般信貸（年限短，通常無寬限期）"
TYPE_MORTGAGE = "理財型房貸（年限長，可設寬限期）"
GRAY = "#a3a29c"
INC_HELP = ("你每個月平均賺多少。算法：年收入（含年終獎金、分紅）÷ 12。例如年收入 72 萬，就填 6。"
            "填 0 代表不檢查信貸額度。")
NEWS = ("依新聞報導：2026-10-31 起，信貸的資金用途如果寫「投資理財」，銀行要先經你同意，才能查詢你在券商的借貸（例如融資）。"
        "你不同意，就辦不成。")
L11 = "填平均月收入可以檢查信貸額度。"
FOOT = "信貸額度是估計。各銀行條件常變動，以銀行核定為準。"
L08_ERR = "信貸額度：既有無擔保債務已用完法規上限，無法再借"


def wan(x):
    """DESIGN 8 的金額格式：千分位、最多一位小數、去掉尾端的 0。"""
    text = f"{x:,.1f}"
    return text[:-2] if text.endswith(".0") else text


def norm(text):
    return re.sub(r"\s+", "", str(text).replace("\\$", "$"))


def l01a(x, y):
    return f"⚠️你輸入{wan(x)}萬，但依規定（平均月收入的22倍，扣掉既有無擔保債務）最多只能借{wan(y)}萬。以下結果以{wan(y)}萬計算。"


def l01b(x, w):
    return f"⚠️你輸入{wan(x)}萬，但產品最高額度是{wan(w)}萬。以下結果以{wan(w)}萬計算。"


def l02(cap):
    return f"⚠️超過可借上限{wan(cap)}萬。計算時會改用{wan(cap)}萬。"


def l03(inc, y, z, w, cap, debt=0):
    text = (f"依平均月收入{wan(inc)}萬：法規上限{wan(y)}萬、一般可核貸約{wan(z)}萬（估計）、產品最高額度{wan(w)}萬。"
            f"你的可借上限是{wan(cap)}萬。")
    return text + (f"已扣掉既有無擔保債務{wan(debt)}萬。" if debt else "")


def l04(cap, z):
    return f"可借上限{wan(cap)}萬｜一般可核貸約{wan(z)}萬（估計）"


def l10(p, z):
    return f"你輸入的{wan(p)}萬，高過一般可核貸的估計{wan(z)}萬。銀行可能只核給較低的額度。"


def l07(inc):
    return f"年收入約{wan(inc * 12)}萬，未滿30萬。多數銀行的信貸申辦門檻是年收入30萬。"


def monthly_payment(principal, rate_pct, years):
    r, n = rate_pct / 100 / 12, years * 12
    return principal * r / (1 - (1 + r) ** -n)


class S46Harness(AppHarness):
    def run_app(self, **query):
        """跑一次，回傳 (at, rec)。每次先清快取，才一定會記錄到引擎呼叫。"""
        st.cache_data.clear()
        with Recorder() as rec:
            at = self.start(**query)
        return at, rec

    def principal(self, rec):
        self.assertTrue(rec.summaries, "沒有送進引擎")
        return rec.summaries[-1][0].principal

    def params(self, rec):
        self.assertTrue(rec.summaries, "沒有送進引擎")
        return rec.summaries[-1][0]

    def texts(self, at):
        return [norm(strip_markup(t)) for _, t in visible_texts(at)]

    def boxes(self, block, kind):
        return [norm(shown(e)) for e in getattr(block, kind)]

    def everything(self, at):
        out = []
        for kind in ("warning", "info", "error", "caption", "success", "markdown", "toast"):
            out += self.boxes(at, kind)
        return out

    def assertShown(self, at, sentence, where=None, kinds=("warning", "info", "error", "caption", "markdown")):
        block = {None: at, "side": at.sidebar, "main": at.main}[where]
        found = []
        for kind in kinds:
            found += self.boxes(block, kind)
        target = norm(sentence)
        self.assertTrue(any(target in f for f in found), f"畫面上沒有（{where or '全頁'}）：{sentence}\n現有：{found[:40]}")

    def assertNotShown(self, at, sentence, where=None):
        block = {None: at, "side": at.sidebar, "main": at.main}[where]
        found = []
        for kind in ("warning", "info", "error", "caption", "markdown", "success"):
            found += self.boxes(block, kind)
        target = norm(sentence)
        self.assertFalse(any(target in f for f in found), f"不該出現：{sentence}")

    def has(self, at, kind, key):
        return any(w.key == key for w in getattr(at, kind))

    def metrics(self, at):
        return [(m.label, m.value) for m in at.metric]

    def report_rows(self, rec):
        kwargs = rec.last_report()
        self.assertIsNotNone(kwargs, "沒有產生報告")
        return dict(kwargs["settings"])

    def report_all(self, rec):
        return norm("\n".join(report_texts(rec.last_report())))


# ---------- 預設值與切換貸款種類 ----------

class DefaultsTests(S46Harness, unittest.TestCase):
    def test_opening_defaults(self):
        at, rec = self.run_app()
        self.assertEqual(at.radio(key="type").value, TYPE_LOAN)
        self.assertEqual(at.number_input(key="loan").value, 100)
        self.assertEqual(at.number_input(key="inc").value, 5)
        self.assertEqual(at.number_input(key="mult").value, 20)
        self.assertEqual(at.number_input(key="udebt").value, 0)
        self.assertEqual(at.number_input(key="pmax").value, 500)
        self.assertEqual(self.principal(rec), 1_000_000)

    def test_field_ranges_and_help(self):
        at, _ = self.run_app()
        inc, udebt, mult, pmax = (at.number_input(key=k) for k in ("inc", "udebt", "mult", "pmax"))
        self.assertEqual((inc.min, inc.max, inc.step), (0, 1000, 0.5))
        self.assertEqual((udebt.min, udebt.max, udebt.step), (0, 10000, 0.5))
        self.assertEqual((mult.min, mult.max, mult.step), (10, 22, 1))
        self.assertEqual((pmax.min, pmax.max, pmax.step), (100, 2000, 50))
        self.assertEqual(norm(inc.help), norm(INC_HELP))
        self.assertEqual(at.radio(key="lmode").value, "自己輸入")
        self.assertEqual(at.radio(key="lmode").options, ["自己輸入", "用估計的可核貸金額"])
        self.assertEqual(at.number_input(key="loan").step, 10)

    def test_switch_to_mortgage_and_back(self):
        at, _ = self.run_app()
        at.number_input(key="loan").set_value(250)
        at = self.ok(at.run())
        at.radio(key="type").set_value(TYPE_MORTGAGE)
        at = self.ok(at.run())
        self.assertEqual(at.number_input(key="loan").value, 300)
        self.assertEqual(at.number_input(key="loan").step, 50)
        for key in ("inc", "udebt", "mult", "pmax"):
            self.assertFalse(self.has(at, "number_input", key), f"房貸不該有 {key}")
        self.assertFalse(self.has(at, "radio", "lmode"))
        at.radio(key="type").set_value(TYPE_LOAN)
        at = self.ok(at.run())
        self.assertEqual(at.number_input(key="loan").value, 100, "改過也會被換回 100")
        self.assertEqual(at.number_input(key="inc").value, 5, "收入欄位保留")

    def test_switch_keeps_income_fields(self):
        at, _ = self.run_app(inc="8", udebt="20", mult="15", pmax="300")
        at.radio(key="type").set_value(TYPE_MORTGAGE)
        at = self.ok(at.run())
        at.radio(key="type").set_value(TYPE_LOAN)
        at = self.ok(at.run())
        self.assertEqual([at.number_input(key=k).value for k in ("inc", "udebt", "mult", "pmax")], [8, 20, 15, 300])

    def test_toast_when_switching(self):
        at, _ = self.run_app()
        at.radio(key="type").set_value(TYPE_MORTGAGE)
        at = self.ok(at.run())
        toasts = [norm(t.value) for t in at.toast]
        self.assertTrue(any(t.startswith("已換成") and "本金300萬" in t and "年利率2.5%" in t and "20年" in t
                            and "寬限期3年" in t for t in toasts), toasts)
        at.radio(key="type").set_value(TYPE_LOAN)
        at = self.ok(at.run())
        toasts = [norm(t.value) for t in at.toast]
        self.assertTrue(any("本金100萬" in t and "年利率3.5%" in t and "7年" in t and "無寬限期" in t for t in toasts), toasts)

    def test_mortgage_default_principal_without_credit_texts(self):
        at, rec = self.run_app(type="0")
        self.assertEqual(self.principal(rec), 3_000_000)
        self.assertNotShown(at, "依平均月收入")
        self.assertNotShown(at, NEWS)
        self.assertNotShown(at, FOOT)
        rows = self.report_rows(rec)
        for name in ("信貸額度", "本金調整", "提醒"):
            self.assertNotIn(name, rows)


# ---------- 公式 ----------

class FormulaTests(S46Harness, unittest.TestCase):
    def check(self, inc, y, z, w, cap, debt=0, **query):
        query = {"inc": str(inc), **query}
        if debt:
            query["udebt"] = str(debt)
        at, rec = self.run_app(**query)
        self.assertShown(at, l03(inc, y, z, w, cap, debt), "main")
        self.assertShown(at, l04(cap, z), "side")
        return at, rec

    def test_income_5(self):
        self.check(5, 110, 100, 500, 110)

    def test_income_10_multiple_16(self):
        self.check(10, 220, 160, 500, 220, mult="16")

    def test_income_50_product_cap_binds(self):
        self.check(50, 1100, 500, 500, 500)

    def test_existing_debt_reduces_both(self):
        self.check(5, 60, 50, 500, 60, debt=50)

    def test_other_product_max(self):
        self.check(30, 660, 300, 300, 300, pmax="300")

    def test_half_step_income(self):
        self.check(5.5, 121, 110, 500, 121)

    def test_debt_above_limit_blocks_calculation(self):
        at, rec = self.run_app(inc="5", udebt="120")
        self.assertShown(at, "你的既有無擔保債務120萬，已經用完法規上限（平均月收入5萬×22＝110萬）。依規定，不能再借信貸。", "side")
        self.assertEqual(rec.summaries, [], "無法再借時不能送進引擎")
        self.assertTrue(any(L08_ERR in t for t in self.texts(at)), "input_errors 要列出原因")
        buttons = [b for b in at.button if b.key in ("safe_run",)]
        self.assertTrue(all(b.proto.disabled for b in buttons))

    def test_debt_equal_to_limit_also_blocks(self):
        at, rec = self.run_app(inc="5", udebt="110")
        self.assertEqual(rec.summaries, [])
        self.assertShown(at, "已經用完法規上限", "side")

    def test_lmode_zero_estimate_message(self):
        at, rec = self.run_app(inc="5", udebt="100", lmode="1")
        self.assertShown(at, "用估計的可核貸金額算出來是 0 萬，無法計算。請改成「自己輸入」，或調高核貸倍數。", "side")
        self.assertEqual(rec.summaries, [])
        self.assertTrue(any("信貸額度" in t for t in self.texts(at)))


# ---------- 平均月收入 0 ----------

class ZeroIncomeTests(S46Harness, unittest.TestCase):
    def test_no_check_and_same_as_v39(self):
        at, rec = self.run_app(inc="0", loan="500")
        self.assertEqual(self.principal(rec), 5_000_000, "不檢查額度，本金照填")
        self.assertShown(at, L11, "side")
        self.assertNotShown(at, "依平均月收入")
        self.assertNotShown(at, "法規上限")
        for key in ("udebt", "mult", "pmax"):
            self.assertFalse(self.has(at, "number_input", key), f"inc=0 時 {key} 隱藏")
        self.assertFalse(self.has(at, "radio", "lmode"))
        rows = self.report_rows(rec)
        self.assertEqual(rows.get("信貸額度"), "未檢查（沒有填平均月收入）")
        self.assertNotIn("本金調整", rows)
        self.assertNotIn(FOOT, self.report_all(rec))

    def test_hidden_fields_do_not_change_result(self):
        at1, rec1 = self.run_app(inc="0", loan="500")
        at2, rec2 = self.run_app(inc="0", loan="500", udebt="999", mult="10", pmax="100", lmode="1")
        self.assertEqual(self.params(rec1), self.params(rec2))
        self.assertEqual(self.metrics(at1), self.metrics(at2))

    def test_equal_to_unbounded_calculation(self):
        """同一個本金：inc=0 的結果，等於額度不限制它時（inc=5、本金在上限內）的結果。"""
        at1, rec1 = self.run_app(inc="0", loan="100")
        at2, rec2 = self.run_app(inc="5", loan="100")
        self.assertEqual(self.params(rec1), self.params(rec2))
        self.assertEqual(self.metrics(at1), self.metrics(at2))

    def test_zero_income_big_loan_is_not_capped(self):
        at, rec = self.run_app(inc="0", loan="3000")
        self.assertEqual(self.principal(rec), 30_000_000)
        self.assertNotShown(at, "最多只能借")


# ---------- 超過上限 ----------

class OverLimitTests(S46Harness, unittest.TestCase):
    def test_over_regulation_limit(self):
        at, rec = self.run_app(inc="5", loan="200")
        self.assertEqual(self.principal(rec), 1_100_000)
        self.assertShown(at, l01a(200, 110), "main")
        self.assertShown(at, l02(110), "side")
        rows = self.report_rows(rec)
        adj = norm(l01a(200, 110)).replace("⚠️", "")
        self.assertEqual(norm(rows.get("本金調整")), adj)
        self.assertIn("110萬元", norm(rows["貸款"]), "報告「貸款」那列寫採用的本金")
        self.assertIn(norm(l03(5, 110, 100, 500, 110)), norm(rows["信貸額度"]))
        self.assertIn("核貸倍數20（估計）。貸款金額：自己輸入。", norm(rows["信貸額度"]))
        self.assertIn(FOOT, self.report_all(rec))

    def test_over_product_max(self):
        at, rec = self.run_app(inc="50", loan="800")
        self.assertEqual(self.principal(rec), 5_000_000)
        self.assertShown(at, l01b(800, 500), "main")
        self.assertNotShown(at, l01a(800, 500), "main")
        self.assertEqual(norm(self.report_rows(rec)["本金調整"]), norm(l01b(800, 500)).replace("⚠️", ""))

    def test_debt_lowers_cap(self):
        at, rec = self.run_app(inc="5", udebt="50", loan="100")
        self.assertEqual(self.principal(rec), 600_000)
        self.assertShown(at, l01a(100, 60), "main")

    def test_at_or_below_cap_uses_input(self):
        at, rec = self.run_app(inc="5", loan="110")
        self.assertEqual(self.principal(rec), 1_100_000)
        self.assertNotShown(at, "最多只能借", "main")
        self.assertNotShown(at, "超過可借上限", "side")
        self.assertNotIn("本金調整", self.report_rows(rec))

    def test_between_estimate_and_cap_shows_info(self):
        at, rec = self.run_app(inc="5", loan="105")
        self.assertEqual(self.principal(rec), 1_050_000)
        self.assertShown(at, l10(105, 100), "main", kinds=("info",))
        self.assertIn(norm(l10(105, 100)), norm(self.report_rows(rec)["提醒"]))
        at, _ = self.run_app(inc="5", loan="100")
        self.assertNotShown(at, "高過一般可核貸", "main")

    def test_main_order(self):
        at, _ = self.run_app(inc="5", loan="200", years="2")
        flow = []
        for kind in ("warning", "caption", "info"):
            flow += [(e, kind) for e in getattr(at.main, kind)]
        texts = [norm(shown(e)) for e, _ in flow]
        idx = lambda s: next(i for i, t in enumerate(texts) if norm(s) in t)  # noqa: E731
        self.assertTrue(idx("最多只能借") < idx("依平均月收入"))


# ---------- 用估計金額 ----------

class EstimateModeTests(S46Harness, unittest.TestCase):
    def test_equals_setting_that_principal(self):
        at1, rec1 = self.run_app(inc="10", mult="16", lmode="1")
        at2, rec2 = self.run_app(inc="10", mult="16", loan="160")
        self.assertEqual(self.principal(rec1), 1_600_000)
        self.assertEqual(self.params(rec1), self.params(rec2))
        self.assertEqual(self.metrics(at1), self.metrics(at2))
        self.assertIn("貸款金額：用估計的可核貸金額。", norm(self.report_rows(rec1)["信貸額度"]))

    def test_principal_box_disabled_and_not_in_url(self):
        at, _ = self.run_app(inc="10", mult="16", lmode="1")
        boxes = [n for n in at.sidebar.number_input if n.label == "貸款本金 (萬)"]
        self.assertEqual(len(boxes), 1)
        self.assertTrue(boxes[0].proto.disabled)
        self.assertEqual(boxes[0].value, 160)
        self.assertNotIn("loan", at.query_params)
        self.assertEqual(at.query_params["lmode"], ["1"])

    def test_own_value_comes_back(self):
        at, rec = self.run_app(inc="10", mult="16", loan="50")
        at.radio(key="lmode").set_value("用估計的可核貸金額")
        at = self.ok(at.run())
        at.radio(key="lmode").set_value("自己輸入")
        at = self.ok(at.run())
        self.assertEqual(at.number_input(key="loan").value, 50)

    def test_estimate_capped_by_product_max(self):
        at, rec = self.run_app(inc="50", lmode="1")
        self.assertEqual(self.principal(rec), 5_000_000)

    def test_estimate_ignored_for_mortgage_and_zero_income(self):
        _, rec = self.run_app(type="0", lmode="1")
        self.assertEqual(self.principal(rec), 3_000_000)
        _, rec = self.run_app(inc="0", lmode="1")
        self.assertEqual(self.principal(rec), 1_000_000)


# ---------- 理財型房貸 ----------

class MortgageTests(S46Harness, unittest.TestCase):
    def test_fields_hidden_and_no_effect(self):
        at1, rec1 = self.run_app(type="0", loan="500")
        at2, rec2 = self.run_app(type="0", loan="500", inc="1", udebt="900", mult="10", pmax="100", lmode="1")
        for key in ("inc", "udebt", "mult", "pmax"):
            self.assertFalse(self.has(at2, "number_input", key))
        self.assertFalse(self.has(at2, "radio", "lmode"))
        self.assertEqual(self.principal(rec2), 5_000_000)
        self.assertEqual(self.params(rec1), self.params(rec2))
        self.assertEqual(self.metrics(at1), self.metrics(at2))
        for at in (at1, at2):
            self.assertNotShown(at, "年收入約")
            self.assertNotShown(at, "月付比")
            self.assertNotShown(at, NEWS)

    def test_no_safety_cap_or_gray_cells(self):
        at, rec = self.run_app(type="0", loan="500", inc="1")
        with spy_everywhere("solve_for") as solve:
            with spy_everywhere("sensitivity_grid"):
                at = self.ok(at.button(key=BUTTON_KEY).click().run())
        principal_call = [c for c in solve_calls(solve) if c[0] == "principal"][0]
        self.assertGreater(float(principal_call[3]), 11_000_000, "房貸不套用可借上限")
        for node in at.get("plotly_chart"):
            spec = json.loads(node.proto.spec)
            self.assertNotIn("超限", json.dumps(spec, ensure_ascii=False))


# ---------- 提醒 ----------

class WarningTests(S46Harness, unittest.TestCase):
    def ratio_text(self, years, inc=5, loan=100, rate=3.5):
        pmt = monthly_payment(loan * 10000, rate, years)
        return pmt, pmt / (inc * 10000)

    def test_high_ratio(self):
        pmt, ratio = self.ratio_text(5)
        self.assertTrue(1 / 3 < ratio <= 0.7, ratio)
        at, rec = self.run_app(inc="5", loan="100", years="5")
        main = self.boxes(at.main, "warning")
        hit = [t for t in main if "月付比偏高" in t]
        self.assertEqual(len(hit), 1, main)
        self.assertIn(f"寬限期後每月應繳${pmt:,.0f}，是平均月收入的{ratio * 100:.1f}%。月付比偏高。", hit[0])
        self.assertIn("部分銀行的產品條件寫，每月還款不能超過月收入的三分之一。這裡只算這筆新貸款，沒有算你其他貸款的月付。", hit[0])
        self.assertFalse([t for t in main if "多數銀行可能婉拒" in t])
        self.assertIn("月付比偏高", norm(self.report_rows(rec)["提醒"]))

    def test_very_high_ratio_replaces_high(self):
        pmt, ratio = self.ratio_text(2)
        self.assertGreater(ratio, 0.7)
        at, rec = self.run_app(inc="5", loan="100", years="2")
        main = self.boxes(at.main, "warning")
        hit = [t for t in main if "多數銀行可能婉拒" in t]
        self.assertEqual(len(hit), 1, main)
        self.assertIn(f"寬限期後每月應繳${pmt:,.0f}，是平均月收入的{ratio * 100:.1f}%。多數銀行可能婉拒。", hit[0])
        self.assertIn("有銀行規定每月還款不能超過月收入的70%。這裡只算這筆新貸款，沒有算你其他貸款的月付。", hit[0])
        self.assertFalse([t for t in main if "月付比偏高" in t])

    def test_normal_ratio_no_warning(self):
        at, _ = self.run_app(inc="5", loan="100", years="7")
        self.assertNotShown(at, "月付比偏高")
        self.assertNotShown(at, "多數銀行可能婉拒")

    def test_ratio_uses_adopted_principal(self):
        """本金被上限壓低後，月付比用採用的本金算。"""
        pmt, ratio = self.ratio_text(5, loan=110)
        at, _ = self.run_app(inc="5", loan="300", years="5")
        self.assertShown(at, f"每月應繳${pmt:,.0f}，是平均月收入的{ratio * 100:.1f}%", "main")

    def test_no_ratio_warning_without_income_or_for_mortgage(self):
        for query in ({"inc": "0", "loan": "100", "years": "2"}, {"type": "0", "loan": "1000", "years": "2"}):
            at, _ = self.run_app(**query)
            self.assertNotShown(at, "月付比")

    def test_income_threshold(self):
        at, rec = self.run_app(inc="2")
        self.assertShown(at, l07(2), "side", kinds=("warning",))
        self.assertShown(at, l07(2), "main", kinds=("warning",))
        self.assertIn(norm(l07(2)), norm(self.report_rows(rec)["提醒"]))
        for inc in ("2.5", "5"):
            at, _ = self.run_app(inc=inc)
            self.assertNotShown(at, "未滿30萬")
        at, _ = self.run_app(inc="0")
        self.assertNotShown(at, "未滿30萬")

    def test_news_notice(self):
        at, _ = self.run_app()
        self.assertShown(at, NEWS, "side", kinds=("info",))
        at, _ = self.run_app(inc="0")
        self.assertShown(at, NEWS, "side", kinds=("info",))
        self.assertIn("依新聞報導", NEWS)


# ---------- 網址 ----------

class UrlTests(S46Harness, unittest.TestCase):
    def test_defaults_not_in_url(self):
        at, _ = self.run_app()
        for key in ("inc", "udebt", "mult", "pmax", "lmode", "loan"):
            self.assertNotIn(key, at.query_params)

    def test_explicit_defaults_are_removed_except_inc_with_loan(self):
        at, _ = self.run_app(udebt="0", mult="20", pmax="500", lmode="0")
        for key in ("udebt", "mult", "pmax", "lmode"):
            self.assertNotIn(key, at.query_params)

    def test_non_defaults_are_written(self):
        at, _ = self.run_app(inc="8", udebt="20", mult="15", pmax="300", lmode="1")
        self.assertEqual([at.query_params[k] for k in ("inc", "udebt", "mult", "pmax", "lmode")],
                         [["8"], ["20"], ["15"], ["300"], ["1"]])

    def test_invalid_values_fall_back(self):
        at, _ = self.run_app(inc="abc", udebt="x", mult="y", pmax="z", lmode="7")
        self.assertEqual([at.number_input(key=k).value for k in ("inc", "udebt", "mult", "pmax")], [5, 0, 20, 500])
        self.assertEqual(at.radio(key="lmode").value, "自己輸入")
        at, _ = self.run_app(lmode="abc")
        self.assertEqual(at.radio(key="lmode").value, "自己輸入")

    def test_out_of_range_is_clamped(self):
        at, _ = self.run_app(mult="30")
        self.assertEqual(at.number_input(key="mult").value, 22)
        at, _ = self.run_app(inc="-2")
        self.assertEqual(at.number_input(key="inc").value, 0)
        at, _ = self.run_app(mult="3", pmax="9999")
        self.assertEqual((at.number_input(key="mult").value, at.number_input(key="pmax").value), (10, 2000))

    def test_non_default_expander_open(self):
        at, _ = self.run_app(mult="15")
        exp = [e for e in at.sidebar.expander if "額度檢查的細項" in e.label]
        self.assertEqual(len(exp), 1)
        self.assertTrue(exp[0].proto.expanded)
        at, _ = self.run_app()
        exp = [e for e in at.sidebar.expander if "額度檢查的細項" in e.label]
        self.assertFalse(exp[0].proto.expanded)

    def test_old_link_loan_without_inc_is_v39(self):
        at, rec = self.run_app(loan="500")
        self.assertEqual(at.number_input(key="inc").value, 0)
        self.assertEqual(self.principal(rec), 5_000_000)
        self.assertShown(at, L11, "side")
        self.assertNotShown(at, "最多只能借")
        self.assertEqual(at.query_params["inc"], ["0"])
        at2, rec2 = self.run_app(loan="500", inc="0")
        self.assertEqual(self.params(rec), self.params(rec2))
        self.assertEqual(self.metrics(at), self.metrics(at2))

    def test_old_link_explicit_type_one(self):
        at, rec = self.run_app(loan="800", type="1")
        self.assertEqual(self.principal(rec), 8_000_000)
        self.assertEqual(at.number_input(key="inc").value, 0)

    def test_old_link_mortgage_keeps_loan(self):
        at, rec = self.run_app(type="0", loan="500")
        self.assertEqual(self.principal(rec), 5_000_000)

    def test_link_without_loan_uses_new_defaults(self):
        _, rec = self.run_app()
        self.assertEqual(self.principal(rec), 1_000_000)
        _, rec = self.run_app(type="0")
        self.assertEqual(self.principal(rec), 3_000_000)

    def test_new_link_with_loan_writes_inc(self):
        at, rec = self.run_app(loan="200", inc="5")
        self.assertEqual(at.query_params["inc"], ["5"], "有 loan 時一律寫出 inc，即使是預設值")
        self.assertEqual(self.principal(rec), 1_100_000, "不被當成舊連結")

    def test_loan_set_in_ui_writes_inc(self):
        at, _ = self.run_app()
        at.number_input(key="loan").set_value(200)
        at = self.ok(at.run())
        self.assertEqual(at.query_params["loan"], ["200"])
        self.assertEqual(at.query_params["inc"], ["5"])

    def test_loan_back_to_default_drops_inc(self):
        at, _ = self.run_app()
        at.number_input(key="loan").set_value(200)
        at = self.ok(at.run())
        at.number_input(key="loan").set_value(100)
        at = self.ok(at.run())
        self.assertNotIn("loan", at.query_params)
        self.assertNotIn("inc", at.query_params)

    def test_old_link_check_runs_only_once(self):
        at, _ = self.run_app(loan="500")
        at.number_input(key="inc").set_value(5)
        at = self.ok(at.run())
        self.assertEqual(at.number_input(key="inc").value, 5, "使用者改回 5 之後不能又被換成 0")
        at = self.ok(at.run())
        self.assertEqual(at.number_input(key="inc").value, 5)

    def test_switch_type_removes_loan_keeps_inc_zero(self):
        at, _ = self.run_app(loan="500")
        at.radio(key="type").set_value(TYPE_MORTGAGE)
        at = self.ok(at.run())
        self.assertNotIn("loan", at.query_params)
        self.assertEqual(at.query_params["inc"], ["0"])

    def test_lmode_one_link_has_no_loan(self):
        at, _ = self.run_app(inc="10", lmode="1")
        self.assertNotIn("loan", at.query_params)


# ---------- 熱圖與安全邊界 ----------

class HeatmapTests(S46Harness, unittest.TestCase):
    def press(self, at):
        with spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid:
            at = self.ok(at.button(key=BUTTON_KEY).click().run())
        return at, solve, grid

    def heatmap(self, at):
        for node in at.get("plotly_chart"):
            spec = json.loads(node.proto.spec)
            if any(t.get("type") == "heatmap" for t in spec["data"]):
                return spec
        self.fail("找不到熱圖")

    def map_table(self, at):
        for exp in at.expander:
            if exp.label == "用表格看這張地圖":
                return exp.table[0].value
        self.fail("找不到「用表格看這張地圖」")

    def test_rows_above_cap_are_gray(self):
        at, rec = self.run_app(inc="5", loan="100")           # 可借上限 110；列 = 50、75、100、125、150、200
        with rec:
            at, solve, grid = self.press(at)
        for call in grid.call_args_list:
            self.assertTrue(all(float(p) <= 1_100_000 for p in call_arg(call, 2, "principals")), "超限的列不送去計算")
        spec = self.heatmap(at)
        gray = [t for t in spec["data"] if t.get("type") == "heatmap" and t.get("showscale") is False]
        self.assertEqual(len(gray), 1)
        layer = gray[0]
        self.assertIn(GRAY, json.dumps(layer.get("colorscale")).lower())
        self.assertIn("超限", (layer.get("texttemplate") or "") + json.dumps(layer.get("text"), ensure_ascii=False))
        filled = [i for i, row in enumerate(layer["z"]) if any(v is not None for v in row)]
        self.assertEqual(len(filled), 3, "125、150、200 三列是灰的")
        hover = (layer.get("hovertemplate") or "") + json.dumps(layer.get("hovertext"), ensure_ascii=False)
        self.assertTrue(re.search(r"貸款本金 .{0,12} 超過可借上限 110 萬，無法計算", hover), hover)
        table = self.map_table(at)
        for row in ("125 萬", "150 萬", "200 萬"):
            self.assertEqual([str(v) for v in table.loc[row]], ["超限"] * 6, row)
        for row in ("50 萬", "75 萬"):
            self.assertTrue(all("%" in str(v) for v in table.loc[row]), row)
        self.assertShown(at, "灰底「超限」的格子：貸款本金超過可借上限110萬，銀行不會核貸，所以不計算。", None, ("caption",))
        tables = (rec.last_report() or {}).get("tables", [])
        self.assertTrue(any("超限" in str(v) for _, frame, _ in tables for v in frame.to_numpy().ravel()), "報告的表也寫「超限」")

    def test_safety_search_upper_bound_is_cap(self):
        at, _ = self.run_app(inc="5", loan="100")
        _, solve, _ = self.press(at)
        call = [c for c in solve_calls(solve) if c[0] == "principal"][0]
        self.assertLessEqual(float(call[3]), 1_100_000)
        self.assertGreaterEqual(float(call[3]), 1_000_000)

    def test_no_gray_when_nothing_exceeds(self):
        at, _ = self.run_app(inc="50", loan="100")             # 可借上限 500；最大列 200
        at, _, _ = self.press(at)
        self.assertNotIn("超限", json.dumps(self.heatmap(at), ensure_ascii=False))
        self.assertNotShown(at, "灰底「超限」的格子")

    def test_zero_income_no_gray(self):
        at, _ = self.run_app(inc="0", loan="100")
        at, _, _ = self.press(at)
        self.assertNotIn("超限", json.dumps(self.heatmap(at), ensure_ascii=False))

    def test_current_cell_never_over_limit(self):
        at, _ = self.run_app(inc="5", loan="200")              # 採用 110
        at, _, _ = self.press(at)
        table = self.map_table(at)
        self.assertEqual(sum("◆" in str(v) for col in table.columns for v in table[col]), 1)


# ---------- 額度模組（credit_limit.py）的直接測試 ----------

class CreditModuleTests(unittest.TestCase):
    def setUp(self):
        import credit_limit as cl
        self.cl = cl

    def limits(self, *args, **kwargs):
        c = self.cl.assess(*args, **kwargs)
        return c.regulatory, c.approvable, c.cap

    def test_five_cases(self):
        self.assertEqual(self.limits(5), (110, 100, 110))
        self.assertEqual(self.limits(10, multiple=16), (220, 160, 220))
        self.assertEqual(self.limits(50), (1100, 500, 500))
        self.assertEqual(self.limits(5, debt=50), (60, 50, 60))
        self.assertEqual(self.limits(5, debt=120), (0, 0, 0))

    def test_never_negative_and_product_max(self):
        self.assertEqual(self.limits(1, debt=999), (0, 0, 0))
        self.assertEqual(self.limits(30, product_max=300), (660, 300, 300))

    def test_no_income_means_no_check(self):
        self.assertIsNone(self.cl.assess(0))

    def test_adopted_principal(self):
        c = self.cl.assess(5)
        self.assertEqual(self.cl.adopted_principal(c, 200), 110)
        self.assertEqual(self.cl.adopted_principal(c, 50), 50)
        self.assertEqual(self.cl.adopted_principal(c, 50, estimated=True), 100)
        self.assertEqual(self.cl.adopted_principal(None, 5000), 5000)

    def test_legacy_link(self):
        f = self.cl.is_legacy_link
        self.assertTrue(f({"loan": "500"}))
        self.assertTrue(f({"loan": "500", "type": "1"}))
        self.assertFalse(f({"loan": "500", "inc": "5"}))
        self.assertFalse(f({"loan": "500", "type": "0"}))
        self.assertFalse(f({}))
        self.assertFalse(f({"type": "1"}))

    def test_number_format(self):
        self.assertEqual([self.cl.wan_text(x) for x in (110, 5.5, 1100, 0, 60.0)], ["110", "5.5", "1,100", "0", "60"])



# V39 程式（commit 14ad2a1）在同一份假行情下算出來的結果；有寫 loan 的舊連結必須完全相同（SPEC 12.4、12.5-5）。
V39_GOLDEN = [
    ({'loan': '100'}, ['$13,439', '$13,439', '$0', '0.0%', '0.0%', '91.6%', '$2,027,339', '$1,795,559', '0.0%', '97.4%', '$2,869,545', '$2,015,511']),
    ({'loan': '1500'}, ['$201,597', '$201,597', '$0', '0.0%', '0.0%', '91.6%', '$7,538,428', '$3,332,274', '0.5%', '97.2%', '$16,725,981', '$3,741,921']),
    ({'loan': '300', 'years': '3', 'rate': '5'}, ['$89,912', '$89,912', '$0', '0.0%', '0.0%', '72.0%', '$1,407,130', '$1,083,646', '0.1%', '88.2%', '$1,790,882', '$1,141,069']),
    ({'loan': '800', 'type': '0'}, ['$16,666', '$48,177', '$0', '0.0%', '100.0%', '$48,612,668', '$18,891,021', '0.0%', '100.0%', '$142,217,416', '$34,560,538']),
    ({'loan': '200', 'buf': '2', 'salary': '10000', 'reinv': '0'}, ['$26,879', '$26,879', '$53,759', '0.0%', '0.0%', '96.3%', '$1,934,077', '$1,357,394', '0.0%', '97.5%', '$3,143,488', '$1,480,512']),
    ({'loan': '450', 'scen': '2', 'jl': '1', 'shock': '1'}, ['$60,479', '$60,479', '$0', '0.0%', '0.0%', '86.9%', '$3,842,295', '$2,322,247', '0.0%', '96.8%', '$7,072,157', '$3,375,912']),
    ({'loan': '50', 'lfee': '100000'}, ['$6,719', '$6,719', '$0', '0.0%', '0.0%', '41.1%', '$813,006', '$898,239', '0.0%', '80.6%', '$1,153,638', '$1,009,791']),
]


class V39RegressionTests(S46Harness, unittest.TestCase):
    def test_old_links_give_v39_numbers(self):
        for query, metrics in V39_GOLDEN:
            with self.subTest(query):
                at, _ = self.run_app(**query)
                self.assertEqual([m.value for m in at.metric], metrics)


# ---------- 說明頁 ----------

class DetailsPageTests(unittest.TestCase):
    def test_new_section(self):
        with patch("streamlit.page_link"):
            at = AppTest.from_file(os.path.join(HERE, DETAILS_PAGE), default_timeout=60).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        page = norm("\n".join(strip_markup(t) for _, t in visible_texts(at)))
        for needle in ("信貸額度", "各銀行條件常變動，以銀行核定為準", "平均月收入的22倍", "既有無擔保債務", "2026-11-17"):
            self.assertIn(norm(needle), page, needle)


if __name__ == "__main__":
    unittest.main()
