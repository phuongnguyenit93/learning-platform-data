# Designing Paginated Results When Total Record Count Is Not Needed

## 1. Why Doesn't Every Paginated API Need a Total Count?

Many screens only need to display a batch of records and let users click **Next** or **Load more**. They do not need to know how many total rows exist in the table, how many pages there are, or where the current records sit within the entire dataset.

If an API always computes the total record count, every request may have to execute an extra `COUNT` query. With large tables or complex filters, the count query can consume substantial resources even though the returned page only contains a few dozen rows. A count query can also end up scanning a much larger data range than the page query itself.

In Spring Data Relational R2DBC, you can design paginated responses without totals by fetching one more row than the number of rows to display. For example, if the client requests 20 rows, the server queries at most 21 rows:

- If 21 rows come back, the server returns the first 20 rows and sets `hasNext` to `true`.
- If at most 20 rows come back, the server returns all of them and sets `hasNext` to `false`.

This avoids a separate `COUNT` query solely to know whether a next page exists. It fits list screens, feeds, histories, recent activity views, and load-more APIs.

This lesson covers designing the response, implementing it with R2DBC, choosing between offset and keyset pagination, handling concurrent data changes, and testing pagination behavior.

## 2. Page, Slice, and Minimal Paginated Results

Different paginated result types answer different questions.

| Result Type | Typical Information Included | Total Count Needed? | Best Suited When |
|---|---|---:|---|
| Page | Content, page number, size, total elements, total pages | Usually yes | UI needs page numbers or total result counts |
| Slice | Content, page info, and `hasNext`/`hasPrevious` | Not necessarily | UI only needs to know if more data can be loaded |
| Cursor page | Content, next cursor, and possibly previous cursor | No | Large datasets, continuous pagination |
| Infinite feed | Content and an indicator of remaining data | No | Timelines, activity feeds, load more |

`Page` may require a count query to determine total elements and total pages. How Spring Data executes counts can be optimized in some cases, but if the API does not use totals, asking for a count upfront is unnecessary work.

`Slice` focuses on answering: "Are there any more elements after this slice?" A cursor page focuses on answering: "Where do I resume from?"

In reactive repositories, pay attention to the return types supported by the Spring Data R2DBC version in use. Reactive queries typically return `Flux` or `Mono`; do not assume every repository method can return `Page` or automatically construct a `Slice` with the same count semantics as imperative repositories. When `hasNext` is needed explicitly, you can implement bounded queries in `DatabaseClient` or `R2dbcEntityTemplate` and construct the response DTO yourself.

The key principle is that the API contract should include only the information consumers actually need. If the client only needs a Next button, omit `totalElements` and `totalPages`.

## 3. The Fetch-One-Extra-Row Technique: limit + 1

Suppose the page size requested by the client is N. The server queries N + 1 rows.

~~~text
Client requests size = 5

Database returns:
[A, B, C, D, E, F]

Server:
- Returns content: [A, B, C, D, E]
- Drops row F from content
- hasNext = true

If database only returns:
[A, B, C]

Server:
- Returns content: [A, B, C]
- hasNext = false
~~~

The (N + 1)-th row is solely proof that more data exists. Never include that row in the current response.

### 3.1. Algorithm

1. Validate page size.
2. Compute fetch size as page size plus one.
3. Set `LIMIT` in the query to fetch size.
4. Read at most fetch size rows.
5. If the number of read rows exceeds page size, set `hasNext = true`.
6. Strip the extra row from content.
7. Generate the next position/cursor if a next page exists.
8. Return the response without a total count.

Processing complexity in the application depends only on at most N + 1 rows. There is no need to read the entire result set before trimming.

### 3.2. Why Not Just Call take(N + 1)?

Reactor operators such as `take` limit how many elements downstream receives, but do not always guarantee the database only does work for N + 1 rows.

The limit must be placed in the query itself via `LIMIT`, `FETCH FIRST`, `TOP`, or the database's equivalent mechanism. Afterward, Reactor can process the publisher already bounded at the database.

### 3.3. Using collectList Is Safe Because Row Count Is Bounded

In a reactive pipeline, `collectList` is generally unsuitable for an unbounded `Flux` because it holds all results in memory.

With a query setting `LIMIT` to N + 1 and an explicit upper cap on N, `collectList` is reasonable for building a response containing both content and `hasNext`. Maximum memory for this step is bounded by the validated page size.

