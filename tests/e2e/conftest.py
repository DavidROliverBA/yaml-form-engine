"""E2E test fixtures for Streamlit form engine.

Manages Streamlit server lifecycle, state cleanup, and page object creation.
"""

import json
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import urllib.request
import urllib.error

# Base directory for the yaml-form-engine project
PROJECT_DIR = Path(__file__).resolve().parents[2]
FORMS_DIR = PROJECT_DIR / "forms"
STATE_DIR = PROJECT_DIR / ".form-state"
STREAMLIT_PORT = 8502
STREAMLIT_URL = f"http://localhost:{STREAMLIT_PORT}"
APP_PATH = PROJECT_DIR / "yaml_form_engine" / "_app.py"


def _wait_for_server(url: str, timeout: float = 30.0, interval: float = 0.5) -> None:
    """Poll the Streamlit health endpoint until it responds or timeout."""
    health_url = f"{url}/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(health_url, timeout=2)
            if resp.status == 200:
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(interval)
    raise TimeoutError(f"Streamlit server did not start within {timeout}s")


def _stop_server(proc: subprocess.Popen) -> None:
    """Gracefully stop the Streamlit server process."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture(scope="class")
def streamlit_server(request):
    """Start a Streamlit server for a specific form.

    The form path is set via a class attribute ``form_path`` on the test class.
    Scoped to class so all tests in the class share one server instance.
    """
    form_path = getattr(request.cls, "form_path", None)
    if form_path is None:
        pytest.skip("No form_path set on test class")

    # Resolve relative to project forms directory
    resolved = FORMS_DIR / form_path
    if not resolved.is_file():
        pytest.fail(f"Form file not found: {resolved}")

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            str(APP_PATH),
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--",
            "--form", str(resolved),
        ],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_server(STREAMLIT_URL)
    except TimeoutError:
        _stop_server(proc)
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        pytest.fail(
            f"Streamlit server failed to start.\nstdout: {stdout}\nstderr: {stderr}"
        )

    yield STREAMLIT_URL

    _stop_server(proc)


@pytest.fixture(autouse=True)
def clean_form_state():
    """Remove .form-state directory before each test for isolation."""
    if STATE_DIR.exists():
        shutil.rmtree(STATE_DIR)
    yield
    # Cleanup after test too
    if STATE_DIR.exists():
        shutil.rmtree(STATE_DIR)


def wait_for_streamlit(page, timeout: float = 10_000) -> None:
    """Wait for Streamlit to finish re-rendering after an interaction.

    Watches for the "Running..." status widget to appear and disappear.
    """
    # Short pause to let Streamlit detect the change
    page.wait_for_timeout(300)
    # Wait for any running indicator to disappear
    status = page.locator('[data-testid="stStatusWidget"]')
    try:
        status.wait_for(state="attached", timeout=2000)
        status.wait_for(state="detached", timeout=timeout)
    except Exception:
        # Status widget may never appear for very fast renders
        pass
    # Extra buffer for DOM settle
    page.wait_for_timeout(500)


@pytest.fixture
def form_page(page, streamlit_server):
    """Navigate to the form and return a FormPage instance."""
    from tests.e2e.page_objects.form_page import FormPage

    page.goto(streamlit_server)
    # Wait for initial Streamlit render
    page.wait_for_selector('[data-testid="stSidebar"]', timeout=15000)
    wait_for_streamlit(page)
    return FormPage(page)
