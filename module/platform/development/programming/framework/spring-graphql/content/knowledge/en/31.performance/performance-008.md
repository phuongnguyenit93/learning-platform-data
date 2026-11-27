# Offset pagination

When a GraphQL query returns a large dataset, the server should not load every record and send it all back to the client in one response. Offset pagination splits the result set into small slices: the client sends a starting position via `offset` and the maximum number of items to return via `limit`. The database skips the first rows and returns the next slice.

Spring for GraphQL lets you build offset pagination directly in SDL and annotated controllers using `@QueryMapping` and `@Argument`. If you use Spring Data Querydsl or Query by Example, you can leverage `@GraphQlRepository` to auto-register paginated queries; this auto-registration mode uses offset-based pagination with a default of 20 items per page.

This lesson walks through the GraphQL contract, resolver and repository implementation, deterministic sorting, input validation, total record counting strategies, performance at high offsets, consistency when data changes, and testing.

## 1. What is offset pagination?

Offset pagination defines a page using two values:

- `offset`: number of records to skip from the start of the result set.
- `limit`: maximum number of records to return.

Example with `limit = 20`:

| Page | Offset | Limit | Record positions |
| --- | ---: | ---: | --- |
| 1 | 0 | 20 | 1–20 |
| 2 | 20 | 20 | 21–40 |
| 3 | 40 | 20 | 41–60 |
| 4 | 60 | 20 | 61–80 |

Offsets usually start at 0. If the client sends `offset = 40` and `limit = 20`, the server skips the first 40 records and fetches up to the next 20 records.

In SQL, this concept is typically expressed as:

```sql
SELECT id, title, created_at
FROM books
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

Exact syntax varies by database engine. In JPA, you can use `Query.setFirstResult(offset)` and `Query.setMaxResults(limit)` to ask the persistence provider to apply dialect-appropriate limits and offsets.

Offset pagination is easy to understand and convenient for UIs with page numbers, Next/Previous buttons, or jumping to specific positions. However, large offsets can consume significant resources, and data changing between two requests can shift page positions.

## 2. Designing a GraphQL schema for offset and limit

A simple schema for a library API:

```graphql
type Query {
  books(offset: Int = 0, limit: Int = 20): BookPage!
}

type BookPage {
  items: [Book!]!
  offset: Int!
  limit: Int!
  hasNextPage: Boolean!
}

type Book {
  id: ID!
  title: String!
  createdAt: String!
}
```

`books` returns a `BookPage` object instead of returning a bare list. The response can carry metadata so clients know the current position and whether more data remains.

Example client requesting the first page:

```graphql
query FirstBooks {
  books(offset: 0, limit: 20) {
    offset
    limit
    hasNextPage
    items {
      id
      title
      createdAt
    }
  }
}
```

Next page request:

```graphql
query NextBooks($offset: Int!, $limit: Int!) {
  books(offset: $offset, limit: $limit) {
    offset
    limit
    hasNextPage
    items {
      id
      title
    }
  }
}
```

Variables:

```json
{
  "offset": 20,
  "limit": 20
}
```

Sample response:

```json
{
  "data": {
    "books": {
      "offset": 20,
      "limit": 20,
      "hasNextPage": true,
      "items": [
        {
          "id": "book-21",
          "title": "Spring GraphQL",
          "createdAt": "2026-10-15T08:30:00Z"
        }
      ]
    }
  }
}
```

In this example, the list is shortened for readability. In practice, it can return up to 20 items.

### Why return BookPage?

If the schema only returns `[Book!]!`, clients do not know which offset/limit the server applied or whether a next page exists. A page object can be extended with:

- `totalCount` if the UI needs to display total records or page count.
- `hasPreviousPage` if the client needs previous-page status.
- `nextOffset` if you want the server to return the next offset directly.
- `appliedFilters` if confirming applied filters is useful.

Do not add metadata that clients do not use. Every extra field can trigger additional database queries or computation logic.

### Note on GraphQL Int

GraphQL's built-in `Int` scalar is a signed 32-bit integer. Therefore, `offset` and `limit` typed as `Int` cannot represent integers larger than the 32-bit limit. For very large datasets, enforce an appropriate offset cap or define a custom scalar/string for wider numeric types if the API contract genuinely requires it. `totalCount` shares the same limitation if declared as `Int`.

## 3. Receiving offset and limit with @QueryMapping

Spring for GraphQL uses `@QueryMapping` to map controller methods to fields on the GraphQL `Query` type. The `@Argument` annotation binds GraphQL arguments to Java parameters.

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookPage books(
            @Argument int offset,
            @Argument int limit) {

        return bookService.findBooks(offset, limit);
    }
}
```

