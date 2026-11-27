# Apache Iceberg Table Format and Table Lifecycle Management

A data lake typically stores data as Parquet, ORC, or Avro files on Amazon S3. However, a directory full of files is not enough to function as a reliable database table: the system needs to know which files belong to the table, what the current schema is, how partitions are organized, which writes have committed, and which version of data queries should read. If every engine infers file lists from directories independently, concurrent updates, record deletions, schema changes, and historical reads become difficult to control.

Apache Iceberg is an open table format that addresses this table management layer. Iceberg stores versioned metadata describing data file sets, snapshots, schemas, and partition specs. Multiple query engines can read the same table through a shared catalog while writes commit under Iceberg's transaction model.

On AWS, a common architecture uses Amazon S3 to store data and metadata files, AWS Glue Data Catalog as the catalog, AWS Lake Formation to govern access permissions, and AWS Glue, Amazon EMR, Amazon Athena, and Amazon Redshift for ETL or analytics. Crucially, engines must be compatible with the same table format version, catalog, and commit mechanism.

This lesson focuses on Iceberg table structure, snapshots and metadata trees, schema/partition evolution, time travel, concurrent writes, and maintenance operations such as compaction, snapshot expiration, and orphan file deletion.

## Learning Objectives

After this lesson, you can:

- Explain why Apache Iceberg is a table format rather than a file format.
- Describe the relationships among data files, metadata JSON, snapshots, manifest lists, manifests, and the catalog.
- Understand how Iceberg commits table changes and handles concurrent writers.
- Create and read Iceberg tables on Amazon S3 using AWS Glue and AWS Glue Data Catalog.
- Distinguish Iceberg format v1, v2, and v3, and evaluate cross-engine compatibility.
- Apply schema evolution and partition evolution without rewriting all data.
- Query historical snapshots, time travel, and metadata tables.
- Use Athena, Glue, and Spark to write, update, delete, and optimize data.
- Design safe policies for compaction, snapshot retention, and orphan file cleanup.
- Architect the table lifecycle from ingestion, querying, governance, and maintenance through archiving.

## 1. What Is Apache Iceberg?

Apache Iceberg is an open table format for large analytic datasets. It defines how to manage tables on object or file storage using versioned metadata, enabling engines to read a consistent table state and update tables atomically via transactions.

Distinguish three layers:

| Layer | Examples | Responsibility |
|---|---|---|
| File format | Parquet, ORC, Avro | Encodes rows and columns within an individual file. |
| Table format | Apache Iceberg | Manages file sets, schemas, partitions, snapshots, deletes, and commits. |
| Catalog | AWS Glue Data Catalog | Registers table names and points to current table metadata. |

Parquet itself does not know that hundreds of files in an S3 prefix belong to the same table or which files represent the latest version. Iceberg provides the metadata to answer those questions.

### 1.1. Comparison with Hive-Style Tables

With Hive-style external tables, metadata usually stores a partition list in the catalog. Each physical partition can correspond to a directory such as `year=2026/month=11/day=20/`. When adding partitions or changing layout, teams must keep catalog metadata and file layout synchronized.

Iceberg uses hidden partitioning. Engines query on business columns; Iceberg applies partition transforms and metadata to identify which files to read. Users do not have to manage partition directories manually as part of the table schema.

| Need | Hive-Style Table | Apache Iceberg |
|---|---|---|
| Tracking files belonging to table | Typically relies on location and partition metadata | Manifests and snapshots enumerate exact data files |
| Schema evolution | Depends on metastore and engine; renames can be unsafe | Uses field IDs and metadata-driven schema evolution |
| Partition evolution | Often requires creating new layouts/partitions and coordinating metadata | Partition spec can change while older files keep prior specs |
| Row-level update/delete | No unified transaction semantics from the table format | Supports DML via delete files and snapshot commits |
| Time travel | Not natively built in at the table format level | Query historical snapshots while retained |
| Concurrent writes | Fragile, relies on engines and operational conventions | Provides commit protocol and optimistic concurrency |

Iceberg does not replace Amazon S3, Parquet, or query engines. It adds metadata and transaction semantics so those components operate together as a table.

## 2. Metadata Architecture of an Iceberg Table

An Iceberg table typically has a root location on S3 containing data files and metadata files. The catalog stores table details and the current metadata location.

~~~mermaid
flowchart TD
    C["AWS Glue Data Catalog"] --> M["Current metadata JSON"]
    M --> S["Current snapshot"]
    S --> ML["Manifest list"]
    ML --> MF1["Manifest A"]
    ML --> MF2["Manifest B"]
    MF1 --> D1["Parquet data files"]
    MF1 --> X1["Delete files (v2)"]
    MF2 --> D2["Parquet data files"]
    M --> SC["Schema + partition specs"]
    M --> H["Snapshot history"]
~~~

In Iceberg v1–v3, the metadata tree typically consists of:

| Component | Role |
|---|---|
| Data file | Stores data rows, commonly Parquet, ORC, or Avro. |
| Delete file | Tracks deleted rows, such as position deletes or equality deletes in Iceberg v2. |
| Manifest file | Avro metadata file listing a group of data files or delete files, partition values, and column metrics. |
| Manifest list | Metadata file for a single snapshot listing manifests and summary info for query planning. |
| Snapshot | Table state at a point in time, defining the set of files comprising the table's data. |
| Table metadata JSON | Stores schemas, partition specs, snapshots, properties, current snapshot, and metadata references. |
| Catalog entry | Stores the table name and current metadata location so engines can open the table. |

A snapshot is not a full copy of all data. It is a set of metadata pointers to immutable files. Multiple snapshots can share references to unchanged data files; a new snapshot only describes the metadata deltas.

