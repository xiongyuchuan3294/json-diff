from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class CompareRules:
    ignore_paths: set[str] = field(default_factory=set)
    array_compare_mode: str = "BY_KEY"
    array_key_map: dict[str, str] = field(default_factory=dict)
    ignore_order: bool = True


def load_rules(rows: list[dict]) -> CompareRules:
    rules = CompareRules()
    for row in sorted(rows, key=lambda item: (item["priority"], item["id"])):
        if row.get("ignore_paths"):
            rules.ignore_paths.update(json.loads(row["ignore_paths"]))
        if row.get("array_compare_mode"):
            rules.array_compare_mode = row["array_compare_mode"]
        if row.get("array_key_map"):
            rules.array_key_map.update(json.loads(row["array_key_map"]))
    return rules
