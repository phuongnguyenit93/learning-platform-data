# Pagination, Native Queries, Projections, and N+1 Query Control

An order-listing API returning just 20 rows can still force the database to execute dozens of queries, hydrate thousands of entities, and consume excessive heap memory. The root cause usually lies in how pagination, data selection, and entity relationship loading are implemented. Spring Data JPA provides `Pageable`, `Page`, `Slice`, projections, and `@Query`; Hibernate provides fetch joins, entity graphs, and batch fetching to control association loading.

This lesson uses Spring Boot 3.x, Spring Data JPA 3.x, Hibernate 6, and MySQL 8.0/8.4. The principles apply across compatible versions as well, though API syntax, native SQL rewriting capabilities, and provider behavior must be verified against your actual dependencies.

## Objectives

After this lesson, you will be able to:

- Paginate with `Pageable`, choosing appropriately among `Page`, `Slice`, and `List`.
- Write native queries with accurate `countQuery` definitions and safe parameter binding.
- Use interface projections and DTO projections to fetch only required columns.
- Detect N+1 queries using SQL logs and Hibernate statistics.
- Choose appropriately among `JOIN FETCH`, `@EntityGraph`, batch fetching, and DTO queries.
- Avoid pagination bugs over collection fetch joins.
- Optimize offset pagination, keyset pagination, and MySQL indexes aligned with sort order.

## 1. Context: Order Listing API

Suppose the system has three tables:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
) ENGINE=InnoDB;
```

A list screen needs only the order ID, customer name, status, total amount, and creation timestamp. Only the detail page needs `order_items`. If the listing API loads full entities and traverses associations row by row, it triggers N+1 queries. If it loads every order and slices pages in Java, both database and application process far more data than needed.

## 2. Pagination with Spring Data JPA

### 2.1. Pageable and Page

A repository method can accept `Pageable` so Spring Data appends limit and offset clauses to the query:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
```

Service constructs the page request:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    purchaseOrderRepository.findByStatus("PAID", pageable);
```

`PageRequest.of()` uses zero-based page numbers. `Page` returns the current page's items plus metadata such as `getTotalElements()`, `getTotalPages()`, `hasNext()`, and `getNumber()`.

With `Page`, Spring Data usually executes an extra `COUNT` query to compute total matching rows. Count queries can be expensive with complex filters, multi-table joins, or large datasets. Use `Page` only when the UI genuinely needs total row counts or total page counts.

### 2.2. Slice When Total Pages Are Unneeded

If the UI only needs to know whether a next page exists, use `Slice`:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Slice<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
```

Spring Data fetches one extra row to determine whether a next page exists, avoiding a full count query. `Slice` exposes `hasNext()` and `hasPrevious()`, without `getTotalElements()` or `getTotalPages()`.

### 2.3. List Combined with Pageable

If you only need the current page's items without pagination metadata:

```java
List<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable
);
```

Spring Data still applies limit/offset from `Pageable`, while skipping any count query needed to build a `Page`. This fits APIs returning only the current page's rows.

### 2.4. Choosing the Return Type

| Return Type | Data Query | Count Query | Metadata |
|---|---|---|---|
| `Page<T>` | Yes | Usually yes; occasionally omitted when total can be inferred | Total rows, total pages, current page |
| `Slice<T>` | Yes, typically fetches one extra row | No | Has next/previous page |
| `List<T>` with `Pageable` | Yes | No | List only |

Never return `Page` simply because a repository paginates. Choose based on client requirements. For infinite scroll or "Load more" buttons, `Slice` is usually a better fit. For reports displaying "1–20 of 12,450 results", `Page` may be necessary.

### 2.5. Deterministic Sorting

