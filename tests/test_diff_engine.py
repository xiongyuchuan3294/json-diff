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


def _build_rules(**kwargs) -> CompareRules:
    rules = CompareRules(**kwargs)
    rules.compile_matchers()
    return rules


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
        rules = _build_rules(ignore_paths={"$.timestamp"}, ignore_order=True)
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
        rules = _build_rules(ignore_order=True)
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "NORMAL")
        self.assertTrue(any(item.json_path.startswith("$.data.content") for item in diffs))

    def test_non_200_status_is_block(self):
        rules = _build_rules(ignore_order=True)
        compare_status, diff_level, diffs = compare_json_text('{"ok":true}', '{"ok":false}', 200, 500, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "BLOCK")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].json_path, "$.status_code")

    def test_severity_rule_exact_wildcard_prefix_default(self):
        old_text = json.dumps({
            "retCode": 0,
            "data": {
                "content": [{"amount": 100}],
                "meta": {"traceId": "A1"},
                "totalCount": 10,
            },
        })
        new_text = json.dumps({
            "retCode": 500,
            "data": {
                "content": [{"amount": 200}],
                "meta": {"traceId": "A2"},
                "totalCount": 11,
            },
        })
        rules = _build_rules(
            severity_default="NORMAL",
            severity_rule_map={
                "$.retCode": "BLOCK",
                "$.data.content[*].amount": "BLOCK",
                "$.data.meta.*": "IGNORABLE",
            },
            ignore_order=False,
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "BLOCK")
        by_path = {item.json_path: item for item in diffs}
        self.assertEqual(by_path["$.retCode"].severity, "BLOCK")
        self.assertEqual(by_path["$.data.content[0].amount"].severity, "BLOCK")
        self.assertEqual(by_path["$.data.meta.traceId"].severity, "IGNORABLE")
        self.assertEqual(by_path["$.data.totalCount"].severity, "NORMAL")

    def test_diff_level_is_ignorable_when_all_diffs_ignorable(self):
        old_text = json.dumps({"timestamp": 1})
        new_text = json.dumps({"timestamp": 2})
        rules = _build_rules(
            severity_default="NORMAL",
            severity_rule_map={"$.timestamp": "IGNORABLE"},
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "IGNORABLE")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].severity, "IGNORABLE")

    def test_numeric_value_equivalence_rule(self):
        old_text = json.dumps({"data": {"totalAmount": 50000}})
        new_text = json.dumps({"data": {"totalAmount": "50000.0"}})
        rules = _build_rules(
            value_equivalence_rule_map={
                "$.data.totalAmount": ("NUMERIC_EQ",),
            }
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "SAME")
        self.assertEqual(diffs, [])

    def test_null_empty_string_equivalence_rule(self):
        old_text = json.dumps({"data": {"memo": None}})
        new_text = json.dumps({"data": {"memo": ""}})
        rules = _build_rules(
            value_equivalence_rule_map={
                "$.data.memo": ("NULL_EMPTY_STRING_EQ",),
            }
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "SAME")
        self.assertEqual(diffs, [])

    def test_unconfigured_value_equivalence_keeps_diff(self):
        old_text = json.dumps({"data": {"totalAmount": 50000}})
        new_text = json.dumps({"data": {"totalAmount": "50000.0"}})
        rules = _build_rules()
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "NORMAL")
        self.assertTrue(any(item.json_path == "$.data.totalAmount" for item in diffs))

    def test_array_key_map_reordered_array_same(self):
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
                    {"transactionkey": "TX002", "amount": 200},
                    {"transactionkey": "TX001", "amount": 100},
                ]
            }
        })
        rules = _build_rules(
            array_compare_mode="BY_KEY",
            array_key_map={"$.data.content": "transactionkey"},
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "SAME")
        self.assertEqual(diffs, [])

    def test_array_key_map_change_is_detected(self):
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
        rules = _build_rules(
            array_compare_mode="BY_KEY",
            array_key_map={"$.data.content": "transactionkey"},
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "NORMAL")
        self.assertTrue(any(item.json_path.startswith("$.data.content.TX002") for item in diffs))

    def test_array_key_map_missing_key_is_block(self):
        old_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX001", "amount": 100},
                ]
            }
        })
        new_text = json.dumps({
            "data": {
                "content": [
                    {"amount": 100},
                ]
            }
        })
        rules = _build_rules(
            array_compare_mode="BY_KEY",
            array_key_map={"$.data.content": "transactionkey"},
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "BLOCK")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].diff_type, "ARRAY_KEY_ERROR")
        self.assertEqual(diffs[0].rule_source, "array_key_map")

    def test_array_key_map_duplicate_key_is_block(self):
        old_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX001", "amount": 100},
                    {"transactionkey": "TX001", "amount": 200},
                ]
            }
        })
        new_text = json.dumps({
            "data": {
                "content": [
                    {"transactionkey": "TX001", "amount": 100},
                ]
            }
        })
        rules = _build_rules(
            array_compare_mode="BY_KEY",
            array_key_map={"$.data.content": "transactionkey"},
        )
        compare_status, diff_level, diffs = compare_json_text(old_text, new_text, 200, 200, rules)
        self.assertEqual(compare_status, "SUCCESS")
        self.assertEqual(diff_level, "BLOCK")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].diff_type, "ARRAY_KEY_ERROR")


if __name__ == "__main__":
    unittest.main()
