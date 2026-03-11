# json-diff

## Stable CLI

```bash
python3 scripts/regression_cli.py "ALL" "old_scenario_id" "new_scenario_id"
```

- `ALL` / `*`: compare all api paths in selected scenarios
- `"/path/a,/path/b"`: compare selected api paths
- `--dry-run`: preflight only, no indexing or compare
- `--json`: print structured JSON result
- Default report path: `output/<batch_code>/测试报告.md`, and also updates `output/latest.md`

## Trace Pair Compare

Directly compare two specific samples by trace id:

```bash
python3 scripts/regression_cli.py --old-trace-id "OLD_TRACE_ID" --new-trace-id "NEW_TRACE_ID"
```

Optional: you can still pass scenario ids in trace mode to override batch metadata fields.
