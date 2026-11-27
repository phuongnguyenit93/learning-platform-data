# Amazon Athena and Querying S3 Data with SQL

Once data is centralized in Amazon S3, analytics teams often need to answer business questions without standing up and operating a separate database cluster just to run queries. Amazon Athena provides a serverless approach: users submit SQL statements, Athena reads data at supported storage locations, executes the query, and writes results to Amazon S3. Teams do not need to provision query servers or manage a cluster during idle periods.

Athena is particularly useful when data is stored in Parquet, ORC, JSON, CSV, Avro, or other supported formats on S3. The service integrates with AWS Glue Data Catalog to look up schemas and partitions, and can work with AWS Lake Formation for data access governance. As a result, analysts can use SQL to explore raw data, query curated datasets, create derived tables, and share results with BI tools.

Serverless does not mean queries are automatically fast or free. Athena costs depend on the usage model and the amount of data processed; queries that scan too many files, select every column, or skip partitions can become expensive. An effective architecture needs proper file organization, schemas, partitions, workgroups, access permissions, and result storage locations from the start.

This lesson belongs to the CLOUD_PROVIDERS_AWS scope: choosing the right service, building systems with observability, security, recoverability, and cost control. The focus is on how Athena queries S3 data using SQL, how to manage catalogs and workgroups, optimize performance, protect data, and operate queries in a multi-team environment.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain Amazon Athena's serverless architecture and how the service reads data on S3.
- Distinguish between source data, metadata in Glue Data Catalog, and query results.
- Create external tables, define schemas, partitions, and data formats.
- Write SQL to filter, aggregate, join, and analyze data on S3.
- Use CTAS, INSERT INTO, and UNLOAD in supported scenarios.
- Manage queries using workgroups, output locations, encryption, and data scan limits.
- Combine IAM, S3 policies, Lake Formation, and KMS to control access.
- Optimize cost and performance with Parquet, compression, partition pruning, and file compaction.
- Identify common errors and design Athena operational workflows.

## 2. What Is Amazon Athena?

### 2.1. A Serverless Query Service

Amazon Athena is an interactive analytics service that lets you run SQL on data stored in Athena-supported sources, most commonly Amazon S3. Athena manages the query execution infrastructure; users focus on SQL, schemas, data, and workload control.

Key characteristics:

- No need to create or maintain query clusters for the standard serverless query model.
- Can read multiple data formats on S3.
- Integrates with AWS Glue Data Catalog to look up databases, tables, columns, and partitions.
- Supports SQL based on the Presto/Trino ecosystem, with differences depending on engine version and Athena features.
- Can create tables and write derived data to S3 via supported statements.
- Can use workgroups to isolate workloads, configure outputs, control queries, and track costs.
- Can extend queries to other data sources via supported federated query connectors.

Athena is well suited for ad hoc queries, data exploration, log analysis, batch reporting, data inspection, and data lake querying. For BI workloads with high frequency, very low latency, or strict concurrency management requirements, you should evaluate Redshift or Athena capacity options as well.

### 2.2. Athena Is Not a Traditional Database

In a traditional database, data is typically loaded into storage managed by the database. With Athena, data can remain in S3; Athena reads objects according to the metadata and SQL provided by the user.

This creates several differences:

- Creating an external table mainly registers metadata and location; it does not necessarily copy data.
- Deleting table metadata does not mean deleting objects in S3.
- Changes to the underlying objects can affect subsequent queries.
- Performance depends heavily on file format, file size, partitions, and the amount of data read.
- Athena does not inherently provide all transaction/update features of a relational database management system.

For append-only file datasets, external tables are usually sufficient. If you need updates, deletes, merges, snapshots, and schema evolution, evaluate table formats such as Apache Iceberg along with supported engines and versions.

### 2.3. Athena and Related Services

| Component | Role |
|---|---|
| Amazon S3 | Stores data objects and query results |
| AWS Glue Data Catalog | Stores database, table, schema, and partition metadata |
| AWS Lake Formation | Governs data lake access permissions at database/table level and supported filters |
| Amazon Athena | Executes SQL on data |
| AWS Glue ETL | Cleans, transforms, compacts, and standardizes data |
| Amazon QuickSight | Builds dashboards and BI analytics |
| Amazon Redshift | Data warehouse for analytical workloads with dedicated models and operational requirements |
| AWS KMS | Manages encryption keys when using SSE-KMS or result encryption |

These services complement each other. Glue Data Catalog describes the data; Athena executes SQL; S3 holds objects. Lake Formation and IAM control permissions. Do not confuse table metadata with the data files themselves.

## 3. Architecture and Query Execution Flow

### 3.1. Basic Flow

An Athena query typically goes through the following steps:

1. A user submits SQL from the Athena console, CLI, SDK, or a BI application.
2. Athena identifies the workgroup and checks configuration, API permissions, limits, and output location.
3. Athena looks up metadata in Glue Data Catalog or a configured catalog/connector.
4. The query engine plans reads for the matching files and partitions.
5. Athena reads data from S3 or federated sources, executing filters, joins, aggregations, and SQL expressions.
6. Results are returned via API and typically written to the workgroup's S3 output location.
7. The user views results, downloads files, or consumes results from another application.

