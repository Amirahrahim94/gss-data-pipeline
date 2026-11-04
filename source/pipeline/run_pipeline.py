"""Run the pipeline steps in order, stopping if a step fails.

1. load_raw: load the source files into the raw database tables.
2. dbt_build: load seeds, build models and run data tests with `dbt build`.
3. dbt_docs: generate the dbt documentation after a successful build.

If a step fails, the remaining steps are skipped. The script returns the
failed step's exit code so an automated job can detect the failure.
Within `dbt build`, failing tests can also prevent dependent models from running.

The pipeline can be rerun: the loader skips unchanged files, and dbt rebuilds
its outputs from the raw data. Step start times, durations and results are
printed to the terminal and appended to logs/pipeline.log, or to pipeline.log
in the directory set by GSS_LOG_DIR.

Usage: python source/pipeline/run_pipeline.py
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = Path(os.environ.get("GSS_LOG_DIR", ROOT / "logs"))

# Require Python 3.12, the version used to test this project.
# requirements.txt fixes package versions but does not set the Python version.
PYTHON_VERSION = (3, 12)

# Give the loader and dbt the same database path.
# Use an absolute default path so it works from any working directory.
# Keep GSS_DB_PATH if the user has already set it.
os.environ.setdefault("GSS_DB_PATH", str(ROOT / "source/data/warehouse/gss.duckdb"))

# Find the installed dbt command and point it to this project and its connection settings.
DBT = shutil.which("dbt") or "dbt"
DBT_FLAGS = ["--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")]

# Define the commands in the order they must run.
STEPS = [
    ("load_raw", [sys.executable, str(ROOT / "source/pipeline/load_raw.py")]),
    ("dbt_build", [DBT, "build", *DBT_FLAGS]),
    ("dbt_docs", [DBT, "docs", "generate", *DBT_FLAGS]),
]


def log(message):
    """Print a timestamped message and append it to the pipeline log file."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} run_pipeline {message}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "pipeline.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run(steps):
    """Run each command in order. Return 0 on success or stop with the failed command's exit code."""
    for name, command in steps:
        log(f"step {name} started")
        # Measure elapsed time with a clock that is unaffected by system time changes.
        started = time.monotonic()
        # Wait for the command to finish and capture its exit code (0 means success).
        code = subprocess.run(command, cwd=ROOT).returncode
        seconds = time.monotonic() - started
        # Stop immediately on failure so later pipeline steps do not run.
        if code != 0:
            log(f"step {name} FAILED with exit code {code} after {seconds:.1f}s; "
                "later steps were not run")
            return code
        log(f"step {name} finished in {seconds:.1f}s")
    log("pipeline finished: all steps succeeded")
    return 0


# When run directly, check the Python version before starting the pipeline.
if __name__ == "__main__":
    if sys.version_info[:2] != PYTHON_VERSION:
        sys.exit(f"Python {'.'.join(map(str, PYTHON_VERSION))} is required (found "
                 f"{sys.version.split()[0]}); see Setup in the README")
    sys.exit(run(STEPS))
