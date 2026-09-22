"""联网采集岗位信息。

为什么要这一步：用户只输入一个岗位名称，模型手上没有任何岗位要求的依据，
打分和建议只能靠印象猜。这里把网上公开的岗位信息抓回来，当成分析时的参考材料。

四条设计原则：
1. 只用 Python 标准库，不新增依赖；
2. 任何一步失败都只降级，不抛异常——分析必须能继续跑完；
3. 抓回来的内容只是「参考材料」，提示词里会明确告诉模型它可能有噪音；
4. 宁缺毋滥：抓到的正文里必须出现岗位描述特征词，否则当成无效页面丢掉。
"""

from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 这些域名里不可能有岗位要求正文，直接跳过
SKIP_DOMAINS = ("bing.com", "duckduckgo.com", "google.com", "microsoft.com", "baidu.com/link")

# 招聘网站：命中的结果排在前面
JOB_DOMAINS = (
    "zhipin.com",
    "liepin.com",
    "nowcoder.com",
    "shixiseng.com",
    "lagou.com",
    "zhaopin.com",
    "51job.com",
    "yingjiesheng.com",
    "xiaozhaobao",
    "ncss.cn",
    "maimai.cn",
    "linkedin.com",
    "jobs.",
    "job.",
    "talent.",
    "careers.",
)

# 正文里出现这些词，才认为它真的是在描述一个岗位
JD_SIGNALS = (
    "岗位职责",
    "职位描述",
    "工作职责",
    "任职要求",
    "任职资格",
    "职位要求",
    "岗位要求",
    "招聘要求",
    "我们希望你",
    "responsibilities",
    "requirements",
)

# 页面开头出现这些词，说明这是个失效页面（招聘站下架职位后经常返回 200 但内容是 404）
SOFT_404_SIGNALS = (
    "页面不存在",
    "页面找不到了",
    "页面已失效",
    "内容不存在",
    "该页面已删除",
    "职位已下线",
    "该职位已关闭",
    "not found",
)

# 单次最多下载多少字节，防止抓到超大页面
MAX_DOWNLOAD_BYTES = 600_000

# 正文短于这个长度就认为没抓到有效内容
MIN_PAGE_CHARS = 300

# 同一个岗位名称在这么长时间内复用上次的采集结果，避免反复打搜索接口被限流
CACHE_TTL_SECONDS = 1800

# 进程内的简易缓存：{岗位名称: (写入时间, 结果)}
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class WebError(Exception):
    """搜索或抓取失败，message 会写进给用户看的说明里。"""


def collect_job_context(job_title: str) -> dict[str, Any]:
    """带缓存的入口，同一个岗位 30 分钟内不重复联网。"""
    key = job_title.strip().lower()
    cached = _CACHE.get(key)
    if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    result = _collect(job_title)
    _CACHE[key] = (time.time(), result)
    return result


def _collect(job_title: str) -> dict[str, Any]:
    """采集岗位信息。

    永远返回一个字典，不会抛异常：
        {
          "status": "ok" / "empty" / "failed" / "disabled",
          "note":   给用户看的一句话说明,
          "sources": [{"title": ..., "url": ...}, ...],
          "text":   拼好的参考材料，喂给模型
        }
    """
    if not settings.web_search_enabled:
        return _result("disabled", "联网采集已关闭（配置里 WEB_SEARCH_ENABLED=0）。")

    # 加上「岗位职责 任职要求」，搜索结果会明显偏向真正的 JD 页面
    query = f"{job_title} 岗位职责 任职要求"
    try:
        candidates = _search(query, settings.web_search_results)
    except WebError as exc:
        return _result("failed", f"联网搜索失败：{exc}")

    if not candidates:
        return _result("empty", "没有搜到相关的岗位信息，本次仅按岗位名称分析。")

    candidates = _rank(candidates)
    pages = _fetch_pages([item["url"] for item in candidates])

    sources: list[dict[str, str]] = []
    bodies: list[str] = []

    for item in candidates:
        if len(sources) >= settings.web_fetch_pages:
            break
        text = pages.get(item["url"], "")
        if not _looks_like_job_page(text):
            continue
        sources.append(
            {"title": item["title"], "url": item["url"], "snippet": item.get("snippet", "")}
        )
        bodies.append(text)

    if not sources:
        return _result(
            "failed",
            "搜到了结果，但没能读到真正的岗位描述（招聘网站大多需要登录或屏蔽抓取），"
            "本次仅按岗位名称分析。",
            sources=[
                {"title": item["title"], "url": item["url"], "snippet": item.get("snippet", "")}
                for item in candidates[:3]
            ],
        )

    return _result(
        "ok",
        f"已从网上采集到 {len(sources)} 个岗位页面，作为分析参考。",
        sources=sources,
        text=_assemble(sources, bodies),
    )


