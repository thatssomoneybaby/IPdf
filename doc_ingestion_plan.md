

# Stage 1 — Document ingestion & extraction (Docling)

## Goal
Turn contracts (PDF/DOCX/HTML) into **high-quality, structured text** that preserves:
- Reading order (columns, headers/footers handled)
- Headings and section boundaries
- Lists and numbering
- Tables (as tables, not scrambled text)
- Page references so reviewers can verify sources

This stage produces a **canonical, reproducible document JSON** that downstream stages (chunking, search, extraction) can rely on.

---

## What we require from Docling

### Input formats
We will support these inputs at minimum:
- PDF (scanned + digital where possible)
- DOCX
- HTML (optional v1)

**Docling is the primary parser.** If a file fails, we will fall back to a secondary parser (e.g., Unstructured) later — but Docling is the baseline.

### Output structure
For every ingested document, Docling must produce:

1) **Plain text** (for quick viewing)
- `document_text.txt`

2) **Structured representation** (canonical)
- `document.json` (our canonical schema; see below)

3) **Evidence mapping**
- Each extracted block must retain at least:
  - `page_start`, `page_end` (or equivalent)
  - `source_span` / `bbox` / offsets if available
  - `section_path` (best-effort: e.g., `Schedule A > Definitions > 1.1`)

4) **Tables preserved**
- Tables must be exported in structured form:
  - row/column structure
  - cell text
  - page reference

5) **Deterministic re-runs**
- Same input file (same bytes) should yield the same output.
- We will version the pipeline config so changes are trackable.

---

## Pipeline responsibilities (our code)

### A. File intake
- Accept upload (later via web UI) and/or local CLI ingest.
- Compute file fingerprint:
  - `sha256`
  - original filename
  - file size
- Store the original file as immutable input:
  - `storage/raw/<sha256>/<original_name>`

### B. Run Docling extraction
- Produce a Docling extraction result per file.
- Capture:
  - tool version
  - run timestamp
  - runtime metrics (duration)
  - any warnings/errors

### C. Normalize into our canonical document schema
Docling’s native output may change over time. We normalize into our own schema so downstream stages are stable.

**Canonical schema (v1)**

```json
{
  "doc_id": "<sha256>",
  "source": {
    "filename": "...",
    "sha256": "...",
    "size_bytes": 123,
    "ingested_at": "2026-01-29T...",
    "parser": {
      "name": "docling",
      "version": "...",
      "config": {"...": "..."}
    }
  },
  "pages": [
    {"page": 1, "width": 0, "height": 0},
    {"page": 2, "width": 0, "height": 0}
  ],
  "blocks": [
    {
      "block_id": "<uuid>",
      "type": "heading|paragraph|list_item|table|footer|header|unknown",
      "text": "...",
      "page_start": 1,
      "page_end": 1,
      "section_path": ["Schedule A", "Definitions"],
      "clause_ref": "1.1" ,
      "bbox": [{"page": 1, "x0": 0, "y0": 0, "x1": 0, "y1": 0}],
      "table": {
        "rows": [["cell", "cell"], ["cell", "cell"]]
      }
    }
  ]
}
```

Notes:
- `bbox` is optional; we include it if Docling provides it.
- `clause_ref` is best-effort and will be refined in the chunking stage.

### D. Persist outputs
Write outputs under:
- `storage/processed/<sha256>/document.json`
- `storage/processed/<sha256>/document_text.txt`
- `storage/processed/<sha256>/docling_raw.json` (optional for debugging)
- `storage/processed/<sha256>/ingest_log.json`

---

## Quality targets (must hit before moving on)

### Text order
- Headings should appear before their content.
- Multi-column PDFs should be in correct reading order.

### Headings & sections
- Major headings (e.g., “Definitions”, “Term”, “Audit”) must be captured as headings blocks.
- Section boundaries must be inferable via `section_path` and heading blocks.

### Lists
- Numbered and bulleted lists must preserve numbering and indentation where possible.

### Tables
- Table content must not be lost.
- At minimum: extract table as structured rows/cells.

### Page evidence
- Every block must have a page reference (`page_start`/`page_end`).

---

## Error handling & fallbacks

### Fail-fast rules
If Docling cannot parse a file:
- Record error details in `ingest_log.json`.
- Mark document status as `FAILED_DOCLING`.
- Do **not** partially index.

### Degraded mode rules
If Docling parses but quality is poor (e.g., no headings, scrambled order):
- Mark status as `PARSED_LOW_CONFIDENCE`.
- Store outputs anyway.
- Flag for manual review.

### Future fallback
In Stage 1 we only implement Docling.
In Stage 1.5 (or Stage 2), we will add a fallback extractor:
- Unstructured or pdfplumber, depending on failure mode.

---

## Testing approach

### Golden set
Create a small internal corpus:
- 10 representative contracts
  - 2 scanned PDFs
  - 4 digital PDFs (with schedules)
  - 2 DOCX
  - 2 “nasty” PDFs (tables, multi-column)

### Automated checks
For each golden doc, assert:
- `document.json` exists
- `blocks.length > 0`
- 95%+ blocks have `page_start`
- headings exist (`type=heading`) for known docs
- tables exist for docs with schedules

### Manual spot checks
For 3 docs in the golden set, verify:
- reading order
- headings correctness
- table correctness

---

## Interfaces (what downstream stages will consume)

### CLI (v1)
- `ipdf ingest <path-to-file-or-folder>`
  - outputs to `storage/processed/<sha256>/...`

### Python API (v1)
- `parse_document(path) -> CanonicalDocument`
- `load_canonical(doc_id) -> CanonicalDocument`

---

## Open questions (track, don’t block)
- Do we need OCR for scanned contracts in v1? If yes, what OSS OCR (Tesseract vs others) and where does it fit?
- Do we need to redact secrets in raw storage?
- Do we need to store PDFs long-term or can we store a pointer?

---

## Definition of done
Stage 1 is complete when:
- We can ingest a folder of mixed PDFs/DOCX and reliably produce canonical `document.json` + `document_text.txt`.
- The golden set passes automated checks.
- Reviewers can open `document.json` and follow evidence back to page numbers.