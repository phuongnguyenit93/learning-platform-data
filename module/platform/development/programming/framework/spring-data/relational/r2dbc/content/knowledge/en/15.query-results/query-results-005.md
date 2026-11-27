# Mapping Join or Aggregate Results into Dedicated Read Models

A business query often needs data from multiple tables or aggregated values. For example, an order list screen may display the customer name, line item count, and total amount; a customer report may display the number of orders placed and total revenue. These results do not necessarily correspond to a single entity in the write model.

In Spring Data R2DBC, you can use `DatabaseClient` to execute SQL joins or aggregates, then map each result row into a DTO/projection dedicated to reading. This read model supplies the API with the exact data needed without building a large entity object graph or calling multiple repositories sequentially.

Keep in mind that a SQL join can return multiple rows for the same parent record, aggregates change the shape of the data, and `LEFT JOIN` can introduce null columns. DTO design and mapping must accurately reflect cardinality, column aliases, data types, and the meaning of each value.

## 1. Why Do We Need a Dedicated Read Model?

Entities typically reflect the data and update rules of an aggregate. Meanwhile, a screen or report often needs a different data shape:

- An order list needs the order number, customer name, status, and total amount.
- An order details page needs order information along with the list of line items.
- A dashboard needs order count, revenue, and average order value per day.
- An admin screen needs to combine data from multiple aggregates strictly for reading.

Trying to force entities into all these cases can cause the application to load unnecessary properties, run repetitive queries, or blur aggregate boundaries. A dedicated read DTO lets you clearly define the data for each use case.

Example:

```java
public record OrderSummary(
    Long orderId,
    String orderNo,
    String status,
    String customerName,
    BigDecimal totalAmount,
    Long lineCount
) {}
```

`OrderSummary` is a read model, not an entity to persist to a single table. It combines fields from `purchase_order`, `customer`, and `order_line` to serve a list screen.

## 2. Distinguishing Entity, Projection, and Read Model

| Concept | Purpose | Example |
|---|---|---|
| Entity | Represents data mapped to a table and participates in write operations | `PurchaseOrder`, `Customer` |
| Projection | Selects a subset of fields from a query result | `OrderSummary` with only ID, status, and total |
| Read model | Complete data shape for a read use case | Order along with customer, line count, and statistics |

A projection is often a small DTO; a read model can contain nested projections or aggregated data. Both can be built directly from SQL without being managed as entities.

Spring Data R2DBC is not an ORM with a persistence context like JPA/Hibernate. When querying joins, do not expect the framework to automatically load and assemble an entire entity relationship graph or perform lazy loading. Explicitly express the SQL and required result mapping.

## 3. Designing the DTO Before Writing the Join Query

First identify which fields the use case needs to return, which table each field comes from, and whether it can be null.

Suppose we have the following tables:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    status VARCHAR(30) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL
);
```

For an order list screen, the DTO could be:

```java
public record OrderSummary(
    Long orderId,
    String orderNo,
    String status,
    String customerName,
    BigDecimal totalAmount,
    Long lineCount
) {}
```

Each field is clearly accounted for:

- `orderId`, `orderNo`, `status`, and `totalAmount` come from `purchase_order`.
- `customerName` comes from `customer`.
- `lineCount` is an aggregate value computed from `order_line`.

Designing the DTO first ensures the SQL selects only needed columns and gives mapping a clear contract. If a field might not exist—such as a customer name from a `LEFT JOIN`—the DTO's data types and null rules must reflect that.

## 4. Using `INNER JOIN` and `LEFT JOIN` with the Right Semantics

`INNER JOIN` returns rows only when both sides have matching records. `LEFT JOIN` preserves all rows on the left side and returns null for right-side columns when no matching record exists.

Example order list where a valid customer always exists:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
INNER JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC;
```