~~~mermaid
flowchart TD
    U[Analyst / BI / SDK] --> W[Athena Workgroup]
    W --> Q[Query Engine]
    Q --> C[Glue Data Catalog]
    C --> M[Schema and partition metadata]
    Q --> S3[Amazon S3 data lake]
    Q --> F[Federated connector if configured]
    Q --> R[SQL execution]
    R --> O[S3 query results]
    R --> API[GetQueryResults / application]
    LF[Lake Formation and IAM] -. controls permissions .-> Q
    KMS[AWS KMS] -. encrypts .-> S3
~~~

The diagram illustrates the general logic. How Athena accesses data and metadata depends on catalog type, connector, Lake Formation, IAM, and workgroup configuration.

### 3.2. Decoupled Storage and Compute

S3 stores data independently from the compute that executes SQL. Therefore:

- Athena can be used on demand without keeping a query cluster running continuously.
- Multiple workgroups can query the same dataset with different configurations and permissions.
- Glue, EMR, Redshift Spectrum, or other engines can consume data on S3 if they have permissions and format support.
- Source data can be preserved in the raw zone while the curated zone is optimized for querying.

This separation provides flexibility but requires strict schema and file management. If a producer changes object structure without updating the catalog or data contract, queries may fail or misinterpret data.

### 3.3. SQL Engine and Versions

Athena provides AWS-managed engine versions. Its SQL is based on Presto/Trino, with differences depending on engine version, table type, and Athena features. A workgroup can configure a specific engine version or use the AWS-managed option under current configuration.

Before using new syntax, engine-specific functions, or Iceberg features:

- Check the workgroup's engine version.
- Confirm the feature is supported in the Region in use.
- Test queries on representative data.
- Review compatibility documentation for the connector/table format.
- Avoid assuming PostgreSQL, MySQL, or Spark SQL syntax will behave identically in Athena.

## 4. Preparing the Athena Environment

### 4.1. Choosing Region and Account

Athena is regional. Determine:

- The Region where the data lake is deployed.
- The account that owns the S3 buckets.
- The account running Athena and Glue Data Catalog.
- The account/role of querying users.
- The storage location for query results.
- VPC endpoints or private access if required by the organization.

When buckets, catalogs, and Athena reside in different accounts or Regions, verify integration support, cross-account permissions, KMS keys, and data transfer costs. Avoid assuming permissions in the querying account automatically apply to the source bucket.

### 4.2. Preparing the S3 Bucket for Data

A data bucket should have:

- Clear prefix and zone structure.
- Agreed-upon object format and compression.
- Read permissions for the querying role.
- Encryption aligned with organizational policy.
- Appropriate lifecycle and retention rules.
- Versioning or replication when recovery is required.
- Catalog tables pointing to the correct location.

Do not place source data and query results in the same prefix. Separating a dedicated result bucket—or at least a dedicated prefix—makes retention, access control, and cost tracking easier.

### 4.3. Preparing the Query Result Location

Athena needs a location to store query results. You can configure the output location at the workgroup level or specify it per request if the workgroup allows it. In a shared environment, configure it centrally at the workgroup level and enforce client-side configuration override so users cannot write results to unmanaged buckets.

Example:

~~~text
s3://company-athena-results/analytics-team/
~~~

The result bucket may contain sensitive data extracted from the lake. Therefore, you should:

- Block public access.
- Grant write permissions to the principal executing queries and read permissions to users who need to view results.
- Enable appropriate encryption, such as SSE-S3 or SSE-KMS.
- Configure lifecycle rules to expire results as required.
- Restrict delete or object-sharing permissions.
- Monitor access and storage costs.

Do not treat the query result bucket as a harmless scratch directory. A single SELECT statement can return PII or financial data that users are not permitted to share broadly.

### 4.4. Creating a Database in Glue Data Catalog

You can create a database in the Athena console or via DDL:

~~~sql
CREATE DATABASE IF NOT EXISTS analytics;
~~~

A database in Glue Data Catalog is a metadata namespace. It does not provision a relational database server and does not automatically grant access to S3 objects.

You can organize databases by domain or zone:

- raw_sales
- standardized_sales
- curated_commerce
- curated_finance

Database and table names should follow consistent naming conventions, avoiding duplicate names or dependencies on personal environments.

## 5. Creating External Tables on S3 Data

### 5.1. What Is an External Table?

An external table describes the logical structure of data residing outside Athena, typically objects in S3. Metadata includes column names, data types, format, SerDe, partitions, and location.

When creating an external table:

- Athena writes metadata to Glue Data Catalog.
- Data remains in the declared S3 location.
- The query engine uses metadata to interpret the files.
- Changing table metadata does not automatically convert or rewrite source files.

### 5.2. Example: Creating a Parquet Table

Suppose order data is organized as follows:

~~~text
s3://company-data-lake/curated/orders/
  order_date=2026-11-19/
    region=ap-southeast-1/
      part-00001.parquet
  order_date=2026-11-20/
    region=ap-southeast-1/
      part-00002.parquet
~~~

You can declare the table:

~~~sql
CREATE EXTERNAL TABLE IF NOT EXISTS curated_commerce.orders (
    order_id       string,
    customer_id    string,
    order_ts       timestamp,
    status         string,
    currency       string,
    total_amount   decimal(18, 2)
)
PARTITIONED BY (
    order_date string,
    region string
)
STORED AS PARQUET
LOCATION 's3://company-data-lake/curated/orders/';
~~~

The `order_date` and `region` columns are declared as partition columns and are not included in the regular data column list in the first part of the definition. Partition names must match the data structure and catalog.

