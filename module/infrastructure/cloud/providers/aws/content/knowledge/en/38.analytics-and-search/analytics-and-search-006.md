# Redshift Spectrum and Analytical Data Sharing

An enterprise typically holds analytical data in multiple places: large fact tables in Amazon S3, dimension tables in the data warehouse, datasets managed by BI teams, and data shared with other accounts or business units. Copying all data into a single warehouse drives up ETL cost, storage, and synchronization lag. Conversely, letting every team access S3 independently and define their own schemas leads to inconsistent permissions, duplicated analytical logic, and weak governance.

Amazon Redshift provides two complementary capabilities:

- **Redshift Spectrum** lets you query data residing outside the warehouse—most commonly files in Amazon S3 described by AWS Glue Data Catalog, Athena Data Catalog, or a Hive metastore. Users can combine external tables with local tables in the same SQL statement.
- **Redshift data sharing** lets you share live database objects from a Redshift producer with other clusters or Serverless workgroups via a datashare. Consumers query shared data using their own compute without building separate ETL copies.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, these two capabilities enable analytics architectures that share both data lakes and warehouses—supporting BI, data science, cross-department reporting, and multi-account/multi-Region sharing. Learners must distinguish external tables, datashares, and Lake Formation; and design IAM, metadata, partitions, producer/consumer permissions, performance, and cost. The goal is delivering accurate, governed, and observable data.

## 1. Two Problems and Two Mechanisms

Both Redshift Spectrum and data sharing help multiple teams access data, yet they solve different layers.

| Criterion | Redshift Spectrum | Redshift Data Sharing |
|---|---|---|
| Primary data | Files outside the warehouse, typically in S3 | Database objects in a Redshift producer; can include supported external data lake tables |
| Metadata | External schemas and external catalogs | Datashares, object permissions, and consumer associations |
| Access method | Query external tables via SQL | Consumer creates a database referencing the datashare and queries it |
| Data copying | No need to load all files into local tables | No warehouse data copy created for consumers |
| Query compute | Redshift query engine combined with the data lake query layer | Consumer's own compute executes queries over shared data |
| Permissions | IAM role to catalog/S3 plus SQL privileges in Redshift; optionally Lake Formation | Producer grants datashare and consumer access; consumer grants internal users/roles |
| Purpose | Combine data lake and warehouse | Distribute governed analytical data across multiple warehouses |

An architecture can combine both: a Redshift producer creates a datashare containing a view that joins a local table with an external S3 table; consumers receive the datashare and query that view alongside their own tables.

## 2. What Is Redshift Spectrum?

Redshift Spectrum is the capability to query data in Amazon S3 through external tables. An external table stores metadata such as column names, data types, file formats, and S3 locations; the data itself remains in S3. Users query external tables in Redshift like standard SQL tables and can join them with local tables.

With the RA3 provisioned architecture, data lake queries run on a dedicated Spectrum processing fleet separate from cluster compute. With Redshift RG provisioned and Redshift Serverless, the data lake query engine is integrated into service compute. Because execution architectures differ, check documentation and pricing for the specific warehouse type in use.

~~~mermaid
flowchart LR
    A[BI / SQL client] --> B[Amazon Redshift]
    B --> C[Local tables]
    B --> D[External schema]
    D --> E[AWS Glue Data Catalog]
    D --> F[Redshift Spectrum / data lake query engine]
    F --> G[Amazon S3 data files]
~~~

Spectrum does not automatically copy all S3 data into a local table before each query. The query optimizer can push certain filters and aggregations down to the data lake processing layer to minimize data returned to the warehouse.

Verify Region constraints by warehouse type before deploying. With an RA3 provisioned cluster, the cluster and the S3 buckets queried by Spectrum must reside in the same Region. RG provisioned and Redshift Serverless use an integrated data lake query engine that supports cross-Region S3 queries per current service documentation.

## 3. External Schemas and External Tables

An external schema is a Redshift schema referencing a database in an external data catalog. An external table is metadata describing the external files Redshift reads.

The external catalog can be AWS Glue Data Catalog, Athena Data Catalog, or an Apache Hive metastore—such as one managed by Amazon EMR.

When catalogs are managed centrally, multiple tools such as Athena, Glue ETL, and Redshift share the same metadata. Catalog updates become visible to referencing Redshift clusters without recreating local tables.

### Setup Flow

1. Upload data files to S3 following the chosen layout and format.
2. Create database/table/partition metadata in Glue Data Catalog or a compatible catalog.
3. Create an IAM role allowing Redshift to read the catalog and data.
4. Attach the role to the Redshift cluster or Serverless namespace/workgroup per service configuration.
5. Create an external schema pointing to the catalog database.
6. Create external tables in the schema, or use tables already present in the catalog.
7. Grant SQL permissions to Redshift users.
8. Inspect query plans, file counts, and bytes scanned.

## 4. IAM Roles for Redshift Spectrum

Redshift needs permissions to access the catalog and S3 objects on behalf of users running queries. The standard pattern is creating an IAM role with a trust policy for the Redshift service, attaching it to the cluster/namespace, and specifying its ARN in `CREATE EXTERNAL SCHEMA`.

