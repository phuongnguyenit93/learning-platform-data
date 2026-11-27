# Syntax Limitations, Sorting Costs, and Result Verification

Window functions compute rankings, running totals, moving averages, and values from preceding or following rows while preserving individual detail rows. However, queries using window functions carry specific syntax limitations and can incur significant sorting and intermediate buffering costs.

When using window functions in MySQL, you must answer three questions:

1. Where in a SELECT statement are window functions permitted, and what limitations apply?
2. How many rows must MySQL partition, sort, and process to evaluate the windows?
3. How do you prove results are correct in the presence of duplicate values, NULLs, frame boundaries, or tied rows?

This article focuses on MySQL 8.0 and higher. Specific capabilities and optimizer planning can vary across releases; always check the exact version you are running.

## 1. Tables used in examples

The examples use the following order tables:

~~~sql
CREATE TABLE sales_orders (
    order_id    BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at  DATETIME NOT NULL,
    status      VARCHAR(20) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id      BIGINT UNSIGNED NOT NULL,
    product_id    BIGINT UNSIGNED NOT NULL,
    quantity      INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_order_items_sales_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(order_id)
) ENGINE = InnoDB;

~~~

Load a small dataset with two customers and some orders sharing timestamps:

~~~sql
INSERT INTO sales_orders
    (order_id, customer_id, created_at, status, total)
VALUES
    (101, 1, '2026-01-01 09:00:00', 'PAID', 100.00),
    (102, 1, '2026-01-01 09:00:00', 'PAID',  50.00),
    (103, 1, '2026-01-02 10:00:00', 'PAID', 200.00),
    (201, 2, '2026-01-01 08:00:00', 'PAID',  80.00),
    (202, 2, '2026-01-03 11:00:00', 'PENDING', 120.00);

INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (101, 1, 1),
    (101, 2, 2),
    (102, 1, 1),
    (103, 3, 1),
    (201, 1, 2);
~~~

Orders 101 and 102 share the same `customer_id` and `created_at`. This is a key test case for checking deterministic ordering, peer rows, and `RANGE` vs. `ROWS` frames.

## 2. At which stage of SELECT are window functions evaluated?

One way to visualize the logical processing order of a SELECT statement:

~~~text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY
     |
     v
HAVING
     |
     v
WINDOW FUNCTIONS
     |
     v
SELECT result
     |
     v
ORDER BY
     |
     v
LIMIT
~~~

This order describes query semantics to determine which data enters the window. It does not claim that MySQL physically executes every step in strict sequence; the optimizer may transform the plan as long as SQL semantics remain preserved.

Window functions see the row set remaining after FROM, JOIN, WHERE, GROUP BY, and HAVING. They then compute values for each row in that set. Therefore:

- WHERE filters rows before window functions are evaluated.
- GROUP BY can change the granularity of the dataset before windows are computed.
- HAVING filters groups before windows are computed within the same query block.
- The final query ORDER BY sorts returned output; ORDER BY inside OVER defines the order used for window calculation.
- The final query LIMIT caps results after window functions have been evaluated over the query's row set.

## 3. Places where window functions cannot be used directly

In MySQL, window functions are allowed in the SELECT list and ORDER BY of the corresponding query. You cannot place a window function directly in WHERE, GROUP BY, or HAVING of the same SELECT level.

### 3.1. Cannot filter directly by ROW_NUMBER in WHERE

The following example is invalid:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders
WHERE row_num <= 2;
~~~

There are two issues: the alias `row_num` does not yet exist at the WHERE stage, and window functions are disallowed directly in WHERE of the same query block.

Compute the window value in an inner query and filter in an outer query:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        total,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS row_num
    FROM sales_orders
)
SELECT order_id, customer_id, created_at, total, row_num
FROM ranked_orders
WHERE row_num <= 2
ORDER BY customer_id, row_num;
~~~

The inner query computes `row_num` for all qualifying orders. The outer query then filters to the first two rows per customer.

### 3.2. Cannot use window functions in same-level GROUP BY or HAVING

You cannot write `GROUP BY` on a `ROW_NUMBER() OVER (...)` expression, or use a condition such as `HAVING RANK() OVER (...) <= 3` directly.

