"""0002：metric_calibers 补统一基类字段（org_id/site_id/created_at/created_by/deleted_at）。

工单统一技术约定要求业务表统一含 id(UUID)、org_id、site_id、created_at、created_by、
updated_at、deleted_at（软删除）。0001 时口径库表按平台级参考表设计、缺 org/site 等
列；本迁移补齐（updated_at 已有），存量 9 行 org/site 记 'platform'。
Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("metric_calibers", sa.Column("org_id", sa.String(length=64), nullable=False, server_default="platform"))
    op.add_column("metric_calibers", sa.Column("site_id", sa.String(length=64), nullable=False, server_default="platform"))
    op.add_column("metric_calibers", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("metric_calibers", sa.Column("created_by", sa.String(length=64), nullable=True))
    op.add_column("metric_calibers", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_metric_calibers_org_id"), "metric_calibers", ["org_id"])
    op.create_index(op.f("ix_metric_calibers_site_id"), "metric_calibers", ["site_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_metric_calibers_site_id"), table_name="metric_calibers")
    op.drop_index(op.f("ix_metric_calibers_org_id"), table_name="metric_calibers")
    op.drop_column("metric_calibers", "deleted_at")
    op.drop_column("metric_calibers", "created_by")
    op.drop_column("metric_calibers", "created_at")
    op.drop_column("metric_calibers", "site_id")
    op.drop_column("metric_calibers", "org_id")
