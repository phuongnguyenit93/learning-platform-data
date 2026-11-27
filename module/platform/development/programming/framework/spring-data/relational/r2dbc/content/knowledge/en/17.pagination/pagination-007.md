# Ensuring Consistency Between Data Pages and Total Counts

A paginated API often returns two kinds of information: the list of records for the current page and the total number of records matching the filter criteria. For example, the UI displays "21–40 of 327 products". In Spring Data Relational R2DBC, the list is typically fetched using a query with LIMIT/OFFSET or a keyset cursor, while the total is fetched using a separate COUNT query.

These two queries can observe two different data states if an INSERT, UPDATE, or DELETE occurs between them. When that happens, the response may contain a page of 20 rows whose total count does not match the dataset that page represents. The issue becomes even more noticeable as users navigate through multiple pages while data is mutating.

To ensure consistency, you must first define what "consistency" means for the API: must the list and total count reflect the same snapshot within a single response, or must an entire multi-page browsing journey see the same dataset? These two requirements demand different strategies. This lesson covers synchronizing filters/ordering, transaction isolation, single-statement counts, offset/keyset pagination, and options when data changes continuously.

## 1. What Does a Paginated Response Include?

A page-number response typically has:

~~~json
{
  "items": [
    { "id": 101, "name": "Keyboard" },
    { "id": 102, "name": "Mouse" }
  ],
  "page": 5,
  "size": 20,
  "totalElements": 327,
  "totalPages": 17,
  "hasNext": true
}
~~~

Meaning of the fields:

| Field | Meaning |
|---|---|
| items | Rows belonging to the current page |
| page | Page index, usually 0-based |
| size | Maximum number of rows requested |
| totalElements | Total number of rows matching the filter |
| totalPages | Number of pages based on page size |
| hasNext | Whether a next page exists |

With page numbers, offset is typically calculated as:

$$
offset = page \times size
$$

And total pages:

$$
totalPages = \left\lceil \frac{totalElements}{size} \right\rceil
$$

When `totalElements` is 0, `totalPages` is 0. If page size is invalid, the API should reject or normalize it according to the published contract.

With keyset pagination, the response usually uses a cursor:

~~~json
{
  "items": [
    { "id": 101, "name": "Keyboard" },
    { "id": 102, "name": "Mouse" }
  ],
  "nextCursor": 102,
  "hasNext": true
}
~~~

Keyset pagination does not necessarily provide `totalElements`. Cursors and total counts are independent concepts; add total counting only when the product truly needs it.

## 2. Why Can the Page Query and COUNT Query Diverge?

A common implementation executes two statements:

~~~sql
SELECT id, name, price
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT 20 OFFSET 100;
~~~

~~~sql
SELECT COUNT(*)
FROM product
WHERE active = TRUE;
~~~

Suppose the table has 327 active products when the page query runs. Immediately afterward, another request inserts 5 active products. The COUNT query may return 332. The response now combines a page read from the earlier state with a total count read from the later state.

Similar situations:

- A row is deleted after the page query but before the COUNT query: the total can be lower than the set the page just read.
- A row changes from inactive to active between the two queries: page and count observe different sets.
- A row has a filter column updated: it can move into or out of the result set.
- Another request inserts/deletes rows ahead of OFFSET: row positions on the next page can shift.

This divergence is not necessarily a database bug. It is a consequence of statements observing data at different moments under the transaction isolation in use.

## 3. First Condition: COUNT and Page Must Use the Same Filters

Before considering transactions, both queries must define the exact same dataset.

For example, an API filtering by active status and name:

~~~sql
SELECT id, name, price
FROM product
WHERE active = :active
  AND name ILIKE :pattern
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

The count query must apply the same conditions:

~~~sql
SELECT COUNT(*)
FROM product
WHERE active = :active
  AND name ILIKE :pattern;
~~~

If the page query filters by tenant, access permissions, soft-delete, or status while the count query omits it, `totalElements` will be wrong even when both statements run on the same snapshot.

An easy-to-verify principle is to define the result set first:

~~~text
Dataset D =
    rows permitted to be viewed
    AND not soft-deleted
    AND matching business filters

Page  = take an ordered slice from D
Count = count rows in D
~~~

COUNT and page must share:

- Tenant/ownership scope.
- Authorization filters.
- Soft-delete conditions.
- Search/filter parameters.
- Join conditions.
- Distinct/grouping rules.

### 3.1. Watch Out for Joins Multiplying Rows

If the page query joins a child table, one product can appear multiple times:

~~~sql
SELECT p.id, p.name, c.id AS category_id
FROM product p
JOIN product_category c ON c.product_id = p.id
WHERE c.category_id IN (:categoryIds)
ORDER BY p.id;
~~~

If the API displays each product once, the count query must count distinct products:

~~~sql
SELECT COUNT(DISTINCT p.id)
FROM product p
JOIN product_category c ON c.product_id = p.id
WHERE c.category_id IN (:categoryIds);
~~~

`COUNT(*)` counts post-join rows, not necessarily root entities. For queries with `GROUP BY`, determine whether the total is the number of groups or source rows. The meaning of total must match the unit returned in `items`.

### 3.2. COUNT(*) and COUNT(column)

`COUNT(*)` counts every row. `COUNT(column)` skips rows where that column is NULL. When total record count is needed, `COUNT(*)` is usually clearer.