If you need to group or filter by window results, put the window calculation in a CTE or derived table and query it from an outer layer:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        total,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total DESC
        ) AS value_rank
    FROM sales_orders
)
SELECT customer_id, order_id, total, value_rank
FROM ranked
WHERE value_rank <= 3;
~~~

### 3.3. Cannot nest a window function directly inside another window function

Do not pass one window function as a direct argument to another window function within the same expression. If the second calculation depends on the first window's output, split them into two query layers:

~~~sql
WITH first_pass AS (
    SELECT
        order_id,
        customer_id,
        total,
        SUM(total) OVER (
            PARTITION BY customer_id
        ) AS customer_total
    FROM sales_orders
)
SELECT
    order_id,
    customer_id,
    total,
    customer_total,
    RANK() OVER (
        ORDER BY customer_total DESC
    ) AS customer_rank
FROM first_pass;
~~~

The `first_pass` CTE creates the `customer_total` column. The outer SELECT level can then use that column as input to RANK.

## 4. Syntax limitations to remember in MySQL

### 4.1. DISTINCT is not supported inside window aggregates

MySQL does not support `COUNT(DISTINCT expression) OVER (...)`. The following example is invalid:

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) OVER (
        PARTITION BY customer_id
    ) AS distinct_status_count
FROM sales_orders;
~~~

If you need to count distinct statuses per customer, compute it at the GROUP BY level:

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) AS distinct_status_count
FROM sales_orders
GROUP BY customer_id;
~~~

If you need to attach that result back to every row, compute it separately and JOIN:

~~~sql
WITH customer_status_counts AS (
    SELECT
        customer_id,
        COUNT(DISTINCT status) AS distinct_status_count
    FROM sales_orders
    GROUP BY customer_id
)
SELECT
    s.order_id,
    s.customer_id,
    s.status,
    c.distinct_status_count
FROM sales_orders AS s
JOIN customer_status_counts AS c
    ON c.customer_id = s.customer_id;
~~~

### 4.2. Frames support ROWS and RANGE

MySQL supports two main frame units:

- ROWS defines the frame by physical row count before or after the current row in window order.
- RANGE defines the frame by the value of the ORDER BY expression and includes peer rows sharing the same sort value at the corresponding boundary.

Do not confuse these two units. When two orders share the same `created_at`, a RANGE frame ending at CURRENT ROW includes both same-timestamp orders; a ROWS frame includes only rows up to the current position.

MySQL does not support GROUPS frames. When designing frames, pick ROWS or RANGE according to exact business semantics.

### 4.3. Not every function uses frames the same way

Aggregate functions used with OVER—such as SUM, AVG, COUNT, MIN, and MAX—can be affected by frames. FIRST_VALUE, LAST_VALUE, and NTH_VALUE also operate with frames.

Functions like ROW_NUMBER, RANK, DENSE_RANK, LAG, and LEAD follow their own rules and do not use frames the way aggregates do. Do not add a frame clause assuming it will alter all window function types.

### 4.4. Do not omit required ordering

Some functions require ORDER BY to have deterministic meaning. ROW_NUMBER without ORDER BY still assigns numbers, but the row ordering is nondeterministic. Never rely on that arbitrary order as a business rule.

If multiple rows share the same sort value, add a unique key as a tie-breaker when deterministic ordering is needed:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
~~~

Here `order_id` is the primary key, distinguishing rows that share the same `created_at`.

## 5. ORDER BY inside OVER vs. final query ORDER BY

ORDER BY inside OVER defines the order used to evaluate window functions. It does not guarantee rows will be returned in that order.

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders;
~~~

`row_num` is computed by `created_at` and `order_id` within each customer, yet final row order in the output is not guaranteed without an outer ORDER BY.

If the UI requires displaying rows by customer and numbered order, write:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Do not rely on physical clustered index order, index scan order, or the order observed in a previous run.

## 6. Understanding PARTITION, ORDER, and frames properly

A window specification can include:

~~~sql
OVER (
    PARTITION BY expression_list
    ORDER BY expression_list
    frame_clause
)
~~~

