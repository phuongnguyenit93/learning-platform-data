# Cursor pagination

Cursor pagination splits a result set into pages based on the position of the last record read. Instead of asking the server to skip a number of rows using an offset, the client sends a cursor representing the previous page boundary. The server uses that value to locate subsequent records in the same sort order.

In GraphQL, cursor pagination is typically modeled using the Relay Connection pattern consisting of Connection, Edge, Cursor, and PageInfo. Spring for GraphQL handles schema declarations, argument binding, and resolver execution; the application still needs to design cursors, keyset queries, input validation, and page metadata. Merely adding `first` and `after` arguments to a schema does not automatically turn database queries into cursor pagination.

## 1. Why is cursor pagination needed?

Offset pagination is a simple way to paginate:

~~~graphql
query {
    books(page: 4, size: 20) {
        id
        title
    }
}
~~~

The server can translate this into SQL `LIMIT 20 OFFSET 60`. This is easy to understand and works well for small lists or admin pages that rarely change. However, large offsets can force the database to read and discard many rows before returning results.

Offsets also produce unstable results when data changes between requests. For example, after reading page one, a new record is inserted at the top of the list. The page two request using the old offset may return a duplicate record or skip a record.

Cursor pagination uses an exact position in the sorted dataset:

~~~graphql
query {
    books(first: 20, after: "eyJ2IjoxLCJpZCI6...") {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
~~~

The cursor marks the next starting point. The database can apply conditions on the sort columns to jump to rows after that position rather than skipping a large offset.

| Criterion | Offset pagination | Cursor pagination |
| --- | --- | --- |
| Parameters | page/size or offset/limit | first/after or last/before |
| Navigation | Easy to jump to any page | Moves forward/backward from a position |
| Deep pages | Can be slow due to large offsets | Typically steadier with keyset indexes |
| Changing data | Can duplicate or skip rows across pages | Less shifted by inserts/deletes before the cursor |
| Total pages | Easy to compute when a count is run | No count needed to fetch the next page |
| Bookmarking | Page number is easy to store | Cursor can be stored to resume from a position |
| Implementation complexity | Low | Higher: cursor codec, sort keys, and page info |

Cursor pagination does not automatically guarantee strict snapshot consistency. If a record updates its sort column between two reads, it can cross the cursor boundary. For consistent snapshot traversal, add snapshot/version semantics or bound queries to a fixed timestamp.

## 2. Relay Connection pattern

The Relay Connection pattern standardizes response structure so clients can paginate different node types uniformly.

- **Connection:** the paginated result of a collection.
- **Edge:** an item in the connection, containing a node and a cursor.
- **Node:** the domain object, such as Book.
- **Cursor:** a string representing an edge's position in the result order.
- **PageInfo:** metadata about the current page and whether forward/backward traversal is available.

Illustrative GraphQL schema:

~~~graphql
type Query {
    books(
        first: Int
        after: String
        last: Int
        before: String
        filter: BookFilter
    ): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}

input BookFilter {
    keyword: String
    status: BookStatus
}
~~~

`totalCount` is an optional field. If the database must run `COUNT(*)` over a large dataset, this field can be much more expensive than the page query itself. Include it only when the product genuinely needs it and has an efficient way to compute it.

Relay conventions typically use `first/after` for forward pagination and `last/before` for backward pagination. Define the API contract clearly, such as disallowing sending both `first` and `last` or both `after` and `before` in the same request.

## 3. A cursor must represent a stable position

A cursor should not simply be a page number or offset. It must contain enough values to pinpoint a record within the sort order.

Suppose the book list is sorted by:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

The cursor can contain:

~~~json
{
  "version": 1,
  "createdAt": "2026-03-10T08:30:00Z",
  "id": "a2d3c2d0-5b0d-4f2c-8a9b-31b10e4c7f20"
}
~~~

The two values `createdAt` and `id` form the sort key. `id` serves as a unique tie-breaker so two records with identical timestamps still have a deterministic order.

Cursors should be treated as opaque on the client side. Clients receive a cursor from an edge and pass it back verbatim in `after` or `before`; clients should not inspect or construct cursor contents themselves.

URL-safe Base64 is a common way to encode the payload:

~~~java
String cursor = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
~~~

Base64 only encodes; it does not encrypt or prevent tampering. If cursors contain sensitive info or clients must not alter sort keys, sign payloads with HMAC or use signed tokens. Never include secrets, credentials, or unnecessary personal data in a cursor.

## 4. Designing a sort key with a total order

A cursor only works reliably when the sort order is deterministic. Do not sort solely by `createdAt` if multiple records can share the same timestamp:

~~~sql
ORDER BY created_at DESC
~~~

If two rows have identical `created_at`, the database is not required to maintain a consistent order across queries. When a cursor splits a group of rows with identical timestamps, a record can be duplicated or skipped.

Add a unique column as a tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

A sort key must have deterministic ordering, be unique when combining its columns, have an exact representation in the cursor, use matching comparison rules in both the codec and database, and be backed by an appropriate index. If a sort field can be null, define nulls first/last explicitly and include null state in the predicate/cursor, or choose a non-nullable sort key.

## 5. Keyset predicate for forward pagination

With descending order:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

To fetch records after a cursor containing createdAt and id, the condition is:

~~~sql
WHERE
    created_at < :cursorCreatedAt
    OR (
        created_at = :cursorCreatedAt
        AND id < :cursorId
    )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

This condition is equivalent to tuple comparison in databases that support tuple comparisons. The explicit expression is often easier to port across SQL dialects. For ascending sort order, flip the comparison operators and `ORDER BY` direction accordingly. Never keep a less-than predicate when switching `ORDER BY` to `ASC`.

Filters must be applied in the same query:

~~~sql
SELECT id, title, status, created_at
FROM book
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

In practice, the cursor predicate is added only when a cursor is provided. Filters and authorization scope must always be applied before pagination limits.

## 6. Fetching n + 1 records to determine hasNextPage

If the client requests `first = 20`, the server fetches up to 21 records:

1. Query with `LIMIT first + 1`.
2. If 21 records are returned, at least one subsequent record exists.
3. Set `hasNextPage = true`.
4. Drop the 21st record from the returned list.
5. Build edges and cursors for the remaining 20 records.

Example:

~~~java
int requestedSize = 20;
List<Book> rows = repository.findAfter(cursor, requestedSize + 1);

boolean hasNextPage = rows.size() > requestedSize;
if (hasNextPage) {
    rows = new ArrayList<>(rows.subList(0, requestedSize));
}
~~~

This technique avoids running a `COUNT(*)` query just to check whether a next page exists.

For forward pagination, `hasPreviousPage` may require an `EXISTS` query to check if any record precedes the first item. Do not infer it solely from whether the client sent `after`; if the API uses best-effort semantics, document that clearly.

## 7. Backward pagination with last and before

Backward pagination lets clients fetch records preceding a cursor. When the public sort order is DESC, the query can flip to ASC to fetch records closest to the cursor:

~~~sql
SELECT id, title, created_at
FROM book
WHERE
    created_at > :cursorCreatedAt
    OR (
        created_at = :cursorCreatedAt
        AND id > :cursorId
    )
ORDER BY created_at ASC, id ASC
LIMIT :limit
~~~

If the client requests `last = 20`, the server fetches 21 rows in reverse direction, drops the extra row, reverses the remaining list back to the connection's DESC order, and builds edges and PageInfo. Never return items in ASC order merely because the internal query used ASC.

Backward pagination may need another `EXISTS` query to compute hasNextPage. Thoroughly test PageInfo flags for the first page, middle pages, last page, and empty datasets.

## 8. Validating pagination arguments

The server should validate arguments before calling the repository:

- `first` and `last` must be non-negative.
- Enforce a maximum cap, such as 100 edges per request.
- Disallow `first` together with `last` unless the API supports combining them.
- Disallow `after` and `before` together unless allowed by the contract.
- Cursor must decode cleanly and match an expected version.
- Cursor must contain all sort keys with valid types.
- Filters/sorts must be in the API's allowlist.

Example:

~~~java
private int validatePageSize(Integer requested) {
    int size = requested == null ? 20 : requested;

    if (size < 0) {
        throw new InvalidPaginationException("Page size must not be negative");
    }
    if (size > 100) {
        throw new InvalidPaginationException("Page size exceeds the limit");
    }
    return size;
}
~~~

You can allow `first = 0` for clients querying only PageInfo, but define clearly how hasNextPage and endCursor are computed. Some APIs prefer requiring page size > 0 for simplicity. What matters is a consistent, well-tested contract.

Malformed cursors should map to a clear request error, such as BAD_REQUEST, rather than letting Base64 or UUID parsing failures surface as INTERNAL_ERROR.

## 9. Building a cursor codec

A simple codec can encode version, timestamp, and ID. The example below uses a colon-delimited text payload whose components cannot contain the delimiter:

~~~java
public record BookCursor(Instant createdAt, UUID id) {
}

public class BookCursorCodec {

    private static final String VERSION = "v1";

    public String encode(BookCursor cursor) {
        String value = VERSION + ":"
            + cursor.createdAt().toEpochMilli() + ":"
            + cursor.id();

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public BookCursor decode(String encoded) {
        try {
            String value = new String(
                Base64.getUrlDecoder().decode(encoded),
                StandardCharsets.UTF_8);

            String[] parts = value.split(":", -1);
            if (parts.length != 3 || !VERSION.equals(parts[0])) {
                throw new InvalidPaginationException("Invalid cursor");
            }

            Instant createdAt =
                Instant.ofEpochMilli(Long.parseLong(parts[1]));
            UUID id = UUID.fromString(parts[2]);

            return new BookCursor(createdAt, id);
        }
        catch (IllegalArgumentException ex) {
            throw new InvalidPaginationException("Invalid cursor", ex);
        }
    }
}
~~~

This codec illustrates only the minimal format. Production systems must decide how to handle old versions, timestamp precision, anti-tampering signatures, and whether cursors stay valid when sort/filter inputs change.

Do not call `toString()` casually on sort keys if the format is unstable. Timestamps must preserve the precision used by the database for comparison; if the database stores microseconds while the cursor keeps only milliseconds, multiple rows can collapse onto the wrong boundary.

## 10. Building Connection and Edge in Java

You can use records as response models:

~~~java
public record BookEdge(String cursor, Book node) {
}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor) {
}

public record BookConnection(
        List<BookEdge> edges,
        PageInfo pageInfo,
        Long totalCount) {
}
~~~

The service converts the paginated list into edges:

~~~java
private BookConnection toConnection(
        List<Book> books,
        boolean hasNextPage,
        boolean hasPreviousPage) {

    List<BookEdge> edges = books.stream()
        .map(book -> new BookEdge(
            cursorCodec.encode(new BookCursor(
                book.createdAt(), book.id())),
            book))
        .toList();

    String startCursor = edges.isEmpty()
        ? null
        : edges.get(0).cursor();
    String endCursor = edges.isEmpty()
        ? null
        : edges.get(edges.size() - 1).cursor();

    PageInfo pageInfo = new PageInfo(
        hasNextPage,
        hasPreviousPage,
        startCursor,
        endCursor);

    return new BookConnection(edges, pageInfo, null);
}
~~~

For an empty connection, startCursor and endCursor should be null. Never fabricate a fake cursor for a page with no edges.

## 11. Resolvers in Spring for GraphQL

Spring for GraphQL binds arguments with `@Argument`. Keep resolvers thin and delegate validation, querying, and connection construction to the service:

~~~java
@Controller
public class BookQueryController {

    private final BookConnectionService connectionService;

    public BookQueryController(BookConnectionService connectionService) {
        this.connectionService = connectionService;
    }

    @QueryMapping
    public BookConnection books(
            @Argument Integer first,
            @Argument String after,
            @Argument BookFilter filter) {

        return connectionService.findBooks(first, after, filter);
    }
}
~~~

The example above shows forward pagination. If supporting backward pagination, add `last` and `before` and validate argument pairs according to your contract. Avoid placing raw SQL, cursor parsing, and PageInfo calculation directly in controllers.

## 12. Repository keyset queries

The repository must execute predicates based on the sort key. With Spring Data JPA, you can use a custom repository to control the query:

~~~java
public interface BookRepositoryCustom {

    List<Book> findAfter(
        UUID tenantId,
        BookStatus status,
        BookCursor cursor,
        int limit);
}
~~~

An implementation using JPQL or Criteria API needs to express the condition:

~~~sql
createdAt < :createdAt
OR (createdAt = :createdAt AND id < :id)
~~~

If the cursor is null, skip the cursor predicate and fetch from the beginning of the connection. The query must apply tenant and filter conditions in the same query:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      :hasCursor = false
      OR created_at < :createdAt
      OR (created_at = :createdAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

This is illustrative SQL; how optional predicates and limits are bound depends on the database and ORM. With JPA, you can use native queries, Criteria API, or a custom repository to build dynamic conditions.

Spring Data supports scrolling with `ScrollPosition`, `Window<T>`, and keyset-based scrolling in supported versions. If using that mechanism, verify that the repository method, sort, and property projections meet keyset requirements. Spring Data's `Window<T>` is a scrolling abstraction; the application still maps results into GraphQL Connection/Edge/PageInfo according to the public schema.

## 13. Indexes for keyset pagination

A query can use a keyset predicate and still be slow without a matching index. For queries filtering by tenant and status and ordering by created_at DESC, id DESC, an index can start with equality filter columns followed by the sort key:

~~~sql
CREATE INDEX idx_book_tenant_status_created_id
ON book (tenant_id, status, created_at DESC, id DESC);
~~~

Exact indexes depend on the database, filter selectivity, status cardinality, and real workload. Do not create indexes for every filter combination blindly; inspect execution plans and measure against production-like data.

- Equality filters generally precede sort keys in composite indexes.
- Cursor columns must appear in the index in exact sort order.
- If filters are optional, a single index may not be optimal for every query shape.
- Projections fetching only needed columns can reduce I/O.
- Sort direction and null ordering must match the predicate.

Use EXPLAIN or EXPLAIN ANALYZE in your database to verify the query actually uses the index and avoids scanning large datasets.

## 14. Filters, sorts, and cursors must stay consistent

A cursor is generated for a specific ordering. If a client takes a cursor from `status=PUBLISHED` and sends it to `status=DRAFT`, the boundary may no longer make sense for the new dataset.

Two ways to handle this:

1. Treat the cursor purely as a sort key and apply it to the new filter according to documented semantics.
2. Embed a filter-and-sort fingerprint in the cursor and reject cursors when the query scope changes.

Fingerprints should be computed from a canonical representation of supported filters and sorts. Never serialize an unordered Map and hash it directly if key order can vary.

Client-selected sort fields must belong to an allowlist. Never concatenate arbitrary column names from GraphQL arguments into SQL. Every sort option must define an appropriate predicate, tie-breaker, and index.

## 15. Authorization and tenant scope

A cursor is not a credential and grants no access rights. Users can send a cursor obtained from another request, so every page must enforce authorization for the current principal.

Example:

~~~java
public BookConnection findBooks(
        String username,
        Integer first,
        String after,
        BookFilter filter) {

    UUID tenantId = tenantAuthorization.requireCurrentTenant(username);
    int size = validatePageSize(first);
    BookCursor cursor = after == null ? null : cursorCodec.decode(after);

    List<Book> rows = repository.findAfter(
        tenantId, filter.status(), cursor, size + 1);

    return buildConnection(rows, size);
}
~~~

`tenantId` must be derived from the principal or verified via server-side membership checks. Never trust a tenant ID simply because it was decoded from a cursor or sent in a GraphQL argument.

If a cursor is signed, the signature only detects cursor tampering. It does not replace authorization, because a user could still replay a valid cursor in a context where they no longer have permission.

## 16. Data changing between pages

Cursor pagination reduces the impact of inserts/deletes before the cursor, but does not automatically create a snapshot.

Example sorting DESC by created_at:

- A new record is inserted at the top of the list after the client reads page one: the next page using the old cursor resumes from the previous boundary, so the new record usually does not shift already-read rows.
- A record behind the cursor is deleted: the next page simply omits that record.
- An already-read record updates its created_at and moves past the cursor: the client may see the record again.
- An unread record updates its sort key and moves ahead of the cursor: the client may miss it during the current traversal.

To minimize drift, prefer immutable sort keys such as createdAt paired with a unique ID. When exact snapshot traversal is required, cursors can embed a snapshot timestamp/version or queries can use a fixed watermark, such as reading only rows with created_at less than or equal to snapshotTime.

Snapshot semantics add complexity and may require maintaining versions or transaction snapshots across requests. Implement them only when business requirements demand them; do not assume cursors provide snapshot isolation on their own.

## 17. PageInfo and edge cases

PageInfo must be tested for these scenarios:

| Scenario | edges | hasNextPage | hasPreviousPage |
| --- | --- | --- | --- |
| No data | Empty | false | false |
| First page with following page | Has data | true | false |
| Middle page | Has data | true/false depending on remaining data | true |
| Last page | Has data | false | true |
| Cursor at end of dataset | Empty or empty page per contract | false | true if prior data exists |
| Page size equals 0 | Empty | Per existence query and contract | Per existence query and contract |

Do not set `hasNextPage = edges.size() == first` because matching the page size does not prove another record exists. Fetch `first + 1` or run an `EXISTS` query.

For `hasPreviousPage`, do not default to true merely because `after` was provided. When exact accuracy is required, check whether any record precedes the starting position under the same filter, tenant, and sort order.

## 18. Should totalCount be included in Connection?

totalCount is convenient for UIs displaying "1,234 results found", but counting can be expensive:

- Complex filters may require scanning many index entries.
- Joins and authorization predicates can make counts slower than page queries.
- Data changing between the count query and edges query means the two values do not reflect the same snapshot.

Options:

- Omit totalCount if the UI does not need it.
- Compute count separately and cache it briefly.
- Use an approximate count if the product accepts estimates.
- Provide counts only for well-indexed filter combinations.

Never run a count query just to check whether a next page exists; fetching n + 1 is usually cheaper.

## 19. Avoiding N+1 when resolving node fields

Cursor pagination only optimizes fetching the list of nodes. If each edge node has nested fields such as author, category, or reviews, resolvers can still trigger N+1 queries.

Example query:

~~~graphql
query {
    books(first: 20) {
        edges {
            node {
                id
                title
                author {
                    id
                    name
                }
            }
        }
    }
}
~~~

Use DataLoader or @BatchMapping for nested associations to batch keys. Batch loaders must enforce the same tenant/authorization scope and never share caches across principals.

Pagination queries should also fetch only the columns needed for the connection and cursor. When resolvers need nested data, let DataLoader handle them in batches rather than joining collections that multiply rows and break page boundaries.

## 20. Testing cursor pagination with GraphQlTester

Tests should execute real GraphQL documents to verify schema, resolvers, cursors, and PageInfo working together:

~~~java
@Test
void returnsNextPageAfterEndCursor() {
    var firstPage = graphQlTester.document("""
            query {
                books(first: 2) {
                    edges {
                        cursor
                        node {
                            id
                            title
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
            """)
        .execute();

    firstPage.errors().verify();
    firstPage.path("books.edges")
        .entityList(BookEdgeView.class)
        .hasSize(2);
    firstPage.path("books.pageInfo.hasNextPage")
        .entity(Boolean.class)
        .isEqualTo(true);

    String endCursor = firstPage.path("books.pageInfo.endCursor")
        .entity(String.class)
        .get();

    var secondPage = graphQlTester.document("""
            query NextBooks($after: String) {
                books(first: 2, after: $after) {
                    edges {
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                    }
                }
            }
            """)
        .variable("after", endCursor)
        .execute();

    secondPage.errors().verify();
    secondPage.path("books.edges")
        .entityList(BookEdgeIdView.class)
        .hasSize(2);
}
~~~

Fixtures should include at least three or four records in a known order to test the first page and the next page. Test DTOs BookEdgeView and BookEdgeIdView must match the response selection.

## 21. Essential test cases

Cover these cases:

1. First page without a cursor.
2. Next page using the previous page's endCursor.
3. Final page with hasNextPage = false.
4. Empty connection with null cursors.
5. Multiple records sharing the same sort timestamp without duplicates or gaps thanks to the tie-breaker.
6. Invalid Base64 cursors, wrong version, missing fields, or invalid UUIDs rejected as bad requests.
7. Negative or over-limit page sizes rejected.
8. Different filters have clear cursor semantics.
9. Tenant A cannot use a cursor to read Tenant B's data.
10. Backward pagination returns edges in the canonical public order.
11. Inserts/deletes between pages do not duplicate already-read records in supported scenarios.
12. Mutations of the sort key behave as defined.
13. Nested DataLoader fields do not cause N+1.
14. totalCount is accurate if exposed by the API.

Test keyset queries at the repository layer with records sharing timestamps. Test the GraphQL layer to verify the response contract. Integration tests against a real database should verify SQL dialect, sorting, indexes, and query plans when performance matters.

## 22. Common pitfalls

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Cursor only holds an offset | Performance and stability are no better than offset pagination | Encode the record's sort key |
| Sort lacks a unique tie-breaker | Duplicate or skipped rows when sort keys tie | Add ID or unique key to sort |
| Predicate mismatches ORDER BY | Next page has wrong order or drops rows | Design predicates per sort direction |
| Not fetching n + 1 | hasNextPage is inaccurate | Fetch one extra row or use EXISTS |
| Always running COUNT(*) | Adds cost to every page | Provide totalCount only when needed |
| Unversioned cursors | Cannot evolve format safely | Add version and handle legacy cursors |
| Treating Base64 as security | Clients can decode/modify cursors | Use HMAC if anti-tampering is needed |
| Trusting cursor for authorization | Replaying a cursor can cross scopes | Enforce authorization on every request |
| Changing filters without cursor policy | Unpredictable page boundaries | Bind cursors to filter/sort or publish semantics |
| Missing matching index | Keyset query remains slow | Inspect execution plan and create composite index |
| Nested resolvers querying per node | N+1 still occurs | Use DataLoader or @BatchMapping |
| No page size limit | Clients can request huge result sets | Validate and cap page size |

## 23. Cursor pagination design principles

Design schemas with Connection/Edge/PageInfo so clients have a consistent contract. Cursors must be opaque, versioned, and contain every sort key of a deterministic ordering; always include a unique tie-breaker. For forward pagination, use keyset predicates and fetch `first + 1` to determine the next page. For backward pagination, query in reverse order and flip results back to connection order.

Apply filters and authorization scope in the same database query. Cap page size, validate cursors, never treat cursors as credentials, and sign payloads when anti-tampering is required. Create indexes matching filters and sort order, inspect execution plans, avoid unnecessary counts, and use DataLoader for nested fields.

Test the first page, next page, last page, invalid cursors, tied sort keys, changing data, backward pagination, tenant isolation, and N+1. Cursor pagination makes large-dataset traversal much more stable when paired with keyset queries and proper sorting/indexing; a cursor string in the GraphQL schema provides no performance gain if the repository still uses offsets underneath.

## References

- [Relay Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data JPA — Query Methods and Scrolling](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