### 2.1. Why Does the Metadata Tree Speed Up Queries?

Manifests hold partition tuples and column statistics such as lower/upper bounds, null counts, or value counts when present. Query engines can prune manifests or data files that cannot contain matching values before reading file contents.

For example, query:

~~~sql
SELECT order_id, amount
FROM analytics.orders
WHERE order_date = DATE '2026-11-20'
  AND customer_id = 'C-1001';
~~~

The engine uses partition specs and manifest metrics to eliminate irrelevant files, then reads only files that could potentially contain matching rows.

Metadata pruning reduces S3 requests, bytes scanned, and query duration. Effectiveness depends on file layout quality, partitioning strategy, statistics, and how well the query engine leverages metadata.

### 2.2. Metadata Is Not the Same as Data

Data files and metadata files are distinct object types. Deleting a metadata file referenced by the catalog or a snapshot can render the table unreadable. Deleting a data file referenced by the current snapshot can cause query errors or missing data.

Never use S3 Lifecycle expiration to delete files inside a table location by object age independently of Iceberg. File deletion must go through metadata-aware snapshot expiration or orphan file cleanup.

## 3. Snapshots and Transaction Commits

A snapshot represents the table state after a commit. When a writer appends, updates, deletes, or rewrites data, Iceberg writes new data/delete files and new metadata, then commits a snapshot.

A typical commit:

1. Writer reads the current metadata and current snapshot.
2. Writer creates new data files or delete files.
3. Writer creates manifests and a manifest list for the change.
4. Writer creates a new metadata JSON pointing to the new snapshot.
5. Writer asks the catalog to swap the current metadata location via an atomic commit.
6. If the commit succeeds, the new snapshot becomes the current table state.
7. If another writer committed first, the current writer can hit a conflict and must refresh metadata, revalidate changes, and retry.

Iceberg uses optimistic concurrency: multiple writers can prepare changes in parallel, yet commits succeed only when current metadata still satisfies transaction checks. Conflict validation prevents blind overwrites of another writer's changes.

### 3.1. Snapshot Isolation

A query opening a table at a specific snapshot reads a consistent set of files for that snapshot. If a writer commits a new snapshot while a query is running, the running query does not mix old files with newly committed files.

Queries starting after the commit see the new snapshot. This underpins table-level snapshot isolation.

Do not mistake this for application-level exactly-once guarantees. If a producer retries after a timeout, applications still need idempotency keys or deduplication to avoid writing the same business event twice.

### 3.2. Commit Conflicts

Conflicts can occur when:

- Two writers modify the same partition or overlapping file sets simultaneously.
- A compaction job runs while another writer appends/updates the same data region.
- Metadata was modified by another transaction before commit.
- Catalog locking/permissions or network calls fail.

How to handle them:

- Use bounded retries with backoff.
- Refresh latest metadata before recomputing commits.
- Avoid uncoordinated writers hammering the same hot table simultaneously.
- Partition or batch workloads along clean boundaries where reasonable.
- Separate maintenance jobs from peak ingestion windows if conflicts arise.
- Monitor commit failures and retry counts instead of checking only job exit codes.

## 4. AWS Glue Data Catalog and Catalog Integration

AWS Glue Data Catalog is the standard catalog for registering Iceberg tables on AWS. The Catalog stores database/table metadata and the current metadata file location, while Amazon S3 holds the actual data and metadata files.

Query and ETL engines can share the same catalog to access a table:

- AWS Glue Spark reads and writes Iceberg via `GlueCatalog`.
- Amazon EMR Spark supports Iceberg per EMR release.
- Amazon Athena supports reading, time travel, DML, and DDL within supported scope.
- Amazon Redshift can query Iceberg tables cataloged in AWS Glue.
- Lake Formation governs access permissions for integrated engines.

### 4.1. Catalog as the Table Authority

A table named `analytics.orders` resolves via catalog/database/table. The Catalog returns the metadata location; the Iceberg reader loads the metadata JSON and walks the snapshot/manifest tree.

If an engine writes Parquet files directly into the S3 prefix without committing Iceberg metadata, those files do not automatically become part of the table. Likewise, manually editing a Glue table location is not how Iceberg transaction states are updated.

### 4.2. Optimistic Locking and Glue Versions

AWS Glue 4.0+ uses optimistic locking by default for the Iceberg Glue Catalog. AWS Glue 3.0 with Iceberg 0.13.1 requires configuring a DynamoDB lock manager to ensure atomic transactions per AWS guidance.

Never configure incompatible locking mechanisms on the same table. When a table is shared across multiple engines, verify all engines use compatible catalog/commit behaviors.

### 4.3. Cross-Engine Compatibility Is Mandatory

Not every engine supports the same Iceberg format version or full feature set.

At the time of the AWS documentation referenced in this lesson:

| Engine/Runtime | Key Support Notes |
|---|---|
| AWS Glue 6.0 | Supports Iceberg format v2 and v3; creates v2 tables by default. |
| AWS Glue 5.1 | Bundles Iceberg 1.10.0. |
| AWS Glue 5.0 | Bundles Iceberg 1.7.1. |
| AWS Glue 4.0 | Bundles Iceberg 1.0.0. |
| AWS Glue 3.0 | Bundles Iceberg 0.13.1; requires configuring DynamoDB lock manager. |
| Amazon Athena engine version 3 | Supports Iceberg 1.4.2 and creates/operates format v2 tables only. |
| Amazon EMR | Native Iceberg support from EMR 6.5.0; specific version and features depend on release/framework. |
| Amazon Redshift | Can query Iceberg v1/v2 via Glue Data Catalog; check limits by Region and engine. |

