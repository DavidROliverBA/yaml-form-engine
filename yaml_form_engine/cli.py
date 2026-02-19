"""CLI entry point for the YAML Form Engine.

Usage:
    yfe forms/my-form.yaml                        # Run a form (shorthand)
    yfe run forms/my-form.yaml                     # Run a form (explicit)
    yfe submit forms/mcp/notion-search.yaml        # Launch, capture payload, exit
    yfe generate --schema-file tools/schema.json   # Generate form from MCP schema
    yfe generate --schema-stdin                    # Generate from piped JSON
    yfe list                                       # List available forms
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def _cmd_run(args):
    """Run a form in Streamlit."""
    form_path = os.path.abspath(args.form)
    if not os.path.isfile(form_path):
        print(f"Error: Form file not found: {form_path}", file=sys.stderr)
        sys.exit(1)

    engine_path = os.path.join(os.path.dirname(__file__), "_app.py")
    port = args.port or "8501"

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        engine_path,
        "--server.headless", "true",
        "--server.port", port,
        "--", "--form", form_path,
    ]

    sys.exit(subprocess.call(cmd))


def _extract_mcp_metadata(form_path: str) -> tuple:
    """Extract form ID, MCP server, and tool from form YAML.

    Returns (form_id, server, tool). Exits with error if not an MCP form.
    """
    import yaml

    with open(form_path) as f:
        form_def = yaml.safe_load(f)
    form = form_def.get("form", form_def)
    form_id = form.get("id", "form")
    for step in form.get("steps", []):
        if step.get("type") == "submit" and "mcp" in step:
            return form_id, step["mcp"]["server"], step["mcp"]["tool"]
    print("Error: Form has no MCP submit step", file=sys.stderr)
    sys.exit(1)


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


def _cmd_submit(args):
    """Launch form, wait for user action choice, behave accordingly."""
    form_path = os.path.abspath(args.form)
    if not os.path.isfile(form_path):
        print(f"Error: Form file not found: {form_path}", file=sys.stderr)
        sys.exit(1)

    form_id, server, tool = _extract_mcp_metadata(form_path)
    port = args.port
    url = f"http://localhost:{port}"

    # Use project root for .form-state and Streamlit cwd
    project_root = _find_project_root(form_path)
    state_dir = Path(project_root) / ".form-state"
    payload_file = state_dir / f"{form_id}-payload.json"
    decision_file = state_dir / f"{form_id}-decision.json"

    # Delete stale files
    for stale in (payload_file, decision_file):
        if stale.exists():
            stale.unlink()

    engine_path = os.path.join(os.path.dirname(__file__), "_app.py")

    print(f"Launching form on port {port}...", file=sys.stderr)
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            engine_path,
            "--server.headless", "true",
            "--server.port", port,
            "--browser.gatherUsageStats", "false",
            "--", "--form", form_path,
        ],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_server(url)
    except TimeoutError:
        _stop_server(proc)
        print("Error: Streamlit server failed to start", file=sys.stderr)
        sys.exit(1)

    # Build open URL — pass default_action as query param if --action given
    open_url = f"{url}?default_action={args.action}" if args.action else url

    if not args.no_browser:
        webbrowser.open(open_url)
        print(f"Opened {open_url} in browser", file=sys.stderr)
    else:
        print(f"Form available at {url}", file=sys.stderr)

    print("Waiting for form submission...", file=sys.stderr)

    # Poll for decision file (written when user clicks an action button)
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            if decision_file.exists():
                with open(decision_file) as f:
                    decision = json.load(f)
                action = decision.get("action", "execute")

                if action == "execute":
                    # Read the payload and output structured JSON
                    with open(payload_file) as f:
                        payload = json.load(f)
                    output = {
                        "server": server,
                        "tool": tool,
                        "arguments": payload,
                        "action": "execute",
                    }
                    print(json.dumps(output, indent=2))
                elif action == "download":
                    print("User downloaded payload", file=sys.stderr)
                elif action == "clipboard":
                    print("User copied invocation", file=sys.stderr)

                # Brief pause so the browser finishes rendering
                time.sleep(2)
                _stop_server(proc)
                sys.exit(0)
            time.sleep(0.5)

        # Timeout reached
        print(f"Error: Timed out after {args.timeout}s waiting for submission", file=sys.stderr)
        _stop_server(proc)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nCancelled by user", file=sys.stderr)
        _stop_server(proc)
        sys.exit(130)


def _find_project_root(form_path: str) -> str:
    """Walk up from form_path to find the project root (contains pyproject.toml or .git)."""
    current = Path(form_path).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return str(parent)
    return str(current)


def _cmd_generate(args):
    """Generate a YAML form from an MCP tool schema."""
    from .form_generator import generate_form
    from .mcp_introspect import parse_tool_schema

    # Load schema from file or stdin
    if args.schema_file:
        schema_path = os.path.abspath(args.schema_file)
        if not os.path.isfile(schema_path):
            print(f"Error: Schema file not found: {schema_path}", file=sys.stderr)
            sys.exit(1)
        with open(schema_path) as f:
            raw = json.load(f)
    elif args.schema_stdin:
        raw = json.load(sys.stdin)
    else:
        print("Error: Provide --schema-file or --schema-stdin", file=sys.stderr)
        sys.exit(1)

    schema = parse_tool_schema(raw)
    output_dir = args.output or "forms/mcp"
    output_path = generate_form(schema, output_dir)
    print(f"Generated: {output_path}")

    if args.launch:
        print(f"Launching: {output_path}")

        class RunArgs:
            pass
        run_args = RunArgs()
        run_args.form = output_path
        run_args.port = args.port
        _cmd_run(run_args)


def _cmd_list(args):
    """List available forms."""
    forms_dir = Path(args.directory or "forms")
    if not forms_dir.is_dir():
        print(f"No forms directory found at: {forms_dir}")
        sys.exit(0)

    yaml_files = sorted(forms_dir.rglob("*.yaml")) + sorted(forms_dir.rglob("*.yml"))
    if not yaml_files:
        print("No forms found.")
        sys.exit(0)

    print(f"Available forms in {forms_dir}/:\n")
    for f in yaml_files:
        rel = f.relative_to(forms_dir)
        print(f"  {rel}")

    print(f"\nTotal: {len(yaml_files)} form(s)")
    print(f"\nRun with: yfe run forms/<name>.yaml")


def main():
    parser = argparse.ArgumentParser(
        prog="yfe",
        description="YAML Form Engine - Define forms in YAML, render in Streamlit",
    )
    subparsers = parser.add_subparsers(dest="command")

    # yfe run <form.yaml>
    run_parser = subparsers.add_parser("run", help="Run a YAML form")
    run_parser.add_argument("form", help="Path to the YAML form definition")
    run_parser.add_argument("--port", default=None, help="Streamlit port (default: 8501)")

    # yfe submit <form.yaml>
    submit_parser = subparsers.add_parser("submit", help="Launch form, capture payload for MCP execution")
    submit_parser.add_argument("form", help="Path to the YAML form definition")
    submit_parser.add_argument("--port", default="8503", help="Streamlit port (default: 8503)")
    submit_parser.add_argument("--timeout", type=int, default=300, help="Max seconds to wait (default: 300)")
    submit_parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    submit_parser.add_argument(
        "--action", default=None,
        choices=["execute", "download", "clipboard"],
        help="Pre-select default action (user still sees all buttons)",
    )

    # yfe generate
    gen_parser = subparsers.add_parser("generate", help="Generate form from MCP tool schema")
    gen_parser.add_argument("--schema-file", help="Path to JSON schema file")
    gen_parser.add_argument("--schema-stdin", action="store_true", help="Read schema from stdin")
    gen_parser.add_argument("--output", "-o", help="Output directory (default: forms/mcp)")
    gen_parser.add_argument("--launch", "-l", action="store_true", help="Launch the form immediately after generating")
    gen_parser.add_argument("--port", default=None, help="Streamlit port when using --launch")

    # yfe list
    list_parser = subparsers.add_parser("list", help="List available forms")
    list_parser.add_argument("--directory", "-d", default=None, help="Forms directory (default: forms)")

    args = parser.parse_args()

    # Backwards compatibility: if no subcommand, treat first arg as a form path
    if args.command is None:
        if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
            parser.print_help()
            print("\nQuick start:")
            print("  yfe forms/my-form.yaml          Run a form")
            print("  yfe generate --schema-file x.json  Generate from MCP schema")
            print("  yfe list                         List available forms")
            print("\nAll form data stays local. Nothing is sent externally.")
            sys.exit(0)

        # Legacy mode: first positional arg is a form path
        # Check if it looks like a file path (not a subcommand)
        potential_path = sys.argv[1]
        if os.path.isfile(potential_path) or potential_path.endswith((".yaml", ".yml")):
            # Parse --port if present
            port = "8501"
            if "--port" in sys.argv:
                idx = sys.argv.index("--port")
                if idx + 1 < len(sys.argv):
                    port = sys.argv[idx + 1]

            class LegacyArgs:
                pass
            legacy = LegacyArgs()
            legacy.form = potential_path
            legacy.port = port
            _cmd_run(legacy)
            return
        else:
            parser.print_help()
            sys.exit(1)

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "submit":
        _cmd_submit(args)
    elif args.command == "generate":
        _cmd_generate(args)
    elif args.command == "list":
        _cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