If the API needs row-by-row streaming instead of a JSON envelope, design a different contract. However, to return both `content` and `hasNext` in the same response, the server normally needs to know whether N + 1 rows were read before sending the envelope.

## 4. Designing Response DTOs

A simple offset response can look like:

~~~java
public record OffsetSlice<T>(
    List<T> items,
    int page,
    int size,
    boolean hasNext,
    Integer nextPage
) {
}
~~~

Illustrative JSON response:

~~~json
{
  "items": [
    {
      "id": 501,
      "status": "OPEN"
    },
    {
      "id": 502,
      "status": "OPEN"
    }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "nextPage": 1
}
~~~

The response omits `totalElements` and `totalPages`. Clients simply check `hasNext` to decide whether to render a Next or Load more button.

A cursor response can look like:

~~~java
public record CursorSlice<T>(
    List<T> items,
    int size,
    boolean hasNext,
    String nextCursor
) {
}
~~~

If `hasNext` is false, `nextCursor` should be null or omitted from JSON per API conventions. Never fabricate a dummy cursor for a final page.

### 4.1. Avoid Misleading Field Names

If the API does not know the total element count, do not send:
- `totalElements = 0`.
- `totalPages = 0`.
- `totalPages = -1`.
- `isLast` guessed from page size.

Such values easily mislead clients into thinking an exact count was provided.

Using `hasNext` accurately expresses what the server knows at query time.

### 4.2. Is hasPrevious Needed?

`hasPrevious` cannot be inferred automatically from `hasNext`. With offset pagination, if `page > 0`, next/previous page numbers can be provided per the contract. However, if rows were deleted between requests, the previous page may no longer contain the same items.

With cursor pagination, a previous cursor must be tracked or generated with a reverse-direction query. Do not send `hasPrevious = true` unless the server can resume backward accurately under the contract.

### 4.3. Keep Metadata Minimal

These fields are usually enough for load more:

- `items`: data from the current fetch.
- `size`: actual row count or requested maximum size per documented convention.
- `hasNext`: whether additional data existed at query time.
- `nextCursor` or `nextPage`: starting position for the next call.

If clients need the actual returned row count, `size` can be `items.size()`. If `size` represents the requested page size, document that clearly. Never use one `size` field with two conflicting meanings.

## 5. Implementing an Offset Slice with DatabaseClient

The following example uses PostgreSQL-style `LIMIT`/`OFFSET` and a status filter. Adjust timestamp types, column names, and syntax for your project's database and driver.

DTOs:

~~~java
public record OrderSummary(
    Long id,
    String status,
    LocalDateTime createdAt
) {
}

public record OffsetSlice<T>(
    List<T> items,
    int page,
    int size,
    boolean hasNext,
    Integer nextPage
) {
}
~~~

Service:

~~~java
@Service
public class OrderQueryService {

    private static final int MAX_PAGE_SIZE = 100;

    private final DatabaseClient databaseClient;

    public OrderQueryService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<OffsetSlice<OrderSummary>> search(
            String tenantId,
            String status,
            int page,
            int requestedSize) {

        int size = validatePageSize(requestedSize);
        validatePage(page);

        long offset = Math.multiplyExact((long) page, size);
        int fetchSize = size + 1;

        return databaseClient.sql("""
                SELECT id, status, created_at
                FROM orders
                WHERE tenant_id = :tenantId
                  AND status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :fetchSize
                OFFSET :offset
                """)
            .bind("tenantId", tenantId)
            .bind("status", status)
            .bind("fetchSize", fetchSize)
            .bind("offset", offset)
            .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("status", String.class),
                row.get("created_at", LocalDateTime.class)
            ))
            .all()
            .collectList()
            .map(rows -> toSlice(rows, page, size));
    }

    private int validatePageSize(int requestedSize) {
        if (requestedSize < 1 || requestedSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }
        return requestedSize;
    }

    private void validatePage(int page) {
        if (page < 0) {
            throw new IllegalArgumentException(
                "Page must be zero or greater"
            );
        }
    }

    private OffsetSlice<OrderSummary> toSlice(
            List<OrderSummary> rows,
            int page,
            int size) {

        boolean hasNext = rows.size() > size;

        List<OrderSummary> content = hasNext
            ? List.copyOf(rows.subList(0, size))
            : List.copyOf(rows);

        Integer nextPage = hasNext ? page + 1 : null;

        return new OffsetSlice<>(
            content,
            page,
            size,
            hasNext,
            nextPage
        );
    }
}
~~~