If a table is read by both Athena and Glue 6.0, stay on format v2 unless every downstream engine is confirmed to support v3. Upgrading to Iceberg v3 is a one-way change; you cannot downgrade a v3 table back to v2.

## 5. Creating Iceberg Tables with Amazon Athena

Athena engine version 3 can create Iceberg tables in AWS Glue Data Catalog with data stored in S3.

Example creating the `orders` table:

~~~sql
CREATE TABLE analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_ts TIMESTAMP,
    order_date DATE,
    amount DECIMAL(12, 2),
    status STRING
)
PARTITIONED BY (order_date, bucket(32, customer_id))
LOCATION 's3://company-data-lake/warehouse/orders/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'PARQUET'
);
~~~

The example above uses business date and customer bucketing as partition fields. The partition evolution section below also illustrates deriving day transforms directly from timestamps. Choose transforms based on query patterns, cardinality, and data distribution; do not copy this exact partitioning strategy blindly for every table.

### 5.1. Creating Tables from Existing Data

You can use CTAS to create an Iceberg table from a query:

~~~sql
CREATE TABLE analytics.orders_iceberg
WITH (
    table_type = 'ICEBERG',
    format = 'PARQUET',
    location = 's3://company-data-lake/warehouse/orders_iceberg/'
) AS
SELECT
    order_id,
    customer_id,
    order_ts,
    order_date,
    amount,
    status
FROM staging.orders;
~~~

An Iceberg table's location must be dedicated solely to that table. Before running CTAS, ensure the target S3 prefix contains no data from other tables or non-Iceberg objects.

## 6. Reading and Writing Iceberg with AWS Glue Spark

AWS Glue 3.0+ supports the Iceberg framework. For Spark Glue jobs, enable Iceberg and configure the Glue Catalog.

Typical configuration parameters:

~~~text
--datalake-formats iceberg

--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions

--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog

--conf spark.sql.catalog.glue_catalog.warehouse=s3://company-data-lake/warehouse/

--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog

--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO
~~~

The catalog name `glue_catalog` is a Spark session alias. `warehouse` is the root location; `GlueCatalog` connects to AWS Glue Data Catalog; `S3FileIO` reads/writes objects on S3.

### 6.1. Creating Tables and Appending Data

PySpark example:

~~~python
# Create a new Iceberg table in the Glue Data Catalog.
df.writeTo("glue_catalog.analytics.orders") \
    .tableProperty("format-version", "2") \
    .create()

# Append a new batch to the existing table.
next_batch.writeTo("glue_catalog.analytics.orders") \
    .append()
~~~

Tables can also be created via SQL:

~~~sql
CREATE TABLE glue_catalog.analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_ts TIMESTAMP,
    amount DECIMAL(12, 2),
    status STRING
)
USING iceberg
TBLPROPERTIES ('format-version' = '2');
~~~

In multi-engine environments, pick the format version matching the lowest-capability engine that must read or write the table. The configuration above illustrates format v2 for compatibility with Athena engine 3.

### 6.2. Reading Tables from Glue Catalog

~~~python
orders_df = spark.read \
    .format("iceberg") \
    .load("glue_catalog.analytics.orders")

orders_df.createOrReplaceTempView("orders")
spark.sql("""
    SELECT status, COUNT(*) AS total_orders
    FROM orders
    GROUP BY status
""").show()
~~~

If the table is registered with Lake Formation, configure the Glue job and IAM/Lake Formation permissions according to guidance for your runtime. Glue 5.0+ has dedicated fine-grained access control guidance; Glue 4.0 requires its corresponding Lake Formation configurations.

## 7. Iceberg Format v1, v2, and v3

The Iceberg format version governs metadata structures and capabilities available to writers and readers.

| Version | Highlights | When to Consider |
|---|---|---|
| v1 | Manages immutable data files and baseline snapshot metadata. | Legacy systems or engines supporting only v1. |
| v2 | Adds row-level delete files, sequence numbers, and Iceberg-native updates/deletes. | Common choice when DML and Athena interoperability are needed. |
| v3 | Adds capabilities such as `VARIANT`, nanosecond timestamp precision, and geospatial types per runtime support. | When all writers and readers support v3 and clear requirements exist. |

### 7.1. Choosing Version by Lowest-Common-Denominator Engine

A lakehouse might have Glue Spark writing tables, Athena running ad-hoc queries, and Redshift handling warehouse analytics. If one engine supports only v2, upgrading the table to v3 can break reads in that engine.

Before upgrading versions, build a compatibility matrix covering:

- Runtime and Iceberg library versions.
- Catalog implementation.
- File formats and compression.
- Delete file semantics.
- Schema and data type support.
- Time travel and metadata table support.
- Maintenance procedures and optimizers.

### 7.2. Upgrading v2 to v3

AWS Glue 6.0 supports creating v3 tables via table property `format-version=3`. Upgrading a v2 table to v3 is a metadata-only operation that does not rewrite data files, but it is a one-way change.

~~~sql
ALTER TABLE glue_catalog.analytics.orders
SET TBLPROPERTIES ('format-version' = '3');
~~~

Perform this only after verifying readers/writers, query engines, backup/rollback strategies, and test environments. If Athena remains a consumer, stay on v2 per current compatibility.

## 8. Schema Evolution

Schema evolution enables modifying table structures via metadata without rewriting all data files.

Commonly supported changes:

- Add: add columns.
- Drop: remove columns.
- Rename: rename columns.
- Reorder: change display column order.
- Type promotion: widen compatible types, such as `integer` to `bigint`, `float` to `double`, or increasing `decimal` precision within supported limits.

Examples:

~~~sql
ALTER TABLE analytics.orders
ADD COLUMNS (sales_channel STRING);

