# Data Partitioning and Parquet, ORC Formats

A data lake on Amazon S3 can store billions of records from transactions, applications, devices, and analytics systems. If every query had to list and read every object, processing times and scan costs would rise rapidly. Two key techniques that organize data efficiently are **partitioning** and **columnar storage**.

**Partitioning** splits a dataset into physical groups based on attributes commonly used for filtering, such as date, region, or event type. A query engine can skip irrelevant partitions instead of reading all data. **Apache Parquet** and **Apache ORC** are columnar storage formats that let engines read only the required columns and blocks while leveraging encoding, compression, and statistics to reduce I/O.

In the **CLOUD_PROVIDERS_AWS** ecosystem, these techniques are commonly used alongside Amazon S3, AWS Glue Data Catalog, AWS Glue ETL, Amazon Athena, Amazon EMR, and other analytics tools. Learners need to know how to choose partition keys, organize S3 prefixes, choose between Parquet and ORC, manage metadata, handle small files, and validate performance. The goal is to build a data lake that is scalable, easy to query, secure, and cost-controlled.

## 1. Why Partition Data?

Suppose a transactions table has 5 TB of data in S3. Users commonly query revenue for a single day or month. If the data is unpartitioned, Athena may have to read a large volume of files to find records within that time range. If the dataset is partitioned by year, month, and day, queries with time predicates can read only the matching prefixes.

Partitioning provides three main benefits:

- **Reduces data scanned:** the query engine skips partitions that do not match filter predicates.
- **Organizes data:** data is divided into manageable groups by time, tenant, region, or business domain.
- **Supports lifecycle and operations:** retention, archiving, or reprocessing can be applied per data group.

Partitioning also has costs. Too many partitions increase object counts, metadata size, and query planning time. Too few partitions force queries to read excessive unnecessary data. The goal is to select a partitioning granularity that matches actual query patterns.

## 2. What Is a Partition Key?

A partition key is an attribute used to divide a dataset into partitions. In the Hive-style layout commonly used with Athena and Glue, partition values are represented in the S3 path in `key=value` format.

Example `orders` dataset partitioned by year, month, and day:

~~~text
s3://company-data-lake/curated/orders/
  year=2026/
    month=11/
      day=20/
        part-00000.parquet
        part-00001.parquet
~~~

Partition keys can be selected from existing columns or derived during ETL. For example, from an `event_timestamp` column you can derive `year`, `month`, and `day` columns. When querying, the engine uses conditions on the partition columns to determine which prefixes to read.

### Characteristics of Good Partition Keys

- Appear frequently in query filter conditions.
- Have low or moderate cardinality.
- Divide data into sufficiently large groups.
- Change infrequently and follow clear standardization rules.
- Align with retention and data ingestion patterns.

Day, month, region, event type, or business unit are usually good candidates. User ID, order ID, or session ID typically have cardinality too high to serve as primary partition keys.

## 3. Cardinality and the Trade-off Between Too Many and Too Few Partitions

Cardinality is the number of distinct values of an attribute. When partitioning by day, one year has about 365 values. When partitioning by `customer_id` with millions of customers, the number of partitions can grow into the millions.

| Design | Common Consequence |
|---|---|
| Unpartitioned | Queries may scan large amounts of data; minimal partition metadata |
| Partition by year | Few partitions, but daily queries still read large amounts of data |
| Partition by year/month/day | Useful for time-range queries, though partition count grows over time |
| Partition by customer_id | High cardinality, creating many small partitions and large metadata |
| Partition by date and region | Can be balanced if queries frequently filter by both attributes |

There is no universal optimal partition count for every dataset. Estimate partition counts based on retention period, distinct values per key, and average data volume per partition.

For example, if one day has only 20 MB of data yet creates thousands of partitions by customer, the system will generate many small files. Metadata, listing, and scheduling overhead can outweigh the benefit of partition pruning.

## 4. Choosing Partition Keys by Query Pattern

Do not pick a partition key solely because a column exists in the schema. Analyze common queries:

| Query Pattern | Partition Keys to Consider |
|---|---|
| Daily revenue reports | year, month, day |
| Country-level analysis | country or region |
| Event type tracking | event_type if the number of types is bounded |
| Business unit reporting | business_unit if unit count is moderate |
| Specific customer lookups | Not necessarily partitioned by customer_id; consider bucketing, sorting, or appropriate indexing |
| Combined time and region | year/month/day + region if combination count and partition size are reasonable |

A practical workflow:

1. Collect query logs and identify frequently used predicates.
2. Rank attributes by filter frequency and expected data reduction.
3. Estimate cardinality and data size per partition.
4. Build a test layout on a representative dataset.
5. Run benchmarks with realistic queries.
6. Monitor partition counts, file counts, and query planning times.

