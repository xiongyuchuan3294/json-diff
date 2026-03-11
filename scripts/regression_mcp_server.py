#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.config import TARGET_SCHEMA, get_demo_db_config, with_database
from regression_demo.db import DbClient
from regression_demo.normalizer import normalize_path
from regression_demo.replay import validate_replay_runtime_options
from regression_demo.runner import RegressionJobParams, run_regression_job

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    _MCP_IMPORT_ERROR = exc

    class FastMCP:  # type: ignore[override]
        def __init__(self, _name: str):
            self.name = _name

        def tool(self, **_kwargs):
            def decorator(func):
                return func

            return decorator

        def run(self, **_kwargs):
            raise SystemExit("Missing dependency: mcp. Install with `python3 -m pip install mcp`.")

else:
    _MCP_IMPORT_ERROR = None


mcp = FastMCP("json-regression")
DEFAULT_BATCH_NAME = "接口回归任务"
DEFAULT_BIZ_NAME = "aml-web"
DEFAULT_OPERATOR = "mcp"
DEFAULT_LIMIT = 20
MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def _target_db() -> DbClient:
    return DbClient(with_database(get_demo_db_config(), TARGET_SCHEMA))


def _serialize_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append({key: _serialize_value(value) for key, value in row.items()})
    return output


def _ok(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True}
    if data:
        payload.update(data)
    return payload


def _error(
    *,
    error_code: str,
    message: str,
    hint: str = "",
    input_echo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "message": message,
    }
    if hint:
        payload["hint"] = hint
    if input_echo is not None:
        payload["input_echo"] = input_echo
    return payload


def _normalize_trace_ids(trace_ids: Sequence[str] | str) -> list[str]:
    if isinstance(trace_ids, str):
        parts = trace_ids.split(",")
    else:
        parts = [str(item) for item in trace_ids]
    rows: list[str] = []
    for item in parts:
        trace_id = str(item).strip()
        if trace_id:
            rows.append(trace_id)
    return list(dict.fromkeys(rows))


def _validate_replay_options(
    *,
    target_base_url: str,
    replay_speed_factor: float,
    replay_min_gap_ms: int,
    replay_max_gap_ms: int,
    replay_timeout_ms: int,
    replay_retries: int,
    input_echo: dict[str, Any],
) -> dict[str, Any] | None:
    replay_error = validate_replay_runtime_options(
        target_base_url=target_base_url,
        replay_speed_factor=replay_speed_factor,
        replay_min_gap_ms=replay_min_gap_ms,
        replay_max_gap_ms=replay_max_gap_ms,
        replay_timeout_ms=replay_timeout_ms,
        replay_retries=replay_retries,
    )
    if replay_error is None:
        return None

    hint_map = {
        "TARGET_BASE_URL_REQUIRED": "Use an http:// or https:// base URL.",
        "TARGET_BASE_URL_SCHEME": "Example: https://api.example.com",
    }
    return _error(
        error_code="INVALID_INPUT",
        message=replay_error.message,
        hint=hint_map.get(replay_error.code, ""),
        input_echo=input_echo,
    )


def _run_job(params: RegressionJobParams, *, input_echo: dict[str, Any]) -> dict[str, Any]:
    try:
        return _ok(run_regression_job(params, root=ROOT))
    except Exception as exc:  # noqa: BLE001
        return _error(
            error_code="JOB_EXECUTION_FAILED",
            message=str(exc),
            hint="Verify selector inputs and DB connectivity, then retry.",
            input_echo=input_echo,
        )


