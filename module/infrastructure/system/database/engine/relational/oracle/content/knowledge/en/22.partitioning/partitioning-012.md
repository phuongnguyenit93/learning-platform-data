# Verifying Partitioning Benefits with Execution Plans and Realistic Load in Oracle Database

Partitioning divides a large table or index into smaller pieces while still being queried as one logical object. Partitioning can reduce the amount of data read, manage data by lifecycle, perform piecewise maintenance, and improve certain joins or data loads. However, **a partitioned table does not automatically make every query faster**. Benefits only appear when the partition design fits the workload and Oracle can exploit it.

To prove effectiveness, combine two types of evidence:

1. **Execution plan:** Does Oracle perform partition pruning, which partitions are read, how are local/global indexes used, and are estimated row counts reasonable?
2. **Execution metrics:** How many buffers and physical blocks does the query actually read, what are CPU and wait times, and how does throughput change across multiple concurrent sessions?

Merely seeing a `PARTITION RANGE` line in a plan is not enough to conclude the system is faster. Nor can you conclude partitioning is useless just because a small test query on a few rows did not prune. This lesson builds a controlled measurement workflow using identical data and workloads, evaluating both query gains and write, index, statistics, and operational costs.

## 1. What Problem Does Partitioning Solve?

### 1.1. One logical table, many physical partitions

For example, a transaction table holding multiple years of data. If split by month, each month is a partition:

```text
TRANSACTIONS
  P2026_01  -> January 2026 data
  P2026_02  -> February 2026 data
  P2026_03  -> March 2026 data
  ...
```

Applications still query `TRANSACTIONS`. Oracle manages mapping rows to partitions via the partition key. Users do not need to write partition names in regular SQL.

### 1.2. Partition pruning

