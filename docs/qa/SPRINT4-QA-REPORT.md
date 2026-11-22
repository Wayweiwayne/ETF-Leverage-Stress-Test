# 衝刺 4 QA 報告：第 39 項「英文介面」

日期：2026-11-19　驗收對象：RD 的 `i18n.py`、`i18n_en.py`、`details_en.py`、`main_page.py`、`app.py`、`report.py`、`engine.py`、`market_data.py`、`ui_state.py`、`safety_limit.py`、`credit_limit.py`、`pages/1_Model_Details.py`、`build_standalone.py`
規格：SPEC-v40 第 7 節與 D8、D10、D16、D18；DESIGN-v40 第 4 節（E-01～E-23、術語表 4.3）；TEST-PLAN-v40 TC-39-01～08。

## 結果

- 驗收測試：`test_acceptance_39.py`，63 項，全部通過（約 90 秒）。
- 完整測試：`.venv/bin/python -m unittest` 共 696 項，695 項通過，1 項失敗：`test_standalone.StandaloneBuildTests.test_committed_file_is_up_to_date`。
  - 原因：UI/UX 在 03:19 校對英文文案，改了 `i18n_en.py`、`details_en.py`；`dist/ETF-Leverage-Stress-Test.html` 是 03:07 產生的。
  - 這不是程式缺陷。UI/UX 校稿結束後，RD 執行 `.venv/bin/python build_standalone.py` 即可。見待辦 P-1。
- pyflakes（`*.py pages/*.py`）：無警告。
- 測試的有效性：同一套掃描在中文模式的預設畫面抓到 1,768 處中日韓字元；英文模式收集到約 4,000 段文字（涵蓋 metric、圖表 JSON、報告 HTML、CSV 欄名、下載檔名、頁面標題、導覽、toast），扣掉例外後為 0。
- 驗收結論：**通過**，但單機檔要在 UI/UX 校稿後重新產生（P-1），並要實機確認 TC-39-07、TC-39-08（P-2）。沒有退回 RD 的程式缺陷。

## 涵蓋範圍

| TC | 內容 | 驗證方式 |
|---|---|---|
| 39-01 | `?lang=en` 是英文；沒帶 lang 是中文且網址不帶 lang；`lang=zh` 是中文；無效值（fr、空字串、zh-TW、english、1、`<script>`）退回中文且不留在網址上；切換鈕是側欄第一個元件、在「開始計算」之上；選項「中文／English」、標籤「語言／Language」；頁面標題與導覽名稱；報告 `<html lang>` 為 `en`／`zh-Hant` | AppTest |
| 39-02 | 切換不重算（`run_summary`、`run_trace`、`solve_for`、`sensitivity_grid` 都是 0 次）；不過期、沒有 toast；一組全部離開預設值的設定（含選項型欄位）切換後欄位值、網址（除 lang 外）、指標完全相同；切回中文後 lang 從網址消失；原本過期的仍過期，在英文介面按 Run 只算 1 次；已算出的安全邊界切換後仍在且不重算（D16） | spy 計數 |
| 39-03 | 中日韓字元掃描（含全形標點）：預設、三組多選項情境、算完安全邊界、安全邊界 9 種結論句組合、沒有薪水補貼、安全邊界引擎錯誤、信貸 10 種情境（超過上限、估計模式、債務用完、月付比、不提供月收入、房貸…）、切換貸款種類的 toast、結果過期（含 toast）、安全邊界過期、自動重算開啟、7 種輸入錯誤、引擎錯誤（開辦費大於本金）、替身代號不能用、算完之後輸入錯誤、行情抓不到（有／沒有即時來源）、存檔資料／股票分割／上市太短／沒有共同月份、說明頁（含 latex）、CSV 欄名與儲存格與下載檔名、報告 HTML 原始碼 | AppTest＋Recorder |
| 39-04（D8） | 上述錯誤在英文模式下是完整的英文句子（至少 3 個英文字）；代號錯誤訊息指出是哪一個代號；中文模式的同樣錯誤仍是中文（預設訊息不變）；行情抓不到的錯誤、快取過的資料提醒（SEAM.TW、STALE.TW）在中文模式出現後切到英文，會被重新翻譯 | AppTest |
| 39-05 | 所有含 `$` 的指標值以 `NT$` 開頭；數字（去掉 `NT`）與中文模式逐項相同；整頁、報告、圖表沒有不帶 NT 的 `$金額`；熱圖刻度有 `NT$…M` 短寫 | AppTest |
| 39-06 | 中文模式不受影響 | 既有 `test_app.py` 等全部通過；`test_acceptance_39` 的中文錯誤訊息測試 |
| D18 | 單機檔載入畫面中文＋英文（標題與一整段說明，英文至少 20 字）；dist 的載入畫面與重新建置的一致；`i18n.py` 在 `APP_FILES` 且嵌入單機檔 | 讀取 `build_standalone` |
| 術語（4.3） | 側欄六個段落標題、Run／Auto-recalculate／Reload market data、7 個指標名稱、歷史回測／蒙地卡羅標題、Loan type 等欄位名、兩種貸款種類選項、`Loan amount (in NT$10,000)`、Find safety limit 與安全邊界標題、`dollar-cost averaging (DCA)` 首次寫法（欄位 help 與說明頁）、NHI supplementary premium、說明頁標題 How it works 與返回連結、sentence case；禁用 ruin／bankrupt／TWD；`default` 不當「預設值」；報告與畫面的指標名稱和數字一致 | AppTest |

