from httpx import AsyncClient

from app.config import get_settings
from app.db import SessionLocal
from app.models import Project
from tests.conftest import register_and_login

PDF_BYTES = b"%PDF-1.4\n%internal recalculate-size fixture\n"


async def _create_project(client: AsyncClient, token: str) -> int:
    response = await client.post(
        "/projects", json={"name": "Internal test"},
        headers={"Authorization": f"Bearer {token}"})
    return response.json()["id"]


async def test_recalculate_size_requires_correct_secret(client: AsyncClient):
    token = await register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/internal/projects/{project_id}/recalculate-size",
        headers={"X-Internal-Secret": "wrong-secret"})

    assert response.status_code == 401


async def test_recalculate_size_requires_secret_header(client: AsyncClient):
    token = await register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(f"/internal/projects/{project_id}/recalculate-size")

    assert response.status_code == 422


async def test_recalculate_size_corrects_drift_from_real_s3_usage(client: AsyncClient):
    token = await register_and_login(client)
    project_id = await _create_project(client, token)
    await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"})

    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        project.total_size_bytes = 999999
        await session.commit()

    response = await client.post(
        f"/internal/projects/{project_id}/recalculate-size",
        headers={"X-Internal-Secret": get_settings().internal_api_secret})

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["total_size_bytes"] == len(PDF_BYTES)
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
    assert project.total_size_bytes == len(PDF_BYTES)


async def test_recalculate_size_for_nonexistent_project_returns_zero(client: AsyncClient):
    response = await client.post(
        "/internal/projects/999999999/recalculate-size",
        headers={"X-Internal-Secret": get_settings().internal_api_secret})

    assert response.status_code == 200
    assert response.json()["total_size_bytes"] == 0
