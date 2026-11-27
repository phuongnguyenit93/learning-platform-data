# Designing Models Aligned with Real Query Patterns

Designing a data model for a Spring Data R2DBC application should start from how the application actually reads and writes data. A heavily normalized schema can force critical queries to join many tables, read excessive rows, or perform multiple round trips. Conversely, a schema optimized for a single screen can duplicate too much data and make updates hard to keep consistent.

The goal is finding a balance among data correctness, aggregate boundaries, query patterns, performance, and maintainability. Spring Data R2DBC provides Repositories, `R2dbcEntityTemplate`, and `DatabaseClient` for data access; these APIs do not decide the optimal schema on behalf of the application. Developers need to understand the critical queries first, then design tables, relationships, keys, and indexes to support them.

## 1. Start from Access Patterns Instead of Starting from Entities

A common design habit is listing nouns in business requirements and turning each noun into an entity. While this helps identify domain concepts, it does not reveal how the application needs to access data. Before deciding table structures, list the read and write operations the system must serve.

For example, in a sales system, access patterns might include:

| Code | Need | Query Criteria | Data to Return |
|---|---|---|---|
| Q1 | View a customer's order list | `customer_id`, status, date range | Order number, created date, status, total amount |
| Q2 | View details of one order | `order_id` | Order info, customer, and order lines |
| Q3 | Find orders pending processing | Status, creation timestamp | Pending orders, sorted by time |
| Q4 | View purchase history of a product | `product_id`, date range | Orders containing that product |
| Q5 | Daily revenue report | Date range, valid statuses | Date, order count, total revenue |
| W1 | Create an order | Customer and product list | Order and order lines persisted consistently |
| W2 | Change order status | `order_id`, new status | New status and update timestamp |

For each access pattern, also record:

- Call frequency: continuous, hourly, daily, or only during admin actions.
- Expected data volume: one row, dozens of rows, or thousands of rows.
- Desired latency and concurrency level.
- Which fields are strictly required in the result.
- Whether data needs immediate consistency or can tolerate delayed updates.
- Whether the query needs pagination, sorting, or optional filtering.

This information distinguishes critical queries from rare ones. A query called thousands of times per minute may warrant dedicated indexes or read models; a report run once a day can accept a different execution plan.

## 2. Distinguishing Domain Models, Aggregates, and Query Models

Three related yet distinct concepts:

**Domain model** describes business concepts and rules, such as customers, orders, products, and payments.

**Aggregate** is the consistency boundary the application manages as a single unit in the domain. The aggregate root is the entry point for modifying aggregate state. In the sales example, `PurchaseOrder` can be the aggregate root managing that order's lines. `Customer` and `Product` are usually independent aggregates; the order stores customer and product identifiers instead of pulling the entire object graph into one aggregate.

**Query model (read model)** represents data in the shape needed by a screen, API, or report. A read model can combine fields from multiple tables, precompute certain values, or include only a subset of data. It does not have to be a writable entity.

In Spring Data R2DBC, aggregate design matters because Spring Data Relational maps data around aggregates. R2DBC does not provide a persistence context and dirty checking like JPA/Hibernate. The application must perform explicit read and write operations; do not expect mutating a property in an object graph to be automatically detected and synchronized like a traditional ORM.

A sound aggregate boundary typically has these traits:

- Objects inside need to change together to uphold a business rule.
- The aggregate has a clear identifier and entry point.
- The aggregate is not so large that every update loads unnecessary data.
- Other aggregates are referenced via IDs or stable business keys.
- Updates spanning multiple aggregates are explicitly coordinated in the Service layer or business workflow.

Do not turn every foreign key relationship into nested object relationships. Foreign keys in the database express referential integrity; aggregate boundaries express how the application protects business consistency. These two concepts can relate, but they do not have to be identical.

## 3. Data Normalization and Choosing Duplication Levels

Normalization reduces duplicate data and avoids anomalies when inserting, updating, or deleting data. For instance, if customer names are duplicated on every order, a customer renaming might force updating many rows. Storing `customer_id` in the order table and keeping customer info in a separate table keeps master data management clean.

