# Derived Tables, CTEs, and Choosing How to Reuse Queries

## Objectives

After this lesson, you will be able to:

- Write a derived table in the `FROM` clause and assign an alias to the subquery result.
- Use a common table expression (CTE) with `WITH` to name part of a query.
- Reuse a CTE multiple times within the same statement when needed.
- Distinguish the usage scopes of derived tables, CTEs, views, and temporary tables.
- Understand how the optimizer can merge or materialize derived tables/CTEs.
- Choose the right structure based on complexity, reusability, performance, and MySQL version.
- Inspect the execution plan instead of assuming a CTE is always faster or always executed once.

## 1. Why Name Subqueries?

When a SQL statement has to aggregate data, filter aggregated results, and continue with JOINs or calculations, a query can become long and hard to read. Derived tables and CTEs let you break a statement into named or clearly positioned query blocks.

For example, to find customers whose total revenue is higher than the average across all customers, you first need to calculate revenue per customer, and then compare those totals against their average. This can be done using a derived table or a CTE.

Both structures help:

- Isolate an intermediate calculation into an easy-to-understand query block.
- Name intermediate data such as `customer_totals` or `monthly_sales`.
- Avoid repeating the same long SQL snippet within a statement.
- Combine intermediate results with other tables.
- Make reading, testing, and modifying queries easier.

Key point to remember: derived tables and CTEs are constructs within a single SQL statement. They do not automatically create long-lived stored tables and do not inherently make queries faster.

## 2. What Is a Derived Table?

A derived table is a subquery placed in the `FROM` clause. The result of the subquery is used like a table in the outer query.

General syntax:

```sql
SELECT outer_query_columns
FROM (
    SELECT inner_query_columns
    FROM source_table
    WHERE conditions
) AS derived_alias
WHERE outer_conditions;
```

In MySQL, a derived table must have an alias. The alias enables the outer query to reference the columns of the subquery result.

### 2.1. Example: Aggregate First, Filter Afterward

Suppose the `orders` table stores orders. To find customers whose total order amount is greater than 10,000,000:

```sql
SELECT
    customer_totals.customer_id,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_totals
WHERE customer_totals.total_amount > 10000000;
```

The inner query produces one row per customer. The outer query treats that result as a table named `customer_totals` and filters by total revenue.

### 2.2. JOINing with a Derived Table

A derived table can be JOINed with a base table:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(t.total_amount, 0) AS total_amount
FROM customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.customer_id;
```

The subquery aggregates orders by customer. `LEFT JOIN` preserves customers without orders; `COALESCE()` displays 0 when there is no matching row in the derived table. Only use 0 if that representation fits the business logic.

### 2.3. Naming Columns Clearly

You should assign aliases to aggregated expressions:

```sql
SELECT
    totals.customer_id,
    totals.order_count,
    totals.revenue
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS totals;
```

The derived table's column names come from source column names or expression aliases. You can declare a column name list after the alias in supported syntax, but aliasing expressions directly in SELECT usually helps readers understand where values come from.

### 2.4. Derived Tables Can Be Nested

You can place one derived table inside another derived table, but deep nesting makes queries hard to read and hard to mentally optimize. If an intermediate step has a clear business name or is used multiple times, a CTE usually expresses the structure better.

Do not split every expression into its own derived table. Create a query block only when it clarifies a processing step or provides a useful logical boundary.

## 3. What Is a CTE?

A CTE (common table expression) is a result set named inside the `WITH` section at the beginning of a statement. The main query can reference the CTE just like referencing a table within that statement's scope.

Basic syntax:

```sql
WITH cte_name AS (
    SELECT ...
)
SELECT ...
FROM cte_name;
```

Example rewriting the revenue query using a CTE:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    total_amount
FROM customer_totals
WHERE total_amount > 10000000;
```

The CTE is named `customer_totals`, so the main query clearly indicates that the data being filtered is total revenue per customer.

### 3.1. A CTE Is Valid Only Within One Statement

A CTE is not a temporary table persisting in the session. A CTE name can only be referenced within the statement associated with that `WITH` section.

