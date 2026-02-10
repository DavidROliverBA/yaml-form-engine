"""MCP tool introspection and schema parsing.

Discovers MCP tools and normalises their JSON Schema definitions into
a consistent ToolSchema structure for form generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolSchema:
    """Normalised representation of an MCP tool's schema."""

    name: str
    server: str
    description: str
    parameters: dict  # JSON Schema for input parameters
    required: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """URL-friendly name for filenames."""
        return self.name.lower().replace(" ", "-").replace("_", "-")


def parse_tool_schema(raw: dict) -> ToolSchema:
    """Parse a raw MCP tool definition into a normalised ToolSchema.

    Accepts multiple input formats:

    Format A - Full MCP tool definition:
        {"name": "API-post-page", "server": "MCP_DOCKER",
         "description": "...", "inputSchema": {"type": "object", "properties": {...}}}

    Format B - Claude Code tool definition:
        {"name": "mcp__MCP_DOCKER__API-post-page", "description": "...",
         "parameters": {"type": "object", "properties": {...}}}

    Format C - Bare JSON Schema with metadata:
        {"name": "create-page", "server": "notion",
         "description": "...", "properties": {...}, "required": [...]}

    Args:
        raw: A dict containing an MCP tool definition.

    Returns:
        A normalised ToolSchema instance.

    Raises:
        ValueError: If the schema cannot be parsed.
    """
    if not isinstance(raw, dict):
        raise ValueError("Tool schema must be a dict")

    name = raw.get("name", "")
    if not name:
        raise ValueError("Tool schema must have a 'name' field")

    # Extract server and tool name from Claude Code format
    server = raw.get("server", "")
    if not server and name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) >= 3:
            server = parts[1]
            name = parts[2]

    description = raw.get("description", "")

    # Find the parameters schema (try multiple locations)
    params = (
        raw.get("inputSchema")
        or raw.get("input_schema")
        or raw.get("parameters")
    )

    if params is None:
        # Bare schema - properties at top level
        if "properties" in raw:
            params = {
                "type": "object",
                "properties": raw["properties"],
                "required": raw.get("required", []),
            }
        else:
            params = {"type": "object", "properties": {}}

    # Normalise - ensure it's an object schema
    if params.get("type") != "object":
        params = {"type": "object", "properties": params}

    required = params.get("required", raw.get("required", []))

    return ToolSchema(
        name=name,
        server=server,
        description=description,
        parameters=params,
        required=required,
    )


def load_schema_from_file(path: str | Path) -> dict:
    """Load a tool schema from a JSON file.

    Args:
        path: Path to a JSON file containing a tool schema.

    Returns:
        The parsed JSON dict.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file isn't valid JSON.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Schema file not found: {path}")

    with open(path) as f:
        return json.load(f)
