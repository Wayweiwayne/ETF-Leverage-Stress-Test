"""衝刺 2「使用者回饋修正輪」（F1～F5）的驗收測試。

F1 說明頁第一節的用語；F2 沒有時區資料庫時也能產生報告；F3 使用者看不到程式碼或 traceback；
F4 「把這次的結果存下來」改成下載按鈕；F5 「一開始預留幾個月的還款現金」移到「1. 貸款條件」。
全部離線（假行情）。
"""
import glob
import os
import re
import sys
import tomllib
import unittest
import zoneinfo
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from test_acceptance_helpers import (APP, DETAILS_PAGE, HERE, AppHarness, Recorder, strip_markup,
                                     visible_texts)
from test_app import fake_history

SAVE_LABEL = "📄 把這次的結果存下來"
OLD_SAVE_LABEL = "📄 下載這次的報告 (HTML)"
TAIPEI = timezone(timedelta(hours=8))


@contextmanager
def no_time_zone_database():
    """模擬單機版（Pyodide）沒有 tzdata：系統時區目錄與 tzdata 套件都找不到，ZoneInfo("Asia/Taipei") 會失敗。"""
    saved = zoneinfo.TZPATH
    with patch.dict(sys.modules, {"tzdata": None}):
        zoneinfo.reset_tzpath(to=[])
        zoneinfo.ZoneInfo.clear_cache()
        try:
            yield
        finally:
            zoneinfo.reset_tzpath(to=list(saved))
            zoneinfo.ZoneInfo.clear_cache()


def walk(node, out):
    out.append(node)
    for child in getattr(node, "children", {}).values():
        walk(child, out)
    return out


def app_sources():
    """App 的程式碼（不含測試）。"""
    files = [f for f in glob.glob(os.path.join(HERE, "*.py")) if not os.path.basename(f).startswith("test_")]
    return files + glob.glob(os.path.join(HERE, "pages", "*.py"))


class DetailsPageWordingTests(unittest.TestCase):
    """F1：說明頁第一節。"""

    def run_page(self):
        with patch("streamlit.page_link"):
            at = AppTest.from_file(os.path.join(HERE, DETAILS_PAGE), default_timeout=60).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at

    def test_section_one_wording(self):
        at = self.run_page()
        texts = [strip_markup(t).replace("**", "") for _, t in visible_texts(at)]
        page = "\n".join(texts)
        for gone in ("吸收邊界", "後面就算市場大漲也跟你無關了", "白話總結"):
            self.assertNotIn(gone, page)
        ruin = [t for t in texts if "湊不出錢繳貸款" in t]
        self.assertEqual(len(ruin), 1, "測試前提：第一節說明破產的那一段")
        self.assertTrue(ruin[0].rstrip().endswith("這個策略就判定破產。"), ruin[0])
        self.assertTrue(any(t.startswith("白話：") for t in texts), "「白話總結」改成「白話」")


