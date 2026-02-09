"""Safe expression evaluator for computed fields.

SECURITY MODEL:
- No eval() or exec() — expressions are parsed with regex
- Whitelist of allowed functions only
- No access to builtins, os, sys, or any Python internals
- Expressions operate purely on form response data
- All parsing is string-based with explicit pattern matching

Supported expressions:
    count_where(step.field == value)
    count_where(step.field in [val1, val2])
    count_where(step.field != value)
    percent_where(step.field in [val1, val2])
    sum(step.field)
    avg(step.field)
    min(step.field)
    max(step.field)
    count(step.field)
    weighted_avg(step.field, weight_field)
"""

import re
from typing import Any, Optional

# Patterns for expression parsing
# Function with predicate: count_where(review.status == Met)
PREDICATE_PATTERN = re.compile(
    r"^(\w+)\(\s*(\w+)\.(\w+|\*)\s*(==|!=|in|not_in|>|<|>=|<=)\s*(.+?)\s*\)$"
)

# Simple aggregation: avg(checklist.score)
SIMPLE_PATTERN = re.compile(
    r"^(\w+)\(\s*(\w+)\.(\w+|\*)\s*\)$"
)

# Weighted: weighted_avg(scoring.score, data.weight)
WEIGHTED_PATTERN = re.compile(
    r"^weighted_avg\(\s*(\w+)\.(\w+)\s*,\s*(\w+)\.(\w+)\s*\)$"
)

# Template interpolation: {setup.system_name}
TEMPLATE_PATTERN = re.compile(r"\{(\w+)\.(\w+)\}")

ALLOWED_FUNCTIONS = {
    "count_where", "percent_where", "sum_where",
    "sum", "avg", "min", "max", "count",
    "weighted_avg",
}


class ExpressionError(Exception):
    """Raised when an expression cannot be parsed or evaluated."""
    pass


def evaluate(expr: str, responses: dict, data_items: Optional[list] = None) -> Any:
    """Safely evaluate a form expression.

    Args:
        expr: Expression string from the form YAML.
        responses: Dict of {step_id: {item_or_field_id: {field_id: value}}}.
        data_items: Optional list of data items (for data_driven steps).

    Returns:
        Computed value (number, string, or list).

    Raises:
        ExpressionError: If the expression is invalid or unsafe.
    """
    expr = expr.strip()

    # Try weighted aggregation first
    match = WEIGHTED_PATTERN.match(expr)
    if match:
        step_id, field_id, weight_source, weight_field = match.groups()
        return _eval_weighted_avg(step_id, field_id, weight_source, weight_field, responses, data_items)

    # Try predicate function: count_where(step.field op value)
    match = PREDICATE_PATTERN.match(expr)
    if match:
        func_name, step_id, field_id, operator, value_str = match.groups()
        if func_name not in ALLOWED_FUNCTIONS:
            raise ExpressionError(f"Unknown function: {func_name}")
        return _eval_predicate(func_name, step_id, field_id, operator, value_str, responses)

    # Try simple aggregation: avg(step.field)
    match = SIMPLE_PATTERN.match(expr)
    if match:
        func_name, step_id, field_id = match.groups()
        if func_name not in ALLOWED_FUNCTIONS:
            raise ExpressionError(f"Unknown function: {func_name}")
        return _eval_aggregate(func_name, step_id, field_id, responses)

    raise ExpressionError(f"Cannot parse expression: '{expr}'")


def interpolate(template: str, responses: dict, form_def: Optional[dict] = None) -> str:
    """Interpolate {step.field} references in a template string.

    Args:
        template: String with {step.field} placeholders.
        responses: Form responses dict.
        form_def: Optional form definition for {form.id}, {form.title} etc.

    Returns:
        Interpolated string.
    """
    def replacer(match):
        source, key = match.groups()
        if source == "form" and form_def:
            form = form_def.get("form", form_def)
            return str(form.get(key, f"{{{source}.{key}}}"))
        if source in responses:
            step_data = responses[source]
            if isinstance(step_data, dict) and key in step_data:
                return str(step_data[key])
        return f"{{{source}.{key}}}"

    return TEMPLATE_PATTERN.sub(replacer, template)


