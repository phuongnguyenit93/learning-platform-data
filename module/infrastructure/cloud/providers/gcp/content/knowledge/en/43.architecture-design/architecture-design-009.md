# Data Platform Architecture Combining BigQuery and Cloud Storage

A data platform on Google Cloud typically addresses two distinct needs: **storing raw source data in an auditable and reprocessable form**, while **delivering standardized, governed, and cost-controlled data for fast analytical queries**. Cloud Storage fits the object storage and data lake layer; BigQuery fits the SQL analytics, data warehouse, and lakehouse querying layer over external data.

Combining the two services lets organizations ingest logs, events, transactional data, partner files, and batch outputs into a scalable architecture. However, dropping files into a bucket and creating a BigQuery table is not enough to build a trustworthy data platform. The architecture must also define ingestion flows, data zones, schemas, quality checks, identities, data locations, query practices, recoverability, and cost allocation.

This lesson constructs a reference data platform architecture using **Cloud Storage as the landing/raw lake** and **BigQuery as the warehouse/analytics engine**, while distinguishing external tables, BigLake, loading into native tables, and operating batch or near-real-time pipelines.

## 1. Separating Roles Between Cloud Storage and BigQuery

### Cloud Storage: Object Storage and Raw Data

Cloud Storage stores objects in buckets with high durability, well-suited for:

- Raw files from applications, partners, CDC, devices, or external systems.
- Semi-structured data like JSON and columnar formats like Parquet, Avro, and ORC.
- Large or infrequently queried data retained for auditing, replay, or reprocessing.
- Exports, logical snapshots, and inter-system exchange datasets.
- Multi-stage data zones such as raw, quarantine, and archive.

Cloud Storage **does not natively provide a full SQL data warehouse** over objects. Users need an engine like BigQuery or another processing system to turn files into queryable datasets.

### BigQuery: Tabular Storage and SQL Analytics

BigQuery provides large-scale analytical query processing with SQL, dataset/table management, access governance, and optimization options such as partitioning, clustering, materialized views, and compute capacity management.

BigQuery is suited for:

- Ad-hoc queries, BI, and dashboards.
- Data marts with consistent schemas.
- Multi-dimensional aggregations and analytics.
- Repeatedly queried cleaned/curated tables.
- Policy-compliant data sharing at dataset, table, row, and column levels.
- Running ELT transformations in SQL.

### The Bridge Between Lake and Warehouse

BigQuery can read data stored in Cloud Storage via **external tables**; **BigLake external tables** add connection-based access governance and supported external data management capabilities. Alternatively, data can be **loaded into BigQuery native tables** to leverage warehouse storage optimizations and management.

| Need | Commonly Suitable Option | Reason |
|---|---|---|
| Keep original files untouched for reprocessing | Cloud Storage | Decoupled from analytical schemas |
| Query a Parquet set infrequently | BigQuery external table | Avoids ingesting a copy into native tables |
| Query the lake with connection-based access governance | BigLake external table | Centralizes external data access control |
| Repeated dashboard queries and large joins | BigQuery native table | Leverages partitioning, clustering, and execution optimizations |
| Periodic batch ingestion | GCS → BigQuery load job | Simple, suited for batch |
| Continuous low-latency events | Pub/Sub/Dataflow → BigQuery | Streaming ingestion and transformation |

Decisions should not rest on buzzwords like "data lake" or "lakehouse", but on **query patterns, latency, storage cost, data permissions, and reuse needs**.

## 2. Reference Architecture from Source to Analytics

A data platform can consist of six layers:

1. **Sources:** applications, transactional databases, logs, partner files, and event streams.
2. **Ingestion:** batch transfers, Pub/Sub, Dataflow, or CDC pipelines.
3. **Raw lake:** Cloud Storage holding original data and ingestion metadata.
4. **Processing:** Dataflow, BigQuery SQL/Dataform, or standardizing batch pipelines.
5. **Curated warehouse:** BigQuery staging, cleaned datasets, and data marts.
6. **Consumption & governance:** BI, notebooks, ML, data catalogs, IAM, quality, and observability.

~~~mermaid
flowchart TD
    A[Applications and partners] --> B[Batch ingestion]
    C[Databases and CDC] --> D[Datastream or Dataflow]
    E[Application events] --> F[Pub/Sub]
    F --> G[Dataflow streaming]
    B --> H[Cloud Storage raw lake]
    D --> H
    G --> H
    G --> I[BigQuery staging]
    H --> J[External or BigLake tables]
    H --> K[BigQuery load jobs]
    K --> I
    I --> L[Transform and data quality]
    J --> L
    L --> M[BigQuery curated and marts]
    M --> N[BI dashboards and analytics]
    M --> O[Machine learning and downstream APIs]
    P[IAM governance metadata and lineage] -.-> H
    P -.-> M
    Q[Monitoring logging budgets] -.-> B
    Q -.-> L
    Q -.-> M
~~~

This diagram shows **available paths**, without requiring every source to use all services simultaneously. For example, partner CSV files can land straight in Cloud Storage and proceed through a load job. Events needing near-real-time visibility can flow via Pub/Sub → Dataflow → BigQuery; if long-term replay is needed, the pipeline can also write a controlled raw copy to Cloud Storage.

