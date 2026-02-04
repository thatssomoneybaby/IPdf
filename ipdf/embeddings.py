from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List


@lru_cache(maxsize=2)
def _get_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: Iterable[str], model_name: str) -> List[list[float]]:
    model = _get_model(model_name)
    embeddings = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


def embed_query(query: str, model_name: str) -> list[float]:
    return embed_texts([query], model_name)[0]
