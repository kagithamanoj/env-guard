"""Parse .env files into key/value entries.

Supported syntax, one entry per line:

    KEY=value
    export KEY=value
    KEY="double quoted value"
    KEY='single quoted value'
    # a comment
    KEY=value # trailing comment (unquoted values only)

Blank lines and full-line comments are skipped. A line without ``=`` is
a parse error, as is a duplicate key.
"""

import re

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "'": "'",
}


class ParseError(Exception):
    """One malformed line in a .env file."""

    def __init__(self, line, message):
        super().__init__(f"line {line}: {message}")
        self.line = line
        self.message = message


class Entry:
    """One parsed KEY=value pair."""

    def __init__(self, key, value, line):
        self.key = key
        self.value = value
        self.line = line

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Entry({self.key!r}, {self.value!r}, line={self.line})"


def _unquote(raw, line):
    """Strip quotes from a value, handling escapes in double quotes."""
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        body = raw[1:-1]
        out = []
        i = 0
        while i < len(body):
            char = body[i]
            if char == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append(_ESCAPES.get(nxt, nxt))
                i += 2
            else:
                out.append(char)
                i += 1
        return "".join(out)
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1]
    if raw[:1] in ('"', "'"):
        raise ParseError(line, "unterminated quote in value")
    return raw


def _strip_inline_comment(raw):
    """Remove a trailing `` # comment`` from an unquoted value."""
    idx = raw.find(" #")
    if idx != -1:
        return raw[:idx].rstrip()
    return raw


def parse_env(text):
    """Parse .env text.

    Returns a list of Entry objects. Raises ParseError on the first
    malformed line (missing ``=``, bad key, duplicate key, bad quotes).
    """
    entries = []
    seen = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            raise ParseError(lineno, "line has no '='")
        key, _, raw_value = line.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ParseError(lineno, f"invalid key {key!r}")
        if key in seen:
            raise ParseError(
                lineno, f"duplicate key {key!r} (first set on line {seen[key]})"
            )
        seen[key] = lineno
        raw_value = raw_value.strip()
        if raw_value[:1] in ('"', "'"):
            value = _unquote(raw_value, lineno)
        else:
            value = _strip_inline_comment(raw_value)
        entries.append(Entry(key, value, lineno))
    return entries
