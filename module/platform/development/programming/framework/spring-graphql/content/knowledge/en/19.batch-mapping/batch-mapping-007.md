# Batch mapping with Mono

## 1. Why is Batch Mapping needed?

In GraphQL, a query can fetch a list of objects and also select relational fields for each object. For example, a client fetches 30 books and requests the author information as well:

```graphql
query BookCatalog {
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

The `Query.books` resolver can load 30 books with a single query. If the `Book.author` field calls the repository separately for each book, the server may execute 30 additional author queries. This is the N+1 problem.

Spring for GraphQL provides `@BatchMapping` to group source objects of the same field into a single batch execution. When used with Reactor, the method can return `Mono<Map<Source, Target>>` or `Mono<List<Target>>`. This allows the application to perform one query for multiple related records and return results to GraphQL matched to each source object.

`Mono` represents an asynchronous result that can emit at most one value. In Batch Mapping, that value is typically the entire map or list for a batch, rather than a separate `Mono` for each parent object.

## 2. How does `@BatchMapping` work?

For a nested field, Spring for GraphQL would normally invoke a `@SchemaMapping` once per source object. `@BatchMapping` replaces those individual calls with a batch function:

1. GraphQL resolves the parent field, e.g., `Query.books`, and obtains a list of `Book`s.
2. Requests for the `Book.author` field are collected through a DataLoader registered by Spring.
3. When the batch is dispatched, Spring calls the `@BatchMapping` method with the list of `Book`s needing resolution.
4. The method executes a bulk query and returns a `Mono` containing the result map or list.
5. Spring/DataLoader matches each result to its corresponding source object and continues building the GraphQL response.

```mermaid
flowchart TD
    A[Query books] --> B[List of Books]
    B --> C[Book.author requests]
    C --> D[DataLoader collects source objects]
    D --> E[@BatchMapping receives List<Book>]
    E --> F[Service loads multiple Authors]
    F --> G[Mono emits Map or List]
    G --> H[Match Author to each Book]
    H --> I[GraphQL response]
```

The key point is that the batch method receives multiple parent objects in a single invocation. Thus, the backend query can use a `WHERE id IN (...)` clause or a bulk lookup mechanism instead of one query per parent.

## 3. Declaring the schema and Java models

Suppose each book references an author via `authorId`:

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

The `Book.author` field is nullable because the example allows books without an author or cases where the author record no longer exists. If business rules guarantee the relationship is always valid, you can declare `Author!`; the batch mapping must then always supply a valid author for every book.

Illustrative Java models:

```java
public record Book(
    String id,
    String title,
    String authorId) {
}

public record Author(
    String id,
    String name) {
}
```

Records are used to keep the example concise. In real applications, `Book` and `Author` can be domain objects or DTOs created from persistence entities.

## 4. Writing a Batch Mapping returning `Mono<Map<Book, Author>>`

When the service can load authors by a set of IDs, a clear approach is accepting the book list, collecting non-null `authorId`s, loading all authors, and building a map from each `Book` to its `Author`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .filter(id -> id != null)
            .collect(Collectors.toSet());

        return authorQueryService.findAllByIds(authorIds)
            .map(authorsById -> books.stream()
                .filter(book -> book.authorId() != null
                    && authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                    Function.identity(),
                    book -> authorsById.get(book.authorId())
                )));
    }
}
```

The service can return `Mono<Map<String, Author>>`:

```java
public interface AuthorQueryService {
    Mono<Map<String, Author>> findAllByIds(Set<String> authorIds);
}
```

The `author` method returns `Mono<Map<Book, Author>>`. The map key is the `Book` source object; the value is the result for the `author` field. Spring for GraphQL uses the key-value mapping to assign the right author to each book.

In the example, if a book has no `authorId` or no corresponding author is found, that book does not appear in the map. With mapped batch loading, a key without an entry receives a null result. This aligns with the nullable SDL `author: Author`.

## 5. Why does `Mono` wrap the entire batch?

The following signature means one batch execution emits one map when data is ready:

```java
Mono<Map<Book, Author>> author(List<Book> books)
```

Each part means:

- `List<Book>`: all source objects to resolve in the current batch.
- `Mono<...>`: the result is delivered asynchronously and emitted at most once.
- `Map<Book, Author>`: results for multiple source objects, matched by key.

