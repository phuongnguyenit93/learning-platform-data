# Offset Pagination and the Cost of Large Starting Positions

Offset pagination is a way of dividing query results into fixed-size chunks using two components: the number of rows to fetch (`LIMIT`) and the number of rows to skip before fetching (`OFFSET`). This is a common way to build lists with page numbers, previous/next page buttons, or controls that let users jump to a specific page.

In Spring Data Relational R2DBC, pagination can be expressed using `Pageable` on query methods where supported by the version, using `R2dbcEntityTemplate`, or by writing `LIMIT`/`OFFSET` directly through `DatabaseClient`. An important caveat is that larger offsets generally force the database to process and discard many rows before returning the needed slice of data. R2DBC lets the application consume results reactively, but it does not eliminate the cost of locating and skipping rows on the database side.

When datasets are small, offset pagination is typically simple and fast enough. As tables grow to millions of rows, users frequently open deep pages, or queries involve heavy joins/sorts, it is important to understand offset costs and consider keyset (seek) pagination.

## 1. How Do LIMIT and OFFSET Work?

Suppose you need to fetch a list of customers, with 20 rows per page. The first page starts at offset 0; the second page starts at offset 20; the third page starts at offset 40.

```sql
SELECT id, name, email
FROM customer
ORDER BY id
LIMIT 20 OFFSET 0;
```

The query above fetches at most 20 rows after sorting. The third page:

```sql
SELECT id, name, email
FROM customer
ORDER BY id
LIMIT 20 OFFSET 40;
```

The database skips the first 40 rows in the specified order and then returns up to the next 20 rows.

Meaning of the two parameters:

| Component | Meaning |
| --- | --- |
| `LIMIT n` | Maximum number of rows to receive |
| `OFFSET m` | Number of preceding rows to skip |

Offset starts at 0, not 1. If users choose 1-based page numbers, the standard formula is:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

For example, `pageNumber = 4`, `pageSize = 25` gives an offset of 75. In the Java API, use `PageRequest.of(3, 25)` because `PageRequest` page indices are 0-based.

## 2. Calculating Offset in Java

An API typically receives page number and page size from the request. Validate both values before passing them into a query:

```java
public record PageRequestInput(int page, int size) {
}

private static PageRequestInput validatePage(int page, int size) {
    if (page < 0) {
        throw new IllegalArgumentException("page must be >= 0");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size must be in range 1..100");
    }
    return new PageRequestInput(page, size);
}
```

When calculating offset manually, use a sufficiently wide integer type and guard against overflow:

```java
long offset = Math.multiplyExact((long) page, size);
```

`Math.multiplyExact` throws an error if the multiplication exceeds the `long` limit, instead of silently producing a wrong offset. When using `Pageable`, `getOffset()` returns `long`, while page size is typically `int`.

Do not allow clients to send an arbitrarily huge `size`. Large page sizes increase the number of rows the database must read, network transfer size, memory consumption, and response serialization time. Set an upper limit appropriate to the UI and system load.

## 3. OFFSET Requires a Deterministic Order

Pagination must include `ORDER BY`. Without ordering, the database does not guarantee which rows appear before or after others across executions. The same query with the same `LIMIT`/`OFFSET` can return rows in different orders due to execution plans, indexes, or data state.

For example:

```sql
-- Not stable enough for pagination.
SELECT id, name
FROM customer
LIMIT 20 OFFSET 40;
```

Instead, define an explicit order:

