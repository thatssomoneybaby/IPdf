import streamlit as st


def build_doc_options(docs: list[dict]) -> tuple[dict, dict]:
    options = {}
    doc_map = {}
    for d in docs:
        doc_id = d.get("doc_id")
        if not doc_id:
            continue
        name = d.get("display_name") or d.get("filename") or doc_id
        doc_map[doc_id] = name
        options[f"{name} ({doc_id[:8]})"] = doc_id
    return options, doc_map


def select_document(docs: list[dict], label: str = "Document") -> str | None:
    options, _ = build_doc_options(docs)
    selected = st.selectbox(label, options=[""] + list(options.keys()))
    return options.get(selected)
