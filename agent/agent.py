"""
Ouroboros agent — the self-healing loop.

Flow (each run is one `invoke_agent` trace in SigNoz):
    1. DIAGNOSE  — query SigNoz via MCP (latency, error rate, memory, logs)
    2. DECIDE    — LLM picks one remediation, or "none" if nothing is wrong
    3. GATE      — three-tier autonomy (the pattern real AI-SRE tools use):
                     • confident + low-blast-radius  -> auto-heal now
                     • otherwise (unsure OR risky)   -> PROPOSE, wait for a human
                     • nothing wrong                 -> no action
    4. ACT       — execute the action (now, or after a human approves it)
    5. VERIFY    — check the fleet's live state to confirm recovery

The LLM call itself is auto-instrumented (opentelemetry-instrumentation-openai
emits the `chat` span + gen_ai.client.* metrics). We wrap the run in an
invoke_agent span and record a custom cost metric, so the agent's own tokens,
cost, latency and tool-calls all land in SigNoz.

Run with auto-instrumentation:  ./agent/run.sh
"""
import json
import os

from openai import OpenAI

from .telemetry import invoke_agent_span, record_cost
from .tools import actions, signoz_mcp

AGENT_NAME = "ouroboros-sre"
MODEL = os.getenv("OURO_MODEL", "llama-3.3-70b-versatile")
# Three-tier autonomy (the pattern real AI-SRE tools use):
#   - action == none                      -> nothing to do
#   - confident AND low-blast-radius      -> AUTO-HEAL (execute immediately)
#   - otherwise (unsure, or high-impact)  -> PROPOSE, wait for human approval
AUTO_THRESHOLD = float(os.getenv("OURO_AUTO_THRESHOLD", "0.8"))
# High-blast-radius actions ALWAYS require approval, no matter how confident.
REQUIRES_APPROVAL = {
    a.strip() for a in os.getenv("OURO_REQUIRES_APPROVAL", "restart_service").split(",") if a.strip()
}
MAX_ATTEMPTS = int(os.getenv("OURO_MAX_ATTEMPTS", "2"))
# How far back the agent looks. Shorter = a fault (and its recovery) shows up
# faster, at the cost of noisier percentiles. 5m is a good live-demo balance.
LOOKBACK_MIN = int(os.getenv("OURO_LOOKBACK_MIN", "5"))

# Groq's Chat Completions API is OpenAI-compatible, so we keep the `openai`
# client (and its auto-instrumentation) and just point it at Groq.
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
)

SYSTEM = """You are Ouroboros, an autonomous SRE agent for a demo fleet.
You are given telemetry evidence about the "demo-api" service. Decide what to do.
Respond ONLY with JSON, no prose, no markdown:
{"diagnosis": "<one sentence: what, if anything, is wrong>",
 "action": "<one of: clear_latency, clear_errors, restart_service, none>",
 "confidence": <0.0-1.0>}
Evidence notes:
- latency_p95_ms = p95 request latency per operation, in MILLISECONDS. Healthy
  top-level requests are single-digit to low-tens of ms; a top-level operation
  over ~100ms is a latency fault.
- error_rate_pct = worst per-operation error rate (percent). Anything more than a
  few percent is an error fault. error_log_count = recent ERROR-level logs.
- memory_leak_chunks = leaked 5MB memory blocks. 0 is healthy; a positive and
  growing value is a memory leak that can only be cleared by restarting.
Rules:
- If the evidence shows the service is healthy, use action "none".
- Pick a remediation only when the evidence clearly points to that specific fault:
  clear_latency for high latency, clear_errors for a high error rate,
  restart_service for a memory leak (memory_leak_chunks > 0).
- "confidence" is your GENUINE certainty that this action is correct. Use a LOW
  value (below 0.6) when the evidence is thin, contradictory, or you are guessing.
  Do NOT default to high numbers."""

_NO_ACTION = {None, "none", "None", ""}


