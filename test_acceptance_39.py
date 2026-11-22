"""第 39 項（英文介面）的驗收測試。

依據：SPEC-v40 第 7 節與決議 D8、D10、D16、D18；DESIGN-v40 第 4 節（E-01～E-23、術語表）；TEST-PLAN-v40 TC-39-01～08。
用 AppTest 離線跑整個 App（假行情）。核心是「中日韓字元掃描」：英文模式下收集畫面上所有看得到的文字
（markdown、caption、help、metric、按鈕、表格欄名與內容、圖表的標題／軸／刻度／hover／圖例、toast、錯誤訊息、
頁面標題與導覽），加上可下載的報告 HTML、CSV 欄名與下載檔名，不可有任何中日韓字元。

掃描的例外（SPEC 7、D10）：
  * ETF 的中文名稱（來自資料；這個離線測試的資料沒有名稱，`leaks(names=...)` 預留了扣除名單）
  * 使用者自己輸入的文字
  * 語言切換鈕上的「中文」兩個字
掃描範圍包含全形標點（，。（）｜…），因為它們一樣是中日韓字元集裡的字；英文畫面上出現全形標點代表有漏翻。

介面上的語言碼假設（DESIGN E-02、E-03、E-05）：語言切換是側欄最上方的 st.segmented_control，值是 "zh"／"en"，
顯示「中文」「English」；網址參數 lang=en；說明頁從同一個網址參數讀語言。
"""
import json
import os
import re
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import build_standalone
import market_data
from test_acceptance_27_ui import BUTTON_KEY as SAFE_KEY
from test_acceptance_27_ui import NO_SALARY_ORDER, fake_solver, shown, spy_everywhere
from test_acceptance_38 import SCAN_SETUPS, widget_snapshot
from test_acceptance_helpers import (APP, DETAILS_PAGE, HERE, AppHarness, Recorder, report_texts,
                                     visible_texts)
from test_app import fake_history
from version import APP_VERSION

# 載入模組時還沒有被任何測試換掉，是真正的 load_history（行情抓不到的情境要用真的來產生訊息）。
REAL_LOAD_HISTORY = market_data.load_history

CJK = re.compile("[　-ヿ㐀-鿿가-힯豈-﫿＀-￯]")
RUN_KEY = "run_sidebar"
EN_TITLE = f"Borrow-to-Invest ETF Stress Test ({APP_VERSION})"           # 術語表 1
ZH_TITLE = f"借錢投資 ETF 壓力測試 ({APP_VERSION})"
UNMARKED_DOLLAR = re.compile(r"(?<!NT)\$(?=[\d{%,])")                      # E-14：金額一律 NT$
WORDS = re.compile(r"[A-Za-z]{3,}")
STALE_WORDS = ("尚未更新", "out of date")

MANY = SCAN_SETUPS["很多情境"]

# 名稱 -> (網址參數, 要改的文字欄位 key, 填入的值)。網址上的非法值會被丟掉，所以用欄位輸入才碰得到錯誤訊息。
INPUT_ERRORS = {
    "代號格式錯誤": ({}, "a", "../etc"),
    "第二標的格式錯誤": ({}, "b", "../etc"),
    "自訂報酬率不是數字": ({"scen": "3"}, "path", "5, 1.2.3"),
    "自訂報酬率沒有任何數字": ({"scen": "3"}, "path", ", ,"),
    "自訂報酬率小於 -100%": ({"scen": "3"}, "path", "5, -150"),
    "浮動利率不是數字": ({"float": "1"}, "rpath", "0.25, 1.2.3"),
    "浮動利率超出範圍": ({"float": "1"}, "rpath", "20"),
}


# ---------- 收集文字 ----------

def json_strings(spec):
    """圖表 JSON 裡所有字串（比 figure_texts 更嚴：tickprefix、ticksuffix、customdata、hoverlabel…都算）。"""
    if isinstance(spec, str):
        spec = json.loads(spec)
    out = []

    def walk(value):
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    walk(spec)
    return out


def leaves(node):
    children = getattr(node, "children", None)
    if children:
        for child in children.values():
            yield from leaves(child)
    else:
        yield node


WIDGET_TYPES = {"button_group", "radio", "selectbox", "toggle", "checkbox", "button", "number_input", "slider",
                "text_input", "download_button"}


def leaks(texts, names=()):
    """[(元素類型, 文字片段)]：掃到中日韓字元的文字（已扣掉例外）。"""
    found = []
    for kind, text in texts:
        text = str(text)
        for name in names:
            text = text.replace(name, " ")
        if kind in ("button_group", "segmented_control") and text.strip() == "中文":
            continue                                                      # D10
        match = CJK.search(text)
        if match:
            start = max(0, match.start() - 30)
            found.append(f"{kind}: …{text[start:match.start() + 40].strip()}…".replace("\n", " "))
    return found


def clean(text):
    return re.sub(r"\s+", " ", str(text).replace("\\$", "$")).strip()


