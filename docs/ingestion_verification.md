# Ingestion verification evidence

Selected local results for the raw loader, so they can be reviewed without the generated
database or log files. They describe the runs on the dates given; rerun the commands in the
README to reproduce them. This document covers ingestion and the dbt build; it is not the final report.

Environment: Windows, Python 3.12.10, DuckDB (pinned in `requirements.txt`).

## Observed Windows load (3 November 2026)

| item | result |
|---|---|
| Run ID | `20261103T134352-3fbd79` |
| Cut A | 5,215 records loaded in 1.1s |
| Cut B | 5,892 records loaded in 1.0s |
| Source records loaded | 11,107 |
| Distinct respondent-years | 8,759 |
| Shared respondent-years | 2,348 |
| Shared respondent-years with conflicting answers | 0 |
| Failed files | 0 |
| Total runtime | 2.2s |

## Load speed

| version | run ID | total | insert step per file |
|---|---|---|---|
| Row-by-row insert | `20261103T122850-0eafef` | 14.2s | not timed separately; whole files took 4.8s and 9.1s |
| Batched SQL inserts | `20261103T130106-ef62f2` | 13.0s | 2.3s and 6.8s |
| Bulk insert from a temporary file | `20261103T134352-3fbd79` | 2.2s | about 0.1s |

This is about six times faster than the batched version. It is a local observation, not a
controlled benchmark. Reading and validation stayed enabled throughout; the file read
(about 0.8s per file, parsing the provider's Python-literal format) is now the largest step.

## Automated tests

`python -m unittest discover -s source/tests -v` (3 November 2026): **41 tests passed** in about
60 seconds: 37 for the loader (`test_load_raw.py`) and 4 for the validity seed
(`test_build_reference_seeds.py`). An earlier naming test was removed when the seeds were added.

| area | what is checked |
|---|---|
| Reruns and order | a rerun skips unchanged files and changes nothing; loading in either order gives identical records |
| Overlap | a shared respondent-year is stored once per file and agrees; a conflict fails the file and rolls it back |
| Bad input | missing, blank, padded or special-missing keys; repeated, clashing or case-colliding column names; non-finite and nested values; changed column set; unreadable and malformed files |
| Isolation | a bad file does not stop the other file loading; a second process is refused with a clear message |
| Integrity | a partly stored, edited or metadata-less file is detected and reloaded; the database rejects a duplicate respondent-year |
| Value preservation | nulls, empty text, the text `None` and `NULL`, quotes, commas, line breaks, tabs and non-Latin text survive the bulk load exactly |
| Evidence | one log row per file per run; failures recorded after rollback; temporary files removed on success and failure |
| Validity seed | a ballot answered only with missing codes is "not asked"; one real answer makes it "asked"; blank and null are not answers |

## Rerun

Run `20261103T140459-54314e` (3 November 2026) reran the current loader against the same
database: 0 loaded, 2 skipped, 0 failed, 2.0 seconds. Both files were skipped after their
stored rows were verified. The overlap check was unchanged: 2,348 shared respondent-years,
0 with different answers. The behaviour is also covered by the automated test
`test_running_twice_changes_nothing`.

## Evidence locations

| evidence | location | what it shows |
|---|---|---|
| Runtime events | `logs/pipeline.log` | Run IDs, per-step timings, counts and failure tracebacks |
| File audit history | `raw.load_log` in DuckDB | One row per attempted file per run: identity, checksum, status, counts, timestamps and error |
| Provider metadata | `raw.extract_metadata` in DuckDB | Current source variable and code metadata per extract |
| Automated checks | `python -m unittest discover -s source/tests -v` | Repeatable checks of the behaviour above |

Generated logs and the warehouse database stay out of Git. Keep the results that matter in
this document or the final report.

## Not verified

- macOS, and a local (non-Docker) run on Linux.
- Behaviour at much larger volumes: the full cumulative GSS file has about 75,700
  respondents and nearly 7,000 variables. The plan is to benchmark a scaled-up copy.
- Crash or power-loss behaviour, and several loaders at once beyond the refusal test.
- A dbt failure does not undo a committed raw load (by design: the steps are separate and
  each is safe to rerun).

## Docker run (4 November 2026)

Image built with `--no-cache` from the repository (base image pinned by digest: Debian,
Python 3.12.10), run on Docker Desktop for Windows with an empty folder mounted at `output/`.

| check | result |
|---|---|
| Full pipeline | 2 files loaded, 0 failed; `dbt build` **60 of 60 passing** (3 seeds, 5 models, 52 data tests); docs generated; exit code 0 |
| Unit tests in the container | 41 passed |
| Rerun on the same output | 0 loaded, 2 skipped, 0 failed; `dbt build` 60 of 60 |
| Same results as the local Windows run | all rows of the three marts and all seven analyses identical |
| Malformed extract added | that file failed with the reason logged, the good file loaded, dbt did not start; exit code 1 |
| Conflicting answers for a shared respondent-year | file rejected and rolled back; exit code 1 |
| New record contradicting `ref_variable_validity` (seeds not rebuilt) | `assert_validity_seed_matches_data` failed; 22 downstream steps skipped, including all marts; docs did not run; exit code 1; `run_results.json` and dbt logs kept |
| Evidence after the container exits | `gss.duckdb`, `logs/pipeline.log`, `dbt_logs/`, `dbt_target/` all in the mounted folder |
| Results and docs commands | `dbt show` returned Q2; `dbt docs serve` served the docs and manifest |
| `profile_extracts.py`, `build_reference_seeds.py` in the container | byte-identical to the committed files |
| `benchmark_sort_order.py` in the container | 128-129 of 129 row groups per scan before, 8 of 129 after; identical results |

## Clean-machine run (4 November 2026)

The repository's files only (no `.venv`, database, logs, `dbt/target` or `dbt/.user.yml`)
were copied to an empty temporary folder. Following the README: a new virtual environment
(Python 3.12.10), `pip install -r requirements.txt`, then `python source/pipeline/run_pipeline.py`.
Result: load 2.9s, `dbt build` 59 of 59 passing, docs generated; `python -m unittest discover
-s source/tests`: 41 tests passed. No step needed anything beyond the README. Windows only.

## dbt build (3 November 2026)

`python source/pipeline/run_pipeline.py`: load (2 files skipped as unchanged), then `dbt
build` with **59 of 59 passing** (3 seeds, 5 models, 51 data tests), then `dbt docs generate`.
The singular tests that carry the main expectations:

| test | expectation |
|---|---|
| `assert_row_counts_hold_through_layers` | every layer keeps each of the 8,759 respondent-years once; the response table has exactly one row per respondent-year per variable |
| `assert_shared_respondent_years_agree` | the 2,348 respondent-years in both cuts have identical answers |
| `assert_codes_are_never_guessed` | a label defined under two codes gets no code and is flagged |
| `assert_validity_seed_matches_data` | the validity seed matches the loaded data, so a new extract without rebuilt seeds fails |
