# What is DataLoader in GraphQL?

DataLoader is a mechanism for batching multiple individual data-loading calls into one or a few batch loads, while caching results within the scope of a single execution. It is especially useful when GraphQL resolves nested fields across multiple parent objects and each child field needs to access related data. If each resolver independently calls a repository for every object, the application easily runs into the N+1 problem; DataLoader batches the keys so a service or repository can query them in bulk.

In Spring for GraphQL, DataLoader integrates with GraphQL Java through `DataLoaderRegistry` and `BatchLoaderRegistry`. Spring creates a registry per GraphQL request and provides the registered DataLoaders to resolvers. You can also use `@BatchMapping` as a concise declarative way to handle fields that require batch loading.

After this lesson, you will be able to:

- Understand how DataLoader solves the N+1 problem.
- Grasp batching, caching, and dispatching mechanisms.
- Distinguish between a batch loader returning an ordered list and a mapped batch loader returning a key-value map.
- Register a DataLoader using `BatchLoaderRegistry` in Spring for GraphQL.
- Use a DataLoader in `@SchemaMapping` to load relational data.
- Understand per-request cache scope and the limitations of DataLoader.
- Know when to use DataLoader, `@BatchMapping`, or join/projection queries.

## 1. The N+1 problem in GraphQL

Suppose a schema has books and authors:

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

The client requests a list of books along with each author's name:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

A simple implementation has the `Query.books` resolver fetch all books, and then the `Book.author` resolver calls the repository to find the author for each book:

```java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}

@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.authorId()).orElse(null);
}
```

If there are 100 books, the application may execute:

- 1 query to fetch the list of books.
- 100 queries to fetch the author, one per book.

That totals 101 database accesses in the worst case. This is the N+1 problem: one initial query fetches N objects, followed by N additional queries to load related data.

The actual query count also depends on caching, data relationships, how the repository behaves, and how many authors overlap. However, a resolver that calls a repository separately for each parent object still risks scaling database accesses with the number of elements.

## 2. How does DataLoader solve N+1?

Instead of loading immediately when a resolver requests a key, DataLoader records the key in a queue. When GraphQL execution reaches the dispatch point, DataLoader gathers the pending keys and invokes the batch loader once. The batch loader receives the set of keys, queries the data in bulk, and returns the corresponding results.

For example, 100 books have `authorId` values `1`, `2`, `3`, ... The resolver calls `load(authorId)` for each book. DataLoader can combine the keys into a batch `[1, 2, 3, ...]`; the service runs a query such as `WHERE id IN (...)` and returns the matching authors.

```mermaid
flowchart TD
    A[Query fetching list of Books] --> B[GraphQL resolves Book.author for each Book]
    B --> C[DataLoader.load(authorId)]
    C --> D[Enqueue key]
    D --> E[Dispatch batch]
    E --> F[BatchLoader receives multiple authorIds]
    F --> G[Service queries in batch]
    G --> H[Return results by key]
    H --> I[GraphQL continues resolving Author.name]
```

If the backend performs an efficient single query for the entire batch, the number of accesses can drop from 1 + N down to 1 + the number of batches. With 100 books in one batch, the example above may only need one query for books and one query for authors.

DataLoader does not write optimal SQL by itself. It only batches requests and manages caching; the batch loader/service must actually query multiple keys at once. If the batch loader still loops over each key and calls the repository once per key, N+1 remains.

## 3. Two core capabilities: batching and caching

DataLoader generally provides two complementary capabilities:

**Batching** combines multiple `load(key)` requests occurring within an execution window into a single call to the batch loader. Rather than calling the service per key, the application calls it once with multiple keys.

**Caching** stores results by key within the DataLoader instance. If the same key is requested multiple times within the same loader scope, DataLoader can reuse the already-loaded or in-flight result, avoiding duplicate queries.

