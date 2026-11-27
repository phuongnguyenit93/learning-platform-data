# Optimizing Count Queries and Deep Pagination

When a list screen needs to display data page by page, the application typically has to solve two distinct problems:

- **Counting total results:** to display total records, total pages, or exact navigation controls.
- **Fetching a slice of results:** to load only the records needed for display rather than reading the entire dataset.

In Spring Data JDBC, the **Page<T>** return type provides total elements and total pages, so the infrastructure may execute an extra count query. **Slice<T>** only needs to know whether a next page exists; Spring Data JDBC fetches one extra row beyond the page size to determine **hasNext**. Returning **List<T>** with **Pageable** can also fetch the requested slice without producing total-count metadata.

As offsets grow larger, queries like `LIMIT ... OFFSET ...` can force the database to walk past huge numbers of rows before returning a small slice at the end. For traversing large datasets in a deterministic order, **keyset pagination** (seek pagination) uses the values of the last record from the previous page as the starting point for the next page. The database can seek via key predicates rather than skipping thousands of results.

This lesson explains the cost of count queries, how to choose among `Page`/`Slice`/`List`, how to write accurate count queries, why deep pagination is slow, and how to transition to keyset pagination with Spring Data JDBC.

## 1. Two Tasks Behind a Page of Data

Suppose an admin screen displays orders with status `PAID`, sorted by newest creation timestamp first. Each page shows 20 orders.

A `Page<Order>` response typically requires:

1. A query fetching the 20 orders for the current page.
2. A query counting all matching orders to compute total elements and total pages.

Conceptual SQL:

~~~sql
SELECT id, order_number, created_at, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Count query:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Result might look like:

~~~text
content       = 20 orders
totalElements = 12,480
totalPages    = 624
number        = 0
size          = 20
hasNext       = true
~~~

These two queries have different objectives. The content query only needs to locate one slice of results. The count query must determine how many total rows match the predicate.

If a table has millions of records, fetching the first 20 rows can be very fast with an index, whereas the count query may still have to read many entries to determine the matching total. Consequently, tuning only the content query while ignoring the count query may miss the actual bottleneck.

## 2. Choosing Page, Slice, or List?

Spring Data JDBC supports common paginated return types in repository query methods.

| Return type | Has page data | Has total elements | How next page is determined |
| --- | --- | --- | --- |
| `Page<T>` | Yes | Yes | Based on total count and page info |
| `Slice<T>` | Yes | No | `hasNext` |
| `List<T>` with `Pageable` | Yes | No | Application coordinates navigation |
| `Stream<T>` | Stream of data | No | Sequential read and close stream |

### 2.1. Page<T>: When the UI Truly Needs the Total Count

Example repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    Page<Order> findByStatus(String status, Pageable pageable);
}
~~~

Service:

~~~java
public Page<Order> findPaidOrders(int page, int size) {
    Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")
            )
    );

    return orderRepository.findByStatus("PAID", pageable);
}
~~~

`Page<T>` fits when the UI needs to show:

- Total record count.
- Total page count.
- "Page 3 of 24".
- Direct jumping to a specific page number.
- Reports or screens requiring exact totals.

In return, a count query may run alongside the content query. The Spring Data JDBC documentation notes that queries returning `Page` may run a count query to determine total elements; the infrastructure can skip the count in certain cases where the returned row count already suffices to infer the total.

Do not pick `Page` out of habit when the UI never uses total counts. Computing an exact total can carry substantial cost.

### 2.2. Slice<T>: Only Knowing Whether More Data Exists

If the UI only has a "Next" button and needs no total page count:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    Slice<Order> findSliceByStatus(
            String status,
            Pageable pageable
    );
}
~~~

Spring Data JDBC fetches up to `pageSize + 1` rows. With a page size of 20:

- Fetches up to 21 rows.
- If 21 rows come back, returns the first 20 rows and sets `hasNext = true`.
- If at most 20 rows come back, there is no next page.

There is no need to count all matching rows just to answer "is there a next page?".

`Slice` still uses offsets when paired with `Pageable`. Thus, it eliminates the count query cost but **does not by itself solve the cost of deep offsets**.

### 2.3. List<T> with Pageable: Only Needing the Data Slice

If the application needs neither total count nor a `hasNext` flag, it can return `List`:

~~~java
public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    List<Order> findAllByStatus(
            String status,
            Pageable pageable
    );
}
~~~

This produces only the page's content list, without `Page` metadata or a count query to build that metadata.

The application must decide how to render navigation. If it needs to check for more data, fetch one extra row or use `Slice`.

### 2.4. Stream<T>: Processing Large Datasets Sequentially

With query methods returning `Stream<T>`, Spring Data JDBC can emit results incrementally as the database returns them. This reduces the need to hold the entire result set in memory.

~~~java
@Query("SELECT * FROM orders WHERE status = :status")
Stream<Order> streamByStatus(String status);
~~~

A `Stream` holds a database connection open while in use. Always close the stream, ideally via try-with-resources:

~~~java
try (Stream<Order> orders =
             repository.streamByStatus("PAID")) {

    orders.forEach(this::process);
}
~~~

