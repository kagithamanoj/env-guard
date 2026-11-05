"""Tests for the env-guard CLI."""

import json
import os
import subprocess
import sys

import pytest

from envguard.cli import main


def run_cli(tmp_path, env_text, schema=None, extra_args=(), cwd=None):
    env = tmp_path / "app.env"
    env.write_text(env_text)
    argv = list(extra_args) + [str(env)]
    if schema is not None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps(schema))
        argv = ["--schema", str(schema_path)] + argv
    import os

    old = os.getcwd()
    try:
        if cwd is not None:
            os.chdir(cwd)
        return main(argv)
    finally:
        os.chdir(old)


def test_cli_clean_exits_zero(tmp_path, capsys):
    code = run_cli(
        tmp_path,
        "A=1\n",
        schema={"required": ["A"]},
    )
    assert code == 0
    assert "ok: no problems found" in capsys.readouterr().out


def test_cli_missing_required_exits_one(tmp_path, capsys):
    code = run_cli(tmp_path, "B=1\n", schema={"required": ["A"]})
    assert code == 1
    assert "missing-required" in capsys.readouterr().out


def test_cli_strict_promotes_warning(tmp_path, capsys):
    code = run_cli(
        tmp_path, "A=1\nEXTRA=2\n", schema={"required": ["A"]}
    )
    assert code == 0
    code = run_cli(
        tmp_path,
        "A=1\nEXTRA=2\n",
        schema={"required": ["A"]},
        extra_args=["--strict"],
    )
    assert code == 1


def test_cli_json_output(tmp_path, capsys):
    code = run_cli(
        tmp_path,
        "B=1\n",
        schema={"required": ["A"]},
        extra_args=["--format", "json"],
    )
    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["errors"] == 1
    assert any(r["code"] == "missing-required" for r in out["results"])


def test_cli_missing_file_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope.env")]) == 2


def test_cli_bad_schema_exits_two(tmp_path, capsys):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{bad json")
    env = tmp_path / "app.env"
    env.write_text("A=1\n")
    assert main(["--schema", str(schema_path), str(env)]) == 2


def test_cli_discovers_schema_in_cwd(tmp_path, capsys):
    schema_path = tmp_path / ".env.schema.json"
    schema_path.write_text(json.dumps({"required": ["A"]}))
    env = tmp_path / "app.env"
    env.write_text("B=1\n")
    code = run_cli(tmp_path, "B=1\n", cwd=str(tmp_path))
    assert code == 1
    assert "missing-required" in capsys.readouterr().out


def test_cli_no_schema_runs_builtin_checks(tmp_path, capsys):
    code = run_cli(tmp_path, "TOKEN=ghp_" + "a" * 36 + "\n")
    assert code == 0
    assert "secret-value" in capsys.readouterr().out


def test_cli_as_script(tmp_path):
    """The installed entry point works end to end."""
    env = tmp_path / "app.env"
    env.write_text("A=1\n")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-m", "envguard.cli", str(env)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": project_root},
    )
    assert proc.returncode == 0
    assert "unknown-key" in proc.stdout
