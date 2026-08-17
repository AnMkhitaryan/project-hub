from fastapi import APIRouter, Depends, Query, status
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user, require_member, require_owner
from app.models import Project, ProjectMember, User
from app.schemas.membership import InviteLink, MembershipPublic
from app.schemas.project import ProjectCreate, ProjectPublic, ProjectUpdate, ProjectWithDocuments
from app.services.projects import (
    create_project,
    delete_project,
    get_project,
    invite_member,
    list_projects_for_user,
    redeem_invite,
    update_project,)
from app.services.security import create_invite_token

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectPublic, status_code=status.HTTP_201_CREATED)
async def create(
        payload: ProjectCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session), ) -> Project:
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
        membership: ProjectMember = Depends(require_member),) -> Project:
    return await get_project(session, project_id)


@router.put("/project/{project_id}/info", response_model=ProjectPublic)
async def update_info(
        project_id: int,
        payload: ProjectUpdate,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_member),) -> Project:
    project = await get_project(session, project_id)
    return await update_project(session, project, payload)


@router.delete("/project/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
        project_id: int,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_owner),) -> None:
    project = await get_project(session, project_id)
    await delete_project(session, project)


@router.post(
    "/project/{project_id}/invite",
    response_model=MembershipPublic,
    status_code=status.HTTP_201_CREATED,)
async def invite(
        project_id: int,
        user: str,
        session: AsyncSession = Depends(get_session),
        membership: ProjectMember = Depends(require_owner),) -> ProjectMember:
    return await invite_member(session, project_id, user)


@router.get("/project/{project_id}/share", response_model=InviteLink)
async def share(
        project_id: int,
        with_email: EmailStr = Query(alias="with"),
        membership: ProjectMember = Depends(require_owner),) -> InviteLink:
    token = create_invite_token(project_id, with_email)
    return InviteLink(token=token, join_url=f"/join?token={token}")


@router.get("/join", response_model=MembershipPublic, status_code=status.HTTP_201_CREATED)
async def join(
        token: str,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),) -> ProjectMember:
    return await redeem_invite(session, token, current_user)