class English(AppHarness):
    """離線跑 App 的共用工具；每個 run 都記錄頁面標題、導覽、報告、下載與引擎呼叫。"""

    @contextmanager
    def observing(self):
        with Recorder() as rec, patch("streamlit.set_page_config", wraps=st.set_page_config) as cfg, \
                patch("streamlit.navigation", wraps=st.navigation) as nav:
            yield rec, cfg, nav

    # ----- 語言切換鈕 -----

    def lang_control(self, at):
        found = [w for w in at.sidebar.get("button_group") if any("English" in str(o) for o in w.options)]
        self.assertEqual(len(found), 1, "側欄要有一個語言切換（segmented_control，選項「中文」「English」）")
        return found[0]

    def switch(self, at, code):
        control = self.lang_control(at)
        control.set_value(code)
        return self.ok(at.run())

    def qp(self, at, key, default=None):
        if key not in at.query_params:
            return default
        value = at.query_params[key]
        return value[0] if isinstance(value, list) else value

    def query_without_lang(self, at):
        return {k: self.qp(at, k) for k in at.query_params if k != "lang"}

    def title(self, at):
        return at.title[0].value

    # ----- 掃描 -----

    def gather(self, at, rec=None, cfg=None, nav=None):
        """畫面＋報告＋下載＋頁面標題與導覽上所有看得到的文字：[(類型, 文字)]。"""
        texts = list(visible_texts(at))
        for node in at.get("plotly_chart"):
            texts += [("chart", s) for s in json_strings(node.proto.spec)]
        texts += [("toast", e.value) for e in at.toast]
        if cfg is not None and cfg.call_args_list:
            call = cfg.call_args_list[-1]
            texts.append(("page_title", call.kwargs.get("page_title") or (call.args[0] if call.args else "")))
        if nav is not None and nav.call_args_list:
            call = nav.call_args_list[-1]
            pages = call.args[0] if call.args else call.kwargs["pages"]
            texts += [("導覽", p.title) for p in pages]
        if rec is not None:
            if rec.last_report():
                texts += [("報告", t) for t in report_texts(rec.last_report())]
                texts.append(("報告 HTML", rec.report_html()))
            for label, name, _ in rec.downloads:
                texts += [("下載按鈕", label), ("下載檔名", name or "")]
            for _, _, frame in rec.csv_frames():
                texts += [("CSV 欄名", str(c)) for c in frame.columns]
        return texts

    def assertEnglish(self, at, rec=None, cfg=None, nav=None, where="", minimum=100, names=()):
        texts = self.gather(at, rec, cfg, nav)
        self.assertGreater(len(texts), minimum, f"測試前提：{where}應收集到足夠的文字")
        found = leaks(texts, names)
        self.assertEqual(found, [], f"{where}英文模式出現 {len(found)} 處中日韓字元（只列前 15 處）：\n"
                         + "\n".join(found[:15]))
        return texts

    def page(self, texts):
        return clean("\n".join(t for _, t in texts))

    def prose(self, texts):
        """畫面文字（不含圖表 JSON 裡的版面範本與報告 HTML 原始碼）。"""
        return self.page([x for x in texts if x[0] not in ("chart", "報告 HTML")])

    def metric_pairs(self, at):
        return [(m.label, m.value) for m in at.metric]

    # ----- 行情抓不到：真的 load_history＋失敗的 Yahoo＋沒有任何存檔 -----

    def failing_loader(self, with_yf):
        class FakeYahoo:
            class Ticker:
                def __init__(self, ticker):
                    pass

                def history(self, **kwargs):
                    raise RuntimeError("down")

        def loader(ticker):
            return REAL_LOAD_HISTORY(ticker) if ticker.startswith("ZZZZ") else fake_history(ticker)

        stack = ExitStack()
        empty = stack.enter_context(tempfile.TemporaryDirectory())
        for patcher in (patch.object(market_data, "SNAPSHOT_DIR", empty), patch.object(market_data, "SEED_DIR", empty),
                        patch("market_data.fetch_mirror", return_value=None), patch("market_data.time.sleep"),
                        patch.object(market_data, "yf", FakeYahoo if with_yf else None),
                        patch("market_data.load_history", side_effect=loader)):
            stack.enter_context(patcher)
        return stack

    def bad_input(self, query, key, value, lang="en"):
        at = self.start(**({"lang": lang} if lang else {}), **query)
        at = self.ok(at.text_input(key=key).set_value(value).run())
        button = at.button(key=RUN_KEY)
        if not button.disabled:          # 代號錯誤要按「開始計算」才會去抓行情；路徑格式錯誤則立即顯示（R-51）
            at = self.ok(button.click().run())
        self.assertTrue(len(at.error) >= 1, f"測試前提：{key}={value!r} 要顯示錯誤")
        return at

    def start_with_real_loader(self, with_yf, **query):
        with self.failing_loader(with_yf):
            return self.start(**query)

    def details_page(self, lang):
        """從 app.py 進入說明頁（語言由 app.py 依網址參數決定，E-05），並攔截 page_link 的標籤。"""
        links = []
        with patch("streamlit.page_link", side_effect=lambda *a, **k: links.append(k.get("label", ""))):
            at = AppTest.from_file(APP, default_timeout=180)
            if lang:
                at.query_params["lang"] = lang
            at = at.run().switch_page(DETAILS_PAGE).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at, links


# =====================================================================
# TC-39-01：網址參數 lang、語言切換鈕
# =====================================================================

