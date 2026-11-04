"""Run the whole pipeline in order and stop at the first step that fails.

  1. load_raw     python source/pipeline/load_raw.py       (exits 1 if any file failed)
  2. dbt_build    dbt build                                (seeds, models and tests, in order)
  3. dbt_docs     dbt docs generate

`dbt build` runs each test straight after its model and skips everything downstream of a
failure, so a failing data test stops the marts from being built on top of bad data. The
runner then stops and exits non-zero, so a scheduler or CI job sees the failure. Every step
is safe to rerun: the loader skips unchanged files and dbt rebuilds from raw.

Usage:  python source/pipeline/run_pipeline.py
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

# requirements.txt pins every package but cannot pin Python itself, and the pinned versions
# were tested on 3.12 only. Refusing other versions keeps "a run next month" the same as today.
PYTHON_VERSION = (3, 12)

# The loader and dbt must use the same database file. profiles.yml's own default is a relative
# path that only works from inside the dbt folder, so every step gets the absolute path here
# unless GSS_DB_PATH is already set.
os.environ.setdefault("GSS_DB_PATH", str(ROOT / "source/data/warehouse/gss.duckdb"))

DBT = shutil.which("dbt") or "dbt"
DBT_FLAGS = ["--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")]

STEPS = [
    ("load_raw", [sys.executable, str(ROOT / "source/pipeline/load_raw.py")]),
    ("dbt_build", [DBT, "build", *DBT_FLAGS]),
    ("dbt_docs", [DBT, "docs", "generate", *DBT_FLAGS]),
]


def log(message):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} run_pipeline {message}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "pipeline.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run(steps):
    """Run steps in order; return 0 if all succeed, else the failing step's exit code."""
    for name, command in steps:
        log(f"step {name} started")
        started = time.monotonic()
        code = subprocess.run(command, cwd=ROOT).returncode
        seconds = time.monotonic() - started
        if code != 0:
            log(f"step {name} FAILED with exit code {code} after {seconds:.1f}s; "
                "later steps were not run")
            return code
        log(f"step {name} finished in {seconds:.1f}s")
    log("pipeline finished: all steps succeeded")
    return 0


if __name__ == "__main__":
    if sys.version_info[:2] != PYTHON_VERSION:
        sys.exit(f"Python {'.'.join(map(str, PYTHON_VERSION))} is required (found "
                 f"{sys.version.split()[0]}); see Setup in the README")
    sys.exit(run(STEPS))
