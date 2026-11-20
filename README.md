# #1856【S3-DASH-005】会员规模与状态分布驾驶舱聚合接口（FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16）

实现 `GET /api/dash/members/overview?site_id=&period=`：认证会员企业数（期末）、有效会员企业数（会籍生效中）、本期新增入会数、本期流失数、生命周期 7 状态分布、会员等级分布、近 12 个月期末有效会员数趋势、环比与同比。所有指标按口径库编码取数、响应带口径版本，排除测试账号与软删除数据，统一响应信封 + 权限依赖 + 10 分钟缓存。

> 本仓库所有数据均为虚构（企业名、用户 ID、站点 ID 皆为自拟测试值），不出现任何真实企业或个人信息。配置全部从环境变量读取（见 `.env.example`）。依赖 S2-CRM 的企业/会籍/生命周期数据，本单按工单允许先落自有只读表（`companies` / `memberships`），真实接入时把这两个表替换为 S2-CRM 的只读数据源即可，对接点见下文「依赖与集成点」。

## 验收标准逐条对照（原文逐字引用）

### 验收 1：虚构数据集上各指标与手工计算一致（测试）

（工单 zh-CN 原文；预做包构建时平台返回英文版 "Each indicator on the fictional data set is consistent with manual calculation (test)"，语义相同。）

- **实现**：`tests/test_overview_calc.py`，22 条用例。夹具 `seed_demo_site`（`tests/conftest.py`）固定虚构站点 org-demo/site-east：14 家企业（12 家有效 + 1 家测试账号 + 1 家软删除）、12 条会籍，覆盖 2025-01 ~ 2026-10。
- **手工计算**（逐企业推算，2026-10 期末 = 2026-10-31T23:59:59 UTC）：
  - 认证会员企业数（期末）= 8（云帆智造/东湖新材料/南屿数字/临江生物/青梧设计/云杉检测/汀兰文化/榕城会展；白鹭物流 2026-09-14 流失、南风咨询 2026-10-05 流失不计入）
  - 有效会员企业数（期末）= 7（南风咨询会籍 2026-10-05 止、白鹭物流 2026-09-14 止不计入）
  - 本期新增入会数 = 1（南屿数字 2026-10-02 入会）
  - 本期流失数 = 1（南风咨询 2026-10-05 流失）
  - 生命周期分布 = lead 1 / negotiating 1 / joined 1 / active 5 / silent 1 / churn_warning 1 / churned 2（合计 12，测试账号与软删除企业已被排除）
  - 等级分布 = standard 2 / advanced 3 / premium 2
  - 12 个月趋势 = 2025-11:6 → 2026-07:7 → 2026-08:8（汀兰文化 08-05 入会）→ 2026-09:7（青梧 08-31 止、白鹭 09-14 止退出，榕城 09-15 入会）→ 2026-10:7（南风 10-05 止退出，南屿 10-02 入会）
  - 环比 = 本期 7 vs 上月 7 → delta 0、change_bp 0；同比 = 本期 7 vs 去年同月 6 → delta 1、change_bp 1667
- **证据**：接口返回值与上述手算逐项相等（`test_verified_members_end_manual`、`test_effective_members_end_manual`、`test_new_joins_manual`、`test_churned_manual`、`test_lifecycle_distribution_manual`、`test_tier_distribution_manual`、`test_trend_12m_manual`、`test_mom_manual`、`test_yoy_manual`）。另有独立 raw SQL 复算（`test_sql_cross_check_matches_api`，与 `app/dash/metrics.py` 不同的实现路径）：2026-10-31=7、2026-09-30=7、2026-08-31=8、2025-10-31=6，全部一致。

### 验收 2：会所负责人只能取到本会所数据（测试）

（工单 zh-CN 原文；预做包构建时平台返回英文版 "The head of the club can only obtain the club data (test)"，语义相同。）