`Stream` fits sequential batch processing. It is not a UI page-navigation mechanism and does not eliminate the cost of a query that scans large amounts of data.

## 3. What Does a Count Query Actually Do?

A count query returns the number of rows matching a predicate. The simplest SQL form:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Common count forms:

| Expression | Meaning |
| --- | --- |
| `COUNT(*)` | Counts all rows in the result set. |
| `COUNT(id)` | Counts rows where `id` is non-NULL. |
| `COUNT(DISTINCT customer_id)` | Counts unique non-NULL customer IDs appearing. |

If `id` is a `NOT NULL` primary key, `COUNT(*)` and `COUNT(id)` normally give the same result. `COUNT(column)` skips `NULL` values in that column; do not swap it with `COUNT(*)` arbitrarily.

### 3.1. Count Queries Do Not Need ORDER BY

Sorting does not affect the total count. Count queries should omit sorting:

~~~sql
-- Unnecessary for count
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
~~~

Preferred form:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Do not include the page's `LIMIT` and `OFFSET` in the count query when the goal is counting the entire result set.

### 3.2. Count Queries Must Preserve Filter Predicates

Content query:

~~~sql
SELECT id, order_number, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Corresponding count query:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime
  AND created_at < :toTime;
~~~

If the count query forgets a predicate such as `created_at < :toTime`, the displayed total will disagree with the dataset the user is browsing.

When queries have many optional filters, share the predicate-building logic between the content query and the count query so the two SQL statements cannot drift apart.

### 3.3. When JOINs Duplicate Rows

Suppose an order has multiple order items. Joining `orders` with `order_items` produces multiple rows for one order:

~~~sql
SELECT o.id, o.order_number, i.product_id
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.status = 'PAID';
~~~

If an order has 4 items, the JOIN output can contain 4 rows sharing the same `o.id`. When counting orders, `COUNT(*)` counts joined rows rather than aggregate roots.

Use:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.status = 'PAID';
~~~

If the goal is counting order items, `COUNT(*)` may be the right expression instead. The count must reflect the exact unit the API paginates: orders, customers, products, or joined lines.

### 3.4. Count Queries with GROUP BY or DISTINCT

When a query returns grouped or distinct results, you cannot always replace the `SELECT` list with `COUNT(*)` over the base table.

For example, a query returning one row per customer:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
~~~

To count the number of customer groups with revenue, count the subquery result:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT customer_id
    FROM orders
    GROUP BY customer_id
) grouped_customers;
~~~

Likewise, when queries use `DISTINCT`, set operations, or complex structures, count the actual result set the user sees.

## 4. Count Queries in Spring Data JDBC

### 4.1. Derived Repository Queries

For derived queries returning `Page<T>`, Spring Data JDBC can derive the count query from the query method's conditions:

~~~java
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {

    Page<Product> findByCategoryId(
            Long categoryId,
            Pageable pageable
    );

    Slice<Product> findSliceByCategoryId(
            Long categoryId,
            Pageable pageable
    );
}
~~~

Use `Page` when totals are needed. Use `Slice` when only checking whether more data exists. Both methods use the `categoryId` filter, yet return different metadata.

### 4.2. Custom SQL via @Query

Spring Data JDBC has an important limitation: string-based queries declared with `@Query` do not automatically accept `Pageable`, `Sort`, `PageRequest`, or `Limit` parameters for the framework to rewrite the SQL.

The following is not a valid pagination approach for a string-based query in Spring Data JDBC:

~~~java
@Query("SELECT * FROM orders WHERE status = :status")
Page<Order> findByStatus(
        String status,
        Pageable pageable
);
~~~

When custom SQL needs pagination, write the limit clause and bind parameters explicitly in SQL, or implement a custom repository fragment to manage both the content query and the count query.

Example SQL:

~~~sql
SELECT id, order_number, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Count query:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = :status;
~~~

Using `LIMIT` and `OFFSET` in custom SQL must be tested on the target database. If an application supports multiple dialects, do not assume vendor-specific syntax is portable everywhere.

### 4.3. Using JdbcAggregateTemplate to Construct Page Manually

`JdbcAggregateTemplate` provides `findAll(Query, Class)` and `count(Query, Class)`. You can define a base query containing only filter criteria, then construct the content query with `Pageable`:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate template;

    public ProductSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public Page<Product> findActiveProducts(Pageable pageable) {
        Query filter = Query.query(
                Criteria.where("status").is("ACTIVE")
        );

        List<Product> content = template.findAll(
                filter.with(pageable),
                Product.class
        );

        long total = template.count(filter, Product.class);

        return new PageImpl<>(content, pageable, total);
    }
}
~~~

Here:

- `filter` contains only business filter criteria.
- `filter.with(pageable)` builds the content query with offset, limit, and sort.
- `template.count(filter, Product.class)` counts all matching aggregates.
- `PageImpl` combines content, page info, and total count.

Do not pass a query that already has offset/limit into `count` when the goal is counting the entire matching dataset. Keeping the base query strictly for filters keeps both parts clean.

In current APIs, the `findAll(Query, Class, Pageable)` overload on `JdbcAggregateOperations`/`JdbcAggregateTemplate` is marked deprecated for removal. The snippet above uses `Query.with(Pageable)` alongside `findAll(Query, Class)` and constructs `Page` manually.

### 4.4. Custom Count Queries via Repository Fragments

For complex queries, a custom repository fragment gives clear control over SQL:

~~~java
public interface OrderSearchRepository {
    Page<OrderSummary> searchPaidOrders(
            Instant fromTime,
            Instant toTime,
            Pageable pageable
    );
}
~~~

The implementation can use `NamedParameterJdbcTemplate`:

~~~java
@Repository
public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public Page<OrderSummary> searchPaidOrders(
            Instant fromTime,
            Instant toTime,
            Pageable pageable
    ) {
        String from = """
                FROM orders
                WHERE status = :status
                  AND created_at >= :fromTime
                  AND created_at < :toTime
                """;

        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("status", "PAID")
                        .addValue("fromTime", fromTime)
                        .addValue("toTime", toTime);

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) " + from,
                parameters,
                Long.class
        );

        parameters
                .addValue("limit", pageable.getPageSize())
                .addValue("offset", pageable.getOffset());

        List<OrderSummary> content = jdbc.query(
                """
                SELECT id, order_number, created_at, total_amount
                """ + from + """
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """,
                parameters,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getBigDecimal("total_amount")
                )
        );

        return new PageImpl<>(
                content,
                pageable,
                count == null ? 0 : count
        );
    }
}
~~~

This example illustrates a database supporting `LIMIT/OFFSET` syntax. In multi-database applications, use an appropriate dialect or split SQL by vendor when necessary.

In particular, if clients can choose dynamic sorting, never concatenate column names from requests directly into SQL. Map sort properties through an allowlist of columns and valid `ASC`/`DESC` directions.

## 5. Why Can a Count Query Be Slow?

A count query returns very little data, yet that does not mean it is always cheap.

The database must determine how many rows match the predicate. Depending on the query and execution plan, it may have to:

- Scan the entire table.
- Scan an index.
- Read many index entries and check heap rows.
- Execute JOINs or complex filters.
- Count distinct rows.
- Compute groups after `GROUP BY`.

For example:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime;
~~~

Without a helpful index, the database may have to read a vast number of rows to determine the result.

### 5.1. Indexes Supporting Count Queries

For predicates filtering by status and timestamp:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders(status, created_at);
~~~

This index can help locate rows matching the predicate. Whether the index is used still depends on selectivity, data distribution, statistics, and the optimizer.

Adding an index does not automatically make counts fast. If most of the table has `status = 'PAID'`, the optimizer may pick another scan. Indexes also increase write cost and storage usage.

### 5.2. Covering Indexes

If every column needed by a query resides in the index, some databases can count or filter from the index without reading full row data. Exact behavior depends on the database engine, MVCC visibility, and execution plan.

Do not assume `COUNT(*)` is always constant time. Measure on your real database with production-like data.

### 5.3. Optimize Filter Predicates Before Optimizing COUNT

Several adjustments often help:

- Ensure `WHERE` predicates can use indexes.
- Avoid unnecessary functions on filtered columns if they prevent index usage.
- Only JOIN tables actually required by the filter conditions.
- Count the exact data unit needed.
- Avoid `DISTINCT` if the query does not require it.
- Exclude `ORDER BY` from count queries.
- Use half-open intervals for time ranges, e.g., `created_at >= :from` and `created_at < :to`.

For instance, instead of:

~~~sql
WHERE DATE(created_at) = :day
~~~

use a range interval:

~~~sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
~~~

The second form is usually much friendlier to an index on `created_at`, depending on the database and exact expression.

## 6. When Exact Totals Are Unnecessary

Not every screen needs an exact total.

For instance, an activity feed only has:

- A list of the 20 newest events.
- A "Load more" button.
- No display of "2,345,789 events found".

In that case, `Slice` or cursor pagination usually fits much better than `Page`.

### 6.1. Using Slice to Drop the Count Query

~~~java
Slice<Event> findSliceByCategory(
        String category,
        Pageable pageable
);
~~~

The application only needs:

~~~java
Slice<Event> slice = repository.findSliceByCategory(
        "SYSTEM",
        PageRequest.of(
                0,
                50,
                Sort.by(
                        Sort.Order.desc("occurredAt"),
                        Sort.Order.desc("id")
                )
        )
);

boolean hasMore = slice.hasNext();
~~~

There is no need to know the total event count just to show a "Load more" button.

### 6.2. Using exists When Checking Presence Only

If you only need to check whether matching records exist, do not run `count` and compare against 0.

With `JdbcAggregateTemplate`:

~~~java
Query filter = Query.query(
        Criteria.where("status").is("PENDING")
);

boolean hasPendingOrders =
        template.exists(filter, Order.class);
~~~

`exists` expresses the exact intent and lets the persistence layer use an appropriate existence-checking strategy.

### 6.3. Caching Totals

If a screen genuinely needs total counts yet count queries are expensive and instant freshness is not required, you can cache results per filter or maintain summary counters.

Examples:

- Cache order counts by status.
- Summary table of product counts by category.
- Materialized views for reporting.
- Counters updated by events or batch jobs.

Define clearly:

- TTL or invalidation rules.
- How much staleness is acceptable.
- How concurrent updates are handled.
- How to rebuild if caches or counters drift.
- Which filters are supported.

Do not use a single global counter for queries with arbitrary filters. Counters must match the exact data scope the API needs to count.

### 6.4. Approximate Counts

Some database engines expose estimated row counts via statistics. These can work for dashboards or admin tools when users accept approximate numbers.

Do not use approximate numbers for business operations requiring exactness, such as invoice counts to settle or granted permission counts.

## 7. Why Is Deep OFFSET Slow?

Suppose a user requests page 5,000 with 20 rows per page:

~~~sql
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 99980;
~~~

The database must find the position after 99,980 matching results before returning the next 20 rows. Even when an index supports the sort order, the engine typically still has to traverse the skipped entries.

Latency can grow with offset:

~~~text
Page 0:       OFFSET 0        -> take 20 rows
Page 10:      OFFSET 200      -> skip 200 rows
Page 100:     OFFSET 2,000    -> skip 2,000 rows
Page 5,000:   OFFSET 99,980   -> skip nearly 100,000 rows
Page 50,000:  OFFSET 999,980  -> skip nearly 1 million rows
~~~

This is why offset pagination suits early pages and random page jumping on moderate datasets, but is a poor fit for scanning millions of records.

### 7.1. Indexes Do Not Eliminate Skip Cost

An index can avoid sorting the entire result set or cut table fetches, yet large offsets still require the database to advance across many entries before the returned slice.

Thus, adding an index improves offset queries without eliminating the inherent cost of skipping N results.

### 7.2. Offset Pagination Can Duplicate or Miss Rows

Suppose page one contains orders:

~~~text
A, B, C, D, E
~~~

Page two uses `OFFSET 5`. Before the user loads page two, a new order is inserted at the top:

~~~text
NEW, A, B, C, D, E, F, G...
~~~

Page two starts after 5 rows of the new result set, so it may return `E` again. Depending on data mutations, a record can also be skipped.

A deterministic sort produces deterministic ordering within one snapshot, yet does not guarantee requests at different moments observe the same dataset.

### 7.3. Always Use a Sort with a Unique Tie-Breaker

Never sort solely on a column that can contain duplicates:

~~~sql
ORDER BY created_at DESC
~~~

If multiple orders share the same `created_at`, their relative order can shift.

Add a unique secondary key:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

`id` establishes a deterministic total order among rows sharing the same timestamp.

This rule applies to both offset pagination and keyset pagination.

## 8. What Is Keyset Pagination?

Keyset pagination (also called seek pagination) uses the sort key values of the last record on the current page as a cursor for the next query.

Instead of saying:

> Skip 100,000 rows and take the next 20.

The application says:

> Take 20 rows after the order with `created_at` and `id` equal to these cursor values.

Given the order:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

The last record of the current page has:

~~~text
created_at = 2026-11-10T09:30:00Z
id         = 8120
~~~

The next page uses the predicate:

~~~sql
WHERE created_at < :cursorCreatedAt
   OR (
        created_at = :cursorCreatedAt
        AND id < :cursorId
   )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

The database seeks rows whose keys come after the cursor in the defined order, instead of counting and skipping every preceding row.

### 8.1. SQL Comparison Example

Offset:

~~~sql
SELECT id, created_at, order_number
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Keyset:

~~~sql
SELECT id, created_at, order_number
FROM orders
WHERE status = 'PAID'
  AND (
        created_at < :cursorCreatedAt
        OR (
            created_at = :cursorCreatedAt
            AND id < :cursorId
        )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

The cursor condition lets the database use a matching index to seek directly to the next position. Actual efficiency depends on indexes, filters, and the execution plan.

### 8.2. Why Must ID Be Included in the Cursor?

If you only use `created_at < :cursorCreatedAt`, rows sharing the exact timestamp of the last row on the page will be skipped.

For example:

~~~text
created_at              id
----------------------  ----
2026-11-10 09:30:00     8122
2026-11-10 09:30:00     8121
2026-11-10 09:30:00     8120  <- end of page
2026-11-10 09:29:59     8119
~~~

The correct condition must include the tie-breaker key:

~~~sql
created_at < :cursorCreatedAt
OR (
    created_at = :cursorCreatedAt
    AND id < :cursorId
)
~~~

This ensures rows with the same timestamp and smaller IDs appear on the next page.

## 9. Designing Cursors Properly

A cursor must contain all values needed to resume cleanly.

For `created_at DESC, id DESC`, a cursor might look like:

~~~json
{
  "createdAt": "2026-11-10T09:30:00Z",
  "id": 8120
}
~~~

In a real API, this can be encoded as an opaque string token. The client simply echoes back the token it received without modifying cursor internals.

### 9.1. Cursors Must Bind to Filters and Sort Order

A cursor generated for `status = PAID` must not be reused for `status = CANCELLED`.

A cursor can include:

- Last sort key values.
- Cursor format version.
- Filters or a filter fingerprint.
- Sort order.
- Tenant ID or data scope if required.
- High-water mark if the API bounds a logical snapshot.

The server must validate the cursor and ensure query parameters match the original request.

### 9.2. Cursors Should Be Signed

If the token carries values the client must not tamper with, sign the token with HMAC or an equivalent mechanism.

Base64 only encodes representation; it provides neither integrity nor confidentiality. Signatures detect tampering; if the cursor carries sensitive fields, consider encryption separately.

### 9.3. Cursors Are Not Necessarily Just an ID

A single ID suffices only when `id` itself is the entire sort order and satisfies business requirements.

When sorting by multiple fields, the cursor must carry all sort fields plus a unique tie-breaker.

For example:

~~~text
ORDER BY priority DESC, created_at ASC, id ASC
~~~

The cursor needs `priority`, `created_at`, and `id`. The continuation predicate must match each field's sort direction. You cannot use a simple `< id` predicate for multi-column sorting.

### 9.4. Avoid Keyset Pagination on Nullable Columns

SQL comparisons against `NULL` have special semantics. A predicate like:

~~~sql
created_at < :cursorCreatedAt
~~~

does not match rows where `created_at IS NULL`.

If a sort column can be `NULL`, define explicit `NULLS FIRST`/`NULLS LAST` rules and write matching cursor predicates. For simple keyset pagination, prefer `NOT NULL`, immutable sort keys.

### 9.5. Avoid Volatile Sort Columns

If a row's `created_at`, `priority`, or sort field changes while a user is paginating, that row can jump across the cursor boundary.

This can cause records to reappear or disappear during traversal. Choose immutable or near-immutable sort keys such as creation timestamp and ID.

Keyset pagination reduces shifting caused by inserts ahead of the cursor, but does not by itself create a consistent snapshot across multiple HTTP requests.

## 10. Implementing Keyset Pagination with Custom Repositories in Spring Data JDBC

Spring Data JDBC lets you use custom repository fragments and `NamedParameterJdbcTemplate` to execute SQL seek queries tailored to your use case.

Example DTOs:

~~~java
import java.time.Instant;

public record OrderSummary(
        Long id,
        String orderNumber,
        Instant createdAt
) {
}

public record OrderCursor(
        Instant createdAt,
        Long id
) {
}

public record CursorPage<T>(
        List<T> content,
        OrderCursor nextCursor,
        boolean hasNext
) {
}
~~~

Interface:

~~~java
public interface OrderScrollRepository {
    CursorPage<OrderSummary> findNextPaidOrders(
            OrderCursor cursor,
            int pageSize
    );
}
~~~

Implementation:

~~~java
@Repository
public class OrderScrollRepositoryImpl
        implements OrderScrollRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderScrollRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public CursorPage<OrderSummary> findNextPaidOrders(
            OrderCursor cursor,
            int pageSize
    ) {
        if (pageSize < 1 || pageSize > 200) {
            throw new IllegalArgumentException(
                    "pageSize must be between 1 and 200"
            );
        }

        String sql;
        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("status", "PAID")
                        .addValue("limit", pageSize + 1);

        if (cursor == null) {
            sql = """
                    SELECT id, order_number, created_at
                    FROM orders
                    WHERE status = :status
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """;
        } else {
            sql = """
                    SELECT id, order_number, created_at
                    FROM orders
                    WHERE status = :status
                      AND (
                            created_at < :cursorCreatedAt
                            OR (
                                created_at = :cursorCreatedAt
                                AND id < :cursorId
                            )
                      )
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """;

            parameters
                    .addValue("cursorCreatedAt", cursor.createdAt())
                    .addValue("cursorId", cursor.id());
        }

        List<OrderSummary> fetched = jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getTimestamp("created_at").toInstant()
                )
        );

        boolean hasNext = fetched.size() > pageSize;

        List<OrderSummary> content = hasNext
                ? List.copyOf(fetched.subList(0, pageSize))
                : fetched;

        OrderCursor nextCursor = null;

        if (hasNext && !content.isEmpty()) {
            OrderSummary last = content.get(content.size() - 1);

            nextCursor = new OrderCursor(
                    last.createdAt(),
                    last.id()
            );
        }

        return new CursorPage<>(
                content,
                nextCursor,
                hasNext
        );
    }
}
~~~

Key points:

1. The first request passes no cursor.
2. Each query fetches `pageSize + 1` rows.
3. The extra row determines `hasNext`.
4. Only `pageSize` rows are returned to the client.
5. The next cursor is taken from the last row actually returned.
6. The next request sends that cursor to seek results after it.

In this example, both sort order and cursor predicates are `DESC`. If you reverse the sort direction, update the comparison operators accordingly.

This is custom SQL for the `orders` table and a DTO, not loading full aggregates via a repository. When you need full aggregate roots with owned components, use `JdbcAggregateTemplate` with `Query` or write appropriate custom repository mapping.

## 11. Indexes for Keyset Pagination

Keyset pagination shines only when the database has an index aligned with filters and sorting.

For the query:

~~~sql
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (
          created_at = :cursorCreatedAt
          AND id < :cursorId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

A candidate index:

~~~sql
CREATE INDEX idx_orders_status_created_id
    ON orders(status, created_at DESC, id DESC);
~~~

This index can support:

- Filtering by `status`.
- Seeking past `created_at` and `id`.
- Returning rows in the desired order.

### 11.1. Index Column Order Matters

With a composite index:

~~~text
(status, created_at, id)
~~~

The equality predicate on `status` narrows down the index range before applying the sort/cursor predicates on `created_at` and `id`.

If another query filters by tenant as well:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
~~~

The index should likely lead with the equality filter columns:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders(tenant_id, status, created_at DESC, id DESC);
~~~

No single index is optimal for every filter/sort combination. Design indexes around queries actually in use and measure execution plans.

### 11.2. Inspecting the Execution Plan

In PostgreSQL, inspect the plan and execution metrics:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
  AND (
      created_at < TIMESTAMP '2026-11-10 09:30:00'
      OR (
          created_at = TIMESTAMP '2026-11-10 09:30:00'
          AND id < 8120
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

In MySQL, use `EXPLAIN` or `EXPLAIN ANALYZE` depending on version. Inspect:

- Which index is chosen.
- Estimated vs. actual row counts.
- Whether an extra sort occurs.
- Whether a full table scan occurs.
- Data read costs.
- How the count query plan differs from the content query plan.

`EXPLAIN ANALYZE` executes the query to gather metrics. Use caution with write statements or heavy queries in production environments.

Do not compare only single-run durations. Use production-like data distributions and measure multiple runs under realistic workloads.

## 12. Does Keyset Replace Page?

No. The two mechanisms serve different navigation patterns.

| Criterion | Offset/Page | Keyset/Cursor |
| --- | --- | --- |
| Jump to arbitrary page | Convenient | Not natively supported |
| Display total page count | Possible | Not natively provided |
| Sequential traversal of large data | Deep offsets can be slow | Better suited when indexed |
| Cursor state needed | Page number/offset | Last sort key values |
| Impact of inserts ahead of current position | Can duplicate or skip rows | Less susceptible to continuation drift |
| Sort requirement | Needs deterministic order | Needs deterministic order and tie-breaker |
| Matching index | Helpful | Essential |
| API complexity | Low | Higher due to cursor handling |

Choose based on UX and business requirements:

- Small admin tables needing page jumping: `Page`.
- Lists needing only a "Next" button: `Slice`.
- Feeds or large sequentially browsed lists: keyset/cursor.
- Batch exports: keyset or stream, depending on connection and transaction needs.
- Dashboards needing exact totals: `Page` or a separate count query.
- Dashboards accepting approximations: cached or summary counters.

## 13. Deep Pagination in Batch Exports

A job exporting millions of rows should not default to looping over pages 0, 1, 2, ... using offsets.

Inefficient example:

~~~java
int page = 0;

while (true) {
    Page<Order> result = repository.findByStatus(
            "PAID",
            PageRequest.of(page, 1000)
    );

    export(result.getContent());

    if (!result.hasNext()) {
        break;
    }

    page++;
}
~~~

Problems:

- Every page can trigger a count query.
- Offset grows on every iteration.
- The database must skip more and more rows.
- Every iteration issues a fresh query request.
- Concurrent changes during export can cause missing or duplicate rows.

A better strategy:

1. Define the export scope, such as a time range or status.
2. Choose a deterministic, unique sort key.
3. Fetch chunks by cursor.
4. Write each chunk to a file or destination.
5. Update cursor/checkpoint after each chunk succeeds.
6. Resume from the last cursor if the job restarts.

If the export requires an exact point-in-time snapshot, keyset pagination alone does not guarantee a snapshot across multiple transactions. Determine whether a high-water mark, appropriate snapshot isolation, or a dedicated snapshot/CDC mechanism is required.

### 13.1. High-Water Mark

You can bound the dataset range with an initial cutoff, such as the maximum ID at start time:

~~~sql
SELECT MAX(id) FROM orders;
~~~

Then every chunk reads only:

~~~sql
WHERE id > :lastId
  AND id <= :initialMaxId
ORDER BY id ASC
LIMIT :limit;
~~~

This keeps rows inserted with IDs above the initial cutoff out of the export. However, it does not guarantee a complete point-in-time snapshot if older records can be updated or deleted during the export. Understand ID semantics and workload before applying it.

## 14. Consistency Between Count Query and Content Query

A `Page` may run two separate SQL statements:

1. Fetch page content.
2. Count total results.

If data changes between those two executions, the total and content can reflect two different points in time.

Example:

~~~text
T1: Count query returns 100 orders
T2: Another transaction inserts a new order
T3: Content query reads data now containing 101 orders
~~~

The response may show content from the newer state alongside a total from the older state.

If the business accepts minor drift during ordinary browsing, this can be a reasonable trade-off.

If both must reflect the exact same snapshot:

- Run both queries inside an appropriate transaction.
- Choose an isolation level that guarantees the required snapshot on your target database.
- Weigh the cost of holding longer transactions.
- For long reports, consider snapshot/reporting tables or dedicated export mechanisms.

Do not assume two queries in the same Java method automatically see the same snapshot. That depends on actual transaction boundaries and isolation levels.

## 15. Ensuring Safe and Deterministic Sorting

Whether using `Page`, `Slice`, or cursors, ordering must be deterministic.

### 15.1. Always Add a Tie-Breaker

Example:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
~~~

If sorting only by `createdAt`, two rows with identical timestamps can switch order across queries.

### 15.2. Whitelist Sort Properties

Never concatenate sort inputs from requests directly into SQL:

~~~java
// Do not do this:
String sql = "SELECT ... ORDER BY " + request.getSort();
~~~

Instead, map API-supported sort names:

~~~java
Map<String, String> allowedSorts = Map.of(
        "createdAt", "created_at",
        "orderNumber", "order_number",
        "totalAmount", "total_amount"
);
~~~

Accept only properties present in the allowlist and validate sort direction. When using repository abstractions, construct `Sort` from validated properties only.

### 15.3. Cap Page Size

Do not let clients request arbitrarily huge pages:

~~~java
private Pageable normalize(Pageable pageable) {
    int size = Math.min(pageable.getPageSize(), 200);

    return PageRequest.of(
            pageable.getPageNumber(),
            size,
            pageable.getSort()
    );
}
~~~

Handle `Pageable.unpaged()` explicitly if your API permits it. Capping page size protects memory, connections, and the database from accidentally loading excessive data.

## 16. Measuring and Diagnosing

Before changing pagination, measure each part separately.

Useful metrics:

- Content query duration.
- Count query duration.
- Actual returned row counts.
- Maximum requested offset.
- Share of requests using `Page`, `Slice`, and cursors.
- Rows scanned/read per execution plan.
- Timeout rates.
- Count cache hit ratio, if cached.
- Share of requests reaching deep pages.

In development, you can enable Spring JDBC SQL logging:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

When a paginated endpoint is slow:

1. Identify whether the bottleneck is the content query or the count query.
2. Record filters, sort order, limit, and offset.
3. Run the execution plan on the target database.
4. Inspect indexes and statistics.
5. Compare first-page performance with deep pages.
6. Check for JOINs multiplying results.
7. Evaluate whether the UI truly needs a total count.
8. Test `Slice` or keyset pagination on the same dataset.
9. Re-measure under production-like workloads.

Do not optimize the count query if most of the time is actually spent loading an aggregate with multiple collections via extra SQL statements.

## 17. Common Misconceptions

**"Page runs only one SELECT."** Not necessarily. `Page` needs total counts and may emit an extra count query.

**"Slice is always fast."** `Slice` avoids the count query but may still use `OFFSET`. Very deep pages can still be slow.

**"List with Pageable includes hasNext."** No. `List` contains only the content; the application must determine navigation itself if needed.

**"COUNT(*) is always fast because it returns one number."** No. The database still must determine matching rows and may read substantial data.

**"COUNT(column) always equals COUNT(*)."** No. `COUNT(column)` ignores `NULL`s.

**"After a JOIN, COUNT(*) gives total aggregates."** No. A one-to-many JOIN can duplicate roots; use `COUNT(DISTINCT root.id)` when counting unique aggregates.

**"Count queries can drop some filters."** Not if the total must match the browsed dataset. Count predicates must match content predicates.

**"Count queries need ORDER BY."** No. Sorting does not change row counts.

**"Pageable can be passed to any @Query."** No. String-based `@Query` in Spring Data JDBC does not rewrite SQL for `Pageable`/`Sort`/`Limit`; write explicit limit clauses or use a custom repository.

**"Adding an index makes deep offsets as fast as page one."** No. The database still has to walk past skipped entries.

**"Sorting by timestamp is enough."** Not if timestamps can tie. Add a unique tie-breaker such as `id`.

**"Keyset pagination automatically provides total pages."** No. Keyset handles resuming from the current position; if exact totals are needed, counting remains a separate problem.

**"Cursors only ever need ID."** True only when ID is the entire sort order. Multi-column sorts require cursors containing all sort keys.

**"Keyset works well with any sort field."** No. Nullable or frequently mutated sort keys complicate predicates and cause unstable results.

**"Keyset guarantees a snapshot across requests."** No. It avoids offset-shift anomalies, but does not replace transactional snapshots or export snapshots.

**"Cached counts never need invalidation."** No. Stale caches return outdated numbers; define acceptable staleness and rebuild rules.

## 18. Workflow for Choosing a Pagination Strategy

When designing a list endpoint, answer:

1. Does the UI need an exact total record count?
2. Do users need to jump to arbitrary page numbers?
3. How large can the dataset grow?
4. Can users navigate to very deep pages?
5. Is the sort key immutable and unique?
6. Do JOINs or `GROUP BY` change the unit being counted?
7. Is the count query actually a bottleneck?
8. Are indexes aligned with filters and sorting?
9. Does data mutate frequently during browsing?
10. Is a consistent snapshot required across the entire traversal?

Decision flowchart:

~~~mermaid
flowchart TD
    A["Design list endpoint"] --> B{"Need exact total count?"}
    B -->|Yes| C["Page + count query"]
    B -->|No| D{"Only need to know if more results exist?"}
    D -->|Yes| E["Slice or cursor"]
    D -->|No| F["List + Pageable"]
    C --> G{"Can offsets get very deep?"}
    E --> G
    F --> G
    G -->|No| H["Offset pagination + stable sort"]
    G -->|Yes| I{"Sequential traversal, no page jumping?"}
    I -->|Yes| J["Keyset / cursor pagination"]
    I -->|No| K["Redesign UX or use snapshot/report"]
    J --> L["Index matching filters + sort keys"]
    H --> M["Measure count/content queries separately"]
    L --> M
~~~

## 19. Practice Exercises

Create an `Order` aggregate with fields `id`, `orderNumber`, `status`, `createdAt`, and `totalAmount`.

### Exercise 1: Comparing Page and Slice

1. Add a repository method returning `Page<Order>` by `status`.
2. Add a method returning `Slice<Order>` by `status`.
3. Run with page size 20.
4. Enable SQL logging.
5. Observe query counts and count query usage.
6. Compare returned metadata.

### Exercise 2: Writing Custom Count Queries

1. Create a custom repository fragment for order search.
2. Write content SQL with filters and sorting.
3. Write count SQL with identical filters.
4. Ensure count omits `ORDER BY`, `LIMIT`, and `OFFSET`.
5. Compare totals against actual rows.
6. Add a JOIN to `order_items` and verify `COUNT(DISTINCT order_id)`.

### Exercise 3: Measuring Deep Offsets

1. Seed at least several hundred thousand orders.
2. Run the first-page query.
3. Run queries at offsets 10,000, 100,000, and 500,000.
4. Record elapsed times and execution plans.
5. Add a matching index.
6. Compare rows read and latency.

### Exercise 4: Implementing Keyset Pagination

1. Sort by `createdAt DESC, id DESC`.
2. Define a cursor containing `createdAt` and `id`.
3. Write the first-page query.
4. Write the next-page query using the cursor predicate.
5. Fetch `pageSize + 1` rows to determine `hasNext`.
6. Return the new cursor from the last displayed row.
7. Verify zero duplicates and zero gaps on static data.

### Exercise 5: Testing Under Concurrent Updates

1. Read the first page.
2. Insert a new order with a newer timestamp.
3. Continue using offset pagination.
4. Observe potential duplicate or missing rows.
5. Repeat with a keyset cursor.
6. Update a sort key on an already-read row and evaluate the impact.

### Exercise 6: Measuring Indexes and Counts

1. Run the count query before adding an index.
2. Create an index on `status` and `created_at`.
3. Re-run the count query.
4. Inspect the execution plan.
5. Measure both content query and count query.
6. Assess write overhead introduced by the index.

## 20. Key Takeaways

- `Page<T>` provides total elements and total pages; a count query may run to compute that metadata.
- `Slice<T>` fetches `pageSize + 1` to determine whether a next page exists without computing a total count.
- `List<T>` with `Pageable` returns only the data slice without total-count metadata.
- Count queries must preserve filters and count the exact data unit the API paginates.
- With one-to-many JOINs, use `COUNT(DISTINCT root.id)` when counting unique aggregate roots.
- Count queries should omit `ORDER BY`, `LIMIT`, and `OFFSET` when counting the full matching set.
- `JdbcAggregateTemplate.count(Query, Class)` can count rows matching a `Query` filter.
- String-based `@Query` in Spring Data JDBC does not automatically support `Pageable`, `Sort`, or `Limit` parameters; write explicit SQL bounds or use a custom repository.
- Counts can be slow even though they return a single number; evaluate indexes and execution plans on real data.
- Deep `OFFSET` can traverse many skipped rows and is vulnerable to inserts/deletes between requests.
- Always use deterministic sorting with a unique tie-breaker.
- Keyset pagination resumes from the last row's sort keys, avoiding large offset-skipping costs.
- Cursors must hold all sort keys, filter/sort context, and be validated.
- Keyset pagination fits sequential traversal; it does not natively provide total page counts or arbitrary page jumping.
- Indexes should align with equality filters, sort fields, and tie-breakers of keyset queries.
- When consistent snapshots across requests or long exports are required, design explicit isolation, high-water marks, or snapshot mechanisms.
- Cache or approximate counts only when business requirements allow staleness or error bounds and an update strategy exists.

**Optimizing pagination starts with identifying what information the UI genuinely needs.** If exact totals are required, use `Page` and optimize the count query. If only knowing whether more data exists suffices, use `Slice`. If large datasets must be traversed sequentially in a deterministic order, use keyset pagination with proper cursors and indexes. Separating counting from content fetching pinpoints the real bottleneck and guides the right strategy for each use case.

## References

- [Spring Data Relational 4.1.2 — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational 4.1.2 — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html)
- [Spring Data Relational 4.1.2 — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [Spring Data Relational 4.1.2 — ScrollDelegate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/support/ScrollDelegate.html)
- [Spring Data Commons 4.1.2 — Scrolling](https://docs.spring.io/spring-data/relational/reference/data-commons/repositories/scrolling.html)
