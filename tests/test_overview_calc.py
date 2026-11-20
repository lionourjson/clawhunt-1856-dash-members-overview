"""验收 1：Each indicator on the fictional data set is consistent with manual calculation (test)。

两重核对：
1. 手工计算（写死的期望值，依据 conftest.seed_demo_site 的数据逐企业推算）；
2. 独立 raw SQL 复算（与 app/dash/metrics.py 不同的实现路径）。
两者都必须与接口返回一致。
"""
import pytest
from sqlalchemy import text

from app.dash.cache import overview_cache
from app.models.company import LIFECYCLE_STATUSES

PERIOD = "2026-10"
EXPECTED_LIFECYCLE = {
    "lead": 1,
    "negotiating": 1,
    "joined": 1,
    "active": 5,
    "silent": 1,
    "churn_warning": 1,
    "churned": 2,
}
EXPECTED_TIER = {"standard": 2, "advanced": 3, "premium": 2}
EXPECTED_TREND = [
    {"month": "2025-11", "effective_members_end": 6},
    {"month": "2025-12", "effective_members_end": 7},
    {"month": "2026-01", "effective_members_end": 7},
    {"month": "2026-02", "effective_members_end": 7},
    {"month": "2026-03", "effective_members_end": 7},
    {"month": "2026-04", "effective_members_end": 7},
    {"month": "2026-05", "effective_members_end": 7},
    {"month": "2026-06", "effective_members_end": 7},
    {"month": "2026-07", "effective_members_end": 7},
    {"month": "2026-08", "effective_members_end": 8},
    {"month": "2026-09", "effective_members_end": 7},
    {"month": "2026-10", "effective_members_end": 7},
]
# 手算过程（期末有效会员，排除测试账号与软删除）：
# 2025-11-30：云帆/东湖/青梧/白鹭/云杉/南风 = 6（临江 12-01 才入会）
# 2025-12~2026-07：+ 临江，青梧(8-31 止)、白鹭(9-14 止)、南风(10-05 止)仍在 = 7
# 2026-08-31：+ 汀兰(08-05 入) = 8
# 2026-09-30：青梧(08-31 止)、白鹭(09-14 止)退出，+ 榕城(09-15 入) = 7
# 2026-10-31：南风(10-05 止)退出，+ 南屿(10-02 入) = 7


@pytest.fixture()
def overview_api(client, seed_demo_site):
    headers = seed_demo_site["headers"]
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": PERIOD},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


def _sql_effective(db, day: str) -> int:
    """独立实现：raw SQL 复算某日有效会员企业数（排除测试账号与软删除）。"""
    row = db.execute(
        text(
            """
            select count(distinct c.id)
            from companies c
            join memberships m on m.company_id = c.id
            where c.org_id = 'org-demo' and c.site_id = 'site-east'
              and c.deleted_at is null and c.is_test_account = false
              and m.deleted_at is null and m.status = 'effective'
              and m.start_date <= :day
              and (m.end_date is null or m.end_date >= :day)
            """
        ),
        {"day": day},
    ).scalar()
    return int(row)


def test_envelope_shape(overview_api):
    """统一响应信封：code/message/data/meta。"""
    assert overview_api["code"] == 0
    assert overview_api["message"] == "ok"
    assert overview_api["meta"] == {"cached": False}
    data = overview_api["data"]
    assert data["site_id"] == "site-east"
    assert data["period"] == PERIOD
    assert data["period_start"].startswith("2026-10-01")
    assert data["period_end"].startswith("2026-10-31")


def test_verified_members_end_manual(overview_api):
    """手工核对：认证会员企业数（期末）= 8（已剔除测试账号、软删除、期内已流失）。"""
    assert overview_api["data"]["metrics"]["DASH_MEMBERS_VERIFIED_END"]["value"] == 8


def test_effective_members_end_manual(overview_api):
    """手工核对：有效会员企业数（期末）= 7。"""
    assert overview_api["data"]["metrics"]["DASH_MEMBERS_EFFECTIVE_END"]["value"] == 7


def test_new_joins_manual(overview_api):
    """手工核对：本期（2026-10）新增入会数 = 1（南屿数字 2026-10-02 入会）。"""
    assert overview_api["data"]["metrics"]["DASH_MEMBERS_NEW_JOINS"]["value"] == 1


def test_churned_manual(overview_api):
    """手工核对：本期（2026-10）流失数 = 1（南风咨询 2026-10-05 流失）。"""
    assert overview_api["data"]["metrics"]["DASH_MEMBERS_CHURNED"]["value"] == 1


def test_lifecycle_distribution_manual(overview_api):
    """手工核对：生命周期 7 状态分布（12 家有效企业全部覆盖，7 个键全返回）。"""
    dist = overview_api["data"]["metrics"]["DASH_LIFECYCLE_DISTRIBUTION"]["value"]
    assert dist == EXPECTED_LIFECYCLE
    assert sum(dist.values()) == 12


def test_tier_distribution_manual(overview_api):
    """手工核对：会员等级分布（期末生效会籍：standard 2 / advanced 3 / premium 2）。"""
    tier = overview_api["data"]["metrics"]["DASH_TIER_DISTRIBUTION"]["value"]
    assert tier == EXPECTED_TIER


def test_trend_12m_manual(overview_api):
    """手工核对：近 12 个月期末有效会员数趋势。"""
    trend = overview_api["data"]["metrics"]["DASH_TREND_EFFECTIVE_12M"]["value"]
    assert trend == EXPECTED_TREND


def test_mom_manual(overview_api):
    """手工核对：环比 = 本期（2026-10）7 vs 上月（2026-09）7，delta=0，change_bp=0。"""
    mom = overview_api["data"]["metrics"]["DASH_MEMBERS_MOM"]["value"]
    assert mom == {"current": 7, "previous": 7, "delta": 0, "change_bp": 0}


