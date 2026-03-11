from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.regression_cli as cli  # noqa: E402


class ReplayCliTest(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["regression_cli.py", *argv]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_replay_validate_target_base_url_required(self):
        with patch.object(cli, "run_regression_job") as mock_run:
            code, _, err = self._run_main(
                [
                    "--replay",
                    "--replay-source-scenario-id",
                    "demo#old#1",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("--replay-target-base-url is required in replay mode", err)
        mock_run.assert_not_called()

    def test_replay_validate_target_base_url_scheme(self):
        with patch.object(cli, "run_regression_job") as mock_run:
            code, _, err = self._run_main(
                [
                    "--replay",
                    "--replay-target-base-url",
                    "ftp://example.com",
                    "--replay-source-scenario-id",
                    "demo#old#1",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("--replay-target-base-url must start with http:// or https://", err)
        mock_run.assert_not_called()

    def test_replay_validate_selector_exactly_one(self):
        cases = [
            (
                [
                    "--replay",
                    "--replay-target-base-url",
                    "http://example.com",
                ],
                "none-selector",
            ),
            (
                [
                    "--replay",
                    "--replay-target-base-url",
                    "http://example.com",
                    "--replay-source-scenario-id",
                    "demo#old#1",
                    "--replay-trace-ids",
                    "T001",
                ],
                "both-selector",
            ),
        ]

        for argv, _name in cases:
            with self.subTest(argv=argv):
                with patch.object(cli, "run_regression_job") as mock_run:
                    code, _, err = self._run_main(argv)
                self.assertEqual(code, 2)
                self.assertIn("exactly one replay selector is required", err)
                mock_run.assert_not_called()

    def test_replay_validate_numeric_args(self):
        cases = [
            (["--replay-speed-factor", "0"], "--replay-speed-factor must be > 0"),
            (["--replay-min-gap-ms", "-1"], "--replay-min-gap-ms must be >= 0"),
            (
                ["--replay-min-gap-ms", "10", "--replay-max-gap-ms", "9"],
                "--replay-max-gap-ms must be >= --replay-min-gap-ms",
            ),
            (["--replay-timeout-ms", "0"], "--replay-timeout-ms must be > 0"),
            (["--replay-retries", "-1"], "--replay-retries must be >= 0"),
        ]
        base = [
            "--replay",
            "--replay-target-base-url",
            "http://example.com",
            "--replay-source-scenario-id",
            "demo#old#1",
        ]

        for extra, expect in cases:
            with self.subTest(extra=extra):
                with patch.object(cli, "run_regression_job") as mock_run:
                    code, _, err = self._run_main([*base, *extra])
                self.assertEqual(code, 2)
                self.assertIn(expect, err)
                mock_run.assert_not_called()

    def test_replay_scenario_mode_passes_params_and_prints(self):
        fake_result = {
            "mode": "REPLAY_RUN",
            "scope": "REPLAY_DIFF:demo#old#1->demo#replay#1",
            "preflight": {"old_selected_count": 2, "new_selected_count": 2},
            "replay_preflight": {
                "mode": "REPLAY",
                "source_scenario_id": "demo#old#1",
                "source_total_count": 3,
                "selected_count": 2,
            },
            "replay": {
                "replay_batch_id": 100,
                "replay_code": "RPL_DEMO",
                "replay_scenario_id": "demo#replay#1",
                "stats": {"total_count": 2, "success_count": 2, "failed_count": 0},
            },
            "batch_id": 200,
            "batch_code": "REG_DEMO",
            "indexed_count": 4,
            "stats": {"matched_count": 2, "diff_count": 1},
            "report_path": "/tmp/report.md",
            "latest_report_path": "/tmp/latest.md",
            "compare_success_trace_ids": ["OLD_1", "NEW_1"],
            "compare_failed_trace_ids": [],
        }

        with patch.object(cli, "run_regression_job", return_value=fake_result) as mock_run:
            code, out, err = self._run_main(
                [
                    "--replay",
                    "--replay-target-base-url",
                    "http://example.com",
                    "--replay-source-scenario-id",
                    "demo#old#1",
                    "--batch-name",
                    "回放测试",
                    "--fuzzy",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("replay preflight source_selected=2, source_total=3", out)
        self.assertIn("replay done, replay_batch_id=100", out)
        self.assertIn("regression done, batch_id=200, batch_code=REG_DEMO", out)
        self.assertIn("'OLD_1',", out)
        self.assertIn("'NEW_1'", out)

        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertTrue(params.replay)
        self.assertEqual(params.replay_target_base_url, "http://example.com")
        self.assertEqual(params.replay_source_scenario_id, "demo#old#1")
        self.assertEqual(params.replay_trace_ids, "")
        self.assertTrue(params.fuzzy_match)
        self.assertEqual(params.batch_name, "回放测试")
        self.assertEqual(mock_run.call_args.kwargs.get("root"), cli.ROOT)

    def test_replay_trace_mode_passes_params(self):
        fake_result = {
            "mode": "REPLAY_RUN",
            "scope": "REPLAY_DIFF:demo#old#1->demo#replay#1",
            "preflight": {"old_selected_count": 1, "new_selected_count": 1},
            "replay_preflight": {
                "mode": "REPLAY",
                "source_scenario_id": "demo#old#1",
                "source_total_count": 1,
                "selected_count": 1,
            },
            "replay": {
                "replay_batch_id": 101,
                "replay_code": "RPL_TRACE",
                "replay_scenario_id": "demo#replay#1",
                "stats": {"total_count": 1, "success_count": 1, "failed_count": 0},
            },
            "batch_id": 201,
            "batch_code": "REG_TRACE",
            "indexed_count": 2,
            "stats": {"matched_count": 1, "diff_count": 1},
            "report_path": "/tmp/report.md",
            "latest_report_path": "",
            "compare_success_trace_ids": [],
            "compare_failed_trace_ids": [],
        }

        with patch.object(cli, "run_regression_job", return_value=fake_result) as mock_run:
            code, out, err = self._run_main(
                [
                    "--replay",
                    "--replay-target-base-url",
                    "https://example.com",
                    "--replay-trace-ids",
                    "T001,T002",
                    "--replay-speed-factor",
                    "2.0",
                    "--replay-min-gap-ms",
                    "10",
                    "--replay-max-gap-ms",
                    "20",
                    "--replay-timeout-ms",
                    "5000",
                    "--replay-retries",
                    "2",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("replay preflight source_selected=1, source_total=1", out)

        mock_run.assert_called_once()
        params = mock_run.call_args.args[0]
        self.assertTrue(params.replay)
        self.assertEqual(params.replay_source_scenario_id, "")
        self.assertEqual(params.replay_trace_ids, "T001,T002")
        self.assertEqual(params.replay_speed_factor, 2.0)
        self.assertEqual(params.replay_min_gap_ms, 10)
        self.assertEqual(params.replay_max_gap_ms, 20)
        self.assertEqual(params.replay_timeout_ms, 5000)
        self.assertEqual(params.replay_retries, 2)

    def test_replay_dry_run_prints_no_batch_created(self):
        fake_result = {
            "mode": "DRY_RUN",
            "scope": "REPLAY_SCENARIO:demo#old#1",
            "preflight": {
                "mode": "REPLAY",
                "source_scenario_id": "demo#old#1",
                "source_total_count": 2,
                "selected_count": 1,
                "warnings": ["source rows found but none matched api_paths filter"],
            },
        }
        with patch.object(cli, "run_regression_job", return_value=fake_result):
            code, out, err = self._run_main(
                [
                    "/todos",
                    "--replay",
                    "--replay-target-base-url",
                    "http://example.com",
                    "--replay-source-scenario-id",
                    "demo#old#1",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("dry-run finished, no batch created.", out)
        self.assertIn("[WARN] source rows found but none matched api_paths filter", out)


if __name__ == "__main__":
    unittest.main()
