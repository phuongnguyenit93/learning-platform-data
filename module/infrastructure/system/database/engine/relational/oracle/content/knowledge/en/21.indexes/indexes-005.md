# Index Skip Scan and Conditions Evaluated by the Optimizer in Oracle

A composite B-tree index stores keys in the order of its declared columns. When a query filters on the leading column, Oracle can usually jump straight to the matching key range with an index range scan. But if the predicate filters only on a trailing column, is the composite index completely useless?

Oracle has an access path called **index skip scan**. Under certain data distributions, the optimizer can treat the composite index as multiple logical search ranges partitioned by the values of the leading column, and search for the trailing column value within each range. This approach can be helpful when the leading column has few distinct values and the predicate on the trailing column selects few rows.

Skip scan is a cost-based choice, not a guarantee that Oracle will use the index. This lesson explains composite index structure, how skip scan works, the factors the optimizer considers, how to read execution plans, and how to decide index column order based on workload.

## 1. Review of Composite B-tree Index Structure

A composite index contains multiple columns. Example:

~~~sql
CREATE INDEX ix_orders_status_customer
ON orders (order_status, customer_id);
~~~

Oracle orders keys as follows:

1. `ORDER_STATUS` first.
2. Within the same `ORDER_STATUS`, sorted next by `CUSTOMER_ID`.

You can visualize the index like this:

~~~text
(CANCELLED, 101)
(CANCELLED, 105)
(CANCELLED, 210)
...
(PAID,      101)
(PAID,      105)
(PAID,      210)
...
(PENDING,   101)
(PENDING,   105)
(PENDING,   210)
...
~~~

This is a logical illustration to understand key ordering, not how Oracle stores a text list. An actual B-tree organizes entries inside root, branch, and leaf blocks.

### 1.1. Leading column and trailing column

With index `(ORDER_STATUS, CUSTOMER_ID)`:

- `ORDER_STATUS` is the **leading column**.
- `CUSTOMER_ID` is the **trailing column**.

Query conditions that normally benefit:

~~~sql
-- Condition on leading column.
SELECT *
FROM orders
WHERE order_status = 'PAID';

-- Conditions on both leading and trailing columns.
SELECT *
FROM orders
WHERE order_status = 'PAID'
  AND customer_id = 101;
~~~

Oracle can isolate a contiguous key range in the index based on the leading column, then apply the trailing column condition.

### 1.2. When filtering only the trailing column

~~~sql
SELECT *
FROM orders
WHERE customer_id = 101;
~~~

Because keys are sorted by `ORDER_STATUS` first, entries with `CUSTOMER_ID = 101` are not contiguous across the whole index. They are scattered across different `ORDER_STATUS` groups.

A traditional access method is a full table scan. However, if `ORDER_STATUS` has only a few distinct values, Oracle may consider an index skip scan.

## 2. What Is Index Skip Scan?

**Index skip scan** is an access path allowing Oracle to use a composite B-tree index even when a query lacks a condition on the leading column, by stepping through distinct values of the leading column and probing each corresponding logical subrange.

With the index:

~~~sql
CREATE INDEX ix_orders_status_customer
ON orders (order_status, customer_id);
~~~

and query:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 101;
~~~

Oracle can conceptually process it as follows:

1. Consider the first `ORDER_STATUS` value, search for `CUSTOMER_ID = 101` within that key range.
2. Move to the next `ORDER_STATUS` value, continue searching for `CUSTOMER_ID = 101`.
3. Repeat for the remaining leading column values.
4. Combine matching ROWIDs to access table rows if needed.

~~~text
Index (ORDER_STATUS, CUSTOMER_ID)

Group CANCELLED: find CUSTOMER_ID = 101
          |
          v
Group PAID:      find CUSTOMER_ID = 101
          |
          v
Group PENDING:   find CUSTOMER_ID = 101
          |
          v
Combine matching entries
          |
          v
Access table rows by ROWID if needed
~~~

The groups above are **logical subindexes** per leading key value. Oracle does not create a new physical index for each value. It uses the existing B-tree structure to perform the probes.

### 2.1. Why is it called skip scan?

Oracle skips pinning a single leading column value. Instead, it steps through possible leading values and probes the trailing key ranges. This differs from a standard index range scan, which enters a single contiguous key range determined by the leading key.