```sql
SELECT id, name
FROM customer
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

`created_at` can repeat across multiple rows. Append `id` as a tie-breaker to create a more stable total order. If you sort only by a non-unique column, rows sharing the same value can swap positions between queries.

A good order for pagination should:

- Be meaningful for the screen or business logic.
- Specify `ASC`/`DESC` directions explicitly.
- Include a unique key as a tie-breaker.
- Handle `NULL` values consistently if the sort column is nullable.
- Align with an index if the query runs frequently on large datasets.

Deterministic ordering prevents rows from being duplicated or skipped merely due to undefined order. However, it does not prevent all position shifts when data is inserted or deleted between page fetches; that issue must be addressed separately.

## 4. OFFSET Pagination in Spring Data R2DBC

There are several ways to implement this depending on the API and Spring Data version in use. With reactive repositories, do not assume every repository `Page<T>` type implies a single non-blocking reactive operation. `Page` typically needs the total row count to compute `totalElements` and `totalPages`; fetching that count is an additional query. Reactive query methods typically return `Flux<T>`/`Mono<T>`, and support for `Pageable` as a parameter depends on the module and version.

### Using `Pageable` When Supported by Query Methods

A derived query method may accept `Pageable` in versions/modules that support this parameter:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status, Pageable pageable);
}
```

Caller creates `Pageable`:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Flux<Customer> customers = customerRepository.findByStatus("ACTIVE", pageable);
```

This snippet illustrates a query method accepting `Pageable`. Check your project's Spring Data Relational R2DBC version to confirm parameter support and how sorting is applied. If the query method does not support it or finer SQL control is needed, compute the offset and use `DatabaseClient` as in the next example.

Do not confuse accepting a `Pageable` parameter with the framework always returning a `Page<T>`. In reactive repositories, `Flux<T>` is usually the appropriate return type for the row stream; if a total count is needed, run a separate count query and compose the publishers explicitly.

### Using `DatabaseClient` with LIMIT/OFFSET

For custom SQL, you can bind limit and offset directly:

```java
public Flux<Customer> findPage(int page, int size) {
    if (page < 0 || size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Invalid page"));
    }

    long offset = Math.multiplyExact((long) page, size);

    return databaseClient.sql("""
                SELECT id, name, email, created_at
                FROM customer
                WHERE status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """)
            .bind("status", "ACTIVE")
            .bind("limit", size)
            .bind("offset", offset)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email", String.class),
                    row.get("created_at", LocalDateTime.class)
            ))
            .all();
}
```

This is a SQL example using `LIMIT`/`OFFSET` syntax common in PostgreSQL and several other databases. Pagination syntax, parameter types, and binding support for limit/offset depend on the dialect and driver. For databases with different syntax, adjust the SQL to match the actual engine. `DatabaseClient` does not automatically translate arbitrary SQL into portable syntax.

### Using `R2dbcEntityTemplate`

`R2dbcEntityTemplate` offers a metadata-driven query API with `Query`. You can build criteria, sort, limit, and offset according to the version's supported API, then map results into entities:

```java
Query query = Query.query(where("status").is("ACTIVE"))
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        ))
        .limit(size)
        .offset(offset);

Flux<Customer> customers = template.select(Customer.class)
        .matching(query)
        .all();
```

Exact builder methods may vary across Spring Data Relational versions; verify against the API your project uses. The advantage of the template is that criteria and sort reference entity properties, letting mapping/dialect handle column names. For SQL joins, CTEs, or database-specific expressions, `DatabaseClient` is usually a better fit.

## 5. Why Are Large Offsets Often Expensive?

Consider this query:

```sql
SELECT id, created_at, title
FROM article
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

The application receives only 20 rows, yet the database still typically has to determine the order and walk past roughly the first 500,020 rows in query order to discard 500,000 rows before returning the next 20. How the database executes this depends on the execution plan, indexes, predicates, and engine; not every case has identical linear cost. Nevertheless, larger offsets generally mean the database does more work to reach the starting position.

Costs that can appear:

1. **Reading or scanning many entries:** the database must traverse rows or index entries preceding the offset.
2. **Sorting:** without an index supporting the order, the database may have to sort a large dataset before discarding the leading rows.
3. **Heap/table access:** an index may locate the order faster, but if columns not present in the index are needed, the database still has to fetch the corresponding data rows.
4. **Joins:** if offset is applied after a join, the database may have to produce/scan many intermediate rows before returning the page.
5. **Internal transfer and processing:** the database may not send discarded rows over the network, but it still has to process them inside the execution plan.

Thus, a 20-row response does not mean the database only touched 20 rows. Deep pages can be much slower than the first page even with the same page size.