The role typically needs these permission groups:

- S3: `s3:ListBucket` on buckets/prefixes and `s3:GetObject` on objects to read.
- Glue Data Catalog: permissions to read databases, tables, partitions, and metadata such as `glue:GetDatabase`, `glue:GetTable`, `glue:GetPartitions`.
- KMS: `kms:Decrypt` if objects are encrypted with SSE-KMS and the role must read the key.
- Lake Formation: permissions granted via Lake Formation if tables/paths are governed by it.

Do not grant `s3:*` account-wide if the workload only reads one bucket or prefix. Separate roles by data domain, account, or sensitivity level to narrow scope.

Example creating an external schema referencing Glue Data Catalog:

~~~sql
CREATE EXTERNAL SCHEMA spectrum_sales
FROM DATA CATALOG
DATABASE 'sales_lake'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftSpectrumReadRole'
REGION 'ap-southeast-1';
~~~

In this statement, `REGION` specifies the Data Catalog's Region, not a directive for where S3 files live. If the catalog sits in another Region, specify the catalog's Region and check data access constraints for your Redshift warehouse type.

### SQL Permissions in Redshift

The IAM role authorizes the service to read data sources; it does not automatically grant query access to every database user. Users also need `USAGE` on the external schema and `TEMP` on the database to run Spectrum queries.

~~~sql
GRANT USAGE ON SCHEMA spectrum_sales TO GROUP analysts;
GRANT TEMP ON DATABASE analytics TO GROUP analysts;
~~~

When using Lake Formation, table/column/row access is checked against the principal and policies configured in Lake Formation. Do not assume that because the IAM role can read S3, every Redshift user is allowed to read every column.

## 5. Creating External Tables on S3

If metadata is not yet in the catalog, you can create an external table via Redshift DDL. For example, order data stored as Parquet in S3:

~~~sql
CREATE EXTERNAL TABLE spectrum_sales.orders (
    order_id       BIGINT,
    customer_id    BIGINT,
    order_ts       TIMESTAMP,
    region         VARCHAR(32),
    total_amount   DECIMAL(18,2)
)
PARTITIONED BY (year SMALLINT, month SMALLINT)
STORED AS PARQUET
LOCATION 's3://company-data-lake/curated/orders/'
TABLE PROPERTIES ('numRows'='250000000');
~~~

`LOCATION` points to the prefix holding the data files. `PARTITIONED BY` describes partition columns present in the data layout. `numRows` provides an estimated row count to help the optimizer plan joins; Redshift does not run `ANALYZE` to generate statistics for external tables the way it does for local tables.

If the table is already defined in Glue Data Catalog or Athena, create an external schema pointing to that database and use the existing table directly. Avoid defining the same dataset multiple times with inconsistent schemas, partitions, or locations.

### Inspecting External Tables

~~~sql
SELECT schemaname, tablename, location
FROM svv_external_tables
WHERE schemaname = 'spectrum_sales';
~~~

You can use `SVV_EXTERNAL_COLUMNS` to inspect schemas and `SVV_EXTERNAL_PARTITIONS` to inspect partition metadata.

## 6. Partitioning for External Tables

Partitioning divides a dataset into prefixes by frequently filtered attributes such as year, month, day, region, or event type. Redshift Spectrum skips unrelated partitions when queries filter directly on partition columns.

Example layout:

~~~text
s3://company-data-lake/curated/orders/
  year=2026/
    month=11/
      part-00001.parquet
      part-00002.parquet
~~~

Registering a partition:

~~~sql
ALTER TABLE spectrum_sales.orders
ADD PARTITION (year=2026, month=11)
LOCATION 's3://company-data-lake/curated/orders/year=2026/month=11/';
~~~

If the table is managed in Glue Data Catalog, partitions can be created via Glue crawlers, Glue ETL, or APIs. Adding partitions through Redshift updates metadata in the corresponding external catalog via supported mechanisms.

### Queries Must Filter on Partition Columns

~~~sql
SELECT
    region,
    SUM(total_amount) AS revenue
FROM spectrum_sales.orders
WHERE year = 2026
  AND month = 11
  AND order_ts >= TIMESTAMP '2026-11-20 00:00:00'
  AND order_ts <  TIMESTAMP '2026-11-21 00:00:00'
GROUP BY region;
~~~

The `year` and `month` conditions drive partition pruning. The `order_ts` condition filters the exact time window inside the files. Filtering only on `order_ts` without partition predicates forces the query to inspect far more partitions.

Choose partition keys based on query patterns and cardinality. Partitioning by `customer_id` creates excessive tiny partitions; consider keeping `customer_id` inside Parquet files, leveraging sorting/encoding/statistics, or redesigning the layout.

## 7. File Formats and File Sizes

Redshift Spectrum supports multiple formats including Parquet, ORC, text, CSV, and others per service documentation. For analytical workloads, Parquet or ORC usually performs better because they are columnar formats.