A baseline relational schema might look like:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL,
    current_price NUMERIC(19, 2) NOT NULL
        CHECK (current_price >= 0)
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_no VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(19, 2) NOT NULL CHECK (line_total >= 0)
);
```

This example uses PostgreSQL syntax; identity columns and timestamp types may need adjustment for other database engines. Database constraints protect data even when multiple application flows or external tools write concurrently.

### When to Keep Data Normalized?

Keep data normalized when:

- The data is a frequently updated source of truth.
- Multiple features share the same information and must see the latest changes.
- Duplicating data would introduce multiple synchronization points.
- Business relationships and constraints should be guarded by the database.

For example, a product's current price belongs in the `product` table. However, a confirmed order must store `unit_price` at purchase time inside `order_line`. If it only referenced `product.current_price`, order history would change whenever the current selling price changes, corrupting transaction records. That is an intentional snapshot of the price at order creation time.

### When Can Data Be Duplicated or Precomputed?

Denormalization can be considered when a critical access pattern requires joining many tables or performing expensive calculations, while source data changes less often than read frequency. Examples:

- Storing `total_amount` on the order for fast order list reads.
- Storing order counts and total spend in a customer summary table.
- Building a daily revenue summary table for dashboards.
- Maintaining a read model containing customer names and order details for list screens.

Every duplicated field needs a synchronization rule: updated in the same transaction, updated asynchronously via events, or periodically rebuilt from source data. Define the maximum acceptable staleness and how to repair data if a sync fails.

Do not duplicate data merely because a query has multiple joins. First measure performance, inspect indexes, and examine execution plans. Denormalization increases write overhead, storage size, and data recovery complexity.

## 4. Designing Tables Around Read and Write Operations

Each table should have a clear responsibility and support specific operations. In the order example:

| Table | Primary Data | Key Access Patterns |
|---|---|---|
| `customer` | Customer details | Look up customer by ID, email |
| `product` | SKU, name, and current price | Look up product by ID or SKU |
| `purchase_order` | Status, customer, creation time, total amount | Order lists, processing queue, reports |
| `order_line` | Product, quantity, purchase-time price | Order details, product sales history |

Useful guidelines:

- Every table has a stable primary key. Surrogate keys such as IDs are often convenient for references and pagination.
- Place `NOT NULL`, `UNIQUE`, `CHECK`, and foreign keys in the database for appropriate data invariants.
- Choose data types matching the value domain: `NUMERIC` for money, appropriate datetime types for timestamps, length-bounded columns for codes and statuses.
- Do not store money in `FLOAT` or `DOUBLE` when exact arithmetic is required.
- Pick a timestamp storage convention with clear time zone semantics. For multi-timezone systems, typically store timestamps in UTC or an offset-aware type and convert on display.
- Avoid overly wide tables packed with rarely used columns when most queries only need a small subset; consider splitting large or rarely accessed data when measurable benefits exist.
- Name tables and columns consistently so mappings and SQL stay readable.

Not every table needs a public repository exposed to the Service layer. A child table can be managed through the aggregate root; a reporting table may only be read via dedicated queries.

## 5. Designing Indexes from Filter Criteria and Sort Orders

Indexes help the database find rows faster, though every index consumes space and adds overhead to inserts, updates, and deletes. Therefore, indexes should stem from real queries.

Suppose Q1 frequently fetches orders by customer, status, and date range, sorted newest first:

```sql
SELECT id, order_no, status, created_at, total_amount
FROM purchase_order
WHERE customer_id = :customerId
  AND status = :status
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

An index candidate to test for this query pattern:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at DESC, id DESC);
```

Equality columns typically precede range and sort columns. `id` acts as a tie-breaker so ordering stays deterministic when multiple orders share the same `created_at`. However, optimal index column order also depends on data selectivity, other queries, the database engine, and execution plans.

If status is an optional filter and many queries filter only by `customer_id`, an index with `status` in second position may not serve those queries as effectively as hoped. A separate index or different query design may be needed. Do not create indexes for every possible filter combination; prioritize high-frequency, high-cost query patterns.

### Indexes for Foreign Keys

Databases typically index primary keys automatically, whereas indexes on foreign key columns do not always appear automatically. For example, `order_line.order_id` is frequently used to load an order's lines, so you may need:

```sql
CREATE INDEX idx_order_line_order_id
    ON order_line (order_id);

CREATE INDEX idx_order_line_product_id
    ON order_line (product_id);
```

The `product_id` index supports Q4 when locating orders containing a product. If queries routinely filter by `product_id` and then sort by order or timestamp, a composite index may be warranted after checking execution plans.

### Inspecting Execution Plans

In PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` can be run on representative queries in a suitable environment to observe which index the database chooses, how many rows it scans, and how much time it takes. `ANALYZE` actually executes the SQL statement, so be careful with write statements and production data.

