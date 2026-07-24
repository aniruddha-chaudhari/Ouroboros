# Ouroboros — Architecture

A self-observing, self-healing SRE agent. It watches a demo fleet through SigNoz,
diagnoses incidents, and remediates them under a three-tier autonomy model
(auto-heal / propose-for-approval / no-action). Every decision the agent makes is
itself OpenTelemetry-traced into SigNoz — you watch the watcher.

```mermaid
flowchart TB
    subgraph fleet["Demo fleet — 'the patient'"]
        api["demo-api (FastAPI)<br/>/orders · /fault control plane"]
        worker["load worker<br/>(generates traffic)"]
        mongo[("MongoDB")]
        worker -->|HTTP| api
        api --> mongo
    end

    subgraph signoz["SigNoz (self-hosted via Foundry)"]
        ingest["OTel collector<br/>(ingester)"]
        ch[("ClickHouse<br/>traces · metrics · logs")]
        mcp["SigNoz MCP server<br/>(query + alert tools)"]
        alerts["Alerts<br/>latency · error-rate"]
        dash["Dashboard<br/>fleet health + agent observability"]
        ingest --> ch
        mcp --> ch
        alerts --> ch
        dash --> ch
    end

    subgraph trigger["Trigger + timeline service (:8090)"]
        watch["Watchdog loop<br/>cheap probe every 15s (no LLM)"]
        hook["/webhook/signoz"]
        api_ep["/diagnose · /approve · /reject · /timeline"]
        pending["PENDING approvals<br/>(in-memory)"]
    end

    subgraph agent["Ouroboros agent (Groq LLM)"]
        diagnose["DIAGNOSE<br/>gather evidence via SigNoz MCP<br/>latency · errors · memory · logs"]
        decide["DECIDE<br/>LLM picks action + confidence"]
        gate{"GATE<br/>3-tier autonomy"}
        act["ACT<br/>clear_latency · clear_errors<br/>restart_service (real docker restart)"]
        verify["VERIFY<br/>re-check fleet ground truth"]
    end

    subgraph ui["React console + landing (:8090)"]
        hero["Hero (ASCII statue)"]
        console["Live console<br/>ring · timeline · stats"]
        card["Approval card<br/>Approve / Reject"]
    end

    %% telemetry out
    api -. OTel spans .-> ingest
    worker -. OTel spans .-> ingest
    agent -. traces its own reasoning .-> ingest

    %% triggers into the agent
    alerts -->|alert fires| hook
    watch -->|degradation detected| diagnose
    hook --> diagnose
    api_ep -->|manual /diagnose| diagnose

    %% the loop
    diagnose -->|SigNoz MCP queries| mcp
    diagnose --> decide --> gate
    gate -->|confident + low-risk| act
    gate -->|unsure OR high-impact| pending
    gate -->|nothing wrong| verify
    act --> verify
    act -->|restart| api

    %% human approval path
    pending -->|shown as| card
    card -->|Approve| api_ep
    api_ep -->|apply_approved| act
    card -->|Reject| api_ep

    %% ui data
    api_ep --> console
    console --> card
    hero --> console
```

## The three-tier autonomy model

| Tier | Condition | What happens |
|------|-----------|--------------|
| **Auto-heal** | Confident (≥ auto threshold) **and** low blast-radius | Executes the fix immediately, then verifies |
| **Propose** | Not confident enough, **or** a high-impact action (e.g. `restart_service`) | Parks an approval card; a human clicks Approve → it runs |
| **No action** | Evidence shows the service is healthy | Does nothing (proves the agent doesn't "fix" what isn't broken) |

## Two kinds of remediation

- **Config reverts** (`clear_latency`, `clear_errors`) — flip the demo-api's fault
  control back to healthy; a stand-in for a feature-flag / bad-config rollback.
  Low blast radius, eligible for auto-heal.
- **Real infrastructure action** (`restart_service`) — actually runs
  `docker restart` on the demo-api container, like restarting an unhealthy pod.
  Genuinely reclaims leaked memory. High blast radius → always approval-gated.
