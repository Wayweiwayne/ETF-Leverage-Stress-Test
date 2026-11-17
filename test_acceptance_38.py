"""第 38 項（白話介面）的驗收測試。

依據：SPEC-v40 第 5 節與決議 D15；DESIGN-v40 第 1 節（用語對照表 T-xx、1.10 禁用字）。
用 AppTest 離線跑整個 App（假行情），收集畫面、說明頁、報告、CSV 欄名、下載檔名與 help 提示中
所有看得到的文字。舊連結的基準值是 V39 程式在同一份假行情下的結果（QA 於衝刺 2 開始前記錄）。
"""
import os
import re
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from test_acceptance_helpers import (AppHarness, Recorder, DETAILS_PAGE, HERE, report_texts, strip_markup,
                                     visible_texts)
from version import APP_VERSION

# DESIGN 1.10：大小寫只列出 Scenario／scenario、Trace／trace 兩種，這裡一律不分大小寫。
BANNED = [("宇宙", re.compile("宇宙")), ("Accounting Trace", re.compile("Accounting Trace", re.I)),
          ("Block Bootstrap", re.compile("Block Bootstrap", re.I)), ("Scenario", re.compile("scenario", re.I)),
          ("Trace", re.compile("trace", re.I)), ("Ledger", re.compile("ledger", re.I)),
          ("Vol Drag", re.compile("vol drag", re.I)), ("MC", re.compile(r"(?<![A-Za-z])MC(?![A-Za-z])")),
          ("引擎", re.compile("引擎")), ("微觀", re.compile("微觀")), ("平行", re.compile("平行")),
          ("實證", re.compile("實證")), ("理論", re.compile("理論")), ("斷頭", re.compile("斷頭"))]
DCA_OK = "定期定額（DCA）"

# 讓條件式出現的文字（升息、失業、黑天鵝、賤賣、浮動利率、自訂情境、不再投入…）也被掃到。
SCAN_SETUPS = {
    "預設": {},
    "很多情境": dict(type="0", shock="1", float="1", jl="1", jl_mode="1", swan="1", hc="1", drag="1",
                    scen="3", path="5, -10, 20", buf="2", seed="0"),
    "不再投入": dict(reinv="0", p1="1", jl="1", m="2019-05"),
}

