# GSS data pipeline: religiosity and media consumption

A local Python, DuckDB and dbt pipeline over two extracts of the General Social Survey (GSS),
focused on religiosity and media consumption alongside employment and demographics. It loads
the extracts safely, models them with dbt, and answers six analytical questions in SQL.

**Status:** loading, modelling, analytical SQL and orchestration are built and tested
(Windows, Python 3.12, DuckDB). The report is still to be added in `report/`.

## Data source

General Social Survey (GSS), produced by NORC at the University of Chicago. Extracts were
made with the NORC GSS Data Explorer (https://gssdataexplorer.norc.org). Please cite NORC
when using this data.

*Citation: replace this line with the exact citation text from the NORC site or the brief.*

| extract | years | records |
|---|---|---:|
| `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 |
| `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 |

The extracts contain 11,107 source records. They share 2,348 respondent-years (all of the
2018 wave, with identical answers), giving 8,759 distinct respondent-years. Raw keeps one
row per respondent-year per extract; staging keeps each respondent-year once. The files are
named `.json` but are Python literals; the reader handles both. They are kept unchanged
under `source/data/raw/`.

*How to reproduce the extracts: to be added (the variable list and the Data Explorer steps).*

## Repository map

| path | purpose |
|---|---|
| `source/data/raw/` | The original extracts, never edited |
| `source/config/extract_config.json` | Settings shared by the profiler and the loader |
| `source/pipeline/extract_reader.py` | Shared reader and validation |
| `source/pipeline/profile_extracts.py` | Data profile (writes `docs/data_profile_*`) |
| `source/pipeline/load_raw.py` | Loads the extracts into DuckDB (`raw` schema) |
| `source/pipeline/build_reference_seeds.py` | Rebuilds the `dbt/seeds` code metadata from the extracts |
| `source/pipeline/run_pipeline.py` | Runs load, dbt build and dbt docs in order |
| `source/tests/` | Loader tests |
| `dbt/models/` | `staging/` (views), `intermediate/` (views), `marts/` (tables) |
| `dbt/seeds/` | `ref_variables` and `ref_codes`: what every code means and what kind of value it is |
| `dbt/tests/` | Singular data tests (`assert_*`) |
| `dbt/analyses/` | The six analytical queries (`q1_` to `q6_`) and `overlap_audit` |
| `docs/` | Design note, naming conventions, data profile, ingestion verification |
| `report/` | The report (to be added) |

## Setup (Windows, PowerShell)

Requires Python 3.12 or later. Dependencies are pinned in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Run

From the repository root, with the environment active:

```powershell
python source/pipeline/run_pipeline.py
```

This runs three steps in order and stops at the first failure (exit code non-zero):

1. `load_raw.py` loads the extracts into the `raw` schema.
2. `dbt build` loads the seeds, builds each model and runs its tests, in dependency order.
3. `dbt docs generate` writes the documentation.

To browse the documentation: `dbt docs serve --project-dir dbt --profiles-dir dbt`.

Other commands:

```powershell
python source/pipeline/profile_extracts.py          # data profile -> docs/
python -m unittest discover -s source/tests -v      # loader tests
```

To see an analytical query's result, from the `dbt` folder:
`dbt show --select q1_prayer_by_religion_raised --profiles-dir .`

### Settings

| setting | meaning | default |
|---|---|---|
| `GSS_DB_PATH` | DuckDB file, used by the loader and dbt | `source/data/warehouse/gss.duckdb` |
| `GSS_LOG_DIR` | log folder | `logs/` |

Data-specific settings are in `source/config/extract_config.json` (file pattern, key
columns, record list name) and `dbt/dbt_project.yml` (the answer variables). Nothing secret
is needed or committed: loading local files needs no credentials. A new user sets nothing
unless they want other paths.

## How the pipeline behaves

- **What triggers a run:** a person or scheduler runs `run_pipeline.py`. At this scale a
  single command is enough; a scheduler such as cron or Task Scheduler would call the same one.
- **A new extract:** drop the file in `source/data/raw/` matching the config pattern and rerun.
  The loader skips files that are unchanged and verified, and loads only the new one in its
  own transaction. dbt then rebuilds from raw, because the models are small views and tables.
- **A failed run:** the runner exits non-zero and `logs/pipeline.log` names the step. Every
  step is safe to rerun. A bad file fails alone and the other files still load.
- **A failing data test:** `dbt build` skips every model downstream of it and the runner
  stops, so the marts are never built on data that failed a check.

## Where to look when something goes wrong

- `logs/pipeline.log`: one line per step, with a run id and per-step timings.
- `raw.load_log` in the database: one row per file per run (loaded, skipped or failed, with
  the reason).
- `raw.extract_metadata`: the export's own variable and code metadata.

To apply a deliberate column change, rebuild all extracts into a new database path with
`--db`, then check the rebuild before switching to it.

## Verification

The loader validates overlapping records, supports safe reruns and records failures; dbt
tests check each layer. Detailed results and evidence locations are in
[ingestion verification](docs/ingestion_verification.md).

## Design

See [the design note](docs/design_note.md) and [naming conventions](docs/naming_conventions.md).

## Limitations and further work

*To be completed with the report.*

## Time spent

Approximately [fill in actual time] hours.
