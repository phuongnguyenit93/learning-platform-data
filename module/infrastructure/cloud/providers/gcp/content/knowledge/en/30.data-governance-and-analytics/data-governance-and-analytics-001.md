# Designing Data Lakes, Data Warehouses, and Lakehouses on GCP

> **Chapter:** Data Governance and Analytics  
> **Module:** CLOUD_PROVIDERS_GCP

A retail company stores orders in Cloud SQL, product browsing events in Pub/Sub, and partner CSV/Parquet files in Cloud Storage. Operations wants to **retain raw data for reprocessing**, Finance needs **verified revenue metrics**, and data scientists want to read the data using both **BigQuery** and **Apache Spark**. Should you build a **data lake**, a **data warehouse**, or a **lakehouse**?

The answer does not lie solely in service names. The architecture must address **how data is ingested, access permissions, how updates/deletes are handled, quality, freshness, querying, and cost**. This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, connecting knowledge from IAM/VPC, Cloud Run/GKE, Cloud Storage, databases, and reliability/cost operations. The recurring example is **orders analytics** for a retail company; all resources and figures are illustrative.

**After this lesson, you will be able to:**

1. Distinguish between a lake, a warehouse, and a lakehouse by storage location, format, permissions, and update model.
2. Design a *raw/bronze → validated/silver → curated/gold* flow for real-world use cases.
3. Choose **Cloud Storage**, **BigQuery native**, **BigLake external**, or **Apache Iceberg managed tables** based on requirements.
4. Coordinate Pub/Sub, Dataflow, Dataform, Spark, and BigQuery in batch and streaming workflows.
5. Design location, partitioning, schema evolution, deduplication, data contracts, retention, and recovery.
6. Configure IAM, BigLake connection delegation, policy tags, row/column policies, and catalog/lineage/data quality.
7. Write example SQL, test data quality, and estimate storage/query/compute costs.
8. Complete the lab and production readiness checklist.

## 1. The Three Models Are Not Synonymous

| Aspect | **Data lake** | **Data warehouse** | **Lakehouse** |
| --- | --- | --- | --- |
| Goal | Store raw/historical multi-format data | Consistent SQL analytics and BI | Open tables on object storage for multiple engines |
| Storage on GCP | **Cloud Storage** | **BigQuery native storage** | **Cloud Storage** + open table format/catalog |
| Data format | CSV, JSON, Avro, Parquet, objects | BigQuery managed tables | Parquet + **Apache Iceberg** metadata |
| Updates | Depends on files/pipelines, typically append | DML, MERGE, BigQuery transactions | Depends on engine/table format; managed Iceberg supports BigQuery DML |
| Governance | Metadata, ownership, and retention must be built | BigQuery IAM/schemas/policies | Catalog, table snapshots, multi-engine access |
| Risk | "Data swamp": hard to discover/untrusted | Data copies and compute charges | Metadata management, concurrent writes, compaction |

**You do not have to pick just one model for the entire company.** A common architecture keeps raw data in Cloud Storage, tables with stable KPIs in BigQuery, and uses Iceberg only for datasets that require open formats. A lakehouse is **not automatically cheaper** than a warehouse: you still pay for compaction, metadata, GCS operations, compute, and egress.

### 1.1. When to Choose Which Model?

- **Lake:** raw data, multiple formats, requiring replay/recovery capability when schemas or processing algorithms change.
- **Warehouse:** revenue reporting, self-service dashboards, SQL joins/aggregates, and BigQuery security and optimization.
- **Lakehouse:** BigQuery and Spark/open engines need to jointly read tables with metadata and snapshots, not just share a Parquet directory.
- **Hybrid:** raw GCS → silver BigQuery or Iceberg → gold BigQuery marts, depending on the domain.

**A lake does not replace OLTP.** Order placement, inventory checks, and payments require Cloud SQL/AlloyDB/Firestore based on access patterns; analytical systems do not replace transactional databases.

## 2. Reference Architecture on Google Cloud

~~~mermaid
flowchart LR
  SQL["Cloud SQL/Firestore\nOperational records"] --> CDC["CDC / batch extract"]
  EVT["Pub/Sub\nEvents"] --> DF["Dataflow\nValidation, windowing"]
  FILES["Partners: CSV/JSON/Parquet"] --> GCS["Cloud Storage\nRaw / Bronze"]
  CDC --> GCS
  DF --> GCS
  GCS --> CLEAN["Silver\nBigQuery / Spark\nNormalize + dedup"]
  CLEAN --> GOLD["Gold\nBigQuery marts / Iceberg"]
  GOLD --> BI["Looker Studio / Looker\nSQL dashboard"]
  GOLD --> ML["Spark / ML / notebooks"]
  GCS --> BGL["BigLake external tables\nSQL without copying files"]
  BGL --> CLEAN
  GOV["Knowledge Catalog\nmetadata, quality, lineage"] -.-> GCS
  GOV -.-> CLEAN
  GOV -.-> GOLD
~~~

The diagram illustrates **alternative options**; every record does not have to pass through every arrow. Dataflow can also write **directly via the BigQuery Storage Write API** so data appears quickly, while storing a raw copy if replay is needed. Do not duplicate data simply because the "medallion" model has three zone names.

### 2.1. Role of Each Service

| Service | Role | What Not to Assume |
| --- | --- | --- |
| **Cloud Storage** | Store raw data, Parquet, logs, objects | Does not natively provide SQL transactions over file sets |
| **BigQuery** | SQL, native warehouse, ETL/ELT, BI | Not an OLTP server with enforced foreign keys |
| **BigLake external tables** | GCS structured data via **connection delegation** | **External BigLake is read-only**, not managed Iceberg |
| **Apache Iceberg managed tables in BigQuery** | BigQuery manages Iceberg tables with Parquet files stored in your GCS bucket | Do not arbitrarily modify/delete underlying files outside the table manager |
| **Pub/Sub** | Buffer events, redelivery | Does not automatically provide business-level exactly-once |
| **Dataflow** | Batch/stream pipelines, enrichment, windowing | Does not replace data contracts |
| **Managed Service for Apache Spark** | Spark over files/open tables | Does not automatically synchronize multi-writer commits across all engines |
| **Dataform** | SQL transformations, assertions, dependencies in BigQuery | Does not replace data ingestion for all source systems |
| **Knowledge Catalog** | Metadata, data quality, lineage | Does not automatically grant data query permissions |
| **Cloud KMS/IAM/Audit Logs** | Encryption, authorization, audit | Does not replace data classification and review |