The schema definition must match the Parquet contents. If a column in the file has a different type, different name, or incompatible ordering/metadata, queries may fail or return incorrect data. With Parquet, the schema is stored inside the file; declaring a table does not physically convert data types.

### 5.3. Data Formats and SerDe

A SerDe (serializer/deserializer) helps Athena parse files into rows and columns. Common formats include:

| Format | Characteristics | Notes |
|---|---|---|
| Parquet | Columnar, supports compression and column projection | Typically well suited for analytics |
| ORC | Columnar, includes metadata for optimization | Check engine compatibility |
| JSON | Flexible, suited for events and nested data | Schema may be inconsistent |
| CSV/TSV | Easy to exchange and debug | Must handle delimiters, quotes, escapes, and headers |
| Avro | Includes record-level schema and serialization | Must declare appropriate SerDe/schema |
| Text | Line-oriented or log format | May require Regex SerDe or preprocessing |

If input data is messy, schemas are unstable, or CSV files contain complex quotes/newlines, standardize with Glue before loading into the curated zone.

### 5.4. Creating Tables with a Glue Crawler

A Glue crawler can scan S3, infer schemas, and create/update table metadata. Crawlers are useful for discovery or new data sources, but include paths, classifiers, grouping, and update behavior must be configured carefully.

Risks of uncontrolled crawler usage:

- Differing schemas in the same prefix cause multiple tables to be created.
- Columns are inferred as unintended types.
- Partitions or tables are duplicated.
- The crawler scans query results or temporary outputs.
- Schema drift breaks existing consumers.

For production datasets, maintain a data contract and schema review process. Crawlers can assist with discovery, while official schemas should be managed in a controlled manner.

## 6. Partitions and Partition Pruning

### 6.1. Why Partition?

Partitioning divides a dataset into physical groups by attribute—commonly date, month, region, or event type. When a query includes a condition on a partition key, Athena can skip irrelevant partitions.

For example, a query for revenue on 2026-11-20 does not need to read years of data if the table is partitioned by `order_date`.

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
GROUP BY region;
~~~

Conditions on partition columns enable partition pruning. If a query filters only on `order_ts` while the partition key is `order_date`, Athena may not prune partitions effectively. Use predicates on partition keys and data columns according to their semantics.

### 6.2. Choosing Partition Keys

Partition keys should be chosen based on real query patterns:

- Day or month for time-series data.
- Region, country, or business unit if queries frequently filter by these dimensions.
- Event type when each type has substantial data volume and queries regularly filter by type.

Avoid partitioning on very high-cardinality values such as user ID, request ID, or transaction ID. Too many partitions bloat metadata, increase planning time, and produce small files.

Not every dataset needs partitioning. For small datasets, queries that normally scan everything, or data without a stable filter dimension, partitioning may add more complexity than benefit.

### 6.3. Registering Partitions with MSCK REPAIR TABLE

For Hive-style partition paths, you can run:

~~~sql
MSCK REPAIR TABLE curated_commerce.orders;
~~~

This command instructs Athena to discover and add partition metadata from the corresponding S3 structure. It is not optimal to run continuously on datasets with very large numbers of partitions, as discovering new partitions can be time-consuming.

Another option is adding specific partitions:

~~~sql
ALTER TABLE curated_commerce.orders
ADD IF NOT EXISTS
PARTITION (
    order_date = '2026-11-20',
    region = 'ap-southeast-1'
)
LOCATION 's3://company-data-lake/curated/orders/order_date=2026-11-20/region=ap-southeast-1/';
~~~

Partition updates can be automated with Glue crawlers, Glue jobs, or metadata pipelines. Choose one clear owner mechanism so multiple components do not update the catalog inconsistently.

### 6.4. Partition Projection

Partition projection lets Athena derive partition values from configuration rules instead of storing and retrieving every individual partition in Glue Data Catalog. This feature fits when partitions follow a regular pattern and exist in large numbers.

Example of a daily partitioned table:

~~~sql
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.order_date.type' = 'date',
  'projection.order_date.range' = '2025-01-01,NOW',
  'projection.order_date.format' = 'yyyy-MM-dd',
  'projection.order_date.interval' = '1',
  'projection.order_date.interval.unit' = 'DAYS',
  'storage.location.template' =
    's3://company-data-lake/curated/orders/order_date=${order_date}/'
);
~~~

These are additional properties for a table that already declares the `order_date` partition column. With multiple partition keys, you must configure projection for each key and the template must match the S3 structure. If the range is overly broad or the location template is wrong, Athena may plan reads against many nonexistent paths.

### 6.5. Partition Projection vs. Catalog Partitions

| Criterion | Catalog Partitions | Partition Projection |
|---|---|---|
| Metadata | Stores each partition in the catalog | Computed from rules |
| Best suited for | Irregular partitions or when explicit metadata is needed | Regular-pattern partitions with high volume |
| Updates | Requires crawler, DDL, or pipeline updates | Adjust projection properties |
| Risks | Catalog grows with many partitions | Incorrect range/template causes unintended location scans |

Do not use partition projection solely because partition count is high. First evaluate query patterns, folder naming, and maintainability.

## 7. Writing SQL on S3 Data

### 7.1. Filtering, Column Selection, and Limiting Results

Example querying selected orders:

~~~sql
SELECT
    order_id,
    order_ts,
    status,
    total_amount
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
  AND region = 'ap-southeast-1'
  AND status = 'PAID'