Pagination must use deterministic ordering. If sorting solely by `createdAt` when multiple orders share the same timestamp, ordering across pages can shift as MySQL returns tied rows arbitrarily. Add a unique key as a tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(pageNumber, pageSize, sort);
```

Never pass client-supplied column names straight into `Sort` without validation. Column names and SQL expressions are not bind parameters. Map an allowlisted set of permitted sort fields to `Sort` properties and reject invalid fields.

Cap `pageSize` at the API boundary so clients cannot request hundreds of thousands of rows in one page. Base the maximum on payload size, latency, and database load.

## 3. Native Queries with Pagination

JPQL suits queries expressed over entities and associations. When you need MySQL-specific syntax, CTEs, window functions, specialized functions, or hand-tuned SQL, use native queries.

### 3.1. Native Query Returning Page

Example fetching orders by status:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT p.*
            FROM purchase_orders p
            WHERE p.status = :status
            ORDER BY p.created_at DESC, p.id DESC
            """,
        countQuery = """
            SELECT COUNT(*)
            FROM purchase_orders p
            WHERE p.status = :status
            """,
        nativeQuery = true
    )
    Page<PurchaseOrder> findPageByStatusNative(
        @Param("status") String status,
        Pageable pageable
    );
}
```

Spring Data applies pagination from `Pageable` onto the native query. `countQuery` computes the exact total matching rows without `ORDER BY`. For complex queries, declare `countQuery` explicitly instead of relying on framework auto-derivation. Since the SQL already fixes `ORDER BY`, pass an unsorted `Pageable` such as `PageRequest.of(page, size, Sort.unsorted())`; if dynamic sorting is required, use an allowlisted sort set and inspect the generated SQL.

If the query joins child rows causing an order to appear multiple times, the count query must count distinct root entities:

```sql
SELECT COUNT(DISTINCT p.id)
FROM purchase_orders p
JOIN order_items i ON i.order_id = p.id
WHERE i.quantity >= 2;
```

Using `COUNT(*)` above would multiply the total by item count. The count query must match the exact filtering and uniqueness semantics of the data query.

### 3.2. Native Query Filtering Across Multiple Tables

Example fetching orders whose customer name matches a keyword:

```java
@Query(
    value = """
        SELECT p.*
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
          AND c.full_name LIKE CONCAT('%', :keyword, '%')
        ORDER BY p.created_at DESC, p.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
          AND c.full_name LIKE CONCAT('%', :keyword, '%')
        """,
    nativeQuery = true
)
Page<PurchaseOrder> searchByStatusAndCustomerName(
    @Param("status") String status,
    @Param("keyword") String keyword,
    Pageable pageable
);
```

If joins can produce multiple rows per order, use `COUNT(DISTINCT p.id)` and ensure the data query matches those semantics. Note that `LIKE '%keyword%'` with a leading wildcard normally cannot use a standard B-tree index; evaluate full-text indexes or a dedicated search solution if workload demands it.

### 3.3. Sorting with Native Queries

Spring Data's ability to rewrite native SQL to apply `Sort` depends on query complexity and Spring Data JPA version. Never assume every native query gets dynamic `ORDER BY` appended reliably. The safest options are fixing `ORDER BY` in SQL or branching query methods from an allowlisted set of sort columns.

Never concatenate user-supplied sort strings directly into SQL:

```java
// Unsafe: sortColumn taken directly from request.
String sql = "SELECT * FROM purchase_orders ORDER BY " + sortColumn;
```

Instead, map valid fields explicitly:

```java
String orderBy = switch (requestedSort) {
    case "createdAt" -> "p.created_at";
    case "amount" -> "p.total_amount";
    case "id" -> "p.id";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String direction = descending ? "DESC" : "ASC";
String sql = """
    SELECT p.id, p.status, p.total_amount
    FROM purchase_orders p
    ORDER BY %s %s, p.id DESC
    """.formatted(orderBy, direction);
```

This illustration only interpolates tokens selected from fixed allowlists; data values must still be bound via `PreparedStatement`. For static repository queries, prefer separate explicit query methods over complex dynamic SQL assembly.

## 4. Projections: Fetching Only Needed Columns

Entities represent domain state and relationships. A list view typically needs only a small subset of attributes; loading entire entities pulls in persistence context tracking, dirty checking, and unnecessary lazy associations. Projections query only the data required for the use case.