Partition pruning is Oracle's ability to eliminate partitions that cannot contain rows matching query conditions. For example, on a table partitioned by `ORDER_DATE`, a query needing only February 2026:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';
```

If partition boundaries align by month, Oracle can read only the February partition instead of scanning every partition. This is typically the most readily observable benefit.

### 1.3. Other benefits

- **Data lifecycle management:** `DROP`/`TRUNCATE`/`EXCHANGE` on a partition can handle a data range faster than conventional bulk operations.
- **Piecewise maintenance:** rebuild or manage indexes per partition in suitable configurations.
- **Partition-wise joins:** reduce data exchange and leverage parallel processing when two tables are compatibly partitioned.
- **Data loading:** partition exchange or direct-path loads can speed up batch loading.
- **Availability/maintenance:** some operations can limit impact scope to the affected partition.

These benefits must be evaluated per workload. A system querying primarily by customer key without predicates on the partition key may receive no pruning for its most critical queries.

### 1.4. Partitioning does not replace indexes

Partitioning and indexing solve different problems:

| Mechanism | Primary objective |
|---|---|
| Partitioning | Limit data scope, manage data in slices |
| B-tree index | Quickly locate rows by key |
| Bitmap index | Support certain low-cardinality analytical workloads |
| Local index | Index partitioned in alignment with table partitions |
| Global index | Index spanning across a partitioned table |

A query can prune down to one partition and then use an index inside that partition. Conversely, without pruning, Oracle may still have to probe multiple partitions or multiple index partitions.

## 2. Formulate Hypotheses Before Measuring

Do not start a benchmark with a vague question like "is partitioning faster?" Write down testable hypotheses:

- Monthly reporting queries currently scan the entire table; monthly partitioning will reduce the number of partitions accessed.
- Old-data purge batches currently run slow `DELETE`s; `DROP`/`TRUNCATE` partition can reduce undo/redo and maintenance duration.
- Fact-table joins with a large dimension table; partition-wise joins can cut data exchange between parallel workers.
- Queries by `customer_id` without a date filter; date partitioning may not help, and may even add cost if probing many partitions.

Tie each hypothesis to specific SQL statements, bind value sets, result row counts, frequencies, concurrency, and metrics. Set success criteria before running tests to avoid cherry-picking favorable numbers afterward.

### 2.1. Document the workload

Build a representative query inventory:

| Category | Example predicate | Weight/Frequency | Objective |
|---|---|---:|---|
| By day/month | `ORDER_DATE` within a range | High | Pruning |
| By business key | `CUSTOMER_ID = :id` | High | Test access without partition key |
| By date and key | `ORDER_DATE` range + `CUSTOMER_ID` | High | Pruning combined with index |
| Summary report | `GROUP BY` month/region | Medium | Scan, aggregate, parallel |
| Batch load | Monthly `INSERT` | Scheduled | DML throughput |
| Old-data purge | Delete by retention period | Scheduled | Partition maintenance |
| Fact/dimension join | Join on dimension key | Medium | Partition-wise join |

Do not select only queries that prune easily. If the real workload has many queries that do not filter on the partition key, they must appear in the overall measurement.

### 2.2. Choose the partition key from workload and lifecycle

The partition key is typically chosen based on:

1. Predicates that appear frequently and can bound data scope.
2. Retention/archiving rules or data loading workflows.
3. Table size and growth rate.
4. How large tables join with one another.
5. Data distribution and the risk of a single partition becoming oversized or hot.

Never pick a partition key solely for a rarely executed reporting query. If you choose `ORDER_DATE` while most requests pass only `CUSTOMER_ID`, measure the cost of probing multiple partitions for those requests.

## 3. Partitioning Types and Impact on Verification

### 3.1. Range partitioning

Range partitioning splits by value ranges:

```sql
CREATE TABLE orders_range_lab (
    order_id      NUMBER(12) NOT NULL,
    order_date    DATE NOT NULL,
    customer_id   NUMBER(10) NOT NULL,
    total_amount  NUMBER(14, 2) NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
```

Each partition receives values less than its upper bound and greater than or equal to the preceding bound. The first partition in this example has no explicit lower bound; it accepts all values less than `2026-02-01`. In production systems, explicitly account for historical data and the initial partition.

Range suits dates, sequence numbers, or ordered keys with clear lifecycles.

### 3.2. Interval partitioning

Interval partitioning automatically creates subsequent partitions when data exceeds the transition point:

```sql
CREATE TABLE orders_interval_lab (
    order_id     NUMBER(12) NOT NULL,
    order_date   DATE NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL
)
PARTITION BY RANGE (order_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
```

Oracle automatically creates interval partitions for intervals past the transition point as needed. When testing, verify which partitions were actually created, their names, counts, and row distributions; do not assume interval partitions already exist before data is loaded.

### 3.3. List partitioning

List partitioning splits by discrete value sets:

```sql
CREATE TABLE orders_by_region_lab (
    order_id NUMBER(12),
    region_code VARCHAR2(10),
    total_amount NUMBER(14, 2)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
```

List fits when value groups carry business meaning and queries frequently filter on those groups. If one group holds nearly all data, distribution benefits may be minimal.

### 3.4. Hash partitioning

Hash partitioning distributes rows using a hash function of the partition key:

```sql
CREATE TABLE customer_events_hash_lab (
    event_id NUMBER(12),
    customer_id NUMBER(10) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    event_type VARCHAR2(30)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Hash distributes data more evenly in some workloads and can reduce hotspots, yet a predicate on `customer_id` identifies a partition only if Oracle can compute the hash from that condition. Hash does not automatically aid queries by `event_time` if `event_time` is not the partition key.

### 3.5. Composite partitioning

Composite partitioning combines two levels, such as monthly range and hash by customer:

```sql
CREATE TABLE orders_composite_lab (
    order_id NUMBER(12),
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2)
)
PARTITION BY RANGE (order_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4 (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Composite partitioning can prune at both partition and subpartition levels if predicates provide suitable information. However, segment counts, index partitions, and administrative work multiply with partition/subpartition counts. Choose it only when workload and scale prove the benefit.

## 4. Partition Pruning in Execution Plans

### 4.1. PSTART and PSTOP

In `DBMS_XPLAN` output, `PSTART`/`PSTOP` columns describe the partition range accessed by a partitioned operation. Values can be:

- Specific partition numbers: static range determinable at parse time.
- `KEY` or `KEY(I)`: range determined at runtime from binds/predicates or runtime mechanisms.
- `ROWID`: partition determined from rowid in certain access paths.
- `MIN`/`MAX` or other special values depending on operation/release.

Do not interpret `KEY` as "read all partitions." Inspect predicates, operations, actual rows, and corresponding partition pruning details in the plan.

### 4.2. Static pruning

Conditions with literals or expressions evaluable at parse time:

```sql
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';
```

Oracle can identify the matching partition during optimization. The plan typically shows concrete `PSTART`/`PSTOP` bounds.

### 4.3. Dynamic pruning

With bind variables:

```sql
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

Partitions are determined at execute time based on bind values. `PSTART`/`PSTOP` may show `KEY` or runtime notation. This does not mean pruning failed to happen; verify execution with different bind values.

Dynamic pruning can also occur when partition keys come from joins or subqueries, such as a dimension join supplying the set of partitions to access.

### 4.4. Full partition scans vs. pruning

A plan with `PARTITION RANGE ALL` typically indicates all partitions in scope are scanned. `PARTITION RANGE SINGLE` typically indicates one partition is selected. `PARTITION RANGE ITERATOR` iterates across a range of partitions.

Operation names and details can vary by partition type, release, and access path. Do not just look for `SINGLE`/`ALL`; cross-check `PSTART`/`PSTOP`, predicates, and actual row sources.

### 4.5. Predicates must be friendly to the partition key

Direct range predicates:

```sql
WHERE order_date >= :from_date
  AND order_date <  :to_date
```

generally favor range partition pruning.

Predicates wrapping columns in functions:

```sql
WHERE TRUNC(order_date) = :day
```

can hinder pruning or depend on transformations/partition expressions. When the partition key is `ORDER_DATE`, a range form is usually clearer and safer:

```sql
WHERE order_date >= TRUNC(:day)
  AND order_date <  TRUNC(:day) + 1
```

Here the function applies to the bind variable, not the partition key. If the column is `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE`, use matching bind types and time boundaries to avoid implicit conversions.

### 4.6. Implicit conversion can block pruning

If `ORDER_DATE` is `DATE` but the application sends a string, Oracle may convert types based on `NLS_DATE_FORMAT`. That makes semantics session-dependent and can prevent optimal predicates.

Bind `DATE`/`TIMESTAMP` with proper types:

```sql
WHERE order_date >= :date_from
  AND order_date <  :date_to
```

Never build conditions by concatenating date strings into SQL. Aside from injection risks, implicit conversion can cause plans and pruning to vary across sessions.

## 5. Viewing Plans with DBMS_XPLAN

### 5.1. EXPLAIN PLAN

Example:

```sql
EXPLAIN PLAN FOR
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(
    NULL,
    NULL,
    'BASIC +PARTITION +PREDICATE +COST +ROWS'
));
```

Items to inspect:

- Operation and accessed object.
- `PSTART`/`PSTOP`.
- Access predicates and filter predicates.
- Estimated rows and cost.
- Index access vs. full scan.
- Join method and join order if querying multiple tables.

`EXPLAIN PLAN` shows an estimated plan and may not reflect actual bind values or runtime behavior.

### 5.2. Actual cursor plan

Run the statement with row-source statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +PEEKED_BINDS'
    )
);
```

`ALLSTATS LAST` shows actual metrics from the most recent execution when statistics are gathered. Compare `E-Rows` (estimated) with `A-Rows` (actual), `Starts`, `Buffers`, and `Reads`. `PEEKED_BINDS` may display binds peeked during hard parse if available; it does not necessarily show binds from every subsequent execution.

### 5.3. Identifying the right cursor

In sessions running many SQL statements, `DISPLAY_CURSOR(NULL, NULL, ...)` typically shows the most recent cursor in context. When benchmarking, record `SQL_ID` and child number to avoid reading the wrong cursor:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       buffer_gets,
       disk_reads,
       rows_processed,
       elapsed_time
FROM v$sql
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
ORDER BY last_active_time DESC;
```

Querying `V$SQL` requires appropriate privileges. Avoid overly broad `LIKE` filters on busy systems; in test environments, use module/action tags or the captured `SQL_ID`.

### 5.4. Reading PSTART/PSTOP with operations

Illustrative interpretation:

| Plan evidence | How to read |
|---|---|
| PARTITION RANGE SINGLE, PSTART=2, PSTOP=2 | Accesses one specific partition |
| PARTITION RANGE ITERATOR, PSTART=2, PSTOP=4 | Iterates over a range of partitions |
| PARTITION RANGE ALL, PSTART=1, PSTOP=12 | Scans all 12 partitions in scope |
| PSTART/PSTOP = KEY | Partition range determined at runtime |

These are illustrative examples; actual partition numbers and operation names depend on DDL/plans. Inspect object names and partition metadata to identify exact partitions.

## 6. Checking Partition Metadata and Data Distribution

### 6.1. List partitions

```sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'ORDERS_RANGE_LAB'
ORDER BY partition_position;
```

`HIGH_VALUE` is stored as a metadata expression; do not parse this string in applications as a stable interface. `NUM_ROWS`/`BLOCKS` reflect statistics at the time of gathering.

### 6.2. Count rows per partition

Extended table syntax can be used in lab queries:

```sql
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_01);
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_02);
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_03);
```

Or check metadata statistics for estimates. Counting every partition exactly can generate substantial I/O; do so only in test environments or approved measurement windows.

### 6.3. Check partitions/subpartitions

With composite partitioning, check:

```sql
SELECT partition_name,
       subpartition_name,
       subpartition_position,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_subpartitions
WHERE table_name = 'ORDERS_COMPOSITE_LAB'
ORDER BY partition_position, subpartition_position;
```

Skewed row counts can turn one partition into a hotspot or create unbalanced workloads. Partitioning does not balance skewed range keys automatically; choose keys and granularity accordingly.

### 6.4. Check index partitions

```sql
SELECT index_name,
       partition_name,
       status,
       num_rows,
       leaf_blocks,
       last_analyzed
FROM user_ind_partitions
WHERE index_name = 'IX_ORDERS_RANGE_LAB_LOCAL'
ORDER BY partition_position;
```

Verify each index partition's status after loads, exchanges, splits, merges, or maintenance. `UNUSABLE` index partitions can impact queries or DML differently depending on index type and configuration.

## 7. Designing Controlled Benchmarks

### 7.1. Two comparative structures

To measure partitioning gains, prepare two tables with identical logical data:

- Table A: nonpartitioned heap table.
- Table B: partitioned table using the candidate partition key.

Keep identical wherever possible:

- Same columns, data types, nullability, and constraints.
- Same data, row counts, and distributions.
- Equivalent indexes in terms of keys and properties.
- Statistics gathered using an equivalent policy.
- Same SQL, bind values, and session settings.

If Table A has an index while Table B lacks one (or vice versa), the benchmark no longer isolates partitioning impact.

### 7.2. Data must be representative

Do not draw conclusions about a 500-million-row table from 10 rows. Test data must represent:

- Row counts per partition.
- Distribution skew across time/customers/regions.
- NULL ratios and common vs. rare values.
- Row sizes and LOBs if present.
- Index density and clustering.
- Hot vs. cold data ratios.

If the workload has skewed data, generate bind values covering both frequent and rare cases.

### 7.3. Identical SQL and identical binds

Compared SQL should be logically identical:

```sql
SELECT COUNT(*), SUM(total_amount)
FROM orders_heap_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

and:

```sql
SELECT COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

Only the table name differs. Use the same bind data types, date ranges, session settings, and expected outputs.

### 7.4. Measure multiple query patterns

Include at least:

1. Single partition (one day/month).
2. Multiple contiguous partitions.
3. Full history.
4. Queries filtering only on non-partition keys.
5. Queries combining partition key and index key.
6. Joins with dimension tables.
7. Aggregations/reports.
8. Batch `INSERT`s and `DELETE`/retention operations.

Partitioning may improve items 1–3 while leaving item 4 unchanged. Weight results by actual workload proportions to assess net benefit.

### 7.5. Control cache state and execution order

Caching heavily affects benchmarks:

- The first run may perform physical I/O; subsequent runs find data in the buffer cache.
- Always running A before B may let B benefit from warm cache.
- Never flush buffer cache/shared pool in production to make a benchmark "fair."
- In a dedicated lab, alternate A/B order, run multiple iterations, and report cold vs. warm runs separately if controllable.
- Document cache conditions and never mix cold-run and warm-run metrics.

### 7.6. Repeat runs and report distributions

One run is insufficient. Run multiple iterations and report:

- Median.
- p95/p99 if measuring latency across many requests.
- Min/max to spot outliers.
- Execution counts and completed requests.
- Throughput (requests/second or rows/second).

Do not report only the fastest run. Note outliers caused by I/O, checkpoints, concurrent loads, or background tasks.

## 8. Metrics to Measure

### 8.1. Time and throughput

| Metric | Meaning |
|---|---|
| Elapsed time | Time from submission to completion |
| CPU time | CPU time consumed by SQL |
| Throughput | Requests or rows processed per second |
| p95/p99 latency | Tail latency of the distribution |
| Rows processed | Actual rows returned/inserted/updated |

Low elapsed time in a single session does not guarantee high throughput under many concurrent sessions.

### 8.2. Logical reads and physical reads

- **Buffer gets/logical reads:** block accesses in the buffer cache; useful for measuring logical work.
- **Physical reads:** blocks read from storage; depends on cache and I/O.
- **Disk reads in V$SQL:** per-cursor metric; understand units and aggregation across releases and child cursors.

Partition pruning generally lowers accessed partitions; if data fits in few blocks or indexes are selective, the gap in physical reads might be small. Inspect buffer gets, reads, and elapsed time together.

### 8.3. Wait events and concurrency

Under multiple sessions, inspect wait times:

- User I/O.
- Concurrency/buffer busy.
- Enqueue/locks.
- Log file sync and redo-related waits.
- Parallel execution waits.
- CPU saturation.

Partitioning can reduce certain contention or introduce extra segment/index maintenance; outcomes depend on partition type and DML patterns.

### 8.4. DML and maintenance costs

Also measure:

- `INSERT` rows/second.
- `UPDATE`/`DELETE` elapsed time.
- Redo and undo volume.
- Index maintenance cost.
- Partition exchange/split/drop duration.
- Statistics gather/refresh duration.
- Storage of table, local indexes, and global indexes.

Never claim a "10x faster query" without accounting for load, index, refresh, retention, and concurrency costs across the whole workload.

## 9. Collecting Execution Metrics

### 9.1. DBMS_XPLAN.DISPLAY_CURSOR

Example:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*),
       SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
```

Inspect `E-Rows` and `A-Rows`, `Starts`, `Buffers`, and `Reads`. If a query has many operations, find which operation consumes the most buffers/time rather than looking only at the root operation.

### 9.2. SQL trace and TKPROF

SQL Trace captures parse/execute/fetch, CPU, elapsed time, logical/physical reads, and wait details as configured. TKPROF formats trace files into readable reports.

In a lab session:

```sql
ALTER SESSION SET sql_trace = TRUE;

-- Run the workload to be measured here.

ALTER SESSION SET sql_trace = FALSE;
```

DBAs locate trace files and run TKPROF on the database host or administrative environment. Never enable system-wide tracing or trace sensitive data in production without proper plans and authorization.

### 9.3. SQL Monitor

SQL Monitoring is valuable for long-running SQL, parallel queries, or workloads needing per-operation visibility. View it via management tools or reporting packages. Using Real-Time SQL Monitoring and certain related features is subject to Oracle Tuning Pack/Diagnostics Pack licensing per contract and version. Verify entitlement before enabling in production.

### 9.4. V$SQL and module/action

Tag module/action names to filter metrics:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'PARTITION_BENCH',
        action_name => 'RANGE_MONTH_QUERY'
    );
END;
/
```

DBAs can then match `V$SQL`/`V$SESSION` by module/action. Reset after finishing the workload:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
```

Module/action tags distinguish benchmark queries from other SQL. Never reuse the same tag across unrelated tests when results must stay separate.

## 10. Optimizer Statistics for Partitioned Tables

### 10.1. Table, partition, and global statistics

The optimizer needs statistics at both table and partition levels. On partitioned tables, partition statistics describe individual slices; global statistics describe the entire table. If global stats are missing or unrepresentative, the optimizer can misestimate queries touching multiple partitions.

Gather:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_RANGE_LAB',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => TRUE
    );
END;
/
```

`GRANULARITY AUTO` lets Oracle choose appropriate statistics levels per object/configuration. For large partitioned tables, evaluate incremental statistics and gather policies instead of rescanning all data after every batch.

### 10.2. View partition statistics

```sql
SELECT partition_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS_RANGE_LAB'
  AND object_type = 'PARTITION'
ORDER BY partition_name;
```

View global/table statistics:

```sql
SELECT table_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS_RANGE_LAB'
  AND object_type = 'TABLE';
```

`object_type` values and columns may vary by dictionary view/release. Verify on your running version.

### 10.3. Incremental statistics

For very large partitioned tables, incremental statistics can use synopses to maintain global statistics from new partition stats instead of rescanning the whole table:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'ORDERS_RANGE_LAB',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Feature availability and usage conditions depend on version, partition type, and statistic type. Check preferences, synopses, and gather schedules; enabling incremental does not guarantee every gather avoids reading source data.

### 10.4. Histograms and partition skew

If December has many times more transactions than February, or one customer holds most data, table-wide stats may misrepresent individual cases. Histograms, partition stats, and extended stats can improve estimates in suitable workloads.

Do not automatically create histograms on every partition key column. Review bind sensitivity, NDV, distributions, and actual rows before altering `method_opt`.

### 10.5. Statistics after partition maintenance

`ADD`/`SPLIT`/`MERGE`/`EXCHANGE`/`TRUNCATE`/`DROP` partition operations can alter metadata and statistics. Afterward, verify:

- Whether new partitions have statistics.
- Whether global statistics remain representative.
- Whether index partitions remain usable.
- Whether partition exchange preserved/imported appropriate statistics.
- Whether query plans shifted due to cardinality estimates.

Establish a dedicated stats-gathering step for newly loaded or heavily modified partitions.

## 11. Local Indexes and Global Indexes in Benchmarks

### 11.1. Local prefixed index

A local index is partitioned in alignment with the table's partitions:

```sql
CREATE INDEX ix_orders_local_date_customer
ON orders_range_lab(order_date, customer_id)
LOCAL;
```

Each index partition holds keys for the matching table partition. Local indexes fit queries with partition pruning and simplify certain partition maintenance operations.

### 11.2. Local nonprefixed index

A local index does not have to start with the partition key:

```sql
CREATE INDEX ix_orders_local_customer
ON orders_range_lab(customer_id)
LOCAL;
```

Queries filtering only on `CUSTOMER_ID` may have to probe index partitions across many partitions because there is no predicate on `ORDER_DATE`. Include this case in benchmarks; a local index does not turn a customer lookup into a single table-wide probe.

### 11.3. Global index

A global index spans multiple or all table partitions:

```sql
CREATE INDEX ix_orders_global_customer
ON orders_range_lab(customer_id)
GLOBAL;
```

Global indexes support `CUSTOMER_ID` lookups without the partition key and avoid opening each local index partition. However, `DROP`/`TRUNCATE`/`EXCHANGE` partition operations can affect global indexes and require an appropriate maintenance strategy.

### 11.4. Comparing costs

| Criterion | Local index | Global index |
|---|---|---|
| Scope | Matches table partitions/subpartitions | Multiple or all partitions |
| Queries with pruning | Can access only matching index partitions | Uses global index |
| Queries without partition key | May need to probe many index partitions | Can look up via global key |
| Partition maintenance | Usually easier to isolate | May require global index update/rebuild/maintenance |
| Administration | Many index partitions | One broad-scope index structure |

There is no right choice for every table. Measure both queries and partition maintenance. Local and global indexes can coexist if the workload demands it.

### 11.5. Checking index status after maintenance

Some partition DDL can make global indexes unusable if appropriate options are omitted. For supported operations, `UPDATE GLOBAL INDEXES` or matching options can be used:

```sql
ALTER TABLE orders_range_lab
TRUNCATE PARTITION p2026_01
UPDATE GLOBAL INDEXES;
```

Exact syntax, duration, and online capability depend on release/index type. Measure both DDL time and index recovery time; never omit this from TCO calculations.

## 12. Partition-Wise Joins

### 12.1. Full and partial partition-wise joins

Partition-wise joins can split a join into smaller pieces across corresponding partitions. With a full partition-wise join, two tables are compatibly partitioned on the join key and can join independent partition pairs. A partial partition-wise join partitions/distributes one side to match the partitioned side in certain plans.

Potential benefits include:

- Reduced data exchanged between parallel workers.
- Higher parallel scalability.
- Smaller intermediate memory/temp footprint.

Eligibility depends on partitioning schemes, join predicates, partition-wise compatibility, and parallel settings.

### 12.2. Fact/dimension example

Suppose two large fact tables are both partitioned by date:

```sql
SELECT f.order_date,
       SUM(f.amount)
FROM sales_fact_partitioned f
JOIN returns_fact_partitioned r
  ON r.order_date = f.order_date
 AND r.product_id = f.product_id
GROUP BY f.order_date;
```

This is a structural example only. For a partition-wise join to help, both sides must have partitioning compatible with the join keys and joined data. Partitioning both by `ORDER_DATE` without matching join conditions is not enough.

### 12.3. Reading the plan

Inspect `DBMS_XPLAN` to identify partition-wise join operations or parallel distributions. Operation names depend on plan and release. Check:

- `PSTART`/`PSTOP` on each row source.
- `PX SEND`/`PX RECEIVE` and distribution method.
- Row counts before/after the join.
- Buffers, reads, CPU, and elapsed time.
- Skew across workers/partitions.

A plan using parallel execution is not automatically a partition-wise join. Read the entire plan tree and predicates.

## 13. Partitioning and DML Workloads

### 13.1. INSERT

`INSERT` must determine the target partition from the partition key. With daily/monthly range partitioning, new rows route to the partition covering that date. If late-arriving data lands in an older partition, corresponding local indexes and partition stats must also stay maintained.

Measure:

- Insert rows/second.
- CPU and redo/undo.
- Index maintenance.
- Partition routing overhead.
- Contention on hot partitions/indexes.

### 13.2. Updating the partition key

If an `UPDATE` modifies the partition key, the row may have to move from one partition to another. Oracle permits row movement when `ENABLE ROW MOVEMENT` is set:

```sql
ALTER TABLE orders_range_lab ENABLE ROW MOVEMENT;
```

If row movement is disabled, updates that would move a row across partitions can fail. Enabling row movement affects `ROWID`s and applications relying on `ROWID`; verify before changing.

### 13.3. Retention deletion

Row-by-row deletion:

```sql
DELETE FROM orders_range_lab
WHERE order_date < DATE '2025-01-01';
```

can generate heavy undo/redo and index maintenance. When an entire old partition is no longer needed, `DROP`/`TRUNCATE` partition is usually a better lifecycle approach:

```sql
ALTER TABLE orders_range_lab
DROP PARTITION p2024_12
UPDATE GLOBAL INDEXES;
```

Partition DDL has different transaction semantics from DML; it typically performs an implicit commit. Never place it inside a business transaction expecting `DELETE`-style rollback.

### 13.4. MERGE and batch loads

`MERGE` or `INSERT SELECT` into a partitioned table still requires evaluating partition keys, local/global indexes, and how many partitions are touched. A monthly batch load may touch just one partition, whereas mixed multi-year data distributes across many partitions.

### 13.5. Partition exchange

Partition exchange swaps a staging table's segment with a target partition:

```sql
ALTER TABLE orders_range_lab
EXCHANGE PARTITION p2026_02
WITH TABLE orders_stage_feb
INCLUDING INDEXES
WITHOUT VALIDATION;
```

This illustrates the syntax form only. Both sides must have compatible columns, data types, and indexes as required; use `WITHOUT VALIDATION` only when data has been verified to belong to the target partition. If that assumption fails, data can sit outside logical ranges. Account for constraints, indexes, statistics, and global index maintenance.

## 14. Scenarios Where Partitioning Does Not Help or Slows Things Down

### 14.1. No predicate on the partition key

Query:

```sql
SELECT *
FROM orders_range_lab
WHERE customer_id = :customer_id;
```

If partitioned by `ORDER_DATE`, Oracle may have to access many partitions. A local `CUSTOMER_ID` index can be probed in each partition; a global index may fit better while introducing different maintenance costs.

### 14.2. Queries routinely read most of the table

If a report needs 80% of the data, pruning eliminates only a small slice. A full scan or parallel scan may still be the best plan. Splitting a table into partitions does not erase the cost of reading required rows.

### 14.3. Too small or too many partitions

Too many partitions/subpartitions increase:

- Metadata and dictionary overhead.
- Number of objects/index partitions to manage.
- Parse/optimization cost in some queries.
- Statistics and maintenance work.
- Number of branches evaluated when queries touch many partitions.

Choose granularity based on data size, retention, and queries. Do not create daily partitions for a few rows per day without a concrete operational reason.

### 14.4. Partition skew

A single partition holding most of the data can become a bottleneck. Hash partitioning can help distribute evenly by key, yet if the key is unsuitable or one key is hot, skew still persists.

### 14.5. Unsuitable indexes

Partitioning does not replace index design. If queries filter on other columns, missing or unsuitable indexes can force Oracle to scan many blocks even after pruning some partitions.

### 14.6. Missing or stale statistics

The optimizer can misestimate row counts per partition and pick poor join methods or parallel degrees. Bad plans are not necessarily caused by partitioning itself; inspect statistics and actual rows.

### 14.7. DML and storage overhead

Every partition has metadata and potentially local index partitions. `INSERT`/`UPDATE` must maintain those structures. A write-heavy OLTP workload whose queries do not filter by the partition key may not gain commensurate benefits.

## 15. Concurrency Benchmarks and Realistic Load

### 15.1. Single-session tests do not represent production

A query running faster in one session does not prove throughput increases with 100 sessions. Concurrency exposes:

- CPU saturation.
- I/O throughput limits.
- Lock/index contention.
- Buffer cache pressure.
- Parallel execution resource contention.
- Connection pool bottlenecks.

Run workloads with representative session counts and realistic `SELECT`/`INSERT`/`UPDATE`/`DELETE` mixes.

### 15.2. Designing a test matrix

| Test | Sessions | Query mix | Objective |
|---|---:|---|---|
| A | 1 | Monthly `SELECT` | Measure isolated pruning |
| B | 10 | Monthly `SELECT` + customer | Measure read contention |
| C | 25 | `SELECT` + `INSERT` | Measure concurrent read/write |
| D | 25 | `SELECT` + `UPDATE`/`DELETE` | Measure DML and index maintenance |
| E | Peak load | Production workload mix | Measure capacity and tail latency |

Numbers are illustrative only. Choose concurrency based on your real system and test environment limits, and never generate unexpected load on production.

### 15.3. Keep workloads identical

For each table design:

- Use the same bind value sets and frequency distributions.
- Use the same session count and think time.
- Use the same commit frequency.
- Use the same isolation level and connection pool.
- Use the same data and controlled cache state.
- Run long enough to pass warm-up and observe steady state.

Never run A when the database is idle and B while another batch runs. Record background load, checkpoints, backups, and maintenance jobs.

### 15.4. Comparing latency and throughput

Example results table:

| Metric | Heap baseline | Partitioned | Delta |
|---|---:|---:|---:|
| Monthly SELECT p50 |  |  |  |
| Monthly SELECT p95 |  |  |  |
| Customer SELECT p95 |  |  |  |
| Requests/second |  |  |  |
| Buffer gets/request |  |  |  |
| Physical reads/request |  |  |  |
| INSERT rows/second |  |  |  |
| Retention operation time |  |  |  |
| Storage table + indexes |  |  |  |

Fill in actual measured figures, never assumptions. A solid outcome demonstrates improvements on target queries while the overall workload still meets SLAs.

## 16. Step-by-Step Benchmark Process

### Step 1 — Capture baseline

Record:

- Current DDL.
- Row counts, table sizes, indexes, and partitions (if any).
- `SQL_ID`, SQL text, and bind distributions.
- Plans, `E-Rows`/`A-Rows`, buffers, reads, CPU, and elapsed time.
- Throughput and latency percentiles.
- Statistics timestamps.

### Step 2 — Create a partitioned test table

Create a new table with identical columns, constraints, and data. Never `ALTER` production just to test. Use controlled CTAS or `INSERT SELECT`; then recreate required constraints, indexes, grants, triggers, and statistics since CTAS does not automatically copy all schema attributes.

### Step 3 — Load identical data

Reconcile:

```sql
SELECT COUNT(*) FROM orders_heap_lab;
SELECT COUNT(*) FROM orders_range_lab;
```

Compare checksums/aggregates by business keys and date ranges. Matching `COUNT`s alone do not prove identical values.

### Step 4 — Create equivalent indexes

Create baseline heap indexes and local/global indexes for the partitioned table per workload design. Document index differences as part of the evaluated design rather than an overlooked variable.

### Step 5 — Gather statistics

Gather table/partition/index statistics using the same policy and check stale stats.

### Step 6 — Run SQL with representative binds

Run single-partition, multi-partition, full-range, and non-partition-key queries. Capture actual plans via `DISPLAY_CURSOR`.

### Step 7 — Run concurrent workloads

Use an approved load-testing tool or lab harness. Keep session counts, durations, and mixes identical.

### Step 8 — Measure DML and maintenance

Measure `INSERT`/`UPDATE`/`DELETE`, partition exchange, drop/truncate, index maintenance, and stats gathering.

### Step 9 — Summarize and explain

State which queries improved, which did not, why pruning occurred or failed to occur, and which costs increased.

### Step 10 — Decide

Deploy only when workload and operational gains outweigh storage, indexing, refresh, maintenance, migration, and administrative costs.

## 17. Controlled Comparison Lab Example

The following examples create two simple tables. Use a dedicated lab schema and scale sizes to available resources.

### 17.1. Create the heap table

```sql
CREATE TABLE orders_heap_lab (
    order_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    status_code VARCHAR2(20 CHAR) NOT NULL
);
```

### 17.2. Create the range-partitioned table

```sql
CREATE TABLE orders_range_lab (
    order_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    status_code VARCHAR2(20 CHAR) NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_04 VALUES LESS THAN (DATE '2025-05-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

### 17.3. Load identical data

Suppose source table `ORDERS_SOURCE` holds the lab data:

```sql
INSERT INTO orders_heap_lab (
    order_id, order_date, customer_id, total_amount, status_code
)
SELECT order_id, order_date, customer_id, total_amount, status_code
FROM orders_source;

INSERT INTO orders_range_lab (
    order_id, order_date, customer_id, total_amount, status_code
)
SELECT order_id, order_date, customer_id, total_amount, status_code
FROM orders_source;

COMMIT;
```

If the source table is large, load in batches under identical conditions and commit policies. Ensure every `order_date` maps to a partition or `pmax`.

### 17.4. Create equivalent indexes

```sql
CREATE INDEX ix_orders_heap_date
ON orders_heap_lab(order_date);

CREATE INDEX ix_orders_range_date_local
ON orders_range_lab(order_date)
LOCAL;

CREATE INDEX ix_orders_range_customer_local
ON orders_range_lab(customer_id)
LOCAL;

CREATE INDEX ix_orders_range_customer_global
ON orders_range_lab(customer_id)
GLOBAL;
```

You do not necessarily create both local and global customer indexes in a production design; the lab lets you compare trade-offs. On the heap baseline, create the corresponding customer index for a fair comparison.

### 17.5. Gather statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_HEAP_LAB',
        cascade => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_RANGE_LAB',
        granularity => 'AUTO',
        cascade => TRUE
    );
END;
/
```

### 17.6. Query a single month

Heap:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_heap_lab
WHERE order_date >= DATE '2025-02-01'
  AND order_date <  DATE '2025-03-01';
```

Partitioned:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= DATE '2025-02-01'
  AND order_date <  DATE '2025-03-01';
```

Inspect `DISPLAY_CURSOR` for each SQL, recording `PSTART`/`PSTOP`, `A-Rows`, `Buffers`, and `Reads`. On small tables or warm caches, elapsed times may look similar even when pruning works properly.

### 17.7. Query without the partition key

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE customer_id = :customer_id;
```

Run with the local customer index and with the global customer index in separate configurations. Observe how many index partitions are probed and the maintenance cost of each choice.

### 17.8. Query across multiple months

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       status_code,
       COUNT(*),
       SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= DATE '2025-01-01'
  AND order_date <  DATE '2025-05-01'
GROUP BY status_code;
```

This query touches all created range partitions. Partitioning can still assist parallelism/partition-wise operations, but pruning does not eliminate data to read.

### 17.9. Verify identical results

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_date) AS min_date,
       MAX(order_date) AS max_date
