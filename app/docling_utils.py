from __future__ import annotations

from pathlib import Path
from typing import Optional


def try_import_docling():
    try:
        import docling  # type: ignore

        return docling
    except Exception:
        return None


def extract_with_pymupdf(pdf_path: Path):
    try:
        import fitz  # PyMuPDF

        page_texts: list[str] = []
        with fitz.open(pdf_path) as doc:
            page_count = doc.page_count
            for page in doc:
                page_texts.append(page.get_text())
        version = getattr(fitz, "__version__", None)
        return (page_texts, page_count, version)
    except Exception:
        return ([], None, None)


def canonical_from_pymupdf(page_texts: list[str]):
    blocks = []
    for i, text in enumerate(page_texts, start=1):
        blk = {
            "block_id": f"p{i}",
            "type": "paragraph",
            "text": text or "",
            "page_start": i,
            "page_end": i,
            # bbox unknown in fallback
        }
        blocks.append(blk)
    pages = [{"page": i} for i in range(1, len(page_texts) + 1)]
    return pages, blocks


def build_docling_converter_with_ocr(ocr_langs_iso: list[str], ocr_langs_tess: list[str], force_full_page: bool):
    try:
        from docling.datamodel.base_models import InputFormat  # type: ignore
        from docling.datamodel.pipeline_options import PdfPipelineOptions  # type: ignore
        from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
    except Exception:
        return None, None

    ocr_engine = "default"
    try:
        pipeline_opts = PdfPipelineOptions()
    except Exception:
        return None, None

    if hasattr(pipeline_opts, "do_ocr"):
        pipeline_opts.do_ocr = True
    if hasattr(pipeline_opts, "force_full_page_ocr"):
        pipeline_opts.force_full_page_ocr = force_full_page

    try:
        if hasattr(pipeline_opts, "ocr_options") and pipeline_opts.ocr_options is not None:
            if hasattr(pipeline_opts.ocr_options, "lang"):
                pipeline_opts.ocr_options.lang = ocr_langs_iso
            if hasattr(pipeline_opts.ocr_options, "force_full_page_ocr"):
                pipeline_opts.ocr_options.force_full_page_ocr = force_full_page
        else:
            raise AttributeError
    except Exception:
        try:
            from docling.datamodel.pipeline_options import TesseractCliOcrOptions  # type: ignore

            pipeline_opts.ocr_options = TesseractCliOcrOptions(lang=ocr_langs_tess)
            ocr_engine = "tesseract_cli"
        except Exception:
            try:
                from docling.datamodel.pipeline_options import TesseractOcrOptions  # type: ignore

                pipeline_opts.ocr_options = TesseractOcrOptions(lang=ocr_langs_tess)
                ocr_engine = "tesseract"
            except Exception:
                return None, None

        if hasattr(pipeline_opts.ocr_options, "force_full_page_ocr"):
            pipeline_opts.ocr_options.force_full_page_ocr = force_full_page

    try:
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)})
        return converter, ocr_engine
    except Exception:
        return None, None


