# Pagination in Spring for GraphQL

Pagination allows a GraphQL API to return data in chunks instead of loading an entire collection in one request. With Spring for GraphQL, resolvers receive pagination parameters from GraphQL arguments, convert them into a `Pageable` or cursor, and call a service/repository to fetch only the required slice of data.

GraphQL does not mandate a single pagination standard. Two common approaches are **offset pagination** with `page`/`size` and **cursor pagination** with `first`/`after`. Offset pagination is easy to implement, supports jumping to an arbitrary page, and often fits admin screens. Cursor/keyset pagination is better suited for large collections, frequently changing data, or infinite-scroll feeds.

## 1. Why is pagination needed?

Suppose an API has a query that returns all books:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

When the number of books grows to hundreds of thousands, a single request can cause:

- Database queries reading too many rows.
- Huge JSON responses consuming bandwidth.
- High serialization and deserialization time.
- Increased heap usage and garbage collection pressure.
- Many child fields resolved, increasing the risk of N+1 issues.
- Requests holding connections and server resources for longer.

Pagination limits the number of records returned per execution. However, simply adding `first` or `size` to the SDL is not enough: resolvers and repositories must enforce the limit directly at the database level. Never load the entire dataset into Java and call `subList` to slice a page.

## 2. Choosing a pagination strategy

| Strategy | Common GraphQL arguments | Advantages | Limitations |
| --- | --- | --- | --- |
| Offset/page-based | `page`, `size`, `sort` | Easy to understand, supports jumping to any page | Deep pages can be slow; changing data can cause duplicate or skipped records |
| Cursor/keyset | `first`, `after` or `last`, `before` | Efficient on large datasets; resumes from a stable position | Cannot jump directly to an arbitrary page; requires stable cursors and sort order |
| Relay connection | `first`, `after`, `last`, `before` | Standardized response with `edges`, `cursor`, `pageInfo` | Requires explicit connection and cursor logic implementation |

Relay connection is a popular response shape for cursor pagination. It is not automatically generated simply by using Spring for GraphQL; the schema, resolvers, and cursor logic are still defined by the application.

## 3. Offset pagination with page and size

Offset pagination usually fits when the UI needs page numbers, total element counts, or lets users jump to a specific page.

Example schema:

~~~graphql
enum BookSortField {
    TITLE
    CREATED_AT
}

enum SortDirection {
    ASC
    DESC
}

type Query {
    books(
        page: Int = 0
        size: Int = 20
        sortBy: BookSortField = CREATED_AT
        direction: SortDirection = DESC
    ): BookPage!
}

type BookPage {
    items: [Book!]!
    page: Int!
    size: Int!
    totalElements: Int!
    totalPages: Int!
    hasNext: Boolean!
    hasPrevious: Boolean!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

GraphQL page indices commonly start at `0`, matching Spring Data `PageRequest`. If an API prefers 1-based page numbering, convert consistently in the resolver and document it clearly in the schema.

In the examples below, `Book` is a JPA entity with `Long id`, `String title`, `Long authorId`, `String tenantId`, and `Instant createdAt`. The GraphQL `author` field is resolved from `authorId` by a resolver/DataLoader; `tenantId`, `authorId`, and `createdAt` do not necessarily have to be exposed to clients.

~~~java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "book")
public class Book {

    @Id
    private Long id;
    private String title;
    private Long authorId;
    private String tenantId;
    private Instant createdAt;

    protected Book() {}