For example, if multiple books share `authorId = 7`, the resolver may call `load(7)` multiple times, yet DataLoader caches by key by default so author 7 is not loaded repeatedly within the same request.

| Capability | Effect | Thing to remember |
| --- | --- | --- |
| Batching | Reduces service/database calls | The batch loader must query multiple keys at once |
| Caching | Avoids loading the same key repeatedly | Cache belongs to the DataLoader instance and must match request scope |

Batching and caching are not the same thing. You can disable caching and still batch; you can also use caching to avoid duplicate keys even when a batch has only one element. The goals and configurations of these two features should be understood separately.

## 4. DataLoader in GraphQL Java

GraphQL Java uses the `java-dataloader` library. A `DataLoader<K, V>` accepts keys of type `K` and returns results of type `V` asynchronously, typically as a `CompletableFuture<V>`.

Example usage:

```java
CompletableFuture<Author> authorFuture = authorDataLoader.load(book.authorId());
```

`load` does not necessarily query the database on that exact line of code. It registers the key with DataLoader and returns a future. When GraphQL dispatches the loader, the batch function is invoked with multiple keys. Once the future completes, GraphQL continues resolving the child fields of `Author`.

DataLoader is commonly used in resolvers for relational fields, such as `Book.author`, `Order.customer`, or `Product.category`. Resolvers can still return `CompletableFuture`, `CompletionStage`, or reactive types compatible with Spring for GraphQL.

Do not call `join()` or `get()` on the future inside a resolver to wait synchronously for the result. Doing so blocks the thread and defeats asynchronous execution. Return the future for the GraphQL engine to handle.

## 5. BatchLoader returning a List: preserving exact order

One style of batch loader accepts a list of keys and returns a list of values in the same order:

```java
BatchLoader<Long, Author> batchLoader = authorIds ->
        authorService.findAuthorsInOrderAsync(authorIds);
```

Here `findAuthorsInOrderAsync` can return `CompletionStage<List<Author>>`; its internal implementation must guarantee the same order as the key list.

If the input keys are `[10, 20, 30]`, the result must have matching positions:

| Index | Key | Value at the same index |
| --- | --- | --- |
| 0 | 10 | Author with ID 10 |
| 1 | 20 | Author with ID 20 |
| 2 | 30 | Author with ID 30 |

A list-based batch loader must guarantee that the result has the exact same element count and order as the key list per the `BatchLoader` contract. If the repository returns results in a different order than the input, you must reconstruct the order before returning the list.

For example:

```java
public List<Author> findAuthorsInOrder(List<Long> authorIds) {
    Iterable<Author> foundAuthors = authorRepository.findAllById(authorIds);
    Map<Long, Author> byId = StreamSupport.stream(foundAuthors.spliterator(), false)
            .collect(Collectors.toMap(Author::id, Function.identity()));

    return authorIds.stream()
            .map(byId::get)
            .toList();
}
```

If a key has no record, the list may contain `null` at the corresponding position when the data type permits it; if you do not want to return `null`, define clear error or missing-result semantics.

## 6. MappedBatchLoader: returning a Map by key

When a repository does not guarantee order or some keys may not be found, a mapped batch loader is often easier to use. It takes a set of keys and returns a map from key to value:

```java
MappedBatchLoader<Long, Author> mappedBatchLoader = authorIds ->
        authorService.findAuthorsByIdsAsync(authorIds);
```

In this example, `findAuthorsByIdsAsync` returns `CompletionStage<Map<Long, Author>>`.

Example map:

```java
{
    10L -> Author(10, "An"),
    30L -> Author(30, "Binh")
}
```

If key `20` is absent from the map, DataLoader has no value for that key; the resolver receives an absent result according to the loader's semantics, typically `null`. This approach does not require the map to preserve input list ordering because each result is explicitly bound to its key.

A mapped loader is suitable when:

- The repository returns data in its own order.
- Some keys might not exist.
- Results need to be matched unambiguously by ID.
- The batch query returns a map or data that needs to be grouped by key.

