

# IPdf — MVP build order (execution checklist)

## Goal of the MVP
A team member can upload a contract and, without touching the CLI:
1) Parse → chunk → index automatically
2) Search with filters (hybrid default)
3) Run Definitions + Entitlements extractors
4) Verify evidence (page/section/clause)
5) Export outputs (MD/CSV/JSON)

---

## Guiding rules (to prevent thrash)
- **Evidence-first always:** nothing is “extracted” unless it points to pages.
- **Stable schemas:** do not let UI depend on raw Docling output.
- **Thin slices:** complete one end-to-end vertical slice before expanding features.
- **Version everything:** pipeline version, ruleset version, embedding model version.

---

## Milestone 0 — Repo + runtime scaffold
**Outcome:** you can run the stack locally in one command.

### Tasks
- [ ] Create repo structure:
  - `app/` (FastAPI)
  - `ui/` (Streamlit)
  - `ipdf/` (core pipeline lib)
  - `storage/` (runtime output)
  - `docker/` (compose files)
- [ ] Add `docker-compose.yml` with:
  - Qdrant
  - App API
  - UI
- [ ] Add `.env.example`:
  - `STORAGE_PATH=...`
  - `QDRANT_URL=...`
  - `EMBEDDING_MODEL=...`
- [ ] Add a simple Makefile:
  - `make up`, `make down`, `make logs`

### Acceptance
- [ ] `make up` starts Qdrant + API + UI
- [ ] UI loads in browser

---

## Milestone 1 — Stage 1 parse + canonical storage
**Outcome:** upload a doc and get `document.json` + `document_text.txt` saved deterministically.

### Tasks
- [ ] Implement `doc_id = sha256(file_bytes)`
- [ ] Save raw file:
  - `storage/raw/<doc_id>/<filename>`
- [ ] Implement Docling parser wrapper:
  - write `storage/processed/<doc_id>/document.json`
  - write `storage/processed/<doc_id>/document_text.txt`
  - write `storage/processed/<doc_id>/ingest_log.json`
- [ ] Add ingest status model:
  - `QUEUED → PARSING → READY|FAILED_DOCLING|PARSED_LOW_CONFIDENCE`

### Acceptance
- [ ] Upload a PDF via API and see outputs on disk
- [ ] Re-ingesting same file does not create duplicate doc_ids

---

## Milestone 2 — Stage 3.1 chunking
**Outcome:** `chunks.json` exists and is navigable by section path.

### Tasks
- [ ] Implement chunker:
  - heading detection
  - section stack → `section_path`
  - clause_ref extraction
  - table-as-chunk
  - chunk boundaries (MAX_CHARS etc.)
- [ ] Persist:
  - `storage/processed/<doc_id>/chunks.json`
  - optional `chunk_debug.md` toggle
- [ ] Add chunking status:
  - `PARSING → CHUNKING → ...`

### Acceptance
- [ ] For a sample contract, `chunks.json` contains headings + tables + clause refs
- [ ] 100% chunks have page ranges + source_blocks

---

## Milestone 3 — Stage 2 indexing + search API (Qdrant)
**Outcome:** search works and returns evidence-rich hits.

### Tasks
- [ ] Choose local embedding runtime and implement `embed(text)->vector`
- [ ] Create Qdrant collection `contract_chunks_v1`
- [ ] Upsert chunks with payload:
  - doc_id, type, section_path, clause_ref, page_start/end
- [ ] Implement `/search`:
  - modes: semantic / keyword-ish / hybrid
  - filters: doc_ids, section contains, type, page range
  - returns `SearchHit[]` with snippet + evidence
- [ ] Add indexing status:
  - `CHUNKING → INDEXING → READY`

### Acceptance
- [ ] Query “audit” returns plausible results
- [ ] Filtering to Definitions reduces noise
- [ ] Hits include section_path + pages

---

## Milestone 4 — UI thin slice (Library → Doc detail → Search)
**Outcome:** non-technical users can browse and search.

