# YAML Form Engine

Define forms in YAML. Render them instantly in Streamlit. All data stays local.

**The AI generates the config. Humans fill in the data. Nothing leaves your machine.**

## Why?

Building a Streamlit form takes ~2,000+ tokens and custom Python code per form. A YAML config takes ~200-500 tokens — an 80-90% reduction. One generic engine renders any form definition.

| Approach | Tokens | Maintenance |
|----------|--------|-------------|
| Custom Streamlit app | ~2,000-3,000 per form | Separate Python files per form |
| YAML form definition | ~200-500 per form | Single engine, many configs |

## Quick Start

```bash
# Install dependencies
pip install streamlit pyyaml pandas

# Run a form
streamlit run yaml_form_engine/engine.py -- --form forms/arch-review.yaml

# Or use the CLI
pip install -e .
yfe forms/arch-review.yaml
```

Open http://localhost:8501 in your browser.

## Security Model

This engine is designed with a strict security boundary: **the AI writes the YAML config, but all captured data stays local**.

- **No network access** — the engine makes zero HTTP calls
- **No telemetry** — no usage data, analytics, or phone-home
- **Local storage only** — form state saves to `.form-state/` as JSON
- **Safe YAML parsing** — `yaml.safe_load` only (no arbitrary code execution)
- **No eval/exec** — expressions use a regex-based parser, not Python eval
- **Path confinement** — data sources must resolve within the form's directory
- **Auditable configs** — YAML is human-readable, diffable, and code-reviewable

See [docs/security.md](docs/security.md) for the full threat model.

## Example Forms

| Form | Description | Launch |
|------|-------------|--------|
| `arch-review.yaml` | Architecture review checklist with 0-3 scoring | `yfe forms/arch-review.yaml` |
| `dpia-assessment.yaml` | Data Protection Impact Assessment questionnaire | `yfe forms/dpia-assessment.yaml` |
| `vendor-scorecard.yaml` | Vendor evaluation with weighted criteria | `yfe forms/vendor-scorecard.yaml` |

## YAML Schema

### Top-Level Structure

```yaml
form:
  id: my-form                    # Unique identifier
  title: "My Form"               # Display title
  description: "What this form captures"
  version: "1.0"

  # Optional: external data source
  data_source:
    path: "../data/criteria.yaml"  # Relative to form file
    key: categories                # Root key containing items
    id_field: id                   # Unique ID field per item
    label_field: title             # Display label field
    items_key: criteria            # Sub-key for nested items

  # Optional: filters (sidebar)
  filters:
    - id: tier
      label: "Tier"
      type: select
      source: data.classification_tiers
    - id: scope
      label: "Scope"
      type: multiselect
      options:
        - { value: all, label: "All", default: true }
      filters_field: applicability

  # Wizard steps
  steps:
    - id: setup
      title: "Setup"
      type: input
      fields: [...]

    - id: review
      title: "Review"
      type: data_driven
      per_item: [...]
      display_fields: [...]

    - id: summary
      title: "Summary"
      type: computed
      metrics: [...]
      tables: [...]

    - id: export
      title: "Export"
      type: export
      formats: [...]
```

### Step Types

| Type | Purpose |
|------|---------|
| `input` | Collect user input with form fields |
| `data_driven` | Iterate over external data items with per-item fields |
| `computed` | Auto-calculated summary with metrics and tables |
| `export` | Download in markdown, CSV, JSON, or Confluence format |
| `info` | Read-only display (instructions, context) |

### Field Types

| Type | Widget | Key Properties |
|------|--------|---------------|
| `text` | Text input | placeholder, required, default |
| `textarea` | Multi-line text | placeholder, height |
| `select` | Dropdown | options, default |
| `multiselect` | Multi-select | options, default |
| `number` | Number input | min, max, step |
| `date` | Date picker | default (today or YYYY-MM-DD) |
| `checkbox` | Checkbox | default, locked |
| `radio` | Radio buttons | options, horizontal |
| `slider` | Slider | min, max, step |
| `score` | Labelled slider | scale [min, max], labels |
| `file` | File upload | types (extensions) |

### Expression Language

For computed steps — safe, no eval:

```yaml
# Counting
count_where(review.status == Met)
count_where(review.score in [0, 1])

# Percentages
percent_where(review.status in [Met, Partial, N/A])

# Aggregation
sum(review.score)
avg(checklist.score)
min(review.score)
max(review.score)
count(review.score)

# Template interpolation (in filenames, text)
"{setup.system_name} - {form.title}"
```

### Conditions

Fields and steps can be conditional:

```yaml
fields:
  - id: pci_details
    type: textarea
    label: "PCI Scope Details"
    show_if: "setup.project_types contains pci"
```

## Architecture

```
┌──────────────┐
│  YAML Form   │  ← AI generates this (~200 tokens)
│  Definition  │
└──────┬───────┘
       │ reads
┌──────▼───────┐
│  Form Engine │  ← Generic, never changes
│  (Streamlit) │
└──────┬───────┘
       │ renders
┌──────▼───────┐
│   Browser    │  ← User fills in data locally
│  (localhost) │
└──────┬───────┘
       │ saves
┌──────▼───────┐
│  .form-state │  ← Local JSON files, never sent anywhere
│  exports/    │
└──────────────┘
```

### Modules

| Module | Purpose |
|--------|---------|
| `engine.py` | Main Streamlit app — renders steps, manages state |
| `schema.py` | Validates YAML form definitions before rendering |
| `data_resolver.py` | Loads external data with path security |
| `fields.py` | Maps field types to Streamlit widgets |
| `expressions.py` | Safe expression evaluator (no eval/exec) |
| `exporters.py` | Export to markdown, Confluence, CSV, JSON |
| `cli.py` | CLI entry point (`yfe` command) |

## Auto-Save

Form state is automatically saved to `.form-state/<form-id>.json` after every interaction. Close the browser and reopen — your data is still there. The `.form-state/` directory is gitignored by default.

## Creating Your Own Forms

1. Copy an example from `forms/`
2. Edit the YAML — change fields, steps, data sources
3. Run: `yfe forms/your-form.yaml`

Or have an AI generate the YAML from a natural language description:

> "Create a YAML form definition for capturing incident post-mortem data.
> Include fields for incident title, severity, timeline, root cause,
> and action items. Use a 0-3 scoring system for impact assessment."

The AI writes ~300 tokens of YAML. The engine renders it immediately.

## Licence

MIT
