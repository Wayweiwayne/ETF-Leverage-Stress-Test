# 測試計畫 v40：安全邊界、白話介面、開始計算按鈕、英文介面

- 文件負責人：QA
- 依據：`docs/specs/SPEC-v40.md`（以下簡稱 SPEC）、`docs/design/DESIGN-v40.md`（UI/UX 產出後補對照）
- 適用版本：V40（四個衝刺）
- 狀態：衝刺 2 版本（第 27 項計算核心與畫面、第 38 項的驗收測試已完成：`test_acceptance_27.py`、`test_acceptance_27_ui.py`、`test_acceptance_38.py`，共用工具在 `test_acceptance_helpers.py`；驗收紀錄見 `docs/qa/SPRINT1-QA-REPORT.md`、`docs/qa/SPRINT2-QA-REPORT.md`）

## 1. 目的與範圍

確認 V40 的四個故事（27 → 38 → 35 → 39）都符合 SPEC 的驗收條件，且不破壞既有功能：既有計算結果、舊分享連結、單機版、可下載報告與 CSV。

不在範圍內：SPEC 第 8 節列的項目；任何計算邏輯的修改（若發現既有計算的缺陷，另開缺陷單，不在本版修）。

## 2. 測試環境與執行方式

| 項目 | 內容 |
|---|---|
| Python | 一律 `.venv/bin/python` |
| 全部測試 | `.venv/bin/python -m unittest`（必須離線；行情一律用合成資料或 mock） |
| 只跑第 27 項驗收 | `.venv/bin/python -m unittest test_acceptance_27 -v` |
| 靜態檢查 | `.venv/bin/python -m pyflakes *.py pages/*.py` 沒有警告 |
| 單機檔 | `.venv/bin/python build_standalone.py --check`（`test_standalone` 也會檢查） |
| 瀏覽器實機 | `.venv/bin/streamlit run app.py --server.headless true --server.port 8602`（QA 專用埠，用完關掉） |
| 暫存檔 | scratchpad：`/tmp/claude-0/-home-user-ETF-Leverage-Stress-Test/d9762379-1ffe-5f59-9687-fb97862f21dd/scratchpad` |

測試資料：

- 計算核心：`test_engine.market(n=226)`（合成月資料，226 個月）與 `test_engine.params()`。為了讓破產率在範圍內有明顯變化，驗收測試另外用「每年再扣 15% 報酬」（`structural_discount_pct=15`）的嚴苛設定。
- App：`test_app.py` 的 `fake_history`（假行情，mock `market_data.load_history`，並把 `MIRROR_URL` 設為空字串）。

## 3. 測試策略

| 層級 | 工具 | 用在哪裡 |
|---|---|---|
| 計算核心驗收（黑箱） | `unittest`，只用 SPEC 4.1 的公開 API 與 `run_summary` | 第 27 項計算核心（`test_acceptance_27.py`） |
| 暴力法對照 | 小範圍內逐一跑 `run_summary`，依 SPEC 定義算出正確答案，再與 `solve_for` 比對 | 第 27 項 |
| 性質測試 | 不依賴單調性的性質（答案達標、往不安全方向的下一個候選值不達標）、目標越寬鬆答案越寬鬆、熱圖單調性 | 第 27 項（SPEC 第 9 節風險） |
| App 端到端 | `streamlit.testing.v1.AppTest` 跑整個 App，假行情；用 `unittest.mock.patch` 計數 `engine.run_summary`／`solve_for`／`sensitivity_grid` | 27 畫面、38、35、39 |
| 文字掃描 | 收集 AppTest 畫面上所有元素的文字＋報告 HTML，掃描禁用詞／中日韓文字 | 38、39 |
| 瀏覽器實機 | 埠 8602，手動操作＋截圖存 scratchpad | 版面、熱圖顏色與標示、互動感受、單機版 |
| 回歸 | 既有全部測試＋本計畫第 9 節新增的回歸案例 | 每個衝刺 |

驗收測試以 SPEC 為準撰寫，不讀 RD 的實作細節。驗收測試失敗時，依第 11 節判斷是 RD 缺陷、SPEC 不清楚、還是測試寫錯。

## 4. 衝刺與測試時程

