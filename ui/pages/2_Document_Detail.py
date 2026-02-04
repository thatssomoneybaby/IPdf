import time
import streamlit as st

from ui_utils import api_url, fetch_document, fetch_chunks, fetch_chunks_json, post_process, post_rechunk, post_reindex, post_rename
from ui_theme import apply_base_theme, status_pill


st.set_page_config(page_title="IPdf — Document", layout="wide")
apply_base_theme()
st.markdown('<div class="app-title">Document Detail</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Review sections, evidence, and extracted results.</div>', unsafe_allow_html=True)


def status_badge(text: str) -> str:
    return status_pill(text or "unknown")

doc_id = st.session_state.get("current_doc_id") or st.query_params.get("doc_id", [None])[0]
if not doc_id:
    st.warning("No document selected. Go to Library.")
    st.page_link("pages/1_Library.py", label="Open Library", icon="📚")
    st.stop()

top_cols = st.columns([1, 1, 2])
if top_cols[0].button("Refresh"):
    st.rerun()
auto_refresh = top_cols[1].toggle("Auto-refresh", value=False)
top_cols[2].caption(f"doc_id: {doc_id[:8]}…")

refresh_row = st.columns([1, 3])
refresh_sec = refresh_row[0].selectbox("Every", options=[5, 10, 15, 30], index=1)
refresh_row[1].caption("Auto-refresh will run while this page is open.")

doc = fetch_document(doc_id)
if not doc:
    st.error("Document not found")
    st.stop()

cols = st.columns([2, 1, 1, 2])
display_name = doc.get("display_name")
cols[0].markdown(f"**Name:** {display_name or doc.get('filename')}")
cols[1].markdown(status_badge(doc.get("status", "?")), unsafe_allow_html=True)
cols[2].markdown(f"Has chunks: {'✅' if doc.get('has_chunks') else '❌'}")
if cols[3].button("Open Search with this doc", type="primary"):
    st.session_state["search_doc_ids"] = [doc_id]
    st.switch_page("pages/3_Search.py")

with st.expander("Rename document", expanded=False):
    new_name = st.text_input("Display name", value=display_name or "")
    if st.button("Save name"):
        ok, msg = post_rename(doc_id, new_name or None)
        if ok:
            st.success("Name updated.")
        else:
            st.error(f"Rename failed: {msg}")

pre = doc.get("preflight") or {}
if pre:
    title_guess = pre.get("title_guess")
    if title_guess:
        st.markdown(f"**Title guess:** {title_guess}")
    if pre.get("scanned"):
        st.warning(
            "This appears to be a scanned PDF. OCR is recommended but can be slower and may introduce errors. "
            "Please review outputs carefully."
        )
    with st.expander("Document Info", expanded=False):
        info_cols = st.columns(4)
        info_cols[0].markdown(f"**File type:** {pre.get('file_type') or '—'}")
        info_cols[1].markdown(f"**Pages:** {pre.get('page_count') or '—'}")
        info_cols[2].markdown(f"**Avg chars/page:** {pre.get('avg_chars_per_page') or '—'}")
        info_cols[3].markdown(f"**Image pages:** {pre.get('image_pages') or '—'}")
        flag_cols = st.columns(3)
        flag_cols[0].markdown(f"**Text present:** {'Yes' if pre.get('text_present') else 'No'}")
        flag_cols[1].markdown(f"**Scanned:** {'Yes' if pre.get('scanned') else 'No'}")
        flag_cols[2].markdown(f"**Parser hint:** {doc.get('parse_method') or '—'}")
        lang = pre.get("language")
        conf = pre.get("language_confidence")
        if lang:
            conf_text = f"{conf:.2f}" if conf is not None else "—"
            st.caption(f"Detected language: {lang} (confidence {conf_text})")
        else:
            if pre.get("language_source") == "insufficient_text":
                st.caption("Detected language: not enough text to infer.")

