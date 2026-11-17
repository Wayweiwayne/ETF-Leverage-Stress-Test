# 台灣個人信用貸款（信貸）額度上限研究報告

- 用途：給 PO 寫「選信貸時依月收入估算可借額度」的功能規格
- 研究日期／所有來源的查詢日期：**2026-11-17**（以下各來源除非另註，查詢日期都是這天）
- 來源標記：`[一手]` = 主管機關、銀行公會、聯徵中心、銀行官網；`[次級]` = 比價網站、部落格、新聞媒體
- 來源編號 `[S#]` 對應第 7 節的來源清單（含網址）

> **查證方法的限制（請先讀）**
> 這次研究環境的網路政策擋住了 WebFetch，`law.fsc.gov.tw`（金管會法規系統）和 `law.banking.gov.tw`（銀行局法規系統）都無法直接開啟（DNS 解析失敗）。依環境提示，之後沒有再逐一嘗試開啟其他網站。
> 因此本報告的內容都來自 **WebSearch 搜尋結果對該網頁內容的擷取與摘要**，我沒有逐字讀過原始網頁全文。數字以搜尋結果引述的原文片段為準。重要的法源字號、日期，以及規格要用的關鍵數字，建議 PM／PO 在定案前親自點開第 7 節的連結核對一次；或在環境網路設定中允許上述網域後再請我核對。

---

## 1. 結論（給 PO 的一段話）

使用者聽到的「信貸上限是月薪的 22 倍」**大致對，但有三處要修正**：
(1) 基數是「**平均月收入**」，一般是年收入（含年終、獎金、分紅）÷ 12，不是單看月薪 [S1][S10][S11]；
(2) 22 倍限制的是借款人在**全體金融機構的「無擔保債務總餘額」**（信用卡、現金卡、信貸合計），不是單筆信貸，所以既有的卡債、分期、其他信貸都會吃掉額度 [S1][S3][S10]；
(3) 「信用很好、資產很多就能超過」**不正確**。22 倍是主管機關的紅線，金管會 2025-12 還強調「DBR22 倍並未鬆綁，也不會取消」[S7]。信用好或資產多的作用是：讓銀行承認較高的收入（例如用財力證明、流動性資產或財力評估模型）[S7][S14]，以及核貸時更接近 22 倍和產品上限，而不是突破 22 倍。真正的例外只有特定用途、依企業戶程序辦理或有擔保的貸款 [S4][S5]，不適用於一般「借錢投資 ETF」的信貸。

**建議 PO 在規格中採用的規則：**

```
平均月收入        = 年收入（含年終獎金、分紅等）÷ 12
法規上限(DBR22)   = 平均月收入 × 22 − 既有無擔保債務餘額
                    （既有無擔保債務 = 信用卡應繳／未到期分期／循環 + 現金卡 + 其他信貸餘額 + 已開始還款的學貸）
可借上限          = min( 法規上限, 產品最高額度 )
估計可核貸金額    = min( 平均月收入 × 核貸倍數 − 既有無擔保債務, 產品最高額度 )
另外檢查          ：新信貸月付金 + 既有各項月付金 ≤ 平均月收入 × 月付比上限
```

**建議預設值：**

| 參數 | 建議預設 | 可調範圍 | 依據 |
|---|---|---|---|
| 法規倍數上限 | **22 倍**（硬上限：超過就提醒，並以上限計算） | 固定，不讓使用者改 | [S1][S2][S7] |
| 「一般情況」核貸倍數 | **16 倍**（介面上標示「估計，實際依銀行審核」） | 保守 12／一般 16／最高 22 | 只有次級來源，見第 4 節 |
| 既有無擔保債務 | 0（請使用者自行填寫） | ≥ 0 | [S1][S10] |
| 產品最高額度 | **500 萬元** | 300 萬（公股銀行常見）～800 萬（大型民營銀行一般產品）；專業人士方案 1,000～1,200 萬 | 第 3 節比較表 |
| 信貸最長年限 | **7 年** | 1～7 年；少數銀行有 10 年期方案 | 第 3 節 |
| 月付比提醒門檻 | 總月付 > 月收入 **1/3** 時提醒「偏高」；> **70%** 時提醒「多數銀行可能婉拒」 | — | 1/3：臺銀、土銀產品條件 [S25][S27]；70%：凱基官網 [S20] |
| 年收入門檻 | 年收入 < 30 萬時提醒「多數銀行的申辦門檻是年收入 30 萬」 | — | 國泰、中信、富邦、兆豐、合庫 [S16][S17][S19][S23][S24] |

說明：平均月收入低於約 22.7 萬元（500 萬 ÷ 22）時，22 倍規則會比產品最高額度先卡住，所以對大多數使用者來說，真正有作用的是 DBR22 和既有債務；產品最高額度只對高收入者有影響。

---

## 2. 主管機關規定（DBR22）

### 2.1 規定內容與法源

