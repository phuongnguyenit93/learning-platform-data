# Avoiding global-state DataLoaders in Spring for GraphQL

`DataLoader` helps batch multiple data loads together and caches results within the scope of a single GraphQL execution. For this mechanism to be safe, each GraphQL execution needs its own `DataLoaderRegistry` and `DataLoader` instances. Never store a `DataLoader`, `DataLoaderRegistry`, or per-request data cache in a `static` variable or singleton shared across multiple requests.

In Spring for GraphQL, you should register batch loaders via `BatchLoaderRegistry` or use `@BatchMapping`. `BatchLoaderRegistry` can be a singleton bean because it holds **registration definitions**; Spring creates a separate registry and `DataLoader` instances for each GraphQL execution. Distinguishing between where loaders are declared and where loader state lives is fundamental to preventing data leaks across users, tenants, and requests.

## 1. What state does a DataLoader hold?

A `DataLoader<K, V>` typically retains the following state throughout its lifecycle:

- Keys queued to be sent to the batch loader.
- Promises/futures corresponding to each `load(key)` call.
- Cached results by key, if caching is enabled.
- Batching and cache-key options.

For example, resolvers for 20 books call `authorLoader.load(authorId)` to load authors. DataLoader can gather the IDs into a batch, call the service once, and distribute results back to each resolver. If the same ID is requested multiple times within the same execution while caching is enabled, DataLoader can reuse the existing result.

This state is request-dependent: the queued keys, cached results, and dispatch timing all belong to a specific GraphQL execution. Consequently, one instance cannot be shared across multiple independent requests.

## 2. Why not use a global DataLoader?

An anti-pattern is creating a `DataLoader` in a `static` field or inside a singleton service and keeping it for all requests:

~~~java
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.springframework.stereotype.Component;

@Component
public class BadAuthorLoader {

    private final DataLoader<Long, Author> authorLoader;

    public BadAuthorLoader(AuthorService authorService) {
        this.authorLoader = DataLoaderFactory.newMappedDataLoader(
                authorIds -> authorService.findByIds(authorIds).toFuture()
        );
    }

    public DataLoader<Long, Author> getLoader() {
        return authorLoader;
    }
}
~~~

`BadAuthorLoader` is a singleton component and holds a `DataLoader` in a field for the lifetime of the application context. Different requests access the same queue and cache concurrently. Using a `static` field for a loader introduces the same scoping flaw while making dependencies harder to manage.

Common risks:

1. **Cross-user data leakage:** an earlier request's cache may be reused for a later request, even when the later user lacks permission to view that data.
2. **Cross-tenant leakage:** the same ID may represent different records in different tenants, yet a global cache keys only by ID.
3. **Stale data:** a mutation updates data while the global cache still retains the previous value.
4. **Cross-request queue mixing:** `load` calls from multiple executions can enter the same loader and dispatch cycle.
5. **Unclear lifecycle:** caches do not terminate when requests finish, increasing memory usage and making tests order-dependent.

DataLoader is not a global application cache and must not be used as a singleton service.

## 3. The proper lifecycle: global registration, per-execution instances

Spring for GraphQL provides `BatchLoaderRegistry` to register batch loaders centrally. The registration registry can exist as a singleton bean, while `DataLoader` instances and the `DataLoaderRegistry` used to execute a GraphQL operation have their own isolated scope.

~~~mermaid
flowchart TD
    A[Spring Application Context] --> B[Singleton BatchLoaderRegistry]
    B --> C[Loader registration definitions]
    D[GraphQL Request A] --> E[DataLoaderRegistry A]
    F[GraphQL Request B] --> G[DataLoaderRegistry B]
    C --> E
    C --> G
    E --> H[DataLoader A: queue and cache]
    G --> I[DataLoader B: queue and cache]
    H --> J[Batch load for Request A]
    I --> K[Batch load for Request B]
~~~

Each request/execution gets its own queue and cache. The same registration definition can instantiate `DataLoader`s across many executions without sharing request state.

Distinguish between the two concepts:

| Component | Scope | Can be a singleton? |
| --- | --- | --- |
| `BatchLoaderRegistry` | Application context; stores registration definitions | Yes |
| Stateless batch loader/service function | Application context | Yes |
| `DataLoaderRegistry` | Single GraphQL execution | No |
| `DataLoader<K, V>` | Single GraphQL execution | No |
| Internal DataLoader queue and cache | Single GraphQL execution | No |
| `GraphQLContext` holding request principal/tenant | Single GraphQL execution | Never use as global mutable state |

