# Queries and Pagination in Spring for GraphQL

GraphQL does not mandate a built-in pagination mechanism. An API must design arguments and return types so clients can fetch data in chunks, know whether more data remains, and resume from the previous position. In Spring for GraphQL, `@QueryMapping` receives arguments via `@Argument`, and the resolver forwards them to a service or repository to execute a bounded query.

Two common strategies are **offset pagination** (paging by page number and page size) and **cursor pagination** (paging by a cursor). Offset pagination is easy to implement and fits numbered-page UIs. Cursor pagination suits large lists, frequently changing data, or continuous load-more flows. Choose a strategy based on how clients consume data and the system's query characteristics.

## 1. Why Do Queries Need Pagination?

A query returning all data can look simple at first:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

When the number of books grows to hundreds of thousands, having the client load the entire list causes several problems:

- Large responses increase bandwidth usage and transfer time.
- The server must read, map, and serialize many records even though the client only displays a subset.
- Resolvers can put heavy pressure on the database and memory.
- The UI struggles to implement load-more, infinite scroll, or page switching.

Pagination limits the number of items returned in a single execution. Clients can fetch the first page, then send subsequent requests based on a page number or cursor.

Pagination must also be combined with query depth limits, query complexity limits, filtering, and authorization. Capping `first` or `size` only controls the item count of one field; it does not automatically cap the total cost of the entire GraphQL operation.

## 2. Designing Offset Pagination in SDL

Offset pagination typically uses two arguments:

- `page`: page number, usually starting at `0`.
- `size`: maximum number of items in a page.

You can add `sort` so clients select from server-allowed sort orders.

~~~graphql
enum BookSort {
    TITLE_ASC
    TITLE_DESC
    CREATED_AT_DESC
}

type Query {
    books(
        page: Int! = 0
        size: Int! = 20
        sort: BookSort! = CREATED_AT_DESC
    ): BookPage!
}

type BookPage {
    content: [Book!]!
    page: Int!
    size: Int!
    totalElements: Int!
    totalPages: Int!
    hasNext: Boolean!
}

type Book {
    id: ID!
    title: String!
    createdAt: String!
}
~~~

`BookPage` is a wrapper type defined by the API. GraphQL clients can select both the book data and pagination metadata. Do not return `Page<Book>` directly as an API contract expecting GraphQL to infer the schema; map the Spring Data result to a DTO or record with explicitly declared fields.

The `page`, `size`, and `sort` arguments have default values so clients may omit them. When omitted, GraphQL uses `0`, `20`, and `CREATED_AT_DESC`. If a client passes `null` for a Non-Null argument, the request is invalid.

`totalElements` in the example uses GraphQL `Int`, which is a signed 32-bit integer. If the system can exceed this limit, do not cast `long` to `int`; use a large-integer custom scalar or design different metadata suited to the API contract.

## 3. Implementing Offset Pagination with Spring Data

Spring for GraphQL does not dictate how databases are queried for every API. The resolver receives arguments, constructs a `Pageable`, and calls the service. Spring Data can use `Pageable` to generate queries with `LIMIT` and `OFFSET` for repositories supporting pagination.

### 3.1. Defining Models and Return Types

Example using Java records for API data:

~~~java
public record Book(
        String id,
        String title,
        String createdAt
) {}
~~~

~~~java
import java.util.List;

public record BookPage(
        List<Book> content,
        int page,
        int size,
        int totalElements,
        int totalPages,
        boolean hasNext
) {}
~~~

Java enum matching the SDL:

~~~java
public enum BookSort {
    TITLE_ASC,
    TITLE_DESC,
    CREATED_AT_DESC
}
~~~

In the SDL example above, `createdAt` is declared as `String`. Real applications should consider a custom `DateTime` scalar to represent timestamp formats clearly; here `String` keeps the focus on the pagination flow.

### 3.2. Service Accepting Pageable

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface BookService {
    Page<Book> findAll(Pageable pageable);
}
~~~

Service implemented with the corresponding Spring Data repository:

~~~java
public class JpaBookService implements BookService {

    private final BookRepository bookRepository;

    public JpaBookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Override
    public Page<Book> findAll(Pageable pageable) {
        return bookRepository.findAll(pageable)
                .map(entity -> new Book(
                        entity.getId().toString(),
                        entity.getTitle(),
                        entity.getCreatedAt().toString()
                ));
    }
}
~~~

