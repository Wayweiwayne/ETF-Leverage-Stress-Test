# 衝刺 6 QA 報告（進行中：6-2 待驗）

## 6-3 第 44 項
- 新增 `test_ui_state.py`（56 個測試，1 個 expectedFailure 對應缺陷 D1）。涵蓋預設值不進網址、無效值退回預設、數值夾範圍與步進、
  choice（位置／by_value／universe／`_c_<key>` 語言切換／重複譯文）、pin 與 migrate、checkbox/toggle、text、language_switch、begin/end/forget。
- `.github/workflows/tests.yml`：新增 `pip install coverage` 與 `coverage run --branch ... -m unittest -v`、`coverage report -m`，不設門檻。
  沒有 requirements-dev.txt，所以沒有動 requirements.txt。
- 覆蓋率（V40 乾淨檢出，702 個測試，--branch）：ui_state.py 92%、全專案 96%（2912 行／782 分支）。
- 補測試後：ui_state.py 單獨跑 test_ui_state 即 98%（未涵蓋 2 行）；與全套合併的全專案數字待 RD 6-2 穩定後再跑（見下）。
- 注意：加上 coverage 後完整測試單版本約 9–14 分鐘，CI 三個版本都會變慢。

## 6-1 第二標的配息：通過
`test_acceptance_s6.py`（15 個測試）：
- 不配息／欄位缺／全 NaN：歷史回測、蒙地卡羅、追蹤表、股息模型、壓力情境與 V40 引擎的數字逐位相同（GOLDEN 取自 V40）。
- 配息有效：歷史與蒙地卡羅（同種子、同路徑）最終值皆上升；平價市場用獨立手算（含稅、ratio 0/0.5/1）吻合；稅額包含第二標的；定期定額對照組同樣計入。
- PM 裁定（無真實紀錄的月份一律 0：上市前、假想未來、股息模型）已用測試固定；管線 monthly_data→align_months→引擎也通。
- 第二標的歸零後不再買它、上市前 NaN 皆無 NaN 結果。

## 6-2 官方配息：待驗
- RD 已加入 `parse_twse_events`、`fetch_twse_events`、`dividend_events`、`attach_official_dividends`、`refresh_dividend_events` 等；PM 指示雲端連不上證交所，改到 GitHub Actions 探測。
- 尚未寫驗收測試（優先序、退回來源與中英提示、假 TWT49U、分割換算、備份相容）；待 RD 介面穩定後補。

## 完整測試
- 我跑到時 RD 仍在改 6-2：779 個測試中 149 失敗，皆來自進行中狀態（例如 `test_standalone` 的 dist 與 build_standalone.py 不同步）。
  這不是最終結果，待 RD 完成與重建 dist 後重跑。pyflakes 乾淨。

## 缺陷
- D1（ui_state.py，退回 RD）：網址 `?<int slider>=inf`、`-inf`、`1e999` 使頁面崩潰（`_seed` 的 `except` 漏掉 OverflowError）。
  修法：`_seed` 同時攔截 OverflowError。修好後移除 `test_ui_state.py` 內的 `@unittest.expectedFailure`。
- D2（流程）：dist/ETF-Leverage-Stress-Test.html 與 6-1 的文字改動不同步，RD 需執行 `python build_standalone.py`。
