import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px

st.title("槓桿與利差套利：主動再配置與 DCA 對決引擎 (V33)")
st.caption("📖 每個欄位旁的問號是白話說明；想看完整公式與模型，點側邊欄最上方的「計算模型詳細說明」頁面。")

# ==========================================
# 1. UI 與參數設定
# ==========================================
with st.sidebar:
    st.page_link("pages/1_Model_Details.py", label="📖 計算模型詳細說明（公式 / 模型）", icon="🧮")
    st.markdown("---")

    st.header("1. 貸款與財務參數")
    loan_principal = st.number_input("貸款本金 (萬)", value=500, step=50,
                                     help="你打算借多少錢來投資。例如填 500 就是借 500 萬。") * 10000
    loan_type = st.radio("貸款產品類型", ["理財型房貸 (長年期/可寬限)", "一般信貸 (短年期/無寬限)"], index=1,
                         help="房貸通常利率低、可以借很多年，但需要拿房子抵押；信貸不用抵押品，但利率較高、年限較短。")
    loan_rate = st.slider("貸款年利率 (%)", 1.5, 8.0, 3.5 if "信貸" in loan_type else 2.5, step=0.1,
                          help="銀行每年跟你收的利息比率。這是這個策略最重要的「成本」——你的投資報酬必須跑贏它才划算。")
    loan_years = st.slider("貸款總年限 (年)", 1, 30, 7 if "信貸" in loan_type else 20, step=1,
                           help="你要花幾年把這筆錢還完。年限越長、每月還得越少，但付的總利息越多。")
    periods = loan_years * 12

    has_grace = st.checkbox("啟用寬限期", value=True,
                            help="寬限期內你只需要付利息、不用還本金，所以每月負擔比較輕。但寬限期一結束，每月要還的錢會明顯跳高。")
    grace_periods = st.slider("寬限期長度 (年)", 1, min(5, max(1, loan_years - 1)), 3, step=1,
                              help="前幾年只繳利息不還本金。") * 12 if has_grace else 0
    pay_day_option = st.selectbox("每月貸款扣款日", [10, 20, 30], index=0,
                                  help="每個月銀行從你帳戶扣款的日子。系統會用當月接近這天的股價來計算。")

    # 利率衝擊情境
    st.markdown("##### 📈 利率變高的情境")
    enable_rate_shock = st.checkbox("模擬「升息」情況", value=False,
                                    help="銀行的利率不是永遠不變的。打開這個，可以模擬「借錢幾年後遇到升息」的情況，看看每月還款變貴後策略還撐不撐得住。")
    if enable_rate_shock:
        rate_shock_year = st.slider("從第幾年開始升息", 1, max(1, loan_years), min(3, loan_years), step=1,
                                    help="設定升息從第幾年發生。")
        rate_shock_delta = st.slider("利率調高多少 (+%)", 0.0, 5.0, 1.0, step=0.1,
                                     help="升息的幅度。例如原本 4%、這裡填 1，升息後就變 5%。升息後每月還款會自動重新計算、變得更高。")
    else:
        rate_shock_year, rate_shock_delta = 0, 0.0

    st.header("2. 投資與再配置策略")
    ticker_a = st.text_input("第一標的 (主資產, 如 0056.TW)", value="00878.TW",
                             help="你借來的錢主要拿去買的股票或 ETF 代號。記得加上 .TW（台股）。")
    is_reinvest = st.checkbox("✅ 啟用配息再投入 (配息不繳貸款)", value=True,
                              help="勾選後，領到的股息不拿去繳貸款，而是再買進股票滾入投資。不勾選的話，股息會先存起來幫忙繳貸款。")

    if is_reinvest:
        ticker_b = st.text_input("第二標的 (再投入資產, 如 00631L.TW)", value="00631L.TW",
                                 help="領到的股息，除了買回原本的標的，也可以分一部分去買另一檔（例如槓桿型 ETF）。這裡填那檔的代號。")
        reinvest_ratio_b = st.slider("配息投入 [第二標的] 比例 (%)", 0, 100, 50, step=10,
                                     help="領到的股息，要分多少比例去買第二檔。例如填 50，就是一半買回原標的、一半買第二檔。") / 100.0
    else:
        ticker_b, reinvest_ratio_b = None, 0.0

    st.header("3. 每月還款的錢從哪來")
    src_options = ["本薪(自掏腰包)", "配息資金池", "緩衝金", "變賣資產(主標的)"]
    st.caption("設定每月繳貸款時，優先動用哪一筆錢。系統會從第一順位開始用，不夠才往下一個。")
    prio_1 = st.selectbox("第一順位", src_options, index=0,
                          help="最先動用的資金來源。本薪=自己掏錢；配息資金池=累積的股息；緩衝金=一開始預留的現金；變賣資產=賣股票換現金。")
    prio_2 = st.selectbox("第二順位", src_options, index=1)
    prio_3 = st.selectbox("第三順位", src_options, index=2)
    prio_4 = st.selectbox("第四順位", src_options, index=3)
    strat_order = [prio_1, prio_2, prio_3, prio_4]

    max_salary_support = st.number_input("每月最多自己補貼多少 (元)", value=25000, step=1000,
                                         help="當其他來源都不夠繳貸款時，你每個月最多願意從薪水掏多少出來補。設太高，幾乎不會破產（因為一直有薪水撐）；設低一點，比較能看出策略本身扛不扛得住。")

    st.markdown("##### 💼 失業 / 降薪情境")
    enable_job_loss = st.checkbox("模擬失業或降薪", value=False,
                                  help="打開後可以模擬某段期間薪水大幅縮水甚至歸零，測試這段期間只靠配息與變賣資產能否撐住貸款。找到工作後薪水自動恢復原本的補貼上限。")
    # 預設值 (關閉或未選到的模式都需有定義，供後續打包)
    job_loss_mode = "手動指定時間"
    job_loss_start, job_loss_duration, job_loss_salary = 0, 0, 0
    jl_annual_prob, jl_mean_dur, jl_dist, jl_dur_sigma = 0.0, 5.0, "對數常態", 0.6
    jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi = False, 0.15, 0.08, 0.12
    if enable_job_loss:
        job_loss_mode = st.radio("失業模型", ["手動指定時間", "隨機失業模型"], index=0,
                                 help="「手動」=自己指定第幾個月失業、持續多久（確定性壓力測試）。「隨機」=設定失業率，每條模擬路徑各自擲骰決定何時失業、多久找到工作（更貼近現實的機率分佈）。")
        job_loss_salary = st.number_input("失業/降薪期間每月最多薪水支援 (元)", value=0, step=1000,
                                          help="完全失業就填 0；部分降薪則填這段期間每月還能從薪水拿出來的最高金額。兩種模型都套用這個金額。")
        if job_loss_mode == "手動指定時間":
            job_loss_start = st.slider("從第幾個月開始失業/降薪", 1, periods, min(13, periods), step=1,
                                       help="設定薪水驟降從進場後的第幾個月發生。")
            job_loss_duration = st.slider("持續幾個月", 1, max(1, periods - job_loss_start + 1),
                                          min(6, max(1, periods - job_loss_start + 1)), step=1,
                                          help="失業或降薪要持續幾個月。這段時間結束後，薪水自動恢復成上方設定的補貼上限。")
        else:
            jl_annual_prob = st.slider("年失業機率 (%)", 0.0, 30.0, 5.0, step=0.5,
                                       help="每一年內遭遇失業的機率。例如填 5，代表每年大約有 5% 機率失業。系統會換算成逐月機率，讓每條模擬路徑各自擲骰。") / 100.0
            jl_mean_dur = st.slider("平均失業持續月數", 1.0, 24.0, 5.0, step=0.5,
                                    help="失業後平均要花幾個月才找到新工作。實際每次失業的長短會依下方的機率分佈隨機決定——有人運氣好 1 個月就上工，也有人拖到十幾個月。")
            jl_dist = st.selectbox("找到工作的時間分佈", ["對數常態", "卜瓦松"], index=0,
                                   help="決定失業持續時間怎麼隨機：對數常態=多數人很快找到、少數人拖很久（右尾長，較貼近現實求職）；卜瓦松=圍繞平均值較對稱地分佈。")
            if jl_dist == "對數常態":
                jl_dur_sigma = st.slider("分佈離散程度 σ", 0.2, 1.5, 0.6, step=0.1,
                                         help="對數常態的標準差。越大代表失業時間落差越懸殊（極短與極長都更常見）；越小代表大家找到工作的時間都接近平均值。")
            st.markdown("（黑天鵝與失業的相關性）")
            jl_crash_on = st.checkbox("市場崩盤時失業率同步飆升", value=True,
                                      help="現實中股災常伴隨裁員潮。打開後，當某個月市場跌幅超過下方門檻，該月的失業機率會額外往上加一段（在設定範圍內隨機），模擬「資產暴跌＋同時失業」的雙重打擊。")
            if jl_crash_on:
                jl_crash_thr = st.slider("市場單月跌幅超過多少 % 視為崩盤", 5, 40, 15, step=1,
                                         help="觸發失業率飆升的單月跌幅門檻。例如填 15，代表當月跌超過 15% 時就啟動失業率加成。") / 100.0
                crash_range = st.slider("崩盤當月額外增加的年失業機率 (%)", 0.0, 40.0, (8.0, 12.0), step=0.5,
                                        help="崩盤觸發時，年失業機率額外往上加的範圍。每條路徑會在這個區間內隨機抽一個值，模擬不同產業、不同景氣下裁員力道的差異。")
                jl_crash_lo, jl_crash_hi = crash_range[0] / 100.0, crash_range[1] / 100.0

    buffer_months = st.slider("一開始預留幾個月的還款現金", 0, 12, 0,
                              help="開局時先留一筆現金當「緩衝」，相當於先存好幾個月的還款。留越多越安全，但能投入市場的本金就越少。")
    trx_fee = st.number_input("買賣手續費與滑價 (%)", value=0.1425, step=0.01,
                              help="每次買賣股票要付給券商的成本，加上實際成交價跟理想價的落差。台股一般約 0.1425%。") / 100.0

    # 動態流動性折價
    st.markdown("##### 💧 急著賣股的「賤賣」損失")
    enable_dyn_haircut = st.checkbox("模擬「崩盤時被迫賤賣」", value=False,
                                     help="市場大跌時，如果你急著賣股票換錢繳貸款，常常只能用更差的價格脫手（賣壓大、流動性差）。打開這個會把這種「賤賣損失」算進去，讓崩盤情境更真實。")
    if enable_dyn_haircut:
        haircut_trigger = st.slider("當月跌幅超過多少 % 才算崩盤", 5, 40, 20, step=1,
                                    help="設定多大的單月跌幅才觸發賤賣損失。例如填 20，代表當月跌超過 20% 時，賣股就會多虧一筆。") / 100.0
        haircut_penalty = st.slider("賤賣時多虧多少 (%)", 0.0, 20.0, 8.0, step=0.5,
                                    help="觸發崩盤時，賣股票要額外多承受的折價損失。例如填 8，就是崩盤時賣股比平常多虧 8%。") / 100.0
    else:
        haircut_trigger, haircut_penalty = 1.0, 0.0  # trigger=100% 等同永不觸發

    st.header("4. 假想未來情境")
    st.info("如果你的貸款年限比股票的歷史資料還長，超出的那段「未來」系統就用底下選的劇本來填。"
            "（旁邊的蒙地卡羅模擬不套用這個劇本，它是另一種純統計的算法。）")
    scenario_mode = st.selectbox("假設未來會發生什麼", [
        "2008 黑天鵝復刻 (先暴跌後復甦)",
        "失落的十年 (長期熊市陰跌)",
        "AI 泡沫破裂 (典範轉移)",
        "自訂年度報酬率路徑"
    ], help="挑一個你想測試的未來劇本。例如「2008 復刻」會先模擬一次大崩盤再慢慢漲回來，看看策略能不能熬過去。")

    custom_path_str = ""
    if scenario_mode == "自訂年度報酬率路徑":
        custom_path_str = st.text_input("輸入未來每年報酬率 (%)，用逗號分開", "5, 10, -20, 15, 5",
                                        help="自己設計未來每一年的漲跌。例如「5, 10, -20」代表第一年漲5%、第二年漲10%、第三年跌20%。")

    # 黑天鵝注入
    st.markdown("##### 🦢 突發大崩盤測試")
    enable_black_swan = st.checkbox("在某個月強制塞入一次暴跌", value=False,
                                    help="手動在你指定的那個月，硬塞一次單月大暴跌，測試策略在最壞時間點遇到崩盤會怎樣。歷史回測和蒙地卡羅模擬都會套用。")
    if enable_black_swan:
        swan_month = st.slider("在進場後第幾個月暴跌", 1, periods, min(12, periods), step=1,
                               help="設定暴跌發生在進場後的第幾個月。選在剛開始、緩衝還很薄的時候，通常最致命。")
        swan_drop = st.slider("這個月跌多少 (%)", 5, 60, 40, step=1,
                              help="暴跌的幅度。例如填 40，代表那個月股價直接腰斬式下殺 40%。") / 100.0
    else:
        swan_month, swan_drop = 0, 0.0

    st.markdown("##### 💧 股息會跟著市場起伏")
    base_div_yield = st.slider("未來平均一年發多少股息 (%)", 0.0, 15.0, 6.0, step=0.1,
                               help="預估這檔標的未來平均一年配發的股息比率。例如填 6，就是一年大約領回本金的 6%。") / 100.0
    div_beta = st.slider("股息跟著市場起伏的程度", 0.0, 1.0, 0.5, step=0.1,
                         help="市場好的時候公司賺得多、發的股息通常也多；市場差時股息會縮水。這個拉桿設定股息跟市場連動的強弱：設 0 代表不管漲跌都固定發，設 1 代表跟市場連動很大。就算遇到崩盤，系統仍保證至少發出基本金額的 10%，不會完全歸零。")

    st.header("5. 進階模擬設定")
    structural_discount = st.slider("每年自動打折的報酬 (%)", 0.0, 5.0, 0.0, step=0.1,
                                    help="有些 ETF 因為內扣費用、追蹤誤差等原因，長期報酬會被悄悄侵蝕一點。這裡可以設定每年自動扣掉多少，模擬這種長期耗損。一般可先設 0。")

    # 槓桿 ETF 波動耗損
    st.markdown("##### ⚙️ 槓桿 ETF 的隱藏耗損")
    enable_vol_drag = st.checkbox("把槓桿 ETF 的「來回震盪虧損」算進去", value=True,
                                  help="像正二這種槓桿型 ETF 有個隱藏小毛病：市場上上下下來回震盪時，它會悄悄虧損一點，震得越兇虧得越多——這跟最後是漲是跌無關，純粹是槓桿的數學特性。打開這個會把這種長期耗損算進去，讓模擬更貼近現實。（只作用在「假想未來」那段；真實歷史資料本身已經含這個效果，不會重複計算。）")

    mc_paths = st.selectbox("模擬要跑幾種可能 (次數)", [2000, 5000, 10000], index=0,
                            help="蒙地卡羅模擬會random出很多種可能的未來來統計成敗機率。跑越多次結果越穩定，但計算時間也越久。")
    block_size = st.selectbox("模擬時每次抽幾個月一組 (月)", [6, 12, 24], index=1,
                              help="模擬未來時，系統會從歷史中『一段一段』抽出來拼接，而不是單月亂抽，這樣才能保留漲跌的連續性（例如崩盤通常會連跌好幾個月）。這裡設定每段多長。")
    use_fixed_seed = st.checkbox("固定亂數 (除錯用)", value=False,
                                 help="勾選後每次跑出來的隨機結果都一樣，方便你重複比對。一般使用不用勾。")

