# Clustering Factor, Selectivity, and Blocks to Access in Oracle Database

When Oracle executes a query that could use an index, the optimizer must estimate the cost of two main options: reading the index and fetching table rows by ROWID, or reading many table blocks directly via a full table scan. An index can locate keys very quickly yet still be a poor choice if the rows to fetch are scattered across many table blocks.

Three concepts help explain that decision:

- **Clustering factor:** a statistic describing the correlation between index key order and the physical placement of rows in the table.
- **Selectivity:** the estimated fraction of rows matching a filter condition; the fewer rows a condition returns, the more selective it generally is.
- **Blocks to access:** the estimated I/O work to read index leaf blocks and table blocks containing matching rows, compared with scanning the table.

A low clustering factor usually favors an index range scan because ROWIDs in index order tend to sit close together in the same table blocks. A high clustering factor can turn table access by ROWID into many scattered reads. Selectivity tells how many rows are needed; clustering factor helps the optimizer estimate how many blocks fetching those rows will cost. Both influence cost, yet no single metric alone can conclude that an index is always faster than a full scan.

## 1. What Must an Index Scan Read?

An Oracle B-tree index consists of a root block, branch blocks if the tree has multiple levels, and leaf blocks containing keys and ROWIDs. When a query uses an index to locate rows in a table, the typical flow is:

1. Traverse from root through branch blocks to the appropriate leaf block.
2. Read leaf blocks containing matching keys.
3. Extract ROWIDs from index entries.
4. Use ROWIDs to visit table blocks for columns not already in the index.

Example:

~~~sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = 100;
~~~

If there is an index on `CUSTOMER_ID`, Oracle can use it to find the matching ROWIDs. However, if `ORDER_DATE` and `TOTAL_AMOUNT` are not in the index, Oracle still needs to read the table blocks containing those rows.

### 1.1 Index blocks and table blocks are two separate parts of the work

| Component | Contents | Related statistics |
|---|---|---|
| Root/branch | Guides navigation to the target key range | `BLEVEL` |
| Leaf | Stores index keys and ROWIDs | `LEAF_BLOCKS`, `DISTINCT_KEYS` |
| Table | Stores the actual rows fetched via ROWID | `BLOCKS`, `NUM_ROWS`, `CLUSTERING_FACTOR` |

An index may be very small, yet if every ROWID points to a different table block, the table access phase remains expensive. Conversely, an index with many leaf blocks can still be efficient if the query reads only a narrow key range.

### 1.2 Queries may not need to visit the table

If every column to return and every column to evaluate is present in the index, Oracle can satisfy the query solely from the index. This is commonly referred to as index-only access or a covering index.

Example index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date);
~~~

Query selecting only those two columns:

~~~sql
SELECT customer_id, order_date
FROM orders
WHERE customer_id = 100;
~~~

Oracle may omit `TABLE ACCESS BY INDEX ROWID`. When the table is not accessed, clustering factor has little direct impact on table block reads for that query. Index blocks must still be read and index size weighed.

## 2. What Is Clustering Factor?

### 2.1 Definition

Clustering factor (CF) is an index statistic reflecting how many times the ROWID sequence in the index switches from one table block to another when traversing the index in key order.

Imagine reading index entries from smallest key to largest key:

- If consecutive entries frequently point to rows in the same table block, block switches are few.
- If each consecutive entry typically points to a different table block, block switches are many.

A low clustering factor indicates that physical row order in the table aligns fairly well with index key order. A high clustering factor indicates that rows in index order are scattered across the table.

### 2.2 Illustration of low CF

Suppose an index is ordered by `ORDER_ID` and rows in the table are also stored roughly in `ORDER_ID` order:

~~~text
Index key order:   1   2   3   4   5   6   7   8
ROWID table block: A   A   A   B   B   B   C   C

Block transitions: A -> B -> C
Approximate transitions: 3
~~~

When an index range scan reads many consecutive keys, Oracle can fetch multiple rows from one block before moving to the next. A low CF is usually close to the number of table blocks holding data.

### 2.3 Illustration of high CF

If rows are scattered:

~~~text
Index key order:   1   2   3   4   5   6   7   8
ROWID table block: A   F   C   H   B   G   D   E

Block transitions: A -> F -> C -> H -> B -> G -> D -> E
Approximate transitions: 8
~~~

Each index entry can point to a different block. When a query needs many rows, table access by ROWID can trigger many scattered block reads.

