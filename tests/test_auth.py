import uuid
from datetime import timedelta

from httpx import AsyncClient

from app.services.security import create_access_token
from tests.conftest import register_user


async def test_register_returns_201_with_public_fields(client: AsyncClient):
    login = f"user_{uuid.uuid4().hex[:12]}"

    response = await client.post(
        "/auth",
        json={
            "login": login,
            "email": f"{login}@example.com",
            "password": "supersecret1",
            "repeat_password": "supersecret1",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["login"] == login
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_login_returns_409(client: AsyncClient):
    user = await register_user(client)

    response = await client.post(
        "/auth",
        json={
            "login": user["login"],
            "email": f"other_{uuid.uuid4().hex[:12]}@example.com",
            "password": "supersecret1",
            "repeat_password": "supersecret1",
        },
    )

    assert response.status_code == 409


async def test_register_password_mismatch_returns_422(client: AsyncClient):
    login = f"user_{uuid.uuid4().hex[:12]}"

    response = await client.post(
        "/auth",
        json={
            "login": login,
            "email": f"{login}@example.com",
            "password": "supersecret1",
            "repeat_password": "somethingelse1",
        },
    )

    assert response.status_code == 422


async def test_login_success(client: AsyncClient):
    user = await register_user(client)

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
    user = await register_user(client)

    response = await client.post(
        "/login", json={"login": user["login"], "password": "wrongpassword1"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "incorrect login or password"


async def _login(client: AsyncClient) -> dict:
    user = await register_user(client)
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


async def test_me_expired_token(client: AsyncClient):
    session = await _login(client)
    valid_response = await client.get(
        "/me", headers={"Authorization": f"Bearer {session['token']}"}
    )
    user_id = valid_response.json()["id"]
    expired_token = create_access_token(user_id=user_id, expires_delta=timedelta(seconds=-1))

    response = await client.get("/me", headers={"Authorization": f"Bearer {expired_token}"})

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