In this example, `tenantId` must come from an authenticated security context or an authorized source. Never trust an arbitrary `tenantId` from query parameters.

### 5.1. Why Does the Query Use a Two-Column ORDER BY?

The query sorts by `created_at DESC` and `id DESC`. If multiple orders share the same timestamp, `id` provides a stable secondary ordering.

With only `ORDER BY created_at`, the database may return rows sharing a timestamp in different orders across runs. When combined with `OFFSET`, a row can appear on two pages or be skipped.

Every pagination query needs a deterministic order, ideally ending with a unique key.

### 5.2. Why Is Offset Computed as a long?

Multiplying `page × size` can overflow a 32-bit integer when `page` is huge. Using `Math.multiplyExact` with `long` detects overflow instead of silently producing a negative or wrong offset.

Beyond overflow checks, the API should still cap maximum page depth or switch to cursor pagination for large datasets. A numerically valid offset can still be far too expensive for the database.

### 5.3. Why Is collectList Safe in This Example?

The SQL sets `LIMIT` to `fetchSize`, where `fetchSize` is at most `MAX_PAGE_SIZE + 1`. The service never collects the entire table.

If the query omitted `LIMIT` or page size had no upper bound, `collectList` could grow the heap with dataset size and defeat resource protection.

## 6. Implementing with R2dbcEntityTemplate

When the query fits the Criteria API, `R2dbcEntityTemplate` can be used instead of hand-written SQL.

Conceptual example:

~~~java
public Mono<OffsetSlice<Order>> findOpenOrders(
        int page,
        int requestedSize) {

    int size = validatePageSize(requestedSize);
    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(
            Criteria.where("status").is("OPEN")
        )
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size + 1)
        .offset(offset);

    return template.select(query, Order.class)
        .all()
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > size;

            List<Order> content = hasNext
                ? List.copyOf(rows.subList(0, size))
                : List.copyOf(rows);

            return new OffsetSlice<>(
                content,
                page,
                size,
                hasNext,
                hasNext ? page + 1 : null
            );
        });
}
~~~

This follows common Spring Data Relational APIs; check the exact `Query`, `limit`, `offset`, and `sort` signatures for your version. If your version lacks a specific API, use `DatabaseClient` for direct SQL control.

What matters remains ensuring the executed database query has a `size + 1` limit, stable sorting, and full authorization filtering.

## 7. Reactive Repositories and Page Limitations

In reactive applications, repository methods typically emit `Flux` or `Mono`. Do not design an API that requires a total count and then merely wrap blocking assumptions into a `Mono` to look reactive.

Key considerations:

- `Page` typically carries `totalElements` and `totalPages`, thus requiring count information.
- Reactive repositories do not necessarily support `Page` in the same way imperative repositories do.
- `Pageable` may be supported as a limit/sort parameter in some query methods and versions, but that does not mean the repository automatically provides a complete `Slice`.
- If exact `hasNext` via `limit + 1` is needed, control fetch size explicitly and build the response in the service.
- Check the documentation for your exact Spring Data R2DBC version rather than relying on Spring Data JPA behavior.

A repository can supply the `Flux` of data while the service builds the pagination envelope. That makes where page size, `hasNext`, and cursors are enforced explicit.

Never return a fake `Page` with guessed `totalElements`. If clients need exact totals, treat counting as a distinct requirement with clear costs and semantics.

## 8. Offset Pagination When Total Count Is Not Needed

Offset pagination can still be useful if users need the current page number or want to step back to a previous page.

For example:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize
OFFSET :offset;
~~~

Each page uses `fetchSize = pageSize + 1`. If the extra row exists, return `hasNext = true` and `nextPage = page + 1`.

### 8.1. Advantages

- Easy to understand and implement.
- Clients can request a specific page.
- Easy to support Previous/Next using page numbers.
- Easy to test on small datasets.
- Works well for moderate tables with proper indexes and queries.

### 8.2. Disadvantages

Large offsets can force the database to scan or skip many rows before returning results. Cost can rise with page depth depending on the execution plan and database.

If users repeatedly click Next across thousands of pages, keyset pagination is usually a better choice.

### 8.3. Capping Deep Pages

If you still use offset:
- Enforce a maximum page or maximum offset.
- Enforce a maximum page size.
- Index filter and sort columns.
- Monitor query latency by page depth.
- Return a meaningful error when clients request overly deep pages.
- Consider switching to cursors for large feeds.

Do not cite the absence of a total count to claim deep offsets are cheap. Counting and fetching deep pages are two separate costs.

