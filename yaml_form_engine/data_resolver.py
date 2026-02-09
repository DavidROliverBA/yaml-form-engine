"""Data source loading with security constraints.

SECURITY MODEL:
- Only yaml.safe_load — no arbitrary object instantiation
- Path traversal prevention — no '..' components
- Allowed extensions whitelist — .yaml, .yml, .json only
- Base directory confinement — data sources resolve relative to form file
- No network access — local filesystem only
- No eval/exec — data is treated as pure data, never code
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml


class DataSecurityError(Exception):
    """Raised when a data source path violates security constraints."""
    pass


def validate_path(path: str, base_dir: str) -> str:
    """Validate and resolve a data source path securely.

    Args:
        path: Relative or absolute path from the form definition.
        base_dir: Base directory (where the form YAML lives).

    Returns:
        Resolved absolute path.

    Raises:
        DataSecurityError: If the path violates security constraints.
    """
    # Reject path traversal
    if ".." in path.split(os.sep):
        raise DataSecurityError(
            f"Path traversal not allowed: '{path}'. "
            "Data sources must not contain '..' components."
        )

    # Resolve relative to base directory
    if not os.path.isabs(path):
        resolved = os.path.realpath(os.path.join(base_dir, path))
    else:
        resolved = os.path.realpath(path)

    # Verify resolved path doesn't escape base via symlinks
    base_real = os.path.realpath(base_dir)
    if not resolved.startswith(base_real):
        raise DataSecurityError(
            f"Data source resolves outside form directory: '{resolved}'. "
            f"Must be within: '{base_real}'"
        )

    # Whitelist extensions
    allowed_extensions = {".yaml", ".yml", ".json"}
    _, ext = os.path.splitext(resolved)
    if ext.lower() not in allowed_extensions:
        raise DataSecurityError(
            f"Data source must be a YAML or JSON file, got: '{ext}'. "
            f"Allowed: {allowed_extensions}"
        )

    # Must exist
    if not os.path.isfile(resolved):
        raise DataSecurityError(f"Data source not found: '{resolved}'")

    return resolved


def load_data_source(ds_config: dict, base_dir: str) -> dict:
    """Load an external data source securely.

    Args:
        ds_config: The data_source config from the form definition.
        base_dir: Directory containing the form YAML.

    Returns:
        Dict with 'raw' (full parsed data) and 'items' (the iterable
        collection extracted by the 'key' field).
    """
    path = ds_config["path"]
    key = ds_config["key"]

    resolved_path = validate_path(path, base_dir)

    # Load using safe loaders only
    _, ext = os.path.splitext(resolved_path)
    if ext.lower() in (".yaml", ".yml"):
        with open(resolved_path, "r") as f:
            raw_data = yaml.safe_load(f)
    elif ext.lower() == ".json":
        with open(resolved_path, "r") as f:
            raw_data = json.load(f)
    else:
        raise DataSecurityError(f"Unsupported file type: {ext}")

    if not isinstance(raw_data, dict):
        raise DataSecurityError("Data source root must be a YAML/JSON mapping")

    # Extract the iterable collection using dot-notation key
    items = _resolve_key(raw_data, key)
    if items is None:
        raise DataSecurityError(f"Key '{key}' not found in data source")
    if not isinstance(items, list):
        raise DataSecurityError(f"Key '{key}' must resolve to a list, got {type(items).__name__}")

    return {
        "raw": raw_data,
        "items": items,
        "config": ds_config,
    }


def _resolve_key(data: dict, key: str) -> Any:
    """Resolve a dot-notation key path in a dict.

    Args:
        data: Source dict.
        key: Dot-separated path, e.g. 'sections' or 'data.items'.

    Returns:
        The resolved value, or None if not found.
    """
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def filter_data_items(
    items: list[dict],
    filter_field: str,
    filter_values: list[str],
) -> list[dict]:
    """Filter data items by a field matching any of the given values.

    Args:
        items: List of data item dicts.
        filter_field: Field name to check (e.g. 'applicability').
        filter_values: Values that qualify an item for inclusion.

    Returns:
        Filtered list of items where the field intersects with filter_values.
    """
    result = []
    for item in items:
        item_values = item.get(filter_field, [])
        if isinstance(item_values, str):
            item_values = [item_values]
        if any(v in filter_values for v in item_values):
            result.append(item)
    return result


def resolve_tier_value(item: dict, tier_key: str, tier_value: str) -> Optional[Any]:
    """Resolve a tier-specific value from a data item.

    Args:
        item: Data item dict (e.g. an NFR).
        tier_key: The key containing tier mappings (e.g. 'tier_values').
        tier_value: The specific tier to look up (e.g. 'SL2').

    Returns:
        The tier-specific value, or None if not tiered/not found.
    """
    tier_data = item.get(tier_key, {})
    if not isinstance(tier_data, dict):
        return None
    return tier_data.get(tier_value)
