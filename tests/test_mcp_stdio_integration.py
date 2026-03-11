from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import anyio

try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except Exception:  # pragma: no cover
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(ClientSession is None or StdioServerParameters is None or stdio_client is None, "mcp client is required")
class McpStdioIntegrationTest(unittest.TestCase):
    def _run(self, coro):
        return anyio.run(coro)

    async def _list_tool_names(self) -> list[str]:
        server = StdioServerParameters(
            command="python3",
            args=["scripts/regression_mcp_server.py"],
            cwd=str(ROOT),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [tool.name for tool in tools.tools]

    async def _call_tool(self, name: str, arguments: dict) -> dict:
        server = StdioServerParameters(
            command="python3",
            args=["scripts/regression_mcp_server.py"],
            cwd=str(ROOT),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                self.assertFalse(result.isError, f"unexpected MCP isError for tool={name}: {result}")
                text_blocks = [item.text for item in result.content if getattr(item, "type", "") == "text"]
                self.assertTrue(text_blocks, f"tool={name} returned no text content: {result.content}")
                return json.loads(text_blocks[0])

    def test_list_tools_contains_new_mcp_tools(self):
        names = self._run(self._list_tool_names)
        required = {
            "run_regression_by_scenario",
            "run_regression_by_scenario_and_api",
            "run_regression_by_trace_pair",
            "replay_and_diff_by_scenario",
            "replay_and_diff_by_scenario_and_api",
            "replay_and_diff_by_trace_ids",
            "list_scenarios",
            "list_api_paths",
            "list_recent_batches",
            "get_batch_report",
        }
        self.assertTrue(required.issubset(set(names)), f"missing tools: {sorted(required - set(names))}")
        removed = {"run_api_regression", "run_api_regression_advanced"}
        self.assertTrue(set(names).isdisjoint(removed), f"removed tools still exposed: {sorted(set(names) & removed)}")

    def test_ping_tool(self):
        payload = self._run(lambda: self._call_tool("ping", {}))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server"], "json-regression")
        self.assertIn("version", payload)

    def test_trace_pair_validation_error(self):
        payload = self._run(
            lambda: self._call_tool(
                "run_regression_by_trace_pair",
                {
                    "old_trace_id": "OLD_001",
                    "new_trace_id": "",
                },
            )
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "INVALID_INPUT")
        self.assertIn("old_trace_id and new_trace_id are required", payload["message"])

    def test_replay_validation_error(self):
        payload = self._run(
            lambda: self._call_tool(
                "replay_and_diff_by_scenario",
                {
                    "source_scenario_id": "demo#old#1",
                    "target_base_url": "ftp://bad",
                },
            )
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "INVALID_INPUT")
        self.assertIn("must start with http:// or https://", payload["message"])

    def test_batch_report_validation_error(self):
        payload = self._run(lambda: self._call_tool("get_batch_report", {"batch_id": 0, "batch_code": ""}))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "INVALID_INPUT")
        self.assertIn("batch_id or batch_code is required", payload["message"])

    def test_recent_batches_validation_error(self):
        payload = self._run(lambda: self._call_tool("list_recent_batches", {"mode": "INVALID"}))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "INVALID_INPUT")
        self.assertIn("mode must be one of", payload["message"])


if __name__ == "__main__":
    unittest.main()
