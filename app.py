import streamlit as st

st.set_page_config(page_title="ETF 壓力測試系統 V33", layout="wide")

pg = st.navigation([
    st.Page("main_page.py", title="壓力測試主頁", default=True),
    st.Page("pages/1_Model_Details.py", title="計算模型詳細說明", icon="🧮"),
])
pg.run()
