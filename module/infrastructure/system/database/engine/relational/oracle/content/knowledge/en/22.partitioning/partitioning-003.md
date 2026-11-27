# Composite Partitioning and Choosing Subpartitions in Oracle

Partitioning divides a large table into smaller pieces to manage and access data efficiently. With **composite partitioning**, Oracle divides a table into two levels: partitions at the outer level and subpartitions at the inner level. The partition level usually represents a major division dimension such as time or region; the subpartition level further subdivides each partition along another dimension such as customer, sales region, or hash key.

Choosing the right subpartition key and subpartitioning method can help queries eliminate additional unnecessary data regions, distribute data and I/O appropriately, and support lifecycle data management. Choosing poorly can create too many subpartitions, increasing metadata and maintenance overhead while queries still have to read large amounts of data.

This lesson explains the two-level structure, common composite partitioning types, how to create RANGE-HASH and RANGE-LIST tables, subpartition templates, partition pruning/subpartition pruning, local/global indexes, metadata, and criteria for choosing subpartitions based on workload.

## 1. What Are Partitions and Subpartitions?

Partitioning divides a logical table into separately managed parts. Applications still query one table by its table name; Oracle determines which partition or subpartition to access based on query conditions and partitioning metadata.

In a composite-partitioned table:

- **Partition** is the first-level division.
- **Subpartition** is the second-level division inside each partition.
- **Partition key** determines the partition.
- **Subpartition key** determines the subpartition within the corresponding partition.

For example, a sales transaction table can be divided along two dimensions:

1. Partition level by quarter of sale date.
2. Subpartition level by HASH of customer ID.

~~~text
SALES_FACT
|
+-- P2025_Q1
|   +-- SP1 (hash customer)
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q2
|   +-- SP1
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q3
|   +-- SP1
|   +-- SP2
|   +-- SP3
|   +-- SP4
|
+-- P2025_Q4
    +-- SP1
    +-- SP2
    +-- SP3
    +-- SP4
~~~

The illustration above shows four subpartitions per partition. With four partitions and four subpartitions per partition, the table has 16 subpartitions in total.

### 1.1. Partitioning does not create multiple independent tables

Partitions and subpartitions belong to the same logical table:

~~~sql
SELECT *
FROM sales_fact
WHERE sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-04-01';
~~~

There is no need to manually UNION individual partitions. The optimizer can perform partition pruning to access only the relevant partitions.

### 1.2. Two levels address two division dimensions

| Level | Design question | Example |
|---|---|---|
| Partition | Which major group is data managed by? | Sales quarter, fiscal year, region |
| Subpartition | Within each major group, which dimension requires further subdivision? | Customer, hash key, region, transaction type |

Two levels are not mandatory just because a table is large. If a single partitioning key already supports pruning and maintenance well enough, adding subpartitions may only increase complexity.

## 2. How Does Composite Partitioning Work?

Composite partitioning applies one partitioning method at the outer level and another subpartitioning method at the inner level. Common combinations include:

- RANGE-HASH: partitions by value range, subpartitions by hash.
- RANGE-LIST: partitions by value range, subpartitions by value list.
- RANGE-RANGE: partitions by one range, subpartitions by another range.
- LIST-HASH: partitions by list, subpartitions by hash.
- LIST-RANGE: partitions by list, subpartitions by range.
- LIST-LIST: both levels divide by list.
- HASH-HASH: both partitions and subpartitions use hash.

Oracle supports many composite partitioning combinations; syntax and specific capabilities may depend on the version. During design, confirm which partitioning types are supported in your target database version.

### 2.1. RANGE-HASH

The outer level uses RANGE, typically on a date or sequence number. The inner level uses HASH, typically on customer_id, account_id, or a distribution key.

Suitable when:

- Data has a time-based lifecycle.
- Queries frequently filter by time ranges.
- Within each time period, data needs to be distributed across multiple regions to reduce I/O concentration or aid management.
- Queries often include both time conditions and the hash key.

Example: sales data by quarter, further split into eight hash subpartitions by CUSTOMER_ID.

### 2.2. RANGE-LIST

The outer level divides by range, and the inner level divides by list. For example:

- Partition by quarter.
- Subpartition by REGION_CODE: NORTH, CENTRAL, SOUTH, and OTHER.

Suitable when each time period needs to be separated into finite, well-defined business groups with group-based query requirements.

