from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


STORAGE_PATH = os.getenv("STORAGE_PATH", str(Path("storage").resolve()))
RAW_DIR = Path(STORAGE_PATH) / "raw"
PROCESSED_DIR = Path(STORAGE_PATH) / "processed"

for d in [RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class DocumentStatus(str):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    READY = "READY"
    FAILED_DOCLING = "FAILED_DOCLING"
    PARSED_LOW_CONFIDENCE = "PARSED_LOW_CONFIDENCE"


class DocumentSummary(BaseModel):
    doc_id: str
    filename: Optional[str] = None
    status: str = "QUEUED"
    page_count: Optional[int] = None
    ingested_at: Optional[str] = None
    errors: Optional[list[str]] = None


class SearchFilter(BaseModel):
    doc_ids: Optional[List[str]] = None
    section_contains: Optional[str] = None
    type: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class SearchRequest(BaseModel):
    query: str
    mode: str = "hybrid"  # semantic | keyword | hybrid
    filters: Optional[SearchFilter] = None


class Evidence(BaseModel):
    doc_id: str
    section_path: Optional[str] = None
    clause_ref: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class SearchHit(BaseModel):
    score: float
    snippet: str
    evidence: Evidence


app = FastAPI(title="IPdf API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: Path):
    import json

    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _try_import_docling():
    try:
        import docling  # type: ignore

        return docling
    except Exception:
        return None


def _extract_with_pymupdf(pdf_path: Path):
    try:
        import fitz  # PyMuPDF

        page_texts: list[str] = []
        with fitz.open(pdf_path) as doc:
            page_count = doc.page_count
            for page in doc:
                page_texts.append(page.get_text())
        return (page_texts, page_count)
    except Exception:
        return ([], None)


def _canonical_from_pymupdf(page_texts: list[str]):
    blocks = []
    for i, text in enumerate(page_texts, start=1):
        blk = {
            "block_id": f"p{i}",
            "type": "paragraph",
            "text": text or "",
            "page_start": i,
            "page_end": i,
            # bbox unknown in fallback
        }
        blocks.append(blk)
    pages = [{"page": i} for i in range(1, len(page_texts) + 1)]
    return pages, blocks


def _try_docling_to_canonical(dl, src_path: Path):
    """Best-effort Docling integration to build canonical pages/blocks.

    Returns tuple (pages, blocks, page_count, adapter_used) or raises.
    """
    # Because Docling's API may vary, attempt a couple of common paths.
    # If any attempt fails, raise to let caller fallback.
    # Implementation is intentionally defensive.
    pages = []
    blocks = []
    page_count = None
    adapter_used: Optional[str] = None

    try:
        # Attempt 1: a hypothetical high-level converter on top-level API
        if hasattr(dl, "convert_pdf"):
            ddoc = dl.convert_pdf(str(src_path))  # type: ignore[attr-defined]
            adapter_used = "convert_pdf"
        else:
            ddoc = None
    except Exception:
        ddoc = None

    if ddoc is None:
        # Attempt 2: try a DocumentConverter available in recent Docling packages
        try:
            converter_cls = None
            # Try nested module first
            try:
                from docling.document_converter import DocumentConverter as _DC  # type: ignore

                converter_cls = _DC
            except Exception:
                converter_cls = getattr(dl, "DocumentConverter", None)

            if converter_cls is not None:
                converter = converter_cls()  # type: ignore
                # Prefer convert(), fall back to run()/process()
                if hasattr(converter, "convert"):
                    ddoc = converter.convert(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.convert"
                elif hasattr(converter, "run"):
                    ddoc = converter.run(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.run"
                elif hasattr(converter, "process"):
                    ddoc = converter.process(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.process"
                else:
                    ddoc = None
        except Exception:
            ddoc = None

    if ddoc is None:
        # Attempt 3: try a Pipeline if exposed (older APIs)
        try:
            pipeline_cls = getattr(dl, "SimplePipeline", None) or getattr(dl, "Pipeline", None)
            if pipeline_cls is None:
                raise RuntimeError("Docling pipeline not found")
            pipeline = pipeline_cls()
            ddoc = pipeline.run(str(src_path))  # type: ignore
            adapter_used = f"{getattr(pipeline_cls, '__name__', 'Pipeline')}.run"
        except Exception as e:
            raise RuntimeError(f"Docling parse failed: {e}")

    # Extract pages/blocks from ddoc using duck-typing
    # Expect either ddoc.pages iterable, each with blocks; or ddoc.blocks with page refs
    try:
        if hasattr(ddoc, "pages"):
            p_list = list(getattr(ddoc, "pages"))
            page_count = len(p_list)
            for idx, p in enumerate(p_list, start=1):
                pages.append({"page": idx})
                p_blocks = getattr(p, "blocks", []) or []
                for bi, b in enumerate(p_blocks):
                    text = getattr(b, "text", None) or getattr(b, "content", "")
                    btype = getattr(b, "type", None) or getattr(b, "kind", "paragraph")
                    bbox = getattr(b, "bbox", None)
                    blocks.append(
                        {
                            "block_id": f"p{idx}_b{bi}",
                            "type": str(btype),
                            "text": str(text) if text is not None else "",
                            "page_start": idx,
                            "page_end": idx,
                            "bbox": bbox,
                        }
                    )
        elif hasattr(ddoc, "blocks"):
            b_list = list(getattr(ddoc, "blocks"))
            # try inferring page_count from max page
            max_page = 0
            for bi, b in enumerate(b_list):
                pg = getattr(b, "page", None) or getattr(b, "page_no", None) or 1
                max_page = max(max_page, int(pg))
                text = getattr(b, "text", None) or getattr(b, "content", "")
                btype = getattr(b, "type", None) or getattr(b, "kind", "paragraph")
                bbox = getattr(b, "bbox", None)
                blocks.append(
                    {
                        "block_id": f"b{bi}",
                        "type": str(btype),
                        "text": str(text) if text is not None else "",
                        "page_start": int(pg),
                        "page_end": int(pg),
                        "bbox": bbox,
                    }
                )
            page_count = max_page or None
            pages = [{"page": i} for i in range(1, (page_count or 0) + 1)]
        else:
            raise RuntimeError("Docling document lacks pages/blocks attributes")
    except Exception as e:
        raise RuntimeError(f"Docling canonicalization failed: {e}")

    return pages, blocks, page_count, adapter_used


def _run_docling_or_fallback(src_path: Path, out_dir: Path):
    log: dict = {
        "started_at": _now_iso(),
        "finished_at": None,
        "steps": [],
        "errors": [],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_json = out_dir / "document.json"
    doc_text = out_dir / "document_text.txt"
    doc_meta = out_dir / "meta.json"

    page_count = None
    parse_method = None

    pages = []
    blocks = []

    dl = _try_import_docling()
    if dl is not None:
        # Log docling-related versions to aid diagnosis
        versions: dict[str, Optional[str]] = {"docling": getattr(dl, "__version__", None)}
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

        log["steps"].append({"step": "docling_parse_start", "at": _now_iso(), "versions": versions})
        try:
            pages, blocks, page_count, adapter_used = _try_docling_to_canonical(dl, src_path)
            parse_method = "docling"
            log["steps"].append({"step": "docling_parse_ok", "at": _now_iso(), "page_count": page_count, "adapter": adapter_used})
        except Exception as e:
            log["errors"].append(f"docling_failed: {e}")
            log["steps"].append({"step": "docling_parse_failed", "at": _now_iso()})
    else:
        log["steps"].append({"step": "docling_not_available", "at": _now_iso()})

    if not pages or not blocks:
        # Fallback: PyMuPDF extraction and simple canonicalization
        page_texts, page_count = _extract_with_pymupdf(src_path)
        pages, blocks = _canonical_from_pymupdf(page_texts)
        parse_method = "pymupdf_fallback"
        log["steps"].append({"step": "fallback_pymupdf_ok", "at": _now_iso(), "page_count": page_count})

    # Persist document_text.txt as the concatenation of page texts
    try:
        joined_text = "\n\n".join([b.get("text", "") for b in blocks if b.get("page_start") == b.get("page_end")])
        doc_text.write_text(joined_text, encoding="utf-8")
        log["steps"].append({"step": "wrote_document_text", "at": _now_iso(), "bytes": len(joined_text.encode('utf-8'))})
    except Exception as e:
        log["errors"].append(f"write_text_failed: {e}")

    # Persist canonical document.json
    try:
        _write_json(
            doc_json,
            {
                "schema": "ipdf.document@v1",
                "filename": src_path.name,
                "doc_id": src_path.parent.name,
                "page_count": page_count or (pages[-1]["page"] if pages else None),
                "pages": pages,
                "blocks": blocks,
            },
        )
        log["steps"].append({"step": "wrote_document_json", "at": _now_iso(), "blocks": len(blocks)})
    except Exception as e:
        log["errors"].append(f"write_document_json_failed: {e}")

    log["finished_at"] = _now_iso()

    # Update meta with nuanced status
    meta = _read_json(doc_meta) or {}
    status = (
        DocumentStatus.READY
        if parse_method == "docling" and not log["errors"]
        else (DocumentStatus.PARSED_LOW_CONFIDENCE if parse_method == "pymupdf_fallback" and blocks else DocumentStatus.FAILED_DOCLING)
    )
    meta.update(
        {
            "filename": src_path.name,
            "ingested_at": meta.get("ingested_at") or _now_iso(),
            "status": status,
            "page_count": page_count or len(pages) if pages else None,
            "errors": log["errors"],
            "parse_method": parse_method,
        }
    )
    _write_json(doc_meta, meta)
    _write_json(out_dir / "ingest_log.json", log)

    return log


@app.post("/upload", response_model=DocumentSummary)
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    doc_id = _sha256_bytes(content)
    # Save raw file
    raw_dir = RAW_DIR / doc_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / file.filename
    if not raw_path.exists():
        raw_path.write_bytes(content)

    # Prepare processed meta
    processed_dir = PROCESSED_DIR / doc_id
    processed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = processed_dir / "meta.json"
    _write_json(
        meta_path,
        {
            "filename": file.filename,
            "ingested_at": _now_iso(),
            "status": "PARSING",
            "page_count": None,
            "errors": [],
        },
    )

    # Run ingest synchronously
    _run_docling_or_fallback(raw_path, processed_dir)

    meta = _read_json(meta_path) or {}
    return DocumentSummary(
        doc_id=doc_id,
        filename=meta.get("filename", file.filename),
        status=meta.get("status", "READY"),
        page_count=meta.get("page_count"),
        ingested_at=meta.get("ingested_at"),
        errors=meta.get("errors"),
    )


@app.get("/documents", response_model=List[DocumentSummary])
def list_documents():
    docs: List[DocumentSummary] = []
    seen: set[str] = set()

    if PROCESSED_DIR.exists():
        for pdir in PROCESSED_DIR.iterdir():
            if not pdir.is_dir():
                continue
            meta = _read_json(pdir / "meta.json") or {}
            if meta:
                doc_id = pdir.name
                seen.add(doc_id)
                docs.append(
                    DocumentSummary(
                        doc_id=doc_id,
                        filename=meta.get("filename"),
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


class DocumentDetail(BaseModel):
    doc_id: str
    filename: Optional[str] = None
    status: str
    has_chunks: bool = False
    page_count: Optional[int] = None
    ingested_at: Optional[str] = None
    errors: Optional[list[str]] = None
    links: Optional[dict] = None


@app.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str):
    raw_dir = RAW_DIR / doc_id
    processed_dir = PROCESSED_DIR / doc_id
    if not raw_dir.exists() and not processed_dir.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    meta = _read_json(processed_dir / "meta.json") or {}
    filename = meta.get("filename")
    if not filename and raw_dir.exists():
        files = list(raw_dir.iterdir())
        filename = files[0].name if files else None

    status = meta.get("status", "READY" if processed_dir.exists() else "QUEUED")
    has_chunks = (processed_dir / "chunks.json").exists()

    links = {}
    for name in ["document_text.txt", "document.json", "ingest_log.json", "meta.json"]:
        if (processed_dir / name).exists():
            links[name] = f"/documents/{doc_id}/files/{name}"

    return DocumentDetail(
        doc_id=doc_id,
        filename=filename,
        status=status,
        has_chunks=has_chunks,
        page_count=meta.get("page_count"),
        ingested_at=meta.get("ingested_at"),
        errors=meta.get("errors"),
        links=links or None,
    )


class Chunk(BaseModel):
    id: str
    type: str
    text_preview: str
    section_path: Optional[str] = None
    clause_ref: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


@app.get("/documents/{doc_id}/chunks", response_model=List[Chunk])
def list_chunks(doc_id: str):
    # MVP-0 stub: return empty list (no chunking yet)
    _ = doc_id
    return []


def _safe_file_path(doc_id: str, name: str) -> Path:
    allowed = {"document_text.txt", "document.json", "ingest_log.json", "meta.json"}
    if name not in allowed:
        raise HTTPException(status_code=400, detail="Invalid file name")
    p = PROCESSED_DIR / doc_id / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return p


@app.get("/documents/{doc_id}/files/{name}")
def download_processed_file(doc_id: str, name: str):
    path = _safe_file_path(doc_id, name)
    return FileResponse(path)


@app.post("/search", response_model=List[SearchHit])
def search(req: SearchRequest):
    # MVP-0 stub: return a single mocked hit to exercise UI wiring
    snippet = f"[stub] Results for query: {req.query}"
    evidence = Evidence(
        doc_id=(req.filters.doc_ids[0] if req.filters and req.filters.doc_ids else "stub-doc"),
        section_path="Definitions > Audit",
        clause_ref="1.2",
        page_start=1,
        page_end=1,
    )
    return [SearchHit(score=0.42, snippet=snippet, evidence=evidence)]
