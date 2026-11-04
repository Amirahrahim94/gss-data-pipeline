# GSS Religiosity and Media Pipeline Report

Data: General Social Survey, NORC at the University of Chicago (citation in the README). Every figure can be reproduced with one Docker command (README) and the queries in `dbt/analyses/`.

## 1. Extracts and variable mapping

Both cuts were built in the GSS Data Explorer with the same 22 variables and exported as JSON to `source/data/raw/`, unchanged (steps in the README).

| Extract | Years | Records | Why |
|---|---|---|---|
| `gss_cut_a_2016_2018` | 2016, 2018 | 5,215 | the waves with the most answers for the religiosity and media questions, and every variable in scope available |
| `gss_cut_b_2018_2022` | 2018, 2022 | 5,892 | keeps 2018 for comparison and adds 2022 to compare with recent years |

The cuts share the whole 2018 wave: 2,348 respondents (45.0% of A, 39.9% of B), with identical answers, giving 8,759 distinct respondents (limit 10,000). Each has a year the other lacks. Cut B is above "roughly 5,000" because whole waves were kept: sampling inside a wave would break the weights and ballot design. A respondent is a respondent-year `(year, id_)`; `id_` restarts each wave, so the waves are separate samples.

"Answered" is the share of people with a usable response each year. The GSS splits people into three groups (ballots a, b and c), and some questions have no answers from a whole group.

| Question | Why this variable? | Answered 2016 / 2018 / 2022 | Limitations and how handled |
|---|---|---|---|
| Working status | `wrkstat` records whether the person was working, retired, unemployed, studying or in another status last week | 99.9 / 99.9 / 99.8% | Almost everyone has a usable response |
| Worked for at least one year | `evwork` asks about having worked as long as one year; `wrkstat` gives the employment context | 36 / 35 / 37% | Almost no current workers have an answer (2 of 5,205), so this cannot be answered for them. Their records stay marked not applicable and are not counted as "no" |
| Education | `educ` records the highest year of school completed | 99.7 / 99.9 / 99.4% | Measures years of schooling, not degrees. Q3 combines them into five bands |
| Industry | `indus10` identifies the industry of the current or last job | 96 / 96 / 94% | Q3 uses `wrkstat` to keep current workers |
| Job satisfaction | `satjob` records satisfaction with work | 62 / 74 / 70% | Also answered outside the working group. Q4 keeps workers only |
| Life after death | `postlife` asks directly whether the person believes in life after death | 90 / 90 / **45%** | In 2022, 1,707 responses are inapplicable and the cause is unconfirmed. They are left out of the YES/NO percentage and reported separately |
| Prayer frequency | `pray` directly measures how often the person prays | 99 / 99 / 99% | "Never" is a usable response and stays in the distribution |
| Religion raised in | `relig16` records the religion the person was raised in | 99 / 99 / 98% | "None" is a usable response |
| Newspaper reading | `news` measures how often the person reads newspapers | 66 / 66 / 67% | No usable answers on ballot c. Percentages use usable responses, with their count shown |
| TV viewing | `tvhours` measures daily hours watching TV | 66 / 66 / 66% | No usable answers on ballot c. Zero hours is valid; missing values are left out of averages |
| Technology interest | `inttech` measures interest in technologies | 48 / 50 / **0%** | Answers in 2016 and 2018; unavailable in 2022. Measures interest, not actual use |

Also extracted: `relig`, `attend`, `reliten`, `wwwhr`, `year`, `id_`, `ballot`, the weight `wtssnrps`, `age` (89 means "89 or older"), `sex` and `region`.

**Records where a question did not apply or was not asked** are never dropped or recoded. Each answer is a row with a `response_type`: `answer`, `inapplicable` (`.i`), `unavailable_that_year` (`.y`), `dont_know`, `no_answer`, `skipped_on_web`, or `not_asked_on_ballot`. All come straight from the GSS code except `not_asked_on_ballot`, which is **derived**: `.i` on a ballot where nobody answered that year, unverified until checked against the questionnaires. Shares use real answers only, with the not-asked counts alongside.

