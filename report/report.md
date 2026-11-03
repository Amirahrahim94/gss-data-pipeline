# GSS religiosity and media pipeline: report

Data: General Social Survey, NORC at the University of Chicago (full citation in the README).
Every figure comes from the run of 4 November 2026 and can be reproduced with
`python source/pipeline/run_pipeline.py` and the queries in `dbt/analyses/`.

## 1. Extracts and variable mapping

Both cuts were built in the GSS Data Explorer with the same 22 variables, exported as JSON
and committed unchanged under `source/data/raw/` (steps in the README).

| extract | years | records | why |
|---|---|---:|---|
| `gss_cut_a_2016_2018` | 2016, 2018 | 5,215 | the waves with the most answers for the religiosity and media questions, and every variable in scope available |
| `gss_cut_b_2018_2022` | 2018, 2022 | 5,892 | keeps 2018 for comparison and adds 2022 to compare with recent years |

The cuts share the whole 2018 wave: 2,348 respondents (45.0% of A, 39.9% of B), with
identical answers, giving 8,759 distinct respondents (limit 10,000). Each has a year the
other lacks. Cut B is above "roughly 5,000" because whole waves were kept: sampling inside a
wave would break the weights and ballot design. The cost of 2022 is stated below: no
`inttech`, and only about half the sample answered `postlife` and `reliten`. A respondent is
a respondent-year `(year, id_)`; `id_` restarts each wave, so the waves are separate samples.