Example:

```sql
WITH active_customers AS (
    SELECT customer_id, full_name
    FROM customers
    WHERE status = 'ACTIVE'
)
SELECT *
FROM active_customers;
```

Right after the SELECT statement completes, the name `active_customers` no longer exists for use in a subsequent standalone SQL statement. If reuse across multiple statements is needed, consider a view or temporary table.

A CTE does not persist data across API calls, does not have user-declared indexes directly on it, and does not replace storage tables.

### 3.2. Declaring Column Names for a CTE

You can declare a column name list right after the CTE name:

```sql
WITH customer_totals (customer_id, order_count, revenue) AS (
    SELECT
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, order_count, revenue
FROM customer_totals;
```

The number of column names must match the number of columns returned by the subquery. This approach is useful when expressions in SELECT do not have clear names, though aliasing directly inside the subquery is still usually easier to read.

## 4. Declaring Multiple CTEs and Building a Query Pipeline

A statement can declare multiple CTEs, separated by commas. A later CTE can reference a CTE declared earlier.

Example calculating monthly revenue and then ranking the months:

```sql
WITH monthly_sales AS (
    SELECT
        DATE_FORMAT(created_at, '%Y-%m') AS sales_month,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY DATE_FORMAT(created_at, '%Y-%m')
), ranked_months AS (
    SELECT
        sales_month,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM monthly_sales
)
SELECT
    sales_month,
    revenue,
    revenue_rank
FROM ranked_months
WHERE revenue_rank <= 3
ORDER BY revenue_rank, sales_month;
```

The processing flow is divided into two steps:

1. `monthly_sales` calculates revenue for each month.
2. `ranked_months` uses that result to assign ranks.
3. The final query retrieves the top three ranks and orders the output.

The example uses the `RANK()` window function, so it requires MySQL 8.0 or later. If multiple months tie in revenue, `RANK()` may assign the same rank and skip the next rank number; if you want contiguous ranks, consider `DENSE_RANK()`.

### 4.1. Reference Ordering Between CTEs

In a non-recursive CTE list, declare the source CTE before the CTE that uses it:

```sql
WITH base_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
), customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM base_orders
    GROUP BY customer_id
)
SELECT *
FROM customer_totals;
```

`customer_totals` references `base_orders`, which was declared earlier. Ordering CTEs by dependency flow helps readers trace data from source to result.

### 4.2. CTEs Can Have Explicit Column Names

Clear column names help avoid confusion when there are multiple calculation steps:

```sql
WITH order_metrics (customer_id, order_count, total_revenue) AS (
    SELECT
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    order_count,
    total_revenue
FROM order_metrics;
```

Name them after their business meaning instead of generic names like `result1`, `temp_data`, or `query_data`.

## 5. Reusing a CTE Multiple Times Within the Same Statement

A clear benefit of CTEs is being able to reference the same name in multiple places within one statement. For example, calculating each customer's revenue and then retrieving customers whose revenue exceeds the average:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    ct.customer_id,
    ct.revenue
FROM customer_totals AS ct
WHERE ct.revenue > (
    SELECT AVG(other.revenue)
    FROM customer_totals AS other
)
ORDER BY ct.revenue DESC, ct.customer_id;
```

`customer_totals` is referenced in both the outer query and the scalar subquery. The logic definition appears only once in the `WITH` section, avoiding duplicating the entire `GROUP BY` query in two places.

However, syntactic reuse does not guarantee that the CTE is computed exactly once in every execution plan. The optimizer may merge the CTE into the outer query block or materialize it. The next section explains the difference.

## 6. How Do Derived Tables and CTEs Differ?

Both structures serve a similar purpose: embedding a subquery into a larger statement. The main differences lie in organization and reference scope.

| Criterion | Derived table | CTE |
|---|---|---|
| Declaration location | Directly inside `FROM` or places supporting derived tables | Beginning of the statement inside `WITH` |
| Naming | Alias right after the closing parenthesis | CTE name in the `WITH` section |
| Scope | The query block containing the derived table | The statement containing the `WITH` section |
| Reusing the same definition | Usually requires rewriting the query block if used in multiple places | Can reference the same name multiple times within the statement |
| Reading multi-step queries | Can become hard to follow with deep nesting | Can name each step and show a clear pipeline |
| Recursion | Not the structure used for recursive CTEs | Can use `WITH RECURSIVE` |
| Performance | Can be merged or materialized | Can also be merged or materialized |

### 6.1. When Should You Use a Derived Table?

A derived table is usually appropriate when:

- The intermediate result is used only once.
- The calculation is small and tightly coupled with a JOIN or outer query.
- Placing the query block right next to where it is used helps readers understand the data relationship.
- No shared name is needed to reference it from multiple locations.

Example:

```sql
SELECT
    c.customer_id,
    t.revenue