| 衝刺 | QA 工作 | 產出 |
|---|---|---|
| 1 | 本測試計畫；第 27 項計算核心驗收測試（測試先行）；RD 完成後執行並回報 | `docs/qa/TEST-PLAN-v40.md`、`test_acceptance_27.py`、`docs/qa/` 底下的缺陷報告（若有） |
| 2 | 第 27 項畫面＋第 38 項的 App 驗收測試；依 D1、D2、D5 更新計算核心測試；瀏覽器實機 | `test_acceptance_27_ui.py`、`test_acceptance_38.py`、`docs/qa/SPRINT2-QA-REPORT.md`（含截圖清單） |
| 3 | 第 35 項驗收測試（含計數 mock）；實機 | `test_acceptance_35.py` |
| 4 | 第 39 項驗收測試（中日韓文字掃描）；實機；全版本回歸 | `test_acceptance_39.py`、V40 驗收總結 |

## 5. 第 27 項：安全邊界

### 5.1 計算核心（衝刺 1，SPEC 4.1）——全部自動，`test_acceptance_27.py`

每個 `solve_for` 結果都會經過共同的合約檢查（`ContractChecks.check_contract`）：型別、`field`／`target` 回傳正確、`status` 只有三種、`value` 落在格點或等於 `hi`、`ruin_rate` 等於 `run_summary` 在該值的蒙地卡羅破產率、`evaluations` 不超過上限、不修改 `params` 與行情資料；若實作內部呼叫 `engine.run_summary`，呼叫次數必須等於 `evaluations`。

| 編號 | SPEC 條件 | 測試案例 | 方式 |
|---|---|---|---|
| TC-27-01 | `SolveResult` 欄位與 frozen | `SolveResultShapeTests.test_is_a_frozen_dataclass_with_the_agreed_fields` | 自動 |
| TC-27-02 | principal：最大本金使破產率 ≤ 目標 | `SolvePrincipalTests.test_matches_brute_force_for_several_targets`（5 個目標）、`test_matches_brute_force_on_a_fine_grid`、`test_other_seeds_and_settings`（4 組設定 × 2 個目標） | 自動，暴力法對照 |
| TC-27-03 | 「≤」包含等號 | `test_target_is_inclusive`（目標恰好等於某格點的破產率） | 自動 |
| TC-27-04 | principal：`hi` 達標 → `all_meet`、`value=hi` | `test_whole_range_safe_is_all_meet_at_hi`、`test_hi_off_the_grid_is_also_checked` | 自動 |
| TC-27-05 | principal：`lo` 不達標 → `none_meet`、`value=None`、`ruin_rate` 為 `lo` 的破產率 | `test_whole_range_unsafe_is_none_meet`、`test_single_point_range` | 自動 |
| TC-27-06 | salary_cap：最小自掏上限 | `SolveSalaryCapTests.test_matches_brute_force_for_several_targets`、`test_matches_brute_force_on_a_fine_grid`、`test_app_sized_search` | 自動，暴力法對照 |
| TC-27-07 | salary_cap：`lo` 達標 → `all_meet`、`value=lo`；`lo=0` 合法 | `test_safe_at_lo_is_all_meet_at_lo`、`test_zero_lo_is_allowed_and_can_be_the_answer` | 自動 |
| TC-27-08 | salary_cap：`hi` 不達標 → `none_meet`、`ruin_rate` 為 `hi` 的破產率 | `test_unsafe_at_hi_is_none_meet` | 自動 |
| TC-27-09 | `value` 是 `lo + k*step` 或 `hi`；`hi` 不在格點上也要檢查 | 合約檢查（每個案例）、兩個欄位的 `test_hi_off_the_grid_is_also_checked`、`test_hi_off_the_grid_that_fails_returns_a_grid_point`、`test_range_narrower_than_one_step` | 自動 |
| TC-27-10 | 沿用 `params` 其他設定、不修改 `params` | 合約檢查（每個案例比對呼叫前後）、`SeedAndInputTests.test_other_settings_are_carried_over` | 自動 |
| TC-27-11 | `seed=None` 時固定用 42、結果可重現；有給 seed 時用該 seed | `test_missing_seed_uses_42_and_stays_missing`、`test_given_seed_is_used` | 自動 |
| TC-27-12 | `evaluations ≤ ceil(log2((hi-lo)/step)) + 3` | 合約檢查（每個案例）、`test_app_sized_search_stays_within_the_evaluation_limit`（畫面用的 10 萬～5,000 萬／10 萬）、salary_cap 0～50 萬／1,000 | 自動 |
| TC-27-13 | 共同隨機數 → 單調（性質） | `test_higher_target_never_allows_a_smaller_loan`、`test_higher_target_never_needs_more_salary`、局部邊界性質（合約檢查） | 自動 |
| TC-27-14 | `ValueError`（中文訊息）：field 錯誤、target 不在 (0,1)（含 0 與 1）、`lo > hi`、`step <= 0`、`lo < 0`、principal 的 `lo = 0`、資料 `n < 2`（含 0 與 1） | `SolveValidationTests` 的 7 個測試 | 自動 |
| TC-27-15 | 熱圖形狀、index／columns 依傳入順序、值在 0～1 | `SensitivityGridTests.test_shape_and_order_follow_the_inputs`（故意用未排序的輸入） | 自動 |
| TC-27-16 | 一致性：目前那一格 = `run_summary` 的破產率（seed 42、7、None） | `test_current_cell_equals_run_summary` | 自動 |
| TC-27-17 | 每一格只改本金與自掏上限；`mc_paths` 用參數值（預設 1000） | `test_every_cell_changes_only_principal_and_cap`、`test_default_path_count_is_1000` | 自動 |
| TC-27-18 | 所有格子同一個種子；None 時用 42；不修改 `params` | `test_missing_seed_uses_42_and_is_repeatable`、`test_params_are_not_modified` | 自動 |
| TC-27-19 | 單調性：同列不升；同欄不降（容許 0.01） | `test_monotone_in_salary_cap_and_nearly_monotone_in_principal`（6×6、1000 路徑、含台灣稅費與補充保費門檻） | 自動 |
| TC-27-20 | 效能：6×6、1000 路徑、226 個月資料、84 個月貸款，10 秒內 | `test_six_by_six_with_1000_paths_finishes_within_ten_seconds` | 自動（計時） |

