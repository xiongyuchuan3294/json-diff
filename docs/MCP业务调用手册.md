# MCP 业务调用手册（最少参数版）

## 1. 适用人群

给日常做回归验证的业务/测试同学使用。  
目标：不记复杂参数，也能完成“回归对比”和“回放+自动对比”。


## 2. 先准备好 MCP 服务

服务端脚本：

- `scripts/regression_mcp_server.py`

客户端配置示例：

- `docs/mcp_config.example.json`

确认能用：

- 调用 `ping`
- 返回里 `ok=true` 即可


## 3. 最常用 5 个操作（最少参数）

### 3.1 先查可用场景（推荐第一步）

工具：`list_scenarios`

最简参数：

```json
{
  "limit": 20
}
```

### 3.2 按场景做回归对比（最常用）

工具：`run_regression_by_scenario`

最简参数：

```json
{
  "old_scenario_id": "custTransInfo#old#20260309_01",
  "new_scenario_id": "custTransInfo#new#20260309_01"
}
```

说明：

- 不传 `api_paths` 时默认对比全部接口。

### 3.2.1 按场景 + 单接口做回归对比

工具：`run_regression_by_scenario_and_api`

最简参数：

```json
{
  "old_scenario_id": "custTransInfo#old#20260309_01",
  "new_scenario_id": "custTransInfo#new#20260309_01",
  "api_path": "/aml/wst/custTransInfo"
}
```

### 3.3 按 trace 一对一对比

工具：`run_regression_by_trace_pair`

最简参数：

```json
{
  "old_trace_id": "TC001OLD_001",
  "new_trace_id": "TC001NEW_002"
}
```

### 3.4 按场景回放并自动对比

工具：`replay_and_diff_by_scenario`

最简参数：

```json
{
  "source_scenario_id": "readonlyReplay#old#20260311_223100",
  "target_base_url": "http://jsonplaceholder.typicode.com"
}
```

说明：

- 回放后会自动做 `source_scenario_id vs replay_scenario_id` 对比。

### 3.4.1 按场景 + 单接口回放并自动对比

工具：`replay_and_diff_by_scenario_and_api`

最简参数：

```json
{
  "source_scenario_id": "readonlyReplay#old#20260311_223100",
  "target_base_url": "http://jsonplaceholder.typicode.com",
  "api_path": "/todos/1"
}
```

### 3.5 按 trace 列表回放并自动对比

工具：`replay_and_diff_by_trace_ids`

最简参数：

```json
{
  "trace_ids": "READONLY_TODO_20260311_223100,READONLY_POST_20260311_223100",
  "target_base_url": "http://jsonplaceholder.typicode.com"
}
```


## 4. 如何看结果

执行类工具返回里重点看：

- `ok`
- `batch_id` / `batch_code`
- `replay_batch_id`（回放模式）
- `stats`
- `report_path`

`ok=false` 时直接看：

- `error_code`
- `message`
- `hint`


## 5. 建议固定流程（3 步）

1. `list_scenarios` 找到要比对/回放的场景。  
2. 选一个执行工具（场景对比 / trace 对比 / 回放对比）。  
3. 看返回里的 `report_path` 和 `stats`。  

如果失败，优先根据 `hint` 修正参数再重试。

## 6. 复制即用模板

如果你希望直接复制一段对话给助手调用 MCP 工具，使用：

- `docs/MCP-Prompt模板.md`
