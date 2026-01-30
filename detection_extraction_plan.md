

# Stage 3 — Clause detection & structured extraction

## Goal
Convert a contract into **review-ready structured outputs** with **evidence**:
- Definitions ("Term" means …) + where each definition comes from
- Product entitlements / schedules (tables + prose)
- Terms of use / license grant / restrictions
- Audit rights, term/renewal/termination, fees/true-ups (as we add templates)

This stage takes Stage 1 canonical documents and Stage 2 retrieval, and produces:
- `extractions.json` (machine-readable)
- `review_pack.md` (human-friendly)
- Evidence pointers for every extracted field (page + clause + snippet)

---

## Design decision (recommended approach)

### Use a 3-layer system (precision → recall → “understanding”)
This avoids the common trap of going “all-in on LLM” too early.

1) **Deterministic rules (high precision)**
   - Heading detection / section boundaries
   - Clause numbering patterns (1.1, 2.3(a), etc.)
   - Definition patterns ("X" means / "X" has the meaning / definition lists)
   - Schedule/table identification

2) **Lightweight classifiers (improve recall)**
   - Classify chunks into clause families: definition, entitlement, audit, license grant, restriction, term/renewal, etc.
   - Implement with local models where possible (fast for <10 users).

3) **Optional local “schema fill” reasoning (only when needed)**
   - Given retrieved, relevant chunks: fill a JSON schema + evidence
   - Must run locally (no external API) to align with OSS-first

We can deliver strong value with layers 1–2.
Layer 3 can be added once the team sees the workflow and we know which fields matter most.

---

## Inputs

### From Stage 1
- `document.json` with `blocks[]` including:
  - `type`, `text`, `page_start/page_end`, optional `bbox`, `section_path` best-effort

### From Stage 2
- `search(query, filters)` for targeted retrieval when we need it (e.g., “audit” clause discovery)

---

## Outputs

### 1) `extractions.json` (canonical v1)
A stable schema with evidence-first fields.

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
  ],
  "entitlements": {
    "products": [
      {
        "name": "Oracle WebLogic Server",
        "metric": "Processor",
        "quantity": "6",
        "restrictions": ["..."],
        "confidence": 0.75,
        "evidence": [{"chunk_id": "...", "page_start": 30, "page_end": 31, "snippet": "..."}]
      }
    ],
    "tables": [
      {
        "title": "Schedule A — Licensed Programs",
        "rows": [["Program", "Metric", "Qty"], ["...", "...", "..."]],
        "confidence": 0.9,
        "evidence": [{"chunk_id": "...", "page_start": 29, "page_end": 29}]
      }
    ]
  },
  "terms_of_use": {
    "license_grant": [{"text": "...", "confidence": 0.7, "evidence": [{"chunk_id": "..."}]}],
    "restrictions": [{"text": "...", "confidence": 0.7, "evidence": [{"chunk_id": "..."}]}],
    "audit": [{"text": "...", "confidence": 0.7, "evidence": [{"chunk_id": "..."}]}],
    "term_and_renewal": [{"text": "...", "confidence": 0.7, "evidence": [{"chunk_id": "..."}]}]
  }
}
```

### 2) `review_pack.md`
A human-oriented summary:
- Definitions table
- Entitlements (tables + extracted product list)
- Key terms-of-use sections with page references

---

## Core concept: Clause “templates”
We will implement extraction via **templates** (small, testable modules).

### Template list (v1)
1) **Definitions extractor**
2) **Entitlements / Schedule extractor**
3) **License grant & restrictions extractor**
4) (Optional v1.1) **Audit extractor**
5) (Optional v1.1) **Term/renewal/termination extractor**

Each template must:
- declare the retrieval strategy (filters + queries)
- declare the extraction patterns / heuristics
- emit structured outputs with evidence

---

## 3.1 Chunking & sectionization (mandatory before detection)

### Why
Docling blocks are often too granular or too layout-driven.
We need contract-aware chunks.

### Chunking rules (v1)
- Start a new chunk on:
  - heading blocks
  - large numbering resets (e.g., 1 → 2)
  - table blocks (table = its own chunk)
- Merge short consecutive paragraphs until:
  - max tokens/characters threshold (e.g., 1,200–2,000 chars)
  - section boundary changes
- Preserve:
  - `section_path` (derived from nearest headings)
  - `clause_ref` (best-effort)
  - page range
  - list formatting (keep numbering)

### Clause reference detection (v1)
Regex-based extraction from leading text:
- `^\s*(\d+(?:\.\d+)*)(?:\s|\)|\.)`  → 1, 1.1, 2.3.4
- `^\s*(\d+(?:\.\d+)*)(\([a-zA-Z0-9]+\))*` → 2.3(a)

Store:
- `clause_ref` (string)
- `clause_level` (int)

---

## 3.2 Template: Definitions extraction

### What it must catch
- Formal definition list in “Definitions” section
- Inline definitions outside definitions section
- Variants:
  - “\"Term\" means …”
  - “\"Term\" has the meaning …”
  - “Term means …” (no quotes)
  - “Capitalised terms not defined …” (flag, not a definition)

### Retrieval strategy
- Prefer `section_path contains "Definitions"` if present
- Otherwise search queries:
  - `" means"`, `" has the meaning"`, `defined as`, `Definition`
- Filter: `type in {clause, paragraph}`

### Extraction rules (v1)
- Pattern A (quoted term):
  - `\"(?P<term>[^\"]{1,80})\"\s+(means|shall mean|has the meaning|is defined as)\s+(?P<def>.+)`
