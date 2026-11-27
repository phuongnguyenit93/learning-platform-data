# Analyzing N+1 Queries, Count Queries, and Deep Offset Pagination

A list endpoint can look simple: fetch orders, display the customer name, line count, total amount, and allow paging. Yet if each order triggers additional queries to fetch its customer or count its lines, the application can fall into the N+1 problem. If the screen also runs an expensive `COUNT(*)` and uses a very large `OFFSET`, the database ends up doing far more work than the number of rows actually returned.

Spring Data R2DBC does not automatically eliminate these problems simply because database access is reactive. `Flux.flatMap(...)` can issue multiple queries concurrently, yet the number of round trips still grows with the number of records. `Pageable` or SQL `OFFSET` expresses pagination, yet it does not make deep offsets cheap. Improving performance requires examining SQL statement counts, join cardinality, counting overhead, pagination ordering, indexes, and how clients traverse the data.

## 1. What Is N+1?

N+1 happens when an application runs one query to retrieve a list of N records and then runs an extra query per record to load related data.

For example, fetching 100 orders in one query, then calling `customerRepository.findById(...)` for each order to obtain the customer name. Total queries can be:

\[
1 + N = 1 + 100 = 101 \text{ queries}
\]

N+1 commonly arises when code maps an object graph element by element, counts children per parent, or calls a repository inside a loop.

| Data to Display | Way That Easily Triggers N+1 |
|---|---|
| Customer name for each order | Calling `findById(customerId)` per order |
| Line count for each order | Calling `countByOrderId(orderId)` per order |
| Product name in each line item | Calling `findById(productId)` per line |
| Associated permissions or status | Calling another repository per user for metadata |
| Comment count for each post | Running a separate `COUNT(*)` per post |

N+1 is independent of synchronous vs. reactive APIs. A JDBC loop can produce N+1; a `Flux.flatMap` chain with R2DBC can produce N+1 just as easily.

## 2. Example of N+1 in Reactive Code

