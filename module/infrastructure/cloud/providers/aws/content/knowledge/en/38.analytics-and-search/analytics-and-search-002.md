# Athena Workgroups, Partition Pruning, and Cost Control

## 1. Why Govern Athena by Workgroup?

Amazon Athena is a serverless SQL query service for data in Amazon S3 and supported data sources. Users do not need to provision clusters, yet every query still reads data, consumes resources, generates outputs, and can incur costs across multiple related services.

In the pay-per-data-scanned model, cost depends primarily on the number of bytes Athena must read. That byte count is affected by:

- How data is organized: partitions, file format, compression, file size, and file count.
- How queries are written: selected columns, partition filters, joins, aggregations, and data range.
- Ability to reuse results from previous queries.
- How workloads are separated and concurrency is controlled.

Athena Workgroups help organize and govern query workloads. A workgroup can enforce its own result configuration, encryption, CloudWatch metrics, data usage controls, engine version, and access permissions.

An effective strategy combines three layers: workgroup governance, data layout, and query discipline. Workgroups provide enforcement and measurement mechanisms; costs drop when queries read less data or use capacity more efficiently.

## 2. Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of Athena Workgroups and governance settings.
2. Distinguish between per-query scan cutoffs and workgroup-wide usage alarms.
3. Configure output location, encryption, expected bucket owner, and workgroup configuration enforcement.
4. Explain how Athena bills by bytes scanned and related charges.
5. Design partition keys around query patterns and implement partition pruning.
6. Distinguish between Glue partition metadata, partition projection, and Glue partition indexes.
7. Use Parquet/ORC, compression, bucketing, and file compaction to reduce scans.
8. Use CTAS to materialize data and optimize repeated queries.
9. Use `EXPLAIN`, query statistics, and CloudWatch to pinpoint bottlenecks.
10. Configure query result reuse and assess stale data risks.
11. Design IAM, S3 results bucket, KMS, and cost allocation tags.
12. Create workgroups, run queries, and check costs using the AWS CLI.

## 3. What Is an Athena Workgroup?

A workgroup is a management unit for Athena queries. Every query execution runs within a designated workgroup. Workgroups help:

- Isolate workloads by team, application, environment, or criticality.
- Manage where query results are stored in S3.
- Enforce encryption and result settings.
- Cap bytes scanned per query.
- Set hourly/daily aggregate usage thresholds and trigger alerts.
- Publish query metrics to CloudWatch.
- Select the Athena engine version.
- Attach tags for cost allocation and tracking.
- Assign workgroups to capacity reservations when using a capacity-based model.

A workgroup is not a database, schema, VPC, or dedicated compute cluster. Nor does a workgroup itself grant permission to read source tables or buckets. Data access continues to be governed by IAM, S3 bucket policies, Lake Formation, and Data Catalog permissions.

### 3.1. Reference Workgroup Model

| Workgroup | Users | Purpose | Guardrails |
|---|---|---|---|
| `analytics-dev` | Developers, data engineers | Query development and testing | Low scan cutoff, separate output |
| `analytics-prod` | Dashboards/service roles | Production queries | Enforced config, encryption, alerts |
| `analytics-ad-hoc` | Analysts | Data exploration | Per-query scan cutoff, usage alerts |
| `analytics-finance` | Finance team | Cost/financial reporting | Restricted data permissions, separate output |
| `analytics-etl` | Pipeline roles | CTAS/INSERT/UNLOAD | Capacity/limits tailored to workload |

Avoid putting every user into the `primary` workgroup when you need separate permissions, cost tracking, and query limits.

## 4. Key Workgroup Settings

| Property | Role |
|---|---|
| `EnforceWorkGroupConfiguration` | Forces clients to use workgroup settings instead of query/client-supplied settings |
| `ResultConfiguration.OutputLocation` | S3 prefix storing query results |
| `ExpectedBucketOwner` | Verifies the account owner of the query results bucket |
| `EncryptionConfiguration` | SSE-S3, SSE-KMS, or CSE-KMS per supported configuration |
| `PublishCloudWatchMetricsEnabled` | Publishes query metrics to CloudWatch |
| `BytesScannedCutoffPerQuery` | Caps bytes scanned per individual query |
| `EngineVersion` | Selects or manages the Athena engine version |
| `RequesterPaysEnabled` | Allows querying Requester Pays buckets when needed |

A workgroup requires a query results location at either the workgroup or query/client level. Without a valid output location, queries may fail.

### 4.1. Enforce Workgroup Configuration

When `EnforceWorkGroupConfiguration=true`, workgroup settings override client-side settings such as output location, expected bucket owner, encryption, and result object configuration. This ensures administrators enforce a single policy across all queries in the workgroup.

If enforcement is off, clients can supply their own settings where permitted. While convenient for experimentation, that makes output location and encryption harder to govern in production.

Enforcing output settings does not automatically restrict source data locations. Queries still require read permissions on source S3 locations and the Data Catalog.

### 4.2. Query Results Location

Use a dedicated bucket/prefix per workgroup, for example:

```text
s3://company-athena-results/
  analytics-prod/
  analytics-dev/
  analytics-finance/
```

