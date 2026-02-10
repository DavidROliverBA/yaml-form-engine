"""Map JSON Schema properties to YAML form field definitions.

Pure functions with no I/O. Given a JSON Schema property definition,
produces the equivalent YAML form field dict for the form engine.
"""

from __future__ import annotations

import re

# Property names or description keywords that suggest long-form text
_TEXTAREA_KEYWORDS = {"description", "content", "body", "notes", "comment", "message", "summary"}

# Maximum enum length before switching from radio to select
_RADIO_ENUM_THRESHOLD = 4

# Maximum numeric range before switching from slider to number
_SLIDER_RANGE_THRESHOLD = 20

# Maximum string length before suggesting textarea
_TEXTAREA_MAX_LENGTH = 200


def _name_to_label(name: str) -> str:
    """Convert a property name to a human-readable label.

    Examples:
        page_title -> Page Title
        firstName -> First Name
        database_id -> Database ID
    """
    # Split on underscores and camelCase boundaries
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").replace("-", " ")
    return parts.title()


def _is_textarea_hint(name: str, description: str | None) -> bool:
    """Check if the property name or description suggests a textarea."""
    name_lower = name.lower()
    for keyword in _TEXTAREA_KEYWORDS:
        if keyword in name_lower:
            return True
    if description:
        desc_lower = description.lower()
        for keyword in _TEXTAREA_KEYWORDS:
            if keyword in desc_lower:
                return True
    return False


def map_property(name: str, prop_schema: dict, required: bool = False) -> dict:
    """Map a single JSON Schema property to a YAML field definition.

    Args:
        name: Property name from the JSON Schema.
        prop_schema: The property's schema definition.
        required: Whether this property is required.

    Returns:
        A dict suitable for use as a field in a YAML form step.
    """
    schema_type = prop_schema.get("type", "string")
    description = prop_schema.get("description")
    title = prop_schema.get("title")
    enum_values = prop_schema.get("enum")
    default = prop_schema.get("default")
    max_length = prop_schema.get("maxLength")
    minimum = prop_schema.get("minimum")
    maximum = prop_schema.get("maximum")
    pattern = prop_schema.get("pattern")

    field = {
        "id": name,
        "label": title or description or _name_to_label(name),
    }

    if required:
        field["required"] = True

    if default is not None:
        field["default"] = default

    # --- Type mapping ---

    if schema_type == "boolean":
        field["type"] = "checkbox"

    elif schema_type in ("number", "integer"):
        if minimum is not None and maximum is not None:
            range_size = maximum - minimum
            if range_size <= _SLIDER_RANGE_THRESHOLD:
                field["type"] = "slider"
                field["min"] = minimum
                field["max"] = maximum
            else:
                field["type"] = "number"
                field["min"] = minimum
                field["max"] = maximum
        else:
            field["type"] = "number"
            if minimum is not None:
                field["min"] = minimum
            if maximum is not None:
                field["max"] = maximum

    elif schema_type == "array":
        items_schema = prop_schema.get("items", {})
        items_enum = items_schema.get("enum")

        if items_enum:
            field["type"] = "multiselect"
            field["options"] = [{"value": v, "label": str(v)} for v in items_enum]
        else:
            field["type"] = "textarea"
            field["placeholder"] = "One item per line"
            field["parse_as"] = "list"

    elif schema_type == "object":
        # Objects become nested steps - caller handles this
        field["type"] = "_nested_object"
        field["properties"] = prop_schema.get("properties", {})
        field["object_required"] = prop_schema.get("required", [])

    else:
        # Default: string types
        if enum_values:
            if len(enum_values) <= _RADIO_ENUM_THRESHOLD:
                field["type"] = "radio"
            else:
                field["type"] = "select"
            field["options"] = [{"value": v, "label": str(v)} for v in enum_values]
        elif max_length and max_length > _TEXTAREA_MAX_LENGTH:
            field["type"] = "textarea"
        elif _is_textarea_hint(name, description):
            field["type"] = "textarea"
        else:
            field["type"] = "text"

    # Pattern hint
    if pattern and field["type"] in ("text", "textarea"):
        field["placeholder"] = f"Format: {pattern}"

    return field


def map_schema_to_fields(schema: dict) -> list[dict]:
    """Map all properties in a JSON Schema to YAML field definitions.

    Args:
        schema: A JSON Schema dict with 'properties' and optionally 'required'.

    Returns:
        List of field dicts, excluding nested objects (type '_nested_object').
    """
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    fields = []
    for name, prop_schema in properties.items():
        field = map_property(name, prop_schema, name in required_fields)
        if field["type"] != "_nested_object":
            fields.append(field)

    return fields


def map_schema_to_steps(schema: dict, base_step_title: str = "Parameters") -> list[dict]:
    """Map a full tool schema to wizard steps.

    Top-level non-object properties go into a single 'Parameters' step.
    Top-level object properties each become their own step.

    Args:
        schema: A JSON Schema dict with 'properties' and optionally 'required'.
        base_step_title: Title for the main parameters step.

    Returns:
        List of step dicts ready for the YAML form definition.
    """
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    flat_fields = []
    nested_steps = []

    for name, prop_schema in properties.items():
        field = map_property(name, prop_schema, name in required_fields)

        if field["type"] == "_nested_object":
            # Create a sub-step for this object
            sub_fields = map_schema_to_fields({
                "properties": field["properties"],
                "required": field.get("object_required", []),
            })
            if sub_fields:
                sub_step_id = name.lower().replace(" ", "_")
                label = prop_schema.get("title") or prop_schema.get("description") or _name_to_label(name)
                nested_steps.append({
                    "id": sub_step_id,
                    "title": label,
                    "type": "input",
                    "fields": sub_fields,
                })
        else:
            flat_fields.append(field)

    steps = []

    if flat_fields:
        steps.append({
            "id": "parameters",
            "title": base_step_title,
            "type": "input",
            "fields": flat_fields,
        })

    steps.extend(nested_steps)

    return steps
