from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class PdfStorageError(Exception):
    pass


async def save_pdf(document_id: str, data: bytes) -> None:
    if settings.S3_BUCKET:
        await _s3_put(document_id, data)
        return
    base = settings.PDF_LOCAL_CACHE_DIR
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{document_id}.bin"
    path.write_bytes(data)


async def load_pdf(document_id: str) -> bytes | None:
    if settings.S3_BUCKET:
        return await _s3_get(document_id)
    path = settings.PDF_LOCAL_CACHE_DIR / f"{document_id}.bin"
    if not path.is_file():
        return None
    return path.read_bytes()


def _s3_key(document_id: str) -> str:
    prefix = settings.S3_KEY_PREFIX.strip("/")
    if prefix:
        return f"{prefix}/{document_id}.bin"
    return f"{document_id}.bin"


def _s3_client():
    kwargs: dict[str, str] = {}
    if settings.S3_REGION:
        kwargs["region_name"] = settings.S3_REGION
    return boto3.client("s3", **kwargs)


async def _s3_put(document_id: str, data: bytes) -> None:
    bucket = settings.S3_BUCKET
    if not bucket:
        raise PdfStorageError("S3 bucket not configured")
    key = _s3_key(document_id)
    client = _s3_client()

    def _put():
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="application/octet-stream",
        )

    try:
        await asyncio.to_thread(_put)
    except (ClientError, BotoCoreError) as e:
        raise PdfStorageError(f"S3 put failed: {e}") from e


async def _s3_get(document_id: str) -> bytes | None:
    bucket = settings.S3_BUCKET
    if not bucket:
        raise PdfStorageError("S3 bucket not configured")
    key = _s3_key(document_id)
    client = _s3_client()

    def _get():
        return client.get_object(Bucket=bucket, Key=key)

    try:
        obj = await asyncio.to_thread(_get)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return None
        raise PdfStorageError(f"S3 get failed: {e}") from e
    except BotoCoreError as e:
        raise PdfStorageError(f"S3 get failed: {e}") from e

    body = obj["Body"]
    return await asyncio.to_thread(body.read)