For projections that can produce duplicates, use `COUNT(DISTINCT primary_key)` when semantics require counting unique entities. Do not use `COUNT(DISTINCT)` out of habit if the query already guarantees one row per entity; distinct operations can make queries more expensive.

### 3.3. Do Not Let Count Leak Restricted Data

If the list returns only rows belonging to the current tenant while count counts the whole table, the API can leak data counts of other tenants. Count must apply the exact same authorization scope as the page query.

## 4. Sort Order Must Be Deterministic and Stable

Pagination requires a deterministic order. When sorting by a non-unique column, rows sharing the same value can swap positions across query executions.

Avoid doing only:

~~~sql
SELECT id, name
FROM product
ORDER BY created_at
LIMIT :size OFFSET :offset;
~~~

If multiple rows share the same `created_at`, the database is not obligated to maintain a stable secondary order among them. Add a unique key as a tie-breaker:

~~~sql
SELECT id, name, created_at
FROM product
ORDER BY created_at, id
LIMIT :size OFFSET :offset;
~~~

With keyset pagination, the cursor must hold enough sort values to identify a unique position. If sorting by `created_at` then `id`, the cursor predicate must compare both fields in the same order.

Stable ordering solves nondeterministic ordering within a snapshot. It does not by itself prevent page drift when rows are INSERTed/DELETEd/UPDATEd between requests.

## 5. PostgreSQL READ COMMITTED and Per-Statement Snapshots

PostgreSQL defaults to the `READ COMMITTED` isolation level. At this level, each statement sees a snapshot containing changes committed before that statement began.

This means two consecutive queries inside the same `READ COMMITTED` transaction can still observe two different states:

~~~text
Transaction A                         Transaction B
-------------                         -------------
BEGIN
SELECT page
  -> sees 100 rows
                                      INSERT product
                                      COMMIT
SELECT COUNT(*)
  -> sees 101 rows
COMMIT
~~~

Therefore, simply wrapping the page query and COUNT query in the same default transaction is not enough to guarantee they use the same snapshot on PostgreSQL `READ COMMITTED`.

### 5.1. READ COMMITTED Still Fits Many APIs

If data changes frequently and the API tolerates totals as figures near read time, `READ COMMITTED` can be a reasonable choice. It provides good concurrency and avoids holding long snapshots like `REPEATABLE READ`.

What matters is documenting the semantics: the total is the count at the time of the count query, not an immutability promise throughout a user's multi-page session.

## 6. Using REPEATABLE READ for Count and Page in the Same Response

In PostgreSQL, `REPEATABLE READ` retains a stable transaction snapshot for statements within the same transaction. When the COUNT query and page query run sequentially inside this transaction, both observe the same data state.

Flow:

~~~text
BEGIN ISOLATION LEVEL REPEATABLE READ
    |
    v
SELECT COUNT(*) ...  ----+
                         |
                         +-- same snapshot
                         |
SELECT ... LIMIT/OFFSET -+
    |
    v
COMMIT
~~~

This is appropriate when a single response needs an exact total count matching the exact same snapshot as `items`.

### 6.1. Configuring TransactionalOperator with an Isolation Level

You can create a dedicated operator for reads requiring a snapshot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.support.DefaultTransactionDefinition;

@Configuration
public class PaginationTransactionConfiguration {

    @Bean
    TransactionalOperator repeatableReadOperator(
            ReactiveTransactionManager transactionManager) {

        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setReadOnly(true);
        definition.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ
        );
        definition.setName("pagination-count-and-page");

        return TransactionalOperator.create(
            transactionManager,
            definition
        );
    }
}
~~~

This bean assumes the application uses a reactive transaction manager paired with the R2DBC `ConnectionFactory`. If there are multiple databases/transaction managers, specify the right manager for the pool holding the paginated data.

### 6.2. Running COUNT and Page in the Same Transaction

Example using `DatabaseClient` with an active filter:

~~~java
import java.util.List;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public record ProductRow(Long id, String name) {
}

public record ProductPage(
    List<ProductRow> items,
    int page,
    int size,
    long totalElements,
    long totalPages
) {
}

@Repository
public class ProductPaginationRepository {

    private final DatabaseClient databaseClient;
    private final TransactionalOperator repeatableReadOperator;

    public ProductPaginationRepository(
            DatabaseClient databaseClient,
            TransactionalOperator repeatableReadOperator) {
        this.databaseClient = databaseClient;
        this.repeatableReadOperator = repeatableReadOperator;
    }

    public Mono<ProductPage> findActivePage(
            int page,
            int size) {

        long offset = Math.multiplyExact((long) page, size);

        Mono<Long> countQuery = databaseClient.sql("""
                SELECT COUNT(*)
                FROM product
                WHERE active = TRUE
                """)
            .map((row, metadata) -> row.get(0, Long.class))
            .one()
            .defaultIfEmpty(0L);

        Mono<List<ProductRow>> pageQuery = databaseClient.sql("""
                SELECT id, name
                FROM product
                WHERE active = TRUE
                ORDER BY id
                LIMIT :size OFFSET :offset
                """)
            .bind("size", size)
            .bind("offset", offset)
            .map((row, metadata) -> new ProductRow(
                row.get("id", Long.class),
                row.get("name", String.class)
            ))
            .all()
            .collectList();

        Mono<ProductPage> result = countQuery.flatMap(total ->
            pageQuery.map(items -> new ProductPage(
                items,
                page,
                size,
                total,
                total == 0 ? 0 : (total + size - 1) / size
            ))
        );

        return result.as(repeatableReadOperator::transactional);
    }
}
~~~