Service example:

```java
public Map<Long, Author> findAuthorsByIds(Set<Long> authorIds) {
    Iterable<Author> foundAuthors = authorRepository.findAllById(authorIds);
    return StreamSupport.stream(foundAuthors.spliterator(), false)
            .collect(Collectors.toMap(Author::id, Function.identity()));
}
```

The service should handle duplicate IDs, missing data, and access permissions according to the application's contract.

## 7. DataLoaderRegistry and cache scope

GraphQL Java manages DataLoaders through `DataLoaderRegistry`. The registry holds named DataLoaders and is bound to a single GraphQL execution. Resolvers obtain a loader from the registry by its corresponding name or through the framework's integration mechanism.

The scope of the registry is critical:

- DataLoader maintains a per-instance cache.
- Sharing a single instance across multiple requests can cause data from an earlier request to affect subsequent requests.
- If the cache holds user- or tenant-dependent data, a global cache can leak data.
- Creating a registry/loader per request scopes the cache to one execution and preserves the proper security context.

In Spring for GraphQL, `BatchLoaderRegistry` is designed to register batch loaders and instantiate corresponding DataLoaders in each request's `DataLoaderRegistry`. This allows controllers to accept a `DataLoader` as a method parameter without manually managing a registry per request.

Do not create a static `DataLoader` or singleton cache holding user data. A request-scoped cache does not replace an application cache or database cache; it only prevents duplicate loads within the same GraphQL execution.

## 8. Registering a DataLoader with BatchLoaderRegistry

Spring for GraphQL provides `BatchLoaderRegistry` to register loaders by key/value type pair. For example, loading authors by ID:

```java
@Configuration
public class GraphQlBatchConfiguration {

    public GraphQlBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAuthorsByIds(authorIds));
    }
}
```

In this example, `findAuthorsByIds` returns `Mono<Map<Long, Author>>` or a reactive type matching the mapped batch loader signature used by your version of Spring for GraphQL. If the service is blocking, use an appropriate adapter to isolate blocking I/O; do not execute blocking queries directly on the WebFlux event loop.

`BatchLoaderRegistry` registers the loader so Spring creates a DataLoader in each request's registry. It also supports passing context from the GraphQL request to the batch loader, which is useful when data loading depends on authenticated user details or tenant context. Do not take tenant/user IDs from arbitrary client-supplied keys if that information must come from the security context.

Spring Boot typically auto-configures a `BatchLoaderRegistry` bean. You can inject that bean into a configuration or component to register loaders; there is no need to create a global registry shared across all requests.

## 9. Using DataLoader in @SchemaMapping

After registering the loader, the `Book.author` field resolver can accept `DataLoader<Long, Author>`:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorDataLoader) {

        return authorDataLoader.load(book.authorId());
    }
}
```

Spring for GraphQL supplies the matching DataLoader from the request registry to the method argument. Each resolver calls `load` with the book's author ID. The keys are queued, and the previously registered batch loader calls the service once for the group of IDs.

The client queries as usual:

```graphql
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
```

No GraphQL schema changes are needed just because a DataLoader is added. DataLoader is a server-side implementation mechanism; the `Book.author` field contract remains unchanged.

## 10. @BatchMapping as a convenient batch declaration

Spring for GraphQL provides `@BatchMapping` to implement batch loading directly for a field. Instead of manually configuring `BatchLoaderRegistry` and injecting `DataLoader` into `@SchemaMapping`, the method receives a list of source objects and returns a map of results per source:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        return authorService.findAuthorsByIds(authorIds)
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();
                    for (Book book : books) {
                        result.put(book, authorsById.get(book.authorId()));
                    }
                    return result;
                });
    }
}
```

Spring for GraphQL uses `@BatchMapping` to register a batch loader for the corresponding field. The returned map associates each source object with its resolved field value. If returning `Flux<V>` instead of a map, you must adhere to the ordering rules matching the source list per the `@BatchMapping` API.

