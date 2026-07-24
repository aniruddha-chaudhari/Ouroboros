#!/usr/bin/env bash
# Inject a demo fault so SigNoz sees degradation and fires an alert.
#   ./scripts/inject_fault.sh latency   # +800ms latency
#   ./scripts/inject_fault.sh errors    # 30% 500s
#   ./scripts/inject_fault.sh leak       # memory leak
set -euo pipefail
API="${DEMO_API_URL:-http://localhost:8001}"
case "${1:-latency}" in
  latency) curl -s -XPOST "$API/fault" -H 'content-type: application/json' -d '{"latency_ms":800}' ;;
  errors)  curl -s -XPOST "$API/fault" -H 'content-type: application/json' -d '{"error_rate":0.3}' ;;
  leak)    curl -s -XPOST "$API/fault" -H 'content-type: application/json' -d '{"mem_leak":true}' ;;
  clear)   curl -s -XPOST "$API/fault" -H 'content-type: application/json' -d '{"latency_ms":0,"error_rate":0,"mem_leak":false}' ;;
  *) echo "usage: $0 {latency|errors|leak|clear}"; exit 1 ;;
esac
echo
