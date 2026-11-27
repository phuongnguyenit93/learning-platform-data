# Request-scoped DataLoader caching in Spring for GraphQL

DataLoader not only groups multiple data loads into a batch, it also stores loaded results in a per-request memoization cache. When the same key is requested multiple times within a single GraphQL execution, DataLoader can return the same future created earlier without submitting that key to the batch loader again.

In Spring for GraphQL, `BatchLoaderRegistry` registers batch loading functions at the application level, while concrete `DataLoader` instances are created and registered in a separate `DataLoaderRegistry` for each request. As a result, the default cache only lives for the scope of a GraphQL request, avoiding sharing loaded data across requests with different users or permissions.

## 1. What problem does request-scoped DataLoader caching solve?

Suppose a GraphQL query fetches multiple posts, each with an author:

```graphql
query {
    posts {
        id
        title
        author {
            id
            name
        }
    }
}
```

If the same author appears on multiple posts, the resolver may call `load("author-1")` multiple times. Without caching, the same key could be passed to the batch loader repeatedly or cause multiple data loads at different points in execution.

DataLoader caches results by key within a request. For example:

```text
GraphQL request R1
  load(author-1)  -> cache miss, queued into batch
  load(author-2)  -> cache miss, queued into batch
  load(author-1)  -> cache hit, reuses previous future
  load(author-1)  -> cache hit, reuses previous future
                 |
                 v
       Batch loader receives author-1, author-2
```

Caching eliminates duplicate loads for the same key within a request. Batch loading groups different keys into one load; the two mechanisms work together but serve different purposes.

## 2. Cache scope in Spring for GraphQL

Spring for GraphQL has two similarly named components with distinct roles:

| Component | Scope | Responsibility |
|---|---|---|
| `BatchLoaderRegistry` | Application-level registration component | Holds batch loader functions and DataLoader configuration. |
| `DataLoaderRegistry` | Per GraphQL request/execution | Holds the DataLoader instances created for that request. |
| `DataLoader` | Per registry/request | Queues keys, dispatches batches, and memoizes results by key. |

Spring Boot provides a `BatchLoaderRegistry` bean. `DefaultExecutionGraphQlService` uses this registry to register DataLoaders into a dedicated `DataLoaderRegistry` for each request. Therefore, batch loader functions are declared once, but a DataLoader's cache is not a singleton cache shared across all requests.

High-level lifecycle:

```text
Application startup
       |
       v
BatchLoaderRegistry holds registrations
       |
       +-------------------------------+
       |                               |
       v                               v
GraphQL request A                 GraphQL request B
       |                               |
       v                               v
DataLoaderRegistry A              DataLoaderRegistry B
       |                               |
       v                               v
DataLoader cache A                DataLoader cache B
       |                               |
       v                               v
Execution ends                    Execution ends
       |                               |
       v                               v
Cache A out of scope              Cache B out of scope
```

Do not store a `DataLoader` instance in a field of a `@Controller`, singleton `@Service`, or static variable. Let Spring register loaders via `BatchLoaderRegistry` and inject DataLoader into data fetcher method arguments when needed.

`@BatchMapping` is Spring for GraphQL's shortcut for registering a DataLoader and mapping a field in batches. Its cache also belongs to the request's DataLoader instance; there is no `@BatchMapping` cache shared across requests.

## 3. Caching is enabled by default

In GraphQL Java `DataLoaderOptions`, future caching is enabled by default. When `load(key)` is called the first time, DataLoader creates a future and stores it in the cache. Subsequent calls with the same cache key can receive the stored future.

Example with the Java API:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;

DataLoader<String, Author> loader = ...;

CompletableFuture<Author> first = loader.load("author-1");
CompletableFuture<Author> second = loader.load("author-1");