| Format | Characteristics | When to Consider |
|---|---|---|
| Parquet | Columnar, column pruning, compression, broad ecosystem | Common choice for curated data lakes |
| ORC | Columnar, stripes/indexes/statistics | Hive/analytics workloads with strong benchmarks |
| CSV/Text | Easy to exchange, though usually reads more data | Small raw datasets or simple compatibility needs |
| JSON | Preserves flexible structure, though parsing can be costly | Raw events or semi-structured data |

AWS recommends using multiple files to exploit parallel processing, keeping files larger than roughly 64 MB, and avoiding wide file-size skew. This is an optimization guideline, not a hard limit; ideal sizing depends on total data volume, query concurrency, and format.

Too many small files inflate listing, metadata, and scan scheduling overhead. One oversized file can constrain parallelism if it cannot be split across scan ranges. Compact files per partition and benchmark with real queries.

## 8. Querying Spectrum Alongside Local Tables

A major advantage is joining external tables with local tables in the same Redshift SQL query. For example, a huge orders fact table resides in S3 while a small customer dimension is loaded into the warehouse:

~~~sql
SELECT
    c.customer_segment,
    o.region,
    SUM(o.total_amount) AS revenue
FROM spectrum_sales.orders AS o
JOIN public.dim_customer AS c
  ON o.customer_id = c.customer_id
WHERE o.year = 2026
  AND o.month = 11
GROUP BY c.customer_segment, o.region;
~~~

This pattern works well when large fact tables live in S3 while small, frequently accessed dimensions live in Redshift. The query optimizer can push filters or aggregations down to Spectrum before sending results back to the warehouse for joining.

Not every SQL operation is pushed down. Use `EXPLAIN` to see which parts run at the S3 layer and which run inside the cluster. When Spectrum returns massive row volumes to the cluster, the cluster can still become the bottleneck.

## 9. Predicate Pushdown and Aggregate Pushdown

Predicate pushdown executes filters close to where data resides, cutting rows sent back to the warehouse. Aggregate pushdown computes eligible aggregations at the Spectrum layer.

Pushdown-eligible operations include comparisons and pattern matching like `LIKE`, certain aggregates like `COUNT`/`SUM`/`AVG`/`MIN`/`MAX`, `GROUP BY`, and supported string functions.

Operations such as `DISTINCT` and `ORDER BY` are not pushed down under current Spectrum documentation. Therefore, do not write queries assuming the entire SQL statement executes in S3.

Example inspecting the query plan:

~~~sql
EXPLAIN
SELECT
    region,
    SUM(total_amount)
FROM spectrum_sales.orders
WHERE year = 2026
  AND month = 11
  AND total_amount > 100
GROUP BY region;
~~~

Look for nodes such as `S3 Seq Scan`, `S3 HashAggregate`, `S3 Query Scan`, `Seq Scan PartitionInfo`, and `Partition Loop`. An `S3 Seq Scan` with a filter shows conditions pushed to Spectrum; `S3 HashAggregate` indicates aggregation executed near the data source.

## 10. Optimizing Spectrum Queries

Practices that consistently deliver gains:

1. Use Parquet or ORC for curated datasets.
2. Select only needed columns; avoid `SELECT *` on wide tables.
3. Partition on frequently used predicates and filter partition columns directly.
4. Keep multiple evenly sized files to maximize parallelism.
5. Keep large fact tables in S3 and small, hot dimensions in Redshift where appropriate.
6. Push filters and aggregations down to Spectrum when supported by the engine.
7. Maintain accurate `numRows` on external tables so the optimizer plans effectively.
8. Generate column statistics in Glue Data Catalog where applicable.
9. Use materialized views over Spectrum tables for recurring workloads if refresh semantics fit.
10. Measure query plans and bytes scanned before and after changes.

Do not partition on every column used in `WHERE`. Overly granular partitions bloat metadata; overly coarse partitions weaken pruning. Base layouts on filter frequency, partition size, and ETL write patterns.

## 11. Metadata Management and Schema Evolution

Glue Data Catalog holds shared metadata across tools. Schema changes must be coordinated across writers, the catalog, and readers:

- Adding columns: verify older files lacking the column and how the engine represents missing values.
- Changing data types: check casting, precision, and Parquet/ORC compatibility.
- Renaming columns: may require compatibility views or rewriting data.
- Changing partition keys: requires coordinated layout and metadata updates.
- Changing locations: update catalog or external table locations consistently without split definitions.

For catalog-managed external tables, maintain one authoritative source for schema changes. Avoid letting Glue crawlers infer schemas unchecked from inconsistent files and unexpectedly mutate production metadata.

## 12. Spectrum and Data Manipulation Limits

An external table references external files and does not behave identically to a local Redshift table.

- `UPDATE` and `DELETE` are not supported on external tables.
- `INSERT` into external tables works only in supported configurations/formats; do not assume every external table is writable.
- External table metadata is inspected via dedicated system views such as `SVV_EXTERNAL_TABLES`, `SVV_EXTERNAL_COLUMNS`, and `SVV_EXTERNAL_PARTITIONS`.
- Without Lake Formation integration on Glue Data Catalog, user permissions on external data are typically governed at the external schema level rather than per external table.
- With a Lake Formation-enabled Data Catalog, permissions can be managed at database/table/column levels and via data filters per supported configuration.

