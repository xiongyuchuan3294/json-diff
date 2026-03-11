from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.runner import (
    default_batch_code,
    has_trace_pair,
    normalize_api_paths,
    normalize_trace_id,
    split_trace_ids_by_compare_status,
)


class RunnerHelperTest(unittest.TestCase):
    def test_normalize_api_paths_all(self):
        self.assertEqual(normalize_api_paths("ALL"), [])
        self.assertEqual(normalize_api_paths("*"), [])
        self.assertEqual(normalize_api_paths(""), [])

    def test_normalize_api_paths_multi_values(self):
        self.assertEqual(
            normalize_api_paths("/a,/b,/a"),
            ["/a", "/b"],
        )

    def test_default_batch_code_format(self):
        value = default_batch_code("biz#old#20260309_01", "biz#new#20260309_01")
        self.assertRegex(value, r"^REG_old_new_\d{8}_\d{6}_\d{6}$")

    def test_normalize_trace_id(self):
        self.assertEqual(normalize_trace_id("  abc123  "), "abc123")
        self.assertEqual(normalize_trace_id(None), "")

    def test_has_trace_pair(self):
        self.assertTrue(has_trace_pair("old", "new"))
        self.assertFalse(has_trace_pair("old", ""))
        self.assertFalse(has_trace_pair("", "new"))

    def test_split_trace_ids_by_compare_status(self):
        success_ids, failed_ids = split_trace_ids_by_compare_status(
            [
                {"pair_status": "MATCHED", "compare_status": "SUCCESS", "diff_level": "SAME", "old_trace_id": "S1", "new_trace_id": "S2"},
                {"pair_status": "MATCHED", "compare_status": "SUCCESS", "diff_level": "BLOCK", "old_trace_id": "B1", "new_trace_id": "B2"},
                {"pair_status": "MATCHED", "compare_status": "FAILED", "diff_level": "BLOCK", "old_trace_id": "F1", "new_trace_id": "F2"},
                {"pair_status": "ONLY_OLD", "compare_status": "SKIPPED", "old_trace_id": "F1", "new_trace_id": "F3"},
                {"pair_status": "MATCHED", "compare_status": "SUCCESS", "diff_level": "NORMAL", "old_trace_id": "S1", "new_trace_id": "S3"},
            ]
        )
        self.assertEqual(success_ids, ["S1", "S2", "S3"])
        self.assertEqual(failed_ids, ["B1", "B2", "F1", "F2"])


if __name__ == "__main__":
    unittest.main()
