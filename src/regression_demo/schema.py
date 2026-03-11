from __future__ import annotations

from pathlib import Path

from .config import TARGET_SCHEMA
from .db import DbClient


def init_schema(db: DbClient) -> None:
    db.execute_sql_file(Path("sql/schema_rrs_test_dev.sql"))


def truncate_demo_tables(db: DbClient) -> None:
    tables = [
        "t_replay_request",
        "t_replay_batch",
        "t_compare_result_detail",
        "t_compare_result",
        "t_compare_rule",
        "t_regression_batch",
        "t_request_compare_index",
        "t_request_info",
    ]
    for table in tables:
        db.execute(f"TRUNCATE TABLE `{TARGET_SCHEMA}`.`{table}`")