FROM customers AS c
JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.customer_id;
```

### 6.2. When Should You Use a CTE?

A CTE is usually appropriate when:

- The query has multiple logical steps.
- The same result set is referenced multiple times within one statement.
- You need to separate filtering, aggregation, ranking, or normalization steps.
- You want business-meaningful naming so the query is easy to read and review.
- You need to write a recursive query for tree structures or hierarchical relationships.

Example:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
), customer_revenue AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM paid_orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.full_name, cr.revenue
FROM customers AS c
JOIN customer_revenue AS cr
  ON cr.customer_id = c.customer_id;
```

Each CTE has a clear responsibility. If the pipeline only has one small step, a derived table may be more concise.

## 7. A CTE Is Not Automatically a Temporary Table

A common misconception is that a CTE is always executed first, saves its entire result into a temporary table, and then the main query reads that table. This is not a general rule.

The MySQL optimizer can handle derived tables, view references, and CTEs in two main ways:

1. **Merge:** merges the query block into the outer query so the optimizer optimizes it as one combined query.
2. **Materialize:** computes the intermediate result and stores it in an internal temporary table for the outer query to read.

A CTE is just a logical name within a statement. The decision to merge or materialize belongs to the optimizer and depends on query structure, statistics, version, and optimization rules.

### 7.1. Merging Query Blocks

When merging, the optimizer brings the subquery into the outer query block. This can enable:

- Pushing filter conditions closer to the source table.
- Leveraging indexes on the base table.
- Optimizing JOIN order together with filter predicates.
- Avoiding creating and reading an unnecessary temporary table.

Thus, a simple CTE such as filtering paid orders can be merged:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT order_id, total_amount
FROM paid_orders
WHERE customer_id = 101;
```

The optimizer can combine both conditions into a direct query on `orders`.

### 7.2. Materializing Intermediate Results

When materializing, MySQL creates an internal temporary table for the query block's result. The internal temporary table may stay in memory or spill to temporary disk storage depending on size and configuration limits.

Materialization incurs the cost of building the intermediate result, but can be useful when:

- The query block must be used as a distinct result set.
- Aggregates or constructs prevent merging.
- The CTE is referenced multiple times and materializing once is beneficial.
- The optimizer can build internal indexes to support lookups on the materialized result.

MySQL can defer materialization until the result is actually needed. If an earlier JOIN branch yields 0 rows and the intermediate result is unused, materialization may be skipped.

### 7.3. Constructs That Can Prevent Merging

Certain constructs commonly prevent a derived table/CTE from being merged into the outer query block, for example:

- Aggregate functions such as `SUM()`, `COUNT()`, `AVG()`.
- `GROUP BY` or `HAVING`.
- `DISTINCT`.
- Window functions.
- `LIMIT`.
- `UNION` or `UNION ALL` in applicable cases.

These rules depend on conditions and version; do not use this list as guesswork in place of an execution plan. When merging is not possible, the optimizer may materialize the result.

### 7.4. CTEs Referenced Multiple Times

If a CTE is materialized and referenced multiple times in the same statement, MySQL materializes it once and reuses the result. The optimizer can create different internal indexes to serve different access patterns on that CTE.

If the CTE is merged, its definition may be folded into each referencing query block. Therefore, do not assume that writing a CTE once guarantees its contents are evaluated only once.

If the goal is performance control, compare execution plans. If the goal is maintainability, CTEs remain useful even when the optimizer merges them.

## 8. ORDER BY Inside a Derived Table or CTE

There is no guarantee that results from a derived table or CTE will preserve ordering simply because the subquery contains `ORDER BY`.

Example:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC
) AS recent_orders;
```

