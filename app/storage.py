from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import UploadFile, HTTPException

from config import RAW_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: dict) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path: Path):
    import json

    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_filename(name: Optional[str]) -> str:
    if not name:
        return "upload.bin"
    return Path(name).name or "upload.bin"


def stream_upload_to_temp(upload: UploadFile, max_bytes: int) -> tuple[Path, str, int]:
    tmp_path: Optional[Path] = None
    try:
        hasher = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File too large (>{max_bytes // (1024 * 1024)} MB)")
                hasher.update(chunk)
                tmp.write(chunk)
        return tmp_path, hasher.hexdigest(), size
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def find_raw_path(doc_id: str) -> Optional[Path]:
    rdir = RAW_DIR / doc_id
    if not rdir.exists():
        return None
    files = [p for p in rdir.iterdir() if p.is_file()]
    if not files:
        return None
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    if pdfs:
        return sorted(pdfs)[0]
    return sorted(files)[0]


def append_feedback(processed_dir: Path, entry: dict) -> None:
    feedback_path = processed_dir / "feedback.json"
    feedback = read_json(feedback_path) or {"entries": []}
    feedback["entries"].append(entry)
    write_json(feedback_path, feedback)
