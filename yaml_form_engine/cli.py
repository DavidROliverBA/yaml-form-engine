"""CLI entry point for the YAML Form Engine.

Usage:
    python -m yaml_form_engine forms/my-form.yaml
    yfe forms/my-form.yaml                           # if installed via pip
    streamlit run yaml_form_engine/engine.py -- --form forms/my-form.yaml
"""

import os
import subprocess
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("YAML Form Engine — Define forms in YAML, render in Streamlit")
        print()
        print("Usage: yfe <form.yaml> [--port PORT]")
        print()
        print("Arguments:")
        print("  form.yaml    Path to the YAML form definition")
        print("  --port PORT  Streamlit port (default: 8501)")
        print()
        print("Examples:")
        print("  yfe forms/nfr-capture.yaml")
        print("  yfe forms/dpia-assessment.yaml --port 8502")
        print()
        print("All form data stays local. Nothing is sent externally.")
        sys.exit(0)

    form_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(form_path):
        print(f"Error: Form file not found: {form_path}", file=sys.stderr)
        sys.exit(1)

    # Parse optional --port
    port = "8501"
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = sys.argv[idx + 1]

    engine_path = os.path.join(os.path.dirname(__file__), "engine.py")

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        engine_path,
        "--server.headless", "true",
        "--server.port", port,
        "--", "--form", form_path,
    ]

    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
