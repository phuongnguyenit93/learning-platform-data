# Batch loader returning Mono

## Objectives

After this lesson, you will be able to:

- Explain how Spring for GraphQL registers batch loading functions using `BatchLoaderRegistry`.
- Distinguish `registerMappedBatchLoader` returning `Mono<Map<K,V>>` from `registerBatchLoader` returning `Flux<V>`.
- Design the contract between the input key set and the result map.
- Use `DataLoader.load()` in `@SchemaMapping` to defer and batch data loads.
- Understand how Spring creates DataLoaders per GraphQL request and shares `GraphQLContext` with batch loaders.
- Handle missing keys, empty publishers, errors, and batch size limits.
- Distinguish `BatchLoaderRegistry` from `@BatchMapping`.
- Test batch loading to verify accurate data and reduced data source calls.

## 1. Why can a batch loader return Mono?

When a GraphQL query fetches a list of objects and then queries a related field on each object, the server easily hits the N+1 problem.

For example, a client fetches 20 books and their authors' names:

~~~graphql
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
~~~

If the `Book.author` resolver calls the database individually for each book, the server may run:

- One query to fetch the list of 20 `Book`s.
- Twenty separate queries to fetch the corresponding `Author`s.

That totals 21 data accesses in the simple case. When lists grow larger or involve multiple nested relationships, the call count can climb rapidly.

DataLoader solves this by deferring each data-loading request, grouping keys together, and calling the batch loader once for a batch of keys. The batch loader can query multiple records in a single call and return the result as a publisher.

In Spring for GraphQL, `BatchLoaderRegistry` supports registering a mapped batch loader with the signature:

~~~java
BiFunction<
        Set<K>,
        BatchLoaderEnvironment,
        Mono<Map<K, V>>
>
~~~

This means:

- The input is the set of keys to load.
- The environment parameter supplies the batch context.
- The output is a `Mono` emitting a map from key to value.

`Mono<Map<K,V>>` fits well when the number of input keys may differ from the number of found values. The map binds each result by key and is therefore independent of database return ordering.

## 2. Distinguishing BatchLoader and MappedBatchLoader

Spring for GraphQL offers two common batch function registration APIs:

| API | Input | Return type | Result rules |
|---|---|---|---|
| `registerBatchLoader` | `List<K>` | `Flux<V>` | Element count and order must match the input key list |
| `registerMappedBatchLoader` | `Set<K>` | `Mono<Map<K,V>>` | Map pairs values with keys, independent of order |

### Ordered batch loader

With `registerBatchLoader`, the batch function receives a list of keys and returns values in the exact matching order.

For example, the keys are:

~~~text
[101, 102, 103]
~~~

The output must be ordered as:

~~~text
[Author(101), Author(102), Author(103)]
~~~

If key 102 is not found, the batch function must preserve that slot with a `null` value per `BatchLoader`'s contract. This can be awkward to handle when the data source returns records in a different order or lacks some records.

### Mapped batch loader

With `registerMappedBatchLoader`, the input is a set of keys and the output is a map:

~~~text
Keys: {101, 102, 103}

Map:
  101 -> Author(101)
  103 -> Author(103)
~~~

Key 102 does not appear in the map because no corresponding `Author` was found. DataLoader can return `null` for that key's load.

This is a convenient choice when querying a database with `WHERE id IN (...)`, because databases do not guarantee returning rows in the order of the input key list.

This lesson focuses on `registerMappedBatchLoader` and `Mono<Map<K,V>>` results.

## 3. Declaring the example schema and models

Suppose an application manages `Book` and `Author`. A `Book` stores `authorId`; `Author` details are loaded from a separate data source.

SDL:

~~~graphql
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
~~~

Java models can use records:

~~~java
public record Book(
        Long id,
        String title,
        Long authorId) {
}

public record Author(
        Long id,
        String name) {
}
~~~

Service loading multiple authors by a collection of IDs:

~~~java
public interface AuthorService {
    Flux<Author> findAllByIds(Collection<Long> authorIds);
}
~~~

Service fetching the list of books used in `Query`:

~~~java
public interface BookService {
    Flux<Book> findAll();
}
~~~

The service returns `Flux<Author>` because a single query can find multiple records. The batch loader collects the `Flux` into a map using `collectMap`, producing `Mono<Map<Long, Author>>`.

## 4. Registering with BatchLoaderRegistry

The Spring Boot GraphQL starter provides a `BatchLoaderRegistry` bean. You can inject the registry into a component or configuration class to register batch loading functions.

For example:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds)
                                .collectMap(Author::id)
                );
    }
}
~~~

Explanation:

- `forTypePair(Long.class, Author.class)` declares `Long` as the key type and `Author` as the value type.
- `registerMappedBatchLoader(...)` registers a function accepting an ID set and returning `Mono<Map<Long, Author>>`.
- `authorIds` is the set of keys gathered by DataLoader in a single dispatch.
- `authorService.findAllByIds(authorIds)` queries the required authors.
- `collectMap(Author::id)` collects `Author`s into a map keyed by ID.

Because `collectMap` emits a map when the `Flux` completes, the batch loader returns a `Mono<Map<Long, Author>>`. If no records are found, `collectMap` still emits an empty map.

### Why use forTypePair?

`forTypePair` declares both the key and value types. Spring uses the value type to assign the default DataLoader name. In the example above, the default name is based on the fully qualified class name of `Author`.

As a result, controllers can declare a `DataLoader<Long, Author>` parameter without normally having to pass a DataLoader name manually.

If you need to register multiple loaders returning the same value type for different purposes, assign distinct names using `forName(...)` and `withName(...)`. When using custom names, ensure the controller's DataLoader lookup matches the registered name.

## 5. Using DataLoader in @SchemaMapping

Once the batch function is registered, the related field's resolver does not call the service directly. Instead, it asks DataLoader to load the value by key.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

In this example:

- `Book book` is the source object for the `Book.author` field.
- `book.authorId()` is the key to load.
- `authorLoader.load(...)` enqueues the key into DataLoader.
- `load()` returns `CompletableFuture<Author>`, which GraphQL awaits during execution.

If a client requests authors for many `Book`s, `load` calls are queued. DataLoader can batch those keys and call the registered batch function.

Do not call `authorService.findById(book.authorId())` directly inside this resolver, as that would issue a separate query per `Book` and bypass batch loading.

### When authorId can be null

If a `Book` has no author, you can skip DataLoader:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    if (book.authorId() == null) {
        return CompletableFuture.completedFuture(null);
    }

    return authorLoader.load(book.authorId());
}
~~~

Since SDL declares `author: Author` as nullable, `null` can be returned. If the schema declares `author: Author!`, the application must ensure an author exists or return an appropriate error.

## 6. Execution flow from load to Mono<Map>

When GraphQL executes a query with multiple `Book`s, the flow proceeds as follows:

~~~mermaid
sequenceDiagram
    participant G as GraphQL Engine
    participant C as Book.author Resolver
    participant D as DataLoader
    participant B as BatchLoaderRegistry
    participant S as AuthorService

    G->>C: Resolve Book 1.author
    C->>D: load(101)
    D-->>C: CompletableFuture pending

    G->>C: Resolve Book 2.author
    C->>D: load(102)
    D-->>C: CompletableFuture pending

    G->>C: Resolve Book 3.author
    C->>D: load(103)
    D-->>C: CompletableFuture pending

    D->>B: Dispatch {101, 102, 103}
    B->>S: findAllByIds(keys)
    S-->>B: Flux<Author>
    B->>B: collectMap(Author::id)
    B-->>D: Mono<Map<Long, Author>>
    D-->>C: Complete pending futures
    C-->>G: Author values
~~~

Main steps:

1. Each resolver calls `load(key)`.
2. DataLoader records the key and returns an uncompleted future.
3. GraphQL Java coordinates when to dispatch the batch loader.
4. Spring invokes the function registered in `BatchLoaderRegistry`.
5. The service queries data for the set of keys.
6. `collectMap` builds the map and emits the result via `Mono`.
7. DataLoader pairs values by key and completes the waiting futures.
8. GraphQL proceeds to serialize the `Author` fields.