### Why keep a raw lake?

When a bug hits transformation logic, retaining original data lets you rerun pipelines without asking upstream sources to re-emit data. A raw lake also supports traceability: which input files produced a given figure on a report?

However, a raw lake is not exempt from management responsibilities. Restrict permissions, classify sensitive information, set retention policies, attach metadata, and avoid generating countless tiny unmanageable files.

## 3. Separating Data Zones: Raw, Staging, Curated, and Marts

A clean architecture separates data by trustworthiness tiers.

| Zone | Suggested Location | Contents | Consumers |
|---|---|---|---|
| Landing/raw | Dedicated Cloud Storage bucket/prefix | Original files, original schema, ingestion metadata | Pipelines and data engineers |
| Quarantine | Restricted Cloud Storage bucket/prefix | Files failing format, checksum, or schema checks | Data operations team |
| Staging | Dedicated BigQuery dataset | Newly loaded data, not yet fully validated | ELT jobs |
| Cleaned/curated | Dedicated BigQuery dataset | Standardized types, deduplicated, quality-checked | Data analysts, data products |
| Gold/data marts | Domain-scoped BigQuery datasets | Fact/dimension tables, aggregates, BI | Dashboards, authorized consumers |
| Archive | Appropriate Cloud Storage storage class | Older, infrequently queried data retained by policy | Replay/audit on demand |

These zones mirror bronze/silver/gold concepts without mandating those exact names. More importantly, **a zone must contain only data that meets its corresponding quality commitment**.

### Never mix raw and data marts

If dashboards query raw files with drifting schemas directly, a single malformed file can break reporting. Staging and quality-gate layers isolate faults before data reaches users.

### Responsibilities of each zone

- Raw: never mutate original objects once published; record source and ingestion time.
- Staging: verify files are readable, types parse cleanly, and metadata is complete.
- Curated: validate business keys, deduplication, freshness, and normalization.
- Marts: maintain stable data contracts for BI and downstream systems.

## 4. Designing Projects, Locations, and Environment Boundaries

A data platform must decide upfront which project holds the data, which region it lives in, and who can access it.

Example organization:

~~~text
gcp-data-dev          : development, synthetic data
gcp-data-staging      : pipeline and data contract testing
gcp-data-prod         : production pipelines and tables
gcp-security-logging  : audit logs and policy-driven monitoring
~~~

In production, projects can be split across ingestion, analytics, and security responsibilities. Keep project count proportional to operational complexity; separating projects only adds value when IAM, billing, and ownership boundaries are genuinely distinct.

### Location compatibility

- Choose Cloud Storage bucket locations based on residency, latency, and data sources.
- Choose BigQuery dataset locations before creating tables; dataset locations cannot simply be altered with a quick config flag later.
- For load jobs or external tables, **bucket locations and BigQuery dataset locations must be compatible per BigQuery location rules**. Do not assume every multi-region bucket is compatible with every regional dataset inside it.
- For Dataflow, Pub/Sub, or cross-region pipelines, examine where processing runs, data movement, and egress.
- If using CMEK, key locations and encrypted services must match service-specific compatibility requirements.

For example, a regional design might co-locate raw buckets and BigQuery datasets in `asia-southeast1` after verifying service availability and policies. Do not pick a region purely for proximity to end users; legal requirements and upstream source locations matter just as much.

### Environment isolation

Never let a staging pipeline write into production buckets or datasets just to save effort creating test fixtures. Use separate service accounts, resource names, quotas, and test data, validating production infrastructure via IaC and release approvals.

## 5. Cloud Storage Layout: Buckets, Prefixes, and Object Naming

Cloud Storage uses flat object names inside buckets; `/` is conventionally used to build meaningful prefix hierarchies.

An operable naming convention:

~~~text
gs://ORG-RAW-BUCKET/
  source=orders-api/
    entity=orders/
      ingest_date=2026-11-19/
        batch_id=run-8c31/
          part-00001.parquet
          part-00002.parquet
          manifest.json
  source=partner-x/
    entity=payments/
      ingest_date=2026-11-19/
        batch_id=run-6e02/
          part-00001.jsonl
~~~

Benefits:

- Scopes data cleanly by source, entity, and batch.
- Simplifies completeness checks, replay, retention, and lifecycle rules.
- Prevents dumping millions of unstructured objects into one flat logical prefix.
- Enables routing pipelines by predictable prefixes.
- Controls scanned data volume when defining external tables.

### Ingestion date vs. event date

- `event_date`: the date the event occurred in the source system.
- `ingest_date`: the date the data platform received the data.

An order created on the 15th and ingested on the 19th is late-arriving data. Analyzing daily sales revenue using only `ingest_date` yields wrong results. Preserve both source timestamps and ingestion timestamps.

### Avoiding partial objects and tiny files

An object should be considered complete only after its upload finishes successfully. A multi-object batch should include a manifest or completion marker rather than relying on seeing the first file appear.