Do not evaluate indexes solely by whether a query feels fast on a few dozen local rows. Use data with realistic scale and distribution while observing the impact on write workloads.

## 6. Designing Pagination and Deterministic Ordering

Order lists can grow to millions of records. Never load everything and filter in Java. Let the database filter, sort, and limit returned rows.

### Offset Pagination

A simple query uses `LIMIT` and `OFFSET`:

```sql
SELECT id, order_no, status, created_at
FROM purchase_order
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
```

Offset pagination is straightforward to implement and fits cases where users jump to arbitrary page numbers over moderate datasets. However, larger offsets require the database to scan and discard more rows. When data changes between calls, records may repeat or be skipped across pages.

### Keyset Pagination

For large lists, keyset pagination can be used. The next request passes a cursor containing the last sort-column values from the previous page:

```sql
SELECT id, order_no, status, created_at
FROM purchase_order
WHERE customer_id = :customerId
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

The cursor predicate must match the `ORDER BY` ordering. Using only `created_at` when multiple rows share the same timestamp can skip or duplicate rows on the next page. Adding `id` as a tie-breaker establishes a deterministic total order.

Keyset pagination performs well when backed by an index matching the filters and sort order. The trade-off is that it suits next/previous cursor navigation better than jumping directly to arbitrary page numbers.

## 7. Designing Read Models for Multi-Table Queries

A list screen rarely needs full entities. For example, a purchase history screen needs order number, customer name, status, and total amount. Loading every `PurchaseOrder` and then calling another repository to fetch each customer creates N+1 queries: one query for the list plus one query per order.

You can use a single join query and map it directly to a projection:

```sql
SELECT o.id,
       o.order_no,
       o.status,
       o.created_at,
       o.total_amount,
       c.display_name AS customer_name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE o.customer_id = :customerId
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit;
```

The read model can be a dedicated DTO:

```java
public record OrderSummary(
    Long id,
    String orderNo,
    String status,
    OffsetDateTime createdAt,
    BigDecimal totalAmount,
    String customerName
) {}
```

For join queries and custom projections, `DatabaseClient` provides control over SQL and result mapping:

```java
public Flux<OrderSummary> findOrderSummaries(Long customerId, int limit) {
    return databaseClient.sql("""
            SELECT o.id,
                   o.order_no,
                   o.status,
                   o.created_at,
                   o.total_amount,
                   c.display_name AS customer_name
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.customer_id = :customerId
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit
            """)
        .bind("customerId", customerId)
        .bind("limit", limit)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("total_amount", BigDecimal.class),
            row.get("customer_name", String.class)
        ))
        .all();
}
```

This snippet illustrates mapping for PostgreSQL and `TIMESTAMP WITH TIME ZONE`; actual Java types must match your driver and mapping configuration. When a driver returns a different temporal type, adjust the DTO or converter accordingly.

A read model contains only the data needed for the use case. It does not need to be stored in a separate table; it can be a DTO built from a SQL query. Only consider persisting physical read models or summary tables if the join query is too expensive and called very frequently.

## 8. Choosing Repository, R2dbcEntityTemplate, or DatabaseClient

Spring Data R2DBC offers multiple abstraction levels. Choose the API by query shape:

| Need | Suitable API | Reason |
|---|---|---|
| CRUD and queries by entity properties | `ReactiveCrudRepository` or extended Repositories | Method names clearly express access patterns with minimal boilerplate |
| Entity queries with dynamically built conditions | `R2dbcEntityTemplate` | Uses Spring Data mapping metadata and fluent query API |
| Multi-table joins, custom projections, database-tuned SQL | `DatabaseClient` | Full control over SQL, parameter binding, and result mapping |
| Low-level driver integration | R2DBC SPI | Used when higher-level abstractions do not meet specialized requirements |

Repository example for straightforward operations:

```java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerIdAndStatusOrderByCreatedAtDesc(
        Long customerId,
        String status
    );
}
```

Method names can express basic queries, but when you need many optional filters, complex cursors, or join projections, a dedicated query is usually easier to read and maintain. Avoid forcing every access pattern into long method names.

`R2dbcEntityTemplate` works well for flexible entity queries:

```java
public Flux<PurchaseOrder> findOrders(Long customerId, String status) {
    Criteria criteria = Criteria.where("customerId").is(customerId)
        .and("status").is(status);

    return template.select(PurchaseOrder.class)
        .matching(Query.query(criteria)
            .sort(Sort.by(Sort.Order.desc("createdAt"))))
        .all();
}
```

This example uses entity property names inside Criteria. When SQL joins or projections do not correspond to a single entity, `DatabaseClient` is generally the clearer choice.

## 9. Safe Dynamic Queries

A search screen may allow filtering by customer, status, date range, and keyword. Never concatenate user input directly into SQL strings:

```java
// Unsafe: do not concatenate input data directly into SQL.
String sql = "SELECT * FROM purchase_order WHERE order_no = '" + orderNo + "'";
```

Use parameter binding for values:

```java
databaseClient.sql("SELECT id, order_no FROM purchase_order WHERE order_no = :orderNo")
    .bind("orderNo", orderNo)
    .map((row, metadata) -> new OrderKey(
        row.get("id", Long.class),
        row.get("order_no", String.class)
    ))
    .one();
