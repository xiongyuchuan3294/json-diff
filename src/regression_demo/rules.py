from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_IGNORE_PATHS: tuple[str, ...] = ("$.timestamp",)
DEFAULT_ARRAY_COMPARE_MODE = "BY_KEY"
DEFAULT_ARRAY_KEY_MAP: dict[str, str] = {
    "$.data.content": "transactionkey",
}
DEFAULT_SEVERITY_DEFAULT = "NORMAL"
DEFAULT_SEVERITY_RULE_MAP: dict[str, str] = {
    "$.retCode": "BLOCK",
    "$.success": "BLOCK",
    "$.timestamp": "IGNORABLE",
    "$.data.totalCount": "NORMAL",
    "$.data.totalPage": "NORMAL",
}
DEFAULT_VALUE_EQ_RULE_MAP: dict[str, tuple[str, ...]] = {
    "$.data.content[*].transAmount": ("NUMERIC_EQ",),
    "$.data.content[*].memo": ("NULL_EMPTY_STRING_EQ",),
}


@dataclass
class CompareRules:
    ignore_paths: set[str] = field(default_factory=set)
    array_compare_mode: str = "BY_KEY"
    array_key_map: dict[str, str] = field(default_factory=dict)
    ignore_order: bool = True
    severity_default: str = "NORMAL"
    severity_rule_map: dict[str, str] = field(default_factory=dict)
    value_equivalence_rule_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _severity_exact_map: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _severity_fuzzy_rules: list[tuple[str, str, Any, int]] = field(default_factory=list, init=False, repr=False)
    _value_eq_exact_map: dict[str, tuple[str, ...]] = field(default_factory=dict, init=False, repr=False)
    _value_eq_fuzzy_rules: list[tuple[str, str, Any, int]] = field(default_factory=list, init=False, repr=False)

    def compile_matchers(self) -> None:
        self._severity_exact_map, self._severity_fuzzy_rules = _compile_pattern_rules(self.severity_rule_map)
        self._value_eq_exact_map, self._value_eq_fuzzy_rules = _compile_pattern_rules(self.value_equivalence_rule_map)

    def severity_for_path(self, path: str) -> str:
        if path in self._severity_exact_map:
            return self._severity_exact_map[path]

        for mode, token, severity, _specificity in self._severity_fuzzy_rules:
            if mode == "WILDCARD" and token.fullmatch(path):
                return severity
            if mode == "PREFIX" and path.startswith(token):
                return severity

        return self.severity_default

    def operators_for_path(self, path: str) -> tuple[str, ...]:
        if path in self._value_eq_exact_map:
            return self._value_eq_exact_map[path]

        for mode, token, operators, _specificity in self._value_eq_fuzzy_rules:
            if mode == "WILDCARD" and token.fullmatch(path):
                return operators
            if mode == "PREFIX" and path.startswith(token):
                return operators

        return ()