| 項目 | 內容 | 來源 |
|---|---|---|
| 規範文字 | 「金融機構對於債務人於全體金融機構之無擔保債務歸戶後之總餘額（包括信用卡、現金卡及信用貸款）除以平均月收入，**不宜**超過 22 倍」（簡稱 DBR22 倍，DBR = Debt Burden Ratio） | [S2][S3]`[一手]` |
| 最初的函令 | 據搜尋結果，源自金管會 **民國 94 年（2005）12 月 19 日** 金管銀(四)字第 09440010950 號函，背景是 2005 年的「雙卡風暴」。**此字號與日期是搜尋摘要給的，我沒有看到函令原文，需要核對** | [S8]`[一手，未逐字核對]`；背景：[S9]`[次級]` |
| 現金卡的明文規定 | 《金融機構辦理現金卡業務應注意事項》第五點第三款：核給的可動用額度加計申請人在全體金融機構的無擔保債務（含信用卡）歸戶總餘額，「**不得**超過申請人最近一年平均月收入之二十二倍」；調高額度時也要符合。該注意事項在 94-04-29 訂定（金管銀(四)字第 0944000230 號令），最近一次修正第 5 點是 **110-11-02**（金管銀票字第 11002735121 號令，修正的是成年年齡，22 倍沒有改） | [S4]`[一手]`、[S12]`[次級：法規轉載]` |
| 信用卡的授權條文 | 《信用卡業務機構管理辦法》第 22 條：核給額度加計申請人在全體金融機構的無擔保債務（含信用卡）歸戶總餘額，與「最近一年內平均月收入」的倍數，「應依主管機關規定辦理」（條文本身沒寫 22 這個數字；修正說明提到參酌金管會 94 年 12 月函令） | [S13]`[一手]` |
| 信用卡分期納入 | 金管會 **97-03-03** 金管銀(四)字第 09700067290 號函：信用卡「**未到期分期償還待付金額**」納入 DBR22 的無擔保債務項目 | [S3]`[一手]` |
| 2025-12 最新動態 | 金管會 2025-12-18 銀行總經理聯繫會議：同意把「財力評估模型」列為認定平均月收入的方式之一；並強調「DBR 22 倍**並未鬆綁，也不會取消**，仍是放貸基本紅線」 | [S7]`[次級：聯合報/經濟日報]` |
| 2026-10 最新動態（與本 App 直接相關） | 因應「四貸同堂」借錢買股，金管會推動銀行與券商「跨業聯徵」：**2026-10-31 起**，銀行新承作的個人信貸，如果資金用途是「投資理財」，必須在取得客戶同意後，查詢客戶在證券端的融資融券、不限用途款項借貸等餘額；客戶不同意，就無法辦理授信。金管會沒有因此另設借款上限，DBR22 不變。另外，2026-10 起本國銀行要新增申報「個人購買股票等金融商品理財周轉金」 | [S30][S31][S32]`[次級：新聞]` |

**生效時間小結：** DBR22 自 2005 年底（民國 94 年 12 月）起由金管會函令要求，並寫進現金卡注意事項與信用卡管理辦法；2008 年把信用卡分期納入；到 2026-11 仍然有效。

### 2.2 哪些債務要算進去

| 債務類型 | 是否計入 DBR22 | 依據與可信度 |
|---|---|---|
| 信用貸款（分期型）餘額 | **計入** | 規範原文 [S2]`[一手]` |
| 信用卡：已消費未繳、循環餘額、預借現金 | **計入** | 規範原文寫「信用卡」[S2]；細項見 [S10][S11]`[次級]` |
| 信用卡分期（未到期分期待付款） | **計入**（2008-03 起） | [S3]`[一手]` |
| 現金卡 | **計入** | 規範原文 [S2]；計入的是「已動用」還是「可動用額度」，各來源說法不一，見第 6 節 |
| 循環型信貸（額度型） | 計入；以額度還是已動用金額計算，**查不到一手說明** | 規範原文寫「信用貸款」[S2] |
| 就學貸款 | 政策性就學貸款**排除**，但「屆期開始清償時仍須依規定辦理」，也就是**開始還款後計入** | [S5]`[一手]`；凱基、永豐官網也說學貸會占用額度 [S20][S21] |
| 房貸、理財型房貸 | **不計入**（有不動產擔保） | 規範只涵蓋無擔保債務 [S2]；[S10][S22]`[次級／一手]` |
| 部分擔保、副擔保貸款 | **超出擔保品鑑估值的部分要計入**：「貸款餘額（擔保放款餘額加上部分擔保、副擔保貸款餘額）扣除擔保品鑑估值」 | [S6]`[一手]` |
| 車貸 | 有動產擔保的車貸**不計入**（一般說法） | Nextbank 官網等 [S22]`[一手：銀行文章]`；沒有找到金管會的明文 |
| 股票質借、券商融資 | 有擔保，不屬於 DBR22；2026-10-31 起透過跨業聯徵讓銀行看得到 | [S30][S31] |

### 2.3 「月收入」怎麼認定

| 問題 | 結論 | 來源 |
|---|---|---|
| 法規用語 | 「最近一年（內）平均月收入」 | 現金卡注意事項、信用卡管理辦法 [S4][S13]`[一手]` |
| 年收入 ÷ 12？ | 是，實務做法是年收入 ÷ 12。例如凱基：年收入 60 萬 ÷ 12 = 5 萬，× 22 = 110 萬 | 凱基官網 [S20]`[一手：銀行]` |
| 含年終獎金嗎？ | **含**。年終獎金、分紅、其他獎金都算入年收入 | 凱基、渣打官網 [S20][S18]`[一手：銀行]`；次級來源 [S10][S11] |
| 要什麼財力證明 | 常見文件：扣繳憑單、所得清單、薪資單、薪轉存摺；部分銀行要近 6 個月收入證明再換算年收入；收入未達門檻時，可另外附本人的流動性資產（存款、投資）佐證 | 中信 [S17]、永豐 [S21]`[一手：銀行]`；次級補充 [S11] |
| 新方式 | 2025-12 起，銀行可以用「財力評估模型」（AI／大數據推估）認定平均月收入，主要給不容易證明財力的人（自由業、網紅等）。玉山 2024-08 是第一個試辦案 | [S7]`[次級：新聞]` |