| question | variable, and why | answered 2016 / 2018 / 2022 | not applicable or not asked |
|---|---|---|---|
| Working status | `wrkstat`: the GSS labour-force item (last week's status) | 99.9 / 99.9 / 99.8% | – |
| Worked 12+ months, if working | `evwork` with `wrkstat`: the only lifetime-work item ("ever worked as long as one year") | 36 / 35 / 37% | Asked only of people not working; working and unemployed people are `.i`. Cannot be answered for workers; Q5 answers it for non-workers |
| Education level | `educ`: highest year of school, the education item in the extract | 99.7 / 99.9 / 99.4% | Years of schooling, not degree; Q3 groups them into five bands |
| Industry | `indus10`: industry of current or last job (2010 Census codes, based on NAICS 2007), coded the same way in all three waves | 96 / 96 / 94% | Q3 keeps people working now |
| Job satisfaction | `satjob`: the GSS work-satisfaction item | 62 / 74 / 70% | Also answered by people keeping house and some unemployed; Q4 keeps people working |
| Life after death | `postlife`: asks the question directly (yes/no) | 90 / 90 / **45%** | In 2022 about half of every ballot is `.i` |
| Prayer frequency | `pray`: asks the question directly | 99 / 99 / 99% | "Never" is an answer |
| Religion raised in | `relig16`: religion at age 16, distinct from current religion (`relig`) | 99 / 99 / 98% | "None" is an answer |
| Newspaper reading | `news`: how often the respondent reads a newspaper | 66 / 66 / 67% | No answers on ballot c |
| TV viewing | `tvhours`: hours per day, a number that supports averages | 66 / 66 / 66% | No answers on ballot c; hours, not programme type |
| Interest in technology | `inttech`: interest in new technologies | 48 / 50 / **0%** | Ballot a and half of b in 2016–18; `.y` in 2022. Interest, not use |

Also extracted: `relig`, `attend`, `reliten`, `wwwhr`, `year`, `id_`, `ballot`, the weight
`wtssnrps`, `age` (89 means "89 or older"), `sex` and `region`.

**Records where a question did not apply or was not asked** are never dropped or recoded.
Each answer is a row with a `response_type`: `answer`, `inapplicable`, `unavailable_that_year`
(`.y`), `dont_know`, `no_answer`, `skipped_on_web`, or `not_asked_on_ballot`. All come
straight from the GSS code except `not_asked_on_ballot`, which is **derived**: `.i` on a
ballot where nobody answered that year. That strongly suggests the question was not on the
ballot but does not prove it; it is unverified until checked against the questionnaires.
Shares are computed over real answers only, with the not-asked counts shown alongside.

## 2. Data profile

Written before the pipeline by `profile_extracts.py`. `docs/data_profile_summary.md` has
record counts and the share of answers, special codes and blanks for every variable and
year, for each cut and for the combined distinct respondents. The main points:

| year | respondents | `postlife` missing | `reliten` missing | `news` missing | `wwwhr` missing | `inttech` missing |
|---|---:|---:|---:|---:|---:|---:|
| 2016 | 2,867 | 9.7% | 1.0% | 34.3% | 44.6% | 51.7% |
| 2018 | 2,348 | 9.6% | 1.5% | 33.6% | 42.0% | 50.0% |
| 2022 | 3,544 | 55.5% | 50.4% | 33.3% | 36.8% | 100.0% |

The other religion, work and demographic variables (`relig`, `attend`, `pray`, `relig16`,
`wrkstat`, `educ`, `indus10`, `age`, `sex`, `region`) are at least 93% answered in every year;
`evwork`, `satjob` and `tvhours` are lower by design or ballot (§1 table). These are unweighted shares of special codes, not the share of eligible people who
failed to answer.

- **Special codes vs answers:** no value is blank; every missing value is a label starting
  with a dot and a letter (`.i:  Inapplicable`, `.d:  Do not Know/Cannot Choose`, `.n`, `.s`,
  `.y`). Real answers never start that way, and literal answers such as "None" or "Never" are
  answers, not missing.
- **Asked only in some years or ballots:** `news`, `tvhours`, `wwwhr` have no answers on
  ballot c; `inttech` is answered on ballot a and half of b in 2016–18 and is `.y` in 2022;
  `postlife` and `reliten` are answered by about half of each 2022 ballot. These are observed
  patterns: zero answers on a ballot strongly suggests, but does not prove, it was not asked.
- **Effect on what can be answered:** Q4 and Q6 rest on two thirds of each wave; technology
  interest cannot be compared with 2022; 2022 belief in life after death rests on 1,576
  answers, not about 3,200; working respondents cannot be asked about lifetime work.

## 3. Database and schema

**DuckDB** through `dbt-duckdb`: a single local file with no server, no account and no cost;
installed with `pip`, so a reviewer can run the pipeline on a clean machine; columnar, so the
counts, shares and cross-tabulations the analyses need are fast; and fully supported by dbt.
Each layer has its own schema, so it is always clear where a table comes from and the dbt
layers can be dropped and rebuilt from `raw` without loss.

| layer / stored as | purpose and justification |
|---|---|
| `raw` / tables | The source exactly as received, one row per respondent per extract; never changed in place |
| `staging` / view | Typed keys and weight, one row per respondent-year, answer labels unchanged. Small and cheap to recompute |
| `intermediate` / view | One row per answer, classified against the seeds; independent of the six questions |
| `marts` / tables | `dim_respondent`, `fct_response` and `fct_variable_coverage`, read by every analysis; a full rebuild is proportionate at this size |
| `reference` / seeds | Version-controlled code meanings, response types and observed coverage |

## 4. Model and structures

- **Layers:** raw → staging → intermediate → marts, with the reference seeds alongside (§3).
- **Grain and keys:** `dim_respondent` has one row per respondent-year (8,759), key
  `respondent_year_id` (e.g. `2018-1042`), with ballot, weight, demographics and work status.
  `fct_response` has one row per respondent-year per variable (157,662 = 8,759 × 18). Tests
  check both grains and that counts hold through every layer.
- **Encodings:** answers are readable labels (`Several times a day`), with the code and a
  numeric value where useful. `ref_codes`, built from the export's own code list, gives each
  code's label and response type; `ref_variable_validity`, derived from the answers, records
  which year and ballot each question was answered in. Models join to these seeds instead of
  repeating them.
- **Missing values:** the source value is kept, `response_type` says what kind it is, and
  `is_answer` is true only for real answers (§1).
- **Naming** (`docs/naming_conventions.md`): lowercase snake_case; `stg_`, `int_`, `dim_`,
  `fct_`, `ref_`, `assert_` and `q<n>_` prefixes; one schema per layer.
- **Adding a variable:** add it to the extracts and the `answer_variables` list and rebuild
  the seeds; no model changes.
- **Weights (bonus):** `wtssnrps` (post-stratified, adjusted for non-response, in all three
  waves). Shares and means are weighted; group sizes are unweighted counts.

## 5. Libraries and frameworks

Python 3.12 standard library for reading and validation (`ast.literal_eval`, because the
export is Python-literal rather than strict JSON; never `eval`), `hashlib` and `unittest`;
DuckDB; dbt-core with dbt-duckdb. Every version is pinned in `requirements.txt`. Rejected:
pandas (DuckDB does the bulk loading), pytest (unittest needs no extra package),
Airflow/Dagster/Prefect (three steps in a row need no scheduler; a Python runner does it),
Docker and Terraform (the pipeline needs no server or cloud, so a virtual environment with
every package and the Python version pinned reproduces it; tested from a clean copy on Windows.
Docker would also pin the operating system and is the next step; Terraform belongs to the
AWS design in the production sketch).
Orchestration, configuration and logs are described in the README.

## 6. Results and caveats

Each respondent is counted once: `overlap_audit.sql` reconciles 5,215 + 5,892 − 2,348 =
8,759, and both marts hold 8,759. Shares and means are weighted; counts are not. No
standard errors or significance tests were calculated, and associations are not causes.

**Q1. Prayer by religion raised in.** Raised Protestant (4,408 answers): 34% pray several
times a day, 14% never. Catholic (2,798): 29% once a day, 16% never. No religion (878): 43%
never. Muslim (67): 68% several times a day. *Trust:* good for the three large groups; groups
under about 100 are indicative only.

**Q2. Belief in life after death.**

| year | answered | believe | inapplicable (`.i`) | don't know / no answer |
|---|---:|---:|---:|---:|
| 2016 | 2,588 | 79.5% | 0 | 279 |
| 2018 | 2,123 | 80.1% | 0 | 225 |
| 2022 | 1,576 | 82.2% | 1,707 | 261 |

No respondent is `.y` or classified not-asked-on-ballot. *Trust:* 2016 and 2018 are solid. In
2022 the 1,707 `.i` rows are spread evenly across ballots, consistent with a split
questionnaire form the extract does not show, so they are probably "not asked", but that
cannot be proven from `.i` alone. A 2-point rise on 1,576 answers is not strong evidence of
change.

**Q3. Most common industry by education (working respondents).** Under 12, 12 and 13–15 years
of school: construction (15%, 11%, 7%). 16 and 17+ years: elementary and secondary schools
(8%, 16%). *Trust:* the leading industry holds only 7–16% of each group; counts are
unweighted; years of school are not degrees.

**Q4. TV and job satisfaction (working respondents).**

| job satisfaction | respondents | mean TV hours | 4+ hours a day |
|---|---:|---:|---:|
| Very satisfied | 1,522 | 2.45 | 19.3% |
| Moderately satisfied | 1,284 | 2.47 | 18.3% |
| A little dissatisfied | 300 | 2.08 | 14.9% |
| Very dissatisfied | 98 | 1.85 | 11.0% |

*Trust:* no difference between the two large groups; less TV among the dissatisfied rests on
small groups and is not adjusted for age, hours worked or year.

**Q5. Ever worked 12+ months, among people not working.** 88.6% (2,880 yes, 280 no): retired
98.8%, keeping house 82.3%, other 85.2%, in school 61.5%. *Trust:* good, but 379 of 386
unemployed people were not asked, so this describes the other four groups.

**Q6. Newspaper and TV, wave to wave.**

| wave | reads paper daily | never reads | mean TV hours | 4+ hours |
|---|---:|---:|---:|---:|
| 2016 | 20.9% | 38.0% | 2.78 | 25.7% |
| 2018 | 17.9% (−3.0) | 44.6% (+6.6) | 2.73 (−0.05) | 25.6% (−0.1) |
| 2022 | 14.0% (−3.9) | 54.7% (+10.1) | 3.07 (+0.34) | 29.1% (+3.5) |

*Trust:* the newspaper decline is large and consistent. The 2022 TV rise is less certain:
four years apart, and 2022 was partly collected on the web, so a mode effect is possible.
Each wave rests on ballots a and b (1,555–2,365 answers). Online news is not measured.

## 7. Efficiency

**Materialisation.** Staging and intermediate are views: read once per build, nothing to
store. Marts are tables, because every analysis reads them. `dbt build` takes 15–30
seconds. At the full cumulative file (about 75,700 respondents × 7,000 variables) the long
model and `fct_response` would become incremental tables, built one survey year at a time.

**Query plan.** The most expensive query is Q1 (about 20 ms): two scans of
`fct_response` (for `pray` and `relig16`), a join to `dim_respondent` for the weights, a
group-by and a window total (plan in Appendix A). Each scan filters on `variable_name`, and
DuckDB skips a block of about 122,880 rows only when that value falls outside the block's
min/max. **Change:** `fct_response` is now stored sorted by `variable_name`. At 157,662 rows
there are two blocks; before, both scans read both blocks, now each reads one, which is too
small to change the time. To show it at scale, `source/pipeline/benchmark_sort_order.py`
copies the table 100 times (15.8 million rows), once appended copy after copy (as
extract-by-extract loads would leave it) and once sorted:

| layout | blocks read per `fct_response` scan | Q1, 1 thread | Q1, all threads |
|---|---|---:|---:|
| appended | 129 of 129 | 521 ms | 167 ms |
| sorted | 8 of 129 | 330 ms | 155 ms |

Both return identical results. With all threads the join and window dominate, so the gain
is small. This is a **layout test, not a full-GSS benchmark**: repeated rows compress and
process more easily than 7,000 varied real variables, so the block counts carry over but the
timings do not.

**A new extract.** The loader skips unchanged files by fingerprint (after checking their
stored rows) and loads only the new one, in its own transaction. The seeds are rebuilt with
`build_reference_seeds.py`; a dbt test fails if this is forgotten. dbt then rebuilds every
model, which at this size is cheaper than incremental logic. A failed dbt build can leave
the marts partly rebuilt; rerunning repairs them.

**Not built, as disproportionate here:** incremental models, partitioned storage, a
scheduler, Docker, CI and a realistic full-scale benchmark.

## 8. Limitations and mitigations

| limitation | mitigation | still open |
|---|---|---|
| `.i` means both "not on ballot" and "did not apply" | derived `not_asked_on_ballot` where a whole ballot has no answers | unverified against the questionnaires |
| 2022 `postlife`, `reliten` half missing within every ballot | kept as `inapplicable`, reported in Q2 | the cause (likely a form split) is not in the extract |
| `inttech` absent in 2022 | marked `.y`; not compared across waves | no recent answer |
| "If working, worked 12+ months" not asked of workers | answered for non-workers (Q5) | needs a job-tenure question |
| Education is years, not degree | five bands in Q3 | add `degree` |
| `satjob` answered beyond workers | Q4 keeps people working | – |
| Separate samples; 2022 mixed mode | descriptive comparisons only | – |

## 9. Risk and complexity at scale

At the full file, respondents grow about 9× and variables about 390×, so values grow about
3,400× (157,662 → about 530 million).

1. **Breaks first: reading the export.** The reader parses each file in memory (0.8 s for
   3 MB). At about 26 bytes per value, the full file would be roughly 13 GB. Fix: CSV or
   Parquet, read in a stream, one wave per file.
2. **Next: the generated SQL.** The long model writes one `union all` per variable; 7,000 is
   too many. Fix: DuckDB `UNPIVOT`.
3. **Grows fastest: the long table**, to about 530 million rows: at least 4 GB (the repeated
   test data gave about 8 bytes per row, a lower bound), too much to rebuild on every run.
   Fix: incremental models by survey year, kept sorted by variable.
4. **Seeds outgrow seeds:** `ref_codes` from 637 rows to about 200,000. Fix: load code
   metadata as a raw table.
5. **More sources:** each brings its own codes, missing values, weights and ballots, and
   comparison needs a mapping per shared concept per source (5 sources × 50 concepts = 250).
   The single-file database allows one writer at a time. Fix: one staging model per source
   into the same long shape, a tested concept-mapping table, and a warehouse engine beyond
   one machine (`docs/production_sketch.md`).

## 10. Assumptions and divergence

Assumptions: `(year, id_)` identifies a respondent-year; shared respondent-years are identical
(checked: 0 conflicts); only `.y` means "not in that year"; waves are separate samples.
Divergences from the design note (listed in its section 8): no wide view for the six
questions; a validity seed derived from the data rather than the codebook; the derived
`not_asked_on_ballot` type; demographics and work status classified in `dim_respondent`;
weighted shares; an added coverage mart; `fct_response` sorted by variable.

## 11. AI use and human oversight

**AI tools and contribution.** I used two AI tools: ChatGPT/Codex (OpenAI) and Claude
(Anthropic, in the Claude desktop app). ChatGPT/Codex was used extensively to develop and
revise the Python ingestion code, dbt models and configuration, tests, analytical SQL and
documentation, and for troubleshooting and identifying survey-data limitations. Claude
reviewed the build against the brief, made the later fixes (the validity seed, the corrected
Q4 and Q5, simplified queries, column documentation), ran the query-plan test and drafted
this report. AI's contribution went well beyond editing or autocomplete.

**My contribution.** I explored the GSS Data Explorer, selected and exported the extracts,
chose the survey years, set up and ran the project locally, and reviewed the results. I
challenged proposed complexity and asked for simpler choices, and raised questions about
variable suitability, missing values, performance, and what the brief requires versus
optional production features.

**Human oversight.** I ran the pipeline and tests on Windows, inspected the counts and
overlap results, and reviewed proposed changes. I have not independently verified every
questionnaire routing rule; the unresolved eligibility limitations are in section 8.

## 12. Time spent and further work

About 16 hours, twice the 8 suggested. Much of the extra time went on understanding the
requirements, getting familiar with the GSS, the Data Explorer and the tools (dbt, DuckDB),
and understanding the code well enough to explain it. With more time: verify ballot and form
routing against the questionnaires; add `degree` and a job-tenure question; CI running
`dbt build` on every commit. How this would run on AWS and take in other surveys is in
`docs/production_sketch.md` (bonus).

---

## Appendix A. Q1 query plan (DuckDB 2.0, `EXPLAIN ANALYZE`)

```
Order By (religion_raised, is_answer, respondents)
└─ Window (share within religion_raised and is_answer)
   └─ Hash Group By (religion_raised, prayer_frequency, is_answer)
      └─ Hash Join (respondent_year_id)
         ├─ Table Scan fct_response     Filters: variable_name = 'pray'
         └─ Hash Join (respondent_year_id)
            ├─ Table Scan fct_response     Filters: variable_name = 'relig16'
            └─ Table Scan dim_respondent
```

Warehouse, after the change: total 0.017 s; blocks read 1 of 2 (`pray`), 1 of 2 (`relig16`),
1 of 1 (`dim_respondent`). 100× copy: 129 of 129 per `fct_response` scan before, 8 of 129
after. Rerun with `python source/pipeline/benchmark_sort_order.py`.
