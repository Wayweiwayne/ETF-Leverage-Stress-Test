"""Sprint 5-1: in English no choice widget holds or shows Chinese (value and options), and a language switch keeps the choice."""
import re
import unittest

import test_app

CJK = re.compile("[⺀-鿿가-힯＀-￯　-〿]")


class ChoiceLanguageTests(unittest.TestCase):
    setUp, start, ok, change, order = (test_app.AppTests.setUp, test_app.AppTests.start, test_app.AppTests.ok,
                                       test_app.AppTests.change, test_app.AppTests.order)

    def widgets(self, at):
        for kind in ("selectbox", "radio", "segmented_control", "multiselect"):
            for w in getattr(at, kind):
                yield kind, w

    def assert_english(self, at, skip=("lang",)):
        seen = 0
        for kind, w in self.widgets(at):
            if w.key in skip:
                continue
            seen += 1
            values = w.value if isinstance(w.value, list) else [w.value]
            for text in [str(v) for v in values] + [str(o) for o in w.options]:
                self.assertIsNone(CJK.search(text), f"{kind} {w.key}: {text!r}")
        self.assertGreater(seen, 10)

    def test_defaults(self):
        self.assert_english(self.start(lang="en"))

    def test_dynamic_priority_options(self):
        for query in (dict(p1="3", p2="4", p3="4", p4="4", p5="4"), dict(p1="3", p2="0", p3="4", p4="4", p5="5"),
                      dict(p1="5", p2="3", p3="1", p4="2", p5="0"), dict(reinv="0"), dict(b="")):
            with self.subTest(query):
                self.assert_english(self.start(lang="en", **query))

    def test_after_an_edit(self):
        at = self.start(lang="en")
        for slot in (1, 2, 3, 4):
            for source in list(at.selectbox(key=f"p{slot}").options):
                at = self.change(at.selectbox(key=f"p{slot}").set_value(source))
                self.assert_english(at)

    def test_other_widgets(self):
        at = self.start(lang="en", type="0", jl="1", scen="1")
        self.assert_english(at)
        self.assert_english(self.change(at.radio(key="type").set_value(at.radio(key="type").options[1])))

    def test_switching_language_keeps_choices_and_links(self):
        at = self.start(lang="en", p1="3", p2="0", p3="4", p4="4", p5="5")
        en = self.order(at)
        self.assertEqual(en[0], "Sell main ETF")
        before = dict(at.query_params)
        at.segmented_control(key="lang").set_value("zh")
        at = self.ok(at.run())
        self.assertEqual(self.order(at), ["賣第一標的", "薪水（自掏腰包）", "（不使用）", "（不使用）", "賣第二標的"])
        self.assertEqual({k: v for k, v in at.query_params.items() if k != "lang"},
                         {k: v for k, v in before.items() if k != "lang"})
        at.segmented_control(key="lang").set_value("en")
        at = self.ok(at.run())
        self.assertEqual(self.order(at), en)
        self.assert_english(at)

    def test_the_stored_value_is_the_same_in_both_languages(self):
        zh = self.start(p1="3", p2="1", p3="4", p4="4", p5="4")
        en = self.start(lang="en", p1="3", p2="1", p3="4", p4="4", p5="4")
        for key in ("p1", "p2", "p3", "type", "scen", "dfreq"):
            self.assertEqual(zh.session_state[f"_c_{key}"], en.session_state[f"_c_{key}"])
        self.assertEqual(zh.query_params["p2"], en.query_params["p2"])


if __name__ == "__main__":
    unittest.main()