- **实现**：权限依赖 `require_site_access`（`app/main.py:52`）：请求头 `X-Org-Id` + `X-User-Id` + 查询参数 `site_id` 必须在 `user_roles` 表里有对应授权行，否则 403。会长（club_head）每个站点只有自己一行授权，因此只能取本会数据。错误响应是统一信封 `{"code":403, "message":..., "data":null}`，不泄露任何其他站点数据。
- **证据**：`tests/test_permission.py` 9 条用例全过：本站 200（`test_club_head_can_read_own_site`）；跨站点 403（`test_club_head_cannot_read_other_site`）；跨组织 403（`test_club_head_cannot_read_other_org_site`）；org 不匹配 403（`test_org_mismatch_rejected`）；未知用户 403（`test_unknown_user_rejected`）；缺头 422（`test_missing_headers_rejected`）；缺 site_id 422（`test_missing_site_id_rejected`）；admin 多站授权可读（`test_admin_can_read_authorized_sites`）；只给角色名不给授权行不给权限（`test_role_name_alone_grants_nothing`）。

### 验收 3：响应中每个指标都带口径版本（测试）

（工单 zh-CN 原文；预做包构建时平台返回英文版 "Each indicator in the response has a calibrated version (test)"，语义相同。）

- **实现**：口径库表 `metric_calibers`（`app/models/caliber.py`，迁移 0001 落库 9 条，种子单一来源 `app/dash/calibers.py`）；计算函数按编码注册（`app/dash/registry.py`，模块导入即校验口径库与注册表一一对应）；响应 data 里 `caliber_library_version` + 每个指标 `{"value":..., "caliber_code":..., "caliber_version":...}`。
- **证据**：`tests/test_caliber.py` 5 条用例全过：9 个指标全在（`test_all_nine_metrics_present`）；每个指标的 caliber_version 与口径库表逐条相等（`test_every_metric_has_caliber_version`）；`caliber_library_version` 进响应（`test_caliber_library_version_in_response`）；注册表与口径库一一对应（`test_registry_matches_caliber_library`）；9 条口径定义落库且 definition 非空（`test_caliber_definitions_persisted`）。

### 验收 4：1 万家虚构企业下接口 P95 < 1 秒（基准）

（工单 zh-CN 原文；预做包构建时平台返回英文版 "10,000 fictional enterprises under interface P95 < 1 second (benchmark)"，语义相同。）

- **实现**：基准数据 `scripts/seed_benchmark.py`（固定种子 `random.Random(1856)`，10,000 家虚构企业 + 6,108 条会籍，org=org-bench 两站点）；测试内基准 `tests/test_benchmark_10000.py`（事务内 bulk insert + `ANALYZE`，30 次 HTTP 请求全走 `refresh=1` 绕过缓存，测完整计算链路）；独立 HTTP 基准脚本 `scripts/benchmark_overview.py`（对运行中的 uvicorn 发真实请求）。
- **关键修复**：bulk insert 后必须 `ANALYZE companies, memberships`——新表统计信息为 0 行时，planner 会给 `count(distinct)` 选 Nested Loop 全索引扫描（实测单查询 88 秒），ANALYZE 后走 Hash Join（7ms）。
- **证据**（实测输出见下文「验证记录」）：pytest 内 30 次 refresh=1 请求 P95=61.7ms；HTTP 基准缓存命中 P95=36.7ms（100 次）、绕过缓存完整计算链路 P95=116.5ms（30 次），均远低于 1000ms。

## 统一技术约定对照

