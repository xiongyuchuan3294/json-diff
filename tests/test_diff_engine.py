from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.diff_engine import compare_json_text
from regression_demo.rules import CompareRules


class DeepDiffEngineTest(unittest.TestCase):
    def test_ignore_order_true_makes_reordered_array_equal(self):
        old_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX001", "amount": 100},
                    {"transactionkey": "TX002", "amount": 200},
                ]
            },
            "timestamp": 1,
        })
        new_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX002", "amount": 200},
                    {"transactionkey": "TX001", "amount": 100},
                ]
            },
            "timestamp": 2,
        })
        rules = CompareRules(ignore_paths={"$.timestamp"}, ignore_order=True)
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "SAME")
        self.assertEqual(diffs, [])

    def test_value_change_is_detected_under_ignore_order(self):
        old_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX001", "amount": 100},
                    {"transactionkey": "TX002", "amount": 200},
                ]
            }
        })
        new_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX002", "amount": 999},
                    {"transactionkey": "TX001", "amount": 100},
                ]
            }
        })
        rules = CompareRules(ignore_order=True)
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "NORMAL")
        self.assertTrue(any(item.json_path.startswith("$.data.content") for item in diffs))

    def test_non_200_status_is_block(self):
        rules = CompareRules(ignore_order=True)
        compare_status, diff_level, diffs = compare_json_text('{"ok":true}', '{"ok":false}', 200, 500, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "BLOCK")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].json_path, "$.status_code")


if __name__ == "__main__":
    unittest.main()
