# 隨程式部署的行情存檔（選用）

這個資料夾裡的 `<代號>.csv` 是最後備援：即時來源連不上、`.yf_cache/` 也沒有存檔時才會用到。

產生方式：

```bash
python market_data.py 0050.TW 0056.TW 00878.TW 00631L.TW --dir data/snapshots
```

預設不放任何資料。把行情資料提交到公開的 repo 之前，請先確認資料來源的使用條款。