Do not write a method returning `Mono<Author>` when accepting `List<Book>` if the goal is to provide results for the whole batch. A `Mono<Author>` only represents a single value, which cannot map relationships for multiple books.

Likewise, do not subscribe manually inside the controller:

```java
// Avoid: subscribing manually detaches processing from GraphQL execution.
Mono<Map<Book, Author>> result = authorQueryService.findAllByIds(authorIds);
result.subscribe();
```

Return the publisher directly to Spring for GraphQL:

```java
return authorQueryService.findAllByIds(authorIds)
    .map(authorsById -> mapBooksToAuthors(books, authorsById));
```

Spring for GraphQL and Reactor manage subscription and coordinate results with GraphQL execution. Calling `subscribe()` manually can allow the response to complete before data is ready and break error propagation.

## 6. Returning `Mono<List<Author>>` when matching by order

Besides a map, Batch Mapping can return a list of results. In that case, the list must have the exact same size and order as the input list of source objects.

Example:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<List<Author>> author(List<Book> books) {
    List<String> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorQueryService.findAllByIdsInOrder(authorIds);
}
```

The `findAllByIdsInOrder` service must return a `List<Author>` with the same number of elements as `books`, where the element at index `i` is the author of `books.get(i)`. If `authorId` is null or an author does not exist, the corresponding element must be `null` if the field is nullable. The service must preserve slots for missing keys rather than omitting them from the list.

Example source list:

```text
books:   [Book-A, Book-B, Book-C]
authors: [Author-A, null, Author-C]
```

GraphQL matches by position: `Book-A` receives `Author-A`, `Book-B` receives null, and `Book-C` receives `Author-C`.

Do not return a list containing only the found authors if any key is missing. For instance, `[Author-A, Author-C]` with two elements will no longer align with three source objects. If the backend cannot preserve order, `Mono<Map<Book, Author>>` is usually safer and easier to verify.

## 7. Choosing Map or List?

| Criterion | `Mono<Map<Book, Author>>` | `Mono<List<Author>>` |
| --- | --- | --- |
| Matching strategy | By source object as key | By position in the list |
| Backend ordering | Order not required if map keys are exact | Must reconstruct exact order |
| Missing data | Omit key from map so corresponding result is null | Place null at exact index |
| Main risk | Map key does not match source object | Wrong order or wrong element count |
| Best suited for | Repository returning an ID map or unordered results | Backend already returning results in exact input order |

Prefer Map when querying the backend with `IN (...)`, because databases normally do not guarantee result order without `ORDER BY`. Choose List when the service can guarantee results in exact input order and positional alignment is explicitly tested.

## 8. Map keys must match source objects

With `Mono<Map<Book, Author>>`, map keys must match the `Book` instances passed into the batch method. Java maps use `equals` and `hashCode` for key lookup, so understand how domain objects define these two methods.

Java records automatically generate `equals` and `hashCode` based on record components. If using JPA entities, avoid arbitrarily including mutable fields in `equals` and `hashCode`, as modifying a field after inserting an entity into a map can break lookup. Choose a stable domain equality strategy.

Example building the map directly from the exact source instances:

```java
Map<Book, Author> result = new LinkedHashMap<>();

for (Book book : books) {
    Author author = authorsById.get(book.authorId());
    if (author != null) {
        result.put(book, author);
    }
}
```

Here the map uses the exact `Book` objects received in the batch. When source objects are entities with proxies or complex equality, test key lookup and consider using a stable DTO/record as the GraphQL source.

## 9. Handling empty batches and missing data

A batch may contain no source objects, or the backend may find no data for any key. In such cases, the well-typed result is still an empty map or list:

```java
if (books.isEmpty()) {
    return Mono.just(Map.of());
}
```

With a reactive service, you can also let the service accept an empty ID set and return `Mono.just(Map.of())`. Do not use `Mono.empty()` to represent a batch with no results. `Mono.empty()` means the publisher completed without emitting a batch value; that is not the same contract as an empty map.

For individual keys missing data:

- If the SDL field is nullable, omit the key from the map so the corresponding field result is null.
- If the field is non-null, a missing value triggers a GraphQL error and null propagation.
- If missing data is an integrity violation, raise an explicit business error rather than silently returning a map missing the key.
- If the parent's `authorId` is null, do not include null in the query key set.

Do not convert database or network errors into `Mono.just(Map.of())`. An empty map indicates a successful query that found no records; infrastructure errors must propagate as error signals so GraphQL error handling processes them properly.

## 10. Using reactive repositories with Mono

The ideal scenario is when both the service and repository already support reactive execution. The batch method can then compose publishers without blocking:

```java
public interface ReactiveAuthorRepository {
    Mono<List<Author>> findAllByIdIn(Set<String> ids);
}
```

The service converts the result list into a map by ID:

```java
@Service
public class AuthorQueryService {