def _safe(fn, *args, **kwargs):
    """Run one MCP call without letting a single failure abort the diagnosis."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _mcp_rows(resp):
    """Pull (columns, rows) out of a SigNoz MCP query/aggregate response.

    The real numbers are buried as JSON-in-a-string-in-JSON
    (result.content[0].text -> data.data.results[0]); an LLM can't reliably dig
    them out of that envelope, so we parse them into clean values here."""
    try:
        inner = json.loads(resp["result"]["content"][0]["text"])
        res = inner["data"]["data"]["results"][0]
        return [c["name"] for c in res["columns"]], res.get("data", []) or []
    except Exception:  # noqa: BLE001
        return None, None


def _scalar(resp):
    """First aggregate value from a scalar response (e.g. a count)."""
    _cols, rows = _mcp_rows(resp)
    if rows and rows[0]:
        return rows[0][-1]
    return None


def _grouped(resp):
    """{group -> aggregate value} from a grouped response."""
    _cols, rows = _mcp_rows(resp)
    return {str(r[0]): r[-1] for r in rows if len(r) >= 2} if rows else {}


def gather_evidence(service: str = "demo-api") -> dict:
    """DIAGNOSE: pull the signals a human SRE would look at, via SigNoz MCP, and
    flatten them into clean, unambiguous numbers the model can actually read
    (latency in ms per operation, error rate %, error-log count)."""
    lat_ns = _grouped(_safe(signoz_mcp.latency_p95, service, minutes=LOOKBACK_MIN))
    latency_ms = {
        op: round(ns / 1e6, 1) for op, ns in lat_ns.items() if isinstance(ns, (int, float))
    }

    err = _safe(signoz_mcp.error_rate, service, minutes=LOOKBACK_MIN)
    error_rate_pct = None
    if isinstance(err, dict) and "total_by_op" in err:
        totals = _grouped(err.get("total_by_op"))
        errs = _grouped(err.get("errors_by_op"))
        # worst per-operation error rate; ignore tiny-volume ops (< 5 spans) so a
        # single stray error can't spike the rate to 100%.
        rates = [
            (errs.get(op, 0) or 0) / t * 100
            for op, t in totals.items()
            if isinstance(t, (int, float)) and t >= 5
        ]
        if rates:
            error_rate_pct = round(max(rates), 1)

    _cols, log_rows = _mcp_rows(
        _safe(signoz_mcp.search_logs, "severity_text = 'ERROR'", minutes=LOOKBACK_MIN)
    )

    mem = _scalar(_safe(signoz_mcp.memory_pressure, service, minutes=LOOKBACK_MIN))
    memory_leak_chunks = int(mem) if isinstance(mem, (int, float)) else 0

    return {
        "latency_p95_ms": dict(sorted(latency_ms.items(), key=lambda kv: kv[1], reverse=True)),
        "error_rate_pct": error_rate_pct,
        "error_log_count": len(log_rows) if log_rows is not None else None,
        "memory_leak_chunks": memory_leak_chunks,
    }


def decide(evidence: dict, prior: list | None = None) -> dict:
    """DECIDE: one LLM call. Auto-instrumented -> shows as a `chat` span.

    `prior` carries earlier failed attempts in the same incident so the model
    can pick a different action instead of repeating one that didn't work."""
    # Cap the prompt size, but high-signal summaries are ordered first in
    # gather_evidence() so the numbers that matter always survive the cut.
    user = f"Evidence:\n{json.dumps(evidence)[:9000]}"
    if prior:
        user += (
            "\n\nEarlier remediation attempts in THIS incident did NOT restore "
            f"health: {json.dumps(prior)}. Pick a different action, or \"none\" "
            "if you now believe it is healthy."
        )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    usage = resp.usage
    cost = record_cost(MODEL, usage.prompt_tokens, usage.completion_tokens)
    decision = json.loads(resp.choices[0].message.content)
    decision["_cost_usd"] = round(cost, 6)
    decision["_tokens"] = {"in": usage.prompt_tokens, "out": usage.completion_tokens}
    return decision


def _finalize(span, decision: dict, outcome: str, recovery: dict) -> None:
    dec = decision or {}
    span.set_attribute("ouroboros.diagnosis", dec.get("diagnosis", ""))
    span.set_attribute("ouroboros.action", dec.get("action") or "none")
    span.set_attribute("ouroboros.confidence", float(dec.get("confidence", 0.0) or 0.0))
    span.set_attribute("ouroboros.outcome", outcome)
    span.set_attribute("ouroboros.healed", bool(recovery.get("healthy")))


