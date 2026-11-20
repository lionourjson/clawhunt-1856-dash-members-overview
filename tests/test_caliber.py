"""验收 3：Each indicator in the response has a calibrated version (test)。

- 响应里 9 个指标全部带 caliber_code + caliber_version；
- 口径版本与 metric_calibers 表一致；
- 注册表与口径库一一对应（防止口径与实现脱节）。
"""
from sqlalchemy import select

from app.dash.calibers import CALIBER_CODES, CALIBER_LIBRARY_VERSION
from app.dash.registry import CALCULATORS
from app.models import MetricCaliber

PERIOD = "2026-10"


def test_all_nine_metrics_present(client, seed_demo_site):
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": PERIOD},
        headers=seed_demo_site["headers"],
    )
    metrics = resp.json()["data"]["metrics"]
    assert set(metrics.keys()) == set(CALIBER_CODES)
    assert len(metrics) == 9


def test_every_metric_has_caliber_version(client, seed_demo_site, test_tx):
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": PERIOD},
        headers=seed_demo_site["headers"],
    )
    metrics = resp.json()["data"]["metrics"]
    db_versions = dict(
        test_tx.execute(select(MetricCaliber.code, MetricCaliber.version)).all()
    )
    for code, payload in metrics.items():
        assert payload["caliber_code"] == code
        assert payload["caliber_version"] == db_versions[code]
        assert payload["caliber_version"].startswith("v")


def test_caliber_library_version_in_response(client, seed_demo_site):
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": PERIOD},
        headers=seed_demo_site["headers"],
    )
    assert resp.json()["data"]["caliber_library_version"] == CALIBER_LIBRARY_VERSION


def test_registry_matches_caliber_library():
    """计算函数注册表与口径库编码一一对应（模块导入即校验，这里显式再断言）。"""
    assert set(CALCULATORS.keys()) == set(CALIBER_CODES)


def test_caliber_definitions_persisted(test_tx):
    """口径库表里 9 条定义，definition 非空（口径库编码取数的落库证据）。"""
    rows = test_tx.execute(select(MetricCaliber)).scalars().all()
    assert len(rows) == 9
    for row in rows:
        assert row.code in CALIBER_CODES
        assert len(row.definition) > 20
