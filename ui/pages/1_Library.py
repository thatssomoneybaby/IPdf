from io import BytesIO
import time

import requests
import streamlit as st

from ui_utils import api_url, fetch_documents
from ui_theme import apply_base_theme, status_pill


st.set_page_config(page_title="IPdf — Library", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Library</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Upload and track contracts through the pipeline.</div>', unsafe_allow_html=True)

top_cols = st.columns([1, 1, 1, 3])
if top_cols[0].button("Refresh"):
    st.rerun()
auto_refresh = top_cols[1].toggle("Auto-refresh", value=False)
refresh_sec = top_cols[2].selectbox("Every", options=[5, 10, 15, 30], index=1)


def status_badge(text: str) -> str:
    return status_pill(text or "unknown")

with st.expander("Upload a document", expanded=False):
    f = st.file_uploader("PDF or DOCX", type=["pdf", "docx"], accept_multiple_files=False)
    if f is not None:
        if st.button("Upload", type="primary"):
            try:
                files = {"file": (f.name, BytesIO(f.getvalue()), f.type or "application/octet-stream")}
                r = requests.post(api_url("/upload"), files=files, timeout=30)
                if r.ok:
                    doc_id = r.json().get("doc_id")
                    if doc_id:
                        st.session_state["current_doc_id"] = doc_id
                        st.switch_page("pages/2_Document_Detail.py")
                    st.success(f"Uploaded: {doc_id}")
                else:
                    st.error(f"Upload failed: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Upload error: {e}")

st.subheader("Documents")
placeholder = st.empty()

docs = fetch_documents()
if not docs:
    st.info("No documents yet. Upload one to get started.")
else:
    for d in docs:
        with st.container(border=True):
            cols = st.columns([4, 2, 2, 2, 2])
            filename = d.get("display_name") or d.get("filename") or d["doc_id"]
            short_id = (d.get("doc_id") or "")[:8]
            cols[0].markdown(f"**{filename}**")
            cols[1].caption(f"id: {short_id}")
            cols[2].markdown(status_badge(d.get("status", "?")), unsafe_allow_html=True)
            cols[3].markdown(f"Pages: {d.get('page_count') or '—'}")
            open_detail = cols[4].button("Open", key=f"open-{d['doc_id']}")
            if open_detail:
                st.session_state["current_doc_id"] = d["doc_id"]
                st.switch_page("pages/2_Document_Detail.py")
            if cols[4].button("Search", key=f"search-{d['doc_id']}"):
                st.session_state["search_doc_ids"] = [d["doc_id"]]
                st.switch_page("pages/3_Search.py")

    if auto_refresh:
        time.sleep(refresh_sec)
        st.rerun()
