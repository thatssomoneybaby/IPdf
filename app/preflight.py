from __future__ import annotations

from pathlib import Path
from typing import Optional

_TESSERACT_LANG_MAP = {
    "en": "eng",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "nl": "nld",
    "sv": "swe",
    "no": "nor",
    "da": "dan",
    "fi": "fin",
    "pl": "pol",
}


def tesseract_lang(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = str(code).lower()
    if "-" in c:
        c = c.split("-", 1)[0]
    return _TESSERACT_LANG_MAP.get(c, c)


def detect_language(text: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    if not text or len(text.strip()) < 200:
        return None, None, "insufficient_text"
    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        langs = detect_langs(text)
        if not langs:
            return None, None, "no_language_detected"
        top = langs[0]
        return getattr(top, "lang", None), float(getattr(top, "prob", 0.0)), "langdetect"
    except Exception as e:
        return None, None, f"langdetect_error: {e}"


def preflight_pdf(pdf_path: Path) -> dict:
    try:
        import fitz  # PyMuPDF

        with fitz.open(pdf_path) as doc:
            page_count = doc.page_count
            total_chars = 0
            image_pages = 0
            title_guess = None
            first_page_text = ""
            text_samples: list[str] = []
            for page in doc:
                text = page.get_text()
                if not first_page_text:
                    first_page_text = text or ""
                total_chars += len(text or "")
                if page.get_images():
                    image_pages += 1
                if len(text_samples) < 3 and text:
                    text_samples.append(text)

        if first_page_text:
            for line in (ln.strip() for ln in first_page_text.splitlines() if ln.strip()):
                alpha = sum(1 for c in line if c.isalpha())
                if 4 <= len(line) <= 120 and alpha >= 4:
                    title_guess = line
                    break

        lang_text = "\n".join(text_samples)[:4000] if text_samples else ""
        language, language_confidence, language_source = detect_language(lang_text)
        ocr_lang_guess = tesseract_lang(language) if language else None

        avg_chars = (total_chars / page_count) if page_count else 0
        scanned = (avg_chars < 40 and image_pages > 0) or avg_chars < 10
        return {
            "file_type": "pdf",
            "page_count": page_count,
            "avg_chars_per_page": round(avg_chars, 2),
            "image_pages": image_pages,
            "scanned": scanned,
            "text_present": total_chars > 0,
            "title_guess": title_guess,
            "language": language,
            "language_confidence": round(language_confidence, 3) if language_confidence is not None else None,
            "language_source": language_source,
            "ocr_lang_guess": ocr_lang_guess,
        }
    except Exception as e:
        return {"file_type": "pdf", "error": str(e)}


def preflight_file(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return preflight_pdf(path)
    if ext == ".docx":
        return {"file_type": "docx"}
    return {"file_type": ext.replace(".", "") or "unknown"}
