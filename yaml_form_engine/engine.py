"""Main Streamlit form engine.

Reads a YAML form definition and renders it as an interactive wizard.
All data stays local — nothing is sent to external services.

Usage:
    streamlit run yaml_form_engine/engine.py -- --form forms/my-form.yaml
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st
import yaml

from .data_resolver import (
    DataSecurityError,
    filter_data_items,
    load_data_source,
    resolve_tier_value,
)
from .expressions import evaluate, evaluate_condition, interpolate
from .exporters import export_form
from .fields import render_field
from .mcp_invoker import build_payload, format_mcp_command
from .mcp_introspect import ToolSchema
from .schema import SchemaError, validate_form_schema


def get_form_path() -> str:
    """Extract --form argument from command line."""
    args = sys.argv[1:]
    if "--form" in args:
        idx = args.index("--form")
        if idx + 1 < len(args):
            return args[idx + 1]
    # Fall back to environment variable
    return os.environ.get("YFE_FORM_PATH", "")


def load_form_definition(form_path: str) -> dict:
    """Load and validate a form YAML file."""
    if not os.path.isfile(form_path):
        st.error(f"Form file not found: {form_path}")
        st.stop()

    with open(form_path, "r") as f:
        form_def = yaml.safe_load(f)

    try:
        validate_form_schema(form_def)
    except SchemaError as e:
        st.error(f"Form schema error: {e}")
        st.stop()

    return form_def


def save_state(form_id: str, responses: dict) -> None:
    """Auto-save form state to local file."""
    state_dir = Path(".form-state")
    state_dir.mkdir(exist_ok=True)
    state_file = state_dir / f"{form_id}.json"

    serialisable = {}
    for step_id, step_data in responses.items():
        if isinstance(step_data, dict):
            serialisable[step_id] = {}
            for k, v in step_data.items():
                if isinstance(v, dict):
                    serialisable[step_id][k] = {
                        fk: str(fv) if not isinstance(fv, (str, int, float, bool, type(None))) else fv
                        for fk, fv in v.items()
                    }
                else:
                    serialisable[step_id][k] = (
                        str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                    )
        else:
            serialisable[step_id] = str(step_data)

    with open(state_file, "w") as f:
        json.dump(serialisable, f, indent=2)


def load_saved_state(form_id: str) -> dict:
    """Load previously saved form state."""
    state_file = Path(".form-state") / f"{form_id}.json"
    if state_file.is_file():
        with open(state_file, "r") as f:
            return json.load(f)
    return {}


def flatten_data_items(data: dict, form: dict) -> list:
    """Flatten nested data (sections → items) into a flat list with metadata."""
    items = data.get("items", [])
    ds = form.get("data_source", {})
    sub_key = ds.get("items_key")  # e.g. "nfrs" for sections containing nfrs
    id_field = ds.get("id_field", "id")
    label_field = ds.get("label_field", "name")

    if not sub_key:
        # Items are already flat — add group metadata
        for item in items:
            if "_section_name" not in item:
                item["_section_name"] = item.get(label_field, "Items")
        return items

    # Nested: sections have sub-items
    flat = []
    for section in items:
        section_name = section.get(label_field, section.get(id_field, "Unknown"))
        sub_items = section.get(sub_key, [])
        for sub in sub_items:
            sub["_section_name"] = section_name
            sub["_section_id"] = section.get(id_field, "")
            # Copy section-level fields that sub-items might reference
            for key in ("applicability", "tier_guidance", "wa_pillar", "purpose"):
                if key in section and key not in sub:
                    sub[f"_section_{key}"] = section[key]
            flat.append(sub)

    return flat


def run():
    """Main engine entry point."""
    form_path = get_form_path()
    if not form_path:
        st.title("YAML Form Engine")
        st.warning(
            "No form specified. Launch with:\n\n"
            "```\nstreamlit run yaml_form_engine/engine.py -- --form forms/my-form.yaml\n```"
        )
        st.stop()

    form_path = os.path.abspath(form_path)
    form_dir = os.path.dirname(form_path)
    form_def = load_form_definition(form_path)
    form = form_def["form"]

    # Page config
    st.set_page_config(
        page_title=form["title"],
        page_icon=form.get("icon", None),
        layout="wide",
    )

    # Load external data source if specified
    data = None
    all_flat_items = []
    if "data_source" in form:
        try:
            data = load_data_source(form["data_source"], form_dir)
            all_flat_items = flatten_data_items(data, form)
        except DataSecurityError as e:
            st.error(f"Data source security error: {e}")
            st.stop()

    # Session state initialisation
    form_id = form["id"]
    if "responses" not in st.session_state:
        st.session_state.responses = load_saved_state(form_id)
    if "current_step" not in st.session_state:
        st.session_state.current_step = 0
    if "filter_values" not in st.session_state:
        st.session_state.filter_values = {}

    responses = st.session_state.responses
    steps = form["steps"]

    # ---- Sidebar ----
    st.sidebar.title(form["title"])
    if form.get("description"):
        st.sidebar.markdown(form["description"])
    if form.get("version"):
        st.sidebar.markdown(f"**Version:** {form['version']}")
    st.sidebar.markdown("---")

    # Step navigation
    step_labels = {i: f"{i + 1}. {s['title']}" for i, s in enumerate(steps)}
    selected_step = st.sidebar.radio(
        "Steps",
        range(len(steps)),
        format_func=lambda x: step_labels[x],
        index=st.session_state.current_step,
        key="_yfe_step_nav",
    )
    st.session_state.current_step = selected_step

    # ---- Filters (sidebar) ----
    filtered_items = all_flat_items
    if "filters" in form and data:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Filters")

        for filt in form["filters"]:
            filt_id = filt["id"]
            filt_type = filt["type"]

            # Resolve options
            if "options" in filt:
                options = filt["options"]
            elif "source" in filt:
                # Resolve from data: e.g. "data.classification_tiers"
                source_parts = filt["source"].split(".")
                resolved = data["raw"]
                for part in source_parts[1:] if source_parts[0] == "data" else source_parts:
                    if isinstance(resolved, dict):
                        resolved = resolved.get(part, {})
                if isinstance(resolved, dict):
                    options = [
                        {"value": k, "label": f"{k} — {v.get('name', k)}" if isinstance(v, dict) else f"{k}"}
                        for k, v in resolved.items()
                    ]
                else:
                    options = []
            else:
                options = []

            values = [o["value"] if isinstance(o, dict) else o for o in options]
            labels_map = {
                (o["value"] if isinstance(o, dict) else o): (o.get("label", o["value"]) if isinstance(o, dict) else str(o))
                for o in options
            }

            if filt_type == "select":
                current_filter = st.session_state.filter_values.get(filt_id, values[0] if values else "")
                idx = values.index(current_filter) if current_filter in values else 0
                selected = st.sidebar.selectbox(
                    filt["label"],
                    values,
                    index=idx,
                    format_func=lambda x, lm=labels_map: lm.get(x, str(x)),
                    key=f"filter_{filt_id}",
                )
                st.session_state.filter_values[filt_id] = selected

            elif filt_type == "multiselect":
                defaults = []
                for o in options:
                    if isinstance(o, dict) and o.get("default"):
                        defaults.append(o["value"])
                current_filter = st.session_state.filter_values.get(filt_id, defaults)
                selected = st.sidebar.multiselect(
                    filt["label"],
                    values,
                    default=[d for d in current_filter if d in values],
                    format_func=lambda x, lm=labels_map: lm.get(x, str(x)),
                    key=f"filter_{filt_id}",
                )
                st.session_state.filter_values[filt_id] = selected

            # Apply filter to items
            if filt.get("filters_field") and filtered_items:
                filter_vals = st.session_state.filter_values.get(filt_id, [])
                if isinstance(filter_vals, str):
                    filter_vals = [filter_vals]
                if filter_vals:
                    filtered_items = filter_data_items(
                        filtered_items,
                        filt["filters_field"],
                        filter_vals,
                    )

    # ---- Render current step ----
    step = steps[selected_step]
    step_type = step.get("type", "input")

    if step_type == "input":
        _render_input_step(step, form, responses)
    elif step_type == "data_driven":
        _render_data_driven_step(step, form, responses, filtered_items, data)
    elif step_type == "computed":
        _render_computed_step(step, form, responses, filtered_items)
    elif step_type == "export":
        _render_export_step(step, form, responses, all_flat_items, filtered_items)
    elif step_type == "info":
        _render_info_step(step, form, responses)
    elif step_type == "submit":
        _render_submit_step(step, form, responses)

    # Auto-save
    save_state(form_id, responses)

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.caption("YAML Form Engine v0.1.0")
    st.sidebar.caption("All data stays local.")


# ---- Step renderers ----

def _render_input_step(step: dict, form: dict, responses: dict) -> None:
    """Render an input step with user-fillable fields."""
    st.title(step["title"])
    if step.get("description"):
        st.markdown(step["description"])

    step_id = step["id"]
    if step_id not in responses:
        responses[step_id] = {}

    layout = step.get("layout", "single")
    fields = step.get("fields", [])

    if layout == "columns" and len(fields) >= 2:
        cols = st.columns(min(len(fields), 4))
        for i, field in enumerate(fields):
            # Check conditional
            if "show_if" in field and not evaluate_condition(field["show_if"], responses):
                continue
            with cols[i % len(cols)]:
                value = render_field(
                    field,
                    key_prefix=f"{step_id}",
                    current_value=responses[step_id].get(field["id"]),
                )
                responses[step_id][field["id"]] = value
    else:
        for field in fields:
            if "show_if" in field and not evaluate_condition(field["show_if"], responses):
                continue
            value = render_field(
                field,
                key_prefix=f"{step_id}",
                current_value=responses[step_id].get(field["id"]),
            )
            responses[step_id][field["id"]] = value


def _render_data_driven_step(
    step: dict,
    form: dict,
    responses: dict,
    filtered_items: list,
    data: dict,
) -> None:
    """Render a data-driven step that iterates over data items."""
    st.title(step["title"])
    if step.get("description"):
        st.markdown(step["description"])

    step_id = step["id"]
    if step_id not in responses:
        responses[step_id] = {}

    ds = form.get("data_source", {})
    id_field = ds.get("id_field", "id")
    label_field = ds.get("label_field", "title")
    per_item = step.get("per_item", [])
    display_fields = step.get("display_fields", [])

    # Summarise scope
    st.markdown(f"**{len(filtered_items)} items** to review")

    # Group by section
    group_by = step.get("group_by", "_section_name")
    grouped = {}
    for item in filtered_items:
        group = item.get("_section_name", item.get(group_by, "Items"))
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(item)

    for group_name, items in grouped.items():
        with st.expander(f"**{group_name}** — {len(items)} items", expanded=False):
            for item in items:
                item_id = str(item.get(id_field, "unknown"))
                item_title = item.get(label_field, item.get("title", item_id))

                st.markdown(f"#### {item_id}: {item_title}")

                # Display read-only context fields
                for df in display_fields:
                    field_path = df.get("field", "")
                    label = df.get("label", field_path)
                    style = df.get("style", "body")

                    # Resolve field path (handles tier_values.{filter.tier})
                    value = _resolve_display_field(item, field_path, form, st.session_state.filter_values)

                    if value:
                        if style == "highlight":
                            st.markdown(f"**{label}:** `{value}`")
                        elif style == "italic":
                            st.markdown(f"**{label}:** _{value}_")
                        elif style == "badge":
                            st.markdown(f"**{label}:** `{value}`")
                        else:
                            st.markdown(f"**{label}:** {value}")

                # Editable per-item fields
                if item_id not in responses[step_id]:
                    responses[step_id][item_id] = {}

                if len(per_item) > 1:
                    cols = st.columns([3] + [1] * (len(per_item) - 1))
                    for i, field in enumerate(per_item):
                        with cols[min(i, len(cols) - 1)]:
                            value = render_field(
                                field,
                                key_prefix=f"{step_id}_{item_id}",
                                current_value=responses[step_id][item_id].get(field["id"]),
                            )
                            responses[step_id][item_id][field["id"]] = value
                else:
                    for field in per_item:
                        value = render_field(
                            field,
                            key_prefix=f"{step_id}_{item_id}",
                            current_value=responses[step_id][item_id].get(field["id"]),
                        )
                        responses[step_id][item_id][field["id"]] = value

                st.markdown("---")


def _render_computed_step(
    step: dict,
    form: dict,
    responses: dict,
    filtered_items: list,
) -> None:
    """Render a computed summary step."""
    st.title(step["title"])
    if step.get("description"):
        st.markdown(step["description"])

    # Setup context
    setup_step = form.get("steps", [{}])[0]
    setup_data = responses.get(setup_step.get("id", "setup"), {})
    for key, val in setup_data.items():
        if val:
            st.markdown(f"**{key.replace('_', ' ').title()}:** {val}")
    st.markdown("---")

    # Metrics
    metrics = step.get("metrics", [])
    if metrics:
        cols = st.columns(min(len(metrics), 4))
        for i, metric in enumerate(metrics):
            with cols[i % len(cols)]:
                try:
                    value = evaluate(metric["calc"], responses, filtered_items)
                    if isinstance(value, float):
                        display = f"{value:.1f}%"  if "percent" in metric["calc"] else f"{value:.1f}"
                    else:
                        display = str(value)
                    st.metric(metric["label"], display)
                except Exception as e:
                    st.metric(metric["label"], "Error")
                    st.caption(str(e))

    # Tables
    tables = step.get("tables", [])
    for table_def in tables:
        st.subheader(table_def.get("title", "Data"))

        table_filter = table_def.get("filter")
        dd_step = _find_data_driven_step(form)
        if not dd_step:
            continue

        step_id = dd_step["id"]
        step_responses = responses.get(step_id, {})

        if table_def.get("group_by") == "section":
            _render_section_summary_table(filtered_items, step_responses, form)
        elif table_filter:
            _render_filtered_table(filtered_items, step_responses, table_filter, form)


def _render_export_step(
    step: dict,
    form: dict,
    responses: dict,
    all_items: list,
    filtered_items: list,
) -> None:
    """Render an export step with format selection and download."""
    st.title(step["title"])

    formats = step.get("formats", [])
    format_labels = [f.get("label", f["id"]) for f in formats]
    format_ids = [f["id"] for f in formats]

    selected_format = st.radio("Export Format", format_ids, format_func=lambda x: next(
        (f.get("label", f["id"]) for f in formats if f["id"] == x), x
    ), horizontal=True, key="_yfe_export_format")

    if st.button("Generate Export", type="primary"):
        output = export_form(
            {"form": form},
            responses,
            selected_format,
            data_items=all_items,
            filtered_items=filtered_items,
        )

        # Filename
        fmt_def = next((f for f in formats if f["id"] == selected_format), {})
        filename_template = fmt_def.get("filename", f"{form['id']}-export.txt")
        filename = interpolate(filename_template, responses, {"form": form})

        # MIME type
        mime_map = {
            "markdown": "text/markdown",
            "confluence": "text/plain",
            "csv": "text/csv",
            "json": "application/json",
        }
        mime = mime_map.get(selected_format, "text/plain")

        st.download_button(
            f"Download {fmt_def.get('label', selected_format)}",
            output,
            file_name=filename,
            mime=mime,
        )

        with st.expander("Preview", expanded=True):
            lang = "markdown" if selected_format == "markdown" else "json" if selected_format == "json" else None
            st.code(output, language=lang)


def _render_info_step(step: dict, form: dict, responses: dict) -> None:
    """Render a read-only info step."""
    st.title(step["title"])
    content = step.get("content", "")
    if content:
        st.markdown(interpolate(content, responses, {"form": form}))


def _render_submit_step(step: dict, form: dict, responses: dict) -> None:
    """Render a submit step that builds and displays an MCP tool invocation payload."""
    st.title(step["title"])

    mcp = step.get("mcp", {})
    server = mcp.get("server", "")
    tool = mcp.get("tool", "")

    st.markdown(f"**MCP Server:** `{server}`")
    st.markdown(f"**Tool:** `{tool}`")

    # Build a lightweight ToolSchema from form metadata
    # Collect all parameter properties from input steps
    param_properties = {}
    param_required = []
    for s in form.get("steps", []):
        if s.get("type", "input") == "input":
            for field in s.get("fields", []):
                field_id = field["id"]
                # Infer JSON Schema type from field type
                field_type = field.get("type", "text")
                schema_type = _field_type_to_schema_type(field_type)
                param_properties[field_id] = {"type": schema_type}
                if field.get("required"):
                    param_required.append(field_id)

    tool_schema = ToolSchema(
        name=tool,
        server=server,
        description="",
        parameters={
            "type": "object",
            "properties": param_properties,
            "required": param_required,
        },
        required=param_required,
    )

    payload = build_payload(responses, tool_schema)

    # Show payload preview
    if step.get("show_payload", True):
        st.subheader("Payload Preview")
        payload_json = json.dumps(payload, indent=2)
        st.code(payload_json, language="json")

    # Action buttons
    col1, col2 = st.columns(2)

    with col1:
        if step.get("confirm", True):
            if st.button("Copy Invocation", type="primary"):
                command = format_mcp_command(server, tool, payload)
                st.code(command)
                st.success("Copy the above to invoke this tool in Claude Code.")

    with col2:
        # Save payload to file
        payload_json = json.dumps(payload, indent=2)
        form_id = form.get("id", "form")
        st.download_button(
            "Download Payload (JSON)",
            payload_json,
            file_name=f"{form_id}-payload.json",
            mime="application/json",
        )

    # Also save to .form-state for programmatic access
    state_dir = Path(".form-state")
    state_dir.mkdir(exist_ok=True)
    payload_file = state_dir / f"{form.get('id', 'form')}-payload.json"
    with open(payload_file, "w") as f:
        json.dump(payload, f, indent=2)
    st.caption(f"Payload also saved to `{payload_file}`")


def _field_type_to_schema_type(field_type: str) -> str:
    """Map a YAML form field type back to a JSON Schema type."""
    mapping = {
        "text": "string",
        "textarea": "string",
        "select": "string",
        "radio": "string",
        "number": "number",
        "slider": "number",
        "date": "string",
        "checkbox": "boolean",
        "multiselect": "array",
        "file": "string",
        "score": "number",
    }
    return mapping.get(field_type, "string")


# ---- Helpers ----

def _resolve_display_field(item: dict, field_path: str, form: dict, filter_values: dict) -> str:
    """Resolve a display field path, handling tier references."""
    if "{filter." in field_path:
        # Replace {filter.tier} with actual filter value
        import re
        def replace_filter(m):
            filt_name = m.group(1)
            return str(filter_values.get(filt_name, ""))
        resolved_path = re.sub(r"\{filter\.(\w+)\}", replace_filter, field_path)
        parts = resolved_path.split(".")
    else:
        parts = field_path.split(".")

    current = item
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return ""

    if isinstance(current, dict):
        return ", ".join(f"{k}: {v}" for k, v in current.items())
    return str(current) if current is not None else ""


def _find_data_driven_step(form: dict) -> dict:
    """Find the first data_driven step."""
    for step in form.get("steps", []):
        if step.get("type") == "data_driven":
            return step
    return None


def _render_section_summary_table(items: list, step_responses: dict, form: dict) -> None:
    """Render a section-grouped summary table."""
    ds = form.get("data_source", {})
    id_field = ds.get("id_field", "id")

    grouped = {}
    for item in items:
        section = item.get("_section_name", "Unknown")
        if section not in grouped:
            grouped[section] = []
        grouped[section].append(item)

    table_data = []
    for section, section_items in grouped.items():
        total = len(section_items)
        met = partial = not_met = na = pending = 0
        gap_ids = []

        for item in section_items:
            item_id = str(item.get(id_field, ""))
            item_data = step_responses.get(item_id, {})
            status = item_data.get("status", "")

            if status == "Met":
                met += 1
            elif status == "Partial":
                partial += 1
                gap_ids.append(item_id)
            elif status == "Not Met":
                not_met += 1
                gap_ids.append(item_id)
            elif status == "N/A":
                na += 1
            else:
                pending += 1
                gap_ids.append(item_id)

        table_data.append({
            "Section": section,
            "Total": total,
            "Met": met,
            "Partial": partial,
            "Not Met": not_met,
            "N/A": na,
            "Pending": pending,
            "Gaps": ", ".join(gap_ids[:5]) + ("..." if len(gap_ids) > 5 else "") if gap_ids else "None",
        })

    st.table(table_data)


def _render_filtered_table(items: list, step_responses: dict, filter_expr: str, form: dict) -> None:
    """Render a table of items matching a filter expression."""
    ds = form.get("data_source", {})
    id_field = ds.get("id_field", "id")
    label_field = ds.get("label_field", "title")

    rows = []
    for item in items:
        item_id = str(item.get(id_field, ""))
        item_data = step_responses.get(item_id, {})
        status = item_data.get("status", "")

        # Simple filter matching
        include = False
        if "in [" in filter_expr:
            field_part = filter_expr.split(" in ")[0].strip()
            values_part = filter_expr.split("[")[1].split("]")[0]
            target_values = [v.strip().strip("'\"") for v in values_part.split(",")]
            if "." in field_part:
                _, field_name = field_part.rsplit(".", 1)
                actual = item_data.get(field_name, "")
            else:
                actual = status
            include = actual in target_values or (actual == "" and "" in target_values)

        if include:
            rows.append({
                "ID": item_id,
                "Section": item.get("_section_name", ""),
                "Title": item.get(label_field, item.get("title", item_id)),
                "Status": status if status else "Not Started",
            })

    if rows:
        st.table(rows)
    else:
        st.success("No outstanding items.")


# Entry point when running engine.py directly (not via _app.py)
if __name__ == "__main__":
    run()
