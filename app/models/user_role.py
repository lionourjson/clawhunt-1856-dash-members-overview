"""用户-站点角色：权限依赖的数据来源。

会长（club_head）每个 site 只有一行：请求的 site_id 没有对应用户行即 403，
从而保证「会长只能取本会的数据」。admin 也按 site 授权（一行一个 site），
跨 site 一律拒绝，不在本单实现平台级超管。
"""
import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, new_uuid

ROLES = ("club_head", "admin")


class UserRole(AuditMixin, Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="club_head")
    # org_id/site_id 继承自 AuditMixin