# ==========================================
# 2. 貸款預處理 (含利率衝擊 PMT 重算)
# ==========================================
# 基礎逐月薪資上限。手動模式直接在此挖洞；隨機模式維持滿薪，由各路徑自行擲骰挖洞 (run_engines 內處理)。
max_sal_arr = np.full(periods, float(max_salary_support))
if enable_job_loss and job_loss_mode == "手動指定時間" and job_loss_duration > 0:
    s_idx = job_loss_start - 1
    e_idx = min(s_idx + job_loss_duration, periods)
    max_sal_arr[s_idx:e_idx] = float(job_loss_salary)

# 隨機失業模型參數打包 (皆為原生型別，可供 @st.cache_data 雜湊)
jl_random_on = bool(enable_job_loss and job_loss_mode == "隨機失業模型")
job_loss_params = (
    jl_random_on, float(job_loss_salary), float(jl_annual_prob), float(jl_mean_dur),
    jl_dist, float(jl_dur_sigma), bool(jl_crash_on), float(jl_crash_thr),
    float(jl_crash_lo), float(jl_crash_hi),
)

r_monthly = (loan_rate / 100) / 12
pmt_grace = loan_principal * r_monthly
remaining_periods = periods - grace_periods
pmt_after = loan_principal * r_monthly / (1 - (1 + r_monthly) ** -remaining_periods) if remaining_periods > 0 else pmt_grace
required_buffer = pmt_after * buffer_months


