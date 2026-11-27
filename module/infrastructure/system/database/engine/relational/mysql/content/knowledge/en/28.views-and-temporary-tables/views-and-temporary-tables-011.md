# Choosing a View, CTE, Temporary Table, or Result Table for Your Use Case

MySQL provides several ways to organize a result set for reuse: **views**, **CTEs**, **temporary tables**, and **result tables** managed by an application or ETL job. They may look similar because each can represent queried data, yet they differ in lifetime scope, reusability, data freshness, indexing, and storage cost.

This lesson belongs to MySQL's **Views and Temporary Tables** section. The goal is to choose the right construct for the problem: views for reusable query logic, CTEs for a single SQL statement broken into readable steps, temporary tables for intermediate data within a session or multi-step workflow, and result tables for aggregated data serving multiple sessions with predictable read latency.

## 1. Four Options Solving Four Different Needs

| Option | Scope and Lifecycle | Are Results Pre-Stored? | Suitable When |
| --- | --- | --- | --- |
| View | Definition exists in schema; queryable from multiple authorized sessions. | Usually no; a view stores a SELECT query, and data is read from source tables when queried. | You want to reuse logic, standardize access, or provide a data interface layer. |
| CTE (`WITH`) | Exists only within a single statement. | Not a persistent storage object; the optimizer may merge or materialize it during execution. | You want to break a complex SQL query into named steps, use recursion, or organize multi-layered queries. |
| Temporary table | Visible only to the creating session; automatically dropped when session ends or explicitly dropped. | Yes; holds rows written into the temporary table. | You need to keep an intermediate set across multiple statements, build dedicated indexes, or process in multiple steps. |
| Result table (summary/cache/staging table) | Schema object existing across multiple sessions until dropped or replaced. | Yes; data is generated and refreshed via an application/ETL process. | Multiple users need to read the same aggregated results and controlled refresh lag is acceptable. |

The deciding factor is not which syntax is shortest. Identify who needs the data, for how long, whether the latest data is required, whether dedicated indexes are needed, and whether compute cost should be paid at read time or refresh time.

## 2. Use a View When Reusing Query Logic

A view is a schema object storing a SELECT definition. When querying a view, MySQL typically merges the view definition with the outer query or materializes the result depending on the algorithm and statement structure. Regular views do not store a separate copy of data.

For example, an application frequently needs a list of paid orders:

```sql
CREATE OR REPLACE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID';
```

Subsequent queries can use the same definition:

```sql
SELECT order_id, created_at, total_amount
FROM v_paid_orders
WHERE customer_id = 1001
ORDER BY created_at DESC;

SELECT COUNT(*) AS paid_order_count
FROM v_paid_orders
WHERE created_at >= '2026-01-01';
```

Benefits of views:

- Consolidates shared logic into a named definition.
- Reduces repetition of JOIN expressions and filter predicates across SQL statements.
- Can restrict exposed columns for a user group, combined with view privileges and appropriate underlying privileges.
- Helps decouple applications from underlying table structural details.

Views do not automatically make queries faster. If a view contains heavy JOINs, aggregates, or expensive expressions, every query may still perform the corresponding work. To speed things up, inspect execution plans, index source tables, or consider storing precomputed results.

### MERGE, TEMPTABLE, and How Views Execute

MySQL supports view algorithms:

- `MERGE`: the optimizer merges the view definition into the outer query when possible.
- `TEMPTABLE`: view results are materialized into an internal temporary table during execution.
- `UNDEFINED`: lets MySQL choose the appropriate algorithm; this is the default if omitted.

Example declaring an algorithm:

```sql
CREATE ALGORITHM = MERGE VIEW v_customer_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

`MERGE` can allow conditions from the outer query to be pushed down to source tables. However, constructs such as aggregates, `DISTINCT`, `GROUP BY`, `HAVING`, `LIMIT`, `UNION`, or incompatible expressions can block merging. In such cases, MySQL may have to materialize or decline a requested algorithm depending on the definition.

A view using `TEMPTABLE` can be useful when an intermediate result is needed before further processing, though it can increase temporary table read/write overhead. It also affects view updatability: a materialized view does not have the same updatability capabilities as a merged view.

### Are Views Updatable?

Some simple views can be used in `INSERT`, `UPDATE`, or `DELETE`. Updatability depends on the view structure. Views with aggregates, `GROUP BY`, `DISTINCT`, `UNION`, certain subqueries, or transformations that break one-to-one mapping to source rows are usually not updatable.

Simple view example:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, email
FROM customers
WHERE status = 'ACTIVE';
```

