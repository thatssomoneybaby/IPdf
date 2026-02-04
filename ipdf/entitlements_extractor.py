from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


HEADER_MAP = {
    "program": "product",
    "product": "product",
    "service": "product",
    "licensed program": "product",
    "item": "product",
    "metric": "metric",
    "license metric": "metric",
    "measure": "metric",
    "qty": "quantity",
    "quantity": "quantity",
    "units": "quantity",
    "number": "quantity",
    "term": "term",
    "subscription term": "term",
    "start": "term",
    "end": "term",
    "territory": "territory",
    "region": "territory",
    "restriction": "restrictions",
    "restrictions": "restrictions",
    "limitations": "restrictions",
    "notes": "restrictions",
    "sku": "sku",
    "part": "sku",
    "item code": "sku",
    "csi": "csi",
    "support id": "csi",
    "price": "price",
    "rate": "price",
    "total": "price",
}


REF_KEYWORDS = [
    "order form",
    "ordering document",
    "sow",
    "statement of work",
    "schedule",
    "ordering",
    "order",
]


def _normalize_header(cell: str) -> str:
    c = re.sub(r"\s+", " ", cell.strip().lower())
    return HEADER_MAP.get(c, c)


def _row_to_cells(row: Any) -> list[str]:
    if isinstance(row, dict):
        return [str(v) for v in row.values()]
    if isinstance(row, (list, tuple)):
        return [str(c) for c in row]
    return [str(row)]


def _table_rows_from_chunk(chunk: dict[str, Any]) -> list[list[str]]:
    table = chunk.get("table")
    if table:
        rows = table.get("rows") if isinstance(table, dict) else table
        if rows:
            return [ _row_to_cells(r) for r in rows ]
    # fallback to parse text lines
    text = chunk.get("text") or ""
    rows = []
    for line in text.splitlines():
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            rows.append([p for p in parts if p])
        else:
            rows.append([line.strip()])
    return [r for r in rows if any(c for c in r)]


