#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from regression_demo.runner import RegressionJobParams, run_regression_job

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: mcp. Install with `python3 -m pip install mcp`."
    ) from exc


mcp = FastMCP("json-regression")


@mcp.tool(
    name="run_api_regression",
    description="Run regression by 3 required args: api_paths + old_scenario_id + new_scenario_id.",
)
def run_api_regression(
    api_paths: str,
    old_scenario_id: str,
    new_scenario_id: str,
) -> dict:
    return run_regression_job(
        RegressionJobParams(
            api_paths_arg=api_paths,
            old_scenario_id=old_scenario_id,
            new_scenario_id=new_scenario_id,
            operator="mcp",
        ),
        root=ROOT,
    )


@mcp.tool(
    name="run_api_regression_advanced",
    description="Run regression with optional batch/report options and dry-run support.",
)
def run_api_regression_advanced(
    api_paths: str,
    old_scenario_id: str,
    new_scenario_id: str,
    batch_code: str = "",
    batch_name: str = "接口回归任务",
    biz_name: str = "aml-web",
    operator: str = "mcp",
    remark: str = "",
    report_path: str = "",
    dry_run: bool = False,
) -> dict:
    return run_regression_job(
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
        ),
        root=ROOT,
    )


@mcp.tool(name="ping", description="Return MCP server health status.")
def ping() -> dict:
    return {"ok": True, "server": "json-regression"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