// With caching enabled, two loads of the same key share the cached result/future.
```

This does not mean the database was already called at the `load` line. DataLoader queues the key; GraphQL Java dispatches the batch at the appropriate point during execution.

The default cache is based on the DataLoader key. With keys of type `String`, `Long`, UUID, or immutable records with proper `equals`/`hashCode`, comparison is predictable. For custom object keys, ensure stable equality and hash code.

## 4. How does caching differ from batching?

These two features can be configured independently:

| Mechanism | Purpose | Effect |
|---|---|---|
| Batching | Group multiple unloaded keys into the same dispatch | Reduces the number of backend calls. |
| Caching | Memoize results/futures by key | Avoids reloading the same key within one request. |

For example, a request calls `load(A)`, `load(B)`, `load(C)`:

- Batching groups A, B, and C into one batch.
- If `load(B)` is called again later, caching returns the existing future for B.

If caching is disabled while batching remains enabled, calls can still be batched. However, duplicate keys may be passed to the batch loader multiple times if the loader uses an ordered list variant. The batch loader must return a corresponding result for each occurrence of the key.

In Spring, `registerMappedBatchLoader` receives `Set<K>`, so duplicate keys appear once in the set. `registerBatchLoader` receives `List<K>` and must handle ordering as well as duplicate keys when caching is disabled.

## 5. Registering DataLoader in Spring for GraphQL

Example domain with `Author` and a GraphQL query looking up an author by ID:

```graphql
type Query {
    author(id: ID!): Author
}

type Author {
    id: ID!
    name: String!
}
```

Java model:

```java
public record Author(String id, String name) {}
```

Batch service returning a map by ID:

```java
public interface AuthorCatalog {
    Mono<Map<String, Author>> findAllByIds(Set<String> ids);
}
```

Registering the loader with `BatchLoaderRegistry`:

```java
import java.util.Map;
import java.util.Set;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;

@Configuration
class AuthorBatchLoaderConfiguration {

    AuthorBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorCatalog authorCatalog) {

        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((ids, environment) ->
                authorCatalog.findAllByIds(ids)
            );
    }
}
```

`forTypePair(String.class, Author.class)` declares the key type and value type. By default, the DataLoader name is derived from the value class, here `Author.class.getName()`. You can customize the loader name on the registration builder if needed.

The data fetcher receives DataLoader as a method argument:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class AuthorQueryController {

    @QueryMapping
    CompletableFuture<Author> author(
            @Argument String id,
            DataLoader<String, Author> authorLoader) {

        return authorLoader.load(id);
    }
}
```

Spring for GraphQL looks up the DataLoader by generic type and default name. Each time `authorLoader.load(id)` is called within the same GraphQL execution, it uses the cache of the loader instance bound to that execution.

## 6. Demonstrating a cache hit within a single GraphQL request

A query can select the same field multiple times using aliases:

```graphql
query {
    first: author(id: "author-1") {
        id
        name
    }
    second: author(id: "author-1") {
        id
        name
    }
}
```

Both field resolvers call `authorLoader.load("author-1")`. With default caching enabled, DataLoader only needs one batch load for this key; both fields can share the result.

Within the same request, a key may be requested from multiple fields or multiple branches of the object graph. Caching prevents those branches from repeatedly loading the same entity.

## 7. A fresh cache is created for the next request

If the client sends the same query again in a new GraphQL request, Spring creates a new `DataLoaderRegistry` and a new DataLoader cache. Thus, the key `author-1` will be a cache miss in the next request unless the batch loader or service layer has its own cache.

Example:

```text
Request A:
  load(author-1) -> miss -> batch loader calls backend
  load(author-1) -> hit
  request ends, cache A goes out of scope

Request B:
  load(author-1) -> miss -> batch loader calls backend again
  load(author-1) -> hit
  request ends, cache B goes out of scope
```

This is the desired behavior when results depend on user, tenant, permissions, or data state at request time. DataLoader's request cache does not replace Redis, Caffeine, or a shared service-layer cache.

## 8. Testing request-scoped caching with `GraphQlTester`

You can verify both behaviors in a single test:

1. Two loads of the same key within one GraphQL execution call the batch service only once.
2. The same key in a subsequent GraphQL execution calls the batch service one more time.

Illustrative test slice:

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

import reactor.core.publisher.Mono;

