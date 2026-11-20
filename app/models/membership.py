"""会籍（S2-CRM 核心对象，本单只读使用）。"""
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, new_uuid

TIERS = ("standard", "advanced", "premium")
MEMBERSHIP_STATUSES = ("effective", "expired", "cancelled")


class Membership(AuditMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("status in ('effective','expired','cancelled')", name="ck_memberships_status"),
        CheckConstraint("tier in ('standard','advanced','premium')", name="ck_memberships_tier"),
        # 与 alembic 0001 保持一致：驾驶舱查询的复合过滤索引
        Index("ix_memberships_dashboard", "org_id", "site_id", "status", "start_date", "end_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    # effective=生效中（end_date 为空或 >= 期末即视为期末仍生效）
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="effective")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    # end_date 为空表示长期有效
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 入会时间：落在 [期初, 期末] 即计「本期新增入会数」
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
