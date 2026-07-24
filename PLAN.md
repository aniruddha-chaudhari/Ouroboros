# Ouroboros — Build & Compliance Plan

> **Track 01 · AI & Agent Observability** — *"Agents of SigNoz" (WeMakeDevs × SigNoz), deadline Jul 26.*
> Solo build, ~1–2 working days, AI-assisted.

**One-liner:** An AI SRE agent that (a) is fully OpenTelemetry-GenAI instrumented into SigNoz, and (b) uses the SigNoz MCP server as its senses and hands. It watches a small demo microservice fleet *and itself* — detects anomalies via SigNoz alerts, root-causes by querying traces/logs/metrics through MCP, executes a remediation, then verifies the fix in SigNoz. Every reasoning step and MCP tool call is itself a GenAI span in SigNoz: **you watch the watcher.**

---

## Part A — Compliance matrix (every rule → how we satisfy it)

### Agency Protocols

| # | Rule | How Ouroboros satisfies it | Deliverable |
|---|------|----------------------------|-------------|
| 1 | Solo or team ≤4 | Solo | — |
| 2 | **Must use/integrate SigNoz; deeper use scores higher** | Core architecture is SigNoz + OTel end to end; agent's only "eyes/hands" are SigNoz MCP tools | Whole repo |
| 3 | Pick one track | Track 01, AI & Agent Observability | README |
| 4 | Interviews ≠ guaranteed job | (informational) | — |
| 5 | Templates/OSS/APIs allowed; original work judged | We use Foundry, OTel SDKs, OpenLLMetry, LangGraph — all declared; original work = the self-healing loop + instrumentation + dashboards | `CREDITS.md` |
| 6 | Submission form TBD | Monitor; keep a "submission" section ready to fill | `SUBMISSION.md` (draft) |
| 7 | **AI assistant use must be declared or disqualified** | Explicit declaration file listing every AI tool used and where | `AI_USAGE.md` |
| 8 | Coding starts only after hackathon starts; notes/diagrams allowed before | This PLAN.md + architecture diagram are pre-start notes (allowed); code commits dated after start | Git history |
| 9 | Teams 1–4 | Solo | — |
| 10 | IP belongs to team | Sole author | `LICENSE` |
| 11 | Code of conduct | Respectful conduct | — |
| 12 | Violations → disqualification | Compliance checklist below | this doc |

### SigNoz Field Requirements

| # | Requirement | How we satisfy it | Deliverable |
|---|-------------|-------------------|-------------|
| 1 | Install SigNoz **using Foundry** (installs SigNoz + MCP in one step) | `casting.yaml` with `spec.mcp.spec.enabled: true`; one-command `foundryctl cast` | `casting.yaml` |
| 2 | More SigNoz features = better (MCP, Query Builder, dashboards, alerts) | Hits all 10 features in the checklist below | dashboards/, alerts/, agent/ |
| 3 | **Reproducible: repo must include `casting.yaml` + `casting.yaml.lock`; judges re-run Foundry** | Both committed; `.gitignore` deliberately does NOT exclude the lock file; clean-clone repro tested | `casting.yaml`, `casting.yaml.lock` |

### Judging criteria → deliverable that earns each

| Criterion | What we ship to win it |
|-----------|------------------------|
| **Potential Impact** | Self-healing SRE loop = real production pain solved; README quantifies MTTR reduction in the demo |
| **Creativity & Innovation** | The recursive "agent observes itself observing" hook; closed action loop beyond SigNoz's own demo |
| **Technical Excellence** | Idiomatic OTel GenAI semconv spans; deterministic Foundry deploy; IaC alerts/dashboards |
| **Best Use of SigNoz** | All 10 SigNoz surfaces exercised *and shown in the demo* (see checklist) |
| **User Experience** | React incident-timeline UI + deep links into SigNoz traces; one-command setup |
| **Presentation Quality** | Tight 2–4 min demo video, architecture diagram, feature→criterion table, clean README |

### SigNoz feature checklist (the "Best Use of SigNoz" score)

