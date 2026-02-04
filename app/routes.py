from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from config import MAX_UPLOAD_BYTES, PROCESSED_DIR, RAW_DIR
from models import (
    Chunk,
    DocumentDetail,
    DocumentStatus,
    DocumentSummary,
    FeedbackItem,
    ProcessingOptions,
    SearchRequest,
    SearchHit,
)
from preflight import preflight_file
from search import hybrid_search, keyword_search, semantic_search
from storage import (
    append_feedback,
    find_raw_path,
    now_iso,
    read_json,
    safe_filename,
    stream_upload_to_temp,
    write_json,
)
from worker import enqueue_task


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


def normalize_processing_options(opts: ProcessingOptions, page_count: Optional[int]) -> dict:
    data = opts.dict()
    page_start = data.get("page_start")
    page_end = data.get("page_end")

    if page_start is not None and page_start < 1:
        raise HTTPException(status_code=400, detail="page_start must be >= 1")
    if page_end is not None and page_end < 1:
        raise HTTPException(status_code=400, detail="page_end must be >= 1")
    if page_count:
        if page_start is not None and page_start > page_count:
            raise HTTPException(status_code=400, detail=f"page_start exceeds page_count ({page_count})")
        if page_end is not None and page_end > page_count:
            page_end = page_count
    if page_start is not None and page_end is not None and page_end < page_start:
        raise HTTPException(status_code=400, detail="page_end must be >= page_start")

    ocr_mode = (data.get("ocr_mode") or "").lower() or None
    if ocr_mode and ocr_mode not in {"auto", "force", "off"}:
        raise HTTPException(status_code=400, detail="ocr_mode must be one of auto, force, off")
    data["ocr_mode"] = ocr_mode

    ocr_language = data.get("ocr_language")
    if isinstance(ocr_language, str):
        ocr_language = ocr_language.strip().lower()
        if not ocr_language:
            ocr_language = None
    data["ocr_language"] = ocr_language

    data["page_start"] = page_start
    data["page_end"] = page_end
    return data


@router.post("/upload", response_model=DocumentSummary)
async def upload_document(file: UploadFile = File(...)):
    safe_name = safe_filename(file.filename)
    tmp_path, doc_id, size_bytes = stream_upload_to_temp(file, MAX_UPLOAD_BYTES)

    raw_dir = RAW_DIR / doc_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / safe_name
    if not raw_path.exists():
        tmp_path.replace(raw_path)
    else:
        tmp_path.unlink(missing_ok=True)

    processed_dir = PROCESSED_DIR / doc_id
    processed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = processed_dir / "meta.json"
    preflight = preflight_file(raw_path)
    page_count = preflight.get("page_count")
    processing_options = {
        "page_start": 1 if page_count else None,
        "page_end": page_count,
        "run_index": True,
        "run_definitions": False,
        "run_entitlements": False,
        "ocr_mode": "auto",
        "ocr_language": preflight.get("language"),
    }
    write_json(
        meta_path,
        {
            "filename": safe_name,
            "ingested_at": now_iso(),
            "status": DocumentStatus.AWAITING_OPTIONS,
            "page_count": page_count,
            "errors": [],
            "size_bytes": size_bytes,
            "preflight": preflight,
            "processing_options": processing_options,
            "stage_message": "Awaiting processing options…",
        },
    )

    meta = read_json(meta_path) or {}
    return DocumentSummary(
        doc_id=doc_id,
        filename=meta.get("filename", safe_name),
        display_name=meta.get("display_name"),
        status=meta.get("status", DocumentStatus.QUEUED),
        page_count=meta.get("page_count"),
        ingested_at=meta.get("ingested_at"),
        errors=meta.get("errors"),
    )