Google uses the name **Knowledge Catalog** (formerly **Dataplex Universal Catalog**) for catalog/quality/lineage capabilities; some APIs still use the `dataplex` prefix. See [Data governance in BigQuery](https://docs.cloud.google.com/bigquery/docs/data-governance).

## 3. Designing from Data Products and Consumers

Start with a **data contracts** table instead of creating buckets first:

| Data | Source | Consumer | Target Freshness | Quality/Sensitivity |
| --- | --- | --- | --- | --- |
| `order_created` | Cloud SQL CDC/Pub/Sub | Near-real-time KPIs | A few minutes (assumed) | Stable `event_id`, valid timestamp |
| Confirmed orders | Operational DB | Finance | Hourly | Unique `order_id`, valid amount |
| Product catalog | Cloud SQL/files | Analysts | Daily | Snapshot/version |
| Supplier files | Cloud Storage inbound | Data engineers | Daily | Schema, checksum, origin |
| App logs | Cloud Logging/GCS | SRE | Minutes/hours | Mask PII, short TTL |
| `daily_revenue` | Silver orders | BI | Daily | SQL definition, owner, reconciliation |

The **data owner** is responsible for the business definition and SLO of a data product; the **platform team** manages storage, IAM, pipelines, and monitoring. A "gold" table without an owner may execute valid SQL yet still carry the wrong business semantics.

### 3.1. Minimal Data Contract

~~~json
{
  "event_id": "evt-20261119-001",
  "order_id": "ord-001",
  "customer_id": "cust-042",
  "order_ts": "2026-11-19T02:10:00Z",
  "amount_minor": 259900,
  "currency": "VND",
  "status": "PAID",
  "source_version": 1
}
~~~

`event_id` must remain unchanged across retries, `order_ts` must be in UTC, `amount_minor` is an integer in the smallest currency unit, and `status/currency` belong to allowed sets. Do not write tokens, passwords, personal addresses, or unnecessary PII into logs/bronze.

## 4. Data Zones: raw/bronze → silver → gold

~~~mermaid
flowchart TD
  INPUT["Incoming events + files"] --> BR["RAW/BRONZE\nOriginal GCS + source metadata"]
  BR --> Q{"Schema + quality pass?"}
  Q -- "No" --> QUAR["Quarantine\nerror code + safe reference"]
  Q -- "Yes" --> SIL["SILVER\nnormalize, dedup, privacy"]
  SIL --> GOLD["GOLD\nbusiness KPIs/aggregates"]
  GOLD --> USE["Dashboards, analytics, ML"]
  BR -. "Replay/backfill" .-> SIL
~~~

| Zone | Goal | Common Formats | Publication Criteria |
| --- | --- | --- | --- |
| **Raw/landing** | Original copy, source traceability | Original CSV/JSON/log/files | Restricted access, hash, source/version |
| **Bronze** | Minimal parsing, add ingestion metadata | Parquet/Avro/BigQuery raw | Source timestamp, event_id, schema version |
| **Silver** | Typed, cleaned/deduped, PII policy | Parquet/Iceberg/BigQuery | DQ checks PASS |
| **Gold** | Standard business definitions for BI/ML | BigQuery marts/curated Iceberg | Owner sign-off, access policy |

In small systems, Raw and Bronze can be **a single zone**; also avoid deleting raw data too early when replay or pipeline investigation is still needed.

### 4.1. Meaningful Paths and Datasets

~~~text
gs://company-lake-lab/
  landing/partner_orders/2026/11/19/file-001.csv
  bronze/orders/dt=2026-11-19/part-0001.parquet
  quarantine/orders/dt=2026-11-19/invalid-001.json
  iceberg/orders_curated/ ...  # Only the table manager may modify metadata

BigQuery (dataset location: asia-southeast1)
  lake_ext.orders_parquet         # BigLake external table
  silver.orders                  # BigQuery native table
  gold.daily_revenue             # Business mart
~~~

Prefixes like `dt=...` are just key strings in GCS; they **do not automatically create Hive partitioning in BigQuery**. For external table partition pruning, you must configure Hive partitioning options and filter on the partition column. A `*.parquet` wildcard does not automatically generate partition metadata.

### 4.2. Choosing Formats and Avoiding the Small-File Problem

- **Parquet:** columnar, compressed, well-suited for column-selective scans with BigQuery/Spark. Use for analytical lakes.
- **Avro:** schema-bearing, good for interchange and sequential data with evolving schemas.
- **NDJSON/CSV:** easy to receive from partners but requires parsing/validating types, timezones, and schema drift.
- **Apache Iceberg:** a **table format** with snapshots/metadata/schema evolution, typically using Parquet data files. Do not confuse an arbitrary Parquet directory with an Iceberg table.
- **Delta Lake/Hudi:** other open formats with engine-dependent support; do not assume they support every SQL feature.

Millions of objects a few KB in size increase listing and metadata/query overhead. Batch or compact into file sizes suited to your workload; do not create one Parquet file per event. Partition by time or query semantics, avoiding high-cardinality partitions that generate countless tiny directories. BigQuery native tables are typically partitioned by day and clustered by `customer_id`/`store_id`.

## 5. Four Ways to Bring GCS into BigQuery

| Approach | Where Is Data Stored? | Read Permissions | Mutations | Use Case |
| --- | --- | --- | --- | --- |
| **Non-BigLake external table** | GCS objects | User needs BigQuery **and GCS permissions** | No DML on external table | Labs, infrequently changing files |
| **Cloud Storage BigLake external table** | GCS objects | BigQuery table permission; **connection SA** reads GCS | **Read-only** table | Access delegation, row/column policies, metadata cache |
| **BigQuery native table** | BigQuery-managed storage | BigQuery IAM/policies | DML/MERGE, BigQuery features | BI/warehouse, SQL marts |
| **Apache Iceberg managed table** | GCS bucket you own | BigQuery/Iceberg permissions; managed connection | **BigQuery DML** and engine-specific access | Open lakehouse, BigQuery + Spark |

**External vs. managed** is the decisive distinction. A BigLake external Parquet table does not become a transactional table just because the connection service account has GCS write permissions. An Apache Iceberg managed table has its files/metadata managed by BigQuery and supports DML, incurring charges for **GCS storage + storage optimization + query compute**.

### 5.1. BigLake Access Delegation

In a non-BigLake external table, the caller needs both BigQuery permissions and direct permissions to the GCS files. With **BigLake external**, you create a **BigQuery connection** whose service account is granted bucket access, while users only need BigQuery query/table permissions. This enables applying row/column policies on the BigLake table and reduces direct sharing of bucket credentials.

**Limitation:** if a user still has permission to read the bucket through another IAM path, BigLake policies **do not revoke that direct GCS read access**. If the table is meant to be the sole access gate, you must prevent direct GCS access.

## 6. Preflight: Location, Resources, and Permissions

Hypothetical lab setup (all values are placeholders):

| Value | Example |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` (example only; check feature support and residency) |
| Raw/bronze bucket | `gs://YOUR_BUCKET` |
| External dataset | `lake_ext` |
| Curated dataset | `silver` |
| Gold dataset | `gold` |
| BigQuery connection | `LAB_PROJECT_ID.asia-southeast1.lake_conn` |
| Parquet | `gs://YOUR_BUCKET/bronze/orders/part-0001.parquet` |

These are not real projects or buckets. Bucket names are globally unique identifiers. Do not run resource creation commands in production without approval for billing, quotas, location, and IAM.

### 6.1. Read-Only Inspection Commands

~~~bash
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud storage buckets describe gs://YOUR_BUCKET
gcloud storage ls gs://YOUR_BUCKET/bronze/orders/

bq ls --project_id=LAB_PROJECT_ID
bq show --format=prettyjson LAB_PROJECT_ID:lake_ext
bq show --format=prettyjson LAB_PROJECT_ID:silver

bq ls --connection --project_id=LAB_PROJECT_ID --location=asia-southeast1
~~~

If a resource does not exist, record **NOT PRESENT**. Do not create billable databases or buckets solely to complete a checklist. Ensure the BigQuery API and BigQuery Connection API are enabled when using connections; enable the Dataflow API only when running Dataflow.

### 6.2. Separation of Duties with IAM

| Identity | Appropriate Permissions |
| --- | --- |
| Ingest Cloud Run/Dataflow SA | Write to approved raw/bronze prefix; do not read all of gold |
| BigLake **connection SA** | `roles/storage.objectViewer` on the bucket/managed folder to query |
| BigLake table analyst | `bigquery.tables.getData` on the table and `bigquery.jobs.create` on the query project |
| ELT service account | Read bronze/silver, write silver/gold scoped to dataset/table |
| Dashboard viewer | Read-only access to gold views/aggregates per credential model |
| Data steward | Catalog, metadata, DQ scans, ownership, lineage |
| Security operator | IAM, policy tags, audit, KMS/retention |

Prefer runtime service accounts and **Workload Identity Federation/ADC**; never commit JSON service account keys. In BigQuery, `roles/bigquery.dataViewer` at the table/dataset level and `roles/bigquery.jobUser` on the project can satisfy querying, but always verify permissions per action. Never grant Project Editor to fix a 403 error.

## 7. BigLake External Lab: Querying Parquet from Cloud Storage

Assume the bucket contains **schema-valid** Parquet files:

~~~text
gs://YOUR_BUCKET/bronze/orders/part-0001.parquet
gs://YOUR_BUCKET/bronze/orders/part-0002.parquet
~~~

Each file has fields `order_id STRING`, `customer_id STRING`, `order_ts TIMESTAMP`, `amount_minor INT64`, `currency STRING`, `status STRING`. **Do not run** SQL if the bucket lacks valid files, the connection lacks permissions, or the GCP project has not been approved for billing.

### 7.1. Create Datasets and BigQuery Connection

~~~bash
# REPLACE PROJECT: run in an approved lab, associated costs apply
bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:lake_ext

bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:silver

bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:gold

# Create a BigQuery Cloud resource connection
bq mk --connection \
  --location=asia-southeast1 \
  --connection_type=CLOUD_RESOURCE \
  lake_conn
~~~

**Before the next step:** Retrieve the **connection's service account** via BigQuery Console → Connections or:

~~~bash
# READ-ONLY: confirm serviceAccountId in connection metadata
bq show --connection \
  LAB_PROJECT_ID.asia-southeast1.lake_conn
~~~

Once you have the real `serviceAccountId`, the bucket owner grants **Storage Object Viewer** only on the bucket/prefix to be read. Do not grant Viewer to a placeholder `principal` from examples. If using a bucket with Uniform bucket-level access, use bucket-level IAM or managed folder IAM as supported.

### 7.2. Declare the BigLake Cloud Storage External Table

~~~sql
-- REPLACE DATASET: create external table in the lab project
CREATE OR REPLACE EXTERNAL TABLE
  `LAB_PROJECT_ID.lake_ext.orders_parquet`
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  format = "PARQUET",
  uris = ["gs://YOUR_BUCKET/bronze/orders/*.parquet"]
);
~~~