- PARTITION BY divides the input set into independent groups. Window functions are evaluated separately per group.
- ORDER BY defines row ordering within each partition for order-dependent functions.
- Frame restricts the subset of rows used to compute frame-supporting functions.

Without PARTITION BY, the entire input set belongs to a single partition. Without ORDER BY, ranking or positional functions have no deterministic business ordering.

### 6.1. Default frames can produce unexpected results

For a window aggregate with ORDER BY and no explicit frame, MySQL's default frame is RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW. RANGE includes all peer rows that share the current row's ORDER BY value.

Example:

~~~sql
SELECT
    order_id,
    created_at,
    total,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1
ORDER BY created_at, order_id;
~~~

Orders 101 and 102 share `created_at` and are peer rows. With the default RANGE frame, the running total on both rows evaluates to 150.00 because the frame includes both rows sharing the ORDER BY value.

If row-by-row accumulation is required, use ROWS and add a tie-breaker:

~~~sql
SELECT
    order_id,
    created_at,
    total,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1
ORDER BY created_at, order_id;
~~~

Expected output for customer 1:

| order_id | total | running_total |
|---:|---:|---:|
| 101 | 100.00 | 100.00 |
| 102 | 50.00 | 150.00 |
| 103 | 200.00 | 350.00 |

This is a difference in frame semantics, not a MySQL calculation bug.

### 6.2. Sliding frames

Average of the three most recent orders by creation order:

~~~sql
SELECT
    customer_id,
    order_id,
    created_at,
    total,
    AVG(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

The frame contains at most three rows: the current row and two preceding rows in the same partition. At the start of a partition, the frame contains only the available rows; it does not synthesize dummy rows to reach three elements.

### 6.3. LAST_VALUE and frames

LAST_VALUE returns the value from the last row of the current frame, not automatically the last row of the entire partition.

The following example returns the current row's value:

~~~sql
SELECT
    customer_id,
    order_id,
    total,
    LAST_VALUE(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS last_value_in_frame
FROM sales_orders;
~~~

If the goal is to retrieve the value at the last row of the entire partition in the chosen order, declare the full frame:

~~~sql
SELECT
    customer_id,
    order_id,
    total,
    LAST_VALUE(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_total
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

A full-partition frame lets LAST_VALUE see through to the final row, even when evaluating rows at the start of the partition.

## 7. Sorting and partitioning costs

Window functions are more than simple per-row operations. To compute them properly, MySQL may have to:

1. Read the input row set after filter predicates and joins.
2. Group rows according to PARTITION BY.
3. Sort rows according to the window's ORDER BY.
4. Maintain state or intermediate row buffers to evaluate frames.
5. Return rows in the order requested by the outer query.

Sorting is a major source of cost. When the input set is large, has many partitions, or contains wide rows, sorting and buffering intermediate data can consume considerable CPU, memory, and I/O.

### 7.1. Input size directly drives cost

Compare:

~~~sql
SELECT
    order_id,
    customer_id,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders;
~~~

against a filtered query:

~~~sql
SELECT
    order_id,
    customer_id,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

The second query evaluates the window over the filtered set of orders. However, that also changes the meaning: the running total sums only PAID orders in January, not all historical orders for each customer. Only push predicates ahead of the window when doing so matches business requirements.

### 7.2. Partition count and partition size

PARTITION BY customer_id creates an independent window per customer. If a single customer has millions of orders, that customer's partition remains huge even if total partition count is high.

Partition size matters because rows inside a partition must be ordered by window order. A handful of skewed mega-partitions can introduce substantial cost and latency.

Inspect data skew:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM sales_orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 20;
~~~

This query helps spot the largest partitions. If your workload includes unusually large customers, benchmark that edge case specifically instead of testing only average-sized customers.

### 7.3. Multiple window specifications may require multiple sorts

Two windows with different orderings may require separate sort orders:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS chronological_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS amount_rank
FROM sales_orders;
~~~

The first window sorts by `created_at, order_id`; the second sorts by `total DESC`. MySQL may need to satisfy different ordering requirements and perform extra sorting work.

When multiple functions share the exact same window specification, declaring a named window expresses that shared definition:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER w AS row_no,
    SUM(total) OVER w AS running_total,
    AVG(total) OVER w AS running_average
FROM sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Named windows avoid duplicating definitions and reduce the risk of functions accidentally using mismatched orderings or frames. Whether the optimizer shares sorts or intermediate buffers in a given plan must be confirmed with EXPLAIN; never assume all windows are automatically merged.

### 7.4. Final query sorting can be a separate step

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_no
FROM sales_orders
ORDER BY total DESC;
~~~

The window requires ordering by `customer_id, created_at, order_id`; the final output requests sorting by `total DESC`. Because the two orders differ, MySQL may need an extra final sort step.

If final output should match the window's order, specify the corresponding outer ORDER BY. Even then, read the execution plan to verify whether the server reuses the order or performs another sort.

## 8. How can indexes help window functions?

An index aligned with filter, partition, and window order columns can reduce read volume or supply useful ordering for certain plans.

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1;
~~~

Index:

~~~sql
CREATE INDEX idx_sales_customer_time
ON sales_orders (customer_id, created_at, order_id);
~~~

has a column order matching filtering by `customer_id` and reading orders by `created_at, order_id`. This structure is worth testing for this query.

However, there is no guarantee an index eliminates all sorting or all window function overhead. Index utilization depends on predicates, column order, sort direction, selected columns, partition counts, and optimizer version.

Design guidelines:

- Place equality filter columns first.
- Follow with PARTITION BY columns.
- Follow with ORDER BY columns in exact order.
- Add covering columns only when read savings outweigh index size overhead.
- Measure plans before and after adding the index.

Do not create a dedicated index for every window. Indexes consume storage and slow down writes, and they may not help if the query sorts on expressions or mismatched directions.

## 9. Reducing row count and row width before window evaluation

If only a few columns are needed, avoid carrying large unnecessary columns through intermediate stages:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders;
~~~

Select only the columns required for output and window calculations. If a table has JSON or large text columns, omit them from the query unless needed.

You can use a CTE or derived table to filter and project columns prior to the window, provided row sets and semantics remain unchanged. A CTE without window functions may be merged or materialized by the optimizer depending on structure and version. A derived table or CTE containing window functions in MySQL must be materialized, which can require memory or temporary disk space.

If you need windows over full history and then display only a small slice, filter in the outer query:

~~~sql
WITH numbered AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS row_no
    FROM sales_orders
)
SELECT order_id, customer_id, created_at, row_no
FROM numbered
WHERE row_no BETWEEN 10 AND 20;
~~~

Moving a row-limiting condition into the CTE would renumber `row_no` over a smaller set and alter the results. Always distinguish pre-window filtering from post-window filtering.

## 10. Reading plans with EXPLAIN

Start with EXPLAIN:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

Depending on MySQL version and EXPLAIN format, details on windowing, sorts, temporary tables, access paths, and estimated rows appear at varying granularity. You can also run:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

And on supported versions:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

EXPLAIN ANALYZE actually executes the SELECT statement and reports real iterator metrics. This feature is available in MySQL 8.0.18+. Run it only in an appropriate environment after assessing query load.

When reading plans, examine:

1. Source table access path and chosen index.
2. Estimated rows vs. actual rows.
3. Sort steps serving PARTITION BY and ORDER BY.
4. Final query sort step if outer ORDER BY differs from window order.
5. Temporary tables or materialization if present.
6. Iterator loop counts and timings in EXPLAIN ANALYZE.

Do not judge cost merely by seeing the keyword OVER. A window over a few hundred rows can be trivial; a window over tens of millions of rows with multiple sort orders can be very expensive.

## 11. Verifying correctness on a small dataset

Before benchmarking large datasets, build a small dataset whose results you can verify by hand. The dataset should include:

- Two or more partitions.
- Two rows with duplicate ORDER BY values.
- A single-row partition.
- Equal values to test RANK and DENSE_RANK.
- NULLs if business columns allow NULL.
- Rows at the start and end of frames.

With the dataset loaded at the start, verify the running total:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_no,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Expected output:

| order_id | customer_id | row_no | running_total |
|---:|---:|---:|---:|
| 101 | 1 | 1 | 100.00 |
| 102 | 1 | 2 | 150.00 |
| 103 | 1 | 3 | 350.00 |
| 201 | 2 | 1 | 80.00 |
| 202 | 2 | 2 | 200.00 |

If `order_id` were omitted from the window ORDER BY, rows 101 and 102 share the same `created_at` and have no deterministic relative order. The `ROWS`-based running total could then be assigned in an unstable order.

## 12. Verifying rankings and tie cases

ROW_NUMBER, RANK, and DENSE_RANK have distinct semantics when multiple rows share the same sort value.

~~~sql
SELECT
    order_id,
    customer_id,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC, order_id
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS dense_rank_no
FROM sales_orders
ORDER BY customer_id, total DESC, order_id;
~~~

- ROW_NUMBER assigns a distinct number to every row; `order_id` ensures deterministic order when `total` ties.
- RANK gives tied rows the same rank and leaves a gap before the next rank.
- DENSE_RANK gives tied rows the same rank without leaving a gap.

In the example, the two customers have distinct amounts. When testing `total` ties, intentionally insert two orders with equal `total` to observe the difference. Do not add a unique key to RANK's ORDER BY if equal totals should tie; add a tie-breaker only for ROW_NUMBER or for display ordering where appropriate.

## 13. Verifying running totals against group totals

A useful sanity check is comparing the final running total in each partition against a regular group sum over the same row set.

Group total per customer:

~~~sql
SELECT customer_id, SUM(total) AS grouped_total
FROM sales_orders
GROUP BY customer_id;
~~~

Final running total value:

~~~sql
WITH running AS (
    SELECT
        customer_id,
        order_id,
        SUM(total) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS reverse_row_no
    FROM sales_orders
)
SELECT customer_id, running_total AS window_total
FROM running
WHERE reverse_row_no = 1;
~~~

Both results must match for every `customer_id` when using the same rows, same filters, and non-NULL totals. If they differ, check:

- Are the WHERE clauses identical?
- Were rows multiplied by a JOIN before the window?
- Were rows excluded before window evaluation?
- Does PARTITION BY use the exact grouping key?
- Does ORDER BY have a stable tie-breaker?
- Does the frame cover the full partition at the last row?

This provides an independent cross-check between grouped aggregation and window aggregation.

## 14. Verifying when a JOIN precedes a window function

A common bug is a JOIN multiplying rows before window evaluation. For example, if one order has multiple line items, joining orders with `order_items` yields one row per line item. `SUM(o.total) OVER (...)` would then repeatedly sum the order total once per line item.

Example needing item counts per order while preserving per-customer order rankings:

~~~sql
WITH item_counts AS (
    SELECT
        order_id,
        COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
),
order_level AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.created_at,
        o.total,
        COALESCE(ic.item_count, 0) AS item_count
    FROM sales_orders AS o
    LEFT JOIN item_counts AS ic
        ON ic.order_id = o.order_id
)
SELECT
    order_id,
    customer_id,
    total,
    item_count,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC, order_id
    ) AS amount_position
