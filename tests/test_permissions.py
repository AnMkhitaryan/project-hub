import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.models import ProjectMember, ProjectRole
from tests.conftest import register_and_login, register_user

PDF_BYTES = b"%PDF-1.4\n%permission matrix fixture\n"


def _auth(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _user_id(client: AsyncClient, token: str) -> int:
    response = await client.get("/me", headers=_auth(token))
    return response.json()["id"]


async def _add_membership(project_id: int, user_id: int, role: ProjectRole) -> None:
    async with SessionLocal() as session:
        session.add(ProjectMember(project_id=project_id, user_id=user_id, role=role))
        await session.commit()


async def _build_world(client: AsyncClient) -> dict:
    owner_token = await register_and_login(client)
    participant_token = await register_and_login(client)
    non_member_token = await register_and_login(client)
    invitee_payload = await register_user(client)

    project_response = await client.post(
        "/projects", json={"name": "Permission matrix"}, headers=_auth(owner_token))
    project_id = project_response.json()["id"]

    participant_id = await _user_id(client, participant_token)
    await _add_membership(project_id, participant_id, ProjectRole.PARTICIPANT)

    return {
        "owner": owner_token,
        "participant": participant_token,
        "non-member": non_member_token,
        "anonymous": None,
        "project_id": project_id,
        "document_id": None,
        "invitee_login": invitee_payload["login"],
    }


async def _seed_document(client: AsyncClient, world: dict) -> None:
    response = await client.post(
        f"/project/{world['project_id']}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers=_auth(world["owner"]))
    world["document_id"] = response.json()[0]["id"]


async def _get_project_info(client, world, headers):
    return await client.get(f"/project/{world['project_id']}/info", headers=headers)


async def _update_project_info(client, world, headers):
    return await client.put(
        f"/project/{world['project_id']}/info", json={"name": "Updated"}, headers=headers)


async def _invite_member(client, world, headers):
    return await client.post(
        f"/project/{world['project_id']}/invite",
        params={"user": world["invitee_login"]},
        headers=headers)


async def _share_project(client, world, headers):
    return await client.get(
        f"/project/{world['project_id']}/share",
        params={"with": "someone@example.com"},
        headers=headers)


async def _upload_document(client, world, headers):
    return await client.post(
        f"/project/{world['project_id']}/documents",
        files={"files": ("second.pdf", PDF_BYTES, "application/pdf")},
        headers=headers)


async def _list_documents(client, world, headers):
    return await client.get(f"/project/{world['project_id']}/documents", headers=headers)


async def _download_document(client, world, headers):
    return await client.get(f"/document/{world['document_id']}", headers=headers)


async def _replace_document(client, world, headers):
    return await client.put(
        f"/document/{world['document_id']}",
        files={"file": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers=headers)


async def _delete_document(client, world, headers):
    return await client.delete(f"/document/{world['document_id']}", headers=headers)


async def _delete_project(client, world, headers):
    return await client.delete(f"/project/{world['project_id']}", headers=headers)


PERMISSION_MATRIX = {
    "GET /project/{id}/info": (
        _get_project_info, False,
        {"owner": 200, "participant": 200, "non-member": 404, "anonymous": 401}),
    "PUT /project/{id}/info": (
        _update_project_info, False,
        {"owner": 200, "participant": 200, "non-member": 404, "anonymous": 401}),
    "POST /project/{id}/invite": (
        _invite_member, False,
        {"owner": 201, "participant": 403, "non-member": 404, "anonymous": 401}),
    "GET /project/{id}/share": (
        _share_project, False,
        {"owner": 200, "participant": 403, "non-member": 404, "anonymous": 401}),
    "POST /project/{id}/documents": (
        _upload_document, False,
        {"owner": 201, "participant": 201, "non-member": 404, "anonymous": 401}),
    "GET /project/{id}/documents": (
        _list_documents, False,
        {"owner": 200, "participant": 200, "non-member": 404, "anonymous": 401}),
    "GET /document/{id}": (
        _download_document, True,
        {"owner": 200, "participant": 200, "non-member": 404, "anonymous": 401}),
    "PUT /document/{id}": (
        _replace_document, True,
        {"owner": 200, "participant": 200, "non-member": 404, "anonymous": 401}),
    "DELETE /document/{id}": (
        _delete_document, True,
        {"owner": 204, "participant": 204, "non-member": 404, "anonymous": 401}),
    "DELETE /project/{id}": (
        _delete_project, False,
        {"owner": 204, "participant": 403, "non-member": 404, "anonymous": 401}),
}

CASES = [
    (endpoint, role, expected_status)
    for endpoint, (_, _needs_document, expected_by_role) in PERMISSION_MATRIX.items()
    for role, expected_status in expected_by_role.items()
]


@pytest.mark.parametrize("endpoint,role,expected_status", CASES)
async def test_permission_matrix(
        client: AsyncClient, endpoint: str, role: str, expected_status: int):
    world = await _build_world(client)
    action, needs_document, _ = PERMISSION_MATRIX[endpoint]
    if needs_document:
        await _seed_document(client, world)

    response = await action(client, world, _auth(world[role]))

    assert response.status_code == expected_status
