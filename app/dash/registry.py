"""计算函数注册表：口径编码 -> 计算函数。

新增指标时在这里注册，并把口径定义加进 app/dash/calibers.py（迁移与测试共用）。
"""
from app.dash import metrics
from app.dash.calibers import CALIBER_CODES

CALCULATORS = {
    "DASH_MEMBERS_VERIFIED_END": metrics.verified_members_end,
    "DASH_MEMBERS_EFFECTIVE_END": metrics.effective_members_end,
    "DASH_MEMBERS_NEW_JOINS": metrics.new_joins_in_period,
    "DASH_MEMBERS_CHURNED": metrics.churned_in_period,
    "DASH_LIFECYCLE_DISTRIBUTION": metrics.lifecycle_distribution,
    "DASH_TIER_DISTRIBUTION": metrics.tier_distribution,
    "DASH_TREND_EFFECTIVE_12M": metrics.trend_effective_12m,
    "DASH_MEMBERS_MOM": metrics.mom_effective,
    "DASH_MEMBERS_YOY": metrics.yoy_effective,
}


def get_calculator(code: str):
    """按口径编码取计算函数；未注册的编码直接报错（防止口径与实现脱节）。"""
    fn = CALCULATORS.get(code)
    if fn is None:
        raise KeyError(f"caliber {code} has no registered calculator")
    return fn


# 启动即校验：口径库里的每个编码都必须有注册的计算函数
_missing = [c for c in CALIBER_CODES if c not in CALCULATORS]
if _missing:
    raise RuntimeError(f"calibers missing calculators: {_missing}")
_extra = [c for c in CALCULATORS if c not in CALIBER_CODES]
if _extra:
    raise RuntimeError(f"calculators missing caliber definitions: {_extra}")
