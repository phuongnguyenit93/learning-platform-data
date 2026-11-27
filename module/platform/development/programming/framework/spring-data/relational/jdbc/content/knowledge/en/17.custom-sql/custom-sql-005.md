# JOINs, Subqueries, Aggregations, and Window Functions in Custom SQL

**Spring Data JDBC** provides repositories to save and load aggregates, without restricting the application to auto-generated CRUD operations. When business logic requires combining multiple tables, filtering by the result of another query, computing totals, or ranking data, you can write custom SQL using `@Query`, `JdbcTemplate`, or `NamedParameterJdbcTemplate`.

This lesson focuses on four groups of SQL techniques commonly used in Spring Data Relational JDBC applications:

- **JOINs** combine data from multiple tables.
- **Subqueries** use the result of one query inside another query.
- **Aggregate functions** such as `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` summarize multiple rows.
- **Window functions** such as `ROW_NUMBER`, `RANK`, `LAG`, and `SUM() OVER` compute across a group of rows while keeping each individual row in the result.

We will use an order system as a running example. Repositories continue managing aggregate roots; read queries with JOINs or reporting results can return dedicated DTOs. SQL must be parameterized, results need deterministic ordering when paginating, and statements should be verified against the application's actual database.

## 1. Data context and query tools

Suppose the application has three tables:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_lines_quantity CHECK (quantity > 0)
);
~~~

An order has multiple order lines. In the domain, `PurchaseOrder` can be the aggregate root, while `OrderLine` is a child entity. `Customer` is an independent aggregate and the order holds a `customerId` reference.

Depending on the need, the application can use three approaches:

| Tool | Usage | Suitable when |
|---|---|---|
| Derived query in repository | Name method by properties | Simple filtering, few conditions |
| `@Query` on repository | Write explicit SQL in the repository | Queries tied to the repository with compatible result mapping |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Write SQL and map results manually | Complex JOINs, reporting DTOs, aggregate functions, window functions |

You do not need a separate repository for every table just to write a JOIN. Repositories represent aggregate access gates; a DAO/query service can serve a separate read model.

## 2. JOIN: combining data from multiple tables

JOINs use conditions to link rows across two or more tables. In the example, `purchase_orders.customer_id` points to `customers.id`, and `order_lines.order_id` points to `purchase_orders.id`.

### 2.1. INNER JOIN

`INNER JOIN` returns only rows with matching linked pairs satisfying the condition:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.status,
    c.display_name AS customer_name
FROM purchase_orders o
INNER JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'SUBMITTED'
ORDER BY o.created_at DESC, o.id DESC;
~~~

Every order with a matching customer appears in the result. If an order had an invalid customer reference, it would not appear with INNER JOIN; in schemas with foreign keys, this case is normally prevented when writing data.

### 2.2. LEFT JOIN

`LEFT JOIN` keeps all rows from the left table, even when there is no matching row in the right table:

~~~sql
SELECT
    o.id,
    o.order_number,
    c.display_name AS customer_name
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
ORDER BY o.id;
~~~

If no customer is found, the columns of `c` have `NULL` values. This is useful when linked data is optional or a report still needs to display left-side rows despite missing right-side data.

A common mistake is placing a filter condition for the right-side table in `WHERE`:

~~~sql
SELECT o.id, c.display_name
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.display_name LIKE 'An%';
~~~

The `WHERE c.display_name ...` condition eliminates rows where `c.display_name IS NULL`, effectively turning the result into an INNER JOIN. To keep all orders while only joining customers whose name starts with "An", move the condition into `ON`:

~~~sql
SELECT o.id, c.display_name
FROM purchase_orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
   AND c.display_name LIKE 'An%';
~~~

### 2.3. JOIN with a one-to-many child table

Fetching each order and its lines:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.product_id,
    l.quantity,
    l.unit_price
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY o.id, l.id;
~~~

If an order has three lines, the result has three rows sharing the same `order_id`. This is the natural cardinality of a one-to-many relationship. Never assume each result row corresponds to a unique aggregate root.

This matters when mapping DTOs. If the screen needs one row per order, use GROUP BY, a pre-aggregating subquery, or a separate query. If you need a list of order lines, let each result row represent a line.

### 2.4. Avoiding row multiplication when JOINing multiple collections

Suppose each order has multiple order lines and multiple payments. Joining both child tables directly:

~~~sql
SELECT o.id, l.id AS line_id, p.id AS payment_id
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id;
~~~