If users commonly query a 7-day window and a region, partitioning by date and region may be useful. However, if each day has hundreds of very small regions, consider partitioning only by date and using sort/order or bucketing for region.

## 5. How Does Partition Pruning Work?

Partition pruning is the process where a query engine eliminates unnecessary partitions based on query predicates. For example, a table has partition keys `year`, `month`, and `day`; a query filtering a single day can read only the matching prefix.

~~~sql
SELECT
    region,
    SUM(total_amount) AS revenue
FROM curated_orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
GROUP BY region;
~~~

If the table is properly partitioned and metadata is ready, Athena can read only data inside the partition for year 2026, month 11, day 20. If a query filters only on `event_timestamp` without filtering on the partition keys, a Hive-style table does not automatically infer the relationship between the timestamp and the partition keys. In that case, the query may read more partitions than necessary.

For example, if `event_timestamp` falls within November 20 and the table is partitioned by `year/month/day`, the query should include both the partition predicates and the timestamp predicate:

~~~sql
SELECT COUNT(*)
FROM curated_orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
  AND event_timestamp >= TIMESTAMP '2026-11-20 10:00:00'
  AND event_timestamp <  TIMESTAMP '2026-11-20 12:00:00';
~~~

The timestamp predicate guarantees accurate business logic; the partition predicates allow Athena to eliminate irrelevant prefixes.

### Partition Keys in Glue/Athena Commonly Use the STRING Type

AWS recommends using the `STRING` type for partition keys in Hive-style tables in Athena to optimize partition processing. Values such as year, month, and day can still be represented as zero-padded strings, e.g., `month='03'`. Original business columns can retain separate `DATE` or `TIMESTAMP` types.

## 6. Managing Partition Metadata with AWS Glue Data Catalog

AWS Glue Data Catalog stores metadata for databases, tables, schemas, locations, and partitions. Athena uses this metadata to determine which files belong to a table and which partitions to read.

There are multiple ways to manage partitions:

- Create partitions using the Glue API or Athena DDL.
- Use an AWS Glue crawler to discover schemas and partitions.
- Use CTAS to create a table and partitions at the same time.
- Use partition projection in Athena to compute partitions from table properties instead of registering each partition.

Crawlers are convenient for data discovery, but are not always the best option for production pipelines. When schemas and layouts are known, managing metadata explicitly in ETL or via the Glue API can be easier to control.

### MSCK REPAIR TABLE

For Hive-style partition layouts, Athena provides `MSCK REPAIR TABLE` to discover new partitions in S3 and add metadata to the Glue Data Catalog.

~~~sql
MSCK REPAIR TABLE curated_orders;
~~~

This command has limitations:

- Can take a long time when there are many prefixes.
- Primarily adds new partitions; does not automatically remove metadata for old partitions deleted from S3.
- Can scan subdirectories and accidentally detect partitions from other datasets if prefixes are shared.
- Has limitations regarding case sensitivity and S3 path structure.

For large datasets, consider managing partitions via the Glue API, controlled crawlers, partition indexes, or partition projection instead of running `MSCK REPAIR TABLE` frequently.

## 7. Glue Partition Indexes and Partition Projection

When a table has tens of thousands or more partitions, retrieving metadata from the Glue Data Catalog can become a significant portion of query planning time. AWS provides two mechanisms to distinguish:

| Mechanism | How It Works | When Appropriate |
|---|---|---|
| Glue partition index | Creates an index on partition keys to filter a subset of partitions in the Data Catalog | Tables with registered partitions where `GetPartitions` needs optimization |
| Athena partition projection | Declares partition rules/ranges in table properties so Athena computes partitions itself | Datasets with clear partition patterns, especially when partition counts are large |

### Glue Partition Index

A partition index is created on an ordered list of partition keys. When `GetPartitions` has a matching expression that uses the leading key of the index, Glue can retrieve a subset of partitions instead of loading the entire list. Up to three partition indexes can be created per table according to current Glue documentation.

For Athena, partition filtering must be enabled on the table via table properties:

~~~sql
ALTER TABLE curated_orders
SET TBLPROPERTIES ('partition_filtering.enabled' = 'true');
~~~

The index must be in `ACTIVE` state, and queries/filters must align with the key order. This optimizes metadata retrieval; it does not change how data files are partitioned on S3.

### Partition Projection

Partition projection lets Athena compute partition values and locations from table properties. For example, a table has `year` from 2020 to 2030, `month` from 01 to 12, and `day` from 01 to 31. Athena can determine the required partitions without calling Glue `GetPartitions` to fetch a registered list.

