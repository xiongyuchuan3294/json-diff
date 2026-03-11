from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.replay import (  # noqa: E402
    ReplayHttpResult,
    ReplayJobParams,
    build_replay_scenario_id,
    calculate_planned_gap_ms,
    collect_replay_preflight,
    load_replay_source_rows,
    normalize_replay_trace_ids_arg,
    rewrite_url,
    run_replay_job,
    sanitize_headers,
    validate_replay_runtime_options,
)


class FakeReplayDb:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.replay_batch_id = 10
        self.next_request_id = 1000
        self.inserted_replay_requests: list[tuple[Any, ...]] = []
        self.inserted_replay_infos: list[tuple[Any, ...]] = []
        self.trace_to_request_id: dict[str, int] = {}

    def query(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        sql_text = sql.lower()
        if "from `rrs_test_dev`.`t_request_info`" in sql_text and "scenario_id = %s" in sql_text:
            scenario_id = str((params or [""])[0])
            return [row for row in self.rows if row.get("scenario_id") == scenario_id]
        if "from `rrs_test_dev`.`t_request_info`" in sql_text and "trace_id in" in sql_text:
            trace_ids = set(str(item) for item in (params or ()))
            return [row for row in self.rows if str(row.get("trace_id")) in trace_ids]
        return []

    def query_one(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        sql_text = sql.lower()
        if "from `rrs_test_dev`.`t_replay_batch`" in sql_text and "where replay_code" in sql_text:
            return {"id": self.replay_batch_id}
        if "from `rrs_test_dev`.`t_request_info`" in sql_text and "where trace_id" in sql_text:
            trace_id = str((params or [""])[0])
            request_id = self.trace_to_request_id.get(trace_id)
            if request_id is None:
                return None
            return {"id": request_id}
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> int:
        sql_text = sql.lower()
        if "insert into `rrs_test_dev`.`t_request_info`" in sql_text and params:
            self.next_request_id += 1
            trace_id = str(params[0])
            self.trace_to_request_id[trace_id] = self.next_request_id
            self.inserted_replay_infos.append(tuple(params))
            return 1
        if "insert into `rrs_test_dev`.`t_replay_request`" in sql_text and params:
            self.inserted_replay_requests.append(tuple(params))
            return 1
        return 1


class ReplayHelperTest(unittest.TestCase):
    def test_normalize_replay_trace_ids_arg(self):
        self.assertEqual(normalize_replay_trace_ids_arg(""), [])
        self.assertEqual(normalize_replay_trace_ids_arg(" t1 , t2, t1 "), ["t1", "t2"])

    def test_build_replay_scenario_id_uses_microsecond_timestamp(self):
        value1 = build_replay_scenario_id("demo#old#1")
        time.sleep(0.001)
        value2 = build_replay_scenario_id("demo#old#1")
        self.assertRegex(value1, r"^demo#replay#\d{8}_\d{6}_\d{6}$")
        self.assertNotEqual(value1, value2)

    def test_rewrite_url_keeps_source_path_and_query(self):
        rewritten = rewrite_url("https://jsonplaceholder.typicode.com", "http://record.local/posts/1?a=1")
        self.assertEqual(rewritten, "https://jsonplaceholder.typicode.com/posts/1?a=1")

        rewritten_with_prefix = rewrite_url("https://demo.example.com/prefix", "http://record.local/api/v1/user?id=2")
        self.assertEqual(rewritten_with_prefix, "https://demo.example.com/prefix/api/v1/user?id=2")

    def test_sanitize_headers_removes_hop_by_hop(self):
        cleaned = sanitize_headers(
            {
                "Host": "record.local",
                "Content-Length": "100",
                "Connection": "keep-alive",
                "Accept": "application/json",
                "X-Request-Id": "abc",
            }
        )
        self.assertNotIn("Host", cleaned)
        self.assertNotIn("Content-Length", cleaned)
        self.assertNotIn("Connection", cleaned)
        self.assertEqual(cleaned["Accept"], "application/json")
        self.assertEqual(cleaned["X-Request-Id"], "abc")

    def test_calculate_planned_gap_ms(self):
        self.assertEqual(
            calculate_planned_gap_ms(
                previous_start_ms=None,
                current_start_ms=1000,
                speed_factor=1.0,
                min_gap_ms=300,
                max_gap_ms=3000,
            ),
            0,
        )

    def test_validate_replay_runtime_options(self):
        self.assertIsNone(
            validate_replay_runtime_options(
                target_base_url="https://example.com",
                replay_speed_factor=1.0,
                replay_min_gap_ms=0,
                replay_max_gap_ms=1000,
                replay_timeout_ms=1000,
                replay_retries=0,
            )
        )

        invalid_cases = [
            (
                {
                    "target_base_url": "",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": 0,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 1000,
                    "replay_retries": 0,
                },
                "TARGET_BASE_URL_REQUIRED",
            ),
            (
                {
                    "target_base_url": "ftp://example.com",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": 0,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 1000,
                    "replay_retries": 0,
                },
                "TARGET_BASE_URL_SCHEME",
            ),
            (
                {
                    "target_base_url": "http://example.com",
                    "replay_speed_factor": 0,
                    "replay_min_gap_ms": 0,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 1000,
                    "replay_retries": 0,
                },
                "SPEED_FACTOR_INVALID",
            ),
            (
                {
                    "target_base_url": "http://example.com",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": -1,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 1000,
                    "replay_retries": 0,
                },
                "MIN_GAP_INVALID",
            ),
            (
                {
                    "target_base_url": "http://example.com",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": 1000,
                    "replay_max_gap_ms": 999,
                    "replay_timeout_ms": 1000,
                    "replay_retries": 0,
                },
                "MAX_GAP_INVALID",
            ),
            (
                {
                    "target_base_url": "http://example.com",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": 0,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 0,
                    "replay_retries": 0,
                },
                "TIMEOUT_INVALID",
            ),
            (
                {
                    "target_base_url": "http://example.com",
                    "replay_speed_factor": 1.0,
                    "replay_min_gap_ms": 0,
                    "replay_max_gap_ms": 1000,
                    "replay_timeout_ms": 1000,
                    "replay_retries": -1,
                },
                "RETRIES_INVALID",
            ),
        ]
        for kwargs, expect_code in invalid_cases:
            with self.subTest(expect_code=expect_code):
                result = validate_replay_runtime_options(**kwargs)
                self.assertIsNotNone(result)
                self.assertEqual(result.code, expect_code)
        self.assertEqual(
            calculate_planned_gap_ms(
                previous_start_ms=1000,
                current_start_ms=1900,
                speed_factor=2.0,
                min_gap_ms=300,
                max_gap_ms=3000,
            ),
            450,
        )
        self.assertEqual(
            calculate_planned_gap_ms(
                previous_start_ms=1000,
                current_start_ms=1100,
                speed_factor=1.0,
                min_gap_ms=300,
                max_gap_ms=3000,
            ),
            300,
        )


class ReplayFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "id": 2,
                "trace_id": "SRC_2",
                "sysid": "aml-web",
                "client_ip": "127.0.0.1",
                "url": "http://record.local/api/demo/b?x=2",
                "method": "GET",
                "headers": '{"Host":"record.local","Accept":"application/json"}',
                "query_params": '{"x":"2"}',
                "request_body": "",
                "page_url": "http://record.local/page",
                "scenario_id": "demo#old#1",
                "start_time": "2026-03-11 10:00:02",
                "start_time_ms": 200,
                "trace_stack_md5": "stack2",
            },
            {
                "id": 1,
                "trace_id": "SRC_1",
                "sysid": "aml-web",
                "client_ip": "127.0.0.1",
                "url": "http://record.local/api/demo/a?x=1",
                "method": "GET",
                "headers": '{"Host":"record.local","Accept":"application/json"}',
                "query_params": '{"x":"1"}',
                "request_body": "",
                "page_url": "http://record.local/page",
                "scenario_id": "demo#old#1",
                "start_time": "2026-03-11 10:00:01",
                "start_time_ms": 100,
                "trace_stack_md5": "stack1",
            },
        ]

    def test_load_replay_source_rows_by_trace_ids_requires_single_scenario(self):
        mixed = list(self.rows)
        mixed[1] = dict(mixed[1], scenario_id="demo#old#2")
        db = FakeReplayDb(mixed)

        with self.assertRaisesRegex(ValueError, "exactly one source scenario_id"):
            load_replay_source_rows(db, trace_ids=["SRC_1", "SRC_2"])

    def test_collect_replay_preflight_with_api_filter(self):
        db = FakeReplayDb(self.rows)
        preflight = collect_replay_preflight(
            db,
            source_scenario_id="demo#old#1",
            api_paths=["/api/demo/a"],
            fuzzy_match=False,
        )
        self.assertEqual(preflight["source_total_count"], 2)
        self.assertEqual(preflight["selected_count"], 1)
        self.assertEqual(preflight["source_scenario_id"], "demo#old#1")

    def test_run_replay_job_continue_on_failure(self):
        db = FakeReplayDb(self.rows)
        request_results = [
            ReplayHttpResult(
                status_code=599,
                response_body='{"error":"timeout"}',
                duration_ms=101,
                request_start_time=datetime(2026, 3, 11, 11, 0, 0),
                request_end_time=datetime(2026, 3, 11, 11, 0, 0) + timedelta(milliseconds=101),
                error_message="timeout",
            ),
            ReplayHttpResult(
                status_code=200,
                response_body='{"ok":true}',
                duration_ms=55,
                request_start_time=datetime(2026, 3, 11, 11, 0, 1),
                request_end_time=datetime(2026, 3, 11, 11, 0, 1) + timedelta(milliseconds=55),
                error_message="",
            ),
        ]
        called_urls: list[str] = []
        sleep_calls: list[float] = []

        def fake_request_func(
            method: str,
            url: str,
            headers: dict[str, str],
            body_text: str,
            timeout_ms: int,
            retries: int,
        ) -> ReplayHttpResult:
            called_urls.append(url)
            return request_results[len(called_urls) - 1]

        result = run_replay_job(
            db,
            ReplayJobParams(
                target_base_url="https://jsonplaceholder.typicode.com",
                source_scenario_id="demo#old#1",
                speed_factor=1.0,
                min_gap_ms=300,
                max_gap_ms=3000,
            ),
            request_func=fake_request_func,
            sleep_func=lambda seconds: sleep_calls.append(seconds),
        )

        self.assertEqual(result["stats"]["total_count"], 2)
        self.assertEqual(result["stats"]["failed_count"], 1)
        self.assertEqual(result["stats"]["success_count"], 1)
        self.assertEqual(len(db.inserted_replay_requests), 2)
        self.assertEqual(db.inserted_replay_requests[0][14], "FAILED")
        self.assertEqual(db.inserted_replay_requests[1][14], "SUCCESS")
        self.assertEqual(called_urls[0], "https://jsonplaceholder.typicode.com/api/demo/a?x=1")
        self.assertEqual(called_urls[1], "https://jsonplaceholder.typicode.com/api/demo/b?x=2")
        self.assertTrue(len(sleep_calls) >= 1)


if __name__ == "__main__":
    unittest.main()