### 2.4 適用範圍與例外

- **適用對象**：金融機構（銀行、信用卡及現金卡發卡機構）辦理個人無擔保授信 [S2][S4][S13]。所有銀行都適用；凱基官網把它描述為「各家銀行共同適用的基準」[S20]。
- **排除適用 DBR22 的項目**（金管會 97-01-07 金管銀(四)字第 09600523370 號函，以及後續函釋）[S5][S6]`[一手]`：
  1. 借款用途是創業、所營事業營運週轉金、建築融資、投標保證金、農業用途，**而且銀行依「企業戶」授信程序辦理**；
  2. 個人無擔保放款在「一定合理期間」（不超過 6 個月）內設定擔保物權的，例如法拍屋代墊投標保證金與尾款、員工認股、自建自住房屋的建築融資、都市更新貸款；102 年再加入「限制員工權利新股」貸款（合理期間不超過 3 年）、不動產買賣價金信託墊付款等；
  3. 政策性就學貸款（開始還款後仍要計入）、青年創業／微型創業貸款、農業信用保證基金保證的貸款；
  4. 其他經專案核准的個案。
- **對本 App 的意義**：使用者借信貸投資 ETF，屬於一般個人消費性信貸，**不適用上述例外**，應該視為一定受 22 倍限制。

---

## 3. 各銀行信貸產品比較表

說明：
- 「最高額度」是產品頁宣傳的上限，實際核貸一律另受 DBR22 與個人信用條件限制。
- 利率多為「定儲利率指數或指標利率 + 加碼」的機動利率；首期 0.01% 這類是促銷利率，不代表長期利率。
- 「倍數規則」一欄：除了另外註明的以外，各銀行都**沒有公開比 22 倍更細的倍數**，只寫依 DBR22 與個人條件核定。
- 資料年份：標示為頁面上看得到的基準日或活動期間；沒有標示的，就是 2026-11-17 搜尋時頁面的現況。

