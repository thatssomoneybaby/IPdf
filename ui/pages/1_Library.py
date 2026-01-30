import os
from io import BytesIO
from urllib.parse import urljoin

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return urljoin(BACKEND_URL.rstrip("/") + "/", path.lstrip("/"))


st.set_page_config(page_title="IPdf — Library", layout="wide")
st.title("📚 Library")


def status_badge(text: str) -> str:
    """Return a colored label using Streamlit's inline color syntax.

    Maps common document statuses to colors and falls back to gray.
    """
    if text is None:
        label = "?"
    else:
        label = str(text)
    key = label.strip().lower()
    color = "gray"
    if key in {"ready", "processed", "ingested", "ok", "complete", "completed", "done"}:
        color = "green"
    elif key in {"processing", "in_progress", "running", "chunking", "ingesting", "pending"}:
        color = "blue"
    elif key in {"error", "failed", "invalid"}:
        color = "red"
    elif key in {"queued", "waiting"}:
        color = "orange"
    return f":{color}[{label}]"

with st.expander("Upload a document", expanded=False):
    f = st.file_uploader("PDF or DOCX", type=["pdf", "docx"], accept_multiple_files=False)
    if f is not None:
        if st.button("Upload", type="primary"):
            try:
                files = {"file": (f.name, BytesIO(f.getvalue()), f.type or "application/octet-stream")}
                r = requests.post(api_url("/upload"), files=files, timeout=30)
                if r.ok:
                    st.success(f"Uploaded: {r.json().get('doc_id')}")
                else:
                    st.error(f"Upload failed: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Upload error: {e}")

st.subheader("Documents")
placeholder = st.empty()

def fetch_docs():
    try:
        r = requests.get(api_url("/documents"), timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []

docs = fetch_docs()
if not docs:
    st.info("No documents yet. Upload one to get started.")
else:
    for d in docs:
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 2])
            cols[0].markdown(f"**{d.get('filename') or d['doc_id']}**")
            cols[1].write(d.get("doc_id"))
            cols[2].markdown(status_badge(d.get("status", "?")))
            open_detail = cols[3].button("Open", key=f"open-{d['doc_id']}")
            if open_detail:
                st.session_state["current_doc_id"] = d["doc_id"]
                st.switch_page("pages/2_Document_Detail.py")
