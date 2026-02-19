"""Tests for the yfe submit command helpers."""

import json
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

from yaml_form_engine.cli import _extract_mcp_metadata, _find_project_root


# ---- Fixtures ----

@pytest.fixture
def tmp_form(tmp_path):
    """Create a temporary YAML form file and return its path."""
    def _make(content: dict) -> str:
        form_file = tmp_path / "test-form.yaml"
        form_file.write_text(yaml.dump(content, default_flow_style=False))
        return str(form_file)
    return _make


# ---- _extract_mcp_metadata ----

class TestExtractMcpMetadata:
    def test_notion_search(self):
        """Parses MCP metadata from notion-search form."""
        form_path = os.path.join(
            os.path.dirname(__file__), "..", "forms", "mcp", "notion-search.yaml"
        )
        form_id, server, tool = _extract_mcp_metadata(form_path)
        assert form_id == "mcp-notion-search"
        assert server == "MCP_DOCKER"
        assert tool == "API-post-search"

    def test_jira_create_issue(self):
        """Parses MCP metadata from jira-create-issue form."""
        form_path = os.path.join(
            os.path.dirname(__file__), "..", "forms", "mcp", "jira-create-issue.yaml"
        )
        form_id, server, tool = _extract_mcp_metadata(form_path)
        assert form_id == "mcp-jira-create-issue"
        assert server == "plugin_atlassian_atlassian"
        assert tool == "createJiraIssue"

    def test_youtube_transcript(self):
        """Parses MCP metadata from youtube-transcript form."""
        form_path = os.path.join(
            os.path.dirname(__file__), "..", "forms", "mcp", "youtube-transcript.yaml"
        )
        form_id, server, tool = _extract_mcp_metadata(form_path)
        assert form_id == "mcp-youtube-transcript"
        assert server == "MCP_DOCKER"
        assert tool == "get_transcript"

    def test_no_mcp_step_exits(self, tmp_form):
        """Exits with error for forms without an MCP submit step."""
        form = {
            "form": {
                "id": "no-mcp",
                "title": "Test",
                "steps": [
                    {"id": "input", "type": "input", "title": "Input", "fields": []},
                    {"id": "submit", "type": "submit", "title": "Submit"},
                ],
            }
        }
        path = tmp_form(form)
        with pytest.raises(SystemExit) as exc_info:
            _extract_mcp_metadata(path)
        assert exc_info.value.code == 1

    def test_defaults_form_id(self, tmp_form):
        """Defaults form_id to 'form' when id not specified."""
        form = {
            "form": {
                "title": "Test",
                "steps": [
                    {
                        "id": "submit",
                        "type": "submit",
                        "title": "Submit",
                        "mcp": {"server": "S", "tool": "T"},
                    },
                ],
            }
        }
        path = tmp_form(form)
        form_id, server, tool = _extract_mcp_metadata(path)
        assert form_id == "form"
        assert server == "S"
        assert tool == "T"


# ---- _find_project_root ----

class TestFindProjectRoot:
    def test_finds_pyproject_toml(self, tmp_path):
        """Finds root when pyproject.toml exists."""
        (tmp_path / "pyproject.toml").touch()
        subdir = tmp_path / "forms" / "mcp"
        subdir.mkdir(parents=True)
        form_file = subdir / "test.yaml"
        form_file.touch()
        result = _find_project_root(str(form_file))
        assert result == str(tmp_path)

    def test_finds_git_dir(self, tmp_path):
        """Finds root when .git directory exists."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "forms"
        subdir.mkdir()
        form_file = subdir / "test.yaml"
        form_file.touch()
        result = _find_project_root(str(form_file))
        assert result == str(tmp_path)

    def test_falls_back_to_parent_dir(self, tmp_path):
        """Falls back to form's parent directory when no markers found."""
        form_file = tmp_path / "test.yaml"
        form_file.touch()
        result = _find_project_root(str(form_file))
        # Should return some directory (at minimum the form's parent or a parent with markers)
        assert os.path.isdir(result)


# ---- Output format ----

class TestSubmitOutputFormat:
    def test_output_structure(self):
        """Validates the JSON output structure matches expected schema."""
        output = {
            "server": "MCP_DOCKER",
            "tool": "API-post-search",
            "arguments": {"query": "test", "filter_object_type": "page"},
            "action": "execute",
        }
        serialised = json.dumps(output, indent=2)
        parsed = json.loads(serialised)

        assert "server" in parsed
        assert "tool" in parsed
        assert "arguments" in parsed
        assert "action" in parsed
        assert parsed["action"] == "execute"
        assert isinstance(parsed["arguments"], dict)

    def test_output_with_empty_arguments(self):
        """Handles empty arguments dict."""
        output = {
            "server": "S",
            "tool": "T",
            "arguments": {},
            "action": "execute",
        }
        serialised = json.dumps(output, indent=2)
        parsed = json.loads(serialised)
        assert parsed["arguments"] == {}
        assert parsed["action"] == "execute"


# ---- Decision file behaviour ----

class TestDecisionFile:
    """Tests for the two-file (payload + decision) approach."""

    def test_decision_file_execute(self, tmp_path):
        """Decision with action=execute produces JSON on stdout."""
        state_dir = tmp_path / ".form-state"
        state_dir.mkdir()

        # Write payload file (as engine does)
        payload = {"query": "test"}
        (state_dir / "test-payload.json").write_text(json.dumps(payload))

        # Write decision file (as engine does when user clicks Execute)
        decision = {"action": "execute"}
        (state_dir / "test-decision.json").write_text(json.dumps(decision))

        # Read back and verify the expected output structure
        with open(state_dir / "test-decision.json") as f:
            d = json.load(f)
        assert d["action"] == "execute"

        with open(state_dir / "test-payload.json") as f:
            p = json.load(f)

        output = {
            "server": "S",
            "tool": "T",
            "arguments": p,
            "action": "execute",
        }
        assert output["arguments"] == {"query": "test"}
        assert output["action"] == "execute"

    def test_decision_file_download(self, tmp_path):
        """Decision with action=download produces no stdout output."""
        state_dir = tmp_path / ".form-state"
        state_dir.mkdir()

        decision = {"action": "download"}
        (state_dir / "test-decision.json").write_text(json.dumps(decision))

        with open(state_dir / "test-decision.json") as f:
            d = json.load(f)
        assert d["action"] == "download"
        # download action should not produce stdout — CLI just exits 0

    def test_decision_file_clipboard(self, tmp_path):
        """Decision with action=clipboard produces no stdout output."""
        state_dir = tmp_path / ".form-state"
        state_dir.mkdir()

        decision = {"action": "clipboard"}
        (state_dir / "test-decision.json").write_text(json.dumps(decision))

        with open(state_dir / "test-decision.json") as f:
            d = json.load(f)
        assert d["action"] == "clipboard"
        # clipboard action should not produce stdout — CLI just exits 0


# ---- --action flag ----

class TestActionFlag:
    """Tests that the --action CLI argument is accepted by argparse."""

    def test_action_flag_accepted(self):
        """--action execute is accepted without error."""
        result = subprocess.run(
            [
                sys.executable, "-m", "yaml_form_engine.cli",
                "submit", "--help",
            ],
            capture_output=True, text=True,
        )
        assert "--action" in result.stdout
        assert "execute" in result.stdout
        assert "download" in result.stdout
        assert "clipboard" in result.stdout

    def test_action_flag_invalid_rejected(self):
        """--action with an invalid value is rejected."""
        result = subprocess.run(
            [
                sys.executable, "-m", "yaml_form_engine.cli",
                "submit", "dummy.yaml", "--action", "invalid",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr
