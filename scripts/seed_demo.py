"""虚构演示数据集（小型、手工可核）。

写入 APP_DATABASE_URL 指向的库（需先 alembic upgrade head）。
2 个组织、3 个站点、~30 家虚构企业，覆盖：认证/未认证、期内新增、期内流失、
7 种生命周期状态、3 种等级、1 个测试账号、1 家软删除企业。
运行：python scripts/seed_demo.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import Company, Membership, UserRole  # noqa: E402


def _dt(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


# (名称, org, site, 生命周期, 认证时间, 流失时间, 测试账号)
COMPANIES: list[tuple] = [
    ("云帆智造", "org-demo", "site-east", "active", "2025-03-10T09:00:00", None, False),
    ("东湖新材料", "org-demo", "site-east", "active", "2025-05-02T09:00:00", None, False),
    ("南屿数字", "org-demo", "site-east", "joined", "2025-08-15T09:00:00", None, False),
    ("临江生物", "org-demo", "site-east", "active", "2025-11-20T09:00:00", None, False),
    ("青梧设计", "org-demo", "site-east", "silent", "2025-06-18T09:00:00", None, False),
    ("白鹭物流", "org-demo", "site-east", "churned", "2025-04-05T09:00:00", "2026-09-14T09:00:00", False),
    ("栖霞农业", "org-demo", "site-east", "lead", None, None, False),
    ("松岭能源", "org-demo", "site-east", "negotiating", None, None, False),
    ("云杉检测", "org-demo", "site-east", "churn_warning", "2025-07-22T09:00:00", None, False),
    ("汀兰文化", "org-demo", "site-east", "active", "2026-08-01T09:00:00", None, False),
    ("榕城会展", "org-demo", "site-east", "active", "2026-09-12T09:00:00", None, False),
    ("南风咨询", "org-demo", "site-east", "churned", "2025-09-30T09:00:00", "2026-10-05T09:00:00", False),
    ("鹿鸣酒店", "org-demo", "site-west", "active", "2025-10-11T09:00:00", None, False),
    ("雁栖环保", "org-demo", "site-west", "active", "2026-06-25T09:00:00", None, False),
    ("砚台软件", "org-demo", "site-west", "silent", "2025-12-01T09:00:00", None, False),
    ("孤山贸易", "org-demo", "site-west", "joined", "2026-10-08T09:00:00", None, False),
    ("沧澜海产", "org-demo", "site-west", "lead", None, None, False),
    ("九皋机械", "org-other", "site-north", "active", "2025-05-19T09:00:00", None, False),
    ("锦溪纺织", "org-other", "site-north", "active", "2026-03-03T09:00:00", None, False),
    ("墨阳电子", "org-other", "site-north", "churn_warning", "2025-11-08T09:00:00", None, False),
    ("测试专用企业（不计入指标）", "org-demo", "site-east", "active", "2025-01-01T09:00:00", None, True),
    ("已软删除企业（不计入指标）", "org-demo", "site-east", "active", "2025-01-02T09:00:00", None, False),
]

# (企业名, 等级, start, end(或None), joined_at)
MEMBERSHIPS: list[tuple] = [
    ("云帆智造", "premium", "2025-03-15", None, "2025-03-15T09:00:00"),
    ("东湖新材料", "advanced", "2025-05-10", None, "2025-05-10T09:00:00"),
    ("南屿数字", "standard", "2026-10-02", None, "2026-10-02T09:00:00"),
    ("临江生物", "premium", "2025-12-01", None, "2025-12-01T09:00:00"),
    ("青梧设计", "standard", "2025-06-20", "2026-08-31", "2025-06-20T09:00:00"),
    ("白鹭物流", "standard", "2025-04-10", "2026-09-14", "2025-04-10T09:00:00"),
    ("云杉检测", "advanced", "2025-08-01", None, "2025-08-01T09:00:00"),
    ("汀兰文化", "standard", "2026-08-05", None, "2026-08-05T09:00:00"),
    ("榕城会展", "advanced", "2026-09-15", None, "2026-09-15T09:00:00"),
    ("南风咨询", "standard", "2025-10-01", "2026-10-05", "2025-10-01T09:00:00"),
    ("鹿鸣酒店", "premium", "2025-11-01", None, "2025-11-01T09:00:00"),
    ("雁栖环保", "standard", "2026-07-01", None, "2026-07-01T09:00:00"),
    ("砚台软件", "standard", "2025-12-05", "2026-06-30", "2025-12-05T09:00:00"),
    ("孤山贸易", "standard", "2026-10-10", None, "2026-10-10T09:00:00"),
    ("九皋机械", "advanced", "2025-06-01", None, "2025-06-01T09:00:00"),
    ("锦溪纺织", "standard", "2026-03-10", None, "2026-03-10T09:00:00"),
    ("墨阳电子", "premium", "2025-12-15", None, "2025-12-15T09:00:00"),
    ("测试专用企业（不计入指标）", "premium", "2025-01-05", None, "2025-01-05T09:00:00"),
    ("已软删除企业（不计入指标）", "standard", "2025-01-06", None, "2025-01-06T09:00:00"),
]

USER_ROLES: list[tuple] = [
    ("user-head-east", "org-demo", "site-east", "club_head"),
    ("user-head-west", "org-demo", "site-west", "club_head"),
    ("user-head-north", "org-other", "site-north", "club_head"),
    ("user-admin-demo", "org-demo", "site-east", "admin"),
    ("user-admin-demo", "org-demo", "site-west", "admin"),
]


def main() -> None:
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        raise SystemExit("export APP_DATABASE_URL first (see .env.example)")
    engine = create_engine(url, future=True)
    name_by_key: dict[str, Company] = {}
    with Session(engine) as db:
        created = 0
        for name, org, site, status, verified, churned, is_test in COMPANIES:
            company = Company(
                name=name,
                org_id=org,
                site_id=site,
                lifecycle_status=status,
                verified_at=_dt(verified) if verified else None,
                churned_at=_dt(churned) if churned else None,
                is_test_account=is_test,
                created_by="seed_demo",
            )
            if name.startswith("已软删除"):
                company.deleted_at = _dt("2026-11-01T00:00:00")
            db.add(company)
            name_by_key[(org, site, name)] = company
            created += 1
        db.flush()  # 先落企业拿到 id，再建会籍
        for comp_name, tier, start, end, joined in MEMBERSHIPS:
            org = next(o for (o, s, n) in name_by_key if n == comp_name)
            site = next(s for (o, s, n) in name_by_key if n == comp_name)
            db.add(
                Membership(
                    company_id=name_by_key[(org, site, comp_name)].id,
                    tier=tier,
                    status="effective",
                    start_date=start,
                    end_date=end,
                    joined_at=_dt(joined),
                    org_id=org,
                    site_id=site,
                    created_by="seed_demo",
                )
            )
        for user_id, org, site, role in USER_ROLES:
            db.add(UserRole(user_id=user_id, org_id=org, site_id=site, role=role, created_by="seed_demo"))
        db.commit()
    print(f"seeded: {created} companies, {len(MEMBERSHIPS)} memberships, {len(USER_ROLES)} user_roles (all fictional)")


if __name__ == "__main__":
    main()
