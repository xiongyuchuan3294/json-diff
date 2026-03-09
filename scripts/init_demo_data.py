#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.config import TARGET_SCHEMA, get_demo_db_config, with_database
from regression_demo.db import DbClient
from regression_demo.schema import init_schema, truncate_demo_tables
from regression_demo.seed_data import seed_request_info, seed_rules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化演示数据（DEMO专用：建表、清表、造数、写规则）")
    parser.add_argument("--no-truncate", action="store_true", help="不执行 TRUNCATE")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_db = DbClient(get_demo_db_config())
    init_schema(base_db)

    target_db = DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))
    if not args.no_truncate:
        truncate_demo_tables(target_db)
    seed_request_info(target_db)
    seed_rules(target_db)

    row = target_db.query_one(f"SELECT COUNT(*) AS cnt FROM `{TARGET_SCHEMA}`.`t_request_info`")
    count = int(row["cnt"]) if row else 0
    print(f"[OK] demo data initialized in schema={TARGET_SCHEMA}, request_info_count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
