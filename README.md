# Ouroboros

A self-healing SRE agent that monitors a microservice fleet, diagnoses
problems, fixes the safe ones automatically, and asks for approval before
anything risky. Its only way of seeing the fleet and its only way of acting on
it is the **SigNoz MCP server** — no separate monitoring backend, no
hand-wired shortcuts. The agent is also fully instrumented into SigNoz itself,
so its own reasoning, tool calls, cost, and confidence show up as traces and
metrics right alongside the system it's watching.

## What it does

1. **Diagnose** — on an alert (or a lightweight watchdog noticing degradation),
   the agent queries SigNoz via MCP for latency, error rate, logs, and memory
   pressure, and turns the results into a clean evidence summary.
2. **Decide** — one LLM call reads that evidence and picks a remediation, or
   decides nothing is wrong.
3. **Gate** — three-tier autonomy:
   - confident + low-risk → heal automatically
   - unsure, or a high-impact action (like restarting a container) → propose
     the fix and wait for a human to approve it
   - telemetry itself is unusable → refuse to answer at all, rather than guess
4. **Act** — run the chosen remediation (a config rollback, or a real
   `docker restart` on the affected service).
5. **Verify** — re-check the fleet directly to confirm the fix actually
   worked before closing out the incident.

A React console shows the live incident timeline, the agent's cost/tokens per
run, and an approval card for anything waiting on a human.

## Architecture

- **Demo fleet** (`services/`) — a FastAPI API + load worker + MongoDB, with a
  `/fault` endpoint for deterministically injecting latency, errors, or a
  memory leak so there's something for the agent to detect and fix.
- **Ouroboros agent** (`agent/`) — the diagnose/decide/act/verify loop. Tools
  are SigNoz MCP calls and remediation actions, each wrapped in an OpenTelemetry
  span.
- **SigNoz** — self-hosted via [Foundry](https://signoz.io/); provides traces,
  metrics, logs, dashboards, alerts, and the MCP server the agent talks to.
- **Trigger service** (`scripts/trigger.py`) — receives SigNoz alert webhooks,
  runs a background watchdog that polls the fleet cheaply, exposes the
  incident timeline API, and serves the built UI.

Full component diagram and the remediation/autonomy model: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Setup

### Prerequisites

- Docker (with Compose)
- Python 3.11+
- Node.js (for the console UI)
- A [Groq](https://console.groq.com/keys) API key (free tier is fine)

### 1. Deploy SigNoz + MCP

```bash
curl -fsSL https://signoz.io/foundry.sh | bash
foundryctl gauge -f casting.yaml    # validate the deployment spec
foundryctl forge -f casting.yaml    # generate manifests + casting.yaml.lock
foundryctl cast  -f casting.yaml    # deploy
```

This brings up SigNoz on `:8080`, the OTel collector on `:4317`/`:4318`, and
the MCP server on `:8000`. In the SigNoz UI, create a service-account API key
under **Settings → Service Accounts** (Admin role).

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in:

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | LLM calls (Groq's OpenAI-compatible API) |
| `SIGNOZ_API_KEY` | The service-account key from step 1 |
| `SIGNOZ_MCP_URL` | Defaults to `http://localhost:8000/mcp` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Defaults to `http://localhost:4317` |
| `DEMO_API_URL` | Defaults to `http://localhost:8001` |

### 3. Bring up the demo fleet and agent

```bash
make fleet        # build + start the demo API, worker, and Mongo
make dashboards   # import dashboards/ai-agent-observability.json into SigNoz
make alerts       # create the threshold + anomaly alerts (via Terraform)
make ui           # build the React console
make trigger      # start the alert bridge + timeline API + console, on :8090
```

### 4. Try it

```bash
make demo-latency   # inject a latency fault; watch the agent detect + heal it
# or trigger a cycle directly:
curl -XPOST localhost:8090/diagnose
```

Open `http://localhost:8090` for the console. For UI development with
hot-reload instead of a static build:

```bash
make ui-dev   # http://localhost:5173, proxies the API to :8090
```

## Repo structure

```
agent/          the Ouroboros agent — telemetry, semantic conventions, MCP + action tools
services/       the demo fleet: FastAPI api + load worker
scripts/        fault injection, alert webhook trigger, incident timeline API
dashboards/     SigNoz dashboard, exported as JSON
alerts/         SigNoz alerts as Terraform
ui/             the React incident-timeline console
casting.yaml(.lock)   Foundry deployment spec for SigNoz + MCP
```

## Notes

- **Host metrics** aren't deployed by Foundry by default (see SigNoz issue
  #11829) — run a collection agent separately if you want the Infra view.
- **Content capture** (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`)
  is on for local/demo use; turn it off or redact at the Collector before
  running this against anything real, since it captures full prompts/completions.
- **GenAI semantic conventions are still pre-1.0** and shift between versions;
  attribute names are isolated in `agent/semconv.py` so a spec bump is a
  one-file change.

## License

MIT — see [`LICENSE`](LICENSE).
