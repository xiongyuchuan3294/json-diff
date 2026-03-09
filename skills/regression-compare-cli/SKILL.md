---
name: regression-compare-cli
description: Run old/new API regression comparison through a stable Python CLI with exactly three required parameters. Use when the user asks to compare API response JSON between two scenario_id datasets, run single or multi-interface batch regression, or trigger regression quickly in weak-model intranet environments.
---

# Regression Compare CLI

Execute regression with one stable command:

`python3 scripts/regression_cli.py <api_paths> <old_scenario_id> <new_scenario_id>`

## Accept Inputs

Collect exactly three parameters:

1. `api_paths`
2. `old_scenario_id`
3. `new_scenario_id`

Interpret `api_paths` as:

- `ALL` or `*`: compare all interface paths under these scenario IDs.
- Comma-separated paths: compare only that subset, e.g. `/aml/wst/custTransInfo,/aml/wst/riskSummary`.

## Execute

Run from repo root:

```bash
python3 scripts/regression_cli.py "<api_paths>" "<old_scenario_id>" "<new_scenario_id>"
```

Examples:

```bash
# Full batch compare for all APIs
python3 scripts/regression_cli.py "ALL" "custTransInfo#old#20260309_01" "custTransInfo#new#20260309_01"

# Multi-interface subset compare
python3 scripts/regression_cli.py "/aml/wst/custTransInfo,/aml/wst/riskSummary" "custTransInfo#old#20260309_01" "custTransInfo#new#20260309_01"
```

## Report And Output

After execution, read:

- CLI stdout fields: `scope`, `batch_id`, `batch_code`, `indexed`, `stats`.
- Report file: `output/<batch_code>/测试报告.md` and `output/latest.md`.

If command fails:

- Verify DB env var `MYSQL_DEMO_CONF`.
- Verify scenario IDs exist in `t_request_info`.
- Retry with `api_paths=ALL` to exclude path filter issues.

## Constraints

- Do not modify `t_request_info` table structure.
- Use this skill for execution only; DB schema evolution is out of scope.