| 约定 | 落实位置 |
| --- | --- |
| 业务表统一含 id(UUID)、org_id、site_id、created_at、created_by、updated_at、deleted_at（软删除） | `app/models/base.py`（`AuditMixin` = `OrgMixin` + `TimestampMixin`），4 张表全部继承 |
| 金额以分存整数 | 本单接口无金额字段；模板沿用的整数化原则体现在 change_bp（环比/同比用万分比整数，不用浮点百分比） |
| 配置与密钥只从环境变量读 | `app/config.py`：APP_DATABASE_URL / APP_DATABASE_ADMIN_URL / APP_DATABASE_TEST_URL / APP_DASH_CACHE_TTL_SECONDS / APP_HOST / APP_PORT，见 `.env.example` |
| 不引入向境外发送数据的第三方 SDK | requirements 只有 fastapi/uvicorn/sqlalchemy/alembic/psycopg/pydantic/pytest/httpx，全部本地运行 |
| 依赖其他工单的接口用桩/mock，README 写明对接点 | 见下文「依赖与集成点」 |
| 只用虚构数据，不出现客户名称 | 全部企业名（云帆智造/东湖新材料等）、用户 ID（user-head-east 等）、org/site ID 均为自拟虚构值 |
| PostgreSQL 16 真实库（不用 SQLite） | pytest conftest 连真实 PostgreSQL 16.10；基准与冒烟同库 |

## 「本单范围」逐项对照

| 工单要求 | 文件 / 函数 | 测试 |
| --- | --- | --- |
| GET /api/dash/members/overview?site_id=&period= | `app/main.py:97` `members_overview` | 全套 |
| 认证会员企业数（期末） | `app/dash/metrics.py` `verified_members_end`（编码 DASH_MEMBERS_VERIFIED_END） | test_verified_members_end_manual |
| 有效会员企业数（会籍生效中） | `metrics.effective_members_end`（DASH_MEMBERS_EFFECTIVE_END） | test_effective_members_end_manual |
| 本期新增入会数 | `metrics.new_joins_in_period`（DASH_MEMBERS_NEW_JOINS） | test_new_joins_manual |
| 本期流失数 | `metrics.churned_in_period`（DASH_MEMBERS_CHURNED） | test_churned_manual |
| 生命周期 7 状态分布（线索/洽谈/入会/活跃/沉默/流失预警/已流失） | `metrics.lifecycle_distribution`（DASH_LIFECYCLE_DISTRIBUTION），7 个键恒全返回、无数据计 0 | test_lifecycle_distribution_manual |
| 会员等级分布 | `metrics.tier_distribution`（DASH_TIER_DISTRIBUTION），同企业取 joined_at 最晚生效会籍 | test_tier_distribution_manual |
| 近 12 个月期末有效会员数趋势 | `metrics.trend_effective_12m`（DASH_TREND_EFFECTIVE_12M） | test_trend_12m_manual |
| 环比与同比 | `metrics.mom_effective` / `metrics.yoy_effective`（DASH_MEMBERS_MOM / DASH_MEMBERS_YOY） | test_mom_manual、test_yoy_manual |
| 按口径库编码取数，响应带口径版本 | `app/dash/calibers.py`（口径库定义）+ `app/dash/registry.py`（计算函数注册）+ `service.load_caliber_versions`（读表） | test_caliber.py 5 条 |
| 排除测试账号与软删除数据 | `metrics._company_cond`（`is_test_account is false` + `deleted_at is null`）贯穿全部指标 | test_test_account_and_deleted_excluded |
| 数据来自 S2-CRM（只读，可先用桩） | `companies` / `memberships` 只读表桩，见「依赖与集成点」 | — |
| 统一响应信封 | `app/main.py` `_envelope` + HTTPException/RequestValidationError/InvalidPeriod/Exception 四个 exception_handler | test_envelope_shape、test_invalid_period_rejected、test_db_error_returns_envelope_500 |
| 权限依赖（会长只能取本会） | `app/main.py` `require_site_access`（user_roles 授权行） | test_permission.py 9 条 |
| 10 分钟缓存 | `app/dash/cache.py` TTLCache（APP_DASH_CACHE_TTL_SECONDS=600 默认，0 禁用）+ `?refresh=1` 绕过 | test_cache_second_call_is_cached、test_cache_disabled_when_ttl_zero |
| 交付物：聚合接口 | `app/main.py` | — |
| 交付物：计算函数注册 | `app/dash/registry.py`（CALCULATORS 字典 + 启动校验） | test_registry_matches_caliber_library |
| 交付物：虚构数据集与测试 | `scripts/seed_demo.py`（22 企业）、`scripts/seed_benchmark.py`（1 万企业）、tests/ 4 个文件 | 37 条用例 |

