"""Streamlit app launcher.

Thin wrapper that sets up the package path so relative imports work
when Streamlit runs this file directly. Without this, engine.py's
relative imports (from .data_resolver, from .schema, etc.) fail
because Streamlit runs files as __main__, not as part of a package.
"""

import os
import sys

# Add the package's parent directory to sys.path so that
# 'from yaml_form_engine.engine import run' resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yaml_form_engine.engine import run

run()
