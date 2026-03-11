# MCP Prompt 模板（可直接复制）

## 1. 使用方式

1. 把下面任一模板整段复制到支持 MCP 工具调用的对话窗口。  
2. 仅替换 `{{...}}` 占位符。  
3. 保持模板中的“返回格式”不改，方便统一阅读。


## 2. 模板 1：先查可用场景

```text
请使用 MCP 工具 `list_scenarios`，参数如下：
{
  "limit": 20,
  "keyword": "{{KEYWORD}}"
}

执行后请按以下格式返回：
1. 结果：成功/失败
2. 共返回多少条：total
3. 场景列表（最多前 10 条）：scenario_id + request_count + last_start_time
4. 如果失败：error_code + message + hint
```


## 3. 模板 2：按场景做回归对比

```text
请使用 MCP 工具 `run_regression_by_scenario`，参数如下：
{
  "old_scenario_id": "{{OLD_SCENARIO_ID}}",
  "new_scenario_id": "{{NEW_SCENARIO_ID}}"
}

执行后请按以下格式返回：
1. 结果：成功/失败（ok）
2. 批次：batch_id / batch_code
3. 统计：stats
4. 报告路径：report_path
5. 如果失败：error_code + message + hint
```


## 4. 模板 3：按 trace 一对一对比

```text
请使用 MCP 工具 `run_regression_by_trace_pair`，参数如下：
{
  "old_trace_id": "{{OLD_TRACE_ID}}",
  "new_trace_id": "{{NEW_TRACE_ID}}"
}

执行后请按以下格式返回：
1. 结果：成功/失败（ok）
2. 批次：batch_id / batch_code
3. 统计：stats
4. 报告路径：report_path
5. 如果失败：error_code + message + hint
```


## 5. 模板 4：按场景回放并自动对比

```text
请使用 MCP 工具 `replay_and_diff_by_scenario`，参数如下：
{
  "source_scenario_id": "{{SOURCE_SCENARIO_ID}}",
  "target_base_url": "{{TARGET_BASE_URL}}"
}

执行后请按以下格式返回：
1. 结果：成功/失败（ok）
2. 回放批次：replay_batch_id / replay_scenario_id
3. 对比批次：batch_id / batch_code
4. 统计：replay_stats 和 stats
5. 报告路径：report_path
6. 如果失败：error_code + message + hint
```


## 6. 模板 5：按 trace 列表回放并自动对比

```text
请使用 MCP 工具 `replay_and_diff_by_trace_ids`，参数如下：
{
  "trace_ids": "{{TRACE_ID_1}},{{TRACE_ID_2}}",
  "target_base_url": "{{TARGET_BASE_URL}}"
}

执行后请按以下格式返回：
1. 结果：成功/失败（ok）
2. 回放批次：replay_batch_id / replay_scenario_id
3. 对比批次：batch_id / batch_code
4. 统计：replay_stats 和 stats
5. 报告路径：report_path
6. 如果失败：error_code + message + hint
```


## 7. 常见占位符示例

- `{{TARGET_BASE_URL}}`：`http://jsonplaceholder.typicode.com`
- `{{OLD_SCENARIO_ID}}`：`custTransInfo#old#20260309_01`
- `{{NEW_SCENARIO_ID}}`：`custTransInfo#new#20260309_01`
- `{{SOURCE_SCENARIO_ID}}`：`readonlyReplay#old#20260311_223100`
- `{{OLD_TRACE_ID}}`：`TC001OLD_001`
- `{{NEW_TRACE_ID}}`：`TC001NEW_002`