Query results can contain data extracted from source tables, so treat them as protected data. Configure Block Public Access, bucket policies restricting principals, SSE-KMS if required, KMS key policies, lifecycle expiration, and object ownership per governance needs.

Expected bucket owner in a workgroup applies only to the S3 output location for query results. It does not automatically apply to source buckets, CTAS/`INSERT INTO` locations, `UNLOAD` outputs, or federated query spill buckets.

### 4.3. Encryption

Workgroups can mandate encryption for query results. With SSE-KMS, principals and services need appropriate KMS permissions such as `kms:GenerateDataKey` and `kms:Decrypt` along the execution path.

Do not encrypt only source data. Query results can also contain sensitive data and are frequently downloaded by multiple users.

## 5. Organizing Workgroups by Ownership and Cost

Design workgroups based on cost-responsible owners, workload types, data sensitivity, SLOs, output buckets, encryption, scan limits, and tags.

Example tags:

| Tag | Example Value |
|---|---|
| `Environment` | `prod` |
| `Owner` | `data-platform` |
| `CostCenter` | `CC-ANALYTICS-01` |
| `DataDomain` | `orders` |
| `Application` | `athena-reporting` |

Workgroup tags can be used in IAM conditions and for cost allocation. For tags to appear in billing/CUR reports as cost allocation tags, activate user-defined cost allocation tags in Billing and Cost Management.

Do not create per-individual workgroups without a clear governance need. Too many workgroups make policies, dashboards, and lifecycles difficult to manage.

## 6. How Does Athena Bill?

Athena SQL can use a pay-per-query model based on data scanned or a capacity-based model via capacity reservations. Under the common pay-per-query model:

\[
\text{Query cost} =
\frac{\text{Billable bytes scanned}}{\text{Bytes per TB}}
\times \text{Regional price per TB}
\]

The price per TB varies by Region and over time. Use the AWS Pricing Calculator or the Amazon Athena Pricing page for current pricing in your target Region.

Under pay-per-query, bytes scanned are rounded up to the nearest MB with a 10 MB minimum per query. DDL statements such as CREATE/ALTER/DROP and partition management statements are not billed for scan under this model; failed queries are not charged for query scan. Cancelled queries are still billed for data scanned up to the point of cancellation.

### 6.1. Illustrative Cost Example

Suppose a Region has an illustrative rate of `P = 5 USD/TB`. This is strictly an illustrative assumption to demonstrate the formula, not a quote for any Region.

| Bytes scanned | Illustrative cost |
|---:|---:|
| 1 TB | 5 USD |
| 200 GB | 1 USD |
| 50 GB | 0.25 USD |
| 10 GB | 0.05 USD |

If a dashboard runs 100 times/day and each query scans 200 GB, total scan is 20 TB/day. Optimizing down to 10 GB/query reduces scan to 1 TB/day. Query cost drops proportionally with bytes read, excluding S3, Glue, KMS, and other services.

### 6.2. Charges Beyond Query Scan

You must also account for S3 storage of source data and query results, S3 requests/data transfer, AWS Glue Data Catalog, Lambda for federated query connectors, KMS requests, capacity reservations, ETL/compaction services, and cross-Region transfer.

A cheap query scan does not mean the overall pipeline incurs no cost.

## 7. Two Types of Data Usage Controls

Athena supports two key usage limit layers within workgroups.

### 7.1. Per-Query Data Usage Control

`BytesScannedCutoffPerQuery` caps total bytes scanned for an individual query in a workgroup.

- Each workgroup has one per-query cutoff.
- When a query exceeds the threshold, Athena cancels that query.
- The cutoff applies per query, not to the sum across all queries.
- Cancelled queries may still be billed for bytes already scanned.
- A query may have written partial results to S3 before cancellation; use lifecycle policies to clean up multipart uploads/incomplete results.

Set cutoffs by workload type. Ad-hoc workgroups can have lower limits than ETL workgroups.

### 7.2. Workgroup-Wide Data Usage Controls

Workgroup-wide controls track total bytes scanned across all queries over a period such as an hour or day. You can set multiple thresholds and use CloudWatch alarms/SNS to notify or trigger operational actions.

This is a usage alerting and response mechanism, not a transactional budget guarantee that immediately halts every query the moment total scans hit the threshold. Running queries may continue until additional controls act. For stronger guardrails, combine per-query cutoffs, workgroup-wide alarms, IAM restrictions on who can run queries, CloudWatch/SNS/Lambda runbooks, AWS Budgets, and admission control.

### 7.3. Choosing Thresholds

| Workgroup | Per-query cutoff | Workgroup alert |
|---|---:|---|
| `analytics-dev` | 10 GB | 100 GB/day |
| `analytics-ad-hoc` | 50 GB | 500 GB/day |
| `analytics-prod` | 100 GB | 2 TB/day |
| `analytics-etl` | 500 GB | 10 TB/day |

These figures are examples. Set thresholds based on actual baselines, user count, data growth, and SLOs.

## 8. Tracking Costs by Workgroup

Enable `PublishCloudWatchMetricsEnabled` to publish query metrics. When creating a workgroup in the console, metrics are often enabled by default; when using the API/CLI, verify the setting explicitly.

