"""Unit tests for ui_state.py (sprint 6-3): pure helpers directly, widgets through minimal AppTest scripts."""
import unittest

from streamlit.testing.v1 import AppTest

import i18n
import ui_state as ui

HEAD = "import streamlit as st\nimport ui_state as ui\nui.begin(%s)\n"
TAIL = "\nui.end()\n"


def run(body, query=None, migrate=None, state=None, end=True):
    """Run `body` (page code) as a Streamlit script with the given address parameters."""
    script = HEAD % ("migrate" if migrate else "") + (migrate or "") + body + (TAIL if end else "")
    if migrate:
        script = script.replace("ui.begin(migrate)\n" + migrate, migrate + "\nui.begin(migrate)\n")
    at = AppTest.from_string(script, default_timeout=30)
    for k, v in (query or {}).items():
        at.query_params[k] = v
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def params(at):
    return {k: v[0] if isinstance(v, list) else v for k, v in dict(at.query_params).items()}


class PureHelperTests(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(ui._fmt(3), "3")
        self.assertEqual(ui._fmt(2.5), "2.5")
        self.assertEqual(ui._fmt(2.0), "2")
        self.assertEqual(ui._fmt(0.1 + 0.2), "0.3")

    def test_kind(self):
        self.assertIs(ui._kind(1, 2, 3), int)
        self.assertIs(ui._kind(1, 2.0), float)

    def test_snap_clamps(self):
        self.assertEqual(ui._snap(500, 0, 10, None, int), 10)
        self.assertEqual(ui._snap(-5, 0, 10, None, int), 0)
        self.assertEqual(ui._snap(7.4, None, None, None, int), 7)
        self.assertEqual(ui._snap(7.4, 0.0, None, None, float), 7.4)

    def test_snap_step(self):
        self.assertEqual(ui._snap(7, 0, 100, 5, int), 5)
        self.assertEqual(ui._snap(8, 0, 100, 5, int), 10)
        self.assertEqual(ui._snap(0.34, 0.0, 1.0, 0.1, float), 0.3)
        # rounding up past the top steps back down
        self.assertEqual(ui._snap(9, 0, 9, 6, int), 6)

    def test_snap_rejects_nan(self):
        with self.assertRaises(ValueError):
            ui._snap(float("nan"), 0, 10, None, int)


class SeedAndRememberTests(unittest.TestCase):
    def test_default_not_in_url(self):
        at = run('ui.slider("a", "A", 0, 10, 5)')
        self.assertEqual(params(at), {})
        self.assertEqual(at.slider(key="a").value, 5)

    def test_changed_value_in_url_and_back(self):
        at = run('ui.slider("a", "A", 0, 10, 5)')
        at.slider(key="a").set_value(8).run()
        self.assertEqual(params(at), {"a": "8"})
        at.slider(key="a").set_value(5).run()
        self.assertEqual(params(at), {})

    def test_url_value_is_read(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "3"})
        self.assertEqual(at.slider(key="a").value, 3)
        self.assertEqual(params(at), {"a": "3"})

    def test_url_equal_to_default_is_dropped(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "5"})
        self.assertEqual(params(at), {})

    def test_invalid_values_fall_back_to_default(self):
        for bad in ("abc", "", "nan", "1e999x"):
            with self.subTest(bad):
                at = run('ui.slider("a", "A", 0, 10, 5)', {"a": bad})
                self.assertEqual(at.slider(key="a").value, 5)
                self.assertEqual(params(at), {})

    def test_infinity_in_url_falls_back(self):
        """?a=inf on an int slider used to raise OverflowError from _seed and crash the page; it now falls back to the default."""
        for bad in ("inf", "-inf", "1e999"):
            with self.subTest(bad):
                at = run('ui.slider("a", "A", 0, 10, 5)', {"a": bad})
                self.assertEqual(at.slider(key="a").value, 5)

    def test_out_of_range_is_clamped(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "999"})
        self.assertEqual(at.slider(key="a").value, 10)
        self.assertEqual(params(at), {"a": "10"})
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "-4"})
        self.assertEqual(at.slider(key="a").value, 0)

    def test_slider_step_snap_from_url(self):
        at = run('ui.slider("a", "A", 0, 100, 50, step=5)', {"a": "52"})
        self.assertEqual(at.slider(key="a").value, 50)

    def test_float_slider(self):
        at = run('ui.slider("a", "A", 0.0, 1.0, 0.5, step=0.1)', {"a": "0.74"})
        self.assertAlmostEqual(at.slider(key="a").value, 0.7)
        self.assertEqual(params(at), {"a": "0.7"})

    def test_degenerate_slider_returns_lo(self):
        at = run('v = ui.slider("a", "A", 3, 3, 3)\nst.write(f"v={v}")')
        self.assertEqual(len(at.slider), 0)
        self.assertIn("v=3", at.markdown[-1].value)
        self.assertEqual(params(at), {})

    def test_default_outside_range_is_snapped(self):
        at = run('ui.slider("a", "A", 0, 10, 50)')
        self.assertEqual(at.slider(key="a").value, 10)
        self.assertEqual(params(at), {})

    def test_settings_and_forget(self):
        at = run('ui.slider("a", "A", 0, 10, 5)\nst.session_state["seen"] = ui.settings()', {"a": "2"})
        self.assertEqual(at.session_state["seen"], {"a": "2"})
        at = run('ui.slider("a", "A", 0, 10, 5)\nui.forget("a")\nst.session_state["after"] = ui.settings()', {"a": "2"},
                 end=False)
        self.assertEqual(at.session_state["after"], {})

    def test_unknown_url_keys_are_kept(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"zzz": "1"})
        self.assertEqual(params(at), {"zzz": "1"})


