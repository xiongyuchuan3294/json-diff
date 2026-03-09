#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.config import TARGET_SCHEMA, get_demo_db_config
from regression_demo.db import DbClient
from regression_demo.schema import init_schema


def main() -> int:
    db = DbClient(get_demo_db_config())
    init_schema(db)
    print(f"[OK] schema initialized: {TARGET_SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
