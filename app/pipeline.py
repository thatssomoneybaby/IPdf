from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from docling_utils import (
    build_docling_converter_with_ocr,
    canonical_from_pymupdf,
    extract_with_pymupdf,
    try_docling_to_canonical,
    try_import_docling,
)
from models import DocumentStatus
from preflight import preflight_file, tesseract_lang
from storage import now_iso, read_json, write_json


def run_docling_or_fallback(src_path: Path, out_dir: Path, options: Optional[dict] = None):
    log: dict = {
        "started_at": now_iso(),
        "finished_at": None,
        "steps": [],
        "errors": [],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_json = out_dir / "document.json"
    doc_text = out_dir / "document_text.txt"
    chunks_json = out_dir / "chunks.json"
    chunk_debug = out_dir / "chunk_debug.md"
    doc_meta = out_dir / "meta.json"

    preflight = preflight_file(src_path)
    try:
        meta = read_json(doc_meta) or {}
        if options:
            meta.update({"processing_options": options})
        meta.update({"preflight": preflight})
        write_json(doc_meta, meta)
    except Exception:
        pass

    meta = read_json(doc_meta) or {}
    opts = options or meta.get("processing_options") or {}
    page_start = opts.get("page_start")
    page_end = opts.get("page_end")
    run_index = opts.get("run_index", True)
    run_definitions = opts.get("run_definitions", False)
    run_entitlements = opts.get("run_entitlements", False)
    semantic_enrich = opts.get("semantic_enrich")
    ocr_mode = (opts.get("ocr_mode") or "auto").lower()
    ocr_language = (opts.get("ocr_language") or (meta.get("preflight") or {}).get("language") or "").strip().lower() or None
    if semantic_enrich is None:
        semantic_enrich = os.getenv("SEMANTIC_ENRICH", "").lower() in {"1", "true", "yes"}

    preflight_meta = meta.get("preflight") or {}
    scanned_flag = bool(preflight_meta.get("scanned"))
    text_present = bool(preflight_meta.get("text_present"))
    if ocr_mode == "off":
        ocr_enabled = False
    elif ocr_mode == "force":
        ocr_enabled = True
    else:
        ocr_enabled = scanned_flag or not text_present

    force_full_page = ocr_mode == "force" or (ocr_mode == "auto" and scanned_flag)
    ocr_langs_iso = [ocr_language] if ocr_language else ["en"]
    tess_lang = tesseract_lang(ocr_language) or "eng"
    ocr_langs_tess = [tess_lang]

    meta.update(
        {
            "filename": meta.get("filename") or src_path.name,
            "ingested_at": meta.get("ingested_at") or now_iso(),
            "status": DocumentStatus.PARSING,
            "stage_message": "Processing PDF with Docling + OCR…" if ocr_enabled else "Processing PDF with Docling…",
        }
    )
    write_json(doc_meta, meta)

    page_count = None
    parse_method = None
    adapter_used = None
    parser_versions: dict[str, Optional[str]] = {}

    pages = []
    blocks = []

    dl = try_import_docling()
    if dl is not None:
        versions: dict[str, Optional[str]] = {"docling": getattr(dl, "__version__", None)}
        if not versions.get("docling"):
            try:
                import importlib.metadata

                versions["docling"] = importlib.metadata.version("docling")
            except Exception:
                pass
        try:
            import docling_core as dlc  # type: ignore

            versions["docling_core"] = getattr(dlc, "__version__", None)
        except Exception:
            versions["docling_core"] = None
        try:
            import docling_parse as dlp  # type: ignore

            versions["docling_parse"] = getattr(dlp, "__version__", None)
        except Exception:
            versions["docling_parse"] = None

        ocr_engine = None
        converter = None
        if ocr_enabled:
            converter, ocr_engine = build_docling_converter_with_ocr(ocr_langs_iso, ocr_langs_tess, force_full_page)
        log["steps"].append(
            {
                "step": "docling_parse_start",
                "at": now_iso(),
                "versions": versions,
                "ocr_enabled": ocr_enabled,
                "ocr_mode": ocr_mode,
                "ocr_language": ocr_langs_iso,
                "ocr_engine": ocr_engine,
            }
        )
        try:
            pages, blocks, page_count, adapter_used = try_docling_to_canonical(dl, src_path, converter=converter)
            parse_method = "docling"
            parser_versions = versions
            log["steps"].append({"step": "docling_parse_ok", "at": now_iso(), "page_count": page_count, "adapter": adapter_used})
        except Exception as e:
            log["errors"].append(f"docling_failed: {e}")
            log["steps"].append({"step": "docling_parse_failed", "at": now_iso()})
    else:
        log["steps"].append({"step": "docling_not_available", "at": now_iso()})

    if not pages or not blocks:
        page_texts, page_count, pymupdf_version = extract_with_pymupdf(src_path)
        pages, blocks = canonical_from_pymupdf(page_texts)
        parse_method = "pymupdf_fallback"
        parser_versions = {"pymupdf": pymupdf_version}
        log["steps"].append({"step": "fallback_pymupdf_ok", "at": now_iso(), "page_count": page_count})

    try:
        joined_text = "\n\n".join([b.get("text", "") for b in blocks if b.get("page_start") == b.get("page_end")])
        doc_text.write_text(joined_text, encoding="utf-8")
        log["steps"].append({"step": "wrote_document_text", "at": now_iso(), "bytes": len(joined_text.encode("utf-8"))})
    except Exception as e:
        log["errors"].append(f"write_text_failed: {e}")

    try:
        meta_for_doc = read_json(doc_meta) or {}
        write_json(
            doc_json,
            {
                "schema": "ipdf.document@v1",
                "source": {
                    "filename": src_path.name,
                    "sha256": src_path.parent.name,
                    "size_bytes": meta_for_doc.get("size_bytes"),
                    "ingested_at": meta_for_doc.get("ingested_at"),
                    "parser": {
                        "name": parse_method,
                        "version": parser_versions,
                        "config": {"adapter": adapter_used} if adapter_used else {},
                    },
                },
                "preflight": meta_for_doc.get("preflight"),
                "doc_id": src_path.parent.name,
                "page_count": page_count or (pages[-1]["page"] if pages else None),
                "pages": pages,
                "blocks": blocks,
            },
        )
        log["steps"].append({"step": "wrote_document_json", "at": now_iso(), "blocks": len(blocks)})
    except Exception as e:
        log["errors"].append(f"write_document_json_failed: {e}")

    try:
        meta = read_json(doc_meta) or {}
        meta.update({"status": DocumentStatus.CHUNKING, "stage_message": "Chunking text into reviewable sections…"})
        write_json(doc_meta, meta)

        from ipdf.chunking import chunk_document, chunk_debug_markdown

        doc_loaded = read_json(doc_json) or {}
        chunked = chunk_document(doc_loaded, page_start=page_start, page_end=page_end)
        write_json(chunks_json, chunked)
        log["steps"].append(
            {
                "step": "chunking_ok",
                "at": now_iso(),
                "chunks": len(chunked.get("chunks", [])),
                "page_start": page_start,
                "page_end": page_end,
            }
        )
        if os.getenv("CHUNK_DEBUG", "").lower() in {"1", "true", "yes"}:
            chunk_debug.write_text(chunk_debug_markdown(chunked), encoding="utf-8")
            log["steps"].append({"step": "chunk_debug_written", "at": now_iso()})

        if run_definitions and chunks_json.exists():
            from worker import enqueue_task

            enqueue_task({"type": "definitions", "processed_dir": out_dir})
        if run_entitlements and chunks_json.exists():
            from worker import enqueue_task

            enqueue_task({"type": "entitlements", "processed_dir": out_dir})

    except Exception as e:
        log["errors"].append(f"chunking_failed: {e}")

    try:
        if run_index:
            meta = read_json(doc_meta) or {}
            stage_msg = "Assigning legal tags…" if semantic_enrich else "Indexing for semantic search…"
            meta.update({"status": DocumentStatus.INDEXING, "stage_message": stage_msg})
            write_json(doc_meta, meta)

            from ipdf.indexing import index_chunks

            qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
            if chunks_json.exists():
                chunked = read_json(chunks_json) or {}
                indexed, enriched = index_chunks(
                    chunked,
                    qdrant_url=qdrant_url,
                    embedding_model=embedding_model,
                    semantic_enrich=semantic_enrich,
                )
                if semantic_enrich:
                    write_json(chunks_json, enriched)
                log["steps"].append(
                    {
                        "step": "indexing_ok",
                        "at": now_iso(),
                        "points": indexed,
                        "embedding_model": embedding_model,
                        "semantic_enrich": semantic_enrich,
                    }
                )
        else:
            log["steps"].append({"step": "indexing_skipped", "at": now_iso()})
    except Exception as e:
        log["errors"].append(f"indexing_failed: {e}")

    log["finished_at"] = now_iso()

    meta = read_json(doc_meta) or {}
    had_chunk_error = any(e.startswith("chunking_failed") for e in log.get("errors", []))
    had_index_error = any(e.startswith("indexing_failed") for e in log.get("errors", []))
    if not blocks:
        status = DocumentStatus.FAILED_DOCLING
    elif had_chunk_error:
        status = DocumentStatus.FAILED_CHUNKING
    elif had_index_error:
        status = DocumentStatus.FAILED_INDEXING
    elif parse_method == "pymupdf_fallback":
        status = DocumentStatus.PARSED_LOW_CONFIDENCE
    else:
        status = DocumentStatus.READY
    meta.update(
        {
            "filename": src_path.name,
            "ingested_at": meta.get("ingested_at") or now_iso(),
            "status": status,
            "page_count": page_count or len(pages) if pages else None,
            "errors": log["errors"],
            "parse_method": parse_method,
            "processing_options": opts,
            "indexing_skipped": not run_index,
            "stage_message": None,
        }
    )
    write_json(doc_meta, meta)
    write_json(out_dir / "ingest_log.json", log)

    return log


def append_log(out_dir: Path, step: dict, error: Optional[str] = None):
    log_path = out_dir / "ingest_log.json"
    log = read_json(log_path) or {"started_at": now_iso(), "finished_at": None, "steps": [], "errors": []}
    log["steps"].append(step)
    if error:
        log["errors"].append(error)
    log["finished_at"] = now_iso()
    write_json(log_path, log)


def run_chunking_only(processed_dir: Path):
    doc_json = processed_dir / "document.json"
    if not doc_json.exists():
        raise RuntimeError("document.json not found")

    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    opts = meta.get("processing_options") or {}
    page_start = opts.get("page_start")
    page_end = opts.get("page_end")
    meta.update({"status": DocumentStatus.CHUNKING, "stage_message": "Chunking text into reviewable sections…"})
    write_json(meta_path, meta)

    from ipdf.chunking import chunk_document, chunk_debug_markdown

    try:
        doc_loaded = read_json(doc_json) or {}
        chunked = chunk_document(doc_loaded, page_start=page_start, page_end=page_end)
        write_json(processed_dir / "chunks.json", chunked)
        if os.getenv("CHUNK_DEBUG", "").lower() in {"1", "true", "yes"}:
            (processed_dir / "chunk_debug.md").write_text(chunk_debug_markdown(chunked), encoding="utf-8")
        append_log(processed_dir, {"step": "rechunk_ok", "at": now_iso(), "chunks": len(chunked.get("chunks", []))})
        meta.update({"status": DocumentStatus.READY, "stage_message": None})
        write_json(meta_path, meta)
    except Exception as e:
        append_log(processed_dir, {"step": "rechunk_failed", "at": now_iso()}, error=f"chunking_failed: {e}")
        meta.update({"status": DocumentStatus.FAILED_CHUNKING, "stage_message": None, "errors": (meta.get("errors") or []) + [str(e)]})
        write_json(meta_path, meta)
        raise


def run_indexing_only(processed_dir: Path):
    chunks_json = processed_dir / "chunks.json"
    if not chunks_json.exists():
        raise RuntimeError("chunks.json not found")

    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    opts = meta.get("processing_options") or {}
    semantic_enrich = opts.get("semantic_enrich")
    if semantic_enrich is None:
        semantic_enrich = os.getenv("SEMANTIC_ENRICH", "").lower() in {"1", "true", "yes"}
    stage_msg = "Assigning legal tags…" if semantic_enrich else "Indexing for semantic search…"
    meta.update({"status": DocumentStatus.INDEXING, "stage_message": stage_msg})
    write_json(meta_path, meta)

    from ipdf.indexing import index_chunks

    try:
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        chunked = read_json(chunks_json) or {}
        indexed, enriched = index_chunks(
            chunked,
            qdrant_url=qdrant_url,
            embedding_model=embedding_model,
            semantic_enrich=semantic_enrich,
        )
        if semantic_enrich:
            write_json(chunks_json, enriched)
        append_log(processed_dir, {"step": "reindex_ok", "at": now_iso(), "points": indexed})
        meta.update({"status": DocumentStatus.READY, "stage_message": None})
        write_json(meta_path, meta)
    except Exception as e:
        append_log(processed_dir, {"step": "reindex_failed", "at": now_iso()}, error=f"indexing_failed: {e}")
        meta.update({"status": DocumentStatus.FAILED_INDEXING, "stage_message": None, "errors": (meta.get("errors") or []) + [str(e)]})
        write_json(meta_path, meta)
        raise


def run_definitions_extractor(processed_dir: Path):
    chunks_json = processed_dir / "chunks.json"
    if not chunks_json.exists():
        raise RuntimeError("chunks.json not found")

    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"definitions_status": "RUNNING"})
    write_json(meta_path, meta)

    from ipdf.definitions_extractor import extract_definitions, update_review_pack, write_definitions_csv

    try:
        chunked = read_json(chunks_json) or {}
        result = extract_definitions(chunked)
        extractions_path = processed_dir / "extractions.json"
        existing = read_json(extractions_path) or {}
        existing.update(
            {
                "doc_id": result.get("doc_id"),
                "extracted_at": result.get("extracted_at"),
                "pipeline": result.get("pipeline"),
                "definitions": result.get("definitions"),
            }
        )
        write_json(extractions_path, existing)

        defs = result.get("definitions") or []
        write_definitions_csv(processed_dir / "definitions.csv", result.get("doc_id"), defs)
        update_review_pack(processed_dir / "review_pack.md", defs)
        append_log(processed_dir, {"step": "definitions_ok", "at": now_iso(), "count": len(defs)})
        meta.update({"definitions_status": "COMPLETE"})
        write_json(meta_path, meta)
    except Exception as e:
        append_log(processed_dir, {"step": "definitions_failed", "at": now_iso()}, error=f"definitions_failed: {e}")
        meta.update({"definitions_status": "FAILED", "errors": (meta.get("errors") or []) + [str(e)]})
        write_json(meta_path, meta)
        raise


