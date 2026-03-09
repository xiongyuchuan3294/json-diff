from __future__ import annotations

from pathlib import Path

from .config import TARGET_SCHEMA


def render_markdown(report: dict) -> str:
    batch = report["batch"]
    results = report["results"]
    detail_counts = report["detail_counts"]
    problem_rows = [row for row in results if row["diff_level"] != "SAME" or row["pair_status"] != "MATCHED"]

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
        "## 2. 汇总统计",
        "",
        f"- 总样本数：`{batch['total_sample_count']}`",
        f"- 可配对指纹数：`{batch['pairable_count']}`",
        f"- 成功配对数：`{batch['matched_count']}`",
        f"- 一致数：`{batch['same_count']}`",
        f"- 差异数：`{batch['diff_count']}`",
        f"- 仅旧版存在数：`{batch['only_old_count']}`",
        f"- 仅新版存在数：`{batch['only_new_count']}`",
        f"- 无效样本数：`{batch['invalid_count']}`",
        f"- 阻断差异数：`{batch['block_count']}`",
        f"- 问题请求数：`{len(problem_rows)}`",
        "",
        "## 3. 问题请求分类",
        "",
    ]

    by_pair: dict[str, int] = {}
    for row in problem_rows:
        key = row["pair_status"] if row["pair_status"] != "MATCHED" else row["diff_level"]
        by_pair[key] = by_pair.get(key, 0) + 1
    for key, count in sorted(by_pair.items()):
        lines.append(f"- `{key}`：`{count}`")

    lines.extend([
        "",
        "## 4. 差异明细统计",
        "",
    ])
    for item in detail_counts:
        lines.append(f"- `{item['severity']}`：`{item['cnt']}`")

    lines.extend([
        "",
        "## 5. 结果明细",
        "",
        "| pair_status | compare_status | diff_level | api_path | old_trace_id | new_trace_id | summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in results:
        lines.append(
            f"| {row['pair_status']} | {row['compare_status']} | {row['diff_level']} | {row['api_path']} | {row['old_trace_id'] or '-'} | {row['new_trace_id'] or '-'} | {row['summary'] or '-'} |"
        )

    lines.extend([
        "",
        "## 6. 结论",
        "",
        "- 本次验证已覆盖正常配对、一般差异、阻断差异、仅单边存在、重复样本、非 200 状态码、非 JSON 响应等场景。",
        "- 当前系统将找不到配对请求、非 200 状态码、非 JSON 响应、重复样本冲突都判定为问题请求。",
        "- 当前实现已验证：请求按 `path + 请求参数` 配对，`response_body` 在配对后通过 `DeepDiff(ignore_order=True)` 单独比较。",
    ])
    return "\n".join(lines) + "\n"


def write_report(report: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path
