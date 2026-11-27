## 4. Bitmap Indexes in Analytical Queries

### 4.1. Filtering by a single attribute

```sql
SELECT COUNT(*)
FROM sales
WHERE status = 'PAID';
```

If the index and statistics fit, Oracle can use a bitmap index on `STATUS` to locate ROWIDs of `PAID` rows. However, if `PAID` accounts for most of the table, a full scan can be more efficient. The optimizer decides based on cost estimates, not a rule that existing bitmap indexes must be used.

### 4.2. Combining multiple attributes

```sql
SELECT
    region_code,
    channel,
    SUM(amount) AS total_amount,
    COUNT(*) AS transaction_count
FROM sales
WHERE region_code IN ('NORTH', 'SOUTH')
  AND channel = 'WEB'
  AND status = 'PAID'
GROUP BY region_code, channel;
```

With appropriate bitmap indexes on `REGION_CODE`, `CHANNEL`, and `STATUS`, Oracle can combine the bitmaps to identify the matching row set before reading `AMOUNT` and performing aggregation.

### 4.3. OR predicates

```sql
SELECT COUNT(*)
FROM sales
WHERE status = 'PAID'
   OR status = 'REFUNDED';
```

Oracle can combine bitmaps using an `OR` operation. An `IN ('PAID', 'REFUNDED')` condition can also be handled in a logically similar manner. The exact plan depends on the optimizer and statistics.

### 4.4. Combining bitmap and B-tree indexes

A query can have predicates on low-cardinality columns alongside predicates on high-cardinality keys. Oracle can use multiple access path types or combine bitmaps with ROWIDs from other indexes depending on the plan. There is no need to convert every index on a table to bitmap; data warehouse tables commonly use B-tree indexes for specific lookup keys and bitmap indexes for categorical attributes.

### 4.5. Bitmap operations in execution plans

When inspecting plans, you may encounter operations such as:

| Operation | General meaning |
| --- | --- |
| BITMAP INDEX SINGLE VALUE | Retrieves the bitmap for a single index value |
| BITMAP INDEX RANGE SCAN | Retrieves bitmaps for a range of values |
| BITMAP AND | Combines bitmaps using logical AND |
| BITMAP OR | Combines bitmaps using logical OR |
| BITMAP MERGE | Merges bitmaps |
| BITMAP CONVERSION TO ROWIDS | Converts matching bitmap bits into ROWIDs |
| TABLE ACCESS BY INDEX ROWID | Accesses table rows by ROWID |

Exact operation names and plans vary by Oracle version, predicates, partitioning, and optimizer transformations. Read the full plan, cardinality estimates, and actual row counts rather than concluding from a single operation line.

## 5. Why Are Bitmap Indexes Well Suited to Data Warehouses?

### 5.1. Read-heavy, batch-write workloads

Data warehouses typically exhibit:

- Data loaded via batch jobs or ETL.
- Queries scanning millions of rows for aggregation.
- Users slicing across many dimensions: time, region, channel, product category, status.
- Dimensions that change less frequently than OLTP transactions.

Bitmap indexes help filter data across many categorical attributes at reasonable storage cost, especially when column values repeat heavily.

### 5.2. Ad hoc queries and predicate combinations

BI users can pick arbitrary filters:

- Region `NORTH` or `EAST`.
- Channel `WEB`.
- Status `PAID`.
- Customer type `BUSINESS`.
- Product group `ELECTRONICS`.

It is impossible to build one composite B-tree index for every column combination a user might choose. Individual bitmap indexes can be combined flexibly to match each query's predicates.

### 5.3. Bitmap join indexes are a related topic

Oracle also offers bitmap join indexes, allowing a bitmap index on a dimension table column via its join relationship to a fact table. Conceptual example:

```sql
CREATE BITMAP INDEX ix_sales_region_join_bm
ON sales(region.region_name)
FROM sales, region
WHERE sales.region_id = region.region_id;
```

