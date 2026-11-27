# Queries Returning a List

## 1. Queries Returning a List in GraphQL

A common requirement for a GraphQL API is returning multiple records, such as a list of books, orders, users, or products. In GraphQL SDL, a field that returns a list is declared using square brackets `[]` around the element type.

Example:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

`books` returns a list of `Book`. The client selects the fields to fetch for each element:

```graphql
query BookCatalog {
    books {
        id
        title
    }
}
```

The response is a JSON array:

```json
{
  "data": {
    "books": [
      { "id": "book-101", "title": "GraphQL Fundamentals" },
      { "id": "book-102", "title": "Spring for GraphQL" }
    ]
  }
}
```

In Spring for GraphQL, the root field `books` is typically handled by a method annotated with `@QueryMapping`. The method can return `List<Book>` or another result type compatible with the list declared in the SDL.

## 2. Understanding List Nullability

In GraphQL, the `!` modifier can apply to the list itself and to each element inside the list. These two positions are independent of each other.

| SDL Type | Can the list be null? | Can elements be null? |
| --- | --- | --- |
| `[Book]` | Yes | Yes |
| `[Book!]` | Yes | No |
| `[Book]!` | No | Yes |
| `[Book!]!` | No | No |

Example:

```graphql
type Query {
    optionalBooks: [Book]
    booksWithRequiredItems: [Book!]!
}
```

With `[Book!]!`, the server must return a non-`null` list, and every element in the list must also be non-`null`. An empty list `[]` is still valid. When no matching data exists, it should usually be represented by an empty list rather than `null` if the API contract specifies that the field always returns a list.

If a resolver returns `null` for a field typed `[Book!]!`, GraphQL raises an execution error and applies null propagation rules. If an element is `null`, the error also propagates based on the nullability of the element and the parent list. Therefore, choose nullability according to business semantics and ensure Java data satisfies that contract.

In Java, `List<Book>` can contain `null` elements and the reference variable itself can be `null`. Java types do not automatically express GraphQL's `!` constraints. The resolver and service layer must ensure neither a null list nor null elements are returned when the schema requires non-null.

## 3. Mapping `@QueryMapping` to `List<T>`

In annotation-based controllers, the method name is used by default as the field name on the root `Query`. For example, if the schema declares `books`, a `books()` method can return `List<Book>`:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

`@QueryMapping` maps the method to the `Query.books` field. Spring for GraphQL calls the method when the client requests this field, and the GraphQL engine serializes each element according to the `Book` type in the schema.

The example above illustrates basic mapping. In a real application, avoid having a list endpoint call an unbounded `findAll()` when the table can grow large. Design pagination and element limits as covered in the following sections.

### When Do You Need `@SchemaMapping`?

`@QueryMapping` is for fields on the root `Query` type. If a list field belongs to another object, such as `Author.books`, use `@SchemaMapping`:

```graphql
type Author {
    id: ID!
    books: [Book!]!
}
```

```java
@SchemaMapping(typeName = "Author", field = "books")
public List<Book> books(Author author) {
    return bookService.findByAuthorId(author.id());
}
```

The method receives the `Author` source object and returns that author's list of books. Even though both methods return `List<Book>`, the annotation is chosen based on the field's location in the schema.

## 4. Returning Filtered Lists Using Arguments

A useful list field typically lets clients pass filter conditions. The schema can declare arguments directly:

```graphql
type Query {
    booksByTitle(keyword: String!, availableOnly: Boolean = false): [Book!]!
}
```

The resolver uses `@Argument` to receive the values:

```java
@QueryMapping
public List<Book> booksByTitle(
        @Argument String keyword,
        @Argument Boolean availableOnly) {
    return bookService.searchByTitle(keyword, Boolean.TRUE.equals(availableOnly));
}
```

The client sends the operation:

```graphql
query SearchBooks($keyword: String!, $availableOnly: Boolean) {
    booksByTitle(keyword: $keyword, availableOnly: $availableOnly) {
        id
        title
    }
}
```

Variables:

```json
{
  "keyword": "spring",
  "availableOnly": true
}
```

