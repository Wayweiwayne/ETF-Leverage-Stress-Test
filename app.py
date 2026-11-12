import streamlit as st

from version import APP_VERSION

st.set_page_config(page_title=f"ETF 壓力測試系統 {APP_VERSION}", layout="wide")

pg = st.navigation([
    st.Page("main_page.py", title="壓力測試主頁", default=True),
    st.Page("pages/1_Model_Details.py", title="計算模型詳細說明", icon="🧮"),
])
pg.run()