DataLoader does not necessarily combine every key in a query into a single call. Dispatching depends on field execution waves, query structure, and batch size limits. A large query can trigger multiple batches.

## 7. The contract of Mono<Map<K,V>>

This is the most important aspect when implementing a mapped batch loader.

### Map keys must match input keys

If the batch loader receives keys:

~~~text
{101, 102, 103}
~~~

then the map must use those exact keys to bind values:

~~~java
Map<Long, Author> result = new HashMap<>();
result.put(101L, author101);
result.put(102L, author102);
result.put(103L, author103);
~~~

Never use positional indices `0, 1, 2` instead of IDs when the controller calls `load(authorId)`. DataLoader looks up the map using the exact key that was submitted.

### Order independence

The database might return `Author`s in order `103, 101, 102`. That makes no difference when the batch loader uses `collectMap(Author::id)`.

The map preserves the association:

- Key `101` receives `Author` with ID `101`.
- Key `102` receives `Author` with ID `102`.
- Key `103` receives `Author` with ID `103`.

This is a major advantage over the list-based `registerBatchLoader`, which must preserve exact positional order.

### Some keys may be missing

If key `102` has no matching record, the map can omit that key:

~~~java
Map<Long, Author> result = Map.of(
        101L, author101,
        103L, author103
);
~~~

DataLoader returns `null` for keys without a value. Accordingly, the schema field needs matching nullability, or the batch loader must turn missing data into a business error.

### Do not return an empty Mono to represent a map with no data

The batch function's contract is to return a map. If no records are found, emit an empty map:

~~~java
return Mono.just(Collections.emptyMap());
~~~

When using `Flux<Author>`, `collectMap(Author::id)` automatically emits an empty map when the `Flux` has zero elements.

`Mono.empty()` means the publisher emits no map at all. That differs from `Mono.just(Collections.emptyMap())`. Ensure the batch function always completes with a valid map even when there are no results.

## 8. Distinguishing errors from missing keys

These two cases are not the same:

- **One key not found:** the batch function succeeds and the map omits that key.
- **Error querying the data source:** the publisher emits an error signal and the batch load fails.

For example, if the database lacks `Author` `102`, the map can contain `Author` `101` and `103`. DataLoader returns `null` for key `102`, while the other two keys still receive results.

If the database loses connectivity, never return an empty map to mask the error. Let the publisher emit the error or map it to an appropriate exception:

If you want to add error handling to the registration example from the earlier section, update that same batch function as shown below; do not register a second loader with the same name:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id)
                        .onErrorMap(
                                DataAccessException.class,
                                ex -> new AuthorBatchLoadException(
                                        "Unable to load authors", ex)
                        )
        );
~~~

Batch errors can affect the keys belonging to that batch. Spring for GraphQL integrates with GraphQL error handling to include execution errors in the response. Do not turn infrastructure errors into an empty map if clients need to know that data could not be loaded.

## 9. BatchLoaderEnvironment and GraphQLContext

A batch loader may need details beyond keys, such as tenant, current user, or data-filtering policies.

The second parameter of a mapped batch loader is `BatchLoaderEnvironment`. Spring for GraphQL exposes the request's `GraphQLContext` through this environment.

For example:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            GraphQLContext graphQLContext = environment.getContext();
            String tenantId = graphQLContext.get("tenantId");

            return authorService.findAllByIdsAndTenant(
                    authorIds, tenantId)
                    .collectMap(Author::id);
        });
~~~

In this example:

- `tenantId` is retrieved from `GraphQLContext`.
- The service loads only authors belonging to the current tenant.
- The resulting map is still keyed by `Author` ID.

Context must be populated into the GraphQL request by a trusted authentication layer or interceptor. Never take a tenant or user ID from arbitrary client input and treat it as a security boundary.

Spring for GraphQL supports propagating `GraphQLContext` to batch loading functions. This is one reason to use `BatchLoaderRegistry` instead of creating and registering `DataLoader`s completely by hand.

## 10. DataLoaders are created per request

