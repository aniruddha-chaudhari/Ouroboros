#!/usr/bin/env bash
set -euo pipefail
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-demo-worker}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://signoz-otel-collector:4317}"
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_PYTHON_LOG_CORRELATION="true"
exec opentelemetry-instrument python worker.py