### OFFSET Is Not the Same as Flux.skip()

These two approaches are different:

```java
// Database is asked to return all rows; the application skips on the client side.
return databaseClient.sql("SELECT id, name FROM customer ORDER BY id")
        .map((row, metadata) -> mapCustomer(row))
        .all()
        .skip(500_000)
        .take(20);
```

```sql
-- Database is asked to execute offset/limit.
SELECT id, name
FROM customer
ORDER BY id
LIMIT 20 OFFSET 500000;
```

`Flux.skip(n)` discards items after the publisher has already emitted them into the pipeline; the database/driver may end up reading and transmitting the skipped rows to the application depending on consumption behavior. `LIMIT/OFFSET` in SQL tells the database it only needs to return the page slice. SQL offset still incurs traversal cost on the database side, but generally avoids sending discarded rows over the network and into the Java pipeline.

Do not use `.skip(offset).take(size)` as a default substitute for SQL pagination on large queries.

## 6. The Role of Indexes in OFFSET Pagination

An appropriate index can reduce search and sort overhead. Suppose a frequent query is:

```sql
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

An index whose column order aligns with the predicate and sort can help the database scan in the required order:

```sql
CREATE INDEX idx_article_status_created_id
ON article (status, created_at DESC, id DESC);
```

The exact index should be based on selectivity, query frequency, sort order, database engine, and write workload. Do not create indexes simply by copying an example without inspecting query plans.

### What Indexes Help With and What They Do Not

- Can help filter by `status` and read in `(created_at, id)` order.
- Can avoid or reduce a separate sort step if the optimizer selects the matching index.
- Can reduce table accesses if the index covers all returned columns and the database supports index-only/covering scans.
- Does not make skipping hundreds of thousands of positions disappear by itself. In many execution plans, the database still has to advance past entries before the offset position.
- Does not guarantee the optimizer will pick the index; statistics, selectivity, and actual cost influence the decision.

If the query selects wide columns or columns outside the index, heap/table reads can still be expensive. Also weigh the write overhead and storage cost of additional indexes.

### Checking with EXPLAIN

Inspect the execution plan for both the first page and deep pages:

```sql
EXPLAIN
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

In PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` provides actual execution timing and buffer statistics by running the real query. `ANALYZE` actually executes the statement, so use it cautiously in production, especially for heavy queries or write statements.

When reading the plan, watch for:

- Estimated vs. actual row counts at each node.
- Whether a `Sort` node exists and how many rows must be sorted.
- Scan type chosen: sequential scan, index scan, index-only scan, or bitmap scan.
- Buffers read/hit and time spent per node.
- How cost changes as offset grows from 0 to 10,000, 100,000, or higher.

Never look solely at `LIMIT 20` and conclude a query is cheap. Measure the exact query against data and filters close to production conditions.

## 7. COUNT(*) and the Cost of Building a Full Page

A paginated UI often needs both the list of rows and the total row count to display the total number of pages. This typically requires two queries:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM customer
WHERE status = :status;
```

Count queries can be costly if predicates are complex, multiple tables are joined, or the table is huge. The database may have to inspect many matching rows to compute an exact count. Indexes and the optimizer can help, but never assume `COUNT(*)` is free.

### Not Every Response Needs a Total Count