`BatchLoaderRegistry` is a shared registry for declaring batch functions. Actual `DataLoader` instances are registered into a separate `DataLoaderRegistry` for each GraphQL request.

This has two implications:

1. Loads within the same request can be batched and share a cache.
2. One request's cache is never automatically shared with another request.

For example, the same query might request `Author` ID `101` across multiple branches. By default, DataLoader reuses the result already requested for key `101` within the same request, avoiding duplicate loading.

Never create a mutable singleton `DataLoader` and share it across all GraphQL requests. Doing so can cause keys, futures, or cached data from one user to appear in another request.

The Spring Boot starter auto-configures `BatchLoaderRegistry` and wires it into `DefaultExecutionGraphQlService`, where `DataLoader`s are registered per request. The application only needs to inject the registry and register batch functions.

## 11. Naming DataLoaders when multiple loaders share a value type

With `forTypePair(keyType, valueType)`, the default DataLoader name derives from the value type's fully qualified class name. Consequently, a `DataLoader<Long, Author>` parameter is usually resolved by Spring based on its generic types.

If you have multiple batch functions returning `Author`, each serving a different purpose, give them distinct names:

~~~java
registry.<Long, Author>forName("authorById")
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id)
        );
~~~

The controller can inject the DataLoader by its registered name:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorById) {

    return authorById.load(book.authorId());
}
~~~

When using `forName`, the `DataLoader` parameter name in the handler method is used as the lookup name. Ensure parameter names are retained in bytecode or follow naming conventions Spring can detect. If there is only one loader for `Author`, `forTypePair` is usually simpler.

## 12. Customizing DataLoaderOptions and batch limits

A batch with too many keys can create huge queries, exceed database parameter limits, or consume excessive memory.

DataLoader supports configuring `DataLoaderOptions`, including capping the maximum keys per batch. Spring provides `withOptions(...)` on the registration spec to customize options.

In principle, you can configure:

- Maximum batch size.
- Enabling or disabling per-request key caching.
- Custom cache map or cache key function when needed.
- Statistics for observing DataLoader behavior.

Do not increase batch size without bounds. Pick a limit suited to your database, bind-parameter limits, response size, and downstream service latency.

If the max batch size is 100 while a query requests 350 keys, DataLoader splits them into multiple batches. Therefore, the batch loader must handle any key set it receives without assuming a fixed key count.

## 13. When to use BatchLoaderRegistry vs @BatchMapping?

Spring for GraphQL provides `@BatchMapping`, a concise declaration for loading related data from a list of source objects.

For example:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<Long> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(Author::id)
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();
                    for (Book book : books) {
                        result.put(
                                book,
                                authorsById.get(book.authorId()));
                    }
                    return result;
                });
    }
}
~~~

`@BatchMapping` automatically registers a batch loading function and `DataFetcher` for the corresponding field. This is a convenient shortcut when the key is the parent object itself.

When returning `Map<Book, Author>`, `Book` needs stable `equals` and `hashCode` implementations to serve as a key. The example above also assumes the controller injects `AuthorService` via its constructor.

Comparison:

| Criterion | BatchLoaderRegistry | @BatchMapping |
|---|---|---|
| Key | Can be an ID or any custom key type | Source/parent object |
| Input | Set of keys or List of keys | List of source objects |
| Output | `Mono<Map<K,V>>` or `Flux<V>` | `Mono<Map<Source,V>>` or `Flux<V>` |
| Resolver calls `load` | Yes, via `DataLoader` | No separate delegating resolver needed |
| Best suited for | Loader reuse, custom keys, complex arguments, or context | Simple parent-child relationships |
| Customization | Flexible with `DataLoaderOptions` and loader names | Less boilerplate |

Use `@BatchMapping` if you only need to load `Author` for a list of `Book`s and do not need extra per-field-call logic.

Use `BatchLoaderRegistry` when:

- The resolver needs to call `DataLoader.load(authorId)`.
- The key is not the entire parent object.
- Multiple fields or controllers need to share the same batch function.
- You need to combine keys with arguments or context.
- You need to name the DataLoader or customize `DataLoaderOptions`.

Both mechanisms build on DataLoader and `BatchLoaderRegistry` in Spring for GraphQL.