`BookRepository` can be declared as follows when using Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<BookEntity, Long> {}
~~~

`BookEntity` is the application's persistence entity. Mapping entities to DTOs keeps the GraphQL API decoupled from the persistence structure.

### 3.3. Resolver Using @QueryMapping and @Argument

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private static final int MAX_PAGE_SIZE = 100;

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookPage books(
            @Argument("page") int page,
            @Argument("size") int size,
            @Argument("sort") BookSort sort
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        Pageable pageable = PageRequest.of(page, size, toSort(sort));
        Page<Book> result = bookService.findAll(pageable);

        return new BookPage(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                Math.toIntExact(result.getTotalElements()),
                result.getTotalPages(),
                result.hasNext()
        );
    }

    private Sort toSort(BookSort sort) {
        return switch (sort) {
            case TITLE_ASC -> Sort.by(Sort.Direction.ASC, "title")
                    .and(Sort.by(Sort.Direction.ASC, "id"));
            case TITLE_DESC -> Sort.by(Sort.Direction.DESC, "title")
                    .and(Sort.by(Sort.Direction.ASC, "id"));
            case CREATED_AT_DESC -> Sort.by(Sort.Direction.DESC, "createdAt")
                    .and(Sort.by(Sort.Direction.DESC, "id"));
        };
    }
}
~~~

Key points:

- `@QueryMapping` maps the method to the `Query.books` field.
- `@Argument` binds GraphQL arguments to Java parameters by their specified names.
- `PageRequest.of(page, size, sort)` builds the pagination request for Spring Data.
- `MAX_PAGE_SIZE` caps the amount of data a client can request in one call.
- `toSort` uses an enum allowlist so clients can only choose predefined sort orders.
- Adding `id` as a tie-breaker to `createdAt` keeps result ordering deterministic when multiple records share the same timestamp.

`Math.toIntExact` throws an exception if the total count exceeds Java `int` bounds. This illustrative example uses `Int` in the SDL so data is expected to fit within those bounds; for large systems, change the contract to an appropriate scalar instead of silently truncating numbers.

## 4. Calling Paginated Queries from Clients

Clients can send the query with variables:

~~~graphql
query Books($page: Int!, $size: Int!, $sort: BookSort!) {
    books(page: $page, size: $size, sort: $sort) {
        content {
            id
            title
        }
        page
        size
        totalElements
        totalPages
        hasNext
    }
}
~~~

Variables for the first page:

~~~json
{
    "page": 0,
    "size": 20,
    "sort": "CREATED_AT_DESC"
}
~~~

Variables for the next page:

~~~json
{
    "page": 1,
    "size": 20,
    "sort": "CREATED_AT_DESC"
}
~~~

Clients can use `hasNext` to decide whether to show a "Load more" button. `totalPages` and `totalElements` fit UIs that display page numbers or total result counts.

Because the schema declares default values, clients can also call it more concisely:

~~~graphql
query {
    books {
        content {
            id
            title
        }
        hasNext
    }
}
~~~

## 5. Page, Slice, and Limiting Count Queries

Spring Data provides several different abstractions for pagination:

| Type | Data Provided | Typical Cost |
| --- | --- | --- |
| `Page<T>` | Content, page metadata, and total elements/pages | Often requires an extra `COUNT` query to compute totals |
| `Slice<T>` | Content and whether a next page exists | Can avoid counting total elements; typically reads one extra element to determine `hasNext` |
| `Window<T>` | A window of results using Spring Data's scrolling mechanism | Can support offset or keyset scrolling depending on repository and version |

If the UI only needs a "Load more" button, `Slice<T>` may suffice and avoids the cost of counting every record. If total pages are required, `Page<T>` is more convenient, though count queries can be expensive with complex filters or large tables.

Do not expose raw persistence abstractions directly in the GraphQL schema. Convert them into DTOs with client-oriented fields, such as `BookSlice { content, hasNext }` or `BookPage { content, totalElements, totalPages }`.

## 6. Limitations of Offset Pagination

Offset pagination is easy to understand, but it has several limitations:

**Deep pages can be slow.** A query like `OFFSET 500000 LIMIT 20` may force the database to scan past many rows before returning the 20 requested rows, depending on the execution plan and indexes.

**Changing data can cause page drift.** If a new record is inserted at the top of the list after the client loads page 0, requesting page 1 may repeat an already-seen item or skip another. Deleting records can also shift item positions.

