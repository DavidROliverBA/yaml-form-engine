"""Field type to Streamlit widget mapping.

Maps YAML field definitions to Streamlit input widgets.
All rendering is local — no data leaves the browser session.
"""

import datetime
from typing import Any, Optional

import streamlit as st


def render_field(
    field: dict,
    key_prefix: str,
    current_value: Any = None,
) -> Any:
    """Render a single form field as a Streamlit widget.

    Args:
        field: Field definition from the form YAML.
        key_prefix: Unique key prefix for Streamlit widget state.
        current_value: Previously saved value (for resuming).

    Returns:
        The widget's current value.
    """
    field_type = field["type"]
    field_id = field["id"]
    label = field.get("label", field_id)
    widget_key = f"{key_prefix}_{field_id}"

    renderer = FIELD_RENDERERS.get(field_type)
    if renderer is None:
        st.warning(f"Unknown field type: {field_type}")
        return None

    return renderer(field, label, widget_key, current_value)


def _render_text(field: dict, label: str, key: str, current: Any) -> str:
    return st.text_input(
        label,
        value=current or field.get("default", ""),
        placeholder=field.get("placeholder", ""),
        key=key,
    )


def _render_textarea(field: dict, label: str, key: str, current: Any) -> str:
    return st.text_area(
        label,
        value=current or field.get("default", ""),
        placeholder=field.get("placeholder", ""),
        height=field.get("height", 100),
        key=key,
    )


def _render_select(field: dict, label: str, key: str, current: Any) -> Any:
    options = _resolve_options(field)
    values = [o["value"] if isinstance(o, dict) else o for o in options]
    labels = [o.get("label", o["value"]) if isinstance(o, dict) else str(o) for o in options]

    # Find current index
    index = 0
    if current and current in values:
        index = values.index(current)
    elif field.get("default") and field["default"] in values:
        index = values.index(field["default"])

    # Prepend empty option if not required
    if not field.get("required", False) and "" not in values:
        values = [""] + values
        labels = [""] + labels
        if current and current in values:
            index = values.index(current)
        elif not current:
            index = 0
        else:
            index += 1

    selected = st.selectbox(label, values, index=index, format_func=lambda x: labels[values.index(x)] if x in values else x, key=key)
    return selected


def _render_multiselect(field: dict, label: str, key: str, current: Any) -> list:
    options = _resolve_options(field)
    values = [o["value"] if isinstance(o, dict) else o for o in options]
    labels_map = {
        (o["value"] if isinstance(o, dict) else o): (o.get("label", o["value"]) if isinstance(o, dict) else str(o))
        for o in options
    }

    default = current or field.get("default", [])
    if isinstance(default, str):
        default = [default]

    return st.multiselect(
        label,
        values,
        default=[d for d in default if d in values],
        format_func=lambda x: labels_map.get(x, str(x)),
        key=key,
    )


def _render_number(field: dict, label: str, key: str, current: Any) -> float:
    return st.number_input(
        label,
        min_value=field.get("min"),
        max_value=field.get("max"),
        value=current if current is not None else field.get("default", 0),
        step=field.get("step", 1),
        key=key,
    )


def _render_date(field: dict, label: str, key: str, current: Any) -> datetime.date:
    default = current
    if default is None:
        default_str = field.get("default", "today")
        if default_str == "today":
            default = datetime.date.today()
        elif isinstance(default_str, str):
            try:
                default = datetime.date.fromisoformat(default_str)
            except ValueError:
                default = datetime.date.today()

    return st.date_input(label, value=default, key=key)


def _render_checkbox(field: dict, label: str, key: str, current: Any) -> bool:
    default = current if current is not None else field.get("default", False)
    disabled = field.get("locked", False)
    return st.checkbox(label, value=default, disabled=disabled, key=key)


def _render_radio(field: dict, label: str, key: str, current: Any) -> Any:
    options = _resolve_options(field)
    values = [o["value"] if isinstance(o, dict) else o for o in options]
    labels = [o.get("label", o["value"]) if isinstance(o, dict) else str(o) for o in options]

    index = 0
    if current and current in values:
        index = values.index(current)

    return st.radio(
        label,
        values,
        index=index,
        format_func=lambda x: labels[values.index(x)] if x in values else str(x),
        horizontal=field.get("horizontal", False),
        key=key,
    )


def _render_slider(field: dict, label: str, key: str, current: Any) -> Any:
    return st.slider(
        label,
        min_value=field.get("min", 0),
        max_value=field.get("max", 100),
        value=current if current is not None else field.get("default", 0),
        step=field.get("step", 1),
        key=key,
    )


def _render_file(field: dict, label: str, key: str, current: Any) -> Any:
    allowed_types = field.get("types")
    return st.file_uploader(
        label,
        type=allowed_types,
        key=key,
    )


def _render_score(field: dict, label: str, key: str, current: Any) -> Any:
    """Render a score selector (select_slider with labelled stops)."""
    scale = field.get("scale", [0, 3])
    labels_map = field.get("labels", {})

    if isinstance(scale, list) and len(scale) == 2:
        options = list(range(scale[0], scale[1] + 1))
    elif isinstance(scale, list):
        options = scale
    else:
        options = [0, 1, 2, 3]

    format_labels = {
        v: f"{v} — {labels_map[v]}" if v in labels_map else str(v)
        for v in options
    }

    default = current if current is not None else options[0]
    if default not in options:
        default = options[0]

    return st.select_slider(
        label,
        options=options,
        value=default,
        format_func=lambda x: format_labels.get(x, str(x)),
        key=key,
    )


def _resolve_options(field: dict) -> list:
    """Resolve field options from static list or data reference."""
    options = field.get("options", [])
    if isinstance(options, list):
        return options
    return []


# Registry of field type → renderer function
FIELD_RENDERERS = {
    "text": _render_text,
    "textarea": _render_textarea,
    "select": _render_select,
    "multiselect": _render_multiselect,
    "number": _render_number,
    "date": _render_date,
    "checkbox": _render_checkbox,
    "radio": _render_radio,
    "slider": _render_slider,
    "file": _render_file,
    "score": _render_score,
}
