from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException

from config import PROCESSED_DIR
from models import Evidence, SearchFilter, SearchHit
from storage import read_json


def iter_chunks_from_disk(filters: Optional[SearchFilter]):
    doc_ids = filters.doc_ids if filters else None
    if PROCESSED_DIR.exists():
        for pdir in PROCESSED_DIR.iterdir():
            if not pdir.is_dir():
                continue
            if doc_ids and pdir.name not in doc_ids:
                continue
            chunks_path = pdir / "chunks.json"
            if not chunks_path.exists():
                continue
            data = read_json(chunks_path) or {}
            doc_id = data.get("doc_id") or pdir.name
            for ch in data.get("chunks") or []:
                if "doc_id" not in ch:
                    ch = dict(ch)
                    ch["doc_id"] = doc_id
                yield ch


def chunk_matches_filters(ch: dict, filters: Optional[SearchFilter]) -> bool:
    if not filters:
        return True
    if filters.doc_ids and ch.get("doc_id") not in filters.doc_ids:
        return False
    if filters.type and ch.get("type") != filters.type:
        return False
    if filters.section_contains:
        section_path = ch.get("section_path") or []
        if isinstance(section_path, list):
            haystack = " > ".join(section_path)
        else:
            haystack = str(section_path)
        if filters.section_contains.lower() not in haystack.lower():
            return False
    if filters.page_start or filters.page_end:
        ps = ch.get("page_start")
        pe = ch.get("page_end")
        if ps is None or pe is None:
            return False
        if filters.page_start and pe < filters.page_start:
            return False
        if filters.page_end and ps > filters.page_end:
            return False
    return True


def keyword_search(query: str, filters: Optional[SearchFilter], top_k: int) -> list[SearchHit]:
    from ipdf.search_utils import keyword_score, make_snippet

    scored = []
    for ch in iter_chunks_from_disk(filters):
        if not chunk_matches_filters(ch, filters):
            continue
        text = ch.get("text", "") or ""
        score = keyword_score(query, text)
        if score <= 0:
            continue
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, ch in scored[: top_k or 10]:
        section_path = ch.get("section_path") or []
        section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path)
        results.append(
            SearchHit(
                score=float(score),
                snippet=make_snippet(query, ch.get("text", "") or ""),
                evidence=Evidence(
                    doc_id=ch.get("doc_id", ""),
                    section_path=section_str or None,
                    clause_ref=ch.get("clause_ref"),
                    page_start=ch.get("page_start"),
                    page_end=ch.get("page_end"),
                ),
            )
        )
    return results


def semantic_search(query: str, filters: Optional[SearchFilter], top_k: int) -> list[SearchHit]:
    from ipdf.embeddings import embed_query
    from ipdf.search_utils import make_snippet
    from ipdf.vector_store import COLLECTION_NAME, build_filter, get_client, payload_matches_filters

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    client = get_client(qdrant_url)
    query_vector = embed_query(query, embedding_model)
    qfilter = build_filter(filters.model_dump() if filters else None)
    limit = max(top_k * 5, top_k)
    if filters and (filters.section_contains or filters.page_start or filters.page_end or filters.type or (filters.doc_ids and len(filters.doc_ids) > 1)):
        limit = min(max(top_k * 15, top_k), 300)
    try:
        hits = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=limit,
            with_payload=True,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Semantic search unavailable: {e}")

    results = []
    for h in hits:
        payload = h.payload or {}
        if not payload_matches_filters(payload, filters.model_dump() if filters else None):
            continue
        section_path = payload.get("section_path") or []
        section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path)
        results.append(
            SearchHit(
                score=float(h.score),
                snippet=make_snippet(query, payload.get("text", "") or ""),
                evidence=Evidence(
                    doc_id=payload.get("doc_id", ""),
                    section_path=section_str or None,
                    clause_ref=payload.get("clause_ref"),
                    page_start=payload.get("page_start"),
                    page_end=payload.get("page_end"),
                ),
            )
        )
        if len(results) >= top_k:
            break
    return results


def hybrid_search(query: str, filters: Optional[SearchFilter], top_k: int) -> list[SearchHit]:
    from ipdf.search_utils import keyword_score, make_snippet
    from ipdf.embeddings import embed_query
    from ipdf.vector_store import COLLECTION_NAME, build_filter, get_client, payload_matches_filters

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    client = get_client(qdrant_url)
    query_vector = embed_query(query, embedding_model)
    qfilter = build_filter(filters.model_dump() if filters else None)
    limit = max(top_k * 5, top_k)
    if filters and (filters.section_contains or filters.page_start or filters.page_end or filters.type or (filters.doc_ids and len(filters.doc_ids) > 1)):
        limit = min(max(top_k * 15, top_k), 300)
    try:
        hits = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=limit,
            with_payload=True,
        )
    except Exception:
        return keyword_search(query, filters, top_k)

    if not hits:
        return keyword_search(query, filters, top_k)

    scored = []
    for h in hits:
        payload = h.payload or {}
        if not payload_matches_filters(payload, filters.model_dump() if filters else None):
            continue
        text = payload.get("text", "") or ""
        kw = keyword_score(query, text)
        sem = float(h.score)
        final = 0.65 * sem + 0.35 * kw
        scored.append((final, payload))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for final, payload in scored[: top_k or 10]:
        section_path = payload.get("section_path") or []
        section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path)
        results.append(
            SearchHit(
                score=float(final),
                snippet=make_snippet(query, payload.get("text", "") or ""),
                evidence=Evidence(
                    doc_id=payload.get("doc_id", ""),
                    section_path=section_str or None,
                    clause_ref=payload.get("clause_ref"),
                    page_start=payload.get("page_start"),
                    page_end=payload.get("page_end"),
                ),
            )
        )
    return results
