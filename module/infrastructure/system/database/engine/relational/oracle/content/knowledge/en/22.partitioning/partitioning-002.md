# Range, List, Hash, and Interval Partitioning

Partitioning divides the data of a large table or index into smaller parts called partitions. Applications still query the table as a single logical object; Oracle manages the partitions physically and can eliminate partitions that are irrelevant to a query.

In Oracle Database, four common basic methods are:

- **Range partitioning:** partitions by ordered value ranges, commonly used for dates or numbers.
- **List partitioning:** partitions by an enumerated set of values, commonly used for region, status, or business category.
- **Hash partitioning:** Oracle applies a hash function to the partition key to distribute rows relatively evenly across partitions.
- **Interval partitioning:** extends range partitioning; Oracle automatically creates a new partition when data enters an interval that does not yet exist.

Choose the right method based on query patterns, how data grows, retention rules, and maintenance requirements. Partitioning does not automatically make every SQL statement faster. Performance benefits typically come from **partition pruning** (skipping partitions that do not need to be read), while operational benefits come from the ability to manage, load, archive, and drop data on a per-partition basis.

The examples below use Oracle 19c syntax. Partitioning is a feature subject to licensing requirements depending on the edition/offering and Oracle version; verify your environment's entitlement before deploying to production.

## 1. At What Level Does Partitioning Operate?

A partitioned table still has a single logical name:

~~~text
APPLICATION SQL
      |
      v
  SALES TABLE
      |
      +-------------------+-------------------+
      |                   |                   |
      v                   v                   v
  PARTITION P1        PARTITION P2        PARTITION P3
  older rows          current rows        future rows
~~~

Applications can run:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-02-01';
~~~

If the table is partitioned by SALE_DATE, the optimizer can read only the partitions covering the target date range. The SQL still references the SALES table; normally the application does not need to know partition names.

### 1.1. Partition key

A partition key is one or more columns Oracle uses to determine which partition a row belongs to. When designing, choose the key based on:

- Predicates that frequently appear in WHERE clauses and joins.
- How data is generated over time or by business group.
- Data deletion/archiving rules.
- Value distribution and degree of imbalance across partitions.
- Ability to maintain required unique keys, foreign keys, and indexes.

Examples:

| Table | Potentially suitable partition key | Reason |
| --- | --- | --- |
| SALES, ORDERS, AUDIT_LOG | SALE_DATE, ORDER_DATE, EVENT_TIME | Time-based queries, archiving/dropping old data |
| CUSTOMER_BY_REGION | REGION_CODE | Querying and administering by region |
| TRANSACTIONS_BY_ACCOUNT | ACCOUNT_ID with HASH | Distributing data by account when there is no natural business boundary |
| Auto-generated monthly SALES | SALE_DATE with INTERVAL | Avoiding manual creation of each time partition |

Do not choose a partition key just because a column has many distinct values. A high-cardinality key that rarely appears in query predicates may not yield useful pruning.

### 1.2. Partition pruning

Partition pruning is the optimizer's ability to skip partitions that cannot contain rows matching the query condition. This is often the largest source of performance benefit from partitioning.

For example, on a table range-partitioned by SALE_DATE:

~~~sql
SELECT COUNT(*)
FROM sales
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-02-01';
~~~

Oracle can read only the January partition. A half-open range predicate (>= start of period, < start of next period) also avoids boundary time errors when the column contains hours/minutes/seconds.

Partition pruning can be:

- **Static pruning:** the optimizer determines partitions from literals or expressions evaluable at parse time.
- **Dynamic pruning:** partitions are determined at runtime, for example from bind variables or join values depending on the execution plan.

Not every query on a partitioned table can be pruned. If predicates do not constrain the partition key, Oracle may have to read many or all partitions.

## 2. Range Partitioning

Range partitioning divides the value domain into contiguous ordered ranges. Each partition declares an **exclusive upper bound** using VALUES LESS THAN.

### 2.1. Syntax

