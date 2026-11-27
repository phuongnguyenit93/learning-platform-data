# Keyset Pagination and When to Apply It

Keyset pagination, also known as seek pagination, retrieves the next page based on the values of the last record from the current page. Instead of asking the database to skip a large number of rows with `OFFSET`, the query uses a comparison condition against the last sort keys and continues reading from that position.

With Spring Data Relational R2DBC, this pagination style can be implemented using `Criteria` and `Query` via `R2dbcEntityTemplate`, or by writing explicit SQL with `DatabaseClient`. Both approaches return data as `Flux`/`Mono`, fitting reactive processing. What matters is having a stable sort order, a cursor holding all sort values, and a continuation predicate that matches that order accurately.

## 1. Why Is Keyset Pagination Needed?

Offset pagination typically uses `LIMIT` and `OFFSET`:

```sql
SELECT id, created_at, status
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
```

The database must locate and skip the rows preceding the requested position before returning the next 20 rows. When offset is large, the skipping work can grow with page depth. Rows newly inserted or deleted earlier in the order can also shift the offset position between calls, leading to duplicate or missed results while users browse pages.

Keyset pagination uses the last row's values from the previous page as a bookmark:

```sql
SELECT id, created_at, status
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The example above uses tuple comparison in PostgreSQL syntax. On other databases, the equivalent condition may need to be written with `OR` and `AND`. The database can use an index to seek to the continuation point rather than counting and skipping a huge number of rows.

Keyset is especially useful when:

- Tables have many records and users routinely browse deep through multiple pages.
- APIs use a "Load more" button, infinite scroll, or continuous-loading streams.
- Data is appended continuously and must be traversed in a stable order.
- Queries have an index matching the filter and sort columns.
- Jumping directly to an arbitrary page number is not required.

Keyset is not the best fit for every screen. If data is small, page counts are low, or users need to jump directly to page 30, offset pagination can be simpler and more suitable.

## 2. Comparing Offset Pagination and Keyset Pagination

| Criterion | Offset pagination | Keyset pagination |
| --- | --- | --- |
| How pages are located | Number of rows to skip (`OFFSET`) | Sort key values of the last row on the previous page |
| Jumping to an arbitrary page | Convenient with page numbers | Unnatural; requires sequential cursor traversal or dedicated anchors |
| Deep pages | Can be expensive due to skipping many rows | Usually more stable if a suitable index exists |
| Data changes between calls | Offset can shift, causing duplicated or skipped results | Less affected by inserts ahead of the cursor, though not an absolute consistent snapshot |
| Client-side cursor | Not needed; typically sends page/size | Requires a cursor representing the last position |
| Total page count | Can combine with `COUNT` to compute | No natural total pages; typically returns only `hasNext` and next cursor |
| Suitable use cases | Small tables, numbered pages, reports needing page jumps | Large lists, infinite scroll, feeds, and load-more APIs |

Keyset changes how data is positioned, not the requirements for authorization, validation, page size limits, or database load control.

## 3. Prerequisite: Sort Order Must Be Stable

A cursor is only meaningful when the query has a deterministic order. Do not paginate a query without `ORDER BY`, because the database does not guarantee row order across executions.

Suppose orders are sorted newest first:

```sql
ORDER BY created_at DESC
```

Multiple orders can share the same `created_at`. If only the timestamp is used as the cursor, rows with the same timestamp can be duplicated or skipped at page boundaries. Add a unique key as a tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

In this example:

- `created_at` defines the primary business order.
- `id` breaks ties among rows sharing the same `created_at`.
- The pair `(created_at, id)` uniquely identifies a position in the result order.

If sorting by a single column that is already a primary key or unique key, an extra tie-breaker may not be needed. For any non-unique ordering, append a unique key at the end.

Columns used for the cursor should remain stable throughout traversal. If `created_at` or a sort field is modified after a row has appeared, the row can move past the cursor position and be duplicated or missed. Prefer immutable or rarely changing fields, such as creation timestamp and ID.

## 4. Rules for Building Continuation Conditions

With descending order:

```sql
ORDER BY created_at DESC, id DESC
```

Suppose the last row of the current page has:

```text
created_at = 2026-05-20T10:30:00
id         = 850
```

The next page must contain rows coming after this row in descending order. The condition is:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

The two branches mean:

1. Fetch rows with `created_at` older than the bookmark.
2. If `created_at` equals the bookmark, fetch rows with `id` smaller than the last row's ID on the page.

This combination is equivalent to lexicographic comparison on the pair `(created_at, id)` in descending order. Never use only `created_at < :lastCreatedAt`, because rows with the same timestamp and smaller IDs would be skipped.

With ascending order:

```sql
ORDER BY created_at ASC, id ASC
```

The continuation condition flips direction:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
```

