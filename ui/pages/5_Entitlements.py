import streamlit as st

from components import select_document
from ui_utils import fetch_document, fetch_documents, fetch_chunks_json, post_extract_entitlements, post_feedback, api_url
from ui_theme import apply_base_theme

st.set_page_config(page_title="IPdf — Entitlements", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Entitlements</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Find licensed products, metrics, and schedules.</div>', unsafe_allow_html=True)

docs = fetch_documents()
doc_id = select_document(docs)

if not doc_id:
    st.info("Select a document to run or view entitlements.")
    st.stop()

doc = fetch_document(doc_id)
if not doc:
    st.error("Document not found")
    st.stop()

status = doc.get("entitlements_status") or "NOT_RUN"
st.markdown(f"**Extractor status:** {status}")

col1, col2 = st.columns([1, 3])
if col1.button("Run Entitlements Extractor", type="primary"):
    ok, msg = post_extract_entitlements(doc_id)
    if ok:
        st.success("Entitlements extraction queued. Click Refresh to update.")
    else:
        st.error(f"Failed to start extraction: {msg}")
if col2.button("Refresh"):
    st.rerun()

links = doc.get("links") or {}
extractions_link = links.get("extractions.json")
csv_link = links.get("entitlements.csv")
review_link = links.get("review_pack.md")

if csv_link:
    st.link_button("Open entitlements.csv", api_url(csv_link))
if review_link:
    st.link_button("Open review_pack.md", api_url(review_link))

entitlements = {}
if extractions_link:
    data = fetch_chunks_json(extractions_link)
    if data:
        entitlements = data.get("entitlements") or {}

if not entitlements:
    st.info("No entitlements found yet.")
    st.stop()

status = entitlements.get("status")
if status and status != "OK":
    st.warning(f"Status: {status}")

st.subheader("Tables")
for t in entitlements.get("tables") or []:
    st.markdown(f"**{t.get('title') or 'Table'}**")
    rows = t.get("rows") or []
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No structured rows detected for this table.")

st.subheader("Normalized Products")
products = entitlements.get("products") or []
if products:
    display = []
    for p in products:
        display.append(
            {
                "Product": p.get("name"),
                "Metric": p.get("metric"),
                "Quantity": p.get("quantity"),
                "Term": p.get("term"),
                "Restrictions": "; ".join(p.get("restrictions") or []),
            }
        )
    st.dataframe(display, use_container_width=True)
    st.markdown("**Selected product**")
    product_options = [p.get("name") or f"Product {idx+1}" for idx, p in enumerate(products)]
    selected_name = st.selectbox("Select product", options=product_options)
    selected_idx = product_options.index(selected_name)
    selected = products[selected_idx]
    ev = (selected.get("evidence") or [{}])[0]
    st.caption(f"p.{ev.get('page_start')}–{ev.get('page_end')}")
    with st.expander("Feedback", expanded=False):
        verdict = st.radio("Is this correct?", options=["Correct", "Incorrect", "Partially correct"], horizontal=True)
        note = st.text_area("Notes (optional)", key="ent-note")
        if st.button("Submit feedback"):
            payload = {
                "item_type": "entitlements",
                "item_id": selected.get("name"),
                "verdict": verdict.lower().replace(" ", "_"),
                "note": note or None,
                "evidence": {
                    "chunk_id": ev.get("chunk_id"),
                    "page_start": ev.get("page_start"),
                    "page_end": ev.get("page_end"),
                },
            }
            ok, msg = post_feedback(doc_id, payload)
            if ok:
                st.success("Feedback saved. Thank you.")
            else:
                st.error(f"Feedback failed: {msg}")
else:
    st.info("No normalized products extracted.")
