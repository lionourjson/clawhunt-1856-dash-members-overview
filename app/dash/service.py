"""聚合服务：组装 overview 响应（口径版本来自 metric_calibers 表）+ 10 分钟缓存。

period 语义：YYYY-MM；期末=当月最后一天 23:59:59 UTC（指标比较用
[期初, 次月 1 日 00:00:00) 左闭右开窗口，见 metrics._end_exclusive）。
period 缺省时取数据集里最近的业务月份（会员入会/认证/流失的最大月份）；
站点没有任何业务数据时取当前月份（新会所空数据首屏返回全 0 而不是报错）。
"""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dash import metrics
from app.dash.calibers import CALIBER_CODES, CALIBER_LIBRARY_VERSION
from app.dash.cache import overview_cache
from app.dash.registry import get_calculator
from app.models.caliber import MetricCaliber
from app.models.company import Company
from app.models.membership import Membership

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# 年份下界：趋势要往前回退 11 个月，year<13 会撞 datetime 下限（year 0）→ 500；
# 客户端输入一律按 InvalidPeriod → 400 拒绝。
MIN_YEAR = 1970


class InvalidPeriod(ValueError):
    pass


def parse_period(period: str | None, db: Session, org_id: str, site_id: str) -> str:
    """校验/推断 period，返回 YYYY-MM。"""
    if period is not None:
        if not _PERIOD_RE.match(period):
            raise InvalidPeriod(f"period must be YYYY-MM, got {period!r}")
        if int(period[:4]) < MIN_YEAR:
            raise InvalidPeriod(f"period year must be >= {MIN_YEAR}, got {period!r}")
        return period
    # 缺省：数据集最近业务月份（入会/认证/流失的最大时间；不含记录创建时间）
    floor = datetime.min.replace(tzinfo=timezone.utc)
    candidates = [
        db.scalar(
            select(func.max(Membership.joined_at)).where(
                Membership.org_id == org_id,
                Membership.site_id == site_id,
                Membership.deleted_at.is_(None),
            )
        )
        or floor,
        db.scalar(
            select(func.max(Company.verified_at)).where(
                Company.org_id == org_id,
                Company.site_id == site_id,
                Company.deleted_at.is_(None),
                Company.is_test_account.is_(False),
                Company.verified_at.isnot(None),
            )
        )
        or floor,
        db.scalar(
            select(func.max(Company.churned_at)).where(
                Company.org_id == org_id,
                Company.site_id == site_id,
                Company.deleted_at.is_(None),
                Company.is_test_account.is_(False),
                Company.churned_at.isnot(None),
            )
        )
        or floor,
    ]
    latest = max(candidates)
    if latest == floor:
        # 站点无任何业务数据（新会所首屏）：取当前月份，返回全 0 指标而非报错
        latest = datetime.now(timezone.utc)
    return f"{latest.year:04d}-{latest.month:02d}"


def load_caliber_versions(db: Session) -> dict[str, str]:
    """从口径库表读 code -> version（响应里每个指标带的口径版本；排除软删行）。"""
    rows = db.execute(
        select(MetricCaliber.code, MetricCaliber.version).where(MetricCaliber.deleted_at.is_(None))
    ).all()
    versions = {code: version for code, version in rows}
    missing = [c for c in CALIBER_CODES if c not in versions]
    if missing:
        raise RuntimeError(f"metric_calibers missing rows for: {missing}")
    return versions


def build_overview_data(db: Session, org_id: str, site_id: str, period: str) -> dict:
    """计算全部指标并组装 data 段（不读缓存，纯计算）。"""
    year, month = int(period[:4]), int(period[5:7])
    period_start, period_end = metrics.month_bounds(year, month)
    versions = load_caliber_versions(db)

    metrics_payload: dict[str, dict] = {}
    for code in CALIBER_CODES:
        fn = get_calculator(code)
        metrics_payload[code] = {
            "value": fn(db, org_id, site_id, period_start, period_end),
            "caliber_code": code,
            "caliber_version": versions[code],
        }

    data = {
        "site_id": site_id,
        "period": period,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "caliber_library_version": CALIBER_LIBRARY_VERSION,
        "metrics": metrics_payload,
    }
    return data


def get_overview(db: Session, org_id: str, site_id: str, period: str | None, refresh: bool = False) -> tuple[dict, bool]:
    """带缓存的入口，返回 (data, cached)。refresh=True 时绕过缓存重算。"""
    resolved = parse_period(period, db, org_id, site_id)
    key = (org_id, site_id, resolved)
    if not refresh:
        cached = overview_cache.get(key)
        if cached is not None:
            return cached, True
    data = build_overview_data(db, org_id, site_id, resolved)
    overview_cache.put(key, data)
    return data, False