### 4.1. Interface Projections

Define an interface:

```java
public interface OrderListRow {
    Long getId();
    String getStatus();
    BigDecimal getTotalAmount();
    LocalDateTime getCreatedAt();
    String getCustomerName();
}
```

JPQL query using aliases matching property names:

```java
@Query(
    value = """
        SELECT p.id AS id,
               p.status AS status,
               p.totalAmount AS totalAmount,
               p.createdAt AS createdAt,
               c.fullName AS customerName
        FROM PurchaseOrder p
        JOIN p.customer c
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<OrderListRow> findOrderRows(
    @Param("status") String status,
    Pageable pageable
);
```

The projection fetches only the selected fields and returns a view tailored to the screen. `Page` still runs a count query; if total count is unneeded, switch to `Slice<OrderListRow>` or `List<OrderListRow>` with `Pageable`.

### 4.2. Interface Projections with Native SQL

Native queries must alias columns to match projection property names:

```java
public interface NativeOrderRow {
    Long getId();
    String getStatus();
    BigDecimal getTotalAmount();
    LocalDateTime getCreatedAt();
    String getCustomerName();
}
```

```java
@Query(
    value = """
        SELECT p.id AS id,
               p.status AS status,
               p.total_amount AS totalAmount,
               p.created_at AS createdAt,
               c.full_name AS customerName
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
        ORDER BY p.created_at DESC, p.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM purchase_orders p
        WHERE p.status = :status
        """,
    nativeQuery = true
)
Page<NativeOrderRow> findNativeOrderRows(
    @Param("status") String status,
    Pageable pageable
);
```

Aliases like `totalAmount`, `createdAt`, and `customerName` map SQL columns to getters. Verify the JDBC types returned for temporal, decimal, and nullable columns; mapping can depend on driver and column definitions.

### 4.3. DTO Projections with Records

For immutable DTOs, Java records are concise:

```java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String customerName
) {}
```

JPQL uses a constructor expression:

```java
@Query(
    value = """
        SELECT new com.example.orders.OrderSummary(
            p.id,
            p.status,
            p.totalAmount,
            p.createdAt,
            c.fullName
        )
        FROM PurchaseOrder p
        JOIN p.customer c
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<OrderSummary> findSummaries(
    @Param("status") String status,
    Pageable pageable
);
```

The class name in a constructor expression must be fully qualified. Argument order and types must match the record/DTO constructor. This approach is explicit and does not rely on alias matching like interface projections.

### 4.4. DTO Projections from Native Queries

Native SQL returns columns as a JDBC result set. Direct mapping to DTOs/records depends on Spring Data's constructor mapping support and result structure. When column order, names, or types do not align directly, use `@SqlResultSetMapping`/`@ConstructorResult` or return an interface projection and map to DTOs in the service layer.

Never assume a native query automatically maps arbitrary SQL results into a record merely because column names resemble component names. Test mapping on your exact Spring Data JPA and Connector/J versions.

### 4.5. When to Use Projections?

| Scenario | Choice |
|---|---|
| List screen displaying only a few columns | Interface or DTO projection |
| Immutable read payload for an API | DTO/record projection |
| Mutating entities using lifecycle/domain behavior | Entity |
| MySQL-specific query, CTE, or window function | Native query + projection |
| Total page count needed | `Page<Projection>` with accurate count query |
| Only "is there more data?" needed | `Slice<Projection>` |

Projections do not automatically eliminate every N+1 query. If a projection returns an entity or nested association and the service accesses lazy relations afterward, N+1 still occurs. For list APIs, favor flat projections containing exactly the fields to return.

## 5. What Is an N+1 Query?

An N+1 problem happens when the application runs one query to fetch N root entities and then triggers an additional query per entity when accessing a lazy association. For instance, fetching 50 orders in one query and calling `order.getCustomer().getFullName()` per row can fire 50 extra queries if customers were not loaded.

