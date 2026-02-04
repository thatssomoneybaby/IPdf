from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional

DEFAULT_MAX_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    if not text:
        return ""
    txt = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove hyphenation across line breaks: hy-\nphen -> hyphen
    txt = re.sub(r"(\w)-\n(\w)", r"\1\2", txt)
    # Collapse 3+ newlines to 2
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _serialize_table(table: Any) -> str:
    if not table:
        return ""
    rows = table.get("rows") if isinstance(table, dict) else table
    if not rows:
        return ""
    lines = []
    for row in rows:
        if isinstance(row, dict):
            cells = [str(v) for v in row.values()]
        elif isinstance(row, (list, tuple)):
            cells = [str(c) for c in row]
        else:
            cells = [str(row)]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def _clause_ref(text: str) -> tuple[Optional[str], Optional[int]]:
    if not text:
        return None, None
    t = text.strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\b", t)
    if m:
        ref = m.group(1)
        level = ref.count(".") + 1
        return ref, level
    m = re.match(r"^\s*(\d+(?:\.\d+)*)(\([a-zA-Z0-9]+\))*", t)
    if m:
        ref = m.group(1)
        level = ref.count(".") + 1
        return ref, level
    m = re.match(r"^\s*\(?([a-z])\)\s+", t)
    if m:
        return f"({m.group(1)})", 1
    return None, None


def _is_numeric_clause(ref: Optional[str]) -> bool:
    if not ref:
        return False
    return re.match(r"^\d+(?:\.\d+)*$", ref) is not None


def _is_lettered_clause(ref: Optional[str]) -> bool:
    if not ref:
        return False
    return re.match(r"^\([a-z]\)$", ref) is not None


def _looks_like_heading(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) < 2 or len(t) > 120:
        return False
    if t.endswith("."):
        return False

    # Numbered heading: "1.2 Term"
    if re.match(r"^\s*\d+(?:\.\d+)*\s+[A-Z]", t):
        return True

    words = re.findall(r"[A-Za-z]+", t)
    letters = [c for c in t if c.isalpha()]
    caps_ratio = 0.0
    title_ratio = 0.0
    if letters:
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        title_ratio = sum(1 for w in words if w[:1].isupper()) / max(len(words), 1)
        if caps_ratio > 0.8 or title_ratio > 0.8:
            return True

    keywords = {
        "definitions",
        "interpretation",
        "term",
        "audit",
        "fees",
        "schedule",
        "appendix",
        "annex",
        "exhibit",
        "license",
        "restrictions",
        "termination",
        "renewal",
    }
    kw_pattern = r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"
    if re.search(kw_pattern, t.lower()) and (caps_ratio > 0.5 or title_ratio > 0.6):
        return True

    return False


def _heading_level(text: str) -> int:
    if not text:
        return 2
    t = text.strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\b", t)
    if m:
        return m.group(1).count(".") + 1
    if t.isupper():
        return 1
    if t.lower().startswith(("schedule", "appendix", "annex", "exhibit")):
        return 1
    return 2


def _chunk_type(section_path: list[str], clause_ref: Optional[str], is_table: bool, is_heading: bool) -> str:
    if is_heading:
        return "heading"
    if is_table:
        return "table"
    if any("definition" in s.lower() for s in section_path):
        return "definition"
    if clause_ref:
        return "clause"
    return "paragraph"


