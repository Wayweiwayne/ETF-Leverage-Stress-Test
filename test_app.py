"""End-to-end checks of the Streamlit pages with market data stubbed out (no network)."""
import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import market_data
from version import APP_VERSION

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
MORTGAGE, CREDIT = "理財型房貸 (長年期/可寬限)", "一般信貸 (短年期/無寬限)"
SOURCES = ["本薪(自掏腰包)", "配息資金池", "緩衝金", "變賣資產(主標的)", "變賣資產(第二標的)"]


def fake_history(ticker):
    """Deterministic daily prices; the 'L' ticker behaves like a 2x fund and pays nothing.

    OLD* reaches back to 2006, SEAM* carries an unadjusted 4-for-1 split, STALE* arrives from a snapshot.
    """
    rng = np.random.RandomState(sum(map(ord, ticker)))
    start = {'OLD': '2006-01-02', 'NEW': '2024-12-16'}.get(ticker[:3], '2016-01-04')
    days = pd.bdate_range(start, '2024-12-31')
    leverage = 2.0 if 'L' in ticker else 1.0
    close = 20 * np.cumprod(1 + rng.normal(0.0004 * leverage, 0.011 * leverage, len(days)))
    dividends = np.zeros(len(days))
    if leverage == 1.0:
        months = pd.Series(days.month, index=days)
        first_day = ~pd.Series(days.to_period('M'), index=days).duplicated()
        payout = (first_day & months.isin([2, 5, 8, 11])).to_numpy()
        dividends[payout] = close[payout] * 0.015
    if ticker.startswith('SEAM'):
        close[days < '2019-06-03'] *= 4
    df = pd.DataFrame({'Close': close, 'Dividends': dividends}, index=days.tz_localize('Asia/Taipei'))
    df.attrs.update(ticker=ticker, data_source='live', fetched_at='2024-12-31T10:00:00Z')
    if ticker.startswith('STALE'):
        df.attrs.update(data_source='snapshot', fetched_at='2024-11-05T10:00:00Z')
    return df


class AppTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        patcher = patch('market_data.MIRROR_URL', '')         # no network: no mirror, no index
        patcher.start()
        self.addCleanup(patcher.stop)
        market_data._index_cache.update(at=float("-inf"), entries=None)
        patcher = patch('market_data.load_history', side_effect=fake_history)
        self.load_history = patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, **query):
        at = AppTest.from_file(APP, default_timeout=120)
        for key, value in query.items():
            at.query_params[key] = value
        return self.ok(at.run())

    def ok(self, at):
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at

    def metric(self, at, label):
        return next(m.value for m in at.metric if m.label == label)

    def order(self, at):
        return [box.value for box in at.selectbox if box.key in ("p1", "p2", "p3", "p4", "p5")]

    def test_defaults_render_results(self):
        at = self.start()
        self.assertIn(f"({APP_VERSION})", at.title[0].value)
        self.assertEqual(len(at.error), 0)
        self.assertEqual(self.metric(at, "初期每月應繳"), "$67,199")
        self.assertIn("槓桿破產率 (現金流斷裂)", [m.label for m in at.metric])
        self.assertEqual(dict(at.query_params), {})

    def test_credit_loan_defaults_to_no_grace_and_mortgage_to_grace(self):
        at = self.start()
        self.assertEqual(at.radio(key="type").value, CREDIT)
        self.assertFalse(at.checkbox(key="grace").value)
        self.assertEqual(self.metric(at, "初期每月應繳"), self.metric(at, "寬限期後每月應繳"))

        self.ok(at.radio(key="type").set_value(MORTGAGE).run())
        self.assertTrue(at.checkbox(key="grace").value)
        self.assertEqual((at.slider(key="rate").value, at.slider(key="years").value), (2.5, 20))
        self.assertNotEqual(self.metric(at, "初期每月應繳"), self.metric(at, "寬限期後每月應繳"))

        self.ok(at.radio(key="type").set_value(CREDIT).run())
        self.assertFalse(at.checkbox(key="grace").value)
        self.assertEqual((at.slider(key="rate").value, at.slider(key="years").value), (3.5, 7))

    def test_grace_period_always_stays_shorter_than_the_loan(self):
        at = self.start(type="0")
        for years, expected_max in ((6, 5), (3, 2)):
            self.ok(at.slider(key="years").set_value(years).run())
            grace = at.slider(key="grace_y")
            self.assertEqual(grace.max, expected_max)
            self.assertLessEqual(grace.value, expected_max)
        # two years leaves a single possible grace length, one year leaves none
        self.ok(at.slider(key="years").set_value(2).run())
        self.assertNotEqual(self.metric(at, "初期每月應繳"), self.metric(at, "寬限期後每月應繳"))
        self.ok(at.slider(key="years").set_value(1).run())
        self.assertEqual(self.metric(at, "初期每月應繳"), self.metric(at, "寬限期後每月應繳"))

    def test_every_stress_scenario_runs_on_a_one_year_loan(self):
        at = self.start(years="1", shock="1", swan="1", jl="1", hc="1", buf="12")
        self.assertEqual(len(at.error), 0)
        self.ok(at.radio(key="jl_mode").set_value("隨機失業模型").run())
        self.assertEqual(len(at.error), 0)

    def test_repayment_sources_cannot_repeat(self):
        at = self.start()
        self.assertEqual(self.order(at), SOURCES)
        for slot in (1, 2, 3, 4):
            for source in at.selectbox(key=f"p{slot}").options:
                self.ok(at.selectbox(key=f"p{slot}").set_value(source).run())
                chosen = [s for s in self.order(at) if s != "（不使用）"]
                self.assertEqual(len(chosen), len(set(chosen)), self.order(at))

    def test_a_source_can_be_left_out(self):
        at = self.start(p1="3", p2="4", p3="4", p4="4", p5="4")
        self.assertEqual(self.order(at), ["變賣資產(主標的)"] + ["（不使用）"] * 4)
        self.assertIn("不會動用：本薪(自掏腰包)、配息資金池、緩衝金、變賣資產(第二標的)", [c.value for c in at.sidebar.caption])
        self.assertIn("第二標的沒有排進順位", self.texts(at.sidebar.caption))

    def test_second_asset_is_a_source_only_when_there_is_one(self):
        self.assertEqual(self.order(self.start()), SOURCES)
        self.assertNotIn("第二標的沒有排進順位", self.texts(self.start().sidebar.caption))
        for query in (dict(reinv="0"), dict(b="")):
            with self.subTest(query):
                at = self.start(**query)
                self.assertEqual(self.order(at), SOURCES[:4])
                self.assertNotIn("變賣資產(第二標的)", at.selectbox(key="p1").options)

    def test_links_made_before_the_second_asset_was_a_source_still_mean_the_same(self):
        # "4" has always meant "not used"; the new source takes the next number.
        at = self.start(p1="3", p2="0", p3="4", p4="4", p5="5")
        self.assertEqual(self.order(at), ["變賣資產(主標的)", "本薪(自掏腰包)", "（不使用）", "（不使用）", "變賣資產(第二標的)"])

    def test_selling_the_second_asset_shows_in_the_ledger(self):
        at = self.start(salary="0", p1="5", p2="3", p3="4", p4="4", p5="4", seed="1")
        ledger = at.dataframe[0].value
        self.assertGreater(ledger['變賣主資產'].sum(), 0)
        self.assertIn('變賣第二標的', ledger.columns)
        paid = ledger[['來自配息資金池', '來自緩衝金', '變賣主資產', '變賣第二標的', '本薪(自掏腰包)']].sum(axis=1)
        np.testing.assert_allclose(paid[~ledger['破產(斷頭)']], ledger['每月應繳本息'][~ledger['破產(斷頭)']])

    def test_no_source_at_all_warns(self):
        at = self.start(p1="4", p2="4", p3="4", p4="4", p5="4")
        self.assertTrue(any("第一個月就會破產" in w.value for w in at.sidebar.warning))
        self.assertEqual(self.metric(at, "槓桿破產率 (現金流斷裂)"), "100.0%")

    def test_settings_are_restored_from_a_link(self):
        at = self.start(loan="800", type="0", years="15", grace_y="2", a="0056.TW", reinv="0", salary="40000",
                        swan="1", swan_m="24", swan_d="30", jl="1", jl_mode="1", jl_extra="5~20", paths="1",
                        scen="3", path="3, -15, 8", dca="1", m="2020-03")
        self.assertEqual(at.number_input(key="loan").value, 800)
        self.assertEqual(at.radio(key="type").value, MORTGAGE)
        self.assertEqual((at.slider(key="years").value, at.slider(key="grace_y").value), (15, 2))
        self.assertEqual(at.text_input(key="a").value, "0056.TW")
        self.assertFalse(at.checkbox(key="reinv").value)
        self.assertEqual(at.number_input(key="salary").value, 40000)
        self.assertEqual((at.slider(key="swan_m").value, at.slider(key="swan_d").value), (24, 30))
        self.assertEqual(at.slider(key="jl_extra").value, (5.0, 20.0))
        self.assertEqual(at.selectbox(key="paths").value, 5000)
        self.assertEqual(at.text_input(key="path").value, "3, -15, 8")
        self.assertEqual(at.selectbox(key="m").value, "2020-03")
        self.assertEqual(len(at.error), 0)
        # the address keeps describing the same settings
        self.assertEqual(at.query_params["loan"], ["800"])
        self.assertEqual(at.query_params["m"], ["2020-03"])

    def test_bad_link_values_fall_back_to_safe_ones(self):
        at = self.start(loan="-5", rate="abc", years="999", a="<script>alert(1)</script>", paths="99",
                        grace="yes", p1="banana", jl_extra="oops", m="1999-01", fee="1e9")
        self.assertEqual(at.number_input(key="loan").value, 1)
        self.assertEqual(at.slider(key="rate").value, 3.5)
        self.assertEqual(at.slider(key="years").value, 30)
        self.assertEqual(at.text_input(key="a").value, "00878.TW")
        self.assertEqual(at.selectbox(key="paths").value, 2000)
        self.assertFalse(at.checkbox(key="grace").value)
        self.assertEqual(self.order(at), SOURCES)
        self.assertEqual(at.number_input(key="fee").value, 5.0)
        self.assertEqual(at.selectbox(key="m").value, "2022-01")

    def test_address_follows_changes_and_drops_defaults(self):
        at = self.start()
        self.ok(at.number_input(key="loan").set_value(300).run())
        self.ok(at.checkbox(key="swan").check().run())
        self.assertEqual(dict(at.query_params), {"loan": ["300"], "swan": ["1"]})
        self.ok(at.number_input(key="loan").set_value(500).run())
        self.assertEqual(dict(at.query_params), {"swan": ["1"]})

    def test_black_swan_shows_once_in_the_ledger(self):
        # A fund that pays nothing, salary covering every payment: value is shares times price, nothing else.
        common = dict(a="00631L.TW", reinv="0", salary="1000000", fee="0", seed="1")
        ledger = self.start(swan="1", swan_m="12", swan_d="40", **common).dataframe[0].value
        before, after = ledger['總資產淨值(槓桿)'].iloc[10], ledger['總資產淨值(槓桿)'].iloc[11]
        plain = self.start(**common).dataframe[0].value
        natural = plain['總資產淨值(槓桿)'].iloc[11] / plain['總資產淨值(槓桿)'].iloc[10] - 1
        self.assertAlmostEqual(after / before - 1, natural - 0.40, places=6)

    def test_invalid_custom_path_is_reported_not_guessed(self):
        at = self.start(scen="3")
        self.ok(at.text_input(key="path").set_value("5, ten, 3").run())
        self.assertTrue(any("參數有誤" in e.value for e in at.error))
        self.assertEqual(len(at.metric), 0)

    def test_invalid_ticker_never_reaches_the_data_source(self):
        at = self.start()
        self.load_history.reset_mock()
        self.ok(at.text_input(key="a").set_value("../etc").run())
        self.assertTrue(any("格式不正確" in e.value for e in at.error))
        self.load_history.assert_not_called()

    def texts(self, elements):
        return " ".join(e.value for e in elements)

    def test_history_is_extended_with_the_proxy(self):
        at = self.start()
        self.assertEqual(at.selectbox(key="m").options[0], "2016-02")
        self.assertIn("替身 0056.TW 的歷史沒有比 00878.TW 更早", self.texts(at.caption))
        self.assertIn("可用的歷史只有 107 個月", self.texts(at.warning))

        at = self.start(proxy="OLD.TW")
        self.assertEqual(at.selectbox(key="m").options[0], "2006-02")
        self.assertIn("以 OLD.TW 當時的實際漲跌與配息代替", self.texts(at.caption))
        self.assertIn("120 個起點用到了替身 OLD.TW 的歷史", self.texts(at.caption))
        self.assertIn("00631L.TW 在 2016-02 之前沒有資料，這 120 個月用", self.texts(at.caption))
        self.assertNotIn("可用的歷史只有", self.texts(at.warning))
        self.assertEqual(len(at.error), 0)

    def test_blank_proxy_uses_only_the_assets_own_history(self):
        at = self.start(proxy="")
        self.assertEqual(at.selectbox(key="m").options[0], "2016-02")
        self.assertNotIn("替身", self.texts(at.caption))

    def test_unusable_proxy_is_reported_and_ignored(self):
        at = self.start()
        self.ok(at.text_input(key="proxy").set_value("no good").run())
        self.assertIn("替身 NO GOOD 的資料無法使用", self.texts(at.warning))
        self.assertIn("槓桿破產率 (現金流斷裂)", [m.label for m in at.metric])

    def test_unadjusted_split_is_repaired_and_announced(self):
        at = self.start(a="SEAM.TW", seed="1")
        self.assertIn("1 股拆成 4 股", self.texts(at.info))
        self.assertNotIn("不尋常", self.texts(at.warning))
        repaired = self.metric(at, "槓桿期滿中位數 (存活者)")

        at = self.start(a="SEAM.TW", seed="1", fix="0")
        self.assertNotIn("1 股拆成 4 股", self.texts(at.info))
        self.assertIn("2019-06-03 單日 -7", self.texts(at.warning))
        self.assertNotEqual(self.metric(at, "槓桿期滿中位數 (存活者)"), repaired)

    def built_report(self, **query):
        import report
        with patch('report.build_report', wraps=report.build_report) as spy:
            at = self.start(**query)
        self.assertEqual(spy.call_count, 1)
        return at, spy.call_args.kwargs, report.build_report(**spy.call_args.kwargs)

    def test_report_gathers_what_the_page_shows(self):
        at, parts, html = self.built_report(salary="15000", swan="1", swan_m="18", swan_d="35", seed="1", m="2020-03")
        settings = dict(parts["settings"])
        self.assertIn("500 萬元｜一般信貸", settings["貸款"])
        self.assertIn("無寬限期", settings["貸款"])
        self.assertEqual(settings["第一標的"], "00878.TW")
        self.assertEqual(settings["每月最多自掏"], "$15,000")
        self.assertIn("黑天鵝(第18月 -35%)", settings["已啟用的情境與稅費"])
        self.assertEqual(settings["逐月追蹤的進場月份"], "2020-03")
        # every number on the page is in the report, under the same name
        shown = {m.label: m.value for m in at.metric}
        reported = {label: value for _, rows in parts["summaries"] for label, value in rows}
        self.assertEqual(reported, shown)
        self.assertEqual([heading for heading, _, _ in parts["tables"]],
                         ["蒙地卡羅：期滿淨值的分佈", "蒙地卡羅：自己掏了多少錢、換到多少報酬"])
        headings = [heading for heading, _, _ in parts["figures"]]
        self.assertEqual(headings[:2], ["歷史上每個月進場的期滿淨值（槓桿策略）", "蒙地卡羅：資產隨時間的可能範圍"])
        self.assertIn("逐月追蹤：2020-03 進場的資產與貸款", headings)
        self.assertTrue(any("來源價格期間" in note for note in parts["data_notes"]))
        self.assertTrue(any("可用的歷史只有" in text for text in parts["warnings"]))
        self.assertIn("ETF 槓桿壓力測試報告：00878.TW", html)
        self.assertIn(f"版本 {APP_VERSION}", html)
        self.assertGreater(len(html), 20_000)

    def test_report_lists_data_repairs_and_stale_data(self):
        _, parts, _ = self.built_report(a="SEAM.TW")
        self.assertTrue(any("SEAM.TW 已自動修正" in note and "1 股拆成 4 股" in note for note in parts["data_notes"]))
        _, parts, _ = self.built_report(a="STALE.TW")
        self.assertTrue(any("目前使用 2024-11-05 存檔的資料" in text for text in parts["warnings"]))

    def test_no_report_when_there_are_no_results(self):
        import report
        self.load_history.side_effect = ValueError("暫時無法取得資料")
        with patch('report.build_report', wraps=report.build_report) as spy:
            self.start()
        spy.assert_not_called()

    def test_standalone_notice_appears_only_without_a_live_source(self):
        self.assertNotIn("這是單機版", self.texts(self.start().info))
        index = {f"00{n:03d}.TW": {"name": f"ETF {n}", "listed": "2020-01-01"} for n in range(247)}
        with patch('market_data.yf', None), patch('market_data.mirror_index', return_value=index), \
                patch('market_data._listed_extras', return_value=set()):
            at = self.start()
        self.assertIn("可以使用所有台灣上市的 ETF（目前 247 檔", self.texts(at.info))

    def test_earliest_entry_month_is_explained_without_a_proxy(self):
        index = {"00878.TW": {"name": "國泰永續高股息", "listed": "2016-01-04"}}
        with patch('market_data.mirror_index', return_value=index):
            at = self.start(proxy="")
        captions = self.texts(at.caption)
        self.assertIn("📅 最早只能從 2016-02 進場：00878.TW 的第一筆價格在 2016-01-04", captions)
        self.assertIn("（證交所公告的上市日是 2016-01-04）", captions)
        self.assertIn("指定一檔上市更久的 ETF，用它的舊資料補上", captions)

    def test_just_listed_etf_needs_a_proxy_or_has_to_wait(self):
        alone = self.start(a="NEW.TW", proxy="")
        self.assertEqual(len(alone.metric), 0)
        self.assertIn("NEW.TW 的第一筆價格在 2024-12-16，目前只有一個月份的價格", self.texts(alone.error))
        self.assertIn("最早要等到 2025-01 有了第二筆月價才能進場", self.texts(alone.error))

        helped = self.start(a="NEW.TW", proxy="OLD.TW")
        self.assertEqual(len(helped.error), 0)
        self.assertIn("槓桿破產率 (現金流斷裂)", [m.label for m in helped.metric])
        self.assertIn("📅 最早可以從 2006-02 進場：NEW.TW 的第一筆價格在 2024-12-16", self.texts(helped.caption))

    def test_earliest_entry_month_is_explained_with_a_proxy(self):
        captions = self.texts(self.start(proxy="OLD.TW").caption)
        self.assertIn("📅 最早可以從 2006-02 進場：00878.TW 的第一筆價格在 2016-01-04，"
                      "在那之前的 120 個月，用替身 OLD.TW 當時的實際漲跌與配息補上。", captions)
        self.assertNotIn("證交所公告的上市日", captions)                 # no index available in tests

    def test_data_origin_and_download_date_are_shown(self):
        captions = self.texts(self.start().caption)
        self.assertIn("資料取得時間 2024-12-31（剛從 Yahoo Finance 取得）", captions)
        self.assertIn("資料取得時間 2024-11-05（較舊的存檔）", self.texts(self.start(a="STALE.TW").caption))

    def test_reload_button_asks_for_live_data_for_every_ticker_in_use(self):
        at = self.start(proxy="OLD.TW")
        with patch('market_data.request_live') as request_live:
            self.ok(at.sidebar.button[0].click().run())
        self.assertEqual(sorted(call.args[0] for call in request_live.call_args_list),
                         ["00631L.TW", "00878.TW", "OLD.TW"])
        self.assertIn("槓桿破產率 (現金流斷裂)", [m.label for m in at.metric])

    def test_snapshot_data_is_flagged_with_its_date(self):
        at = self.start(a="STALE.TW")
        self.assertIn("STALE.TW：即時行情暫時無法取得，目前使用 2024-11-05 存檔的資料", self.texts(at.warning))
        self.assertNotIn("存檔的資料", self.texts(self.start().warning))

    def test_entry_month_changes_the_ledger_but_not_the_statistics(self):
        at = self.start(seed="1")
        metrics = [(m.label, m.value) for m in at.metric]
        ledger = at.dataframe[0].value
        self.assertEqual(ledger['真實/預測月份'].iloc[0], "2022-02")     # entered 2022-01, first payment a month later
        self.ok(at.selectbox(key="m").set_value("2019-05").run())
        self.assertEqual([(m.label, m.value) for m in at.metric], metrics)
        self.assertEqual(at.dataframe[0].value['真實/預測月份'].iloc[0], "2019-06")
        self.assertFalse(at.dataframe[0].value['總資產淨值(槓桿)'].equals(ledger['總資產淨值(槓桿)']))

    def test_random_job_loss_reports_averaged_history(self):
        at = self.start(jl="1", jl_mode="1", jl_prob="20")
        self.assertIn("每個起點各模擬 93 種失業時點", self.texts(at.caption))
        self.assertEqual(len(at.error), 0)

    def test_same_settings_give_the_same_monte_carlo_by_default(self):
        first = [(m.label, m.value) for m in self.start().metric]
        st.cache_data.clear()
        self.assertEqual([(m.label, m.value) for m in self.start().metric], first)
        self.assertTrue(self.start().checkbox(key="seed").value)

    def test_result_is_put_in_plain_words_with_its_sampling_error(self):
        safe = self.start()
        self.assertIn("沒有任何一種繳不出貸款", self.texts(safe.markdown))
        risky = self.start(salary="0", swan="1", swan_m="6", swan_d="40")
        self.assertRegex(self.texts(risky.markdown), r"大約每 \d+ 種可能的未來，就有 1 種會在中途繳不出貸款")
        self.assertRegex(self.texts(risky.caption), r"抽樣誤差約 ±\d+\.\d 個百分點")
        self.assertIn("把破產的也算進去（以 0 計）", self.texts(risky.caption))

    def test_distribution_table_and_ruin_timing(self):
        risky = self.start(salary="0", swan="1", swan_m="6", swan_d="40")
        table = risky.table[0].value
        self.assertEqual(list(table.index), ["最差的 5%", "偏差的 25%", "中位數", "偏好的 25%", "最好的 5%"])
        self.assertEqual(list(table.columns), ["槓桿策略（破產以 0 計）", "定期定額對照組"])
        self.assertIn("次破產的模擬裡，有一半發生在第", self.texts(risky.caption))
        self.assertNotIn("次破產的模擬裡", self.texts(self.start().caption))

    def test_out_of_pocket_and_annual_return_table(self):
        at = self.start(seed="1")
        table = at.table[1].value
        self.assertEqual(list(table.columns), ["槓桿策略", "定期定額對照組"])
        self.assertEqual(table.index[0], "整段期間自掏腰包的總額（中位數）")
        self.assertEqual(table.iloc[0, 0], "$2,100,000")                # 25,000 a month for 84 months
        self.assertEqual(table.iloc[0, 1], "$2,100,000")                # the comparison puts in the same
        self.assertRegex(table.iloc[2, 0], r"^[+-]\d+\.\d%$")

        nothing_paid = self.start(seed="1", p1="3", p2="4", p3="4", p4="4", p5="4")    # sell assets only
        self.assertEqual(nothing_paid.table[1].value.iloc[2, 0], "不適用")

    def test_range_over_time_is_explained(self):
        self.assertIn("色帶是槓桿策略手上資產的總值", self.texts(self.start().caption))
        risky = self.start(salary="0", swan="1", swan_m="6", swan_d="40")
        self.assertIn("資產已經不夠還清貸款", self.texts(risky.caption))

    def test_dividend_assumption_is_checked_against_the_record(self):
        self.assertNotIn("未來平均一年發多少股息", self.texts(self.start().warning))       # fixture pays about 6%
        self.assertIn("實際平均約", self.texts(self.start(div="12").warning))
        self.assertIn("沒有任何配息", self.texts(self.start(a="00631L.TW").warning))
        self.assertNotIn("沒有任何配息", self.texts(self.start(a="00631L.TW", div="0").warning))

    def test_monte_carlo_uses_recorded_dividends_unless_told_otherwise(self):
        mc_labels = ["槓桿破產率 (現金流斷裂)", "槓桿擊敗 DCA 勝率"]

        def mc_metrics(at):
            values = [m.value for m in at.metric]
            return values[-4:]                                  # the Monte Carlo column comes last

        default = self.start()
        self.assertIn("配息跟著報酬一起從歷史重抽", self.texts(default.caption))
        self.assertTrue(all(label in [m.label for m in default.metric] for label in mc_labels))
        self.assertEqual(mc_metrics(self.start(div="12")), mc_metrics(default))          # the slider is not involved

        assumed = self.start(mcdiv="1")
        self.assertIn("配息照你設定的「未來平均股息」計算", self.texts(assumed.caption))
        self.assertNotEqual(mc_metrics(self.start(mcdiv="1", div="12")), mc_metrics(assumed))

    def test_dividend_warning_says_what_the_assumed_yield_affects(self):
        self.assertIn("歷史資料用完之後的未來情境，配息是照你設的數字算的", self.texts(self.start(div="12").warning))
        self.assertIn("蒙地卡羅和歷史資料用完之後的未來情境，配息是照你設的數字算的",
                      self.texts(self.start(div="12", mcdiv="1").warning))

    def flags(self, at):
        return next((c.value for c in at.caption if c.value.startswith("🟢 已啟用情境")), "")

    def ledger_tax(self, at):
        return at.dataframe[0].value['配息被扣的稅費'].sum()

    def test_taiwan_taxes_apply_by_default_and_can_be_switched_off(self):
        default = self.start(seed="1")
        self.assertIn("稅費(證交稅0.1%、補充保費2.11%、股利所得稅3.5%)", self.flags(default))
        self.assertGreater(self.ledger_tax(default), 0)

        untaxed = self.start(seed="1", stax="0", nhi="0", itax="0")
        self.assertNotIn("稅費", self.flags(untaxed))
        self.assertEqual(self.ledger_tax(untaxed), 0)
        median = lambda at: int(self.metric(at, "DCA 定期定額 期滿中位數").replace("$", "").replace(",", ""))
        self.assertGreater(median(untaxed), median(default))

    def test_tax_bracket_sets_the_dividend_tax(self):
        self.assertIn("股利所得稅28%", self.flags(self.start(itax="5")))
        low = self.flags(self.start(itax="1"))
        self.assertNotIn("股利所得稅", low)
        self.assertIn("補充保費2.11%", low)
        self.assertIn("配息的40%算股利所得", self.flags(self.start(dshare="40")))
        self.assertIn("開辦費$6,000", self.flags(self.start(lfee="6000")))
        self.assertEqual(self.start(itax="99").selectbox(key="itax").value, "12%")       # nonsense in a link

    def test_floating_rate_path_and_random_moves(self):
        fixed = self.start()
        self.assertNotIn("浮動利率", self.flags(fixed))
        self.assertNotIn("月付金最高會到", self.texts(fixed.caption))

        floating = self.start(**{"float": "1"})
        self.assertIn("浮動利率(第2年起每年 +0.25、+0.25、+0.125 個百分點，蒙地卡羅每年隨機 ±0.25)", self.flags(floating))
        self.assertIn("月付金最高會到", self.texts(floating.caption))
        self.assertIn("九成的路徑年利率落在", self.texts(floating.caption))
        self.assertIn("不含隨機升降息", self.texts(floating.caption))
        self.assertEqual(self.metric(floating, "初期每月應繳"), self.metric(fixed, "初期每月應繳"))
        rates = floating.dataframe[0].value['當期年利率(%)']
        np.testing.assert_allclose(rates.iloc[[0, 12, 24, 36, 83]], [3.5, 3.75, 4.0, 4.125, 4.125])

        steady = self.start(**{"float": "1", "rvol": "0", "rpath": "-0.5"})
        self.assertNotIn("九成的路徑年利率落在", self.texts(steady.caption))
        self.assertNotIn("月付金最高會到", self.texts(steady.caption))               # a cut never raises the payment

    def test_invalid_rate_path_is_reported(self):
        at = self.start(**{"float": "1"})
        self.ok(at.text_input(key="rpath").set_value("0.25, up").run())
        self.assertTrue(any("浮動利率路徑" in e.value for e in at.error))
        self.assertEqual(len(at.metric), 0)

    def test_dividend_frequency_follows_the_record_unless_chosen(self):
        self.assertIn("每季發一次，依這檔標的最近三年的紀錄判斷", self.texts(self.start().caption))
        yearly = self.texts(self.start(dfreq="4").caption)
        self.assertIn("每年發一次。", yearly)
        self.assertNotIn("依這檔標的最近三年的紀錄判斷", yearly)

    def test_empty_dividend_pool_is_pointed_out_when_dividends_are_reinvested(self):
        self.assertIn("配息資金池不會有錢", self.texts(self.start().sidebar.caption))
        self.assertNotIn("配息資金池不會有錢", self.texts(self.start(reinv="0").sidebar.caption))

    def test_disclaimer_is_shown_even_when_data_fails(self):
        self.assertIn("不構成任何投資建議", self.texts(self.start().caption))
        self.assertIn("AGPL-3.0", self.texts(self.start().caption))
        self.assertIn("github.com/Wayweiwayne/ETF-Leverage-Stress-Test", self.texts(self.start().caption))
        self.load_history.side_effect = ValueError("暫時無法取得資料")
        self.assertIn("不構成任何投資建議", self.texts(self.start().caption))

    def test_data_failure_is_shown_as_a_message(self):
        self.load_history.side_effect = ValueError("暫時無法取得資料")
        at = self.start()
        self.assertTrue(any("暫時無法取得資料" in e.value for e in at.error))

    def test_blank_second_ticker_reinvests_everything_in_the_first(self):
        at = self.start()
        self.ok(at.text_input(key="b").set_value("").run())
        self.assertEqual(len(at.error), 0)
        self.assertEqual(at.dataframe[0].value['再投入資產股數'].abs().sum(), 0)


if __name__ == '__main__':
    unittest.main()
