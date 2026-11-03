# Design note: GSS survey pipeline

Status: proposed design, written before the pipeline code. Anything below is a plan until
it is built and tested; differences are recorded in section 8.

## 1. Scope and inputs

A local Python and dbt pipeline for respondent-year questions and aggregate analysis of
religiosity, media consumption, employment and demographics.

| extract | years | records |
|---|---|---:|
| `gss_cut_a_2016_2018.json` | 2016, 2018 | 5,215 |
| `gss_cut_b_2018_2022.json` | 2018, 2022 | 5,892 |

They share 2,348 respondent-years (45.0% of A, 39.9% of B), giving 8,759 distinct
respondent-years.
Each cut has a year the other lacks (2016, 2022), and the shared respondent-years have identical
answers in both. Cut B is above the "roughly 5,000" target because whole waves were taken
rather than sampling respondent-years; this is stated in the report.

The files are named `.json` but are Python literals (single quotes). They are committed
unchanged under `source/data/raw/`. The reader tries strict JSON, then `ast.literal_eval`
(never `eval`).

## 2. Grain and identity

- **Respondent-year key: `(year, id_)`.** A respondent-year is one person interviewed in one
  survey year. `id_` restarts every wave, so it is unique only within a year, and the GSS
  waves are cross-sectional. The same `id_` across years does not establish that the
  records represent the same person.
- **Raw:** one row per respondent-year per source file, so a shared respondent-year appears once for
  each cut that contains them.
- **`dim_respondent`:** one row per distinct respondent-year, unique on `(year, id_)`. Carries
  the weight and ballot.
- **`fct_response`:** one row per respondent-year per question variable, unique on
  `(year, id_, variable)`.

## 3. Layers

| layer | contents | purpose |
|---|---|---|
| `raw` | source values represented as text, plus source file, SHA-256 and load time; a load log; the export's own variable and code metadata (the source for the `ref_*` seeds); unchanged source files remain the authoritative originals | preserve the source and show what was loaded |
| `staging` | one row per distinct respondent-year; renamed and typed columns; the overlap between cuts resolved | one place where the source is cleaned and deduplicated |
| `intermediate` | the long response table (one row per respondent-year per variable) with each value's response type and label attached from the metadata seeds | reusable logic that does not depend on one survey or on any analytical question |
| `marts` | `dim_respondent`, `fct_response` and a wide view for the six questions | what analysts query |

The intermediate layer is small at this size, but it keeps the generic logic in one place:
a new survey gets its own staging model and reuses the intermediate logic, and a new
variable needs only new extract columns and seed rows.

**Semantic metadata** lives in version-controlled seeds (`ref_*`): for each variable, what
each code means, whether it is an answer or a kind of missing data, and the years and
ballots where it is valid. Models read the seeds and do not repeat them. (Section 8 says how
the validity seed was built.)

## 4. Missing values and extensibility

Special missing codes arrive as text (`.i: Inapplicable`, `.y`, `.d`, `.n`, `.s` and
others). Each response keeps its source value and gets one response type: `answer`,
`inapplicable`, `unavailable_that_year`, `dont_know`, `no_answer`, `skipped_on_web`, or
another observed missing code. The original code stays in its own column even when a
summary grouping such as `other_missing` is used, so the grouping never replaces it.
Nothing is filled or recoded in place, and an analyst cannot mistake "not asked that
year" for "no" or for a real answer.

Literal answers such as `None` (religion), `Never`, or the number zero are genuine
answers. `evwork` is read together with `wrkstat`, since inapplicable is not "never
worked".

`fct_response` is long, so adding a variable means adding it to the extracts and the seeds;
the long model and its generic logic are unchanged. The specialised wide view for the six
questions may need new columns if the new variable is to appear in it.

## 5. Database

**DuckDB** through `dbt-duckdb`: a local file with no server or cost, suited to a
single-process batch run. Python, DuckDB, dbt and
adapter versions are pinned in `requirements.txt`. Raw is a
persistent table; staging is views and marts are tables, rebuilt in full at this volume.