def _stable_chunk_id(doc_id: str, source_blocks: list[str], text: str) -> str:
    base = "|".join([doc_id] + (source_blocks or []) + [text])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def chunk_document(
    doc: dict[str, Any],
    max_chars: int = DEFAULT_MAX_CHARS,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
) -> dict[str, Any]:
    blocks = doc.get("blocks") or []
    chunked: list[dict[str, Any]] = []

    doc_id = doc.get("doc_id") or (doc.get("source") or {}).get("sha256") or "unknown"
    section_stack: list[tuple[int, str]] = []
    current: Optional[dict[str, Any]] = None
    range_start = int(page_start) if page_start else None
    range_end = int(page_end) if page_end else None

    def in_range(block: dict[str, Any]) -> bool:
        if range_start is None and range_end is None:
            return True
        b_start = block.get("page_start") or block.get("page") or block.get("page_no")
        b_end = block.get("page_end") or b_start
        try:
            b_start = int(b_start) if b_start is not None else None
        except Exception:
            b_start = None
        try:
            b_end = int(b_end) if b_end is not None else None
        except Exception:
            b_end = None
        if b_start is None and b_end is None:
            return True
        if range_start is not None and b_end is not None and b_end < range_start:
            return False
        if range_end is not None and b_start is not None and b_start > range_end:
            return False
        return True

    def current_section_path() -> list[str]:
        return [h for _lvl, h in section_stack]

    def flush_current():
        nonlocal current
        if not current:
            return
        text = normalize_text("\n\n".join(current["texts"]))
        if not text:
            current = None
            return
        clause_ref, clause_level = current.get("clause_ref"), current.get("clause_level")
        section_path = current.get("section_path", [])
        ctype = _chunk_type(section_path, clause_ref, current.get("is_table", False), current.get("is_heading", False))
        chunk_id = _stable_chunk_id(doc_id, current.get("source_blocks") or [], text)
        chunked.append(
            {
                "chunk_id": chunk_id,
                "type": ctype,
                "text": text,
                "tokens_est": len(text.split()),
                "char_len": len(text),
                "page_start": current["page_start"],
                "page_end": current["page_end"],
                "section_path": section_path,
                "heading": current.get("heading"),
                "clause_ref": clause_ref,
                "clause_level": clause_level,
                "source_blocks": current["source_blocks"],
                "bbox": current["bbox"],
                "table": current.get("table"),
            }
        )
        current = None

    def start_chunk(block: dict[str, Any], text: str, is_table: bool, is_heading: bool):
        nonlocal current
        clause_ref, clause_level = _clause_ref(text)
        current = {
            "texts": [text],
            "page_start": block.get("page_start"),
            "page_end": block.get("page_end"),
            "section_path": current_section_path(),
            "heading": current_section_path()[-1] if current_section_path() else None,
            "clause_ref": clause_ref,
            "clause_level": clause_level,
            "source_blocks": [block.get("block_id")],
            "bbox": [block.get("bbox")] if block.get("bbox") is not None else [],
            "is_table": is_table,
            "is_heading": is_heading,
            "table": block.get("table") if is_table else None,
        }

    skip_types = {"header", "footer"}

    for block in blocks:
        if not in_range(block):
            continue
        btype = str(block.get("type") or "").lower()
        if btype in skip_types:
            continue

        is_table = btype == "table" or bool(block.get("table"))
        text = normalize_text(str(block.get("text") or ""))
        if is_table and not text:
            text = normalize_text(_serialize_table(block.get("table")))
        if not text and not is_table:
            continue

        is_heading = btype == "heading" or _looks_like_heading(text)

        if is_heading:
            flush_current()
            level = _heading_level(text)
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, text))
            # Store heading as its own chunk
            start_chunk(block, text, is_table=False, is_heading=True)
            flush_current()
            continue

        if is_table:
            flush_current()
            start_chunk(block, text, is_table=True, is_heading=False)
            flush_current()
            continue

        if current is None:
            start_chunk(block, text, is_table=False, is_heading=False)
            continue

        # Decide whether to start a new chunk
        next_clause_ref, _next_clause_level = _clause_ref(text)
        if current.get("clause_ref") and next_clause_ref and next_clause_ref != current.get("clause_ref"):
            if _is_lettered_clause(next_clause_ref) and _is_numeric_clause(current.get("clause_ref")):
                pass
            elif _is_lettered_clause(next_clause_ref) and _is_lettered_clause(current.get("clause_ref")):
                pass
            else:
                flush_current()
                start_chunk(block, text, is_table=False, is_heading=False)
                continue

        prospective_len = sum(len(t) for t in current["texts"]) + len(text)
        if prospective_len > max_chars:
            flush_current()
            start_chunk(block, text, is_table=False, is_heading=False)
            continue

        # Merge into current chunk
        current["texts"].append(text)
        current["page_start"] = min(current["page_start"], block.get("page_start")) if current["page_start"] else block.get("page_start")
        current["page_end"] = max(current["page_end"], block.get("page_end")) if current["page_end"] else block.get("page_end")
        current["source_blocks"].append(block.get("block_id"))
        if block.get("bbox") is not None:
            current["bbox"].append(block.get("bbox"))
        if current.get("clause_ref") is None and next_clause_ref:
            current["clause_ref"] = next_clause_ref

    flush_current()

    return {
        "doc_id": doc.get("doc_id"),
        "chunked_at": _now_iso(),
        "chunking": {"version": "v1", "ruleset": "2026-01", "page_start": range_start, "page_end": range_end},
        "chunks": chunked,
    }


def chunk_debug_markdown(chunked: dict[str, Any]) -> str:
    chunks = chunked.get("chunks") or []
    lines: list[str] = []
    lines.append("# Chunk Debug")
    lines.append("")
    lines.append(f"Generated at: {_now_iso()}")
    lines.append("")

    for idx, ch in enumerate(chunks, start=1):
        page_start = ch.get("page_start")
        page_end = ch.get("page_end")
        section_path = ch.get("section_path") or []
        if isinstance(section_path, list):
            section_str = " > ".join(section_path)
        else:
            section_str = str(section_path)

        lines.append(f"## {idx}. {ch.get('type','chunk')} — p.{page_start}-{page_end}")
        lines.append(f"chunk_id: `{ch.get('chunk_id')}`")
        lines.append(f"section_path: {section_str or '—'}")
        lines.append(f"clause_ref: `{ch.get('clause_ref') or '—'}`")
        lines.append(f"source_blocks: {', '.join(ch.get('source_blocks') or [])}")
        lines.append("")
        lines.append("```text")
        lines.append(ch.get("text", "") or "")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
