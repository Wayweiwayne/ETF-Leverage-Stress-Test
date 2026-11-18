import logging
import re
from contextlib import contextmanager
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import engine
import report
import safety_limit as safe
import ui_state as ui
from market_data import (load_history, monthly_data, align_months, backfill_with_proxy, normalize_ticker,
                         request_live, live_source_available, available_snapshots, listing_info,
                         too_short_error, taipei_now)
from version import APP_VERSION, SOURCE_URL

LOAN_TYPES = ["理財型房貸（年限長，可設寬限期）", "一般信貸（年限短，通常無寬限期）"]
# 各貸款類型的預設值：(年利率 %, 年限, 是否預設啟用寬限期)
LOAN_DEFAULTS = {LOAN_TYPES[0]: (2.5, 20, True), LOAN_TYPES[1]: (3.5, 7, False)}

SOURCE_BY_LABEL = {
    "薪水（自掏腰包）": engine.SALARY,
    "存下來的配息": engine.DIVIDEND,
    "緩衝金": engine.BUFFER,
    "賣第一標的": engine.SELL,
    "賣第二標的": engine.SELL_B,
}
SOURCE_LABELS = list(SOURCE_BY_LABEL)
LABEL_BY_SOURCE = {code: label for label, code in SOURCE_BY_LABEL.items()}
NO_SOURCE = "（不使用）"
# Links store a choice by its position here, so new entries go at the end.
SOURCE_UNIVERSE = SOURCE_LABELS[:4] + [NO_SOURCE, LABEL_BY_SOURCE[engine.SELL_B]]
# What each source paid in a month, as the ledger column and the chart legend name it.
PAID_FROM = {
    engine.DIVIDEND: ("從存下來的配息繳", "from_dividend", "#F1C40F"),
    engine.BUFFER: ("從緩衝金繳", "from_buffer", "#2ECC71"),
    engine.SELL: ("賣第一標的繳", "from_sell", "#3498DB"),
    engine.SELL_B: ("賣第二標的繳", "from_sell_b", "#8E44AD"),
    engine.SALARY: ("從薪水繳（自掏）", "from_salary", "#E74C3C"),
}
SLOT_NAMES = ["第一順位", "第二順位", "第三順位", "第四順位", "第五順位"]

SCENARIO_BY_LABEL = {
    "2008 黑天鵝復刻 (先暴跌後復甦)": "crash_2008",
    "失落的十年 (長期熊市陰跌)": "lost_decade",
    "AI 泡沫破裂 (典範轉移)": "ai_bubble",
    "自訂年度報酬率路徑": None,
}

JOB_LOSS_MODES = ["手動指定時間", "隨機失業模型"]
JOB_LOSS_DISTS = {"對數常態（多數很快找到、少數拖很久）": "lognormal", "卜瓦松（集中在平均附近）": "poisson"}

# 綜所稅級距 -> 股利的淨稅率。合併計稅時股利有 8.5% 可抵減稅額，所以淨稅率是級距減 8.5%；
# 40% 級距改用 28% 分開計稅比較划算。
INCOME_TAX_BRACKETS = {
    "不計股利所得稅": 0.0,
    "5%（可抵減額大於稅額，以 0 計）": 0.0,
    "12%": 0.035,
    "20%": 0.115,
    "30%": 0.215,
    "40%（以 28% 分開計稅）": 0.28,
}
NHI_RATE, NHI_THRESHOLD = 0.0211, 20_000

DIVIDEND_INTERVALS = {"跟歷史一樣（自動判斷）": 0, "每月": 1, "每季": 3, "每半年": 6, "每年": 12}
INTERVAL_NAMES = {1: "每月", 3: "每季", 6: "每半年", 12: "每年"}

MC_DIVIDEND_MODES = {
    "照歷史上實際發的配息（跟報酬一起重抽）": engine.MC_DIVIDENDS_HISTORY,
    "照「未來平均一年發多少股息」的設定": engine.MC_DIVIDENDS_MODEL,
}

DCA_MODES = {
    "與槓桿組相同的自掏金額 (公平比較)": engine.DCA_MATCH_OUT_OF_POCKET,
    "每月投入整筆應繳金額 (舊版算法)": engine.DCA_FULL_PAYMENT,
}

_PATH_RE = re.compile(r"[0-9eE+\-., ]{1,200}")
SHORT_HISTORY_MONTHS = 120
DISCLAIMER = ("⚠️ 本工具是財務工程的模擬，結果完全取決於歷史資料與你輸入的假設，僅供教育與研究用途，不構成任何投資建議。"
              "借錢投資可能損失全部本金並仍須償還貸款，請自行審慎評估，必要時諮詢專業人士。")
DATA_SOURCE_NAMES = {
    "live": "剛從 Yahoo Finance 取得",
    "cache": "這台主機先前取得的存檔",
    "mirror": "每日自動更新的存檔",
    "snapshot": "較舊的存檔",
    "snapshot+twse": "較舊的存檔，加上證交所的近期資料",
}


def clean_ticker(raw):
    return normalize_ticker(raw) if raw.strip() else ""


def clean_path(raw):
    if not _PATH_RE.fullmatch(raw):
        raise ValueError(raw)
    return raw


def money(value):
    return "不適用" if pd.isna(value) else f"${int(value):,}"


def percent(value):
    return "不適用" if pd.isna(value) else f"{value * 100:+.1f}%"


def fan_chart(fan):
    """Range of the leveraged strategy's assets over time, with the comparison portfolio and the loan."""
    fig = go.Figure()
    x = fan['month']
    for low, high, shade, name in (('lev_p5', 'lev_p95', 'rgba(52,152,219,0.15)', '槓桿：九成的結果落在這裡'),
                                   ('lev_p25', 'lev_p75', 'rgba(52,152,219,0.35)', '槓桿：一半的結果落在這裡')):
        fig.add_trace(go.Scatter(x=x, y=fan[low], mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=x, y=fan[high], mode='lines', line=dict(width=0), fill='tonexty',
                                 fillcolor=shade, name=name, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=x, y=fan['lev_p50'], mode='lines', line=dict(color='#3498DB', width=2), name='槓桿：中位數'))
    fig.add_trace(go.Scatter(x=x, y=fan['dca_p50'], mode='lines', line=dict(color='#9B59B6', width=2, dash='dash'),
                             name='定期定額：中位數'))
    fig.add_trace(go.Scatter(x=x, y=fan['loan_balance'], mode='lines', line=dict(color='#F39C12', width=2, dash='dot'),
                             name='貸款剩餘餘額'))
    fig.update_layout(xaxis_title='進場後第幾個月', yaxis_title='金額 (元)', hovermode='x unified',
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0))
    return fig


log = logging.getLogger(__name__)
REPORT_FAILED = "❌ 這次的報告暫時無法產生，其他結果不受影響。"


@contextmanager
def page_part(failure, broken):
    """Run one part of the results; if it breaks, show `failure` in its place and go on with the rest.

    The details go to the server log only; .streamlit/config.toml keeps tracebacks off the page.
    The failure is added to `broken`, so the report can tell it would be missing something.
    """
    try:
        yield
    except Exception:
        log.exception("part of the page failed: %s", failure)
        st.error(failure)
        broken.append(failure)


def part_failed(name):
    return f"❌ 「{name}」這一段暫時無法顯示，其他結果不受影響。"