When a list has multiple filter criteria, group them into an input object so the schema stays concise and extensible:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
    available: Boolean
}

type Query {
    books(filter: BookFilter): [Book!]!
}
```

Java can use a corresponding DTO or record:

```java
public record BookFilterInput(
        String keyword,
        String authorId,
        Boolean available) {
}

@QueryMapping
public List<Book> books(@Argument BookFilterInput filter) {
    return bookService.search(filter);
}
```

Field names in the input object must match the properties used by Spring's binding mechanism. For complex inputs, use a DTO with appropriate constructors or setters. Check for null on each criterion because clients may omit the input or leave individual fields unset.

Filter conditions should be applied in the service or repository before returning results. Do not load the entire table into Java and filter afterward if the database can evaluate the conditions more efficiently.

## 5. Pagination Is an Essential Requirement for List Queries

Returning an entire list may be acceptable for small, fixed datasets. For data that grows over time, unpaginated queries can produce huge responses, consume memory, increase serialization time, and place heavy load on the database.

A simple approach is offset pagination:

```graphql
type Query {
    books(first: Int = 20, offset: Int = 0): [Book!]!
}
```

`first` is the number of items to retrieve, and `offset` is the number of items to skip before taking the current page. The resolver should enforce bounds on these values:

```java
@QueryMapping
public List<Book> books(
        @Argument Integer first,
        @Argument Integer offset) {

    int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    int start = offset == null ? 0 : Math.max(offset, 0);

    return bookService.findPage(pageSize, start);
}
```

In this example, the page size is capped at 100 and negative offsets are clamped to 0. Specific rules can vary by API, but the server must always validate limits itself; never assume clients will only send valid values.

### Pros and Cons of Offset Pagination

- Easy to understand and easy to integrate with `LIMIT`/`OFFSET` and numbered page UIs.
- Can become slow at very large offsets because the database must scan past many rows before returning the page.
- When records are inserted or deleted between calls, items may be duplicated or skipped across pages.
- Requires a stable sort order, ideally adding a unique key as a tie-breaker.

For example, the SQL query should specify a deterministic order:

```sql
SELECT id, title
FROM books
ORDER BY title ASC, id ASC
LIMIT :limit OFFSET :offset;
```

Without `ORDER BY`, the database does not guarantee row ordering. Under pagination, this makes results across calls unpredictable.

## 6. Pagination with Spring Data `Pageable`

If the application uses Spring Data, you can translate `first` and `offset` into a `Pageable` so the repository executes a bounded query.

Service example:

```java
public List<Book> findPageContent(int pageSize, int offset) {
    int pageNumber = offset / pageSize;
    Pageable pageable = PageRequest.of(
        pageNumber,
        pageSize,
        Sort.by(Sort.Order.asc("title"), Sort.Order.asc("id"))
    );

    return bookRepository.findAll(pageable)
        .map(bookMapper::toDomain)
        .getContent();
}
```

This maps `offset` to a page number when `offset` is a multiple of `pageSize`. If the API allows arbitrary offsets, handle them accurately according to the repository strategy or use a query that supports offsets directly; integer division rounds the offset down to the start of the nearest page.

Another option is to design the API to accept `page` and `size` from the start:

```graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
```

Then `PageRequest.of(page, size, sort)` maps more directly. Even when using `Pageable`, do not return `Page<Book>` directly for a field declared as `[Book!]!`; return `getContent()` or design a dedicated GraphQL object containing `content`, `totalElements`, `totalPages`, and page metadata.

## 7. Designing Responses with Pagination Metadata

If clients need to know the total record count or whether a next page exists, instead of returning only a list, declare an object containing both the list and metadata:

```graphql
type BookPage {
    items: [Book!]!
    page: Int!
    size: Int!
    totalElements: Long!
    totalPages: Int!
    hasNext: Boolean!
}

type Query {
    books(page: Int = 0, size: Int = 20): BookPage!
}
```

`Long` in the example is a custom scalar, which must be declared and registered via runtime wiring or replaced with an existing compatible scalar. If you do not want to add a custom scalar, you can choose `Int` when the maximum total count fits within the 32-bit range.

Illustrative Java record:

```java
public record BookPage(
        List<Book> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}
