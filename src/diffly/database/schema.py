from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict

from diffly.agents.schema import Severity


# ---------------------------------------------------------------------------
# User Schemas (FastAPI-Users)
# ---------------------------------------------------------------------------
class UserRead(schemas.BaseUser[UUID]):
    created_at: datetime
    github_username: str | None = None
    avatar_url: str | None = None


class UserCreate(schemas.BaseUserCreate):
    github_username: str | None = None
    avatar_url: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    github_username: str | None = None
    avatar_url: str | None = None


# ---------------------------------------------------------------------------
# Repository Schemas
# ---------------------------------------------------------------------------
class RepositoryBase(BaseModel):
    github_repo_id: int
    name: str
    full_name: str
    user_id: UUID | None = None


class RepositoryCreate(RepositoryBase):
    pass


class RepositoryRead(RepositoryBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Review Finding Schemas
# ---------------------------------------------------------------------------
class ReviewFindingBase(BaseModel):
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    severity: Severity
    category: str
    title: str
    description: str
    suggestion: str | None = None


class ReviewFindingCreate(ReviewFindingBase):
    review_id: UUID


class ReviewFindingRead(ReviewFindingBase):
    id: UUID
    review_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# AI Call Telemetry Schemas
# ---------------------------------------------------------------------------
class AICallBase(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int | None = None
    cost: Decimal | None = None


class AICallCreate(AICallBase):
    review_id: UUID


class AICallRead(AICallBase):
    id: UUID
    review_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Review Schemas
# ---------------------------------------------------------------------------
class ReviewBase(BaseModel):
    pr_number: int
    commit_sha: str
    status: str = "completed"
    summary: str | None = None


class ReviewCreate(ReviewBase):
    repository_id: UUID


class ReviewRead(ReviewBase):
    id: UUID
    repository_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewDetail(ReviewRead):
    findings: list[ReviewFindingRead] = []
    ai_calls: list[AICallRead] = []
