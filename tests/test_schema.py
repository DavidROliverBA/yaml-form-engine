"""Tests for YAML form schema validation."""

import pytest
from yaml_form_engine.schema import SchemaError, validate_form_schema


def _minimal_form(**overrides):
    form = {
        "form": {
            "id": "test-form",
            "title": "Test Form",
            "steps": [
                {
                    "id": "step1",
                    "title": "Step 1",
                    "type": "input",
                    "fields": [
                        {"id": "name", "type": "text", "label": "Name"}
                    ],
                }
            ],
        }
    }
    form["form"].update(overrides)
    return form


class TestTopLevel:
    def test_valid_minimal_form(self):
        validate_form_schema(_minimal_form())

    def test_missing_form_key(self):
        with pytest.raises(SchemaError, match="Missing top-level 'form' key"):
            validate_form_schema({"steps": []})

    def test_missing_id(self):
        with pytest.raises(SchemaError, match="form.id"):
            validate_form_schema(_minimal_form(id=""))

    def test_missing_title(self):
        with pytest.raises(SchemaError, match="form.title"):
            validate_form_schema(_minimal_form(title=""))

    def test_empty_steps(self):
        with pytest.raises(SchemaError, match="at least one step"):
            validate_form_schema(_minimal_form(steps=[]))


class TestDataSource:
    def test_valid_data_source(self):
        form = _minimal_form(data_source={"path": "data/test.yaml", "key": "items"})
        validate_form_schema(form)

    def test_path_traversal_rejected(self):
        with pytest.raises(SchemaError, match="must not contain"):
            form = _minimal_form(data_source={"path": "../../etc/passwd.yaml", "key": "items"})
            validate_form_schema(form)

    def test_non_yaml_extension_rejected(self):
        with pytest.raises(SchemaError, match="must be a .yaml"):
            form = _minimal_form(data_source={"path": "data/test.py", "key": "items"})
            validate_form_schema(form)


class TestSteps:
    def test_duplicate_step_ids(self):
        with pytest.raises(SchemaError, match="Duplicate step id"):
            form = _minimal_form(steps=[
                {"id": "s1", "title": "S1", "type": "input", "fields": []},
                {"id": "s1", "title": "S2", "type": "input", "fields": []},
            ])
            validate_form_schema(form)

    def test_invalid_step_type(self):
        with pytest.raises(SchemaError, match="not valid"):
            form = _minimal_form(steps=[
                {"id": "s1", "title": "S1", "type": "dangerous"},
            ])
            validate_form_schema(form)

    def test_data_driven_requires_per_item(self):
        with pytest.raises(SchemaError, match="per_item"):
            form = _minimal_form(steps=[
                {"id": "s1", "title": "S1", "type": "data_driven"},
            ])
            validate_form_schema(form)

    def test_export_requires_formats(self):
        with pytest.raises(SchemaError, match="formats"):
            form = _minimal_form(steps=[
                {"id": "s1", "title": "S1", "type": "export", "formats": []},
            ])
            validate_form_schema(form)


class TestFields:
    def test_invalid_field_type(self):
        with pytest.raises(SchemaError, match="not valid"):
            form = _minimal_form(steps=[
                {
                    "id": "s1", "title": "S1", "type": "input",
                    "fields": [{"id": "f1", "type": "executable", "label": "Bad"}],
                },
            ])
            validate_form_schema(form)

    def test_select_requires_options(self):
        with pytest.raises(SchemaError, match="requires 'options'"):
            form = _minimal_form(steps=[
                {
                    "id": "s1", "title": "S1", "type": "input",
                    "fields": [{"id": "f1", "type": "select", "label": "Pick"}],
                },
            ])
            validate_form_schema(form)

    def test_duplicate_field_ids(self):
        with pytest.raises(SchemaError, match="Duplicate field id"):
            form = _minimal_form(steps=[
                {
                    "id": "s1", "title": "S1", "type": "input",
                    "fields": [
                        {"id": "f1", "type": "text", "label": "A"},
                        {"id": "f1", "type": "text", "label": "B"},
                    ],
                },
            ])
            validate_form_schema(form)
