from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.seed_data import seed_request_info, seed_rules


class FakeDb:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> int:
        self.execute_calls.append((sql, params))
        return 1

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> int:
        self.executemany_calls.append((sql, params))
        return len(params)


class SeedDataIdempotentTest(unittest.TestCase):
    def test_seed_rules_uses_upsert(self):
        db = FakeDb()
        seed_rules(db)  # type: ignore[arg-type]

        self.assertEqual(len(db.execute_calls), 1)
        sql_text, _ = db.execute_calls[0]
        self.assertIn("ON DUPLICATE KEY UPDATE", sql_text.upper())

    def test_seed_request_info_uses_upsert(self):
        db = FakeDb()
        seed_request_info(db)  # type: ignore[arg-type]

        self.assertEqual(len(db.executemany_calls), 1)
        sql_text, params = db.executemany_calls[0]
        self.assertIn("ON DUPLICATE KEY UPDATE", sql_text.upper())
        self.assertGreater(len(params), 0)


if __name__ == "__main__":
    unittest.main()
