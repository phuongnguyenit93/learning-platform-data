# Aggregate Queries, GROUP BY, and Statistical Data

Many use cases do not need individual entities, but rather aggregated results: monthly revenue totals, order counts by status, average order value, active customer counts, or stock levels by product. With Spring Data R2DBC, let the database perform aggregations in SQL and map the results into projections/DTOs. This reduces network traffic, avoids loading large numbers of entities into the JVM, and is usually far more efficient than fetching all rows to sum or average in Java.

`GROUP BY`, `HAVING`, and aggregate functions can be used via `@Query`, `DatabaseClient`, or appropriate `R2dbcEntityTemplate` APIs. For reports with multiple calculations, JOINs, or flexible filters, `DatabaseClient` typically gives clearer control over SQL and mapping. Pay special attention to `NULL` semantics, return data types, JOIN cardinality, and paginating grouped results rather than source rows.

## 1. What are aggregate queries used for?

Aggregate queries condense many rows into one or more summary values. For example, the `purchase_order` table may hold millions of orders, yet a dashboard only needs order counts and revenue by status. Instead of loading every order into the application, the database can return just a few summary rows.

| Requirement | Common SQL |
|---|---|
| Total row count | `COUNT(*)` |
| Count of non-NULL values | `COUNT(column)` |
| Total amount/quantity | `SUM(column)` |
| Average value | `AVG(column)` |
| Minimum/maximum value | `MIN(column)`, `MAX(column)` |
| Distinct value count | `COUNT(DISTINCT column)` |
| Group-level statistics | `GROUP BY` |
| Filtering groups after aggregation | `HAVING` |

Example: counting orders by status:

```sql
SELECT status, COUNT(*) AS order_count
FROM purchase_order
GROUP BY status;
```

If the table has statuses `NEW`, `PAID`, and `CANCELLED`, the result has at most one row per status present in the dataset.

## 2. Tables used in examples

Suppose a system has tables for orders and order lines:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_no VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 4) NOT NULL
);
```

Common reports include:

- Order count by status.
- Total monthly revenue.
- Order count and revenue by tenant.
- Quantity of products sold.
- Average order value per customer.
- Customer groups whose total spend exceeds a threshold.

The examples use common SQL; timestamp types, date functions, and pagination syntax may need adjustments for your target database.

## 3. Basic aggregate functions

### `COUNT`

`COUNT(*)` counts all rows in the input set:

```sql
SELECT COUNT(*) AS total_orders
FROM purchase_order;
```

`COUNT(column)` counts only rows where the column value is not `NULL`:

```sql
SELECT COUNT(customer_id) AS orders_with_customer
FROM purchase_order;
```

`COUNT(DISTINCT column)` counts distinct non-`NULL` values:

```sql
SELECT COUNT(DISTINCT customer_id) AS customer_count
FROM purchase_order;
```

### `SUM`

`SUM` adds non-`NULL` values:

```sql
SELECT SUM(quantity) AS total_quantity
FROM order_line;
```

For money, use `DECIMAL`/`NUMERIC` and Java `BigDecimal`, never `double` for calculations requiring decimal precision.

### `AVG`

`AVG` computes the mean of non-`NULL` values:

```sql
SELECT AVG(unit_price) AS average_unit_price
FROM order_line;
```

The result type of `AVG` depends on the database and input type. Verify mapping through your R2DBC driver; if specific precision/scale rules are needed, CAST in SQL according to your dialect.

### `MIN` and `MAX`

```sql
SELECT MIN(created_at) AS first_order_at,
       MAX(created_at) AS latest_order_at
FROM purchase_order;
```

`MIN`/`MAX` operate on ordered types such as numbers, timestamps, or strings. For strings, results depend on collation.

## 4. How does `NULL` affect aggregation?

Aggregate functions generally ignore `NULL` values, though the final result can be `NULL` when no non-null input values exist:

| Expression | Meaning |
|---|---|
| `COUNT(*)` | Counts all rows, including rows with NULL columns |
| `COUNT(amount)` | Counts rows where `amount` is not NULL |
| `SUM(amount)` | Sum of non-NULL amounts; can be NULL if no values exist |
| `AVG(amount)` | Average of non-NULL amounts; can be NULL if no values exist |
| `MIN(amount)`/`MAX(amount)` | Ignores NULL; returns NULL if no values exist |

Example:

```sql
SELECT COALESCE(SUM(amount), 0) AS total_amount
FROM payment
WHERE status = 'SETTLED';
```

`COALESCE` returns 0 when `SUM` is NULL. Use a default value only when business logic considers "no transactions" equivalent to a total of 0. For `AVG`, replacing NULL with 0 can skew statistics; do not apply defaults blindly.

## 5. `GROUP BY` partitions data into groups

`GROUP BY` groups rows that share the same values across the grouping columns. Each group yields one result row after aggregates are applied.

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY status
ORDER BY status;
```