Projection can reduce metadata retrieval time and eliminate manual partition registration. However, when projection is enabled, Athena ignores partition metadata registered in the Glue Data Catalog for that table. Configured ranges and templates must match the S3 layout.

Projection can perform poorly on sparse datasets, where many projected partition combinations do not actually contain data. Therefore, do not enable projection solely because partition counts are high; benchmark against actual query patterns.

## 8. How Does Partitioning Differ from Bucketing?

Partitioning splits data into directories/prefixes by partition key values. Bucketing splits data into a fixed number of buckets based on a hash of one or more columns.

| Criterion | Partitioning | Bucketing |
|---|---|---|
| Splitting method | By key value, typically creating separate prefixes | By hash, with a configured number of buckets |
| Cardinality | Should be low or moderate | Can use higher-cardinality columns |
| Goal | Eliminate irrelevant data groups before reading files | Distribute data, aiding certain joins/parallel processing |
| S3 layout | Typically `key=value` directories | Files written by bucket ID within a partition |
| Example | `year=2026/month=11` | Bucketed by `customer_id` into 32 buckets |

Do not create partitions for every `customer_id` just to speed up customer queries. You can partition by date and then bucket by `customer_id` if the engine and workload benefit. Athena supports bucketing in certain formats/table types, though you must check current compatibility and CTAS limits.

For Iceberg tables, partition transforms such as `year(timestamp)`, `month(timestamp)`, `day(timestamp)`, and `bucket(column, n)` are declared through Iceberg's partitioning mechanism; do not treat Hive `partitioned_by` as identical to Iceberg partitioning.

## 9. The Small Files Problem

A dataset with millions of small files often queries slower than expected even if total data volume is small. Every file adds overhead for listing, metadata, open/close, scheduling, and footer processing. With columnar formats, overly small files also reduce the benefits of row groups or stripes.

Common causes:

- Streaming or micro-batch pipelines continuously writing files with overly small batches.
- Too many partitions, where each partition holds only a few MB of data.
- ETL writing as many files as workers without compaction.
- Frequent `INSERT INTO` runs generating many small files.

AWS Athena documents a default Parquet block/row-group size of 128 MB and ORC stripe size of 64 MB. These are internal structural sizes, not a strict requirement that every file equal those exact numbers. Target file sizes typically need benchmarking; analytical datasets usually benefit from files large enough to reduce overhead without becoming so large that parallelism suffers.

### Mitigations

1. Batch records before writing.
2. Use appropriate Spark `repartition`/`coalesce` before writing.
3. Compact small files per partition.
4. Avoid high-cardinality partitioning.
5. Monitor average file counts per partition.
6. Use Iceberg compaction or data file rewrite mechanisms if the table format supports them.

Do not compact the entire data lake on every data load. Process only affected partitions or time ranges to control cost and avoid rewriting data unnecessarily.

## 10. What Are Columnar Storage Formats?

Row-oriented formats store all fields of a record together. Columnar formats store values by column or column group. For analytical queries that typically read only a subset of the schema, columnar storage can reduce the amount of data read and decompressed.

Example `orders` table with columns:

| order_id | customer_id | order_date | region | total_amount | status |
|---|---|---|---|---:|---|
| O-001 | C-01 | 2026-11-20 | north | 120.50 | PAID |
| O-002 | C-02 | 2026-11-20 | south | 75.00 | PENDING |
| O-003 | C-03 | 2026-11-20 | north | 240.00 | PAID |

A query needs only `region` and `total_amount`. With a columnar format, the engine can read the corresponding column chunks instead of decompressing `order_id`, `customer_id`, `order_date`, and `status`.

Benefits:

- Column pruning: reads only columns requested by the query.
- Column-wise compression: values of the same type tend to have similar patterns and compress well.
- Encoding: dictionary, run-length, or delta encoding can reduce size.
- Statistics: min/max, null counts, or other metadata help skip non-matching blocks.
- Predicate pushdown: filter conditions can be applied near the storage read layer to reduce I/O.

## 11. What Is Apache Parquet?

Apache Parquet is an open columnar storage format widely used across Spark, Hadoop, Athena, Glue, Trino, and many other analytics tools. Parquet is designed to store schemas and data by column groups, supporting compression and encoding.

### Parquet Structure

A Parquet file typically consists of:

- **Row groups:** groups of rows in the file; each row group contains data for multiple columns.
- **Column chunks:** data for a single column within a row group.
- **Pages:** units of data and encoding inside a column chunk.
- **File metadata/footer:** schema, row group/column chunk offsets, statistics, and other metadata.

