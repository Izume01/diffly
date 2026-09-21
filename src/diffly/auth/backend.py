from uuid import UUID

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from httpx_oauth.clients.github import GitHubOAuth2

from diffly.auth.config import auth_settings
from diffly.auth.manager import get_user_manager
from diffly.database.models import User

# Bearer Token transport for REST API and SPAs
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=auth_settings.auth_secret,
        lifetime_seconds=auth_settings.jwt_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)

github_oauth_client = GitHubOAuth2(
    client_id=auth_settings.github_client_id,
    client_secret=auth_settings.github_client_secret,
)