## 9. Keyset Pagination When Total Count Is Not Needed

Keyset pagination resumes from the sort values of the last row on the previous page instead of skipping rows with offset.

Suppose data is sorted:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

The previous page's cursor contains `created_at` and `id` of the last returned row.

Next page:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize;
~~~

Still fetch `pageSize + 1` to determine `hasNext`.

### 9.1. Why Is the Secondary Key Required?

If only `created_at` is used in the cursor and multiple rows share the same timestamp, `created_at < lastCreatedAt` will skip remaining rows with that timestamp.

Adding `id` establishes a unique order:

- `created_at` smaller than the last timestamp.
- Or `created_at` equal to the last timestamp and `id` smaller than the last id.

This is a lexicographic comparison for the descending sort-key pair.

### 9.2. The Cursor Must Match ORDER BY

If sorting by `created_at DESC, id DESC`, the predicate must use that exact order and direction.

If sorting by `amount ASC, created_at DESC, id DESC`, the predicate becomes more complex because each field has its own direction. Build keyset logic per allowlisted sort combination, or restrict the API to fixed orders.

Never generate a cursor from one field while sorting the query by another.

### 9.3. Choosing Stable Sort Keys

Prefer fields that:
- Are non-null or have explicit null ordering.
- Have supporting indexes.
- Rarely change after record creation.
- Pair cleanly with a unique key.

`created_at` is usually more stable than `updated_at`. If `updated_at` is used as a cursor and a row gets updated, it can move past the cursor and be duplicated or skipped.

### 9.4. Indexes for Keyset Queries

Suppose the query filters by tenant and status and sorts by `created_at DESC, id DESC`. You may need an index matching predicate and sort order:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Exact index design depends on database, selectivity, filters, and workload. Use `EXPLAIN`/`EXPLAIN ANALYZE` on representative data to confirm the database can leverage the index.

Do not create indexes based purely on SQL shape without measuring write overhead and storage.

## 10. Implementing a Cursor Slice with DatabaseClient

Cursor DTOs:

~~~java
public record OrderCursor(
    LocalDateTime createdAt,
    long id
) {
}

public record CursorSlice<T>(
    List<T> items,
    int size,
    boolean hasNext,
    String nextCursor
) {
}
~~~

Simple service example with a decoded and verified cursor:

~~~java
public Mono<CursorSlice<OrderSummary>> nextOrders(
        String tenantId,
        String status,
        String encodedCursor,
        int requestedSize) {

    int size = validatePageSize(requestedSize);
    int fetchSize = size + 1;

    Mono<List<OrderSummary>> rows;

    if (encodedCursor == null) {
        rows = firstPage(tenantId, status, fetchSize);
    } else {
        OrderCursor cursor = cursorCodec.decodeAndVerify(encodedCursor);

        rows = nextPage(
            tenantId,
            status,
            cursor,
            fetchSize
        );
    }

    return rows.map(result -> {
        boolean hasNext = result.size() > size;

        List<OrderSummary> content = hasNext
            ? List.copyOf(result.subList(0, size))
            : List.copyOf(result);

        String nextCursor = hasNext
            ? cursorCodec.encode(content.get(content.size() - 1))
            : null;

        return new CursorSlice<>(
            content,
            content.size(),
            hasNext,
            nextCursor
        );
    });
}
~~~

Both `firstPage` and `nextPage` must set `LIMIT` to `fetchSize` at the database. Never fetch everything and use `subList` to fake keyset pagination.

### 10.1. First-Page Query

~~~java
private Mono<List<OrderSummary>> firstPage(
        String tenantId,
        String status,
        int fetchSize) {

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :fetchSize
            """)
        .bind("tenantId", tenantId)
        .bind("status", status)
        .bind("fetchSize", fetchSize)
        .map((row, metadata) -> mapOrderSummary(row))
        .all()
        .collectList();
}
~~~

### 10.2. Next-Page Query

~~~java
private Mono<List<OrderSummary>> nextPage(
        String tenantId,
        String status,
        OrderCursor cursor,
        int fetchSize) {

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND status = :status
              AND (
                  created_at < :lastCreatedAt
                  OR (
                      created_at = :lastCreatedAt
                      AND id < :lastId
                  )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :fetchSize
            """)
        .bind("tenantId", tenantId)
        .bind("status", status)
        .bind("lastCreatedAt", cursor.createdAt())
        .bind("lastId", cursor.id())
        .bind("fetchSize", fetchSize)
        .map((row, metadata) -> mapOrderSummary(row))
        .all()
        .collectList();
}
~~~

