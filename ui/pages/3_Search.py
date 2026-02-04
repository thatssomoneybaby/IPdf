import requests
import streamlit as st

from components import build_doc_options
from ui_utils import api_url, fetch_documents
from ui_theme import apply_base_theme


st.set_page_config(page_title="IPdf — Search", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Search</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Find clauses with evidence in seconds.</div>', unsafe_allow_html=True)

if "query" not in st.session_state:
    st.session_state["query"] = st.session_state.get("last_query", "audit")

preset_cols = st.columns(5)
if preset_cols[0].button("Audit"):
    st.session_state["query"] = "audit"
    st.rerun()
if preset_cols[1].button("Definitions"):
    st.session_state["query"] = "definitions"
    st.rerun()
if preset_cols[2].button("License grant"):
    st.session_state["query"] = "license grant"
    st.rerun()
if preset_cols[3].button("Termination"):
    st.session_state["query"] = "termination"
    st.rerun()
if preset_cols[4].button("Fees"):
    st.session_state["query"] = "fees"
    st.rerun()

q = st.text_input("Query", key="query")
mode = st.selectbox("Mode", options=["hybrid", "semantic", "keyword"], index=0)
top_k = st.slider("Top K", min_value=5, max_value=50, value=10, step=5)

with st.sidebar:
    st.header("Filters")
    docs = fetch_documents()
    doc_options, doc_map = build_doc_options(docs)
    default_doc_ids = st.session_state.get("search_doc_ids", [])
    default_labels = [label for label, did in doc_options.items() if did in default_doc_ids]
    selected_labels = st.multiselect("Documents", options=list(doc_options.keys()), default=default_labels)
    doc_ids = [doc_options[lbl] for lbl in selected_labels]
    section_contains = st.text_input("Section contains", placeholder="e.g., Definitions, Schedule A")
    type_filter = st.selectbox("Type", options=["", "definition", "clause", "table", "heading", "paragraph"], index=0)
    page_start = st.number_input("Page start", min_value=0, value=0)
    page_end = st.number_input("Page end", min_value=0, value=0)

if st.button("Search", type="primary"):
    st.session_state["last_query"] = q
    payload = {
        "query": q,
        "mode": mode,
        "top_k": top_k,
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
            hits = r.json() or []
            st.session_state["search_results"] = hits
            if hits:
                st.session_state["selected_result"] = 0
    except Exception as e:
        st.error(f"Search error: {e}")

results = st.session_state.get("search_results", [])
if results:
    st.subheader("Results")
    left, right = st.columns([2, 1])
    with left:
        for i, h in enumerate(results):
            ev = h.get("evidence", {})
            filename = doc_map.get(ev.get("doc_id"), ev.get("doc_id"))
            with st.container(border=True):
                st.write(h.get("snippet", ""))
                st.caption(
                        f"{filename} • {ev.get('section_path')} • ref {ev.get('clause_ref')} • p.{ev.get('page_start')}–{ev.get('page_end')} • score={h.get('score')}"
                )
                if st.button("View", key=f"view-{i}"):
                    st.session_state["selected_result"] = i

    with right:
        idx = st.session_state.get("selected_result", 0)
        idx = min(idx, len(results) - 1)
        sel = results[idx]
        ev = sel.get("evidence", {})
        st.markdown("**Evidence**")
        st.caption(f"doc_id: {ev.get('doc_id')}")
        st.caption(f"section: {ev.get('section_path')}")
        st.caption(f"clause: {ev.get('clause_ref') or '—'}")
        st.caption(f"pages: {ev.get('page_start')}–{ev.get('page_end')}")

        citation = (
            f"{sel.get('snippet','')}\n\n"
            f"[citation] doc_id={ev.get('doc_id')} | section={ev.get('section_path')} | clause={ev.get('clause_ref')} | p.{ev.get('page_start')}-{ev.get('page_end')}"
        )
        st.text_area("Copy-ready citation", value=citation, height=200)

        if ev.get("doc_id") and st.button("Open Document Detail"):
            st.session_state["current_doc_id"] = ev.get("doc_id")
            st.switch_page("pages/2_Document_Detail.py")
