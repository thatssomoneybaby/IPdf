

# Stage 4 — UI plan (web app for contract review)

## Goal
Deliver a small internal web app (<10 users) that makes the pipeline usable:
- Upload contracts (PDF/DOCX)
- Parse → chunk → index automatically
- Search (keyword + semantic + filters)
- Run extractors (Definitions, Entitlements)
- Review outputs with evidence (page/section/clause)
- Export results (MD/CSV/JSON)

Design principle: **evidence-first**. The UI should always help a reviewer verify where information came from.

---

## Non-goals (v1)
- No user accounts / SSO (we can add later)
- No multi-tenant / external hosting
- No automated “final legal interpretation”
- No editing PDFs directly

---

## Deployment assumptions
- Runs on a small internal server or a local machine (Docker)
- Stores documents + outputs on disk (with a simple folder structure)
- Qdrant runs alongside the app (Docker)

---

## Tech stack (recommended)

### v1 (fast to ship)
- Backend: **FastAPI**
- Worker queue: **simple background worker** (Celery/RQ optional; start with in-process worker)
- Vector DB: **Qdrant**
- UI: **Streamlit** (or Gradio) for the first usable version

Why:
- Streamlit lets us iterate fast with small team feedback.
- FastAPI keeps a clean boundary so we can swap UI to React later.

### v2 (polish)
- UI: Next.js (React) + component library
- Auth: SSO (OIDC)
- Persistent DB (Postgres) for metadata and review feedback

---

## Core UX flows

### Flow A — Upload & ingest
1) User uploads one or more documents
2) System shows:
   - filename
   - status (queued / parsing / chunking / indexing / ready / failed)
3) When ready:
   - user can open doc detail page

### Flow B — Browse & verify
1) User opens a document
2) UI shows:
   - section tree (from `section_path`)
   - chunks list
3) Clicking a chunk shows:
   - full chunk text
   - metadata (pages, clause ref, section path)
   - “copy snippet”

### Flow C — Smart search
1) User enters query
2) User chooses mode:
   - Hybrid (default)
   - Keyword
   - Semantic
3) User applies filters:
   - document(s)
   - section
   - type (definition / clause / table / schedule)
   - page range
4) Results show:
   - snippet
   - section path
   - page numbers
   - score

### Flow D — Extraction
1) User clicks “Run Extractors”
2) Options:
   - Definitions
   - Entitlements
3) Results pages:
   - Definitions table (sortable, searchable)
   - Entitlements tables + normalized product rows
4) Every extracted item links back to evidence chunk

### Flow E — Export
User can download:
- `review_pack.md`
- `definitions.csv`
- `entitlements.csv`
- `extractions.json`

---

## Information architecture (pages)

### 1) Home / Library
**Purpose:** show all documents and their status.

Components:
- Upload button
- Document table:
  - Name
  - Ingested at
  - Status
  - Actions: Open / Re-run / Delete (optional)

### 2) Document detail
**Purpose:** make the parsed structure navigable.

Layout:
- Left: Section tree
- Middle: Chunk list
- Right: Chunk viewer (text + metadata)

Actions:
- “Open Search with this doc preselected”
- “Run Extractors”
- “Download Outputs”

### 3) Search
**Purpose:** find relevant clauses fast.

Layout:
- Top: Query bar + mode selector
- Left: Filters
- Center: Results list
- Right: Evidence viewer (selected result)

Result card includes:
- snippet
- section path + clause ref
- page range
- match highlights (optional)

### 4) Definitions results
**Purpose:** review extracted defined terms.

Components:
- Table view:
  - Term | Definition | Page | Clause | Confidence
- Search within terms
- Filter: conflicts only
- Click row → opens evidence chunk

### 5) Entitlements results
**Purpose:** review schedules/order forms.

Components:
- Detected tables (rendered)
- Normalized products table:
  - Product | Metric | Qty | Term | Notes | Confidence
- “No entitlements found” state with extracted references to ordering docs

### 6) Outputs / Exports
**Purpose:** quick download and sharing.

Components:
- Links to generated files
- Copy-to-clipboard for key sections

---

## UI states & status model