Because the schema declares default values, if a client omits either argument, GraphQL supplies the default value before calling the resolver. If you prefer applying defaults in Java instead of SDL, declare nullable wrapper-type arguments and handle null values explicitly.

Do not assume `Pageable` is automatically bound from two `offset` and `limit` arguments across every Spring for GraphQL version. Dedicated controller pagination support uses `Subrange` or `ScrollSubrange` when `CursorStrategy` is configured; that is a separate mechanism. For a custom offset/limit contract, binding explicit scalars via `@Argument` is direct and clear.

## 4. Validating offset and limit

Negative offsets or oversized limits can create invalid requests or force the server to process unnecessary amounts of data. Always validate on the server, even if the client already validates.

Example capping maximum records at 100:

```java
public BookPage findBooks(int offset, int limit) {
    if (offset < 0) {
        throw new IllegalArgumentException("offset must be greater than or equal to zero");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("limit must be between 1 and 100");
    }

    // Fetch page after validating arguments.
}
```

In production applications, map these input errors to an appropriately classified GraphQL error such as `BAD_REQUEST` using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. Never let invalid input errors surface as internal system errors.

Common rules:

| Input | Rule |
| --- | --- |
| offset | Non-negative |
| limit | Greater than 0 |
| max limit | Bounded by database load and response size |
| overly large offset | Can reject, cap, or guide clients toward another search mechanism |
| offset + limit | Compute safely to avoid integer overflow |

If Bean Validation is needed, wrap parameters in an input object and apply suitable constraints. With two standalone scalar arguments, explicit validation in the service is also clean.

Do not silently clamp a huge limit down to 100 without notifying the client. Clients need to know what values are accepted; returning a clear validation error prevents the UI from misinterpreting how many items were received.

## 5. Querying data with JPA offset

JPA supports offsetting and limiting results via `setFirstResult` and `setMaxResults`. Example repository:

```java
@Repository
public class JpaBookPageRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Book> findSlice(int offset, int limit) {
        return entityManager.createQuery("""
                select book
                from Book book
                order by book.createdAt desc, book.id desc
                """, Book.class)
                .setFirstResult(offset)
                .setMaxResults(limit)
                .getResultList();
    }
}
```

In this query, `ORDER BY` has two criteria:

1. `createdAt DESC` so newer books appear first.
2. `id DESC` as a tie-breaker when multiple books share the same creation timestamp.

The second criterion is critical. If you sort only by a non-unique column, the database can return rows with equal values in different orders across runs. When the client requests the next page, some records may be duplicated or skipped even when the data has not changed.

### Using limit + 1 to detect the next page

If the schema only needs `hasNextPage` without a total record count, you do not need to run an extra count query. Fetch one row more than limit:

```java
public BookPage findBooks(int offset, int limit) {
    validate(offset, limit);

    List<Book> rows = repository.findSlice(offset, limit + 1);
    boolean hasNextPage = rows.size() > limit;

    List<Book> items = hasNextPage
            ? rows.subList(0, limit)
            : rows;

    return new BookPage(
            List.copyOf(items),
            offset,
            limit,
            hasNextPage);
}
```

DTO:

```java
public record BookPage(
        List<Book> items,
        int offset,
        int limit,
        boolean hasNextPage) {
}
```

Since limit is capped at 100, `limit + 1` cannot overflow. The `(limit + 1)`-th item is only used to check whether more data exists; do not include it in the response.

This approach resembles Spring Data's `Slice` concept: knowing whether a next slice exists without counting the entire result set.

## 6. When is totalCount needed?

Some interfaces need the total record count to display "1–20 of 1,250 results" or compute total page numbers. In that case, you can add a `totalCount` field and run a count query.

Example:

```java
public long countBooks() {
    return entityManager.createQuery(
            "select count(book) from Book book",
            Long.class)
            .getSingleResult();
}
```

If the query has filters, the count query must apply the exact same predicates as the page query:

```sql
SELECT COUNT(*)
FROM books
WHERE status = 'PUBLISHED';
```

The data query must also apply `status = 'PUBLISHED'`. If the two queries use different conditions, `totalCount` will not match the dataset the client is paginating.

### Page vs Slice

| Result type | Data fetched | Extra cost |
| --- | --- | --- |
| Slice | limit + 1 items | No full count needed |
| Page with totalCount | limit items + count query | One additional count query |

Count queries can be expensive with complex joins, multi-condition filters, or huge tables. Return `totalCount` only when the UI or business logic genuinely requires it.

GraphQL's built-in `Int` only holds 32-bit integers. If total records can exceed that limit, use an appropriate custom scalar or represent the total count as a string per the API contract; never silently cast `long` to `int`.

## 7. Offset pagination with Spring Data @GraphQlRepository

If your application already uses Spring Data Querydsl or Query by Example, Spring for GraphQL can auto-register DataFetchers for repositories annotated with `@GraphQlRepository`. Auto-registration supports single-item queries, multi-item queries, and paginated queries.

Example repository using Querydsl:

```java
@GraphQlRepository
public interface BookRepository extends
        JpaRepository<Book, Long>,
        QuerydslPredicateExecutor<Book> {
}
```

The schema declares a connection type named after the domain type:

```graphql
type Query {
  books: BooksConnection
}

type Book {
  id: ID!
  title: String!
}
```

For paginated queries, the connection type name must match the domain type name before the `Connection` suffix. For example, domain type `Book` corresponds to `BooksConnection`. The Spring for GraphQL Boot Starter automatically detects annotated repositories and registers matching runtime wiring when the required integrations are on the classpath.

In auto-registration, pagination is offset-based with a default of 20 items per page. This is a quick way to expose a simple repository query. If you need a custom contract with `offset`, `limit`, custom metadata, specialized filters, or per-field access controls, build explicit controllers and DataFetchers rather than relying on default conventions.

### QuerydslDataFetcher and Query by Example

Spring for GraphQL has two main integrations:

| Integration | Repository interface | Builder |
| --- | --- | --- |
| Querydsl | `QuerydslPredicateExecutor<T>` | `QuerydslDataFetcher.builder(repository)` |
| Query by Example | `QueryByExampleExecutor<T>` | `QueryByExampleDataFetcher.builder(repository)` |

Querydsl fits when you need flexible, type-safe predicates. Query by Example fits simple search criteria based on an example object. Both can build DataFetchers and be registered via `RuntimeWiringConfigurer`.

Example building a multi-result DataFetcher with Querydsl:

```java
DataFetcher<Iterable<Book>> booksFetcher =
        QuerydslDataFetcher.builder(bookRepository).many();
```

For paginated queries, Spring for GraphQL provides the `scrollable()` builder method. This API works with Spring Data scrolling and `Window`; when configured with a cursor strategy, it can represent cursor-based pagination. Do not confuse this scrolling/cursor connection with custom `offset` and `limit` GraphQL fields from earlier sections.

The Data Integration documentation clearly describes the default 20-item offset-based auto-registration. Verify the actual connection schema and argument behavior for your exact Spring for GraphQL/Spring Data versions before exposing auto-registration as a public contract.

## 8. Why are large offsets slow?

Offset pagination is simple on the client side, but can become expensive in the database. When requesting:

```sql
SELECT id, title
FROM books
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

The database often still has to scan or materialize many results before position 500,000 just to return the next 20 rows. Exact execution depends on the database, query plan, and indexes, but cost generally increases as offset grows.

Illustration:

| Offset | Limit | Potential database work |
| ---: | ---: | --- |
| 0 | 20 | Reads the beginning of the ordered result set |
| 1,000 | 20 | Skips roughly 1,000 rows before returning 20 rows |
| 100,000 | 20 | May have to scan/skip a huge number of rows |
| 1,000,000 | 20 | Can incur heavy I/O and CPU depending on query plan |

This is why offset pagination works best for moderate datasets, UIs needing arbitrary page jumps, or heavily filtered data. For large feeds and deep traversal, keyset/cursor pagination is usually much more efficient.

### Creating indexes matching filters and sorts

If queries frequently run:

```sql
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
```

consider an index matching the filter and sort order, for example:

```sql
CREATE INDEX idx_books_status_created_id
ON books (status, created_at DESC, id DESC);
```

Exact indexes depend on the database, filter selectivity, sort direction, and other queries. Use execution plans to confirm the database uses the index; do not create indexes solely from example column names.

### Selecting only needed columns

The GraphQL selection set might only request `id` and `title`. If an entity has many wide columns or eager relationships, loading the entire entity increases I/O and memory usage. Use projections or DTOs when queries only need a subset of data.

## 9. Sort order must be deterministic

Offset pagination relies on a record's position within a sorted list. If the ordering is non-deterministic, the same offset can point to different records across requests.

Insufficiently stable example:

```sql
ORDER BY created_at DESC
```

Many records can share the same `created_at`. Add a unique key as a tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

This produces a deterministic result sequence. Even if clients are allowed to choose a sort field, the server should still append a unique key at the end to break ties.

### Whitelisting sort inputs

Never concatenate client-sent sort strings directly into JPQL or SQL. Use an enum:

```graphql
enum BookSort {
  NEWEST
  TITLE_ASC
}

type Query {
  books(offset: Int = 0, limit: Int = 20, sort: BookSort = NEWEST): BookPage!
}
```

In the service, map the enum to fixed sort expressions:

```java
Sort sort = switch (requestedSort) {
    case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"));
    case TITLE_ASC -> Sort.by(
            Sort.Order.asc("title"),
            Sort.Order.asc("id"));
};
```

Never let clients pass arbitrary column names without checking a whitelist. Dynamic column names can cause query errors, leak internal properties, or widen the attack surface.

## 10. Data changing between pages

Even with deterministic ordering, offset pagination can duplicate or skip records when data changes between two requests.

Suppose a client fetched the first page containing records at positions 0–19. Before the client requests offset 20, a new record is inserted at the top of the list:

```text
Before insert:
0  1  2  ...  19 | 20  21  22 ...
<---- page 1 ---> | <--- page 2 --->

After insert at top:
NEW 0  1 ... 17 18 | 19 20 21 ...
<----- page 1 -----> | <--- page 2 --->
```

When the client proceeds to call offset 20, some records may reappear compared to the previous page. If a record before the offset is deleted, the client may skip a record it never saw.

This is an inherent property of offset pagination on constantly changing datasets, not necessarily a bug in GraphQL or the repository.

Options to reduce risk:

- Use deterministic ordering with a unique key.
- Use a fixed filter or timestamp cutoff for the entire traversal if business rules allow.
- Use transaction snapshots when all reads occur within one transaction; never assume a transaction spans multiple independent HTTP requests.
- Use cursor/keyset pagination when traversing large, frequently updated datasets.
- Deduplicate by ID on the client if the user experience allows it.

Never promise snapshot consistency across multiple page requests unless the server genuinely maintains a snapshot or matching query token.

## 11. Offset pagination and Spring Data Pageable

Spring Data uses `Pageable` to represent page number, page size, and sort. This is a page-based model:

```java
Page<Book> findAll(Pageable pageable);
```

Clients typically send `page` and `size`, and the server creates:

```java
PageRequest.of(page, size, sort);
```

Offset is computed as:

```text
offset = page * size
```

Therefore, `Pageable` fits when the API paginates by page number and every offset is a multiple of page size. If the GraphQL contract allows arbitrary offsets, such as `offset = 15` and `limit = 20`, converting directly via `PageRequest.of(offset / limit, limit)` loses the exact offset due to integer division.

For arbitrary offsets:

- Use JPA `setFirstResult(offset)` and `setMaxResults(limit)`.
- Use a persistence provider query API that supports offset/limit directly.
- Or build a custom repository abstraction accepting offset and limit.

Never turn an arbitrary offset into a page number by dividing by limit unless the API guarantees offset is divisible by limit.

## 12. Filters and authorization must run before pagination

If the query supports filters, the server must apply filters before computing offset and limit:

```graphql
input BookFilterInput {
  status: String
  authorId: ID
}

