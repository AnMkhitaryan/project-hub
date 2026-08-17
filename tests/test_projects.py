import uuid
from datetime import timedelta

import boto3
import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient
from sqlalchemy import event, select

from app.config import get_settings
from app.db import SessionLocal
from app.db import engine as db_engine
from app.models import Document, Project, ProjectMember, ProjectRole
from app.services.security import create_invite_token
from tests.conftest import register_and_login as _register_and_login


def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url)


async def test_create_project_returns_201_with_body(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.post(
        "/projects",
        json={"name": "Capstone", "description": "A project management API"},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Capstone"
    assert body["description"] == "A project management API"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_project_makes_creator_owner(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.post(
        "/projects",
        json={"name": "Capstone"},
        headers={"Authorization": f"Bearer {token}"},)
    project_id = response.json()["id"]

    async with SessionLocal() as session:
        result = await session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id))
        memberships = result.scalars().all()

    assert len(memberships) == 1
    assert memberships[0].role == ProjectRole.OWNER


async def test_create_project_requires_auth(client: AsyncClient):
    response = await client.post("/projects", json={"name": "Capstone"})

    assert response.status_code == 401


async def _create_projects(client: AsyncClient, token: str, count: int) -> list[int]:
    ids = []
    for i in range(count):
        response = await client.post(
            "/projects",
            json={"name": f"Project {i}"},
            headers={"Authorization": f"Bearer {token}"},)
        ids.append(response.json()["id"])
    return ids


async def _add_document(session, project_id: int, filename: str) -> None:
    session.add(
        Document(
            project_id=project_id,
            filename=filename,
            content_type="application/pdf",
            size_bytes=123,
            s3_key=f"key-{uuid.uuid4().hex}",
        )
    )
    await session.commit()


class _QueryCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, *args, **kwargs):
        self.count += 1


