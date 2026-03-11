from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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


def _resolve_severity(path: str, rules: CompareRules) -> str:
    if path == "$.status_code" or path.startswith("$.status_code"):
        return "BLOCK"
    severity = rules.severity_for_path(path)
    return str(severity or "NORMAL").upper()


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


def _split_json_path(path: str) -> list[str | int]:
    text = path.strip()
    if not text.startswith("$"):
        raise ValueError(f"invalid json path: {path}")
    if text == "$":
        return []

    tokens: list[str | int] = []
    i = 1
    while i < len(text):
        char = text[i]
        if char == ".":
            i += 1
            start = i
            while i < len(text) and text[i] not in ".[":
                i += 1
            token = text[start:i]
            if token:
                tokens.append(token)
            continue
        if char == "[":
            end = text.index("]", i)
            token = text[i + 1 : end].strip()
            if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
                token = token[1:-1]
            if token.isdigit():
                tokens.append(int(token))
            else:
                tokens.append(token)
            i = end + 1
            continue
        i += 1
    return tokens


def _get_node(root: Any, path: str) -> tuple[bool, Any]:
    current = root
    for token in _split_json_path(path):
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                return False, None
            current = current[token]
            continue
        if not isinstance(current, dict) or token not in current:
            return False, None
        current = current[token]
    return True, current


def _set_node(root: Any, path: str, value: Any) -> Any:
    tokens = _split_json_path(path)
    if not tokens:
        return value

    current = root
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                return root
            current = current[token]
            continue
        if not isinstance(current, dict) or token not in current:
            return root
        current = current[token]

    final = tokens[-1]
    if isinstance(final, int):
        if isinstance(current, list) and 0 <= final < len(current):
            current[final] = value
        return root

    if isinstance(current, dict):
        current[final] = value
    return root


def _normalize_numeric_like(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value

    raw = ""
    if isinstance(value, (int, float, Decimal)):
        raw = str(value)
    elif isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return value
    else:
        return value

    try:
        decimal_value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return value
    if not decimal_value.is_finite():
        return value

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return normalized


def _normalize_by_operators(value: Any, operators: tuple[str, ...]) -> Any:
    normalized = value
    for operator in operators:
        if operator == "NUMERIC_EQ":
            normalized = _normalize_numeric_like(normalized)
        elif operator == "NULL_EMPTY_STRING_EQ":
            if normalized is None or normalized == "":
                normalized = ""
    return normalized


def _apply_value_equivalence(value: Any, path: str, rules: CompareRules) -> Any:
    if isinstance(value, dict):
        transformed: dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
            transformed[key] = _apply_value_equivalence(item, child_path, rules)
        value = transformed
    elif isinstance(value, list):
        transformed_list: list[Any] = []
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            transformed_list.append(_apply_value_equivalence(item, child_path, rules))
        value = transformed_list

    operators = rules.operators_for_path(path)
    if not operators:
        return value
    return _normalize_by_operators(value, operators)


def _align_array_payload_by_key(payload: Any, array_path: str, key_name: str) -> tuple[Any, str | None]:
    exists, node = _get_node(payload, array_path)
    if not exists:
        return payload, None
    if not isinstance(node, list):
        return payload, f"{array_path} is not an array"

    keyed_rows: dict[str, Any] = {}
    for index, item in enumerate(node):
        if not isinstance(item, dict):
            return payload, f"{array_path}[{index}] is not an object"
        if key_name not in item:
            return payload, f"{array_path}[{index}] missing key: {key_name}"

        key_value = item.get(key_name)
        if key_value is None or key_value == "":
            return payload, f"{array_path}[{index}] empty key: {key_name}"

        aligned_key = str(key_value)
        if aligned_key in keyed_rows:
            return payload, f"{array_path} duplicated key '{aligned_key}'"
        keyed_rows[aligned_key] = item

    aligned_rows = {key: keyed_rows[key] for key in sorted(keyed_rows)}
    payload = _set_node(payload, array_path, aligned_rows)
    return payload, None


def _align_arrays_by_key(old_json: Any, new_json: Any, rules: CompareRules) -> tuple[Any, Any, list[DiffItem]]:
    if str(rules.array_compare_mode or "").upper() != "BY_KEY":
        return old_json, new_json, []
    if not rules.array_key_map:
        return old_json, new_json, []

    errors: list[DiffItem] = []
    for array_path, key_name in sorted(rules.array_key_map.items()):
        old_json, old_error = _align_array_payload_by_key(old_json, array_path, key_name)
        new_json, new_error = _align_array_payload_by_key(new_json, array_path, key_name)
        if old_error or new_error:
            errors.append(
                DiffItem(
                    json_path=array_path,
                    diff_type="ARRAY_KEY_ERROR",
                    old_value=old_error,
                    new_value=new_error,
                    severity="BLOCK",
                    rule_source="array_key_map",
                )
            )

    return old_json, new_json, errors


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
                severity=_resolve_severity(json_path, rules),
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
                severity=_resolve_severity(json_path, rules),
            )
        )

    for path in diff_dict.get("dictionary_item_added", []):
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="ADD", old_value=None, new_value="<added>", severity=_resolve_severity(json_path, rules)))

    for path in diff_dict.get("dictionary_item_removed", []):
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="REMOVE", old_value="<removed>", new_value=None, severity=_resolve_severity(json_path, rules)))

    for path, payload in diff_dict.get("iterable_item_added", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="ADD", old_value=None, new_value=payload, severity=_resolve_severity(json_path, rules)))

    for path, payload in diff_dict.get("iterable_item_removed", {}).items():
        json_path = _deepdiff_path_to_json_path(path)
        if json_path in rules.ignore_paths:
            continue
        items.append(DiffItem(json_path=json_path, diff_type="REMOVE", old_value=payload, new_value=None, severity=_resolve_severity(json_path, rules)))

    items.sort(key=lambda item: (item.json_path, item.diff_type))
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

    old_json = _apply_value_equivalence(old_json, "$", rules)
    new_json = _apply_value_equivalence(new_json, "$", rules)
    old_json, new_json, array_key_errors = _align_arrays_by_key(old_json, new_json, rules)
    if array_key_errors:
        return "SUCCESS", "BLOCK", array_key_errors

    exclude_paths = {_json_path_to_deepdiff_path(path) for path in rules.ignore_paths if path.startswith("$")}
    diff = DeepDiff(
        old_json,
        new_json,
        ignore_order=rules.ignore_order,
        exclude_paths=exclude_paths,
    )
    diff_items = _build_diff_items(diff.to_dict(), rules)

    if not diff_items:
        return "SUCCESS", "SAME", []

    severities = {str(item.severity or "").upper() for item in diff_items}
    if "BLOCK" in severities:
        level = "BLOCK"
    elif severities and severities.issubset({"IGNORABLE"}):
        level = "IGNORABLE"
    else:
        level = "NORMAL"
    return "SUCCESS", level, diff_items