type Query {
  books(
    offset: Int = 0
    limit: Int = 20
    filter: BookFilterInput
  ): BookPage!
}
```

Logical processing order:

1. Identify the user and tenant from the security context.
2. Apply authorization/tenant conditions.
3. Apply client-requested filters.
4. Sort in deterministic order.
5. Apply offset and limit.
6. Compute metadata such as hasNextPage or totalCount.

Never fetch a global page and filter access permissions in Java after the database has applied offset. Doing so can return underfilled pages, wrong hasNextPage values, and accidentally leak information through totalCount.

For example, if users can only see books in their tenant, both the item query and count query must include the tenant condition:

```sql
SELECT id, title
FROM books
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM books
WHERE tenant_id = :tenantId;
```

If there is a status filter, both queries must apply that status filter. Authorization is a condition on the result set, not a post-query response cleanup step.

## 13. Avoiding N+1 in nested fields of a page

Offset pagination only caps the number of parent objects returned. If each Book has an Author field and the resolver calls the repository once per book, a page of 20 books can still generate 21 queries.

Example query:

```graphql
query {
  books(offset: 0, limit: 20) {
    items {
      id
      title
      author {
        id
        name
      }
    }
  }
}
```

Combine `@BatchMapping` or `DataLoader` to batch author loads:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    return authorService.findByBooks(books)
            .collectMap(AuthorEntry::book, AuthorEntry::author);
}
```

Thus, pagination limits the number of Books at the root query, while DataLoader/BatchMapping reduces related data loads. The two techniques solve different performance problems and usually belong together.

## 14. Testing offset pagination

Test both the GraphQL contract and repository rules:

- Default offset of 0 and default limit of 20 when arguments are omitted.
- First page and next page have no duplicates when data is unchanged.
- Final page has fewer items than limit and `hasNextPage = false`.
- Offset past the end of the result set returns an empty list with consistent metadata.
- Limit equal to 0, negative, or exceeding maximum is rejected.
- Records sharing sort keys remain deterministically ordered via the tie-breaker.
- Filters and tenant authorization apply identically to item and count queries.
- GraphQL response never exposes total counts outside the user's authorized scope.