## 边界情况对照（按八类边界逐类过）

| 边界类 | 本单处理 | 测试 |
| --- | --- | --- |
| ① 正常路径 | 9 指标手算逐项一致 + 独立 raw SQL 复算 | test_overview_calc 22 条 |
| ② 空输入/空数据 | 空站点全指标 0/空分布、生命周期 7 键恒全返回计 0；period 缺省取数据集最近业务月份 | test_empty_site_all_zero_metrics、test_default_period_is_latest_activity_month |
| ③ 上限 | 1 万企业规模基准（工单给的规模点），P95 < 1 秒 | test_benchmark_10000 + scripts/benchmark_overview.py |
| ④ 格式/类型不对 | period 非法（字母/月越界/缺横线/空串）→ 400；缺权限头或缺 site_id → 422 | test_invalid_period_rejected、test_period_rejects_invalid_formats、test_missing_headers_rejected、test_missing_site_id_rejected |
| ⑤ 被引用对象自身无效 | 本单是只读聚合接口，无引用链写入，多级连锁不适用；对应形态是 join：会籍引用的企业被软删除/为测试账号时整行排除 | test_test_account_and_deleted_excluded（_company_cond 贯穿全部指标） |
| ⑥ 权限/身份不对 | 本站 200、跨站/跨组织/org 不匹配/未知用户 403、缺头 422、admin 按授权行多站可读、只给角色名不放行 | test_permission.py 9 条 |
| ⑦ 重复/并发/幂等 | GET 只读天然幂等；重复请求走缓存（cached=true）、refresh=1 绕过、TTL=0 禁用；多进程各 worker 各自缓存 | test_cache_second_call_is_cached、test_cache_disabled_when_ttl_zero |
| ⑧ 依赖失败/回滚 | 数据库不可用 → 统一信封 500（Exception 兜底 handler，不泄露内部细节）；get_db 异常回滚；测试夹具事务回滚隔离 | test_db_error_returns_envelope_500、tests/conftest.py test_tx |

## 依赖与集成点

- **S2-CRM（CRM 核心对象）**：本单按工单允许先用桩——把企业（`companies`）、会籍（`memberships`）落成本单库内的只读表，字段与统一基类一致。真实接入时：把这两个表的 ORM 换成指向 S2-CRM 库的只读引擎（`app/db.py` 加第二个 engine），或在 S2-CRM 暴露内部查询接口后由本服务的 `app/dash/metrics.py` 数据访问层切换过去；指标计算函数签名不变。
- **权限对接**：`user_roles` 表是授权桩；真实接入时替换为平台统一鉴权服务返回的用户-站点授权（`require_site_access` 依赖一个函数，改这一处即可）。
- **驾驶舱前端（S3-DASH 其他工单）**：响应信封 `code/message/data/meta`，data.metrics 按口径编码为键，前端可直接按编码渲染卡片。

## 运行与测试（陌生人复跑步骤）

