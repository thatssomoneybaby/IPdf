from __future__ import annotations

import os
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)


COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "contract_chunks_v1")


def get_client(url: str) -> QdrantClient:
    return QdrantClient(url=url)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    if client.collection_exists(COLLECTION_NAME):
        info = client.get_collection(COLLECTION_NAME)
        try:
            existing_size = info.config.params.vectors.size  # type: ignore[attr-defined]
            if existing_size != vector_size:
                raise RuntimeError(
                    f"Qdrant collection '{COLLECTION_NAME}' has size={existing_size}, expected {vector_size}"
                )
        except Exception:
            # If we can't read size, don't fail; assume compatible for MVP
            pass
        _ensure_payload_indexes(client)
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    _ensure_payload_indexes(client)


def _ensure_payload_indexes(client: QdrantClient) -> None:
    fields = [
        ("doc_id", PayloadSchemaType.KEYWORD),
        ("type", PayloadSchemaType.KEYWORD),
        ("semantic_type", PayloadSchemaType.KEYWORD),
        ("section_path", PayloadSchemaType.KEYWORD),
        ("clause_ref", PayloadSchemaType.KEYWORD),
        ("page_start", PayloadSchemaType.INTEGER),
        ("page_end", PayloadSchemaType.INTEGER),
    ]
    for field, schema in fields:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            # Index may already exist; ignore for MVP.
            pass


def build_filter(filters: Optional[dict[str, Any]]) -> Optional[Filter]:
    if not filters:
        return None
    must = []
    doc_ids = filters.get("doc_ids")
    if doc_ids and isinstance(doc_ids, list):
        if len(doc_ids) == 1:
            must.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_ids[0])))
        else:
            must.append(FieldCondition(key="doc_id", match=MatchAny(any=doc_ids)))
    if filters.get("type"):
        must.append(FieldCondition(key="type", match=MatchValue(value=filters["type"])))
    # Page filters are applied post-retrieval for overlap correctness.
    if not must:
        return None
    return Filter(must=must)


def payload_matches_filters(payload: dict[str, Any], filters: Optional[dict[str, Any]]) -> bool:
    if not filters:
        return True

    doc_ids = filters.get("doc_ids")
    if doc_ids and payload.get("doc_id") not in doc_ids:
        return False

    if filters.get("type") and payload.get("type") != filters.get("type"):
        return False

    section_contains = filters.get("section_contains")
    if section_contains:
        section_path = payload.get("section_path") or []
        if isinstance(section_path, list):
            haystack = " > ".join(section_path)
        else:
            haystack = str(section_path)
        if section_contains.lower() not in haystack.lower():
            return False

    page_start = filters.get("page_start")
    page_end = filters.get("page_end")
    if page_start or page_end:
        ps = payload.get("page_start")
        pe = payload.get("page_end")
        if ps is None or pe is None:
            return False
        if page_start and pe < page_start:
            return False
        if page_end and ps > page_end:
            return False

    return True
