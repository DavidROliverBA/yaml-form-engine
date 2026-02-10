"""Tests for the JSON Schema → YAML field type mapper."""

import pytest

from yaml_form_engine.type_mapper import (
    map_property,
    map_schema_to_fields,
    map_schema_to_steps,
)


# ---- map_property: basic type mappings ----

class TestStringMapping:
    def test_plain_string(self):
        field = map_property("title", {"type": "string"}, required=False)
        assert field["type"] == "text"
        assert field["id"] == "title"

    def test_string_with_enum_small(self):
        """Enum with <= 4 values -> radio."""
        field = map_property("status", {
            "type": "string",
            "enum": ["draft", "active", "archived"],
        }, required=False)
        assert field["type"] == "radio"
        assert len(field["options"]) == 3
        assert field["options"][0] == {"value": "draft", "label": "draft"}

    def test_string_with_enum_large(self):
        """Enum with > 4 values -> select."""
        field = map_property("country", {
            "type": "string",
            "enum": ["UK", "US", "DE", "FR", "ES"],
        }, required=False)
        assert field["type"] == "select"
        assert len(field["options"]) == 5

    def test_string_with_max_length_over_200(self):
        """MaxLength > 200 -> textarea."""
        field = map_property("bio", {"type": "string", "maxLength": 500}, required=False)
        assert field["type"] == "textarea"

    def test_string_with_description_keyword(self):
        """Property name containing textarea keyword -> textarea."""
        field = map_property("description", {"type": "string"}, required=False)
        assert field["type"] == "textarea"

    def test_string_with_body_keyword(self):
        field = map_property("message_body", {"type": "string"}, required=False)
        assert field["type"] == "textarea"

    def test_string_with_content_in_description(self):
        """Description containing textarea keyword -> textarea."""
        field = map_property("field_x", {
            "type": "string",
            "description": "The main body content of the page",
        }, required=False)
        assert field["type"] == "textarea"

    def test_string_with_pattern(self):
        field = map_property("email", {
            "type": "string",
            "pattern": "^[a-z]+@example.com$",
        }, required=False)
        assert field["type"] == "text"
        assert "Format:" in field["placeholder"]

    def test_string_with_enum_exactly_4(self):
        """Boundary: exactly 4 enum values -> radio."""
        field = map_property("priority", {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        }, required=False)
        assert field["type"] == "radio"


class TestNumberMapping:
    def test_plain_number(self):
        field = map_property("count", {"type": "number"}, required=False)
        assert field["type"] == "number"

    def test_integer(self):
        field = map_property("age", {"type": "integer"}, required=False)
        assert field["type"] == "number"

    def test_number_with_small_range(self):
        """Range <= 20 -> slider."""
        field = map_property("score", {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
        }, required=False)
        assert field["type"] == "slider"
        assert field["min"] == 0
        assert field["max"] == 10

    def test_number_with_large_range(self):
        """Range > 20 -> number."""
        field = map_property("year", {
            "type": "integer",
            "minimum": 1900,
            "maximum": 2100,
        }, required=False)
        assert field["type"] == "number"
        assert field["min"] == 1900
        assert field["max"] == 2100

    def test_number_with_boundary_range(self):
        """Exactly 20 range -> slider."""
        field = map_property("rating", {
            "type": "number",
            "minimum": 0,
            "maximum": 20,
        }, required=False)
        assert field["type"] == "slider"

    def test_number_with_only_minimum(self):
        field = map_property("quantity", {
            "type": "integer",
            "minimum": 0,
        }, required=False)
        assert field["type"] == "number"
        assert field["min"] == 0
        assert "max" not in field


class TestBooleanMapping:
    def test_boolean(self):
        field = map_property("enabled", {"type": "boolean"}, required=False)
        assert field["type"] == "checkbox"


class TestArrayMapping:
    def test_array_with_enum_items(self):
        """Array with enum items -> multiselect."""
        field = map_property("tags", {
            "type": "array",
            "items": {"type": "string", "enum": ["a", "b", "c"]},
        }, required=False)
        assert field["type"] == "multiselect"
        assert len(field["options"]) == 3

    def test_array_without_enum(self):
        """Array without enum -> textarea with parse_as: list."""
        field = map_property("items", {
            "type": "array",
            "items": {"type": "string"},
        }, required=False)
        assert field["type"] == "textarea"
        assert field["parse_as"] == "list"