Numerous tiny Parquet files inflate metadata listing/reading overhead and degrade processing efficiency. Pipelines should target file sizes suited to the workload and engine rather than forcing one arbitrary fixed size across all sources.

### Immutability

For raw data used in audits/replays, prefer writing new objects rather than overwriting in place. Use object generations and preconditions to prevent accidental overwrites. When enabling versioning or retention, account for version storage costs and deletion enforcement rules.

## 6. Choosing Data Formats and Managing Schemas

Common formats:

| Format | Benefits | Limitations and Watch-outs |
|---|---|---|
| CSV | Simple, easy to exchange with partners | Weak schema/type representation, prone to delimiter and encoding bugs |
| JSON Lines | Easy per-event emission, flexible schema | Larger footprint; requires handling nested fields and schema drift |
| Avro | Embedded schema, supports structured data and complex types | Requires coordinating schema registries and compatibility rules |
| Parquet | Columnar, strong compression, great for analytics | Not optimized for single-record updates; many tiny files hurt performance |
| ORC | Columnar, fits select analytical workloads | Compatibility depends on toolchain |

For batch analytics frequently reading subsets of columns, Parquet is a popular choice. For streaming events, JSON or Avro can be convenient at ingestion, after which pipelines compact and standardize into Parquet for long-term storage.

### Schema evolution

An upstream source may add a column, change `price` from `STRING` to `NUMERIC`, or alter the meaning of `status`. Classify changes:

- Compatible changes: adding nullable or optional fields.
- Migration-required changes: changing data types, dropping fields, changing business semantics.
- Contract-breaking changes: reusing an old field name with a new meaning.

Do not turn on schema autodetection and assume every incoming file is valid. In production, enforce schema contracts, versioning, and error handling for invalid fields.

### Ingestion metadata

Every record or batch should capture at least:

- Source system and entity.
- Batch/run ID.
- Event timestamp and ingestion timestamp.
- Schema version.
- Object URI, generation, or checksum where applicable.
- Expected and actual record counts.

This metadata enables tracing back from BigQuery to the exact source file.

## 7. Choosing Ingestion Architecture by Latency

### Batch ingestion

Suited for partner files, daily exports, or periodic batches from source systems:

~~~text
Source export
  → Cloud Storage landing
  → Validate files/manifest
  → BigQuery load job
  → SQL transforms and quality gate
  → Curated tables and marts
~~~

Orchestrate using Cloud Scheduler + Workflows, Cloud Composer, or an appropriate pipeline orchestrator. BigQuery Data Transfer Service supports scheduled transfers from Cloud Storage for certain patterns, though you must verify source types and file naming rules when choosing it.

### Streaming or near-real-time

~~~text
Application event → Pub/Sub → Dataflow → BigQuery
                                  └─────→ Cloud Storage raw
~~~

For direct writes into BigQuery, evaluate the BigQuery Storage Write API and supported connectors. Streaming does not mean every record is instantaneously ready for every downstream query; define freshness targets and measure end-to-end latency from source to destination table.

### CDC

For source databases, Datastream or other CDC solutions can export changes into Cloud Storage/BigQuery via supported pipelines. CDC streams contain updates, deletes, and out-of-order events; **you cannot simply append all changes and treat the resulting table as current state**.

### When is Cloud Storage needed in the middle?

Raw Cloud Storage helps when you need replay, auditing, file exchange, or untouched source copies. If the application needs low-latency near-real-time analytics, a direct Pub/Sub/Dataflow → BigQuery path can work well while writing raw copies asynchronously if required by policy.

## 8. BigQuery External Tables: Querying Data in Cloud Storage

BigQuery external tables declare a schema/table to query files in place without necessarily loading everything into native BigQuery storage.

Suppose you have Parquet files:

~~~text
gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/part-00001.parquet
gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/part-00002.parquet
~~~

You can create an external table for the sample batch:

~~~sql
CREATE OR REPLACE EXTERNAL TABLE `PROJECT_ID.raw.orders_20261119_external`
OPTIONS (
  format = 'PARQUET',
  uris = [
    'gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/*.parquet'
  ]
);
~~~

BigQuery reads the Parquet schema and queries the matching objects. Ensure bucket locations are compatible with the BigQuery dataset and callers hold required permissions.

Query:

~~~sql
SELECT
  status,
  COUNT(*) AS order_count
FROM `PROJECT_ID.raw.orders_20261119_external`
GROUP BY status
ORDER BY order_count DESC;
~~~

The example uses a wildcard for files within a single date partition. When building external tables across many dates or Hive-style partitioning, configure partition discovery/prefixes per supported table capabilities rather than assuming an arbitrary wildcard handles arbitrary nested directory trees.

### When to use external tables?

- Exploring and validating newly arrived files.
- Reading infrequently accessed data.
- Querying datasets shared across multiple engines via Cloud Storage.
- Performing data discovery or migration checks.

### Limits to keep in mind

External table queries depend on external storage latency, file structure, object count, schemas, and underlying storage behavior. Do not assume native BigQuery performance, DML support, or caching behavior. Benchmark for your specific workload and external table type.

## 9. BigLake and Access Governance Boundaries