def build_pmt_schedule(prin, base_rate_ann, tot_p, g_p, shock_year, shock_delta):
    """
    【V32】產生長度 tot_p 的逐月 (利率, 應繳金額, 該月計息利率) 排程。
    - 寬限期內：純繳息 = 當期剩餘本金 × 當期月利率。
    - 寬限期後：本息平均攤還。
    - 利率衝擊：自 shock_year 年起利率 +shock_delta%，以「當下剩餘本金 + 剩餘期數」重算月付金（年限不變）。
    回傳: pmt_arr, int_rate_monthly_arr, principal_path(每月初剩餘本金)
    """
    shock_start_idx = (shock_year - 1) * 12 if shock_year > 0 else None

    pmt_arr = np.zeros(tot_p)
    rate_arr = np.zeros(tot_p)
    bal = prin
    bal_path = np.zeros(tot_p)

    # 初始攤還月付金 (寬限期後)
    def amort_pmt(balance, r_m, n_left):
        if n_left <= 0:
            return balance * (1 + r_m)
        if r_m <= 0:
            return balance / n_left
        return balance * r_m / (1 - (1 + r_m) ** -n_left)

    rem_after = tot_p - g_p
    curr_rate_ann = base_rate_ann
    r_m = (curr_rate_ann / 100) / 12
    pmt_amort = amort_pmt(prin, r_m, rem_after) if rem_after > 0 else prin * r_m

    for t in range(tot_p):
        # 利率衝擊：在 shock 當月，依當下剩餘本金與剩餘攤還期數重算月付金
        if shock_start_idx is not None and t == shock_start_idx:
            curr_rate_ann = base_rate_ann + shock_delta
            r_m = (curr_rate_ann / 100) / 12
            n_left = tot_p - max(t, g_p)
            if t >= g_p:
                pmt_amort = amort_pmt(bal, r_m, n_left)
            else:
                # 仍在寬限期：純繳息提高，寬限結束後再以新利率重算
                pass

        rate_arr[t] = r_m
        bal_path[t] = bal
        int_due = bal * r_m

        if t < g_p:
            pmt = int_due  # 純繳息
            prin_paid = 0.0
        else:
            # 若剛跨出寬限期且尚未因 shock 重算，於寬限期結束首月計算攤還金
            if t == g_p and (shock_start_idx is None or t != shock_start_idx):
                n_left = tot_p - g_p
                pmt_amort = amort_pmt(bal, r_m, n_left)
            pmt = pmt_amort
            prin_paid = max(0.0, pmt - int_due)

        pmt_arr[t] = pmt
        bal = max(0.0, bal - prin_paid)

    return pmt_arr, rate_arr, bal_path


# 預先建立逐月還款排程 (供所有引擎與微觀追蹤共用)
pmt_schedule, rate_schedule, _ = build_pmt_schedule(
    loan_principal, loan_rate, periods, grace_periods, rate_shock_year, rate_shock_delta
)

# ==========================================
# 3. 核心資料引擎
# ==========================================
@st.cache_data
def fetch_pure_asset_data(ticker, pay_day):
    try:
        df = yf.download(ticker, period="max", progress=False, auto_adjust=False)
        if df.empty:
            return f"Yahoo Finance 回傳空值。請確認代號 '{ticker}' 是否存在。"

        if isinstance(df.columns, pd.MultiIndex):
            if 'Close' in df.columns.get_level_values(0):
                df.columns = df.columns.get_level_values(0)
            else:
                df.columns = df.columns.get_level_values(1)

        if 'Close' not in df.columns:
            return "找不到 Close 收盤價欄位。"

        try:
            tkr = yf.Ticker(ticker)
            divs = tkr.dividends
            if divs is None or divs.empty:
                divs = pd.Series(dtype=float)
        except Exception:
            divs = pd.Series(dtype=float)

        df = df[['Close']].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if not divs.empty:
            divs.index = pd.to_datetime(divs.index).tz_localize(None)

        df = df.sort_index()
        df['YYYYMM'] = df.index.to_period('M')

        df['_day'] = df.index.day
        target_idxs = []
        for _, g in df.groupby('YYYYMM'):
            valid = g[g['_day'] >= pay_day]
            target_idxs.append(valid.index[0] if not valid.empty else g.index[-1])
        monthly = df.loc[target_idxs].copy()
        monthly = monthly.drop(columns=['_day'])
        monthly['YYYYMM'] = monthly.index.to_period('M')

        if not divs.empty:
            divs_df = pd.DataFrame({'Div': divs})
            divs_df['YYYYMM'] = divs_df.index.to_period('M')
            m_divs = divs_df.groupby('YYYYMM')['Div'].sum()
            monthly['Monthly_Div'] = monthly['YYYYMM'].map(m_divs).fillna(0.0)
        else:
            monthly['Monthly_Div'] = 0.0

        monthly['Price_Return'] = monthly['Close'].pct_change()
        monthly['Div_Yield'] = monthly['Monthly_Div'] / monthly['Close'].shift(1)
        monthly['Div_Yield'] = monthly['Div_Yield'].fillna(0.0)

        return monthly.dropna(subset=['Price_Return'])
    except Exception as e:
        import traceback
        return f"處理 {ticker} 資料發生錯誤：\n{str(e)}\n\n```python\n{traceback.format_exc()}\n```"