class LanguageParameterTests(English, unittest.TestCase):
    def test_default_is_chinese_and_the_default_is_not_written_to_the_url(self):
        at = self.start()
        self.assertEqual(self.title(at), ZH_TITLE)
        self.assertNotIn("lang", at.query_params, "E-03：預設（中文）不寫進網址")
        self.assertEqual(self.lang_control(at).value, "zh")

    def test_lang_en_is_english(self):
        at = self.start(lang="en")
        self.assertEqual(self.title(at), EN_TITLE)                          # 術語表 1
        self.assertEqual(self.lang_control(at).value, "en")
        self.assertEqual(self.qp(at, "lang"), "en", "E-03：lang=en 留在網址上")
        self.assertEqual(at.button(key=RUN_KEY).label, "Run")                # 術語表 6

    def test_explicit_zh_is_chinese(self):
        at = self.start(lang="zh")
        self.assertEqual(self.title(at), ZH_TITLE)

    def test_invalid_values_fall_back_to_chinese(self):
        for bad in ("fr", "", "zh-TW", "english", "1", "<script>"):
            with self.subTest(lang=bad):
                at = self.start(lang=bad)
                self.assertEqual(self.title(at), ZH_TITLE)
                self.assertEqual(self.lang_control(at).value, "zh")

    def test_invalid_value_is_not_kept_in_the_url(self):
        # E-03「中文是預設，不寫進網址」＋TC-39-01「無效值退回中文」：退回之後網址不該還帶著 lang=fr。
        at = self.start(lang="fr")
        self.assertNotIn(self.qp(at, "lang"), ("fr",), "無效的 lang 不該留在網址上")

    def test_language_control_is_at_the_very_top_of_the_sidebar(self):
        for query in ({}, {"lang": "en"}):
            with self.subTest(**query):
                at = self.start(**query)
                widgets = [n for n in leaves(at.sidebar) if getattr(n, "type", "") in WIDGET_TYPES]
                self.assertTrue(widgets)
                first = widgets[0]
                self.assertEqual(first.type, "button_group", "E-01：側欄第一個元件是語言切換")
                self.assertIs(first, self.lang_control(at))
                self.assertLess(widgets.index(first), [w.key for w in widgets].index(RUN_KEY),
                                "語言切換在「開始計算」之上")

    def test_language_control_options_and_label(self):
        at = self.start()
        control = self.lang_control(at)
        self.assertEqual(list(control.options), ["中文", "English"])        # E-02、E-06
        self.assertEqual(control.label, "語言")                              # 術語表 5
        at = self.start(lang="en")
        control = self.lang_control(at)
        self.assertEqual(list(control.options), ["中文", "English"], "兩種語言的選項文字都一樣（語言用自己的名字）")
        self.assertEqual(control.label, "Language")

    def test_page_title_and_navigation_follow_the_language(self):
        with self.observing() as (_, cfg, nav):
            self.start(lang="en")
        title = cfg.call_args.kwargs.get("page_title") or cfg.call_args.args[0]
        self.assertEqual(title, f"Borrow-to-Invest ETF Stress Test {APP_VERSION}")
        pages = nav.call_args.args[0] if nav.call_args.args else nav.call_args.kwargs["pages"]
        self.assertEqual([p.title for p in pages], ["Stress test", "How it works"])   # 術語表 2、3（E-05）
        with self.observing() as (_, cfg, nav):
            self.start()
        pages = nav.call_args.args[0] if nav.call_args.args else nav.call_args.kwargs["pages"]
        self.assertEqual([p.title for p in pages], ["壓力測試", "計算方法說明"])

    def test_old_links_work_with_lang_and_give_the_same_numbers(self):
        zh = self.start(loan="500")
        en = self.start(loan="500", lang="en")
        self.assertEqual(self.query_without_lang(en), self.query_without_lang(zh))
        self.assertEqual([v.replace("NT$", "$") for _, v in self.metric_pairs(en)], [v for _, v in self.metric_pairs(zh)])

    def test_html_report_is_marked_english(self):
        with Recorder() as rec:
            self.start(lang="en")
        self.assertIn("lang='en'", rec.report_html().replace('"', "'")[:200], "E-22：報告的 <html lang> 是 en")
        with Recorder() as rec:
            self.start()
        self.assertIn("lang='zh-Hant'", rec.report_html().replace('"', "'")[:200], "中文報告維持 zh-Hant")


# =====================================================================
# TC-39-03：中日韓字元掃描（SPEC 7 的核心驗收）
# =====================================================================

