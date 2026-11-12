"""Zero-dependency HTTP/REST server hosting the VIRA Stage 4 Web MVP and API."""

from __future__ import annotations

import argparse
import json
import mimetypes
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from vira import ENGINE_VERSION
from vira.mcp_tools import MCP_TOOL_DEFINITIONS, ViraMCPHandler
from vira.service import ViraService

WEB_DIR = Path(__file__).resolve().parent / "web"


def _make_handler(service: ViraService, web_dir: Path) -> type[BaseHTTPRequestHandler]:
    mcp_handler = ViraMCPHandler(service)

    class ViraRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Suppress noisy default stderr access logging during automated tests unless desired
            pass

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, file_path: Path) -> None:
            if not file_path.exists() or not file_path.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
                return
            content_type, _ = mimetypes.guess_type(str(file_path))
            if file_path.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif file_path.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif file_path.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            elif content_type is None:
                content_type = "application/octet-stream"

            data = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)

            if path.startswith("/api/"):
                self._handle_api_get(path, query)
                return

            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            candidate = (web_dir / rel).resolve()
            if not candidate.is_relative_to(web_dir.resolve()):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden"})
                return
            self._send_file(candidate)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            try:
                body = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON: {exc}"})
                return

            if path == "/api/simulate":
                try:
                    bps_raw = body.get("commission_rate_bps")
                    buy_raw = body.get("buy_amount_rub")
                    sell_raw = body.get("sell_share_pct", "100")
                    payload = service.simulate_what_if(
                        portfolio_id=str(body["portfolio_id"]),
                        action=str(body["action"]),
                        target_key=str(body["target_key"]),
                        replacement_key=body.get("replacement_key"),
                        sell_share_pct=Decimal(str(sell_raw)),
                        buy_amount_rub=Decimal(str(buy_raw)) if buy_raw is not None else None,
                        commission_rate_bps=Decimal(str(bps_raw)) if bps_raw is not None else None,
                    )
                    self._send_json(HTTPStatus.OK, payload)
                except (KeyError, InvalidOperation, ValueError) as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if path == "/api/news/refresh":
                include_tier3 = bool(body.get("include_tier3", False))
                save_cache = bool(body.get("save_cache", True))
                payload = service.refresh_live_news(
                    include_tier3=include_tier3,
                    save_cache=save_cache,
                )
                self._send_json(HTTPStatus.OK, payload)
                return

            if path == "/api/mcp/rpc":
                resp = mcp_handler.handle_jsonrpc(body)
                self._send_json(HTTPStatus.OK, resp or {"status": "accepted"})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint"})

        def _handle_api_get(self, path: str, query: Dict[str, list[str]]) -> None:
            try:
                if path == "/api/health":
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "status": "ok",
                            "engine_version": ENGINE_VERSION,
                            "agent_mode": service.requested_agent_mode,
                            "llm_configured": service.llm_explainer.is_configured(),
                        },
                    )
                    return

                if path == "/api/portfolios":
                    self._send_json(HTTPStatus.OK, {"portfolios": service.list_portfolios()})
                    return

                if path == "/api/mcp/tools":
                    self._send_json(HTTPStatus.OK, {"tools": MCP_TOOL_DEFINITIONS})
                    return

                if path == "/api/news":
                    asset_key = query.get("asset_key", [None])[0]
                    trust_tier = query.get("trust_tier", [None])[0]
                    self._send_json(
                        HTTPStatus.OK,
                        service.get_live_news(asset_key=asset_key, trust_tier=trust_tier),
                    )
                    return

                parts = [p for p in path.split("/") if p]
                # Expected: ["api", "portfolios", pid, ...]
                if len(parts) == 4 and parts[0] == "api" and parts[1] == "portfolios" and parts[3] == "overview":
                    self._send_json(HTTPStatus.OK, service.get_overview(parts[2]))
                    return

                if len(parts) == 5 and parts[0] == "api" and parts[1] == "portfolios" and parts[3] == "assets":
                    self._send_json(HTTPStatus.OK, service.get_asset_card(parts[2], parts[4]))
                    return

                if len(parts) == 4 and parts[0] == "api" and parts[1] == "portfolios" and parts[3] == "compare":
                    target = query.get("target", [None])[0]
                    replacement = query.get("replacement", [None])[0]
                    bps_str = query.get("commission_rate_bps", [None])[0]
                    bps = Decimal(bps_str) if bps_str is not None else None
                    self._send_json(
                        HTTPStatus.OK,
                        service.get_compare(
                            parts[2],
                            target_key=target,
                            replacement_key=replacement,
                            commission_rate_bps=bps,
                        ),
                    )
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint"})
            except KeyError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (InvalidOperation, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return ViraRequestHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    service: Optional[ViraService] = None,
    web_dir: Path = WEB_DIR,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer instance."""
    svc = service or ViraService()
    handler_cls = _make_handler(svc, web_dir)
    return ThreadingHTTPServer((host, port), handler_cls)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="VIRA Stage 4 Web MVP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument(
        "--agent-mode",
        choices=["rule_based", "llm"],
        default=None,
        help="Agent explanation mode (default: rule_based, or VIRA_AGENT_MODE env)",
    )
    parser.add_argument(
        "--live-news",
        action="store_true",
        help="Fetch live RSS news from CBR, Interfax, and RBC on startup",
    )
    args = parser.parse_args(argv)

    service = ViraService(agent_mode=args.agent_mode, auto_load_news_cache=args.live_news)
    if args.live_news:
        news_res = service.refresh_live_news()
        print(
            f"Live news ingested: {news_res['deduped_count']} items "
            f"({news_res['linked_count']} linked to instruments)"
        )
    server = create_server(host=args.host, port=args.port, service=service)
    actual_host, actual_port = server.server_address
    print(f"VIRA Web MVP running at http://{actual_host}:{actual_port}/ (agent_mode={service.requested_agent_mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down VIRA server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
