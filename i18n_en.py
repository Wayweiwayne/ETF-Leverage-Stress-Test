"""English wording of every Chinese sentence the app shows (see i18n.py).

The key is the Chinese source text exactly as it is written in the code; the value has the same placeholders.
Style: Simplified Technical English, sentence case, short active sentences; terms follow DESIGN-v40 section 4.3
(default = 破產, DCA = 定期定額, amounts in NT$). test_i18n.py checks that nothing is missing or left over.
"""
EN = {

    # ---- app.py ----
    "借錢投資 ETF 壓力測試 {APP_VERSION}":
        "Borrow-to-Invest ETF Stress Test {APP_VERSION}",
    "壓力測試":
        "Stress test",
    "計算方法說明":
        "How it works",

    # ---- main_page.py ----
    "❌ 「{name}」這一段暫時無法顯示，其他結果不受影響。":
        "❌ Couldn't show \"{name}\". The other results are not affected.",
    "借錢投資 ETF 壓力測試 ({APP_VERSION})":
        "Borrow-to-Invest ETF Stress Test ({APP_VERSION})",
    "📖 每個欄位旁的問號有白話說明；想看公式和計算方式，點側欄最上方的「計算方法說明」。":
        "📖 Each ? next to a field explains it in plain words. For the formulas and how the numbers are worked out, open \"How it works\" at the top of the sidebar.",
    "最先動用的錢。薪水＝自己掏錢；存下來的配息＝還沒用掉的股息；緩衝金＝一開始預留的現金；賣第一標的＝賣掉用貸款買的那檔；賣第二標的＝賣掉用配息買進的第二檔。":
        "The first money to use. Salary = your own money. Saved dividends = dividends you haven't spent yet. Cash buffer = the cash you set aside at the start. Sell main ETF = sell the ETF you bought with the loan. Sell second ETF = sell the second ETF you bought with dividends.",
    "重新載入行情":
        "Reload market data",
    "{APP_VERSION}｜本程式為自由軟體，以 AGPL-3.0 授權，不提供任何擔保。原始碼：[{v1}]({SOURCE_URL})":
        "{APP_VERSION} | This program is free software under the AGPL-3.0 license, with no warranty. Source code: [{v1}]({SOURCE_URL})",
    "不適用":
        "N/A",
    "📦 這是單機版：在瀏覽器裡直接執行，不需要安裝任何東西。可以使用所有台灣上市的 ETF（目前 {v1} 檔，每天自動更新），代號請加上 .TW，例如 0056.TW。無法即時查詢上市 ETF 以外的商品，要測試其他代號請使用網頁版。":
        "📦 This is the standalone version. It runs in your browser and you install nothing. You can use every ETF listed in Taiwan ({v1} now, updated every day). Add .TW to the ticker, for example 0056.TW. It can't look up anything else live. To test other tickers, use the web version.",
    "自動重算":
        "Auto-recalculate",
    "1. 貸款條件":
        "1. Loan",
    "貸款種類":
        "Loan type",
    "你打算借多少錢來投資。例如填 300 就是借 300 萬。":
        "How much you plan to borrow to invest. For example, enter 300 for NT$3 million.",
    "一開始預留幾個月的還款現金":
        "Cash buffer at the start (months of payments)",
    "貸款年利率 (%)":
        "Annual interest rate (%)",
    "貸款總年限 (年)":
        "Loan term (years)",
    "每月貸款扣款日":
        "Monthly payment day",
    "##### 📈 利率會變動":
        "##### 📈 Rates can change",
    "模擬「升息」情況":
        "Simulate a rate hike",
    "浮動利率：利率每年都可能變":
        "Variable rate: the rate can change every year",
    "2. 買什麼、配息怎麼用":
        "2. What you buy and what happens to dividends",
    "第一標的（借來的錢買這檔，如 0056.TW）":
        "Main ETF (the one you buy with the loan, such as 0056.TW)",
    "上市前的歷史用哪一檔代替 (選填)":
        "Stand-in ETF for history before listing (optional)",
    "配息拿去再買股票（不拿來繳貸款）":
        "Reinvest dividends (don't use them for loan payments)",
    "3. 每月還款的錢從哪來":
        "3. Where each monthly payment comes from",
    "設定每月繳貸款時，優先動用哪一筆錢。系統會從第一順位開始用，不夠才往下一個。每個來源只能排一次；不想動用的來源，把多出來的順位選成「（不使用）」即可。":
        "Choose which money pays the loan first each month. The tool starts with the 1st choice and moves to the next one only when the money runs out. Each source can be used once. To skip a source, set the extra choices to \"(Not used)\".",
    "每月最多自掏多少 (元)":
        "Monthly out-of-pocket limit (NT$)",
    "##### 💼 失業或降薪":
        "##### 💼 Job loss or pay cut",
    "模擬失業或降薪":
        "Simulate job loss or a pay cut",
    "##### 💧 急著賣股的「賤賣」損失":
        "##### 💧 Fire-sale loss when you must sell fast",
    "模擬「崩盤時被迫賤賣」":
        "Simulate a fire-sale loss in a crash",
    "4. 假想未來情境":
        "4. Assumed future",
    "如果你的貸款年限比股票的歷史資料還長，超出的那段「未來」系統就用底下選的劇本來填。（旁邊的蒙地卡羅模擬不套用這個劇本，它是另一種純統計的算法。）":
        "If your loan term is longer than the ETF's history, the tool fills the missing future with the scenario you pick below. (The Monte Carlo simulation does not use this scenario. It is a separate, purely statistical method.)",
    "假設未來會發生什麼":
        "What do you assume will happen?",
    "##### 🦢 突發大崩盤測試":
        "##### 🦢 Sudden crash test",
    "在某個月強制塞入一次暴跌":
        "Force one big drop in a chosen month",
    "##### 💰 未來的股息":
        "##### 💰 Future dividends",
    "未來的配息多久發一次":
        "How often future dividends are paid",
    "股息跟著市場起伏的程度":
        "How closely dividends follow the market",
    "5. 進階設定":
        "5. Advanced",
    "每年報酬再扣掉多少 (%)":
        "Extra yearly return to subtract (%)",
    "##### ⚙️ 槓桿 ETF 的隱藏耗損":
        "##### ⚙️ Hidden cost of leveraged ETFs",
    "把槓桿 ETF 的「來回震盪虧損」算進去":
        "Include the volatility decay of leveraged ETFs",
    "自動還原來源沒處理的股票分割":
        "Repair stock splits the source did not adjust",
    "定期定額對照組每月投入多少":
        "How much the DCA comparison invests each month",
    "蒙地卡羅的配息怎麼算":
        "How Monte Carlo treats dividends",
    "蒙地卡羅要模擬幾次":
        "Monte Carlo simulations to run",
    "模擬時每次抽幾個月一組 (月)":
        "Months drawn at a time in the simulation",
    "固定亂數（同樣設定得到同樣結果）":
        "Same random draws every run (same settings, same results)",
    "6. 稅與費用":
        "6. Taxes and fees",
    "預設用台灣現行的費率。槓桿策略和定期定額對照組都適用同一套規則。":
        "The standard Taiwan rates are used. The leveraged strategy and the DCA comparison follow the same rules.",
    "扣二代健保補充保費 (2.11%)":
        "Deduct the NHI supplementary premium (2.11%)",
    "你的綜合所得稅級距（決定股利要繳多少稅）":
        "Your income tax bracket (sets the tax on dividends)",
    "貸款開辦費 (元)":
        "Loan setup fee (NT$)",
    "平常會優先使用一天半以內的存檔，不必每次都向行情來源重抓。按這個按鈕會略過存檔，直接向 Yahoo Finance 重新取得這幾檔標的最新的價格與配息，並立刻重新計算。":
        "Normally the tool uses a saved copy that is less than a day and a half old, so it doesn't fetch from the data source every time. This button skips the saved copy, gets the latest prices and dividends of these ETFs from Yahoo Finance, and recalculates right away.",
    "行情資料暫時無法處理。請稍後再試，或按側欄的「重新載入行情」。":
        "Couldn't process the market data. Try again later, or press \"Reload market data\" in the sidebar.",
    "歷史回測":
        "Historical backtest",
    "蒙地卡羅模擬（{mc_paths:,} 次）":
        "Monte Carlo simulation ({mc_paths:,} runs)",
    "📋 使用的資料：{index:%Y-%m} 至 {index1:%Y-%m}，共 {n_months} 個月":
        "📋 Data used: {index:%Y-%m} to {index1:%Y-%m}, {n_months} months",
    "貸款":
        "Loan",
    "初期每月應繳":
        "Monthly payment at first",
    "寬限期後每月應繳":
        "Monthly payment after interest-only period",
    "開局預留的緩衝金":
        "Cash buffer at the start",
    "#### 📜 歷史回測：如果當年進場":
        "#### 📜 Historical backtest: if you had started back then",
    "把歷史上每個月都當成進場點，之後照真實走勢走；真實資料不夠長的部分接上假想未來，得到「如果當時進場會怎樣」的結果。":
        "Every month in the history is used as a start month, and the real prices play out from there. Where the real data is too short, the assumed future fills in. You see what would have happened if you had started then.",
    "#### 🎲 蒙地卡羅模擬：{mc_paths:,} 種可能的未來":
        "#### 🎲 Monte Carlo simulation: {mc_paths:,} possible futures",
    "配息跟著報酬一起從歷史重抽，是當時實際發的金額，平均一年約 {v1:.1f}%。":
        "Dividends are drawn from history together with the returns. They are the amounts actually paid back then, about {v1:.1f}% a year on average.",
    "配息照你設定的「未來平均股息」計算，平均一年約 {v1:.1f}%。":
        "Dividends follow your \"average future dividend\" setting, about {v1:.1f}% a year on average.",
    "從整段歷史裡每次抽連續 {block_size} 個月，重新拼成 {mc_paths:,} 種可能的未來，和哪個月進場無關。{mc_dividend_note}**不套用側欄第 4 段的假想未來**，但升息、突發大崩盤、崩盤賤賣等設定仍然有效。":
        "Each run draws {block_size} months in a row from the whole history and joins the pieces into {mc_paths:,} possible futures. The start month doesn't matter. {mc_dividend_note} **The assumed future in sidebar section 4 is not used**, but rate hikes, the sudden crash and the fire-sale loss still apply.",
    "❌ 資料獲取異常：\n\n{loaded}":
        "❌ Couldn't get the data:\n\n{loaded}",
    "槓桿：九成的結果落在這裡":
        "Leveraged: 90% of outcomes fall in this band",
    "槓桿：一半的結果落在這裡":
        "Leveraged: half of outcomes fall in this band",
    "進場後第幾個月":
        "Month since start",
    "金額 (元)":
        "Amount (NT$)",
    "貸款第幾年":
        "Loan year",
    "破產的模擬次數":
        "Simulations that defaulted",
    "房貸通常利率低、可以借很多年，但需要拿房子抵押；信貸不用抵押品，但利率較高、年限較短。":
        "A home-equity loan usually has a lower rate and a longer term, but you must put up your home as collateral. A personal loan needs no collateral, but the rate is higher and the term is shorter.",
    "貸款本金 (萬)":
        "Loan amount (in NT$10,000)",
    "開局時先留一筆現金當「緩衝」，相當於先存好幾個月的還款。留越多越安全，但能投入市場的本金就越少。":
        "Sets aside some cash at the start as a \"buffer\". It works like saving several months of payments in advance. A bigger buffer is safer, but less money goes into the market.",
    "銀行每年跟你收的利息比率。這是這個策略最重要的「成本」——你的投資報酬必須跑贏它才划算。":
        "The interest the bank charges you each year. This is the most important cost of the strategy: your investment return must beat it to be worth it.",
    "你要花幾年把這筆錢還完。年限越長、每月還得越少，但付的總利息越多。":
        "How many years you take to repay the loan. A longer term means smaller monthly payments but more total interest.",
    "啟用寬限期":
        "Use an interest-only period",
    "貸款年限只有 1 年，無法設定寬限期。":
        "The loan term is only 1 year, so an interest-only period isn't available.",
    "每個月銀行從你帳戶扣款的日子。系統會用當月接近這天的股價來計算。":
        "The day each month the bank takes the payment from your account. The tool uses prices near that day of the month.",
    "銀行的利率不是永遠不變的。打開這個，可以模擬「借錢幾年後遇到升息」的情況，看看每月還款變貴後策略還撐不撐得住。":
        "Bank rates don't stay the same forever. Turn this on to see what happens if rates rise some years after you borrow, and whether the strategy can handle the higher payments.",
    "從第幾年開始升息":
        "Rate hike starts in year",
    "利率調高多少 (+%)":
        "Rate increase (+%)",
    "多數房貸和信貸是浮動利率，會跟著央行升降息調整。打開後可以排定之後每年利率各調多少，也可以讓蒙地卡羅在這條路徑之外再加上隨機的升降息。每次利率變動，月付金都會依剩餘本金和剩餘期數重算。":
        "Most home and personal loans have a variable rate that follows the central bank. When this is on, you can set how much the rate changes each year. You can also let Monte Carlo add random rate changes on top of this path. Each time the rate changes, the monthly payment is recalculated from the remaining balance and remaining months.",
    "第 2 年起，每年利率調整多少（百分點），用逗號分開":
        "Rate change each year from year 2 (percentage points), separated by commas",
    "蒙地卡羅：每年再隨機升降多少（標準差，百分點）":
        "Monte Carlo: random yearly rate change (standard deviation, percentage points)",
    "你借來的錢主要拿去買的股票或 ETF 代號。記得加上 .TW（台股）。":
        "The ticker of the stock or ETF you mainly buy with the borrowed money. Add .TW for Taiwan-listed stocks.",
    "第一標的如果上市不久，歷史只涵蓋最近幾年，容易全是多頭、看不到大空頭。這裡可以填一檔性質相近、上市更久的標的；第一標的上市前的月份，就直接用它當時的實際漲跌與配息代替，讓回測與蒙地卡羅都能涵蓋更長的歷史（例如 2008 年）。留空代表只用第一標的自己的歷史。如果替身的歷史沒有比較長，這個欄位不會有任何作用。":
        "If the main ETF was listed only recently, its history covers just a few years. That is often all bull market, with no big bear market. You can enter a similar ETF that was listed earlier. For the months before the main ETF was listed, the tool uses that ETF's actual price moves and dividends instead. Backtest and Monte Carlo can then cover a longer history (for example 2008). Leave it empty to use only the main ETF's own history. If the stand-in's history is not longer, this field has no effect.",
    "勾選後，領到的股息不拿去繳貸款，而是再買進股票滾入投資。不勾選的話，股息會先存起來幫忙繳貸款。":
        "When on, dividends are not used for loan payments. They buy more shares instead. When off, dividends are saved first and help pay the loan.",
    "第二標的（用配息加買這檔，如 00631L.TW）":
        "Second ETF (bought with dividends, such as 00631L.TW)",
    "所有順位都選了「（不使用）」，等於沒有任何錢可以繳貸款，第一個月就會破產。":
        "Every choice is set to \"(Not used)\", so no money is available to pay the loan and you default in the first month.",
    "當其他來源都不夠繳貸款時，你每個月最多願意從薪水掏多少出來補。設太高，幾乎不會破產（因為一直有薪水撐）；設低一點，比較能看出策略本身扛不扛得住。":
        "When the other sources run short, this is the most you are willing to pay from your salary each month. If it is very high, you will almost never default, because your salary always covers the gap. A lower limit shows better whether the strategy holds up by itself.",
    "打開後可以模擬某段期間薪水大幅縮水甚至歸零，測試這段期間只靠配息與變賣資產能否撐住貸款。找到工作後薪水自動恢復原本的補貼上限。":
        "Simulates a period when your salary drops sharply or to zero. It tests whether dividends and asset sales can carry the loan through that period. When you find work, your salary goes back to the normal out-of-pocket limit.",
    "失業模型":
        "Job-loss model",
    "失業或降薪期間，每月最多自掏多少 (元)":
        "Monthly out-of-pocket limit during job loss or pay cut (NT$)",
    "買賣手續費與滑價 (%)":
        "Trading fee and slippage (%)",
    "市場大跌時，如果你急著賣股票換錢繳貸款，常常只能用更差的價格脫手（賣壓大、流動性差）。打開這個會把這種「賤賣損失」算進去，讓崩盤情境更真實。":
        "In a big drop, if you must sell shares quickly to pay the loan, you often get a worse price (heavy selling, poor liquidity). Turn this on to include that fire-sale loss and make crash scenarios more realistic.",
    "挑一個你想測試的未來劇本。例如「2008 復刻」會先模擬一次大崩盤再慢慢漲回來，看看策略能不能熬過去。":
        "Pick a future scenario to test. For example, \"2008 replay\" first simulates a big crash and then a slow recovery, to see whether the strategy survives.",
    "輸入未來每年報酬率 (%)，用逗號分開":
        "Enter each future year's return (%), separated by commas",
    "手動在你指定的那個月，硬塞一次單月大暴跌，測試策略在最壞時間點遇到崩盤會怎樣。歷史回測和蒙地卡羅模擬都會套用。":
        "Forces one big one-month drop in the month you choose. It tests what happens if a crash hits at the worst moment. Both the backtest and Monte Carlo use it.",
    "在進場後第幾個月暴跌":
        "Drop happens in month",
    "未來平均一年發多少股息 (%)":
        "Average dividend per year in the future (%)",
    "同樣一年發 6%，每個月發一點和每季發一大筆，對現金流的影響不一樣：沒發的月份只能靠其他來源繳貸款，而且單筆金額越大，越容易超過二代健保補充保費的門檻。「自動判斷」會看這檔標的最近三年實際多久配一次。這只影響用股息模型算出來的配息（假想未來那段），真實資料的月份照實際發放日。":
        "Paying 6% a year as a little each month or a big amount each quarter affects cash flow differently. In months with no dividend, other sources must pay the loan. Also, a bigger single payment is more likely to pass the threshold for the NHI supplementary premium. \"Same as history (automatic)\" looks at how often this ETF paid over the last three years. This only affects dividends made by the dividend model (the assumed-future part). Months with real data use the real payment dates.",
    "市場好的時候公司賺得多、發的股息通常也多；市場差時股息會縮水。這個拉桿設定股息跟市場連動的強弱：設 0 代表不管漲跌都固定發，設 1 代表跟市場連動很大。就算遇到崩盤，系統仍保證至少發出基本金額的 10%，不會完全歸零。":
        "When the market does well, companies earn more and usually pay more. When it does badly, dividends shrink. This slider sets how strongly dividends follow the market. At 0, dividends stay fixed whatever the market does. At 1, they follow the market closely. Even in a crash, the tool always pays at least 10% of the base amount, so dividends never drop to zero.",
    "有些 ETF 因為內扣費用、追蹤誤差等原因，長期報酬會被悄悄侵蝕一點。這裡可以設定每年自動扣掉多少，模擬這種長期耗損。一般可先設 0。":
        "Some ETFs lose a little return over time to internal costs, tracking error and similar causes. You can set how much to subtract each year to simulate this long-term drag. You can leave it at 0.",
    "第二標的沒有真實資料的月份（它上市前，以及「假想未來」那段），系統要用第一標的的漲跌去推估它。像正二這種每日調整的槓桿型 ETF，市場來回震盪時會悄悄虧損一點，但連續上漲或連續下跌時，複利又會讓它賺得比「直接乘兩倍」多、賠得比較少。打開這個，推估時會用槓桿 ETF 的標準公式把這兩種效果一起算進去；關掉則單純用「第一標的漲跌 × 倍數」。真實歷史資料本身已經含這些效果，不受這個開關影響。":
        "For months when the second ETF has no real data (before it was listed, and the \"assumed future\" part), the tool estimates it from the main ETF's moves. A daily-reset leveraged ETF, such as a 2x ETF, quietly loses a little when the market goes up and down. But in a long run of rises or falls, compounding helps it gain more and lose less than simply \"2 times\". When this is on, the estimate uses the standard leveraged-ETF formula and includes both effects. When it is off, the tool simply uses \"main ETF move × multiple\". Real historical data already includes these effects, so this switch doesn't change it.",
    "行情來源對部分台股 ETF（例如 0050、00631L、0052）的股票分割沒有完整還原，資料裡會出現單日 -75% 或 -95% 的假暴跌。打開後，系統會找出這種「跳動幅度剛好是整數倍」的接縫並接回去，同時校正還沒換算的配息，結果頁上方會列出修正了什麼。只有在來源完全沒有該標的的分割紀錄時才會修；有紀錄的標的（多數美股）不會被更動。":
        "For some Taiwan ETFs (for example 0050, 00631L, 0052), the data source did not fully adjust stock splits. The data then shows a false one-day drop of -75% or -95%. When this is on, the tool finds jumps that are exact whole-number multiples, joins the two sides, and fixes dividends that were not converted. The top of the results lists what was fixed. It only repairs data when the source has no split record for that ticker. Tickers with split records (most US stocks) are left alone.",
    "定期定額（DCA）是「不借錢、每月慢慢買」的對照組。公平比較＝對照組每月投入的錢，等於槓桿策略當月實際從薪水掏出來的錢，兩邊自掏腰包的總額相同。舊版算法＝對照組每月投入整筆應繳金額，不受薪水上限限制；當應繳金額遠高於薪水上限時，對照組投入的本金會比槓桿組多很多。":
        "The comparison group uses dollar-cost averaging (DCA): you don't borrow and buy a little every month. Fair comparison = the DCA side invests the same amount you actually paid from your salary in that month under the leveraged strategy, so both sides pay the same total out of pocket. Old method = the DCA side invests the full loan payment every month, with no salary limit. When the payment is far above the salary limit, the DCA side invests much more than the leveraged side.",
    "蒙地卡羅是把歷史上的月份重新排列組合。預設是抽到哪個月的漲跌，就一併用那個月實際發的配息，所以不配息的標的不會憑空多出配息，配息多寡也跟著這檔標的自己的紀錄走。如果你認為未來的配息水準會跟過去不同，可以改成照「假想未來情境」裡設定的股息率來算。不管選哪一個，歷史資料用完之後的「假想未來」都是照你設定的股息率。":
        "Monte Carlo shuffles and recombines the months of history. By default, when a month's price move is drawn, the dividend actually paid in that month comes with it. So an ETF that pays no dividends doesn't get any from nowhere, and the amount follows the ETF's own record. If you think future dividends will differ from the past, you can switch to the dividend rate in the \"Assumed future\" section. Either way, the \"assumed future\" after the history ends always uses your dividend rate.",
    "蒙地卡羅模擬會隨機產生很多種可能的未來來統計成敗機率。跑越多次結果越穩定，但計算時間也越久。":
        "Monte Carlo creates many random possible futures to count how often the strategy succeeds or fails. More runs give steadier results but take longer.",
    "模擬未來時，系統會從歷史中『一段一段』抽出來拼接，而不是單月亂抽，這樣才能保留漲跌的連續性（例如崩盤通常會連跌好幾個月）。這裡設定每段多長。":
        "To simulate the future, the tool draws \"pieces\" of history and joins them, instead of drawing single months. This keeps the way moves follow each other (for example, a crash usually means several falling months in a row). This sets how long each piece is.",
    "勾選時，同一組設定每次算出來的蒙地卡羅結果都一樣，所以你調整參數後看到的變化，確定是參數造成的，不是運氣。取消勾選則每次重算都重新抽樣，可以用來感受抽樣本身會讓數字跳動多少。":
        "When on, the same settings always give the same Monte Carlo results. So when you change a setting, you know the change comes from the setting, not from luck. When off, every recalculation draws new samples, so you can see how much the numbers move from sampling alone.",
    "賣出時的證交稅 (%)":
        "Securities transaction tax when selling (%)",
    "單次領到的股利達 2 萬元時，整筆要扣 2.11% 的補充保費。借錢買的部位大，每次配息很容易超過門檻；定期定額對照組的部位小，初期通常不會被扣。":
        "When a single dividend payment reaches NT$20,000, Taiwan's National Health Insurance (NHI) deducts a supplementary premium of 2.11% of the whole amount. A large leveraged position often passes this threshold on every payment. The small DCA position usually doesn't at first.",
    "股利要併入綜合所得稅，但有 8.5% 的可抵減稅額，所以實際多繳的大約是「級距 − 8.5%」：12% 級距約 3.5%、20% 約 11.5%、30% 約 21.5%；40% 級距改用 28% 分開計稅比較划算。5% 級距其實會退稅，這裡保守以 0 計。系統在每次領到配息時就先扣掉，不等到隔年報稅。每戶可抵減稅額上限 8 萬元沒有另外計算。":
        "Dividends are added to your income tax, but there is an 8.5% tax credit. So the extra tax you pay is about \"bracket − 8.5%\": about 3.5% in the 12% bracket, 11.5% in 20%, 21.5% in 30%. For the 40% bracket, separate taxation at 28% is better. The 5% bracket actually gets a refund, so the tool uses 0 to be cautious. The tool deducts the tax each time a dividend is paid, not at tax time next year. The credit limit of NT$80,000 per household is not applied separately.",
    "配息裡有多少比例算股利所得 (%)":
        "Share of the dividend that counts as dividend income (%)",
    "銀行撥款時收的一次性費用（開辦費、帳管費等），會直接從借到的錢裡扣掉，能拿去投資的錢就少這一筆。":
        "A one-time fee the bank charges when it pays out the loan (setup fee, account fee and so on). It comes straight out of the money you borrow, so you have that much less to invest.",
    "｜已自動修正 {n_repairs} 項":
        " | {n_repairs} fixed automatically",
    "｜⚠️ {n_alerts} 項提醒":
        " | ⚠️ {n_alerts} warning(s)",
    "蒙地卡羅和歷史資料用完之後的未來情境":
        "Monte Carlo and the assumed future after the history ends",
    "歷史資料用完之後的未來情境":
        "the assumed future after the history ends",
    "（證交所公告的上市日是 {official}）":
        " (Taiwan Stock Exchange's listing date: {official})",
    "📈 照你設定的利率變化，月付金最高會到 ${v1:,}（第 {v2} 個月，當時年利率 {v3:.2f}%）。":
        "📈 With the rate path you set, the monthly payment peaks at NT${v1:,} (month {v2}, annual rate {v3:.2f}% then).",
    "升息（第 {rate_shock_year} 年起 +{rate_shock_delta}%）":
        "Rate hike (+{rate_shock_delta}% from year {rate_shock_year})",
    "無排定調整":
        "no scheduled changes",
    "，蒙地卡羅每年隨機 ±{rate_volatility:g}":
        ", Monte Carlo adds a random ±{rate_volatility:g} each year",
    "浮動利率（第2年起每年 {path_txt} 個百分點{vol_txt}）":
        "Variable rate (from year 2, each year {path_txt} percentage points{vol_txt})",
    "證交稅{v1:g}%":
        "securities transaction tax {v1:g}%",
    "補充保費2.11%":
        "supplementary premium 2.11%",
    "股利所得稅{v1:g}%":
        "dividend income tax {v1:g}%",
    "開辦費${v1:,}":
        "setup fee NT${v1:,}",
    "；配息的{v1:.0f}%算股利所得":
        "; {v1:.0f}% of dividends count as dividend income",
    "稅費（{v1}{share_txt}）":
        "Taxes and fees ({v1}{share_txt})",
    "突發大崩盤（第 {swan_month} 個月 -{v1}%）":
        "Sudden crash (-{v1}% in month {swan_month})",
    "崩盤賤賣（單月跌超過 {v1}% 時多虧 {v2:.1f}%）":
        "Fire-sale loss (when a month falls more than {v1}%, an extra {v2:.1f}% is lost)",
    "槓桿 ETF 震盪耗損（持平的月份每月 -{v1:.3f}%）":
        "Leveraged-ETF volatility decay (-{v1:.3f}% each flat month)",
    "⚖️ 定期定額對照組：每月投入「槓桿策略當月實際從薪水掏出的金額」，兩邊自掏腰包的錢相同。":
        "⚖️ DCA comparison: each month it invests \"the amount the leveraged strategy actually paid from salary that month\", so both sides pay the same out of pocket.",
    "⚖️ 定期定額對照組（舊版算法）：每月投入整筆應繳金額，不受薪水上限限制，投入本金可能高於槓桿組的自掏金額。":
        "⚖️ DCA comparison (old method): each month it invests the full loan payment, with no salary limit. It may invest more than the leveraged side pays out of pocket.",
    "破產機率（所有進場月份）":
        "Chance of default (all start months)",
    "共 {n_total} 個進場月份：只用真實資料 {n_pure} 個、後段接上假想未來 {n_spliced} 個。相鄰的月份走的幾乎是同一段行情，所以這不是幾百個獨立樣本，破產機率只能當作「歷史上發生過的情況」來看。{v1}":
        "{n_total} start months: {n_pure} use real data only, {n_spliced} have the assumed future added after the real data. Neighboring months follow almost the same market, so these are not hundreds of independent samples. Read the chance of default as \"what happened in history\", not as a forecast. {v1}",
    "贏過定期定額的機率":
        "Chance of beating DCA",
    "期滿資產中位數（沒破產的）":
        "Median final value (no default)",
    "把破產的也算進去（以 0 計）：${v1:,}。":
        "Counting defaults as 0: NT${v1:,}.",
    "定期定額：期滿資產中位數":
        "DCA: median final value",
    "📈 每條路徑的利率各自隨機升降：到最後一期，九成的路徑年利率落在 {mc_final_rate_p5:.2f}% 到 {mc_final_rate_p95:.2f}% 之間。":
        "📈 Each path's rate moves up and down on its own. In the last period, 90% of paths have an annual rate between {mc_final_rate_p5:.2f}% and {mc_final_rate_p95:.2f}%.",
    "破產機率（繳不出貸款）":
        "Chance of default (missed a payment)",
    "想知道最多能借多少？看下方的[安全邊界](#{ANCHOR})。":
        "Want to know the most you can borrow? See the [safety limit](#{ANCHOR}) below.",
    "把破產的也算進去（以 0 計）：${v1:,}。破產時其實還欠著沒還完的貸款，真實處境比 0 更差。":
        "Counting defaults as 0: NT${v1:,}. After a default you still owe the rest of the loan, so the real situation is worse than 0.",
    "歷史資料不到 2 個月，無法做蒙地卡羅模擬。":
        "The history is shorter than 2 months, so Monte Carlo can't run.",
    "歷史回測：每個月進場，期滿剩多少":
        "Historical backtest: start in any month, final value at the end",
    "有斜線紋路的長條：這個月份之後的真實資料不夠長，後段接上了你選的假想未來，請謹慎解讀。":
        "Bars with a diagonal pattern: the real data after that month was too short, so the assumed future you chose was added after it. Read these with care.",
    "蒙地卡羅：期滿資產的分佈":
        "Monte Carlo: spread of final values",
    "蒙地卡羅：自己掏了多少錢、換到多少報酬":
        "Monte Carlo: what you pay out of pocket and what you get back",
    "蒙地卡羅：資產隨時間的可能範圍":
        "Monte Carlo: possible range of assets over time",
    "進場月份":
        "Start month",
    "📥 下載歷史回測結果 (CSV)":
        "📥 Download historical backtest results (CSV)",
    "📥 下載蒙地卡羅結果 (CSV)":
        "📥 Download Monte Carlo results (CSV)",
    "🔍 逐月明細：挑一個月份進場看看":
        "🔍 Month-by-month detail: pick a start month",
    "💡 這裡只是「如果在某個月進場」的其中一種結果。要評估整體風險，請看上方蒙地卡羅模擬的破產機率。":
        "💡 This is only one possible result for \"if you started in one month\". To judge the overall risk, look at the chance of default in the Monte Carlo results above.",
    "要看哪一個月份進場":
        "Start month to look at",
    "月份（後面標「（預測）」的是假想未來）":
        "Month (months marked \"(projected)\" are the assumed future)",
    "{sel_month} 進場：資產和貸款餘額":
        "Start in {sel_month}: assets and loan balance",
    "{sel_month} 進場：每月貸款用哪些錢繳":
        "Start in {sel_month}: what pays the loan each month",
    "❌ 參數有誤，請先修正：\n\n":
        "❌ Some inputs are invalid. Fix them first:\n\n",
    "🔗 分享這組設定":
        "🔗 Share these settings",
    "網址列會自動帶著你目前的所有設定。直接複製瀏覽器的網址傳給別人，對方打開就會看到同一組參數；重新整理頁面也不會遺失設定。":
        "The address bar always carries all your current settings. Copy the browser address and send it to someone. They will see the same settings when they open it. Reloading the page doesn't lose your settings either.",
    "槓桿：中位數":
        "Leveraged: median",
    "定期定額：中位數":
        "DCA: median",
    "貸款剩餘餘額":
        "Loan balance",
    "%{x}：%{y} 次<extra></extra>":
        "%{x}: %{y} runs<extra></extra>",
    "安全邊界":
        "Safety limit",
    "這次沒有計算":
        "Not calculated this time",
    "安全邊界的目標":
        "Safety limit target",
    "破產機率 ≤ {v1}":
        "chance of default ≤ {v1}",
    "寬限期內你只需要付利息、不用還本金，所以每月負擔比較輕。但寬限期一結束，每月要還的錢會明顯跳高。一般信貸通常沒有寬限期，所以選信貸時預設不勾。":
        "During the interest-only period you pay only interest and no principal, so the monthly burden is lighter. But when it ends, the monthly payment jumps clearly. Personal loans usually have no interest-only period, so it is off by default for them.",
    "設定升息從第幾年發生。":
        "The year the rate hike happens.",
    "升息的幅度。例如原本 4%、這裡填 1，升息後就變 5%。升息後每月還款會自動重新計算、變得更高。":
        "How much the rate goes up. For example, if the rate was 4% and you enter 1, it becomes 5% after the hike. After the hike the monthly payment is recalculated and gets higher.",
    "依序是第 2 年、第 3 年、第 4 年…開始時利率的變動，正數是升息、負數是降息，會一直累加。例如「0.25, 0.25, 0.125」代表第 2 年升 1 碼、第 3 年再升 1 碼、第 4 年再升半碼，之後維持不變。留空代表沒有排定的調整。":
        "The rate change at the start of year 2, year 3, year 4 and so on. A positive number is a hike, a negative number is a cut, and the changes add up. For example, \"0.25, 0.25, 0.125\" means +0.25 in year 2, another +0.25 in year 3, and another +0.125 in year 4. After that the rate stays the same. Leave it empty for no scheduled changes.",
    "現實中沒有人知道未來的利率。設成 0.25 的話，蒙地卡羅的每條路徑每年會在你排定的調整之外，再隨機多升或多降一些（大約三分之二的年份落在 ±0.25 個百分點以內），而且會逐年累積。設 0 就只照排定的路徑。歷史回測那一欄只用排定的路徑，不加隨機變動。":
        "Nobody knows future rates. At 0.25, each Monte Carlo path adds a random extra rise or fall each year on top of your scheduled changes (about two thirds of years stay within ±0.25 percentage points), and the changes add up year after year. At 0, only your scheduled path is used. The historical backtest column uses only the scheduled path, with no random changes.",
    "領到的股息，除了買回原本的標的，也可以分一部分去買另一檔（例如槓桿型 ETF）。這裡填那檔的代號。留空代表全部買回第一標的。":
        "Besides buying more of the main ETF, you can use part of the dividends to buy another ETF (for example a leveraged ETF). Enter its ticker here. Leave it empty to put all dividends back into the main ETF.",
    "實際動用順序：":
        "Order used: ",
    "ℹ️ 第二標的沒有排進順位：就算手上還有第二標的，其他來源用完時仍會判定破產。":
        "ℹ️ The second ETF isn't in the order. Even if you still hold it, you default once the other sources run out.",
    "ℹ️ 你選了「配息拿去再買股票」，配息一領到就買股票，所以「存下來的配息」不會有錢，這個順位實際上不會出到力。":
        "ℹ️ You chose \"Reinvest dividends\". Dividends buy shares as soon as they arrive, so \"Saved dividends\" never has any money and this choice never pays anything.",
    "「手動」=自己指定第幾個月失業、持續多久（確定性壓力測試）。「隨機」=設定失業率，每條模擬路徑各自擲骰決定何時失業、多久找到工作（更貼近現實的機率分佈）。":
        "\"Manual\" = you choose in which month the job loss starts and how long it lasts (a fixed stress test). \"Random\" = you set a job-loss rate, and each simulated path rolls dice for when a job loss happens and how long it lasts (a more realistic spread).",
    "完全失業就填 0；部分降薪則填這段期間每月還能從薪水拿出來的最高金額。兩種模型都套用這個金額。":
        "Enter 0 for a full job loss. For a pay cut, enter the most you can still pay from salary each month during that time. Both models use this amount.",
    "從第幾個月開始失業/降薪":
        "Job loss or pay cut starts in month",
    "持續幾個月":
        "Lasts (months)",
    "平均失業持續月數":
        "Average months out of work",
    "找到工作的時間分佈":
        "How long it takes to find a job",
    "（股災常伴隨裁員）":
        "(Crashes often come with layoffs)",
    "市場崩盤時失業率同步飆升":
        "Job losses rise together with market crashes",
    "每次買賣股票要付給券商的成本，加上實際成交價跟理想價的落差。台股一般約 0.1425%。":
        "The cost of each trade paid to the broker, plus the gap between the price you get and the ideal price. About 0.1425% in Taiwan.",
    "當月跌幅超過多少 % 才算崩盤":
        "A month counts as a crash if it falls by more than (%)",
    "賤賣時多虧多少 (%)":
        "Extra loss when selling in a fire sale (%)",
    "自己設計未來每一年的漲跌。例如「5, 10, -20」代表第一年漲5%、第二年漲10%、第三年跌20%。":
        "Design each future year's gain or loss. For example, \"5, 10, -20\" means +5% in the first year, +10% in the second, and -20% in the third.",
    "設定暴跌發生在進場後的第幾個月。選在剛開始、緩衝還很薄的時候，通常最致命。":
        "The month after the start in which the drop happens. The worst time is right at the start, when the buffer is thin.",
    "這個月跌多少 (%)":
        "How much it drops this month (%)",
    "預估這檔標的未來平均一年配發的股息比率。例如填 6，就是一年大約領回本金的 6%。這個數字用在歷史資料用完之後的「假想未來」；有真實資料的月份一律用實際發過的配息。蒙地卡羅預設也用實際發過的配息，可以在「進階設定」改成用這裡的數字。":
        "The expected average dividend this ETF pays per year. For example, enter 6 to get back about 6% of the amount invested each year. This is used for the \"assumed future\" after the history ends. Months with real data always use the dividends actually paid. By default, Monte Carlo also uses the dividends actually paid. You can switch it to this number under \"Advanced\".",
    "賣股票時政府收的稅，買進不用。ETF 是 0.1%，個股是 0.3%。這筆是在上面「買賣手續費」之外另外算的。":
        "The tax the government charges when you sell. Buying has none. It is 0.1% for ETFs and 0.3% for single stocks. It is charged in addition to the trading fee above.",
    "ETF 的配息常常不全是股利，還包含資本利得和收益平準金，那些部分不用繳所得稅和補充保費。各檔 ETF 每次配息的組成不同，可以在投信公告的收益分配通知查到。不確定的話維持 100，等於全部都課，最保守。":
        "ETF payouts are often not all dividends. They can include capital gains and income equalization, and those parts have no income tax or supplementary premium. Each ETF's payout is made up differently, and you can find it in the fund company's distribution notice. If you're not sure, keep 100. That taxes the whole amount, which is the most cautious.",
    "信貸額度":
        "Credit limit",
    "使用的資料":
        "Data used",
    "進場當月以該月價格買進，下個月開始繳第一期。處理方式的說明見「計算方法說明」第十節。":
        "The start month's price is the buying price, and the first payment is due the next month. See section 10 of \"How it works\" for how the data is handled.",
    "📎 用股息模型算的配息（歷史資料用完之後的假想未來{v1}）：{INTERVAL_NAMES}發一次{v2}。":
        "📎 Dividends made by the dividend model (the assumed future after the history ends{v1}): paid {INTERVAL_NAMES}{v2}.",
    "⚠️ {symbol_a} 與替身 {backfill} 在重疊的 {backfill1} 個月裡，月報酬相關係數只有 {backfill2:.2f}，兩者走勢差異不小，替身可能不適合，建議換一檔性質更接近的。":
        "⚠️ In the {backfill1} months where {symbol_a} and the stand-in {backfill} overlap, the correlation of their monthly returns is only {backfill2:.2f}. They move quite differently, so the stand-in may not be suitable. Consider an ETF that is more similar.",
    "⚠️ 替身 {symbol_proxy} 的資料無法使用，改為只用 {symbol_a} 自己的歷史。原因：{loaded}":
        "⚠️ Couldn't use the stand-in {symbol_proxy}. Only the history of {symbol_a} is used. Reason: {loaded}",
    "⚠️ {symbol_a} 的歷史資料裡沒有任何配息，但「未來平均一年發多少股息」設為 {v1:.1f}%。{uses_assumed_yield}，配息是照這個數字算的，等於憑空多出一筆現金；如果它真的不配息，請把這個拉桿調到 0。":
        "⚠️ {symbol_a}'s history has no dividends at all, but \"Average dividend per year in the future\" is set to {v1:.1f}%. For {uses_assumed_yield}, dividends are calculated from this number, which adds cash out of nowhere. If it really pays no dividends, set this slider to 0.",
    "📅 最早可以從 {index:%Y-%m} 進場：{symbol_a} 的第一筆價格在 {attrs}{listed_txt}，在那之前的 {backfill} 個月，用替身 {backfill1} 當時的實際漲跌與配息補上。":
        "📅 You can start as early as {index:%Y-%m}: the first price of {symbol_a} is on {attrs}{listed_txt}. For the {backfill} months before that, the stand-in {backfill1}'s actual price moves and dividends fill the gap.",
    "📅 最早只能從 {index:%Y-%m} 進場：{symbol_a} 的第一筆價格在 {attrs}{listed_txt}，在那之前沒有資料。想測更早的行情（例如 2008 年），可以在側欄「上市前的歷史用哪一檔代替」指定一檔上市更久的 ETF，用它的舊資料補上。":
        "📅 You can only start from {index:%Y-%m}: the first price of {symbol_a} is on {attrs}{listed_txt}, and there is no data before that. To test earlier markets (for example 2008), set a stand-in ETF that was listed earlier under \"Stand-in ETF for history before listing\" in the sidebar. Its older data then fills the gap.",
    "可以在側欄「上市前的歷史用哪一檔代替」填一檔性質相近、上市更久的標的（例如 0056.TW 或 0050.TW）。":
        "Under \"Stand-in ETF for history before listing\" in the sidebar, enter a similar ETF that was listed earlier (for example 0056.TW or 0050.TW).",
    "⚠️ 可用的歷史只有 {n_months} 個月（不到 10 年），很可能沒有涵蓋完整的空頭循環，破產機率容易被低估。{hint}":
        "⚠️ Only {n_months} months of history are available (less than 10 years). It probably doesn't include a full bear market, so the chance of default is likely too low. {hint}",
    "；崩盤（單月跌超過 {v1:.0f}%）時年失業機率再加 {v2:g}～{v3:g}%":
        "; in a crash (a month falling more than {v1:.0f}%), the yearly job-loss chance rises by another {v2:g} to {v3:g}%",
    "隨機失業（年失業機率 {v1:.1f}%，平均失業 {jl_mean_dur:g} 個月，{dist_name}，每月最多自掏 ${v2:,}{crash_txt}｜蒙地卡羅中 {v3:.1f}% 的路徑失業過，平均失業 {job_loss_avg_months:.1f} 個月）":
        "Random job loss (yearly chance {v1:.1f}%, average {jl_mean_dur:g} months out of work, {dist_name}, monthly out-of-pocket limit NT${v2:,}{crash_txt} | in Monte Carlo, {v3:.1f}% of paths had a job loss, average {job_loss_avg_months:.1f} months)",
    "失業或降薪（第 {job_loss_start} 個月起 {job_loss_duration} 個月，每月最多自掏 ${v1:,}）":
        "Job loss or pay cut (for {job_loss_duration} months from month {job_loss_start}, monthly out-of-pocket limit NT${v1:,})",
    "ℹ️ 這組設定下槓桿策略完全沒有動用薪水，所以對照組沒有任何投入、期滿為 0；此時「贏過定期定額的機率」就等於「沒有破產的比例」。":
        "ℹ️ With these settings the leveraged strategy never uses salary, so the DCA comparison invests nothing and ends at 0. In that case \"Chance of beating DCA\" equals \"the share that did not default\".",
    "⤷ 只算真實資料的 {n_pure:,} 個月份":
        "⤷ Real data only, {n_pure:,} months",
    "其中 {n_backfilled} 個進場月份用到了替身 {v1} 的歷史。":
        "{n_backfilled} of the start months use the history of the stand-in {v1}.",
    "🎲 已開啟隨機失業：每個進場月份各模擬 {hist_replicates} 種失業時點，上面的破產機率是平均值。":
        "🎲 Random job loss is on: for each start month, {hist_replicates} job-loss timings are simulated, and the chance of default above is their average.",
    "📈 這一欄的利率只照你排定的路徑走，不含隨機升降息。":
        "📈 The rate in this column follows only your scheduled path, with no random rate changes.",
    "無":
        "none",
    "**👉 大約每 {v1} 種可能的未來，就有 1 種會在中途繳不出貸款。**":
        "**👉 About 1 in every {v1} possible futures ends in a missed loan payment along the way.**",
    "抽樣誤差約 ±{v1:.1f} 個百分點（95% 信賴區間，{v2} 次模擬）。":
        "Sampling error is about ±{v1:.1f} percentage points (95% confidence interval, {v2} simulations).",
    "**👉 {v1} 種模擬的未來裡，沒有任何一種繳不出貸款。**":
        "**👉 In {v1} simulated futures, none of them missed a loan payment.**",
    "這只代表用歷史上出現過的行情重組時沒有發生，不代表不可能；真實的破產機率有 95% 的把握低於 {v1:.2f}%。":
        "This only means it didn't happen when recombining market moves that happened in history. It doesn't mean it can't happen. We are 95% sure the true chance of default is below {v1:.2f}%.",
    "圖表":
        "Charts",
    "破產機率":
        "Chance of default",
    "結果":
        "Result",
    "資料":
        "Data",
    "破產":
        "Defaulted",
    "撐到期滿":
        "Made it to the end",
    "只用真實資料":
        "Real data only",
    "含假想未來":
        "Includes assumed future",
    "最差的 5%":
        "Worst 5%",
    "偏差的 25%":
        "Weaker 25%",
    "中位數":
        "Median",
    "偏好的 25%":
        "Better 25%",
    "最好的 5%":
        "Best 5%",
    "每一列是「有這麼多比例的模擬結果比這個數字差」。例如「最差的 5%」那列，代表 20 次裡有 1 次會落在這個金額以下。":
        "Each row shows the value that this share of the simulated results falls below. For example, in the \"Worst 5%\" row, 1 run in 20 ends at or below this amount.",
    "年化報酬率是把「每個月從薪水掏出的錢」和「期滿時手上的錢」換算成等值的每年報酬，方便和定存或其他投資比較。破產的路徑算 -100%；整段期間完全沒有自掏的路徑無法計算，不列入。":
        "Annualized return converts \"the money you pay from salary each month\" and \"the money you hold at the end\" into an equal yearly return, so you can compare it with a savings account or other investments. A path that defaulted counts as -100%. A path with no out-of-pocket payment at all can't be calculated and is left out.",
    "色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。":
        "The bands show the total value of the leveraged strategy's holdings (before subtracting the loan). Paths that defaulted count as 0.",
    "蒙地卡羅：破產多半發生在第幾年":
        "Monte Carlo: in which year defaults mostly happen",
    "每根柱子代表貸款的一年；高度是 {n_paths:,} 次模擬裡，在那一年繳不出貸款的次數。":
        "Each bar is one year of the loan. Its height is the number of the {n_paths:,} simulations that missed a loan payment in that year.",
    "下載計算結果":
        "Download results",
    "逐月明細":
        "Month-by-month detail",
    "挑一個月份，看「如果那個月進場」之後每個月的資產、貸款餘額和還款來源。進場當月以該月價格買進，下個月開始繳款；真實資料用完之後接上你選的假想未來。這個選擇只影響下面的逐月明細，不會改變上方的統計結果。":
        "Pick a month to see the assets, loan balance and payment sources in each month after \"starting in that month\". The start month's price is the buying price, and payments start the next month. After the real data ends, the assumed future you chose is added. This choice only changes the month-by-month detail below. It doesn't change the statistics above.",
    "🎲 已開啟隨機失業：下面顯示的是這個進場月份其中一種失業時點的結果。":
        "🎲 Random job loss is on: what you see below is one possible job-loss timing for this start month.",
    "單一進場月份的結果，真實資料用完之後接上假想未來。":
        "The result of one start month. After the real data ends, the assumed future is added.",
    "##### {sel_month} 進場：逐月明細表":
        "##### Start in {sel_month}: month-by-month table",
    "📥 下載逐月明細表 (CSV)":
        "📥 Download month-by-month table (CSV)",
    "%Y-%m-%d %H:%M（台北時間）":
        "%Y-%m-%d %H:%M (Taipei time)",
    "（沒有任何來源）":
        "(no source)",
    "📄 把這次的結果存下來":
        "📄 Save this result",
    "❌ 參數有誤，請先修正：\n\n{exc}":
        "❌ Some inputs are invalid. Fix them first:\n\n{exc}",
    "第{y}年":
        "Year {y}",
    "❌ 無法計算安全邊界：{exc}":
        "❌ Couldn't find the safety limit: {exc}",
    "寬限期長度 (年)":
        "Interest-only period (years)",
    "浮動利率路徑：{exc}":
        "Variable-rate path: {exc}",
    "配息拿多少比例買第二標的 (%)":
        "Share of dividends used to buy the second ETF (%)",
    "不會動用：":
        "Not used: ",
    "設定薪水驟降從進場後的第幾個月發生。":
        "The month after the start in which pay drops sharply.",
    "失業或降薪要持續幾個月。這段時間結束後，薪水自動恢復成上方設定的補貼上限。":
        "How many months the job loss or pay cut lasts. After that, your salary goes back to the out-of-pocket limit set above.",
    "年失業機率 (%)":
        "Yearly chance of job loss (%)",
    "失業後平均要花幾個月才找到新工作。實際每次失業的長短會依下方的機率分佈隨機決定——有人運氣好 1 個月就上工，也有人拖到十幾個月。":
        "The average number of months it takes to find a new job after losing one. The real length of each job loss is drawn at random from the distribution below. Some people find work in 1 month, and others take over ten.",
    "決定失業持續時間怎麼隨機：對數常態=多數人很快找到、少數人拖很久（右尾長，較貼近現實求職）；卜瓦松=圍繞平均值較對稱地分佈。":
        "How the length of a job loss is drawn. Log-normal = most people find work quickly and a few take very long (a long right tail, closer to real job searches). Poisson = spread more evenly around the average.",
    "失業長短的落差 (σ)":
        "Spread of job-loss lengths (σ)",
    "現實中股災常伴隨裁員潮。打開後，當某個月市場跌幅超過下方門檻，該月的失業機率會額外往上加一段（在設定範圍內隨機），模擬「資產暴跌＋同時失業」的雙重打擊。":
        "In real life, crashes often come with layoffs. When on, in a month when the market falls more than the threshold below, that month's chance of job loss rises by an extra amount (drawn at random within the range you set). It simulates a double hit: assets drop and you lose your job at the same time.",
    "崩盤當月額外增加的年失業機率 (%)":
        "Extra yearly job-loss chance in a crash month (%)",
    "設定多大的單月跌幅才觸發賤賣損失。例如填 20，代表當月跌超過 20% 時，賣股就會多虧一筆。":
        "How big a one-month drop triggers the fire-sale loss. For example, enter 20 and any month falling more than 20% makes you lose an extra amount when you sell shares.",
    "觸發崩盤時，賣股票要額外多承受的折價損失。例如填 8，就是崩盤時賣股比平常多虧 8%。":
        "The extra discount you lose when selling shares in a crash. For example, enter 8 and you lose 8% more than usual when selling in a crash.",
    "自訂年度報酬率路徑：{exc}":
        "Custom yearly return path: {exc}",
    "暴跌的幅度。例如填 40，代表那個月股價直接腰斬式下殺 40%。":
        "How big the drop is. For example, enter 40 and the price falls 40% in that one month, almost cutting it in half.",
    "提醒":
        "Note",
    "（歷史替身）":
        " (history stand-in)",
    "{symbol} 已自動修正：{n}":
        "{symbol} fixed automatically: {n}",
    "{symbol} 資料提醒（未更動）：{n}":
        "{symbol} data warning (not changed): {n}",
    "兩者重疊 {backfill} 個月，月報酬相關係數 {corr:.2f}。":
        " The two overlap for {backfill} months, and the correlation of their monthly returns is {corr:.2f}.",
    "📎 {symbol_a} 在 {backfill} 至 {backfill1} 這 {backfill2} 個月還沒有自己的資料，以 {backfill3} 當時的實際漲跌與配息代替。{corr_txt}":
        "📎 {symbol_a} has no data of its own for these {backfill2} months, {backfill} to {backfill1}. The actual price moves and dividends of {backfill3} at that time are used instead.{corr_txt}",
    "📎 {symbol_b} 在 {first_real:%Y-%m} 之前沒有資料，這 {modelled_b_months} 個月用「第一標的漲跌 × {beta_b:.2f} 倍」推估（倍數由兩者重疊期間估出；不假設它會持續贏過或輸給這個倍數）。":
        "📎 {symbol_b} has no data before {first_real:%Y-%m}. For these {modelled_b_months} months, it is estimated as \"main ETF move × {beta_b:.2f}\" (the multiple is estimated from the overlap period. The tool does not assume it keeps beating or lagging this multiple).",
    "先前":
        "earlier",
    "⚠️ 「未來平均一年發多少股息」設為 {v1:.1f}%，但 {symbol_a} 最近 {v2} 個月實際平均約 {v3:.1f}%（全部歷史平均 {v4:.1f}%）。{uses_assumed_yield}，配息是照你設的數字算的，差距這麼大會直接影響結果，請確認這是你想測試的假設。":
        "⚠️ \"Average dividend per year in the future\" is set to {v1:.1f}%, but {symbol_a} actually averaged about {v3:.1f}% over the last {v2} months (average over all its history: {v4:.1f}%). For {uses_assumed_yield}, dividends are calculated from your number. A gap this large directly affects the results, so check that this is the assumption you want to test.",
    "、":
        ", ",
    "🟢 這次有開啟： ":
        "🟢 Turned on for this run: ",
    "色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。色帶下緣跌到貸款餘額線以下的月份，代表最差的 5% 情況裡資產已經不夠還清貸款；差距最大在第 {v1} 個月。":
        "The bands show the total value of the leveraged strategy's holdings (before subtracting the loan). Paths that defaulted count as 0. In months where the lower edge of the band falls below the loan balance line, the assets in the worst 5% of cases can no longer repay the loan. The gap is largest in month {v1}.",
    "色帶是槓桿策略手上資產的總值（還沒扣掉貸款），破產的路徑以 0 計。整段期間即使是最差的 5% 情況，資產都還高於貸款餘額。":
        "The bands show the total value of the leveraged strategy's holdings (before subtracting the loan). Paths that defaulted count as 0. Even in the worst 5% of cases, the assets stay above the loan balance for the whole period.",
    "{n_paths:,} 次模擬裡只有 {v1} 次破產，發生在第 {listed}{gap}個月。次數很少，這張圖只供參考。":
        "Only {v1} of {n_paths:,} simulations defaulted, in month {listed}.{gap}There are very few, so use this chart as a rough guide only.",
    "{v1} 次破產的模擬裡，有一半發生在第 {v2} 個月之前。集中在哪一段，通常就是現金流最吃緊的時期（例如寬限期剛結束）。":
        "Of the {v1} simulations that defaulted, half did so before month {v2}. Where they cluster is usually when cash flow is tightest (for example, just after the interest-only period ends).",
    "多數情況破產":
        "Mostly defaulted",
    "用到替身歷史":
        "Used history of stand-in",
    "槓桿期滿資產":
        "Leveraged final value",
    "槓桿期滿資產（沒破產的）":
        "Leveraged final value (no default)",
    "定期定額期滿資產":
        "DCA final value",
    "贏過定期定額":
        "Beat DCA",
    "破產月份(0=未破產)":
        "Default month (0 = no default)",
    "槓桿自掏總額":
        "Leveraged total paid out of pocket",
    "定期定額投入總額":
        "DCA total invested",
    "槓桿年化報酬率":
        "Leveraged annualized return",
    "定期定額年化報酬率":
        "DCA annualized return",
    "第一標的":
        "Main ETF",
    "配息":
        "Dividends",
    "還款資金的動用順序":
        "Order of repayment sources",
    "每月最多自掏":
        "Monthly out-of-pocket limit",
    "{buffer_months} 個月的還款":
        "{buffer_months} months of payments",
    "買賣手續費與滑價":
        "Trading fee and slippage",
    "歷史用完之後的未來情境":
        "Future scenario after the history ends",
    "未來的股息假設":
        "Future dividend assumption",
    "一年 {v1:g}%｜{INTERVAL_NAMES}發放｜跟市場連動程度 {div_beta:g}":
        "{v1:g}% a year | paid {INTERVAL_NAMES} | follows the market at {div_beta:g}",
    "蒙地卡羅模擬":
        "Monte Carlo simulation",
    "{mc_paths:,} 次｜每次抽 {block_size} 個月一組｜{v1}｜配息：{mc_div_label}":
        "{mc_paths:,} runs | {block_size} months drawn at a time | {v1} | dividends: {mc_div_label}",
    "定期定額對照組":
        "DCA comparison",
    "有開啟的情境與稅費":
        "Scenarios and taxes turned on",
    "逐月明細的進場月份":
        "Start month of the month-by-month detail",
    "借錢投資 ETF 壓力測試報告：{symbol_a}":
        "Borrow-to-Invest ETF Stress Test report: {symbol_a}",
    "報告是單一檔案，包含這次的設定、主要結果、表格和互動圖表，用瀏覽器打開就能看，也可以直接列印成 PDF。圖表需要連上網路才會顯示。":
        "The report is one file. It holds this run's settings, main results, tables and interactive charts. Open it in a browser, or print it as a PDF. The charts need an internet connection to show.",
    "模擬計算中…":
        "Running the simulation…",
    "前幾年只繳利息不還本金。":
        "Only interest is paid in the first years, with no principal.",
    "領到的股息，要分多少比例去買第二檔。例如填 50，就是一半買回原標的、一半買第二檔。":
        "The share of dividends used to buy the second ETF. For example, enter 50 to put half back into the main ETF and buy the second ETF with the other half.",
    "每一年內遭遇失業的機率。例如填 5，代表每年大約有 5% 機率失業。系統會換算成逐月機率，讓每條模擬路徑各自擲骰。":
        "The chance of losing your job within a year. For example, enter 5 for about a 5% chance each year. The tool converts it to a monthly chance, and each simulated path rolls its own dice.",
    "對數常態的標準差。越大代表失業時間落差越懸殊（極短與極長都更常見）；越小代表大家找到工作的時間都接近平均值。":
        "The standard deviation of the log-normal distribution. A larger value makes job-loss lengths vary more (both very short and very long are more common). A smaller value keeps everyone's time to find work close to the average.",
    "市場單月跌幅超過多少 % 視為崩盤":
        "A one-month market drop of more than this (%) counts as a crash",
    "崩盤觸發時，年失業機率額外往上加的範圍。每條路徑會在這個區間內隨機抽一個值，模擬不同產業、不同景氣下裁員力道的差異。":
        "The range of extra yearly job-loss chance added when a crash happens. Each path draws one value in this range at random, to simulate how layoffs differ across industries and economic conditions.",
    "核貸倍數 {multiple:g}（估計）。貸款金額：{LMODE_OPTIONS}。":
        " Approval multiple {multiple:g} (estimate). Loan amount: {LMODE_OPTIONS}.",
    "本金調整":
        "Principal adjusted",
    "{symbol}{role}：來源價格期間 {attrs} 至 {attrs1}（非成立／上市日期）。":
        "{symbol}{role}: source price period {attrs} to {attrs1} (not the founding or listing date).",
    "📎 替身 {symbol_proxy} 的歷史沒有比 {symbol_a} 更早（或中間有缺口），所以沒有用到。":
        "📎 The history of the stand-in {symbol_proxy} is not earlier than {symbol_a} (or has gaps), so it was not used.",
    "⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，並已用證交所的資料補到 {attrs}。可以稍後按側欄的「重新載入行情」再試一次。":
        "⚠️ {symbol}: Live market data is not available right now. The tool is using the data saved on {saved}, topped up to {attrs} with data from the Taiwan Stock Exchange. You can try again later with \"Reload market data\" in the sidebar.",
    "⚠️ {symbol}：即時行情暫時無法取得，目前使用 {saved} 存檔的資料，最新的價格與配息可能沒有包含在內。可以稍後按側欄的「重新載入行情」再試一次。":
        "⚠️ {symbol}: Live market data is not available right now. The tool is using the data saved on {saved}. The latest prices and dividends may not be included. You can try again later with \"Reload market data\" in the sidebar.",
    "⚠️ 含假想未來的月份都接上同一段假想未來，彼此更相關，只能當成單一劇本的參考。":
        "⚠️ All months with the assumed future use the same assumed future, so they are even more alike. Treat them only as a guide for one scenario.",
    "期滿資產 (元)":
        "Final value (NT$)",
    "槓桿策略（破產以 0 計）":
        "Leveraged strategy (default counts as 0)",
    "槓桿策略":
        "Leveraged strategy",
    "（預測）":
        " (projected)",
    "當月繳款金額 (元)":
        "Amount paid this month (NT$)",
    "｜每月 {pay_day_option} 日扣款":
        " | payment on day {pay_day_option} of each month",
    "再投入，其中 {v1:.0f}% 買第二標的 {symbol_b}":
        "reinvested, {v1:.0f}% of it buys the second ETF {symbol_b}",
    "觸發失業率飆升的單月跌幅門檻。例如填 15，代表當月跌超過 15% 時就啟動失業率加成。":
        "The one-month drop that triggers the job-loss rise. For example, enter 15 and the extra job-loss chance applies when a month falls more than 15%.",
    "資料取得時間 {fetched}（{origin}）。":
        " Data fetched on {fetched} ({origin}).",
    "🔧 {symbol} 的來源資料有已知問題，已自動修正：\n\n":
        "🔧 The source data for {symbol} has known problems and was fixed automatically:\n\n",
    "⚠️ {symbol} 的資料有不尋常的地方。系統無法判斷是來源錯誤還是真實情況，所以沒有更動，照原樣納入計算：\n\n":
        "⚠️ The data for {symbol} has something unusual. The tool can't tell whether it is a source error or a real event, so it did not change it and uses it as it is:\n\n",
    "，以及蒙地卡羅":
        ", and Monte Carlo",
    "，依這檔標的最近三年的紀錄判斷":
        ", judged from this ETF's record of the last three years",
    " ｜ ":
        " | ",
    "整段期間自掏腰包的總額（中位數）":
        "Total paid out of pocket over the whole period (median)",
    "期滿資產（中位數，破產以 0 計）":
        "Final value (median, default counts as 0)",
    "換算成年化報酬率（中位數）":
        "Converted to annualized return (median)",
    "換算成年化報酬率（最差的 5%）":
        "Converted to annualized return (worst 5%)",
    "{v1} 萬元｜{loan_type}｜年利率 {loan_rate:g}%｜{loan_years} 年":
        "{v1} | {loan_type} | annual rate {loan_rate:g}% | {loan_years} years",
    "（上市前以 {backfill} 代替）":
        " (stand-in {backfill} before listing)",
    "再投入，全部買回第一標的":
        "reinvested, all of it buys the main ETF",
    "不再投入，存下來繳貸款":
        "not reinvested, saved to pay the loan",
    "（{custom_path_str}）":
        " ({custom_path_str})",
    "{m}（{c} 次）":
        "{m} ({c} times)",
    "路徑":
        "Path",
    "｜寬限期 {v1} 年":
        " | interest-only period {v1} years",
    "｜無寬限期":
        " | no interest-only period",
    "固定亂數":
        "same random draws every run",
    "每次重新抽樣":
        "new draws every run",
    "理財型房貸（年限長，可設寬限期）":
        "Home-equity loan (long term, interest-only period available)",
    "一般信貸（年限短，通常無寬限期）":
        "Personal loan (short term, usually no interest-only period)",
    "薪水（自掏腰包）":
        "Salary (out of pocket)",
    "存下來的配息":
        "Saved dividends",
    "緩衝金":
        "Cash buffer",
    "賣第一標的":
        "Sell main ETF",
    "賣第二標的":
        "Sell second ETF",
    "（不使用）":
        "(Not used)",
    "從存下來的配息繳":
        "Paid from saved dividends",
    "從緩衝金繳":
        "Paid from cash buffer",
    "賣第一標的繳":
        "Paid by selling main ETF",
    "賣第二標的繳":
        "Paid by selling second ETF",
    "從薪水繳（自掏）":
        "Paid from salary (out of pocket)",
    "第幾個月":
        "Month number",
    "月份":
        "Month",
    "槓桿：手上資產":
        "Leveraged: holdings value",
    "定期定額：手上資產":
        "DCA: holdings value",
    "當月年利率 (%)":
        "Annual rate this month (%)",
    "已破產":
        "Defaulted",
    "當月應繳":
        "Payment due this month",
    "配息被扣的稅費":
        "Tax and fees taken from dividends",
    "定期定額：當月投入":
        "DCA: invested this month",
    "第一標的股數":
        "Shares of main ETF",
    "第二標的股數":
        "Shares of second ETF",
    "第一順位":
        "1st choice",
    "第二順位":
        "2nd choice",
    "第三順位":
        "3rd choice",
    "第四順位":
        "4th choice",
    "第五順位":
        "5th choice",
    "2008 黑天鵝復刻 (先暴跌後復甦)":
        "2008 replay (crash first, then recovery)",
    "失落的十年 (長期熊市陰跌)":
        "Lost decade (long, slow bear market)",
    "AI 泡沫破裂 (典範轉移)":
        "AI bubble bursts (paradigm shift)",
    "自訂年度報酬率路徑":
        "Custom yearly return path",
    "手動指定時間":
        "Manual timing",
    "隨機失業模型":
        "Random job-loss model",
    "對數常態（多數很快找到、少數拖很久）":
        "Log-normal (most find work quickly, a few take very long)",
    "卜瓦松（集中在平均附近）":
        "Poisson (clustered around the average)",
    "不計股利所得稅":
        "No tax on dividend income",
    "5%（可抵減額大於稅額，以 0 計）":
        "5% (credit is larger than the tax, so 0)",
    "40%（以 28% 分開計稅）":
        "40% (taxed separately at 28%)",
    "跟歷史一樣（自動判斷）":
        "Same as history (automatic)",
    "每月":
        "monthly",
    "每季":
        "quarterly",
    "每半年":
        "twice a year",
    "每年":
        "yearly",
    "照歷史上實際發的配息（跟報酬一起重抽）":
        "Dividends actually paid in history (redrawn with the returns)",
    "照「未來平均一年發多少股息」的設定":
        "The \"average dividend per year in the future\" setting",
    "與槓桿組相同的自掏金額 (公平比較)":
        "Same out-of-pocket amount as the leveraged side (fair comparison)",
    "每月投入整筆應繳金額 (舊版算法)":
        "Invest the full payment every month (old method)",
    "剛從 Yahoo Finance 取得":
        "Just fetched from Yahoo Finance",
    "這台主機先前取得的存檔":
        "Saved copy from this computer",
    "每日自動更新的存檔":
        "Saved copy, updated automatically every day",
    "較舊的存檔":
        "Older saved copy",
    "較舊的存檔，加上證交所的近期資料":
        "Older saved copy, plus recent data from the Taiwan Stock Exchange",
    "❌ 這次的報告暫時無法產生，其他結果不受影響。":
        "❌ Couldn't create the report this time. The other results are not affected.",
    "開始計算":
        "Run",
    "❌ 這次的計算暫時無法完成。可以調整設定後再試一次，或按側欄的「重新載入行情」。":
        "❌ Couldn't finish the calculation this time. Change the settings and try again, or press \"Reload market data\" in the sidebar.",
    "⚠️ 設定已變更，結果尚未更新。下面還是上一次計算的結果，按側欄最上方的「開始計算」更新。":
        "⚠️ Settings changed. Results are out of date. What you see below is from the last run. Press Run to update.",
    "設定已變更。調好後按「開始計算」更新結果。":
        "Settings changed. Press Run when you're ready.",
    "⚠️ 設定已變更，結果尚未更新":
        "⚠️ Settings changed. Results are out of date",
    "✓ 結果對應目前的設定":
        "✓ Results match your current settings",
    "自動重算已開啟：每次調整都會重新計算。":
        "Auto-recalculate is on: every change recalculates.",
    "⚠️ 設定已變更：報告內容是上一次計算的結果。":
        "⚠️ Settings changed: the report shows the last run.",
    "請先修正上面的錯誤":
        "Fix the errors above first",
    "打開後，每次調整設定都會立刻重新計算（舊的做法）。設定很多或電腦較慢時建議關閉：調好所有設定，再按「開始計算」一次算完。":
        "When on, every change recalculates right away (the old behavior). With many settings or a slow computer, leave it off: adjust everything, then press Run once.",
    "理財型房貸":
        "home-equity loan",
    "一般信貸":
        "personal loan",

    # ---- ui_state.py ----
    "語言":
        "Language",
    "{label}：{v1}（目前只有這個選項）":
        "{label}: {v1} (this is the only choice)",

    # ---- safety_limit.py ----
    "貸款本金 {y} 不比開辦費多，無法計算":
        "A loan of {y} is not more than the setup fee, so it can't be calculated",
    "安全邊界（破產機率 ≤ {v1}）":
        "Safety limit (chance of default ≤ {v1})",
    "借 {v1} 萬時，破產機率約 {r}（{n:,} 次模擬）。":
        "When you borrow {v1}, the chance of default is about {r} ({n:,} simulations).",
    "最多可以借":
        "Most you can borrow",
    "{v1} 萬":
        "{v1}",
    "以目前其他設定，要讓破產機率在 {t} 以下，最多可以借 **{v1} 萬**（你目前設定 {v2} 萬）。":
        "With your other settings unchanged, the most you can borrow and keep the chance of default at or below {t} is **{v1}** (you entered {v2}).",
    "每月最多自掏 {v1} 時，破產機率約 {r}（{n:,} 次模擬）。":
        "With a monthly out-of-pocket limit of {v1}, the chance of default is about {r} ({n:,} simulations).",
    "每月最少要自掏":
        "Least you must pay in each month",
    "以目前其他設定，要讓破產機率在 {t} 以下，每月最少要能自掏 **{v1}**（你目前設定 {v2}）。":
        "To keep the chance of default at or below {t}, you need to be able to pay in at least **{v1}** a month (you entered {v2}).",
    "{BAND_NAMES}（≤ {a}）":
        "{BAND_NAMES} (≤ {a})",
    "{BAND_NAMES}（{a}–{b}）":
        "{BAND_NAMES} ({a}–{b})",
    "{BAND_NAMES}（{b}–{c}）":
        "{BAND_NAMES} ({b}–{c})",
    "{BAND_NAMES}（> {c}）":
        "{BAND_NAMES} (> {c})",
    "{v1} 萬以上":
        "{v1} or more",
    "以目前其他設定，就算借到搜尋上限 **{v1} 萬**，破產機率也只有 {r}，仍在 {t} 以下（你目前設定 {v2} 萬）。":
        "Even at the search limit of **{v1}**, the chance of default is only {r}, within {t} (you entered {v2}).",
    "不到 {v1} 萬":
        "Under {v1}",
    "以目前其他設定，就算只借 **{v1} 萬**，破產機率也有 {r}，達不到 {t} 以下。":
        "Even borrowing just **{v1}**, the chance of default is {r}, above {t}.",
    "⚠️ 你目前設定的 {v1} 萬已經超過這個上限。":
        "⚠️ The {v1} you entered is already over this limit.",
    "和目前相同":
        "Same as now",
    "{v1}{v2} 萬（比目前）":
        "{v1}{v2} (vs. now)",
    "以目前其他設定，就算每月完全不自掏，破產機率也只有 {r}，仍在 {t} 以下。":
        "Even paying nothing in each month, the chance of default is only {r}, within {t}.",
    "超過 {v1}":
        "Over {v1}",
    "以目前其他設定，就算每月最多自掏到 **{v1}**，破產機率仍有 {r}，達不到 {t} 以下。":
        "Even paying in up to **{v1}** a month, the chance of default is still {r}, above {t}.",
    "⚠️ 你目前設定的 {v1} 不夠，每月還差 {v2}。":
        "⚠️ The {v1} you entered is not enough. You are short by {v2} each month.",
    "{v1}{v2}（比目前）":
        "{v1}{v2} (vs. now)",
    "每月最多自掏（元）":
        "Monthly out-of-pocket limit (NT$)",
    "貸款本金":
        "Loan amount",
    "借到 {v1} 萬時的破產機率":
        "Chance of default when borrowing {v1}",
    "{v1} 萬（目前 {v2} 萬）":
        "{v1} (now {v2})",
    "借 {v1} 萬時的破產機率":
        "Chance of default when borrowing {v1}",
    "完全不自掏時的破產機率":
        "Chance of default when paying nothing in",
    "{v1}（目前 {v2}）":
        "{v1} (now {v2})",
    "每月自掏 {v1} 時的破產機率":
        "Chance of default with {v1} a month out of pocket",
    "光靠多掏錢救不回來，可以試著降低貸款本金再算一次。":
        "Paying in more can't fix this. Try a smaller loan and run it again.",
    "貸款本金 %{{y}}｜每月最多自掏 %{{x}}<br>破產機率 %{{customdata}}（{paths:,} 次模擬）<extra></extra>":
        "Loan amount %{{y}} | monthly out-of-pocket limit %{{x}}<br>Chance of default %{{customdata}} ({paths:,} simulations)<extra></extra>",
    "只借 {v1} 萬時的破產機率":
        "Chance of default when borrowing just {v1}",
    "不計算（薪水沒有排進還款順位）":
        "Not calculated (salary is not in the repayment order)",
    "很安全":
        "Very safe",
    "達標":
        "Within target",
    "超過":
        "Over target",
    "危險":
        "Danger",
    "🛡️ 安全邊界：最多能借多少？":
        "🛡️ Safety limit: how much can you borrow?",
    "用蒙地卡羅模擬反過來找：其他設定都不變的情況下，貸款本金最多可以多少、每月最少要能自掏多少，破產機率才不會超過你能接受的上限。要跑幾十次模擬，所以按按鈕才會計算。":
        "Monte Carlo works backwards to find this. With your other settings unchanged, it finds the most you can borrow and the least you must be able to pay out of pocket each month, so that the chance of default stays within the limit you accept. It runs dozens of simulations, so it only runs when you press the button.",
    "你能接受的破產機率最多多少":
        "Highest chance of default you'll accept",
    "例如選 5%，就是要求「每 20 種可能的未來裡，最多只有 1 種會繳不出貸款」。選越低越保守。":
        "For example, 5% means \"out of every 20 possible futures, at most 1 may end in a missed loan payment\". The lower you choose, the more cautious it is.",
    "🛡️ 計算安全邊界":
        "🛡️ Find safety limit",
    "還沒有計算。按「計算安全邊界」開始。":
        "Not calculated yet. Press \"Find safety limit\" to start.",
    "請先按「開始計算」更新上方結果，再計算安全邊界。":
        "Press Run to update the results above first, then find the safety limit.",
    "歷史資料不到 2 個月，無法做蒙地卡羅模擬，所以也無法計算安全邊界。":
        "The history is shorter than 2 months, so Monte Carlo can't run and the safety limit can't be found.",
    "⚠️ 設定已變更，下面的安全邊界是用舊設定算的。按「計算安全邊界」重新計算。":
        "⚠️ Settings changed. The safety limit below was found with the old settings. Press Find safety limit to update it.",
    "⚠️ 你改了能接受的破產機率，下面還是 {t} 的結果。按「計算安全邊界」重新計算。":
        "⚠️ You changed the chance of default you accept. The result below is still for {t}. Press Find safety limit to update it.",
    "你沒有把「薪水（自掏腰包）」排進還款順位，所以每月自掏多少都不影響結果，這一項不計算。":
        "Salary (out of pocket) is not in your repayment order, so the monthly out-of-pocket amount doesn't change the result. This item is not calculated.",
    "你關閉了「固定亂數」，安全邊界固定用同一組抽樣計算，所以數字可能和上方的破產機率略有不同。":
        "You turned off \"Same random draws every run\". The safety limit always uses one fixed set of draws, so its numbers may differ slightly from the chance of default above.",
    "破產機率地圖：借多少 × 每月自掏多少":
        "Default-risk map: loan amount × monthly out-of-pocket",
    "怎麼看這張圖：每一格是「只把貸款本金換成左邊的數字、每月最多自掏換成下面的數字，其他設定都不變」時的破產機率。◆ 是你目前的設定。藍色是在你選的上限（{t}）以內，紅色是超過；顏色越深，離上限越遠。往上（借越多）、往左（自掏越少）通常越危險。":
        "How to read this chart: each cell is the chance of default when only the loan amount is changed to the number on the left and the monthly out-of-pocket limit to the number below, with all other settings unchanged. ◆ is your current setting. Blue is within the limit you chose ({t}) and red is over it. The darker the color, the further from the limit. Going up (borrowing more) and left (paying less out of pocket) is usually more dangerous.",
    "安全邊界只看蒙地卡羅模擬的破產機率，不看歷史回測。它是用歷史行情重新組合出來的估計，不是保證。":
        "The safety limit uses only the chance of default from Monte Carlo, not the historical backtest. It is an estimate built from recombined market history, not a guarantee.",
    "「—」的格子：貸款本金不比開辦費多，借到的錢扣掉開辦費就沒了，無法計算。":
        "Cells with \"—\": the loan is not more than the setup fee, so nothing is left after the fee and it can't be calculated.",
    "你沒有把薪水排進還款順位，所以地圖上每一格幾乎都一樣：借多少、每月自掏多少，都不太影響破產機率。":
        "Salary is not in your repayment order, so almost every cell on the map is the same. How much you borrow or pay out of pocket hardly changes the chance of default.",
    "你的每月最多自掏是 0，所以最左邊「$0」那一欄上下幾乎都一樣：不自掏的話，借多少都不太影響破產機率。往右看，是每月補一點錢的效果。":
        "Your monthly out-of-pocket limit is 0, so the leftmost \"NT$0\" column looks almost the same from top to bottom: with nothing paid out of pocket, the loan amount hardly changes the chance of default. Look to the right to see the effect of adding a little money each month.",
    "你沒有用薪水補貼還款。這時借多借少，每月還款和買進的資產都等比例變大或變小，破產機率幾乎不變，所以「最多可以借」不是「{hi} 萬以上」就是「不到 {lo} 萬」，不會落在中間。":
        "You don't use salary to help pay the loan. Then, borrowing more or less scales the monthly payment and the assets you buy by the same proportion, so the chance of default hardly changes. So \"Most you can borrow\" is either \"{hi} or more\" or \"under {lo}\", never in between.",
    "借越多，每月還款和買進的資產都會等比例變大，每月自掏那筆固定的錢就越不夠看，所以破產機率不會一直升高，而是慢慢接近「完全不自掏」時的水準；這個水準在 {t} 以下，所以整個搜尋範圍都達標。":
        "The more you borrow, the larger the monthly payment and the assets you buy by the same proportion, and the fixed out-of-pocket amount counts for less. So the chance of default doesn't keep rising. It slowly approaches the level for \"paying nothing out of pocket\". That level is within {t}, so the whole search range meets the target.",
    "這次的破產機率在 {t} 以下，所以整個搜尋範圍都達標。":
        "This time the chance of default is within {t}, so the whole search range meets the target.",
    "破產機率低不代表風險小：借越多，一旦出事賠得也越多。":
        "A low chance of default doesn't mean low risk: the more you borrow, the more you lose if something goes wrong.",
    "這次的破產機率超過 {t}，調整本金沒有用；要從利率、年限、還款的順序或每月自掏的錢下手。":
        "This time the chance of default is above {t}, and changing the loan amount doesn't help. Look at the rate, the term, the order of repayment sources or the monthly out-of-pocket amount.",
    "問題可能不在借多少，而是利率、年限、每月自掏的錢或還款的順序；可以看看下面的地圖。":
        "The problem may not be how much you borrow, but the rate, the term, the monthly out-of-pocket amount or the order of repayment sources. See the map below.",
    "用表格看這張地圖":
        "See this map as a table",
    "（1/3）找最多能借多少…":
        "(1/3) Finding the most you can borrow…",
    "（2/3）找每月最少要自掏多少…":
        "(2/3) Finding the least you must pay in each month…",
    "（3/3）畫破產機率地圖（{n} 格）…":
        "(3/3) Drawing the default-risk map ({n} cells)…",
    "◆ 目前":
        "◆ You",

    # ---- credit_limit.py ----
    "依平均月收入 {v1} 萬：法規上限 {v2}、一般可核貸約 {v3}（估計）、產品最高額度 {v4}。你的可借上限是 {v5}。":
        "With an average monthly income of {v1}: legal limit {v2}, typical approval about {v3} (estimate), product maximum {v4}. Your borrowing limit is {v5}.",
    "你輸入 {v1}，但依規定（平均月收入的 22 倍，扣掉既有無擔保債務）最多只能借 {v2}。以下結果以 {v2}計算。":
        "You entered {v1}, but by regulation (22 times average monthly income, minus existing unsecured debt) you can borrow at most {v2}. The results below use {v2}.",
    "寬限期後每月應繳 ${v1:,}，是平均月收入的 {v2:.1f}%。":
        "The monthly payment after the interest-only period is NT${v1:,}, which is {v2:.1f}% of average monthly income.",
    "這裡只算這筆新貸款，沒有算你其他貸款的月付。":
        "This counts only this new loan, not the monthly payments on your other loans.",
    "已換成{type_name}的預設值：本金 {principal} 萬、年利率 {rate:g}%、{years} 年、{grace}。":
        "Switched to the standard values for a {type_name}: loan amount {principal}, annual rate {rate:g}%, {years} years, {grace}.",
    "已扣掉既有無擔保債務 {v1}。":
        "Existing unsecured debt of {v1} has been subtracted.",
    "你輸入 {v1}，但產品最高額度是 {v2}。以下結果以 {v2}計算。":
        "You entered {v1}, but the product maximum is {v2}. The results below use {v2}.",
    "你輸入的 {v1}，高過一般可核貸的估計 {v2}。銀行可能只核給較低的額度。":
        "The {v1} you entered is higher than the typical approval estimate of {v2}. The bank may approve a lower amount.",
    "寬限期 {grace_years} 年":
        "interest-only period {grace_years} years",
    "無寬限期":
        "no interest-only period",
    "月付比偏高。部分銀行的產品條件寫，每月還款不能超過月收入的三分之一。":
        "The payment-to-income ratio is high. Some banks' product terms say the monthly payment can't be more than one third of monthly income.",
    "多數銀行可能婉拒。有銀行規定每月還款不能超過月收入的 70%。":
        "Most banks may decline. Some banks require that the monthly payment can't be more than 70% of monthly income.",
    "自己輸入":
        "Enter it myself",
    "用估計的可核貸金額":
        "Use the estimated approvable amount",
    "你每個月平均賺多少。算法：年收入（含年終獎金、分紅）÷ 12。例如年收入 72 萬，就填 6。填 0 代表不檢查信貸額度。":
        "How much you earn on average each month. Calculation: yearly income (including year-end bonus and profit share) ÷ 12. For example, for a yearly income of NT$720,000, enter 6. Enter 0 to skip the credit-limit check.",
    "你現在欠的、沒有拿房子或車子抵押的錢，全部加起來。要算：信用卡未繳的錢和分期、循環利息、預借現金、現金卡、其他信貸、已經開始還的學貸。不用算：房貸、有抵押的車貸、股票質借、券商融資。":
        "All the money you owe that is not secured by a house or car, added together. Count: unpaid credit-card balances and installments, revolving interest, cash advances, cash cards, other personal loans, and student loans you have started repaying. Don't count: mortgages, secured car loans, margin loans on stocks, broker margin financing.",
    "銀行實際肯借你幾倍的月收入，沒有公開的數字，所以這是估計。依網路文章（不是銀行公布的），多在 15～18 倍，預設的 20 比較樂觀。想保守一點，可以調低。法規最高是 22 倍。":
        "How many times your monthly income a bank will actually lend is not published, so this is an estimate. According to online articles (not published by banks), it is mostly 15 to 18 times, so the standard 20 is optimistic. To be more cautious, lower it. The legal maximum is 22 times.",
    "一個信貸產品最多借多少。大型民營銀行常見 500 萬，公股銀行常見 300 萬。專業人士專案可到 1,000～1,200 萬。":
        "The most one personal-loan product lends. Large private banks commonly offer NT\\$5 million and state-owned banks NT\\$3 million. Professional-worker programs can reach NT\\$10 to 12 million.",
    "自己輸入：本金照你填的算。用估計的可核貸金額：本金直接用下面算出來的一般可核貸金額，不能自己改。":
        "Enter it myself: the loan amount is what you enter. Use the estimated approvable amount: the loan amount is the typical approval calculated below, and you can't change it.",
    "你打算借多少錢來投資。例如填 100 就是借 100 萬。":
        "How much you plan to borrow to invest. For example, enter 100 for NT$1 million.",
    "目前用的是估計的可核貸金額，要自己填請把上面改成「自己輸入」。":
        "The estimated approvable amount is in use. To enter your own, change the setting above to \"Enter it myself\".",
    "額度檢查的細項（估計）":
        "Credit-limit details (estimate)",
    "平均月收入 (萬)":
        "Average monthly income (in NT$10,000)",
    "既有無擔保債務 (萬)":
        "Existing unsecured debt (in NT$10,000)",
    "核貸倍數（估計）(倍)":
        "Approval multiple (estimate) (times)",
    "產品最高額度 (萬)":
        "Product maximum (in NT$10,000)",
    "貸款金額怎麼決定":
        "How the loan amount is set",
    "⚠️ 超過可借上限 {cap} 萬。計算時會改用 {cap} 萬。":
        "⚠️ Over your borrowing limit of {cap}. The calculation uses {cap}.",
    "可借上限 {cap} 萬｜一般可核貸約 {z} 萬（估計）":
        "Borrowing limit {cap} | typical approval about {z} (estimate)",
    "年收入約 {yearly} 萬，未滿 30 萬。多數銀行的信貸申辦門檻是年收入 30 萬。":
        "Your yearly income is about {yearly}, under NT$300,000. For most banks, the minimum yearly income to apply for a personal loan is NT$300,000.",
    "你的既有無擔保債務 {d} 萬，已經用完法規上限（平均月收入 {inc} 萬 × 22 ＝ {gross} 萬）。依規定，不能再借信貸。":
        "Your existing unsecured debt of {d} has used up the legal limit (average monthly income {inc} × 22 = {gross}). By regulation, you can't borrow another personal loan.",
    "信貸額度：既有無擔保債務已用完法規上限，無法再借":
        "Credit limit: existing unsecured debt has used up the legal limit, so you can't borrow more",
    "用估計的可核貸金額算出來是 0 萬，無法計算。請改成「自己輸入」，或調高核貸倍數。":
        "The estimated approvable amount comes to NT$0, so it can't be calculated. Change the setting to \"Enter it myself\", or raise the approval multiple.",
    "信貸額度：用估計的可核貸金額算出來是 0 萬，無法計算":
        "Credit limit: the estimated approvable amount comes to NT$0, so it can't be calculated",
    "填平均月收入可以檢查信貸額度。":
        "Enter your average monthly income to check the credit limit.",
    "依新聞報導：2026-10-31 起，信貸的資金用途如果寫「投資理財」，銀行要先經你同意，才能查詢你在券商的借貸（例如融資）。你不同意，就辦不成。":
        "According to news reports: from 2026-10-31, if you state \"investing\" as the purpose of a personal loan, the bank must first get your consent before it can look up your brokerage borrowing (for example margin loans). If you don't consent, the loan can't be made.",
    "信貸額度是估計。各銀行條件常變動，以銀行核定為準。":
        "The credit limit is an estimate. Bank conditions change often. The bank's own approval is what counts.",
    "未檢查（沒有填平均月收入）":
        "Not checked (no average monthly income entered)",
    "超限":
        "Over",
    "灰底「超限」的格子：貸款本金超過可借上限 {cap} 萬，銀行不會核貸，所以不計算。":
        "Cells marked \"Over\" on grey: the loan is over the borrowing limit of {cap}. A bank won't approve it, so it isn't calculated.",
    "貸款本金 {y} 超過可借上限 {cap} 萬，無法計算":
        "A loan of {y} is over the borrowing limit of {cap}, so it can't be calculated",
    "以目前其他設定，就算借到可借上限 **{cap} 萬**，破產機率也只有 {r}，仍在 {t} 以下（你目前設定 {cur} 萬）。":
        "Even at the borrowing limit of **{cap}**, the chance of default is only {r}, within {t} (you entered {cur}).",
    "{cap} 萬（可借上限）":
        "{cap} (borrowing limit)",

    # ---- report.py ----
    "版本 {version}｜產生時間 {generated}":
        "Version {version} | Created {generated}",
    "主要結果":
        "Main results",
    "用這個連結可以重現同一組設定：":
        "Use this link to recreate the same settings: ",
    "這次的設定":
        "Settings for this run",
    "圖表需要連上網路才會顯示（會從 plotly 的 CDN 載入繪圖程式）；滑鼠移上去可以看數值。":
        "The charts need an internet connection to show (the plotting library loads from the plotly CDN). Move your mouse over a chart to see the values.",
    "本程式為自由軟體，以 AGPL-3.0 授權，不提供任何擔保。原始碼：":
        "This program is free software under the AGPL-3.0 license, with no warranty. Source code: ",

    # ---- engine.py ----
    "貸款本金必須大於 0。":
        "The loan amount must be more than 0.",
    "貸款利率不可為負。":
        "The loan rate can't be negative.",
    "升息後的利率不可為負。":
        "The rate after the hike can't be negative.",
    "貸款期數至少需要 1 個月。":
        "The loan term must be at least 1 month.",
    "寬限期必須短於貸款總年限。":
        "The interest-only period must be shorter than the loan term.",
    "升息年份與緩衝月數不可為負。":
        "The year of the rate hike and the number of buffer months can't be negative.",
    "配息投入第二標的的比例必須介於 0 與 1。":
        "The share of dividends put into the second ETF must be between 0 and 1.",
    "手續費必須介於 0 與 100% 之間。":
        "The trading fee must be between 0 and 100%.",
    "每月薪水補貼上限不可為負。":
        "The monthly salary limit can't be negative.",
    "賤賣折價設定超出範圍。":
        "The fire-sale discount settings are out of range.",
    "黑天鵝跌幅必須介於 0 與 100% 之間。":
        "The sudden-crash drop must be between 0 and 100%.",
    "股息率與股息連動程度不可為負。":
        "The dividend rate and how closely dividends follow the market can't be negative.",
    "未來情境的年度報酬率必須大於 -100%。":
        "The yearly returns of the future scenario must be above -100%.",
    "蒙地卡羅次數必須介於 1 與 100,000。":
        "The number of Monte Carlo runs must be between 1 and 100,000.",
    "區塊長度至少 1 個月。":
        "The block length must be at least 1 month.",
    "未知的 DCA 對照模式：{dca_mode}":
        "Unknown DCA comparison mode: {dca_mode}",
    "未知的蒙地卡羅配息來源：{mc_dividends}":
        "Unknown Monte Carlo dividend source: {mc_dividends}",
    "每年利率變動必須介於 -10 與 10 個百分點之間。":
        "The yearly rate change must be between -10 and 10 percentage points.",
    "利率隨機波動必須介於 0 與 5 個百分點。":
        "The random rate volatility must be between 0 and 5 percentage points.",
    "賣出的稅費合計必須低於 100%。":
        "The taxes and fees on selling must add up to less than 100%.",
    "股利的稅率與補充保費費率必須介於 0 與 100%，合計不可超過 100%。":
        "The dividend tax rate and the supplementary premium rate must each be between 0 and 100%, and together can't be more than 100%.",
    "補充保費門檻或股利所得比例超出範圍。":
        "The supplementary premium threshold or the share counted as dividend income is out of range.",
    "貸款開辦費必須小於貸款本金。":
        "The loan setup fee must be less than the loan amount.",
    "配息頻率必須是每 1、3、6 或 12 個月（或 0 代表依歷史判斷）。":
        "The dividend frequency must be every 1, 3, 6 or 12 months (or 0 to follow history).",
    "未知的失業模型：{mode}":
        "Unknown job-loss model: {mode}",
    "失業期間的薪水支援不可為負。":
        "The salary support during job loss can't be negative.",
    "請至少輸入一個年度報酬率。":
        "Enter at least one yearly return.",
    "年度報酬率必須大於 -100%。":
        "Yearly returns must be above -100%.",
    "年失業機率必須介於 0 與 1。":
        "The yearly chance of job loss must be between 0 and 1.",
    "平均失業月數必須大於 0。":
        "The average months of job loss must be more than 0.",
    "未知的失業時間分佈：{distribution}":
        "Unknown job-loss duration distribution: {distribution}",
    "崩盤時額外失業機率的範圍不正確。":
        "The range of the extra job-loss chance in a crash is not valid.",
    "沒有可回測的月份。":
        "There are no months to backtest.",
    "進場月份超出資料範圍。":
        "The start month is outside the data.",
    "資料至少需要 2 個月才能跑蒙地卡羅模擬。":
        "The data needs at least 2 months to run the Monte Carlo simulation.",
    "求解項目必須是 principal（貸款本金）或 salary_cap（每月自掏上限），收到：{field!r}":
        "The item to solve for must be principal (loan amount) or salary_cap (monthly out-of-pocket limit). Got: {field!r}",
    "目標破產率必須介於 0 與 1 之間（不含 0 與 1）。":
        "The target chance of default must be between 0 and 1 (not including 0 and 1).",
    "搜尋範圍與間距必須是有限的數字。":
        "The search range and step must be finite numbers.",
    "搜尋下限不可大於上限。":
        "The lower search limit can't be above the upper limit.",
    "搜尋間距必須大於 0。":
        "The search step must be more than 0.",
    "搜尋下限不可為負。":
        "The lower search limit can't be negative.",
    "貸款本金的搜尋下限必須大於 0。":
        "The lower search limit for the loan amount must be more than 0.",
    "貸款本金與每月自掏上限都至少要有一個值。":
        "The loan amount and the monthly out-of-pocket limit each need at least one value.",
    "熱圖的貸款本金必須大於 0。":
        "The loan amount in the heat map must be more than 0.",
    "熱圖的每月自掏上限不可為負。":
        "The monthly out-of-pocket limit in the heat map can't be negative.",
    "年度報酬率必須是用逗號分開的數字，例如「5, 10, -20」。":
        "Yearly returns must be numbers separated by commas, for example \"5, 10, -20\".",
    "每年利率變動必須是用逗號分開的數字，例如「0.25, 0.25, -0.125」。":
        "The yearly rate changes must be numbers separated by commas, for example \"0.25, 0.25, -0.125\".",
    "未知的還款資金來源：{src}":
        "Unknown repayment source: {src}",

    # ---- market_data.py ----
    "暫時無法取得 {ticker} 的完整歷史資料（已嘗試 3 次），也沒有先前存檔的資料可用。這不代表代號不存在，也可能是來源暫時異常或限制連線；請稍後按「重新載入行情」，並檢查代號。":
        "Couldn't get the full history of {ticker} (tried 3 times), and there is no saved copy to use. This doesn't mean the ticker doesn't exist. The source may be down or limiting connections. Press \"Reload market data\" later, and check the ticker.",
    "其中 {v1} 筆配息（{dates:%Y-%m-%d} 至 {dates1:%Y-%m-%d}）仍是分割前的單位，已一併換算":
        "{v1} dividends ({dates:%Y-%m-%d} to {dates1:%Y-%m-%d}) were still in pre-split units and were converted too",
    "{ticker} 的第一筆價格在 {v1:%Y-%m-%d}，目前只有一個月份的價格，還無法計算月報酬；沒有指定替身時，最早要等到 {v2} 有了第二筆月價才能進場。如果想現在就測試，可以在側欄「上市前的歷史用哪一檔代替」指定一檔上市更久的 ETF，用它的舊資料補上。":
        "The first price of {ticker} is on {v1:%Y-%m-%d}, and it has prices for only one month, so a monthly return can't be calculated yet. With no stand-in set, you can start at the earliest in {v2}, once the second monthly price exists. To test now, set a stand-in ETF that was listed earlier under \"Stand-in ETF for history before listing\" in the sidebar. Its older data fills the gap.",
    "請輸入 Yahoo Finance 代號，例如 0056.TW、00679B.TWO 或 SPY。":
        "Enter a Yahoo Finance ticker, for example 0056.TW, 00679B.TWO or SPY.",
    "代號「{ticker}」格式不正確：只能包含英數字與 . - ^ = 符號，最長 20 個字元。":
        "The ticker \"{ticker}\" is not in a valid format. It can contain only letters, digits and the symbols . - ^ =, up to 20 characters.",
    "資料來源回傳空值":
        "The data source returned nothing",
    "資料缺少價格或配息欄位":
        "The data is missing the price or dividend columns",
    "行情日期格式異常或包含重複日期":
        "The dates in the market data are malformed or repeated",
    "歷史價格為空或含無效價格":
        "The price history is empty or has invalid prices",
    "配息資料含缺值或無效數值，無法可靠計算現金流":
        "The dividend data has missing or invalid values, so cash flow can't be calculated reliably",
    "清單格式不正確":
        "The list is not in the expected format",
    "清單只有 {v1} 檔，可能被拒絕或不完整":
        "The list has only {v1} ETFs. It may have been refused or is incomplete",
    "無法取得上市 ETF 清單：{last}":
        "Couldn't get the list of listed ETFs: {last}",
    "證交所回應異常：{v1}":
        "The Taiwan Stock Exchange gave an unexpected reply: {v1}",
    "證交所與存檔在同一天的價格不一致，不合併":
        "The Taiwan Stock Exchange price and the saved copy disagree on the same day, so they were not merged",
    "單機版無法即時查詢行情，只能使用台灣上市的 ETF（目前 {v1} 檔，每天自動更新），沒有 {ticker} 的資料。請確認代號是否正確，例如 0056.TW、00878.TW。要測試其他商品，請使用網頁版。":
        "The standalone version can't look up market data live. It can only use ETFs listed in Taiwan ({v1} now, updated every day), and there is no data for {ticker}. Check that the ticker is correct, for example 0056.TW or 00878.TW. To test other products, use the web version.",
    "{ts:%Y-%m-%d} 單日 {v1:+.1%}":
        "{ts:%Y-%m-%d} one-day move {v1:+.1%}",
    "每月扣款日必須介於 1 至 31 日。":
        "The monthly payment day must be from 1 to 31.",
    "歷史價格為空或含非正價格，無法回測。":
        "The price history is empty or has non-positive prices, so it can't be backtested.",
    "歷史價格有缺漏月份，無法將跨月變動當作單月報酬；請重新載入行情。":
        "The price history is missing months, so a move across months can't be treated as a one-month return. Reload the market data.",
    "{m} 配息相當於股價的 {y:.1%}":
        "{m} dividend equals {y:.1%} of the price",
    "兩檔標的沒有共同可回測月份，請更換標的。":
        "The two ETFs have no common months to backtest. Choose different ETFs.",
    "共同資料有缺漏月份，無法安全執行逐月回測。":
        "The combined data is missing months, so the month-by-month backtest can't run safely.",
    "另有 {v1} 筆":
        "{v1} more",
    "{index} 至 {v1} 沒有任何配息紀錄，之後才開始有。如果它當時其實有配息，就是來源缺漏；這段期間的配息以 0 計":
        "There is no dividend record from {index} to {v1}. Dividends start only after that. If it actually paid dividends then, the source is missing them. Dividends for this period count as 0",
    "證交所沒有正常回應：{last_error}":
        "The Taiwan Stock Exchange did not respond normally: {last_error}",
    "補齊期間有除權，價格需要另外還原，不合併":
        "There was an ex-rights event in the period to fill, so prices would need a separate adjustment. Not merged",
    "1 股拆成 {n} 股":
        "a 1-for-{n}",
    "{ts:%Y-%m-%d} 來源價格出現 {v1:+.1%} 的永久位移，與標的指數走勢不符，已視為資料錯誤並把當日漲跌當作 0。":
        "{ts:%Y-%m-%d} the source price shows a permanent shift of {v1:+.1%} that doesn't match the underlying index. It was treated as a data error and that day's move was set to 0.",
    "{ts:%Y-%m-%d} 的價格跳動（{jump:+.1%}）符合{label}的股票分割，而來源沒有還原；已把這天之前的價格換算成同一基準，{dividend_note}。":
        "On {ts:%Y-%m-%d} the price jumped ({jump:+.1%}), which matches {label} stock split that the source did not adjust. Prices before that day were converted to the same basis, and {dividend_note}.",
    "{ts:%Y-%m-%d} 的價格跳動（{jump:+.1%}）符合{label}的股票分割，而來源沒有還原；已把這天之前的價格換算成同一基準。":
        "On {ts:%Y-%m-%d} the price jumped ({jump:+.1%}), which matches {label} stock split that the source did not adjust. Prices before that day were converted to the same basis.",
    "這檔標的":
        "this ETF",
    "{n} 股併成 1 股":
        "a {n}-for-1 reverse",

    # ---- version.py ----
    "⚠️ 本工具是財務工程的模擬，結果完全取決於歷史資料與你輸入的假設，僅供教育與研究用途，不構成任何投資建議。借錢投資可能損失全部本金並仍須償還貸款，請自行審慎評估，必要時諮詢專業人士。":
        "⚠️ This tool is a financial-engineering simulation. Its results depend entirely on historical data and the assumptions you enter. It is for education and research only and is not investment advice. Borrowing to invest can lose all your money and you must still repay the loan. Judge the risk carefully, and ask a professional if needed.",

    # ---- pages/1_Model_Details.py ----
    "🧮 計算方法說明":
        "🧮 How it works",
    "這一頁說明每個參數背後的公式與模型假設。看不懂沒關係——主頁面每個欄位旁的問號都有白話版本。":
        "This page explains the formulas and model assumptions behind each setting. Don't worry if it's hard to follow. Every field on the main page has a plain-words version behind its ? mark.",
    "← 回到壓力測試":
        "← Back to the stress test",
}
