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
MORTGAGE, CREDIT = "理財型房貸（年限長，可設寬限期）", "一般信貸（年限短，通常無寬限期）"
SOURCES = ["薪水（自掏腰包）", "存下來的配息", "緩衝金", "賣第一標的", "賣第二標的"]
MC_RUIN = "破產機率（繳不出貸款）"


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
        self.assertEqual(self.metric(at, "初期每月應繳"), "$13,439")        # 100 萬 since V40; 500 萬 gave $67,199
        self.assertEqual(self.metric(at, "初期每月應繳"), self.metric(self.start(loan="100", inc="5"), "初期每月應繳"))
        self.assertIn(MC_RUIN, [m.label for m in at.metric])
        self.assertEqual(dict(at.query_params), {})

    def test_a_link_from_v39_with_a_loan_keeps_its_numbers(self):
        at = self.start(loan="500")
        self.assertEqual(self.metric(at, "初期每月應繳"), "$67,199")
        self.assertEqual(at.number_input(key="inc").value, 0)             # no income: nothing is checked
        self.assertEqual(at.query_params["inc"], ["0"])

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
        self.assertEqual(self.order(at), ["賣第一標的"] + ["（不使用）"] * 4)
        self.assertIn("不會動用：薪水（自掏腰包）、存下來的配息、緩衝金、賣第二標的", [c.value for c in at.sidebar.caption])
        self.assertIn("第二標的沒有排進順位", self.texts(at.sidebar.caption))

    def test_second_asset_is_a_source_only_when_there_is_one(self):
        self.assertEqual(self.order(self.start()), SOURCES)
        self.assertNotIn("第二標的沒有排進順位", self.texts(self.start().sidebar.caption))
        for query in (dict(reinv="0"), dict(b="")):
            with self.subTest(query):
                at = self.start(**query)
                self.assertEqual(self.order(at), SOURCES[:4])
                self.assertNotIn("賣第二標的", at.selectbox(key="p1").options)

    def test_links_made_before_the_second_asset_was_a_source_still_mean_the_same(self):
        # "4" has always meant "not used"; the new source takes the next number.
        at = self.start(p1="3", p2="0", p3="4", p4="4", p5="5")
        self.assertEqual(self.order(at), ["賣第一標的", "薪水（自掏腰包）", "（不使用）", "（不使用）", "賣第二標的"])

    def test_selling_the_second_asset_shows_in_the_ledger(self):
        at = self.start(salary="0", p1="5", p2="3", p3="4", p4="4", p5="4", seed="1")
        ledger = at.dataframe[0].value
        self.assertGreater(ledger['賣第一標的繳'].sum(), 0)
        self.assertIn('賣第二標的繳', ledger.columns)
        paid = ledger[['從存下來的配息繳', '從緩衝金繳', '賣第一標的繳', '賣第二標的繳', '從薪水繳（自掏）']].sum(axis=1)
        np.testing.assert_allclose(paid[~ledger['已破產']], ledger['當月應繳'][~ledger['已破產']])

    def test_no_source_at_all_warns(self):
        at = self.start(p1="4", p2="4", p3="4", p4="4", p5="4")
        self.assertTrue(any("第一個月就會破產" in w.value for w in at.sidebar.warning))
        self.assertEqual(self.metric(at, MC_RUIN), "100.0%")

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
        self.assertEqual(dict(at.query_params), {"loan": ["300"], "inc": ["5"], "swan": ["1"]})   # inc tells it from a V39 link
        self.ok(at.number_input(key="loan").set_value(100).run())
        self.assertEqual(dict(at.query_params), {"swan": ["1"]})

    def test_black_swan_shows_once_in_the_ledger(self):
        # A fund that pays nothing, salary covering every payment: value is shares times price, nothing else.
        common = dict(a="00631L.TW", reinv="0", salary="1000000", fee="0", seed="1")
        ledger = self.start(swan="1", swan_m="12", swan_d="40", **common).dataframe[0].value
        before, after = ledger['槓桿：手上資產'].iloc[10], ledger['槓桿：手上資產'].iloc[11]
        plain = self.start(**common).dataframe[0].value
        natural = plain['槓桿：手上資產'].iloc[11] / plain['槓桿：手上資產'].iloc[10] - 1
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
        self.assertIn("120 個進場月份用到了替身 OLD.TW 的歷史", self.texts(at.caption))
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
        self.assertIn(MC_RUIN, [m.label for m in at.metric])

    def test_unadjusted_split_is_repaired_and_announced(self):
        at = self.start(a="SEAM.TW", seed="1")
        self.assertIn("1 股拆成 4 股", self.texts(at.info))
        self.assertNotIn("不尋常", self.texts(at.warning))
        repaired = self.metric(at, "期滿資產中位數（沒破產的）")

        at = self.start(a="SEAM.TW", seed="1", fix="0")
        self.assertNotIn("1 股拆成 4 股", self.texts(at.info))
        self.assertIn("2019-06-03 單日 -7", self.texts(at.warning))
        self.assertNotEqual(self.metric(at, "期滿資產中位數（沒破產的）"), repaired)

    def built_report(self, **query):
        import report
        with patch('report.build_report', wraps=report.build_report) as spy:
            at = self.start(**query)
        self.assertEqual(spy.call_count, 1)
        return at, spy.call_args.kwargs, report.build_report(**spy.call_args.kwargs)

    def test_report_gathers_what_the_page_shows(self):
        at, parts, html = self.built_report(loan="500", salary="15000", swan="1", swan_m="18", swan_d="35", seed="1", m="2020-03")
        settings = dict(parts["settings"])
        self.assertIn("500 萬元｜一般信貸", settings["貸款"])
        self.assertIn("無寬限期", settings["貸款"])
        self.assertEqual(settings["第一標的"], "00878.TW")
        self.assertEqual(settings["每月最多自掏"], "$15,000")
        self.assertIn("突發大崩盤（第 18 個月 -35%）", settings["有開啟的情境與稅費"])
        self.assertEqual(settings["逐月明細的進場月份"], "2020-03")
        self.assertEqual(settings["安全邊界"], "這次沒有計算")
        # every number on the page is in the report, under the same name
        shown = {m.label: m.value for m in at.metric}
        reported = {label: value for _, rows in parts["summaries"] for label, value in rows}
        self.assertEqual(reported, shown)
        self.assertEqual([heading for heading, _, _ in parts["tables"]],
                         ["蒙地卡羅：期滿資產的分佈", "蒙地卡羅：自己掏了多少錢、換到多少報酬"])
        headings = [heading for heading, _, _ in parts["figures"]]
        self.assertEqual(headings[:2], ["歷史回測：每個月進場，期滿剩多少", "蒙地卡羅：資產隨時間的可能範圍"])
        self.assertIn("2020-03 進場：資產和貸款餘額", headings)
        self.assertIn("2020-03 進場：每月貸款用哪些錢繳", headings)
        self.assertTrue(any("來源價格期間" in note for note in parts["data_notes"]))
        self.assertTrue(any("可用的歷史只有" in text for text in parts["warnings"]))
        self.assertIn("借錢投資 ETF 壓力測試報告：00878.TW", html)
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
        self.assertIn(MC_RUIN, [m.label for m in helped.metric])
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
        self.assertIn(MC_RUIN, [m.label for m in at.metric])

    def test_snapshot_data_is_flagged_with_its_date(self):
        at = self.start(a="STALE.TW")
        self.assertIn("STALE.TW：即時行情暫時無法取得，目前使用 2024-11-05 存檔的資料", self.texts(at.warning))
        self.assertNotIn("存檔的資料", self.texts(self.start().warning))

    def test_entry_month_changes_the_ledger_but_not_the_statistics(self):
        at = self.start(seed="1")
        metrics = [(m.label, m.value) for m in at.metric]
        ledger = at.dataframe[0].value
        self.assertEqual(ledger['月份'].iloc[0], "2022-02")     # entered 2022-01, first payment a month later
        self.ok(at.selectbox(key="m").set_value("2019-05").run())
        self.assertEqual([(m.label, m.value) for m in at.metric], metrics)
        self.assertEqual(at.dataframe[0].value['月份'].iloc[0], "2019-06")
        self.assertFalse(at.dataframe[0].value['槓桿：手上資產'].equals(ledger['槓桿：手上資產']))

    def test_random_job_loss_reports_averaged_history(self):
        at = self.start(jl="1", jl_mode="1", jl_prob="20")
        self.assertIn("每個進場月份各模擬 93 種失業時點", self.texts(at.caption))
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
        at = self.start(seed="1", loan="500")
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
        mc_labels = [MC_RUIN, "贏過定期定額的機率"]

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
        return next((c.value for c in at.caption if c.value.startswith("🟢 這次有開啟")), "")

    def ledger_tax(self, at):
        return at.dataframe[0].value['配息被扣的稅費'].sum()

    def test_taiwan_taxes_apply_by_default_and_can_be_switched_off(self):
        default = self.start(seed="1")
        self.assertIn("稅費（證交稅0.1%、補充保費2.11%、股利所得稅3.5%）", self.flags(default))
        self.assertGreater(self.ledger_tax(default), 0)

        untaxed = self.start(seed="1", stax="0", nhi="0", itax="0")
        self.assertNotIn("稅費", self.flags(untaxed))
        self.assertEqual(self.ledger_tax(untaxed), 0)
        median = lambda at: int(self.metric(at, "定期定額：期滿資產中位數").replace("$", "").replace(",", ""))
        self.assertGreater(median(untaxed), median(default))

    def test_tax_bracket_sets_the_dividend_tax(self):
        self.assertIn("股利所得稅28%", self.flags(self.start(itax="5")))
        low = self.flags(self.start(itax="1"))
        self.assertNotIn("股利所得稅", low)
        self.assertIn("補充保費2.11%", low)
        self.assertIn("配息的40%算股利所得", self.flags(self.start(dshare="40")))
        self.assertIn("開辦費\\$6,000", self.flags(self.start(lfee="6000")))
        self.assertEqual(self.start(itax="99").selectbox(key="itax").value, "12%")       # nonsense in a link

    def test_floating_rate_path_and_random_moves(self):
        fixed = self.start()
        self.assertNotIn("浮動利率", self.flags(fixed))
        self.assertNotIn("月付金最高會到", self.texts(fixed.caption))

        floating = self.start(**{"float": "1"})
        self.assertIn("浮動利率（第2年起每年 +0.25、+0.25、+0.125 個百分點，蒙地卡羅每年隨機 ±0.25）", self.flags(floating))
        self.assertIn("月付金最高會到", self.texts(floating.caption))
        self.assertIn("九成的路徑年利率落在", self.texts(floating.caption))
        self.assertIn("不含隨機升降息", self.texts(floating.caption))
        self.assertEqual(self.metric(floating, "初期每月應繳"), self.metric(fixed, "初期每月應繳"))
        rates = floating.dataframe[0].value['當月年利率 (%)']
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
        self.assertIn("「存下來的配息」不會有錢", self.texts(self.start().sidebar.caption))
        self.assertNotIn("「存下來的配息」不會有錢", self.texts(self.start(reinv="0").sidebar.caption))

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

    # ---- 安全邊界 ----

    def find_limit(self, at):
        return self.ok(at.button(key="safe_run").click().run())

    def heatmap(self, at):
        import json
        charts = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
        return next(c for c in charts if any(t.get("type") == "heatmap" for t in c["data"]))

    def test_safety_limit_waits_for_the_button(self):
        import report
        with patch('report.build_report', wraps=report.build_report) as spy, \
                patch('engine.solve_for', wraps=__import__('engine').solve_for) as solve:
            at = self.start()
        solve.assert_not_called()
        self.assertIn("還沒有計算。按「計算安全邊界」開始。", self.texts(at.caption))
        self.assertIn("想知道最多能借多少？看下方的[安全邊界](#safe-limit)。", self.texts(at.caption))
        self.assertNotIn("最多可以借", [m.label for m in at.metric])
        self.assertEqual(at.segmented_control(key="tgt").value, "5")
        self.assertEqual(at.segmented_control(key="tgt").options, ["1%", "5%", "10%"])
        self.assertEqual(dict(spy.call_args.kwargs["settings"])["安全邊界"], "這次沒有計算")

    def test_safety_limit_answers_and_map(self):
        at = self.find_limit(self.start(seed="1", loan="500"))
        labels = {m.label: m for m in at.metric}
        self.assertEqual(labels["最多可以借"].value, "5,000 萬以上")         # the fixture market is kind
        self.assertEqual(labels["每月最少要自掏"].value, "$0")
        self.assertEqual(len(at.success), 2)
        self.assertNotIn("還沒有計算", self.texts(at.caption))
        table = at.table[0].value
        self.assertEqual(table.shape, (6, 6))
        self.assertEqual(list(table.columns), ["$12,500", "$18,750", "$25,000", "$31,250", "$37,500", "$50,000"])
        self.assertEqual(table.iloc[2, 2], "◆ " + self.metric(at, MC_RUIN))      # same paths as the result above
        figure = self.heatmap(at)
        self.assertEqual((figure["layout"]["xaxis"]["type"], figure["layout"]["yaxis"]["type"]), ("category", "category"))
        self.assertIn("◆ 目前", figure["data"][0]["text"][2][2])

    def test_safety_limit_with_a_tight_budget(self):
        at = self.find_limit(self.start(loan="500", salary="5000", rate="8", seed="1", tgt="1"))
        self.assertEqual(at.segmented_control(key="tgt").value, "1")
        principal = self.metric(at, "最多可以借")
        self.assertRegex(principal, r"^[\d,]+ 萬$")
        sentences = self.texts(at.success) + self.texts(at.warning) + self.texts(at.error)
        self.assertIn("要讓破產機率在 1% 以下，最多可以借 **" + principal, sentences)
        self.assertIn("你目前設定 \\$5,000", sentences)                     # dollar signs are not read as a formula

    def test_target_comes_from_the_link_and_goes_back_into_it(self):
        self.assertEqual(self.start(tgt="10").segmented_control(key="tgt").value, "10")
        self.assertEqual(self.start(tgt="7").segmented_control(key="tgt").value, "5")
        at = self.start()
        self.ok(at.segmented_control(key="tgt").set_value("1").run())
        self.assertEqual(dict(at.query_params), {"tgt": ["1"]})
        self.ok(at.segmented_control(key="tgt").set_value("5").run())
        self.assertEqual(dict(at.query_params), {})

    def test_old_safety_limit_is_marked_and_left_out_of_the_report(self):
        import report
        at = self.find_limit(self.start(seed="1", loan="500"))
        self.ok(at.segmented_control(key="tgt").set_value("10").run())
        self.assertIn("你改了能接受的破產機率，下面還是 5% 的結果。", self.texts(at.warning))
        self.assertIn("最多可以借", [m.label for m in at.metric])              # the old answer stays on screen
        self.ok(at.segmented_control(key="tgt").set_value("5").run())
        self.assertNotIn("你改了能接受的破產機率", self.texts(at.warning))

        with patch('report.build_report', wraps=report.build_report) as spy:
            self.ok(at.run())
        parts = spy.call_args.kwargs
        self.assertEqual(dict(parts["settings"])["安全邊界的目標"], "破產機率 ≤ 5%")
        group, rows = parts["summaries"][-1]
        self.assertEqual(group, "安全邊界（破產機率 ≤ 5%）")
        self.assertEqual([label for label, _ in rows],
                         ["最多可以借", "借到 5,000 萬時的破產機率", "每月最少要自掏", "完全不自掏時的破產機率"])
        self.assertEqual((rows[0][1], rows[2][1]), ("5,000 萬以上", "$0"))
        self.assertIn("破產機率地圖：借多少 × 每月自掏多少", [h for h, _, _ in parts["tables"]])
        self.assertIn("破產機率地圖：借多少 × 每月自掏多少", [h for h, _, _ in parts["figures"]])

        with patch('report.build_report', wraps=report.build_report) as spy:
            self.ok(at.number_input(key="loan").set_value(600).run())
        self.assertIn("設定已變更，下面的安全邊界是用舊設定算的。", self.texts(at.warning))
        parts = spy.call_args.kwargs
        self.assertEqual(dict(parts["settings"])["安全邊界"], "這次沒有計算")
        self.assertNotIn("破產機率地圖：借多少 × 每月自掏多少", [h for h, _, _ in parts["tables"]])
        self.assertFalse(any(group.startswith("安全邊界") for group, _ in parts["summaries"]))
        self.find_limit(at)
        self.assertNotIn("舊設定", self.texts(at.warning))

    def test_safety_limit_without_salary_in_the_order(self):
        import report
        with patch('report.build_report', wraps=report.build_report) as spy:
            at = self.find_limit(self.start(p1="3", p2="5", p3="4", p4="4", p5="4", seed="1"))
        self.assertIn("你沒有把「薪水（自掏腰包）」排進還款順位", self.texts(at.info))
        self.assertNotIn("每月最少要自掏", [m.label for m in at.metric])
        captions = self.texts(at.caption)
        self.assertIn("你沒有用薪水補貼還款。這時借多借少", captions)
        self.assertIn("你沒有把薪水排進還款順位，所以地圖上每一格幾乎都一樣", captions)
        rows = dict(next(rows for group, rows in spy.call_args.kwargs["summaries"] if group.startswith("安全邊界")))
        self.assertEqual(rows["每月最少要自掏"], "不計算（薪水沒有排進還款順位）")
        self.assertEqual(len(rows), 3)                                       # no rate row for a search not run
        rows = at.table[0].value.map(lambda cell: cell.removeprefix("◆ ")).to_numpy()
        self.assertTrue((rows == rows[:, :1]).all())                         # the cap changes nothing

    def test_safety_limit_with_fresh_draws_and_a_big_fee(self):
        at = self.find_limit(self.start(loan="500", seed="0", lfee="3000000"))
        self.assertIn("你關閉了「固定亂數」，安全邊界固定用同一組抽樣計算", self.texts(at.caption))
        self.assertEqual(list(at.table[0].value.iloc[0]), ["—"] * 6)       # 250 萬 does not cover the fee
        self.assertIn("「—」的格子", self.texts(at.caption))
        grey, heat = self.heatmap(at)["data"]
        self.assertEqual(grey["text"][0], ["—"] * 6)
        self.assertEqual(grey["textfont"]["color"], "#0b0b0b")             # readable on grey in either theme
        self.assertEqual(heat["text"][0], [""] * 6)

    def test_zero_salary_cap_explains_the_first_column(self):
        at = self.find_limit(self.start(salary="0", seed="1"))
        self.assertEqual(list(at.table[0].value.columns), ["$0", "$5,000", "$10,000", "$20,000", "$30,000", "$50,000"])
        self.assertIn("你的每月最多自掏是 0，所以最左邊「\\$0」那一欄上下幾乎都一樣", self.texts(at.caption))
        self.assertIn("你沒有用薪水補貼還款。", self.texts(at.caption))

    def test_random_job_loss_is_described_in_full(self):
        at = self.start(jl="1", jl_mode="1", jl_prob="5", jl_mean="5.5")
        self.assertRegex(self.flags(at), r"隨機失業（年失業機率 5\.0%，平均失業 5\.5 個月，對數常態，每月最多自掏 \\\$0；"
                                         r"崩盤（單月跌超過 15%）時年失業機率再加 8～12%｜蒙地卡羅中 \d+\.\d% 的路徑失業過，"
                                         r"平均失業 \d+\.\d 個月）")
        self.assertNotIn("崩盤（", self.flags(self.start(jl="1", jl_mode="1", jl_crash="0")))

    # ---- 使用者回饋（F2～F5） ----

    def test_saving_the_results_is_one_primary_button(self):
        at = self.start()
        buttons = {d.proto.label: d.proto for d in at.get("download_button")}
        self.assertEqual(buttons["📄 把這次的結果存下來"].type, "primary")
        self.assertNotIn("把這次的結果存下來", self.texts(at.markdown))           # no heading above it any more
        self.assertIn("也可以直接列印成 PDF。圖表需要連上網路才會顯示。", self.texts(at.caption))

    def test_cash_buffer_sits_right_below_the_loan(self):
        keys = [getattr(node, "key", None) for node in self.start().sidebar]
        keys = [k for k in keys if k]
        self.assertEqual(keys[keys.index("loan") + 1], "buf")
        self.assertLess(keys.index("type"), keys.index("loan"))                 # the kind comes first since V40
        self.assertEqual(self.start(buf="6").slider(key="buf").value, 6)          # old links still work

    def test_report_works_without_a_time_zone_database(self):
        import zoneinfo

        def missing(*args, **kwargs):
            raise zoneinfo.ZoneInfoNotFoundError("No time zone found with key Asia/Taipei")

        # The fixture's own prices carry the Taipei zone, so they are made before the database goes missing.
        histories = {t: fake_history(t) for t in ("00878.TW", "0056.TW", "00631L.TW")}
        self.load_history.side_effect = histories.__getitem__
        with patch("zoneinfo.ZoneInfo", side_effect=missing):
            at, parts, _ = self.built_report(seed="1")
        self.assertRegex(parts["generated"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}（台北時間）$")
        self.assertEqual(len(at.error), 0)

    def errors(self, at):
        return [f"{e.proto.icon} {e.value}" if e.proto.icon else e.value for e in at.error]

    def test_a_broken_report_leaves_the_rest_of_the_page(self):
        with patch("report.build_report", side_effect=RuntimeError("boom")):
            at = self.start()
        self.assertEqual(self.errors(at), ["❌ 這次的報告暫時無法產生，其他結果不受影響。"])
        self.assertIn(MC_RUIN, [m.label for m in at.metric])
        self.assertIn("不構成任何投資建議", self.texts(at.caption))                 # the footer still runs
        self.assertNotIn("把這次的結果存下來", [d.proto.label for d in at.get("download_button")])

    def test_a_broken_part_is_replaced_by_a_plain_message_and_no_report_is_offered(self):
        with patch("engine.run_trace", side_effect=RuntimeError("boom")):
            at = self.start()
        self.assertEqual(self.errors(at), ["❌ 「逐月明細」這一段暫時無法顯示，其他結果不受影響。",
                                           "❌ 這次的報告暫時無法產生，其他結果不受影響。"])
        self.assertIn(MC_RUIN, [m.label for m in at.metric])
        self.assertTrue(any(d.proto.label == "📥 下載蒙地卡羅結果 (CSV)" for d in at.get("download_button")))

        with patch("safety_limit.map_figure", side_effect=RuntimeError("boom")):
            at = self.find_limit(self.start())
        self.assertIn("❌ 「安全邊界」這一段暫時無法顯示，其他結果不受影響。", self.errors(at))
        self.assertTrue(any(h.value.startswith("🔍 逐月明細") for h in at.header))

    def test_a_failing_calculation_shows_a_plain_message(self):
        with patch("engine.run_summary", side_effect=RuntimeError("boom")):
            at = self.start()
        self.assertEqual(self.errors(at), ["❌ 這次的計算暫時無法完成。可以調整設定後再試一次，或按側欄的「重新載入行情」。"])
        self.assertIn("不構成任何投資建議", self.texts(at.caption))
        with patch("engine.run_summary", side_effect=ValueError("貸款開辦費必須小於貸款本金。")):
            at = self.start()
        self.assertEqual(self.errors(at), ["❌ 參數有誤，請先修正：\n\n貸款開辦費必須小於貸款本金。"])

    def test_unexpected_trouble_loading_data_is_a_plain_message(self):
        with patch("market_data.align_months", side_effect=KeyError("Close_A")):
            at = self.start()
        self.assertEqual(self.errors(at), ["❌ 資料獲取異常：\n\n行情資料暫時無法處理。請稍後再試，或按側欄的「重新載入行情」。"])

    # ---- 破產發生在第幾年（F6） ----

    def with_defaults(self, months, **query):
        """Run the page with the Monte Carlo paths defaulting exactly in `months` (1-based) and nowhere else."""
        import engine
        real = engine.run_summary

        def rigged(df, params):
            result = real(df, params)
            mc = result.mc.copy()
            mc["Is_Ruined"], mc["Ruin_Month"] = False, 0
            mc.loc[:len(months) - 1, "Is_Ruined"] = True
            mc.loc[:len(months) - 1, "Ruin_Month"] = months
            result.mc = mc
            return result

        with patch("engine.run_summary", side_effect=rigged):
            return self.start(seed="1", **query)

    def year_chart(self, at):
        import json
        for node in at.get("plotly_chart"):
            spec = json.loads(node.proto.spec)
            bars = [t for t in spec["data"] if t.get("type") == "bar" and str(t["x"][0]).startswith("第1年")]
            if bars:
                return spec, bars[0]
        self.fail("no chart of defaults by year")

    def check_year_chart(self, at, years, expected):
        spec, bar = self.year_chart(at)
        self.assertEqual(bar["x"], [f"第{y}年" for y in range(1, years + 1)])
        self.assertEqual(spec["layout"]["xaxis"]["type"], "category")
        counts = bar["y"]["bdata"] if isinstance(bar["y"], dict) else bar["y"]
        if isinstance(counts, str):
            import base64
            counts = list(np.frombuffer(base64.b64decode(counts), dtype=bar["y"]["dtype"]))
        self.assertEqual([int(c) for c in counts], expected)
        self.assertEqual(bar["text"], [str(c) if c else "" for c in expected])
        yaxis = spec["layout"]["yaxis"]
        self.assertEqual((yaxis["tickformat"], yaxis["tick0"]), ("d", 0))
        self.assertEqual(yaxis["dtick"], int(yaxis["dtick"]))
        self.assertGreaterEqual(yaxis["dtick"], 1)
        self.assertEqual(yaxis["title"]["text"], "破產的模擬次數")

    def test_a_single_default_still_gives_a_readable_chart(self):
        at = self.with_defaults([77])
        self.assertIn("##### 蒙地卡羅：破產多半發生在第幾年", [m.value for m in at.markdown])
        self.check_year_chart(at, 7, [0, 0, 0, 0, 0, 0, 1])
        captions = self.texts(at.caption)
        self.assertIn("每根柱子代表貸款的一年；高度是 2,000 次模擬裡，在那一年繳不出貸款的次數。", captions)
        self.assertIn("2,000 次模擬裡只有 1 次破產，發生在第 77 個月。次數很少，這張圖只供參考。", captions)
        self.assertNotIn("有一半發生在第", captions)

    def test_defaults_bunched_in_one_year(self):
        at = self.with_defaults([25, 30, 36, 26, 30], years="10")
        self.check_year_chart(at, 10, [0, 0, 5, 0, 0, 0, 0, 0, 0, 0])
        self.assertIn("只有 5 次破產，發生在第 25、26、30（2 次）、36 個月。", self.texts(at.caption))
        last_repeated = self.with_defaults([61, 84, 84])
        self.assertIn("只有 3 次破產，發生在第 61、84（2 次）個月。", self.texts(last_repeated.caption))
        spec, _ = self.year_chart(last_repeated)
        self.assertEqual((spec["layout"]["height"], spec["layout"]["margin"]["t"], spec["layout"]["margin"]["b"]),
                         (400, 30, 10))

    def test_many_defaults_keep_the_median_sentence_and_go_into_the_report(self):
        import report
        months = [1, 12, 13, 24, 37, 40, 40, 41, 84, 84, 60, 61]
        with patch("report.build_report", wraps=report.build_report) as spy:
            at = self.with_defaults(months)
        self.check_year_chart(at, 7, [2, 2, 0, 4, 1, 1, 2])
        captions = self.texts(at.caption)
        self.assertIn("12 次破產的模擬裡，有一半發生在第 40 個月之前。", captions)
        self.assertNotIn("次數很少", captions)
        heading, figure, note = next(f for f in spy.call_args.kwargs["figures"] if f[0] == "蒙地卡羅：破產多半發生在第幾年")
        self.assertEqual(list(figure.data[0].x), [f"第{y}年" for y in range(1, 8)])
        self.assertIn("每根柱子代表貸款的一年", note)
        self.assertIn("有一半發生在第 40 個月之前", note)

    def test_blank_second_ticker_reinvests_everything_in_the_first(self):
        at = self.start()
        self.ok(at.text_input(key="b").set_value("").run())
        self.assertEqual(len(at.error), 0)
        self.assertEqual(at.dataframe[0].value['第二標的股數'].abs().sum(), 0)


if __name__ == '__main__':
    unittest.main()