Grouping by multiple columns:

```sql
SELECT tenant_id,
       status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Each `(tenant_id, status)` pair forms its own group. The number of result rows equals the number of distinct combinations appearing in the dataset after `WHERE`.

In standard SQL, every expression in `SELECT` must be a grouping expression, an aggregate function, or an expression permitted by the database via functional dependency. Do not select an ungrouped, unaggregated column expecting the database to pick a representative value automatically.

## 6. Rules for selecting columns with GROUP BY

Valid example:

```sql
SELECT status,
       COUNT(*) AS order_count,
       MAX(created_at) AS latest_order_at
FROM purchase_order
GROUP BY status;
```

Non-portable and usually invalid example:

```sql
SELECT status,
       customer_id,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY status;
```

One `status` group can contain many `customer_id`s; the database does not know which customer to choose. If statistics per customer are needed, add `customer_id` to `GROUP BY`. If only the count of distinct customers per status is needed, use `COUNT(DISTINCT customer_id)`.

Some databases offer extended functional-dependency rules or allow non-standard syntax, but do not rely on that behavior if the application must stay portable across engines.

## 7. `WHERE` vs. `HAVING`

`WHERE` filters rows before grouping. `HAVING` filters groups after aggregation.

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE created_at >= :fromTime
GROUP BY status
HAVING COUNT(*) >= :minimumOrders;
```

In this example:

1. `WHERE` keeps only orders from `fromTime` onward.
2. `GROUP BY` groups orders by status.
3. `COUNT(*)` computes the order count per group.
4. `HAVING` keeps only groups with at least `minimumOrders` orders.

Do not write `WHERE COUNT(*) >= ...` because aggregates have not been computed yet during the WHERE phase. If a condition does not depend on aggregates, prefer placing it in WHERE to reduce the number of rows processed.

## 8. Logical processing order of SELECT

You can visualize the common logical order as follows:

```text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY
    ↓
HAVING
    ↓
SELECT
    ↓
DISTINCT
    ↓
ORDER BY
    ↓
OFFSET / FETCH / LIMIT
```

Physical execution order is chosen by the optimizer, but logical order explains why aggregate aliases normally cannot be used in WHERE, why HAVING filters groups, and why LIMIT applies to result rows after grouping.

## 9. Order count and revenue statistics by status

Suppose revenue is computed from order lines:

```sql
SELECT o.status,
       COUNT(DISTINCT o.id) AS order_count,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS revenue
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
GROUP BY o.status
ORDER BY o.status;
```

`COUNT(DISTINCT o.id)` ensures each order is counted once across a one-to-many JOIN. Line totals are summed across line rows. If the query joins another collection such as payment attempts, line totals can be multiplied; pre-aggregate each collection before joining or run separate queries.

If `status` is an input filter, use a bind parameter instead of string concatenation:

```sql
WHERE o.status = :status
```

## 10. Tenant-scoped aggregation and protecting data boundaries

In multi-tenant applications, tenant filters must be applied before grouping:

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE tenant_id = :tenantId
GROUP BY status;
```

Do not simply group by `tenant_id` and return every group to the client. Queries must restrict results to the authenticated tenant. `tenantId` should come from the security context or server-side identity, never trusting an arbitrary value in a request.

If a report spans multiple tenants, the use case must enforce explicit authorization and limit permitted data. Aggregation does not make data inherently safe: summary statistics can still leak sensitive information if groups are tiny or filters are wrong.

## 11. Monthly total revenue

You can group by year and month. Date/time extraction syntax varies by database; PostgreSQL example:

```sql
SELECT DATE_TRUNC('month', o.created_at) AS month_start,
       COUNT(DISTINCT o.id) AS order_count,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS revenue
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
WHERE o.created_at >= :fromTime
  AND o.created_at < :toTime
GROUP BY DATE_TRUNC('month', o.created_at)
ORDER BY month_start;
```

`DATE_TRUNC` is a PostgreSQL function, not portable syntax across every database. MySQL, SQL Server, and Oracle have their own date/time functions and expressions. Separate queries by dialect if supporting multiple engines.

Prefer half-open time intervals `[fromTime, toTime)` to avoid boundary errors when columns store fractional seconds. For example, querying all of January uses the start of January inclusive to the start of February exclusive.

## 12. Grouping by day and time zones

Daily statistics depend on the business time zone. A single instant `2026-01-01T17:00:00Z` can fall on different calendar days in UTC versus a local time zone.

Before grouping by day, clarify:

- Does the column store UTC instants or local date-times?
- Are report days based on UTC or the tenant's time zone?
- Do day boundaries observe daylight saving time?
- How is the database session time zone configured?
- Does the trunc/extract function convert time zones before grouping?

When reporting in a tenant's time zone, you can convert instants to that time zone in SQL or calculate time boundaries in the application and filter with half-open intervals. The second approach often lets indexes on timestamp columns work better because the column is not wrapped inside a function in WHERE.

## 13. Conditional aggregation

Conditional aggregation computes multiple metrics in a single group scan using `CASE`:

```sql
SELECT tenant_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
       SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
FROM purchase_order
GROUP BY tenant_id;
```

You can sum revenue only from paid orders:

```sql
SELECT tenant_id,
       SUM(CASE WHEN status = 'PAID'
                THEN amount
                ELSE 0 END) AS paid_revenue
FROM order_summary
GROUP BY tenant_id;
```

`CASE` is generally more portable than database-specific aggregate filter extensions. In PostgreSQL, `FILTER (WHERE ...)` can also express conditional aggregates, but avoid it if a single SQL statement must work across multiple engines.

## 14. `COUNT(DISTINCT ...)` and distinct entity counts

To get the number of customers with orders per status:

```sql
SELECT status,
       COUNT(DISTINCT customer_id) AS unique_customers
FROM purchase_order
GROUP BY status;
```

`COUNT(DISTINCT)` can require extra CPU/memory or sort/hash steps to deduplicate. On large datasets, inspect execution plans and indexes. Never substitute `COUNT(*)` if business logic asks for unique entities.

For multiple distinct columns, distinct-tuple counting syntax varies across databases. For portability, you can use a subquery `SELECT DISTINCT col_a, col_b ...` and apply `COUNT(*)` in the outer query.

## 15. GROUP BY after JOIN: avoiding metric multiplication

A common reporting bug happens when joining multiple one-to-many relationships. Suppose an order has 3 lines and 2 payment records. Joining both collections creates 6 rows. `SUM(line_amount)` doubles and `COUNT(line.id)` gets multiplied by the payment count.

Do not patch this by sprinkling `DISTINCT` onto every aggregate without understanding cardinality. Pre-aggregate each child table first:

```sql
WITH line_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity * unit_price) AS order_total
    FROM order_line
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(amount) AS paid_amount
    FROM payment
    GROUP BY order_id
)
SELECT o.id,
       o.order_no,
       COALESCE(l.line_count, 0) AS line_count,
       COALESCE(l.order_total, 0) AS order_total,
       COALESCE(p.payment_count, 0) AS payment_count,
       COALESCE(p.paid_amount, 0) AS paid_amount
FROM purchase_order o
LEFT JOIN line_totals l ON l.order_id = o.id
LEFT JOIN payment_totals p ON p.order_id = o.id;
```

Each CTE has at most one row per `order_id`, so the JOIN does not multiply aggregates from the other collection. CTEs may be optimized or inlined depending on the database; what matters is controlling cardinality logic.

## 16. Aggregates with LEFT JOIN

When you want to keep parent groups that have no child rows, use `LEFT JOIN`:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id
GROUP BY c.id, c.display_name;
```

Customers without orders still appear with `order_count = 0`. If you used `COUNT(*)`, the customer row still produces a row after LEFT JOIN and the count would be 1. Always count a non-null column from the right-hand table, such as its primary key.