@st.cache_data
def prepare_unified_data(t_a, t_b, pay_day, is_reinv):
    df_a = fetch_pure_asset_data(t_a, pay_day)
    if isinstance(df_a, str):
        return df_a, 0, 0
    if df_a is None:
        return "主標的資料獲取失敗。", 0, 0

    len_a_orig = len(df_a)

    if is_reinv and t_b:
        df_b = fetch_pure_asset_data(t_b, pay_day)
        if isinstance(df_b, str):
            return df_b, 0, 0
        if df_b is None:
            return "第二標的資料獲取失敗。", 0, 0
        merged = df_a.join(df_b, lsuffix='_A', rsuffix='_B', how='inner')
        return merged, len_a_orig, len(merged)
    else:
        df_a.columns = [f"{c}_A" if c != 'YYYYMM' else c for c in df_a.columns]
        return df_a, len_a_orig, len_a_orig


data_result = prepare_unified_data(ticker_a, ticker_b, pay_day_option, is_reinvest)

if not isinstance(data_result[0], str):
    data, orig_len, merged_len = data_result
    avail_dates = data.index.strftime('%Y-%m').unique().tolist()

    st.markdown("---")
    st.markdown("### 🎯 選擇您的進場觀測點")
    sel_month = st.selectbox(
        "基準進場月份 (錨定 MC 宇宙起點與微觀追蹤)",
        avail_dates,
        index=avail_dates.index('2022-01') if '2022-01' in avail_dates else 0,
        help="系統將以此月份的真實股價作為起點，計算過去的真實損益，不足的部分無縫接軌未來 Scenario 情境。"
    )
    anchor_idx = avail_dates.index(sel_month)

# ==========================================
# 4. 微觀會計與現金流引擎 (單一路徑)
# ==========================================
def execute_accounting_month(pmt, shares_a, shares_b, price_a, price_b, div_yield_a, div_pool, buf,
                             is_reinv, ratio_b, order, fee_rate, max_sal, eff_haircut):
    """eff_haircut: 該月『額外』流動性折價 (動態)。實際賣股折損 = fee_rate + eff_haircut。"""
    current_div = shares_a * price_a * div_yield_a

    if is_reinv and current_div > 0:
        buy_b_cash = current_div * ratio_b
        buy_a_cash = current_div * (1 - ratio_b)
        shares_b += (buy_b_cash * (1 - fee_rate) / price_b) if price_b > 0 else 0
        shares_a += (buy_a_cash * (1 - fee_rate) / price_a) if price_a > 0 else 0
    else:
        div_pool += current_div

    sell_cost = min(0.99, fee_rate + eff_haircut)  # 賣出總折損率上限保護

    rem = pmt
    used = {"Sal": 0.0, "Div": 0.0, "Buf": 0.0, "ETF": 0.0}
    deducted = set()

    for src in order:
        if rem <= 1e-5:
            break
        if src in deducted:
            continue
        deducted.add(src)

        if src == "配息資金池" and div_pool > 0:
            pay = min(div_pool, rem)
            div_pool -= pay; used["Div"] += pay; rem -= pay
        elif src == "緩衝金" and buf > 0:
            pay = min(buf, rem)
            buf -= pay; used["Buf"] += pay; rem -= pay
        elif src == "變賣資產(主標的)" and shares_a > 0:
            req_cash_before_fee = rem / (1 - sell_cost)
            req_shares = req_cash_before_fee / price_a
            if shares_a >= req_shares:
                shares_a -= req_shares; used["ETF"] += rem; rem = 0
            else:
                yielded_cash = shares_a * price_a * (1 - sell_cost)
                used["ETF"] += yielded_cash; shares_a = 0; rem -= yielded_cash
        elif src == "本薪(自掏腰包)":
            available_sal = max_sal - used["Sal"]
            if available_sal > 0:
                pay = min(available_sal, rem)
                used["Sal"] += pay; rem -= pay

    is_default = (rem > 1e-5)
    return shares_a, shares_b, div_pool, buf, used, is_default

# ==========================================
# 5. 向量化模擬引擎
# ==========================================
def simulate_paths(ret_A_paths, ret_B_paths, div_y_A_paths, p_A_init_arr, p_B_init_arr,
                   pmt_arr, g_p, prin, buf_m, pmt_a_for_buf, fee, is_reinv, r_b, order, max_sal_mat,
                   haircut_trigger, haircut_penalty):
    """
    全向量化。pmt_arr 為逐月應繳排程 (長度 tot_p)，支援利率衝擊。
    max_sal_mat: 形狀 (tot_p, n_paths) 的逐月逐路徑薪資上限 (支援各路徑獨立失業軌跡)。
    動態流動性折價：當 ret_A_paths[i] < -haircut_trigger 的路徑，該月賣股折損額外 +haircut_penalty。
    """
    tot_p = ret_A_paths.shape[0]
    n_paths = ret_A_paths.shape[1]

    prices_a = np.array(p_A_init_arr, dtype=float)
    prices_b = np.array(p_B_init_arr, dtype=float)
    shares_a = (prin - (pmt_a_for_buf * buf_m)) / prices_a
    shares_b = np.zeros(n_paths, dtype=float)
    div_pools = np.zeros(n_paths, dtype=float)
    buf_vals = np.full(n_paths, pmt_a_for_buf * buf_m, dtype=float)
    is_ruined = np.zeros(n_paths, dtype=bool)

    dca_prices_a = np.array(p_A_init_arr, dtype=float)
    dca_prices_b = np.array(p_B_init_arr, dtype=float)
    dca_shares_a = np.zeros(n_paths, dtype=float)
    dca_shares_b = np.zeros(n_paths, dtype=float)
    dca_div_pools = np.zeros(n_paths, dtype=float)

    seen = set()
    uniq_order = []
    for s in order:
        if s not in seen:
            seen.add(s)
            uniq_order.append(s)

    for i in range(tot_p):
        pmt = float(pmt_arr[i])

        ret_a_i = ret_A_paths[i, :]
        prices_a = prices_a * (1 + ret_a_i)
        prices_b = prices_b * (1 + ret_B_paths[i, :])
        dca_prices_a = dca_prices_a * (1 + ret_a_i)
        dca_prices_b = dca_prices_b * (1 + ret_B_paths[i, :])
        div_y_A = div_y_A_paths[i, :]

        current_div = shares_a * prices_a * div_y_A
        if is_reinv:
            with np.errstate(divide='ignore', invalid='ignore'):
                add_b = np.where(prices_b > 0, (current_div * r_b * (1 - fee)) / prices_b, 0.0)
                add_a = np.where(prices_a > 0, (current_div * (1 - r_b) * (1 - fee)) / prices_a, 0.0)
            shares_b = shares_b + add_b
            shares_a = shares_a + add_a
        else:
            div_pools = div_pools + current_div

        # 動態流動性折價：依當月 A 報酬判定，逐路徑的有效賣出折損率
        eff_sell_cost = np.full(n_paths, fee, dtype=float)
        if haircut_penalty > 0:
            triggered = ret_a_i < -haircut_trigger
            eff_sell_cost = np.where(triggered, np.minimum(0.99, fee + haircut_penalty), fee)

        rem = np.where(is_ruined, 0.0, pmt)
        sal_used = np.zeros(n_paths, dtype=float)

        for src in uniq_order:
            if src == "配息資金池":
                pay = np.minimum(div_pools, rem)
                div_pools = div_pools - pay
                rem = rem - pay
            elif src == "緩衝金":
                pay = np.minimum(buf_vals, rem)
                buf_vals = buf_vals - pay
                rem = rem - pay
            elif src == "變賣資產(主標的)":
                max_cash = np.maximum(shares_a * prices_a * (1 - eff_sell_cost), 0.0)
                pay = np.minimum(max_cash, rem)
                with np.errstate(divide='ignore', invalid='ignore'):
                    shares_sold = np.where(prices_a > 0, (pay / (1 - eff_sell_cost)) / prices_a, 0.0)
                shares_a = shares_a - shares_sold
                rem = rem - pay
            elif src == "本薪(自掏腰包)":
                avail = np.maximum(max_sal_mat[i, :] - sal_used, 0.0)
                pay = np.minimum(avail, rem)
                sal_used = sal_used + pay
                rem = rem - pay

        is_ruined = is_ruined | ((rem > 1e-5) & (~is_ruined))

        current_dca_divs = dca_shares_a * dca_prices_a * div_y_A
        if is_reinv:
            with np.errstate(divide='ignore', invalid='ignore'):
                dca_shares_b = dca_shares_b + np.where(dca_prices_b > 0, (current_dca_divs * r_b * (1 - fee)) / dca_prices_b, 0.0)
                dca_shares_a = dca_shares_a + np.where(dca_prices_a > 0, ((current_dca_divs * (1 - r_b) + pmt) * (1 - fee)) / dca_prices_a, 0.0)
        else:
            dca_div_pools = dca_div_pools + current_dca_divs
            with np.errstate(divide='ignore', invalid='ignore'):
                dca_shares_a = dca_shares_a + np.where(dca_prices_a > 0, ((pmt + dca_div_pools) * (1 - fee)) / dca_prices_a, 0.0)
            dca_div_pools = np.zeros(n_paths, dtype=float)

    lev_finals = (shares_a * prices_a * (1 - fee)) + div_pools + buf_vals
    if is_reinv:
        lev_finals = lev_finals + (shares_b * prices_b * (1 - fee))
    lev_finals[is_ruined] = 0

    dca_finals = (dca_shares_a * dca_prices_a * (1 - fee)) + dca_div_pools
    if is_reinv:
        dca_finals = dca_finals + (dca_shares_b * dca_prices_b * (1 - fee))

    return is_ruined, lev_finals, dca_finals


