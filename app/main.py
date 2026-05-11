from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.core.security import apply_security_headers

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Deterministic PNG thumbnails for PDFs and images, deployed on Vercel.",
    version=settings.VERSION,
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)

if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

app.include_router(api_router, prefix=settings.API_V1_STR)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(request, response)
    return response


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "docs_enabled": settings.ENABLE_API_DOCS,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=5001, reload=True)
