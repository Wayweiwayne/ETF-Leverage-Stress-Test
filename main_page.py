import re
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import streamlit as st

import engine
import ui_state as ui
from market_data import load_history, monthly_data, align_months, backfill_with_proxy, normalize_ticker
from version import APP_VERSION, SOURCE_URL

LOAN_TYPES = ["理財型房貸 (長年期/可寬限)", "一般信貸 (短年期/無寬限)"]
# 各貸款類型的預設值：(年利率 %, 年限, 是否預設啟用寬限期)
LOAN_DEFAULTS = {LOAN_TYPES[0]: (2.5, 20, True), LOAN_TYPES[1]: (3.5, 7, False)}

SOURCE_BY_LABEL = {
    "本薪(自掏腰包)": engine.SALARY,
    "配息資金池": engine.DIVIDEND,
    "緩衝金": engine.BUFFER,
    "變賣資產(主標的)": engine.SELL,
}
SOURCE_LABELS = list(SOURCE_BY_LABEL)
NO_SOURCE = "（不使用）"

SCENARIO_BY_LABEL = {
    "2008 黑天鵝復刻 (先暴跌後復甦)": "crash_2008",
    "失落的十年 (長期熊市陰跌)": "lost_decade",
    "AI 泡沫破裂 (典範轉移)": "ai_bubble",
    "自訂年度報酬率路徑": None,
}

JOB_LOSS_MODES = ["手動指定時間", "隨機失業模型"]
JOB_LOSS_DISTS = {"對數常態": "lognormal", "卜瓦松": "poisson"}

DCA_MODES = {
    "與槓桿組相同的自掏金額 (公平比較)": engine.DCA_MATCH_OUT_OF_POCKET,
    "每月投入整筆應繳金額 (舊版算法)": engine.DCA_FULL_PAYMENT,
}

_PATH_RE = re.compile(r"[0-9eE+\-., ]{1,200}")
SHORT_HISTORY_MONTHS = 120


def clean_ticker(raw):
    return normalize_ticker(raw) if raw.strip() else ""


def clean_path(raw):
    if not _PATH_RE.fullmatch(raw):
        raise ValueError(raw)
    return raw


def reset_loan_defaults():
    ui.forget("rate", "years", "grace", "grace_y")


ui.begin()

st.title(f"槓桿與利差套利：主動再配置與 DCA 對決引擎 ({APP_VERSION})")
st.caption("📖 每個欄位旁的問號是白話說明；想看完整公式與模型，點側邊欄最上方的「計算模型詳細說明」頁面。")

# ==========================================
# 1. 參數設定
# ==========================================
input_errors = []