~~~mermaid
flowchart TD
    A[Parquet file] --> B[File metadata / Footer]
    A --> C[Row group 1]
    A --> D[Row group 2]
    C --> E[Column chunk: order_id]
    C --> F[Column chunk: region]
    C --> G[Column chunk: amount]
    E --> H[Pages]
    F --> I[Pages]
    G --> J[Pages]
~~~

When a query needs only `region` and `amount`, the engine can skip the `order_id` column chunk. Statistics in the footer or row group metadata can help skip data groups that do not satisfy predicates.

### When Is Parquet Appropriate?

- Datasets need to be shared across multiple query engines and frameworks.
- Analytical workloads commonly project a subset of columns from wide schemas.
- Strong compatibility with Spark, Athena, Glue, EMR, and other tools is needed.
- Complex schemas or nested data require interoperability.
- A balance of compression, scan performance, and ecosystem support is desired.

## 12. What Is Apache ORC?

Apache ORC (Optimized Row Columnar) is a columnar format developed in the Hadoop/Hive ecosystem. ORC organizes data into stripes, with indexes and statistics to support selective reads, compression, and predicate filtering.

### ORC Structure

An ORC file typically consists of:

- **Stripes:** groups of rows stored in columnar layout.
- **Index data:** information used to locate and skip unnecessary data.
- **Data streams:** encoded/compressed column data streams.
- **Stripe footer:** metadata for each stripe.
- **File footer and postscript:** schema, stripe list, compression, and file-level metadata.

~~~mermaid
flowchart TD
    A[ORC file] --> B[Postscript]
    A --> C[File footer]
    A --> D[Stripe 1]
    A --> E[Stripe 2]
    D --> F[Stripe index]
    D --> G[Column data streams]
    D --> H[Stripe footer]
    E --> I[Stripe index]
    E --> J[Column data streams]
    E --> K[Stripe footer]
~~~

ORC maintains multi-level indexes and statistics so engines can identify which stripes or regions to read. In certain workloads, ORC can produce smaller files and faster queries than Parquet; results depend on schema, compression, engine, and queries.

### When Is ORC Appropriate?

- Workloads rely heavily on Hive or the Hadoop ecosystem.
- Datasets contain complex types such as `struct`, `map`, and `list`.
- Benchmarks show ORC reduces storage size or scan times better.
- ETL tools and query engines in the organization fully support ORC.

## 13. Comparing Parquet and ORC

| Criterion | Parquet | ORC |
|---|---|---|
| Storage layout | Columnar | Columnar |
| Core structure | Row groups, column chunks, pages | Stripes, indexes, data streams |
| Metadata | Footer with schema, row group, and column metadata | File footer, stripe footer, indexes, and postscript |
| Compression | Supports multiple codecs depending on writer/reader | Supports multiple codecs depending on writer/reader |
| Predicate pushdown | Yes, based on statistics and metadata | Yes, based on indexes and statistics |
| Ecosystem | Broad, popular in Spark, Arrow, and many engines | Strong in Hive/Hadoop and ORC-supporting engines |
| Complex/nested types | Supports nested schemas | Supports struct, map, list, and complex types |
| File size | Depends on data and codec | Can often be smaller in certain workloads |
| Selection | Often a safe default when broad interoperability is needed | Choose when the ecosystem or benchmarks show an advantage |

Neither format wins in every case. AWS Athena notes that ORC often creates smaller files and ORC indexes can accelerate queries, while Parquet supports a wide range of queries and broad compatibility. Benchmark on real data rather than choosing based on format reputation or a generic benchmark.

## 14. Compression and Encoding

Compression reduces the bytes stored in S3 and the bytes read before decompression. Encoding leverages data characteristics to represent values more efficiently before or alongside compression.

Examples:

- Dictionary encoding: stores repeated values as integer codes and a dictionary.
- Run-length encoding: stores sequences of identical values as the value and repeat count.
- Delta encoding: stores differences between steadily increasing/decreasing values.
- Bit packing: stores integers using only the minimum required bits.

### Common Codecs in Athena

| Format | Codecs Usable When Writing via Athena CTAS | Notes |
|---|---|---|
| Parquet | GZIP, SNAPPY, ZSTD per current writer support | GZIP is the traditional CTAS default; check engine/properties when using ZSTD |
| ORC | LZ4, SNAPPY, ZLIB, ZSTD | ZLIB is the ORC CTAS default |

Stronger compression generally reduces storage and bytes scanned but can increase CPU during compression/decompression. Snappy typically favors speed; GZIP/ZLIB can deliver higher compression ratios; ZSTD can balance speed and compression ratio. Results depend on data, cardinality, and engine.