### 2.3. RANGE-RANGE

The outer level divides by one range, and the inner level divides by a second range. For example:

- Partition by ORDER_DATE.
- Subpartition by SHIP_DATE.

Suitable when both time dimensions are meaningful for querying or management. Ensure subpartition ranges within each partition are designed consistently with the data and business boundaries.

### 2.4. LIST-HASH

The outer level divides by category groups such as REGION_CODE or BUSINESS_UNIT; the inner level uses HASH to distribute data across a high-cardinality key.

Suitable when the number of partition groups is finite, yet each group still holds large data volumes that need even distribution by a key.

## 3. Choose the Partition Key First, Then the Subpartition Key

A practical design approach starts with data management and common query questions:

1. Along which dimension is data inserted?
2. On what cycle is old data archived, compressed, or deleted?
3. Which columns do queries frequently filter on?
4. Is there a second key that helps narrow the data region read inside a partition?
5. Is data distribution needed to avoid concentrating data in one area?

Example table FACT_SALES:

| Attribute | Value |
|---|---|
| Row count | Hundreds of millions |
| New data | Continuously appended by SALE_DATE |
| Reporting queries | Filter by SALE_DATE ranges |
| Customer queries | Filter by CUSTOMER_ID within a time range |
| Lifecycle | Quarterly data is archived or dropped after retention |

One option could be RANGE(SALE_DATE) at the partition level and HASH(CUSTOMER_ID) at the subpartition level. The partition key addresses time filtering and lifecycle; the subpartition key subdivides customer data within each quarter.

Do not choose CUSTOMER_ID as the partition key solely because the application searches by customer if retention, archiving, and dropping rules are primarily time-based. In that case, outer-level RANGE by date usually fits the data lifecycle better.

## 4. Preparing a RANGE-HASH Lab Table

We create a sales table:

- SALE_DATE: sale date, partition key.
- CUSTOMER_ID: customer ID, subpartition key.
- SALE_ID: transaction ID.
- REGION_CODE: sales region.
- AMOUNT: transaction amount.

The example uses quarterly RANGE and HASH on CUSTOMER_ID with four subpartitions per partition.

### 4.1. Create the table

Run in a lab schema inside a practice PDB. If a table with the same name already exists, use a different schema or name; do not overwrite active data.

~~~sql
CREATE TABLE lab_sales_fact (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    region_code  VARCHAR2(12 CHAR) NOT NULL,
    amount       NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_sales_amount CHECK (amount >= 0)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p2025_q1 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_q2 VALUES LESS THAN (DATE '2025-07-01'),
    PARTITION p2025_q3 VALUES LESS THAN (DATE '2025-10-01'),
    PARTITION p2025_q4 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

With RANGE partitioning, the first partition receives all values less than the first boundary. In this example, P2025_Q1 receives dates before 2025-04-01; PMAX receives dates from 2026-01-01 onward. During real implementation, declare boundaries so that date ranges and partition names accurately reflect business periods.

Each partition has four hash subpartitions on CUSTOMER_ID.

### 4.2. Insert sample data

~~~sql
INSERT INTO lab_sales_fact (
    sale_id,
    sale_date,
    customer_id,
    region_code,
    amount
)
SELECT
    LEVEL,
    DATE '2025-01-01' + MOD(LEVEL, 365),
    MOD(LEVEL * 37, 10000) + 1,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'CENTRAL'
        ELSE 'SOUTH'
    END,
    MOD(LEVEL * 19, 100000) / 100
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;
~~~

### 4.3. Create a local index

~~~sql
CREATE INDEX ix_lab_sales_customer
ON lab_sales_fact (customer_id)
LOCAL;
~~~

A LOCAL index is divided according to the table's partitioning structure. On a composite-partitioned table, the local index is likewise organized along the table's partitions and subpartitions. Local indexes are generally favorable for partition-level maintenance and can support queries within each partition.

### 4.4. Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => USER,
        tabname     => 'LAB_SALES_FACT',
        cascade     => TRUE,
        granularity => 'ALL'
    );
END;
/
~~~

Statistics help the optimizer estimate row counts and costs for partition pruning, subpartition pruning, and access paths. Statistics collection policies may differ across environments; do not run manual gathers on production without reviewing DBA policies.

## 5. RANGE-LIST and Subpartition Templates

With RANGE-LIST, the outer level divides by time and the inner level divides by a region list. A subpartition template defines the same subpartition structure for every created partition.