def ruin_year_chart(ruin_months, total_months):
    """Bar per loan year, the first to the last, with how many Monte Carlo paths defaulted in it.

    `ruin_months` are 1-based months of default (months 1-12 are year 1). Years without a default
    still get a bar of zero, so the axis always spans the whole loan.
    """
    years = -(-total_months // 12)
    counts = np.bincount((np.asarray(ruin_months, dtype=int) - 1) // 12, minlength=years)[:years]
    top = int(counts.max()) if len(counts) else 0
    # Whole numbers only, a 1-2-5 step giving at most about five ticks.
    step = next(n * 10 ** k for k in range(12) for n in (1, 2, 5) if n * 10 ** k * 5 >= top)
    fig = go.Figure(go.Bar(x=[f"第{y}年" for y in range(1, years + 1)], y=counts, marker_color='#E74C3C',
                           text=[str(c) if c else "" for c in counts], textposition='outside', cliponaxis=False,
                           hovertemplate="%{x}：%{y} 次<extra></extra>"))
    fig.update_xaxes(type='category', title='貸款第幾年')
    fig.update_yaxes(title='破產的模擬次數', tickmode='linear', tick0=0, dtick=step, tickformat='d',
                     range=[0, (top + step) * 1.1], rangemode='tozero')
    fig.update_layout(bargap=0.15, showlegend=False)
    return fig


def reset_loan_defaults():
    ui.forget("rate", "years", "grace", "grace_y")


SAFE_STATE = "_safety_limit"  # the last safety limit found, with the settings it was found for


def show_safety_limit(record, data, params, mc_ok, snapshot, results_stale=False):
    """The safety-limit block: computed only when asked, then kept until the settings move on.

    `snapshot` identifies everything the search depends on. `results_stale` means the results
    above no longer match the sidebar; a search then has to wait for them, since it always uses
    their settings. What is shown and found goes into the report `record` only while it is current.
    """
    st.header(safe.HEADER, anchor=safe.ANCHOR)
    st.caption(safe.INTRO)
    notice = st.container()
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    with left:
        target = ui.choice("tgt", safe.TARGET_LABEL, list(safe.TARGETS), safe.DEFAULT_TARGET,
                           widget=st.segmented_control, by_value=True, required=True,
                           format_func=safe.target_text, help=safe.TARGET_HELP) or safe.DEFAULT_TARGET
    blocked = results_stale or not mc_ok
    with right:
        clicked = st.button(safe.BUTTON, key="safe_run", type="secondary", width="stretch", disabled=blocked)
    if results_stale:
        st.caption(safe.NEEDS_RUN)
    elif not mc_ok:
        st.caption(safe.NO_MONTE_CARLO)

    if clicked and not blocked:
        bar = st.progress(0.0, text=safe.STEPS[0])
        try:
            found = safe.compute(data, params, target, on_step=lambda done, text: bar.progress(done, text=text))
            st.session_state[SAFE_STATE] = {"snapshot": snapshot, "record": found}
        except ValueError as exc:
            st.error(f"❌ 無法計算安全邊界：{exc}")
        bar.empty()

    saved = st.session_state.get(SAFE_STATE)
    if saved is None:
        st.caption(safe.NOT_YET)
        record["settings"].append(("安全邊界", "這次沒有計算"))
        return
    found = saved["record"]
    current = saved["snapshot"] == snapshot and found["target"] == target
    if saved["snapshot"] != snapshot:
        notice.warning(safe.STALE)
    elif not current:
        notice.warning(safe.STALE_TARGET.format(t=safe.target_text(found["target"])))

    columns = st.columns(2)
    for column, view in zip(columns, (safe.principal_view(found), safe.salary_view(found))):
        if view is None:
            column.info(safe.NO_SALARY)
            continue
        column.metric(view["label"], view["value"], delta=view["delta"], delta_color=view["delta_color"])
        getattr(column, view["style"])(safe.markdown(view["sentence"]))
        for text in view["captions"]:
            column.caption(safe.markdown(text))

    st.markdown(f"##### {safe.MAP_TITLE}")
    figure = safe.map_figure(found)
    st.plotly_chart(figure, width="stretch")
    st.caption(safe.map_note(found))
    if safe.map_salary_note(found):
        st.caption(safe.markdown(safe.map_salary_note(found)))
    st.caption(safe.MAP_NOTE_2)
    if safe.has_blank_cells(found):
        st.caption(safe.MAP_NOTE_FEE)
    table = safe.map_table(found)
    with st.expander(safe.TABLE_TITLE):
        st.table(table)
    if found["seed_is_random"]:
        st.caption(safe.RANDOM_SEED)

    if current:
        record["settings"].append(("安全邊界的目標", f"破產機率 ≤ {safe.target_text(found['target'])}"))
        record["summaries"][safe.report_group(found)] = safe.report_rows(found)
        record["tables"].append((safe.MAP_TITLE, table, safe.report_table_note(found)))
        record["figures"].append((safe.MAP_TITLE, figure, safe.map_note(found)))
    else:
        record["settings"].append(("安全邊界", "這次沒有計算"))


ui.begin()

st.title(f"借錢投資 ETF 壓力測試 ({APP_VERSION})")
st.caption("📖 每個欄位旁的問號有白話說明；想看公式和計算方式，點側欄最上方的「計算方法說明」。")
if not live_source_available():
    st.info(f"📦 這是單機版：在瀏覽器裡直接執行，不需要安裝任何東西。可以使用所有台灣上市的 ETF"
            f"（目前 {len(available_snapshots())} 檔，每天自動更新），代號請加上 .TW，例如 0056.TW。"
            "無法即時查詢上市 ETF 以外的商品，要測試其他代號請使用網頁版。")

# ==========================================
# 1. 參數設定
# ==========================================
input_errors = []

with st.sidebar:
    st.header("1. 貸款條件")
    loan_principal = ui.number("loan", "貸款本金 (萬)", 500, 50, min_value=1, max_value=100000,
                               help="你打算借多少錢來投資。例如填 500 就是借 500 萬。") * 10000
    buffer_months = ui.slider("buf", "一開始預留幾個月的還款現金", 0, 12, 0,
                              help="開局時先留一筆現金當「緩衝」，相當於先存好幾個月的還款。留越多越安全，但能投入市場的本金就越少。")
    loan_type = ui.choice("type", "貸款種類", LOAN_TYPES, LOAN_TYPES[1], widget=st.radio,
                          on_change=reset_loan_defaults,
                          help="房貸通常利率低、可以借很多年，但需要拿房子抵押；信貸不用抵押品，但利率較高、年限較短。")
    default_rate, default_years, default_grace = LOAN_DEFAULTS[loan_type]
    loan_rate = ui.slider("rate", "貸款年利率 (%)", 1.5, 8.0, default_rate, step=0.1,
                          help="銀行每年跟你收的利息比率。這是這個策略最重要的「成本」——你的投資報酬必須跑贏它才划算。")
    loan_years = ui.slider("years", "貸款總年限 (年)", 1, 30, default_years, step=1,
                           help="你要花幾年把這筆錢還完。年限越長、每月還得越少，但付的總利息越多。")
    periods = loan_years * 12

    grace_periods = 0
    if loan_years >= 2:
        has_grace = ui.checkbox("grace", "啟用寬限期", default_grace,
                                help="寬限期內你只需要付利息、不用還本金，所以每月負擔比較輕。但寬限期一結束，每月要還的錢會明顯跳高。"
                                     "一般信貸通常沒有寬限期，所以選信貸時預設不勾。")
        if has_grace:
            grace_periods = ui.slider("grace_y", "寬限期長度 (年)", 1, min(5, loan_years - 1), 3, step=1,
                                      help="前幾年只繳利息不還本金。") * 12
    else:
        st.caption("貸款年限只有 1 年，無法設定寬限期。")
    pay_day_option = ui.choice("payday", "每月貸款扣款日", [10, 20, 30], 10,
                               help="每個月銀行從你帳戶扣款的日子。系統會用當月接近這天的股價來計算。")

    st.markdown("##### 📈 利率會變動")
    enable_rate_shock = ui.checkbox("shock", "模擬「升息」情況", False,
                                    help="銀行的利率不是永遠不變的。打開這個，可以模擬「借錢幾年後遇到升息」的情況，看看每月還款變貴後策略還撐不撐得住。")
    rate_shock_year, rate_shock_delta = 0, 0.0
    if enable_rate_shock:
        rate_shock_year = ui.slider("shock_y", "從第幾年開始升息", 1, loan_years, min(3, loan_years), step=1,
                                    help="設定升息從第幾年發生。")
        rate_shock_delta = ui.slider("shock_d", "利率調高多少 (+%)", 0.0, 5.0, 1.0, step=0.1,
                                     help="升息的幅度。例如原本 4%、這裡填 1，升息後就變 5%。升息後每月還款會自動重新計算、變得更高。")

    enable_floating = ui.checkbox("float", "浮動利率：利率每年都可能變", False,
                                  help="多數房貸和信貸是浮動利率，會跟著央行升降息調整。打開後可以排定之後每年利率各調多少，"
                                       "也可以讓蒙地卡羅在這條路徑之外再加上隨機的升降息。每次利率變動，月付金都會依剩餘本金和剩餘期數重算。")
    rate_path, rate_volatility = (), 0.0
    if enable_floating:
        rate_path_str = ui.text("rpath", "第 2 年起，每年利率調整多少（百分點），用逗號分開", "0.25, 0.25, 0.125", clean_path, max_chars=200,
                                help="依序是第 2 年、第 3 年、第 4 年…開始時利率的變動，正數是升息、負數是降息，會一直累加。"
                                     "例如「0.25, 0.25, 0.125」代表第 2 年升 1 碼、第 3 年再升 1 碼、第 4 年再升半碼，之後維持不變。"
                                     "留空代表沒有排定的調整。")
        try:
            rate_path = engine.parse_rate_path(rate_path_str)
        except ValueError as exc:
            st.error(str(exc))
            input_errors.append(f"浮動利率路徑：{exc}")
        rate_volatility = ui.slider("rvol", "蒙地卡羅：每年再隨機升降多少（標準差，百分點）", 0.0, 2.0, 0.25, step=0.05,
                                    help="現實中沒有人知道未來的利率。設成 0.25 的話，蒙地卡羅的每條路徑每年會在你排定的調整之外，"
                                         "再隨機多升或多降一些（大約三分之二的年份落在 ±0.25 個百分點以內），而且會逐年累積。設 0 就只照排定的路徑。"
                                         "歷史回測那一欄只用排定的路徑，不加隨機變動。")

    st.header("2. 買什麼、配息怎麼用")
    ticker_a = ui.text("a", "第一標的（借來的錢買這檔，如 0056.TW）", "00878.TW", clean_ticker, max_chars=20,
                       help="你借來的錢主要拿去買的股票或 ETF 代號。記得加上 .TW（台股）。")
    ticker_proxy = ui.text("proxy", "上市前的歷史用哪一檔代替 (選填)", "0056.TW", clean_ticker, max_chars=20,
                           help="第一標的如果上市不久，歷史只涵蓋最近幾年，容易全是多頭、看不到大空頭。"
                                "這裡可以填一檔性質相近、上市更久的標的；第一標的上市前的月份，就直接用它當時的實際漲跌與配息代替，"
                                "讓回測與蒙地卡羅都能涵蓋更長的歷史（例如 2008 年）。"
                                "留空代表只用第一標的自己的歷史。如果替身的歷史沒有比較長，這個欄位不會有任何作用。")
    is_reinvest = ui.checkbox("reinv", "配息拿去再買股票（不拿來繳貸款）", True,
                              help="勾選後，領到的股息不拿去繳貸款，而是再買進股票滾入投資。不勾選的話，股息會先存起來幫忙繳貸款。")
    ticker_b, reinvest_ratio_b = "", 0.0
    if is_reinvest:
        ticker_b = ui.text("b", "第二標的（用配息加買這檔，如 00631L.TW）", "00631L.TW", clean_ticker, max_chars=20,
                           help="領到的股息，除了買回原本的標的，也可以分一部分去買另一檔（例如槓桿型 ETF）。這裡填那檔的代號。留空代表全部買回第一標的。")
        if ticker_b.strip():
            reinvest_ratio_b = ui.slider("ratio_b", "配息拿多少比例買第二標的 (%)", 0, 100, 50, step=10,
                                         help="領到的股息，要分多少比例去買第二檔。例如填 50，就是一半買回原標的、一半買第二檔。") / 100.0

    st.header("3. 每月還款的錢從哪來")
    st.caption("設定每月繳貸款時，優先動用哪一筆錢。系統會從第一順位開始用，不夠才往下一個。"
               "每個來源只能排一次；不想動用的來源，把多出來的順位選成「（不使用）」即可。")
    prio_help = ("最先動用的錢。薪水＝自己掏錢；存下來的配息＝還沒用掉的股息；緩衝金＝一開始預留的現金；"
                 "賣第一標的＝賣掉用貸款買的那檔；賣第二標的＝賣掉用配息買進的第二檔。")
    # 有第二標的時才有東西可賣
    available_sources = [s_ for s_ in SOURCE_LABELS
                         if SOURCE_BY_LABEL[s_] != engine.SELL_B or (is_reinvest and ticker_b.strip())]
    strat_labels = []
    for slot, slot_name in enumerate(SLOT_NAMES[:len(available_sources)], start=1):
        remaining = [s_ for s_ in available_sources if s_ not in strat_labels]
        picked = ui.choice(f"p{slot}", slot_name, remaining + [NO_SOURCE], remaining[0],
                           universe=SOURCE_UNIVERSE, help=prio_help if slot == 1 else None)
        if picked != NO_SOURCE:
            strat_labels.append(picked)
    strat_order = tuple(SOURCE_BY_LABEL[s_] for s_ in strat_labels)
    if strat_labels:
        st.caption("實際動用順序：" + " → ".join(strat_labels))
        unused = [s_ for s_ in available_sources if s_ not in strat_labels]
        if unused:
            st.caption("不會動用：" + "、".join(unused))
        if engine.SELL_B in (SOURCE_BY_LABEL[s_] for s_ in unused):
            st.caption("ℹ️ 第二標的沒有排進順位：就算手上還有第二標的，其他來源用完時仍會判定破產。")
        if is_reinvest and engine.DIVIDEND in strat_order:
            st.caption("ℹ️ 你選了「配息拿去再買股票」，配息一領到就買股票，所以「存下來的配息」不會有錢，這個順位實際上不會出到力。")
    else:
        st.warning("所有順位都選了「（不使用）」，等於沒有任何錢可以繳貸款，第一個月就會破產。")

    max_salary_support = ui.number("salary", "每月最多自掏多少 (元)", 25000, 1000, min_value=0,
                                   help="當其他來源都不夠繳貸款時，你每個月最多願意從薪水掏多少出來補。設太高，幾乎不會破產（因為一直有薪水撐）；設低一點，比較能看出策略本身扛不扛得住。")

    st.markdown("##### 💼 失業或降薪")
    enable_job_loss = ui.checkbox("jl", "模擬失業或降薪", False,
                                  help="打開後可以模擬某段期間薪水大幅縮水甚至歸零，測試這段期間只靠配息與變賣資產能否撐住貸款。找到工作後薪水自動恢復原本的補貼上限。")
    job_loss = engine.JobLossParams()
    job_loss_mode, job_loss_salary, job_loss_start, job_loss_duration = JOB_LOSS_MODES[0], 0, 0, 0
    jl_annual_prob, jl_mean_dur, jl_dist, jl_dur_sigma = 0.0, 5.0, list(JOB_LOSS_DISTS)[0], 0.6
    jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi = False, 0.15, 0.08, 0.12
    if enable_job_loss:
        job_loss_mode = ui.choice("jl_mode", "失業模型", JOB_LOSS_MODES, JOB_LOSS_MODES[0], widget=st.radio,
                                  help="「手動」=自己指定第幾個月失業、持續多久（確定性壓力測試）。「隨機」=設定失業率，每條模擬路徑各自擲骰決定何時失業、多久找到工作（更貼近現實的機率分佈）。")
        job_loss_salary = ui.number("jl_sal", "失業或降薪期間，每月最多自掏多少 (元)", 0, 1000, min_value=0,
                                    help="完全失業就填 0；部分降薪則填這段期間每月還能從薪水拿出來的最高金額。兩種模型都套用這個金額。")
        if job_loss_mode == JOB_LOSS_MODES[0]:
            job_loss_start = ui.slider("jl_start", "從第幾個月開始失業/降薪", 1, periods, min(13, periods), step=1,
                                       help="設定薪水驟降從進場後的第幾個月發生。")
            max_duration = periods - job_loss_start + 1
            job_loss_duration = ui.slider("jl_dur", "持續幾個月", 1, max_duration, min(6, max_duration), step=1,
                                          help="失業或降薪要持續幾個月。這段時間結束後，薪水自動恢復成上方設定的補貼上限。")
            job_loss = engine.JobLossParams(mode=engine.JOB_LOSS_MANUAL, unemployed_salary=float(job_loss_salary),
                                            start_month=job_loss_start, duration_months=job_loss_duration)
        else:
            jl_annual_prob = ui.slider("jl_prob", "年失業機率 (%)", 0.0, 30.0, 5.0, step=0.5,
                                       help="每一年內遭遇失業的機率。例如填 5，代表每年大約有 5% 機率失業。系統會換算成逐月機率，讓每條模擬路徑各自擲骰。") / 100.0
            jl_mean_dur = ui.slider("jl_mean", "平均失業持續月數", 1.0, 24.0, 5.0, step=0.5,
                                    help="失業後平均要花幾個月才找到新工作。實際每次失業的長短會依下方的機率分佈隨機決定——有人運氣好 1 個月就上工，也有人拖到十幾個月。")
            jl_dist = ui.choice("jl_dist", "找到工作的時間分佈", list(JOB_LOSS_DISTS), list(JOB_LOSS_DISTS)[0],
                                help="決定失業持續時間怎麼隨機：對數常態=多數人很快找到、少數人拖很久（右尾長，較貼近現實求職）；卜瓦松=圍繞平均值較對稱地分佈。")
            if JOB_LOSS_DISTS[jl_dist] == "lognormal":
                jl_dur_sigma = ui.slider("jl_sigma", "失業長短的落差 (σ)", 0.2, 1.5, 0.6, step=0.1,
                                         help="對數常態的標準差。越大代表失業時間落差越懸殊（極短與極長都更常見）；越小代表大家找到工作的時間都接近平均值。")
            st.markdown("（股災常伴隨裁員）")
            jl_crash_on = ui.checkbox("jl_crash", "市場崩盤時失業率同步飆升", True,
                                      help="現實中股災常伴隨裁員潮。打開後，當某個月市場跌幅超過下方門檻，該月的失業機率會額外往上加一段（在設定範圍內隨機），模擬「資產暴跌＋同時失業」的雙重打擊。")
            if jl_crash_on:
                jl_crash_thr = ui.slider("jl_thr", "市場單月跌幅超過多少 % 視為崩盤", 5, 40, 15, step=1,
                                         help="觸發失業率飆升的單月跌幅門檻。例如填 15，代表當月跌超過 15% 時就啟動失業率加成。") / 100.0
                crash_range = ui.range_slider("jl_extra", "崩盤當月額外增加的年失業機率 (%)", 0.0, 40.0, (8.0, 12.0), step=0.5,
                                              help="崩盤觸發時，年失業機率額外往上加的範圍。每條路徑會在這個區間內隨機抽一個值，模擬不同產業、不同景氣下裁員力道的差異。")
                jl_crash_lo, jl_crash_hi = crash_range[0] / 100.0, crash_range[1] / 100.0
            job_loss = engine.JobLossParams(
                mode=engine.JOB_LOSS_RANDOM, unemployed_salary=float(job_loss_salary), annual_prob=jl_annual_prob,
                mean_duration=jl_mean_dur, distribution=JOB_LOSS_DISTS[jl_dist], duration_sigma=jl_dur_sigma,
                crash_linked=jl_crash_on, crash_threshold=jl_crash_thr,
                crash_extra_low=jl_crash_lo, crash_extra_high=jl_crash_hi)

    trx_fee = ui.number("fee", "買賣手續費與滑價 (%)", 0.1425, 0.01, min_value=0.0, max_value=5.0, format="%.4f",
                        help="每次買賣股票要付給券商的成本，加上實際成交價跟理想價的落差。台股一般約 0.1425%。") / 100.0

    st.markdown("##### 💧 急著賣股的「賤賣」損失")
    enable_dyn_haircut = ui.checkbox("hc", "模擬「崩盤時被迫賤賣」", False,
                                     help="市場大跌時，如果你急著賣股票換錢繳貸款，常常只能用更差的價格脫手（賣壓大、流動性差）。打開這個會把這種「賤賣損失」算進去，讓崩盤情境更真實。")
    haircut_trigger, haircut_penalty = 1.0, 0.0  # 門檻 100% 等同永不觸發
    if enable_dyn_haircut:
        haircut_trigger = ui.slider("hc_thr", "當月跌幅超過多少 % 才算崩盤", 5, 40, 20, step=1,
                                    help="設定多大的單月跌幅才觸發賤賣損失。例如填 20，代表當月跌超過 20% 時，賣股就會多虧一筆。") / 100.0
        haircut_penalty = ui.slider("hc_pen", "賤賣時多虧多少 (%)", 0.0, 20.0, 8.0, step=0.5,
                                    help="觸發崩盤時，賣股票要額外多承受的折價損失。例如填 8，就是崩盤時賣股比平常多虧 8%。") / 100.0

    st.header("4. 假想未來情境")
    st.info("如果你的貸款年限比股票的歷史資料還長，超出的那段「未來」系統就用底下選的劇本來填。"
            "（旁邊的蒙地卡羅模擬不套用這個劇本，它是另一種純統計的算法。）")
    scenario_mode = ui.choice("scen", "假設未來會發生什麼", list(SCENARIO_BY_LABEL), list(SCENARIO_BY_LABEL)[0],
                              help="挑一個你想測試的未來劇本。例如「2008 復刻」會先模擬一次大崩盤再慢慢漲回來，看看策略能不能熬過去。")
    scenario_key = SCENARIO_BY_LABEL[scenario_mode]
    if scenario_key is None:
        custom_path_str = ui.text("path", "輸入未來每年報酬率 (%)，用逗號分開", "5, 10, -20, 15, 5", clean_path, max_chars=200,
                                  help="自己設計未來每一年的漲跌。例如「5, 10, -20」代表第一年漲5%、第二年漲10%、第三年跌20%。")
        try:
            future_annual_returns = engine.parse_annual_returns(custom_path_str)
        except ValueError as exc:
            st.error(str(exc))
            input_errors.append(f"自訂年度報酬率路徑：{exc}")
            future_annual_returns = (5.0,)
    else:
        future_annual_returns = engine.SCENARIOS[scenario_key]

    st.markdown("##### 🦢 突發大崩盤測試")
    enable_black_swan = ui.checkbox("swan", "在某個月強制塞入一次暴跌", False,
                                    help="手動在你指定的那個月，硬塞一次單月大暴跌，測試策略在最壞時間點遇到崩盤會怎樣。歷史回測和蒙地卡羅模擬都會套用。")
    swan_month, swan_drop = 0, 0.0
    if enable_black_swan:
        swan_month = ui.slider("swan_m", "在進場後第幾個月暴跌", 1, periods, min(12, periods), step=1,
                               help="設定暴跌發生在進場後的第幾個月。選在剛開始、緩衝還很薄的時候，通常最致命。")
        swan_drop = ui.slider("swan_d", "這個月跌多少 (%)", 5, 60, 40, step=1,
                              help="暴跌的幅度。例如填 40，代表那個月股價直接腰斬式下殺 40%。") / 100.0

    st.markdown("##### 💰 未來的股息")
    base_div_yield = ui.slider("div", "未來平均一年發多少股息 (%)", 0.0, 15.0, 6.0, step=0.1,
                               help="預估這檔標的未來平均一年配發的股息比率。例如填 6，就是一年大約領回本金的 6%。"
                                    "這個數字用在歷史資料用完之後的「假想未來」；有真實資料的月份一律用實際發過的配息。"
                                    "蒙地卡羅預設也用實際發過的配息，可以在「進階設定」改成用這裡的數字。") / 100.0
    dividend_interval_label = ui.choice("dfreq", "未來的配息多久發一次", list(DIVIDEND_INTERVALS), list(DIVIDEND_INTERVALS)[0],
                                        help="同樣一年發 6%，每個月發一點和每季發一大筆，對現金流的影響不一樣：沒發的月份只能靠其他來源繳貸款，"
                                             "而且單筆金額越大，越容易超過二代健保補充保費的門檻。"
                                             "「自動判斷」會看這檔標的最近三年實際多久配一次。這只影響用股息模型算出來的配息（假想未來那段），真實資料的月份照實際發放日。")
    dividend_interval = DIVIDEND_INTERVALS[dividend_interval_label]
    div_beta = ui.slider("div_beta", "股息跟著市場起伏的程度", 0.0, 1.0, 0.5, step=0.1,
                         help="市場好的時候公司賺得多、發的股息通常也多；市場差時股息會縮水。這個拉桿設定股息跟市場連動的強弱：設 0 代表不管漲跌都固定發，設 1 代表跟市場連動很大。就算遇到崩盤，系統仍保證至少發出基本金額的 10%，不會完全歸零。")

    st.header("5. 進階設定")
    structural_discount = ui.slider("disc", "每年報酬再扣掉多少 (%)", 0.0, 5.0, 0.0, step=0.1,
                                    help="有些 ETF 因為內扣費用、追蹤誤差等原因，長期報酬會被悄悄侵蝕一點。這裡可以設定每年自動扣掉多少，模擬這種長期耗損。一般可先設 0。")

    st.markdown("##### ⚙️ 槓桿 ETF 的隱藏耗損")
    enable_vol_drag = ui.checkbox("drag", "把槓桿 ETF 的「來回震盪虧損」算進去", True,
                                  help="第二標的沒有真實資料的月份（它上市前，以及「假想未來」那段），系統要用第一標的的漲跌去推估它。"
                                       "像正二這種每日調整的槓桿型 ETF，市場來回震盪時會悄悄虧損一點，但連續上漲或連續下跌時，複利又會讓它賺得比「直接乘兩倍」多、賠得比較少。"
                                       "打開這個，推估時會用槓桿 ETF 的標準公式把這兩種效果一起算進去；關掉則單純用「第一標的漲跌 × 倍數」。"
                                       "真實歷史資料本身已經含這些效果，不受這個開關影響。")

    repair_splits = ui.checkbox("fix", "自動還原來源沒處理的股票分割", True,
                                help="行情來源對部分台股 ETF（例如 0050、00631L、0052）的股票分割沒有完整還原，資料裡會出現單日 -75% 或 -95% 的假暴跌。"
                                     "打開後，系統會找出這種「跳動幅度剛好是整數倍」的接縫並接回去，同時校正還沒換算的配息，結果頁上方會列出修正了什麼。"
                                     "只有在來源完全沒有該標的的分割紀錄時才會修；有紀錄的標的（多數美股）不會被更動。")

    dca_label = ui.choice("dca", "定期定額對照組每月投入多少", list(DCA_MODES), list(DCA_MODES)[0],
                          help="定期定額（DCA）是「不借錢、每月慢慢買」的對照組。"
                               "公平比較＝對照組每月投入的錢，等於槓桿策略當月實際從薪水掏出來的錢，兩邊自掏腰包的總額相同。"
                               "舊版算法＝對照組每月投入整筆應繳金額，不受薪水上限限制；當應繳金額遠高於薪水上限時，對照組投入的本金會比槓桿組多很多。")
    dca_mode = DCA_MODES[dca_label]

    mc_div_label = ui.choice("mcdiv", "蒙地卡羅的配息怎麼算", list(MC_DIVIDEND_MODES), list(MC_DIVIDEND_MODES)[0],
                             help="蒙地卡羅是把歷史上的月份重新排列組合。"
                                  "預設是抽到哪個月的漲跌，就一併用那個月實際發的配息，所以不配息的標的不會憑空多出配息，配息多寡也跟著這檔標的自己的紀錄走。"
                                  "如果你認為未來的配息水準會跟過去不同，可以改成照「假想未來情境」裡設定的股息率來算。"
                                  "不管選哪一個，歷史資料用完之後的「假想未來」都是照你設定的股息率。")
    mc_dividends = MC_DIVIDEND_MODES[mc_div_label]

    mc_paths = ui.choice("paths", "蒙地卡羅要模擬幾次", [2000, 5000, 10000], 2000,
                         help="蒙地卡羅模擬會隨機產生很多種可能的未來來統計成敗機率。跑越多次結果越穩定，但計算時間也越久。")
    block_size = ui.choice("block", "模擬時每次抽幾個月一組 (月)", [6, 12, 24], 12,
                           help="模擬未來時，系統會從歷史中『一段一段』抽出來拼接，而不是單月亂抽，這樣才能保留漲跌的連續性（例如崩盤通常會連跌好幾個月）。這裡設定每段多長。")
    use_fixed_seed = ui.checkbox("seed", "固定亂數（同樣設定得到同樣結果）", True,
                                 help="勾選時，同一組設定每次算出來的蒙地卡羅結果都一樣，所以你調整參數後看到的變化，確定是參數造成的，不是運氣。"
                                      "取消勾選則每次重算都重新抽樣，可以用來感受抽樣本身會讓數字跳動多少。")

    st.header("6. 稅與費用")
    st.caption("預設用台灣現行的費率。槓桿策略和定期定額對照組都適用同一套規則。")
    sell_tax = ui.number("stax", "賣出時的證交稅 (%)", 0.1, 0.05, min_value=0.0, max_value=1.0, format="%.2f",
                         help="賣股票時政府收的稅，買進不用。ETF 是 0.1%，個股是 0.3%。這筆是在上面「買賣手續費」之外另外算的。") / 100.0
    apply_nhi = ui.checkbox("nhi", "扣二代健保補充保費 (2.11%)", True,
                            help="單次領到的股利達 2 萬元時，整筆要扣 2.11% 的補充保費。借錢買的部位大，每次配息很容易超過門檻；"
                                 "定期定額對照組的部位小，初期通常不會被扣。")
    bracket_label = ui.choice("itax", "你的綜合所得稅級距（決定股利要繳多少稅）", list(INCOME_TAX_BRACKETS), "12%",
                              help="股利要併入綜合所得稅，但有 8.5% 的可抵減稅額，所以實際多繳的大約是「級距 − 8.5%」："
                                   "12% 級距約 3.5%、20% 約 11.5%、30% 約 21.5%；40% 級距改用 28% 分開計稅比較划算。"
                                   "5% 級距其實會退稅，這裡保守以 0 計。系統在每次領到配息時就先扣掉，不等到隔年報稅。"
                                   "每戶可抵減稅額上限 8 萬元沒有另外計算。")
    dividend_tax_rate = INCOME_TAX_BRACKETS[bracket_label]
    taxable_share = ui.slider("dshare", "配息裡有多少比例算股利所得 (%)", 0, 100, 100, step=5,
                              help="ETF 的配息常常不全是股利，還包含資本利得和收益平準金，那些部分不用繳所得稅和補充保費。"
                                   "各檔 ETF 每次配息的組成不同，可以在投信公告的收益分配通知查到。不確定的話維持 100，等於全部都課，最保守。") / 100.0
    loan_fee = ui.number("lfee", "貸款開辦費 (元)", 0, 1000, min_value=0,
                         help="銀行撥款時收的一次性費用（開辦費、帳管費等），會直接從借到的錢裡扣掉，能拿去投資的錢就少這一筆。")

params = engine.SimParams(
    principal=float(loan_principal), annual_rate_pct=float(loan_rate), total_months=periods,
    grace_months=grace_periods, rate_shock_year=rate_shock_year, rate_shock_delta_pct=float(rate_shock_delta),
    buffer_months=buffer_months, reinvest=is_reinvest, reinvest_ratio_b=reinvest_ratio_b,
    source_order=strat_order, fee=trx_fee, salary_cap=float(max_salary_support), job_loss=job_loss,
    haircut_trigger=haircut_trigger, haircut_penalty=haircut_penalty,
    future_annual_returns=tuple(future_annual_returns), base_div_yield=base_div_yield, div_beta=div_beta,
    structural_discount_pct=structural_discount, vol_drag=enable_vol_drag,
    swan_month=swan_month, swan_drop=swan_drop, mc_paths=mc_paths, block_size=block_size,
    seed=42 if use_fixed_seed else None, dca_mode=dca_mode, mc_dividends=mc_dividends,
    rate_path_pct=tuple(rate_path), rate_volatility_pct=float(rate_volatility),
    sell_tax=sell_tax, dividend_tax_rate=dividend_tax_rate, nhi_rate=NHI_RATE if apply_nhi else 0.0,
    nhi_threshold=float(NHI_THRESHOLD), dividend_taxable_share=taxable_share, loan_fee=float(loan_fee),
    dividend_interval_months=dividend_interval,
)


# ==========================================
# 2. 行情資料
# ==========================================
@st.cache_data(ttl=3600, max_entries=64)
def fetch_pure_asset_data(ticker, pay_day, repair, allow_short=False):
    # Exceptions propagate so unsuccessful requests are never cached.
    return monthly_data(load_history(ticker), pay_day, repair=repair, allow_short=allow_short)


@st.cache_data(ttl=3600, max_entries=32, show_spinner="模擬計算中…")
def run_summary(df, sim_params):
    return engine.run_summary(df, sim_params)


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def run_trace(df, sim_params, anchor):
    return engine.run_trace(df, sim_params, anchor)


def prepare_unified_data(t_a, t_b, t_proxy, pay_day, repair):
    """Aligned monthly data plus the per-ticker frames it was built from, or an error message."""
    try:
        t_a = normalize_ticker(t_a)
        t_b = normalize_ticker(t_b) if t_b else ""
        # A just-listed main asset may have a single month of prices; a proxy can still fill in the rest.
        feeds = {t_a: fetch_pure_asset_data(t_a, pay_day, repair, allow_short=True)}
        df_a, proxy_problem = feeds[t_a], ""
        if t_proxy and t_proxy != t_a:
            try:
                feeds[t_proxy] = fetch_pure_asset_data(normalize_ticker(t_proxy), pay_day, repair)
                df_a = backfill_with_proxy(df_a, feeds[t_proxy])
            except ValueError as exc:
                proxy_problem = str(exc)
        if df_a.empty:
            raise too_short_error(t_a, feeds[t_a].attrs['source_start'], feeds[t_a].attrs['base_month'])
        if t_b:
            feeds[t_b] = fetch_pure_asset_data(t_b, pay_day, repair)
        merged = align_months(df_a, feeds.get(t_b))
        return {"data": merged, "feeds": feeds, "backfill": df_a.attrs.get("backfill"),
                "proxy_problem": proxy_problem}
    except ValueError as exc:
        return str(exc)


symbol_a = ticker_a.strip().upper()
symbol_b = ticker_b.strip().upper() if is_reinvest else ""
symbol_proxy = ticker_proxy.strip().upper()

if st.sidebar.button("重新載入行情", help="平常會優先使用一天半以內的存檔，不必每次都向行情來源重抓。"
                                              "按這個按鈕會略過存檔，直接向 Yahoo Finance 重新取得這幾檔標的最新的價格與配息。"):
    for symbol in {symbol_a, symbol_b, symbol_proxy} - {""}:
        try:
            request_live(symbol)
        except ValueError:
            continue  # a malformed symbol is reported by the load below
        fetch_pure_asset_data.clear(symbol, pay_day_option, repair_splits)

try:
    loaded = prepare_unified_data(symbol_a, symbol_b, symbol_proxy, pay_day_option, repair_splits)
except Exception:                             # prepare_unified_data already turns expected problems into text
    log.exception("loading market data failed")
    loaded = "行情資料暫時無法處理。請稍後再試，或按側欄的「重新載入行情」。"

# ==========================================
# 3. 結果
# ==========================================
def show_results():
    """Everything below the title once the market data has loaded and the inputs are valid."""
    data, feeds, backfill = loaded["data"], loaded["feeds"], loaded["backfill"]
    avail_dates = data.index.strftime('%Y-%m').unique().tolist()
    n_months = len(data)

    try:
        result = run_summary(data, params)
    except ValueError as exc:                 # settings the engine cannot simulate
        st.error(f"❌ 參數有誤，請先修正：\n\n{exc}")
        return
    broken = []                               # parts below that failed to show
    hist_res, mc_res, schedule = result.hist, result.mc, result.schedule

    HIST, MC = "歷史回測", f"蒙地卡羅模擬（{mc_paths:,} 次）"
    record = {"data_notes": [], "warnings": [], "summaries": {"貸款": [], HIST: [], MC: []}, "tables": [], "figures": [],
              "settings": []}

    def caution(text):
        st.warning(text)
        record["warnings"].append(text)

    def data_note(text):
        st.caption(text)
        record["data_notes"].append(text)

    def show_metric(column, group, name, value):
        column.metric(name, value)
        record["summaries"][group].append((name, value))

    def show_table(heading, frame, note=""):
        st.table(frame)
        record["tables"].append((heading, frame, note))

    def show_chart(heading, figure, note=""):
        st.plotly_chart(figure, width='stretch')
        record["figures"].append((heading, figure, note))

    # ---- 資料來源與品質 ----
    with page_part(part_failed("使用的資料"), broken):
        st.markdown("---")
        n_repairs = sum(len(feed.attrs.get('repairs', [])) for feed in feeds.values())
        n_alerts = sum(len(feed.attrs.get('anomalies', [])) for feed in feeds.values())
        label = f"📋 使用的資料：{data.index[0]:%Y-%m} 至 {data.index[-1]:%Y-%m}，共 {n_months} 個月"
        if n_repairs:
            label += f"｜已自動修正 {n_repairs} 項"
        if n_alerts:
            label += f"｜⚠️ {n_alerts} 項提醒"
        with st.expander(label):
            st.caption("進場當月以該月價格買進，下個月開始繳第一期。處理方式的說明見「計算方法說明」第十節。")
            for symbol, feed in feeds.items():
                role = "（歷史替身）" if symbol == symbol_proxy and symbol not in (symbol_a, symbol_b) else ""
                fetched = (feed.attrs.get('fetched_at') or '')[:10]
                origin = DATA_SOURCE_NAMES.get(feed.attrs.get('data_source'), '')
                data_note(f"{symbol}{role}：來源價格期間 {feed.attrs['source_start']} 至 {feed.attrs['source_end']}（非成立／上市日期）。"
                          + (f"資料取得時間 {fetched}（{origin}）。" if fetched and origin else ""))
                record["data_notes"] += [f"{symbol} 已自動修正：{n}" for n in feed.attrs.get('repairs', [])]
                record["data_notes"] += [f"{symbol} 資料提醒（未更動）：{n}" for n in feed.attrs.get('anomalies', [])]
                if feed.attrs.get('repairs'):
                    st.info(f"🔧 {symbol} 的來源資料有已知問題，已自動修正：\n\n" + "\n\n".join(f"- {n}" for n in feed.attrs['repairs']))
                if feed.attrs.get('anomalies'):
                    st.warning(f"⚠️ {symbol} 的資料有不尋常的地方。系統無法判斷是來源錯誤還是真實情況，所以沒有更動，照原樣納入計算：\n\n"
                               + "\n\n".join(f"- {n}" for n in feed.attrs['anomalies']))
            if backfill:
                corr = backfill['correlation']
                corr_txt = f"兩者重疊 {backfill['overlap_months']} 個月，月報酬相關係數 {corr:.2f}。" if corr == corr else ""
                data_note(f"📎 {symbol_a} 在 {backfill['start']} 至 {backfill['end']} 這 {backfill['months']} 個月還沒有自己的資料，"
                           f"以 {backfill['proxy']} 當時的實際漲跌與配息代替。{corr_txt}")
            elif symbol_proxy and symbol_proxy != symbol_a and not loaded["proxy_problem"]:
                data_note(f"📎 替身 {symbol_proxy} 的歷史沒有比 {symbol_a} 更早（或中間有缺口），所以沒有用到。")
            data_note(f"📎 用股息模型算的配息（歷史資料用完之後的假想未來"
                       f"{'，以及蒙地卡羅' if mc_dividends == engine.MC_DIVIDENDS_MODEL else ''}）：{INTERVAL_NAMES[result.dividend_interval]}發一次"
                       f"{'，依這檔標的最近三年的紀錄判斷' if dividend_interval == 0 else ''}。")
            if result.modelled_b_months:
                first_real = data.index[result.modelled_b_months]
                data_note(f"📎 {symbol_b} 在 {first_real:%Y-%m} 之前沒有資料，這 {result.modelled_b_months} 個月用「第一標的漲跌 × {result.beta_b:.2f} 倍」推估"
                           "（倍數由兩者重疊期間估出；不假設它會持續贏過或輸給這個倍數）。")

        for symbol, feed in feeds.items():
            if str(feed.attrs.get('data_source', '')).startswith('snapshot'):
                saved = (feed.attrs.get('fetched_at') or '')[:10] or '先前'
                if feed.attrs.get('topped_up_to'):
                    caution(f"⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，並已用證交所的資料補到 {feed.attrs['topped_up_to']}。"
                               "可以稍後按側欄的「重新載入行情」再試一次。")
                else:
                    caution(f"⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，最新的價格與配息可能沒有包含在內。"
                               "可以稍後按側欄的「重新載入行情」再試一次。")
        if backfill and backfill['correlation'] == backfill['correlation'] and backfill['correlation'] < 0.6:
            caution(f"⚠️ {symbol_a} 與替身 {backfill['proxy']} 在重疊的 {backfill['overlap_months']} 個月裡，月報酬相關係數只有 {backfill['correlation']:.2f}，"
                       "兩者走勢差異不小，替身可能不適合，建議換一檔性質更接近的。")
        if loaded["proxy_problem"]:
            caution(f"⚠️ 替身 {symbol_proxy} 的資料無法使用，改為只用 {symbol_a} 自己的歷史。原因：{loaded['proxy_problem']}")
        own_yield = feeds[symbol_a]['Div_Yield']
        recent_yield = float(own_yield.tail(60).mean() * 12)
        uses_assumed_yield = ("蒙地卡羅和歷史資料用完之後的未來情境" if mc_dividends == engine.MC_DIVIDENDS_MODEL
                              else "歷史資料用完之後的未來情境")
        if own_yield.sum() == 0 and base_div_yield > 0:
            caution(f"⚠️ {symbol_a} 的歷史資料裡沒有任何配息，但「未來平均一年發多少股息」設為 {base_div_yield * 100:.1f}%。"
                       f"{uses_assumed_yield}，配息是照這個數字算的，等於憑空多出一筆現金；如果它真的不配息，請把這個拉桿調到 0。")
        elif recent_yield > 0 and not 2 / 3 <= base_div_yield / recent_yield <= 1.5:
            caution(f"⚠️ 「未來平均一年發多少股息」設為 {base_div_yield * 100:.1f}%，但 {symbol_a} 最近 {min(60, len(own_yield))} 個月實際平均約 {recent_yield * 100:.1f}%"
                       f"（全部歷史平均 {float(own_yield.mean() * 12) * 100:.1f}%）。{uses_assumed_yield}，配息是照你設的數字算的，"
                       "差距這麼大會直接影響結果，請確認這是你想測試的假設。")
        official = listing_info(symbol_a).get("listed", "")
        listed_txt = f"（證交所公告的上市日是 {official}）" if official else ""
        if backfill:
            data_note(f"📅 最早可以從 {data.index[0]:%Y-%m} 進場：{symbol_a} 的第一筆價格在 {feeds[symbol_a].attrs['source_start']}"
                      f"{listed_txt}，在那之前的 {backfill['months']} 個月，用替身 {backfill['proxy']} 當時的實際漲跌與配息補上。")
        else:
            data_note(f"📅 最早只能從 {data.index[0]:%Y-%m} 進場：{symbol_a} 的第一筆價格在 {feeds[symbol_a].attrs['source_start']}"
                      f"{listed_txt}，在那之前沒有資料。想測更早的行情（例如 2008 年），可以在側欄「上市前的歷史用哪一檔代替」"
                      "指定一檔上市更久的 ETF，用它的舊資料補上。")
        if n_months < SHORT_HISTORY_MONTHS:
            hint = ("可以在側欄「上市前的歷史用哪一檔代替」填一檔性質相近、上市更久的標的（例如 0056.TW 或 0050.TW）。"
                    if not backfill else "")
            caution(f"⚠️ 可用的歷史只有 {n_months} 個月（不到 10 年），很可能沒有涵蓋完整的空頭循環，破產機率容易被低估。{hint}")

    pmt_after_grace = float(schedule.payments[grace_periods])

    col1, col2, col3 = st.columns(3)
    show_metric(col1, "貸款", "初期每月應繳", f"${int(schedule.payments[0]):,}")
    show_metric(col2, "貸款", "寬限期後每月應繳", f"${int(pmt_after_grace):,}")
    show_metric(col3, "貸款", "開局預留的緩衝金", f"${int(result.buffer_cash):,}")

    if schedule.payments.max() > pmt_after_grace * 1.001:
        peak = int(schedule.payments.argmax())
        st.caption(f"📈 照你設定的利率變化，月付金最高會到 ${int(schedule.payments.max()):,}（第 {peak + 1} 個月，"
                   f"當時年利率 {schedule.monthly_rates[peak] * 1200:.2f}%）。")

    active_flags = []
    if enable_rate_shock:
        active_flags.append(f"升息（第 {rate_shock_year} 年起 +{rate_shock_delta}%）")
    if enable_floating:
        path_txt = "、".join(f"{d:+g}" for d in rate_path) if rate_path else "無排定調整"
        vol_txt = f"，蒙地卡羅每年隨機 ±{rate_volatility:g}" if rate_volatility > 0 else ""
        active_flags.append(f"浮動利率（第2年起每年 {path_txt} 個百分點{vol_txt}）")
    taxes = [f"證交稅{sell_tax * 100:g}%"] if sell_tax > 0 else []
    if apply_nhi:
        taxes.append("補充保費2.11%")
    if dividend_tax_rate > 0:
        taxes.append(f"股利所得稅{dividend_tax_rate * 100:g}%")
    if loan_fee > 0:
        taxes.append(f"開辦費${int(loan_fee):,}")
    if taxes:
        share_txt = f"；配息的{taxable_share * 100:.0f}%算股利所得" if taxable_share < 1 and (apply_nhi or dividend_tax_rate > 0) else ""
        active_flags.append(f"稅費（{'、'.join(taxes)}{share_txt}）")
    if enable_black_swan:
        active_flags.append(f"突發大崩盤（第 {swan_month} 個月 -{int(swan_drop*100)}%）")
    if enable_dyn_haircut:
        active_flags.append(f"崩盤賤賣（單月跌超過 {int(haircut_trigger*100)}% 時多虧 {haircut_penalty*100:.1f}%）")
    if result.vol_drag > 0:
        active_flags.append(f"槓桿 ETF 震盪耗損（持平的月份每月 -{result.vol_drag*100:.3f}%）")
    if enable_job_loss:
        if job_loss.mode == engine.JOB_LOSS_RANDOM:
            crash_txt = (f"；崩盤（單月跌超過 {jl_crash_thr * 100:.0f}%）時年失業機率再加 "
                         f"{round(jl_crash_lo * 100, 2):g}～{round(jl_crash_hi * 100, 2):g}%" if jl_crash_on else "")
            dist_name = jl_dist.split("（")[0]
            active_flags.append(
                f"隨機失業（年失業機率 {jl_annual_prob*100:.1f}%，平均失業 {jl_mean_dur:g} 個月，{dist_name}，"
                f"每月最多自掏 ${int(job_loss_salary):,}{crash_txt}"
                f"｜蒙地卡羅中 {result.job_loss_any_rate*100:.1f}% 的路徑失業過，平均失業 {result.job_loss_avg_months:.1f} 個月）")
        else:
            active_flags.append(f"失業或降薪（第 {job_loss_start} 個月起 {job_loss_duration} 個月，每月最多自掏 ${int(job_loss_salary):,}）")
    if active_flags:
        st.caption(safe.markdown("🟢 這次有開啟： " + " ｜ ".join(active_flags)))
    if dca_mode == engine.DCA_MATCH_OUT_OF_POCKET:
        st.caption("⚖️ 定期定額對照組：每月投入「槓桿策略當月實際從薪水掏出的金額」，兩邊自掏腰包的錢相同。")
        if hist_res['DCA_Final'].max() <= 0:
            st.caption("ℹ️ 這組設定下槓桿策略完全沒有動用薪水，所以對照組沒有任何投入、期滿為 0；"
                       "此時「贏過定期定額的機率」就等於「沒有破產的比例」。")
    else:
        st.caption("⚖️ 定期定額對照組（舊版算法）：每月投入整筆應繳金額，不受薪水上限限制，投入本金可能高於槓桿組的自掏金額。")
    st.markdown("---")

    c1, c2 = st.columns(2)
    c1.markdown("#### 📜 歷史回測：如果當年進場")
    c1.caption("把歷史上每個月都當成進場點，之後照真實走勢走；真實資料不夠長的部分接上假想未來，得到「如果當時進場會怎樣」的結果。")
    if not hist_res.empty:
        n_total = len(hist_res)
        n_spliced = int(hist_res['Is_Spliced'].sum())
        n_pure = n_total - n_spliced

        show_metric(c1, HIST, "破產機率（所有進場月份）", f"{hist_res['Ruin_Prob'].mean() * 100:.1f}%")
        pure = hist_res[~hist_res['Is_Spliced']]
        if n_pure > 0:
            show_metric(c1, HIST, f"⤷ 只算真實資料的 {n_pure:,} 個月份", f"{pure['Ruin_Prob'].mean() * 100:.1f}%")
        c1.caption(f"共 {n_total} 個進場月份：只用真實資料 {n_pure} 個、後段接上假想未來 {n_spliced} 個。"
                   "相鄰的月份走的幾乎是同一段行情，所以這不是幾百個獨立樣本，破產機率只能當作「歷史上發生過的情況」來看。"
                   f"{'⚠️ 含假想未來的月份都接上同一段假想未來，彼此更相關，只能當成單一劇本的參考。' if n_spliced > 0 else ''}")
        n_backfilled = int(hist_res['Is_Backfilled'].sum())
        if n_backfilled:
            c1.caption(f"其中 {n_backfilled} 個進場月份用到了替身 {backfill['proxy'] if backfill else ''} 的歷史。")
        if result.hist_replicates > 1:
            c1.caption(f"🎲 已開啟隨機失業：每個進場月份各模擬 {result.hist_replicates} 種失業時點，上面的破產機率是平均值。")
        if rate_volatility > 0:
            c1.caption("📈 這一欄的利率只照你排定的路徑走，不含隨機升降息。")

        show_metric(c1, HIST, "贏過定期定額的機率", f"{hist_res['Lev_Win'].mean() * 100:.1f}%")
        h_med = hist_res['Lev_Final_Survivors'].median()
        show_metric(c1, HIST, "期滿資產中位數（沒破產的）", f"${int(h_med):,}" if not pd.isna(h_med) else "無")
        c1.caption(f"把破產的也算進去（以 0 計）：${int(hist_res['Lev_Final'].median()):,}。")
        show_metric(c1, HIST, "定期定額：期滿資產中位數", f"${int(hist_res['DCA_Final'].median()):,}")

    c2.markdown(f"#### 🎲 蒙地卡羅模擬：{mc_paths:,} 種可能的未來")
    if mc_dividends == engine.MC_DIVIDENDS_HISTORY:
        mc_dividend_note = f"配息跟著報酬一起從歷史重抽，是當時實際發的金額，平均一年約 {result.mc_dividend_yield * 100:.1f}%。"
    else:
        mc_dividend_note = f"配息照你設定的「未來平均股息」計算，平均一年約 {result.mc_dividend_yield * 100:.1f}%。"
    c2.caption(f"從整段歷史裡每次抽連續 {result.block_size} 個月，重新拼成 {mc_paths:,} 種可能的未來，和哪個月進場無關。"
               f"{mc_dividend_note}**不套用側欄第 4 段的假想未來**，但升息、突發大崩盤、崩盤賤賣等設定仍然有效。")
    if rate_volatility > 0 and result.mc_ok:
        c2.caption(f"📈 每條路徑的利率各自隨機升降：到最後一期，九成的路徑年利率落在 "
                   f"{result.mc_final_rate_p5:.2f}% 到 {result.mc_final_rate_p95:.2f}% 之間。")
    if result.mc_ok and not mc_res.empty:
        ruin_rate = float(mc_res['Is_Ruined'].mean())
        margin = 1.96 * (ruin_rate * (1 - ruin_rate) / len(mc_res)) ** 0.5
        show_metric(c2, MC, "破產機率（繳不出貸款）", f"{ruin_rate * 100:.1f}%")
        if ruin_rate > 0:
            c2.markdown(f"**👉 大約每 {max(1, round(1 / ruin_rate))} 種可能的未來，就有 1 種會在中途繳不出貸款。**")
            c2.caption(f"抽樣誤差約 ±{margin * 100:.1f} 個百分點（95% 信賴區間，{len(mc_res)} 次模擬）。")
        else:
            c2.markdown(f"**👉 {len(mc_res)} 種模擬的未來裡，沒有任何一種繳不出貸款。**")
            c2.caption(f"這只代表用歷史上出現過的行情重組時沒有發生，不代表不可能；真實的破產機率有 95% 的把握低於 {3 / len(mc_res) * 100:.2f}%。")
        c2.caption(f"想知道最多能借多少？看下方的[安全邊界](#{safe.ANCHOR})。")
        show_metric(c2, MC, "贏過定期定額的機率", f"{mc_res['Lev_Win'].mean() * 100:.1f}%")
        m_med = mc_res.loc[~mc_res['Is_Ruined'], 'Lev_Final'].median()
        show_metric(c2, MC, "期滿資產中位數（沒破產的）", f"${int(m_med):,}" if not pd.isna(m_med) else "無")
        c2.caption(f"把破產的也算進去（以 0 計）：${int(mc_res['Lev_Final'].median()):,}。"
                   "破產時其實還欠著沒還完的貸款，真實處境比 0 更差。")
        show_metric(c2, MC, "定期定額：期滿資產中位數", f"${int(mc_res['DCA_Final'].median()):,}")
    else:
        c2.warning("歷史資料不到 2 個月，無法做蒙地卡羅模擬。")

    # ---- 安全邊界 ----
    st.markdown("---")
    with page_part(part_failed("安全邊界"), broken):
        show_safety_limit(record, data, params, result.mc_ok,
                          snapshot=(params, symbol_a, symbol_b, symbol_proxy, pay_day_option, repair_splits))
    st.markdown("---")

    with page_part(part_failed("圖表"), broken):
        if not hist_res.empty:
            heading = "歷史回測：每個月進場，期滿剩多少"
            st.markdown(f"##### {heading}")
            chart = hist_res.assign(
                破產機率=(hist_res['Ruin_Prob'] * 100).round(1).astype(str) + '%',
                結果=hist_res['Is_Ruined'].map({True: '破產', False: '撐到期滿'}),
                資料=hist_res['Is_Spliced'].map({True: '含假想未來', False: '只用真實資料'}))
            fig_hist = px.bar(chart, x='Start_Date', y='Lev_Final', color='結果', pattern_shape='資料',
                              hover_data=['破產機率'],
                              color_discrete_map={'破產': '#E74C3C', '撐到期滿': '#1ABC9C'},
                              category_orders={'結果': ['撐到期滿', '破產'], '資料': ['只用真實資料', '含假想未來']},
                              labels={'Start_Date': '進場月份', 'Lev_Final': '期滿資產 (元)'})
            fig_hist.update_layout(legend_title_text='')
            note = "有斜線紋路的長條：這個月份之後的真實資料不夠長，後段接上了你選的假想未來，請謹慎解讀。"
            show_chart(heading, fig_hist, note)
            st.caption(note)

        if result.mc_ok and not mc_res.empty:
            heading = "蒙地卡羅：期滿資產的分佈"
            st.markdown(f"##### {heading}")
            levels = [0.05, 0.25, 0.50, 0.75, 0.95]
            names = ["最差的 5%", "偏差的 25%", "中位數", "偏好的 25%", "最好的 5%"]
            show_table(heading, pd.DataFrame({
                "槓桿策略（破產以 0 計）": [f"${int(v):,}" for v in mc_res['Lev_Final'].quantile(levels)],
                "定期定額對照組": [f"${int(v):,}" for v in mc_res['DCA_Final'].quantile(levels)],
            }, index=names))
            st.caption("每一列是「有這麼多比例的模擬結果比這個數字差」。例如「最差的 5%」那列，代表 20 次裡有 1 次會落在這個金額以下。")

            heading = "蒙地卡羅：自己掏了多少錢、換到多少報酬"
            st.markdown(f"##### {heading}")
            show_table(heading, pd.DataFrame({
                "槓桿策略": [money(mc_res['Out_Of_Pocket'].median()), money(mc_res['Lev_Final'].median()),
                             percent(mc_res['Lev_IRR'].median()), percent(mc_res['Lev_IRR'].quantile(0.05))],
                "定期定額對照組": [money(mc_res['DCA_Invested'].median()), money(mc_res['DCA_Final'].median()),
                                   percent(mc_res['DCA_IRR'].median()), percent(mc_res['DCA_IRR'].quantile(0.05))],
            }, index=["整段期間自掏腰包的總額（中位數）", "期滿資產（中位數，破產以 0 計）",
                      "換算成年化報酬率（中位數）", "換算成年化報酬率（最差的 5%）"]))
            st.caption("年化報酬率是把「每個月從薪水掏出的錢」和「期滿時手上的錢」換算成等值的每年報酬，方便和定存或其他投資比較。"
                       "破產的路徑算 -100%；整段期間完全沒有自掏的路徑無法計算，不列入。")

            heading = "蒙地卡羅：資產隨時間的可能範圍"
            st.markdown(f"##### {heading}")
            show_chart(heading, fan_chart(result.mc_fan),
                       "色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。")
            gap = result.mc_fan['lev_p5'] - result.mc_fan['loan_balance']
            if (gap < 0).any():
                worst = int(gap.idxmin())
                st.caption(f"色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。"
                           f"色帶下緣跌到貸款餘額線以下的月份，代表最差的 5% 情況裡資產已經不夠還清貸款；"
                           f"差距最大在第 {int(result.mc_fan['month'].iloc[worst])} 個月。")
            else:
                st.caption("色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。"
                           "整段期間即使是最差的 5% 情況，資產都還高於貸款餘額。")

            ruined_paths = mc_res[mc_res['Is_Ruined']]
            if not ruined_paths.empty:
                heading = "蒙地卡羅：破產多半發生在第幾年"
                st.markdown(f"##### {heading}")
                n_paths, months = len(mc_res), ruined_paths['Ruin_Month'].astype(int)
                above = f"每根柱子代表貸款的一年；高度是 {n_paths:,} 次模擬裡，在那一年繳不出貸款的次數。"
                st.caption(above)
                if len(months) < 10:
                    seen = months.value_counts().sort_index()
                    listed = "、".join(f"{m}（{c} 次）" if c > 1 else str(m) for m, c in seen.items())
                    below = (f"{n_paths:,} 次模擬裡只有 {len(months)} 次破產，發生在第 {listed} 個月。"
                             "次數很少，這張圖只供參考。")
                else:
                    below = (f"{len(months)} 次破產的模擬裡，有一半發生在第 {int(months.median())} 個月之前。"
                             "集中在哪一段，通常就是現金流最吃緊的時期（例如寬限期剛結束）。")
                show_chart(heading, ruin_year_chart(months, periods), above + below)
                st.caption(below)

    with page_part(part_failed("下載計算結果"), broken):
        export_hist = hist_res.rename(columns={
            'Start_Date': '進場月份', 'Ruin_Prob': '破產機率', 'Is_Ruined': '多數情況破產', 'Is_Spliced': '含假想未來',
            'Is_Backfilled': '用到替身歷史', 'Lev_Final': '槓桿期滿資產', 'Lev_Final_Survivors': '槓桿期滿資產（沒破產的）',
            'DCA_Final': '定期定額期滿資產', 'Lev_Win': '贏過定期定額的機率'})
        export_hist['進場月份'] = export_hist['進場月份'].dt.strftime('%Y-%m')
        export_mc = mc_res.rename(columns={'Is_Ruined': '破產', 'Lev_Final': '槓桿期滿資產', 'DCA_Final': '定期定額期滿資產',
                                           'Lev_Win': '贏過定期定額', 'Ruin_Month': '破產月份(0=未破產)',
                                           'Out_Of_Pocket': '槓桿自掏總額', 'DCA_Invested': '定期定額投入總額',
                                           'Lev_IRR': '槓桿年化報酬率', 'DCA_IRR': '定期定額年化報酬率'})
        d1, d2 = st.columns(2)
        d1.download_button("📥 下載歷史回測結果 (CSV)", data=export_hist.to_csv(index=False).encode('utf-8-sig'),
                           file_name="history_results.csv", mime="text/csv", key="dl_hist")
        d2.download_button("📥 下載蒙地卡羅結果 (CSV)", data=export_mc.to_csv(index_label='路徑').encode('utf-8-sig'),
                           file_name="monte_carlo_results.csv", mime="text/csv", key="dl_mc")

    st.markdown("---")
    with page_part(part_failed("逐月明細"), broken):
        st.header("🔍 逐月明細：挑一個月份進場看看")
        st.info("💡 這裡只是「如果在某個月進場」的其中一種結果。要評估整體風險，請看上方蒙地卡羅模擬的破產機率。")
        sel_month = ui.choice(
            "m", "要看哪一個月份進場", avail_dates,
            '2022-01' if '2022-01' in avail_dates else avail_dates[0], by_value=True,
            help="挑一個月份，看「如果那個月進場」之後每個月的資產、貸款餘額和還款來源。"
                 "進場當月以該月價格買進，下個月開始繳款；真實資料用完之後接上你選的假想未來。"
                 "這個選擇只影響下面的逐月明細，不會改變上方的統計結果。"
        )
        anchor_idx = avail_dates.index(sel_month)
        if result.hist_replicates > 1:
            st.caption("🎲 已開啟隨機失業：下面顯示的是這個進場月份其中一種失業時點的結果。")

        trace = run_trace(data, params, anchor_idx)
        if not trace.empty:
            month_labels = [f"{d:%Y-%m}" + ("（預測）" if projected else "")
                            for d, projected in zip(trace['date'], trace['projected'])]
            paid_from = [PAID_FROM[src] for src in (engine.DIVIDEND, engine.BUFFER, engine.SELL, engine.SELL_B, engine.SALARY)]
            df_trace = pd.DataFrame({
                '第幾個月': trace['month'],
                '月份': month_labels,
                '槓桿：手上資產': trace['lev_value'],
                '定期定額：手上資產': trace['dca_value'],
                '貸款剩餘餘額': trace['loan_balance'],
                '當月年利率 (%)': trace['annual_rate_pct'],
                '已破產': trace['defaulted'],
                '當月應繳': trace['payment'],
                **{name: trace[column] for name, column, _ in paid_from},
                '配息被扣的稅費': trace['dividend_tax'],
                '定期定額：當月投入': trace['dca_contribution'],
                '第一標的股數': trace['shares_a'],
                '第二標的股數': trace['shares_b'],
            })

            tick_step = max(1, len(month_labels) // 24)
            month_axis = "月份（後面標「（預測）」的是假想未來）"
            heading = f"{sel_month} 進場：資產和貸款餘額"
            st.markdown(f"##### {heading}")
            fig1 = px.line(df_trace, x='月份', y=['槓桿：手上資產', '定期定額：手上資產', '貸款剩餘餘額'],
                           color_discrete_map={'槓桿：手上資產': '#3498DB', '定期定額：手上資產': '#9B59B6', '貸款剩餘餘額': '#F39C12'},
                           hover_data={'第幾個月': True}, labels={'value': '金額 (元)', 'variable': '', '月份': month_axis})
            fig1.update_xaxes(type='category', tickmode='array', tickvals=month_labels[::tick_step])
            show_chart(heading, fig1, "單一進場月份的結果，真實資料用完之後接上假想未來。")

            heading = f"{sel_month} 進場：每月貸款用哪些錢繳"
            st.markdown(f"##### {heading}")
            fig2 = px.bar(df_trace, x='月份', y=[name for name, _, _ in paid_from],
                          color_discrete_map={name: color for name, _, color in paid_from},
                          hover_data={'第幾個月': True}, labels={'value': '當月繳款金額 (元)', 'variable': '', '月份': month_axis})
            fig2.update_xaxes(type='category', tickmode='array', tickvals=month_labels[::tick_step])
            show_chart(heading, fig2)

            st.markdown(f"##### {sel_month} 進場：逐月明細表")
            format_dict = {c: "{:,.2f}" if ('股數' in c or '利率' in c) else "${:,.0f}" for c in df_trace.columns
                           if c not in ['月份', '第幾個月', '已破產']}
            st.dataframe(df_trace.style.format(format_dict), width='stretch')

            csv = df_trace.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載逐月明細表 (CSV)", data=csv, file_name=f"monthly_detail_{sel_month}.csv", mime="text/csv")

    st.markdown("---")
    if broken:
        st.error(REPORT_FAILED)             # a report missing a part would still look complete
    else:
        with page_part(REPORT_FAILED, broken):
            generated = taipei_now().strftime("%Y-%m-%d %H:%M（台北時間）")
            base_url = (st.context.url or "").split("?")[0]
            settings_query = urlencode(ui.settings())
            order_text = " → ".join(strat_labels) if strat_labels else "（沒有任何來源）"
            report_settings = [
                ("貸款", f"{int(loan_principal / 10000):,} 萬元｜{loan_type}｜年利率 {loan_rate:g}%｜{loan_years} 年"
                         + (f"｜寬限期 {grace_periods // 12} 年" if grace_periods else "｜無寬限期") + f"｜每月 {pay_day_option} 日扣款"),
                ("第一標的", symbol_a + (f"（上市前以 {backfill['proxy']} 代替）" if backfill else "")),
                ("配息", (f"再投入，其中 {reinvest_ratio_b * 100:.0f}% 買第二標的 {symbol_b}" if is_reinvest and symbol_b
                          else "再投入，全部買回第一標的" if is_reinvest else "不再投入，存下來繳貸款")),
                ("還款資金的動用順序", order_text),
                ("每月最多自掏", f"${int(max_salary_support):,}"),
                ("開局預留的緩衝金", f"{buffer_months} 個月的還款"),
                ("買賣手續費與滑價", f"{trx_fee * 100:g}%"),
                ("歷史用完之後的未來情境", scenario_mode + (f"（{custom_path_str}）" if scenario_key is None else "")),
                ("未來的股息假設", f"一年 {base_div_yield * 100:g}%｜{INTERVAL_NAMES[result.dividend_interval]}發放｜跟市場連動程度 {div_beta:g}"),
                ("蒙地卡羅模擬", f"{mc_paths:,} 次｜每次抽 {result.block_size} 個月一組｜{'固定亂數' if use_fixed_seed else '每次重新抽樣'}｜配息：{mc_div_label}"),
                ("定期定額對照組", dca_label),
                ("有開啟的情境與稅費", " ｜ ".join(active_flags) if active_flags else "無"),
                ("逐月明細的進場月份", sel_month),
                *record["settings"],
            ]
            report_html = report.build_report(
                title=f"借錢投資 ETF 壓力測試報告：{symbol_a}",
                version=APP_VERSION, generated=generated,
                share_url=f"{base_url}?{settings_query}" if base_url and settings_query else base_url,
                settings=report_settings, data_notes=record["data_notes"], warnings=record["warnings"],
                summaries=[(group, rows) for group, rows in record["summaries"].items() if rows],
                tables=record["tables"], figures=record["figures"], disclaimer=DISCLAIMER, source_url=SOURCE_URL)
            st.download_button("📄 把這次的結果存下來", data=report_html.encode("utf-8"),
                               file_name=f"stress_test_{symbol_a}_{taipei_now():%Y%m%d}.html",
                               mime="text/html", key="dl_report", type="primary")
            st.caption("報告是單一檔案，包含這次的設定、主要結果、表格和互動圖表，用瀏覽器打開就能看，也可以直接列印成 PDF。"
                       "圖表需要連上網路才會顯示。")


if isinstance(loaded, str):
    st.error(f"❌ 資料獲取異常：\n\n{loaded}")
elif input_errors:
    st.error("❌ 參數有誤，請先修正：\n\n" + "\n\n".join(input_errors))
else:
    with page_part("❌ 這次的計算暫時無法完成。可以調整設定後再試一次，或按側欄的「重新載入行情」。", []):
        show_results()

st.markdown("---")
st.caption(DISCLAIMER)
st.caption(f"{APP_VERSION}｜本程式為自由軟體，以 AGPL-3.0 授權，不提供任何擔保。"
           f"原始碼：[{SOURCE_URL.removeprefix('https://')}]({SOURCE_URL})")

# ==========================================
# 4. 分享連結
# ==========================================
ui.end()

with st.sidebar:
    st.markdown("---")
    with st.expander("🔗 分享這組設定"):
        st.caption("網址列會自動帶著你目前的所有設定。直接複製瀏覽器的網址傳給別人，對方打開就會看到同一組參數；"
                   "重新整理頁面也不會遺失設定。")
        query = urlencode(ui.settings())
        base_url = (st.context.url or "").split("?")[0]
        if base_url:
            st.code(f"{base_url}?{query}" if query else base_url, language=None, wrap_lines=True)
