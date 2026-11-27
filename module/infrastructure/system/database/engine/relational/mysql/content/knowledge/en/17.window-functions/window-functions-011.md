# Filtering Window Function Results via CTE or Derived Table

## Lesson objectives

After this lesson, you will be able to:

- Explain why window function results cannot be filtered directly in WHERE within the same SELECT.
- Wrap queries containing window functions in a CTE or derived table to filter in an outer query.
- Use ROW_NUMBER, RANK, and DENSE_RANK to retrieve top N per group.
- Distinguish filtering input data before window evaluation from filtering results after window evaluation.
- Filter by running totals, LAG, LEAD, and other window expressions.
- Choose the right ranking function according to tie-handling requirements.
- Inspect ordering, NULLs, partition scope, and performance with EXPLAIN.

Window functions compute a value based on related rows in a result set while still retaining each detail row. Common examples include numbering orders per customer, ranking employees within a department, computing running totals, and comparing values with the preceding row.

A frequent requirement is keeping only rows whose window function result satisfies a condition—for example, the three most recent orders per customer or employees in the top 10% of their department. MySQL does not allow placing window functions directly inside WHERE or HAVING of the same query block. The solution is to compute the window function in an inner query layer and filter the result in an outer layer using a CTE or derived table.

## 1. Why is an outer query layer required?

### 1.1. Window functions are evaluated after WHERE

A SELECT query can be conceptualized through the following general logical evaluation order:

1. FROM and JOIN assemble the input row set.
2. WHERE filters input rows.
3. GROUP BY and HAVING process groups.
4. Window functions compute results over the remaining rows.
5. SELECT constructs output columns.
6. DISTINCT, ORDER BY, and LIMIT finalize the returned result set.

This is a conceptual model for understanding clause scope; the optimizer may choose a different physical execution plan as long as SQL semantics remain preserved.

Window functions need to see the row set after prior filtering and grouping steps. Therefore, the following statement is invalid:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC
    ) AS row_num
FROM sales_order
WHERE row_num <= 3;
~~~

WHERE is evaluated before `row_num` is computed. The alias `row_num` does not yet exist when WHERE is evaluated. Writing the window expression directly inside WHERE is equally invalid:

~~~sql
SELECT
    order_id,
    customer_id
FROM sales_order
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC
) <= 3;
~~~

MySQL only allows window functions in the SELECT list and ORDER BY of the corresponding query block. They cannot be used directly in WHERE, GROUP BY, or HAVING of the same query block.

### 1.2. Compute inside, filter outside

Split the work into two layers:

- The inner layer reads the data and computes the window function.
- The outer layer reads the output with named window columns and filters using a standard WHERE clause.

You can use a CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    row_num
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

Or use a derived table:

~~~sql
SELECT
    ranked.order_id,
    ranked.customer_id,
    ranked.ordered_at,
    ranked.row_num
FROM (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
) AS ranked
WHERE ranked.row_num <= 3
ORDER BY ranked.customer_id, ranked.row_num;
~~~

Both express the same idea. A CTE names the intermediate step at the top of the statement; a derived table places the subquery directly inside FROM. The outer query can filter on `row_num` because at that point `row_num` is an ordinary column of `ranked_orders`.

### 1.3. MySQL does not support QUALIFY

Some database management systems provide a QUALIFY clause to filter window function results after evaluation. MySQL 8.4 does not support QUALIFY. When working with MySQL, use a CTE or derived table to create an outer filtering layer.

## 2. Preparing practice data

The examples use a simple orders table. Each row is an order; one customer can have multiple orders.

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_status_customer_date (
        order_status,
        customer_id,
        ordered_at,
        order_id
    )
) ENGINE = InnoDB;

INSERT INTO sales_order (
    order_id,
    customer_id,
    order_status,
    ordered_at,
    total_amount
)
VALUES
    (1001, 101, 'completed', '2026-01-05 09:15:00', 1250000.00),
    (1002, 101, 'completed', '2026-01-20 14:30:00', 5200000.00),
    (1003, 101, 'pending',   '2026-02-16 10:00:00',  890000.00),
    (1004, 101, 'completed', '2026-02-12 16:45:00', 1500000.00),
    (1005, 102, 'completed', '2026-01-10 08:20:00', 5200000.00),
    (1006, 102, 'completed', '2026-01-17 12:10:00', 3400000.00),
    (1007, 102, 'completed', '2026-02-03 13:00:00', 3400000.00),
    (1008, 103, 'cancelled', '2026-02-15 11:20:00', 2100000.00);
~~~

Inspect the data:

~~~sql
SELECT *
FROM sales_order
ORDER BY customer_id, ordered_at, order_id;
~~~

In this lesson:

- `customer_id` identifies the customer group.
- `ordered_at` records the order timestamp.
- `order_id` is a unique key serving as a tie-breaker when two orders share the same timestamp.
- `total_amount` is the order total, used in ranking examples.

The dataset includes two orders for customer 102 with the same value of 3,400,000 to illustrate the differences among ROW_NUMBER, RANK, and DENSE_RANK.

## 3. Filtering top N rows per group with ROW_NUMBER

### 3.1. Retrieving the three most recent orders per customer

ROW_NUMBER numbers each row in a partition according to the declared order. Each partition restarts at 1.

If ORDER BY is omitted from OVER, row numbering within a partition is nondeterministic. Whenever you need to select a specific row or a stable top N, declare a business order and add a unique tie-breaker.

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    row_num
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

Explanation:

- PARTITION BY customer_id groups orders by customer.
- ORDER BY ordered_at DESC puts the newest orders first.
- `order_id DESC` breaks ties deterministically when timestamps match.
- ROW_NUMBER numbers 1, 2, 3... within each customer.
- `WHERE row_num <= 3` keeps at most three rows per customer.

If a customer has only one or two orders, the result has only one or two rows. The condition `row_num <= 3` does not pad missing rows up to three.

### 3.2. Retrieving strictly one latest row per group

This pattern is commonly used to fetch the current record from a history table:

~~~sql
WITH latest_order AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    order_status,
    ordered_at
FROM latest_order
WHERE rn = 1
ORDER BY customer_id;
~~~

Each `customer_id` has at most one row in the result. If multiple orders share the same `ordered_at`, `order_id DESC` decides which row is picked.

Never omit the tie-breaker when business rules require a single deterministic result. If you only sort by `ordered_at` and two rows share a timestamp, their relative order is not guaranteed; which row receives `rn = 1` could shift across execution plans or data states.

### 3.3. Filtering with multiple conditions on window results

You can combine multiple conditions in the outer layer:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 2
  AND order_status = 'completed'
  AND total_amount >= 1000000
ORDER BY customer_id, rn;
~~~

In this query, `rn` is computed across all order statuses. Then the outer query keeps only the top two rows per customer and subsequently drops any rows that are not completed or have a low amount.

That means a customer may end up with fewer than two rows even if they have additional completed orders further back. If the intent is to get the two most recent completed orders, filter `order_status` inside the CTE before computing ROW_NUMBER. Section 7 examines this difference.

## 4. ROW_NUMBER, RANK, and DENSE_RANK when filtering top N

The three ranking functions behave differently when tied values occur.

| Function | Rule | Example ranks for values 100, 90, 90, 80 |
|---|---|---|
| ROW_NUMBER | Each row gets a distinct sequence number | 1, 2, 3, 4 |
| RANK | Equal rows share rank; subsequent ranks skip | 1, 2, 2, 4 |
| DENSE_RANK | Equal rows share rank; no ranks skipped | 1, 2, 2, 3 |

### 4.1. ROW_NUMBER: strict row count cap

If the requirement is "at most three orders per customer," use ROW_NUMBER:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

Each group has at most three rows. The tie-breaker `order_id DESC` picks specific rows when `total_amount` ties.

### 4.2. RANK: keeping all tied rows within the top N positions

If the requirement is "retrieve orders in the top three rank positions, keeping tied orders," use RANK:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE amount_rank <= 3
ORDER BY customer_id, amount_rank, order_id;
~~~

Do not add `order_id` to ORDER BY inside RANK if orders with the same `total_amount` should tie. Adding a unique column to ORDER BY gives each row a distinct rank because the full sort tuple is no longer equal.