Skip scan does not mean Oracle arbitrarily skips blocks or reads only a few rows. Cost still depends on the number of leading key values, index size, matching entries, and table accesses required.

### 2.2. Crucial condition: leading column has few distinct values

Suppose `ORDER_STATUS` has only three values:

- `CANCELLED`
- `PAID`
- `PENDING`

When a query filters only on `CUSTOMER_ID`, Oracle may need to probe three logical ranges for `ORDER_STATUS`. If the leading column had thousands of distinct values, the number of ranges to probe would be much higher and skip scan would usually be unattractive.

Rule of thumb:

> Skip scan is worth considering when the leading column has low cardinality while the predicate on the trailing column has good selectivity.

This is a practical guideline, not a formula forcing the optimizer to pick skip scan. Oracle still compares cost against a full table scan and other access paths.

## 3. Preparing Practice Data

Let us create an orders table with:

- `ORDER_STATUS`: only three status values.
- `CUSTOMER_ID`: many distinct values.
- `ORDER_ID`: order ID.
- `ORDER_DATE` and `AMOUNT`: additional columns for queries.

The composite index will put `ORDER_STATUS` before `CUSTOMER_ID`. Then we will run a query filtering only `CUSTOMER_ID` to observe skip scan behavior.

### 3.1. Create the table

Run in a lab schema inside a practice PDB. If a table with the same name already exists, use another schema or name; do not overwrite data in active use.

~~~sql
CREATE TABLE lab_ss_orders (
    order_id     NUMBER(10) PRIMARY KEY,
    order_status VARCHAR2(12 CHAR) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    order_date   DATE NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_lab_ss_order_status
      CHECK (order_status IN ('PAID', 'PENDING', 'CANCELLED')),
    CONSTRAINT ck_lab_ss_amount
      CHECK (amount >= 0)
);
~~~

### 3.2. Generate sample data

To give the optimizer enough data to compare access paths, generate 200,000 rows:

~~~sql
INSERT INTO lab_ss_orders (
    order_id,
    order_status,
    customer_id,
    order_date,
    amount
)
SELECT
    LEVEL,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'PAID'
        WHEN 1 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    MOD(LEVEL * 37, 10000) + 1,
    DATE '2024-01-01' + MOD(LEVEL, 730),
    MOD(LEVEL * 19, 50000) / 100
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;
~~~

With this formula:

- `ORDER_ID` runs from 1 to 200,000.
- `ORDER_STATUS` has three values.
- `CUSTOMER_ID` ranges from 1 to 10,000.
- Multiple orders belong to the same customer.

This is synthetic data for learning access paths, not a standard data distribution model for every application.

### 3.3. Create the composite index

~~~sql
CREATE INDEX ix_lab_ss_status_customer
ON lab_ss_orders (order_status, customer_id);
~~~

### 3.4. Gather statistics

The optimizer needs statistics to estimate cardinality and cost:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_SS_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

`CASCADE => TRUE` gathers statistics for associated indexes alongside the table. `DBMS_STATS` privileges and statistics policies vary by environment; in a lab schema, use the privileges granted to the schema.

### 3.5. Inspect value distribution

~~~sql
SELECT
    order_status,
    COUNT(*) AS order_count
FROM lab_ss_orders
GROUP BY order_status
ORDER BY order_status;
~~~

And:

~~~sql
SELECT
    COUNT(DISTINCT order_status) AS status_ndv,
    COUNT(DISTINCT customer_id) AS customer_ndv,
    COUNT(*) AS total_rows
FROM lab_ss_orders;
~~~

NDV stands for number of distinct values. This dataset has 3 `ORDER_STATUS` values and 10,000 `CUSTOMER_ID` values.

## 4. Query Eligible for Index Skip Scan

Query filtering only on `CUSTOMER_ID`:

~~~sql
SELECT
    order_id,
    order_status,
    customer_id,
    amount
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

The index is ordered `(ORDER_STATUS, CUSTOMER_ID)`, yet the predicate specifies only `CUSTOMER_ID`. Because `ORDER_STATUS` has three values, the optimizer may consider skip scan to look up `CUSTOMER_ID = 1234` within each status group.

If that access path is chosen, the execution plan will show the operation:

~~~text
INDEX SKIP SCAN
~~~

Because the query also fetches `ORDER_ID` and `AMOUNT`, which are not in the index, the plan may require `TABLE ACCESS BY INDEX ROWID` to fetch the remaining columns from the table.

