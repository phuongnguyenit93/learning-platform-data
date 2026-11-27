# Partitioning Objectives and Oracle Version/Edition/Licensing Requirements

A transactional table can grow from a few million to billions of rows. As data grows, the questions are no longer just "does the query use an index?" but also: how to quickly eliminate irrelevant data regions, store data according to its lifecycle, remove old data without running a massive DELETE, maintain parts of a table, and keep recovery time within operational limits? Oracle **table partitioning** divides a logical table into multiple physical partitions based on one or more partitioning keys. Applications still query a single table, while Oracle can operate on only the required partitions.

Partitioning serves multiple goals: data lifecycle management, partition pruning, piecewise maintenance, support for partition-wise joins, and certain parallel strategies. However, partitioning does not automatically make every query faster. Effectiveness depends on the partition key, how queries filter data, the number and size of partitions, indexes, statistics, and execution plans.

Beyond technical design, partitioning also has **version, edition, and licensing** requirements. The fact that a database accepts the syntax or displays a feature in the data dictionary does not prove that the organization is entitled to use that feature. Specifically, in Oracle Database 19c, Partitioning is an option that must be licensed separately for Enterprise Edition; Standard Edition 2 does not provide this option. Cloud services and other contracts may have different packaging terms, so you must verify the exact product, release, edition, service, metric, and contract in use.

This lesson belongs to the **Partitioning** group of Database Engine Relational Oracle. It covers partitioning objectives, partitioning methods and key design, pruning, indexes, partition maintenance, release/edition/licensing requirements, and the pre-deployment verification process.

After this lesson, you will be able to:

- Explain why a large table needs to be partitioned and when not to partition.
- Distinguish partitioning from indexing, sharding, and manually splitting a table into multiple tables.
- Choose RANGE, INTERVAL, LIST, HASH, or composite partitioning based on data distribution and workload.
- Design a partition key to support partition pruning and data lifecycle.
- Understand local indexes, global indexes, and the impact of partition maintenance.
- Use EXPLAIN PLAN/DBMS_XPLAN to verify partition pruning.
- Manage partitions using ADD, DROP, TRUNCATE, EXCHANGE, SPLIT, MERGE, and appropriate operations.
- Identify requirements dependent on version, COMPATIBLE, and edition.
- Distinguish technical capability, feature usage, and licensing entitlement.
- Build a contract/licensing verification checklist before enabling partitioning in production.

> **Version scope:** DDL examples use Oracle Database 19c syntax. Partitioning types, limits, online operations, automation capabilities, and licensing requirements may vary by release, edition, cloud service, and contract. Consult the Licensing Information User Manual for your exact version and your organization's ordering documents before deployment.

## 1. What is Partitioning?

Partitioning divides a large table into smaller pieces called partitions based on the value of the partition key. Each partition is part of the same logical table and can be managed as an independent unit in many operations.

~~~text
APPLICATION
    |
    | SELECT ... FROM SALES
    v
LOGICAL TABLE: SALES
    |
    +-- PARTITION P2026_01
    +-- PARTITION P2026_02
    +-- PARTITION P2026_03
    +-- PARTITION P2026_04
    +-- PARTITION P2026_05
    +-- PARTITION P2026_06
~~~

The application still writes:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
~~~

Normally, there is no need to specify the partition name explicitly. The optimizer can determine which partitions may contain matching data and access only the necessary ones.

### 1.1. A partition is a management unit within a logical table

A partition is not an independent table that the application must manually UNION. A partitioned table still has:

- One table name and one set of column definitions.
- One common SQL model for queries and DML.
- Table-level constraints and metadata, along with some partition-level metadata.
- Partitions/subpartitions managed by the database.

Oracle stores partition data in corresponding segments when segments are allocated. The exact physical structure depends on tablespaces, segment creation, and the partition type.

### 1.2. Partitioning vs. indexing

| Concept | Purpose | Scope |
| --- | --- | --- |
| Index | Efficiently find rows by key/expression | An auxiliary index structure |
| Partitioning | Divide a table into independently manageable data regions | Table data organization |
| Subpartitioning | Further subdivide each partition along a second dimension | Multi-level partitioning structure |
| Sharding | Distribute data across multiple databases/shards | Multiple databases or shards |

Partitioning does not replace indexes. A query can use partition pruning first, then use a local index within the remaining partitions. Another query might scan only the required partitions using a full scan.

### 1.3. Partitioning vs. creating multiple monthly tables

Manually creating SALES_2026_01, SALES_2026_02, SALES_2026_03 and combining them with manual UNION ALL forces the application to manage:

- Which table holds which period.
- New tables for upcoming periods.
- How many tables a query must combine.
- Constraints, privileges, indexes, and statistics across tables.
- Write operations and cross-period queries.

Partitioning preserves a unified table interface and lets Oracle manage partition boundaries.

## 2. Main Objectives of Partitioning

Partitioning is not an end in itself. Choose it when one or more of the following benefits deliver practical value.

### 2.1. Data lifecycle management

This is often the strongest reason for large historical tables. For example, a SALES table holding monthly data:

- The current partition receives INSERTs.
- Prior months' partitions are mostly read-only.
- Partitions older than the retention period are archived or dropped.
- A partition can be compressed/moved according to an appropriate storage policy.

Dropping an old partition via DDL can be much more efficient than DELETEing millions of rows, because it does not generate row-by-row undo/redo in the way a large DML does. However, DROP/TRUNCATE PARTITION is a DDL operation, performs an implicit commit, and cannot be rolled back like DELETE. Always confirm the retention policy and backup before executing.

### 2.2. Partition pruning

