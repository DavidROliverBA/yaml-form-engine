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

# Install the CLI
pip install -e .

# Run a form
yfe forms/arch-review.yaml

# List all available forms
yfe list

# Generate a form from an MCP tool schema
yfe generate --schema-file tools/my-tool.json
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

### Custom Forms

| Form | Description | Launch |
|------|-------------|--------|
| `arch-review.yaml` | Architecture review checklist with 0-3 scoring | `yfe forms/arch-review.yaml` |
| `dpia-assessment.yaml` | Data Protection Impact Assessment questionnaire | `yfe forms/dpia-assessment.yaml` |
| `vendor-scorecard.yaml` | Vendor evaluation with weighted criteria | `yfe forms/vendor-scorecard.yaml` |

### MCP Tool Forms (Pre-Built)

Forms generated from MCP tool schemas. Fill in the form, get a validated JSON payload for the tool.

| Form | MCP Tool | Server | Launch |
|------|----------|--------|--------|
| `notion-create-page.yaml` | `API-post-page` | Notion (MCP_DOCKER) | `yfe forms/mcp/notion-create-page.yaml` |
| `notion-search.yaml` | `API-post-search` | Notion (MCP_DOCKER) | `yfe forms/mcp/notion-search.yaml` |
| `jira-create-issue.yaml` | `createJiraIssue` | Jira (Atlassian) | `yfe forms/mcp/jira-create-issue.yaml` |
| `jira-search.yaml` | `searchJiraIssuesUsingJql` | Jira (Atlassian) | `yfe forms/mcp/jira-search.yaml` |
| `confluence-create-page.yaml` | `createConfluencePage` | Confluence (Atlassian) | `yfe forms/mcp/confluence-create-page.yaml` |
| `confluence-search.yaml` | `searchConfluenceUsingCql` | Confluence (Atlassian) | `yfe forms/mcp/confluence-search.yaml` |
| `diagram-generate.yaml` | `generate_diagram` | Diagrams (MCP_DOCKER) | `yfe forms/mcp/diagram-generate.yaml` |
| `youtube-transcript.yaml` | `get_transcript` | YouTube (MCP_DOCKER) | `yfe forms/mcp/youtube-transcript.yaml` |

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
| `submit` | Build and display an MCP tool invocation payload |

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
| `cli.py` | CLI entry point (`yfe` command) with subcommands |
| `type_mapper.py` | Maps JSON Schema properties to YAML form field types |
| `mcp_introspect.py` | Parses MCP tool definitions into normalised schemas |
| `form_generator.py` | Generates complete YAML forms from tool schemas |
| `mcp_invoker.py` | Coerces form responses to typed JSON payloads |

## Auto-Save

Form state is automatically saved to `.form-state/<form-id>.json` after every interaction. Close the browser and reopen — your data is still there. The `.form-state/` directory is gitignored by default.

## MCP Form Generation

Generate GUI forms from any MCP tool's JSON Schema — no Python code needed.

### How It Works

```
MCP Tool Schema (JSON) ──> Generator ──> YAML Form Definition
                                                │
                                           User fills form
                                                │
                                           Submit step ──> Validated JSON Payload
```

The generator reads a tool's parameter schema and produces a YAML form with:
- **Input steps** for each parameter group (flat fields in one step, nested objects as separate steps)
- **A review step** showing tool metadata
- **A submit step** that builds a validated JSON payload, previews it, and offers copy/download

### CLI Usage

```bash
# Generate from a JSON schema file
yfe generate --schema-file tools/notion-create-page.json

# Generate from piped JSON (e.g., from Claude Code)
echo '{"name": "my-tool", ...}' | yfe generate --schema-stdin

# Specify output directory
yfe generate --schema-file tools/foo.json --output forms/custom/

# List all available forms (including generated ones)
yfe list

# Run a generated form
yfe run forms/mcp/notion-search.yaml
yfe forms/mcp/jira-create-issue.yaml    # shorthand (backwards compatible)
```