The outer query does not specify `ORDER BY`, so there is no guarantee on output order. If you need the newest results first, sort in the outer query:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
) AS recent_orders
ORDER BY created_at DESC, order_id DESC;
```

If `ORDER BY` is used together with `LIMIT` inside to pick top-N rows, that ordering determines which rows are selected into the intermediate set:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 10
) AS latest_orders
ORDER BY created_at DESC, order_id DESC;
```

Here, the inner `ORDER BY` selects the 10 latest orders; the outer `ORDER BY` guarantees the return order. Use a unique tie-breaker if timestamps can collide.

## 9. CTEs vs. Views and Temporary Tables

Derived tables and CTEs exist only within a single statement's structure. When you need to reuse logic or data across multiple statements, consider other mechanisms.

| Mechanism | Lifespan scope | Use when |
|---|---|---|
| Derived table | One position within a single statement | Small query block used only once |
| CTE | One statement | Multiple logical steps or reusing the CTE name within the same statement |
| View | Schema object existing until altered/dropped | Wanting to encapsulate a query and reuse it across multiple statements/authorized users |
| Temporary table | Current session, until dropped or session ends | Needing to retain intermediate results across multiple statements or create custom indexes for processing steps |
| Regular table / application-managed materialized result | Exists according to storage policy | Needing to store precomputed results, share across sessions, or serve repetitive workloads |

### 9.1. When to Use a View?

A view is suitable when the same query logic needs to be used by multiple statements or multiple application components:

```sql
CREATE VIEW customer_order_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Then:

```sql
SELECT customer_id, revenue
FROM customer_order_totals
WHERE revenue > 10000000;
```

A regular view stores the query definition, not precomputed results like materialized views in some other DBMSs. When querying a view, the optimizer still processes the view definition and may merge or materialize it according to MySQL rules.

### 9.2. When to Use a Temporary Table?

If you need to build an intermediate dataset and use it across multiple SQL statements in the same session:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (customer_id)
);

INSERT INTO tmp_customer_totals (customer_id, revenue)
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;

SELECT customer_id, revenue
FROM tmp_customer_totals
WHERE revenue > 10000000;

DROP TEMPORARY TABLE tmp_customer_totals;
```

Temporary tables allow declaring indexes/constraints as needed and reusing results across multiple statements. In exchange, the application must manage their lifecycle, session scope, and cleanup. Connection pools can reuse connections, so avoid letting old temporary tables affect subsequent requests.

## 10. Choosing Between Derived Tables and CTEs by Example

### 10.1. Single Use, One Simple Step: Derived Table

```sql
SELECT
    p.category_id,
    p.product_name,
    p.price
FROM products AS p
JOIN (
    SELECT category_id, AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
) AS category_average
  ON category_average.category_id = p.category_id
WHERE p.price > category_average.avg_price;
```

The derived table is used once to compute the average price per category. This style is concise when the intermediate logic has only one step.

### 10.2. Multiple Steps or Reuse: CTE

```sql
WITH category_average AS (
    SELECT
        category_id,
        AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
), above_average AS (
    SELECT
        p.product_id,
        p.category_id,
        p.product_name,
        p.price,
        ca.avg_price
    FROM products AS p
    JOIN category_average AS ca
      ON ca.category_id = p.category_id
    WHERE p.price > ca.avg_price
)
SELECT
    product_id,
    category_id,
    product_name,
    price,
    avg_price
FROM above_average
ORDER BY category_id, price DESC, product_id;
```

Each CTE represents a business step: calculating category averages, then retrieving products above average. The final query explicitly specifies the return order.

### 10.3. Do Not Use CTEs Just to Rename Every Table