async def test_list_projects_returns_only_own_projects(client: AsyncClient):
    token_a = await _register_and_login(client)
    token_b = await _register_and_login(client)
    await _create_projects(client, token_a, 1)
    await _create_projects(client, token_b, 1)

    response = await client.get("/projects", headers={"Authorization": f"Bearer {token_a}"})

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_projects_includes_documents(client: AsyncClient):
    token = await _register_and_login(client)
    [project_id] = await _create_projects(client, token, 1)
    async with SessionLocal() as session:
        await _add_document(session, project_id, "spec.pdf")

    response = await client.get("/projects", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert body[0]["documents"][0]["filename"] == "spec.pdf"


async def test_list_projects_query_count_does_not_grow_with_project_count(client: AsyncClient):
    token_few = await _register_and_login(client)
    few_ids = await _create_projects(client, token_few, 2)
    token_many = await _register_and_login(client)
    many_ids = await _create_projects(client, token_many, 6)
    async with SessionLocal() as session:
        for project_id in few_ids + many_ids:
            await _add_document(session, project_id, "doc.pdf")

    async def _count_queries(token: str) -> int:
        counter = _QueryCounter()
        event.listen(db_engine.sync_engine, "before_cursor_execute", counter)
        try:
            response = await client.get("/projects", headers={"Authorization": f"Bearer {token}"})
        finally:
            event.remove(db_engine.sync_engine, "before_cursor_execute", counter)
        assert response.status_code == 200
        return counter.count

    few_query_count = await _count_queries(token_few)
    many_query_count = await _count_queries(token_many)

    assert few_query_count == many_query_count


async def _user_id(client: AsyncClient, token: str) -> int:
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return response.json()["id"]


async def _add_membership(project_id: int, user_id: int, role: ProjectRole) -> None:
    async with SessionLocal() as session:
        session.add(ProjectMember(project_id=project_id, user_id=user_id, role=role))
        await session.commit()


async def test_get_project_info_returns_project_for_member(client: AsyncClient):
    token = await _register_and_login(client)
    [project_id] = await _create_projects(client, token, 1)

    response = await client.get(
        f"/project/{project_id}/info", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["id"] == project_id


async def test_get_project_info_404_for_non_member(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    outsider_token = await _register_and_login(client)

    response = await client.get(
        f"/project/{project_id}/info", headers={"Authorization": f"Bearer {outsider_token}"})

    assert response.status_code == 404


async def test_update_project_info_by_participant_changes_updated_at(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    participant_token = await _register_and_login(client)
    participant_id = await _user_id(client, participant_token)
    await _add_membership(project_id, participant_id, ProjectRole.PARTICIPANT)

    before = await client.get(
        f"/project/{project_id}/info", headers={"Authorization": f"Bearer {owner_token}"})
    before_updated_at = before.json()["updated_at"]

    response = await client.put(
        f"/project/{project_id}/info",
        json={"name": "Renamed"},
        headers={"Authorization": f"Bearer {participant_token}"},)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["updated_at"] != before_updated_at


async def test_update_project_info_404_for_non_member(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    outsider_token = await _register_and_login(client)

    response = await client.put(
        f"/project/{project_id}/info",
        json={"name": "Hacked"},
        headers={"Authorization": f"Bearer {outsider_token}"},)

    assert response.status_code == 404


async def test_update_project_info_partial_update_preserves_other_fields(client: AsyncClient):
    token = await _register_and_login(client)
    create_response = await client.post(
        "/projects",
        json={"name": "Original", "description": "Keep me"},
        headers={"Authorization": f"Bearer {token}"},)
    project_id = create_response.json()["id"]

    response = await client.put(
        f"/project/{project_id}/info",
        json={"name": "Updated"},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated"
    assert body["description"] == "Keep me"


async def _add_document_with_s3_object(session, project_id: int, filename: str) -> str:
    s3_key = f"key-{uuid.uuid4().hex}"
    session.add(
        Document(
            project_id=project_id,
            filename=filename,
            content_type="application/pdf",
            size_bytes=5,
            s3_key=s3_key,
        )
    )
    await session.commit()
    _s3_client().put_object(Bucket=get_settings().s3_bucket, Key=s3_key, Body=b"hello")
    return s3_key


async def test_delete_project_by_owner_removes_db_rows_and_s3_objects(client: AsyncClient):
    token = await _register_and_login(client)
    [project_id] = await _create_projects(client, token, 1)
    async with SessionLocal() as session:
        s3_key = await _add_document_with_s3_object(session, project_id, "doc.pdf")

    response = await client.delete(
        f"/project/{project_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204

    async with SessionLocal() as session:
        assert await session.get(Project, project_id) is None
        result = await session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id))
        assert result.scalars().all() == []
        result = await session.execute(select(Document).where(Document.project_id == project_id))
        assert result.scalars().all() == []

    with pytest.raises(ClientError):
        _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=s3_key)


async def test_delete_project_by_participant_returns_403(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    participant_token = await _register_and_login(client)
    participant_id = await _user_id(client, participant_token)
    await _add_membership(project_id, participant_id, ProjectRole.PARTICIPANT)

    response = await client.delete(
        f"/project/{project_id}", headers={"Authorization": f"Bearer {participant_token}"})

    assert response.status_code == 403
    async with SessionLocal() as session:
        assert await session.get(Project, project_id) is not None


async def test_delete_project_by_non_member_returns_404(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    outsider_token = await _register_and_login(client)

    response = await client.delete(
        f"/project/{project_id}", headers={"Authorization": f"Bearer {outsider_token}"})

    assert response.status_code == 404


async def _user_login(client: AsyncClient, token: str) -> str:
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return response.json()["login"]


async def test_invite_by_owner_returns_201_with_participant_role(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_login = await _user_login(client, invitee_token)

    response = await client.post(
        f"/project/{project_id}/invite",
        params={"user": invitee_login},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == project_id
    assert body["role"] == "participant"


async def test_invite_by_participant_returns_403(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    participant_token = await _register_and_login(client)
    participant_id = await _user_id(client, participant_token)
    await _add_membership(project_id, participant_id, ProjectRole.PARTICIPANT)
    invitee_token = await _register_and_login(client)
    invitee_login = await _user_login(client, invitee_token)

    response = await client.post(
        f"/project/{project_id}/invite",
        params={"user": invitee_login},
        headers={"Authorization": f"Bearer {participant_token}"},
    )

    assert response.status_code == 403


async def test_invite_unknown_user_returns_404(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)

    response = await client.post(
        f"/project/{project_id}/invite",
        params={"user": f"nobody_{uuid.uuid4().hex[:12]}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 404


async def test_invite_already_member_returns_409(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_login = await _user_login(client, invitee_token)
    await client.post(
        f"/project/{project_id}/invite",
        params={"user": invitee_login},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.post(
        f"/project/{project_id}/invite",
        params={"user": invitee_login},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_invite_by_non_member_returns_404(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    outsider_token = await _register_and_login(client)
    invitee_token = await _register_and_login(client)
    invitee_login = await _user_login(client, invitee_token)

    response = await client.post(
        f"/project/{project_id}/invite",
        params={"user": invitee_login},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 404


async def _user_email(client: AsyncClient, token: str) -> str:
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return response.json()["email"]


async def test_share_and_join_grants_participant_access(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)

    share_response = await client.get(
        f"/project/{project_id}/share",
        params={"with": invitee_email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert share_response.status_code == 200
    token = share_response.json()["token"]

    join_response = await client.get(
        "/join", params={"token": token}, headers={"Authorization": f"Bearer {invitee_token}"}
    )

    assert join_response.status_code == 201
    body = join_response.json()
    assert body["project_id"] == project_id
    assert body["role"] == "participant"

    access = await client.get(
        f"/project/{project_id}/info", headers={"Authorization": f"Bearer {invitee_token}"}
    )
    assert access.status_code == 200


async def test_share_by_participant_returns_403(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    participant_token = await _register_and_login(client)
    participant_id = await _user_id(client, participant_token)
    await _add_membership(project_id, participant_id, ProjectRole.PARTICIPANT)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)

    response = await client.get(
        f"/project/{project_id}/share",
        params={"with": invitee_email},
        headers={"Authorization": f"Bearer {participant_token}"},
    )

    assert response.status_code == 403


async def test_join_with_tampered_token_returns_400(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)
    share_response = await client.get(
        f"/project/{project_id}/share",
        params={"with": invitee_email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    token = share_response.json()["token"]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    response = await client.get(
        "/join", params={"token": tampered}, headers={"Authorization": f"Bearer {invitee_token}"}
    )

    assert response.status_code == 400


async def test_join_with_expired_token_returns_400(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)

    expired_token = create_invite_token(
        project_id, invitee_email, expires_delta=timedelta(seconds=-1)
    )

    response = await client.get(
        "/join",
        params={"token": expired_token},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )

    assert response.status_code == 400


async def test_join_with_wrong_recipient_email_returns_403(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)
    other_token = await _register_and_login(client)
    share_response = await client.get(
        f"/project/{project_id}/share",
        params={"with": invitee_email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    token = share_response.json()["token"]

    response = await client.get(
        "/join", params={"token": token}, headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 403


async def test_join_already_member_returns_409(client: AsyncClient):
    owner_token = await _register_and_login(client)
    [project_id] = await _create_projects(client, owner_token, 1)
    invitee_token = await _register_and_login(client)
    invitee_email = await _user_email(client, invitee_token)
    share_response = await client.get(
        f"/project/{project_id}/share",
        params={"with": invitee_email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    token = share_response.json()["token"]
    await client.get(
        "/join", params={"token": token}, headers={"Authorization": f"Bearer {invitee_token}"}
    )

    response = await client.get(
        "/join", params={"token": token}, headers={"Authorization": f"Bearer {invitee_token}"}
    )

    assert response.status_code == 409
