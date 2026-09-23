"""FastAPI 应用入口。

启动方式（在 backend 目录下）：
    python -m uvicorn app.main:app --reload
接口文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import PROJECT_DIR, settings
from .database import cleanup_old_data, engine, init_db
from .routers import analyses, mydata, resumes
from .services import limits


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时建表（表已存在就跳过）
    init_db()
    # 清掉超过保留期的数据（公开部署时很重要）
    removed = cleanup_old_data()
    if removed:
        print(f"[清理] 删除了 {removed} 份超过保留期的简历")

    task = asyncio.create_task(_periodic_cleanup())
    try:
        yield
    finally:
        task.cancel()


async def _periodic_cleanup() -> None:
    """每小时清一次过期数据，不阻塞请求。"""
    while True:
        await asyncio.sleep(3600)
        try:
            cleanup_old_data()
        except Exception as exc:  # 清理失败不能影响服务
            print(f"[清理] 出错：{exc}")


app = FastAPI(
    title="AI 简历优化器 API",
    description="上传简历 + 输入目标岗位，得到匹配度分析和优化后的简历。",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许前端开发服务器访问。前端已经配了代理，这里是双保险。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router)
app.include_router(analyses.router)
app.include_router(mydata.router)


@app.get("/api/health", tags=["系统"], summary="检查服务是否正常")
def health(request: Request) -> dict:
    """前端启动时会调这个接口，用来提示「密钥没配」这类问题。"""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # 数据库文件损坏等少见情况
        db_status = f"error: {exc}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "llm_ready": settings.llm_ready,
        "llm": settings.safe_llm_summary(),
        "web": settings.safe_web_summary(),
        "privacy": settings.safe_privacy_summary(),
        "quota": {"remaining": limits.remaining(limits.client_ip(request))},
        "database": db_status,
    }


# 如果前端已经打包过（frontend/dist 存在），后端直接把它托管起来，
# 这样只启动一个服务就能用完整产品。开发阶段用 npm run dev 更方便。
_DIST_DIR = PROJECT_DIR / "frontend" / "dist"
if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="frontend")