## 2. Data profile

Written before the pipeline by `profile_extracts.py`. `docs/data_profile_summary.md` has record counts and the share of answers, special codes and blanks for every variable and year, for each cut and for the combined distinct respondents. The main points:

| Year | Respondents | `postlife` missing | `reliten` missing | news missing | `wwwhr` missing | `inttech` missing |
|---|---|---|---|---|---|---|
| 2016 | 2,867 | 9.7% | 1.0% | 34.3% | 44.6% | 51.7% |
| 2018 | 2,348 | 9.6% | 1.5% | 33.6% | 42.0% | 50.0% |
| 2022 | 3,544 | 55.5% | 50.4% | 33.3% | 36.8% | 100.0% |

All other variables are at least 93% answered in every year, except `evwork`, `satjob` and `tvhours` (see Section 1 table). These are unweighted shares of special codes, not the share of eligible people who failed to answer.

- **Special codes vs answers:** no value is blank; every missing value is a label starting with a dot and a letter (`.i:  Inapplicable`, `.d:  Do not Know/Cannot Choose`, `.n`, `.s`, `.y`). Real answers never start that way, and literal answers such as "None" or "Never" are answers, not missing.
- **Asked only in some years or ballots:** `news`, `tvhours`, `wwwhr` have no answers on ballot c; `inttech` is answered on ballot a and half of b in 2016–18 and is `.y` in 2022; `postlife` and `reliten` are answered by about half of each 2022 ballot. These are observed patterns, not proof of what each ballot asked.
- **Effect on what can be answered:** Q4 and Q6 rest on two thirds of each wave; technology interest cannot be compared with 2022; 2022 belief in life after death rests on 1,576 answers, not about 3,200; lifetime work cannot be reported for working respondents.

## 3. Database and schema

**DuckDB** through `dbt-duckdb`: a single local file with no server, account or cost; a Python package, so it needs nothing beyond the pinned environment; columnar, so the counts, shares and cross-tabulations the analyses need are fast; and supported by dbt. Each layer has its own schema, so it is clear where a table comes from and the dbt layers can be rebuilt from `raw`.

| Layer / Stored As | Purpose And Justification |
|---|---|
| `raw` / tables | The source exactly as received, one row per respondent per extract; never changed in place |
| `staging` / view | Typed keys and weight, one row per respondent-year, answer labels unchanged. Small and cheap to recompute |
| `intermediate` / view | One row per answer, classified against the seeds; independent of the six questions |
| `marts` / tables | `dim_respondent`, `fct_response` and `fct_variable_coverage`, read by every analysis; a full rebuild is proportionate at this size |
| `reference` / seeds | Version-controlled code meanings, response types and observed coverage |

## 4. Model and structures

- **Layers:** Data moves through raw → staging → intermediate → marts. These stages preserve the source, prepare the records, interpret responses and produce tables for analysis. Reference seeds provide the definitions used during processing (see Section 3).
- **Grain:** `dim_respondent` has one row per respondent per survey year (8,759 rows). `fct_response` has one row per respondent-year per variable, including missing responses (157,662 rows across 18 variables).
- **Keys:** `respondent_year_id` combines the year and respondent ID, for example `2018-1042`. It uniquely identifies a row in `dim_respondent`. In `fct_response`, the unique key is `respondent_year_id` together with `variable_name`.
- **Encodings:** Models use `ref_codes` to translate codes into readable labels and response types. `ref_variable_validity` records observed answer coverage by variable, year and ballot; it does not confirm questionnaire assignment.
- **Missing values:** The original value is retained. `response_type` distinguishes genuine answers from "inapplicable", "don't know", "no answer" and "unavailable that year". `is_answer` identifies genuine answers. The derived `not_asked_on_ballot` category remains an inference requiring questionnaire verification.
- **Naming:** Names use lowercase words separated by underscores. Prefixes identify purpose: `stg_`, `int_`, `dim_`, `fct_`, `ref_`, `assert_` and `q<n>_`. Each layer has its own schema. Details are in `docs/naming_conventions.md`.
- **Adding a variable**: add it to the extracts and the `answer_variables` list and rebuild the seeds; no model changes.
- **Survey weights (bonus):** Percentages and averages use `wtssnrps`, which adjusts respondents' contributions for survey representation and non-response. Reported group counts remain the actual number of respondents.

