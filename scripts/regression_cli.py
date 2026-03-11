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

from regression_demo.runner import RegressionJobParams, run_regression_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stable regression CLI.\n"
            "Scenario mode: api_paths + old_scenario_id + new_scenario_id\n"
            "Trace mode: --old-trace-id + --new-trace-id"
        )
    )
    parser.add_argument("api_paths", nargs="?", default="ALL", help="ALL/* or comma-separated api paths, e.g. /a,/b")
    parser.add_argument("old_scenario_id", nargs="?", default="", help="old scenario_id (required in scenario mode)")
    parser.add_argument("new_scenario_id", nargs="?", default="", help="new scenario_id (required in scenario mode)")
    parser.add_argument("--old-trace-id", default="", help="old trace_id for direct pair compare")
    parser.add_argument("--new-trace-id", default="", help="new trace_id for direct pair compare")
    parser.add_argument("--batch-code", default="", help="batch code, auto-generated when empty")
    parser.add_argument("--batch-name", default="接口回归任务", help="batch name")
    parser.add_argument("--biz-name", default="aml-web", help="biz name")
    parser.add_argument("--operator", default="codex", help="operator")
    parser.add_argument("--remark", default="", help="remark")
    parser.add_argument("--report-path", default="", help="report output path, default output/<batch_code>/测试报告.md")
    parser.add_argument("--dry-run", action="store_true", help="preflight only, no index/build/run")
    parser.add_argument("--fuzzy", action="store_true", help="use fuzzy api path match (prefix)")
    parser.add_argument("--json", action="store_true", help="print result in JSON")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> tuple[bool, str]:
    old_trace_id = (args.old_trace_id or "").strip()
    new_trace_id = (args.new_trace_id or "").strip()
    trace_mode = bool(old_trace_id or new_trace_id)

    if trace_mode and not (old_trace_id and new_trace_id):
        return False, "both --old-trace-id and --new-trace-id are required in trace mode"

    if not trace_mode:
        if not (args.old_scenario_id or "").strip() or not (args.new_scenario_id or "").strip():
            return False, "old_scenario_id and new_scenario_id are required in scenario mode"

    return True, ""


def _print_trace_id_lines(title: str, trace_ids: list[str]) -> None:
    print(title)
    last_index = len(trace_ids) - 1
    for index, trace_id in enumerate(trace_ids):
        suffix = "," if index < last_index else ""
        print(f"'{trace_id}'{suffix}")


def main() -> int:
    args = parse_args()
    ok, reason = _validate_args(args)
    if not ok:
        print(f"[ERROR] {reason}", file=sys.stderr)
        return 2

    try:
        result = run_regression_job(
            RegressionJobParams(
                api_paths_arg=args.api_paths,
                old_scenario_id=args.old_scenario_id,
                new_scenario_id=args.new_scenario_id,
                old_trace_id=args.old_trace_id,
                new_trace_id=args.new_trace_id,
                batch_code=args.batch_code,
                batch_name=args.batch_name,
                biz_name=args.biz_name,
                operator=args.operator,
                remark=args.remark,
                report_path=args.report_path or None,
                dry_run=args.dry_run,
                fuzzy_match=args.fuzzy,
            ),
            root=ROOT,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    preflight = result.get("preflight", {})
    print(
        f"[OK] preflight old_selected={preflight.get('old_selected_count', 0)}, "
        f"new_selected={preflight.get('new_selected_count', 0)}, scope={result.get('scope', '')}"
    )
    if preflight.get("old_trace_id") or preflight.get("new_trace_id"):
        print(
            f"[OK] trace_pair old_trace_id={preflight.get('old_trace_id', '')}, "
            f"new_trace_id={preflight.get('new_trace_id', '')}"
        )

    if result.get("mode") == "DRY_RUN":
        print("[OK] dry-run finished, no batch created.")
        warnings = preflight.get("warnings", [])
        for warning in warnings:
            print(f"[WARN] {warning}")
        return 0

    print(f"[OK] regression done, batch_id={result['batch_id']}, batch_code={result['batch_code']}")
    print(f"[OK] indexed={result['indexed_count']}, stats={result['stats']}")
    print(f"[OK] report={result['report_path']}")
    if result.get("latest_report_path"):
        print(f"[OK] latest_report={result['latest_report_path']}")

    _print_trace_id_lines("对比成功 trace_id:", result.get("compare_success_trace_ids", []))
    _print_trace_id_lines("对比失败 trace_id:", result.get("compare_failed_trace_ids", []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
