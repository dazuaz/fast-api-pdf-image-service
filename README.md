# PDF thumbnail service (FastAPI + Vercel)

Upload a PDF or raster image and get **stable, content-addressed thumbnail URLs**. The `document_id` is the SHA-256 of the file bytes, so the same file always maps to the same paths.

Deploy by linking this repository in the [Vercel dashboard](https://vercel.com/new) or running `vercel --prod` from the project root.

## Open source

Licensed under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and pull request expectations. To report security issues privately, read [SECURITY.md](SECURITY.md).

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Landing page |
| `POST` | `/api/v1/documents/` | Multipart upload (`file` field). Returns `document_id`, `page_count`, and per-page thumbnail URLs. |
| `POST` | `/api/v1/documents/from-url` | Server-side fetch from `https://...` or `s3://bucket/key`, then register document for thumbnail URLs. |
| `GET` | `/api/v1/documents/{document_id}/pages/{page}.png` | PNG thumbnail; `page` is **1-based**. Optional query: `max_width` (default from `DEFAULT_THUMB_MAX_WIDTH`, usually 256). |
| `GET` | `/docs` | OpenAPI (Swagger), enabled locally and optionally in production |

### Deterministic URLs

After upload, thumbnails are served at:

`/api/v1/documents/<64-char-sha256>/pages/<n>.png`

Same bytes ⇒ same `document_id` ⇒ same URLs. Responses use `Cache-Control: public, max-age=31536000, immutable` so CDNs can cache aggressively.

## Project layout

```
app/
├── main.py                 # FastAPI app
├── templates/index.html
├── api/
│   ├── main.py             # Router assembly
│   └── routes/
│       └── documents.py    # Upload + thumbnail routes
├── core/
│   └── config.py           # Settings (env)
└── services/
    ├── document_id.py      # SHA-256 id
    ├── pdf_render.py       # PyMuPDF + Pillow rendering
    ├── pdf_storage.py      # Local disk or S3
    └── document_source.py  # URL / S3 source downloader
```

## Local setup

```bash
uv sync
```

Run the test suite:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

Run with Uvicorn:

```bash
.venv/bin/uvicorn app.main:app --reload --port 5001
```

Or use the Vercel CLI:

```bash
vercel dev
```

## Configuration (environment)

| Variable | Purpose |
|----------|---------|
| `S3_BUCKET` | If set, documents are stored in S3 (recommended in production). |
| `S3_REGION` | Optional AWS region override for S3 client. |
| `S3_KEY_PREFIX` | Key prefix inside bucket (default `documents`). |
| `MAX_UPLOAD_BYTES` | Max multipart upload size (default `4500000`, aligned with Vercel’s ~4.5 MB function body limit). |
| `MAX_SOURCE_DOWNLOAD_BYTES` | Max size when ingesting via `/from-url` (default `100000000`). |
| `API_KEY` | If set, `POST /api/v1/documents/` and `POST /api/v1/documents/from-url` require `X-API-Key: <value>` or `Authorization: Bearer <value>`. |
| `PROTECT_THUMBNAILS_WITH_API_KEY` | If `true`, thumbnail `GET` routes also require the API key. |
| `ENABLE_API_DOCS` | Enables `/docs` and `/openapi.json`. Defaults to `true` locally and `false` on Vercel. |
| `ALLOWED_HOSTS` | Optional comma-separated host allowlist for `TrustedHostMiddleware` (for example `fast-api-pdf-image-service.vercel.app,localhost,127.0.0.1`). |
| `ALLOW_INSECURE_SOURCE_HTTP` | Allows `http://` source URLs when `true`. Default is `false`, so remote ingestion is HTTPS-only. |
| `BLOCK_PRIVATE_SOURCE_ADDRESSES` | Blocks `/from-url` fetches to private, loopback, link-local, multicast, reserved, and unspecified IPs. Default `true`. |
| `SOURCE_URL_ALLOWED_HOSTS` | Optional comma-separated hostname allowlist for `/from-url`; exact hosts and subdomains are accepted. |
| `SOURCE_S3_ALLOWED_BUCKETS` | Optional comma-separated S3 bucket allowlist for `s3://` ingestion. |
| `PDF_LOCAL_CACHE_DIR` | When S3 is **not** configured, files are written under this directory. Default: `.cache/pdfs` locally, **`/tmp/pdf-thumbnail-cache`** when `VERCEL` is set (only `/tmp` is writable on Vercel). |
| `DEFAULT_THUMB_MAX_WIDTH` | Default thumbnail width in pixels (default `256`). |

## Security defaults

- Production docs are disabled by default on Vercel unless `ENABLE_API_DOCS=true`.
- Remote URL ingestion is HTTPS-only by default.
- `/from-url` rejects hosts that resolve to non-public IP space to reduce SSRF risk.
- When `API_KEY` is set, upload and URL-registration endpoints require it.

## Deploying to Vercel

1. Configure AWS credentials for the deployment runtime and set `S3_BUCKET` (plus `S3_REGION` / `S3_KEY_PREFIX` as needed).
2. Deploy:

```bash
pnpm dlx vercel --prod
```

`pyproject.toml` sets `[tool.vercel] entrypoint = "app.main:app"` so Vercel finds the FastAPI app.

## Supported inputs

- **PDF** (PyMuPDF)
- Common **images** (PNG, JPEG via PyMuPDF; other formats via Pillow as a single-page document)

## Notes

- Rendering uses **PyMuPDF** (no separate Poppler install), which fits serverless bundles well.
- Thumbnail **`max_width`** is part of the URL only as the `max_width` query string; different widths are different cache keys.
- `/from-url` avoids request-body upload limits and is better for larger files (still bounded by `MAX_SOURCE_DOWNLOAD_BYTES`).

## Publishing this repository

Before the first push, confirm sensitive paths are **not** tracked: `.env`, `.venv`, `.vercel` (contains project/org IDs), and `.cache` are listed in `.gitignore`. After creating the GitHub repository, you can add a CI status badge to this README using your `owner/repo` slug and the workflow name `CI` (see `.github/workflows/ci.yml`).
