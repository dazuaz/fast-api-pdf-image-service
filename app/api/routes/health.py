from fastapi import APIRouter, Depends

from app.api.dependencies.security import require_api_key

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/auth", dependencies=[Depends(require_api_key)])
async def check_authenticated_health():
    return {"ok": True}
