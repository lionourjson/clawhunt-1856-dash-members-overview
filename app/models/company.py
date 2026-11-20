"""企业（S2-CRM 核心对象，本单只读使用）。

生命周期 7 个状态（口径库 DASH_LIFECYCLE_DISTRIBUTION 定义）：
  lead 线索 / negotiating 洽谈 / joined 入会 / active 活跃 /
  silent 沉默 / churn_warning 流失预警 / churned 已流失
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, new_uuid

LIFECYCLE_STATUSES = (
    "lead",
    "negotiating",
    "joined",
    "active",
    "silent",
    "churn_warning",
    "churned",
)


class Company(AuditMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status in ('lead','negotiating','joined','active','silent','churn_warning','churned')",
            name="ck_companies_lifecycle_status",
        ),
        # 与 alembic 0001 保持一致：驾驶舱查询的复合过滤索引
        Index("ix_companies_dashboard", "org_id", "site_id", "is_test_account", "deleted_at"),
        Index("ix_companies_lifecycle_status", "lifecycle_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="lead")
    # 认证时间：非空且 <= 期末 才计入「认证会员企业数（期末）」
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 流失时间：进入「已流失」的时间点，用于「本期流失数」
    churned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 测试账号不参与任何指标（工单硬性要求）
    is_test_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