### 5.1. Entity Example

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
```

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
}
```

Iterating the list:

```java
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByStatus("PAID");

for (PurchaseOrder order : orders) {
    // May trigger a separate SELECT for each customer.
    log.info("Customer: {}", order.getCustomer().getFullName());
}
```

With 50 orders belonging to 50 distinct customers, this issues 1 query for orders plus 50 queries for customers. If multiple orders share a customer, the persistence context caches loaded customers and reduces queries slightly, though you should never rely on that in design.

N+1 also occurs with collections:

```java
for (PurchaseOrder order : orders) {
    int itemCount = order.getItems().size();
    log.info("Order {} has {} items", order.getId(), itemCount);
}
```

Hibernate may fire an extra query for every order's collection. Serializing entities directly to JSON can similarly touch lazy relations inadvertently and trigger N+1.

### 5.2. Detecting N+1

Enable SQL logging in development:

```yaml
spring:
  jpa:
    show-sql: false

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Bind logging can print sensitive data; enable it only under controlled dev/test settings and redact before sharing logs. `spring.jpa.show-sql` is unnecessary once Hibernate loggers are configured.

You can enable Hibernate statistics in test environments:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Assert prepared statement counts in tests:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Call the service/repository under test.
orderService.getOrderList();

long statementCount = statistics.getPrepareStatementCount();
assertThat(statementCount).isLessThanOrEqualTo(3);
```

This demonstrates the testing idea; isolate test data and reset statistics before each test. Setup statements, count queries, flushes, or secondary lookups affect counts. Inspect SQL logs to see which queries caused extra round-trips rather than relying solely on a threshold.

## 6. Controlling N+1 Queries

No single fetch strategy fits all cases. Choose based on which associations are read, page size, and query purpose.

### 6.1. JOIN FETCH for To-One Associations

If the list needs each order's customer, fetch-join the `ManyToOne` association:

```java
@Query("""
    SELECT p
    FROM PurchaseOrder p
    JOIN FETCH p.customer
    WHERE p.status = :status
    """)
List<PurchaseOrder> findWithCustomerByStatus(
    @Param("status") String status
);
```

This normally fetches orders and customers in a single SQL query instead of loading customers lazily one by one. `JOIN FETCH` does not introduce a separate projection in JPQL results; it instructs the provider to load the association alongside the root entity.

For to-one associations, fetch joins generally work cleanly with pagination because each order links to at most one customer. Even so, inspect generated SQL, count queries, and actual results—especially when additional joins exist.

### 6.2. @EntityGraph

You can declare a fetch plan directly on the repository:

```java
@EntityGraph(attributePaths = "customer")
Page<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable
);
```

`@EntityGraph` tells the provider which associations to fetch in that query without writing a JPQL fetch join manually. It is concise for adding one or a few to-one relations. Inspect Hibernate's generated SQL and confirm the count query does not accumulate unnecessary joins.

Never add large collections to an `@EntityGraph` on a paginated query without evaluating the impact. EntityGraph causes the provider to fetch the collection, carrying the same collection-pagination risks as fetch join.

### 6.3. Why Is Collection JOIN FETCH Dangerous with Pagination?

Suppose one order has 10 items. When fetch-joining the collection, SQL returns 10 rows for that single order. Applying `LIMIT 20` in SQL limits joined rows, not 20 distinct orders. Hibernate must then fetch excess rows and deduplicate/paginate in memory.

Example to avoid on list pages:

```java
@Query("""
    SELECT DISTINCT p
    FROM PurchaseOrder p
    LEFT JOIN FETCH p.items
    WHERE p.status = :status
    """)
Page<PurchaseOrder> findPageWithItems(
    @Param("status") String status,
    Pageable pageable
);
```

Hibernate 6 emits warning `HHH90003004` when pagination is applied over a collection fetch and falls back to in-memory pagination. Enable fail-fast in dev/test so design mistakes cannot slip by silently:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

