# Fixing N+1 with @BatchMapping

In this hands-on practice, we build a GraphQL query that returns a list of books along with their authors. The initial version uses `@SchemaMapping` to load the author separately for each book, creating an N+1 problem. Then we replace the resolver with `@BatchMapping`, batching books within the same execution, fetching authors by a set of IDs, and mapping the results back to the right books.

The goal is not only to reduce the number of SQL queries. We must also ensure the results remain correct when multiple books share an author, a book has no author, data is missing, or the user is only allowed to see part of the data. At the end of the lesson, we will measure and write tests to verify that batching actually works.

## 1. Learning Outcomes

After this hands-on practice, you will be able to:

- Identify N+1 issues from the GraphQL query shape and the number of database accesses.
- Write a field resolver with `@SchemaMapping` and explain why it causes N+1.
- Use `@BatchMapping` to group multiple source objects in a single batch.
- Query unique keys, build a result map, and attach the right value to each source object.
- Handle null IDs, missing records, pagination, tenancy, and access permissions.
- Verify repository/service call counts and compare before/after optimization.

## 2. Context and Data Structure

Suppose an API manages books. Each book has one author; multiple books can share the same author. The client wants to fetch a list of books and author information in a single operation.

SDL Schema:

```graphql
type Query {
    books: [Book!]!
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
```

`Book.author` is left nullable because data might not have an author assigned yet or the author may have been deleted under a data retention policy. If business rules require every book to have an author, change it to `Author!` and clearly define how to handle data that violates the constraint.

Java models used in the example:

```java
public record Book(UUID id, String title, UUID authorId) {}

public record Author(UUID id, String name) {}
```

`Book` only holds `authorId`; it does not have an `author` property for Spring to read automatically. The `Book.author` field in GraphQL will be supplied by our resolver.

Suppose `BookService.findAll()` returns the following three books:

| Book | Author |
|---|---|
| B-101 | A-01 |
| B-102 | A-02 |
| B-103 | A-01 |

Two books share author A-01. This is an important case to verify deduplicating IDs before querying.

## 3. GraphQL Query Used to Reproduce

The client sends the operation:

```graphql
query BooksWithAuthors {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
```

The query requests three books and the `author` field of each book. If it only requests `id` and `title`, the `author` resolver does not need to run. Therefore, when investigating N+1, use the exact query shape causing slowness; calling the endpoint without requesting the relationship field will not reproduce the issue.

## 4. Step 1 — Write a Single-Item Resolver and Observe N+1

Root query resolver:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book book) {
        if (book.authorId() == null) {
            return null;
        }
        return authorService.findById(book.authorId()).orElse(null);
    }
}
```

`@SchemaMapping` is invoked for the `Book.author` field on each `Book` object. With three books, execution may be equivalent to:

```sql
SELECT id, title, author_id FROM book;
SELECT id, name FROM author WHERE id = 'A-01';
SELECT id, name FROM author WHERE id = 'A-02';
SELECT id, name FROM author WHERE id = 'A-01';
```

We have one query to fetch the book list and three queries to fetch authors: four queries in total. When the list grows to 100 books, loading authors can trigger 100 queries. That is the N+1 pattern.

In practice, the query count may differ due to ORM behavior, first-level cache, application cache, or how the repository is implemented. Do not conclude from code alone. Enable SQL logging in development or use tracing/query metrics to count queries per GraphQL request. Caching may mask repeated queries in the example, but it does not solve the cost of loading distinct authors one by one.

## 5. Step 2 — Prepare a Query Method by Set of IDs

Batching is only effective if the data layer can load multiple authors in a single operation. We define a service method that returns a map keyed by ID:

```java
@Service
class AuthorService {

    private final AuthorRepository authorRepository;

    AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    Optional<Author> findById(UUID id) {
        return authorRepository.findById(id);
    }

    Map<UUID, Author> findByIds(Collection<UUID> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }

        return authorRepository.findByIdIn(ids).stream()
                .collect(Collectors.toMap(Author::id, Function.identity()));
    }
}
```

The repository in the example has a method to query by a collection of IDs:

```java
interface AuthorRepository {
    Optional<Author> findById(UUID id);

    List<Author> findByIdIn(Collection<UUID> ids);
}
```

If using Spring Data JPA, you can declare the corresponding derived query method on the entity's repository. If using JDBC or another data access layer, implement it with a single query containing `WHERE id IN (...)` or an equivalent bulk query mechanism. What must be verified is that this method actually performs a batch query by set of IDs rather than looping over single-item queries internally.

When the ID set is empty, return an empty map and do not send an `IN ()` query to the database. When collecting results into a map, each author's ID must be unique; if data might contain duplicates, handle them explicitly instead of silently overwriting.

## 6. Step 3 — Replace `@SchemaMapping` with `@BatchMapping`

Once the batch-by-IDs query API is ready, replace the single-item resolver with a batch resolver:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();

        for (Book book : books) {
            Author author = book.authorId() == null
                    ? null
                    : authors.get(book.authorId());
            result.put(book, author);
        }

        return result;
    }
}
```

Java imports required for the example:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
```

`@BatchMapping(typeName = "Book", field = "author")` binds the method to the `Book.author` field in the schema. Spring for GraphQL registers the corresponding batch loader and DataLoader. When execution needs to resolve this field for multiple books, the source objects are collected and passed into the `List<Book>` parameter.

The method returns `Map<Book, Author>`. Each key is a source `Book` object, and each value is the result for that source's `author` field. Returning a map provides explicit mapping independent of the order in which the repository returns authors. This matters because `WHERE id IN (...)` queries do not guarantee record ordering matches the input ID order.

With the sample data, the deduplicated ID set is `{A-01, A-02}`. The database only needs one query to fetch two authors. The resolver builds the result map for all three books, where B-101 and B-103 both receive author A-01.

## 7. Understanding the Batch and DataLoader Flow

The processing flow can be visualized as follows:

```mermaid
flowchart TD
    A[Query books] --> B[BookService returns multiple Books]
    B --> C[GraphQL requests Book.author field]
    C --> D[DataLoader batches Books to resolve]
    D --> E[@BatchMapping receives List<Book>]
    E --> F[Collect and deduplicate authorIds]
    F --> G[AuthorService queries by ID set]
    G --> H[Build Map<Book, Author>]
    H --> I[GraphQL completes response]