ORDER BY total_amount DESC
LIMIT 100;
~~~

Selecting only required columns helps columnar formats such as Parquet/ORC read less data. `LIMIT` caps the number of returned rows, but it does not guarantee reduced data scanned if the query still needs to read the entire partition to filter or sort.

### 7.2. Time-Based Aggregations

~~~sql
SELECT
    order_date,
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_revenue,
    AVG(total_amount) AS average_order_value
FROM curated_commerce.orders
WHERE order_date BETWEEN '2026-11-01' AND '2026-11-20'
  AND status = 'PAID'
GROUP BY order_date, region
ORDER BY order_date, region;
~~~

If `order_date` is a string partition key in ISO `yyyy-MM-dd` format, string conditions filter accurately in chronological order. For partition keys with other types or formats, use values and expressions matching the schema.

### 7.3. Joining Two Tables

Example joining orders and customers:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.total_amount,
    c.customer_segment
FROM curated_commerce.orders o
JOIN curated_commerce.customer_profile c
  ON o.customer_id = c.customer_id
WHERE o.order_date = '2026-11-20';
~~~

Joins on S3 can be expensive if both tables are large or not filtered early. You should:

- Filter partitions before joining.
- Select only necessary columns.
- Verify join keys have consistent data types.
- Avoid joins that unintentionally multiply rows.
- Consider broadcast/hash strategies based on engine capabilities and data size.
- Create a curated dataset if the same join is repeated frequently.

### 7.4. Handling Nulls and Data Types

Athena supports SQL functions such as `COALESCE`, `NULLIF`, `CAST`, `TRY_CAST`, `CASE`, string, date/time, and aggregate functions depending on engine version.

Example safely converting strings to numbers:

~~~sql
SELECT
    order_id,
    TRY_CAST(raw_amount AS DECIMAL(18, 2)) AS amount
FROM raw_sales.orders_csv
WHERE raw_amount IS NOT NULL;
~~~

`TRY_CAST` returns `NULL` when conversion fails according to engine semantics. Track failed conversion counts so data is not silently lost in reports.

### 7.5. Working with JSON

For JSON with varying structure, you can use `ROW`, `ARRAY`, `MAP` types or JSON functions according to syntax supported by the engine. If the schema is complex and queried frequently, standardize into Parquet with Glue rather than parsing JSON repeatedly in every query.

Example extracting fields from JSON:

~~~sql
SELECT
    json_extract_scalar(payload, '$.eventType') AS event_type,
    json_extract_scalar(payload, '$.customerId') AS customer_id
FROM raw_events.application_logs
WHERE ingest_date = '2026-11-20';
~~~

The `payload` column name and JSON structure are examples only. Verify whether files contain valid JSON, one object per record or another layout, and configure the appropriate SerDe.

## 8. Creating and Writing Data with CTAS, INSERT INTO, and UNLOAD

### 8.1. CTAS

`CREATE TABLE AS SELECT` (CTAS) creates a new table from query results and writes data to S3 in the chosen format/partitioning. It is commonly used to build curated datasets or convert CSV/JSON to Parquet.

~~~sql
CREATE TABLE curated_commerce.daily_paid_orders
WITH (
    format = 'PARQUET',
    external_location = 's3://company-data-lake/curated/daily-paid-orders/',
    partitioned_by = ARRAY['order_date']
) AS
SELECT
    order_id,
    customer_id,
    total_amount,
    order_date
FROM standardized_sales.orders
WHERE status = 'PAID';
~~~

For partitioned CTAS, partition columns must be placed at the end of the `SELECT` list as required by Athena. `external_location` must be a valid location and must not contain existing data per CTAS requirements. Check output before re-running; do not reuse the same location assuming CTAS safely overwrites automatically.

CTAS creates both table metadata and output files. You must manage S3 write permissions, Glue Catalog permissions, encryption, partitions, and lifecycle rules for the new dataset.

### 8.2. INSERT INTO

For supported table formats and table types, `INSERT INTO` can append data to a table:

~~~sql
INSERT INTO curated_commerce.daily_paid_orders
SELECT
    order_id,
    customer_id,
    total_amount,
    order_date
FROM standardized_sales.orders
WHERE order_date = '2026-11-20'
  AND status = 'PAID';
~~~

For file-backed Hive external tables, this typically appends new files; it is not a row-level update like an OLTP database. Re-running the same batch without controls can introduce duplicate data. Use batch IDs, supported partition overwrite workflows, or a table format with appropriate update semantics.

### 8.3. UNLOAD

`UNLOAD` exports query results to S3 in a supported format. It is useful when generating structured output files for other systems to consume:

~~~sql
UNLOAD (
    SELECT
        region,
        SUM(total_amount) AS revenue
    FROM curated_commerce.orders
    WHERE order_date = '2026-11-20'
    GROUP BY region
)
TO 's3://company-data-exports/daily-revenue/'
WITH (
    format = 'PARQUET',
    compression = 'SNAPPY'
);
~~~

Check syntax and output options for your engine version. The destination prefix must meet `UNLOAD` requirements and must not be treated as an arbitrary overwrite target. Protect exported files since data may be shared outside the data lake.

### 8.4. Views

Views store SQL definitions to reuse query logic and provide an abstraction layer for consumers:

~~~sql
CREATE OR REPLACE VIEW curated_commerce.paid_orders_view AS
SELECT
    order_id,
    order_date,
    region,
    total_amount
FROM curated_commerce.orders
WHERE status = 'PAID';
~~~

Views do not necessarily store a copy of the data. When querying a view, Athena executes the view's SQL definition against the source data. If a view contains heavy joins and transforms, repeated queries can incur repeated costs. For frequently repeated reports, evaluate CTAS or aggregated datasets.

## 9. Workgroups and Workload Management

### 9.1. What Is a Workgroup?

A workgroup is an organizational unit for Athena queries. You can use workgroups to separate user teams, environments, or workloads and apply dedicated configurations:

- Query result location.
- Result encryption.
- Engine version.
- CloudWatch metrics.
- Per-query data usage controls.
- Related limits and settings.

Examples:

| Workgroup | Purpose | Recommended Configuration |
|---|---|---|
| analyst-ad-hoc | Exploratory queries | Limit bytes scanned, short result retention |
| finance-reporting | Financial reporting | Strict permissions, encrypted output, full audit |
| data-engineering | ETL and CTAS | Write access to curated prefix, controlled engine |
| development | Experimentation | Low budget and query limits, non-sensitive data |

### 9.2. Enforcing Workgroup Configuration

A workgroup can be configured to override client-side settings. In enterprise environments, enable enforcement so users cannot redirect output locations to unmanaged buckets or disable mandated encryption.

Clearly define who has permission to:

- Create and modify workgroups.
- Change engine versions.
- Change query result locations.
- Change data scan limits.
- View or run queries in a workgroup.

Workgroup administration permissions can affect cost, security, and where results are stored, so they should not be granted broadly.

### 9.3. Data Scan Limits

Workgroups can enforce per-query data scan limits or alerts/controls via supported options. Use limits to protect budgets against queries that accidentally scan the entire lake.

Limits should match the workload. If set too low, valid queries may fail; if set too high, the limit provides little protection. Monitor bytes scanned and tune limits per query group.

### 9.4. Query History and Metrics

Athena provides query execution details and integrates with CloudWatch metrics. You should monitor:

- Query count by workgroup and principal.
- Query runtime and queue time.
- Data scanned.
- Failed/cancelled queries.
- Queries exceeding thresholds.
- Output size and result bucket growth.
- Capacity utilization if using capacity reservations.

Combine query history with tags/workgroups and cost allocation to identify cost-generating teams.

## 10. Security and Access Governance

### 10.1. IAM Permissions for Athena

Users need appropriate IAM permissions to operate Athena, such as starting queries, retrieving status, fetching results, and accessing the relevant workgroup. Exact actions depend on console, CLI, SDK usage, and features.

A role with only `athena:StartQueryExecution` may still fail to run a query if it lacks catalog or S3 permissions. Review permissions across the entire flow:

1. Athena API and workgroup permissions.
2. Glue Data Catalog permissions to read databases/tables/partitions.
3. S3 read permissions on source objects.
4. S3 write and read permissions on query results.
5. KMS key permissions if objects or results are encrypted with SSE-KMS.
6. Lake Formation permissions if catalogs/tables are governed by Lake Formation.

### 10.2. S3 Permissions

To read data, principals typically need `s3:ListBucket` on the appropriate bucket/prefix and `s3:GetObject` on objects. To write query results, principals need write permissions to the configured output location. Object deletion permissions should be granted separately—never automatically given to analysts just because they need to run `SELECT`.

Bucket policies can restrict access by principal, VPC endpoint, TLS, or other conditions. Avoid using `Principal "*"` with broad read/write access on data lake or result buckets.

### 10.3. Lake Formation

When Lake Formation governs a data lake, database/table access can be granted by principal and data permissions. With supported features, you can use LF-tags, column filters, row filters, or cell-level filters.

IAM must still allow the principal to invoke Athena and related services. Lake Formation grants do not automatically grant read access to every object or use of every KMS key if underlying configurations are incomplete. Verify the permission mode, data location registration, and service role permissions.

### 10.4. KMS Encryption

With SSE-KMS, principals need permissions to use the key via both the key policy and IAM policies. Verify:

- The key belongs to the right Region.
- The key policy allows required services/principals.
- Cross-account access is fully configured.
- Query result encryption is enabled at the workgroup level.
- Readers of query results have decrypt permissions.
- The KMS key is not disabled or scheduled for deletion while data still needs to be accessed.

S3 Bucket Keys can reduce KMS API calls in certain SSE-KMS scenarios. However, evaluate their impact on policies and auditing.

### 10.5. Protecting Query Results

Query results can contain all data selected from a table. You should:

- Use a dedicated result bucket with Block Public Access enabled.
- Enable encryption.
- Restrict read permissions by workgroup or group.
- Set lifecycle/retention policies.
- Control URL sharing and file downloads.
- Log access and bucket policy changes.

If query results contain PII, governing the source table with Lake Formation is insufficient if the result bucket allows overly broad read access.

### 10.6. Cross-Account Access

When Athena runs in account A and S3 data resides in account B, configure cross-account permissions across S3 buckets, IAM, Glue Catalog, and KMS according to supported patterns. If Lake Formation governs access, grant cross-account data permissions and set up resource links where required.

Do not simply add a bucket policy and assume queries will work. Verify catalog location, resource policies, KMS keys, and output location permissions in the account running Athena.

## 11. Optimizing Performance and Cost