## 5. Libraries and frameworks

**Python 3.12:** Reads and validates the extracts. The standard library provides `ast.literal_eval` to read the Python-literal export safely without `eval`, `hashlib` for file and record fingerprints, and `unittest` for automated tests. **DuckDB:** Stores the data and executes SQL, including bulk loading. **dbt-core and `dbt-duckdb`:** Build and test the transformation models and generate documentation. **Docker:** Packages the environment using a base image fixed by digest and pinned package versions. A build without cached layers reproduced the pipeline, tests and results.

No pandas or pytest dependencies were added because DuckDB and `unittest` cover the required work. A separate orchestration framework was omitted (Airflow, Dagster or Prefect) since a Python runner coordinates the three pipeline steps. AWS deployment remains proposed future work in the production sketch. Run instructions, configuration and log locations are documented in the README.

## 6. Results and caveats

Each respondent-year is counted once. `overlap_audit.sql` confirms that 5,215 + 5,892 − 2,348 shared records gives 8,759 distinct respondent-years. `dim_respondent` contains these 8,759 records, and `fct_response` covers the same respondent-years across multiple response rows. Percentages and averages are weighted; counts are actual respondent counts. Statistical uncertainty was not calculated, so differences should be interpreted cautiously. The results describe associations and do not establish causes.

**Q1. Prayer by religion raised in.** Among respondents raised Protestant (4,408 usable answers), 34% pray several times a day and 14% never pray. Among those raised Catholic (2,798), 29% pray once a day and 16% never. Among those raised without religion (878), 43% never pray. Among those raised Muslim (67), 68% pray several times a day.

**Trust:** Prayer patterns differ by religious upbringing. Estimates for smaller groups, particularly the 67 respondents raised Muslim, are less precise and should be treated cautiously.

**Q2. Belief in life after death.**

| Year | Usable YES/NO answers | believe | inapplicable (`.i`) | don't know / no answer |
|---|---|---|---|---|
| 2016 | 2,588 | 79.5% | 0 | 279 |
| 2018 | 2,123 | 80.1% | 0 | 225 |
| 2022 | 1,576 | 82.2% | 1,707 | 261 |

Percentages use only usable YES/NO answers. Counts are unweighted. Belief was reported by around four in five respondents who gave a usable answer in each year.

**Trust:** 2016 and 2018 are solid. Coverage was lower in 2022: 1,707 records were marked "inapplicable". The extract does not establish why, so these remain separate from other missing responses and are excluded from the percentage. None were classified as unavailable that year (`.y`) or `not_asked_on_ballot`. The estimated percentage rose by 2.1 percentage points between 2018 and 2022. Without uncertainty estimates and confirmation of the 2022 coverage rules, this should not be presented as an established increase.

**Q3. Most common industry by education (working respondents).**

Construction is the leading industry for workers with under 12, 12 and 13–15 completed school years (15%, 11% and 7%). Elementary and secondary schools lead for 16 and 17+ years (8% and 16%). Shares are unweighted.

**Trust:** The leading industry represents only 7–16% of each group; most work elsewhere. Completed schooling years are not degrees.

**Q4. TV and job satisfaction (working respondents).** Among respondents currently working who gave usable answers to both questions:

| Job satisfaction | Respondents | Mean TV hours per day | Watching 4+ hours |
|---|---|---|---|
| Very satisfied | 1,522 | 2.45 | 19.3% |
| Moderately satisfied | 1,284 | 2.47 | 18.3% |
| A little dissatisfied | 300 | 2.08 | 14.9% |
| Very dissatisfied | 98 | 1.85 | 11.0% |

