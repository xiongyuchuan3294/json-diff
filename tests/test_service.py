from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.service import _pick_latest_sample, run_regression, run_regression_by_trace_ids


class FakeDb:
    def __init__(self, index_rows: list[dict[str, Any]] | None = None, trace_rows: list[dict[str, Any]] | None = None):
        self.index_rows = index_rows or []
        self.trace_rows = trace_rows or []
        self.inserted_compare_rows: list[tuple[Any, ...]] = []
        self.batch_update_params: tuple[Any, ...] | None = None
        self._result_id = 0

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> int:
        if "`t_compare_result`" in sql and "INSERT INTO" in sql and params:
            self.inserted_compare_rows.append(params)
        if "`t_regression_batch`" in sql and "SET status=%s" in sql and params:
            self.batch_update_params = params
        return 1

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> int:
        return len(params)

    def query(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if "`t_request_info` req" in sql and "WHERE req.deleted = 0" in sql:
            return list(self.trace_rows)
        if "`t_request_compare_index` idx" in sql:
            return list(self.index_rows)
        if "`t_compare_rule`" in sql:
            return []
        return []

    def query_one(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        if "`t_compare_result`" in sql and "SELECT id" in sql:
            self._result_id += 1
            return {"id": self._result_id}
        return None


class PickLatestSampleTest(unittest.TestCase):
    def test_pick_latest_sample_by_end_time(self):
        rows = [
            {"request_info_id": 1, "request_end_time": "2026-03-11 10:00:01", "request_end_time_ms": 200},
            {"request_info_id": 2, "request_end_time": "2026-03-11 10:00:02", "request_end_time_ms": 100},
        ]
        latest = _pick_latest_sample(rows)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["request_info_id"], 2)

    def test_pick_latest_sample_tiebreaker(self):
        rows = [
            {"request_info_id": 10, "request_end_time": "2026-03-11 10:00:02", "request_end_time_ms": 100},
            {"request_info_id": 11, "request_end_time": "2026-03-11 10:00:02", "request_end_time_ms": 100},
        ]
        latest = _pick_latest_sample(rows)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["request_info_id"], 11)


class RegressionRuleBehaviorTest(unittest.TestCase):
    def test_only_single_side_fingerprint_not_written_as_failure(self):
        index_rows = [
            {
                "request_fingerprint": "FP_ONLY_OLD",
                "scenario_id": "old",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 1,
                "trace_id": "OLD_1",
                "status_code": 200,
                "response_body": '{"ok": true}',
                "request_end_time": "2026-03-11 10:00:01",
                "request_end_time_ms": 100,
            },
            {
                "request_fingerprint": "FP_MATCHED",
                "scenario_id": "old",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 2,
                "trace_id": "OLD_2",
                "status_code": 200,
                "response_body": '{"ok": true}',
                "request_end_time": "2026-03-11 10:00:01",
                "request_end_time_ms": 200,
            },
            {
                "request_fingerprint": "FP_MATCHED",
                "scenario_id": "new",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 3,
                "trace_id": "NEW_3",
                "status_code": 200,
                "response_body": '{"ok": true}',
                "request_end_time": "2026-03-11 10:00:02",
                "request_end_time_ms": 100,
            },
            {
                "request_fingerprint": "FP_ONLY_NEW",
                "scenario_id": "new",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 4,
                "trace_id": "NEW_4",
                "status_code": 200,
                "response_body": '{"ok": true}',
                "request_end_time": "2026-03-11 10:00:03",
                "request_end_time_ms": 100,
            },
        ]
        db = FakeDb(index_rows)

        stats = run_regression(db, batch_id=99, old_scenario_id="old", new_scenario_id="new")

        self.assertEqual(stats.get("matched_count", 0), 1)
        self.assertEqual(stats.get("same_count", 0), 1)
        self.assertEqual(stats.get("only_old_count", 0), 0)
        self.assertEqual(stats.get("only_new_count", 0), 0)
        self.assertEqual(len(db.inserted_compare_rows), 1)
        self.assertEqual(db.inserted_compare_rows[0][11], "MATCHED")
        self.assertIsNotNone(db.batch_update_params)
        self.assertEqual(db.batch_update_params[2], 1)

    def test_trace_mode_multi_rows_choose_latest_not_skip(self):
        trace_rows = [
            {
                "request_info_id": 10,
                "trace_id": "TRACE_OLD",
                "sysid": "aml-web",
                "scenario_id": "old",
                "method": "POST",
                "url": "http://demo/api",
                "normalized_path": "/api",
                "status_code": 200,
                "response_body": '{"v": 1}',
                "request_end_time": "2026-03-11 10:00:01",
                "request_end_time_ms": 100,
            },
            {
                "request_info_id": 11,
                "trace_id": "TRACE_OLD",
                "sysid": "aml-web",
                "scenario_id": "old",
                "method": "POST",
                "url": "http://demo/api",
                "normalized_path": "/api",
                "status_code": 200,
                "response_body": '{"v": 2}',
                "request_end_time": "2026-03-11 10:00:02",
                "request_end_time_ms": 100,
            },
            {
                "request_info_id": 21,
                "trace_id": "TRACE_NEW",
                "sysid": "aml-web",
                "scenario_id": "new",
                "method": "POST",
                "url": "http://demo/api",
                "normalized_path": "/api",
                "status_code": 200,
                "response_body": '{"v": 2}',
                "request_end_time": "2026-03-11 10:00:03",
                "request_end_time_ms": 100,
            },
        ]
        db = FakeDb(trace_rows=trace_rows)

        stats = run_regression_by_trace_ids(
            db,
            batch_id=100,
            old_scenario_id="old",
            new_scenario_id="new",
            old_trace_id="TRACE_OLD",
            new_trace_id="TRACE_NEW",
        )

        self.assertEqual(stats.get("matched_count", 0), 1)
        self.assertEqual(stats.get("same_count", 0), 1)
        self.assertEqual(len(db.inserted_compare_rows), 1)
        compare_row = db.inserted_compare_rows[0]
        self.assertEqual(compare_row[7], 11)
        self.assertEqual(compare_row[8], 21)
        self.assertEqual(compare_row[11], "MATCHED")

    def test_block_diff_is_marked_failed(self):
        index_rows = [
            {
                "request_fingerprint": "FP_BLOCK",
                "scenario_id": "old",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 31,
                "trace_id": "OLD_31",
                "status_code": 200,
                "response_body": '{"ok": true}',
                "request_end_time": "2026-03-11 10:00:01",
                "request_end_time_ms": 100,
            },
            {
                "request_fingerprint": "FP_BLOCK",
                "scenario_id": "new",
                "normalized_path": "/api/demo",
                "method": "POST",
                "sysid": "aml-web",
                "request_info_id": 32,
                "trace_id": "NEW_32",
                "status_code": 500,
                "response_body": '{"ok": false}',
                "request_end_time": "2026-03-11 10:00:02",
                "request_end_time_ms": 100,
            },
        ]
        db = FakeDb(index_rows=index_rows)

        stats = run_regression(db, batch_id=101, old_scenario_id="old", new_scenario_id="new")

        self.assertEqual(stats.get("matched_count", 0), 1)
        self.assertEqual(stats.get("block_count", 0), 1)
        self.assertEqual(len(db.inserted_compare_rows), 1)
        compare_row = db.inserted_compare_rows[0]
        self.assertEqual(compare_row[12], "FAILED")
        self.assertEqual(compare_row[13], "BLOCK")


if __name__ == "__main__":
    unittest.main()
