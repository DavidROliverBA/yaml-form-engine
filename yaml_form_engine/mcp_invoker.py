"""MCP tool invocation support.

Coerces form responses to JSON Schema types and builds invocation payloads.
Does NOT execute tools directly - produces validated payloads for the user
or Claude Code to invoke.
"""

from __future__ import annotations

import json
from typing import Any

from .mcp_introspect import ToolSchema


def coerce_value(value: Any, schema_type: str, parse_as: str | None = None) -> Any:
    """Coerce a single form value to the expected JSON Schema type.

    Args:
        value: The raw form value (usually a string from Streamlit).
        schema_type: The target JSON Schema type.
        parse_as: Optional hint (e.g., 'list' for textarea → array).

    Returns:
        The coerced value.
    """
    if value is None or value == "":
        return None

    if parse_as == "list":
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        if isinstance(value, list):
            return value
        return [str(value)]

    if schema_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    if schema_type == "integer":
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return value

    if schema_type in ("number", "float"):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value

    if schema_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return [value]

    # Default: string pass-through
    return str(value) if value is not None else None


def coerce_responses(responses: dict, schema: ToolSchema) -> dict:
    """Coerce all form responses to match the tool's JSON Schema types.

    Args:
        responses: Form responses keyed by step_id → field_id → value.
        schema: The target tool's schema.

    Returns:
        A flat dict of coerced values keyed by parameter name.
    """
    properties = schema.parameters.get("properties", {})
    result = {}

    # Flatten responses from all steps into a single dict
    flat = {}
    for step_id, step_data in responses.items():
        if isinstance(step_data, dict):
            for field_id, value in step_data.items():
                flat[field_id] = value
        else:
            flat[step_id] = step_data

    for param_name, param_schema in properties.items():
        if param_name in flat:
            value = flat[param_name]
            schema_type = param_schema.get("type", "string")
            coerced = coerce_value(value, schema_type)
            if coerced is not None:
                result[param_name] = coerced

    return result


def build_payload(responses: dict, schema: ToolSchema) -> dict:
    """Build the final JSON payload for MCP tool invocation.

    Coerces types and reconstructs nested objects from dot-notation field IDs.

    Args:
        responses: Form responses keyed by step_id → field_id → value.
        schema: The target tool's schema.

    Returns:
        A dict ready for JSON serialisation and MCP tool invocation.
    """
    properties = schema.parameters.get("properties", {})
    coerced = coerce_responses(responses, schema)

    # Reconstruct nested objects from step-based responses
    for param_name, param_schema in properties.items():
        if param_schema.get("type") == "object" and param_name not in coerced:
            # Look for a step matching this param name
            step_id = param_name.lower().replace(" ", "_")
            if step_id in responses and isinstance(responses[step_id], dict):
                nested_props = param_schema.get("properties", {})
                nested = {}
                for nested_name, nested_schema in nested_props.items():
                    if nested_name in responses[step_id]:
                        nested_type = nested_schema.get("type", "string")
                        val = coerce_value(responses[step_id][nested_name], nested_type)
                        if val is not None:
                            nested[nested_name] = val
                if nested:
                    coerced[param_name] = nested

    # Remove None values
    return {k: v for k, v in coerced.items() if v is not None}


def format_mcp_command(server: str, tool: str, payload: dict) -> str:
    """Format the MCP tool invocation for display.

    Produces a human-readable representation that can be used with Claude Code.

    Args:
        server: MCP server name.
        tool: Tool name.
        payload: The JSON payload dict.

    Returns:
        A formatted string showing the tool invocation.
    """
    tool_name = f"mcp__{server}__{tool}" if server else tool
    payload_str = json.dumps(payload, indent=2)
    return f"Tool: {tool_name}\n\nPayload:\n{payload_str}"