ALTER TABLE analytics.orders
RENAME COLUMN status TO order_status;

ALTER TABLE analytics.orders
DROP COLUMN sales_channel;
~~~

### 8.1. Field IDs Matter More Than Column Position

Iceberg uses stable field IDs to identify columns. When a column is renamed, its field ID stays unchanged, allowing readers to interpret older files under the new schema.

Never assume the third column in every data file is always `amount`. Some files were written under older schemas and others under newer schemas. Iceberg uses field IDs and schema metadata to map columns accurately.

### 8.2. Type Promotion and Compatibility

Not every type change is safe. For instance, narrowing `bigint` to `int` can lose data; converting `string` to `timestamp` requires parsing and checking invalid values.

Before changing types:

1. Inspect real data and null/invalid values.
2. Confirm readers and writers support the promotion.
3. Verify downstream schema contracts.
4. Test queries across both older and newer data.
5. Document the schema change in data contracts or catalog documentation.

## 9. Partition Evolution and Hidden Partitioning

Partitioning helps query engines skip irrelevant files. However, a partitioning strategy can become suboptimal as workloads evolve.

For example, a table might initially partition by day, yet later grow large with queries filtering mostly by customer. Iceberg lets you adopt a new partition spec without forcing a rewrite of all older files.

### 9.1. Partition Transforms

Common transforms:

| Transform | Example | Meaning |
|---|---|---|
| identity | `category` | Uses the column value directly. |
| year | `year(order_ts)` | Groups by year. |
| month | `month(order_ts)` | Groups by month. |
| day | `day(order_ts)` | Groups by day. |
| hour | `hour(event_ts)` | Groups by hour. |
| bucket | `bucket(32, customer_id)` | Hashes into a fixed number of buckets. |
| truncate | `truncate(10, postal_code)` | Truncates values to a fixed width. |

Example partition spec:

~~~sql
CREATE TABLE analytics.events (
    event_id STRING,
    event_ts TIMESTAMP,
    customer_id STRING,
    event_type STRING,
    payload STRING
)
PARTITIONED BY (day(event_ts), bucket(32, customer_id))
LOCATION 's3://company-data-lake/warehouse/events/'
TBLPROPERTIES ('table_type' = 'ICEBERG');
~~~

### 9.2. Evolving Partition Specs Without Rewriting Old Files

When a partition spec changes:

- Older files keep their previous partition spec.
- New files are written under the new spec.
- Manifests record each file's spec ID and partition tuple.
- The query planner understands each spec and generates matching predicates to prune files.

Thus, a table can hold files written under multiple partition specs. Never manually rename or move S3 folders to simulate partition evolution.

Athena supports hidden partitioning when creating tables, though Hive-style partition DDL commands such as `SHOW PARTITIONS` and `ALTER TABLE ADD/DROP PARTITION` do not apply to Iceberg. Modify partition specs using supported engines and syntax for your version.

### 9.3. Selecting a Partition Strategy

Avoid overly fine partitioning that yields millions of tiny partitions/files. Avoid partitioning on ultra-high-cardinality columns like transaction ID. Choose partitions based on:

- Predicates frequently appearing in queries.
- Data volume and distribution.
- Ingestion velocity and update frequency.
- Skew levels.
- Compaction feasibility.
- Number of files and manifests queries must scan.

Partitioning does not replace sort order or clustering. For multi-dimensional filter queries, sort/Z-order compaction may be better than adding extra partition levels.

## 10. Time Travel and Version Travel

Each snapshot represents a table state. While a snapshot is retained, query engines can read data as of a prior timestamp or snapshot ID.

Time travel is useful for:

- Investigating unexpected data changes.
- Comparing figures before and after a batch.
- Recovering logically after a buggy pipeline write.
- Reproducing historical report outputs.
- Auditing and lineage checks.

Athena time travel example by timestamp:

~~~sql
SELECT *
FROM analytics.orders
FOR TIMESTAMP AS OF TIMESTAMP '2026-11-20 08:00:00';
~~~

Version travel example by snapshot ID:

~~~sql
SELECT *
FROM analytics.orders
FOR VERSION AS OF 1234567890123456789;
~~~

The snapshot ID above is illustrative. Retrieve actual IDs from the `$snapshots` metadata table.

### 10.1. Inspecting Snapshot History

~~~sql
SELECT
    committed_at,
    snapshot_id,
    parent_id,
    operation,
    manifest_list
FROM "analytics"."orders$snapshots";
~~~

History can also be queried:

~~~sql
SELECT *
FROM "analytics"."orders$history"
ORDER BY made_current_at DESC;
~~~

Metadata tables such as `$files`, `$manifests`, `$partitions`, `$snapshots`, `$history`, and `$refs` help inspect table structure. Lake Formation row/cell filters may restrict querying certain metadata tables; verify access policies if you encounter `AccessDeniedException`.

### 10.2. Time Travel Is Not Indefinite Backup

Time travel works only while snapshots and their required data files remain retained. Once a snapshot expires and files are no longer referenced by any retained snapshot, those files can be deleted.

When long-term auditing is needed, set appropriate snapshot retention or export datasets/evidence to a separate archive store. Never promise recovery from a snapshot that has already expired.

## 11. Insert, Update, Delete, and Merge

Iceberg v2 supports row-level changes using delete files. Writers can produce position deletes or equality deletes depending on the engine and write mode.

Supported engines can execute:

~~~sql
INSERT INTO analytics.orders
VALUES ('O-9001', 'C-1001', TIMESTAMP '2026-11-20 09:00:00', DATE '2026-11-20', 125.50, 'NEW');

UPDATE analytics.orders
SET status = 'SHIPPED'
WHERE order_id = 'O-9001';

