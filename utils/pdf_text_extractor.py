"""Reliable PDF text extraction with a Tesseract OCR fallback."""

from __future__ import annotations

import io
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path


LogCallback = Callable[[str], None]
_ocr_warning_emitted = False


def extract_pdf_text(
    pdf_path: Path,
    max_pages: int,
    *,
    use_ocr: bool = True,
    force_ocr: bool = False,
    min_native_chars: int = 50,
    language: str = "eng",
    dpi: int = 250,
    timeout_seconds: int = 30,
    log: LogCallback | None = None,
) -> str:
    """Extract page text normally, OCRing only pages with inadequate native text."""
    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(str(pdf_path))
        page_count = min(max(0, int(max_pages)), len(reader.pages))
    except Exception as exc:
        if log:
            log(f"[WARNING] Could not open {pdf_path.name} for text extraction: {exc}")
        return ""

    page_texts: list[str] = []
    for page_index in range(page_count):
        try:
            native_text = reader.pages[page_index].extract_text() or ""
        except Exception:
            native_text = ""

        if not force_ocr and _meaningful_character_count(native_text) >= max(0, min_native_chars):
            page_texts.append(native_text)
            continue

        ocr_text = _ocr_page(
            pdf_path,
            page_index,
            language=language,
            dpi=dpi,
            timeout_seconds=timeout_seconds,
            log=log,
        ) if use_ocr else ""
        page_texts.append(ocr_text or native_text)

    return "\n".join(page_texts)


def _meaningful_character_count(text: str) -> int:
    return sum(1 for char in (text or "") if char.isalnum())


def _ocr_page(
    pdf_path: Path,
    page_index: int,
    *,
    language: str,
    dpi: int,
    timeout_seconds: int,
    log: LogCallback | None,
) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image

        tesseract_cmd = find_tesseract()
        if tesseract_cmd is None:
            _warn_once(log, "OCR fallback is unavailable because Tesseract was not found")
            return ""

        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
        _configure_tessdata(tesseract_cmd)
        zoom = max(1.0, int(dpi) / 72.0)

        with fitz.open(str(pdf_path)) as document:
            if page_index >= document.page_count:
                return ""
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                if log:
                    log(f"OCR reading page {page_index + 1} of {pdf_path.name}...")
                return pytesseract.image_to_string(
                    image,
                    lang=language,
                    timeout=max(1, int(timeout_seconds)),
                ).strip()
    except Exception as exc:
        _warn_once(log, f"OCR fallback could not read {pdf_path.name}: {exc}")
        return ""


def find_tesseract() -> Path | None:
    """Find Tesseract in development, installed, and PyInstaller locations."""
    project_root = Path(__file__).resolve().parents[1]
    executable_root = Path(sys.executable).resolve().parent
    bundle_root_value = getattr(sys, "_MEIPASS", None)
    bundle_root = Path(bundle_root_value) if bundle_root_value else None
    local_app_data = os.environ.get("LOCALAPPDATA")

    candidates: list[Path | None] = [
        _as_path(os.environ.get("WVPUC0_TESSERACT_PATH")),
        _as_path(shutil.which("tesseract")),
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        Path(local_app_data, "Programs", "Tesseract-OCR", "tesseract.exe") if local_app_data else None,
        project_root / "tesseract" / "tesseract.exe",
        project_root / "Tesseract-OCR" / "tesseract.exe",
        executable_root / "tesseract" / "tesseract.exe",
        executable_root / "Tesseract-OCR" / "tesseract.exe",
        bundle_root / "tesseract" / "tesseract.exe" if bundle_root else None,
        bundle_root / "Tesseract-OCR" / "tesseract.exe" if bundle_root else None,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def _as_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _configure_tessdata(tesseract_cmd: Path) -> None:
    tessdata = tesseract_cmd.resolve().parent / "tessdata"
    if tessdata.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)


def _warn_once(log: LogCallback | None, message: str) -> None:
    global _ocr_warning_emitted
    if not _ocr_warning_emitted:
        if log:
            log(f"[WARNING] {message}")
        _ocr_warning_emitted = True