If workloads require transactions, frequent updates/deletes, or warehouse-style constraints, load data into local Redshift tables or use a table format and engine with matching semantics.

## 13. What Is Redshift Data Sharing?

Redshift data sharing lets a producer share live access to database objects with one or more consumers—Redshift provisioned clusters or Redshift Serverless namespaces/workgroups. The unit of sharing is a datashare.

A datashare contains supported schemas, tables, views, materialized views, or functions along with granted privileges. Each datashare is bound to one source database; only objects within that database can be added.

When the producer commits changes, consumers see up-to-date data via data sharing without running ETL jobs to copy data into separate warehouses. Consumers execute queries using their own compute, allowing teams to isolate workloads and operating schedules.

~~~mermaid
flowchart LR
    subgraph Producer["Producer warehouse"]
      A[Database]
      B[Datashare]
      A --> B
    end
    subgraph Consumers["Consumer warehouses"]
      C[BI cluster]
      D[Data science workgroup]
      E[Reporting cluster]
    end
    B --> C
    B --> D
    B --> E
    C --> F[Consumer queries]
    D --> G[Consumer queries]
    E --> H[Consumer queries]
~~~

## 14. Datashares vs. Data Copying

| Criterion | ETL / Copy to Consumer | Redshift Data Sharing |
|---|---|---|
| Data | Creates an independent copy | Accesses shared objects |
| Update latency | Scheduled or sync pipeline delay | Live data; changes visible after commit |
| Storage | Duplicates data | No separate warehouse copy needed for consumers |
| Compute | Consumer queries its own copy | Consumer queries shared data using consumer compute |
| Governance | Must manage pipelines, schemas, and copy freshness | Producer manages objects and share grants; consumer manages internal privileges |
| Workload isolation | Yes | Yes, each consumer uses separate compute |
| Best suited for | Independent transforms, separate snapshots, or decoupled lifecycles | Multiple teams needing access to the same governed data |

Data sharing does not give consumers direct access to the producer's entire S3 buckets. Consumers access objects added to the datashare; for data lake tables, external catalogs and source data permissions must be properly configured.

## 15. Creating a Datashare on the Producer

Basic SQL workflow:

1. Create a datashare in the source database.
2. Add schemas to the datashare.
3. Add tables/views to share and assign corresponding privileges.
4. Add consumer namespaces or AWS accounts.
5. For cross-account sharing, perform Redshift authorization.

Example:

~~~sql
CREATE DATASHARE sales_share;

ALTER DATASHARE sales_share
ADD SCHEMA mart;

ALTER DATASHARE sales_share
ADD TABLE mart.daily_sales;

GRANT USAGE ON DATASHARE sales_share
TO ACCOUNT '222233334444';
~~~

`CREATE DATASHARE` binds the share to the currently connected database. `ALTER DATASHARE ADD SCHEMA` adds the schema to the share; it does not automatically include every object inside. `ADD TABLE` adds the object and grants default `SELECT` privileges via direct addition.

To include current and future objects in a schema, you can use scoped permissions or `INCLUDENEW` settings per Redshift documentation. Understand exact privilege scope before enabling automatic inclusion of new objects.

### Verifying Datashares

~~~sql
SELECT *
FROM svv_datashares;

SELECT *
FROM svv_datashare_objects
WHERE share_name = 'sales_share';
~~~

System views help verify which objects are included and which consumers are configured.

## 16. Producer Grants and Least Privilege

Datashares support permissions at schema, table, view, or supported function levels. Share only standardized, approved objects.

Example sharing only a reporting table:

~~~sql
CREATE DATASHARE finance_read_share;
ALTER DATASHARE finance_read_share ADD SCHEMA reporting;
ALTER DATASHARE finance_read_share ADD TABLE reporting.monthly_revenue;
GRANT USAGE ON DATASHARE finance_read_share
TO NAMESPACE 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
~~~

Adding a schema via `ALTER DATASHARE ADD SCHEMA` grants `USAGE` on that schema. Adding a table via `ALTER DATASHARE ADD TABLE` grants `SELECT` by default. You can use `GRANT` for granular privileges or scoped permissions across object groups.

Do not include staging schemas, PII tables, or unvalidated data in a share merely because they sit beside reporting tables. Use masked views or column projections when consumers do not need full tables.

## 17. Cross-Account Sharing

Sharing across AWS accounts involves two-way authorization.

**Producer:**

1. Create the datashare and add objects.
2. Add the consumer AWS account.
3. Grant `USAGE` to the account.
4. Authorize the datashare for the consumer account via console or API/CLI.
5. If writes are permitted, explicitly enable write authorization, grant proper object privileges, and ensure the consumer associates the datashare with a specific cluster/workgroup permitted to write.

Example authorizing via CLI:

~~~bash
aws redshift authorize-data-share \
  --data-share-arn "arn:aws:redshift:ap-southeast-1:111122223333:datashare:12345678-1234-1234-1234-123456789012/sales_share" \
  --consumer-identifier "222233334444"
~~~

**Consumer:**

1. Accept/receive the datashare invitation in the Redshift console.
2. Associate the datashare with the whole account, a Region, or a specific namespace.
3. Create a database from the datashare.
4. Grant internal permissions to users/roles.
5. Run queries and monitor usage.