暴力法的「正確答案」完全依 SPEC 定義：principal 是格點（加上 `hi`）中破產率 ≤ 目標的最大值；`hi` 達標為 `all_meet`、`lo` 不達標為 `none_meet`；salary_cap 對稱。細格點的對照案例先確認該範圍的破產率確實單調（測試前提），避免把「二分搜尋在不單調處找到局部邊界」誤判為缺陷；不單調時改以局部邊界性質判斷。

### 5.2 畫面（衝刺 2，SPEC 4.2）

| 編號 | 驗收條件 | 方式 |
|---|---|---|
| TC-27-21 | 「安全邊界」區塊在主要結果之後 | AppTest（元素順序）＋實機 |
| TC-27-22 | 按按鈕才計算：打開頁面、改設定都不呼叫 `solve_for`／`sensitivity_grid`；按一次各呼叫預期次數 | AppTest＋mock 計數 |
| TC-27-23 | 本金搜尋：`lo=10 萬`、`hi=min(目前本金×10, 1 億)`、`step=10 萬`；自掏：`0～50 萬`、`step=1,000` | AppTest＋mock 檢查呼叫參數（含本金 1 萬、500 萬、2,000 萬三種邊界） |
| TC-27-24 | 目標破產率 1%／5%／10%，預設 5%；網址參數 `tgt`（1、5、10）；預設值不寫進網址；無效值（`tgt=7`、`tgt=abc`）退回 5% | AppTest |
| TC-27-25 | 熱圖：本金與自掏各取 0.5、0.75、1、1.25、1.5、2 倍；自掏為 0 時改用 0、5,000、10,000、20,000、30,000、50,000 | AppTest＋mock 檢查 `sensitivity_grid` 參數 |
| TC-27-26 | 熱圖標出目前設定那一格、格內顯示破產率 | 實機（截圖）＋AppTest 檢查圖表資料 |
| TC-27-27 | 白話結論句（例如「以目前其他設定，要讓破產機率在 5% 以下，最多可以借 820 萬（你目前設定 500 萬）。」）；`all_meet`／`none_meet` 各有合理的句子 | AppTest（文字比對）＋實機 |
| TC-27-28 | 算過的結果寫進可下載的報告；沒算過時報告不出現空白區塊 | AppTest（取下載按鈕的 HTML） |
| TC-27-29 | 計算期間顯示進度、不卡住其他互動 | 實機 |
| TC-27-30 | 第 35 項完成後：設定改變 → 已算出的安全邊界標示過期 | 衝刺 3 的 AppTest |