### 2.4 Typical value range

For a standard B-tree index on a heap table, CF generally ranges from roughly the number of table blocks to roughly the number of rows in the table:

- CF close to table `BLOCKS`: data is relatively ordered with respect to the index key.
- CF close to `NUM_ROWS`: data is scattered with respect to the index key.

This is an intuitive interpretation, not an absolute good/bad threshold. You must look at table scale, query type, selectivity, returned columns, and execution plans.

### 2.5 CF is not the number of distinct blocks

Do not interpret clustering factor as the count of distinct table blocks referenced by the index. While scanning the index, a block can be left and revisited later. Every transition from one block to a different block contributes to CF.

Thus, CF can exceed the number of physical blocks in the table. It is closer to the count of block transitions along the ROWID sequence in index order than to the distinct block count.

## 3. Where Is Clustering Factor Stored?

Oracle stores clustering factor in index statistics. View it via `USER_INDEXES`:

~~~sql
SELECT index_name,
       table_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       num_rows,
       clustering_factor,
       avg_leaf_blocks_per_key,
       avg_data_blocks_per_key,
       last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

Key columns:

| Column | Meaning |
|---|---|
| `BLEVEL` | Number of branch levels in the index structure as recorded by Oracle stats |
| `LEAF_BLOCKS` | Number of leaf blocks in the index |
| `DISTINCT_KEYS` | Number of distinct index keys |
| `NUM_ROWS` | Number of index entries recorded in stats |
| `CLUSTERING_FACTOR` | Frequency of table block transitions in index key order |
| `AVG_LEAF_BLOCKS_PER_KEY` | Average leaf blocks per key |
| `AVG_DATA_BLOCKS_PER_KEY` | Average table blocks associated with a key |
| `LAST_ANALYZED` | Timestamp of the most recent statistics gathering |

Check table statistics:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       empty_blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
~~~

`BLOCKS` in statistics is the block count recorded during statistics gathering; do not mechanically equate it with allocated segment blocks or blocks currently holding rows in all cases.

## 4. Selectivity and Cardinality

### 4.1 Selectivity is the fraction of rows matching a predicate

Selectivity of a filter predicate can be expressed as:

\[
\text{Selectivity} =
\frac{\text{Estimated rows matching the condition}}
{\text{Total rows in the input set}}
\]

For a table with 1,000,000 rows:

- Predicate returning 100 rows: selectivity around 0.0001 (0.01%).
- Predicate returning 100,000 rows: selectivity around 0.1 (10%).
- Predicate returning 800,000 rows: selectivity around 0.8 (80%).

A condition returning very few rows is often called highly selective. To avoid terminology confusion, this lesson always specifies the ratio or estimated row count clearly.

### 4.2 Cardinality is the estimated row count

Cardinality is the number of rows the optimizer estimates a row source will return. For a table with $N$ rows and a predicate with selectivity $S$, basic cardinality can be thought of as:

\[
\text{Cardinality} \approx N \times S
\]

For example, 1,000,000 rows with selectivity 0.001 yields an estimated cardinality of about 1,000 rows.

Cardinality affects the cost of subsequent steps: number of ROWIDs, number of table accesses, join data volume, and access path selection.

### 4.3 Equality selectivity from NDV

If a column has `NUM_DISTINCT` (NDV) distinct values and a roughly uniform distribution, the simple estimate for the predicate:

~~~sql
WHERE status_code = 10
~~~

is:

\[
\text{Selectivity} \approx \frac{1}{\text{NDV}}
\]

If `STATUS_CODE` has 10 uniformly distributed values, each value accounts for roughly 10% of rows. However, if one status makes up 90% and the remaining statuses are rare, the uniformity assumption will be inaccurate.

### 4.4 Index selectivity vs. predicate selectivity

Two uses of the term are often mixed up:

- Predicate selectivity: the fraction of rows matching a specific condition.
- Index key selectivity: the distinctiveness of keys, typically inspected via `DISTINCT_KEYS` relative to `NUM_ROWS` or average rows per key.

Example:

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       CASE
         WHEN num_rows > 0
         THEN distinct_keys / num_rows
       END AS distinct_key_ratio
FROM user_indexes
WHERE table_name = 'ORDERS';
~~~

For a unique index on a non-NULL column, each entry has its own key so the distinct key ratio is close to 1. For a nonunique index with many rows per key, the ratio is lower. This indicates key distinctiveness, not the selectivity of every combined predicate on the table.