class RangeSliderTests(unittest.TestCase):
    BODY = 'st.session_state["v"] = ui.range_slider("r", "R", 0, 10, (2, 8))'

    def test_default_not_in_url(self):
        at = run(self.BODY)
        self.assertEqual(at.slider(key="r").value, (2, 8))
        self.assertEqual(params(at), {})

    def test_from_url(self):
        at = run(self.BODY, {"r": "3~6"})
        self.assertEqual(at.slider(key="r").value, (3, 6))
        self.assertEqual(params(at), {"r": "3~6"})

    def test_reversed_and_clamped(self):
        at = run(self.BODY, {"r": "9~-3"})
        self.assertEqual(at.slider(key="r").value, (0, 9))

    def test_malformed_falls_back(self):
        for bad in ("5", "1~2~3", "a~b", ""):
            with self.subTest(bad):
                at = run(self.BODY, {"r": bad})
                self.assertEqual(at.slider(key="r").value, (2, 8))
                self.assertEqual(params(at), {})


class NumberTests(unittest.TestCase):
    BODY = 'ui.number("n", "N", 1.5, 0.5, min_value=0.0, max_value=10.0)'

    def test_default_and_url(self):
        self.assertEqual(params(run(self.BODY)), {})
        at = run(self.BODY, {"n": "4"})
        self.assertEqual(at.number_input(key="n").value, 4.0)
        self.assertEqual(params(at), {"n": "4"})

    def test_clamped_and_invalid(self):
        self.assertEqual(run(self.BODY, {"n": "99"}).number_input(key="n").value, 10.0)
        self.assertEqual(run(self.BODY, {"n": "-1"}).number_input(key="n").value, 0.0)
        at = run(self.BODY, {"n": "x"})
        self.assertEqual(at.number_input(key="n").value, 1.5)
        self.assertEqual(params(at), {})

    def test_int_number(self):
        at = run('ui.number("n", "N", 3, 1, min_value=1, max_value=9)', {"n": "20"})
        self.assertEqual(at.number_input(key="n").value, 9)

    def test_edit_updates_url(self):
        at = run(self.BODY)
        at.number_input(key="n").set_value(2.5).run()
        self.assertEqual(params(at), {"n": "2.5"})


class CheckboxTests(unittest.TestCase):
    def test_checkbox(self):
        body = 'ui.checkbox("c", "C", True)'
        at = run(body)
        self.assertTrue(at.checkbox(key="c").value)
        self.assertEqual(params(at), {})
        at = run(body, {"c": "0"})
        self.assertFalse(at.checkbox(key="c").value)
        self.assertEqual(params(at), {"c": "0"})
        at = run(body, {"c": "yes"})
        self.assertTrue(at.checkbox(key="c").value)
        self.assertEqual(params(at), {})
        at = run('ui.checkbox("c", "C", False)', {"c": "1"})
        self.assertTrue(at.checkbox(key="c").value)

    def test_toggle_widget(self):
        at = run('ui.checkbox("t", "T", False, widget=st.toggle)', {"t": "1"})
        self.assertTrue(at.toggle(key="t").value)
        self.assertEqual(params(at), {"t": "1"})
        at.toggle(key="t").set_value(False).run()
        self.assertEqual(params(at), {})