Track data scanned per query, query execution time, query planning time, query queue time, succeeded/failed/cancelled query counts, hourly/daily workgroup usage, top query IDs by bytes scanned, and owners.

CloudWatch metrics support dashboards and alarms. The Athena console also displays query stats and execution details. Workgroup metrics do not replace Cost Explorer/CUR: use query metrics to identify technical root causes and billing data to reconcile actual charges.

## 9. What Is Partition Pruning?

Partitioning divides data into physical/logical regions based on keys such as date, month, region, or tenant. Athena uses predicates in `WHERE` to determine which partitions must be read and skips unrelated partitions.

For example, data stored at:

```text
s3://company-lake/orders/
  dt=2026-11-18/region=ap-southeast-1/part-000.parquet
  dt=2026-11-18/region=ap-northeast-1/part-001.parquet
  dt=2026-11-19/region=ap-southeast-1/part-002.parquet
  dt=2026-11-20/region=ap-southeast-1/part-003.parquet
```

If a query only needs Nov 20 and the Singapore region, Athena can skip the remaining partitions provided table metadata and predicates are configured properly.

Partition pruning reduces data read, improves latency, and lowers pay-per-query cost.

## 10. Choosing Partition Keys by Query Pattern

Do not pick a partition key just because a field exists in events. Analyze whether dashboards typically filter by day/month or date ranges, whether analysts filter by region/business unit/tenant, the number of distinct key values, data distribution, size per partition, and the number of empty partition combinations.

For large event/log datasets, common keys are `dt` or `year/month/day` for time, `region` for geography, and `event_type` when cardinality is low and frequently filtered.

Do not partition by `request_id`, `transaction_id`, `user_id` with millions of values, or millisecond timestamps. Those keys produce excessive small partitions, metadata overhead, and high file counts. If you need to filter by high-cardinality keys, consider bucketing, Parquet statistics, or sorting/clustering data.

AWS recommends using the `STRING` type for partition keys so Athena can push partition filtering down to AWS Glue effectively. For date partition values, store standardized strings like `YYYY-MM-DD`. When date arithmetic is needed, cast values after partition filtering or use a separate timestamp column in the data.

## 11. Hive-Style Partitions and Glue Data Catalog

Hive-style paths follow the `key=value` format, for example:

```text
s3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/
```

When creating an external table, declare partition columns:

```sql
CREATE EXTERNAL TABLE analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_total DECIMAL(18,2),
    created_at TIMESTAMP
)
PARTITIONED BY (
    dt STRING,
    region STRING
)
STORED AS PARQUET
LOCATION 's3://company-lake/orders/';
```

Athena requires partition metadata in Glue Data Catalog or a partition projection mechanism to locate data.

### 11.1. Adding Partitions Manually

```sql
ALTER TABLE analytics.orders
ADD IF NOT EXISTS PARTITION (
    dt = '2026-11-20',
    region = 'ap-southeast-1'
)
LOCATION 's3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/';
```

Partitions can be added automatically via Glue crawlers, Glue APIs, or ingestion pipelines.

### 11.2. MSCK REPAIR TABLE

`MSCK REPAIR TABLE` scans an S3 prefix to find unregistered Hive-style partitions and add them to the catalog. It is useful for some initial workflows but should not be run periodically on large tables when better partition management options exist.

Notes: it can take significant time when prefixes contain many partitions; it primarily recognizes Hive-style `key=value` paths; it does not remove stale partition metadata from Glue; and it is not a substitute for partition projection or partition index design.

For large tables, use Glue APIs/partition projection/indexes and a clear metadata lifecycle process.

## 12. Writing Queries to Trigger Partition Pruning

Assume the partition keys are `dt` and `region`.

Good query:

```sql
SELECT
    order_id,
    order_total,
    created_at
FROM analytics.orders
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01'
  AND region = 'ap-southeast-1';
```

The predicates reference the partition columns directly and bound the data range.

Suboptimal query:

```sql
SELECT *
FROM analytics.orders
WHERE CAST(dt AS DATE) = DATE '2026-11-20'
  AND lower(region) = 'ap-southeast-1';
```

Wrapping partition columns in functions or casts can prevent effective partition pushdown. Standardize partition values and compare directly against string literals.

Partition predicates reduce the number of folders/objects read. Data predicates such as `order_total > 1000000` further filter records inside files. With Parquet/ORC, column statistics and predicate pushdown can skip non-matching row groups or stripes.

## 13. AWS Glue Partition Indexes

When tables have hundreds of thousands or millions of partitions, Glue `GetPartitions` calls can become a bottleneck during query planning.

Glue partition indexes help the Data Catalog locate the matching subset of partitions instead of loading the entire partition list and filtering afterward.

When creating an index, choose the partition key order, such as `(region, dt)` or `(dt, region)`. Indexes follow key order. Predicates must include the leading key of the index to leverage index filtering optimally.

Athena requires enabling the table property:

```sql
ALTER TABLE analytics.orders
SET TBLPROPERTIES (
    'partition_filtering.enabled' = 'true'
);
```

Important limits:

- A Glue table can have at most three partition indexes.
- Indexes have states CREATING, ACTIVE, FAILED, or DELETING.
- Indexes only support certain filter expressions; `AND` and supported comparison operators are common cases.
- Expressions with `OR`, `LIKE`, `IN`, `NOT` may not be usable for index filtering.
- The leading key in the index must appear in the expression.
- Indexes add storage items and Glue Data Catalog charges.

Partition indexes do not reduce bytes inside already selected files if the query still reads the same objects. They primarily cut metadata lookup overhead and query planning time.

## 14. Partition Projection

Partition projection lets Athena compute partition values and S3 locations from table properties instead of fetching all partition metadata from Glue Data Catalog.

It fits well when data is partitioned along a predictable pattern, new partitions arrive regularly by day/hour, the table has a large partition count, and you want to avoid manual partition registration.

### 14.1. Projection Types

| Projection type | Example |
|---|---|
| `date` | Dates/times within a range |
| `integer` | Contiguous integer IDs/ranges |
| `enum` | Finite value set such as Regions |
| `injected` | Values supplied directly from predicates per supported configuration |

### 14.2. Example Partition Projection Configuration

Suppose the S3 layout is:

```text
s3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/
```

Configure table properties:

```sql
ALTER TABLE analytics.orders
SET TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.dt.type' = 'date',
  'projection.dt.range' = '2025-01-01,NOW',
  'projection.dt.format' = 'yyyy-MM-dd',
  'projection.dt.interval' = '1',
  'projection.dt.interval.unit' = 'DAYS',
  'projection.region.type' = 'enum',
  'projection.region.values' = 'ap-southeast-1,ap-northeast-1',
  'storage.location.template' =
    's3://company-lake/orders/dt=${dt}/region=${region}/'
);
```

`projection.dt.format` must match the actual partition values and paths. If partition values are `YYYY-MM-DD`, use the corresponding format and align the template accordingly.

### 14.3. Projection Limitations

- When projection is enabled, Athena ignores partition metadata registered in Glue for that table.
- If a projected partition does not exist in S3, the query typically returns no records rather than raising an error.
- If more than half of projected partitions are empty, traditional Glue partitions often perform better.
- Projection is used only by Athena; other engines such as EMR/Redshift Spectrum may still need Glue partition metadata.
- `SHOW PARTITIONS` does not list projected partitions that are not registered in Glue.
- Queries outside the configured range may return 0 rows instead of an error.

Do not use partition projection if the partition space is very sparse or data does not follow a predictable pattern.

## 15. Choosing Between Glue Partitions, Partition Indexes, and Projection

| Criterion | Glue partitions | Glue partition indexes | Partition projection |
|---|---|---|---|
| Partition metadata | Stores each partition in catalog | Stores partitions and indexes | Computed from table properties |
| Partition management | Requires crawler/API/DDL | Requires managing partitions and indexes | No per-partition registration needed |
| Query planning | Can be slow with very many partitions | Accelerates `GetPartitions` filtering | Avoids `GetPartitions` lookup |
| Best suited for | Small/medium tables, non-sparse data | Large tables, high partition metadata count | Regular, predictable partition patterns |
| Sparse partitions | Metadata reflects actual partitions | Metadata reflects actual partitions | Can project many nonexistent partitions |
| Engine compatibility | Broader | Engines supporting Glue indexes | Primarily Athena |

Rule of thumb: tables with few partitions use standard Glue partitions; tables with many actual partitions and clear filter patterns evaluate partition indexes; tables partitioned continuously by date/integer/enum evaluate projection; very sparse tables prefer actual partition metadata and indexes.

## 16. Bucketing for High-Cardinality Keys

Partitioning works well for keys with moderate value counts that are frequently filtered. For high-cardinality keys such as `customer_id` or `device_id`, creating a partition per value is ineffective.

Bucketing divides data into a fixed number of buckets based on a hash of one or more columns. This can help lookups/joins on high-cardinality keys and reduce data read in supported scenarios.

Pick keys with high cardinality, relatively uniform distribution, and frequent filtering; size the bucket count based on volume and workload; avoid creating too many tiny buckets; and test join/filter plans before deploying. Partitioning and bucketing can be combined—for example, partitioning by `dt` and bucketing by `customer_id`.

## 17. Columnar Formats, Compression, and Column Pruning

Athena can reduce bytes scanned substantially when data is stored in columnar formats.

| Format | Characteristics | Best suited for |
|---|---|---|
| CSV/JSON | Row-oriented, flexible, easy to debug | Raw landing, variable payloads |
| Parquet | Columnar, compression and statistics | Analytics, dashboards, selective column queries |
| ORC | Columnar, compression and stripe statistics | Hive-oriented analytics |
| Avro | Row-oriented, schema evolution | Data exchange/streaming use cases |

With Parquet/ORC, Athena can read only the required columns rather than whole row files. Compression also reduces bytes read from S3.

Queries selecting only needed columns are typically cheaper than `SELECT *` when tables have many unused columns and use columnar formats.

Too many small files increase S3 listing, metadata, and query planning overhead. Overly large or non-splittable files can limit parallelism. Use CTAS, Glue ETL, or compaction pipelines to merge small files into columnar files sized for your throughput and query patterns. Do not pick one fixed file size for every workload; measure scan time, file counts, and concurrency.

