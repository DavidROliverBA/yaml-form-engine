"""Tests for MCP tool introspection and schema parsing."""

import json
import os
import pytest

from yaml_form_engine.mcp_introspect import ToolSchema, load_schema_from_file, parse_tool_schema


class TestParseToolSchema:
    def test_format_a_full_mcp(self):
        """Format A: Full MCP tool definition with inputSchema."""
        raw = {
            "name": "API-post-page",
            "server": "MCP_DOCKER",
            "description": "Create a page in Notion",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent": {"type": "object", "properties": {"database_id": {"type": "string"}}},
                    "properties": {"type": "object"},
                },
                "required": ["parent"],
            },
        }
        schema = parse_tool_schema(raw)
        assert schema.name == "API-post-page"
        assert schema.server == "MCP_DOCKER"
        assert schema.description == "Create a page in Notion"
        assert "parent" in schema.parameters["properties"]
        assert "parent" in schema.required

    def test_format_b_claude_code(self):
        """Format B: Claude Code tool definition with __ naming."""
        raw = {
            "name": "mcp__MCP_DOCKER__API-post-search",
            "description": "Search Notion",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        }
        schema = parse_tool_schema(raw)
        assert schema.name == "API-post-search"
        assert schema.server == "MCP_DOCKER"
        assert schema.required == ["query"]

    def test_format_c_bare_schema(self):
        """Format C: Bare schema with properties at top level."""
        raw = {
            "name": "create-issue",
            "server": "jira",
            "description": "Create a Jira issue",
            "properties": {
                "project": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["project", "summary"],
        }
        schema = parse_tool_schema(raw)
        assert schema.name == "create-issue"
        assert schema.server == "jira"
        assert schema.parameters["type"] == "object"
        assert "project" in schema.parameters["properties"]
        assert schema.required == ["project", "summary"]

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="'name' field"):
            parse_tool_schema({"description": "test"})

    def test_not_dict_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            parse_tool_schema("not a dict")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="'name' field"):
            parse_tool_schema({"name": ""})

    def test_no_parameters_defaults_empty(self):
        schema = parse_tool_schema({"name": "test-tool"})
        assert schema.parameters == {"type": "object", "properties": {}}

    def test_input_schema_underscore_variant(self):
        """Accepts input_schema as well as inputSchema."""
        raw = {
            "name": "test-tool",
            "input_schema": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
            },
        }
        schema = parse_tool_schema(raw)
        assert "x" in schema.parameters["properties"]

    def test_server_extraction_from_name(self):
        """Server extracted from mcp__SERVER__tool format."""
        raw = {"name": "mcp__plugin_atlassian_atlassian__createJiraIssue"}
        schema = parse_tool_schema(raw)
        assert schema.server == "plugin_atlassian_atlassian"
        assert schema.name == "createJiraIssue"

    def test_slug_property(self):
        schema = ToolSchema(name="API-post-page", server="MCP", description="", parameters={})
        assert schema.slug == "api-post-page"

    def test_slug_with_underscores(self):
        schema = ToolSchema(name="create_jira_issue", server="", description="", parameters={})
        assert schema.slug == "create-jira-issue"


class TestLoadSchemaFromFile:
    def test_load_valid_file(self, tmp_path):
        schema_file = tmp_path / "test-schema.json"
        schema_file.write_text(json.dumps({
            "name": "test-tool",
            "server": "test",
            "description": "A test tool",
            "properties": {"x": {"type": "string"}},
        }))
        raw = load_schema_from_file(str(schema_file))
        assert raw["name"] == "test-tool"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_schema_from_file("/nonexistent/path.json")

    def test_invalid_json_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            load_schema_from_file(str(bad_file))