Never treat `DISTINCT` as a fix for this issue. `DISTINCT` deduplicates at the entity/result level, yet does not make SQL `LIMIT/OFFSET` paginate by root entity count.

### 6.4. Two-Step Approach: Paginate IDs, Then Fetch Associations

When a page genuinely requires collections, a safer pattern is:

1. Query a page of root entity IDs with filters, sorting, and pagination.
2. Execute a second query loading entities and associations for those IDs.
3. Reorder results to match the ID order from step 1, because `IN (...)` does not preserve order.

Repository:

```java
@Query(
    value = """
        SELECT p.id
        FROM PurchaseOrder p
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<Long> findPageIdsByStatus(
    @Param("status") String status,
    Pageable pageable
);

@Query("""
    SELECT DISTINCT p
    FROM PurchaseOrder p
    JOIN FETCH p.customer
    LEFT JOIN FETCH p.items
    WHERE p.id IN :ids
    """)
List<PurchaseOrder> findWithCustomerAndItemsByIdIn(
    @Param("ids") Collection<Long> ids
);
```

Service:

```java
Page<Long> idPage =
    repository.findPageIdsByStatus("PAID", pageable);

if (idPage.isEmpty()) {
    return new PageImpl<>(
        List.of(),
        pageable,
        idPage.getTotalElements()
    );
}

List<Long> orderedIds = idPage.getContent();
List<PurchaseOrder> loaded =
    repository.findWithCustomerAndItemsByIdIn(orderedIds);

Map<Long, PurchaseOrder> byId = loaded.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = orderedIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();

Page<PurchaseOrder> result = new PageImpl<>(
    ordered,
    pageable,
    idPage.getTotalElements()
);
```

The first query paginates across root orders, and the second fetches associations for at most one page of IDs. If collections contain huge item counts, the second query can still return a large result; consider loading items separately via a DTO query with `order_id IN (...)` or using batch fetching.

Both queries need consistent read semantics. If data can mutate between reads, wrap them in a transaction with appropriate isolation or accept that associations may reflect a slightly different instant. For read-heavy apps, weigh the cost of holding long snapshots.

### 6.5. Batch Fetching

If you prefer not to join multiple associations in one query, instruct Hibernate to load lazy associations in batches.

Configure on the association:

```java
@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<OrderItem> items = new ArrayList<>();
```

Or globally by default:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 50
```

Instead of issuing one query per collection, Hibernate groups pending keys into batched `IN (...)` queries. Batch fetching cuts round-trips while still loading entities/collections and potentially fetching more data than a projection. Size batches according to page size, association count, and database bind-parameter limits.

### 6.6. Projections Are Usually Best for List Screens

When a list screen only needs customer name and a few order fields, a flat projection is simpler and cheaper than loading entities and fetch-joining associations:

```java
@Query("""
    SELECT new com.example.orders.OrderSummary(
        p.id, p.status, p.totalAmount, p.createdAt, c.fullName
    )
    FROM PurchaseOrder p
    JOIN p.customer c
    WHERE p.status = :status
    """)
Slice<OrderSummary> findOrderSummaries(
    @Param("status") String status,
    Pageable pageable
);
```

Projections do not populate the persistence context like entity queries. They excel for read models and list APIs. For use cases that mutate entities or invoke domain behavior, stick with entities and explicit fetch plans.

## 7. Deep Pagination and Keyset Pagination

### 7.1. Offset Pagination

Spring Data `Pageable` normally uses offset pagination, equivalent to:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
```

With large offsets, MySQL must locate and discard all skipped rows before returning the final 20. Queries grow progressively slower on deep pages. Inserts or deletes between requests can also cause users to see duplicate or skipped rows if ordering is unstable.

### 7.2. Keyset/Seek Pagination

Keyset pagination uses values from the last row of the previous page as the starting cursor for the next page. For sort order `created_at DESC, id DESC`:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

`id` acts as a tie-breaker ensuring unique ordering. Ensure `lastCreatedAt` and `lastId` come from the last row of the prior page. If sorting involves nullable columns, explicitly define `NULL` ordering and matching seek predicates.

