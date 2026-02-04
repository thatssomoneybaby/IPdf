import os
from pathlib import Path


STORAGE_PATH = os.getenv("STORAGE_PATH", str(Path("storage").resolve()))
RAW_DIR = Path(STORAGE_PATH) / "raw"
PROCESSED_DIR = Path(STORAGE_PATH) / "processed"
TMP_DIR = Path(STORAGE_PATH) / "tmp"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def ensure_dirs() -> None:
    for d in [RAW_DIR, PROCESSED_DIR, TMP_DIR]:
        d.mkdir(parents=True, exist_ok=True)
