# json-diff

本仓库用于做接口新旧版本回归对比。  
`docs/` 里的运行命令已统一收敛到本文件，`docs/` 只保留设计和说明信息。

## 1. 环境准备

### 1.1 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 1.2 离线安装（内网无公网时）

外网机器下载依赖：

```bash
python3 -m pip download -r requirements.txt -d wheelhouse
tar -czf wheelhouse.tar.gz wheelhouse
```

内网机器安装：

```bash
tar -xzf wheelhouse.tar.gz
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --no-index --find-links=wheelhouse -r requirements.txt
```

### 1.3 MySQL 配置

最常用是设置 `MYSQL_DEMO_CONF`（格式：`host,port,database,user,password[,charset]`）：

```bash
export MYSQL_DEMO_CONF='127.0.0.1,3308,demo_db,dev,123456,utf8mb4'
export REGRESSION_TARGET_SCHEMA='rrs_test_dev'
```

如果你使用仓库里的配置文件 `conf/aml_conf.conf`（例如 `rrs_test_dev`）：

```bash
export MYSQL_DEMO_CONF="$(python3 -c 'from conf.config import get_config; print(get_config("rrs_test_dev", conf_file="aml_conf.conf"))')"
export REGRESSION_TARGET_SCHEMA='rrs_test_dev'
```

## 2. 初始化命令

### 2.1 生产初始化（推荐，仅建表）

```bash
python3 scripts/init_schema_only.py
```

### 2.2 DEMO 初始化（会清表）

```bash
python3 scripts/init_demo_data.py
```

可选不清表：

```bash
python3 scripts/init_demo_data.py --no-truncate
```

## 3. 核心运行命令（稳定入口）

统一入口：`scripts/regression_cli.py`

### 3.1 场景模式（推荐）

对场景下所有接口：

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id"
```

对指定接口（支持逗号分隔）：

```bash
python3 scripts/regression_cli.py "/a,/b" "old_scenario_id" "new_scenario_id"
```

前缀模糊匹配：

```bash
python3 scripts/regression_cli.py "/aml/str/strCase/list" "strCase#old#20260310_01" "strCase#new#20260310_01" --fuzzy
```

### 3.2 Trace 模式（单对样本）

```bash
python3 scripts/regression_cli.py --old-trace-id "OLD_TRACE_ID" --new-trace-id "NEW_TRACE_ID"
```

说明：

- `--old-trace-id/--new-trace-id` 必须同时传。
- 这里必须是 `trace_id`，不是 `scenario_id`。

### 3.3 常用可选参数

预检查不落库：

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id" --dry-run
```

输出 JSON：

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id" --json
```

指定任务信息：

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id" \
  --batch-code "REG_xxx" \
  --batch-name "接口回归任务" \
  --biz-name "aml-web" \
  --operator "your_name" \
  --remark "note" \
  --report-path "output/custom_report.md"
```

## 4. 兼容/演示入口

### 4.1 兼容入口（计划 2026-06-30 弃用）

```bash
python3 scripts/run_regression_only.py --old-scenario-id "old_scenario_id" --new-scenario-id "new_scenario_id"
```

### 4.2 一键演示入口（会清表 + 造数 + 比对）

```bash
python3 scripts/run_demo.py
```

## 5. 测试命令

全量（含 e2e）：

```bash
python3 -m unittest tests/test_runner.py tests/test_diff_engine.py tests/test_service.py tests/test_e2e.py -v
```

仅 e2e（指定批次）：

```bash
TEST_BATCH_CODE="REG_xxx" python3 -m unittest tests/test_e2e.py -v
```

## 6. 报告与结果

每次执行会输出：

- `output/<batch_code>/测试报告.md`
- `output/latest.md`

快速查看最新报告：

```bash
cat output/latest.md
```

当前报告口径（按最新代码）：

- 成功：`compare_status = SUCCESS` 且 `diff_level != BLOCK`
- 失败：`compare_status != SUCCESS` 或 `diff_level = BLOCK`
- 报告会分别打印成功/失败 `trace_id`，格式为逐行 `'trace_id'`，仅非最后一行带逗号。

## 7. 结果校验 SQL（可选）

```sql
SELECT 't_request_info' AS table_name, COUNT(*) AS cnt FROM rrs_test_dev.t_request_info
UNION ALL
SELECT 't_request_compare_index', COUNT(*) FROM rrs_test_dev.t_request_compare_index
UNION ALL
SELECT 't_regression_batch', COUNT(*) FROM rrs_test_dev.t_regression_batch
UNION ALL
SELECT 't_compare_result', COUNT(*) FROM rrs_test_dev.t_compare_result
UNION ALL
SELECT 't_compare_result_detail', COUNT(*) FROM rrs_test_dev.t_compare_result_detail;
```

## 8. MCP 服务（可选）

```bash
python3 scripts/regression_mcp_server.py
```

客户端配置样例见：`docs/mcp_config.example.json`

## 9. 其他文档

设计和实现说明见 `docs/`：

- [设计文档目录](docs/设计文档目录.md)
- [系统实现设计](docs/系统实现设计.md)
- [规则配置设计](docs/规则配置设计.md)
- [任务与报表设计](docs/任务与报表设计.md)