| 銀行 | 產品 | 最高額度 | 倍數規則 | 最長年限 | 利率（公開區間） | 特殊族群較高額度方案 | 來源 |
|---|---|---|---|---|---|---|---|
| 台新 | 一般信貸／Richart 信貸 | **500 萬**（較早的頁面寫 300 萬） | 官網文章引用 DBR22 | 一般 2～7 年，**最長 10 年**（2025 年底推出 10 年期） | 2.88%～15% 機動（30 萬、5 年試算的 APR 為 4.12%～16.39%） | 醫師方案（年收入 ≥ 200 萬，2026-09-30 截止）、優質科技企業員工（2.99%，已截止）；**額度查不到**；申請年齡 20～60 歲（次級） | [S15]`[一手]`、[S15b]`[次級]` |
| 國泰世華 | 泰幸福信用貸款 | **500 萬**（部分次級來源寫 300 萬） | 未公開 | 7 年 | 前 6 期 1.88% 起，第 7 期起 5.43% 起機動；一段式 4.73% 起（次級） | 職域員工信貸專案 500 萬、1.68% 起；大樹速貸（邀請制）300 萬、3.33% 起；條件：滿 20 歲、年齡 + 期限 ≤ 65、年收入 ≥ 30 萬 | [S16]`[一手]` |
| 中國信託 | 分期型信貸（Online 貸） | **800 萬** | 未公開；官網額度試算要填年收入與既有卡債、貸款餘額 | 7 年（84 期） | 首期 0.01%，第 2 期起 2.99% 起機動（30 萬、5 年的 APR 為 4.13%～16.29%） | 公教白領、有屋族、優質客戶方案同為 800 萬；循環型 300 萬、1 年；條件：18～65 歲、年收入 ≥ 30 萬；收入不夠時可附流動性資產 | [S17]`[一手]` |
| 玉山 | e 指信貸 | **800 萬** | 未公開；FAQ 說負債不得超過「月薪 22 倍」 | 7 年（12～84 期） | 試算例：首期 0.01%，第 2 期起 4.75%～16.00% | **醫師專屬 1,200 萬（菁英以上會員最高 1,500 萬）**；六師（醫師、律師、會計師、建築師等）800 萬（2026-10-01～12-31）；卡友信貸 300 萬；公教專屬 84 期 | [S14]`[一手]` |
| 台北富邦 | 富邦一般信貸 | **800 萬**（同頁另一處寫 500 萬） | 未公開 | 7 年 | I+1.79%～13.27%（目前 3.50%～14.98%）機動；APR 4.74%～16.37% | 優職貸、優選企業員工信貸 500 萬、2.4%～2.7% 起；自營業主 100 萬、6.78% 起；循環型 300 萬、3 年；條件：18 歲至未滿 64 歲、年收入 ≥ 30 萬 | [S19]`[一手]` |
| 永豐 | 數時貸（數位信貸） | **800 萬**（另一版一般分期型寫 300 萬） | 官網文章舉例：月收入 5 萬 × 22 = 110 萬 | 7 年 | 分期型前三期 1.66%～14.60%，第四期起 5.65%～14.60% 機動 | 醫護信貸 800 萬；軍公教尊榮信貸 500 萬、84 期（2024 新聞稿寫 800 萬，互相矛盾）；私房錢（循環）150 萬、3 年、3.5%～15% | [S21]`[一手]` |
| 凱基 | 上班族信貸 | **500 萬** | 官網：DBR ≤ 22 倍，加上**月負債支出比 ≤ 70%** | 一般 2～7 年；部分專案 10 年 | 依條件核定 3.5%～15.99%；優惠起點 2.71%～2.88% | **專業新世貸 1,000 萬、最長 10 年**（軍公教、醫師、律師、會計師、建築師、金融同業、上市櫃與優質企業、外商）；醫護信貸 1,000 萬（2026 年度）；速還金（額度型）100 萬 | [S20]`[一手]` |
| 星展 | 個人信貸 | **300 萬**（最低 10 萬） | 未公開 | 1～7 年 | 3.16%～16% 機動 | 卡友信貸／十年期信貸 **500 萬、最長 10 年**；條件：20～63 歲、年收入 ≥ 22 萬、年資滿半年 | [S26]`[一手]` |
| 滙豐 | 個人信用貸款 | **300 萬**（英文頁「最高月薪 15 倍」）；但官網另一處寫「Financing up to TWD 8,000,000」，**互相矛盾** | **月薪 15 倍**（英文頁，日期不明） | 1～7 年（12～84 期） | 首期 0.01%，第 2 期起 2.54%～15.99% | 卓越理財客戶 300 萬（2020 年專案）；條件：月收入 ≥ 5 萬、18～55 歲（英文頁）或 18～60 歲（中文頁） | [S28]`[一手]` |
| 渣打 | 信用貸款（多數方案） | **600 萬**；理享貸 350 萬 | 官網文章：一般最高可達月收入 22 倍；核貸會抓月收支比約 40～45% | 1～7 年 | 優質客戶 2.99% 起；尊爵專案首期 0.01%、2.68% 起 | 尊爵專案、優質客戶信貸方案（醫師、律師、會計師、上市公司員工、金融同業）600 萬 | [S18]`[一手]` |
| 王道 | 一般信用貸款 | **500 萬** | 未公開 | 7 年 | 一段式 3.49%～16% 機動（基準日 2026-03-23） | 女性專屬（前 3 期 1.38%，第 4 期起 3.9%～16%）；優質客群 3.31% 起（2025-05 基準）；外送員 15 萬、24 期、15.90%；中高齡方案的額度查不到 | [S29]`[一手]` |
| 第一銀行 | iLEO 信用貸款（大桶金） | **300 萬**（小桶金 3～15 萬） | 未公開 | 7 年 | 1.80%～15.00% 機動 | 公教人員專屬信貸 300 萬、84 期、2.50% 起（非循環 2.5%～5.00%）；第 e 數速貸要求現職滿 6 個月；樂活理財信貸 3.04%～10.00%，額度查不到 | [S23]`[一手]` |
| 合作金庫 | 一般／薪轉戶／優職優利信貸 | **有保證人 300 萬；沒有保證人 80 萬** | 未公開 | 7 年 | 薪轉戶前 3 個月 2.08% 起；軍公教前 3 個月 1.78% 起、第 4 個月起 1.89% 起（2026 年活動） | 軍公教優惠信貸、優職優利（專業人士、上市櫃員工）同樣是 300 萬／80 萬；國軍專案沒有保證人 120 萬；特約商店業主 100 萬、5.678%～7.678%；條件：年收入 ≥ 30 萬 | [S24]`[一手]` |
| 兆豐 | 個人信用貸款（專屬方案） | **300 萬** | 未公開 | 7 年（2～7 年） | 2.70%（IR+0.982%）起，每月浮動（基準日 2024-04-23） | 公教好享貸 300 萬、2.20% 起；生活好享貸前 3 期 0.66%（綁約 12 期）；條件：年收入 ≥ 30 萬、年齡 + 年限 ≤ 65 | [S25b]`[一手]` |
| 臺灣銀行 | 消費者貸款（未提供擔保） | 公教機關或公營事業員工 **150 萬**（經權最高額度）；另有一列 120 萬、5 年（類別無法確認）；民營事業員工 80 萬、5 年（次級） | **每月攤還本息不得超過收入 1/3**（次級來源引述臺銀表格） | 公教 7 年；其他 5 年 | 表格列有 2.866%、4.617%、5.907% 等數字，各欄對應的條件無法從搜尋擷取確認（115-09-21 起適用指數 1.751%） | 公教員工即為較高額度族群（150 萬）；公教房貸「築巢優利貸」不是信貸 | [S27]`[一手：利率表 PDF]`、[S27b]`[次級]` |
| 土地銀行 | 一般信用貸款 | 公營機構正式員工 **200 萬**；民營公司經理級以上 200 萬；其他員工 **100 萬** | **每月攤還本息不超過每月薪資收入 1/3** | 7 年（到期日不得晚於退休日） | 試算例 4%～7%（APR 4.73%～7.79%） | 社會菁英 200 萬；優選菁英 200 萬（同一民營企業滿 2 年）；公教員工低利貸款 200 萬；薪褔貸 100 萬 | [S25]`[一手]` |