class TestObjectMapping:
    def test_nested_object(self):
        """Object properties -> _nested_object marker."""
        field = map_property("address", {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
            },
        }, required=False)
        assert field["type"] == "_nested_object"
        assert "street" in field["properties"]


# ---- Common field attributes ----

class TestFieldAttributes:
    def test_required_flag(self):
        field = map_property("name", {"type": "string"}, required=True)
        assert field["required"] is True

    def test_not_required(self):
        field = map_property("name", {"type": "string"}, required=False)
        assert "required" not in field

    def test_default_value(self):
        field = map_property("status", {
            "type": "string",
            "default": "active",
        }, required=False)
        assert field["default"] == "active"

    def test_title_preferred_for_label(self):
        field = map_property("x", {
            "type": "string",
            "title": "My Custom Title",
            "description": "Some description",
        }, required=False)
        assert field["label"] == "My Custom Title"

    def test_description_fallback_for_label(self):
        field = map_property("x", {
            "type": "string",
            "description": "Some field description",
        }, required=False)
        assert field["label"] == "Some field description"

    def test_name_fallback_for_label(self):
        field = map_property("my_field_name", {"type": "string"}, required=False)
        assert field["label"] == "My Field Name"

    def test_missing_type_defaults_to_string(self):
        field = map_property("x", {}, required=False)
        assert field["type"] == "text"


# ---- map_schema_to_fields ----

class TestMapSchemaToFields:
    def test_flat_schema(self):
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"},
            },
            "required": ["name"],
        }
        fields = map_schema_to_fields(schema)
        assert len(fields) == 3
        assert fields[0]["id"] == "name"
        assert fields[0]["required"] is True
        assert fields[1]["id"] == "age"
        assert fields[2]["id"] == "active"

    def test_excludes_nested_objects(self):
        schema = {
            "properties": {
                "name": {"type": "string"},
                "address": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
        fields = map_schema_to_fields(schema)
        assert len(fields) == 1
        assert fields[0]["id"] == "name"

    def test_empty_schema(self):
        fields = map_schema_to_fields({})
        assert fields == []

    def test_no_required(self):
        schema = {
            "properties": {"x": {"type": "string"}},
        }
        fields = map_schema_to_fields(schema)
        assert "required" not in fields[0]


# ---- map_schema_to_steps ----

class TestMapSchemaToSteps:
    def test_flat_schema_single_step(self):
        schema = {
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }
        steps = map_schema_to_steps(schema)
        assert len(steps) == 1
        assert steps[0]["id"] == "parameters"
        assert steps[0]["type"] == "input"
        assert len(steps[0]["fields"]) == 2

    def test_nested_object_creates_sub_step(self):
        schema = {
            "properties": {
                "title": {"type": "string"},
                "properties_obj": {
                    "type": "object",
                    "title": "Page Properties",
                    "properties": {
                        "colour": {"type": "string"},
                        "size": {"type": "integer"},
                    },
                },
            },
        }
        steps = map_schema_to_steps(schema)
        assert len(steps) == 2
        assert steps[0]["id"] == "parameters"
        assert len(steps[0]["fields"]) == 1  # Only 'title'
        assert steps[1]["id"] == "properties_obj"
        assert steps[1]["title"] == "Page Properties"
        assert len(steps[1]["fields"]) == 2

    def test_only_objects_no_flat(self):
        schema = {
            "properties": {
                "parent": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
            },
        }
        steps = map_schema_to_steps(schema)
        assert len(steps) == 1
        assert steps[0]["id"] == "parent"

    def test_custom_base_title(self):
        schema = {"properties": {"x": {"type": "string"}}}
        steps = map_schema_to_steps(schema, base_step_title="Settings")
        assert steps[0]["title"] == "Settings"

    def test_empty_schema(self):
        steps = map_schema_to_steps({})
        assert steps == []
