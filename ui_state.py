"""Input widgets whose values survive page switches and travel in the URL.

Every input is declared with a short key. The key doubles as the URL query parameter, so the
address bar always describes the current settings and can be shared as-is. Values that equal
the default are left out to keep links short. Anything read back from a URL is parsed and
range-checked before use; anything that fails is ignored in favour of the default.

All state lives in st.session_state, which is per browser session — nothing here is shared
between users.
"""
import streamlit as st

import i18n
from i18n import t

_STORE = "_settings"  # key -> serialised value, for every input that differs from its default


def begin(migrate=None):
    """Call at the top of the page, before any input is drawn.

    `migrate(settings)` may rewrite the settings read from an old link; it runs once per session,
    on the first load only.
    """
    if _STORE not in st.session_state:
        store = {k: st.query_params[k] for k in st.query_params}
        if migrate is not None:
            migrate(store)
        st.session_state[_STORE] = store


def pin(key, value):
    """Write `key` into the address bar even when it equals its default."""
    st.session_state[_STORE][key] = _fmt(value)


def end():
    """Call at the bottom of the page: publishes the current settings to the address bar."""
    wanted = dict(st.session_state[_STORE])
    if wanted != {k: st.query_params[k] for k in st.query_params}:
        st.query_params.from_dict(wanted)


def forget(*keys):
    """Drop inputs so they fall back to their defaults (safe to call from widget callbacks)."""
    for key in keys:
        st.session_state.pop(key, None)
        st.session_state[_STORE].pop(key, None)


def settings():
    return dict(st.session_state[_STORE])


def _seed(key, default, parse):
    if key in st.session_state:
        return
    value = default
    raw = st.session_state[_STORE].get(key)
    if raw is not None:
        try:
            value = parse(raw)
        except (ValueError, TypeError, IndexError):
            value = default
    st.session_state[key] = value


def _remember(key, raw, default_raw):
    if raw == default_raw:
        st.session_state[_STORE].pop(key, None)
    else:
        st.session_state[_STORE][key] = raw


def _kind(*values):
    return float if any(isinstance(v, float) for v in values) else int


def _snap(value, lo, hi, step, kind):
    if value != value:  # NaN
        raise ValueError("not a number")
    if hi is not None:
        value = min(value, hi)
    if lo is not None:
        value = max(value, lo)
    if step and lo is not None:
        value = lo + round((value - lo) / step) * step
        if hi is not None and value > hi:
            value -= step
    return int(round(value)) if kind is int else round(float(value), 8)


def _fmt(value):
    return f"{value:.10g}" if isinstance(value, float) else str(value)


def slider(key, label, lo, hi, default, step=None, **kwargs):
    kind = _kind(lo, hi, default, step)
    if lo >= hi:
        # A slider needs at least two positions; with one there is nothing to choose.
        st.caption(t("{label}：{v1}（目前只有這個選項）", label=label, v1=_fmt(kind(lo))))
        return kind(lo)
    default = _snap(default, lo, hi, step, kind)
    _seed(key, default, lambda raw: _snap(kind(float(raw)), lo, hi, step, kind))
    st.session_state[key] = _snap(st.session_state[key], lo, hi, step, kind)
    value = st.slider(label, lo, hi, step=step, key=key, **kwargs)
    _remember(key, _fmt(value), _fmt(default))
    return value


def range_slider(key, label, lo, hi, default, step=None, **kwargs):
    kind = _kind(lo, hi, step, *default)

    def clean(pair):
        a, b = sorted(_snap(kind(float(v)), lo, hi, step, kind) for v in pair)
        return (a, b)

    def parse(raw):
        parts = raw.split("~")
        if len(parts) != 2:
            raise ValueError(raw)
        return clean(parts)

    def fmt(pair):
        return f"{_fmt(pair[0])}~{_fmt(pair[1])}"

    default = clean(default)
    _seed(key, default, parse)
    st.session_state[key] = clean(st.session_state[key])
    value = st.slider(label, lo, hi, step=step, key=key, **kwargs)
    _remember(key, fmt(value), fmt(default))
    return value


