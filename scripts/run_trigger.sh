#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Load .env (GROQ_API_KEY, SIGNOZ_API_KEY, ...) into the process environment —
# nothing else does this for a host-side run.
if [ -f .env ]; then set -a; source .env; set +a; fi
# Same auto-instrumentation env as agent/run.sh — the trigger service imports
# agent.agent and calls run_once() directly (webhook + /diagnose), so it needs
# the same OTel wrapper or those runs produce zero spans in SigNoz.
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-ouroboros-agent}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4317}"
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_PYTHON_LOG_CORRELATION="true"
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="true"
exec opentelemetry-instrument uvicorn scripts.trigger:app --host 0.0.0.0 --port 8090
