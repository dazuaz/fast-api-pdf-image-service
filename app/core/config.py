import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_pdf_cache_dir() -> Path:
    # Vercel’s serverless filesystem is read-only except /tmp.
    if os.environ.get("VERCEL"):
        return Path("/tmp/pdf-thumbnail-cache")
    return Path(".cache/pdfs")


def _default_enable_api_docs() -> bool:
    return not bool(os.environ.get("VERCEL"))


def _default_cors_origins() -> str:
    # Browser calls from a local dev server (e.g. Next.js on :3000) need CORS.
    if os.environ.get("VERCEL"):
        return ""
    return "http://localhost:3000,http://127.0.0.1:3000"


def _parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "PDF thumbnail service"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Vercel function body limit is ~4.5 MB; keep uploads within that on serverless.
    MAX_UPLOAD_BYTES: int = 4_500_000
    MAX_SOURCE_DOWNLOAD_BYTES: int = 100_000_000
    DEFAULT_THUMB_MAX_WIDTH: int = 256

    API_KEY: str | None = None
    THUMBNAIL_SERVICE_API_KEY: str | None = None
    PROTECT_THUMBNAILS_WITH_API_KEY: bool = False
    ENABLE_API_DOCS: bool = Field(default_factory=_default_enable_api_docs)
    ALLOWED_HOSTS: str = ""
    CORS_ORIGINS: str = Field(default_factory=_default_cors_origins)

    ALLOW_INSECURE_SOURCE_HTTP: bool = False
    BLOCK_PRIVATE_SOURCE_ADDRESSES: bool = True
    SOURCE_URL_ALLOWED_HOSTS: str = ""
    SOURCE_S3_ALLOWED_BUCKETS: str = ""

    # S3 storage backend for documents (recommended in production).
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_KEY_PREFIX: str = "documents"

    PDF_LOCAL_CACHE_DIR: Path = Field(default_factory=_default_pdf_cache_dir)

    @model_validator(mode="after")
    def validate_api_key_aliases(self) -> "Settings":
        if (
            self.API_KEY
            and self.THUMBNAIL_SERVICE_API_KEY
            and self.API_KEY != self.THUMBNAIL_SERVICE_API_KEY
        ):
            raise ValueError(
                "API_KEY and THUMBNAIL_SERVICE_API_KEY must match when both are set",
            )
        return self

    @property
    def api_key(self) -> str | None:
        return self.THUMBNAIL_SERVICE_API_KEY or self.API_KEY

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return _parse_csv(self.ALLOWED_HOSTS)

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return _parse_csv(self.CORS_ORIGINS)

    @property
    def source_url_allowed_hosts(self) -> tuple[str, ...]:
        return _parse_csv(self.SOURCE_URL_ALLOWED_HOSTS)

    @property
    def source_s3_allowed_buckets(self) -> tuple[str, ...]:
        return _parse_csv(self.SOURCE_S3_ALLOWED_BUCKETS)


settings = Settings()