## 5. Column Statistics, Histograms, and Data Distribution

### 5.1 NUM_DISTINCT does not tell the whole story

Suppose column `STATUS` has 3 values:

| STATUS | Row count | Percentage |
|---|---:|---:|
| ACTIVE | 900,000 | 90% |
| PENDING | 90,000 | 9% |
| CLOSED | 10,000 | 1% |

`NDV = 3`. If the optimizer assumes uniformity, each value gets ~33.3% of rows. That is visibly wrong for both `ACTIVE` and `CLOSED`.

Histograms help the optimizer describe column distribution skew and estimate selectivity more accurately for certain predicates.

### 5.2 Viewing column statistics

~~~sql
SELECT column_name,
       num_distinct,
       density,
       num_nulls,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

Information such as `NUM_DISTINCT`, `NUM_NULLS`, `DENSITY`, and `HISTOGRAM` shows what statistics the optimizer has available. Exact `DENSITY` semantics depend on histogram type and Oracle version; do not substitute a single formula for the optimizer's estimation model.

### 5.3 Gathering histograms when needed

You can instruct `DBMS_STATS` to gather statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
~~~

`SIZE AUTO` lets Oracle decide which columns need histograms based on workload and policy statistics. Do not create histograms on every column out of habit; histograms can make plans dependent on bind values and increase plan management complexity.

### 5.4 Bind variables and data skew

A SQL statement:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE status = :p_status;
~~~

might be invoked with `ACTIVE` (very many rows) or `CLOSED` (very few rows). An access path good for one value may be poor for the other.

Oracle has mechanisms such as bind peeking and adaptive cursor sharing to handle some skewed bind selectivity scenarios. However, behavior depends on version, statistics, cursors, and workload. When you see the same SQL having multiple child cursors or different plans, check bind values, histograms, and execution statistics.

### 5.5 Correlation between columns

If a query has:

~~~sql
WHERE region_id = 10
  AND status = 'CLOSED'
~~~

and `REGION_ID` correlates with `STATUS`, assuming independence between the two predicates can misestimate cardinality. Extended statistics for column groups can help the optimizer capture correlation:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           USER,
           'ORDERS',
           '(REGION_ID, STATUS)'
       )
FROM dual;
~~~

After creating extended statistics, gather stats appropriately and re-check cardinality in the execution plan. Do not create column groups for every column combination; choose based on real predicates and evidence of misestimation.

## 6. How Does Clustering Factor Affect Table Access?

### 6.1 Two indexes with identical selectivity can still have different costs

Suppose the same predicate returns 1,000 rows:

- Index A has low CF: rows in index order lie in relatively few table blocks.
- Index B has high CF: rows in index order are scattered across many table blocks.

The result row count is identical, yet the number of table blocks to access can differ dramatically. Index B may generate far more random table accesses.

### 6.2 Low CF and index range scan

~~~text
Index entries by key
  k1 -> block A
  k2 -> block A
  k3 -> block A
  k4 -> block B
  k5 -> block B
  k6 -> block C

Table access:
  A, B, C
~~~

Multiple ROWIDs point to the same block; blocks can be reused in the buffer cache when reading nearby rows.

### 6.3 High CF and index range scan

~~~text
Index entries by key
  k1 -> block A
  k2 -> block X
  k3 -> block C
  k4 -> block Y
  k5 -> block B
  k6 -> block Z

Table access:
  A, X, C, Y, B, Z
~~~

Accesses can be scattered, generating random I/O. As cardinality grows, the cost of revisiting the table can make a full table scan cheaper.

### 6.4 CF does not directly equal the block count for a single predicate

Clustering factor is computed across the entire index order, whereas a query may scan only part of the index. The optimizer estimates table blocks for a predicate using multiple statistics and cost models, including CF, cardinality, table blocks, index leaf blocks, and other factors.

Do not use a mechanical formula like:

~~~text
query table blocks = clustering_factor * selectivity
~~~

to predict every plan accurately. That serves only as rough intuition in some cases. Oracle also accounts for ROWID distribution, key counts, caching, batching, partitioning, and CPU/I/O costs.

## 7. Estimating Block Counts and Comparing Access Paths

### 7.1 Index range scan

Conceptual cost of an index range scan breaks down into:

~~~text
Index access:
    root/branch traversal
  + leaf blocks to read

