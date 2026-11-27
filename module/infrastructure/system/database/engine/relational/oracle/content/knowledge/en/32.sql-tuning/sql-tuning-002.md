# Reducing Rows and Columns Processed Before Expensive Operations

In Oracle Database, a SQL statement may have to read, join, sort, group, or deduplicate a very large volume of data before returning results. These operations typically consume CPU, memory, and I/O; when work areas lack sufficient memory, Oracle may also have to write temporary data to TEMP. Therefore, an important principle in SQL tuning is to **reduce the number of rows and columns each processing step receives as early as possible**, as long as the query's semantics are preserved.

This principle has two complementary parts:

- **Row reduction:** eliminate irrelevant records before performing joins, sorts, groupings, window calculations, or deduplication.
- **Column reduction:** read and carry only the columns actually needed for the output, filter conditions, join conditions, sorting, or calculations.

For example, if a report only needs a customer's 50 most recent orders, reading all columns of millions of orders before filtering and sorting wastes resources. The query should let Oracle know the date range, customer, and required columns early; the cost-based optimizer will then choose an appropriate execution plan.

## 1. Why reduce data before expensive operations?

Suppose the `ORDERS` table has 20 million rows, each containing order ID, customer ID, order date, status, amount, and a `CLOB` notes column. A report query only needs the order ID, date, and amount for paid orders in a single month.

If the query reads all columns and all rows before filtering, Oracle may end up processing far more data than necessary. As the number of rows or the width of each row grows, the cost of passing data between steps in the execution plan increases as well.

Operations that commonly become expensive with large inputs include:

| Operation | Why input data volume matters |
|---|---|
| `SORT ORDER BY` | Must sort the candidate rows; can consume significant memory or TEMP. |
| `HASH JOIN` | Must build and probe hash structures; large inputs increase memory and processing work. |
| `HASH GROUP BY` / `SORT GROUP BY` | Must aggregate many rows and maintain state for groups. |
| `DISTINCT` | Must identify duplicate rows, usually requiring a sort or hash. |
| Analytic/window functions | Must partition and potentially sort rows within each window. |
| Table and LOB access | Reading extra wide columns or LOBs can increase I/O and returned data volume. |

Not every full table scan or hash join is bad. If a query needs most of a table's data, a full table scan can be more efficient than reading an index and fetching rows one by one. The goal is to reduce unnecessary data and let Oracle choose an appropriate access path, not to force every query to use an index.

## 2. Understanding how Oracle executes SQL

SQL describes **what result is needed**, while Oracle decides **how to obtain it**. The order in which clauses are written in a SQL statement is not the physical execution order. The optimizer can reorder table joins, push filter predicates into views or subqueries, prune unused columns, and transform the query as long as the transformation preserves the result.

Therefore, writing filter conditions early and selecting only necessary columns gives the optimizer clear information to produce a good plan. However, simply seeing `WHERE` before `ORDER BY` in the SQL text does not prove that data was filtered before sorting. You must inspect the execution plan and runtime statistics to know what actually happened.

Two common concepts are:

- **Predicate pushdown:** pushing filter conditions as close as possible to where data is read, so downstream steps receive fewer rows.
- **Projection pushdown:** retaining only the columns needed in lower steps, so intermediate data is narrower.

Oracle can perform these transformations automatically. Good SQL authoring makes conditions and column requirements explicit while avoiding constructs that make optimization opportunities hard for the optimizer to recognize.

## 3. Reducing rows with effective filter predicates

### 3.1. Filtering by specific ranges in `WHERE`

Place conditions that can be applied directly to the source table in `WHERE`. For example, if a report only needs paid orders from November 2026:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01';
```

The date condition uses a half-open interval: inclusive of the start timestamp and exclusive of the start of the next month. This correctly handles every timestamp on the last day of the month, even when `ORDER_DATE` includes hours, minutes, and seconds.

If the date column is stored as `DATE` or `TIMESTAMP`, pass a bind variable of the matching type when the application executes the query. Avoid converting the column to a string for comparison.

### 3.2. Avoiding wrapping filter columns in functions unnecessarily

A common pattern is:

```sql
SELECT order_id, order_date
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

`TRUNC(order_date)` applies a function to every value in the column. A regular index on `ORDER_DATE` may not be usable effectively for this condition because the searched expression is no longer the raw column value.

It can be rewritten as a time range:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

Range predicates typically allow Oracle to use an index on `ORDER_DATE` and support partition pruning if the table is partitioned on that column. This is semantically equivalent for retrieving the entire 14th day without applying a function to the column.

If the business requirement genuinely needs to search by an expression like `UPPER(email)`, consider a function-based index on that exact expression. That decision should be based on workload, selectivity, statistics, and index maintenance overhead during writes.

### 3.3. Writing predicates that can leverage indexes and partition pruning

B-tree indexes are generally helpful when a condition selects a relatively small portion of a table. Favorable condition patterns include equality comparisons, range comparisons, and join predicates on appropriate columns:

```sql
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date
```

If `ORDERS` is partitioned by `ORDER_DATE`, a range predicate on the partition key can allow Oracle to access only the relevant partitions. This is partition pruning. Wrapping the partition key in `TRUNC(order_date)` or inappropriate data type conversions can limit pruning.

When considering a composite index, examine the full query pattern. A candidate index may include equality filter columns, range filter columns, and join columns; column order must match actual predicates and selectivity. There is no single column order that fits every workload. Indexes also consume space and increase the cost of `INSERT`, `UPDATE`, and `DELETE`, so do not create an index based on a single isolated SQL statement.

### 3.4. Placing filter conditions properly with `GROUP BY` and `HAVING`

`WHERE` filters input rows before grouping. `HAVING` filters grouped results after aggregates have been computed. If a condition does not depend on aggregate results, placing it in `WHERE` usually reduces the number of rows that must be grouped.

Example:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS total_paid
FROM orders
WHERE status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date
GROUP BY customer_id
HAVING SUM(total_amount) > :minimum_total;
```

Here, status and date are filtered before grouping. The condition on each customer's total amount must remain in `HAVING` because it depends on the `SUM` result. It cannot be moved to row-level filtering while preserving the same meaning.

### 3.5. Using `EXISTS` when you only need to know if related records exist

If the goal is simply to find customers who have at least one paid order, a regular join can produce multiple rows per customer when a customer has multiple orders. The query might then have to use `DISTINCT` to deduplicate.

You can express the intent directly with `EXISTS`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.order_date >= :from_date
      AND o.order_date <  :to_date
);
```

