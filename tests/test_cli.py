"""CLI argument parsing tests for drought-severity-assessment."""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from conftest import mod as dr, SCRIPT


def run_cli(args, timeout=120):
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout,
    )


class TestCLIBasics:
    def test_help(self):
        r = run_cli(["--help"])
        assert r.returncode == 0
        assert "--bbox" in r.stdout
        assert "--synthetic" in r.stdout
        assert "--n-dates" in r.stdout

    def test_version(self):
        r = run_cli(["--version"])
        assert r.returncode == 0
        assert "1.0.0" in r.stdout

    def test_no_args_exit_2(self):
        """No arguments → UsageError → exit 2."""
        r = run_cli([])
        assert r.returncode == 2

    def test_unknown_arg_exit_2(self):
        """Unknown option → argparse error → exit 2."""
        r = run_cli(["--bbox", "116", "39", "117", "40", "--synthetic",
                     "--bogus-option", "x"])
        assert r.returncode == 2

    def test_bad_ndates_exit_2(self):
        """Non-integer --n-dates → argparse type error → exit 2."""
        r = run_cli(["--bbox", "116", "39", "117", "40", "--synthetic",
                     "--n-dates", "abc"])
        assert r.returncode == 2

    def test_input_file_not_found_exit_2(self):
        """Non-existent input file → UsageError → exit 2."""
        r = run_cli(["--input", "nonexistent.tif"])
        assert r.returncode == 2

    def test_synthetic_without_bbox_exit_2(self):
        """--synthetic without --bbox → UsageError → exit 2."""
        r = run_cli(["--synthetic"])
        assert r.returncode == 2


class TestCLIRun:
    def test_synthetic_run_ok(self, tmp_path):
        out = str(tmp_path / "out")
        r = run_cli(["--bbox", "116", "39", "117", "40", "--n-dates", "12",
                     "--synthetic", "--output-dir", out, "--quiet"])
        assert r.returncode == 0, r.stderr
        assert os.path.exists(os.path.join(out, "output-manifest.json"))
        assert os.path.exists(os.path.join(out, "drought_grade.tif"))
        assert os.path.exists(os.path.join(out, "spi.tif"))

    def test_bbox_only_auto_synthetic(self, tmp_path):
        """仅给 --bbox（无 --input）→ 自动走合成模式 → exit 0。"""
        out = str(tmp_path / "out2")
        r = run_cli(["--bbox", "121", "31", "122", "32", "--output-dir", out, "--quiet"])
        assert r.returncode == 0, r.stderr
        assert os.path.exists(os.path.join(out, "output-manifest.json"))