~~~sql
CREATE TABLE sales_range (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2024
        VALUES LESS THAN (DATE '2024-01-01'),
    PARTITION p_2024_h1
        VALUES LESS THAN (DATE '2024-07-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

The partitions are interpreted as follows:

| Partition | Value range of SALE_DATE |
| --- | --- |
| P_BEFORE_2024 | Less than 2024-01-01 |
| P_2024_H1 | From 2024-01-01 to before 2024-07-01 |
| P_FUTURE | From 2024-07-01 onward |

VALUES LESS THAN is an exclusive upper bound. The date 2024-07-01 does not belong in P_2024_H1; it belongs to the next partition.

The first partition does not declare a lower bound; it accepts all values less than the first upper bound. The final MAXVALUE partition accepts values greater than or equal to the preceding bound.

### 2.2. Inserting data and partition mapping

~~~sql
INSERT INTO sales_range VALUES
    (1, DATE '2023-12-15', 101, 100);

INSERT INTO sales_range VALUES
    (2, DATE '2024-02-10', 102, 200);

INSERT INTO sales_range VALUES
    (3, DATE '2024-08-20', 103, 300);

COMMIT;
~~~

Result:

- Row 1 goes into P_BEFORE_2024.
- Row 2 goes into P_2024_H1.
- Row 3 goes into P_FUTURE.

If no partition accepts the key value, INSERT can raise ORA-14400: inserted partition key does not map to any partition. Therefore, for a range table without MAXVALUE, partitions must be created before loading data into a new domain.

### 2.3. NULLs in range partitions

With range partitioning, NULL values are treated as smaller than non-NULL values and placed into the first partition. If the partition key column is declared NOT NULL, this situation is blocked by the constraint before becoming table data.

Do not rely on NULL behavior as a substitute for business rules. If transaction date is mandatory, declare NOT NULL and handle missing data in staging.

### 2.4. Choosing partition boundaries

Boundaries should match the workload and retention cycle:

- Daily if queries/retention require day-level granularity.
- Monthly if data volume is large and business administration is monthly.
- Quarterly/yearly if data grows slowly or queries rarely need narrow ranges.

Do not create thousands of tiny partitions just because you can. Each partition adds metadata and administrative overhead; the appropriate count depends on table size, Oracle release, and workload.

### 2.5. Range pruning

~~~sql
SELECT sale_id, sale_date, amount
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';
~~~

The predicate above matches the domain of P_2024_H1, so the optimizer can eliminate the other two partitions. To verify, inspect the execution plan and the PSTART, PSTOP columns.

## 3. List Partitioning

List partitioning divides rows by **explicitly enumerated values**. This method fits when the value domain consists of discrete business groups, such as region code, product type, or status.

### 3.1. Syntax

~~~sql
CREATE TABLE customers_by_region (
    customer_id NUMBER NOT NULL,
    region_code VARCHAR2(10) NOT NULL,
    full_name   VARCHAR2(100)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north
        VALUES ('N', 'NE'),
    PARTITION p_south
        VALUES ('S', 'SE'),
    PARTITION p_central
        VALUES ('C'),
    PARTITION p_other
        VALUES (DEFAULT)
);
~~~

Each partition accepts a specific set of values. DEFAULT accepts values not listed in any other partition, which is convenient when a new code appears before a dedicated partition exists.

### 3.2. NULL and DEFAULT

In list partitioning, NULL is a value that can appear in the partition key. If NULL is not listed in a specific partition, the DEFAULT partition can accept it. If there is no DEFAULT and no partition accepts the incoming value, INSERT can raise ORA-14400.

If REGION_CODE is mandatory, declare it NOT NULL as in the example. If NULL has business meaning, decide explicitly whether it belongs in its own partition or in DEFAULT.

### 3.3. Adding new values

When a new region code appears, you can:

- Let rows go into the DEFAULT partition.
- Create a dedicated partition and move the value from DEFAULT into the new partition using an appropriate maintenance operation.

Example of adding a partition for code NW:

~~~sql
ALTER TABLE customers_by_region
SPLIT PARTITION p_other
VALUES ('NW')
INTO (
    PARTITION p_northwest,
    PARTITION p_other
);
~~~

SPLIT PARTITION splits the DEFAULT partition into a new partition for the specified value and the remaining DEFAULT partition. Verify syntax/limits for your release and ensure the partition name does not already exist.

### 3.4. List pruning

~~~sql
SELECT customer_id, full_name
FROM customers_by_region
WHERE region_code IN ('N', 'NE');
~~~

Oracle can read only P_NORTH. If the predicate does not filter on REGION_CODE, list partitioning does not automatically provide pruning benefits.

### 3.5. When should you use list?

List is suitable when value groups carry administrative meaning and are relatively stable. If new codes appear frequently, DEFAULT helps accept incoming data, but it can also accumulate too many distinct groups inside one partition. Monitor values in DEFAULT and maintain a process to reclassify them.

Do not use list partitioning for columns with millions of distinct values such as customer ID; an excessive number of groups makes the design unmanageable. When the goal is even distribution by key, consider hash partitioning.

## 4. Hash Partitioning

Hash partitioning applies Oracle's hash function to the partition key to distribute rows across partitions. The designer specifies the number of partitions; Oracle decides which row goes into which partition.

### 4.1. Syntax

~~~sql
CREATE TABLE customer_events_hash (
    event_id    NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    event_time  TIMESTAMP NOT NULL,
    payload     VARCHAR2(200)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Oracle creates eight hash partitions. Rows with the same CUSTOMER_ID map to the same partition; different customer IDs are distributed according to the hash function.

Partitions can also be named explicitly:

~~~sql
CREATE TABLE account_activity_hash (
    activity_id NUMBER NOT NULL,
    account_id  NUMBER NOT NULL,
    activity_at DATE NOT NULL
)
PARTITION BY HASH (account_id) (
    PARTITION p_h1,
    PARTITION p_h2,
    PARTITION p_h3,
    PARTITION p_h4
);
~~~

### 4.2. When is hash useful?

Hash is typically useful when:

- There is no natural range or list boundary.
- You want to distribute rows across multiple partitions to reduce data concentration.
- Queries commonly perform equality lookups on the partition key.
- You want to leverage partition-wise processing when tables are compatibly partitioned.

Hash does not order data by time or by key value. It does not replace range partitioning when you need to archive old data by month.

### 4.3. Hash pruning

~~~sql
SELECT *
FROM customer_events_hash
WHERE customer_id = 10042;
~~~

Because the predicate specifies the hash key value, Oracle can identify the relevant partition. If a query has no condition on CUSTOMER_ID, Oracle may have to read all partitions.

For a predicate filtering only on EVENT_TIME, hash partitioning by CUSTOMER_ID generally does not prune partitions by time. This is why the partition key must be chosen based on actual queries.

### 4.4. Distribution is not guaranteed to be strictly balanced

Hash improves distribution in many cases, but it does not guarantee every partition has the exact same row count or storage size. If the key is skewed—for example, one customer accounts for most transactions—that customer's rows still go to the same partition and create a hotspot.

Choose a key with suitable distribution and measure real data. The number of partitions affects parallelism, segment size, and management overhead; do not pick a large number just expecting a speedup.

### 4.5. Hash subpartitioning

Oracle also allows combining methods in composite partitioning, such as range by date followed by hash by customer. This can manage time-based lifecycle while distributing data within each time interval. Composite partitioning is an advanced design; evaluate subpartition counts, indexes, and maintenance before adopting it.

## 5. Interval Partitioning

Interval partitioning extends range partitioning for data that grows in uniform steps, such as every month or every day. The designer declares a **transition point** using initial range partitions and an interval. When new data exceeds the transition point, Oracle automatically creates the corresponding interval partition.

### 5.1. Monthly syntax

~~~sql
CREATE TABLE sales_interval (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2024
        VALUES LESS THAN (DATE '2024-01-01')
);
~~~

In this example:

- P_BEFORE_2024 is the initial range partition.
- The boundary 2024-01-01 is the transition point.
- The interval is one month.
- When inserting rows for January 2024 or later months, Oracle creates the corresponding interval partitions as needed.

Interval partitioning requires an initial range partition to establish the transition point. Interval partitions are created automatically on demand rather than pre-creating all future partitions.

### 5.2. Inserting data and auto-generated partitions

~~~sql
INSERT INTO sales_interval VALUES
    (1, DATE '2023-12-20', 101, 100);

INSERT INTO sales_interval VALUES
    (2, DATE '2024-01-15', 102, 200);

INSERT INTO sales_interval VALUES
    (3, DATE '2024-03-05', 103, 300);

INSERT INTO sales_interval VALUES
    (4, DATE '2024-03-25', 104, 400);

COMMIT;
~~~

The January and March rows go into their respective interval partitions. The two March rows go into the same March partition. Oracle normally assigns system-generated names to new interval partitions unless renamed; do not hard-code `SYS_P...` names in applications.

### 5.3. Interval partitioning does not create partitions for arbitrary old dates

Auto-generation applies to values **above the transition point**. Rows older than the transition point must still match a declared range partition. If there is only an initial partition for before 2024, rows from 2022 can go into that partition; if the older value range is not covered, INSERT can fail.

### 5.4. Data types and interval expressions

In Oracle 19c, interval partitioning uses a single partition key of type NUMBER or DATE, with a compatible interval expression. Examples:

~~~sql
-- Monthly for DATE.
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))

-- Daily for DATE.
INTERVAL (NUMTODSINTERVAL(1, 'DAY'))

-- Numeric step.
INTERVAL (1000)
~~~

Check supported column types and interval expressions for your running Oracle release. Do not use an interval expression that varies per row; the interval must define a fixed partitioning step.

### 5.5. MAXVALUE and interval

Do not declare a MAXVALUE range partition as the final partition of an interval-partitioned table. Interval partitioning needs space above the transition point so Oracle can create new partitions. Design the range section and transition point according to proper interval syntax.

### 5.6. Partition pruning on interval tables

~~~sql
SELECT SUM(amount)
FROM sales_interval
WHERE sale_date >= DATE '2024-03-01'
  AND sale_date <  DATE '2024-04-01';
~~~

Oracle can prune to the March interval partition. Querying and verifying pruning work the same way as range partitioning.

## 6. Comparing the Four Methods

| Criterion | RANGE | LIST | HASH | INTERVAL |
| --- | --- | --- | --- | --- |
| Classification method | Ordered value ranges | Enumerated set of values | Hash function on key | Auto-created range intervals by step |
| Best suited for | Dates, numbers, time | Region, status, category | Distribution by key | Uniformly growing time/numeric data |
| Partition boundaries | VALUES LESS THAN | VALUES (...), optional DEFAULT | Partition count/names | Range transition point + interval |
| Auto-creates new partitions | No | No | Not by new values | Yes, when data exceeds transition point |
| Typical pruning | Range predicates on key | Equality/IN on key | Equality/IN on hash key | Range predicates on key |
| Old data management | Very suitable | By value group | Inconvenient by time | Very suitable by interval |
| Design risks | Boundary gaps/missing partitions | DEFAULT accumulating new values | Skew/hot partitions | Interval/key/type and transition point |

### 6.1. Method selection decision tree

~~~text
Is there a natural value range rule?
       |
      YES --------------------> RANGE
       |
       NO
       v
Do values belong to clearly listed business groups?
       |
      YES --------------------> LIST
       |
       NO
       v
Need to distribute rows by hash key?
       |
      YES --------------------> HASH
       |
       NO
       v
Does data grow in uniform steps and need auto-created partitions?
       |
      YES --------------------> INTERVAL
       |
       NO
       v
Re-evaluate partition key or do not partition
~~~

If you need time-based management and row distribution within each month, consider composite RANGE-HASH or INTERVAL-HASH. Do not add subpartitions if the workload does not need them.

## 7. Querying Data and Specifying Partitions

### 7.1. Normal table queries

~~~sql
SELECT *
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';
~~~

This is the recommended approach in most applications. The optimizer automatically selects partitions based on predicates.

### 7.2. Partition extension syntax

During checks or maintenance, a partition can be specified explicitly:

~~~sql
SELECT *
FROM sales_range PARTITION (p_2024_h1);
~~~

Or identify the partition by key value:

~~~sql
SELECT *
FROM sales_interval PARTITION FOR (DATE '2024-03-15');
~~~

Partition names and PARTITION FOR are useful for specialized operations, but business applications should normally query the table using key predicates to avoid depending on partition names.

### 7.3. Reading execution plans to confirm pruning

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

In the plan, look for operations involving PARTITION RANGE or partition start/stop information:

- PSTART and PSTOP indicate the range of partitions accessed.
- Numeric values represent partition positions; KEY generally indicates pruning is determined at runtime.
- Actual plans also depend on statistics, bind variables, and the optimizer environment.

EXPLAIN PLAN shows the estimated plan. When the runtime plan and actual row counts are needed, the DBA can use appropriate cursor plan display methods, keeping in mind privileges and licensing of related features.

## 8. Managing Indexes on Partitioned Tables

Partitioned tables can use local indexes or global indexes. Index choice affects query performance, uniqueness, and partition maintenance operations.

### 8.1. Local index

A local index is partitioned in correspondence with the table's partitions. Each index partition serves only the corresponding table partition's data.

~~~sql
CREATE INDEX ix_sales_range_customer_local
ON sales_range (customer_id)
LOCAL;
~~~

Characteristics:

- Index partitions are managed alongside table partitions.
- Partition maintenance is generally easy to keep synchronized with local indexes.
- Partition pruning on the table and index can work together.
- Each index partition has a data scope matching its table partition.

### 8.2. Global index

A global index spans across table partition boundaries. It can be a nonpartitioned global index or a partitioned global index with an independent partitioning scheme.

~~~sql
CREATE INDEX ix_sales_range_sale_id_global
ON sales_range (sale_id)
GLOBAL;
~~~

Global indexes are useful when access is needed by a key that does not include the partition key, or when enforcing uniqueness across the entire table. In return, DROP/TRUNCATE/SPLIT/MERGE partition operations may require global index maintenance to avoid unusable indexes or incur update overhead.

### 8.3. Unique constraints and the partition key

A unique local index can only enforce uniqueness within each index partition. For uniqueness to be enforced across the entire table using a local unique index, the unique key must include the partition key.

For example, on a table range-partitioned by SALE_DATE:

- A unique key `(SALE_ID, SALE_DATE)` can work with a local unique index.
- A unique key on `(SALE_ID)` alone does not contain the partition key; to enforce `SALE_ID` uniqueness table-wide, a suitable global unique index/constraint is normally needed.

Do not drop a unique constraint just to use a local index. Determine whether uniqueness is table-wide or only per-partition before designing.

### 8.4. Checking index partitions

~~~sql
SELECT
    index_name,
    partitioned,
    status
FROM user_indexes
WHERE table_name = 'SALES_RANGE'
ORDER BY index_name;

SELECT
    index_name,
    partition_name,
    status
FROM user_ind_partitions
WHERE index_name = UPPER(:index_name)
ORDER BY partition_position;
~~~

For global partitioned indexes, check the status of each index partition. For nonpartitioned global indexes, inspect `USER_INDEXES.STATUS`.

## 9. Partition Maintenance

Partitioning provides administrative benefits because several operations can target a subset of data rather than the entire table. Syntax and support capabilities vary by partitioning method and release.

### 9.1. Truncating a partition

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_before_2024;
~~~

This command deletes data within the partition while keeping the partition structure. It is a destructive operation; run it only when the partition's retention has expired and approval is obtained.

### 9.2. Dropping a partition

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_before_2024;
~~~

This command removes the partition and the data inside it. If the partition contains data that must be retained, archive or exchange it before dropping.

Global indexes may need to be maintained during partition maintenance. Depending on the operation and release, the `UPDATE INDEXES` clause can be used:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_before_2024
UPDATE INDEXES;
~~~

Check syntax and index status for your Oracle release. `UPDATE INDEXES` can increase operation cost; in exchange, related indexes are maintained as specified by the statement.

### 9.3. Splitting partitions

Use split when an existing partition needs to be divided into smaller ranges, for example when a future partition is too broad:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2025-01-01')
INTO (
    PARTITION p_2024_h2,
    PARTITION p_future
);
~~~

In this example, P_FUTURE previously held all values from 2024-07-01 onward. After splitting:

- P_2024_H2 holds values from 2024-07-01 up to before 2025-01-01.
- P_FUTURE holds values from 2025-01-01 onward.

### 9.4. Adding partitions for range/list

For a range table without a MAXVALUE partition, you can add a partition at the high end:

~~~sql
ALTER TABLE sales_range_no_max
ADD PARTITION p_2025_q1
VALUES LESS THAN (DATE '2025-04-01');
~~~

If the table already has a MAXVALUE partition, you cannot add a new partition after MAXVALUE using a regular ADD; you must split the partition covering that range.

A list table can add a partition for a new set of values when those values do not already belong to another partition and the table structure permits it. If a DEFAULT partition currently accepts those values, you must split/reorganize DEFAULT using the appropriate syntax.

### 9.5. Auto-generated interval partitions

With an interval table, a new partition is created by Oracle when data requires an interval that does not yet exist. There is no need to pre-create monthly partitions. However, you must still manage:

- The number of generated partitions.
- Statistics of new partitions.
- Corresponding index partitions.
- Retention and archiving.
- Data older than the transition point.

Do not assume auto-generated partition names are stable across environments. Use metadata or `PARTITION FOR` to reference partitions by key.

### 9.6. Exchange partition

`EXCHANGE PARTITION` swaps the data segment of a partition with a structurally compatible staging table. This is a useful technique for bulk loading or archiving with brief metadata operation time compared to row-by-row bulk INSERTs.

Before exchanging, ensure:

- Column structures, data types, and attributes are compatible.
- Staging data falls within the correct partition range.
- Constraint validation is explicitly decided (`WITH VALIDATION`/`WITHOUT VALIDATION` depending on the use case).
- Indexes and dependent objects are handled according to plan.

Exchange partition is an advanced operation; do not use `WITHOUT VALIDATION` unless you have a mechanism verifying every staging row belongs to the target partition.

## 10. Row Movement When Updating the Partition Key

If an UPDATE changes the partition key such that a row must move to a different partition, Oracle requires row movement to be enabled:

~~~sql
ALTER TABLE sales_range ENABLE ROW MOVEMENT;
~~~

Only then can you execute an UPDATE that moves a row across partitions:

~~~sql
UPDATE sales_range
SET sale_date = DATE '2024-08-01'
WHERE sale_id = 2;
~~~

If row movement is not enabled, an UPDATE changing the partition key can raise ORA-14402: updating partition key column would cause a partition change. Enabling row movement allows Oracle to relocate the row; it is not a zero-cost operation and can affect `ROWID`. Applications should not treat `ROWID` as a permanent identifier across such operations.

## 11. Metadata for Tracking Partitions

### 11.1. Partitions of a current table

~~~sql
SELECT
    table_name,
    partition_name,
    partition_position,
    tablespace_name,
    num_rows,
    last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_RANGE'
ORDER BY partition_position;
~~~

`NUM_ROWS` and `LAST_ANALYZED` come from statistics and may be NULL or stale if statistics have not been gathered. Do not use `NUM_ROWS` as an exact real-time row count.

### 11.2. Table partitioning information

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    interval
FROM user_part_tables
WHERE table_name IN (
    'SALES_RANGE',
    'CUSTOMERS_BY_REGION',
    'CUSTOMER_EVENTS_HASH',
    'SALES_INTERVAL'
)
ORDER BY table_name;
~~~

### 11.3. Partition key

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_part_key_columns
WHERE name = UPPER(:table_name)
ORDER BY column_position;
~~~

The `USER_PART_KEY_COLUMNS` view shows which columns participate in the partition key. For composite partitioning, also use `USER_SUBPART_KEY_COLUMNS` and `USER_TAB_SUBPARTITIONS`.

### 11.4. Schema-wide or database-wide

Corresponding views:

| Scope | Table partition | Partition key | Index partition |
| --- | --- | --- | --- |
| Current schema | USER_TAB_PARTITIONS | USER_PART_KEY_COLUMNS | USER_IND_PARTITIONS |
| Accessible objects | ALL_TAB_PARTITIONS | ALL_PART_KEY_COLUMNS | ALL_IND_PARTITIONS |
| Entire database | DBA_TAB_PARTITIONS | DBA_PART_KEY_COLUMNS | DBA_IND_PARTITIONS |

Choose views based on required privileges. Do not grant broad DBA catalog privileges just for an application to read metadata of tables in its own schema.

## 12. Statistics and Performance

The optimizer requires statistics to estimate cardinality and choose appropriate partition access paths. After bulk loads or partition maintenance, evaluate statistics for the table, partitions, and indexes.

Example of gathering table statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_RANGE',
        granularity => 'AUTO'
    );
