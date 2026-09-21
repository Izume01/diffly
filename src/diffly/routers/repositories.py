from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from diffly.auth import current_active_user
from diffly.database.db import get_session
from diffly.database.models import Repository, Review, User
from diffly.database.schema import RepositoryRead, ReviewRead

router = APIRouter(tags=["repositories"])


@router.get("/repositories/me", response_model=list[RepositoryRead])
async def list_my_repositories(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """List all repositories linked to the authenticated user."""
    stmt = select(Repository).where(Repository.user_id == user.id)
    result = await session.exec(stmt)
    return result.all()


@router.post("/repositories/{repo_id}/claim", response_model=RepositoryRead)
async def claim_repository(
    repo_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Link an installed repository to the authenticated user account."""
    repo = await session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if repo.user_id and repo.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Repository is already claimed by another user",
        )

    repo.user_id = user.id
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    return repo


@router.get("/reviews/me", response_model=list[ReviewRead])
async def list_my_reviews(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """List recent code reviews across all repositories owned by the authenticated user."""
    stmt = (
        select(Review)
        .join(Repository)
        .where(Repository.user_id == user.id)
        .order_by(col(Review.created_at).desc())
    )

    result = await session.exec(stmt)
    return result.all()
