"""env-guard: validate .env files against a schema."""

from envguard.parser import Entry, ParseError, parse_env
from envguard.schema import SchemaError, load_schema
from envguard.validate import Finding, validate_entries, validate_file

__all__ = [
    "Entry",
    "Finding",
    "ParseError",
    "SchemaError",
    "load_schema",
    "parse_env",
    "validate_entries",
    "validate_file",
]