The two publishers are composed sequentially: `COUNT` finishes before the page query executes. Both run within the same subscription managed by `TransactionalOperator`. On PostgreSQL `REPEATABLE READ`, they share the same transaction snapshot.

Do not use `Mono.zip(countQuery, pageQuery)` by default when both queries must execute on the same transactional connection. `Mono.zip` subscribes to both branches concurrently; many R2DBC drivers/connections do not support executing two statements simultaneously on one connection the way code might assume. Sequential composition with `flatMap` is clearer and more compatible.

### 6.3. Why Doesn't readOnly Automatically Guarantee a Snapshot?

`readOnly` is a transaction hint/attribute; it does not automatically elevate the isolation level. If you only set `readOnly=true` while the database still uses `READ COMMITTED`, each statement still gets its own snapshot. Specify the appropriate isolation level explicitly and confirm the transaction manager/driver applies it.

### 6.4. Watch Out for Long-Running Transactions

`REPEATABLE READ` retains a snapshot for the duration of the transaction. Holding a transaction open for long can lengthen connection hold times and force PostgreSQL to retain old row versions needed by the snapshot. Therefore:

- Wrap only the two short queries that require consistency.
- Do not stream an entire response across a long transaction unnecessarily.
- Do not make HTTP service calls or wait on clients inside this transaction.
- Do not use a single snapshot transaction for a user's multi-minute multi-page browsing session.

## 7. Using a Single SQL Statement to Fetch Page and Total from the Same Snapshot

Another approach is calculating the total via a window function inside the same statement:

~~~sql
SELECT
    id,
    name,
    price,
    COUNT(*) OVER() AS total_elements
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

`COUNT(*) OVER()` counts the total number of rows in the post-WHERE set and attaches `total_elements` to every returned row. Because page and count belong to a single statement, they observe the exact same statement snapshot without needing a transaction wrapping two separate queries.

Advantages:

- No time gap between the count query and page query.
- No multi-statement transaction needed solely to synchronize the two results.
- The total can be read from the first row on the page.

Limitations:

- If offset exceeds the end of the result set, the query returns zero rows; there is then no row from which to read `total_elements`.
- Window counts still typically evaluate the entire matching row set, so `LIMIT` does not make counting free.
- If a join multiplies rows, the window count may count post-join rows; design the input set at the right grain.
- The mapper must read `total_elements` from every row or from the first row.

### 7.1. Window Count Mapping Example

~~~java
public record ProductWithTotal(
    Long id,
    String name,
    Long totalElements
) {
}

public Flux<ProductWithTotal> findActivePage(
        int size,
        long offset) {

    return databaseClient.sql("""
            SELECT id, name, COUNT(*) OVER() AS total_elements
            FROM product
            WHERE active = TRUE
            ORDER BY id
            LIMIT :size OFFSET :offset
            """)
        .bind("size", size)
        .bind("offset", offset)
        .map((row, metadata) -> new ProductWithTotal(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("total_elements", Long.class)
        ))
        .all();
}
~~~

The service can take `totalElements` from the first element and build the page response. Because all rows in the same result carry the same total, there is no need to recompute it per element.

If the page is empty, a clear policy is required. You can return total as 0 if the API defines out-of-range pages as empty without needing an exact count; or run a separate count in a `REPEATABLE READ` transaction; or use a CTE/LEFT JOIN query so the total is still returned even when the page is empty.

### 7.2. CTE/LEFT JOIN to Return Total Even When the Page Is Empty

PostgreSQL can compute the total and the page in one statement and then `LEFT JOIN` so a total row always exists:

~~~sql
WITH totals AS (
    SELECT COUNT(*) AS total_elements
    FROM product
    WHERE active = TRUE
),
page_rows AS (
    SELECT id, name, price
    FROM product
    WHERE active = TRUE
    ORDER BY id
    LIMIT :size OFFSET :offset
)
SELECT
    page_rows.id,
    page_rows.name,
    page_rows.price,
    totals.total_elements
FROM totals
LEFT JOIN page_rows ON TRUE
ORDER BY page_rows.id;
~~~

The statement always returns at least one row from `totals`. When `page_rows` is empty, `page_rows` columns are NULL while `total_elements` still holds its value. The mapper must distinguish this sentinel row from real products, for example by checking for a null `id` and not adding an item to the list.

Both CTEs belong to the same statement snapshot. PostgreSQL may optimize/inline CTEs depending on version and query structure; do not assume CTEs always materialize. Inspect `EXPLAIN` on realistic data.

## 8. Choosing Between Two Queries in a Transaction and a Single Window Query

| Criterion | COUNT + page in REPEATABLE READ | COUNT(*) OVER() |
|---|---|---|
| Snapshot | Same transaction snapshot | Same statement snapshot |
| Number of statements | Two | One |
| Empty page | COUNT still returns a value | Window returns no rows carrying total |
| Query structure | Easy to separate count/page and reuse | Compact in one SQL, though requires total mapping |
| Transaction | Requires a reactive transaction | No transaction needed solely to sync count/page |
| Cost | Two statements, count still has to count | Window count still has to evaluate the result set |
| Best suited for | Repositories/services needing separated queries | Page APIs needing total and page in one statement |