**比較表觀察：**
- 一般上班族可申請的產品最高額度大致分成三群：**公股銀行 80～300 萬**（臺銀、土銀、合庫、第一、兆豐）、**大型民營銀行 500～800 萬**（台新、國泰、凱基、王道、星展卡友為 500 萬；中信、玉山、富邦、永豐為 800 萬）、**外商 300～600 萬**（滙豐、渣打）。
- 專業人士或高資產族群的方案上限明顯較高：凱基 1,000 萬、玉山醫師 1,200～1,500 萬、中信與永豐醫護 800 萬、渣打 600 萬。但**這些方案仍受 DBR22 限制**，提高的是產品上限，不是倍數。
- 公開寫出「比 22 倍更低的倍數」的只有滙豐（月薪 15 倍），另外臺銀、土銀用「月付 ≤ 收入 1/3」來限制額度。

---

## 4. 實務上常見的核貸倍數

**重要提醒：我沒有找到任何一手來源（銀行、金管會、聯徵中心）公布「實際核貸平均是月收入幾倍」。** 下面的倍數全部來自比價網站、貸款業者或部落格 `[次級]`，彼此差距不小，只能當作參考區間。

| 來源 | 說法 |
|---|---|
| AlphaLoan（信貸比價） [S33] | 銀行平均核定額度多落在平均月收入 16～18 倍，部分約 20 倍，保守的只有 16 倍 |
| houseloan.tw [S34] | 多數銀行內部風控更保守，安全上限大約 14～18 倍 |
| Roo.Cash／Money101 等 [S10][S11] | 許多銀行不會讓人貸滿，通常最高只到 16～18 倍 |
| 其他貸款網站彙整 [S35] | 10～15 倍、15～18 倍、16～20 倍都有人說；條件好的人才可能接近 20 倍以上 |
| 一手的間接佐證 | 滙豐公開「月薪 15 倍」[S28]；臺銀、土銀的月付 ≤ 收入 1/3 規則，換算成本金：7 年期、利率約 3%～5% 時，約等於月收入 23.6～25 倍，所以這時真正卡住的還是 22 倍；5 年期、利率約 4.6% 時，只有約 18 倍（我自己用本息平均攤還公式算的） |

**整理出的區間（供 App 參數使用）：**

| 情境 | 倍數（× 平均月收入，再扣既有無擔保債務） | 說明 |
|---|---|---|
| 保守 | **10～12 倍** | 信用普通、有其他卡債或分期、任職小公司或年資短、收入證明不完整 |
| 一般 | **15～18 倍**（建議預設 16 倍） | 信用正常、有薪轉或扣繳憑單的上班族 |
| 最高 | **22 倍**（法規天花板） | 信用良好、公教、專業人士、優質企業員工、無其他負債；同時受產品最高額度限制 |

補充數據 `[次級]`：經濟日報報導引述聯徵中心數據，某年 1 月新增個人信貸約 81,267 人、新增金額 902.2 億元；總人數約 185.9 萬人、總餘額突破 1.5 兆元 [S36]。換算每人平均新增約 111 萬元，但這是我自己算的，不是官方公布的平均值；報導的年份也沒有在搜尋摘要中確認（推測為 2026 年初）。

---

## 5. 其他會影響額度的限制

| 限制 | 常見標準 | 來源 |
|---|---|---|
| 月負債收支比（每月應還的所有負債 ÷ 平均月收入） | 凱基：≤ 70%，超過會婉拒或調降額度；渣打：核貸額度約抓月收支比 40～45%；臺銀、土銀：每月攤還本息 ≤ 收入 1/3 | [S20][S18][S25][S27b] |
| 總資產負債比（總負債 ÷ 總資產） | 常見參考 < 60%，屬於業界慣例，不是法規 | LINE Bank 文章 [S37]、[S11]`[次級]` |
| 年收入門檻 | 多數銀行要求年收入 ≥ 30 萬（國泰、中信、富邦、兆豐、合庫）；星展 ≥ 22 萬；滙豐月收入 ≥ 5 萬 | [S16][S17][S19][S25b][S24][S26][S28] |
| 年齡 | 下限 18 或 20 歲；上限常見「年齡 + 貸款年限 ≤ 65」（國泰、兆豐），或 63～65 歲（星展 63、富邦未滿 64、玉山 64、中信 65） | 同上 |
| 年資 | 現職滿 6 個月（第一銀行第 e 數速貸、星展）；土銀優選菁英要求同一企業滿 2 年；合庫優職優利要求同一單位滿 2 年且年收入 ≥ 60 萬 | [S23][S26][S25][S24] |
| 保證人 | 合庫：沒有保證人時，最高額度從 300 萬降到 80 萬 | [S24] |
| 聯徵查詢次數 | 短期內查詢太多次（例如 3 個月內超過 3 次）會被視為急需用錢，扣分 | [S11]`[次級]` |
| 資金用途 | **2026-10-31 起**，用途寫「投資理財」的新信貸，銀行必須在客戶同意後查詢證券端借貸；不同意就無法授信 | [S30][S31] |
| 職業與任職單位 | 公教、醫師、律師、會計師等專業人士、上市櫃或百大企業員工，較容易拿到高額度和低利率 | 永豐官網 [S21]、[S35] |

---

## 6. 不確定或互相矛盾的地方

1. **「不宜」還是「不得」**：金管會的 DBR22 函令用「**不宜**超過 22 倍」[S2][S3]；現金卡注意事項第五點用「**不得**超過」[S4]；信用卡管理辦法寫「依主管機關規定辦理」[S13]。
   **判斷：** 實務上應該視為硬上限。理由：現金卡規定是明文「不得」，金管會 2025-12 公開稱它為「放貸基本紅線」[S7]，各銀行官網也一致當成上限 [S14][S20][S21]。
