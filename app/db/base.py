from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine(url: str):
    return create_async_engine(url, echo=False)


def create_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)