def run_entitlements_extractor(processed_dir: Path):
    chunks_json = processed_dir / "chunks.json"
    if not chunks_json.exists():
        raise RuntimeError("chunks.json not found")

    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"entitlements_status": "RUNNING"})
    write_json(meta_path, meta)

    from ipdf.entitlements_extractor import extract_entitlements, update_review_pack, write_entitlements_csv

    try:
        chunked = read_json(chunks_json) or {}
        result = extract_entitlements(chunked)
        extractions_path = processed_dir / "extractions.json"
        existing = read_json(extractions_path) or {}
        existing.update(
            {
                "doc_id": result.get("doc_id"),
                "extracted_at": result.get("extracted_at"),
                "pipeline": result.get("pipeline"),
                "entitlements": result.get("entitlements"),
            }
        )
        write_json(extractions_path, existing)

        ent = result.get("entitlements") or {}
        write_entitlements_csv(processed_dir / "entitlements.csv", result.get("doc_id"), ent.get("products") or [])
        update_review_pack(processed_dir / "review_pack.md", ent)
        append_log(processed_dir, {"step": "entitlements_ok", "at": now_iso(), "count": len(ent.get("products") or [])})
        meta.update({"entitlements_status": "COMPLETE"})
        write_json(meta_path, meta)
    except Exception as e:
        append_log(processed_dir, {"step": "entitlements_failed", "at": now_iso()}, error=f"entitlements_failed: {e}")
        meta.update({"entitlements_status": "FAILED", "errors": (meta.get("errors") or []) + [str(e)]})
        write_json(meta_path, meta)
        raise
