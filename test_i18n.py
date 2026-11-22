"""Checks on the two-language interface text (story 39).

Part 1 reads the source files, not the running app: every Chinese sentence the pages can show must have an
English version with the same placeholders, and no sentence may be left outside i18n.
Part 2 runs the app with `?lang=en` and collects everything the screen shows: nothing but the ETF names
and the language switch's own "中文" may contain Chinese, Japanese or Korean characters.
"""
import ast
import os
import pickle
import re
import string
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import i18n
from i18n_en import EN
from test_acceptance_helpers import APP, DETAILS_PAGE, AppHarness, Recorder, report_texts, visible_texts

HERE = os.path.dirname(os.path.abspath(__file__))
CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯぀-ヿ가-힯]")
SOURCES = ["app.py", "main_page.py", "ui_state.py", "safety_limit.py", "credit_limit.py", "report.py", "engine.py",
           "market_data.py", "version.py", "pages/1_Model_Details.py"]
WRAPPERS = {"t", "msg", "err", "need"}      # calls whose text argument is an i18n key
CAPS = re.compile(r"^_?[A-Z][A-Z0-9_]*$")


def _cjk_constants(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and CJK.search(n.value)]


def scan(path):
    """(keys, loose): the texts handed to t()/msg()/err() or kept in module-level constants, and Chinese
    literals found anywhere else, as (line, text) pairs."""
    with open(os.path.join(HERE, path), encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    keys, covered = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if func in WRAPPERS:
                args = node.args[1:2] if func == "need" else node.args[:1]
                for arg in args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and CJK.search(arg.value):
                        keys.append(arg.value)
                        covered.add(arg)
    for statement in tree.body:                       # module-level constants: their texts are keys, shown through t()
        if isinstance(statement, ast.Assign) and all(
                isinstance(x, ast.Name) and CAPS.match(x.id) for target in statement.targets for x in ast.walk(target)
                if isinstance(x, ast.Name)):
            for const in _cjk_constants(statement):
                keys.append(const.value)
                covered.add(const)
    loose = []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant):
            docstrings.add(node.body[0].value)
    body_from = next((i for i, line in enumerate(source.splitlines(), 1) if line.strip() == "st.stop()"), None) \
        if path.startswith("pages/") else None          # the Chinese page body follows the English dispatch
    for const in _cjk_constants(tree):
        if const in covered or const in docstrings or (body_from and const.lineno > body_from):
            continue
        parent = parents.get(const)
        if isinstance(parent, (ast.Compare, ast.Subscript)) or (isinstance(parent, ast.Dict) and const in parent.keys):
            continue                                   # data the code compares with, not text it shows
        loose.append((const.lineno, const.value))
    return keys, loose


# Chinese text that is deliberately outside i18n: it is data the code compares with, or text that only goes to a log or
# to a string method, or an English default that the page translates when it shows it.
RAW_OK = {
    "main_page.py": {"（", "）"},
    "safety_limit.py": {" 萬"},                # the Chinese-only branch of the amount labels
    "credit_limit.py": {" 萬"},
    "market_data.py": {"上市", "日期", "收盤價", "資料日期", "股票代號", "權值+息值", "權/息", "息", "息值", "沒有符合條件"},
}


def placeholders(text):
    return sorted((name, spec) for _, name, spec, _ in string.Formatter().parse(text) if name is not None)


class CatalogTests(unittest.TestCase):
    def collected(self):
        found = {}
        for path in SOURCES:
            keys, loose = scan(path)
            for key in keys:
                found.setdefault(key, path)
        return found

    def test_every_chinese_sentence_has_an_english_version(self):
        missing = [f"{path}: {key[:50]}" for key, path in self.collected().items() if key not in EN]
        self.assertEqual(missing, [], "add these to i18n_en.EN")

    def test_english_has_no_leftovers_and_no_chinese(self):
        known = set(self.collected())
        orphans = [key[:50] for key in EN if key not in known and key not in EXTRA_KEYS]
        self.assertEqual(orphans, [], "entries nothing uses any more")
        chinese = [f"{key[:30]} -> {value[:40]}" for key, value in EN.items() if CJK.search(value)]
        self.assertEqual(chinese, [])
        empty = [key[:40] for key, value in EN.items() if not value.strip()]
        self.assertEqual(empty, [])

    def test_placeholders_match(self):
        bad = [f"{key[:40]!r}: {placeholders(key)} != {placeholders(value)}" for key, value in EN.items()
               if placeholders(key) != placeholders(value)]
        self.assertEqual(bad, [])

    def test_no_chinese_text_is_left_outside_i18n(self):
        left = []
        for path in SOURCES:
            for line, text in scan(path)[1]:
                if text not in RAW_OK.get(path, set()):
                    left.append(f"{path}:{line} {text[:40]!r}")
        self.assertEqual(left, [], "wrap these in t()/msg()/err(), or list them in RAW_OK if the code only compares with them")

    def test_no_unconverted_chinese_f_strings(self):
        left = []
        for path in SOURCES:
            with open(os.path.join(HERE, path), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr) and any(
                        isinstance(v, ast.Constant) and CJK.search(v.value) and v.value.strip() != "萬"
                        for v in node.values) and not path.startswith("pages/"):
                    left.append(f"{path}:{node.lineno}")
        self.assertEqual(left, [])