DELETE FROM analytics.orders
WHERE order_id = 'O-9001';
~~~

`MERGE INTO` example for upserts:

~~~sql
MERGE INTO analytics.customers target
USING staging.customer_changes source
ON target.customer_id = source.customer_id
WHEN MATCHED THEN
    UPDATE SET
        email = source.email,
        updated_at = source.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, email, updated_at)
    VALUES (source.customer_id, source.email, source.updated_at);
~~~

Syntax and DML support depend on query engine and version. Athena engine 3 supports `INSERT`, `UPDATE`, `DELETE`, and `MERGE` on Iceberg v2; Athena's `UPDATE`/`DELETE`/`MERGE` operations use merge-on-read with positional deletes and do not switch to copy-on-write solely from table properties.

### 11.1. Merge-on-Read vs. Copy-on-Write

| Strategy | How It Works | Trade-off |
|---|---|---|
| Copy-on-write | Rewrites data files containing modified rows. | Simpler reads, though writes can incur high I/O. |
| Merge-on-read | Writes delete files and new data files; readers reconcile at query time. | Faster writes in many cases, though queries pay extra cost merging delete files. |

After many merge-on-read updates/deletes, run compaction to fold delete files into data files and keep read costs low.

## 12. Compaction and File Layout Optimization

Streaming or micro-batch pipelines can generate many small files. Millions of small files inflate S3 requests, metadata size, planning overhead, and query latency.

Compaction reads existing files, rewrites them into fewer larger files, and commits a new snapshot. Prior snapshots remain per the retention policy, so older files may not be deleted immediately.

Strategies:

- **Binpack:** merges small files into larger files; the most common baseline strategy.
- **Sort:** orders data by frequently filtered columns to improve data skipping.
- **Z-order:** clusters data across multiple dimensions to speed up multi-column filters.

Do not enforce a single rigid target file size for every workload. The right size depends on engine, query concurrency, object size, parallelism, file groups, memory, and data volume.

### 12.1. Compaction with Athena

Athena engine 3 supports `OPTIMIZE` for Iceberg:

~~~sql
OPTIMIZE analytics.orders
REWRITE DATA USING BIN_PACK;
~~~

You can scope compaction with partition predicates:

~~~sql
OPTIMIZE analytics.orders
REWRITE DATA USING BIN_PACK
WHERE order_date = DATE '2026-11-20';
~~~

In Athena, `OPTIMIZE` predicates support only partition columns. Compaction cost depends on data scanned and rewritten. Athena fits straightforward bin-pack compaction; for advanced sort/Z-order compaction, consider Spark on AWS Glue or EMR.

### 12.2. Compaction with Spark

Spark can invoke Iceberg system procedures:

~~~sql
CALL glue_catalog.system.rewrite_data_files(
    table => 'analytics.orders',
    strategy => 'binpack'
);
~~~

You can configure target sizes or sort strategies to fit query patterns. For large tables, bound file groups and concurrency to prevent driver/executor memory pressure.

Avoid running compaction concurrently with uncoordinated writers on the same partitions. For continuously ingested tables, compact colder partitions or enable partial progress to reduce conflict scope.

## 13. Snapshot Retention and Expiring Snapshots

Snapshot retention controls how many snapshots and how much history are preserved. Without snapshot expiration, old metadata and data files accumulate over time, increasing S3 storage and metadata operation costs.

Spark procedure example:

~~~sql
CALL glue_catalog.system.expire_snapshots(
    table => 'analytics.orders',
    older_than => TIMESTAMP '2026-11-13 00:00:00',
    retain_last => 10
);
~~~

Athena example:

~~~sql
VACUUM analytics.orders;
~~~

Athena's `VACUUM` performs snapshot expiration and orphan file removal according to table property configurations. Once a snapshot expires, you can no longer time travel to that snapshot.

### 13.1. Defining Business-Aligned Retention Policies

A policy should weigh:

- Audit and compliance requirements.
- How long it takes to detect bad data.
- How far back pipelines may need to backfill.
- Post-release rollback windows.
- Storage costs and query history needs.
- Protected branches, tags, or snapshot references.

For instance, raw ingestion tables may retain longer history than aggregate tables regenerable from raw. Financial reporting tables may require retention and archiving policies driven by regulatory mandates.

Never set a 1–2 day retention solely to trim S3 bills if your team often needs several days to detect data anomalies.

## 14. Orphan Files and Safe Cleanup

Orphan files are objects inside the table location that are no longer referenced by any Iceberg metadata. They can arise when:

- A job writes files successfully, then fails before committing.
- A compaction or rewrite job is aborted mid-run.
- Pipeline retries leave uncommitted temporary files.
- Snapshot expiration removes metadata references without deleting associated files.
- Operators manually delete or modify data outside proper procedures.

Orphan file cleanup reclaims storage. However, running cleanup too aggressively can delete files an in-flight writer is about to commit or files belonging to another table sharing the same location.

### 14.1. Safety Rules

- Give every Iceberg table its own dedicated S3 location—never share prefixes with other tables or data sources.
- Set orphan cleanup retention longer than the maximum elapsed time from file creation to commit completion, including retries and delays.
- Never apply S3 Lifecycle expiration rules to delete Iceberg data/metadata files by object age.
- Inspect optimizer logs and location scope before enabling cleanup.
- Test on non-production tables and verify snapshots/queries after cleanup.
- Never delete metadata JSONs, manifests, or data files via ad-hoc prefix-cleaning scripts.

The AWS Glue orphan file deletion optimizer retains orphan files for 3 days by default; this is configurable down to a minimum of 1 day. The optimizer deletes only files meeting the age threshold and created after the optimizer was enabled. If a table location contains data from another table, the optimizer could misidentify files and delete data belonging elsewhere.