## 6. 第 38 項：白話介面（衝刺 2，SPEC 5）

| 編號 | 驗收條件 | 方式 |
|---|---|---|
| TC-38-01 | 主頁、說明頁、報告中看不到：「宇宙」「Accounting Trace」「Block Bootstrap」「Scenario」「Trace」「Ledger」「Vol Drag」 | 自動：AppTest 收集 title、header、subheader、markdown、caption、metric label、按鈕、展開區標題、表格欄名、圖表標題與圖例、`help` 提示；報告 HTML 去標籤後掃描。說明頁另跑一次 |
| TC-38-02 | 「DCA」只以「定期定額（DCA）」形式出現在第一次提到處或說明裡 | 自動：找出每個「DCA」出現位置，第一次必須是「定期定額（DCA）」，其後不得單獨出現（說明頁除外，依 PO 澄清結果調整） |
| TC-38-03 | 主標題不超過 20 個字，仍含版本號 | 自動（字數計算方式待 PO 澄清，見第 12 節） |
| TC-38-04 | 網址參數不變；舊連結照常運作 | 自動：第 9.1 節的舊連結回歸案例 |
| TC-38-05 | 報告與畫面用同一套名稱 | 自動：依 UI/UX 的用語對照表，畫面上的新名稱在報告中也出現、舊名稱都不出現 |
| TC-38-06 | 不改任何計算 | 自動：第 9.2 節的數值回歸（預設設定的指標值與 V39 完全相同） |
| TC-38-07 | 用語對照表涵蓋：標題、區塊標題、指標、圖表標題與圖例、側欄分段標題、按鈕、說明頁標題 | 對照 DESIGN-v40 逐項人工核對＋實機 |
| TC-38-08 | 版面沒有因文字變長而跑版（手機寬度、窄側欄） | 實機 |

## 7. 第 35 項：開始計算按鈕（衝刺 3，SPEC 6）

用 `patch('engine.run_summary', wraps=engine.run_summary)` 計數。

| 編號 | 驗收條件 | 方式 |
|---|---|---|
| TC-35-01 | 第一次打開自動計算一次（預設與分享連結兩種）| AppTest：計數 = 1 |
| TC-35-02 | 連續改三個會影響計算的設定 → 零次計算；畫面保留上次結果 | AppTest：計數不變、指標值不變 |
| TC-35-03 | 結果最上方標示「設定已變更，結果尚未更新」，旁邊有「開始計算」；側欄有同一顆按鈕 | AppTest＋實機 |
| TC-35-04 | 按一次按鈕 → 剛好一次計算，標示消失，結果更新 | AppTest：計數 +1 |
| TC-35-05 | 改了又改回原值 → 不標示過期（依「比對參數」的設計） | AppTest |
| TC-35-06 | 「自動重算」開關預設關閉；打開後每次調整都重算；網址參數 `auto` | AppTest |
| TC-35-07 | 不影響計算的操作立即生效、不需按鈕：逐月追蹤的進場月份、下載、展開說明 | AppTest：計數不變、畫面更新 |
| TC-35-08 | 輸入錯誤立即顯示（自訂報酬率、浮動利率路徑格式錯誤） | AppTest |
| TC-35-09 | 網址列一律反映目前輸入（即使還沒按計算）；重新整理以目前輸入自動算一次 | AppTest（`query_params`）＋實機重新整理 |
| TC-35-10 | 安全邊界在設定改變後標示過期；按鈕行為一致 | AppTest |
| TC-35-11 | 側欄依勾選出現的欄位（寬限期、失業、升息…）照常運作（SPEC 9：不用 `st.form`） | AppTest＋實機 |
| TC-35-12 | 報告與 CSV 下載內容對應「最後一次計算」的設定，而非尚未計算的新設定 | AppTest（報告中的設定與分享連結） |

## 8. 第 39 項：英文介面（衝刺 4，SPEC 7）

