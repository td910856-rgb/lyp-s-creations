"""全项目唯一接触大模型的地方。

外部只想调用一个函数：
    analyze_resume(resume_text, job_title, web_context) -> (结果字典, 使用的模型名)

好处：以后要换模型服务商、换模型名、加缓存、加计费统计，
只改这一个文件，其它代码一行都不用动。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from ..config import settings
from . import prompts


class LLMError(Exception):
    """模型调用或结果解析失败。message 是给用户看的中文提示。"""


def analyze_resume(
    resume_text: str,
    job_title: str,
    web_context: str = "",
    jd_text: str = "",
    override: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str]:
    """分析简历，返回 (结构化结果, 模型名)。

    web_context 是联网采集到的岗位信息，jd_text 是用户自己粘贴的岗位描述。
    两个都可能为空字符串；都为空时就只按岗位名称分析。

    override 允许访客自带密钥（BYOK）：
        {"api_key": ..., "base_url": ..., "model": ...}
    只用于这一次请求，服务端不保存。
    """
    api_key, base_url, model = _resolve_credentials(override)

    # 访客自带密钥时，即使服务器开了演示模式也要真的调用模型
    if settings.llm_mock and not (override or {}).get("api_key"):
        return _mock_result(resume_text, job_title), "mock"

    if not api_key:
        raise LLMError(
            "没有可用的模型密钥。请在页面的「模型设置」里填上你自己的 API Key；"
            "如果你是部署者，就在 backend/.env 里配置 LLM_API_KEY。"
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": prompts.build_user_prompt(resume_text, job_title, web_context, jd_text),
        },
    ]

    raw = _call_model(messages, api_key=api_key, base_url=base_url, model=model)
    try:
        return _parse_json(raw), model
    except ValueError:
        # 模型偶尔会输出不合法 JSON：带上它的回答重试一次
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": prompts.REPAIR_INSTRUCTION})
        raw_retry = _call_model(messages, api_key=api_key, base_url=base_url, model=model)
        try:
            return _parse_json(raw_retry), model
        except ValueError as exc:
            raise LLMError(
                "模型返回的内容不是合法 JSON，重试一次仍然失败。"
                "可以再点一次「开始分析」，或换一个模型（LLM_MODEL）试试。"
            ) from exc


def _resolve_credentials(override: dict[str, str] | None) -> tuple[str, str, str]:
    """访客自带的配置优先，其次用服务器 .env 里的。"""
    override = override or {}
    api_key = (override.get("api_key") or "").strip() or settings.llm_api_key
    base_url = (override.get("base_url") or "").strip() or settings.llm_base_url
    model = (override.get("model") or "").strip() or settings.llm_model
    return api_key, base_url, model


def _call_model(
    messages: list[dict[str, str]],
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """发起一次真实的模型调用。

    这里用 Python 标准库直接发 HTTP 请求，而不是装 openai 那个第三方包。
    原因：本项目只需要一个「发 JSON、收 JSON」的接口，
    标准库够用、少一个依赖，而且整个过程看得见。
    主流的国产模型服务（DeepSeek、通义千问等）都兼容这个接口格式。
    """
    # 把地址拼成 https://xxx/v1/chat/completions
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,  # 低温度让输出更稳定，改简历这类任务不需要发挥
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # 401 密钥不对、404 地址不对、429 太频繁或没额度，都在这里
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(
            f"模型接口返回错误（HTTP {exc.code}）：{detail}。"
            "请检查密钥、接口地址和模型名（在 .env 或页面「模型设置」里）是否写对、"
            "账户是否还有余额。"
        ) from exc
    except (TimeoutError, OSError) as exc:
        raise LLMError(
            f"连接模型接口失败或超时：{exc}。"
            "请检查网络，以及接口地址是否写对（.env 或页面「模型设置」里填的那个）；"
            "如果是模型响应慢，可以把 LLM_TIMEOUT 调大一点。"
        ) from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            "模型返回的内容看不懂，可能这个接口地址不是 OpenAI 兼容格式。"
            "请确认 LLM_BASE_URL 是服务商的 /v1 接口地址。"
        ) from exc

    if not content or not content.strip():
        raise LLMError("模型返回了空内容，请重试一次。")
    return content


def _parse_json(raw: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON。模型经常会附带 ``` 代码块，这里做兼容。"""
    text = raw.strip()

    # 去掉 ```json ... ``` 包裹
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 再从整段文字里截取第一个 { 到最后一个 } 之间的部分
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no json object found")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc

    if not isinstance(data, dict):
        raise ValueError("json root is not an object")
    return data


# ---------------------------------------------------------------- 演示模式

# 演示模式用到的常见技能词表，命中的会出现在「已具备技能」里
_SKILL_WORDS = [
    "Python", "Java", "C++", "Go", "JavaScript", "TypeScript", "SQL", "R", "MATLAB",
    "PyTorch", "TensorFlow", "Keras", "scikit-learn", "Pandas", "NumPy", "OpenCV",
    "Transformer", "BERT", "LLM", "RAG", "LangChain", "NLP", "计算机视觉", "机器学习",
    "深度学习", "推荐系统", "数据挖掘", "数据分析", "爬虫", "Docker", "Kubernetes",
    "Git", "Linux", "MySQL", "Redis", "MongoDB", "FastAPI", "Flask", "Django",
    "React", "Vue", "Node.js", "Spring", "Hadoop", "Spark", "Flink", "Hive",
]


