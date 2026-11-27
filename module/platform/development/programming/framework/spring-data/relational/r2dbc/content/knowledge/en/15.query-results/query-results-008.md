# Organizing Read Models When Queries Do Not Map to a Single Table

## 1. Why Do We Need Dedicated Read Models?

In applications using Spring Data Relational R2DBC, an entity typically represents data stored in a single table or part of an aggregate. Save and update operations need a clear structure so Spring Data knows how to map Java properties to SQL columns.

However, many queries serving screens or reports do not pull data from a single table. An order details page may require the customer name, order date, status, product names, quantities, and total amount. That data resides across multiple tables and is combined using JOINs, aggregations, or computed expressions.

Trying to force these query results into a single-table entity prevents the Java model from accurately reflecting the data structure. Some properties do not exist in the table, a SQL row may repeat the same order header info, or an aggregate value makes no sense to save back into an entity.

The solution is organizing a **read model** tailored to the shape of the query result. A read model is typically a DTO, record, or projection containing only the data a use case needs to display or process.

This organization separates three concepts:

- **Entity/aggregate:** the data model used for persistence and maintaining business rules.
- **Query:** the SQL statement combining, filtering, or aggregating data as needed.
- **Read model:** the result structure returned to a screen, API, or report.

In this guide, examples use Spring Data Relational R2DBC, Reactor, and `DatabaseClient`.

## 2. Entities and Read Models Serve Different Purposes

Suppose the system has the following tables:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
);
~~~

The `Order` entity may contain only data belonging to the `orders` table:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;

    private Instant createdAt;
}
~~~

This entity fits saving and updating orders. However, an admin screen API might need results such as:

- Order ID.
- Customer name.
- Order status.
- Total number of line items.
- Total product quantity.
- Total order amount.

Not all of these properties are columns of the `orders` table. Some come from `customers` or `order_items`; others are results of `COUNT` and `SUM`.

Create a separate read model:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    String status,
    Instant createdAt,
    Long lineCount,
    Long totalQuantity,
    BigDecimal totalAmount
) {}
~~~

`OrderSummary` describes the result of a specific query. It does not need `@Table` or `@Id` if used solely as a read object. Do not call `repository.save(orderSummary)` as if it were an entity writable to a table.

A useful principle: **entities describe data managed in the persistence model; read models describe data that a read operation needs to receive.**

## 3. When Should You Create a Read Model?

A dedicated read model is helpful when a query exhibits one or more of the following traits:

- Combines data from multiple tables via JOINs.
- Computes sums, counts, averages, min/max, or other metrics.
- Selects only a subset of columns for display.
- Returns names or labels combined from multiple properties.
- Includes grouping, statistics, or reporting data.
- Produces a result structure differing from the persisted entity.
- Needs to avoid loading an entire aggregate just to render a screen.
- Returns a result row containing aggregated data from multiple source records.

For example, a dashboard page may need order counts by status:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status;
~~~

The result does not correspond to the `Order` entity. Each row represents a status group rather than an order. A suitable read model:

~~~java
public record OrderStatusCount(
    String status,
    Long orderCount
) {}
~~~

Similarly, a daily revenue query can return:

~~~java
public record DailyRevenue(
    LocalDate orderDate,
    BigDecimal revenue
) {}
~~~

Do not invent artificial entities for every SQL result shape. Create small, purpose-built read types containing only the needed fields.

## 4. Common Forms of Read Models

### 4.1. DTO Class

A DTO (Data Transfer Object) is a class that carries data between the data access layer and the application/API layer.

~~~java
public class CustomerOrderView {
    private final Long orderId;
    private final String customerName;
    private final String status;

    public CustomerOrderView(
            Long orderId,
            String customerName,
            String status) {
        this.orderId = orderId;
        this.customerName = customerName;
        this.status = status;
    }

