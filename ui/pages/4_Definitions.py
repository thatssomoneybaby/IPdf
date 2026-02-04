import streamlit as st

from components import select_document
from ui_utils import fetch_document, fetch_documents, fetch_chunks_json, post_extract_definitions, post_feedback, api_url
from ui_theme import apply_base_theme

st.set_page_config(page_title="IPdf — Definitions", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Definitions</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Extract defined terms with evidence.</div>', unsafe_allow_html=True)

docs = fetch_documents()
doc_id = select_document(docs)

if not doc_id:
    st.info("Select a document to run or view definitions.")
    st.stop()

doc = fetch_document(doc_id)
if not doc:
    st.error("Document not found")
    st.stop()

status = doc.get("definitions_status") or "NOT_RUN"
st.markdown(f"**Extractor status:** {status}")

col1, col2 = st.columns([1, 3])
if col1.button("Run Definitions Extractor", type="primary"):
    ok, msg = post_extract_definitions(doc_id)
    if ok:
        st.success("Definitions extraction queued. Click Refresh to update.")
    else:
        st.error(f"Failed to start extraction: {msg}")
if col2.button("Refresh"):
    st.rerun()

links = doc.get("links") or {}
extractions_link = links.get("extractions.json")
csv_link = links.get("definitions.csv")
review_link = links.get("review_pack.md")

if csv_link:
    st.link_button("Open definitions.csv", api_url(csv_link))
if review_link:
    st.link_button("Open review_pack.md", api_url(review_link))

definitions = []
if extractions_link:
    data = fetch_chunks_json(extractions_link)
    if data:
        definitions = data.get("definitions") or []

if not definitions:
    st.info("No definitions found yet.")
    st.stop()

st.subheader("Definitions Table")
filter_cols = st.columns([2, 2, 1])
term_filter = filter_cols[0].text_input("Filter by term")
conf_min = filter_cols[1].slider("Min confidence", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
max_rows = filter_cols[2].number_input("Max rows", min_value=5, max_value=500, value=200, step=5)

rows = []
for d in definitions:
    ev = (d.get("evidence") or [{}])[0]
    rows.append(
        {
            "Term": d.get("term"),
            "Definition": d.get("definition"),
            "Confidence": d.get("confidence"),
            "Page": ev.get("page_start"),
            "Clause": ev.get("clause_ref") or "—",
        }
    )

filtered = []
for r in rows:
    if term_filter and term_filter.lower() not in (r.get("Term") or "").lower():
        continue
    if r.get("Confidence") is not None and r.get("Confidence") < conf_min:
        continue
    filtered.append(r)

st.dataframe(filtered[: int(max_rows)], use_container_width=True)

st.markdown("**Selected item**")
selected_term = st.selectbox("Select term", options=[r["Term"] for r in filtered[: int(max_rows)]])
selected = next((d for d in definitions if d.get("term") == selected_term), None)
if selected:
    ev = (selected.get("evidence") or [{}])[0]
    st.markdown(f"**{selected.get('term')}**")
    st.write(selected.get("definition"))
    st.caption(
        f"p.{ev.get('page_start')}–{ev.get('page_end')} • clause {ev.get('clause_ref') or '—'}"
    )
    with st.expander("Feedback", expanded=False):
        verdict = st.radio("Is this correct?", options=["Correct", "Incorrect", "Partially correct"], horizontal=True)
        note = st.text_area("Notes (optional)")
        if st.button("Submit feedback"):
            payload = {
                "item_type": "definitions",
                "item_id": selected.get("term"),
                "verdict": verdict.lower().replace(" ", "_"),
                "note": note or None,
                "evidence": {
                    "chunk_id": ev.get("chunk_id"),
                    "page_start": ev.get("page_start"),
                    "page_end": ev.get("page_end"),
                    "clause_ref": ev.get("clause_ref"),
                },
            }
            ok, msg = post_feedback(doc_id, payload)
            if ok:
                st.success("Feedback saved. Thank you.")
            else:
                st.error(f"Feedback failed: {msg}")