This statement creates a **BigLake external table** because it includes `WITH CONNECTION`. BigQuery reads the Parquet files and metadata stored in Cloud Storage without **copying** the entire dataset into BigQuery managed storage. On such an external table, **you cannot use BigQuery DML directly to modify rows in the files**.

If the table has millions of files or Hive-style partitions, you can add **metadata caching** configuration as documented:

~~~sql
-- Create another table to compare cache behavior
CREATE OR REPLACE EXTERNAL TABLE
  `LAB_PROJECT_ID.lake_ext.orders_cached`
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  format = "PARQUET",
  uris = ["gs://YOUR_BUCKET/bronze/orders/*.parquet"],
  max_staleness = INTERVAL 2 HOUR,
  metadata_cache_mode = "AUTOMATIC"
);
~~~

Caching improves metadata/listing read efficiency and incurs **cache refresh costs**; new files may not appear immediately in the cache until the next refresh. With `AUTOMATIC`, the refresh interval is typically around **30–60 minutes**, not a 2-hour guarantee of business data freshness. `max_staleness` specifies when a query can use cached metadata, not a retention period.

### 7.3. Sample Query

~~~sql
-- READ-ONLY; executes a query and may incur charges
SELECT
  DATE(order_ts) AS order_date,
  currency,
  COUNT(*) AS orders,
  SUM(amount_minor) AS total_minor
