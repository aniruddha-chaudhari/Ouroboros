"""
Alert-to-agent bridge + incident timeline API + continuous watchdog.

Three ways the agent gets triggered:
  1. /webhook/signoz — a SigNoz alert fires and POSTs here (event-driven).
  2. /diagnose       — manual button, for demos.
  3. watchdog        — a background loop probes the fleet's numbers cheaply
                       (no LLM) every few seconds and escalates to a full agent
                       run ONLY when it sees real degradation. This is what makes
                       healing continuous without burning an LLM call per tick.

Run:  uvicorn scripts.trigger:app --port 8090
"""
import asyncio
import contextlib
import datetime as dt
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from agent.agent import apply_approved, gather_evidence, run_once

# --- watchdog config --------------------------------------------------------
WATCH_ENABLED = os.getenv("OURO_AUTO_HEAL", "1") not in ("0", "false", "False", "")
WATCH_INTERVAL = int(os.getenv("OURO_WATCH_INTERVAL_SEC", "15"))   # probe cadence
WATCH_LATENCY_MS = float(os.getenv("OURO_WATCH_LATENCY_MS", "100"))  # escalation thresholds
WATCH_ERROR_PCT = float(os.getenv("OURO_WATCH_ERROR_PCT", "5"))
WATCH_MEM_CHUNKS = int(os.getenv("OURO_WATCH_MEM_CHUNKS", "3"))  # leaked 5MB blocks
# After an auto-heal, wait this long before escalating again — telemetry lags the
# actual fix, so without a cooldown the loop would re-heal an already-fixed fleet.
WATCH_COOLDOWN = int(os.getenv("OURO_WATCH_COOLDOWN_SEC", "90"))

TIMELINE: list[dict] = []
# Approvals the agent proposed but is waiting on a human to approve/reject.
# Keyed by id; the UI renders these as approval cards.
PENDING: dict[str, dict] = {}
WATCH = {"enabled": WATCH_ENABLED, "last_check": None, "healthy": None, "cooldown": False}
_cooldown_until = 0.0
_pending_seq = 0


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _record(type_: str, detail: dict | None = None) -> None:
    TIMELINE.append({"ts": _now(), "type": type_, "detail": detail or {}})


def _run_and_record(trigger_type: str, detail: dict | None = None) -> dict:
    """Record the trigger, run one agent cycle, and record the outcome. If the
    agent proposed an action (didn't auto-heal), park it in PENDING for approval
    instead of recording a remediation. Runs synchronously — call via to_thread."""
    global _pending_seq
    _record(trigger_type, detail)
    result = run_once()
    if result.get("outcome") == "proposed":
        _pending_seq += 1
        pid = f"appr-{_pending_seq}"
        proposal = (result.get("decision") or {}).get("_proposal", {})
        PENDING[pid] = {
            "id": pid, "ts": _now(),
            "action": proposal.get("action") or (result["decision"] or {}).get("action"),
            "reason": proposal.get("reason", ""),
            "decision": result["decision"],
        }
        _record("proposed", {"id": pid, **result})
    else:
        _record("remediation", result)
    return result


def _looks_degraded(evidence: dict) -> bool:
    """Cheap rule over the numeric evidence — no LLM. Decides whether it's worth
    escalating to a full (LLM) agent run."""
    lat = evidence.get("latency_p95_ms") or {}
    worst_latency = max(lat.values(), default=0)
    err = evidence.get("error_rate_pct") or 0
    mem = evidence.get("memory_leak_chunks") or 0
    return worst_latency > WATCH_LATENCY_MS or err > WATCH_ERROR_PCT or mem > WATCH_MEM_CHUNKS