General rule: for ascending order, take values greater than the cursor; for descending order, take values smaller than the cursor. When there are multiple sort columns, construct conditions by priority level, holding earlier columns equal to the cursor when evaluating the next column.

## 5. Mixed ASC and DESC Ordering

Not every query sorts all columns in the same direction. For example:

```sql
ORDER BY priority ASC, created_at DESC, id DESC
```

The continuation condition after cursor `(priority, created_at, id)` is:

```sql
WHERE priority > :lastPriority
   OR (
       priority = :lastPriority
       AND created_at < :lastCreatedAt
   )
   OR (
       priority = :lastPriority
       AND created_at = :lastCreatedAt
       AND id < :lastId
   )
```

Each branch checks the next column once all higher-priority columns equal the cursor. The comparison operator for the current column depends on that column's own sort direction.

With multiple columns, you can construct the condition following the pattern:

```text
key1 after cursor
OR (key1 equal cursor AND key2 after cursor)
OR (key1 equal cursor AND key2 equal cursor AND key3 after cursor)
...
```

Where "after cursor" is `>` if the column is sorted ASC and `<` if sorted DESC. This prevents operator mix-ups when ordering has mixed directions.

## 6. Example with `R2dbcEntityTemplate` and `Criteria`

Suppose the entity is:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("tenant_id")
    private Long tenantId;

    @Column("created_at")
    private LocalDateTime createdAt;

    private String status;

    // Constructors, getters, and setters.
}
```

The cursor holds all values needed to resume the order:

```java
public record OrderCursor(
        LocalDateTime createdAt,
        Long id
) {
}
```

For the first page, there is no cursor predicate. For subsequent pages, add the continuation group:

```java
public Flux<Order> findNextOrders(
        Long tenantId,
        OrderCursor cursor,
        int pageSize) {

    Criteria criteria = where("tenantId").is(tenantId);

    if (cursor != null) {
        Criteria afterCursor = where("createdAt").lessThan(cursor.createdAt())
                .or(where("createdAt").is(cursor.createdAt())
                        .and("id").lessThan(cursor.id()));

        criteria = criteria.and(afterCursor);
    }

    Query query = Query.query(criteria)
            .sort(Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")
            ))
            .limit(pageSize + 1);

    return template.select(Order.class)
            .matching(query)
            .all();
}
```

`tenantId` is always applied outside the cursor group so every page contains only data belonging to the current tenant. `afterCursor` expresses the proper SQL parenthesization: `created_at < cursorTime OR (created_at = cursorTime AND id < cursorId)`. `limit(pageSize + 1)` fetches one extra row to determine whether a next page exists.

The example uses Java property names in `Criteria` and `Sort`; Spring Data maps them to columns via entity metadata. The fluent `Query` API can have minor differences across Spring Data Relational versions, so verify against the Javadoc for your exact project version.

## 7. Why Fetch `pageSize + 1` Rows?

If you fetch exactly `pageSize` rows, the application does not know whether another row follows without running an extra `EXISTS` or `COUNT` query. A common technique is fetching one extra row:

1. Client requests `pageSize = 20`.
2. Query fetches at most 21 rows.
3. If 21 rows come back, the current page has 20 rows and `hasNext = true`.
4. If at most 20 rows come back, `hasNext = false`.
5. If there is an extra row, omit the 21st row from the page content.
6. The next cursor is built from the 20th row—the last row actually returned to the client.

Never build the cursor from the extra row. If you use the extra row as the bookmark, the next page starts after that row and skips the very row that was never returned.

Cap `pageSize` on the server, for example minimum 1 and maximum 100, so clients cannot request an arbitrary volume of data. When computing `pageSize + 1`, use an appropriate numeric type and validate bounds to prevent overflow or invalid values.

## 8. Building Page Results and Next Cursors

A response can include the item list, a `hasNext` flag, and the next cursor:

```java
public record CursorPage<T>(
        List<T> items,
        boolean hasNext,
        String nextCursor
) {
}
```

Example service collecting the bounded rows:

```java
public Mono<CursorPage<Order>> getOrders(
        Long tenantId,
        OrderCursor cursor,
        int requestedSize) {

    int pageSize = Math.max(1, Math.min(requestedSize, 100));

    return findNextOrders(tenantId, cursor, pageSize)
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > pageSize;
                List<Order> items = hasNext
                        ? List.copyOf(rows.subList(0, pageSize))
                        : List.copyOf(rows);

                String nextCursor = null;
                if (hasNext && !items.isEmpty()) {
                    Order last = items.get(items.size() - 1);
                    nextCursor = encodeCursor(
                            new OrderCursor(last.getCreatedAt(), last.getId()));
                }

                return new CursorPage<>(items, hasNext, nextCursor);
            });
}
```

`encodeCursor` is an application API-layer helper implemented to serialize the cursor into a token. This example uses `collectList()` because the query is already capped at most 101 rows; never collect an entire table into memory just to paginate.

If there is no extra row, `hasNext` is false and `nextCursor` can be left null. If an API wants to always return a cursor whenever data exists, it can be designed differently, but clients still need to know whether a next page exists.

## 9. Implementation with `DatabaseClient`

For complex queries or when precise SQL control is wanted, two SQL statements can be written: one for the first page and one for subsequent pages. PostgreSQL example with descending order:

```java
private static final String FIRST_PAGE_SQL = """
        SELECT id, created_at, status
        FROM orders
        WHERE tenant_id = :tenantId
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """;