FROM orders_heap_lab;

SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_date) AS min_date,
       MAX(order_date) AS max_date
FROM orders_range_lab;
```

Also reconcile by month, status, and business keys. If row-by-row confirmation is needed, compare both directions with `MINUS` on appropriate columns in the lab.

## 18. Interpreting Results and Making Decisions

### 18.1. When partitioning clearly pays off

Evidence usually includes:

- Queries with partition predicates access only one or a few partitions.
- `A-Rows` and buffers drop proportionally to the data scope read.
- p95 latency and CPU drop under realistic workloads.
- Throughput rises or SLAs hold better under high concurrency.
- Retention/maintenance operations drop significantly in duration.
- Additional index/statistics/storage costs stay within budget.

### 18.2. When only the plan changes while performance stays flat

Pruning may occur, yet the table is small, data is already cached, the query returns few rows, or the bottleneck lies in network/application layers. This proves pruning works, without yet proving partitioning brings sufficient operational gain.

### 18.3. When one query speeds up while overall workload degrades

A reporting query might drop 80% in runtime while insert throughput falls and customer lookups slow down due to probing many local index partitions. Weight results by traffic share and SLAs per category; never optimize one isolated SQL at the expense of the primary workload.

### 18.4. Calculating overall benefit

Build a weighted summary table:

| Workload group | Request share | p95 change | Throughput change | SLA met? |
|---|---:|---:|---:|---|
| Date range |  |  |  |  |
| Customer lookup |  |  |  |  |
| Report aggregate |  |  |  |  |
| Insert batch |  |  |  |  |
| Retention maintenance |  |  |  |  |

For queries, weighted latency helps show trends, though it does not replace overall percentiles on the full request stream. For batch/maintenance, measure completion time and system impact while running.

### 18.5. Conclusions must state scope and limits

A rigorous conclusion explicitly documents:

- Oracle release/RU and configuration.
- Test row count and partition count.
- Partition key and granularity.
- Indexes and statistics.
- SQL/bind distributions and session counts.
- Cache state, run duration, and iteration count.
- Measured metrics.
- Which queries improved and which did not.
- Remaining operational costs and risks.

Never extrapolate findings from a tiny schema or single query into a system-wide guarantee.

## 19. Partitioning Benefit Verification Checklist

- [ ] Representative workload and SQL statements are documented.
- [ ] Partition key aligns with real predicates or data lifecycle.
- [ ] Heap and partitioned tables hold identical logical data.
- [ ] Indexes, constraints, data types, and binds are compared fairly.
- [ ] Table, partition, and index statistics have been gathered.
- [ ] Execution plans show `PSTART`/`PSTOP` and partition pruning is interpreted properly.
- [ ] Actual rows, buffers, reads, and elapsed times are collected.
- [ ] Queries both with and without the partition key are included.
- [ ] Concurrent read/write workloads are tested.
- [ ] Insert/update/delete and retention maintenance are measured.
- [ ] Local/global indexes and index partition statuses are verified.
- [ ] Partition skew and partition count are checked.
- [ ] Tests are repeated with controlled cache and background load.
- [ ] p50/p95/p99 or appropriate latency distributions are captured.
- [ ] Storage, redo/undo, stats, and operational effort are compared.
- [ ] Conclusions explicitly state test conditions and applicability limits.

## 20. Self-Check Questions

1. How does partitioning differ from indexing in objective?
2. How does partition pruning reduce data access work?
3. Which workloads fit range, interval, list, hash, and composite partitioning?
4. What do `PSTART`/`PSTOP` represent in an execution plan?
5. How does static pruning differ from dynamic pruning?
6. Why can bind variables cause `PSTART`/`PSTOP` to show `KEY` while still pruning?
7. How can a `TRUNC(partition_key)` predicate affect pruning?
8. Why must `DATE`/`TIMESTAMP` binds be passed with proper data types?
9. How does `EXPLAIN PLAN` differ from `DISPLAY_CURSOR` with `ALLSTATS LAST`?
10. How do `E-Rows` and `A-Rows` differ?
11. Why must a query without the partition key be included in benchmarks?
12. What are the trade-offs between local indexes and global indexes?
13. What compatibility conditions does a partition-wise join require?
14. Why does partitioning not automatically speed up queries that read most of a table?
15. What problems do partition skew and excessive partition counts cause?
16. How do partition statistics and global statistics support the optimizer?
17. In what scenarios are incremental statistics beneficial?
18. Why must concurrency be measured instead of running only a single session?
19. Which metrics prove reduced I/O/CPU and improved latency?
20. Why must DML, index, retention, and statistics costs be included?
21. When can `DROP`/`TRUNCATE` partition replace bulk `DELETE`?
22. What structural and data conditions does partition exchange require?
23. How do you control cache state for fair benchmarking?
24. What information must a benchmark conclusion record to be reproducible?

**Key takeaway:** partitioning is valuable when it reduces actual workload work or simplifies lifecycle data operations. Prove pruning via `PSTART`/`PSTOP` and execution plans, then prove impact via actual rows, buffer gets, physical reads, CPU, latency, and throughput under representative load. Measure queries lacking the partition key, DML, index maintenance, statistics, and retention operations as well. Base decisions on overall results rather than merely having a partitioned table or a nicer-looking execution plan.
