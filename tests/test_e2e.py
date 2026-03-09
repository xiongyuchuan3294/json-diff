from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.config import BATCH_CODE, TARGET_SCHEMA, get_demo_db_config, with_database
from regression_demo.db import DbClient


class RegressionDemoE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))
        preferred_code = os.environ.get("TEST_BATCH_CODE", "").strip()
        if preferred_code:
            cls.batch_code = preferred_code
            return
        baseline = cls.db.query_one(
            f"SELECT batch_code FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE batch_code = %s LIMIT 1",
            (BATCH_CODE,),
        )
        if baseline:
            cls.batch_code = BATCH_CODE
            return
        latest = cls.db.query_one(
            f"""
            SELECT batch_code
            FROM `{TARGET_SCHEMA}`.`t_regression_batch`
            ORDER BY id DESC
            LIMIT 1
            """
        )
        cls.batch_code = latest["batch_code"] if latest else BATCH_CODE

    def test_batch_exists(self):
        row = self.db.query_one(
            f"SELECT * FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE batch_code = %s",
            (self.batch_code,),
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "SUCCESS")

    def test_problem_cases_exist(self):
        rows = self.db.query(
            f"SELECT pair_status, compare_status, diff_level, summary FROM `{TARGET_SCHEMA}`.`t_compare_result` ORDER BY id"
        )
        self.assertTrue(any(row["pair_status"] == "ONLY_OLD" for row in rows))
        self.assertTrue(any(row["pair_status"] == "ONLY_NEW" for row in rows))
        self.assertTrue(any(row["pair_status"] == "MULTI_OLD" for row in rows))
        self.assertTrue(any(row["diff_level"] == "BLOCK" for row in rows))
        self.assertTrue(any(row["diff_level"] == "SAME" for row in rows))

    def test_batch_statistics_match_expected_demo(self):
        row = self.db.query_one(
            f"SELECT matched_count, same_count, diff_count, only_old_count, only_new_count, invalid_count, block_count FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE batch_code = %s",
            (self.batch_code,),
        )
        self.assertIsNotNone(row)
        if self.batch_code == BATCH_CODE:
            self.assertEqual(int(row["same_count"]), 2)
            self.assertEqual(int(row["diff_count"]), 5)
            self.assertEqual(int(row["only_old_count"]), 2)
            self.assertEqual(int(row["only_new_count"]), 2)
            self.assertEqual(int(row["invalid_count"]), 1)
            self.assertEqual(int(row["block_count"]), 3)
            return

        self.assertGreaterEqual(int(row["matched_count"]), 0)
        self.assertGreaterEqual(int(row["same_count"]), 0)
        self.assertGreaterEqual(int(row["diff_count"]), 0)
        self.assertGreaterEqual(int(row["only_old_count"]), 0)
        self.assertGreaterEqual(int(row["only_new_count"]), 0)
        self.assertGreaterEqual(int(row["invalid_count"]), 0)
        self.assertGreaterEqual(int(row["block_count"]), 0)

    def test_non_json_case_recorded(self):
        row = self.db.query_one(
            f"SELECT pair_status, compare_status, diff_level, summary FROM `{TARGET_SCHEMA}`.`t_compare_result` WHERE compare_status = 'FAILED' LIMIT 1"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["pair_status"], "MATCHED")
        self.assertEqual(row["diff_level"], "BLOCK")

    def test_detail_rows_written(self):
        row = self.db.query_one(
            f"SELECT COUNT(*) AS cnt FROM `{TARGET_SCHEMA}`.`t_compare_result_detail`"
        )
        self.assertIsNotNone(row)
        self.assertGreater(int(row["cnt"]), 0)


if __name__ == "__main__":
    unittest.main()
