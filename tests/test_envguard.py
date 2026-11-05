"""Tests for env-guard parsing, schemas, formats, and validation."""

import json

import pytest

from envguard.parser import ParseError, parse_env
from envguard.schema import Schema, SchemaError, load_schema
from envguard.validate import (
    check_format,
    looks_like_secret,
    validate_entries,
    validate_file,
)
from envguard.parser import Entry


def entries(text):
    return parse_env(text)


def codes(findings):
    return [(f.level, f.code) for f in findings]


# --- parser ---


def test_parse_basic_and_export_and_comments():
    got = entries("# heading\n\nexport FOO=bar\nBAZ=qux # trailing\n")
    assert [(e.key, e.value) for e in got] == [("FOO", "bar"), ("BAZ", "qux")]


def test_parse_quoted_values():
    got = entries('A="a b c"\nB=\'x y\'\nC="tab\\there"\nD=""\n')
    assert [(e.key, e.value) for e in got] == [
        ("A", "a b c"),
        ("B", "x y"),
        ("C", "tab\there"),
        ("D", ""),
    ]


def test_parse_empty_value_and_hash_inside_quotes():
    got = entries('A=\nB="keep # this"\n')
    assert [(e.key, e.value) for e in got] == [("A", ""), ("B", "keep # this")]


def test_parse_line_numbers():
    got = entries("\n\nKEY=value\n")
    assert got[0].line == 3


def test_parse_missing_equals():
    with pytest.raises(ParseError):
        entries("NOT_A_PAIR\n")


def test_parse_bad_key():
    with pytest.raises(ParseError):
        entries("1BAD=value\n")


def test_parse_duplicate_key():
    with pytest.raises(ParseError) as excinfo:
        entries("A=1\nA=2\n")
    assert "duplicate" in str(excinfo.value)


def test_parse_unterminated_quote():
    with pytest.raises(ParseError):
        entries('A="oops\n')


# --- schema ---


