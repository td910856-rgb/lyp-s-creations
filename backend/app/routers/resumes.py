"""简历上传相关接口。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR, settings
from ..database import get_db
from ..models import Resume
from ..schemas import ResumeOut
from ..services import limits
from ..services.file_parser import SUPPORTED_EXTENSIONS, ParseError, extract_text

router = APIRouter(prefix="/api/resumes", tags=["简历"])

PREVIEW_CHARS = 150


def resume_payload(resume: Resume) -> dict:
    """把数据库对象转成前端需要的结构（不回传全文，减少流量）。"""
    preview = resume.raw_text[:PREVIEW_CHARS].replace("\n", " ")
    if len(resume.raw_text) > PREVIEW_CHARS:
        preview += "……"

    return {
        "id": resume.id,
        "filename": resume.filename,
        "file_type": resume.file_type,
        "char_count": resume.char_count,
        "preview": preview,
        "created_at": resume.created_at,
    }


@router.post("/upload", response_model=ResumeOut, summary="上传简历并提取文字")
async def upload_resume(
    request: Request,
    file: UploadFile = File(..., description="PDF / DOCX / TXT 简历"),
    x_client_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    # 上传也要限流：不然有人会拿它当免费文件存储
    # 上传只受每分钟限制，不消耗"每日分析次数"
    allowed, message = limits.check(limits.client_ip(request), count_quota=False)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)

    # 只取文件名，防止有人用 ../ 之类的路径做坏事
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="没有拿到文件名，请重新选择文件。")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式 {suffix or '（无扩展名）'}，请上传 PDF 或 DOCX 文件。",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的，请换一份简历再上传。")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件太大了（超过 {settings.max_upload_mb} MB），请压缩后再上传。",
        )

    # 用随机文件名存盘，避免同名文件互相覆盖
    stored_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(content)

    try:
        text = extract_text(stored_path)
    except ParseError as exc:
        stored_path.unlink(missing_ok=True)  # 解析失败就不留垃圾文件
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resume = Resume(
        client_id=(x_client_id or "")[:64],
        filename=filename,
        file_type=suffix.lstrip("."),
        stored_path=str(stored_path),
        raw_text=text,
        char_count=len(text),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return resume_payload(resume)


@router.get("", response_model=list[ResumeOut], summary="已上传的简历列表")
def list_resumes(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """按上传时间倒序列出简历，前端用它做简历切换。"""
    rows = db.execute(select(Resume).order_by(Resume.id.desc()).limit(limit)).scalars().all()
    return [resume_payload(resume) for resume in rows]


@router.get("/{resume_id}", response_model=ResumeOut, summary="查看某份简历的提取结果")
def get_resume(resume_id: int, db: Session = Depends(get_db)) -> dict:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="没有找到这份简历，可能数据库被清空了。")
    return resume_payload(resume)
