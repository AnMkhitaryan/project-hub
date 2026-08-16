from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_internal_secret
from app.schemas.project import ProjectSizePublic
from app.services.projects import recalculate_project_size

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post(
    "/projects/{project_id}/recalculate-size",
    response_model=ProjectSizePublic,
    dependencies=[Depends(require_internal_secret)],)
async def recalculate_size(
    project_id: int,
    session: AsyncSession = Depends(get_session),) -> ProjectSizePublic:
    total = await recalculate_project_size(session, project_id)
    return ProjectSizePublic(project_id=project_id, total_size_bytes=total)
