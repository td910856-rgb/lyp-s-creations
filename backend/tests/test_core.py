"""最小测试集：覆盖几个最容易改坏的纯逻辑。

跑法（在 backend 目录下）：
    .venv\\Scripts\\python.exe -m pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import analyzer, exporter, file_parser, limits  # noqa: E402


class _FakeRequest:
    """够用的假 Request，只为测试取 IP 的逻辑。"""

    def __init__(self, headers=None, host="10.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


def test_client_ip_behind_proxy():
    """线上实测的代理链路：真实 IP 在第一段。"""
    assert (
        limits.client_ip(_FakeRequest({"x-forwarded-for": "110.65.147.194, 162.158.108.39, 10.24.101.1"}))
        == "110.65.147.194"
    )
    # 只有一段的情况
    assert limits.client_ip(_FakeRequest({"x-forwarded-for": "9.9.9.9"})) == "9.9.9.9"
    # 没有这个头就退回直连地址
    assert limits.client_ip(_FakeRequest({}, host="127.0.0.1")) == "127.0.0.1"


def test_score_normalization():
    """模型返回的分数什么格式都有，必须都能变成 0-100 的整数。"""
    assert analyzer._as_score("78分", default=0) == 78
    assert analyzer._as_score(0.74, default=0) == 74
    assert analyzer._as_score("58", default=0) == 58
    assert analyzer._as_score(120, default=0) == 100
    assert analyzer._as_score(-5, default=0) == 0
    assert analyzer._as_score("不知道", default=42) == 42


def test_normalize_details_handles_messy_output():
    """字段缺失、类型不对时也要给出结构稳定的结果。"""
    result = analyzer.normalize_details(
        {
            "skill_score": "60分",
            "project_score": 0.5,
            "matched_skills": "Python、SQL",
            "missing_keywords": ["Transformer", {"keyword": "RAG", "importance": "high"}],
            "suggestions": [{"advice": "补量化结果"}],
            "interview_questions": [{"question": "为什么选这个模型？"}],
        }
    )

    assert result["skill_score"] == 60
    assert result["project_score"] == 50
    # 模型没给总分时用技能和项目的平均分兜底
    assert result["overall_score"] == 55
    assert result["details"]["matched_skills"] == ["Python", "SQL"]
    assert result["details"]["missing_keywords"][1]["importance"] == "高"
    assert result["details"]["interview_questions"][0]["question"] == "为什么选这个模型？"


def test_markdown_to_docx():
    """简历导出应该产出一个能正常打开的 Word 文件。"""
    from docx import Document
    from io import BytesIO

    markdown = """# 张三
## 教育背景
- 某某大学 计算机 2023-2027
> 待补充：填写具体数字
这里是 **加粗** 的一句话。
"""
    data = exporter.markdown_to_docx(markdown)
    assert data[:2] == b"PK"  # docx 本质是个 zip

    document = Document(BytesIO(data))
    texts = [p.text for p in document.paragraphs if p.text.strip()]
    assert "张三" in texts
    assert "教育背景" in texts
    assert any("某某大学" in t for t in texts)


def test_extract_text_from_txt(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("张三\n" * 40, encoding="utf-8")
    text = file_parser.extract_text(path)
    assert "张三" in text


def test_extract_text_rejects_unknown_extension(tmp_path):
    path = tmp_path / "resume.doc"
    path.write_text("legacy", encoding="utf-8")
    try:
        file_parser.extract_text(path)
    except file_parser.ParseError as exc:
        assert ".docx" in str(exc)  # 提示用户另存为 docx
    else:  # pragma: no cover
        raise AssertionError("旧版 .doc 应该被拒绝")
