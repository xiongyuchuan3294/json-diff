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
        description="稳定回归入口（3个必填参数）：api_paths(ALL或逗号分隔), old_scenario_id, new_scenario_id"
    )
    parser.add_argument("api_paths", help="接口范围：ALL/* 表示全接口，或 '/a,/b,/c' 形式")
    parser.add_argument("old_scenario_id", help="旧版本 scenario_id")
    parser.add_argument("new_scenario_id", help="新版本 scenario_id")
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
    result = run_regression_job(
        RegressionJobParams(
            api_paths_arg=args.api_paths,
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

    preflight = result.get("preflight", {})
    print(
        f"[OK] preflight old_selected={preflight.get('old_selected_count', 0)}, "
        f"new_selected={preflight.get('new_selected_count', 0)}, scope={result.get('scope', '')}"
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