Neither option is universally faster. Benchmark with real filters, indexes, and data sizes. If an exact total count is not necessary, omitting count is usually the simplest optimization.

## 9. Count and Page Must Align Dynamic Filters

In real APIs, filters may be optional: active, category, keyword, min/max price. Ensure both queries receive the exact same values and semantics.

Example with required `active`:

~~~java
Mono<Long> countProducts(boolean active) {
    return databaseClient.sql("""
            SELECT COUNT(*)
            FROM product
            WHERE active = :active
            """)
        .bind("active", active)
        .map((row, metadata) -> row.get(0, Long.class))
        .one()
        .defaultIfEmpty(0L);
}
~~~

With optional nullable parameters, R2DBC `DatabaseClient` should not be called with `bind(name, null)`. Use `bindNull(name, JavaType.class)` or build appropriate queries/criteria.

Conceptual example:

~~~java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

if (active == null) {
    spec = spec.bindNull("active", Boolean.class);
} else {
    spec = spec.bind("active", active);
}
~~~

SQL predicates like:

~~~sql
WHERE (:active IS NULL OR active = :active)
~~~

can be convenient, though `OR` with optional parameters can sometimes make it harder for the planner to choose an optimal index. Under heavy workloads, consider generating explicit query shapes matching active filters or using Spring Data `Criteria`/`Query` builders for consistent predicates.

### 9.1. Avoid Copy-Pasting Divergent Filters Between Count and Page

When filters evolve, it is easy to update the page query and forget the count query. Reduce this risk by using:

- A shared criteria-building function for both queries.
- A repository method accepting an immutable filter object.
- A shared SQL CTE when using a single statement.
- Integration tests comparing counts against known fixture row counts.

If assembling SQL fragments, append only fixed code-controlled fragments; never concatenate client input directly.

### 9.2. Authorization Filters Must Match

Multi-tenant example:

~~~sql
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND active = :active
~~~

Both count and page must use the exact same `tenantId` obtained from the authenticated security context, the same soft-delete predicate, and the same active filter. Never accept `tenantId` from a query parameter and trust it directly when authorization requires deriving tenant from the principal.

## 10. Offset Pagination and Page Drift

Offset pagination is straightforward to implement:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

However, row positions are determined by how many rows precede them. If an INSERT or DELETE occurs before the offset between two requests, the next page can contain duplicates or skip rows relative to the initial traversal.

Example:

~~~text
Before reading page 1:
IDs: 10, 20, 30, 40, 50, 60
size = 3

Page 1 (offset 0): 10, 20, 30

A new row with ID 15 is INSERTed.
New order: 10, 15, 20, 30, 40, 50, 60

Page 2 (offset 3): 30, 40, 50
                         ^^
                    ID 30 is duplicated
~~~

If a DELETE occurs before the offset, the next page can skip a row. A stable `ORDER BY` makes ordering deterministic within each snapshot, but does not prevent positions from shifting across snapshots.

### 10.1. Total Count Can Change Between Pages

Even when count and page within a single response are consistent, `totalElements` on page 1 and page 2 can differ if data changes between the two HTTP requests. This is normal behavior when each request reads a fresh snapshot.

If the UI displays a fixed total throughout a session, define a snapshot/cutoff or treat the total as a reference figure from the start time.

## 11. Keyset Pagination Reduces Page Drift from Leading INSERTs

Keyset pagination uses the last key from the previous page:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :size;
~~~

If the first page returns IDs 10, 20, 30, the cursor is 30. A new row with ID 15 inserted afterward does not push rows after the cursor to different offset positions; the next page still starts from `id > 30`.

Keyset usually fits:

- Large tables and sequential traversal.
- Feeds or newest/oldest lists.
- Batch exports.
- APIs that do not need direct jumping to arbitrary page numbers.

Keyset does not preserve a snapshot of the data by itself. Rows after the cursor can still be deleted or change filter membership; previously read rows can be updated; a new row with a key smaller than the cursor may not be seen in the current pass.

### 11.1. Multi-Column Cursors

If ordering is `created_at` then `id`:

~~~sql
SELECT id, name, created_at
FROM product
WHERE active = TRUE
  AND (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :size;
~~~

Row-value comparisons like the above work well in PostgreSQL for columns with compatible comparison semantics. When DESC sort directions, nullable sort keys, or complex multi-column orders are involved, design the corresponding cursor predicate, including `NULLS FIRST`/`LAST` rules.

### 11.2. Total Count with Keyset

A keyset page only needs to query the next rows and can fetch one extra row to determine `hasNext`:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :sizePlusOne;
~~~

If `size + 1` rows return, a next page exists. Drop the extra row before returning the response and use the last ID among the `size` rows actually returned as the cursor.

If `totalElements` is required, the COUNT query must count the entire filtered set, not only rows after the cursor. Never add `id > afterId` to the count unless the API explicitly defines the total as "remaining rows after cursor".

Make this distinction explicit in the API:

- `totalElements`: total rows in the entire filtered set.
- `remainingElements`: rows remaining after the cursor.

These two values are not the same.

## 12. Ensuring Snapshots Across Multiple HTTP Requests

`REPEATABLE READ` only preserves a snapshot for the lifetime of a transaction. If a client fetches page 1, waits 10 seconds, and fetches page 2 in another request, the first request's transaction has already ended. The second request gets a new snapshot.

Do not keep a database transaction and connection open across multiple HTTP requests or while a user browses the UI. Doing so:

- Holds connections long and reduces pool capacity.
- Retains MVCC snapshots long, which can impede cleanup of old row versions in PostgreSQL.
- Is hard to handle when clients abandon pages, drop network connections, or open multiple tabs.
- Introduces server-side state that must be managed and expired.

If the entire session must observe the exact same dataset, pick an appropriate snapshot model instead of holding a transaction open across requests.

### 12.1. Cutoff Snapshots for Append-Only Data

If a table is primarily append-only and IDs increase monotonically, you can capture the max ID at the start:

~~~sql
SELECT COALESCE(MAX(id), 0)
FROM product
WHERE active = TRUE;
~~~

Call that value `snapshotMaxId`. Every subsequent page uses:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id <= :snapshotMaxId
  AND id > :afterId
ORDER BY id
LIMIT :size;
~~~

The `snapshotMaxId` predicate prevents newly added rows with IDs higher than the initial mark from appearing on later pages. This is useful for append-only data or when only excluding new INSERTs is required.

It is not a full database snapshot:

- Older rows can still be DELETEd.
- Older rows can be UPDATEd to enter/leave the filter.
- IDs allocated earlier whose transactions commit later can appear after the max ID was read, depending on ID allocation and commit order.
- Changes in related tables can alter join results.

Therefore, clearly document that a cutoff only bounds the key range and does not guarantee immutability of all row contents.

### 12.2. Time-Based or Business-Version Snapshots

If records have an immutable `created_at`, you can capture an `asOf` timestamp on the first request and apply:

~~~sql
WHERE created_at <= :asOf
  AND id > :afterId
~~~

This excludes most rows created after the timestamp. However, it does not preserve old values when existing rows are updated or deleted. To reconstruct state at a point in time, the schema needs history/versioning or an appropriate temporal/audit mechanism.

### 12.3. Materialized Snapshot / Export Jobs

For reports or exports requiring a fixed dataset:

1. Create an export job.
2. Freeze the ID set or write the snapshot into a staging/materialized table.
3. Have a worker process the snapshot in batches.
4. Persist checkpoints/cursors to resume.
5. Return the file or result upon completion.
6. Clean up the snapshot according to TTL/retention policies.

This increases storage and preparation work but decouples snapshot lifecycle from HTTP connections. It suits large reports far better than holding a long transaction.

## 13. Choosing Total Count Semantics

Not every API requires an exact total. Choose one of the following semantics:

| Semantics | Description | Best Suited For |
|---|---|---|
| Exact per response | Items and total share a snapshot within one response | Admin pages needing exact totals |
| Current count | Count reflects the time of the count query | Frequently changing lists where UI accepts updates |
| As-of count | Total bounded by a defined cutoff/version | Browsing time-anchored datasets |
| Approximate count | Estimated count, accuracy not guaranteed | Very large datasets, dashboards/analytics |
| No total | Returns only items, cursor, and `hasNext` | Feeds, infinite scroll, exports |

The API contract should state the semantics clearly. If a field is named `totalElements` yet is actually approximate, rename or add metadata so clients do not display it as an exact count.

### 13.1. Exact Counts Have a Cost

In PostgreSQL, an exact `COUNT(*)` must determine how many rows satisfy the predicate under MVCC visibility rules. On large tables, counting may have to read many index pages/entries or table data; never assume it is O(1).

Suitable indexes can help filter/count queries, though they do not always eliminate all work. Inspect:

- Execution plan.
- Estimated vs. actual rows.
- Buffer hits/reads.
- Query duration.
- Count call frequency.

If total counting becomes a bottleneck, consider dropping totals, using `hasNext`, caching counts with a TTL, approximate counts, or business-maintained counter tables.

### 13.2. Approximate Counts in PostgreSQL

PostgreSQL stores estimated row counts in system catalogs such as `reltuples`, updated by `ANALYZE`/`VACUUM` and potentially stale. These statistics can be used for dashboards or rough estimates, but must not be used as exact totals for an API contract requiring absolute precision.

Estimating counts for complex filter conditions is even harder than estimating total table rows. When using approximate counts, return metadata indicating the figure is an estimate and when it was last updated.

## 14. Count First or Page First?

Execution order does not fix consistency on its own if isolation remains `READ COMMITTED`. However, it does affect latency and how out-of-range pages are handled.

### 14.1. Count First, Then Page

Advantages:

- Total is available even when the page exceeds the end of the set.
- Overly high page numbers can be rejected early if the API desires.

Disadvantages:

- Users wait for count before receiving the page.
- If count is slow, the entire response slows down.
- Under `READ COMMITTED`, the page running afterward still gets a different snapshot.

### 14.2. Page First, Then Count

Advantages:

- Empty pages can be detected early.
- Some APIs could emit items earlier when streaming, though total would not be ready yet.

Disadvantages:

- Count still needs to run if the response requires a total.
- Same snapshot discrepancy if the two statements do not share a snapshot.

### 14.3. Choose Based on Contract and Query Plan

If the response needs items and total simultaneously, use a single window-count statement or a `REPEATABLE READ` transaction. If total is unnecessary, fetch only the page and `hasNext`. If count is the costliest part, consider cached/approximate counts or dropping totals.

## 15. Constructing Page Responses Safely

A DTO can be defined as:

~~~java
import java.util.List;

public record PageResponse<T>(
    List<T> items,
    int page,
    int size,
    long totalElements,
    long totalPages,
    boolean hasNext
) {
    public static <T> PageResponse<T> of(
            List<T> items,
            int page,
            int size,
            long totalElements) {

        long totalPages = totalElements == 0
            ? 0
            : (totalElements + size - 1) / size;

        return new PageResponse<>(
            List.copyOf(items),
            page,
            size,
            totalElements,
            totalPages,
            (long) page + 1 < totalPages
        );
    }
}
~~~

Compute `totalPages` as `long` to avoid overflow on large datasets. Before computing offset, use `long` and check for overflow:

~~~java
long offset = Math.multiplyExact((long) page, size);
~~~

Never compute `page * size` with `int` if `page` can grow large. Validate `page >= 0` and `size` within allowed bounds before building queries.

### 15.1. Out-of-Range Page Numbers

If `totalElements` is 327 and `size` is 20, `totalPages` is 17, so valid page indices run from 0 to 16. When a client requests page 20, the API can:

- Return empty `items` while still returning `totalElements`/`totalPages`.
- Return 404/400 per API contract.

Usually returning 200 with empty `items` makes list handling easier for clients, though the choice must be consistent and documented.

## 16. Do Not Use Total Count to Infer hasNext Unnecessarily

If the API only needs to know whether a next page exists, query `size + 1` rows:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :sizePlusOne;
~~~

If more than `size` rows return:

1. Set `hasNext = true`.
2. Drop the extra trailing row.
3. Build the cursor from the last returned row.

Code example:

~~~java
import java.util.List;

public record ProductRow(Long id, String name) {
}

public record CursorPage<T>(
    List<T> items,
    Long nextAfterId,
    boolean hasNext
) {
}

public Mono<CursorPage<ProductRow>> findNext(
        long afterId,
        int size) {

    return databaseClient.sql("""
            SELECT id, name
            FROM product
            WHERE active = TRUE
              AND id > :afterId
            ORDER BY id
            LIMIT :limit
            """)
        .bind("afterId", afterId)
        .bind("limit", size + 1)
        .map((row, metadata) -> new ProductRow(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > size;
            List<ProductRow> items = hasNext
                ? List.copyOf(rows.subList(0, size))
                : List.copyOf(rows);

            Long next = items.isEmpty()
                ? null
                : items.get(items.size() - 1).id();

            return new CursorPage<>(items, next, hasNext);
        });
}
~~~

Here `collectList` holds at most `size + 1` elements because the SQL has `LIMIT` and `size` was validated. If `size` could be large, cap the input before adding 1.

This avoids running an exact `COUNT` on every request when the UI only needs a "Load more" or "Next" button.

## 17. Count Queries with Spring Data R2DBC

`ReactiveCrudRepository` does not automatically provide a `Page<T>` with total count in the same way traditional synchronous repositories do. A `Flux` merely represents a result stream; to produce a `PageResponse`, the application must define how total and items are fetched.

`DatabaseClient` can be used:

~~~java
Mono<Long> countActiveProducts() {
    return databaseClient.sql("""
            SELECT COUNT(*)
            FROM product
            WHERE active = TRUE
            """)
        .map((row, metadata) -> row.get(0, Long.class))
        .one()
        .defaultIfEmpty(0L);
}
~~~

`one()` emits a single value or empty if there are no rows. A `COUNT` aggregate normally always returns one row, even when the count is 0; `defaultIfEmpty` can still be kept as a safeguard for the mapper/implementation.

### 17.1. Do Not Use Whole-Table Count for a Filtered Page

If the page filters `active = true`, count must filter `active = true`. If the page enforces a tenant scope, count must enforce that tenant scope too. Never call an unfiltered `repository.count()` and pair it with a filtered page.

### 17.2. Immutable Filter Objects

When multiple criteria exist, bundle inputs into one object:

~~~java
import java.math.BigDecimal;

public record ProductFilter(
    Boolean active,
    String nameContains,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Long tenantId
) {
}
~~~

The service normalizes the filter once, then passes the exact same object to both count and page queries. Never create two separate filter objects that could drift in values.

## 18. Testing Consistency Between Count and Page

Unit tests with mocks can confirm a service combines total and items properly, but cannot verify PostgreSQL MVCC snapshots or isolation levels. Those behaviors require integration tests against a real database.

### 18.1. Testing Identical Filters

Seed a dataset of products with varying `active`/`inactive` states and categories. Invoke the API with filters, then assert:

- `items` contains only rows matching the filter.
- `totalElements` equals the number of unique entities matching the same filter.
- Subsequent pages use the same filter.
- Tenant/soft-delete scopes apply to both count and page.

### 18.2. Testing Count/Page Under READ COMMITTED

You can open two connections/transactions:

~~~text
Transaction A (READ COMMITTED)       Transaction B
--------------------------------     ----------------------------
BEGIN
SELECT COUNT(*) -> 10
                                     INSERT product
                                     COMMIT
SELECT page -> may see 11 rows
COMMIT
~~~

The test should coordinate with a latch/barrier so the INSERT commits right between the two statements. Verify two different snapshots can be observed. Do not rely on fixed sleeps, which make tests flaky.

### 18.3. Testing REPEATABLE READ

Repeat the scenario with Transaction A in `REPEATABLE READ`:

~~~text
Transaction A (REPEATABLE READ)     Transaction B
--------------------------------   ----------------------------
BEGIN
SELECT COUNT(*) -> snapshot S
                                   INSERT product
                                   COMMIT
SELECT page -> still uses snapshot S
COMMIT
~~~

Transaction A's COUNT and page must reflect the same snapshot. After Transaction A commits, new queries can see the newly inserted row.

### 18.4. Testing Single-Statement Window Counts

With `COUNT(*) OVER()`, verify `totalElements` repeats across every row of the page and matches the fixture. Add an out-of-range offset test to confirm how the API handles queries returning zero rows.

### 18.5. Testing Page Drift Between Two HTTP Requests

Read the first page, run an INSERT/DELETE in another transaction, then read the next page:

- Offset pagination may duplicate/skip due to shifting positions.
- Keyset pagination by ascending ID usually prevents new INSERTs ahead of the cursor from shifting the page.
- Both can reflect mutated data on later pages.

Tests must verify the exact published semantics rather than claiming keyset is a full snapshot.

## 19. Testing with StepVerifier and WebTestClient

`StepVerifier` is useful for testing publishers returning `PageResponse`:

~~~java
StepVerifier.create(repository.findActivePage(0, 20))
    .assertNext(page -> {
        assertEquals(20, page.size());
        assertEquals(327L, page.totalElements());
        assertEquals(17L, page.totalPages());
        assertTrue(page.hasNext());
    })
    .verifyComplete();
~~~

This is an example test against prepared fixture data; it is not a default repository number.

With `WebTestClient`, verify the HTTP contract:

~~~java
webTestClient.get()
    .uri("/api/products?active=true&page=0&size=20")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.items.length()").isEqualTo(20)
    .jsonPath("$.totalElements").isEqualTo(327)
    .jsonPath("$.totalPages").isEqualTo(17)
    .jsonPath("$.hasNext").isEqualTo(true);
~~~

If test data can be mutated by other tests, isolate databases/schemas or clean up fixtures to avoid execution-order dependencies.

## 20. Performance of Count and Page

A page query with `LIMIT` does not mean the whole operation is cheap. Exact counting can be the slowest part.

Contributing factors:

- Number of rows matching the filter.
- Predicate selectivity.
- Whether indexes match predicates and ordering.
- Joins and `DISTINCT`.
- MVCC visibility and dead tuples.
- Whether statistics are up to date.
- Cache/buffer state.
- Large offsets.

### 20.1. Indexes for Filters and Ordering

For a common query:

~~~sql
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset
~~~

A suitable index might be `(active, id)` depending on data distribution and workload. If `active` has low selectivity, the planner may pick another plan. Check `EXPLAIN (ANALYZE, BUFFERS)` on representative data.

### 20.2. Deep OFFSETs

With large offsets, the database may have to traverse many rows before returning the page. Keyset pagination usually fits sequential traversal on large sets better.

### 20.3. Caching Counts

If total count does not need per-request precision, it can be cached by filter key with a TTL. Ensure:

- Cache keys include all filter, tenant, and version fields.
- TTL and invalidation rules are defined.
- Acceptable staleness delay is documented.
- Count caches are never shared across tenants or authorization scopes.

A cached count is approximate/current-as-of-cache-time, no longer an exact per-response snapshot unless explicit data/version synchronization exists.

## 21. Edge Cases

### 21.1. Last Page Changing Under DELETEs

If count is 41 and size is 20, `totalPages` is 3. While a user is on page 2 (index 1), several rows are deleted, reducing total to 18. Page 2 may return empty even though the UI previously indicated that page existed.

The API can return an empty page with the updated total; clients can navigate back to the last valid page. If using an exact snapshot per response, page and total in that single response stay consistent, though subsequent requests can still change.

### 21.2. UPDATEs Moving Rows Into or Out of Filters

If the filter is `active=true` and a product switches `active` from true to false, that row disappears from the result set. Count and page must apply filters on the same snapshot when exact-per-response consistency is required.

### 21.3. GROUP BY and Total Number of Groups

If the API returns one summary row per category, `totalElements` should be the number of categories/groups returned, not the number of source products. The count query must count grouped results:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT category_id
    FROM product
    WHERE active = TRUE
    GROUP BY category_id
) grouped_categories;
~~~