This is a specialized index type for star schemas with its own syntax and constraints; the example merely illustrates the idea. Do not confuse a regular single-table bitmap index with a bitmap join index. This lesson focuses on regular bitmap indexes; bitmap join indexes must be designed and tested per the Oracle Data Warehousing Guide for your release.

### 5.4. Bitmaps do not always make queries faster

A query needing to read 80% of a table can run faster via a full table scan, especially with sequential I/O and parallel query. Bitmap indexes do not eliminate the cost of reading data required for the `SELECT` list, `GROUP BY`, or calculations.

Compare:

- Full table scan.
- Bitmap index access + table access by ROWID.
- B-tree access.
- Partition pruning if the table is partitioned.
- Parallel execution if the workload permits.

The objective is overall workload cost and SLAs, not forcing every query to use an index.

## 6. Bitmap Indexes vs. B-tree Indexes

The two index types have different structures and workload characteristics. Neither is universally better than the other.

| Criterion | Bitmap index | B-tree index |
| --- | --- | --- |
| Conceptual structure | Bitmap per value mapping to many ROWIDs | Balanced tree of keys and ROWIDs |
| Typical suitable columns | Low cardinality or categorical dimensions in DW | High cardinality, identifier keys, point/range lookups |
| Combining multiple predicates | Strong with bitmap AND/OR/NOT | Can use composite indexes or multiple access paths; different combination mechanism |
| Aggregation queries | Often useful for ad hoc filtering on large tables | Useful when predicates are selective or key-driven |
| Concurrent DML | Potential contention because bitmap entries span many rows | Usually better suited to frequent OLTP updates |
| NULLs | Can store bitmaps for NULLs | B-tree stores no entry if all key columns are NULL |
| Unique constraints | Not used as a unique index | Can be unique and enforce PK/UNIQUE |
| Storage size | Compresses well when values repeat heavily | Depends on keys, ROWIDs, and data distribution |

### 6.1. Example of choosing indexes by workload

A `FACT_SALES` table with 200 million rows:

- `STATUS` has 4 values, used in multi-dimension filtering reports and rarely updated row-by-row: bitmap is a candidate.
- `CHANNEL` has 3 values, changed only during nightly ETL: bitmap may fit.
- `CUSTOMER_ID` has millions of values, application looks up transactions for a specific customer: B-tree usually fits better.
- `SALE_ID` is a unique key: use primary key/unique B-tree, not bitmap.

If the same `FACT_SALES` table receives single-row `UPDATE`s from hundreds of concurrent sessions all day long, re-evaluate bitmap indexes on updated columns. Actual workload matters more than the "fact table" label.

### 6.2. A bitmap index is not a single composite index for every query

Separate bitmap indexes on `REGION`, `CHANNEL`, and `STATUS` can be combined for many predicate combinations. A composite bitmap index `(REGION, CHANNEL, STATUS)` may suit specific queries, yet is less flexible when users filter only on non-leading columns or different combinations.

Decisions should be based on common queries, index size, statistics, and ETL cost. Do not create an index solely because a column has few distinct values.

## 7. Update Contention: A Key Drawback of Bitmaps

### 7.1. Why can updating one row affect the bitmap of many rows?

In a B-tree, entries typically map a key to one or more ROWIDs; DML updates the index structure associated with the modified row. In a bitmap index, a single bitmap entry represents a set of many ROWIDs sharing the same key value. When one row's value changes, Oracle must update the bitmaps corresponding to both the old value and the new value.

Because a bitmap entry spans many rows, concurrency locks can be held over a bitmap entry or ROWID range broader than a single logical row. Therefore, two transactions modifying completely different table rows can still block each other if they need to modify overlapping bitmap entries.

This is why bitmap indexes can reduce write concurrency in OLTP systems. It does not mean every `UPDATE` on a table with a bitmap index locks the entire table; contention depends on the index, old/new values, ROWID locations, transaction duration, and DML patterns.

### 7.2. Two-session illustration