### Document statuses
- `QUEUED`
- `PARSING`
- `CHUNKING`
- `INDEXING`
- `READY`
- `FAILED_DOCLING`
- `PARSED_LOW_CONFIDENCE`

### Extractor statuses
- `NOT_RUN`
- `RUNNING`
- `COMPLETE`
- `FAILED`

UI must show:
- what failed
- where to find logs
- how to re-run

---

## Data contracts (what UI consumes)

### Document list item
- doc_id
- filename
- ingested_at
- status
- page_count

### Document structure
- `chunks.json` (primary)
  - section_path
  - clause_ref
  - page ranges

### Search response
`SearchHit[]`:
- chunk_id
- doc_id
- score
- snippet
- section_path
- clause_ref
- page_start/page_end

### Extractions
- `extractions.json`
  - definitions[]
  - entitlements.tables[]
  - entitlements.products[]
  - entitlements.references[]

---

## Backend API (FastAPI)

### Document endpoints
- `POST /docs/upload`
  - body: multipart files
  - returns: job ids + doc ids

- `GET /docs`
  - returns: list of docs + statuses

- `GET /docs/{doc_id}`
  - returns: metadata + status

- `GET /docs/{doc_id}/chunks`
  - returns: chunks.json

- `POST /docs/{doc_id}/reindex`
  - re-run chunking + indexing

### Search endpoints
- `POST /search`
  - body: query + mode + filters + top_k
  - returns: hits

### Extraction endpoints
- `POST /docs/{doc_id}/extract`
  - body: {definitions: true/false, entitlements: true/false}
  - returns: extractor job id

- `GET /docs/{doc_id}/extractions`
  - returns: extractions.json

### Export endpoints
- `GET /docs/{doc_id}/export/review_pack.md`
- `GET /docs/{doc_id}/export/definitions.csv`
- `GET /docs/{doc_id}/export/entitlements.csv`
- `GET /docs/{doc_id}/export/extractions.json`

---

## Jobs & background processing

### Ingest job pipeline
For each uploaded doc:
1) Stage 1 parse (Docling)
2) Stage 3.1 chunk
3) Stage 2 index (embed + upsert into Qdrant)
4) Mark READY

### Extraction job pipeline
On demand per doc:
1) Definitions extractor
2) Entitlements extractor
3) Write outputs + update `review_pack.md`

### Simple v1 worker
- Start with a single background worker thread/process
- Persist job state in a lightweight `jobs.json` or sqlite

---

## Storage layout (UI-friendly)

```
storage/
  raw/<doc_id>/<filename>
  processed/<doc_id>/
    document.json
    document_text.txt
    chunks.json
    extractions.json
    review_pack.md
    definitions.csv
    entitlements.csv
    ingest_log.json
    extract_log.json
```

---

## Evidence UX patterns

### Evidence drawer
Whenever user clicks:
- a search result
- a definition row
- an entitlement row

Show:
- snippet
- pages
- section path
- clause ref
- full chunk text

### “Copy with citation”
Button that copies:
- selected text
- plus a citation string like: `(Doc: <filename>, p.<page_start>, clause <clause_ref>)`

---

## Security & privacy (v1)
- Local-only processing (no external APIs)
- Files stored on internal disk
- Optional: encrypt storage at rest (OS level)
- Optional: simple password gate / basic auth

---

## MVP milestones

### Milestone 1 — Usable library + browse
- Upload
- Status
- Document detail with section tree + chunks

### Milestone 2 — Search
- Hybrid search + filters
- Evidence viewer

### Milestone 3 — Definitions + Entitlements outputs
- Run extractors
- Definitions table
- Entitlements tables + normalized products
- Exports

---

## V2 backlog (after MVP)

### Reviewer feedback loop
- “Mark as correct/incorrect” on extracted items
- Add notes
- Export “review decisions”

### Document linking
- Link MSA to Order Form(s)
- Combined extraction across linked docs

### Compare
- Compare definitions/entitlements between two docs

### Admin features
- Usage metrics (queries/run counts)
- Pipeline versioning UI

---

## Definition of done
Stage 4 is complete when:
- A team member can upload a contract and, without touching the CLI,:
  - search for clauses
  - run Definitions + Entitlements extractors
  - verify evidence
  - export outputs
- The UI surfaces failures clearly and supports re-runs.