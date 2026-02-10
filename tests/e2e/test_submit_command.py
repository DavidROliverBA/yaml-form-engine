"""End-to-end test for the yfe submit command.

Launches yfe submit as a subprocess, fills the form with Playwright,
and verifies the subprocess outputs correct JSON and exits cleanly.
"""

import json
import signal
import subprocess
import sys
import time

import pytest
import urllib.error
import urllib.request

from tests.e2e.conftest import PROJECT_DIR


SUBMIT_PORT = 8504  # Avoid clashing with other test servers


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    """Poll the Streamlit health endpoint until it responds."""
    health_url = f"{url}/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(health_url, timeout=2)
            if resp.status == 200:
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Server did not start within {timeout}s")


@pytest.mark.e2e
class TestSubmitCommand:
    """Full yfe submit flow: launch, fill form, capture JSON output."""

    def test_notion_search_submit(self, page):
        """Launch submit for notion-search, fill form, verify JSON output."""
        form_path = str(PROJECT_DIR / "forms" / "mcp" / "notion-search.yaml")
        url = f"http://localhost:{SUBMIT_PORT}"

        # Launch yfe submit as a subprocess
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "yaml_form_engine.cli",
                "submit", form_path,
                "--port", str(SUBMIT_PORT),
                "--no-browser",
                "--timeout", "60",
            ],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for the Streamlit server to be ready
            _wait_for_server(url)

            # Navigate to the form
            page.goto(url)
            page.wait_for_selector('[data-testid="stSidebar"]', timeout=15000)
            page.wait_for_timeout(1000)

            # Fill the form
            # Search Query
            query_container = page.locator(
                '[data-testid="stTextInput"]', has_text="Search Query"
            )
            query_input = query_container.locator("input")
            query_input.click()
            query_input.fill("architecture decisions")
            query_input.press("Tab")
            page.wait_for_timeout(500)

            # Select "Pages" radio
            radio_container = page.locator(
                '[data-testid="stRadio"]', has_text="Filter by Type"
            )
            radio_container.locator(
                'label[data-baseweb="radio"]', has_text="Pages"
            ).click()
            page.wait_for_timeout(500)

            # Navigate to Submit step
            sidebar = page.locator('[data-testid="stSidebar"]')
            sidebar.locator(
                '[data-testid="stRadio"] label[data-baseweb="radio"]',
                has_text="Submit",
            ).click()
            page.wait_for_timeout(2000)

            # Wait for the subprocess to capture the payload and exit
            stdout, stderr = proc.communicate(timeout=30)
            assert proc.returncode == 0, f"Submit exited with {proc.returncode}: {stderr.decode()}"

            # Parse and validate JSON output
            output = json.loads(stdout.decode())
            assert output["server"] == "MCP_DOCKER"
            assert output["tool"] == "API-post-search"
            assert output["arguments"]["query"] == "architecture decisions"
            assert output["arguments"]["filter_object_type"] == "page"

        except Exception:
            # Clean up on failure
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            raise

    def test_submit_timeout_exits_with_code_2(self):
        """Verify that submit exits with code 2 on timeout."""
        form_path = str(PROJECT_DIR / "forms" / "mcp" / "notion-search.yaml")

        # Launch with a very short timeout so it times out immediately
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "yaml_form_engine.cli",
                "submit", form_path,
                "--port", str(SUBMIT_PORT + 1),
                "--no-browser",
                "--timeout", "2",
            ],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = proc.communicate(timeout=60)
        assert proc.returncode == 2, f"Expected exit code 2, got {proc.returncode}: {stderr.decode()}"
        assert b"Timed out" in stderr

    def test_submit_non_mcp_form_exits_with_code_1(self):
        """Verify that submit exits with code 1 for non-MCP forms."""
        form_path = str(PROJECT_DIR / "forms" / "arch-review.yaml")

        proc = subprocess.Popen(
            [
                sys.executable, "-m", "yaml_form_engine.cli",
                "submit", form_path,
                "--port", str(SUBMIT_PORT + 2),
                "--no-browser",
            ],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 1
        assert b"no MCP submit step" in stderr