只逐字比對 DESIGN 4.3 的術語與結論句句型，不逐字比對 RD 新翻的其他句子（UI/UX 還在校對）。

掃描的例外：ETF 中文名稱（離線資料沒有名稱，目前畫面也不顯示名稱，掃描函式預留扣除名單）、使用者輸入、語言切換鈕上的「中文」（D10）。

## 缺陷

沒有程式缺陷。

## 修改過的既有測試

沒有修改任何既有測試。只新增 `test_acceptance_39.py`。

## 測試本身的錯誤（QA 自己修正，不是 RD 的缺陷）

RD 在整合時回報 16 個失敗都在 `test_acceptance_39.py`。逐一查證後確認是測試錯誤，QA 已在 RD 回報之前自行發現並修正；兩邊的判斷一致。

| 編號 | 失敗的原因 | 查證 | 修正 |
|---|---|---|---|
| T-1 | 用網址參數（`a=../etc`、`path=abc`）製造輸入錯誤 | `ui.text` 會擋掉非法值並退回預設，中文模式也不會出現錯誤；`path` 的格式只允許數字、逗號、正負號與小數點 | 改用 `set_value` 在欄位輸入，路徑改成「5, 1.2.3」「, ,」「5, -150」等格式合法但內容有誤的值；代號錯誤要按「開始計算」才會去抓行情（R-51 的路徑格式錯誤則立即顯示）。每個案例同時在中文模式驗證有錯誤，避免空過 |
| T-2 | 找 `Default-risk map` 時只搜尋圖表 JSON | 這個標題是圖外的 `#####` 標題（DESIGN S-30），不在圖表 spec 裡 | 改搜尋畫面文字 |
| T-3 | 禁用寫法 `default is` | 會誤抓正常的 `chance of default is …` | 改成禁用 `default value／setting`、`defaults to`、`the default` |
| T-4 | 術語測試的文字混入圖表 JSON 的 Plotly 版面範本與報告 HTML 原始碼，並用巢狀 `setUp` 快取頁面，導致 DCA 首次寫法的檢查偶爾找不到 | 單獨跑通過，整批跑失敗 | 術語測試改在 `setUpClass` 只跑一次英文頁面，比對時排除圖表範本與原始碼 |
| T-5 | `proxy=../etc` 當成錯誤 | 替身不能用只是警告，不是 `st.error` | 移出輸入錯誤表，另寫 `test_unusable_stand_in_is_a_warning` |

## 待辦與限制

| 編號 | 負責 | 內容 |
|---|---|---|
| P-1 | RD | UI/UX 校稿完成後執行 `.venv/bin/python build_standalone.py`，再跑 `test_standalone`（目前唯一失敗項）。 |
| P-2 | 使用者／實機 | TC-39-07（英文文案是否截斷、跑版，需 UI/UX 校稿＋瀏覽器）與 TC-39-08（單機版切英文、載入畫面）在這個環境無法執行；本次沒有截圖。 |
| P-3 | QA 的限制 | 說明頁用 `AppTest.from_file(app.py)` 加 `switch_page` 進入，並攔截 `st.page_link`；真實瀏覽器裡在兩頁之間來回切換時語言是否保留，AppTest 看不到，要實機確認。 |
| P-4 | QA 的假設 | 測試假設語言切換是側欄第一個 `segmented_control`（值 `zh`／`en`）、網址參數 `lang`、金額 `NT$`（DESIGN E-02、E-03、E-14）。若 UI/UX 校稿後改了這些，測試要跟著改。 |
