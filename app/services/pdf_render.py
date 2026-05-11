from __future__ import annotations

import io
from typing import Final

import fitz
from PIL import Image

_PDF_MAGIC: Final[bytes] = b"%PDF"
_PNG_MAGIC: Final[bytes] = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final[bytes] = b"\xff\xd8\xff"


class RenderError(Exception):
    pass


def page_count(data: bytes) -> int:
    kind, doc = _open_document(data)
    try:
        if kind == "pil":
            return 1
        return doc.page_count
    finally:
        if kind == "fitz":
            doc.close()


def render_page_png(data: bytes, page_index: int, max_width: int) -> bytes:
    if page_index < 0:
        raise RenderError("Invalid page index")
    if max_width < 16 or max_width > 4096:
        raise RenderError("max_width must be between 16 and 4096")

    kind, doc = _open_document(data)
    try:
        if kind == "pil":
            if page_index != 0:
                raise RenderError("Image documents have a single page")
            return _pil_thumbnail_png(doc, max_width)
        if page_index >= doc.page_count:
            raise RenderError("Page out of range")
        page = doc.load_page(page_index)
        pix = page.get_pixmap(
            matrix=fitz.Matrix(1, 1),
            alpha=False,
        )
        if pix.width > max_width:
            scale = max_width / pix.width
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        if kind == "fitz":
            doc.close()


def _open_document(data: bytes) -> tuple[str, fitz.Document | Image.Image]:
    if data.startswith(_PDF_MAGIC):
        return "fitz", fitz.open(stream=data, filetype="pdf")
    if data.startswith(_PNG_MAGIC):
        return "fitz", fitz.open(stream=data, filetype="png")
    if data.startswith(_JPEG_MAGIC):
        return "fitz", fitz.open(stream=data, filetype="jpeg")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return "pil", img.convert("RGB")
    except OSError as e:
        raise RenderError("Unsupported or corrupt document") from e


def _pil_thumbnail_png(img: Image.Image, max_width: int) -> bytes:
    w, h = img.size
    if w > max_width:
        new_h = max(1, int(h * (max_width / w)))
        img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