Suppose there is a bitmap index on `STATUS` and many rows currently have `STATUS = NEW`. Two sessions update two different `SALE_ID`s, both transitioning `NEW` to `PAID`:

```text
Session A                              Session B
---------                              ---------
UPDATE sale_id = 101: NEW -> PAID      UPDATE sale_id = 202: NEW -> PAID
Modifies NEW and PAID bitmaps          Needs to modify NEW and PAID bitmaps
Holds lock on relevant bitmap          May wait on bitmap lock
COMMIT                                 Proceeds once lock is released
```

Two different `SALE_ID`s do not mean different bitmap entries. Both rows may belong to the same bitmap segment for `NEW` and the same bitmap segment for `PAID`. Actual wait behavior depends on index structure and updated bitmap ranges; this example explains the mechanism rather than guaranteeing any two sessions will always block on every dataset.

### 7.3. INSERT, UPDATE, and DELETE all carry costs

- `INSERT` must set the new ROWID bit in the bitmap matching the column value.
- `UPDATE` changing the value must clear the bit in the old bitmap and set the bit in the new bitmap.
- `DELETE` must clear the ROWID from the corresponding bitmap.
- Updating a non-indexed column can still incur index work if row movement/ROWID changes require bitmap updates, though contention centers on DML modifying indexed bitmap columns.

Bulk modifications can trigger substantial index maintenance. In data warehouses, batch loading and index maintenance are usually scheduled in ETL windows.

### 7.4. Updating columns not in the bitmap index

If an `UPDATE` modifies only `AMOUNT` and does not touch any bitmap-indexed column, that bitmap index generally does not need to change key bitmaps for column values. However, DML can still incur costs from other indexes, triggers, constraints, row movement, or partition operations. Do not conclude every `UPDATE` on a table with a bitmap index causes equal bitmap contention.

### 7.5. Long transactions increase wait times

If a transaction updates a row and stays open while calling an external service or doing unrelated work, associated locks are held longer. Other sessions needing to modify overlapping bitmap entries must wait longer.

Keep transactions short, commit at sensible boundaries, and avoid waiting on external I/O while holding locks. For large batches, choose chunk sizes and writer coordination to limit contention duration.

## 8. Why Are Bitmap Indexes Unsuitable for Write-Heavy OLTP?

OLTP typically features:

- Many concurrent writing sessions.
- Continuous single-row `UPDATE`/`INSERT`/`DELETE` operations.
- Transactions requiring low latency and short lock durations.
- Status or classification columns changing frequently.

If a bitmap index is placed on a heavily updated column, many sessions can contend on bitmap entries. This increases enqueue/lock waits, lowers throughput, and creates long latency tails.

### 8.1. When should bitmap indexes be avoided?

- Transactional tables with many concurrent writers.
- Indexed columns whose status changes frequently.
- Systems requiring low-latency single-row updates.
- Transactions that hold locks for extended periods.
- Indexes created on low-cardinality columns merely because distinct counts are low, without an analytical workload proving benefit.

### 8.2. When can they still be considered?

- Read-mostly or read-only tables.
- Data loaded in batches during controlled windows.
- Workloads consisting primarily of reporting and aggregation.
- Classification columns with few values used in multi-predicate combinations.
- Queries benchmarked to show bitmaps reduce overall cost.

### 8.3. Distinguishing bitmap contention from normal row locks

A transaction updating a row still locks the table row under Oracle's locking mechanism. A bitmap index adds a potential contention point at the index entry level. Thus, two sessions updating two different rows may have no table row-lock conflict yet still block each other when updating shared bitmap entries.

When diagnosing, do not look solely at distinct `SALE_ID`s and conclude a lock wait is impossible. Inspect wait events, involved objects/indexes, and blocking transactions.

### 8.4. Do not solve it by blindly deleting every bitmap index

If a system combines analytical reads and transactional updates:

- Identify which columns actually change during OLTP.
- Measure wait times and throughput with and without the index.
- Consider separating read-only fact/history tables from operational status tables.
- Use B-tree indexes for transactional application access paths.
- Use bitmaps for data warehouse tables or ETL-managed partitions.
- Consider materialized views or summary tables when the goal is reporting.

Never drop an index in production based on theory alone. The index may be supporting critical queries or other constraints; evaluate plans and impact before making changes.

## 9. Practice Dataset

Create a table simulating a fact table with low-cardinality categorical attributes:

```sql
CREATE TABLE lab_sales_bitmap (
    sale_id      NUMBER(12)
        CONSTRAINT pk_lab_sales_bitmap PRIMARY KEY,
    region_code  VARCHAR2(20),
    channel      VARCHAR2(20),
    status       VARCHAR2(20),
    sold_at      DATE,
    amount       NUMBER(12, 2)
);
```

Load enough data for the optimizer to consider indexes:

```sql
INSERT INTO lab_sales_bitmap (
    sale_id, region_code, channel, status, sold_at, amount
)
SELECT
    LEVEL,
    CASE MOD(LEVEL, 5)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        WHEN 2 THEN 'EAST'
        WHEN 3 THEN 'WEST'
        ELSE 'CENTRAL'
    END,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'WEB'
        WHEN 1 THEN 'STORE'
        ELSE 'PARTNER'
    END,
    CASE MOD(LEVEL, 4)
        WHEN 0 THEN 'PAID'
        WHEN 1 THEN 'NEW'
        WHEN 2 THEN 'CANCELLED'
        ELSE 'REFUNDED'
    END,
    DATE '2026-01-01' + MOD(LEVEL, 365),
    MOD(LEVEL * 17, 100000) / 100
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
```

This dataset has 100,000 rows, 5 regions, 3 channels, and 4 statuses. The `MOD`-generated distribution is uniform purely for illustration. Real-world data often exhibits skew and column correlation.

Check cardinality:

```sql
SELECT 'REGION_CODE' AS column_name,
       COUNT(DISTINCT region_code) AS distinct_values
FROM lab_sales_bitmap
UNION ALL
SELECT 'CHANNEL', COUNT(DISTINCT channel)
FROM lab_sales_bitmap
UNION ALL
SELECT 'STATUS', COUNT(DISTINCT status)
FROM lab_sales_bitmap
UNION ALL
SELECT 'SALE_ID', COUNT(DISTINCT sale_id)
FROM lab_sales_bitmap;
```

## 10. Creating Bitmap Indexes and Comparing Queries

### 10.1. Create bitmap indexes for categorical attributes

```sql
CREATE BITMAP INDEX ix_lsb_region_bm
ON lab_sales_bitmap (region_code);

CREATE BITMAP INDEX ix_lsb_channel_bm
ON lab_sales_bitmap (channel);

CREATE BITMAP INDEX ix_lsb_status_bm
ON lab_sales_bitmap (status);
```

`SALE_ID` already has a primary key index; do not create a bitmap index on a unique key. `SOLD_AT` has many date values and may need a B-tree or partition pruning depending on workload.

### 10.2. Query combining three predicates

```sql
SELECT
    region_code,
    channel,
    SUM(amount) AS total_amount,
    COUNT(*) AS sale_count
FROM lab_sales_bitmap
WHERE region_code IN ('NORTH', 'SOUTH')
  AND channel = 'WEB'
  AND status = 'PAID'
GROUP BY region_code, channel;
```

Oracle can use bitmap indexes on all three columns to combine predicates. If the table is small or statistics show a full scan is cheaper, the plan may not use bitmaps. That is not necessarily an error.

### 10.3. Refresh statistics

In a lab environment, you can gather statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_SALES_BITMAP',
        cascade => TRUE
    );
