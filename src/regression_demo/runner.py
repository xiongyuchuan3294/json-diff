from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import TARGET_SCHEMA, get_demo_db_config, with_database
from .db import DbClient
from .normalizer import normalize_path
from .reporting import write_report
from .service import build_request_index, collect_report_data, create_regression_batch, run_regression


@dataclass
class RegressionJobParams:
    api_paths_arg: str
    old_scenario_id: str
    new_scenario_id: str
    batch_code: str = ""
    batch_name: str = "接口回归任务"
    biz_name: str = "aml-web"
    operator: str = "codex"
    remark: str = ""
    env_tag: str = "runtime"
    report_path: str | None = None
    write_latest: bool = True
    dry_run: bool = False


def normalize_api_paths(api_paths_arg: str | None) -> list[str]:
    value = (api_paths_arg or "").strip()
    if not value or value.upper() == "ALL" or value == "*":
        return []
    rows = []
    for item in value.split(","):
        path = item.strip()
        if path:
            rows.append(path)
    return list(dict.fromkeys(rows))


def default_batch_code(old_scenario_id: str, new_scenario_id: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_tag = old_scenario_id.split("#")[1] if "#" in old_scenario_id and len(old_scenario_id.split("#")) > 1 else "old"
    new_tag = new_scenario_id.split("#")[1] if "#" in new_scenario_id and len(new_scenario_id.split("#")) > 1 else "new"
    return f"REG_{old_tag}_{new_tag}_{timestamp}"


def _resolve_report_path(root: Path, batch_code: str, report_path: str | None) -> Path:
    if report_path:
        candidate = Path(report_path)
        return candidate if candidate.is_absolute() else root / candidate
    return root / "output" / batch_code / "测试报告.md"


def _collect_preflight(db: DbClient, old_scenario_id: str, new_scenario_id: str, selected_paths: list[str]) -> dict[str, Any]:
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
    for row in rows:
        path = normalize_path(row["url"])
        scenario_id = row["scenario_id"]
        if scenario_id == old_scenario_id:
            old_total += 1
            old_paths.add(path)
            if not selected_set or path in selected_set:
                old_selected += 1
        elif scenario_id == new_scenario_id:
            new_total += 1
            new_paths.add(path)
            if not selected_set or path in selected_set:
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


def run_regression_job(params: RegressionJobParams, root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[2]
    selected_paths = normalize_api_paths(params.api_paths_arg)
    scope_msg = "ALL_API_PATHS" if not selected_paths else ",".join(selected_paths)
    target_db = DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))
    preflight = _collect_preflight(target_db, params.old_scenario_id, params.new_scenario_id, selected_paths)

    if params.dry_run:
        return {
            "mode": "DRY_RUN",
            "schema": TARGET_SCHEMA,
            "scope": scope_msg,
            "preflight": preflight,
        }

    batch_code = params.batch_code or default_batch_code(params.old_scenario_id, params.new_scenario_id)
    indexed = build_request_index(
        target_db,
        scenario_ids=[params.old_scenario_id, params.new_scenario_id],
        api_paths=selected_paths or None,
        env_tag=params.env_tag,
    )
    batch_id = create_regression_batch(
        target_db,
        batch_code=batch_code,
        batch_name=params.batch_name,
        old_scenario_id=params.old_scenario_id,
        new_scenario_id=params.new_scenario_id,
        biz_name=params.biz_name,
        operator=params.operator,
        remark=params.remark,
    )
    stats = run_regression(
        target_db,
        batch_id,
        old_scenario_id=params.old_scenario_id,
        new_scenario_id=params.new_scenario_id,
        api_paths=selected_paths or None,
    )
    report = collect_report_data(target_db, batch_id)
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
        "preflight": preflight,
    }
