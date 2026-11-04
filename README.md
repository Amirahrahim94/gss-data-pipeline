# GSS data pipeline: religiosity and media consumption

A local Python, DuckDB and dbt pipeline over two extracts of the General Social Survey (GSS),
focused on religiosity and media consumption alongside employment and demographics. It loads
the extracts safely, models them with dbt, and answers six analytical questions in SQL.

**Status:** loading, modelling, analytical SQL and orchestration are built and tested (in
Docker, and locally on Windows). The report is in [`report/report.md`](report/report.md).

## Data source

The General Social Survey (GSS) is a project of the independent research organization NORC
at the University of Chicago, with principal funding from the National Science Foundation.
The extracts were made with the GSS Data Explorer (https://gssdataexplorer.norc.org).

Citation, as given in the Data Explorer's
[terms and conditions](https://gssdataexplorer.norc.org/terms_and_conditions):

> Davern, Michael; Bautista, Rene; Freese, Jeremy; Herd, Pamela; and Morgan, Stephen L;,
> General Social Surveys, 1972-2024 [machine-readable data file] /Principal Investigator,
> Smith, Tom W.; Co-Principal Investigators, Rene Bautista, Jeremy Freese, Pamela Herd, and
> Stephen L. Morgan; Sponsored by National Science Foundation. --NORC ed.-- Chicago: NORC,
> 2025: NORC at the University of Chicago [producer and distributor]. Data accessed from the
> GSS Data Explorer website at gssdataexplorer.norc.org.

| extract | years | records |
|---|---|---:|
| `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 |
| `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 |

The extracts contain 11,107 source records. They share 2,348 respondent-years (all of the
2018 wave, with identical answers), giving 8,759 distinct respondent-years. Raw keeps one
row per respondent-year per extract; staging keeps each respondent-year once. The files are
named `.json` but are Python literals; the reader handles both. They are kept unchanged
under `source/data/raw/`.

### How to reproduce the extracts

1. Create an account at https://gssdataexplorer.norc.org and sign in.
2. Search for each variable below and add it to an extract.
3. Go to create extract and name the extract `gss_cut_a_2016_2018` (cut A) or
   `gss_cut_b_2018_2022` (cut B).
4. Choose all the variables below.
5. Choose the years for that cut (table below).
6. Choose JSON as the format and export.
7. Save the downloaded file, contents unchanged, under `source/data/raw/` as
   `gss_cut_a_2016_2018.json` or `gss_cut_b_2018_2022.json`.

Both cuts use the same 22 variables, in this order:

`year id_ wrkstat evwork indus10 age educ sex region relig attend reliten postlife pray
relig16 satjob news tvhours wwwhr inttech ballot wtssnrps`

| cut | years selected | why |
|---|---|---|
| A | 2016, 2018 | the waves with the most answers for the religiosity and media questions, and the most variables in scope available |
| B | 2018, 2022 | keeps 2018 for comparison and adds 2022, the most recent wave, to compare with recent years |

Each cut was exported as JSON (all respondents in the chosen years, no further filter) and
saved unchanged under `source/data/raw/`. The overlap is the whole 2018 wave (2,348
respondent-years, 45% of A and 40% of B). The cost of including 2022: `inttech` is not
available that year, and `postlife` and `reliten` were answered by only about half of it.

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
| `source/tests/` | Loader and seed-builder tests |
| `dbt/models/` | `staging/` (views), `intermediate/` (views), `marts/` (tables) |
| `dbt/seeds/` | `ref_variables`, `ref_codes` (what every code means and what kind of value it is) and `ref_variable_validity` (which years and ballots each question was answered in, as observed) |
| `dbt/tests/` | Singular data tests (`assert_*`) |
| `dbt/analyses/` | The six analytical queries (`q1_` to `q6_`) and `overlap_audit` |
| `docs/` | Design note, naming conventions, data profile, ingestion verification, production sketch (bonus) |
| `report/` | The report (`report.md`) |
| `Dockerfile`, `.dockerignore` | The packaged environment (see Setup) |

## Setup

There are two ways to run the pipeline. Docker is the recommended one: it needs only Docker
installed. A local virtual environment needs Python 3.12.

### Option A: Docker (recommended)

Requires Docker (Docker Desktop on Windows or macOS). From the repository root, build once:

```bash
docker build -t gss-pipeline .
```

Then run the whole pipeline (load, dbt build and tests, dbt docs).

Windows (PowerShell):

```powershell
docker run --rm -v "${PWD}/output:/app/output" gss-pipeline
```

macOS or Linux:

```bash
docker run --rm -v "$(pwd)/output:/app/output" gss-pipeline
```

Everything a run produces is written to `output/`, which is not committed: the database
(`gss.duckdb`), `logs/pipeline.log`, `dbt_logs/` and `dbt_target/` (docs and
`run_results.json`). The container exits with a non-zero code if any step fails.

Other commands, using the same image (PowerShell shown; on macOS or Linux use `$(pwd)`):

```powershell
# unit tests
docker run --rm gss-pipeline python -m unittest discover -s source/tests

# one analytical query's result
docker run --rm -v "${PWD}/output:/app/output" gss-pipeline dbt show --select q1_prayer_by_religion_raised --project-dir dbt --profiles-dir dbt

# browse the dbt documentation at http://localhost:8080
docker run --rm -p 8080:8080 -v "${PWD}/output:/app/output" gss-pipeline dbt docs serve --project-dir dbt --profiles-dir dbt --host 0.0.0.0 --port 8080 --no-browser
```

### Option B: local virtual environment

Requires Python 3.12 (tested with 3.12.10). Every dependency, including transitive ones, is
pinned in `requirements.txt`, so a later install resolves the same versions.

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The commands in "Run" below are the same on every platform once the environment is active.
This option has been tested on Windows only.

### Why Docker

The core pipeline needs no server, no cloud and no credentials: it is Python, local files and
an embedded database (DuckDB). So the environment is all there is to package, and each part of
it is pinned, so a run next month behaves like a run today:

- **Operating system and Python:** the base image is fixed by digest (Debian Linux, Python
  3.12.10). `run_pipeline.py` also refuses any other Python version when run outside Docker.
- **Packages:** every package, including the ones dbt pulls in, is pinned to an exact version
  in `requirements.txt`.
- **Evidence:** a no-cache build reproduced the full run, the unit tests and the same results
  as the local run (see [ingestion verification](docs/ingestion_verification.md)).

Terraform and AWS services provision cloud infrastructure, which the core pipeline
deliberately does not need; they belong to the [production sketch](docs/production_sketch.md).

## Run

For a local virtual environment (Option B), from the repository root with it active:

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
python source/pipeline/build_reference_seeds.py     # rebuild dbt/seeds from the extracts
python -m unittest discover -s source/tests -v      # loader and seed-builder tests
```

Rebuild the seeds whenever an extract is added or changed; the
`assert_validity_seed_matches_data` dbt test fails if you forget.

To see an analytical query's result, from the `dbt` folder:
`dbt show --select q1_prayer_by_religion_raised --profiles-dir .`

### Settings

| setting | meaning | default |
|---|---|---|
| `GSS_DB_PATH` | DuckDB file, used by the loader and dbt | `source/data/warehouse/gss.duckdb` |
| `GSS_LOG_DIR` | log folder | `logs/` |

The Docker image sets both to paths under `output/`, along with dbt's own `DBT_LOG_PATH` and
`DBT_TARGET_PATH`, so a Docker user sets nothing.

Data-specific settings are in `source/config/extract_config.json` (file pattern, key
columns, record list name) and `dbt/dbt_project.yml` (the answer variables). Nothing secret
is needed or committed: loading local files needs no credentials, and `dbt/profiles.yml`
reads the database path from `GSS_DB_PATH` rather than holding it. A new user sets nothing
unless they want other paths. To use other paths, set the variables in the shell before
running (they apply to that shell session only):

```powershell
$env:GSS_DB_PATH = "D:\gss\gss.duckdb"    # Windows PowerShell
$env:GSS_LOG_DIR = "D:\gss\logs"
```

```bash
export GSS_DB_PATH=/data/gss/gss.duckdb   # macOS / Linux
export GSS_LOG_DIR=/data/gss/logs
```

If a deployment ever needs real credentials (for example a hosted warehouse), they go in the
same way, as environment variables read by `profiles.yml` through `env_var()`, never in a
committed file. Machine-specific files (`.venv/`, the database, `logs/`, `output/`,
`dbt/target/`, `dbt/.user.yml`) are listed in `.gitignore`.

## How the pipeline behaves

- **What triggers a run:** a person or scheduler runs `run_pipeline.py`. At this scale a
  single command is enough; a scheduler such as cron or Task Scheduler would call the same one.
- **A new extract:** drop the file in `source/data/raw/` matching the config pattern, run
  `build_reference_seeds.py`, and rerun. The loader skips files that are unchanged and
  verified, and loads only the new one in its own transaction. dbt then rebuilds from raw,
  because the models are small views and tables.
- **A failed run:** the runner (or the container) exits non-zero and `pipeline.log` names the
  step; later steps do not run. Every step is safe to rerun. A bad file fails alone and the other files still load.
- **A failing data test:** `dbt build` skips every model downstream of it and the runner
  stops before the docs, so no mart is rebuilt on data that failed a check. Marts from an
  earlier successful run stay in place until a run succeeds.

## Where to look when something goes wrong

Paths are for a local run; in Docker they are under `output/` (for example
`output/logs/pipeline.log`).

- `logs/pipeline.log`: one line per step, with a run id and per-step timings.
- `dbt/logs/dbt.log` and `dbt/target/run_results.json`: what dbt ran, and which test or model
  failed and why.
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
How this would run on AWS at full scale, and how other surveys would be added, is in the
[production sketch](docs/production_sketch.md).

## Limitations and further work

The report covers these in full. In short:

- `inttech` (interest in technology) is not available in 2022 and was answered on ballot a
  and half of b only in 2016 and 2018.
- `news`, `tvhours` and `wwwhr` have no answers on ballot c; the model marks those rows
  `not_asked_on_ballot` rather than `inapplicable`. That classification is derived from
  observed coverage, not from the questionnaires, and is unverified until checked there.
- In 2022 about half of every ballot has `.i` for `postlife` and `reliten`, most likely a
  split questionnaire form that the extract does not carry. These stay `inapplicable`.
- Education is years of schooling (`educ`), not degree; Q3 bands the years as an approximation.
- Waves are cross-sectional: `id_` restarts each year, so the same number is not the same person.
- `ref_variable_validity` is derived from the data, not the codebook; check it there before
  relying on it for a variable with very few answers.

## Time spent

About 16 hours, twice the 8 suggested: much of it went on understanding the requirements,
learning the GSS, the Data Explorer and the tools, and understanding the code.