END;
/
~~~

`GRANULARITY => 'AUTO'` lets Oracle choose the appropriate statistics level for the partition structure. Actual policies also depend on incremental statistics, partition exchange, global statistics, and version. Do not repeatedly gather full-table statistics after every small batch without measuring the impact.

Performance factors to monitor:

- Whether partition pruning actually occurs.
- Number of partitions accessed.
- Local/global index access.
- Whether statistics are fresh enough.
- Skew across partitions.
- Parallel execution and partition-wise joins.
- Overhead of managing many partitions and index partitions.

## 13. Partition-Wise Joins

If two tables are compatibly partitioned on the join key, Oracle can perform a partition-wise join: each partition of one table is joined with the corresponding partition of the other table. This can reduce inter-process data exchange and increase parallelism.

For example, two fact/dimension tables or two transaction tables partitioned on the same key. However, partition-wise joins depend on partitioning scheme, join predicates, optimizer plans, and parallel configuration. Simply having the same number of partitions does not guarantee Oracle will use a partition-wise join.

Check the execution plan instead of assuming this technique is applied automatically.

## 14. Choosing a Partition Key and Operational Design

Before creating partitions, answer these questions:

1. Which columns do queries frequently filter on?
2. Does data have a clear time domain or value grouping?
3. Is there a need to delete/archive old data by a management unit?
4. Are key values heavily skewed?
5. Are there unique constraints that must be enforced table-wide?
6. Which indexes should be local and which need to be global?
7. Do batch loads know the target partition in advance?
8. Will new partitions be created manually or automatically?
9. Is row movement needed when updating the partition key?
10. Who monitors partition count, statistics, and index status?