### 5.1. Create the table

~~~sql
CREATE TABLE lab_sales_region (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    region_code  VARCHAR2(12 CHAR) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY LIST (region_code)
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_north   VALUES ('NORTH'),
    SUBPARTITION sp_central VALUES ('CENTRAL'),
    SUBPARTITION sp_south   VALUES ('SOUTH'),
    SUBPARTITION sp_other   VALUES (DEFAULT)
)
(
    PARTITION p2025_q1 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_q2 VALUES LESS THAN (DATE '2025-07-01'),
    PARTITION p2025_q3 VALUES LESS THAN (DATE '2025-10-01'),
    PARTITION p2025_q4 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Oracle applies the template to each partition. Every partition gets subpartitions for NORTH, CENTRAL, SOUTH, and OTHER. When adding new time partitions, the template ensures a consistent subpartition structure is created.

### 5.2. Why use a template?

Without a template, you may have to declare subpartitions inside each partition individually. With many monthly/quarterly/yearly partitions, repeating configurations easily leads to omissions or inconsistencies across partitions.

Templates help:

- Maintain the same subpartition list across partitions.
- Assign recognizable subpartition names.
- Define DEFAULT for unlisted region values.
- Simplify adding new partitions.

### 5.3. Insert data and inspect

~~~sql
INSERT INTO lab_sales_region VALUES
  (1, DATE '2025-01-10', 'NORTH', 101, 1200);
INSERT INTO lab_sales_region VALUES
  (2, DATE '2025-02-11', 'SOUTH', 102, 900);
INSERT INTO lab_sales_region VALUES
  (3, DATE '2025-04-05', 'CENTRAL', 103, 1500);
INSERT INTO lab_sales_region VALUES
  (4, DATE '2025-05-20', 'WEST', 104, 700);
COMMIT;
~~~

WEST has no dedicated subpartition, so it goes into the DEFAULT subpartition SP_OTHER within the corresponding time partition.

## 6. Partition Pruning and Subpartition Pruning

Pruning is Oracle's elimination of partitions or subpartitions that do not need to be accessed based on query conditions.

- **Partition pruning**: eliminates outer-level partitions.
- **Subpartition pruning**: further eliminates inner-level subpartitions.

The goal is to reduce the number of data regions read, thereby reducing I/O and processing work.

### 6.1. Condition only on the partition key

On the RANGE-HASH table by SALE_DATE and CUSTOMER_ID:

~~~sql
SELECT COUNT(*)
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01';
~~~

Oracle can access only partition P2025_Q2. Since there is no condition on CUSTOMER_ID, all hash subpartitions inside this partition may need to be examined.

### 6.2. Conditions on both the partition key and subpartition key

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;
~~~

Oracle can:

1. Prune partitions outside Q2/2025.
2. Within the remaining partition, prune hash subpartitions that do not correspond to CUSTOMER_ID = 1234.
3. Access matching entries/rows in the selected subpartition.

This is the clearest two-level utilization case: the time predicate narrows the partition, and the customer predicate narrows the subpartition.

### 6.3. Condition only on the subpartition key

~~~sql
SELECT COUNT(*)
FROM lab_sales_fact
WHERE customer_id = 1234;
~~~

Oracle can prune subpartitions by hash key within each partition, but it still has to examine the time partitions because there is no condition on SALE_DATE. Subpartition pruning does not automatically eliminate outer partitions.

### 6.4. Unsuitable predicates can limit pruning

Conditions written directly on the partition key usually make it easier for the optimizer to determine ranges:

~~~sql
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date < DATE '2025-07-01'
~~~

Avoid applying unnecessary functions to the partition key:

~~~sql
-- May make pruning harder depending on expression and transformation capability:
WHERE TO_CHAR(sale_date, 'YYYY-MM') = '2025-04'
~~~

Use half-open date ranges instead of converting date columns to strings. If business requirements truly demand querying by an expression, consider appropriate virtual column/function-based partitioning and verify the plan.

## 7. Pruning with RANGE-LIST

On table LAB_SALES_REGION, querying by time and region:

~~~sql
SELECT sale_id, sale_date, region_code, amount
FROM lab_sales_region
WHERE sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-04-01'
  AND region_code IN ('NORTH', 'SOUTH');
~~~

Oracle can prune:

- Partitions by SALE_DATE range, leaving only P2025_Q1.
- Subpartitions by LIST REGION_CODE, leaving only SP_NORTH and SP_SOUTH.

If there is only a REGION_CODE condition without SALE_DATE:

~~~sql
SELECT COUNT(*)
FROM lab_sales_region
WHERE region_code = 'NORTH';
~~~

Oracle can select the NORTH subpartition inside each partition, but it still considers all time partitions that may hold data.

## 8. Reading Execution Plans to Verify Pruning

### 8.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PARTITION +PREDICATE +COST +NOTE'
    )
);
~~~

