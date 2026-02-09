"""Tests for the safe expression evaluator."""

import pytest
from yaml_form_engine.expressions import (
    ExpressionError,
    evaluate,
    evaluate_condition,
    interpolate,
)


SAMPLE_RESPONSES = {
    "review": {
        "item1": {"status": "Met", "score": 3},
        "item2": {"status": "Partial", "score": 2},
        "item3": {"status": "Not Met", "score": 0},
        "item4": {"status": "Met", "score": 3},
        "item5": {"status": "N/A", "score": 0},
    },
    "setup": {
        "system_name": "Test System",
        "tier": "CS2",
    },
}


class TestCountWhere:
    def test_count_equals(self):
        result = evaluate("count_where(review.status == Met)", SAMPLE_RESPONSES)
        assert result == 2

    def test_count_not_equals(self):
        result = evaluate("count_where(review.status != Met)", SAMPLE_RESPONSES)
        assert result == 3

    def test_count_in_list(self):
        result = evaluate("count_where(review.status in [Met, Partial])", SAMPLE_RESPONSES)
        assert result == 3


class TestPercentWhere:
    def test_percent(self):
        result = evaluate("percent_where(review.status in [Met, Partial, N/A])", SAMPLE_RESPONSES)
        assert result == 80.0  # 4 of 5


class TestAggregates:
    def test_avg(self):
        result = evaluate("avg(review.score)", SAMPLE_RESPONSES)
        assert result == 1.6  # (3+2+0+3+0) / 5

    def test_sum(self):
        result = evaluate("sum(review.score)", SAMPLE_RESPONSES)
        assert result == 8

    def test_min(self):
        result = evaluate("min(review.score)", SAMPLE_RESPONSES)
        assert result == 0

    def test_max(self):
        result = evaluate("max(review.score)", SAMPLE_RESPONSES)
        assert result == 3

    def test_count(self):
        result = evaluate("count(review.score)", SAMPLE_RESPONSES)
        assert result == 5


class TestInterpolate:
    def test_step_field(self):
        result = interpolate("{setup.system_name} report", SAMPLE_RESPONSES)
        assert result == "Test System report"

    def test_form_field(self):
        result = interpolate("{form.id}-export", SAMPLE_RESPONSES, {"form": {"id": "test"}})
        assert result == "test-export"

    def test_missing_field(self):
        result = interpolate("{setup.missing}", SAMPLE_RESPONSES)
        assert result == "{setup.missing}"


class TestConditions:
    def test_equals(self):
        assert evaluate_condition("setup.tier == CS2", SAMPLE_RESPONSES) is True
        assert evaluate_condition("setup.tier == CS1", SAMPLE_RESPONSES) is False

    def test_not_equals(self):
        assert evaluate_condition("setup.tier != CS1", SAMPLE_RESPONSES) is True

    def test_contains(self):
        responses = {"setup": {"types": ["all", "pci"]}}
        assert evaluate_condition("setup.types contains pci", responses) is True
        assert evaluate_condition("setup.types contains gdpr", responses) is False

    def test_in_list(self):
        assert evaluate_condition("setup.tier in [CS1, CS2, CS3]", SAMPLE_RESPONSES) is True
        assert evaluate_condition("setup.tier in [CS3, CS4]", SAMPLE_RESPONSES) is False


class TestSafety:
    def test_unknown_function_rejected(self):
        with pytest.raises(ExpressionError, match="Unknown function"):
            evaluate("dangerous(review.status)", SAMPLE_RESPONSES)

    def test_unparseable_expression(self):
        with pytest.raises(ExpressionError, match="Cannot parse"):
            evaluate("this is not a valid expression at all", SAMPLE_RESPONSES)

    def test_nested_expression_rejected(self):
        with pytest.raises(ExpressionError, match="Cannot parse"):
            evaluate("count_where(count_where(review.status == Met) > 0)", SAMPLE_RESPONSES)

    def test_empty_responses(self):
        result = evaluate("count_where(review.status == Met)", {})
        assert result == 0

    def test_avg_empty(self):
        result = evaluate("avg(review.score)", {})
        assert result == 0
