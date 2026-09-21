from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlmodel.ext.asyncio.session import AsyncSession

from diffly.auth.config import auth_settings
from diffly.database.db import get_session
from diffly.database.models import OAuthAccount, User


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID]]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = auth_settings.auth_secret
    verification_token_secret = auth_settings.auth_secret

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        print(f"User {user.id} successfully registered with email {user.email}")

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        user = await super().oauth_callback(
            oauth_name=oauth_name,
            access_token=access_token,
            account_id=account_id,
            account_email=account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
            request=request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )

        # Enrich user profile with GitHub metadata (handle, avatar)
        if oauth_name == "github" and (
            user.github_username is None or user.avatar_url is None
        ):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/user",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": "Diffly-Auth",
                        },
                        timeout=5.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        user.github_username = data.get("login")
                        user.avatar_url = data.get("avatar_url")
                        await self.user_db.update(
                            user,
                            {
                                "github_username": user.github_username,
                                "avatar_url": user.avatar_url,
                            },
                        )
            except (httpx.HTTPError, KeyError) as exc:
                print(f"Failed to fetch GitHub profile for user {user.id}: {exc}")

        return user


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager]:
    yield UserManager(user_db)
