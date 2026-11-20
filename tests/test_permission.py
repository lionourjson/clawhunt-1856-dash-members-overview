"""验收 2：The head of the club can only obtain the club data (test)。

会长（club_head）只有自己站点的授权行：请求别的 site 一律 403，
且响应体不携带任何其他站点数据（统一信封，data=null）。
"""
import pytest


def test_club_head_can_read_own_site(client, seed_demo_site):
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": "2026-10"},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["site_id"] == "site-east"


def test_club_head_cannot_read_other_site(client, seed_demo_site):
    """会长 A（site-east）请求 site-west → 403，data 为空。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-west", "period": "2026-10"},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 403
    assert body["data"] is None
    assert "site-west" in body["message"]


def test_club_head_cannot_read_other_org_site(client, seed_demo_site):
    """跨组织（org-other 的 site-north）同样 403。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-north", "period": "2026-10"},
        headers=seed_demo_site["headers"],
    )
    assert resp.status_code == 403


def test_org_mismatch_rejected(client, seed_demo_site):
    """X-Org-Id 与授权行不一致 → 403。"""
    headers = {"X-Org-Id": "org-other", "X-User-Id": "user-head-east"}
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": "2026-10"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_unknown_user_rejected(client, seed_demo_site):
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-east", "period": "2026-10"},
        headers={"X-Org-Id": "org-demo", "X-User-Id": "user-nobody"},
    )
    assert resp.status_code == 403


def test_missing_headers_rejected(client, seed_demo_site):
    resp = client.get("/api/dash/members/overview", params={"site_id": "site-east"})
    assert resp.status_code == 422
    assert resp.json()["code"] == 422


def test_missing_site_id_rejected(client, seed_demo_site):
    resp = client.get("/api/dash/members/overview", headers=seed_demo_site["headers"])
    assert resp.status_code == 422


def test_admin_can_read_authorized_sites(client, seed_demo_site):
    """admin 用户在 site-east / site-west 各有一行授权，两个站点都能读。"""
    headers = {"X-Org-Id": "org-demo", "X-User-Id": "user-admin-demo"}
    for site in ("site-east", "site-west"):
        resp = client.get(
            "/api/dash/members/overview",
            params={"site_id": site, "period": "2026-10"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["site_id"] == site


def test_role_name_alone_grants_nothing(client, seed_demo_site):
    """user-admin-demo 没有 site-north 的授权行 → 403（权限完全由授权行决定）。"""
    resp = client.get(
        "/api/dash/members/overview",
        params={"site_id": "site-north", "period": "2026-10"},
        headers={"X-Org-Id": "org-demo", "X-User-Id": "user-admin-demo"},
    )
    assert resp.status_code == 403