END;
/
```

Statistics help the optimizer estimate row counts and cost. With skewed data, histograms can influence predicate estimates. Do not gather statistics arbitrarily in production; follow your system's statistics management procedures.

### 10.4. View execution plan

```sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM lab_sales_bitmap
WHERE region_code = 'NORTH'
  AND channel = 'WEB'
  AND status = 'PAID';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Look for bitmap operations such as `BITMAP INDEX SINGLE VALUE`, `BITMAP AND`, and `BITMAP CONVERSION TO ROWIDS` if the optimizer picks a bitmap access path. If the plan shows `TABLE ACCESS FULL`, compare estimated rows and cost; with small/uniform lab data, a full scan may be reasonable.

### 10.5. View actual row-source statistics

You can run the query with execution statistics in a test environment:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       SUM(amount)
FROM lab_sales_bitmap
WHERE region_code = 'NORTH'
  AND channel = 'WEB'
  AND status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

`ALLSTATS LAST` displays actual rows if row-source statistics were collected and the account has appropriate privileges. Compare `E-Rows` with `A-Rows` to check whether the optimizer estimated accurately. If there is a large discrepancy, examine data distribution, histograms, column correlation, and statistics freshness.

### 10.6. Compare before and after dropping bitmap indexes

In the lab schema, you can save the previous plan, drop the indexes, and re-examine the plan:

```sql
DROP INDEX ix_lsb_region_bm;
DROP INDEX ix_lsb_channel_bm;
DROP INDEX ix_lsb_status_bm;
```

Re-run `EXPLAIN PLAN` and compare. The optimizer may pick a full scan or another access path. Dropping indexes is DDL with an implicit commit; perform it only in a lab schema, never on production tables for experimentation.

## 11. Testing Update Contention with Two Sessions

The goal of this lab is to observe that bitmap indexes can cause waits between DML statements modifying different rows that touch the same bitmap entry. Results depend on how Oracle organizes bitmaps, ROWID placement, and session timing; not every run reproduces the exact same wait duration.

### 11.1. Prepare a bitmap index on STATUS

Recreate the index if dropped in Section 10.6:

```sql
CREATE BITMAP INDEX ix_lsb_status_bm
ON lab_sales_bitmap (status);
```

Find two different `SALE_ID`s sharing `STATUS = 'NEW'`:

```sql
SELECT sale_id, status
FROM lab_sales_bitmap
WHERE status = 'NEW'
  AND ROWNUM <= 10
ORDER BY sale_id;
```

Pick two distinct IDs from the result, e.g., rows A and B. Do not use the same `SALE_ID` in both sessions, as that would trigger ordinary row locking and obscure the observation of bitmap contention.

### 11.2. Test in sessions A and B

In session A:

```sql
UPDATE lab_sales_bitmap
SET status = 'PAID'
WHERE sale_id = :sale_id_a;
-- Do not COMMIT yet.
```

In session B, update the other row with the same old status:

```sql
UPDATE lab_sales_bitmap
SET status = 'PAID'
WHERE sale_id = :sale_id_b;
-- Observe whether the statement waits.
```

Back in session A:

```sql
COMMIT;
```

Observe whether session B resumes or has completed. You can repeat this in the lab schema and compare after dropping the bitmap index. Not seeing a wait on one run does not prove bitmap indexes cannot contend; timing, entry boundaries, and concurrency patterns matter.

### 11.3. Compare with a B-tree index

In the lab, drop the bitmap index and create a B-tree index on `STATUS`:

```sql
DROP INDEX ix_lsb_status_bm;

CREATE INDEX ix_lsb_status_btree
ON lab_sales_bitmap (status);
```

Repeat the two-session test and compare. This is a qualitative illustration; do not use a small table to draw production performance benchmark conclusions. B-trees also experience block/index contention and row-level locking, but bitmap lock structures can create broader contention across ROWID ranges.

### 11.4. Inspecting waiting sessions

DBAs can inspect session waits/locks using dynamic performance views such as `V$SESSION`, `V$LOCK`, and related object views if authorized. Regular users may lack privileges to read these views. Do not grant DBA privileges just to run a lab; ask an administrator to supply relevant wait diagnostics.

## 12. Bitmap Indexes on Partitioned Tables and ETL Workflows