Adjust `LocalDateTime`/`Instant` types to match the column type and R2DBC driver. Do not parse timestamps arbitrarily from raw client strings.

### 10.3. The Cursor Must Be Built from the Last Returned Row

Suppose the query fetches 21 rows for page size 20. The 21st row only confirms a next page exists.

The next cursor must be based on the 20th row—the last item in `content` sent to the client. If you build the cursor from the 21st row, the next page starts after the extra row and skips that record.

This is a common off-by-one bug that drops a row at page boundaries.

## 11. Encoding, Signing, and Validating Cursors

A cursor is query-driving input sent back by clients. Never trust an unvalidated cursor.

A cursor can hold:
- Format version.
- Last sort keys.
- Sort direction.
- Filter fingerprint.
- Expiration timestamp.
- Snapshot/watermark if the API carries those semantics.

You can serialize the payload and sign it with HMAC to detect tampering. If the payload contains sensitive data, encrypt it rather than relying solely on Base64. Base64 is not security.

### 11.1. Cursors Must Bind to Filters

If the first page filtered `status = OPEN` but the next page reuses that cursor with `status = CANCELLED`, results may no longer make sense.

Store a fingerprint of the filters and sort inside the cursor and compare it against the next request. If it differs, return an invalid-cursor error or ask the client to restart.

### 11.2. Cursors Do Not Replace Authorization

Even when a cursor is signed, every request must still:
- Authenticate the user.
- Obtain the tenant from the security context.
- Enforce access permissions.
- Apply data filters.
- Verify the cursor belongs to the right query type.

Never treat a cursor as an authorization token granting access to data.

### 11.3. Set Size Caps and Expiration

A cursor should have:
- A maximum length.
- A supported format/version.
- An expiration time if required by the business.
- Clear decode error handling.
- No arbitrary SQL.
- No unnecessary sensitive secrets.

An overly large cursor becomes needless request payload overhead. Never let clients pass arbitrary predicates or column names.

## 12. Data Changing While Users Paginate

Omitting total counts does not mean data is immutable. While a client views the first page, other requests may insert, update, or delete rows.

### 12.1. Offset Can Duplicate or Skip Rows

Initial state:

~~~text
Page 1, size 3:
[100, 99, 98]

Expected page 2:
[97, 96, 95]
~~~

If a new row is inserted at the top of the list before the client fetches page 2, offset positions shift. The client may receive 98 again or skip another row depending on the query and sort.

If a row before the offset is deleted, the next page can shift in the opposite direction.

### 12.2. Keyset Is More Stable Against Inserts Ahead of the Cursor

If sort keys do not change and the cursor simply resumes from the last pair of values, inserting new rows before the cursor position generally does not shift already-passed rows the way offset does.

Still, keyset does not create an absolute snapshot:
- Deleted rows will stop appearing.
- New rows inserted after the cursor can appear on later pages.
- Rows whose sort keys change can move across the cursor.
- Filter membership changes can bring rows into or out of the result set.

Document the API's semantics explicitly: whether the list reflects the latest data per request or a fixed snapshot.

### 12.3. Snapshot Consistency for Exports

If the business requires exporting a complete dataset accurately at a single point in time, do not assume multiple independent cursor requests automatically share a database snapshot.

Consider:
- A meaningful watermark/`as-of` timestamp for the data.
- A snapshot table or materialized list of IDs.
- An export job reading within an appropriately managed transaction/snapshot.
- An immutable read model for the export process.

Never keep a database transaction open for several minutes just so a user can load pages over HTTP. Doing so holds connections and snapshots open for too long, putting pressure on the pool and database.

## 13. When Is COUNT Still Needed?

Not every API should drop totals. Some UIs or business flows genuinely need an exact count:

- UI must display "1–20 of 3,450".
- Users need to jump to the last page.
- Reports require exact totals.
- Business workflows need count reconciliation.
- Exports must confirm data volume before running.

In such cases, treat counting as a distinct part of the contract and measure its cost.

Consider:
- Counting only when the client requests it.
- Counting with suitable filters and indexes.
- Caching counts if update staleness is acceptable.
- Returning approximate counts if the product explicitly accepts them.
- Running counts asynchronously for large reports.
- Querying a pre-aggregated read model for totals.

Never return an approximate number in a `totalElements` field without disclosing its semantics. Clients may assume it is an exact count.