@mcp.tool(
    name="run_regression_by_scenario",
    description="Run regression by scenario pair. Supports optional api_paths/fuzzy/dry_run.",
)
def run_regression_by_scenario(
    old_scenario_id: str,
    new_scenario_id: str,
    api_paths: str = "ALL",
    fuzzy: bool = False,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
) -> dict[str, Any]:
    input_echo = {
        "old_scenario_id": old_scenario_id,
        "new_scenario_id": new_scenario_id,
        "api_paths": api_paths,
        "fuzzy": fuzzy,
        "dry_run": dry_run,
    }
    if not (old_scenario_id or "").strip() or not (new_scenario_id or "").strip():
        return _error(
            error_code="INVALID_INPUT",
            message="old_scenario_id and new_scenario_id are required",
            hint="Use run_regression_by_trace_pair for trace-level compare.",
            input_echo=input_echo,
        )

    return _run_job(
        RegressionJobParams(
            api_paths_arg=api_paths,
            old_scenario_id=old_scenario_id,
            new_scenario_id=new_scenario_id,
            batch_code=batch_code,
            batch_name=batch_name,
            biz_name=biz_name,
            operator=operator,
            remark=remark,
            report_path=report_path or None,
            dry_run=dry_run,
            fuzzy_match=fuzzy,
        ),
        input_echo=input_echo,
    )


@mcp.tool(
    name="run_regression_by_scenario_and_api",
    description="Run regression by scenario pair with one api_path.",
)
def run_regression_by_scenario_and_api(
    old_scenario_id: str,
    new_scenario_id: str,
    api_path: str,
    fuzzy: bool = False,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
) -> dict[str, Any]:
    api_path_value = (api_path or "").strip()
    input_echo = {
        "old_scenario_id": old_scenario_id,
        "new_scenario_id": new_scenario_id,
        "api_path": api_path_value,
        "fuzzy": fuzzy,
        "dry_run": dry_run,
    }
    if not api_path_value:
        return _error(
            error_code="INVALID_INPUT",
            message="api_path is required",
            hint="Example: /aml/wst/custTransInfo",
            input_echo=input_echo,
        )
    if "," in api_path_value:
        return _error(
            error_code="INVALID_INPUT",
            message="api_path must be a single path, comma-separated values are not supported",
            hint="Use run_regression_by_scenario(api_paths='path1,path2') for multiple paths.",
            input_echo=input_echo,
        )
    return run_regression_by_scenario(
        old_scenario_id=old_scenario_id,
        new_scenario_id=new_scenario_id,
        api_paths=api_path_value,
        fuzzy=fuzzy,
        dry_run=dry_run,
        batch_code=batch_code,
        batch_name=batch_name,
        biz_name=biz_name,
        operator=operator,
        remark=remark,
        report_path=report_path,
    )


@mcp.tool(
    name="run_regression_by_trace_pair",
    description="Run regression by one old/new trace_id pair.",
)
def run_regression_by_trace_pair(
    old_trace_id: str,
    new_trace_id: str,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
) -> dict[str, Any]:
    input_echo = {
        "old_trace_id": old_trace_id,
        "new_trace_id": new_trace_id,
        "dry_run": dry_run,
    }
    if not (old_trace_id or "").strip() or not (new_trace_id or "").strip():
        return _error(
            error_code="INVALID_INPUT",
            message="old_trace_id and new_trace_id are required",
            input_echo=input_echo,
        )

    return _run_job(
        RegressionJobParams(
            api_paths_arg="ALL",
            old_trace_id=old_trace_id,
            new_trace_id=new_trace_id,
            batch_code=batch_code,
            batch_name=batch_name,
            biz_name=biz_name,
            operator=operator,
            remark=remark,
            report_path=report_path or None,
            dry_run=dry_run,
        ),
        input_echo=input_echo,
    )


@mcp.tool(name="ping", description="Return MCP server health status.")
def ping() -> dict[str, Any]:
    return _ok(
        {
            "server": "json-regression",
            "schema": TARGET_SCHEMA,
            "version": "2026-03-11",
        }
    )