Suppose we have these repositories:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
    Flux<Order> findByStatus(String status);
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {
    Flux<OrderLine> findByOrderId(Long orderId);
}
```

A service that is easy to write yet creates N+1:

```java
public Flux<OrderListItem> findOrderList(String status) {
    return orderRepository.findByStatus(status)
        .flatMap(order -> customerRepository.findById(order.customerId())
            .flatMap(customer -> orderLineRepository.findByOrderId(order.id())
                .count()
                .map(lineCount -> new OrderListItem(
                    order.id(),
                    order.orderNo(),
                    customer.displayName(),
                    lineCount
                ))));
}
```

If the list has N orders, this flow can execute:

- 1 query to fetch the order list.
- N queries to fetch customers.
- N queries to count order lines.

That totals roughly `1 + 2N` queries. With 100 orders, that could mean 201 round trips.

Reactive programming only expresses asynchronous I/O and signal coordination. It does not merge independent queries into a single query. `flatMap` may run multiple queries concurrently, but query count remains O(N); high concurrency can even hit the database with a burst of load.

Changing `flatMap` to `concatMap` does not remove N+1 either. `concatMap` merely runs sequentially and lowers concurrent operations; it still sends each individual query.

## 3. Why Does N+1 Hurt Performance Even When Each Query Is Fast?

The cost of a query is more than database SQL execution time. A round trip also involves:

- Acquiring a connection or waiting for the pool to grant one.
- Encoding and sending the request over the network.
- Database parsing, planning, and executing SQL.
- Sending results back to the driver.
- Decoding rows and mapping them to Java objects.
- Propagating signals through the reactive pipeline.

If each query averages 3 ms and there are 200 sequential queries, total wait time can reach hundreds of milliseconds before counting other overhead. If run concurrently, latency may drop in some cases, yet the database must process many statements, hold multiple connections/slots, and strain the pool.

N+1 also makes latency unpredictable: a 10-row list looks fast, while a 1,000-row list triggers thousands of queries. Always monitor query counts as page size grows rather than measuring only a tiny fixture.

## 4. Detecting N+1 with Query Counts and Metrics

Common indicators:

- Logs show the same SQL statement executing repeatedly with different IDs.
- Query count rises nearly linearly with the number of rows in the response.
- An endpoint executes many short queries yet suffers high overall latency.
- Pool acquires or active connection counts spike as page size increases.
- Count queries or metadata lookups repeat inside loops.

To detect N+1, you can:

1. Enable selective SQL logging in development/test environments.
2. Collect query count, query duration, and operation names via R2DBC-compatible metrics or instrumentation.
3. Use an R2DBC proxy/instrumentation if the project needs per-statement visibility.
4. Compare query counts when increasing page size from 10 to 50 or 100.
5. Write integration tests verifying an endpoint emits a fixed number of queries or scales by batch count rather than per row.

Do not log sensitive bind parameters in production. SQL logs and metrics require redaction, sampling, and cardinality limits.

## 5. Approach 1: Using JOINs and Projections for Display Data

If a screen only needs a few fields from order and customer, a single JOIN query mapped straight into a DTO avoids loading full entity graphs.

DTO:

```java
public record OrderListItem(
    Long orderId,
    String orderNo,
    String customerName,
    String status
) {}
```

Query via `DatabaseClient`:

```java
public Flux<OrderListItem> findOrderList(String status, int limit, long offset) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   c.display_name AS customer_name
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
            """)
        .bind("status", status)
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> new OrderListItem(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("customer_name", String.class),
            row.get("status", String.class)
        ))
        .all();
}
```

The SQL example uses `LIMIT/OFFSET` syntax common in PostgreSQL/MySQL; other DBMSs may require their own pagination syntax. The key point is returning needed DTO fields in one query instead of running a customer query per order.

Projections are often advantageous because:

- Only required columns are read.
- Round trips are reduced.
- Unnecessary large object graphs are avoided.
- API contracts stay explicit and decoupled from entity structure.

Do not join every table just because you can. Every JOIN alters cardinality and can multiply rows; choose relationships carefully and inspect the execution plan.

## 6. Approach 2: Batch Fetching by ID Set

If you want to keep separate repositories per aggregate or a join is unsuitable, fetch the parent list first, collect the related IDs, and load child data in a single `IN` query.

Example fetching orders, then collecting distinct customer IDs:

```java
public Mono<List<OrderListItem>> findOrderList(String status) {
    return orderRepository.findByStatus(status)
        .collectList()
        .flatMap(orders -> {
            if (orders.isEmpty()) {
                return Mono.just(List.of());
            }

            Set<Long> customerIds = orders.stream()
                .map(Order::customerId)
                .collect(Collectors.toSet());

            return customerRepository.findAllById(customerIds)
                .collectMap(Customer::id)
                .map(customers -> orders.stream()
                    .map(order -> {
                        Customer customer = customers.get(order.customerId());
                        return new OrderListItem(
                            order.id(),
                            order.orderNo(),
                            customer == null ? null : customer.displayName(),
                            order.status()
                        );
                    })
                    .toList());
        });
}
```

Here, one query fetches customers by ID set rather than one per customer. For N orders, there are typically two main queries: one for orders and one for customers. If order lines are also needed, collect order IDs and fetch all lines for the page in another single query.

Batch fetching works well when:

- Relationships can be loaded independently by ID set.
- You want to avoid writing a complex JOIN.
- You want to reuse repository mappings.
- ID counts are bounded by page/batch size.

Note: `collectList()` holds the entire list in memory. Limit page size before collecting. For very large lists, process in batches instead of collecting all results.

## 7. Batch Fetching One-to-Many Counts to Avoid Per-Parent Count Queries

Suppose a screen needs the number of lines per order. Instead of calling `count()` for each order, fetch counts for the entire set of order IDs:

```sql
SELECT order_id, COUNT(*) AS line_count
FROM order_line
WHERE order_id IN (:orderIds)
GROUP BY order_id;
```

Then map results into an `orderId -> lineCount` map and merge with the order list. Orders with no lines receive a default of 0.

With `R2dbcEntityTemplate`, you can use Criteria `IN`:

```java
Query query = Query.query(Criteria.where("orderId").in(orderIds));

return template.select(query, OrderLine.class)
    .all();
```

This illustrates the template API; property names in Criteria must match entity mapping metadata and should be verified against your Spring Data version. For aggregate queries, `DatabaseClient` is usually clearer because you can write `GROUP BY` directly.

When using named collection parameters in `DatabaseClient`, verify how your Spring Framework/driver version expands bind lists. For strict cross-driver portability, generate bind markers matching the element count via a controlled helper and bind each value individually; never concatenate user values into SQL.

## 8. Avoiding N+1 When Combining Multiple Aggregations

An order page might require:

- Customer info.
- Line count.
- Total amount.
- Latest payment status.

Do not run four queries per order. Build a read query joining aggregated subqueries grouped by order ID:

```sql
SELECT o.id,
       o.order_no,
       c.display_name AS customer_name,
       COALESCE(lines.line_count, 0) AS line_count,
       COALESCE(lines.total_amount, 0) AS total_amount,
       payment.status AS payment_status
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
LEFT JOIN (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity * unit_price) AS total_amount
    FROM order_line
    GROUP BY order_id
) lines ON lines.order_id = o.id
LEFT JOIN latest_payment payment ON payment.order_id = o.id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

`latest_payment` here represents a subquery/view guaranteed to produce at most one row per order. Joining all payments or order lines directly without controlling cardinality can duplicate orders and corrupt totals.

On large tables, avoid aggregating the entire `order_line` table before filtering the page if the query planner cannot push predicates down. Limit the parent set first in a CTE/subquery, then aggregate lines only for those parents.

## 9. Paginating Parents Before Joining Collections

A common mistake is paginating directly on a one-to-many JOIN result:

```sql
SELECT o.id, o.order_no, l.id AS line_id
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
```

`LIMIT 20` here caps 20 joined rows, not 20 orders. An order with 10 lines consumes 10 result rows; the page may end up containing only a few orders despite a limit of 20.

The fix is selecting the parent page first, then joining or loading children:

```sql
WITH page_orders AS (
    SELECT id, order_no, customer_id, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT p.id AS order_id,
       p.order_no,
       c.display_name AS customer_name,
       l.id AS line_id,
       l.product_id,
       l.quantity
FROM page_orders p
JOIN customer c ON c.id = p.customer_id
LEFT JOIN order_line l ON l.order_id = p.id
ORDER BY p.created_at DESC, p.id DESC, l.id;
```

The CTE determines the parent page first. The output still has multiple rows per order when multiple lines exist, so the application must group rows into DTOs/aggregates or issue a separate batch query for lines.

An alternative is querying the order DTO page first, then batch-fetching lines for those order IDs. That can be simpler to map and avoids parent row multiplication in the main result.

## 10. N+1 Can Hide Inside COUNT Queries

A loop may fetch the order list once yet invoke a count query for each order:

```java
return orderRepository.findByStatus(status)
    .flatMap(order -> orderLineRepository.countByOrderId(order.id())
        .map(count -> new OrderSummary(order.id(), order.orderNo(), count)));
```

This is still N+1: one query for orders and N queries counting lines. Each count query may be lightweight with a proper index, yet N round trips still add overhead.

Use `GROUP BY order_id` for the parent set or an aggregated subquery. If you only need to know whether any line exists, use `EXISTS` instead of counting everything:

```sql
SELECT o.id,
       o.order_no,
       EXISTS (
           SELECT 1
           FROM order_line l
           WHERE l.order_id = o.id
       ) AS has_lines
FROM purchase_order o
WHERE o.status = :status;
```

`EXISTS` can stop at the first matching row and directly expresses an existence check. Ensure an index exists on `order_line(order_id)` to support this query.

## 11. What Are Count Queries Used For?

Traditional paginated UIs often display:

- Total matching records.
- Total pages.
- Current page.
- Items per page.

To calculate total pages, applications usually run `COUNT(*)` with the same filter criteria as the data query. If 10 million rows match, the count query may need to scan many index entries or rows to compute an exact total.

In reactive applications, do not assume `Page<T>` is free. A full `Page` typically requires both a content query and a count query. With reactive repositories, `Page<T>` is not a standard reactive return type because computing total elements requires an extra asynchronous operation; applications typically return `Flux<T>` with `Pageable` or combine content and count into a custom DTO/page model.

Example using `Mono.zip` to fetch content and count:

```java
public Mono<OrderPage> findPage(String status, int limit, long offset) {
    Mono<List<OrderListItem>> content = findOrderList(status, limit, offset)
        .collectList();

    Mono<Long> total = countOrders(status);

    return Mono.zip(content, total)
        .map(tuple -> new OrderPage(
            tuple.getT1(),
            tuple.getT2(),
            limit,
            offset
        ));
}
```

Both queries can run concurrently under `Mono.zip`, yet they remain two separate statements. Consider transactions/isolation if content and total must reflect an identical data snapshot.

## 12. Is COUNT(*) Always Expensive?

There is no single answer. Cost depends on:

- How many rows match the filter predicates.
- Whether indexes support both the filter and counting.
- Whether the database can use an index-only scan or must read heap/table pages.
- Visibility maps/MVCC and vacuum state in PostgreSQL.
- Joins, distinct, group by, or subqueries in predicates.
- Data update frequency and concurrency level.
- The execution plan chosen by the optimizer.

`COUNT(*)` on a small table can be very fast. `COUNT(*)` on a massive table with an unindexed filter can scan huge volumes of data. Do not assume every count is slow; check `EXPLAIN`/`EXPLAIN ANALYZE` on your target database with production-like data.

An exact count can take longer than fetching a small page. For example, the content query only needs 20 rows and can stop early along an index, whereas the count must tally every matching row.

## 13. Writing Count Queries with Correct Semantics

A count query must count the exact unit returned by the API. If the API returns orders, count orders—not joined rows.

Wrong example with a one-to-many join:

```sql
SELECT COUNT(*)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.status = :status;
```

An order with 5 lines gets counted 5 times. To count orders, you can write:

```sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.status = :status;
```

Or if the condition only checks whether matching lines exist, use `EXISTS`:

```sql
SELECT COUNT(*)
FROM purchase_order o
WHERE o.status = :status
  AND EXISTS (
      SELECT 1
      FROM order_line l
      WHERE l.order_id = o.id
  );
```

`COUNT(DISTINCT ...)` can incur expensive sorting or hashing to deduplicate. When the condition can be expressed with `EXISTS`, the query is often simpler and easier to optimize. Compare execution plans and verify results against fixtures containing parents with multiple children.

## 14. COUNT(*) vs. COUNT(column) vs. COUNT(DISTINCT ...)

Counting functions have distinct semantics:

| Expression | Meaning |
|---|---|
| `COUNT(*)` | Counts all rows in the result set |
| `COUNT(column)` | Counts rows where `column` is not NULL |
| `COUNT(DISTINCT column)` | Counts distinct non-NULL values |
| `COUNT(DISTINCT parent.id)` | Counts unique parents after a JOIN |

`LEFT JOIN` example:

```sql
SELECT o.id,
       COUNT(*) AS joined_rows,
       COUNT(l.id) AS line_count
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
GROUP BY o.id;
```

An order without lines still produces one row after `LEFT JOIN`, so `COUNT(*)` returns 1 while `COUNT(l.id)` returns 0. When counting children, pass a non-null child column such as its primary key.

If another one-to-many table is joined, row counts multiply further. Even `COUNT(l.id)` would then double-count lines; pre-aggregate or use `COUNT(DISTINCT l.id)` as appropriate.

## 15. Optimizing Counts with Predicates and Indexes

Suppose an endpoint filters by `tenant_id`, `status`, and a time range:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime;
```

A suitable index helps the database narrow the counted range faster. For example, a composite index starting with equality filters followed by range/sort columns:

```sql
CREATE INDEX idx_order_tenant_status_created
ON purchase_order (tenant_id, status, created_at DESC, id DESC);
```

Index column order should follow query workload and selectivity. Do not create indexes solely because one query has many predicates; every index adds insert/update overhead and storage cost.

On PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` reveals scan types, actual row counts, buffer hits/reads, and timings. `EXPLAIN ANALYZE` executes the query, so be careful with writes and production environments.

On MySQL, SQL Server, and Oracle, use each engine's execution plan tools. Do not carry PostgreSQL plan conclusions blindly over to another database.

## 16. Not Every API Needs an Exact Total

Many UIs only need to know whether a next page exists. Running an exact count across millions of rows in those cases is wasted work.

A common pattern is fetching `limit + 1` rows:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize OFFSET :offset;
```

Where `fetchSize = pageSize + 1`. If the query returns more than `pageSize` rows, the application knows more data exists, drops the extra row, and sets `hasNext = true`.

DTO:

```java
public record OrderSlice(
    List<OrderListItem> content,
    boolean hasNext,
    int pageSize,
    long offset
) {}
```

Service:

```java
public Mono<OrderSlice> findSlice(String status, int pageSize, long offset) {
    int fetchSize = pageSize + 1;

    return findOrderList(status, fetchSize, offset)
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > pageSize;
            List<OrderListItem> content = hasNext
                ? rows.subList(0, pageSize)
                : rows;
            return new OrderSlice(content, hasNext, pageSize, offset);
        });
}
```

This is slice-style pagination: no total page count, while avoiding the count query. Validate `pageSize` with an upper bound and `offset` as non-negative.

## 17. Count Queries and Content Queries Can Observe Different Data

When running content and count queries concurrently with `Mono.zip`, another transaction can insert or delete rows between the two statements. Content and total may then reflect slightly different points in time.

Example:

1. Content query reads 20 rows.
2. Another transaction inserts 1 row.
3. Count query runs and sees the updated total.

The page result is usually fine for typical UIs, though not a strict consistent snapshot.

If the business requires content and count to match a single snapshot, execute both within a transaction at an appropriate isolation level and verify the database provides the expected snapshot semantics. This increases cost and connection hold time. For most list screens, minor eventual consistency between count and content is acceptable.

Never use `COUNT(*)` as a concurrency control mechanism. Counts can change immediately after being returned.

## 18. How Does OFFSET Pagination Work?

Offset pagination typically uses:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

`LIMIT 20 OFFSET 0` returns the first 20 rows. `LIMIT 20 OFFSET 1000` skips the first 1,000 ordered rows and returns the next 20.

Advantages:

- Easy to understand and map to page numbers.
- Users can jump directly to any page number.
- Fits UIs displaying total pages and page indexes.
- Convenient for small or medium datasets.

Disadvantages:

- The larger the offset, the more rows the database must locate/read and discard.
- Data changes between requests can duplicate or skip rows across pages.
- High page numbers can suffer high query latency.
- Accompanying count queries can cost even more than content queries.

## 19. Why Is Deep Offset Slow?

For `OFFSET 500000 LIMIT 20`, the database must determine the position of the first 500,000 ordered rows before returning the next 20. Even with a suitable index, the engine often must walk through vast numbers of index entries or rows only to discard them.

Cost typically grows with offset because the database does not automatically know the physical location of “row 500,001” under a dynamic sort/filter. The planner may pick an index scan, bitmap scan, or other plan, yet skipping huge row counts remains expensive.

That is why page 1 is fast while page 20,000 is slow, even though each page returns only 20 rows.

Do not just raise timeouts for deep pages. Determine whether UX truly requires jumping to arbitrary pages or can switch to cursor/keyset pagination.

## 20. OFFSET Pagination Is Unstable Under Data Mutations

Suppose page 1 fetches the 20 newest rows, and page 2 uses `OFFSET 20`. After the client views page 1, a new row is inserted at the top of the list. When querying page 2, row positions have shifted down by one; the client can see a duplicate row or miss one.

With deletes, subsequent rows shift up and some rows may be skipped. If a sort key changes, a row can move between pages.

To mitigate these issues:

- Use deterministic ordering with a unique tie-breaker such as `created_at, id`.
- When a strict snapshot is required, use an appropriate transaction/snapshot over a short session or an explicit snapshot token design.
- For rapidly changing lists, prefer keyset/cursor pagination.
- Never hold a database transaction open across user page flips.

Deterministic ordering avoids nondeterminism when rows share a sort key, yet it cannot prevent shifts from rows inserted or deleted between requests.

## 21. What Is Keyset Pagination?

Keyset pagination (also called seek pagination) uses values from the last row of the previous page as a cursor. The next page queries rows strictly after that cursor in the chosen sort order, rather than skipping rows with `OFFSET`.

Suppose sorting descending by `created_at`, then `id`:

```sql
ORDER BY created_at DESC, id DESC
```

First page:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Suppose the last row has `created_at = :cursorCreatedAt` and `id = :cursorId`. Next page:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

The database can use an index to seek straight from the cursor position onward. Cost does not grow linearly with page depth as deep offsets do in many workloads.

## 22. Cursors Must Include All Sort Keys

If only `created_at` is used as the cursor, two or more rows sharing the same timestamp can be skipped or duplicated. Include a unique key as a tie-breaker.

For `(created_at DESC, id DESC)`, the cursor must carry both values:

```java
public record OrderCursor(
    Instant createdAt,
    Long id
) {}
```

Response DTO:

```java
public record CursorPage<T>(
    List<T> content,
    String nextCursor,
    boolean hasNext
) {}
```

The cursor can be serialized into an opaque token, such as URL-safe Base64 JSON signed with HMAC so clients cannot tamper with values arbitrarily. APIs do not need to expose raw SQL sort keys when keeping cursors opaque.

Cursors should include or bind to the active filter and sort parameters. Do not allow a cursor issued for `status=NEW` to be reused on `status=PAID` unless the contract explicitly permits it.

## 23. Keyset Pagination Example with DatabaseClient

A repository adapter can support two paths: first page without a cursor and subsequent pages with a cursor.

```java
public Flux<OrderListItem> findNextPage(
        String status,
        Instant cursorCreatedAt,
        Long cursorId,
        int limit) {

    return databaseClient.sql("""
            SELECT id, order_no, status, created_at
            FROM purchase_order
            WHERE status = :status
              AND (
                  created_at < :cursorCreatedAt
                  OR (created_at = :cursorCreatedAt AND id < :cursorId)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """)
        .bind("status", status)
        .bind("cursorCreatedAt", cursorCreatedAt)
        .bind("cursorId", cursorId)
        .bind("limit", limit + 1)
        .map((row, metadata) -> new OrderListItem(
            row.get("id", Long.class),
            row.get("order_no", String.class),
            null,
            row.get("status", String.class)
        ))
        .all();
}
```

The example uses PostgreSQL/MySQL `LIMIT` syntax; adapt for other dialects. `limit + 1` detects `hasNext`. In a real implementation, the DTO or cursor builder needs `created_at` and `id` of the last row to construct the next cursor; avoid stripping sort keys internally before building the token.

The first page uses a similar query without the cursor condition. Always enforce an upper bound on `limit`, such as 100, so clients cannot request millions of records in a single call.

## 24. Keyset Pagination with Mixed Sort Directions

When sorting across multiple fields:

```sql
ORDER BY priority DESC, created_at ASC, id ASC
```

The cursor predicate must match the exact lexicographic order and ascending/descending direction of each column:

```sql
WHERE priority < :cursorPriority
   OR (priority = :cursorPriority AND created_at > :cursorCreatedAt)
   OR (priority = :cursorPriority
       AND created_at = :cursorCreatedAt
       AND id > :cursorId)
```

Because `priority` is descending, rows after the cursor have a smaller priority; `created_at` and `id` are ascending, so tie-breakers use greater-than comparisons. For complex sort directions, construct matching predicates and test duplicate sort-key edge cases thoroughly.

You cannot use a simple predicate like `id > :cursorId` when the primary ordering is `created_at DESC, id DESC` and ID does not reflect that order.

## 25. Handling NULLs in Keyset Pagination

Nullable sort keys complicate cursors because comparisons with NULL evaluate to UNKNOWN. For example, `created_at < :cursor` does not match rows where `created_at IS NULL`.

Options:

- Design sort keys to be non-nullable whenever possible.
- Define `NULLS FIRST`/`NULLS LAST` explicitly and write cursor predicates to match the exact rules.
- Normalize sort values with an indexed expression or computed column if appropriate.
- Encode null state alongside tie-breakers in the cursor.

For instance, PostgreSQL supports `NULLS LAST` in `ORDER BY`, yet cursor predicates must mirror that ordering explicitly. Do not assume every database shares identical null-ordering syntax.

For high-performance paginated APIs, non-nullable indexed sort keys are usually simpler and more reliable.

## 26. Indexes for Offset and Keyset Pagination

Indexes should align with filters and sort order. Example query:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Candidate index:

```sql
CREATE INDEX idx_order_tenant_status_created_id
ON purchase_order (tenant_id, status, created_at DESC, id DESC);
```

Equality filter columns typically precede sort keys in a composite index. Final index design depends on cardinality, selectivity, other workload queries, and the database optimizer.

Keyset pagination especially benefits when an index supports both cursor conditions and ordering. Without an index, even keyset queries can scan many rows. Inspect execution plans instead of assuming cursors are automatically fast.

Do not create separate indexes for every filter combination. Each index adds storage and write costs. Track common queries and choose indexes for the real workload.

## 27. Count Queries in Cursor Pagination APIs

Cursor pagination typically omits total counts. The API can return:

- `content`: current page rows.
- `nextCursor`: token for the last row.
- `hasNext`: whether more data exists.

`hasNext` is determined by fetching `limit + 1` rows. If an extra row is returned, exclude it from `content` and set `hasNext = true`.

This eliminates running `COUNT(*)` across the entire dataset on every page. For large or rapidly changing lists, this is usually a better contract than total pages.

If the business genuinely requires an exact total, expose a separate count endpoint, cache it briefly, or compute it in a reporting job. Weigh total freshness against computation cost.

## 28. When Is OFFSET Still Appropriate?

Offset pagination remains suitable when:

- The dataset is small or moderate.
- Users need to jump straight to arbitrary page numbers.
- Total page counts are a strict requirement.
- Large offsets do not occur in realistic workloads.
- Queries are well indexed and deep-page latency has been measured.
- Data changes infrequently while users browse.

You do not need to convert every endpoint to keyset pagination. Keyset makes jumping directly to page 500 difficult without storing checkpoints or another positioning mechanism. Choose pagination based on user behavior and data scale.

A practical design often uses offset for small admin grids and cursors for large feeds or timelines.

## 29. Keyset Pagination Does Not Guarantee a Fixed Snapshot

Keyset avoids skipping leading rows and prevents shifts from inserts before the cursor. However, it does not automatically create a snapshot across requests.

For example:

- An older row has its `created_at` or sort key updated, moving it past the cursor.
- A row is deleted before the client reaches a later page.
- Filters change between requests.
- A new record with a sort key after the cursor is inserted.

For greater consistency:

- Use immutable sort keys such as `created_at` and an unchanging ID.
- Embed filter/sort parameters inside the cursor token.
- If a fixed snapshot is required, use a watermark/high-water mark or business snapshot/version.
- Avoid holding transactions open across HTTP requests merely to preserve an MVCC snapshot.

A cursor can store an `upperBound` from the first page to ignore records created after browsing started. This stabilizes newly created data without handling all updates/deletes; API contracts should document the semantics clearly.

## 30. Comparing Offset and Keyset

| Criterion | Offset Pagination | Keyset / Cursor Pagination |
|---|---|---|
| Navigation | Page numbers, jump to arbitrary page | Forward/backward via cursor; arbitrary page jump is harder |
| Deep page cost | Usually scales with rows skipped | Can seek directly to cursor via index |
| Deterministic order | Needs `ORDER BY` with tie-breaker | Needs sort keys and tie-breaker in cursor |
| Mutating data across pages | Can duplicate/skip rows as positions shift | Less affected by inserts before cursor, though not a snapshot |
| Total page count | Usually paired with a count query | Usually omits count |
| Best suited for | Admin grids, moderate datasets, page jumps | Feeds, timelines, large lists, sequential browsing |
| Implementation complexity | Simple | Cursor, sort predicates, nulls, and filters need careful design |

## 31. Pagination with Spring Data R2DBC

Reactive repositories typically return `Flux<T>` for lists. Query methods or `@Query` can accept pagination parameters depending on features supported by your Spring Data R2DBC version. However, do not expect reactive repositories to return a full `Page<T>` with total count in a single simple synchronous-style call.

For custom queries, accept `Pageable` at the service layer and pass `pageSize` and `offset` as bind parameters to `DatabaseClient`, or use `R2dbcEntityTemplate` with `Query`/`Criteria` and `limit`/`offset` per your version's API.

Service example with input validation:

```java
public Mono<OrderPage> search(String status, Pageable pageable) {
    int limit = Math.min(pageable.getPageSize(), 100);
    long offset = pageable.getOffset();

    Mono<List<OrderListItem>> content =
        findOrderList(status, limit, offset).collectList();
    Mono<Long> total = countOrders(status);

    return Mono.zip(content, total)
        .map(tuple -> new OrderPage(
            tuple.getT1(), tuple.getT2(), limit, offset));
}
```

In production, validate minimum/maximum page size, non-negative offsets, allow-listed sort fields, and valid sort directions. Never interpolate client-supplied column names directly into SQL.

## 32. Building a Separate Count Query with DatabaseClient

Content queries and count queries should be optimized independently:

```java
public Mono<Long> countOrders(String status) {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM purchase_order
            WHERE status = :status
            """)
        .bind("status", status)
        .map((row, metadata) -> row.get("total", Long.class))
        .one()
        .defaultIfEmpty(0L);
}
```

Use `Long` because row counts can exceed `Integer` limits. Exact driver return types may need conversion if the database returns a different numeric type; verify mapping on the target engine.

If the content query joins `customer` only to display customer names while filtering relies solely on `purchase_order`, the count query can omit the `customer` join. Dropping unnecessary joins simplifies counting as long as filter semantics remain identical.

## 33. Caching or Estimating Total Counts When Appropriate

Some reporting screens do not require second-by-second exact totals. You can:

- Cache counts for a short TTL.
- Compute counts via batch/background jobs.
- Use database statistics/estimates on dashboards that accept approximate totals.
- Show only “more available” instead of total pages.
- Compute totals from a separately optimized read model.

When using approximate counts, both API and UI must clearly communicate that the number is an estimate. Never use estimated statistics for business controls such as quotas, billing, or authorization.

Cached counts need appropriate invalidation or TTLs. If filters have many combinations, cache keys must include tenant, status, time range, and every predicate affecting the result.

## 34. Measuring Query Plans and Benchmarking with Realistic Data

A query running fast on 100 rows says nothing about performance at 10 million rows. Build a test dataset with production-like distributions:

- Realistic parent and child volumes.
- Realistic one-to-many cardinalities.
- Realistic ratios per status and tenant.
- Duplicate sort keys and NULL values where schema permits.
- Production-equivalent indexes.
- Representative insert/update/delete rates.

Measure separately:

- Content query.
- Count query.
- Total queries per request.
- First page, middle page, and deep offset.
- Next keyset page.
- Pool acquire latency and database execution time.

Use execution plans to verify how many rows are scanned, whether indexes are used properly, and whether joins multiply cardinality. Warm up benchmarks and run multiple iterations; never draw conclusions from a single run.

## 35. Testing to Prevent N+1 Regressions

An integration test can count statements executed during a request. Use an R2DBC proxy or project instrumentation to count queries per connection or test scope.

Scenario:

1. Seed 10 orders, each with a customer and several order lines.
2. Reset the query counter.
3. Call the list service.
4. Assert DTOs have correct customer names and line counts.
5. Verify query count does not scale with order count.
6. Increase the fixture to 50 orders and verify query count remains fixed or scales by batch count rather than one query per row.

Do not hardcode fragile total counts if the framework runs metadata or auxiliary health queries; explicitly identify the business statements being counted. Tests should run against a real database and driver to measure real round trips.

## 36. Testing Count Semantics and Pagination

Cases to cover:

- Parent with zero children.
- Parent with one child.
- Parent with multiple children.
- Joining two collections to catch row multiplication.
- Filters solely on parent vs. filters involving children.
- Rows sharing identical `created_at` values to test tie-breakers.
- Rows inserted/deleted between page fetches.
- Offset 0, large offset, last page, and oversized page size requests.
- Cursor pointing to duplicate sort-key values.
- Null sort keys if schema allows them.

For count queries, compare totals against unique parents in the fixture rather than joined row counts. For keyset pagination, concatenate multiple pages and assert zero duplicate IDs and zero missing IDs on a static dataset.

## 37. Common Mistakes and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Endpoint executes hundreds of queries per page | N+1 from repository calls inside `flatMap` | JOIN projection or batch fetch by ID set |
| Switching `flatMap` to `concatMap` stays slow | Still N+1, merely shifted from parallel to sequential | Reduce query count instead of just changing concurrency |
| `COUNT(*)` returns more than parent count | Counting after a one-to-many JOIN | `COUNT(DISTINCT parent.id)` or `EXISTS`/pre-aggregation |
| Order with no lines gets count 1 | Using `COUNT(*)` after `LEFT JOIN` | Use `COUNT(child.id)` |
| First page fast, deep pages very slow | Large offset must skip many rows | Keyset pagination and indexes matching filter/sort |
| Rows repeat or vanish between pages | Non-unique sort or mutating data | Add tie-breaker; use cursors/watermarks where appropriate |
| Page shows fewer parents than limit | `LIMIT` applied after collection JOIN | Paginate parents first, then fetch children |
| Count and content disagree slightly | Two queries reading at different moments | Accept eventual consistency or use an appropriate snapshot |
| Keyset skips rows with NULL sort keys | Predicate ignores null semantics | Non-null sort keys or explicit null-ordering predicates |
| Raising concurrency overloads database | N+1 still exists and queries run concurrently | Batch queries, cap concurrency, and monitor pool |

## 38. Process for Optimizing a List Endpoint

When a list endpoint is slow, follow this sequence:

**Step 1 — Measure query count.** Record statements per request and identify queries repeating per parent.

**Step 2 — Determine exact DTO requirements.** Avoid loading full object graphs if only a few display columns are needed.

**Step 3 — Eliminate N+1.** Use JOIN projections or batch fetches by ID set; consolidate counts with `GROUP BY`.

**Step 4 — Check cardinality.** When joining collections, paginate parents first and prevent parent/aggregate multiplication.

**Step 5 — Evaluate count queries.** Decide whether exact totals are needed or `hasNext` suffices; fix count semantics and indexes.

**Step 6 — Measure deep offsets.** Benchmark first, middle, and deep pages on production-like datasets.

**Step 7 — Choose pagination strategy.** Keep offset when page jumping is required on moderate data; switch to keyset for large sequential lists.

**Step 8 — Design indexes.** Align with filters, sorts, and cursor predicates; verify execution plans.

**Step 9 — Test under concurrency.** Verify results while data changes and multiple requests run concurrently.

**Step 10 — Add regression tests.** Assert query counts, count semantics, and zero duplicates/gaps across pages.

## 39. Conclusion

N+1 queries, count queries, and deep offsets are three common reasons R2DBC list endpoints degrade as data grows. Reactive APIs do not automatically coalesce queries; calling repositories inside `flatMap` still issues one query per parent. Use JOIN projections or batched fetches by ID set, consolidate counts with `GROUP BY`/`EXISTS`, and control cardinality when joining collections.

Exact counts carry their own cost, and not every UI needs total pages. When only next-page availability matters, fetch `limit + 1` rows for a slice. Offset pagination is easy to use, yet deep pages discard many rows and shift under mutations; keyset pagination uses cursors containing all sort keys and tie-breakers to seek efficiently via indexes. Combining execution plans, workload-aligned indexes, metrics, and integration tests on real databases keeps list performance predictable as data scales.