FROM `LAB_PROJECT_ID.lake_ext.orders_parquet`
WHERE order_ts >= TIMESTAMP "2026-11-18 00:00:00+00"
  AND order_ts < TIMESTAMP "2026-11-20 00:00:00+00"
  AND status = "PAID"
GROUP BY order_date, currency
ORDER BY order_date;
~~~

**Reminder:** Being able to run SQL queries does not mean an external BigLake table supports `UPDATE`/`DELETE`. If you need upserts or repeated analytical queries, consider loading into BigQuery native or choosing Iceberg managed.

## 8. Data Warehouse with BigQuery Native Tables

A warehouse is appropriate when BI teams need stable tables, partition pruning, joins, materialized views, scheduled transformations, and SQL DML.

### 8.1. Create a Partitioned/Clustered Silver Table

Once the Parquet external table is ready, here is an example ELT load into BigQuery native:

~~~sql
-- REPLACE DATASET: create/overwrite the silver table in the lab
CREATE OR REPLACE TABLE `LAB_PROJECT_ID.silver.orders`
PARTITION BY DATE(order_ts)
CLUSTER BY customer_id
OPTIONS (description="Orders normalized from BigLake external source")
AS
SELECT
  CAST(order_id AS STRING) AS order_id,
  CAST(customer_id AS STRING) AS customer_id,
  SAFE_CAST(order_ts AS TIMESTAMP) AS order_ts,
  SAFE_CAST(amount_minor AS INT64) AS amount_minor,
  UPPER(TRIM(CAST(currency AS STRING))) AS currency,
  UPPER(TRIM(CAST(status AS STRING))) AS status
FROM `LAB_PROJECT_ID.lake_ext.orders_parquet`
WHERE order_id IS NOT NULL;
~~~

**Gaps before production:** A full-refresh `CREATE OR REPLACE` incurs scan/copy costs and does not automatically handle duplicate `order_id` values; failed `SAFE_CAST` conversions can return `NULL`. You need quality checks beforehand or inline, routing invalid records to quarantine and applying rules to select the latest updated record. Time partitioning should preserve a valid `TIMESTAMP` data type and handle late events.

### 8.2. Gold Mart with KPI Definitions

~~~sql
CREATE OR REPLACE TABLE `LAB_PROJECT_ID.gold.daily_revenue`
PARTITION BY order_date
AS
SELECT
  DATE(order_ts) AS order_date,
  currency,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM `LAB_PROJECT_ID.silver.orders`
WHERE status = "PAID"
  AND order_ts IS NOT NULL
  AND amount_minor >= 0
GROUP BY 1, 2;
~~~

This is only a **simplified example for learning**; with refunds, cancellations, partial payments, and taxes/discounts, `revenue` must follow an **accounting contract** and point-in-time status data. Do not treat `SUM` over `PAID` orders as official accounting revenue without owner approval.

### 8.3. Incremental Instead of Full Refresh

- **CDC** delivers inserts/updates/deletes from operational systems. You must distinguish the initial snapshot from change events.
- **MERGE** into the silver table by `order_id` using a defined latest source version or event-time/sequence.
- **Dataform** manages dependencies, SQL models, assertions, and schedules; it does not automatically create exactly-once semantics from a stream with duplicates.
- **Materialized views** are suitable only for supported SQL/sources/query patterns; not every external table is supported.
- **Gold** should have a query contract/metric definition tested against mock data before publication.

A safe `MERGE` must ensure **at most one source row per target key** per execution; if the input has multiple updates for the same `order_id`, use `ROW_NUMBER()/QUALIFY` with a deterministic tie-breaker before merging. Avoid running `MERGE` for every individual event when micro-batches can be grouped.

## 9. Lakehouse: Apache Iceberg Managed Tables in BigQuery

BigQuery supports **Apache Iceberg managed tables** storing **Parquet in a Cloud Storage bucket owned by your organization**. The Iceberg table metadata format lets Spark/third-party engines read data in supported ways, while BigQuery provides a managed experience including schema evolution, DML, and background storage optimization. <https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery>

### 9.1. Sample DDL (Advanced, Billable)

~~~sql
-- REPLACE DATASET AND BUCKET: run only in an eligible lab
CREATE TABLE `LAB_PROJECT_ID.silver.orders_iceberg` (
  order_id STRING,
  customer_id STRING,
  order_ts TIMESTAMP,
  amount_minor INT64,
  currency STRING,
  status STRING
)
CLUSTER BY customer_id
WITH CONNECTION `LAB_PROJECT_ID.asia-southeast1.lake_conn`
OPTIONS (
  file_format = "PARQUET",
  table_format = "ICEBERG",
  storage_uri = "gs://YOUR_BUCKET/iceberg/orders_curated"
);
~~~

Unlike read-only BigLake external tables, this is a **managed table** with no `EXTERNAL` keyword. The connection service account needs appropriate permissions to **read, create, delete, and list GCS objects** per the Iceberg managed documentation, rather than just Object Viewer. The dataset, bucket, connection, and storage location must be compatible; feature availability in the region and organization policies must also be checked.

### 9.2. Responsibility Boundaries with Open Table Formats

| Topic | Key Points to Remember |
| --- | --- |
| Actual data | Parquet files and Iceberg metadata reside in a bucket you own |
| DML | BigQuery manages mutations, compaction, and metadata/snapshots |
| Spark reads | Use a supported Iceberg snapshot/catalog, not arbitrary file paths |
| Concurrent writers | Check **write ownership/commit protocol** for each specific integration |
| Table deletion | Do not assume all GCS data files are automatically deleted with the BigQuery table |
| Metadata freshness | Snapshots/exports have refresh schedules/mechanisms; external engines may read prior versions |
| Cost | GCS bytes/operations, BigQuery queries, **DCU storage optimization**, egress |

**Do not** run `gcloud storage rm -r gs://.../iceberg/orders_curated` or let Spark write directly into a managed table directory **without official integration guidance**. Uncoordinated parallel writes from multiple engines can corrupt metadata and snapshots. Sharing an open format **does not mean automatic multi-writer ACID across all engines**.

### 9.3. Criteria for Choosing Iceberg

