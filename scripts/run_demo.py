#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.config import (
    BATCH_CODE,
    BATCH_NAME,
    NEW_SCENARIO_ID,
    OLD_SCENARIO_ID,
    TARGET_SCHEMA,
    get_demo_db_config,
    with_database,
)
from regression_demo.db import DbClient
from regression_demo.runner import RegressionJobParams, run_regression_job
from regression_demo.schema import init_schema, truncate_demo_tables
from regression_demo.seed_data import seed_request_info, seed_rules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键演示：清表 + 造数 + 回归比对")
    parser.add_argument(
        "--api-path",
        default="/aml/wst/custTransInfo",
        help="接口 path（演示模式默认只跑 /aml/wst/custTransInfo）",
    )
    parser.add_argument("--report-path", default="", help="报告输出路径，默认 output/<batch_code>/测试报告.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    demo_db = DbClient(get_demo_db_config())
    init_schema(demo_db)

    target_db = DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))
    truncate_demo_tables(target_db)
    seed_request_info(target_db)
    seed_rules(target_db)

    result = run_regression_job(
        RegressionJobParams(
            api_paths_arg=args.api_path,
            old_scenario_id=OLD_SCENARIO_ID,
            new_scenario_id=NEW_SCENARIO_ID,
            batch_code=BATCH_CODE,
            batch_name=BATCH_NAME,
            biz_name="aml-web",
            operator="codex",
            remark="run_demo one-shot",
            env_tag="demo",
            report_path=args.report_path or None,
            write_latest=True,
        ),
        root=ROOT,
    )
    print(f"[OK] demo run finished, batch_code={result['batch_code']}, indexed={result['indexed_count']}, stats={result['stats']}")
    print(f"[OK] report written: {result['report_path']}")
    print("[TIP] production use: scripts/init_schema_only.py + scripts/regression_cli.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