class NoCjkInEnglishTests(English, unittest.TestCase):
    def test_default(self):
        with self.observing() as (rec, cfg, nav):
            at = self.start(lang="en")
        texts = self.assertEnglish(at, rec, cfg, nav, "預設情境", minimum=300)
        kinds = {k for k, _ in texts}
        for expected in ("metric", "plotly_chart", "chart", "報告", "報告 HTML", "CSV 欄名", "下載檔名", "page_title", "導覽"):
            self.assertIn(expected, kinds, f"測試前提：掃描範圍要涵蓋 {expected}")

    def test_scenarios_with_many_options_on(self):
        for name, query in SCAN_SETUPS.items():
            with self.subTest(name):
                with self.observing() as (rec, cfg, nav):
                    at = self.start(lang="en", **query)
                self.assertEnglish(at, rec, cfg, nav, f"情境「{name}」", minimum=300)

    def test_after_the_safety_limit_is_calculated(self):
        at = self.start(lang="en")
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.button(key=SAFE_KEY).click().run())
        texts = self.assertEnglish(at, rec, cfg, nav, "算完安全邊界", minimum=300)
        self.assertIn("Default-risk map", self.prose(texts), "測試前提：熱圖已出現")

    def test_safety_limit_every_conclusion_sentence(self):
        ok = {"principal": (8_200_000.0, 0.04, "ok"), "salary_cap": (20_000.0, 0.04, "ok")}
        all_meet = {"principal": ("hi", 0.01, "all_meet"), "salary_cap": (0.0, 0.01, "all_meet")}
        none_meet = {"principal": (None, 0.2, "none_meet"), "salary_cap": (None, 0.2, "none_meet")}
        for p_name, p in (("ok", ok), ("all_meet", all_meet), ("none_meet", none_meet)):
            for s_name, s in (("ok", ok), ("all_meet", all_meet), ("none_meet", none_meet)):
                with self.subTest(principal=p_name, salary=s_name):
                    solver = fake_solver({"principal": p["principal"], "salary_cap": s["salary_cap"]})
                    at = self.start(lang="en", loan="500")
                    with spy_everywhere("solve_for", solver), self.observing() as (rec, cfg, nav):
                        at = self.ok(at.button(key=SAFE_KEY).click().run())
                    self.assertEnglish(at, rec, cfg, nav, f"安全邊界結論（本金 {p_name}／自掏 {s_name}）", minimum=300)

    def test_safety_limit_conclusion_sentences_follow_the_design(self):
        # DESIGN 4.3「安全邊界結論句」的句型（粗體記號與數字不比對）。
        cases = {"ok": ("With your other settings unchanged, the most you can borrow and keep the chance of default at or below",
                        "To keep the chance of default at or below"),
                 "all_meet": ("Even at the search limit of", "Even paying nothing in each month"),
                 "none_meet": ("Even borrowing just", "Even paying in up to")}
        results = {"ok": {"principal": (8_200_000.0, 0.04, "ok"), "salary_cap": (20_000.0, 0.04, "ok")},
                   "all_meet": {"principal": ("hi", 0.01, "all_meet"), "salary_cap": (0.0, 0.01, "all_meet")},
                   "none_meet": {"principal": (None, 0.2, "none_meet"), "salary_cap": (None, 0.2, "none_meet")}}
        for status, (principal_sentence, salary_sentence) in cases.items():
            with self.subTest(status):
                at = self.start(lang="en", loan="500")
                with spy_everywhere("solve_for", fake_solver(results[status])):
                    at = self.ok(at.button(key=SAFE_KEY).click().run())
                page = self.page(visible_texts(at)).replace("**", "")
                self.assertIn(principal_sentence, page)
                self.assertIn(salary_sentence, page)

    def test_safety_limit_without_salary(self):
        at = self.start(lang="en", salary="0", **NO_SALARY_ORDER)
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.button(key=SAFE_KEY).click().run())
        self.assertEnglish(at, rec, cfg, nav, "沒有薪水補貼的安全邊界", minimum=300)

    def test_safety_limit_engine_error(self):
        # engine.solve_for 自己丟的錯誤（target_ruin 超出範圍）：D8，英文模式要顯示英文。
        real = __import__("engine").solve_for

        def broken(df, params, field, target_ruin, lo, hi, step):
            return real(df, params, field, 1.5, lo, hi, step)

        at = self.start(lang="en")
        with spy_everywhere("solve_for", broken), self.observing() as (rec, cfg, nav):
            at = self.ok(at.button(key=SAFE_KEY).click().run())
        self.assertTrue(len(at.error) >= 1, "測試前提：要顯示錯誤")
        self.assertEnglish(at, rec, cfg, nav, "安全邊界計算失敗", minimum=100)

    def test_credit_limit_situations(self):
        cases = {
            "信貸超過上限（本金大於可借上限）": dict(loan="300"),
            "估計可核貸模式": dict(lmode="1"),
            "債務用完法規上限": dict(udebt="600"),
            "有債務、本金高於估計可核貸": dict(udebt="10", loan="95"),
            "本金高於估計但未超過上限": dict(loan="105"),
            "月付比偏高（平均月收入低）": dict(inc="2", loan="100"),
            "不提供月收入": dict(inc="0"),
            "月付比超過 70%": dict(inc="3", loan="150", years="3"),
            "選理財型房貸": dict(type="0"),
            "房貸加寬限期": dict(type="0", grace="1", grace_y="3"),
        }
        for name, query in cases.items():
            with self.subTest(name):
                with self.observing() as (rec, cfg, nav):
                    at = self.start(lang="en", **query)
                self.assertEnglish(at, rec, cfg, nav, name, minimum=100)

    def test_switching_the_loan_type_toast(self):
        at = self.start(lang="en")
        with self.observing() as (rec, cfg, nav):
            radio = at.radio(key="type")
            at = self.ok(radio.set_value(radio.options[0]).run())
        self.assertTrue(len(at.toast) >= 1, "測試前提：切換貸款種類會有 toast")
        self.assertEnglish(at, rec, cfg, nav, "切換貸款種類之後", minimum=100)

    def test_results_out_of_date(self):
        at = self.start(lang="en")
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.number_input(key="loan").set_value(150.0).run())
        self.assertEqual(at.button(key=RUN_KEY).proto.type, "primary", "測試前提：結果已過期")
        self.assertTrue(len(at.toast) >= 1 and len(at.warning) >= 1, "測試前提：過期提示與 toast")
        self.assertEnglish(at, rec, cfg, nav, "結果過期", minimum=300)

    def test_safety_limit_out_of_date(self):
        at = self.start(lang="en", loan="500")
        at = self.ok(at.button(key=SAFE_KEY).click().run())
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.number_input(key="loan").set_value(600.0).run())
        self.assertEnglish(at, rec, cfg, nav, "安全邊界也過期", minimum=300)

    def test_auto_recalculate_on(self):
        with self.observing() as (rec, cfg, nav):
            at = self.start(lang="en", auto="1")
        self.assertEnglish(at, rec, cfg, nav, "自動重算開啟", minimum=300)

    def test_input_errors(self):
        for name, (query, key, value) in INPUT_ERRORS.items():
            with self.subTest(name):
                with self.observing() as (rec, cfg, nav):
                    at = self.bad_input(query, key, value)
                self.assertEnglish(at, rec, cfg, nav, name, minimum=100)

    def test_engine_error_on_run(self):
        with self.observing() as (rec, cfg, nav):
            at = self.start(lang="en", loan="100", lfee="2000000")
        self.assertTrue(len(at.error) >= 1, "測試前提：引擎拒絕這組設定")
        self.assertEnglish(at, rec, cfg, nav, "貸款開辦費大於本金", minimum=100)

    def test_input_error_after_a_good_run(self):
        at = self.start(lang="en")
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.text_input(key="a").set_value("../etc").run())
            at = self.ok(at.button(key=RUN_KEY).click().run())
        self.assertTrue(len(at.error) >= 1, "測試前提：要顯示錯誤")
        self.assertEnglish(at, rec, cfg, nav, "算完之後輸入錯誤", minimum=300)

    def test_data_unavailable(self):
        # 用真的 load_history：yf 失敗、沒有任何存檔 → market_data 自己丟的訊息。
        for with_yf in (True, False):
            with self.subTest(live_source=with_yf):
                at = self.start_with_real_loader(with_yf, lang="en", a="ZZZZ.TW")
                self.assertTrue(len(at.error) >= 1, "測試前提：要顯示錯誤")
                self.assertEnglish(at, None, None, None, "行情抓不到", minimum=100)

    def test_data_problems_shown_as_warnings_and_notes(self):
        cases = {"存檔資料（即時行情抓不到）": dict(a="STALE.TW"), "股票分割自動修正": dict(a="SEAM.TW"),
                 "上市太短（沒有替身）": dict(a="NEW1.TW", proxy=""), "上市太短（有替身）": dict(a="NEW1.TW"),
                 "兩檔沒有共同月份": dict(a="NEW1.TW", b="OLD1.TW", proxy=""),
                 "上市很久": dict(a="OLD0050.TW", m="2008-01")}
        for name, query in cases.items():
            with self.subTest(name):
                with self.observing() as (rec, cfg, nav):
                    at = self.start(lang="en", **query)
                self.assertEnglish(at, rec, cfg, nav, name, minimum=100)

    def test_unusable_stand_in_is_a_warning(self):
        at = self.start(lang="en")
        with self.observing() as (rec, cfg, nav):
            at = self.ok(at.text_input(key="proxy").set_value("NO GOOD").run())
            at = self.ok(at.button(key=RUN_KEY).click().run())
        self.assertTrue(len(at.warning) >= 1, "測試前提：替身不能用的提醒")
        self.assertEnglish(at, rec, cfg, nav, "替身代號不能用", minimum=100)

    def test_details_page(self):
        at, links = self.details_page("en")
        texts = visible_texts(at) + [("page_link", label) for label in links]
        self.assertGreater(len(texts), 40, "測試前提：說明頁有內容")
        for node in at.get("latex"):
            texts.append(("latex", node.value))
        found = leaks(texts)
        self.assertEqual(found, [], "說明頁英文模式出現中日韓字元：\n" + "\n".join(found[:15]))

    def test_csv_file_names_and_cells(self):
        with Recorder() as rec:
            self.start(lang="en")
        self.assertTrue(rec.csv_frames(), "測試前提：有 CSV 下載")
        for label, name, frame in rec.csv_frames():
            with self.subTest(label):
                self.assertEqual(leaks([("CSV 欄名", c) for c in frame.columns] + [("下載檔名", name)]), [])
                cells = [("CSV 儲存格", v) for col in frame.columns for v in frame[col].tolist() if isinstance(v, str)]
                self.assertEqual(leaks(cells)[:5], [], "CSV 內容也不該有中文字串")