A CTE does not automatically improve a statement if it only adds a meaningless naming layer:

```sql
WITH all_orders AS (
    SELECT * FROM orders
)
SELECT * FROM all_orders;
```

If a CTE adds no filter, calculation, business name, or reuse benefit, querying directly is usually easier to read. Avoid `SELECT *` in long-lived CTEs because source schema changes can alter the column set and carry unnecessary data.

## 11. Performance: EXPLAIN and Factors to Observe

You cannot conclude that a CTE is faster than a derived table from syntax alone. If two SQL statements express the same logic, the optimizer may generate identical or nearly identical execution plans.

### 11.1. Using EXPLAIN

```sql
EXPLAIN
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 10000000;
```

Check:

- Which source tables are read and under which access type.
- Which indexes are selected.
- Estimated row counts at each step.
- Whether there is a materialize step or temporary table.
- Whether there is any significant filesort or temporary processing.
- Whether filter conditions are applied early or late.

How CTEs/derived tables appear in `EXPLAIN` depends on the version and explain format. You can use `EXPLAIN FORMAT=TREE` on supported versions to read the execution flow more clearly.

### 11.2. EXPLAIN ANALYZE

MySQL 8.0.18 and later supports `EXPLAIN ANALYZE` for eligible SELECT statements:

```sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 10000000;
```

This command actually executes the query and reports actual timings and row counts across iterators. Use it only with appropriate queries and environments, because a large aggregation query still generates real server load.

### 11.3. Indexes Are Still Required on Source Tables

A CTE does not directly create indexes for source tables. If a query filters orders by status and timestamp:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount, created_at
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2026-01-01'
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM paid_orders
GROUP BY customer_id;
```

you need to examine the workload to evaluate indexes on `orders`, for instance `(status, created_at, customer_id)` or another column order based on selectivity and actual queries. No template index fits every data distribution.

### 11.4. Materialization and Memory/Disk Cost

If a query block materializes many rows or many columns, the internal temporary table can grow large. Reduce cost by:

- Selecting only needed columns; avoiding `SELECT *`.
- Filtering rows early if conditions can be applied safely.
- Aggregating at the exact granularity required.
- Avoiding materializing a large dataset for a single use when merging can work efficiently.
- Measuring at near-production scale and monitoring temporary tables on disk.

If a CTE is referenced multiple times, materializing once can save recomputation. However, if the intermediate set is very large or the optimizer can push distinct predicates into each query block when merging, materialization may not be the best choice. Base your decision on the execution plan and measured metrics.

## 12. Controlling Merge/Materialization When Needed

In certain advanced optimization scenarios, MySQL provides the `MERGE()` and `NO_MERGE()` optimizer hints for derived tables, view references, and CTEs in supported versions.

Illustrative example instructing the optimizer not to merge a CTE:

```sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT /*+ NO_MERGE(customer_totals) */
    customer_id,
    revenue
FROM customer_totals
WHERE revenue > 10000000;
```

A hint is a suggestion to the optimizer, not a substitute for performance measurement. Syntax, scope, and applicability depend on the MySQL version. Check warnings in case a hint is unrecognized or not applied, then compare `EXPLAIN`/`EXPLAIN ANALYZE` before and after.

Do not force materialization or merging just because you assume one approach is always faster. An inappropriate hint can prevent the optimizer from pushing predicates, using indexes, or choosing a better JOIN order.

## 13. Recursive CTEs and the Scope of This Lesson

Non-recursive CTEs are declared using `WITH`. When you need to query hierarchical structures such as category trees or management charts, MySQL supports `WITH RECURSIVE`:

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, parent_id, category_name, 0 AS depth
    FROM categories
    WHERE category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        ct.depth + 1
    FROM categories AS c
    JOIN category_tree AS ct
      ON c.parent_id = ct.category_id
)
SELECT category_id, parent_id, category_name, depth
FROM category_tree
ORDER BY depth, category_id;
```

