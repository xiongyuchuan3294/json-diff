from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.runner import default_batch_code, normalize_api_paths


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
        self.assertRegex(value, r"^REG_old_new_\d{8}_\d{6}$")


if __name__ == "__main__":
    unittest.main()