An update through the view can be translated to the source table if the view satisfies updatability rules:

```sql
UPDATE v_active_customers
SET email = 'new-address@example.com'
WHERE customer_id = 1001;
```

Do not assume every view is writable. Inspect the definition, add `CHECK OPTION` if rows written through the view must remain constrained, and test behavior in an appropriate environment. Views have no own indexes; indexes must be created on source tables.

## 3. Use a CTE When Structuring a Multi-Step Statement

A CTE (Common Table Expression) is declared with `WITH` and is valid only within the statement that follows it. CTEs help name a logical result set and break a query into steps that can be read and verified individually.

Example calculating order totals per customer and then filtering high-revenue groups:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS total_spent
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 10000
ORDER BY total_spent DESC;
```

CTEs fit well when:

- One SQL statement needs multiple clearly named logical steps.
- The same result set is referenced multiple times within one statement.
- You need a recursive query to traverse trees, parent-child relationships, or linked chains.
- You want to separate filtering, aggregation, and JOINs for easier inspection.

CTEs do not exist after the statement ends. If a session needs to use the same intermediate data across multiple statements, a CTE cannot replace a temporary table.

### A CTE Does Not Always Materialize

MySQL may merge a non-recursive CTE into the outer query block or materialize its result depending on structure and optimizer choices. A CTE referenced multiple times may be materialized once and reused within the statement; the optimizer may even create internal indexes on the materialized result when beneficial. Do not assume every CTE always creates a physical temporary table or always recomputes for every reference.

Inspect the plan:

```sql
EXPLAIN FORMAT = TREE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_spent
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 10000;
```

If actual execution metrics are needed, `EXPLAIN ANALYZE` can be used on suitable SELECT statements. CTEs organize SQL; execution plans reveal how the optimizer actually runs it.

### Recursive CTEs for Hierarchical Data

Recursive CTEs are well suited for traversing tree structures such as categories, employees and managers, or parent-child nodes:

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, parent_id, category_name, 0 AS depth
    FROM categories
    WHERE category_id = 10

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name, ct.depth + 1
    FROM categories AS c
    JOIN category_tree AS ct
      ON c.parent_id = ct.category_id
)
SELECT category_id, parent_id, category_name, depth
FROM category_tree
ORDER BY depth, category_id;
```

The anchor part finds root nodes; the recursive part fetches child nodes of the discovered set. Include proper termination conditions and avoid cyclic data causing excessive recursion. MySQL enforces a recursion depth limit (`cte_max_recursion_depth`), and timeouts can be configured for appropriate SELECT statements.

## 4. Use a Temporary Table When Holding Results Across Multiple Statements

A session-created temporary table is visible only within that session. Other sessions cannot query this temporary table; it is dropped automatically when the session closes or can be dropped early via `DROP TEMPORARY TABLE`.

For example, a workflow needs to select qualified customers, then validate and process them in multiple steps:

```sql
CREATE TEMPORARY TABLE tmp_target_customers (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    total_spent DECIMAL(14, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_target_customers (customer_id, total_spent)
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
GROUP BY customer_id;

SELECT COUNT(*) AS target_count
FROM tmp_target_customers;

SELECT c.customer_id, c.customer_name, t.total_spent
FROM customers AS c
JOIN tmp_target_customers AS t
  ON t.customer_id = c.customer_id;

DROP TEMPORARY TABLE tmp_target_customers;
```

Temporary tables are useful when:

- The same intermediate set is used across multiple statements in a session.
- Dedicated indexes are needed on intermediate data.
- You want to split a workflow into stages and check row counts between steps.
- You want to avoid recomputing an expensive result set multiple times in the same session.
- You need to store intermediate processing results without creating a schema-wide shared object.

### Temporary Tables and Session Scope

Two sessions can create temporary tables with the same name; each session sees its own temporary table. Within the creating session, that temporary table can shadow a permanent table of the same name when resolving unqualified names. Therefore, use a prefix like `tmp_` and drop temporary tables explicitly to avoid confusion.

```sql
CREATE TEMPORARY TABLE tmp_session_result (
    id BIGINT PRIMARY KEY,
    score DECIMAL(8, 2)
) ENGINE = InnoDB;
```

Temporary tables can use engines like InnoDB or MEMORY depending on requirements and support. InnoDB fits when broader data types and storage properties are needed; MEMORY stores data in RAM, has column type limits, and consumes memory per session. Do not choose MEMORY merely because its name sounds faster.

