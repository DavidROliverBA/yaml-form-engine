"""Tests for MCP tool invocation and response coercion."""

import json
import pytest

from yaml_form_engine.mcp_introspect import ToolSchema
from yaml_form_engine.mcp_invoker import (
    build_payload,
    coerce_responses,
    coerce_value,
    format_mcp_command,
)


def _make_schema(properties=None, required=None):
    """Helper to create a ToolSchema."""
    if properties is None:
        properties = {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        }
    return ToolSchema(
        name="test-tool",
        server="TEST",
        description="",
        parameters={
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        required=required or [],
    )


# ---- coerce_value ----

class TestCoerceValue:
    def test_string_passthrough(self):
        assert coerce_value("hello", "string") == "hello"

    def test_integer_from_string(self):
        assert coerce_value("42", "integer") == 42

    def test_integer_from_float_string(self):
        assert coerce_value("3.7", "integer") == 3

    def test_float_from_string(self):
        assert coerce_value("3.14", "number") == 3.14

    def test_boolean_true_string(self):
        assert coerce_value("true", "boolean") is True

    def test_boolean_false_string(self):
        assert coerce_value("false", "boolean") is False

    def test_boolean_yes_string(self):
        assert coerce_value("yes", "boolean") is True

    def test_boolean_from_bool(self):
        assert coerce_value(True, "boolean") is True

    def test_array_from_list(self):
        assert coerce_value(["a", "b"], "array") == ["a", "b"]

    def test_array_from_multiline_string(self):
        result = coerce_value("a\nb\nc", "array")
        assert result == ["a", "b", "c"]

    def test_parse_as_list(self):
        result = coerce_value("line1\nline2\n\nline3", "string", parse_as="list")
        assert result == ["line1", "line2", "line3"]

    def test_parse_as_list_from_list(self):
        result = coerce_value(["a", "b"], "string", parse_as="list")
        assert result == ["a", "b"]

    def test_none_returns_none(self):
        assert coerce_value(None, "string") is None

    def test_empty_string_returns_none(self):
        assert coerce_value("", "string") is None

    def test_invalid_integer_passes_through(self):
        assert coerce_value("not-a-number", "integer") == "not-a-number"


# ---- coerce_responses ----

class TestCoerceResponses:
    def test_flat_responses(self):
        schema = _make_schema()
        responses = {
            "parameters": {
                "query": "test search",
                "limit": "10",
            },
        }
        result = coerce_responses(responses, schema)
        assert result["query"] == "test search"
        assert result["limit"] == 10

    def test_skips_none_values(self):
        schema = _make_schema()
        responses = {
            "parameters": {
                "query": "test",
                "limit": "",
            },
        }
        result = coerce_responses(responses, schema)
        assert "query" in result
        assert "limit" not in result

    def test_multi_step_responses(self):
        schema = _make_schema(properties={
            "title": {"type": "string"},
            "enabled": {"type": "boolean"},
        })
        responses = {
            "step1": {"title": "My Page"},
            "step2": {"enabled": "true"},
        }
        result = coerce_responses(responses, schema)
        assert result["title"] == "My Page"
        assert result["enabled"] is True

    def test_ignores_unknown_fields(self):
        schema = _make_schema(properties={"known": {"type": "string"}})
        responses = {
            "step": {"known": "value", "unknown": "ignored"},
        }
        result = coerce_responses(responses, schema)
        assert result == {"known": "value"}


# ---- build_payload ----

class TestBuildPayload:
    def test_basic_payload(self):
        schema = _make_schema()
        responses = {
            "parameters": {"query": "test", "limit": "5"},
        }
        payload = build_payload(responses, schema)
        assert payload == {"query": "test", "limit": 5}

    def test_nested_object_reconstruction(self):
        schema = _make_schema(properties={
            "title": {"type": "string"},
            "parent": {
                "type": "object",
                "properties": {
                    "database_id": {"type": "string"},
                },
            },
        })
        responses = {
            "parameters": {"title": "My Page"},
            "parent": {"database_id": "abc-123"},
        }
        payload = build_payload(responses, schema)
        assert payload["title"] == "My Page"
        assert payload["parent"] == {"database_id": "abc-123"}

    def test_removes_none_values(self):
        schema = _make_schema()
        responses = {
            "parameters": {"query": "test", "limit": ""},
        }
        payload = build_payload(responses, schema)
        assert "limit" not in payload

    def test_empty_responses(self):
        schema = _make_schema()
        payload = build_payload({}, schema)
        assert payload == {}


# ---- format_mcp_command ----

class TestFormatMcpCommand:
    def test_with_server(self):
        result = format_mcp_command("MCP_DOCKER", "API-post-page", {"title": "Test"})
        assert "mcp__MCP_DOCKER__API-post-page" in result
        assert '"title": "Test"' in result

    def test_without_server(self):
        result = format_mcp_command("", "some-tool", {"x": 1})
        assert "some-tool" in result
        assert "mcp__" not in result

    def test_valid_json_in_output(self):
        payload = {"a": 1, "b": "two"}
        result = format_mcp_command("S", "T", payload)
        # Extract JSON from the output
        json_str = result.split("Payload:\n")[1]
        parsed = json.loads(json_str)
        assert parsed == payload
