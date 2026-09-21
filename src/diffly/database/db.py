from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from .config import settings

# Convert postgresql:// to postgresql+asyncpg:// for asyncpg driver
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    ASYNC_DATABASE_URL = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgres://"):
    ASYNC_DATABASE_URL = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = db_url

# Strip query parameters not supported directly by asyncpg
ASYNC_DATABASE_URL = ASYNC_DATABASE_URL.split("?")[0]

# Neon PgBouncer connection configuration
# statement_cache_size=0 is required to prevent prepared statement collisions
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args={
        "ssl": "require",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
    pool_size=5,
    max_overflow=5,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=False,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)



async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI and Arq dependency for providing an async database session."""
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """Create tables on Neon Postgres if they do not already exist (cold-start fallback)."""
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