def apply_action(action_name: str, service: str = "demo-api") -> dict:
    """ACT + VERIFY: execute one remediation and confirm recovery (retrying the
    same action up to MAX_ATTEMPTS). Used both for auto-heal and after a human
    approves a proposed action."""
    attempts: list[dict] = []
    act_result = None
    recovery = actions.verify_recovery()
    act_fn = actions.ACTIONS.get(action_name)
    if act_fn is None:
        return {"outcome": "failed", "action_result": {"error": f"unknown action {action_name}"},
                "recovery": recovery, "attempts": attempts}
    for _ in range(max(1, MAX_ATTEMPTS)):
        act_result = act_fn()                                    # ACT
        recovery = actions.verify_recovery()                     # VERIFY (ground truth)
        attempts.append({"action": action_name, "healthy": recovery["healthy"]})
        if recovery["healthy"]:
            return {"outcome": "healed", "action_result": act_result,
                    "recovery": recovery, "attempts": attempts}
    return {"outcome": "failed", "action_result": act_result,
            "recovery": recovery, "attempts": attempts}


def run_once(service: str = "demo-api") -> dict:
    """One diagnose→decide→gate cycle, as a single invoke_agent trace.

    Three-tier autonomy — outcomes:
      no_action — agent judged nothing is wrong (did not act)
      healed    — confident + low-risk: auto-executed and verified recovery
      failed    — auto-executed but did not recover
      proposed  — action recommended but NOT executed; awaiting human approval
                  (either below the auto-heal confidence bar, or a high-impact
                  action like a restart that always needs sign-off)
    """
    with invoke_agent_span(AGENT_NAME, f"heal {service}") as span:
        evidence = gather_evidence(service)                      # DIAGNOSE
        decision = decide(evidence)                              # DECIDE
        decision["_evidence"] = evidence                         # surface what it saw

        action_name = decision.get("action")
        confidence = float(decision.get("confidence", 0.0) or 0.0)

        # Tier 1: nothing to do (or model invented an unknown action)
        if action_name in _NO_ACTION or actions.ACTIONS.get(action_name) is None:
            recovery = actions.verify_recovery()
            _finalize(span, decision, "no_action", recovery)
            return {"outcome": "no_action", "decision": decision,
                    "action_result": None, "recovery": recovery, "attempts": []}

        risky = action_name in REQUIRES_APPROVAL
        auto = confidence >= AUTO_THRESHOLD and not risky

        # Tier 2: propose only — do NOT execute, wait for a human
        if not auto:
            recovery = actions.verify_recovery()
            reason = (
                "high-impact action — needs human sign-off" if risky
                else f"confidence {int(confidence * 100)}% is below the "
                     f"{int(AUTO_THRESHOLD * 100)}% auto-heal bar"
            )
            decision["_proposal"] = {"action": action_name, "reason": reason,
                                     "requires_approval": risky}
            _finalize(span, decision, "proposed", recovery)
            span.set_attribute("ouroboros.proposed", True)
            return {"outcome": "proposed", "decision": decision,
                    "action_result": None, "recovery": recovery, "attempts": []}

        # Tier 3: confident + low-risk -> auto-heal
        applied = apply_action(action_name, service)
        _finalize(span, decision, applied["outcome"], applied["recovery"])
        span.set_attribute("ouroboros.auto", True)
        return {"outcome": applied["outcome"], "decision": decision,
                "action_result": applied["action_result"],
                "recovery": applied["recovery"], "attempts": applied["attempts"]}


def apply_approved(action_name: str, service: str = "demo-api") -> dict:
    """Execute an action a human approved — its own invoke_agent trace so the
    approved remediation shows up in SigNoz just like an autonomous one."""
    with invoke_agent_span(AGENT_NAME, f"apply {action_name}") as span:
        applied = apply_action(action_name, service)
        span.set_attribute("ouroboros.action", action_name)
        span.set_attribute("ouroboros.outcome", applied["outcome"])
        span.set_attribute("ouroboros.approved", True)
        span.set_attribute("ouroboros.healed", bool(applied["recovery"]["healthy"]))
        return applied


if __name__ == "__main__":
    from pprint import pprint
    pprint(run_once())