Native repository query example:

```java
@Query(value = """
    SELECT p.id AS id,
           p.status AS status,
           p.created_at AS createdAt
    FROM purchase_orders p
    WHERE p.status = :status
      AND (
          p.created_at < :lastCreatedAt
          OR (p.created_at = :lastCreatedAt AND p.id < :lastId)
      )
    ORDER BY p.created_at DESC, p.id DESC
    LIMIT :pageSize
    """, nativeQuery = true)
List<NativeOrderCursorRow> findNextOrderRows(
    @Param("status") String status,
    @Param("lastCreatedAt") LocalDateTime lastCreatedAt,
    @Param("lastId") Long lastId,
    @Param("pageSize") int pageSize
);
```

This is the subsequent-page query; the first page requires a separate query without seek predicates. Since the native query writes `LIMIT` directly, do not pass `Pageable` so limit/offset is not applied twice. Validate `pageSize` in the service layer and keep it within allowed bounds.

Keyset pagination fits "Load more" buttons, batch jobs, and forward-scrolling feeds. It does not natively compute total page counts. If the application must jump straight to page 5,000, offset pagination may still be needed despite higher cost.

### 7.3. Indexing for MySQL Pagination

For queries filtering on `status` and sorting by `created_at DESC, id DESC`, evaluate a composite index:

```sql
CREATE INDEX idx_orders_status_created_id
ON purchase_orders (status, created_at DESC, id DESC);
```

Index column order must align with filter predicates and sort order. Verify the execution plan:

```sql
EXPLAIN ANALYZE
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Never create an index solely because a query has `ORDER BY`. Indexes increase write overhead and storage footprint. Evaluate read/write ratio, cardinality, status selectivity, and actual execution plans before deciding.

## 8. DTOs at the Service and API Layers

Never serialize entities directly from controllers. Entities can contain lazy proxies, bidirectional cycles, internal fields, and uninitialized associations. Invoking getters during serialization can trigger unexpected queries or fail with `LazyInitializationException`.

Convert projections/DTOs into response models inside the service:

```java
public record OrderListResponse(
    Long id,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String customerName
) {}

public Page<OrderListResponse> getOrders(
        String status,
        Pageable pageable) {

    return repository.findOrderRows(status, pageable)
        .map(row -> new OrderListResponse(
            row.getId(),
            row.getStatus(),
            row.getTotalAmount(),
            row.getCreatedAt(),
            row.getCustomerName()
        ));
}
```

The API accepts only validated page and sort parameters:

```java
@GetMapping("/orders")
public Page<OrderListResponse> listOrders(
        @RequestParam String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    Pageable pageable = PageRequest.of(
        Math.max(page, 0),
        safeSize,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );
    return orderService.getOrders(status, pageable);
}
```

This controller snippet is illustrative; handle invalid parameters and error payloads per your API standards. If the repository query has a fixed sort or uses native SQL, never forward arbitrary request sorts into it.

## 9. Open Session in View and Data-Loading Boundaries

In web applications, Open Session in View (OSIV) keeps the persistence context open until the HTTP response is rendered. Consequently, lazy associations can be loaded during response serialization, causing N+1 queries in the web layer after the service method has returned.

Disable OSIV to force explicit data loading inside the transaction/service layer:

```yaml
spring:
  jpa:
    open-in-view: false
