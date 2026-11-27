# Cloud Data Fusion and Building Data Integration Flows

An e-commerce platform records orders via a Java application on Cloud Run, stores transactions in Cloud SQL, and exports daily CSV files to Cloud Storage. The analytics team wants to normalize dates, filter out invalid records, and load the data into BigQuery at 02:00. Maintaining custom cron jobs manually forces the team to own connectors, schema transformations, error handling, schedules, and data lineage.

**Cloud Data Fusion** is a **managed data integration service** for building ETL/ELT pipelines through a visual interface and source, transform, and sink plugins. It is built on the open-source **CDAP** platform and typically runs batch pipelines on **Managed Service for Apache Spark** clusters (referred to as Dataproc in older docs). Cloud Data Fusion simplifies managing integration flows, yet **it does not automatically guarantee data correctness, exactly-once loads, or zero cost when pipelines are idle**.

This lesson belongs to the **Data Pipelines and Processing** chapter of the `CLOUD_PROVIDERS_GCP` module. It builds on the Java/GCP concepts covered earlier—projects, IAM, VPC, Cloud Run, GKE, Cloud Storage, Pub/Sub, and databases—to select solutions, protect data sources, automate pipelines, and monitor reliability and cost. Examples use a lab project and **synthetic** order data without real PII.

## Learning Objectives

After this lesson, you will be able to:

1. Explain **instance → namespace → pipeline → run** and distinguish the design plane from the Spark execution plane.
2. Choose **batch ETL, streaming pipelines, or replication/CDC** based on latency requirements and data sources.
3. Build a **Cloud Storage → validate/transform → BigQuery** pipeline using Pipeline Studio and Wrangler.
4. Use **Preview, schemas, and error handling** to catch issues before deploying.
5. Use macros/runtime arguments for reusable pipelines and configure schedules and chaining.
6. Design **idempotency**, record-count checks, and safe reruns.
7. Configure service account permissions, VPC/Private Service Connect, and secret protection.
8. Monitor run logs/metrics/lineage and account for **both cost components: instance + execution**.

## 1. What Problems Does Cloud Data Fusion Solve?

Distinguish an **integration flow** from a transactional application:

| Need | Does Cloud Data Fusion fit? | Rationale |
| --- | --- | --- |
| Read GCS, clean CSVs, write BigQuery daily | **Yes** | Plugins, Wrangler, scheduling, centralized monitoring |
| Extract from JDBC/SaaS into a data warehouse | **Yes**, if compatible plugins/drivers exist | Broad source/sink support; may require private connectivity |
| Replicate certain databases to BigQuery | **Possibly**, via Replication/CDC per support matrix | Differs from batch snapshots/polling; verify source, version, and semantics |
| Process continuous Pub/Sub events | Has streaming plugins, though evaluate **Dataflow** | Latency SLAs, checkpoints, state, watermarks, and operations |
| Single SQL transform wholly inside BigQuery | **May not need** Data Fusion | BigQuery scheduled queries / Dataform are usually simpler |
| Run custom complex Spark algorithms | Consider **Managed Service for Apache Spark** directly | Full control over Spark code and tuning |
| Orchestrate dozens of multi-service tasks with dependencies | Consider **Cloud Composer / Workflows** | Data Fusion designs transforms; it does not replace general orchestrators |

**Never pick a tool solely for its drag-and-drop UI.** Evaluate schema/connector support, latency, data governance, team skills, and operational cost.

## 2. Architecture: Studio vs. Execution Engine

~~~mermaid
flowchart LR
    USER["Data engineer"] --> UI["Cloud Data Fusion Studio<br/>design, preview, deploy"]
    UI --> META["Instance / namespaces<br/>pipelines, configs, metadata"]
    META --> RUN["Pipeline run"]
    RUN --> SPARK["Managed Spark cluster<br/>customer project"]
    GCS[("Cloud Storage<br/>raw files")] --> SPARK
    DB[("Cloud SQL / SaaS<br/>optional source")] --> SPARK
    SPARK --> BQ[("BigQuery<br/>staging / curated")]
    RUN --> OBS["Run logs / metrics / lineage"]
    SPARK --> OBS
~~~

- **Control/design plane:** Cloud Data Fusion instance hosting Studio, the plugin catalog, namespaces, pipeline definitions, and runtime preferences; service components run in a Google-managed **tenant project**.
- **Execution plane:** batch pipelines compile into jobs on **Managed Service for Apache Spark**. By default, Cloud Data Fusion provisions an ephemeral cluster in the **customer project** and deletes it after completion. You can select other compute profiles or pre-configured clusters where supported.
- **Sources/sinks:** GCS, BigQuery, JDBC, Pub/Sub, and other plugins. Some BigQuery sinks stage through **Cloud Storage**, so the execution identity needs appropriate permissions there.
- **Metadata/lineage:** tracks schema and data flow where supported by plugins, regions, and configuration; lineage alone does not verify business-value correctness.

### 2.1. Do Not Confuse Configuration Levels