| 編號 | 驗收條件 | 方式 |
|---|---|---|
| TC-39-01 | 側欄最上方有語言切換（中文／English）；網址參數 `lang`（`en`；預設中文、預設不寫進網址）；無效值退回中文 | AppTest |
| TC-39-02 | 切換語言不改變任何設定與結果 | AppTest：切換前後的 `query_params`（除 `lang`）與指標數值相同；第 35 項完成後也不應標示過期（待 PO 確認） |
| TC-39-03 | 英文模式下主頁、說明頁、報告、圖表、表格、提示與錯誤訊息沒有中日韓文字（扣掉 ETF 中文名稱與使用者輸入） | 自動：收集所有元素文字（含 `help`、圖表 JSON 的標題／軸／圖例／hover、表格欄名與內容、CSV 欄名）＋報告 HTML，掃描 `[぀-ヿ㐀-鿿가-힯]` |
| TC-39-04 | `market_data.py`、`engine.py` 的錯誤訊息在英文模式下是英文 | 自動：觸發代表性錯誤（無效代號、資料不足、自訂報酬率錯誤、浮動利率錯誤、失業設定錯誤、安全邊界參數錯誤） |
| TC-39-05 | 金額格式用 `NT$` | 自動：英文模式下的金額指標以 `NT$` 開頭 |
| TC-39-06 | 中文模式完全不受影響 | 自動：既有 `test_app.py` 全部通過 |
| TC-39-07 | 英文文案可讀、不截斷、不跑版 | 實機＋UI/UX 校稿 |
| TC-39-08 | 單機版可切英文 | 實機（單機 HTML） |

## 9. 回歸風險與守護方式

| 風險 | 可能影響的故事 | 守護方式 |
|---|---|---|
| 舊分享連結失效（參數改名、值的格式改變、預設值改變） | 38、35、39 | 9.1 舊連結回歸；`test_settings_are_restored_from_a_link`、`test_bad_link_values_fall_back_to_safe_ones`、`test_links_made_before_the_second_asset_was_a_source_still_mean_the_same` 必須照常通過 |
| 計算結果被改動（第 27 項只新增、第 38 項不改計算） | 27、38 | 9.2 數值回歸；`test_engine.py` 全部通過；`solve_for` 不得修改 `params` |
| 單機版失效（新模組沒加進 `APP_FILES`、`dist/` 沒重新產生、Pyodide 不支援的寫法、效能在瀏覽器裡慢很多） | 27、35、39 | `test_standalone`（檔案最新、每個 import 的本地模組都有嵌入、離線可跑）；新模組（例如 `i18n.py`）要在 `APP_FILES`；實機用單機 HTML 跑一次安全邊界並記錄耗時 |
| 報告缺漏或與畫面不一致 | 27、38、39 | `test_report.py`、`test_report_gathers_what_the_page_shows`；新增：安全邊界結果出現在報告、報告用語與畫面一致、英文報告無中文 |
| Streamlit 重跑機制：按鈕狀態遺失、session_state 汙染、換頁後結果消失 | 35、27 | AppTest 模擬多次互動；實機在主頁與說明頁之間來回切換 |
| 亂數行為改變（「固定亂數」預設勾選；同設定同結果） | 27、35 | `test_same_settings_give_the_same_monte_carlo_by_default`；安全邊界用 seed 42 不可影響主結果的亂數 |
| 效能退步（安全邊界太慢、按鈕重算時跑兩次） | 27、35 | TC-27-20；TC-35-04 計數剛好 1 |
| CSV 下載欄名改變 | 38、39 | 若 CSV 欄名要翻譯或改白話，需 PO 決定是否算「看得到的文字」；先記錄目前欄名作為基準 |
| pyflakes 警告、未使用的 import | 全部 | DoD 第 2 條，每個衝刺執行 |

### 9.1 舊分享連結回歸案例

以 V39 的網址參數組成固定的連結清單（至少包含 `loan`、`type`、`rate`、`years`、`grace`、`grace_y`、`salary`、`a`、`proxy`、`b`、`reinv`、`ratio_b`、`p1`～`p5`、`jl*`、`scen`、`path`、`swan*`、`div`、`dfreq`、`paths`、`seed`、`stax`、`nhi`、`itax`、`lfee`），每個連結在 V40 打開後：

1. 不出現例外；
2. 各輸入元件的值與 V39 相同；
3. 指標數值與 V39 相同（固定亂數下）；
4. 網址列保留原本的參數，不多出預設值（新參數 `tgt`、`auto`、`lang` 為預設值時不寫進網址）。

### 9.2 數值回歸基準

在衝刺 1 結束時（V39 程式碼）記錄預設設定與 3 組代表性連結的主要指標（初期每月應繳、歷史與蒙地卡羅破產率、期滿中位數），之後每個衝刺比對必須完全相同。`test_defaults_render_results` 的 `$67,199` 是其中之一。

