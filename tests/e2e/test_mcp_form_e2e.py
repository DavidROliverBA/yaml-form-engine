"""End-to-end tests for complete MCP form flows.

Each test fills a form from start to finish and verifies the payload.
"""

import pytest


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestNotionSearchFlow:
    """Full flow through the notion-search form."""

    form_path = "mcp/notion-search.yaml"

    def test_full_flow(self, form_page):
        """Fill search params, navigate to submit, verify payload JSON."""
        # Step 1: Fill input fields
        form_page.fill_text("Search Query", "architecture decisions")
        form_page.select_radio("Filter by Type", "Pages")

        # Step 3: Navigate to Submit
        form_page.navigate_to_step("Submit")
        assert form_page.get_step_title() == "Submit"

        # Verify payload
        payload = form_page.get_payload_json()
        assert payload["query"] == "architecture decisions"
        assert payload["filter_object_type"] == "page"

    def test_info_step_renders_content(self, form_page):
        """Review step renders markdown with tool info."""
        form_page.navigate_to_step("Review")
        text = form_page.get_markdown_text()
        assert "API-post-search" in text

    def test_submit_step_shows_metadata(self, form_page):
        """Submit step displays MCP server and tool names."""
        form_page.navigate_to_step("Submit")
        text = form_page.get_markdown_text()
        assert "MCP_DOCKER" in text
        assert "API-post-search" in text


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestJiraCreateIssueFlow:
    """Full flow through the jira-create-issue form."""

    form_path = "mcp/jira-create-issue.yaml"

    def test_full_flow(self, form_page):
        """Fill all fields, navigate to submit, verify payload."""
        form_page.fill_text("Project Key", "ARCH")
        form_page.select_option("Issue Type", "Task")
        form_page.fill_text("Summary", "Review ADR for data platform")
        form_page.fill_textarea("Description", "Detailed review needed.")
        form_page.select_radio("Priority", "Medium")

        form_page.navigate_to_step("Submit")
        payload = form_page.get_payload_json()
        assert payload["projectKey"] == "ARCH"
        assert payload["issueType"] == "Task"
        assert payload["summary"] == "Review ADR for data platform"
        assert payload["description"] == "Detailed review needed."
        assert payload["priority"] == "Medium"


@pytest.mark.e2e
@pytest.mark.usefixtures("streamlit_server")
class TestYouTubeTranscriptFlow:
    """Full flow through the youtube-transcript form."""

    form_path = "mcp/youtube-transcript.yaml"

    def test_full_flow(self, form_page):
        """Fill URL and language, verify payload."""
        form_page.fill_text("YouTube Video URL", "https://www.youtube.com/watch?v=abc123")
        # Language should already be "en" by default

        form_page.navigate_to_step("Submit")
        payload = form_page.get_payload_json()
        assert payload["url"] == "https://www.youtube.com/watch?v=abc123"
        assert payload["lang"] == "en"