    public Book(Long id, String title, Long authorId,
            String tenantId, Instant createdAt) {
        this.id = id;
        this.title = title;
        this.authorId = authorId;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Long getAuthorId() { return authorId; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

## 4. Converting GraphQL arguments into Pageable

Spring Data provides `Pageable`, `PageRequest`, `Sort`, `Page`, and `Slice`. A resolver can construct a `Pageable` from arguments and pass it down to the service.

Java enums matching the SDL enums:

~~~java
public enum BookSortField {
    TITLE,
    CREATED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Record representing the response:

~~~java
import java.util.List;

public record BookPage(
        List<Book> items,
        int page,
        int size,
        int totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious
) {}
~~~

Repository and service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    Page<Book> findByTenantId(String tenantId, Pageable pageable);
}
~~~

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Page<Book> findVisibleBooks(String tenantId, Pageable pageable) {
        return repository.findByTenantId(tenantId, pageable);
    }
}
~~~

`tenantId` here comes from an abstraction that reads only the authenticated principal's tenant:

~~~java
public interface CurrentTenantProvider {
    String currentTenantId();
}
~~~

The `CurrentTenantProvider` implementation can read the tenant from the Spring Security principal or authenticated context. The tenant condition is applied directly in the repository query before the database paginates. In non-multi-tenant applications, omit this parameter and apply the corresponding domain filters.

Controller:

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

    private final BookService bookService;
    private final CurrentTenantProvider tenantProvider;

    public BookQueryController(BookService bookService,
            CurrentTenantProvider tenantProvider) {
        this.bookService = bookService;
        this.tenantProvider = tenantProvider;
    }

    @QueryMapping
    public BookPage books(
            @Argument Integer page,
            @Argument Integer size,
            @Argument BookSortField sortBy,
            @Argument SortDirection direction
    ) {
        int pageNumber = page == null ? 0 : page;
        int pageSize = size == null ? 20 : size;

        if (pageNumber < 0) {
            throw new InvalidPaginationException("page must be zero or greater");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new InvalidPaginationException("size must be between 1 and 100");
        }

        BookSortField field = sortBy == null ? BookSortField.CREATED_AT : sortBy;
        SortDirection order = direction == null ? SortDirection.DESC : direction;

        String property = switch (field) {
            case TITLE -> "title";
            case CREATED_AT -> "createdAt";
        };
        Sort.Direction sortDirection = order == SortDirection.ASC
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        Sort sort = Sort.by(sortDirection, property)
                .and(Sort.by(sortDirection, "id"));
        Pageable pageable = PageRequest.of(pageNumber, pageSize, sort);

        Page<Book> result = bookService.findVisibleBooks(
                tenantProvider.currentTenantId(), pageable);

        return new BookPage(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                Math.toIntExact(result.getTotalElements()),
                result.getTotalPages(),
                result.hasNext(),
                result.hasPrevious()
        );
    }
}
~~~

`CurrentTenantProvider` is an application abstraction to obtain the tenant from the authenticated principal. The controller does not accept a tenant ID from GraphQL arguments, so clients cannot switch tenants by editing the query.

Invalid pagination inputs should be mapped to a client-facing GraphQL error such as `BAD_REQUEST`, instead of letting an `IllegalArgumentException` surface as an internal error. Below is a shared exception and handler for page/size and cursors.

~~~java
public class InvalidPaginationException extends RuntimeException {
    public InvalidPaginationException(String message) {
        super(message);
    }