    public Long getOrderId() {
        return orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public String getStatus() {
        return status;
    }
}
~~~

DTO classes are useful when constructors, validation, or simple presentation logic are needed. If the data simply carries immutable values, Java records are usually more concise.

### 4.2. Java Record

Records fit read models well because components are declared clearly, canonical constructors are generated automatically, and data is immutable by design.

~~~java
public record CustomerOrderView(
    Long orderId,
    String customerName,
    String status
) {}
~~~

A record is not an entity just because it contains fields similar to an entity. It can be constructed directly from SQL results and returned from services.

### 4.3. Projection Interface

A projection interface describes the set of properties to read via getters:

~~~java
public interface CustomerNameView {
    Long getId();
    String getFullName();
}
~~~

In repository methods and projection mechanisms supported by Spring Data Relational, projections restrict data to the required properties. With interface projections, Spring Data can generate a proxy providing getters backed by query results.

Projections fit simple cases, especially when read data stays close to entity properties. However, for complex JOINs, computed expressions, custom aliases, or aggregated results, explicit DTOs/records are usually easier to control.

The applicability of interface projections and result mapping behavior depend on the query type and Spring Data version. Confirm method signatures and documentation for the version in use. Do not assume all Spring Data JPA projection behaviors work identically in R2DBC.

### 4.4. Nested Read Models

An API may require data shaped like:

~~~text
OrderDetail
  orderId
  customer
    customerId
    customerName
  items
    - productName
      quantity
      unitPrice
  totalAmount
~~~

This can be modeled with nested records:

~~~java
public record CustomerSummary(
    Long customerId,
    String customerName
) {}

public record OrderItemView(
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailView(
    Long orderId,
    String status,
    CustomerSummary customer,
    List<OrderItemView> items,
    BigDecimal totalAmount
) {}
~~~

A flat JOIN query typically returns multiple rows for an order with multiple items. The database does not automatically transform those flat rows into your desired nested object graph. The application must group rows by `orderId` and build the `items` list, or use a database-appropriate aggregate/JSON query.

This is the key difference between mapping a single entity and organizing an aggregated read model.

## 5. Choosing the Right Query Tool

Spring Data R2DBC offers several ways to run queries. Not every query needs the same abstraction.

| Tool | Suitable When | Typical Result |
|---|---|---|
| Derived query in repository | Simple filtering predicates on an entity | Entity or supported projection type |
| `@Query` on repository | Static, parameterized SQL, relatively concise query | Entity or mapping-compatible DTO/projection |
| `R2dbcEntityTemplate` | Queries based on mapping metadata, `Criteria`, and entity operations | Entity and API-supported types |
| `DatabaseClient` | JOINs, aggregates, aliases, DB-specific SQL, or explicit `Row` mapping control | DTO/record or custom result type |
| Database view | Queries reused in many places, stable read schema | Read model from view |
| Materialized view | Heavy reports where periodically refreshed data is acceptable | Precomputed read model |

Start from query complexity and result shape. Repository methods excel at CRUD and standard entity queries. When the result is an aggregated dataset that does not correspond to an entity, `DatabaseClient` usually gives clear control over SQL and mapping.

## 6. Using `@Query` to Return Read Types

For relatively static SQL, a repository can declare `@Query` and return an appropriate result type.

Example:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT
            o.id AS order_id,
            c.full_name AS customer_name,
            o.status AS status
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = :orderId
        """)
    Mono<OrderCustomerRow> findOrderCustomer(
        @Param("orderId") Long orderId
    );
}
~~~

Result type:

~~~java
public record OrderCustomerRow(
    Long orderId,
    String customerName,
    String status
) {}
~~~

This declaration works cleanly when the mapping infrastructure of your Spring Data version supports DTO projections for that query. Aliases must be named so mapping can match them to properties/constructor parameters. For complex projections or constructor mappings, check the documentation and test on the actual driver/database.

If the query contains many aggregates, special data types, or requires careful null handling, explicit mapping with `DatabaseClient` makes every column and Java type clearly visible.

## 7. Using `DatabaseClient` to Map JOINs into DTOs

### 7.1. SQL Query Returning One Row per Order

For example, an order summary screen needs the customer name and total value:

~~~sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status AS status,
    o.created_at AS created_at,
    COUNT(oi.id) AS line_count,
    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.id
WHERE o.id = :orderId
GROUP BY
    o.id,
    c.full_name,
    o.status,
    o.created_at
~~~

Meaning:

- `JOIN customers` fetches the customer name.
- `LEFT JOIN order_items` retains orders that have no detail rows yet.
- `COUNT` counts product line items.
- `SUM` computes total quantity and total amount.
- `COALESCE` converts `NULL` aggregate results to `0` when no detail rows exist.
- `GROUP BY` produces one result row per order.

Read model:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    String status,
    LocalDateTime createdAt,
    Long lineCount,
    Long totalQuantity,
    BigDecimal totalAmount
) {}
~~~

The type of `createdAt` must fit the actual timestamp type and driver. This example uses `LocalDateTime` for illustration; if the schema stores timestamps with time zones, choose the corresponding Java type and time convention.

### 7.2. Mapping `Row` with `DatabaseClient`

~~~java
@Repository
public class OrderReadRepository {

    private final DatabaseClient databaseClient;

    public OrderReadRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<OrderSummary> findSummary(Long orderId) {
        return databaseClient.sql("""
                SELECT
                    o.id AS order_id,
                    c.full_name AS customer_name,
                    o.status AS status,
                    o.created_at AS created_at,
                    COUNT(oi.id) AS line_count,
                    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
                    COALESCE(
                        SUM(oi.quantity * oi.unit_price),
                        0
                    ) AS total_amount
                FROM orders o
                JOIN customers c
                    ON c.id = o.customer_id
                LEFT JOIN order_items oi
                    ON oi.order_id = o.id
                WHERE o.id = :orderId
                GROUP BY
                    o.id,
                    c.full_name,
                    o.status,
                    o.created_at
                """)
            .bind("orderId", orderId)
            .map((row, metadata) -> new OrderSummary(
                row.get("order_id", Long.class),
                row.get("customer_name", String.class),
                row.get("status", String.class),
                row.get("created_at", LocalDateTime.class),
                row.get("line_count", Long.class),
                row.get("total_quantity", Long.class),
                row.get("total_amount", BigDecimal.class)
            ))
            .one();
    }
}
~~~

`DatabaseClient` executes the SQL when the publisher is subscribed. `.bind("orderId", orderId)` binds the value to the placeholder. `.map()` receives `Row` and metadata to construct `OrderSummary`. `.one()` returns a `Mono` because querying by a single ID expects at most one row.

Verify the data types returned by the driver for aggregate expressions. For example, `COUNT` usually returns a large integer type, and `SUM` on `DECIMAL` usually returns `BigDecimal`, though details depend on the RDBMS and driver. If types mismatch, convert in a controlled manner or use `CAST` in SQL.

### 7.3. Aliases Are the Contract Between SQL and the Read Model

Alias names such as `order_id`, `customer_name`, and `total_amount` are the result column names used by the `Row` mapper. They do not have to match the original column names.

Use explicit aliases:

| SQL Expression | Alias | Property in Read Model |
|---|---|---|
| `o.id` | `order_id` | `orderId` |
| `c.full_name` | `customer_name` | `customerName` |
| `COUNT(oi.id)` | `line_count` | `lineCount` |
| `SUM(...)` | `total_amount` | `totalAmount` |

When mapping manually, the string passed to `row.get()` must match the alias returned by SQL. If an alias changes in SQL and you forget to update the mapper, the bug may only surface at runtime.

A good convention is using `snake_case` for SQL aliases and `camelCase` for Java properties. Translating between the two should be done intentionally in the mapper rather than by guesswork.

## 8. One-to-Many JOINs and Grouping Rows into Nested Structures

### 8.1. Why Do JOINs Produce Multiple Rows?

Suppose an order has three products. The query:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    oi.id AS item_id,
    oi.product_name,
    oi.quantity,
    oi.unit_price
FROM orders o
LEFT JOIN order_items oi
    ON oi.order_id = o.id
WHERE o.id = :orderId
ORDER BY oi.id
~~~

can return three rows. Each row repeats `order_id` and `status`, while having distinct `item_id` and product data.

If you directly map each row into an `OrderDetailView` containing `List<OrderItemView>`, you end up with three separate order objects instead of one order containing three items. Per-`Row` mapping does not automatically group rows into a nested aggregate.

### 8.2. Separating the Flat Row Type and Final Result Type

Create an internal type for each row:

~~~java
public record OrderItemRow(
    Long orderId,
    String status,
    Long itemId,
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

Then define the final read model:

~~~java
public record OrderItemView(
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailView(
    Long orderId,
    String status,
    List<OrderItemView> items
) {}
~~~

The query returns `Flux<OrderItemRow>`. The read layer groups rows by `orderId` and builds an `OrderDetailView`. Separating the two types distinguishes flat intermediate data from the structure the API needs to return.

### 8.3. Grouping Rows in a Reactive Pipeline

For a specific order, you can collect the rows of that order and build the DTO:

~~~java
public Mono<OrderDetailView> findDetail(Long orderId) {
    return loadOrderItemRows(orderId)
        .collectList()
        .map(rows -> {
            if (rows.isEmpty()) {
                return null;
            }

            OrderItemRow first = rows.get(0);

            List<OrderItemView> items = rows.stream()
                .filter(row -> row.itemId() != null)
                .map(row -> new OrderItemView(
                    row.productName(),
                    row.quantity(),
                    row.unitPrice()
                ))
                .toList();

            return new OrderDetailView(
                first.orderId(),
                first.status(),
                items
            );
        })
        .flatMap(detail -> detail == null
            ? Mono.empty()
            : Mono.just(detail));
}
~~~

This example illustrates grouping rows for a single `orderId`. In production code, explicitly handle the missing-order case and avoid using `null` as an internal signal if possible. You can return `Mono.empty()` or emit a business exception directly from the appropriate query/flow.

Because an order can have multiple lines, `collectList()` holds all rows in memory. This is reasonable when line counts are bounded by business rules. For large result sets, use pagination, limits, or appropriate aggregation.

### 8.4. Grouping Multiple Orders in a Single Query

When reading multiple orders each having multiple items, rows can be grouped by `orderId` using an ordered map. The example below sketches the processing structure:

~~~java
return loadRowsForCustomer(customerId)
    .collect(
        LinkedHashMap<Long, List<OrderItemRow>>::new,
        (grouped, row) -> grouped
            .computeIfAbsent(row.orderId(), key -> new ArrayList<>())
            .add(row)
    )
    .flatMapMany(grouped -> Flux.fromIterable(grouped.values()))
    .map(this::toOrderDetail);
~~~

The snippet above outlines grouping by key; in real Java code, declare a `Supplier<Map<Long, List<OrderItemRow>>>` or use a syntactically valid map-initializing lambda, and implement `toOrderDetail` to construct the DTO. Decide how to handle rows with `item_id` NULL caused by `LEFT JOIN`.

Another option is splitting parent and child queries into batches, while avoiding N+1: do not execute an extra query per order. Load items for a batch of `orderId` values in a single query and group them in memory.

## 9. Distinguishing `LEFT JOIN`, `NULL`, and Default Values

With `LEFT JOIN`, columns of the right-hand table can be `NULL` when no matching record exists.

Example:

~~~sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name
FROM orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
~~~

If there is no matching customer, `customer_name` can be `NULL`. The read model must allow that field to be null or the query must define a fallback:

~~~sql
COALESCE(c.full_name, 'Unknown customer') AS customer_name
~~~

Only use `COALESCE` when the fallback value makes business sense. Do not turn `NULL` into an empty string or zero arbitrarily, as that can hide missing data.

When reading `Row`:

~~~java
String customerName = row.get("customer_name", String.class);
~~~

the value can be `null`. Using primitive types like `long` or `int` in a DTO cannot represent null. For potentially missing data, use `Long`, `Integer`, or an appropriate reference type.

Several points to keep in mind:

- `COUNT` on an empty set returns `0`.
- `SUM` can return `NULL` when there are no matching rows.
- `LEFT JOIN` can produce a row with right-hand columns set to `NULL`.
- `COUNT(*)` counts rows generated by `LEFT JOIN`; `COUNT(oi.id)` counts only items with an ID.
- `COALESCE` should only be used when `0` or a fallback value genuinely fits the data's meaning.

## 10. Reading Aggregated Data and Numeric Types

Aggregate expressions often have return types differing from their input columns. Determine the types based on your database and driver.

Example:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_amount
FROM orders
WHERE created_at >= :fromTime
~~~

Read model:

~~~java
public record RevenueStatistics(
    Long orderCount,
    BigDecimal revenue,
    BigDecimal averageAmount
) {}
~~~

If no matching rows exist:

- `COUNT(*)` typically still returns `0`.
- `SUM` and `AVG` can return `NULL`.
- `COALESCE` can be used if business rules want missing data represented as `0`.

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0) AS revenue,
    COALESCE(AVG(total_amount), 0) AS average_amount
FROM orders
WHERE created_at >= :fromTime
~~~

Pay attention to `DECIMAL` precision and scale. Do not convert monetary totals to `double` merely for convenience. Keep `BigDecimal` for monetary values and specify scale/rounding per business rules.

## 11. `R2dbcEntityTemplate` and `DatabaseClient` in Read Models

### 11.1. `R2dbcEntityTemplate`

`R2dbcEntityTemplate` works with entity mapping metadata and provides Spring Data Relational-style data access APIs. It fits well when queries remain tied to an entity, needing `Criteria`, `Query`, mapping-based updates/deletes, or the mapping context.

Conceptual example:

~~~java
Query query = Query.query(
    Criteria.where("status").is("PAID")
);

return r2dbcEntityTemplate.select(query, Order.class);
~~~

Exact APIs may differ across Spring Data versions. Check the method signatures of the version in use.

If results require multi-table JOINs, `GROUP BY`, or non-entity DTO structures, `DatabaseClient` is usually easier to control because you write SQL and `Row` mapping explicitly.

### 11.2. `DatabaseClient`

`DatabaseClient` provides a SQL-level reactive API. You control:

- `SELECT` and `JOIN` clauses.
- Result column aliases.
- Bind parameters.
- How `Row` is mapped to a DTO.
- `Mono` or `Flux` return type.

Example:

~~~java
return databaseClient.sql("""
        SELECT id AS customer_id, full_name
        FROM customers
        WHERE active = :active
        """)
    .bind("active", true)
    .map((row, metadata) -> new CustomerNameViewImpl(
        row.get("customer_id", Long.class),
        row.get("full_name", String.class)
    ))
    .all();
~~~

`DatabaseClient` fits custom read models well because the mapping code directly expresses the result structure. Use `bind` for all input values; do not concatenate data strings into SQL.

## 12. Using Database Views or Materialized Views

When a complex read query is reused across multiple screens or services, the logic can be placed in a database view.

Example:

~~~sql
CREATE VIEW order_summary_view AS
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.id
GROUP BY
    o.id,
    c.full_name,
    o.status,
    o.created_at;
~~~

The application can read the view using SQL:

~~~sql
SELECT order_id, customer_name, status, created_at, total_amount
FROM order_summary_view
WHERE order_id = :orderId
~~~

A view typically represents a defined query; data is computed when the view is queried, depending on the database and query optimizer. A materialized view stores precomputed results and must be refreshed according to the database's mechanism.

Comparison:

| Approach | Characteristics | Considerations |
|---|---|---|
| Direct query in application | SQL logic stays close to the use case | Query may be duplicated if used in many places |
| Database view | Places shared read logic in the schema | Must manage view versioning and access permissions |
| Materialized view | Fast reads from precomputed data | Data can be stale until the next refresh |
| Separate read model table | Data updated via application/event mechanisms | More complex; requires handling sync and consistency |

Do not create a materialized view for a single JOIN query. Base the decision on read frequency, computation cost, data freshness requirements, and operational capacity.

## 13. Read Models and CQRS

CQRS (Command Query Responsibility Segregation) is a pattern separating the write command model from the read query model. In a simple system, using a DTO for a JOIN query does not mean the entire application has adopted CQRS.

Different levels can be distinguished:

- **Local read DTO:** a query method returning a DTO for a single use case.
- **Dedicated read repository:** a class focused solely on querying and building read models.
- **Database view/read schema:** multiple use cases sharing a common read structure.
- **Full CQRS:** command and query models organized independently, possibly with separate synchronization mechanisms.

You do not need full CQRS just to handle a screen requiring a JOIN. Start with DTOs and read repositories; separate read infrastructure only when performance, scalability, or domain organization justifies it.

If a read model is updated asynchronously from events or projection workers, define the consistency lag. A user might update an order and not see it reflected immediately on a dashboard. This is a characteristic of eventual consistency and must be accounted for in UX and business design.

## 14. Pagination and Ordering in Aggregated Read Queries

Read models often serve lists and reports. When a query has a one-to-many JOIN, paginating directly on the JOIN rows can split a single order across multiple pages or duplicate it.

For example, if each order has multiple items, `LIMIT 20` on the JOIN result limits to 20 joined rows, not 20 orders.

A common approach is paginating the list of parent table IDs first, then loading the needed data for that ID set:

~~~sql
SELECT
    o.id,
    o.created_at
FROM orders o
WHERE o.customer_id = :customerId
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset
~~~

Then load related data for that set of `orderId` values in another query or a suitable aggregated query.

Always include a deterministic sort criterion, such as `created_at` with `id` as a tie-breaker. If sorting solely by timestamp when multiple rows share the same timestamp, ordering across pages may become unstable.

For large datasets, consider keyset pagination:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = :customerId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

Keyset pagination requires tracking the cursor of the previous page's last row and having suitable indexes. It avoids large-offset overhead and reduces page drift when new data is inserted, though it does not provide total page counts like offset pagination.

## 15. Avoiding N+1 When Building Read Models

An inefficient approach is reading a list of orders and then calling a repository per order to fetch the customer name or items.

Example:

~~~java
return orderRepository.findAll()
    .flatMap(order ->
        customerRepository.findById(order.getCustomerId())
            .map(customer -> toView(order, customer))
    );
~~~

If there are N orders, the code can issue N additional customer queries. This is the N+1 query problem.

It can be solved in several ways:

- Use a JOIN to retrieve related data in a single query.
- Load related ID lists in batches and join them in memory.
- Use a view if the logic is shared across multiple use cases.
- Design aggregates/read models aligned with common query patterns.

JOINs are not always better than separate queries. For large one-to-many relationships, a JOIN can multiply rows and repeat parent data. Compare execution plans and bytes transferred, not just SQL statement counts.

In reactive pipelines, `flatMap` can launch many concurrent queries. Even when concurrency is bounded, N+1 is still N+1. Fix the query shape or batch data rather than merely tuning concurrency.

## 16. Performance and Indexing for Read Queries

Read models often combine multiple tables and filters. Consider:

- Indexes on foreign keys used in JOINs.
- Indexes on filter columns like `customer_id`, `status`, or `created_at`.
- Composite indexes with column order matching filter predicates and sorting.
- Selecting only needed columns instead of `SELECT *`.
- Avoiding unnecessary computations or conversions on filter columns that prevent index usage.
- Using `EXPLAIN`/`EXPLAIN ANALYZE` per database to inspect execution plans.
- Checking actual row counts, cardinality, and sort/aggregate costs.

For instance, a query filtering by `customer_id` and sorting by `created_at` and `id` may benefit from an index like:

~~~sql
CREATE INDEX ix_orders_customer_created_id
ON orders(customer_id, created_at DESC, id DESC);
~~~

Specific indexes must be based on workload and database capabilities. Indexes add write overhead and storage footprint. Do not create indexes based solely on column names appearing in SQL without inspecting query plans.

## 17. Organizing Code into Write Repositories and Read Repositories

An easy-to-follow structure separates the entity repository from custom query classes:

~~~text
order/
  domain/
    Order.java
    OrderItem.java
  repository/
    OrderRepository.java
  query/
    OrderReadRepository.java
    OrderSummary.java
    OrderDetailView.java
  service/
    OrderService.java
~~~

`OrderRepository` manages entity/aggregate operations:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
    Flux<Order> findByCustomerId(Long customerId);
}
~~~

`OrderReadRepository` manages JOIN queries, statistics, or read models:

~~~java
public interface OrderReadRepository {
    Mono<OrderSummary> findSummary(Long orderId);
    Flux<OrderSummary> findSummaries(Long customerId);
}
~~~

The implementation of `OrderReadRepository` can use `DatabaseClient`. The service coordinates when a use case needs both reads and writes:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderReadRepository orderReadRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderReadRepository orderReadRepository) {
        this.orderRepository = orderRepository;
        this.orderReadRepository = orderReadRepository;
    }

    public Mono<OrderSummary> getSummary(Long orderId) {
        return orderReadRepository.findSummary(orderId);
    }
}
~~~

Separating into two packages or beans is not mandatory for every project. The key is not distorting entities just to carry data from an aggregated query. As query count grows, separating a read repository makes SQL easier to find, test, and optimize.

## 18. Testing Read Models

A read model should be verified at both the mapping level and the query level.

### 18.1. Testing Mappings

With an extracted mapper, verify:

- SQL aliases match column names read by the mapper.
- Null values are handled accurately.
- Aggregate numeric types are compatible.
- Timestamps have the expected type and time zone.
- A `LEFT JOIN` with no child records produces the right result.

### 18.2. Integration Tests with a Real Database

Use the corresponding R2DBC driver and database to verify:

- JOIN queries return the right row count.
- `GROUP BY` and aggregates yield expected results.
- Zero-item states return `0` or `null` per design.
- Bind parameters work properly.
- Pagination neither duplicates nor drops rows.
- Data types and conversions behave like the deployment environment.

H2 or in-memory substitutes may not fully replicate the behavior of PostgreSQL, MySQL, or SQL Server. For dialect-dependent SQL, maintain integration tests against the target database.

### 18.3. Testing Boundary Data

Test fixtures should include:

- Orders with no items.
- Orders with multiple items.
- Missing customers if the relationship allows `LEFT JOIN`.
- Total amount values with fractional decimals.
- Nullable fields.
- Multiple orders with identical timestamps.
- An empty result set.

## 19. Common Mistakes

| Mistake or Misconception | Consequence | Fix |
|---|---|---|
| Using a single-table entity to hold all JOIN columns | Entity no longer reflects the schema | Create a dedicated DTO/record |
| Assuming JOINs automatically build nested objects | Each `Row` remains a flat row | Group by key or use an aggregate query |
| Using `@MappedCollection` for all JOIN results | Confuses aggregate mapping with read projections | Use DTOs/mappers for query results |
| `SELECT *` in multi-table queries | Colliding column names and extra data | Select needed columns and alias clearly |
| Alias mismatches `row.get()` | Mapper receives null or fails at runtime | Align SQL aliases and mapper |
| `COUNT(*)` after `LEFT JOIN` to count items | May count parent rows with no items | Use `COUNT(item.id)` |
| `SUM` returns `NULL` when DTO expects `0` | Unexpected result | Use `COALESCE` when required by business rules |
| Using `double` for money | Floating-point precision errors | Use `BigDecimal`/`DECIMAL` |
| N+1 queries when building DTOs | Increases round trips and latency | Use JOIN or batch queries |
| Paginating directly on a one-to-many JOIN | A parent entity gets split across pages | Paginate parent IDs first |
| Collecting all results with `collectList()` | Memory grows with data size | Limit, paginate, or stream |
| Creating materialized views too early | Adds sync and refresh complexity | Start with queries/DTOs; measure performance first |
| Assuming DTOs can be saved like entities | Lacks proper persistence mapping/lifecycle | Use DTOs strictly for reading or map to separate commands/entities |

## 20. Process for Designing Read Models

When a query does not correspond to a single table, follow these steps:

1. Identify the read use case: screen, API, report, or statistics.
2. List the exact output fields required.
3. Determine which table each field comes from and which are expressions or aggregates.
4. Decide whether the result is one row, multiple flat rows, or a nested structure.
5. Create a DTO, record, or projection named after its purpose.
6. Choose derived queries, `@Query`, `R2dbcEntityTemplate`, or `DatabaseClient` based on complexity.
7. Write SQL with stable aliases, select only needed columns, and bind all input values.
8. Map `Row` to the read type, handling nulls and aggregate types explicitly.
9. For one-to-many relationships, determine how to group rows and bound memory.
10. Check for N+1 issues, pagination, indexes, and execution plans.
11. Write integration tests against an actual database/driver.
12. Keep read models independent of write entities when the two structures serve different purposes.

## 21. Self-Check Exercises

### Exercise 1: Choosing the Result Type

A query joining `customers` and `orders` returns `orderId`, `customerName`, and `status`. Should it map directly into the `Customer` entity?

Hint: No. This is the result of a read use case, so create a DTO/record such as `OrderCustomerView`.

### Exercise 2: Aggregating by Status

A query counting orders by `status` returns multiple rows. Declare the read model.

Hint:

~~~java
public record OrderStatusCount(
    String status,
    Long orderCount
) {}
~~~

### Exercise 3: `LEFT JOIN` with No Child Rows

An order has no items yet. Why is `COUNT(oi.id)` better than `COUNT(*)` when counting items after a `LEFT JOIN`?

Hint: `LEFT JOIN` still produces a row for the parent order. `COUNT(*)` counts that row, whereas `COUNT(oi.id)` ignores `NULL` values on the item side.

### Exercise 4: One-to-Many JOIN

An order has five items. The JOIN query returns five rows. How do you produce a single `OrderDetailView` containing a list of five items?

Hint: Map each `Row` to a flat intermediate type, group by `orderId`, and build the parent DTO with the `List` of items. Or use a database-appropriate aggregate query.

### Exercise 5: Pagination

You want to paginate 20 orders, where each order can have multiple items. Why can `LIMIT 20` directly on the JOIN be wrong?

Hint: `LIMIT` applies to joined rows, not distinct orders. Paginate order IDs first, then load items for that set of IDs.

### Exercise 6: Choosing the Tool

A reporting query uses a three-table JOIN, `GROUP BY`, and `SUM`. Should you choose a derived query or `DatabaseClient`?

Hint: `DatabaseClient` usually fits well because it lets you control SQL, aliases, data types, and `Row` mapping. `@Query` can also be used if the query is static and projection mapping is clearly supported.

### Exercise 7: Distinguishing Read Models from CQRS

A service has a record DTO returned from a JOIN query. Does that mean full CQRS has been applied?

Hint: Not yet. That is a read model. Full CQRS further separates command/query responsibilities and may use separate storage models or synchronization mechanisms.

## 22. Key Takeaways

- A JOIN or aggregate query does not need to return a single-table entity.
- Entities/aggregates serve persistence and business rules; DTOs, records, or projections describe read results.
- Use projections for simple results; use explicit DTOs/records for JOINs, aggregates, and custom structures.
- `DatabaseClient` fits when you need control over SQL, aliases, binding, and `Row` mapping.
- SQL aliases are the contract between the query and the mapper; keep them synchronized with the column names read.
- One-to-many JOINs produce multiple flat rows; creating nested objects requires explicit grouping or aggregation.
- `LEFT JOIN` can produce `NULL`; `COUNT`, `SUM`, and `COALESCE` must be used with proper semantics.
- Use `BigDecimal` for monetary values and verify aggregate types per database/driver.
- Avoid N+1 using JOINs or batch queries; paginate parent tables before expanding one-to-many relationships.
- Views and materialized views are useful when read logic is shared or needs optimization, though they carry management and data-freshness costs.
- A read DTO is not synonymous with full CQRS.
- Test mappings, nulls, aggregates, pagination, and SQL on a real database/driver.

When query results have a different shape than the underlying storage tables, design read models around how the data will be used. Keep entities focused on persistence, write queries returning the needed columns, and map them to clear DTOs or records. That structure keeps JOIN and reporting queries readable, testable, and easy to optimize in Spring Data Relational R2DBC applications.
