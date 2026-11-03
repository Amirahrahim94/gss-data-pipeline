# GSS survey data pipeline

A local Python, DuckDB and dbt project analysing GSS survey data,
with a focus on religiosity and media consumption.

## Current status

Raw-data profiling and ingestion are implemented and tested.
dbt transformations, analytical queries and orchestration are pending.

## Data source

General Social Survey (GSS), produced by NORC at the University of Chicago. Extracts were
made with the NORC GSS Data Explorer (https://gssdataexplorer.norc.org).

*Citation: replace this line with the exact NORC citation text from the brief or the NORC site.*

*How the extracts were made (variables and Data Explorer steps): to be added.*

## Input data

| Extract | File | Survey years | Source records |
|---|---|---|---:|
| Cut A | `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 |
| Cut B | `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 |

The extracts contain 11,107 source records, including 2,348 shared
respondent-years, giving 8,759 distinct respondent-years. Shared respondent-years have
identical answers in both extracts.

Raw retains one record per respondent-year per extract.
The planned downstream models resolve the overlap.

The files are named `.json` but are Python literals (single quotes). The reader handles both.
They are kept unchanged under `source/data/raw/`.

## Repository map

| Path | Purpose |
|---|---|
| `source/data/raw/` | The original extracts, never edited |
| `source/config/extract_config.json` | Settings shared by the profiler and the loader |
| `source/pipeline/extract_reader.py` | Shared reader and validation |
| `source/pipeline/profile_extracts.py` | Data profile (writes `docs/data_profile_*`) |
| `source/pipeline/load_raw.py` | Loads the extracts into DuckDB (`raw` schema) |
| `source/tests/` | Loader and naming tests |
| `docs/` | Design note, naming conventions, data profile |
| `dbt/`, `report/` | Pending |

## Setup and run (Windows, PowerShell)

Requires Python 3.12 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

From the repository root, with the environment active:

```powershell
python source/pipeline/profile_extracts.py   # writes docs/data_profile_summary.md and .csv
python source/pipeline/load_raw.py           # loads the extracts into DuckDB
python -m unittest discover -s source/tests -v
```

Running the loader twice is safe: unchanged files are verified and skipped. Each file loads
in its own transaction, so a bad file is rejected without touching the others, and the run
exits with status 1 if any file failed. To apply a column change in the source, delete the
database file and load again.

| Setting | Meaning | Default |
|---|---|---|
| `GSS_DB_PATH` | DuckDB file | `source/data/warehouse/gss.duckdb` |
| `GSS_LOG_DIR` | Log folder | `logs/` |

Data-specific settings (file pattern, key columns, record list name) are in
`source/config/extract_config.json`, so another source of the same shape needs a config
change, not a code change. The repository holds no secrets.

## Verification

### Initial load

Verified locally on Windows on 3 November 2026 (Python 3.12.10, DuckDB).

- Run ID: `20261103T134352-3fbd79`
- Both extracts loaded successfully.
- Total runtime: 2.2 seconds (the first version, which inserted row by row, took about 14).
- Shared respondent-years: 2,348.
- Shared respondent-years with conflicting answers: 0.
- Failed files: 0.

### Safe rerun

Verified by the automated test `test_running_twice_changes_nothing`. A manual rerun of the
loader against the same database should report both extracts as skipped.
*Record the run ID of a manual rerun here.*

### Automated checks

```powershell
python -m unittest discover -s source/tests -v
```

Local test result: 41 tests passed in 48 seconds (3 November 2026, Windows).

The tests cover reruns, loading in either order, overlap agreement, rollback, malformed
input, value preservation (nulls, empty text, the text `None`, special characters) and audit
evidence.

## Operational evidence

The loader appends run IDs, timings, counts and errors to `logs/pipeline.log`.

The DuckDB table `raw.load_log` records each attempted file load,
including its checksum, status, counts and any error.
Failure records are written after rollback. `raw.extract_metadata` keeps the export's own
variable and code metadata.

Generated logs, temporary files and the local database are excluded
from version control.

## Design

See [the design note](docs/design_note.md) and [naming conventions](docs/naming_conventions.md).

## Limitations and further work

To be updated as the remaining work is completed.

## Time spent

Approximately [fill in actual time] hours.

With more time, I would [describe the highest-priority remaining work].
