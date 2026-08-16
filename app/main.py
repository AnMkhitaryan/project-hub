from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.routers import auth, documents, internal, projects
from app.services import lambda_deploy, storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await storage.ensure_bucket_exists()
    await lambda_deploy.ensure_lambda_deployed()
    yield


app = FastAPI(title="project-hub", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(internal.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}