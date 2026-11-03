# Production sketch and extensibility (bonus, section 4.5)

A description, not built or deployed. It keeps the same code and dbt project and changes
where they run. Prices are approximate AWS list prices (us-east-1, late 2026) and should be
checked before relying on them.

## 1. Running on AWS at full scale

**Assumed scale:** the full GSS cumulative file (about 75,700 respondents, about 7,000
variables), a new wave every two years, plus the sources in section 2. The long response
table is about 530 million rows: at least 4 GB compressed, probably more, since that figure
comes from repeated test data (report, section 9).

```
Data Explorer export / other sources
        │  upload
        ▼
S3  landing/<source>/<extract>        (immutable, versioned)
        │  S3 event → EventBridge
        ▼
Step Functions:  load_raw  →  dbt build  →  dbt docs generate
                 (ECS Fargate tasks, one container image)
        │
        ▼
S3  warehouse/  Parquet, partitioned by source and survey_year
        │
        ▼
Athena workgroup (analysts)      dbt docs as a private S3 static site
```

| concern | choice | why |
|---|---|---|
| Where data is stored | **S3**: `landing/` holds exports exactly as received (versioning on, never overwritten); `warehouse/` holds every layer as Parquet, partitioned by `source` and `survey_year`, with `fct_response` sorted by `variable_name` as now | Cheap, durable storage; raw stays immutable, the brief's "preserve raw" rule enforced by the storage itself |
| What runs the transformations | **dbt-duckdb in an ECS Fargate task**, reading and writing the S3 Parquet files | The same dbt project with a different profile. Data of a few GB fits comfortably in one task (for example 4 vCPU, 16 GB), so no cluster is needed. If data or concurrent users outgrow one machine, switch the adapter to **dbt-athena** with Iceberg tables; the models stay the same |
| The loader | The same `load_raw.py` in the same image, reading from `landing/` | Keeps the SHA-256 skip, per-file transactions and validation that exist today |
| What schedules them | **EventBridge**: a new object in `landing/` starts a run; a monthly schedule runs anyway as a check. **Step Functions** runs the steps in order | Event-driven fits data that changes a few times a year; Step Functions gives retries, a visible history of every run, and stops on the first failure exactly like `run_pipeline.py` |
| Failure and rerun | A failed step (including a failing dbt test) stops the run and sends an SNS alert; rerunning the state machine is safe because every step is idempotent | Same behaviour as today, with alerting |
| Observability | CloudWatch Logs for each task; `load_log` and dbt `run_results.json` written to S3 and queryable in Athena | What ran, what it processed and why it failed, without logging into anything |
| How permissions are scoped | One IAM role per task, no long-lived keys: the **loader** reads `landing/` and writes only `warehouse/raw/`; the **dbt** role reads `raw/` and `reference/` and writes the other layers; **analysts** use an Athena workgroup that can read only `marts/` and `reference/` (Lake Formation if column-level control is needed). Buckets encrypted with KMS, public access blocked, S3 and ECR reached through VPC endpoints | Each part can do only its own job; a bug in dbt cannot change raw data |
| Secrets | None needed for S3 (IAM roles). Any future credential (for example a source API key) goes in **Secrets Manager** and reaches the task as an environment variable, as `profiles.yml` already expects | Nothing secret in code or images |

**What drives cost.** At this volume the bill is small and dominated by things that are easy
to get wrong rather than by data size:

| item | rough size | notes |
|---|---|---|
| S3 storage | about 10–20 GB, well under $1 a month | raw exports plus Parquet |
| Fargate | a run of tens of minutes, a few times a month: a few dollars | billed per second only while running |
| Athena | $5 per TB scanned | the cost that grows with use; Parquet, partitions and the sort by variable keep each query to megabytes |
| NAT gateway | about $30 a month if added | avoid it: VPC endpoints give the tasks S3 and ECR access without one |

Not included: Terraform. It would describe exactly the resources above; it is left out
because nothing here is deployed and the brief makes it optional.

## 2. Adding other sources

### Which sources, and why

| source | why it adds value | assumptions (volume, format, cadence, licence, access) |
|---|---|---|
| **American Time Use Survey** (US Bureau of Labor Statistics) | Measures minutes per day actually spent watching TV and on religious activities, from diaries. A check on the GSS's self-reported `tvhours` and a second view of religious practice | About 8,000–10,000 respondents a year; CSV microdata; annual; public domain; direct download |
| **Pew Research Center Religious Landscape Study** | Very large US religion survey (about 35,000 per wave): religion raised in, prayer, attendance, belief in life after death. Enough cases for the small groups that are weak in the GSS (Muslim, Hindu, Buddhist in Q1) | About 35,000 per wave; SPSS files; a wave every 7–10 years; free with registration, terms limit redistribution, so the files are stored privately and not committed |
| **World Values Survey** | The same concepts (importance of religion, prayer, attendance, media use) across about 60–90 countries, to set US results in context | About 90,000 respondents per wave; CSV or SPSS; a wave every 5 years; free for non-commercial use with registration |

### How each is ingested

Each source gets a small **reader** in `source/pipeline/` that turns its file format (CSV,
SPSS) into the same raw contract the GSS uses now: one row per respondent per extract, every
value as text, plus the loader's audit columns, and the source's own code metadata saved
alongside. Everything after that (SHA-256 skip, per-file transaction, validation,
`load_log`) is shared. Licence-restricted files are read from private storage, never
committed.

### How each is modelled alongside the GSS

- **Keys include the source.** `respondent_key = source | year | id`. Respondents are never
  linked across sources: these are separate samples.
- **One staging model per source** (`stg_atus__respondents`, `stg_pew__respondents`, …)
  maps into the same long shape and the same `response_type` values. Each source's missing
  codes are translated into those types through its own rows in `ref_codes`, which gains a
  `source` column.
- **A concept layer for comparison.** A version-controlled `ref_concepts` table maps each
  source variable and code to a shared concept and category, for example `religion_raised`:
  GSS `relig16` "Catholic" and Pew's raised-Catholic answer both map to `catholic`. A model
  `fct_concept_response` uses it. Mappings that lose detail (a 9-point attendance scale onto a
  6-point one) are flagged `is_approximate`, and differences in question wording are recorded
  in the mapping, so a comparison carries its caveats with it.
- **Weights stay within a source.** Each source keeps its own weight; shares are computed per
  source and compared side by side, never pooled into one total.

### How they are kept consistent

- Tests that every source code is either mapped to a concept or explicitly marked as
  unmapped, the same rule `assert_codes_are_never_guessed` applies to the GSS today.
- A validity seed per source, checked against the data as `assert_validity_seed_matches_data`
  does now.
- A reconciliation check per wave: weighted headline figures (for example the share raised
  Catholic) compared with the figures each source publishes, failing the build beyond a set
  tolerance.
- Each source's own documentation is the authority for what its codes mean; the mapping
  table records where it came from.