    public InvalidPaginationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class PaginationExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidPagination(
            InvalidPaginationException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message(exception.getMessage())
                .extensions(Map.of("code", "INVALID_PAGINATION"))
                .build();
    }
}
~~~

## 5. Why cap page size and allow-list sort fields?

Do not let clients arbitrarily request `size = 1000000`. Oversized pages produce heavy queries, huge responses, and high memory consumption. Always enforce a server-side maximum even when the SDL provides a default.

Do not pass a client-supplied string directly into `Sort.by(...)`:

~~~java
// Avoid accepting raw property names from the client.
Sort sort = Sort.by(clientProvidedSortField);
~~~

Instead, use a GraphQL enum or allow-list and map it to fixed Java properties. This prevents leaking internal fields, prevents sorting by expensive relationships, and makes supported options explicit in the schema.

Sort order must be deterministic. If multiple books share the same `createdAt`, add a unique tie-breaker such as `id`. Otherwise, two requests for adjacent pages may receive duplicate or missing records if the database returns tied rows in a different order.

## 6. How do Page and Slice differ?

Spring Data provides two commonly used abstractions:

| Type | Provided information | Typical cost |
| --- | --- | --- |
| `Page<T>` | Content, page metadata, total elements, total pages | Usually requires an extra count query to know total elements |
| `Slice<T>` | Content, hasNext, hasPrevious | Can simply fetch one extra element to determine if a next page exists |

If the UI needs to display "page 2 of 50" or total result count, `Page<T>` fits. If the UI only has a "Load more" button, `Slice<T>` is usually cheaper because it avoids counting all matching rows.

Count queries can be expensive on large tables, complex joins, or multi-condition filters. Do not expose `totalElements` merely because Spring Data `Page` provides that property; consider whether the client actually needs the total count.

## 7. Be careful with GraphQL Int and totalElements

GraphQL's built-in `Int` scalar is a signed 32-bit integer. Spring Data's `Page.getTotalElements()` returns `long`. `Math.toIntExact(...)` in the example throws an exception if the count exceeds GraphQL `Int` range.

If counts can exceed that limit, choose one of these approaches:

- Register a custom `Long`/`BigInt` scalar and use it consistently on the client.
- Return the total count as a `String` if the API contract accepts that representation.
- Omit `totalElements` and return only `hasNext` or `pageInfo`.

Cursor connections typically omit total counts because counting can be expensive and is unnecessary to load the next page.

## 8. Offset pagination degrades on deep pages

Offset queries are commonly executed by databases with `OFFSET n LIMIT m` semantics. At large page indices, the database may still have to scan or skip many rows before returning the requested slice.

Example:

~~~sql
SELECT id, title, created_at
FROM book
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
~~~

Deep page queries can take far longer than the first page. Moreover, when records are inserted or deleted between requests, offsets can shift positions: clients may see a record twice or skip one.

Offset pagination remains reasonable for moderate collections, infrequently changing data, and UIs needing page-number jumps. For feeds, audit logs, or large collections, consider cursor/keyset pagination.

## 9. Cursor pagination and Relay connections

Cursor pagination locates the next page relative to the last received record instead of counting records to skip. A Relay connection typically looks like:

~~~graphql
extend type Query {
    bookConnection(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
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
~~~

`edges` contains each record paired with its cursor. `pageInfo` indicates whether previous/next pages exist and provides the start/end cursors of the current page. The client sends the previous response's `endCursor` as `after` in the next request.

Example query:

~~~graphql
query FirstBooks {
    bookConnection(first: 20) {
        edges {
            cursor
            node { id title }
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

Next page:

~~~graphql
query NextBooks($after: String!) {
    bookConnection(first: 20, after: $after) {
        edges {
            cursor
            node { id title }
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

## 10. Designing a stable cursor

A cursor must represent a position in the sort order. Using `id` alone is sufficient only when the collection is sorted uniquely by ID. If sorting by `createdAt`, the cursor needs both `createdAt` and the unique tie-breaker `id`.

Model:

~~~java
import java.time.Instant;

public record BookCursor(Instant createdAt, Long id) {}
~~~

Simple codec using URL-safe Base64:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;

public class BookCursorCodec {

    public String encode(Book book) {
        String value = book.getCreatedAt() + "|" + book.getId();
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public BookCursor decode(String cursor) {
        try {
            String value = new String(
                    Base64.getUrlDecoder().decode(cursor),
                    StandardCharsets.UTF_8
            );
            int separator = value.indexOf('|');
            if (separator <= 0 || separator == value.length() - 1) {
                throw new InvalidPaginationException("after cursor is invalid");
            }
            Instant createdAt = Instant.parse(value.substring(0, separator));
            Long id = Long.valueOf(value.substring(separator + 1));
            return new BookCursor(createdAt, id);
        }
        catch (RuntimeException exception) {
            if (exception instanceof InvalidPaginationException invalid) {
                throw invalid;
            }
            throw new InvalidPaginationException("after cursor is invalid", exception);
        }
    }
}
~~~

Base64 only formats the cursor as an opaque string; it does not encrypt or protect integrity. Clients can decode and modify its contents. If cursors must resist tampering, sign payloads with HMAC or use server-protected tokens. Even with signed cursors, authorization and tenant filters must still be enforced in the database query.

Cursors should be tied to the sort algorithm version and filter scope. If a client changes filters or sort order between pages, an old cursor may no longer represent the same ordering. You can embed a filter/sort fingerprint in the payload and reject mismatched cursors.

The example service below fixes the order to `createdAt DESC, id DESC`. If the API lets clients choose another sort order, build matching keyset predicates and cursor payloads for each sort mode; a cursor holding only `createdAt` and `id` cannot be used for a different ordering.

## 11. Keyset queries with a tie-breaker

Suppose pages are sorted descending by `createdAt`, then descending by `id`. The next records must satisfy:

~~~sql
WHERE tenant_id = :tenantId
  AND (
       created_at < :createdAt
       OR (created_at = :createdAt AND id < :id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

The tuple condition ensures records with identical timestamps are still ordered distinctly by ID. For ascending sorts, flip comparison operators and sort direction accordingly. When sorting by multiple columns, the cursor must carry enough values to reproduce the total ordering.

Indexes should support both the filter and the keyset ordering. For the query above, an index might look like:

~~~sql
CREATE INDEX idx_book_tenant_created_id
    ON book (tenant_id, created_at DESC, id DESC);
~~~

Exact syntax and index ordering utilization depend on the database engine. Inspect `EXPLAIN`/query plans on your target DBMS; if supporting multiple sort modes, you may need separate indexes for each critical access path. Do not create indexes solely from examples without evaluating workload and write overhead.

A Spring Data JPA repository can declare a custom query:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookCursorRepository extends JpaRepository<Book, Long> {

    List<Book> findByTenantIdOrderByCreatedAtDescIdDesc(
            String tenantId,
            Pageable pageable
    );

    @Query("""
            select b from Book b
            where b.tenantId = :tenantId
              and (
                    b.createdAt < :createdAt
                    or (b.createdAt = :createdAt and b.id < :id)
              )
            order by b.createdAt desc, b.id desc
            """)
    List<Book> findAfter(
            @Param("tenantId") String tenantId,
            @Param("createdAt") Instant createdAt,
            @Param("id") Long id,
            Pageable limit
    );
}
~~~

For the first page, use the derived query with a fixed sort order. For subsequent pages, use the keyset predicate in `findAfter`. `Pageable` here only caps the row count; ordering is fixed inside the query.

## 12. Fetching one extra record to determine hasNextPage

When a client requests `first = 20`, the service loads up to 21 records. If a 21st record exists, the current page has a next page. The extra record is excluded from `edges`.

Response models:

~~~java
import java.util.List;

public record BookEdge(String cursor, Book node) {}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor
) {}

public record BookConnection(List<BookEdge> edges, PageInfo pageInfo) {}
~~~

Service:

~~~java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

@Service
public class BookConnectionService {

    private final BookCursorRepository repository;
    private final BookCursorCodec cursorCodec;

    public BookConnectionService(
            BookCursorRepository repository,
            BookCursorCodec cursorCodec
    ) {
        this.repository = repository;
        this.cursorCodec = cursorCodec;
    }

    public BookConnection findNextPage(
            String tenantId,
            int first,
            String after
    ) {
        if (first < 1 || first > 100) {
            throw new InvalidPaginationException("first must be between 1 and 100");
        }

        int fetchSize = first + 1;
        List<Book> rows;

        if (after == null || after.isBlank()) {
            rows = repository.findByTenantIdOrderByCreatedAtDescIdDesc(
                    tenantId,
                    PageRequest.of(0, fetchSize)
            );
        }
        else {
            BookCursor cursor = cursorCodec.decode(after);
            rows = repository.findAfter(
                    tenantId,
                    cursor.createdAt(),
                    cursor.id(),
                    PageRequest.of(0, fetchSize)
            );
        }

        boolean hasNextPage = rows.size() > first;
        List<Book> pageItems = hasNextPage
                ? rows.subList(0, first)
                : rows;

        List<BookEdge> edges = pageItems.stream()
                .map(book -> new BookEdge(cursorCodec.encode(book), book))
                .toList();

        String startCursor = edges.isEmpty() ? null : edges.get(0).cursor();
        String endCursor = edges.isEmpty() ? null : edges.get(edges.size() - 1).cursor();

        boolean hasPreviousPage = after != null && !after.isBlank();
        return new BookConnection(
                edges,
                new PageInfo(hasNextPage, hasPreviousPage, startCursor, endCursor)
        );
    }
}
~~~

The example above demonstrates forward pagination. `hasPreviousPage` is inferred from whether the request supplied an `after` cursor, assuming the cursor is valid and belongs to the same connection scope. If exact accuracy is required in all situations, verify that the cursor belongs to the current tenant/filter and check whether any record precedes the cursor.

## 13. Resolver for cursor connections

The resolver only accepts arguments and context, then delegates querying to the service:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookConnectionController {

    private final BookConnectionService connectionService;
    private final CurrentTenantProvider tenantProvider;

    public BookConnectionController(BookConnectionService connectionService,
            CurrentTenantProvider tenantProvider) {
        this.connectionService = connectionService;
        this.tenantProvider = tenantProvider;
    }

    @QueryMapping
    public BookConnection bookConnection(
            @Argument Integer first,
            @Argument String after
    ) {
        int pageSize = first == null ? 20 : first;
        return connectionService.findNextPage(
                tenantProvider.currentTenantId(), pageSize, after);
    }
}
~~~

Clients use `endCursor` to fetch the next page:

~~~graphql
query NextBooks($first: Int!, $after: String) {
    bookConnection(first: $first, after: $after) {
        edges {
            cursor
            node { id title }
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

Variables for the first request can be `{ "first": 20 }`. The next request passes `{ "first": 20, "after": "<endCursor-of-previous-page>" }`.

## 14. Backward pagination with last and before

Relay connections also support `last` and `before` to load records preceding a cursor. With canonical ordering `createdAt DESC, id DESC`, backward queries typically invert the predicate and sort direction when reading from the database, fetch `last + 1` records, and then reverse the list back to canonical order before creating edges.

Conceptual example:

~~~sql
WHERE tenant_id = :tenantId
  AND (
       created_at > :createdAt
       OR (created_at = :createdAt AND id > :id)
  )
ORDER BY created_at ASC, id ASC
LIMIT :limit;
~~~

After retrieving results, reverse the list order before returning so clients always see the same canonical ordering. Thoroughly test `hasPreviousPage`, `hasNextPage`, `startCursor`, and `endCursor` when pages are empty or contain only a single element.

If the application only needs forward loading, do not add `last`/`before` until there is a clear use case. Bidirectional support adds complexity to cursor services and tests.

## 15. Pagination and filtering must be applied together

Filters, tenant scope, and authorization must be applied before pagination. Never load a global page and filter out unauthorized records in Java:

~~~java
// Avoid: can return an underfilled page and corrupt page metadata.
Page<Book> page = repository.findAll(pageable);
List<Book> visible = page.getContent().stream()
        .filter(book -> book.tenantId().equals(tenantId))
        .toList();
~~~

Instead, place the tenant condition inside the database query before `LIMIT/OFFSET` or keyset predicates. This prevents data leaks and ensures page metadata accurately reflects the result set the user is allowed to view.

Cursors must also be bound to the active filter/sort. If a cursor was generated for `status = PUBLISHED` and the next request switches to `status = DRAFT`, the cursor position may no longer make sense. Encode a filter fingerprint inside the cursor or require clients to reuse identical filter variables.

## 16. Pagination does not automatically solve N+1

Pagination bounds the number of parent objects. However, if each parent has child fields requiring separate queries, a query can still trigger N+1 within a single page.

For example, a page has 20 books and each book needs its author:

- Pagination loads 20 books.
- A naive resolver can trigger 20 author queries.
- `DataLoader` or `@BatchMapping` groups author IDs into a single batch.

Therefore, combine pagination with DataLoader for nested relationships. Inspect both parent row counts and batch/database call counts in tests and profiling.

## 17. Testing offset pagination with GraphQlTester

Tests should verify both the response and the `Pageable` passed down to the service:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest(BookQueryController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    CurrentTenantProvider tenantProvider;

    @Test
    void appliesPageSizeAndStableSort() {
        given(tenantProvider.currentTenantId()).willReturn("tenant-a");
        given(bookService.findVisibleBooks(eq("tenant-a"), org.mockito.ArgumentMatchers.any()))
                .willReturn(new PageImpl<>(
                        List.of(new Book(21L, "Spring GraphQL", 10L, "tenant-a",
                                Instant.parse("2026-01-01T00:00:00Z"))),
                        PageRequest.of(1, 10),
                        21
                ));

        graphQlTester.document("""
                query {
                    books(page: 1, size: 10, sortBy: CREATED_AT, direction: DESC) {
                        items { id title }
                        page
                        size
                        totalElements
                        totalPages
                        hasNext
                    }
                }
                """)
                .execute()
                .path("books.page")
                .entity(Integer.class)
                .isEqualTo(1);

        verify(bookService).findVisibleBooks(eq("tenant-a"), argThat(pageable ->
                pageable.getPageNumber() == 1
                        && pageable.getPageSize() == 10
                        && pageable.getSort().getOrderFor("createdAt").isDescending()
                        && pageable.getSort().getOrderFor("id").isDescending()
        ));
    }
}
~~~

The test mocks `CurrentTenantProvider` to return the current principal's tenant, so no tenant ID needs to be passed via GraphQL arguments.

Boundary tests to include:

- `page = 0`, `size = 1`.
- Negative `page` is rejected.
- `size = 0` and `size` exceeding the maximum limit are rejected.
- Omitted `size` receives the default.
- Sort fields outside the enum cannot be bound.
- Sort always includes a unique tie-breaker.
- Tenant filter is passed down to the repository.
- Final page has `hasNext = false`.

## 18. Testing cursor pagination

For cursor pagination, verify that:

1. The first page fetches at most `first + 1` records.
2. `hasNextPage` is true when an extra record exists.
3. The first page's `endCursor` works for the next request.
4. The next page does not repeat the last record of the previous page.
5. Records with identical timestamps remain deterministically ordered via the ID tie-breaker.
6. Invalid cursors are clearly rejected.
7. Tenant and filters are enforced on both the first page and subsequent pages.

Example testing two pages with `GraphQlTester`:

~~~java
@Test
void loadsNextCursorPageWithoutDuplicates() {
    String firstPageDocument = """
            query {
                bookConnection(first: 2) {
                    edges { cursor node { id } }
                    pageInfo { hasNextPage endCursor }
                }
            }
            """;

    GraphQlTester.Response firstResponse = graphQlTester
            .document(firstPageDocument)
            .execute();

    firstResponse.path("bookConnection.edges[*].node.id")
            .entityList(String.class)
            .containsExactly("5", "4");
    firstResponse.path("bookConnection.pageInfo.hasNextPage")
            .entity(Boolean.class)
            .isEqualTo(true);

    String endCursor = firstResponse.path("bookConnection.pageInfo.endCursor")
            .entity(String.class)
            .get();

    graphQlTester.document("""
            query Next($after: String!) {
                bookConnection(first: 2, after: $after) {
                    edges { node { id } }
                    pageInfo { hasNextPage }
                }
            }
            """)
            .variable("after", endCursor)
            .execute()
            .path("bookConnection.edges[*].node.id")
            .entityList(String.class)
            .containsExactly("3", "2");
}
~~~

The test assumes a fixture with IDs ordered from `5` down to `1` and matching service/repository configuration. For tests running against a real database, create fixtures with identical timestamps to prove the ID tie-breaker works.

## 19. Common pitfalls when implementing pagination

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query still returns entire collection | Resolver loads everything and slices in memory | Use `Pageable`, SQL limits, or keyset queries in the repository |
| Deep pages are very slow | Large offsets must skip many rows | Switch to cursor/keyset pagination |
| Duplicate or missing records across pages | Unstable sort or data changes between requests | Add a unique tie-breaker; consider keyset or snapshot semantics |
| `totalElements` slows down queries | `Page<T>` runs an expensive count query | Use `Slice<T>` or a connection with only `hasNextPage` |
| Clients request huge page sizes | Missing server-side cap | Clamp or reject sizes above the maximum threshold |
| Sort fails or exposes unintended fields | Using raw property strings from client | Use an enum/allow-list mapped to fixed properties |
| Next cursor page skips records sharing timestamp | Cursor only stores timestamp | Use a composite cursor with a unique tie-breaker |
| Clients can tamper with cursors | Mistaking Base64 for encryption | Sign cursors or validate payloads; always enforce authorization in queries |
| Changing filters makes next page inconsistent | Cursor not bound to filter/sort scope | Embed a filter/sort fingerprint in cursors or enforce matching variables |
| Page has fewer records than expected | Filtering applied after fetching the page | Push filters/tenant conditions into the query before pagination |
| Page of 20 books still executes many SQL queries | N+1 on child fields | Use DataLoader or `@BatchMapping` |
| GraphQL fails to serialize large total counts | `Int` exceeds 32-bit range | Use a custom scalar or omit total count |

## 20. Workflow for choosing and implementing pagination

When designing a GraphQL collection field:

1. Determine whether the UI needs arbitrary page jumps or only incremental loading.
2. Choose offset/page-based pagination for moderate collections; choose cursor/keyset for large or frequently changing collections.
3. Define explicit arguments and response shapes in the SDL.
4. Configure default and maximum page sizes on the server.
5. Only allow sort fields from an allow-list.
6. Ensure ordering includes a unique tie-breaker.
7. Apply tenant, authorization, and filters before limit/offset.
8. Use `Page` when total counts are genuinely needed; use `Slice` or `first + 1` when only checking for a next page.
9. For cursors, encode all sort keys and bind cursors to the filter/sort scope.
10. Combine with DataLoader for child fields to prevent N+1 within each page.
11. Test boundaries, sorting, cursor continuity, missing/invalid cursors, and tenant isolation.
12. Measure query count, count-query cost, page depth, and response size with integration/performance tests.

Effective pagination must happen at the database layer with deterministic ordering and explicit input bounds. Offset pagination keeps page-numbered UIs simple; cursor/keyset pagination scales better for large datasets and continuous feeds. In both cases, authorization, filtering, and DataLoader remain integral parts of query design.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Data — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [GraphQL Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
