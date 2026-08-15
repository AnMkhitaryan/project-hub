from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ProjectMember, ProjectRole, User
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


async def require_member(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),) -> ProjectMember:
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise PROJECT_NOT_FOUND_ERROR
    return membership


async def require_owner(
    membership: ProjectMember = Depends(require_member),) -> ProjectMember:
    if membership.role != ProjectRole.OWNER:
        raise NOT_PROJECT_OWNER_ERROR
    return membership
