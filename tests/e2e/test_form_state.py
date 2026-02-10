"""Tests for form state persistence and payload file generation.

Verifies that .form-state/ files are created correctly.
"""

import json
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_DIR / ".form-state"


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestNotionFormState:
    """State persistence tests using the notion-search form."""

    form_path = "mcp/notion-search.yaml"

    def test_state_file_created(self, form_page):
        """State file is created after interacting with a field."""
        form_page.fill_text("Search Query", "test query")
        # Give Streamlit time to auto-save state
        form_page.page.wait_for_timeout(1000)

        state_file = STATE_DIR / "mcp-notion-search.json"
        assert state_file.exists(), f"Expected state file at {state_file}"

        data = json.loads(state_file.read_text())
        assert "parameters" in data
        assert data["parameters"]["query"] == "test query"

    def test_state_restored_on_reload(self, form_page):
        """Values persist after a page reload."""
        form_page.fill_text("Search Query", "persistent value")
        form_page.page.wait_for_timeout(1000)

        # Reload
        form_page.page.reload()
        form_page.page.wait_for_selector('[data-testid="stSidebar"]', timeout=15000)
        form_page._wait()

        value = form_page.get_text_value("Search Query")
        assert value == "persistent value"

    def test_payload_file_written(self, form_page):
        """Payload JSON file is created when navigating to Submit step."""
        form_page.fill_text("Search Query", "payload test")
        form_page.navigate_to_step("Submit")
        form_page.page.wait_for_timeout(1000)

        payload_file = STATE_DIR / "mcp-notion-search-payload.json"
        assert payload_file.exists(), f"Expected payload file at {payload_file}"

        payload = json.loads(payload_file.read_text())
        assert payload["query"] == "payload test"


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestJiraFormState:
    """State persistence tests using the jira-create-issue form."""

    form_path = "mcp/jira-create-issue.yaml"

    def test_payload_excludes_empty(self, form_page):
        """Payload omits fields left empty (optional fields)."""
        form_page.fill_text("Project Key", "PROJ")
        form_page.select_option("Issue Type", "Task")
        form_page.fill_text("Summary", "Minimal issue")
        # Leave Description, Priority, Assignee, Labels empty

        form_page.navigate_to_step("Submit")
        form_page.page.wait_for_timeout(1000)

        payload_file = STATE_DIR / "mcp-jira-create-issue-payload.json"
        assert payload_file.exists()

        payload = json.loads(payload_file.read_text())
        assert payload["projectKey"] == "PROJ"
        assert payload["summary"] == "Minimal issue"
        # Optional fields should not appear if empty
        assert "assignee" not in payload