FROM order_level;
~~~

The `item_counts` CTE aggregates line items down to one row per `order_id` before joining with the order level. `order_level` therefore preserves one row per order, and the window function does not double-count order totals.

When verifying, confirm the grain of the window's input data: does each row represent an order, a line item, or a JOIN combination? This is critical so SUM, COUNT, and ROW_NUMBER retain accurate meaning.

## 15. Verifying results after modifying a query

When optimizing a window function query, do not compare execution time alone. Verify that the rewritten query returns the exact same business results.

A practical verification workflow:

1. Save the original query and parameter set.
2. Record output row count and identifying keys.
3. Run the rewritten query against the same snapshot or static dataset.
4. Compare key sets, row counts, and computed values.
5. Check large partitions, tied rows, and frame boundaries specifically.
6. Benchmark execution plans and timings only after correctness is confirmed.

For two queries expected to return the exact same row set, you can use symmetric NOT EXISTS checks to detect key differences:

~~~sql
WITH old_result AS (
    SELECT order_id
    FROM sales_orders
    WHERE status = 'PAID'
),
new_result AS (
    SELECT order_id
    FROM sales_orders
    WHERE status = 'PAID'
      AND total >= 0
)
SELECT 'missing_from_new' AS difference_type, o.order_id
FROM old_result AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM new_result AS n
    WHERE n.order_id = o.order_id
)
UNION ALL
SELECT 'extra_in_new' AS difference_type, n.order_id
FROM new_result AS n
WHERE NOT EXISTS (
    SELECT 1
    FROM old_result AS o
    WHERE o.order_id = n.order_id
);
~~~

