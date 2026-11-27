# Amazon Redshift and Data Warehouse Modeling

Amazon Redshift is a managed analytical data warehouse service on AWS. Redshift is engineered for SQL queries over large datasets using a Massively Parallel Processing (MPP) architecture, columnar storage, and workload-aware query optimization. It is well suited for BI reporting, historical analytics, dashboards, data marts, and analytical workloads that combine data across multiple systems.

To use Redshift effectively, you need to understand two layers simultaneously:

- **Data warehouse modeling:** what data is stored, the grain of fact tables, dimensions, change history, data quality, and lineage.
- **Execution architecture:** how data is distributed, how many blocks queries read, whether joins must move data across nodes, and how workloads are queued and provisioned compute.

A good data warehouse does not merely run queries fast. It must deliver consistent metrics, enforce access controls, support recovery, scale with demand, and have predictable costs.

This lesson belongs to the **Analytics and Search** chapter in the CLOUD_PROVIDERS_AWS module. The module helps learners explore the AWS ecosystem from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless—building the ability to select services and design and deploy secure, observable, recoverable, and cost-controlled applications.

## Learning Objectives

After this lesson, you will be able to:

- Explain Amazon Redshift's role in data analytics architectures and distinguish a data warehouse from an OLTP database.
- Describe MPP architecture, leader nodes, compute nodes, slices, columnar storage, and Redshift Managed Storage.
- Choose between Redshift Provisioned and Redshift Serverless based on workload, control requirements, and cost model.
- Design star schemas, fact tables, dimensions, surrogate keys, and slowly changing dimensions.
- Choose distribution styles, sort keys, compression, and data types to reduce data movement and block scans.
- Load data efficiently using S3, IAM roles, `COPY`, staging tables, and `MERGE`.
- Integrate Redshift with S3, AWS Glue Data Catalog, Redshift Spectrum, streaming ingestion, federated queries, and zero-ETL integrations.
- Manage workloads, concurrency, materialized views, and SQL optimization.
- Protect data using IAM, database roles, encryption, network isolation, row-level security, and audit logging.
- Establish backups, monitoring, cost guardrails, and data warehouse operational workflows.

## 1. What Problems Does a Data Warehouse Solve?

### 1.1. OLTP and OLAP

Transactional databases and data warehouses serve two different access patterns.

| Characteristic | OLTP | OLAP / Data Warehouse |
|---|---|---|
| Goal | Record business transactions | Analyze and aggregate data |
| Queries | Short, keyed lookups | Scans many rows/columns, joins, and aggregations |
| Data writes | Many small, continuous transactions | Batch, micro-batch, CDC, or streams |
| Access pattern | Row-level `INSERT`/`UPDATE`/`DELETE` | `SELECT`, `GROUP BY`, `JOIN`, window functions |
| Modeling | Typically normalized to reduce redundancy | Typically dimensional/star schema or analytical models |
| Optimization | Transaction latency, consistency, concurrency | Throughput, scan reduction, parallelism |
| Examples | Orders being placed, account balances | Monthly revenue, cohorts, historical inventory |

Avoid running heavy analytical queries against an OLTP database. Multi-year aggregation queries can contend for CPU, I/O, and connections with application transactions. Conversely, Redshift is not the default choice for low-latency single transactions or high-frequency single-row updates.

### 1.2. Redshift's Role in a Data Architecture

Redshift can act as a central analytical warehouse or a compute warehouse reading data from a data lake. A common architecture:

~~~mermaid
flowchart LR
    A[OLTP Applications] --> B[CDC / Zero-ETL]
    C[Event streams] --> D[Kinesis / MSK]
    E[Files and batches] --> F[Amazon S3]
    B --> G[Amazon Redshift]
    D --> G
    F --> H[Glue Data Catalog]
    H --> I[Redshift Spectrum]
    I --> G
    G --> J[BI / Dashboard]
    G --> K[Data Science / SQL]
    G --> L[Data Sharing]
~~~

Ingestion paths do not replace one another:

- Batch loads suit scheduled, high-volume datasets.
- CDC/zero-ETL suits replicating changes from operational databases.
- Streaming ingestion suits events requiring low-latency analytics.
- Spectrum suits data remaining in S3 that needs to be queried alongside warehouse data.
- Federated queries suit selective access to data still residing in operational databases.

Choose based on latency, volume, consistency, cost, and operational complexity.

## 2. Amazon Redshift Architecture

### 2.1. MPP, Leader Node, and Compute Nodes

Redshift splits query execution into steps that can run in parallel across compute resources.

- **Leader node:** accepts client connections, parses SQL, builds execution plans, coordinates compute nodes, and aggregates final results.
- **Compute nodes:** store and process data. Nodes are divided into multiple **slices**; each slice handles a portion of data and work.
- **MPP execution:** slices perform scans, filters, joins, aggregations, and sorts in parallel when the query plan allows.
- **Columnar storage:** data is stored by column, letting queries read only required columns instead of entire rows.
- **Compression:** per-column encoding shrinks storage footprint and bytes read from storage.

Adding compute nodes or compute capacity increases parallelism, but does not automatically speed up every query. A query with distribution skew, poor joins, or excessive data reads can still bottleneck.

### 2.2. Redshift Managed Storage

With the RA3 architecture, compute and storage are decoupled:

- Compute nodes provide CPU, memory, and query processing capacity.
- Redshift Managed Storage (RMS) manages durable storage that scales with data volume.
- Redshift automatically caches hot data locally and fetches data from managed storage as needed.
- Compute capacity can scale independently without coupling storage capacity to node count as in older models.

RA3 lets you size compute for performance and storage for capacity. However, RMS remains a separate cost component; growing stored data is not free just because compute node count stays unchanged.

### 2.3. Provisioned and Serverless

Redshift offers two common ways to provision warehouse compute.

| Criterion | Provisioned | Serverless |
|---|---|---|
| Management unit | Cluster | Namespace and workgroup |
| Compute | Choose node family and node count | Redshift Processing Units (RPU) |
| Scaling | Resize, elastic resize, or concurrency scaling per configuration | Automatic scaling within configured limits |
| Compute billing | Per node-hour while cluster is running | Per RPU-hour used; no compute charge when idle without running queries |
| Storage | RMS with RA3; node-local storage on some older node families | Redshift Managed Storage, billed separately per GB-month |
| Control | Greater control over capacity, maintenance, and parameter groups | Less infrastructure management, with base/max capacity and usage limits |
| Best suited for | Steady workloads needing predictable capacity and deep tuning | Variable workloads, teams avoiding cluster management, or on-demand environments |

**Provisioned** fits steady workloads requiring control over node families, maintenance windows, parameter groups, and predictable performance. With RA3, compute and RMS are billed separately. Clusters can be resized or paused when appropriate; while paused, compute charges stop, though storage, snapshots, and related resources still incur costs.

**Serverless** uses a namespace to manage database objects, users, encryption, and storage attributes; a workgroup manages compute, networking, and base capacity. A namespace can be associated with a workgroup according to service-supported designs. Base RPU sets the baseline compute level, while max capacity caps scaling. Redshift bills compute per RPU-hour on a per-second basis with a 60-second minimum charge per usage session; storage is billed separately.

Query runtime on system tables/views also counts toward compute usage. If operational dashboards continuously poll `SYS_QUERY_HISTORY` or other views, control refresh intervals and execution counts.

Do not pick Serverless merely because workloads are intermittent. Evaluate base capacity, query duration, scale-up behavior, scale-down timing, storage, and usage limits. For always-on workloads, Provisioned can be more economical depending on node reservations and utilization.

### 2.4. Serverless Namespaces and Workgroups

- A namespace groups database objects and storage/security state: databases, users, permissions, KMS keys, datashares, and recovery points.
- A workgroup groups compute resources, VPC/subnets/security groups, endpoints, and capacity settings.
- You can isolate compute workloads by environment or persona using multiple workgroups, while considering sharing a namespace if security boundaries and access controls permit.
- Workgroups support usage limits to cap RPU-hours per day/week/month; actions can alert, log to system tables, or turn off user queries.
- Max RPU capacity is a scaling ceiling; a usage limit is a time-window threshold with an enforcement action. The two mechanisms address different goals.

