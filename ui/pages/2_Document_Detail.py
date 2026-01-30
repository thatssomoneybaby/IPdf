import os
from urllib.parse import urljoin

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return urljoin(BACKEND_URL.rstrip("/") + "/", path.lstrip("/"))


st.set_page_config(page_title="IPdf — Document", layout="wide")
st.title("📄 Document Detail")


def status_badge(text: str) -> str:
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

doc_id = st.session_state.get("current_doc_id") or st.query_params.get("doc_id", [None])[0]
if not doc_id:
    st.warning("No document selected. Go to Library.")
    st.page_link("pages/1_Library.py", label="Open Library", icon="📚")
    st.stop()

st.caption(f"doc_id: {doc_id}")

def get_doc(doc_id: str):
    r = requests.get(api_url(f"/documents/{doc_id}"), timeout=10)
    if not r.ok:
        st.error("Document not found")
        st.stop()
    return r.json()

doc = get_doc(doc_id)

cols = st.columns([2, 1, 1, 2])
cols[0].markdown(f"**Filename:** {doc.get('filename')}")
cols[1].markdown(status_badge(doc.get("status", "?")))
cols[2].markdown(f"Has chunks: {'✅' if doc.get('has_chunks') else '❌'}")
if cols[3].button("Open Search with this doc", type="primary"):
    st.session_state["search_doc_ids"] = [doc_id]
    st.switch_page("pages/3_Search.py")

st.divider()

st.subheader("Ingestion")
icols = st.columns([2, 1, 3])
icols[0].markdown(f"Ingested: {doc.get('ingested_at') or '—'}")
icols[1].markdown(f"Pages: {doc.get('page_count') if doc.get('page_count') is not None else '—'}")

links = (doc.get("links") or {})
text_link = links.get("document_text.txt")
json_link = links.get("document.json")

btn_cols = icols[2].columns(2)
if text_link:
    btn_cols[0].link_button("Open document_text.txt", api_url(text_link))
if json_link:
    btn_cols[1].link_button("Open document.json", api_url(json_link))

errors = doc.get("errors") or []
if errors:
    st.error("\n".join(errors))

st.subheader("Chunks")
chunks = []
try:
    r = requests.get(api_url(f"/documents/{doc_id}/chunks"), timeout=10)
    if r.ok:
        chunks = r.json()
except Exception:
    pass

if not chunks:
    st.info("No chunks yet. Chunking not implemented in MVP-0.")
else:
    for ch in chunks:
        with st.container(border=True):
            st.markdown(f"**{ch.get('type','chunk')}** — {ch.get('section_path','?')} — p.{ch.get('page_start')}–{ch.get('page_end')}")
            st.write(ch.get("text_preview", ""))