## 4. Registering loaders via BatchLoaderRegistry

Suppose an application has `Book` containing `authorId`, and needs to load `Author` by ID.

Models:

~~~java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
~~~

Service providing batch operations:

~~~java
import java.util.Map;
import java.util.Set;
import reactor.core.publisher.Mono;

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
    Mono<Map<Long, Author>> findByTenantAndIds(String tenantId, Set<Long> authorIds);
}
~~~

Register the batch loader once when the application context starts:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration(proxyBeanMethods = false)
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService
    ) {
        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findByIds(authorIds)
                );
    }
}
~~~

`BatchLoaderRegistry` holds the registration for the `Long` and `Author` key/value pair. When a GraphQL execution needs that loader, Spring creates a `DataLoader` inside that execution's registry. The service can be a singleton because it holds no DataLoader queue or cache; it simply executes a batch query for the supplied ID set.

A mapped batch loader returns a map from key to value. Keys absent from the map are treated as having no corresponding result; if the GraphQL field is Non-Null, design missing-data handling consistent with the schema.

## 5. Injecting DataLoader into an annotated controller

Spring for GraphQL can supply the corresponding `DataLoader` to a handler method parameter:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader
    ) {
        return authorLoader.load(book.authorId());
    }
}
~~~

The controller does not instantiate `DataLoader`, does not hold `DataLoader` in a field, and does not manually call `dispatch()`. GraphQL execution manages batch loader dispatching across execution cycles. Each resolver merely requests a key via `load`; DataLoader batches eligible requests and returns futures for each field.

With a query loading many books, `authorLoader.load(...)` calls can be batched into a single `AuthorService.findByIds(...)` invocation. If two books share the same `authorId`, per-request caching eliminates duplicate loads.

## 6. Using @BatchMapping to let Spring manage DataLoader

If you do not need direct access to `DataLoader`, `@BatchMapping` is shorter. Spring for GraphQL automatically registers the batch loader and corresponding `DataLoader`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

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

        return authorService.findByIds(authorIds)
                .map(authors -> books.stream()
                        .filter(book -> authors.containsKey(book.authorId()))
                        .collect(Collectors.toMap(
                                book -> book,
                                book -> authors.get(book.authorId())
                        )));
    }
}
~~~

This example uses the reactive service declared in the previous section. `@BatchMapping` still uses Spring-managed `DataLoader` mechanics underneath; there is no need to build registries or caches manually.

## 7. Do not keep request state in singleton services

Having a singleton service to access a repository or API is normal. Problems arise when the service stores request-dependent data in mutable fields:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class BadAuthorService {

    private final AuthorRepository repository;
    private final Map<Long, Author> lastRequestCache = new HashMap<>();
    private String currentTenant;

    public BadAuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<Long, Author> findByIds(Set<Long> ids, String tenantId) {
        this.currentTenant = tenantId;
        Map<Long, Author> result = repository.findAuthors(ids, currentTenant);
        lastRequestCache.putAll(result);
        // Returns shared mutable state across requests.
        return lastRequestCache;
    }
}
~~~

A singleton bean can be invoked concurrently by multiple GraphQL executions. `currentTenant` and `lastRequestCache` allow one request's data to overwrite or corrupt another request's results.

Pass required data through method parameters and return local results instead:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class JpaAuthorLookup {

    private final AuthorRepository repository;

    public JpaAuthorLookup(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<Long, Author> findByIdsForTenant(Set<Long> ids, String tenantId) {
        return repository.findByTenantIdAndIdIn(tenantId, ids).stream()
                .collect(java.util.stream.Collectors.toMap(
                        AuthorEntity::getId,
                        this::toDomain
                ));
    }

    private Author toDomain(AuthorEntity entity) {
        return new Author(entity.getId(), entity.getName());
    }
}
~~~

A singleton service remains safe when its dependencies are designed for concurrent use and its methods never write request state to shared fields. Standard Spring Data repositories are designed to be used through bean proxies; even so, never store an `EntityManager`, transaction, or arbitrary mutable request data in fields.

## 8. Passing tenant and security context per request

A batch loader sometimes needs the tenant, principal, or locale to query data with the right scope. Never store these values in `static` variables, singleton fields, or a shared `currentUser` variable.

With Spring for GraphQL, per-request metadata can be placed into `GraphQLContext` during transport/interceptor processing. `BatchLoaderRegistry` supports propagating the GraphQL execution context to batch loaders through `BatchLoaderEnvironment`.

The processing flow should be:

1. Authenticate the request and resolve the principal/tenant from a trusted source.
2. Put the required metadata into the current execution's `GraphQLContext`.
3. Have the batch loader read that execution's context when running the batch query.
4. Ensure the service always enforces tenant and access-control filters in data queries.

Conceptual example of reading context in a context-aware callback:

~~~java
import graphql.GraphQLContext;
import java.util.Set;
import reactor.core.publisher.Mono;

registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            GraphQLContext graphQLContext =
                    (GraphQLContext) environment.getContext();
            String tenantId = graphQLContext.get("tenantId");
            return authorService.findByTenantAndIds(tenantId, authorIds);
        });
