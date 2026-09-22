"""把优化后的简历（Markdown 文本）导出成 Word 文档。

用 python-docx（解析简历时已经装了），不新增任何依赖。
支持的范围很小：一级/二级/三级标题、无序列表、引用、**加粗**，
刚好覆盖模型输出的排版。
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# 中文字体：Windows 上基本都有
BODY_FONT = "微软雅黑"

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s*(.*)$")


def markdown_to_docx(markdown: str) -> bytes:
    """把 Markdown 简历转成 .docx 的字节内容。"""
    document = Document()
    _setup_page(document)

    for raw_line in (markdown or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            _add_heading(document, len(heading.group(1)), heading.group(2))
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            _add_paragraph(document, bullet.group(1), style="List Bullet")
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            paragraph = _add_paragraph(document, quote.group(1))
            for run in paragraph.runs:
                run.italic = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x92, 0x40, 0x0E)
            continue

        _add_paragraph(document, line)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _setup_page(document: Document) -> None:
    """页面设置：A4 边距 + 中文字体。"""
    for section in document.sections:
        section.top_margin = Cm(1.8)
        section.bottom_margin = Cm(1.8)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    # 中文字体要单独设 eastAsia，否则 Word 里会退回宋体
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.25


def _add_heading(document: Document, level: int, text: str) -> None:
    if level == 1:
        # 一级标题当姓名处理：居中、加大
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(10)
        run = paragraph.add_run(_plain(text))
        run.bold = True
        run.font.size = Pt(18)
        _set_run_font(run)
        return

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10 if level == 2 else 6)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(_plain(text))
    run.bold = True
    run.font.size = Pt(12 if level == 2 else 11)
    if level == 2:
        run.font.color.rgb = RGBColor(0x43, 0x38, 0xCA)
    _set_run_font(run)


def _add_paragraph(document: Document, text: str, style: str | None = None):
    paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()
    for index, part in enumerate(_BOLD_RE.split(text)):
        if not part:
            continue
        run = paragraph.add_run(part)
        if index % 2 == 1:  # 被 ** 包起来的那一段
            run.bold = True
        _set_run_font(run)
    return paragraph


def _set_run_font(run) -> None:
    run.font.name = BODY_FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), BODY_FONT)


def _plain(text: str) -> str:
    """标题里的 ** 直接去掉，不做加粗处理。"""
    return _BOLD_RE.sub(r"\1", text)

