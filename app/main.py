from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.routers import auth, projects

app = FastAPI(title="project-hub")
app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}