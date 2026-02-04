from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class DocumentStatus(str):
    AWAITING_OPTIONS = "AWAITING_OPTIONS"
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED_DOCLING = "FAILED_DOCLING"
    FAILED_CHUNKING = "FAILED_CHUNKING"
    FAILED_INDEXING = "FAILED_INDEXING"
    PARSED_LOW_CONFIDENCE = "PARSED_LOW_CONFIDENCE"


class DocumentSummary(BaseModel):
    doc_id: str
    filename: Optional[str] = None
    display_name: Optional[str] = None
    status: str = "QUEUED"
    page_count: Optional[int] = None
    ingested_at: Optional[str] = None
    errors: Optional[list[str]] = None


class ProcessingOptions(BaseModel):
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    run_index: bool = True
    run_definitions: bool = False
    run_entitlements: bool = False
    semantic_enrich: Optional[bool] = None
    ocr_mode: Optional[str] = None  # auto | force | off
    ocr_language: Optional[str] = None


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
    top_k: int = 10


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


class DocumentDetail(BaseModel):
    doc_id: str
    filename: Optional[str] = None
    display_name: Optional[str] = None
    status: str
    has_chunks: bool = False
    page_count: Optional[int] = None
    ingested_at: Optional[str] = None
    errors: Optional[list[str]] = None
    links: Optional[dict] = None
    definitions_status: Optional[str] = None
    entitlements_status: Optional[str] = None
    preflight: Optional[dict] = None
    processing_options: Optional[dict] = None
    stage_message: Optional[str] = None
    parse_method: Optional[str] = None


class Chunk(BaseModel):
    id: str
    type: str
    text_preview: str
    section_path: Optional[str] = None
    clause_ref: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    semantic_type: Optional[str] = None
    semantic_confidence: Optional[float] = None


class FeedbackItem(BaseModel):
    item_type: str  # definitions | entitlements | tables | search
    item_id: Optional[str] = None
    verdict: str  # correct | incorrect | partial
    note: Optional[str] = None
    evidence: Optional[dict] = None
