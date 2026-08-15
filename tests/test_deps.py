import uuid

import pytest
from fastapi import HTTPException

from app.db import SessionLocal
from app.deps import require_member, require_owner
from app.models import Project, ProjectMember, ProjectRole, User
from app.services.security import hash_password


async def _create_user(session) -> User:
    login = f"user_{uuid.uuid4().hex[:12]}"
    user = User(login=login, email=f"{login}@example.com", password_hash=hash_password("x" * 8))
    session.add(user)
    await session.flush()
    return user


async def _create_project(session) -> Project:
    project = Project(name="Test project")
    session.add(project)
    await session.flush()
    return project


async def _add_member(session, project: Project, user: User, role: ProjectRole) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
    await session.flush()


async def test_require_member_returns_membership_for_member():
    async with SessionLocal() as session:
        owner = await _create_user(session)
        project = await _create_project(session)
        await _add_member(session, project, owner, ProjectRole.OWNER)

        membership = await require_member(project.id, current_user=owner, session=session)

        assert membership.project_id == project.id
        assert membership.user_id == owner.id
        assert membership.role == ProjectRole.OWNER


async def test_require_member_raises_404_for_non_member():
    async with SessionLocal() as session:
        outsider = await _create_user(session)
        project = await _create_project(session)

        with pytest.raises(HTTPException) as exc_info:
            await require_member(project.id, current_user=outsider, session=session)

        assert exc_info.value.status_code == 404


async def test_require_owner_returns_membership_for_owner():
    async with SessionLocal() as session:
        owner = await _create_user(session)
        project = await _create_project(session)
        await _add_member(session, project, owner, ProjectRole.OWNER)

        membership = await require_member(project.id, current_user=owner, session=session)
        result = await require_owner(membership=membership)

        assert result is membership


async def test_require_owner_raises_403_for_participant():
    async with SessionLocal() as session:
        participant = await _create_user(session)
        project = await _create_project(session)
        await _add_member(session, project, participant, ProjectRole.PARTICIPANT)

        membership = await require_member(project.id, current_user=participant, session=session)

        with pytest.raises(HTTPException) as exc_info:
            await require_owner(membership=membership)

        assert exc_info.value.status_code == 403


async def test_require_owner_raises_404_for_non_member():
    async with SessionLocal() as session:
        outsider = await _create_user(session)
        project = await _create_project(session)

        with pytest.raises(HTTPException) as exc_info:
            membership = await require_member(project.id, current_user=outsider, session=session)
            await require_owner(membership=membership)

        assert exc_info.value.status_code == 404