In the plan, inspect the PSTART and PSTOP columns along with operations related to table/index access. For partitioned objects, Oracle can display the accessed partition/subpartition range or symbols indicating dynamic pruning.

### 8.2. Static and dynamic pruning

- **Static pruning**: the optimizer identifies partitions to access from literals or information known at parse time.
- **Dynamic pruning**: partitions are determined at runtime, for example when values come from bind variables, joins, or expressions known only at execution.

The plan may display specific PSTART/PSTOP values or a symbol like KEY for dynamic pruning, depending on the access path and version.

### 8.3. Viewing runtime statistics

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       sale_id, sale_date, customer_id, amount
FROM lab_sales_fact
WHERE sale_date >= DATE '2025-04-01'
  AND sale_date <  DATE '2025-07-01'
  AND customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +COST'
    )
);
~~~

ALLSTATS LAST displays actual statistics from the most recent execution if collected. Compare E-Rows and A-Rows, buffers, reads, and elapsed time. EXPLAIN PLAN alone only shows the estimated plan and does not prove actual runtime behavior.

## 9. How Should You Choose the Subpartition Key?

The subpartition key must serve a clear goal. Key criteria include:

### 9.1. Queries have predicates on the subpartition key

If most queries always filter by CUSTOMER_ID, subpartitioning by HASH(CUSTOMER_ID) can help Oracle prune subpartitions when appropriate equality conditions are present.

If the application frequently filters REGION_CODE with a small list, LIST subpartitioning may fit.

If queries need a second range of values, RANGE subpartitioning can help eliminate irrelevant ranges.

Do not pick a key just because a column seems important. Look at the actual predicates in frequently executed SQL statements.

### 9.2. Cardinality and data distribution

HASH generally fits high-cardinality keys requiring relatively even distribution. LIST fits finite, business-meaningful groups. RANGE fits ordered values with range queries.

| Subpartition method | Key characteristics | Typical use cases |
|---|---|---|
| HASH | High cardinality, needs distribution | CUSTOMER_ID, ACCOUNT_ID |
| LIST | Finite, meaningful groups | REGION_CODE, CHANNEL_CODE |
| RANGE | Ordered, range queries | SHIP_DATE, EVENT_DATE, numeric tiers |

### 9.3. Data balance

HASH can distribute rows across subpartitions based on the hash key. This is useful when you do not want a popular value to create an oversized subpartition as can happen when splitting by LIST business groups.

LIST can create uneven subpartition sizes if one group contains most of the data. Measure distribution before deciding.

RANGE can create imbalanced subpartitions if boundaries do not reflect data distribution or if data clusters in a single range.

### 9.4. Key stability

Choose a subpartition column whose values rarely change. If UPDATEs frequently change the subpartition key, Oracle may have to move rows across subpartitions; this increases DML cost and can affect ROWID.

If a candidate key column is a business attribute that changes often, evaluate the impact of row movement and indexes before using it as a subpartition key.

### 9.5. Maintenance and retention

The partition key is typically tied to major data management units: month, quarter, year, region. The subpartition key should support queries/distribution without making maintenance overly complex.

If the primary requirement is dropping old data monthly, RANGE partitioning alone may suffice. Adding HASH subpartitions should only be done when benefits in querying, I/O distribution, indexing, or operations are proven.

## 10. Choosing the Number of Subpartitions

The number of subpartitions affects:

- The number of data regions to manage.
- Data and I/O distribution capability.
- Granularity of pruning when queries include the subpartition key.
- The number of local index partitions/subpartitions.
- Metadata, statistics, backups, maintenance, and DDL operations.

For example, with 120 monthly partitions and 16 subpartitions per partition:

\[
120 \times 16 = 1920 \text{ subpartitions}
\]

With multiple fact tables and local indexes, the number of partitioned objects to manage can grow rapidly.