### Schema Input Formats

The generator accepts three schema formats:

**Format A — Full MCP tool definition:**
```json
{
  "name": "API-post-page",
  "server": "MCP_DOCKER",
  "description": "Create a page in Notion",
  "inputSchema": {
    "type": "object",
    "properties": { "title": { "type": "string" } },
    "required": ["title"]
  }
}
```

**Format B — Claude Code tool definition:**
```json
{
  "name": "mcp__MCP_DOCKER__API-post-search",
  "description": "Search Notion",
  "parameters": {
    "type": "object",
    "properties": { "query": { "type": "string" } },
    "required": ["query"]
  }
}
```

**Format C — Bare JSON Schema with metadata:**
```json
{
  "name": "create-issue",
  "server": "jira",
  "description": "Create a Jira issue",
  "properties": { "summary": { "type": "string" } },
  "required": ["summary"]
}
```

### Type Mapping Rules

The generator automatically maps JSON Schema types to the best form widget:

| JSON Schema | Constraints | Form Widget |
|-------------|-------------|-------------|
| `string` | plain | `text` |
| `string` | enum with 1-4 values | `radio` |
| `string` | enum with 5+ values | `select` |
| `string` | maxLength > 200 or name contains "description", "body", etc. | `textarea` |
| `number` / `integer` | no range, or range > 20 | `number` |
| `number` / `integer` | min + max with range <= 20 | `slider` |
| `boolean` | — | `checkbox` |
| `array` | items with enum | `multiselect` |
| `array` | items without enum | `textarea` (one item per line) |
| `object` | — | separate wizard step (recurse) |

Additional mappings:
- `required` in parent → `required: true` on field
- `default` → `default: <value>`
- `title` or `description` → `label`
- `minimum` / `maximum` → `min` / `max`
- `pattern` → `placeholder: "Format: <pattern>"`

### The Submit Step

Generated forms include a `submit` step that:

1. Collects responses from all previous steps
2. Coerces values to the correct JSON Schema types (strings → integers, booleans, etc.)
3. Reconstructs nested objects from step-based field groups
4. Displays a JSON payload preview
5. Offers "Copy Invocation" (formatted for Claude Code) and "Download Payload (JSON)"
6. Saves the payload to `.form-state/<form-id>-payload.json`

```yaml
steps:
  - id: submit
    title: "Submit"
    type: submit
    mcp:
      server: MCP_DOCKER
      tool: API-post-page
    confirm: true          # Show confirmation before displaying command
    show_payload: true     # Preview the JSON payload
```

**Security note:** The submit step does NOT execute MCP tools directly. It produces a validated payload for you (or Claude Code) to invoke. No network calls are made.

### Using with Claude Code

The typical workflow with Claude Code:

1. **Claude Code reads the tool schema** via ToolSearch
2. **Saves it to a JSON file** (or pipes it directly)
3. **Runs `yfe generate`** to produce the YAML form
4. **You open the form** in Streamlit and fill it in
5. **Copy the payload** from the submit step
6. **Claude Code invokes the MCP tool** with the payload

Or use the pre-built gallery forms in `forms/mcp/` — they're ready to run.

## Creating Your Own Forms

1. Copy an example from `forms/`
2. Edit the YAML — change fields, steps, data sources
3. Run: `yfe forms/your-form.yaml`

Or have an AI generate the YAML from a natural language description:

> "Create a YAML form definition for capturing incident post-mortem data.
> Include fields for incident title, severity, timeline, root cause,
> and action items. Use a 0-3 scoring system for impact assessment."

The AI writes ~300 tokens of YAML. The engine renders it immediately.

Or generate a form from any MCP tool:

```bash
yfe generate --schema-file tools/my-mcp-tool.json
yfe run forms/mcp/my-mcp-tool.yaml
```

## Licence

MIT
