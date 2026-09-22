"""访客管理自己的数据。

没有账号系统，所以用一个浏览器生成的随机 client_id 来区分。
页面上可以查看"我传过什么"，并一键删除。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Analysis, Resume

router = APIRouter(prefix="/api/my-data", tags=["我的数据"])


@router.get("", summary="看看这个浏览器上传过什么")
def my_data(x_client_id: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    client_id = (x_client_id or "")[:64]
    if not client_id:
        return {"resumes": [], "analyses": []}

    resumes = db.execute(
        select(Resume).where(Resume.client_id == client_id).order_by(Resume.id.desc())
    ).scalars().all()
    analyses = db.execute(
        select(Analysis)
        .where(Analysis.client_id == client_id)
        .order_by(Analysis.id.desc())
        .limit(50)
    ).scalars().all()

    return {
        "resumes": [
            {"id": item.id, "filename": item.filename, "created_at": item.created_at}
            for item in resumes
        ],
        "analyses": [
            {
                "id": item.id,
                "job_title": item.job_title,
                "overall_score": item.overall_score,
                "created_at": item.created_at,
            }
            for item in analyses
        ],
    }


@router.delete("", summary="删除这个浏览器产生的全部数据")
def delete_my_data(
    x_client_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    client_id = (x_client_id or "")[:64]
    if not client_id:
        raise HTTPException(status_code=400, detail="没有识别到你的身份，无法删除。")

    resumes = db.execute(select(Resume).where(Resume.client_id == client_id)).scalars().all()
    removed_files = 0
    for resume in resumes:
        if resume.stored_path:
            try:
                Path(resume.stored_path).unlink(missing_ok=True)
                removed_files += 1
            except OSError:
                pass
        db.delete(resume)  # 关联的分析记录会一起删掉

    db.execute(delete(Analysis).where(Analysis.client_id == client_id))
    db.commit()

    return {"deleted_resumes": len(resumes), "deleted_files": removed_files}
