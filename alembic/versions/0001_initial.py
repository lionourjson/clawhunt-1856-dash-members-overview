"""初始迁移：驾驶舱聚合接口数据表 + 口径库种子数据。

Revision ID: 0001
Revises:
Create Date: 2026-11-19

表：
- companies        企业（S2-CRM 只读对象桩，含生命周期/认证/流失时间）
- memberships      会籍
- metric_calibers  口径库（平台级，种子来自 app.dash.calibers.CALIBERS）
- user_roles       用户-站点授权（会长只能取本会数据）
"""
import uuid

import sqlalchemy as sa
from alembic import op

from app.dash.calibers import CALIBERS

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("churned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_test_account", sa.Boolean(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status in ('lead','negotiating','joined','active','silent','churn_warning','churned')",
            name="ck_companies_lifecycle_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companies_org_id"), "companies", ["org_id"])
    op.create_index(op.f("ix_companies_site_id"), "companies", ["site_id"])
    op.create_index("ix_companies_dashboard", "companies", ["org_id", "site_id", "is_test_account", "deleted_at"])
    op.create_index("ix_companies_lifecycle_status", "companies", ["lifecycle_status"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint("status in ('effective','expired','cancelled')", name="ck_memberships_status"),
        sa.CheckConstraint("tier in ('standard','advanced','premium')", name="ck_memberships_tier"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"])
    op.create_index(op.f("ix_memberships_site_id"), "memberships", ["site_id"])
    op.create_index(op.f("ix_memberships_company_id"), "memberships", ["company_id"])
    op.create_index("ix_memberships_dashboard", "memberships", ["org_id", "site_id", "status", "start_date", "end_date"])
    op.create_index("ix_memberships_joined_at", "memberships", ["joined_at"])

    op.create_table(
        "metric_calibers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_metric_calibers_code"),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"])
    op.create_index(op.f("ix_user_roles_org_id"), "user_roles", ["org_id"])
    op.create_index(op.f("ix_user_roles_site_id"), "user_roles", ["site_id"])

    # 口径库种子（单一来源：app.dash.calibers）
    op.bulk_insert(
        sa.table(
            "metric_calibers",
            sa.column("id", sa.Uuid),
            sa.column("code", sa.String),
            sa.column("version", sa.String),
            sa.column("name", sa.String),
            sa.column("definition", sa.Text),
        ),
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"caliber:{c.code}"),
                "code": c.code,
                "version": c.version,
                "name": c.name,
                "definition": c.definition,
            }
            for c in CALIBERS
        ],
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("metric_calibers")
    op.drop_index("ix_memberships_joined_at", table_name="memberships")
    op.drop_index("ix_memberships_dashboard", table_name="memberships")
    op.drop_index(op.f("ix_memberships_company_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_site_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_org_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_companies_lifecycle_status", table_name="companies")
    op.drop_index("ix_companies_dashboard", table_name="companies")
    op.drop_index(op.f("ix_companies_site_id"), table_name="companies")
    op.drop_index(op.f("ix_companies_org_id"), table_name="companies")
    op.drop_table("companies")