# English entries that are looked up by a path the scan cannot see (a parameter that is itself a text).
EXTRA_KEYS = set()


class MechanismTests(unittest.TestCase):
    def test_chinese_is_the_default_and_passes_through(self):
        self.assertEqual(i18n.lang(), "zh")
        self.assertEqual(i18n.t("開始計算"), "開始計算")
        self.assertEqual(i18n.t("第{y}年", y=3), "第3年")
        self.assertEqual(i18n.t("100%"), "100%")

    def test_english_and_an_unknown_text(self):
        with i18n.use("en"):
            self.assertEqual(i18n.t("開始計算"), "Run")
            self.assertEqual(i18n.t("沒有這句話"), "沒有這句話")     # no entry: the Chinese comes back, tests would see it
            self.assertEqual(i18n.nt(67199.9), "NT$67,199")
            self.assertEqual(i18n.nt_round(67199.9), "NT$67,200")
        self.assertEqual(i18n.nt(67199.9), "$67,199")

    def test_amounts_in_english(self):
        self.assertEqual(i18n.nt_big(8_200_000), "NT$8.2 million")
        self.assertEqual(i18n.nt_big(5_000_000), "NT$5 million")
        self.assertEqual(i18n.nt_big(820_000), "NT$820,000")
        self.assertEqual(i18n.nt_short(8_200_000), "NT$8.2M")

    def test_a_stored_message_is_rendered_again_in_the_language_of_the_moment(self):
        stored = i18n.msg("❌ 無法計算安全邊界：{exc}", exc=i18n.err("貸款期數至少需要 1 個月。"))
        self.assertEqual(str(stored), "❌ 無法計算安全邊界：貸款期數至少需要 1 個月。")
        with i18n.use("en"):
            self.assertEqual(i18n.t(stored), "❌ Couldn't find the safety limit: The loan term must be at least 1 month.")
        again = pickle.loads(pickle.dumps(stored))
        self.assertEqual((str(again), again.template, again.params.keys()), (str(stored), stored.template, stored.params.keys()))

    def test_an_error_keeps_its_chinese_message_and_carries_a_code(self):
        exc = i18n.err("未知的還款資金來源：{src}", src="x")
        self.assertIsInstance(exc, ValueError)
        self.assertEqual(str(exc), "未知的還款資金來源：x")
        self.assertEqual((exc.template, exc.params), ("未知的還款資金來源：{src}", {"src": "x"}))
        with i18n.use("en"):
            self.assertEqual(i18n.t(exc), "Unknown repayment source: x")


    def test_engine_and_market_data_raise_coded_errors(self):
        import engine
        import market_data
        with self.assertRaises(i18n.LocalizedError) as caught:
            engine.validate_params(engine.SimParams(principal=-1.0, annual_rate_pct=2.0, total_months=12))
        self.assertEqual(str(caught.exception), "貸款本金必須大於 0。")           # D8: the Chinese message is unchanged
        self.assertEqual(caught.exception.template, "貸款本金必須大於 0。")
        with self.assertRaises(i18n.LocalizedError) as caught:
            engine.parse_annual_returns("5, -150")
        with i18n.use("en"):
            self.assertEqual(i18n.t(caught.exception), "Yearly returns must be above -100%.")
        with self.assertRaises(i18n.LocalizedError) as caught:
            market_data.normalize_ticker("###")
        self.assertEqual(caught.exception.params["ticker"], "###")
        with i18n.use("en"):
            self.assertIn("is not in a valid format", i18n.t(caught.exception))

    def test_data_notes_are_stored_as_messages(self):
        import pandas as pd
        import market_data
        index = pd.bdate_range("2020-01-01", periods=300)
        close = pd.Series(100.0, index=index)
        close.iloc[150:] = 25.0                      # a 4-for-1 split the source did not adjust
        frame = pd.DataFrame({"Close": close, "Dividends": 0.0, "Open": close, "High": close, "Low": close, "Volume": 1})
        _, notes = market_data.repair_history(frame)
        self.assertTrue(notes, "the seam should be repaired and noted")
        for note in notes:
            self.assertIsInstance(note, i18n.Msg)
            self.assertTrue(CJK.search(str(note)))                    # Chinese by default, as before
            with i18n.use("en"):
                self.assertFalse(CJK.search(i18n.t(note)), i18n.t(note))