def _mock_result(resume_text: str, job_title: str) -> dict[str, Any]:
    """演示数据：完全不调用模型，用于在没配密钥时跑通整个流程。

    它会真的扫描简历文本，命中哪些技能词就列出来，所以看起来像真结果。
    """
    lowered = resume_text.lower()
    hit = [word for word in _SKILL_WORDS if word.lower() in lowered]
    hit = list(dict.fromkeys(hit))[:12]

    suggestions = [
        {
            "area": "项目",
            "problem": "项目描述停留在「做了什么」，没有说明「做成什么样」。",
            "advice": "每个项目补一句量化结果：数据规模、指标提升、处理效率。",
            "example": "把「负责模型训练」改成「在 8 万条样本上训练 BERT 分类模型，验证集 F1 从 0.78 提升到 0.86」。",
        },
        {
            "area": "技能",
            "problem": f"简历里没有覆盖「{job_title}」岗位要求的部分关键词。",
            "advice": "把真正用过的技能按「语言 / 框架 / 工具」分组，去掉和岗位无关的罗列。",
            "example": "技能栏：Python（熟练）、PyTorch、SQL；了解 Transformer 与 RAG 检索增强。",
        },
        {
            "area": "表达",
            "problem": "经历描述缺少动作动词，读起来像岗位职责而不是个人成果。",
            "advice": "每条经历用「动词 + 对象 + 结果」的结构重写。",
            "example": "「参与数据清洗」→「独立完成 3 万条数据的清洗与标注质检，脏数据比例从 12% 降到 3%」。",
        },
    ]

    return {
        "overall_score": 68,
        "overall_summary": (
            f"这是一份演示结果（当前为演示模式，未调用真实模型）。"
            f"就「{job_title}」而言，简历的技术基础方向是对的，"
            "主要差距在于项目缺少量化结果、岗位关键词覆盖不全。"
            "把这两点补齐，匹配度还能明显提升。"
        ),
        "skill_score": 72,
        "matched_skills": hit or ["（演示模式下未在简历中匹配到常见技能词）"],
        "missing_keywords": [
            {"keyword": "Transformer", "category": "技能", "importance": "高", "note": "算法岗的基础要求，需要能说明原理和实践。"},
            {"keyword": "向量数据库", "category": "工具", "importance": "中", "note": "做 RAG 类项目常见的技术栈。"},
            {"keyword": "模型评估指标", "category": "经验", "importance": "高", "note": "能证明你真的跑过实验而不是只调库。"},
            {"keyword": "工程化部署", "category": "经验", "importance": "中", "note": "实习岗很看重能否把模型跑成服务。"},
            {"keyword": "团队协作", "category": "软技能", "importance": "低", "note": "可以用小组项目的分工体现。"},
        ],
        "project_score": 61,
        "project_comments": [
            {
                "title": "简历中的第一个项目",
                "comment": "演示模式无法真正读懂项目内容，这里只是示例结构。真实模式会逐个点评。",
                "suggestion": "补上数据规模、你负责的模块、最终效果指标这三样。",
            }
        ],
        "suggestions": suggestions,
        "interview_questions": _mock_questions(job_title),
        "optimized_resume": _mock_optimized_resume(resume_text, job_title),
    }


def _mock_questions(job_title: str) -> list[dict[str, str]]:
    """演示模式下的面试问题示例。"""
    return [
        {
            "question": "你简历里提到「负责图像数据标注和质检」，具体是怎么定义质检标准的？",
            "why": "面试官想确认你是执行者还是思考者，标准是不是你定的。",
            "hint": "说清楚标准怎么来的、抽检比例多少、发现不合格怎么处理。",
        },
        {
            "question": "CIFAR-10 那个实验，为什么选这个网络结构？试过别的吗？",
            "why": "验证你是真的调过模型，还是照着教程跑了一遍。",
            "hint": "对比至少两种方案，说明指标差异和你最终的取舍理由。",
        },
        {
            "question": f"你觉得做好「{job_title}」这份工作，最重要的能力是什么？",
            "why": "看你对岗位的理解是否到位，以及自我认知是否清晰。",
            "hint": "结合岗位职责回答，再补一个你已经在做的事来佐证。",
        },
        {
            "question": "项目里遇到最大的困难是什么？你怎么解决的？",
            "why": "经典行为面试题，考察解决问题的过程和主动性。",
            "hint": "用 STAR 结构：背景、任务、你做了什么、结果如何。",
        },
        {
            "question": "你为什么想做这个方向的实习？未来一年想学到什么？",
            "why": "判断你的动机和稳定性，实习生最怕来了就想换方向。",
            "hint": "把个人兴趣、已做的准备和岗位方向串成一条线。",
        },
        {
            "question": "如果给的数据和你的预期不一样，你会怎么处理？",
            "why": "考察数据敏感度和严谨性，这是最容易暴露短板的地方。",
            "hint": "先说核对数据本身，再说排查口径，最后才怀疑结论。",
        },
    ]


def _mock_optimized_resume(resume_text: str, job_title: str) -> str:
    first_line = resume_text.strip().split("\n")[0][:30] or "你的姓名"
    return f"""# {first_line}

> 以下为演示模式下生成的示例结构。配置真实模型后，这里会输出基于你简历全文的改写版本。

## 求职意向
{job_title}

## 教育背景
学校 / 专业 / 学历 / 起止时间 / GPA 或专业排名（有优势再写）

## 专业技能
- 编程语言：Python（熟练）、SQL
- 框架与工具：PyTorch、Git、Linux
- 方向相关：机器学习基础、Transformer、数据处理

## 项目经历
### 项目名称
- 背景：这个项目要解决什么问题，数据规模多大
- 我的工作：具体负责哪一部分（动词开头）
- 结果：指标提升 / 效率提升 / 上线效果（待补充：填写具体数字）

## 实习与校园经历
- 岗位或角色 + 做了什么 + 产出是什么

## 自我评价（可选）
一两句话说明你和这个岗位的契合点，不要写空话。"""