### 11.1. Understanding the Cost Model

Athena can charge per amount of data scanned under the standard on-demand model; there are also capacity options and feature-specific charges depending on the workload. Pricing varies by Region and current rate tables.

Total cost for an Athena workload may include:

- Athena queries or capacity.
- S3 storage for source data and query results.
- S3 requests.
- Glue Data Catalog and related features per pricing model.
- KMS API requests.
- Lambda and federated connector resources.
- Data transfer and other pipeline services.
- Glue/EMR jobs used to standardize data.

Do not look solely at Athena query charges when evaluating total analytics cost.

### 11.2. Parquet and ORC

Parquet and ORC generally reduce bytes scanned because data is stored in columnar format. If a query reads only 5 out of 50 columns, the engine can skip reading most of the unnecessary columns. Compression also lowers storage footprint and bytes read.

A common pipeline pattern:

1. Keep original JSON/CSV in the raw zone.
2. Use Glue or EMR to convert to Parquet/ORC.
3. Write standardized/curated datasets with partitions.
4. Update Glue Data Catalog.
5. Use Athena to query the optimized tables.

Benchmark codecs and file sizes for your workload. Overly aggressive compression can increase CPU usage; overly small files increase overhead.

### 11.3. Partition Pruning

Partition filter conditions allow Athena to skip folders that do not need to be read. Queries should include predicates on partition columns:

~~~sql
SELECT COUNT(*)
FROM curated_commerce.orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-11-08';
~~~

If the partition key is a string, ISO `yyyy-MM-dd` format allows lexical string comparisons to match chronological order within the same format. For partition keys of other types or formats, use corresponding predicates.

### 11.4. Reading Only Necessary Columns

Avoid `SELECT *` on large datasets when only a few fields are needed. With columnar formats, selecting exact columns reduces the data read and processed.

Example:

~~~sql
SELECT order_id, total_amount
FROM curated_commerce.orders
WHERE order_date = '2026-11-20';
~~~

### 11.5. Small Files and Compaction

Too many small files increase S3 listing, metadata, and task overhead. Mitigation approaches:

- Buffer data before writing to S3.
- Tune Firehose buffer size/interval.
- Compact files using Glue or EMR.
- Choose an appropriate partition count and writer parallelism.
- Monitor average file size and object count per partition.

Files in the range of hundreds of MB are often a starting benchmark for analytics, though not a rigid rule. Workload, concurrency, and schema determine the right size.

### 11.6. Avoiding Unnecessary Scans

- Do not run unpredicated queries across multi-year datasets when only one day is needed.
- Do not use `ORDER BY` unless sorting is required.
- Avoid `DISTINCT` on large datasets when duplicates can be handled in ETL.
- Filter data before joining.
- Use pre-aggregated datasets for recurring reports.
- Set query limits in the workgroup.
- Use `EXPLAIN` to inspect query plans when needed.

### 11.7. CTAS and Materializing Results

If the same transformation runs frequently, CTAS can produce a partitioned, compressed derived dataset so subsequent queries read less data. However, CTAS adds storage and pipeline maintenance; account for refresh costs, retention, and duplicate data risks.

### 11.8. Result Reuse

Athena offers query result reuse for supported scenarios. When queries and conditions qualify, the system can return previously stored results instead of re-executing. This can reduce latency and cost for repeated queries, though you must configure maximum result age and understand cache invalidation rules.

Do not rely on result reuse for data requiring immediate freshness if stale results are unacceptable. Check workgroup settings, query parameters, and supported conditions before depending on this feature.

### 11.9. Capacity Reservations

For workloads with steady concurrency and throughput requirements, organizations can evaluate Athena capacity reservations where supported for the Region and engine type. Capacity helps control performance and availability for critical workloads, but introduces a different cost commitment than pay-per-data-scanned.

Measure concurrency, query runtimes, and utilization before choosing capacity. Do not purchase capacity solely based on analyst headcount or peak requests without workload telemetry.

## 12. Federated Queries

### 12.1. Concept

Athena federated queries allow querying data from sources outside S3 via connectors. Connectors are typically deployed using Lambda and can connect to supported sources such as relational databases, document stores, or other systems.

Benefits:

- Use a single SQL interface across multiple sources.
- Reduce the need to copy all data into S3 before exploring.
- Join data lake datasets with data still residing in source systems.

### 12.2. Considerations

- Connectors may require dedicated Lambda functions, IAM roles, network/VPC configuration, and secrets.
- Queries can place direct load on source databases.
- Predicate pushdown and performance depend on the connector.
- Data may temporarily spill to S3 depending on connector settings.
- Cross-account and KMS permissions must be verified.
- Costs include Athena as well as connector/downstream resources.

Federated queries are well suited for exploration or reasonably scoped queries. For large, recurring analytics, ingesting data into S3/a warehouse offers better performance and cost control.

## 13. Athena with Apache Iceberg

### 13.1. When to Use Iceberg

With plain Parquet files, appending is straightforward, whereas updates/deletes and concurrent writes require custom logic. Apache Iceberg adds table metadata, snapshots, and transaction semantics at the table format layer, supporting schema evolution, partition evolution, and engine-level mutation operations.

Athena supports querying and certain write/management operations on Iceberg tables depending on engine version and service limits. Before using `UPDATE`, `DELETE`, `MERGE`, time travel, or vacuum/maintenance, verify supported syntax and features for your Region/workgroup.

