"""接口的请求 / 响应结构。

作用有两个：
1. 前后端约定好字段名，改字段时不容易互相踩坑；
2. FastAPI 会据此生成 /docs 里可交互的接口文档。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MissingKeyword(BaseModel):
    """岗位要求里有、但简历里没体现的关键词。"""

    keyword: str
    category: str = "技能"
    importance: str = "中"  # 高 / 中 / 低
    note: str = ""


class ProjectComment(BaseModel):
    """对单个项目的点评。"""

    title: str
    comment: str = ""
    suggestion: str = ""


class Suggestion(BaseModel):
    """一条具体修改建议。"""

    area: str = "表达"
    problem: str = ""
    advice: str = ""
    example: str = ""


class WebSource(BaseModel):
    """联网采集到的一条参考来源。"""

    title: str = ""
    url: str = ""
    snippet: str = ""


class InterviewQuestion(BaseModel):
    """根据简历和岗位预测的面试问题。"""

    question: str
    why: str = ""
    hint: str = ""


class AnalysisDetails(BaseModel):
    """分析结果的详细部分（整体存进数据库的一个 JSON 字段）。"""

    overall_summary: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_keywords: list[MissingKeyword] = Field(default_factory=list)
    project_comments: list[ProjectComment] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    optimized_resume: str = ""
    # 联网采集的情况：ok / empty / failed / disabled
    web_status: str = ""
    web_note: str = ""
    web_sources: list[WebSource] = Field(default_factory=list)
    # 面试问题预测
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    # 和上一次同简历、同岗位的分析对比
    previous_score: int | None = None
    score_delta: int | None = None
    previous_id: int | None = None


class AnalysisRequest(BaseModel):
    """发起一次分析。"""

    resume_id: int = Field(..., ge=1, description="上传接口返回的简历 ID")
    job_title: str = Field(..., description="目标岗位名称")
    use_web: bool = Field(True, description="是否联网采集最新岗位信息")
    job_description: str = Field(
        "",
        description="可选：直接粘贴的岗位描述。填了就以它为准，不再联网采集",
    )

    @field_validator("job_title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        # 长度校验写在自定义校验里，是为了让报错信息是中文的
        # （用 Field(min_length=...) 的话，提示会是英文的 "String should have..."）
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) < 2:
            raise ValueError("目标岗位名称太短了，至少写 2 个字")
        if len(cleaned) > 200:
            raise ValueError("目标岗位名称太长了，请控制在 200 字以内")
        return cleaned

    @field_validator("job_description")
    @classmethod
    def _clean_jd(cls, value: str) -> str:
        # 太短的粘贴内容没意义（可能只粘了个标题），当成没填
        cleaned = (value or "").strip()
        if len(cleaned) < 30:
            return ""
        return cleaned[:8000]


class ResumeOut(BaseModel):
    """上传成功后返回给前端的信息（只给预览，不回传全文）。"""

    id: int
    filename: str
    file_type: str
    char_count: int
    preview: str
    created_at: datetime


class AnalysisOut(BaseModel):
    """一次完整分析结果。"""

    id: int
    resume_id: int
    resume_filename: str = ""
    job_title: str
    overall_score: int
    skill_score: int
    project_score: int
    details: AnalysisDetails
    model_used: str = ""
    is_mock: bool = False
    created_at: datetime


class AnalysisSummary(BaseModel):
    """历史记录列表里的精简条目。"""

    id: int
    job_title: str
    resume_filename: str = ""
    overall_score: int
    is_mock: bool = False
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    llm_ready: bool
    llm: dict
    web: dict = Field(default_factory=dict)
    database: str