### 14.1. Common starting choices

| Requirement | Starting choice |
| --- | --- |
| Filtering and archiving by day/month | RANGE or INTERVAL |
| Each region/data type code has its own group | LIST |
| Spreading load by customer/account ID | HASH |
| Monthly, but want auto-generated partitions | INTERVAL |
| Monthly and distributed by customer within each month | INTERVAL-RANGE/HASH composite depending on release and need |

### 14.2. When not to partition

Not every table needs partitioning. Small tables, tables rarely queried by the partition key, tables with no range-based data management needs, or tables where index/maintenance costs outweigh benefits may not need partitioning.

Partitioning also does not replace indexes. If a query looks up a single row by a key unrelated to the partition key, Oracle may still need a suitable index or have to check multiple partitions.

## 15. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ORA-14400 on INSERT | Partition key value matches no partition | Add/split partition or adjust transition point |
| First-of-month row enters unexpected partition | Mistaking VALUES LESS THAN for an inclusive bound | Remember the upper bound is exclusive |
| Range table missing future data domain | No matching partition or MAXVALUE | Create partitions before load or split the last partition |
| List INSERT fails on new code | Value unlisted and no DEFAULT | Add partition or use controlled DEFAULT |
| DEFAULT partition grows too large | Many new codes accumulate | Monitor new values and split/reorganize as needed |
| Hash does not help date queries | Hash key is customer/account, not date | Choose key based on predicates; consider composite range-hash |
| Hash partitions have uneven data | Key is skewed or one value dominates | Measure distribution, review key and workload |
| Interval does not auto-create partition for old data | Values lie below the transition point | Declare range partitions covering historical data |
| Invalid Interval DDL | Key/interval expression unsupported or MAXVALUE used | Check key type, interval, and release-specific syntax |
| Query still reads many partitions | Predicate does not filter partition key or expression blocks pruning | Write predicates directly on the key and inspect plan |
| Global index unusable after maintenance | Index not maintained during partition operation | Check status and use UPDATE INDEXES when appropriate |
| Unique local index cannot be created | Unique key does not include partition key | Use global unique index or redesign the key |
| UPDATE partition key raises ORA-14402 | Row movement not enabled | Enable `ENABLE ROW MOVEMENT` if business logic permits |
| Row counts in partition views inaccurate | Stale or ungathered statistics | Gather/check statistics; use COUNT for exact reconciliation |