class ChoiceTests(unittest.TestCase):
    BODY = ('v = ui.choice("k", "K", ["甲", "乙", "丙"], "乙")\n'
            'st.session_state["got"] = v')

    def test_default_not_in_url(self):
        at = run(self.BODY)
        self.assertEqual(at.session_state["got"], "乙")
        self.assertEqual(params(at), {})

    def test_url_is_position_in_universe(self):
        at = run(self.BODY, {"k": "2"})
        self.assertEqual(at.session_state["got"], "丙")
        self.assertEqual(params(at), {"k": "2"})
        self.assertEqual(at.session_state["_c_k"], "丙")

    def test_invalid_index_falls_back(self):
        for bad in ("9", "-9x", "abc", ""):
            with self.subTest(bad):
                at = run(self.BODY, {"k": bad})
                self.assertEqual(at.session_state["got"], "乙")
                self.assertEqual(params(at), {})

    def test_default_not_in_options_becomes_first(self):
        at = run('st.session_state["got"] = ui.choice("k", "K", ["甲", "乙"], "無")')
        self.assertEqual(at.session_state["got"], "甲")

    def test_universe_keeps_index_stable(self):
        body = ('st.session_state["got"] = ui.choice("k", "K", ["乙", "丙"], "乙", universe=["甲", "乙", "丙"])')
        at = run(body, {"k": "2"})
        self.assertEqual(at.session_state["got"], "丙")
        at.selectbox(key="k").set_value("乙").run()
        self.assertEqual(params(at), {})

    def test_by_value(self):
        body = 'st.session_state["got"] = ui.choice("k", "K", ["a", "b"], "a", by_value=True)'
        at = run(body, {"k": "b"})
        self.assertEqual(at.session_state["got"], "b")
        self.assertEqual(params(at), {"k": "b"})
        at = run(body, {"k": "zzz"})        # an unknown value is ignored
        self.assertEqual(at.session_state["got"], "a")

    def test_edit_updates_url(self):
        at = run(self.BODY)
        at.selectbox(key="k").set_value("丙").run()
        self.assertEqual(at.session_state["got"], "丙")
        self.assertEqual(params(at), {"k": "2"})

    def test_language_switch_keeps_choice(self):
        # i18n.t falls back to the Chinese text when there is no English entry, so use a known sentence.
        from i18n_en import EN
        opts = [k for k in EN if "{" not in k and len(k) < 12][:3]
        self.assertEqual(len(opts), 3)
        body = (f'opts = {opts!r}\n'
                'st.session_state["_lang"] = st.session_state.get("want", "zh")\n'
                'st.session_state["got"] = ui.choice("k", "K", opts, opts[0])')
        at = run(body, {"k": "1"}, state={"want": "zh"})
        self.assertEqual(at.session_state["got"], opts[1])
        self.assertEqual(at.selectbox(key="k").value, opts[1])
        at.session_state["want"] = "en"
        at.run()
        self.assertEqual(at.session_state["got"], opts[1])
        self.assertEqual(at.session_state["_c_k"], opts[1])
        self.assertEqual(at.selectbox(key="k").value, i18n_t_en(opts[1]))
        self.assertEqual(params(at), {"k": "1"})
        at.session_state["want"] = "zh"
        at.run()
        self.assertEqual(at.selectbox(key="k").value, opts[1])
        self.assertEqual(at.session_state["got"], opts[1])

    def test_duplicate_labels_fall_back_to_raw_options(self):
        # two different Chinese options that read the same in English must stay distinguishable
        body = ('st.session_state["_lang"] = "en"\n'
                'st.session_state["got"] = ui.choice("k", "K", ["破產", "已破產"], "已破產")')
        at = run(body)
        self.assertEqual(sorted(at.selectbox(key="k").options), sorted(["破產", "已破產"]))
        self.assertEqual(at.session_state["got"], "已破產")

    def test_chosen(self):
        at = run('st.session_state["k"] = "乙"\nst.session_state["r"] = ui.chosen("k", ["甲", "乙"])\n'
                 'st.session_state["n"] = ui.chosen("k", ["甲", "丙"])', end=False)
        self.assertEqual(at.session_state["r"], "乙")
        self.assertIsNone(at.session_state["n"])

    def test_chosen_translated(self):
        from i18n_en import EN
        key = next(k for k in EN if "{" not in k)
        body = (f'st.session_state["_lang"] = "en"\nst.session_state["k"] = ui.t({key!r}) if hasattr(ui, "t") else ""\n'
                f'st.session_state["r"] = ui.chosen("k", [{key!r}])')
        at = run(body, end=False)
        self.assertEqual(at.session_state["r"], key)


def i18n_t_en(text):
    with i18n.use("en"):
        return i18n.t(text)