| Component | Scope |
| --- | --- |
| **Instance** | A Data Fusion deployment with an **edition, region, and public/private networking** |
| **Namespace** | Logical grouping holding pipelines, artifacts, preferences, and user configs |
| **Pipeline** | Graph of sources → transformations → sinks, saved and deployed |
| **Plugin** | Reusable building block: source/transform/sink/action/error handler |
| **Compute profile** | Selects how Spark infrastructure is provisioned for execution |
| **Run** | A specific execution with timestamps, runtime arguments, logs/metrics, and a **RunID** |

**A deployed pipeline does not mean data has been loaded.** Outcomes must be verified via run status **and actual sink data**.

## 3. Batch, Streaming, and Replication: Three Distinct Modes

| Mode | Input data | Latency | Key considerations |
| --- | --- | --- | --- |
| **Batch** | Daily files, JDBC snapshots, periodic datasets | Minutes/hours | Reruns, backfills, partitioning, idempotent sinks |
| **Streaming** | Pub/Sub/Kafka, continuous events | Seconds/minutes depending on architecture | Ordering, checkpoints, retries, late data, state, 24/7 cost |
| **Replication/CDC** | Source DB change logs (supported sources) | Near real time per configuration | Initial snapshot, log retention, schema evolution, update/delete semantics |

**CDC is not running `SELECT *` every minute.** Replication requires understanding primary keys, capture mechanisms, and offset tracking. Supported capabilities/connectors depend on database type and Cloud Data Fusion version; never assume every JDBC database supports CDC.

In this lab, we use **batch** because it is simple and easy to verify. Data Fusion can be used for streaming when appropriate, yet **it does not automatically achieve exactly-once business effects** when sinks or external systems fail; always analyze delivery, commit, and retry semantics.

## 4. Designing the Data Contract Before Dragging and Dropping

Synthetic source: daily orders CSV for `2026-11-19`.

~~~csv
order_id,sales_region,amount_vnd,order_date
o-1001,APAC,120000,2026-11-18
o-1002,EMEA,95000,2026-11-18
o-1003,APAC,-5000,2026-11-18
o-1004,APAC,50000,2026-11-18
~~~

**Output contract** for table `etl_lab.orders_stage`:

| Column | BigQuery type | Rule |
| --- | --- | --- |
| `order_id` | STRING | Non-empty; business key |
| `sales_region` | STRING | Normalized value, e.g., `APAC`/`EMEA` |
| `amount_vnd` | INT64 | Parsed from CSV string; **must be greater than 0** |
| `order_date` | DATE | ISO date `YYYY-MM-DD` |

Expected result: **3 valid records**, with `o-1003` rejected due to negative amount. Real systems need a **quarantine/DLQ** process for bad records rather than silently dropping them. For refund revenue, negative amounts might be **valid**; the rule here applies specifically to the assumed `OrderCreated` event type.

**Security:** use only synthetic order IDs; never put real customer names, emails, or addresses in samples or logs.

## 5. Preflight: APIs, Region, Edition, and Accounts

Prerequisites: a lab project with billing enabled, approved resource-admin permissions, and Cloud Storage / BigQuery / Managed Service for Apache Spark APIs and networking configured as needed. Every `create` command below **makes real changes and may incur charges**.

Start with **read-only** commands:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud beta data-fusion instances list \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud beta data-fusion operations list \
  --project=PROJECT_ID \
  --location=asia-southeast1

bq ls --project_id=PROJECT_ID
~~~

`gcloud beta data-fusion` is a **beta** command group documented in the Cloud SDK; verify `--help` against your installed CLI version. The Console can also be used instead of the CLI.

### 5.1. Choosing an Edition

| Edition | Typical scenario | Considerations |
| --- | --- | --- |
| **Developer** | Experimentation, learning, small prototypes | Limited throughput and concurrency |
| **Basic** | Sandboxes, PoCs, moderate workloads | Lacks granular RBAC found in Enterprise |
| **Enterprise** | Multiple teams, critical pipelines, granular access control | **RBAC**, higher management cost |

**The edition is fixed at instance creation and cannot be changed in place.** Moving editions requires creating a new instance and migrating per documentation. **Private instances** use private connectivity; Google Cloud recommends Private Service Connect (PSC) for architectures requiring strong network boundaries.

### 5.2. Creating a Lab Instance — Only If None Exists

~~~bash
# Incurs cost; verify project and permissions before running.
gcloud services enable \
  datafusion.googleapis.com \
  dataproc.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  --project=PROJECT_ID

gcloud beta data-fusion instances create df-orders-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --edition=basic \
  --enable_stackdriver_logging
~~~

This example uses a **public/basic lab** for simplicity; **production should evaluate private instances/PSC, RBAC, and network controls** rather than copying lab defaults. Creating an instance takes time, quotas, and service account permissions; once ready, click **Cloud Data Fusion → Instances → View Instance** to open Studio.

**Do not delete and recreate an instance just to test a pipeline**: deleting an instance destroys its pipeline definitions, config, and metadata with no direct recovery.

## 6. IAM: The Designer Differs from the Spark Execution Account

Cloud Data Fusion typically involves two identities:

- **Cloud Data Fusion API service agent** (Google-managed, design/control plane), requiring its dedicated service-agent role such as `roles/datafusion.serviceAgent`. **Never assign service-agent roles to users or regular apps.**
- **Execution-time service account** for the Spark cluster, which may default to the Compute Engine default SA. Prefer a **user-managed service account** with least-privilege permissions scoped to sources and sinks.

Example scoped permission matrix:

| Component | Permissions to review |
| --- | --- |
| Data Fusion instance admin | `roles/datafusion.admin` or equivalent at instance/project scope |
| Execution identity running Data Fusion/Spark | `roles/datafusion.runner`, plus corresponding Spark cluster permissions per configuration |
| GCS raw bucket | `storage.objects.get/list` for source files |
| GCS temporary/staging bucket | Object read/write/delete permissions required by Spark and BigQuery sink plugins |
| BigQuery job project | `bigquery.jobs.create` |
| BigQuery target dataset | Table creation / data write (`bigquery.tables.create`/`updateData`) as needed |
| Cloud SQL/JDBC source | Network route + read-only DB user, matching driver/credentials |
| Pipeline developer | Design/deploy permissions scoped to instance/namespace; should not imply Viewer on all PII |

`roles/datafusion.runner` **does not automatically grant** GCS file reads or BigQuery writes. Exact Spark cluster / Dataproc worker roles also depend on **compute profile, project, and service version**; verify against runtime permission errors.

In **Enterprise RBAC**, grant namespace/application/plugin permissions by role; a namespace is only a **logical grouping**, not a strong security boundary replacing projects, VPCs, and IAM.

## 7. Lab: Preparing GCS Inputs and BigQuery

**Use a lab project only.** Bucket names must be **globally unique**; replace the `UNIQUE` suffix with a real unique string. Keep all resources in `asia-southeast1` to avoid unexpected location errors or egress charges.

Create `orders.csv` on your lab machine:

~~~bash
cat > orders.csv <<'CSV'
order_id,sales_region,amount_vnd,order_date
o-1001,APAC,120000,2026-11-18
o-1002,EMEA,95000,2026-11-18
o-1003,APAC,-5000,2026-11-18
o-1004,APAC,50000,2026-11-18
CSV
~~~

Create two buckets (raw and temporary staging) and the dataset:

~~~bash
gcloud storage buckets create gs://PROJECT_ID-df-raw-UNIQUE \
  --project=PROJECT_ID --location=asia-southeast1

gcloud storage buckets create gs://PROJECT_ID-df-temp-UNIQUE \
  --project=PROJECT_ID --location=asia-southeast1

gcloud storage cp orders.csv \
  gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv

bq --location=asia-southeast1 mk --dataset \
  PROJECT_ID:etl_lab
~~~

If resources already exist, **check ownership, location, and permissions, and do not overwrite them**. Grant read access on the raw bucket and read/write on the temp bucket to the execution identity; the Studio designer does not have to be the principal reading/writing data inside the Spark job.

