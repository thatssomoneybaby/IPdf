import requests
import streamlit as st

from ui_utils import api_url, BACKEND_URL
from ui_theme import apply_base_theme


st.set_page_config(page_title="IPdf", layout="wide")
apply_base_theme()

st.markdown('<div class="app-title">IPdf</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Evidence-first contract analysis for fast internal review.</div>', unsafe_allow_html=True)

st.markdown('<div class="section-title">Getting Started</div>', unsafe_allow_html=True)
st.markdown(
    """
1. Upload a contract in **Library**.
2. Wait for status to reach **READY**.
3. Review sections and evidence in **Document Detail**.
4. Use **Search** to find clauses fast.
    """
)

col1, col2 = st.columns(2)
with col1:
    st.markdown('<div class="section-title">Backend</div>', unsafe_allow_html=True)
    st.code(BACKEND_URL)
    try:
        r = requests.get(api_url("/health"), timeout=3)
        st.success(f"API health: {r.json().get('status', 'unknown')}")
    except Exception as e:
        st.error(f"API not reachable: {e}")

with col2:
    st.markdown('<div class="section-title">Quick Links</div>', unsafe_allow_html=True)
    st.page_link("pages/1_Library.py", label="Open Library", icon="📚")
    st.page_link("pages/3_Search.py", label="Open Search", icon="🔎")
    st.page_link("pages/4_Definitions.py", label="Definitions", icon="📘")
    st.page_link("pages/5_Entitlements.py", label="Entitlements", icon="📑")
    st.page_link("pages/6_Exports.py", label="Exports", icon="📦")

st.divider()
st.write("This is a thin slice to exercise API wiring and page navigation.")
