from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.regression_mcp_server as mcp_server  # noqa: E402


class McpServerToolTest(unittest.TestCase):
    def test_run_regression_by_scenario_success(self):
        with patch.object(
            mcp_server,
            "run_regression_job",
            return_value={"mode": "RUN", "batch_id": 101, "batch_code": "REG_X"},
        ) as mock_run:
            result = mcp_server.run_regression_by_scenario(
                old_scenario_id="demo#old#1",
                new_scenario_id="demo#new#1",
                api_paths="/api/a",
                fuzzy=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["batch_id"], 101)
        self.assertEqual(result["batch_code"], "REG_X")
        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertEqual(params.old_scenario_id, "demo#old#1")
        self.assertEqual(params.new_scenario_id, "demo#new#1")
        self.assertEqual(params.api_paths_arg, "/api/a")
        self.assertTrue(params.fuzzy_match)

    def test_run_regression_by_scenario_missing_inputs(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.run_regression_by_scenario(
                old_scenario_id="",
                new_scenario_id="demo#new#1",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("old_scenario_id and new_scenario_id are required", result["message"])
        mock_run.assert_not_called()

    def test_run_regression_by_scenario_and_api_requires_api_path(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.run_regression_by_scenario_and_api(
                old_scenario_id="demo#old#1",
                new_scenario_id="demo#new#1",
                api_path="",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("api_path is required", result["message"])
        mock_run.assert_not_called()

    def test_run_regression_by_scenario_and_api_success(self):
        with patch.object(
            mcp_server,
            "run_regression_job",
            return_value={"mode": "RUN", "batch_id": 102, "batch_code": "REG_PATH"},
        ) as mock_run:
            result = mcp_server.run_regression_by_scenario_and_api(
                old_scenario_id="demo#old#1",
                new_scenario_id="demo#new#1",
                api_path="/api/a",
                fuzzy=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["batch_id"], 102)
        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertEqual(params.api_paths_arg, "/api/a")
        self.assertTrue(params.fuzzy_match)

    def test_run_regression_by_trace_pair_requires_both_ids(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.run_regression_by_trace_pair(old_trace_id="OLD_1", new_trace_id="")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("old_trace_id and new_trace_id are required", result["message"])
        mock_run.assert_not_called()

    def test_run_job_exception_is_wrapped(self):
        with patch.object(mcp_server, "run_regression_job", side_effect=ValueError("boom")):
            result = mcp_server.run_regression_by_scenario(
                old_scenario_id="demo#old#1",
                new_scenario_id="demo#new#1",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "JOB_EXECUTION_FAILED")
        self.assertIn("boom", result["message"])

    def test_replay_and_diff_by_scenario_validates_url(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.replay_and_diff_by_scenario(
                source_scenario_id="demo#old#1",
                target_base_url="ftp://invalid",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("must start with http:// or https://", result["message"])
        mock_run.assert_not_called()

    def test_replay_and_diff_by_scenario_and_api_requires_api_path(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.replay_and_diff_by_scenario_and_api(
                source_scenario_id="demo#old#1",
                target_base_url="http://example.com",
                api_path="",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("api_path is required", result["message"])
        mock_run.assert_not_called()

    def test_replay_and_diff_by_scenario_and_api_success(self):
        with patch.object(
            mcp_server,
            "run_regression_job",
            return_value={"mode": "REPLAY_RUN", "batch_id": 401, "replay_batch_id": 501},
        ) as mock_run:
            result = mcp_server.replay_and_diff_by_scenario_and_api(
                source_scenario_id="demo#old#1",
                target_base_url="http://example.com",
                api_path="/api/a",
                replay_speed_factor=1.5,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["batch_id"], 401)
        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertTrue(params.replay)
        self.assertEqual(params.api_paths_arg, "/api/a")
        self.assertEqual(params.replay_source_scenario_id, "demo#old#1")
        self.assertEqual(params.replay_speed_factor, 1.5)

    def test_replay_and_diff_by_trace_ids_normalizes_list_input(self):
        with patch.object(
            mcp_server,
            "run_regression_job",
            return_value={"mode": "REPLAY_RUN", "batch_id": 201, "replay_batch_id": 301},
        ) as mock_run:
            result = mcp_server.replay_and_diff_by_trace_ids(
                trace_ids=["T001", "T002", "T001"],
                target_base_url="http://example.com",
                replay_speed_factor=2.0,
                replay_min_gap_ms=10,
                replay_max_gap_ms=20,
                replay_timeout_ms=5000,
                replay_retries=2,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["batch_id"], 201)
        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertTrue(params.replay)
        self.assertEqual(params.replay_trace_ids, "T001,T002")
        self.assertEqual(params.replay_target_base_url, "http://example.com")
        self.assertEqual(params.replay_speed_factor, 2.0)
        self.assertEqual(params.replay_min_gap_ms, 10)
        self.assertEqual(params.replay_max_gap_ms, 20)
        self.assertEqual(params.replay_timeout_ms, 5000)
        self.assertEqual(params.replay_retries, 2)

    def test_replay_and_diff_by_trace_ids_requires_non_empty_trace(self):
        with patch.object(mcp_server, "run_regression_job") as mock_run:
            result = mcp_server.replay_and_diff_by_trace_ids(trace_ids="  , ", target_base_url="http://example.com")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertIn("trace_ids is required", result["message"])
        mock_run.assert_not_called()

    def test_list_scenarios_returns_items(self):
        db = MagicMock()
        db.query.return_value = [
            {
                "scenario_id": "demo#old#1",
                "request_count": 12,
                "first_start_time": "2026-03-11 10:00:00",
                "last_start_time": "2026-03-11 10:05:00",
            }
        ]
        with patch.object(mcp_server, "_target_db", return_value=db):
            result = mcp_server.list_scenarios(limit=10, keyword="demo")

        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["scenario_id"], "demo#old#1")

    def test_list_api_paths_groups_and_sorts(self):
        db = MagicMock()
        db.query.return_value = [
            {"url": "http://host/a?id=1"},
            {"url": "http://host/a?id=2"},
            {"url": "http://host/b"},
        ]
        with patch.object(mcp_server, "_target_db", return_value=db):
            result = mcp_server.list_api_paths(scenario_id="demo#old#1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["api_path"], "/a")
        self.assertEqual(result["items"][0]["request_count"], 2)

    def test_list_recent_batches_rejects_invalid_mode(self):
        with patch.object(mcp_server, "_target_db") as mock_db:
            result = mcp_server.list_recent_batches(mode="WRONG")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        mock_db.assert_not_called()

    def test_get_batch_report_not_found(self):
        db = MagicMock()
        db.query_one.return_value = None
        with patch.object(mcp_server, "_target_db", return_value=db):
            result = mcp_server.get_batch_report(batch_code="NOT_EXISTS")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "NOT_FOUND")

    def test_get_batch_report_with_results(self):
        db = MagicMock()
        db.query_one.return_value = {
            "id": 500,
            "batch_code": "REG_500",
            "status": "SUCCESS",
        }
        db.query.side_effect = [
            [{"compare_status": "SUCCESS", "diff_level": "SAME", "cnt": 2}],
            [
                {
                    "id": 1,
                    "pair_status": "MATCHED",
                    "compare_status": "SUCCESS",
                    "diff_level": "SAME",
                    "api_path": "/a",
                    "old_trace_id": "OLD_1",
                    "new_trace_id": "NEW_1",
                    "summary": "ok",
                }
            ],
        ]
        with patch.object(mcp_server, "_target_db", return_value=db):
            result = mcp_server.get_batch_report(batch_id=500, include_results=True, result_limit=5)

        self.assertTrue(result["ok"])
        self.assertEqual(result["batch"]["batch_code"], "REG_500")
        self.assertEqual(len(result["summary"]), 1)
        self.assertEqual(len(result["results"]), 1)


if __name__ == "__main__":
    unittest.main()
