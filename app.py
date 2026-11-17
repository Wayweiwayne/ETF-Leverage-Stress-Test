import streamlit as st

from version import APP_VERSION

st.set_page_config(page_title=f"借錢投資 ETF 壓力測試 {APP_VERSION}", layout="wide")

pg = st.navigation([
    st.Page("main_page.py", title="壓力測試", default=True),
    st.Page("pages/1_Model_Details.py", title="計算方法說明", icon="🧮"),
])
pg.run()