# =====================================================================
# D8：engine、market_data 的訊息在英文模式下是英文（TC-39-04）
# =====================================================================

class ErrorMessageTests(English, unittest.TestCase):
    def english_errors(self, at):
        errors = [clean(shown(e)) for e in at.error]
        self.assertTrue(errors, "測試前提：要有錯誤訊息")
        return errors

    def assertReadableEnglish(self, errors):
        for text in errors:
            self.assertEqual(leaks([("error", text)]), [], text)
            self.assertGreaterEqual(len(WORDS.findall(text)), 3, f"錯誤訊息要是完整的英文句子：{text}")

    def test_user_input_errors_in_english(self):
        for name, (query, key, value) in INPUT_ERRORS.items():
            with self.subTest(name):
                self.assertReadableEnglish(self.english_errors(self.bad_input(query, key, value)))

    def test_engine_error_in_english(self):
        self.assertReadableEnglish(self.english_errors(self.start(lang="en", loan="100", lfee="2000000")))

    def test_ticker_error_names_the_ticker(self):
        errors = self.english_errors(self.bad_input({}, "a", "../etc"))
        self.assertTrue(any("../etc" in e or "ticker" in e.lower() for e in errors), "E-20：錯誤訊息要說明哪裡錯")

    def test_the_same_errors_are_still_chinese_in_chinese_mode(self):
        cases = [(q, k, v, "zh") for q, k, v in INPUT_ERRORS.values()]
        for query, key, value, _ in cases:
            with self.subTest(key=key, value=value):
                errors = [shown(e) for e in self.bad_input(query, key, value, lang=None).error]
                self.assertTrue(errors and all(CJK.search(e) for e in errors), "D8：預設中文訊息不變")
        errors = [shown(e) for e in self.start(loan="100", lfee="2000000").error]
        self.assertTrue(errors and all(CJK.search(e) for e in errors))

    def test_data_errors_in_english(self):
        for with_yf in (True, False):
            with self.subTest(live_source=with_yf):
                at = self.start_with_real_loader(with_yf, lang="en", a="ZZZZ.TW")
                self.assertReadableEnglish(self.english_errors(at))

    def test_data_errors_translate_after_a_language_switch(self):
        # E-21：st.cache_data 裡的訊息是「代碼＋參數」，切語言之後要重新翻譯，不能還是中文。
        at = self.start_with_real_loader(True, a="ZZZZ.TW")
        self.assertTrue(any(CJK.search(shown(e)) for e in at.error), "測試前提：中文模式看到中文錯誤")
        with self.failing_loader(True):
            at = self.switch(at, "en")
        self.assertReadableEnglish(self.english_errors(at))

    def test_cached_data_notes_translate_after_a_language_switch(self):
        for ticker in ("SEAM.TW", "STALE.TW"):
            with self.subTest(ticker):
                at = self.start(a=ticker)
                zh_notes = [t for k, t in visible_texts(at) if k in ("info", "warning", "caption") and CJK.search(t)]
                self.assertTrue(zh_notes)
                at = self.switch(at, "en")
                self.assertEqual(leaks(self.gather(at)), [], "快取過的資料提醒切到英文後仍是中文")

    def test_job_loss_and_other_engine_messages(self):
        # 失業設定、黑天鵝設定走 engine；全部打開後的整頁不可有中文（含警示）。
        at = self.start(lang="en", jl="1", jl_mode="1", jl_start="1", jl_dur="60", swan="1", swan_m="1", shock="1",
                        shock_y="1", salary="0", **NO_SALARY_ORDER)
        self.assertEqual(leaks(self.gather(at)), [])


