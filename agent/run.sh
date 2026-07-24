#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Load .env (GROQ_API_KEY, SIGNOZ_API_KEY, ...) into the process environment —
# nothing else does this for a host-side run.
if [ -f .env ]; then set -a; source .env; set +a; fi
# Auto-instrument the agent: HTTP + OpenAI-client spans (works against Groq's
# OpenAI-compatible API too) -> chat spans, gen_ai.client.* metrics
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-ouroboros-agent}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4317}"
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_PYTHON_LOG_CORRELATION="true"
# Opt-in GenAI content capture — DEMO ONLY (captures prompts/completions; PII risk)
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="true"
exec opentelemetry-instrument python -m agent.agent