### 10.1. Do not mechanically match subpartition count to CPU count

HASH subpartitioning can help distribute data, but setting 64 subpartitions just because a machine has 64 CPUs does not guarantee faster queries than 8 or 16 subpartitions. The count should be based on:

- Data size per partition.
- Block count and actual concurrency/parallelism.
- Concurrent query volume.
- Pruning effectiveness.
- Local index size.
- Time to create, rebuild, and gather statistics.

### 10.2. Too few subpartitions

If each partition has too few subpartitions:

- Read region sizes may not be reduced enough.
- I/O distribution capability may be limited.
- Some workloads remain concentrated on few data regions.

### 10.3. Too many subpartitions

If each partition has too many subpartitions:

- Increases metadata volume.
- Increases the number of index subpartition objects.
- Increases statistics gathering and maintenance costs.
- Easily creates many tiny subpartitions, increasing overhead.
- Complicates DDL administration.

Choose a count tailored to data size and workload. Measure with representative data before rolling out system-wide.

## 11. Subpartition Templates

A template predefines the subpartition structure applied to each partition. This is a useful tool when all partitions need the same inner structure.

### 11.1. Template for HASH

~~~sql
CREATE TABLE lab_hash_template (
    event_id    NUMBER NOT NULL,
    event_date  DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    payload     VARCHAR2(100 CHAR)
)
PARTITION BY RANGE (event_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_h1,
    SUBPARTITION sp_h2,
    SUBPARTITION sp_h3,
    SUBPARTITION sp_h4
)
(
    PARTITION p2025 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01')
);
~~~

The template creates the same number and structure of hash subpartitions for the partitions. Actual subpartition names are managed by Oracle according to naming rules and metadata; query USER_TAB_SUBPARTITIONS to identify the generated names.

### 11.2. Template for LIST

The RANGE-LIST example in section 5 defined a template for NORTH, CENTRAL, SOUTH, and DEFAULT. When adding new time partitions, the list subpartition structure is applied uniformly.

### 11.3. Without a template

If no template is declared, subpartitions can be specified directly inside each partition. This is useful when each partition needs a distinct structure, but it makes DDL lengthy and harder to keep consistent.

Templates fit when the subpartition structure is uniform. If partitions have differing requirements, explicit per-partition declarations may be more suitable.

## 12. Local Indexes and Global Indexes on Composite-Partitioned Tables

Indexes are a crucial part of partitioning design. Choose indexes that both support queries and satisfy maintenance requirements.

### 12.1. Local index

A local index is partitioned following the table's partitioning structure. Each index partition/subpartition corresponds to the matching table data segment.

~~~sql
CREATE INDEX ix_lab_sales_date_local
ON lab_sales_fact (sale_date)
LOCAL;
~~~

Advantages:

- Index partitions/subpartitions are tied to the table's data boundaries.
- Maintaining a single partition is generally easier to control.
- Parts of an index can be rebuilt or managed at the partition level.
- Local indexes typically fit tables with a partition-based data lifecycle.

A local index is not always optimal for querying a single key across the entire table; access paths and partition scope still determine cost.

### 12.2. Global index

A global index has a partitioning structure independent of the table's partitioning, or it can be a nonpartitioned index. It is useful when queries need to look up a key across many partitions without an appropriate partition key predicate.

Advantages:

- Can provide a single global index structure on a query key.
- Useful for unique keys that do not include the partition key or queries spanning many partitions.

Considerations:

- Some DROP/TRUNCATE/EXCHANGE partition operations can render global indexes unusable or require maintenance depending on syntax and version.
- Maintaining global indexes can add overhead when data is managed by partition.
- An appropriate `UPDATE INDEXES` or rebuild policy must be chosen.

### 12.3. Choosing local vs. global

| Requirement | Typical direction to consider |
|---|---|
| Frequent partition-level data maintenance | Local index |
| Queries filtering on the partition key and within partition scope | Local index usually fits well |
| Key lookups across many partitions without a partition predicate | Global index can be useful |
| Unique key not containing the partition key | May need global unique index or alternative key design |
| Need fast and simple partition drop/truncate | Consider local indexes and global index impact |

There is no rule that "local is always better" or "global is always faster." Examine predicates, constraints, maintenance, and execution plans.

## 13. Partition-Wise Joins and Subpartitioning