status = (doc.get("status") or "").upper()
status_messages = {
    "AWAITING_OPTIONS": "Awaiting processing options…",
    "QUEUED": "Queued for processing…",
    "PARSING": "Processing PDF with Docling…",
    "CHUNKING": "Chunking text into reviewable sections…",
    "INDEXING": "Indexing for semantic search…",
    "READY": "Ready for review.",
    "PARSED_LOW_CONFIDENCE": "Parsed with fallback parser; results may be lower fidelity.",
}
stage_message = doc.get("stage_message")
msg = stage_message or status_messages.get(status)
if msg and status != "READY":
    st.info(msg)
if status == "PARSED_LOW_CONFIDENCE":
    st.warning("Parsed with fallback parser. OCR or a higher-quality parse may improve results.")

status_steps = {
    "AWAITING_OPTIONS": 0,
    "QUEUED": 0,
    "PARSING": 1,
    "CHUNKING": 2,
    "INDEXING": 3,
    "READY": 4,
    "PARSED_LOW_CONFIDENCE": 4,
}
step = status_steps.get(status, 0)
st.progress(step / 4 if step else 0)
st.caption(f"Stage {step} of 4")

opts = doc.get("processing_options") or {}
page_count = pre.get("page_count") or doc.get("page_count")
default_start = int(opts.get("page_start") or 1)
default_end = int(opts.get("page_end") or (page_count or default_start))
if page_count:
    max_page = int(page_count)
    if default_start > max_page:
        default_start = 1
    if default_end > max_page:
        default_end = max_page

processing_busy = status in {"QUEUED", "PARSING", "CHUNKING", "INDEXING"}

st.subheader("Summary")
summary_cols = st.columns(4)
pages_processed = None
if opts.get("page_start") and opts.get("page_end"):
    try:
        pages_processed = int(opts.get("page_end")) - int(opts.get("page_start")) + 1
    except Exception:
        pages_processed = None
summary_cols[0].metric("Pages processed", pages_processed or doc.get("page_count") or 0)

chunks_count = 0
if doc.get("has_chunks") and doc.get("links", {}).get("chunks.json"):
    _chunks = fetch_chunks_json(doc.get("links", {}).get("chunks.json"))
    if _chunks and isinstance(_chunks, dict):
        chunks_count = len(_chunks.get("chunks") or [])
summary_cols[1].metric("Chunks", chunks_count)

defs_count = 0
ents_count = 0
extractions_link = (doc.get("links") or {}).get("extractions.json")
if extractions_link:
    ex = fetch_chunks_json(extractions_link)
    if ex:
        defs_count = len(ex.get("definitions") or [])
        ent = ex.get("entitlements") or {}
        ents_count = len(ent.get("products") or [])
summary_cols[2].metric("Definitions", defs_count)
summary_cols[3].metric("Entitlements", ents_count)

st.subheader("Processing Options")
st.caption("Select a page range and which outputs to generate before processing.")
with st.form("process_options"):
    if page_count:
        page_start_val = st.number_input(
            "Start page",
            min_value=1,
            max_value=int(page_count),
            value=min(default_start, int(page_count)),
            disabled=processing_busy,
        )
        page_end_val = st.number_input(
            "End page",
            min_value=page_start_val,
            max_value=int(page_count),
            value=min(default_end, int(page_count)),
            disabled=processing_busy,
        )
    else:
        page_start_val = st.number_input("Start page", min_value=1, value=default_start, disabled=processing_busy)
        page_end_val = st.number_input("End page", min_value=page_start_val, value=default_end, disabled=processing_busy)

    run_index = st.checkbox("Index for search", value=opts.get("run_index", True), disabled=processing_busy)
    run_definitions = st.checkbox("Extract definitions (terms)", value=opts.get("run_definitions", False), disabled=processing_busy)
    run_entitlements = st.checkbox("Extract entitlements (products)", value=opts.get("run_entitlements", False), disabled=processing_busy)
    semantic_default = opts.get("semantic_enrich")
    if semantic_default is None:
        semantic_default = False
    semantic_enrich = st.checkbox(
        "Assign legal tags (semantic enrichment)",
        value=semantic_default,
        disabled=processing_busy,
        help="Adds legal tags to each chunk; increases indexing time.",
    )
    ocr_default = (opts.get("ocr_mode") or "auto").lower()
    ocr_mode = st.selectbox(
        "OCR mode",
        options=["auto", "force", "off"],
        index=["auto", "force", "off"].index(ocr_default) if ocr_default in {"auto", "force", "off"} else 0,
        disabled=processing_busy,
        help="Auto enables OCR only for scanned/low-text docs.",
    )
    ocr_language_default = opts.get("ocr_language") or pre.get("language") or ""
    ocr_language = st.text_input(
        "OCR language (ISO code, e.g., en, fr, de)",
        value=ocr_language_default,
        disabled=processing_busy,
    )

    submit_label = "Start processing" if status in {"AWAITING_OPTIONS", "QUEUED"} else "Reprocess with options"
    submitted = st.form_submit_button(submit_label, disabled=processing_busy)

    if submitted:
        payload = {
            "page_start": int(page_start_val) if page_start_val else None,
            "page_end": int(page_end_val) if page_end_val else None,
            "run_index": run_index,
            "run_definitions": run_definitions,
            "run_entitlements": run_entitlements,
            "semantic_enrich": semantic_enrich,
            "ocr_mode": ocr_mode,
            "ocr_language": ocr_language or None,
        }
        ok, msg = post_process(doc_id, payload)
        if ok:
            st.success("Processing queued. Use Refresh to track progress.")
        else:
            st.error(f"Processing failed: {msg}")
