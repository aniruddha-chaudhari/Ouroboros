.PHONY: fleet dashboards alerts trigger ui ui-dev demo-latency demo-errors clean repro-check

fleet:
	docker compose -f docker-compose.fleet.yaml up -d --build

dashboards:
	@echo "Import dashboards/ai-agent-observability.json via SigNoz UI: Dashboards -> New -> Import JSON"
	@echo "(or use the SigNoz MCP signoz_import_dashboard tool)"

alerts:
	cd alerts && terraform init && terraform apply -auto-approve \
	  -var="signoz_endpoint=$${SIGNOZ_ENDPOINT:-http://localhost:8080}" \
	  -var="signoz_api_key=$${SIGNOZ_API_KEY}"

alerts-mcp:
	python scripts/create_alerts_via_mcp.py

ui:
	cd ui && npm install && npm run build
	@echo "UI built -> served at http://localhost:8090 once 'make trigger' is running"

ui-dev:
	cd ui && npm install && npm run dev   # hot-reload console on :5173 (proxies API to :8090)

trigger:
	./scripts/run_trigger.sh   # opentelemetry-instrument uvicorn — serves built UI + timeline API on :8090

demo-latency:
	./scripts/inject_fault.sh latency
	@echo "Latency injected. Alert should fire -> agent heals. Watch SigNoz + curl localhost:8090/timeline"

demo-errors:
	./scripts/inject_fault.sh errors

clean:
	docker compose -f docker-compose.fleet.yaml down -v
	./scripts/inject_fault.sh clear || true

# Verify the two reproducibility files are present and not gitignored.
repro-check:
	@test -f casting.yaml && echo "OK casting.yaml present" || (echo "MISSING casting.yaml" && exit 1)
	@test -f casting.yaml.lock && echo "OK casting.yaml.lock present" || echo "WARN: run 'foundryctl forge' to generate casting.yaml.lock, then commit it"
	@git check-ignore casting.yaml.lock >/dev/null 2>&1 && (echo "ERROR: lock is gitignored!" && exit 1) || echo "OK lock not ignored"