Compatible partitioning between two tables can enable Oracle to perform partition-wise joins, joining corresponding data slices rather than processing both entire tables as two massive blocks.

For example, tables SALES_FACT and SALES_TARGET both partitioned by the same SALE_DATE ranges with compatible partition structures. If a query joins on the partition key with appropriate conditions, Oracle can process corresponding partition pairs.

With composite partitioning, compatible subpartitioning can also support joins at a finer granularity, especially when both tables use the same subpartitioning method and compatible keys. Exact eligibility depends on the partitioning scheme, join predicates, and execution plan.

Merely declaring the same number of subpartitions is not enough to guarantee a partition-wise join. Confirm the partitioning structure and actual operations in the execution plan.

## 14. Viewing Partition and Subpartition Metadata

Oracle provides Data Dictionary views to inspect the structure.

### 14.1. View partitioning types

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    def_subpartition_count
FROM user_part_tables
WHERE table_name IN ('LAB_SALES_FACT', 'LAB_SALES_REGION');
~~~

### 14.2. View partitions

~~~sql
SELECT
    table_name,
    partition_name,
    partition_position,
    high_value,
    num_rows,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'LAB_SALES_FACT'
ORDER BY partition_position;
~~~

### 14.3. View subpartitions

~~~sql
SELECT
    table_name,
    partition_name,
    subpartition_name,
    subpartition_position,
    high_value,
    num_rows,
    tablespace_name
FROM user_tab_subpartitions
WHERE table_name = 'LAB_SALES_FACT'
ORDER BY partition_name, subpartition_position;
~~~

### 14.4. View partition keys and subpartition keys

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_part_key_columns
WHERE name = 'LAB_SALES_FACT'
ORDER BY column_position;
~~~

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_subpart_key_columns
WHERE name = 'LAB_SALES_FACT'
ORDER BY column_position;
~~~

Metadata view/column names may vary by object type and version; check the corresponding ALL/USER dictionary views if the current schema does not own the table. `USER_*` views only show objects owned by the current schema.

## 15. Maintenance at Partition and Subpartition Levels

A key benefit of partitioning is managing data by slices. With composite tables, distinguish between partition-level and subpartition-level operations.

### 15.1. TRUNCATE PARTITION

~~~sql
ALTER TABLE lab_sales_fact
TRUNCATE PARTITION p2025_q1;
~~~

This command deletes data across the entire P2025_Q1 partition, meaning all subpartitions inside that partition. The table itself and other partitions remain intact.

### 15.2. TRUNCATE SUBPARTITION

~~~sql
ALTER TABLE lab_sales_fact
TRUNCATE SUBPARTITION subpartition_name;
~~~

Replace `SUBPARTITION_NAME` with the actual name queried from `USER_TAB_SUBPARTITIONS`. The command deletes data in only that single subpartition.

### 15.3. DROP PARTITION

~~~sql
ALTER TABLE lab_sales_fact
DROP PARTITION p2025_q1;
~~~

This command removes the partition along with its subpartitions. This is a structural and data change; verify indexes and dependencies before running.

### 15.4. ADD PARTITION

For RANGE partitioning, you can add a partition at the high end:

~~~sql
ALTER TABLE lab_sales_fact
ADD PARTITION p2026_q1
VALUES LESS THAN (DATE '2026-04-01');
~~~

With composite tables, new subpartitions must be determined via a template or declared in accordance with the partitioning type's syntax. If the table has no template, supply subpartition definitions as required by Oracle.

### 15.5. MOVE SUBPARTITION

A subpartition can be moved to another tablespace:

~~~sql
ALTER TABLE lab_sales_fact
MOVE SUBPARTITION subpartition_name
TABLESPACE users;
~~~

A `MOVE` operation can change ROWIDs and affect indexes; choose index update/rebuild options appropriate for your version and operational policy.

### 15.6. SPLIT and MERGE

With RANGE/LIST partitioning, `SPLIT` can divide one partition into multiple partitions along new boundaries; `MERGE` can combine adjacent partitions. On a composite table, you must specify the subpartition structure for the new partitions using the corresponding syntax.

Illustrative partition-level split syntax example:

~~~sql
ALTER TABLE lab_sales_fact
SPLIT PARTITION pmax AT (DATE '2026-04-01')
INTO (
    PARTITION p2026_q1,
    PARTITION pmax
);
~~~