def try_docling_to_canonical(dl, src_path: Path, converter=None):
    """Best-effort Docling integration to build canonical pages/blocks.

    Returns tuple (pages, blocks, page_count, adapter_used) or raises.
    """
    pages = []
    blocks = []
    page_count = None
    adapter_used: Optional[str] = None

    try:
        if converter is not None and hasattr(converter, "convert"):
            ddoc = converter.convert(str(src_path))  # type: ignore[attr-defined]
            adapter_used = "DocumentConverter.convert+ocr"
        else:
            ddoc = None
    except Exception:
        ddoc = None

    try:
        if ddoc is None and hasattr(dl, "convert_pdf"):
            ddoc = dl.convert_pdf(str(src_path))  # type: ignore[attr-defined]
            adapter_used = "convert_pdf"
    except Exception:
        ddoc = None

    if ddoc is None:
        try:
            converter_cls = None
            try:
                from docling.document_converter import DocumentConverter as _DC  # type: ignore

                converter_cls = _DC
            except Exception:
                converter_cls = getattr(dl, "DocumentConverter", None)

            if converter_cls is not None:
                converter = converter_cls()  # type: ignore
                if hasattr(converter, "convert"):
                    ddoc = converter.convert(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.convert"
                elif hasattr(converter, "run"):
                    ddoc = converter.run(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.run"
                elif hasattr(converter, "process"):
                    ddoc = converter.process(str(src_path))  # type: ignore
                    adapter_used = "DocumentConverter.process"
                else:
                    ddoc = None
        except Exception:
            ddoc = None

    if ddoc is None:
        try:
            pipeline_cls = getattr(dl, "SimplePipeline", None) or getattr(dl, "Pipeline", None)
            if pipeline_cls is None:
                raise RuntimeError("Docling pipeline not found")
            pipeline = pipeline_cls()
            ddoc = pipeline.run(str(src_path))  # type: ignore
            adapter_used = f"{getattr(pipeline_cls, '__name__', 'Pipeline')}.run"
        except Exception as e:
            raise RuntimeError(f"Docling parse failed: {e}")

    def _cell_text(cell) -> str:
        if cell is None:
            return ""
        if isinstance(cell, (str, int, float)):
            return str(cell)
        if isinstance(cell, dict):
            for k in ("text", "content", "value"):
                if k in cell and cell[k] is not None:
                    return str(cell[k])
        for attr in ("text", "content", "value"):
            if hasattr(cell, attr):
                val = getattr(cell, attr)
                if val is not None:
                    return str(val)
        return str(cell)

    def _rows_from_table_obj(table_obj) -> Optional[list[list[str]]]:
        if table_obj is None:
            return None
        rows = None
        if isinstance(table_obj, dict):
            rows = table_obj.get("rows") or table_obj.get("cells")
        elif isinstance(table_obj, list):
            rows = table_obj
        else:
            rows = getattr(table_obj, "rows", None) or getattr(table_obj, "cells", None)

        if rows is None:
            return None

        out_rows: list[list[str]] = []
        for row in rows:
            if isinstance(row, dict):
                cells = row.get("cells") or row.get("row") or list(row.values())
            elif isinstance(row, (list, tuple)):
                cells = row
            else:
                cells = getattr(row, "cells", None) or row
            if not isinstance(cells, (list, tuple)):
                cells = [cells]
            out_rows.append([_cell_text(c) for c in cells])
        return out_rows if out_rows else None

    def _extract_table_rows(b, btype: str) -> Optional[list[list[str]]]:
        if "table" not in (btype or "").lower():
            return None
        table_obj = getattr(b, "table", None)
        rows = _rows_from_table_obj(table_obj)
        if rows:
            return rows
        rows = _rows_from_table_obj(getattr(b, "rows", None) or getattr(b, "cells", None))
        if rows:
            return rows
        content = getattr(b, "content", None)
        rows = _rows_from_table_obj(content)
        return rows

    try:
        if hasattr(ddoc, "pages"):
            p_list = list(getattr(ddoc, "pages"))
            page_count = len(p_list)
            for idx, p in enumerate(p_list, start=1):
                pages.append({"page": idx})
                p_blocks = getattr(p, "blocks", []) or []
                for bi, b in enumerate(p_blocks):
                    text = getattr(b, "text", None) or getattr(b, "content", "")
                    btype = getattr(b, "type", None) or getattr(b, "kind", "paragraph")
                    bbox = getattr(b, "bbox", None)
                    table_rows = _extract_table_rows(b, str(btype))
                    blocks.append(
                        {
                            "block_id": f"p{idx}_b{bi}",
                            "type": str(btype),
                            "text": str(text) if text is not None else "",
                            "page_start": idx,
                            "page_end": idx,
                            "bbox": bbox,
                            **({"table": {"rows": table_rows}} if table_rows else {}),
                        }
                    )
        elif hasattr(ddoc, "blocks"):
            b_list = list(getattr(ddoc, "blocks"))
            max_page = 0
            for bi, b in enumerate(b_list):
                pg = getattr(b, "page", None) or getattr(b, "page_no", None) or 1
                max_page = max(max_page, int(pg))
                text = getattr(b, "text", None) or getattr(b, "content", "")
                btype = getattr(b, "type", None) or getattr(b, "kind", "paragraph")
                bbox = getattr(b, "bbox", None)
                table_rows = _extract_table_rows(b, str(btype))
                blocks.append(
                    {
                        "block_id": f"b{bi}",
                        "type": str(btype),
                        "text": str(text) if text is not None else "",
                        "page_start": int(pg),
                        "page_end": int(pg),
                        "bbox": bbox,
                        **({"table": {"rows": table_rows}} if table_rows else {}),
                    }
                )
            page_count = max_page or None
            pages = [{"page": i} for i in range(1, (page_count or 0) + 1)]
        else:
            raise RuntimeError("Docling document lacks pages/blocks attributes")
    except Exception as e:
        raise RuntimeError(f"Docling canonicalization failed: {e}")

    return pages, blocks, page_count, adapter_used
