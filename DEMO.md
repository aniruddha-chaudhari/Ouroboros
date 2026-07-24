# Ouroboros — Demo Script (2–4 min)

Goal: show the full self-healing loop **and** the agent observing itself, all in SigNoz.

## Setup (before recording)
- SigNoz up via Foundry (UI :8080, MCP :8000), service-account key created.
- Demo fleet running (`make fleet`), dashboard imported, alerts created, trigger running (`make trigger`).
- Two browser tabs: (1) SigNoz Traces, (2) the "Ouroboros — AI Agent Observability" dashboard. Terminal ready.

## Beats

**0:00 — The pitch (15s).**
"This is Ouroboros: an SRE agent that heals my systems using SigNoz's MCP server as its senses and hands — and it's fully traced in SigNoz, so I can watch the agent watch itself."

**0:15 — Healthy baseline (20s).**
Show the dashboard: flat error rate, steady latency, token/cost panels. Show the demo-api service in SigNoz Services.

**0:35 — Inject a fault (15s).**
`make demo-latency` (or `./scripts/inject_fault.sh latency`). In SigNoz, latency on `demo-api` climbs; the error-rate/latency panel reacts.

**0:50 — Alert fires (20s).**
Show the SigNoz alert going into firing state (Alerts view / alert history). The notification channel POSTs the webhook to the trigger service.

**1:10 — Agent wakes and diagnoses (40s).**
Open the new trace in SigNoz. Walk the tree:
`invoke_agent ouroboros-sre` → several `execute_tool` MCP spans (`error_rate`, `search_traces`, `query_metrics`, `search_logs`) → the `chat` LLM span with token counts. Point out: "the agent's investigation is itself telemetry."

**1:50 — Act + verify (30s).**
Same trace: the `execute_tool clear_latency` action span, then `verify_recovery`. Back on the dashboard, latency drops to baseline.

**2:20 — Watch the watcher (30s).**
On the AI Agent Observability dashboard, show the agent's own **token usage**, **estimated cost**, **p95/p99 latency**, and **tool-call distribution** — telemetry the agent produced about itself during the heal.

**2:50 — Close (15s).**
"One command with Foundry reproduces this entire stack — SigNoz, MCP, dashboards, alerts. Traces, metrics, logs, dashboards, alerts, Query Builder, and MCP, all in one closed loop."

## Fallback if the LLM/action loop misbehaves live
Use the deterministic trigger: `curl -XPOST localhost:8090/diagnose`, and if needed narrate over a pre-recorded successful run. The observability half (traces/metrics/dashboards/alerts) stands on its own.