@mcp.tool(
    name="replay_and_diff_by_scenario",
    description="Replay by source scenario_id (optional api_paths filter) and auto run diff.",
)
def replay_and_diff_by_scenario(
    source_scenario_id: str,
    target_base_url: str,
    api_paths: str = "ALL",
    fuzzy: bool = False,
    replay_speed_factor: float = 1.0,
    replay_min_gap_ms: int = 300,
    replay_max_gap_ms: int = 3000,
    replay_timeout_ms: int = 10000,
    replay_retries: int = 1,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
    replay_code: str = "",
) -> dict[str, Any]:
    input_echo = {
        "source_scenario_id": source_scenario_id,
        "target_base_url": target_base_url,
        "api_paths": api_paths,
        "fuzzy": fuzzy,
        "dry_run": dry_run,
    }
    if not (source_scenario_id or "").strip():
        return _error(
            error_code="INVALID_INPUT",
            message="source_scenario_id is required",
            input_echo=input_echo,
        )
    replay_error = _validate_replay_options(
        target_base_url=target_base_url,
        replay_speed_factor=replay_speed_factor,
        replay_min_gap_ms=replay_min_gap_ms,
        replay_max_gap_ms=replay_max_gap_ms,
        replay_timeout_ms=replay_timeout_ms,
        replay_retries=replay_retries,
        input_echo=input_echo,
    )
    if replay_error:
        return replay_error

    return _run_job(
        RegressionJobParams(
            api_paths_arg=api_paths,
            batch_code=batch_code,
            batch_name=batch_name,
            biz_name=biz_name,
            operator=operator,
            remark=remark,
            report_path=report_path or None,
            dry_run=dry_run,
            fuzzy_match=fuzzy,
            replay=True,
            replay_target_base_url=target_base_url,
            replay_source_scenario_id=source_scenario_id,
            replay_trace_ids="",
            replay_speed_factor=replay_speed_factor,
            replay_min_gap_ms=replay_min_gap_ms,
            replay_max_gap_ms=replay_max_gap_ms,
            replay_timeout_ms=replay_timeout_ms,
            replay_retries=replay_retries,
            replay_code=replay_code,
        ),
        input_echo=input_echo,
    )


@mcp.tool(
    name="replay_and_diff_by_scenario_and_api",
    description="Replay by scenario with one api_path and auto run diff.",
)
def replay_and_diff_by_scenario_and_api(
    source_scenario_id: str,
    target_base_url: str,
    api_path: str,
    fuzzy: bool = False,
    replay_speed_factor: float = 1.0,
    replay_min_gap_ms: int = 300,
    replay_max_gap_ms: int = 3000,
    replay_timeout_ms: int = 10000,
    replay_retries: int = 1,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
    replay_code: str = "",
) -> dict[str, Any]:
    api_path_value = (api_path or "").strip()
    input_echo = {
        "source_scenario_id": source_scenario_id,
        "target_base_url": target_base_url,
        "api_path": api_path_value,
        "fuzzy": fuzzy,
        "dry_run": dry_run,
    }
    if not api_path_value:
        return _error(
            error_code="INVALID_INPUT",
            message="api_path is required",
            hint="Example: /aml/wst/custTransInfo",
            input_echo=input_echo,
        )
    if "," in api_path_value:
        return _error(
            error_code="INVALID_INPUT",
            message="api_path must be a single path, comma-separated values are not supported",
            hint="Use replay_and_diff_by_scenario(api_paths='path1,path2') for multiple paths.",
            input_echo=input_echo,
        )
    return replay_and_diff_by_scenario(
        source_scenario_id=source_scenario_id,
        target_base_url=target_base_url,
        api_paths=api_path_value,
        fuzzy=fuzzy,
        replay_speed_factor=replay_speed_factor,
        replay_min_gap_ms=replay_min_gap_ms,
        replay_max_gap_ms=replay_max_gap_ms,
        replay_timeout_ms=replay_timeout_ms,
        replay_retries=replay_retries,
        dry_run=dry_run,
        batch_code=batch_code,
        batch_name=batch_name,
        biz_name=biz_name,
        operator=operator,
        remark=remark,
        report_path=report_path,
        replay_code=replay_code,
    )