When ties occur at the third position, more than three rows may be returned.

### 4.3. DENSE_RANK: retrieving the top N distinct value tiers

If the requirement is "retrieve the top three highest order amount tiers," use DENSE_RANK:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_level
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE amount_level <= 3
ORDER BY customer_id, amount_level, order_id;
~~~

For values 100, 90, 90, 80:

- `RANK <= 3` returns 100, 90, 90; value 80 has rank 4.
- `DENSE_RANK <= 3` returns all of 100, 90, 90, 80 because those represent three distinct value tiers.

Determine whether the business requirement caps row count, rank positions, or distinct value tiers before choosing a function.

## 5. Filtering results using a derived table

A CTE is not the only option. A derived table creates a query block inside FROM, supplying the same window columns to the outer query block.

Example retrieving the two most recent orders per customer:

~~~sql
SELECT
    ranked.order_id,
    ranked.customer_id,
    ranked.ordered_at,
    ranked.row_num
FROM (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
) AS ranked
WHERE ranked.row_num <= 2
ORDER BY ranked.customer_id, ranked.row_num;
~~~

The alias `ranked` is required for the derived table. The outer query references columns as `ranked.row_num`.

### 5.1. Choosing between a CTE and a derived table

| Scenario | Usually more readable option |
|---|---|
| Single simple window step used once | Derived table |
| Multiple intermediate steps or chained CTEs | CTE |
| Same result set referenced multiple times in the statement | CTE |
| Preferring to name logic at the top of the statement | CTE |
| Small subquery sitting right where it is used | Derived table |

Neither approach changes semantics when the same calculations and predicates are written. Pick whichever makes the query structure easiest to read, then measure performance on real data.

### 5.2. A CTE can be reused in multiple places

For example, rank orders once and then compute summary stats over that result set:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT
    customer_id,
    MAX(CASE WHEN rn = 1 THEN total_amount END) AS highest_order,
    COUNT(CASE WHEN rn <= 3 THEN 1 END) AS top_three_count
FROM ranked_orders
GROUP BY customer_id;
~~~

The CTE clarifies the ranking step. The outer query can use `rn` inside regular aggregate expressions because `rn` is now an output column of the CTE.

## 6. Filtering results of other window functions

Wrapping a query is not limited to ROW_NUMBER or RANK. Any window function result can be filtered in an outer query block.

### 6.1. Filtering by running total

Compute cumulative order value over time for each customer:

~~~sql
WITH running_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS running_total
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    running_total
FROM running_orders
WHERE running_total >= 5000000
ORDER BY customer_id, ordered_at, order_id;
~~~

The inner query calculates the running total. The outer query keeps only rows where the cumulative total has reached at least 5 million.

The frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` spans from the first row in the partition to the current row. Adding `order_id` as a tie-breaker ensures deterministic accumulation when `ordered_at` matches.

If you only wrote `ORDER BY ordered_at` and multiple orders shared a timestamp, the order among same-timestamp rows would be nondeterministic, and their row-by-row running totals could differ arbitrarily.

### 6.2. Filtering rows that changed relative to the previous row

LAG retrieves a value from the preceding row in window order. You can use it to find orders whose value increased compared to the prior order:

~~~sql
WITH order_changes AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
        ) AS previous_amount
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    previous_amount,
    total_amount - previous_amount AS amount_change
FROM order_changes
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount
ORDER BY customer_id, ordered_at, order_id;
~~~

The first row in each partition has no preceding row, so `previous_amount` is NULL. `previous_amount IS NOT NULL` excludes the first row from the comparison.

### 6.3. Filtering rows by next row values

LEAD reads values from the following row. For instance, finding orders whose subsequent order by the same customer had a larger amount:

~~~sql
WITH order_sequence AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        LEAD(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
        ) AS next_amount
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    total_amount,
    next_amount
FROM order_sequence
WHERE next_amount > total_amount
ORDER BY customer_id, ordered_at, order_id;
~~~

The last row of each partition has no following row, so `next_amount` is NULL and the comparison evaluates to unknown (false).

### 6.4. Filtering by ratio to group average

Example retrieving orders larger than that customer's own average:

~~~sql
WITH orders_with_average AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        AVG(total_amount) OVER (
            PARTITION BY customer_id
        ) AS customer_average
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    total_amount,
    customer_average
FROM orders_with_average
WHERE total_amount > customer_average
ORDER BY customer_id, total_amount DESC;
~~~

Window AVG retains every individual order while attaching the group's average. The outer query filters orders above the average.

If you used `GROUP BY customer_id` in the inner layer, the output would collapse to one row per customer and you could no longer retain individual orders for comparison.

## 7. Filtering before vs. after window evaluation

This is the most critical point when writing multi-layer queries. A predicate placed inside the CTE changes the row set seen by the window function. A predicate placed in the outer query only removes rows after the window has been evaluated.

### 7.1. Ranking only completed orders

Place the condition inside the CTE:

~~~sql
WITH ranked_completed_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT *
FROM ranked_completed_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Here, only completed orders participate in ROW_NUMBER. The result is the two most recent completed orders per customer.

### 7.2. Ranking all orders, then displaying only completed ones

Place the condition outside:

~~~sql
WITH ranked_all_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_all_orders
WHERE rn <= 2
  AND order_status = 'completed'
ORDER BY customer_id, rn;
~~~

Here, all statuses participate in ranking. Then only rows that are both in the top 2 overall and have `completed` status are returned.

The two queries can return different results. For customer 101, the newest pending order takes rank 1 when ranking all orders. Filtering status after ranking leaves only one completed order in the result.

### 7.3. Rule for deciding predicate placement

Before writing the query, ask:

- Does this condition define which rows participate in the window calculation? Place it in the inner query block, before the window.
- Does this condition only decide which rows to keep after the window has been calculated? Place it in the outer query block.
- If you push a condition from outside to inside, would ranks, running totals, LAG/LEAD, or group averages change?

Never push a predicate across a window boundary merely to reduce row count. Pushing filters can alter business results.

## 8. Combining multiple layers of windows and filtering

You can use one CTE to compute a window, and subsequent CTEs to filter or compute further over those results.

Example retrieving the two highest-value orders per customer, then computing each order's share of the top-2 total:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
),
top_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount
    FROM ranked_orders
    WHERE rn <= 2
),
top_order_shares AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
        ) AS top_total
    FROM top_orders
)
SELECT
    order_id,
    customer_id,
    total_amount,
    top_total,
    total_amount / NULLIF(top_total, 0) AS share_of_top
FROM top_order_shares
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

The three layers have distinct purposes:

1. `ranked_orders` ranks all orders within each customer.
2. `top_orders` filters to the top two orders.
3. `top_order_shares` sums only those two selected orders.

The window in the third layer sees only the filtered rows in `top_orders`. If SUM were computed in the same layer as the initial ROW_NUMBER, the total would cover all orders for that customer rather than only the top 2.

## 9. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Using a window function in WHERE of the same SELECT | MySQL raises a syntax/context error | Wrap in a CTE or derived table |
| Using a window alias in WHERE of the same query block | Alias does not exist at WHERE evaluation time | Filter the alias in an outer query block |
| Thinking HAVING can filter window functions | Window functions are disallowed in same-block HAVING | Use an outer query layer |
| Using ROW_NUMBER without a tie-breaker | Tied rows can swap positions | Add a unique column to ORDER BY |
| Using RANK while adding a unique key to ORDER BY | Rows no longer tie | Sort only by business criteria to preserve ties |
| Using RANK when strictly N rows are needed | May return more than N rows due to ties | Use ROW_NUMBER |
| Using DENSE_RANK when N positions are needed | Returns N distinct value tiers | Pick the function matching requirements |
| Placing a status filter in the wrong layer | Alters the row set entering the window | Decide whether the filter belongs before or after the window |
| Assuming ORDER BY in OVER sorts final output | Return order remains unguaranteed | Add ORDER BY to the outer SELECT |
| Using LIMIT to get top N per group | LIMIT caps the entire result set | Use ROW_NUMBER/RANK and filter outside |
| Using SELECT * for large intermediate sets | Increases intermediate data volume | Select only required columns |
| Ignoring NULLs in sort columns | Results may not match intent | Specify explicit NULL placement rules in ORDER BY |

### 9.1. ORDER BY in OVER does not replace outer ORDER BY

Window ORDER BY defines calculation order inside partitions. It does not guarantee the final order of returned rows.

Always place ORDER BY in the outer query block when the UI, report, or API expects a specific order:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

### 9.2. LIMIT cannot replace top N per group

The following example retrieves only three rows across the entire table:

~~~sql
SELECT *
FROM sales_order
ORDER BY ordered_at DESC
LIMIT 3;
~~~

It does not retrieve three rows per `customer_id`. To limit per group, partition and number or rank each group using a window function.

### 9.3. Handling NULLs in ordering

In MySQL, when sorting ASC, NULLs come before non-NULL values; when sorting DESC, NULLs come after. If an explicit rule is needed, include a NULL-check expression in ORDER BY:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY
            (ordered_at IS NULL) ASC,
            ordered_at DESC,
            order_id DESC
    ) AS rn
FROM sales_order;
~~~

The expression `(ordered_at IS NULL) ASC` places rows with non-NULL timestamps first. Then `ordered_at DESC` puts the newest timestamps first, and `order_id DESC` breaks ties.

## 10. Performance and execution plans

Wrapping window functions in a CTE or derived table resolves syntax and scoping rules. It does not eliminate the cost of evaluating the window.

### 10.1. Partitioning and sorting costs

To compute ROW_NUMBER by customer and date, MySQL must process rows by `customer_id` partition and `ordered_at, order_id` order. On large datasets, sorting can consume significant time and memory.

An index with matching column order can assist data access:

~~~sql
CREATE INDEX idx_order_customer_date
ON sales_order (
    customer_id,
    ordered_at,
    order_id
);
~~~

This index matches many queries that filter or sort by `customer_id` then `ordered_at`. However, the optimizer may still require a sort depending on predicates, sort directions, window expressions, and the execution plan. Do not assume having an index guarantees eliminating sorts.

### 10.2. Filtering input early when semantically valid

If ranking only orders within a specific date range, filter that date range inside the CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
    WHERE ordered_at >= '2026-01-01'
      AND ordered_at <  '2026-04-01'
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

The window sees only orders within that date range. This differs from ranking the entire history and then filtering to rows whose `ordered_at` falls in that range. Choose based on business requirements.

### 10.3. Window functions in CTEs and materialization

In MySQL, a derived table or CTE containing a window function cannot be merged under optimization rules. MySQL must typically materialize the result of the query block containing the window function before the outer query filters it.

This can incur intermediate write/read overhead. Reduce rows and columns in the inner layer whenever doing so does not change window results.

An outer query block's WHERE predicates are also not pushed down through a query block containing a window function under MySQL 8.4 derived condition pushdown rules. Therefore, if you need to restrict data entering the window by customer, status, or time, verify whether the predicate belongs to the business input set and place it directly inside the inner query block from the start.

Never move an outer query predicate inside solely to reduce materialization if that predicate must be evaluated after ranking. Doing so alters the input partitions and can change ranks.

### 10.4. Using EXPLAIN

Inspect the plan:

~~~sql
EXPLAIN
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

Observe:

- How MySQL reads `sales_order` and which index is chosen.
- Estimated rows entering the window.
- Sort or materialization steps.
- Rows retained after `rn <= 3`.
- Whether an additional sort occurs in the outer query.

In MySQL 8.0.18 and later, you can use EXPLAIN ANALYZE to see actual timings and row counts for iterators:

~~~sql
EXPLAIN ANALYZE
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

EXPLAIN ANALYZE actually executes the SELECT statement. Avoid running it casually on heavy queries in production. Compare real data, row counts, timings, and resource usage before deciding to add indexes or rewrite queries.

## 11. Workflow for choosing a filtering pattern

You can follow this workflow when filtering window function results:

~~~mermaid
flowchart TD
    A[Write window function in SELECT] --> B{Need to filter by window result?}
    B -->|No| C[Use current query block]
    B -->|Yes| D[Choose CTE or derived table]
    D --> E[Place window in inner query block]
    E --> F[Alias the window result]
    F --> G[Place filter condition in outer query block]
    G --> H{Does condition need to filter window input?}
    H -->|Yes| I[Move condition into inner query block]
    H -->|No| J[Keep condition in outer query block]
    I --> K[Verify ties, NULLs, and ordering]
    J --> K
    K --> L[Run EXPLAIN and verify results]
~~~

Practical sequence:

1. Identify grouping via PARTITION BY.
2. Identify ordering or ranking criteria inside OVER.
3. Choose ROW_NUMBER, RANK, DENSE_RANK, or another window function.
4. Give the window result a clear alias.
5. Wrap the query in a CTE or derived table.
6. Write the filter condition in the outer layer.
7. Identify which conditions must filter before the window.
8. Add an outer ORDER BY if result ordering is needed.
9. Check ties, NULLs, and small-group edge cases.
10. Use EXPLAIN to evaluate cost.

## 12. Practice exercises

### Exercise 1: Top three most recent orders

Use ROW_NUMBER to retrieve the three most recent orders per customer. Add `order_id` as a tie-breaker. Check customers with fewer than three orders.

### Exercise 2: Retrieving the latest order

Use a CTE to compute ROW_NUMBER per `customer_id`. Filter `rn = 1`. Try creating two orders with identical `ordered_at` and observe the tie-breaker's effect.

### Exercise 3: Comparing the three ranking functions

Rank `total_amount` per customer using ROW_NUMBER, RANK, and DENSE_RANK. Create data with tied values and explain the row counts returned when filtering `rank <= 2`.

### Exercise 4: Top two completed orders

Write two queries: one filtering `order_status` inside the CTE before computing ROW_NUMBER; one filtering `completed` outside after ranking all orders. Compare the results and explain why they differ.

### Exercise 5: Running total reaching a threshold

Compute `running_total` by `customer_id` and `ordered_at`. Use a CTE to filter orders once the cumulative total reaches 5 million. Specify the frame and tie-breaker.

### Exercise 6: Comparing with the previous row

Use LAG to find orders whose `total_amount` is greater than the same customer's previous order. Exclude the first row of each partition and explain the NULL value.

### Exercise 7: Comparing CTE and derived table

Write the same top-N per group query using both a CTE and a derived table. Compare readability and EXPLAIN plans.

### Exercise 8: Handling NULLs in ordering

Allow `ordered_at` to be NULL in the practice table using `ALTER TABLE sales_order MODIFY ordered_at DATETIME NULL`, then insert at least one row with `ordered_at` set to NULL. Decide whether NULL should appear first or last, write an explicit ORDER BY, and check rankings.

### Exercise 9: Measuring performance

Generate larger test data for `sales_order`. Compare the top-three per `customer_id` query before and after adding an appropriate index. Use EXPLAIN ANALYZE in a test environment.

### Exercise 10: Designing a business query

Write a query retrieving orders in the top 10% by value for each customer. Determine whether PERCENT_RANK or CUME_DIST is needed, and explain the filter condition in the outer query block.

## Conclusion

To filter window function results in MySQL, compute them in one query block and filter in an outer query block. A CTE works well when you want to clearly name intermediate steps; a derived table fits a single-use subquery in one spot. Both allow the outer query to reference the window alias in WHERE.

Choose the ranking function according to requirements: ROW_NUMBER caps row count, RANK preserves position-based ties, and DENSE_RANK keeps distinct value tiers. Place filter conditions in the right layer because filtering before the window alters the rows entering each partition. Finally, add tie-breakers, define NULL rules, sort output in the outer query block, and use EXPLAIN to evaluate cost.

## References

- MySQL 8.4 Reference Manual — Window Function Concepts and Syntax: https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html
- MySQL 8.4 Reference Manual — Window Function Restrictions: https://dev.mysql.com/doc/refman/8.4/en/window-function-restrictions.html
- MySQL 8.4 Reference Manual — Window Function Descriptions: https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html
- MySQL 8.4 Reference Manual — Derived Table Optimization: https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html