# V39 的分享連結與當時的結果（V39 程式、test_app.fake_history 假行情、固定亂數）。
OLD_LINKS = {
    "default": ({}, {
        "metrics": ["$67,199", "$67,199", "$0", "0.0%", "0.0%", "91.6%", "$4,609,599", "$3,332,274", "0.0%",
                    "97.3%", "$7,982,072", "$3,741,921"],
        "widgets": {"m": 71, "payday": 0, "p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0, "scen": 0, "dfreq": 0,
                    "dca": 0, "mcdiv": 0, "paths": 0, "block": 1, "itax": 2, "type": 1, "rate": 3.5, "years": 7,
                    "ratio_b": 50, "buf": 0, "div": 6.0, "div_beta": 0.5, "disc": 0.0, "dshare": 100, "loan": 500,
                    "salary": 25000, "fee": 0.1425, "stax": 0.1, "lfee": 0, "grace": False, "shock": False,
                    "float": False, "reinv": True, "jl": False, "hc": False, "swan": False, "drag": True,
                    "fix": True, "seed": True, "nhi": True, "a": "00878.TW", "proxy": "0056.TW", "b": "00631L.TW"}}),
    "mortgage": (dict(type="0", loan="800", rate="2.2", grace_y="2", salary="30000", swan="1", swan_m="18",
                      swan_d="35", m="2020-03"), {
        "metrics": ["$14,666", "$44,886", "$0", "0.0%", "94.4%", "$29,897,810", "$21,812,251", "0.0%", "98.6%",
                    "$92,619,747", "$39,253,995"],
        "widgets": {"m": 49, "payday": 0, "p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0, "scen": 0, "dfreq": 0,
                    "dca": 0, "mcdiv": 0, "paths": 0, "block": 1, "itax": 2, "type": 0, "rate": 2.2, "years": 20,
                    "grace_y": 2, "ratio_b": 50, "buf": 0, "swan_m": 18, "swan_d": 35, "div": 6.0, "div_beta": 0.5,
                    "disc": 0.0, "dshare": 100, "loan": 800, "salary": 30000, "fee": 0.1425, "stax": 0.1, "lfee": 0,
                    "grace": True, "shock": False, "float": False, "reinv": True, "jl": False, "hc": False,
                    "swan": True, "drag": True, "fix": True, "seed": True, "nhi": True, "a": "00878.TW",
                    "proxy": "0056.TW", "b": "00631L.TW"}}),
    "stress": (dict(loan="650", p1="3", p2="5", ratio_b="30", jl="1", jl_mode="1", jl_prob="10", shock="1",
                    shock_y="2", shock_d="1.5", scen="3", path="5, -10, 20", div="5.5", nhi="0", itax="3",
                    lfee="5000", buf="3"), {
        "metrics": ["$87,359", "$87,359", "$262,077", "1.9%", "0.0%", "98.1%", "$2,998,347", "$0", "5.0%", "94.7%",
                    "$4,606,473", "$0"],
        "widgets": {"m": 71, "payday": 0, "p1": 3, "p2": 3, "p3": 0, "p4": 0, "p5": 0, "jl_dist": 0, "scen": 3,
                    "dfreq": 0, "dca": 0, "mcdiv": 0, "paths": 0, "block": 1, "itax": 3, "type": 1, "jl_mode": 1,
                    "rate": 3.5, "years": 7, "shock_y": 2, "shock_d": 1.5, "ratio_b": 30, "jl_prob": 10.0,
                    "jl_mean": 5.0, "jl_sigma": 0.6, "jl_thr": 15, "jl_extra": [8.0, 12.0], "buf": 3, "div": 5.5,
                    "div_beta": 0.5, "disc": 0.0, "dshare": 100, "loan": 650, "salary": 25000, "jl_sal": 0,
                    "fee": 0.1425, "stax": 0.1, "lfee": 5000, "grace": False, "shock": True, "float": False,
                    "reinv": True, "jl": True, "jl_crash": True, "hc": False, "swan": False, "drag": True,
                    "fix": True, "seed": True, "nhi": False, "a": "00878.TW", "proxy": "0056.TW", "b": "00631L.TW",
                    "path": "5, -10, 20"}}),
    "advanced": (dict(float="1", rpath="0.5, 0.25", rvol="0.5", block="0", dca="1", mcdiv="1", hc="1", hc_thr="15",
                      hc_pen="10", disc="1.5", drag="0", dfreq="2", div_beta="0.8", fee="0.2", stax="0.3",
                      dshare="80", jl="1", jl_sal="5000", jl_start="6", jl_dur="9", payday="1"), {
        "metrics": ["$67,199", "$67,199", "$0", "0.0%", "0.0%", "0.0%", "$3,425,135", "$8,521,461", "0.1%", "9.1%",
                    "$6,138,834", "$9,449,439"],
        "widgets": {"m": 71, "payday": 1, "p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0, "scen": 0, "dfreq": 2,
                    "dca": 1, "mcdiv": 1, "paths": 0, "block": 0, "itax": 2, "type": 1, "jl_mode": 0, "rate": 3.5,
                    "years": 7, "rvol": 0.5, "ratio_b": 50, "jl_start": 6, "jl_dur": 9, "buf": 0, "hc_thr": 15,
                    "hc_pen": 10.0, "div": 6.0, "div_beta": 0.8, "disc": 1.5, "dshare": 80, "loan": 500,
                    "salary": 25000, "jl_sal": 5000, "fee": 0.2, "stax": 0.3, "lfee": 0, "grace": False,
                    "shock": False, "float": True, "reinv": True, "jl": True, "hc": True, "swan": False,
                    "drag": False, "fix": True, "seed": True, "nhi": True, "rpath": "0.5, 0.25", "a": "00878.TW",
                    "proxy": "0056.TW", "b": "00631L.TW"}}),
    "no_reinvest": (dict(reinv="0", p1="1", p3="3", salary="20000", scen="1", a="OLD0050.TW"), {
        "metrics": ["$67,199", "$67,199", "$0", "4.8%", "7.0%", "67.4%", "$4,938,463", "$2,191,752", "7.7%", "77.7%",
                    "$10,344,649", "$3,418,694"],
        "widgets": {"m": 191, "payday": 0, "p1": 1, "p2": 0, "p3": 1, "p4": 0, "scen": 1, "dfreq": 0, "dca": 0,
                    "mcdiv": 0, "paths": 0, "block": 1, "itax": 2, "type": 1, "rate": 3.5, "years": 7, "buf": 0,
                    "div": 6.0, "div_beta": 0.5, "disc": 0.0, "dshare": 100, "loan": 500, "salary": 20000,
                    "fee": 0.1425, "stax": 0.1, "lfee": 0, "grace": False, "shock": False, "float": False,
                    "reinv": False, "jl": False, "hc": False, "swan": False, "drag": True, "fix": True,
                    "seed": True, "nhi": True, "a": "OLD0050.TW", "proxy": "0056.TW"}}),
}


