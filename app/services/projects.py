from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, Project, ProjectMember, ProjectRole, User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import storage


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
    assert project is not None
    return project


async def update_project(session: AsyncSession, project: Project, data: ProjectUpdate) -> Project:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project