def number(key, label, default, step, min_value=None, max_value=None, **kwargs):
    kind = _kind(default, step)
    _seed(key, default, lambda raw: _snap(kind(float(raw)), min_value, max_value, None, kind))
    st.session_state[key] = _snap(st.session_state[key], min_value, max_value, None, kind)
    value = st.number_input(label, min_value=min_value, max_value=max_value, step=step, key=key, **kwargs)
    _remember(key, _fmt(value), _fmt(default))
    return value


def checkbox(key, label, default, widget=None, **kwargs):
    def parse(raw):
        if raw not in ("0", "1"):
            raise ValueError(raw)
        return raw == "1"

    _seed(key, bool(default), parse)
    value = (widget or st.checkbox)(label, key=key, **kwargs)
    _remember(key, str(int(value)), str(int(bool(default))))
    return value


def choice(key, label, options, default, universe=None, widget=None, by_value=False, **kwargs):
    """Pick one of `options`.

    Links store the position of the choice within `universe` (the full, fixed list of
    possibilities) so they stay valid if labels are reworded; `by_value` stores the text
    itself, for lists that depend on data.

    The options are Chinese texts that double as stored values. The widget itself is given the texts
    as they read in the page language, so what it holds and shows is already translated and never
    depends on `format_func` (a browser that keeps a selected value while the option list changes
    would show the raw Chinese one). The caller still gets the stored (Chinese) value back, and the
    choice is kept in `_c_<key>` so a language switch re-labels it without changing it.
    """
    options = list(options)
    universe = list(universe) if universe is not None else options
    if default not in options:
        default = options[0]
    labels = [t(o) if isinstance(o, str) else o for o in options]
    if len(set(labels)) < len(labels):  # two options that read the same: keep them apart
        labels = list(options)
    to_label = dict(zip(options, labels))
    from_label = dict(zip(labels, options))
    canon_key = f"_c_{key}"
    if canon_key not in st.session_state:
        _seed(key, default, (lambda raw: raw) if by_value else (lambda raw: universe[int(raw)]))
        shown = st.session_state[key]
        current = from_label.get(shown, shown)
    else:
        shown = st.session_state.get(key)
        current = from_label.get(shown, st.session_state[canon_key])  # a label of another language: keep the choice
    if current not in options:
        current = default
    st.session_state[key] = to_label[current]
    st.session_state[canon_key] = current
    picked = (widget or st.selectbox)(label, labels, key=key, **kwargs)
    value = from_label[picked]
    st.session_state[canon_key] = value

    def fmt(v):
        return str(v) if by_value else str(universe.index(v))

    _remember(key, fmt(value), fmt(default))
    return value


def chosen(key, options):
    """The stored (Chinese) value of choice `key` from its widget state, which holds the page-language text.

    Meant for widget callbacks, which run before the page redraws the widget.
    """
    shown = st.session_state.get(key)
    for option in options:
        if shown == option or (isinstance(option, str) and shown == t(option)):
            return option
    return None


def text(key, label, default, clean, **kwargs):
    """Free text. `clean` normalises a value or raises ValueError; it guards what a link may inject."""
    _seed(key, default, clean)
    value = st.text_input(label, key=key, **kwargs)
    _remember(key, value, default)
    return value


def read_lang():
    """The page language before any widget is drawn: the switch if it was used, else the settings, else the link."""
    for raw in (st.session_state.get("lang"), st.session_state.get(_STORE, {}).get("lang"), st.query_params.get("lang")):
        if raw in i18n.LANGS:
            return raw
    return i18n.DEFAULT


def language_switch():
    """The language switch at the top of the sidebar (E-01..E-06). Changing it is not a settings change."""
    st.session_state["lang"] = read_lang()  # every run: a switch drawn on another page has its own widget state
    value = st.segmented_control(t("語言"), list(i18n.LANGS), key="lang", required=True, label_visibility="collapsed",
                                 format_func=i18n.LANG_NAMES.get)
    value = i18n.valid(value)
    if value != i18n.lang():
        i18n.set_lang(value)  # normally app.py has read it already; this covers a page run without it
    if _STORE in st.session_state:
        _remember("lang", value, i18n.DEFAULT)
    current = st.query_params.get("lang")      # the page may have no end() to publish the settings (the details page)
    if value == i18n.DEFAULT and current is not None:
        del st.query_params["lang"]
    elif value != i18n.DEFAULT and current != value:
        st.query_params["lang"] = value
    return value