class PinAndMigrateTests(unittest.TestCase):
    def test_pin_writes_default_value(self):
        at = run('ui.slider("a", "A", 0, 10, 5)\nui.pin("a", 5)')
        self.assertEqual(params(at), {"a": "5"})

    def test_pin_float_format(self):
        at = run('ui.pin("x", 2.0)\nui.pin("y", 0.25)')
        self.assertEqual(params(at), {"x": "2", "y": "0.25"})

    def test_pin_stays_while_value_is_default(self):
        body = 'v = ui.number("inc", "I", 0.0, 0.5, min_value=0.0)\nui.pin("inc", v)'
        at = run(body)
        self.assertEqual(params(at), {"inc": "0"})
        at.number_input(key="inc").set_value(1.0).run()
        self.assertEqual(params(at), {"inc": "1"})

    MIG = 'def migrate(s):\n    if "loan" in s and "inc" not in s:\n        s["inc"] = "0"\n'

    def test_migrate_runs_on_old_link(self):
        body = 'ui.number("inc", "I", 3.0, 0.5, min_value=0.0, max_value=100.0)'
        at = run(body, {"loan": "500"}, migrate=self.MIG)
        self.assertEqual(at.number_input(key="inc").value, 0.0)
        self.assertEqual(params(at)["inc"], "0")

    def test_migrate_untouched_for_new_link(self):
        body = 'ui.number("inc", "I", 3.0, 0.5, min_value=0.0, max_value=100.0)'
        at = run(body, {"loan": "500", "inc": "4"}, migrate=self.MIG)
        self.assertEqual(at.number_input(key="inc").value, 4.0)

    def test_migrate_only_on_first_load(self):
        body = 'ui.number("inc", "I", 3.0, 0.5, min_value=0.0, max_value=100.0)'
        at = run(body, {"loan": "500"}, migrate=self.MIG)
        at.number_input(key="inc").set_value(2.0).run()
        self.assertEqual(at.number_input(key="inc").value, 2.0)
        self.assertEqual(params(at)["inc"], "2")


class BeginEndTests(unittest.TestCase):
    def test_begin_reads_url_once(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "7"})
        self.assertEqual(at.session_state["_settings"], {"a": "7"})
        at.query_params["a"] = "1"          # a later address change does not override the session
        at.run()
        self.assertEqual(at.slider(key="a").value, 7)

    def test_end_publishes_only_when_different(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "7"})
        self.assertEqual(params(at), {"a": "7"})

    def test_end_removes_params_back_at_default(self):
        at = run('ui.slider("a", "A", 0, 10, 5)', {"a": "7"})
        at.slider(key="a").set_value(5).run()
        self.assertEqual(params(at), {})

    def test_forget_resets_to_default(self):
        body = ('ui.slider("a", "A", 0, 10, 5)\n'
                'st.button("reset", key="reset", on_click=ui.forget, args=("a",))')
        at = run(body, {"a": "7"})
        at.button(key="reset").click().run()
        self.assertEqual(at.slider(key="a").value, 5)
        self.assertEqual(params(at), {})


class TextTests(unittest.TestCase):
    CLEAN = ('def clean(v):\n    v = v.strip().upper()\n    if not v.isalnum():\n        raise ValueError(v)\n    return v\n')

    def test_text(self):
        body = self.CLEAN + 'ui.text("tk", "T", "AB", clean)'
        self.assertEqual(params(run(body)), {})
        at = run(body, {"tk": "cd"})
        self.assertEqual(at.text_input(key="tk").value, "CD")
        at = run(body, {"tk": "a b!"})
        self.assertEqual(at.text_input(key="tk").value, "AB")
        self.assertEqual(params(at), {})


class LanguageSwitchTests(unittest.TestCase):
    BODY = ('ui.slider("a", "A", 0, 10, 5)\n'
            'st.session_state["v"] = ui.language_switch()\n'
            'st.session_state["rl"] = ui.read_lang()')

    def test_default_language_not_in_url(self):
        at = run(self.BODY)
        self.assertEqual(at.session_state["v"], "zh")
        self.assertEqual(params(at), {})

    def test_url_language(self):
        at = run(self.BODY, {"lang": "en"})
        self.assertEqual(at.session_state["v"], "en")
        self.assertEqual(params(at), {"lang": "en"})

    def test_invalid_language_ignored(self):
        at = run(self.BODY, {"lang": "fr"})
        self.assertEqual(at.session_state["v"], "zh")
        self.assertNotIn("lang", params(at))

    def test_switch_and_back(self):
        at = run(self.BODY)
        at.session_state["lang"] = "en"
        at.run()
        self.assertEqual(at.session_state["v"], "en")
        self.assertEqual(params(at).get("lang"), "en")
        at.session_state["lang"] = "zh"
        at.run()
        self.assertNotIn("lang", params(at))

    def test_read_lang_priority(self):
        at = run('st.session_state["rl"] = ui.read_lang()', {"lang": "en"}, end=False)
        self.assertEqual(at.session_state["rl"], "en")
        at = run('st.session_state["rl"] = ui.read_lang()', {"lang": "en"}, state={"lang": "zh"}, end=False)
        self.assertEqual(at.session_state["rl"], "zh")

    def test_switch_without_begin(self):
        script = "import streamlit as st\nimport ui_state as ui\nst.session_state['v'] = ui.language_switch()\n"
        at = AppTest.from_string(script, default_timeout=30)
        at.query_params["lang"] = "en"
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["v"], "en")
        self.assertEqual(params(at), {"lang": "en"})


if __name__ == "__main__":
    unittest.main()