## 10. 瀏覽器實機檢查清單（埠 8602）

每次檢查記錄：日期、衝刺、commit 或工作目錄狀態、瀏覽器、視窗寬度；截圖存 scratchpad。

- [ ] 預設設定打開，第一次自動有結果（衝刺 3 後）
- [ ] 安全邊界：按鈕、進度、結論句、熱圖顏色與目前格標示、格內數字可讀（桌機與手機寬度）
- [ ] 目標破產率切換 1%／5%／10%，網址列的 `tgt` 跟著改
- [ ] 安全邊界結果寫進下載的報告，報告在瀏覽器中正常顯示
- [ ] 白話名稱：主頁、側欄、說明頁、圖表圖例、報告逐一看過
- [ ] 改設定後「設定已變更，結果尚未更新」出現在結果最上方、側欄按鈕可用、按下後消失
- [ ] 自動重算開關打開時恢復舊行為
- [ ] 重新整理頁面、複製網址到新分頁，結果相同
- [ ] English：切換後所有文字為英文、金額 `NT$`、不跑版；切回中文設定不變
- [ ] 單機版 HTML（`dist/ETF-Leverage-Stress-Test.html`）打開，安全邊界可算完並記錄耗時
- [ ] 用完關掉 streamlit 程序

## 11. 缺陷回報格式

缺陷報告寫在 `docs/qa/`（每個衝刺一個檔案，例如 `docs/qa/DEFECTS-sprint1.md`），一筆一節：

```
### DEF-<衝刺>-<序號>：<一句話描述>

- 嚴重度：阻斷／嚴重／一般／輕微
- 故事／驗收條件：例如 27／TC-27-12（SPEC 4.1「evaluations 不可超過…」）
- 判斷：RD 缺陷／SPEC 不清楚（需 PO 澄清）／測試寫錯（QA 自行修正）
- 環境：工作目錄狀態（git status 摘要）、Python 版本、作業系統
- 重現步驟：
  1. …
  2. …（可直接執行的指令或最小程式碼）
- 預期結果：…（引用 SPEC 原文）
- 實際結果：…（貼上錯誤訊息或數值）
- 附件：測試名稱、截圖路徑
- 狀態：新開／RD 處理中／待驗證／已關閉
```

嚴重度定義：

| 嚴重度 | 定義 |
|---|---|
| 阻斷 | App 打不開、計算當掉、舊連結整批失效、單機版不能用 |
| 嚴重 | 驗收條件不符、答案錯誤（例如找到的本金不是最大的）、資料遺失 |
| 一般 | 部分情況不符（邊界值、少數訊息）、效能未達標 |
| 輕微 | 文字、版面、不影響判斷的小問題 |

判斷原則：先用 QA 自己的參考做法（依 SPEC 寫的獨立實作或暴力法）確認測試本身正確；測試正確且實作不符 → RD 缺陷；SPEC 兩種讀法都合理 → SPEC 不清楚，先依較嚴格的讀法寫測試並列入待澄清；測試的前提或計算有誤 → 測試寫錯，QA 修正並註記。

## 12. 進入與完成條件

- 進入：SPEC 已定稿；RD 回報該衝刺實作完成。
- 完成（每個衝刺）：該衝刺的驗收測試全部通過；`.venv/bin/python -m unittest` 全部通過；pyflakes 沒有警告；單機檔已重新產生；實機檢查清單中該衝刺相關項目已勾選；未關閉的缺陷都已由 PM 決定處理方式。

## 13. 需要 PO 澄清的地方（衝刺 1 盤點）

見 `docs/qa/SPRINT1-QA-REPORT.md` 第 4 節與衝刺 1 的 QA 回報；結論確定後更新本節與對應的測試。其他故事的待澄清事項：

- 38：「畫面上看得到的文字」是否包含 `help` 提示、CSV 欄名（目前有「DCA期滿淨值」）、下載檔名（`trace_進場…csv`）；英文模式（39）下 Scenario、Trace 這類英文詞是否仍禁用。
- 38：主標題「不超過 20 個字」的計算方式（版本號「V40」、空白、標點、括號算不算字）。
- 35：只影響安全邊界的設定（`tgt`）與切換語言（`lang`），是否要讓主結果標示過期；「自動重算」打開時，安全邊界是否也自動算。
- 39：單機版開機畫面（Python 環境載入前顯示的中文說明）在英文模式下是否列為例外。
