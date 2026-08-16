from pydantic import BaseModel, ConfigDict

from app.models import ProjectRole


class MembershipPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    user_id: int
    role: ProjectRole


class InviteLink(BaseModel):
    token: str
    join_url: str
