from __future__ import annotations

import os
from typing import Any, Iterable

import uuid

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from .embeddings import embed_texts
from .vector_store import COLLECTION_NAME, ensure_collection, get_client


def index_chunks(
    chunked: dict[str, Any],
    qdrant_url: str,
    embedding_model: str,
    semantic_enrich: bool = False,
) -> tuple[int, dict[str, Any]]:
    chunks = chunked.get("chunks") or []
    if not chunks:
        return 0

    texts = [c.get("text", "") or "" for c in chunks]
    embeddings = embed_texts(texts, embedding_model)
    if not embeddings:
        return 0

    vector_size = len(embeddings[0])
    client = get_client(qdrant_url)
    ensure_collection(client, vector_size)

    doc_id = chunked.get("doc_id")
    if doc_id:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        )

    semantic_labels = None
    if semantic_enrich:
        from .semantic_enrich import infer_semantic_labels

        semantic_labels = infer_semantic_labels(embeddings, embedding_model)

    points = []
    for idx, ch in enumerate(chunks):
        chunk_id = ch.get("chunk_id")
        try:
            uuid.UUID(str(chunk_id))
        except Exception:
            # Ensure Qdrant-compatible UUIDs even for legacy chunks.
            base = "|".join([str(doc_id)] + (ch.get("source_blocks") or []) + [ch.get("text", "") or ""])
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, base))
            ch["chunk_id"] = chunk_id
        if semantic_labels:
            ch["semantic_type"] = semantic_labels[idx]["semantic_type"]
            ch["semantic_confidence"] = semantic_labels[idx]["semantic_confidence"]
        payload = {
            "doc_id": chunked.get("doc_id"),
            "type": ch.get("type"),
            "section_path": ch.get("section_path"),
            "clause_ref": ch.get("clause_ref"),
            "page_start": ch.get("page_start"),
            "page_end": ch.get("page_end"),
            "text": ch.get("text"),
            "heading": ch.get("heading"),
            "embedding_model": embedding_model,
            "embedding_dim": vector_size,
            "semantic_type": ch.get("semantic_type"),
            "semantic_confidence": ch.get("semantic_confidence"),
        }
        points.append(PointStruct(id=chunk_id, vector=embeddings[idx], payload=payload))

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points), chunked
