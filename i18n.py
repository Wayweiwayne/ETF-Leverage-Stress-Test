"""Interface text in two languages. No Streamlit import at load time, so the engine can use it too.

Traditional Chinese is the default and the source text: every sentence is written once in Chinese in
the code, and that Chinese text is also its key. `t("中文原文", name=value)` returns it unchanged in
Chinese and looks up the English wording in `i18n_en.EN` when the language is English. A sentence
with no English entry comes back in Chinese (tests make sure that never happens for text the pages show).
The placeholders of the two versions must be the same; `test_i18n.py` checks that.

Messages that are stored or cached (errors, data notes) must not freeze one language. They are
`Msg` objects: a `str` that reads as the Chinese sentence, so existing code and tests see no
change, and that also remembers its template and parameters, so `t(message)` can render it again
in the language of the moment. `err()` does the same for exceptions (design D8: code + parameters,
Chinese message by default).

The language of a page run lives in `st.session_state["_lang"]`, set by `app.py` from the `lang`
address parameter. Outside Streamlit it is Chinese, unless `use()` says otherwise.
"""
import contextlib
import contextvars

LANGS = ("zh", "en")
DEFAULT = "zh"
STATE_KEY = "_lang"
LANG_NAMES = {"zh": "中文", "en": "English"}  # each language in its own words, whatever the page language

_forced = contextvars.ContextVar("i18n_forced", default=None)


def valid(value):
    return value if value in LANGS else DEFAULT


def lang():
    """The language of the running page: "zh" or "en"."""
    forced = _forced.get()
    if forced:
        return forced
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is None:
            return DEFAULT
        import streamlit as st
        return valid(st.session_state.get(STATE_KEY, DEFAULT))
    except Exception:  # noqa: BLE001 - no Streamlit, or no session: Chinese
        return DEFAULT


def set_lang(value):
    import streamlit as st
    st.session_state[STATE_KEY] = valid(value)


@contextlib.contextmanager
def use(value):
    """Force a language for a block (tests, report generation)."""
    token = _forced.set(valid(value))
    try:
        yield
    finally:
        _forced.reset(token)


def is_en():
    return lang() == "en"


def _english():
    from i18n_en import EN
    return EN


class Msg(str):
    """A sentence that reads as Chinese but can be shown in either language (see the module docstring)."""

    def __new__(cls, text, template=None, params=None):
        self = super().__new__(cls, text)
        self.template = template if template is not None else str(text)
        self.params = dict(params or {})
        return self

    def __reduce__(self):
        return (Msg, (str(self), self.template, self.params))


class LocalizedError(ValueError):
    """An error with a code (its Chinese template) and parameters; `str(exc)` is the Chinese message."""

    def __init__(self, template, params=None):
        self.template = template
        self.params = dict(params or {})
        super().__init__(_fill(template, self.params, "zh"))

    def __reduce__(self):
        return (LocalizedError, (self.template, self.params))


def _fill(template, params, language):
    if language == "en":
        template = _english().get(template, template)
    shown = {k: _shown(v, language) for k, v in params.items()}
    return template.format(**shown) if params else template


def _shown(value, language):
    """A parameter as it reads in `language` (messages inside messages are rendered too)."""
    if isinstance(value, (Msg, LocalizedError)):
        return _fill(value.template, value.params, language)
    if isinstance(value, str) and language == "en":
        return _english().get(value, value)
    return value


def t(text, **params):
    """`text` (Chinese source text, a Msg or a LocalizedError) in the current language, with `params` filled in."""
    if isinstance(text, (Msg, LocalizedError)):
        return _fill(text.template, {**text.params, **params}, lang())
    if not isinstance(text, str):
        return text
    return _fill(text, params, lang())


def msg(template, **params):
    """A storable message: Chinese text now, any language later via `t()`."""
    return Msg(_fill(template, params, "zh"), template, params)


def err(template, **params):
    """`raise err("中文訊息 {x}", x=1)`: a ValueError that carries its code and parameters."""
    return LocalizedError(template, params)


def as_msg(value):
    """An exception or text as a Msg (what is stored in results that get cached)."""
    if isinstance(value, Msg):
        return value
    if isinstance(value, LocalizedError):
        return Msg(str(value), value.template, value.params)
    return Msg(str(value))


def labeller():
    """`format_func` for widgets whose options are Chinese texts that double as stored values.

    It is tied to the language of the run that draws the widget (not looked up when it is called), so the
    labels it gives always match the options that run sent to the browser, also to the test runner.
    """
    language = lang()

    def label(value):
        return _fill(value, {}, language) if isinstance(value, str) else str(value)
    return label


# ---- amounts ----

def currency():
    return "NT$" if is_en() else "$"


def nt(value):
    """Whole dollars, cut off after the decimal point: $67,199 in Chinese, NT$67,199 in English."""
    return f"{currency()}{int(value):,}"


def nt_round(value):
    """Whole dollars, rounded."""
    return f"{currency()}{int(round(value)):,}"


def _trim(number):
    return f"{number:.1f}".rstrip("0").rstrip(".")


def nt_big(dollars):
    """English wording of a sum: NT$8.2 million from one million up, NT$820,000 below it."""
    if abs(dollars) >= 1_000_000:
        return f"NT${_trim(dollars / 1_000_000)} million"
    return f"NT${int(round(dollars)):,}"


def nt_short(dollars):
    """Axis and heat-map ticks in English: NT$8.2M from one million up, NT$820,000 below it."""
    if abs(dollars) >= 1_000_000:
        return f"NT${_trim(dollars / 1_000_000)}M"
    return f"NT${int(round(dollars)):,}"
