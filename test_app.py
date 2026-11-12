"""End-to-end checks of the Streamlit pages with market data stubbed out (no network)."""
import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
MORTGAGE, CREDIT = "理財型房貸 (長年期/可寬限)", "一般信貸 (短年期/無寬限)"
SOURCES = ["本薪(自掏腰包)", "配息資金池", "緩衝金", "變賣資產(主標的)"]


def fake_history(ticker):
    """Deterministic daily prices; the 'L' ticker behaves like a 2x fund and pays nothing."""
    rng = np.random.RandomState(sum(map(ord, ticker)))
    days = pd.bdate_range('2016-01-04', '2024-12-31')
    leverage = 2.0 if 'L' in ticker else 1.0
    close = 20 * np.cumprod(1 + rng.normal(0.0004 * leverage, 0.011 * leverage, len(days)))
    dividends = np.zeros(len(days))
    if leverage == 1.0:
        months = pd.Series(days.month, index=days)
        first_day = ~pd.Series(days.to_period('M'), index=days).duplicated()
        payout = (first_day & months.isin([2, 5, 8, 11])).to_numpy()
        dividends[payout] = close[payout] * 0.015
    return pd.DataFrame({'Close': close, 'Dividends': dividends}, index=days.tz_localize('Asia/Taipei'))


class AppTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
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
        return [at.selectbox(key=f"p{i}").value for i in range(1, 5)]

    def test_defaults_render_results(self):
        at = self.start()
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
        for slot in (1, 2, 3):
            for source in at.selectbox(key=f"p{slot}").options:
                self.ok(at.selectbox(key=f"p{slot}").set_value(source).run())
                chosen = [s for s in self.order(at) if s != "（不使用）"]
                self.assertEqual(len(chosen), len(set(chosen)), self.order(at))

    def test_a_source_can_be_left_out(self):
        at = self.start(p1="3", p2="4", p3="4", p4="4")
        self.assertEqual(self.order(at), ["變賣資產(主標的)", "（不使用）", "（不使用）", "（不使用）"])
        self.assertIn("不會動用：本薪(自掏腰包)、配息資金池、緩衝金", [c.value for c in at.sidebar.caption])

    def test_no_source_at_all_warns(self):
        at = self.start(p1="4", p2="4", p3="4", p4="4")
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
