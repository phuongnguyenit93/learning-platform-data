# BatchLoaderRegistry

In Spring for GraphQL, **BatchLoaderRegistry** is the registration point for batch loaders so that DataLoader can batch multiple data-loading calls into a single bulk query. This component is particularly useful when a GraphQL operation returns a list of objects and each object needs to load additional related data—such as multiple `Book`s each needing their `Author`.

Spring manages loader registration and integrates DataLoader into each GraphQL request. A controller can receive a DataLoader configured for the key/value types, call `load()` inside the resolver, and return the future so GraphQL can continue execution. This lesson covers how to register loaders, how to write batch functions, cache scope, context integration, how it differs from `@BatchMapping`, and how to test it.

## 1. What problem does BatchLoaderRegistry solve?

Suppose a schema models the relationship between `Book` and `Author`:

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

The root resolver loads the list of books:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

If each `Book` holds an `authorId`, the `Book.author` field resolver might query the `Author` individually:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

When the list contains 50 `Book`s, GraphQL may call the `author` resolver 50 times. If each call executes a repository query, the server produces 50 extra queries. This is the N+1 problem.

DataLoader combines `load(authorId)` calls within the same request into a single batch. Instead of querying each `Author` separately, the batch loader receives a set of IDs and loads the data once:

~~~text
Without DataLoader:
Book 1 -> query Author 1
Book 2 -> query Author 2
Book 3 -> query Author 3
...
Book 50 -> query Author 50

With DataLoader:
Book 1 ─┐
Book 2 ─┤
Book 3 ─┼─> DataLoader -> batch query Authors
...     │
Book 50 ─┘
~~~

`BatchLoaderRegistry` is the Spring for GraphQL API used to register batch functions for this mechanism.

## 2. What is BatchLoaderRegistry?

GraphQL Java provides `DataLoader` and `DataLoaderRegistry`. Spring for GraphQL adds `BatchLoaderRegistry` to integrate batch loader registration with the GraphQL request lifecycle.

Responsibilities of the components:

| Component | Responsibility |
| --- | --- |
| `BatchLoaderRegistry` | Registers batch loaders by key/value type and associated configuration. |
| Batch loader | Receives multiple keys, loads data in bulk, and returns results. |
| `DataLoader<K, V>` | API used by resolvers to request data loading by key. |
| `DataLoaderRegistry` | Holds the DataLoaders used during a single GraphQL execution. |
| `BatchLoaderEnvironment` | Provides environment details to the batch function, including propagated context. |

Spring Boot provides `BatchLoaderRegistry` in the standard Spring for GraphQL auto-configuration. You can inject the registry into a configuration or component and register loaders during application startup.

An important distinction is that loader functions are registered at the application level, whereas `DataLoader` instances are created and used per GraphQL request. Consequently, DataLoader's default cache is not shared across all users or all requests.

## 3. Registering a loader by key/value type

For example, `Book` stores a `Long` `authorId` and the resolver needs the corresponding `Author`. You can register a mapped batch loader:

~~~java
package com.example.catalog.config;

import com.example.catalog.author.Author;
import com.example.catalog.author.AuthorService;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration
public class GraphQlDataLoaderConfig {

    public GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds));
    }
}
~~~

In this example, `AuthorService.findAllByIds` returns `Mono<Map<Long, Author>>`. The map is indexed by `Author` ID:

~~~java
public Mono<Map<Long, Author>> findAllByIds(Set<Long> authorIds) {
    return authorRepository.findAllByIdIn(authorIds)
            .collectMap(Author::id);
}
~~~

The service snippet above assumes the repository has a reactive `findAllByIdIn` method returning `Flux<Author>`. If using a blocking repository, wrap the blocking result in an appropriate reactive type and run blocking work on an I/O scheduler; never block an event-loop thread.

`forTypePair(Long.class, Author.class)` declares the key and value types. When a resolver requests `DataLoader<Long, Author>`, Spring matches it to the loader registered for that type pair.

### Why use a mapped batch loader?

A mapped batch loader returns results as `Map<K, V>`, associating each key with its corresponding value. This is helpful when the order of results returned from the database differs from the order of input keys.

For example, DataLoader receives keys:

~~~text
[authorId-8, authorId-2, authorId-5]
~~~

The database might return `Author`s in this order:

~~~text
[authorId-2, authorId-5, authorId-8]
~~~

If the batch function only returns a list, it must ensure element order matches the key order exactly. With a mapped loader, results are keyed explicitly:

~~~java
Map<Long, Author> authorsById = Map.of(
        2L, author2,
        5L, author5,
        8L, author8
);
~~~

DataLoader uses the map to distribute results back to the right `load()` calls.

If a key is missing from the map, the corresponding result has no value and the resolver receives `null`. Handle that case in alignment with the field's nullability in the schema.

