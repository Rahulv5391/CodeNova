"""
CodeNavigator — FastAPI application entry point.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import health, repositories, auth, chat, docs, pull_request
from app.core.config import get_settings
from app.core.database import create_tables
from app.core.redis import close_redis, get_redis
from app.services.graph_store import close_driver, create_indexes
from app.services.vector_store import ensure_collection

settings = get_settings()

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting CodeNavigator API…")

    # Create DB tables (idempotent)
    await create_tables()
    logger.info("Database tables ensured ✓")

    # Warm Redis connection
    await get_redis()
    logger.info("Redis connected ✓")

    # Ensure Neo4j indexes
    try:
        await create_indexes()
        logger.info("Neo4j indexes ensured ✓")
    except Exception as exc:
        logger.warning(f"Neo4j not available at startup (will retry on use): {exc}")

    # Qdrant Collection
    await ensure_collection()
    logger.info("Qdrant Collection Ensured ✓")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down…")
    await close_redis()
    await close_driver()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeNavigator API",
        description="AI Codebase Navigator & Autonomous GitHub Engineering Assistant",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url="/redoc" if settings.is_dev else None,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled error on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = "/api/v1"
    app.include_router(health.router)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(repositories.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(docs.router, prefix=prefix)
    app.include_router(pull_request.router, prefix=prefix)

    return app


app = create_app()
