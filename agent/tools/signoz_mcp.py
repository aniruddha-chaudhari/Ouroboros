"""
SigNoz MCP tools — the agent's senses.

Thin wrappers over the SigNoz MCP server (HTTP transport, default :8000).
Each is wrapped as an `execute_tool` GenAI span so the agent's investigation
is fully visible in SigNoz. These call the MCP endpoint directly with the
service-account API key; if you drive the agent through an MCP-native client
(Claude Code, LangGraph MCP adapter) the same tools are exposed natively.

Tools used here map to real SigNoz MCP tool names:
  signoz_search_traces, signoz_aggregate_traces, signoz_search_logs,
  signoz_query_metrics, signoz_execute_builder_query, signoz_list_services,
  signoz_create_dashboard, signoz_create_alert, signoz_get_alert_history
"""
import os

import httpx

from ..telemetry import traced_tool

MCP_URL = os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
API_KEY = os.getenv("SIGNOZ_API_KEY", "")

_client = httpx.Client(timeout=30.0)


def _call(tool: str, arguments: dict) -> dict:
    """Invoke a SigNoz MCP tool over the streamable-HTTP transport."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    headers = {"SIGNOZ-API-KEY": API_KEY, "Content-Type": "application/json"}
    resp = _client.post(MCP_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


@traced_tool("mcp")
def list_services() -> dict:
    return _call("signoz_list_services", {})


@traced_tool("mcp")
def search_traces(service: str, minutes: int = 15, limit: int = 20) -> dict:
    return _call("signoz_search_traces", {
        "service": service,
        "timeRange": f"{minutes}m",
        "limit": limit,
    })


@traced_tool("mcp")
def query_metrics(metric: str, minutes: int = 15) -> dict:
    return _call("signoz_query_metrics", {
        "metricName": metric,
        "timeRange": f"{minutes}m",
    })


@traced_tool("mcp")
def memory_pressure(service: str, minutes: int = 15) -> dict:
    """Max leaked-memory chunk count on the service's spans (each chunk = 5MB).
    A growing value is a memory leak — the one fault a config-revert can't fix,
    so it's what points the agent at a restart."""
    return _call("signoz_aggregate_traces", {
        "service": service,
        "timeRange": f"{minutes}m",
        "aggregation": "max",
        "aggregateOn": "app.mem_leak_chunks",
    })


@traced_tool("mcp")
def latency_p95(service: str, minutes: int = 15) -> dict:
    """p95 span duration (nanoseconds) PER OPERATION for the service — the fleet's
    REAL request latency, from its traces (not the agent's own LLM-call latency).

    Grouping by operation is essential: an un-grouped p95 is dominated by the many
    tiny child spans (db calls, internal work) and hides a slow top-level request.
    Grouped + sorted descending, a slow endpoint like `GET /orders` stands out."""
    return _call("signoz_aggregate_traces", {
        "service": service,
        "timeRange": f"{minutes}m",
        "aggregation": "p95",
        "aggregateOn": "duration_nano",
        "groupBy": "name",
        "orderBy": "p95(duration_nano) desc",
        "limit": 8,
    })


@traced_tool("mcp")
def search_logs(query: str, minutes: int = 15, limit: int = 50) -> dict:
    return _call("signoz_search_logs", {
        "filter": query,
        "timeRange": f"{minutes}m",
        "limit": limit,
    })


@traced_tool("mcp")
def memory_leak_chunks(service: str, minutes: int = 15) -> dict:
    """Max value of the app.mem_leak_chunks span attribute — how much memory the
    service has leaked (each chunk = 5MB). A growing/non-zero value is the only
    trace-visible signal of the memory-leak fault, since host memory metrics
    aren't exported in this demo."""
    return _call("signoz_aggregate_traces", {
        "service": service,
        "timeRange": f"{minutes}m",
        "aggregation": "max",
        "aggregateOn": "app.mem_leak_chunks",
    })


@traced_tool("mcp")
def error_rate(service: str, minutes: int = 15) -> dict:
    """Span counts PER OPERATION, total vs error, so a real per-endpoint error rate
    can be computed. An all-spans rate is diluted by the many non-error child spans
    (db calls, http-send), so a 30% request error rate would wash out to a few %.
    Grouping by operation keeps the entry span's true rate visible."""
    common = {
        "service": service, "timeRange": f"{minutes}m", "aggregation": "count",
        "groupBy": "name", "orderBy": "count() desc", "limit": 15,
    }
    total = _call("signoz_aggregate_traces", common)
    errors = _call("signoz_aggregate_traces", {**common, "error": True})
    return {"total_by_op": total, "errors_by_op": errors}


@traced_tool("mcp")
def alert_history(minutes: int = 60) -> dict:
    return _call("signoz_get_alert_history", {"start": f"now-{minutes}m", "end": "now"})


@traced_tool("mcp")
def create_alert(name: str, expr: str, threshold: float) -> dict:
    """The agent can even create new alerts it thinks are missing."""
    return _call("signoz_create_alert", {
        "alert_name": name, "expression": expr, "threshold": threshold,
    })
