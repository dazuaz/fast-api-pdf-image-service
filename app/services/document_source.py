from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin
from urllib.parse import urlparse

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class DocumentSourceError(Exception):
    pass


_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


async def load_from_source_url(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        return await _load_from_s3_url(parsed.netloc, parsed.path.lstrip("/"))
    if parsed.scheme in _allowed_http_schemes():
        return await _load_from_http_url(url)
    raise DocumentSourceError("Unsupported URL scheme. Use https://... or s3://bucket/key")


async def _load_from_http_url(url: str) -> bytes:
    limit = settings.MAX_SOURCE_DOWNLOAD_BYTES
    timeout = httpx.Timeout(120.0, connect=15.0)
    next_url = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for redirect_count in range(_MAX_REDIRECTS + 1):
            await _validate_http_source_url(next_url)
            async with client.stream("GET", next_url) as resp:
                if resp.status_code in _REDIRECT_STATUS_CODES:
                    location = resp.headers.get("location")
                    if not location:
                        raise DocumentSourceError("Source URL redirect did not include a location")
                    if redirect_count >= _MAX_REDIRECTS:
                        raise DocumentSourceError("Source URL redirected too many times")
                    next_url = urljoin(str(resp.url), location)
                    continue
                if resp.status_code >= 400:
                    raise DocumentSourceError(f"Source URL returned HTTP {resp.status_code}")
                content_length = resp.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > limit:
                            raise DocumentSourceError(
                                f"Source file exceeds MAX_SOURCE_DOWNLOAD_BYTES ({limit})",
                            )
                    except ValueError:
                        pass
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise DocumentSourceError(
                            f"Source file exceeds MAX_SOURCE_DOWNLOAD_BYTES ({limit})",
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
    raise DocumentSourceError("Source URL redirected too many times")


def _s3_client():
    kwargs: dict[str, str] = {}
    if settings.S3_REGION:
        kwargs["region_name"] = settings.S3_REGION
    return boto3.client("s3", **kwargs)


async def _load_from_s3_url(bucket: str, key: str) -> bytes:
    if not bucket or not key:
        raise DocumentSourceError("Invalid s3:// URL. Expected s3://bucket/key")
    allowed_buckets = settings.source_s3_allowed_buckets
    if allowed_buckets and bucket not in allowed_buckets:
        raise DocumentSourceError("Source bucket is not allowed")
    client = _s3_client()

    def _get():
        return client.get_object(Bucket=bucket, Key=key)

    try:
        obj = await asyncio.to_thread(_get)
    except (ClientError, BotoCoreError) as e:
        raise DocumentSourceError(f"Failed to download from s3:// URL: {e}") from e

    body = obj["Body"]
    data = await asyncio.to_thread(body.read)
    if len(data) > settings.MAX_SOURCE_DOWNLOAD_BYTES:
        raise DocumentSourceError(
            f"Source file exceeds MAX_SOURCE_DOWNLOAD_BYTES ({settings.MAX_SOURCE_DOWNLOAD_BYTES})",
        )
    return data


def _allowed_http_schemes() -> set[str]:
    if settings.ALLOW_INSECURE_SOURCE_HTTP:
        return {"http", "https"}
    return {"https"}


async def _validate_http_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _allowed_http_schemes():
        allowed = "http(s)" if settings.ALLOW_INSECURE_SOURCE_HTTP else "https"
        raise DocumentSourceError(f"Unsupported URL scheme. Use {allowed}://...")
    if not parsed.hostname:
        raise DocumentSourceError("Source URL must include a hostname")
    if parsed.username or parsed.password:
        raise DocumentSourceError("Source URL must not include userinfo")

    hostname = parsed.hostname.rstrip(".").lower()
    allowed_hosts = settings.source_url_allowed_hosts
    if allowed_hosts and not _host_is_allowed(hostname, allowed_hosts):
        raise DocumentSourceError("Source host is not allowed")
    if settings.BLOCK_PRIVATE_SOURCE_ADDRESSES:
        await _ensure_public_host(hostname)


def _host_is_allowed(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    for allowed_host in allowed_hosts:
        normalized = allowed_host.rstrip(".").lower()
        if hostname == normalized or hostname.endswith(f".{normalized}"):
            return True
    return False


async def _ensure_public_host(hostname: str) -> None:
    addresses = await _resolve_ip_addresses(hostname)
    if not addresses:
        raise DocumentSourceError("Source hostname did not resolve")
    for address in addresses:
        if _is_blocked_ip_address(address):
            raise DocumentSourceError("Source URL resolved to a blocked IP address")


async def _resolve_ip_addresses(hostname: str) -> set[str]:
    try:
        ipaddress.ip_address(hostname)
        return {hostname}
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as e:
        raise DocumentSourceError("Source hostname could not be resolved") from e
    return {entry[4][0] for entry in addrinfo}


def _is_blocked_ip_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ),
    )