### 12.1. Local bitmap indexes

For time-partitioned fact tables, local indexes align with table partitions. Local bitmap indexes are usually the preferred choice in data warehouses because:

- Each partition has its own index segment.
- New data can be loaded/maintained per partition.
- Partition drop/truncate/exchange operations can be managed more locally.
- Maintenance work does not necessarily touch the entire table's index.

Oracle supports local bitmap indexes on partitioned tables; partitioned bitmap indexes have different restrictions than global B-tree indexes. Verify capabilities and syntax for your specific Oracle version before designing.

Illustrative example:

```sql
CREATE BITMAP INDEX ix_fact_status_local
ON fact_sales (status)
LOCAL;
```

`LOCAL` requires the table to be partitioned, splitting the index according to the table partitions.

### 12.2. Batch data loading

In a data warehouse, an ETL pipeline might:

1. Load data into staging.
2. Validate data and filter out errors.
3. Load/exchange partitions into the fact table.
4. Update or rebuild local bitmap indexes per operational strategy.
5. Gather statistics.
6. Run quality checks and representative reporting queries.

Do not assume you must `DROP` bitmap indexes before every load. Some load methods maintain indexes online; some load or partition operations can mark indexes `UNUSABLE` or require rebuilds. Check index status after operations and consult Oracle documentation for the exact load/partition method used.

### 12.3. Checking index and partition status

Non-partitioned index:

```sql
SELECT index_name, status, visibility
FROM user_indexes
WHERE table_name = 'FACT_SALES';
```

Partitioned index:

```sql
SELECT
    index_name,
    partition_name,
    status
FROM user_ind_partitions
WHERE index_name = UPPER(:index_name)
ORDER BY partition_position;
```

If an index or index partition is `UNUSABLE`, the optimizer cannot use it as a valid index for queries; subsequent DML may also be affected depending on status/configuration. Resolve via rebuild or appropriate recovery procedures before relying on the index.

### 12.4. Rebuild and maintenance

Example rebuilding a non-partitioned bitmap index:

```sql
ALTER INDEX ix_lsb_status_bm REBUILD;
```

For local partitioned indexes, you may need to act on individual index partitions or use appropriate statements. `REBUILD` is DDL and impacts I/O, space, locking, and availability; schedule it in maintenance windows and monitor tablespace free space.

## 13. Design and Operational Best Practices

### 13.1. Assess before creating a bitmap index

Before creating an index, gather:

- Total row count and table size.
- Distinct count and value distribution of the column.
- Typical predicate selectivity.
- Common `WHERE` combinations in BI queries.
- Frequency of `INSERT`/`UPDATE`/`DELETE` on the table and specific columns.
- Number of concurrent writers and DML SLAs.
- Index storage, redo/undo, and ETL maintenance overhead.

Do not create a bitmap solely because cardinality is low. A status column with only 3 values updated 20,000 times per second in OLTP is a poor candidate.

### 13.2. Test the workload instead of forcing indexes

Do not use `INDEX` or `BITMAP` hints to force the optimizer to use an index without benchmarking. Hints can yield a good plan on a small dataset while degrading badly as data distribution shifts.

Compare execution time, logical reads, physical reads, CPU, `TEMP`, actual rows, and DML duration with and without the index. Evaluate total workload: an index that speeds up `SELECT` yet slows down `UPDATE` may be an unacceptable trade-off.

### 13.3. Histograms and skewed data

If one value accounts for 95% of rows and others 5%, selectivity estimates assuming uniform distribution will be wrong. Statistics and histograms can help the optimizer understand skew. However, histograms also carry administrative overhead and depend on workload; invoke `DBMS_STATS` per system policy.

### 13.4. Correlation between columns

`REGION_CODE` and `TAX_ZONE` may be strongly correlated. If the optimizer assumes two predicates are independent, row estimates after bitmap `AND` can be off. Extended statistics or suitable partition/dimension design can help, though they must be measured and configured against real queries.

