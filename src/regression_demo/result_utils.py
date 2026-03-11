from __future__ import annotations

from collections.abc import Mapping, Sequence


def normalize_trace_id(value: object) -> str:
    return "" if value is None else str(value).strip()


def is_success_result(row: Mapping[str, object]) -> bool:
    compare_status = str(row.get("compare_status") or "").upper()
    diff_level = str(row.get("diff_level") or "").upper()
    return compare_status == "SUCCESS" and diff_level != "BLOCK"


def split_trace_ids_by_compare_status(results: Sequence[Mapping[str, object]]) -> tuple[list[str], list[str]]:
    success_trace_ids: list[str] = []
    failed_trace_ids: list[str] = []

    def append_unique(container: list[str], value: object) -> None:
        trace_id = normalize_trace_id(value)
        if trace_id and trace_id not in container:
            container.append(trace_id)

    for row in results:
        if str(row.get("pair_status") or "").upper() != "MATCHED":
            continue
        target = success_trace_ids if is_success_result(row) else failed_trace_ids
        append_unique(target, row.get("old_trace_id"))
        append_unique(target, row.get("new_trace_id"))

    return success_trace_ids, failed_trace_ids


def render_trace_id_lines(trace_ids: Sequence[str], *, empty_placeholder: str = "-") -> list[str]:
    rows = [normalize_trace_id(item) for item in trace_ids]
    rows = [item for item in rows if item]
    if not rows:
        return [empty_placeholder]

    output: list[str] = []
    last_index = len(rows) - 1
    for index, trace_id in enumerate(rows):
        suffix = "," if index < last_index else ""
        output.append(f"'{trace_id}'{suffix}")
    return output