## 18. CTAS for Data Transformation and Materialization

`CREATE TABLE AS SELECT` (CTAS) creates a new table from query results and writes files to S3. CTAS is useful for converting CSV/JSON to Parquet/ORC, keeping only needed columns, standardizing schemas, creating a new partition layout, materializing frequently repeated aggregations/joins, and building curated layers for dashboards.

Example creating a Parquet table partitioned by day and Region:

```sql
CREATE TABLE analytics.orders_curated
WITH (
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    external_location = 's3://company-curated/orders/',
    partitioned_by = ARRAY['dt', 'region']
) AS
SELECT
    order_id,
    customer_id,
    order_total,
    created_at,
    dt,
    region
FROM analytics.orders_raw
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01';
```

In CTAS, partition columns must be placed at the end of the `SELECT` list matching `partitioned_by`.

CTAS also consumes bytes scanned on input and writes data to S3. Account for ETL, storage, and maintenance costs before materializing. CTAS has a limit on the number of partitions created per statement; if you need more partitions than the current limit, split into batches or use a dedicated ETL pipeline.

Avoid running CTAS over the entire history every day when only new partitions arrive. Use `INSERT INTO`, Glue ETL, or incremental pipelines for new data slices. Manage late-arriving records, partition overwrites/reprocessing, duplicate events, schema evolution, data quality, retention, and compaction.

## 19. Query Result Reuse

Athena can reuse prior query results to avoid re-executing identical queries and re-scanning data.

When result reuse is enabled, Athena searches for a matching result in the same workgroup. Conditions include the query string, database/catalog, result configuration, table access permissions, and read permissions on the S3 result object.

Key limitations:

- Result reuse works only within the same workgroup.
- Only queries that produce an S3 result set are supported; primarily `SELECT`/`EXECUTE` per documentation.
- Results expire after 60 minutes by default if no max age is set.
- Max age is configurable up to 7 days.
- Athena does not check whether underlying source data changed before reusing results.
- Unsuitable for queries requiring the freshest data or using non-deterministic functions like `rand()`.
- Restrictions apply with federated catalogs, Lake Formation row/column filters, and managed query results.

Enable result reuse only when the business accepts the freshness window. Financial dashboards, inventory reports, and near-real-time monitoring must evaluate data recency requirements before enabling it.

## 20. EXPLAIN and EXPLAIN ANALYZE

`EXPLAIN` shows the execution plan so you can see how Athena intends to read tables, join, filter, and distribute data. It is helpful for inspecting plans without executing the full query.

```sql
EXPLAIN
SELECT
    region,
    COUNT(*) AS order_count
FROM analytics.orders
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01'
GROUP BY region;
```

`EXPLAIN ANALYZE` executes the query and provides runtime statistics such as CPU, input/output rows, and operator behavior.

```sql
EXPLAIN ANALYZE
SELECT
    region,
    COUNT(*) AS order_count
FROM analytics.orders
WHERE dt = '2026-11-20'
GROUP BY region;
```

Because the query actually runs and scans data, `EXPLAIN ANALYZE` can incur charges just like a normal query. Use it only when runtime evidence is required.

## 21. Reading Query Statistics

After each query, check Query stats or the `GetQueryExecution` API.

| Statistic | Meaning | Signal to watch |
|---|---|---|
| `DataScannedInBytes` | Bytes of data scanned | Unusually high relative to output |
| `EngineExecutionTimeInMillis` | Engine execution time | Heavy query processing |
| `QueryPlanningTimeInMillis` | Planning time, including partition lookup | High value may indicate many partitions |
| `QueryQueueTimeInMillis` | Time spent waiting in queue for resources | High value may indicate concurrency/capacity pressure |
| `TotalExecutionTimeInMillis` | Total query duration | End-to-end user experience metric |
| `ServiceProcessingTimeInMillis` | Time to finalize/publish results | Bottleneck in result return phase |
| `ResultReuseInformation` | Whether the query reused prior results | Evaluates scan savings and freshness |

A slow query does not always scan a lot of data. If query planning time is high, inspect partition metadata/indexes/projection. If queue time is high, inspect concurrency, workgroup load, and capacity. If engine execution time is high, inspect joins, aggregations, skew, and file layout.

## 22. CloudWatch, EventBridge, and Alerting

Enable query metrics for each workgroup. Build dashboards tracking bytes scanned, query execution time, query planning/queue time, query state/failure counts, hourly/daily workgroup usage, top query IDs or principals by scan volume, and query result reuse rates where recorded.

Use CloudWatch alarms for usage thresholds and SNS for notifications. EventBridge query state change events can trigger Lambda/automation when queries finish, fail, or are cancelled.

Do not send full SQL text or query results to logs if they contain sensitive information. Log query execution IDs, workgroups, principals, databases, and necessary metrics.

## 23. IAM, Lake Formation, and Data Protection

Workgroup controls do not replace data authorization.

A principal running Athena typically needs Athena permissions for workgroup/query actions, Glue Data Catalog permissions to inspect databases/tables/partitions, S3 `GetObject`/`ListBucket` on source data, S3 `PutObject` on the query results bucket, KMS permissions if source/results use SSE-KMS, and Lake Formation grants if tables are governed by Lake Formation.