Never use a codec that writers and readers in your pipeline do not jointly support. Athena can read some Parquet codecs such as LZ4/LZO, but does not support writing Parquet with those codecs according to current documentation.

## 15. Schema Evolution

Data lakes often evolve schemas over time: adding columns, changing types, renaming columns, modifying nested structures, or adding enum values. Parquet and ORC store schemas in file metadata, so schema evolution must be managed carefully.

Common changes:

| Change | Risk | Mitigation |
|---|---|---|
| Adding a nullable column | Old files lack the new column | Verify how engines return NULL for old files |
| Changing numeric type | Precision loss or cast errors | Use tested migrations and control precision |
| Renaming a column | Readers may treat it as a new column | Use aliases/views or planned rewrites |
| Modifying nested structures | Different readers may handle it differently | Version schemas and test cross-engine |
| Changing timestamp timezone | Time shifts or partition mismatches | Standardize on UTC and explicit conversion rules |

Do not assume every schema change is backward compatible. Maintain a schema registry or metadata contract, test readers/writers, and plan how older files are handled. For Hive-style tables, the Glue Data Catalog schema may need separate updates; the catalog schema and actual file schemas must remain consistent per engine rules.

## 16. Choosing Partitions and Formats Together

Partitioning and columnar formats optimize two different layers:

- Partitioning reduces the number of prefixes or file groups considered.
- Columnar formats reduce the columns and blocks read within selected files.

Example query for daily revenue in one region:

~~~sql
SELECT region, SUM(total_amount)
FROM orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
  AND region = 'north'
GROUP BY region;
~~~

Partitioning by date reduces the folders read. Parquet/ORC allows the engine to read only `region` and `total_amount`, while using statistics to skip non-matching row groups/stripes.

Do not partition on every column in `WHERE`. A high-cardinality column may perform better inside the files so engines can filter via statistics or bucketing. The design must balance partition counts, file sizes, and pruning effectiveness.

## 17. Creating a Parquet Partitioned Table Using Athena CTAS

Athena CTAS can convert CSV/JSON data to Parquet, compress it, and partition it in a single query.

Example where source `raw_orders` has columns `order_id`, `event_timestamp`, `region`, and `total_amount`:

~~~sql
CREATE TABLE curated_orders_parquet
WITH (
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day'],
    external_location = 's3://company-data-lake/curated/orders-parquet/'
)
AS
SELECT
    order_id,
    event_timestamp,
    region,
    total_amount,
    CAST(year(event_timestamp) AS VARCHAR) AS year,
    LPAD(CAST(month(event_timestamp) AS VARCHAR), 2, '0') AS month,
    LPAD(CAST(day(event_timestamp) AS VARCHAR), 2, '0') AS day
FROM raw_orders;
~~~

Important notes:

- Partition columns must appear at the end of the `SELECT` list in the exact order declared in `partitioned_by`.
- Athena CTAS limits creation to 100 partition/bucket combinations per query. If data exceeds this limit, split into multiple batches or use an appropriate ETL workflow.
- `external_location` must be an S3 prefix containing no existing target data per CTAS rules.
- Database/table names and locations must follow organizational conventions.
- The query above is illustrative; verify data types and date functions for your engine version.

After CTAS finishes, Athena creates the files and registers table/partition metadata in the Glue Data Catalog.

## 18. Creating an ORC Partitioned Table Using Athena CTAS

To write the same dataset as ORC:

~~~sql
CREATE TABLE curated_orders_orc
WITH (
    format = 'ORC',
    write_compression = 'ZSTD',
    partitioned_by = ARRAY['year', 'month', 'day'],
    external_location = 's3://company-data-lake/curated/orders-orc/'
)
AS
SELECT
    order_id,
    event_timestamp,
    region,
    total_amount,
    CAST(year(event_timestamp) AS VARCHAR) AS year,
    LPAD(CAST(month(event_timestamp) AS VARCHAR), 2, '0') AS month,
    LPAD(CAST(day(event_timestamp) AS VARCHAR), 2, '0') AS day
FROM raw_orders;
~~~

CTAS uses `write_compression` to specify the codec. For ORC, `ZLIB` is the default if unspecified; for Parquet, `GZIP` is the default per Athena CTAS documentation. You can use `SNAPPY` or `ZSTD` when appropriate and supported by the writer.

Do not write Parquet and ORC into the same prefix. Each table should have its own location so crawlers or query engines do not accidentally read files of another format.

## 19. Querying and Verifying Partition Pruning

Queries should filter partition keys directly:

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_orders_parquet
WHERE year = '2026'
  AND month = '11'
  AND day BETWEEN '01' AND '07'
GROUP BY region;
~~~

Check the partition list:

~~~sql
SHOW PARTITIONS curated_orders_parquet;
~~~

Inspect the query plan or query execution details in Athena to verify bytes scanned and selected partitions. Compare against a query without partition predicates to measure the reduction in data scanned.

### Avoid Ineffective Predicates

If partition keys are `year/month/day` strings, do not filter only on an expression over the raw timestamp and expect Athena to infer partitions automatically. Add corresponding partition predicates. Ensure consistent value formatting—for example, always zero-pad months to two digits so `'2'` and `'02'` do not split into two separate partitions.

## 20. Partition Projection for Time-Series Datasets

For time-series datasets with predictable patterns, partition projection can reduce metadata overhead. For example, a table has `year` from 2024 to 2030, `month` from 01 to 12, and `day` from 01 to 31.

Illustrative table properties:

~~~sql
ALTER TABLE curated_orders_parquet
SET TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2024,2030',
  'projection.month.type' = 'integer',
  'projection.month.range' = '1,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '1,31',
  'projection.day.digits' = '2',
  'storage.location.template' = 's3://company-data-lake/curated/orders-parquet/year=${year}/month=${month}/day=${day}/'
);
~~~

The properties above are illustrative configuration examples; the template must match the actual layout and partition types/ranges exactly. Projection computes nonexistent partition combinations as well, so it can be inefficient for sparse or irregular datasets. When projection is enabled, Athena ignores partition metadata registered in the Glue Catalog for that table.

## 21. AWS Glue ETL and File Compaction

AWS Glue ETL can read raw data, standardize schemas, generate partition columns, and write Parquet/ORC to S3. With Spark, account for DataFrame partitions, output file counts, and data distribution.

Illustrative PySpark example:

~~~python
from pyspark.sql import functions as F

source = spark.read.json("s3://company-data-lake/raw/orders/")

curated = (
    source
    .withColumn("event_date", F.to_date("event_timestamp"))
    .withColumn("year", F.date_format("event_date", "yyyy"))
    .withColumn("month", F.date_format("event_date", "MM"))
    .withColumn("day", F.date_format("event_date", "dd"))
    .select(
        "order_id",
        "event_timestamp",
        "region",
        "total_amount",
        "year",
        "month",
        "day"
    )
)

(
    curated
    .repartition("year", "month", "day")
    .write
    .mode("append")
    .format("parquet")
    .option("compression", "snappy")
    .partitionBy("year", "month", "day")
    .save("s3://company-data-lake/curated/orders/")
)
~~~

The example must be adapted to your Glue version, Spark configuration, and data volume. Calling `repartition` on keys can trigger heavy shuffles or skew; do not apply it blindly. You can repartition by target file count, use `coalesce` when reducing partitions, and handle hot keys separately.

### Compaction

A compaction job can read small files over a time window, merge them into larger files, and rewrite that partition. Avoid having jobs read and write to the same prefix while queries are running if there is a risk of exposing inconsistent intermediate states. Use a staging prefix and a controlled publish/replace workflow when needed.

## 22. Partition Pruning, Projection, and Indexes: Which Mechanism to Choose?

| Scenario | Mechanism to Consider |
|---|---|
| Table has a few hundred or a few thousand partitions | Standard partition pruning is usually sufficient |
| Glue `GetPartitions` is slow on registered partitions | Glue partition indexes and partition filtering |
| Partitions follow a continuous, predictable pattern | Athena partition projection |
| Sparse dataset where many projected combinations lack data | Consider indexes or explicit partition metadata management |
| Partition keys are missing from predicates | Fix queries or review layout; projection does not replace filter predicates |
| Too many files inside each partition | Compact files; indexes/projection do not solve small files |

Partition pruning still takes place when partition projection is enabled. Projection only changes how Athena retrieves/defines partition metadata. Glue partition indexes optimize metadata filtering inside the Data Catalog; they do not compress files or reduce file counts.

## 23. Choosing Parquet or ORC in AWS

A selection process:

1. Identify query engines: Athena, Spark, Hive, EMR, Trino, or multiple engines.
2. Analyze schema: flat vs. nested, column count, data types, and schema change frequency.
3. Analyze query patterns: column projection, filters, joins, and aggregations.
4. Create two sample copies in Parquet and ORC using equivalent compression.
5. Run the same query suite on the same engine version and configuration.
6. Compare bytes scanned, execution time, CPU, memory, and storage size.
7. Verify interoperability between writers and readers.

Parquet is typically a good default when broad compatibility is needed. ORC is worth testing when workloads rely on Hive or benchmarks show storage/index gains. If the organization has already standardized on one format and performance meets SLOs, do not switch formats just to follow trends.