`EXISTS` only checks for the existence of at least one matching row. Oracle can transform the query into a semi join to avoid generating all joined pairs just to test existence. `SELECT 1` inside the subquery indicates that column values are unused; Oracle does not need to fetch output columns from the order rows for this purpose.

If you need to display individual orders or sum order amounts, use an appropriate join. Do not replace `JOIN` with `EXISTS` if doing so drops rows or values required in the output.

### 3.6. Preserving semantics when filtering before joins

Filtering tables before joining is often beneficial, but predicate placement can change results, especially with outer joins.

For example, the following query keeps all customers and only matches paid orders:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

If `o.status = 'PAID'` is moved to `WHERE`, customer rows with no matching order will be eliminated because the `o` columns are `NULL`. In that case, the result can effectively become equivalent to an inner join for that predicate. Only move conditions after confirming the transformation preserves business rules.

## 4. Reducing columns with explicit projection

### 4.1. Avoiding `SELECT *` in targeted queries

Suppose a table has columns `ORDER_ID`, `CUSTOMER_ID`, `ORDER_DATE`, `STATUS`, `TOTAL_AMOUNT`, `SHIPPING_ADDRESS`, and a `CLOB` column `NOTES`. If a screen only displays order ID, date, and amount, write:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id;
```

instead of:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Explicitly selecting columns reduces the data that must be read, held in intermediate steps, sent over the network, and marshaled at the application tier. This is especially significant for wide columns like `CLOB`, `BLOB`, large JSON, or long text columns. It also keeps the query's data contract clear when new columns are added to the table.

### 4.2. Carrying only columns needed for downstream steps

In multi-table queries, each branch only needs to retain columns serving one of the following purposes:

- Returned in the final output.
- Used in join conditions.
- Used in filter conditions.
- Used in `GROUP BY`, `ORDER BY`, expressions, or analytic functions.

For example, a per-customer aggregation query does not need to carry the shipping address or notes of every order:

```sql
WITH paid_orders AS (
    SELECT
        customer_id,
        total_amount
    FROM orders
    WHERE status = 'PAID'
      AND order_date >= :from_date
      AND order_date <  :to_date
)
SELECT
    c.customer_id,
    c.customer_name,
    SUM(p.total_amount) AS total_paid
FROM paid_orders p
JOIN customers c
    ON c.customer_id = p.customer_id
GROUP BY c.customer_id, c.customer_name;
```

The `paid_orders` CTE makes clear that the query only needs customer ID and amount for matching orders. Oracle can inline or merge the CTE into the main query and continue optimizing the entire statement; do not assume `WITH` always creates a temporary table or always forces materialization. The primary benefit of this style is expressing the exact required columns and filters.

### 4.3. Considering index-only access

If a query only needs columns already present in an index, Oracle can sometimes satisfy the result from the index without visiting table blocks. This is an opportunity to reduce I/O. For example, a composite index might contain customer ID and order date for a query that only needs those two columns.

However, do not add every output column to an index solely to achieve index-only access. Wider indexes take more space, consume more buffer cache, and increase maintenance overhead when data changes. Weigh query frequency, selected row count, write volume, and other queries sharing the index.

## 5. Reducing data before `JOIN`, `SORT`, `DISTINCT`, and aggregations

### 5.1. Filtering before joining large datasets

Suppose a report needs total paid amount per customer over a date range. A clear way to write it is:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    SUM(o.total_amount) AS total_paid
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_date >= :from_date
  AND o.order_date <  :to_date
GROUP BY c.customer_id, c.customer_name;
```

The predicates on `ORDERS` indicate that only paid orders within the reporting range are relevant. Oracle can push these predicates down to the `ORDERS` access step before joining with `CUSTOMERS`. The actual execution plan also depends on statistics, indexes, partitioning, estimated row counts, and the cost of each alternative.

You do not need to create an inline view just to restate the same predicate if the optimizer can already push it down. Conversely, do not rely on subquery syntax alone to assume a guaranteed execution order. Verify with the execution plan.

### 5.2. Avoiding `DISTINCT` to mask row-multiplication bugs

`DISTINCT` may require sorting or hashing across the selected columns. If a query produces duplicate rows because a parent table is joined to a child table with multiple records, and then uses `DISTINCT` to collapse back to one row per parent, check whether the real goal is merely an existence check. In that case, `EXISTS` can express the intent accurately and avoid generating duplicate rows in the first place.

Do not remove `DISTINCT` mechanically. If the business requirement genuinely calls for unique combinations of values, `DISTINCT` is part of the semantics and must be kept. You can reduce its cost by selecting only the required columns before deduplicating, rather than feeding extra wide columns into the comparison.

### 5.3. Sorting only when ordered output is required

An `ORDER BY` clause may require Oracle to sort a large number of rows. If ordering is not required by the output or UI, omit `ORDER BY`. Row order is not guaranteed without `ORDER BY`, so relying on an incidental order observed in testing is unsafe.

If only the first few rows are needed, combine ordering with a row limit:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

`FETCH FIRST` has been supported since Oracle Database 12c. Oracle may use a top-N plan such as `SORT ORDER BY STOPKEY`, or leverage a suitable index to retrieve the leading rows. However, limiting results does not guarantee Oracle only reads 20 rows: without a matching access path, the system may still have to inspect and sort many rows to determine the top 20.

The secondary sort `ORDER_ID DESC` makes results deterministic when multiple orders share the same `ORDER_DATE`. When using top-N or pagination, include sort keys sufficient to distinguish rows.

### 5.4. Deep pagination with keyset pagination

`OFFSET` pagination can do extra work on deep pages because Oracle must identify and skip preceding rows. For large data streams, consider keyset pagination: pass back the key of the last row from the previous page and request the next rows.

Example with descending order by date and order ID:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (
        order_date < :last_order_date
        OR (order_date = :last_order_date AND order_id < :last_order_id)
      )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

The application passes `:last_order_date` and `:last_order_id` from the last row of the prior page. Ensure the key pair establishes a stable total order and has an index matching the customer predicate and sort order. If data changes between page requests, the application should also define its pagination consistency requirements.

### 5.5. Being careful with `ROWNUM` on older versions