```

Resolver:

```java
@QueryMapping
public BookPage books(
        @Argument Integer page,
        @Argument Integer size) {

    int pageNumber = page == null ? 0 : Math.max(page, 0);
    int pageSize = size == null ? 20 : Math.min(Math.max(size, 1), 100);

    Page<Book> result = bookService.findPage(
        PageRequest.of(pageNumber, pageSize)
    );

    return new BookPage(
        result.getContent(),
        result.getNumber(),
        result.getSize(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.hasNext()
    );
}
```

In this example, `Page<Book>` is only used internally in Java; the GraphQL response is `BookPage` with a structure explicitly declared in the SDL. This lets clients access page items and metadata without coupling to Spring Data's internal structure.

## 8. Cursor Pagination for Frequently Changing Lists

Offset pagination works well for many admin screens and numbered-page lists. For feeds or continuously updated lists, cursor pagination is usually more stable because the client continues from the position of the last item instead of asking to skip a fixed number of records.

A simple connection structure:

```graphql
type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    endCursor: String
    hasNextPage: Boolean!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
}

type Query {
    books(first: Int = 20, after: String): BookConnection!
}
```

The client sends `after` using the cursor received from the previous page:

```graphql
query NextBooks($first: Int!, $after: String) {
    books(first: $first, after: $after) {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            endCursor
            hasNextPage
        }
    }
}
```

The cursor typically encodes the sort key of the last record, such as `createdAt` and `id`. The server must validate the cursor, maintain a stable sort order, and apply the corresponding continuation query predicate. Do not trust a cursor sent by the client without validating its structure and bounds.

Cursor pagination does not automatically guarantee a consistent snapshot if data is updated while the client iterates. If the business logic requires strict consistency, additionally design a snapshot/version or appropriate time boundary condition.

## 9. Sorting Lists Safely

Clients may need to sort lists by title, creation date, or price. Expose valid choices using an enum rather than accepting arbitrary column names:

```graphql
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
        first: Int = 20
        sortBy: BookSortField = TITLE
        direction: SortDirection = ASC
    ): [Book!]!
}
```

The resolver maps the enum to an allowed property:

```java
@QueryMapping
public List<Book> books(
        @Argument Integer first,
        @Argument BookSortField sortBy,
        @Argument SortDirection direction) {

    int size = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    String property = switch (sortBy == null ? BookSortField.TITLE : sortBy) {
        case TITLE -> "title";
        case CREATED_AT -> "createdAt";
    };
    Sort.Direction order = direction == SortDirection.DESC
        ? Sort.Direction.DESC
        : Sort.Direction.ASC;

    return bookService.findSorted(PageRequest.of(
        0,
        size,
        Sort.by(order, property).and(Sort.by("id"))
    ));
}
```

Enums restrict sortable columns and make the schema self-documenting. Never concatenate client-supplied strings directly into SQL `ORDER BY`; if dynamic field names are needed, map them through an allowlist. Add a unique secondary key so ordering remains deterministic when multiple records share the same sort value.

## 10. List Queries and Server-Side Performance

A GraphQL request can return a list at the root field and continue resolving multiple nested fields for each element. Example:

```graphql
query Books {
    books(first: 50) {
        id
        title
        author {
            id
            name
        }
    }
}
```

If `books` loads 50 books in one query, but each `Book.author` invokes a separate repository call, the server may execute one book query plus 50 author queries. This is the N+1 problem on nested fields.

Ways to reduce cost:

- Paginate and cap the maximum item count on root list fields.
- Push filtering, sorting, and pagination down to the repository/database.
- Use `@BatchMapping` or DataLoader to batch relationship loading.
- Query only necessary columns when that reduces data read.
- Avoid calling services inside a resolver loop when batch loading is possible.
- Measure query duration, database call counts, and response size.

Paginating the root list does not solve N+1 on its own. Conversely, DataLoader does not replace page size limits. The two techniques address different problems and usually need to be combined.

## 11. Security and Limits for List Queries

List queries can return large amounts of data or data belonging to different users. The server must enforce access control before returning data to clients.

Some principles:

- Filter by tenant or user scope directly in the service/repository.
- Do not rely on `authorId`, `ownerId`, or filters sent by the client to decide whether a user is authorized to view data.
- Limit `first`, `size`, `offset`, and query complexity.
- Apply per-user or per-client rate limits if the endpoint is at risk of excessive calls.
- Avoid returning entire entities if they contain internal fields or sensitive data not meant for clients.
- Log operations and performance metrics without unnecessarily logging sensitive variables.

If each item has its own access permissions, filter or check permissions per record on the server. Do not return the full list and expect the client to hide unauthorized items.

## 12. Testing Queries Returning Lists with GraphQlTester

`GraphQlTester` lets you test operations and response structure. Example:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookList() {
        graphQlTester.document("""
            query {
                books(first: 10) {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("books")
            .entityList(BookView.class)
            .hasSize(2);
    }
}
```