## 4. List batch loaders and mapped batch loaders

`BatchLoaderRegistry` supports registering either list-returning batch loaders or map-returning mapped batch loaders.

### List-returning batch loader

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerBatchLoader(authorIds ->
                authorService.findAllByIdsInRequestedOrder(authorIds));
~~~

With the list form, the batch function receives a list of keys and must return results in the exact order corresponding to the input key list. If the database returns data in another order, the service must reorder the results by key before returning.

For example:

~~~java
public Mono<List<Author>> findAllByIdsInRequestedOrder(List<Long> ids) {
    return authorRepository.findAllByIdIn(ids)
            .collectMap(Author::id)
            .map(byId -> ids.stream()
                    .map(byId::get)
                    .toList());
}
~~~

This example demonstrates restoring key order after the repository returns results. If a key is not found, you must preserve that key's slot and decide whether to return `null` or raise an error according to the field's contract.

### Map-returning mapped batch loader

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds));
~~~

The map form is usually easier to use when the repository does not guarantee result order. You only need to match keys to the requested keys.

Prefer a mapped loader when entities have stable identifiers and can be indexed by key. Use a list loader when the batch function can cleanly guarantee positional correspondence.

## 5. Injecting DataLoader into a resolver

After registering the loader, a controller can accept `DataLoader<K, V>` as a method parameter.

Model example:

~~~java
public record Book(
        Long id,
        String title,
        Long authorId
) {
}

public record Author(
        Long id,
        String name
) {
}
~~~

Resolver:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.author.Author;
import com.example.catalog.book.Book;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

import java.util.concurrent.CompletableFuture;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

Spring supplies the `DataLoader` matching the registered key/value types. The resolver calls `load()` and returns `CompletableFuture<Author>`. The GraphQL engine awaits the asynchronous result to complete the `author` field.

There is no need to call the repository directly inside the resolver. Bulk loading lives inside the registered batch function.

### Processing flow

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as GraphQL Engine
    participant Resolver as Book.author resolver
    participant Loader as DataLoader
    participant Batch as BatchLoaderRegistry function
    participant DB as Author repository

    Client->>GraphQL: Query books { author { name } }
    GraphQL->>Resolver: Resolve author for each Book
    Resolver->>Loader: load(authorId)
    Resolver->>Loader: load(nextAuthorId)
    Resolver->>Loader: load(otherAuthorId)
    GraphQL->>Loader: Dispatch pending keys
    Loader->>Batch: Batch keys
    Batch->>DB: Load authors by IDs
    DB-->>Batch: Authors
    Batch-->>Loader: Map<id, Author>
    Loader-->>Resolver: Complete futures
    Resolver-->>GraphQL: Author values
    GraphQL-->>Client: GraphQL response
~~~

`load()` calls are accumulated before the batch function executes. Dispatching is coordinated by GraphQL Java during execution; normal resolvers do not need to call `dispatch()` themselves.

## 6. Do not block the DataLoader future

A common mistake is calling `join()` or `get()` immediately after `load()`:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId()).join();
}
~~~

This forces the resolver to wait immediately for the result. If every resolver blocks like this, GraphQL may fail to batch keys across multiple `Book`s effectively.

Return the future instead:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

Or chain asynchronous transformations:

~~~java
return authorLoader.load(book.authorId())
        .thenApply(author -> author);
~~~

There is no need to add `thenApply` if no transformation is needed. The second snippet merely illustrates that you can continue chaining work while keeping the future asynchronous.

Returning a future lets the GraphQL engine coordinate dispatching and complete multiple fields concurrently. Do not convert the result to synchronous just to make the code shorter.

## 7. DataLoader key batching and request-scoped caching

DataLoader typically exhibits two key behaviors:

**Batching:** multiple `load(key)` calls are gathered so the batch function processes them together.

**Caching by key:** if the same key is requested multiple times in the same request, DataLoader by default reuses the loaded result rather than invoking the batch loader again.

For example:

~~~java
CompletableFuture<Author> first = authorLoader.load(10L);
CompletableFuture<Author> second = authorLoader.load(10L);
CompletableFuture<Author> third = authorLoader.load(20L);
~~~

Within the same request, both calls for key `10L` share the same scheduled or cached result. The batch loader only needs to load two unique keys: `10L` and `20L`.

This cache is scoped to the request's `DataLoader` instance. Another request gets its own `DataLoader` and can fetch fresh data.

Do not confuse DataLoader's cache with long-lived business caches like Redis or repository caches. DataLoader optimizes data-loading coordination within a single GraphQL execution; it does not replace an application-wide caching strategy.

## 8. Choosing the right key for a batch loader

The key must fully represent all parameters that affect the loaded result.

If `Author` is only loaded by ID, a `Long` key works:

~~~java
DataLoader<Long, Author>
~~~

