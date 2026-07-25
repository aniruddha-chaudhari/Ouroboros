"""
Ouroboros agent telemetry.

The agent is auto-instrumented at launch via `opentelemetry-instrument` (HTTP,
logging, and the OpenAI instrumentor emit chat spans + gen_ai.client.* metrics
automatically). On top of that we add:
  * a custom cost histogram (cost is NOT standardized in semconv)
  * an `invoke_agent` span wrapping each agent run
  * `execute_tool` spans wrapping each MCP / action tool call

Together these produce the trace tree judges recognize:
    invoke_agent  ->  chat  ->  execute_tool(signoz_search_traces)  ->  ...
and let the agent's own token/cost/latency show up in SigNoz — "watch the watcher".
"""
import functools
import json
import time
from contextlib import contextmanager

from opentelemetry import metrics, trace

from . import semconv as S

tracer = trace.get_tracer("ouroboros.agent")
meter = metrics.get_meter("ouroboros.agent")

_cost_hist = meter.create_histogram(
    name=S.METRIC_COST, unit="USD",
    description="Estimated cost per LLM call (custom; not in semconv).",
)

# Rough USD per 1K tokens — extend as needed.
_PRICING = {
    "llama-3.3-70b-versatile": (0.00059, 0.00079),  # Groq
    "llama-3.1-8b-instant": (0.00005, 0.00008),     # Groq
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.0025, 0.010),
    "gemini-1.5-flash": (0.000075, 0.00030),
    "gemini-2.0-flash": (0.0001, 0.0004),
}


def record_cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = _PRICING.get(model, (0.0, 0.0))
    cost = (in_tok / 1000) * pin + (out_tok / 1000) * pout
    _cost_hist.record(cost, {S.REQUEST_MODEL: model})
    return cost


@contextmanager
def invoke_agent_span(agent_name: str, task: str):
    """Root span for one agent run."""
    with tracer.start_as_current_span(f"invoke_agent {agent_name}") as span:
        span.set_attribute(S.OPERATION_NAME, S.OP_INVOKE_AGENT)
        span.set_attribute(S.AGENT_NAME, agent_name)
        span.set_attribute(S.INPUT_MESSAGES, task)  # demo: content capture on
        yield span


def _rows_of(payload) -> int | None:
    """Row count from a parsed SigNoz query payload, across its result shapes.

    Returns None when the shape isn't one we model — "unknown", not "invalid";
    we don't want to cry wolf on a response we simply don't understand."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    # aggregate / query_range: data.data.results[0].data (or .rows for raw logs)
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            results = inner.get("results")
            if isinstance(results, list) and results:
                first = results[0] or {}
                for key in ("data", "rows"):
                    seq = first.get(key)
                    if isinstance(seq, list):
                        return len(seq)
                return 0
        # list endpoints paginate: data.data is a list, or data.total
        if isinstance(inner, list):
            return len(inner)
    # list_services / list_dashboards: top-level data is a list
    if isinstance(data, list):
        return len(data)
    return None


def mcp_output_validity(result) -> tuple[str, int | None]:
    """Judge whether one MCP response actually returned usable content.

    (status, rows) where status is ok | empty | error | unknown. This is the
    signal conventional monitoring can't produce: a tool can answer 200 OK at
    normal latency and still hand back nothing, which an LLM will happily
    reason over. `empty` is that case, made explicit."""
    # A composite (e.g. error_rate returns {"total_by_op": r1, "errors_by_op": r2}):
    # worst status wins, rows sum.
    if isinstance(result, dict) and "result" not in result and result:
        parts = [v for v in result.values() if isinstance(v, dict)]
        if parts and all("result" in p or "error" in p for p in parts):
            statuses, total = [], 0
            for p in parts:
                st, n = mcp_output_validity(p)
                statuses.append(st)
                total += n or 0
            for worst in ("error", "unknown", "empty"):
                if worst in statuses:
                    return worst, total
            return "ok", total

    if not isinstance(result, dict):
        return "unknown", None
    if "error" in result and "result" not in result:
        return "error", 0

    res = result.get("result")
    if not isinstance(res, dict):
        return "unknown", None
    if res.get("isError"):
        return "error", 0

    content = res.get("content")
    if not isinstance(content, list) or not content:
        return "empty", 0

    text = (content[0] or {}).get("text")
    if not isinstance(text, str) or not text.strip():
        return "empty", 0
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        # non-JSON (e.g. "dashboard deleted") — it said something, so it's fine
        return "ok", None
    if isinstance(payload, dict) and payload.get("status") == "error":
        return "error", 0

    rows = _rows_of(payload)
    if rows is None:
        return "unknown", None
    return ("ok", rows) if rows > 0 else ("empty", 0)


def traced_tool(kind: str):
    """
    Decorator turning a tool fn into an `execute_tool` span.
    kind = "mcp" for SigNoz MCP calls, "action" for remediation calls.

    For MCP calls it also emits the semantic-quality attributes
    (tool.output_valid / status / rows) so a silently-empty query is visible in
    the trace instead of looking identical to a successful one.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"execute_tool {fn.__name__}") as span:
                span.set_attribute(S.OPERATION_NAME, S.OP_EXECUTE_TOOL)
                span.set_attribute(S.TOOL_NAME, fn.__name__)
                span.set_attribute("ouroboros.tool.kind", kind)
                t0 = time.time()
                try:
                    result = fn(*args, **kwargs)
                    span.set_attribute("ouroboros.tool.ok", True)
                    if kind == "mcp":
                        status, rows = mcp_output_validity(result)
                        span.set_attribute(S.TOOL_OUTPUT_STATUS, status)
                        span.set_attribute(S.TOOL_OUTPUT_VALID, status == "ok")
                        if rows is not None:
                            span.set_attribute(S.TOOL_OUTPUT_ROWS, rows)
                    return result
                except Exception as e:  # noqa: BLE001
                    span.record_exception(e)
                    span.set_attribute("ouroboros.tool.ok", False)
                    if kind == "mcp":
                        span.set_attribute(S.TOOL_OUTPUT_STATUS, "error")
                        span.set_attribute(S.TOOL_OUTPUT_VALID, False)
                        span.set_attribute(S.TOOL_OUTPUT_ROWS, 0)
                    raise
                finally:
                    span.set_attribute(
                        "ouroboros.tool.duration_ms", round((time.time() - t0) * 1000, 1)
                    )
        return wrapper
    return deco