@mcp.tool(
    name="replay_and_diff_by_trace_ids",
    description="Replay by trace_ids and auto run diff. trace_ids can be list or comma-separated string.",
)
def replay_and_diff_by_trace_ids(
    trace_ids: Sequence[str] | str,
    target_base_url: str,
    replay_speed_factor: float = 1.0,
    replay_min_gap_ms: int = 300,
    replay_max_gap_ms: int = 3000,
    replay_timeout_ms: int = 10000,
    replay_retries: int = 1,
    dry_run: bool = False,
    batch_code: str = "",
    batch_name: str = DEFAULT_BATCH_NAME,
    biz_name: str = DEFAULT_BIZ_NAME,
    operator: str = DEFAULT_OPERATOR,
    remark: str = "",
    report_path: str = "",
    replay_code: str = "",
) -> dict[str, Any]:
    trace_list = _normalize_trace_ids(trace_ids)
    input_echo = {
        "trace_ids": trace_list,
        "target_base_url": target_base_url,
        "dry_run": dry_run,
    }
    if not trace_list:
        return _error(
            error_code="INVALID_INPUT",
            message="trace_ids is required",
            hint="Provide trace_ids like ['T1','T2'] or 'T1,T2'.",
            input_echo=input_echo,
        )
    replay_error = _validate_replay_options(
        target_base_url=target_base_url,
        replay_speed_factor=replay_speed_factor,
        replay_min_gap_ms=replay_min_gap_ms,
        replay_max_gap_ms=replay_max_gap_ms,
        replay_timeout_ms=replay_timeout_ms,
        replay_retries=replay_retries,
        input_echo=input_echo,
    )
    if replay_error:
        return replay_error

    return _run_job(
        RegressionJobParams(
            api_paths_arg="ALL",
            batch_code=batch_code,
            batch_name=batch_name,
            biz_name=biz_name,
            operator=operator,
            remark=remark,
            report_path=report_path or None,
            dry_run=dry_run,
            replay=True,
            replay_target_base_url=target_base_url,
            replay_source_scenario_id="",
            replay_trace_ids=",".join(trace_list),
            replay_speed_factor=replay_speed_factor,
            replay_min_gap_ms=replay_min_gap_ms,
            replay_max_gap_ms=replay_max_gap_ms,
            replay_timeout_ms=replay_timeout_ms,
            replay_retries=replay_retries,
            replay_code=replay_code,
        ),
        input_echo=input_echo,
    )


@mcp.tool(
    name="list_scenarios",
    description="List recent scenario_id candidates from t_request_info to reduce manual input cost.",
)
def list_scenarios(limit: int = DEFAULT_LIMIT, keyword: str = "") -> dict[str, Any]:
    db = _target_db()
    limited = _clamp_limit(limit)
    keyword_value = (keyword or "").strip()
    params: list[Any] = []
    condition = ""
    if keyword_value:
        condition = " AND scenario_id LIKE %s"
        params.append(f"%{keyword_value}%")

    rows = db.query(
        f"""
        SELECT scenario_id, COUNT(*) AS request_count, MIN(start_time) AS first_start_time, MAX(start_time) AS last_start_time
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND scenario_id IS NOT NULL
          AND scenario_id <> ''
          {condition}
        GROUP BY scenario_id
        ORDER BY last_start_time DESC
        LIMIT %s
        """,
        tuple([*params, limited]),
    )
    return _ok(
        {
            "schema": TARGET_SCHEMA,
            "items": _serialize_rows(rows),
            "total": len(rows),
        }
    )


@mcp.tool(
    name="list_api_paths",
    description="List normalized API paths under a scenario_id.",
)
def list_api_paths(scenario_id: str, limit: int = 50, keyword: str = "") -> dict[str, Any]:
    scenario = (scenario_id or "").strip()
    if not scenario:
        return _error(
            error_code="INVALID_INPUT",
            message="scenario_id is required",
            input_echo={"scenario_id": scenario_id},
        )

    db = _target_db()
    rows = db.query(
        f"""
        SELECT url
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND scenario_id = %s
        """,
        (scenario,),
    )
    counter: dict[str, int] = {}
    keyword_value = (keyword or "").strip()
    for row in rows:
        path = normalize_path(str(row.get("url") or ""))
        if not path:
            continue
        if keyword_value and keyword_value not in path:
            continue
        counter[path] = counter.get(path, 0) + 1

    items = [
        {"api_path": path, "request_count": count}
        for path, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ][: _clamp_limit(limit)]
    return _ok(
        {
            "scenario_id": scenario,
            "items": items,
            "total": len(items),
        }
    )


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return datetime.min