### Temporary Tables Can Have Indexes

Unlike CTEs and views, user-created temporary tables can declare primary keys and secondary indexes:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT NOT NULL,
    total_spent DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY ix_total_spent (total_spent)
) ENGINE = InnoDB;
```

Indexes help if multiple subsequent statements JOIN or filter the intermediate set. However, building indexes also incurs write and memory/disk costs; if scanned only once, an index may not be worth creating.

### Caveats on Transactions and Lifecycle

Temporary tables are not shared across sessions and are cleaned up when the session closes. However, creating/dropping a temporary table should not be treated as a business data change that can be completely rolled back: some temporary table DDL operations do not cause an implicit commit, yet table creation/dropping itself does not roll back like DML. Keep temporary table structural lifecycles separate from transactions updating business data.

In connection pools, sessions can be reused across different requests. Lingering temporary tables can cause name collisions or data leakage between logical flows if the application fails to drop them or reset the session properly. Use clear names, drop temporary tables when done, and verify the pool's connection reset policy.

## 5. Use a Result Table When Multiple Sessions Need to Read the Same Data

If many users or services need to read the same aggregated dataset and recomputing it every time is too costly, you can store the results in a permanent table. An application or ETL job is responsible for generating and refreshing the data.

Example of a daily sales summary table:

```sql
CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(16, 2) NOT NULL,
    refreshed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (sales_date, customer_id),
    KEY ix_customer_date (customer_id, sales_date)
) ENGINE = InnoDB;
```

A job can aggregate source data and write to the table:

```sql
INSERT INTO daily_sales_summary (
    sales_date,
    customer_id,
    order_count,
    revenue,
    refreshed_at
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount),
    CURRENT_TIMESTAMP
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-03-02'
GROUP BY DATE(created_at), customer_id;
```

This example illustrates loading aggregated results for one day. When refreshing multiple days, define how groups that disappeared from source data are handled: a plain insert does not automatically remove stale groups with no remaining rows. You can delete the refresh date range within the same transaction and re-insert, or use staging and a controlled replacement workflow. If choosing upsert, use syntax compatible with your MySQL version and clearly identify which unique keys can conflict.

### Benefits and Costs of Result Tables

Benefits:

- Multiple sessions read the same data without recomputing heavy aggregation queries.
- Dedicated indexes, partitions, and access privileges can be created.
- Refresh schedules and data publication timing are controllable.
- Extra metadata like `refreshed_at`, batch ID, or source watermark can be stored to track freshness.

Costs:

- Consumes storage and index space.
- Requires designing full refresh, incremental refresh, or backfill handling when source data changes.
- Data may lag behind source tables; applications must understand the freshness contract.
- Requires handling concurrency between refresh jobs and read queries.
- Risks inaccurate aggregated data if job retries, missed ranges, or non-idempotent updates occur.

A result table is not an auto-refreshing materialized view. MySQL does not provide built-in materialized views in the way some other DBMSs do; storage, refreshing, and synchronization must be designed by the application or ETL pipeline.

## 6. Refreshing Result Tables: Full Refresh and Incremental Refresh

### Full Refresh Over a Small Scope

If refreshing only one day or a small period, you can delete old data in that scope and insert new results within the same transaction:

```sql
START TRANSACTION;

DELETE FROM daily_sales_summary
WHERE sales_date = '2026-03-01';

INSERT INTO daily_sales_summary (
    sales_date,
    customer_id,
    order_count,
    revenue,
    refreshed_at
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount),
    CURRENT_TIMESTAMP
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-03-02'
GROUP BY DATE(created_at), customer_id;

COMMIT;
```

If the insert fails before commit, both the delete and insert can be rolled back because the table uses InnoDB. However, large transactions can hold locks and generate substantial undo/redo logs. For large scopes, use staging tables or checkpointed partial refreshes.

### Incremental Refresh

Incremental refresh recomputes only data that changed since a watermark or CDC position. This reduces data scanned, though it adds complexity:

- Must detect inserts, updates, and deletes in source tables.
- Must handle late-arriving events or backdated updates.
- Must persist watermarks reliably and update them in the same transaction publishing results.
- Needs periodic reconciliation against full-refresh results.

If source systems can modify last month's data, an incremental refresh reading only new records by `created_at` will miss updates. Base watermarks on modification columns or an appropriate change data capture mechanism.

### Staging and Publishing Results

For large refreshes, you can load results into a staging table, verify row counts and control totals, and then publish via a controlled replacement step. Conceptual example:

```sql
CREATE TABLE daily_sales_summary_stage LIKE daily_sales_summary;