## 15. AWS Glue Table Optimizers

AWS Glue Data Catalog can manage three optimizers for Iceberg tables:

| Optimizer | Purpose | Outcome |
|---|---|---|
| Compaction | Merges small files, rewrites layout, optionally applies sort/Z-order per configuration | Reduces file count, metadata overhead, and query scan |
| Snapshot retention | Expires older snapshots by age/count policies | Reduces storage and metadata history |
| Orphan file deletion | Deletes files no longer referenced by metadata | Reclaims storage occupied by orphan files |

Optimizers can be enabled at the table level via the Glue console, CLI, or API; catalog-level optimization applies defaults to new or updated tables. Table-level settings can override catalog defaults.

### 15.1. Permissions for Optimizers

Glue optimizers assume a designated IAM role. The role requires permissions to access S3, Glue Data Catalog, CloudWatch Logs/metrics, and KMS when data uses customer managed keys.

Required permissions vary by optimizer. Compaction and snapshot retention need read/write on data and metadata; orphan deletion needs list/delete permissions within scope. Follow least privilege, scoping policies strictly to the target catalog/database/table and S3 prefix.

If buckets require VPC endpoints or specific network paths, configure appropriate Glue network connections. For Lake Formation-registered tables, both the role and Lake Formation grants must satisfy optimizer requirements.

### 15.2. Monitoring Optimizer Runs

Check:

- Optimizer enabled/disabled status.
- Last run status and timestamp.
- Counts of rewritten/deleted files.
- IAM, KMS, S3, or Glue errors.
- CloudWatch logs and metrics.
- Impact on query latency and storage footprint.

Do not assume an enabled optimizer means maintenance is succeeding. Review run histories and actual outcomes.

## 16. Integrating AWS Engines

### 16.1. AWS Glue

Glue Spark fits ETL, streaming/micro-batches, merges, schema/partition evolution, and Spark-procedure maintenance. Glue Data Catalog serves as the catalog entry point.

### 16.2. Amazon EMR

EMR provides Spark, Flink, Hive, and other processing frameworks. Iceberg is natively supported starting in EMR 6.5.0; specific features and versions depend on EMR release and framework. Use EMR when needing cluster control, pinned library versions, custom Spark tuning, or massive scale.

### 16.3. Amazon Athena

Athena fits serverless SQL querying, ad-hoc analysis, v2 DML, time travel, metadata tables, `OPTIMIZE`, and `VACUUM`. Athena carries specific format/version bounds; current docs cite Iceberg 1.4.2 and v2. Verify support before upgrading table versions or adopting newer types.

### 16.4. Amazon Redshift

Redshift can query Iceberg tables cataloged in AWS Glue via external schemas, join them with local Redshift tables, and use Iceberg metadata statistics to optimize queries. Redshift supports querying Iceberg v1/v2, read-only time travel, and certain transaction semantics per service guidance.

Example creating an external schema:

~~~sql
CREATE EXTERNAL SCHEMA lake_analytics
FROM DATA CATALOG
DATABASE 'analytics'
IAM_ROLE 'arn:aws:iam::111122223333:role/redshift-lake-role';
~~~

Then query:

~~~sql
SELECT customer_id, SUM(amount)
FROM lake_analytics.orders
GROUP BY customer_id;
~~~

For strong query performance, generate column statistics in Glue for Iceberg tables per Redshift guidance. Check Region availability and Lake Formation permissions for your environment.

## 17. Lake Formation, IAM, and Data Protection

Iceberg metadata contains column names, partition values, snapshot history, file paths, and statistics. This can expose sensitive details about your data systems.

Govern:

- IAM roles for Glue, EMR, Athena, Redshift, and application writers.
- Lake Formation grants at database/table/column/row levels where appropriate.
- S3 bucket policies and access points.
- KMS key policies and encryption.
- CloudTrail auditing for catalog, permission, and resource changes.
- Access to metadata tables such as `$files`, `$snapshots`, and `$manifests`.
- Permissions granted to optimizer roles.

Lake Formation fine-grained access control can apply across supported engines. However, not every Iceberg operation is governed identically by Lake Formation. For instance, Athena does not support DDL on Iceberg tables registered with Lake Formation under current limitations; operations such as `VACUUM`, `MERGE`, `UPDATE`, and `OPTIMIZE` also carry specific permission constraints.

Never share a single IAM role with full read/write across the entire data lake for every job. Separate roles by table domain and operation.

## 18. Protecting S3 Locations and Data Lifecycles

S3 stores the files, while Iceberg tracks the relationship between files and snapshots. Therefore, S3 operations must respect table metadata.

Best practices:

- Assign each table an isolated location.
- Enforce encryption at rest via SSE-S3 or SSE-KMS per policy.
- Keep metadata and data files in storage classes supported for live engine access.
- Avoid deleting objects directly outside Iceberg procedures.
- Never use S3 Lifecycle expiration to delete data/metadata files by age.
- Restrict `DeleteObject` and `DeleteObjectVersion` permissions.
- Enable S3 Versioning when object protection demands it, without mistaking Versioning for an Iceberg snapshot/backup substitute.
- Design archives and backups with awareness of snapshots, metadata, and restore workflows.

If using storage classes such as Glacier, check engine query and restore support. Athena has restrictions with Glacier objects in Iceberg tables; never transition files referenced by active snapshots into tiers that block query reads.

## 19. Monitoring and Table Operations

An Iceberg table requires tracking data quality, metadata health, query behavior, and maintenance together.

