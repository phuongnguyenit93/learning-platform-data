# Designing Sort Order and Indexes for Keyset

## Objectives

Keyset scrolling is a technique for fetching data in windows by continuing from the sort values of the last-read record. Instead of asking the database to skip thousands or millions of rows with OFFSET, the next query uses a WHERE predicate based on the sort keys to continue from a known position.

Keyset is only effective when the sort order is designed to be stable and the database has suitable indexes. In Spring Data JPA, the Scroll API represents each group of results with `Window<T>`, and `ScrollPosition.keyset()` starts a keyset scroll traversal.

After this lesson, you will be able to:

- Distinguish between offset scrolling and keyset scrolling.
- Design deterministic sort orders for data with duplicate values.
- Understand lexicographic keyset predicates.
- Use `Window<T>`, `ScrollPosition`, and `WindowIterator`.
- Choose non-null fields with stable ordering.
- Design composite indexes matching filter predicates and ORDER BY.
- Understand the impact of concurrent updates, projections, and query method limitations.
- Benchmark with execution plans and test against a real database.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. The Scroll API has been available since Spring Data 3.1; verify the Spring Data version managed by your project.

## 1. Why Does OFFSET Become Expensive?

Traditional pagination typically uses `Pageable` or `LIMIT/OFFSET`. For example:

```sql
SELECT id, order_number, created_at, total
FROM orders
WHERE status = 'PAID'
ORDER BY created_at ASC, id ASC
LIMIT 100 OFFSET 500000;
```

The application only receives 100 rows, but the database may have to locate, sort, and traverse a large volume of results before returning the slice starting at offset 500,000. Cost generally increases with large offsets, depending on indexes, query plans, and the database.

OFFSET is also sensitive to data changes between reads. If a new record is inserted before the offset position, the next page may duplicate or skip records compared to the previous read. Deleting or updating records can also shift row positions.

OFFSET remains useful when jumping to an arbitrary page is required, when datasets are small, or when users need page numbers/total record counts. For sequential processing of large datasets, keyset is usually a better fit.

## 2. How Does Keyset Scrolling Work?

Keyset remembers the sort values of the last row in the current window. The next query uses those values to find rows that follow it in the same order.

Suppose the order is:

```sql
ORDER BY created_at ASC, id ASC
```

After reading the last row with:

- `created_at = 2026-01-10T09:30:00Z`
- `id = 420`

the continuation condition is logically:

```sql
WHERE created_at > :lastCreatedAt
   OR (
       created_at = :lastCreatedAt
       AND id > :lastId
   )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

This condition means:

1. Fetch rows with created_at greater than the last timestamp.
2. If created_at is equal, fetch rows with id greater than the last ID.
3. Sort in the defined order and fetch the next window.

This is a lexicographic comparison across multiple keys. For three ascending sort fields, the general form is:

```text
k1 > v1
OR (k1 = v1 AND k2 > v2)
OR (k1 = v1 AND k2 = v2 AND k3 > v3)
```

For descending order, the corresponding comparison changes to less than. If mixing ASC and DESC, each comparison must match the direction of that field. Spring Data builds the continuation condition from the keyset; you do not need to concatenate WHERE strings manually when the Scroll API is supported.

## 3. Sort Order Must Be Deterministic and Stable

A good sort order must uniquely determine the position of each row. Sorting solely by `createdAt` is usually insufficient because multiple orders can be created at the same instant.

Non-deterministic example:

```sql
ORDER BY created_at ASC
```

If the last row of a window shares the same created_at with several other rows, the database does not guarantee the relative order among rows with equal sort values. The cursor lacks enough information to distinguish the exact position.

Add a unique key as the final criterion:

```sql
ORDER BY created_at ASC, id ASC
```

`id` distinguishes rows that have the same created_at. Spring Data keyset scrolling automatically appends the primary key (or the remaining parts of a composite primary key) to the ordering to ensure a deterministic keyset. Declaring the ID explicitly in the method/query is still useful because it clarifies business ordering and makes index design easier to verify.

### 3.1. Choosing Sort Keys

Typically suitable sort keys:

- Immutable creation timestamps such as `createdAt`.
- Sequential codes or IDs.
- A non-null business value that rarely changes.
- Multiple combined fields with a unique key as a tie-breaker.

Avoid using frequently modified fields like `displayName`, `priority`, or `status` as the primary cursor if rows can change position while scrolling. When a sort key changes, a row can move from before the cursor to after the cursor or vice versa, causing duplicates or skipped rows across a multi-query traversal.

When sorting by multiple criteria, clearly define the precedence and direction of each field. Ensure the final combination is unique; Spring Data automatically appends the primary key when needed.

### 3.2. Sort Keys Must Be Non-Null

Keyset filtering requires the properties used for sorting to be non-nullable. Comparisons with NULL have special SQL semantics and vary by database; operators like `>`, `<`, or `=` are not sufficient to form a reliable cursor for null values.

Unsuitable example:

```sql
ORDER BY shipped_at ASC, id ASC
```

if `shipped_at` allows nulls.

Prefer a non-null field:

```java
@Column(name = "created_at", nullable = false)
private Instant createdAt;
```

Also ensure the database actually enforces a `NOT NULL` constraint. The `nullable = false` attribute assists mapping/schema generation; if the schema is managed by Flyway or Liquibase, the migration must also define the corresponding constraint.

If business rules allow the shipping date to be undetermined, do not use that nullable field as a keyset sort key. You can use createdAt and id, or design another non-null sort key column. Do not rely on nulls-first/nulls-last to work around keyset limitations.

## 4. Entity and Composite Index Example

Suppose we need to scroll paid orders by creation time.

```java
@Entity
@Table(
    name = "orders",
    indexes = {
        @Index(
            name = "idx_orders_status_created_id",
            columnList = "status, created_at, id"
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal total;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Indexes declared in `@Table(indexes = ...)` can be used by the provider during schema generation. In production, if the schema is managed with migrations, create indexes in Flyway/Liquibase to control naming, column order, and deployment behavior.

SQL migration example:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders (status, created_at, id);
```

The index consists of:

1. `status`: equality filter predicate.
2. `created_at`: primary sort key.
3. `id`: unique tie-breaker.

This structure fits queries with `status = ?` and ordering `created_at, id`. It is a common design pattern, not a formula to apply mechanically to every database or data distribution.

## 5. Composite Index Design Rules

A keyset query typically combines filter predicates with cursor continuation predicates:

```sql
WHERE tenant_id = ?
  AND status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

A reasonable starting point for an index is:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at, id);
```

### 5.1. Put Equality Predicates First

For queries with stable equality predicates such as tenant_id and status, they are typically placed before the sort columns:

```text
(tenant_id, status, created_at, id)
  equality   equality   order      tie-breaker
```

Once the first two columns are fixed by equality, the database can enter the corresponding index range and read along created_at/id.

If a query does not filter by tenant_id or status, the index may not be utilized as effectively as expected due to the B-tree leftmost-prefix rule. If multiple distinct query patterns need optimization, separate indexes may be required for each pattern.

### 5.2. Column Order Matters Greatly

The following indexes are not equivalent:

```sql
CREATE INDEX idx_a ON orders (status, created_at, id);
CREATE INDEX idx_b ON orders (created_at, id, status);
```

Index A prioritizes queries filtering by status and then reading by created_at/id. Index B prioritizes created_at/id ordering and may be poorly suited when status is the primary filter condition.

There is no single universal index optimal for all queries. Start from the actual WHERE, JOIN, and ORDER BY clauses, then inspect the execution plan.

### 5.3. ASC, DESC, and Index Direction

For example:

```sql
ORDER BY created_at DESC, id DESC
```

Some databases can scan a B-tree backward to serve a uniformly reversed order. For mixed-direction orders such as:

```sql
ORDER BY created_at DESC, id ASC
```

the database may need an index declared with matching column directions or may choose a different plan. Syntax and optimization capabilities differ across databases. Never assume every ASC index serves all ASC/DESC combinations well; verify with EXPLAIN.

### 5.4. Covering Indexes and INCLUDE

Some databases support INCLUDE columns or covering indexes. If a projection only reads order_number and total in addition, you can consider placing those columns in the index payload instead of the sort key.

Example for databases supporting INCLUDE syntax:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders (status, created_at, id)
    INCLUDE (order_number, total);
```

INCLUDE is not portable SQL syntax and does not carry identical semantics on every database. Wider indexes increase storage size, INSERT/UPDATE overhead, and maintenance cost. Only add columns when execution plans and metrics show covering indexes are beneficial.

## 6. Spring Data JPA Scroll API

Spring Data provides the Scroll API to retrieve results in windows. Key types:

- `Window<T>`: a group of results along with continuation information.
- `ScrollPosition`: the starting or continuation position.
- `ScrollPosition.keyset()`: the initial position for keyset scrolling.
- `WindowIterator<T>`: a utility for iterating across multiple Windows without manually managing the cursor loop.

Repository example using a derived query:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Window<PurchaseOrder>
    findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus status,
            ScrollPosition position
    );
}
```

The method name defines:

- `First100`: limits each Window to at most 100 orders.
- `ByStatus`: filters by status.
- `OrderByCreatedAtAscIdAsc`: sorts ascending by creation time and ID.
- `ScrollPosition`: accepts the scroll continuation position.

### 6.1. Iterating with WindowIterator

```java
WindowIterator<PurchaseOrder> orders = WindowIterator.of(
        position -> repository
                .findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                        OrderStatus.PAID,
                        position
                )
).startingAt(ScrollPosition.keyset());

