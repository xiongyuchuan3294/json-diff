#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.runner import RegressionJobParams, normalize_api_paths, run_regression_job

DEPRECATION_DATE = "2026-06-30"


def _print_trace_id_lines(title: str, trace_ids: list[str]) -> None:
    print(title)
    last_index = len(trace_ids) - 1
    for index, trace_id in enumerate(trace_ids):
        suffix = "," if index < last_index else ""
        print(f"'{trace_id}'{suffix}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"只执行回归比对（兼容入口，计划于 {DEPRECATION_DATE} 弃用）"
    )
    parser.add_argument(
        "--api-path",
        action="append",
        default=[],
        help="接口 path，可重复传入或逗号分隔；不传则按场景ID覆盖的全部接口批量对比",
    )
    parser.add_argument("--old-scenario-id", required=True, help="旧版本 scenario_id")
    parser.add_argument("--new-scenario-id", required=True, help="新版本 scenario_id")
    parser.add_argument("--batch-code", default="", help="任务编码，默认自动生成")
    parser.add_argument("--batch-name", default="接口回归任务", help="任务名称")
    parser.add_argument("--biz-name", default="aml-web", help="业务名称")
    parser.add_argument("--operator", default="codex", help="操作人")
    parser.add_argument("--remark", default="", help="备注")
    parser.add_argument("--report-path", default="", help="报告输出路径，默认 output/<batch_code>/测试报告.md")
    parser.add_argument("--dry-run", action="store_true", help="仅做预检查，不执行索引构建和回归")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_paths = normalize_api_paths(",".join(args.api_path))
    api_paths_arg = "ALL" if not selected_paths else ",".join(selected_paths)
    result = run_regression_job(
        RegressionJobParams(
            api_paths_arg=api_paths_arg,
            old_scenario_id=args.old_scenario_id,
            new_scenario_id=args.new_scenario_id,
            batch_code=args.batch_code,
            batch_name=args.batch_name,
            biz_name=args.biz_name,
            operator=args.operator,
            remark=args.remark,
            report_path=args.report_path or None,
            dry_run=args.dry_run,
        ),
        root=ROOT,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(
        f"[DEPRECATION] scripts/run_regression_only.py is compatibility entrypoint "
        f"and is planned to be retired on {DEPRECATION_DATE}; prefer scripts/regression_cli.py"
    )
    preflight = result.get("preflight", {})
    print(
        f"[OK] preflight old_selected={preflight.get('old_selected_count', 0)}, "
        f"new_selected={preflight.get('new_selected_count', 0)}, scope={result.get('scope', '')}"
    )
    if result.get("mode") == "DRY_RUN":
        print("[OK] dry-run finished, no batch created.")
        for warning in preflight.get("warnings", []):
            print(f"[WARN] {warning}")
        return 0

    print(f"[OK] regression done, batch_id={result['batch_id']}, batch_code={result['batch_code']}")
    print(f"[OK] indexed={result['indexed_count']}, stats={result['stats']}")
    print(f"[OK] report={result['report_path']}")
    _print_trace_id_lines("对比成功 trace_id:", result.get("compare_success_trace_ids", []))
    _print_trace_id_lines("对比失败 trace_id:", result.get("compare_failed_trace_ids", []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
