from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, Project, ProjectMember, ProjectRole, User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import storage
from app.services.security import InvalidInviteTokenError, decode_invite_token

USER_NOT_FOUND_ERROR = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="user not found",
)

ALREADY_MEMBER_ERROR = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="user is already a member of this project",
)

INVALID_INVITE_ERROR = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="invalid or expired invite link",
)

WRONG_RECIPIENT_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="this invite is for a different email address",
)


async def create_project(session: AsyncSession, data: ProjectCreate, owner: User) -> Project:
    project = Project(name=data.name, description=data.description)
    session.add(project)
    await session.flush()

    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER))
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    result = await session.execute(
        select(Document.s3_key).where(Document.project_id == project.id))
    s3_keys = list(result.scalars().all())

    await storage.delete_many(s3_keys)

    await session.delete(project)
    await session.commit()


async def list_projects_for_user(session: AsyncSession, user_id: int) -> Sequence[Project]:
    result = await session.execute(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
        .options(selectinload(Project.documents))
        .order_by(Project.id))
    return result.scalars().all()


async def get_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise RuntimeError(f"project {project_id} vanished after membership check")
    return project


async def update_project(session: AsyncSession, project: Project, data: ProjectUpdate) -> Project:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


async def _create_participant_membership(
    session: AsyncSession, project_id: int, user_id: int
) -> ProjectMember:
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ALREADY_MEMBER_ERROR

    membership = ProjectMember(project_id=project_id, user_id=user_id, role=ProjectRole.PARTICIPANT)
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


async def invite_member(session: AsyncSession, project_id: int, login: str) -> ProjectMember:
    result = await session.execute(select(User).where(User.login == login))
    user = result.scalar_one_or_none()
    if user is None:
        raise USER_NOT_FOUND_ERROR
    return await _create_participant_membership(session, project_id, user.id)


async def redeem_invite(session: AsyncSession, token: str, current_user: User) -> ProjectMember:
    try:
        payload = decode_invite_token(token)
    except InvalidInviteTokenError as exc:
        raise INVALID_INVITE_ERROR from exc

    if payload["email"].lower() != current_user.email.lower():
        raise WRONG_RECIPIENT_ERROR

    return await _create_participant_membership(session, payload["project_id"], current_user.id)


async def recalculate_project_size(session: AsyncSession, project_id: int) -> int:
    project = await session.get(Project, project_id)
    if project is None:
        return 0

    total = await storage.sum_object_sizes(f"projects/{project_id}/")
    project.total_size_bytes = total
    await session.commit()
    return total