| Metric | Meaning | Actionable Signal |
|---|---|---|
| Snapshot count/age | Number of snapshots and age of oldest snapshot | Metadata/storage bloat or overly short retention |
| Data file count | Number of files referenced by active snapshot | Rapid file growth, slower query planning |
| Average file size | Mean data file size | Excessive small files or oversized files |
| Manifest count/size | Metadata overhead | Rising query planning and metadata scan time |
| Delete file count | Count of position/equality delete files | Slowing merge-on-read queries |
| Orphan file bytes/count | Storage unreferenced by metadata | Cleanup backlog or failing jobs |
| Commit conflicts/retries | Writer concurrency contention | High job retries or rising write latency |
| Query bytes scanned | Data scanned per query | Suboptimal partition pruning or file stats |
| Optimizer run status | Compaction/retention/orphan cleanup results | Failing maintenance or missing role permissions |
| Data quality metrics | Nulls, duplicates, freshness, schema mismatches | Broken ingestion or producer contract drift |

Metadata tables can be queried via Athena:

~~~sql
SELECT COUNT(*) AS data_files
FROM "analytics"."orders$files";

SELECT
    committed_at,
    snapshot_id,
    operation
FROM "analytics"."orders$snapshots"
ORDER BY committed_at DESC;
~~~

For tables governed by Lake Formation filters, metadata table queries may be restricted. Check permissions before assuming metadata is missing.

## 20. Practical Scenario: E-Commerce Orders Data Lake

An e-commerce company stores order events from Kinesis into S3. A Glue streaming job writes events into an Iceberg table `analytics.orders`. Athena serves analysts, Redshift serves BI, and Glue Spark runs daily enrichment.

### 20.1. Table Design

Schema includes:

- `order_id`: order identifier.
- `customer_id`: customer identifier.
- `order_ts`: order creation timestamp.
- `order_date`: business date.
- `amount`: order amount.
- `status`: current status.
- `source_updated_at`: source update timestamp.

Choose Iceberg v2 since Athena is a primary reader. Partition by `day(order_ts)` and `bucket(32, customer_id)` after analyzing query workloads.

### 20.2. Ingestion

Glue Spark writes micro-batches to Iceberg. The job uses idempotency keys to prevent duplicates and records `source_updated_at`/event version to resolve late updates.

Each append/merge commits a new snapshot. Analysts query the current snapshot; data engineers can use time travel to compare states before and after a batch.

### 20.3. Querying and Governance

- Athena uses SQL for queries, time travel, and supported DML.
- Redshift queries the same table via a Glue Data Catalog external schema.
- Lake Formation governs permissions by database/table/column or row-level filters per use case.
- Separate IAM roles exist for writers, readers, and optimizers.

### 20.4. Maintenance

- Periodic compaction reduces small files.
- Snapshot retention keeps enough history for auditing and backfills.
- Orphan cleanup runs with a safety window exceeding maximum commit/retry duration.
- Glue optimizer logs and CloudWatch metrics are reviewed regularly.
- S3 Lifecycle does not expire objects inside the Iceberg table location.

### 20.5. Handling Schema Changes

When adding `sales_channel`, use schema evolution rather than rewriting the entire table. Update the data contract and downstream BI. Queries can still read files written before the column existed; the new column returns null on older files depending on schema semantics.

## 21. Common Mistakes

1. **Confusing Iceberg with Parquet.** Parquet is a file format; Iceberg manages table metadata and transactions.
2. **Writing files directly to S3 expecting Iceberg to pick them up.** Files must enter metadata via an Iceberg commit.
3. **Treating S3 folder listings as truth.** Iceberg metadata defines which files belong to a snapshot.
4. **Deleting data files via the S3 console.** Can leave the active snapshot missing referenced files.
5. **Upgrading to v3 while Athena still reads the table.** Athena currently supports only Iceberg v2.
6. **Assuming Glue and Athena share identical feature sets.** Runtimes and Iceberg library versions differ.
7. **Ignoring commit conflicts.** Concurrent writers can retry excessively or fail.
8. **Over-partitioning.** Creates too many tiny files and metadata bloat.
9. **Skipping compaction after streaming ingestion.** Small files slow down query planning and scans.
10. **Expiring snapshots too early.** Loses needed time travel and rollback capability.
11. **Running orphan cleanup too aggressively.** Can delete uncommitted files from active writers.
12. **Using S3 Lifecycle age-based expiration.** Can delete data/metadata still referenced by active snapshots.
13. **Assuming snapshot retention and orphan cleanup are the same.** One expires snapshots; the other deletes unreferenced files.
14. **Ignoring delete files.** Merge-on-read queries degrade without periodic compaction.
15. **Assuming partition evolution rewrites old files.** Old files retain old specs; Iceberg's planner handles mixed specs.
16. **Neglecting cross-engine compatibility.** Readers may fail on newer format versions or types.
17. **Overlooking Lake Formation metadata restrictions.** Querying metadata tables can trigger `AccessDenied`.
18. **Treating S3 Versioning as an Iceberg backup.** Versioning does not restore catalog pointers or table transaction state.

## 22. Self-Check Questions

**1. Is Apache Iceberg a file format or a table format?**

A table format. It manages file sets, schemas, partitions, snapshots, and commits; underlying data files can still be Parquet, ORC, or Avro.

**2. Does the Data Catalog store table data or metadata pointers?**

The Catalog registers tables and points to current metadata locations; actual data and metadata files live in S3.

**3. How does a manifest list differ from a manifest file?**

A manifest list enumerates manifests belonging to a snapshot; a manifest lists data/delete files along with partition values and column metrics.

**4. What does a snapshot represent?**

The table's state at a point in time, defining the exact set of data files comprising the table then.

**5. How do Iceberg commits handle concurrent writers?**

Through optimistic concurrency and atomic metadata commits; conflicting writers must refresh metadata, revalidate, and retry per application logic.