**Ordering must be deterministic.** Sorting only by a column with duplicate values allows rows to swap positions across requests. Add a unique key as a secondary criterion, such as `createdAt DESC, id DESC`.

Offset pagination fits when data does not change too frequently, pages are not too deep, and the UI needs to jump directly to arbitrary page numbers. For large lists or continuously updated data, cursor/keyset pagination is usually a better fit.

## 7. Designing Cursor Pagination with GraphQL Connections

Cursor pagination uses a cursor value representing the last read position. The next request sends that cursor to retrieve items following it in the defined sort order.

A common connection schema by convention:

~~~graphql
type Query {
    books(first: Int! = 20, after: String): BookConnection!
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

type Book {
    id: ID!
    title: String!
    createdAt: String!
}
~~~

Components:

- `first`: maximum number of items to retrieve.
- `after`: cursor of the last edge the client received.
- `edges`: list of edges, each containing a `cursor` and a `node`.
- `pageInfo`: metadata telling the client whether next or previous pages exist.
- `totalCount`: total number of results if supplied by the server; this field may be omitted or return null if counting is too expensive.

GraphQL does not require using the names `Connection`, `Edge`, or `PageInfo`. This is a widespread convention from the Relay Connection Specification, useful when an API needs a consistent pagination model.

`totalCount` in the example also uses GraphQL `Int`, so it has a 32-bit limit. For large datasets, use an appropriate custom scalar or omit the total count if clients do not need it.

## 8. Cursors Must Be Stable and Offset-Independent

Cursors typically encode the values used to locate a position in the sort order. For example, for a book list sorted by `createdAt DESC, id DESC`, a cursor might contain:

~~~json
{
    "createdAt": "2026-11-20T08:30:00Z",
    "id": "book-101"
}
~~~

To prevent clients from coupling to internal structure, the server typically encodes this data into an opaque string, such as URL-safe Base64. Base64 is only encoding, not cryptographic encryption, and does not stop clients from tampering with cursors. If a cursor contains sensitive data or must be tamper-resistant, use a signed token or appropriate verification mechanism.

A good cursor should:

1. Represent an exact position in the sort order.
2. Use stable sort keys, typically with a unique ID as a tie-breaker.
3. Be validated upon decoding; malformed or incompatible cursors must be explicitly rejected.
4. Be bound to the corresponding filter and sort if changing those criteria would invalidate the cursor's meaning.
5. Never replace authorization; every subsequent request must still check data access permissions.

Cursor/keyset pagination reduces the impact of insertions at the head of a list compared to offset pagination, but it does not automatically create a consistent snapshot across multiple requests. If the value of a sort column changes between fetches, a record can still move across the cursor boundary. When iterating an immutable dataset is required, use immutable sort keys or design a dedicated snapshot/version.

Do not build a cursor merely from a page number and fall back to offset on the server if your goal is keyset pagination. That simply wraps offset in a string while retaining all of offset's drawbacks.

## 9. Querying Keyset Pagination in the Repository Layer

With ordering `createdAt DESC, id DESC`, the server can find records after the cursor using a key-pair comparison predicate. SQL pseudocode:

~~~sql
SELECT id, title, created_at
FROM book
WHERE created_at < :cursorCreatedAt
   OR (created_at = :cursorCreatedAt AND id < :cursorId)
ORDER BY created_at DESC, id DESC
LIMIT :firstPlusOne
~~~

When there is no cursor yet, omit the cursor `WHERE` condition and read from the start of the list. The server fetches `first + 1` rows:

- If the returned row count does not exceed `first`, there is no next page.
- If `first + 1` rows are returned, discard the extra element and set `hasNextPage = true`.
- Each edge's cursor is built from the sort keys of its corresponding node.

The query example above assumes both `created_at` and `id` are ordered descending. For ascending sort, flip the comparison operators. For multi-column sorts, the keyset condition must accurately reflect the lexicographical order of all sort columns plus the tie-breaker.

Columns used as cursor keys should have deterministic values. If `NULL` is allowed in a sort key, define explicit null ordering and apply that same rule in both SQL and the cursor codec.

Database indexes should support the columns in the predicate and sort order, such as a composite index `(created_at DESC, id DESC)` depending on the database. Inspect actual execution plans; switching to cursors without an appropriate index will not automatically improve performance.

## 10. Cursor Pagination Resolver in Spring for GraphQL

The resolver receives `first` and `after`, validates limits, decodes the cursor, and calls the service:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookConnectionController {

    private static final int DEFAULT_FIRST = 20;
    private static final int MAX_FIRST = 100;

    private final BookConnectionService bookService;
    private final BookCursorCodec cursorCodec;

    public BookConnectionController(
            BookConnectionService bookService,
            BookCursorCodec cursorCodec
    ) {
        this.bookService = bookService;
        this.cursorCodec = cursorCodec;
    }

    @QueryMapping
    public BookConnection books(
            @Argument("first") Integer first,
            @Argument("after") String after
    ) {
        int limit = first != null ? first : DEFAULT_FIRST;
        if (limit < 1 || limit > MAX_FIRST) {
            throw new IllegalArgumentException(
                    "first must be between 1 and " + MAX_FIRST
            );
        }

        BookCursor cursor = after != null
                ? cursorCodec.decode(after)
                : null;

        return bookService.findAfter(cursor, limit);
    }
}
~~~

`BookConnectionService`, `BookCursorCodec`, and `BookCursor` are application-defined types. The service is responsible for keyset querying and constructing `edges` and `pageInfo`; the codec is responsible for encoding/decoding cursors and validating their structure.

The resolver keeps a coordinating role: binding arguments, enforcing limits, and forwarding the validated cursor to the service. Do not put SQL or cursor encoding logic directly in the controller.

## 11. Querying Cursor Pagination from Clients

First request:

~~~graphql
query FirstBooks {
    books(first: 20) {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            hasNextPage
            hasPreviousPage
            startCursor
            endCursor
        }
    }
}
~~~