If an order has 3 order lines and 2 payments, the result can have 3 × 2 = 6 rows. Then `SUM(l.quantity * l.unit_price)` can be multiplied because each order line appears alongside every payment.

The usual fix is to aggregate each child table first and then JOIN:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.id,
    COALESCE(l.order_total, 0) AS order_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM purchase_orders o
LEFT JOIN line_totals l ON l.order_id = o.id
LEFT JOIN payment_totals p ON p.order_id = o.id;
~~~

Each CTE returns at most one row per order, so the JOIN does not duplicate the computed totals. CTEs and derived tables are useful tools for separating aggregation steps.

## 3. Subqueries: using a query inside a query

A subquery is a SELECT statement nested inside another SQL statement. It can return a single value, a set of values, or a temporary table for the outer query to use.

### 3.1. Scalar subquery

A scalar subquery returns a single value, such as an order's total amount:

~~~sql
SELECT
    o.id,
    o.order_number,
    (
        SELECT COALESCE(SUM(l.quantity * l.unit_price), 0)
        FROM order_lines l
        WHERE l.order_id = o.id
    ) AS order_total
FROM purchase_orders o
WHERE o.status = 'SUBMITTED';
~~~

The subquery references `o.id` from the outer query, making it a **correlated subquery**. It clearly expresses the sum calculation per order. The database may optimize this query in its own way; check the execution plan when order volume is large.

### 3.2. EXISTS and NOT EXISTS

`EXISTS` checks whether at least one row satisfies a condition:

~~~sql
SELECT o.id, o.order_number
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.quantity >= 5
);
~~~

This query returns orders that have at least one line with quantity 5 or greater. Without joining all lines into the result, each order appears only once.

`NOT EXISTS` finds orders with no order lines:

~~~sql
SELECT o.id, o.order_number
FROM purchase_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
);
~~~

For "at least one" or "none at all" questions, EXISTS usually expresses the intent more clearly than JOIN combined with DISTINCT.

### 3.3. IN with a subquery

`IN` checks whether a value belongs to the set returned by a subquery:

~~~sql
SELECT id, order_number
FROM purchase_orders
WHERE customer_id IN (
    SELECT id
    FROM customers
    WHERE display_name LIKE 'Nguyen%'
);
~~~

The result contains orders belonging to customers with matching names. In this example, an INNER JOIN could be used instead; the choice depends on which columns are needed from the customer table and which query reads more clearly.

### 3.4. NOT IN and NULL

Be careful when `NOT IN` can receive a set of values containing `NULL`:

~~~sql
SELECT id
FROM customers
WHERE id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
~~~

If the result set contains NULL, SQL three-valued logic can cause the condition to return zero rows contrary to expectations. When the column can be NULL, `NOT EXISTS` is usually safer and clearer:

~~~sql
SELECT c.id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers b
    WHERE b.customer_id = c.id
);
~~~

### 3.5. Derived tables and CTEs

A subquery in the FROM clause forms a derived table:

~~~sql
SELECT totals.order_id, totals.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
) totals
WHERE totals.order_total >= 1000000;
~~~

A CTE (`WITH`) gives a name to an intermediate query result:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_lines
    GROUP BY order_id
)
SELECT o.order_number, t.total_amount
FROM purchase_orders o
JOIN order_totals t ON t.order_id = o.id
WHERE t.total_amount >= 1000000;
~~~

CTEs are helpful when a query has multiple steps, needs named intermediate calculations, or reuses logic within the same SQL statement. Depending on the DBMS, a CTE may be inlined or materialized; do not assume it always creates a physical temporary table.

## 4. Aggregate functions: summarizing multiple rows

Aggregate functions compute a single value from multiple rows. Common functions:

| Function | Meaning | Example |
|---|---|---|
| `COUNT(*)` | Counts rows | Number of orders |
| `COUNT(column)` | Counts non-NULL values | Number of lines with product_id |
| `SUM(expression)` | Computes sum | Total revenue |
| `AVG(expression)` | Computes average | Average order value |
| `MIN(expression)` | Minimum value | Earliest order date |
| `MAX(expression)` | Maximum value | Latest order date |

### 4.1. GROUP BY

Count orders by status:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM purchase_orders
GROUP BY status
ORDER BY status;
~~~

Total revenue by customer:

~~~sql
SELECT
    o.customer_id,
    SUM(l.quantity * l.unit_price) AS revenue
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
GROUP BY o.customer_id
ORDER BY revenue DESC;
~~~

