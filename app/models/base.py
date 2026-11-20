"""统一基类：多租户字段 + 时间戳 + 软删除。

所有业务表继承 Base。约定：
- id 用 UUID（数据库端 uuid_v4 生成）；
- org_id / site_id 做多租户隔离，查询必须带 org_id 过滤；
- created_by 记创建人（幂等信息，测试用 fake-user-1 之类虚构值）；
- deleted_at 非空即视为已删除（软删除），业务查询统一用 ``app.models.base.soft_delete_filter``。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrgMixin:
    """多租户字段。"""

    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class TimestampMixin:
    """时间戳 + 软删除字段。金额字段不放这里，见 models/item.py 的示例。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditMixin(OrgMixin, TimestampMixin):
    pass


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def soft_delete_filter(model):
    """软删除过滤条件：model.deleted_at IS NULL。所有业务查询都要带上。

    注意传具体模型类（如 Company / Membership），不要传 mixin ——
    mixin 上的 Column 没有绑定表名，编译会报 "Cannot compile Column object"。
    """
    return model.deleted_at.is_(None)


# 时间戳统一存 UTC
def utcnow() -> datetime:
    return datetime.now(timezone.utc)