```

Parameter binding applies to values, not table names, column names, or SQL keywords. If users can choose a sort column, map their selection through an allow-list in code:

```java
String sortColumn = switch (sortBy) {
    case "createdAt" -> "created_at";
    case "totalAmount" -> "total_amount";
    default -> "id";
};
```

Only insert the validated column name into the dynamic SQL portion, while still binding all filter values. For multiple optional criteria, build SQL from predetermined branches or use `R2dbcEntityTemplate`'s `Criteria` API when querying entities.

## 10. Writing Aggregates Consistently

A new order typically consists of an order record and multiple order lines. This write operation requires atomicity: if saving one line fails, the order must not remain partially created.

A service can coordinate repositories inside a reactive transaction:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;
    private final OrderLineRepository lines;

    public OrderCommandService(
            PurchaseOrderRepository orders,
            OrderLineRepository lines) {
        this.orders = orders;
        this.lines = lines;
    }

    @Transactional
    public Mono<PurchaseOrder> create(CreateOrder command) {
        PurchaseOrder order = new PurchaseOrder(
            null,
            command.customerId(),
            command.orderNo(),
            "PENDING",
            Instant.now(),
            command.totalAmount()
        );

        return orders.save(order)
            .flatMap(saved -> Flux.fromIterable(command.lines())
                .map(line -> new OrderLine(
                    null,
                    saved.id(),
                    line.productId(),
                    line.quantity(),
                    line.unitPrice(),
                    line.lineTotal()
                ))
                .concatMap(lines::save)
                .then(Mono.just(saved)));
    }
}
```

This illustrates the orchestration flow; `CreateOrder`, `OrderLine`, and repositories must be defined according to the actual schema. In production code, there is no need to inject a transaction manager if Spring is configured with `@Transactional` and an appropriate reactive transaction manager. Avoid calling `subscribe()` inside the service; return the publisher so Spring manages the transaction per subscription.

If inventory or current pricing must be verified before writing, decide whether those checks belong in the same transaction or require a separate workflow. Never hold a database transaction open while waiting on an external HTTP service longer than necessary.

## 11. Designing Reporting Queries and Aggregated Data

Reporting queries often differ from transactional queries. For instance, Q5 aggregating daily revenue:

```sql
SELECT CAST(created_at AS DATE) AS order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM purchase_order
WHERE status IN ('PAID', 'COMPLETED')
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day;
```

With moderate data volume, the database can compute this directly from transactional tables. When reports scan large datasets frequently, consider:

- Daily or monthly summary tables.
- Materialized views if supported by the database and refresh lag is acceptable.
- Read models updated asynchronously from business events.
- A dedicated analytics system if reporting workloads impact transactional traffic.

When using aggregated data, document metric definitions precisely. For example, is revenue counted at order creation, payment, or completion? Are refunded orders subtracted? Business definitions must stay consistent between transactional data and reports.

## 12. Avoiding N+1 Queries and Over-Fetching

N+1 queries happen when an application fetches N records and then runs one extra query per record to load related data. For example, loading 100 orders and calling `customerRepository.findById()` 100 times to display customer names.

This can be addressed by:

- Writing a single join query to return the needed projection.
- Collecting the list of IDs and querying by ID set using an appropriate SQL query.
- Designing a read model for frequently viewed screens.
- Selecting only needed columns instead of `SELECT *`.
- Paginating and limiting rows right in the database.

