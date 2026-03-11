from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.rules import load_rules


def _row(**kwargs):
    base = {
        "id": 1,
        "priority": 10,
        "ignore_paths": None,
        "array_compare_mode": None,
        "array_key_map": None,
        "severity_rule": None,
        "value_equivalence_rule": None,
    }
    base.update(kwargs)
    return base


class RulesLoaderTest(unittest.TestCase):
    def test_default_rules_apply_when_table_rules_missing(self):
        rules = load_rules([])
        self.assertIn("$.timestamp", rules.ignore_paths)
        self.assertEqual(rules.array_compare_mode, "BY_KEY")
        self.assertEqual(rules.array_key_map.get("$.data.content"), "transactionkey")
        self.assertEqual(rules.severity_for_path("$.retCode"), "BLOCK")
        self.assertEqual(rules.severity_for_path("$.success"), "BLOCK")
        self.assertEqual(rules.severity_for_path("$.timestamp"), "IGNORABLE")
        self.assertEqual(rules.operators_for_path("$.data.content[0].transAmount"), ("NUMERIC_EQ",))

    def test_table_rules_override_default_by_same_key(self):
        rows = [
            _row(
                id=100,
                priority=999,
                array_key_map=json.dumps({"$.data.content": "id"}),
                severity_rule=json.dumps({
                    "rules": [
                        {"path": "$.retCode", "severity": "NORMAL"},
                    ],
                }),
                value_equivalence_rule=json.dumps({
                    "rules": [
                        {"path": "$.data.content[*].transAmount", "operators": ["NULL_EMPTY_STRING_EQ"]},
                    ],
                }),
            )
        ]
        rules = load_rules(rows)
        self.assertEqual(rules.array_key_map.get("$.data.content"), "id")
        self.assertEqual(rules.severity_for_path("$.retCode"), "NORMAL")
        self.assertEqual(rules.operators_for_path("$.data.content[5].transAmount"), ("NULL_EMPTY_STRING_EQ",))

    def test_load_rules_merge_and_override(self):
        rows = [
            _row(
                id=1,
                priority=10,
                ignore_paths=json.dumps(["$.timestamp"]),
                array_compare_mode="UNORDERED",
                array_key_map=json.dumps({"$.data.content": "legacyKey"}),
                severity_rule=json.dumps({
                    "default": "NORMAL",
                    "rules": [
                        {"path": "$.retCode", "severity": "BLOCK"},
                    ],
                }),
                value_equivalence_rule=json.dumps({
                    "rules": [
                        {"path": "$.amount", "operators": ["NUMERIC_EQ"]},
                    ],
                }),
            ),
            _row(
                id=2,
                priority=20,
                ignore_paths=json.dumps(["$.traceId"]),
                array_compare_mode="BY_KEY",
                array_key_map=json.dumps({"$.data.content": "transactionkey"}),
                severity_rule=json.dumps({
                    "rules": [
                        {"path": "$.retCode", "severity": "NORMAL"},
                        {"path": "$.success", "severity": "BLOCK"},
                    ],
                }),
                value_equivalence_rule=json.dumps({
                    "rules": [
                        {"path": "$.amount", "operators": ["NULL_EMPTY_STRING_EQ"]},
                        {"path": "$.memo", "operators": ["NULL_EMPTY_STRING_EQ"]},
                    ],
                }),
            ),
        ]

        rules = load_rules(rows)
        self.assertEqual(rules.ignore_paths, {"$.timestamp", "$.traceId"})
        self.assertEqual(rules.array_compare_mode, "BY_KEY")
        self.assertEqual(rules.array_key_map["$.data.content"], "transactionkey")
        self.assertEqual(rules.severity_for_path("$.retCode"), "NORMAL")
        self.assertEqual(rules.severity_for_path("$.success"), "BLOCK")
        self.assertEqual(rules.operators_for_path("$.amount"), ("NULL_EMPTY_STRING_EQ",))
        self.assertEqual(rules.operators_for_path("$.memo"), ("NULL_EMPTY_STRING_EQ",))

    def test_severity_path_match_precedence(self):
        rules = load_rules(
            [
                _row(
                    severity_rule=json.dumps({
                        "default": "NORMAL",
                        "rules": [
                            {"path": "$.data.content[*].amount", "severity": "NORMAL"},
                            {"path": "$.data.content[0].amount", "severity": "BLOCK"},
                            {"path": "$.data.meta.*", "severity": "IGNORABLE"},
                        ],
                    })
                )
            ]
        )
        self.assertEqual(rules.severity_for_path("$.data.content[0].amount"), "BLOCK")
        self.assertEqual(rules.severity_for_path("$.data.content[3].amount"), "NORMAL")
        self.assertEqual(rules.severity_for_path("$.data.meta.traceId"), "IGNORABLE")
        self.assertEqual(rules.severity_for_path("$.data.unknown"), "NORMAL")

    def test_value_equivalence_path_match_precedence(self):
        rules = load_rules(
            [
                _row(
                    value_equivalence_rule=json.dumps({
                        "rules": [
                            {"path": "$.data.content[*].amount", "operators": ["NUMERIC_EQ"]},
                            {"path": "$.data.content[0].amount", "operators": ["NULL_EMPTY_STRING_EQ"]},
                            {"path": "$.data.meta.*", "operators": ["NULL_EMPTY_STRING_EQ"]},
                        ],
                    })
                )
            ]
        )
        self.assertEqual(rules.operators_for_path("$.data.content[0].amount"), ("NULL_EMPTY_STRING_EQ",))
        self.assertEqual(rules.operators_for_path("$.data.content[2].amount"), ("NUMERIC_EQ",))
        self.assertEqual(rules.operators_for_path("$.data.meta.memo"), ("NULL_EMPTY_STRING_EQ",))
        self.assertEqual(rules.operators_for_path("$.data.none"), ())


if __name__ == "__main__":
    unittest.main()
