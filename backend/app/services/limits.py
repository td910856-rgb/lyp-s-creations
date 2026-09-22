"""按 IP 的简单限流。

为什么需要：网站一旦公开，就会有人（或爬虫）反复调用。
不限流的话，模型额度几分钟就被烧光。

实现是进程内内存计数，重启就清零——对一个单机小站足够用。
以后要横向扩展再换 Redis，接口不用改。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from ..config import settings

_lock = threading.Lock()
_state: dict[str, object] = {"day": "", "per_ip": {}, "minute": {}, "global": 0}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check(ip: str, use_own_key: bool = False, count_quota: bool = True) -> tuple[bool, str]:
    """检查并记一次数。

    返回 (是否放行, 拒绝时给用户看的话)。
    use_own_key=True（访客自带密钥）时不占服务器的每日额度，但依然受每分钟限制。
    count_quota=False 用于上传这类动作：只受每分钟限制，不吃每日分析额度。
    """
    if not settings.rate_limit_enabled:
        return True, ""

    now = time.time()
    counted = not use_own_key and count_quota
    with _lock:
        today = _today()
        if _state["day"] != today:
            _state["day"] = today
            _state["per_ip"] = {}
            _state["minute"] = {}
            _state["global"] = 0

        per_ip = _state["per_ip"]  # type: ignore[assignment]
        minute = _state["minute"]  # type: ignore[assignment]

        # 每分钟窗口
        recent = [t for t in minute.get(ip, []) if now - t < 60]
        if len(recent) >= settings.rate_limit_per_minute:
            minute[ip] = recent
            return False, (
                f"请求太频繁了，每分钟最多 {settings.rate_limit_per_minute} 次，"
                "请等一分钟再试。"
            )

        if counted:
            used = int(per_ip.get(ip, 0))
            if used >= settings.rate_limit_per_day:
                return False, (
                    f"今天的免费额度用完了（每天 {settings.rate_limit_per_day} 次）。"
                    "可以填自己的模型密钥继续用，或者明天再来。"
                )
            if int(_state["global"]) >= settings.rate_limit_global_per_day:
                return False, "今天网站整体的额度已经用完了，明天再来吧。"

        recent.append(now)
        minute[ip] = recent
        if counted:
            per_ip[ip] = int(per_ip.get(ip, 0)) + 1
            _state["global"] = int(_state["global"]) + 1

    return True, ""


def remaining(ip: str, use_own_key: bool = False) -> int | None:
    """还可以用几次（给前端显示）。自带密钥时返回 None 表示不限。"""
    if not settings.rate_limit_enabled or use_own_key:
        return None
    with _lock:
        used = int(_state["per_ip"].get(ip, 0))  # type: ignore[union-attr]
    return max(0, settings.rate_limit_per_day - used)