- [ ] **Traces** — GenAI span tree: `invoke_agent → chat → execute_tool`, error spans
- [ ] **Metrics** — `gen_ai.client.token.usage`, `gen_ai.client.operation.duration` (p95/p99), custom cost histogram
- [ ] **Logs** — structured, trace-correlated (`OTEL_PYTHON_LOG_CORRELATION=true`)
- [ ] **Dashboards** — "AI Agent Observability" dashboard, exported as JSON and committed
- [ ] **Alerts** — 1 threshold (cost/latency/error-rate) + 1 anomaly alert, committed as IaC
- [ ] **Query Builder v5** — formulas (error % = A/B×100); agent uses `signoz_execute_builder_query`
- [ ] **MCP server** — agent's toolset; also creates a dashboard/alert via MCP in the demo
- [ ] **Service accounts / API keys** — used for MCP auth; documented
- [ ] **Host / infra metrics** — collection agent deployed (works around Foundry issue #11829)
- [ ] **Saved views + notification channels + alert history** — cheap "depth" extras

---

## Part B — Architecture

```
                    ┌─────────────────────────────────────────┐
                    │   SigNoz (self-hosted via Foundry)        │
                    │   UI :8080   OTLP :4317/:4318             │
                    │   Traces · Metrics · Logs · Dashboards    │
                    │   Alerts · Query Builder v5               │
                    │   MCP server :8000  ◄──────────┐          │
                    └───────▲───────────────┬────────┼──────────┘
                            │ OTLP          │ alert  │ MCP tools
                            │ (telemetry)   │ webhook │ (query/act)
        ┌───────────────────┼───────────────┼────────┼───────────┐
        │                   │               ▼        │           │
  ┌─────┴──────┐     ┌──────┴───────┐  ┌────────────┴────────┐   │
  │ Demo fleet │     │ Host-metrics │  │  Ouroboros AGENT     │   │
  │ (patient)  │     │  collector   │  │  (the doctor)        │   │
  │            │     └──────────────┘  │  LangGraph + LLM     │   │
  │ FastAPI API│◄─────────────────────►│  tools = SigNoz MCP  │   │
  │ worker     │   action tools        │  + action tools      │   │
  │ MongoDB    │  (restart/rollback/   │  self-instrumented   │   │
  │ +fault-inj │   flag-off/scale)     │  (invoke_agent spans)│   │
  └────────────┘                       └──────────┬───────────┘   │
                                                  │ emits its own │
                                                  │ GenAI traces  │
                                                  └───────────────┘
        ┌──────────────────────────────────────────────────┐
        │  React UI: incident timeline + deep links to SigNoz│
        └──────────────────────────────────────────────────┘
```

**The loop:** fault injected → SigNoz alert fires → webhook triggers agent → agent queries traces/logs/metrics via MCP → diagnoses → picks + executes an action tool → verifies recovery in SigNoz → posts timeline to UI. All agent steps are GenAI spans in SigNoz.

**Stack:** Python 3.11 (FastAPI demo fleet + agent host), LangGraph + OpenAI/Gemini, SigNoz self-hosted MCP on :8000, OTel native auto-instrumentation + thin manual span layer, React/TS UI. IaC: `casting.yaml`(+lock), dashboards-as-JSON, alerts via SigNoz Terraform provider and/or MCP.

---

## Part C — Phased build plan (checkpoints, not clock-watching)

### Phase 0 — Deploy & wire (target ~2h)
- [ ] Install `foundryctl`; run `foundryctl gauge` → `forge` → `cast` with the committed `casting.yaml`
- [ ] Verify UI :8080, OTLP :4318, MCP :8000 (`curl localhost:8000/livez`)
- [ ] Create service account + API key (Settings → Service Accounts, Admin)
- [ ] Register MCP with the agent / Claude Code
- [ ] **Commit `casting.yaml.lock`** (verify not gitignored)
- **✅ Gate:** SigNoz up, MCP reachable, lock file committed.

### Phase 1 — Demo fleet + telemetry (target ~4h)
- [ ] FastAPI API + worker + Mongo call, with a `/fault` endpoint (latency / 500s / memory pressure)
- [ ] Auto-instrument via `opentelemetry-instrument`; confirm traces + logs + metrics land in SigNoz
- [ ] Deploy host-metrics collection agent (Foundry issue #11829 workaround)
- **✅ Gate:** injecting a fault visibly changes traces/metrics in SigNoz.

### Phase 2 — Agent + self-healing loop (target ~4h)
- [ ] Agent scaffold (LangGraph or plain tool-loop) with SigNoz MCP tools + action tools
- [ ] Manual `invoke_agent` / `execute_tool` spans + custom cost histogram
- [ ] One clean **diagnose → act → verify** loop working end to end
- **✅ Gate (GO/NO-GO):** if the loop works → keep full scope. If not → **cut action tools, ship the observability-cockpit fallback** (still competitive).

### Phase 3 — Dashboards + alerts + trigger (target ~4h)
- [ ] "AI Agent Observability" dashboard (tokens, cost, p95/p99 latency, tool-call distribution, error rate) → **export JSON to `dashboards/`**
- [ ] 1 threshold alert + 1 anomaly alert → **commit to `alerts/`** (Terraform or MCP script)
- [ ] Wire alert → webhook → agent trigger; add a manual "diagnose now" button for demo determinism
- [ ] Add saved views
- **✅ Gate:** alert fires and auto-triggers the agent.

### Phase 4 — UX + presentation (target ~4h)
- [ ] React incident-timeline UI with deep links into SigNoz traces
- [ ] README: problem, architecture diagram, **one-command repro**, feature→criterion table, screenshots
- [ ] `DEMO.md` script + record 2–4 min video (fault → alert → agent watching itself → fix → recovery)
- [ ] Fill `AI_USAGE.md`, `CREDITS.md`; final clean-clone repro test
- [ ] (Bonus) warm-up blog post on Dev.to/Medium — eligible for the blog side-track, doubles as README narrative
- **✅ Gate:** fresh `git clone` → `foundryctl cast` → demo runs.

---

## Part D — Deliverables checklist (repo root)

- [ ] `casting.yaml` (MCP enabled) **+ `casting.yaml.lock`**
- [ ] `docker-compose.yaml` / Makefile — demo fleet + fault injector + host-metrics collector
- [ ] `agent/` source + `requirements.txt`; `.env.example`
- [ ] `dashboards/*.json` (exported SigNoz dashboards) + import instructions
- [ ] `alerts/*.tf` or `alerts/create_alerts.py` (MCP)
- [ ] `README.md` — architecture, one-command repro, feature→criterion table, screenshots
- [ ] `DEMO.md` + recorded video link
- [ ] `AI_USAGE.md` (rule 7 — **disqualification if missing**)
- [ ] `CREDITS.md` (templates/OSS/APIs used — rule 5)
- [ ] `LICENSE`
- [ ] `.gitignore` — verified NOT excluding `casting.yaml.lock` or committed configs

---

## Part E — Risk register

| Risk | Mitigation |
|------|------------|
| Self-healing loop too fragile in 2 days | Phase-2 GO/NO-GO gate → fall back to observability cockpit |
| MCP alert tools 404 | Pin SigNoz ≥ v0.120.0 in `casting.yaml` (see file comments) |
| Foundry doesn't deploy host collector (#11829) | Deploy collector separately; document it |
| GenAI semconv pre-1.0, attribute names shift | Isolate attribute strings in one mapping module; pin instrumentor versions |
| Content capture = PII | Enable only for demo; note prod should redact at Collector |
| Lock file gitignored by accident | Explicit `.gitignore` check in Phase 0 gate |
| Submission form adds a live-link field | Keep a short-lived cloud VM plan ready; monitor the form |

---

## Part F — AI usage declaration (fill as you go — rule 7)

Record every AI assistant used and where: e.g. "Claude — repo scaffolding, instrumentation boilerplate, dashboard JSON drafting, README"; "Copilot — inline completions in agent/"; "ChatGPT — none". **Missing this file = disqualification.**