### 13.2. Example: Creating an Iceberg Table

Illustrative example:

~~~sql
CREATE TABLE curated_commerce.orders_iceberg (
    order_id string,
    customer_id string,
    order_ts timestamp,
    order_date date,
    region string,
    status string,
    total_amount decimal(18, 2)
)
LOCATION 's3://company-data-lake/curated/orders-iceberg/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);
~~~

Iceberg schema and syntax can vary by engine version. Follow Athena documentation for your running engine, and ensure catalog, S3 location, encryption, and Lake Formation permissions are configured.

### 13.3. Managing Snapshots and Files

Iceberg generates metadata and snapshots on data commits. Without maintenance, file and metadata counts can grow. Establish procedures to:

- Compact data files when small files accumulate.
- Expire snapshots according to approved retention.
- Clean up orphan files using supported maintenance operations.
- Control concurrent writers and commit conflicts.
- Test time travel/rollback capabilities before relying on them in recovery runbooks.

Do not arbitrarily use S3 Lifecycle rules to delete data files by prefix if table metadata still references those files.

## 14. Querying, Testing, and Troubleshooting

### 14.1. Query Verification Workflow

Before running production queries:

1. Confirm the right workgroup and Region.
2. Check table schema and S3 location.
3. Verify catalog, S3, and KMS permissions.
4. Add partition predicates.
5. Select only needed columns.
6. Test on a small data slice or safe limit.
7. Inspect query execution details, bytes scanned, and runtime.
8. Reconcile results against source metrics or control reports.

### 14.2. EXPLAIN

`EXPLAIN` displays the execution plan to help understand how the engine intends to read and process data:

~~~sql
EXPLAIN
SELECT
    region,
    SUM(total_amount)
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
GROUP BY region;
~~~

Use the plan to verify partition pruning, joins, and scan stages. Execution plans do not replace benchmarking; actual performance also depends on file sizes, concurrency, and system state.

### 14.3. Common Errors

| Error / Symptom | Possible Cause | Remediation |
|---|---|---|
| AccessDenied when running query | Missing Athena, Glue, S3, Lake Formation, or KMS permissions | Check each permission layer and the executing principal |
| Table/database not found | Wrong Region/catalog, table not created, or wrong name | Check Glue Data Catalog and workgroup |
| Query returns 0 rows | Unregistered partitions, wrong location, or unmatched predicate | Verify object paths, partition metadata, and filters |
| HIVE_BAD_DATA | File contains records/types incompatible with schema | Inspect bad files, check SerDe, and standardize data |
| Schema/partition mismatch | Partitions have differing schemas | Standardize schemas or separate datasets by version |
| Query is very slow | Many small files, large scan, inefficient join | Compact files, use Parquet, partition, and optimize SQL |
| Query exceeds data scan limit | Query reads too much data | Add filters, adjust workgroup limits, and reduce columns |
| Results not updating as expected | Reading stale partition or hitting result reuse | Check partitions, data arrival, and cache settings |
| CTAS/UNLOAD fails | Output location, write permissions, or prefix issue | Verify S3 permissions, KMS, and prefix state |
| Cannot decrypt results | Missing KMS permissions or disabled key | Check key policy, IAM, and key state |

### 14.4. Reading Query Execution Details

When investigating, review:

- Query execution ID.
- Status and failure reason.
- Workgroup and engine version.
- Data scanned.
- Queue time and engine execution time.
- Output location.
- Query text and principal.

Record the query execution ID in tickets or investigation logs so other teams can trace it. Do not include query text containing sensitive data in public logs.

## 15. Practical Walkthrough: Revenue Analysis on S3

### 15.1. Scenario

An e-commerce system records orders in Aurora PostgreSQL. AWS DMS delivers full load and CDC data into an S3 raw zone. A Glue job standardizes schemas, deduplicates records, and writes Parquet into a curated zone partitioned by date and region.

The analytics team needs:

- Revenue by day and region.
- Count of paid orders.
- Average order value.
- List of high-value orders.
- Queries must not expose customer emails or phone numbers.

### 15.2. Registering the Table

Glue Data Catalog contains the `curated_commerce` database and `orders` table pointing to the partitioned Parquet prefix. Lake Formation grants `SELECT` to the analyst role on permitted tables or views.

The `finance-reporting` workgroup is configured with:

- Dedicated output location.
- Mandatory encryption.
- Budget-aligned query limit.
- Tested engine version.
- CloudWatch metrics enabled.

### 15.3. Aggregation Query

~~~sql
SELECT
    order_date,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_order_value
FROM curated_commerce.orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01'
  AND status = 'PAID'
GROUP BY order_date, region
ORDER BY order_date, region;
~~~

The query narrows down the analysis month using the `order_date` partition key. If the dataset can contain duplicates from CDC or replays, apply latest-record deduplication logic before aggregating.

### 15.4. Creating a Derived Dataset

If dashboards need the same daily aggregation every day, data engineering can run CTAS or Glue ETL to build a daily revenue table. This dataset can be partitioned by month/day and include only required columns.

During refresh:

- Identify the batch/window to update.
- Prevent duplicate appends if the job reruns.
- Reconcile order counts and total revenue against source control figures.
- Publish partitions only after quality checks succeed.
- Track bytes scanned and runtime.

### 15.5. Access Control