### 13.1. Count and Page Data May Not Share a Snapshot

If the count query and content query run separately, data can change between the two statements. For example, count returns 100, yet before the content query runs, several rows are deleted.

If exact consistency between count and content is required, evaluate transaction isolation and database snapshot semantics. This can increase cost and transaction duration.

If clients only need to know whether a next page exists, `limit + 1` is much simpler.

## 14. Endpoint Design and Client Experience

### 14.1. Offset Endpoint

Example:

~~~http
GET /orders?status=OPEN&page=0&size=20
~~~

Response:

~~~json
{
  "items": [],
  "page": 0,
  "size": 20,
  "hasNext": true,
  "nextPage": 1
}
~~~

Client continues:

~~~http
GET /orders?status=OPEN&page=1&size=20
~~~

The server must validate `page` and `size` on every request. Do not trust clients to keep filters or sort unchanged across pages if the contract requires consistency; embed a query fingerprint in a token or re-verify parameters.

### 14.2. Cursor Endpoint

Example:

~~~http
GET /orders?status=OPEN&limit=20
~~~

Response:

~~~json
{
  "items": [],
  "hasNext": true,
  "nextCursor": "eyJ2IjoxLCJrZXkiOi4uLn0.signature"
}
~~~

Client continues:

~~~http
GET /orders?status=OPEN&limit=20&cursor=eyJ2IjoxLCJrZXkiOi4uLn0.signature
~~~

The cursor value above is purely illustrative. Never use static or unsigned cursors in production.

### 14.3. Changing Filters Must Start Over

When the user changes status, keyword, sort, or tenant context, the client should discard the old cursor and start from the first page. A cursor bound to a prior query must not be reused for new filters.

The server must also verify the filter fingerprint to avoid returning data in an incompatible order.

### 14.4. Behavior When the Last Page Is Empty

If a client requests a page after data was deleted, the server can return:
- Empty `items`.
- `hasNext = false`.
- `nextCursor = null`.

This is a valid result. Do not throw a 404 merely because a page has no rows, unless the API explicitly defines different semantics.

## 15. Protecting Paginated Queries

Pagination does not automatically make a query safe or cheap.

Ensure you:
- Cap page size on the server.
- Cap page depth if using offset.
- Allowlist sort fields and directions.
- Bind all filter values.
- Limit filter count and `IN` list size.
- Apply tenant/security predicates.
- Set query and acquire timeouts.
- Select only needed columns.
- Maintain appropriate indexes.
- Monitor rows scanned and rows returned.

A `LIMIT 20` query can still scan millions of rows if filters lack indexes. `LIMIT` bounds returned results; it does not guarantee bounded database work.

Never accept raw `ORDER BY` or predicates from clients. Cursor sort keys must map from a fixed set of choices.

## 16. Testing Paginated Results Without Count

### 16.1. Testing a Full Page with hasNext

Seed 6 rows, request size 5:
- Response contains 5 rows.
- `hasNext = true`.
- The 6th row does not appear in content.
- Next position is generated from the 5th row.

### 16.2. Testing Exact Page Size Match

Seed exactly 5 rows, request size 5:
- Response contains 5 rows.
- `hasNext = false`.
- `nextCursor`/`nextPage` is null or omitted per contract.

This is a critical test because if the implementation checks `rows.size() >= size`, it will falsely report `hasNext`.

### 16.3. Testing a Partial Last Page

Seed 7 rows, request size 5:
- First page has 5 rows, `hasNext = true`.
- Second page has 2 rows, `hasNext = false`.

### 16.4. Testing an Empty Set

No matching rows:
- Empty `items`.
- `hasNext = false`.
- No cursor created.

### 16.5. Testing Duplicate Sort Key Ordering

Seed multiple rows sharing `created_at` but with different IDs. Verify ordering is stable and neither duplicates nor skips across page boundaries.

### 16.6. Testing That Count Is Not Executed

If the goal is to eliminate the count query, integration tests or instrumentation should verify paginated requests do not emit unnecessary `COUNT` statements.

Do not merely mock a repository method and assume the database skips counting if the real implementation might issue another query.

### 16.7. Testing Concurrent Inserts/Deletes

With offset:
- Insert a row at the top between two pages.
- Delete a row before the offset.
- Document duplication/skipping behavior according to chosen semantics.

With keyset:
- Insert a row before the cursor.
- Insert a row after the cursor.
- Update a sort key.
- Delete a row at the boundary.
- Verify behavior matches the contract.