def _detect_header_row(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    if not rows:
        return [], []
    def header_score(row: list[str]) -> int:
        score = 0
        for cell in row:
            if not cell:
                continue
            c = cell.lower()
            if any(k in c for k in HEADER_MAP.keys()):
                score += 1
        return score

    if len(rows) >= 1 and header_score(rows[0]) >= 2:
        return rows[0], rows[1:]
    if len(rows) >= 2 and header_score(rows[1]) > header_score(rows[0]):
        return rows[1], rows[2:]
    # No header row
    header = [f"col_{i+1}" for i in range(max(len(r) for r in rows))]
    return header, rows


def _classify_table(headers: list[str]) -> str:
    h = " ".join(headers).lower()
    if "metric" in h and ("program" in h or "product" in h):
        return "licensed_programs"
    if "price" in h or "rate" in h or "total" in h:
        return "pricing"
    if "support" in h or "csi" in h:
        return "support"
    return "unknown"


def _normalize_rows(headers: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    norm_headers = [_normalize_header(h) for h in headers]
    normalized = []
    for row in rows:
        row_cells = row + [""] * (len(norm_headers) - len(row))
        item = {}
        for idx, cell in enumerate(row_cells[: len(norm_headers)]):
            key = norm_headers[idx]
            item[key] = cell.strip()
        if any(v for v in item.values()):
            normalized.append(item)
    return normalized


def _parse_quantity(value: str) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"\d+", value.replace(",", ""))
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def extract_entitlements(chunked: dict[str, Any]) -> dict[str, Any]:
    chunks = chunked.get("chunks") or []
    doc_id = chunked.get("doc_id")

    tables = []
    products = []
    references = []

    for ch in chunks:
        if ch.get("type") != "table" and not ch.get("table"):
            continue
        rows = _table_rows_from_chunk(ch)
        headers, data_rows = _detect_header_row(rows)
        table_type = _classify_table(headers)
        normalized_rows = _normalize_rows(headers, data_rows)

        tables.append(
            {
                "title": ch.get("heading") or (ch.get("section_path")[-1] if ch.get("section_path") else None),
                "table_type": table_type,
                "headers": headers,
                "rows": normalized_rows,
                "confidence": 0.8 if table_type != "unknown" else 0.6,
                "evidence": [
                    {
                        "chunk_id": ch.get("chunk_id"),
                        "page_start": ch.get("page_start"),
                        "page_end": ch.get("page_end"),
                    }
                ],
            }
        )

        for row in normalized_rows:
            name = row.get("product") or row.get("program") or row.get("service")
            metric = row.get("metric")
            quantity_raw = row.get("quantity")
            quantity = _parse_quantity(quantity_raw or "")
            if not name:
                name = row.get("col_1")
            if not metric:
                col2 = row.get("col_2")
                if col2 and re.search(r"[A-Za-z]", col2):
                    metric = col2
            if not quantity_raw:
                col2 = row.get("col_2")
                col3 = row.get("col_3")
                if col2 and re.search(r"\d", col2) and not metric:
                    quantity_raw = col2
                    quantity = _parse_quantity(quantity_raw)
                elif col3 and re.search(r"\d", col3):
                    quantity_raw = col3
                    quantity = _parse_quantity(quantity_raw)
            if not name:
                continue
            confidence = 0.6
            if metric:
                confidence += 0.1
            if quantity is not None:
                confidence += 0.1
            products.append(
                {
                    "name": name,
                    "metric": metric,
                    "quantity": quantity or quantity_raw,
                    "unit": metric,
                    "term": row.get("term"),
                    "territory": row.get("territory"),
                    "restrictions": [row.get("restrictions")] if row.get("restrictions") else [],
                    "source": "table",
                    "confidence": min(confidence, 0.95),
                    "evidence": [
                        {
                            "chunk_id": ch.get("chunk_id"),
                            "page_start": ch.get("page_start"),
                            "page_end": ch.get("page_end"),
                        }
                    ],
                }
            )

    # References if no entitlements found
    if not products:
        for ch in chunks:
            text = (ch.get("text") or "").lower()
            if any(k in text for k in REF_KEYWORDS):
                references.append(
                    {
                        "ref_type": "ordering_document",
                        "ref_text": (ch.get("text") or "")[:240],
                        "confidence": 0.6,
                        "evidence": [
                            {
                                "chunk_id": ch.get("chunk_id"),
                                "page_start": ch.get("page_start"),
                                "page_end": ch.get("page_end"),
                                "snippet": (ch.get("text") or "")[:240],
                            }
                        ],
                    }
                )

    status = "OK" if products else "NO_ENTITLEMENTS_FOUND_IN_DOCUMENT"

    return {
        "doc_id": doc_id,
        "extracted_at": _now_iso(),
        "pipeline": {"version": "v1", "ruleset": "2026-01"},
        "entitlements": {
            "status": status,
            "tables": tables,
            "products": products,
            "references": references,
        },
    }


def write_entitlements_csv(path: Path, doc_id: str, products: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["doc_id", "product_name", "metric", "quantity", "unit", "term", "restrictions", "page_start"])
        for p in products:
            ev = (p.get("evidence") or [{}])[0]
            writer.writerow(
                [
                    doc_id,
                    p.get("name"),
                    p.get("metric"),
                    p.get("quantity"),
                    p.get("unit"),
                    p.get("term"),
                    "; ".join(p.get("restrictions") or []),
                    ev.get("page_start"),
                ]
            )


def update_review_pack(path: Path, entitlements: dict[str, Any]) -> None:
    header = "## Entitlements & Schedules"
    lines = [header, ""]
    if entitlements.get("status") != "OK":
        lines.append(f"**Status:** {entitlements.get('status')}")
        lines.append("")

    tables = entitlements.get("tables") or []
    for t in tables:
        lines.append(f"### {t.get('title') or 'Table'}")
        headers = t.get("headers") or []
        if headers:
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in t.get("rows") or []:
                row_cells = [row.get(_normalize_header(h), "") for h in headers]
                row_cells = [str(c).replace("|", "\\|") for c in row_cells]
                lines.append("| " + " | ".join(row_cells) + " |")
        lines.append("")

    products = entitlements.get("products") or []
    if products:
        lines.append("### Normalized Products")
        lines.append("| Product | Metric | Qty | Term |")
        lines.append("| --- | --- | --- | --- |")
        for p in products:
            lines.append(
                f"| {p.get('name')} | {p.get('metric') or '—'} | {p.get('quantity') or '—'} | {p.get('term') or '—'} |"
            )
        lines.append("")

    section = "\n".join(lines) + "\n"
    if not path.exists():
        path.write_text("# Review Pack\n\n" + section, encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8")
    if header in content:
        before, rest = content.split(header, 1)
        next_idx = rest.find("\n## ")
        if next_idx != -1:
            after = rest[next_idx + 1 :]
            content = before + section + "\n" + after
        else:
            content = before + section
    else:
        content = content.rstrip() + "\n\n" + section
    path.write_text(content, encoding="utf-8")
