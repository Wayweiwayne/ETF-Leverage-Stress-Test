"""A self-contained HTML report of one run: settings, results, tables and charts.

No Streamlit here: the page hands over plain values and plotly figures and gets a string back.
Everything that came from the user or the data source is escaped.
"""
from html import escape

_STYLE = """
body { font-family: -apple-system, "Segoe UI", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
       color: #1f2933; background: #fff; max-width: 1040px; margin: 0 auto; padding: 32px 20px 56px; line-height: 1.6; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 40px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e4e7eb; }
h3 { font-size: 15px; margin: 22px 0 8px; }
p.meta, p.note { color: #52606d; font-size: 13px; margin: 4px 0; }
p.caption { color: #52606d; font-size: 13px; margin: 6px 0 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin: 6px 0; }
th, td { border: 1px solid #e4e7eb; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f5f7fa; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.warn { background: #fffbea; border: 1px solid #f7d070; border-radius: 6px; padding: 8px 12px; font-size: 13px; margin: 6px 0; }
.footer { margin-top: 44px; padding-top: 14px; border-top: 1px solid #e4e7eb; color: #52606d; font-size: 12px; }
a { color: #0b69a3; word-break: break-all; }
@media (max-width: 720px) { .columns { grid-template-columns: 1fr; } }
@media print { h2 { break-after: avoid; } .figure, table { break-inside: avoid; } }
"""


def _pairs_table(rows):
    body = "".join(f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>" for label, value in rows)
    return f"<table>{body}</table>"


def _frame_table(frame):
    head = "<th></th>" + "".join(f"<th class='num'>{escape(str(c))}</th>" for c in frame.columns)
    body = "".join(
        f"<tr><th>{escape(str(index))}</th>" + "".join(f"<td class='num'>{escape(str(v))}</td>" for v in row) + "</tr>"
        for index, row in zip(frame.index, frame.itertuples(index=False)))
    return f"<table><tr>{head}</tr>{body}</table>"


def build_report(*, title, version, generated, share_url, settings, data_notes, warnings, summaries,
                 tables, figures, disclaimer, source_url, closing_notes=()):
    """Return the report as one HTML document.

    settings   -- [(label, value)] describing the run
    data_notes -- [text] about the market data used and how it was prepared
    warnings   -- [text] the page showed as cautions
    summaries  -- [(heading, [(label, value)])], laid out side by side
    tables     -- [(heading, DataFrame of display strings, caption)]
    figures    -- [(heading, plotly figure, caption)]; charts load plotly from its CDN
    closing_notes -- [text] added to the footer
    """
    parts = [
        "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>",
        f"<h1>{escape(title)}</h1>",
        f"<p class='meta'>版本 {escape(version)}｜產生時間 {escape(generated)}</p>",
    ]
    if share_url:
        parts.append(f"<p class='meta'>用這個連結可以重現同一組設定：<a href='{escape(share_url, quote=True)}'>"
                     f"{escape(share_url)}</a></p>")

    parts.append("<h2>這次的設定</h2>" + _pairs_table(settings))

    parts.append("<h2>主要結果</h2><div class='columns'>")
    for heading, rows in summaries:
        parts.append(f"<div><h3>{escape(heading)}</h3>{_pairs_table(rows)}</div>")
    parts.append("</div>")
    parts.extend(f"<div class='warn'>{escape(text)}</div>" for text in warnings)

    for heading, frame, caption in tables:
        parts.append(f"<h3>{escape(heading)}</h3>{_frame_table(frame)}")
        if caption:
            parts.append(f"<p class='caption'>{escape(caption)}</p>")

    if figures:
        parts.append("<h2>圖表</h2><p class='note'>圖表需要連上網路才會顯示（會從 plotly 的 CDN 載入繪圖程式）；滑鼠移上去可以看數值。</p>")
    for position, (heading, figure, caption) in enumerate(figures):
        chart = figure.to_html(full_html=False, include_plotlyjs="cdn" if position == 0 else False,
                               config={"displaylogo": False})
        parts.append(f"<div class='figure'><h3>{escape(heading)}</h3>{chart}")
        if caption:
            parts.append(f"<p class='caption'>{escape(caption)}</p>")
        parts.append("</div>")

    if data_notes:
        parts.append("<h2>使用的資料</h2><ul>" + "".join(f"<li>{escape(text)}</li>" for text in data_notes) + "</ul>")

    parts.append("<div class='footer'>" + "".join(f"<p>{escape(text)}</p>" for text in closing_notes)
                 + f"<p>{escape(disclaimer)}</p>"
                 f"<p>本程式為自由軟體，以 AGPL-3.0 授權，不提供任何擔保。原始碼："
                 f"<a href='{escape(source_url, quote=True)}'>{escape(source_url)}</a></p></div>")
    parts.append("</body></html>")
    return "".join(parts)