```bash
# 1) 环境：Python 3.14.3 + PostgreSQL 16.10（Windows 11，本机 127.0.0.1:5432）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 2) 建库（psql）
create database dash_members;
create database dash_members_test;

# 3) 迁移（口径库 9 条种子随迁移落库）
set APP_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/dash_members
set APP_DATABASE_ADMIN_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres
set APP_DATABASE_TEST_URL=postgresql+psycopg://postgres@127.0.0.1:5432/dash_members_test
.venv/Scripts/python.exe -m alembic upgrade head

# 4) 全部测试（连真实 PostgreSQL 16，37 条用例）
.venv/Scripts/python.exe -m pytest -v

# 5) 演示数据集 + 起服务冒烟
.venv/Scripts/python.exe scripts/seed_demo.py
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8301
curl -s -H "X-Org-Id: org-demo" -H "X-User-Id: user-head-east" "http://127.0.0.1:8301/api/dash/members/overview?site_id=site-east&period=2026-10"

# 6) 1 万企业基准（基准脚本默认打 8000 端口；目标服务不在 8000 时用 APP_BENCHMARK_BASE_URL 指过去）
.venv/Scripts/python.exe scripts/seed_benchmark.py
set APP_BENCHMARK_BASE_URL=http://127.0.0.1:8303
.venv/Scripts/python.exe scripts/benchmark_overview.py --requests 100          # 缓存命中
.venv/Scripts/python.exe scripts/benchmark_overview.py --requests 30 --refresh # 绕过缓存
```

## 验证记录（真实命令与原始输出，2026-11-21 干净目录匿名 clone 重跑）

环境：Windows 11（10.0.26200 x64）、PostgreSQL 16.10（本机 127.0.0.1:5432，psql 16.10）、Python 3.14.3；依赖版本来自干净 venv 的 pip list：fastapi 0.118.0、uvicorn 0.37.0、SQLAlchemy 2.0.44、alembic 1.16.5、psycopg 3.2.10、pydantic 2.12.3、pytest 8.4.2、httpx 0.28.1。
复跑方式：`git -c credential.helper= clone https://github.com/lionourjson/clawhunt-1856-dash-members-overview.git`（无登录凭据的匿名 clone），建干净 venv 后 pip install -r requirements.txt。

### 建库与迁移往返（upgrade head → downgrade base → upgrade head）

```
psql：drop database if exists dash_members / dash_members_test，create database ×2
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, 初始迁移：驾驶舱聚合接口数据表 + 口径库种子数据。
INFO  [alembic.runtime.migration] Running downgrade 0001 -> , 初始迁移：驾驶舱聚合接口数据表 + 口径库种子数据。
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, 初始迁移：驾驶舱聚合接口数据表 + 口径库种子数据。
（随后 psql 查询 metric_calibers 行数 = 9）
```

### pytest 全套（真实 PostgreSQL 16，37 条）