Choose Iceberg managed if you **already have a multi-engine use case**, need an open format on GCS, and accept responsibility for KMS/retention/table metadata lifecycle. If all dashboards and SQL transformations use only BigQuery, **native BigQuery tables are usually simpler**, with fully managed BI/warehouse optimizations. If you only need to query an infrequently changing set of Parquet files, a **BigLake external table** may be sufficient.

## 10. Ingestion and Batch/Streaming Processing

~~~mermaid
flowchart TD
  INPUT["Operational DB / Events / Files"] --> CLASS{"Source nature?"}
  CLASS -- "CDC/batch" --> LAND["GCS raw + manifest/hash"]
  CLASS -- "Streaming" --> PUB["Pub/Sub"]
  PUB --> FLOW["Dataflow validate + dedup"]
  LAND --> LOAD["BigQuery load job / Spark transform"]
  LOAD --> SILVER["Silver table"]
  FLOW --> SILVER
  SILVER --> TEST["Data quality gate"]
  TEST --> GOLD["Gold mart"]
  TEST --> QUAR["Quarantine / retry if failed"]
~~~

### 10.1. Batch File Ingestion

1. Write files to `landing`, along with source ID, arrival timestamp, checksum, and schema version.
2. Validate size, format, encoding, and schema before publishing.
3. Store raw data under a path where only the ingest job has write permissions; avoid overwriting files with the same name.
4. Use a BigQuery load job or Spark to process and emit bronze/silver.
5. Set an idempotency key from `source_file_checksum + version` so reruns do not duplicate records.
6. Emit quality metrics, rejected-record counts, and manifest/job IDs.

### 10.2. Streaming with Pub/Sub and Dataflow

1. Producers attach a business-unique `event_id`.
2. Pub/Sub can redeliver messages; Dataflow must manage watermarks, late data, and DLQs.
3. Choose the BigQuery Storage Write API write mode per requirements: default at-least-once, or application-created committed/offsets when you need exactly-once **within a stream**.
4. Deduplicate by `event_id/source_version` before Silver or during batch reconciliation.
5. Create an `event_to_query_lag` metric and alert on backlog.
6. Do not ack/commit upstream based solely on a step without confirmed durable writes.

**Do not claim business-level exactly-once just because you use an API named "exactly once".** You still must handle source duplication, retries, checkpoints, deduplication, and downstream idempotency.

### 10.3. Common Transformation Options

| Workload | Suitable Tool | Notes |
| --- | --- | --- |
| Small batch CSV, SQL transformations | BigQuery load + SQL/Dataform | Schema types and refresh schedule |
| Large Parquet, Spark ecosystem | Managed Service for Apache Spark | File sizing, partitioning, temporary storage |
| Near-real-time events | Pub/Sub + Dataflow + BigQuery Write API | Backpressure, duplicates, watermarks |
| Periodic SQL ELT | BigQuery scheduled queries/Dataform | Dependency order, incremental MERGE |
| Data source from Cloud SQL | Supported CDC/data integration | Snapshot + change log + tombstones |
| Machine learning features | BigQuery/Vertex AI, validated data products | Training/serving skew, privacy |

## 11. Catalog, Ownership, Lineage, and Data Quality

A lakehouse architecture fails if 100 TB of data exists with nobody knowing its source, quality, or who is authorized to use it. **Knowledge Catalog** (formerly Dataplex Universal Catalog) supports asset discovery, metadata annotation, quality scans, and lineage within supported services. <https://docs.cloud.google.com/dataplex/docs/use-auto-data-quality>

### 11.1. Attaching Actionable Metadata

| Component | Required Metadata | Example |
| --- | --- | --- |
| Data product | Owner, SLA, classification, contract | `orders-paid-v1`, owner Finance |
| Table/field | Description, schema, format, tags, sensitivity | `customer_id`: Internal; `email`: Restricted |
| Ingestion | Source, run ID, checkpoint, hash, arrival time | `cdc-run-20261119` |
| Quality | Completeness, validity, uniqueness, freshness | `order_id` nonnull, `event_id` unique |
| Retention | Business/legal rule, expiration, deletion flow | Raw 90 days (assumed) |
| Lineage | Upstream → transform → downstream | GCS orders → Silver orders → Gold daily revenue |
| Access | Data owner approvals, policy, IAM | Gold viewers, raw restricted |

### 11.2. Data Quality Gates

For example, Silver orders requires:

- **Completeness:** `order_id`, `order_ts`, `currency` are non-null.
- **Validity:** `amount_minor >= 0`; status is in the allowed list.
- **Uniqueness:** no duplicate `order_id` in the current snapshot or `event_id` in the change log.
- **Freshness:** ingestion time does not exceed the agreed SLA.
- **Reconciliation:** totals/counts between raw and Silver match after accounting for logged invalid records.
- **Contract drift:** no required columns added or removed without updating the schema/version.

Quality scans can run automatically on a schedule and emit results; **that does not mean a scan automatically blocks SQL dashboards from reading bad data**. You need a **publication gate**: if checks fail, do not replace the approved gold snapshot, raise an alert, and store evidence.

### 11.3. Lineage and Change Impact

~~~mermaid
flowchart LR
  SRC["Cloud SQL orders"] --> BR["GCS bronze orders"]
  BR --> SIL["BigQuery silver.orders"]
  SIL --> GOLD["BigQuery gold.daily_revenue"]
  GOLD --> DASH["Finance dashboard"]
  SIL --> MODEL["ML features"]
~~~

When changing the type of `amount_minor` or removing `customer_id`, lineage shows which reports or models depend on that field. Enable the Data Lineage API/capture per documentation; lineage is captured automatically from certain services, **but does not automatically detect every script, laptop run, or third-party transformation**. Add custom lineage where needed and verify cross-project metadata viewing permissions.

## 12. Security, Privacy, and Data Lifecycle

### 12.1. Defense-in-Depth Layers That Must Work Together