Create an empty **staging table** via BigQuery Studio (replace `PROJECT_ID`; run in `asia-southeast1`):

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.etl_lab.orders_stage` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  order_date DATE
);
~~~

Table names in SQL require backticks as shown; use **a dedicated lab dataset** because sinks may append rows or alter schemas depending on settings. Never run `CREATE OR REPLACE` against real data.

## 8. Designing the Pipeline in Pipeline Studio

In Console: **Cloud Data Fusion → Instances → View Instance → Studio → Pipeline Design**. Create a **Batch pipeline** named `orders_gcs_to_bq_lab` in an appropriate lab namespace.

~~~mermaid
flowchart LR
    SRC["Cloud Storage Source<br/>orders.csv"] --> PARSE["CSV parse / schema"]
    PARSE --> VALID["Wrangler + Filter<br/>amount_vnd > 0"]
    VALID --> SINK["BigQuery Table Sink<br/>orders_stage"]
    VALID -. "invalid" .-> BAD["Quarantine / error sink<br/>when configured"]
~~~

Steps:

1. **Source: Cloud Storage** — set path `gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv`, format **CSV**, UTF-8 encoding, and **Use first row as header = true**. The plugin may need an explicit schema if type inference is inaccurate.
2. **Parse / Schema** — confirm four columns. `amount_vnd` must be **long/int** and `order_date` must be **date** at output; if the source reads everything as STRING, cast types in Wrangler/Projection before the sink.
3. **Wrangler** — trim whitespace, parse/cast types, validate values, and build the recipe. For this example, filter out rows with `amount_vnd <= 0` or route them to a restricted-access **error path**.
4. **BigQuery Table sink** — select the right project, dataset `etl_lab`, table `orders_stage`, schema matching all four fields, and the staging Cloud Storage bucket. Verify the **write mode** (append/overwrite or plugin-specific behavior) before running.
5. **Validate** each plugin and stage connection; check field names, types, plugin properties, and execution identity.
6. **Preview** against sample data, inspect errors, and fix while still in Draft.
7. **Deploy → Run** in the lab project; watch `Provisioning → Starting → Running → Succeeded` and then verify the BigQuery table.

**No single plugin configuration applies to every version:** field names, CSV parser options, BigQuery sinks, and Studio UI vary across releases. If the output schema mismatches, **never bypass validation to run the job**—check plugin docs and fix the recipe/sink.

## 9. Wrangler, Preview, and Data Quality

**Wrangler** lets you interactively build a sequence of **directives** to parse, rename, cast, filter, or transform a sample dataset. A **recipe** is that set of directives; when attached to a pipeline, the logic executes across the full data flow.

Notes:

- **Preview typically samples only the first 100 records** from the source in Studio; a clean sample **does not prove the entire file is error-free**.
- Once deployed, the batch pipeline processes **all data matched by the source**, not just the preview sample.
- Casting `"abc"` to INT64, invalid date formats, or renamed columns can trigger **parse errors or pipeline failures**; configure error handlers/quarantine instead of silently dropping rows.
- An **error sink** should capture `source_file`, `record_id`, `reason`, and processing timestamp where supported—never storing raw PII payloads or credentials.
- Add **data quality gates**: input rows = valid rows + error rows (when no intentional drops exist); check uniqueness, non-null constraints, and currency/range rules.

### 9.1. Expected Lab Output Data

| order_id | sales_region | amount_vnd | order_date | Outcome |
| --- | --- | ---: | --- | --- |
| o-1001 | APAC | 120000 | 2026-11-18 | Valid |
| o-1002 | EMEA | 95000 | 2026-11-18 | Valid |
| o-1003 | APAC | -5000 | 2026-11-18 | Filtered/quarantined per lab rule |
| o-1004 | APAC | 50000 | 2026-11-18 | Valid |

**Expected single-run state:** three rows in `orders_stage` when starting with an empty table and no duplicate writes. Seeing four rows means the filter was not applied. Seeing zero rows means you should check run logs, schema, source path, and sink errors.

## 10. Verifying the Sink with BigQuery SQL

After the run reports `Succeeded`, run **read-only** queries:

~~~sql
SELECT
  order_id, sales_region, amount_vnd, order_date
FROM `PROJECT_ID.etl_lab.orders_stage`
ORDER BY order_id;

SELECT
  COUNT(*) AS rows_loaded,
  COUNTIF(amount_vnd <= 0 OR amount_vnd IS NULL) AS invalid_amount,
  COUNT(DISTINCT order_id) AS distinct_orders,
  SUM(amount_vnd) AS total_vnd
FROM `PROJECT_ID.etl_lab.orders_stage`;
~~~

Result after **one clean run**:

~~~text
rows_loaded = 3
invalid_amount = 0
distinct_orders = 3
total_vnd = 265000
~~~

If the table already held data from an earlier run, these numbers will differ. **Never conclude a job failed** before confirming the staging table started empty or was isolated for that test run.

When strict **schema governance** is required, manage schemas in source control (DDL) and validate changes in staging before running against production.

## 11. Retries and Reruns: "Pipeline Succeeded" Does Not Mean Exactly-Once

A failure can happen after a sink commits successfully but before the run records its final status, or an operator may intentionally **rerun** the same input. If the sink is in **append** mode, rows can appear **twice**.

~~~text
Run 1: 3 rows written to orders_stage → succeeds
Run 2: reads same file → appends 3 more rows

orders_stage: 6 rows, yet only 3 business order_ids.
~~~

**Principle:** distinguish **at-least-once execution/retries** from **exactly-once business effects**. Use one of these strategies:

- **Partition overwrite / snapshot replacement** when the entire dataset can be rebuilt within a controlled write scope.
- **Landing/staging + BigQuery `MERGE`** on business keys.
- **Run ID / source object generation / watermark** to track which inputs have already been processed.
- **Deduplicate** by primary key + explicitly ordered event version/timestamp.
- **Checkpoints/offsets** for streaming/CDC where supported by plugins, paired with an idempotent sink.

Simple example to **deduplicate when promoting from staging to a curated table** (do not use directly as a full CDC algorithm):

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.etl_lab.orders_curated` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  order_date DATE
);

MERGE `PROJECT_ID.etl_lab.orders_curated` AS T
USING (
  SELECT order_id, sales_region, amount_vnd, order_date
  FROM `PROJECT_ID.etl_lab.orders_stage`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY order_date DESC, amount_vnd DESC
  ) = 1
) AS S
ON T.order_id = S.order_id
WHEN MATCHED THEN UPDATE SET
  sales_region = S.sales_region,
  amount_vnd = S.amount_vnd,
  order_date = S.order_date
WHEN NOT MATCHED THEN
  INSERT (order_id, sales_region, amount_vnd, order_date)
  VALUES (S.order_id, S.sales_region, S.amount_vnd, S.order_date);
~~~

In the lab, even if staging has 6 rows after a rerun, curated still holds **3 order IDs**. In production, selecting the "latest" version must rely on a **trusted `event_version`/`updated_at`**; ordering by `amount_vnd DESC` here only breaks ties across identical demo rows and is **unsuitable for resolving real business updates**.

**Never blindly run two concurrent `MERGE` jobs against the same target**: use orchestration, idempotency, and job concurrency controls. Continuously growing staging tables also need retention, partitioning, and cleanup policies.

## 12. Macros and Runtime Arguments for Reusability

Instead of duplicating a pipeline for every file or date, use **macros** in plugin properties marked with the macro indicator (`M`), for example:

~~~text
Cloud Storage Source Path:
  ${input_path}

BigQuery Sink Table:
  ${target_table}

A run with:
  input_path=gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv
  target_table=orders_stage
~~~

A macro is a **runtime substitution placeholder**; the exact syntax is `${input_path}` (no space between `$` and `{`). Use **preferences** for shared config and **runtime arguments** for per-day files and tables.

For secrets, use **secure macros** / secure storage per plugin support:

~~~text
${secure(db_password)}
~~~

Never put **real passwords** into plain runtime arguments, Git repositories, pipeline JSONs, or Logs Explorer. For JDBC, keep connections/credentials in **secure keys / Secret Manager integrations** as supported by your version, scoped strictly to the execution identity.

### 12.1. Identifying Runs for Traceability

A batch run should record:

- `run_id` to correlate logs, outputs, and incidents.
- `input_path`, and for GCS consider **object generation** to distinguish overwritten files.
- `source_system`, `source_extract_time`, and `schema_version`.
- `rows_read`, `rows_valid`, `rows_quarantined`, `rows_written`.
- `start_time`, `end_time`, `compute_profile`, `pipeline_version`.

**Never generate `run_id` using local timestamps inside separate stages**, which breaks correlation across a single run. Pass one stable ID across the entire pipeline invocation.

## 13. Scheduling and Orchestrating Multiple Pipelines

After **Deploy**, Data Fusion Studio supports:

- **Run:** manual execution.
- **Schedule:** periodic batch execution on a cron schedule.
- **Incoming triggers:** triggers a downstream pipeline upon upstream completion status.
- **REST API / Git-backed lifecycle:** supports CI/CD and external orchestration outside Studio.
- **Cloud Composer:** ideal when coordinating multiple Data Fusion pipelines, BigQuery jobs, Cloud Run tasks, or external systems.

Example flow:

~~~mermaid
flowchart TD
    A["02:00 - Data Fusion raw → staging"] --> B{"Pipeline succeeded + quality gate?"}
    B -->|Yes| C["BigQuery MERGE → curated"]
    B -->|No| D["Alert + quarantine + stop downstream"]
    C --> E["BI / report"]
~~~

**Warning:** a schedule does not guarantee source files have arrived. If today's source is missing, the pipeline may fail or reprocess yesterday's file. Use upstream dependencies or file sensors in approved orchestration and check object dates and generations.

### 13.1. CI/CD for Pipelines

Store **pipeline definitions, plugin versions, schemas, and macros** in source control. Recommended workflow:

1. Use a **dev** namespace/project for design and Preview.
2. Test against clean data, bad records, schema changes, missing credentials, reruns, and duplicate sources.
3. Review plugin packages and network/IAM settings.
4. Deploy approved versions to staging, then production.
5. Use **runtime arguments/secrets**—never hardcode environment values in pipeline JSON.
6. Record versions, RunIDs, and quality results; keep rollback plans for both pipeline definitions and target tables.

Editing a deployed pipeline can create a **new runtime version**; never assume everyone is running the expected version based solely on pipeline name.

## 14. Secure Connectivity: VPC, PSC, Cloud SQL, and External Sources

~~~mermaid
flowchart LR
    UI["Studio instance<br/>private networking"] --> PSC["PSC / VPC connectivity"]
    PSC --> EXEC["Spark execution<br/>customer project/VPC"]
    EXEC --> SQL[("Private Cloud SQL")]
    EXEC --> GCS[("Cloud Storage")]
    EXEC --> BQ[("BigQuery")]
    EXEC -. "when authorized" .-> ONPREM["On-prem via VPN / Interconnect"]
~~~

When handling sensitive data:

- Evaluate a **private Data Fusion instance**; Google Cloud recommends **Private Service Connect** (VPC peering may also apply depending on architecture/version).
- The Spark execution cluster also needs a **private network path** to sources: VPC, subnet, firewall rules, DNS, private IP/PSC, and **Cloud NAT / Google APIs access** where needed.
- JDBC to Cloud SQL requires dedicated **DB authentication** (username/secret or IAM DB auth per engine) on top of Google Cloud IAM and network routing.
- Keep sources and sinks in aligned regions to avoid **data residency** risks and egress charges.
- Never allowlist public IPs broadly just to bypass permission errors; protect secrets and logs.
- If your organization uses **VPC Service Controls**, verify service perimeters across Data Fusion, Spark, GCS, BigQuery, and supporting services per product support.

**IAM governs API access; VPC/PSC governs network paths; DB credentials govern database access.** All three layers must be verified independently.

## 15. Compute Profiles, Spark Tuning, and Pushdown

Default **Spark execution** scales processing well, though it incurs cluster provisioning time and compute charges.

| Issue | What to inspect |
| --- | --- |
| Small pipeline takes several minutes waiting | Spark cluster provisioning/startup time; consider running directly in BigQuery SQL |
| Spark executor OOM | Schema, skew, memory/executor settings, partition count |
| Single huge source/file | Partitioning/splits, Parquet/Avro formats, parallel reads |
| Slow Join/GroupBy | Shuffle, skewed keys, worker count, pushdown where supported |
| Slow BigQuery sink | GCS staging, BigQuery load jobs, quotas, region, schema |
| Cluster created in wrong project | Compute profile/project, runtime identity, network |
| Streaming misses latency targets | Checkpoints/state/backpressure, or consider Dataflow |