## 16. Practice Exercises

Perform these in a dedicated lab schema. You can create the four tables from the examples in sections 2–5.

### Exercise 1 — Range boundaries

Insert dates immediately before, equal to, and immediately after each boundary. Predict which partition receives each row. Explain why the date equal to 2024-07-01 does not go into the partition ending at that date.

### Exercise 2 — Range pruning

Run a query retrieving only the first half of the year. Use `EXPLAIN PLAN` and `DBMS_XPLAN.DISPLAY` to inspect PSTART/PSTOP. Then remove the date condition and compare the number of partitions accessed.

### Exercise 3 — List DEFAULT

Insert declared region codes, a new code, and NULL. Observe which partitions receive the data. Then split DEFAULT to create a dedicated partition for the new code.

### Exercise 4 — Hash distribution

Insert many different customer IDs into the eight-partition hash table. Inspect `USER_TAB_PARTITIONS` and statistics to observe distribution. Try querying by a single customer ID and querying only by time; compare pruning.

### Exercise 5 — Interval auto-creation

Insert data spanning multiple months past the transition point. Inspect the partition list before and after INSERT. Use `PARTITION FOR` to access a partition by date without relying on system-generated names.

### Exercise 6 — Local and global indexes

Create a local index on customer ID and a global index on sale ID. Inspect `USER_INDEXES` and `USER_IND_PARTITIONS`. Discuss which index fits queries filtering on the partition key versus queries using a table-wide key.