For cross-account data sharing, both producer and consumer clusters must be encrypted. Consumers can associate at account or namespace scope depending on requirements; account-wide association extends access to current and future namespaces per configuration. For cross-account write sharing, association must target a specific cluster/workgroup configured to permit writes; authorizing the account alone is insufficient.

## 18. Creating Databases and Querying on the Consumer

Once the datashare is associated, the consumer administrator creates a database referencing the datashare.

~~~sql
CREATE DATABASE sales_shared
FROM DATASHARE sales_share
OF ACCOUNT '111122223333'
NAMESPACE 'producer-namespace-guid';
~~~

For same-account datashares, omit `ACCOUNT` and specify the producer namespace. For cross-account shares, supply both the account ID and producer namespace GUID.

After creating the database, grant access to analytics groups:

~~~sql
GRANT USAGE ON DATABASE sales_shared TO ROLE analyst_role;
~~~

If the database is created `WITH PERMISSIONS`, grant additional object-level privileges on schemas/tables as needed. Without `WITH PERMISSIONS`, users/roles with `USAGE` on the database gain access to objects inside according to datashare rules.

Querying shared data:

~~~sql
SELECT
    region,
    SUM(revenue) AS total_revenue
FROM sales_shared.mart.daily_sales
WHERE sales_date >= DATE '2026-11-01'
GROUP BY region;
~~~

Consumers can build local views or materialized views over shared data if workloads need semantic layers or local aggregations.

## 19. Cross-Region Data Sharing

Redshift supports data sharing across Regions for supported configurations and warehouse types. Consumers can associate datashares with an entire account, a Region, or a specific namespace in that Region.

Key points:

- Data remains managed by the producer; consumers query through the datashare.
- Cross-Region data transfer incurs transfer charges from the producer Region to the consumer Region.
- Both sides must meet encryption and access requirements.
- Region/namespace association governs which consumer resources can use the share.
- Query performance depends on consumer compute, network latency, and volume read.

Cross-Region sharing suits geographically distributed teams querying the same dataset. If consumers require independent snapshots, low local latency, or availability when the producer is unreachable, evaluate copy/replication pipelines instead of relying solely on datashares.

Note: sharing datashares through AWS Lake Formation carries different limitations than direct Redshift datashares. Under current documentation, cross-Region Lake Formation-managed datashares are not supported; do not extrapolate standard cross-Region datashare capabilities to that flow.

## 20. Sharing External Data Lake Tables via Datashares

Datashares are not limited to local Redshift tables. Producers can share tables from an external schema pointing to AWS Glue Data Catalog, or share late-binding views combining data lake tables with local tables.

Two main approaches:

| Approach | When Appropriate |
|---|---|
| Sharing external tables directly | Consumers need to query raw tables or join with their own local tables |
| Sharing late-binding views | Producer wants to expose a curated logical layer with selected columns, joins, or standardized schemas |

### Sharing External Tables Directly

A key requirement is that the producer's IAM role must hold `SELECT` access on the table. Once the external schema and table exist, add them to the datashare:

~~~sql
ALTER DATASHARE lake_share
ADD SCHEMA spectrum_sales;

ALTER DATASHARE lake_share
ADD TABLE spectrum_sales.orders;
~~~

The consumer associates the datashare, creates a referencing database, and queries the shared external table—optionally joining it with local consumer tables.

### Sharing Late-Binding Views

A late-binding view can combine external tables and local tables:

~~~sql
CREATE VIEW reporting.orders_enriched AS
SELECT
    o.order_id,
    o.order_ts,
    o.total_amount,
    c.customer_segment
FROM spectrum_sales.orders AS o
JOIN mart.customer_dimension AS c
  ON o.customer_id = c.customer_id
WITH NO SCHEMA BINDING;
~~~

Add the schemas containing the view and base tables to the datashare before adding the view:

~~~sql
ALTER DATASHARE lake_share ADD SCHEMA reporting;
ALTER DATASHARE lake_share ADD SCHEMA spectrum_sales;
ALTER DATASHARE lake_share ADD SCHEMA mart;
ALTER DATASHARE lake_share ADD TABLE reporting.orders_enriched;
~~~

Late-binding views are helpful when producers want to expose a stable data interface so consumers do not have to rewrite join logic between local tables and data lake tables.

## 21. Redshift Spectrum with AWS Lake Formation

AWS Lake Formation provides centralized governance for databases, tables, columns, and data filters over S3 data registered in Glue Data Catalog.

When using Redshift Spectrum with a Lake Formation-managed Data Catalog:

1. The Lake Formation administrator registers S3 locations and catalog databases/tables.
2. The administrator grants permissions to principals or roles.
3. Redshift uses an IAM role or compatible federated identity to access the catalog.
4. At query time, Lake Formation validates permissions and vends temporary credentials to Spectrum.
5. Data filters can restrict rows/columns per supported configuration.

Lake Formation avoids relying solely on bucket policies or schema-level access when multiple teams need fine-grained permissions. Verify Region availability and integration limits—for example, cell-level filters have specific restrictions, and you should not assume every Lake Formation policy applies uniformly across every datashare type.

