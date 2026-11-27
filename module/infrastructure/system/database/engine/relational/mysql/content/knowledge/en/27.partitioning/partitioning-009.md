# Per-Partition Indexes and Trade-Offs When Querying Multiple Partitions

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, privileges, backups, and relational database operations. When an InnoDB table is partitioned, each partition has its own local index structures. The optimizer can eliminate irrelevant partitions before accessing indexes, yet queries touching multiple partitions still must process multiple data regions and multiple local indexes.

MySQL does not provide global indexes for partitioned tables. This rule directly affects unique keys, composite index design, and queries filtering on keys that omit the partition key. Partitioning can help limit data scanned or manage large data lifecycles, but does not automatically accelerate every query. You must design the partition key, indexes, and query predicates together, then verify with EXPLAIN.

## 1. How Do Partitions and Indexes Work Together?

Partitioning splits a logical table into multiple physical data regions according to a partitioning expression. Applications still query a single table name; MySQL determines which partitions need to participate based on query predicates and the execution plan.

With InnoDB, each partition maintains local index structures. Conceptually:

~~~text
event_log (one logical table)
|
+-- p2026_01
|   +-- local clustered index
|   +-- local secondary indexes
|
+-- p2026_02
|   +-- local clustered index
|   +-- local secondary indexes
|
+-- p2026_03
    +-- local clustered index
    +-- local secondary indexes
~~~

All partitions share the same index definitions, while each partition stores its own index trees over its subset of rows. Users declare indexes at the table level; you cannot declare a different set of indexes per individual partition.

### 1.1. Local Indexes

A local index is an index covering only the data within a single partition. When a query needs only one partition, MySQL can search inside that partition's local index. When a query needs multiple partitions, the engine may have to probe the corresponding index across multiple partitions and combine the results.

### 1.2. MySQL Has No Global Index for Partitioned Tables

A global index is a single index structure spanning rows across all partitions. MySQL partitioning does not provide this index type. Every index on a partitioned table is local to each partition.

Consequences:

- Queries filtering on the partition key can prune down to a subset of partitions and then use local indexes.
- Queries without predicates on the partition key may have to inspect many or all partitions.
- A unique key cannot rely solely on a column outside the partition key to enforce table-wide uniqueness.
- A secondary index on a non-partitioned column can still be used inside each partition, but never becomes a single global lookup.

### 1.3. Partitioning Does Not Replace Indexing

Partition pruning eliminates partitions that do not need to be accessed. Indexes locate matching rows efficiently inside the retained partitions. The two mechanisms operate at different scopes:

| Mechanism | Scope of impact | Goal |
|---|---|---|
| Partition pruning | Partition selection | Skip irrelevant data regions |
| Local index | Inside each selected partition | Locate matching rows without scanning the entire partition |
| Covering index | Columns needed inside a local index | Reduce extra clustered record lookups when eligible |

A query can prune properly yet remain slow if it must full-scan the selected partition. Conversely, a well-designed index may still have to be probed across many partitions if predicates do not permit pruning.

## 2. Example of a Time-Partitioned Table

An event log table typically grows daily or monthly. It can be partitioned with RANGE COLUMNS on a date column:

~~~sql
CREATE TABLE event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON,
    PRIMARY KEY (event_date, event_id),
    KEY ix_event_tenant_date (tenant_id, event_date),
    KEY ix_event_type_date (event_type, event_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

In the example, each partition holds a date range ending at its VALUES LESS THAN bound. The first partition receives dates earlier than 2026-02-01; partition p2026_02 receives dates from 2026-02-01 up to before 2026-03-01.

### 2.1. Why Does the Primary Key Contain event_date?

The partitioning expression uses event_date. MySQL requires every column used in the partitioning expression to be present in every unique key, including the primary key. Therefore, PRIMARY KEY (event_date, event_id) is valid, whereas PRIMARY KEY (event_id) violates this rule.

A primary key on (event_date, event_id) guarantees uniqueness of the pair. It does not guarantee event_id is globally unique across the table if the same event_id appears on two different dates.

### 2.2. Non-Unique Secondary Indexes

The two indexes:

- (tenant_id, event_date)
- (event_type, event_date)

are non-unique secondary indexes. They can accelerate queries by tenant or event type within each partition. They are not forced to contain the partition key merely by being secondary indexes; the requirement to include partition columns applies specifically to unique keys.

### 2.3. Every Partition Shares the Same Index Definitions

When KEY ix_event_tenant_date is declared, MySQL creates the corresponding local index structure across all partitions. You cannot declare a tenant index on this month's partition while omitting it from another month's partition within the same partitioned table.

This keeps access structures uniform, yet also means every declared index incurs storage and write-maintenance overhead across every partition.

## 3. Partition Pruning and Index Lookup

Partition pruning is the optimizer step that eliminates partitions guaranteed not to hold rows matching the predicates. After pruning, MySQL chooses access methods and indexes across the remaining partitions.

Example time-range query:

~~~sql
SELECT event_id, tenant_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date <  '2026-02-18'
  AND tenant_id = 42;
~~~

The event_date predicate narrows the query to the partition covering that date interval. Index (tenant_id, event_date) can be considered to locate rows for tenant 42 within the date range inside each selected partition.

### 3.1. Pruning Does Not Mean Reading Only One Partition

If the date range spans multiple months, multiple partitions will be retained. For example, a query from late January to early March may need p2026_01, p2026_02, and p2026_03 depending on declared boundaries.

Partition pruning only removes irrelevant regions; it does not guarantee every query touches a single partition.

### 3.2. Direct Predicates on the Partition Key

With RANGE COLUMNS(event_date), write predicates directly on event_date:

~~~sql
WHERE event_date >= '2026-02-01'
  AND event_date <  '2026-03-01'
~~~

A half-open interval [start, end) avoids end-of-day timestamp errors with DATETIME/TIMESTAMP and usually makes partition boundary deduction straightforward.

### 3.3. Avoid Wrapping the Partition Key in Unnecessary Functions

Example:

~~~sql
WHERE YEAR(event_date) = 2026
~~~

Function expressions can make it harder for the optimizer to deduce required partitions, depending on the partitioning expression and version. When partitioned directly by date, prefer writing:

~~~sql
WHERE event_date >= '2026-01-01'
  AND event_date <  '2027-01-01'
~~~

If the table is partitioned by the expression YEAR(event_date) itself, the appropriate predicate style may differ. Write predicates compatible with the partitioning expression and verify the partitions column in EXPLAIN.

### 3.4. Combined Predicates

~~~sql
SELECT event_id
FROM event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND event_type = 'LOGIN';
~~~

The partition key selects the February region; index (event_type, event_date) can help locate LOGIN events inside that region. Which index gets chosen still depends on row counts, selectivity, and statistics.

## 4. Unique Key Rules on Partitioned Tables

This rule is one of the biggest trade-offs when choosing a partition key in MySQL:

**Every unique key on the table must contain all columns used in the partitioning expression.**

### 4.1. Unique Keys Without the Partition Column Are Rejected

Suppose the table is partitioned by event_date. The following definition is invalid:

~~~sql
CREATE TABLE invalid_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

The primary key lacks event_date, failing MySQL's partitioning rule.

### 4.2. Unique Key Combining the Partition Column

Valid definition:

~~~sql
CREATE TABLE valid_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    PRIMARY KEY (event_date, event_id),
    UNIQUE KEY uq_date_event (event_date, event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

In practice, there is no need to create an extra unique index identical to the primary key; the example above merely illustrates that unique keys must contain the partition column. Usually keep only the necessary primary key.

### 4.3. Partition Keys Alter Uniqueness Semantics

If you use:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

then two rows with the same event_id and different event_date values can coexist. If business rules demand globally unique event_id across the table, this key pair is insufficient to enforce that rule.

### 4.4. Solutions When Table-Wide Unique IDs Are Required

One option is using an unpartitioned registry table to enforce global uniqueness:

~~~sql
CREATE TABLE event_id_registry (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
~~~

When inserting an event, the application writes to both the registry and the partitioned table in the same transaction:

~~~sql
START TRANSACTION;

INSERT INTO event_id_registry (event_id, event_date)
VALUES (700001, '2026-02-12');

INSERT INTO event_log (
    event_date, event_id, tenant_id, event_type, payload
)
VALUES (
    '2026-02-12', 700001, 42, 'LOGIN', JSON_OBJECT('source', 'web')
);

COMMIT;
~~~

If either INSERT fails, the application rolls back the entire transaction so the registry and event_log stay consistent. This adds an extra write and an extra table to manage; use it only when global uniqueness genuinely needs database enforcement.

Other options include application-generated global IDs or an ID service, provided collision probability and retry rules are clearly specified. Never rely on a local unique index to claim event_id is unique across partitions.

## 5. Choosing Column Order in Composite Indexes

Partition pruning and index column ordering are two separate decisions. The partition key determines the region; column order inside a composite index determines how searches proceed inside each region.

### 5.1. Queries Filtering Tenant First, Then Date

~~~sql
SELECT event_id, event_type
FROM event_log
WHERE tenant_id = 42
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Index (tenant_id, event_date) aligns with equality on tenant_id followed by a range on event_date. Within each pruned partition, the optimizer can use the leftmost prefix and range scan.

### 5.2. Queries Filtering Event Type First, Then Date

~~~sql
SELECT event_id, tenant_id
FROM event_log
WHERE event_type = 'LOGIN'
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Index (event_type, event_date) may fit. If event_type has low selectivity or tenant/date distributions differ, the optimizer may pick another index or scan the partition.

### 5.3. Indexes Leading with the Partition Key

Index (event_date, tenant_id) can fit queries starting with a date range and then filtering by tenant. However, when the leading column is a range, the ability to use subsequent columns to narrow the range scan differs from an equality-prefix followed by a range.

There is no single column order optimal for every query. List frequent query shapes and design indexes around equality, range, ordering/grouping, and covering columns.

### 5.4. Covering Indexes Remain Useful Inside Partitions

If a query reads only columns already present in a secondary index, the local index can serve as a covering index within each selected partition. That reduces clustered record lookups, though it does not eliminate the cost of visiting each partition in the selected set.

### 5.5. Avoid Redundant Indexes Across All Partitions

Every table-level index is maintained across every partition. Adding too many indexes increases:

- Overall index storage size.
- INSERT/UPDATE/DELETE write overhead.
- Index update work when partitions are reorganized or data moves.
- Time and resources for index maintenance.

Before adding an index, review SHOW INDEX, workload, and EXPLAIN. An index serving only a rare query may not justify constant write overhead across a massive table.

## 6. Queries Without the Partition Key and Fan-Out Cost

This scenario requires special attention with local indexes.

Example:

~~~sql
SELECT event_date, event_id, tenant_id
FROM event_log
WHERE event_id = 700001;
~~~

The query has no event_date predicate. The optimizer cannot pinpoint a partition from event_id alone when partitioning is based on event_date. It may have to check many partitions.

If a local index exists on event_id, MySQL can use that index inside each accessed partition. Yet because there is no global index, there is no single global B-tree pointing straight to the partition containing event_id.

### 6.1. Fan-Out Across Multiple Partitions

When a query touches multiple partitions, costs can include:

- Identifying and opening the necessary partitions.
- Probing corresponding local indexes across many partitions.
- Reading and merging results from multiple regions.
- Sorting or deduplicating across the merged result set if required by the query.
- Maintaining more index structures and metadata compared to single-region access.

More partitions do not slow down every query by the same ratio; cost depends on plans, data, and caching. Still, broad fan-out is a warning sign to investigate whenever queries omit the partition key.

### 6.2. Does Adding an Index on event_id Completely Solve It?

You can create:

~~~sql
CREATE INDEX ix_event_id
ON event_log (event_id);
~~~

This index allows looking up event_id in each partition's local index. It can lower cost compared to scanning data in each partition, yet still does not turn into a global index and does not restrict the lookup to one partition.

If querying by event_id is a primary access path, reconsider the partition key, use a registry table, or choose a different storage design instead of merely adding an index.

### 6.3. The Partition Key Should Reflect Query Patterns

Time-based partitioning makes sense when most queries and maintenance tasks are time-bounded. If most queries filter solely by tenant_id without a date condition, time partitioning can force tenant queries to fan out across many partitions.

Never choose a partition key solely because a column grows steadily or has high cardinality. Base it on query workload and retention needs.

## 7. Querying Across One, Several, and All Partitions

Workloads can be grouped into three categories:

| Query type | Example | Trade-off |
|---|---|---|
| Single partition | One day or one month | Good pruning; smaller local indexes |
| Several partitions | Quarterly report or date range spanning multiple months | Moderate fan-out; results must be combined |
| Many/all partitions | Lookup by event_id without date or full-history report | May have to probe many local indexes or scan many regions |

### 7.1. Single-Partition Query

~~~sql
SELECT COUNT(*)
FROM event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

With monthly partitions and matching boundaries, the query needs only February's partition. This is where partition pruning delivers clear benefits.

### 7.2. Multi-Partition Query

~~~sql
SELECT event_type, COUNT(*) AS event_count
FROM event_log
WHERE event_date >= '2026-01-15'
  AND event_date < '2026-03-15'
GROUP BY event_type;
~~~

The query may touch several partitions. Each region is read and aggregated per the plan, and partial results are combined. Partitioning does not eliminate the cost of reading the data needed for reporting.

### 7.3. Full-Partition Query

~~~sql
SELECT event_type, COUNT(*) AS event_count
FROM event_log
GROUP BY event_type;
~~~

With no partition key predicate, many or all partitions may participate. If this is a frequent report, consider summary tables, application-maintained aggregates, or a dedicated analytics pipeline.

## 8. Inspecting Partitions and Indexes in EXPLAIN

Never guess partition pruning from SQL text alone. Inspect the plan.

### 8.1. Tabular EXPLAIN

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

In traditional output, the partitions column lists the partitions chosen by the optimizer. Columns type, possible_keys, key, rows, filtered, and Extra show the access path and read estimates.

If the partitions column lists only one partition when querying strictly inside February, pruning is working. If multiple partitions appear, re-check boundaries and predicates.

### 8.2. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

JSON shows partition details inside the table access block alongside index, estimated rows, and other plan details. Use it for automated analysis or saving plans for comparison.

### 8.3. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

TREE reveals iterators and execution order. Depending on version, partition details may be displayed differently than in tabular/JSON output; when an explicit partition list is needed, check tabular or JSON output.

### 8.4. EXPLAIN ANALYZE

MySQL 8.0.18+ supports EXPLAIN ANALYZE for compatible SELECT statements:

~~~sql
EXPLAIN ANALYZE
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

EXPLAIN ANALYZE executes the actual query and reports actual timing, actual row counts, and loops. Compare against estimated rows to spot stale or skewed statistics. Run on lab or staging when possible; do not treat it as a free metadata-only command.

### 8.5. Comparing Queries With and Without the Partition Key

~~~sql
EXPLAIN
SELECT event_id
FROM event_log
WHERE event_date = '2026-02-12'
  AND event_id = 700001;

EXPLAIN
SELECT event_id
FROM event_log
WHERE event_id = 700001;
~~~

Compare the partitions column and chosen index. The first query can prune by event_date; the second query lacks a partition key predicate and may need to search across many partitions.

## 9. Explicit Partition Selection

MySQL supports explicit partition selection syntax:

~~~sql
SELECT event_id, event_type
FROM event_log PARTITION (p2026_02)
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18';
~~~

This syntax restricts the query to the named partition. It is not merely an optimizer hint; if matching rows reside in another partition, the query will not return them.

Use explicit partition selection only when the application knows with certainty which partition to access and manages partition names reliably. For regular queries, letting the optimizer prune automatically from data predicates is safer and easier to maintain.

## 10. How the Partition Key Affects Keys and Queries

The partition key must be evaluated alongside primary keys, unique keys, and indexes.

### 10.1. Composite Primary Keys

When partitioning by event_date:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

This primary key both satisfies the unique key rule and supports queries on event_date and event_id. Still, column order in the clustered index affects access patterns:

- Lookups by event_date or event_date + event_id can leverage the leftmost prefix.
- Lookups by event_id alone cannot use the leftmost prefix as a direct lookup.
- A local secondary index on event_id can assist per-partition lookups, yet still incurs fan-out.

### 10.2. Auto-Increment

If a partitioned table uses AUTO_INCREMENT, the auto-increment column must still be indexed per MySQL rules and every unique key must still include partition columns. A composite primary key design may make table-wide ID uniqueness behave differently from a single-column ID primary key.

Check AUTO_INCREMENT and unique key rules for your exact MySQL version before converting an existing table to partitioning. Never assume adding partitions preserves all key semantics unchanged.

### 10.3. Foreign Keys

InnoDB partitioned tables carry a major restriction: MySQL does not support foreign keys on partitioned InnoDB tables, whether the partitioned table holds the foreign key or another table references it. If the schema relies on foreign keys, partitioning may require redesigning data integrity mechanisms.

Never drop foreign keys merely to partition a table without shifting referential checks to application logic or controlled data workflows.

## 11. When Does Partitioning Help?

Partitioning is usually valuable when:

- Data is large and queries frequently filter on the partition key.
- Data has a time-based lifecycle, such as logs, events, or historical transactions.
- Old data needs to be purged by partition instead of running DELETE across millions of rows.
- Maintenance tasks can be scoped to a few partitions.
- Each partition stays sized appropriately for operations and storage.

### 11.1. Retention via DROP PARTITION

For data expiring monthly, a DBA can drop an old partition:

~~~sql
ALTER TABLE event_log
DROP PARTITION p2026_01;
~~~

This DDL operation removes all data in that partition. It is usually much faster than row-by-row DELETE when dropping a full data region, though backups, replication, privileges, and operational plans must be checked before running.

### 11.2. Partitioning Does Not Automatically Speed Up Unrelated Queries

If the application regularly runs WHERE tenant_id = ? without filtering event_date, time partitioning can force tenant queries to fan out across many partitions. A local index on (tenant_id) can still be probed per partition, yet there is no single global index.

### 11.3. Partitioning Is Not Sharding

Partitioning keeps one logical table inside the same MySQL server/instance. It does not distribute data across multiple servers like sharding. If the bottleneck is CPU, RAM, or I/O of one server, partitioning does not scale compute resources horizontally.

## 12. Trade-Offs of Having Many Partitions

Having many partitions helps break up data and manage retention, yet also increases administrative overhead and can worsen query fan-out.

### 12.1. Metadata and Planning Overhead

The optimizer and server must manage metadata across all partitions. Tables with excessive partitions can increase table-opening, statement preparation, planning, and maintenance overhead. Impact depends on MySQL version, number of partitions touched, and workload.

### 12.2. Local Index Overhead

Every declared index exists per partition. Many partitions multiplied by many indexes increases the number of structures managed, storage footprint, and maintenance work.

### 12.3. Query Fan-Out

Queries spanning many partitions must coordinate multiple local indexes or scan multiple regions. For queries lacking a partition predicate, pruning benefits are nearly nonexistent.

### 12.4. DDL and Maintenance

Adding, dropping, splitting, or merging partitions can require metadata locks and data reorganization depending on the operation. Evaluate duration, temporary space, replication lag, and workload impact before changing partition layouts.

### 12.5. Do Not Pick Partition Counts Arbitrarily

Do not create daily partitions if workload and retention do not require them. Equally, do not bundle many years into one partition if monthly purging is an essential requirement. Base granularity on:

- Data volume per day/month.
- Typical query time windows.
- Retention period.
- Rate of new partition creation.
- DDL overhead and version limits.

## 13. Index Design Process for Partitioned Tables

A practical workflow:

1. Collect query workload: filter columns, joins, ordering, grouping, and time ranges.
2. Select the partition key based on queries and retention.
3. Determine whether unique/primary keys can include all partition columns.
4. Classify queries as single-partition, multi-partition, or full-partition.
5. Design local indexes around equality prefixes, range columns, and covering needs.
6. Check whether queries omitting the partition key suffer excessive fan-out.
7. Use EXPLAIN to verify pruning and index access.
8. Use EXPLAIN ANALYZE on representative data to measure actual rows and timing.
9. Measure write cost, index storage size, and DDL speed.
10. Monitor post-deployment and adjust based on real workload.

### 13.1. Query and Index Matrix

Example workload:

| Query shape | Partition key filter | Candidate local index |
|---|---|---|
| Tenant within one month | Yes | (tenant_id, event_date) |
| Event type within one month | Yes | (event_type, event_date) |
| Event by date and ID | Yes | Primary key (event_date, event_id) |
| Lookup event_id without date | No | (event_id) reduces per-partition scan yet still fans out |
| Full-history report by type | No | (event_type, event_date) or summary table depending on cardinality |

This is a starting point for measurement, not a mandatory index list. Do not add every index if the workload does not need them.

## 14. Practice Lab: Observing Local Indexes and Partition Pruning

Run on MySQL 8.0 inside a lab database. This lab creates a partitioned event table, inspects query plans, and compares queries with and without the partition key.

### 14.1. Create the Lab Table

~~~sql
CREATE TABLE lab_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (event_date, event_id),
    KEY ix_lab_tenant_date (tenant_id, event_date),
    KEY ix_lab_type_date (event_type, event_date),
    KEY ix_lab_event_id (event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

### 14.2. Load Sample Data

~~~sql
INSERT INTO lab_event_log
    (event_date, event_id, tenant_id, event_type)
VALUES
    ('2026-01-10', 1001, 10, 'LOGIN'),
    ('2026-01-20', 1002, 20, 'PAYMENT'),
    ('2026-02-05', 1003, 10, 'LOGIN'),
    ('2026-02-12', 1004, 10, 'PAYMENT'),
    ('2026-02-18', 1005, 30, 'LOGIN'),
    ('2026-03-03', 1006, 20, 'PAYMENT'),
    ('2026-03-15', 1007, 10, 'LOGIN');
~~~

### 14.3. Step 1 — Single-Partition Query

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND tenant_id = 10;
~~~

Inspect the partitions column. Only February's partition is selected. Inspect the index key and rows estimate; small sample data may lead the optimizer to choose a scan.

### 14.4. Step 2 — Multi-Partition Query

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-01-15'
  AND event_date < '2026-03-15'
  AND tenant_id = 10;
~~~

Observe which partitions are selected and compare with Step 1. Because the query crosses month boundaries, more partitions are needed.

### 14.5. Step 3 — Query Missing the Partition Key

~~~sql
EXPLAIN
SELECT event_date, event_id, tenant_id
FROM lab_event_log
WHERE event_id = 1004;
~~~

Inspect the partitions column. Because event_id is not the partition key, the optimizer may have to check multiple partitions. Index ix_lab_event_id is a local index in each partition, not a global index.

### 14.6. Step 4 — Comparing Composite Index Usage

~~~sql
EXPLAIN
SELECT event_id
FROM lab_event_log
WHERE tenant_id = 10
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Read key and access type. Observe whether the optimizer picks ix_lab_tenant_date. On tiny tables, a scan may be cheaper than an index lookup; that is a cost-based optimizer decision.

### 14.7. Step 5 — View the Partition List

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    TABLE_ROWS
FROM information_schema.partitions
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lab_event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

InnoDB TABLE_ROWS is an estimate and not always exact. Use COUNT queries filtered by the partition key when exact row counts are needed in the lab.

### 14.8. Step 6 — Measure with EXPLAIN ANALYZE

On MySQL 8.0.18 or newer:

~~~sql
EXPLAIN ANALYZE
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND tenant_id = 10;
~~~

Read actual rows, loops, and execution time. The sample dataset is too small to judge production performance; the goal is understanding the distinction between partition pruning and index access.

### 14.9. Step 7 — Clean Up the Lab Table

~~~sql
DROP TABLE lab_event_log;
~~~

Only drop the lab table you just created.

**Expected outcome:** ability to explain local indexes, why MySQL lacks global indexes on partitioned tables, why unique keys must include partition columns, how to read pruning in EXPLAIN, and the trade-offs of queries lacking the partition key.

## 15. Principles to Remember

- Every InnoDB partition has local index structures; index definitions are declared at the table level and apply to all partitions.
- MySQL does not support global indexes for partitioned tables; queries lacking the partition key may have to probe local indexes across many partitions.
- Partition pruning eliminates irrelevant partitions; indexes then locate rows inside the selected partitions.
- Partitioning does not replace indexes and does not automatically make all queries faster.
- Every unique key, including the primary key, must contain all columns used in the partitioning expression.
- A composite primary key containing the partition key may not guarantee table-wide uniqueness of a business ID alone.
- If global uniqueness is required on a column outside the partition key, consider a registry table or globally unique IDs and maintain consistency via transactions.
- Choose composite index column order based on equality, range, ordering, and covering needs; partition key selection and index column ordering are separate decisions.
- Queries spanning multiple partitions can fan out across many local indexes, increasing read and result-merging costs.
- Write predicates directly on the partition key so the optimizer can prune easily; verify with the partitions column in EXPLAIN.
- Explicit partition selection restricts which data is read and can omit matching rows if the wrong partition is named.
- InnoDB partitioned tables do not support foreign keys; assess the impact on data integrity before partitioning.
- Partitioning suits workloads with partition-key predicates and retention needs; it does not replace sharding.
- Many partitions increase metadata, index structures, and management overhead; choose granularity to match workload.
- Use EXPLAIN/JSON to inspect partitions and indexes; use EXPLAIN ANALYZE to measure real execution on MySQL 8.0.18+.

Partition and index design must start from how the application queries data. When queries filter effectively on the partition key, pruning shrinks the regions accessed and local indexes locate rows within those regions. When queries omit the partition key, local indexes may be probed across many partitions; in that case, partitioning benefits shrink and fan-out cost becomes a factor to measure carefully.
