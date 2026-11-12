"""MCP-compatible tool definitions and JSON-RPC dispatcher for VIRA (Q-05a readiness)."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional

from vira.service import ViraService


MCP_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "vira_list_portfolios",
        "description": "List available portfolio snapshots with mode, free cash, and commission config.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "vira_get_overview",
        "description": "Compute deterministic 21-session scenario forecast, risk limits (45%/10%), and position contributions.",
        "inputSchema": {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "vira_analyze_asset",
        "description": "Return instrument card with history, scenarios, separated facts/sources, data status, and guarded VIRA verdict.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "asset_key": {"type": "string"},
            },
            "required": ["portfolio_id", "asset_key"],
        },
    },
    {
        "name": "vira_compare_options",
        "description": "Compare hold, sell-to-cash, replacement, or top-up options with limit validation and Q-04e ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "target_key": {"type": "string"},
                "replacement_key": {"type": "string"},
                "commission_rate_bps": {"type": "number"},
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "vira_simulate_what_if",
        "description": "Run custom What-If simulation supporting partial sales, swaps from net proceeds, and commissions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "action": {"type": "string", "enum": ["partial_sell", "replace", "buy"]},
                "target_key": {"type": "string"},
                "replacement_key": {"type": "string"},
                "sell_share_pct": {"type": "number"},
                "buy_amount_rub": {"type": "number"},
                "commission_rate_bps": {"type": "number"},
            },
            "required": ["portfolio_id", "action", "target_key"],
        },
    },
    {
        "name": "vira_refresh_news",
        "description": "Fetch, deduplicate, and link live Russian financial news (CBR Tier 1, Interfax/RBC Tier 2, optional Smart-Lab Tier 3) via Exposure Profiles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_tier3": {"type": "boolean"},
                "save_cache": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "vira_get_news",
        "description": "Return collected live news items with trust tier, source URL, and matched portfolio instruments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_key": {"type": "string"},
                "trust_tier": {
                    "type": "string",
                    "enum": ["tier1_official", "tier2_media", "tier3_quarantine"],
                },
            },
            "additionalProperties": False,
        },
    },
]


class ViraMCPHandler:
    """Handles MCP JSON-RPC requests (`initialize`, `tools/list`, `tools/call`) using ViraService."""

    def __init__(self, service: Optional[ViraService] = None) -> None:
        self.service = service or ViraService()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "vira_list_portfolios":
            return {"portfolios": self.service.list_portfolios()}
        if name == "vira_get_overview":
            return self.service.get_overview(arguments["portfolio_id"])
        if name == "vira_analyze_asset":
            return self.service.get_asset_card(arguments["portfolio_id"], arguments["asset_key"])
        if name == "vira_compare_options":
            bps = arguments.get("commission_rate_bps")
            return self.service.get_compare(
                arguments["portfolio_id"],
                target_key=arguments.get("target_key"),
                replacement_key=arguments.get("replacement_key"),
                commission_rate_bps=Decimal(str(bps)) if bps is not None else None,
            )
        if name == "vira_simulate_what_if":
            bps = arguments.get("commission_rate_bps")
            buy_amt = arguments.get("buy_amount_rub")
            return self.service.simulate_what_if(
                portfolio_id=arguments["portfolio_id"],
                action=arguments["action"],
                target_key=arguments["target_key"],
                replacement_key=arguments.get("replacement_key"),
                sell_share_pct=Decimal(str(arguments.get("sell_share_pct", 100))),
                buy_amount_rub=Decimal(str(buy_amt)) if buy_amt is not None else None,
                commission_rate_bps=Decimal(str(bps)) if bps is not None else None,
            )
        if name == "vira_refresh_news":
            return self.service.refresh_live_news(
                include_tier3=bool(arguments.get("include_tier3", False)),
                save_cache=bool(arguments.get("save_cache", False)),
            )
        if name == "vira_get_news":
            return self.service.get_live_news(
                asset_key=arguments.get("asset_key"),
                trust_tier=arguments.get("trust_tier"),
            )
        raise KeyError(f"Unknown MCP tool: {name}")

    def handle_jsonrpc(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = payload.get("id")
        method = payload.get("method", "")
        params = payload.get("params") or {}

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "vira-portfolio-mcp", "version": "1.0.0"},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOL_DEFINITIONS},
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            try:
                result = self.call_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                        "structuredContent": result,
                        "isError": False,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def run_stdio_mcp() -> None:
    """Run line-delimited JSON-RPC MCP server over stdin/stdout."""
    handler = ViraMCPHandler()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = handler.handle_jsonrpc(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_mcp()
