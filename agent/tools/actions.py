"""
Remediation action tools — the agent's hands.

These are the closed-loop half that goes beyond SigNoz's own read-only demo:
after diagnosing, the agent picks and executes one of these to actually fix
the fleet, then checks the fleet directly to verify recovery. Each is an
`execute_tool` span so the remediation is on the same trace as the diagnosis.

Two kinds of remediation, matching how real AI-SRE tools act:
  * config reverts — clear_latency / clear_errors flip the demo-api's fault
    control back to healthy (a stand-in for a feature-flag / bad-config
    rollback). Low blast radius.
  * a REAL infrastructure action — restart_service actually restarts the
    demo-api container (like restarting an unhealthy pod). Higher blast radius,
    so it is gated behind human approval (see agent.REQUIRES_APPROVAL).
"""
import os
import subprocess
import time

import httpx

from ..telemetry import traced_tool

API_URL = os.getenv("DEMO_API_URL", "http://localhost:8001")
DEMO_CONTAINER = os.getenv("DEMO_CONTAINER", "ouroboros-demo-api-1")
_client = httpx.Client(timeout=10.0)


@traced_tool("action")
def clear_latency() -> dict:
    """Remediation for a latency regression (roll back the slow config)."""
    r = _client.post(f"{API_URL}/fault", json={"latency_ms": 0})
    return {"action": "clear_latency", "result": r.json()}


@traced_tool("action")
def clear_errors() -> dict:
    """Remediation for elevated error rate (e.g. roll back a bad deploy)."""
    r = _client.post(f"{API_URL}/fault", json={"error_rate": 0.0})
    return {"action": "clear_errors", "result": r.json()}


def _wait_healthy(timeout: float = 25.0) -> bool:
    """Poll the service's /healthz until it answers or we give up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _client.get(f"{API_URL}/healthz", timeout=2.0).status_code == 200:
                return True
        except Exception:  # noqa: BLE001 — service is mid-restart, keep waiting
            pass
        time.sleep(1)
    return False


@traced_tool("action")
def restart_service() -> dict:
    """REAL remediation: restart the demo-api container, like restarting an
    unhealthy pod. This genuinely reclaims leaked memory (you can't un-leak a
    running process — you have to restart it) and resets in-memory fault state.
    Waits for the service to pass /healthz before returning so verification
    sees the true post-restart state."""
    proc = subprocess.run(
        ["docker", "restart", DEMO_CONTAINER],
        capture_output=True, text=True, timeout=90,
    )
    ok = proc.returncode == 0
    ready = _wait_healthy() if ok else False
    return {
        "action": "restart_service",
        "container": DEMO_CONTAINER,
        "restarted": ok,
        "ready": ready,
        "error": None if ok else proc.stderr.strip(),
    }


@traced_tool("action")
def verify_recovery() -> dict:
    """Confirm recovery by reading the fleet's live fault state directly.

    This is deliberately NOT routed through SigNoz: telemetry lags the actual
    fix by seconds, so the fault-control endpoint is the ground truth for
    'is it healthy right now'."""
    r = _client.get(f"{API_URL}/fault")
    faults = r.json()["faults"]
    healthy = faults["latency_ms"] == 0 and faults["error_rate"] == 0.0 and not faults["mem_leak"]
    return {"healthy": healthy, "faults": faults}


ACTIONS = {
    "clear_latency": clear_latency,
    "clear_errors": clear_errors,
    "restart_service": restart_service,
    "verify_recovery": verify_recovery,
}
