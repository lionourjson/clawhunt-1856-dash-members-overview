"""边界⑦（重复操作、幂等）：seed 脚本重跑不翻倍、不主键冲突。

在临时 scratch 库（dash_members_seedtest，测完即删）里对两个脚本各真实运行两次，
断言 created_by 计数恒定——不污染 dash_members_test（其他测试的 org/site 数据）。
"""
import pytest
from sqlalchemy import create_engine, text

from app.config import DATABASE_ADMIN_URL
from app.models import Base

SCRATCH_DB = "dash_members_seedtest"


def _scratch_url() -> str:
    return DATABASE_ADMIN_URL.rsplit("/", 1)[0] + "/" + SCRATCH_DB


@pytest.fixture()
def scratch_db(monkeypatch):
    admin = create_engine(DATABASE_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'drop database if exists "{SCRATCH_DB}"'))
        conn.execute(text(f'create database "{SCRATCH_DB}"'))
    admin.dispose()
    url = _scratch_url()
    monkeypatch.setenv("APP_DATABASE_URL", url)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    yield url
    engine.dispose()
    admin = create_engine(DATABASE_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        # 兜底终止残留连接（seed 脚本引擎已 dispose，正常无残留）
        conn.execute(text(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname = :d and pid <> pg_backend_pid()"
        ), {"d": SCRATCH_DB})
        conn.execute(text(f'drop database if exists "{SCRATCH_DB}"'))
    admin.dispose()


def _count(url: str, table: str, created_by: str) -> int:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            return int(conn.execute(
                text(f"select count(*) from {table} where created_by = :cb"), {"cb": created_by}
            ).scalar())
    finally:
        engine.dispose()


def test_seed_scripts_idempotent(scratch_db):
    """seed_demo / seed_benchmark 各跑两遍：行数恒定、无 IntegrityError。"""
    from scripts.seed_benchmark import main as seed_benchmark_main
    from scripts.seed_demo import main as seed_demo_main

    seed_demo_main()
    seed_demo_main()
    assert _count(scratch_db, "companies", "seed_demo") == 22
    assert _count(scratch_db, "memberships", "seed_demo") == 19
    assert _count(scratch_db, "user_roles", "seed_demo") == 5

    seed_benchmark_main()
    seed_benchmark_main()
    assert _count(scratch_db, "companies", "seed_benchmark") == 10000