**Trust:** Average TV viewing is similar in the two satisfied groups. Dissatisfied respondents report less viewing, but those groups are smaller, particularly the very dissatisfied group. The comparison does not account for age, hours worked or survey year, and does not establish that job satisfaction affects TV viewing.

**Q5. Ever worked 12+ months, among people not working.** Among respondents not currently working who gave usable YES/NO answers, the weighted share answering YES was 88.6%. The actual counts were 2,880 YES and 280 NO.

Weighted YES shares are 98.8% for retired respondents, 82.3% for those keeping house, 85.2% for other status and 61.5% for those in school.

**Trust:** 379 of 386 unemployed respondents were marked "inapplicable", so these findings mainly describe the four groups above. The selected variable cannot reliably answer the assignment's question for current workers; missing responses are not treated as NO.

**Q6. Newspaper and TV, wave to wave.**

| Survey year | Reads paper daily | Never reads paper | Mean TV hours per day | Watching 4+ hours |
|---|---|---|---|---|
| 2016 | 20.9% | 38.0% | 2.78 | 25.7% |
| 2018 | 17.9% | 44.6% | 2.73 | 25.6% |
| 2022 | 14.0% | 54.7% | 3.07 | 29.1% |

Compared with the preceding selected year, daily newspaper reading fell by 3.0 percentage points in 2018 and 3.9 points in 2022. Never reading increased by 6.6 and 10.1 points. Mean daily TV viewing changed by −0.05 and +0.34 hours, while the share watching four or more hours changed by −0.1 and +3.5 percentage points.

**Trust:** The newspaper decline is large and consistent. TV viewing was higher in 2022, but the four-year gap and the inclusion of web responses could affect comparability. Each measure uses usable answers from ballots a and b, with 1,555–2,365 answers depending on the year and variable. Online news consumption is not measured.

## 7. Efficiency

**Materialisation.** Raw data is stored as tables to preserve loaded records. Staging and intermediate models are views because they are small and inexpensive to recompute. Marts are tables so analyses can reuse the prepared results. Reference seeds are loaded as tables containing shared definitions.

At full scale (about 75,700 respondents × 7,000 variables), the long intermediate model and `fct_response` would become incremental tables, processing one survey year at a time rather than rebuilding all historical responses.

**Query plan and change.** Q1 is one of the most expensive queries, taking about 30 milliseconds. It scans `fct_response` twice, joins to `dim_respondent`, groups the answers and calculates percentages within each group. Sorting `fct_response` by `variable_name` groups matching responses together. Each scan reads one of two row groups instead of both; the dataset is too small for a reliable timing difference. See Appendix A.

**At scale, I would demonstrate it this way:** Copy `fct_response` 100 times to create about 15.8 million rows. Prepare two versions: one in the original order and one sorted by `variable_name`. Run Q1 with `EXPLAIN ANALYZE` on both, compare the row groups read and execution times, and confirm that the results are identical. This tests the benefit of sorting; repeated data does not represent the full variety of 7,000 survey variables.

**Processing a new extract.** The loader reads and validates each matching file. An unchanged file is skipped only after its fingerprint, stored rows and metadata are checked. New or changed extracts are loaded separately, with one transaction per file. Regenerate the reference seeds with `build_reference_seeds.py`; the coverage test detects a stale validity seed. dbt then rebuilds the models. If the build fails, some marts may already have changed. Fix the cause and rerun the pipeline before using the results.

**Not built, as disproportionate here:** incremental models, partitioned storage, a scheduler, CI and a realistic full-scale benchmark.

## 8. Limitations and mitigations

| Limitation | Mitigation | Remains unsolved |
|---|---|---|
| `.i` means both "not on ballot" and "did not apply" | derived `not_asked_on_ballot` where a whole ballot has no answers | unverified against the questionnaires |
| 2022 `postlife`, `reliten` half missing within every ballot | kept as `inapplicable`, reported in Q2 | the cause (likely a form split) is not in the extract |
| `inttech` absent in 2022 | marked `.y`; not compared across waves | Find a suitable recent measure. |
| "If working, worked 12+ months": almost no answers from workers | reported as unanswerable; nothing guessed | Find a suitable work-history measure. |
| Education is years, not degree | five bands in Q3 | add `degree` |

