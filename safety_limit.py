"""Safety limit: the most that can be borrowed and the least that must be paid in each month.

Runs the engine's solver and sensitivity grid for one set of settings and turns the outcome into
what the page and the report show: metric values, sentences, captions, the risk map and its
table. No Streamlit here; the page decides where each piece goes.

Sentences carry **bold** markers; `markdown()` makes them safe for Streamlit (a pair of dollar
signs would otherwise be read as a formula) and `plain()` strips them for the report.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

import engine

TARGETS = ("1", "5", "10")  # percent; a link stores the number itself
DEFAULT_TARGET = "5"

PRINCIPAL_STEP = 100_000
PRINCIPAL_CEILING = 100_000_000
SALARY_HI, SALARY_STEP = 500_000, 1_000

MULTIPLES = (0.5, 0.75, 1, 1.25, 1.5, 2)
ZERO_SALARY_AXIS = (0, 5_000, 10_000, 20_000, 30_000, 50_000)

BAND_COLORS = ("#1c5cab", "#86b6ef", "#f0938f", "#b8322f")
BAND_NAMES = ("很安全", "達標", "超過", "危險")

HEADER = "🛡️ 安全邊界：最多能借多少？"
ANCHOR = "safe-limit"
INTRO = ("用蒙地卡羅模擬反過來找：其他設定都不變的情況下，貸款本金最多可以多少、每月最少要能自掏多少，"
         "破產機率才不會超過你能接受的上限。要跑幾十次模擬，所以按按鈕才會計算。")
TARGET_LABEL = "你能接受的破產機率最多多少"
TARGET_HELP = "例如選 5%，就是要求「每 20 種可能的未來裡，最多只有 1 種會繳不出貸款」。選越低越保守。"
BUTTON = "🛡️ 計算安全邊界"
NOT_YET = "還沒有計算。按「計算安全邊界」開始。"
NEEDS_RUN = "請先按「開始計算」更新上方結果，再計算安全邊界。"
NO_MONTE_CARLO = "歷史資料不到 2 個月，無法做蒙地卡羅模擬，所以也無法計算安全邊界。"
STALE = "⚠️ 設定已變更，下面的安全邊界是用舊設定算的。按「計算安全邊界」重新計算。"
STALE_TARGET = "⚠️ 你改了能接受的破產機率，下面還是 {t} 的結果。按「計算安全邊界」重新計算。"
NO_SALARY = "你沒有把「薪水（自掏腰包）」排進還款順位，所以每月自掏多少都不影響結果，這一項不計算。"
RANDOM_SEED = "你關閉了「固定亂數」，安全邊界固定用同一組抽樣計算，所以數字可能和上方的破產機率略有不同。"
MAP_TITLE = "破產機率地圖：借多少 × 每月自掏多少"
MAP_NOTE = ("怎麼看這張圖：每一格是「只把貸款本金換成左邊的數字、每月最多自掏換成下面的數字，其他設定都不變」時的破產機率。"
            "◆ 是你目前的設定。藍色是在你選的上限（{t}）以內，紅色是超過；顏色越深，離上限越遠。"
            "往上（借越多）、往左（自掏越少）通常越危險。")
MAP_NOTE_2 = "安全邊界只看蒙地卡羅模擬的破產機率，不看歷史回測。它是用歷史行情重新組合出來的估計，不是保證。"
MAP_NOTE_FEE = "「—」的格子：貸款本金不比開辦費多，借到的錢扣掉開辦費就沒了，無法計算。"
MAP_NOTE_NO_SALARY = "你沒有把薪水排進還款順位，所以地圖上每一格幾乎都一樣：借多少、每月自掏多少，都不太影響破產機率。"
MAP_NOTE_ZERO_SALARY = ("你的每月最多自掏是 0，所以最左邊「$0」那一欄上下幾乎都一樣：不自掏的話，借多少都不太影響破產機率。"
                        "往右看，是每月補一點錢的效果。")
BLANK_COLOR, BLANK_TEXT_COLOR = "#a3a29c", "#0b0b0b"
NO_SUPPORT = ("你沒有用薪水補貼還款。這時借多借少，每月還款和買進的資產都等比例變大或變小，破產機率幾乎不變，"
              "所以「最多可以借」不是「{hi} 萬以上」就是「不到 {lo} 萬」，不會落在中間。")
ALL_MEET_SCALES = ("借越多，每月還款和買進的資產都會等比例變大，每月自掏那筆固定的錢就越不夠看，所以破產機率不會一直升高，"
                   "而是慢慢接近「完全不自掏」時的水準；這個水準在 {t} 以下，所以整個搜尋範圍都達標。")
ALL_MEET_NO_SUPPORT = "這次的破產機率在 {t} 以下，所以整個搜尋範圍都達標。"
LOW_IS_NOT_SAFE = "破產機率低不代表風險小：借越多，一旦出事賠得也越多。"
NONE_MEET_NO_SUPPORT = "這次的破產機率超過 {t}，調整本金沒有用；要從利率、年限、還款的順序或每月自掏的錢下手。"
NONE_MEET = "問題可能不在借多少，而是利率、年限、每月自掏的錢或還款的順序；可以看看下面的地圖。"
TABLE_TITLE = "用表格看這張地圖"
STEPS = ("（1/3）找最多能借多少…", "（2/3）找每月最少要自掏多少…", "（3/3）畫破產機率地圖（{n} 格）…")
CURRENT_MARK = "◆ 目前"


def principal_bounds(principal, loan_fee):
    """Search range for the loan: from the first multiple of 100,000 above the fee to ten times the loan."""
    lo = max(PRINCIPAL_STEP, (int(loan_fee) // PRINCIPAL_STEP + 1) * PRINCIPAL_STEP)
    hi = max(lo, min(principal * 10, PRINCIPAL_CEILING))
    return float(lo), float(hi)


def _round_half_up(value):
    return int(np.floor(value + 0.5))


def _unique(values):
    return list(dict.fromkeys(values))


def map_axes(principal, salary_cap):
    """Loans and monthly caps for the risk map, in whole dollars; repeats from rounding are dropped."""
    principals = _unique(float(_round_half_up(principal * m)) for m in MULTIPLES)
    caps = ZERO_SALARY_AXIS if salary_cap == 0 else (_round_half_up(salary_cap * m) for m in MULTIPLES)
    return principals, _unique(float(c) for c in caps)


def compute(df, params, target, on_step=None):
    """Find both limits and the risk map for `params` at a target of `target` percent.

    `on_step(fraction, text)` is called before each stage. The result holds everything needed
    to show it again later, after the settings have moved on.
    """
    step = on_step or (lambda fraction, text: None)
    rate = int(target) / 100
    lo, hi = principal_bounds(params.principal, params.loan_fee)
    step(0.0, STEPS[0])
    principal = engine.solve_for(df, params, "principal", rate, lo, hi, PRINCIPAL_STEP)
    salary = None
    if engine.SALARY in params.source_order:
        step(1 / 3, STEPS[1])
        salary = engine.solve_for(df, params, "salary_cap", rate, 0.0, float(SALARY_HI), SALARY_STEP)
    principals, caps = map_axes(params.principal, params.salary_cap)
    step(2 / 3, STEPS[2].format(n=len(principals) * len(caps)))
    # A loan the fee would swallow whole cannot be simulated; its row stays empty.
    usable = [p for p in principals if p > params.loan_fee]
    grid = pd.DataFrame(np.nan, index=principals, columns=caps)
    if usable:
        grid.loc[usable] = engine.sensitivity_grid(df, params, usable, caps, mc_paths=params.mc_paths).to_numpy()
    return {"target": str(target), "paths": int(params.mc_paths), "seed_is_random": params.seed is None,
            "salary_in_order": engine.SALARY in params.source_order,
            "principal": principal, "salary": salary, "lo": lo, "hi": hi,
            "current_principal": float(params.principal), "current_salary": float(params.salary_cap), "grid": grid}


# ---- formatting ----

def target_text(target):
    return f"{target}%"


def ruin_text(rate, target):
    """A ruin rate to one decimal, or two when it sits within 0.1 point of the target."""
    if rate != rate:
        return "—"
    close = abs(rate - int(target) / 100) < 0.001 - 1e-12
    return f"{rate * 100:.2f}%" if close else f"{rate * 100:.1f}%"


def wan(value):
    """An amount in units of 10,000 (萬), without trailing zeros."""
    text = f"{value / 10_000:,.4f}".rstrip("0").rstrip(".")
    return text or "0"


def dollars(value):
    return f"${int(round(value)):,}"


def markdown(text):
    return text.replace("$", "\\$")


def plain(text):
    return text.replace("**", "")


def _view(label, value, sentence, style, captions=(), delta=None, delta_color="normal"):
    return {"label": label, "value": value, "delta": delta, "delta_color": delta_color, "sentence": sentence,
            "style": style, "captions": list(captions)}


def has_salary_support(record):
    """Whether salary can top up payments at all: it is a repayment source and its cap is above zero."""
    return record["salary_in_order"] and record["current_salary"] > 0


def principal_view(record):
    """Metric, sentence (with its alert style) and captions for the most that can be borrowed."""
    res, t = record["principal"], target_text(record["target"])
    cur, r, n = record["current_principal"], ruin_text(record["principal"].ruin_rate, record["target"]), record["paths"]
    no_support = NO_SUPPORT.format(hi=wan(record["hi"]), lo=wan(record["lo"]))
    if res.status == "all_meet":
        caption = (ALL_MEET_SCALES.format(t=t) if has_salary_support(record)
                   else no_support + ALL_MEET_NO_SUPPORT.format(t=t))
        return _view("最多可以借", f"{wan(record['hi'])} 萬以上",
                     f"以目前其他設定，就算借到搜尋上限 **{wan(record['hi'])} 萬**，破產機率也只有 {r}，"
                     f"仍在 {t} 以下（你目前設定 {wan(cur)} 萬）。", "success", [caption + LOW_IS_NOT_SAFE])
    if res.status == "none_meet":
        caption = NONE_MEET if has_salary_support(record) else no_support + NONE_MEET_NO_SUPPORT.format(t=t)
        return _view("最多可以借", f"不到 {wan(record['lo'])} 萬",
                     f"以目前其他設定，就算只借 **{wan(record['lo'])} 萬**，破產機率也有 {r}，達不到 {t} 以下。", "error",
                     [caption])
    value, diff = res.value, res.value - cur
    captions = [f"借 {wan(value)} 萬時，破產機率約 {r}（{n:,} 次模擬）。"]
    if cur > value:
        captions.append(f"⚠️ 你目前設定的 {wan(cur)} 萬已經超過這個上限。")
    delta, color = (("和目前相同", "off") if diff == 0
                    else (f"{'+' if diff > 0 else '-'}{wan(abs(diff))} 萬（比目前）", "normal"))
    return _view("最多可以借", f"{wan(value)} 萬",
                 f"以目前其他設定，要讓破產機率在 {t} 以下，最多可以借 **{wan(value)} 萬**（你目前設定 {wan(cur)} 萬）。",
                 "success" if cur <= value else "warning", captions, delta, color)


def salary_view(record):
    """Like principal_view for the least monthly out-of-pocket cap; None when it was not searched."""
    res = record["salary"]
    if res is None:
        return None
    t, cur, n = target_text(record["target"]), record["current_salary"], record["paths"]
    r = ruin_text(res.ruin_rate, record["target"])
    if res.status == "all_meet":
        return _view("每月最少要自掏", dollars(0),
                     f"以目前其他設定，就算每月完全不自掏，破產機率也只有 {r}，仍在 {t} 以下。", "success")
    if res.status == "none_meet":
        return _view("每月最少要自掏", f"超過 {dollars(SALARY_HI)}",
                     f"以目前其他設定，就算每月最多自掏到 **{dollars(SALARY_HI)}**，破產機率仍有 {r}，達不到 {t} 以下。",
                     "error", ["光靠多掏錢救不回來，可以試著降低貸款本金再算一次。"])
    value, diff = res.value, res.value - cur
    captions = [f"每月最多自掏 {dollars(value)} 時，破產機率約 {r}（{n:,} 次模擬）。"]
    if cur < value:
        captions.append(f"⚠️ 你目前設定的 {dollars(cur)} 不夠，每月還差 {dollars(value - cur)}。")
    delta, color = (("和目前相同", "off") if diff == 0
                    else (f"{'+' if diff > 0 else '-'}{dollars(abs(diff))}（比目前）", "inverse"))
    return _view("每月最少要自掏", dollars(value),
                 f"以目前其他設定，要讓破產機率在 {t} 以下，每月最少要能自掏 **{dollars(value)}**（你目前設定 {dollars(cur)}）。",
                 "success" if cur >= value else "warning", captions, delta, color)


# ---- risk map ----

def _labels(record):
    grid = record["grid"]
    return [f"{wan(p)} 萬" for p in grid.index], [dollars(c) for c in grid.columns]


def _current_cell(record):
    grid = record["grid"]
    rows = [i for i, p in enumerate(grid.index) if p == record["current_principal"]]
    cols = [j for j, c in enumerate(grid.columns) if c == record["current_salary"]]
    return (rows[0], cols[0]) if rows and cols else None


def bands(rates, target):
    """Colour band of each ruin rate: 0 very safe, 1 within the target, 2 over it, 3 more than twice it."""
    t = int(target) / 100
    rates = np.asarray(rates, dtype=float)
    out = np.digitize(np.nan_to_num(rates), [t / 2, t, 2 * t], right=True).astype(float)
    out[np.isnan(rates)] = np.nan
    return out


def _band_ticks(target):
    t = int(target) / 100
    a, b, c = (f"{v * 100:g}%" for v in (t / 2, t, 2 * t))
    return [f"{BAND_NAMES[0]}（≤ {a}）", f"{BAND_NAMES[1]}（{a}–{b}）", f"{BAND_NAMES[2]}（{b}–{c}）",
            f"{BAND_NAMES[3]}（> {c}）"]


def map_cells(record):
    """Text of every cell: the ruin rate, "—" where it could not be computed, the current one marked."""
    grid, target, here = record["grid"], record["target"], _current_cell(record)
    return [[ruin_text(v, target) for v in row] for row in grid.to_numpy()], here


def map_figure(record):
    grid, target = record["grid"], record["target"]
    y_labels, x_labels = _labels(record)
    cells, here = map_cells(record)
    blank = grid.isna().to_numpy()
    text = [["" if blank[i, j] else cell + (f"<br>{CURRENT_MARK}" if (i, j) == here else "")
             for j, cell in enumerate(row)] for i, row in enumerate(cells)]
    z = [[None if v != v else v for v in row] for row in bands(grid.to_numpy(), target).tolist()]
    scale = []
    for i, color in enumerate(BAND_COLORS):
        scale += [[i / 4, color], [(i + 1) / 4, color]]
    fig = go.Figure()
    if blank.any():
        # Its own layer underneath: the theme would otherwise pick a text colour that vanishes on grey.
        fig.add_trace(go.Heatmap(
            z=[[0 if b else None for b in row] for row in blank], x=x_labels, y=y_labels, zmin=0, zmax=1,
            colorscale=[[0, BLANK_COLOR], [1, BLANK_COLOR]], showscale=False, xgap=2, ygap=2, hoverongaps=False,
            text=[["—" if b else "" for b in row] for row in blank], texttemplate="%{text}",
            textfont=dict(color=BLANK_TEXT_COLOR),
            hovertemplate="貸款本金 %{y} 不比開辦費多，無法計算<extra></extra>"))
    fig.add_trace(go.Heatmap(
        z=z, x=x_labels, y=y_labels, zmin=-0.5, zmax=3.5, colorscale=scale, text=text, texttemplate="%{text}",
        customdata=cells, xgap=2, ygap=2, hoverongaps=False,
        hovertemplate=(f"貸款本金 %{{y}}｜每月最多自掏 %{{x}}<br>破產機率 %{{customdata}}（{record['paths']:,} 次模擬）"
                       "<extra></extra>"),
        colorbar=dict(title=dict(text="破產機率"), tickvals=[0, 1, 2, 3], ticktext=_band_ticks(target))))
    if here is not None:
        i, j = here
        for color, width in (("#ffffff", 6), ("#0b0b0b", 2.5)):
            fig.add_shape(type="rect", x0=j - 0.5, x1=j + 0.5, y0=i - 0.5, y1=i + 0.5, layer="above",
                          line=dict(color=color, width=width))
    fig.update_layout(xaxis_title="每月最多自掏（元）", yaxis_title="貸款本金", height=400, margin=dict(t=30, b=10))
    fig.update_xaxes(type="category")
    fig.update_yaxes(type="category")
    return fig


def map_table(record):
    y_labels, x_labels = _labels(record)
    cells, here = map_cells(record)
    if here is not None:
        cells[here[0]][here[1]] = f"◆ {cells[here[0]][here[1]]}"
    return pd.DataFrame(cells, index=y_labels, columns=x_labels)


def map_note(record):
    return MAP_NOTE.format(t=target_text(record["target"]))


def has_blank_cells(record):
    return bool(record["grid"].isna().to_numpy().any())


def map_salary_note(record):
    """Why the map hardly changes when there is no salary to fall back on; None otherwise."""
    if not record["salary_in_order"]:
        return MAP_NOTE_NO_SALARY
    if record["current_salary"] == 0:
        return MAP_NOTE_ZERO_SALARY
    return None


# ---- report ----

def report_group(record):
    return f"安全邊界（破產機率 ≤ {target_text(record['target'])}）"


def report_rows(record):
    res, target = record["principal"], record["target"]
    if res.status == "all_meet":
        most, at = f"{wan(record['hi'])} 萬以上", f"借到 {wan(record['hi'])} 萬時的破產機率"
    elif res.status == "none_meet":
        most, at = f"不到 {wan(record['lo'])} 萬", f"只借 {wan(record['lo'])} 萬時的破產機率"
    else:
        most = f"{wan(res.value)} 萬（目前 {wan(record['current_principal'])} 萬）"
        at = f"借 {wan(res.value)} 萬時的破產機率"
    rows = [("最多可以借", most), (at, ruin_text(res.ruin_rate, target))]
    sal = record["salary"]
    if sal is None:
        return rows + [("每月最少要自掏", "不計算（薪水沒有排進還款順位）")]
    if sal.status == "all_meet":
        least, at = dollars(0), "完全不自掏時的破產機率"
    elif sal.status == "none_meet":
        least, at = f"超過 {dollars(SALARY_HI)}", f"每月自掏 {dollars(SALARY_HI)} 時的破產機率"
    else:
        least = f"{dollars(sal.value)}（目前 {dollars(record['current_salary'])}）"
        at = f"每月自掏 {dollars(sal.value)} 時的破產機率"
    return rows + [("每月最少要自掏", least), (at, ruin_text(sal.ruin_rate, target))]


def report_table_note(record):
    salary = salary_view(record)
    parts = [plain(principal_view(record)["sentence"]), plain(salary["sentence"]) if salary else NO_SALARY,
             map_note(record)]
    if has_blank_cells(record):
        parts.append(MAP_NOTE_FEE)
    return "".join(parts)
