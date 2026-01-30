import os
from urllib.parse import urljoin

import streamlit as st
import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return urljoin(BACKEND_URL.rstrip("/") + "/", path.lstrip("/"))


st.set_page_config(page_title="IPdf", layout="wide")

st.title("IPdf — Evidence-first contract analysis")
st.caption("MVP UI — Library / Doc detail / Search wiring")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Backend")
    st.code(BACKEND_URL)
    try:
        r = requests.get(api_url("/health"), timeout=3)
        st.success(f"API health: {r.json().get('status', 'unknown')}")
    except Exception as e:
        st.error(f"API not reachable: {e}")

with col2:
    st.subheader("Quick links")
    st.page_link("pages/1_Library.py", label="Open Library", icon="📚")
    st.page_link("pages/3_Search.py", label="Open Search", icon="🔎")

st.divider()
st.write("This is a thin slice to exercise API wiring and page navigation.")

