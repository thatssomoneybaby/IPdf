

# Stage 3.2 — Definitions extractor

## Goal
Extract a contract’s **defined terms** into a structured, reviewable output with **evidence**.

Deliverables per document:
- `extractions.json` (definitions section populated)
- `review_pack.md` (Definitions table)
- Optional: `definitions.csv` for spreadsheet review

This stage validates that:
- Chunking + sectionization are correct
- Search filters can target “Definitions” reliably
- Evidence plumbing (page + clause + snippet) is end-to-end solid

---

## Inputs

### Required
- `storage/processed/<doc_id>/chunks.json`
  - `chunks[]` with:
    - `chunk_id`, `text`, `type`, `section_path`, `clause_ref`, `page_start/page_end`

### Optional
- Stage 2 `search()` API for fallback retrieval when sectionization is weak

---

## Outputs

### 1) `extractions.json` (definitions only for v1)
This stage only populates `definitions[]`.

```json
{
  "doc_id": "<sha256>",
  "extracted_at": "2026-01-29T...",
  "pipeline": {"version": "v1", "ruleset": "2026-01"},
  "definitions": [
    {
      "term": "Processor",
      "definition": "...",
      "confidence": 0.92,
      "location": {"section_path": ["Definitions"], "clause_ref": "1.1"},
      "evidence": [
        {
          "chunk_id": "...",
          "page_start": 12,
          "page_end": 12,
          "clause_ref": "1.1",
          "snippet": "\"Processor\" means ..."
        }
      ]
    }
  ]
}
```

### 2) `review_pack.md` additions
Add a “Definitions” section that includes:
- Table columns: Term | Definition | Page | Clause
- Sorted alphabetically by term
- Flag duplicates / conflicts

### 3) Optional `definitions.csv`
Columns:
- doc_id, term, definition, confidence, page_start, clause_ref, section_path

---

## High-level approach

### Three passes
1) **Targeted retrieval**: identify candidate chunks likely to contain definitions
2) **Extraction**: parse candidate text into (term, definition)
3) **Normalization + dedupe**: merge duplicates, resolve multi-line definitions, score confidence

---

## Pass 1 — Candidate selection (retrieval)

### Primary: Section filter
Select chunks where `section_path` contains any of:
- `Definitions`
- `Interpretation`
- `Defined Terms`

Also include headings matching those.

### Secondary: Pattern scan (whole doc)
If definitions section is missing or weak, scan all chunks for definition indicators:
- `" means` / `" shall mean` / `" has the meaning`
- `is defined as`
- `for the purposes of this Agreement, ... means`
- `capitalised terms` / `capitalized terms`

### Tertiary: Stage 2 search fallback
Run a small set of queries (hybrid mode):
- `" means"`
- `" shall mean"`
- `" has the meaning"`
- `defined as`
- `defined terms`

Take top N hits, dedupe by chunk_id.

### Candidate cap
- Default: max 250 chunks (safety)
- If doc is small: all candidates

---

## Pass 2 — Extraction rules

### Definition patterns (v1)

#### Pattern A — Quoted term (most common)
Examples:
- “\"Processor\" means …”
- “\"Program\" shall mean …”

Regex (v1):
- `\"(?P<term>[^\"]{1,80})\"\s+(means|shall mean|has the meaning|is defined as)\s+(?P<def>.+)`

#### Pattern B — Term in bold/caps without quotes
Examples:
- `Processor means …`

Regex (v1):
- `(?P<term>[A-Z][A-Za-z0-9\- ]{1,80})\s+(means|shall mean|has the meaning|is defined as)\s+(?P<def>.+)`

#### Pattern C — “Term:” style
Examples:
- `Processor: the number of ...`

Heuristic:
- line starts with `Term:` and term is Title Case

#### Pattern D — List of definitions separated by semicolons
Common in dense definitions sections.

Heuristic:
- split on `;` when we see repeated “"Term"” occurrences

---

## Multi-line definitions

### Problem
Definitions often wrap across lines or paragraphs, especially in PDFs.

### Solution (v1)
- If a definition line ends with:
  - comma, “and”, “or”, “including”, or no terminal punctuation
  - and the next line/paragraph is not a new term
- Then append the next line/paragraph to the definition until:
  - a new term begins OR
  - we hit a heading/clause boundary

Max merge window:
- up to 3 following paragraphs or 1200 chars

---

## Stop conditions (avoid over-capture)
A definition should stop when we detect:
- the start of a new definition term
- a new clause number at left margin
- a heading block
- “For the avoidance of doubt” (often starts a new concept)

---

## Normalization

### Term cleanup
- Strip quotes and trailing punctuation
- Normalize whitespace
- Preserve capitalization (do not lowercase)
- Reject if term is:
  - too long (>80 chars)
  - mostly numeric
  - contains line breaks

### Definition cleanup
- Remove leading punctuation and extra whitespace
- Keep cross references (do not remove legal meaning)
- If definition is extremely short (<10 chars), mark low confidence

---

## Deduplication & conflicts

### Deduplicate by normalized term
Normalize:
- trim spaces
- collapse whitespace

Rules:
- Prefer definitions found inside a Definitions section
- Prefer quoted-term matches
- If multiple definitions differ materially:
  - keep both
  - mark as `conflict=true`
  - include both evidence entries

---

## Confidence scoring (v1)
Start at 0.4 and add:
- +0.25 if in Definitions section
- +0.20 if Pattern A (quoted)
- +0.10 if clause_ref present
- +0.05 if definition length is reasonable (30–500 chars)
- -0.20 if term length > 60 chars
- -0.20 if definition length < 10 chars

Clamp to [0, 1].

---

## Evidence requirements (non-negotiable)
Every definition must include at least:
- `chunk_id`
- `page_start/page_end`
- `clause_ref` if known
- `snippet` (short excerpt showing the match)

If evidence is missing, do not emit the definition.

---

## Performance & scaling
Target: <10 users, local deployment.
- Extraction should complete within seconds for typical contracts (<200 pages).
- Use streaming/iterative parsing; avoid loading huge intermediate strings.

---

## Testing approach

### Golden set
- 10 contracts
- For 3 of them, manually label 20 key terms each.

### Automated checks
- At least 70% of labeled terms are found for labeled docs (v1 target)
- 100% extracted items have evidence
- Duplicate detection flags repeated terms

### Manual checks
- For each labeled doc:
  - scan top 30 terms
  - verify 5 random terms are correct and point to the right pages

---

## Interfaces

### CLI
- `ipdf extract definitions <doc_id>`
  - reads `chunks.json`
  - writes `extractions.json` + updates `review_pack.md`

### Python API
- `extract_definitions(chunks: ChunkedDocument) -> DefinitionsResult`

---

## Definition of done
Stage 3.2 is complete when:
- Definitions extraction works reliably on the golden set.
- Output is evidence-first and reviewer-friendly.
- We can export `definitions.csv` for quick validation.

---

## Next stage hook
Stage 3.3 will implement **Entitlements/Schedules extraction** (tables + product rows).