| Layer | Example Tools | Scope |
| --- | --- | --- |
| Ingestion/network | Service identity, private connectivity, VPC Service Controls where appropriate | Reduce risk of unauthorized data access/exfiltration |
| Object storage | Cloud Storage **Uniform bucket-level access**, IAM, Public Access Prevention | Who can read/write files |
| BigLake | Connection access delegation | Avoid exposing the GCS bucket to all analysts |
| BigQuery | Dataset/table IAM, **row access policies**, **column policy tags**, masking | Row/column read permissions, masking |
| Encryption | Google-managed encryption/CMEK with Cloud KMS | Keys and key lifecycle operations |
| Governance | Catalog classification, retention, audit, DQ | Ownership, lineage, auditing, trustworthiness |
| Presentation | Authorized views, curated aggregates, dashboard permissions | Share data only with the right audience |

**Important:** CMEK applied to a BigQuery table **does not automatically apply** to Parquet objects in Cloud Storage read by a BigLake external table. If end-to-end CMEK is required, you must configure encryption and key access for **both GCS and BigQuery** per each service's documentation.

### 12.2. Row/Column Policies and Authorized Views

For example, Silver orders contains `customer_id` and `amount_minor`, while some teams only need daily revenue. A lower-risk approach is:

1. The Gold mart **does not contain customer IDs**.
2. Grant analysts only `roles/bigquery.dataViewer` on the Gold dataset/view.
3. If per-branch or per-tenant access is needed, use row-level policies or reviewed authorized views with filters.
4. If PII masking is required, use policy tags and **dynamic data masking** per supported features.
5. Also test **direct GCS access**: anyone permitted to read bronze files can bypass BigQuery controls if bucket IAM is too broad.

**Do not treat hiding sensitive columns in a dashboard UI as real security.** Controls must reside at the source/table/view and identity layer.

### 12.3. Retention/TTL and Data Deletion Requests

- Distinguish **raw legal retention**, **Silver TTL**, **Gold aggregate retention**, and **backups/snapshots**.
- Cloud Storage has lifecycle policies, object versioning/soft delete, and retention policies; each feature has distinct behavior.
- **Bucket Lock** prevents a retention policy from being shortened or removed once locked; this action is **irreversible**—do not run it in a lab.
- BigQuery has table/partition expiration, time travel, and recovery windows based on configuration. Deleting a logical row does not necessarily erase all snapshots/backups immediately.
- Data that must be deleted upon user request must propagate through **all copies and derived data** according to organizational law/policy.
- If data is replicated across regions or external engines, retention/deletion must cover **every location where a copy exists**.

**Do not promise that "deleting from the warehouse means deleting from the data lake."** You need lineage, a data inventory, and contractual deletion/rewrite workflows.

## 13. Reliability, Performance, Cost, and SLOs

### 13.1. Set Measurable Targets

| Metric | Definition | Example Requirement (Not a Google SLA) |
| --- | --- | --- |
| Freshness | How soon is a new record queryable in Silver/Gold? | 95% of events appear within 5 minutes |
| Completeness | Ratio of valid records received vs. source | ≥ 99.9% per manifest |
| Uniqueness | No duplicate business events | 0 duplicate `order_id` in snapshot |
| Accuracy | Total revenue reconciled with accounting source | Variance ≤ owner-approved threshold |
| Availability | Ability to query/ingest data | Per dashboard/pipeline SLO |
| Recoverability | RPO/RTO for replay/backfill | RPO within raw retention window |
| Cost efficiency | Ingest/store/query cost per 1 million events | Budget benchmark per workload |

**Assign an owner accountable for each SLO.** Do not equate "job succeeded" with "data meets quality": a pipeline can be green while double-counting revenue.

### 13.2. TCO Analysis

Total architecture cost must account for all of:

\[
C_{\text{total}} =
C_{\text{storage}} + C_{\text{ingest}} + C_{\text{processing}} +
C_{\text{query}} + C_{\text{network}} + C_{\text{governance/operations}}
\]

| Design | Primary Cost Drivers | Optimization Approach |
| --- | --- | --- |
| GCS raw lake | GCS bytes, operations, retrieval, egress | Retention-aligned lifecycle, Parquet compaction, fewer copies |
| BigLake external | GCS + BigQuery query compute + metadata cache refresh | Partition/file pruning, avoid scanning millions of small files |
| BigQuery native | Native storage + loads/transforms + SQL query slots/bytes | Partition/cluster, incrementals, materialized aggregations |
| Iceberg managed | GCS bytes + BigQuery queries + storage optimization DCUs | File sizing, data lifecycle, use only when multi-engine adds value |
| Streaming | Pub/Sub, Dataflow, Write API, worker CPU | Batching, backpressure, checkpoints, and DLQs |
| Governance | Catalog scans, logging, KMS, personnel | Scheduled scans, log/PII filtering, ownership |

**Do not assume querying external tables is cheaper than native just because "data isn't copied."** External tables still incur file metadata/listing reads and query compute charges, and can be slower/more expensive under repeated queries; native incurs storage costs but offers stronger optimizations for many BI workloads.

### 13.3. Reducing Bytes Scanned in BigQuery

~~~bash
# Dry run only, does not execute query results
bq query \
  --project_id=LAB_PROJECT_ID \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT COUNT(*) FROM `LAB_PROJECT_ID.silver.orders`'

# Query with a maximum bytes billed limit; run only against created lab tables
bq query \
  --project_id=LAB_PROJECT_ID \
  --use_legacy_sql=false \
  --maximum_bytes_billed=1073741824 \
  'SELECT currency, SUM(amount_minor) AS total
   FROM `LAB_PROJECT_ID.silver.orders`
   WHERE order_ts >= TIMESTAMP("2026-11-18")
     AND order_ts < TIMESTAMP("2026-11-20")
   GROUP BY currency'
~~~

Filtering directly on the **partitioning field/expression** lets BigQuery prune partitions on native tables, unlike adding `LIMIT 10` to a full-table scan query. Dry runs help estimate cost, though for external tables **the estimate may only be a lower bound**, so measure actual query job statistics.

## 14. Hands-On Lab Without Creating Cloud Resources

If you do not yet have IAM/budget permissions, run **inline** queries in the BigQuery SQL editor on a lab project where you have query permissions. No Cloud SQL, GCS, BigLake connection, or dataset is required; the query below **does not write** any data.

### 14.1. Mock Input

| event_id | order_id | status | amount_minor | Notes |
| --- | --- | --- | ---: | --- |
| evt-01 | ord-101 | PAID | 100000 | Valid |
| evt-01 | ord-101 | PAID | 100000 | Duplicate replay |
| evt-02 | ord-102 | PAID | 250000 | Valid |
| evt-03 | ord-103 | CANCELLED | 200000 | Excluded from paid |
| evt-04 | ord-104 | PAID | -2000 | Violates contract |