def test_load_schema(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(
        json.dumps(
            {
                "required": ["URL"],
                "optional": ["PORT"],
                "formats": {"URL": "url", "PORT": "port"},
            }
        )
    )
    schema = load_schema(str(path))
    assert schema.required == ["URL"]
    assert schema.formats == {"URL": "url", "PORT": "port"}


def test_load_schema_missing_file():
    with pytest.raises(SchemaError):
        load_schema("/nonexistent/schema.json")


def test_load_schema_bad_json(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text("{not json")
    with pytest.raises(SchemaError):
        load_schema(str(path))


def test_load_schema_overlap_real(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps({"required": ["A"], "optional": ["A"]}))
    with pytest.raises(SchemaError):
        load_schema(str(path))


def test_load_schema_format_for_unknown_key(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps({"required": ["A"], "formats": {"B": "int"}}))
    with pytest.raises(SchemaError):
        load_schema(str(path))


def test_load_schema_bad_format(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps({"required": ["A"], "formats": {"A": "nope"}}))
    with pytest.raises(SchemaError):
        load_schema(str(path))


def test_load_schema_bad_regex(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(
        json.dumps({"required": ["A"], "formats": {"A": "regex:([bad"}})
    )
    with pytest.raises(SchemaError):
        load_schema(str(path))


# --- formats ---


@pytest.mark.parametrize(
    "spec,value,ok",
    [
        ("int", "42", True),
        ("int", "-3", True),
        ("int", "4.5", False),
        ("int", "abc", False),
        ("float", "4.5", True),
        ("float", "42", True),
        ("float", "abc", False),
        ("bool", "true", True),
        ("bool", "YES", True),
        ("bool", "0", True),
        ("bool", "maybe", False),
        ("port", "8000", True),
        ("port", "0", False),
        ("port", "65536", False),
        ("port", "abc", False),
        ("url", "https://example.com/x", True),
        ("url", "http://localhost:8000", True),
        ("url", "postgres://user:pass@localhost:5432/app", True),
        ("url", "example.com", False),
        ("url", "http://", False),
        ("email", "ops@example.com", True),
        ("email", "not-an-email", False),
        ("email", "a@b", False),
        ("enum:DEBUG,INFO", "DEBUG", True),
        ("enum:DEBUG,INFO", "TRACE", False),
        ("regex:^sk-[0-9]+$", "sk-123", True),
        ("regex:^sk-[0-9]+$", "sk-abc", False),
    ],
)
def test_check_format(spec, value, ok):
    assert (check_format(value, spec) is None) == ok


# --- secrets and placeholders ---


def test_secret_patterns():
    assert looks_like_secret("AKIAIOSFODNN7EXAMPLE")
    assert looks_like_secret("ghp_" + "a" * 36)
    assert looks_like_secret("sk-live-" + "b" * 24)
    assert looks_like_secret("-----BEGIN RSA PRIVATE KEY-----")
    assert not looks_like_secret("sk-0123456789abcdef")
    assert not looks_like_secret("postgres://user:pass@localhost/db")


def test_high_entropy_secret():
    assert looks_like_secret("Xk9$mQ2vL8#wZ4pR7&tY1uI6oP3aS5dF")
    assert not looks_like_secret("all-lowercase-words-here")


# --- validation ---


def test_clean_file_passes():
    schema = Schema(
        required=["DATABASE_URL"],
        optional=["PORT"],
        formats={"DATABASE_URL": "url", "PORT": "port"},
    )
    findings = validate_entries(
        entries("DATABASE_URL=https://db.example.com\nPORT=5432\n"),
        schema,
        filename="/tmp/app.env",
    )
    assert findings == []


def test_missing_and_empty_required():
    schema = Schema(required=["A", "B"])
    findings = validate_entries(entries("A=\n"), schema)
    assert ("error", "missing-required") in codes(findings)
    assert ("error", "empty-required") in codes(findings)


def test_unknown_key_is_warning_and_strict_promotes():
    schema = Schema(required=["A"])
    findings = validate_entries(entries("A=1\nSURPRISE=2\n"), schema)
    assert ("warning", "unknown-key") in codes(findings)
    strict = validate_entries(
        entries("A=1\nSURPRISE=2\n"), schema, strict=True
    )
    assert ("error", "unknown-key") in codes(strict)


def test_bad_format_is_error():
    schema = Schema(required=["PORT"], formats={"PORT": "port"})
    findings = validate_entries(entries("PORT=banana\n"), schema)
    assert ("error", "bad-format") in codes(findings)


def test_secret_value_warns():
    schema = Schema(required=["TOKEN"])
    findings = validate_entries(
        entries("TOKEN=ghp_" + "a" * 36 + "\n"), schema
    )
    assert ("warning", "secret-value") in codes(findings)


def test_placeholder_warns():
    schema = Schema(required=["API_KEY"])
    findings = validate_entries(entries("API_KEY=changeme\n"), schema)
    assert ("warning", "placeholder-value") in codes(findings)


def test_dotenv_without_gitignore_warns(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    findings = validate_file(str(env), Schema(required=["A"]))
    assert ("warning", "not-gitignored") in codes(findings)


def test_dotenv_with_gitignore_passes(tmp_path):
    (tmp_path / ".gitignore").write_text(".env\n")
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    findings = validate_file(str(env), Schema(required=["A"]))
    assert ("warning", "not-gitignored") not in codes(findings)


def test_validate_file_parse_error(tmp_path):
    env = tmp_path / "bad.env"
    env.write_text("NO_EQUALS_HERE\n")
    findings = validate_file(str(env))
    assert ("error", "parse-error") in codes(findings)


def test_validate_file_missing(tmp_path):
    findings = validate_file(str(tmp_path / "nope.env"))
    assert ("error", "unreadable") in codes(findings)