def _result(
    status: str,
    note: str,
    sources: list[dict[str, str]] | None = None,
    text: str = "",
) -> dict[str, Any]:
    return {"status": status, "note": note, "sources": sources or [], "text": text}


def _assemble(sources: list[dict[str, str]], bodies: list[str]) -> str:
    """把多个页面的正文拼成一段参考材料，总长度受配置限制。"""
    chunks: list[str] = []
    total = 0

    for source, body in zip(sources, bodies):
        header = f"【来源：{source['title']}】\n"
        snippet = source.get("snippet", "")
        if snippet:
            header += f"摘要：{snippet[:200]}\n"

        remain = settings.web_max_chars - total
        if remain <= len(header):
            break
        chunk = header + body[: remain - len(header)]
        chunks.append(chunk)
        total += len(chunk)

    return "\n\n".join(chunks)


def _looks_like_job_page(text: str) -> bool:
    """正文里必须出现岗位描述特征词，且不是失效页面，才算有效。"""
    if len(text) < MIN_PAGE_CHARS:
        return False
    head = text[:800].lower()
    if "not found" in head:
        return False
    # 中文的失效提示可能出现在页面中后部，整段都查一遍
    if any(signal in text for signal in SOFT_404_SIGNALS if signal != "not found"):
        return False
    return any(signal in text for signal in JD_SIGNALS)


def _rank(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """招聘网站的结果排在前面，其它保持原顺序。"""

    def score(item: dict[str, str]) -> int:
        domain = urllib.parse.urlparse(item["url"]).netloc.lower()
        return 0 if any(key in domain for key in JOB_DOMAINS) else 1

    return sorted(items, key=score)


# ---------------------------------------------------------------- 搜索


def _search(query: str, limit: int) -> list[dict[str, str]]:
    """按配置的服务商搜索，默认 auto。

    auto 的顺序是「先 DuckDuckGo 再 Bing」：实测 DuckDuckGo 返回的是真正的
    岗位页面，而 Bing 更容易给出和岗位无关的结果。如果 DuckDuckGo 连不上
    （比如国内网络），会自动落到 Bing。
    """
    provider = (settings.web_search_provider or "auto").lower()
    order = ["duckduckgo", "duckduckgo-lite", "bing"] if provider == "auto" else [provider]

    errors: list[str] = []
    for name in order:
        try:
            if name == "duckduckgo":
                found = _search_duckduckgo(query, limit)
            elif name == "duckduckgo-lite":
                # 主站被限流时，精简版通常还能用
                found = _search_duckduckgo(query, limit, lite=True)
            else:
                found = _search_bing(query, limit)
        except WebError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if found:
            return _dedupe(found, limit)

    if errors:
        raise WebError("；".join(errors))
    return []


def _search_duckduckgo(query: str, limit: int, lite: bool = False) -> list[dict[str, str]]:
    if lite:
        url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
    else:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    page = _http_get(url)

    # 标题链接和摘要是分开的两类标签，按出现顺序一一对应
    titles = re.findall(
        r'(?is)<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        page,
    )
    snippets = re.findall(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', page)

    results: list[dict[str, str]] = []
    for index, (href, title_html) in enumerate(titles):
        target = html.unescape(href)
        # DuckDuckGo 的链接是跳转形式：//duckduckgo.com/l/?uddg=<编码后的真实地址>
        if "uddg=" in target:
            values = urllib.parse.parse_qs(urllib.parse.urlparse(target).query).get("uddg")
            if values:
                target = values[0]
        snippet = _strip_tags(snippets[index]) if index < len(snippets) else ""
        results.append({"url": target, "title": _strip_tags(title_html), "snippet": snippet})

    return [item for item in results if _looks_useful(item)]


def _search_bing(query: str, limit: int) -> list[dict[str, str]]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "count": max(limit * 2, 10), "setlang": "zh-CN", "mkt": "zh-CN"}
    )
    page = _http_get(url)

    results: list[dict[str, str]] = []
    # Bing 的标准结果结构：<li class="b_algo"> ... <h2><a href="...">标题</a></h2> ... <p>摘要</p>
    for block in re.findall(r'(?is)<li class="b_algo".*?</li>', page):
        match = re.search(r'(?is)<h2[^>]*>\s*<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', block)
        if not match:
            continue
        snippet_match = re.search(r"(?is)<p[^>]*>(.*?)</p>", block)
        results.append(
            {
                "url": html.unescape(match.group(1)),
                "title": _strip_tags(match.group(2)),
                "snippet": _strip_tags(snippet_match.group(1)) if snippet_match else "",
            }
        )

    return [item for item in results if _looks_useful(item)]