# =====================================================================
# TC-39-02、E-04、D16：切換語言不改變設定與結果
# =====================================================================

class SwitchTests(English, unittest.TestCase):
    def watch(self):
        return spy_everywhere("run_summary")

    def test_switching_does_not_recalculate_or_go_stale(self):
        at = self.start()
        before = self.metric_pairs(at)
        with self.watch() as summary, spy_everywhere("run_trace") as trace, spy_everywhere("solve_for") as solve, \
                spy_everywhere("sensitivity_grid") as grid:
            at = self.switch(at, "en")
            self.assertEqual(summary.call_count, 0, "E-04：切換語言不重算（run_summary）")
            self.assertEqual(trace.call_count, 0)
            self.assertEqual(solve.call_count + grid.call_count, 0)
            self.assertEqual(self.title(at), EN_TITLE)
            self.assertEqual(at.button(key=RUN_KEY).proto.type, "secondary", "E-04：切換語言不標示過期")
            self.assertFalse([w for w in at.warning if any(s in clean(shown(w)) for s in STALE_WORDS)])
            self.assertEqual(len(at.toast), 0, "切換語言不跳「設定已變更」的 toast")
            after_en = self.metric_pairs(at)
            at = self.switch(at, "zh")
            self.assertEqual(summary.call_count, 0, "切回中文也不重算")
            self.assertEqual(self.title(at), ZH_TITLE)
        self.assertEqual(self.metric_pairs(at), before, "切回中文：結果與原來完全相同")
        self.assertEqual(len(after_en), len(before))

    def test_numbers_are_identical_and_money_uses_nt_dollar(self):
        at = self.start(loan="500")
        zh = self.metric_pairs(at)
        at = self.switch(at, "en")
        en = self.metric_pairs(at)
        self.assertEqual(len(en), len(zh))
        self.assertEqual([v.replace("NT$", "$") for _, v in en], [v for _, v in zh], "數字與中文模式完全相同")
        dollars = [v for _, v in en if "$" in v]
        self.assertTrue(dollars, "測試前提：有金額指標")
        for value in dollars:
            self.assertIn("NT$", value, "TC-39-05：金額以 NT$ 開頭")
            self.assertFalse(UNMARKED_DOLLAR.search(value), value)
        self.assertNotEqual([l for l, _ in en], [l for l, _ in zh], "標籤要換成英文")

    def test_every_setting_survives_a_switch(self):
        # E-21：選項若以中文標籤存放，切到英文會被重設成預設值。用一組全部離開預設值的設定檢查。
        query = {**MANY, "salary": "40000", "p2": "3", "dca": "1", "payday": "1", "lfee": "3000"}
        at = self.start(**query)
        before_widgets, before_query = widget_snapshot(at), self.query_without_lang(at)
        before_metrics = self.metric_pairs(at)
        at = self.switch(at, "en")
        self.assertEqual(widget_snapshot(at), before_widgets, "切換語言之後，所有欄位的值不變")
        self.assertEqual(self.query_without_lang(at), before_query, "網址上除了 lang 之外都不變")
        self.assertEqual(self.qp(at, "lang"), "en")
        self.assertEqual([v.replace("NT$", "$") for _, v in self.metric_pairs(at)], [v for _, v in before_metrics])
        at = self.switch(at, "zh")
        self.assertEqual(widget_snapshot(at), before_widgets)
        self.assertEqual(self.query_without_lang(at), before_query)
        self.assertNotIn("lang", at.query_params, "切回中文：lang 從網址消失")

    def test_a_stale_result_stays_stale_and_fresh_stays_fresh(self):
        at = self.start()
        at = self.ok(at.number_input(key="loan").set_value(150.0).run())
        self.assertEqual(at.button(key=RUN_KEY).proto.type, "primary")
        with self.watch() as summary:
            at = self.switch(at, "en")
            self.assertEqual(summary.call_count, 0)
            self.assertEqual(at.button(key=RUN_KEY).proto.type, "primary", "原本就過期：切換之後仍過期")
            self.assertEqual(at.number_input(key="loan").value, 150.0, "切換語言不動設定")
            at = self.ok(at.button(key=RUN_KEY).click().run())
            self.assertEqual(summary.call_count, 1, "在英文介面按「Run」只算一次")
        self.assertEqual(at.button(key=RUN_KEY).proto.type, "secondary")

    def test_calculated_safety_limit_survives_a_switch(self):
        at = self.start(loan="500")
        at = self.ok(at.button(key=SAFE_KEY).click().run())
        zh_map = [n for n in at.get("plotly_chart") if "heatmap" in n.proto.spec]
        self.assertTrue(zh_map, "測試前提：熱圖已算出")
        with spy_everywhere("solve_for") as solve, spy_everywhere("sensitivity_grid") as grid:
            at = self.switch(at, "en")
            self.assertEqual(solve.call_count + grid.call_count, 0, "切換語言不重算安全邊界")
        self.assertTrue([n for n in at.get("plotly_chart") if "heatmap" in n.proto.spec], "切換後熱圖仍在")
        self.assertEqual(leaks(self.gather(at)), [], "已算出的安全邊界切到英文後仍有中文")

    def test_input_error_follows_the_language(self):
        at = self.bad_input({"scen": "3"}, "path", "5, -150", lang=None)
        self.assertTrue(any(CJK.search(shown(e)) for e in at.error))
        at = self.switch(at, "en")
        self.assertTrue(len(at.error) >= 1)
        self.assertEqual(leaks(self.gather(at)), [])
        self.assertEqual(at.text_input(key="path").value, "5, -150", "使用者輸入的文字不動")

    def test_lang_in_the_url_is_the_only_extra_parameter(self):
        at = self.start(loan="500")
        before = {k: self.qp(at, k) for k in at.query_params}
        at = self.switch(at, "en")
        self.assertEqual({k: self.qp(at, k) for k in at.query_params}, {**before, "lang": "en"})

    def test_reload_market_data_in_english(self):
        at = self.start(lang="en")
        found = [b for b in at.sidebar.button if b.label == "Reload market data"]
        self.assertEqual(len(found), 1, "術語表 11")