Or use a window count on the already-grouped query. Clarify the pagination grain before writing the count.

### 21.4. COUNT DISTINCT on Joins

If a page returns each product once after filtering by category, count must count distinct product IDs or use `EXISTS` to avoid row multiplication:

~~~sql
SELECT p.id, p.name
FROM product p
WHERE EXISTS (
    SELECT 1
    FROM product_category pc
    WHERE pc.product_id = p.id
      AND pc.category_id = :categoryId
)
ORDER BY p.id
LIMIT :size OFFSET :offset;
~~~

Corresponding count query:

~~~sql
SELECT COUNT(*)
FROM product p
WHERE EXISTS (
    SELECT 1
    FROM product_category pc
    WHERE pc.product_id = p.id
      AND pc.category_id = :categoryId
);
~~~

`EXISTS` prevents multiplying products when joining across multiple category rows. Still inspect query plans on realistic data.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| COUNT and page use different filters | Total does not describe items | Share filters/criteria and write tests |
| Page enforces tenant scope while count does not | Leaks out-of-scope data counts | Apply the exact same authorization predicate |
| COUNT(*) over a join that multiplies entities | Total exceeds unique items | Use `COUNT(DISTINCT id)` or `EXISTS` |
| ORDER BY lacks a unique tie-breaker | Ordering can shift | Append primary key to ORDER BY |
| Assuming same `READ COMMITTED` transaction shares a snapshot | Count and page can still diverge | Use `REPEATABLE READ` or a single statement |
| Only setting `readOnly=true` | Does not elevate isolation automatically | Configure isolation level explicitly |
| Using `COUNT(*) OVER()` with an empty page | No row returned to read total | Handle empty pages via contract, CTE/LEFT JOIN, or separate snapshot count |
| Computing count on every request even when UI ignores it | Wastes queries and increases latency | Use `hasNext` or omit total |
| Reusing total from a previous page without snapshot definition | UI displays stale figures | Define current/as-of semantics |
| OFFSET on mutating data | Duplicated or skipped rows across pages | Use keyset or suitable snapshot/cutoff |
| Thinking keyset guarantees a snapshot | UPDATE/DELETE still changes result sets | Use versioned/materialized snapshots if needed |
| Holding `REPEATABLE READ` across multiple HTTP requests | Holds connections and snapshots too long | Use cutoffs or export snapshot jobs |
| Using whole-table count for a filtered page | Wrong total | Count with the same predicates |
| Not checking overflow when computing offset | Negative or wrong offset on large pages | Use `long` and `Math.multiplyExact` |
| Caching counts without documenting staleness | Clients assume total is exact | Publish approximate/as-of semantics |
| Unnecessary `COUNT(DISTINCT)` | Query can be more expensive | Identify grain and inspect execution plan |

