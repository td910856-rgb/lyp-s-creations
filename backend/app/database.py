"""SQLite 连接与会话管理。

用 SQLAlchemy 的最小用法：一个 engine、一个会话工厂、一个 Base。
数据库就是一个文件 backend/resume.db，不需要额外安装数据库服务。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# check_same_thread=False：FastAPI 的请求可能跑在不同线程上，SQLite 需要这个开关
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有数据表模型的基类。"""


def init_db() -> None:
    """建表。已存在则跳过，可以反复调用。"""
    from . import models  # noqa: F401  必须导入，模型才会注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """SQLite 的 create_all 不会给已有的表加字段，这里补一次。

    只做「加字段」这种最安全的操作，不动已有数据。
    """
    wanted = {
        "resumes": {"client_id": "VARCHAR(64) DEFAULT ''"},
        "analyses": {"client_id": "VARCHAR(64) DEFAULT ''"},
    }
    with engine.connect() as conn:
        for table, columns in wanted.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.commit()


def cleanup_old_data() -> int:
    """删掉超过保留期的简历（连同它的分析记录和上传文件），返回删除条数。"""
    from .config import settings
    from .models import Resume

    if settings.data_retention_hours <= 0:
        return 0

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=settings.data_retention_hours
    )
    session = SessionLocal()
    try:
        old = session.execute(select(Resume).where(Resume.created_at < cutoff)).scalars().all()
        for resume in old:
            if resume.stored_path:
                try:
                    Path(resume.stored_path).unlink(missing_ok=True)
                except OSError:
                    pass  # 文件被占用也无所谓，记录删掉就行
            session.delete(resume)
        if old:
            session.commit()
        return len(old)
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个数据库会话，用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
