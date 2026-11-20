"""进程内 TTL 缓存（默认 10 分钟，工单要求）。

key = (org_id, site_id, period)。TTL 从环境变量 APP_DASH_CACHE_TTL_SECONDS 读，
0 表示禁用（测试与基准跑冷数据用）。
"""
import os
import time


class TTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple, tuple[float, object]] = {}

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def get(self, key: tuple):
        if not self.enabled:
            return None
        hit = self._store.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def put(self, key: tuple, value: object) -> None:
        if not self.enabled:
            return
        self._store[key] = (time.monotonic() + self.ttl_seconds, value)

    def clear(self) -> None:
        self._store.clear()


def default_ttl_seconds() -> int:
    return int(os.environ.get("APP_DASH_CACHE_TTL_SECONDS", "600"))


overview_cache = TTLCache(default_ttl_seconds())