def test_yoy_manual(overview_api):
    """手工核对：同比 = 本期 7 vs 去年同月（2025-10）6，delta=1，change_bp=1667。"""
    yoy = overview_api["data"]["metrics"]["DASH_MEMBERS_YOY"]["value"]
    assert yoy == {"current": 7, "previous": 6, "delta": 1, "change_bp": 1667}


def test_sql_cross_check_matches_api(client, seed_demo_site, test_tx, overview_api):
    """独立 raw SQL 复算与接口一致（2026-10 与 2026-09 两个期末）。"""
    assert _sql_effective(test_tx, "2026-10-31") == 7
    assert _sql_effective(test_tx, "2026-09-30") == 7
    assert _sql_effective(test_tx, "2026-08-31") == 8
    assert _sql_effective(test_tx, "2025-10-31") == 6


def test_test_account_and_deleted_excluded(client, seed_demo_site):
    """排除测试账号与软删除：把两家改成普通企业前，指标不含它们；数据集本身已验证。"""
    data = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": PERIOD},
        headers=seed_demo_site["headers"],
    ).json()["data"]
    dist = data["metrics"]["DASH_LIFECYCLE_DISTRIBUTION"]["value"]
    # 14 家企业里 2 家（测试账号 + 软删除）必须被排除：分布合计 = 12
    assert sum(dist.values()) == 12


def test_invalid_period_rejected(client, seed_demo_site):
    """period 非 YYYY-MM → 400，统一信封。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": "2026-13"},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


def test_default_period_is_latest_activity_month(client, seed_demo_site):
    """period 缺省 → 取数据集最近业务月份（site-east 最新入会/流失在 2026-10）。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east"},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["period"] == "2026-10"


def test_cache_second_call_is_cached(client, seed_demo_site):
    """10 分钟缓存：第二次同参请求 meta.cached=true；refresh=1 绕过缓存。"""
    headers = seed_demo_site["headers"]
    params = {"site_id": "site-east", "period": PERIOD}
    first = client.get("/api/dash/members/overview", params=params, headers=headers).json()
    assert first["meta"]["cached"] is False
    second = client.get("/api/dash/members/overview", params=params, headers=headers).json()
    assert second["meta"]["cached"] is True
    assert second["data"] == first["data"]
    refreshed = client.get(
        "/api/dash/members/overview", params={**params, "refresh": "1"}, headers=headers
    ).json()
    assert refreshed["meta"]["cached"] is False
    overview_cache.clear()


def test_empty_site_all_zero_metrics(client, seed_demo_site):
    """空站点（site-west 无任何企业/会籍数据）：全部指标为 0/空分布，生命周期 7 键恒全返回。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-west", "period": PERIOD},
        headers={"X-Org-Id": "org-demo", "X-User-Id": "user-head-west"},
    )
    assert resp.status_code == 200
    m = resp.json()["data"]["metrics"]
    assert m["DASH_MEMBERS_VERIFIED_END"]["value"] == 0
    assert m["DASH_MEMBERS_EFFECTIVE_END"]["value"] == 0
    assert m["DASH_MEMBERS_NEW_JOINS"]["value"] == 0
    assert m["DASH_MEMBERS_CHURNED"]["value"] == 0
    assert m["DASH_LIFECYCLE_DISTRIBUTION"]["value"] == {s: 0 for s in LIFECYCLE_STATUSES}
    assert m["DASH_TIER_DISTRIBUTION"]["value"] == {}
    trend = m["DASH_TREND_EFFECTIVE_12M"]["value"]
    assert len(trend) == 12 and all(p["effective_members_end"] == 0 for p in trend)
    # 上月/去年同期都是 0 → change_bp 无意义，返回 null（不除零）
    assert m["DASH_MEMBERS_MOM"]["value"] == {"current": 0, "previous": 0, "delta": 0, "change_bp": None}
    assert m["DASH_MEMBERS_YOY"]["value"] == {"current": 0, "previous": 0, "delta": 0, "change_bp": None}


@pytest.mark.parametrize("bad", ["abc", "2026-14", "202601", ""])
def test_period_rejects_invalid_formats(client, seed_demo_site, bad):
    """period 非 YYYY-MM（字母、月越界、缺横线、空串）一律 400 统一信封。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": bad},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


def test_cache_disabled_when_ttl_zero(client, seed_demo_site):
    """APP_DASH_CACHE_TTL_SECONDS=0 时缓存禁用：两次同参请求都不算命中。"""
    headers = seed_demo_site["headers"]
    params = {"site_id": "site-east", "period": PERIOD}
    saved_ttl = overview_cache.ttl_seconds
    overview_cache.ttl_seconds = 0
    try:
        first = client.get("/api/dash/members/overview", params=params, headers=headers).json()
        second = client.get("/api/dash/members/overview", params=params, headers=headers).json()
    finally:
        overview_cache.ttl_seconds = saved_ttl
        overview_cache.clear()
    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is False


def test_db_error_returns_envelope_500(pg_engine, seed_demo_site):
    """数据库依赖失败：兜底异常处理返回统一信封 500，不泄露内部错误细节。"""
    from fastapi.testclient import TestClient

    from app import db as app_db
    from app.main import app

    def boom():
        raise RuntimeError("db unavailable (simulated)")

    app.dependency_overrides[app_db.get_db] = boom
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(
                "/api/dash/members/overview",
                params={"site_id": "site-east", "period": PERIOD},
                headers=seed_demo_site["headers"],
            )
    finally:
        app.dependency_overrides.pop(app_db.get_db, None)
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 500
    assert body["data"] is None
    assert body["message"] == "internal server error"