After receiving the response, the client takes `endCursor` and passes it in `after` to load the next page:

~~~graphql
query NextBooks($after: String!) {
    books(first: 20, after: $after) {
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

Variables for the next request:

~~~json
{
    "after": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwVDA4OjMwOjAwWiIsImlkIjoiYm9vay0xMDEifQ"
}
~~~

The string above is only an illustrative example of an opaque cursor. Clients should treat cursors as server-issued tokens and never decode or forge cursors themselves. When changing filters or sort orders, clients should typically restart from the first page because the old cursor may no longer apply.

## 12. Choosing Page, Slice, or Cursor/Keyset?

| Criterion | Offset with Page | Offset with Slice | Cursor/Keyset |
| --- | --- | --- | --- |
| Jumping to an arbitrary page | Convenient | Convenient | Not a primary goal |
| Knowing total element count | Yes | Not by default | Not by default; count can be added |
| Load more / infinite scroll | Usable | Suitable | Very suitable |
| Very deep pages | Can be slow | Can be slow | Usually faster with proper indexes |
| Data changing between calls | Can duplicate or skip items | Can duplicate or skip items | More stable when cursor and ordering are designed properly |
| Implementation complexity | Low | Low | Higher: requires cursor encoding/decoding and validation |

Choose `Page` when the UI needs page numbers and total result counts. Choose `Slice` when it only needs to know whether a next page exists. Choose cursor/keyset when clients load sequentially from the last position, data is large, or deep offsets become a performance bottleneck.

## 13. Combining Filtering, Sorting, and Pagination

Filters must be applied before pagination. Example query filtering books by status:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input BookFilter {
    keyword: String
    status: BookStatus
}

type Query {
    books(
        filter: BookFilter
        page: Int! = 0
        size: Int! = 20
    ): BookPage!
}
~~~

The service should execute in logical order:

1. Determine the data scope the user is permitted to view.
2. Apply filters by keyword, status, or business criteria.
3. Apply the allowlisted sort order.
4. Apply page/size or cursor to limit results.
5. Build pagination metadata matching the chosen strategy.

With cursor pagination, the cursor must be compatible with the filter and sort. If a client sends a cursor created for `CREATED_AT_DESC` while a subsequent request switches to `TITLE_ASC`, the server should reject the incompatible cursor or require the client to restart.

Never accept arbitrary SQL column names or entity property names directly from clients as sort keys. Use enums or allowlists to avoid exposing internal fields and prevent unintended queries.

## 14. Testing Pagination with GraphQlTester

You can use `@GraphQlTest` to test resolvers and schemas without starting the full application. Example testing offset pagination:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

@GraphQlTest(BookQueryController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsRequestedPage() {
        List<Book> books = List.of(
                new Book("book-1", "GraphQL basics", "2026-01-02T00:00:00Z"),
                new Book("book-2", "Spring GraphQL", "2026-01-01T00:00:00Z")
        );
        Pageable pageable = PageRequest.of(
                1, 2,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );
        Page<Book> page = new PageImpl<>(books, pageable, 5);
        given(bookService.findAll(any(Pageable.class))).willReturn(page);

        GraphQlTester.Response response = graphQlTester.document("""
                query Books($page: Int!, $size: Int!, $sort: BookSort!) {
                    books(page: $page, size: $size, sort: $sort) {
                        content { id title }
                        page
                        size
                        totalElements
                        totalPages
                        hasNext
                    }
                }
                """)
            .variable("page", 1)
            .variable("size", 2)
            .variable("sort", "CREATED_AT_DESC")
            .execute();

        response.errors().verify();
        response.path("books.content").entityList(Book.class).hasSize(2);
        response.path("books.page").entity(Integer.class).isEqualTo(1);
        response.path("books.totalElements").entity(Integer.class).isEqualTo(5);
        response.path("books.hasNext").entity(Boolean.class).isEqualTo(true);
    }
}
~~~

`BookService` is mocked with `@MockitoBean`; the returned data simulates the second page out of five total items. Assertions read both content and metadata from the same GraphQL response.

Cases to test:

1. First page returns data and last page has `hasNext = false`.
2. Page beyond available pages returns an empty list or defined behavior.
3. Negative `page`, `size` equal to 0, or `size` exceeding the maximum are rejected.
4. Sort only accepts values in the allowlist enum.
5. Filters are applied before pagination.
6. Valid cursors return the expected next items; malformed or mismatched filter/sort cursors are rejected.
7. Two consecutive cursor requests do not duplicate items when a new record is inserted at the head of the list.
8. Users cannot use pagination to read data outside their permitted scope.

## 15. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Client requests an overly large page size | Resolver does not cap `size` or `first` | Enforce a server-side maximum and return a clear input error |
| Pages contain duplicate or skipped items | Unstable sort or data changes between offset requests | Add a unique tie-breaker or use cursor/keyset |
| Deep pages respond slowly | Large offset and missing suitable index | Use keyset/cursor and inspect execution plans |
| `totalElements` is expensive | `Page` requires a count query over a large dataset | Use `Slice` or omit `totalCount` if the UI does not need it |
| Cursor becomes invalid | Cursor was created under a different sort/filter or old format | Validate cursors, include a version and filter/sort fingerprint |
| Client tampers with cursor | Base64 encoding only, without integrity checks | Use a signature or authenticated token if tamper resistance is needed |
| GraphQL errors on sort | Client passed an enum value not in the schema | Check enum definitions and handle supported values |
| Wrong response metadata | Mismapped page, size, total, or hasNext | Write tests for first, middle, and last pages |

## 16. Security and Cost Optimization for Pagination

Pagination does not replace authorization. Every subsequent page request must re-apply the data scope the user is permitted to view. Never trust a cursor as proof that the user has permission to read a record; a cursor only represents a position.

Enforce page size limits on the server even when the schema defines defaults. Clients can still send the maximum value allowed by the schema, so resolvers/services must check hard limits. Also cap query depth, complexity, and the number of related fields in an operation; even a small page where every item pulls in multiple relationships can create very expensive queries.

When pagination is paired with `@SchemaMapping` or `@BatchMapping`, check for N+1 on child fields. Limiting the number of `Book` items does not automatically cap generated queries if each `Book` fetches `author`, `reviews`, or `publisher` individually. DataLoader and batching group those related data fetches together.

## 17. Workflow for Implementing Query Pagination

When adding pagination to a GraphQL query:

1. Determine whether the UI needs page jumping, total counts, or only load-more.
2. Choose offset `Page`/`Slice` or cursor/keyset based on data scale and mutation patterns.
3. Design the SDL with clear arguments, default values, and wrapper types.
4. Use `@QueryMapping` and `@Argument` to bind inputs; validate page size and sort on the server.
5. Delegate querying to the service/repository, applying authorization and filtering before pagination.
6. For offset, use deterministic ordering and evaluate count/offset costs. For cursors, build opaque cursors from all sort keys with a unique tie-breaker.
7. Test first page, last page, invalid inputs, changing data, and access permissions with `GraphQlTester`.
8. Monitor query timing, rows read, count queries, and child field resolvers for further optimization.

Pagination is part of the GraphQL contract. Good design enables clients to fetch data as needed, keeps server load under control, and maintains stable result ordering as data grows.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Relay — Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
