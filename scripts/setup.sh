#!/usr/bin/env bash
#
# Ouroboros one-shot setup.
#
# Automates:
#   Step 1  Deploy SigNoz + MCP via Foundry (gauge -> forge -> cast)
#   Step 3  Create .env from template
#   Step 4  Start the demo fleet (auto-detects the SigNoz docker network)
#   Step 5  Create the agent's Python venv + install deps
#
# Still MANUAL afterwards (need the SigNoz UI or intentional choices):
#   Step 2  Create a SigNoz service-account API key  -> paste into .env as SIGNOZ_API_KEY
#   Step 6  Import dashboards/ai-agent-observability.json (SigNoz UI)
#   Step 7  make alerts        (Terraform)   OR   make alerts-mcp (Python, no TF)
#   Step 8  source .venv/bin/activate && make trigger   (:8090)
#   Step 9  make demo-latency  /  curl -XPOST localhost:8090/diagnose
#
# Usage:   bash scripts/setup.sh            (run from repo root)
#          SKIP_FOUNDRY=1 bash scripts/setup.sh   (skip step 1 if SigNoz already up)
set -euo pipefail

# --- run from repo root regardless of where invoked ------------------------
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[error] %s\033[0m\n' "$*" >&2; exit 1; }

# --- prerequisite check ----------------------------------------------------
say "Checking prerequisites"
missing=()
for bin in docker python3 curl make; do
  command -v "$bin" >/dev/null 2>&1 || missing+=("$bin")
done
docker compose version >/dev/null 2>&1 || missing+=("docker-compose-plugin")
if [ "${SKIP_FOUNDRY:-0}" != "1" ]; then
  command -v foundryctl >/dev/null 2>&1 || missing+=("foundryctl")
fi
if [ "${#missing[@]}" -ne 0 ]; then
  die "Missing required tools: ${missing[*]}
  - docker + compose: https://docs.docker.com/get-docker/
  - foundryctl:       curl -fsSL https://signoz.io/foundry.sh | bash
  - python3 3.11+ / curl / make: install via your package manager (WSL on Windows)"
fi
echo "OK: docker, python3, curl, make$( [ "${SKIP_FOUNDRY:-0}" != "1" ] && echo ', foundryctl' )"

# ==========================================================================
# STEP 1 — Deploy SigNoz + MCP
# ==========================================================================
if [ "${SKIP_FOUNDRY:-0}" = "1" ]; then
  say "Step 1: SKIPPED (SKIP_FOUNDRY=1)"
else
  say "Step 1: Deploying SigNoz + MCP via Foundry"
  foundryctl gauge -f casting.yaml
  foundryctl forge -f casting.yaml     # writes casting.yaml.lock — commit it
  foundryctl cast  -f casting.yaml
  [ -f casting.yaml.lock ] && echo "casting.yaml.lock generated (remember to commit it)" \
                           || warn "casting.yaml.lock not found after forge — check foundryctl output"
fi

# --- wait for SigNoz UI (8080) and MCP (8000) to answer --------------------
say "Waiting for SigNoz UI (:8080) and MCP (:8000/livez)"
wait_for() { # url, label, tries
  local url="$1" label="$2" tries="${3:-60}" i=0
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    i=$((i+1)); [ "$i" -ge "$tries" ] && { warn "$label not responding at $url after ${tries}s — continuing anyway"; return 0; }
    printf '.'; sleep 1
  done
  echo " $label up"
}
wait_for "http://localhost:8080"        "SigNoz UI" 90
wait_for "http://localhost:8000/livez"  "MCP"       60

# ==========================================================================
# STEP 3 — Configure env
# ==========================================================================
say "Step 3: Configuring .env"
if [ -f .env ]; then
  echo ".env already exists — leaving it untouched"
else
  cp .env.example .env
  echo "Created .env from .env.example"
fi
grep -q '^GROQ_API_KEY=gsk_\.\.\.' .env 2>/dev/null && \
  warn "Edit .env: set GROQ_API_KEY (free, no card: console.groq.com/keys)"
grep -q '^SIGNOZ_API_KEY=your-signoz' .env 2>/dev/null && \
  warn "Edit .env: set SIGNOZ_API_KEY — create it in SigNoz UI: Settings -> Service Accounts -> Admin role (Step 2)"

# ==========================================================================
# STEP 4 — Start the demo fleet (auto-detect the SigNoz network)
# ==========================================================================
say "Step 4: Starting the demo fleet"
# The fleet joins SigNoz's external docker network. Foundry may not name it
# 'signoz_default'; detect the real one and patch docker-compose.fleet.yaml.
detected_net="$(docker network ls --format '{{.Name}}' | grep -i signoz | head -n1 || true)"
if [ -n "$detected_net" ]; then
  current_net="$(grep -E '^\s*name:\s*' docker-compose.fleet.yaml | tail -n1 | sed -E 's/^\s*name:\s*//')"
  if [ "$detected_net" != "$current_net" ]; then
    warn "Docker network is '$detected_net' but compose says '$current_net' — patching docker-compose.fleet.yaml"
    cp docker-compose.fleet.yaml docker-compose.fleet.yaml.bak
    sed -i -E "s|^(\s*name:\s*).*$|\1$detected_net|" docker-compose.fleet.yaml
    echo "Patched (backup: docker-compose.fleet.yaml.bak)"
  else
    echo "Network name matches: $detected_net"
  fi
else
  warn "No 'signoz' docker network found. Is SigNoz running? Check: docker network ls"
fi
make fleet

# ==========================================================================
# STEP 5 — Python venv for the agent (runs on host, not in a container)
# ==========================================================================
say "Step 5: Creating agent Python venv"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "Created .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r agent/requirements.txt
opentelemetry-bootstrap -a install   # pull in auto-instrumentation plugins

# --- done ------------------------------------------------------------------
say "Setup complete"
cat <<EOF

Next (manual) steps:
  2. In SigNoz UI (http://localhost:8080): Settings -> Service Accounts -> new Admin
     key, paste into .env as SIGNOZ_API_KEY. Also set GROQ_API_KEY in .env.
  6. Import dashboards/ai-agent-observability.json (SigNoz UI -> Dashboards -> Import JSON)
  7. make alerts        # Terraform (needs SIGNOZ_ENDPOINT + SIGNOZ_API_KEY env vars)
     make alerts-mcp    # or: no Terraform, pure Python
  8. source .venv/bin/activate && make trigger        # timeline service on :8090
  9. make demo-latency  &&  curl -XPOST localhost:8090/diagnose
     Run the agent loop:  ./agent/run.sh

Repo root: $ROOT
EOF
