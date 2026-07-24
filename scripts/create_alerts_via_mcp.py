"""
Create the SigNoz alerts via the MCP server (alternative to Terraform).

This doubles as a demo of the agent's write-capability over MCP: the same
signoz_create_alert tool the agent can call at runtime. Requires SigNoz
>= v0.120.0 for the alert-rule MCP tools.

Usage:  SIGNOZ_API_KEY=... python scripts/create_alerts_via_mcp.py
"""
from agent.tools import signoz_mcp


def main():
    print(signoz_mcp.create_alert(
        name="Ouroboros: demo-api error rate > 5%",
        expr="traces error rate for service.name='demo-api'",
        threshold=5.0,
    ))
    print(signoz_mcp.create_alert(
        name="Ouroboros: agent latency anomaly",
        expr="p95 gen_ai.client.operation.duration anomaly",
        threshold=3.0,
    ))


if __name__ == "__main__":
    main()
