import os
from urllib.parse import urljoin

import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return urljoin(BACKEND_URL.rstrip("/") + "/", path.lstrip("/"))


def fetch_documents():
    try:
        r = requests.get(api_url("/documents"), timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []


def fetch_document(doc_id: str):
    r = requests.get(api_url(f"/documents/{doc_id}"), timeout=10)
    if not r.ok:
        return None
    return r.json()


def fetch_chunks(doc_id: str):
    try:
        r = requests.get(api_url(f"/documents/{doc_id}/chunks"), timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []


def fetch_chunks_json(link: str):
    try:
        r = requests.get(api_url(link), timeout=20)
        return r.json() if r.ok else None
    except Exception:
        return None


def post_rechunk(doc_id: str):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/rechunk"), timeout=10)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_reindex(doc_id: str):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/reindex"), timeout=10)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_process(doc_id: str, options: dict):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/process"), json=options, timeout=20)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_rename(doc_id: str, display_name: str | None):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/rename"), json={"display_name": display_name}, timeout=10)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_feedback(doc_id: str, payload: dict):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/feedback"), json=payload, timeout=10)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_extract_definitions(doc_id: str):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/extract/definitions"), timeout=20)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)


def post_extract_entitlements(doc_id: str):
    try:
        r = requests.post(api_url(f"/documents/{doc_id}/extract/entitlements"), timeout=20)
        return r.ok, r.json() if r.ok else r.text
    except Exception as e:
        return False, str(e)
