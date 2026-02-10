"""Tests for sidebar step navigation.

Uses the notion-search form (3 steps: Search Parameters, Review, Submit).
"""

import pytest


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestStepNavigation:
    form_path = "mcp/notion-search.yaml"

    def test_form_loads_with_title(self, form_page):
        """Page loads and sidebar shows the form title."""
        assert form_page.get_sidebar_title() == "Search Notion"
        assert form_page.get_step_title() == "Search Parameters"

    def test_all_step_labels_visible(self, form_page):
        """All three step labels appear in the sidebar."""
        labels = form_page.get_step_labels()
        assert "Search Parameters" in labels
        assert "Review" in labels
        assert "Submit" in labels

    def test_sidebar_step_navigation(self, form_page):
        """Clicking each step label renders the correct content."""
        form_page.navigate_to_step("Review")
        assert form_page.get_step_title() == "Review"

        form_page.navigate_to_step("Submit")
        assert form_page.get_step_title() == "Submit"

        form_page.navigate_to_step("Search Parameters")
        assert form_page.get_step_title() == "Search Parameters"