Analysts read views/datasets with PII stripped out. Customer support teams may receive separate permissions if justified by business need and approved. The result bucket allows only the corresponding group to read outputs. CloudTrail and query history support auditing query activity.

## 16. Operating and Governing Athena at Scale

### 16.1. Standardizing Workgroups

Multi-team organizations should define workgroups by workload or sensitivity tier. Establish naming conventions, owners, output locations, encryption, engine versions, scan limits, and retention. Avoid letting all users run queries in an unowned shared workgroup.

### 16.2. Managing Schema Changes

When a producer adds, removes, or changes a column type:

1. Identify table consumers.
2. Assess backward compatibility.
3. Update the data contract and Glue Catalog.
4. Test queries, views, and ETL jobs.
5. Roll out by version or within a migration window for breaking changes.
6. Monitor errors after release.

Do not alter the catalog schema merely to make a query pass if the underlying physical files have not been converted.

### 16.3. Monitoring and Alerting

Monitor:

- Failed/cancelled queries.
- Query runtime and queue time.
- Data scanned by workgroup.
- Count of queries exceeding thresholds.
- Output bucket growth.
- Glue Catalog access failures.
- Lake Formation permission denials.
- Connector Lambda errors and spill storage when using federated queries.

Use CloudWatch alarms and EventBridge to notify or trigger workflows. Alerts should have defined owners, severity levels, and concrete remediation steps.

### 16.4. Managing Result Lifecycle

Query results and CTAS/UNLOAD outputs accumulate in S3. Apply tailored lifecycle rules:

- Short retention for ad hoc results.
- Regulatory retention for audit reports.
- Business-driven retention for curated datasets.
- Clean up temporary CTAS outputs once confirmed no consumers remain.

Do not apply one blanket lifecycle rule across all prefixes if retention needs differ.

### 16.5. Change Control and Auditing

Manage changes to workgroups, catalogs, bucket policies, KMS keys, Lake Formation grants, and connectors. Use IaC or review workflows for production configurations. CloudTrail records API activity; query history helps identify statements and executions. Restrict configuration edit permissions so analysts do not inadvertently alter shared policies.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking creating an external table copies data into Athena | Confuses metadata with source objects | Understand Glue Catalog and S3 are separate layers |
| Running `SELECT *` on a large lake | Scans unnecessary columns and increases cost | Select only required columns |
| Skipping partition filters | Scans unnecessary days/months | Add predicates on partition keys |
| Partitioning on high-cardinality IDs | Bloats metadata and slows query planning | Pick partitions based on query patterns |
| Writing too many small files | Increases read and metadata overhead | Buffer and compact files |
| Running crawlers unchecked | Schema drift and duplicate tables | Enforce data contracts and schema reviews |
| Not configuring a result bucket | Results may land in unintended locations | Enforce workgroup output locations |
| Granting only Athena permissions | Queries fail at Glue/S3/KMS/Lake Formation | Verify end-to-end permissions |
| Opening result bucket access too broadly | Exposes extracted data | Separate bucket, enforce encryption, and restrict reads |
| Re-running CTAS into the same prefix | Output failures or inconsistent data | Manage locations and batch refreshes |
| Retrying write queries non-idempotently | Duplicates derived data | Use batch IDs, partition controls, and proper table formats |
| Using Athena for every BI workload | May miss latency/concurrency targets | Evaluate Redshift or suitable capacity options |

## 18. Athena Implementation Checklist

### Before Querying

1. Identify Region, account, workgroup, and data owner.
2. Verify bucket/prefix and data format.
3. Create the appropriate Glue database/table or catalog.
4. Confirm schema, partitions, and locations.
5. Configure query result bucket, encryption, and lifecycle.
6. Grant Athena, Glue, S3, KMS, and Lake Formation permissions.

### When Writing SQL

1. Select only required columns.
2. Filter partitions directly in the query.
3. Verify data types, timezones, and nulls.
4. Filter before joining.
5. Use `EXPLAIN` and query execution details when needed.
6. Test on a small data range before running across the full dataset.

### During Operations

1. Separate workgroups by workload and access tier.
2. Set data scan limits and alerts.
3. Monitor query runtime, bytes scanned, and errors.
4. Compact small files and optimize Parquet/ORC.
5. Review schema changes and catalog metadata.
6. Protect query results and manage retention.
7. Review costs across Athena, S3, Glue, KMS, and connectors.
8. Test both allowed permissions and permissions that must be denied.

## 19. Conclusion

Amazon Athena lets you query data on S3 with SQL without managing query clusters under the standard serverless model. Athena uses metadata from Glue Data Catalog or supported catalogs/connectors to understand schemas, partitions, and data locations; the query engine reads objects, executes SQL, and writes results to an S3 output location.

To query effectively, choose suitable file formats, prefer Parquet/ORC for analytics, partition according to real filter patterns, compact small files, and avoid reading unnecessary columns or partitions. External tables register metadata; CTAS builds derived datasets; `INSERT INTO` and `UNLOAD` support write/export flows within engine features and limits. Workgroups isolate workloads, standardize output locations, enforce encryption, and bound scans.

Athena security is multi-layered: IAM for APIs, Glue Catalog for metadata, S3 for objects, Lake Formation for data permissions, and KMS for encryption. Query results must be protected just like source data. When combined with governance, monitoring, schema management, and FinOps, Athena becomes a valuable component of a data lake—enabling analysts to explore data and generate insights while keeping performance, access, and cost under control.
