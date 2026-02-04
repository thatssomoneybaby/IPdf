# IPdf — Risks & Mitigations (MVP)

This document tracks early risks that could slow development and the mitigations we plan to apply.

## 1) Docling dependency weight + build time
- Risk: Docker builds are slow and occasionally brittle due to heavy parsing/ML deps.
- Mitigations:
  - Keep tight `.dockerignore` to shrink build contexts (done).
  - Consider a prebuilt base image with Docling deps for the API.
  - Cache wheels or use BuildKit cache mounts for pip.
  - Pin versions (current approach) to reduce resolver backtracking.

## 2) Synchronous ingest blocks requests
- Risk: Large PDFs can stall the API/UI and cause timeouts.
- Mitigations:
  - Offload parse to a background task (done).
  - Add a lightweight job status model to poll progress.
  - Later: move to a worker queue (RQ/Celery) if needed.

## 3) Chunking quality drives all downstream accuracy
- Risk: Weak chunking → noisy search and bad extraction.
- Mitigations:
  - Implement a contract-aware chunker per `chunking_plan.md`.
  - Add `chunk_debug.md` outputs for rapid tuning.
  - Build a small golden set for regression checks.

## 4) Evidence UX can make or break trust
- Risk: If evidence is weak or unclear, reviewers won’t trust results.
- Mitigations:
  - Keep evidence mandatory in all outputs.
  - Add page rendering (PyMuPDF) alongside snippets early.

## 5) Scanned PDFs / OCR gaps
- Risk: Scanned documents produce empty or low-quality text.
- Mitigations:
  - Detect scanned/no-text docs and flag as low confidence.
  - Add optional OCR (Tesseract) when needed.

## 6) Schema drift if Docling output changes
- Risk: Upstream changes break downstream code.
- Mitigations:
  - Normalize into a stable canonical schema (planned).
  - Version schema + pipeline config in outputs.