```

Disabling OSIV does not fix N+1 by itself. If a service returns entities with uninitialized lazy associations, the controller/serializer will throw `LazyInitializationException`. Return projections/DTOs or use explicit fetch plans inside the service transaction. This exposes missing fetch requirements early instead of letting them trigger silent queries during serialization.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| First-page API runs two queries | `Page` executes data query and count query | Use `Slice` or `List` when total count is unneeded. |
| Total element count exceeds actual orders | `countQuery` counts joined rows instead of root entities | Use `COUNT(DISTINCT root.id)` when joins multiply rows. |
| Native query paginates incorrectly | Complex SQL not rewritten as expected or contains manual `LIMIT` | Declare `countQuery`, inspect actual SQL, and avoid double-limiting. |
| Native query sorting fails | Framework cannot rewrite dynamic `ORDER BY` | Use fixed `ORDER BY` or allowlisted sort columns. |
| N+1 when reading customer | Lazy association accessed in a loop | Use projection, to-one fetch join, `EntityGraph`, or batch fetching. |
| N+1 during JSON serialization | Serializer accesses lazy associations | Return DTOs/projections, disable OSIV, and load data in service. |
| Page missing orders or duplicating orders | Collection fetch join multiplies rows; non-unique sort | Avoid paginating collection fetches; include unique tie-breaker in sort. |
| Hibernate loads entire table when paginating | Pagination over collection fetch join runs in memory | Enable `fail_on_pagination_over_collection_fetch`, use two-step ID pagination, or use projections. |
| Deep pages are very slow | Large `OFFSET` | Consider keyset pagination and composite indexes. |
| Projection returns null fields | Alias mismatches getter or column type incompatible | Define explicit aliases and verify JDBC type mapping. |
| `LazyInitializationException` after disabling OSIV | Service returned entity with unloaded lazy associations | Load with proper fetch plan or map to DTOs inside the transaction. |

## 11. Workflow for Optimizing a List API

1. List the exact fields the API must return and the supported filters/sorts.
2. Choose `Page`, `Slice`, or `List` based on metadata needs.
3. Use projections when only a subset of columns is needed; use entities when domain behavior is required.
4. If using native SQL, declare `countQuery` and bind every input parameter.
5. Identify which associations must load; prefer to-one fetches or explicit DTO joins.
6. Avoid collection fetch joins on paginated queries.
7. Enable SQL logs/statistics in tests to count queries and detect N+1.
8. Run `EXPLAIN ANALYZE` on MySQL queries against production-like data.
9. Evaluate offset versus keyset pagination and add indexes matching filters/sorts when justified by evidence.
10. Test the API with many orders, many customers, and many items; compare query counts, latency, and pagination accuracy.

## 12. Self-Check Exercises

1. What is the key difference between `Page` and `Slice`?
2. Why can `Page` slow down an API even when fetching 20 rows is fast?
3. When a native query joins a child table, why might the count query need `COUNT(DISTINCT p.id)`?
4. How must columns be aliased for an interface projection to map to getters?
5. How does N+1 occur when accessing `order.getCustomer()` in a loop?
6. Why is collection `JOIN FETCH` unsuitable for direct pagination?
7. When should you prefer `@BatchSize` over a fetch join?
8. Why does keyset pagination require a unique, deterministic ordering?
9. Does disabling OSIV automatically eliminate N+1 queries?
10. For a query filtering on `status` and sorting by `created_at, id`, what should you evaluate before creating a composite index?

**Answer Hints:** (1) `Page` normally runs a count query and exposes totals; `Slice` only checks if a next page exists. (2) The count query can cost more than the page query, especially with complex joins/filters. (3) Joins can emit multiple rows per parent; the count must count distinct parents. (4) Aliases must match projection property/getter names, e.g., `customerName` for `getCustomerName()`. (5) The list query is query 1, and each unloaded lazy customer can trigger an extra query. (6) Joins multiply parent rows so SQL limit applies to joined rows; Hibernate falls back to in-memory pagination. (7) When batch-loading multiple lazy associations while avoiding massive joins or Cartesian products. (8) Without unique sorting, tied rows can duplicate or drop across page boundaries. (9) No; it merely exposes lazy-loading boundaries, so the app must still choose an explicit fetch plan or projection. (10) Selectivity, cardinality, index column order, write overhead, and `EXPLAIN ANALYZE`.

## References

- [Spring Data JPA Reference: Paging, Iterating Large Results, Sorting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data JPA Reference: Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA Reference: Declaring Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Hibernate ORM User Guide: Fetching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide: Batch fetching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch-fetching)
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
