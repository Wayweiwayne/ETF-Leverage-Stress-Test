import unittest

import pandas as pd
import plotly.express as px

from report import build_report


def sample(**overrides):
    figure = px.line(pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}), x="x", y="y")
    kwargs = dict(
        title="ETF 槓桿壓力測試報告：0056.TW", version="V99", generated="2026-01-02 03:04（台北時間）",
        share_url="https://example.app/?a=0056.TW&salary=15000",
        settings=[("貸款", "500 萬元｜年利率 3.5%"), ("第一標的", "0056.TW")],
        data_notes=["0056.TW：來源價格期間 2008-01-02 至 2026-01-02。"],
        warnings=["⚠️ 可用的歷史只有 76 個月"],
        summaries=[("歷史滾動", [("槓桿破產率", "1.5%")]), ("蒙地卡羅", [("槓桿破產率", "2.6%")])],
        tables=[("期滿淨值的分佈", pd.DataFrame({"槓桿策略": ["$0", "$5,080,000"]}, index=["最差的 5%", "中位數"]), "說明文字")],
        figures=[("第一張圖", figure, "圖說"), ("第二張圖", figure, "")],
        disclaimer="不構成任何投資建議。", source_url="https://github.com/someone/project")
    kwargs.update(overrides)
    return build_report(**kwargs)


class ReportTests(unittest.TestCase):
    def test_document_contains_every_part_it_was_given(self):
        html = sample()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertTrue(html.endswith("</html>"))
        for text in ("ETF 槓桿壓力測試報告：0056.TW", "版本 V99", "2026-01-02 03:04", "500 萬元｜年利率 3.5%",
                     "歷史滾動", "蒙地卡羅", "1.5%", "2.6%", "可用的歷史只有 76 個月", "期滿淨值的分佈", "$5,080,000",
                     "最差的 5%", "說明文字", "第一張圖", "第二張圖", "圖說", "來源價格期間 2008-01-02",
                     "不構成任何投資建議。", "AGPL-3.0", "https://github.com/someone/project"):
            self.assertIn(text, html)
        self.assertIn("<meta charset='utf-8'>", html)

    def test_share_link_is_a_working_anchor(self):
        html = sample()
        self.assertIn("href='https://example.app/?a=0056.TW&amp;salary=15000'", html)
        self.assertNotIn("重現同一組設定", sample(share_url=""))

    def test_plotting_library_is_loaded_once(self):
        html = sample()
        self.assertEqual(html.count("cdn.plot.ly"), 1)
        self.assertEqual(html.count("Plotly.newPlot"), 2)

    def test_without_charts_nothing_is_fetched_from_the_network(self):
        html = sample(figures=[])
        self.assertNotIn("cdn.plot.ly", html)
        self.assertNotIn("<h2>圖表</h2>", html)

    def test_text_from_the_user_or_the_data_cannot_inject_markup(self):
        evil = "<script>alert(1)</script>"
        html = sample(title=evil, settings=[(evil, evil)], data_notes=[evil], warnings=[evil],
                      summaries=[(evil, [(evil, evil)])], share_url="https://x/?q='><script>alert(2)</script>",
                      tables=[(evil, pd.DataFrame({evil: [evil]}, index=[evil]), evil)], figures=[], disclaimer=evil,
                      source_url="https://x/'><script>alert(3)</script>")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("'><script>", html)

    def test_optional_sections_can_be_empty(self):
        html = sample(data_notes=[], warnings=[], tables=[], figures=[])
        self.assertNotIn("<h2>使用的資料</h2>", html)
        self.assertNotIn("class='warn'", html)
        self.assertIn("<h2>主要結果</h2>", html)


if __name__ == '__main__':
    unittest.main()