### Lake Formation-Managed Datashares

Redshift datashares can be published to AWS Glue Data Catalog so Lake Formation manages sharing and grants to consumers. This fits organizations seeking one unified governance layer over Redshift objects.

Key points:

- The producer creates the datashare and grants usage to the Lake Formation account.
- The producer authorizes the datashare as required.
- The Lake Formation administrator discovers/registers the datashare and links it with Glue Data Catalog.
- Create a federated database and grant database/table permissions to consumer principals.
- Consumers need matching permissions in both Redshift and Lake Formation.
- Producer/consumer must meet encryption and supported warehouse requirements.

Per current documentation, cross-Region Lake Formation-managed datashares are not supported. When cross-Region sharing is required, evaluate direct Redshift datashares or appropriate data replication strategies.

## 22. Security and Auditing for Spectrum

Primary protection layers:

- Least-privilege IAM roles for S3 and Glue.
- Bucket policies restricting buckets/prefixes and principals.
- KMS key policies for objects and Glue Data Catalog when the catalog is encrypted.
- Lake Formation permissions for databases/tables/columns/rows when enabled.
- Redshift SQL privileges on external schemas and databases.
- VPC endpoints, Enhanced VPC Routing, and network paths matching warehouse architecture.
- CloudTrail to audit administrative APIs and data source access per logging capabilities.

With Enhanced VPC Routing, configure VPC endpoints for S3 and Glue so clusters access data and catalogs as required. However, with RA3 Spectrum, S3 scans are executed by a managed fleet outside the VPC; do not assume all scan traffic traverses the VPC merely because Enhanced VPC Routing is enabled.

## 23. Security and Auditing for Datashares

Producers must manage sharing permissions at two layers:

1. Which users/roles may modify datashares, add objects, or grant consumers.
2. Which consumer accounts/namespaces may access the datashare and specific objects.

Consumers must manage access to databases created from datashares for internal users/roles. Never grant `USAGE` to the entire account or `PUBLIC` if only one BI group needs the data.

Guardrails:

- Keep `PUBLICACCESSIBLE` set to `FALSE` unless explicitly justified for public clusters/workgroups.
- Share only standardized views or approved tables.
- Separate datashares by data domain and consumer group.
- Use `WITH PERMISSIONS` when object-level authorization is needed on the consumer side.
- Audit producer/consumer access, object changes, and authorizations.
- Revoke `USAGE` or associations when sharing agreements end.
- Exclude secrets or sensitive fields from views when consumers do not need them.

When using Lake Formation for row/column control, configure policies at the supported layer and test interactions with Redshift row-level/column-level security. Do not assume producer policies automatically carry over unchanged across every datashare mode.

## 24. Consumer Performance and Independence

Data sharing gives each consumer isolated compute. Heavy BI workloads on a consumer do not steal query slots from the producer the way shared-cluster queries do. Still, performance depends on:

- Consumer compute size and concurrency.
- Query complexity, joins, and aggregations.
- Data volume read from the datashare or external S3.
- Network latency and cross-Region transfers.
- Statistics, distribution/sort design, and materialized views.
- WLM or Serverless capacity configuration.

Do not treat a datashare as a pre-tuned copy optimized for every query. Consumers still need to tune SQL, inspect plans, evaluate materialized views, and size compute.

## 25. Costs to Track

Costs depend on warehouse mode, Spectrum architecture, data location, and sharing direction.

| Component | Typical Cost Bearer |
|---|---|
| Redshift producer compute | Producer account |
| Redshift consumer compute | Consumer account |
| S3 storage and S3 operations | Bucket-owning account |
| Spectrum scan on RA3 provisioned consumer | Consumer under applicable Spectrum/data-scanned pricing |
| Data lake queries on RG provisioned or Serverless | Included in corresponding compute pricing per current docs |
| Cross-Region datashare data transfer | Billed per applicable pricing for the data-receiving flow |
| Glue/Lake Formation and KMS | By usage and resource-owning account |

When a consumer queries a shared data lake table, scan charges apply to the consumer, while S3 storage and request charges stay with the bucket-owning account. Confirm Regional and warehouse-type pricing tables before budgeting.

To reduce costs:

- Partition and use Parquet/ORC to cut bytes scanned.
- Avoid `SELECT *` and filter on partition columns.
- Use materialized views for recurring queries when refresh cost is justified.
- Share column-pruned views/tables rather than entire schemas.
- Place consumers in matching Regions to avoid cross-Region transfer fees.
- Monitor query frequency and clean up unused consumer associations.
- Run heavy workloads on appropriately sized consumer warehouses.

## 26. Monitoring Spectrum and Data Lake Queries

Use system views to track partition counts, file counts, bytes scanned, and processing durations.

Example using `SYS_EXTERNAL_QUERY_DETAIL`:

~~~sql
SELECT
    query_id,
    start_time,
    duration,
    total_partitions,
    qualified_partitions,
    scanned_files,
    returned_rows,
    returned_bytes,
    file_format,
    file_location
FROM sys_external_query_detail
WHERE source_type = 'S3'
ORDER BY start_time DESC
LIMIT 20;
~~~