Table access:
    table blocks containing matching ROWIDs

Total cost:
    index work + table rowid work + CPU
~~~

For queries needing columns outside the index, table access can dominate total cost.

### 7.2 Full table scan

A full table scan reads segment blocks within the scan scope, typically leveraging multiblock I/O. Oracle can read multiple blocks in a single I/O operation depending on configuration, storage, and execution plan.

A full scan can be cheaper than an index range scan when:

- The predicate returns a large fraction of rows.
- High CF scatters ROWID table accesses.
- The table is small and can be read quickly in a few I/Os.
- The query needs most columns or nearly all rows.
- The index has many leaf blocks to read and still must visit the table.

### 7.3 Index range scan can be cheaper when

- The predicate returns few rows.
- The index key has good selectivity.
- CF is low or matching rows sit in few blocks.
- The query needs only columns present in the index.
- The index has appropriate structure and statistics.

### 7.4 There is no fixed selectivity threshold

There is no universal rule like "under 5% use index, over 5% use full scan." The crossover depends on:

- Clustering factor.
- Table block count.
- Index leaf block count and tree height.
- Row width and number of columns needed.
- MBRC and storage characteristics.
- Buffer cache and workload.
- Histograms, cardinality estimates, and bind values.
- Partition pruning, parallelism, and other predicates.

The optimizer picks the plan with the lowest estimated cost given statistics and environmental parameters. A plan sensible on a small table may differ from the optimal plan on a large table.

## 8. Example of Selectivity and CF Acting Together

Suppose a table has 1,000,000 rows, 20,000 table blocks, and an index on `CUSTOMER_ID`.

| Scenario | Estimated cardinality | CF | Interpretation |
|---|---:|---:|---|
| A | 100 rows | 20,000 | Very few rows; likely fetched from relatively few blocks |
| B | 100 rows | 900,000 | Few rows, though ROWIDs may scatter; index may still win, compare costs |
| C | 300,000 rows | 20,000 | Rows may be well clustered, yet total data volume is large |
| D | 300,000 rows | 900,000 | Many rows and scattered access; full scan may be attractive |

These numbers illustrate tendencies, not a cost formula. Scenario B can still have a good index range scan because only 100 rows are fetched; Scenario C does not automatically use an index just because CF is low.

Key points:

- Selectivity/cardinality determines how many rows must be fetched.
- Clustering factor helps estimate the dispersion of table access in index order.
- Leaf/table block counts and I/O patterns determine total work.
- The optimizer evaluates total cost rather than optimizing a single statistic in isolation.

## 9. Index Range Scan, Full Scan, and Index-Only Access

| Access path | Primary work | Role of CF |
|---|---|---|
| `INDEX RANGE SCAN` + `TABLE ACCESS BY INDEX ROWID` | Scans key range then fetches table rows | Critical because it determines table access dispersion |
| `INDEX RANGE SCAN` (index-only) | Reads index entries and returns indexed columns | Less critical because table is not visited |
| `INDEX UNIQUE SCAN` + `TABLE ACCESS BY INDEX ROWID` | Locates one unique key then fetches row | Usually one row; CF has less influence |
| `TABLE ACCESS FULL` | Scans table blocks | Index CF does not directly apply |
| `INDEX FAST FULL SCAN` | Reads full index as a data structure without key order | Minimal relevance if table is not visited |
| `TABLE ACCESS BY INDEX ROWID BATCHED` | Batches ROWIDs to improve table access | Can reduce actual random access, without changing the CF statistic |

### 9.1 BATCHED rowid access

Oracle can use `TABLE ACCESS BY INDEX ROWID BATCHED` to gather ROWIDs and visit table blocks with improved locality. This can reduce block switches compared with visiting each ROWID individually.

Batched access does not mean the clustering factor has become lower. CF is a statistic of the relationship between index order and row placement; batching is an execution technique that can lower table access cost for a query.

### 9.2 Index unique scan

If a predicate matches a unique key:

~~~sql
SELECT *
FROM orders
WHERE order_id = 10001;
~~~

Oracle can use `INDEX UNIQUE SCAN`. Because at most one index entry is located, table access cost is generally bounded to that row. Index-wide CF matters far less here than in a range scan returning thousands of rows.

### 9.3 Index fast full scan

`INDEX FAST FULL SCAN` reads all index leaf blocks as a data source, typically using multiblock I/O and without guaranteeing index order. If the index contains all columns needed by the query, it can be cheaper than a full table scan because the index segment is smaller than the table. This is a different access path from index range scan.

