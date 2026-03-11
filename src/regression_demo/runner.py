from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import TARGET_SCHEMA, get_demo_db_config, with_database
from .db import DbClient
from .normalizer import normalize_path
from .reporting import write_report
from .service import (
    build_request_index,
    collect_report_data,
    create_regression_batch,
    run_regression,
    run_regression_by_trace_ids,
)


@dataclass
class RegressionJobParams:
    api_paths_arg: str = "ALL"
    old_scenario_id: str = ""
    new_scenario_id: str = ""
    batch_code: str = ""
    batch_name: str = "接口回归任务"
    biz_name: str = "aml-web"
    operator: str = "codex"
    remark: str = ""
    env_tag: str = "runtime"
    report_path: str | None = None
    write_latest: bool = True
    dry_run: bool = False
    fuzzy_match: bool = False
    old_trace_id: str = ""
    new_trace_id: str = ""


def normalize_api_paths(api_paths_arg: str | None) -> list[str]:
    value = (api_paths_arg or "").strip()
    if not value or value.upper() == "ALL" or value == "*":
        return []
    rows: list[str] = []
    for item in value.split(","):
        path = item.strip()
        if path:
            rows.append(path)
    return list(dict.fromkeys(rows))


def normalize_trace_id(trace_id: str | None) -> str:
    return (trace_id or "").strip()


def has_trace_pair(old_trace_id: str | None, new_trace_id: str | None) -> bool:
    return bool(normalize_trace_id(old_trace_id) and normalize_trace_id(new_trace_id))