Key fields:

- `total_partitions`: total partitions evaluated.
- `qualified_partitions`: partitions selected by the query.
- `scanned_files`: number of files scanned.
- `returned_bytes`: for `source_type = 'S3'`, bytes scanned; for federated query sources, bytes returned.
- `duration`: segment processing time.
- `s3list_time` and `get_partition_time`: time spent listing S3 and fetching partition metadata.

On some provisioned clusters, `SVL_S3QUERY` and `SVL_S3QUERY_SUMMARY` are available. Serverless and newer warehouse versions rely more heavily on `SYS` monitoring views; choose views matching your deployment type.

## 27. Monitoring Datashares

Monitor both producer and consumer sides:

- `SVV_DATASHARES`: existing datashares and attributes.
- `SVV_DATASHARE_OBJECTS`: schemas/tables/views inside shares.
- `SVV_DATASHARE_CONSUMERS`: configured consumers.
- `SVV_REDSHIFT_DATABASES`: databases created from datashares.
- `SYS_DATASHARE_USAGE_PRODUCER` and `SYS_DATASHARE_USAGE_CONSUMER`: producer/consumer usage where supported.
- `SYS_DATASHARE_CROSS_REGION_USAGE`: cross-Region usage on supported deployments.

Beyond system views, use CloudTrail and Redshift audit logging to track privilege changes, associations, authorizations, and sensitive queries. Alert if a consumer loses association, a share is revoked, or query usage spikes unexpectedly.

## 28. Architecture Pattern: Data Lake Producer and Multiple BI Consumers

An enterprise maintains an S3 data lake, curated tables cataloged in Glue, and a producer Redshift warehouse. Finance, Sales, and Data Science each operate their own warehouses.

Design:

1. Glue Data Catalog stores curated data lake metadata.
2. Producer Redshift creates an external schema pointing to Glue catalog.
3. Producer creates external tables for fact data and local tables/views for business logic.
4. Producer creates datashares adding external tables directly or via late-binding views.
5. Producer grants consumers by namespace/account and authorizes cross-account access as needed.
6. Consumers associate datashares, create referencing databases, and grant access to analysts.
7. Consumers query shared data alongside their own local tables.
8. Lake Formation governs row/column access when centralized governance is required.

~~~mermaid
flowchart TB
    subgraph Lake["Data lake"]
      S3[Amazon S3 Parquet / ORC]
      Glue[AWS Glue Data Catalog]
      S3 --> Glue
    end
    subgraph Producer["Producer Redshift"]
      ES[External schema / Spectrum]
      RT[Local tables and views]
      DS[Datashare]
      Glue --> ES
      ES --> DS
      RT --> DS
    end
    subgraph ConsumerA["Finance consumer"]
      A[Redshift cluster]
      AQ[Finance BI]
      A --> AQ
    end
    subgraph ConsumerB["Sales consumer"]
      B[Serverless workgroup]
      BQ[Sales analytics]
      B --> BQ
    end
    DS --> A
    DS --> B
~~~

The advantage is that the producer retains control over schemas and data, while each consumer group manages its own compute and workloads independently. When data lake files update or the producer commits new data, consumers observe fresh data through the share and catalog metadata.

## 29. Comparing Data Sharing Options

| Need | Option | When Appropriate |
|---|---|---|
| Query S3 files alongside local Redshift tables | Redshift Spectrum | Combining data lake and warehouse in SQL |
| Share live Redshift tables/views between warehouses | Redshift datashare | Consumers need fresh data without copying |
| Share data lake with centralized DB/table/column/row access | Glue Data Catalog + Lake Formation | Multiple analytics services share S3 |
| Distribute data products to external subscribers | AWS Data Exchange datashare | Subscription/licensing management required |
| Create independent data copies | ETL, `UNLOAD`/`COPY`, or replication | Consumers need independent snapshots, transforms, or isolation |
| Scheduled file transfers | AWS DataSync / Glue ETL | Syncing or transforming datasets instead of direct querying |

No single service covers every sharing pattern. Choose based on data source, freshness, copy requirements, governance, Region, compute, and cost.

## 30. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| AccessDenied when querying Spectrum | Role missing S3/Glue/KMS permissions or wrong trust policy | Verify role attached to cluster/namespace, bucket/key policies, and catalog grants |
| External schema/table not found | Wrong catalog database, Region, or unregistered metadata | Check `SVV_EXTERNAL_SCHEMAS`, `SVV_EXTERNAL_TABLES`, and Glue catalog |
| Query scans too much data | Missing partition predicate, row-oriented files, or too many columns | Add partition filters, convert to Parquet/ORC, select needed columns |
| Slow query planning | Many partitions/files and large Glue metadata | Optimize partitions, catalog statistics, and layout |
| Suboptimal join plan | External table missing `numRows` or statistics | Update `TABLE PROPERTIES numRows` and inspect `EXPLAIN` |
| New partitions do not appear | Catalog or external partition metadata not updated | Register partitions via Glue/DDL/crawler |
| Consumer cannot see datashare | Producer has not granted/authorized or consumer has not associated | Check producer/consumer handshake and namespace |
| `CREATE DATABASE FROM DATASHARE` fails | Wrong account ID, namespace GUID, or share name | Verify datashare ARN and producer namespace |
| Consumer user cannot query | Missing `USAGE` on database/schema or object-level grants | Check consumer database permissions and `WITH PERMISSIONS` |
| Cross-account share fails | Producer/consumer unencrypted or missing authorization | Verify encryption, account authorization, and association |
| Cross-Region query expensive or slow | Data transfer charges and network latency | Evaluate consumer Region, materialized views, or local copies |
| Data lake table in datashare fails | Producer role lacks `SELECT` or Lake Formation missing grants | Verify IAM role, catalog, Lake Formation grants, and object metadata |

