"""口径库定义（单一来源）：alembic 迁移、测试夹具都用这一份种子数据。

每个指标一个编码；所有指标取数都按这里的定义实现（app/dash/metrics.py），
响应里每个指标带 caliber_code + caliber_version。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Caliber:
    code: str
    version: str
    name: str
    definition: str


CALIBER_LIBRARY_VERSION = "v1.0.0"

CALIBERS: tuple[Caliber, ...] = (
    Caliber(
        code="DASH_MEMBERS_VERIFIED_END",
        version="v1.0.0",
        name="认证会员企业数（期末）",
        definition="期末时点已认证且未流失的会员企业数：verified_at <= 期末，且 churned_at 为空或 > 期末；"
        "排除测试账号（is_test_account=true）与软删除（deleted_at 非空）数据。",
    ),
    Caliber(
        code="DASH_MEMBERS_EFFECTIVE_END",
        version="v1.0.0",
        name="有效会员企业数（期末，会籍生效中）",
        definition="期末时点存在生效会籍的企业数（按企业去重）：会籍 start_date <= 期末日，"
        "且 end_date 为空或 >= 期末日，status='effective'；排除测试账号与软删除数据。",
    ),
    Caliber(
        code="DASH_MEMBERS_NEW_JOINS",
        version="v1.0.0",
        name="本期新增入会数",
        definition="入会时间 joined_at 落在 [期初, 期末] 的企业数（按企业去重）；排除测试账号与软删除数据。",
    ),
    Caliber(
        code="DASH_MEMBERS_CHURNED",
        version="v1.0.0",
        name="本期流失数",
        definition="流失时间 churned_at 落在 [期初, 期末] 的企业数（按企业去重）；排除测试账号与软删除数据。",
    ),
    Caliber(
        code="DASH_LIFECYCLE_DISTRIBUTION",
        version="v1.0.0",
        name="生命周期 7 状态企业数分布",
        definition="期末时点按 lifecycle_status 统计的企业数分布，7 个状态（lead 线索 / negotiating 洽谈 / "
        "joined 入会 / active 活跃 / silent 沉默 / churn_warning 流失预警 / churned 已流失）全部返回，"
        "无数据的状态计 0；排除测试账号与软删除数据。",
    ),
    Caliber(
        code="DASH_TIER_DISTRIBUTION",
        version="v1.0.0",
        name="会员等级分布",
        definition="期末时点有效会员企业按其生效会籍等级（standard/advanced/premium）分布；"
        "同一企业取 joined_at 最晚的一条生效会籍；排除测试账号与软删除数据。",
    ),
    Caliber(
        code="DASH_TREND_EFFECTIVE_12M",
        version="v1.0.0",
        name="近 12 个月期末有效会员数趋势",
        definition="以本期所在月为最后一月，往前共 12 个月，每月按 DASH_MEMBERS_EFFECTIVE_END 口径"
        "计算该月末（当月最后一天 23:59:59 UTC）的有效会员企业数。",
    ),
    Caliber(
        code="DASH_MEMBERS_MOM",
        version="v1.0.0",
        name="有效会员企业数环比",
        definition="本期期末有效会员企业数 vs 上月期末：delta=本期-上月；change_bp=round(delta/上月*10000)"
        "（万分比整数，上月为 0 时为 null）。",
    ),
    Caliber(
        code="DASH_MEMBERS_YOY",
        version="v1.0.0",
        name="有效会员企业数同比",
        definition="本期期末有效会员企业数 vs 去年同月期末：delta=本期-去年同期；change_bp=round(delta/去年同期*10000)"
        "（万分比整数，去年同期为 0 或无数据时为 null）。",
    ),
)

CALIBER_BY_CODE: dict[str, Caliber] = {c.code: c for c in CALIBERS}
CALIBER_CODES: tuple[str, ...] = tuple(c.code for c in CALIBERS)