If the UI only needs a "Next page" button, you can fetch `size + 1` rows:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :sizePlusOne OFFSET :offset;
```

If more than `size` rows come back, you know a next page exists. Then discard the extra row and return `hasNext = true`. This avoids running a count query on every request.

With reactive repositories, do not assume `Page<T>` is built for free. `Page` typically holds `totalElements`, so it requires a count. If you only need content and whether more pages exist, define a `Slice`/cursor response or a DTO with `hasNext`, depending on your project's API.

### Combining the Data Query and Count Query

If a total count is required, the two publishers can be combined:

```java
public Mono<PageResult<Customer>> findCustomerPage(
        String status,
        int page,
        int size
) {
    long offset = Math.multiplyExact((long) page, size);

    Flux<Customer> content = findCustomers(status, size, offset);
    Mono<Long> total = countCustomers(status);

    return Mono.zip(content.collectList(), total)
            .map(tuple -> new PageResult<>(
                    tuple.getT1(),
                    page,
                    size,
                    tuple.getT2()
            ));
}
```

Example response DTO:

```java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements
) {
    public long totalPages() {
        return totalElements == 0
                ? 0
                : (totalElements + size - 1) / size;
    }
}
```

`findCustomers` and `countCustomers` represent two separate queries. `Mono.zip` subscribes to and combines the results when the composed publisher is subscribed to. If the count and data queries must observe the same data snapshot, run them inside a reactive transaction with an appropriate isolation level. Otherwise, data can change between the two queries, causing `content` and `totalElements` not to reflect the same point in time.

## 8. Data Changing Between Page Fetches

Even when `ORDER BY` has a unique tie-breaker, offset pagination can still skip or duplicate rows when data changes between two requests.

For example, with page size 3 and ascending ID order:

```text
Page 0: 10, 20, 30
Page 1: 40, 50, 60
```

After the user reads page 0, a new row with ID 15 is inserted:

```text
New order: 10, 15, 20, 30, 40, 50, 60
```

Page 1 with `OFFSET 3` now returns `30, 40, 50`. Row 30 is duplicated because its position shifted. Similarly, if a row before the offset is deleted, a later row can shift forward and be skipped on the next request.

This is not an R2DBC bug; it is a consequence of defining each page by relative position in a mutable result set.

### Can Transactions Solve This?

A transaction with an appropriate isolation level can preserve a consistent snapshot within the scope of one operation spanning multiple queries. However, UIs typically call the page 0 and page 1 APIs in two separate HTTP requests, each with its own transaction. The earlier request's transaction cannot automatically preserve a snapshot for the subsequent request.

If users must browse a fixed snapshot across multiple requests, a more explicit design is needed, such as dataset snapshots/versions, a cutoff timestamp, or cursors anchored to a stable mark. Holding a transaction open while a user reads page by page is generally unsuitable because it holds connections and snapshots for too long.

## 9. Why Is Keyset Pagination Well-Suited for Deep Pages?

Keyset pagination (also known as seek pagination) identifies the next page using values from the last row of the previous page, rather than counting how many rows to skip.

Suppose a list is ordered by `created_at DESC, id DESC`. The previous page ended at:

```text
created_at = 2026-10-10T10:30:00
id = 9000
```

The next page fetches rows appearing after that value pair in descending order:

```sql
SELECT id, created_at, title
FROM article
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

This condition is equivalent to finding rows after cursor `(lastCreatedAt, lastId)` in the chosen order. There is no need to skip 500,000 preceding rows. With a suitable index, the database can seek directly to the target value range and fetch the bounded number of rows.

### Conditions for Keyset to Work Properly

- Sort order must be deterministic and have a unique tie-breaker.
- The cursor must contain values for all sort columns.
- Comparison predicates must accurately reflect each column's ascending/descending direction.
- Handle `NULL` explicitly because SQL comparisons with NULL do not yield ordinary true/false outcomes.
- If sorting by a column that can change during browsing, rows can move past the cursor; prefer immutable keys/timestamps.
- Indexes should start with equality filter columns followed by sort/cursor columns matching the query.

Keyset pagination fits "next/previous" buttons, infinite scroll, feeds, and large datasets. It is inconvenient when users need to jump straight to page 500 without intermediate cursors.

## 10. Keyset with a Simple Unique Key

If a list is sorted solely by ascending ID, the cursor is very simple:

```sql
SELECT id, name
FROM customer
WHERE id > :lastSeenId
ORDER BY id ASC
LIMIT :size;
```

On the first call there is no `lastSeenId`, so use a separate initial query or an appropriately constructed condition. After returning a page, save the last ID as the cursor for the next request.

Example using `DatabaseClient`:

```java
public Flux<Customer> findNextCustomers(Long lastSeenId, int size) {
    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("invalid size"));
    }

    if (lastSeenId == null) {
        return databaseClient.sql("""
                    SELECT id, name
                    FROM customer
                    ORDER BY id ASC
                    LIMIT :limit
                    """)
                .bind("limit", size)
                .map((row, metadata) -> new Customer(
                        row.get("id", Long.class),
                        row.get("name", String.class)
                ))
                .all();
    }

    return databaseClient.sql("""
                SELECT id, name
                FROM customer
                WHERE id > :lastId
                ORDER BY id ASC
                LIMIT :limit
                """)
            .bind("lastId", lastSeenId)
            .bind("limit", size)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class)
            ))
            .all();
}
```

This is a simple form of seek pagination. The cursor must be returned to the client, usually based on the last ID of the page. In real APIs, you can wrap the cursor together with page data in a DTO instead of making clients infer it themselves.

## 11. Keyset with Multiple Sort Columns

If sorting by `created_at DESC, id DESC`, storing only `id` is insufficient to describe the position when the primary order uses `created_at`. The cursor must contain both values.

Next-page predicate:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

When all columns share the same sort direction, some databases support tuple comparison:

```sql
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
```

Tuple comparison does not have identical syntax or behavior across all databases. Expanding the expression with `OR` is often easier to adapt across dialects. If sorting mixes directions, such as `score DESC, name ASC, id ASC`, build the lexicographic condition matching each column's exact direction:

```sql
WHERE score < :lastScore
   OR (score = :lastScore AND name > :lastName)
   OR (score = :lastScore AND name = :lastName AND id > :lastId)
```

Do not mechanically flip all operators if sort columns have different directions. Write the condition so it expresses the exact order produced by `ORDER BY`.

### Handling NULLs in Sort Keys

If a sort column is nullable, databases have different NULL placement rules depending on dialect or `NULLS FIRST`/`NULLS LAST`. `<`, `>`, and `=` comparisons with NULL evaluate to unknown. Therefore, cursors with NULL values require dedicated predicates to identify subsequent rows.

A simple approach is choosing non-nullable sort columns. When that is impossible, specify `NULLS FIRST` or `NULLS LAST` explicitly, add sort/flag expressions, and write the corresponding cursor predicates. Test NULL and non-NULL groups separately.

## 12. Index Design for Keyset

For this query:

```sql
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

A suitable index may be:

```sql
CREATE INDEX idx_article_status_created_id
ON article (status, created_at DESC, id DESC);
```

Equality filter columns are typically placed ahead of seek/sort columns in a composite index. Exact column order should be guided by actual queries, selectivity, and the database optimizer's rules.

Keyset is not automatically fast if there is no index or if the predicate cannot use the index. If the database must scan/sort most of the table, the gains may be smaller than expected. Use `EXPLAIN` and production-like data to confirm.

## 13. Offset vs. Keyset: Comparison

| Criterion | Offset pagination | Keyset pagination |
| --- | --- | --- |
| Page positioning | Number of rows to skip | Values from the last row of the previous page |
| Jumping to an arbitrary page | Convenient | Difficult without a cursor for that position |
| Deep pages | Often degrades as offset grows | Typically more stable with a matching index |
| Data changing before position | Can duplicate or skip rows between requests | Less affected by inserts/deletes before cursor, though still depends on sort key and mutations |
| Total page count | Easy to pair with a count query | Typically does not need total count |
| Cursor | Not needed | Must store and pass cursor |
| Sorting | Relatively easy to support dynamic sort | Sort must be fully encoded in cursor and predicate |
| Previous page | Easy to compute offset | Requires separate cursor/reversed condition |
| Use cases | Admin tables, search with page jumping, moderate datasets | Feeds, infinite scroll, logs, large datasets, sequential browsing |

Keyset typically avoids the row-skipping cost of deep pages, but it does not replace offset in all situations. If users need to jump directly to page 100, offset gives a simpler experience. If users only advance from their current position, a cursor is usually a better fit.

## 14. Response for Offset Pagination

If the UI requires the total number of pages, define an explicit response:

```java
public record OffsetPage<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages,
        boolean hasNext
) {
}
```

Once you have `content`, `page`, `size`, and `totalElements`, compute page counts:

```java
long totalPages = totalElements == 0
        ? 0
        : (totalElements + size - 1) / size;

