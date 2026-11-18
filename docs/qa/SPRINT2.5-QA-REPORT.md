# 衝刺 2.5 QA 驗收紀錄：故事 46 信貸可貸額度

- 日期：2026-11-18
- 依據：SPEC-v40 第 12.4、12.5 節；DESIGN-v40 第 8 節（L-xx、B-xx）
- 受測對象：工作目錄中 RD 的實作（`credit_limit.py`、`main_page.py`、`ui_state.py`、`report.py`、`safety_limit.py`、說明頁）

## 1. 結果

| 項目 | 結果 |
|---|---|
| `test_acceptance_s46`（新） | 68 個全部通過 |
| `.venv/bin/python -m unittest`（全部） | 542 個全部通過（約 335 秒） |
| `pyflakes *.py pages/*.py` | 沒有警告 |
| 單機檔 `build_standalone.py --check` | 是最新的 |

沒有未解決的缺陷。

## 2. 驗收條件對照

| 12.4 條件 | 測試 |
|---|---|
| 預設值、切換貸款種類 | `DefaultsTests`（本金 100／300、欄位顯示、收入欄位保留、L-16） |
| 公式：五組數字 | `FormulaTests`、`CreditModuleTests` |
| 負債大於上限：為 0、無法再借 | `test_debt_above_limit_blocks_calculation`、L-08、L-09 |
| 平均月收入 0＝V39 | `ZeroIncomeTests` |
| 超過上限以上限計算，畫面與報告都寫明 | `OverLimitTests`（L-01a、L-01b、L-02、L-10、報告列） |
| 用估計金額＝直接設定本金 | `EstimateModeTests` |
| 理財型房貸不顯示、不影響 | `MortgageTests` |
| 月付比、年收入門檻 | `WarningTests`（L-05、L-06、L-07、L-11、L-12） |
| 網址：預設不寫、無效退回、舊連結規則 | `UrlTests` |
| 熱圖超限格為灰色、搜尋上限用可借上限 | `HeatmapTests` |
| 舊連結（有 loan）結果同 V39 | `V39RegressionTests`（7 條，數字取自 V39 程式） |

## 3. 回歸基準更新

預設本金改變是預期的（SPEC 12.4）。更新如下：

- `test_acceptance_helpers.py`：`AppHarness.BASE_QUERY`，各類別可設預設網址參數。
- `test_acceptance_27_ui.py`：`SafetyHarness` 沿用 `loan=500`。
- `test_acceptance_38.py`：V39 舊連結加 `loan=500`；快照與網址多一個 `inc=0`（舊連結規則）。
- `test_acceptance_fix2.py`：`buf` 舊連結加 `loan=500`，網址多 `inc=0`。

## 4. 補充比對

對照 V39 程式（commit 14ad2a1）與現在的實作，在同一份假行情下比對 8 條連結的主要結果：

- 有 `loan` 的 7 條，數字完全相同。
- 只寫 `type=0`（沒有 loan）的不同。本金 500 萬變 300 萬，這是預期的。

## 5. 缺陷清單

無。測試過程中的 3 個失敗都是測試本身的錯（預期值算錯、隱藏欄位、報告時機），已修正，不是產品缺陷。

## 6. 未涵蓋

- 沒有瀏覽器實機截圖（依指示省略）。
- L-15a（安全邊界全部達標的句子）、R-01 快照的「設定已變更」未單獨測。
- 說明頁只檢查關鍵字，沒有逐句比對。
