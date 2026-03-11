from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.schema import init_schema


class FakeDb:
    def __init__(self) -> None:
        self.sql_path: Path | None = None

    def execute_sql_file(self, path: Path) -> None:
        self.sql_path = path


class SchemaInitTest(unittest.TestCase):
    def test_init_schema_uses_schema_sql_file(self):
        db = FakeDb()

        init_schema(db)  # type: ignore[arg-type]

        self.assertEqual(db.sql_path, Path("sql/schema_rrs_test_dev.sql"))

    def test_schema_sql_contains_all_core_tables(self):
        schema_file = ROOT / "sql" / "schema_rrs_test_dev.sql"
        self.assertTrue(schema_file.exists(), "schema_rrs_test_dev.sql should exist")
        sql_text = schema_file.read_text(encoding="utf-8")

        self.assertRegex(
            sql_text,
            r"CREATE DATABASE IF NOT EXISTS\s+`rrs_test_dev`",
        )

        required_tables = [
            "t_request_info",
            "t_request_compare_index",
            "t_regression_batch",
            "t_compare_rule",
            "t_compare_result",
            "t_compare_result_detail",
            "t_replay_batch",
            "t_replay_request",
        ]
        for table in required_tables:
            pattern = rf"CREATE TABLE IF NOT EXISTS\s+`rrs_test_dev`\.`{re.escape(table)}`"
            self.assertRegex(sql_text, pattern)

        self.assertNotIn("INSERT INTO", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
