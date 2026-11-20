"""配置全部从环境变量读取，不写死任何密钥或路径。见 .env.example。"""
import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


APP_ENV = _get("APP_ENV", "dev")

# 业务库连接串，例如：
# postgresql+psycopg://app_user:app_pass@127.0.0.1:5432/dash_members
DATABASE_URL = _get("APP_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/dash_members")

# 测试库管理连接串（pytest 的 conftest 用它建库/删库），只在测试环境用
DATABASE_ADMIN_URL = _get(
    "APP_DATABASE_ADMIN_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5432/postgres",
)

HOST = _get("APP_HOST", "127.0.0.1")
PORT = int(_get("APP_PORT", "8000"))

# 驾驶舱聚合接口缓存 TTL（秒）。工单要求 10 分钟；0 = 禁用（测试/基准用）
DASH_CACHE_TTL_SECONDS = int(_get("APP_DASH_CACHE_TTL_SECONDS", "600"))