If you want to preserve orders even when customer information might be missing or the relationship is nullable, use `LEFT JOIN`:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
LEFT JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status;
```

With `LEFT JOIN`, `customer_name` can be null. If the DTO uses a record, a reference type like `String` can hold null; do not use primitive types for nullable columns. Decide at the read layer whether to keep null, substitute a default display value, or filter out such rows.

A common mistake is placing a filter on the right-hand table inside `WHERE` after a `LEFT JOIN`:

```sql
-- This condition filters out rows with no matching customer,
-- making the result behave almost like an INNER JOIN.
SELECT o.id, c.display_name
FROM purchase_order o
LEFT JOIN customer c ON c.id = o.customer_id
WHERE c.status = 'ACTIVE';
```

If you want to keep all orders while only matching active customers, put the condition in the `ON` clause:

```sql
SELECT o.id, c.display_name
FROM purchase_order o
LEFT JOIN customer c
    ON c.id = o.customer_id
   AND c.status = 'ACTIVE';
```

Where the condition is placed can dramatically change the result. Identify which table is the preserved side before choosing the join type.

## 5. Mapping Join Results with `DatabaseClient`

`DatabaseClient` lets you execute SQL and map each `Row` into the desired Java type. Example fetching an order list with customer names:

```java
public Flux<OrderSummary> findOrderSummaries(String status) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   c.display_name AS customer_name,
                   o.total_amount,
                   COUNT(ol.id) AS line_count
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            LEFT JOIN order_line ol ON ol.order_id = o.id
            WHERE o.status = :status
            GROUP BY o.id, o.order_no, o.status,
                     c.display_name, o.total_amount, o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("customer_name", String.class),
            row.get("total_amount", BigDecimal.class),
            row.get("line_count", Long.class)
        ))
        .all();
}
```

In this example:

1. `JOIN customer` retrieves the customer name.
2. `LEFT JOIN order_line` keeps orders that have no line items yet.
3. `COUNT(ol.id)` counts actual line items.
4. `GROUP BY` groups rows by order to return one summary row per order.
5. Aliases like `order_id`, `customer_name`, and `line_count` provide stable column names for the mapper.
6. `map(...)` converts each result row into an `OrderSummary`.

`COUNT(ol.id)` is used instead of `COUNT(*)` because `LEFT JOIN` still produces a result row with null `ol` columns when an order has no lines. `COUNT(*)` would count that null-extended row as 1, whereas `COUNT(ol.id)` ignores null values and returns 0.

The example assumes `COUNT` returns a large integer type; the exact Java type must match the driver. In PostgreSQL, `COUNT(*)` is typically mapped to `Long`. For other data types or drivers, verify the return type with integration tests.

## 6. Using Aliases to Avoid Column Name Collisions

When joining multiple tables, tables often share column names such as `id`, `status`, `created_at`, or `name`. Without aliases, calling `row.get("id")` can be ambiguous or read the wrong column.

Use aliases aligned with the DTO's semantics:

```sql
SELECT o.id AS order_id,
       c.id AS customer_id,
       o.status AS order_status,
       c.display_name AS customer_name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id;
```

Corresponding mapper:

```java
public record OrderCustomerView(
    Long orderId,
    Long customerId,
    String orderStatus,
    String customerName
) {}
```

```java
.map((row, metadata) -> new OrderCustomerView(
    row.get("order_id", Long.class),
    row.get("customer_id", Long.class),
    row.get("order_status", String.class),
    row.get("customer_name", String.class)
))
```

Aliases decouple SQL and Java mapping from physical column names while clarifying the origin of each value. When a column is renamed in the schema, only the SQL in the data access layer needs updating if the public alias remains unchanged.

## 7. Mapping Null Values from `LEFT JOIN`

With `LEFT JOIN`, right-hand columns can be null. For example, a customer may not have placed any orders yet:

```sql
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       o.id AS order_id,
       o.order_no
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id;
```

A join-row DTO can represent nullable `orderId` and `orderNo`:

```java
public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId,
    String orderNo
) {}
```

During mapping, `row.get("order_id", Long.class)` can return null if the customer has no orders. If building a nested list of orders inside a customer, check `orderId != null` before constructing a child object. Creating an `Order` with a null ID could accidentally represent a nonexistent child row as a bogus object.

Do not replace null with 0 or an empty string if those values carry valid domain meaning. Preserving null distinguishes "no related record" from "a record exists with value 0/empty".

## 8. Mapping Aggregated Results with `GROUP BY`

Aggregate queries return values computed across multiple rows, such as `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX`. Results usually fit reporting DTOs rather than entities.

Example aggregating order counts and revenue by customer:

```sql
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total_amount), 0) AS revenue,
       MAX(o.created_at) AS last_order_at
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
   AND o.status IN ('PAID', 'COMPLETED')