**BigLake external tables** use a Cloud resource connection to access data outside BigQuery via a managed identity, rather than requiring every SQL user to hold direct bucket permissions as with traditional external tables.

Concept:

~~~mermaid
flowchart LR
    A[Analyst or BI service] --> B[BigQuery table permissions]
    B --> C[BigLake external table]
    C --> D[Cloud resource connection]
    D --> E[Connection service account]
    E --> F[Cloud Storage objects]
~~~

General setup workflow:

1. Create a BigQuery connection in a location compatible with the dataset.
2. Identify the service account bound to that connection.
3. Grant least-privilege object read permissions to that service account on the target bucket/prefix per policy.
4. Create the BigLake external table referencing the connection and data URIs.
5. Grant BigQuery dataset/table permissions to querying principals.
6. Test both allowed and denied access paths, and enable audit logs.

Never grant `roles/storage.admin` to all analysts just so they can query BigLake. BigQuery permissions, connection usage rights, and object access permissions are separate layers.

### Standard external tables vs. BigLake?

| Criterion | Standard External Table | BigLake External Table |
|---|---|---|
| Goal | Query files outside BigQuery | Query files outside BigQuery with more integrated access governance |
| Cloud Storage access | Depends on standard mechanisms and querying principal | Can delegate via connection service account |
| SQL permissions | Based on BigQuery IAM | Based on BigQuery IAM and connection configuration |
| Cost / performance | Depends on format, queries, and source type | Benchmark on real workloads |
| Typical use case | Simple file analysis | Shared data lake across multiple teams needing access control |

Feature names, caching limits, fine-grained access control capabilities, and supported formats vary by table type and service version; check product documentation before locking in a capability as a hard requirement.

## 10. Loading into BigQuery Native Tables

When data is queried frequently or participates in heavy joins/aggregations, loading into native BigQuery tables is usually more convenient for schema management, partitioning, and query optimization.

Example creating a dataset and loading a Parquet batch:

~~~bash
bq mk --dataset --location=asia-southeast1 PROJECT_ID:staging

bq load \
  --source_format=PARQUET \
  PROJECT_ID:staging.orders_20261119 \
  "gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/*.parquet"
~~~

This is a lab example; replace project, bucket, location, and paths with real values. If the dataset already exists, skip creation or check existence beforehand.

### Avoiding duplicate appends on retries

If a load job times out on the orchestrator side, do not assume the job failed—it may still be running or may have already succeeded. Retrying an append command into the same table without idempotency can duplicate rows.

Safer design:

- Assign each batch a unique `batch_id`.
- Load into a dedicated staging table or managed temporary partition.
- Record job IDs, source object generations, and completion status.
- Retry based on existing job state or perform batch-idempotent operations.
- Publish into curated tables only after completeness/quality checks pass.
- Use `MERGE` or controlled partition replacement when updating data.

**Cloud Storage does not share a distributed transaction with BigQuery.** Design orchestration explicitly to avoid states like "file landed yet table missed it" or "table loaded twice".

## 11. Designing BigQuery Partitioning and Clustering

Native BigQuery tables can be partitioned by an appropriate date or timestamp and clustered by frequently filtered columns.

Example creating a curated table:

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.curated.orders` (
  order_id STRING NOT NULL,
  order_ts TIMESTAMP,
  order_date DATE,
  customer_id STRING,
  amount NUMERIC,
  status STRING,
  updated_at TIMESTAMP
)
PARTITION BY order_date
CLUSTER BY customer_id, status
OPTIONS (
  description = 'Current curated order records'
);
~~~

### Which column to partition by?

- `order_date`: sensible if BI dashboards filter by order placement date.
- `ingest_date`: may fit if queries mostly target ingested batches and handle late arrivals explicitly.
- Another partition key: choose based on real `WHERE` clauses and update patterns.

If dashboards typically inspect the last 7 or 30 days, partition pruning cuts scanned bytes. Ensure queries actually filter on the partition column.

### Clustering

Clustering by `customer_id` or `status` can speed up certain filters and joins, though it does not automatically accelerate every query. Effectiveness depends on table size, data skew, and query patterns. Avoid clustering on near-unique IDs without a clear query pattern.

### Avoid `SELECT *`

~~~sql
SELECT
  order_id,
  order_ts,
  amount
FROM `PROJECT_ID.curated.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-19';
~~~

The query selects only needed columns and filters the partition. Under many BigQuery pricing models, bytes processed is a primary cost driver; adding slots or capacity cannot fix a query scanning unnecessary columns.

## 12. ELT and Data Quality: Turning Raw into Curated

In ELT, data lands in staging first and is transformed via BigQuery SQL. For pipelines handling complex formats or streaming, Dataflow can run transformations prior to writing to BigQuery.

### Standardizing fields and filtering bad records

Suppose the staging table has text and timestamp columns:

~~~sql
CREATE OR REPLACE TABLE `PROJECT_ID.staging.orders_validated` AS
SELECT
  CAST(order_id AS STRING) AS order_id,
  TIMESTAMP(order_time) AS order_ts,
  DATE(TIMESTAMP(order_time)) AS order_date,
  CAST(customer_id AS STRING) AS customer_id,
  SAFE_CAST(amount AS NUMERIC) AS amount,
  CAST(status AS STRING) AS status,
  TIMESTAMP(updated_time) AS updated_at
