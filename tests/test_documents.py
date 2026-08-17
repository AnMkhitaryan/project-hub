import boto3
import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Document, Project
from tests.conftest import register_and_login as _register_and_login


def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url)


async def _create_project(client: AsyncClient, token: str) -> int:
    response = await client.post(
        "/projects", json={"name": "Docs test"}, headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()["id"]


PDF_BYTES = b"%PDF-1.4\n%fake pdf content for testing\n"
PDF_BYTES_V2 = b"%PDF-1.4\n%replaced pdf content, longer than the original\n"
EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00fake exe content"
DOCX_BYTES = b"PK\x03\x04fake docx content for testing"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_BYTES = b"just plain text, not a real document"


async def test_upload_document_returns_201_with_metadata(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 201
    body = response.json()
    assert len(body) == 1
    doc = body[0]
    assert doc["filename"] == "report.pdf"
    assert doc["content_type"] == "application/pdf"
    assert doc["size_bytes"] == len(PDF_BYTES)
    assert "id" in doc
    assert "uploaded_at" in doc


async def test_upload_document_object_exists_in_bucket(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = response.json()[0]["id"]

    async with SessionLocal() as session:
        document = await session.get(Document, doc_id)
        s3_key = document.s3_key

    head = _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=s3_key)
    assert head["ContentLength"] == len(PDF_BYTES)


async def test_upload_rejects_exe_renamed_to_pdf(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("totally_a.pdf", EXE_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 415


async def test_upload_docx_document_returns_201_with_metadata(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": (
            "report.docx", DOCX_BYTES,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 201
    doc = response.json()[0]
    assert doc["filename"] == "report.docx"
    assert doc["content_type"] == DOCX_CONTENT_TYPE
    assert doc["size_bytes"] == len(DOCX_BYTES)

    async with SessionLocal() as session:
        document = await session.get(Document, doc["id"])
        s3_key = document.s3_key
    head = _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=s3_key)
    assert head["ContentLength"] == len(DOCX_BYTES)


async def test_upload_rejects_plain_text_file(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("notes.pdf", TEXT_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 415


async def test_upload_multiple_files_at_once(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files=[
            ("files", ("a.pdf", PDF_BYTES, "application/pdf")),
            ("files", ("b.pdf", PDF_BYTES, "application/pdf")),
        ],
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert len(response.json()) == 2


async def test_upload_requires_membership(client: AsyncClient):
    owner_token = await _register_and_login(client)
    project_id = await _create_project(client, owner_token)
    outsider_token = await _register_and_login(client)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {outsider_token}"},)

    assert response.status_code == 404


async def test_list_documents_returns_metadata_for_member(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    await client.post(
        f"/project/{project_id}/documents",
        files=[
            ("files", ("a.pdf", PDF_BYTES, "application/pdf")),
            ("files", ("b.pdf", PDF_BYTES, "application/pdf")),
        ],
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        f"/project/{project_id}/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert {doc["filename"] for doc in body} == {"a.pdf", "b.pdf"}


async def test_list_documents_requires_membership(client: AsyncClient):
    owner_token = await _register_and_login(client)
    project_id = await _create_project(client, owner_token)
    outsider_token = await _register_and_login(client)

    response = await client.get(
        f"/project/{project_id}/documents", headers={"Authorization": f"Bearer {outsider_token}"})

    assert response.status_code == 404


async def test_download_document_returns_intact_content(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]

    response = await client.get(
        f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="report.pdf"' in response.headers["content-disposition"]


async def test_download_document_requires_membership(client: AsyncClient):
    owner_token = await _register_and_login(client)
    project_id = await _create_project(client, owner_token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {owner_token}"},)
    doc_id = upload_response.json()[0]["id"]
    outsider_token = await _register_and_login(client)

    response = await client.get(
        f"/document/{doc_id}", headers={"Authorization": f"Bearer {outsider_token}"})

    assert response.status_code == 404


async def test_download_nonexistent_document_returns_404(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.get(
        "/document/999999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_replace_document_content_updates_metadata_and_storage(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]
    async with SessionLocal() as session:
        old_s3_key = (await session.get(Document, doc_id)).s3_key

    response = await client.put(
        f"/document/{doc_id}",
        files={"file": ("report.pdf", PDF_BYTES_V2, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 200
    body = response.json()
    assert body["size_bytes"] == len(PDF_BYTES_V2)

    download = await client.get(f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert download.content == PDF_BYTES_V2

    async with SessionLocal() as session:
        new_s3_key = (await session.get(Document, doc_id)).s3_key
    assert new_s3_key != old_s3_key
    with pytest.raises(ClientError):
        _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=old_s3_key)


async def test_replace_document_content_rejects_exe_renamed_to_pdf(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]

    response = await client.put(
        f"/document/{doc_id}",
        files={"file": ("report.pdf", EXE_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 415
    download = await client.get(f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert download.content == PDF_BYTES


async def test_replace_document_content_requires_membership(client: AsyncClient):
    owner_token = await _register_and_login(client)
    project_id = await _create_project(client, owner_token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {owner_token}"},)
    doc_id = upload_response.json()[0]["id"]
    outsider_token = await _register_and_login(client)

    response = await client.put(
        f"/document/{doc_id}",
        files={"file": ("report.pdf", PDF_BYTES_V2, "application/pdf")},
        headers={"Authorization": f"Bearer {outsider_token}"},)

    assert response.status_code == 404


async def test_delete_document_removes_db_row_and_s3_object(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]
    async with SessionLocal() as session:
        s3_key = (await session.get(Document, doc_id)).s3_key

    response = await client.delete(
        f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    async with SessionLocal() as session:
        assert await session.get(Document, doc_id) is None
    with pytest.raises(ClientError):
        _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=s3_key)


async def test_delete_document_row_removed_even_if_s3_delete_fails(
    client: AsyncClient, monkeypatch):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]

    async def _failing_delete(s3_key: str) -> None:
        raise RuntimeError("simulated S3 outage")

    monkeypatch.setattr("app.services.documents.storage.delete", _failing_delete)

    with pytest.raises(RuntimeError):
        await client.delete(f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    async with SessionLocal() as session:
        assert await session.get(Document, doc_id) is None


async def test_upload_updates_project_total_size_bytes(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    await client.post(
        f"/project/{project_id}/documents",
        files=[
            ("files", ("a.pdf", PDF_BYTES, "application/pdf")),
            ("files", ("b.pdf", PDF_BYTES, "application/pdf")),
        ],
        headers={"Authorization": f"Bearer {token}"},
    )

    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
    assert project.total_size_bytes == 2 * len(PDF_BYTES)


async def test_upload_rejects_when_exceeding_project_size_limit(
    client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_project_bytes", len(PDF_BYTES) - 1)
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 413
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        documents = await session.execute(
            select(Document).where(Document.project_id == project_id))
    assert project.total_size_bytes == 0
    assert documents.scalars().all() == []


async def test_delete_document_decrements_project_total_size_bytes(client: AsyncClient):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]

    await client.delete(f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
    assert project.total_size_bytes == 0


async def test_replace_document_rejects_when_growth_exceeds_limit(
    client: AsyncClient, monkeypatch):
    token = await _register_and_login(client)
    project_id = await _create_project(client, token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)
    doc_id = upload_response.json()[0]["id"]
    monkeypatch.setattr(get_settings(), "max_project_bytes", len(PDF_BYTES))

    response = await client.put(
        f"/document/{doc_id}",
        files={"file": ("report.pdf", PDF_BYTES_V2, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},)

    assert response.status_code == 413
    download = await client.get(f"/document/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert download.content == PDF_BYTES
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
    assert project.total_size_bytes == len(PDF_BYTES)


async def test_delete_document_requires_membership(client: AsyncClient):
    owner_token = await _register_and_login(client)
    project_id = await _create_project(client, owner_token)
    upload_response = await client.post(
        f"/project/{project_id}/documents",
        files={"files": ("report.pdf", PDF_BYTES, "application/pdf")},
        headers={"Authorization": f"Bearer {owner_token}"},)
    doc_id = upload_response.json()[0]["id"]
    outsider_token = await _register_and_login(client)

    response = await client.delete(
        f"/document/{doc_id}", headers={"Authorization": f"Bearer {outsider_token}"})

    assert response.status_code == 404