## 9. Risk and complexity at scale

- **Breaks first: reading files.** The reader parses whole files in memory (0.8 s for 3 MB). At about 26 bytes per value, the full file would be roughly 13 GB. Use a batch-readable format such as CSV or Parquet, split by survey year.
- **Grows fastest: the long table.** Expanding every variable gives about 530 million rows, roughly 3,400 times this extract. This is an arithmetic estimate, not a measured benchmark. Replace thousands of `UNION ALL` branches with a tested unpivot approach, and process new or corrected years incrementally.
- **Reference data:** `ref_codes` would grow from 637 rows to about 200,000, so load it as data tables rather than CSV seeds.
- **Adding sources:** each brings its own keys, missing codes and weights, and comparison needs a mapping per shared concept per source (5 sources × 50 concepts = 250). Use source-specific staging and reviewed mappings. The single-file database allows one writer at a time.

## 10. Assumptions and divergence

**Assumptions:** `(year, id_)` identifies a respondent-year; shared records agree (zero conflicts found); `.y` explicitly means unavailable that year; waves are separate samples. Zero usable answers alone do not prove a question was not asked.

**Changes from the original plan:** The build uses long responses without the planned wide view, adds observed-coverage metadata and an inferred ballot-missing type, and keeps demographics/work status in `dim_respondent`. It also adds weighted results, a coverage mart, sorted response storage and Docker packaging. Reasons are recorded in the design note's divergences section.

## 11. AI use and human oversight

**AI tools and contribution.** I used ChatGPT and Claude extensively throughout the project, including design, implementation, testing, troubleshooting, analysis and documentation. AI contributed substantially to the end-to-end solution.

**My contribution and oversight.** I explored the GSS Data Explorer, chose the survey years, and set up and ran the pipeline on Windows and in Docker. I inspected execution results, record counts and overlap, reviewed proposed changes and the report, and questioned variable choices, missing-value handling, performance and unnecessary complexity.

## 12. Time spent and further work

About 20 hours; much of it went on understanding the requirements, learning the GSS Data Explorer, becoming familiar with the tools, and understanding and reviewing the code and checking results. With more time, I would first verify the remaining survey rules and weighting assumptions, and independently check selected results. For larger-scale use, I would test performance and incremental processing, automate tests through CI, and add failure alerts. I would also implement and evaluate the proposed AWS design.

---

## Appendix A. Q1 Query Plan Comparison

**Query:** prayer frequency by religion raised in (`q1_prayer_by_religion_raised.sql`).

**Purpose:** check whether sorting the response table helps DuckDB read less data.

### What the query does

The steps run in this order (DuckDB 2.0, `EXPLAIN ANALYZE`):

| Step | Purpose |
|---|---|
| Table scans | Read prayer and religion-raised responses from `fct_response`, and respondents from `dim_respondent` |
| Hash joins | Match records using `respondent_year_id` |
| Group by | Count responses by religion raised and prayer frequency |
| Window calculation | Calculate percentages within each religion and answer-status group |
| Sort | Arrange the final output |

### The change and the result

`fct_response` was sorted by `variable_name, survey_year`, so answers to the same question are stored together. DuckDB can then skip row groups that do not hold the requested variable.

On the real data (157,662 rows), each `fct_response` scan read both row groups before the change and one of two after it. The query takes only about 30 ms, so the data is too small to show a reliable time difference. Section 7 explains how I would demonstrate it at scale.

| Measurement | Before sorting | After sorting |
|---|---|---|
| Row groups per `fct_response` scan | 2 of 2 | 1 of 2 |

### Evidence

The full before-and-after plans are in `docs/q1_query_plan.txt`.