Example using `GraphQlTester` in a slice test:

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(BookController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsRequestedOffsetAndLimit() {
        given(bookService.findBooks(20, 10))
                .willReturn(new BookPage(
                        List.of(new Book("book-21", "Spring GraphQL")),
                        20,
                        10,
                        true));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books(offset: 20, limit: 10) {
                        offset
                        limit
                        hasNextPage
                        items {
                            id
                        }
                    }
                }
                """)
                .execute();

        response.path("books.offset").entity(Integer.class).isEqualTo(20);
        response.path("books.limit").entity(Integer.class).isEqualTo(10);
        response.path("books.hasNextPage").entity(Boolean.class).isEqualTo(true);
        response.path("books.items[0].id").entity(String.class).isEqualTo("book-21");

        then(bookService).should().findBooks(20, 10);
    }
}
```

The example uses `@MockitoBean` for current Spring Boot versions. In older Boot versions, the mock bean annotation may be `@MockBean`. The test assumes a schema and controller with the `books` field from earlier sections.

### Repository testing

GraphQL slice tests typically mock the service, so they do not prove SQL/JPA executes offsets accurately. Add repository integration tests against an appropriate database to verify:

- The query returns the exact records at the requested offset.
- Ordering stays consistent when multiple records share createdAt.
- Count and data queries apply identical filters.
- Indexes are utilized according to execution plans in production-like environments.

You do not need a live HTTP server to test repository offset logic; persistence tests can run directly against Spring Data/JPA.

## 15. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| First page and next page duplicate items | Sort lacks a unique tie-breaker or data changed | Add a unique key to ORDER BY; consider cursors |
| Items skipped between pages | Records inserted/deleted before offset | Accept offset trade-off or use cursor/keyset |
| Large offset requests are very slow | Database must skip many rows | Cap offset, add indexes, or switch to keyset |
| Page has fewer items even though more data exists | Filters/authorization applied after pagination | Apply all conditions in the query before limit/offset |
| totalCount does not match items | Count and data queries use different filters or permission scopes | Share identical predicates and tenant conditions |
| Wrong offset when using PageRequest | Converting arbitrary offset to page number via division | Use offset API directly |
| Huge limit bloats response | Missing maximum page size | Validate and cap limit |
| totalCount fails GraphQL Int | `long` value exceeds 32-bit range | Use custom scalar/string or adjust API contract |
| Page order changes randomly | Sorting by non-unique column | Add ID as tie-breaker |
| Small page still triggers many queries | N+1 in nested field resolvers | Use DataLoader or @BatchMapping |
| Sort query can be manipulated | Concatenating raw sort string into SQL/JPQL | Use enum and whitelist sort fields |

## 16. When should you move to cursor/keyset pagination?

Offset pagination has the advantage of being easy to understand, easy to implement, and supporting arbitrary page jumps. However, if clients routinely traverse hundreds of thousands or millions of records, offsets can become costly.

Keyset pagination uses the values of the last record on the current page as the continuation point. For example, sorting by `createdAt DESC, id DESC`, the next page uses:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

The database can use an index on the sort keys to jump to the next slice without skipping all preceding rows. Cursors typically encode these sort keys and are sent back on the next request.

Choose the pagination style based on your needs:

| Requirement | Best fit |
| --- | --- |
| Small pages, moderate dataset | Offset/limit |
| UI needs to jump to any page number | Offset/limit |
| Large feed with continuous new records | Cursor/keyset |
| Want to use Spring Data Window/ScrollPosition | Scroll API and ConnectionAdapter |
| Need exact total record count | Offset + count query, if cost is acceptable |

Spring for GraphQL supports GraphQL Connection types and Spring Data Window/Slice adapters for cursor-based pagination. This is a natural upgrade path when offset pagination stops scaling; there is no need to force every API to use cursors from day one.

## 17. Offset pagination implementation principles

- Clearly define offset as rows skipped and limit as maximum rows returned.
- Configure default and maximum limits in schema/service.
- Validate non-negative offset, positive limit, and reasonable upper bounds.
- Use deterministic ORDER BY with a unique key as a tie-breaker.
- Use `limit + 1` to compute hasNextPage when totalCount is not needed.
- Run count queries only when clients genuinely need total record counts.
- Apply filters, tenant scope, and authorization before offset/limit.
- Create indexes matching filters and sorts; inspect execution plans.
- Avoid excessive offsets; consider cursor/keyset as data grows.
- Use DataLoader or @BatchMapping for nested fields of each item.
- Never concatenate raw client sort strings into SQL/JPQL.
- Test both GraphQL resolvers and repository queries.
- Never promise snapshot consistency across requests without a backing mechanism.

## 18. Hands-on exercise

Build a book search API with offset pagination:

1. Declare GraphQL field `books(offset, limit)` and type `BookPage`.
2. Write `@QueryMapping` accepting both arguments via `@Argument`.
3. Validate offset and limit, capping limit at 100.
4. Write a JPA repository using `setFirstResult` and `setMaxResults`.
5. Sort by createdAt and ID for deterministic ordering.
6. Fetch `limit + 1` items to determine `hasNextPage`.
7. Add a status filter and apply the same filter to both item and count queries.
8. Add tenant filtering before pagination.
9. Write a query fetching books and authors; use `@BatchMapping` to avoid N+1.
10. Write GraphQlTester tests for first page, next page, last page, and invalid inputs.
11. Write repository integration tests verifying offset and sorting.
12. Measure query duration at small and large offsets; inspect execution plans.
13. Propose criteria for migrating to cursor/keyset pagination.

After completing the exercise, you should be able to explain how offset/limit flow from GraphQL down to the database, why sorting must be deterministic, when count queries are needed, and why deep offsets can slow down queries.

## 19. References

- [Spring for GraphQL — Data Integration and @GraphQlRepository](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL — Annotated Controllers and @Argument](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Pagination](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data JPA — Paging and Sorting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Scrolling and Offset](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [GraphQL Specification — Int Scalar](https://spec.graphql.org/September2026/#sec-Int)

Offset pagination is a simple choice for moderate datasets and UIs requiring position-based navigation. When datasets are large or continuously changing, evaluate cursor/keyset pagination along with the scrolling mechanisms provided by Spring for GraphQL and Spring Data.