```
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.16.0
collecting ... collected 37 items

tests/test_benchmark_10000.py::test_p95_under_1s PASSED                  [  2%]
tests/test_caliber.py::test_all_nine_metrics_present PASSED              [  5%]
tests/test_caliber.py::test_every_metric_has_caliber_version PASSED      [  8%]
tests/test_caliber.py::test_caliber_library_version_in_response PASSED   [ 10%]
tests/test_caliber.py::test_registry_matches_caliber_library PASSED      [ 13%]
tests/test_caliber.py::test_caliber_definitions_persisted PASSED         [ 16%]
tests/test_overview_calc.py::test_envelope_shape PASSED                  [ 18%]
tests/test_overview_calc.py::test_verified_members_end_manual PASSED     [ 21%]
tests/test_overview_calc.py::test_effective_members_end_manual PASSED    [ 24%]
tests/test_overview_calc.py::test_new_joins_manual PASSED                [ 27%]
tests/test_overview_calc.py::test_churned_manual PASSED                  [ 29%]
tests/test_overview_calc.py::test_lifecycle_distribution_manual PASSED   [ 32%]
tests/test_overview_calc.py::test_tier_distribution_manual PASSED        [ 35%]
tests/test_overview_calc.py::test_trend_12m_manual PASSED                [ 37%]
tests/test_overview_calc.py::test_mom_manual PASSED                      [ 40%]
tests/test_overview_calc.py::test_yoy_manual PASSED                      [ 43%]
tests/test_overview_calc.py::test_sql_cross_check_matches_api PASSED     [ 45%]
tests/test_overview_calc.py::test_test_account_and_deleted_excluded PASSED [ 48%]
tests/test_overview_calc.py::test_invalid_period_rejected PASSED         [ 51%]
tests/test_overview_calc.py::test_default_period_is_latest_activity_month PASSED [ 54%]
tests/test_overview_calc.py::test_cache_second_call_is_cached PASSED     [ 56%]
tests/test_overview_calc.py::test_empty_site_all_zero_metrics PASSED     [ 59%]
tests/test_overview_calc.py::test_period_rejects_invalid_formats[abc] PASSED [ 62%]
tests/test_overview_calc.py::test_period_rejects_invalid_formats[2026-14] PASSED [ 64%]
tests/test_overview_calc.py::test_period_rejects_invalid_formats[202601] PASSED [ 67%]
tests/test_overview_calc.py::test_period_rejects_invalid_formats[] PASSED [ 70%]
tests/test_overview_calc.py::test_cache_disabled_when_ttl_zero PASSED    [ 72%]
tests/test_overview_calc.py::test_db_error_returns_envelope_500 PASSED   [ 75%]
tests/test_permission.py::test_club_head_can_read_own_site PASSED        [ 78%]
tests/test_permission.py::test_club_head_cannot_read_other_site PASSED   [ 81%]
tests/test_permission.py::test_club_head_cannot_read_other_org_site PASSED [ 83%]
tests/test_permission.py::test_org_mismatch_rejected PASSED              [ 86%]
tests/test_permission.py::test_unknown_user_rejected PASSED              [ 89%]
tests/test_permission.py::test_missing_headers_rejected PASSED           [ 91%]
tests/test_permission.py::test_missing_site_id_rejected PASSED           [ 94%]
tests/test_permission.py::test_admin_can_read_authorized_sites PASSED    [ 97%]
tests/test_permission.py::test_role_name_alone_grants_nothing PASSED     [100%]

======================= 37 passed, 13 warnings in 3.79s =======================
```

benchmark 用例 -s 输出（30 次 refresh=1 全链路请求）：
`benchmark: n=30 p50=56.8ms p95=61.7ms max=61.8ms mean=56.8ms`（1 passed in 2.70s）

warnings 说明：13 条均为 DeprecationWarning（starlette testclient 的 anyio 别名，依赖库内部）与 SAWarning（测试夹具事务回滚顺序提示），不影响结果。

### uvicorn 冒烟（演示数据集，org-demo/site-east，period=2026-10）

```
GET /healthz
{"ok":true}

GET /api/dash/members/overview?site_id=site-east&period=2026-10   （会长 user-head-east，首次 cached=false）
{"code":0,"message":"ok","data":{"site_id":"site-east","period":"2026-10",
 "period_start":"2026-10-01T00:00:00+00:00","period_end":"2026-10-31T23:59:59+00:00",
 "caliber_library_version":"v1.0.0","metrics":{
  "DASH_MEMBERS_VERIFIED_END":{"value":8,...},
  "DASH_MEMBERS_EFFECTIVE_END":{"value":7,...},
  "DASH_MEMBERS_NEW_JOINS":{"value":1,...},
  "DASH_MEMBERS_CHURNED":{"value":1,...},
  "DASH_LIFECYCLE_DISTRIBUTION":{"value":{"lead":1,"negotiating":1,"joined":1,"active":5,"silent":1,"churn_warning":1,"churned":2},...},
  "DASH_TIER_DISTRIBUTION":{"value":{"advanced":3,"premium":2,"standard":2},...},
  "DASH_TREND_EFFECTIVE_12M":{"value":[{"month":"2025-11","effective_members_end":6},{"month":"2025-12","effective_members_end":7},...,
                                        {"month":"2026-08","effective_members_end":8},...,{"month":"2026-10","effective_members_end":7}],...},
  "DASH_MEMBERS_MOM":{"value":{"current":7,"previous":7,"delta":0,"change_bp":0},...},
  "DASH_MEMBERS_YOY":{"value":{"current":7,"previous":6,"delta":1,"change_bp":1667},...}},
 "meta":{"cached":false}}（每个指标都带 caliber_code/caliber_version=v1.0.0，与手算逐项一致）

GET 同参第二次    → meta {"cached": true}（10 分钟缓存命中）
GET ?refresh=1    → meta {"cached": false}
GET ?site_id=site-west（会长 east）→ HTTP 403 {"code":403,"message":"user user-head-east has no access to site site-west","data":null}
GET ?period=2026-13 → HTTP 400 {"code":400,"message":"period must be YYYY-MM, got '2026-13'","data":null}
```

