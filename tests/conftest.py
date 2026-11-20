"""pytest fixture：连真实 PostgreSQL 16。

- 测试库 APP_DATABASE_TEST_URL（默认 postgresql+psycopg://postgres@127.0.0.1:5432/dash_members_test）
  不存在时用 APP_DATABASE_ADMIN_URL 自动创建；
- 建表后写入口径库种子（与 alembic 0001 同源：app.dash.calibers）；
- 每个用例一个共享事务（test_tx）：client 与各 seed fixture 都用同一个会话，
  用例结束回滚，互相隔离；
- FastAPI 用 DependencyOverrides 把 get_db 换成测试会话。
"""
import os
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import db as app_db
from app.config import DATABASE_ADMIN_URL
from app.dash.cache import overview_cache
from app.dash.calibers import CALIBERS
from app.models import Base, Company, Membership, UserRole  # noqa: F401
from app.models.base import new_uuid

TEST_DB_URL = os.environ.get(
    "APP_DATABASE_TEST_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5432/dash_members_test",
)

HEADERS_ORG_DEMO = {"X-Org-Id": "org-demo", "X-User-Id": "user-head-east"}


def _ensure_test_db(admin_url: str, test_url: str) -> None:
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    dbname = test_url.rsplit("/", 1)[1]
    with admin.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :d"), {"d": dbname}
        ).scalar()
        if not exists:
            conn.execute(text(f'create database "{dbname}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def pg_engine() -> Generator[Engine, None, None]:
    _ensure_test_db(DATABASE_ADMIN_URL, TEST_DB_URL)
    engine = create_engine(TEST_DB_URL, future=True)
    Base.metadata.create_all(engine)
    # 口径库种子（与迁移 0001 同源）
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into metric_calibers (id, code, version, name, definition) "
                "values (:id, :code, :version, :name, :definition) on conflict (code) do nothing"
            ),
            [
                {
                    "id": new_uuid(),
                    "code": c.code,
                    "version": c.version,
                    "name": c.name,
                    "definition": c.definition,
                }
                for c in CALIBERS
            ],
        )
    yield engine
    engine.dispose()


