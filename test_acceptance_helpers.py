"""QA 驗收測試共用的工具：離線跑整個 App、收集畫面上看得到的文字、攔截報告與下載內容。

這個檔案沒有測試案例；test_acceptance_27_ui.py、test_acceptance_38.py 從這裡 import。
"""
import io
import json
import os
import re
from html.parser import HTMLParser
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.elements.widgets import button as st_button
from streamlit.testing.v1 import AppTest

import engine
import market_data
import report
from test_app import fake_history

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
DETAILS_PAGE = "pages/1_Model_Details.py"

# 不是給人看的 proto 欄位（識別碼、網址、圖表原始規格等）
_SKIP_FIELDS = {"id", "form_id", "url", "deferred_file_id", "spec", "theme", "config", "icon", "query_param_key",
                "anchor", "arrow_data", "data", "default", "type", "style", "selection_mode", "raw_values",
                "set_value", "shortcut", "icon_position", "click_mode", "label_visibility", "width_config",
                "height_config", "format", "step", "min", "max", "value", "default_value", "color"}
# 有文字內容的 proto 欄位（Markdown 的 body、警示框、標題…）
_TEXT_FIELDS_ALWAYS = {"body", "label", "help", "options", "placeholder", "delta", "value_text", "caption",
                       "text", "title"}


class AppHarness:
    """跟 test_app.AppTests 一樣的離線設定：假行情、沒有鏡像站、清掉快取。"""

    def setUp(self):
        st.cache_data.clear()
        for target, kwargs in (("market_data.MIRROR_URL", {"new": ""}),
                               ("market_data.load_history", {"side_effect": fake_history})):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        market_data._index_cache.update(at=float("-inf"), entries=None)

    def start(self, **query):
        at = AppTest.from_file(APP, default_timeout=180)
        for key, value in query.items():
            at.query_params[key] = value
        return self.ok(at.run())

    def ok(self, at):
        self.assertEqual([str(e.value) for e in at.exception], [])
        return at


class Recorder:
    """攔截一次 App 執行期間的報告、下載按鈕與引擎呼叫（只觀察，照常執行原本的函式）。"""

    def __init__(self):
        self.reports = []      # build_report 的 kwargs
        self.downloads = []    # (label, file_name, data)
        self.summaries = []    # (params, EngineResults)
        self._patches = []

    def __enter__(self):
        real_report, real_marshall, real_summary = report.build_report, st_button.marshall_file, engine.run_summary

        def build_report(**kwargs):
            self.reports.append(kwargs)
            return real_report(**kwargs)

        def marshall_file(coordinates, data, proto, mimetype, file_name=None):
            self.downloads.append((proto.label, file_name, data() if callable(data) else data))
            return real_marshall(coordinates, data, proto, mimetype, file_name)

        def run_summary(df, params):
            res = real_summary(df, params)
            self.summaries.append((params, res))
            return res

        self._patches = [patch("report.build_report", side_effect=build_report),
                         patch.object(st_button, "marshall_file", side_effect=marshall_file),
                         patch("engine.run_summary", side_effect=run_summary)]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False

    def last_report(self):
        return self.reports[-1] if self.reports else None

    def report_html(self):
        kwargs = self.last_report()
        return report.build_report(**kwargs) if kwargs else ""

    def csv_frames(self):
        """每個 CSV 下載的 (按鈕文字, 檔名, DataFrame)。"""
        frames = []
        for label, name, data in self.downloads:
            if name and name.lower().endswith(".csv"):
                raw = data.decode("utf-8-sig") if isinstance(data, bytes) else str(data)
                frames.append((label, name, pd.read_csv(io.StringIO(raw))))
        return frames


# ---------- 收集看得到的文字 ----------

def _repeated(desc):
    flag = getattr(desc, "is_repeated", None)
    return flag if flag is not None else desc.label == 3  # LABEL_REPEATED