# =====================================================================
# D18：單機版載入畫面中英並列；新模組要放進單機檔
# =====================================================================

class StandaloneTests(unittest.TestCase):
    def boot_block(self, html):
        start = html.index('<div id="boot">')
        return html[start:html.index('<div id="root">', start)]

    def test_loading_screen_shows_chinese_and_english_side_by_side(self):
        block = re.sub(r"<[^>]+>", " ", self.boot_block(build_standalone.build()))
        self.assertRegex(block, CJK, "D18：載入畫面保留中文")
        english = re.findall(r"[A-Za-z][A-Za-z'’-]*", re.sub(r"[　-ヿ㐀-鿿＀-￯]+", " ", block))
        self.assertGreaterEqual(len(english), 20, "D18：載入畫面有一整段英文說明（不只是標題）")
        self.assertTrue(re.search(r"Python|download|browser", block, re.I), "英文說明要提到在瀏覽器準備 Python 環境")
        self.assertIn("Borrow-to-Invest ETF Stress Test", block, "英文標題")
        self.assertIn("借錢投資 ETF 壓力測試", block, "中文標題")

    def test_the_built_file_has_the_same_loading_screen(self):
        path = build_standalone.OUTPUT
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        self.assertEqual(self.boot_block(html), self.boot_block(build_standalone.build()), "dist/ 要重新產生")

    def test_new_modules_are_shipped_in_the_standalone_file(self):
        for module in ("i18n.py",):
            if os.path.exists(os.path.join(HERE, module)):
                self.assertIn(module, build_standalone.APP_FILES, f"{module} 要放進 APP_FILES")
                with open(build_standalone.OUTPUT, encoding="utf-8") as fh:
                    self.assertIn(f'"{module}"', fh.read())


# =====================================================================
# 術語一致（DESIGN 4.3）與寫法（E-10～E-20）
# =====================================================================

