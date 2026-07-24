# Credits & Third-Party Components

Built on top of (rule 5 — original work is judged; dependencies declared):

- **SigNoz** + **Foundry** (Apache-2.0) — observability backend & deployment
- **SigNoz MCP server** — agent's telemetry query/action interface
- **OpenTelemetry** Python SDK + auto-instrumentation (Apache-2.0)
- **opentelemetry-instrumentation-openai-v2** — GenAI chat spans/metrics
- **FastAPI**, **Uvicorn**, **PyMongo**, **httpx**, **MongoDB**
- **OpenAI Python SDK** — pointed at **Groq**'s OpenAI-compatible API (swappable for OpenAI/Gemini/LiteLLM)
- OpenTelemetry **GenAI semantic conventions** (attribute names)

Original work: the self-observing self-healing loop, the fleet/fault control
plane, the instrumentation layer (agent/telemetry.py, agent/semconv.py), the
SigNoz dashboards and alerts, and the incident-timeline UI.