## 23. Workflow for Designing Page and Total APIs

When building a paginated API with totals, proceed in order:

1. **Identify the data grain:** whether each item is one row, one unique entity, or one group.
2. **Define filters:** search, tenant, authorization, soft-delete, and all business predicates.
3. **Define ordering:** deterministic ordering with a unique tie-breaker.
4. **Pick pagination style:** offset if page jumping is required; keyset for sequential traversal of large sets.
5. **Define total semantics:** exact per response, current, as-of, approximate, or no total.
6. **If exact per response:** use a single statement or run count/page in `REPEATABLE READ`.
7. **Keep count/page predicates aligned:** avoid duplicating filter logic.
8. **Cap page size:** validate at the API and enforce `LIMIT` in SQL.
9. **Handle empty/out-of-range pages:** publish an explicit response contract.
10. **Test concurrent writes:** verify behavior under INSERT/UPDATE/DELETE.
11. **Measure performance:** inspect counts, deep offsets, indexes, and query plans.
12. **Monitor production:** count latency, page latency, rows returned, and pool usage.

## 24. Key Principles to Remember

- COUNT and page must use identical filters, tenant scope, authorization, and data grain.
- Joins can multiply rows; count unique entities using `COUNT(DISTINCT id)` or `EXISTS` where suitable.
- Pagination needs a deterministic `ORDER BY` with a unique tie-breaker.
- PostgreSQL `READ COMMITTED` creates a fresh snapshot per statement, even inside the same transaction.
- `readOnly=true` does not automatically ensure count and page share a snapshot.
- Use `REPEATABLE READ` for two queries in the same response when snapshot consistency is required.
- Or use `COUNT(*) OVER()` so page and total share a single statement snapshot.
- Window counts return no total on empty pages; handle this via contract, a follow-up query in the snapshot, or CTE/LEFT JOIN.
- Exact COUNTs carry a cost; `LIMIT` does not make counting the full set free.
- Exact-per-response consistency does not mean an entire multi-HTTP-request journey shares one snapshot.
- Offset can suffer page drift under INSERT/DELETE; keyset reduces position shifts from new rows ahead of the cursor.
- Keyset does not protect against UPDATE/DELETE or filter changes on its own.
- `SnapshotMaxId`/`asOf` cutoffs guarantee only the specific semantics fixed by the cutoff predicate.
- Never hold transactions and connections open across multiple UI requests; use versioned/materialized snapshots for long-lived export consistency.
- When you only need to know if more rows exist, fetch `size + 1` and return `hasNext` instead of `COUNT`.
- Use `totalElements`, `remainingElements`, and `approximateCount` accurately; never conflate semantics.
- Use `long` for offsets/counts and guard against overflow.
- Test isolation and concurrent writes against real PostgreSQL, not just mocked repositories.

Consistency between data pages and total counts begins with defining the exact dataset and point in time the API intends to represent. When a single response needs items and total from the same snapshot, use a single SQL statement with a window count or run count and page sequentially inside a `REPEATABLE READ` transaction on PostgreSQL. When users browse across multiple requests, a short transaction cannot preserve a snapshot throughout; select current/as-of semantics, cursors/cutoffs, or snapshot jobs accordingly. If the UI only needs to know whether more data exists, keyset pagination with `LIMIT size + 1` is usually simpler and cheaper than running an exact full-table count on every request.