-- Load and validate data in daily_sales_summary_stage.
-- After verification, plan the table swap following operational procedures.
```

Do not run `RENAME TABLE` or drop/replace production tables based solely on a skeleton example. DDL involves metadata locks and implicit commit rules; review privileges, dependent views, foreign keys, triggers, backups, replication, and rollback capability before publishing. For large tables or critical systems, test the swap procedure on a production-equivalent replica.

## 7. Comparing Data Freshness and Read Cost

A quick selection method is determining the data freshness required by the application:

| Data Requirement | Typically Suitable Choice | Reason |
| --- | --- | --- |
| Always read current source data, logic reused in many places | View | No separate refresh process needed; each query reads source tables. |
| Only need an intermediate set within one statement | CTE | Clear scope with no object lifecycle management needed. |
| Need intermediate results across multiple statements in one session | Temporary table | Can store rows, build indexes, and reuse within the session. |
| Multiple sessions need precomputed results, lag is acceptable | Result table | Results are stored and refreshed on a schedule or event. |
| Need to traverse trees or multi-level hierarchies in one query | Recursive CTE | Expresses recursion directly in SQL. |
| Need per-request private results, not shared across sessions | Temporary table or CTE | Choose based on statement count and indexing needs. |

For example, a revenue dashboard tolerating 5-minute lag can read a summary table refreshed every 5 minutes. An order detail screen requiring live status can read a view or source tables directly. A report needing multi-step calculations within a single query can use a CTE. An import workflow needing multi-step reconciliation within one connection can use a temporary table.

## 8. Access Privileges and Security

Views can form an access layer exposing only permitted columns. Combine with `SQL SECURITY DEFINER` or `SQL SECURITY INVOKER` to define which privileges apply when the view runs:

```sql
CREATE SQL SECURITY DEFINER VIEW v_public_customer AS
SELECT customer_id, customer_name
FROM customers
WHERE status = 'ACTIVE';
```

- `DEFINER`: privilege checks on underlying objects are evaluated against the view's definer account.
- `INVOKER`: privileges are checked against the account invoking the view.

Manage the definer and its account privileges carefully. A definer view can allow users to read underlying data they do not have direct SELECT access to, provided the view and privileges are configured properly. Do not grant overly broad privileges to definers and do not treat views as an automatic security boundary.

Temporary tables are session-scoped, yet their contents can still hold sensitive information during the session's lifetime. Result tables are permanent objects and require authorization, backups, retention, and auditing like any other business table. CTEs exist only within a statement, yet the query still requires read privileges on source tables under the corresponding privilege model.

## 9. Performance Factors to Inspect

When choosing among the four options, check:

1. **Execution plan:** does the view merge or materialize; does the CTE materialize; does the temporary table scan or use indexes; does the summary table have an appropriate access path?
2. **Computation cost:** is logic recomputed on every read or only during refresh?
3. **Reuse count:** single statement, multiple statements in one session, or multiple sessions?
4. **Intermediate size:** row count, row width, and indexes needed.
5. **Concurrency:** do multiple sessions concurrently refresh or write to temporary/result tables?
6. **Freshness:** how fresh must data be, and how much stale read latency is acceptable?
7. **Operations:** who creates, refreshes, drops, monitors failures, and purges old data?

Inspection tools:

```sql
EXPLAIN FORMAT = TREE
SELECT *
FROM v_paid_orders
WHERE customer_id = 1001;