GROUP BY c.id, c.display_name
ORDER BY revenue DESC, c.id ASC;
```

DTO:

```java
public record CustomerOrderStats(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue,
    OffsetDateTime lastOrderAt
) {}
```

Mapping:

```java
public Flux<CustomerOrderStats> findCustomerStats() {
    return databaseClient.sql("""
            SELECT c.id AS customer_id,
                   c.display_name AS customer_name,
                   COUNT(o.id) AS order_count,
                   COALESCE(SUM(o.total_amount), 0) AS revenue,
                   MAX(o.created_at) AS last_order_at
            FROM customer c
            LEFT JOIN purchase_order o
                ON o.customer_id = c.id
               AND o.status IN ('PAID', 'COMPLETED')
            GROUP BY c.id, c.display_name
            ORDER BY revenue DESC, c.id ASC
            """)
        .map((row, metadata) -> new CustomerOrderStats(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class),
            row.get("revenue", BigDecimal.class),
            row.get("last_order_at", OffsetDateTime.class)
        ))
        .all();
}
```

Key points to note:

- `COUNT(o.id)` returns 0 for customers with no matching orders.
- `SUM(...)` over an empty set can return null; `COALESCE` turns it into 0 if that is the desired rule.
- `MAX(o.created_at)` can still be null if there are no orders.
- `GROUP BY` must include directly selected non-aggregated columns according to your database's SQL rules.
- `revenue` is an alias for an aggregate expression; using aliases in `ORDER BY` depends on the SQL dialect, though it is supported by common RDBMSs.

Temporal types in the DTO must match the column type and driver. For example, PostgreSQL `TIMESTAMP WITH TIME ZONE` typically maps to an offset temporal type or a driver-supported type. Do not assume all drivers return the exact same Java class.

## 9. Avoiding Metric Duplication When Joining Multiple Collections

A common aggregation bug occurs when joining two one-to-many relationships simultaneously. Suppose an order has 3 line items and 2 payments. Joining both `order_line` and `payment` can produce 3 × 2 = 6 result rows for one order.

The following query can miscount and over-sum:

```sql
SELECT o.id,
       COUNT(ol.id) AS line_count,
       SUM(p.amount) AS paid_amount
FROM purchase_order o
LEFT JOIN order_line ol ON ol.order_id = o.id
LEFT JOIN payment p ON p.order_id = o.id
GROUP BY o.id;
```

Each line item is repeated for every payment, and each payment is repeated for every line item. `COUNT(DISTINCT ol.id)` can fix the count, but `SUM(DISTINCT p.amount)` is not a general solution because two distinct payments can have the exact same amount.

A safe approach is aggregating each collection separately before joining:

```sql
WITH line_stats AS (
    SELECT order_id,
           COUNT(*) AS line_count
    FROM order_line
    GROUP BY order_id
), payment_stats AS (
    SELECT order_id,
           SUM(amount) AS paid_amount
    FROM payment
    WHERE status = 'SUCCESS'
    GROUP BY order_id
)
SELECT o.id AS order_id,
       o.order_no,
       COALESCE(ls.line_count, 0) AS line_count,
       COALESCE(ps.paid_amount, 0) AS paid_amount