**6. Why do field IDs matter when renaming columns?**

Field IDs uniquely identify columns across schema evolution, avoiding reliance on physical column positions inside files.

**7. What benefit does hidden partitioning provide?**

Queries filter on business columns; Iceberg applies partition transforms and metadata to prune files without users managing partition folders.

**8. Does partition evolution rewrite all historical files?**

No. Existing files retain the partition spec used when written; new files adopt the updated spec.

**9. What does time travel depend on?**

Retained snapshots and their required data files; expired snapshots can no longer be queried via time travel.

**10. What major capability did Iceberg v2 introduce?**

Row-level deletes via delete files, sequence numbers, and update/delete support in compatible engines.

**11. Why is compaction needed?**

To reduce small files, fold in delete files, and improve query planning and read performance.

**12. How does snapshot expiration differ from orphan file deletion?**

Snapshot expiration removes old snapshots from history and can delete files referenced only by them; orphan cleanup removes files unreferenced by any active metadata.

**13. Why must orphan cleanup retention exceed commit delays?**

Files already written to S3 before commit finishes are not yet referenced in metadata; premature cleanup can delete files before the writer commits.

**14. Does Athena support Iceberg v3?**

Per the documentation referenced in this lesson, Athena engine 3 supports Iceberg 1.4.2 and operates v2 tables; verify compatibility before adopting v3.

**15. Does Lake Formation govern every Iceberg operation in Athena?**

No. Read permissions and fine-grained access can be governed, yet certain DDL/maintenance operations carry specific limitations.

**16. When should you use Glue Spark or EMR for maintenance?**

When needing sort/Z-order compaction, large-scale file rewrites, fine-grained Spark resource tuning, or Iceberg procedures more flexible than Athena `OPTIMIZE`.

## 23. Production Checklist for Iceberg Tables

- [ ] Table has an owner, business purpose, data contract, and isolated S3 location.
- [ ] Unified catalog chosen, preferring Glue Data Catalog for compatible AWS engines.
- [ ] Iceberg format version chosen to match the lowest-capability reader/writer.
- [ ] Runtime/engine support verified before enabling v3 or newer types.
- [ ] Separate IAM/Lake Formation permissions exist for readers, writers, and optimizers.
- [ ] S3/KMS encryption and bucket policies satisfy data requirements.
- [ ] No S3 Lifecycle expiration rules delete data/metadata inside the table location.
- [ ] Schema evolution is governed via field IDs and data contracts.
- [ ] Partition transforms align with query patterns and data distribution.
- [ ] Writers implement idempotency, retry/backoff, and commit conflict handling.
- [ ] Compaction strategy aligns with file count/size and query performance.
- [ ] Snapshot retention satisfies auditing, rollback, and backfill needs.
- [ ] Orphan cleanup retention exceeds maximum commit/retry duration.
- [ ] Table location does not overlap with any other table or data source.
- [ ] Monitoring tracks snapshot counts, file counts, delete files, commit retries, and query scans.
- [ ] Tested time travel, rollback, schema changes, and partition evolution.
- [ ] Tested concurrent writers and compaction conflicts.
- [ ] Runbooks exist for `AccessDenied`, commit failures, and missing files.
- [ ] Backup/restore workflows and recoverability have been tested.
- [ ] Periodic reviews cover cost, storage, query performance, and data quality.

## References

- [Apache Iceberg specification](https://iceberg.apache.org/spec/)
- [Apache Iceberg terminology](https://iceberg.apache.org/terms/)
- [Apache Iceberg documentation](https://iceberg.apache.org/docs/latest/)
- [Using the Iceberg framework in AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
- [AWS Glue table optimizers](https://docs.aws.amazon.com/glue/latest/dg/table-optimizers.html)
- [AWS Glue table optimization prerequisites](https://docs.aws.amazon.com/glue/latest/dg/optimization-prerequisites.html)
- [AWS Glue compaction optimization](https://docs.aws.amazon.com/glue/latest/dg/compaction.html)
- [AWS Glue snapshot retention optimization](https://docs.aws.amazon.com/glue/latest/dg/snapshot-retention-management.html)
- [AWS Glue orphan file deletion](https://docs.aws.amazon.com/glue/latest/dg/orphan-file-deletion.html)
- [AWS Glue optimizer considerations and limitations](https://docs.aws.amazon.com/glue/latest/dg/optimizer-notes.html)
- [Catalog-level table optimizers](https://docs.aws.amazon.com/glue/latest/dg/catalog-level-optimizers.html)
- [Query Apache Iceberg tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg.html)
- [Create Iceberg tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html)
- [Athena Iceberg time travel and version travel](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-time-travel-and-version-travel-queries.html)
- [Update Iceberg table data in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-updating-iceberg-table-data.html)
- [Athena OPTIMIZE](https://docs.aws.amazon.com/athena/latest/ug/optimize-statement.html)
- [Athena VACUUM](https://docs.aws.amazon.com/athena/latest/ug/vacuum-statement.html)
- [Athena Iceberg schema evolution](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-evolving-table-schema.html)
- [Query Iceberg metadata tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-table-data.html)
- [Using Iceberg with Amazon EMR](https://docs.aws.amazon.com/prescriptive-guidance/latest/apache-iceberg-on-aws/iceberg-emr.html)
- [Self-managed Iceberg maintenance on AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/apache-iceberg-on-aws/self-managed-maintenance.html)
- [Query Apache Iceberg tables with Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/querying-iceberg.html)
- [Referencing Iceberg tables in Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/referencing-iceberg-tables.html)
- [AWS Lake Formation table optimization](https://docs.aws.amazon.com/lake-formation/latest/dg/data-compaction.html)
