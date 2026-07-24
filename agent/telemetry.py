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


def traced_tool(kind: str):
    """
    Decorator turning a tool fn into an `execute_tool` span.
    kind = "mcp" for SigNoz MCP calls, "action" for remediation calls.
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
                    return result
                except Exception as e:  # noqa: BLE001
                    span.record_exception(e)
                    span.set_attribute("ouroboros.tool.ok", False)
                    raise
                finally:
                    span.set_attribute(
                        "ouroboros.tool.duration_ms", round((time.time() - t0) * 1000, 1)
                    )
        return wrapper
    return deco
