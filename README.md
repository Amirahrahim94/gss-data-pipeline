# GSS data pipeline: religiosity and media consumption

This project loads two General Social Survey (GSS) extracts into DuckDB, transforms them
with dbt, and answers six questions about religiosity, media use and employment.

The pipeline has been run locally on Windows and in Docker, as recorded in the
[verification notes](docs/ingestion_verification.md). Read the
[report](report/report.md) for findings, design decisions and limitations.

## 1. Data source

The GSS is a project of the independent research organization NORC at the University of
Chicago, with principal funding from the National Science Foundation. The extracts were made
with the [GSS Data Explorer](https://gssdataexplorer.norc.org).

Citation, as given in the Data Explorer's
[terms and conditions](https://gssdataexplorer.norc.org/terms_and_conditions):

> Davern, Michael; Bautista, Rene; Freese, Jeremy; Herd, Pamela; and Morgan, Stephen L;,
> General Social Surveys, 1972-2024 [machine-readable data file] /Principal Investigator,
> Smith, Tom W.; Co-Principal Investigators, Rene Bautista, Jeremy Freese, Pamela Herd, and
> Stephen L. Morgan; Sponsored by National Science Foundation. --NORC ed.-- Chicago: NORC,
> 2025: NORC at the University of Chicago [producer and distributor]. Data accessed from the
> GSS Data Explorer website at gssdataexplorer.norc.org.

The inputs are stored unchanged in `source/data/raw/`.

| Extract | Years | Records | Why |
|---|---|---:|---|
| `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 | the waves with the most answers for the religiosity and media questions, and the most variables in scope available |
| `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 | keeps 2018 for comparison and adds 2022, the most recent wave, to compare with recent years |

There are **11,107 source records** and **8,759 distinct respondent-years**. The extracts
share all 2,348 records from 2018, with identical answers: 45.0% of A and 39.9% of B. Each cut
includes a year the other lacks. Cut B exceeds the approximate 5,000 target because complete
waves were retained; the strict combined limit of 10,000 distinct respondent-years is met.

A respondent-year is identified by `(year, id_)`. Raw keeps each extract's copy; staging keeps
one copy for downstream analysis. An ID repeated in another year does not establish that it is
the same person. The cost of including 2022: `inttech` is not available that year, and
`postlife` and `reliten` were answered by only about half of it.

## 2. How to reproduce the extracts

The extracts are already in the repository, so you do not need these steps for a first run.

1. Create an account at the [GSS Data Explorer](https://gssdataexplorer.norc.org) and sign in.
2. Search for each variable below and add it to an extract. Both cuts use the same 22
   variables, in this order:

   ```text
   year id_ wrkstat evwork indus10 age educ sex region relig attend reliten
   postlife pray relig16 satjob news tvhours wwwhr inttech ballot wtssnrps
   ```

3. Go to create extract and name it `gss_cut_a_2016_2018` (cut A) or `gss_cut_b_2018_2022`
   (cut B).
4. Build the extract by choosing all the variables above.
5. Choose the output options by selecting the years for that cut: **2016 and 2018** for A,
   **2018 and 2022** for B.
6. Choose JSON as the format and create the extract.
7. Select the extract, click download under the Actions button, and save the downloaded file,
   contents unchanged, under `source/data/raw/` as `gss_cut_a_2016_2018.json` or
   `gss_cut_b_2018_2022.json`.
8. To check the files, run the profiler (Option B below), which rewrites the
   `docs/data_profile_*` files, then look for changes with `git diff docs/`:

   ```powershell
   python source/pipeline/profile_extracts.py
   ```

The files are named `.json` but contain Python-literal syntax; the reader handles both. A future
provider release may change the data: record any differences rather than editing the extracts
to force a match.

## 3. Setup and run

Choose **Docker** or **local Python**. Run the commands from the project root, the folder
containing this README and the Dockerfile.

### Option A: Docker (recommended)

Install Docker and start it. On Windows, use PowerShell:

```powershell
# Build the environment once, or rebuild after changing project files.
docker build -t gss-pipeline .

# Run the pipeline and save its output on your computer.
docker run --rm -v "${PWD}/output:/app/output" gss-pipeline
```

On macOS or Linux, replace `${PWD}` with `$(pwd)` in the run command.

The pipeline runs these steps in order:

1. **Load:** validate the extracts and load them into DuckDB.
2. **Build and test:** load the reference seeds, build the dbt models and run their tests.
3. **Document:** generate the dbt documentation.

A failed step stops the runner and returns a non-zero exit code. A successful run builds the
analysis tables; it does not automatically execute the seven analysis queries (see section 4).

Docker writes its results to the local `output/` folder, which is not committed:

| Output | Location |
|---|---|
| DuckDB database | `output/gss.duckdb` |
| Pipeline log | `output/logs/pipeline.log` |
| Detailed dbt log | `output/dbt_logs/` |
| dbt documentation and execution results | `output/dbt_target/` |

**Why Docker:** the pipeline needs no server, cloud or credentials, so the environment is all
there is to package. The base image is fixed by digest (Debian, Python 3.12.10) and every package
is pinned in `requirements.txt`, so a run next month behaves like a run today. Terraform and AWS
services provision cloud infrastructure, which the core pipeline does not need; they belong to
the [production sketch](docs/production_sketch.md).

### Option B: local Python

Use **Python 3.12** (tested with 3.12.10). In Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python source/pipeline/run_pipeline.py
```

If PowerShell blocks activation, allow it for this terminal session and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Local output defaults to `source/data/warehouse/gss.duckdb`, `logs/`, `dbt/logs/` and
`dbt/target/`. To leave the environment afterwards, type `deactivate`.

On macOS or Linux (not tested there; use Docker for the tested environment):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python source/pipeline/run_pipeline.py
```

## 4. Run tests and view results

Run these after building the Docker image, or after activating the local Python environment.
Docker examples use PowerShell.

**Python tests:**

```powershell
# Docker
docker run --rm gss-pipeline python -m unittest discover -s source/tests -v

# Local Python
python -m unittest discover -s source/tests -v
```

The normal pipeline run already executes the dbt tests through `dbt build`.

**An analysis result:** results are printed in the terminal, not saved as files. `dbt show`
displays 5 rows by default, so `--limit -1` is included here to show them all.

```powershell
# Docker: uses the database created by the pipeline.
docker run --rm -v "${PWD}/output:/app/output" gss-pipeline dbt show --select q1_prayer_by_religion_raised --limit -1 --project-dir dbt --profiles-dir dbt

# Local Python
Push-Location dbt
dbt show --select q1_prayer_by_religion_raised --limit -1 --profiles-dir .
Pop-Location
```

Replace the query name to run another file from `dbt/analyses/`, which holds Q1 to Q6 and
`overlap_audit` (a check of the two extracts' shared respondents).

**The dbt documentation:** run this command, open http://localhost:8080 and keep it running
while browsing. Press Ctrl+C to stop it.

```powershell
# Docker
docker run --rm -p 8080:8080 -v "${PWD}/output:/app/output" gss-pipeline dbt docs serve --project-dir dbt --profiles-dir dbt --host 0.0.0.0 --port 8080 --no-browser

# Local Python
Push-Location dbt
dbt docs serve --profiles-dir .
Pop-Location
```

## 5. Project map

| Location | Purpose |
|---|---|
| `source/data/raw/` | Original extracts, never edited |
| `source/config/extract_config.json` | Input pattern, key columns and reader settings |
| `source/pipeline/run_pipeline.py` | Runs load, dbt build and tests, and documentation |
| `source/pipeline/extract_reader.py` | Reads files and validates their structure |
| `source/pipeline/load_raw.py` | Loads raw records, checks overlap and records outcomes |
| `source/pipeline/profile_extracts.py` | Reports counts, missing values and observed coverage |
| `source/pipeline/build_reference_seeds.py` | Rebuilds the reference CSV files |
| `source/tests/` | Python loader and seed-builder tests |
| `dbt/models/` | Staging views, intermediate views and mart tables |
| `dbt/seeds/` | `ref_variables`, `ref_codes` (what each code means) and `ref_variable_validity` (which years and ballots each question was answered in, as observed) |
| `dbt/tests/` | Custom data checks (`assert_*`) |
| `dbt/analyses/` | Six analysis queries and the overlap audit |
| `docs/` | Design, conventions, profile, verification, Q1 query plans and production sketch |
| `report/` | Findings and caveats |
| `Dockerfile`, `.dockerignore`, `requirements.txt` | Packaged environment and pinned dependencies |

The transformation layers are **raw → staging → intermediate → marts**, with the reference seeds
alongside. See the [design note](docs/design_note.md) and
[naming conventions](docs/naming_conventions.md).

## 6. How the pipeline behaves

**What triggers a run:** a person or scheduler runs `run_pipeline.py` (in Docker, `docker run`).
At this scale a single command is enough; a scheduler such as cron or Task Scheduler would call
the same one.

| Situation | Behaviour |
|---|---|
| Run again with unchanged inputs | The loader verifies the files against the stored data and skips loading them. dbt rebuilds the small models. |
| Add or change an extract | Put the file in `source/data/raw/`, rebuild the seeds, then rerun. New or changed files load in their own transactions. |
| A file is invalid or conflicts with overlapping records | That file fails and its transaction rolls back. Other files can still load; the runner stops before dbt. |
| A dbt model or test fails | Dependent models are skipped and the runner stops before the documentation. Some marts may already have been rebuilt; rerunning repairs them. |

To update the seeds after changing an extract, use the local Python environment:

```powershell
python source/pipeline/build_reference_seeds.py
python source/pipeline/run_pipeline.py
```

The `assert_validity_seed_matches_data` test fails if you forget. Review and commit the regenerated
CSVs. If you run in Docker, rebuild the image afterwards so it includes the updated extracts and
seeds.

To apply a deliberate column change, rebuild all extracts into a new database path with `--db`,
then check the rebuild before switching to it.

**Where to look when something goes wrong:**

- **Pipeline log:** `logs/pipeline.log` locally, or `output/logs/pipeline.log` in Docker. One line
  per step, with a run id and timings.
- **dbt log and results:** `dbt/logs/dbt.log` and `dbt/target/run_results.json` locally;
  `output/dbt_logs/` and `output/dbt_target/` in Docker.
- **Database audit tables:** `raw.load_log` has one row per file per run (loaded, skipped or
  failed, with the reason). `raw.extract_metadata` holds the export's own variable and code
  metadata.

Evidence and test results are in [ingestion verification](docs/ingestion_verification.md).

## 7. Settings

No credentials are needed. A new user sets nothing unless they want other paths.

| Setting | Meaning | Default |
|---|---|---|
| `GSS_DB_PATH` | DuckDB file, used by the loader and dbt | `source/data/warehouse/gss.duckdb` |
| `GSS_LOG_DIR` | Log folder | `logs/` |

The Docker image sets both to paths under `output/`, along with dbt's own `DBT_LOG_PATH` and
`DBT_TARGET_PATH`. To use other paths locally, set them before running (they apply to the current
terminal only):

```powershell
$env:GSS_DB_PATH = "D:\gss\gss.duckdb"
$env:GSS_LOG_DIR = "D:\gss\logs"
```

Data settings are in `source/config/extract_config.json` (file pattern, key columns, record list
name) and `dbt/dbt_project.yml` (the answer variables). `dbt/profiles.yml` reads the database path
from `GSS_DB_PATH` rather than holding it. If a deployment ever needs real credentials, they go in
the same way, as environment variables read through `env_var()`, never in a committed file.
Machine-specific files (`.venv/`, the database, `logs/`, `output/`, `dbt/target/`,
`dbt/.user.yml`) are listed in `.gitignore`.

## 8. Limitations and further reading

- `inttech` has no answers in 2022, and in 2016 and 2018 was answered on ballot a and half of b.
- `news`, `tvhours` and `wwwhr` have no answers on ballot c. `not_asked_on_ballot` is derived from
  observed coverage; confirm it against the questionnaires before treating it as verified.
- Many 2022 `postlife` and `reliten` responses are inapplicable; the cause remains unconfirmed.
- Education is measured in completed school years, not degrees. Survey waves are cross-sectional;
  results do not track individuals over time.

See the [report](report/report.md) and the optional
[AWS and additional-source sketch](docs/production_sketch.md).

Approximately **16 hours** were spent on the assignment. The report explains the effort, AI use and
priorities for further work.