Conditions on the right-hand table must go in the right place. Writing:

```sql
WHERE o.status = 'PAID'
```

causes rows without orders to have `o.status = NULL` and get filtered out, effectively turning the LEFT JOIN into an INNER JOIN. To keep customers who have no paid orders, put the condition in `ON`:

```sql
LEFT JOIN purchase_order o
  ON o.customer_id = c.id
 AND o.status = 'PAID'
```

## 17. `HAVING` filters groups by aggregate values

Example showing only customers with at least 5 orders:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       MAX(created_at) AS latest_order_at
FROM purchase_order
GROUP BY customer_id
HAVING COUNT(*) >= :minimumOrders
ORDER BY order_count DESC;
```

`HAVING` fits conditions on totals, sums, or averages. Whenever source rows can be filtered with `WHERE`, do so before GROUP BY to shrink the aggregation workload.

Do not rely on referencing the alias `order_count` inside HAVING because support varies across databases. Repeat the aggregate expression or wrap the query in a subquery for better portability.

## 18. Subqueries and CTEs for multi-step reports

When a report needs filtering on aggregates, you can wrap GROUP BY in a subquery:

```sql
SELECT customer_id, order_count, total_spend
FROM (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_spend
    FROM order_summary
    WHERE created_at >= :fromTime
      AND created_at < :toTime
    GROUP BY customer_id
) customer_stats
WHERE order_count >= :minimumOrders
ORDER BY total_spend DESC;
```

CTEs (`WITH`) break a query into named steps:

```sql
WITH customer_stats AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_spend
    FROM order_summary
    GROUP BY customer_id
)
SELECT *
FROM customer_stats
WHERE total_spend >= :minimumSpend;
```

CTEs improve readability and allow reusing logic within one SQL statement, though they are not automatically faster than subqueries. The database optimizer determines the execution plan.

## 19. Statistical queries with `DatabaseClient`

`DatabaseClient` is a good fit for aggregate queries because you control SQL, aliases, and DTO mapping directly:

```java
public record StatusStatistics(
    String status,
    Long orderCount
) {}
```

```java
@Repository
public class OrderStatisticsRepository {

    private final DatabaseClient databaseClient;