Use IAM policies to restrict principals to executing queries only in designated workgroups, using workgroup resource ARNs and appropriate condition keys. Separate workgroup admin permissions from query execution permissions. Analysts should not be able to alter output buckets, encryption, or scan cutoffs of production workgroups.

When row-level, column-level, or cell-level permissions are required, use Lake Formation grants integrated with Athena. Workgroups only govern query execution/configuration; Lake Formation controls which data users may read.

## 24. End-to-End Cost Governance

A cost governance workflow can include:

1. Assigning owner, cost center, and data domain tags to every workgroup.
2. Designating output buckets/prefixes and lifecycle policies.
3. Enforcing encryption and query result settings.
4. Setting per-query scan cutoffs.
5. Setting workgroup-wide hourly/daily alerts.
6. Publishing query metrics to CloudWatch.
7. Retaining query execution metadata for analysis.
8. Reviewing top-scanning queries weekly.
9. Optimizing partitions, Parquet/ORC, compression, and CTAS.
10. Reviewing IAM principals with high query scans.
11. Reconciling against Cost Explorer/CUR and AWS Budgets.
12. Updating thresholds as baselines and data volumes grow.

For each high-scan query, identify the workgroup/principal, check `DataScannedInBytes`, verify partition filters, inspect `SELECT *`, format/compression, object count, join cardinality/skew, reuse/materialization options, and compare before/after query stats.

## 25. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Everyone shares the primary workgroup | Difficult access separation and chargeback | Separate workgroups by workload/team |
| Not enforcing workgroup settings | Users can change output/encryption | Enable `EnforceWorkGroupConfiguration` |
| Mistaking workgroup-wide alarms for hard budget caps | Queries keep running | Use per-query cutoffs and response automation |
| No lifecycle policy on query results | S3 results grow indefinitely | Configure lifecycle expiration and access policies |
| `SELECT *` on wide tables | Scans excess columns | Select only needed columns |
| Missing partition filters | Reads unnecessary days/months | Add predicates directly on partition keys |
| Partitioning by request/user ID | Too many tiny partitions | Use bucketing or Parquet statistics |
| Partition projection on sparse tables | Athena projects many nonexistent partitions | Use Glue partitions/indexes |
| Too many small files | Metadata/listing overhead | Use CTAS/compaction |
| Running `MSCK REPAIR` constantly on large tables | Planning/metadata overhead | Use Glue APIs, projection, or partition indexes |
| Running `EXPLAIN ANALYZE` on huge queries just for the plan | Incurs scan charges | Run `EXPLAIN` first |
| Enabling result reuse for real-time reports | Returns stale data | Set a short max age or disable reuse |
| Ignoring query planning time | Focuses solely on engine time | Optimize partition metadata |

## 26. Design Example: Analyzing Orders by Date and Region

An enterprise holds 20 TB of order events in S3, generating roughly 100 GB per day. Analysts frequently query by date, Region, and order type.

| Component | Choice |
|---|---|
| Raw layer | JSON/GZIP or Parquet from ingestion |
| Curated layer | Parquet with appropriate compression |
| Partition keys | `dt`, `region` |
| Glue Catalog | Table metadata, partition indexes when partition count grows |
| Athena workgroup | `analytics-orders` |
| Query results | `s3://company-athena-results/orders/` |
| Encryption | SSE-KMS |
| Per-query cutoff | Baseline-driven, e.g., 50 GB |
| Workgroup alerts | Hourly/daily |
| Metrics | CloudWatch query metrics |
| Query reuse | Enabled for dashboards accepting a freshness window |

Query:

```sql
SELECT
    region,
    order_type,
    COUNT(*) AS order_count,
    SUM(order_total) AS revenue
FROM analytics.orders_curated
WHERE dt >= '2026-11-01'
  AND dt < '2026-11-08'
  AND region = 'ap-southeast-1'
GROUP BY region, order_type;
```

With data partitioned by date/Region and stored in Parquet, Athena skips irrelevant partitions and reads only the needed columns.

## 27. AWS CLI: Creating and Managing Workgroups

### 27.1. Create a Workgroup with Enforced Settings and Cutoff

The example below sets a 50 GiB per-query cutoff, stores query results in S3, and enforces SSE-KMS encryption. Replace the bucket, account, and key ARN with actual values.

```bash
aws athena create-work-group \
  --name analytics-prod \
  --description "Production analytics queries" \
  --configuration '{
    "ResultConfiguration": {
      "OutputLocation": "s3://company-athena-results/analytics-prod/",
      "EncryptionConfiguration": {
        "EncryptionOption": "SSE_KMS",
        "KmsKey": "arn:aws:kms:ap-southeast-1:111122223333:key/00000000-1111-2222-3333-444444444444"
      },
      "ExpectedBucketOwner": "111122223333"
    },
    "EnforceWorkGroupConfiguration": true,
    "PublishCloudWatchMetricsEnabled": true,
    "BytesScannedCutoffPerQuery": 53687091200
  }' \
  --tags Key=Environment,Value=prod Key=Owner,Value=data-platform Key=CostCenter,Value=CC-ANALYTICS-01 \
  --region ap-southeast-1
```

