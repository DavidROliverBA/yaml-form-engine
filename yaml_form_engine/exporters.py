"""Export engine for form responses.

Generates output in multiple formats from collected form data.
All output stays local — written to filesystem or downloaded via browser.
"""

import csv
import io
import json
import datetime
from typing import Any, Optional


def export_form(
    form_def: dict,
    responses: dict,
    format_id: str,
    data_items: Optional[list] = None,
    filtered_items: Optional[list] = None,
) -> str:
    """Export form responses in the specified format.

    Args:
        form_def: The full form definition.
        responses: All collected responses {step_id: {field_id: value}}.
        format_id: Export format identifier (markdown, confluence, csv, json).
        data_items: All data items from data source (if any).
        filtered_items: Filtered data items based on active filters.

    Returns:
        Formatted string output.
    """
    form = form_def.get("form", form_def)

    exporters = {
        "markdown": _export_markdown,
        "confluence": _export_confluence,
        "csv": _export_csv,
        "json": _export_json,
    }

    exporter = exporters.get(format_id)
    if not exporter:
        return f"Unknown export format: {format_id}"

    return exporter(form, responses, data_items, filtered_items)


def _export_markdown(
    form: dict,
    responses: dict,
    data_items: Optional[list],
    filtered_items: Optional[list],
) -> str:
    """Export as markdown tables."""
    lines = []
    lines.append(f"# {form['title']}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.date.today().isoformat()}")

    # Add setup step values
    for step in form.get("steps", []):
        if step.get("type", "input") == "input":
            for field in step.get("fields", []):
                fid = field["id"]
                val = responses.get(step["id"], {}).get(fid, "")
                if val:
                    label = field.get("label", fid)
                    lines.append(f"**{label}:** {val}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Data-driven sections
    if filtered_items:
        grouped = _group_items(filtered_items, form)

        for group_label, items in grouped.items():
            lines.append(f"## {group_label}")
            lines.append("")

            # Find the data_driven step to get per_item fields
            dd_step = _find_step_by_type(form, "data_driven")
            if dd_step:
                per_item = dd_step.get("per_item", [])
                # Table header
                header_fields = ["ID", "Title"] + [f.get("label", f["id"]) for f in per_item]
                lines.append("| " + " | ".join(header_fields) + " |")
                lines.append("| " + " | ".join(["---"] * len(header_fields)) + " |")

                # Table rows
                step_id = dd_step["id"]
                for item in items:
                    item_id = item.get(
                        form.get("data_source", {}).get("id_field", "id"),
                        "?"
                    )
                    item_label = item.get(
                        form.get("data_source", {}).get("label_field", "title"),
                        item_id
                    )
                    row = [str(item_id), str(item_label)]

                    item_responses = responses.get(step_id, {}).get(str(item_id), {})
                    for f in per_item:
                        val = item_responses.get(f["id"], "")
                        row.append(str(val) if val else "")

                    lines.append("| " + " | ".join(row) + " |")

                lines.append("")
    else:
        # Non-data-driven: export input step responses
        for step in form.get("steps", []):
            if step.get("type", "input") == "input" and step["id"] != form.get("steps", [{}])[0].get("id"):
                lines.append(f"## {step['title']}")
                lines.append("")
                step_responses = responses.get(step["id"], {})
                for field in step.get("fields", []):
                    val = step_responses.get(field["id"], "")
                    lines.append(f"- **{field.get('label', field['id'])}:** {val}")
                lines.append("")

    return "\n".join(lines)


def _export_confluence(
    form: dict,
    responses: dict,
    data_items: Optional[list],
    filtered_items: Optional[list],
) -> str:
    """Export as Confluence wiki markup."""
    lines = []
    lines.append(f"h1. {form['title']}")
    lines.append("")
    lines.append(f"*Generated:* {datetime.date.today().isoformat()}")
    lines.append("")

    # Setup values
    for step in form.get("steps", []):
        if step.get("type", "input") == "input":
            for field in step.get("fields", []):
                fid = field["id"]
                val = responses.get(step["id"], {}).get(fid, "")
                if val:
                    label = field.get("label", fid)
                    lines.append(f"*{label}:* {val}")

    lines.append("")
    lines.append("----")
    lines.append("")

    if filtered_items:
        grouped = _group_items(filtered_items, form)
        dd_step = _find_step_by_type(form, "data_driven")

        for group_label, items in grouped.items():
            lines.append(f"h2. {group_label}")
            lines.append("")

            if dd_step:
                per_item = dd_step.get("per_item", [])
                header_fields = ["ID", "Title"] + [f.get("label", f["id"]) for f in per_item]
                lines.append("|| " + " || ".join(header_fields) + " ||")

                step_id = dd_step["id"]
                for item in items:
                    item_id = item.get(
                        form.get("data_source", {}).get("id_field", "id"), "?"
                    )
                    item_label = item.get(
                        form.get("data_source", {}).get("label_field", "title"),
                        item_id
                    )
                    row = [str(item_id), str(item_label)]

                    item_responses = responses.get(step_id, {}).get(str(item_id), {})
                    for f in per_item:
                        val = item_responses.get(f["id"], "")
                        row.append(str(val) if val else " ")

                    lines.append("| " + " | ".join(row) + " |")

            lines.append("")

    return "\n".join(lines)


def _export_csv(
    form: dict,
    responses: dict,
    data_items: Optional[list],
    filtered_items: Optional[list],
) -> str:
    """Export as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    dd_step = _find_step_by_type(form, "data_driven")

    if filtered_items and dd_step:
        per_item = dd_step.get("per_item", [])
        id_field = form.get("data_source", {}).get("id_field", "id")
        label_field = form.get("data_source", {}).get("label_field", "title")

        # Header
        headers = ["ID", "Title", "Section"] + [f.get("label", f["id"]) for f in per_item]
        writer.writerow(headers)

        # Rows
        step_id = dd_step["id"]
        grouped = _group_items(filtered_items, form)
        for group_label, items in grouped.items():
            for item in items:
                item_id = item.get(id_field, "?")
                item_label = item.get(label_field, item_id)
                row = [str(item_id), str(item_label), group_label]

                item_responses = responses.get(step_id, {}).get(str(item_id), {})
                for f in per_item:
                    val = item_responses.get(f["id"], "")
                    row.append(str(val) if val else "")

                writer.writerow(row)
    else:
        # Flat export of all input steps
        writer.writerow(["Step", "Field", "Value"])
        for step in form.get("steps", []):
            if step.get("type", "input") == "input":
                step_responses = responses.get(step["id"], {})
                for field in step.get("fields", []):
                    val = step_responses.get(field["id"], "")
                    writer.writerow([step["title"], field.get("label", field["id"]), val])

    return output.getvalue()


def _export_json(
    form: dict,
    responses: dict,
    data_items: Optional[list],
    filtered_items: Optional[list],
) -> str:
    """Export as JSON."""
    export_data = {
        "form_id": form.get("id", "unknown"),
        "form_title": form.get("title", "Unknown"),
        "generated": datetime.date.today().isoformat(),
        "responses": _serialise_responses(responses),
    }
    return json.dumps(export_data, indent=2, default=str)


def _serialise_responses(responses: dict) -> dict:
    """Make responses JSON-serialisable."""
    result = {}
    for step_id, step_data in responses.items():
        if isinstance(step_data, dict):
            result[step_id] = {}
            for key, value in step_data.items():
                if isinstance(value, dict):
                    result[step_id][key] = {
                        k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                        for k, v in value.items()
                    }
                else:
                    result[step_id][key] = (
                        str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
                    )
        else:
            result[step_id] = str(step_data) if not isinstance(step_data, (str, int, float, bool, type(None))) else step_data
    return result


def _find_step_by_type(form: dict, step_type: str) -> Optional[dict]:
    """Find the first step of a given type."""
    for step in form.get("steps", []):
        if step.get("type") == step_type:
            return step
    return None


def _group_items(items: list, form: dict) -> dict:
    """Group data items by section/parent for display.

    If the data source has nested items (sections with sub-items),
    groups by parent. Otherwise returns all items in a single group.
    """
    ds = form.get("data_source", {})
    key = ds.get("key", "items")
    id_field = ds.get("id_field", "id")
    label_field = ds.get("label_field", "name")

    # Check if items have a 'section' or parent grouping
    # This handles the common pattern of sections containing nfrs/criteria
    grouped = {}
    for item in items:
        section = item.get("_section_name", item.get("_group", "Items"))
        if section not in grouped:
            grouped[section] = []
        grouped[section].append(item)

    if len(grouped) <= 1 and "Items" in grouped:
        return {"All Items": items}

    return grouped
