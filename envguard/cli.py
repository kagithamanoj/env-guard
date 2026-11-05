"""Command line interface for env-guard.

Usage:

    env-guard [--schema schema.json] [--strict] [--format text|json] FILE...

The schema is found, in order, from ``--schema``, then ``.env.schema.json``,
``env-guard.json``, or ``.envguard.json`` in the working directory. With no
schema file, only the built-in checks run: parse errors, duplicate keys,
secret-looking values, placeholders, and the .gitignore check for files
named ``.env``.

Exit code is 0 when clean, 1 when findings are errors (or warnings under
``--strict``), and 2 on usage errors.
"""

import argparse
import json
import os
import sys

from envguard.schema import SchemaError, load_schema
from envguard.validate import validate_file

SCHEMA_CANDIDATES = (".env.schema.json", "env-guard.json", ".envguard.json")


def find_schema(explicit):
    if explicit:
        return explicit
    for name in SCHEMA_CANDIDATES:
        if os.path.isfile(name):
            return name
    return None


def render_text(results):
    lines = []
    for path, findings in results:
        for finding in findings:
            where = path
            if finding.line is not None:
                where += f":{finding.line}"
            lines.append(f"{where}: {finding.level} [{finding.code}] {finding.message}")
    errors = sum(
        1 for _, findings in results for f in findings if f.level == "error"
    )
    warnings = sum(
        1 for _, findings in results for f in findings if f.level == "warning"
    )
    if not errors and not warnings:
        lines.append("ok: no problems found")
    else:
        lines.append(f"{errors} error(s), {warnings} warning(s)")
    return "\n".join(lines) + "\n"


def render_json(results):
    docs = []
    errors = warnings = 0
    for path, findings in results:
        for finding in findings:
            if finding.level == "error":
                errors += 1
            else:
                warnings += 1
            doc = finding.as_dict()
            doc["file"] = path
            docs.append(doc)
    return (
        json.dumps(
            {
                "results": docs,
                "summary": {
                    "files": len(results),
                    "errors": errors,
                    "warnings": warnings,
                },
            },
            indent=2,
        )
        + "\n"
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="env-guard",
        description="Validate .env files against a schema.",
    )
    parser.add_argument("files", nargs="+", help=".env file(s) to validate")
    parser.add_argument(
        "--schema", help="schema JSON file (default: auto-discover in cwd)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    schema_path = find_schema(args.schema)
    schema = None
    if schema_path is not None:
        try:
            schema = load_schema(schema_path)
        except SchemaError as exc:
            print(f"env-guard: {exc}", file=sys.stderr)
            return 2
    results = []
    for path in args.files:
        if not os.path.isfile(path):
            print(f"env-guard: no such file: {path}", file=sys.stderr)
            return 2
        results.append((path, validate_file(path, schema, strict=args.strict)))
    if args.format == "json":
        sys.stdout.write(render_json(results))
    else:
        sys.stdout.write(render_text(results))
    errors = sum(
        1 for _, findings in results for f in findings if f.level == "error"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
