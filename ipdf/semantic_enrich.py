from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List

from .embeddings import embed_texts


LABELS: Dict[str, List[str]] = {
    "definition": [
        "definitions section",
        "\"term\" means",
        "defined terms",
    ],
    "entitlement": [
        "licensed programs",
        "schedule of products",
        "order form entitlements",
        "license metric quantity",
    ],
    "audit": [
        "audit rights",
        "inspection and compliance",
        "records review",
    ],
    "license_grant": [
        "license grant",
        "grant of rights",
        "permitted use",
    ],
    "restriction": [
        "restrictions",
        "limitations of use",
        "prohibited actions",
    ],
    "term": [
        "term and termination",
        "renewal and expiration",
        "termination for cause",
    ],
    "other": [
        "general clause",
    ],
}


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


@lru_cache(maxsize=2)
def _label_vectors(model_name: str) -> Dict[str, List[float]]:
    label_vecs: Dict[str, List[float]] = {}
    for label, phrases in LABELS.items():
        embs = embed_texts(phrases, model_name)
        if not embs:
            continue
        # average + normalize
        dims = len(embs[0])
        avg = [0.0] * dims
        for e in embs:
            for i in range(dims):
                avg[i] += e[i]
        avg = [v / len(embs) for v in avg]
        label_vecs[label] = _normalize(avg)
    return label_vecs


def infer_semantic_labels(embeddings: List[List[float]], model_name: str) -> List[dict]:
    label_vecs = _label_vectors(model_name)
    labels = list(label_vecs.keys())
    vectors = [label_vecs[l] for l in labels]

    results = []
    for emb in embeddings:
        best_label = "other"
        best_score = -1.0
        for lbl, vec in zip(labels, vectors):
            score = sum(e * v for e, v in zip(emb, vec))
            if score > best_score:
                best_score = score
                best_label = lbl
        confidence = (best_score + 1.0) / 2.0
        results.append({"semantic_type": best_label, "semantic_confidence": confidence})
    return results