Performance at the full GSS cumulative file (about 75,700 respondents and nearly 7,000
variables, up to roughly 530 million long rows if every variable were expanded) is not
assumed. Plan: benchmark build time and query plans on a scaled-up copy of these extracts,
and expand the long model only for chosen variables. The result goes in the report.

## 6. Loading

Each source file is loaded in one DuckDB transaction that replaces that file's rows in
`raw`, so a rerun, or loading the cuts in either order, gives the same result, and any error
rolls the file back (atomic, consistent, isolated and durable in ACID terms). An unchanged
file is skipped by its SHA-256, a fingerprint of its contents. A file with bad input
(missing or duplicate keys, a changed column set, or conflicting answers for a shared
respondent-year) is rejected, not partly loaded. Valid GSS missing codes are kept and
classified, and values that are invalid for their variable are caught by dbt tests. Loading
raw data and building the dbt models are separate steps: a dbt failure does not undo a
committed load. The full behaviour is described in the README and report.

## 7. Assumptions

1. `(year, id_)` identifies a respondent-year, and a respondent-year in several cuts has identical
   answers in all of them (true in this data).
2. `wtssnrps` is carried as the weight. Percentages are unweighted unless stated.
3. Zero answers in a year do not by themselves mean "not asked"; only an explicit `.y`
   does.
4. Coverage gaps (see the profile): `inttech` is unavailable in 2022; `news`, `tvhours`
   and `wwwhr` have no answers on ballot c; `postlife` and `reliten` are only about half
   answered in 2022 for a reason the extract does not show.
5. The waves are cross-sectional, so comparisons are descriptive and not about individuals.

## 8. Divergences

Where the build differs from this plan, and why.

| plan | built | why |
|---|---|---|
| `marts` would include a wide view for the six questions | Not built. The analyses read `fct_response` and `dim_respondent` directly | Each question needs two or three variables, which a filtered CTE gives just as clearly. A wide view would hard-code the six questions into the model, which the brief asks us not to do, and would need a new column for every new variable |
| Seeds would hold "the years and ballots where it is valid" | `ref_variable_validity`: one row per variable, year and ballot with `is_asked`. Derived from the extracts (any real answer there), not typed from the codebook | The export carries code metadata but no questionnaire design. Deriving it is reproducible and a test (`assert_validity_seed_matches_data`) fails if the seed and the data drift apart; the codebook remains the authority |
| One response type for `.i` (`inapplicable`) | `.i` on a ballot where nobody answered the question that year becomes `not_asked_on_ballot` (a derived classification, unverified against the questionnaires); elsewhere it stays `inapplicable` | The GSS uses `.i` for both "not on your ballot" and "did not apply to you". 10,576 response rows (ballot c for `news`, `tvhours` and `wwwhr` in all three years, and for `inttech` in 2016 and 2018) were otherwise indistinguishable from genuine inapplicability |
| Staging carries demographics through to `dim_respondent` | `dim_respondent` takes `sex`, `region`, `educ`, `age` and work status (`is_working`) from the classified long table; the value is null unless it is a real answer, with a `<variable>_response_type` column alongside | A special missing label in a demographic column could be grouped as if it were an answer |
| Percentages unweighted unless stated (assumption 2) | The analyses report weighted shares and means, and unweighted counts (`n`, `respondents`) for group sizes | Weighted shares estimate the population; unweighted counts show how much evidence sits behind each figure |
| Marts as plain tables | `fct_response` is written sorted by `variable_name`, `survey_year` | Every analysis filters on one variable; sorted rows let DuckDB skip row groups. On a 100× copy, Q1 read 8 of 129 row groups per scan instead of 129 (report, section 7); the copy tests the layout, not realistic full-scale performance |
| — | `fct_variable_coverage` (one row per variable, year and ballot) | Added so an analyst can see where each variable is answered without reading the profile |

Still as planned: the respondent-year key, the four layers, DuckDB, and the loader's
transaction-per-file behaviour.

Not resolved: in 2022 about half of every ballot (a, b and c alike) has `.i` for `postlife` and
`reliten`, while the other half answered. This looks like a split questionnaire form within ballots, which the
extract does not carry, so these stay `inapplicable`. The Q2 analysis says so.