@GraphQlTest(AuthorQueryController.class)
@Import(AuthorBatchLoaderConfiguration.class)
class DataLoaderRequestCacheTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    AuthorCatalog authorCatalog;

    private static final String QUERY = """
        query {
            first: author(id: "author-1") { id name }
            second: author(id: "author-1") { id name }
        }
        """;

    @Test
    void cachesWithinOneRequestButNotAcrossRequests() {
        Author author = new Author("author-1", "Ada");

        given(authorCatalog.findAllByIds(Set.of("author-1")))
            .willReturn(Mono.just(Map.of("author-1", author)));

        graphQlTester.document(QUERY)
            .execute()
            .path("first.name")
            .entity(String.class)
            .isEqualTo("Ada");

        then(authorCatalog).should(times(1))
            .findAllByIds(Set.of("author-1"));

        graphQlTester.document(QUERY)
            .execute()
            .path("second.name")
            .entity(String.class)
            .isEqualTo("Ada");

        then(authorCatalog).should(times(2))
            .findAllByIds(Set.of("author-1"));
    }
}
```

The example uses `@MockitoBean` from Spring Framework 6.2+ and the Spring Boot 3.x `@GraphQlTest` package. In Spring Boot 4.x, test auto-configuration packages are reorganized under `org.springframework.boot.graphql.test.autoconfigure`; in older Boot versions, use the version-appropriate mock bean annotation such as `@MockBean`.

The test assumes `AuthorBatchLoaderConfiguration` is imported, `AuthorCatalog` is mocked, and the schema has `Query.author`. Two aliases in one query test caching within a single execution; the second `graphQlTester.document(QUERY).execute()` call verifies that cache is not shared across requests.

## 9. Removing a key from the cache with `clear`

After data changes within the same GraphQL execution, a cached value may no longer be accurate. `DataLoader.clear(key)` removes a key so the next `load(key)` calls the batch loader again.

Example mutation renaming an author:

Suppose the controller injects the business service:

```java
public interface AuthorService {
    Author rename(String id, String name);
    BulkUpdateResult recalculateAll();
}

public record BulkUpdateResult(int updatedCount) {}
```

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.dataloader.DataLoader;

@MutationMapping
Author renameAuthor(
        @Argument String id,
        @Argument String name,
        DataLoader<String, Author> authorLoader) {

    Author updated = authorService.rename(id, name);
    authorLoader.clear(id);

    return updated;
}
```

After `clear(id)`, the next load for the same ID does not reuse the previously cached future. This is useful when a mutation modifies an entity that subsequent fields in the same execution might reload via DataLoader.

## 10. Updating the cache with `clear` and `prime`

If the mutation already has the updated entity after saving, you can put that entity directly into the cache so subsequent fields do not need to reload it:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.dataloader.DataLoader;

@MutationMapping
Author renameAuthor(
        @Argument String id,
        @Argument String name,
        DataLoader<String, Author> authorLoader) {

    Author updated = authorService.rename(id, name);

    authorLoader.clear(id).prime(id, updated);

    return updated;
}
```

`prime(key, value)` only inserts a value if the key is not already in the cache. If the key already exists, `prime` does not overwrite it. Therefore, to replace an existing entry, call `clear(key).prime(key, value)`.

Only prime values that have been validated and successfully saved. If a mutation fails or a transaction rolls back, do not place uncommitted objects into the cache.

## 11. Clearing the entire cache with `clearAll`

`clearAll()` removes every entry from a DataLoader. Use it when an operation modifies many keys and the application cannot pinpoint the exact affected entries.

```java
@MutationMapping
BulkUpdateResult recalculateAuthors(
        DataLoader<String, Author> authorLoader) {

    BulkUpdateResult result = authorService.recalculateAll();
    authorLoader.clearAll();
    return result;
}
```

`clearAll()` only clears the cache of the current loader; it does not clear other DataLoaders, Redis/Caffeine caches, or service-layer caches. Prefer `clear(key)` when the exact key is known to avoid reloading unrelated data.

## 12. Disabling memoization caching when there is a specific reason

Caching can be disabled with `DataLoaderOptions.setCachingEnabled(false)`. In Spring for GraphQL, pass the options into the registration:

```java
import org.springframework.context.annotation.Configuration;
import org.dataloader.DataLoaderOptions;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
class UncachedAuthorLoaderConfiguration {

    UncachedAuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorCatalog authorCatalog) {

        DataLoaderOptions options = DataLoaderOptions.newOptions()
            .setCachingEnabled(false)
            .build();

        registry.forTypePair(String.class, Author.class)
            .withOptions(options)
            .registerMappedBatchLoader((ids, environment) ->
                authorCatalog.findAllByIds(ids)
            );
    }
}
```

Disabling caching does not automatically disable batching. However, with a `BatchLoader` receiving `List<K>`, the same key can appear multiple times in the list if loaded multiple times. The loader must return results in the exact positions for each key. With `MappedBatchLoader` receiving `Set<K>`, duplicate keys are collapsed by the semantics of `Set`.

Do not disable caching solely to update an entity after a mutation. Using `clear`, `clearAll`, or `prime` is usually better and preserves deduplication benefits for all other keys.

## 13. Customizing cache keys for object keys or composite keys

By default, DataLoader uses the key itself as the cache key. If the key is an object, two different instances are treated as the same key only when their `equals` and `hashCode` match accordingly.

For example, an author loaded by tenant and locale:

```java
public record AuthorLookupKey(
    String tenantId,
    String locale,
    String authorId
) {}
```

All three components can affect the result. Using a record bases equality/hash code on those components. If using a custom class, implement `equals`/`hashCode` properly or configure `DataLoaderOptions.setCacheKeyFunction(...)` to produce an equivalent cache key.

Do not use `authorId` alone as the cache key if the result also depends on tenant, locale, permissions, or filters. Two loads with the same ID but different contexts must never collide on the same cached value.

## 14. Caching exceptions and errors from batch loaders

`DataLoaderOptions` provides `setCachingExceptionsEnabled(...)` to control memoization of exceptional results by key. With short-lived per-request caching, keeping errors cached by default avoids repeating a load that is guaranteed to fail again within the same execution. However, if an error is recoverable within the request and the application needs to retry, consider clearing the key or disabling exception caching.

Example configuration disabling exception caching:

```java
import org.dataloader.DataLoaderOptions;

DataLoaderOptions options = DataLoaderOptions.newOptions()
    .setCachingEnabled(true)
    .setCachingExceptionsEnabled(false)
    .build();
```

Distinguish whole-batch failures from errors tied to a specific key. When the batch function fails, the batch futures may complete exceptionally; for per-key errors, representation depends on the batch loader type and `java-dataloader` version. Do not blindly auto-retry every error, as that can repeat backend operations or mask data errors.

## 15. DataLoader cache does not replace shared caches

DataLoader cache is designed for a single short-lived GraphQL request. It does not share data across requests, processes, or application instances.

| Cache type | Scope | Example |
|---|---|---|
| DataLoader memoization cache | One DataLoader in one GraphQL execution | The same key is loaded only once per request. |
| Service/application cache | Multiple requests within one process | Caffeine or Spring's cache abstraction. |
| Distributed cache | Multiple processes/instances | Redis or a shared caching system. |
| HTTP/GraphQL response cache | Entire response by cache policy | Caching responses by query, variables, and permissions. |

In Java DataLoader, two cache layers should be distinguished:

- `CacheMap` stores futures by key inside the DataLoader instance; this is the memoization cache typically used per request.
- `ValueCache` is an optional abstraction for reading/writing values from an external cache, potentially asynchronously. By default, it does not connect to Redis or any distributed cache on its own.

If you want to cache data across multiple requests, use a cache at the service/data layer or deliberately configure a `ValueCache`. Do not extend the lifetime of a DataLoader request cache into a singleton merely to reuse data.

## 16. Tenant isolation and user-dependent data

Request-scoped caching is safer when each GraphQL execution has its own DataLoader instances, but batch loaders must still enforce tenant and access checks properly.

Example batch loader using tenant from `BatchLoaderEnvironment`:

```java
import graphql.GraphQLContext;
import org.springframework.graphql.execution.BatchLoaderRegistry;

registry.forTypePair(String.class, Project.class)
    .registerMappedBatchLoader((projectIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        TenantContext tenant = context.get("tenantContext");

        return projectService.findByTenantAndIds(
            tenant.tenantId(), projectIds
        ).collectMap(Project::id);
    });