@pytest.fixture()
def test_tx(pg_engine: Engine) -> Generator[Session, None, None]:
    """每个用例一个事务级会话：client 与 seed fixture 共享，结束回滚。"""
    maker = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False, future=True)
    conn = pg_engine.connect()
    trans = conn.begin()
    session = maker(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()


@pytest.fixture()
def client(pg_engine: Engine, test_tx: Session) -> Generator[object, None, None]:
    overview_cache.clear()

    def override_get_db():
        try:
            yield test_tx
            test_tx.commit()
        except Exception:
            test_tx.rollback()
            raise
        finally:
            pass

    from fastapi.testclient import TestClient

    from app.main import app

    app.dependency_overrides[app_db.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _dt(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


@pytest.fixture()
def seed_demo_site(test_tx: Session) -> dict:
    """一个固定的小型虚构站点：手工可算，供验收 1 的逐指标核对。

    org-demo / site-east，数据覆盖 2025-2026 年；另有 1 个测试账号企业、
    1 家软删除企业（都不应计入任何指标）。
    """
    session = test_tx

    def company(name, status, verified=None, churned=None, is_test=False, site="site-east", org="org-demo", deleted=None):
        c = Company(
            name=name,
            org_id=org,
            site_id=site,
            lifecycle_status=status,
            verified_at=_dt(verified) if verified else None,
            churned_at=_dt(churned) if churned else None,
            is_test_account=is_test,
            created_by="test",
        )
        if deleted:
            c.deleted_at = _dt(deleted)
        session.add(c)
        return c

    companies = {
        "云帆智造": company("云帆智造", "active", "2025-03-10T09:00:00"),
        "东湖新材料": company("东湖新材料", "active", "2025-05-02T09:00:00"),
        "南屿数字": company("南屿数字", "joined", "2025-08-15T09:00:00"),
        "临江生物": company("临江生物", "active", "2025-11-20T09:00:00"),
        "青梧设计": company("青梧设计", "silent", "2025-06-18T09:00:00"),
        "白鹭物流": company("白鹭物流", "churned", "2025-04-05T09:00:00", "2026-09-14T09:00:00"),
        "栖霞农业": company("栖霞农业", "lead"),
        "松岭能源": company("松岭能源", "negotiating"),
        "云杉检测": company("云杉检测", "churn_warning", "2025-07-22T09:00:00"),
        "汀兰文化": company("汀兰文化", "active", "2026-08-01T09:00:00"),
        "榕城会展": company("榕城会展", "active", "2026-09-12T09:00:00"),
        "南风咨询": company("南风咨询", "churned", "2025-09-30T09:00:00", "2026-10-05T09:00:00"),
        "测试账号企业": company("测试账号企业", "active", "2025-01-01T09:00:00", is_test=True),
        "已删除企业": company("已删除企业", "active", "2025-01-02T09:00:00", deleted="2026-11-01T00:00:00"),
    }
    session.flush()  # 先落企业，拿到 id 再建会籍
    memberships = [
        Membership(company_id=companies["云帆智造"].id, tier="premium", status="effective", start_date="2025-03-15", end_date=None, joined_at=_dt("2025-03-15T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["东湖新材料"].id, tier="advanced", status="effective", start_date="2025-05-10", end_date=None, joined_at=_dt("2025-05-10T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["南屿数字"].id, tier="standard", status="effective", start_date="2026-10-02", end_date=None, joined_at=_dt("2026-10-02T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["临江生物"].id, tier="premium", status="effective", start_date="2025-12-01", end_date=None, joined_at=_dt("2025-12-01T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["青梧设计"].id, tier="standard", status="effective", start_date="2025-06-20", end_date="2026-08-31", joined_at=_dt("2025-06-20T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["白鹭物流"].id, tier="standard", status="effective", start_date="2025-04-10", end_date="2026-09-14", joined_at=_dt("2025-04-10T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["云杉检测"].id, tier="advanced", status="effective", start_date="2025-08-01", end_date=None, joined_at=_dt("2025-08-01T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["汀兰文化"].id, tier="standard", status="effective", start_date="2026-08-05", end_date=None, joined_at=_dt("2026-08-05T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["榕城会展"].id, tier="advanced", status="effective", start_date="2026-09-15", end_date=None, joined_at=_dt("2026-09-15T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["南风咨询"].id, tier="standard", status="effective", start_date="2025-10-01", end_date="2026-10-05", joined_at=_dt("2025-10-01T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["测试账号企业"].id, tier="premium", status="effective", start_date="2025-01-05", end_date=None, joined_at=_dt("2025-01-05T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
        Membership(company_id=companies["已删除企业"].id, tier="standard", status="effective", start_date="2025-01-06", end_date=None, joined_at=_dt("2025-01-06T09:00:00"), org_id="org-demo", site_id="site-east", created_by="test"),
    ]
    session.add_all(memberships)
    session.add_all(
        [
            UserRole(user_id="user-head-east", org_id="org-demo", site_id="site-east", role="club_head", created_by="test"),
            UserRole(user_id="user-head-west", org_id="org-demo", site_id="site-west", role="club_head", created_by="test"),
            UserRole(user_id="user-head-north", org_id="org-other", site_id="site-north", role="club_head", created_by="test"),
            UserRole(user_id="user-admin-demo", org_id="org-demo", site_id="site-east", role="admin", created_by="test"),
            UserRole(user_id="user-admin-demo", org_id="org-demo", site_id="site-west", role="admin", created_by="test"),
        ]
    )
    session.flush()
    return {"headers": dict(HEADERS_ORG_DEMO), "companies": companies, "memberships": memberships}