`@BatchMapping` is well suited when batch logic serves only one specific field. Use `BatchLoaderRegistry` directly when you want to reuse a key-based loader across multiple resolvers or need explicit control over `DataLoader.load(...)` calls.

Do not register both `@SchemaMapping` and `@BatchMapping` for the same field coordinate without a clear intent; both provide a data fetcher for that field and can conflict.

## 11. Cache keys and cache behavior

By default, DataLoader caches by key within the loader instance. Therefore, the key type must implement `equals` and `hashCode` properly. For IDs such as `Long`, `String`, or `UUID`, the semantics are usually straightforward. If using an object as a key, ensure equality is stable and does not depend on mutable fields.

Several scenarios to consider:

- The same key is loaded multiple times in a request: the cache can share the result.
- The same key yields results that depend on locale, tenant, or permissions: include that information in the key or design an appropriate loader/cache scope; never share results across the wrong context.
- Data changes between mutations within the same request: the cache may hold stale values; consider clearing or priming the key after a mutation updates data.
- You do not want caching inside the loader: you can configure DataLoader with caching disabled or use an appropriate cache map, while batching still works.

DataLoader caches normally live for only a single request, so they are not a place for long-lived caching. If cross-request caching is needed, use an application cache with explicit TTL, invalidation, and access-permission partitioning.

## 12. Dispatch and asynchronicity

DataLoader batches `load` calls before the batch function is invoked. GraphQL Java coordinates dispatching during execution to wait for and resolve the futures. When integrated via Spring for GraphQL, resolvers typically just call `load` and return the future; do not manually call `dispatch()` inside every resolver.

