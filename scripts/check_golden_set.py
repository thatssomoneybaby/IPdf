#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    storage = Path(os.getenv("STORAGE_PATH", root / "storage"))
    processed = storage / "processed"
    if not processed.exists():
        print(f"No processed dir found at {processed}")
        return 1

    doc_ids = []
    if len(sys.argv) > 1:
        doc_ids = sys.argv[1:]
    else:
        env_ids = os.getenv("GOLDEN_DOC_IDS", "")
        doc_ids = [s.strip() for s in env_ids.split(",") if s.strip()]

    if not doc_ids:
        # Default to all processed docs
        doc_ids = [p.name for p in processed.iterdir() if p.is_dir()]

    failures = 0
    for doc_id in doc_ids:
        pdir = processed / doc_id
        print(f"Checking {doc_id}...")
        required = ["document.json", "document_text.txt", "chunks.json", "meta.json", "ingest_log.json"]
        for name in required:
            if not (pdir / name).exists():
                print(f"  ❌ missing {name}")
                failures += 1
        chunks_path = pdir / "chunks.json"
        if chunks_path.exists():
            data = json.loads(chunks_path.read_text(encoding="utf-8"))
            chunks = data.get("chunks") or []
            if not chunks:
                print("  ❌ chunks.json is empty")
                failures += 1
            else:
                # Check page ranges
                bad = [c for c in chunks if c.get("page_start") is None or c.get("page_end") is None]
                if bad:
                    print(f"  ❌ {len(bad)} chunks missing page ranges")
                    failures += 1
        print("  ✅ ok")

    if failures:
        print(f"Failures: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
