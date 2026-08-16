from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_document_access, require_member
from app.models import Document, ProjectMember
from app.schemas.document import DocumentPublic
from app.services import storage
from app.services.documents import (
    delete_document,
    list_documents_for_project,
    replace_document_content,
    upload_documents,
)

router = APIRouter(tags=["documents"])


def _content_disposition(filename: str) -> str:
    safe = filename.replace("\r", "").replace("\n", "").replace('"', "'")
    return f'attachment; filename="{safe}"'


@router.post(
    "/project/{project_id}/documents",
    response_model=list[DocumentPublic],
    status_code=status.HTTP_201_CREATED,)
async def upload(
    project_id: int,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    membership: ProjectMember = Depends(require_member),) -> list[Document]:
    return await upload_documents(session, project_id, files)


@router.get("/project/{project_id}/documents", response_model=list[DocumentPublic])
async def list_documents(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    membership: ProjectMember = Depends(require_member),) -> list[Document]:
    return list(await list_documents_for_project(session, project_id))


@router.get("/document/{document_id}")
async def download(
    document_id: int,
    document: Document = Depends(require_document_access),) -> StreamingResponse:
    return StreamingResponse(
        storage.download_stream(document.s3_key),
        media_type=document.content_type,
        headers={"Content-Disposition": _content_disposition(document.filename)},)


@router.put("/document/{document_id}", response_model=DocumentPublic)
async def replace(
    document_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    document: Document = Depends(require_document_access),) -> Document:
    return await replace_document_content(session, document, file)


@router.delete("/document/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    document: Document = Depends(require_document_access),) -> None:
    await delete_document(session, document)
