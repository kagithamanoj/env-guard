"""Validate parsed .env entries against a schema.

Checks, in order:

* missing required keys, and required keys set to an empty value
* unknown keys (a warning; a key the schema never mentions)
* format mismatches (int, float, bool, url, email, port, enum, regex)
* values that look like real secrets (a warning: do not commit them)
* values that look like unfilled placeholders (a warning)
* a file literally named ``.env`` that no nearby ``.gitignore`` lists
  (a warning: one stray ``git add .`` would commit it)

Warnings stay warnings unless the caller passes ``strict=True``, which
promotes them to errors.
"""

import math
import os
import re
from urllib.parse import urlparse

from envguard.parser import ParseError, parse_env
from envguard.schema import Schema

_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"sk-live-[A-Za-z0-9]{16,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
    re.compile(r"sq0atp-[A-Za-z0-9_-]{22}"),
]

_PLACEHOLDERS = {
    "changeme",
    "change-me",
    "change_me",
    "xxx",
    "xxxx",
    "todo",
    "placeholder",
    "your-api-key-here",
    "example",
    "dummy",
    "test",
    "none",
    "null",
    "replace-me",
    "replace_me",
}

_BOOL_VALUES = {"true", "false", "1", "0", "yes", "no", "on", "off"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Finding:
    """One validation result: level is 'error' or 'warning'."""

    def __init__(self, level, code, message, key=None, line=None):
        self.level = level
        self.code = code
        self.message = message
        self.key = key
        self.line = line

    def as_dict(self):
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "key": self.key,
            "line": self.line,
        }

    def __repr__(self):  # pragma: no cover - debugging aid
        return (
            f"Finding({self.level!r}, {self.code!r}, "
            f"{self.message!r}, key={self.key!r}, line={self.line!r})"
        )


def _entropy(value):
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum(
        (count / total) * math.log2(count / total) for count in counts.values()
    )


def looks_like_secret(value):
    """True when a value looks like a real credential, not a placeholder."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return True
    if len(value) >= 32:
        classes = sum(
            (
                any(char.islower() for char in value),
                any(char.isupper() for char in value),
                any(char.isdigit() for char in value),
                any(not char.isalnum() for char in value),
            )
        )
        if classes >= 3 and _entropy(value) > 4.0:
            return True
    return False


def _looks_like_placeholder(value):
    lowered = value.strip().lower()
    if lowered in _PLACEHOLDERS:
        return True
    return lowered.startswith("<") and lowered.endswith(">") and len(lowered) > 2


def check_format(value, spec):
    """Return an error message when value breaks the format, else None."""
    if spec == "int":
        try:
            int(value)
        except ValueError:
            return f"expected an integer, got {value!r}"
    elif spec == "float":
        try:
            float(value)
        except ValueError:
            return f"expected a number, got {value!r}"
    elif spec == "bool":
        if value.strip().lower() not in _BOOL_VALUES:
            return f"expected true/false (or yes/no, on/off, 1/0), got {value!r}"
    elif spec == "port":
        try:
            port = int(value)
        except ValueError:
            return f"expected a port number, got {value!r}"
        if not 1 <= port <= 65535:
            return f"expected a port between 1 and 65535, got {value!r}"
    elif spec == "url":
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return f"expected a URL with a scheme and host, got {value!r}"
    elif spec == "email":
        if not _EMAIL_RE.match(value):
            return f"expected an email address, got {value!r}"
    elif spec.startswith("enum:"):
        choices = spec[len("enum:"):].split(",")
        if value not in choices:
            return f"expected one of {', '.join(choices)}, got {value!r}"
    elif spec.startswith("regex:"):
        if not re.fullmatch(spec[len("regex:"):], value):
            return f"value {value!r} does not match {spec[len('regex:'):]!r}"
    return None


def _gitignore_lists(env_path):
    """True when a .gitignore next to the file, or in the cwd, names it."""
    name = os.path.basename(env_path)
    for directory in (os.path.dirname(os.path.abspath(env_path)), os.getcwd()):
        ignore_file = os.path.join(directory, ".gitignore")
        if not os.path.isfile(ignore_file):
            continue
        with open(ignore_file, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                if entry in (name, f"/{name}", f"*{name}", name + "/"):
                    return True
    return False


def validate_entries(entries, schema=None, filename=None, strict=False):
    """Validate parsed entries. Returns a list of Finding objects."""
    schema = schema or Schema()
    warn = "error" if strict else "warning"
    findings = []
    by_key = {}
    for entry in entries:
        by_key[entry.key] = entry
        if entry.key not in schema.known_keys():
            findings.append(
                Finding(
                    warn,
                    "unknown-key",
                    f"key {entry.key!r} is not in the schema",
                    key=entry.key,
                    line=entry.line,
                )
            )
        spec = schema.formats.get(entry.key)
        if spec is not None and entry.value != "":
            problem = check_format(entry.value, spec)
            if problem is not None:
                findings.append(
                    Finding(
                        "error",
                        "bad-format",
                        f"{entry.key}: {problem}",
                        key=entry.key,
                        line=entry.line,
                    )
                )
        if looks_like_secret(entry.value):
            findings.append(
                Finding(
                    warn,
                    "secret-value",
                    f"{entry.key} looks like a real secret; "
                    "do not commit this file",
                    key=entry.key,
                    line=entry.line,
                )
            )
        elif _looks_like_placeholder(entry.value):
            findings.append(
                Finding(
                    warn,
                    "placeholder-value",
                    f"{entry.key} still holds a placeholder value",
                    key=entry.key,
                    line=entry.line,
                )
            )
    for key in schema.required:
        if key not in by_key:
            findings.append(
                Finding("error", "missing-required", f"missing required key {key!r}", key=key)
            )
        elif by_key[key].value == "":
            findings.append(
                Finding(
                    "error",
                    "empty-required",
                    f"required key {key!r} is empty",
                    key=key,
                    line=by_key[key].line,
                )
            )
    if filename is not None and os.path.basename(filename) == ".env":
        if not _gitignore_lists(filename):
            findings.append(
                Finding(
                    warn,
                    "not-gitignored",
                    ".env is not listed in .gitignore; "
                    "one stray 'git add .' would commit it",
                )
            )
    return findings


def validate_file(path, schema=None, strict=False):
    """Parse and validate one .env file. Returns a list of Finding objects."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return [Finding("error", "unreadable", f"cannot read {path}: {exc}")]
    try:
        entries = parse_env(text)
    except ParseError as exc:
        return [
            Finding("error", "parse-error", exc.message, line=exc.line)
        ]
    return validate_entries(entries, schema=schema, filename=path, strict=strict)
