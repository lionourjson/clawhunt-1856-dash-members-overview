"""模型注册：import 以便 Alembic / Base.metadata 发现全部表。"""
from app.models.base import AuditMixin, Base, OrgMixin, TimestampMixin, new_uuid, soft_delete_filter  # noqa: F401
from app.models.company import Company, LIFECYCLE_STATUSES  # noqa: F401
from app.models.membership import MEMBERSHIP_STATUSES, Membership, TIERS  # noqa: F401
from app.models.caliber import MetricCaliber  # noqa: F401
from app.models.user_role import ROLES, UserRole  # noqa: F401