def widget_snapshot(at):
    snap = {}
    for kind in ("selectbox", "radio"):
        for w in getattr(at, kind):
            if w.key:
                snap[w.key] = w.index
    for kind in ("slider", "number_input", "checkbox", "text_input"):
        for w in getattr(at, kind):
            if w.key:
                snap[w.key] = list(w.value) if isinstance(w.value, tuple) else w.value
    return snap


class ScanMixin:
    def assertNoBannedWords(self, texts, where):
        found = {}
        for kind, text in texts:
            clean = strip_markup(text)
            for word, pattern in BANNED:
                if pattern.search(clean):
                    found.setdefault(word, []).append(f"{kind}: {clean.strip()[:80]}")
            if "DCA" in clean.replace(DCA_OK, ""):
                found.setdefault("DCA（不是「定期定額（DCA）」的寫法）", []).append(f"{kind}: {clean.strip()[:80]}")
        self.assertEqual(found, {}, f"{where}出現禁用字")

    def run_details_page(self):
        links = []
        with patch("streamlit.page_link", side_effect=lambda *a, **k: links.append(k.get("label", ""))):
            at = AppTest.from_file(os.path.join(HERE, DETAILS_PAGE), default_timeout=60).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at, links


class BannedWordTests(ScanMixin, AppHarness, unittest.TestCase):
    """DESIGN 1.10＋SPEC 5＋D15：主頁、說明頁、報告、CSV 欄名、下載檔名、help 提示都不可出現禁用字。"""

    def scan_run(self, **query):
        with Recorder() as rec:
            at = self.start(**query)
        texts = visible_texts(at)
        texts += [("報告", t) for t in report_texts(rec.last_report())]
        for label, name, frame in rec.csv_frames():
            texts += [("CSV 欄名", str(c)) for c in frame.columns]
        texts += [("下載檔名", name or "") for _, name, _ in rec.downloads]
        texts += [("下載按鈕", label) for label, _, _ in rec.downloads]
        return at, texts

    def test_main_page_report_and_downloads(self):
        for name, query in SCAN_SETUPS.items():
            with self.subTest(name):
                _, texts = self.scan_run(**query)
                self.assertGreater(len(texts), 300, "測試前提：應收集到整頁的文字")
                self.assertNoBannedWords(texts, f"主頁／報告／下載（{name}）")

    def test_safety_section_after_it_is_calculated(self):
        at = self.start()
        with Recorder() as rec:
            at = self.ok(at.button(key="safe_run").click().run())
        texts = visible_texts(at) + [("報告", t) for t in report_texts(rec.last_report())]
        self.assertTrue(any("破產機率地圖" in t for _, t in texts), "測試前提：安全邊界已算出")
        self.assertNoBannedWords(texts, "算過安全邊界之後的主頁／報告")

    def test_details_page(self):
        at, links = self.run_details_page()
        texts = visible_texts(at) + [("page_link", label) for label in links]
        self.assertGreater(len(texts), 40)
        self.assertNoBannedWords(texts, "說明頁")

    def test_page_title_and_navigation(self):
        with patch("streamlit.set_page_config", wraps=st.set_page_config) as config, \
                patch("streamlit.navigation", wraps=st.navigation) as navigation:
            self.start()
        page_title = config.call_args.kwargs.get("page_title") or config.call_args.args[0]
        self.assertEqual(page_title, f"借錢投資 ETF 壓力測試 {APP_VERSION}")              # T-02
        pages = navigation.call_args.args[0] if navigation.call_args.args else navigation.call_args.kwargs["pages"]
        self.assertEqual([p.title for p in pages], ["壓力測試", "計算方法說明"])         # T-03、T-04
        self.assertNoBannedWords([("page_title", page_title)] + [("導覽", p.title) for p in pages], "分頁標題與導覽")


