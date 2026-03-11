from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.result_utils import (  # noqa: E402
    is_success_result,
    render_trace_id_lines,
    split_trace_ids_by_compare_status,
)


class ResultUtilsTest(unittest.TestCase):
    def test_is_success_result(self):
        self.assertTrue(is_success_result({"compare_status": "SUCCESS", "diff_level": "SAME"}))
        self.assertTrue(is_success_result({"compare_status": "success", "diff_level": "normal"}))
        self.assertFalse(is_success_result({"compare_status": "FAILED", "diff_level": "SAME"}))
        self.assertFalse(is_success_result({"compare_status": "SUCCESS", "diff_level": "BLOCK"}))

    def test_split_trace_ids_by_compare_status(self):
        success_ids, failed_ids = split_trace_ids_by_compare_status(
            [
                {"pair_status": "MATCHED", "compare_status": "SUCCESS", "diff_level": "SAME", "old_trace_id": "S1", "new_trace_id": "S2"},
                {"pair_status": "MATCHED", "compare_status": "FAILED", "diff_level": "BLOCK", "old_trace_id": "F1", "new_trace_id": "F2"},
                {"pair_status": "ONLY_OLD", "compare_status": "SKIPPED", "old_trace_id": "X1", "new_trace_id": "X2"},
                {"pair_status": "MATCHED", "compare_status": "SUCCESS", "diff_level": "NORMAL", "old_trace_id": "S1", "new_trace_id": "S3"},
            ]
        )
        self.assertEqual(success_ids, ["S1", "S2", "S3"])
        self.assertEqual(failed_ids, ["F1", "F2"])

    def test_render_trace_id_lines(self):
        self.assertEqual(render_trace_id_lines([]), ["-"])
        self.assertEqual(render_trace_id_lines(["A"]), ["'A'"])
        self.assertEqual(render_trace_id_lines(["A", "B"]), ["'A',", "'B'"])
        self.assertEqual(render_trace_id_lines([" A ", "", "B"]), ["'A',", "'B'"])


if __name__ == "__main__":
    unittest.main()