```

`BatchLoaderRegistry` shares the same `GraphQLContext` between data fetchers and batch loading functions. Use a verified tenant context; never take an arbitrary tenant ID from a GraphQL argument as the authorization source of truth.

If the same DataLoader can load data for multiple tenants within a special execution, the tenant must be part of the key/cache key or the loader must be separated per tenant. Never let identical resource IDs from two tenants collide in the cache.

## 17. Memory and batch size limits

DataLoader retains loaded entries in its cache until the request completes or keys are cleared. For a large query with tens of thousands of unique keys, the cache can consume significant memory during execution.

Ways to keep it under control:

- Limit page size and the number of parent objects a query can return.
- Use query complexity/depth limits when the API allows large queries.
- Select keys carefully and only load fields the client requests.
- Consider `maxBatchSize` to split an overly large batch into multiple dispatches.
- Use `clear(key)` or `clearAll()` when entries are no longer needed during execution.
- Avoid retaining a DataLoader or its futures after GraphQL execution finishes.

`maxBatchSize` limits how many keys are sent to a single batch loader invocation; it does not limit the total number of keys cached across the entire request. Do not use `maxBatchSize` as a substitute for pagination or query complexity limits.

## 18. Testing caching and invalidation

Consider adding the following tests:

| Scenario | Expectation |
|---|---|
| Load the same key twice in one request | Batch loader receives the key only once when caching is enabled. |
| Load the same key in the next request | A fresh loader is created and the key is loaded again. |
| Two different keys | Both can be grouped into the same batch. |
| `clear(key)` then load again | The key is passed to the batch loader again. |
| `clearAll()` then load again | Cleared keys are loaded again. |
| `clear(key).prime(key, value)` | Subsequent loads use the newly primed value. |
| `prime` when key already exists | Existing entry is not overwritten. |
| Caching disabled | Same key can trigger multiple loads; batch loader must handle duplicates per contract. |
| Two concurrent tenants/requests | Cache and context never mix data. |

With `GraphQlTester`, test a query with two aliases calling the same key, then run the query again to verify caching does not cross request boundaries. For DataLoader unit tests, you can instantiate `DefaultBatchLoaderRegistry`, register loaders into a `DataLoaderRegistry`, and call `load`, `clear`, `prime`, and `dispatchAndJoin()` to test cache behavior directly.

## 19. Common pitfalls

**Assuming `BatchLoaderRegistry` is the request cache.** This registry holds registrations; `DefaultExecutionGraphQlService` creates DataLoader instances in a separate `DataLoaderRegistry` for each request.

**Storing DataLoader in a singleton field.** The cache can be shared across different users or requests. Receive the loader via a data fetcher method argument.

**Assuming caching replaces batching.** Caching eliminates duplicate keys; batching groups distinct keys together. Both solve different halves of the N+1 problem.

**Assuming disabling caching disables batching.** `setCachingEnabled(false)` only disables memoization. Batching still operates if `batchingEnabled` remains true.

**Using `prime` to overwrite an existing entry.** `prime` does not modify an already cached key. Use `clear(key).prime(key, value)` when replacing a value.

**Forgetting to clear cache after a mutation in the same execution.** Subsequent resolvers may receive stale data. Clear or prime modified keys.

**Using mutable object keys.** `equals`/`hashCode` may change after a key is cached, causing inconsistent lookups. Use immutable keys or a stable cache key function.

**Using request cache as a distributed cache.** The cache is discarded when execution ends and is not shared across instances. Use a service cache or `ValueCache` when longer-lived caching is truly needed.

**Ignoring cardinality and memory on large queries.** The cache holds every unique key until the request ends. Bound pagination, query complexity, and batch size appropriately.

## Conclusion

Request-scoped DataLoader caching is GraphQL Java's default memoization mechanism, integrated by Spring for GraphQL via `BatchLoaderRegistry` and a per-execution `DataLoaderRegistry`. Caching ensures the same key is loaded only once per request, while batching groups distinct keys into a single dispatch. When data changes within the same execution, use `clear`, `clearAll`, or `clear(...).prime(...)`; disable caching only for specific reasons while understanding its effect on duplicate keys. Never treat the DataLoader request cache as a shared cache across users or requests; use a separate service/distributed cache and ensure keys include tenant, locale, or permission context whenever those factors change the result.

## References

- [Spring for GraphQL — Request Execution: DataLoader and BatchLoaderRegistry](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: DataLoader argument](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — java-dataloader README](https://github.com/graphql-java/java-dataloader)
- [GraphQL Java — `DataLoaderOptions` API](https://javadoc.io/doc/com.graphql-java/java-dataloader/latest/org/dataloader/DataLoaderOptions.html)