    public OrderStatisticsRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<StatusStatistics> countByStatus(Long tenantId) {
        return databaseClient.sql("""
                SELECT status,
                       COUNT(*) AS order_count
                FROM purchase_order
                WHERE tenant_id = :tenantId
                GROUP BY status
                ORDER BY status
                """)
            .bind("tenantId", tenantId)
            .map((row, metadata) -> new StatusStatistics(
                row.get("status", String.class),
                row.get("order_count", Long.class)
            ))
            .all();
    }
}
```

Each group is emitted as an item of `Flux<StatusStatistics>`. There is no need to pull all `purchase_order` entities into the JVM to count them.

## 20. Mapping aggregate results and numeric types

The SQL type of an aggregate can differ from the source column type. For example:

| SQL expression | Common Java type |
|---|---|
| `COUNT(*)` | `Long` |
| `SUM(INTEGER)` | Often `Long`/numeric depending on database |
| `SUM(DECIMAL)` | `BigDecimal` |
| `AVG(DECIMAL)` | Usually `BigDecimal`, verify driver |
| `MIN(timestamp)` | Temporal type per driver/schema |
| `COUNT(DISTINCT ...)` | `Long` |

Do not force every aggregate into `Integer`, as table counts can overflow. For monetary amounts, use `BigDecimal`. For percentages or ratios, define explicit precision/scale and consider dialect-appropriate CASTs.

DTO example:

```java
public record RevenueStatistics(
    String status,
    Long orderCount,
    BigDecimal totalRevenue,
    BigDecimal averageOrderValue
) {}
```

Mapper:

```java
.map((row, metadata) -> new RevenueStatistics(
    row.get("status", String.class),
    row.get("order_count", Long.class),
    row.get("total_revenue", BigDecimal.class),
    row.get("average_order_value", BigDecimal.class)
))
```

If the driver does not directly map the returned type to the requested class, use a converter or read the actual driver type and convert safely. Never cast large integers down to `int` without overflow checks.

## 21. Using `@Query` in reactive repositories

For simple aggregates, SQL can live on a repository method:

```java
public record StatusStatistics(String status, Long orderCount) {}

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT status,
               COUNT(*) AS order_count
        FROM purchase_order
        WHERE tenant_id = :tenantId
        GROUP BY status
        ORDER BY status
        """)
    Flux<StatusStatistics> countByStatus(Long tenantId);
}
```

Spring Data R2DBC supports `@Query` declarations; how projections/DTOs are mapped depends on projection style, constructors, and the Spring Data version. Column names/aliases must align with the DTO's mapping convention. If a query has many calculations, complex aliases, or special nullable type handling, `DatabaseClient` with an explicit mapper gives clearer control.

Avoid cramming huge SQL statements into `@Query` on an interface if it hurts readability. You can extract a custom read repository into its own class.

## 22. `R2dbcEntityTemplate` and aggregate queries

`R2dbcEntityTemplate` is useful for queries driven by entity metadata, `Query`, `Criteria`, and CRUD operations. However, statistical queries involving `GROUP BY`, multiple aggregate expressions, CTEs, or specialized projections are usually clearer when written directly in SQL via `DatabaseClient`.

Example using Template for ordinary entity filtering:

```java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
);

Flux<Order> orders = template.select(query, Order.class).all();
```

This reads entities, not aggregates. If you follow it with `.collectList()` and sum totals in Java, the application has shifted aggregation work from the database into the JVM. Do that only for small datasets or specific business reasons; for large datasets, prefer SQL aggregation.

## 23. Conditional filters for reports

A report may filter by tenant, status, date range, and customer. Bind all values safely and avoid duplicating many nearly identical SQL statements unnecessarily.

Optional condition example:

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE tenant_id = :tenantId
  AND (:status IS NULL OR status = :status)
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY status;
```

The `(:status IS NULL OR status = :status)` pattern is easy to understand, though it can prevent optimizers from picking optimal indexes in some databases/plans. With many filter combinations, building dynamic SQL by appending only allowlisted conditions—while keeping every value bound as a parameter—is often clearer.

Never concatenate user input directly into SQL. Bind parameters protect values, not table or column names. If clients can select dynamic grouping or sorting fields, use a server-defined allowlist mapping.

## 24. Filtering time ranges with half-open intervals

For time-based reports, prefer:

```sql
WHERE created_at >= :fromTime
  AND created_at < :toTime
```

For example, March:

- `fromTime`: start of March, inclusive.
- `toTime`: start of April, exclusive.

Avoid constructing `23:59:59.999999` for the end day because timestamp precision varies across databases and drivers. Half-open intervals prevent missing boundary records.

If a column stores UTC instants while reports run in a local time zone, convert local day boundaries into instants before binding or perform time zone conversion in SQL per dialect. Never mix `LocalDateTime` and `Instant` without an explicit time zone policy.

## 25. Paginating GROUP BY results

When a query uses GROUP BY, `LIMIT`/`OFFSET` applies to the grouped result rows after `HAVING` filtering, not to the source rows.

Example:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(amount) AS total_spend
FROM order_summary
WHERE tenant_id = :tenantId
GROUP BY customer_id
HAVING SUM(amount) >= :minimumSpend
ORDER BY total_spend DESC, customer_id
LIMIT :limit OFFSET :offset;
```

Ordering must be deterministic. If multiple customers tie on `total_spend`, add `customer_id` as a tie-breaker. Without `ORDER BY`, group order is not guaranteed.

## 26. Counting total groups for pagination metadata

If an API needs total pages for statistical results, the count query must count groups after `HAVING`, not source rows.

Wrapped query example:

```sql
SELECT COUNT(*) AS total_groups
FROM (
    SELECT customer_id
    FROM order_summary
    WHERE tenant_id = :tenantId
    GROUP BY customer_id
    HAVING SUM(amount) >= :minimumSpend
) grouped_customers;
```

This is a common pitfall: `COUNT(*) FROM order_summary` counts orders, while the API returns one row per customer. Total groups must be calculated from the exact same filter, grouping, and having logic as the content query.

If you only need to know whether another page exists, fetch `limit + 1` groups and skip running an exact count. This is especially helpful for expensive aggregate reports.

## 27. Reactive composition for content and count

You can combine the content query and group-count query with `Mono.zip`:

```java
public Mono<StatisticsPage<CustomerStatistics>> findCustomerStats(
        Long tenantId, int limit, long offset) {

    Mono<List<CustomerStatistics>> content =
        findCustomerStatsContent(tenantId, limit, offset).collectList();

    Mono<Long> totalGroups = countCustomerStatsGroups(tenantId);

    return Mono.zip(content, totalGroups)
        .map(tuple -> new StatisticsPage<>(
            tuple.getT1(), tuple.getT2(), limit, offset));
}
```

`Mono.zip` subscribes to both publishers and can execute both queries concurrently. Because these are two separate statements, data may change between when content and count run. If both must observe the same snapshot, use an appropriate transaction/isolation level. For dashboards that tolerate slightly stale totals, consider caching the count or omitting exact totals.

## 28. Grouping sets, ROLLUP, and CUBE

Some databases support multi-level aggregations in one query:

- `ROLLUP`: generates subtotals along prefixes of the grouping key list plus a grand total.
- `CUBE`: generates aggregate combinations across all grouping keys.
- `GROUPING SETS`: specifies the exact grouping levels to produce.

Conceptual example:

```sql
SELECT tenant_id,
       status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY ROLLUP (tenant_id, status);
```

Results can contain `(tenant_id, status)` groups, `tenant_id` subtotals, and a grand total. Subtotal rows typically represent omitted grouping columns with `NULL`; use the `GROUPING(...)` function if supported by your database to distinguish subtotals from real NULL source data.

`ROLLUP`, `CUBE`, `GROUPING SETS`, and `GROUPING` vary in support and syntax across engines. Use them only if your target database supports and tests them; for portability, write multiple aggregate queries or combine with `UNION ALL` using explicit semantics.

## 29. Window functions vs. GROUP BY

`GROUP BY` collapses many rows into one row per group. Window functions compute aggregates over a window while keeping every source row intact.

Example calculating tenant total revenue while still returning each order:

```sql
SELECT id,
       tenant_id,
       amount,
       SUM(amount) OVER (PARTITION BY tenant_id) AS tenant_total
FROM order_summary;
```

The output still has one row per order, plus a `tenant_total` column. To rank orders within a tenant:

```sql
SELECT id,
       tenant_id,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY tenant_id
           ORDER BY amount DESC, id
       ) AS rank_in_tenant
FROM order_summary;
```

Window functions are helpful for rankings, running totals, moving averages, and top-N-per-group queries. Syntax and support depend on the database and version; separate by dialect when necessary.

## 30. Top N per group

Example retrieving the top 3 customers by revenue within each tenant:

```sql
WITH customer_revenue AS (
    SELECT tenant_id,
           customer_id,
           SUM(amount) AS total_spend
    FROM order_summary
    GROUP BY tenant_id, customer_id
), ranked AS (
    SELECT tenant_id,
           customer_id,
           total_spend,
           ROW_NUMBER() OVER (
               PARTITION BY tenant_id
               ORDER BY total_spend DESC, customer_id
           ) AS row_num
    FROM customer_revenue
)
SELECT tenant_id, customer_id, total_spend
FROM ranked
WHERE row_num <= :topN;
```

`ROW_NUMBER` assigns unique ranks; if you want to keep ties, consider `RANK` or `DENSE_RANK`. A tie-breaker inside `ROW_NUMBER` keeps results deterministic.

## 31. Indexes and aggregate query performance

Aggregate queries often read many rows. Appropriate indexes let the database filter inputs before grouping and reduce the amount of data scanned.

Query example:

```sql
SELECT status, COUNT(*)
FROM purchase_order
WHERE tenant_id = :tenantId
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY status;
```

A candidate index might be:

```sql
CREATE INDEX idx_order_tenant_created_status
ON purchase_order (tenant_id, created_at, status);
```

Column order depends on selectivity and query workload. If the database needs to group by status, a different index might help; do not guess from SQL alone. Inspect execution plans on representative data volumes.

Things to check:

- Is it doing a full table scan or an index scan?
- Do filters sharply reduce row counts before aggregation?
- Does the database use hash aggregate or sort aggregate?
- Does sorting spill to disk?
- Do JOINs produce excessive intermediate rows?
- Are cardinality estimates far off from actual row counts?
- Is an index-only scan possible?

Do not create indexes on every GROUP BY column. Indexes add write overhead and storage cost; base index choices on frequent queries and measurements.

## 32. Do not wrap filter columns in functions if you want index usage

Example:

```sql
WHERE DATE(created_at) = :reportDate
```

This can prevent normal indexes on `created_at` from being used efficiently because the database must evaluate the function on every column value. Instead, compute time boundaries in the application and use a half-open interval:

```sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
```

If daily grouping is needed, use the expression in `SELECT/GROUP BY` while keeping the range filter on the raw column so indexes remain usable. If queries filter by that expression very frequently, evaluate functional indexes or computed columns per database.

## 33. Approximate statistics and materialized summaries

For massive dashboards, exact aggregation over transactional tables can be too expensive. Options include:

- Short-lived caching of statistical results.
- Summary tables updated via batch jobs or events.
- Materialized views if supported by the database.
- A data warehouse/OLAP store for heavy reporting.
- Approximate distinct/count functions when business rules tolerate error margins.

Example daily/tenant/status summary table:

```sql
CREATE TABLE daily_order_stats (
    stat_date DATE NOT NULL,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(19, 4) NOT NULL,
    PRIMARY KEY (stat_date, tenant_id, status)
);
```

Dashboard APIs read the summary table instead of scanning every order and order line. However, you must design update mechanisms, duplicate-counting prevention, late-arriving event handling, rebuild procedures, and reconciliation against source data.

Approximate counts are inappropriate for quota enforcement, billing, or authorization checks where inaccuracies have business consequences. Keep approximate metrics distinct from exact figures.

## 34. Statistical data may have different consistency needs than CRUD

Dashboards often tolerate figures that lag by seconds or minutes; financial reports or reconciliations may require an exact snapshot. Define freshness and consistency requirements explicitly:

| Use case | Potentially suitable consistency level |
|---|---|
| Operational dashboard | Eventual consistency or short cache |
| Closed daily report | Finalized snapshot/summary |
| Fee calculation or billing | Exact per transaction/ledger and period-closing rules |
| Online display count | Acceptable if totals shift between requests |
| Quota check before writes | Requires transactions/locking or atomic guards; never rely on display counts |

Never use potentially stale statistical results to gate critical write operations without dedicated synchronization or atomic enforcement.

## 35. Testing aggregate queries with Testcontainers

Aggregate queries depend on SQL semantics and data types, so integration tests should run against the target database. Test fixtures should include:

- Multiple distinct groups.
- Single-row groups and multi-row groups.
- NULL values.
- Parents without children in LEFT JOINs.
- Multiple children to catch JOIN multiplication.
- Decimals with scales that must be preserved.
- Timestamps right near day/month boundaries.
- Different tenant/status filters.

Example test checking status statistics:

```java
@Test
void countsOrdersByStatus() {
    StepVerifier.create(orderStatisticsRepository.countByStatus(tenantId)
            .collectMap(StatusStatistics::status, StatusStatistics::orderCount))
        .assertNext(stats -> {
            assertThat(stats.get("PAID")).isEqualTo(2L);
            assertThat(stats.get("NEW")).isEqualTo(1L);
        })
        .verifyComplete();
}
```

Fixtures must be created before the test, and tenant IDs must be isolated. If result order matters, include `ORDER BY` in SQL and assert ordering rather than collecting solely into a map.

## 36. Testing `NULL`, LEFT JOIN, and cardinality

An essential test suite should verify:

1. Customer with no orders: `COUNT(order.id)` must be 0.
2. Order with no lines: line total must be 0 per contract.
3. Lines with nullable values: `COUNT(column)` differs from `COUNT(*)` as expected.
4. An order with multiple lines and multiple payments: line totals are not multiplied.
5. Multiple customers with identical totals: tie-breaker sorting works.
6. `HAVING` filters groups properly by aggregate values.
7. Total group count matches the row count of the unpaginated query.

Do not test only with a fixture containing one row per group. Double-counting bugs usually surface only when one-to-many relationships contain multiple records.

## 37. Testing numeric and temporal types

For `SUM(DECIMAL)` and `AVG`, tests should verify exact values with `BigDecimal`:

```java
assertThat(actual.totalRevenue())
    .isEqualByComparingTo(new BigDecimal("12345.6700"));
```

If scale is part of the contract, assert `scale()` as well. For ratios, define explicit rounding modes and decimal places.

For monthly/daily reports, test data at:

- Exactly the inclusive interval start.
- Exactly the exclusive interval end.
- Immediately before and after month boundaries.
- UTC instants mapping to different local calendar dates.
- Days involving DST transitions if applicable to the time zone.

Ensure tests run under the same time zone/session settings as production or pin time zones explicitly.

## 38. Common errors when writing statistical queries

| Symptom | Cause | Resolution |
|---|---|---|
| Count is higher than entity count | One-to-many JOIN multiplies rows | `COUNT(DISTINCT id)` or pre-aggregate before JOIN |
| Customers with no orders disappear | Used INNER JOIN | Use LEFT JOIN and count a non-null child column |
| Customers with no orders get count 1 | Used `COUNT(*)` after LEFT JOIN | Use `COUNT(child.id)` |
| Revenue totals are multiplied | Joined multiple collections | Pre-aggregate each collection or split queries |
| Aggregate returns NULL instead of 0 | No non-NULL inputs | Use `COALESCE` when business logic specifies 0 |
| AVG is skewed | Replaced NULL with 0 or divided by wrong count | Clarify which values belong in the average |
| HAVING does not filter properly | Placed aggregate condition in WHERE or relied on alias | Place condition after GROUP BY with HAVING/subquery |
| Total pages mismatch | Counted source rows instead of groups | Count from a subquery containing GROUP BY/HAVING |
| Report misses last-day data | Used BETWEEN with an imprecise end timestamp | Use half-open intervals `[from, to)` |
| Aggregate query is slow | Missing/unsuitable filters/indexes or heavy scans | Inspect execution plan and design indexes for the workload |
| DTO mapping error | Aggregate result type differs from column type | Check driver type; use Long/BigDecimal/converters |
| Tenant data leaks | Missing tenant filter/authorization | Obtain tenant from security context and bind filter |

## 39. Workflow for building a statistics endpoint

**Step 1 — Define metrics.** Document exact business formulas: counting orders vs. customers, gross vs. net revenue, handling of refunds/cancellations.

**Step 2 — Define grain.** Clarify whether each output row represents a tenant, status, customer, day, or combination.

**Step 3 — Define source dataset.** Choose time, tenant, status, and authorization filters prior to aggregation.

**Step 4 — Check JOIN cardinality.** List one-to-one/one-to-many relationships and check for row multiplication.

**Step 5 — Write aggregate SQL.** Apply `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY`, and `HAVING` with accurate semantics.

**Step 6 — Design the DTO.** Pick suitable Java types, especially `Long`, `BigDecimal`, and nullable wrappers.

**Step 7 — Choose the R2DBC API.** Use `@Query` for simple queries or `DatabaseClient` for complex projections/aggregates.

**Step 8 — Design pagination.** Paginate groups after GROUP BY; count groups or use a `limit + 1` slice.

**Step 9 — Optimize.** Inspect execution plans, indexes, range filters, and JOIN/aggregation costs.

**Step 10 — Test.** Use Testcontainers and fixtures covering nulls, cardinality, and time boundaries, verifying outputs against known independent data.

## 40. Conclusion

Aggregate queries and `GROUP BY` let the database turn large datasets into compact statistical results before sending data to the application. `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `COUNT(DISTINCT)`, and `HAVING` are the fundamental tools for building reports by tenant, status, customer, or time period. In Spring Data R2DBC, map aggregate rows into DTOs/projections via `DatabaseClient` or suitable query methods instead of loading full entities and computing summaries in the JVM.

The essentials are defining the right group grain, understanding `NULL`, choosing accurate numeric types, and controlling JOIN cardinality. In particular, joining multiple one-to-many relationships multiplies metrics; pre-aggregate each collection or split queries. When paginating, count groups after `GROUP BY`/`HAVING`, and design filters and indexes around real workloads. Combining integration tests on the target database with execution-plan analysis keeps statistical metrics accurate, tenant-safe, and performant as data grows.