~~~

Context-aware callbacks depend on the `registerMappedBatchLoader` overload and context type in your version of Spring for GraphQL/GraphQL Java. If the API returns context as `Object`, cast or convert it safely before reading. The essential principle is that context must originate from the current execution, never a singleton field.

The service contract for the context-aware example should accept tenant as a parameter:

~~~java
Mono<Map<Long, Author>> findByTenantAndIds(String tenantId, Set<Long> authorIds);
~~~

Never trust an arbitrary client-supplied `tenantId` argument without authorization checks. Use the authenticated principal to resolve the tenant, then enforce the tenant condition in the repository/service. DataLoader's per-key cache does not automatically include tenant in the key; if a single execution can load the same ID under multiple scopes, include that scope in the key or separate loaders per scope.

## 9. Request-scoped DataLoader caching

DataLoader typically enables per-key caching. This cache avoids duplicate loads within the same GraphQL execution:

~~~java
CompletableFuture<Author> first = authorLoader.load(100L);
CompletableFuture<Author> second = authorLoader.load(100L);
~~~

When caching is enabled, both `load(100L)` calls on the same loader share the same future result. Another execution gets a different `DataLoader` instance and therefore never reads the previous execution's cache.

This differs from a global cache inside a service:

| Cache type | Lifetime | Purpose |
| --- | --- | --- |
| DataLoader cache | Single GraphQL execution | Deduplicates loads and shares results within one query |
| Cache inside a singleton service | Can last as long as the application context | Application cache; requires explicit key design, TTL, invalidation, and access control |
| Shared Redis/Caffeine cache | Multiple requests/instances | Intentional distributed or application-level cache |

Do not use DataLoader's cache in place of a long-lived business cache. Conversely, if the application needs a shared cache, design it as a dedicated component whose keys include tenant, locale, data version, and appropriate authorization dimensions.

## 10. When should you disable DataLoader caching?

Batching and caching are related yet distinct features. You may want to batch multiple keys together without reusing results by key within the same execution—for example, when each load carries distinct context or data must be read fresh per special semantics.

GraphQL Java provides `DataLoaderOptions` to configure caching, batch size, and cache keys. You can disable caching for a loader via `setCachingEnabled(false)` on the corresponding registration's options.

Disabling caching does not make a DataLoader global or non-request-scoped; the instance lifetime still belongs to the current execution. Batching still operates, though the same key may appear multiple times in a batch and the backend must handle that. Only disable caching when data requirements demand it; the default per-request cache normally prevents redundant queries.

If the default cache key does not fully capture input variations, consider a custom cache key or a composite key rather than creating a global DataLoader.

## 11. Updating the cache after a mutation

A GraphQL operation can contain a mutation updating a record and then resolve fields depending on that record. If a `DataLoader` in the same execution has already cached the old value, clear or replace the corresponding entry.

For example:

~~~java
@MutationMapping
public CompletableFuture<Book> renameBook(
        @Argument("id") Long id,
        @Argument("title") String title,
        DataLoader<Long, Book> bookLoader
) {
    return bookService.renameAsync(id, title)
            .thenApply(updated -> {
                bookLoader.clear(updated.id());
                bookLoader.prime(updated.id(), updated);
                return updated;
            });
}
~~~

This example assumes the application registered a `Long` → `Book` DataLoader in `BatchLoaderRegistry` so Spring can inject the loader into the mutation handler. `clear(key)` deletes the stale entry for that key in the current `DataLoader`. `prime(key, value)` inserts the new value into the cache if the key is absent. Combining both ensures field resolvers running after the mutation receive fresh data within the same execution.

This is solely request-scoped cache invalidation. If the application has a shared Redis/Caffeine cache, the mutation must also update or evict the application cache per its own policy. Never attempt to solve global caching by keeping a `DataLoader` alive longer.

