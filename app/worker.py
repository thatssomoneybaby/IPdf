from __future__ import annotations

import os
import threading
from queue import Queue

from config import PROCESSED_DIR
from models import DocumentStatus
from pipeline import (
    run_chunking_only,
    run_definitions_extractor,
    run_docling_or_fallback,
    run_entitlements_extractor,
    run_indexing_only,
)
from storage import find_raw_path, read_json, write_json


TASK_QUEUE: "Queue[dict]" = Queue()
WORKER_STARTED = False


def enqueue_task(task: dict) -> None:
    TASK_QUEUE.put(task)


def _ingest_worker():
    while True:
        task = TASK_QUEUE.get()
        try:
            t = task.get("type")
            if t == "ingest":
                run_docling_or_fallback(task["raw_path"], task["processed_dir"], task.get("options"))
            elif t == "rechunk":
                run_chunking_only(task["processed_dir"])
            elif t == "reindex":
                run_indexing_only(task["processed_dir"])
            elif t == "definitions":
                run_definitions_extractor(task["processed_dir"])
            elif t == "entitlements":
                run_entitlements_extractor(task["processed_dir"])
        except Exception as e:
            try:
                processed_dir = task.get("processed_dir")
                meta_path = processed_dir / "meta.json"
                meta = read_json(meta_path) or {}
                t = task.get("type")
                if t == "rechunk":
                    meta.update({"status": DocumentStatus.FAILED_CHUNKING})
                elif t == "reindex":
                    meta.update({"status": DocumentStatus.FAILED_INDEXING})
                elif t == "definitions":
                    meta.update({"definitions_status": "FAILED"})
                elif t == "entitlements":
                    meta.update({"entitlements_status": "FAILED"})
                else:
                    meta.update({"status": DocumentStatus.FAILED_DOCLING})
                meta.update({"errors": (meta.get("errors") or []) + [str(e)]})
                write_json(meta_path, meta)
            except Exception:
                pass
        finally:
            TASK_QUEUE.task_done()


def _requeue_incomplete_tasks():
    if not PROCESSED_DIR.exists():
        return
    for pdir in PROCESSED_DIR.iterdir():
        if not pdir.is_dir():
            continue
        meta = read_json(pdir / "meta.json") or {}
        status = (meta.get("status") or "").upper()
        defs_status = (meta.get("definitions_status") or "").upper()

        if status == DocumentStatus.AWAITING_OPTIONS:
            continue

        if status in {"QUEUED", "PARSING"}:
            if (pdir / "document.json").exists():
                if not (pdir / "chunks.json").exists():
                    enqueue_task({"type": "rechunk", "processed_dir": pdir})
                else:
                    enqueue_task({"type": "reindex", "processed_dir": pdir})
            else:
                raw_path = find_raw_path(pdir.name)
                if raw_path:
                    enqueue_task({"type": "ingest", "raw_path": raw_path, "processed_dir": pdir})
        elif status == DocumentStatus.CHUNKING:
            enqueue_task({"type": "rechunk", "processed_dir": pdir})
        elif status == DocumentStatus.INDEXING:
            enqueue_task({"type": "reindex", "processed_dir": pdir})

        if defs_status == "RUNNING":
            if (pdir / "chunks.json").exists():
                enqueue_task({"type": "definitions", "processed_dir": pdir})

        ent_status = (meta.get("entitlements_status") or "").upper()
        if ent_status == "RUNNING":
            if (pdir / "chunks.json").exists():
                enqueue_task({"type": "entitlements", "processed_dir": pdir})


def start_workers():
    global WORKER_STARTED
    if WORKER_STARTED:
        return
    workers = int(os.getenv("INGEST_WORKERS", "1"))
    for _ in range(max(workers, 1)):
        t = threading.Thread(target=_ingest_worker, daemon=True)
        t.start()
    _requeue_incomplete_tasks()
    WORKER_STARTED = True