Example of what not to do:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId()).join();
}
```

`join()` blocks the thread waiting for the result. This negates asynchronous benefits and can cause bottlenecks when multiple fields are waiting on a batch.

Return the future instead:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

If the service returns `Mono`, Spring for GraphQL supports reactive types at the appropriate boundaries. Keep the pipeline non-blocking in WebFlux and never call `.block()` inside a resolver.

## 13. DataLoader does not replace every optimization technique

DataLoader is very useful for relationships loaded from nested resolvers, yet it is not always the best option.

| Scenario | Solution to consider |
| --- | --- |
| A list of books each needing its author by ID | DataLoader or `@BatchMapping` |
| One query can efficiently join authors and authors are always needed | Join fetch or repository projection |
| Client only selects `Book.id` and `Book.title` | Projection selecting only the required fields |
| Field is loaded from a REST service supporting a bulk endpoint | DataLoader calling the bulk endpoint |
| A field is a pure computation on the existing object | Direct resolver, no DataLoader needed |
| Data shared across multiple requests | Dedicated application cache, not request DataLoader cache |

If a single database query can return all data efficiently with a join/projection, adding a DataLoader may add complexity without improving performance. Conversely, if resolvers must load data from multiple sources or only certain fields are selected by clients, DataLoader helps batch calls flexibly.

## 14. Limitations and considerations when using DataLoader

- **Batch size:** an overly large batch can exceed bind parameter limits or produce heavy queries. You can configure a max batch size so the loader splits work into multiple batches.
- **Duplicate keys:** default caching may deduplicate key requests; if you need per-input-position handling, understand how the loader distributes the same value across `load` calls.
- **Missing data:** decide whether a nonexistent key returns `null`, an error, or a dedicated result type.
- **Ordering:** a list batch loader must preserve key order; a mapped loader maps by key.
- **Request context:** batch loaders must receive the proper security/tenant context; do not use a singleton loader holding user state.
- **Batch errors:** if the entire batch function fails, multiple fields depending on the batch may all fail; if per-key errors are required, use DataLoader's per-key error mechanism.
- **Mutations and caching:** if data is modified within the same request, consider clearing or priming the cache so subsequent fields do not read stale values.
- **Batching does not guarantee fast queries:** measure SQL, network calls, batch sizes, and latency to confirm effectiveness.

## 15. Testing DataLoader

You should verify both the output and the number of times the batch service is called. For instance, with a resolver using DataLoader, a test can assert that multiple books are returned with the right authors and that the batch service receives only one group of IDs in a single dispatch.

Scenarios worth testing:

1. Multiple source objects call `load` and are grouped into a batch.
2. Two sources using the same key do not issue duplicate queries when caching is enabled.
3. The batch loader returns results mapped to the right key or in the right order according to the loader type.
4. Nonexistent keys produce results matching the expected semantics.
5. Batch errors are translated into appropriate GraphQL errors.
6. Two different requests do not share a DataLoader cache.
7. Security/tenant context is properly propagated to the batch loader.
8. Mutations modifying data do not leave stale values in the same request's cache.
9. `@BatchMapping` handles the entire source list and returns accurate mappings.

GraphQL client test example:

```java
graphQlTester.document("""
        query {
            books {
                id
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
```

To verify actual batching, use a spy/mock service or an integration test observing how many times the repository is called. Checking only that the response is correct is insufficient to prove that N+1 has been eliminated.

## 16. Common mistakes

- **Using `DataLoader.load` while the batch loader still queries per key:** N+1 persists; the service must provide a bulk query.
- **Returning a list in the wrong order:** values get assigned to the wrong keys; use a mapped loader or restore order before returning.
- **Using an application-wide singleton DataLoader:** cache can leak across requests and users.
- **Calling `join()` or `get()` inside a resolver:** blocks threads and breaks asynchronous execution.
- **Manually dispatching inside each resolver:** can break GraphQL execution's key batching; let the engine coordinate dispatch when using Spring integration.
- **Confusing DataLoader cache with long-term cache:** loader caches are typically request-scoped.
- **Skipping authorization in the batch loader:** a single batch can contain many IDs; each resource must be authorized for the caller/tenant.
- **Using DataLoader for simple computations:** adds complexity with no data-loading benefit.
- **Not updating the cache after a mutation:** fields read after a mutation in the same request may receive stale data.
- **Testing only the output without measuring batch invocations:** fails to confirm that backend calls were reduced.

## 17. Workflow for implementing DataLoader in Spring for GraphQL

When a relational field poses an N+1 risk, follow these steps:

1. Measure how many times the resolver/repository is called using a representative query.
2. Identify the key needed to load related data, such as `authorId`.
3. Create a service/repository method capable of loading multiple keys in one call.
4. Choose a list batch loader if order can be guaranteed, or a mapped batch loader if results should be mapped by key.
5. Register the loader via `BatchLoaderRegistry` so Spring creates a per-request DataLoader.
6. Inject `DataLoader` into `@SchemaMapping` and return the future from `load(key)`.
7. Or use `@BatchMapping` if the batch logic serves only a single field.
8. Ensure the cache stays within request scope and security context is propagated properly.
9. Test data accuracy, ordering, missing keys, errors, and backend call counts.
10. Compare performance before/after; consider a join or projection if more appropriate.

DataLoader coordinates between GraphQL execution and server-side batch loading. It combines multiple data-loading requests, caches results by key within the loader's scope, and allows resolvers to proceed asynchronously. In Spring for GraphQL, `BatchLoaderRegistry` helps register per-request loaders, while `@BatchMapping` provides a concise way to declare batch fields. When the batch loader genuinely queries in bulk, preserves accurate key/value mapping, and is tested for backend call counts, DataLoader resolves N+1 while keeping the GraphQL schema flexible.

## References

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batching)
- [Spring for GraphQL — Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [GraphQL Java — DataLoader](https://www.graphql-java.com/documentation/batching/)
- [java-dataloader — DataLoader concepts and API](https://github.com/graphql-java/java-dataloader)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
