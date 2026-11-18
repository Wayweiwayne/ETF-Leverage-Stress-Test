"""Pack the whole app into one HTML file that runs in the browser.

    python build_standalone.py            # writes dist/ETF-Leverage-Stress-Test.html
    python build_standalone.py --check    # fails if that file is out of date

The page uses stlite (Streamlit on Pyodide, Python compiled to WebAssembly). The app's own
files and the shipped market-data snapshots are embedded; Pyodide, Streamlit and the Python
packages are downloaded from public CDNs the first time the page opens, so that needs an internet
connection. There is no live market data in the browser: tickers come from the daily mirror and
the embedded snapshots.
"""
import json
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "dist", "ETF-Leverage-Stress-Test.html")
STLITE_VERSION = "1.12.0"
APP_FILES = ["app.py", "main_page.py", "pages/1_Model_Details.py", "engine.py", "market_data.py",
             "report.py", "credit_limit.py", "safety_limit.py", "ui_state.py", "version.py", "data/mirror_tickers.txt"]
# Pure-Python packages fetched from PyPI; numpy and pandas come with Pyodide itself.
REQUIREMENTS = ["plotly==6.7.0"]

TEMPLATE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>借錢投資 ETF 壓力測試 __VERSION__（單機版）</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.css">
<style>
  #boot { font-family: -apple-system, "Segoe UI", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
          max-width: 640px; margin: 15vh auto; padding: 0 20px; color: #1f2933; line-height: 1.7; }
  #boot h1 { font-size: 22px; } #boot p { color: #52606d; font-size: 15px; }
</style>
</head>
<body>
<div id="boot">
  <h1>借錢投資 ETF 壓力測試 __VERSION__（單機版）</h1>
  <p>正在瀏覽器裡準備 Python 執行環境。第一次打開需要下載約 30 MB，視網路速度大約要半分鐘到幾分鐘；之後瀏覽器會記住，下次會快很多。</p>
  <p>計算全部在你的電腦上進行，不會把任何輸入送到伺服器。</p>
  <noscript><p>這個頁面需要開啟 JavaScript。</p></noscript>
</div>
<div id="root"></div>
<script type="module">
import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.js";
const files = __FILES__;
const boot = document.getElementById("boot");
new MutationObserver((_, observer) => {
  if (document.querySelector("#root [data-testid]")) { boot.remove(); observer.disconnect(); }
}).observe(document.getElementById("root"), { childList: true, subtree: true });
mount({ requirements: __REQUIREMENTS__, entrypoint: "app.py", files, streamlitConfig: __CONFIG__ },
      document.getElementById("root"));
</script>
</body>
</html>
"""


def collect_files():
    """Every file the app needs, as path -> text, in a fixed order."""
    paths = list(APP_FILES)
    snapshots = os.path.join(HERE, "data", "snapshots")
    paths += sorted(f"data/snapshots/{f}" for f in os.listdir(snapshots) if f.endswith(".csv"))
    files = {}
    for path in paths:
        with open(os.path.join(HERE, path), encoding="utf-8") as fh:
            files[path] = fh.read()
    return files


def streamlit_config():
    """The server's .streamlit/config.toml as the "section.option" pairs stlite takes in mount()."""
    with open(os.path.join(HERE, ".streamlit", "config.toml"), "rb") as fh:
        sections = tomllib.load(fh)
    return {f"{section}.{name}": value for section, options in sections.items() for name, value in options.items()}


def _script_json(value):
    """JSON that is safe inside a <script> element."""
    text = json.dumps(value, ensure_ascii=False, indent=None, separators=(",", ":"))
    return text.replace("</", "<\\/")


def build():
    sys.path.insert(0, HERE)
    from version import APP_VERSION
    return (TEMPLATE.replace("__VERSION__", APP_VERSION).replace("__STLITE__", STLITE_VERSION)
            .replace("__REQUIREMENTS__", _script_json(REQUIREMENTS)).replace("__CONFIG__", _script_json(streamlit_config()))
            .replace("__FILES__", _script_json(collect_files())))


def main(argv):
    html = build()
    if "--check" in argv:
        try:
            with open(OUTPUT, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = None
        if current != html:
            print(f"{os.path.relpath(OUTPUT, HERE)} is out of date; run: python build_standalone.py")
            return 1
        print("up to date")
        return 0
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print(f"wrote {os.path.relpath(OUTPUT, HERE)} ({len(html.encode('utf-8')) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