# ---------------------------------------------------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------------------------------------------------

UNMARKED_DOLLAR = re.compile(r"(?<!NT)\$(?=\d)")     # E-14: every amount reads NT$
LANGUAGE_NAME = "中文"        # D10: the switch names each language in its own words


def cjk_in(texts, names=()):
    """[(kind, snippet)] of texts holding Chinese, after taking away the ETF names and the switch's own "中文"."""
    found = []
    for kind, text in texts:
        text = str(text)
        for name in names:
            text = text.replace(name, " ")
        if kind in ("button_group", "segmented_control") and text.strip() == LANGUAGE_NAME:
            continue
        match = CJK.search(text)
        if match:
            start = max(0, match.start() - 30)
            found.append((kind, text[start:match.start() + 40].replace("\n", " ")))
    return found


class EnglishScreen(AppHarness, unittest.TestCase):
    """The default scenario and the special ones, with `?lang=en`: no Chinese anywhere on the screen."""

    def setUp(self):
        super().setUp()
        self.etf_names = []

    def screen(self, at):
        return visible_texts(at)

    def assertEnglish(self, at, label=""):
        texts = self.screen(at)
        leaks = cjk_in(texts, self.etf_names)
        self.assertEqual(leaks, [], f"Chinese left on the English screen ({label})")
        bare = [(kind, str(text)[:60]) for kind, text in texts if UNMARKED_DOLLAR.search(str(text).replace("\\$", "$"))]
        self.assertEqual(bare, [], f"amounts must read NT$ ({label})")

    def click_safety(self, at):
        at = at.button(key="safe_run").click().run()
        return self.ok(at)

    def test_default_scenario(self):
        with Recorder() as rec:
            at = self.start(lang="en")
        self.assertEnglish(at, "default")
        self.assertEqual(at.query_params["lang"], ["en"] if isinstance(at.query_params["lang"], list) else "en")
        leaks = cjk_in([("report", t) for t in report_texts(rec.last_report())])
        self.assertEqual(leaks, [], "Chinese in the report")
        html = rec.report_html()
        self.assertIn("lang='en'", html[:200].replace('"', "'"))
        for label, name, _ in rec.downloads:
            self.assertFalse(CJK.search(str(label) + str(name)), (label, name))
        for label, name, frame in rec.csv_frames():
            self.assertEqual(cjk_in([("csv", c) for c in frame.columns]), [], name)

    def test_credit_limit_exceeded(self):
        at = self.start(lang="en", loan="900", inc="5")
        self.assertEnglish(at, "over the credit limit")

    def test_credit_limit_everything(self):
        for query in ({"inc": "0"}, {"inc": "5", "lmode": "1"}, {"inc": "2", "udebt": "10"}, {"inc": "5", "udebt": "120"},
                      {"inc": "5", "lmode": "1", "udebt": "120"}, {"type": "0"}, {"inc": "2", "loan": "300", "salary": "60000"}):
            with self.subTest(query=query):
                self.assertEnglish(self.start(lang="en", **query), str(query))

    def test_safety_limit(self):
        at = self.click_safety(self.start(lang="en"))
        self.assertEnglish(at, "safety limit")

    def test_safety_limit_with_a_cap_and_without_salary(self):
        at = self.click_safety(self.start(lang="en", loan="400", inc="5"))
        self.assertEnglish(at, "safety limit under a credit cap")
        at = self.click_safety(self.start(lang="en", salary="0"))
        self.assertEnglish(at, "safety limit, no salary")

    def test_stale_state(self):
        at = self.start(lang="en")
        at = self.ok(at.number_input(key="loan").set_value(200).run())
        self.assertEnglish(at, "stale")
        self.assertTrue(any("out of date" in w.value for w in at.warning), "the stale notice is shown")

    def test_input_errors(self):
        for query in ({"float": "1", "rpath": "1; 2"}, {"scen": "3", "path": "5, -150"}, {"float": "1", "rpath": "30"},
                      {"a": "ZZZZ.TW"}, {"a": "###"}):
            with self.subTest(query=query):
                self.assertEnglish(self.start(lang="en", **query), str(query))

    def test_the_other_switches_and_scenarios(self):
        for query in ({"shock": "1", "float": "1", "rvol": "0.5"}, {"jl": "1"}, {"jl": "1", "jl_mode": "1"},
                      {"swan": "1", "hc": "1"}, {"scen": "3"}, {"auto": "1"}, {"seed": "0"}, {"nhi": "0", "itax": "5"},
                      {"type": "0", "grace": "1"}, {"reinv": "0"}, {"p1": "4", "p2": "0"}):
            with self.subTest(query=query):
                self.assertEnglish(self.start(lang="en", **query), str(query))

    def test_details_page(self):
        links = []
        with patch("streamlit.page_link", side_effect=lambda *a, **k: links.append(k.get("label", ""))):
            at = AppTest.from_file(APP, default_timeout=180)
            at.query_params["lang"] = "en"
            at = at.run().switch_page(DETAILS_PAGE).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertEqual(links, ["← Back to the stress test"])
        self.assertEqual(cjk_in(visible_texts(at)), [])
        self.assertGreater(len(at.markdown), 10)
        # math written inside the formulas counts as text too
        for latex in at.get("latex"):
            self.assertFalse(CJK.search(latex.value), latex.value)