## 24. Data Lake Layout and Data Zones

A data lake can be organized into zones:

| Zone | Goal | Common Formats |
|---|---|---|
| Raw/Bronze | Keep data close to source for replay and auditing | JSON, CSV, Avro, or raw source formats |
| Curated/Silver | Standardize schema, data types, quality, and partitioning | Parquet or ORC |
| Analytics/Gold | Datasets serving BI, dashboards, and business queries | Parquet, ORC, or table formats like Iceberg |

Not every zone needs to use the same format. Raw can preserve original data for reprocessing; curated and analytics typically use columnar formats to reduce scans and cost.

For datasets requiring updates/deletes, transactions, time travel, or schema/partition evolution, evaluate table formats such as Apache Iceberg. Parquet and ORC are file formats; Iceberg is a table format managing metadata, snapshots, and data files. The two concepts complement each other rather than compete directly.

## 25. Security and Governance for Partitioned Data Lakes

Partition paths can expose sensitive information such as tenant, region, or business unit. Do not treat S3 prefixes as the sole security boundary.

Controls to enforce:

- Least-privilege IAM policies and S3 bucket policies.
- AWS Lake Formation to manage database, table, column, and row-level filtering where appropriate.
- KMS encryption and key policies.
- Glue Data Catalog permissions and resource links for cross-account sharing.
- CloudTrail to audit catalog, bucket, and query operations.
- Tags and ownership for databases/tables/partitions.
- Retention, lifecycle, and data deletion policies.

If a partition key contains a tenant ID, define per-tenant data access controls. Including a `tenant_id` predicate in queries does not prevent a user from removing the predicate and reading another tenant's data. Enforce proper governance controls rather than relying on query conventions.

## 26. Athena Query Performance and Cost

Under per-query pricing, Athena charges primarily by the amount of data scanned. Partitioning and columnar formats can reduce bytes scanned:

- Partition pruning skips unnecessary prefixes.
- Columnar projection reads only columns requested by the query.
- Compression reduces bytes stored and read.
- Statistics/predicate pushdown can skip non-matching row groups or stripes.
- Appropriate file sizes reduce metadata overhead and improve parallelism.

However, too many partitions or small files can increase planning time. Heavy compression can increase decompression CPU. Queries that do not filter on partition keys can scan large volumes of data even on a partitioned table.

Monitor:

- Data scanned per query.
- Query planning time and execution time.
- Number of partitions selected.
- File counts and average file size.
- Bytes read and compression ratio.
- Glue `GetPartitions` latency.
- Schema/SerDe errors and corrupt files.

Optimization must balance scan costs against ETL/compaction/catalog operational costs.

## 27. Design Example: Transactional Data Lake

An enterprise ingests 500 GB of events per day. BI commonly queries revenue by date, region, and product category; the data science team occasionally analyzes `customer_id` across multiple months.

### Initial Proposed Design

- Raw: store original JSON by ingestion date for replay.
- Curated: normalize timestamps to UTC, use decimal types for currency, apply schema versioning and deduplication.
- Partition curated by `year/month/day`; consider adding `region` if region count is small and queries frequently filter by region.
- Use Parquet with Snappy or ZSTD after benchmarking.
- Keep `customer_id` inside files; do not partition by `customer_id` due to high cardinality.
- Compact small files per daily partition.
- Glue Data Catalog stores schemas and partitions; use projection or partition indexes if metadata becomes a bottleneck.
- Athena queries must include `year/month/day` predicates; customer-level analytical queries can use bucketing or a dedicated layout if benchmarks prove beneficial.

### Data Flow Diagram

~~~mermaid
flowchart LR
    A[Application events] --> B[S3 Raw JSON]
    B --> C[AWS Glue ETL]
    C --> D[Schema validation and dedup]
    D --> E[Partition by date / optional region]
    E --> F[Parquet or ORC files]
    F --> G[Glue Data Catalog]
    G --> H[Amazon Athena]
    G --> I[Amazon EMR / Spark]
~~~

### Validation

1. Select one representative week of data.
2. Produce two curated versions: Parquet and ORC.
3. Run the identical BI query suite.
4. Compare bytes scanned, planning time, execution time, and file sizes.
5. Test daily queries, regional queries, and multi-month `customer_id` queries.
6. Scale to one month and evaluate partition counts, file counts, and Glue metadata.
7. Choose the appropriate layout/format and document the rationale in the architecture.