**Pitfall:** Summing paid amounts directly from raw without deduplication/validation produces the wrong total. The correct answer for this exercise is **350,000 VND** (each event counted once, excluding cancelled orders and negative amounts).

### 14.2. Complete SQL Running on Mock Data

~~~sql
-- Read-only GoogleSQL query; creates no tables and modifies no resources.
WITH bronze AS (
  SELECT 'evt-01' event_id, 'ord-101' order_id,
         TIMESTAMP '2026-11-19 02:00:00+00' order_ts,
         'PAID' status, 100000 amount_minor, 'VND' currency
  UNION ALL SELECT 'evt-01', 'ord-101',
         TIMESTAMP '2026-11-19 02:00:00+00', 'PAID', 100000, 'VND'
  UNION ALL SELECT 'evt-02', 'ord-102',
         TIMESTAMP '2026-11-19 02:01:00+00', 'PAID', 250000, 'VND'
  UNION ALL SELECT 'evt-03', 'ord-103',
         TIMESTAMP '2026-11-19 02:02:00+00', 'CANCELLED', 200000, 'VND'
  UNION ALL SELECT 'evt-04', 'ord-104',
         TIMESTAMP '2026-11-19 02:03:00+00', 'PAID', -2000, 'VND'
),
validated AS (
  SELECT *
  FROM bronze
  WHERE order_id IS NOT NULL
    AND amount_minor >= 0
    AND status IN ('PAID', 'CANCELLED')
    AND currency = 'VND'
),
silver AS (
  SELECT * EXCEPT(row_number)
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY order_ts DESC, order_id DESC
      ) AS row_number
    FROM validated
  )
  WHERE row_number = 1
),
gold AS (
  SELECT DATE(order_ts) order_date, currency,
         COUNT(*) paid_orders, SUM(amount_minor) revenue_minor
  FROM silver
  WHERE status = 'PAID'
  GROUP BY 1, 2
)
SELECT * FROM gold ORDER BY order_date;
~~~

**Expected output:** `2026-11-19 | VND | 2 | 350000`. This is a clear data quality/deduplication example, **not complete business logic**: if two events share the same `event_id` with different payloads, you need a stable source sequence/ingest time and conflict-resolution rules. In production, `ROW_NUMBER` should not rely on arbitrary tie-breakers; the source must provide a consistent sequence/snapshot version.

### 14.3. Follow-Up Exercises from the Query

1. Add a record `evt-05, ord-105, PAID, 300000, USD`. Modify the SQL to **group by currency** rather than summing VND and USD together.
2. Add a record with a null `order_ts`; route it into a quality-failure summary instead of gold.
3. Count raw records, rejected records, dropped duplicates, and records reaching gold. Clearly record which step filters out each row.
4. Add a `status='REFUNDED'` filter and decide whether to subtract from revenue or place it in a separate mart per Finance's contract.
5. Simulate replaying `evt-01` one day later and explain the difference between event time, ingest time, and partition date.

Do not copy this mock data into `silver.orders` or production Gold tables.

## 15. Case Study: Growing from a Small Lake to a Multi-Team System

### 15.1. Phase A — Data Lake + BigQuery Warehouse

The company has only a few sources (nightly orders CSVs and event logs), 5 analysts, and one revenue dashboard:

- GCS holds raw files with clear retention.
- BigQuery native Silver/Gold for SQL, partitioned by day.
- Dataform/Scheduled Queries for ELT with tests; dataset-level IAM.
- No need for Iceberg solely because "lakehouse is modern."

**Benefit:** Simple, easy to operate, minimal table metadata coordination.

### 15.2. Phase B — Adding BigLake for Controlled Raw Sharing

Parquet datasets grow large, and multiple analysts want to query immediately without loading every file:

- Create a BigLake external table with a connection SA reading GCS.
- Only analysts with BigQuery permissions run SQL; lock down direct GCS access where appropriate.
- Enable metadata caching with suitable freshness if file listings are large.
- Frequently queried datasets should still be loaded into native BigQuery.

**Avoid this mistake:** Letting analysts read the bucket directly and assuming column masking on the BigLake table protects the underlying objects.

### 15.3. Phase C — Iceberg Managed Tables for Multi-Engine Needs

Data science genuinely needs to run Spark on a curated dataset while BI wants BigQuery SQL:

- Pick one Iceberg managed dataset, define **write ownership**, version/catalog integration, and snapshot refresh.
- Use BigQuery to manage the Iceberg table per documentation; Spark reads via the supported catalog/snapshot.
- Test concurrent writes, metadata rollback, performance/compaction, lineage, and GCS object lifecycle.
- Monitor query + GCS + DCU storage optimization + data egress costs.

**Selection criterion:** The multi-engine value must outweigh the added cost and complexity. Do not migrate the entire warehouse to Iceberg just to follow a trend.

## 16. Troubleshooting Table

| Symptom | Cause | Check / Action |
| --- | --- | --- |
| BigLake query 403 | Connection SA lacks GCS Object Viewer | IAM of the **connection SA**, bucket/managed folder |
| Analyst can still download raw files despite BigQuery block | User has direct GCS IAM | Audit direct bucket permissions, perimeter |
| External table does not see new files | Metadata cache not refreshed or wrong URI | Cache freshness, wildcard, file naming |
| SQL reading Parquet fails on schema | Files have differing types or writer drift | Check schema contract, quarantine |
| BigQuery CTAS/MERGE fails on type | `SAFE_CAST` returns null, source has multiple versions | DQ gates, dedup by source version |
| Gold revenue doubles | Pub/Sub retry/CDC replay, missing dedup | `event_id`, checkpoint, MERGE uniqueness |
| Query expensive despite small LIMIT | Scans many external files/native partitions | Dry run, partition filters, file compaction |
| Iceberg metadata out of sync with Spark view | Stale snapshot/catalog, uncoordinated writers | Refresh/export metadata, commit protocol |
| Iceberg storage balloons | Snapshots/files not garbage-collected per policy | Retention/optimization metrics, do not `rm` files manually |
| BigQuery IAM is right but GCS fails to read | Non-BigLake external requires permissions in both places | Distinguish external table types |
| Data quality scan green but dashboard wrong | Business definition/reconciliation not tested | Owner verifies KPI/late data |
| Bucket with data cannot be deleted | Retention policy/Bucket Lock/lifecycle hold | Check policies, do not try to bypass |
| Region/storage mismatch | Incompatible bucket/dataset/connection locations | Verify data residency before creation |
| BI refresh too slow | Many external files, unoptimized cache/indexes/SQL | Native marts, appropriate cache, cost alerts |