FROM purchase_order o
LEFT JOIN line_stats ls ON ls.order_id = o.id
LEFT JOIN payment_stats ps ON ps.order_id = o.id;
```

Each CTE produces at most one row per `order_id`, so joining them back to the order will not multiply metrics across the two collections. CTE syntax is supported in modern RDBMSs, though you should verify the dialect and execution plan of your database.

Another approach is running independent aggregate queries and merging results in the application layer. Choose based on data volume, round trips, and consistency requirements.

## 10. Mapping a Flat Join Result into a Nested Model

A one-to-many join query typically returns one row per child row. If the API needs a parent object containing a list of children, the application must group rows by parent ID.

Example intermediate DTO for each SQL row:

```java
public record OrderLineRow(
    Long orderId,
    String orderNo,
    String status,
    Long lineId,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

Final DTOs:

```java
public record OrderDetail(
    Long orderId,
    String orderNo,
    String status,
    List<OrderLineView> lines
) {}

public record OrderLineView(
    Long lineId,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

Query:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       l.id AS line_id,
       l.product_id,
       l.quantity,
       l.unit_price
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
WHERE o.id = :orderId
ORDER BY l.id;
```

Rows can be mapped individually and then grouped by `orderId`. The example below uses an internal accumulator to avoid creating a bogus line item when `LEFT JOIN` finds no child rows:

```java
private static final class OrderAccumulator {
    final Long id;
    final String orderNo;
    final String status;
    final List<OrderLineView> lines = new ArrayList<>();

    OrderAccumulator(OrderLineRow row) {
        this.id = row.orderId();
        this.orderNo = row.orderNo();
        this.status = row.status();
    }

    OrderDetail toResult() {
        return new OrderDetail(id, orderNo, status, List.copyOf(lines));
    }
}

public Mono<OrderDetail> findOrderDetail(Long orderId) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   l.id AS line_id,
                   l.product_id,
                   l.quantity,
                   l.unit_price
            FROM purchase_order o
            LEFT JOIN order_line l ON l.order_id = o.id
            WHERE o.id = :orderId
            ORDER BY l.id
            """)
        .bind("orderId", orderId)
        .map((row, metadata) -> new OrderLineRow(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("line_id", Long.class),
            row.get("product_id", Long.class),
            row.get("quantity", Integer.class),
            row.get("unit_price", BigDecimal.class)
        ))
        .all()
        .collectList()
        .flatMap(rows -> {
            if (rows.isEmpty()) {
                return Mono.empty();
            }

            OrderAccumulator order = new OrderAccumulator(rows.get(0));
            for (OrderLineRow row : rows) {
                if (row.lineId() != null) {
                    order.lines.add(new OrderLineView(
                        row.lineId(),
                        row.productId(),
                        row.quantity(),
                        row.unitPrice()
                    ));
                }
            }
            return Mono.just(order.toResult());
        });
}
```

This example works well when the details of a single order are bounded in size. `collectList()` holds all query rows in memory; do not apply full-list buffering to a large report or a query that may return millions of rows. For large datasets, paginate parents, stream by ordered groups, or use database-appropriate aggregate/JSON projections.

If you need to distinguish a nonexistent order from an order with zero lines, the mapping above handles both: no result rows returns `Mono.empty()`, whereas a parent row with `lineId == null` returns an `OrderDetail` with an empty `lines` list.

## 11. Avoiding N+1 Queries When Building Read Models

An N+1 query issue happens when an application fetches a parent list and then executes another query per record to fetch related data. For example:

1. Query 50 orders.
2. For each order, call `customerRepository.findById(...)` to get the customer name.
3. For each order, call `orderLineRepository.findByOrderId(...)` to get line items.

The number of queries can jump from 1 to dozens or hundreds. A join with an appropriate projection usually reduces round trips:

```sql
SELECT o.id AS order_id,
       o.order_no,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit;
```

A join is not always the best choice. If related data is very large or has high cardinality, you can fetch a page of parent IDs first and then load child data in a single `WHERE order_id IN (...)` query. This still avoids N+1 without creating an overly wide flat result set.

## 12. Pagination When Joining One-to-Many

A major mistake is applying `LIMIT` directly to the result set after joining a collection. If an order has many line items, `LIMIT 20` might return only part of the last order's lines or fill the entire page with just a few orders that have many lines.

If the goal is paginating by orders, paginate the order set first and then join the line items:

```sql
WITH order_page AS (
    SELECT id, order_no, status, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :pageSize OFFSET :offset
)
SELECT p.id AS order_id,
       p.order_no,
       p.status,
       l.id AS line_id,
       l.product_id,
       l.quantity
FROM order_page p
LEFT JOIN order_line l ON l.order_id = p.id
ORDER BY p.created_at DESC, p.id DESC, l.id ASC;
```

The `order_page` CTE identifies the exact page of orders. The outer query then fetches the line items for those orders. The result can still contain more rows than `pageSize` because each order has multiple lines, but it will not drop line items merely because the page limit was applied after the join.

If only summary information is needed for a list, aggregate `order_line` beforehand or join with a subquery grouped by `order_id` so each order remains a single row. When using offset or keyset pagination, the ordering of the parent set must be deterministic with a unique key as a tie-breaker.

## 13. Aggregates and Commonly Used Functions

Aggregate functions commonly appearing in read models:

| Function | Meaning | Note |
|---|---|---|
| `COUNT(*)` | Counts rows in the group | Counts null-extended rows from `LEFT JOIN` |
| `COUNT(column)` | Counts non-null values | Suitable for counting real child records after `LEFT JOIN` |
| `COUNT(DISTINCT column)` | Counts unique values | Can be resource-intensive; does not fix all row-multiplication bugs |
| `SUM(column)` | Sums values | Returns null when there are no values; use `COALESCE` if 0 is desired |
| `AVG(column)` | Average | Define rounding rules and result type |
| `MIN` / `MAX` | Minimum/maximum value | Can return null when the group has no values |

Example daily revenue report:

```sql
SELECT CAST(created_at AS DATE) AS order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue,
       AVG(total_amount) AS average_order_value
FROM purchase_order
WHERE status IN ('PAID', 'COMPLETED')
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day ASC;
```

DTO:

```java
public record DailySales(
    LocalDate orderDay,
    Long orderCount,
    BigDecimal revenue,
    BigDecimal averageOrderValue
) {}
```

When mapping aggregates, verify the numeric types returned by the driver. Monetary values should use `BigDecimal`, not `double` or `float` for calculations requiring decimal precision. If specific rounding rules are required, define them in SQL or the application layer per business requirements.

## 14. Using Subqueries or CTEs to Separate Aggregation Steps

When a query requires multiple levels of aggregation, subqueries or CTEs help break logic into understandable steps.

Example aggregating revenue by customer first, then filtering for customers exceeding a threshold:

```sql
WITH customer_revenue AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS revenue
    FROM purchase_order
    WHERE status IN ('PAID', 'COMPLETED')
    GROUP BY customer_id
)
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       cr.order_count,
       cr.revenue
FROM customer_revenue cr
JOIN customer c ON c.id = cr.customer_id
WHERE cr.revenue >= :minimumRevenue
ORDER BY cr.revenue DESC, c.id ASC;
```

The CTE clarifies the order of operations: aggregate transactions first, then join customer names and filter results. Database optimizers may inline or materialize CTEs depending on the RDBMS and version; do not assume a CTE is always a physically materialized temporary table.

## 15. When to Use `DatabaseClient` vs. Template?

`R2dbcEntityTemplate` fits entity operations guided by mapping metadata: insert, select, update, and delete using `Query`/`Criteria`. This API is convenient when the query centers on a single entity and its properties.

`DatabaseClient` is a better fit when you need:

- Multi-table joins returning custom DTOs.
- Aggregates with `GROUP BY`, `HAVING`, CTEs, or window functions.
- Projections with SQL expressions or custom aliases.
- Database-specific SQL syntax.
- Exact control over how each column in `Row` is mapped.

You can encapsulate SQL queries inside a custom repository fragment so services do not need to know query details. If a query is used in only one business flow, consider placing it in a dedicated query repository class to keep responsibilities clear.

Do not pick `R2dbcEntityTemplate` just to avoid writing SQL if a join or aggregate query is not naturally expressed by that abstraction. Conversely, do not write raw SQL for simple CRUD operations that repositories already handle well.

## 16. Mapping Data Types and Handling Special Values

When using `DatabaseClient`, the mapper must read the exact data types provided by the driver. Things to watch out for:

- `BIGINT` typically maps to `Long`.
- `INTEGER` typically maps to `Integer`.
- `NUMERIC`/`DECIMAL` should map to `BigDecimal`.
- `COUNT` usually returns a large integer type, though this should be verified per driver.
- Nullable columns from `LEFT JOIN` must be handled as nullable values.
- Timestamps with or without time zones need corresponding Java types and explicit time zone conventions.
- JSON, arrays, enums, and custom types depend on the driver, converters, or query syntax.

If the Java type does not match what the driver supports, `row.get(column, TargetType.class)` can throw a conversion error. When complex conversion is needed, use converters or read the source type and convert in a controlled manner. Do not cast blindly without checking for null and precision.

With aggregates, aliases should be stable and unique. Avoid selecting two columns with the same name without aliasing, as mappers can read the wrong column or break when new joins are added later.

## 17. Security and Correctness of Custom SQL

When building join or aggregate queries from requests, every value such as status, tenant ID, time range, and revenue threshold must use bind parameters:

```java
databaseClient.sql("""
        SELECT customer_id, SUM(total_amount) AS revenue
        FROM purchase_order
        WHERE status = :status
          AND created_at >= :fromTime
        GROUP BY customer_id
        HAVING SUM(total_amount) >= :minimumRevenue
        """)
    .bind("status", status)
    .bind("fromTime", fromTime)
    .bind("minimumRevenue", minimumRevenue);
```

Do not concatenate user input directly into SQL. Table names, column names, sort directions, and SQL expressions cannot be bound as values; if they need to vary, use a fixed allow-list in code.

Beyond SQL injection, ensure data-scope predicates are always enforced. For instance, multi-tenant queries must filter by the server-authenticated tenant rather than trusting a client-supplied tenant ID alone. A syntactically valid join missing a tenant predicate can leak another customer's data.

## 18. Performance and Indexing for Join/Aggregate Queries

Joins and aggregates can scan many rows, so inspect indexes and execution plans:

- Indexes on foreign keys used for joins, such as `purchase_order.customer_id` and `order_line.order_id`.
- Indexes on filter columns like `status`, `created_at`, or `tenant_id` depending on selectivity and workload.
- Composite indexes ordered to match filter predicates and sorting.
- Select only needed columns; avoid `SELECT *` in read models.
- Pre-aggregate data before joining if joining multiple collections would multiply rows.
- Paginate the parent set before joining one-to-many collections.
- Measure the cost of `COUNT(DISTINCT ...)`, `GROUP BY`, sorts, and CTEs on realistic data volumes.

In PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` shows actual row counts, timing, and buffers read. Note that `ANALYZE` actually executes the query. On other databases, use the equivalent execution plan tool.

Adding an index does not automatically make a query faster. Indexes increase write overhead and storage usage; the optimizer may choose a scan if the table is small or a predicate is not selective enough. Rely on measured numbers.

## 19. Consistency When Running Multiple Queries to Assemble a Read Model

Sometimes an application fetches a page of orders in one query and then fetches statistics or child data in a second query using the ID list. This avoids N+1, but data between queries can change if another transaction updates it in between.

If the read model must reflect a single snapshot, consider an appropriate isolation level and transaction. In reactive transactions, publishers must be composed in the same chain using the same transaction manager/`ConnectionFactory`. Do not call `subscribe()` or `block()` between steps.

Do not hold transactions open while waiting for user input or calling external services. For dashboards that can tolerate approximate or slightly stale data, a periodically or asynchronously updated summary read model may be better than holding long transactions.

## 20. Physical Read Models and CQRS

A read model does not have to be computed solely by a SELECT query. When joins and aggregates are too expensive yet called frequently, results can be stored in a separate table or materialized view.

Example customer statistics table:

```sql
CREATE TABLE customer_order_stats (
    customer_id BIGINT PRIMARY KEY REFERENCES customer(id),
    order_count BIGINT NOT NULL,
    total_revenue NUMERIC(19, 2) NOT NULL,
    last_order_at TIMESTAMP WITH TIME ZONE
);
```

This table can be updated:

- Within the same transaction as the write operation if immediate consistency is needed and computation cost is acceptable.
- Asynchronously via events/outbox if staleness is acceptable and read/write workloads need separation.
- On a schedule via a batch job recomputing from source data.
- Via a materialized view and refresh mechanism if supported by the database.

This is a common form of separating read and write models in CQRS. Clearly define which source data is the source of truth, acceptable lag, how duplicate or lost events are handled, and how to rebuild the read model if drift occurs.

Do not create summary tables merely to optimize an unmeasured query. Physical read models add synchronization, storage, and operational overhead. Optimize SQL, indexes, and projections first; separate read models only when workload measurements justify it.

## 21. Testing Join and Aggregate Mappings

Unit tests can verify transformation logic if the mapper is extracted, but integration tests are needed to validate SQL and data types against a real driver.

Verify the following cases:

- `INNER JOIN` excludes unmatched rows; `LEFT JOIN` retains parent rows as required.
- Colliding column names are aliased and mapped accurately.
- One-to-many relationships yield the exact child row count without duplicates.
- Parents without children produce an empty list rather than a child object with a null ID.
- `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` return the expected values and data types.
- `COALESCE` handles empty sets according to business rules.
- Joining multiple collections does not multiply sums or counts.
- Pagination applies to the parent set before joining collections.
- Tenant and authorization scope predicates are always enforced.
- Transactions preserve consistency when composing multiple queries.

When using Testcontainers, run tests against the same RDBMS planned for deployment. H2 may not faithfully reflect the syntax, data types, aggregates, or driver behavior of PostgreSQL, SQL Server, or Oracle.

## 22. Workflow for Building Read Models from Joins or Aggregates

You can follow this sequence:

**Step 1 — Define the read use case.** Specify what data the screen or report needs, which filters apply, the sort order, and whether pagination is required.

**Step 2 — Design the DTO/read model.** Define each field, data type, nullability, and data source.

**Step 3 — Choose the join type.** Use `INNER JOIN` when matching records on both sides are required; use `LEFT JOIN` when left-side rows must be kept even without a match.

**Step 4 — Write SQL with clear aliases.** Select only needed columns, assign unique aliases, and bind all input values.

**Step 5 — Determine cardinality.** Check one-to-one, one-to-many, and many-to-many relationships; prevent row multiplication when joining multiple collections.

**Step 6 — Build aggregates or group rows.** Use `GROUP BY`, subqueries/CTEs, or fold flat rows into nested DTOs depending on the result shape.

**Step 7 — Map with `DatabaseClient`.** Read accurate column types, handle nulls, and return the appropriate `Mono`/`Flux`.

**Step 8 — Optimize the query.** Review indexes, execution plans, result limits, and avoid N+1.

**Step 9 — Test against a real database.** Verify mapping, aggregates, pagination, transactions, and data scoping.

## 23. Conclusion

Join or aggregate results typically serve a specific read use case and do not need to be forced into a single-table entity. Design DTOs/read models around the data actually returned, use aliases for unambiguous mapping, handle nulls from `LEFT JOIN`, and understand cardinality to avoid duplicating metrics when joining multiple collections.

In Spring Data R2DBC, `DatabaseClient` is a solid choice for executing SQL joins, `GROUP BY`, CTEs, and custom projections and mapping `Row` to DTOs. For one-to-many results, flat rows can be grouped into nested models when result sizes are bounded; for large datasets, paginate parent sets or aggregate in the database. Combining sound SQL, clear mapping, proper indexes, and integration tests on a real driver ensures read models accurately reflect the data needed by screens or reports.