    private final ReactiveAuthorRepository repository;

    public AuthorQueryService(ReactiveAuthorRepository repository) {
        this.repository = repository;
    }

    public Mono<Map<String, Author>> findAllByIds(Set<String> ids) {
        if (ids.isEmpty()) {
            return Mono.just(Map.of());
        }

        return repository.findAllByIdIn(ids)
            .map(authors -> authors.stream()
                .collect(Collectors.toMap(
                    Author::id,
                    Function.identity()
                )));
    }
}
```

Batch mapping composes the result:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    Set<String> ids = books.stream()
        .map(Book::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

    return authorQueryService.findAllByIds(ids)
        .map(authorsById -> toBookAuthorMap(books, authorsById));
}
```

Do not call `.block()` inside a Batch Mapping method to wait on a reactive repository. Doing so blocks the thread and negates the benefits of a reactive pipeline; in some execution contexts it can cause deadlocks or reduce throughput.

## 11. When the service uses blocking JPA/JDBC

Not every Spring for GraphQL project uses a reactive database. If the service uses Spring Data JPA or JDBC, repository queries are blocking. Wrapping one in `Mono.fromCallable` only creates a deferred publisher; it does not make the call non-blocking.

If you need to return `Mono` while running in a reactive execution, offload blocking work to the bounded elastic scheduler:

```java
return Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    .subscribeOn(Schedulers.boundedElastic());
```

Consider your application's thread model. With an MVC stack and blocking repositories, a synchronous batch method returning `Map<Book, Author>` may be used if it fits your execution configuration. With a reactive stack, do not run JPA/JDBC directly on event-loop threads.

Do not use `.block()` to turn a reactive service into a synchronous result inside a resolver. Choose a consistent approach aligned with your data access technology and GraphQL configuration.

## 12. `@BatchMapping` integrates DataLoader automatically

`@BatchMapping` is Spring for GraphQL's shortcut for registering a batch loader and data fetcher for a field. The application does not need to manually create a `DataLoader` or register with `BatchLoaderRegistry` for this straightforward batch case.

Spring uses the source object as the batch loader's key. When the method returns a Map, the map must map source objects to field values. When the method returns a List, results must preserve the exact order of source objects.

Therefore, do not write another `@SchemaMapping` for the same `Book.author` field when `@BatchMapping` is already present. Two methods registering the same field can cause mapping conflicts or unclear resolver ownership.

If you need an ID-keyed DataLoader shared across multiple fields, or need custom keys, custom names, or `DataLoaderOptions`, consider registering via `BatchLoaderRegistry` and having `@SchemaMapping` call `DataLoader.load`. Choose one mechanism per type/field pair.

## 13. Tuning batch size

A query may request a very large number of source objects. An overly large batch can produce an `IN` query with thousands of parameters, increase memory usage, and overload the database. Spring for GraphQL supports limiting `@BatchMapping` batch size via the `maxBatchSize` attribute in supported versions:

```java
@BatchMapping(
    typeName = "Book",
    field = "author",
    maxBatchSize = 100
)
public Mono<Map<Book, Author>> author(List<Book> books) {
    // Load authors for at most one configured batch.
    return loadAuthors(books);
}
```

When the number of source objects exceeds the limit, DataLoader can split them into multiple batches. Therefore, do not assume a large operation always invokes the batch method exactly once. Choose the limit based on bind parameter limits, response size, query duration, and database capacity.

