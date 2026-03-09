from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from deepdiff import DeepDiff

from .rules import CompareRules


@dataclass
class DiffItem:
    json_path: str
    diff_type: str
    old_value: Any
    new_value: Any
    severity: str
    rule_source: str = "deepdiff"
    is_ignored: int = 0


def _severity_for_path(path: str) -> str:
    if path in {"$.status_code", "$.retCode", "$.success"}:
        return "BLOCK"
    if path.startswith("$.retCode") or path.startswith("$.success"):
        return "BLOCK"
    if path.startswith("$.data"):
        return "NORMAL"
    return "NORMAL"


def _parse_json(text: str | None) -> Any:
    if text is None or text == "":
        raise ValueError("empty response body")
    return json.loads(text)


def _json_path_to_deepdiff_path(path: str) -> str:
    if path == "$":
        return "root"
    remaining = path[1:]
    tokens: list[str] = []
    i = 0
    while i < len(remaining):
        char = remaining[i]
        if char == ".":
            i += 1
            start = i
            while i < len(remaining) and remaining[i] not in ".[":
                i += 1
            token = remaining[start:i]
            if token:
                tokens.append(f"['{token}']")
            continue
        if char == "[":
            end = remaining.index("]", i)
            token = remaining[i + 1 : end]
            if token.isdigit():
                tokens.append(f"[{token}]")
            else:
                tokens.append(f"['{token}']")
            i = end + 1
            continue
        i += 1
    return "root" + "".join(tokens)


def _deepdiff_path_to_json_path(path: str) -> str:
    result = path.replace("root", "$")
    result = re.sub(r"\['([^']+)'\]", lambda match: "." + match.group(1), result)
    return result


def _build_diff_items(diff_dict: dict[str, Any], rules: CompareRules) -> list[DiffItem]:
    items: list[DiffItem] = []

    for path, payload in diff_dict.get("values_changed", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(
            DiffItem(
                json_path=json_path,
                diff_type="CHANGE",
                old_value=payload.get("old_value"),
                new_value=payload.get("new_value"),
                severity=_severity_for_path(json_path),
            )
        )

    for path, payload in diff_dict.get("type_changes", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(
            DiffItem(
                json_path=json_path,
                diff_type="TYPE_CHANGE",
                old_value=payload.get("old_value"),
                new_value=payload.get("new_value"),
                severity="BLOCK",
            )
        )

    for path in diff_dict.get("dictionary_item_added", []):
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="ADD", old_value=None, new_value="<added>", severity=_severity_for_path(json_path)))

    for path in diff_dict.get("dictionary_item_removed", []):
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="REMOVE", old_value="<removed>", new_value=None, severity=_severity_for_path(json_path)))

    for path, payload in diff_dict.get("iterable_item_added", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="ADD", old_value=None, new_value=payload, severity=_severity_for_path(json_path)))

    for path, payload in diff_dict.get("iterable_item_removed", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="REMOVE", old_value=payload, new_value=None, severity=_severity_for_path(json_path)))

    items.sort(key=lambda item: item.json_path)
    return items


def compare_json_text(old_text: str, new_text: str, status_code_old: int | None, status_code_new: int | None, rules: CompareRules) -> tuple[str, str, list[DiffItem]]:
    if status_code_old != 200 or status_code_new != 200:
        return "SUCCESS", "BLOCK", [
            DiffItem("$.status_code", "CHANGE", status_code_old, status_code_new, "BLOCK")
        ]

    try:
        old_json = _parse_json(old_text)
        new_json = _parse_json(new_text)
    except Exception as exc:
        return "FAILED", "BLOCK", [
            DiffItem("$.response_body", "INVALID_JSON", old_text, new_text, "BLOCK", rule_source=str(exc))
        ]

    exclude_paths = {_json_path_to_deepdiff_path(path) for path in rules.ignore_paths if path.startswith("$")}
    diff = DeepDiff(
        old_json,
        new_json,
        ignore_order=True,
        exclude_paths=exclude_paths,
    )
    diff_items = _build_diff_items(diff.to_dict(), rules)

    if not diff_items:
        return "SUCCESS", "SAME", []

    level = "BLOCK" if any(item.severity == "BLOCK" for item in diff_items) else "NORMAL"
    return "SUCCESS", level, diff_items
