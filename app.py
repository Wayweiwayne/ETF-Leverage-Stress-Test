import streamlit as st

import i18n
import ui_state as ui
from i18n import t
from version import APP_VERSION

i18n.set_lang(ui.read_lang())  # before anything else is drawn: the page names below are already in this language

st.set_page_config(page_title=t("借錢投資 ETF 壓力測試 {APP_VERSION}", APP_VERSION=APP_VERSION), layout="wide")

pg = st.navigation([
    st.Page("main_page.py", title=t("壓力測試"), default=True),
    st.Page("pages/1_Model_Details.py", title=t("計算方法說明"), icon="🧮"),
])
pg.run()