The anchor query retrieves the root node; the recursive query finds child nodes of existing rows. This example illustrates the structure and assumes the data has no cycles causing infinite loops. Appropriate cycle-prevention policies and depth limits are needed in implementation.

Recursive CTEs are a specialized topic for tree queries. This lesson focuses on derived tables, non-recursive CTEs, and choosing query reuse structures; when working with trees, you also need to learn termination conditions, recursive column data types, `cte_max_recursion_depth`, and cycle handling.

## 14. Common Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Derived table without an alias | MySQL reports a syntax error / missing derived table name | Add an alias right after the closing parenthesis |
| Thinking a CTE is a temporary table | Expecting the CTE to exist in the next statement | Use a view or temporary table if multiple statements are needed |
| Thinking a CTE is always evaluated once | Misestimating cost when the optimizer merges | Check merge/materialization with EXPLAIN |
| Thinking a CTE always materializes | May miss merge capability and predicate pushdown | Understand CTEs are query blocks; the optimizer decides execution |
| Using a CTE just to wrap SELECT * | Adds unnecessary layers and couples to source schema | Select explicit columns; only create a CTE when meaningful |
| Relying on ORDER BY inside a CTE to sort output | Outer result order is not guaranteed | Put ORDER BY on the final SELECT |
| Nesting too many derived tables | SQL becomes hard to read and maintain | Name steps with CTEs if it clarifies the processing flow |
| Using a CTE multiple times without measuring | Materialization or merging may not suit the workload | Compare execution plans and latency |
| Creating temporary tables without pool management | Reused sessions may retain stale temporary tables | Clean up and manage lifecycle per connection |

## 15. Workflow for Choosing the Right Structure

1. **Determine the reuse scope:** used once, multiple places in one statement, or across multiple statements?
2. **Identify the logical steps:** are there filtering, aggregation, ranking, or intermediate transformation steps that need distinct names?
3. **Choose a derived table if:** the query block is small, used only once, and placing it beside the JOIN aids comprehension.
4. **Choose a CTE if:** there are multiple steps, business-meaningful naming is needed, or the same result is reused within one statement.
5. **Choose a view if:** the logic needs to be reused across multiple statements and managed as a schema object.
6. **Choose a temporary table if:** results need to be stored across multiple statements, custom indexes are needed, or processing happens in stages within a session.
7. **Check the optimizer:** verify whether the query block is merged or materialized, and whether temporary tables or internal indexes are used.
8. **Measure performance:** use EXPLAIN, EXPLAIN ANALYZE as appropriate, and representative data.
9. **Verify output:** validate row counts, NULLs, grouping, ordering, and accuracy of aggregations.

## 16. Pre-Production Query Checklist

- [ ] Derived tables have clear aliases.
- [ ] CTEs have names and column names that reflect business meaning.
- [ ] Each query block selects only the required columns.
- [ ] Determined whether the CTE is single-statement only or needs long-term reuse.
- [ ] Not relying on derived table/CTE ordering if the final SELECT lacks ORDER BY.
- [ ] Not assuming a CTE always materializes or always runs once.
- [ ] Evaluated merging, materialization, and intermediate dataset size.
- [ ] Source tables have indexes suited to actual filter/JOIN conditions.
- [ ] Inspected EXPLAIN and measured the query with representative data.
- [ ] If using hints, verified the server accepted the hint and measured before/after.
- [ ] If using temporary tables, managed lifecycle per session/connection pool.
- [ ] If using recursive CTEs, defined anchor, termination condition, depth limit, and cycle protection.

## 17. Conclusion

A derived table places a subquery inside `FROM` and usually fits a single-use intermediate step. A CTE names a query block at the start of a statement, helping split multi-step queries and reference the same definition in multiple places within one statement. Both can be merged or materialized by the optimizer; a CTE is not automatically a temporary table and does not guarantee faster queries.

Choose the structure based on reuse scope and logical clarity. Use a view when reuse across multiple statements is needed, a temporary table when intermediate results must persist across multiple steps, and always inspect the execution plan when performance matters. A readable query must go hand in hand with accurate results, appropriate indexes, and measured execution behavior.