## 14. Testing a mapped batch loader

Tests should verify both the response and that keys are batched together.

Query example:

~~~graphql
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
~~~

Use `GraphQlTester` to verify the result:

~~~java
@Test
void shouldLoadAuthorsForBooksInBatch() {
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
}
~~~

Beyond checking the response, verify that the batch service is called only with the required ID set:

~~~java
verify(authorService).findAllByIds(argThat(ids ->
        ids.size() == 2 &&
        ids.containsAll(Set.of(101L, 102L))));
~~~

Scenarios to test:

1. Multiple `Book`s have distinct `authorId`s and load in the same batch.
2. Multiple `Book`s share the same `authorId` within one request.
3. A key does not exist and the map omits that key.
4. No records match and the batch loader returns an empty map.
5. The service emits an error and the GraphQL response contains an appropriate error.
6. Tenant or user context is applied in the batch query.
7. Batch size limits cause a large query to split into multiple batches.
8. Two independent GraphQL requests do not share DataLoader caches.
9. Nullable fields handle unfound keys properly.
10. Non-null fields surface an error properly when a value is missing.

Do not check only the service call count. Also assert that every key receives the right value to catch cases where keys are mismatched or results attach to the wrong entity.

## 15. Common mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| DataLoader not found | Registration key mismatches DataLoader name/type | Check `forTypePair`, `forName`, and generic types |
| `author` field is always `null` | Map lacks the requested key or `authorId` is wrong | Check input keys and map keys |
| Results attached to the wrong `Author` | Using positional index or wrong key | Use `Author` ID as the `Map` key |
| Batch function errors when no data exists | Returning `Mono.empty` instead of an empty map | Use `collectMap` or `Mono.just(emptyMap)` |
| N+1 still occurs | Resolver calls service directly instead of `DataLoader` | Use `loader.load(key)` |
| One batch is too large | No cap on key count | Configure a max batch size |
| Cache mixes data across requests | Sharing a mutable `DataLoader` | Let Spring register per-request loaders |
| Non-null field throws an error | Key lacks a value while SDL requires non-null | Review nullability or handle missing data |
| Tenant context missing in batch | Context not added to the GraphQL request | Check interceptor and `GraphQLContext` |

## 16. Design principles for batch loaders returning Mono

When writing a mapped batch loader:

- Use `forTypePair` to clearly declare key and value types.
- Use `registerMappedBatchLoader` when returning `Mono<Map<K,V>>`.
- Return a map indexed by the exact keys received.
- Do not rely on database record ordering.
- Allow the map to omit keys when related records do not exist.
- Return an empty map instead of an empty publisher when there are no results.
- Distinguish data source errors from unfound keys.
- Keep DataLoaders scoped to the GraphQL request.
- Use `GraphQLContext` for trusted request metadata.
- Set batch size limits based on data source capacity.
- Test responses, key-value mapping, errors, and data-access counts.
- Use `@BatchMapping` for simple parent-child relationships; use the registry directly when control over keys and `DataLoader` is needed.

## Conclusion

A mapped batch loader returning `Mono<Map<K,V>>` is how Spring for GraphQL combines reactive programming with DataLoader. The batch function receives a set of keys, loads multiple records with one or a few appropriate queries, and returns a map linking each key to its value.

`BatchLoaderRegistry` centralizes loader registration and creates DataLoaders per GraphQL request. Resolvers call `DataLoader.load(key)` to enqueue requests; GraphQL Java coordinates dispatching, and Spring delivers the `Mono` result to waiting fields. When maps use exact keys, missing keys are handled explicitly, and caches remain request-scoped, applications can cut down data accesses dramatically while preserving reactive flow.

## References

- [Spring for GraphQL — Request Execution, Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batching)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — Annotated Controllers, DataLoader and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — Batching and DataLoader](https://www.graphql-java.com/documentation/batching/)
- [GraphQL Java — java-dataloader BatchLoaderEnvironment](https://javadoc.io/doc/com.graphql-java/java-dataloader/latest/org/dataloader/BatchLoaderEnvironment.html)