### HTTP 基准（10,000 家虚构企业，org-bench/site-bench-1，独立 uvicorn 进程）

基准脚本默认目标 8000 端口；本轮服务起在 8303，用 `APP_BENCHMARK_BASE_URL=http://127.0.0.1:8303` 指定（脚本自带的环境变量，见 scripts/benchmark_overview.py）。

```
=== 缓存命中（100 次请求）===
预热请求 OK：effective_members_end=2421（period=2026-07）
{"requests":100,"status_codes":{"200":100},"p50_ms":29.3,"p95_ms":36.7,"p99_ms":39.7,"max_ms":42.1,"mean_ms":23.8,"refresh":false}
P95 < 1000ms: PASS

=== 绕过缓存 refresh=1（30 次请求，完整计算链路）===
预热请求 OK：effective_members_end=2421（period=2026-07）
{"requests":30,"status_codes":{"200":30},"p50_ms":77.1,"p95_ms":116.5,"p99_ms":118.6,"max_ms":118.6,"mean_ms":78.8,"refresh":true}
P95 < 1000ms: PASS
```

## 文件清单

```
app/config.py                     环境变量配置
app/db.py                         引擎与会话
app/main.py                       接口 + 权限依赖 + 统一信封
app/models/base.py                统一基类（AuditMixin + soft_delete_filter）
app/models/company.py             企业（生命周期/认证/流失时间/测试账号标记）
app/models/membership.py          会籍（等级/起止日/入会时间）
app/models/caliber.py             口径库表
app/models/user_role.py           用户-站点授权
app/dash/calibers.py              口径库定义（9 个编码，单一来源）
app/dash/metrics.py               指标计算函数（按编码一一对应）
app/dash/registry.py              计算函数注册表 + 启动校验
app/dash/cache.py                 进程内 TTL 缓存（默认 600s）
app/dash/service.py               聚合服务（组响应 + 缓存入口）
alembic/versions/0001_initial.py  建表 + 口径库种子（含 downgrade）
scripts/seed_demo.py              演示数据集（22 家虚构企业，手工可核）
scripts/seed_benchmark.py         基准数据集（10,000 家，种子 1856，含 ANALYZE）
scripts/benchmark_overview.py     HTTP P50/P95/P99 基准脚本
tests/conftest.py                 真实 PG16 夹具（事务回滚隔离）+ 演示站点夹具
tests/test_overview_calc.py       验收 1（手算 + 独立 SQL 复算 + 边界，22 条）
tests/test_permission.py          验收 2（9 条）
tests/test_caliber.py             验收 3（5 条）
tests/test_benchmark_10000.py     验收 4（1 条）
.env.example                      环境变量样例（无任何真实密钥）
```

## 缓存说明

进程内 TTL 缓存，key=(org_id, site_id, period)，TTL 默认 600 秒（工单要求 10 分钟），`APP_DASH_CACHE_TTL_SECONDS=0` 可禁用，`?refresh=1` 单次绕过并重算。多进程部署时各 worker 各自缓存，接 Redis 可替换 `app/dash/cache.py` 的实现（接口不变）。