### 13.5. Avoid redundant indexes

Multiple bitmap indexes increase storage and ETL overhead. Evaluate each index by asking:

- Do predicates actually use it?
- Does it help combine bitmaps with other indexes?
- Does a composite index or another access path supersede it?
- Does the column change frequently?
- Does it impact load, rebuild, and backup times?

Unused indexes may be candidates for removal, but observe the workload across full business cycles and confirm no infrequent periodic reports depend on them.

## 14. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Low-cardinality columns must always use bitmaps | Also depends on DML concurrency, selectivity, table size, and workload |
| If a bitmap index exists, the optimizer will always use it | Full scan or B-tree may be cheaper |
| Bitmap indexes only suit columns with 2–3 values | There is no fixed threshold; evaluate distribution and workload |
| Bitmap indexes lock the entire table on UPDATE | Not necessarily; contention affects bitmap entries/ROWID ranges, not always a full table lock |
| Two sessions updating two different rows cannot block each other | They can block on shared bitmap entries despite distinct row locks |
| Bitmap indexes can enforce PRIMARY KEY | Bitmap indexes cannot be used to enforce unique constraints |
| Public/low-cardinality columns always deserve bitmaps | Low-distinct columns can still be B-tree indexed when workload fits |
| Dropping an index does not affect anything beyond metadata | Table data stays intact, yet query plans and performance can change drastically |
| Bitmap indexes only help single-column queries | Their key strength is combining multiple categorical conditions |
| A single SELECT benchmark is enough to decide | Must benchmark DML, concurrency, ETL, and overall workload |

## 15. Comprehensive Exercises

### Part A — Reading bitmaps

Using the illustrative table from Section 1.1:

1. How many `1` bits does the `WEB` bitmap have?
2. How many `1` bits does the `STORE` bitmap have?
3. What does `AND`ing `WEB` and `STORE` produce?
4. If the query is `CHANNEL = 'WEB' OR CHANNEL = 'STORE'`, which rows appear in the resulting bitmap?

### Part B — Choosing index types

A table has 50 million transactions. `STATUS` has 4 values, `CUSTOMER_ID` has 3 million values, and `SALE_ID` is the unique key. The workload includes:

- A read-heavy dashboard filtering `STATUS` + `REGION` + `CHANNEL`.
- An API looking up `SALE_ID` and updating status row-by-row.
- A history report by `CUSTOMER_ID`.

Propose indexes for each requirement and explain why you should not create bitmaps on every column.

### Part C — Checking cardinality

Run the `COUNT(DISTINCT)` query in Section 9. Add a new `STATUS` value and re-measure cardinality. Discuss whether distinct count alone is sufficient to decide on a bitmap index.

### Part D — Reading execution plans

Run the query in Section 10.4. Record:

- Did the optimizer pick full scan or bitmap access?
- Are `BITMAP AND`/`OR` operations present?
- What are `E-Rows` at the bitmap and table access steps?
- Is there any difference between estimated rows and actual rows?

There is no single mandatory plan for the lab. The goal is learning how to read and explain the optimizer's choice.

### Part E — Simulating contention

Perform the two-session lab in Section 11:

1. Pick two different rows with the same `STATUS`.
2. Session A runs `UPDATE` without committing.
3. Session B runs `UPDATE` on the other row to the same target status.
4. Observe whether it waits.
5. Commit A, observe B.
6. Drop the bitmap index, create a B-tree index, and repeat.

Explain why the same table and two distinct rows can exhibit different wait behavior when the index type changes.

### Part F — Designing ETL

A fact table loads 20 million rows nightly, is partitioned monthly, and has 4 bitmap indexes on categorical columns. Propose a workflow for loading, checking index status, rebuilding when needed, and gathering statistics. List questions to confirm with the DBA before using partition exchange or direct-path loads.

### Part G — Distinguishing workloads

Evaluate two systems:

- System A: 95% reporting `SELECT`s, 5% nightly batch loads.
- System B: 30% `SELECT`, 70% `UPDATE`/`INSERT` from hundreds of sessions.