If the version of Spring for GraphQL you are using does not yet support `maxBatchSize` on `@BatchMapping`, check the API for that version and configure batch size through the corresponding DataLoader mechanism. Do not copy attributes from another version's documentation without verifying your actual dependency.

## 14. Testing Batch Mapping with `GraphQlTester`

Tests should verify both that the response is accurate and that the batch function actually groups multiple source objects. Example operation:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesAuthorsForBooks() {
        graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

The example assumes the test context contains fixture data and the service returns the author `Nguyen An` for the first book.

To verify batching rather than only checking the response, use a spy or counter on the service:

- Prepare multiple books with shared and distinct `authorId`s.
- Send a single query fetching the list and the `author` field.
- Verify the service is called with the collected set of IDs rather than once per book.
- If batch size is limited, verify the call count matches the actual batches.
- Verify ordering and source-target relationships are not swapped.

Cases to include:

- Empty source list.
- All keys find data.
- Some keys have no data.
- Parent has a null key.
- Backend throws an error.
- Nullable and non-null fields react properly when results are missing.
- Batch is split due to `maxBatchSize`.
- Publisher is cancelled or the request ends before completion if the application has cancellation scenarios to handle.

## 15. Common pitfalls when using Mono in Batch Mapping

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Field is not batch-resolved | `@BatchMapping` type/field names do not match SDL | Explicitly declare `typeName` and `field` |
| Duplicate DataFetcher registered | Same field has both `@BatchMapping` and `@SchemaMapping` | Choose one mapping to own the field |
| Field is always null | Map uses keys other than source objects or entries are missing | Use the exact source objects as keys and check the map |
| Results assigned to wrong parent | List returned with wrong order or element count | Use a map or order the list to match exact source order |
| Query does not complete | Publisher emits no value or is blocked | Return a `Mono` emitting the map/list and do not call subscribe/block manually |
| Empty batch fails | Returning `Mono.empty()` instead of an empty map/list | Return `Mono.just(Map.of())` or `Mono.just(List.of())` |
| Thread is blocked | Running blocking JPA/JDBC on a reactive thread | Use a matching synchronous stack or offload blocking work to a scheduler |
| Database still called many times | Batch function calls repository in a loop | Use a single bulk query by key set |
| Nullable field returns error | SDL declares non-null or backend error is converted improperly | Check nullability and separate missing data from infrastructure errors |
| Batch is too large | No limit on source object count | Configure `maxBatchSize` if supported and paginate the parent query |

## 16. Checklist for implementing Batch Mapping with Mono

- [ ] Identify relational fields at risk of N+1.
- [ ] Declare the exact source type and field in `@BatchMapping`.
- [ ] Method accepts `List<Source>` and returns `Mono<Map<Source, Target>>` or `Mono<List<Target>>`.
- [ ] If returning a Map, keys match source objects and have stable equality.
- [ ] If returning a List, size and order match the input source list.
- [ ] Return an empty map/list via `Mono.just(...)` when there are no batch results.
- [ ] Do not use `Mono.empty()` to represent an empty collection.
- [ ] Do not call `subscribe()` or `block()` inside the resolver.
- [ ] Do not run blocking JPA/JDBC directly on the reactive event loop.
- [ ] Handle missing keys in accordance with SDL nullability.
- [ ] Do not register another resolver for the same field.
- [ ] Limit batch size and paginate parent fields when needed.
- [ ] Test responses, key mapping, ordering, and backend call counts.

## Conclusion

`@BatchMapping` combined with `Mono` allows Spring for GraphQL to process multiple source objects in a single batch and return results asynchronously. With `Mono<Map<Source, Target>>`, each source object is matched to its value via key; with `Mono<List<Target>>`, the list must preserve the exact count and order of the source list.

Use a Map when the backend returns data by key and ordering is not guaranteed. Use a List when the service can preserve corresponding order. Return the publisher for Spring to manage without subscribing or blocking manually; distinguish missing data from infrastructure errors, pick the right nullability in the SDL, and test query counts to confirm N+1 has been reduced. For large batches, limit batch size and paginate parent queries to maintain stable performance.

## References

- [Spring for GraphQL — Annotated Controllers: Batch Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping.batch-mapping)
- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphql-datafetcher.batch-loading)
- [Project Reactor — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