FROM `PROJECT_ID.staging.orders_20261119`
WHERE
  order_id IS NOT NULL
  AND SAFE_CAST(amount AS NUMERIC) IS NOT NULL;
~~~

This SQL pattern is illustrative: the staging schema must contain fields and types compatible with these expressions. For sources prone to malformed timestamps, use `SAFE_CAST(... AS TIMESTAMP)` and route unparseable rows to a quarantine table rather than letting the entire job crash unexpectedly.

### Quality gates

Metrics to verify:

- Source row count vs. loaded row count.
- Rate of schema/parsing errors.
- Null or duplicate business keys.
- Invalid negative numbers or out-of-domain statuses.
- Abnormal value distribution shifts compared to prior days.
- Freshness: is the newest data arriving on schedule?
- Batch completeness and checksum/manifest match.

Example table check:

~~~sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT order_id) AS distinct_order_ids,
  COUNTIF(order_id IS NULL) AS null_order_ids,
  COUNTIF(amount < 0) AS negative_amounts
FROM `PROJECT_ID.staging.orders_validated`;
~~~

Enforce quality thresholds before publishing. Quarantine failing records for remediation and replay instead of silently dropping them without counting.

### Dataform and orchestration

Dataform or compatible SQL transformation tools manage table dependencies, test assertions, and publish transformations under version control. Orchestrators like Workflows or Cloud Composer coordinate dependencies and retries. Whichever tool you pick, record the SQL version, source batch, and quality-gate results.

## 13. Incremental `MERGE`, Deduplication, and Late-Arriving Data

Source applications may emit the same record multiple times or update an order days after creation. Simply appending every batch into curated tables causes downstream queries to see multiple versions of the same order.

### Deduplicate by business key

Suppose staging holds multiple versions of an order:

~~~sql
SELECT
  order_id,
  customer_id,
  order_ts,
  order_date,
  amount,
  status,
  updated_at
FROM `PROJECT_ID.staging.orders_validated`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY order_id
  ORDER BY updated_at DESC
) = 1;
~~~

When multiple records share the exact same `updated_at`, add a deterministic tie-breaker such as source sequence, event version, or ingestion sequence. Ordering solely by timestamp may pick arbitrarily.

### Incremental upsert with `MERGE`

~~~sql
MERGE `PROJECT_ID.curated.orders` T
USING (
  SELECT
    order_id, customer_id, order_ts, order_date,
    amount, status, updated_at
  FROM `PROJECT_ID.staging.orders_validated`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY updated_at DESC
  ) = 1
) S
ON T.order_id = S.order_id
WHEN MATCHED AND S.updated_at >= T.updated_at THEN
  UPDATE SET
    customer_id = S.customer_id,
    order_ts = S.order_ts,
    order_date = S.order_date,
    amount = S.amount,
    status = S.status,
    updated_at = S.updated_at
WHEN NOT MATCHED THEN
  INSERT (order_id, customer_id, order_ts, order_date, amount, status, updated_at)
  VALUES (S.order_id, S.customer_id, S.order_ts, S.order_date, S.amount, S.status, S.updated_at);
~~~

This example maintains current-state order records. On huge tables, `MERGE` by business key can scan many partitions; consider narrowing date/partition predicates when business rules allow, clustering, and inspecting query plans. Never inject a date filter into the `ON` clause if it could cause an older order update to be inserted as a duplicate row.

### Late arrivals and corrections

Late-arriving data needs a watermark strategy and reprocessing window. For example, each run reprocesses the last 3 days alongside a weekly batch reconciliation. Window sizes must fit source behavior; very late corrections may need dedicated backfill workflows.

### Delete events and CDC

CDC deletes must not be ignored. When an event indicates deletion, the curated model must specify whether to hard-delete, soft-delete, or retain a tombstone. This depends on audit needs and downstream contracts, not merely picking the row with the largest `updated_at`.

## 14. Data Governance and Access Control

Data platforms frequently hold financial records, user profiles, sensitive logs, or internal business metrics. Design IAM and governance from day one.

### Layered IAM

| Principal | Typical Permissions | Principle |
|---|---|---|
| Ingestion service account | Write objects to raw bucket | Scoped strictly to allowed buckets/prefixes |
| Transformation service account | Read raw, run BigQuery jobs, write staging/curated | Scoped to specific datasets and resources |
| Analyst | Run BigQuery queries, read marts | No default read access to raw or staging |
| BI service account | Read-only access to data marts or authorized views | Strictly read-only as needed |
| Governance / security | Inspect metadata, audits, and policies | Separate from querying payload data unless required |
| Pipeline deploy identity | Modify IaC/pipeline configs | Never reuse runtime accounts as deploy admins |

Common roles include `roles/storage.objectViewer`, `roles/storage.objectCreator`, `roles/bigquery.jobUser`, `roles/bigquery.dataViewer`, and `roles/bigquery.dataEditor`. Verify role scopes, granular permissions, and connection models for your actual project.