class TerminologyTests(English, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """英文頁面只跑一次（預設與 dca=1 兩種），全班測試共用。"""
        cls._cache = {}
        with ExitStack() as stack:
            st.cache_data.clear()
            stack.enter_context(patch("market_data.MIRROR_URL", new=""))
            stack.enter_context(patch("market_data.load_history", side_effect=fake_history))
            market_data._index_cache.update(at=float("-inf"), entries=None)
            for query in ({}, {"dca": "1"}):
                with Recorder() as rec, patch("streamlit.set_page_config", wraps=st.set_page_config) as cfg, \
                        patch("streamlit.navigation", wraps=st.navigation) as nav:
                    at = AppTest.from_file(APP, default_timeout=180)
                    at.query_params["lang"] = "en"
                    for key, value in query.items():
                        at.query_params[key] = value
                    at.run()
                    assert not at.exception, [str(e.value) for e in at.exception]
                    cls._cache[tuple(sorted(query.items()))] = (at, cls.gather(cls, at, rec, cfg, nav), rec)

    def english_page(self, **query):
        return self._cache[tuple(sorted(query.items()))]

    def test_titles_and_sidebar_sections(self):
        at, texts, _ = self.english_page()
        self.assertEqual(self.title(at), EN_TITLE)                                         # 1
        headers = [h.value for h in at.sidebar.header]
        for expected in ("1. Loan", "2. What you buy and what happens to dividends",
                         "3. Where each monthly payment comes from", "4. Assumed future", "5. Advanced",
                         "6. Taxes and fees"):                                              # 17, 28, 34, 44, 47, 50
            self.assertIn(expected, headers)

    def test_buttons_and_toggles(self):
        at, _, _ = self.english_page()
        self.assertEqual(at.button(key=RUN_KEY).label, "Run")                              # 6
        self.assertIn("Auto-recalculate", [t.label for t in at.sidebar.toggle])             # 7
        self.assertIn("Reload market data", [b.label for b in at.sidebar.button])            # 11

    def test_metric_names(self):
        at, _, _ = self.english_page()
        labels = [m.label for m in at.metric]
        for expected in ("Chance of default (missed a payment)", "Chance of default (all start months)",   # 60, 61
                         "Chance of beating DCA", "Median final value (no default)",                      # 62, 63
                         "DCA: median final value", "Cash buffer at the start",                           # 64, 66
                         "Monthly payment at first"):                                                      # 65
            self.assertIn(expected, labels)

    def test_result_headings_and_options(self):
        _, texts, _ = self.english_page()
        page = self.prose(texts)
        for expected in ("Historical backtest: if you had started back then",                  # 56
                         "Monte Carlo simulation: 2,000 possible futures",                      # 58
                         "Month-by-month detail",                                               # 79
                         "Loan type", "Annual interest rate", "Loan term", "Monthly out-of-pocket limit",
                         "Main ETF", "Reinvest dividends", "Highest chance of default you'll accept",
                         "Find safety limit", "Safety limit: how much can you borrow?",         # 81、82、83
                         "Personal loan (short term, usually no interest-only period)",         # 21
                         "Home-equity loan (long term, interest-only period available)"):       # 20
            self.assertIn(expected, page)

    def test_loan_amount_label_and_help_use_the_ten_thousand_unit(self):
        # E-15：輸入欄位以萬為單位，標籤寫 NT$10,000，不能出現「萬」，也不能憑空換算。
        at, _, _ = self.english_page()
        self.assertIn("Loan amount (in NT$10,000)", [w.label for w in at.number_input])      # 18

    def test_default_is_never_used_as_a_noun_for_standard_values(self):
        # E-12：「預設」不用 default 當名詞；default 只指「破產」。這裡抽查沒有 "defaults to"／"the default" 之類的寫法。
        _, texts, _ = self.english_page()
        page = self.prose(texts)
        for bad in (r"\bdefault values?\b", r"\bdefault settings?\b", r"\bdefaults? to\b", r"\bthe default\b",
                    r"(?<!of )(?<!chance of )default is\b"):
            self.assertNotRegex(page.lower(), bad, bad)

    def test_banned_synonyms(self):
        # E-12、E-19：不用 ruin、bankruptcy；不用 TWD；「破產」一律 default。
        at, texts, rec = self.english_page()
        pages = {"主頁": self.prose(texts), "說明頁": self.page(visible_texts(self.details_page("en")[0]))}
        for where, page in pages.items():
            lower = page.lower()
            for word in ("ruin", "bankrupt", "twd"):
                self.assertNotRegex(lower, rf"\b{word}", f"{where}不該出現 {word}")
        self.assertNotRegex(rec.report_html().lower(), r"\b(ruin|bankrupt|twd)")

    def test_money_is_written_with_nt_dollar(self):
        # E-14：不寫 $ 開頭的金額（metric、說明文字、報告、圖表）。
        at, texts, rec = self.english_page()
        bad = [f"{k}: {clean(t)[:70]}" for k, t in texts if k != "報告 HTML" and UNMARKED_DOLLAR.search(clean(t))
               and not re.search(r"\$\$|\\\$|\\frac|\\times", t)]
        self.assertEqual(bad[:10], [], "金額要寫成 NT$12,345；沒有 NT 的 $ 出現在：")

    def test_dca_is_introduced_once_in_full(self):
        # E-13：第一次出現寫 dollar-cost averaging (DCA)，之後 DCA。
        _, texts, _ = self.english_page(dca="1")
        self.assertIn("dollar-cost averaging (DCA)", self.prose(texts))
        self.assertIn("dollar-cost averaging (DCA)", self.page(visible_texts(self.details_page("en")[0])))

    def test_nhi_is_explained(self):
        _, texts, _ = self.english_page()
        page = self.prose(texts)
        self.assertIn("NHI supplementary premium", page)                                      # 52（E-17）
        self.assertIn("National Health Insurance", page)

    def test_heatmap_uses_english_names_and_short_money(self):
        at = self.start(lang="en", loan="500")
        at = self.ok(at.button(key=SAFE_KEY).click().run())
        strings = [s for n in at.get("plotly_chart") for s in json_strings(n.proto.spec)]
        joined = " ".join(strings)
        self.assertIn("Default-risk map", self.prose(visible_texts(at)))                    # 86
        self.assertRegex(joined, r"NT\$\d+(\.\d+)?M", "E-15：熱圖刻度寫 NT$8.2M 這種短寫")

    def test_sentences_are_sentence_case(self):
        # E-11：標題、按鈕、指標名稱用 sentence case（只有第一個字大寫）。
        at, _, _ = self.english_page()
        labels = [m.label for m in at.metric] + [at.button(key=RUN_KEY).label]
        for label in labels:
            words = re.findall(r"[A-Za-z][A-Za-z'’-]*", label)
            title_cased = [w for w in words[1:] if w[0].isupper() and w.upper() != w and w not in ("DCA",)]
            self.assertEqual(title_cased, [], f"E-11：{label}")

    def test_details_page_names(self):
        at, links = self.details_page("en")
        self.assertIn("How it works", at.title[0].value)                                     # 3
        self.assertTrue(links and all(label == "← Back to the stress test" for label in links), links)   # 4

    def test_report_names(self):
        _, _, rec = self.english_page()
        parts = rec.last_report()
        self.assertIn("ETF Stress Test", parts["title"])
        groups = [g for g, _ in parts["summaries"]]
        self.assertIn("Historical backtest", groups)                                         # 55
        shown_metrics = {m.label: m.value for m in self.english_page()[0].metric}
        reported = {label: value for _, rows in parts["summaries"] for label, value in rows}
        self.assertEqual(reported, shown_metrics, "SPEC 5：報告與畫面用同一套名稱與數字（英文也一樣）")


if __name__ == "__main__":
    unittest.main()