st.caption("Page range limits chunking, indexing, and extraction. Parsing still scans the full PDF.")
if processing_busy:
    st.info("Processing is queued or running. You can reprocess with new options once it finishes.")

st.subheader("Actions")
act_cols = st.columns([1, 1, 3])
if act_cols[0].button("Re-chunk"):
    ok, msg = post_rechunk(doc_id)
    if ok:
        st.success("Re-chunk queued. Click Refresh to see status updates.")
    else:
        st.error(f"Re-chunk failed: {msg}")
if act_cols[1].button("Re-index"):
    ok, msg = post_reindex(doc_id)
    if ok:
        st.success("Re-index queued. Click Refresh to see status updates.")
    else:
        st.error(f"Re-index failed: {msg}")
act_cols[2].caption("Tip: Re-chunk after ingest if sections look off. Re-index after chunking to refresh search.")

def_status = doc.get("definitions_status")
ent_status = doc.get("entitlements_status")
if def_status:
    st.caption(f"Definitions extractor: {def_status}")
if ent_status:
    st.caption(f"Entitlements extractor: {ent_status}")

if (def_status or "").upper() == "RUNNING":
    st.info("Extracting definitions…")
if (ent_status or "").upper() == "RUNNING":
    st.info("Extracting entitlements…")

st.subheader("Extractors")
ex_cols = st.columns([1, 1, 2])
if ex_cols[0].button("Run Definitions"):
    from ui_utils import post_extract_definitions

    ok, msg = post_extract_definitions(doc_id)
    if ok:
        st.success("Definitions extraction queued. Click Refresh to update.")
    else:
        st.error(f"Definitions extraction failed: {msg}")
if ex_cols[1].button("Run Entitlements"):
    from ui_utils import post_extract_entitlements

    ok, msg = post_extract_entitlements(doc_id)
    if ok:
        st.success("Entitlements extraction queued. Click Refresh to update.")
    else:
        st.error(f"Entitlements extraction failed: {msg}")
ex_cols[2].caption("Run these after chunking is complete.")

st.divider()

st.subheader("Ingestion")
icols = st.columns([2, 1, 3])
icols[0].markdown(f"Ingested: {doc.get('ingested_at') or '—'}")
icols[1].markdown(f"Pages: {doc.get('page_count') if doc.get('page_count') is not None else '—'}")
if opts.get("page_start") or opts.get("page_end"):
    st.caption(f"Selected pages: {opts.get('page_start') or '—'}–{opts.get('page_end') or '—'}")

links = (doc.get("links") or {})
text_link = links.get("document_text.txt")
json_link = links.get("document.json")
chunks_link = links.get("chunks.json")
debug_link = links.get("chunk_debug.md")

