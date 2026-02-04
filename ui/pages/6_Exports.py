import streamlit as st

from components import select_document
from ui_utils import fetch_document, fetch_documents, api_url
from ui_theme import apply_base_theme

st.set_page_config(page_title="IPdf — Exports", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Exports</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Download outputs for sharing and review.</div>', unsafe_allow_html=True)

docs = fetch_documents()
doc_id = select_document(docs)

if not doc_id:
    st.info("Select a document to view exports.")
    st.stop()

doc = fetch_document(doc_id)
if not doc:
    st.error("Document not found")
    st.stop()

links = doc.get("links") or {}
for label, key in [
    ("document.json", "document.json"),
    ("document_text.txt", "document_text.txt"),
    ("chunks.json", "chunks.json"),
    ("extractions.json", "extractions.json"),
    ("definitions.csv", "definitions.csv"),
    ("entitlements.csv", "entitlements.csv"),
    ("review_pack.md", "review_pack.md"),
]:
    link = links.get(key)
    if link:
        st.link_button(f"Open {label}", api_url(link))