class NamingTests(ScanMixin, AppHarness, unittest.TestCase):
    def test_title_is_short_and_keeps_the_version(self):
        at = self.start()
        title = at.title[0].value
        self.assertEqual(title, f"借錢投資 ETF 壓力測試 ({APP_VERSION})")              # T-01
        self.assertLessEqual(len(title), 20, "D15：主標題連同空白與版本號不超過 20 個字")
        self.assertIn(f"({APP_VERSION})", title)

    def test_new_names_on_the_main_page(self):
        at = self.start()
        headers = [h.value for h in at.sidebar.header]
        for expected in ("1. 貸款條件", "2. 買什麼、配息怎麼用", "3. 每月還款的錢從哪來", "5. 進階設定"):  # T-10..T-19
            self.assertIn(expected, headers)
        labels = [m.label for m in at.metric]
        for expected in ("初期每月應繳", "開局預留的緩衝金", "破產機率（所有進場月份）", "破產機率（繳不出貸款）",
                         "贏過定期定額的機率", "期滿資產中位數（沒破產的）", "定期定額：期滿資產中位數"):  # T-60..T-68
            self.assertIn(expected, labels)
        texts = [t for _, t in visible_texts(at)]
        joined = "\n".join(texts)
        for expected in ("📜 歷史回測：如果當年進場", "🎲 蒙地卡羅模擬：2,000 種可能的未來",       # T-50、T-51
                         "🔍 逐月明細：挑一個月份進場看看", "要看哪一個月份進場",                # T-100、T-102
                         "歷史回測：每個月進場，期滿剩多少", "蒙地卡羅：期滿資產的分佈"):        # T-80、T-81
            self.assertIn(expected, joined)

    def test_csv_columns_and_file_names(self):
        with Recorder() as rec:
            self.start()
        downloads = {label: (name, frame) for label, name, frame in rec.csv_frames()}
        self.assertIn("📥 下載歷史回測結果 (CSV)", downloads)                                       # T-110
        self.assertIn("📥 下載蒙地卡羅結果 (CSV)", downloads)                                       # T-111
        self.assertIn("📥 下載逐月明細表 (CSV)", downloads)                                        # T-103
        name, ledger = downloads["📥 下載逐月明細表 (CSV)"]
        self.assertRegex(name, r"^monthly_detail_\d{4}-\d{2}\.csv$")
        hist = list(downloads["📥 下載歷史回測結果 (CSV)"][1].columns)
        for column in ("槓桿期滿資產", "槓桿期滿資產（沒破產的）", "定期定額期滿資產", "贏過定期定額的機率", "含假想未來"):
            self.assertIn(column, hist)                                                          # T-112
        mc = list(downloads["📥 下載蒙地卡羅結果 (CSV)"][1].columns)
        for column in ("槓桿期滿資產", "定期定額期滿資產", "贏過定期定額", "定期定額投入總額", "定期定額年化報酬率"):
            self.assertIn(column, mc)                                                            # T-113
        for column in ("第幾個月", "月份", "槓桿：手上資產", "定期定額：手上資產", "當月年利率 (%)", "已破產",
                       "當月應繳", "從薪水繳（自掏）", "從存下來的配息繳", "從緩衝金繳", "賣第一標的繳",
                       "定期定額：當月投入", "第一標的股數"):
            self.assertIn(column, list(ledger.columns))                                          # 1.6 欄名
        for _, name, _ in rec.downloads:
            self.assertNotRegex(name or "", re.compile("trace", re.I))

    def test_report_uses_the_same_names_as_the_page(self):
        with Recorder() as rec:
            at = self.start(m="2020-03")
        parts = rec.last_report()
        self.assertEqual(parts["title"], "借錢投資 ETF 壓力測試報告：00878.TW")                     # T-120
        groups = [group for group, _ in parts["summaries"]]
        self.assertEqual(groups[:3], ["貸款", "歷史回測", "蒙地卡羅模擬（2,000 次）"])            # T-121
        shown = {m.label: m.value for m in at.metric}
        reported = {label: value for _, rows in parts["summaries"] for label, value in rows}
        self.assertEqual(reported, shown, "SPEC 5：報告與畫面用同一套名稱與數字")
        settings = dict(parts["settings"])
        for label in ("每月最多自掏", "逐月明細的進場月份", "有開啟的情境與稅費", "蒙地卡羅模擬"):       # T-122..T-125
            self.assertIn(label, settings)
        tables = [heading for heading, _, _ in parts["tables"]]
        self.assertEqual(tables[:2], ["蒙地卡羅：期滿資產的分佈", "蒙地卡羅：自己掏了多少錢、換到多少報酬"])
        figures = [heading for heading, _, _ in parts["figures"]]
        for heading in ("歷史回測：每個月進場，期滿剩多少", "蒙地卡羅：資產隨時間的可能範圍",
                        "2020-03 進場：資產和貸款餘額", "2020-03 進場：每月貸款用哪些錢繳"):     # T-80..T-86
            self.assertIn(heading, figures)
        page = "\n".join(strip_markup(t) for _, t in visible_texts(at))
        for heading in tables + figures:                                                         # G-2
            self.assertIn(heading, page, "G-2：報告的圖表標題也要是畫面上的標題")

    def test_details_page_names(self):
        at, links = self.run_details_page()
        self.assertEqual(at.title[0].value, "🧮 計算方法說明")                                     # T-04
        self.assertTrue(links and all(label == "← 回到壓力測試" for label in links))                # T-05
        headers = [h.value for h in at.header] + [h.value for h in at.subheader]
        for expected in ("二、貸款每月要還多少？（對應側欄「貸款條件」）", "七、歷史回測和蒙地卡羅模擬有什麼不同？",
                         "十一、安全邊界怎麼算？"):                                               # T-130、T-133、T-140
            self.assertIn(expected, headers)
        page = "\n".join(t for _, t in visible_texts(at))
        self.assertIn(DCA_OK, page, "說明頁第八節仍以「定期定額（DCA）」介紹")


class OldLinkTests(AppHarness, unittest.TestCase):
    """SPEC 5、2：網址參數不改名，V39 的分享連結照常運作，數字和 V39 完全相同（不改計算）。"""

    def test_v39_links_restore_the_same_settings_and_results(self):
        for name, (query, expected) in OLD_LINKS.items():
            with self.subTest(name):
                at = self.start(**query)
                self.assertEqual(widget_snapshot(at), expected["widgets"], "各欄位的值應和 V39 相同")
                self.assertEqual([m.value for m in at.metric], expected["metrics"], "主要結果應和 V39 相同")
                got = {k: v[0] if isinstance(v, list) else v for k, v in at.query_params.items()}
                self.assertEqual(got, query, "網址列應保留原本的參數，也不多出新參數的預設值")

    def test_default_first_payment_is_unchanged(self):
        at = self.start()
        self.assertEqual(next(m.value for m in at.metric if m.label == "初期每月應繳"), "$67,199")


if __name__ == "__main__":
    unittest.main()