@router.get("/documents", response_model=List[DocumentSummary])
def list_documents():
    docs: List[DocumentSummary] = []
    seen: set[str] = set()

    if PROCESSED_DIR.exists():
        for pdir in PROCESSED_DIR.iterdir():
            if not pdir.is_dir():
                continue
            meta = read_json(pdir / "meta.json") or {}
            if meta:
                doc_id = pdir.name
                seen.add(doc_id)
                docs.append(
                    DocumentSummary(
                        doc_id=doc_id,
                        filename=meta.get("filename"),
                        display_name=meta.get("display_name"),
                        status=meta.get("status", "READY"),
                        page_count=meta.get("page_count"),
                        ingested_at=meta.get("ingested_at"),
                        errors=meta.get("errors"),
                    )
                )

    if RAW_DIR.exists():
        for rdir in RAW_DIR.iterdir():
            if not rdir.is_dir() or rdir.name in seen:
                continue
            files = list(rdir.iterdir())
            filename = files[0].name if files else None
            docs.append(DocumentSummary(doc_id=rdir.name, filename=filename, status="QUEUED"))

    docs.sort(key=lambda d: (d.ingested_at or "", d.filename or ""), reverse=True)
    return docs


@router.post("/documents/{doc_id}/process")
def process_document(doc_id: str, options: ProcessingOptions):
    raw_path = find_raw_path(doc_id)
    if not raw_path:
        raise HTTPException(status_code=404, detail="Raw document not found")

    processed_dir = PROCESSED_DIR / doc_id
    processed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    preflight = meta.get("preflight") or {}
    page_count = preflight.get("page_count") or meta.get("page_count")

    normalized = normalize_processing_options(options, page_count)
    meta.update(
        {
            "processing_options": normalized,
            "status": DocumentStatus.QUEUED,
            "stage_message": "Queued for processing…",
        }
    )
    write_json(meta_path, meta)

    enqueue_task({"type": "ingest", "raw_path": raw_path, "processed_dir": processed_dir, "options": normalized})
    return {"status": "queued", "action": "process", "options": normalized}


@router.post("/documents/{doc_id}/rename")
def rename_document(doc_id: str, payload: dict):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    name = (payload or {}).get("display_name")
    if name is not None and not str(name).strip():
        name = None
    meta.update({"display_name": name})
    write_json(meta_path, meta)
    return {"status": "ok", "display_name": name}


@router.post("/documents/{doc_id}/feedback")
def submit_feedback(doc_id: str, feedback: FeedbackItem):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    entry = feedback.dict()
    entry.update({"doc_id": doc_id, "submitted_at": now_iso()})
    append_feedback(processed_dir, entry)
    return {"status": "ok"}


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str):
    raw_dir = RAW_DIR / doc_id
    processed_dir = PROCESSED_DIR / doc_id
    if not raw_dir.exists() and not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    meta = read_json(processed_dir / "meta.json") or {}
    filename = meta.get("filename")
    if not filename and raw_dir.exists():
        files = list(raw_dir.iterdir())
        filename = files[0].name if files else None

    status = meta.get("status", "READY" if processed_dir.exists() else "QUEUED")
    has_chunks = (processed_dir / "chunks.json").exists()

    links = {}
    for name in [
        "document_text.txt",
        "document.json",
        "ingest_log.json",
        "meta.json",
        "chunks.json",
        "chunk_debug.md",
        "extractions.json",
        "definitions.csv",
        "entitlements.csv",
        "review_pack.md",
        "feedback.json",
    ]:
        if (processed_dir / name).exists():
            links[name] = f"/documents/{doc_id}/files/{name}"

    return DocumentDetail(
        doc_id=doc_id,
        filename=filename,
        display_name=meta.get("display_name"),
        status=status,
        has_chunks=has_chunks,
        page_count=meta.get("page_count"),
        ingested_at=meta.get("ingested_at"),
        errors=meta.get("errors"),
        definitions_status=meta.get("definitions_status"),
        entitlements_status=meta.get("entitlements_status"),
        preflight=meta.get("preflight"),
        processing_options=meta.get("processing_options"),
        stage_message=meta.get("stage_message"),
        parse_method=meta.get("parse_method"),
        links=links or None,
    )