### 16.8. Testing Cursors

- Valid cursor.
- Cursor with tampered signature.
- Expired cursor.
- Cursor from different filters.
- Cursor with unsupported format version.
- Cursor with mismatched tenant/query scope.
- Empty or overly long cursor.

### 16.9. Testing Resource Limits

Verify:
- Page size exceeding max is rejected.
- Query fetches at most `size + 1`.
- The whole table is never collected.
- Timeouts are enforced.
- No connection leaks occur when clients cancel.

## 17. Testing Examples with StepVerifier

Suppose the service returns `OffsetSlice`:

~~~java
@Test
void shouldReturnHasNextWhenExtraRowExists() {
    StepVerifier.create(
            orderQueryService.search("tenant-a", "OPEN", 0, 2)
        )
        .assertNext(slice -> {
            assertThat(slice.items()).hasSize(2);
            assertThat(slice.hasNext()).isTrue();
            assertThat(slice.nextPage()).isEqualTo(1);
        })
        .verifyComplete();
}

@Test
void shouldNotReportNextWhenResultEqualsPageSize() {
    StepVerifier.create(
            orderQueryService.search("tenant-a", "OPEN", 0, 2)
        )
        .assertNext(slice -> {
            assertThat(slice.items()).hasSize(2);
            assertThat(slice.hasNext()).isFalse();
            assertThat(slice.nextPage()).isNull();
        })
        .verifyComplete();
}
~~~

The second test assumes the database fixture has exactly two matching rows. Reset/seed fixtures explicitly so tests do not accidentally share mutated data state.

With cursors, tests must confirm the next cursor is derived from the last returned element, not the (N + 1)-th extra row.

## 18. Common Mistakes

| Mistake or Misconception | Consequence | Fix |
|---|---|---|
| Always running COUNT even when client ignores total | Increases database work and latency | Use `limit + 1` to determine `hasNext` |
| Fetching N rows and setting `hasNext = true` when N rows return | Last page with exactly N rows falsely claims another page exists | Fetch N + 1 and check `rows.size() > N` |
| Using `rows.size() >= N` for `hasNext` | Wrong result on a final page of exact size N | True only when the (N + 1)-th extra row exists |
| Using `take(N + 1)` without SQL `LIMIT` | Database may still do more work than necessary | Enforce limit at the database |
| Calling `collectList` on an unbounded `Flux` | Heap usage scales with entire dataset | Bound query with N + 1 first |
| `ORDER BY` without a unique key | Pages can duplicate or drop rows | Add a unique tie-breaker |
| Cursor uses different sort keys than `ORDER BY` | Can miss or duplicate rows | Align predicate, cursor, and sort |
| Building cursor from the (N + 1)-th row | Skips the extra row on the next page | Build cursor from the N-th returned row |
| Unbounded deep offsets | Queries slow down as page grows | Cap offset or use keyset |
| Using `updated_at` as cursor without accounting for edits | Rows can shift across the cursor | Prefer stable sort keys or define mutation semantics |
| Thinking keyset creates a snapshot | Inserts/updates/deletes can still appear across pages | Use watermarks/snapshots/jobs if consistency is needed |
| Treating cursor as authorization | Risk of cross-tenant access | Verify auth on every request |
| Cursor not bound to filters | Next page can use mismatched conditions | Sign and verify filter fingerprint |
| Sending fake `totalElements` | Clients mistake it for an exact count | Drop total fields from contract |
| Assuming reactive repositories always return `Slice` | Incompatible with current version's API | Check support; build custom response DTO when needed |
| Holding one long transaction while user clicks Next | Holds connections and snapshots open too long | Keep each request an independent query or use snapshot/export jobs |
| Not capping page size | Clients can request excessive rows | Validate and enforce max size on server |

## 19. Workflow for Designing a Count-Free Paginated API

1. Determine whether the client needs Next/Load more or truly needs total page counts.
2. If totals are not needed, remove `totalElements` and `totalPages` from the response.
3. Choose offset when page jumping is needed and dataset size is suitably bounded.
4. Choose keyset when datasets are large or clients navigate sequentially across many pages.
5. Set default and maximum page sizes on the server.
6. Define a deterministic sort order ending with a unique key.
7. Build the query with `LIMIT` equal to `page size + 1`.
8. Collect at most N + 1 rows and compute `hasNext`.
9. Return only the first N rows.
10. Build `nextPage` or `nextCursor` from the last returned row.
11. For cursors, sign/validate the cursor and bind it to filters/sort.
12. Enforce tenant authorization on every page.
13. Index columns supporting filters and sorting.
14. Test exact N, N + 1, fewer than N, empty sets, and duplicate sort keys.
15. Test concurrent data mutations between requests.
16. Monitor query duration, rows scanned, rows returned, and p95/p99 latency.
17. Add `COUNT` only if the product truly requires exact totals.

