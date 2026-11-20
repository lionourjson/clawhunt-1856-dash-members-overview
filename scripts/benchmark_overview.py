"""HTTP 基准：对运行中的 uvicorn 发起真实请求，输出 P50/P95/P99。

验收 4：10,000 fictional enterprises under interface P95 < 1 second (benchmark)。

用法：
  1) alembic upgrade head
  2) python scripts/seed_benchmark.py
  3) uvicorn app.main:app --port 8000   （APP_DASH_CACHE_TTL_SECONDS=0 时测冷查询）
  4) python scripts/benchmark_overview.py [--requests 100] [--refresh]
参数：
  --requests N   请求次数（默认 100）
  --refresh      每次带 refresh=1，绕过 10 分钟缓存（测真实计算链路）
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = os.environ.get("APP_BENCHMARK_BASE_URL", "http://127.0.0.1:8000")
ORG = "org-bench"
SITE = "site-bench-1"
HEADERS = {"X-Org-Id": ORG, "X-User-Id": "user-head-site-bench-1"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    latencies_ms: list[float] = []
    codes: list[int] = []
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # 预热一次，确认接口可用
        r = client.get("/api/dash/members/overview", params={"site_id": SITE}, headers=HEADERS)
        r.raise_for_status()
        sample = r.json()
        effective = sample["data"]["metrics"]["DASH_MEMBERS_EFFECTIVE_END"]["value"]
        print(f"预热请求 OK：effective_members_end={effective}（period={sample['data']['period']}）")

        for _ in range(args.requests):
            params = {"site_id": SITE}
            if args.refresh:
                params["refresh"] = "1"
            t0 = time.perf_counter()
            resp = client.get("/api/dash/members/overview", params=params, headers=HEADERS)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            codes.append(resp.status_code)
            latencies_ms.append(elapsed_ms)

    latencies_ms.sort()
    n = len(latencies_ms)

    def pct(p: float) -> float:
        return latencies_ms[min(n - 1, max(0, round(p * (n - 1))))]

    result = {
        "requests": n,
        "status_codes": {str(c): codes.count(c) for c in sorted(set(codes))},
        "p50_ms": round(pct(0.50), 1),
        "p95_ms": round(pct(0.95), 1),
        "p99_ms": round(pct(0.99), 1),
        "max_ms": round(latencies_ms[-1], 1),
        "mean_ms": round(statistics.fmean(latencies_ms), 1),
        "refresh": args.refresh,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = result["p95_ms"] < 1000 and set(codes) == {200}
    print(f"P95 < 1000ms: {'PASS' if ok else 'FAIL'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