## 10. Why Does Index Rebuild Not Automatically Fix Clustering Factor?

Clustering factor describes the relationship between index key order and ROWID locations in the table. Rebuilding an index reorganizes the index structure, but it does not move table rows into different blocks sorted by the key.

Therefore:

- `REBUILD` can change leaf blocks, `blevel`, space allocation, and index structure.
- `REBUILD` is not a direct tool for reordering heap table data by an index key.
- CF generally does not improve significantly from an index rebuild alone if table row placement remains unchanged.

To improve CF, you must consider reorganizing table data by a critical access key—such as CTAS/reload in sorted order, table move/reorganization, or another storage design. After changing row placement, check and rebuild/recreate indexes as required by the operation.

### 10.1 Reorganizing a table involves trade-offs

A table has multiple indexes with different key orders. Physically ordering rows by `CUSTOMER_ID` may improve the CF of the `CUSTOMER_ID` index while worsening the CF of the `ORDER_DATE` index.

You cannot assume a single heap table can be physically sorted optimally for every index simultaneously. Prioritize critical access paths by workload, query frequency, selectivity, and write cost.

### 10.2 Index-organized tables

For tables where the primary key is the dominant access path, an index-organized table (IOT) stores table rows inside a B-tree structure ordered by primary key. An IOT can suit primary-key-centric access, though secondary indexes, row overflow, and update workloads must be weighed separately.

An IOT is a storage design choice, not a simple fix for the CF of every index on a heap table.

## 11. Gathering and Refreshing Optimizer Statistics

### 11.1 Gather table and index statistics

`DBMS_STATS` can gather table and index statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

`CASCADE => TRUE` requests gathering statistics for associated indexes. `AUTO_SAMPLE_SIZE` and `AUTO_DEGREE` let Oracle choose appropriate sampling and parallelism for the version and environment.

### 11.2 Check whether stats are stale

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

Stale status shows whether statistics may be outdated after substantial changes. Stale stats alone do not prove the optimizer picked a bad plan, yet they are a signal to inspect alongside the execution plan and workload.

### 11.3 Do not gather stats arbitrarily during peak hours

Gathering stats can consume CPU/I/O and alter plans for many SQL statements. For production systems:

- Identify an appropriate gathering window.
- Check current statistics and volume of data change.
- Use `DBMS_STATS` rather than `ANALYZE TABLE COMPUTE STATISTICS` for optimizer statistics.
- Consider pending statistics and controlled publishing when plan changes carry risk.
- Monitor SQL plans after publishing stats.

### 11.4 Pending statistics

Oracle supports gathering pending statistics to test and evaluate before publishing under appropriate configuration. This reduces the risk of unexpected plan regressions, though DBAs must manage preferences, sessions using pending stats, and publishing timing.

Do not treat pending stats as a mandatory step for every gather; it is a change-control tool for environments requiring strict plan governance.

## 12. Inspecting Execution Plans and Actual Block Counts

### 12.1 EXPLAIN PLAN only gives an estimated plan

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = 100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the plan generated for the statement under the environment and bind context at explain time. It does not provide actual rows or buffers from a real execution.

### 12.2 Gathering runtime statistics

You can use `GATHER_PLAN_STATISTICS`:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = 100;
~~~

Immediately after running the SQL:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

In the plan, inspect:

- `E-Rows`: optimizer's estimated rows.
- `A-Rows`: actual rows emitted by the row source.
- `Buffers`: logical reads, i.e., buffers accessed.
- `Reads`: physical reads recorded for the row source per format/runtime stats.
- `Operation`: `INDEX RANGE SCAN`, `TABLE ACCESS BY INDEX ROWID`, `TABLE ACCESS FULL`, etc.
- `Predicate Information`: access and filter conditions.

If `E-Rows` differs widely from `A-Rows`, investigate statistics, histograms, bind values, correlation, or predicate expressions before blaming CF.

### 12.3 Buffers do not equal physical disk reads

`Buffers` reflects logical I/O. A block can be read from the buffer cache and still count as a buffer get. Physical reads occur only when blocks must be fetched from storage depending on cache state and read mechanisms.

Therefore:

- High buffer gets can cause CPU/latch overhead even if physical reads are low.
- Physical reads depend on cache, workload, and storage.
- Comparing plans requires equivalent cache/workload conditions or sufficient repeated measurements.

