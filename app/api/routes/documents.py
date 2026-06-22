from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.dependencies.security import require_api_key, require_thumbnail_api_key
from app.core.config import settings
from app.services.document_id import content_document_id
from app.services.document_source import DocumentSourceError, load_from_source_url
from app.services.pdf_render import RenderError, page_count, render_page_png
from app.services.pdf_storage import (
    PdfStorageError,
    load_pdf,
    load_thumbnail_png,
    save_pdf,
    save_thumbnail_png,
)

router = APIRouter(prefix="/documents", tags=["documents"])

_DOCUMENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceUrlRequest(BaseModel):
    url: str


def _require_document_id(document_id: str) -> None:
    if not _DOCUMENT_ID_RE.match(document_id):
        raise HTTPException(
            status_code=400,
            detail="document_id must be a 64-character lowercase hex SHA-256 digest",
        )


@router.post("/", dependencies=[Depends(require_api_key)])
async def register_document(file: UploadFile = File(...)):
    """
    Upload a PDF or raster image. The response includes a **document_id** (SHA-256 of the file bytes)
    and deterministic thumbnail URLs: `/api/v1/documents/{document_id}/pages/{page}.png`.
    """
    data = await file.read()
    return await _register_document_bytes(data, enforce_upload_limit=True)


@router.post("/from-url", dependencies=[Depends(require_api_key)])
async def register_document_from_url(payload: SourceUrlRequest):
    """
    Fetch a document from a URL and register it for deterministic thumbnail URLs.
    Supports:
    - https://... (including pre-signed S3 URLs)
    - s3://bucket/key (requires AWS credentials in runtime)
    """
    try:
        data = await load_from_source_url(payload.url)
    except DocumentSourceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _register_document_bytes(
        data,
        enforce_upload_limit=False,
    )


async def _register_document_bytes(
    data: bytes,
    enforce_upload_limit: bool = True,
):
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if enforce_upload_limit and len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds MAX_UPLOAD_BYTES ({settings.MAX_UPLOAD_BYTES})",
        )
    document_id = content_document_id(data)
    try:
        n_pages = page_count(data)
    except RenderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        await save_pdf(document_id, data)
    except PdfStorageError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    base = settings.API_V1_STR
    return {
        "document_id": document_id,
        "page_count": n_pages,
        "pages": [
            {
                "page": p + 1,
                "url": f"{base}/documents/{document_id}/pages/{p + 1}.png",
            }
            for p in range(n_pages)
        ],
    }


@router.get("/{document_id}/pages/{page}.png")
async def get_page_thumbnail(
    document_id: str,
    page: int,
    max_width: int | None = None,
    _: None = Depends(require_thumbnail_api_key),
):
    """
    Render a page thumbnail as PNG. **page** is 1-based. Same document and page always yields the
    same URL; use `max_width` only when you need a different resolution (cached separately per URL).
    """
    _require_document_id(document_id)
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    mw = max_width if max_width is not None else settings.DEFAULT_THUMB_MAX_WIDTH

    try:
        cached = await load_thumbnail_png(document_id, page, mw)
    except PdfStorageError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if cached is not None:
        return _thumbnail_response(cached)

    try:
        data = await load_pdf(document_id)
    except PdfStorageError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown document_id — upload first or register via /from-url.",
        )
    try:
        png = render_page_png(data, page - 1, mw)
    except RenderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        await save_thumbnail_png(document_id, page, mw, png)
    except PdfStorageError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return _thumbnail_response(png)


def _thumbnail_response(png: bytes):
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