If the result also depends on locale or tenant, using only `authorId` could reuse the wrong result within the same request:

~~~java
public record AuthorLookupKey(
        Long authorId,
        String locale,
        String tenantId
) {
}
~~~

The loader must then be registered with the composite key type and corresponding value type:

~~~java
registry.forTypePair(AuthorLookupKey.class, Author.class)
        .registerMappedBatchLoader((keys, environment) ->
                authorService.findAllByKeys(keys));
~~~

The service must group or query by all components of the key. For data that depends on access permissions, tenant, or locale, never omit those factors from the key if they alter the result.

However, you do not always need to put every piece of information into the key. If a piece of information is fixed for the entire GraphQL request and the batch function reads it from the request context, you can use the context instead of repeating it in every key. Make sure your design never mixes data across requests.

## 9. Passing context to a batch loader

Sometimes a batch function needs information beyond the key, such as locale, tenant, or request metadata. Spring for GraphQL integrates the GraphQL context with the batch loader environment.

For example, the batch function receives `BatchLoaderEnvironment`:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds, environment));
~~~

`BatchLoaderEnvironment` provides the batch execution environment and context entries configured for the loader. You can use the context to choose a language or apply the right policy for the current request.

Keep in mind:

- Context must be populated from a trusted server-side source.
- Never trust client-supplied tenant or user IDs without authentication/validation.
- Never store one request's context in a variable shared with other requests.
- If returned data differs per key due to per-load key context, design the key/context accordingly and check the DataLoader API in use.
- Never use context to bypass authorization checks in the service layer.

For simple cases that do not require context, use a batch function that takes only the key collection. Add context only when the business logic truly needs it.

## 10. BatchLoaderRegistry and @BatchMapping

Spring for GraphQL offers two common ways to batch nested fields: registering a DataLoader via `BatchLoaderRegistry` or using the `@BatchMapping` annotation.

### Using @BatchMapping

For example:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findForBooks(books);
    }
}
~~~

The `findForBooks` method must return a map keyed by each `Book` in the input list with its corresponding `Author` value. Spring uses this map to align each result back to the right source object.

`@BatchMapping` tells Spring that this method handles a group of source objects at once. Spring creates an underlying DataLoader to link the map results to each `Book`.

### When to use BatchLoaderRegistry?

Use `BatchLoaderRegistry` when:

- A DataLoader needs to be shared across multiple resolvers or locations.
- Explicit control over key/value types is needed.
- Composite keys are needed.
- Access to the batch environment or context is required.
- Loaders should be configured at the infrastructure or service layer.
- You want to call `DataLoader` explicitly from a controller or data fetcher.

Use `@BatchMapping` when the relationship between a source type and a field has straightforward batch logic where the method accepts a list of source objects and returns results per source.

Both approaches rely on GraphQL Java's DataLoader mechanism. Do not register both `@BatchMapping` and another DataLoader for the same field without explicit intent, as that can cause conflicting mappings or make the logic hard to follow.

## 11. Handling missing data and errors in a batch loader

A batch function must define how to handle keys that are not found.

With a mapped loader, if the map lacks a key, DataLoader has no corresponding value and the result for that key is `null`. This works when the field is nullable in SDL:

~~~graphql
type Book {
    author: Author
}
~~~

If the schema declares:

~~~graphql
type Book {
    author: Author!
}
~~~

then a `null` result can trigger a GraphQL execution error and null propagation. Ensure the loader returns complete data or follows appropriate error rules.

If the entire batch function fails, you can return `Mono.error(...)` or let the reactive pipeline emit an error:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .onErrorMap(
                                DataAccessException.class,
                                AuthorBatchLoadException::new
                        ));
~~~

The example above illustrates translating a data access exception. GraphQL records the error while resolving the fields depending on the loader. Review your application's error paths and exception handling so clients receive safe error information.

Never turn every query exception into an empty map. Doing so can cause database failures to be mistaken for "Author not found". Only return an empty result when that is genuinely the semantics of the data.

## 12. Batch size limits and loading large datasets

A single operation can request many keys. A batch loader should limit how much data it processes at once to avoid oversized queries or exceeding database parameter limits.

You can split keys into smaller chunks in the service:

~~~java
public Mono<Map<Long, Author>> findAllByIds(Set<Long> ids) {
    return Flux.fromIterable(ids)
            .buffer(500)
            .concatMap(authorRepository::findAllByIdIn)
            .flatMapIterable(authors -> authors)
            .collectMap(Author::id);
}
~~~

This example assumes the repository has a method accepting a collection of IDs and returning `Flux<Author>` (or an iterable of `Author`). The chunk size 500 is illustrative; tune it based on your database, statement limits, response size, and actual load.

Also enforce limits at the API level:

