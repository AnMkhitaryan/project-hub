from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user, require_member, require_owner
from app.models import Project, ProjectMember, User
from app.schemas.project import ProjectCreate, ProjectPublic, ProjectUpdate, ProjectWithDocuments
from app.services.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects_for_user,
    update_project,)

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectPublic, status_code=status.HTTP_201_CREATED)
async def create(
        payload: ProjectCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session), ) -> ProjectPublic:
    return await create_project(session, payload, current_user)


@router.get("/projects", response_model=list[ProjectWithDocuments])
async def list_projects(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session), ) -> list[Project]:
    return list(await list_projects_for_user(session, current_user.id))


@router.get("/project/{project_id}/info", response_model=ProjectPublic)
async def get_info(
        project_id: int,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_member),) -> ProjectPublic:
    return await get_project(session, project_id)


@router.put("/project/{project_id}/info", response_model=ProjectPublic)
async def update_info(
        project_id: int,
        payload: ProjectUpdate,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_member),) -> ProjectPublic:
    project = await get_project(session, project_id)
    return await update_project(session, project, payload)


@router.delete("/project/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
        project_id: int,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_owner),) -> None:
    project = await get_project(session, project_id)
    await delete_project(session, project)
