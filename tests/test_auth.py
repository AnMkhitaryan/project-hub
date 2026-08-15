import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register(client: AsyncClient) -> dict:
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


async def test_login_success(client: AsyncClient):
    user = await _register(client)

    response = await client.post(
        "/login", json={"login": user["login"], "password": user["password"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_unknown_user(client: AsyncClient):
    response = await client.post(
        "/login", json={"login": f"nobody_{uuid.uuid4().hex[:12]}", "password": "whatever1"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "incorrect login or password"


async def test_login_wrong_password(client: AsyncClient):
    user = await _register(client)

    response = await client.post(
        "/login", json={"login": user["login"], "password": "wrongpassword1"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "incorrect login or password"


async def _login(client: AsyncClient) -> dict:
    user = await _register(client)
    response = await client.post(
        "/login", json={"login": user["login"], "password": user["password"]}
    )
    return {"user": user, "token": response.json()["access_token"]}


async def test_me_no_token(client: AsyncClient):
    response = await client.get("/me")

    assert response.status_code == 401


async def test_me_garbage_token(client: AsyncClient):
    response = await client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


async def test_me_valid_token(client: AsyncClient):
    session = await _login(client)

    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {session['token']}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["login"] == session["user"]["login"]
    assert "password" not in body
    assert "password_hash" not in body