boolean hasNext = page + 1L < totalPages;
```

If you skip the count query, you can fetch `size + 1` rows to compute `hasNext` and discard the extra row before returning the response. In that case, there is no exact `totalElements`, and the response should reflect that rather than fabricating a total page count.

For very large tables, always computing `totalPages` can be a significant cost. An infinite-scroll UI usually needs only a cursor and `hasNext`, not total page counts.

## 15. Pagination Combined with One-to-Many JOINs

A common mistake is applying `LIMIT`/`OFFSET` directly to the result set of a one-to-many join when the goal is to paginate the parent entity.

Suppose a customer has 10 orders. Joining `customer` with `orders` produces 10 rows for that single customer. If the query uses `LIMIT 10`, the database may return 10 rows belonging to the same customer, even though the page size is meant to be 10 customers.

If the goal is to paginate customers, paginate the root set first:

```sql
WITH page_customer AS (
    SELECT id, name
    FROM customer
    WHERE status = :status
    ORDER BY id
    LIMIT :limit OFFSET :offset
)
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number
FROM page_customer c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id;
```

The `page_customer` CTE selects the exact number of customers for the page. Then the join fetches all orders for the customers on that page. The result may have more than `limit` rows because one customer has multiple orders, yet the parent count matches the page size.

The count query must also count customers in the root set, not joined rows. If counting after a join is necessary, use `COUNT(DISTINCT c.id)` where appropriate.

## 16. Large OFFSETs and Optimization Options

When measurements show deep pages are slow, evaluate these steps in order:

1. **Reduce page size:** avoid returning hundreds or thousands of records per request if the UI does not need them.
2. **Select only needed columns:** avoid reading large payloads, JSON, or blobs when the list displays only a few fields.
3. **Create appropriate indexes:** support filter predicates and `ORDER BY`.
4. **Push predicates down to the database:** filter in SQL instead of loading many rows and using Reactor `filter`.
5. **Re-evaluate the count query:** omit total counts if the UI does not need them; if needed, optimize the count query separately.
6. **Paginate the root before joining children:** avoid applying limit to joined rows and miscounting parent entities.
7. **Switch to keyset:** if users browse sequentially and deep offsets are the bottleneck.
8. **Inspect query plans:** verify the database actually uses the index and check the number of rows processed.

Do not simply enlarge the connection pool or raise concurrency to cure slow offset queries. If the database must traverse hundreds of thousands of entries per page, adding more connections can overload the database without reducing the work per query.

## 17. Choosing Offset or Keyset Based on UI Requirements

### Offset Fits When

- Users need to jump to a specific page number.
- Datasets are moderate in size or maximum offset is capped.
- The UI requires total page count and total row count.
- Queries have good indexes and response times remain acceptable at deep pages.
- Minor data shifts between requests are acceptable.

### Keyset Fits When

- Users primarily click "Load more" or use infinite scrolling.
- Datasets are large and deep positions are accessed frequently.
- Ordering can be expressed with a stable cursor, such as `(createdAt, id)`.
- You want to avoid skipping large numbers of rows in the database.
- Direct jumping to arbitrary page numbers is not required.

### Both Can Be Combined

An application can use offset for admin screens that need page jumping and keyset for high-volume feeds or logs. The entire system does not have to choose a single strategy. Each endpoint should pick the strategy matching how users navigate data and the query characteristics.

## 18. Testing and Performance Measurement

Pagination tests should verify both data correctness and query cost.

### Correctness Testing

- The first page uses offset 0 and returns at most the page size.
- Subsequent pages advance offset by page size.
- The last row of the previous page does not reappear on the next page when data is unchanged.
- Ordering includes a unique tie-breaker.
- Pages beyond the end of the dataset return empty.
- Page size 0, negative, or exceeding the cap is rejected.
- Offset calculation does not overflow.
- Count and data queries use the exact same predicate.
- LEFT JOIN with root pagination neither drops parents nor duplicates parents.

Example using `StepVerifier`:

```java
StepVerifier.create(repository.findPage(0, 20))
        .expectNextCount(20)
        .verifyComplete();