**There is no guarantee** that the optimizer will choose skip scan on every machine or every run. If the table is small, statistics differ, bind values differ, or a full table scan is cheaper, the plan may differ.

## 5. Reading Execution Plans to Confirm Skip Scan

### 5.1. Using EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT
    order_id,
    order_status,
    customer_id,
    amount
FROM lab_ss_orders
WHERE customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PREDICATE +COST +NOTE'
    )
);
~~~

In the output, look for the `INDEX SKIP SCAN` operation and the index name `IX_LAB_SS_STATUS_CUSTOMER`.

A portion of the plan might look conceptually like:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Name                         |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT              |                              |
|  1 |  TABLE ACCESS BY INDEX ROWID  | LAB_SS_ORDERS                |
|  2 |   INDEX SKIP SCAN             | IX_LAB_SS_STATUS_CUSTOMER    |
--------------------------------------------------------------------------------
~~~

This only illustrates the operation shape; Id numbers, cost, cardinality, and whether `TABLE ACCESS` appears depend on the actual plan.

### 5.2. Using hints to observe the access path

If the optimizer picks a full table scan due to estimated cost, you can test the `INDEX_SS` hint in a lab environment to ask it to consider index skip scan:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.order_status,
    o.customer_id,
    o.amount
FROM lab_ss_orders o
WHERE o.customer_id = 1234;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The `INDEX_SS` hint is an experimentation and optimizer-steering tool. A hint may be ignored if the alias or index is wrong, inapplicable, or conflicts with query context. Always check the execution plan to verify whether the hint took effect.

Do not keep a hint solely because it produces `INDEX SKIP SCAN`. A good plan must fit real data and workload.

### 5.3. Viewing runtime metrics

`EXPLAIN PLAN` shows the estimated plan; to view actual execution statistics, use `GATHER_PLAN_STATISTICS`:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.order_status,
    o.customer_id,
    o.amount
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

After running the query:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST +NOTE'
    )
);
~~~

`ALLSTATS LAST` displays actual statistics from the most recent execution if statistics were collected. Reading cursors and underlying views may require extra privileges. If you lack privileges, use `EXPLAIN PLAN` or request assistance from a DBA.

## 6. Why Does the Optimizer Choose or Reject Skip Scan?

Oracle uses a cost-based optimizer (CBO). It estimates rows returned, blocks to read, and CPU/I/O cost, comparing feasible plans.

For skip scan, notable factors include:

1. Number of distinct values of the leading column.
2. Selectivity of the predicate on the trailing column.
3. Total row count and table size.
4. Index size and number of leaf blocks.
5. Index clustering factor.
6. Whether statistics are complete and up to date.
7. Alternative access paths, such as a separate index on the trailing column or a full table scan.
8. Number of query columns needed and cost of table access by ROWID.

### 6.1. Cardinality of the leading column

This is usually the first factor to inspect.

| Leading column | Distinct values | Skip scan suitability |
|---|---:|---|
| ORDER_STATUS | 3 | May be attractive if trailing key is selective |
| GENDER | 2 | May be attractive if other conditions align |
| COUNTRY_CODE | 200 | Likely costlier due to probing many groups |
| CUSTOMER_ID | 1000000 | Usually unattractive if leading column is omitted |

Low NDV reduces the number of logical subranges to probe. However, low NDV alone does not guarantee skip scan is good: if the trailing predicate returns too many rows, a full scan can still be cheaper.

### 6.2. Selectivity of the trailing column

Selectivity describes the fraction of rows matching the condition. If `CUSTOMER_ID = 1234` returns only a tiny fraction of 200,000 rows, the predicate is highly selective.

If the predicate returns most of the table, reading the index and accessing many ROWIDs can be more expensive than scanning the table sequentially.

Example:

~~~sql
-- Likely highly selective if each customer has few orders.
WHERE customer_id = 1234

-- Likely low selectivity if the range covers most customers.
WHERE customer_id BETWEEN 1 AND 9000
~~~

Do not judge by operator alone. Base decisions on data distribution and actual row counts.

### 6.3. Index and table sizes

An index much smaller than the table can make index search attractive. However, skip scan must probe multiple logical regions; if the index is large or leading NDV is high, total block reads can increase.

