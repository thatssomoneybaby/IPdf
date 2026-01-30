

# Stage 3.1 — Chunking & sectionization

## Goal
Transform Stage 1 `document.json` blocks into **contract-aware chunks** that are:
- Stable and reproducible
- Large enough to carry meaning (semantic search + extraction)
- Small enough to be precise and evidence-friendly
- Rich in metadata (section path, clause refs, page range, block provenance)

Chunking is the foundation for:
- Stage 2 search quality (vector similarity + filters)
- Stage 3 extraction templates (definitions/entitlements/terms)

---

## Inputs
- `storage/processed/<doc_id>/document.json`
  - `pages[]`
  - `blocks[]` with:
    - `block_id`, `type`, `text`, `page_start/page_end`, optional `bbox`

---

## Outputs

### 1) `chunks.json`

```json
{
  "doc_id": "<sha256>",
  "chunked_at": "2026-01-29T...",
  "chunking": {"version": "v1", "ruleset": "2026-01"},
  "chunks": [
    {
      "chunk_id": "<uuid>",
      "type": "heading|definition|clause|schedule|table|paragraph|unknown",
      "text": "...",
      "tokens_est": 0,
      "char_len": 0,
      "page_start": 1,
      "page_end": 2,
      "section_path": ["Schedule A", "Definitions"],
      "heading": "Definitions",
      "clause_ref": "1.1",
      "clause_level": 2,
      "source_blocks": ["block_id_1", "block_id_2"],
      "bbox": [{"page": 1, "x0": 0, "y0": 0, "x1": 0, "y1": 0}]
    }
  ]
}
```

### 2) `chunk_debug.md` (optional)
A human-readable log that shows:
- each chunk
- its metadata
- which blocks it came from
- why boundaries were chosen

---

## Core concepts

### Block vs Chunk
- **Block**: Docling extraction unit (layout-driven)
- **Chunk**: our contract-aware unit used for search + extraction

### Sectionization
We create a **section stack** as we walk blocks in order:
- headings push onto stack
- heading level changes pop/push

This creates `section_path` for every chunk.

---

## Ordering guarantees

### Rule 1 — Preserve Docling order
We process blocks in the order they appear in `document.json`.

### Rule 2 — Ignore noise blocks
We skip or downweight these block types (configurable):
- `header`, `footer` (unless they contain critical identifiers)
- repeated page numbers
- watermarks

We keep the originals in `document.json`; we just don’t chunk them by default.

---

## Heading detection

### Primary signal
Use `block.type == heading` when provided.

### Secondary signals (fallback)
If heading blocks are missing or unreliable, infer headings using heuristics:
- line is short (< 120 chars)
- high title-case ratio OR all-caps ratio
- ends without a period
- matches common section names (Definitions, Term, Audit, Fees, Schedule, Appendix)
- looks like numbered heading: `^\s*\d+(?:\.\d+)*\s+[A-Z]`

### Heading levels (v1)
Assign a simple heading level:
- Level 1: all-caps or starts at “1 ” / “1.” at far left
- Level 2: “1.1 …”
- Level 3: “1.1.1 …”

We only need levels to maintain a sane `section_path`.

---

## Clause reference extraction

### Clause ref regexes (v1)
We extract from the start of the chunk text:
- Numeric: `^\s*(\d+(?:\.\d+)*)\b` → 1, 1.1, 2.3.4
- Numeric + parens: `^\s*(\d+(?:\.\d+)*)(\([a-zA-Z0-9]+\))*` → 2.3(a)
- Lettered: `^\s*\(?([a-z])\)\s+` → (a), (b)

Store:
- `clause_ref` as a display string
- `clause_level` as count of dot segments (1.1.1 = 3)

---

## Chunk boundary rules (v1)

### Hard boundaries
Always start a new chunk when we hit:
- a heading
- a table block
- a page break **only** if we’re already near max size

### Soft boundaries
Prefer a new chunk when:
- clause numbering resets (e.g., 1.9 → 2.1)
- we detect a new sub-clause pattern
- we see a “list run” begin (multiple list items)

### Merge rules
We merge consecutive non-heading blocks into the current chunk until:
- `MAX_CHARS` exceeded (default 2000)
- `MAX_LIST_ITEMS` exceeded (default 12)
- section_path changes
- a new clause_ref begins and current chunk already has a clause_ref

Defaults are tuned for:
- good semantic retrieval
- readable reviewer snippets

---

## List handling

### Preserve numbering
- Keep list numbering/bullets in text.
- Normalize whitespace.

### List chunking strategy
- If a clause contains a long list, keep it together up to size limits.
- If it exceeds limits, split by list item boundaries, but keep `clause_ref` and `section_path`.

---

## Table handling

### One table = one chunk
Tables are always stored as their own chunks:
- `type = table`
- `text` becomes a readable serialization (pipe table or TSV)
- raw rows remain in `table.rows`

### Table title linking
If a heading immediately precedes a table:
- attach `heading` and `section_path` to the table chunk

---

## Normalization

### Text normalization (v1)
- collapse 3+ newlines to 2
- trim trailing spaces
- remove hyphenation across line breaks: `hy-\nphen` → `hyphen`

### Safety rules
- Never remove content that changes legal meaning.
- Keep punctuation.
- Keep quoted terms intact.

---

## Quality targets

### Chunk sizes
- Median chunk length: 700–1500 chars
- 95% chunks < 2500 chars

### Evidence
- 100% chunks include `page_start/page_end`
- 100% chunks include `source_blocks[]`

### Sections
- `section_path` should reflect contract structure for major headings.

---

## Testing approach

### Golden set checks
For 10 representative contracts:
- chunks created
- tables become table chunks
- definitions section produces chunks with section_path containing “Definitions”
- clause_ref extraction rate > 70% for numbered contracts

### Debugging tools
- `chunk_debug.md` for 3 sample docs
- ability to print chunk boundary reasons in logs

---

## Interfaces

### CLI
- `ipdf chunk <doc_id>`
  - reads `document.json`
  - writes `chunks.json`

### Python API
- `chunk_document(canonical_doc) -> ChunkedDocument`

---

## Definition of done
Stage 3.1 is complete when:
- `chunks.json` is produced deterministically for the golden set.
- Search (Stage 2) improves noticeably vs raw blocks.
- Definitions + schedules become clearly navigable via `section_path` and `type`.
- Chunk evidence is complete (pages + source blocks).

---

## Next stage hook
Stage 3.2 will implement the first extractor template (Definitions) **on top of chunks**.