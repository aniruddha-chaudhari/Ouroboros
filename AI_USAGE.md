# AI Assistant Usage Declaration

Per hackathon rule 7, all AI-assistant usage on this project is declared here.

| Tool | Model | Used for |
|------|-------|----------|
| Claude Code (Anthropic) | Claude Opus | Repo scaffolding; OpenTelemetry / GenAI-semconv instrumentation boilerplate (`agent/telemetry.py`, `agent/semconv.py`); drafting the dashboard JSON and Terraform alert definitions; the React console UI; Foundry `casting.yaml` version pinning; README, ARCHITECTURE, DEMO and other docs |

No other AI assistants (Copilot, ChatGPT, Cursor, etc.) were used.

The project's original contributions are the author's own work, built on top of
the assistance above and the open-source components listed in CREDITS.md:

- the closed diagnose → decide → act → verify self-healing loop and its
  framing as an agent that observes itself in SigNoz;
- the **semantic-quality signals** in `agent/semconv.py` (`tool.output_valid`,
  `tool.output_status`, `ouroboros.evidence.*`) — instrumenting "did this tool
  actually return usable evidence" rather than only latency and error rate,
  which is the failure mode that makes an SRE agent confabulate;
- the SigNoz MCP server as the agent's entire sensory surface, with every tool
  call emitted as an `execute_tool` GenAI span;
- the deterministic fault-injection control plane in the demo fleet and the
  alert → agent → recovery incident timeline.
