

# Required external components (OSS-first)

## Purpose of this document
This project intentionally builds on existing OSS components. This file lists:
- what external pieces we rely on
- why we need them
- how we integrate them
- whether we **clone a repo** or use **pip/docker**

**Rule of thumb:**
- We only *clone* our own `ipdf` repo.
- We consume upstream projects via **Python packages** (pip) or **Docker images** where possible.

---

## 1) Document parsing (Stage 1)

### Primary parser — Docling
**What it does**
- Parses PDFs/DOCX into structured text while preserving layout signals (headings, lists, tables) and page references.

**How we use it**
- As a Python dependency (preferred for MVP)
- Called by our ingest pipeline to generate `document.json` + `document_text.txt`

**Integration**
- `pip install docling` (or pin in `pyproject.toml`)
- Our wrapper normalizes Docling output into our canonical schema.

**Repo (reference / issues / docs)**
- Docling: https://github.com/docling-project/docling

**Optional: run as a service**
If we want parsing isolated behind an API:
- Docling Serve: https://github.com/docling-project/docling-serve

---

## 2) Vector database (Stage 2)

### Qdrant (Docker)
**What it does**
- Stores embeddings for semantic search
- Supports payload-based filtering (doc_id, section_path, page range, type)

**How we use it**
- Run via Docker Compose
- Upsert chunks as points with payload fields
- Query for semantic results + filters

**Integration**
- `docker-compose.yml` service: `qdrant`
- Python client in our API for upsert/query

**Repo (reference / docs)**
- Qdrant: https://github.com/qdrant/qdrant

---

## 3) Embeddings runtime (Stage 2)

### Sentence-Transformers (Python)
**What it does**
- Generates embeddings for chunks and queries locally (no external API)

**How we use it**
- Embed each chunk once during indexing
- Embed user queries at search time

**Integration**
- `pip install sentence-transformers`
- Choose an embedding model and pin it via config:
  - `EMBEDDING_MODEL=<model_name>`

**Repo (reference)**
- Sentence-Transformers: https://github.com/UKPLab/sentence-transformers

**Notes**
- Model weights will be downloaded locally when first used.
- We version the model name in outputs so results are reproducible.

---

## 4) Web API backend (Stage 4)

### FastAPI (Python)
**What it does**
- Provides endpoints for:
  - upload
  - job status
  - search
  - run extractors
  - exports

**How we use it**
- Runs as the backend service in Docker Compose
- Talks to:
  - local storage
  - Qdrant

**Integration**
- `pip install fastapi uvicorn`

**Repo (reference)**
- FastAPI: https://github.com/fastapi/fastapi

---

## 5) UI (Stage 4)

### Streamlit (v1 UI)
**What it does**
- Rapid internal UI for:
  - library
  - doc viewer
  - search
  - extracted results
  - exports

**How we use it**
- Runs as the UI service in Docker Compose
- Calls the FastAPI backend

**Integration**
- `pip install streamlit`

**Repo (reference)**
- Streamlit: https://github.com/streamlit/streamlit

**Optional alternative**
- Gradio: https://github.com/gradio-app/gradio

---

## 6) PDF evidence rendering (strongly recommended)

### PyMuPDF (fitz)
**What it does**
- Renders PDF pages as images so reviewers can visually verify clauses.

**How we use it**
- Given a `page_start/page_end` from evidence:
  - render that page
  - show it alongside extracted text/snippet

**Integration**
- `pip install pymupdf`

**Repo (reference)**
- PyMuPDF: https://github.com/pymupdf/PyMuPDF

**Note**
- v1 can show page images server-side.
- v2 React UI could use PDF.js in-browser instead.

---

## 7) Optional OCR (only if needed)

### When OCR is required
If we receive scanned PDFs with no embedded text, we need OCR to extract readable text.

### Tesseract (system dependency)
**What it does**
- OCR engine to convert scanned page images into text.

**How we use it**
- Only for documents detected as “scanned/no text”.
- Plugged into Stage 1 ingest as an optional step.

**Integration**
- Install on host OS (not a Python-only dependency).
- Our pipeline toggles OCR via config:
  - `ENABLE_OCR=true/false`

**Repo (reference)**
- Tesseract: https://github.com/tesseract-ocr/tesseract

---

## 8) Job tracking / persistence (MVP uses lightweight; hardening uses sqlite)

### v1 (simplest)
- In-memory job state + persisted JSON file

### v1.5 / hardening
- sqlite for job + doc metadata
- avoids losing statuses on restarts

Python option:
- `sqlite3` (built in)
- or `SQLModel` / `SQLAlchemy` if we want an ORM

---

## 9) Optional: pipeline orchestration (only if we need it)

### When to add
If we have concurrency, retries, and long-running jobs, add a worker queue.

Options:
- RQ (Redis Queue)
- Celery

MVP guidance:
- Start with a single background worker thread/process.

---

## 10) Optional: “BM25 keyword engine” (later)

### Why
Our v1 keyword scoring may be simple (phrase match / token overlap). If we want true BM25 keyword search, add one of:

- Meilisearch (fast + simple)
- OpenSearch/Elasticsearch (heavier)
- Tantivy (embedded Rust search engine)

MVP guidance:
- Do not add this until semantic + filters are working.

---

## Summary table

| Component | Purpose | How we consume it | Required for MVP |
|---|---|---|---|
| Docling | Parse PDFs/DOCX into structured text | pip (preferred) or docling-serve | Yes |
| Qdrant | Vector DB + filtering | Docker | Yes |
| Sentence-Transformers | Local embeddings | pip | Yes |
| FastAPI | Backend API | pip | Yes |
| Streamlit | Internal UI | pip | Yes |
| PyMuPDF | Render PDF pages for evidence | pip | Strongly recommended |
| Tesseract | OCR for scanned PDFs | system install | Optional |
| sqlite | Job/doc metadata | built-in | Hardening |
| RQ/Celery | Background jobs | pip + Redis | Optional |
| BM25 engine | Better keyword retrieval | Docker or embedded | Optional |