class DetailsPageTests(unittest.TestCase):
    """The two versions of the "How it works" page are written separately; they must keep the same shape."""

    def run_page(self, lang):
        with patch("streamlit.page_link"):
            at = AppTest.from_file(APP, default_timeout=180)
            if lang:
                at.query_params["lang"] = lang
            at = at.run().switch_page(DETAILS_PAGE).run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at

    def shape(self, at):
        return {kind: len(at.get(kind)) for kind in ("header", "subheader", "table", "latex", "warning", "info", "caption", "title")}

    def test_same_sections_tables_and_formulas_in_both_languages(self):
        zh, en = self.run_page(None), self.run_page("en")
        self.assertEqual(self.shape(en), self.shape(zh))
        self.assertEqual(len(en.get("header")), 12)
        self.assertEqual(len(zh.markdown), len(en.markdown))
        self.assertEqual([m.value.count("|") for m in zh.markdown if m.value.lstrip().startswith("| ")],
                         [m.value.count("|") for m in en.markdown if m.value.lstrip().startswith("| ")])


class SwitchingTests(AppHarness, unittest.TestCase):
    """E-04: changing the language changes the words and nothing else."""

    def lang_control(self, at):
        return at.sidebar.get("button_group")[0]

    def test_switch_keeps_the_numbers_and_does_not_recalculate(self):
        with Recorder() as rec:
            at = self.start()
            runs = len(rec.summaries)
            before = [(m.label, m.value) for m in at.metric]
            report_before = rec.report_html()
            self.lang_control(at).set_value("en")
            at = self.ok(at.run())
            self.assertEqual(len(rec.summaries), runs, "no new calculation")
            after = [(m.label, m.value) for m in at.metric]
            self.assertEqual(len(before), len(after))
            self.assertEqual([v.replace("$", "") for _, v in before], [v.replace("NT$", "").replace("$", "") for _, v in after])
            self.assertFalse(any("out of date" in w.value for w in at.warning), "not stale")
            self.assertNotEqual(report_before, rec.report_html())
            self.assertEqual(at.query_params["lang"] if not isinstance(at.query_params["lang"], list) else at.query_params["lang"][0], "en")
            self.lang_control(at).set_value("zh")
            at = self.ok(at.run())
            self.assertEqual(len(rec.summaries), runs)
            self.assertEqual([(m.label, m.value) for m in at.metric], before)
            self.assertNotIn("lang", at.query_params)

    def test_switch_keeps_every_setting(self):
        query = {"loan": "150", "rate": "3.2", "type": "0", "jl": "1", "scen": "1", "dfreq": "2", "salary": "30000"}
        at = self.start(**query)
        def stored(app):  # choice widgets hold the page-language text; the choice itself is kept in _c_<key>
            return {k: app.session_state[f"_c_{k}"] if f"_c_{k}" in app.session_state else app.session_state[k] for k in query}
        mine = stored(at)
        self.lang_control(at).set_value("en")
        at = self.ok(at.run())
        self.assertEqual(stored(at), mine)
        for key, value in query.items():
            self.assertEqual(str(at.query_params[key][0] if isinstance(at.query_params[key], list) else at.query_params[key]), value)


if __name__ == "__main__":
    unittest.main()