### Protecting Cloud Storage

- Enable uniform bucket-level access where suitable.
- Enforce public access prevention on internal buckets.
- Never share raw buckets directly with all analysts.
- Configure lifecycle, retention, and versioning aligned with data classes.
- Avoid static service account keys; prefer Workload Identity Federation and runtime identities.

### Protecting BigQuery

BigQuery supports dataset, table/view permissions, and fine-grained controls such as row-level access policies, column-level security via policy tags, or data masking where supported by service capabilities and policy.

For example, analysts may view total revenue by region without viewing customer emails. Expose marts, authorized views, or protective policies rather than letting users run `SELECT *` on raw tables containing PII.

### Encryption and perimeter controls

Cloud Storage and BigQuery provide default Google-managed encryption; when organizational policy requires customer-managed keys, configure CMEK on supported resources and secure key IAM. VPC Service Controls can help mitigate exfiltration risks in suitable architectures; they do not replace IAM and do not automatically block every data-leak path.

## 15. Metadata, Lineage, and Data Catalog

As datasets multiply, users must be able to answer:

- Where did this data originate?
- Who owns it?
- What are the column schemas and business definitions?
- How often is the dataset updated?
- Does it contain PII or sensitive fields?
- Which dashboards depend on which tables?
- If a column is renamed or dropped, which consumers break?

A data catalog/governance layer—such as Dataplex's cataloging and data quality capabilities—can manage metadata, classification, and discovery. Lineage must be captured from actual pipelines rather than guessed solely from filenames.

### Minimum metadata for a data product

| Field | Example |
|---|---|
| Data product | `orders_curated` |
| Owner | Commerce data team |
| Source | `orders-api` |
| Frequency | Every 15 minutes |
| Freshness objective | 99% of batches ready within 15 minutes |
| Primary key | `order_id` |
| Partition key | `order_date` |
| Classification | Internal; may contain customer identifiers |
| Data contract | Schema v2 |
| Retention | Per approved data retention policy |
| Runbook | Procedure for failed batches and backfills |

The timing figures above are hypothetical targets. Derive real SLOs from actual user needs.

### Data lineage

A lineage chain can be traced as:

~~~text
gs://raw/.../batch_id=run-8c31/part-00001.parquet
  -> staging.orders_20261119
  -> staging.orders_validated
  -> curated.orders
  -> marts.daily_revenue
  -> BI dashboard
~~~

When a dashboard metric looks wrong, lineage traces back to the exact job, SQL, source, and batch needing reconciliation.

## 16. Pipeline Observability and Data SLOs

An ops dashboard showing only "job succeeded" is insufficient. A pipeline can succeed while loading incomplete rows or arriving late.

### SLIs to track

| Category | Metrics | What to Detect |
|---|---|---|
| Ingestion | Arriving batches/files, bytes, object generations | Did upstream deliver complete data? |
| Freshness | Time from event to curated table | Is data delayed? |
| Completeness | Expected vs. ingested/curated record counts | Was data dropped? |
| Quality | Null keys, duplicates, invalid schemas | Is the data trustworthy? |
| Pipeline | Job duration, failures/retries, backlogs | Where is the bottleneck? |
| Query | Slot usage, bytes processed, latency | Are queries blowing budgets? |
| Security | IAM changes, access denials, sensitive reads | Any anomalous access? |
| Cost | Storage, compute, transfer, logging | Where are costs spiking? |

An illustrative SLO:

> 99% of order batches are published to the curated dataset within 15 minutes of manifest completion; 100% of failed batches trigger alerts with runbooks.

Define the freshness clock start explicitly: event timestamp, object finalization, or manifest readiness? Never mechanically compare metrics across pipelines using different start anchors.

### Cloud Monitoring and Cloud Logging

Collect logs from Dataflow, orchestrators, BigQuery jobs, and ingestion services. Export custom metrics for record counts, quality scores, latency, and backlogs. BigQuery `INFORMATION_SCHEMA` offers rich job metadata; ensure view scopes, regions, and IAM permissions match the queried project.

Useful fields to track on failed jobs from logs:

- Pipeline run ID and batch ID.
- GCP job ID, status, and error code.
- Source object URIs, generations, and row counts.
- Query/destination table.
- Retry count and owner.
- Start/end timestamps.

Never write customer row payloads or secret values into logs.

## 17. Platform-Wide Performance and Cost Optimization

Total cost is not just BigQuery queries. Factor in object storage, object operations, Dataflow/compute, cross-region data transfer, orchestration, and observability.

### BigQuery

- Partition aligned with how users query.
- Cluster when tables are large enough and filter patterns benefit.
- Avoid `SELECT *` on wide tables.
- Use pre-aggregated data marts or materialized views where workloads justify them.
- Evaluate on-demand vs. capacity/editions compute pricing per organizational profile.
- Run query dry runs and inspect bytes processed / slot usage before approving expensive queries.
- Set project/workload quotas and cost alerts.

### Cloud Storage

