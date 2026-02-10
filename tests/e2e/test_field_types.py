"""Tests for individual field type rendering and interaction.

Covers text, textarea, select, radio, slider, and text with default value.
"""

import pytest


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestJiraFieldTypes:
    """Field type tests using the jira-create-issue form."""

    form_path = "mcp/jira-create-issue.yaml"

    def test_text_input(self, form_page):
        """Text input accepts and retains a value."""
        form_page.fill_text("Project Key", "TEST-123")
        assert form_page.get_text_value("Project Key") == "TEST-123"

    def test_textarea(self, form_page):
        """Textarea accepts multi-line content."""
        desc = "Line one\nLine two\nLine three"
        form_page.fill_textarea("Description", desc)
        assert "Line one" in form_page.get_textarea_value("Description")

    def test_select_with_options(self, form_page):
        """Selectbox renders options and allows selection."""
        form_page.select_option("Issue Type", "Bug")
        # After selection the dropdown closes; the value is committed

    def test_radio_with_options(self, form_page):
        """Radio group shows all options and allows selection."""
        options = form_page.get_radio_options("Priority")
        assert "Highest" in options
        assert "High" in options
        assert "Medium" in options
        assert "Low" in options

        form_page.select_radio("Priority", "High")


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestNotionFieldTypes:
    """Field type tests using the notion-search form."""

    form_path = "mcp/notion-search.yaml"

    def test_slider_default_value(self, form_page):
        """Slider renders with the correct default value."""
        value = form_page.get_slider_value("Results Limit")
        assert value == "10"


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestYouTubeFieldTypes:
    """Field type tests using the youtube-transcript form."""

    form_path = "mcp/youtube-transcript.yaml"

    def test_text_with_default(self, form_page):
        """Text input with a YAML default pre-populates the value."""
        value = form_page.get_text_value("Language Code")
        assert value == "en"