private static final String NEXT_PAGE_SQL = """
        SELECT id, created_at, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND (
              created_at < :lastCreatedAt
              OR (created_at = :lastCreatedAt AND id < :lastId)
          )
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """;
```

Reading repository:

```java
public Flux<OrderRow> findPage(
        Long tenantId,
        OrderCursor cursor,
        int limit) {

    String sql = cursor == null ? FIRST_PAGE_SQL : NEXT_PAGE_SQL;
    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql)
            .bind("tenantId", tenantId);

    if (cursor != null) {
        spec = spec.bind("lastCreatedAt", cursor.createdAt())
                .bind("lastId", cursor.id());
    }

    return spec.bind("limit", limit)
            .map((row, metadata) -> new OrderRow(
                    row.get("id", Long.class),
                    row.get("created_at", LocalDateTime.class),
                    row.get("status", String.class)
            ))
            .all();
}
```

`OrderRow` is a flat read DTO. Column names in `row.get(...)` must match the column names or aliases returned by SQL. Java types must be compatible with the actual types provided by the driver. Parameter names are bound via the API instead of concatenating values into SQL strings.

The two SQL statements are selected via fixed code branches. Never accept raw SQL or sort column names from clients. If an API allows choosing sort order, map that choice through a server-approved list of sort keys and generate the matching continuation condition.

## 10. What Is a Cursor and What Should It Contain?

A cursor is information sufficient to identify the current page's position in a chosen order. With `ORDER BY created_at DESC, id DESC`, the cursor needs at least `created_at` and `id` of the page's last row.

A general-purpose cursor might contain:

```java
public record OrderPageCursor(
        int version,
        LocalDateTime createdAt,
        Long id,
        String sort,
        String filterFingerprint
) {
}
```

Meaning of the fields:

- `version`: enables controlled evolution of the cursor format.
- `createdAt`, `id`: sort values of the last row on the page.
- `sort`: identifies the sort direction/order for which the cursor was generated.
- `filterFingerprint`: helps detect reuse of a cursor with different filters.

A real cursor might also include tenant or query scope, though the tenant used for authorization must still come from the server-side authentication context. Never treat a client-supplied cursor as proof that the user has permission to access data.

## 11. Encoding and Validating Cursors

APIs typically return cursors as opaque tokens so clients do not need to understand internal structure. A simple approach is JSON serialization followed by URL-safe Base64. Base64 is only a representation encoding; it does not protect integrity or hide data.

If a cursor could be tampered with to alter bookmark values or filters, sign the token with HMAC or an equivalent protection mechanism. The server verifies the signature before using the values. If the cursor contains sensitive information, encrypt it with an appropriate mechanism; signing is not encryption.

When decoding, verify:

- Whether the token version is supported.
- Whether types and ranges of all fields are valid.
- Whether the cursor belongs to the current query type and sort order.
- Whether the filter matches the current request's filter.
- Whether the token has a valid signature and has not expired if expiration is enforced.
- Whether cursor values align with the current user's tenant/authorization scope.

A cursor must not be treated as an authentication secret or a substitute for authorization checks. Every request must still verify permissions and apply tenant/ownership predicates in the query.

## 12. Filters Must Remain Consistent Across Pages

The continuation condition only identifies position in the sort order. Business filters must be re-applied on every request:

```sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
```

If the first page filters `status = 'OPEN'` but the next page drops that predicate, results can include other statuses. Likewise, tenant, access permissions, time ranges, and other filters must remain unchanged.

You can embed a filter fingerprint in the cursor to reject tokens reused with different filters. The fingerprint should be generated from a canonical representation of meaningful filters; do not rely on arbitrary JSON key ordering or unnormalized query strings.

Do not rely on the filter fingerprint as a security mechanism. Queries must still bind values and enforce authorization predicates independently.

## 13. Keyset Pagination with Nullable Columns

The simplest continuation conditions assume sort columns are non-null. If a column can be null, SQL comparisons with `NULL` evaluate to `UNKNOWN`; `column < :cursorValue` does not automatically cover null rows.

There are three design approaches:

1. **Prefer `NOT NULL` columns:** pick sort keys that always have values, such as creation timestamps and IDs.
2. **Define explicit null ordering:** specify `NULLS FIRST` or `NULLS LAST` per database support, then extend the cursor predicate to distinguish null and non-null cursors.
3. **Use normalized values:** if appropriate for the business domain, create a non-null sort key column or generated column with clear rules.

PostgreSQL example:

```sql
ORDER BY published_at DESC NULLS LAST, id DESC
```

Here, the continuation predicate must handle cases where the cursor's `published_at` is null separately from when it is non-null. You cannot simply replace `<` and expect SQL to handle null ordering properly on its own.

For critical queries, avoid nullable sort keys unless there is a clear business need. A simple cursor over `NOT NULL` columns is easier to implement and test.

## 14. What Happens When Data Changes Between Pages?

Keyset reduces positional shifts caused by inserts at the top of a list, but it does not automatically create a database snapshot across multiple HTTP requests.

Suppose the first page returned the newest rows down to cursor C:

- A row newer than C inserted afterward typically falls ahead of the cursor and does not appear on subsequent pages. This is usually the desired behavior when continuing through history.
- A new row with sort keys smaller than C can appear on a subsequent page if it matches the cursor and filter predicates.
- A row deleted before it is read will no longer appear.
- A row already read whose sort field is updated to move past the cursor can appear again.
- An unread row updated to move ahead of the cursor can be skipped.
- Status or filter-membership changes can cause rows to enter or leave the result set between pages.

Thus, keyset fits stable sequential traversal when sort keys rarely change, but it is not equivalent to an absolute consistent snapshot. If the business requires a snapshot, a fixed cutoff, version/snapshot ID, temporary result table, or suitable snapshot transaction mechanism may be needed. Keeping a database transaction open across multiple requests is generally unsuitable for standard APIs.

## 15. Using a Cutoff to Stabilize the Dataset

For newest-first feeds, you can fix the starting point using `asOf`:

```sql
WHERE tenant_id = :tenantId
  AND created_at <= :asOf
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
```

The first page records `asOf` and all subsequent pages reuse it. This prevents rows created after the start time from entering the result set, assuming `created_at` reflects creation time accurately and is not modified. It does not prevent row deletions, changes to other filters, or edits to existing data.

If a true multi-table snapshot or financial report is needed, a simple cutoff may not suffice. Clarify consistency requirements and pick appropriate isolation, snapshots/versions, or data models.

## 16. Indexes for Keyset Pagination

Keyset achieves performance advantages when the database has an index matching the filters and sort order. For the query:

```sql
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :limit
```

An index to consider is:

```sql
CREATE INDEX ix_orders_tenant_created_id
    ON orders (tenant_id, created_at DESC, id DESC);
