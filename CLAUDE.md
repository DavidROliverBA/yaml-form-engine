# CLAUDE.md

## Project Overview

YAML Form Engine — a generic Streamlit form renderer driven by YAML configuration files. One engine renders any form definition. AI agents generate the YAML; humans fill in the data locally.

## Quick Start

```bash
pip install streamlit pyyaml pandas
streamlit run yaml_form_engine/engine.py -- --form forms/arch-review.yaml
```

## Architecture

```
yaml_form_engine/
├── engine.py          # Main Streamlit app (entry point)
├── schema.py          # YAML form validation
├── data_resolver.py   # External data loading + path security
├── fields.py          # Field type to Streamlit widget mapping
├── expressions.py     # Safe expression evaluator (regex only)
├── exporters.py       # Export to markdown/CSV/JSON/Confluence
├── cli.py             # CLI entry point (yfe command)
└── __main__.py        # python -m yaml_form_engine support

forms/                 # Example form definitions
data/                  # Example data files
docs/                  # Documentation
tests/                 # Test suite
```

## Security Rules

**CRITICAL — these rules must never be violated:**

1. **Never use unsafe YAML loading** — always `yaml.safe_load()`
2. **Never use dynamic code evaluation** — expressions use regex parsing only
3. **Never make HTTP calls** — no `requests`, `urllib`, `httpx`, `socket` imports
4. **Always validate data source paths** — must resolve within form directory, no `..`
5. **Form responses stay local** — `.form-state/` directory, never transmitted

## Key Design Decisions

- **Expression evaluator** (`expressions.py`): Uses regex to parse expressions into (function, field, operator, value) tuples. Whitelisted functions only. No dynamic code evaluation of any kind.
- **Data resolver** (`data_resolver.py`): Paths are validated, resolved, and confined to the form's directory tree. Only `.yaml`, `.yml`, `.json` extensions allowed.
- **Field renderer** (`fields.py`): Registry pattern mapping field type strings to Streamlit widget functions. No dynamic dispatch.

## Creating New Form Types

To create a new form YAML:

1. Define `form.id`, `form.title`, `form.steps`
2. Each step has `id`, `title`, `type` (input | data_driven | computed | export | info)
3. Input steps have `fields` array with `id`, `type`, `label`
4. Data-driven steps reference a `data_source` and define `per_item` fields
5. Computed steps define `metrics` with expression `calc` values
6. Export steps define `formats` with `id`, `label`, `filename`

## Testing

```bash
pip install -e ".[dev]"
pytest
```
