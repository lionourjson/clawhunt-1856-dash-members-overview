"""验收 4：10,000 fictional enterprises under interface P95 < 1 second (benchmark)。

- 固定种子造 10,000 家虚构企业 + 会籍（事务内 bulk insert，测试结束回滚）；
- 通过 TestClient 走真实 HTTP 接口（refresh=1 绕过缓存，测的是完整计算链路）；
- 30 次请求取 P95，断言 < 1000 ms。
另配 scripts/benchmark_overview.py 做真实 uvicorn 进程的 HTTP 基准（README 记录输出）。
"""
import statistics
import time

import pytest

ORG = "org-bench"
SITE = "site-bench-1"
PERIOD = "2026-06"  # 基准数据集最近业务月份（见 scripts/seed_benchmark.py 的月份分布）
REQUESTS = 30


@pytest.fixture(scope="function")
def bench_10k(test_tx):
    """事务内 bulk insert 10,000 家企业 + 会籍 + 授权行（结束回滚，不留数据）。"""
    import random
    import uuid
    from datetime import date, datetime, timezone

    from app.models import Company, Membership, UserRole

    rng = random.Random(1856)
    session = test_tx

    LIFECYCLE = ("lead", "negotiating", "joined", "active", "silent", "churn_warning", "churned")
    TIERS = ("standard", "advanced", "premium")

    company_rows = []
    membership_rows = []
    for i in range(10_000):
        site = "site-bench-1" if i % 2 == 0 else "site-bench-2"
        months_ago = rng.randint(1, 30)
        year = 2024 + (30 - months_ago) // 12
        month = (30 - months_ago) % 12 + 1
        joined = datetime(year, month, rng.randint(1, 28), 9, 0, 0, tzinfo=timezone.utc)
        verified = joined if rng.random() < 0.8 else None
        status = rng.choices(LIFECYCLE, weights=[6, 8, 10, 45, 12, 9, 10])[0]
        churned = None
        if status == "churned":
            churn_month = max(months_ago - rng.randint(1, 6), 1)
            cy = 2024 + (30 - churn_month) // 12
            cm = (30 - churn_month) % 12 + 1
            churned = datetime(cy, cm, rng.randint(1, 28), 18, 0, 0, tzinfo=timezone.utc)
            verified = verified or joined
        company_id = uuid.uuid5(uuid.NAMESPACE_URL, f"bench-test:{i}")
        company_rows.append(
            {
                "id": company_id,
                "name": f"虚构企业-{i:05d}",
                "lifecycle_status": status,
                "verified_at": verified,
                "churned_at": churned,
                "is_test_account": False,
                "org_id": ORG,
                "site_id": site,
                "created_by": "bench-test",
            }
        )
        if verified is not None and status != "churned" and rng.random() < 0.85:
            mstatus = "expired" if rng.random() < 0.2 else "effective"
            end = date(joined.year, joined.month, 28) if mstatus == "expired" else None
            membership_rows.append(
                {
                    "id": uuid.uuid5(uuid.NAMESPACE_URL, f"bench-test-m:{i}"),
                    "company_id": company_id,
                    "tier": rng.choices(TIERS, weights=[50, 30, 20])[0],
                    "status": mstatus,
                    "start_date": date(joined.year, joined.month, min(28, joined.day)),
                    "end_date": end,
                    "joined_at": joined,
                    "org_id": ORG,
                    "site_id": site,
                    "created_by": "bench-test",
                }
            )

    session.execute(
        Company.__table__.insert(), company_rows
    )
    session.execute(Membership.__table__.insert(), membership_rows)
    # 关键：bulk insert 后立即 ANALYZE，否则 planner 在空表统计下会选灾难性计划
    # （实测：无 ANALYZE 时 count(distinct) 走 Nested Loop 扫 8000 万行组合，单查询 88 秒）
    from sqlalchemy import text

    session.execute(text("analyze companies"))
    session.execute(text("analyze memberships"))
    session.add_all(
        [
            UserRole(user_id="user-head-site-bench-1", org_id=ORG, site_id="site-bench-1", role="club_head", created_by="bench-test"),
            UserRole(user_id="user-head-site-bench-2", org_id=ORG, site_id="site-bench-2", role="club_head", created_by="bench-test"),
        ]
    )
    session.flush()
    return {"headers": {"X-Org-Id": ORG, "X-User-Id": "user-head-site-bench-1"}}


def test_p95_under_1s(client, bench_10k):
    """10,000 家虚构企业：接口 P95 < 1 秒（refresh=1 每次绕过缓存，测完整计算）。"""
    headers = bench_10k["headers"]
    params = {"site_id": SITE, "period": PERIOD, "refresh": "1"}

    warmup = client.get("/api/dash/members/overview", params=params, headers=headers)
    assert warmup.status_code == 200
    effective = warmup.json()["data"]["metrics"]["DASH_MEMBERS_EFFECTIVE_END"]["value"]
    assert effective > 1000, f"benchmark dataset should have >1000 effective members, got {effective}"

    latencies = []
    for _ in range(REQUESTS):
        t0 = time.perf_counter()
        resp = client.get("/api/dash/members/overview", params=params, headers=headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        latencies.append(elapsed_ms)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
    print(f"\nbenchmark: n={REQUESTS} p50={p50:.1f}ms p95={p95:.1f}ms max={latencies[-1]:.1f}ms mean={statistics.fmean(latencies):.1f}ms")
    assert p95 < 1000, f"p95 {p95:.1f}ms >= 1000ms"
