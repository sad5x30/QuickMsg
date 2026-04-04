import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)

async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def init_models() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as db:
        yield db
