from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi_users.db import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from fastapi_users.models import UserOAuthProtocol
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlmodel import Field, Relationship, SQLModel

from diffly.agents.schema import Severity


class Base(DeclarativeBase):
    registry = SQLModel._sa_registry



class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    pass


if TYPE_CHECKING:
    class User(SQLAlchemyBaseUserTableUUID, Base, UserOAuthProtocol[UUID, OAuthAccount]):
        created_at: datetime
        github_username: str | None
        avatar_url: str | None
        oauth_accounts: list[OAuthAccount]
        repositories: list["Repository"]
else:
    class User(SQLAlchemyBaseUserTableUUID, Base):
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
        )
        github_username: Mapped[str | None] = mapped_column(nullable=True, index=True)
        avatar_url: Mapped[str | None] = mapped_column(nullable=True)

        oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
            "OAuthAccount",
            lazy="joined",
            cascade="all, delete-orphan",
        )
        repositories: Mapped[list["Repository"]] = relationship(
            "Repository",
            back_populates="user",
        )




class Repository(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    github_repo_id: int = Field(unique=True, index=True)
    name: str
    full_name: str
    user_id: UUID | None = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    user: User | None = Relationship(back_populates="repositories")
    reviews: list["Review"] = Relationship(back_populates="repository")


class Review(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    repository_id: UUID = Field(foreign_key="repository.id", index=True)
    pr_number: int
    commit_sha: str
    status: str = Field(default="completed")
    summary: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    repository: Repository | None = Relationship(back_populates="reviews")
    findings: list["ReviewFinding"] = Relationship(
        back_populates="review",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    ai_calls: list["AICall"] = Relationship(
        back_populates="review",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ReviewFinding(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    review_id: UUID = Field(foreign_key="review.id", index=True)

    file_path: str
    line_start: int | None = None
    line_end: int | None = None

    severity: Severity
    category: str
    title: str
    description: str
    suggestion: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    review: Review | None = Relationship(back_populates="findings")


class AICall(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    review_id: UUID = Field(foreign_key="review.id", index=True)

    provider: str
    model: str

    input_tokens: int
    output_tokens: int
    total_tokens: int

    latency_ms: int | None = None
    cost: Decimal | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    review: Review | None = Relationship(back_populates="ai_calls")
