import os
from urllib.parse import urljoin

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return urljoin(BACKEND_URL.rstrip("/") + "/", path.lstrip("/"))


st.set_page_config(page_title="IPdf — Search", layout="wide")
st.title("🔎 Search")

q = st.text_input("Query", value=st.session_state.get("last_query", "audit"))
mode = st.selectbox("Mode", options=["hybrid", "semantic", "keyword"], index=0)

with st.sidebar:
    st.header("Filters")
    default_doc_ids = st.session_state.get("search_doc_ids", [])
    doc_ids_raw = st.text_input("doc_ids (comma-separated)", value=",".join(default_doc_ids))
    doc_ids = [s.strip() for s in doc_ids_raw.split(",") if s.strip()]
    section_contains = st.text_input("Section contains")
    type_filter = st.text_input("Type (e.g., definition)")
    page_start = st.number_input("Page start", min_value=0, value=0)
    page_end = st.number_input("Page end", min_value=0, value=0)

if st.button("Search", type="primary"):
    st.session_state["last_query"] = q
    payload = {
        "query": q,
        "mode": mode,
        "filters": {
            "doc_ids": doc_ids or None,
            "section_contains": section_contains or None,
            "type": type_filter or None,
            "page_start": int(page_start) or None,
            "page_end": int(page_end) or None,
        },
    }
    try:
        r = requests.post(api_url("/search"), json=payload, timeout=20)
        if not r.ok:
            st.error(f"Search failed: {r.status_code} {r.text}")
        else:
            hits = r.json()
            st.subheader("Results")
            if not hits:
                st.info("No results")
            for h in hits:
                with st.container(border=True):
                    st.write(h.get("snippet", ""))
                    ev = h.get("evidence", {})
                    st.caption(
                        f"doc_id={ev.get('doc_id')} • {ev.get('section_path')} • ref {ev.get('clause_ref')} • p.{ev.get('page_start')}–{ev.get('page_end')} • score={h.get('score')}"
                    )
                    st.button("Copy with citation", key=f"copy-{ev.get('doc_id')}-{ev.get('clause_ref')}")
    except Exception as e:
        st.error(f"Search error: {e}")

