from __future__ import annotations

from pathlib import Path

from .config import TARGET_SCHEMA
from .result_utils import is_success_result, render_trace_id_lines, split_trace_ids_by_compare_status


def _md_table_cell(value: object) -> str:
    text = "-" if value is None else str(value)
    if text == "":
        return "-"
    # Keep markdown table stable.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text


def _append_trace_id_block(lines: list[str], trace_ids: list[str]) -> None:
    lines.extend(["", "```text"])
    lines.extend(render_trace_id_lines(trace_ids))
    lines.append("```")


def _format_summary(row: dict) -> str:
    compare_status = str(row.get("compare_status") or "")
    summary = row.get("summary") or ""
    if compare_status.upper() == "FAILED":
        detail = str(summary).strip()
        return "对比失败" if not detail else f"对比失败<br>失败详情：{detail}"
    return str(summary)


def render_markdown(report: dict) -> str:
    batch = report["batch"]
    results = [row for row in report["results"] if str(row.get("pair_status") or "").upper() == "MATCHED"]
    success_rows = [row for row in results if is_success_result(row)]
    failed_rows = [row for row in results if not is_success_result(row)]
    total_count = len(results)
    success_count = len(success_rows)
    failed_count = len(failed_rows)
    success_rate = 0.0 if total_count == 0 else round(success_count * 100 / total_count, 2)
    success_trace_ids, failed_trace_ids = split_trace_ids_by_compare_status(results)

    lines = [
        "# 测试报告",
        "",
        "## 1. 基本信息",
        "",
        f"- 任务编码：`{batch['batch_code']}`",
        f"- 目标库：`{TARGET_SCHEMA}`",
        f"- 旧版场景：`{batch['old_scenario_id']}`",
        f"- 新版场景：`{batch['new_scenario_id']}`",
        f"- 任务状态：`{batch['status']}`",
        "- 对比引擎：`DeepDiff(ignore_order=True)`",
        "",
        "## 2. 对比总览",
        "",
        f"- 请求场景总数：`{total_count}`",
        f"- 对比成功场景数：`{success_count}`",
        f"- 对比失败场景数：`{failed_count}`",
        f"- 成功率：`{success_rate}%`",
        "- 失败判定口径：`compare_status != SUCCESS` 或 `diff_level = BLOCK`",
        "",
        "## 3. 失败分类",
        "",
    ]

    by_pair: dict[str, int] = {}
    for row in failed_rows:
        key = row["diff_level"]
        by_pair[key] = by_pair.get(key, 0) + 1
    if not by_pair:
        lines.append("- `无`：`0`")
    else:
        for key, count in sorted(by_pair.items()):
            lines.append(f"- `{key}`：`{count}`")

    lines.extend([
        "",
        "## 4. 对比成功 Trace ID",
    ])
    _append_trace_id_block(lines, success_trace_ids)

    lines.extend([
        "",
        "## 5. 对比失败 Trace ID",
    ])
    _append_trace_id_block(lines, failed_trace_ids)

    lines.extend([
        "",
        "## 6. 失败请求明细",
        "",
        "| compare_status | diff_level | api_path | old_trace_id | new_trace_id | query_params | request_body | summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    if not failed_rows:
        lines.append("| - | - | - | - | - | - | - | - |")
    for row in failed_rows:
        compare_status = str(row.get("compare_status") or "")
        summary = _format_summary(row)
        query_params = row.get("old_query_params") or row.get("new_query_params")
        request_body = row.get("old_request_body") or row.get("new_request_body")
        lines.append(
            f"| {_md_table_cell(compare_status)} | {_md_table_cell(row.get('diff_level'))} | {_md_table_cell(row.get('api_path'))} | {_md_table_cell(row.get('old_trace_id'))} | {_md_table_cell(row.get('new_trace_id'))} | {_md_table_cell(query_params)} | {_md_table_cell(request_body)} | {_md_table_cell(summary)} |"
        )

    lines.extend([
        "",
        "## 7. 结论",
        "",
        f"- 本批次共 `total={total_count}` 个请求场景，`success={success_count}`，`failed={failed_count}`。",
        "- 重点查看上方失败明细中的 `query_params`、`request_body` 与失败原因。",
    ])
    return "\n".join(lines) + "\n"


def write_report(report: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path
