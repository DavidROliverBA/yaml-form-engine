"""CLI entry point for the YAML Form Engine.

Usage:
    yfe forms/my-form.yaml                        # Run a form (shorthand)
    yfe run forms/my-form.yaml                     # Run a form (explicit)
    yfe generate --schema-file tools/schema.json   # Generate form from MCP schema
    yfe generate --schema-stdin                    # Generate from piped JSON
    yfe list                                       # List available forms
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _cmd_run(args):
    """Run a form in Streamlit."""
    form_path = os.path.abspath(args.form)
    if not os.path.isfile(form_path):
        print(f"Error: Form file not found: {form_path}", file=sys.stderr)
        sys.exit(1)

    engine_path = os.path.join(os.path.dirname(__file__), "engine.py")
    port = args.port or "8501"

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        engine_path,
        "--server.headless", "true",
        "--server.port", port,
        "--", "--form", form_path,
    ]

    sys.exit(subprocess.call(cmd))


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
    elif args.command == "generate":
        _cmd_generate(args)
    elif args.command == "list":
        _cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
