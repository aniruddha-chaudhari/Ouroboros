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

from . import semconv as S
from .telemetry import invoke_agent_span, mcp_output_validity, record_cost
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
- telemetry = how trustworthy this evidence is. `missing` lists signals that came
  back unusable. If a signal is missing you have NO information about that fault
  type — do not read it as "healthy". Lower your confidence accordingly, and if
  the missing signal is the one that would confirm your diagnosis, say so.
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
    (latency in ms per operation, error rate %, error-log count).

    Also judges whether the evidence is TRUSTWORTHY, not just what it says.
    Every failure path here used to collapse into a falsy default (no rows ->
    {} -> "0ms latency, 0% errors"), which reads exactly like a perfectly
    healthy service. So a telemetry outage looked like good news, and the LLM
    would confidently diagnose "healthy" over an empty evidence blob. The
    `telemetry` block it returns makes that distinguishable.

    Note which empties are meaningful: a service actually serving traffic MUST
    produce spans and latency, so empty there means we're blind. But zero error
    logs and zero leaked memory are the *normal* state of a healthy service, so
    empty there is a real answer, not a missing one."""
    lat_raw = _safe(signoz_mcp.latency_p95, service, minutes=LOOKBACK_MIN)
    lat_status, _ = mcp_output_validity(lat_raw)
    lat_ns = _grouped(lat_raw)
    latency_ms = {
        op: round(ns / 1e6, 1) for op, ns in lat_ns.items() if isinstance(ns, (int, float))
    }

    err = _safe(signoz_mcp.error_rate, service, minutes=LOOKBACK_MIN)
    # Judge this on the TOTAL span counts (the denominator) only. The error-span
    # half legitimately returns zero rows on a healthy service — that's the
    # numerator being 0, not missing data. Grading the pair "worst wins" would
    # mark every healthy service as degraded and block all auto-healing.
    err_status, _ = mcp_output_validity(
        err.get("total_by_op") if isinstance(err, dict) and "total_by_op" in err else err
    )
    error_rate_pct = None
    spans_seen = 0
    if isinstance(err, dict) and "total_by_op" in err:
        totals = _grouped(err.get("total_by_op"))
        errs = _grouped(err.get("errors_by_op"))
        spans_seen = int(sum(v for v in totals.values() if isinstance(v, (int, float))))
        # worst per-operation error rate; ignore tiny-volume ops (< 5 spans) so a
        # single stray error can't spike the rate to 100%.
        rates = [
            (errs.get(op, 0) or 0) / t * 100
            for op, t in totals.items()
            if isinstance(t, (int, float)) and t >= 5
        ]
        if rates:
            error_rate_pct = round(max(rates), 1)

    logs_raw = _safe(signoz_mcp.search_logs, "severity_text = 'ERROR'", minutes=LOOKBACK_MIN)
    logs_status, _ = mcp_output_validity(logs_raw)
    _cols, log_rows = _mcp_rows(logs_raw)

    mem_raw = _safe(signoz_mcp.memory_pressure, service, minutes=LOOKBACK_MIN)
    mem_status, _ = mcp_output_validity(mem_raw)
    mem = _scalar(mem_raw)
    memory_leak_chunks = int(mem) if isinstance(mem, (int, float)) else 0

    # "ok" = returned rows. For logs/memory an empty answer is still a real
    # answer (nothing wrong to report), so it counts as usable.
    signals = {
        "latency": lat_status,
        "errors": err_status,
        "logs": logs_status,
        "memory": mem_status,
    }
    usable = {
        "latency": lat_status == "ok",
        "errors": err_status == "ok",
        "logs": logs_status in ("ok", "empty"),
        "memory": mem_status in ("ok", "empty"),
    }
    missing = sorted(k for k, good in usable.items() if not good)
    # The anchor question: can we see this service at all? If it's serving
    # traffic there are spans; zero spans AND no latency means we are blind,
    # not that everything is fine.
    visible = spans_seen > 0 or bool(latency_ms)

    return {
        "latency_p95_ms": dict(sorted(latency_ms.items(), key=lambda kv: kv[1], reverse=True)),
        "error_rate_pct": error_rate_pct,
        "error_log_count": len(log_rows) if log_rows is not None else None,
        "memory_leak_chunks": memory_leak_chunks,
        "telemetry": {
            "visible": visible,
            "spans_seen": spans_seen,
            "signals": signals,
            "usable_signals": sum(usable.values()),
            "total_signals": len(usable),
            "missing": missing,
            "degraded": bool(missing),
        },
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
    tel = (dec.get("_evidence") or {}).get("telemetry") or {}
    if tel:
        span.set_attribute(S.EVIDENCE_VISIBLE, bool(tel.get("visible")))
        span.set_attribute(S.EVIDENCE_SPANS_SEEN, int(tel.get("spans_seen", 0)))
        span.set_attribute(S.EVIDENCE_USABLE, int(tel.get("usable_signals", 0)))
        span.set_attribute(S.EVIDENCE_TOTAL, int(tel.get("total_signals", 0)))
        span.set_attribute(S.EVIDENCE_DEGRADED, bool(tel.get("degraded")))
        span.set_attribute(S.EVIDENCE_MISSING, ",".join(tel.get("missing") or []))


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

    Outcomes:
      blind     — telemetry unusable; refused to diagnose (no LLM call made)
      no_action — agent judged nothing is wrong (did not act)
      healed    — confident + low-risk: auto-executed and verified recovery
      failed    — auto-executed but did not recover
      proposed  — action recommended but NOT executed; awaiting human approval
                  (below the auto-heal confidence bar, a high-impact action like
                  a restart, or a diagnosis made on incomplete evidence)
    """
    with invoke_agent_span(AGENT_NAME, f"heal {service}") as span:
        evidence = gather_evidence(service)                      # DIAGNOSE
        tel = evidence.get("telemetry") or {}

        # Tier 0: BLIND — we cannot see the service, so we refuse to diagnose.
        # Deliberately does NOT call the LLM: given an all-zeros evidence blob it
        # would confidently answer "healthy", which is the exact failure mode
        # this guard exists to prevent. No answer beats a confident wrong one.
        if not tel.get("visible", True):
            recovery = actions.verify_recovery()
            decision = {
                "diagnosis": (
                    "Cannot see the service — telemetry returned no usable data "
                    f"(spans seen: {tel.get('spans_seen', 0)}). Refusing to guess."
                ),
                "action": "none", "confidence": 0.0,
                "_cost_usd": 0.0, "_tokens": {"in": 0, "out": 0},
                "_evidence": evidence,
                "_blind": {"missing": tel.get("missing") or [],
                           "signals": tel.get("signals") or {}},
            }
            _finalize(span, decision, "blind", recovery)
            span.set_attribute("ouroboros.blind", True)
            return {"outcome": "blind", "decision": decision,
                    "action_result": None, "recovery": recovery, "attempts": []}

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
        # Partial blindness downgrades autonomy: if some signals came back
        # unusable the agent may still be right, but it reasoned on incomplete
        # evidence, so it loses the right to act unsupervised.
        degraded = bool(tel.get("degraded"))
        auto = confidence >= AUTO_THRESHOLD and not risky and not degraded

        # Tier 2: propose only — do NOT execute, wait for a human
        if not auto:
            recovery = actions.verify_recovery()
            if risky:
                reason = "high-impact action — needs human sign-off"
            elif degraded:
                missing = ", ".join(tel.get("missing") or []) or "some signals"
                reason = (
                    f"incomplete evidence ({missing} unavailable) — not safe to "
                    "auto-apply on partial data"
                )
            else:
                reason = (
                    f"confidence {int(confidence * 100)}% is below the "
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