The optimizer weighs index access cost against fetching rows from the table. An index covering all `SELECT` columns can avoid table access, whereas a non-covering index may require ROWID lookups.

### 6.4. Clustering factor

Clustering factor reflects how closely key order in the index correlates with row locations in the table. When rows with nearby keys also sit near each other in data blocks, table access by ROWID can be efficient.

If the clustering factor is high, matching ROWIDs may be scattered across many blocks. When a query needs many columns not in the index, table access cost can rise sharply.

Thus, even if skip scan finds few entries, `TABLE ACCESS BY INDEX ROWID` can still make the plan expensive.

### 6.5. Statistics and cardinality estimation

The optimizer relies on table/index statistics and may use histograms when data distribution is skewed. Stale or missing statistics can cause the optimizer to misestimate row counts and select a suboptimal access path.

Inspect index metadata:

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    num_rows,
    last_analyzed
FROM user_indexes
WHERE index_name = 'IX_LAB_SS_STATUS_CUSTOMER';
~~~

Inspect column order:

~~~sql
SELECT
    index_name,
    column_name,
    column_position
FROM user_ind_columns
WHERE index_name = 'IX_LAB_SS_STATUS_CUSTOMER'
ORDER BY column_position;
~~~

These views show collected index statistics and structure. Do not turn a single metric like `BLEVEL` or `CLUSTERING_FACTOR` into a performance verdict without reviewing the workload and execution plan.

## 7. Comparing Skip Scan with Other Access Paths

### 7.1. Index range scan

With index `(ORDER_STATUS, CUSTOMER_ID)`, the query:

~~~sql
SELECT order_id, customer_id
FROM lab_ss_orders
WHERE order_status = 'PAID'
  AND customer_id = 1234;
~~~

constrains both the leading column and trailing column. Oracle can locate a single matching key range via `INDEX RANGE SCAN` without skipping across multiple leading key values.

### 7.2. Index skip scan

~~~sql
SELECT order_id, customer_id
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

No predicate on `ORDER_STATUS`. If the optimizer sees a cost benefit, it can use `INDEX SKIP SCAN` to probe the status subranges.

### 7.3. Full table scan

~~~sql
SELECT order_id, customer_id, order_status, amount
FROM lab_ss_orders
WHERE customer_id BETWEEN 1 AND 9000;
~~~

If most of the table satisfies the condition, reading the table sequentially can be cheaper than many index and ROWID table accesses. A full table scan is not inherently bad; it can be the most sensible choice.

### 7.4. Index full scan and fast full index scan

`INDEX FULL SCAN` reads the entire index in key order; `INDEX FAST FULL SCAN` reads index blocks optimized for I/O without guaranteeing key order like a regular full scan. Both operations differ from skip scan.

| Access path | General read mechanism | Commonly seen when |
|---|---|---|
| INDEX RANGE SCAN | Reads a contiguous key range defined by predicates | Predicate matches the leading key |
| INDEX SKIP SCAN | Probes logical regions by leading key, then searches trailing key | Leading key with low NDV is omitted |
| INDEX FULL SCAN | Reads entire index in key order | Index data or key order is needed |
| INDEX FAST FULL SCAN | Reads entire index via fast block scan without key order | Index is small/covering and many entries are needed |
| TABLE ACCESS FULL | Reads table blocks | Small table or query returns many rows |

Do not choose a plan based solely on operation names. Examine actual rows, buffers, reads, elapsed time, and system load.

## 8. Changing Index Column Order Can Eliminate the Need for Skip Scan

If the workload frequently queries by `CUSTOMER_ID` without filtering `ORDER_STATUS`, you can design the index in the reverse order:

~~~sql
CREATE INDEX ix_lab_ss_customer_status
ON lab_ss_orders (customer_id, order_status);
~~~

With the new index, `CUSTOMER_ID` is the leading column. The query:

~~~sql
SELECT order_id, customer_id, order_status, amount
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

can use `INDEX RANGE SCAN` directly by `CUSTOMER_ID`.

Meaning comparison:

| Index | Query by ORDER_STATUS | Query by CUSTOMER_ID only |
|---|---|---|
| `(ORDER_STATUS, CUSTOMER_ID)` | Favorable leading-key access | May use skip scan if cost is favorable |
| `(CUSTOMER_ID, ORDER_STATUS)` | Less favorable without CUSTOMER_ID | Favorable leading-key access |