On Oracle releases that do not support `FETCH FIRST`, you can limit top-N by sorting inside a subquery and applying `ROWNUM` in the outer block:

```sql
SELECT order_id, order_date, total_amount
FROM (
    SELECT order_id, order_date, total_amount
    FROM orders
    WHERE customer_id = :customer_id
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM <= 20;
```

Do not put `ROWNUM <= 20` and `ORDER BY` in the same query block when the goal is to get the 20 newest rows. `ROWNUM` is assigned before the sort step of that query block, so the result could be 20 arbitrary rows picked first and then sorted, rather than the 20 newest rows.

## 6. Cases where predicates cannot be pushed down arbitrarily

Reducing data as early as possible is a tuning principle, but filter predicates must preserve calculation semantics.

- **Outer join:** a condition on the nullable-side table placed in `ON` can keep unmatched rows; placed in `WHERE`, it can filter them out.
- **Aggregation:** row-level conditions belong in `WHERE`; conditions on `SUM`, `COUNT`, `AVG`, or group results belong in `HAVING`.
- **Analytic functions:** filtering rows before evaluating `ROW_NUMBER`, `RANK`, or `SUM(...) OVER (...)` can change the window row set and rankings. Only push a condition down if that is the intended behavior.
- **Top-N:** filtering before ranking can differ from ranking everything and then filtering. Be clear about the scope of top-N.
- **Set operators:** `UNION` removes duplicates, whereas `UNION ALL` keeps all rows. Only replace `UNION` with `UNION ALL` when you have proven duplicates cannot occur or are allowed.

For example, if you need to rank orders per customer, the query must define the exact set of orders participating in the ranking:

```sql
SELECT customer_id, order_id, order_date, rn
FROM (
    SELECT
        customer_id,
        order_id,
        order_date,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY order_date DESC, order_id DESC
        ) AS rn
    FROM orders
    WHERE status = 'PAID'
)
WHERE rn <= 3;
```

Here, `status = 'PAID'` defines which orders enter the ranking. `rn <= 3` must be applied after `ROW_NUMBER` is computed. Moving the second condition into the inner block before the analytic function would not preserve the top-3 semantics.

## 7. Measuring with execution plans instead of guessing

After modifying SQL, verify whether Oracle actually reads fewer rows and less data. A shorter SQL statement or one with extra CTEs is not automatically faster.

### 7.1. Viewing the estimated execution plan

You can use `EXPLAIN PLAN` to inspect the plan Oracle anticipates:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` does not execute the SQL statement. Its numbers are estimates based on statistics available to the optimizer; they can differ from actual runtime data for a specific execution.

### 7.2. Viewing statistics from actual execution

When you need to know how many rows actually flowed through each step, collect runtime statistics with the `GATHER_PLAN_STATISTICS` hint and inspect the cursor just executed:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +MEMSTATS'
    )
);
```

`ALLSTATS LAST` displays statistics for the most recent execution when runtime statistics were collected. The hint in the example requests statistics collection for that SQL statement; collection adds a small amount of overhead. An alternative is setting `STATISTICS_LEVEL = ALL` in an appropriate scope, subject to environment privileges and governance procedures.

When reading the output, pay attention to:

| Field | How to use it |
|---|---|
| `E-Rows` | Optimizer's estimated row count for a step. |
| `A-Rows` | Actual row count returned by that step in the recorded run. |
| `Starts` | Number of times a step was started; examine alongside `A-Rows` to understand row volume across iterations. |
| `Buffers` | Logical reads; useful for comparing blocks processed. |
| `Reads` | Recorded physical reads. |
| `A-Time` | Recorded execution time for the step, interpreted in the context of the whole plan. |
| `TempSpc`, `OMem`, `1Mem`, `Used-Mem` | Show estimated temp space and memory details for memory-intensive operations; inspect alongside runtime statistics to spot operations needing substantial memory or spilling to TEMP. |
| `Predicate Information` | Shows where access and filter predicates are applied. |

If `A-Rows` spikes at a join step relative to its inputs, check one-to-many relationships and join predicates. If `E-Rows` diverges widely from `A-Rows`, statistics or data distribution may be causing misestimates. If a sort or hash receives too many rows, look for predicates that can be applied earlier while preserving semantics. If row counts are already small yet `Buffers` is high, inspect the access path, indexes, partition pruning, and table visit counts.

Access to cursors and runtime statistics depends on configuration, privileges, and Oracle version. In shared or production environments, follow established operational procedures when collecting and analyzing metrics.

### 7.3. Verifying both correctness and performance

When comparing queries before and after tuning:

1. Use the same bind variable set and representative data conditions.
2. Confirm row counts and output values still meet business requirements.
3. Compare execution plans, `A-Rows`, `Buffers`, `Reads`, timing, and TEMP if any.
4. Test bind values with differing selectivity; a query can be fast for a customer with few orders yet slow for a customer with many orders.
5. Evaluate impact on other queries and write overhead if indexes changed.

Do not draw conclusions from a single run or timings measured only on a development machine. Caching, system load, bind variables, statistics, and data distribution can all alter results.

## 8. Practical tuning workflow

When encountering a SQL statement processing too much data, follow this process:

1. **Define the exact output needed:** list output columns, row scope, ordering, grouping rules, and business conditions.
2. **Locate expensive processing steps:** inspect the execution plan and runtime statistics; identify sorts, hash joins, group bys, distincts, table accesses, or LOB accesses consuming resources.
3. **Reduce rows at the source:** place aggregate-independent conditions in `WHERE`, filter with appropriate ranges, leverage partition pruning, and evaluate indexes against the workload.
4. **Reduce row width:** remove `SELECT *`, avoid carrying unused or LOB columns, and keep only join keys and computation columns.
5. **Avoid generating redundant rows:** inspect one-to-many relationships, use `EXISTS` for existence checks, and use `DISTINCT` only when deduplication is genuinely required.
6. **Limit results purposefully:** if only top-N is needed, use a deterministic `ORDER BY` with `FETCH FIRST`; consider keyset pagination for deep pages.
7. **Re-measure and verify:** compare actual rows per step, logical reads, physical reads, TEMP, and timing, while verifying business results.

## 9. Common pitfalls to avoid

| Practice | Issue | Better approach |
|---|---|---|
| `SELECT *` when only a few columns are needed | Increases data read, transferred, and held in intermediate steps. | List only the columns actually needed. |
| `TRUNC(date_col) = ...` | Can hinder regular indexes and partition pruning. | Use `>=` and `<` ranges on the raw column, or consider a function-based index if appropriate. |
| Using `DISTINCT` to fix multiplied rows | Forces extra work and can hide a broken join. | Check cardinality; use `EXISTS` if only existence matters. |
| Sorting all data before limiting | Can cause a large sort. | Use top-N properly and check the access path. |
| Moving an outer join predicate from `ON` to `WHERE` | Can drop unmatched rows. | Check `NULL` semantics and predicate placement. |
| Creating an index for every filter column | Increases space and DML cost; index might not be chosen. | Evaluate selectivity, column order, workload, and execution plan. |
| Forcing an index with hints before measuring | Can lock the query into a bad plan as data shifts. | Let the optimizer choose first; use hints only with evidence and change control. |
| Assuming CTEs are always materialized | Oracle can inline or merge CTEs. | Use CTEs for clarity; verify the actual execution plan. |

## 10. Combined example

Suppose a screen needs to display a customer's 20 most recent paid orders. The table has many columns, including a `CLOB` column `NOTES`, and spans several years of data.

An untrimmed query might read every column, apply a function to the date, and sort all of the customer's orders:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND TRUNC(order_date) <= TRUNC(:as_of_date)
ORDER BY order_date DESC;
```

The query can be written with explicit data scope and output columns as follows:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date < :next_day
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

The application sets `:next_day` to the start of the following day according to the agreed timezone and business rules. The new query:

- Selects only the three columns needed for display, avoiding `NOTES` and unused columns.
- Filters by customer, status, and timestamp directly at the source table.
- Avoids applying `TRUNC` to `ORDER_DATE`, facilitating appropriate index usage or partition pruning.
- Requests only the first 20 rows in an order with a tie-breaker key for stability when dates match.

A candidate index such as `(CUSTOMER_ID, STATUS, ORDER_DATE, ORDER_ID)` can be evaluated, though column order and sort direction must be tested against data distribution, related queries, and execution plans. If status has low selectivity or the table is date-partitioned, the optimal design may differ. You cannot conclude which index is best from the SQL statement alone.

After running the query with representative bind sets, inspect `DBMS_XPLAN.DISPLAY_CURSOR` to confirm whether Oracle reduced rows at the `ORDERS` access step, avoided reading unnecessary columns, used an appropriate access path, and bounded the sort efficiently. Finally, compare results against the original query to ensure the new date predicate and ordering still meet requirements.

## Conclusion

When tuning SQL in Oracle, clarify the required row scope and column set before data enters joins, sorts, groupings, deduplication, and window calculations. Effective filter predicates, lean projections, goal-aligned joins, and purposeful row limiting typically reduce CPU, memory, I/O, and TEMP usage. Final effectiveness must be confirmed via execution plans, runtime statistics, and result correctness verification.
# Reducing Rows and Columns Processed Before Expensive Operations

A SQL query may have to read millions of rows only to return a few dozen. Performance depends heavily on whether Oracle eliminates unnecessary data early or carries a large dataset through multiple operations such as joins, sorts, group bys, window functions, or inter-process data exchanges.

Two quantities to watch are:

- **Row count (cardinality):** how many rows pass through each row source.
- **Row width:** how many columns and bytes each row carries.

A dataset with few rows where each row contains multiple large columns can still consume substantial memory and I/O. Conversely, a narrow dataset with millions of rows can still make hash joins, sorts, or aggregations expensive. Query tuning therefore requires reducing both row counts and row width at appropriate points in the execution tree.

The practical principle is to move filter conditions close to the data source, select only the columns actually needed, and ensure join/aggregate/sort operations receive the smallest possible inputs while preserving SQL semantics.

## 1. Why do row count and column count matter?

Suppose a query reads an `ORDERS` table with 8 million rows, but only needs orders for one customer in one month. If Oracle must read and process many rows before applying filter conditions, upstream operations may do far more work than necessary.

Picture a pipeline:

```text
TABLE ACCESS
    ↓
JOIN
    ↓
SORT
    ↓
GROUP BY
    ↓
RESULT
```

If data is filtered right at table access, the upstream join and sort receive fewer rows. If only required columns are selected, each row flowing through the pipeline is also lighter.

### 1.1. Cardinality affects operation cost

Input row count directly drives the amount of work for many operations:

- Nested loops may perform inner lookups proportional to the outer row count.
- Hash joins must build and probe hash tables sized to their inputs.
- Sorts must order all received rows.
- Group by must maintain aggregation state across groups.
- Window functions must process partitions and row ordering accordingly.
- Parallel execution may have to redistribute large data volumes across processes.

If a predicate cuts rows from 2,000,000 down to 5,000, upstream operations can save substantial work. However, not every predicate can be pushed to the lowest level: SQL has rules for outer joins, aggregations, analytic functions, and subqueries that the optimizer must preserve.

### 1.2. Row width affects memory and I/O

Two queries can read the same 100,000 rows yet incur different costs if one selects only keys and amounts while the other also retrieves large text or LOB columns.

Example:

```sql
-- Select only the data needed for the report.
SELECT order_id,
       customer_id,
       total_amount
FROM orders
WHERE order_status = 'PAID';
```

```sql
-- Select all columns even though the report only needs three.
SELECT *
FROM orders
WHERE order_status = 'PAID';
```

`SELECT *` can increase the bytes read, transferred, stored in workareas, and returned to the client. It also couples the SQL statement more tightly to table structure. Oracle can perform projection pruning when columns are unused, but when a SQL statement asks for every column, the optimizer must fulfill that request.

### 1.3. The goal is not always eliminating every operation

A full table scan is not inherently bad. If a query needs most of the data or the table is small, a full scan can be the most efficient approach. A sort may be mandatory if results must be ordered in a sequence not already provided.

The goal is reducing unnecessary work. Look at the actual rows and bytes flowing through each operation rather than trying to eliminate an operation merely because of its name.

## 2. Filtering early with WHERE and predicate pushdown

`WHERE` specifies row filter conditions before results pass to subsequent steps according to query semantics. The Oracle Optimizer can perform *predicate pushdown*: pushing predicates closer to the data source to reduce intermediate rows.

For example, a query needing paid orders in October:

```sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-10-01'
  AND o.order_date <  DATE '2026-11-01';