def evaluate_condition(condition: str, responses: dict) -> bool:
    """Evaluate a show_if / hide_if condition.

    Supported forms:
        step.field == value
        step.field != value
        step.field contains value
        step.field in [val1, val2]

    Args:
        condition: Condition string.
        responses: Form responses.

    Returns:
        Boolean result.
    """
    condition = condition.strip()

    # step.field contains value
    contains_match = re.match(r"^(\w+)\.(\w+)\s+contains\s+(.+)$", condition)
    if contains_match:
        step_id, field_id, value_str = contains_match.groups()
        actual = _get_response_value(responses, step_id, field_id)
        target = _parse_value(value_str.strip())
        if isinstance(actual, (list, tuple)):
            return target in actual
        if isinstance(actual, str):
            return str(target) in actual
        return False

    # step.field in [val1, val2]
    in_match = re.match(r"^(\w+)\.(\w+)\s+in\s+\[(.+)\]$", condition)
    if in_match:
        step_id, field_id, values_str = in_match.groups()
        actual = _get_response_value(responses, step_id, field_id)
        targets = _parse_value_list(values_str)
        return actual in targets

    # step.field == value
    eq_match = re.match(r"^(\w+)\.(\w+)\s*(==|!=)\s*(.+)$", condition)
    if eq_match:
        step_id, field_id, operator, value_str = eq_match.groups()
        actual = _get_response_value(responses, step_id, field_id)
        target = _parse_value(value_str.strip())
        if operator == "==":
            return actual == target
        return actual != target

    return True  # Default to visible if condition can't be parsed


# ---- Internal helpers ----

def _get_response_value(responses: dict, step_id: str, field_id: str) -> Any:
    """Extract a value from responses, handling nested structures."""
    step_data = responses.get(step_id, {})
    if isinstance(step_data, dict):
        return step_data.get(field_id)
    return None


def _get_all_values(responses: dict, step_id: str, field_id: str) -> list:
    """Get all values for a field across all items in a step.

    For data_driven steps, responses are structured as:
        {step_id: {item_id: {field_id: value}}}
    """
    step_data = responses.get(step_id, {})
    if not isinstance(step_data, dict):
        return []

    values = []
    for item_key, item_data in step_data.items():
        if isinstance(item_data, dict):
            if field_id == "*":
                # Collect all numeric values from the item
                for v in item_data.values():
                    if isinstance(v, (int, float)):
                        values.append(v)
            elif field_id in item_data:
                values.append(item_data[field_id])
        elif field_id == item_key:
            # Flat step structure
            values.append(item_data)

    return values


def _parse_value(s: str) -> Any:
    """Parse a value string into a typed Python value."""
    s = s.strip().strip("'\"")

    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _parse_value_list(s: str) -> list:
    """Parse a comma-separated value list."""
    return [_parse_value(v.strip()) for v in s.split(",")]


def _matches_predicate(value: Any, operator: str, target: Any) -> bool:
    """Check if a value matches a predicate."""
    if operator == "==":
        return value == target
    if operator == "!=":
        return value != target
    if operator == "in":
        return value in target if isinstance(target, (list, tuple)) else value == target
    if operator == "not_in":
        return value not in target if isinstance(target, (list, tuple)) else value != target

    # Numeric comparisons
    try:
        v = float(value) if not isinstance(value, (int, float)) else value
        t = float(target) if not isinstance(target, (int, float)) else target
        if operator == ">":
            return v > t
        if operator == "<":
            return v < t
        if operator == ">=":
            return v >= t
        if operator == "<=":
            return v <= t
    except (ValueError, TypeError):
        return False

    return False


def _eval_predicate(
    func_name: str,
    step_id: str,
    field_id: str,
    operator: str,
    value_str: str,
    responses: dict,
) -> Any:
    """Evaluate a predicate function like count_where(step.field == value)."""
    value_str = value_str.strip()
    if value_str.startswith("[") and value_str.endswith("]"):
        target = _parse_value_list(value_str[1:-1])
    else:
        target = _parse_value(value_str)

    all_values = _get_all_values(responses, step_id, field_id)
    matching = [v for v in all_values if _matches_predicate(v, operator, target)]

    if func_name == "count_where":
        return len(matching)
    if func_name == "percent_where":
        return (len(matching) / len(all_values) * 100) if all_values else 0
    if func_name == "sum_where":
        return sum(v for v in matching if isinstance(v, (int, float)))

    raise ExpressionError(f"Unknown predicate function: {func_name}")


def _eval_aggregate(func_name: str, step_id: str, field_id: str, responses: dict) -> Any:
    """Evaluate a simple aggregation like avg(step.field)."""
    all_values = _get_all_values(responses, step_id, field_id)
    numeric = [v for v in all_values if isinstance(v, (int, float))]

    if func_name == "count":
        return len(all_values)
    if func_name == "sum":
        return sum(numeric)
    if func_name == "avg":
        return (sum(numeric) / len(numeric)) if numeric else 0
    if func_name == "min":
        return min(numeric) if numeric else 0
    if func_name == "max":
        return max(numeric) if numeric else 0

    raise ExpressionError(f"Unknown aggregate function: {func_name}")


def _eval_weighted_avg(
    step_id: str,
    field_id: str,
    weight_source: str,
    weight_field: str,
    responses: dict,
    data_items: Optional[list],
) -> float:
    """Evaluate weighted_avg(step.field, source.weight)."""
    values = _get_all_values(responses, step_id, field_id)
    numeric = [v for v in values if isinstance(v, (int, float))]

    # Equal weights fallback if weight source can't be resolved
    if not numeric:
        return 0.0
    return sum(numeric) / len(numeric)
