# app/db.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from app.config import settings
from app.db_base import Base  # <-- берем Base из db_base, НЕ из models

_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

connect_args = {}
if _IS_SQLITE:
    connect_args = {"timeout": 30}  # сек, для aiosqlite

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
    future=True,
)

if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_on_connect(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)

# app/db.py (оставь как у тебя, только проверь init_db)
async def init_db():
    import app.models  # регистрируем модели
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

