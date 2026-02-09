"""YAML form schema validation.

Validates form definitions against the expected structure before rendering.
Rejects malformed configs early with clear error messages.
"""

from typing import Any

VALID_FIELD_TYPES = {
    "text", "textarea", "select", "multiselect", "number",
    "date", "checkbox", "radio", "slider", "file", "score",
}

VALID_STEP_TYPES = {
    "input", "data_driven", "computed", "export", "info", "conditional",
}

VALID_EXPORT_TEMPLATES = {
    "table_per_section", "confluence_table", "flat_csv", "raw_json",
}


class SchemaError(Exception):
    """Raised when a form YAML fails validation."""
    pass


def validate_form_schema(form_def: dict) -> None:
    """Validate a loaded form definition dict.

    Args:
        form_def: Parsed YAML dict with top-level 'form' key.

    Raises:
        SchemaError: If validation fails.
    """
    if not isinstance(form_def, dict):
        raise SchemaError("Form definition must be a YAML mapping")

    if "form" not in form_def:
        raise SchemaError("Missing top-level 'form' key")

    form = form_def["form"]
    _require_string(form, "id", "form")
    _require_string(form, "title", "form")

    # Validate data_source if present
    if "data_source" in form:
        _validate_data_source(form["data_source"])

    # Validate filters if present
    if "filters" in form:
        if not isinstance(form["filters"], list):
            raise SchemaError("form.filters must be a list")
        for i, f in enumerate(form["filters"]):
            _validate_filter(f, i)

    # Validate steps
    if "steps" not in form or not isinstance(form["steps"], list):
        raise SchemaError("form.steps must be a non-empty list")
    if len(form["steps"]) == 0:
        raise SchemaError("form.steps must contain at least one step")

    step_ids = set()
    for i, step in enumerate(form["steps"]):
        _validate_step(step, i, step_ids)


def _require_string(obj: dict, key: str, context: str) -> None:
    if key not in obj or not isinstance(obj[key], str) or not obj[key].strip():
        raise SchemaError(f"{context}.{key} is required and must be a non-empty string")


def _validate_data_source(ds: dict) -> None:
    if not isinstance(ds, dict):
        raise SchemaError("form.data_source must be a mapping")
    _require_string(ds, "path", "data_source")
    _require_string(ds, "key", "data_source")

    path = ds["path"]
    # Security: reject obviously dangerous paths
    if ".." in path:
        raise SchemaError(f"data_source.path must not contain '..': {path}")
    # Only allow YAML/JSON data files
    if not path.endswith((".yaml", ".yml", ".json")):
        raise SchemaError(f"data_source.path must be a .yaml, .yml, or .json file: {path}")


def _validate_filter(f: dict, index: int) -> None:
    ctx = f"filters[{index}]"
    if not isinstance(f, dict):
        raise SchemaError(f"{ctx} must be a mapping")
    _require_string(f, "id", ctx)
    _require_string(f, "label", ctx)
    _require_string(f, "type", ctx)

    if f["type"] not in ("select", "multiselect"):
        raise SchemaError(f"{ctx}.type must be 'select' or 'multiselect'")


def _validate_step(step: dict, index: int, seen_ids: set) -> None:
    ctx = f"steps[{index}]"
    if not isinstance(step, dict):
        raise SchemaError(f"{ctx} must be a mapping")

    _require_string(step, "id", ctx)
    _require_string(step, "title", ctx)

    step_id = step["id"]
    if step_id in seen_ids:
        raise SchemaError(f"Duplicate step id: {step_id}")
    seen_ids.add(step_id)

    step_type = step.get("type", "input")
    if step_type not in VALID_STEP_TYPES:
        raise SchemaError(f"{ctx}.type '{step_type}' is not valid. Must be one of: {VALID_STEP_TYPES}")

    # Type-specific validation
    if step_type == "input":
        _validate_input_step(step, ctx)
    elif step_type == "data_driven":
        _validate_data_driven_step(step, ctx)
    elif step_type == "export":
        _validate_export_step(step, ctx)


def _validate_input_step(step: dict, ctx: str) -> None:
    fields = step.get("fields", [])
    if not isinstance(fields, list):
        raise SchemaError(f"{ctx}.fields must be a list")

    field_ids = set()
    for i, field in enumerate(fields):
        fctx = f"{ctx}.fields[{i}]"
        if not isinstance(field, dict):
            raise SchemaError(f"{fctx} must be a mapping")
        _require_string(field, "id", fctx)
        _require_string(field, "type", fctx)

        if field["id"] in field_ids:
            raise SchemaError(f"Duplicate field id in {ctx}: {field['id']}")
        field_ids.add(field["id"])

        if field["type"] not in VALID_FIELD_TYPES:
            raise SchemaError(
                f"{fctx}.type '{field['type']}' is not valid. "
                f"Must be one of: {VALID_FIELD_TYPES}"
            )

        # Select/multiselect/radio need options
        if field["type"] in ("select", "multiselect", "radio"):
            if "options" not in field:
                raise SchemaError(f"{fctx} of type '{field['type']}' requires 'options'")


def _validate_data_driven_step(step: dict, ctx: str) -> None:
    if "per_item" not in step or not isinstance(step["per_item"], list):
        raise SchemaError(f"{ctx} of type 'data_driven' requires a 'per_item' field list")

    for i, field in enumerate(step["per_item"]):
        fctx = f"{ctx}.per_item[{i}]"
        if not isinstance(field, dict):
            raise SchemaError(f"{fctx} must be a mapping")
        _require_string(field, "id", fctx)
        _require_string(field, "type", fctx)

        if field["type"] not in VALID_FIELD_TYPES:
            raise SchemaError(
                f"{fctx}.type '{field['type']}' is not valid. "
                f"Must be one of: {VALID_FIELD_TYPES}"
            )


def _validate_export_step(step: dict, ctx: str) -> None:
    formats = step.get("formats", [])
    if not isinstance(formats, list) or len(formats) == 0:
        raise SchemaError(f"{ctx} of type 'export' requires a non-empty 'formats' list")

    for i, fmt in enumerate(formats):
        fctx = f"{ctx}.formats[{i}]"
        _require_string(fmt, "id", fctx)
        _require_string(fmt, "label", fctx)
