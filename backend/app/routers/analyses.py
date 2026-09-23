"""简历分析相关接口。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..models import Analysis, Resume
from ..schemas import AnalysisOut, AnalysisRequest, AnalysisSummary
from ..services import exporter
from ..services import limits
from ..services.analyzer import run_analysis
from ..services.llm_client import LLMError

router = APIRouter(prefix="/api/analyses", tags=["分析"])


def analysis_payload(analysis: Analysis, filename: str = "") -> dict:
    """把数据库对象转成前端需要的结构。"""
    return {
        "id": analysis.id,
        "resume_id": analysis.resume_id,
        "resume_filename": filename,
        "job_title": analysis.job_title,
        "overall_score": analysis.overall_score,
        "skill_score": analysis.skill_score,
        "project_score": analysis.project_score,
        "details": analysis.details or {},
        "model_used": analysis.model_used,
        "is_mock": analysis.is_mock,
        "created_at": analysis.created_at,
    }


@router.post("", response_model=AnalysisOut, summary="分析简历与目标岗位的匹配度")
def create_analysis(
    payload: AnalysisRequest,
    request: Request,
    x_llm_key: str | None = Header(default=None),
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    # 访客自带密钥（BYOK）：只在这次请求里用，不落库、不写日志
    override = {
        "api_key": x_llm_key or "",
        "base_url": x_llm_base_url or "",
        "model": x_llm_model or "",
    }
    use_own_key = bool(override["api_key"])

    if settings.require_own_key and not use_own_key:
        raise HTTPException(
            status_code=400,
            detail="本站不提供模型密钥，请在左侧的「模型设置」里填上你自己的 API Key。",
        )

    allowed, message = limits.check(limits.client_ip(request), use_own_key=use_own_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)

    resume = db.get(Resume, payload.resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在，请重新上传。")

    try:
        analysis = run_analysis(
            db,
            resume,
            payload.job_title,
            use_web=payload.use_web,
            job_description=payload.job_description,
            override=override if use_own_key else None,
            client_id=(x_client_id or "")[:64],
        )
    except LLMError as exc:
        # 模型相关的问题统一用 502，前端会直接把 detail 显示给用户
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return analysis_payload(analysis, resume.filename)


@router.get("", response_model=list[AnalysisSummary], summary="最近的分析记录")
def list_analyses(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(
        select(Analysis, Resume.filename)
        .join(Resume, Resume.id == Analysis.resume_id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
    ).all()

    return [
        {
            "id": analysis.id,
            "job_title": analysis.job_title,
            "resume_filename": filename,
            "overall_score": analysis.overall_score,
            "is_mock": analysis.is_mock,
            "created_at": analysis.created_at,
        }
        for analysis, filename in rows
    ]


@router.get("/{analysis_id}", response_model=AnalysisOut, summary="查看历史分析结果")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        select(Analysis, Resume.filename)
        .join(Resume, Resume.id == Analysis.resume_id)
        .where(Analysis.id == analysis_id)
    ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这条分析记录。")

    analysis, filename = row
    return analysis_payload(analysis, filename)


@router.delete("/{analysis_id}", summary="删除一条分析记录")
def delete_analysis(analysis_id: int, db: Session = Depends(get_db)) -> dict:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="没有找到这条分析记录。")

    db.delete(analysis)
    db.commit()
    return {"deleted": analysis_id}


@router.get("/{analysis_id}/export.docx", summary="把优化后的简历导出成 Word")
def export_analysis_docx(analysis_id: int, db: Session = Depends(get_db)) -> Response:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="没有找到这条分析记录。")

    markdown = (analysis.details or {}).get("optimized_resume", "")
    if not markdown.strip():
        raise HTTPException(status_code=400, detail="这次分析没有生成简历文本，无法导出。")

    content = exporter.markdown_to_docx(markdown)
    filename = f"{analysis.job_title}-优化后简历.docx"

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        # 中文文件名要用 filename* 的写法，浏览器才不会乱码
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
