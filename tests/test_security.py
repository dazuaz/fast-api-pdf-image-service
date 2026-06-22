from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import app
from app.services.document_source import DocumentSourceError, _validate_http_source_url


def _sample_png_bytes() -> bytes:
    image = Image.new("RGB", (2, 2), (255, 255, 255))
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        image.save(handle.name, format="PNG")
        return Path(handle.name).read_bytes()


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.originals = {
            "API_KEY": settings.API_KEY,
            "THUMBNAIL_SERVICE_API_KEY": settings.THUMBNAIL_SERVICE_API_KEY,
            "PROTECT_THUMBNAILS_WITH_API_KEY": settings.PROTECT_THUMBNAILS_WITH_API_KEY,
            "PDF_LOCAL_CACHE_DIR": settings.PDF_LOCAL_CACHE_DIR,
        }
        settings.API_KEY = "top-secret"
        settings.THUMBNAIL_SERVICE_API_KEY = None
        settings.PROTECT_THUMBNAILS_WITH_API_KEY = False
        settings.PDF_LOCAL_CACHE_DIR = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        settings.API_KEY = self.originals["API_KEY"]
        settings.THUMBNAIL_SERVICE_API_KEY = self.originals[
            "THUMBNAIL_SERVICE_API_KEY"
        ]
        settings.PROTECT_THUMBNAILS_WITH_API_KEY = self.originals[
            "PROTECT_THUMBNAILS_WITH_API_KEY"
        ]
        settings.PDF_LOCAL_CACHE_DIR = self.originals["PDF_LOCAL_CACHE_DIR"]
        self.tmpdir.cleanup()

    def test_upload_requires_api_key(self) -> None:
        response = self.client.post(
            "/api/v1/documents/",
            files={"file": ("sample.png", _sample_png_bytes(), "image/png")},
        )

        self.assertEqual(response.status_code, 401)

    def test_upload_accepts_bearer_api_key(self) -> None:
        response = self.client.post(
            "/api/v1/documents/",
            files={"file": ("sample.png", _sample_png_bytes(), "image/png")},
            headers={"Authorization": "Bearer top-secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("document_id", response.json())

    def test_auth_health_requires_valid_api_key(self) -> None:
        unauthorized = self.client.get("/api/v1/health/auth")
        authorized = self.client.get(
            "/api/v1/health/auth",
            headers={"X-API-Key": "top-secret"},
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json(), {"ok": True})

    def test_thumbnail_service_api_key_alias_is_accepted(self) -> None:
        settings.API_KEY = None
        settings.THUMBNAIL_SERVICE_API_KEY = "top-secret"

        response = self.client.get(
            "/api/v1/health/auth",
            headers={"Authorization": "Bearer top-secret"},
        )

        self.assertEqual(response.status_code, 200)

    def test_thumbnail_can_be_protected_with_api_key(self) -> None:
        upload = self.client.post(
            "/api/v1/documents/",
            files={"file": ("sample.png", _sample_png_bytes(), "image/png")},
            headers={"X-API-Key": "top-secret"},
        )
        document_id = upload.json()["document_id"]
        settings.PROTECT_THUMBNAILS_WITH_API_KEY = True

        unauthorized = self.client.get(
            f"/api/v1/documents/{document_id}/pages/1.png",
        )
        authorized = self.client.get(
            f"/api/v1/documents/{document_id}/pages/1.png",
            headers={"X-API-Key": "top-secret"},
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.headers["content-type"], "image/png")

    def test_thumbnail_render_is_cached_after_first_request(self) -> None:
        upload = self.client.post(
            "/api/v1/documents/",
            files={"file": ("sample.png", _sample_png_bytes(), "image/png")},
            headers={"X-API-Key": "top-secret"},
        )
        document_id = upload.json()["document_id"]

        with patch("app.api.routes.documents.render_page_png") as render:
            render.return_value = b"cached-png"
            thumbnail_path = f"/api/v1/documents/{document_id}/pages/1.png"
            first = self.client.get(thumbnail_path)
            second = self.client.get(thumbnail_path)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.content, b"cached-png")
        self.assertEqual(second.content, b"cached-png")
        render.assert_called_once()

    def test_root_includes_security_headers(self) -> None:
        response = self.client.get("/", headers={"X-Forwarded-Proto": "https"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertIn("max-age=63072000", response.headers["strict-transport-security"])

    def test_cors_reflects_localhost_3000_origin(self) -> None:
        if not settings.cors_origins:
            self.skipTest("CORS disabled (e.g. empty CORS_ORIGINS on Vercel)")
        response = self.client.get(
            "/",
            headers={"Origin": "http://localhost:3000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )

    def test_cors_preflight_for_api_post(self) -> None:
        if not settings.cors_origins:
            self.skipTest("CORS disabled (e.g. empty CORS_ORIGINS on Vercel)")
        response = self.client.options(
            "/api/v1/documents/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertIn(response.status_code, (200, 204))
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )


class SettingsTests(unittest.TestCase):
    def test_api_key_uses_thumbnail_service_alias(self) -> None:
        configured = Settings(API_KEY=None, THUMBNAIL_SERVICE_API_KEY="top-secret")

        self.assertEqual(configured.api_key, "top-secret")

    def test_api_key_aliases_must_match_when_both_are_set(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                API_KEY="top-secret",
                THUMBNAIL_SERVICE_API_KEY="different-secret",
            )


class SourceUrlSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.originals = {
            "ALLOW_INSECURE_SOURCE_HTTP": settings.ALLOW_INSECURE_SOURCE_HTTP,
            "BLOCK_PRIVATE_SOURCE_ADDRESSES": settings.BLOCK_PRIVATE_SOURCE_ADDRESSES,
            "SOURCE_URL_ALLOWED_HOSTS": settings.SOURCE_URL_ALLOWED_HOSTS,
        }
        settings.ALLOW_INSECURE_SOURCE_HTTP = False
        settings.BLOCK_PRIVATE_SOURCE_ADDRESSES = True
        settings.SOURCE_URL_ALLOWED_HOSTS = ""

    async def asyncTearDown(self) -> None:
        settings.ALLOW_INSECURE_SOURCE_HTTP = self.originals[
            "ALLOW_INSECURE_SOURCE_HTTP"
        ]
        settings.BLOCK_PRIVATE_SOURCE_ADDRESSES = self.originals[
            "BLOCK_PRIVATE_SOURCE_ADDRESSES"
        ]
        settings.SOURCE_URL_ALLOWED_HOSTS = self.originals["SOURCE_URL_ALLOWED_HOSTS"]

    async def test_private_ip_is_blocked(self) -> None:
        with self.assertRaisesRegex(
            DocumentSourceError,
            "blocked IP address",
        ):
            await _validate_http_source_url("https://127.0.0.1/private.pdf")

    async def test_http_scheme_is_rejected_by_default(self) -> None:
        with self.assertRaisesRegex(
            DocumentSourceError,
            "Unsupported URL scheme",
        ):
            await _validate_http_source_url("http://example.com/file.pdf")

    async def test_host_allowlist_is_enforced(self) -> None:
        settings.SOURCE_URL_ALLOWED_HOSTS = "example.com"

        with self.assertRaisesRegex(DocumentSourceError, "Source host is not allowed"):
            await _validate_http_source_url("https://not-example.org/file.pdf")