## 28. Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Query scans excessive data despite partitioned table | Missing predicate on partition key or mismatched key | Add partition predicates; verify S3 paths and table metadata |
| New partitions not visible | Glue metadata not updated | Use Glue API, crawler, or `MSCK REPAIR TABLE` within appropriate scope |
| Slow query planning | Too many partitions causing slow `GetPartitions` | Use Glue partition index/filtering or partition projection |
| Slow projection queries | Sparse dataset, overly wide range, or wrong template | Narrow ranges, benchmark, consider explicit metadata |
| Very high file count | Small micro-batches or high-cardinality partitioning | Compact files and revisit partition keys |
| One partition is huge | Overly coarse partition key or hot key | Add a reasonable-cardinality key or bucketing |
| Query cannot read Parquet/ORC | Schema mismatch, unsupported codec, or corrupt file | Verify writer version, schema, and compression support |
| Wrong data after schema change | Incompatible reader/writer | Version schemas, apply controlled casts, and rewrite if needed |
| CTAS reports too many open partitions | Single query creates more than 100 partition/bucket combinations | Split CTAS/`INSERT INTO` into multiple batches |
| Month partition split into `'2'` and `'02'` | Unstandardized partition values | Use zero-padding and fix metadata/layout |
| Glue crawler alters schema unexpectedly | Crawler infers schema from inconsistent files | Define explicit schemas, classifiers, and schema change policies |

## 29. Partitioning and Columnar Format Design Checklist

- [ ] Analyzed query patterns and common predicates.
- [ ] Partition keys have appropriate cardinality and sufficiently large partition sizes.
- [ ] S3 prefixes follow a consistent convention without mixing datasets.
- [ ] Partition keys use `STRING` type with standardized values.
- [ ] Queries include predicates on partition keys to leverage pruning.
- [ ] Partition counts and file counts are monitored.
- [ ] A Glue Catalog partition registration strategy is in place.
- [ ] Evaluated Glue partition indexes or Athena partition projection when metadata grows large.
- [ ] Projection templates/ranges fit the layout and dataset sparsity.
- [ ] Benchmarked Parquet and ORC on representative data and queries.
- [ ] Compression codecs are supported by all writers and readers in the pipeline.
- [ ] Row group/stripe and file sizes are not overly small.
- [ ] Compaction jobs exist for small files while avoiding unnecessary full-dataset rewrites.
- [ ] Schema evolution has versioning and cross-engine testing.
- [ ] Retention, lifecycle, encryption, IAM, and Lake Formation are configured.
- [ ] Monitored bytes scanned, planning time, execution time, and ETL cost.

## 30. Key Takeaways

Partitioning divides datasets into prefixes based on attributes commonly used for filtering. Choose partition keys with reasonable cardinality, sufficiently large partition sizes, and alignment with query patterns. Partition pruning skips irrelevant prefixes; Glue partition indexes and Athena partition projection optimize metadata retrieval in different scenarios.

Parquet and ORC are columnar formats that reduce data read via column pruning, compression, encoding, statistics, and predicate pushdown. Parquet has a broad ecosystem; ORC often offers advantages in certain Hive/analytics workloads and can produce smaller files. Only benchmarking on real data and queries determines the right format.

A solid design combines partitioning, file sizing, schemas, compression, Glue metadata, and governance. Avoid overly high partition cardinality, small files, schema drift, and queries missing partition predicates. Track bytes scanned, planning time, and ETL costs to maintain predictable data lake performance as data grows.

## References

- [Partition Your Data - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/partitions.html)
- [What Is Partitioning? - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/ctas-partitioning-and-bucketing-what-is-partitioning.html)
- [Use Partition Projection with Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html)
- [Optimize Data - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-data-optimization-techniques.html)
- [Optimize Tables and File Sizes - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-s3-throttling-optimizing-your-tables.html)
- [Use Columnar Storage Formats - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html)
- [Use Compression in Athena](https://docs.aws.amazon.com/athena/latest/ug/compression-formats.html)
- [Create a Table from Query Results (CTAS)](https://docs.aws.amazon.com/athena/latest/ug/ctas.html)
- [CTAS Examples](https://docs.aws.amazon.com/athena/latest/ug/ctas-examples.html)
- [CTAS Considerations and Limitations](https://docs.aws.amazon.com/athena/latest/ug/ctas-considerations-limitations.html)
- [Use CTAS and INSERT INTO for ETL and Data Analysis](https://docs.aws.amazon.com/athena/latest/ug/ctas-insert-into-etl.html)
- [Work Around the 100 Partition Limit](https://docs.aws.amazon.com/athena/latest/ug/ctas-insert-into.html)
- [AWS Glue Partition Indexes](https://docs.aws.amazon.com/glue/latest/dg/partition-indexes.html)
- [Optimize Athena with Glue Partition Indexing and Filtering](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices-partition-index.html)
- [AWS Glue Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