```

If the plan applies both predicates right at the `ORDERS` access path, only matching rows are forwarded to any upstream join or aggregation. Writing half-open range conditions also avoids converting date columns to strings or truncating the time component.

### 2.1. Predicates that can use indexes and partition pruning

A predicate is generally better suited for index usage when it compares a column directly to a value or bind variable of a compatible type:

```sql
WHERE order_id = :p_order_id
```

```sql
WHERE order_date >= :p_from_date
  AND order_date <  :p_to_date
```

Conversely, expressions transforming the column can make a regular index difficult to use as intended:

```sql
-- May hinder range access on a regular index on ORDER_DATE.
WHERE TRUNC(order_date) = DATE '2026-10-15'
```

This can be rewritten as a date range:

```sql
WHERE order_date >= DATE '2026-10-15'
  AND order_date <  DATE '2026-10-16'
```

If business logic truly requires querying by `TRUNC(order_date)`, consider a function-based index or virtual column. Rewriting predicates must preserve data types, timezones, and business rules.

Avoid transforming columns with `TO_CHAR`, `TO_NUMBER`, or other functions when unnecessary. Also watch for implicit conversion: if both sides of a comparison have different types, Oracle may have to convert one side, making the access path less efficient. Use bind variables matching the column's data type.

### 2.2. Using time ranges instead of applying functions to columns

For a `DATE` column containing time components, the condition:

```sql
WHERE order_date = DATE '2026-10-15'
```

only matches values at exact midnight on that day. If the goal is the entire day, use a half-open range:

```sql
WHERE order_date >= DATE '2026-10-15'
  AND order_date <  DATE '2026-10-16'
```

Avoid using:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-10-15'
```

because the conversion expression can keep a regular index on `ORDER_DATE` from being a favorable access path and relies on explicit formatting. With `TIMESTAMP` or `TIMESTAMP WITH TIME ZONE`, choose bind types and time boundaries matching application semantics.

### 2.3. Predicates with OR

Some predicates using `OR` can make it harder for the optimizer to pick a simple access path:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :p_customer_id
   OR order_status = :p_status;
```

Oracle can use OR expansion to transform this into separate branches if beneficial and semantically equivalent. In some cases, it can be rewritten as `UNION ALL` with mutually exclusive conditions:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :p_customer_id

UNION ALL

SELECT order_id, order_date
FROM orders
WHERE order_status = :p_status
  AND (customer_id <> :p_customer_id OR customer_id IS NULL);
```

This example illustrates splitting into two branches while avoiding returning rows that satisfy both conditions twice. `NULL` handling is critical because SQL comparisons with `NULL` evaluate to UNKNOWN. Do not apply this rewrite pattern without proving equivalence for data types, NULL semantics, and deduplication requirements of the original query. `UNION` removes duplicates but usually requires a distinct step; `UNION ALL` retains duplicates and is typically lighter when branches are made disjoint.

### 2.4. Predicate pushdown through views and subqueries

Example of an aggregate view:

```sql
SELECT *
FROM (
    SELECT customer_id,
           order_status,
           SUM(total_amount) AS amount
    FROM orders
    GROUP BY customer_id, order_status
) x
WHERE x.order_status = 'PAID';
```

Oracle can push the predicate on `ORDER_STATUS` below the group by step if semantics are preserved:

```sql
SELECT customer_id,
       order_status,
       SUM(total_amount) AS amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id, order_status;
```

Filtering before aggregation reduces the rows that must be grouped. However, not every outer predicate can be pushed through every view. Predicates involving aggregate results, analytic functions, outer joins, or other transformations may have to stay at the upper level.

Writing an inline view does not guarantee Oracle materializes the result into a temporary table. The optimizer can merge the view, push predicates, or transform query blocks. Verify with the execution plan rather than inferring purely from SQL syntax.

## 3. Reducing data before JOIN

Joins can multiply work rapidly, especially when a large table is combined with another table before a highly selective filter is applied.

Suppose we need paid orders for a region:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID'
  AND c.region_id = :p_region_id;
```

The optimizer can push predicates on `ORDERS` and `CUSTOMERS` down to their respective row sources before joining. If region data represents a small slice and `PAID` status is also selective, the input branches can be much smaller.

You do not need to rewrite every query with inline views to force pre-join filtering. First write clear predicates, ensure appropriate statistics, and inspect the plan. If the optimizer cannot push a predicate due to query block structure or semantic constraints, then consider a verified rewrite.

### 3.1. Using EXISTS when you only need to know if related records exist

If you only need customers who have at least one paid order, there is no need to join to return order columns:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'PAID'
);
```

`EXISTS` accurately expresses the intent of checking existence. Oracle can transform it into a semi join, allowing it to stop searching once a single matching row is found instead of generating all matching pairs and deduplicating.

Compare with joining and applying distinct:

```sql
SELECT DISTINCT c.customer_id,
                c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID';
```

If a customer has many orders, the join generates multiple rows per customer and `DISTINCT` must deduplicate them. `EXISTS` directly describes the requirement and often avoids those intermediate rows. The optimizer may still transform both SQL statements; inspect the plan and ensure identical semantics.

### 3.2. Using NOT EXISTS for non-existence checks

To find customers who have never placed an order:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Oracle can use an anti join. This avoids building the full join result just to find non-matching rows.

Be careful when replacing `NOT IN` with `NOT EXISTS`. If the subquery in `NOT IN` can return `NULL`, `NOT IN` follows three-valued logic and can differ from `NOT EXISTS`. Handle `NULL` strictly according to business rules.

### 3.3. Joining only the needed columns

When joining, avoid carrying all columns of tables across multiple operations if the result only uses a few columns:

```sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
```

Here, the query only needs `ORDER_ID`, `CUSTOMER_NAME`, `CUSTOMER_ID` for joining, and `ORDER_STATUS` for filtering. There is no need to pass addresses, long notes, LOBs, or other unused attributes.

Projection pruning can strip unnecessary columns at layers within the plan. However, `SELECT *`, wide views, or expressions requiring wide data can reduce pruning opportunities and raise data transfer costs.

## 4. Reducing columns with projection pruning

Projection determines which columns must be kept at each processing step. The optimizer can push projection closer to the data source to read or pass only the columns required by upstream operations.