@router.get("/documents/{doc_id}/chunks", response_model=List[Chunk])
def list_chunks(doc_id: str):
    processed_dir = PROCESSED_DIR / doc_id
    chunks_path = processed_dir / "chunks.json"
    if not chunks_path.exists():
        return []
    data = read_json(chunks_path) or {}
    chunks = data.get("chunks") or []
    results: List[Chunk] = []
    for ch in chunks:
        text = ch.get("text", "") or ""
        preview = text[:240] + ("…" if len(text) > 240 else "")
        results.append(
            Chunk(
                id=ch.get("chunk_id"),
                type=ch.get("type", "chunk"),
                text_preview=preview,
                section_path=" > ".join(ch.get("section_path") or []) if isinstance(ch.get("section_path"), list) else ch.get("section_path"),
                clause_ref=ch.get("clause_ref"),
                page_start=ch.get("page_start"),
                page_end=ch.get("page_end"),
                semantic_type=ch.get("semantic_type"),
                semantic_confidence=ch.get("semantic_confidence"),
            )
        )
    return results


@router.post("/documents/{doc_id}/rechunk")
def rechunk_document(doc_id: str):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if not (processed_dir / "document.json").exists():
        raise HTTPException(status_code=400, detail="document.json not found for this document")
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"status": DocumentStatus.CHUNKING})
    write_json(meta_path, meta)
    enqueue_task({"type": "rechunk", "processed_dir": processed_dir})
    return {"status": "queued", "action": "rechunk"}


@router.post("/documents/{doc_id}/reindex")
def reindex_document(doc_id: str):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if not (processed_dir / "chunks.json").exists():
        raise HTTPException(status_code=400, detail="chunks.json not found for this document")
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"status": DocumentStatus.INDEXING})
    write_json(meta_path, meta)
    enqueue_task({"type": "reindex", "processed_dir": processed_dir})
    return {"status": "queued", "action": "reindex"}


@router.post("/documents/{doc_id}/extract/definitions")
def extract_definitions(doc_id: str):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if not (processed_dir / "chunks.json").exists():
        raise HTTPException(status_code=400, detail="chunks.json not found for this document")
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"definitions_status": "RUNNING"})
    write_json(meta_path, meta)
    enqueue_task({"type": "definitions", "processed_dir": processed_dir})
    return {"status": "queued", "action": "definitions"}


@router.post("/documents/{doc_id}/extract/entitlements")
def extract_entitlements(doc_id: str):
    processed_dir = PROCESSED_DIR / doc_id
    if not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if not (processed_dir / "chunks.json").exists():
        raise HTTPException(status_code=400, detail="chunks.json not found for this document")
    meta_path = processed_dir / "meta.json"
    meta = read_json(meta_path) or {}
    meta.update({"entitlements_status": "RUNNING"})
    write_json(meta_path, meta)
    enqueue_task({"type": "entitlements", "processed_dir": processed_dir})
    return {"status": "queued", "action": "entitlements"}


def safe_file_path(doc_id: str, name: str) -> Path:
    allowed = {
        "document_text.txt",
        "document.json",
        "ingest_log.json",
        "meta.json",
        "chunks.json",
        "chunk_debug.md",
        "extractions.json",
        "definitions.csv",
        "entitlements.csv",
        "review_pack.md",
        "feedback.json",
    }
    if name not in allowed:
        raise HTTPException(status_code=400, detail="Invalid file name")
    p = PROCESSED_DIR / doc_id / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return p


@router.get("/documents/{doc_id}/files/{name}")
def download_processed_file(doc_id: str, name: str):
    path = safe_file_path(doc_id, name)
    return FileResponse(path)


@router.get("/documents/{doc_id}/pages/{page}")
def render_page_image(doc_id: str, page: int, zoom: float = 1.5):
    raw_path = find_raw_path(doc_id)
    if not raw_path:
        raise HTTPException(status_code=404, detail="Raw document not found")
    if raw_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Page rendering is only supported for PDF files")
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")

    try:
        import fitz  # PyMuPDF

        with fitz.open(raw_path) as doc:
            if page > doc.page_count:
                raise HTTPException(status_code=404, detail="Page out of range")
            pg = doc.load_page(page - 1)
            mat = fitz.Matrix(zoom, zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
        return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render page: {e}")


@router.post("/search", response_model=List[SearchHit])
def search(req: SearchRequest):
    mode = (req.mode or "hybrid").lower()
    top_k = req.top_k or 10
    if mode == "keyword":
        return keyword_search(req.query, req.filters, top_k)
    if mode == "semantic":
        return semantic_search(req.query, req.filters, top_k)
    return hybrid_search(req.query, req.filters, top_k)
