"""把文件解析、模型调用、数据落库串起来。

模型返回的内容不可全信，这里做一次「归一化」：
分数夹到 0-100、字段补默认值、类型不对的做兼容处理，
保证前端永远拿到结构稳定的数据，不会因为模型抽风而白屏。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Analysis, Resume
from . import llm_client, web_collector


def run_analysis(
    db: Session,
    resume: Resume,
    job_title: str,
    use_web: bool = True,
    job_description: str = "",
    override: dict[str, str] | None = None,
    client_id: str = "",
) -> Analysis:
    """执行一次完整分析并写入数据库。

    岗位信息的优先级：用户粘贴的 JD > 联网采集 > 只有岗位名称。
    """
    jd_text = (job_description or "").strip()

    if jd_text:
        # 用户自己粘了 JD，这就是最准的岗位依据，不用再去网上瞎抓
        web = {
            "status": "manual",
            "note": "使用了你粘贴的岗位描述作为依据，未联网采集。",
            "sources": [],
            "text": "",
        }
    elif use_web:
        web = web_collector.collect_job_context(job_title)
    else:
        web = {
            "status": "disabled",
            "note": "本次未启用联网采集，仅根据你填写的岗位名称分析。",
            "sources": [],
            "text": "",
        }

    raw, model_used = llm_client.analyze_resume(
        resume.raw_text,
        job_title,
        web.get("text", ""),
        jd_text,
        override=override,
    )
    details = normalize_details(raw)
    # 把联网采集的情况一起存进结果里，前端要展示来源和采集状态
    details["details"]["web_status"] = web.get("status", "")
    details["details"]["web_note"] = web.get("note", "")
    details["details"]["web_sources"] = web.get("sources", [])

    # 和上一次「同一份简历 + 同一个岗位」的分析对比，用来显示"比上次 +N 分"
    previous = db.execute(
        select(Analysis)
        .where(Analysis.resume_id == resume.id, Analysis.job_title == job_title)
        .order_by(Analysis.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if previous is not None:
        details["details"]["previous_score"] = previous.overall_score
        details["details"]["score_delta"] = details["overall_score"] - previous.overall_score
        details["details"]["previous_id"] = previous.id

    analysis = Analysis(
        client_id=client_id,
        resume_id=resume.id,
        job_title=job_title,
        overall_score=details["overall_score"],
        skill_score=details["skill_score"],
        project_score=details["project_score"],
        details=details["details"],
        model_used=model_used,
        is_mock=model_used == "mock",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def normalize_details(raw: dict[str, Any]) -> dict[str, Any]:
    """把模型的原始输出整理成前端能直接用的结构。"""
    skill_score = _as_score(raw.get("skill_score"), default=0)
    project_score = _as_score(raw.get("project_score"), default=0)

    overall_raw = _as_score(raw.get("overall_score"), default=-1)
    if overall_raw < 0:
        # 模型没给总分时，用技能分和项目分的平均值兜底
        overall_raw = round((skill_score + project_score) / 2)

    details = {
        "overall_summary": _as_text(raw.get("overall_summary")),
        "matched_skills": _as_text_list(raw.get("matched_skills")),
        "missing_keywords": _normalize_keywords(raw.get("missing_keywords")),
        "project_comments": _normalize_projects(raw.get("project_comments")),
        "suggestions": _normalize_suggestions(raw.get("suggestions")),
        "interview_questions": _normalize_questions(raw.get("interview_questions")),
        "optimized_resume": _as_text(raw.get("optimized_resume")),
    }

    return {
        "overall_score": overall_raw,
        "skill_score": skill_score,
        "project_score": project_score,
        "details": details,
    }


# ---------------------------------------------------------------- 工具函数


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value).strip()
    return str(value).strip()


def _as_score(value: Any, default: int) -> int:
    """把 '78'、'78分'、7.8 这类值统一变成 0-100 的整数。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        if not match:
            return default
        number = float(match.group())

    # 有些模型会返回 0.78 表示 78 分
    if 0 < number <= 1 and not float(number).is_integer():
        number *= 100

    return max(0, min(100, int(round(number))))


def _as_text_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[、,，;；\n]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("keyword") or item.get("name") or item.get("skill") or item
                text = _as_text(text)
            else:
                text = _as_text(item)
            if text:
                result.append(text)
        return result
    return []


def _normalize_keywords(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_raw_list(value):
        if isinstance(item, dict):
            keyword = _as_text(
                item.get("keyword") or item.get("skill") or item.get("name") or item.get("name_cn")
            )
            entry = {
                "keyword": keyword,
                "category": _as_text(item.get("category") or item.get("type")) or "技能",
                "importance": _normalize_importance(item.get("importance")),
                "note": _as_text(item.get("note") or item.get("reason") or item.get("why")),
            }
        else:
            entry = {"keyword": _as_text(item), "category": "技能", "importance": "中", "note": ""}
        if entry["keyword"]:
            result.append(entry)
    return result[:15]


def _normalize_projects(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_raw_list(value):
        if isinstance(item, dict):
            title = _as_text(item.get("title") or item.get("project") or item.get("name"))
            entry = {
                "title": title or "未命名项目",
                "comment": _as_text(item.get("comment") or item.get("analysis") or item.get("problem")),
                "suggestion": _as_text(item.get("suggestion") or item.get("advice")),
            }
        else:
            entry = {"title": "未命名项目", "comment": _as_text(item), "suggestion": ""}
        if entry["comment"] or entry["suggestion"]:
            result.append(entry)
    return result[:10]


def _normalize_suggestions(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_raw_list(value):
        if isinstance(item, dict):
            entry = {
                "area": _as_text(item.get("area") or item.get("target") or item.get("category")) or "表达",
                "problem": _as_text(item.get("problem") or item.get("issue") or item.get("current")),
                "advice": _as_text(item.get("advice") or item.get("action") or item.get("suggestion")),
                "example": _as_text(item.get("example") or item.get("demo")),
            }
        else:
            entry = {"area": "表达", "problem": "", "advice": _as_text(item), "example": ""}
        if entry["advice"] or entry["problem"]:
            result.append(entry)
    return result[:8]


def _normalize_questions(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_raw_list(value):
        if isinstance(item, dict):
            entry = {
                "question": _as_text(item.get("question") or item.get("q")),
                "why": _as_text(item.get("why") or item.get("reason")),
                "hint": _as_text(item.get("hint") or item.get("answer") or item.get("tip")),
            }
        else:
            entry = {"question": _as_text(item), "why": "", "hint": ""}
        if entry["question"]:
            result.append(entry)
    return result[:10]


def _as_raw_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return [value]


def _normalize_importance(value: Any) -> str:
    text = _as_text(value).lower()
    if text in {"高", "高优先级", "high", "important", "critical"}:
        return "高"
    if text in {"低", "低优先级", "low", "minor"}:
        return "低"
    return "中"