@mcp.tool(
    name="list_recent_batches",
    description="List recent regression/replay batches for quick navigation.",
)
def list_recent_batches(limit: int = DEFAULT_LIMIT, mode: str = "ALL") -> dict[str, Any]:
    mode_value = (mode or "ALL").strip().upper()
    if mode_value not in {"ALL", "REGRESSION", "REPLAY"}:
        return _error(
            error_code="INVALID_INPUT",
            message="mode must be one of: ALL, REGRESSION, REPLAY",
            input_echo={"mode": mode},
        )

    db = _target_db()
    limited = _clamp_limit(limit)
    items: list[dict[str, Any]] = []
    if mode_value in {"ALL", "REGRESSION"}:
        rows = db.query(
            f"""
            SELECT id, batch_code, batch_name, status, old_scenario_id, new_scenario_id, created_time, start_time, end_time
            FROM `{TARGET_SCHEMA}`.`t_regression_batch`
            ORDER BY id DESC
            LIMIT %s
            """,
            (limited,),
        )
        for row in rows:
            items.append(
                {
                    "batch_type": "REGRESSION",
                    **row,
                }
            )
    if mode_value in {"ALL", "REPLAY"}:
        rows = db.query(
            f"""
            SELECT id, replay_code, replay_name, status, source_scenario_id, replay_scenario_id, created_time, start_time, end_time
            FROM `{TARGET_SCHEMA}`.`t_replay_batch`
            ORDER BY id DESC
            LIMIT %s
            """,
            (limited,),
        )
        for row in rows:
            items.append(
                {
                    "batch_type": "REPLAY",
                    **row,
                }
            )

    items = sorted(items, key=lambda row: _to_datetime(row.get("created_time")), reverse=True)[:limited]
    return _ok({"mode": mode_value, "items": _serialize_rows(items), "total": len(items)})


@mcp.tool(
    name="get_batch_report",
    description="Get one regression batch summary by batch_id or batch_code.",
)
def get_batch_report(
    batch_id: int = 0,
    batch_code: str = "",
    include_results: bool = False,
    result_limit: int = 20,
) -> dict[str, Any]:
    code = (batch_code or "").strip()
    if not batch_id and not code:
        return _error(
            error_code="INVALID_INPUT",
            message="batch_id or batch_code is required",
            input_echo={"batch_id": batch_id, "batch_code": batch_code},
        )

    db = _target_db()
    batch = db.query_one(
        f"SELECT * FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE {'id = %s' if batch_id else 'batch_code = %s'} LIMIT 1",
        (batch_id or code,),
    )
    if not batch:
        return _error(
            error_code="NOT_FOUND",
            message="regression batch not found",
            input_echo={"batch_id": batch_id, "batch_code": batch_code},
        )

    resolved_batch_id = int(batch["id"])
    summary_rows = db.query(
        f"""
        SELECT compare_status, diff_level, COUNT(*) AS cnt
        FROM `{TARGET_SCHEMA}`.`t_compare_result`
        WHERE batch_id = %s
        GROUP BY compare_status, diff_level
        ORDER BY compare_status, diff_level
        """,
        (resolved_batch_id,),
    )
    output: dict[str, Any] = {
        "batch": _serialize_rows([batch])[0],
        "summary": _serialize_rows(summary_rows),
    }
    report_file = ROOT / "output" / str(batch.get("batch_code") or "") / "测试报告.md"
    output["report_path"] = str(report_file)
    output["report_exists"] = report_file.exists()

    if include_results:
        rows = db.query(
            f"""
            SELECT id, pair_status, compare_status, diff_level, api_path, old_trace_id, new_trace_id, summary
            FROM `{TARGET_SCHEMA}`.`t_compare_result`
            WHERE batch_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (resolved_batch_id, _clamp_limit(result_limit)),
        )
        output["results"] = _serialize_rows(rows)
    return _ok(output)


if __name__ == "__main__":
    if _MCP_IMPORT_ERROR is not None:
        raise SystemExit("Missing dependency: mcp. Install with `python3 -m pip install mcp`.")
    mcp.run(transport="stdio")
