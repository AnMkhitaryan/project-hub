import uuid
from collections.abc import Sequence

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document, Project
from app.services import storage

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_SIGNATURES: dict[bytes, str] = {
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": DOCX_CONTENT_TYPE,
}

PROJECT_SIZE_LIMIT_ERROR = HTTPException(
    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
    detail="this would exceed the project's storage limit",)


def _detect_content_type(body: bytes) -> str:
    for signature, content_type in _SIGNATURES.items():
        if body.startswith(signature):
            return content_type
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="only PDF and DOCX files are supported",)


async def _try_adjust_project_size(session: AsyncSession, project_id: int, delta: int) -> bool:
    if delta == 0:
        return True

    stmt = update(Project).where(Project.id == project_id)
    if delta > 0:
        max_bytes = get_settings().max_project_bytes
        stmt = stmt.where(Project.total_size_bytes + delta <= max_bytes)
    stmt = stmt.values(total_size_bytes=Project.total_size_bytes + delta).returning(Project.id)

    result = await session.execute(stmt)
    return result.first() is not None


async def upload_documents(
    session: AsyncSession, project_id: int, files: list[UploadFile]) -> list[Document]:
    bodies = [await file.read() for file in files]
    content_types = [_detect_content_type(body) for body in bodies]
    total_new_bytes = sum(len(body) for body in bodies)

    if not await _try_adjust_project_size(session, project_id, total_new_bytes):
        raise PROJECT_SIZE_LIMIT_ERROR

    documents = []
    for file, body, content_type in zip(files, bodies, content_types, strict=True):
        s3_key = f"projects/{project_id}/{uuid.uuid4().hex}"
        await storage.upload(s3_key, body, content_type=content_type)
        document = Document(
            project_id=project_id,
            filename=file.filename or "unnamed",
            content_type=content_type,
            size_bytes=len(body),
            s3_key=s3_key,)
        session.add(document)
        documents.append(document)

    await session.commit()
    for document in documents:
        await session.refresh(document)
    return documents


async def replace_document_content(
    session: AsyncSession, document: Document, file: UploadFile) -> Document:
    body = await file.read()
    content_type = _detect_content_type(body)

    delta = len(body) - document.size_bytes
    if not await _try_adjust_project_size(session, document.project_id, delta):
        raise PROJECT_SIZE_LIMIT_ERROR

    new_s3_key = f"projects/{document.project_id}/{uuid.uuid4().hex}"
    await storage.upload(new_s3_key, body, content_type=content_type)

    old_s3_key = document.s3_key
    document.s3_key = new_s3_key
    document.content_type = content_type
    document.size_bytes = len(body)
    await session.commit()
    await session.refresh(document)

    await storage.delete(old_s3_key)
    return document


async def delete_document(session: AsyncSession, document: Document) -> None:
    await storage.delete(document.s3_key)
    await _try_adjust_project_size(session, document.project_id, -document.size_bytes)
    await session.delete(document)
    await session.commit()


async def list_documents_for_project(session: AsyncSession, project_id: int) -> Sequence[Document]:
    result = await session.execute(
        select(Document).where(Document.project_id == project_id).order_by(Document.id))
    return result.scalars().all()