2. **最初函令的字號與日期**：「94-12-19 金管銀(四)字第 09440010950 號」只出現在搜尋摘要中 [S8]，我沒看到函令原文。94 年 12 月這個時間，信用卡管理辦法的修正說明可以佐證 [S13]，但完整字號需要核對。
3. **現金卡計入的是「已動用」還是「可動用額度」**：次級來源有寫「已動用」、有寫「可動用」、也有寫「已動用或可動用」[S10][S12]。現金卡注意事項規定，新核的是「核給的可動用額度」加計既有債務 [S4]，所以至少在核卡當下，額度本身會被計入。既有現金卡在其他銀行歸戶時怎麼算，**查不到一手說明**。循環型信貸是以額度還是已動用金額計算，也**查不到**。
4. **各銀行產品上限，在同一家銀行內也互相矛盾**：
   - 富邦同一頁有 800 萬和 500 萬兩種寫法 [S19]（較新的寫法是 800 萬）；
   - 滙豐英文頁寫「月薪 15 倍、上限 300 萬」，官網另一處寫「up to TWD 8,000,000」[S28]，**無法判斷哪個是現行**；
   - 永豐軍公教：專案頁寫 500 萬，2024 新聞稿寫 800 萬 [S21]（以專案頁為準）；
   - 國泰泰幸福：官網寫 500 萬，部分次級網站寫 300 萬 [S16]（以官網為準）；
   - 台新：現行頁面寫 500 萬，舊頁面寫 300 萬 [S15]（以現行頁為準）。
   原則：**以銀行官網現行產品頁為準，次級網站與舊活動頁不採用。**
5. **臺灣銀行利率表**：搜尋擷取只看得到部分數字（150 萬／7 年、120 萬／5 年、2.866%、4.617%、5.907% 等），沒辦法確定每個數字對應哪一欄或哪個類別 [S27]。「民營事業員工 80 萬／5 年」和「月付 ≤ 收入 1/3」來自次級來源引述 [S27b]。
6. **實務核貸倍數**：完全沒有一手數據，次級來源的說法從 10 倍到 22 倍都有（第 4 節）。建議 App 介面標示「估計值」，並讓使用者自己調整。
7. **時效性**：利率與促銷（首期 0.01% 等）變動頻繁，許多活動在 2026 年底到期（玉山六師、渣打尊爵到 2026-12-31；台新醫師方案已在 2026-09-30 截止）。**規格不應寫死銀行利率**；額度上限與 DBR22 比較穩定。
8. **跨業聯徵的細節**：2026-10-31 新制的內容來自多家新聞報導 [S30][S31][S32]，沒有取得金管會新聞稿原文；券商端的觸發門檻（3 億元或券商淨值 1%）各報導描述略有差異。

---

## 7. 來源清單

所有來源的查詢日期都是 **2026-11-17**。內容取自 WebSearch 對該網頁的擷取或摘要（原因見文首）。

**主管機關、法規 `[一手]`**
- [S2] 金管會主管法規共用系統：〈關於適用 DBR22 倍之個人無擔保貸款項目之說明〉（97-01-07 金管銀(四)字第 09600523370 號）— https://law.fsc.gov.tw/LawContent.aspx?id=FE052046
- [S3] 金管會主管法規共用系統：將信用卡「未到期分期償還待付金額」納入 DBR22 項目（97-03-03 金管銀(四)字第 09700067290 號）— https://law.fsc.gov.tw/LawContent.aspx?id=FE057297
- [S4] 金融機構辦理現金卡業務應注意事項（第五點、沿革）— https://law.fsc.gov.tw/LawContent.aspx?id=FL035378 ；第五點條文 https://law.banking.gov.tw/Chi/FLAW/FLAWDOC01.aspx?lsid=FL035378&lno=5 ；第五點修正對照表 https://law.banking.gov.tw/Chi/GetLawFile.ashx?fileid=0000303811
- [S5] 銀行局：DBR22 倍之個人無擔保貸款項目說明（排除項目）— https://law.banking.gov.tw/chi/NewsContent.aspx?msgid=1018 ；https://law.fsc.gov.tw/LawContent.aspx?id=GL001009
- [S6] 金管會：部分擔保、副擔保貸款納入 DBR22 規範 — https://law.fsc.gov.tw/LawContent.aspx?id=GL003875
- [S8] 搜尋摘要所指的 94-12 函令來源（公平會處分書、銀行局判解函釋）— https://www.ftc.gov.tw/uploadDecision/119d84f9-69fd-426e-a1f2-be9b60bb2b69.pdf ；https://law.banking.gov.tw/Chi/FLAW/FLAWDOC03.aspx?datatype=etype&cnt=12&keyword=22%E5%80%8D&recordNo=9
- [S13] 信用卡業務機構管理辦法第 22 條與修正對照表 — https://law.banking.gov.tw/Chi/FLAW/FLAWDOC01.aspx?lsid=FL006433&lno=22 ；https://law.banking.gov.tw/Chi/GetLawFile.ashx?fileid=0000157453

