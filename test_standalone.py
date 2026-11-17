"""Checks on the single-file build (dist/ETF-Leverage-Stress-Test.html).

The browser runtime itself (stlite on Pyodide) cannot run here, so the closest offline stand-in
is used: the files embedded in the page are unpacked into an empty folder and the app is run
from there with yfinance unavailable and the mirror switched off, as it would be in a browser
with no network beyond the page's own files.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

import build_standalone

RUNNER = r'''
import json, sys
sys.modules["yfinance"] = None            # importing it now fails, as in the browser
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=180)
for key, value in json.loads(sys.argv[1]).items():
    at.query_params[key] = value
at.run()
print(json.dumps({
    "exceptions": [str(e.value) for e in at.exception],
    "errors": [e.value for e in at.error],
    "info": [i.value for i in at.info],
    "metrics": {m.label: m.value for m in at.metric},
    "captions": [c.value for c in at.caption],
}, ensure_ascii=False))
'''


def embedded_files(html):
    return json.loads(re.search(r"const files = (\{.*?\});\n", html, re.S).group(1))


class StandaloneBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = build_standalone.build()
        cls.files = embedded_files(cls.html)

    def test_committed_file_is_up_to_date(self):
        with open(build_standalone.OUTPUT, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), self.html, "run: python build_standalone.py")

    def test_every_app_file_and_snapshot_is_embedded_unchanged(self):
        for path in build_standalone.APP_FILES:
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(self.files[path], fh.read(), path)
        shipped = sorted(f for f in os.listdir("data/snapshots") if f.endswith(".csv"))
        self.assertEqual(sorted(p.split("/")[-1] for p in self.files if p.startswith("data/snapshots/")), shipped)

    def test_every_local_module_the_app_imports_is_embedded(self):
        local = {os.path.splitext(f)[0] for f in os.listdir(".") if f.endswith(".py")}
        for path, text in self.files.items():
            if path.endswith(".py"):
                for name in re.findall(r"^(?:from|import) (\w+)", text, re.M):
                    if name in local:
                        self.assertIn(f"{name}.py", self.files, f"{path} imports {name}")

    def test_page_has_one_script_element_and_pinned_runtime(self):
        self.assertEqual(self.html.count("</script>"), 1)
        self.assertEqual(self.html.count(f"@stlite/browser@{build_standalone.STLITE_VERSION}/build/"), 2)
        self.assertNotIn("yfinance", json.dumps(build_standalone.REQUIREMENTS))

    def run_unpacked(self, **query):
        with tempfile.TemporaryDirectory() as folder:
            for path, text in self.files.items():
                os.makedirs(os.path.join(folder, os.path.dirname(path)), exist_ok=True)
                with open(os.path.join(folder, path), "w", encoding="utf-8") as fh:
                    fh.write(text)
            env = {**os.environ, "ETF_SNAPSHOT_MIRROR": "", "PYTHONPATH": ""}
            done = subprocess.run([sys.executable, "-c", RUNNER, json.dumps(query)], cwd=folder, env=env,
                                  capture_output=True, text=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_unpacked_app_runs_without_a_live_source(self):
        out = self.run_unpacked(seed="1")
        self.assertEqual(out["exceptions"], [])
        self.assertEqual(out["errors"], [])
        self.assertTrue(any("這是單機版" in text for text in out["info"]))
        self.assertIn("破產機率（繳不出貸款）", out["metrics"])
        self.assertTrue(any("較舊的存檔" in text for text in out["captions"]))

    def test_unpacked_app_explains_a_ticker_it_does_not_have(self):
        out = self.run_unpacked(a="2330.TW")
        self.assertEqual(out["exceptions"], [])
        self.assertTrue(any("無法即時查詢行情" in text for text in out["errors"]))
        self.assertEqual(out["metrics"], {})


if __name__ == "__main__":
    unittest.main()