### 12.4 Comparing actual plans

Do not glance at `INDEX RANGE SCAN` and declare it good. Inspect `TABLE ACCESS BY INDEX ROWID`, `A-Rows`, `Buffers`, `Reads`, and elapsed time together. An index range scan can read few index blocks yet visit very many table blocks.

## 13. Lab Example: Two Indexes, Two Clustering Factors

This lab creates a heap table with ascending `ORDER_ID` and cyclically repeating `CUSTOMER_ID`. When loaded roughly in `ORDER_ID` order, the `ORDER_ID` index tends to have a low CF, while the `CUSTOMER_ID` index tends to have a high CF because rows for the same customer are spread across many areas of the table.

Final physical row placement depends on how Oracle loads data, segment layout, parallelism, and environment. Therefore, measure CF after gathering stats; never treat `INSERT`/`CTAS` order as an absolute guarantee of physical row order.

### 13.1 Create the lab table

~~~sql
CREATE TABLE lab_orders AS
SELECT LEVEL AS order_id,
       MOD(LEVEL, 100) AS customer_id,
       MOD(LEVEL, 10) AS status_code,
       DATE '2026-01-01' + MOD(LEVEL, 365) AS order_date,
       CAST(LEVEL * 1.25 AS NUMBER(12,2)) AS total_amount,
       RPAD('X', 100, 'X') AS payload
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Create primary key or index on `ORDER_ID`:

~~~sql
ALTER TABLE lab_orders
ADD CONSTRAINT pk_lab_orders PRIMARY KEY (order_id);
~~~

Create an index on `CUSTOMER_ID`:

~~~sql
CREATE INDEX ix_lab_orders_customer
ON lab_orders (customer_id);
~~~

### 13.2 Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
~~~

### 13.3 Inspect clustering factors of both indexes

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       blevel
FROM user_indexes
WHERE table_name = 'LAB_ORDERS'
ORDER BY index_name;
~~~

Compare CF against `NUM_ROWS` and `BLOCKS` of the table:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len
FROM user_tables
WHERE table_name = 'LAB_ORDERS';
~~~

Typically, the `ORDER_ID` index shows a lower CF than the `CUSTOMER_ID` index under this load pattern. If results differ from expectation, check actual segment layout, stats, and how data was generated; that demonstrates CF is measured from actual ROWIDs rather than inferred from column names.

### 13.4 Compare query by ORDER_ID

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       payload
FROM lab_orders
WHERE order_id BETWEEN 50000 AND 50100;
~~~

Display plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

The `ORDER_ID` predicate returns ~101 consecutive rows in key order. If physical layout aligns, table blocks accessed usually exhibit good locality.

### 13.5 Compare query by CUSTOMER_ID

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       payload
FROM lab_orders
WHERE customer_id = 42;
~~~

Display the plan using `DBMS_XPLAN.DISPLAY_CURSOR` as above. This predicate returns roughly 1% of table rows. Because rows for the same customer are scattered across `ORDER_ID` positions, index access may visit many table blocks.

The optimizer may choose index range scan, batched rowid access, or full table scan depending on statistics and cost. Do not force a plan with hints in the baseline measurement; the goal is observing the optimizer's natural decision.

### 13.6 Test a query selecting only indexed columns

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id
FROM lab_orders
WHERE customer_id = 42;
~~~

The query needs only `CUSTOMER_ID`, already in the index. Oracle can resolve it via index access without revisiting the table. Compare `buffers` against the query fetching `PAYLOAD` to see how table access cost can dominate.

### 13.7 Test varying selectivity

Compare:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       payload
FROM lab_orders
WHERE customer_id = 42;
~~~

with:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       payload
FROM lab_orders
WHERE customer_id BETWEEN 0 AND 49;
~~~

The second predicate can return roughly half the table. Index range scan may no longer be economical; a full scan may be chosen. Inspect `E-Rows`/`A-Rows` and `buffers` rather than relying on a fixed percentage rule.

### 13.8 Clean up the lab table

Drop only objects you created in the lab schema once you confirm the data is no longer needed. DDL triggers an implicit commit:

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Do not run `DROP` on tables outside your lab.

## 14. Ways to Improve Locality and Clustering Factor

### 14.1 Load data in key access order

If the workload relies heavily on range scans by one key, loading data ordered by that key can place rows closer together in the table. However, verify physical placement after loading; SQL result order is not a contract guaranteeing block layout.

