from __future__ import annotations

import re
from typing import Iterable


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def keyword_score(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    t_tokens = _tokenize(text)
    if not t_tokens:
        return 0.0
    t_set = set(t_tokens)
    hits = sum(1 for t in q_tokens if t in t_set)
    return hits / max(len(set(q_tokens)), 1)


def make_snippet(query: str, text: str, max_len: int = 300) -> str:
    if not text:
        return ""
    if not query:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    q = query.strip()
    idx = text.lower().find(q.lower())
    if idx == -1:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    start = max(idx - 80, 0)
    end = min(idx + 220, len(text))
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