```

DataLoader defers and batches data loads during GraphQL execution. `@BatchMapping` is a convenient way to declare a batch resolver, and Spring registers a loader based on this method. Batching operates within the scope of a single request execution; it is not a distributed cache and does not automatically refresh data across requests.

The actual batch size depends on the number of source objects to resolve, execution behavior, and configured batch limits. With large lists, a single execution may be split into multiple batches. Therefore, the goal is to reduce backend round trips into reasonable groups, not to assume every input size always produces exactly one SQL statement.

## 8. Step 4 — Compare Query Counts Before and After

With the three books in the sample data:

| Implementation | Book Queries | Author Queries | Total |
|---|---:|---:|---:|
| `@SchemaMapping` calling `findById` per book | 1 | 3 | 4 |
| `@BatchMapping` calling `findByIds` once | 1 | 1 | 2 |

These are the expected query counts when the batch contains all three books and the database adapter executes a single bulk query. When measuring in practice, count SQL statements and service calls, not just how many times the `@BatchMapping` method runs.

With 100 books and 100 distinct authors, the single-item approach can generate 101 queries; batching can generate 2 queries if all books fit in one batch with no chunk limit. If 100 books only reference 5 authors, using `Set<UUID>` also reduces the key set sent to the database to 5 IDs.

## 9. Step 5 — Test the GraphQL Results

Tests must verify two things simultaneously: the returned data is correct and the number of backend calls decreases. Checking only the response is insufficient because an N+1 resolver can still return completely accurate data.

With `GraphQlTester`, configure a test slice for the controller, provide mocks for `BookService` and `AuthorService`, and send the `BooksWithAuthors` query. The annotation name for declaring mocks depends on your Spring Boot/Spring Framework version (`@MockitoBean` in newer versions or `@MockBean` in earlier versions).

Example of the core assertion:

```java
@Test
void resolvesAuthorsInBatch() {
    // bookService returns B-101 -> A-01, B-102 -> A-02, B-103 -> A-01.
    // authorService.findByIds(Set.of(A01, A02)) returns two authors.

    graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author { id name }
                }
            }
            """)
            .execute()
            .path("books")
            .entityList(BookGraphQlView.class);

    then(authorService).should(times(1))
            .findByIds(Set.of(A01, A02));
}
```

`BookGraphQlView` is a test DTO with fields `id`, `title`, and `author`; `A01`, `A02` are test UUID fixtures. Complete the assertions on the DTO to confirm B-101 and B-103 receive the same author A-01, and B-102 receives A-02. If the test uses Mockito, you can use `ArgumentCaptor` to inspect the exact set of IDs passed to the service.

With the old resolver version, verify that `findById` is called once per book with a valid `authorId`. After switching to batching, verify that `findByIds` is called according to the actual batch count and there are no repeated `findById` calls per book. Do not hardcode an expectation of a single batch for tests whose size exceeds the configured batch limit.

## 10. Step 6 — Handle Edge Cases

### Book Without authorId

For example, B-104 has `authorId = null`. Do not include `null` in the query ID set. When building the result map, still add key B-104 with value `null`. This ensures the `author` field returns `null` according to the declared schema.

### Author Not Found

If a book references a non-existent ID, `authors.get(id)` returns `null`. You must decide whether this is acceptable missing data, a data integrity error, or a situation requiring a GraphQL error. That decision must align with SDL nullability and business rules.

### Empty Book List

If `books` is empty, the ID set is also empty. `findByIds` returns `Map.of()` without querying the database. The batch resolver returns an empty map.

### Multiple Books by the Same Author

`Set<UUID>` deduplicates IDs so the author is queried once. When building results, each book still gets its own entry pointing to the same author object. Do not map results by index position in the ID list because database query ordering is not guaranteed.

### Partial Data Not Permitted to View

If permission to view authors depends on tenant or user, enforce that condition inside `findByIds` or the invoked service. Do not load all authors by ID and return data without checking access scope. If an author is not permitted to be viewed, decide whether to return `null` or emit a field error per authorization policy and schema.

## 11. Step 7 — Preserve Tenant and Security Boundaries

Batching groups multiple source objects within a single execution, so the service must process the key set as a unit while still preserving all access conditions. For example, instead of merely querying:

```sql
SELECT id, name
FROM author
WHERE id IN (:ids);
```

a multi-tenant application needs tenant scoping:

```sql
SELECT id, name
FROM author
WHERE tenant_id = :tenantId
  AND id IN (:ids);
```

`tenantId` must come from the server-authenticated security context; never trust a value sent by the client in the query. If access rights depend on individual authors, the service must apply those rules to every ID in the batch.

Do not use a static map cache or a cache shared across users for tenant/authorization-dependent results. GraphQL's DataLoader is scoped to request execution; still be careful if you manually configure loaders, caches, or singleton services. Do not put sensitive data into metric labels or query key logs.

## 12. Step 8 — Handle Large Batches and Pagination

Batching reduces call counts but does not remove database limits. An `IN` clause with too many parameters can exceed driver/database limits or produce poor query plans. You should:

- Limit page size in the root query resolver.
- Configure batch size limits suited to your database and downstream services if your Spring for GraphQL version/configuration supports it.
- Split the ID set into chunks when the service needs to control the number of bind parameters.
- Monitor keys per batch, query duration, and batch count per operation.
- Avoid returning unbounded lists and expecting DataLoader to absorb the entire cost.

Example of splitting an ID set into chunks in the service (use only when necessary):

```java
Map<UUID, Author> findByIdsInChunks(Collection<UUID> ids, int chunkSize) {
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be greater than zero");
    }
    if (ids.isEmpty()) {
        return Map.of();
    }

    Map<UUID, Author> result = new HashMap<>();
    List<UUID> allIds = new ArrayList<>(ids);

    for (int start = 0; start < allIds.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, allIds.size());
        List<UUID> chunk = allIds.subList(start, end);
        for (Author author : authorRepository.findByIdIn(chunk)) {
            result.put(author.id(), author);
        }
    }

    return result;
}
```

`chunkSize` must be a configuration grounded in system limits and query parameter limits, and validated to be greater than 0. Measure the resulting query count after chunking to ensure limits are handled in a controlled manner.

## 13. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping both `@SchemaMapping` and `@BatchMapping` for `Book.author` | Two data fetchers compete for one field or configuration becomes ambiguous | Replace the old resolver with the batch resolver |
| Calling `findById` inside the batch loop | N+1 still persists at the service layer | Use a query API that accepts a set of IDs |
| Returning `List<Author>` in repository order | Authors may be attached to the wrong books if ordering differs | Return `Map<Book, Author>` or explicitly guarantee ordering per the loader contract |
| Not deduplicating IDs | Unnecessary repeated key queries | Collect IDs into a `Set` |
| Using `Map.of(book, null)` | Java throws `NullPointerException` | Use `HashMap` if null values are needed or handle nulls by another policy |
| Omitting tenant filter | Risk of cross-tenant data leakage | Apply tenant and authorization checks inside the batch service |
| Unbounded lists | Oversized batches, expensive responses and queries | Use pagination and batch limits |
| Measuring only total latency | Cannot tell whether query count actually decreased | Measure SQL count, batch size, service call count, and traces |

## 14. Extended Practice

After finishing the book and author example, implement these additional scenarios on your own:

1. A book has multiple categories. Write `@BatchMapping` for `Book.categories` and return `Map<Book, List<Category>>`.
2. An author may be hidden per tenant. Ensure the batch does not return author details outside the current tenant.
3. A page has 500 books. Set a page size and batch limit; measure the number of queries when the batch is split.
4. Some books have a non-existent `authorId`. Define the response and GraphQL error according to schema nullability.
5. Compare `@BatchMapping` against explicit DataLoader registration via `BatchLoaderRegistry`. Choose the appropriate approach when batch logic is complex or a loader needs to be reused.

## 15. Practice Completion Criteria

- [ ] The GraphQL query returns the book list with accurate author information.
- [ ] The query count of the single-item resolver was observed and the N+1 pattern confirmed.
- [ ] `@BatchMapping` is properly bound to `Book.author`.
- [ ] The service queries by a set of IDs and deduplicates IDs.
- [ ] The result map pairs the right author with each book, independent of database ordering.
- [ ] Null IDs, missing IDs, and empty lists are handled explicitly.
- [ ] Tenancy and authorization are enforced inside the batch service.
- [ ] Tests verify both the response and the backend call count.
- [ ] SQL count, batch size, and latency were re-measured with the same query shape.

## Self-Check Questions

**Why doesn't `@BatchMapping` automatically fix N+1 if the service still calls `findById` for each element?** Because the annotation only gathers source objects into one batch resolver invocation; data access is still determined by application code. If the code continues looping and querying one by one, N+1 simply moves inside the batch method.

**Why does the example return `Map<Book, Author>` instead of `List<Author>`?** A map directly associates each source `Book` with its corresponding result. An `IN` query does not guarantee returned record order, so you cannot assume the author's position in a list matches the book's position.

**Is DataLoader a shared cache across all requests?** No. DataLoader is used to batch and manage data loading within a GraphQL execution. Do not treat it as a distributed cache or a mechanism for sharing data across users.

**How do you prove N+1 is fixed?** Use the same query shape and representative data, measure SQL/backend call counts before and after, check batch sizes, and confirm the response remains accurate. Lower latency in a single run is not sufficient proof on its own.

When finished, you should see author data accesses scale with a reasonable number of batches rather than per book, while every field continues to respect the schema, tenancy, and access permissions.
