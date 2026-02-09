# Security Model

## Design Principle

The YAML Form Engine separates **form definition** (AI-generated, auditable YAML) from **form data** (user-entered, stays local). The AI's role ends at generating the YAML config. All captured data remains on the user's machine.

## Threat Model

### In Scope

| Threat | Mitigation |
|--------|-----------|
| **Arbitrary code in YAML** | `yaml.safe_load` only — no `!!python/object` tags, no code during parsing |
| **Expression injection** | Regex-based parser with function whitelist — no dynamic code evaluation |
| **Path traversal in data sources** | Reject `..` in paths, resolve symlinks, confine to form directory |
| **Exfiltration of form data** | Zero network calls from engine — no HTTP, no WebSocket, no telemetry |
| **Malicious YAML form definitions** | Schema validation rejects malformed configs before rendering |
| **Sensitive data in form state** | `.form-state/` is gitignored; state files are local JSON only |

### Out of Scope

| Area | Reason |
|------|--------|
| **Browser-side attacks (XSS)** | Streamlit handles HTML sanitisation; engine does not emit raw HTML |
| **Multi-user access control** | Engine runs locally for a single user; no authentication needed |
| **Encryption at rest** | Deferred to OS-level disk encryption (FileVault, BitLocker) |
| **Supply chain (pip packages)** | Standard Python dependency management; pin versions in production |

## Security Controls

### 1. Safe YAML Parsing

All YAML loading uses `yaml.safe_load`, which only instantiates basic Python types (dict, list, str, int, float, bool, None). No custom objects, no code instantiation.

### 2. Expression Evaluator

The expression language is deliberately limited:

**Allowed:**
- `count_where(step.field == value)` — count matching items
- `percent_where(step.field in [val1, val2])` — percentage matching
- `avg(step.field)` — average of numeric values
- `sum(step.field)`, `min(step.field)`, `max(step.field)` — aggregations
- `{step.field}` — template interpolation in strings

**Prohibited:**
- No arbitrary Python expressions
- No access to `builtins`, `os`, `sys`, `subprocess`
- No function calls beyond the whitelist
- No lambda or comprehension syntax
- No string concatenation tricks

**Implementation:** Regular expressions parse the expression into (function, step, field, operator, value) tuples. The function is looked up in a whitelist dict. Values are extracted from form responses by key. No string is ever passed to dynamic code evaluation.

### 3. Data Source Path Validation

```python
def validate_path(path, base_dir):
    # 1. Reject path traversal components
    if ".." in path.split(os.sep):
        raise DataSecurityError("Path traversal not allowed")

    # 2. Resolve to absolute path (follows symlinks)
    resolved = os.path.realpath(os.path.join(base_dir, path))

    # 3. Verify it's within the form's directory tree
    if not resolved.startswith(os.path.realpath(base_dir)):
        raise DataSecurityError("Path escapes form directory")

    # 4. Whitelist file extensions
    if not path.endswith((".yaml", ".yml", ".json")):
        raise DataSecurityError("Only YAML/JSON data files allowed")

    # 5. Must be a regular file (not dir, not device)
    if not os.path.isfile(resolved):
        raise DataSecurityError("File not found")
```

### 4. No Network Access

The engine makes **zero** network calls:
- No HTTP requests
- No WebSocket connections
- No DNS lookups
- No telemetry or analytics
- No auto-update checks

Streamlit itself binds to `localhost` by default. The `--server.headless true` flag disables the "open browser" prompt.

### 5. Local State Only

Form responses are saved to `.form-state/<form-id>.json`:
- Plain JSON files on the local filesystem
- Gitignored by default (`.gitignore` includes `.form-state/`)
- No database, no cloud storage, no shared state
- User can delete state files at any time

## For AI Agent Authors

When generating YAML form definitions:

1. **Never include executable content** — YAML is data, not code
2. **Use relative paths** for data sources — they resolve from the form file's directory
3. **Don't reference paths outside the project** — path validation will reject them
4. **Keep expressions simple** — use the documented functions only
5. **Test with schema validation** before deploying

## Audit Checklist

- [ ] All YAML loading uses `yaml.safe_load`
- [ ] No dynamic code evaluation anywhere in the codebase
- [ ] Expression evaluator only accepts whitelisted functions
- [ ] Data source paths are validated and confined
- [ ] No network imports (`requests`, `urllib`, `httpx`, `socket`)
- [ ] `.form-state/` is in `.gitignore`
- [ ] Form definitions contain no embedded scripts or HTML
