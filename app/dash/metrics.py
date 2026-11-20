"""指标计算函数（纯函数，按口径库编码一一对应）。

签名统一为 fn(db, org_id, site_id, period_start, period_end) -> 值。
period_start/period_end 为该期的起止时间（UTC，期末=当月最后一天 23:59:59）。
所有查询统一排除：软删除（deleted_at 非空）、测试账号（is_test_account=true）、
且只取本 org_id + site_id 的数据（多租户隔离）。
"""
import calendar
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import soft_delete_filter
from app.models.company import LIFECYCLE_STATUSES, Company
from app.models.membership import Membership

# 口径编码 -> 计算函数（见 app/dash/registry.py）


def _company_cond(org_id: str, site_id: str):
    """企业表的公共过滤条件：租户隔离 + 软删除 + 排除测试账号。"""
    return (
        Company.org_id == org_id,
        Company.site_id == site_id,
        soft_delete_filter(Company),
        Company.is_test_account.is_(False),
    )


def _effective_membership_cond(period_end: datetime):
    """会籍生效中（期末口径）：start_date <= 期末日 且 (end_date 为空 或 >= 期末日)。"""
    end_day = period_end.date()
    return (
        Membership.status == "effective",
        Membership.start_date <= end_day,
        (Membership.end_date.is_(None)) | (Membership.end_date >= end_day),
    )


def verified_members_end(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> int:
    """DASH_MEMBERS_VERIFIED_END：认证会员企业数（期末）。"""
    cond = _company_cond(org_id, site_id) + (
        Company.verified_at.isnot(None),
        Company.verified_at <= period_end,
        (Company.churned_at.is_(None)) | (Company.churned_at > period_end),
    )
    return int(db.scalar(select(func.count()).select_from(Company).where(*cond)) or 0)


def effective_members_end(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> int:
    """DASH_MEMBERS_EFFECTIVE_END：有效会员企业数（期末，会籍生效中），按企业去重。"""
    cond = _company_cond(org_id, site_id) + (
        Membership.org_id == org_id,
        Membership.site_id == site_id,
        soft_delete_filter(Company),
        *_effective_membership_cond(period_end),
    )
    return int(
        db.scalar(
            select(func.count(func.distinct(Company.id)))
            .select_from(Company)
            .join(Membership, Membership.company_id == Company.id)
            .where(*cond)
        )
        or 0
    )


def new_joins_in_period(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> int:
    """DASH_MEMBERS_NEW_JOINS：本期新增入会数（joined_at 落在期内，按企业去重）。

    按口径定义只看 joined_at 是否落在 [期初, 期末]，不限定会籍当前状态
    （期内入会后又流失的企业也计入新增）。
    """
    cond = _company_cond(org_id, site_id) + (
        Membership.org_id == org_id,
        Membership.site_id == site_id,
        soft_delete_filter(Company),
        Membership.joined_at >= period_start,
        Membership.joined_at <= period_end,
    )
    return int(
        db.scalar(
            select(func.count(func.distinct(Company.id)))
            .select_from(Company)
            .join(Membership, Membership.company_id == Company.id)
            .where(*cond)
        )
        or 0
    )


def churned_in_period(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> int:
    """DASH_MEMBERS_CHURNED：本期流失数（churned_at 落在期内）。"""
    cond = _company_cond(org_id, site_id) + (
        Company.churned_at.isnot(None),
        Company.churned_at >= period_start,
        Company.churned_at <= period_end,
    )
    return int(db.scalar(select(func.count()).select_from(Company).where(*cond)) or 0)


def lifecycle_distribution(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> dict[str, int]:
    """DASH_LIFECYCLE_DISTRIBUTION：生命周期 7 状态分布（期末快照，无数据的状态计 0）。"""
    rows = db.execute(
        select(Company.lifecycle_status, func.count())
        .where(*_company_cond(org_id, site_id))
        .group_by(Company.lifecycle_status)
    ).all()
    dist = {status: 0 for status in LIFECYCLE_STATUSES}
    for status, count in rows:
        dist[status] = int(count)
    return dist


def tier_distribution(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> dict[str, int]:
    """DASH_TIER_DISTRIBUTION：会员等级分布（同一企业取 joined_at 最晚的生效会籍）。"""
    rn = (
        func.row_number()
        .over(partition_by=Membership.company_id, order_by=Membership.joined_at.desc())
        .label("rn")
    )
    latest = (
        select(Membership.tier.label("tier"), rn)
        .join(Company, Company.id == Membership.company_id)
        .where(
            *_company_cond(org_id, site_id),
            Membership.org_id == org_id,
            Membership.site_id == site_id,
            soft_delete_filter(Membership),
            *_effective_membership_cond(period_end),
        )
        .subquery()
    )
    rows = db.execute(
        select(latest.c.tier, func.count()).select_from(latest).where(latest.c.rn == 1).group_by(latest.c.tier)
    ).all()
    return {tier: int(count) for tier, count in rows}


def effective_members_end_for_month(db: Session, org_id: str, site_id: str, year: int, month: int) -> int:
    """某个月月末口径的有效会员企业数（供趋势/环比/同比复用）。"""
    period_start, period_end = month_bounds(year, month)
    return effective_members_end(db, org_id, site_id, period_start, period_end)


def trend_effective_12m(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> list[dict]:
    """DASH_TREND_EFFECTIVE_12M：以本期为最后一月，往前共 12 个月的期末有效会员数。"""
    points: list[dict] = []
    year, month = period_end.year, period_end.month
    months: list[tuple[int, int]] = []
    for _ in range(12):
        months.append((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    for y, m in reversed(months):
        points.append(
            {
                "month": f"{y:04d}-{m:02d}",
                "effective_members_end": effective_members_end_for_month(db, org_id, site_id, y, m),
            }
        )
    return points


def _change(current: int, previous: int | None) -> dict:
    delta = None if previous is None else current - previous
    change_bp = None
    if previous not in (None, 0) and delta is not None:
        change_bp = round(delta / previous * 10000)
    return {"current": current, "previous": previous, "delta": delta, "change_bp": change_bp}


def mom_effective(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> dict:
    """DASH_MEMBERS_MOM：环比（vs 上月期末）。"""
    current = effective_members_end_for_month(db, org_id, site_id, period_end.year, period_end.month)
    py, pm = (period_end.year, period_end.month - 1) if period_end.month > 1 else (period_end.year - 1, 12)
    previous = effective_members_end_for_month(db, org_id, site_id, py, pm)
    return _change(current, previous)


def yoy_effective(db: Session, org_id: str, site_id: str, period_start: datetime, period_end: datetime) -> dict:
    """DASH_MEMBERS_YOY：同比（vs 去年同月期末）。"""
    current = effective_members_end_for_month(db, org_id, site_id, period_end.year, period_end.month)
    previous = effective_members_end_for_month(db, org_id, site_id, period_end.year - 1, period_end.month)
    return _change(current, previous)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """某月的 [期初, 期末]（UTC）：期末=当月最后一天 23:59:59。"""
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end
