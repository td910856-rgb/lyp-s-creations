"""数据表定义：只有两张表，够用就好。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Resume(Base):
    """一份上传的简历。"""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 浏览器生成的一串随机 ID，用来让访客管理"自己上传的东西"
    client_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    stored_path: Mapped[str] = mapped_column(String(500), default="")
    raw_text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )


class Analysis(Base):
    """一次分析结果。

    三个分数单独成列，方便以后排序 / 对比；
    其余零散内容全部塞进 details 这个 JSON 字段，避免为了一点小改动反复改表结构。
    """

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)
    job_title: Mapped[str] = mapped_column(String(200))
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    skill_score: Mapped[int] = mapped_column(Integer, default=0)
    project_score: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_used: Mapped[str] = mapped_column(String(100), default="")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    resume: Mapped[Resume] = relationship(back_populates="analyses")