Example report query:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
```

The required columns are:

- `CUSTOMER_ID` for grouping.
- `TOTAL_AMOUNT` for summing.
- `ORDER_STATUS` for filtering.

Columns like `ORDER_NOTE`, `SHIPPING_ADDRESS`, `ATTACHMENT`, or `CREATED_BY` do not participate in the query and do not need to be carried into aggregation.

### 4.1. Avoiding SELECT *

`SELECT *` commonly causes these issues:

- Reading or transferring unneeded columns.
- Increasing row source and workarea size.
- Making the query more fragile to columns being added to the table.
- Potentially preventing covering indexes from satisfying the entire query.
- Increasing data sent over the network to the application.

Instead of:

```sql
SELECT *
FROM orders
WHERE order_status = 'PAID';
```

select columns explicitly:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE order_status = 'PAID';
```

Explicit column selection also makes the API's data contract more stable. When new columns are added to the table, the query's output shape does not unexpectedly change.

### 4.2. Columns in SELECT, WHERE, JOIN, and ORDER BY

A column might not appear in the SELECT list yet still need to be read for filtering, joining, grouping, or sorting. Projection pruning does not mean reading only the final output columns; it keeps every column required for the entire computation.

Example:

```sql
SELECT order_id,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC;
```

`CUSTOMER_ID` and `ORDER_DATE` are not returned, yet are still required by the predicate and order by. If an appropriate index contains the relevant columns, Oracle can satisfy the query from the index without table access, depending on index structure and requested columns.

### 4.3. Covering indexes and data width

An index can cover a query if it contains all columns needed to filter, join, sort, and return results. In that case, Oracle can avoid table access by rowid.

For example, the query:

```sql
SELECT order_id,
       order_date
FROM orders
WHERE customer_id = :p_customer_id;
```

can be satisfied by an index starting with `CUSTOMER_ID` and containing `ORDER_ID` and `ORDER_DATE` in a suitable structure. However, do not add every column to an index just to cover one query. Wider indexes increase storage, DML overhead, redo/undo, and maintenance cost.

Balance the columns a query needs against index maintenance cost. Creating an index is a separate design decision; projection pruning does not mean creating an index for every SELECT.

## 5. Reducing data before GROUP BY and aggregation

Aggregation typically must process all rows within the grouping scope. If rows can be filtered before grouping, the number of rows to aggregate drops.

Example:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
GROUP BY customer_id;
```

The `WHERE` conditions eliminate irrelevant rows before aggregation processes them. If predicates are applied at table access, hash group by or sort group by receives fewer rows.

### 5.1. WHERE and HAVING serve different roles

`WHERE` filters input rows before grouping. `HAVING` filters groups after aggregates have been calculated.

Example:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(total_amount) > 100000;
```

`ORDER_STATUS = 'PAID'` is a row-level condition, so it belongs in `WHERE`. `SUM(TOTAL_AMOUNT) > 100000` depends on the aggregate result, so it belongs in `HAVING`.

You cannot convert every `HAVING` condition into `WHERE`. For instance, `HAVING SUM(total_amount) > 100000` is not equivalent to filtering individual orders with `TOTAL_AMOUNT > 100000`.

### 5.2. Pre-aggregation before joining

If a very large detail table must be joined with another table, yet only key-level aggregates are needed, you can aggregate first and then join the smaller result.

For example, needing total amount by customer alongside customer name:

```sql
WITH order_totals AS (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE order_status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.customer_name,
       ot.total_amount
FROM order_totals ot
JOIN customers c
  ON c.customer_id = ot.customer_id;
```

If `ORDERS` has millions of rows while there are far fewer customers, pre-aggregation can reduce the rows entering the join. However, Oracle can also perform group-by placement or similar query transformations automatically. A CTE by itself does not guarantee materialization.

### 5.3. Preserving semantics during pre-aggregation

Pre-aggregation is only valid if it preserves relationships between data and calculations. Be cautious when:

- Joins have one-to-many or many-to-many relationships that duplicate rows.
- Aggregates depend on columns from the joined table.
- Outer joins exist and unmatched groups must be preserved.
- `COUNT(DISTINCT ...)`, analytic functions, or `HAVING` conditions are present.
- Data contains NULLs and aggregates have rules for ignoring NULLs.

For example, if a customer has multiple rows in an addresses table, joining `CUSTOMERS` with `ADDRESSES` before summing orders can duplicate order amounts. Aggregating orders by customer first and then joining addresses may be right if the report wants totals per customer, but wrong if the goal is totals per address where each order must be allocated by a specific rule.

Do not rewrite solely to reduce cardinality without checking multiplicity and NULL semantics. Optimizations must preserve results.

## 6. Reducing data before SORT and TOP-N

Sorting can consume CPU, memory, and TEMP. If a query only needs the first N rows in a defined order, express the row limit clearly so Oracle has an opportunity to use top-N optimization or stopkey.

Example retrieving the 20 newest orders:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Oracle 12c and later support the `FETCH FIRST` row limiting clause. Whether execution can stop early depends on the access path and required ordering. If a suitable index starts with `CUSTOMER_ID` and follows with date/ID order, Oracle may scan part of the index and stop after 20 rows. Without an order-providing access path, it may still read many rows and use a top-N sort.

### 6.1. ORDER BY must define a deterministic order

If multiple rows share the same `ORDER_DATE`, a query with only `ORDER BY ORDER_DATE DESC` does not uniquely determine which row comes first among ties. Adding a tie-breaker key like `ORDER_ID` makes pagination/top-N results stable:

```sql
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Do not drop `ORDER BY` just to make a query faster if the business logic requires ordering. Without `ORDER BY`, Oracle makes no guarantee about result order.

### 6.2. OFFSET pagination and keyset pagination

Paginating with OFFSET:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
OFFSET 10000 ROWS FETCH NEXT 20 ROWS ONLY;
```

Oracle may have to walk through or discard many rows before returning page 501. The larger the OFFSET, the larger the volume of rows that may need to be processed.

If the UI can send the key of the last row from the prior page, keyset pagination is typically more efficient:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND (
        order_date < :p_last_order_date
        OR (
            order_date = :p_last_order_date
            AND order_id < :p_last_order_id
        )
      )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

With a suitable index, the query can seek directly to the position after the previous page's last key instead of skipping a large number of rows. The predicate must match the sort order completely and handle NULLs according to clear rules. When data changes between page fetches, keyset pagination also avoids several page-shift anomalies of OFFSET.

### 6.3. Do not limit rows before sorting

The following pattern does not mean getting the 20 newest rows:

```sql
SELECT *
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = :p_customer_id
    FETCH FIRST 20 ROWS ONLY
)
ORDER BY order_date DESC;
```

It limits to 20 rows first and then sorts those 20 rows. Without ordering inside the subquery, the 20 chosen rows are arbitrary and may not be the 20 newest. Put `ORDER BY` together with the row limiting clause in the right query block:

```sql
SELECT order_id,
       order_date
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

## 7. Reducing data before analytic/window functions

Analytic functions such as `ROW_NUMBER`, `RANK`, and `SUM(...) OVER (...)` generally need to inspect many rows within a partition and may require sorting by partition/order keys. Therefore, filtering to the proper data scope before analytic functions can cut cost substantially.

Example retrieving the newest paid order for each customer:

```sql
SELECT customer_id,
       order_id,
       order_date,
       total_amount
FROM (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           o.total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
)
WHERE rn = 1;
```

The status and date conditions filter rows before `ROW_NUMBER` is evaluated. The predicate `rn = 1` must be applied after the analytic function determines rank; moving it into the inner level before the analytic function alters the meaning.

### 7.1. Which predicates can be pushed past analytic functions?

Predicates on columns not participating in partitioning/ordering or that do not alter the candidate row set for ranking may be pushed down in some cases. However, predicates that restrict the rows inside a partition can change rankings, so they cannot be moved arbitrarily.

For example, if the goal is the newest order among paid orders, filtering `ORDER_STATUS = 'PAID'` before `ROW_NUMBER` is right. If the goal is identifying the overall newest order and returning it only if it is paid, filtering status after the analytic function is right. The two SQL statements have different meanings.

## 8. Partition pruning: avoiding unnecessary partition reads

If a table is partitioned by day or month, a predicate on the partition key allows Oracle to read only relevant partitions. This reduces both rows and blocks right at the data source.

Example `SALES` table partitioned by `SALE_DATE`:

```sql
SELECT sale_id,
       customer_id,
       amount
FROM sales
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01';
```

If the partition key and predicate are compatible, Oracle can access only October's partition. The plan may show `PARTITION RANGE SINGLE`, `PARTITION RANGE ITERATOR`, or other partition operations.

Avoid wrapping the partition key in a function when unnecessary:

```sql
-- Can make partition pruning harder in some cases.
WHERE TO_CHAR(sale_date, 'YYYYMM') = '202610'
```

Writing a date range is usually clearer and easier to prune:

```sql
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01'
```

With dynamic partition pruning, the plan may show `KEY` in `PSTART`/`PSTOP`; the range is resolved at runtime from binds or runtime values. Inspect the plan and runtime stats rather than looking only for fixed partition numbers.

## 9. Reducing data before exchange in parallel or distributed queries

Parallel execution and distributed queries may have to ship data between processes or databases. The larger the row count and row width, the higher the exchange cost.

In parallel plans, `PX SEND` and `PX RECEIVE` operations represent data distribution. Filtering and projecting before `PX SEND` reduces the data volume transferred between processes.

For queries across a database link, predicate pushdown can allow the remote database to filter data before sending it to the local database. Example:

```sql
SELECT order_id,
       total_amount
FROM remote_orders@reporting_link
WHERE order_status = 'PAID'
  AND order_date >= :p_from_date;
```

If the predicate executes at the remote site, only necessary rows cross the network. If the local database pulls all data before filtering, network cost can be huge.

Inspect remote operation details and query plans as permitted by your environment. When necessary, check plans on both local and remote databases. Do not assume every predicate or function is pushed across a database link; pushdown capability depends on SQL, data types, functions, release, and configuration.

## 10. CTEs, inline views, and materialization

CTEs (`WITH`) and inline views help organize SQL into readable query blocks. They do not by themselves guarantee intermediate data is computed once or stored in a temporary table.

Example:

```sql
WITH paid_orders AS (
    SELECT order_id,
           customer_id,
           total_amount
    FROM orders
    WHERE order_status = 'PAID'
)
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM paid_orders
GROUP BY customer_id;
```

The optimizer can merge the `PAID_ORDERS` query block into the outer query, push predicates, or perform other transformations. Depending on the case, Oracle may also materialize intermediate results. Check the plan to see the actual operation.

Do not apply `MATERIALIZE` or `INLINE` hints mechanically. Hints affect how query blocks are handled, but do not replace identifying the root cost. Consider how many times the CTE is referenced, intermediate data size, TEMP usage, and predicate pushdown opportunities.

## 11. Combined example: filter and project before joining, aggregate afterward

Suppose a report needs total revenue by region for paid orders in Q4. The `ORDERS` table is huge, `ORDER_ITEMS` is even larger, and `CUSTOMERS` holds many profile columns unneeded for the report.

A query with clear data scope:

```sql
WITH order_totals AS (
    SELECT o.order_id,
           o.customer_id,
           SUM(oi.quantity * oi.unit_price) AS order_amount
    FROM orders o
    JOIN order_items oi
      ON oi.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-10-01'
      AND o.order_date <  DATE '2027-01-01'
    GROUP BY o.order_id,
             o.customer_id
)
SELECT c.region_id,
       SUM(ot.order_amount) AS total_revenue
FROM order_totals ot
JOIN customers c
  ON c.customer_id = ot.customer_id
GROUP BY c.region_id;
```

Key points:

1. Status and date predicates are placed directly on `ORDERS`, allowing the optimizer to filter near the data source.
2. Joins only need `ORDER_ID` to combine `ORDERS` with `ORDER_ITEMS` and `CUSTOMER_ID` to combine with `CUSTOMERS`.
3. Only columns required for joins and calculations are retained; no `SELECT *`.
4. Detail data is aggregated per order before joining with the customers table.
5. After joining, results are aggregated by region.

This is a query structure that clarifies intent. The optimizer may transform query blocks or pick another execution order. Confirm that pre-aggregating by order before joining does not alter results if the data has one-to-many relationships or special allocation rules.

## 12. Verifying with execution plans and runtime statistics

You cannot conclude a rewrite is better just by counting SQL lines or seeing shorter syntax. Measure plans before and after using representative data and bind values.

You can instruct Oracle to collect row-source statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-10-01'
  AND o.order_date <  DATE '2026-11-01';
```

