"""
OpenTelemetry GenAI semantic-convention attribute names, isolated here.

The GenAI semconv is still pre-1.0 and attribute names have shifted between
versions (e.g. gen_ai.system -> gen_ai.provider.name; per-message events ->
aggregated message attributes). Keeping every string in one module means a
future spec bump is a one-file change. Pinned to the v1.37+ baseline.
"""

# Span attributes
OPERATION_NAME = "gen_ai.operation.name"        # invoke_agent | chat | execute_tool
PROVIDER_NAME = "gen_ai.provider.name"          # openai | gemini | ...
REQUEST_MODEL = "gen_ai.request.model"
RESPONSE_MODEL = "gen_ai.response.model"
FINISH_REASONS = "gen_ai.response.finish_reasons"
USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
AGENT_NAME = "gen_ai.agent.name"
AGENT_ID = "gen_ai.agent.id"
TOOL_NAME = "gen_ai.tool.name"

# Content capture (opt-in; PII-sensitive — demo only)
INPUT_MESSAGES = "gen_ai.input.messages"
OUTPUT_MESSAGES = "gen_ai.output.messages"

# MCP tool-call attributes
MCP_METHOD_NAME = "mcp.method.name"
MCP_SESSION_ID = "mcp.session.id"

# --- Semantic-quality attributes (NOT in semconv; our own) -------------------
# An agent's real failure mode isn't a 500 — it's a tool that returns nothing
# usable while reporting OK at normal latency, which the LLM then confabulates
# over. Latency/error-rate monitoring is structurally blind to that, so we emit
# an explicit "did this step actually return usable content" signal per tool
# call, plus an aggregate per agent run.
TOOL_OUTPUT_VALID = "tool.output_valid"    # bool — usable content returned?
TOOL_OUTPUT_STATUS = "tool.output_status"  # ok | empty | error | unknown
TOOL_OUTPUT_ROWS = "tool.output_rows"      # int — rows the query returned

EVIDENCE_VISIBLE = "ouroboros.evidence.visible"    # bool — can we see the service at all?
EVIDENCE_SPANS_SEEN = "ouroboros.evidence.spans_seen"
EVIDENCE_USABLE = "ouroboros.evidence.usable_signals"
EVIDENCE_TOTAL = "ouroboros.evidence.total_signals"
EVIDENCE_DEGRADED = "ouroboros.evidence.degraded"  # bool — some signals unusable
EVIDENCE_MISSING = "ouroboros.evidence.missing"    # csv of unusable signal names

# Metric instrument names
METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"  # histogram, seconds
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"                # histogram, {token}
METRIC_COST = "gen_ai.client.cost"                              # custom histogram, USD
TOKEN_TYPE = "gen_ai.token.type"                                # input | output

# Operation-name values
OP_INVOKE_AGENT = "invoke_agent"
OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"