`GROUP BY` groups rows sharing the same values in the grouping columns, then computes aggregate functions for each group.

### 4.2. HAVING vs. WHERE

`WHERE` filters rows **before grouping**. `HAVING` filters groups **after aggregation**:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM purchase_orders
WHERE created_at >= :fromTime
GROUP BY customer_id
HAVING COUNT(*) >= 3
ORDER BY order_count DESC;
~~~

In this example, only orders from `fromTime` onward participate in grouping; afterward, only customers with at least three orders in that period are kept.

Do not use `WHERE COUNT(*) >= 3` because aggregate functions cannot be filtered that way in a same-level WHERE clause. Use HAVING.

### 4.3. COUNT(*) vs. COUNT(column) with LEFT JOIN

Consider this query:

~~~sql
SELECT
    o.id,
    COUNT(*) AS joined_rows,
    COUNT(l.id) AS line_count
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id;
~~~

For an order with no lines, LEFT JOIN still produces one result row with NULL values for `l.*` columns. Therefore `COUNT(*)` returns 1, while `COUNT(l.id)` returns 0. When counting elements on the right side of a LEFT JOIN, count a non-null key column of the child table.

### 4.4. COALESCE and NULL handling

`SUM` over a set with no values can return NULL. If you want the sum to be 0:

~~~sql
SELECT
    o.id,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id;
~~~

`COALESCE(a, b, ...)` returns the first non-NULL value. It is useful for read models, but choose replacement values that fit business semantics; not every NULL should become 0 or an empty string.

### 4.5. DISTINCT and COUNT DISTINCT

A one-to-many JOIN can make a customer appear multiple times. Count distinct customers with orders:

~~~sql
SELECT COUNT(DISTINCT customer_id) AS active_customer_count
FROM purchase_orders
WHERE created_at >= :fromTime;
~~~

`DISTINCT` removes duplicate values before counting. However, do not use DISTINCT to mask a wrong-cardinality JOIN when the goal is summing amounts; model the relationships and grouping properly.

## 5. Window functions: computing across groups while keeping individual rows

Aggregate functions with GROUP BY collapse each group into one row. **Window functions** compute across a window of related rows while preserving each input row in the result.

General structure:

~~~sql
function_name(expression) OVER (
    PARTITION BY grouping_columns
    ORDER BY ordering_columns
    window_frame
)
~~~

- `PARTITION BY` divides the result into independent partitions.
- `ORDER BY` determines the order inside each partition.
- The window frame defines the range of rows the function evaluates at each position.

### 5.1. ROW_NUMBER: numbering rows

Number orders chronologically per customer:

~~~sql
SELECT
    customer_id,
    id AS order_id,
    order_number,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC, id DESC
    ) AS row_num
FROM purchase_orders;
~~~

Each customer gets a sequence starting from 1. `id DESC` serves as a tie-breaker so the result is deterministic when two orders share the same creation timestamp.

### 5.2. Fetching the latest order per customer

Window functions can be combined with a CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, id DESC
        ) AS rn
    FROM purchase_orders o
)
SELECT id, customer_id, order_number, status, created_at
FROM ranked_orders
WHERE rn = 1;
~~~

The result keeps only the latest order for each customer. You cannot place `WHERE rn = 1` at the same query level as the window expression in many SQL engines because WHERE is evaluated before window functions; wrap it in a CTE or subquery to filter the computed values.

### 5.3. RANK and DENSE_RANK

Rank customers by revenue:

~~~sql
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        SUM(l.quantity * l.unit_price) AS revenue
    FROM purchase_orders o
    JOIN order_lines l ON l.order_id = o.id
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_revenue_rank
FROM customer_revenue
ORDER BY revenue DESC;
~~~

Difference:

| Revenue | RANK | DENSE_RANK |
|---:|---:|---:|
| 900000 | 1 | 1 |
| 750000 | 2 | 2 |
| 750000 | 2 | 2 |
| 500000 | 4 | 3 |

`RANK` leaves gaps after ties. `DENSE_RANK` leaves no gaps.

### 5.4. SUM OVER: running totals

Compute running revenue over time:

~~~sql
SELECT
    o.id,
    o.created_at,
    SUM(l.quantity * l.unit_price) AS order_total,
    SUM(SUM(l.quantity * l.unit_price)) OVER (
        ORDER BY o.created_at, o.id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.created_at
ORDER BY o.created_at, o.id;
~~~

The query first groups order lines into per-order totals, then the window function accumulates those order totals in order. The window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` specifies summing from the first row up to the current row.

To compute a running total separately per customer, add `PARTITION BY o.customer_id`.

### 5.5. LAG and LEAD: comparing previous/next rows

`LAG` reads a value from a preceding row in the window; `LEAD` reads from a following row:

~~~sql
SELECT
    customer_id,
    id AS order_id,
    created_at,
    LAG(created_at) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, id
    ) AS previous_order_at,
    LEAD(created_at) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, id
    ) AS next_order_at
FROM purchase_orders;
~~~

Applications can calculate intervals between orders, find previous/next orders, or analyze event sequences. The first row with no preceding row receives NULL from LAG unless a default value is supplied.

### 5.6. Window frames and ordering

When using aggregate functions like `SUM` inside OVER, understand the frame. If you only write:

~~~sql
SUM(amount) OVER (ORDER BY created_at)
~~~

the default window frame rule may group peers sharing the same sort key value, depending on the SQL dialect. If you want a row-by-row running total, explicitly specify `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` and include a unique secondary key in ORDER BY.

Do not confuse:

- `ORDER BY` inside OVER determines how the window function evaluates rows.
- `ORDER BY` at the end of SELECT determines the order of rows returned to the client.

If a deterministic display order is needed, you still need an outer ORDER BY.

## 6. Combining custom SQL with Spring Data JDBC

Spring Data JDBC can execute SQL via repositories or Spring JDBC. The choice depends on result mapping and query complexity.

### 6.1. Using `@Query` for repository-scoped queries

Example repository finding orders by status:

~~~java
package com.example.orders.repository;

import java.util.List;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, order_number, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<PurchaseOrder> findByStatusSql(
        @Param("status") String status
    );
}
~~~

This example assumes `PurchaseOrder` mapping has properties matching the selected columns. If the aggregate has child collections, a custom query returning the root does not automatically mean child tables will be loaded identically to calling `findById`; clarify the result type and aggregate-loading behavior for your version. For reporting-only queries, DTOs via Spring JDBC are often more transparent.

### 6.2. Using `@Query` for update statements

For data-modifying SQL, Spring Data JDBC supports `@Modifying`:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :newStatus
    WHERE id = :id
    """)
int updateStatus(
    @Param("id") Long id,
    @Param("newStatus") String newStatus
);
~~~

`@Modifying` marks a data-modifying query; the `int` return type reports the number of affected rows. This is a direct SQL update that can bypass domain methods and aggregate persistence mechanisms such as optimistic locking unless handled explicitly. Do not use this style of query to arbitrarily replace repository `save()` when invariants must be protected.

### 6.3. Using `NamedParameterJdbcTemplate` for DTOs and JOINs

For reporting results, a dedicated DAO is often easier to control:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        LocalDateTime createdAt,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

DAO:

~~~java
package com.example.orders.read;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReportDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReportDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findSummaries(
            LocalDateTime from,
            LocalDateTime to) {

        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.display_name AS customer_name,
                o.status,
                o.created_at,
                COUNT(l.id) AS line_count,
                COALESCE(
                    SUM(l.quantity * l.unit_price),
                    0
                ) AS total_amount
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE o.created_at >= :fromTime
              AND o.created_at < :toTime
            GROUP BY
                o.id,
                o.order_number,
                c.display_name,
                o.status,
                o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """;

        Map<String, Object> params = Map.of(
            "fromTime", from,
            "toTime", to
        );

        return jdbc.query(sql, params, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

The DAO maps each SQL row into `OrderSummary`. The data contains only the columns needed by the screen; there is no intention of calling `save()` on this DTO.

### 6.4. Using window functions in a DAO

Example fetching the three latest orders per customer:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.order_number,
        o.status,
        o.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS rn
    FROM purchase_orders o
)
SELECT
    id,
    customer_id,
    order_number,
    status,
    created_at
FROM ranked_orders
WHERE rn <= :limitPerCustomer
ORDER BY customer_id, created_at DESC, id DESC;
~~~

The DAO can pass `limitPerCustomer` via a named parameter. This is a data value, not a column name or concatenated SQL fragment.

Window functions execute in the database, so the application does not have to load all orders into Java to group and sort per customer. However, verify that the target database supports the window function syntax used.

## 7. Parameterizing SQL and preventing SQL injection

Every value supplied by users or external systems must be bound through parameters:

~~~java
String sql = """
    SELECT id, order_number
    FROM purchase_orders
    WHERE status = :status
      AND created_at >= :fromTime
    """;

Map<String, Object> params = Map.of(
    "status", requestedStatus,
    "fromTime", fromTime
);

List<Map<String, Object>> rows = jdbc.queryForList(sql, params);
~~~

Never concatenate values directly into SQL:

~~~java
// UNSAFE:
String sql = "SELECT * FROM purchase_orders WHERE status = '"
    + requestedStatus + "'";
~~~

Parameter binding protects data values and lets the driver handle types properly. However, parameters **cannot substitute table names, column names, or SQL keywords**. If dynamic sorting is needed, use an allowlist:

~~~java
String orderBy = switch (requestedSort) {
    case "created" -> "created_at";
    case "number" -> "order_number";
    case "status" -> "status";
    default -> "created_at";
};

String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    ORDER BY
    """ + orderBy + " DESC, id DESC";
~~~

The concatenation above only uses values taken from a fixed allowlist in code. Never concatenate `requestedSort` directly from the request into SQL. Similarly, ASC/DESC direction must be validated against an allowed set of values.

## 8. Pagination, sorting, and deterministic results

For reports with many rows, paginate at the database:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

The order includes secondary key `id` for stability when multiple orders share the same `created_at`. Without a deterministic ORDER BY, the database does not guarantee the same order across runs.

Large OFFSET values can be expensive because the database has to skip many rows. For large lists, consider keyset pagination:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The client sends a cursor consisting of the timestamp and ID from the last row of the previous page. A suitable composite index can make fetching the next page more efficient. Handle timezone and timestamp precision consistently between the database and application.

## 9. Choosing JOIN, subquery, GROUP BY, or window functions

| Need | Typically suitable technique | Example |
|---|---|---|
| Fetch customer name along with order | JOIN | `purchase_orders JOIN customers` |
| Only check whether an order has lines | EXISTS | At least one `order_lines` row |
| Get total amount per order | GROUP BY or scalar subquery | `SUM(quantity * unit_price)` |
| Filter groups by count | HAVING | Customers with at least 3 orders |
| Fetch latest order per customer | ROW_NUMBER + CTE | `rn = 1` |
| Rank by revenue | RANK/DENSE_RANK | Top customers |
| Compute running totals | SUM OVER | Cumulative revenue by date |
| Compare with previous row | LAG | Interval between two purchases |
| Read multi-table DTO | JdbcTemplate DAO | Order list report |

No single technique is always best. Choose SQL that accurately reflects relationships and cardinality, is easy to maintain, and then measure performance against realistic data.

## 10. Query optimization and checking execution plans

A short SQL query is not guaranteed to be fast. Key factors include:

- Number of rows read and returned.
- Indexes on JOIN, WHERE, and ORDER BY columns.
- Selectivity of filter predicates.
- Cardinality of one-to-many relationships.
- Cost of sorting, grouping, and window partitioning.
- Result payload size and number of round-trips between application and database.

Illustrative indexes for the queries above:

~~~sql
CREATE INDEX idx_orders_status_created
    ON purchase_orders(status, created_at, id);

CREATE INDEX idx_orders_customer_created
    ON purchase_orders(customer_id, created_at, id);

CREATE INDEX idx_lines_order
    ON order_lines(order_id);
~~~

These are only examples. Column order in a composite index should match actual filter predicates and sort orders. Every index increases storage and INSERT/UPDATE/DELETE overhead, so do not index every column blindly.

Use your database's execution plan tool, such as `EXPLAIN` or `EXPLAIN ANALYZE` where supported. Check:

1. Does the database use the expected index?
2. Is there a full table scan on a large table?
3. Does a JOIN produce an unexpected number of intermediate rows?
4. Do GROUP BY or ORDER BY require an expensive sort?
5. Does a window partition process an excessively large dataset?
6. Are row estimates far off from actual row counts?

Do not apply the exact same `EXPLAIN ANALYZE` syntax across every database; consult the documentation and tools of your running DBMS.

## 11. SQL differences across database management systems

Spring Data JDBC does not make every SQL statement portable. The following features can vary:

- Pagination syntax (`LIMIT/OFFSET`, `FETCH FIRST`, `TOP`).
- Timestamp, UUID, and decimal data types.
- String concatenation, NULL handling, and type casting.
- Support for recursive CTEs or window frames.
- Function names, JSON syntax, and date/time functions.
- Identifier quoting rules and column name case sensitivity.

JOIN, GROUP BY, and many window functions are widely available in modern databases, though you should still verify the target database version. If the application supports multiple databases, keep SQL isolated in replaceable components, run integration tests on each supported DBMS, and avoid relying on vendor-specific syntax unnecessarily.

## 12. Common mistakes

| Symptom | Cause | How to fix |
|---|---|---|
| One order appears multiple times after JOIN | One-to-many relationship multiplies rows | GROUP BY, subquery, or EXISTS depending on goal |
| Total amount is larger than actual | Joining multiple collections multiplies lines | Aggregate each child table before JOINing |
| LEFT JOIN drops rows without matches | Filter on right table placed in WHERE | Move the appropriate condition into ON |
| Order with no lines counted as 1 | Using COUNT(*) after LEFT JOIN | Use COUNT(child.id) |
| WHERE throws an error on COUNT/SUM | Filtering aggregates at the wrong stage | Use HAVING |
| NOT IN returns unexpected results | Subquery contains NULL | Use NOT EXISTS or filter NULLs explicitly |
| Window function cannot be filtered in same-level WHERE | Window functions are evaluated after WHERE | Wrap the query in a CTE or subquery |
| Paginated result order changes | ORDER BY lacks a stable secondary key | Add a unique column to the ordering |
| SQL injection in filters/sorting | Concatenating input into SQL | Bind values and allowlist identifiers |
| DTO missing or has wrong columns | Aliases and RowMapper do not match | Define clear aliases and map by name |
| Query slows down as data grows | Missing indexes or high cardinality | Inspect execution plan and optimize for workload |

## 13. Practice exercises

### Exercise 1 — JOIN and DTO

1. JOIN orders with customers to return order number, customer name, and status.
2. Add a LEFT JOIN with order lines.
3. Count the number of lines per order.
4. Create an `OrderSummary` DTO and map it using `NamedParameterJdbcTemplate`.
5. Create an order with no lines and verify `lineCount` is 0.

### Exercise 2 — Subqueries and EXISTS

1. Find orders with at least one line of quantity greater than 5 using EXISTS.
2. Find orders with no lines using NOT EXISTS.
3. Rewrite the first query using JOIN.
4. Compare the row counts and semantics when an order has multiple matching lines.

### Exercise 3 — Aggregations

1. Calculate the total amount per order.
2. Calculate revenue per customer.
3. Keep only customers with revenue above a threshold using HAVING.
4. Compare COUNT(*) and COUNT(line.id) when using LEFT JOIN.
5. Add COALESCE for orders with no lines.

### Exercise 4 — Window functions

1. Use ROW_NUMBER to number orders per customer.
2. Use a CTE to fetch the latest order per customer.
3. Use RANK and DENSE_RANK to rank customers by revenue.
4. Use SUM OVER to compute a daily running total.
5. Use LAG to get each customer's previous purchase date.

### Exercise 5 — Performance and stability

1. Generate a sufficiently large test dataset.
2. Run queries with and without appropriate indexes.
3. Inspect execution plans.
4. Paginate with OFFSET and keyset pagination.
5. Add rows sharing the same timestamp and verify ORDER BY with a secondary key gives deterministic results.

## 14. Principles for applying custom SQL in Spring Data JDBC

When writing custom SQL, keep clear boundaries:

- **Commands and aggregate mutations:** load the root, invoke domain behavior, and save via the repository when invariants must be protected.
- **Specialized read queries:** use JOINs, subqueries, aggregate functions, or window functions to return suitable DTOs.
- **Direct modifying SQL:** use `@Modifying` or Spring JDBC when there is a specific reason; understand that such statements may bypass aggregate lifecycle and optimistic locking.
- **Parameters:** bind values; allowlist column names and sort directions if dynamic.
- **Performance:** check cardinality, indexes, execution plans, and result sizes.
- **Portability:** verify syntax against the actual database and version.

## 15. Conclusion

JOINs combine data across tables; subqueries reuse the output of another query; aggregate functions summarize multiple rows into aggregated values; window functions compute across groups while retaining row-level detail. These are essential tools for writing custom SQL queries in Spring Data JDBC applications.

Use `@Query` for repository-bound SQL with compatible result mapping; use `JdbcTemplate` or `NamedParameterJdbcTemplate` for JOINs, reports, and complex DTOs. Always understand cardinality to avoid row and sum multiplication, use HAVING for group conditions, handle NULLs carefully, and specify deterministic ordering when paginating.

Repositories remain the aggregate gateway for write use cases. Custom SQL extends read and aggregation capabilities without forcing every query result to become a saveable aggregate.