After running in the same session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +PARTITION'
    )
);
```

Metrics to compare:

| Field | Question |
|---|---|
| `E-Rows` | How many rows did the optimizer predict at each operation? |
| `A-Rows` | How many rows did the operation actually return? |
| `Starts` | How many times was the operation started? |
| `Buffers` | How many logical reads were used? |
| `Reads` | How many physical reads were recorded? |
| `A-Time` | Which operation accounts for the actual execution time? |
| `Bytes` | Is the estimated data width abnormally large? |
| `PSTART` / `PSTOP` | Were only the required partitions pruned and read? |
| TEMP/workarea | Did the sort or hash spill to TEMP? |

### 12.1. Finding where data grows or shrinks

Read actual rows from leaf operations upward:

- If table access returns too many rows, check whether predicates are applied early and whether the access path is suitable.
- If a join produces more rows than expected, check multiplicity, join conditions, and cardinality estimates.
- If aggregation receives very many rows, check whether filtering earlier or key-level pre-aggregation preserves semantics.
- If a sort receives many rows or overly wide rows, check whether data can be trimmed before sorting or whether an ordered access path can be used.
- If the inner branch of nested loops has a huge `Starts` count, check outer row counts and per-lookup cost.

### 12.2. Do not look only at final A-Rows

A query might return 20 rows yet still scan millions of rows and sort a huge set before limiting results. Therefore, `A-Rows` at the root node is insufficient to conclude a query is efficient.

Inspect intermediate operations, `Starts`, `Buffers`, `A-Time`, and predicates. An operation with many actual rows but low time may not be the bottleneck; an operation with few rows per call that executes hundreds of thousands of times can create high cost.

## 13. Rewrites requiring extra care

Reducing rows and columns is a good objective, but a non-equivalent rewrite can return wrong results. Watch out for:

- **Outer joins:** moving predicates between `WHERE` and `ON` can change retention of unmatched rows.
- **Aggregation:** shifting predicates between `WHERE` and `HAVING` can alter the rows being aggregated.
- **Analytic functions:** filtering before versus after `ROW_NUMBER`/`RANK` can produce different rankings.
- **DISTINCT:** adding or removing `DISTINCT` can change results and add sort/hash cost.
- **UNION and UNION ALL:** `UNION` deduplicates, whereas `UNION ALL` retains duplicates.
- **NULLs:** `NOT IN`, `NOT EXISTS`, comparisons, and OR conditions can behave differently with NULLs.
- **Join multiplicity:** pre-aggregating before a join is valid only when calculations and table relationships are preserved.
- **Top-N:** limiting rows before sorting is not equivalent to taking the top N rows after sorting.
- **Data type/time zone:** date range rewrites must preserve exact data types and time rules.

Test results against datasets with edge cases: no matching rows, many matching rows, NULLs, duplicates, boundary timestamps, and one-to-many relationships.

## 14. Practices that commonly cause waste

| Practice | Potential cost | How to evaluate |
|---|---|---|
| `SELECT *` | Large row width, increased network and workarea usage | Select only needed columns |
| Filtering with functions on columns | Index/partition pruning harder to leverage | Write range predicates or consider function-based indexes |
| Joining detail tables then `DISTINCT` | Generates many intermediate rows then deduplicates | Use `EXISTS` if only checking existence |
| Aggregating after many-to-many join | Data multiplied, large aggregation | Identify multiplicity and pre-aggregate when equivalent |
| Very large OFFSET | Must traverse many skipped rows | Consider keyset pagination |
| Sorting everything before limiting | Large sort and possible TEMP usage | Use semantically valid top-N and order-supporting access paths |
| Fetching LOBs in unneeded column lists | Increases I/O, memory, and network | Separate metadata queries from large payload queries |
| Pulling all data across a DB link | Heavy network traffic | Check predicate/projection pushdown |
| Using CTEs assuming they always materialize | May misunderstand intermediate cost | Inspect query transformations and actual plan |
| Forcing hints before understanding cardinality | Can mask root causes and destabilize plans | Measure estimates/actuals and check statistics first |

## 15. Sequential tuning process

When a query processes too much data, investigate in order:

1. **Define required output:** list the exact columns, rows, and order the application needs.
2. **Tag predicates:** separate row-filter predicates from join predicates.
3. **Filter near the source:** ensure predicates can be applied at table/index/partition access when semantics allow.
4. **Reduce row width:** strip unneeded columns from SELECT, subqueries, and intermediate branches.
5. **Check join multiplicity:** identify one-to-one, one-to-many, or many-to-many relationships; use EXISTS if only existence is needed.
6. **Evaluate aggregation:** filter before group by and consider pre-aggregation when result-preserving.
7. **Evaluate sort/top-N:** apply row limiting with proper ordering and consider keyset pagination for deep pages.
8. **Check partitions/network:** verify pruning and pushdown before data-exchange steps.
9. **Measure the execution plan:** compare E-Rows, A-Rows, Starts, Buffers, A-Time, and TEMP.
10. **Verify correctness:** compare outputs of old and new queries on representative data, including NULLs and edge cases.

## 16. Checklist for reviewing an expensive query

| Area | Question to answer |
|---|---|
| Output | Is it fetching more rows than the application actually needs? |
| Projection | Are any unused columns still being SELECTed or carried through branches? |
| Predicate | Are filter predicates applied close to the data source? |
| Sargability | Are functions or implicit conversions on columns reducing index usability? |
| Partition | Do predicates enable partition pruning? |
| Join | Are intermediate rows multiplying due to join multiplicity? |
| Existence | Can EXISTS/NOT EXISTS replace a join followed by deduplication? |
| Aggregation | Can rows be filtered earlier or safely pre-aggregated? |
| Sort | Is it sorting a wider or larger dataset than necessary? |
| Top-N | Are rows limited after proper ordering and able to stop early? |
| Analytic | Are predicates placed accurately before/after analytic functions per semantics? |
| Network | Are too many rows or columns being sent over PX/database links? |
| Runtime | Where do actual rows, starts, buffers, and timing show the bottleneck? |
| Correctness | Does the rewrite preserve NULLs, duplicates, outer joins, and ordering? |

Reducing rows and columns before expensive operations lowers the data volume Oracle must read, join, sort, aggregate, and transmit. The most effective approach starts with understanding the required output, placing predicates properly, keeping projections lean, and verifying the actual execution plan. Every rewrite must be confirmed for both result correctness and runtime statistics to ensure the query is faster while still returning the right data.