### 14.2 Table reorganization

CTAS/reload, table move, or reorganization tools can alter physical row placement. When reorganizing:

- Pick the sort key based on critical access paths.
- Evaluate downtime/online availability and row movement.
- Handle indexes, constraints, triggers, grants, statistics, and dependencies.
- Gather stats after completion.
- Compare workload before and after.

Reorganization can improve one index's CF while degrading another's. Do not do it just to optimize a rarely executed report.

### 14.3 Index rebuild is not table reorganization

Rebuilding an index reorganizes the index segment, not the rows in the heap table by key. If CF is high due to scattered ROWIDs, simply rebuilding the index will not fix the root cause.

### 14.4 Partitioning can reduce data scope

Partition pruning can reduce the number of partitions/table blocks to access. With local indexes, per-partition index statistics help the optimizer estimate within each partition. Partitioning addresses data scope and manageability; it does not automatically guarantee low CF for every local index.

### 14.5 Choose indexes matching the workload

Indexes do not only have read costs:

- `INSERT` must maintain index entries.
- `UPDATE` of indexed columns may have to update index entries.
- `DELETE` must maintain indexes and undo/redo.
- Many indexes increase storage and write overhead.

Do not add an index merely to make one query look faster without measuring total workload impact.

## 15. Other Factors Affecting Actual Block Counts

Clustering factor and selectivity are two major factors, yet actual block counts also depend on:

### 15.1 Buffer cache

Table blocks may already reside in the buffer cache. A logical access does not always incur a physical disk read. However, buffer gets still consume CPU and cache-management overhead.

### 15.2 Multiblock reads and storage

Full table scans can generally leverage multiblock reads. Index ROWID access is more single-block/random in nature, though batching and storage characteristics can shift costs.

### 15.3 Table width and selected column count

Selecting fewer columns reduces data read and moved. If an index covers the query, table access is avoided. If many non-indexed columns are needed, table block accesses increase.

### 15.4 Partition pruning

Predicates on partition keys can eliminate unneeded partitions before index or table access. Blocks to access must be evaluated within the remaining partitions.

### 15.5 Parallel query

Parallel full scans can cut elapsed time by using multiple processes, at the expense of higher resource consumption. Never compare elapsed time alone while ignoring CPU, I/O, and impact on concurrent workloads.

### 15.6 Compression and row migration/chaining

Compression, row migration, and row chaining can alter the number of blocks read to fetch a row. Clustering factor does not capture all of these costs. When a row spans multiple blocks, table access may require extra I/O beyond the block holding the row header.

## 16. Common Mistakes and Misconceptions

| Mistake/misconception | Reality | How to handle |
|---|---|---|
| Low CF means the index has few leaf blocks | CF measures locality between index keys and table row placement | Inspect `LEAF_BLOCKS` and `CF` separately |
| CF is the number of distinct table blocks | CF counts block transitions in index order | Do not equate CF with distinct block count |
| High CF makes the index useless | Very selective predicates or index-only queries can still benefit | Measure cardinality and plans |
| Selectivity depends only on NDV | Skew, histograms, `NULL`s, and correlation affect estimates | Check column/extended stats |
| Predicates returning 5% always use an index | No universal threshold; CF and I/O models differ | Compare costs and actual runtime |
| Rebuilding an index lowers CF | Rebuild does not reorder heap table rows | Reorganize the table only with solid justification |
| `ORDER BY` on `SELECT` guarantees physical row order | `ORDER BY` only guarantees query result order | Measure CF after loading and gathering stats |
| All indexes on a table can have low CF | One physical order cannot optimize every key order | Prioritize critical workloads |
| Buffers means physical disk reads | Buffers are logical reads | Inspect both `Buffers` and `Reads` |
| `EXPLAIN PLAN` shows actual I/O | It mainly shows an estimated plan | Use `DISPLAY_CURSOR` with runtime stats |
| `E-Rows` always equals `A-Rows` | Cardinality estimates can be off | Investigate stats, histograms, binds, and correlation |
| Index range scan is always faster than full scan | Table access via ROWID can be very expensive | Inspect the full plan |
| CF changes per predicate | CF is an index-wide statistic; predicates scan subsets | Distinguish index statistics from query estimates |
| Checking CF alone is enough to pick an index | Also need selectivity, leaf blocks, table blocks, cache, and workload | Evaluate holistically |