def _proto_strings(msg, out, path=""):
    for desc, value in msg.ListFields():
        name = desc.name
        if name in _SKIP_FIELDS and name not in _TEXT_FIELDS_ALWAYS:
            continue
        if desc.type == desc.TYPE_MESSAGE:
            for v in (value if _repeated(desc) else [value]):
                if hasattr(v, "ListFields"):
                    _proto_strings(v, out, f"{path}.{name}")
        elif desc.type == desc.TYPE_STRING:
            values = value if _repeated(desc) else [value]
            out.extend((f"{path}.{name}", v) for v in values if v)


def figure_texts(spec):
    """Plotly 圖表上看得到的文字：標題、座標軸、圖例、格內文字、hover、色標、註解、類別刻度。"""
    if isinstance(spec, str):
        spec = json.loads(spec)
    out = []

    def add(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)
        elif isinstance(v, dict) and "text" in v:
            add(v["text"])

    layout = spec.get("layout", {})
    add(layout.get("title"))
    for key, axis in layout.items():
        if re.match(r"^[xy]axis\d*$", key) and isinstance(axis, dict):
            add(axis.get("title"))
            add(axis.get("ticktext"))
    add((layout.get("legend") or {}).get("title"))
    for ann in layout.get("annotations", []) or []:
        add(ann.get("text"))
    coloraxis = layout.get("coloraxis") or {}
    add((coloraxis.get("colorbar") or {}).get("title"))
    add((coloraxis.get("colorbar") or {}).get("ticktext"))
    for trace in spec.get("data", []):
        if trace.get("showlegend", True) is not False:
            add(trace.get("name"))
        for key in ("text", "hovertemplate", "texttemplate", "x", "y"):
            v = trace.get(key)
            if key in ("x", "y") and not (isinstance(v, list) and v and all(isinstance(i, str) for i in v)):
                continue
            add(v)
        bar = trace.get("colorbar") or {}
        add(bar.get("title"))
        add(bar.get("ticktext"))
    return out


def _frame_strings(frame):
    out = [str(c) for c in frame.columns] + [str(i) for i in frame.index if isinstance(i, str)]
    for col in frame.columns:
        out.extend(v for v in frame[col].tolist() if isinstance(v, str))
    return out


def visible_texts(at):
    """畫面上（主區與側欄）所有看得到的文字，回傳 [(元素類型, 文字)]。"""
    out = []

    def walk(node):
        kind = getattr(node, "type", "")
        if kind == "plotly_chart":
            out.extend((kind, t) for t in figure_texts(node.proto.spec))
        elif kind in ("table", "dataframe"):
            try:
                out.extend((kind, t) for t in _frame_strings(node.value))
            except Exception:  # noqa: BLE001 - a table AppTest cannot decode still has its proto strings
                pass
        proto = getattr(node, "proto", None)
        if proto is not None and hasattr(proto, "ListFields") and kind != "plotly_chart":
            found = []
            _proto_strings(proto, found)
            out.extend((kind, t) for _, t in found)
        for child in getattr(node, "children", {}).values():
            walk(child)

    walk(at._tree)
    return out


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for name, value in attrs:
            if name in ("title", "alt", "aria-label") and value:
                self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def report_texts(kwargs):
    """報告裡看得到的文字：HTML 去掉標籤與程式碼，再加上每張圖表上的文字。"""
    if not kwargs:
        return []
    parser = _TextOnly()
    parser.feed(report.build_report(**kwargs))
    texts = list(parser.parts)
    for _, figure, _ in kwargs.get("figures", []):
        texts.extend(figure_texts(figure.to_json() if hasattr(figure, "to_json") else figure))
    for heading, frame, note in kwargs.get("tables", []):
        texts.extend([heading, note] + _frame_strings(frame))
    return texts


def strip_markup(text):
    text = re.sub(r"https?://\S+", " ", str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"%\{[^}]*\}", " ", text)