async def _watchdog() -> None:
    """Continuously probe the fleet; escalate to the agent only on degradation."""
    global _cooldown_until
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        if not WATCH["enabled"]:
            WATCH["healthy"] = None
            continue
        try:
            evidence = await asyncio.to_thread(gather_evidence)   # cheap: MCP only
            degraded = _looks_degraded(evidence)
            WATCH["last_check"] = _now()
            WATCH["healthy"] = not degraded
            in_cooldown = time.monotonic() < _cooldown_until
            WATCH["cooldown"] = in_cooldown
            # Don't re-escalate while something is already awaiting a human, or
            # we'd pile up duplicate approval cards for the same incident.
            if degraded and not in_cooldown and not PENDING:
                result = await asyncio.to_thread(
                    _run_and_record, "auto_detected", {"evidence": evidence}
                )
                # Only cool down after we actually acted; a proposal is still
                # unresolved, so keep watching (the human hasn't decided yet).
                if result.get("outcome") in ("healed", "failed"):
                    _cooldown_until = time.monotonic() + WATCH_COOLDOWN
        except Exception as e:  # keep the loop alive on a transient error
            WATCH["last_check"] = _now()
            WATCH["healthy"] = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_watchdog())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Ouroboros trigger + timeline", lifespan=lifespan)
# Allow the React dev server (vite on :5173) to call the API cross-origin.
# In production the built app is served same-origin from this app (see bottom).
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"


@app.post("/webhook/signoz")
async def signoz_alert(req: Request):
    """SigNoz alert notification channel target."""
    alert = await req.json()
    result = await asyncio.to_thread(_run_and_record, "alert", alert)
    return {"triggered": True, "result": result}


@app.post("/diagnose")
async def diagnose():
    """Manual, deterministic trigger for the live demo."""
    result = await asyncio.to_thread(_run_and_record, "manual_trigger", {})
    return result


@app.post("/approve")
async def approve(req: Request):
    """Human approves a proposed action — NOW execute it and verify."""
    body = await req.json()
    item = PENDING.pop(body.get("id", ""), None)
    if not item:
        return {"ok": False, "error": "no such pending approval"}
    _record("approved", {"id": item["id"], "action": item["action"]})
    result = await asyncio.to_thread(apply_approved, item["action"])
    _record("remediation", {**result, "approved": True, "decision": item["decision"]})
    # Telemetry lags the real fix, so cool the watchdog down after a successful
    # approval — otherwise it re-proposes the same action on stale data.
    if result.get("outcome") == "healed":
        global _cooldown_until
        _cooldown_until = time.monotonic() + WATCH_COOLDOWN
    return {"ok": True, "result": result}


@app.post("/reject")
async def reject(req: Request):
    """Human rejects a proposed action — discard it, do nothing to the fleet."""
    body = await req.json()
    item = PENDING.pop(body.get("id", ""), None)
    if not item:
        return {"ok": False, "error": "no such pending approval"}
    _record("rejected", {"id": item["id"], "action": item["action"]})
    return {"ok": True}


@app.post("/auto")
async def set_auto(req: Request):
    """Toggle the continuous watchdog on/off from the UI."""
    body = await req.json()
    WATCH["enabled"] = bool(body.get("enabled", True))
    return {"enabled": WATCH["enabled"]}


@app.get("/timeline")
def timeline():
    return {"events": TIMELINE[-50:], "watch": WATCH, "pending": list(PENDING.values())}


# --- serve the React console -------------------------------------------------
# Mounted LAST so the API routes above take precedence. After `cd ui && npm run
# build`, the built app is served at http://localhost:8090/. During development
# use `cd ui && npm run dev` instead (vite on :5173, proxying the API here).
if (UI_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
else:
    @app.get("/", response_class=HTMLResponse)
    def ui_not_built():
        return (
            "<pre style='font:14px/1.6 monospace;color:#7dff9b;background:#070a09;"
            "padding:32px;height:100vh;margin:0'>"
            "Ouroboros console not built yet.\n\n"
            "  Dev:   cd ui && npm install && npm run dev   -> http://localhost:5173\n"
            "  Prod:  cd ui && npm install && npm run build -> reload this page\n\n"
            "The timeline API is live at /timeline and /diagnose.</pre>"
        )
