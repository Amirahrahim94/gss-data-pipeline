# Production sketch and extensibility (bonus, section 4.5)

This is a proposal, not a deployed system: nothing here has been built or tested. The submitted
pipeline runs locally with Python, DuckDB and dbt. This note explains how it could run on AWS at
full scale and how other survey sources could be added.

## 1. Running on AWS at full scale

**Assumed scale:** the full GSS cumulative file (about 75,700 respondents and about 7,000
variables), a new wave about every two years, plus the sources in section 2. Expanding every
variable would give a long response table of about 530 million rows (report, section 9).

```
Data Explorer export / other sources
        |  upload
        v
S3 landing/  (original files, versioned)
        |  EventBridge starts a run
        v
Step Functions:  ingest  ->  dbt build and tests  ->  publish  ->  dbt docs
                 (Python in ECS Fargate; dbt sends its SQL to Athena)
        |
        v
Iceberg tables on S3, registered in the Glue Data Catalog
        |
        v
Analysts query published tables through an Athena workgroup
```

| Component | Proposed choice | Purpose |
|---|---|---|
| Source storage | **S3** | Preserve original extracts and their versions |
| Starting a run | **EventBridge** | A new upload starts the workflow; a scheduled check could be added |
| Ingestion | **Python in ECS Fargate** | Read, validate and prepare incoming files without maintaining a server |
| Workflow | **Step Functions** | Coordinate ingestion, transformation and checks in order, and show which step failed |
| Transformation | **dbt with Athena** | Build the analytical layers using AWS query compute |
| Analytical storage | **Iceberg tables on S3** | Support controlled table updates rather than manually replacing collections of Parquet files |
| Table catalogue | **Glue Data Catalog** | Register tables so Athena can find and query them |
| Operations | **CloudWatch and SNS** | Keep execution evidence and notify on failure |

The main design choice is Athena and Iceberg as the target, rather than promising that DuckDB
will handle the full workload inside one Fargate task. That promise would need benchmarking,
particularly when expanding thousands of variables into hundreds of millions of response rows.

**A simpler option to test first:** keep DuckDB in one larger Fargate task, write each run's
Parquet files to a new S3 folder, and point analysts to that folder only after the checks pass.
This would be cheaper and need less rewriting, but it depends on the full data fitting on one
machine. If a benchmark showed that it does, this option could replace Athena for the
transformations and Iceberg for storage.

If dashboards or heavy concurrent use appear, the published tables could move to a warehouse such
as Redshift or Snowflake. Terraform is not included: nothing here is deployed, and the brief makes
it optional.

### What can be reused and what must change

The existing project still provides reusable work: validation rules, missing-value semantics,
reference metadata, tests and analytical logic. However, the loader's storage handling, the dbt
adapter and some SQL would need adaptation and testing. For example, the current DuckDB
transactions and load log live inside one database file, so they do not carry over to S3 as they
are.

At full scale, I would also propose:

- Processing new or corrected survey waves without rebuilding every historical wave.
- Reading files in batches instead of parsing the entire cumulative export into Python memory.
- Expanding selected variables into the long model, with all-variable expansion tested separately
  if required.
- Recording processed file versions and preventing overlapping writes.
- Publishing results only after validation, with an explicit recovery procedure for failures.

### What happens during one run

1. A source file is uploaded to S3, and EventBridge starts the workflow.
2. The loader validates the file and checks whether that version has already been processed.
3. dbt builds the models and runs the data tests.
4. Only outputs that pass the checks are published for analysts.
5. The run keeps its evidence: CloudWatch logs, plus the load log and dbt's `run_results.json`
   saved to S3. A failure stops publication, leaves the previous published version available and
   sends a notification.
6. The dbt documentation is published as a private S3 static site.

### Permissions and credentials

Each task uses its own **IAM role** rather than permanent AWS keys:

- The **loader** reads `landing/` and writes only the raw layer.
- **dbt** reads the raw layer and reference data, and writes the prepared layers.
- **Analysts** use an Athena workgroup that can read only the published tables, with Lake Formation
  if column-level control is needed.

These roles mean a bug in dbt or an analyst's query cannot change the original files. Storage is
encrypted with KMS, with public access blocked. Any future source password or API key would be held in
**Secrets Manager**, never committed to Git.

### What would drive cost

No monthly total is claimed here: an estimate would follow a measured trial using current regional
AWS prices. The prices below are approximate and should be checked.

| Cost driver | What affects it | How to control it |
|---|---|---|
| **Athena** (about $5 per TB scanned) | Analyst queries and dbt builds, because dbt runs its SQL through Athena. This is the cost that grows with use | Parquet files within Iceberg tables, partitions by source and survey year, processing only changed waves, and a scan limit per workgroup so a bad query fails |
| **S3 storage** | Original files, tables and retained Iceberg snapshots | Clean up old snapshots on a schedule |
| **Fargate** | Billed for task running time | Tasks run only during a pipeline run; size them after testing |
| **CloudWatch Logs** | Volume and retention of logs | Set a retention period |
| **NAT gateway** (about $30 a month if added) | Networking that is easy to add by accident | Use VPC endpoints where possible |

## 2. Adding other sources

These are candidate sources, not sources already integrated. The figures below are assumptions:
before using a source, confirm its years, question wording, formats, access and redistribution
terms.

### Which sources, and why

| Source | Why it adds value | Assumed volume | Format | Cadence | Licence and access |
|---|---|---|---|---|---|
| **American Time Use Survey** (US Bureau of Labor Statistics) | Diary records give another view of time spent watching TV and on religious activities, alongside the GSS's self-reported `tvhours` | About 8,000–10,000 respondents a year | CSV | Annual | Public; direct download |
| **Pew Research Center Religious Landscape Study** | Evidence on religion raised in, prayer and attendance, including groups with few observations in these extracts (for example Muslim in Q1) | About 35,000 per wave | SPSS | Every 7–10 years | Free with registration; terms limit redistribution, so files stay private |
| **World Values Survey** | Places the US findings alongside results from other countries | About 90,000 respondents per wave | CSV or SPSS | About every 5 years | Free for non-commercial use with registration |

### How each is ingested and modelled

The aim is to reuse the processing approach while preserving the differences between surveys.

| Area | Proposed approach | Why it matters |
|---|---|---|
| Reading files | Add a reader for each required format, such as CSV or SPSS. Keep the original files and code metadata | Different sources do not necessarily arrive in the GSS format |
| Respondent identity | Include `source`, survey wave and the source's respondent ID in the key. Never link respondents across sources | The same ID in two surveys does not identify the same person |
| Staging | Give each source its own staging model, mapping into the same long shape and response types | Cleaning and interpretation depend on that survey's rules |
| Codes and missing values | Add source-specific reference metadata for labels, missing types and coverage | A code such as `9` may mean an answer in one survey and missing data in another |
| Shared concepts | Add a mapping table that connects comparable variables and categories | Analysts need a documented basis for comparisons |
| Weights | Calculate results within each survey using its own weights, and compare side by side | Separate samples should not be combined into one weighted total |

For example, GSS and Pew might both have a category meaning "raised Catholic". A mapping table
could connect them to a shared `religion_raised` category, recording the original questions and any
differences. Similar labels alone would not establish that the measures are equivalent.

### How they are kept consistent

- Check record counts and unique respondent keys for each source and wave.
- Check that every observed code has a documented meaning or is explicitly flagged as unmapped.
- Check observed coverage against the reference metadata, and use survey documentation to confirm
  eligibility and routing rules.
- Compare selected results with published source figures where definitions match. Investigate
  differences before setting an automated tolerance.
- Record any comparison that loses detail, such as grouping different response scales into broader
  categories.

Restricted source files stay in private storage and are not committed to the repository.