def split_trace_ids_by_compare_status(results: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    success_trace_ids: list[str] = []
    failed_trace_ids: list[str] = []

    def append_unique(container: list[str], value: str) -> None:
        if value and value not in container:
            container.append(value)

    for row in results:
        if str(row.get("pair_status") or "").upper() != "MATCHED":
            continue
        compare_status = str(row.get("compare_status") or "").upper()
        diff_level = str(row.get("diff_level") or "").upper()
        is_success = compare_status == "SUCCESS" and diff_level != "BLOCK"
        target = success_trace_ids if is_success else failed_trace_ids
        for key in ("old_trace_id", "new_trace_id"):
            trace_id = normalize_trace_id(row.get(key))
            append_unique(target, trace_id)

    return success_trace_ids, failed_trace_ids


def default_batch_code(old_scenario_id: str, new_scenario_id: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_value = (old_scenario_id or "old").strip()
    new_value = (new_scenario_id or "new").strip()
    old_tag = old_value.split("#")[1] if "#" in old_value and len(old_value.split("#")) > 1 else "old"
    new_tag = new_value.split("#")[1] if "#" in new_value and len(new_value.split("#")) > 1 else "new"
    return f"REG_{old_tag}_{new_tag}_{timestamp}"


def _resolve_report_path(root: Path, batch_code: str, report_path: str | None) -> Path:
    if report_path:
        candidate = Path(report_path)
        return candidate if candidate.is_absolute() else root / candidate
    return root / "output" / batch_code / "测试报告.md"


def _collect_preflight(
    db: DbClient,
    old_scenario_id: str,
    new_scenario_id: str,
    selected_paths: list[str],
    fuzzy_match: bool = False,
) -> dict[str, Any]:
    rows = db.query(
        f"""
        SELECT scenario_id, url
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND scenario_id IN (%s, %s)
        """,
        (old_scenario_id, new_scenario_id),
    )
    old_total = 0
    new_total = 0
    old_selected = 0
    new_selected = 0
    old_paths: set[str] = set()
    new_paths: set[str] = set()

    selected_set = set(selected_paths)

    def path_matches(path: str) -> bool:
        if not selected_set:
            return True
        if fuzzy_match:
            return any(path.startswith(p) for p in selected_set)
        return path in selected_set

    for row in rows:
        path = normalize_path(row["url"])
        scenario_id = row["scenario_id"]
        if scenario_id == old_scenario_id:
            old_total += 1
            old_paths.add(path)
            if path_matches(path):
                old_selected += 1
        elif scenario_id == new_scenario_id:
            new_total += 1
            new_paths.add(path)
            if path_matches(path):
                new_selected += 1

    common_paths = sorted(old_paths & new_paths)
    warnings: list[str] = []
    if old_total == 0:
        warnings.append(f"old_scenario_id has no samples: {old_scenario_id}")
    if new_total == 0:
        warnings.append(f"new_scenario_id has no samples: {new_scenario_id}")
    if old_selected == 0 or new_selected == 0:
        warnings.append("selected api_paths has no samples on one side")
    if old_selected > 0 and new_selected > 0 and not common_paths:
        warnings.append("both sides have samples but no common api path")

    return {
        "old_total_count": old_total,
        "new_total_count": new_total,
        "old_selected_count": old_selected,
        "new_selected_count": new_selected,
        "selected_api_paths": selected_paths or ["ALL_API_PATHS"],
        "common_api_path_count": len(common_paths),
        "common_api_paths_preview": common_paths[:20],
        "warnings": warnings,
    }


def _collect_trace_pair_preflight(db: DbClient, old_trace_id: str, new_trace_id: str) -> dict[str, Any]:
    rows = db.query(
        f"""
        SELECT id, trace_id, scenario_id, url, method
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND trace_id IN (%s, %s)
        ORDER BY id DESC
        """,
        (old_trace_id, new_trace_id),
    )
    old_rows = [row for row in rows if row.get("trace_id") == old_trace_id]
    new_rows = [row for row in rows if row.get("trace_id") == new_trace_id]
    old_path = normalize_path(old_rows[0]["url"]) if old_rows else ""
    new_path = normalize_path(new_rows[0]["url"]) if new_rows else ""
    old_method = old_rows[0]["method"] if old_rows else ""
    new_method = new_rows[0]["method"] if new_rows else ""

    warnings: list[str] = []
    if not old_rows:
        warnings.append(f"old_trace_id not found: {old_trace_id}")
    if not new_rows:
        warnings.append(f"new_trace_id not found: {new_trace_id}")
    if len(old_rows) > 1:
        warnings.append(f"old_trace_id matched multiple rows: {old_trace_id} (count={len(old_rows)})")
    if len(new_rows) > 1:
        warnings.append(f"new_trace_id matched multiple rows: {new_trace_id} (count={len(new_rows)})")
    if old_path and new_path and old_path != new_path:
        warnings.append(f"trace pair api_path differs: old={old_path}, new={new_path}")
    if old_method and new_method and old_method != new_method:
        warnings.append(f"trace pair method differs: old={old_method}, new={new_method}")

    return {
        "mode": "TRACE_ID_PAIR",
        "old_trace_id": old_trace_id,
        "new_trace_id": new_trace_id,
        "old_total_count": len(old_rows),
        "new_total_count": len(new_rows),
        "old_selected_count": 1 if old_rows else 0,
        "new_selected_count": 1 if new_rows else 0,
        "selected_api_paths": [path for path in [old_path, new_path] if path] or ["TRACE_ID_PAIR"],
        "common_api_path_count": 1 if old_path and new_path and old_path == new_path else 0,
        "common_api_paths_preview": [old_path] if old_path and new_path and old_path == new_path else [],
        "old_scenario_id": old_rows[0]["scenario_id"] if old_rows else "",
        "new_scenario_id": new_rows[0]["scenario_id"] if new_rows else "",
        "warnings": warnings,
    }


def run_regression_job(params: RegressionJobParams, root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[2]
    old_trace_id = normalize_trace_id(params.old_trace_id)
    new_trace_id = normalize_trace_id(params.new_trace_id)
    trace_mode = has_trace_pair(old_trace_id, new_trace_id)

    selected_paths = normalize_api_paths(params.api_paths_arg)
    scope_msg = "ALL_API_PATHS" if not selected_paths else ",".join(selected_paths)
    if trace_mode:
        scope_msg = f"TRACE_ID_PAIR:{old_trace_id},{new_trace_id}"

    target_db = DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))
    preflight = (
        _collect_trace_pair_preflight(target_db, old_trace_id, new_trace_id)
        if trace_mode
        else _collect_preflight(target_db, params.old_scenario_id, params.new_scenario_id, selected_paths, params.fuzzy_match)
    )

    if params.dry_run:
        return {
            "mode": "DRY_RUN",
            "schema": TARGET_SCHEMA,
            "scope": scope_msg,
            "preflight": preflight,
        }

    old_scenario_id = params.old_scenario_id
    new_scenario_id = params.new_scenario_id
    if trace_mode:
        if preflight["old_selected_count"] != 1 or preflight["new_selected_count"] != 1:
            raise ValueError("trace_id pair must match exactly one old sample and one new sample")
        old_scenario_id = old_scenario_id or preflight.get("old_scenario_id", "") or "trace-old"
        new_scenario_id = new_scenario_id or preflight.get("new_scenario_id", "") or "trace-new"

    batch_code = params.batch_code or default_batch_code(old_scenario_id, new_scenario_id)

    if trace_mode:
        indexed = build_request_index(
            target_db,
            trace_ids=[old_trace_id, new_trace_id],
            env_tag=params.env_tag,
        )
    else:
        indexed = build_request_index(
            target_db,
            scenario_ids=[old_scenario_id, new_scenario_id],
            api_paths=selected_paths or None,
            env_tag=params.env_tag,
            fuzzy_match=params.fuzzy_match,
        )

    batch_id = create_regression_batch(
        target_db,
        batch_code=batch_code,
        batch_name=params.batch_name,
        old_scenario_id=old_scenario_id,
        new_scenario_id=new_scenario_id,
        biz_name=params.biz_name,
        operator=params.operator,
        remark=params.remark,
    )

    if trace_mode:
        stats = run_regression_by_trace_ids(
            target_db,
            batch_id,
            old_scenario_id=old_scenario_id,
            new_scenario_id=new_scenario_id,
            old_trace_id=old_trace_id,
            new_trace_id=new_trace_id,
        )
    else:
        stats = run_regression(
            target_db,
            batch_id,
            old_scenario_id=old_scenario_id,
            new_scenario_id=new_scenario_id,
            api_paths=selected_paths or None,
            fuzzy_match=params.fuzzy_match,
        )

    report = collect_report_data(target_db, batch_id)
    success_trace_ids, failed_trace_ids = split_trace_ids_by_compare_status(report.get("results", []))
    report_file = write_report(report, _resolve_report_path(project_root, batch_code, params.report_path))
    latest_file: Path | None = None
    if params.write_latest:
        latest_file = write_report(report, project_root / "output" / "latest.md")

    return {
        "mode": "RUN",
        "batch_id": batch_id,
        "batch_code": batch_code,
        "schema": TARGET_SCHEMA,
        "indexed_count": indexed,
        "scope": scope_msg,
        "stats": stats,
        "report_path": str(report_file),
        "latest_report_path": str(latest_file) if latest_file else "",
        "compare_success_trace_ids": success_trace_ids,
        "compare_failed_trace_ids": failed_trace_ids,
        "preflight": preflight,
    }
