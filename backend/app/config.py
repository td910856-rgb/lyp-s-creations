"""集中读取环境变量。

原则：密钥只从环境变量 / .env 读取，绝不写进代码，也绝不打进日志。
其它模块统一 `from .config import settings`，不要在别处再读 os.getenv。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录
BACKEND_DIR = Path(__file__).resolve().parent.parent
# 项目根目录（ai-resume-optimizer/）
PROJECT_DIR = BACKEND_DIR.parent
# 读取 backend/.env（不存在也不报错，此时走系统环境变量）
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return (value if value is not None else default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


# 上传的原始文件存放位置。
# 部署到容器里时用 UPLOAD_DIR 指到挂载盘，容器重建数据也不会丢。
_upload_dir = _env("UPLOAD_DIR")
UPLOAD_DIR = Path(_upload_dir) if _upload_dir else BACKEND_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    """应用配置。在 import 时实例化一次，全局共享。"""

    def __init__(self) -> None:
        self.llm_api_key: str = _env("LLM_API_KEY")
        self.llm_base_url: str = _env("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_model: str = _env("LLM_MODEL", "gpt-4o-mini")
        self.llm_timeout: float = _env_float("LLM_TIMEOUT", 120.0)

        # 演示模式：不用密钥、不花钱，也能跑通完整流程
        self.llm_mock: bool = _env("LLM_MOCK", "0").lower() in {"1", "true", "yes", "on"}

        self.max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 10)

        # 限流与数据保留（公开部署时用得上）
        self.rate_limit_enabled: bool = _env("RATE_LIMIT_ENABLED", "1").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.rate_limit_per_day: int = _env_int("RATE_LIMIT_PER_DAY", 10)
        self.rate_limit_per_minute: int = _env_int("RATE_LIMIT_PER_MINUTE", 3)
        self.rate_limit_global_per_day: int = _env_int("RATE_LIMIT_GLOBAL_PER_DAY", 500)
        # 上传的简历和分析记录保留多少小时后自动删除
        self.data_retention_hours: int = _env_int("DATA_RETENTION_HOURS", 72)
        # 公开部署建议设成 1：服务器不再为访客垫付模型费用，必须自带密钥
        self.require_own_key: bool = _env("REQUIRE_OWN_KEY", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        # 联网采集岗位信息
        self.web_search_enabled: bool = _env("WEB_SEARCH_ENABLED", "1").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        # auto = 先试 Bing，再试 DuckDuckGo；也可以写死 bing 或 duckduckgo
        self.web_search_provider: str = _env("WEB_SEARCH_PROVIDER", "auto").lower()
        self.web_search_results: int = _env_int("WEB_SEARCH_MAX_RESULTS", 5)
        self.web_fetch_pages: int = _env_int("WEB_FETCH_PAGES", 2)
        self.web_timeout: float = _env_float("WEB_TIMEOUT", 12.0)
        self.web_max_chars: int = _env_int("WEB_MAX_CHARS", 3000)

        database_url = _env("DATABASE_URL")
        if not database_url:
            # Windows 上也要用正斜杠，SQLAlchemy 才认这个路径
            db_file = (BACKEND_DIR / "resume.db").as_posix()
            database_url = f"sqlite:///{db_file}"
        self.database_url: str = database_url

    @property
    def llm_ready(self) -> bool:
        """是否可以真的调用模型（演示模式也算就绪）。"""
        return self.llm_mock or bool(self.llm_api_key)

    def safe_llm_summary(self) -> dict[str, object]:
        """给前端看的模型状态，保证不泄露密钥。"""
        return {
            "mode": "mock" if self.llm_mock else "live",
            "model": self.llm_model if not self.llm_mock else "演示数据（未调用模型）",
            "base_url": self.llm_base_url,
            "api_key_configured": bool(self.llm_api_key),
        }

    def safe_web_summary(self) -> dict[str, object]:
        """给前端看的联网采集状态。"""
        return {
            "enabled": self.web_search_enabled,
            "provider": self.web_search_provider,
            "max_results": self.web_search_results,
            "fetch_pages": self.web_fetch_pages,
        }

    def safe_privacy_summary(self) -> dict[str, object]:
        """给前端展示的隐私与额度信息。"""
        return {
            "rate_limit_enabled": self.rate_limit_enabled,
            "rate_limit_per_day": self.rate_limit_per_day,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "retention_hours": self.data_retention_hours,
            "require_own_key": self.require_own_key,
        }


settings = Settings()