StepVerifier.create(repository.findPage(1, 20))
        .expectNextCount(20)
        .verifyComplete();
```

This test assumes at least 40 matching rows exist. Add fixtures to test a partial last page and out-of-range pages.

### Performance Measurement

Generate a sufficiently large dataset and measure the same query at offset 0, 10,000, 100,000, and deeper positions. Record:

- p50/p95/p99 latency.
- Actual rows the database must traverse per the execution plan.
- Buffers/pages read.
- Whether sorting occurs.
- Separate count query duration.
- Database CPU and I/O.
- Connection counts and pool wait times.

Compare offset and keyset with identical filters, sorting, page size, and data. Do not draw conclusions from a single run; warm/cold caches, statistics, and concurrent load can change results.

## 19. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Pages have duplicate or missing rows | No stable `ORDER BY` or data changed between requests | Add a unique tie-breaker; consider keyset |
| Deep pages are much slower | Database must walk through many rows before offset | Use appropriate indexes or switch to keyset |
| Response has few parents despite large page size | LIMIT applied to one-to-many joined rows | Paginate root first, then join children |
| Count query is slow | Heavy count predicate/join or huge table | Optimize count, add indexes, or drop total if UI doesn't need it |
| Total pages don't match content | Data and count queries use different conditions or data changed | Align predicates; consider transaction/isolation |
| SQL returns too much data | Using `.skip()` in pipeline instead of SQL pagination | Push LIMIT/OFFSET down to the database |
| Negative or wrong offset | 1-based page numbers mixed with 0-based formula/API | Standardize page index convention and validate |
| Offset overflows | Multiplying page and size in too small an integer type | Compute with `long` and `Math.multiplyExact` |
| Sort cannot use index | Index column order does not match filter/sort | Check EXPLAIN and design composite index for the query |
| Keyset misses rows with same sort value | Cursor holds only part of the sort key | Store all sort columns and the tie-breaker |
| Keyset mishandles NULL values | Predicate does not reflect `NULLS FIRST/LAST` | Specify null ordering and write dedicated predicates |

## 20. Takeaways

- Offset pagination uses `LIMIT` to cap row count and `OFFSET` to skip preceding rows; offset is 0-based.
- The offset formula is `pageIndex * pageSize`; use `long`, validate inputs, and prevent overflow.
- Always use a stable `ORDER BY`, typically appending a unique key as a tie-breaker.
- Large offsets usually make the database scan/skip many rows before returning the page; reactive R2DBC does not remove that cost.
- `Flux.skip()` discards rows on the application side and can cause lots of data to cross the driver/network; prefer SQL pagination.
- Appropriate indexes can reduce sorting and data access, but do not make the cost of skipping huge offsets vanish in every execution plan.
- Count queries carry a separate cost; fetch total counts only when the UI or business logic genuinely needs them.
- Inserts or deletes between requests can cause offset pages to duplicate or skip rows even with a stable order.
- With one-to-many joins, paginate the root set first and then join children so page size counts parent entities accurately.
- Keyset pagination uses the last row's values as a cursor, typically performing better for deep pages and sequential browsing with the right index.
- Cursors must hold all sort keys, include a unique tie-breaker, and explicitly handle sort directions and NULL values.
- Use `EXPLAIN`/`EXPLAIN ANALYZE` and benchmark with realistic data before deciding whether to optimize or switch strategies.

When designing R2DBC pagination, start from how users navigate the list. If jumping to arbitrary pages is required and the dataset is moderate, offset is easy to implement. If continuous browsing over a large dataset is needed, consider cursor/keyset pagination so the database seeks from the last row of the previous page instead of skipping a massive number of rows.
