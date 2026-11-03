# Ingestion verification evidence

Selected local results for the raw loader, so they can be reviewed without the generated
database or log files. They describe the runs on the dates given; rerun the commands in the
README to reproduce them. This document covers ingestion only and is not the final report.

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

`python -m unittest discover -s source/tests -v`: **41 tests passed** in 48 seconds.

| area | what is checked |
|---|---|
| Reruns and order | a rerun skips unchanged files and changes nothing; loading in either order gives identical records |
| Overlap | a shared respondent-year is stored once per file and agrees; a conflict fails the file and rolls it back |
| Bad input | missing, blank, padded or special-missing keys; repeated, clashing or case-colliding column names; non-finite and nested values; changed column set; unreadable and malformed files |
| Isolation | a bad file does not stop the other file loading; a second process is refused with a clear message |
| Integrity | a partly stored, edited or metadata-less file is detected and reloaded; the database rejects a duplicate respondent-year |
| Value preservation | nulls, empty text, the text `None` and `NULL`, quotes, commas, line breaks, tabs and non-Latin text survive the bulk load exactly |
| Evidence | one log row per file per run; failures recorded after rollback; temporary files removed on success and failure |
| Naming | file, config, CSV and Python names follow `docs/naming_conventions.md` |

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

- Linux or macOS execution.
- Behaviour at much larger volumes: the full cumulative GSS file has about 75,700
  respondents and nearly 7,000 variables. The plan is to benchmark a scaled-up copy.
- Crash or power-loss behaviour, and several loaders at once beyond the refusal test.
- Anything downstream of raw: dbt models and marts are not built yet, and a dbt failure
  does not undo a committed raw load.