- Use columnar formats and appropriate compression for frequently scanned files.
- Right-size objects and counts for ingestion and query patterns.
- Choose storage classes and lifecycle rules matching real access frequency.
- Weigh operation charges, retrieval fees, minimum storage durations, and egress when transitioning classes or regions.
- Avoid keeping identical raw and curated duplicates without a clear recovery or governance purpose.

### External vs. native

External tables avoid copying data, yet repeated queries may scan many objects repeatedly. Native tables carry BigQuery storage charges, yet often provide superior query speed and optimization for high-frequency dashboards.

Benchmark with **the exact same dataset, query mix, and freshness target**. There is no universal rule that "external is always cheaper" or "native is always faster" for every workload.

### Cost per data product

A helpful KPI is the cost to deliver clean, user-ready data—such as cost per million valid records or monthly cost of a data mart. Saving pennies on raw storage while forcing pipelines to reprocess the entire history daily can raise total cost.

## 18. Reliability, Backups, and Data Recovery

The architecture must handle two failure categories:

1. Pipeline failures: late data, job crashes, schema drift, or duplicate records.
2. Data/resource errors: accidental object deletion, table overwrites, misconfigured IAM, or corrupted datasets.

### Designing replay and reprocessing

Retain raw objects and batch metadata long enough to:

- Recreate staging after a failed load.
- Rerun transformations with updated SQL versions.
- Backfill missing time windows.
- Reconcile record counts and checksums against sources.
- Trace dashboard metrics back to raw inputs.

Replays must be **idempotent**: never duplicate curated rows or trigger unintended external business side effects.

### GCS versioning and retention

Versioning retains older object generations upon replacement or deletion per configuration. Retention policies prevent deleting objects before a minimum age; locking a retention policy strictly restricts edits. These mechanisms protect data differently and can increase storage costs.

### BigQuery recovery

BigQuery provides time travel within a configurable retention window within supported bounds; table snapshots/copies and exports also assist recovery and DR. Never rely solely on time travel for long-term archival or cross-region disaster recovery.

### DR and recovery objectives

Determine:

- RPO: maximum acceptable loss of recent data?
- RTO: maximum acceptable downtime before data products resume?
- Must raw, staging, or curated layers be restored first?
- Can BI consumers temporarily use the last published clean snapshot?
- Are standby resources provisioned in compliant regions?
- Are CMEK keys and IAM bindings available during recovery?

Run restore drills on test data; having backups does not prove restores will succeed.

## 19. Infrastructure as Code, CI/CD, and Schema Changes

To keep the platform maintainable, manage Cloud Storage, BigQuery datasets, IAM, connections, networking, and pipelines in code where fitting.

Minimal HCL example:

~~~hcl
resource "google_storage_bucket" "raw" {
  name                        = "ORG-UNIQUE-RAW-BUCKET"
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_bigquery_dataset" "curated" {
  dataset_id                 = "curated"
  location                   = "asia-southeast1"
  delete_contents_on_destroy = false
}
~~~

Bucket names must be globally unique; examples cannot be applied verbatim. Add retention, lifecycle, labels, CMEK, IAM, and deletion protections per organizational policy.

### Change management

- Pull request reviews for SQL transformations, schema contracts, and IaC.
- Terraform plan reviews before apply, especially for resource deletions/replacements.
- Unit tests for complex transformation logic.
- Integration tests on test datasets and production-like samples.
- Data quality assertions prior to publishing.
- Planned rollbacks or forward-fixes for schema changes.
- Never hardcode credentials in code or manifests.

In BigQuery, `DROP COLUMN`, type changes, or overwriting curated tables can break dashboards. Use backward-compatible column additions, views/versioned data products, and phased migrations.

## 20. Hands-On Scenario: Data Platform for an Ordering System

Suppose a system has:

- Orders API writing transactions to Cloud SQL.
- Pub/Sub emitting `OrderCreated` and `OrderUpdated` events.
- A partner exporting daily Parquet files of settled payments.
- A BI team needing revenue by day, region, and status.
- An operations team needing replay and reconciliation capabilities.

### Step 1 — Define data contracts

Define the order schema, business key `order_id`, source timestamps, event version, `amount`, `status`, `customer_id`, and schema version. Set freshness and completeness targets for each source.

### Step 2 — Create storage zones

Create a regional raw bucket and BigQuery datasets for `raw`, `staging`, `curated`, and `marts` in compatible locations. Configure uniform bucket-level access, IAM, and retention per policy.

### Step 3 — Partner batch ingestion

1. Partner uploads Parquet files under `source=partner/entity=payments/ingest_date=...`.
2. Ingestion workflow validates the batch manifest, checksums, and schema.
3. Invalid files move to quarantine with recorded reasons.
4. Valid files load into a staging table tagged by batch ID.
5. Quality gate checks record counts and business values.

### Step 4 — Event ingestion

Pub/Sub receives events, Dataflow normalizes and writes to BigQuery staging; raw events can also be archived to Cloud Storage for replay if policy requires. Every event carries an event ID and event timestamp, and consumers handle redeliveries and out-of-order arrivals.

### Step 5 — Curate and deduplicate

BigQuery SQL / Dataform:

- Normalize types and timezones.
- Deduplicate by `order_id` / event version.
- Apply updates/deletes from CDC if present.
- Route invalid records to quarantine.
- Publish `curated.orders` after quality gates pass.

### Step 6 — Build the revenue mart

Example:

~~~sql
CREATE OR REPLACE TABLE `PROJECT_ID.marts.daily_revenue`
PARTITION BY order_date
AS
SELECT
  order_date,
  status,
  COUNT(*) AS order_count,
  SUM(amount) AS total_amount
FROM `PROJECT_ID.curated.orders`
WHERE amount IS NOT NULL
GROUP BY order_date, status;
~~~

For multi-year tables, consider incremental partition updates instead of full-table `CREATE OR REPLACE` on every run. Also clearly define which statuses count toward recognized revenue so cancelled orders are excluded.

### Step 7 — Access control and observability

- Data engineering identity holds write rights on staging/curated.
- Analysts hold read-only rights on approved marts and views.
- BI service accounts never read raw PII directly.
- Dashboards track freshness, completeness, failed jobs, and BigQuery costs.
- Alerts fire on missing batches, error-rate threshold breaches, or missed data-product SLA windows.

### Step 8 — Verify recovery

Simulate a failed batch load. Use the raw objects and manifest to rerun the same batch, verifying curated tables have zero duplicates. Next, inject a schema change into a lab file and confirm quarantine/alerting triggers before onboarding the new source to production.

## 21. Common Design Mistakes

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| BI querying all raw JSON directly | Slow, brittle to schema drift, expensive scans | Standardize to Parquet or native curated tables |
| Overwriting raw files without tracking generations | Hard to audit or replay | Immutable objects and batch manifests |
| Tracking only ingestion date | Skewed event-date analytics and late-arrival errors | Store event time, ingest time, and watermarks |
| One service account privileged across all projects | Risk of data exposure or corruption | Separate identities by workload and environment |
| Skipping location checks | Load/external query failures or cross-region egress fees | Plan regions/datasets upfront |
| Blind appends after retries | Duplicate records | Idempotent loads and `MERGE` by business key |
| Dashboards reading staging tables | Unverified data quality reaches users | Publish curated tables only after quality gates |
| Running `SELECT *` on massive tables | Inflates bytes processed | Project needed columns, prune partitions, use marts |
| Keeping thousands of tiny KB-sized files | High metadata/query overhead | Batch and compact files appropriately |
| Omitting schema versions | Downstream breaks silently on source changes | Enforce data contracts and schema evolution |
| Never testing restores | Having backups without proving recovery | Run regular replay/restore drills |
| Monitoring only "job succeeded" | Misses dropped or delayed records | Track freshness, completeness, and correctness SLIs |

## 22. Pre-Production Architecture Checklist

### Planning and Source Data

- [ ] Sources, formats, volumes, frequencies, and target latencies are defined.
- [ ] Data contracts, business keys, and schema versions are established.
- [ ] Compatible locations are selected for buckets, BigQuery datasets, and pipelines.
- [ ] Sensitive data, owners, and retention rules are identified.
- [ ] Batch, streaming, or CDC chosen based on genuine needs.

### Cloud Storage and Ingestion

- [ ] Buckets enforce least-privilege IAM and public access prevention.
- [ ] Raw objects follow naming conventions, batch IDs, and metadata standards.
- [ ] Manifest/completeness checks and quarantine paths exist.
- [ ] Deduplication and retry logic prevent duplicate loads.
- [ ] Lifecycle/retention policies and cost controls are configured.

### BigQuery and Transformation

- [ ] External/BigLake/native choices match actual query patterns.
- [ ] Queries are verified for partition pruning and column projection.
- [ ] Schemas and transformations live under version control.
- [ ] Curated tables enforce quality gates and late-arrival handling.
- [ ] Dashboards query only stable data marts or views.
- [ ] SQL/ETL jobs emit traceable logs, job IDs, and lineage.

### Security and Governance

- [ ] Separate service accounts for ingestion, transformation, and consumption.
- [ ] IAM scoped accurately at bucket/dataset/table/connection levels.
- [ ] Row/column protections applied where data requires them.
- [ ] No hardcoded credentials; logs exclude unnecessary PII/secrets.
- [ ] Audit logs, catalogs, data owners, and policy exceptions are governed.

### SRE, Cost, and Recovery

- [ ] Freshness/completeness/correctness SLOs and alerts are active.
- [ ] Budgets, cost allocation, and query cost reviews are in place.
- [ ] Procedures exist for backfills, replays, quarantine, and rollbacks.
- [ ] Data restore tested in a safe environment.
- [ ] Runbooks exist for missing batches, schema drift, and runaway queries.
- [ ] IaC and SQL changes are reviewed prior to deployment.

A data platform combining **Cloud Storage + BigQuery** succeeds when it clearly separates raw source data from analytics-ready data, picks fitting ingestion paths, enforces schema contracts, governs access from buckets to tables, and measures quality with data SLIs. With this design, an organization gains both a flexible storage foundation for auditing/replay and a powerful warehouse for BI and analytics on Google Cloud.