Explain why the same `STATUS` column may fit a bitmap index in System A yet be unsuitable in System B.

## 16. Best Practices

1. **Choose bitmaps based on workload.** Low distinct count is an initial signal, not the final decision.
2. **Favor bitmaps for read-heavy analytical workloads.** Data warehouses and reporting benefit strongly from bitmap combination.
3. **Avoid bitmaps on hot updated columns in OLTP.** Concurrent updates can contend on bitmap entries.
4. **Use B-trees for identifier keys and point lookups.** Primary/unique keys require appropriate uniqueness enforcement.
5. **Combine multiple predicates deliberately.** Bitmap `AND`/`OR` shines when queries filter across multiple dimensions.
6. **Do not force the optimizer to use an index.** A full table scan can be cheaper when reading most of the table.
7. **Measure both SELECT and DML.** An index that helps reports can slow writes and increase lock waits.
8. **Keep transactions short.** Never hold locks while waiting on external services or unrelated work.
9. **Manage ETL and indexes together.** Check index status after loads and partition operations.
10. **Gather appropriate statistics.** Skew and correlation affect cardinality estimates.
11. **Do not use bitmap indexes to enforce uniqueness.** Use `PK`/`UNIQUE` constraints.
12. **Inspect actual plans and wait events.** Base conclusions on real data and workload, not theory alone.

## 17. Self-Check Questions

1. How does a bitmap index represent a column value and its corresponding ROWIDs?
2. How does cardinality differ from selectivity?
3. Why is a 4-value `STATUS` column often a bitmap candidate in a data warehouse?
4. Why might the same `STATUS` column be unsuitable for a bitmap index in OLTP?
5. How does Oracle combine bitmap indexes for `AND` predicates?
6. When can a full table scan be faster than bitmap access?
7. How does a bitmap index differ from a B-tree index in structure and DML behavior?
8. Why can a bitmap index represent `NULL` while a B-tree stores no entry for all-`NULL` keys?
9. Can a bitmap index be used as a unique index? Why or why not?
10. Why can two sessions updating two different rows still block each other?
11. Which bitmaps must be modified during an `UPDATE` from `NEW` to `PAID`?
12. Why can long transactions worsen bitmap wait times?
13. What do `BITMAP AND`, `BITMAP OR`, and `BITMAP CONVERSION TO ROWIDS` represent?
14. Why can you not conclude the optimizer is wrong when it picks a full table scan despite a bitmap index existing?
15. How do local bitmap indexes help partitioned fact tables?
16. Why should index status be checked after ETL or partition maintenance?
17. How can histograms and column correlation affect optimizer estimates?
18. Which metrics should be benchmarked besides `SELECT` execution time?

## 18. Summary Model

```text
BITMAP INDEX
    |
    +-- Each value has a bitmap mapping to ROWIDs
    |
    +-- Typically effective with low cardinality
    |
    +-- Combines predicates via AND / OR / NOT
    |
    v
ANALYTICAL WORKLOAD
    |
    +-- Large tables, read-heavy
    +-- Multi-dimensional ad hoc reporting
    +-- Batch ETL
    |
    v
DML RISKS
    |
    +-- One bitmap entry spans many rows
    +-- UPDATE alters both old and new bitmaps
    +-- Two sessions on different rows can still contend
    |
    v
DECISION
    |
    +-- DW / reporting with low writes: consider bitmap
    +-- Concurrent-write OLTP: usually prefer B-tree
    +-- PK / UNIQUE: use unique B-tree constraints
    +-- Always measure plans, actual rows, waits, and ETL cost
```

**Key takeaway:** Bitmap indexes excel at filtering and combining multiple categorical attributes in read-heavy workloads. That same bitmap structure can cause concurrent DML contention because a single entry represents many rows. Choose based on cardinality, selectivity, update frequency, and query patterns; inspect both execution plans and wait events to verify real-world effectiveness.
