from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFINITION_KEYWORDS = {"definitions", "definition", "interpretation", "defined terms"}


def _in_definitions_section(section_path: Any) -> bool:
    if not section_path:
        return False
    if isinstance(section_path, list):
        haystack = " > ".join(section_path)
    else:
        haystack = str(section_path)
    return any(k in haystack.lower() for k in DEFINITION_KEYWORDS)


def _normalize_term(term: str) -> str:
    t = term.strip().strip('"').strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _clean_definition(defn: str) -> str:
    d = defn.strip()
    d = re.sub(r"\s+", " ", d)
    return d


def _make_snippet(text: str, term: str, max_len: int = 240) -> str:
    if not text:
        return ""
    idx = text.lower().find(term.lower())
    if idx == -1:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    start = max(idx - 80, 0)
    end = min(idx + 200, len(text))
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _extract_matches(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    kw = r"(?:means|shall mean|has the meaning|is defined as)"
    quoted = re.compile(
        rf"\"(?P<term>[^\"]{{1,80}})\"\s+{kw}\s+(?P<def>.+?)(?=(?:\n\s*\"[^\"]{{1,80}}\"\s+{kw})|(?:\n\s*[A-Z][A-Za-z0-9\- ]{{1,80}}\s+{kw})|(?:\n\s*\d+(?:\.\d+)*\b)|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    unquoted = re.compile(
        rf"(?P<term>[A-Z][A-Za-z0-9\- ]{{1,80}})\s+{kw}\s+(?P<def>.+?)(?=(?:\n\s*\"[^\"]{{1,80}}\"\s+{kw})|(?:\n\s*[A-Z][A-Za-z0-9\- ]{{1,80}}\s+{kw})|(?:\n\s*\d+(?:\.\d+)*\b)|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    term_colon = re.compile(
        r"^\s*(?P<term>[A-Z][A-Za-z0-9\- ]{1,80})\s*:\s*(?P<def>.+?)(?=(?:\n\s*[A-Z][A-Za-z0-9\- ]{1,80}\s*:)|(?:\n\s*\d+(?:\.\d+)*\b)|$)",
        flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )

    matches: list[dict[str, str]] = []
    for m in quoted.finditer(text):
        matches.append({"term": m.group("term"), "def": m.group("def"), "pattern": "quoted"})
    for m in unquoted.finditer(text):
        matches.append({"term": m.group("term"), "def": m.group("def"), "pattern": "unquoted"})
    for m in term_colon.finditer(text):
        matches.append({"term": m.group("term"), "def": m.group("def"), "pattern": "colon"})
    return matches


def _confidence(pattern: str, in_defs: bool, term: str, definition: str) -> float:
    score = 0.5
    if in_defs:
        score += 0.2
    if pattern == "quoted":
        score += 0.2
    if len(definition) > 20:
        score += 0.1
    if len(term) > 80 or len(definition) < 10:
        score -= 0.2
    return max(0.0, min(1.0, score))


def extract_definitions(chunked: dict[str, Any]) -> dict[str, Any]:
    chunks = chunked.get("chunks") or []
    doc_id = chunked.get("doc_id")

    # Candidate selection
    candidates = []
    for ch in chunks:
        if _in_definitions_section(ch.get("section_path")):
            candidates.append(ch)

    if len(candidates) < 5:
        # Fallback to any chunk containing definition indicators
        indicators = (" means ", " shall mean ", " has the meaning ", " is defined as ")
        for ch in chunks:
            text = (ch.get("text") or "").lower()
            if any(i in text for i in indicators):
                candidates.append(ch)

    # Cap for safety
    candidates = candidates[:250]

    definitions = []
    seen = {}
    for ch in candidates:
        text = ch.get("text") or ""
        in_defs = _in_definitions_section(ch.get("section_path"))
        for match in _extract_matches(text):
            term = _normalize_term(match["term"])
            definition = _clean_definition(match["def"])
            if not term or not definition:
                continue
            if len(term) > 80 or "\n" in term:
                continue
            conf = _confidence(match["pattern"], in_defs, term, definition)
            evidence = {
                "chunk_id": ch.get("chunk_id"),
                "page_start": ch.get("page_start"),
                "page_end": ch.get("page_end"),
                "clause_ref": ch.get("clause_ref"),
                "snippet": _make_snippet(text, term),
            }
            item = {
                "term": term,
                "definition": definition,
                "confidence": conf,
                "location": {
                    "section_path": ch.get("section_path"),
                    "clause_ref": ch.get("clause_ref"),
                },
                "evidence": [evidence],
            }
            norm = term.lower()
            if norm in seen:
                # Keep higher confidence
                if conf > seen[norm]["confidence"]:
                    seen[norm] = item
            else:
                seen[norm] = item

    definitions = list(seen.values())
    definitions.sort(key=lambda d: d["term"].lower())

    return {
        "doc_id": doc_id,
        "extracted_at": _now_iso(),
        "pipeline": {"version": "v1", "ruleset": "2026-01"},
        "definitions": definitions,
    }


def write_definitions_csv(path: Path, doc_id: str, definitions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["doc_id", "term", "definition", "confidence", "page_start", "clause_ref", "section_path"])
        for d in definitions:
            evidence = (d.get("evidence") or [{}])[0]
            section_path = d.get("location", {}).get("section_path")
            if isinstance(section_path, list):
                section_path = " > ".join(section_path)
            writer.writerow(
                [
                    doc_id,
                    d.get("term"),
                    d.get("definition"),
                    d.get("confidence"),
                    evidence.get("page_start"),
                    evidence.get("clause_ref"),
                    section_path,
                ]
            )


def update_review_pack(path: Path, definitions: list[dict[str, Any]]) -> None:
    header = "## Definitions"
    lines = [header, "", "| Term | Definition | Page | Clause |", "| --- | --- | --- | --- |"]
    for d in definitions:
        ev = (d.get("evidence") or [{}])[0]
        page = ev.get("page_start")
        clause = ev.get("clause_ref") or "—"
        term = (d.get("term") or "").replace("|", "\\|")
        definition = (d.get("definition") or "").replace("|", "\\|")
        lines.append(f"| {term} | {definition} | {page or '—'} | {clause} |")
    section = "\n".join(lines) + "\n"

    if not path.exists():
        path.write_text("# Review Pack\n\n" + section, encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8")
    if header in content:
        # Replace existing Definitions section
        before, rest = content.split(header, 1)
        # Find next section header
        next_idx = rest.find("\n## ")
        if next_idx != -1:
            after = rest[next_idx + 1 :]
            content = before + section + "\n" + after
        else:
            content = before + section
    else:
        content = content.rstrip() + "\n\n" + section
    path.write_text(content, encoding="utf-8")