**Diagnostic order:** data source → IAM/network/location → file schema → table type & metadata → DQ/lineage → SQL access path → query cost → BI definitions.

## 17. Review Exercises

1. **How does a data lake differ from a warehouse?** A lake stores raw, multi-format data; a warehouse organizes standardized SQL tables for analytics.
2. **Does lakehouse mean "Parquet in GCS"?** No; it requires a table format/catalog/snapshots and write governance.
3. **Does a BigLake external table store data in BigQuery managed storage?** No, the files remain in GCS.
4. **What permissions does a non-BigLake external table require?** Both BigQuery permissions and GCS data read permissions for the caller.
5. **How does a BigLake connection SA replace an analyst's GCS permissions?** Access delegation; analysts can query the table without direct bucket read access.
6. **Can a BigLake external table be updated with BigQuery DML?** No; external BigLake tables are read-only.
7. **Does a managed Iceberg table support DML in BigQuery?** Yes, within supported capabilities/documentation.
8. **Are Iceberg metadata and Parquet synonymous?** No; Iceberg is a format for managing tables and snapshots.
9. **Why do we need Bronze?** Replay, source fidelity, traceability, and investigation.
10. **Why not push invalid files straight into Silver?** Quality and types are unverified; they belong in quarantine.
11. **Does Pub/Sub automatically eliminate all business duplicates?** No; you need event identity, checkpoints, and deduplication.
12. **Does Dataform replace Pub/Sub/Dataflow?** No, it primarily manages SQL workflows and assertions.
13. **Does the Catalog grant table read permissions?** No; IAM and policies control access.
14. **What does data lineage help with?** Tracking upstream/downstream dependencies, impact analysis, and auditing.
15. **Does CMEK on a BigQuery table automatically protect external GCS files?** No.
16. **Should Cloud Storage Bucket Lock be enabled as a test in a lab?** No; locking a retention policy is irreversible.
17. **When Gold queries are slow, does increasing Raw retention help?** No; inspect SQL, partitioning, caching, and capacity instead.
18. **When should you choose native BigQuery over Iceberg?** When you only need BigQuery analytics and want simpler operations.
19. **Why can a data lake turn into a data swamp?** Lack of ownership, metadata, quality checks, retention, and access controls.
20. **Why must you include DCU/GCS charges when using Iceberg managed?** Because costs are not limited to BigQuery query compute.

## 18. Production Checklist and Google Cloud Documentation

- [ ] Clear use cases and consumers/SLOs, with lake/warehouse/lakehouse compared.
- [ ] Data contracts specify owner, source ID, schema version, event time, and retention.
- [ ] Decided whether raw/bronze/silver/gold are all needed or can be consolidated.
- [ ] Parquet/Avro/JSON format and file size/partition design match the workload.
- [ ] Layered IAM across GCS, BigQuery, and BigLake connections; no policy-violating direct access.
- [ ] Project, region, bucket/dataset/connection locations satisfy residency requirements.
- [ ] Read-only BigLake external tables are not confused with DML-capable Iceberg managed tables.
- [ ] Iceberg multi-engine access has write ownership, snapshot/metadata management, and cleanup plans.
- [ ] Tested schema validation, dedup/replay, DLQs, and incremental updates.
- [ ] Silver/Gold have DQ gates, quality scores, and business reconciliation.
- [ ] Knowledge Catalog records searchable metadata/ownership/lineage.
- [ ] BigQuery row/column masking/policy tags tested against real principals.
- [ ] Data retention/backups/PII deletion applied across all copies and derived data.
- [ ] Monitoring covers end-to-end freshness, failures, backlog, query p95, and cost per data unit.
- [ ] BigQuery dry run, maximum bytes billed, and partition pruning verified.
- [ ] Change approval, rollback/backfill, on-call runbooks, and budgets in place.

**Official documentation (verify edition/region/feature availability at deployment time):**

- [BigQuery introduction to external sources](https://docs.cloud.google.com/bigquery/docs/external-data-sources) — distinguish external/BigLake/object tables.
- [Create Cloud Storage BigLake tables](https://docs.cloud.google.com/bigquery/docs/create-cloud-storage-table-biglake) — BigLake connections, DDL, IAM.
- [BigLake tables overview](https://docs.cloud.google.com/bigquery/docs/biglake-intro) — access delegation, read-only, storage.
- [BigLake external metadata caching](https://docs.cloud.google.com/bigquery/docs/metadata-caching-external-tables) — cache freshness and performance.
- [Apache Iceberg managed tables in BigQuery](https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery) — open table format, GCS, DML/metadata.
- [BigQuery native tables](https://docs.cloud.google.com/bigquery/docs/tables-intro) — storage, views, and DML.
- [Introduction to data governance in BigQuery](https://docs.cloud.google.com/bigquery/docs/data-governance) — catalog/quality/lineage.
- [Knowledge Catalog automatic data quality](https://docs.cloud.google.com/dataplex/docs/use-auto-data-quality) — DQ rules/scans.
- [Knowledge Catalog data lineage](https://docs.cloud.google.com/knowledge-catalog/docs/about-data-lineage) — tracing and impact.
- [Column-level access control](https://docs.cloud.google.com/bigquery/docs/column-level-security) — policy tags.
- [Cloud Storage uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access) — IAM instead of ACLs.
- [Cloud Storage Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock) — irreversible retention.
- [BigQuery best practices for costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — dry run, max bytes billed.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) and [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — total cost.

**Remember:** A **data lake** optimizes keeping raw data and replayability; a **data warehouse** optimizes SQL/BI with business definitions; a **lakehouse** uses an open table format to combine multiple engines on object storage. On GCP, what matters most is not what you name the architecture, but choosing the **right table types, access controls, data quality/lineage, retention, and verifiable cost/SLOs**.
