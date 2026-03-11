# MCP 易用化接入方案（先于可视化）

## 1. 背景与目标

当前 CLI 入口功能完整，但参数较多，用户需要理解模式差异（scenario/trace/replay）并手动拼装参数，使用门槛偏高。  
本方案目标是在不破坏现有 CLI 的前提下，优先通过 MCP 提供“低心智负担”的调用入口。

本次目标：

- 把高频能力封装为语义化 MCP 工具，而不是参数化脚本调用。
- 默认参数内置，减少必填项数量。
- 统一错误提示与返回结构，便于客户端直出。
- 保持现有 CLI/DB/回归引擎兼容，不改业务口径。


## 2. 范围

包含：

- `scripts/regression_mcp_server.py` 工具层改造。
- 新增“选择器友好”的回放+对比 MCP 接口。
- 增加查询辅助工具（场景、接口路径、最近批次）。
- 增加 MCP 层单元测试与契约测试。
- 更新 README 与 `docs/mcp_config.example.json`。

不包含：

- 前后端可视化页面。
- 新数据库表结构变更（沿用现有表）。
- 变更 diff 业务规则口径。


## 3. 现状问题

- 工具参数偏底层：用户需要知道 `api_paths`、`old/new_scenario_id`、`replay selector` 组合约束。
- replay 的 selector 需要“二选一”规则，出错成本高。
- 用户经常不知道可选 `scenario_id`/`api_path` 值，缺少“先查后跑”入口。
- MCP 仅暴露回归，不包含 replay 主流程，不足以成为主入口。


## 4. 设计原则

- 单一职责：每个工具只对应一种明确操作意图。
- 最小必填：默认值前置，必要信息才要求输入。
- 参数安全：强校验，错误信息直接可行动。
- 结果可追溯：返回 `batch_id/replay_batch_id/report_path/stats`。
- 向后兼容：底层仍调用 `run_regression_job`，不破坏 CLI。


## 5. MCP 工具设计（P0）

### 5.1 基础健康检查

- `ping() -> {ok, server, version}`

### 5.2 查询辅助（降低组参成本）

- `list_scenarios(limit=20, keyword="")`
- `list_api_paths(scenario_id, limit=50, keyword="")`
- `list_recent_batches(limit=20, mode="REGRESSION|REPLAY|ALL")`
- `get_batch_report(batch_id="", batch_code="")`

说明：

- 查询工具优先返回“可直接复制到运行工具”的字段。
- `list_api_paths` 支持按场景推荐路径，避免手工猜 path。

### 5.3 执行工具（语义化）

- `run_regression_by_scenario(old_scenario_id, new_scenario_id, api_paths="ALL", fuzzy=false, dry_run=false, ...可选任务字段)`
- `run_regression_by_trace_pair(old_trace_id, new_trace_id, dry_run=false, ...可选任务字段)`
- `replay_and_diff_by_scenario(source_scenario_id, target_base_url, api_paths="ALL", fuzzy=false, replay_speed_factor=1.0, replay_min_gap_ms=300, replay_max_gap_ms=3000, replay_timeout_ms=10000, replay_retries=1, dry_run=false, ...可选任务字段)`
- `replay_and_diff_by_trace_ids(trace_ids, target_base_url, replay_speed_factor=1.0, replay_min_gap_ms=300, replay_max_gap_ms=3000, replay_timeout_ms=10000, replay_retries=1, dry_run=false, ...可选任务字段)`

说明：

- 不再让用户在一个工具里自行判断模式。
- `trace_ids` 允许字符串（逗号分隔）和数组两种输入，服务端归一化。


## 6. 参数与校验策略

校验规则：

- `target_base_url` 必须 `http://` 或 `https://`。
- replay 速率参数需满足：`speed_factor>0`，`min_gap_ms>=0`，`max_gap_ms>=min_gap_ms`，`timeout_ms>0`，`retries>=0`。
- trace 对比要求 old/new 成对出现。
- replay by trace 要求 trace 均存在且属于同一 source scenario（沿用已有规则）。

默认值策略：

- 所有任务默认 `operator="mcp"`。
- `api_paths` 默认 `"ALL"`。
- `batch_code/replay_code` 默认自动生成（微秒级防冲突）。

错误返回规范：

- 统一结构：`{ok:false, error_code, message, hint, input_echo}`
- `hint` 提供下一步建议，减少反复试错。


## 7. 返回结构标准化

执行类工具统一返回：

- `ok`
- `mode`
- `scope`
- `batch_id`
- `batch_code`
- `replay_batch_id`（如适用）
- `replay_scenario_id`（如适用）
- `stats`
- `report_path`
- `latest_report_path`
- `compare_success_trace_ids`
- `compare_failed_trace_ids`
- `preflight`

查询类工具统一返回：

- `ok`
- `items`
- `total`
- `next_cursor`（预留）


## 8. 服务端实现改造点

文件：

- `scripts/regression_mcp_server.py`

改造内容：

- 新增上述工具函数，工具内只做参数解析与校验。
- 调用层统一汇聚到 `RegressionJobParams + run_regression_job`。
- 对查询工具，新增只读查询函数（可放 `src/regression_demo/service.py` 或 `runner.py` 辅助函数）。
- 所有工具增加 docstring，便于 MCP 客户端展示。


## 9. 测试方案

### 9.1 单元测试（P0 必做）

- 新增 `tests/test_mcp_server.py`。
- 使用 `unittest.mock` mock `run_regression_job` 与 DB 查询。
- 覆盖点：
  - 每个工具成功路径。
  - replay 参数非法路径。
  - trace/senario 模式参数缺失路径。
  - 返回结构字段完整性。

### 9.2 集成测试（P0 建议）

- 启动 MCP server（stdio），通过客户端调用：
  - `run_regression_by_scenario`
  - `run_regression_by_trace_pair`
  - `replay_and_diff_by_scenario`
- 验证返回与数据库落库一致（批次存在、报告路径可访问）。

### 9.3 回归测试

- 现有 CLI 测试保持全通过。
- replay 的既有测试保持全通过。


## 10. 交付计划

### 阶段 A（1 天，P0）

- 扩展 MCP 工具定义。
- 实现参数校验与标准返回。
- 补 `test_mcp_server.py` 单测。
- 更新 README 的 MCP 使用示例。

### 阶段 B（0.5 天，P0+）

- 增加查询辅助工具（场景、路径、批次）。
- 增加集成调用示例文档。

### 阶段 C（后续，P1）

- 在 MCP 之上生成 typed CLI wrapper（减少命令手敲）。
- 再评估是否加轻量 Web 表单页。


## 11. 验收标准

- MCP 可独立完成 4 类操作：场景对比、trace 对比、场景回放+对比、trace 回放+对比。
- 新用户不看源码，仅看 MCP 工具描述即可完成一次 replay+diff。
- 常见输入错误能返回可执行提示，不需要查看服务端日志。
- 不影响现有 CLI 与数据库口径。


## 12. 风险与应对

- 风险：工具过多导致用户选择困难。  
  应对：保留 4 个执行主工具 + 4 个查询工具，不做冗余别名。

- 风险：返回字段不统一导致客户端处理复杂。  
  应对：统一响应 envelope（`ok/error_code/message/data`）。

- 风险：后续 UI 与 MCP 参数口径不一致。  
  应对：UI 直接消费 MCP 工具定义，禁止 UI 自造参数协议。
