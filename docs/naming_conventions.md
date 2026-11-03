# Naming conventions

One style everywhere: lowercase `snake_case`, no spaces, no capitals. A name says what the
thing is or does, so it can be found without opening it.

Variable and column names are always written lowercase, in prose as well as code
(`evwork`, `wrkstat`), exactly as they appear in the data.

## Files in the repository

| kind | pattern | example |
|---|---|---|
| Raw extract | `<source>_<cut>_<first year>_<last year>.json` | `gss_cut_a_2016_2018.json` |
| Pipeline script (does something) | `<verb>_<noun>.py` | `load_raw.py`, `profile_extracts.py` |
| Shared module (provides something) | `<noun>.py` | `extract_reader.py` |
| Test | `test_<module under test>.py` | `test_load_raw.py`, `test_build_reference_seeds.py` |
| Config | `<noun>_config.json` | `extract_config.json` |
| Documentation | `<topic>.md` in `/docs` | `design_note.md`, `naming_conventions.md` |
| Generated evidence | `<topic>_<what>.<ext>` | `data_profile_summary.md`, `data_profile_detail.csv` |

Raw extracts are never renamed after they are loaded: the file name is the extract
identity unless `extract_ids` maps it to a stable id in the config.

## Database objects

| object | pattern | example |
|---|---|---|
| Schema | layer name | `raw`, `reference` (seeds), `staging`, `intermediate`, `marts` |
| Raw table | `<source>_<what>` | `raw.gss_responses` |
| Control tables | `load_<what>` | `raw.load_log` |
| Columns | source names kept as received in `raw`; `snake_case` from staging on | `id_`, `year`, `wtssnrps` |
| Loader-added columns | fixed set | `extract_id`, `source_file`, `file_sha256`, `record_sha256`, `run_id`, `loaded_at` |

## dbt

| object | prefix | example |
|---|---|---|
| Staging model | `stg_<source>__<entity>` | `stg_gss__respondents` |
| Intermediate model | `int_<source>__<what>` | `int_gss__responses_long` |
| Dimension | `dim_<entity>` | `dim_respondent` |
| Fact | `fct_<event>` | `fct_response` |
| Reference seed | `ref_<what>` | `ref_codes`, `ref_variables`, `ref_variable_validity` |
| Analytical query | `q<number>_<topic>.sql` | `q1_prayer_by_religion_raised.sql` |
| Other analysis | `<topic>_<what>.sql` | `overlap_audit.sql` |
| Singular dbt test | `assert_<rule>.sql` | `assert_shared_respondent_years_agree.sql` |
| Properties (docs and generic tests) | `_<folder>__models.yml`, `_<folder>__sources.yml`, `_<folder>__seeds.yml` | `_staging__models.yml`, `_reference__seeds.yml` |
| Generic tests in YAML | always under `data_tests:` | |

Source names are kept as received in `raw`. From staging on, `year` becomes `survey_year` and
`id_` becomes `respondent_id`, so the respondent-year key is `(survey_year, respondent_id)`.
Other keys are `<entity>_id`; booleans start with `is_` or
`has_`; dates end in `_date`, timestamps in `_at`. Within the long response table, columns
about the answer start with `answer_` (`answer_label`, `answer_code`, `answer_number`). In
`dim_respondent` a demographic keeps its GSS name (`sex`, `educ`) and its missing-value kind
is `<variable>_response_type`; a numeric form ends in its unit (`educ_years`, `age_number`).

## Columns in analytical queries

| kind | pattern | example |
|---|---|---|
| Count of respondents in the row's group | `respondents` | `respondents` |
| Count of a named subset | `respondents_<subset>`, or `<answer>_count` for one answer | `respondents_in_level`, `respondents_news`, `yes_count` |
| Count of a missing kind | the kind's name | `not_asked`, `inapplicable`, `no_usable_answer` |
| Share, in percent | `pct_<what>`; weighted unless prefixed `unweighted_` | `pct_news_every_day`, `pct_yes_of_answered` |
| Mean | `avg_<what>`; weighted unless prefixed `unweighted_` | `avg_tv_hours`, `unweighted_avg_tv_hours` |
| Difference from the previous wave | `change_<column>` | `change_pct_news_never` |

## Inside files

| where | rule |
|---|---|
| Python functions, variables, arguments, modules | `snake_case` |
| Python constants | `UPPER_SNAKE_CASE` (the same words, capitalised) |
| Python classes | `CapWords`, the one exception, because Python and `unittest` expect it |
| Config keys, CSV headers, JSON fields we write | `snake_case` |
| SQL identifiers (schemas, tables, columns, aliases) | `snake_case`, never quoted to preserve case |
| Status and type values we write (`loaded`, `no_answer`) | lowercase `snake_case` |
| Test methods | `test_<what_is_checked>` in `snake_case` |

Exceptions allowed by tools: `README.md`, `Dockerfile`, `.gitignore`, `.env.example`.