### Exercise 7 — Row movement

Try an UPDATE that changes `SALE_DATE` and forces a row to switch partitions while row movement is disabled. Then enable row movement and run it again. Note the impact on `ROWID` and indexes.

### Exercise 8 — Planning retention

Design a transaction table retaining 36 months. Choose RANGE or INTERVAL, define the interval, transition point, local/global indexes, and how to archive/drop old partitions. Describe how to safeguard data that has not yet expired.

## 17. Cleaning Up Lab Data

Run only in the lab schema you created, after completing the exercises:

~~~sql
DROP TABLE sales_range PURGE;
DROP TABLE customers_by_region PURGE;
DROP TABLE customer_events_hash PURGE;
DROP TABLE sales_interval PURGE;
DROP TABLE account_activity_hash PURGE;
~~~

If you created `sales_range_no_max` or other lab tables, drop only the tables belonging to your practice schema. `PURGE` bypasses the recycle bin; do not use it on business tables or data that may require recovery.

## Summary

RANGE divides the key domain into contiguous intervals with exclusive upper bounds; LIST divides by declared value sets with an optional DEFAULT; HASH uses a hash function to distribute rows; INTERVAL extends RANGE and automatically creates partitions by step when data exceeds the transition point. Choose the method based on query predicates, data distribution, and lifecycle management procedures.