Avoid loading entire aggregates just to display a few fields. For order details, loading the root and its lines with two intentional queries is reasonable. For order lists, a join projection can be far more efficient than assembling full object graphs.

Spring Data R2DBC has no JPA-style lazy loading. Loading related data must be expressed explicitly via queries or appropriate mapping APIs. That keeps database round-trip counts predictable and controllable.

## 13. Choosing Relationship Strategies Across Tables

Schema relationships should reflect both data rules and query patterns:

**One-to-one:** use only when two pieces of data have sufficiently distinct lifecycles or access controls to justify splitting tables. If always read and written together, one table can be simpler.

**One-to-many:** e.g., one order has many order lines. A foreign key on the child table works well. If lines belong to the order's lifecycle, the application can manage them through the aggregate root; if there are significant independent query needs, a dedicated repository or query can be built.

**Many-to-many:** typically needs a join table. If the relationship carries its own attributes such as quantity, added timestamp, or status, model the join table as its own entity. For instance, `order_line` not only links orders and products, it also stores quantity and purchase-time price.

**Inter-aggregate references:** typically store the ID of the other aggregate. When data from that aggregate is needed, query explicitly according to access patterns. This avoids loading and updating large object graphs across consistency boundaries.

Foreign keys protect referential integrity. Still, choosing `ON DELETE CASCADE`, `RESTRICT`, or `SET NULL` must follow data lifecycles and audit requirements. Never cascade-delete transactional records just because a parent entity is removed from the application.

## 14. Factors to Consider When Tuning Schemas

When a query is slow, evaluate multiple factors before changing the model:

- **Selectivity:** does the filter predicate eliminate the majority of rows?
- **Index:** does an index match the filter criteria and sort order?
- **Join:** do join columns have compatible data types and appropriate indexes?
- **Projection:** is the query reading unnecessary columns?
- **Cardinality:** does a join multiply row counts unexpectedly?
- **Pagination:** is a very large offset being used?
- **Locking:** are write operations waiting on locks or update conflicts?
- **Round trips:** is the application issuing many small sequential queries?
- **Pool:** is the query slow in the database or waiting for a connection?
- **Consistency:** can a read model or summary data with acceptable lag be used?

Change the schema only when backed by evidence from representative queries, execution plans, metrics, or profiling. A new index can accelerate reads while slowing writes; a summary table can offload reads while increasing synchronization work.

## 15. Workflow for Query-Driven Data Modeling

You can apply this workflow per bounded context or feature group:

**Step 1 — List access patterns.** Document every critical read and write operation, filters, ordering, projections, frequency, and data volume.

**Step 2 — Identify business rules.** Find invariants that must be protected together and identify aggregate roots. Separate inter-aggregate references from in-code object relationships.

**Step 3 — Draft a normalized schema.** Choose tables, primary keys, foreign keys, unique constraints, check constraints, and domain-accurate data types.

**Step 4 — Write representative SQL.** Author queries for the key access patterns before optimizing indexes. Pinpoint filtered, joined, sorted, and returned columns.

**Step 5 — Design indexes.** Add indexes aligned with real workloads, considering composite indexes, foreign key indexes, and write overhead.

**Step 6 — Choose read models.** Use entities for aggregate writes and DTOs/projections for screens and reports. Denormalize only with measurable justification and clear sync rules.

**Step 7 — Pick R2DBC APIs.** Use Repositories for CRUD and stable queries, `R2dbcEntityTemplate` for dynamic entity queries, and `DatabaseClient` for joins and custom SQL.

**Step 8 — Verify load and consistency.** Use realistic data to test execution plans, latency, transactions, concurrent writes, and pagination behavior.

**Step 9 — Monitor post-deployment.** Watch slow queries, connection pools, timeout errors, and shifting data distributions. Adjust the schema as actual workloads evolve.

## 16. Conclusion

A good data model serves both business rules and the queries the application must execute. Start from access patterns, define aggregates to guard consistency, normalize master data, and design indexes around filter conditions and sort orders. For multi-table queries, use appropriate projections or read models; duplicate data only with clear performance justification and a synchronization strategy.

In Spring Data R2DBC, Repositories suit standard aggregate operations, `R2dbcEntityTemplate` supports flexible entity queries, and `DatabaseClient` fits SQL joins and dedicated projections. Pairing the right abstraction with a schema grounded in real queries keeps database round trips predictable, preserves data consistency, and establishes a clear foundation for measuring and improving performance.
