"""Page Object Model for the YAML Form Engine Streamlit UI.

Encapsulates Streamlit widget interaction patterns so tests read cleanly.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect


class FormPage:
    """Interact with a rendered YAML form in the browser."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.sidebar = page.locator('[data-testid="stSidebar"]')
        self.main = page.locator('[data-testid="stMain"]')

    # ---- Navigation ----

    def navigate_to_step(self, label: str) -> None:
        """Click a step label in the sidebar radio navigation.

        Streamlit renders format_func output as Markdown, so numbered prefixes
        like '1.' are stripped from text content. Pass just the step title.
        """
        self.sidebar.locator(
            '[data-testid="stRadio"] label[data-baseweb="radio"]',
            has_text=label,
        ).click()
        self._wait()

    def get_step_labels(self) -> list[str]:
        """Return all step labels visible in the sidebar radio."""
        labels = self.sidebar.locator(
            '[data-testid="stRadio"] label[data-baseweb="radio"]'
        )
        return [
            labels.nth(i).text_content().strip()
            for i in range(labels.count())
        ]

    def get_step_title(self) -> str:
        """Read the main content area h1 title."""
        return self.main.locator("h1").first.text_content().strip()

    # ---- Text Input ----

    def fill_text(self, label: str, value: str) -> None:
        """Fill a text_input widget identified by its label."""
        container = self.main.locator(
            '[data-testid="stTextInput"]', has_text=label
        )
        inp = container.locator("input")
        inp.click()
        inp.fill(value)
        inp.press("Tab")
        self._wait()

    def get_text_value(self, label: str) -> str:
        """Read the current value of a text_input."""
        container = self.main.locator(
            '[data-testid="stTextInput"]', has_text=label
        )
        return container.locator("input").input_value()

    # ---- Textarea ----

    def fill_textarea(self, label: str, value: str) -> None:
        """Fill a text_area widget."""
        container = self.main.locator(
            '[data-testid="stTextArea"]', has_text=label
        )
        ta = container.locator("textarea")
        ta.click()
        ta.fill(value)
        ta.press("Tab")
        self._wait()

    def get_textarea_value(self, label: str) -> str:
        """Read the current value of a text_area."""
        container = self.main.locator(
            '[data-testid="stTextArea"]', has_text=label
        )
        return container.locator("textarea").input_value()

    # ---- Select (Dropdown) ----

    def select_option(self, label: str, value: str) -> None:
        """Choose an option from a selectbox widget.

        Uses exact text matching to avoid 'Task' matching 'Sub-task'.
        """
        container = self.main.locator(
            '[data-testid="stSelectbox"]', has_text=label
        )
        # Click the combobox input to open the dropdown
        container.locator('input[role="combobox"]').click()
        self.page.wait_for_timeout(300)
        # Click the matching option using exact match
        self.page.get_by_role("option", name=value, exact=True).click()
        self._wait()

    # ---- Radio ----

    def select_radio(self, label: str, value: str) -> None:
        """Select a radio option within a radio group identified by label.

        Uses exact text matching to avoid partial matches (e.g. 'High' vs 'Highest').
        """
        container = self.main.locator(
            '[data-testid="stRadio"]', has_text=label
        )
        # Use exact match via regex to avoid 'High' matching 'Highest'
        container.locator(
            'label[data-baseweb="radio"]',
            has_text=re.compile(rf"^{re.escape(value)}$"),
        ).click()
        self._wait()

    def get_radio_options(self, label: str) -> list[str]:
        """Return all option labels for a radio group."""
        container = self.main.locator(
            '[data-testid="stRadio"]', has_text=label
        )
        options = container.locator('label[data-baseweb="radio"]')
        return [
            options.nth(i).text_content().strip()
            for i in range(options.count())
        ]

    # ---- Slider ----

    def get_slider_value(self, label: str) -> str:
        """Read the current displayed value of a slider."""
        container = self.main.locator(
            '[data-testid="stSlider"]', has_text=label
        )
        return container.locator(
            '[data-testid="stSliderThumbValue"]'
        ).text_content().strip()

    # ---- Content Inspection ----

    def get_payload_json(self) -> dict:
        """Parse JSON from the first st.code block on the page."""
        code_block = self.main.locator('[data-testid="stCode"]').first
        raw = code_block.text_content().strip()
        return json.loads(raw)

    def get_markdown_text(self) -> str:
        """Get all markdown text from the main content area."""
        blocks = self.main.locator('[data-testid="stMarkdown"]').all_text_contents()
        return "\n".join(blocks)

    def get_sidebar_title(self) -> str:
        """Read the sidebar title."""
        return self.sidebar.locator("h1").first.text_content().strip()

    def has_text_in_main(self, text: str) -> bool:
        """Check if text appears anywhere in the main content area."""
        return self.main.locator(f"text={text}").count() > 0

    # ---- Internal ----

    def _wait(self, timeout: float = 10_000) -> None:
        """Wait for Streamlit to finish re-rendering."""
        from tests.e2e.conftest import wait_for_streamlit

        wait_for_streamlit(self.page, timeout)
