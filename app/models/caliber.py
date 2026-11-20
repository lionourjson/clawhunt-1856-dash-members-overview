"""口径库：指标编码 -> 指标定义与版本。

平台级参考表：所有租户共用同一套指标口径，行内 org_id/site_id 记为 'platform'，
但列结构与统一约定一致（AuditMixin：id UUID、org_id、site_id、created_at、
created_by、updated_at、deleted_at 软删除）——4 张表全部继承统一基类。
响应里每个指标都带 caliber_code + caliber_version（取自本表）。
"""
import uuid

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, new_uuid


class MetricCaliber(AuditMixin, Base):
    __tablename__ = "metric_calibers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    # 平台级行：org/site 记 'platform'（统一约定要求列存在且非空）
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True,
                                        server_default="platform", default="platform")
    site_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True,
                                         server_default="platform", default="platform")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    # created_at/updated_at/deleted_at/created_by 由 AuditMixin（TimestampMixin）提供