Partition pruning is the ability to eliminate partitions that definitely cannot contain rows satisfying the predicate. If a table is partitioned by SALE_DATE and a query only requests March, Oracle can skip the other monthly partitions.

~~~text
SALES
  P_JAN   [skipped]
  P_FEB   [skipped]
  P_MAR   [READ]
  P_APR   [skipped]
  P_MAY   [skipped]
~~~

Pruning reduces the number of partitions/segments that need to be accessed. It can reduce I/O, CPU, and execution time, especially for queries with appropriate predicates on the partition key.

### 2.3. Piecewise maintenance

Instead of maintaining the entire table, the DBA can operate at the partition level:

- Truncate a partition to empty a period.
- Drop a partition whose retention has expired.
- Exchange a partition with a staging table.
- Split or merge partitions when changing boundaries.
- Move a partition to another tablespace as part of a storage plan.
- Gather statistics at the partition level when appropriate.

The capability and impact of each operation depend on the release, index types, constraints, logging, concurrency, and online options.

### 2.4. Availability and reduced maintenance scope

Some operations can limit the impact scope to the partition being modified. This helps organizations maintain old data or staging data piece by piece. However, do not assume every partition operation is online or non-blocking to queries/DML. Check the online options supported in your exact release and evaluate locks, global index maintenance, undo/redo, and execution time.

### 2.5. Partition-wise joins

If two tables are compatibly partitioned on the join key, Oracle can perform a partition-wise join: processing corresponding pairs of partitions rather than joining the entire datasets in one large region. This can reduce data communication and support parallel execution.

Partition-wise joins require compatible partitioning and join conditions. Simply having two partitioned tables does not mean Oracle will automatically use a partition-wise join.

### 2.6. Parallelism and scalability

Partitions can provide units of work for parallel query and parallel DML. Oracle can distribute work across partitions or subpartitions. However, parallel execution consumes CPU, I/O, memory, and PX resources; having many partitions does not automatically make the system faster.

### 2.7. Storage management and data policies

Different partitions can be placed in different tablespaces to support storage, backup/recovery, and lifecycle policies. For instance, recent data can reside on high-performance storage while historical data resides on lower-cost storage. Compression, ILM, and tiering features have separate technical and licensing requirements that must be verified independently.

## 3. When to Partition and When Not to Partition

### 3.1. Cases worth considering

- Very large tables where queries frequently filter on a stable dimension such as date, tenant, or data region.
- Data with a clear lifecycle, such as retaining 13 months and then archiving.
- DBAs frequently delete, load, or move data by period.
- Reports read specific periods while the table retains many years of data.
- Fact tables that can be compatibly partitioned for partition-wise joins.
- Requirements to manage backup, storage, or maintenance at the data-region level.

### 3.2. Cases where partitioning may be unnecessary

- Small tables, or queries that read nearly the entire table.
- Workloads that do not filter by the partition key.
- Small data volumes with no lifecycle management needs.
- Increasing partition count adds complexity without reducing access cost.
- The application requires lookups by keys unrelated to the partition key, causing global indexes to become a major dependency.
- The edition, license, or service in use does not allow the required feature.

There is no single row-count threshold for deciding on partitioning. A table with tens of millions of rows may need partitioning for lifecycle/time pruning; an even larger table may still gain no benefit if every query reads the entire dataset.

### 3.3. Questions to ask before designing

1. Which columns do critical queries filter on?
2. Does data grow over time or distribute by tenant/region?
3. What rules govern keeping, archiving, or deleting old data?
4. Is DML distributed evenly across partitions or concentrated in a hot partition?
5. Is a table-wide unique key required?
6. Will indexes be local or global?
7. Are partition-wise joins needed?
8. What are the database release, edition, and partitioning entitlement?
9. Do backup, replication, ETL, and migration tools support partitions?
10. Do you already have baseline execution plans and runtime metrics for comparison?

## 4. Basic Partitioning Strategies

Oracle supports multiple partitioning methods. Choose based on data semantics and access patterns, not by technical buzzwords.

### 4.1. RANGE partitioning

RANGE partitions by ordered value ranges. It is a common choice for dates, sequence numbers, or naturally ordered keys.

~~~sql
CREATE TABLE sales_range_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

Each partition accepts values strictly less than its declared upper bound. For example, P2026_01 contains dates from 2026-01-01 up to before 2026-02-01 because the preceding partition already captured all values less than 2026-01-01.

RANGE fits ordered data and range queries. You need to define a future partition or a policy for creating new partitions to prevent errors when an INSERT exceeds the highest boundary.

### 4.2. INTERVAL partitioning

INTERVAL is an extension of range partitioning that allows Oracle to automatically create the next partition when new data exceeds the transition point. It is useful for time-series data continuously loaded by month/quarter/day.

~~~sql
CREATE TABLE sales_interval_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01')
);
~~~

The first partition is an explicit range partition. When data exceeds the transition point, Oracle can create the corresponding interval partition. Partition names are system-generated by Oracle unless an appropriate naming mechanism is implemented in the design.

Interval partitioning is convenient for periodic loads, but it does not replace monitoring partition counts, retention, and release limits. Check the interval rules and supported partition key types in your target version.

### 4.3. LIST partitioning

LIST partitions by discrete values, such as region, product type, or market code:

~~~sql
CREATE TABLE customer_list_lab (
    customer_id NUMBER NOT NULL,
    region_code VARCHAR2(10 CHAR) NOT NULL,
    customer_name VARCHAR2(100 CHAR)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_east  VALUES ('EAST'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

The DEFAULT partition catches values not listed in the other partitions. It prevents insert failures when a new value appears, though it also means new data will accumulate in p_other until the DBA splits it out.

LIST is suitable when the domain of values is small and has clear business meaning. If values grow continuously or the distinct count is very large, LIST can create too many partitions.

### 4.4. HASH partitioning

HASH distributes rows across partitions based on a hash function applied to the partition key. It is suitable when relatively even data distribution is needed and there is no natural range/lifecycle.

~~~sql
CREATE TABLE event_hash_lab (
    event_id NUMBER NOT NULL,
    tenant_id NUMBER NOT NULL,
    event_time TIMESTAMP NOT NULL,
    payload CLOB
)
PARTITION BY HASH (tenant_id)
PARTITIONS 8;
~~~

HASH can help spread data and DML across multiple partitions. However, time-range queries will not automatically prune by EVENT_TIME if the partition key is TENANT_ID. Choose the key based on critical queries and data distribution.

### 4.5. Composite partitioning

Composite partitioning divides data using one method at the partition level and then subdivides each partition using another method. For example, RANGE-HASH:

~~~sql
CREATE TABLE sales_range_hash_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN (DATE '2026-04-01')
);
~~~

This example partitions by month first, then hashes by customer_id within each month. Monthly queries can prune partitions; queries within a month can leverage subpartition pruning if an appropriate predicate on customer_id is present.

Supported composite types and combinations depend on the release. Check the documentation for your exact version before using a specific method.

### 4.6. Reference partitioning

Reference partitioning allows a child table to be partitioned by its foreign key relationship to an already partitioned parent table. It is useful when child data needs to stay in the same partition as its parent record, such as order headers and order lines. The structure requires an appropriate foreign key and meets the support conditions documented by Oracle.

~~~sql
CREATE TABLE orders_parent_lab (
    order_id NUMBER PRIMARY KEY,
    order_date DATE NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

CREATE TABLE order_lines_ref_lab (
    order_id NUMBER NOT NULL,
    line_id NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT pk_order_lines_ref_lab
        PRIMARY KEY (order_id, line_id),
    CONSTRAINT fk_order_lines_ref_lab
        FOREIGN KEY (order_id)
        REFERENCES orders_parent_lab(order_id)
)
PARTITION BY REFERENCE (fk_order_lines_ref_lab);
~~~

Reference partitioning keeps child rows in the corresponding partition of the parent row via the referential relationship. Support for cascading partition maintenance operations and related restrictions must be verified for your release.

## 5. Choosing the Partition Key

Choosing the partition key is the most critical design decision. Selecting the wrong key can cause partitioning to add complexity without reducing query work.

### 5.1. Choose based on frequently used predicates

If most reports filter by SALE_DATE, range partitioning on SALE_DATE can enable pruning. If the system primarily processes per tenant and data is distributed by tenant, hash/list partitioning on TENANT_ID may be appropriate.

Inspect actual SQL statements rather than relying solely on business descriptions. A column that has business significance but does not appear in predicates, joins, or lifecycle rules may not be a good partition key.

### 5.2. Choose based on data lifecycle

If old data is archived or dropped monthly, a date/month partition key provides a natural retention unit. If old data must be deleted by tenant or region, the corresponding partition key can enable region-based operations.

### 5.3. Balance partition count and size

Partitions that are too large reduce maintenance and pruning benefits. Partitions that are too small or too numerous increase metadata, parse/optimization overhead, administrative effort, index partitions, and segment counts. There is no universal optimal partition count for all systems.

Estimate:

- Data growth rate.
- Average size per period.
- Number of periods kept online.
- Number of partitions accessed by a single query.
- Number of subpartitions per partition.
- Number of corresponding index partitions.

### 5.4. Avoid skew and hot partitions

LIST partitioning on a large tenant can cause one partition to hold most of the data. HASH can distribute more evenly, but if the key has skew or the workload concentrates on one value, certain partitions/blocks can still become hot.

Inspect row counts, storage size, and DML rates per partition. Do not look solely at the number of declared partitions and assume data is evenly distributed.

### 5.5. Partition key and unique constraints

On a partitioned table, a local unique index/unique constraint requires the partition key to be part of the unique key so Oracle can enforce uniqueness within each partition. If a table-wide unique key that does not contain the partition key is required, you may need a global unique index or an alternative key design.

For example, a SALES table partitioned by SALE_DATE where SALE_ID must be globally unique:

- A unique key `(SALE_ID, SALE_DATE)` can work with a local unique index if business semantics permit that pair.
- If only `SALE_ID` must be globally unique across the table, a global unique index on `SALE_ID` may be necessary.

This is a key trade-off: global indexes can make partition maintenance more complex. Design uniqueness and partitioning together rather than discovering at the end that the desired constraint cannot be created.

## 6. Partition Pruning

### 6.1. Static pruning

If the predicate identifies partitions from literals or bind values determinable at parse/execute time, Oracle can know in advance which partition range to access. For example:

~~~sql
SELECT SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';
~~~

With range partitioning on SALE_DATE, only the February partition needs to be read.

### 6.2. Dynamic pruning

In some queries, the partitions to access depend on values known only at runtime, such as bind variables, joins, or subqueries. Oracle can perform dynamic pruning during execution. The execution plan may represent partition start/stop as `KEY` instead of static partition numbers.

### 6.3. Predicates must be compatible with the partition key

An explicit predicate:

~~~sql
WHERE sale_date >= :start_date
  AND sale_date < :end_date
~~~

usually supports pruning better than an expression wrapping the column:

~~~sql
WHERE TO_CHAR(sale_date, 'YYYY-MM') = :month_text
~~~

Some expressions may be transformed by the optimizer or supported via function-based partitioning/virtual columns, but you should not rely on that when a clean range predicate can be written directly on the partition key.

### 6.4. Queries not filtering on the partition key

If a table is partitioned by SALE_DATE but the SQL only filters on CUSTOMER_ID, Oracle may have to access many or all partitions. A local index on CUSTOMER_ID can help within each partition, but it does not eliminate partitions on its own.

This is why the partition key must be designed around the workload. Partitioning does not automatically solve every query.

### 6.5. Viewing pruning in execution plans

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

In the plan, inspect the `PARTITION_START` and `PARTITION_STOP` columns. Numeric values or `KEY` indicate the selected partition range; how they display depends on static/dynamic pruning and the plan format.

Actual plan:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       SUM(amount)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Verify that partition pruning actually occurs and that the number of rows/buffers read matches expectations.

## 7. Local Indexes and Global Indexes

Indexes on a partitioned table can be organized as local or global. This decision affects queries, uniqueness, and partition maintenance cost.

### 7.1. Local index

A local index is partitioned identically to the table's partitions. Each table partition has a corresponding index partition. Local index partitioning is generally easier to maintain when adding, dropping, or truncating partitions.

~~~sql
CREATE INDEX ix_sales_date_local_lab
ON sales_range_lab(sale_date)
LOCAL;
~~~

A local index can be local prefixed or local nonprefixed depending on the order of index columns relative to the partition key. Locality allows each index partition to be managed alongside its table partition.

### 7.2. Global index

A global index spans multiple partitions of the table. It can support lookups by keys that do not contain the partition key and enforce table-wide unique keys.

~~~sql
CREATE INDEX ix_sales_id_global_lab
ON sales_range_lab(sale_id)
GLOBAL;
~~~

A global index is not partitioned one-to-one with each table partition the way a local index is. It can be a nonpartitioned global index or a global partitioned index depending on the design.

### 7.3. Comparing local and global

| Criterion | Local index | Global index |
| --- | --- | --- |
| Scope | Corresponds to each table partition | Spans multiple table partitions |
| Pruning | Usually fits queries that prune partitions | Can support lookups without knowing the partition |
| Partition maintenance | Usually easy to isolate by partition | May require global index maintenance/rebuild or update |
| Unique key | Local unique has rules involving the partition key | Can enforce a unique key without the partition key |
| Administration | Many index partitions | Manages table-wide scope or global partitions |

There is no universally best option. If queries always filter on the partition key and data is managed by partition, local indexes are usually easier to operate. If fast lookups on a global key that does not contain the partition key are needed, a global index may be required.

### 7.4. Global indexes and partition maintenance

DROP, TRUNCATE, EXCHANGE, or MOVE partition operations can affect global indexes. Oracle provides maintenance options, such as `UPDATE GLOBAL INDEXES` in certain operations, or options related to unusable indexes depending on the release and statement.

~~~sql
ALTER TABLE sales_range_lab
DROP PARTITION p2026_01
UPDATE GLOBAL INDEXES;
~~~

This is illustrative syntax for a release supporting the corresponding option. You must verify exact syntax, online behavior, DML impact, and index maintenance cost for your version. Do not run DROP partition without confirming retention, backups, and dependencies.

### 7.5. Index UNUSABLE

Some partition operations can leave a global index or index partition `UNUSABLE` if appropriate maintenance is not requested or performed. When an index is unusable, queries/DML relying on that index may be affected or fail depending on the situation.

After partition maintenance, check:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'SALES_RANGE_LAB';

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_RANGE_LAB'
)
ORDER BY index_name, partition_position;
~~~

If a rebuild is needed, plan resources and concurrency; do not blindly rebuild all indexes after every operation without understanding their status and cost.

## 8. Managing Partitions in the Data Lifecycle

### 8.1. Adding partitions

For a range-partitioned table with a final `MAXVALUE` partition, adding a partition in the middle requires a split or appropriate operation because `MAXVALUE` already accepts all higher values:

~~~sql
ALTER TABLE sales_range_lab
SPLIT PARTITION p_future
AT (DATE '2026-05-01')
INTO (
    PARTITION p2026_04,
    PARTITION p_future
);
~~~

This example creates the April boundary before the future partition. Specify the exact upper bound and partition names according to operational conventions.

If there is no `MAXVALUE` partition and the new value is higher than the highest existing partition, you can use `ADD PARTITION` with the appropriate syntax:

~~~sql
ALTER TABLE sales_range_lab
ADD PARTITION p2026_04
VALUES LESS THAN (DATE '2026-05-01');
~~~

### 8.2. DROP PARTITION

~~~sql
ALTER TABLE sales_range_lab
DROP PARTITION p_before_2026;
~~~

`DROP PARTITION` removes the partition and its data. This is a destructive operation, performs an implicit commit, and requires retention/backup confirmation. It is generally more efficient than `DELETE`ing all rows in a partition when the goal is to remove an entire data region.

### 8.3. TRUNCATE PARTITION

~~~sql
ALTER TABLE sales_range_lab
TRUNCATE PARTITION p2026_01;
~~~

`TRUNCATE PARTITION` empties the partition while preserving the partition structure. Use it for staging/reloads or clearing a specific period when semantics allow. It is DDL and cannot be rolled back like `DELETE`.

### 8.4. EXCHANGE PARTITION

`EXCHANGE PARTITION` swaps the data segment between a partition and a compatible non-partitioned table. This pattern is commonly used for fast staging loads:

~~~sql
ALTER TABLE sales_range_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITHOUT VALIDATION;
~~~

`WITHOUT VALIDATION` skips certain partition boundary checks; use it only when the staging data has been strictly verified to belong to the target partition. If data falls outside the range/list, it can cause data to mismatch the partition definition. Validation options, index maintenance, and online exchange depend on the release and table definition.

### 8.5. SPLIT PARTITION

`SPLIT` divides one partition into two or more partitions:

~~~sql
ALTER TABLE sales_range_lab
SPLIT PARTITION p_future
AT (DATE '2026-07-01')
INTO (
    PARTITION p2026_h1_future,
    PARTITION p_future
);
~~~

Use this when an existing partition becomes too large or boundaries need adjustment. Evaluate execution time, index maintenance, logging, and concurrent access impact.

### 8.6. MERGE PARTITIONS

`MERGE` combines adjacent partitions according to the syntax supported for the partition type:

~~~sql
ALTER TABLE sales_range_lab
MERGE PARTITIONS p2026_01, p2026_02
INTO PARTITION p2026_q1_part;
~~~

The name and range of the resulting partition must match the ordering and definition. Merging can be useful when older data only needs to be managed at a quarterly rather than monthly granularity.

### 8.7. Interval partitions and partition maintenance

Interval partitions can be created automatically when an insert exceeds the transition point. However, automatic partition creation does not automatically handle retention, statistics, tablespaces, naming, index status, or partition count monitoring. Maintain an administrative job to track created partitions and enforce data policies.

## 9. Statistics and the Optimizer on Partitioned Tables

### 9.1. Table-level and partition-level statistics

The optimizer needs statistics to estimate row counts and choose access paths. For partitioned tables, statistics can be gathered at both the table/global level and the partition level. Incremental statistics can help maintain global statistics efficiently when only new partitions change, depending on configuration and version.

### 9.2. Gathering statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_RANGE_LAB',
        granularity      => 'AUTO',
        cascade          => TRUE,
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

`GRANULARITY AUTO` lets `DBMS_STATS` choose the appropriate collection level based on the object and configuration. In production systems, follow your DBA statistics policy, incremental statistics settings, and maintenance windows.

### 9.3. Inspecting partition metadata

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    partitioning_key_count
FROM user_part_tables
WHERE table_name = 'SALES_RANGE_LAB';
~~~

Inspecting individual partitions:

~~~sql
SELECT
    partition_name,
    partition_position,
    high_value,
    num_rows,
    blocks,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_RANGE_LAB'
ORDER BY partition_position;
~~~

`HIGH_VALUE` in some dictionary views is stored as `LONG`, so SQL tools may restrict direct filtering or display. Use `DBMS_METADATA` or appropriate dictionary utilities if you need to extract DDL or ranges.

### 9.4. Checking execution plans

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sales_range_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date < DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Evaluate:

- Do `PARTITION_START`/`PARTITION_STOP` indicate only the expected range to read?
- Does `A-Rows` match the row count for the period?
- Do `Buffers` decrease compared to an unpruned query?
- Does the optimizer choose an appropriate local/global index?
- Is there an operation reading all partitions due to a predicate missing the partition key?

## 10. Oracle Version: Technical Requirements

Partitioning is a feature that has evolved across multiple releases. You cannot take syntax or capabilities from a newer release and assume an older database supports them. During design, identify the target database release and compatibility level.

### 10.1. Identifying the running release

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Or:

~~~sql
SELECT product, version, status
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

These views show the software version currently running. They do not indicate whether the organization has purchased a Partitioning license.

### 10.2. Checking COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

`COMPATIBLE` affects the database's ability to use certain new format structures and features. Upgrading binaries to a new release does not mean all new features are enabled if `COMPATIBLE` has not been raised accordingly. Changing `COMPATIBLE` requires DBA planning and is not an arbitrary operation.

### 10.3. Verifying syntax for the exact release

Before using a partition type or maintenance operation:

1. Open the SQL Language Reference / Database VLDB and Partitioning Guide for the exact release.
2. Check the `CREATE TABLE` and `ALTER TABLE` syntax for that release.
3. Check partition count limits, supported partition key types, and datatypes.
4. Check online, parallel, reference/interval/composite support.
5. Check edition and licensing conditions.
6. Test in an environment matching the production release/edition/`COMPATIBLE`.

Do not rely on a blog post or syntax from another version as the final authority for your target release.

### 10.4. Partition types and new features can differ between releases

Across Oracle generations, partitioning support has expanded: range/list/hash, composite, interval, reference partitioning, automation of certain partition types, and online/maintenance operations. Feature names, limits, syntax, and usage conditions are not identical across all versions.

Some storage management, compression, ILM, online operation, or query optimization capabilities may also depend on options other than Partitioning. Do not infer that having Partitioning entitlement includes every related option.

## 11. Edition and Licensing: Conditions You Must Verify

This section requires clearly separating three questions:

1. **Does the database release technically support the feature?**
2. **Does the edition/service in use provide that feature?**
3. **Is the organization entitled to use it under its current contract/metrics?**

These three questions are not equivalent.

### 11.1. Oracle Database 19c Enterprise Edition

For Oracle Database 19c, Oracle Partitioning is an Enterprise Edition option and requires the corresponding option license. Purchasing Enterprise Edition must not be assumed to automatically include Partitioning.

If a system runs 19c Enterprise Edition and plans to create or use partitioned tables, verify that the contract includes Partitioning entitlement for the exact deployment and metric before implementing.

### 11.2. Oracle Database 19c Standard Edition 2

Oracle Database 19c Standard Edition 2 does not provide the Oracle Partitioning option. Do not design a solution relying on table partitioning and expect to simply switch editions or flip a parameter to use it.

If the system currently runs SE2, evaluate alternatives such as indexes, archival tables, application-managed periodic tables, or a plan to migrate edition/service if partitioning is required. Each approach has its own operational trade-offs.

### 11.3. Other releases and editions

Do not extrapolate 19c requirements to every release. Edition names, products, limits, and option packaging can change over time. For releases other than 19c:

- Consult the Licensing Information User Manual for that exact release.
- Check the feature availability matrix by edition.
- Verify whether Partitioning is a separate option or included in the service/package.
- Review terms specific to cloud services, engineered systems, or custom contracts.

In particular, do not use an old version matrix to draw conclusions about entitlement for a current cloud service.

### 11.4. Metrics and licensing scope

Oracle options may be licensed by metrics such as Processor or Named User Plus depending on the contract. Do not try to derive license quantities simply from partition counts, table counts, or querying users.

You must verify:

- The metric specified in the contract.
- Processor definitions/factors if applicable.
- Named User Plus minimums if applicable.
- The number of servers/nodes/processors and environments covered by the contract.
- Rules for clustering, failover, disaster recovery, test/dev, and cloud.
- Any service- or contract-specific terms.

Do not invent a universal formula for all deployments. License scope depends on ordering documents, metrics, and specific legal terms.

### 11.5. Feature usage is not proof of entitlement

Some views/tools can display options or feature usage:

~~~sql
SELECT parameter, value
FROM v$option
WHERE parameter LIKE '%Partition%';
~~~

`V$OPTION` can show whether an option is recognized/enabled at the software level. This value **does not prove** that the organization has purchased a license.

~~~sql
SELECT name, detected_usages, currently_used,
       first_usage_date, last_usage_date
FROM dba_feature_usage_statistics
WHERE LOWER(name) LIKE '%partition%';
~~~

`DBA_FEATURE_USAGE_STATISTICS` can assist in tracking feature usage via Oracle's mechanism. It does not replace contracts, the Licensing Information User Manual, or conclusions from a license management team. Detection and recording behavior may depend on version and timing.

Do not use the SELECT queries above to declare "allowed to use" or "no license needed." This is technical diagnostic data, not a license.

### 11.6. Cloud services and bundled contracts

Some Oracle Cloud services or managed/engineered services may package usage rights under service descriptions/contracts different from on-premises installations. Check the exact SKU/service, region, deployment model, and purchased terms.

Do not assume:

- A database running in the cloud always includes every option.
- A service named Enterprise automatically includes Partitioning.
- A feature showing TRUE in `V$OPTION` means it is licensed.
- Test/dev environment entitlements automatically match production.

Use the contract and licensing documentation of the specific service as your basis.

### 11.7. Related options that must be verified separately

Partitioning does not automatically grant rights to every feature that can be used alongside partitioned tables. For example, a design might also use Advanced Compression, certain ILM/Heat Map capabilities, In-Memory, or other options. Each option must be verified against the exact release, edition, and license terms. Do not lump them all together into one "partitioning bundle."

## 12. Verification Process Before Using Partitioning

Before creating partitioned tables in an organizational environment, follow this sequence:

### Step 1 — Identify the environment

Record:

- Database product and release.
- Edition.
- On-premises, cloud service, or engineered system.
- `COMPATIBLE`.
- RAC/cluster/standby if present.
- Where DDL will run and where the feature will be used.

### Step 2 — Check feature support

Consult the SQL Language Reference, VLDB and Partitioning Guide, and Licensing Information User Manual for the exact release. Confirm the required partition type, limits, and maintenance operations.

### Step 3 — Verify entitlement

Review ordering documents, contracts, metrics, CSI/service SKU, and deployment scope. For Oracle 19c EE, verify that the Partitioning Option is licensed; for 19c SE2, do not use the Oracle Partitioning option.

### Step 4 — Verify related options

If the design also uses compression, ILM, online operations, or other options, check the requirements for each feature separately.

### Step 5 — Build a proof of concept

Test in an environment matching the production release/edition/`COMPATIBLE`:

- Partition creation DDL.
- INSERTs into partitions.
- Partition pruning.
- Local/global index behavior.
- Partition maintenance.
- Backup/restore, replication, and ETL.
- Execution plans and runtime metrics.

### Step 6 — Operational and licensing review

DBA, architect, and license manager confirm:

- Are the technical benefits measurable?
- Are maintenance/index risks acceptable?
- Is entitlement sufficient across all deployments?
- Are contract or architecture changes required?

### Step 7 — Controlled rollout

Prepare migration, backup/recovery plans, partition creation schedules, retention policies, index maintenance, statistics plans, monitoring, and rollback/contingency plans. Partition DDL performs an implicit commit; never place it inside a business transaction.

## 13. Hands-On Lab: Partition Pruning and Lifecycle

The following example uses a lab table and basic range partitioning syntax. Run it only on a database where partitioning usage has been verified to comply with release/edition/licensing.

### 13.1. Create a RANGE-partitioned table

~~~sql
CREATE TABLE sales_partition_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

### 13.2. Load data

~~~sql
INSERT INTO sales_partition_lab
VALUES (1, DATE '2026-01-05', 100, 120);

INSERT INTO sales_partition_lab
VALUES (2, DATE '2026-01-20', 101, 250);

INSERT INTO sales_partition_lab
VALUES (3, DATE '2026-02-10', 100, 80);

INSERT INTO sales_partition_lab
VALUES (4, DATE '2026-03-12', 102, 310);

INSERT INTO sales_partition_lab
VALUES (5, DATE '2026-04-01', 103, 90);

COMMIT;
~~~

### 13.3. Inspect partitions containing data

~~~sql
SELECT
    partition_name,
    partition_position,
    num_rows,
    blocks
FROM user_tab_partitions
WHERE table_name = 'SALES_PARTITION_LAB'
ORDER BY partition_position;
~~~

`NUM_ROWS`/`BLOCKS` depend on statistics. If stats have not been gathered, values may be NULL or stale.

### 13.4. Query a single month

~~~sql
SELECT sale_id, sale_date, amount
FROM sales_partition_lab
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date < DATE '2026-03-01';
~~~

Inspect the execution plan to confirm only the February partition is accessed. Because the lab dataset is small, the optimizer may choose a different scan path; focus on partition start/stop and the actual plan.

### 13.5. Query without the partition key

~~~sql
SELECT SUM(amount)
FROM sales_partition_lab
WHERE customer_id = 100;
~~~

Because the partition key is `SALE_DATE` while the predicate only filters `CUSTOMER_ID`, Oracle may have to access multiple partitions. A local index on `CUSTOMER_ID` can aid lookups within each partition, but it does not eliminate partitions on its own.

### 13.6. Add a local index

~~~sql
CREATE INDEX ix_sales_customer_local_lab
ON sales_partition_lab(customer_id)
LOCAL;
~~~

Compare the execution plan of the `CUSTOMER_ID` query before and after creating the index. Do not assume the index is always chosen; small lab tables or low-selectivity predicates may make a full scan cheaper.

### 13.7. Add a future partition

Because `p_future` uses `MAXVALUE`, use `SPLIT` to create a new partition:

~~~sql
ALTER TABLE sales_partition_lab
SPLIT PARTITION p_future
AT (DATE '2026-05-01')
INTO (
    PARTITION p2026_04,
    PARTITION p_future
);
~~~

Re-check `USER_TAB_PARTITIONS`. Understand that values less than `2026-05-01` after the March partition will go into `p2026_04`; values from `2026-05-01` onward remain in `p_future`.

### 13.8. Truncate a lab partition

~~~sql
ALTER TABLE sales_partition_lab
TRUNCATE PARTITION p2026_01;
~~~

This operation removes data in the January partition. It is DDL and cannot be rolled back like `DELETE`. Run it only after confirming the lab data can be discarded.

### 13.9. Clean up the lab table

~~~sql
DROP TABLE sales_partition_lab PURGE;
~~~

`DROP TABLE` is DDL with an implicit commit. Do not run it on production business tables.

## 14. Impact on Applications and the Data Ecosystem

Partitioning affects more than just the `CREATE TABLE` statement. Before applying it, review every dependent component:

### 14.1. SQL and applications

SQL typically still references the logical table name. However, code might be:

- Relying on `ROWID` or physical assumptions.
- Using hints specifying old indexes or access paths.
- Querying metadata to list tables.
- Running DDL incompatible with partitioned tables.
- Running batch jobs that delete data via `DELETE` instead of partition maintenance.

Verify physical assumptions and SQL hints before migration.

### 14.2. ETL and bulk loads

ETL may require staging tables, partition exchange, or direct-path inserts. Check:

- Whether data conforms to partition range/list definitions.
- Constraint validation.
- Local/global index maintenance.
- Logging and recoverability.
- Post-load statistics.
- Whether new partitions are created on schedule.

### 14.3. Backup, recovery, and standby

Partitioning changes segment administration units, but it does not replace a backup/recovery strategy. Verify RMAN, Data Guard, replication, CDC, and restore procedures with partitioned objects. A `DROP` partition operation creates a change that cannot be reversed with `ROLLBACK`; recoverability depends on backups, archivelogs, and DBA procedures.

### 14.4. Data Pump and migration

Export/import can handle partitioned tables, but you must verify source/target versions, metadata, tablespace mapping, indexes, partition definitions, and target licensing. Do not assume importing into an edition without partition support will automatically convert it into a heap table as desired.

## 15. Common Errors and Risks

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| INSERT beyond partition range fails | No partition exists to accept the new value | Add a partition/interval or `MAXVALUE` per policy |
| Query reads many partitions | Predicate does not use partition key or cannot prune | Review partition key, predicate, and execution plan |
| Index becomes unusable after maintenance | Global/local index was not properly maintained | Check index status and maintenance options |
| DROP partition causes data loss | DDL operation removes the entire partition | Confirm retention/backup and obtain approval before DDL |
| Cannot create unique constraint | Unique key does not satisfy local partitioned index rules | Consider global unique index or key/partition design |
| Too many partitions | Granularity too fine or retention too long | Re-evaluate period, subpartitions, and lifecycle |
| Data skewed into one partition | Skewed partition key or default value | Inspect data distribution, change key or strategy |
| Partition pruning does not occur | Function/conversion on key, incompatible bind/logic | Write clean predicates, check plan and datatype |
| Optimizer chooses full scan | Large result set or index/table access is more costly | Evaluate selectivity, clustering, and buffers |
| Partition DDL blocks workload | Non-online operation or requires metadata/table locks | Check release, online capability, and maintenance window |
| Technically works but lacks license | Confusing feature availability with entitlement | Halt deployment, verify contract/option |
| Syntax not supported | Release/`COMPATIBLE` does not meet requirements | Consult documentation for the exact version |

## 16. Partitioning Selection and Implementation Checklist

Before finalizing the design, verify:

**Data objectives**

- Is the table large enough or does it have a lifecycle complex enough to require partitioning?
- Do primary queries filter on the partition key?
- Can retention/archive/drop be modeled by partition?
- Are there hot partitions or skew?

**Technical design**

- Is RANGE, INTERVAL, LIST, HASH, or composite appropriate?
- Are partition boundaries complete, non-overlapping, and aligned with periods?
- Is there a future partition or a process to create new partitions?
- Do unique constraints include the partition key or is a global unique index needed?
- Which local/global indexes are needed?
- How are global indexes maintained during DROP/TRUNCATE/EXCHANGE/MOVE?
- Are partition-wise joins or parallel execution required?

**Operations**

- How are partition/global statistics managed?
- How do ETL, Data Pump, backup, standby, and CDC support it?
- Does the DDL cause implicit commits and which maintenance window is needed?
- Is monitoring in place to detect partitions nearing range limits, skew, and unusable indexes?
- Is there a recovery/reconciliation procedure after DDL operations?

**Version and licensing**

- Have release and `COMPATIBLE` been confirmed?
- Does the edition/service support partitioning?
- Has the Licensing Information User Manual for the exact release been checked?
- For Oracle 19c EE, is the Partitioning Option entitlement confirmed?
- If using Oracle 19c SE2, does the design rely on an unavailable feature?
- Have metrics, servers/nodes, cloud SKUs, and contract scope been confirmed by the license manager?
- Have related options such as Advanced Compression/ILM been verified separately?

## 17. Self-Check Questions

1. Into what units does partitioning divide a logical table?
2. How does partitioning differ from indexing?
3. Why does partitioning not automatically make every query faster?
4. What is partition pruning?
5. What types of data is RANGE partitioning suited for?
6. How does INTERVAL partitioning differ from standard RANGE partitioning?
7. What scenarios do LIST partitioning and the DEFAULT partition solve?
8. What advantage does HASH partitioning offer, and along which dimension does it not prune in the `tenant_id` hash example?
9. How does composite RANGE-HASH partitioning divide data?
10. Why must the partition key be chosen based on workload and lifecycle?
11. How do leading predicates on the partition key affect pruning?
12. How do static pruning and dynamic pruning differ in when partitions are determined?
13. How does a local index differ from a global index in scope?
14. Why can global indexes make partition maintenance more complex?
15. What kind of index might a unique key that does not contain the partition key require?
16. How does DROP PARTITION differ from DELETEing rows in terms of transaction semantics?
17. In which workflow is EXCHANGE PARTITION commonly used?
18. Why should you check index status after partition maintenance?
19. Where can BLEVEL, partition count, and statistics be viewed?
20. Why does `V$OPTION` not prove a license has been purchased?
21. Does `DBA_FEATURE_USAGE_STATISTICS` replace a license contract?
22. What is the Partitioning requirement in Oracle Database 19c Enterprise Edition?
23. Does Oracle Database 19c Standard Edition 2 provide the Oracle Partitioning option?
24. Why should the 19c license matrix not be extrapolated to every release/cloud service?
25. Which related options must be verified separately from Partitioning?

**Suggested Answers:**

1. Into partitions/subpartitions managed within the same logical table.
2. An index is an auxiliary lookup structure; partitioning divides table data into management regions.
3. Queries may not filter on the partition key, may read many partitions, or may need most of the table.
4. Eliminating partitions that definitely cannot contain matching rows.
5. Ordered values such as DATE, timestamp, or numbers.
6. Oracle can automatically create interval partitions when data exceeds the transition point.
7. LIST divides by a discrete value domain; DEFAULT catches unlisted values.
8. HASH distributes data; hashing by `tenant_id` does not automatically prune by `event_time`.
9. Divides by range at the partition level, then hashes within each partition.
10. To support actual queries, retention, and data distribution.
11. Suitable predicates allow Oracle to identify which partitions need to be read.
12. Static knows the partitions from information determinable early; dynamic determines them at runtime.
13. Local corresponds to each table partition; global spans across multiple table partitions.
14. A partition change may require updating an index structure that spans multiple partitions.
15. A global unique index may be needed if the unique key does not contain the partition key.
16. `DROP PARTITION` is DDL, performs an implicit commit, and does not roll back like `DELETE`.
17. Loading/swapping staging data into a partition.
18. Some operations can make an index or index partition unusable if maintenance is not performed.
19. `USER_PART_TABLES`, `USER_TAB_PARTITIONS`, `USER_INDEXES`, and related views.
20. It reflects software option status, not contractual entitlement.
21. No.
22. Partitioning is an option that requires separate licensing for Enterprise Edition in 19c.
23. No.
24. Edition, SKU, service, and contract terms can vary by release.
25. For example, Advanced Compression, ILM/Heat Map, In-Memory, or other options used alongside the design.

## Oracle Reference Documentation

- [Oracle Database 19c VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): concepts, partitioning strategies, pruning, indexes, and partition maintenance.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): partitioning syntax in CREATE TABLE.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): ADD, DROP, TRUNCATE, EXCHANGE, SPLIT, MERGE operations and related options.
- [Oracle Database 19c SQL Tuning Guide — Partition Pruning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-pruning.html): partition pruning and how the optimizer eliminates partitions.
- [Oracle Database 19c SQL Tuning Guide — Partition-Wise Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-wise-joins.html): conditions and benefits of partition-wise joins.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): edition, option, and feature licensing for release 19c.
- [Oracle Database Licensing](https://www.oracle.com/corporate/pricing/database-licensing.html): Oracle Database licensing information; must be cross-checked with specific contracts and service terms.
- [Oracle Database Reference — V$OPTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-OPTION.html): information about options recognized in the database.
- [Oracle Database Reference — DBA_FEATURE_USAGE_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FEATURE_USAGE_STATISTICS.html): feature usage tracking data.

**Key takeaway:** Partitioning is valuable when it solves a measurable goal: pruning unnecessary partitions, managing data by lifecycle, or maintaining part of a table. Choose the partition key based on queries and how data is retained/deleted, design local/global indexes alongside constraints, and verify pruning via execution plans. Before using it in production, verify the exact release, edition, service, and contractual entitlement. Technical capability visible inside the database does not mean the organization holds a license.