`BookView` is a test DTO with `id` and `title` properties; the test context must provide appropriate data so the list has two items.

Additional cases to test:

- List with multiple items where each item has the expected fields.
- No data returns `[]` per the non-null list contract.
- Unmatched filter returns an empty list.
- `first` equal to 0, negative, or exceeding the limit is handled according to policy.
- Invalid offset or cursor is rejected or normalized per contract.
- Result ordering is deterministic when multiple records share the same sort value.
- Nested fields are batched properly when the list has multiple parents.
- Unauthorized users do not receive out-of-scope records.
- Service exceptions are mapped to appropriate GraphQL errors.

## 13. Common Errors When Queries Return Lists

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Field returns `null` when there are no records | Resolver returns `null` instead of an empty list | Return `List.of()` or an empty collection if the schema is `[Book!]!` |
| Non-null error when an element is null | Java list contains a null element while SDL uses `[Book!]` | Remove or handle invalid elements before returning |
| Slow query as data grows | Missing pagination or loading the entire table | Add a page size limit and paginated database queries |
| Pages have duplicate or missing items | Unstable sort order or data changes between calls | Use deterministic sorting and consider cursor pagination |
| `Page<T>` does not return the list properly | Java Page object does not directly match an SDL list | Return `getContent()` or create a GraphQL page wrapper |
| Filter argument is always null | Input field name or DTO binding mismatch | Check SDL, property names, and `@Argument` |
| Sorting causes errors or query risks | Using arbitrary column names passed by the client | Use an enum and an allowlist of sort properties |
| N+1 when fetching nested fields | Each element triggers a relationship query | Use DataLoader or `@BatchMapping` |
| User sees another tenant's data | Security filter relies only on client input | Apply tenant/authorization from the server security context |

## 14. List Query Design Checklist

- [ ] List field is declared with appropriate nullability.
- [ ] `@QueryMapping` or `@SchemaMapping` resolver returns the corresponding Java type.
- [ ] Empty results return `[]` if the schema requires a non-null list.
- [ ] Maximum page size and validation exist for pagination parameters.
- [ ] Filtering and sorting are handled in the service/repository.
- [ ] Sort order is deterministic, with a unique secondary key when needed.
- [ ] `Page<T>` is not returned directly if the SDL declares a simple list.
- [ ] A dedicated wrapper exists if the client needs pagination metadata.
- [ ] Cursor pagination is used when appropriate for frequently changing lists.
- [ ] Nested relationships have been checked for N+1 risks.
- [ ] Authorization and tenant filters are enforced on the server.
- [ ] Tests cover empty lists, populated lists, pagination, filters, and errors.

## Conclusion

Queries returning lists in GraphQL are declared with list types `[]` and typically map to `List<T>` in Spring for GraphQL `@QueryMapping` methods. Nullability of both the list and its elements must be clearly defined; with `[Book!]!`, an empty list is valid, while a null list or null element violates the contract.

For real-world data, list queries require filtering, sorting, and pagination with server-controlled limits. You can use offset pagination for simple lists, cursor pagination for frequently changing feeds, or a GraphQL wrapper when clients need page metadata. Combine pagination with DataLoader or `@BatchMapping` for nested fields, server-side authorization, and `GraphQlTester` tests so list APIs remain reliable as data grows.
