"""基准数据集：10,000 家虚构企业（验收 4：P95 < 1 秒）。

固定种子（random.Random(1856)），可重复生成完全相同的数据。
写入 APP_DATABASE_URL 指向的库，org=org-bench，site=site-bench-1/site-bench-2。
运行：python scripts/seed_benchmark.py
"""
import os
import random
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, insert  # noqa: E402

from app.models import Company, Membership, UserRole  # noqa: E402

ORG = "org-bench"
SITES = ("site-bench-1", "site-bench-2")
TOTAL = 10_000
LIFECYCLE = ("lead", "negotiating", "joined", "active", "silent", "churn_warning", "churned")
TIERS = ("standard", "advanced", "premium")
NAME_PARTS_A = ("云", "东", "南", "青", "白", "松", "汀", "榕", "鹿", "雁", "砚", "孤", "沧", "九", "锦", "墨")
NAME_PARTS_B = ("帆智造", "湖新材", "屿数字", "梧设计", "鹭物流", "岭能源", "兰文化", "城会展", "鸣酒店", "栖环保", "台软件", "山贸易", "澜海产", "皋机械", "溪纺织", "阳电子")
BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def main() -> None:
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        raise SystemExit("export APP_DATABASE_URL first (see .env.example)")
    rng = random.Random(1856)
    engine = create_engine(url, future=True)
    try:
        _seed(engine, rng)
    finally:
        engine.dispose()


def _seed(engine, rng: random.Random) -> None:

    company_rows = []
    membership_rows = []
    for i in range(TOTAL):
        site = SITES[i % len(SITES)]
        name = f"{NAME_PARTS_A[i % len(NAME_PARTS_A)]}{NAME_PARTS_B[(i // len(NAME_PARTS_A)) % len(NAME_PARTS_B)]}-{i:05d}"
        months_ago = rng.randint(1, 30)
        joined = datetime(2024, 1, 1, tzinfo=timezone.utc)  # 占位，下面按月偏移
        year = 2024 + (30 - months_ago) // 12
        month = (30 - months_ago) % 12 + 1
        joined = datetime(year, month, rng.randint(1, 28), 9, 0, 0, tzinfo=timezone.utc)
        verified = joined if rng.random() < 0.8 else None
        churned = None
        status = rng.choices(LIFECYCLE, weights=[6, 8, 10, 45, 12, 9, 10])[0]
        if status == "churned":
            churn_month = min(30, months_ago - rng.randint(1, 6))
            if churn_month < 0:
                churn_month = months_ago
            cy = 2024 + (30 - churn_month) // 12
            cm = (30 - churn_month) % 12 + 1
            churned = datetime(cy, cm, rng.randint(1, 28), 18, 0, 0, tzinfo=timezone.utc)
            verified = verified or joined
        company_rows.append(
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"bench-company:{i}"),
                "name": name,
                "lifecycle_status": status,
                "verified_at": verified,
                "churned_at": churned,
                "is_test_account": False,
                "org_id": ORG,
                "site_id": site,
                "created_by": "seed_benchmark",
            }
        )
        if verified is not None and status != "churned" and rng.random() < 0.85:
            end = None
            mstatus = "effective"
            if rng.random() < 0.2:
                mstatus = "expired"
                end = date(joined.year, joined.month, 28)
            membership_rows.append(
                {
                    "id": uuid.uuid5(uuid.NAMESPACE_URL, f"bench-membership:{i}"),
                    "company_id": company_rows[-1]["id"],
                    "tier": rng.choices(TIERS, weights=[50, 30, 20])[0],
                    "status": mstatus,
                    "start_date": date(joined.year, joined.month, min(28, joined.day)),
                    "end_date": end,
                    "joined_at": joined,
                    "org_id": ORG,
                    "site_id": site,
                    "created_by": "seed_benchmark",
                }
            )

    role_rows = [
        {
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"bench-role:{site}"),
            "user_id": f"user-head-{site}",
            "role": "club_head",
            "org_id": ORG,
            "site_id": site,
            "created_by": "seed_benchmark",
        }
        for site in SITES
    ]

    with engine.begin() as conn:
        # 幂等：先清掉上一轮 seed_benchmark 写入的行（先子表后父表；uuid5 固定主键，直接重插会主键冲突）
        from sqlalchemy import delete as _delete, text

        conn.execute(_delete(Membership).where(Membership.created_by == "seed_benchmark"))
        conn.execute(_delete(UserRole).where(UserRole.created_by == "seed_benchmark"))
        conn.execute(_delete(Company).where(Company.created_by == "seed_benchmark"))
        conn.execute(insert(Company), company_rows)
        conn.execute(insert(Membership), membership_rows)
        conn.execute(insert(UserRole), role_rows)
        # 关键：bulk insert 后 ANALYZE，否则 planner 在空表统计下会选灾难性计划
        conn.execute(text("analyze companies"))
        conn.execute(text("analyze memberships"))
    print(f"seeded benchmark (idempotent re-run safe): {len(company_rows)} companies, {len(membership_rows)} memberships, {len(role_rows)} user_roles (org={ORG}, all fictional, seed=1856)")


if __name__ == "__main__":
    main()