btn_cols = icols[2].columns(2)
if text_link:
    btn_cols[0].link_button("Open document_text.txt", api_url(text_link))
if json_link:
    btn_cols[1].link_button("Open document.json", api_url(json_link))
if chunks_link:
    btn_cols = st.columns(2)
    btn_cols[0].link_button("Open chunks.json", api_url(chunks_link))
if debug_link:
    st.link_button("Open chunk_debug.md", api_url(debug_link))

errors = doc.get("errors") or []
if errors:
    st.error("\n".join(errors))

st.subheader("Chunks")
chunks_data = None
if chunks_link:
    chunks_data = fetch_chunks_json(chunks_link)

chunks = []
if chunks_data and isinstance(chunks_data, dict):
    chunks = chunks_data.get("chunks") or []
else:
    chunks = fetch_chunks(doc_id)

if not chunks:
    st.info("No chunks yet.")
else:
    section_paths = []
    for ch in chunks:
        path = ch.get("section_path") or []
        if isinstance(path, list):
            section_paths.append(" > ".join(path))
        elif path:
            section_paths.append(str(path))
    section_paths = sorted({p for p in section_paths if p})

    left, middle, right = st.columns([1, 2, 2])

    with left:
        st.markdown("**Sections**")
        section_filter = st.selectbox("Filter by section", options=["All"] + section_paths)
        text_filter = st.text_input("Text contains")
        max_show = st.slider("Max chunks", min_value=10, max_value=300, value=80, step=10)

    filtered = []
    for ch in chunks:
        section_path = ch.get("section_path") or []
        section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path or "")
        if section_filter != "All" and section_str != section_filter:
            continue
        if text_filter and text_filter.lower() not in (ch.get("text") or ch.get("text_preview", "")).lower():
            continue
        filtered.append((section_str, ch))

    if filtered:
        if "selected_chunk_id" not in st.session_state:
            st.session_state["selected_chunk_id"] = filtered[0][1].get("chunk_id") or filtered[0][1].get("id")

    with middle:
        st.markdown("**Chunk List**")
        for section_str, ch in filtered[:max_show]:
            with st.container(border=True):
                stype = ch.get("semantic_type")
                label = f"{ch.get('type','chunk')} — {section_str or '—'} — p.{ch.get('page_start')}–{ch.get('page_end')}"
                if stype:
                    label += f" • {stype}"
                st.markdown(label)
                st.write(ch.get("text_preview") or (ch.get("text", "")[:240] + "…"))
                if st.button("View", key=f"view-{ch.get('chunk_id') or ch.get('id')}"):
                    st.session_state["selected_chunk_id"] = ch.get("chunk_id") or ch.get("id")

    with right:
        st.markdown("**Chunk Viewer**")
        selected = None
        for _section_str, ch in filtered:
            if (ch.get("chunk_id") or ch.get("id")) == st.session_state.get("selected_chunk_id"):
                selected = ch
                break
        if not selected and filtered:
            selected = filtered[0][1]

        if selected:
            section_path = selected.get("section_path") or []
            section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path or "")
            st.caption(f"Type: {selected.get('type')} • Section: {section_str or '—'}")
            if selected.get("semantic_type"):
                conf = selected.get("semantic_confidence")
                st.caption(f"Legal tag: {selected.get('semantic_type')} ({conf:.2f})")
            st.caption(f"Clause: {selected.get('clause_ref') or '—'} • Pages: {selected.get('page_start')}–{selected.get('page_end')}")
            st.text_area("Text", value=selected.get("text") or selected.get("text_preview", ""), height=420)

            show_image = st.toggle("Show page image", value=False)
            if show_image and selected.get("page_start"):
                page_num = selected.get("page_start")
                try:
                    st.image(api_url(f"/documents/{doc_id}/pages/{page_num}"), caption=f"Page {page_num}")
                except Exception:
                    st.info("Page image unavailable.")

if auto_refresh and (status != "READY" or (def_status or "").upper() == "RUNNING"):
    time.sleep(refresh_sec)
    st.rerun()