while (orders.hasNext()) {
    PurchaseOrder order = orders.next();
    process(order);
}
```

`WindowIterator` fetches the next Window on demand and manages ScrollPosition. This is suitable when processing entities sequentially without holding all results in a List.

If batch-level processing is needed, you can call the repository directly and use the Window API:

```java
Window<PurchaseOrder> window =
        repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                OrderStatus.PAID,
                ScrollPosition.keyset()
        );

while (!window.isEmpty()) {
    window.forEach(this::process);

    if (window.isLast()) {
        break;
    }

    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    window = repository
            .findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                    OrderStatus.PAID,
                    nextPosition
            );
}
```

The position obtained from the last element is exclusive: the next query starts after that element, avoiding re-reading the last row of the previous Window.

### 6.2. ScrollPosition.keyset() Is the Initial Position

```java
ScrollPosition position = ScrollPosition.keyset();
```

This is the starting scroll position before any row-specific continuation predicate is applied. After receiving a Window, obtain the position from the last row via `window.positionAt(window.size() - 1)`.

Do not use `ScrollPosition.offset(0)` as a substitute for the initial keyset position. Offset and keyset are two different scrolling modes.

## 7. Keyset Queries and SQL Predicates

For the order `created_at ASC, id ASC`, Spring Data constructs the continuation condition from the last row's sort values. Logically, the query looks like:

```sql
SELECT id, status, created_at, order_number, total
FROM orders
WHERE status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
FETCH FIRST 100 ROWS ONLY;
```

The result-limiting syntax depends on the database; actual SQL may use LIMIT, FETCH FIRST, or an equivalent clause. The provider-generated query may differ in parentheses and predicate structure but must express the same semantics.

The key point is that the database can seek forward from the keyset value in the index instead of skipping a huge offset. Effectiveness depends on matching indexes, query plans, cardinality, and data distribution.

## 8. Projections Must Contain the Sort Keys

Keyset scrolling needs to read the sort values to build the ScrollPosition for the next Window. Therefore, the projection result must expose all properties used in the sort order as well as the required key fields.

Interface projection example:

```java
public interface OrderScrollView {
    Long getId();
    Instant getCreatedAt();
    String getOrderNumber();
    BigDecimal getTotal();
}
```

Repository:

```java
Window<OrderScrollView>
findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
);
```

The projection includes `createdAt` and `id`, which are needed to extract the keyset. If the projection only returns `orderNumber` and `total`, Spring Data may not be able to retrieve the sort values and keyset extraction will fail.

If using DTO projections, you must also include the sort fields in the constructor/result. Whether these fields appear in the external API response is a separate decision; you can retain them in an internal DTO for scrolling and then map to another response type.

## 9. Query Method Limitations

The Scroll API supports derived query methods, Query by Example, and Querydsl. According to current Spring Data JPA documentation, scrolling with string-based query methods such as methods declared with `@Query` is not yet supported.

Therefore, the keyset example above uses a derived query:

```java
Window<PurchaseOrder>
findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
);
```

If a query is too complex to express as a derived method, options include:

- Query by Example or Querydsl if suitable.
- Custom repository implementations using Criteria API/EntityManager.
- JDBC or another query tool if fine-grained SQL control is needed.

Scrolling support varies by Spring Data version. Check the documentation for your project's exact version; do not assume a `@Query` method can accept ScrollPosition and automatically become a keyset query.

## 10. Keyset and Concurrent Data Changes

Keyset reduces the impact of row inserts/deletes before the cursor compared to OFFSET, because the next query seeks from the last sort values. However, keyset does not automatically create a consistent snapshot across multiple Windows.

For example:

1. The first Window reads up to `createdAt = 10:00, id = 500`.
2. An older order has its createdAt updated to 10:30.
3. The next query continues after cursor 10:00/500.
4. The order whose timestamp changed may appear in a later Window even though it previously sat before the cursor.

Similarly, a row whose sort key changes from after the cursor to before it may not be read in the current pass.

To mitigate this issue:

- Prefer immutable sort keys like createdAt when business rules allow.
- Add the primary key as a tie-breaker.
- Clarify whether data changes during processing are acceptable.
- If a consistent snapshot is needed, design dedicated transaction/isolation or snapshot/export mechanisms.
- For long batch jobs, consider splitting transactions per batch and persisting durable progress.

Keeping a single very long transaction can increase snapshot retention, locks, or database resource usage. Choose transaction boundaries based on consistency and job recovery requirements.

## 11. Keyset Scrolling vs. Offset and Page

| Criterion | Page/Offset | Keyset/Window |
|---|---|---|
| Resuming from position | Offset count | Sort values of the last row |
| Deep pages | Can incur cost skipping many rows | Usually more efficient with proper indexes |
| Jump to arbitrary page | Naturally supported | Not the primary goal |
| Total record count | Page can run a count query | Window does not provide total count |
| Ordering | Needs stable sort | Needs stable sort and non-null keyset fields |
| Projection | Depends on query | Must contain sort keys |
| Data changing between reads | Offset easily shifts position | Less shifted by inserts/deletes before cursor, though sort-key updates can still affect |
| Indexes | Helpful for filtering/sorting | Indexes matching filters + sort are especially important |

Choose Page when the UI needs page numbers/total counts and users need direct page navigation. Choose keyset Window for exports, batch processing, feeds, or sequential reading of large datasets.

## 12. Verifying Indexes with Execution Plans

You cannot conclude an index is suitable from column names alone. Run EXPLAIN/EXPLAIN ANALYZE on a production-like database with similar data distribution.

PostgreSQL example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at, total
FROM orders
WHERE status = 'PAID'
  AND (
      created_at > TIMESTAMP '2026-01-10 09:30:00'
      OR (
          created_at = TIMESTAMP '2026-01-10 09:30:00'
          AND id > 420
      )
  )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

When reading the plan, pay attention to:

- Is an appropriate index scan or index-only scan used?
- Does the database have to sort a large number of rows?
- How many rows are read to return 100 rows?
- Which filters are applied during the index scan and which remain afterward?
- Are buffer reads and execution times stable as the cursor moves to different positions?
- Is the index still used when tenant/status values change?

`EXPLAIN ANALYZE` executes the query. Run it in a test environment or on appropriate data; avoid running heavy queries arbitrarily on production.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Keyset misses or duplicates rows | Non-unique sort or mutable sort keys | Use a stable order and unique key |
| Keyset produces erratic results with nulls | Nullable sort property | Use NOT NULL sort keys |
| Error extracting keyset from projection | Projection missing sort property | Expose all required sort fields and ID |
| Deep queries remain slow | Index does not match filters/ORDER BY | Design composite index and inspect EXPLAIN |
| Index not chosen | Wrong column order or query misses leftmost prefix | Compare WHERE, ORDER BY, and data distribution |
| Unstable sort across rows sharing timestamp | Sorting only by createdAt | Add ID as tie-breaker |
| @Query method cannot scroll | String-based query scrolling unsupported in current version | Use derived query, QBE, Querydsl, or custom implementation |
| Next Window duplicates last row | Wrong position used or manual inclusive cursor applied | Use positionAt on the last element; ScrollPosition is exclusive |
| Rows appear/disappear while job runs | Sort key updated between Windows | Prefer immutable sort keys or use an appropriate snapshot |
| Indexes slow down writes | Too many or overly wide indexes | Measure write cost and keep only beneficial indexes |

## 14. Keyset and Index Design Checklist

- [ ] Choose a sequential-reading use case; confirm whether total record count or page jumping is actually required.
- [ ] Define a clear and stable sort order.
- [ ] Include a unique key to distinguish rows sharing sort keys; Spring Data appends primary key when needed.
- [ ] Ensure all sort properties used for keyset are non-null.
- [ ] Prefer sort keys that rarely change during scrolling.
- [ ] Projections return all required sort fields and keys.
- [ ] Use `Window<T>` and `ScrollPosition.keyset()` or `WindowIterator`.
- [ ] Check version: string-based `@Query` scrolling may not be supported.
- [ ] Design composite indexes around equality filters followed by sort order.
- [ ] Consider ASC/DESC, leftmost prefix, cardinality, and index write overhead.
- [ ] Use EXPLAIN/EXPLAIN ANALYZE to confirm the query plan.
- [ ] Test with duplicate sort keys, null data, and concurrent updates.
- [ ] Define transaction/snapshot boundaries and batch job resumption on failure.

## 15. References

- [Spring Data JPA Reference — Scrolling and Keyset Filtering](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.scrolling)
- [Spring Data Commons — ScrollPosition API](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data JPA Reference — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

## Conclusion

Keyset scrolling resumes queries from the sort values of the last-read row, helping avoid large OFFSET costs during sequential data processing. For keyset to work accurately, you need a stable order, non-null sort keys, and projections containing enough fields to construct the cursor. Spring Data appends the primary key to the keyset when needed to distinguish rows sharing the same sort values.

Composite indexes should reflect equality conditions in WHERE before ORDER BY columns, though the final column order must be verified with execution plans on a real database. Prefer immutable sort keys, add a tie-breaker, account for concurrent updates, and choose appropriate transactions. When these elements are designed together, keyset scrolling can process large datasets with more stable query costs.