- Pattern B (unquoted capitalised term):
  - `(?P<term>[A-Z][A-Za-z0-9\- ]{1,80})\s+(means|shall mean|has the meaning|is defined as)\s+(?P<def>.+)`

### Post-processing
- Clean trailing clause references and cross-refs (“as set out in…”)
- Merge multi-paragraph definitions (when definition spans multiple chunks)
- Deduplicate terms (keep best confidence / earliest in Definitions section)

### Confidence scoring (simple)
Start at 0.5 and add:
- +0.2 if in Definitions section
- +0.2 if quoted term pattern
- +0.1 if definition ends before next numbered clause
- -0.2 if term is overly long (>80 chars) or def is too short (<10 chars)

---

## 3.3 Template: Entitlements / Schedules extraction

### What it must catch
- Product list tables (“Licensed Programs”, “Products”, “Schedule”, “Order Form”)
- Metrics + quantities + unit type
- Prose entitlements (when no table exists)

### Retrieval strategy
- First pass: all `type=table` chunks
- Second pass: search queries:
  - `schedule`, `licensed`, `program`, `product`, `entitlement`, `order form`, `support services`
- Prefer sections:
  - `Schedule`, `Order Form`, `Commercials`, `Pricing`, `Product Details`

### Table normalization (v1)
- Convert tables to:
  - header row detection
  - normalize column names (Program/Product, Metric, Qty, Restrictions, Territory, Term)
- Extract row objects:
  - `product_name`, `metric`, `quantity`, `notes/restrictions`

### Prose entitlements (v1)
- Identify paragraphs that look like “Customer is licensed to … for …”
- Extract key fields if present:
  - product name
  - metric keywords (processor, named user, user, core)
  - quantities (numbers + units)

### Confidence scoring
- Table with recognizable headers: 0.85+
- Table without headers but consistent rows: ~0.65
- Prose-only entitlements: ~0.5–0.7 depending on signals

---

## 3.4 Template: Terms of use (license grant + restrictions)

### What it must catch
- License grant clause(s)
- Restrictions (“may not”, “must not”, “except”, “prohibited”)
- Audit/compliance rights (optional in v1)

### Retrieval strategy
- Hybrid search with synonyms:
  - license grant: “grant of rights”, “permitted use”, “license is granted”, “non-exclusive”
  - restrictions: “may not”, “shall not”, “prohibited”, “restriction”, “limitations”
  - audit: “audit”, “inspect”, “verify”, “records”, “compliance review”
- Filter to likely sections:
  - `License`, `Use`, `Restrictions`, `Compliance`, `Audit`, `Verification`

### Extraction rules (v1)
- License grant:
  - capture paragraphs containing “license” + (“grant” or “non-exclusive” or “right to use”)
- Restrictions:
  - capture list items / sentences containing prohibition language
  - keep them as atomic bullets

### Output format
- `terms_of_use.license_grant[]` as short excerpts + evidence
- `terms_of_use.restrictions[]` as bullet items + evidence

---

## Lightweight classification (layer 2)

### Why
Rules alone miss variation. A classifier improves recall and helps routing.

### Implementation (v1)
- Use simple keyword features + section heading cues to assign:
  - `family`: definition | entitlement | license_grant | restriction | audit | term_renewal | other
- This can be a deterministic scorer first.
- Later: plug in a small local text classifier (fine-tuned) if needed.

---

## Optional local “schema fill” reasoning (layer 3)

### When we use it
Only for:
- ambiguous tables
- prose-only entitlements
- complex license grant language

### Rule
The model must return:
- structured fields
- evidence snippets
- never “invent” values without evidence

If we add this, we keep it behind a feature flag:
- `ENABLE_LOCAL_REASONER=false` by default

---

## Testing approach

### Golden extraction set
Pick 10 contracts and label expected outputs:
- 20 known defined terms per doc (for 3 docs)
- at least 1 schedule/entitlement table per doc (where present)
- at least 1 license grant clause per doc

### Automated checks
- Every extracted item has evidence with page references
- Definitions extractor finds >= X known terms in labeled docs
- Entitlements table extractor:
  - detects table presence
  - extracts >= 80% rows without empty product names

### Manual review workflow
- For each doc, reviewers validate:
  - top 10 definitions
  - entitlements table rendering
  - top restrictions list

---

## Definition of done
Stage 3 is complete when:
- We can generate `extractions.json` + `review_pack.md` from a contract.
- Definitions extraction reliably captures the main definition section.
- Entitlements extractor reliably captures schedule tables.
- Terms-of-use extractor returns license grant + restriction bullets.
- All outputs are evidence-first with page references.

---

## Next stage hook
Stage 4 will cover the UI workflow:
- upload → parse → index → search → run extractors
- reviewer corrections & feedback loop (to improve rules/classifier)