**銀行官網 `[一手]`**
- [S14] 玉山：FAQ「薪水多寡與核貸額度」https://www.esunbank.com/zh-tw/about/faq/content?q=loan%2F024 ；信貸 https://www.esunbank.com.tw/bank/personal/loan/personal ；醫師專屬 https://www.esunbank.com/zh-tw/marketing/digital/doctor_personal ；六師 https://event.esunbank.com.tw/credit/elite-loan/index.html ；FAQ 最高額度 https://www.esunbank.com/zh-tw/about/faq/content?q=loan%2F023 ；公教 https://event.esunbank.com.tw/credit/gov-employee-loan/index.html
- [S15] 台新：https://www.taishinbank.com.tw/TSB/personal/loan/credit/my-plan/ ；https://www.taishinbank.com.tw/TSB/about-taishin/taishin-article/TSBankGridPage-000321/ ；Richart https://mkp.taishinbank.com.tw/s/2026/2026tsrichartloan/index.html ；https://www.taishinbank.com.tw/TSB/personal/common/news/TSBankNews-007931/
- [S16] 國泰世華：泰幸福 https://www.cathaybk.com.tw/cathaybk/personal/loan/product/personal-loan/ ；大樹速貸 https://www.cathaybk.com.tw/cathaybk/personal/loan/product/tree-loan/ ；職域員工 https://www.cathaybk.com.tw/cathaybk/personal/loan/product/employee-loan/
- [S17] 中國信託：分期型 https://www.ctbcbank.com/content/dam/minisite/long/loan/leader/loan1.html ；公教白領 https://www.ctbcbank.com/content/dam/minisite/long/loan/leader/project2.html ；有屋族 https://www.ctbcbank.com/content/dam/minisite/long/loan/leader/project5.html ；額度試算 https://www.ctbcbank.com/content/dam/minisite/long/loan/leader/calculate1.html ；循環型 https://www.ctbcbank.com/content/dam/minisite/long/loan/leader/loan2.html
- [S18] 渣打：https://www.sc.com/tw/personal-loan/ ；尊爵 https://www.sc.com/tw/personal-loan/top-professional/ ；優質客戶 https://www.sc.com/tw/personal-loan/elite/ ；負債比文章 https://www.sc.com/tw/personal-loan/articles/debt-burden-ratio/ ；利率文章 https://www.sc.com/tw/personal-loan/articles/about-pricing/
- [S19] 台北富邦：一般信貸 https://www.fubon.com/banking/personal/personal_loan/personal_loan01/personal_loan01.htm ；優職貸 https://www.fubon.com/banking/personal/personal_loan/personal_loan06/personal_loan06.htm ；優選企業 https://www.fubon.com/banking/personal/personal_loan/personal_loan03/personal_loan03.htm ；自營業主 https://www.fubon.com/banking/personal/personal_loan/personal_loan04/personal_loan04.htm ；循環型 https://www.fubon.com/banking/personal/personal_loan/personal_loan05/personal_loan05.htm
- [S20] 凱基：額度怎麼算 https://www.kgibank.com.tw/zh-tw/kgibarticleshome/loan/pl_loan-amount ；上班族信貸 https://www.kgibank.com.tw/zh-tw/personal/loan/personal/salaried ；專業新世貸 https://www.kgibank.com.tw/zh-tw/personal/loan/personal/elite ；醫護 https://www.kgibank.com.tw/zh-tw/personal/promotion/loan/pl-mediloan ；10 年期 https://www.kgibank.com.tw/webpages/loan-personal-campaign/index.html ；速還金 https://www.kgibank.com.tw/zh-tw/personal/loan/revolving/revolving-loan
- [S21] 永豐：信貸最高額度文章 https://bank.sinopac.com/sinopacBT/personal/article/smart-consumption/high-credit-limit.html ；小額信貸文章 https://bank.sinopac.com/sinopacBT/personal/article/smart-consumption/small-unsecured-loan.html ；信用貸款文章 https://bank.sinopac.com/sinopacBT/personal/article/smart-consumption/credit-loan.html ；數時貸 https://bank.sinopac.com/sinopacBT/webevents/1910_PLdigital/index.html ；軍公教 https://bank.sinopac.com/sinopacBT/webevents/2203pogotpl/index.html ；醫護 https://bank.sinopac.com/sinopacBT/webevents/2203healthcarepl/index.html ；私房錢 https://bank.sinopac.com/sinopacBT/webevents/22revolvingloan/index.html ；商品說明書 2026.03 版 https://apply.sinopac.com/applyweb/PersonalLoans/loan-terms/LNC382.pdf
- [S22] 將來銀行（Nextbank）信貸文章（有擔保貸款不計入）https://www.nextbank.com.tw/blog/termloans
- [S23] 第一銀行：iLEO https://www.firstbank.com.tw/sites/fcb/touch/1565687620657 ；公教專屬 https://www.firstbank.com.tw/sites/fcb/touch/1565690547155 ；樂活理財信貸 https://www.firstbank.com.tw/sites/fcb/touch/1565687620098 ；第 e 數速貸 https://firstloan.firstbank.com.tw/LoanPlatform/fcb-credit.action
- [S24] 合作金庫：薪轉戶 https://www.tcb-bank.com.tw/personal-banking/loan/credit-loan/salary-loan ；優職優利 https://www.tcb-bank.com.tw/personal-banking/loan/credit-loan/elite ；軍公教 https://www.tcb-bank.com.tw/personal-banking/loan/others/event/loan-event-2 ；國軍 https://www.tcb-bank.com.tw/personal-banking/loan/credit-loan/policy-loan-overview ；特約商店 https://www.tcb-bank.com.tw/personal-banking/loan/credit-loan/shop-owner ；速速貸 https://www.tcb-bank.com.tw/personal-banking/loan/credit-loan/event/fast
- [S25] 土地銀行：一般信用貸款 https://oi.landbank.com.tw/product/6 ；社會菁英 https://oi.landbank.com.tw/product/2 ；優選菁英 https://oi.landbank.com.tw/product/64 ；薪褔貸 https://oi.landbank.com.tw/product/3 ；公教員工低利 https://oi.landbank.com.tw/product/5
- [S25b] 兆豐：專屬方案 https://www.megabank.com.tw/personal/loan/credit-loan/personal-project-loan ；公教好享貸 https://marketing.megabank.com.tw/public148 ；生活好享貸 https://marketing.megabank.com.tw/megalifeloanv2-sf01 ；線上貸款 https://onlineloan.megabank.com.tw/
- [S26] 星展：個人信貸 https://www.dbs.com.tw/personal-zh/loans/personal-loans/default.page ；卡友／十年期 https://www.dbs.com.tw/personal-zh/dbs-forms/ploandt.page ；https://www.dbs.com.tw/personal-zh/ploan/10yearloan/index.html
- [S27] 臺灣銀行消費者貸款適用利率一覽表（PDF，115-09-21 起適用）https://www.bot.com.tw/Images/File/GetFileId/bbd3341a-00fb-411f-815b-9d3259005e06 ；https://www.bot.com.tw/Images/File/GetFileId/bc518e56-3341-4de4-ba88-65b0d74df77c ；https://www.bot.com.tw/tw/footer/information-disclosure/legal-disclaimers/consumer-loan
- [S28] 滙豐（台灣）：https://www.hsbc.com.tw/en-tw/loans/ ；https://www.hsbc.com.tw/loans/products/pil-news/ ；卓越理財 https://www.hsbc.com.tw/loans/products/premier/ ；費率表 https://www.hsbc.com.tw/content/dam/hsbc/tw/docs/help/tariffs-personal-loan.pdf
- [S29] 王道：https://www.o-bank.com/retail/loan/personal/personalmain ；女性 https://www.o-bank.com/retail/loan/personal/femaleloan ；優質客群 https://www.o-bank.com/retail/loan/personal/elite ；外送員 https://www.o-bank.com/retail/loan/personal/delivery