## 20. Self-Check Exercises

### Exercise 1: Computing hasNext

A client requests 10 rows. The database returns 10 rows. Can you conclude a next page exists?

Hint: Not yet. You must fetch up to 11 rows. If only 10 rows exist, `hasNext = false`.

### Exercise 2: Extra Row

Page size is 20 and the query returns 21 rows. How should the 21st row be handled?

Hint: Use it solely to set `hasNext = true`. Do not include it in `content` and do not build the cursor from it.

### Exercise 3: COUNT Query

A screen only has a Load more button. Are `totalElements` and `totalPages` needed?

Hint: No. The response only needs `items`, `hasNext`, and the next position/cursor.

### Exercise 4: collectList

Why is `collectList` appropriate in the `limit + 1` example yet dangerous on an unbounded `findAll`?

Hint: The first case collects at most N + 1 database-bounded rows; the second can load the entire table onto the heap.

### Exercise 5: Stable Ordering

A query only specifies `ORDER BY created_at`, yet many rows share the same timestamp. What problem can occur?

Hint: Ordering among rows with identical timestamps is undefined; add a unique key such as `id` as a tie-breaker.

### Exercise 6: Offset and Inserts

A new row is inserted at the top of the list after the client fetched page 1 via offset. How can page 2 be affected?

Hint: Offset positions shift, potentially duplicating or skipping rows. Keyset mitigates shifts caused by inserts ahead of the cursor.

### Exercise 7: Keyset Cursor

If the sort order is `created_at DESC, id DESC`, what information must the cursor contain?

Hint: The `created_at` and `id` values of the last returned row, plus metadata needed to identify the corresponding filter/sort.

### Exercise 8: Cursor Tampering

A client alters the `id` inside a signed cursor. What should the server do?

Hint: Verify the signature before using the cursor; reject invalid cursors.

### Exercise 9: Snapshots

Does keyset pagination guarantee all pages reflect a data snapshot at a single point in time?

Hint: No. Watermarks/snapshots or export jobs are required if the business demands snapshot consistency.

### Exercise 10: Deciding Between Page and Slice

A report must display the exact text "1–20 of 10,532 results". Should counting be omitted completely?

Hint: No. Counting is a product requirement. Measure and design an appropriate count query, or use pre-aggregated/cached figures if allowed by the contract.

## 21. Takeaways

- Not every paginated API needs total record counts.
- `Page` typically provides a total count; `Slice` focuses on `hasNext`/`hasPrevious`; cursor pages resume from sort-key positions.
- With reactive R2DBC, check version-specific `Page`/`Slice` support; custom response DTOs can be built from `Flux`/`Mono`.
- The `limit + 1` technique reveals whether a next page exists without a separate `COUNT`.
- Queries must set `LIMIT` in the database to `pageSize + 1`.
- `hasNext` is `true` only when the number of received rows exceeds `pageSize`.
- Return only the first `pageSize` rows; the extra row is used strictly as an indicator.
- `collectList` is safe when the query is bounded to N + 1 and N has an explicit maximum.
- Offset is easy to understand, but deep pages can be costly and sensitive to data mutations.
- Keyset fits large datasets and sequential navigation.
- Sorting must be deterministic and end with a unique key.
- Cursors must match `ORDER BY`, filters, and sort directions, and be built from the last returned row.
- Cursors must be integrity-checked and never replace authorization.
- Keyset reduces positional shifts but does not create an absolute snapshot.
- When exact counts are required, treat counting as a distinct requirement and measure its cost.
- Test exact N, N + 1, fewer than N, empty sets, duplicate sort keys, and data mutations between pages.
- Monitor query latency, rows scanned/returned, and performance across page depths.

When clients only need to know whether more items can be loaded, have the database return at most `pageSize + 1` rows and derive `hasNext`. This design eliminates unnecessary total-count work, keeps responses simple, and fits reactive pipelines cleanly. For large datasets, combining cursor/keyset pagination, deterministic sorting, proper indexes, and cursor validation keeps multi-page traversal predictable in cost.
