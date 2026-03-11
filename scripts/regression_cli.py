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

from regression_demo.replay import validate_replay_runtime_options
from regression_demo.result_utils import render_trace_id_lines
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
    parser.add_argument("--replay", action="store_true", help="enable replay then auto diff")
    parser.add_argument("--replay-target-base-url", default="", help="replay target base url, e.g. https://host")
    parser.add_argument("--replay-source-scenario-id", default="", help="replay selector: source scenario_id")
    parser.add_argument("--replay-trace-ids", default="", help="replay selector: comma-separated trace_ids")
    parser.add_argument("--replay-speed-factor", type=float, default=1.0, help="replay speed factor, default 1.0")
    parser.add_argument("--replay-min-gap-ms", type=int, default=300, help="replay min gap ms, default 300")
    parser.add_argument("--replay-max-gap-ms", type=int, default=3000, help="replay max gap ms, default 3000")
    parser.add_argument("--replay-timeout-ms", type=int, default=10000, help="replay request timeout ms, default 10000")
    parser.add_argument("--replay-retries", type=int, default=1, help="replay retries, default 1")
    parser.add_argument("--replay-code", default="", help="replay batch code, auto-generated when empty")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> tuple[bool, str]:
    if args.replay:
        source_scenario_id = (args.replay_source_scenario_id or "").strip()
        replay_trace_ids = [item.strip() for item in (args.replay_trace_ids or "").split(",") if item.strip()]
        selector_count = int(bool(source_scenario_id)) + int(bool(replay_trace_ids))

        if selector_count != 1:
            return False, "exactly one replay selector is required: --replay-source-scenario-id or --replay-trace-ids"

        replay_error = validate_replay_runtime_options(
            target_base_url=args.replay_target_base_url,
            replay_speed_factor=args.replay_speed_factor,
            replay_min_gap_ms=args.replay_min_gap_ms,
            replay_max_gap_ms=args.replay_max_gap_ms,
            replay_timeout_ms=args.replay_timeout_ms,
            replay_retries=args.replay_retries,
        )
        if replay_error is not None:
            replay_error_message_map = {
                "TARGET_BASE_URL_REQUIRED": "--replay-target-base-url is required in replay mode",
                "TARGET_BASE_URL_SCHEME": "--replay-target-base-url must start with http:// or https://",
                "SPEED_FACTOR_INVALID": "--replay-speed-factor must be > 0",
                "MIN_GAP_INVALID": "--replay-min-gap-ms must be >= 0",
                "MAX_GAP_INVALID": "--replay-max-gap-ms must be >= --replay-min-gap-ms",
                "TIMEOUT_INVALID": "--replay-timeout-ms must be > 0",
                "RETRIES_INVALID": "--replay-retries must be >= 0",
            }
            return False, replay_error_message_map.get(replay_error.code, replay_error.message)
        return True, ""

    old_trace_id = (args.old_trace_id or "").strip()
    new_trace_id = (args.new_trace_id or "").strip()
    trace_mode = bool(old_trace_id or new_trace_id)

    if trace_mode and not (old_trace_id and new_trace_id):
        return False, "both --old-trace-id and --new-trace-id are required in trace mode"

    if not trace_mode:
        if not (args.old_scenario_id or "").strip() or not (args.new_scenario_id or "").strip():
            return False, "old_scenario_id and new_scenario_id are required in scenario mode"

    return True, ""


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
                replay=args.replay,
                replay_target_base_url=args.replay_target_base_url,
                replay_source_scenario_id=args.replay_source_scenario_id,
                replay_trace_ids=args.replay_trace_ids,
                replay_speed_factor=args.replay_speed_factor,
                replay_min_gap_ms=args.replay_min_gap_ms,
                replay_max_gap_ms=args.replay_max_gap_ms,
                replay_timeout_ms=args.replay_timeout_ms,
                replay_retries=args.replay_retries,
                replay_code=args.replay_code,
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
    replay_preflight = result.get("replay_preflight") or preflight
    if args.replay or str(preflight.get("mode") or "").upper() == "REPLAY":
        print(
            f"[OK] replay preflight source_selected={replay_preflight.get('selected_count', 0)}, "
            f"source_total={replay_preflight.get('source_total_count', 0)}, "
            f"source_scenario_id={replay_preflight.get('source_scenario_id', '')}, scope={result.get('scope', '')}"
        )
    else:
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

    replay_info = result.get("replay") or {}
    if replay_info:
        print(
            f"[OK] replay done, replay_batch_id={replay_info.get('replay_batch_id')}, "
            f"replay_code={replay_info.get('replay_code')}, replay_scenario_id={replay_info.get('replay_scenario_id')}"
        )
        print(f"[OK] replay_stats={replay_info.get('stats', {})}")

    print(f"[OK] regression done, batch_id={result['batch_id']}, batch_code={result['batch_code']}")
    print(f"[OK] indexed={result['indexed_count']}, stats={result['stats']}")
    print(f"[OK] report={result['report_path']}")
    if result.get("latest_report_path"):
        print(f"[OK] latest_report={result['latest_report_path']}")

    print("对比成功 trace_id:")
    for line in render_trace_id_lines(result.get("compare_success_trace_ids", [])):
        print(line)
    print("对比失败 trace_id:")
    for line in render_trace_id_lines(result.get("compare_failed_trace_ids", [])):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
