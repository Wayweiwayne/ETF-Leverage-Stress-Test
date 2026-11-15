"""Input widgets whose values survive page switches and travel in the URL.

Every input is declared with a short key. The key doubles as the URL query parameter, so the
address bar always describes the current settings and can be shared as-is. Values that equal
the default are left out to keep links short. Anything read back from a URL is parsed and
range-checked before use; anything that fails is ignored in favour of the default.

All state lives in st.session_state, which is per browser session — nothing here is shared
between users.
"""
import streamlit as st

_STORE = "_settings"  # key -> serialised value, for every input that differs from its default


def begin():
    """Call at the top of the page, before any input is drawn."""
    if _STORE not in st.session_state:
        st.session_state[_STORE] = {k: st.query_params[k] for k in st.query_params}


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
        st.caption(f"{label}：{_fmt(kind(lo))}（目前只有這個選項）")
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


def checkbox(key, label, default, **kwargs):
    def parse(raw):
        if raw not in ("0", "1"):
            raise ValueError(raw)
        return raw == "1"

    _seed(key, bool(default), parse)
    value = st.checkbox(label, key=key, **kwargs)
    _remember(key, str(int(value)), str(int(bool(default))))
    return value


def choice(key, label, options, default, universe=None, widget=None, by_value=False, **kwargs):
    """Pick one of `options`.

    Links store the position of the choice within `universe` (the full, fixed list of
    possibilities) so they stay valid if labels are reworded; `by_value` stores the text
    itself, for lists that depend on data.
    """
    options = list(options)
    universe = list(universe) if universe is not None else options
    if default not in options:
        default = options[0]
    _seed(key, default, (lambda raw: raw) if by_value else (lambda raw: universe[int(raw)]))
    if st.session_state[key] not in options:
        st.session_state[key] = default
    value = (widget or st.selectbox)(label, options, key=key, **kwargs)

    def fmt(v):
        return str(v) if by_value else str(universe.index(v))

    _remember(key, fmt(value), fmt(default))
    return value


def text(key, label, default, clean, **kwargs):
    """Free text. `clean` normalises a value or raises ValueError; it guards what a link may inject."""
    _seed(key, default, clean)
    value = st.text_input(label, key=key, **kwargs)
    _remember(key, value, default)
    return value
