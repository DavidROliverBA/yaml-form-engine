# Plan: User Action Choice in `yfe submit`

## Context

`yfe submit` currently auto-captures the payload the instant the user navigates to the Submit step and immediately hands it to Claude Code for execution. The user has no say — no choice to download it, copy it, or just close the form. The request: always give the user a choice of what happens with their payload, and let the `/mcp-form` skill detect intent from the user's prompt to suggest a default.

## How It Works (Updated Flow)

```
Claude Code                          Browser
    |                                    |
    |-- yfe submit form.yaml --------->  |
    |   (starts Streamlit on 8503)       |
    |   (opens browser)                  |
    |                              User fills form
    |                              Navigates to Submit
    |                                    |
    |                              Sees payload preview
    |                              Sees 3 action buttons:
    |                                [Execute]  [Download]  [Copy & Close]
    |                                    |
    |                              User clicks one
    |                                    |
    |   (decision file appears in        |
    |    .form-state/<id>-decision.json) |
    |                                    |
    |<-- behaviour depends on action     |
    |   (kills Streamlit)                |
    |                                    |
    |-- skill handles follow-up -------> |
```

## Key Design: Two-File Approach

**Why?** The payload file is written automatically when the Submit step renders (side-effect of `_render_submit_step`). Changing that would require rearchitecting the render function. Instead, we add a **decision file** that the CLI polls for. The payload file continues to be written immediately (supports download button and manual access).

| File | Written when | Purpose |
|------|-------------|---------|
| `.form-state/{id}-payload.json` | Submit step renders (as today) | Payload data |
| `.form-state/{id}-decision.json` | User clicks an action button | User's choice: `execute`, `download`, or `clipboard` |

## Implementation Steps

### Step 1: Refactor `_render_submit_step()` in engine.py

**Current** (lines 584-611): Two-column layout with "Copy Invocation" and "Download Payload" buttons. Payload auto-saved.

**New**: Three-column layout with explicit action buttons. Each writes a decision file.

Changes:
- Keep payload file auto-write (lines 605-611) — unchanged
- Replace the two-column button layout with three action buttons
- Add `_write_decision()` helper to write `{"action": "<choice>"}` to `.form-state/{id}-decision.json`
- Use `st.session_state` to disable buttons after one is clicked (prevent double-click)
- Show feedback after click: success message for Execute, info message for Copy

```python
# Decision file path
decision_file = state_dir / f"{form_id}-decision.json"

st.subheader("What would you like to do?")

# Prevent double-click
if "submit_decision_made" not in st.session_state:
    st.session_state.submit_decision_made = False

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Execute via Claude Code", type="primary",
                  disabled=st.session_state.submit_decision_made):
        _write_decision(decision_file, "execute")
        st.session_state.submit_decision_made = True
        st.success("Payload sent to Claude Code.")

with col2:
    # download_button triggers browser download + writes decision
    st.download_button(
        "Download Payload",
        payload_json,
        file_name=f"{form_id}-payload.json",
        mime="application/json",
        disabled=st.session_state.submit_decision_made,
        on_click=_on_download_click,
        args=(decision_file,),
    )

with col3:
    if st.button("Copy & Close",
                  disabled=st.session_state.submit_decision_made):
        command = format_mcp_command(server, tool, payload)
        _write_decision(decision_file, "clipboard")
        st.session_state.submit_decision_made = True
        st.code(command)
        st.info("Copy the command above. Form closing shortly.")
```

Helper functions:
```python
def _write_decision(decision_file: Path, action: str) -> None:
    with open(decision_file, "w") as f:
        json.dump({"action": action}, f)

def _on_download_click(decision_file: Path) -> None:
    _write_decision(decision_file, "download")
```

### Step 2: Modify `_cmd_submit()` in cli.py

Change the polling loop to watch for the **decision file** instead of the payload file.

- Delete both stale files (payload + decision) at startup
- Poll for `{form_id}-decision.json` every 0.5s
- Read the `action` field from the decision file
- Behave differently per action:

| Action | stdout | Exit code | Behaviour |
|--------|--------|-----------|-----------|
| `execute` | Full JSON `{"server", "tool", "arguments", "action": "execute"}` | 0 | Claude Code parses and invokes MCP tool |
| `download` | Nothing | 0 | User has the file; stderr: "User downloaded payload" |
| `clipboard` | Nothing | 0 | User copied command; stderr: "User copied invocation" |