Partitioning pays off when the optimizer can prune partitions to read and when operations teams leverage partition-level maintenance. Verify execution plans, statistics, local/global indexes, uniqueness, and row movement. For interval partitioning, configure the transition point, partition key type, and interval expression properly. Do not create partitions merely to increase counts; a sound design must simplify queries and operations under real workloads.

## Oracle Reference Documentation

- [Oracle Database VLDB and Partitioning Guide — Partitioning Concepts (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-intro.html) — partitioning concepts and benefits.
- [Oracle Database VLDB and Partitioning Guide — Range and Interval Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — creating range/interval partitions.
- [Oracle Database VLDB and Partitioning Guide — List Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — list partitioning and DEFAULT.
- [Oracle Database VLDB and Partitioning Guide — Hash Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — hash partitioning.
- [Oracle Database VLDB and Partitioning Guide — Partition Maintenance Operations (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html) — split, merge, drop, truncate, and exchange.
- [Oracle Database Reference — USER_TAB_PARTITIONS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html) — partition metadata for the current schema.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — partitioning syntax when creating tables.

When deploying on Oracle releases other than 19c, consult the VLDB and Partitioning Guide and SQL Language Reference for your exact version, particularly regarding partition key limits, interval expressions, index maintenance, and Partitioning feature entitlement.
