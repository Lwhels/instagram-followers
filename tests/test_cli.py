"""Unit tests for CLI commands."""

import os
import subprocess
import sys


def test_cli_help():
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    result = subprocess.run(
        [sys.executable, "-m", "instagram_analyzer", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Instagram Follower Analyzer" in result.stdout


def test_cli_demo_command(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    db_file = tmp_path / "test_cli.db"
    result = subprocess.run(
        [sys.executable, "-m", "instagram_analyzer", "demo", "--db", str(db_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Loaded rich demo dataset" in result.stdout


def test_cli_compare_command(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    f_file = tmp_path / "f.html"
    fg_file = tmp_path / "fg.html"
    db_file = tmp_path / "cli_comp.db"

    f_file.write_text('<a href="https://instagram.com/alice">alice</a>')
    fg_file.write_text('<a href="https://instagram.com/alice">alice</a><a href="https://instagram.com/bob">bob</a>')

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "instagram_analyzer",
            "compare",
            str(f_file),
            str(fg_file),
            "--save-db",
            "--db",
            str(db_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "ANALYSIS SUMMARY" in result.stdout
    assert "Unreciprocated:     1" in result.stdout
    assert "@bob" in result.stdout
