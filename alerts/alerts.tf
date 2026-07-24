terraform {
  required_providers {
    signoz = {
      source = "SigNoz/signoz"
    }
  }
}

# Point at your Foundry-deployed SigNoz + a service-account API key.
provider "signoz" {
  endpoint    = var.signoz_endpoint # e.g. "http://localhost:8080"
  access_token = var.signoz_api_key
}

variable "signoz_endpoint" { type = string }
variable "signoz_api_key" { type = string, sensitive = true }

# 1) THRESHOLD alert — demo fleet error rate too high.
resource "signoz_alert" "fleet_error_rate" {
  alert   = "Ouroboros: demo-api error rate > 5%"
  alert_type = "METRIC_BASED_ALERT"
  version = "v5"
  severity = "warning"

  condition = jsonencode({
    compositeQuery = {
      queryType = "builder"
      builderQueries = {
        A = { dataSource = "traces", aggregateOperator = "count", expression = "A",
              filters = { items = [
                { key = { key = "service.name" }, op = "=", value = "demo-api" },
                { key = { key = "hasError" }, op = "=", value = "true" } ] } }
        B = { dataSource = "traces", aggregateOperator = "count", expression = "B",
              filters = { items = [{ key = { key = "service.name" }, op = "=", value = "demo-api" }] } }
      }
      queryFormulas = [{ expression = "A/B*100", legend = "error %" }]
    }
    op        = ">"
    target    = 5
    matchType = "1"    # at least once
  })

  # Fire the Ouroboros trigger so the agent auto-heals.
  preferred_channels = [var.notification_channel]
}

# 2) ANOMALY alert — agent/LLM latency deviates from its own baseline.
resource "signoz_alert" "agent_latency_anomaly" {
  alert    = "Ouroboros: agent latency anomaly"
  alert_type = "ANOMALY_BASED_ALERT"
  version  = "v5"
  severity = "warning"

  condition = jsonencode({
    compositeQuery = {
      queryType = "builder"
      builderQueries = {
        A = { dataSource = "metrics", aggregateAttribute = { key = "gen_ai.client.operation.duration" },
              timeAggregation = "p95", spaceAggregation = "p95", expression = "A" }
      }
    }
    op        = ">"
    target    = 3      # z-score threshold
    matchType = "1"
    algorithm = "standard"
    seasonality = "hourly"
  })

  preferred_channels = [var.notification_channel]
}

variable "notification_channel" {
  type    = string
  default = "ouroboros-webhook" # a SigNoz webhook channel pointing at :8090/webhook/signoz
}