### 27.2. Inspect the Workgroup

```bash
aws athena get-work-group \
  --work-group analytics-prod \
  --region ap-southeast-1
```

Confirm `EnforceWorkGroupConfiguration`, output location, encryption, metrics, and cutoff match expectations.

### 27.3. Run a Query in the Workgroup

```bash
aws athena start-query-execution \
  --query-string "SELECT region, COUNT(*) FROM analytics.orders_curated WHERE dt = '2026-11-20' GROUP BY region" \
  --query-execution-context Database=analytics,Catalog=AwsDataCatalog \
  --work-group analytics-prod \
  --region ap-southeast-1
```

Save the returned `QueryExecutionId` to check execution status and statistics.

### 27.4. Read Bytes Scanned and Execution Time

```bash
aws athena get-query-execution \
  --query-execution-id 01234567-89ab-cdef-0123-456789abcdef \
  --region ap-southeast-1 \
  --query "QueryExecution.{State:Status.State,WorkGroup:WorkGroup,Statistics:Statistics.{DataScannedBytes:DataScannedInBytes,EngineMs:EngineExecutionTimeInMillis,PlanningMs:QueryPlanningTimeInMillis,QueueMs:QueryQueueTimeInMillis,TotalMs:TotalExecutionTimeInMillis}}"
```

Use these metrics to compare queries before and after changing partitions, file formats, or SQL.

## 28. Hands-On Lab: Workgroups and Partition Pruning

### 28.1. Objective

Create a workgroup with guardrails, query a partitioned table, measure bytes scanned, and cut costs with partition pruning/columnar formats.

### 28.2. Prerequisites

- Lab AWS account.
- S3 bucket containing a sample dataset using Hive-style partitions.
- AWS Glue Data Catalog database/table.
- IAM role/user with appropriate Athena, Glue, S3, and KMS permissions.
- Dedicated S3 bucket for query results.
- CloudWatch metrics enabled.

### 28.3. Steps

1. Prepare an `orders` table partitioned by `dt` and `region`.
2. Register partitions via Glue crawler/API or DDL.
3. Create the `analytics-lab` workgroup.
4. Set output location, SSE-KMS, and `EnforceWorkGroupConfiguration=true`.
5. Enable CloudWatch metrics.
6. Set a per-query cutoff suited to the lab dataset size.
7. Run an unfiltered `SELECT *` and record `DataScannedInBytes`.
8. Run a query filtering directly on `dt` and `region`.
9. Run a query selecting only the 3 required columns.
10. Convert a curated copy to Parquet using CTAS.
11. Re-run the query on Parquet and compare bytes scanned.
12. If the table has many partitions, create a Glue partition index and enable `partition_filtering.enabled=true`.
13. If partitions follow continuous dates, test partition projection in a test table.
14. Set a CloudWatch usage alarm and verify notification delivery.
15. Test query result reuse with an appropriate max age.
16. Configure lifecycle rules for the query results bucket.
17. Document latency, bytes scanned, and estimated costs.

### 28.4. Completion Criteria

- Workgroup enforces output/encryption settings.
- Per-query cutoff is applied.
- Workgroup-wide usage alarm sends notifications when thresholds are exceeded.
- Partition-filtered queries scan less data than unfiltered queries.
- Parquet and column pruning reduce bytes scanned where applicable.
- Query statistics are saved for comparison.
- Partition projection/indexes match table characteristics.
- Query result reuse is enabled only when freshness requirements allow it.
- S3 query results have lifecycle rules and access policies.

## 29. Self-Check Questions

### Question 1

What is an Athena Workgroup used for?

**Answer:** Grouping query executions to manage configuration, output location, encryption, metrics, data usage controls, engine version, tags, and access permissions.

### Question 2

What does `EnforceWorkGroupConfiguration=true` do?

**Answer:** Forces queries to use workgroup settings such as output location, expected bucket owner, and encryption instead of client-side settings.

### Question 3

How does a per-query cutoff differ from workgroup-wide usage controls?

**Answer:** Per-query cutoff cancels a single query when bytes scanned exceed the threshold. Workgroup-wide controls track aggregate usage over time and trigger alarms/notifications.

### Question 4

Does a workgroup automatically restrict read access to source S3 buckets?

**Answer:** No. Source access still requires appropriate IAM, S3 bucket policies, and Lake Formation grants.

### Question 5

How does partition pruning reduce cost?

**Answer:** Athena skips unrelated partitions based on predicates, reducing the number of objects/bytes read.

### Question 6

Why should partition keys usually use `STRING`?

**Answer:** So Athena can push partition filtering down to AWS Glue efficiently. Date/numeric values can be standardized as strings and cast when needed.

### Question 7

How does partition projection differ from Glue partition indexes?

**Answer:** Projection computes partition values/locations from table properties and skips Glue partition metadata; partition indexes accelerate finding subsets of partitions already registered in Glue.

### Question 8

When should you avoid partition projection?

**Answer:** When the partition space is very sparse, many projected partitions do not exist, or engines other than Athena need to read Glue partition metadata.

### Question 9

Why should you avoid partitioning by `requestId`?

