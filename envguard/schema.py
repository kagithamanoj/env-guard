"""Load and check an env-guard schema file (JSON).

Schema shape:

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

Formats: int, float, bool, url, email, port, enum:a,b,c, regex:<pattern>.
``required`` and ``optional`` must not overlap, and every key named in
``formats`` must appear in one of the two lists.
"""

import json
import re

KNOWN_FORMATS = ("int", "float", "bool", "url", "email", "port")


class SchemaError(Exception):
    """The schema file is missing, invalid JSON, or inconsistent."""


class Schema:
    def __init__(self, required=(), optional=(), formats=None):
        self.required = list(required)
        self.optional = list(optional)
        self.formats = dict(formats or {})

    def known_keys(self):
        return set(self.required) | set(self.optional)


def _check_key_list(value, field):
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise SchemaError(f"schema field {field!r} must be a list of strings")
    return value


def _check_format(spec, key):
    if not isinstance(spec, str) or not spec:
        raise SchemaError(f"format for {key!r} must be a non-empty string")
    if spec in KNOWN_FORMATS:
        return
    if spec.startswith("enum:"):
        choices = spec[len("enum:"):].split(",")
        if not choices or any(not choice for choice in choices):
            raise SchemaError(f"format for {key!r} has an empty enum choice")
        return
    if spec.startswith("regex:"):
        try:
            re.compile(spec[len("regex:"):])
        except re.error as exc:
            raise SchemaError(f"format for {key!r} has a bad regex: {exc}")
        return
    raise SchemaError(f"unknown format {spec!r} for key {key!r}")


def load_schema(path):
    """Load a schema from a JSON file. Raises SchemaError on any problem."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise SchemaError(f"cannot read schema {path}: {exc}")
    except json.JSONDecodeError as exc:
        raise SchemaError(f"schema {path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise SchemaError("schema must be a JSON object")
    unknown = sorted(set(data) - {"required", "optional", "formats"})
    if unknown:
        raise SchemaError(f"unknown schema fields: {', '.join(unknown)}")
    required = _check_key_list(data.get("required", []), "required")
    optional = _check_key_list(data.get("optional", []), "optional")
    overlap = sorted(set(required) & set(optional))
    if overlap:
        raise SchemaError(
            f"keys in both required and optional: {', '.join(overlap)}"
        )
    formats = data.get("formats", {})
    if not isinstance(formats, dict):
        raise SchemaError("schema field 'formats' must be an object")
    known = set(required) | set(optional)
    for key in formats:
        if key not in known:
            raise SchemaError(
                f"format given for {key!r}, which is not required or optional"
            )
        _check_format(formats[key], key)
    return Schema(required, optional, formats)