- Maximum page size for lists.
- Query depth or complexity limits per server policy.
- Maximum number of elements allowed per operation.
- Timeouts and resource limits for data queries.

DataLoader reduces query count, but it does not make an unbounded query safe or cheap. A huge batch can still consume excessive memory and time.

## 13. Testing BatchLoaderRegistry

Test both the returned data and the number of times the batch function is invoked.

GraphQL operation example:

~~~graphql
query {
    books {
        id
        author {
            id
            name
        }
    }
}
~~~

A test can use `GraphQlTester`:

~~~java
@Test
void loadsAuthorsForBooksThroughBatchLoader() {
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
        .isEqualTo("Ada");
}
~~~

This illustrates the test structure; the test context must load the schema, controller, `BatchLoaderRegistry`, and the corresponding data/service beans.

Scenarios to test:

- A `Book` with a valid `Author`.
- Multiple `Book`s referencing multiple distinct `Author`s.
- Multiple `Book`s referencing the same `Author`.
- A nonexistent `authorId`.
- The batch function returning a map missing a key.
- The batch function throwing/emitting an error.
- Composite keys with different locales or tenants.
- DataLoader caching working within the same request.
- Two independent requests not sharing caches.
- Repository call count decreasing/staying bounded as the number of `Book`s grows.

You can use a mock or spy service to assert that `findAllByIds` receives the distinct set of keys in a batch. A test that only checks a valid response does not prove N+1 is gone; verify the batch service or repository invocation count.

## 14. Common mistakes when using BatchLoaderRegistry

| Symptom | Common cause | Solution |
| --- | --- | --- |
| Resolver does not receive `DataLoader` | Key/value types not registered properly or generics mismatch. | Match `forTypePair` with `DataLoader<K, V>`. |
| Batch function is never called | Resolver does not call `load()` or field is not in the selection set. | Check the operation and nested resolver. |
| N+1 still occurs | Resolver calls repository directly instead of `DataLoader`. | Return the future from `load()` and let the batch function query in bulk. |
| List batch loader returns wrong data | List order does not match input key order. | Reorder by key or use a mapped batch loader. |
| Some fields return `null` | Map lacks the key or repository did not find the record. | Verify keys, missing-data behavior, and SDL nullability. |
| Wrong data returned across conditions | Key omits parameters that affect the result. | Use a composite key or appropriate context. |
| Stale data within the same request | DataLoader cache already stored the result by key. | Consider clearing/priming after mutations if re-read in the same request. |
| Cache shared across users | Manually created a singleton DataLoader or cache. | Use the request-scoped integrated registry and avoid sharing mutable instances. |
| Batch query too large | No limit on batch size or query complexity. | Chunk batches, cap page sizes, and monitor load. |
| Repository errors treated as missing data | Batch function swallows exceptions and returns an empty map. | Propagate errors so GraphQL error handling handles them properly. |

## 15. Workflow for implementing BatchLoaderRegistry

When adding a batch loader, follow this sequence:

1. Identify which nested field is issuing multiple queries.
2. Determine the minimal key and value type the resolver needs.
3. Choose a mapped batch loader or a list batch loader.
4. Register it with `BatchLoaderRegistry.forTypePair`.
5. Ensure the batch function loads in bulk and returns results mapped accurately per key.
6. Inject `DataLoader<K, V>` into the resolver.
7. Call `load(key)` and return the future without blocking via `join`/`get`.
8. Check missing keys, errors, context, and authorization.
9. Verify whether the cache key includes all factors affecting the result.
10. Limit batch sizes and query complexity.
11. Use `GraphQlTester` to verify both results and batch invocation count.
12. Compare query counts before and after applying DataLoader.

## 16. Key takeaways

- `BatchLoaderRegistry` is Spring for GraphQL's API for registering batch loaders integrated with DataLoader.
- `forTypePair(keyType, valueType)` links the loader's key/value types with the `DataLoader` used by resolvers.
- Mapped batch loaders return `Map<K, V>`, mapping results by key independent of database return order.
- List batch loaders must preserve the exact order matching input keys.
- Resolvers call `DataLoader.load()` and should return futures so GraphQL coordinates batching.
- DataLoader batches keys and caches within a request scope; it does not replace a shared application cache.
- Composite keys or context must capture all conditions affecting the result.
- `@BatchMapping` is convenient for simple source-to-field relationships; `BatchLoaderRegistry` fits when an explicit, reusable `DataLoader` is needed.
- Handle nonexistent keys, batch errors, authorization, and batch size limits.
- Test both returned data and batch call counts to confirm effectiveness.

`BatchLoaderRegistry` enables Spring for GraphQL to connect resolvers to batch loading consistently. By registering the right key/value types, returning accurate per-key results, and keeping resolvers asynchronous, applications can curb N+1 queries while preserving per-field and per-request semantics.
