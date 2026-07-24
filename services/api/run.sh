#!/usr/bin/env bash
set -euo pipefail

# Zero-code auto-instrumentation: FastAPI, HTTP clients, logging, PyMongo all
# get traced/metered/logged and shipped to SigNoz via OTLP. Trace-log
# correlation is enabled so logs carry trace_id/span_id.
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-demo-api}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://signoz-otel-collector:4317}"
export OTEL_EXPORTER_OTLP_PROTOCOL="${OTEL_EXPORTER_OTLP_PROTOCOL:-grpc}"
export OTEL_PYTHON_LOG_CORRELATION="true"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="otlp"
export OTEL_TRACES_EXPORTER="otlp"

exec opentelemetry-instrument \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