**新聞、次級來源 `[次級]`**
- [S1] CMoney：DBR 22 倍說明 https://www.cmoney.tw/notes/note-detail.aspx?nid=404522
- [S7] 聯合新聞網／經濟日報：金管會開放財力評估模型、DBR22 不鬆綁（2025-12）https://udn.com/news/story/7239/9205027 ；https://money.udn.com/money/story/5613/9205028 ；PChome／卡優 https://news.pchome.com.tw/finance/cardu/20251218/index-17660040391243541003.html
- [S9] 方格子：雙卡危機與 DBR https://vocus.cc/article/6a6f4906fd89780001a66a17
- [S10] Roo.Cash：DBR22 https://roo.cash/blog/dbr22/
- [S11] Money101：信貸額度與 DBR22 https://www.money101.com.tw/blog/%E4%BF%A1%E8%B2%B8%E9%A1%8D%E5%BA%A6%E6%9C%89%E5%A4%9A%E5%B0%91-%E6%8F%AD%E9%9C%B2%E9%8A%80%E8%A1%8C%E4%B8%8D%E6%9C%83%E8%AA%AA%E7%9A%84%E9%97%9C%E9%8D%B5%E6%95%B8%E5%AD%97
- [S12] 6laws.net 現金卡注意事項轉載 https://6laws.net/6law/law3/金融機構辦理現金卡業務應注意事項.htm ；UpToGo https://uptogo.com.tw/財經/貸款/dbr22倍/
- [S15b] Roo.Cash 台新信貸 https://roo.cash/blog/loan-bank/taishin-loan
- [S27b] 貸樂融：2026 公教人員信貸整理 https://dollar-loan.com/civil-servant-loan-comparison-2026/
- [S30] 聯合新聞網：防堵四貸同堂新制上路 https://udn.com/news/story/12806/9851083
- [S31] 風傳媒：10/31 起跨業聯徵 https://www.storm.mg/lifestyle/11177171 ；TVBS https://news.tvbs.com.tw/money/4043548
- [S32] 工商時報：四貸同堂 https://www.ctee.com.tw/news/20261004700010-431003 ；經濟日報 https://money.udn.com/money/story/5613/9583899 ；鉅亨網 https://news.cnyes.com/news/id/6508373
- [S33] AlphaLoan：DBR22 https://www.alphaloan.co/blog/542/dbr22/
- [S34] houseloan.tw：DBR22 https://houseloan.tw/dbr22/
- [S35] 其他貸款網站彙整：https://vocus.cc/article/5f7ebbd5fd897800016c6e99 ；https://goodtoloan.com/all/loan-monthly-salary/ ；https://www.alphaloan.co/blog/536/loan-limit/
- [S36] 經濟日報：信貸族創高 金額突破 1.5 兆 https://money.udn.com/money/story/5613/9398376
- [S37] LINE Bank：DBR22、月負債收支比及總資產負債比 https://corp.linebank.com.tw/blog/b3f526ec-ac10-4ebc-a645-aed7e8c75051
