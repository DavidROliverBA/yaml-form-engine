"""Generate YAML form definitions from MCP tool schemas.

Orchestrates mcp_introspect and type_mapper to produce complete,
ready-to-run YAML form definitions.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .mcp_introspect import ToolSchema, load_schema_from_file, parse_tool_schema
from .type_mapper import _name_to_label, map_schema_to_steps


def schema_to_form_dict(schema: ToolSchema) -> dict:
    """Convert a ToolSchema to the YAML form dict structure.

    Produces a complete form definition with:
    - Parameter steps (one per top-level group)
    - A review/info step showing what will be submitted
    - A submit step with MCP tool metadata

    Args:
        schema: A normalised ToolSchema.

    Returns:
        A dict ready for YAML serialisation.
    """
    steps = map_schema_to_steps(schema.parameters, base_step_title="Parameters")

    # Add review step
    steps.append({
        "id": "review",
        "title": "Review",
        "type": "info",
        "content": (
            "Review your entries above before submitting.\n\n"
            f"**Tool:** `{schema.name}`\n\n"
            f"**Server:** `{schema.server}`\n\n"
            f"**Description:** {schema.description}"
        ),
    })

    # Add submit step
    submit_step = {
        "id": "submit",
        "title": "Submit",
        "type": "submit",
        "mcp": {
            "server": schema.server,
            "tool": schema.name,
        },
        "confirm": True,
        "show_payload": True,
    }
    steps.append(submit_step)

    form_dict = {
        "form": {
            "id": f"mcp-{schema.slug}",
            "title": _name_to_label(schema.name),
            "description": schema.description,
            "version": "1.0",
            "steps": steps,
        }
    }

    return form_dict


def generate_form(
    schema: ToolSchema,
    output_dir: str = "forms/mcp",
) -> str:
    """Generate a YAML form from an MCP tool schema and write it to disk.

    Args:
        schema: A normalised ToolSchema.
        output_dir: Directory to write the YAML file to.

    Returns:
        The path to the generated YAML file.
    """
    form_dict = schema_to_form_dict(schema)

    # Ensure output directory exists
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filename = f"{schema.slug}.yaml"
    filepath = out_path / filename

    with open(filepath, "w") as f:
        yaml.dump(
            form_dict,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

    return str(filepath)


def generate_form_from_file(
    schema_path: str,
    output_dir: str = "forms/mcp",
) -> str:
    """Load a schema JSON file and generate a YAML form.

    Args:
        schema_path: Path to a JSON file containing an MCP tool schema.
        output_dir: Directory to write the YAML file to.

    Returns:
        The path to the generated YAML file.
    """
    raw = load_schema_from_file(schema_path)
    schema = parse_tool_schema(raw)
    return generate_form(schema, output_dir)