No single column order is optimal for all queries. Consider common predicates, `JOIN` conditions, `ORDER BY`, `GROUP BY`, returned row counts, and index maintenance overhead during `INSERT`/`UPDATE`/`DELETE`.

### 8.1. Do not create both indexes mechanically

Both `(ORDER_STATUS, CUSTOMER_ID)` and `(CUSTOMER_ID, ORDER_STATUS)` can serve different query groups, but each index consumes storage and increases DML cost. Keep both only when the workload truly requires them and measured benefits exceed costs.

### 8.2. Index skip scan does not replace properly ordered indexes

If a column is filtered frequently with high selectivity, putting it in the leading position yields a more direct and predictable access path. Skip scan is an extra capability to leverage a composite index in certain queries, not a reason to invert every column order.

## 9. When Is Skip Scan Usually Unattractive?

Several situations:

- The leading column has too many distinct values.
- The trailing predicate is unselective, returning most of the table.
- The table is small, making a full table scan very cheap.
- The index is large or clustering factor makes table lookups expensive.
- The query needs many columns outside the index and must access many table blocks.
- Another index exists that better fits the query's leading key.
- Statistics do not accurately reflect data distribution.
- Predicates use expressions or datatype conversions that prevent the index from being used as expected.

For instance, if `ORDER_STATUS` were replaced by a nearly unique `TRANSACTION_ID` in `(TRANSACTION_ID, CUSTOMER_ID)`, searching for `CUSTOMER_ID` without `TRANSACTION_ID` could force Oracle to probe far too many leading key values. Skip scan is usually unattractive then.

## 10. Predicates, Expressions, and JOIN Conditions

Skip scan is evaluated based on predicates the optimizer can apply to index columns. Datatypes and how conditions are written matter.

Example:

~~~sql
-- Direct predicate on indexed column.
WHERE customer_id = 1234
~~~

Differs from:

~~~sql
-- Function applied to column.
WHERE TO_CHAR(customer_id) = '1234'
~~~

The second expression cannot use a standard index in the same way unless an appropriate function-based index exists or the optimizer rewrites the expression. Avoid unnecessary type casts and bind variables with the proper datatype.

In a `JOIN`, the optimizer can also choose an access path for one table based on values supplied by the other table. Skip scan can appear in complex plans if cost-effective, so read the full join order and predicate information rather than looking at a single operation in isolation.

## 11. Using the INDEX_SS and NO_INDEX_SS Hints

Oracle provides hints to influence index skip scan usage:

~~~sql
SELECT /*+ INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

Opposite hint:

~~~sql
SELECT /*+ NO_INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

`INDEX_SS` directs the optimizer to consider skip scan on the specified index; `NO_INDEX_SS` excludes skip scan on that index within the hint scope. Hints do not alter index structure or replace statistics.

### 11.1. Why should you not force hints upfront?

Hints can prevent plans from adapting as data changes. For example, today `ORDER_STATUS` has three values, but later the application adds many more statuses or `CUSTOMER_ID` distribution shifts. A skip scan that was once good can become more expensive.

Recommended workflow:

1. Run the SQL without hints.
2. Inspect the execution plan and runtime statistics.
3. Identify where the optimizer misestimates.
4. Check statistics, index column order, and predicates.
5. Test hints in a controlled environment for comparison.
6. Keep a hint only with clear evidence on a representative workload and a monitoring plan.

## 12. Reading Predicate Information

In `DBMS_XPLAN` output, the `Predicate Information` section distinguishes conditions used to access the index from conditions filtered only after fetching rows.

Illustrative example:

~~~text
Predicate Information:
----------------------
  2 - access("O"."CUSTOMER_ID"=1234)
~~~

Operation names and how Oracle displays predicates can vary by version, plan shape, and SQL syntax. Check both access and filter sections:

- Access predicates define the index/table region accessed.
- Filter predicates eliminate rows after a row source has been read.

A condition appearing under `FILTER` does not necessarily mean the index is useless; however, it indicates that the condition is not used in the same way to position the access range.

## 13. Role of Statistics and Histograms

The optimizer needs to know how data is distributed to estimate row counts.

### 13.1. Table statistics

Table statistics can include:

- `NUM_ROWS`.
- `BLOCKS`.
- `AVG_ROW_LEN`.
- `LAST_ANALYZED`.

### 13.2. Column statistics

Column statistics can include:

- `NUM_DISTINCT`.
- `NUM_NULLS`.
- `DENSITY`.
- `HISTOGRAM`.

For skip scan, the number of distinct values in the leading column is crucial. Selectivity of the trailing predicate also affects cardinality estimation.

You can inspect column statistics:

~~~sql
SELECT
    table_name,
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_SS_ORDERS'
  AND column_name IN ('ORDER_STATUS', 'CUSTOMER_ID')
ORDER BY column_name;
~~~

Histograms can help the optimizer handle skewed distributions, but creating histograms does not automatically make every plan better. Histograms can alter estimates per bind value and cause different values to get different plans; follow your system's statistics gathering policy.

### 13.3. Stale statistics

If data changes dramatically without updated statistics, the optimizer may think the leading column has a different distinct count than reality or misestimate rows for `CUSTOMER_ID`. When investigating an unexpected plan:

1. Check `LAST_ANALYZED`.
2. Check `NUM_ROWS` and `NUM_DISTINCT`.
3. Check histograms if present.
4. Compare estimated rows with actual rows.
5. Re-gather statistics if genuinely needed.

Do not run `GATHER_TABLE_STATS` arbitrarily in production without understanding statistics policies, locking, incremental stats, and SQL plan impact.

## 14. Skip Scan and Index Covering Capability

Index `(ORDER_STATUS, CUSTOMER_ID)` contains those two columns plus `ROWID`. If a query only needs columns stored in the index, Oracle can avoid table access:

~~~sql
SELECT order_status, customer_id
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

If index skip scan is chosen, the index can supply all columns to return the result. This is a covering access path.

Conversely:

~~~sql
SELECT order_id, order_status, customer_id, amount, order_date
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

needs additional columns not in the index, so table access by ROWID is typically required.

Do not add too many columns to an index just to turn every query into index-only. Larger indexes consume more storage, increase write overhead, and can reduce cache efficiency.

## 15. Index Skip Scan Is Not Index Fast Full Scan

Two easily confused concepts:

- Skip scan uses the composite index structure to search by a non-leading column by probing leading key values.
- Fast full index scan reads the entire index optimized for I/O without requiring results in key order.

Skip scan searches a subset of matching entries; fast full index scan reads the entire index. The operation name in the execution plan is direct proof, rather than merely seeing the index name in the plan.

## 16. Designing Composite Indexes by Workload

Before creating index `(A, B)`, ask:

1. Do queries more often filter on `A` or `B`?
2. Are there many queries filtering on both `A` and `B`?
3. Does `A` have few distinct values or very many?
4. Is `B` highly selective?
5. Do queries require `ORDER BY A, B`?
6. Do queries `JOIN` on `A` or `B`?
7. Does the index cover critical `SELECT` columns?
8. What is the `INSERT`/`UPDATE`/`DELETE` cost of adding the index?

Examples:

| Common query | Candidate index to evaluate |
|---|---|
| `WHERE order_status = :s` | `(order_status, customer_id)` |
| `WHERE order_status = :s AND customer_id = :c` | `(order_status, customer_id)` |
| `WHERE customer_id = :c` | `(customer_id, order_status)`, or evaluate skip scan on reverse index if leading NDV is low |
| `WHERE customer_id = :c ORDER BY order_date` | `(customer_id, order_date)` may be needed depending on workload |
| Query reading most of the table | Full table scan may suit better than an index |

Indexes in this table are evaluation suggestions, not automatic rules. Measure with representative data, bind values, and concurrency.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| A composite index can only be used when the leading column is present | Skip scan can use the index when predicates are only on trailing columns, if cost is favorable |
| Low distinct count on leading column guarantees skip scan | Also depends on selectivity, index/table sizes, clustering factor, and statistics |
| Skip scan is always faster than full table scan | No; queries returning many rows or large indexes can make full scan cheaper |
| Skip scan creates physical subindexes | No; subindexes are a logical interpretation per leading key |
| Skip scan guarantees Oracle will use the index | No; the optimizer chooses based on cost |
| Using ORDER or hints fixes index design | No; design indexes for the workload and measure |
| Seeing the index name in a plan means skip scan | Check the specific operation, e.g., `INDEX SKIP SCAN` |
| Adding every SELECT column to an index is always good | Index bloats and increases DML overhead |

## 18. Practice Exercises

### Exercise 1 — Identifying the leading column

Given index:

~~~sql
CREATE INDEX ix_a_b_c
ON some_table (a, b, c);
~~~

Identify the leading column and trailing columns. Explain under what conditions a query with only `WHERE b = :value` might be considered for skip scan.

### Exercise 2 — Comparing predicates

With index `(ORDER_STATUS, CUSTOMER_ID)`, compare three queries:

~~~sql
WHERE order_status = 'PAID'
~~~

~~~sql
WHERE order_status = 'PAID'
  AND customer_id = 1234
~~~

~~~sql
WHERE customer_id = 1234
~~~

**Hint:** the first and second queries have leading predicates; the third query is a candidate where skip scan might be considered.

### Exercise 3 — Observing NDV

Run `COUNT(DISTINCT ORDER_STATUS)` and `COUNT(DISTINCT CUSTOMER_ID)`. Explain why `ORDER_STATUS` is more suitable as the leading column in the skip scan example.

### Exercise 4 — Reading the execution plan

Run `EXPLAIN PLAN` for the query `CUSTOMER_ID = 1234`. Locate `INDEX SKIP SCAN`, `TABLE ACCESS BY INDEX ROWID`, and predicate information.

### Exercise 5 — Comparing with full table scan

Test a query with a wide `CUSTOMER_ID` range. Compare the unhinted plan with a plan using `NO_INDEX_SS` or `FULL` in the lab environment.

**Question:** Why can a full table scan be cheaper when a condition returns many rows?

### Exercise 6 — Testing a reversed index

Create index `(CUSTOMER_ID, ORDER_STATUS)`. Use the `INDEX` hint to inspect the access path when filtering `CUSTOMER_ID`. Compare with `(ORDER_STATUS, CUSTOMER_ID)`.

### Exercise 7 — Statistics

Query `USER_INDEXES` and `USER_TAB_COL_STATISTICS`. Explain the roles of `DISTINCT_KEYS`, `CLUSTERING_FACTOR`, and `NUM_DISTINCT`.

### Exercise 8 — Hints

Compare `INDEX_SS` and `NO_INDEX_SS`. Check the execution plan to confirm the hint took effect.

**Question:** Why should you not keep `INDEX_SS` solely because it makes `INDEX SKIP SCAN` appear in the plan?

### Exercise 9 — Workload-driven design

An application has:

- 60% of queries filtering by `CUSTOMER_ID`.
- 25% of queries filtering by `ORDER_STATUS`.
- 15% of queries filtering by both.

Propose an index column order and explain whether one or two indexes are needed. State the DML and storage trade-offs to weigh.

## 19. Process for Evaluating Index Skip Scan

When you see a query missing the leading column of a composite index, follow this sequence:

1. Check the actual column order in the index.
2. Identify which columns the predicates filter.
3. Check the NDV of the leading column.
4. Check selectivity/cardinality of the trailing column predicate.
5. Check table/index statistics and clustering factor.
6. Check which access path the optimizer selected.
7. Compare estimated rows with actual rows.
8. Test alternative index orders or hints in a lab to understand the options.
9. Measure logical reads, physical reads, buffers, and elapsed time on a representative workload.
10. Choose index design based on the total workload, not a single SQL statement.

Diagram:

~~~text
Query without leading column predicate
                 |
                 v
Inspect composite B-tree index
                 |
                 v
Does leading column have low NDV?
          /              \
         No              Yes
         |                 |
         v                 v
Skip scan usually     Is trailing predicate
unattractive          selective?
                           |
                     +-----+-----+
                     |           |
                    No          Yes
                     |           |
                     v           v
              Consider FTS   Check index size,
              or another     clustering factor,
              access path    statistics, and cost
                                  |
                                  v
                         Check execution plan
                                  |
                                  v
                        Measure actual runtime
                                  |
                                  v
                       Choose index by workload
~~~

Index skip scan broadens the usefulness of composite B-tree indexes when queries omit the leading column. It is most worth considering when the leading column has few distinct values and the predicate on the trailing column is highly selective. Still, the optimizer must compare its cost against index range scans, other indexes, and full table scans. Check the operation in the execution plan, verify statistics, and measure runtime before altering column order or forcing hints. Index design should serve the overall workload, with skip scan acting as a supplementary access path when the data shape fits.
