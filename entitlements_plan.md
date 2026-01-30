

# Stage 3.3 — Entitlements & schedules extractor

## Goal
Extract **licensing entitlements** from contracts and ordering documents into structured outputs with evidence.

This includes:
- Schedules/appendices containing product lists (tables)
- Metrics + quantities + units
- Term/renewal dates relevant to entitlements
- Territory / environment / use restrictions (where stated)
- References to external ordering docs (Order Form, Ordering Document, SOW)

Outputs must be **review-ready**:
- Tables preserved and rendered
- Product rows normalized
- Every extracted field linked to evidence (page + chunk)

---

## Inputs

### Required
- `storage/processed/<doc_id>/chunks.json`
  - `chunks[]` including table chunks with `table.rows` (if available)

### Optional
- Stage 2 `search()` API for targeted retrieval:
  - find “Order Form”, “Ordering Document”, “Schedule”, “Licensed Programs”, “Support Services”

---

## Outputs

### 1) `extractions.json` (entitlements section populated)

```json
{
  "doc_id": "<sha256>",
  "extracted_at": "2026-01-29T...",
  "pipeline": {"version": "v1", "ruleset": "2026-01"},
  "entitlements": {
    "tables": [
      {
        "title": "Schedule A — Licensed Programs",
        "table_type": "licensed_programs|pricing|support|unknown",
        "headers": ["Program", "Metric", "Qty", "Notes"],
        "rows": [
          {"Program": "Oracle WebLogic Server", "Metric": "Processor", "Qty": "6", "Notes": "..."}
        ],
        "confidence": 0.9,
        "evidence": [{"chunk_id": "...", "page_start": 29, "page_end": 29}]
      }
    ],
    "products": [
      {
        "name": "Oracle WebLogic Server",
        "metric": "Processor",
        "quantity": 6,
        "unit": "Processor",
        "term": {"start": null, "end": null},
        "territory": null,
        "restrictions": ["..."],
        "source": "table",
        "confidence": 0.75,
        "evidence": [{"chunk_id": "...", "page_start": 29, "page_end": 29, "snippet": "..."}]
      }
    ],
    "references": [
      {
        "ref_type": "order_form|ordering_document|sow|msa|support_schedule",
        "ref_text": "Order Form dated 1 Jan 2026",
        "confidence": 0.6,
        "evidence": [{"chunk_id": "...", "page_start": 3, "page_end": 3, "snippet": "..."}]
      }
    ]
  }
}
```

### 2) `review_pack.md` additions
Add an “Entitlements & Schedules” section:
- Render each detected table (as markdown)
- Summarize normalized product rows beneath
- Call out missing/ambiguous metrics and items needing manual check

### 3) Optional `entitlements.csv`
One row per normalized product entitlement:
- doc_id, product_name, metric, quantity, unit, term_start, term_end, restrictions, page_start, clause_ref

---

## High-level approach

### Two lanes of extraction
1) **Table-first lane** (primary):
   - Identify entitlement tables, normalize headers, extract rows

2) **Prose lane** (fallback):
   - Identify paragraphs that describe entitlements without a clean table

Both lanes emit:
- structured fields
- confidence score
- evidence

---

## Pass 1 — Candidate selection

### A. Table candidates (always)
Select all chunks where:
- `type == table` OR `table.rows` exists

### B. Heading/section candidates
Select chunks where `section_path` or `heading` contains:
- Schedule, Appendix, Annex
- Order Form, Ordering Document, Ordering
- Licensed Programs, Products, Program
- Support Services, Fees, Pricing

### C. Search fallback (Stage 2)
Queries (hybrid) limited to top N:
- `licensed program`
- `ordering document`
- `order form`
- `schedule`
- `support services`
- `fees` / `pricing`

---

## Pass 2 — Table extraction (table-first lane)

### 2.1 Identify entitlement table types
Classify each table into:
- `licensed_programs` (product + metric + qty)
- `pricing` (price/rates; may still include metric/qty)
- `support` (support level/term)
- `unknown`

Signals:
- header contains `Program|Product|Service|SKU`
- header contains `Metric|Quantity|Qty|Units`
- header contains `Support|CSI|Support Level`
- header contains `Price|Rate|Total|AUD|USD`

### 2.2 Header row detection
Tables may have:
- explicit headers
- multi-row headers
- no headers

Rules (v1):
- If first row has 2+ cells with mostly non-numeric tokens and includes known header keywords → header row
- Else if second row matches header keywords better → header row = second row
- Else → treat as headerless and use `col_1`, `col_2`, ...

### 2.3 Column normalization
Map common header variants into canonical columns:

