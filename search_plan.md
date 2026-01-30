# Stage 2 — Smart search (keyword + semantic + filters)

## Goal
Make search **feel smart** for contract review:
- Exact keyword lookups (fast, predictable)
- Semantic search (find relevant clauses even when wording differs)
- Filters (restrict results to sections/pages/clauses/types)
- Evidence-first UX (always show where a result came from)

This stage builds the retrieval layer that downstream extraction agents will rely on.

---

## Design decision (recommended)

### Use Qdrant + lightweight pipeline code (v1)
- **Qdrant** as the vector store + filter engine.
- A small amount of our own retrieval orchestration (hybrid scoring + rerank hooks).

Why this is the best default:
- Qdrant is simple to run locally (Docker) and supports strong filtering on payload fields.
- It keeps our architecture modular: we can add Haystack later without rewriting storage.

### When to add Haystack (v2)
Introduce **Haystack** once we want:
- multiple retrievers (BM25 + embeddings) with easy composability
- reranking, query rewriting, evaluation harness, tracing
- pipeline graphs with clear components

We can do Stage 2 without Haystack, but we will design data + interfaces so adding Haystack later is painless.

---

## What we store (index schema)
We index **chunks** derived from Stage 1 `document.json`.

### Chunk record (canonical)
Each chunk is a unit of retrieval.

```json
{
  "chunk_id": "<uuid>",
  "doc_id": "<sha256>",
  "text": "...",
  "type": "definition|clause|schedule|table|heading|paragraph|unknown",
  "section_path": ["Schedule A", "Definitions"],
  "clause_ref": "1.1",
  "page_start": 12,
  "page_end": 13,
  "bbox": [{"page": 12, "x0": 0, "y0": 0, "x1": 0, "y1": 0}],
  "source_blocks": ["block_id_1", "block_id_2"],
  "created_at": "2026-01-29T...",
  "embedding_model": "...",
  "embedding_dim": 1024
}
```

### Minimum filter fields (must)
- `doc_id`
- `type`
- `section_path`
- `clause_ref`
- `page_start/page_end`

These enable:
- “search only within Definitions”
- “only return schedules/entitlements tables”
- “only show results from pages 30–50”

---

## Retrieval behavior

### Search modes
We support 3 modes:

1) **Keyword**
- Exact matches and phrase search
- Useful for: part numbers, product names, defined terms, unique strings

2) **Semantic**
- Vector similarity on chunk embeddings
- Useful for: “audit rights”, “license grant”, “territory restrictions”

3) **Hybrid (default)**
- Combine keyword score + semantic score
- Hybrid is best for contracts because wording varies but key terms still matter.

### Scoring (v1 simple hybrid)
- Keyword score: BM25-like (we can implement in code or via a small local search engine later)
- Semantic score: Qdrant cosine similarity
- Combined score: `final = w_sem * sem + w_kw * kw`
  - start with `w_sem=0.65`, `w_kw=0.35`

Notes:
- If we don’t implement true BM25 in v1, we can approximate keyword scoring with:
  - substring/phrase matches
  - token overlap
  - boosting exact phrase hits

We’ll keep the interface compatible so we can swap in a real BM25 engine later (e.g., Tantivy/Meilisearch/OpenSearch).

---

## Qdrant setup

### Collections
- `contract_chunks_v1` — main collection

### Payload fields
Store filterable metadata in payload:
- `doc_id` (string)
- `type` (string)
- `section_path` (array of strings)
- `clause_ref` (string)
- `page_start`, `page_end` (int)

### Indexing rules
- Insert/update is idempotent based on `chunk_id`
- Chunk embeddings are computed once per chunk per embedding model version
- If embedding model changes:
  - new collection `contract_chunks_v2` OR
  - store multiple vectors (optional later)

---

## Embeddings (OSS-first)

### Requirements
- Run locally (no external API)
- Reasonable quality on legal text
- Fast enough for <10 users

### Options
- Sentence-Transformers legal-ish models (OSS) via `sentence-transformers`
- Later: domain-tuned embeddings (fine-tune on our clause library)

### What we store
- embedding vector per chunk
- `embedding_model` name + version

---

## Filters (how search becomes *useful*)

### User-facing filters (v1)
- Document selector (single doc / multiple docs)
- Section filter:
  - Definitions
  - Schedules / Entitlements
  - Term / Renewal
  - Audit
  - Restrictions / Use rights
- Type filter: `definition`, `clause`, `table`, `schedule`
- Page range filter

### Implementation
- All filters map to Qdrant payload constraints.

---

## Smart features (contract-review specific)

### 1) Query presets
Buttons that run common searches:
- “Definitions for: <term>”
- “License grant / use rights”
- “Metric (NUP/Processor/Named user/etc.)”
- “Audit / compliance”
- “Termination / renewal”

### 2) Query expansion (local)
Without calling external services:
- Expand synonyms:
  - “audit” → “inspection”, “verify”, “compliance review”, “records”
  - “license grant” → “grant of rights”, “permitted use”, “use rights”
- Add boosts for expanded terms (keyword side)

### 3) Evidence-first snippets
- Return results with:
  - snippet around match
  - section path + clause ref
  - page numbers

---

## APIs (what we implement)

### Python service layer (v1)

```python
search(query: str,
       doc_ids: list[str] | None,
       mode: "hybrid"|"keyword"|"semantic" = "hybrid",
       filters: dict | None = None,
       top_k: int = 10) -> list[SearchHit]
```

`SearchHit` must include:
- `chunk_id`, `doc_id`
- `score`
- `text_snippet`
- `section_path`, `clause_ref`
- `page_start`, `page_end`

### HTTP API (FastAPI later)
- `POST /search`
  - returns hits + evidence

---

## Testing approach

### Retrieval golden set
Create a small list of queries with expected hits (by doc_id + clause_ref):
- “audit rights”
- “definition of Processor”
- “term and renewal”
- “licensed territory”
- “license metric named user”

### Automated checks
- For each query, at least 1 expected hit appears in top 5
- Results always include page evidence
- Filters work (e.g., restrict to Definitions only)

---

## Definition of done
Stage 2 is complete when:
- We can index chunks from Stage 1 outputs into Qdrant.
- Users can run keyword + semantic + hybrid searches.
- Filters reliably narrow results (doc/section/type/page range).
- Every hit is evidence-first (section + page info).

---

## Next stage hook
Stage 3 will define:
- Chunking rules (how we create `chunks` from `blocks`)
- Clause classification (definition vs entitlement vs term vs audit)
- “smart extraction” that uses Stage 2 retrieval as its input
