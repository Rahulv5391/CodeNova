from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import get_redis

s = get_settings()

router = APIRouter(tags=["health"], prefix="/health")


@router.get("")
async def health():
    return {"status": "ok"}


@router.get("/full")
async def health_full(db: AsyncSession = Depends(get_db)):
    checks: dict = {}

    # Postgres
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Redis
    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Qdrant
    try:
        from qdrant_client import AsyncQdrantClient
        from app.core.config import get_settings

        s = get_settings()
        qc = AsyncQdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key,)
        await qc.get_collections()
        await qc.close()
        checks["qdrant"] = "ok"

    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
