# GSS data pipeline: religiosity and media consumption

A local Python and dbt pipeline over two extracts of the General Social Survey (GSS),
focused on religiosity and media consumption alongside employment and demographics.
Raw-data profiling and DuckDB ingestion are implemented. The planned dbt models and SQL
will answer the six analytical questions in the assignment.

**Status:** the profiler, the raw loader and their tests are built and tested (Windows,
Python 3.12, DuckDB). The dbt models, analytical SQL, orchestration and report are still to
come; the sections marked *to come* are placeholders.

## Data source

General Social Survey (GSS), produced by NORC at the University of Chicago. Extracts were
made with the NORC GSS Data Explorer (https://gssdataexplorer.norc.org). Please cite NORC
when using this data.

*Citation: replace this line with the exact citation text from the NORC site or the brief.*

| extract | years | records |
|---|---|---:|
| `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 |
| `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 |

The extracts contain 11,107 source records. They share 2,348 respondent-years (identical
answers), giving 8,759 distinct respondent-years. Raw retains one row per respondent-year
per extract; resolving the overlap into one respondent-year belongs to the planned
downstream models. The files are named `.json` but are Python literals; the reader handles
both. They are kept unchanged under `source/data/raw/`.

*How to reproduce the extracts: to come (the variable list and the Data Explorer steps).*

## Repository map

| path | purpose |
|---|---|
| `source/data/raw/` | The original extracts, never edited |
| `source/config/extract_config.json` | Settings shared by the profiler and the loader |
| `source/pipeline/extract_reader.py` | Shared reader and validation |
| `source/pipeline/profile_extracts.py` | Data profile (writes `docs/data_profile_*`) |
| `source/pipeline/load_raw.py` | Loads the extracts into DuckDB (`raw` schema) |
| `source/tests/` | Loader and naming tests |
| `docs/` | Design note, naming conventions, data profile and ingestion verification |
| `dbt/` | *to come* |
| `report/` | *to come* |

## Setup (Windows, PowerShell)

Requires Python 3.12 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Run

From the repository root, with the environment active:

```powershell
python source/pipeline/profile_extracts.py   # writes docs/data_profile_summary.md and docs/data_profile_detail.csv
python source/pipeline/load_raw.py           # loads the extracts into DuckDB
python -m unittest discover -s source/tests -v
```

Running the loader twice is safe: unchanged files are verified and skipped. Each file loads
in its own transaction, so a bad file is rejected without touching the others. The run
exits with status 1 if any file failed.

### Settings

| setting | meaning | default |
|---|---|---|
| `GSS_DB_PATH` | DuckDB file | `source/data/warehouse/gss.duckdb` |
| `GSS_LOG_DIR` | log folder | `logs/` |

Data-specific settings (file pattern, key columns, record list name) are in
`source/config/extract_config.json`. Another source with the same shape needs a config
change, not a code change. Local-file loading needs no credentials. Any credentials added
for future sources belong in environment variables or an untracked `.env` file, never in
committed configuration.

## Where to look when something goes wrong

- `logs/pipeline.log`: one line per step, with a run id and per-step timings.
- `raw.load_log` in the database: one row per file per run (loaded, skipped or failed, with
  the reason).
- `raw.extract_metadata`: the export's own variable and code metadata.

To apply a deliberate column change, preserve the existing database and rebuild all
extracts into a new database path with `--db`. Verify the rebuild before switching any
downstream consumers to it.

## Verification

The loader validates overlapping records, supports safe reruns and records failures.
Run the test command above to check its behaviour. Detailed results and evidence
locations are in [ingestion verification](docs/ingestion_verification.md).

## dbt models, analysis and orchestration

*To come.*