## 31. Production Checklist

- [ ] Clarified whether queried data is external S3 data or Redshift database objects.
- [ ] External schema points to the right Glue/Athena/Hive catalog and Region.
- [ ] IAM role is attached to the right cluster/namespace with least privilege.
- [ ] S3 bucket/object, KMS key, and Glue catalog policies allow access.
- [ ] External table schemas, locations, formats, and partitions match actual files.
- [ ] Partition keys reflect query patterns without excessive cardinality.
- [ ] Parquet/ORC formats, file sizes, and compression are benchmarked.
- [ ] Query plans verify predicate/aggregation pushdown where possible.
- [ ] External tables have realistic `numRows` for optimizer planning.
- [ ] Monitoring tracks bytes scanned, files, partitions, and planning time.
- [ ] Datashares contain only approved schemas/tables/views.
- [ ] Producer granted object permissions and target consumer namespaces/accounts.
- [ ] Cross-account shares are authorized and consumer-associated.
- [ ] Producer/consumer encryption meets requirements.
- [ ] Consumer databases and user/role permissions are clearly configured.
- [ ] Lake Formation is used if centralized row/column governance is required.
- [ ] Cross-Region transfer and scan charges are budgeted.
- [ ] Procedures exist to revoke shares/associations when no longer needed.
- [ ] CloudTrail/audit logs cover permission changes and data access.

## 32. Key Takeaways

Redshift Spectrum lets you query external data—typically files in S3—through external schemas and tables defined in Glue/Athena Data Catalog or a Hive metastore. IAM roles authorize reading the catalog and S3; partition pruning, Parquet/ORC, predicate pushdown, file sizing, and statistics heavily influence scan performance and cost.

Redshift data sharing uses datashares to share live database objects between producer and consumer clusters/workgroups without copying warehouse data. Cross-account sharing requires producer authorization and consumer association; cross-Region sharing incurs transfer costs. External data lake tables can also be included directly or via late-binding views when source permissions are properly configured.

Lake Formation adds centralized governance for S3 data and certain datashare flows. Production designs must separate IAM, catalog, Lake Formation, and SQL permissions while tracking bytes scanned, partitions, files, query usage, and cost. Choose Spectrum to query the data lake, datashares to distribute governed warehouse data, and combine both when delivering a shared data product.

## References

- [Amazon Redshift Spectrum Overview](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-overview.html)
- [External Schemas in Amazon Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-schemas.html)
- [External Tables for Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-tables.html)
- [CREATE EXTERNAL SCHEMA](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_SCHEMA.html)
- [CREATE EXTERNAL TABLE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_TABLE.html)
- [IAM Policies for Amazon Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-iam-policies.html)
- [Redshift Spectrum Query Performance](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-performance.html)
- [Redshift Spectrum Metrics](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-metrics.html)
- [SYS_EXTERNAL_QUERY_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_EXTERNAL_QUERY_DETAIL.html)
- [Redshift Spectrum Limitations](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-considerations.html)
- [Redshift Spectrum and AWS Lake Formation](https://docs.aws.amazon.com/redshift/latest/dg/spectrum-lake-formation.html)
- [Data Sharing in Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/datashare-overview.html)
- [Creating Datashares](https://docs.aws.amazon.com/redshift/latest/dg/datashare-creation.html)
- [CREATE DATASHARE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_DATASHARE.html)
- [GRANT for Datashare Permissions](https://docs.aws.amazon.com/redshift/latest/dg/r_GRANT.html)
- [Authorizing a Datashare](https://docs.aws.amazon.com/redshift/latest/dg/writes-authorizing.html)
- [Sharing Data Across AWS Accounts](https://docs.aws.amazon.com/redshift/latest/dg/across-account.html)
- [Associating a Datashare from a Different AWS Account](https://docs.aws.amazon.com/redshift/latest/dg/writes-associating.html)
- [CREATE DATABASE from DATASHARE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_DATABASE.html)
- [Sharing Data Across AWS Regions](https://docs.aws.amazon.com/redshift/latest/dg/across-region.html)
- [Adding Data Lake Tables to a Datashare](https://docs.aws.amazon.com/redshift/latest/dg/create-datashare-external-views.html)
- [Considerations for Sharing Data Lake Tables](https://docs.aws.amazon.com/redshift/latest/dg/considerations-datashare-datalake.html)
- [Lake Formation-Managed Datashares](https://docs.aws.amazon.com/redshift/latest/dg/lf_datashare_overview.html)