This example illustrates the key-comparison pattern; the new query condition is equivalent to the old one only if the data satisfies `total >= 0`. In real verification, substitute your old and new queries into the two CTEs. An empty result shows no missing or extra keys, though you must still compare computed value columns.

If output can contain duplicate keys or has no unique key, compare across the full business key or reconcile occurrence counts as well. Comparing with DISTINCT can hide row-multiplication bugs.

## 16. Common pitfalls

**"ORDER BY in OVER always sorts the final output."** False. It only defines window ordering. To sort final output, add an ORDER BY in the outer query.

**"ROW_NUMBER automatically produces a deterministic order."** False. If ORDER BY cannot distinguish rows, their relative order is undefined. Add a unique key as a tie-breaker when needed.

**"The default frame is always row by row."** False. With ORDER BY, an aggregate window's default frame is RANGE from UNBOUNDED PRECEDING to CURRENT ROW; peer rows can share the frame.

**"LAST_VALUE always fetches the last row of the partition."** False. It fetches the last row of the current frame. For the full partition, declare the frame up to UNBOUNDED FOLLOWING.

**"You can filter ROW_NUMBER in same-level WHERE."** False. Compute the window in a CTE or derived table and filter in the outer query.

**"Every window function uses a frame."** False. ROW_NUMBER, RANK, DENSE_RANK, LAG, and LEAD do not use frames the way aggregate windows do.

**"Adding an index guarantees eliminating sorts."** False. Indexes can assist certain access paths and orders; always check the actual execution plan.

**"A query with multiple OVER clauses always sorts only once."** False. Windows with different orderings may require multiple sort passes. Named windows share definitions, but plans must still be verified.

**"CTEs are always materialized."** False. A CTE without window functions may be merged or materialized depending on structure. A CTE/derived table containing window functions in MySQL must be materialized.

**"Making it faster is enough."** False. You must confirm identical results—especially with peer rows, NULLs, frames, and JOINs that can multiply rows.

## 17. Pre-release checklist for window queries

- [ ] Verified the exact input row set after WHERE, JOIN, GROUP BY, and HAVING.
- [ ] Window functions appear only in syntax positions supported by MySQL.
- [ ] No direct nesting of window functions or DISTINCT inside window aggregates.
- [ ] PARTITION BY accurately reflects business grouping.
- [ ] ORDER BY includes a tie-breaker when deterministic order is required.
- [ ] Frame is declared explicitly whenever results depend on ROWS vs. RANGE.
- [ ] Checked peer rows and values at the start/end of partitions.
- [ ] Outer query ORDER BY is declared if the UI expects specific output order.
- [ ] Checked whether any JOIN multiplies rows prior to window evaluation.
- [ ] Evaluated indexes for filters, partitions, and window ordering.
- [ ] Inspected EXPLAIN; used EXPLAIN ANALYZE where environment and version permit.
- [ ] Cross-checked results on a small hand-verifiable dataset.
- [ ] Reconciled key sets and computed values after optimization.
- [ ] Benchmarked with large partitions and production-representative data distribution.

## Conclusion

Window functions in MySQL have strict placement rules: compute in SELECT or ORDER BY, never filter directly in same-level WHERE, GROUP BY, or HAVING; never nest window functions directly; and note that DISTINCT inside window aggregates is unsupported. When filtering by window results is needed, use a CTE or derived table.

Execution cost primarily depends on input row count, partition sizes, sort orders, number of window specifications, and intermediate buffering. Suitable indexes can assist some plans, though they do not guarantee eliminating every sort. Inspect EXPLAIN, measure in realistic environments, and verify correctness on data containing peer rows, frame boundaries, NULLs, and JOINs. Following this approach ensures queries are both semantically accurate and explainably performant.
