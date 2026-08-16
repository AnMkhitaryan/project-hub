from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Document, ProjectMember, ProjectRole, User
from app.services.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),) -> User:
    if credentials is None:
        raise INVALID_TOKEN_ERROR
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise INVALID_TOKEN_ERROR from exc

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise INVALID_TOKEN_ERROR
    return user


PROJECT_NOT_FOUND_ERROR = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="project not found",)

NOT_PROJECT_OWNER_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="only the project owner can do this",)


async def _find_membership(
    session: AsyncSession, project_id: int, user_id: int) -> ProjectMember | None:
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_member(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),) -> ProjectMember:
    membership = await _find_membership(session, project_id, current_user.id)
    if membership is None:
        raise PROJECT_NOT_FOUND_ERROR
    return membership


async def require_owner(
    membership: ProjectMember = Depends(require_member),) -> ProjectMember:
    if membership.role != ProjectRole.OWNER:
        raise NOT_PROJECT_OWNER_ERROR
    return membership


DOCUMENT_NOT_FOUND_ERROR = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="document not found",)


async def require_document_access(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise DOCUMENT_NOT_FOUND_ERROR
    membership = await _find_membership(session, document.project_id, current_user.id)
    if membership is None:
        raise DOCUMENT_NOT_FOUND_ERROR
    return document