```

`tenant_id` comes first because the query filters by tenant; the subsequent columns support traversal order. If the query also frequently filters by `status` with equality, consider `(tenant_id, status, created_at DESC, id DESC)`. Actual index column order must be guided by workload and execution plans.

Principles:

- Equality filter columns typically precede sort columns in a composite index.
- Column order and direction in the index should match `ORDER BY` and how the database can scan backward.
- The tie-breaker should be included in the index if it is part of the keyset order.
- Do not create multiple nearly identical indexes without measuring benefit and write cost.
- Use `EXPLAIN`/`EXPLAIN ANALYZE` on realistic data to confirm the database performs an index seek.

Indexes do not make queries fast automatically. If filters are unselective, sorting does not match the index, or the query planner selects a different plan, keyset may still read many rows.

## 17. Reverse Pagination

Many APIs need only "next page". If "previous page" is needed, you can query in the reverse direction relative to display order:

1. Use a cursor from the first row of the current page.
2. Build a condition finding rows preceding that row in display order.
3. Reverse `ORDER BY` so the database fetches the rows closest to the cursor.
4. Limit the number of rows fetched.
5. Reverse the list in the application to restore the original display order.

For example, if display order is `created_at DESC, id DESC`, to fetch rows immediately before the current page, the query can use `created_at > cursorTime OR (created_at = cursorTime AND id > cursorId)`, order by `created_at ASC, id ASC`, apply the limit, and reverse the result. Exact predicates must match how the top-of-page cursor is defined.

If the API does not need backward navigation, do not implement reverse traversal just to mimic page-number UIs. Keep the contract simple based on actual requirements.

## 18. Comparing Keyset with Spring Data's Scrolling API

Spring Data Commons provides scrolling abstractions such as `ScrollPosition`, `Window`, and keyset-based scrolling in certain repository/store types. However, support depends on the store module, repository type, and Spring Data version; do not assume every scrolling API in Spring Data JPA is present or behaves identically in reactive R2DBC.

Before using built-in scrolling APIs, check the documentation for your exact Spring Data Relational/R2DBC version and repository signatures. If the reactive repository or specific query does not yet support the needed scrolling style, implement seek pagination explicitly using `Criteria`/`Query` or `DatabaseClient` as shown in this article's examples.

Manual implementation also makes cursor predicates, tenant filters, sort orders, and token generation transparent. In exchange, the application is responsible for ensuring all query branches use the same order, filters, and cursor rules.

## 19. When to Use Keyset and When Not To

| Scenario | Usually Suitable Choice | Reason |
| --- | --- | --- |
| Tables with millions of records, sequential forward browsing | Keyset | Avoids deep offsets and uses index seeks |
| Infinite scroll or "Load more" button | Keyset | Natural cursor for loading the next chunk |
| Chronological feeds with an ID tie-breaker | Keyset | Resumes stably from the last bookmark |
| Small tables with only a few pages | Offset | Easy to implement, low skipping cost |
| Users need to jump directly to page 50 | Offset or dedicated page-anchor strategy | Keyset has no natural numeric page position |
| Total pages and current page number required | Offset with count, or a different API design | Keyset usually does not compute total pages |
| Arbitrary dynamic sort without a tie-breaker | Not ready for keyset | Cursor cannot define a stable position |
| Absolute snapshot needed over long browsing sessions | Snapshots/versions or dedicated mechanism | Cursors do not hold snapshots across requests |

Keyset does not necessarily replace offset across an entire system. Both pagination styles can be used for different use cases.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| No stable `ORDER BY` | Row order shifts between requests | Sort explicitly and add a unique key |
| Cursor holds only a non-unique sort column | Skips or duplicates rows sharing the sort value | Add a tie-breaker and store all sort keys in cursor |
| Wrong comparison operator | Next page repeats data or skips rows | Match `ASC` with `>` and `DESC` with `<` |
| Mixing sort directions with a single comparison operator | Continuation predicate violates lexicographic order | Build each branch per column and its own direction |
| Forgetting parentheses in predicate | Tenant/filter predicates can be loosened | Wrap cursor group in `AND (...)` and test cross-tenant data |
| Building cursor from extra row `pageSize + 1` | Skips the unreturned row | Build cursor from the last row actually returned |
| Dropping filters on later pages | Later pages come from a different dataset | Re-apply all filters and authorization |
| Using nullable sort key without null handling | Null rows are skipped or misordered | Use non-null keys or define null ordering and full predicates |
| Sort key mutated between requests | Rows can be duplicated or skipped | Prefer immutable keys or use snapshot/version when needed |
| Not capping page size | Requests can load too much data | Enforce min/max on server and fetch one extra row for `hasNext` |
| Using cursor instead of authorization | Users might attempt to access another data scope | Authenticate and enforce permissions on every request |
| Lacking a matching index | Keyset may still scan many rows or sort expensively | Design composite indexes and inspect execution plans |

## 21. Testing Keyset Pagination

Tests must demonstrate that consecutive pages neither duplicate nor skip rows on a stable dataset. Create multiple rows sharing the same primary sort value to force the tie-breaker to activate.

Example data:

| ID | `created_at` | Descending Order |
| ---: | --- | ---: |
| 105 | 10:00 | 1 |
| 104 | 10:00 | 2 |
| 103 | 10:00 | 3 |
| 102 | 09:00 | 4 |
| 101 | 08:00 | 5 |

With page size 2 and `ORDER BY created_at DESC, id DESC`, expected results:

- Page 1: IDs 105, 104; cursor `(10:00, 104)`.
- Page 2: IDs 103, 102; cursor `(09:00, 102)`.
- Page 3: ID 101; no next cursor.

Cases to verify:

1. First page has no cursor and returns the first rows in order.
2. Next page uses both cursor values properly.
3. Multiple rows sharing a timestamp are paginated completely thanks to the ID tie-breaker.
4. No rows are duplicated or skipped in an unchanging dataset.
5. The extra row is used only for `hasNext` and is not dropped across pages.
6. Tenant, status, and date-range filters are applied on every page.
7. Malformed, expired, or invalidly signed cursors are rejected.
8. Page size 0, negative, or exceeding the limit is handled per the API contract.
9. Nullable columns and mixed sort directions are tested if supported by the use case.
10. Behavior under inserts, deletes, or sort-key updates between pages is clearly defined.

In reactive code, `StepVerifier` can be used to verify publishers. Across a full pagination sequence, integration tests should invoke pages consecutively with `nextCursor`, concatenate received IDs, and compare them against the expected database order.

## 22. Implementation Workflow

When designing a keyset pagination endpoint, follow this sequence:

1. Determine whether the use case needs sequential load-more or jumping to page numbers.
2. Choose a business-meaningful, stable sort order.
3. Add a unique key as a tie-breaker if the primary sort key can repeat.
4. Determine ASC/DESC direction for each column and write the continuation predicate in exact lexicographic order.
5. Choose `Criteria`/`Query` or `DatabaseClient` based on complexity and SQL control needs.
6. Re-apply all filters, tenant scope, and authorization on every request.
7. Fetch `pageSize + 1`, trim the extra item, and create the cursor from the last returned row.
8. Encode/validate cursors at the API boundary; never substitute cursors for access control.
9. Create a matching composite index and verify with execution plans.
10. Test duplicate sort keys, the last page, mutating data, and invalid cursors.
11. Monitor query latency, rows read, page sizes, and error request rates.

## 23. Practical Guidelines

- Use keyset for large lists, infinite scroll, and sequential traversal flows.
- Pick a deterministic `ORDER BY` and append a unique tie-breaker at the end.
- Store all values needed to reconstruct the position in order inside the cursor.
- For ASC, continuation uses `>`; for DESC, `<`; handle each column individually for mixed sorting.
- Keep the cursor predicate inside parentheses and combine it with tenant/filters using `AND`.
- Fetch one extra row to determine `hasNext`; build the cursor from the last row actually returned.
- Re-apply filters and authorization on every page.
- Use non-null and rarely changing sort columns; otherwise define null ordering and mutation behavior explicitly.
- Cap page size, bind all values, and validate cursors.
- Create indexes matching equality filters and sort order; verify with query plans.
- Do not assume cursors provide an absolute consistent snapshot or total page count.
- Check built-in scrolling support in your exact Spring Data R2DBC version before using it; if unsuitable, implement explicit seek queries.

## 24. Conclusion

Keyset pagination identifies the next page using the sort keys of the previous page's last row. With `created_at DESC, id DESC`, the continuation condition is `created_at` smaller than the cursor or equal timestamps with `id` smaller than the cursor. A unique tie-breaker, properly grouped predicates, and matching indexes are essential for stable and efficient pagination.

In Spring Data Relational R2DBC, predicates can be built with `Criteria`/`Query` or SQL via `DatabaseClient`, then processed through reactive publishers. Keyset suits large lists and sequential loading; offset remains suitable when page jumping is needed or data is small. Cursors help position results but do not replace authorization and do not guarantee an absolute snapshot while data is changing. Choose the method based on actual needs, define ordering clearly, and test edge cases before exposing the API.