## 12. Choosing safe keys and cache keys

A DataLoader key must fully represent the data to load. If you only use `authorId` while results also depend on tenant, locale, or permission state, check whether those factors remain constant throughout an execution.

Simple key example:

~~~java
DataLoader<Long, Author> authorLoader;
~~~

Composite key example when one execution uses multiple locales:

~~~java
public record AuthorKey(Long authorId, String locale) {}

DataLoader<AuthorKey, Author> localizedAuthorLoader;
~~~

With composite keys, the batch loader receives a set of `AuthorKey`s and returns a map keyed by those exact keys. If using a `cacheKeyFunction`, ensure the key-derivation function never drops tenant, locale, or any factor altering results. An incomplete key can cause two distinct requests to share the same cache entry.

Authorization must still be verified at the service/data-access layer. A cache hit is not proof that the current user is allowed to see the data.

## 13. Testing for zero state leakage across requests

You should test at least two properties:

- Within a single GraphQL execution, loads for the same key can be batched/cached per configuration.
- Across two separate executions, the same key goes through separate `DataLoader` instances and caches.

Integration test example: send two independent GraphQL requests with the same `bookId` or `authorId`, then verify the batch service is called once per execution. You can use `@MockitoBean` or a counter in a fake service to observe invocation counts.

Important test cases:

1. One query loads multiple parent objects and asserts the batch service receives multiple keys in one call.
2. Two fields in the same execution request the same key and verify caching behaves as expected.
3. Two different requests ask for the same key, yet the batch service is invoked separately for each request.
4. Two different tenants request the same ID, yet results always belong to their respective tenants.
5. A mutation updates a record and `DataLoader` is `clear`/`prime`d before dependent fields re-read it.
6. When caching is disabled, batching still works and the backend handles duplicate keys properly.
7. The batch loader retains no key lists, principals, or request results after execution completes.

For tenant/security tests, establish distinct contexts for two requests via an interceptor or appropriate test transport rather than mutating a singleton `currentTenant` variable between calls.

## 14. Anti-patterns to avoid

| Anti-pattern | Why it is dangerous | Right approach |
| --- | --- | --- |
| `static DataLoader<K,V>` | Shares queues and caches across executions | Inject `DataLoader` into handlers from per-execution registries |
| Singleton holding `DataLoaderRegistry` | Registries and loader instances lose per-request isolation | Use `BatchLoaderRegistry` to hold registration definitions |
| Singleton service with `currentTenant` field | Concurrent requests can overwrite each other's context | Pass tenant via method parameters or execution context |
| Static `Map<K,V>` as a default cache | Lacks TTL, invalidation, and clear authorization scope | Use per-request DataLoader cache or a dedicated application cache |
| Batch loader holding a mutable key list | Keys from an earlier request can linger into another request | Treat keys as local callback inputs; never store them in fields |
| Manually calling `dispatch()` inside a resolver | Interferes with the dispatch cycle managed by GraphQL | Call only `load(key)` and let GraphQL execution dispatch |
| Using ID-only keys across multiple data scopes | Can return wrong tenant, locale, or data version | Use composite keys or separate loaders per scope |
| Using cache hits in place of authorization | May return data the current user is forbidden to see | Enforce permissions in services for every access path |

## 15. Safe DataLoader implementation workflow

When curbing N+1 with DataLoader in Spring for GraphQL:

1. Identify the relational field and the key to batch-load.
2. Prefer `@BatchMapping` if batch logic ties directly to the source field.
3. Use `BatchLoaderRegistry` if you need loader reuse or to inject `DataLoader<K,V>` into multiple resolvers.
4. Register batch loaders in application configuration; never instantiate `DataLoader` instances in singleton fields.
5. Let Spring create a separate `DataLoaderRegistry` and `DataLoader` instances for each GraphQL execution.
6. Pass principal, tenant, and locale via `GraphQLContext`/context-aware batch loaders; never use global mutable state.
7. Ensure keys and cache keys include every factor affecting the result.
8. Keep DataLoader caches scoped to the execution; design shared caches as separate components when genuinely needed.
9. After mutations, clear/prime the execution's loader and invalidate any application cache if present.
10. Test batching, intra-execution cache hits, and isolation between independent requests.

DataLoader only works safely when its queue and cache belong to the right GraphQL execution. In Spring for GraphQL, `BatchLoaderRegistry` and `@BatchMapping` keep registrations shared while creating isolated loader state per execution. This structure reduces N+1 while preserving data boundaries across users and requests.

## References

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batching)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
