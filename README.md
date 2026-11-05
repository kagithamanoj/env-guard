# env-guard

Validate `.env` files against a schema before they bite you: required keys,
value formats, and a check that no real secret is sitting in a file about
to be committed.

## Install

```bash
pip install env-guard
```

Or from source:

```bash
pip install -e .
```

## Use

```bash
env-guard .env
env-guard --schema .env.schema.json .env .env.local
env-guard --strict --format json .env
```

Exit code is 0 when clean, 1 when findings are errors (or warnings under
`--strict`), and 2 on usage errors such as a missing file or bad schema.

## Schema

A JSON file describing the keys a project needs:

```json
{
  "required": ["DATABASE_URL", "API_KEY"],
  "optional": ["LOG_LEVEL", "PORT"],
  "formats": {
    "DATABASE_URL": "url",
    "PORT": "port",
    "LOG_LEVEL": "enum:DEBUG,INFO,WARNING,ERROR",
    "ADMIN_EMAIL": "email",
    "API_KEY": "regex:^sk-[A-Za-z0-9]{16,}$"
  }
}
```

Formats: `int`, `float`, `bool`, `url`, `email`, `port`, `enum:a,b,c`,
`regex:<pattern>`. A key named in `formats` must be listed as required or
optional.

When no `--schema` is given, env-guard looks for `.env.schema.json`,
`env-guard.json`, or `.envguard.json` in the working directory. With no
schema at all it still runs the built-in checks.

## What it checks

| Check | Level | Meaning |
| --- | --- | --- |
| `parse-error` | error | A line has no `=`, a bad key, a duplicate key, or bad quotes |
| `missing-required` | error | A required key is absent |
| `empty-required` | error | A required key is set but empty |
| `bad-format` | error | A value does not match its schema format |
| `unknown-key` | warning | A key the schema never mentions |
| `secret-value` | warning | A value looks like a real credential (AWS key, GitHub token, live Stripe key, private key, or a long high-entropy token) |
| `placeholder-value` | warning | A value is still `changeme`, `xxx`, `<...>` or similar |
| `not-gitignored` | warning | A file named `.env` is not listed in any nearby `.gitignore` |
| `unreadable` | error | The file cannot be read |

`--strict` promotes every warning to an error, which is what you want in
CI and in the pre-commit hook.

## Pre-commit hook

Add this to `.pre-commit-config.yaml` in any repo:

```yaml
repos:
  - repo: https://github.com/kagithamanoj/env-guard
    rev: v0.1.0
    hooks:
      - id: env-guard
```

The hook validates every staged `.env` file against the schema it finds
in the repo, with `--strict` on. A staged file holding a real-looking
secret fails the commit, which is the point: the secret never reaches
the remote.

## Library use

```python
from envguard import load_schema, validate_file

schema = load_schema(".env.schema.json")
for finding in validate_file(".env", schema, strict=True):
    print(finding.level, finding.code, finding.message)
```

## License

MIT