This is a skeleton example for a RANGE partition. When the table has subpartitions, supply subpartition definitions or use an appropriate template; do not copy commands verbatim into production without verifying the exact syntax for the table structure.

## 16. Interval Partitioning Combined with Subpartitions

For data growing over time, Oracle can automatically create new RANGE partitions via INTERVAL partitioning when data exceeds declared boundaries.

Conceptual example:

~~~sql
CREATE TABLE lab_interval_sales (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(14,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4
(
    PARTITION p_before_2025
    VALUES LESS THAN (DATE '2025-01-01')
);
~~~

Oracle can create interval partitions for new months when inserted data exceeds the partition transition point. Each interval partition uses the subpartition structure declared in the composite specification.

Interval partitioning reduces manual partition creation, but it does not automatically solve all maintenance challenges. Verify Oracle version, partition key data type, interval expression, and partition count limits.

## 17. NULL and DEFAULT in Subpartitions

### 17.1. LIST subpartitions

With LIST subpartitions, clearly define how values outside the list are handled:

~~~sql
SUBPARTITION TEMPLATE
(
    SUBPARTITION sp_north VALUES ('NORTH'),
    SUBPARTITION sp_south VALUES ('SOUTH'),
    SUBPARTITION sp_other VALUES (DEFAULT)
)
~~~

DEFAULT accepts values not enumerated in the remaining subpartitions. If there is no DEFAULT and inserted data has an unmatched value, INSERT can fail because no matching partition/subpartition is found.

If the column can be NULL, verify NULL rules and column constraints; do not rely on DEFAULT as a substitute for explicit data design.

### 17.2. RANGE subpartitions

With RANGE, boundaries must cover the range of values that can appear. If you need to accept all larger values, MAXVALUE can generally be used in the final subpartition of each partition under an appropriate design.

### 17.3. HASH subpartitions

HASH distributes based on a hash function of the key and has no value list to declare DEFAULT. If the key contains NULL, Oracle still applies hashing rules to that value; verify constraints and data behavior for your actual design.

## 18. Subpartition Pruning Does Not Replace Partition Pruning

Suppose a RANGE-HASH table has:

- Partition key: SALE_DATE.
- Subpartition key: CUSTOMER_ID.

Scenarios:

| Predicate | Partition pruning | Subpartition pruning |
|---|---|---|
| SALE_DATE only | Can select one/few partitions | Usually scans all subpartitions within selected partitions |
| CUSTOMER_ID only | Cannot eliminate time partitions | Can select matching hash subpartitions across partitions |
| SALE_DATE and CUSTOMER_ID | Selects partitions by date | Further selects subpartitions by hash key |
| Neither | No pruning on either key | No pruning on either key |

This is a high-level view. The optimizer may apply static or dynamic pruning, and actual access paths depend on expressions, binds, joins, statistics, and version.

If most queries filter only by CUSTOMER_ID without SALE_DATE, RANGE-HASH may still have to inspect every time partition. In that situation, evaluate whether subpartition pruning reduces cost sufficiently or if another partitioning design is more suitable.

## 19. Common Design Mistakes

| Mistake | Consequence | How to reconsider |
|---|---|---|
| Choosing a subpartition key absent from predicates | Subpartition pruning has little value | Analyze SQL workload before selecting key |
| Creating too many subpartitions | Metadata/index/statistics/maintenance overhead grows | Choose count based on size and measurement |
| Using LIST for heavily skewed groups | Some subpartitions huge, others tiny | Evaluate HASH or adjust groups |
| Using HASH when queries need value ranges | Cannot leverage range pruning on key | Consider RANGE if predicates use ranges |
| Having only subpartition predicate and forgetting partition key | Still scans many outer partitions | Add partition key predicates where business logic allows |
| Creating local indexes on every column | Many index subpartitions, higher DML cost | Select indexes based on workload |
| Ignoring global indexes on partition drop/truncate | Indexes may need rebuild/maintenance | Plan index maintenance before DDL |
| Relying on EXPLAIN PLAN without runtime metrics | May misjudge pruning benefits | Inspect actual rows, buffers, reads, and elapsed time |
| Unnecessary functions on partition key | Can make pruning less effective | Write predicates directly on key ranges |

## 20. Practice Exercises

### Exercise 1 — Distinguishing two levels

Given a table partitioned by RANGE(SALE_DATE) and subpartitioned by HASH(CUSTOMER_ID).

**Requirement:** explain the partition key and subpartition key; state how many subpartitions each partition has if SUBPARTITIONS 8 is declared across 12 partitions.

**Target answer:** 12 × 8 = 96 subpartitions.

### Exercise 2 — Creating RANGE-HASH

Create a transaction table partitioned by month and subpartitioned by hash on account_id with eight subpartitions per month.

**Requirement:** insert data spanning two months and inspect metadata.

### Exercise 3 — Creating RANGE-LIST

Create an events table partitioned by quarter, subpartitioned by a list of EVENT_TYPE or REGION_CODE, with a DEFAULT subpartition.

**Question:** where will data carrying a new region go?

### Exercise 4 — Observing two-level pruning

Write three queries on LAB_SALES_FACT:

1. Filter only SALE_DATE.
2. Filter only CUSTOMER_ID.
3. Filter both SALE_DATE and CUSTOMER_ID.

Use `DBMS_XPLAN` to compare PSTART/PSTOP and operations.

### Exercise 5 — Templates

Create a RANGE-LIST table with a four-region template. Add a new time partition and verify that the subpartition structure is applied automatically.

### Exercise 6 — Local and global indexes

Create a local index on CUSTOMER_ID and compare it with a global index suitable for cross-partition queries.

**Question:** how do DROP/TRUNCATE partition operations affect maintenance of the two index types?

### Exercise 7 — Choosing subpartition count

A table has 60 monthly partitions, each expected to hold 20 million rows. Compare options of 4, 8, 16, and 32 hash subpartitions.

**Requirement:** state total subpartitions, expected benefits, and metadata/maintenance costs to measure.

### Exercise 8 — Choosing the method

Choose HASH, LIST, or RANGE for subpartitions in these scenarios:

- CUSTOMER_ID has many values and needs even distribution.
- REGION_CODE has five fixed business groups.
- SHIP_DATE needs range queries.

### Exercise 9 — Partition maintenance

Look up an actual subpartition name in `USER_TAB_SUBPARTITIONS` and write the corresponding `TRUNCATE SUBPARTITION` command in the lab environment.

### Exercise 10 — Workload-driven design

A fact table is queried primarily by date and customer; old data is dropped quarterly. Propose a partition key, subpartition key, method, and initial subpartition count. Explain what needs to be measured before deployment.

## 21. Subpartition Selection Workflow

When designing composite partitioning, follow this order:

1. **Identify data lifecycle:** must data be dropped, archived, compressed, or exchanged by month/quarter/year or business group?
2. **Choose partition key:** prioritize the dimension supporting maintenance and primary filter predicates.
3. **Analyze SQL workload:** identify columns frequently filtered within each partition.
4. **Choose subpartition method:** HASH for distribution; LIST for finite groups; RANGE for range queries.
5. **Choose subpartition key:** use a stable column appearing in predicates with suitable distribution.
6. **Estimate subpartition count:** balance size, pruning, concurrency, and administrative overhead.
7. **Design template:** use when partitions share the same subpartition structure.
8. **Design indexes:** weigh local vs. global based on queries and partition maintenance.
9. **Gather statistics:** ensure the optimizer has estimation data.
10. **Measure execution plan and runtime:** verify pruning, actual rows, buffers, I/O, and DML cost.

Diagram:

~~~text
Identify lifecycle and primary queries
               |
               v
        Choose partition key
               |
               v
  Need to subdivide inside partition?
          /             \
         No              Yes
         |                |
         v                v
 Single partition    Analyze predicates
                          |
                          v
               Choose HASH / LIST / RANGE
                          |
                          v
                Choose subpartition key
                          |
                          v
               Estimate subpartition count
                          |
                          v
                 Template and indexes
                          |
                          v
                 Gather statistics
                          |
                          v
             Inspect plan and measure runtime
                          |
                          v
                  Adjust design
~~~

Composite partitioning divides a table into two levels to combine coarse-grained data management with fine-grained pruning or distribution within each group. The partition key should reflect data lifecycle and primary query conditions; the subpartition key should serve querying, data balance, or I/O distribution. RANGE-HASH generally fits time-series data needing division by a high-cardinality key; RANGE-LIST fits when each time period requires finite business groups; RANGE-RANGE fits when both dimensions are meaningful by range. Subpartition counts, templates, and local/global indexes should be chosen based on real workloads, then verified via execution plans and runtime statistics.
