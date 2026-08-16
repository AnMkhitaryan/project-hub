from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import DocumentPublic


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectWithDocuments(ProjectPublic):
    documents: list[DocumentPublic]


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectSizePublic(BaseModel):
    project_id: int
    total_size_bytes: int