| Canonical | Examples |
|---|---|
| `product` | Program, Product, Licensed Program, Service, Item |
| `metric` | Metric, Unit, License Metric, Measure |
| `quantity` | Qty, Quantity, Units, Number |
| `term` | Term, Subscription Term, Start/End, Period |
| `territory` | Territory, Region |
| `restrictions` | Notes, Restrictions, Limitations, Use |
| `sku` | SKU, Part #, Item Code |
| `csi` | CSI, Support ID |

### 2.4 Row extraction
For each row:
- Build a dict keyed by canonical column names
- Trim whitespace, collapse newlines
- If row looks like a continuation (e.g., empty product but notes exist), attach to previous row’s restrictions

### 2.5 Product normalization
From each row, attempt to derive:
- `name`
- `metric`
- `quantity` (int if possible, else store raw)
- `unit`
- `term_start/term_end` (best-effort parse)
- `restrictions[]`

### 2.6 Evidence
For each table and row:
- evidence references table chunk id + page range
- where possible include a short row snippet (e.g., joined row cells)

---

## Pass 3 — Prose entitlements (fallback lane)

### 3.1 Candidate prose chunks
Select chunks that match signals:
- contains `licensed` + (`program`|`product`|`service`)
- contains `entitled` / `entitlement`
- contains `subscription` + (`term`|`period`)
- contains metric keywords: `processor`, `core`, `named user`, `user`, `employee`, `seat`

Prefer sections:
- Schedule, Order Form, Commercials, Pricing

### 3.2 Extraction rules
Heuristics (v1):
- Product name:
  - look for patterns like `Oracle <X>` or Title Case runs
- Quantity:
  - regex for numbers + units: `(?P<n>\d{1,6})\s*(licenses?|users?|processors?|cores?|seats?)`
- Metric:
  - keyword mapping (e.g., “Named User Plus” → `NUP`)
- Term:
  - extract dates, “12 months”, “three (3) years”, “subscription term”

Emit a product object only if at least:
- (product name + metric) OR (product name + quantity)

---

## Handling common contract realities

### “Ordering document governs entitlements”
Many MSAs only define legal terms and say entitlements are in order forms.

We must:
- detect and extract those references into `entitlements.references[]`
- if no actual entitlements are present, say so clearly in outputs:
  - `status: NO_ENTITLEMENTS_FOUND_IN_DOCUMENT`
  - and list the referenced order docs

### Multi-document workflows
Later, we may ingest multiple related docs and join them:
- MSA + Order Form + Schedules

For v1:
- extraction is per document
- references are captured so a human can locate the ordering doc

---

## Confidence scoring (v1)

### Table-derived products
Start 0.6 and add:
- +0.2 if table classified as `licensed_programs`
- +0.1 if metric column present and filled
- +0.1 if quantity parsed as number
- -0.2 if product cell is empty/unknown

### Prose-derived products
Start 0.45 and add:
- +0.15 if product name looks strong (matches known vendor/product pattern)
- +0.15 if metric keyword found
- +0.10 if quantity parsed
- -0.20 if ambiguous pronouns (“it”, “the software”) without clear product name

Clamp to [0,1].

---

## Evidence requirements (non-negotiable)
Every entitlement table/product/reference must include evidence:
- `chunk_id`
- `page_start/page_end`
- snippet when available

If evidence is missing, do not emit the item.

---

## Testing approach

### Golden set
- 10 docs with known schedules/order forms
- Include at least:
  - 3 clean tables
  - 3 messy tables (multi-row headers)
  - 2 prose-only ordering docs
  - 2 MSAs with references but no entitlements

### Automated checks
- 100% extracted rows have evidence
- Header detection works on clean tables
- For table docs: extract >= 80% non-empty product names
- For reference-only docs: status indicates no entitlements and references captured

### Manual checks
- Rendered tables match expectations
- Normalized product rows are sensible

---

## Interfaces

### CLI
- `ipdf extract entitlements <doc_id>`
  - reads `chunks.json`
  - writes `extractions.json` + updates `review_pack.md`
  - optional `entitlements.csv`

### Python API
- `extract_entitlements(chunks: ChunkedDocument) -> EntitlementsResult`

---

## Definition of done
Stage 3.3 is complete when:
- Entitlement tables are reliably detected and rendered.
- Product/metric/qty are extracted for typical ordering schedules.
- Reference-only MSAs are handled cleanly (no false entitlements).
- Output is evidence-first and reviewer-friendly.

---

## Next stage hook
Stage 4 will define the **UI workflow**:
- upload → parse → chunk → index → search
- run extractors (Definitions / Entitlements)
- display results with evidence and export options