with st.sidebar:
    st.header("1. 貸款與財務參數")
    loan_principal = ui.number("loan", "貸款本金 (萬)", 500, 50, min_value=1, max_value=100000,
                               help="你打算借多少錢來投資。例如填 500 就是借 500 萬。") * 10000
    loan_type = ui.choice("type", "貸款產品類型", LOAN_TYPES, LOAN_TYPES[1], widget=st.radio,
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

    st.markdown("##### 📈 利率變高的情境")
    enable_rate_shock = ui.checkbox("shock", "模擬「升息」情況", False,
                                    help="銀行的利率不是永遠不變的。打開這個，可以模擬「借錢幾年後遇到升息」的情況，看看每月還款變貴後策略還撐不撐得住。")
    rate_shock_year, rate_shock_delta = 0, 0.0
    if enable_rate_shock:
        rate_shock_year = ui.slider("shock_y", "從第幾年開始升息", 1, loan_years, min(3, loan_years), step=1,
                                    help="設定升息從第幾年發生。")
        rate_shock_delta = ui.slider("shock_d", "利率調高多少 (+%)", 0.0, 5.0, 1.0, step=0.1,
                                     help="升息的幅度。例如原本 4%、這裡填 1，升息後就變 5%。升息後每月還款會自動重新計算、變得更高。")

    st.header("2. 投資與再配置策略")
    ticker_a = ui.text("a", "第一標的 (主資產, 如 0056.TW)", "00878.TW", clean_ticker, max_chars=20,
                       help="你借來的錢主要拿去買的股票或 ETF 代號。記得加上 .TW（台股）。")
    ticker_proxy = ui.text("proxy", "上市前的歷史用哪一檔代替 (選填)", "0056.TW", clean_ticker, max_chars=20,
                           help="第一標的如果上市不久，歷史只涵蓋最近幾年，容易全是多頭、看不到大空頭。"
                                "這裡可以填一檔性質相近、上市更久的標的；第一標的上市前的月份，就直接用它當時的實際漲跌與配息代替，"
                                "讓回測與蒙地卡羅都能涵蓋更長的歷史（例如 2008 年）。"
                                "留空代表只用第一標的自己的歷史。如果替身的歷史沒有比較長，這個欄位不會有任何作用。")
    is_reinvest = ui.checkbox("reinv", "✅ 啟用配息再投入 (配息不繳貸款)", True,
                              help="勾選後，領到的股息不拿去繳貸款，而是再買進股票滾入投資。不勾選的話，股息會先存起來幫忙繳貸款。")
    ticker_b, reinvest_ratio_b = "", 0.0
    if is_reinvest:
        ticker_b = ui.text("b", "第二標的 (再投入資產, 如 00631L.TW)", "00631L.TW", clean_ticker, max_chars=20,
                           help="領到的股息，除了買回原本的標的，也可以分一部分去買另一檔（例如槓桿型 ETF）。這裡填那檔的代號。留空代表全部買回第一標的。")
        if ticker_b.strip():
            reinvest_ratio_b = ui.slider("ratio_b", "配息投入 [第二標的] 比例 (%)", 0, 100, 50, step=10,
                                         help="領到的股息，要分多少比例去買第二檔。例如填 50，就是一半買回原標的、一半買第二檔。") / 100.0

    st.header("3. 每月還款的錢從哪來")
    st.caption("設定每月繳貸款時，優先動用哪一筆錢。系統會從第一順位開始用，不夠才往下一個。"
               "每個來源只能排一次；不想動用的來源，把多出來的順位選成「（不使用）」即可。")
    prio_help = "最先動用的資金來源。本薪=自己掏錢；配息資金池=累積的股息；緩衝金=一開始預留的現金；變賣資產=賣股票換現金。"
    strat_labels = []
    for slot, slot_name in enumerate(["第一順位", "第二順位", "第三順位", "第四順位"], start=1):
        remaining = [s for s in SOURCE_LABELS if s not in strat_labels]
        picked = ui.choice(f"p{slot}", slot_name, remaining + [NO_SOURCE], remaining[0],
                           universe=SOURCE_LABELS + [NO_SOURCE], help=prio_help if slot == 1 else None)
        if picked != NO_SOURCE:
            strat_labels.append(picked)
    strat_order = tuple(SOURCE_BY_LABEL[s] for s in strat_labels)
    if strat_labels:
        st.caption("實際動用順序：" + " → ".join(strat_labels))
        unused = [s for s in SOURCE_LABELS if s not in strat_labels]
        if unused:
            st.caption("不會動用：" + "、".join(unused))
        if is_reinvest and "配息資金池" in strat_labels:
            st.caption("ℹ️ 你開啟了「配息再投入」，配息一領到就拿去買股票，所以配息資金池不會有錢，這個順位實際上不會出到力。")
    else:
        st.warning("四個順位都選了「（不使用）」，等於沒有任何錢可以繳貸款，第一個月就會破產。")

    max_salary_support = ui.number("salary", "每月最多自己補貼多少 (元)", 25000, 1000, min_value=0,
                                   help="當其他來源都不夠繳貸款時，你每個月最多願意從薪水掏多少出來補。設太高，幾乎不會破產（因為一直有薪水撐）；設低一點，比較能看出策略本身扛不扛得住。")

    st.markdown("##### 💼 失業 / 降薪情境")
    enable_job_loss = ui.checkbox("jl", "模擬失業或降薪", False,
                                  help="打開後可以模擬某段期間薪水大幅縮水甚至歸零，測試這段期間只靠配息與變賣資產能否撐住貸款。找到工作後薪水自動恢復原本的補貼上限。")
    job_loss = engine.JobLossParams()
    job_loss_mode, job_loss_salary, job_loss_start, job_loss_duration = JOB_LOSS_MODES[0], 0, 0, 0
    jl_annual_prob, jl_mean_dur, jl_dist, jl_dur_sigma = 0.0, 5.0, "對數常態", 0.6
    jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi = False, 0.15, 0.08, 0.12
    if enable_job_loss:
        job_loss_mode = ui.choice("jl_mode", "失業模型", JOB_LOSS_MODES, JOB_LOSS_MODES[0], widget=st.radio,
                                  help="「手動」=自己指定第幾個月失業、持續多久（確定性壓力測試）。「隨機」=設定失業率，每條模擬路徑各自擲骰決定何時失業、多久找到工作（更貼近現實的機率分佈）。")
        job_loss_salary = ui.number("jl_sal", "失業/降薪期間每月最多薪水支援 (元)", 0, 1000, min_value=0,
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
            jl_dist = ui.choice("jl_dist", "找到工作的時間分佈", list(JOB_LOSS_DISTS), "對數常態",
                                help="決定失業持續時間怎麼隨機：對數常態=多數人很快找到、少數人拖很久（右尾長，較貼近現實求職）；卜瓦松=圍繞平均值較對稱地分佈。")
            if jl_dist == "對數常態":
                jl_dur_sigma = ui.slider("jl_sigma", "分佈離散程度 σ", 0.2, 1.5, 0.6, step=0.1,
                                         help="對數常態的標準差。越大代表失業時間落差越懸殊（極短與極長都更常見）；越小代表大家找到工作的時間都接近平均值。")
            st.markdown("（黑天鵝與失業的相關性）")
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

    buffer_months = ui.slider("buf", "一開始預留幾個月的還款現金", 0, 12, 0,
                              help="開局時先留一筆現金當「緩衝」，相當於先存好幾個月的還款。留越多越安全，但能投入市場的本金就越少。")
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

    st.markdown("##### 💧 股息會跟著市場起伏")
    base_div_yield = ui.slider("div", "未來平均一年發多少股息 (%)", 0.0, 15.0, 6.0, step=0.1,
                               help="預估這檔標的未來平均一年配發的股息比率。例如填 6，就是一年大約領回本金的 6%。") / 100.0
    div_beta = ui.slider("div_beta", "股息跟著市場起伏的程度", 0.0, 1.0, 0.5, step=0.1,
                         help="市場好的時候公司賺得多、發的股息通常也多；市場差時股息會縮水。這個拉桿設定股息跟市場連動的強弱：設 0 代表不管漲跌都固定發，設 1 代表跟市場連動很大。就算遇到崩盤，系統仍保證至少發出基本金額的 10%，不會完全歸零。")

    st.header("5. 進階模擬設定")
    structural_discount = ui.slider("disc", "每年自動打折的報酬 (%)", 0.0, 5.0, 0.0, step=0.1,
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

    mc_paths = ui.choice("paths", "模擬要跑幾種可能 (次數)", [2000, 5000, 10000], 2000,
                         help="蒙地卡羅模擬會隨機產生很多種可能的未來來統計成敗機率。跑越多次結果越穩定，但計算時間也越久。")
    block_size = ui.choice("block", "模擬時每次抽幾個月一組 (月)", [6, 12, 24], 12,
                           help="模擬未來時，系統會從歷史中『一段一段』抽出來拼接，而不是單月亂抽，這樣才能保留漲跌的連續性（例如崩盤通常會連跌好幾個月）。這裡設定每段多長。")
    use_fixed_seed = ui.checkbox("seed", "固定亂數（同樣設定得到同樣結果）", True,
                                 help="勾選時，同一組設定每次算出來的蒙地卡羅結果都一樣，所以你調整參數後看到的變化，確定是參數造成的，不是運氣。"
                                      "取消勾選則每次重算都重新抽樣，可以用來感受抽樣本身會讓數字跳動多少。")

params = engine.SimParams(
    principal=float(loan_principal), annual_rate_pct=float(loan_rate), total_months=periods,
    grace_months=grace_periods, rate_shock_year=rate_shock_year, rate_shock_delta_pct=float(rate_shock_delta),
    buffer_months=buffer_months, reinvest=is_reinvest, reinvest_ratio_b=reinvest_ratio_b,
    source_order=strat_order, fee=trx_fee, salary_cap=float(max_salary_support), job_loss=job_loss,
    haircut_trigger=haircut_trigger, haircut_penalty=haircut_penalty,
    future_annual_returns=tuple(future_annual_returns), base_div_yield=base_div_yield, div_beta=div_beta,
    structural_discount_pct=structural_discount, vol_drag=enable_vol_drag,
    swan_month=swan_month, swan_drop=swan_drop, mc_paths=mc_paths, block_size=block_size,
    seed=42 if use_fixed_seed else None, dca_mode=dca_mode,
)


# ==========================================
# 2. 行情資料
# ==========================================
@st.cache_data(ttl=3600, max_entries=64)
def fetch_pure_asset_data(ticker, pay_day, repair):
    # Exceptions propagate so unsuccessful requests are never cached.
    return monthly_data(load_history(ticker), pay_day, repair=repair)


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
        feeds = {t_a: fetch_pure_asset_data(t_a, pay_day, repair)}
        df_a, proxy_problem = feeds[t_a], ""
        if t_proxy and t_proxy != t_a:
            try:
                feeds[t_proxy] = fetch_pure_asset_data(normalize_ticker(t_proxy), pay_day, repair)
                df_a = backfill_with_proxy(df_a, feeds[t_proxy])
            except ValueError as exc:
                proxy_problem = str(exc)
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

if st.sidebar.button("重新載入行情", help="清除這幾檔標的的行情快取並重新取得價格與配息。"):
    for symbol in {symbol_a, symbol_b, symbol_proxy} - {""}:
        fetch_pure_asset_data.clear(symbol, pay_day_option, repair_splits)

loaded = prepare_unified_data(symbol_a, symbol_b, symbol_proxy, pay_day_option, repair_splits)

# ==========================================
# 3. 結果
# ==========================================
if isinstance(loaded, str):
    st.error(f"❌ 資料獲取異常：\n\n{loaded}")
elif input_errors:
    st.error("❌ 參數有誤，請先修正：\n\n" + "\n\n".join(input_errors))
else:
    data, feeds, backfill = loaded["data"], loaded["feeds"], loaded["backfill"]
    avail_dates = data.index.strftime('%Y-%m').unique().tolist()
    n_months = len(data)

    result = run_summary(data, params)
    hist_res, mc_res, schedule = result.hist, result.mc, result.schedule

    # ---- 資料來源與品質 ----
    st.markdown("---")
    n_repairs = sum(len(feed.attrs.get('repairs', [])) for feed in feeds.values())
    n_alerts = sum(len(feed.attrs.get('anomalies', [])) for feed in feeds.values())
    label = f"📋 使用的資料：{data.index[0]:%Y-%m} 至 {data.index[-1]:%Y-%m}，共 {n_months} 個月"
    if n_repairs:
        label += f"｜已自動修正 {n_repairs} 項"
    if n_alerts:
        label += f"｜⚠️ {n_alerts} 項提醒"
    with st.expander(label):
        st.caption("進場當月以該月價格買進，下個月開始繳第一期。處理方式的說明見「計算模型詳細說明」第九節。")
        for symbol, feed in feeds.items():
            role = "（歷史替身）" if symbol == symbol_proxy and symbol not in (symbol_a, symbol_b) else ""
            st.caption(f"{symbol}{role}：來源價格期間 {feed.attrs['source_start']} 至 {feed.attrs['source_end']}（非成立／上市日期）。")
            if feed.attrs.get('repairs'):
                st.info(f"🔧 {symbol} 的來源資料有已知問題，已自動修正：\n\n" + "\n\n".join(f"- {n}" for n in feed.attrs['repairs']))
            if feed.attrs.get('anomalies'):
                st.warning(f"⚠️ {symbol} 的資料有不尋常的地方。系統無法判斷是來源錯誤還是真實情況，所以沒有更動，照原樣納入計算：\n\n"
                           + "\n\n".join(f"- {n}" for n in feed.attrs['anomalies']))
        if backfill:
            corr = backfill['correlation']
            corr_txt = f"兩者重疊 {backfill['overlap_months']} 個月，月報酬相關係數 {corr:.2f}。" if corr == corr else ""
            st.caption(f"📎 {symbol_a} 在 {backfill['start']} 至 {backfill['end']} 這 {backfill['months']} 個月還沒有自己的資料，"
                       f"以 {backfill['proxy']} 當時的實際漲跌與配息代替。{corr_txt}")
        elif symbol_proxy and symbol_proxy != symbol_a and not loaded["proxy_problem"]:
            st.caption(f"📎 替身 {symbol_proxy} 的歷史沒有比 {symbol_a} 更早（或中間有缺口），所以沒有用到。")
        if result.modelled_b_months:
            first_real = data.index[result.modelled_b_months]
            st.caption(f"📎 {symbol_b} 在 {first_real:%Y-%m} 之前沒有資料，這 {result.modelled_b_months} 個月用「第一標的漲跌 × {result.beta_b:.2f} 倍」推估"
                       "（倍數由兩者重疊期間估出；不假設它會持續贏過或輸給這個倍數）。")

    for symbol, feed in feeds.items():
        if str(feed.attrs.get('data_source', '')).startswith('snapshot'):
            saved = (feed.attrs.get('fetched_at') or '')[:10] or '先前'
            if feed.attrs.get('topped_up_to'):
                st.warning(f"⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，並已用證交所的資料補到 {feed.attrs['topped_up_to']}。"
                           "可以稍後按側欄的「重新載入行情」再試一次。")
            else:
                st.warning(f"⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，最新的價格與配息可能沒有包含在內。"
                           "可以稍後按側欄的「重新載入行情」再試一次。")
    if backfill and backfill['correlation'] == backfill['correlation'] and backfill['correlation'] < 0.6:
        st.warning(f"⚠️ {symbol_a} 與替身 {backfill['proxy']} 在重疊的 {backfill['overlap_months']} 個月裡，月報酬相關係數只有 {backfill['correlation']:.2f}，"
                   "兩者走勢差異不小，替身可能不適合，建議換一檔性質更接近的。")
    if loaded["proxy_problem"]:
        st.warning(f"⚠️ 替身 {symbol_proxy} 的資料無法使用，改為只用 {symbol_a} 自己的歷史。原因：{loaded['proxy_problem']}")
    own_yield = feeds[symbol_a]['Div_Yield']
    recent_yield = float(own_yield.tail(60).mean() * 12)
    if own_yield.sum() == 0 and base_div_yield > 0:
        st.warning(f"⚠️ {symbol_a} 的歷史資料裡沒有任何配息，但「未來平均一年發多少股息」設為 {base_div_yield * 100:.1f}%。"
                   "蒙地卡羅和未來情境的配息是照這個數字算的，等於憑空多出一筆現金；如果它真的不配息，請把這個拉桿調到 0。")
    elif recent_yield > 0 and not 2 / 3 <= base_div_yield / recent_yield <= 1.5:
        st.warning(f"⚠️ 「未來平均一年發多少股息」設為 {base_div_yield * 100:.1f}%，但 {symbol_a} 最近 {min(60, len(own_yield))} 個月實際平均約 {recent_yield * 100:.1f}%"
                   f"（全部歷史平均 {float(own_yield.mean() * 12) * 100:.1f}%）。蒙地卡羅和未來情境的配息是照你設的數字算的，"
                   "差距這麼大會直接影響結果，請確認這是你想測試的假設。")
    if n_months < SHORT_HISTORY_MONTHS:
        hint = ("可以在側欄「上市前的歷史用哪一檔代替」填一檔性質相近、上市更久的標的（例如 0056.TW 或 0050.TW）。"
                if not backfill else "")
        st.warning(f"⚠️ 可用的歷史只有 {n_months} 個月（不到 10 年），很可能沒有涵蓋完整的空頭循環，破產機率容易被低估。{hint}")

    pmt_after_grace = float(schedule.payments[grace_periods])

    col1, col2, col3 = st.columns(3)
    col1.metric("初期每月應繳", f"${int(schedule.payments[0]):,}")
    col2.metric("寬限期後每月應繳", f"${int(pmt_after_grace):,}")
    col3.metric("初始現金緩衝", f"${int(result.buffer_cash):,}")

    active_flags = []
    if enable_rate_shock:
        active_flags.append(f"利率衝擊(第{rate_shock_year}年 +{rate_shock_delta}%)")
    if enable_black_swan:
        active_flags.append(f"黑天鵝(第{swan_month}月 -{int(swan_drop*100)}%)")
    if enable_dyn_haircut:
        active_flags.append(f"動態折價(跌>{int(haircut_trigger*100)}% 加扣{haircut_penalty*100:.1f}%)")
    if result.vol_drag > 0:
        active_flags.append(f"槓桿波動耗損(持平月份每月 -{result.vol_drag*100:.3f}%)")
    if enable_job_loss:
        if job_loss.mode == engine.JOB_LOSS_RANDOM:
            crash_txt = f" 崩盤(跌>{int(jl_crash_thr*100)}%)加+{int(jl_crash_lo*100)}~{int(jl_crash_hi*100)}%" if jl_crash_on else ""
            active_flags.append(
                f"隨機失業(年率{jl_annual_prob*100:.1f}% 平均{jl_mean_dur:.0f}月/{jl_dist} 薪資上限${int(job_loss_salary):,}{crash_txt}"
                f"｜MC失業率{result.job_loss_any_rate*100:.1f}% 平均失業{result.job_loss_avg_months:.1f}月)")
        else:
            active_flags.append(f"失業/降薪(第{job_loss_start}月起 {job_loss_duration}個月 薪資上限${int(job_loss_salary):,})")
    if active_flags:
        st.caption("🟢 已啟用情境： " + " ｜ ".join(active_flags))
    if dca_mode == engine.DCA_MATCH_OUT_OF_POCKET:
        st.caption("⚖️ 定期定額對照組：每月投入「槓桿策略當月實際從薪水掏出的金額」，兩邊自掏腰包的錢相同。")
        if hist_res['DCA_Final'].max() <= 0:
            st.caption("ℹ️ 這組設定下槓桿策略完全沒有動用薪水，所以對照組沒有任何投入、期滿為 0；"
                       "此時「擊敗 DCA 勝率」等同於「沒有破產的比例」。")
    else:
        st.caption("⚖️ 定期定額對照組（舊版算法）：每月投入整筆應繳金額，不受薪水上限限制，投入本金可能高於槓桿組的自掏金額。")
    st.markdown("---")

    c1, c2 = st.columns(2)
    c1.markdown("#### 【實證】歷史滾動與情境拼接宇宙")
    c1.caption("把歷史上每個月都當成進場點，之後照真實走勢走；真實資料不夠長的部分接上未來情境，得到「如果當時進場會怎樣」的結果。")
    if not hist_res.empty:
        n_total = len(hist_res)
        n_spliced = int(hist_res['Is_Spliced'].sum())
        n_pure = n_total - n_spliced

        c1.metric("槓桿破產率 (全部起點)", f"{hist_res['Ruin_Prob'].mean() * 100:.1f}%")
        pure = hist_res[~hist_res['Is_Spliced']]
        if n_pure > 0:
            c1.metric(f"⤷ 僅『純歷史』起點破產率 (n={n_pure})", f"{pure['Ruin_Prob'].mean() * 100:.1f}%")
        c1.caption(f"共 {n_total} 個起點：純歷史 {n_pure} 個、含未來情境拼接 {n_spliced} 個。"
                   "相鄰的起點走的幾乎是同一段行情，所以這不是幾百個獨立樣本，破產率只能當作「歷史上發生過的情況」來看。"
                   f"{'⚠️ 拼接起點還全部共用同一條 scenario 劇本，彼此更加相關，僅供單一劇本壓力參考。' if n_spliced > 0 else ''}")
        n_backfilled = int(hist_res['Is_Backfilled'].sum())
        if n_backfilled:
            c1.caption(f"其中 {n_backfilled} 個起點用到了替身 {backfill['proxy'] if backfill else ''} 的歷史。")
        if result.hist_replicates > 1:
            c1.caption(f"🎲 已開啟隨機失業：每個起點各模擬 {result.hist_replicates} 種失業時點，上面的破產率是平均值。")

        c1.metric("槓桿擊敗 DCA 勝率 (全部起點)", f"{hist_res['Lev_Win'].mean() * 100:.1f}%")
        h_med = hist_res['Lev_Final_Survivors'].median()
        c1.metric("槓桿期滿中位數 (存活者)", f"${int(h_med):,}" if not pd.isna(h_med) else "無")
        c1.caption(f"把破產的也算進去（以 0 計）：${int(hist_res['Lev_Final'].median()):,}。")
        c1.metric("DCA 定期定額 期滿中位數", f"${int(hist_res['DCA_Final'].median()):,}")

    c2.markdown(f"#### 【理論】蒙地卡羅宇宙 ({mc_paths}次)")
    c2.caption(f"全歷史 Block Bootstrap (區塊={result.block_size}月) 純統計重抽樣；配息由 Dividend Beta 模型驅動。"
               "**不套用 Scenario 劇本**（但黑天鵝/利率/動態折價情境仍生效）。"
               "它從整段歷史隨機重組未來，結果與哪個月進場無關。")
    if result.mc_ok and not mc_res.empty:
        ruin_rate = float(mc_res['Is_Ruined'].mean())
        margin = 1.96 * (ruin_rate * (1 - ruin_rate) / len(mc_res)) ** 0.5
        c2.metric("槓桿破產率 (現金流斷裂)", f"{ruin_rate * 100:.1f}%")
        if ruin_rate > 0:
            c2.markdown(f"**白話：大約每 {max(1, round(1 / ruin_rate))} 種可能的未來，就有 1 種會在中途繳不出貸款。**")
            c2.caption(f"抽樣誤差約 ±{margin * 100:.1f} 個百分點（95% 信賴區間，{len(mc_res)} 次模擬）。")
        else:
            c2.markdown(f"**白話：{len(mc_res)} 種模擬的未來裡，沒有任何一種繳不出貸款。**")
            c2.caption(f"這只代表用歷史上出現過的行情重組時沒有發生，不代表不可能；真實的破產率有 95% 的把握低於 {3 / len(mc_res) * 100:.2f}%。")
        c2.metric("槓桿擊敗 DCA 勝率", f"{mc_res['Lev_Win'].mean() * 100:.1f}%")
        m_med = mc_res.loc[~mc_res['Is_Ruined'], 'Lev_Final'].median()
        c2.metric("槓桿期滿中位數 (存活者)", f"${int(m_med):,}" if not pd.isna(m_med) else "無")
        c2.caption(f"把破產的也算進去（以 0 計）：${int(mc_res['Lev_Final'].median()):,}。"
                   "破產時其實還欠著沒還完的貸款，真實處境比 0 更差。")
        c2.metric("DCA 定期定額 期滿中位數", f"${int(mc_res['DCA_Final'].median()):,}")
    else:
        c2.warning("歷史資料過短 (< 2 個月)，無法進行有意義的 Block Bootstrap 模擬。")

    if not hist_res.empty:
        st.markdown("##### 實證拼接測試期滿淨值分佈 (槓桿策略)")
        chart = hist_res.assign(破產機率=(hist_res['Ruin_Prob'] * 100).round(1).astype(str) + '%')
        fig_hist = px.bar(chart, x='Start_Date', y='Lev_Final', color='Is_Ruined',
                          pattern_shape='Is_Spliced', hover_data=['破產機率'],
                          color_discrete_map={True: '#E74C3C', False: '#1ABC9C'},
                          labels={'Start_Date': '進場月份', 'Lev_Final': '期滿資產淨值 (元)',
                                  'Is_Ruined': '破產(斷頭)', 'Is_Spliced': '含未來情境拼接'})
        st.plotly_chart(fig_hist, width='stretch')
        st.caption("有斜線紋路的長條 = 該起點歷史資料不足、已拼接未來 scenario 劇本，請謹慎解讀。")

    if result.mc_ok and not mc_res.empty:
        st.markdown("##### 蒙地卡羅：期滿淨值的分佈")
        levels = [0.05, 0.25, 0.50, 0.75, 0.95]
        names = ["最差的 5%", "偏差的 25%", "中位數", "偏好的 25%", "最好的 5%"]
        st.table(pd.DataFrame({
            "槓桿策略（破產以 0 計）": [f"${int(v):,}" for v in mc_res['Lev_Final'].quantile(levels)],
            "定期定額對照組": [f"${int(v):,}" for v in mc_res['DCA_Final'].quantile(levels)],
        }, index=names))
        st.caption("每一列是「有這麼多比例的模擬結果比這個數字差」。例如「最差的 5%」那列，代表 20 次裡有 1 次會落在這個金額以下。")

        ruined_paths = mc_res[mc_res['Is_Ruined']]
        if not ruined_paths.empty:
            st.markdown("##### 蒙地卡羅：破產發生在進場後第幾個月")
            fig_ruin = px.histogram(ruined_paths, x='Ruin_Month', nbins=min(60, periods),
                                    color_discrete_sequence=['#E74C3C'],
                                    labels={'Ruin_Month': '進場後第幾個月'})
            fig_ruin.update_layout(yaxis_title='破產的模擬次數', bargap=0.05)
            st.plotly_chart(fig_ruin, width='stretch')
            st.caption(f"{len(ruined_paths)} 次破產的模擬裡，有一半發生在第 {int(ruined_paths['Ruin_Month'].median())} 個月之前。"
                       "集中在哪一段，通常就是現金流最吃緊的時期（例如寬限期剛結束）。")

    export_hist = hist_res.rename(columns={
        'Start_Date': '進場月份', 'Ruin_Prob': '破產機率', 'Is_Ruined': '多數情況破產', 'Is_Spliced': '含未來情境拼接',
        'Is_Backfilled': '用到替身歷史', 'Lev_Final': '槓桿期滿淨值', 'Lev_Final_Survivors': '槓桿期滿淨值(未破產者)',
        'DCA_Final': 'DCA期滿淨值', 'Lev_Win': '槓桿勝過DCA的機率'})
    export_hist['進場月份'] = export_hist['進場月份'].dt.strftime('%Y-%m')
    export_mc = mc_res.rename(columns={'Is_Ruined': '破產', 'Lev_Final': '槓桿期滿淨值', 'DCA_Final': 'DCA期滿淨值',
                                       'Lev_Win': '槓桿勝過DCA', 'Ruin_Month': '破產月份(0=未破產)'})
    d1, d2 = st.columns(2)
    d1.download_button("📥 下載歷史滾動結果 (CSV)", data=export_hist.to_csv(index=False).encode('utf-8-sig'),
                       file_name="history_results.csv", mime="text/csv", key="dl_hist")
    d2.download_button("📥 下載蒙地卡羅結果 (CSV)", data=export_mc.to_csv(index_label='路徑').encode('utf-8-sig'),
                       file_name="monte_carlo_results.csv", mime="text/csv", key="dl_mc")

    st.markdown("---")
    st.header("🔍 微觀路徑追蹤與 Accounting Trace")
    st.info("💡 提醒：此微觀追蹤僅代表您選擇進場月份的「單一平行宇宙」展開，請參考上方 MC 引擎的整體破產率來評估真實系統性風險。")
    sel_month = ui.choice(
        "m", "要逐月追蹤哪一個進場月份", avail_dates,
        '2022-01' if '2022-01' in avail_dates else avail_dates[0], by_value=True,
        help="挑一個月份，看「如果那個月進場」之後每個月的資產、貸款餘額和還款來源。"
             "進場當月以該月價格買進，下個月開始繳款；真實資料用完之後接上你選的未來情境。"
             "這個選擇只影響下面的逐月明細，不會改變上方的統計結果。"
    )
    anchor_idx = avail_dates.index(sel_month)
    if result.hist_replicates > 1:
        st.caption("🎲 已開啟隨機失業：下面顯示的是這個進場月份其中一種失業時點的結果。")

    trace = run_trace(data, params, anchor_idx)
    if not trace.empty:
        month_labels = [f"{d:%Y-%m}" + (" (預測)" if projected else "")
                        for d, projected in zip(trace['date'], trace['projected'])]
        df_trace = pd.DataFrame({
            '相對期數': trace['month'],
            '真實/預測月份': month_labels,
            '總資產淨值(槓桿)': trace['lev_value'],
            '總資產淨值(DCA)': trace['dca_value'],
            '貸款剩餘餘額': trace['loan_balance'],
            '當期年利率(%)': trace['annual_rate_pct'],
            '破產(斷頭)': trace['defaulted'],
            '每月應繳本息': trace['payment'],
            '來自配息資金池': trace['from_dividend'],
            '來自緩衝金': trace['from_buffer'],
            '變賣主資產': trace['from_sell'],
            '本薪(自掏腰包)': trace['from_salary'],
            'DCA 當月投入': trace['dca_contribution'],
            '主資產股數': trace['shares_a'],
            '再投入資產股數': trace['shares_b'],
        })

        tick_step = max(1, len(month_labels) // 24)
        fig1 = px.line(df_trace, x='真實/預測月份', y=['總資產淨值(槓桿)', '總資產淨值(DCA)', '貸款剩餘餘額'],
                       color_discrete_map={'總資產淨值(槓桿)': '#3498DB', '總資產淨值(DCA)': '#9B59B6', '貸款剩餘餘額': '#F39C12'},
                       hover_data={'相對期數': True}, labels={'value': '金額 (元)', 'variable': ''})
        fig1.update_xaxes(type='category', tickmode='array', tickvals=month_labels[::tick_step])
        st.plotly_chart(fig1, width='stretch')

        st.markdown("##### 槓桿策略：每月貸款繳納資金來源拆解")
        fig2 = px.bar(df_trace, x='真實/預測月份', y=['來自配息資金池', '來自緩衝金', '變賣主資產', '本薪(自掏腰包)'],
                      color_discrete_map={'來自配息資金池': '#F1C40F', '來自緩衝金': '#2ECC71', '變賣主資產': '#3498DB', '本薪(自掏腰包)': '#E74C3C'},
                      hover_data={'相對期數': True}, labels={'value': '當月繳款金額 (元)', 'variable': ''})
        fig2.update_xaxes(type='category', tickmode='array', tickvals=month_labels[::tick_step])
        st.plotly_chart(fig2, width='stretch')

        st.markdown("##### 會計明細 (Accounting Trace Ledger)")
        format_dict = {c: "{:,.2f}" if ('股數' in c or '利率' in c) else "${:,.0f}" for c in df_trace.columns if c not in ['真實/預測月份', '相對期數', '破產(斷頭)']}
        st.dataframe(df_trace.style.format(format_dict), width='stretch')

        csv = df_trace.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載完整會計明細 (CSV)", data=csv, file_name=f"trace_進場{sel_month}.csv", mime="text/csv")

st.markdown("---")
st.caption("⚠️ 本工具是財務工程的模擬，結果完全取決於歷史資料與你輸入的假設，僅供教育與研究用途，不構成任何投資建議。"
           "借錢投資可能損失全部本金並仍須償還貸款，請自行審慎評估，必要時諮詢專業人士。")
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
