# Ouroboros — a self-observing, self-healing SRE agent on SigNoz

> **"Agents of SigNoz" hackathon · Track 01 — AI & Agent Observability**

An AI SRE agent that **watches your systems _and itself_**. It is fully
instrumented with OpenTelemetry GenAI semantic conventions into SigNoz, and its
only senses and hands are the **SigNoz MCP server**: it detects an anomaly via a
SigNoz alert, root-causes by querying traces/logs/metrics through MCP, executes a
remediation, then verifies the fix in SigNoz. Every reasoning step and tool call
is itself a GenAI span in SigNoz — so **you watch the watcher.**

This fuses three of the track's example builds — *SRE Sidekick with SigNoz MCP* +
*Self-healing infra with SigNoz metrics* + *AI agents with E2E observability* —
into one closed loop.

## The loop

```
 fault injected → SigNoz alert fires → webhook triggers agent
     → agent queries traces/logs/metrics via MCP  (DIAGNOSE)
     → LLM picks the single best fix               (DECIDE)
     → agent executes a remediation action tool    (ACT)
     → agent re-queries SigNoz to confirm recovery (VERIFY)
 …and the agent's own tokens / cost / latency / tool-calls stream into SigNoz.
```

## Architecture

- **Demo fleet ("the patient")** — FastAPI API + load worker + MongoDB, auto-instrumented via `opentelemetry-instrument`, with a `/fault` control plane for deterministic latency / error / memory-leak injection.
- **Ouroboros agent ("the doctor")** — Python; tools are SigNoz MCP calls + remediation actions; wrapped in `invoke_agent` / `execute_tool` GenAI spans with a custom cost metric.
- **SigNoz** — self-hosted via **Foundry** (SigNoz + MCP in one `casting.yaml`); dashboards, threshold + anomaly alerts, Query Builder v5.
- **Trigger + timeline** — alert webhook → agent run; incident timeline API for the UI.

## Quickstart (one-command-ish repro)

```bash
# 0. Deploy SigNoz + MCP with Foundry (installs both in one step)
curl -fsSL https://signoz.io/foundry.sh | bash
foundryctl gauge -f casting.yaml    # validate
foundryctl forge -f casting.yaml    # generates pours/ + writes casting.yaml.lock
foundryctl cast  -f casting.yaml    # deploy
#   UI :8080 · OTLP :4317/:4318 · MCP :8000
#   -> create a service-account API key: Settings → Service Accounts (Admin)

cp .env.example .env && $EDITOR .env   # add GROQ_API_KEY + SIGNOZ_API_KEY

make fleet        # build + start demo fleet (API, worker, Mongo)
make dashboards   # import dashboards/ai-agent-observability.json
make alerts       # create threshold + anomaly alerts (Terraform) 
make ui           # build the React console (npm install + vite build)
make trigger      # start alert→agent bridge + timeline API + console on :8090

# Demo the loop:
make demo-latency  # inject latency → alert fires → agent heals → recovery
# or deterministically:
curl -XPOST localhost:8090/diagnose
```

### Console UI

A React console (`ui/`, Vite) visualises the closed loop and streams the incident
timeline (alert → agent decision → remediation → recovery) with the agent's own
cost/tokens/confidence.

```bash
make ui         # build once → served at http://localhost:8090 by `make trigger`
# …or hot-reload during development (proxies the API to :8090):
make ui-dev     # http://localhost:5173
```

## What this exercises in SigNoz (Best-Use-of-SigNoz mapping)

| SigNoz feature | Where | Judging criterion it serves |
|----------------|-------|------------------------------|
| **Traces** (GenAI span tree `invoke_agent→chat→execute_tool`) | `agent/telemetry.py` | Best Use of SigNoz, Technical Excellence |
| **Metrics** (`gen_ai.client.token.usage`, `.operation.duration`, custom `.cost`) | `agent/telemetry.py`, dashboard | Best Use of SigNoz |
| **Logs** (trace-correlated) | `run.sh` (`OTEL_PYTHON_LOG_CORRELATION`) | Best Use of SigNoz |
| **Dashboards** (exported JSON, reproducible) | `dashboards/` | Presentation, Best Use |
| **Alerts** (threshold + anomaly, as code) | `alerts/` | Best Use, Technical Excellence |
| **Query Builder v5** (formula error% = A/B×100) | `agent/tools/signoz_mcp.py`, dashboard | Technical Excellence |
| **MCP server** (agent's toolset; also creates alerts) | `agent/tools/signoz_mcp.py` | Creativity, Best Use |
| **Service accounts / API keys** | `.env`, MCP auth | Technical Excellence |
| **Host / infra metrics** | collector (see note) | Best Use |
| **Alert history / saved views** | MCP tools | Best Use |

## Reproducibility

- `casting.yaml` **and** `casting.yaml.lock` are committed; `.gitignore` explicitly keeps the lock and ignores only the regenerable `pours/`.
- All three SigNoz images are pinned to exact versions in `casting.yaml` (`signoz` v0.134.0, `signoz-mcp-server` v0.9.0, `signoz-otel-collector` v0.144.6) — the same versions this project was built and demoed against, not floating `latest` tags.
- Dashboards are committed as JSON; alerts as Terraform (or via `scripts/create_alerts_via_mcp.py`).
- Judges can re-run `foundryctl cast -f casting.yaml` to reproduce the full stack.

## Notes & caveats

- **Host metrics:** Foundry deploys SigNoz + MCP but not the Docker host-metrics collector (SigNoz issue #11829). Run a collection agent separately if you showcase the Infra view.
- **MCP tool versions:** alert-rule MCP tools need SigNoz ≥ v0.120.0, which v0.134.0 (pinned above) satisfies.
- **GenAI semconv is pre-1.0:** attribute strings are isolated in `agent/semconv.py` for easy version bumps.
- **Content capture** (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`) is on for the demo only — redact at the Collector in production.

See `PLAN.md` for the full compliance matrix and build plan, `AI_USAGE.md` for
the AI-assistant declaration, and `DEMO.md` for the demo script.