EXPLAIN ANALYZE
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY
)
SELECT customer_id, SUM(total_amount)
FROM recent_orders
GROUP BY customer_id;
```

`EXPLAIN ANALYZE` executes the query. Use it on safe SELECTs, bounded datasets, and appropriate environments. Never judge solely by SQL brevity or line count.

## 10. Practical Selection Scenarios

### Scenario A: Multiple Screens Share the Same Active Customer Filter

Choose a view if multiple queries need the same simple filter and join logic while requiring fresh data from source tables. Create indexes on source tables matching query predicates; verify view merging and access privileges.

### Scenario B: A Report Needs Multiple Aggregation Steps in One Query

Choose a CTE to name steps such as `paid_orders`, `customer_totals`, and `ranked_customers`. If a CTE is referenced multiple times or yields a large result, check whether the optimizer materializes it and measure actual cost.

### Scenario C: An Import Job Needs the Same Key Set Across Multiple Steps

Choose a temporary table to store the key set, build primary keys/indexes, and reuse across multiple statements. Drop the table upon completion; ensure connection pools do not reuse sessions with leftover temporary data.

### Scenario D: A Dashboard Has Many Users and Very Heavy Aggregations

Choose a result table if the dashboard can tolerate delayed data under a clear SLA. Design idempotent refreshes, watermarks, publication timestamps, freshness indicators, and reconciliation procedures.

### Scenario E: Temporary Aggregated Data Is Needed Only Inside One Query

A CTE is usually the most readable choice. There is no need to create a permanent view or temporary table if the result is used only in a single statement.

## 11. Quick Decision Table

| Question | If the Answer Is "Yes" | Option to Consider |
| --- | --- | --- |
| Does SELECT logic need reuse across multiple statements and sessions? | Yes | View |
| Is the result needed only within one statement? | Yes | CTE |
| Must intermediate data persist across multiple statements in one session? | Yes | Temporary table |
| Are dedicated indexes needed on the intermediate set? | Yes, and only within the session | Temporary table |
| Do multiple sessions need to read precomputed results? | Yes | Result table |
| Is lagged data acceptable with a refresh process? | Yes | Result table |
| Is the latest data from source tables needed on every read? | Yes | View or direct query; CTE if multi-step structuring is needed |

You do not have to pick only one type. A workflow might use a CTE to compute results, load them into a temporary table for multi-step validation, and then write into a result table after verification. Choose according to data boundaries and lifecycle rather than adding extra constructs without a clear need.

## 12. Design and Operations Workflow

1. Explicitly document freshness requirements: live source reads, statement-scoped snapshot, session-scoped, or scheduled refresh results.
2. Identify user count and reuse scope: one statement, one session, or system-wide.
3. Estimate intermediate data volume and indexing needs.
4. Pick a view, CTE, temporary table, or result table using the matrix above.
5. Use EXPLAIN to inspect merge/materialization, access paths, and estimated rows.
6. If materializing or storing results, measure creation time, storage size, index overhead, and read latency.
7. Design lifecycle management: dropping temporary tables, refreshing summaries, cleaning staging, and monitoring job failures.
8. Design appropriate access privileges, especially for view definers and result tables containing sensitive data.
9. Check concurrency, connection pools, transactions, metadata locks, and retry behavior.
10. Clearly expose data freshness and refresh timestamps so users do not mistake lagged data for real-time updates.

## 13. Common Selection Mistakes

- **Using a view expecting pre-stored results.** Regular views store definitions, not results; queries still read source tables.
- **Using a CTE like a table shared across multiple statements.** A CTE is scoped to a single statement.
- **Creating temporary tables while forgetting session scope.** Other sessions cannot see the data; connection pools can retain temporary tables across reused sessions.
- **Creating summary tables without a refresh contract.** Readers do not know how stale data is and jobs risk missing updates.
- **Assuming CTEs always materialize.** The optimizer may merge or materialize depending on structure and plan.
- **Assuming views are always updatable.** Aggregates, DISTINCT, GROUP BY, and other constructs can make views non-updatable.
- **Creating indexes on every temporary table.** Indexes have overhead; add them only when subsequent steps actually use them.
- **Using `CREATE OR REPLACE VIEW` without checking privileges/dependencies.** Changing definitions can break applications and access controls.
- **Refreshing result tables with non-atomic multi-statement steps.** Readers may see mixed data across two refreshes; use transactions or proper staging/publishing workflows.

## 14. Self-Check Exercises

1. Does a view store a definition or store results? Why does a view not automatically speed up queries?
2. When can MySQL merge a view and when might it materialize it?
3. How does a CTE differ from a temporary table in scope and lifecycle?
4. Why should you not assume a CTE is always materialized?
5. Give a scenario where a recursive CTE is more suitable than a view or temporary table.
6. When does a temporary table gain an advantage from dedicated indexes and multi-statement reuse?
7. Why must a connection pool clean up temporary tables before reusing sessions?
8. When should results be persisted in a summary table instead of recomputing via a view?
9. Distinguish full refresh from incremental refresh; what must a watermark guarantee?
10. How do you publish refreshed results so reading sessions never see half-old, half-new data?

Choose the right construct by answering four questions: **how fresh must the data be, who needs to reuse it, how long must it persist, and does it need dedicated indexes**. Views and CTEs organize query logic; temporary tables hold intermediate results within a session; result tables serve multiple sessions when a clear refresh and freshness-control workflow is in place.
