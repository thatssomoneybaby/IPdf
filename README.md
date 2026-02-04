IPdf — Evidence-first contract analysis (M1)

IPdf is a small stack to ingest PDFs, normalize them into a canonical JSON representation, and surface them in a Streamlit UI. This repository contains:

- A FastAPI backend that ingests files, tries Docling for parsing with a PyMuPDF fallback, and exposes simple endpoints.
- A Streamlit UI (Library / Document Detail / Search) to exercise the ingest path end-to-end.
- Docker Compose wiring for local development.

Repository Structure

- `app/` — FastAPI API service
  - `main.py` — endpoints and ingest logic
  - `requirements.txt` — Python deps (Docling, FastAPI, PyMuPDF, etc.)
  - `Dockerfile` — API image
- `ui/` — Streamlit frontend
  - `streamlit_app.py` — entry point
  - `pages/` — Library, Document Detail, Search
  - `requirements.txt` — UI deps
  - `Dockerfile` — UI image
- `docker/` — Compose definitions
  - `docker-compose.yml` — brings up Qdrant, API, and UI
- `storage/` — local storage for raw/processed files (ignored by git)
- `Makefile` — convenience targets (`make up`, `make down`, etc.)

Quickstart (Docker Compose)

Prereqs: Docker, Docker Compose, and Make.

- Start the stack:
  - `make up`
- Open UI: http://localhost:8501
- Upload a PDF in Library → open Document Detail to see parsing results.
- API docs: http://localhost:8000/docs

To force dependency rebuilds:
- `make down`
- `docker compose -f docker/docker-compose.yml build --no-cache`
- `make up`

Backend: Ingest + Docling

- Tries Docling first; falls back to PyMuPDF on failure.
- Canonical JSON is written to `storage/processed/<doc_id>/document.json`.
- Diagnostics are written to `ingest_log.json`, including:
  - Installed versions of `docling`, `docling_core`, `docling_parse`
  - Which adapter path ran (e.g., `DocumentConverter.convert`, `Pipeline.run`)
  - Any `docling_failed:` message

Docling pins (in `app/requirements.txt`) are chosen to build reliably on Apple Silicon. If you hit runtime mismatches:
- Option A: unpin `docling-core` and `docling-parse` and keep only `docling==<version>` so pip resolves compatible subpackages.

UI Notes

- Streamlit badge() isn’t used; we render status with colored Markdown labels for compatibility across Streamlit versions.
- Page links use paths relative to the UI root (e.g., `pages/1_Library.py`).

Common Tasks

- Logs: `make logs`
- Rebuild images: `make build`
- Stop: `make down`

Pushing to GitHub

If you want to push this repo to GitHub, you can either:

- Use the helper script:
  - `scripts/push_to_github.sh <git_remote_url>`
  - Example: `scripts/push_to_github.sh git@github.com:your-org/ipdf.git`
- Or run the commands manually (see the script contents).

Note: pushing requires your git credentials configured locally (SSH or HTTPS with token).

Troubleshooting

- Slow Docker builds due to pip resolver backtracking: pins are set to avoid backtracking on aarch64. You can iterate by keeping Docker layer cache (remove `--no-cache-dir`), or use `--no-cache` for clean rebuilds.
- Docling "pipeline not found": check `ingest_log.json` → update pins or the adapter path as needed.

Docker build reliability (Docling base)

- We build a local base image with Docling deps so API builds are fast and consistent.
- Build steps (first time or after changing dependencies):
  - `docker compose -f docker/docker-compose.yml build docling-base api`
- For pip cache mounts, enable BuildKit:
  - `DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.yml build docling-base api`
- To lock transitive deps:
  - `scripts/lock_deps.sh` (writes `app/constraints.txt`)
- The `docling-base` service is marked with a compose profile (`build`) so it won't start during `up`.
  - To build it explicitly: `docker compose -f docker/docker-compose.yml --profile build build docling-base`
