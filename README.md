# Market data snapshots

Raw daily history from Yahoo Finance for every ETF listed on the Taiwan Stock Exchange, plus the
tickers in `data/mirror_tickers.txt` on the main branch. `index.csv` lists them with name and listing date.
Replaced every day by the "refresh market data" workflow; the app reads these files instead of
contacting Yahoo Finance on every visit. The data belongs to its original source and is not covered
by the project's licence.
