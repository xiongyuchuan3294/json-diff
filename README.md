# json-diff

## Stable CLI

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id"
```

- `ALL` / `*`：按场景下全部接口批量对比
- `"/path/a,/path/b"`：按多接口子集批量对比
- `--dry-run`：只做预检查，不落库
- `--json`：输出结构化 JSON
- 报告默认输出：`output/<batch_code>/测试报告.md`，并更新 `output/latest.md`