class TimeZoneTests(AppHarness, unittest.TestCase):
    """F2：沒有 tzdata 時整個 App 跑完、報告照常產生，時間仍是台北時間（UTC+8）。"""

    def setUp(self):
        super().setUp()
        cache = {}

        def history(ticker):  # 假行情本身要用時區，所以先在有時區資料庫時做好
            if ticker not in cache:
                cache[ticker] = fake_history(ticker)
            return cache[ticker].copy()

        for ticker in ("00878.TW", "00631L.TW", "0056.TW"):
            history(ticker)
        patcher = patch("market_data.load_history", side_effect=history)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_simulation_really_has_no_taipei_zone(self):
        with no_time_zone_database():
            with self.assertRaises(zoneinfo.ZoneInfoNotFoundError):
                pd.Timestamp.now(tz="Asia/Taipei")

    def test_report_is_built_without_a_time_zone_database(self):
        with Recorder() as rec, no_time_zone_database():
            before = datetime.now(TAIPEI)
            at = AppTest.from_file(APP, default_timeout=180).run()
            after = datetime.now(TAIPEI)
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertEqual(len(at.error), 0, [e.value for e in at.error])
        self.assertEqual(len(rec.reports), 1, "報告應照常產生")
        generated = rec.last_report()["generated"]
        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", generated)
        self.assertIsNotNone(match, generated)
        stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)
        self.assertLessEqual(before.replace(second=0, microsecond=0), stamp, "產生時間應是台北時間（UTC+8）")
        self.assertLessEqual(stamp, after)
        self.assertIn("台北時間", generated)
        names = [name for label, name, _ in rec.downloads if label == SAVE_LABEL]
        self.assertEqual(names, [f"stress_test_00878.TW_{after:%Y%m%d}.html"], "檔名的日期也是台北日期")

    def test_code_no_longer_asks_for_the_taipei_zone_by_name(self):
        pattern = re.compile(r"""tz\s*=\s*["']Asia/Taipei["']""")
        found = []
        for path in app_sources():
            with open(path, encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    if pattern.search(line):
                        found.append(f"{os.path.relpath(path, HERE)}:{number}: {line.strip()}")
        self.assertEqual(found, [])


class ErrorDetailTests(AppHarness, unittest.TestCase):
    """F3：使用者看不到程式碼或 traceback。"""

    def test_server_config_hides_error_details(self):
        path = os.path.join(HERE, ".streamlit", "config.toml")
        self.assertTrue(os.path.exists(path), ".streamlit/config.toml 應存在")
        with open(path, "rb") as f:
            config = tomllib.load(f)
        self.assertEqual(config.get("client", {}).get("showErrorDetails"), "none")

    def test_standalone_mount_hides_error_details(self):
        with open(os.path.join(HERE, "dist", "ETF-Leverage-Stress-Test.html"), encoding="utf-8") as f:
            html = f.read()
        mount = html[html.index("mount("):]
        self.assertRegex(mount, r"""["']?(client\.)?showErrorDetails["']?\s*:\s*["']none["']""")

    def test_report_failure_is_one_plain_sentence(self):
        normal = [(m.label, m.value) for m in self.start().metric]
        with patch("report.build_report", side_effect=RuntimeError("boom-詳細內部錯誤")):
            with Recorder() as rec:
                at = AppTest.from_file(APP, default_timeout=180).run()
        self.assertEqual([str(e.value) for e in at.exception], [], "不可出現例外與 traceback")
        shown = [e.value for e in list(at.error) + list(at.warning) if "報告" in e.value]
        self.assertEqual(len(shown), 1, "畫面只顯示一句白話錯誤")
        for leak in ("boom", "RuntimeError", "Traceback", "詳細內部錯誤", 'File "'):
            self.assertNotIn(leak, shown[0])
        self.assertEqual([(m.label, m.value) for m in at.metric], normal, "其他結果照常顯示")
        labels = [label for label, _, _ in rec.downloads]
        self.assertNotIn(SAVE_LABEL, labels)
        self.assertIn("📥 下載歷史回測結果 (CSV)", labels)


class SaveButtonTests(AppHarness, unittest.TestCase):
    """F4：「把這次的結果存下來」是一個 primary 的下載按鈕，下面有一句說明。"""

    def test_save_is_a_primary_download_button(self):
        with Recorder() as rec:
            at = self.start()
        main = walk(at.main, [])
        self.assertFalse(any(getattr(n, "type", "") == "markdown" and "把這次的結果存下來" in n.value for n in main),
                         "不再是小標題")
        buttons = [n for n in main if getattr(n, "type", "") == "download_button" and n.proto.label == SAVE_LABEL]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].proto.type, "primary")
        self.assertNotIn(OLD_SAVE_LABEL, [label for label, _, _ in rec.downloads])

        saved = [(name, data) for label, name, data in rec.downloads if label == SAVE_LABEL]
        self.assertEqual(len(saved), 1)
        name, data = saved[0]
        self.assertRegex(name, r"^stress_test_00878\.TW_\d{8}\.html$", "檔名規則不變")
        html = data.decode("utf-8") if isinstance(data, bytes) else data
        self.assertIn("借錢投資 ETF 壓力測試報告：00878.TW", html)
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"), "按下會下載報告本身")

        index = main.index(buttons[0])
        following = [n for n in main[index + 1:] if getattr(n, "type", "") in ("caption", "markdown", "info")]
        self.assertTrue(following and following[0].type == "caption" and following[0].value.strip(),
                        "按鈕下方有一句說明")


class BufferPlacementTests(AppHarness, unittest.TestCase):
    """F5：「一開始預留幾個月的還款現金」在「貸款本金 (萬)」正下方、「2.」區段之前；buf 參數照常運作。"""

    def test_buffer_months_sit_right_below_the_principal(self):
        at = self.start()
        nodes = walk(at.sidebar, [])
        headers = [(i, n.value) for i, n in enumerate(nodes) if getattr(n, "type", "") == "header"]
        widgets = [(i, n) for i, n in enumerate(nodes) if getattr(n, "key", None)]
        first = next(i for i, text in headers if text == "1. 貸款條件")
        second = next(i for i, text in headers if text.startswith("2."))
        keys = [n.key for _, n in widgets]
        loan_at = keys.index("loan")
        self.assertEqual(keys[loan_at + 1], "buf", f"貸款本金之後的下一個欄位應是 buf，實際：{keys[loan_at:loan_at + 3]}")
        buf_index = widgets[loan_at + 1][0]
        self.assertTrue(first < widgets[loan_at][0] < buf_index < second)
        self.assertEqual(widgets[loan_at + 1][1].label, "一開始預留幾個月的還款現金")

    def test_old_link_with_buf_keeps_its_value_and_result(self):
        at = self.start(buf="3")
        self.assertEqual(at.slider(key="buf").value, 3)
        metrics = {m.label: m.value for m in at.metric}
        self.assertEqual(metrics["初期每月應繳"], "$67,199")
        self.assertEqual(metrics["開局預留的緩衝金"], f"${3 * 67_199:,}")   # V39：預留 3 個月的還款
        got = {k: v[0] if isinstance(v, list) else v for k, v in at.query_params.items()}
        self.assertEqual(got, {"buf": "3"})


if __name__ == "__main__":
    unittest.main()