### Tasks
- [ ] Streamlit Library page:
  - upload widget
  - document table with status
- [ ] Document detail page:
  - section tree (derived from chunks)
  - chunk list
  - chunk viewer
  - “Open Search with this doc”
- [ ] Search page:
  - query bar + mode
  - filters sidebar
  - results list + evidence drawer
  - copy-with-citation

### Acceptance
- [ ] Upload and navigate a document end-to-end
- [ ] Search results are verifiable via evidence drawer

---

## Milestone 5 — Stage 3.2 Definitions extractor
**Outcome:** definitions table exists with evidence and export.

### Tasks
- [ ] Implement candidate selection (Definitions section + pattern scan + search fallback)
- [ ] Implement regex extraction (quoted + unquoted + Term:)
- [ ] Multi-line merge + stop conditions
- [ ] Dedup + conflict marking
- [ ] Write:
  - `storage/processed/<doc_id>/extractions.json` (definitions filled)
  - `storage/processed/<doc_id>/definitions.csv`
  - append to `review_pack.md`
- [ ] Add extractor status tracking

### Acceptance
- [ ] Definitions page shows 30+ terms for a typical software contract
- [ ] Every row links to evidence chunk + page

---

## Milestone 6 — Stage 3.3 Entitlements extractor
**Outcome:** schedules/tables are extracted, products normalized, and “reference-only” docs handled.

### Tasks
- [ ] Table-first extraction:
  - header detection
  - column normalization
  - row extraction + continuation rows
  - table classification
- [ ] Prose fallback:
  - metric keyword detection
  - quantity parsing
  - product name heuristics
- [ ] Reference detection:
  - “ordering document governs entitlements”
  - populate `entitlements.references[]`
  - set `NO_ENTITLEMENTS_FOUND_IN_DOCUMENT` when appropriate
- [ ] Write:
  - update `extractions.json` (entitlements filled)
  - `entitlements.csv`
  - append to `review_pack.md`

### Acceptance
- [ ] Entitlements page renders detected tables
- [ ] Normalized product table contains metric + qty for at least one schedule doc
- [ ] Reference-only MSA shows “no entitlements” with extracted references

---

## Milestone 7 — UI extraction + export
**Outcome:** one-click extract + download outputs.

### Tasks
- [ ] Add “Run Extractors” button (Definitions, Entitlements)
- [ ] Add Definitions results page:
  - sortable table
  - conflict filter
  - evidence drawer
- [ ] Add Entitlements results page:
  - rendered tables
  - normalized products table
  - evidence drawer
- [ ] Add Exports page / download links:
  - review_pack.md
  - extractions.json
  - definitions.csv
  - entitlements.csv

### Acceptance
- [ ] A user can run extractors without CLI
- [ ] A user can export outputs and share internally

---

## Milestone 8 — Hardening (minimum required)
**Outcome:** reliable enough for daily team use.

### Tasks
- [ ] Add job persistence (sqlite) for statuses
- [ ] Add re-run buttons:
  - re-parse
  - re-chunk
  - re-index
  - re-extract
- [ ] Add structured logs and error surfacing in UI
- [ ] Add a small golden test set and a `make test` command

### Acceptance
- [ ] Failures are visible and actionable
- [ ] Re-running a stage is safe and idempotent

---

## Nice-to-haves (post-MVP)
- Reviewer feedback loop (correct/incorrect)
- Compare two docs (definitions + entitlements)
- Link related docs (MSA + Order Form)
- Saved searches (audit, term, restrictions)
- Auth/SSO

---

## Implementation order (summary)
1) Milestone 0 (stack)
2) Milestone 1 (parse)
3) Milestone 2 (chunk)
4) Milestone 3 (index/search)
5) Milestone 4 (UI browse/search)
6) Milestone 5 (definitions)
7) Milestone 6 (entitlements)
8) Milestone 7 (UI extract/export)
9) Milestone 8 (hardening)