def _build_dividend_model_yields(price_path, p_init, base_ann_yield, beta):
    base_div_amt = p_init * base_ann_yield / 12.0
    cum_ret = (price_path / p_init) - 1.0
    div_amt = np.maximum(base_div_amt * 0.1, base_div_amt * (1 + cum_ret * beta))
    with np.errstate(divide='ignore', invalid='ignore'):
        div_y = np.where(price_path > 0, div_amt / price_path, 0.0)
    return div_y


def _simulate_unemployment_matrix(ret_paths, full_salary, unemp_sal, annual_prob, mean_dur,
                                  dist_type, dur_sigma, crash_on, crash_thr, crash_lo, crash_hi, rng):
    """
    產生逐月逐路徑薪資上限矩陣 (tot_p, n_paths)，模擬隨機失業：
    - 每月以 monthly_base 機率擲骰是否失業 (由年失業率換算)。
    - 黑天鵝相關：當月跌幅 > crash_thr 時，失業機率額外 +U(crash_lo, crash_hi) (年化後換算)。
    - 失業持續時間：對數常態或卜瓦松抽樣，至少 1 個月。
    - 失業中薪資上限 = unemp_sal；其餘月份 = full_salary。
    兩態 Markov：employed <-> unemployed，重新就業後可再次失業。
    """
    tot_p, n_paths = ret_paths.shape
    monthly_base = 1.0 - (1.0 - annual_prob) ** (1.0 / 12.0) if annual_prob > 0 else 0.0
    mat = np.full((tot_p, n_paths), float(full_salary))
    is_unemp = np.zeros(n_paths, dtype=bool)
    remaining = np.zeros(n_paths, dtype=int)

    def draw_dur(n):
        if n == 0:
            return np.array([], dtype=int)
        if dist_type.startswith("卜瓦松"):
            d = rng.poisson(max(mean_dur, 1e-9), size=n)
        else:
            sig = max(0.05, dur_sigma)
            mu = np.log(max(mean_dur, 1e-9)) - 0.5 * sig ** 2
            d = rng.lognormal(mu, sig, size=n)
        return np.maximum(1, np.round(d).astype(int))

    for i in range(tot_p):
        p_loss = np.full(n_paths, monthly_base)
        if crash_on:
            crashed = ret_paths[i, :] < -crash_thr
            extra_ann = rng.uniform(crash_lo, crash_hi, size=n_paths)
            extra_monthly = 1.0 - (1.0 - extra_ann) ** (1.0 / 12.0)
            p_loss = np.where(crashed, np.minimum(0.99, monthly_base + extra_monthly), monthly_base)

        new_loss = (~is_unemp) & (rng.random(n_paths) < p_loss)
        if new_loss.any():
            remaining[new_loss] = draw_dur(int(new_loss.sum()))
            is_unemp[new_loss] = True

        mat[i, is_unemp] = float(unemp_sal)

        remaining[is_unemp] -= 1
        re_emp = is_unemp & (remaining <= 0)
        is_unemp[re_emp] = False
        remaining[re_emp] = 0

    return mat


