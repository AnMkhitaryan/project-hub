import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import engine as db_engine
from app.main import app
from app.services import storage


@pytest.fixture(scope="session", autouse=True)
async def _ensure_test_bucket():
    await storage.ensure_bucket_exists()


@pytest.fixture(autouse=True)
async def _clean_database():
    async with db_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users, projects CASCADE"))
    yield
    await db_engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_user(client: AsyncClient) -> dict:
    login = f"user_{uuid.uuid4().hex[:12]}"
    payload = {
        "login": login,
        "email": f"{login}@example.com",
        "password": "supersecret1",
        "repeat_password": "supersecret1",
    }
    response = await client.post("/auth", json=payload)
    assert response.status_code == 201
    return payload


async def register_and_login(client: AsyncClient) -> str:
    user = await register_user(client)
    response = await client.post(
        "/login", json={"login": user["login"], "password": user["password"]})
    return response.json()["access_token"]