**Answer:** Very high cardinality produces too many small partitions and metadata overhead. Bucketing or Parquet statistics can be used instead.

### Question 10

How do Parquet/ORC reduce bytes scanned?

**Answer:** Columnar formats let Athena read only required columns; compression and predicate pushdown help skip irrelevant data.

### Question 11

Can `EXPLAIN ANALYZE` incur costs?

**Answer:** Yes. `EXPLAIN ANALYZE` executes the query and scans data; `EXPLAIN` only displays the execution plan.

### Question 12

Can query result reuse return stale data?

**Answer:** Yes. Athena does not check whether source data changed when reusing results; set max age in line with freshness requirements.

## 30. Production Checklist

### Workgroup governance

- [ ] Workgroups are separated by workload/team/environment.
- [ ] IAM policies restrict workgroup access.
- [ ] `EnforceWorkGroupConfiguration` is enabled for production.
- [ ] Output location, expected bucket owner, and encryption are configured.
- [ ] S3 results bucket has lifecycle rules and access policies.
- [ ] Workgroup tags include owner/cost center.
- [ ] Per-query cutoffs are configured.
- [ ] Workgroup-wide usage alarms and response runbooks are configured.

### Data layout

- [ ] Partition keys are derived from query patterns.
- [ ] Partition cardinality and data skew are evaluated.
- [ ] Partition columns use `STRING` where appropriate.
- [ ] Glue partitions/indexes or projection are chosen to fit the workload.
- [ ] Not too many empty partitions exist.
- [ ] Analytical data uses Parquet/ORC and suitable compression.
- [ ] File compaction reduces small files.
- [ ] Bucketing is used only when key/query patterns justify it.

### Query optimization

- [ ] Queries select only needed columns, avoiding `SELECT *`.
- [ ] `WHERE` includes direct predicates on partition keys.
- [ ] Joins and aggregations are checked for cardinality/skew.
- [ ] `EXPLAIN` is used before deep optimization.
- [ ] `EXPLAIN ANALYZE` runs only when runtime evidence is needed.
- [ ] Query stats are captured and compared.
- [ ] CTAS/materialized datasets are considered for recurring workloads.
- [ ] Query result reuse has a max age aligned with freshness needs.

### Cost and security

- [ ] Bytes scanned and query costs are tracked.
- [ ] CloudWatch metrics/dashboards/alarms are enabled.
- [ ] Cost Explorer/CUR and AWS Budgets are used for reconciliation.
- [ ] KMS policies and S3 bucket policies follow least privilege.
- [ ] Lake Formation grants protect rows/columns where required.
- [ ] Query results are not public.
- [ ] Failed/cancelled query artifacts and incomplete multipart uploads have lifecycle cleanup.
- [ ] Periodic reviews of top queries by scan volume and owner are conducted.

## 31. Official Reference Documentation

### Workgroups and cost controls

- [Use workgroups to control query access and costs](https://docs.aws.amazon.com/athena/latest/ug/workgroups-manage-queries-control-costs.html)
- [Create an Athena workgroup](https://docs.aws.amazon.com/athena/latest/ug/creating-workgroups.html)
- [Override client-side settings](https://docs.aws.amazon.com/athena/latest/ug/workgroups-settings-override.html)
- [Configure per-query and per-workgroup data usage controls](https://docs.aws.amazon.com/athena/latest/ug/workgroups-setting-control-limits-cloudwatch.html)
- [Monitor queries and control costs with CloudWatch and EventBridge](https://docs.aws.amazon.com/athena/latest/ug/workgroups-control-limits.html)
- [Enable CloudWatch query metrics](https://docs.aws.amazon.com/athena/latest/ug/athena-cloudwatch-metrics-enable.html)

### Partitioning and data optimization

- [Partition your data](https://docs.aws.amazon.com/athena/latest/ug/partitions.html)
- [Optimize data for Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-data-optimization-techniques.html)
- [Use partition projection](https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html)
- [Optimize Athena with AWS Glue partition indexes](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices-partition-index.html)
- [AWS Glue partition indexes](https://docs.aws.amazon.com/glue/latest/dg/partition-indexes.html)
- [Use columnar storage formats](https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html)
- [Optimize tables and bucketing](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-s3-throttling-optimizing-your-tables.html)

### Query execution and pricing

- [Create a table from query results (CTAS)](https://docs.aws.amazon.com/athena/latest/ug/ctas.html)
- [CTAS considerations and limitations](https://docs.aws.amazon.com/athena/latest/ug/ctas-considerations-limitations.html)
- [Reuse query results](https://docs.aws.amazon.com/athena/latest/ug/reusing-query-results.html)
- [View query statistics](https://docs.aws.amazon.com/athena/latest/ug/query-stats.html)
- [EXPLAIN and EXPLAIN ANALYZE](https://docs.aws.amazon.com/athena/latest/ug/athena-explain-statement.html)
- [Query execution statistics API](https://docs.aws.amazon.com/athena/latest/APIReference/API_QueryExecutionStatistics.html)
- [Amazon Athena pricing](https://aws.aws.amazon.com/athena/pricing/)
- [Amazon Athena FAQs](https://aws.aws.amazon.com/athena/faqs/)