def _normalize_severity(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _parse_operator_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()

    raw_ops: list[str] = []
    if isinstance(value, str):
        raw_ops = [value]
    elif isinstance(value, list):
        raw_ops = [str(item) for item in value]
    else:
        raw_ops = [str(value)]

    ordered: list[str] = []
    seen: set[str] = set()
    for item in raw_ops:
        op = item.strip().upper()
        if not op or op in seen:
            continue
        ordered.append(op)
        seen.add(op)
    return tuple(ordered)


def _parse_severity_rule(raw: str) -> tuple[str | None, dict[str, str]]:
    payload = json.loads(raw)
    default_value: str | None = None
    entries: dict[str, str] = {}

    if isinstance(payload, dict):
        default_value = _normalize_severity(payload.get("default"))
        rule_rows = payload.get("rules")
        if isinstance(rule_rows, list):
            for row in rule_rows:
                if not isinstance(row, dict):
                    continue
                path = str(row.get("path") or "").strip()
                severity = _normalize_severity(row.get("severity"))
                if path and severity:
                    entries[path] = severity
        else:
            for path, severity in payload.items():
                if str(path) == "default":
                    continue
                normalized = _normalize_severity(severity)
                text_path = str(path).strip()
                if text_path and normalized:
                    entries[text_path] = normalized
    elif isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            severity = _normalize_severity(row.get("severity"))
            if path and severity:
                entries[path] = severity

    return default_value, entries


def _parse_value_equivalence_rule(raw: str) -> dict[str, tuple[str, ...]]:
    payload = json.loads(raw)
    entries: dict[str, tuple[str, ...]] = {}

    if isinstance(payload, dict):
        rule_rows = payload.get("rules")
        if isinstance(rule_rows, list):
            for row in rule_rows:
                if not isinstance(row, dict):
                    continue
                path = str(row.get("path") or "").strip()
                operators = _parse_operator_list(row.get("operators"))
                if path and operators:
                    entries[path] = operators
        else:
            for path, operators in payload.items():
                text_path = str(path).strip()
                normalized = _parse_operator_list(operators)
                if text_path and normalized:
                    entries[text_path] = normalized
    elif isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            operators = _parse_operator_list(row.get("operators"))
            if path and operators:
                entries[path] = operators

    return entries


def _compile_pattern_rules(pattern_map: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str, Any, int]]]:
    exact_map: dict[str, Any] = {}
    fuzzy_rules: list[tuple[str, str, Any, int]] = []

    for raw_pattern, value in pattern_map.items():
        pattern = str(raw_pattern or "").strip()
        if not pattern:
            continue

        if pattern.endswith("*"):
            prefix = pattern[:-1]
            fuzzy_rules.append(("PREFIX", prefix, value, len(prefix)))
            continue

        if "[*]" in pattern:
            escaped = re.escape(pattern).replace(r"\[\*\]", r"\[\d+\]")
            fuzzy_rules.append(("WILDCARD", re.compile(f"^{escaped}$"), value, len(pattern.replace("[*]", ""))))
            continue

        exact_map[pattern] = value

    fuzzy_rules.sort(key=lambda item: item[3], reverse=True)
    return exact_map, fuzzy_rules


def build_default_rules() -> CompareRules:
    rules = CompareRules(
        ignore_paths=set(DEFAULT_IGNORE_PATHS),
        array_compare_mode=DEFAULT_ARRAY_COMPARE_MODE,
        array_key_map=dict(DEFAULT_ARRAY_KEY_MAP),
        ignore_order=True,
        severity_default=DEFAULT_SEVERITY_DEFAULT,
        severity_rule_map=dict(DEFAULT_SEVERITY_RULE_MAP),
        value_equivalence_rule_map={path: tuple(operators) for path, operators in DEFAULT_VALUE_EQ_RULE_MAP.items()},
    )
    rules.compile_matchers()
    return rules


def load_rules(rows: list[dict]) -> CompareRules:
    rules = build_default_rules()
    severity_rule_map: dict[str, str] = dict(rules.severity_rule_map)
    value_equivalence_rule_map: dict[str, tuple[str, ...]] = dict(rules.value_equivalence_rule_map)

    for row in sorted(rows, key=lambda item: (item["priority"], item["id"])):
        if row.get("ignore_paths"):
            try:
                payload = json.loads(row["ignore_paths"])
            except Exception:
                payload = []
            if isinstance(payload, list):
                for item in payload:
                    if item is None:
                        continue
                    path = str(item).strip()
                    if path:
                        rules.ignore_paths.add(path)

        if row.get("array_compare_mode"):
            rules.array_compare_mode = str(row["array_compare_mode"]).strip() or rules.array_compare_mode

        if row.get("array_key_map"):
            try:
                payload = json.loads(row["array_key_map"])
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key, value in payload.items():
                    if key is None or value is None:
                        continue
                    path = str(key).strip()
                    key_name = str(value).strip()
                    if path and key_name:
                        rules.array_key_map[path] = key_name

        if row.get("severity_rule"):
            try:
                default_value, parsed_map = _parse_severity_rule(row["severity_rule"])
            except Exception:
                default_value, parsed_map = None, {}
            if default_value:
                rules.severity_default = default_value
            severity_rule_map.update(parsed_map)

        if row.get("value_equivalence_rule"):
            try:
                parsed_map = _parse_value_equivalence_rule(row["value_equivalence_rule"])
            except Exception:
                parsed_map = {}
            value_equivalence_rule_map.update(parsed_map)

    rules.severity_default = _normalize_severity(rules.severity_default) or "NORMAL"
    rules.severity_rule_map = severity_rule_map
    rules.value_equivalence_rule_map = value_equivalence_rule_map
    rules.compile_matchers()
    return rules