All actions exit 0 (success) — the user made a deliberate choice in each case. Error/timeout/cancel codes unchanged (1, 2, 130).

### Step 3: Add `--action` flag for precanned defaults

Add a `--action` CLI argument that the skill can pass based on prompt intent:

```python
submit_parser.add_argument(
    "--action", default=None,
    choices=["execute", "download", "clipboard"],
    help="Pre-select default action (user still sees all buttons)"
)
```

When `--action` is provided, pass it as a Streamlit query param:
```python
open_url = f"{url}?default_action={args.action}" if args.action else url
webbrowser.open(open_url)
```

In `_render_submit_step()`, read `st.query_params.get("default_action")` and set that button as `type="primary"` while the others are `type="secondary"`. The user still sees all three buttons and can override.

### Step 4: Update `/mcp-form` skill

Two changes to `.claude/skills/mcp-form.md`:

**a) Interpret exit codes and stdout:**
```
After `yfe submit` exits:
- If JSON on stdout → parse it, check `action` field:
  - "execute" → call mcp__<server>__<tool>(arguments)
  - (other actions produce no stdout)
- If no stdout, exit 0 → user handled it themselves, report that
- Exit 2 → timeout, report it
- Exit 130 → user cancelled
```

**b) Prompt intent detection → `--action` flag:**

| User prompt pattern | Detected intent | Flag |
|---|---|---|
| "fetch/search/create and ..." (action verb + continuation) | Execute | `--action execute` |
| "save/export/download the payload" | Download | `--action download` |
| No clear signal | Let user choose | (no flag) |

**c) Follow-up in terminal** (after MCP tool returns):

For tool-specific follow-ups, the skill asks in the terminal:
- `get_transcript` → "Create a YouTube note from this transcript?"
- `API-post-search` → "Show results as a table?"
- `createJiraIssue` → "Link this issue to a project note?"

This is skill logic only — no engine changes needed.

### Step 5: Update unit tests

In `tests/test_cli_submit.py`, add:
- `test_decision_file_execute` — decision `{"action": "execute"}` → JSON on stdout
- `test_decision_file_download` — decision `{"action": "download"}` → no stdout, exit 0
- `test_decision_file_clipboard` — decision `{"action": "clipboard"}` → no stdout, exit 0
- `test_action_flag_accepted` — `--action execute` is accepted by argparser

### Step 6: Update E2E tests

In `tests/e2e/test_submit_command.py`:
- **Update** `test_notion_search_submit` — after navigating to Submit, click "Execute via Claude Code" button before expecting JSON output
- **Add** `test_download_action` — click "Download Payload", verify no stdout, exit 0
- **Add** `test_copy_action` — click "Copy & Close", verify no stdout, exit 0

## Critical Files

| File | Action | Purpose |
|------|--------|---------|
| `yaml_form_engine/engine.py` | Modify | Refactor `_render_submit_step()`: 3 action buttons, decision file write |
| `yaml_form_engine/cli.py` | Modify | Poll for decision file, `--action` flag, action-dependent exit behaviour |
| `.claude/skills/mcp-form.md` | Modify | Interpret actions, prompt intent detection, follow-up questions |
| `tests/test_cli_submit.py` | Modify | Add decision file and action flag tests |
| `tests/e2e/test_submit_command.py` | Modify | Update execute test, add download/copy tests |

## Reusable Code

- `engine.py:606-610` — Payload file write pattern (keep as-is)
- `engine.py:589-592` — `format_mcp_command()` call (reuse for Copy & Close)
- `cli.py:64-76` — `_wait_for_server()` (unchanged)
- `cli.py:79-87` — `_stop_server()` (unchanged)
- Streamlit's `st.query_params` (>=1.30.0, already in deps)
- Streamlit's `st.download_button(on_click=...)` for triggering decision write alongside download

## Verification

```bash
# 1. Unit tests
pytest tests/test_cli_submit.py -v

# 2. E2E tests
pytest tests/e2e/test_submit_command.py -v

# 3. Manual test: each action path
yfe submit forms/mcp/youtube-transcript.yaml                # click Execute
yfe submit forms/mcp/youtube-transcript.yaml                # click Download
yfe submit forms/mcp/youtube-transcript.yaml                # click Copy & Close
yfe submit forms/mcp/notion-search.yaml --action execute    # pre-selected default

# 4. Full test suite
pytest -m "not e2e" -v
pytest tests/e2e/ -v
```