### 2.5. Choosing a Deployment Model

Use these questions to guide the decision:

1. Does the workload run nearly continuously or in bursts?
2. Is deep control over node family, parameter groups, and maintenance required?
3. Are concurrency levels and SLAs steady?
4. Do you need to isolate compute warehouses per user group via data sharing?
5. Can the operations team manage cluster monitoring, resizing, backups, and WLM?
6. Should budgets be forecasted by node-hour or by RPU usage?
7. Do your target Region and required features support that option?

Always verify service availability and feature parity by Region, node type, engine version, and warehouse mode before finalizing architecture.

## 3. Data Warehouse Data Modeling

### 3.1. Grain Is the Most Important Decision

**Grain** precisely defines what a single row in a fact table represents. Examples:

- One row per line item in an order.
- One row per payment attempt.
- One row per SKU inventory snapshot at a store at end of day.
- One row per website visit.

If grain is unclear, teams can double-count revenue, multiply quantities, or join at the wrong cardinality. Before creating a table, write a single sentence defining its grain and verify it against business keys.

For example, `fact_sales` has the grain "one product line item within an order", not "one order". If an order has three products, the table has three rows; total order revenue is the sum of those line items.

### 3.2. Fact Tables and Dimension Tables

**Fact tables** store analyzable events or measurements:

- Foreign keys to dimensions.
- Measures such as quantity, amount, discount, duration.
- Date/time keys or timestamps.
- Degenerate dimensions such as order number when business identifiers must stay in the fact.

**Dimension tables** describe context:

- Customer: segment, region, channel.
- Product: category, brand, product type.
- Store: store, province/city, zone.
- Date: day, week, month, quarter, year.
- Employee or campaign: owner, program.

### 3.2.1. Types of Fact Tables

- **Transaction fact:** one row per event/transaction at the defined grain, such as one line item in an order.
- **Periodic snapshot fact:** one row per entity at a fixed cadence, such as end-of-day inventory or month-end balance. Measures like balances are typically semi-additive: summable across stores, but not across multiple days.
- **Accumulating snapshot fact:** one row representing a multi-milestone lifecycle, such as an order moving through created, packed, shipped, and completed. Timestamp columns are updated as the process progresses.

Choose the fact type based on business semantics and analytical needs. Never mix multiple grains in a single table if measures would be mis-aggregated; standardize grain or build separate marts when combining is needed.

### 3.3. Star Schema and Snowflake Schema

~~~mermaid
flowchart TB
    D1[dim_customer] --> F[fact_sales]
    D2[dim_product] --> F
    D3[dim_store] --> F
    D4[dim_date] --> F
    D5[dim_channel] --> F
~~~

A star schema places the fact table at the center with dimensions connected directly; it is intuitive for BI and typically reduces join counts.

A **snowflake schema** normalizes dimensions into sub-tables, such as product → category → department. This reduces data duplication at the cost of more joins and potentially more complex BI queries. Choose based on governance, data quality, redundancy, and query patterns; no single schema fits every system.

### 3.4. Surrogate Keys and Business Keys

A business key comes from the source system, such as `customer_id`. A surrogate key is a warehouse-managed key, such as `customer_key`.

Benefits of surrogate keys:

- Decouple the warehouse from source identifier changes.
- Support storing multiple dimension versions in SCD Type 2.
- Merge multiple sources that share customer codes across different namespaces.
- Let fact tables reference a specific point-in-time dimension version.

Do not use a business key as a surrogate key when tracking historical dimension attributes. A customer who moves regions can have multiple dimension versions sharing the same business key but distinct surrogate keys.

### 3.5. Slowly Changing Dimensions

Common SCD types:

| Type | Handling | When appropriate |
|---|---|---|
| Type 0 | Keep original value | Immutable attributes or no updates needed |
| Type 1 | Overwrite old value | Error corrections, no historical tracking needed |
| Type 2 | Insert new row, close effective window on old row | Need analysis by attribute value at transaction time |
| Type 3 | Add column for previous value | Only limited single-step history needed |

SCD Type 2 example:

| customer_key | customer_id | region | valid_from | valid_to | is_current |
|---:|---|---|---|---|---|
| 101 | C-1001 | North | 2025-01-01 | 2025-09-30 | false |
| 245 | C-1001 | South | 2025-10-01 | 9999-12-31 | true |

When a customer moves regions, the warehouse closes the old version and inserts a new version. New facts reference `customer_key` 245; historical facts continue referencing `customer_key` 101, preserving context at the time of the transaction.

Handle late-arriving dimensions, duplicate CDC events, timezones, effective dates, and late-arriving transactions. Otherwise, facts may link to the wrong dimension version.

### 3.6. Primary Keys and Foreign Keys in Redshift

Redshift allows declaring primary key, unique, and foreign key constraints, but these constraints are **not enforced** as in many OLTP databases. The query optimizer may use constraint metadata to generate better execution plans. Therefore:

- Only declare constraints when your pipeline truly guarantees uniqueness and referential integrity.
- Data violating constraints can cause incorrect query results if the optimizer relies on that metadata.
- Use data quality checks for duplicate keys, orphan facts, and null keys before publishing datasets.

Example checking for orphan facts:

~~~sql
SELECT COUNT(*) AS orphan_rows
FROM fact_sales f
LEFT JOIN dim_customer d
  ON f.customer_key = d.customer_key
WHERE d.customer_key IS NULL;
~~~

## 4. Table Design and Data Distribution

### 4.1. Distribution Styles

Redshift distributes rows across compute nodes/slices. The goal is balanced workload distribution and minimal data movement during joins or aggregations.

| Distribution style | Behavior | When to consider |
|---|---|---|
| AUTO | Redshift chooses automatically and can adapt as the table grows | Recommended starting point for most new tables |
| EVEN | Round-robin distribution | No suitable join key or table rarely participates in joins |
| KEY | Distributed by values of a single column | Two large tables frequently join on the same key with uniform distribution |
| ALL | Copies the entire table to every node | Small, slowly changing dimensions needing local joins |

Key concepts:

- **Data redistribution:** the query engine must send rows across nodes to execute a join/aggregation.
- **Broadcast:** a dataset is sent to multiple nodes.
- **Skew:** certain nodes receive disproportionately more data or work, making those nodes dictate overall completion time.
- **Collocation:** rows sharing the same join key already sit on the same node/slice, minimizing data movement.

`DISTSTYLE KEY` can optimize joins, but picking a low-cardinality or skewed key creates skew. `DISTSTYLE ALL` increases storage and load/update cost because copies must be maintained on every node; avoid it for large or frequently changing dimensions.

### 4.2. Sort Keys

Sort keys define physical data ordering in storage. Redshift tracks min/max metadata per block, enabling skipping blocks outside query predicates.

- **SORTKEY AUTO:** lets automatic table optimization pick sort order based on workload.
- **Compound sort key:** works well when queries consistently filter on the leading column and subsequent columns in order.
- **Interleaved sort key:** a specialized technique for certain multi-dimensional workloads; evaluate maintenance overhead and do not choose by default for new tables.

If most queries analyze recent data, a timestamp is a natural sort key candidate. If queries consistently join or filter on a specific key, measure impact via query plans before pinning a sort key manually.

### 4.3. Automatic Table Optimization

Automatic table optimization recommends and applies distribution styles, sort keys, and certain encodings based on observed table usage. Newly created tables without explicit keys typically default to `AUTO`.

Benefits:

- Reduces initial tuning effort.
- Adapts as table size and query workloads evolve.
- Reduces risk of picking distribution/sort keys on unmeasured assumptions.

However, `AUTO` does not replace proper grain design, data types, S3 partitioning, or well-written queries. Monitor automatic changes and workload impact after optimization; tables with highly specialized workloads may still benefit from manual tuning.

### 4.4. Compression and Data Types

Redshift stores data in columnar format and uses encoding to cut storage and scan volume. When loading via `COPY`, Redshift can select appropriate compression encodings; `ENCODE AUTO` lets the service manage encodings for the table.

