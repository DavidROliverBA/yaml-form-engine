"""Tests for form generation from MCP tool schemas."""

import json
import os

import pytest
import yaml

from yaml_form_engine.form_generator import generate_form, schema_to_form_dict
from yaml_form_engine.mcp_introspect import ToolSchema
from yaml_form_engine.schema import validate_form_schema


def _make_schema(
    name="test-tool",
    server="TEST_SERVER",
    description="A test tool",
    properties=None,
    required=None,
):
    """Helper to create a ToolSchema."""
    if properties is None:
        properties = {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }
    return ToolSchema(
        name=name,
        server=server,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        required=required or [],
    )


class TestSchemaToFormDict:
    def test_basic_form_structure(self):
        schema = _make_schema()
        form_dict = schema_to_form_dict(schema)

        assert "form" in form_dict
        form = form_dict["form"]
        assert form["id"] == "mcp-test-tool"
        assert form["title"] == "Test Tool"
        assert form["version"] == "1.0"
        assert len(form["steps"]) >= 3  # parameters + review + submit

    def test_parameters_step(self):
        schema = _make_schema()
        form_dict = schema_to_form_dict(schema)
        steps = form_dict["form"]["steps"]

        params_step = steps[0]
        assert params_step["id"] == "parameters"
        assert params_step["type"] == "input"
        assert len(params_step["fields"]) == 2

    def test_review_step_present(self):
        schema = _make_schema()
        form_dict = schema_to_form_dict(schema)
        steps = form_dict["form"]["steps"]

        review = next(s for s in steps if s["id"] == "review")
        assert review["type"] == "info"
        assert "test-tool" in review["content"]

    def test_submit_step_present(self):
        schema = _make_schema()
        form_dict = schema_to_form_dict(schema)
        steps = form_dict["form"]["steps"]

        submit = next(s for s in steps if s["id"] == "submit")
        assert submit["type"] == "submit"
        assert submit["mcp"]["server"] == "TEST_SERVER"
        assert submit["mcp"]["tool"] == "test-tool"
        assert submit["confirm"] is True
        assert submit["show_payload"] is True

    def test_nested_object_creates_sub_steps(self):
        schema = _make_schema(properties={
            "title": {"type": "string"},
            "parent": {
                "type": "object",
                "title": "Parent Page",
                "properties": {
                    "database_id": {"type": "string", "description": "Database ID"},
                },
                "required": ["database_id"],
            },
        })
        form_dict = schema_to_form_dict(schema)
        steps = form_dict["form"]["steps"]

        step_ids = [s["id"] for s in steps]
        assert "parameters" in step_ids
        assert "parent" in step_ids

        parent_step = next(s for s in steps if s["id"] == "parent")
        assert parent_step["title"] == "Parent Page"
        assert parent_step["fields"][0]["id"] == "database_id"
        assert parent_step["fields"][0]["required"] is True

    def test_validates_against_schema(self):
        """Generated form passes the engine's own schema validation."""
        schema = _make_schema()
        form_dict = schema_to_form_dict(schema)
        # Should not raise
        validate_form_schema(form_dict)

    def test_complex_schema_validates(self):
        """Complex schema with multiple types passes validation."""
        schema = _make_schema(properties={
            "title": {"type": "string"},
            "enabled": {"type": "boolean"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "tags": {
                "type": "array",
                "items": {"type": "string", "enum": ["a", "b", "c"]},
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
            },
        })
        form_dict = schema_to_form_dict(schema)
        validate_form_schema(form_dict)

    def test_empty_properties(self):
        schema = _make_schema(properties={})
        form_dict = schema_to_form_dict(schema)
        # Should still have review + submit steps
        steps = form_dict["form"]["steps"]
        assert len(steps) >= 2


class TestGenerateForm:
    def test_writes_yaml_file(self, tmp_path):
        schema = _make_schema()
        output_path = generate_form(schema, str(tmp_path))

        assert os.path.isfile(output_path)
        assert output_path.endswith(".yaml")

        with open(output_path) as f:
            loaded = yaml.safe_load(f)
        assert "form" in loaded

    def test_creates_output_directory(self, tmp_path):
        out_dir = tmp_path / "deep" / "nested"
        schema = _make_schema()
        output_path = generate_form(schema, str(out_dir))

        assert os.path.isfile(output_path)
        assert out_dir.is_dir()

    def test_filename_from_slug(self, tmp_path):
        schema = _make_schema(name="API-post-page")
        output_path = generate_form(schema, str(tmp_path))
        assert output_path.endswith("api-post-page.yaml")

    def test_generated_yaml_validates(self, tmp_path):
        """Full round-trip: generate → load → validate."""
        schema = _make_schema()
        output_path = generate_form(schema, str(tmp_path))

        with open(output_path) as f:
            loaded = yaml.safe_load(f)

        # Should not raise
        validate_form_schema(loaded)