Certain transformations can **push down to BigQuery** when source, sink, transform plugins, and configurations are compatible. Pushdown reduces Spark compute while shifting part of the cost to **BigQuery slots / bytes processed**; **benchmark** before and after rather than assuming enabling it is always cheaper.

**Never add worker nodes blindly:** the real culprit may be the driver JVM, a hot key, malformed input, BigQuery quotas, or IAM permissions. Monitor CPU, executor memory, stage durations, and provisioning time separately.

## 16. Logs, Metrics, Lineage, and Alerting

In **Data Fusion Studio → deployed pipeline → Summary / Run history**, inspect **RunID**, status, row counts, and per-stage timings. Open **Logs** and filter `Error/Warning/Info/Debug`; inspect **advanced logs** when diagnosing cluster/Spark issues.

With **Cloud Data Fusion 6.11+**, pipeline and service logs can be viewed via **Cloud Logging** per instance features and config; cluster logs also have dedicated resource views. Some older versions require explicitly enabling **Dataproc / Managed Spark Cloud Logging**. Never assume all logs appear automatically if logging wasn't enabled.

| Signal | Control |
| --- | --- |
| Pipeline run `Failed` / `Succeeded` | Alert on run status and schedule misses |
| Run duration & provisioning time | Separate Spark startup time from data processing time |
| `rows_read`, `rows_written` | Reconcile completeness and duplicates |
| `rows_quarantined` / error ratio | Data quality gate; never hide schema errors |
| Stage latency / records per second | Pinpoint plugin/source/sink bottlenecks |
| Spark CPU/memory, cluster/job logs | Catch OOMs, driver/executor failures, quotas |
| BigQuery load/query jobs, GCS bytes | Verify sink behavior and billing |
| Metadata/lineage | Assess impact of schema/source changes and trace bad data |
| Cost by SKU, RunID/time window | Track TCO per pipeline |

**When a run reports `Succeeded` yet BigQuery has too few rows**, do not stop at the status badge: a filter may be wrong, the source path misconfigured, or a data quality gate missing. The SQL check in Section 10 is mandatory.

### 16.1. Practical Error-Handling Workflow

1. Record **instance, namespace, pipeline name/version, RunID, project, and UTC timestamp**.
2. Inspect the **failing stage** in Studio. Starting in 6.11, errors can be viewed by category, reason, and message.
3. Read pipeline logs and advanced/Spark logs as needed.
4. Classify the failure across **source / credentials / network / schema / transform / sink / quota**.
5. Fix the root cause in dev/staging and rerun **idempotently** against stable inputs.
6. Compare input/output/error counts, latency, and cost, then update the incident/owner.

Never log JDBC passwords or raw PII payloads while debugging. Error records need enough correlation IDs without leaking secrets.

## 17. Cloud Data Fusion Costs: Beyond Just Pipeline Run Time

Per published pricing, Data Fusion charges split into **instance development/management** and **pipeline execution**:

| Component | How charges accrue |
| --- | --- |
| **Data Fusion instance** | Billed continuously from **creation** to **deletion**, even when no pipelines run |
| **Spark execution** | Managed Service for Apache Spark / Compute Engine VMs and disks by configuration and runtime |
| **Cloud Storage** | Raw/staging files, reads/writes, storage |
| **BigQuery** | Storage, loads/queries, and quotas/slots per billing model |
| **Networking** | Egress, VPC/PSC/Cloud NAT/Interconnect where used |
| **Logging/Monitoring** | Log ingestion/storage and monitoring per service |
| **Other sources/sinks** | Cloud SQL, SaaS APIs, Pub/Sub, connector resources |

