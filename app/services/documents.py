import uuid
from collections.abc import Sequence

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.services import storage

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_SIGNATURES: dict[bytes, str] = {
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": DOCX_CONTENT_TYPE,
}


def _detect_content_type(body: bytes) -> str:
    for signature, content_type in _SIGNATURES.items():
        if body.startswith(signature):
            return content_type
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="only PDF and DOCX files are supported",)


async def upload_documents(
    session: AsyncSession, project_id: int, files: list[UploadFile]) -> list[Document]:
    bodies = [await file.read() for file in files]
    content_types = [_detect_content_type(body) for body in bodies]

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
    await session.delete(document)
    await session.commit()


async def list_documents_for_project(session: AsyncSession, project_id: int) -> Sequence[Document]:
    result = await session.execute(
        select(Document).where(Document.project_id == project_id).order_by(Document.id))
    return result.scalars().all()