@st.cache_data
def run_engines(df, prin, pmt_arr, tot_p, g_p, buf_m, pmt_a_for_buf, s_mode, c_path, b_div_y, d_beta,
                s_disc, is_reinv, r_b, order, fee, max_sal_arr, n_paths, b_size, seed, anchor_idx,
                hc_trigger, hc_penalty, swan_m, swan_d, vol_drag_on, job_loss_params):
    max_sal_arr = np.asarray(max_sal_arr, dtype=float)
    (jl_random, jl_unemp_sal, jl_ann_prob, jl_mean_dur, jl_dist, jl_dur_sig,
     jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi) = job_loss_params
    full_salary = float(max_sal_arr.max()) if max_sal_arr.size else 0.0
    m_disc = s_disc / 100.0 / 12.0
    n_hist = len(df)

    if s_mode == "2008 黑天鵝復刻 (先暴跌後復甦)":
        ann_rets = [-45, 78, 10, 5, 15, 2, 8]
    elif s_mode == "失落的十年 (長期熊市陰跌)":
        ann_rets = [-10, -5, -5, 2, 0, -2, 4, 3]
    elif s_mode == "AI 泡沫破裂 (典範轉移)":
        ann_rets = [25, -30, -10, 2, 2, 2, 4]
    else:
        try:
            ann_rets = [float(x.strip()) for x in c_path.split(",")]
        except Exception:
            ann_rets = [5, 5, 5]

    future_m_rets = []
    for ar in ann_rets:
        future_m_rets.extend([(1 + ar / 100.0) ** (1 / 12) - 1] * 12)
    while len(future_m_rets) < tot_p:
        future_m_rets.extend(future_m_rets[-12:])

    # 第二標的 CAPM 係數 + 歷史月報酬標準差 (供 Volatility Drag)
    beta_B, alpha_B, resid_std_B, sigma_A = 1.0, 0.0, 0.0, 0.0
    if len(df) > 1:
        ret_A = df['Price_Return_A'].dropna()
        sigma_A = ret_A.std()
        if is_reinv:
            ret_B = df['Price_Return_B'].dropna()
            cov_mat = np.cov(ret_A, ret_B)
            if cov_mat[0, 0] > 0:
                beta_B = cov_mat[0, 1] / cov_mat[0, 0]
                alpha_B = ret_B.mean() - beta_B * ret_A.mean()
                residuals = ret_B - (alpha_B + beta_B * ret_A)
                resid_std_B = residuals.std()

    # 【V32】Volatility Drag (僅作用於模型合成的未來 r_B)
    # drag ≈ 0.5 × (β × σ_A)^2，每月扣除
    vol_drag = 0.5 * (beta_B * sigma_A) ** 2 if (vol_drag_on and is_reinv) else 0.0

    splice_rng = np.random.RandomState(20240601)

    ret_A_hist = np.zeros((tot_p, n_hist))
    ret_B_hist = np.zeros((tot_p, n_hist))
    div_y_A_hist = np.zeros((tot_p, n_hist))

    win_lens = np.minimum(tot_p, n_hist - np.arange(n_hist))
    is_spliced = win_lens < tot_p

    for i in range(n_hist):
        win_len = min(tot_p, n_hist - i)
        fut_len = tot_p - win_len

        r_A = np.zeros(tot_p)
        r_A[:win_len] = df['Price_Return_A'].iloc[i:i + win_len].values - m_disc
        d_A = np.zeros(tot_p)
        d_A[:win_len] = df['Div_Yield_A'].iloc[i:i + win_len].values
        r_B = np.zeros(tot_p)
        if is_reinv:
            r_B[:win_len] = df['Price_Return_B'].iloc[i:i + win_len].values - m_disc

        if fut_len > 0:
            p_end = df['Close_A'].iloc[i + win_len - 1] if win_len > 0 else df['Close_A'].iloc[0]
            base_div_amt = p_end * b_div_y / 12.0
            p_curr = p_end

            for f in range(fut_len):
                idx = win_len + f
                mr = future_m_rets[f] - m_disc
                r_A[idx] = mr

                if is_reinv:
                    noise = splice_rng.normal(0, resid_std_B) if resid_std_B > 0 else 0
                    # 【V32】合成 r_B 才扣 Volatility Drag (實證真實段不扣)
                    r_B[idx] = alpha_B + mr * beta_B + noise - vol_drag

                p_next = p_curr * (1 + mr)
                cum_ret = (p_next / p_end) - 1
                div_amt = max(base_div_amt * 0.1, base_div_amt * (1 + cum_ret * d_beta))
                d_A[idx] = div_amt / p_curr if p_curr > 0 else 0
                p_curr = p_next

        ret_A_hist[:, i] = r_A
        div_y_A_hist[:, i] = d_A
        ret_B_hist[:, i] = r_B

    # 【V32】黑天鵝注入 (實證引擎)：對所有起點於相對第 swan_m 月注入
    if swan_d > 0 and 1 <= swan_m <= tot_p:
        sm = swan_m - 1
        ret_A_hist[sm, :] = ret_A_hist[sm, :] - swan_d
        if is_reinv:
            # 槓桿標的衝擊以 β 放大 (更貼近正二在崩盤時的實際跌幅)
            ret_B_hist[sm, :] = ret_B_hist[sm, :] - swan_d * beta_B

    p_A_inits_hist = df['Close_A'].values
    p_B_inits_hist = df['Close_B'].values if is_reinv else np.ones(n_hist)

    # 薪資上限矩陣 (tot_p, n_hist)。隨機模型：各起點獨立擲骰失業 (含黑天鵝相關)；否則沿用手動/滿薪 1-D 廣播。
    if jl_random:
        rng_hist = np.random.RandomState(13572468)
        sal_mat_hist = _simulate_unemployment_matrix(
            ret_A_hist, full_salary, jl_unemp_sal, jl_ann_prob, jl_mean_dur, jl_dist, jl_dur_sig,
            jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi, rng_hist)
    else:
        sal_mat_hist = np.repeat(max_sal_arr.reshape(-1, 1), n_hist, axis=1)

    h_ruin, h_lev, h_dca = simulate_paths(
        ret_A_hist, ret_B_hist, div_y_A_hist, p_A_inits_hist, p_B_inits_hist,
        pmt_arr, g_p, prin, buf_m, pmt_a_for_buf, fee, is_reinv, r_b, order, sal_mat_hist,
        hc_trigger, hc_penalty
    )

    df_hist_res = pd.DataFrame({
        'Start_Date': df.index, 'Is_Ruined': h_ruin, 'Is_Spliced': is_spliced,
        'Lev_Final': h_lev, 'DCA_Final': h_dca, 'Lev_Win': (~h_ruin) & (h_lev > h_dca)
    })

    # === MC 引擎 ===
    if seed:
        np.random.seed(42)

    b_size = int(max(1, min(b_size, n_hist)))
    mc_ok = n_hist >= 2

    if mc_ok:
        p_A_init_mc = df['Close_A'].iloc[anchor_idx]
        p_B_init_mc = df['Close_B'].iloc[anchor_idx] if is_reinv else 1.0

        blocks_needed = (tot_p // b_size) + 1
        start_indices = np.random.randint(0, n_hist - b_size + 1, size=(blocks_needed, n_paths))
        idx_matrix = np.array([np.arange(s, s + b_size) for s in start_indices.flatten()]).reshape(blocks_needed, n_paths, b_size)
        idx_matrix = np.transpose(idx_matrix, (0, 2, 1)).reshape(-1, n_paths)[:tot_p, :]

        ret_A_mc = df['Price_Return_A'].values[idx_matrix] - m_disc
        # MC 用真實歷史報酬 (已含波動耗損) -> 不扣 vol_drag
        ret_B_mc = df['Price_Return_B'].values[idx_matrix] - m_disc if is_reinv else np.zeros((tot_p, n_paths))

        # 黑天鵝注入 (MC 引擎)
        if swan_d > 0 and 1 <= swan_m <= tot_p:
            sm = swan_m - 1
            ret_A_mc[sm, :] = ret_A_mc[sm, :] - swan_d
            if is_reinv:
                ret_B_mc[sm, :] = ret_B_mc[sm, :] - swan_d * beta_B

        price_path_a_mc = p_A_init_mc * np.cumprod(1 + ret_A_mc, axis=0)
        div_y_A_mc = _build_dividend_model_yields(price_path_a_mc, p_A_init_mc, b_div_y, d_beta)

        # MC 薪資上限矩陣：每條路徑獨立擲骰失業 (圍繞設定失業率 + 黑天鵝相關)。
        if jl_random:
            rng_mc = np.random.RandomState(42) if seed else np.random.RandomState()
            sal_mat_mc = _simulate_unemployment_matrix(
                ret_A_mc, full_salary, jl_unemp_sal, jl_ann_prob, jl_mean_dur, jl_dist, jl_dur_sig,
                jl_crash_on, jl_crash_thr, jl_crash_lo, jl_crash_hi, rng_mc)
            unemp_mask = sal_mat_mc < full_salary
            jl_any_rate = float(unemp_mask.any(axis=0).mean())
            jl_avg_months = float(unemp_mask.sum(axis=0).mean())
        else:
            sal_mat_mc = np.repeat(max_sal_arr.reshape(-1, 1), n_paths, axis=1)
            jl_any_rate, jl_avg_months = 0.0, 0.0

        m_ruin, m_lev, m_dca = simulate_paths(
            ret_A_mc, ret_B_mc, div_y_A_mc, np.full(n_paths, p_A_init_mc), np.full(n_paths, p_B_init_mc),
            pmt_arr, g_p, prin, buf_m, pmt_a_for_buf, fee, is_reinv, r_b, order, sal_mat_mc,
            hc_trigger, hc_penalty
        )
        df_mc_res = pd.DataFrame({
            'Is_Ruined': m_ruin, 'Lev_Final': m_lev, 'DCA_Final': m_dca, 'Lev_Win': (~m_ruin) & (m_lev > m_dca)
        })
    else:
        df_mc_res = pd.DataFrame(columns=['Is_Ruined', 'Lev_Final', 'DCA_Final', 'Lev_Win'])
        jl_any_rate, jl_avg_months = 0.0, 0.0

    trace_data = {
        'r_A': ret_A_hist[:, anchor_idx],
        'r_B': ret_B_hist[:, anchor_idx],
        'd_A': div_y_A_hist[:, anchor_idx],
        'p_a_init': df['Close_A'].iloc[anchor_idx],
        'p_b_init': df['Close_B'].iloc[anchor_idx] if is_reinv else 1.0,
        'max_sal_path': sal_mat_hist[:, anchor_idx],
        'jl_any_rate': jl_any_rate,
        'jl_avg_months': jl_avg_months,
    }

    return df_hist_res, df_mc_res, trace_data, b_size, mc_ok, vol_drag

# ==========================================
# 6. UI 渲染與微觀 Trace
# ==========================================
if isinstance(data_result[0], str):
    st.error(f"❌ 資料獲取異常：\n\n{data_result[0]}")
elif 'anchor_idx' in locals():
    if merged_len < orig_len - 12:
        st.error(f"⚠️ **歷史生存者偏差警告 (Survivorship Bias Alert)** ⚠️\n\n主標的 `{ticker_a}` 原本擁有 {orig_len} 個月的歷史資料，但為了與較晚上市的 `{ticker_b}` 進行時間軸對齊 (Inner Join)，系統被迫**裁切掉了 {orig_len - merged_len} 個月的舊資料**。\n\n這意味著您的歷史回測可能**遺漏了 2008 年金融海嘯等極端熊市**，導致勝率被樂觀高估！若要測試長線韌性，建議使用上市較久的 ETF 作為替代標的。")

    pmt_a_for_buf = float(pmt_schedule[grace_periods]) if grace_periods < periods else float(pmt_schedule[-1])

    hist_res, mc_res, t_data, eff_block, mc_ok, applied_vol_drag = run_engines(
        data, loan_principal, pmt_schedule, periods, grace_periods, buffer_months, pmt_a_for_buf,
        scenario_mode, custom_path_str, base_div_yield, div_beta, structural_discount, is_reinvest, reinvest_ratio_b, strat_order,
        trx_fee, max_sal_arr, mc_paths, block_size, use_fixed_seed, anchor_idx,
        haircut_trigger, haircut_penalty, swan_month, swan_drop, enable_vol_drag, job_loss_params
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("初期每月應繳 (DCA 金額)", f"${int(pmt_schedule[0]):,}")
    col2.metric("寬限期後每月應繳", f"${int(pmt_a_for_buf):,}")
    col3.metric("初始現金緩衝", f"${int(required_buffer):,}")

    # V32 啟用情境提示列
    active_flags = []
    if enable_rate_shock:
        active_flags.append(f"利率衝擊(第{rate_shock_year}年 +{rate_shock_delta}%)")
    if enable_black_swan:
        active_flags.append(f"黑天鵝(第{swan_month}月 -{int(swan_drop*100)}%)")
    if enable_dyn_haircut:
        active_flags.append(f"動態折價(跌>{int(haircut_trigger*100)}% 加扣{haircut_penalty*100:.1f}%)")
    if enable_vol_drag and is_reinvest:
        active_flags.append(f"Vol Drag(月扣{applied_vol_drag*100:.3f}%)")
    if enable_job_loss:
        if jl_random_on:
            crash_txt = f" 崩盤(跌>{int(jl_crash_thr*100)}%)加+{int(jl_crash_lo*100)}~{int(jl_crash_hi*100)}%" if jl_crash_on else ""
            active_flags.append(
                f"隨機失業(年率{jl_annual_prob*100:.1f}% 平均{jl_mean_dur:.0f}月/{jl_dist} 薪資上限${int(job_loss_salary):,}{crash_txt}"
                f"｜MC失業率{t_data['jl_any_rate']*100:.1f}% 平均失業{t_data['jl_avg_months']:.1f}月)")
        else:
            active_flags.append(f"失業/降薪(第{job_loss_start}月起 {job_loss_duration}個月 薪資上限${int(job_loss_salary):,})")
    if active_flags:
        st.caption("🟢 已啟用情境： " + " ｜ ".join(active_flags))
    st.markdown("---")

    c1, c2 = st.columns(2)
    c1.markdown("#### 【實證】歷史滾動與情境拼接宇宙")
    c1.caption("基於過去真實軌跡拼接未來情境，測算特定時間點進場的「確定性 What-If」結果。")
    if not hist_res.empty:
        n_total = len(hist_res)
        n_spliced = int(hist_res['Is_Spliced'].sum())
        n_pure = n_total - n_spliced

        c1.metric("槓桿破產率 (全部起點)", f"{hist_res['Is_Ruined'].mean() * 100:.1f}%")
        pure = hist_res[~hist_res['Is_Spliced']]
        if n_pure > 0:
            c1.metric(f"⤷ 僅『純歷史』起點破產率 (n={n_pure})", f"{pure['Is_Ruined'].mean() * 100:.1f}%")
        c1.caption(f"共 {n_total} 個起點：純歷史 {n_pure} 個、含未來情境拼接 {n_spliced} 個。"
                   f"{'⚠️ 拼接起點全部共用同一條 scenario 劇本，彼此高度相關，其破產率不代表獨立統計分佈，僅供單一劇本壓力參考。' if n_spliced > 0 else ''}")

        c1.metric("槓桿擊敗 DCA 勝率 (全部起點)", f"{hist_res['Lev_Win'].mean() * 100:.1f}%")
        h_med = hist_res.loc[~hist_res['Is_Ruined'], 'Lev_Final'].median()
        c1.metric("槓桿期滿中位數 (存活者)", f"${int(h_med):,}" if not pd.isna(h_med) else "無")
        c1.metric("DCA 定期定額 期滿中位數", f"${int(hist_res['DCA_Final'].median()):,}")

    c2.markdown(f"#### 【理論】錨定當前股價之 MC 宇宙 ({mc_paths}次)")
    c2.caption(f"全歷史 Block Bootstrap (區塊={eff_block}月) 純統計重抽樣；配息由 Dividend Beta 模型驅動。"
               "**不套用 Scenario 劇本**（但黑天鵝/利率/動態折價情境仍生效）。")
    if mc_ok and not mc_res.empty:
        c2.metric("槓桿破產率 (現金流斷裂)", f"{mc_res['Is_Ruined'].mean() * 100:.1f}%")
        c2.metric("槓桿擊敗 DCA 勝率", f"{mc_res['Lev_Win'].mean() * 100:.1f}%")
        m_med = mc_res.loc[~mc_res['Is_Ruined'], 'Lev_Final'].median()
        c2.metric("槓桿期滿中位數 (存活者)", f"${int(m_med):,}" if not pd.isna(m_med) else "無")
        c2.metric("DCA 定期定額 期滿中位數", f"${int(mc_res['DCA_Final'].median()):,}")
    else:
        c2.warning("歷史資料過短 (< 2 個月)，無法進行有意義的 Block Bootstrap 模擬。")

    if not hist_res.empty:
        st.markdown("##### 實證拼接測試期滿淨值分佈 (槓桿策略)")
        fig_hist = px.bar(hist_res, x='Start_Date', y='Lev_Final', color='Is_Ruined',
                          pattern_shape='Is_Spliced',
                          color_discrete_map={True: '#E74C3C', False: '#1ABC9C'},
                          labels={'Start_Date': '進場月份', 'Lev_Final': '期滿資產淨值 (元)',
                                  'Is_Ruined': '破產(斷頭)', 'Is_Spliced': '含未來情境拼接'})
        st.plotly_chart(fig_hist, width='stretch')
        st.caption("有斜線紋路的長條 = 該起點歷史資料不足、已拼接未來 scenario 劇本，請謹慎解讀。")

    st.markdown("---")
    st.header("🔍 微觀路徑追蹤與 Accounting Trace")
    st.info("💡 提醒：此微觀追蹤僅代表您選擇進場月份的「單一平行宇宙」展開，請參考上方 MC 引擎的整體破產率來評估真實系統性風險。")

    loan_bal, buf_val = loan_principal, required_buffer
    shares_a = (loan_principal - buf_val) / t_data['p_a_init']
    shares_b, div_pool = 0.0, 0.0
    dca_shares_a = 0.0
    dca_shares_b = 0.0
    dca_div_pool = 0.0
    records = []

    p_a_curr = t_data['p_a_init']
    p_b_curr = t_data['p_b_init']

    for i in range(periods):
        curr_pmt = float(pmt_schedule[i])
        r_m_i = float(rate_schedule[i])
        int_paid = loan_bal * r_m_i
        prin_paid = 0 if i < grace_periods else max(0.0, curr_pmt - int_paid)
        loan_bal -= prin_paid

        r_a_i = t_data['r_A'][i]
        r_b_i = t_data['r_B'][i]
        # 微觀追蹤同步套用黑天鵝注入 (與實證引擎一致)
        if enable_black_swan and (i + 1) == swan_month:
            r_a_i = r_a_i - swan_drop
            r_b_i = r_b_i - swan_drop  # 微觀單路徑以原始衝擊呈現

        p_a_curr *= (1 + r_a_i)
        p_b_curr *= (1 + r_b_i)
        div_y_A = t_data['d_A'][i]

        # 微觀動態折價
        eff_hc = haircut_penalty if (enable_dyn_haircut and r_a_i < -haircut_trigger) else 0.0

        shares_a, shares_b, div_pool, buf_val, used, is_def = execute_accounting_month(
            curr_pmt, shares_a, shares_b, p_a_curr, p_b_curr, div_y_A, div_pool, buf_val,
            is_reinvest, reinvest_ratio_b, strat_order, trx_fee, float(t_data['max_sal_path'][i]), eff_hc
        )

        lev_val = (shares_a * p_a_curr * (1 - trx_fee)) + div_pool + buf_val
        if is_reinvest and p_b_curr > 0:
            lev_val += (shares_b * p_b_curr * (1 - trx_fee))

        current_dca_divs = dca_shares_a * p_a_curr * div_y_A
        if is_reinvest:
            if p_b_curr > 0:
                dca_shares_b += (current_dca_divs * reinvest_ratio_b * (1 - trx_fee)) / p_b_curr
            if p_a_curr > 0:
                dca_shares_a += ((current_dca_divs * (1 - reinvest_ratio_b) + curr_pmt) * (1 - trx_fee)) / p_a_curr
        else:
            dca_div_pool += current_dca_divs
            if p_a_curr > 0:
                dca_shares_a += ((curr_pmt + dca_div_pool) * (1 - trx_fee)) / p_a_curr
                dca_div_pool = 0.0

        dca_val = (dca_shares_a * p_a_curr * (1 - trx_fee)) + dca_div_pool
        if is_reinvest and p_b_curr > 0:
            dca_val += (dca_shares_b * p_b_curr * (1 - trx_fee))

        if anchor_idx + i < len(data):
            trace_date = data.index[anchor_idx + i].strftime('%Y-%m')
        else:
            fut_months = (anchor_idx + i) - len(data) + 1
            trace_date = (data.index[-1] + pd.DateOffset(months=fut_months)).strftime('%Y-%m (預測)')

        records.append({
            '相對期數': i + 1,
            '真實/預測月份': trace_date,
            '總資產淨值(槓桿)': max(lev_val, 0),
            '總資產淨值(DCA)': max(dca_val, 0),
            '貸款剩餘餘額': max(loan_bal, 0),
            '當期年利率(%)': r_m_i * 12 * 100,
            '破產(斷頭)': is_def,
            '每月應繳本息': curr_pmt,
            '來自配息資金池': used["Div"],
            '來自緩衝金': used["Buf"],
            '變賣主資產': used["ETF"],
            '本薪(自掏腰包)': used["Sal"],
            '主資產股數': shares_a,
            '再投入資產股數': shares_b
        })
        if is_def:
            break

    if records:
        df_trace = pd.DataFrame(records)

        fig1 = px.line(df_trace, x='真實/預測月份', y=['總資產淨值(槓桿)', '總資產淨值(DCA)', '貸款剩餘餘額'],
                       color_discrete_map={'總資產淨值(槓桿)': '#3498DB', '總資產淨值(DCA)': '#9B59B6', '貸款剩餘餘額': '#F39C12'},
                       hover_data={'相對期數': True})
        fig1.update_xaxes(type='category')
        st.plotly_chart(fig1, width='stretch')

        st.markdown("##### 槓桿策略：每月貸款繳納資金來源拆解")
        fig2 = px.bar(df_trace, x='真實/預測月份', y=['來自配息資金池', '來自緩衝金', '變賣主資產', '本薪(自掏腰包)'],
                      color_discrete_map={'來自配息資金池': '#F1C40F', '來自緩衝金': '#2ECC71', '變賣主資產': '#3498DB', '本薪(自掏腰包)': '#E74C3C'},
                      hover_data={'相對期數': True})
        fig2.update_xaxes(type='category')
        st.plotly_chart(fig2, width='stretch')

        st.markdown("##### 會計明細 (Accounting Trace Ledger)")
        format_dict = {c: "{:,.2f}" if ('股數' in c or '利率' in c) else "${:,.0f}" for c in df_trace.columns if c not in ['真實/預測月份', '相對期數', '破產(斷頭)']}
        st.dataframe(df_trace.style.format(format_dict), width='stretch')

        csv = df_trace.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載完整會計明細 (CSV)", data=csv, file_name=f"trace_進場{sel_month}.csv", mime="text/csv")