At the time of pricing review (2026), reference edition rates in USD are **Developer $0.35/hour, Basic $1.80/hour, Enterprise $4.20/hour**, with **Basic including the first 120 hours/month per account free** under pricing terms. **Do not assume those 120 hours cover Spark/VMs/BigQuery or apply across every account unconditionally.** Rates, terms, and billing currencies can change; verify current [Data Fusion pricing](https://cloud.google.com/data-fusion/pricing) and Billing SKUs before committing.

Illustrative development cost example after exhausting Basic free hours:

~~~text
One Basic instance running 24 hours:
  Development = 24 × $1.80 = $43.20 (illustrative)

Pipeline runs hourly, 15 minutes/run:
  24 runs × 0.25 hours = 6 hours of Spark cluster runtime

Total = Data Fusion instance charge
      + Managed Spark / Compute Engine / disks
      + GCS / BigQuery / networking / logging...
~~~

Never treat `$43.20` as your **total ETL bill**. Instances keep billing while idle; temporary Spark clusters stopping does not pause instance charges. Cloud Billing budget alerts **do not automatically stop resources or cap spending**.

## 18. Common Troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Cannot create Data Fusion instance | APIs, quotas, service agent, region/edition | Check IAM/operations and quotas |
| Studio opens, yet Spark cluster fails to start | Runtime SA / `datafusion.runner`, Spark permissions, compute quota | Inspect Cloud Logging, IAM, quotas |
| Cannot read GCS | Path, bucket, object permissions, region/connector | Verify source path and execution identity |
| JDBC source times out | VPC/PSC/DNS, firewall rules, DB auth/driver | Separate network connectivity from DB credentials |
| Wrangler Preview succeeds, Run fails | Preview only samples; schema error sits later in the file | Add error handlers/quarantine; inspect full file |
| BigQuery sink reports access denied | Missing `jobUser` / dataset permissions / staging bucket access | Verify Spark execution identity permissions |
| BigQuery load schema mismatch | Type/date parsing, nulls, field mapping | Align schemas across source/transform/sink |
| Reruns create duplicates | Append sink without deduplication/idempotency | `MERGE` on event key, run ID, and backfill plan |
| Pipeline too slow for tiny data | Spark startup dominates runtime | Consider BigQuery SQL or a simpler service |
| Spark OOM / shuffle bottleneck | Skew, partition sizing, memory | Tune keys, memory, executors, and dataset layout |
| `Succeeded` yet rows are missing | Overly strict filter or wrong source glob | Compare record counts, quality gates, and BigQuery queries |
| High bill with no jobs running | Data Fusion instance left running | Check instance hours; delete approved idle labs |

**Never fix issues by granting project-wide Owner/Editor or exposing databases publicly.** Identify the exact principal, permission, network route, and failing stage.

## 19. End-to-End Scenario: Multi-Source Order Data

The Commerce team runs a Java Order API on Cloud Run, Cloud SQL PostgreSQL, partner CSV files in GCS, and dashboards on BigQuery. Goals:

- Load new partner files nightly, clean data, and reconcile row counts.
- Sync order updates from Cloud SQL in near real time when needed.
- Strip PII from analyst datasets and preserve lineage.
- Prevent duplicate orders on retries or backfills.

**Proposal:**

~~~mermaid
flowchart LR
    GCS["Partner CSV in GCS"] --> DF["Data Fusion batch<br/>parse + quality"]
    SQL[("Cloud SQL")] -. "CDC if compatible" .-> CDC["Replication / Datastream"]
    DF --> STAGE[("BigQuery staging")]
    CDC --> STAGE
    STAGE --> MERGE["MERGE / dedupe / audit"]
    MERGE --> CURATED[("BigQuery curated")]
    CURATED --> BI["BI dashboards"]
~~~

Step-by-step decisions:

1. Define schemas, business keys, read/write permissions, and data quality rules.
2. Test **one batch pipeline lab** with three valid rows and one quarantined row.
3. Add runtime arguments, date partitioning, and `order_id`/`event_version` keys.
4. Put idempotent staging + `MERGE` in place, avoiding unordered direct updates to curated from two sources.
5. For CDC, compare **Cloud Data Fusion replication** against **Datastream + Dataflow/BigQuery** across supported sources, latency, DDL handling, and cost.
6. Set up run-level and record-level monitoring, IAM audits, and lineage tracking.
7. Evaluate TCO before upgrading editions or cluster sizes.

**Never allow partner CSVs to overwrite canonical transactional orders** without source-priority/versioning rules and business reconciliation.

## 20. Hands-On Exercises and Self-Check

**Exercise 1 — GCS → BigQuery pipeline.** Build the pipeline following Sections 7–10.

*Pass criteria:* one run from the lab file produces **3 valid rows**, totaling `265000`, with the negative-amount error explained/quarantined.

**Exercise 2 — Rerun.** Re-run the input with an `append` sink, comparing `orders_stage` and `orders_curated` after `MERGE`.

*Pass criteria:* staging grows to 6 rows; curated still contains **only 3 order IDs**. Explain why `MERGE` should not pick the largest monetary value in production.

**Exercise 3 — Runtime macros.** Point `input_path` to another file in the same pipeline without creating a new pipeline.

*Pass criteria:* each run reads the right source, logs capture `run_id`/`input_path`, and no secrets appear in plain runtime arguments.

**Exercise 4 — IAM.** The runtime SA can read GCS but fails to write BigQuery. List what to check.

*Answer:* `bigquery.jobs.create` in the job project, table creation/write permissions in the dataset, staging bucket access, and the actual execution identity.

**Question 5.** Once a pipeline is deployed, has it already run and loaded data?

*Answer:* No. You must trigger/run it, monitor run status, and verify the sink.

**Question 6.** Cloud Data Fusion uses Spark as its default batch engine; does that mean compute is free?

*Answer:* No. Spark clusters, VMs, and disks incur charges separate from the Data Fusion instance.

**Question 7.** Preview shows 100 clean sample rows; does that guarantee the whole dataset is clean?

*Answer:* No. Preview only samples data; enforce quality gates across the full dataset.

**Question 8.** Are batch and CDC the same thing?

*Answer:* No. Batch reads periodic files or snapshots; CDC streams DB changes subject to source/connector support.

**Question 9.** Does rerunning a pipeline after an ACK/timeout failure guarantee no duplicate loads?

*Answer:* No. You need sink idempotency/`MERGE`, checkpoints, and business keys.

**Question 10.** Can namespaces replace IAM and project isolation for confidential data?

*Answer:* No. Namespaces are logical groupings; strong security boundaries require IAM, networking, and project controls.

**Question 11.** Cloud SQL uses a private IP, yet execution Spark has no route to the VPC. Is granting a DB Reader user enough?

*Answer:* No. You need network routing and DB authentication alongside IAM.

**Question 12.** Can a Cloud Data Fusion Basic instance left idle for 24 hours still incur charges?

*Answer:* Yes, by instance hours (outside eligible free-tier hours), regardless of whether any pipelines run.

**Question 13.** When a pipeline reports `Succeeded` but rows are missing, what should you check?

*Answer:* Source selection, Filter/Wrangler logic, error handling, row counts, and sink queries.

**Question 14.** Should a workload that only runs daily SQL inside BigQuery choose Data Fusion by default?

*Answer:* No. Compare BigQuery scheduled queries or Dataform, which are often simpler and cheaper.

## 21. Pre-Production Checklist

- [ ] Defined batch/streaming/CDC mode, freshness SLA, and data owner.
- [ ] Chose Data Fusion over Dataflow/BigQuery SQL/Composer based on actual workload requirements.
- [ ] Selected appropriate edition/region, private VPC/PSC, and compute profile.
- [ ] Separated IAM for design-time service agent, execution SA, datasets, buckets, and DB users.
- [ ] Stored JDBC/credentials securely; no hardcoded secrets in pipelines.
- [ ] Defined input schemas, data quality rules, error quarantine, and row reconciliation.
- [ ] Established idempotency, backfill, and rerun plans; staging and curated layers are protected.
- [ ] Used Preview only for early checks; tested full files and edge cases in staging.
- [ ] Version-controlled pipeline definitions, plugins, schemas, and runtime arguments.
- [ ] Paired schedules/triggers with upstream dependencies, file-readiness checks, and quality gates.
- [ ] Monitored RunIDs, records in/out/error, latency, Spark errors, and lineage.
- [ ] Measured CPU/memory, Spark startup, and BigQuery bytes; optimized before scaling clusters.
- [ ] Budgeted combined instance + Spark/VM/disk + GCS/BQ/network/logging costs.
- [ ] Enforced cleanup/retention for staging files, run records, and lab instances.
- [ ] Practiced handling bad inputs, missing IAM, source DB timeouts, duplicate reruns, and rollbacks.

## 22. Conclusion

**Cloud Data Fusion** streamlines designing and operating ETL/ELT via plugins and Studio, yet pipeline quality is proven only when **schemas match, sources/sinks have proper permissions, reruns are safe, numbers reconcile, and costs stay within budget**. Start with **GCS → Wrangler/Filter → BigQuery**, and add macros, orchestration, CDC, or streaming only when justified by measurable requirements.

In production, clearly separate the **Data Fusion instance managing pipelines** from **separately billed Spark execution**, secure VPC/IAM/secrets, track RunIDs, and pair **staging + `MERGE`/idempotency** so a retry incident never turns into an inaccurate business report.

## Official References

- [Cloud Data Fusion: overview](https://cloud.google.com/data-fusion/docs)
- [Cloud Data Fusion: Studio overview](https://cloud.google.com/data-fusion/docs/concepts/studio-overview)
- [Cloud Data Fusion: Console, instance/edition/network](https://cloud.google.com/data-fusion/docs/concepts/console-overview)
- [Create a data pipeline quickstart](https://cloud.google.com/data-fusion/docs/create-data-pipeline)
- [Cloud Data Fusion plugin reference](https://cloud.google.com/data-fusion/plugins)
- [Parse files in Wrangler](https://cloud.google.com/data-fusion/docs/how-to/wrangler-parse-files)
- [Wrangler overview](https://cloud.google.com/data-fusion/docs/concepts/wrangler-overview)
- [Design reusable pipelines](https://cloud.google.com/data-fusion/docs/tutorials/reusable-pipeline)
- [Cloud Storage batch source](https://cloud.google.com/data-fusion/docs/how-to/configure-cloud-storage-batch-source)
- [Deploy and run pipelines](https://cloud.google.com/data-fusion/docs/concepts/deploy-and-run-pipelines)
- [Cloud Data Fusion service accounts and IAM](https://cloud.google.com/data-fusion/docs/access-control)
- [Security overview and private instances](https://cloud.google.com/data-fusion/docs/concepts/security)
- [Cloud Data Fusion networking](https://cloud.google.com/data-fusion/docs/concepts/networking)
- [View pipeline logs](https://cloud.google.com/data-fusion/docs/how-to/view-and-download-pipeline-logs)
- [View Cloud Data Fusion Cloud Logging logs](https://cloud.google.com/data-fusion/docs/how-to/view-datafusion-logs)
- [Troubleshoot Cloud Data Fusion](https://cloud.google.com/data-fusion/docs/troubleshoot)
- [Cloud Data Fusion pricing](https://cloud.google.com/data-fusion/pricing)
- [gcloud beta data-fusion instances](https://cloud.google.com/sdk/gcloud/reference/beta/data-fusion/instances)