Guidelines:

- Use the smallest data type covering the value domain.
- Use `DECIMAL(p,s)` for monetary amounts; avoid floating-point types for financial values requiring exact decimal precision.
- Use `DATE`/`TIMESTAMP`/`TIMESTAMPTZ` matching time semantics and enforce consistent timezones.
- Avoid overly wide `VARCHAR` columns unnecessarily.
- Do not store numbers or dates as text when frequent comparisons, sorting, or calculations are needed.
- Keep only columns needed for analytics; omit large raw payloads from fact tables if they can be retrieved from the data lake.

### 4.5. Example Creating Dimension and Fact Tables

The following example uses `AUTO` so Redshift can optimize distribution and sort keys automatically:

~~~sql
CREATE TABLE dim_customer (
    customer_key BIGINT IDENTITY(1,1),
    customer_id  VARCHAR(64) NOT NULL,
    customer_name VARCHAR(256),
    region       VARCHAR(64),
    valid_from   TIMESTAMP NOT NULL,
    valid_to     TIMESTAMP NOT NULL,
    is_current   BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE fact_sales (
    sales_line_id VARCHAR(80) NOT NULL,
    order_id      VARCHAR(64) NOT NULL,
    order_ts      TIMESTAMP NOT NULL,
    customer_key  BIGINT,
    product_key   BIGINT,
    store_key     BIGINT,
    quantity      INTEGER NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

This is an illustrative skeleton. Add columns, constraints, and defaults per your data contract. If declaring PK/FKs, ensure pipelines enforce valid relationships since Redshift does not enforce them.

## 5. Loading Data into Redshift

### 5.1. Loading Methods

| Method | Best suited for | Notes |
|---|---|---|
| COPY from S3 | Large batches, CSV/JSON/Parquet/ORC files | Usually the preferred choice for bulk loads |
| Multi-row INSERT | Small datasets, controlled operations | Avoid single-row inserts in loops |
| MERGE | Upserts from staging/CDC | Requires business key definition and deduplication |
| Streaming ingestion | Kinesis Data Streams or MSK | Uses materialized views to read streams |
| Zero-ETL | Supported integration sources | Reduces custom CDC pipeline work; still requires monitoring |
| Federated query | Data still in RDS/Aurora | Queries directly; watch latency and OLTP load |

### 5.2. COPY from S3

`COPY` reads multiple files in parallel and is generally far more efficient than many small `INSERT`s. For efficient loading:

- Split data into reasonably sized files—avoid a single huge file or millions of tiny files.
- Use compressed files or columnar formats when suitable.
- Load in consistent batches and avoid concurrent jobs writing to the same table unnecessarily.
- Use a manifest when exact file lists must be specified.
- Load into a staging table before validating and merging.
- Monitor load errors and system load error tables.

Example CSV `COPY`:

~~~sql
COPY staging.sales_raw
FROM 's3://company-data-lake/warehouse/sales/batch-2026-11-20/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
CSV
IGNOREHEADER 1
TIMEFORMAT 'auto'
DATEFORMAT 'auto'
COMPUPDATE PRESET
STATUPDATE ON;
~~~

Example Parquet `COPY`:

~~~sql
COPY staging.sales_parquet
FROM 's3://company-data-lake/warehouse/sales-parquet/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
FORMAT AS PARQUET;
~~~

Notes for Parquet/ORC:

- The S3 bucket must be in the same AWS Region as the Redshift database when using `COPY` with columnar formats.
- Columnar `COPY` supports a narrower set of parameters; do not assume every CSV option applies.
- `COPY` does not automatically apply compression encoding to columnar loads the same way traditional text `COPY` does.
- Verify schema compatibility, decimal precision, timestamp semantics, and schema evolution before loading.

### 5.3. IAM Roles for COPY and UNLOAD

Never embed long-lived access/secret keys in SQL. Attach an appropriate IAM role to the cluster or workgroup and reference it in `COPY`/`UNLOAD`.

A load role typically requires minimum permissions:

- `s3:ListBucket` on the source bucket/prefix.
- `s3:GetObject` on the objects to load.
- `kms:Decrypt` if objects are encrypted with a customer managed KMS key and the role needs to decrypt them.
- `glue:GetDatabase`, `glue:GetTable`, `glue:GetPartitions` if Data Catalog access is part of the flow.
- Appropriate network/DNS/endpoint permissions when Enhanced VPC Routing is enabled.

Do not grant `s3:*` across the entire account just to run a `COPY`. Separate roles for load, unload, Spectrum, and integrations by responsibility.

### 5.4. Staging, Validation, and MERGE

A safe pipeline typically follows these steps:

1. Load the raw batch into a staging table.
2. Validate schema, row counts, nulls, duplicates, and out-of-range values.
3. Standardize timezones, business keys, and malformed records.
4. Deduplicate by source event ID or version/timestamp.
5. `MERGE` valid data into dimensions/facts.
6. Record ingestion watermarks, batch IDs, and check results.
7. Publish the batch only once the transaction succeeds.

Example `MERGE`:

~~~sql
MERGE INTO dim_customer AS target
USING staging.customer_delta AS source
ON target.customer_id = source.customer_id
AND target.is_current = true
WHEN MATCHED THEN
    UPDATE SET
        customer_name = source.customer_name,
        region = source.region
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        customer_name,
        region,
        valid_from,
        valid_to,
        is_current
    )
    VALUES (
        source.customer_id,
        source.customer_name,
        source.region,
        source.change_ts,
        '9999-12-31 00:00:00',
        true
    );
~~~

The example above demonstrates a simple Type 1 update, not a full SCD Type 2 implementation. For Type 2, close the current version, insert the new version, and map fact keys according to business event timestamps. Prevent batch reruns from duplicating rows by enforcing idempotency with batch IDs, source event IDs, or watermarks.

### 5.5. UNLOAD Data to S3

`UNLOAD` exports query results to S3, useful for file sharing, archiving, or transferring data to other systems.

~~~sql
UNLOAD ('SELECT order_date, store_key, SUM(net_amount) AS revenue
         FROM fact_sales
         GROUP BY order_date, store_key')
TO 's3://company-analytics/exports/daily-revenue/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftUnloadRole'
FORMAT AS PARQUET
ALLOWOVERWRITE;
~~~

Considerations:

- Manage output prefixes by batch and retention.
- `ALLOWOVERWRITE` can overwrite identically named objects; avoid it when concurrent jobs could run simultaneously.
- Protect sensitive exported data with bucket policies, KMS, access points, or Lake Formation depending on architecture.
- `UNLOAD` incurs data transfer and S3 storage/request costs; budget accordingly and clean up temporary outputs per policy.

## 6. ELT, CDC, and Data Integration

### 6.1. ETL and ELT

- **ETL:** extract from source, transform in an intermediate processing system, then load into the warehouse.
- **ELT:** extract and load raw/staging first, then transform with SQL inside the warehouse.

ELT leverages Redshift's MPP power while retaining raw data for reprocessing. However, do not let the warehouse become a dumping ground of unretained, untracked copies. Separate raw, staging, curated, and mart layers—each with clear ownership, schemas, quality checks, and retention.

### 6.2. CDC and Idempotency

CDC captures source changes, typically including inserts/updates/deletes along with metadata such as transaction ID, log sequence number, or commit timestamp.

A reliable CDC pipeline needs:

- Unique event keys for deduplication.
- Event ordering and late-event handling.
- Explicit delete handling, not merely upserts.
- Monitoring for replication lag and schema drift.
- Replay capability from checkpoints.
- Staging tables and idempotent `MERGE` operations.
- Not treating event timestamps as absolute ordering if the source does not guarantee it.

### 6.3. Zero-ETL Integration

Zero-ETL integration connects supported data sources to Redshift, performs an initial load, and continuously replicates changes so data is ready for analytics without operating a custom ETL/CDC pipeline.

Key points to remember:

- "Zero-ETL" does not mean zero latency, zero configuration, or zero cost.
- Permissions, encryption, networking, and target warehouse setup are still required.
- Monitor integration status, lag, schema errors, and recovery.
- Initial loads can take time and resources; target Redshift still requires compute and storage.
- Supported sources and Region availability evolve over time; verify the support matrix before designing.

Zero-ETL fits well when analyzing replicated operational data. If you need complex transforms, multi-source consolidation, historical tracking, or deep data quality checks, downstream pipelines may still be needed.

### 6.4. Data Sharing Across Warehouses

Redshift data sharing lets consumers read live data from a producer warehouse without `UNLOAD`ing to S3 and `COPY`ing a separate copy. Sharing works across Provisioned clusters and Serverless workgroups, within the same account or cross-account; cross-Region sharing is also supported on eligible Regions/warehouses.

A cross-account flow typically involves two sides:

1. The producer creates a datashare, adds database objects, and grants required permissions.
2. The producer authorizes the target AWS account or consumer within supported scopes.
3. The consumer associates the datashare with the appropriate namespace/cluster/workgroup.
4. The consumer creates a database referencing the datashare and `GRANT`s permissions to internal users/roles.

Data sharing can support reads and certain write scenarios if the producer explicitly grants `INSERT`/`UPDATE`/`CREATE` privileges and the consumer associates in a permitted mode. Do not assume every datashare is writable. Cross-Region data sharing incurs data transfer charges from the producer Region to the consumer Region; query compute is billed to the consumer's warehouse. Both sides must satisfy encryption and access requirements. Data sharing fits scenarios requiring compute isolation by workload or team while sharing governed data.

## 7. Querying the Data Lake with Redshift Spectrum

### 7.1. How Does Spectrum Work?

Redshift Spectrum lets you query data in S3 through external schemas/tables, commonly backed by AWS Glue Data Catalog or a compatible catalog. Data remains in S3; Redshift does not need to ingest it all into internal tables.

Example creating an external schema:

~~~sql
CREATE EXTERNAL SCHEMA lake_sales
FROM DATA CATALOG
DATABASE 'analytics_catalog'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftSpectrumRole'
REGION 'ap-southeast-1'
CREATE EXTERNAL DATABASE IF NOT EXISTS;
~~~

External tables hold metadata describing schemas, formats, and S3 locations. Redshift needs Glue Catalog and S3 permissions; if Lake Formation governs data permissions, configure corresponding permissions for the principal/role.

### 7.2. Partition Pruning and Columnar Formats

Spectrum minimizes data read when the data lake layout is well designed:

- Partition by commonly filtered columns such as year/month/day or source.
- Use Parquet/ORC to read only needed columns.
- Pick appropriate compression.
- Avoid excessive small files causing listing/metadata overhead.
- Avoid `SELECT *` when only a few columns are needed.
- Filter directly on partition keys using matching data types.
- Maintain consistent Glue Catalog/partition metadata.

Example query with a partition filter:

~~~sql
SELECT store_id, SUM(net_amount) AS revenue
FROM lake_sales.sales_external
WHERE sales_year = 2026
  AND sales_month = 11
GROUP BY store_id;
~~~

If a partition key is a string but the query casts or wraps it in functions improperly, the optimizer may not prune partitions as expected. Check the query plan and bytes scanned.

### 7.3. Spectrum Costs

On Provisioned warehouses, Spectrum typically incurs scan-based charges on top of warehouse compute and S3 costs. On Redshift Serverless, data lake queries are billed by compute/RPU time just like warehouse queries, without a separate Spectrum scan fee structured the same way as Provisioned.

Regardless of model, reducing scans pays off: faster queries, lower compute time, and less load on the data lake. Review Region- and warehouse-specific pricing before estimating.

## 8. Streaming Ingestion from Kinesis and MSK

Redshift supports streaming ingestion from Amazon Kinesis Data Streams and Amazon Managed Streaming for Apache Kafka (MSK) via materialized views.

~~~mermaid
flowchart LR
    A[Producers] --> B[Kinesis Data Streams / MSK]
    B --> C[Redshift external schema]
    C --> D[Streaming materialized view]
    D --> E[Curated tables / BI]
~~~

Example creating an external schema for Kinesis:

~~~sql
CREATE EXTERNAL SCHEMA streaming_kds
FROM KINESIS
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftStreamingRole';
~~~

Create a materialized view reading the stream (replace stream name with actual stream):

~~~sql
CREATE MATERIALIZED VIEW sales_stream_mv AS
SELECT
    approximate_arrival_timestamp,
    partition_key,
    shard_id,
    sequence_number,
    kinesis_data
FROM streaming_kds."sales-stream";

REFRESH MATERIALIZED VIEW sales_stream_mv;
~~~

Streaming ingestion notes:

- The IAM role must have permissions to read the stream and related resources.
- Raw data may be JSON/Avro or binary payloads; parse and validate before transforming.
- Monitor shards/partitions, throughput, lag, duplicates, and event ordering.
- Design refresh cadence around freshness targets; overly frequent refreshes create overhead.
- Materialized views do not replace data quality checks, deduplication, or retention management.
- When handling replayable events, downstream pipelines must be idempotent.

Use streaming ingestion when you need lower-latency queries on fresh events than batch offers. If you need fan-out, enrichment, or complex orchestration, consider Kinesis Data Analytics/Flink, Lambda, or upstream pipelines before Redshift.

## 9. Federated Queries with RDS and Aurora

Federated queries allow Redshift to query live data in Amazon RDS for PostgreSQL/MySQL or Amazon Aurora PostgreSQL/MySQL and combine it with warehouse/S3 data.

Example external schema to PostgreSQL:

~~~sql
CREATE EXTERNAL SCHEMA operational
FROM POSTGRES
DATABASE 'orders'
SCHEMA 'public'
URI 'orders-db.cluster-abcdefghijkl.ap-southeast-1.rds.amazonaws.com'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftFederationRole'
SECRET_ARN 'arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:redshift/federation/orders';
~~~

Querying the source data:

~~~sql
SELECT o.order_id, o.status, f.net_amount
FROM operational.orders o
JOIN fact_sales f
  ON f.order_id = o.order_id
WHERE o.updated_at >= CURRENT_DATE - INTERVAL '1 day';
~~~

Federated queries can push down portions of filters/compute to the source database, then return result rows to Redshift. Keep in mind:

- Never run heavy analytical queries that scan an entire OLTP database.
- Optimize predicate pushdown and select only needed columns.
- Ensure network routes, security groups, Enhanced VPC Routing, and Secrets Manager access are configured.
- Account for latency, remote database IOPS, connection load, and any cross-Region transfer.
- This is a read path; do not use federated queries as a write-back mechanism to operational databases.
- Federated queries do not support concurrency scaling under current service limits.

If data is queried frequently or requires consistent performance, replicate/CDC it into the warehouse rather than querying the source live every time.

## 10. Materialized Views and Optimizing Repeated Queries

Materialized views persist precomputed query results so subsequent queries read aggregated data instead of re-executing full joins/aggregations.

Example:

~~~sql
CREATE MATERIALIZED VIEW mv_monthly_store_sales AS
SELECT
    DATE_TRUNC('month', order_ts) AS sales_month,
    store_key,
    SUM(net_amount) AS revenue,
    SUM(quantity) AS units_sold
FROM fact_sales
GROUP BY 1, 2;
~~~

When source data changes, materialized views must be refreshed through supported mechanisms. Some queries support incremental refresh; others require a full refresh depending on SQL constructs and source changes. Verify refresh behavior before relying on freshness.

Redshift also offers automated materialized views (AutoMV), which observe workloads and automatically create/maintain selected materialized views to accelerate eligible queries. Not every query gets materialized; monitor benefits, storage, and maintenance cost.

Trade-offs:

- Faster query reads.
- Storage cost for precomputed results.
- Compute consumption during refreshes.
- Data can become stale if refresh cadence is misaligned.
- Excessive materialized views add cost and complexity.

## 11. SQL and Query Optimization

### 11.1. Query Plans with EXPLAIN

Use `EXPLAIN` to inspect the execution plan without running the query:

~~~sql
EXPLAIN
SELECT
    d.region,
    DATE_TRUNC('month', f.order_ts) AS sales_month,
    SUM(f.net_amount) AS revenue
FROM fact_sales f
JOIN dim_customer d
  ON f.customer_key = d.customer_key
WHERE f.order_ts >= '2026-01-01'
GROUP BY 1, 2;
~~~

Check the plan for:

- Are table scans reading too many blocks?
- Are filters applied early?
- Do joins broadcast or redistribute data?
- Are there unintended nested loops?
- Are there large sorts/hash aggregates or disk spills?
- Is one node processing far more rows than others?

Common plan labels:

| Label | General Meaning |
|---|---|
| DS_DIST_NONE | Data is already collocated; no redistribution needed for that join |
| DS_BCAST_INNER | Broadcasts the inner relation to all nodes |
| DS_DIST_INNER | Redistributes the inner relation |
| DS_DIST_OUTER | Redistributes the outer relation |
| DS_DIST_BOTH | Both sides must be redistributed |

Do not judge a plan by a single label alone. Inspect estimated rows, actual runtime, bytes scanned, skew, and queue time to find the real bottleneck.

### 11.2. Writing Efficient Queries

- Select only needed columns; avoid `SELECT *` on large fact tables.
- Filter early with predicates capable of pruning blocks/partitions.
- Avoid wrapping sort-key columns in functions when a direct range predicate works.
- Match data types on join keys to avoid costly implicit casts.
- Avoid fact-to-fact joins when pre-aggregation or dimension lookups suffice.
- Guard against accidental Cartesian joins.
- Limit repeated subqueries that can be materialized or rewritten.
- Partition window functions cleanly to avoid unnecessary global sorts.
- Choose appropriate decimal precision without constant casting inside expressions.
- Avoid many tiny queries when a single bulk operation works better.

Example timestamp predicate:

~~~sql
SELECT SUM(net_amount)
FROM fact_sales
WHERE order_ts >= TIMESTAMP '2026-11-01 00:00:00'
  AND order_ts <  TIMESTAMP '2026-12-01 00:00:00';
~~~

Prefer this over `DATE_PART(month, order_ts) = 11` when leveraging sort order or block pruning on timestamps. Function expressions on columns can force row-by-row evaluation and defeat metadata pruning.

### 11.3. VACUUM and ANALYZE

- **VACUUM:** re-sorts rows by sort key, reclaims space after deletes, and preserves sort quality.
- **ANALYZE:** updates statistics so the optimizer estimates cardinality and picks better joins/plans.
- Redshift performs automatic vacuum and automatic analyze in many scenarios; do not schedule manual commands blindly without a specific issue.
- After large bulk loads, updates/deletes, or substantial data shifts, inspect sort state and statistics.
- Specify `VACUUM SORT ONLY`, `VACUUM DELETE ONLY`, or `VACUUM FULL` intentionally; the wrong mode can trigger heavy maintenance overhead.

### 11.4. Workload Management

Workload Management (WLM) coordinates query concurrency and resource allocation.

**Automatic WLM** is the recommended starting point for most workloads. Redshift determines concurrency and allocates memory dynamically based on workload demand.

Available controls include:

- Query priority to distinguish critical, reporting, and ad-hoc workloads.
- Short Query Acceleration to improve latency for eligible short queries.
- Query Monitoring Rules (QMR) to log, hop, or abort queries exceeding thresholds.
- Concurrency scaling for eligible queues on Provisioned warehouses to handle concurrent bursts.
- Queue routing via user groups, roles, query groups, or rules.

Do not assign high priority to every group. If every query is highest priority, tiering loses all meaning. Use QMR to catch runaway queries, excessive disk spills, or resource abuse; test rules in staging before enabling aborts in production.

### 11.5. Concurrency Is Not Throughput

- **Concurrency** is the number of queries/sessions executing or queued simultaneously.
- **Throughput** is the amount of work completed per unit of time.
- Raising concurrency too high can starve per-query memory, cause disk spills, and lengthen latency.
- Concurrency scaling adds compute for eligible queries, but does not substitute for query tuning or sound data modeling.

## 12. Security and Access Governance

### 12.1. Network Isolation

- Deploy Redshift inside a VPC and private subnets if workloads do not need public endpoints.
- Disable public accessibility unless explicitly justified.
- Restrict security groups to approved application/BI subnets or endpoints.
- Use VPC endpoints / Redshift-managed VPC endpoints when private access is required.
- Enable Enhanced VPC Routing to force `COPY`/`UNLOAD` traffic to S3 through VPC endpoints, route tables, and network policies.
- Enforce TLS for client connections; configure JDBC/ODBC drivers and certificate policies per security standards.

Enhanced VPC Routing does not automatically grant S3 permissions or create endpoints. Appropriate IAM roles, endpoint policies, routes, security groups, and bucket policies are still required.

### 12.2. Encryption

Redshift supports encryption at rest for data and backups using default AWS KMS keys or customer managed keys:

- Customer managed keys give control over key policies, rotation, disabling, and auditing.
- Redshift uses envelope encryption and a key hierarchy.
- The KMS key must be in the same Region and authorized for the Redshift service/role.
- Never disable or schedule deletion for a KMS key while clusters, snapshots, integrations, or restores still depend on it.
- Encryption in transit must be enabled/enforced per security policy.

When data flows through S3, Glue, or Kinesis, Redshift encryption does not automatically encrypt upstream/downstream copies; configure SSE-KMS or appropriate encryption on each service.

### 12.3. IAM Authentication and Database Authorization

Separate two layers:

- **IAM authorization:** who can call APIs to manage clusters/workgroups, snapshots, namespaces, datashares, or obtain temporary database credentials.
- **Database authorization:** which users/roles have `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, or object-level privileges.

Prefer temporary credentials and IAM federation/IdPs over static passwords. Redshift supports IAM-based database authentication, integrating with SAML 2.0 IdPs and compatible JDBC/ODBC drivers.

Example database RBAC:

~~~sql
CREATE ROLE analyst_readonly;

GRANT USAGE ON SCHEMA analytics TO ROLE analyst_readonly;

GRANT SELECT ON ALL TABLES IN SCHEMA analytics
TO ROLE analyst_readonly;

GRANT ROLE analyst_readonly TO analyst_user;
~~~

To cover future tables, configure appropriate default privileges for the object owner/schema and test with real accounts. Do not grant superuser to BI analysts or ETL runtimes unnecessarily.

### 12.4. Row-Level Security and Dynamic Data Masking

- **Row-level security (RLS):** restricts which rows a user/role can view.
- **Dynamic data masking (DDM):** transforms sensitive values at query time so users see only permitted detail levels.
- Column-level privileges restrict access to specific columns.
- Data sharing and Lake Formation require explicit privilege mapping across producers, consumers, and external data.

For example, the North sales team sees only North region rows; analysts see total revenue without seeing customer emails/phone numbers. Test policies across views, datashares, role inheritance, and superuser/break-glass access.

### 12.5. Audit Logging

Redshift provides system tables/views to investigate query and user activity. Audit logging can export to CloudWatch Logs or S3:

- Connection log: authentication, connect/disconnect events.
- User log: changes to user definitions.
- User activity log: SQL activity (requires enabling the corresponding configuration).
- CloudTrail records control-plane APIs such as cluster creation/changes, snapshots, parameters, and resource policies.
- Store audit logs with appropriate retention, access restrictions, and KMS/Object Lock if compliance evidence is required.

Audit logging is not enabled for every destination by default. Verify both database parameters and export settings, and confirm logs actually arrive at the destination.

## 13. Backup, Recovery, and Availability

### 13.1. Provisioned Snapshots

Redshift Provisioned supports automated and manual snapshots:

- Automated snapshots are incremental, capturing changes since the prior snapshot.
- By default, snapshots are taken roughly every 8 hours or after 5 GB of changes per node, whichever comes first; minimum intervals depend on dataset size.
- Default automated snapshot retention is 1 day and is configurable. On RA3, automated snapshots cannot be disabled; retention ranges from 1–35 days. On other node types, setting retention to 0 can disable automated snapshots per service limits.
- Manual snapshots are retained until deleted or until their configured retention expires.
- Snapshot storage incurs charges; copying snapshots cross-Region incurs data transfer and storage costs in the destination Region.

Restoring a snapshot creates a new cluster; data can hydrate progressively while the cluster begins serving queries depending on restore state.

### 13.2. Serverless Recovery Points

Redshift Serverless automatically creates recovery points periodically—typically every 30 minutes or after 5 GB of changes per node, whichever comes first; automatic recovery points are retained for 24 hours. Manual snapshots can also be created for longer retention.

Do not mistake 24-hour recovery points for a long-term backup policy. If RPO/RTO or multi-month/year retention is required, establish snapshot, AWS Backup, or cross-Region plans.

### 13.3. Designing DR

A DR plan should specify:

- RPO: maximum acceptable data loss.
- RTO: maximum time to restore service.
- Source Region and DR Region.
- Snapshot copy, destination Region encryption keys, and retention.
- How endpoints, security groups, IAM roles, secrets, and BI connections are recreated.
- Post-restore data validation procedures.
- Approvers and failover runbooks.

Do not merely enable cross-Region snapshot copy and assume DR is complete. Run periodic restore drills, measure actual recovery times, and verify applications/BI can connect.

## 14. Monitoring and Operations

### 14.1. Key Metrics to Observe

| Category | Metrics / Sources | Operational Question |
|---|---|---|
| Compute | CPU, query duration, throughput, RPU usage | Is compute starved or sitting idle? |
| Storage | RMS used, disk space, snapshot size | Where is data growing rapidly? |
| Workload | Queue length, query queue time, running queries | Are queries waiting due to concurrency or plans? |
| Query | Rows scanned, bytes scanned, spill, execution steps | Are scans excessive or redistributions heavy? |
| Connection | DatabaseConnections, failed connections | Are BI/apps opening too many connections? |
| Load | COPY duration, load errors, batch lag | Are pipelines delayed or hitting file format errors? |
| Security | Failed logins, privilege changes, audit logs | Is there unusual access or over-privileged access? |
| Serverless | Base/max RPU, RPU-hours, usage limits | How is workload scaling and is it approaching budget? |

Combine CloudWatch metrics, Redshift system views, CloudTrail, audit logs, and query history. Aggregate metrics surface symptoms; system views and query plans pinpoint root causes.

### 14.2. System Views and Query History

Useful views depending on warehouse version:

- `SYS_QUERY_HISTORY`: status, timing, user, query type, and query text in the newer system view model.
- `SYS_QUERY_DETAIL`: step-level query details, bytes/rows, and execution behavior.
- `SYS_LOAD_HISTORY` or equivalent load views: track `COPY`/loads.
- `SVV_TABLE_INFO`: table size, sort keys, distribution, and table health.
- `SVL_QUERY_SUMMARY` and system log views: diagnose queries on provisioned clusters.
- `STL_LOAD_ERRORS` or equivalent load error views: identify failing records/files.

Example fetching recent queries (adjust time window and access per environment):

~~~sql
SELECT
    query_id,
    status,
    start_time,
    elapsed_time,
    queue_time,
    execution_time,
    query_text
FROM SYS_QUERY_HISTORY
WHERE start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP)
ORDER BY start_time DESC
LIMIT 20;
~~~

Do not rely on a single view across both Provisioned and Serverless; certain system tables/views exist only on specific deployment types. Check system view documentation for your deployment.

### 14.3. Redshift Advisor

Redshift Advisor surfaces optimization recommendations such as:

- Distribution/sort keys.
- Compression.
- Workload management.
- Table maintenance.
- Cluster sizing.

These are workload-based recommendations, not mandatory commands. Evaluate them against real queries, maintenance windows, workload impact, and cost before applying.

## 15. Cost Control

### 15.1. Cost Components

| Component | Provisioned | Serverless |
|---|---|---|
| Compute | Node-hour, by node type and node count | RPU-hours consumed |
| Storage | Redshift Managed Storage on RA3 or node-family storage | Redshift Managed Storage per GB-month |
| Backup | Snapshot storage, manual retention, cross-Region copy | Snapshots/recovery points by type and retention |
| Data lake | Spectrum scan per Provisioned pricing | Query time/RPU same as warehouse queries |
| Data transfer | Cross-Region, S3/network, and datashare flows | Cross-Region datashare and corresponding network traffic |
| Extra capacity | Concurrency scaling and enabled features | Scaling above base RPU, compute time |
| Integration | CDC/zero-ETL and source/target services | Similar, plus target compute/storage |

You cannot compare the two options solely by per-node or per-RPU price. Model the full workload: query duration, query volume, concurrency, storage growth, snapshots, data transfer, and integration services.

### 15.2. Cost Guardrails

For Serverless:

- Set base RPU to match typical steady demand.
- Set max RPU to cap scaling ceilings.
- Set daily/weekly/monthly usage limits with appropriate actions: alert, log, or stop queries.
- Monitor RPU-hours and storage GB-month.
- Separate workgroups for workloads with different priorities and budgets when needed.

For Provisioned:

- Right-size node count and type using CPU, queue time, query runtime, and RMS telemetry.
- Use reserved pricing when workloads are steady with long-term commitment.
- Pause non-production clusters when idle if SLAs/maintenance permit.
- Use concurrency scaling and elastic resize carefully.
- Remove expired manual snapshots, test clusters, and unowned resources.

### 15.3. Optimizing Storage and Query Costs

- Purge expired raw/staging data per retention.
- Use appropriate compression, sort keys, and partitioning.
- Avoid copying the same dataset across warehouses when data sharing fits.
- Reduce Spectrum bytes scanned via partition pruning and Parquet/ORC.
- Trim snapshot retention while still meeting RPO/compliance targets.
- Limit overly aggressive dashboard auto-refresh schedules.
- Materialize repeated aggregations when compute savings outweigh refresh/storage cost.
- Isolate workloads so ad-hoc queries do not disrupt critical pipelines.

## 16. Reference Architecture for a Retail Sales System

A retail company has the following sources:

- Aurora PostgreSQL storing orders and customers.
- DynamoDB storing sessions and status events.
- Kinesis Data Streams receiving clickstreams.
- S3 storing order history, product feeds, and batch files.
- BI requiring dashboards for revenue by region, store, product, and cohort.

A viable design:

1. Operational databases continue serving transactions.
2. Use zero-ETL or CDC for analytical tables from Aurora/DynamoDB.
3. Clickstreams land in Kinesis; Redshift streaming ingestion reads the stream for near-real-time dashboards.
4. Batch files land in S3 partitioned by year/month/day.
5. Glue Data Catalog manages data lake schemas.
6. Redshift `COPY` loads curated batches into staging/fact/dimension tables.
7. Spectrum queries raw historical data in S3 without loading everything into Redshift.
8. Materialized views precompute daily/monthly aggregations.
9. Data sharing lets BI warehouses read live curated data without copying.
10. RLS/DDM restrict data by region and role.
11. CloudWatch, system views, and audit logs monitor performance, security, and freshness.
12. Snapshots, cross-Region copies, and restore drills protect RPO/RTO.

~~~mermaid
flowchart TB
    A[Aurora / DynamoDB] --> B[Zero-ETL / CDC]
    C[Kinesis / MSK] --> D[Streaming ingestion]
    E[Batch files] --> F[S3 raw zone]
    F --> G[Glue Catalog]
    G --> H[Spectrum]
    B --> I[Redshift staging]
    D --> I
    H --> I
    I --> J[Dimension / Fact]
    J --> K[Materialized views]
    K --> L[BI / Data Sharing]
~~~

Key principle: not every source must be replicated into Redshift. Infrequently accessed raw data can remain in S3; dashboard datasets can be materialized; operational data can be queried via federation in narrow cases. Every path needs clear freshness, ownership, security, and cost models.

## 17. Lab: Building a Retail Data Warehouse Model

This lab uses illustrative SQL—do not run it on production. Create a test warehouse with least-privilege permissions.

### Step 1: Create Schemas

~~~sql
CREATE SCHEMA staging;
CREATE SCHEMA analytics;
~~~

### Step 2: Create Dimensions and Fact Table

~~~sql
CREATE TABLE analytics.dim_store (
    store_key BIGINT IDENTITY(1,1),
    store_id VARCHAR(40) NOT NULL,
    store_name VARCHAR(200),
    region VARCHAR(80),
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.dim_customer (
    customer_key BIGINT IDENTITY(1,1),
    customer_id VARCHAR(64) NOT NULL,
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.dim_product (
    product_key BIGINT IDENTITY(1,1),
    product_id VARCHAR(64) NOT NULL,
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.fact_sales (
    sales_line_id VARCHAR(80) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    order_ts TIMESTAMP NOT NULL,
    store_key BIGINT,
    customer_key BIGINT,
    product_key BIGINT,
    quantity INTEGER NOT NULL,
    net_amount DECIMAL(18,2) NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

### Step 3: Load Data into Staging

~~~sql
CREATE TABLE staging.sales_raw (
    sales_line_id VARCHAR(80),
    order_id VARCHAR(64),
    order_ts TIMESTAMP,
    store_id VARCHAR(40),
    customer_id VARCHAR(64),
    product_id VARCHAR(64),
    quantity INTEGER,
    net_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

After attaching the IAM role and preparing S3 files:

~~~sql
COPY staging.sales_raw
FROM 's3://YOUR_BUCKET/sales/sample/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
CSV
IGNOREHEADER 1
TIMEFORMAT 'auto';
~~~

Replace `YOUR_BUCKET`, Region, IAM role, and prefix with your lab environment values. Never use example ARNs in production.

### Step 4: Validate Data Quality

Before loading the fact table, load corresponding dimension data into `dim_store`, `dim_customer`, and `dim_product`. This lab only creates schemas and illustrates queries; do not assume dimensions automatically contain rows.

~~~sql
SELECT COUNT(*) AS total_rows
FROM staging.sales_raw;

SELECT COUNT(*) AS invalid_amount_rows
FROM staging.sales_raw
WHERE net_amount IS NULL OR net_amount < 0;

SELECT sales_line_id, COUNT(*) AS duplicate_count
FROM staging.sales_raw
GROUP BY sales_line_id
HAVING COUNT(*) > 1;
~~~

### Step 5: Load the Fact Table After Dimension Keys Are Mapped

~~~sql
INSERT INTO analytics.fact_sales (
    sales_line_id,
    order_id,
    order_ts,
    store_key,
    customer_key,
    product_key,
    quantity,
    net_amount
)
SELECT
    s.sales_line_id,
    s.order_id,
    s.order_ts,
    d.store_key,
    c.customer_key,
    p.product_key,
    s.quantity,
    s.net_amount
FROM staging.sales_raw s
JOIN analytics.dim_store d
  ON d.store_id = s.store_id
 AND d.is_current = true
JOIN analytics.dim_customer c
  ON c.customer_id = s.customer_id
 AND c.is_current = true
JOIN analytics.dim_product p
  ON p.product_id = s.product_id
 AND p.is_current = true;
~~~

In production systems, add logic to resolve the dimension version as of transaction time, handle missing keys, deduplicate, and enforce idempotent batches. Do not assume current dimension rows are always accurate for historical facts.

### Step 6: Run Reports and Inspect the Plan

~~~sql
SELECT
    d.region,
    DATE_TRUNC('month', f.order_ts) AS sales_month,
    SUM(f.net_amount) AS revenue,
    SUM(f.quantity) AS units
FROM analytics.fact_sales f
JOIN analytics.dim_store d
  ON f.store_key = d.store_key
WHERE f.order_ts >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY 1, 2
ORDER BY 2, 1;
~~~

Run `EXPLAIN` before executing large queries. Record query duration, rows scanned, redistribution, queue time, and outputs; then change one variable at a time when comparing.

## 18. Common Troubleshooting

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| COPY gets AccessDenied | IAM role, bucket policy, KMS, or endpoint policy | Check attached role, S3 List/Get, KMS decrypt, and CloudTrail |
| COPY reports format error | CSV delimiter, encoding, schema, or Parquet type | Inspect load errors, sample files, and schema mapping |
| Queries slow after bulk load | Sort order, statistics, or distribution | Inspect `EXPLAIN`, `SVV_TABLE_INFO`, and run `ANALYZE`/`VACUUM` if needed |
| Queries spill to disk | Insufficient query memory, large join/aggregate, skew | Check `SYS_QUERY_DETAIL`, WLM, predicates, and intermediate rows |
| One node runs longer than others | Distribution skew or data skew | Check skew metrics, distribution key, and join plan |
| Queue time increases | Concurrency, long queries, workload priority | Check WLM queues, Auto WLM, QMR, and concurrency scaling |
| Spectrum scans too much data | Poor partition pruning, file format, or too many columns | Inspect partitions, Parquet/ORC, `EXPLAIN`, and bytes scanned |
| Streaming view lags | Stream lag, refresh cadence, shard/partition throughput | Check source metrics, IAM, refresh schedule, and consumer lag |
| Zero-ETL integration fails | Permissions, KMS, schema changes, source limits | Check integration status, events, and source/target configuration |
| Federated query times out | Network, security group, overloaded remote database | Check routes, Enhanced VPC Routing, Secrets Manager, and remote load |
| BI connection fails | Endpoint, TLS, IAM auth, or database privileges | Check JDBC/ODBC, credential expiration, SGs, and `GRANT`s |
| Serverless costs spike unexpectedly | Base RPU, prolonged scale-up, query/system table load | Check RPU usage, max capacity, usage limits, and query history |
| Restore fails | KMS key, Region, IAM, snapshot retention | Check snapshot state, destination key grants, and restore permissions |

Never change multiple parameters at once while investigating. Capture a baseline, apply one hypothesis-driven change, re-measure, and roll back if results worsen.

## 19. Common Design Mistakes

**Using Redshift as an OLTP database.** Frequent small updates and continuous point lookups are a poor fit. Keep transactions in operational databases and move data to the warehouse via CDC/ELT.

**Failing to define grain.** Fact tables can double-count, mis-aggregate, or join incorrectly. Document the grain before designing schemas.

**Picking a DISTKEY too early.** Skewed keys turn a single node into a bottleneck. Start with `AUTO`, observe real workloads, and pin manually only with evidence.

**Using DISTSTYLE ALL for large dimensions.** Replicating across every node inflates storage and load/update cost. Reserve it for small, slowly changing dimensions.

**Adding sort keys that queries do not filter on.** Sort keys yield no benefit if query patterns cannot leverage block pruning.

**Declaring inaccurate PK/FK constraints.** Redshift does not enforce constraints; the optimizer may assume data is valid. Only declare them when pipelines guarantee integrity.

**Loading data with row-by-row INSERTs.** Use `COPY`/bulk loads for large volumes, and staging plus `MERGE` for upserts.

**Ignoring duplicates and late-arriving events.** CDC/stream replays can duplicate rows or assign wrong dimension versions. Design for idempotency and watermarks.

**Running federated queries over entire operational datasets.** This can overload source databases and add latency. Pull only needed slices or replicate into the warehouse.

**Scanning S3 via Spectrum without partitioning.** Huge scans inflate runtime and cost. Use partitioning, Parquet/ORC, and projection.

**Creating too many materialized views.** Refresh and storage overhead can outweigh base query costs. Measure workloads and keep only views delivering net value.

**Skipping restore tests.** Having snapshots without validated runbooks, permissions, or KMS keys can cause recovery failures.

**Letting Serverless scale without guardrails.** Configure max RPU and usage limits, and monitor query/system table usage alongside budgets.

## 20. Self-Check Exercises

1. How does Redshift differ from an OLTP database in workload and optimization architecture?
2. What are the roles of the leader node, compute nodes, and slices?
3. How does columnar storage reduce I/O?
4. How does Redshift Managed Storage decouple compute and storage on RA3?
5. When should you choose Provisioned over Serverless?
6. What do namespaces and workgroups manage in Serverless?
7. Why are base RPU, max capacity, and usage limits three distinct concepts?
8. What is the grain of a fact table, and what happens when grain is unclear?
9. How do fact tables and dimension tables differ?
10. What are the trade-offs between star schemas and snowflake schemas?
11. How do surrogate keys support SCD Type 2?
12. Does Redshift enforce primary keys and foreign keys, and how does this affect design?
13. How do `DISTSTYLE AUTO`, `EVEN`, `KEY`, and `ALL` differ?
14. How does data skew impact query performance?
15. How do sort keys enable block pruning?
16. Why should you start with `AUTO` table optimization?
17. Why is `COPY` usually better than row-by-row `INSERT`s?
18. What minimum permissions does an IAM role for `COPY` need?
19. How do staging tables and `MERGE` help handle CDC?
20. How does Redshift Spectrum query S3, and what drives its cost?
21. How does partition pruning reduce scans?
22. How does streaming ingestion use Kinesis/MSK and materialized views?
23. Does Zero-ETL mean zero latency and zero cost?
24. How do federated queries differ from CDC/replication?
25. What problems do Auto WLM, QMR, and concurrency scaling solve?
26. How does `EXPLAIN` help locate query bottlenecks?
27. What roles do `VACUUM` and `ANALYZE` play?
28. Which two layers do IAM authentication and database RBAC protect?
29. How do RLS and DDM differ?
30. Why should you run snapshot restore tests and measure RTO/RPO periodically?

## 21. Production Checklist

- [ ] Workloads are classified: BI, ELT, ad-hoc, streaming, or data science.
- [ ] Provisioned/Serverless is chosen based on workload and total cost.
- [ ] VPC, subnets, endpoints, security groups, and Enhanced VPC Routing are verified.
- [ ] Namespaces/workgroups or clusters have owner, environment tags, and budgets.
- [ ] Grain, facts, dimensions, business keys, and surrogate keys are defined.
- [ ] SCD policies and late-arriving data handling are designed.
- [ ] PK/FKs are declared only when pipelines guarantee valid data.
- [ ] Distribution, sort keys, and encodings use `AUTO` or have benchmarks justifying manual settings.
- [ ] `COPY`/`UNLOAD` use least-privilege IAM roles and proper KMS policies.
- [ ] Staging, deduplication, validation, `MERGE`, and idempotency are tested.
- [ ] Spectrum partitions, Glue Catalog, Lake Formation, and S3 policies are configured properly.
- [ ] Zero-ETL/streaming/federated paths have freshness targets and lag monitoring.
- [ ] WLM, query priorities, QMR, and concurrency scaling are tuned appropriately.
- [ ] `EXPLAIN` and query history are used in performance reviews.
- [ ] Encryption at rest, TLS, IAM auth, RBAC, RLS/DDM, and audit logging are configured.
- [ ] Snapshots, retention, cross-Region copies, and KMS key recovery are verified.
- [ ] Restore drills have measured actual RTO/RPO.
- [ ] CloudWatch metrics, system views, and alerts have owners/runbooks.
- [ ] Serverless max RPU/usage limits or Provisioned resize/pause policies are clear.
- [ ] Cost allocation, storage growth, query usage, and data transfer are reviewed periodically.

## Conclusion

Amazon Redshift is an analytical data warehouse platform built on SQL and MPP architecture. Redshift's effectiveness depends on combining proper data modeling, distribution/sorting strategies, ingestion patterns, workload management, security, and cost governance.

Start with grain and data contracts, use `AUTO` to reduce premature tuning, load data via `COPY`/staging/`MERGE`, and optimize queries using `EXPLAIN` and empirical metrics. Combine Spectrum, streaming, federated queries, zero-ETL, and data sharing wherever each model fits latency and ownership requirements. Finally, design backups, auditing, monitoring, and cost guardrails alongside the architecture rather than bolting them on after the warehouse enters production.

## AWS Reference Documentation

- [What is Amazon Redshift?](https://docs.aws.amazon.com/redshift/latest/mgmt/welcome.html)
- [Amazon Redshift best practices](https://docs.aws.amazon.com/redshift/latest/dg/best-practices.html)
- [Amazon Redshift architecture](https://docs.aws.amazon.com/redshift/latest/dg/c_high_level_system_architecture.html)
- [Amazon Redshift Serverless workgroups and namespaces](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-workgroup-namespace.html)
- [Amazon Redshift Serverless billing](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-billing.html)
- [Amazon Redshift Serverless snapshots and recovery points](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-snapshots-recovery-points.html)
- [Setting usage limits for Amazon Redshift Serverless](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-workgroup-max-rpu.html)
- [Amazon Redshift node types](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-clusters.html)
- [Redshift Managed Storage](https://docs.aws.amazon.com/redshift/latest/dg/c_high_level_system_architecture.html)
- [Best practices for designing tables](https://docs.aws.amazon.com/redshift/latest/dg/c_designing-tables-best-practices.html)
- [Choosing a distribution style](https://docs.aws.amazon.com/redshift/latest/dg/c_choosing_dist_sort.html)
- [Choosing the best sort key](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-sort-key.html)
- [Automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/c_autonomics.html)
- [Data distribution for query optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Distributing_data.html)
- [Loading data best practices](https://docs.aws.amazon.com/redshift/latest/dg/c_loading-data-best-practices.html)
- [COPY command](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY.html)
- [COPY from Parquet and ORC](https://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-columnar.html)
- [Using IAM_ROLE with COPY and UNLOAD](https://docs.aws.amazon.com/redshift/latest/dg/copy-parameters-authorization.html)
- [MERGE command](https://docs.aws.amazon.com/redshift/latest/dg/r_MERGE.html)
- [UNLOAD command](https://docs.aws.amazon.com/redshift/latest/dg/r_UNLOAD.html)
- [Redshift Spectrum external tables](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-tables.html)
- [CREATE EXTERNAL SCHEMA](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_SCHEMA.html)
- [Streaming ingestion from Kinesis and MSK](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-streaming-ingestion.html)
- [Zero-ETL integrations](https://docs.aws.amazon.com/redshift/latest/mgmt/zero-etl-using.html)
- [Federated queries](https://docs.aws.amazon.com/redshift/latest/dg/federated-overview.html)
- [Data sharing overview](https://docs.aws.amazon.com/redshift/latest/dg/datashare-overview.html)
- [Considerations for data sharing](https://docs.aws.amazon.com/redshift/latest/dg/datashare-considerations.html)
- [Sharing data across AWS accounts](https://docs.aws.amazon.com/redshift/latest/dg/across-account.html)
- [Sharing data across AWS Regions](https://docs.aws.amazon.com/redshift/latest/dg/across-region.html)
- [Workload management](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html)
- [Automatic WLM](https://docs.aws.amazon.com/redshift/latest/dg/automatic-wlm.html)
- [Concurrency scaling](https://docs.aws.amazon.com/redshift/latest/dg/concurrency-scaling.html)
- [WLM query monitoring rules](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-wlm-query-monitoring-rules.html)
- [Query performance tuning](https://docs.aws.amazon.com/redshift/latest/dg/c-optimizing-query-performance.html)
- [SYS_QUERY_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_HISTORY.html)
- [EXPLAIN command](https://docs.aws.amazon.com/redshift/latest/dg/r_EXPLAIN.html)
- [Vacuuming tables](https://docs.aws.amazon.com/redshift/latest/dg/t_Reclaiming_storage_space202.html)
- [Database security and access control](https://docs.aws.amazon.com/redshift/latest/dg/r_Database_objects.html)
- [IAM authentication for database credentials](https://docs.aws.amazon.com/redshift/latest/mgmt/generating-user-credentials.html)
- [Database encryption](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-db-encryption.html)
- [Enhanced VPC routing](https://docs.aws.amazon.com/redshift/latest/mgmt/enhanced-vpc-routing.html)
- [Database audit logging](https://docs.aws.amazon.com/redshift/latest/mgmt/db-auditing.html)
- [Snapshots and backups](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-snapshots.html)
- [Cross-Region snapshot copy](https://docs.aws.amazon.com/redshift/latest/mgmt/cross-region-snapshot-copy.html)
- [Amazon Redshift pricing](https://aws.amazon.com/redshift/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
