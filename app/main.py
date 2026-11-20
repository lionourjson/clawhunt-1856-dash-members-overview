"""会员规模与状态分布驾驶舱聚合接口（#1856 S3-DASH-005）。

GET /api/dash/members/overview?site_id=&period=&refresh=
- 权限：X-Org-Id + X-User-Id 请求头 + user_roles 表授权；用户在请求的 site_id
  没有授权行即 403（会长只能取本会数据）。org_id 从 X-Org-Id 头读，不在 URL 传。
- 响应统一信封：{"code", "message", "data", "meta"}；每个指标带 caliber_code +
  caliber_version（口径库 metric_calibers 表）。
- 缓存：进程内 TTL 缓存，默认 600 秒（APP_DASH_CACHE_TTL_SECONDS 可配，0 禁用），
  ?refresh=1 绕过缓存重算。
"""
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dash.service import InvalidPeriod, get_overview
from app.db import get_db
from app.models.user_role import UserRole

app = FastAPI(title="会员空间平台 · 驾驶舱聚合接口（FastAPI+SQLAlchemy2+PostgreSQL16）")


def _envelope(code: int, message: str, data=None, **meta) -> dict:
    body = {"code": code, "message": message, "data": data}
    if meta:
        body["meta"] = meta
    return body


@app.exception_handler(HTTPException)
async def http_exception_envelope(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_envelope(exc.status_code, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_envelope(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content=_envelope(422, "validation error: " + str(exc.errors()[:3])))


@app.exception_handler(InvalidPeriod)
async def invalid_period_envelope(request: Request, exc: InvalidPeriod) -> JSONResponse:
    return JSONResponse(status_code=400, content=_envelope(400, str(exc)))


@app.exception_handler(Exception)
async def unhandled_exception_envelope(request: Request, exc: Exception) -> JSONResponse:
    """兜底：任何未处理异常（如数据库不可用）也走统一信封，不泄露内部错误细节。"""
    return JSONResponse(status_code=500, content=_envelope(500, "internal server error"))


def require_site_access(
    x_org_id: str = Header(..., min_length=1, max_length=64),
    x_user_id: str = Header(..., min_length=1, max_length=64),
    site_id: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> str:
    """权限依赖：用户必须在该 org + site 上有授权行（user_roles），否则 403。

    会长（club_head）每个站点只有自己的一行授权，因此只能取到本会数据。
    """
    row = db.scalar(
        select(UserRole).where(
            UserRole.user_id == x_user_id,
            UserRole.org_id == x_org_id,
            UserRole.site_id == site_id,
            UserRole.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=403, detail=f"user {x_user_id} has no access to site {site_id}")
    return site_id


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/dash/members/overview")
def members_overview(
    refresh: bool = Query(False, description="绕过缓存重算"),
    period: str | None = Query(None, description="统计月份 YYYY-MM，缺省取数据集最近业务月份"),
    x_org_id: str = Header(..., min_length=1, max_length=64),
    site_id: str = Depends(require_site_access),
    db: Session = Depends(get_db),
) -> dict:
    """会员规模与状态分布驾驶舱聚合接口（口径版本随每个指标返回）。"""
    data, cached = get_overview(db, org_id=x_org_id, site_id=site_id, period=period, refresh=refresh)
    return _envelope(0, "ok", data, cached=cached)