## 17. Checklist for Analyzing an Index-Using Query

When a query is slow, follow this sequence:

1. Identify the actual SQL, bind values, and current execution plan.
2. Inspect `E-Rows` and `A-Rows` at every row source.
3. Inspect access/filter predicates and cardinality estimates.
4. Check table `NUM_ROWS`, `BLOCKS` and index `LEAF_BLOCKS`, `BLEVEL`, `DISTINCT_KEYS`, `CLUSTERING_FACTOR`.
5. Check column statistics, histograms, `NULL`s, and correlations.
6. Determine whether the query must visit the table or if an index covers the columns.
7. Check whether `TABLE ACCESS BY INDEX ROWID` uses batching and how many `buffers`/`reads` it incurs.
8. Compare against `TABLE ACCESS FULL` on representative data and workload.
9. Check whether stats are stale or missing appropriate histograms.
10. If CF is high, assess whether that access path is important enough to justify reorganization.
11. Evaluate write overhead and storage if considering adding indexes or changing structures.
12. After changes, gather stats and re-measure with runtime plans.

## 18. Self-Practice Exercises

**Question 1 — Defining CF.** Why does a low clustering factor usually favor an index range scan?

Hint: Many consecutive index entries point to the same or nearby table blocks, reducing block transitions when fetching rows.

**Question 2 — CF is not block count.** An index has a CF of 80,000 and the table has 10,000 blocks. Does that mean the table has 80,000 blocks?

Hint: No. CF can exceed the distinct block count because the same block can be revisited after moving to other blocks.

**Question 3 — Selectivity.** A table has 2 million rows and a predicate is estimated to return 2,000 rows. What is the selectivity?

Hint: 2,000 / 2,000,000 = 0.001, or 0.1%.

**Question 4 — NDV.** A column has 20 distinct values distributed uniformly. What is the simple estimated equality selectivity?

Hint: Approximately 1/20 = 5%; if skewed, histograms can change the estimate.

**Question 5 — Two indexes.** Two indexes both return 5,000 rows, yet one has low CF and the other has CF near `NUM_ROWS`. Why can their costs differ?

Hint: The number of table blocks accessed via ROWID can differ due to locality.

**Question 6 — Index-only.** Why does CF matter less when a query needs only columns stored in the index?

Hint: There is no need to visit the table to fetch missing columns.

**Question 7 — Histograms.** Why is `NDV=3` insufficient to estimate the predicate `STATUS='CLOSED'`?

Hint: Three values can be heavily skewed; histograms capture skew.

**Question 8 — Rebuild.** Does rebuilding an index place heap table rows adjacent to each other in index key order?

Hint: No. Rebuilding reorganizes the index segment, not table rows.

**Question 9 — Plan.** `E-Rows` is 100 while `A-Rows` is 100,000. What should you investigate?

Hint: Stats, histograms, bind peeking, correlation, predicates, and data skew.

**Question 10 — Choosing access paths.** A predicate returns 60% of rows, the index has high CF, and the query needs many columns outside the index. Why can a full scan be cheaper?

Hint: The index would need to read many entries and visit many scattered table blocks; a full scan can read blocks via multiblock I/O.

## 19. Summary

Clustering factor, selectivity, and blocks to access are interconnected concepts when Oracle's optimizer evaluates index access:

- **Clustering factor** describes table block transitions when traversing ROWIDs in index key order. Low CF generally signals good locality; high CF signals scattered rows.
- **Selectivity** is the fraction of rows matching a predicate; cardinality is the optimizer's estimated row count. NDV, histograms, `NULL`s, and correlation affect estimates.
- **Index range scan** must account for both reading leaf blocks and visiting table blocks via ROWID if the query needs non-indexed columns.
- **Full table scan** can be cheaper when queries need many rows or high CF makes random table access expensive.
- **Index-only access** reduces reliance on CF because table access is avoided.
- **DBMS_STATS** provides statistics to the optimizer; `DBMS_XPLAN` helps compare estimated rows against actual rows, buffers, and reads.
- **Index rebuild** does not automatically reorder a heap table. Changing locality requires evaluating table reorganization and trade-offs across access paths.

Do not pick an index merely because a predicate looks selective or CF is low. Examine actual cardinality, block counts, columns to read, execution plans, and overall workload. With proper statistics and access paths validated by runtime evidence, the choice between index range scan and full table scan will be well grounded.