def _looks_useful(item: dict[str, str]) -> bool:
    url = item.get("url", "")
    if not url.lower().startswith("http"):
        return False
    if any(domain in url.lower() for domain in SKIP_DOMAINS):
        return False
    return bool(item.get("title"))


def _dedupe(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    """同一个网站最多取两条，避免整屏都是同一个招聘站。"""
    seen_domains: dict[str, int] = {}
    seen_urls: set[str] = set()
    result: list[dict[str, str]] = []

    for item in items:
        url = item["url"]
        if url in seen_urls:
            continue
        domain = urllib.parse.urlparse(url).netloc.lower()
        if seen_domains.get(domain, 0) >= 2:
            continue
        seen_urls.add(url)
        seen_domains[domain] = seen_domains.get(domain, 0) + 1
        result.append(item)
        if len(result) >= limit:
            break

    return result


# ---------------------------------------------------------------- 抓取与清洗


def _fetch_pages(urls: list[str]) -> dict[str, str]:
    """并发抓取多个页面，任何一个失败都只是返回空字符串。"""
    if not urls:
        return {}

    def fetch(url: str) -> tuple[str, str]:
        try:
            return url, _html_to_text(_http_get(url))
        except WebError:
            return url, ""

    workers = max(1, min(4, len(urls)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(fetch, urls))


def _http_get(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.web_timeout) as response:
            raw = response.read(MAX_DOWNLOAD_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raise WebError(f"HTTP {exc.code}") from exc
    except (TimeoutError, OSError) as exc:
        raise WebError(str(exc)) from exc

    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _html_to_text(page: str) -> str:
    """把 HTML 变成纯文本：去掉脚本样式、把块级标签换成换行、再剥掉所有标签。"""
    page = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?is)<!--.*?-->", " ", page)
    page = re.sub(r"(?is)<br\s*/?>", "\n", page)
    page = re.sub(r"(?is)</(p|div|li|tr|h[1-6]|section|article)>", "\n", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    page = html.unescape(page)

    lines = []
    for line in page.split("\n"):
        cleaned = re.sub(r"[ \t\u3000]+", " ", line).strip()
        if not cleaned:
            continue
        # 页面里常带一大坨 JSON（前端框架塞进去的），对分析没用还占 token
        if cleaned.startswith(("{", "[")):
            continue
        lines.append(cleaned[:400])
    return "\n".join(lines).strip()


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
