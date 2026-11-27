# Per-request DataLoader scope

## Objectives

After this lesson, you will be able to:

- Explain why DataLoaders normally have a lifecycle tied to a single GraphQL execution request.
- Distinguish application-level `BatchLoaderRegistry` from per-request `DataLoaderRegistry` and `DataLoader` instances.
- Understand the scope within which DataLoader caches operate and why instances should never be shared across requests.
- Recognize how DataLoader batches `load` calls and deduplicates keys within a single request.
- Pass request context such as tenant, principal, locale, and correlation ID to a batch loader.
- Design cache keys that capture all factors affecting the result.
- Update or clear cache entries after mutations to avoid reading stale data.
- Handle DataLoader scope in subscriptions and long-lived execution flows.
- Test cache isolation between two requests and diagnose data leakage bugs.

## 1. Why does DataLoader need per-request scope?

DataLoader helps batch multiple data loads together and caches results by key. For instance, an operation fetches multiple books and needs each book's author:

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

If there are 30 books, the `Book.author` resolver may issue 30 author load requests. DataLoader batches keys within the same execution so the batch loader queries authors by ID set. If multiple fields request the same ID, DataLoader's cache also avoids loading it repeatedly within that scope.

Author data may depend on the user, tenant, locale, or access permissions. If a single `DataLoader` instance is shared across multiple requests, the cache could return results produced under a previous request's security context to a later request.

For example:

- User A's request loads `Author(id = 42)` in tenant A.
- The result is cached inside a shared `DataLoader`.
- User B's request in tenant B also loads key `42`.
- If the loader returns A's cache entry, tenant A's data leaks to B.

Therefore, DataLoaders must normally be created and used within the scope of a single GraphQL execution request. Each request has its own cache, its own context, and its own lifecycle.

## 2. Distinguishing BatchLoaderRegistry and DataLoaderRegistry

Spring for GraphQL provides `BatchLoaderRegistry` to register batch loaders. Distinguish between the registry used to declare loaders and the registry holding the `DataLoader` instances used during execution.

| Component | Scope | Role |
| --- | --- | --- |
| `BatchLoaderRegistry` | Application-wide, typically a singleton Spring bean | Holds batch loader definitions and registrations |
| `DataLoaderRegistry` | Per GraphQL execution request | Holds `DataLoader` instances dedicated to that execution |
| `DataLoader<K, V>` | Per request/execution | Accepts keys, batches loads, and caches results within its scope |
| Batch loader function | Registered at application level, invoked for an execution's batch | Loads data for the received set of keys |

`BatchLoaderRegistry` can live as long as the application context because it stores registration definitions. That does not mean the `DataLoader` instances it creates are shared across the entire application.

When Spring GraphQL creates an execution context for a request, `DataLoader`s are registered into that execution's `DataLoaderRegistry`. Resolvers for that request receive `DataLoader`s from the current execution's registry.

This is the key boundary: batch loader definitions can be shared across requests, but caches and `DataLoader` instances must never be shared in a way that breaks isolation between requests.

## 3. Registering batch loaders in Spring for GraphQL

The example below uses a reactive repository so the batch loader returns `Flux<Author>`:

~~~java
@Configuration
class AuthorBatchLoaderConfiguration {

    AuthorBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(UUID.class, Author.class)
                .registerBatchLoader((authorIds, environment) ->
                        authorService.findAllInBatchKeyOrder(authorIds)
                );
    }
}
~~~

`forTypePair(UUID.class, Author.class)` registers a loader by key/value type pair. `registerBatchLoader` receives the keys to load and returns a publisher of corresponding values. For a batch loader returning a sequence, the service must guarantee value ordering matches key ordering per the loader contract. Never assume every repository method like `findAllById` preserves input order; if ordering cannot be guaranteed, use a mapped batch loader.

`BatchLoaderRegistry` is an application-level configuration component. Spring uses these registrations to prepare `DataLoader`s for each GraphQL execution. Each execution gets its own `DataLoader` instances, so one request's cache never becomes another request's default cache.

With a loader returning `Flux<V>`, ensure results align accurately with keys per the batch loader contract. If ordering or missing keys could introduce mismatches, consider using a mapped batch loader returning `Map<K, V>`.

Mapped loader example:

~~~java
@Configuration
class AuthorMappedBatchLoaderConfiguration {

    AuthorMappedBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(UUID.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findMapByIds(authorIds)
                );
    }
}
~~~

In the second example, `findMapByIds` returns a publisher of a map from author ID to author. Keys absent from the map have no corresponding value; resolvers handle them according to schema nullability.

Register only one mapping style for a given `DataLoader` key/type pair per your application design. If multiple distinct loaders need to share the same Java types for different purposes, assign distinct loader names and inject by the matching name.

## 4. Injecting DataLoader in a resolver

After registering a loader, a resolver can accept `DataLoader` as a method parameter:

~~~java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;

@Controller
class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<UUID, Author> authorLoader) {

        return authorLoader.load(book.getAuthorId());
    }
}
~~~

The resolver does not call the repository directly. It submits the key to `DataLoader` and returns `CompletableFuture` to GraphQL. DataLoader can batch keys requested within the same execution.

The generic types of `DataLoader<K, V>` must match the registered loader. In this example:

- `UUID` is the key type.
- `Author` is the value type.
- `book.getAuthorId()` supplies the key to load.

If an application has multiple loaders sharing the same key/value types, differentiate them using registration names and qualifiers as supported by Spring for GraphQL. Never let two loaders with different purposes accidentally share the same name.

## 5. Lifecycle of a DataLoader within a request

A typical lifecycle can be illustrated as follows:

~~~mermaid
flowchart TD
    A["Receive GraphQL request"] --> B["Create execution context"]
    B --> C["Create DataLoaderRegistry for execution"]
    C --> D["Register DataLoader instances"]
    D --> E["Resolver calls load(key)"]
    E --> F["Batch keys and check cache"]
    F --> G["Dispatch batch loader"]
    G --> H["Store results in request cache"]
    H --> I["Complete GraphQL response"]
    I --> J["End execution registry lifecycle"]
~~~

A request typically moves through these steps:

1. Spring GraphQL receives the operation and variables.
2. An execution is created with the request's context.
3. The corresponding `DataLoaderRegistry` is prepared from registered batch loaders.
4. Resolvers call `load(key)` as GraphQL processes fields.
5. Keys are accumulated and dispatched to the batch loader.
6. Results are delivered to waiting resolvers and cached in that execution's `DataLoader`.
7. Execution completes; the execution's `DataLoaderRegistry` is not retained for the next independent request.

Never store a `DataLoader` obtained in a resolver into a singleton controller field, a static field, or a global cache. Never pass that instance to another request.

## 6. Per-key caching within the same request

DataLoader typically enables caching by key. When a key is requested multiple times within the same request, calls can share an in-flight load or an already-cached result.

For example:

~~~java
CompletableFuture<Author> first = authorLoader.load(authorId);
CompletableFuture<Author> second = authorLoader.load(authorId);
~~~

If caching is enabled on the loader, two calls with the same key on the same `DataLoader` instance are normally deduplicated. The batch loader does not need to load the same key multiple times.

This helps when:

- Multiple books reference the same author.
- Two nested fields both need the same entity by ID.
- A fragment is used across multiple selection-set branches.
- Different resolvers query the same key within one operation.

This cache is not a cross-request cache. Each new GraphQL request gets new `DataLoader` instances and loads data afresh for the new execution, unless the application explicitly layers an additional service-level or distributed cache.

## 7. Two independent requests do not share caches

Suppose two requests both load author ID `42`:

~~~text
Request A
  DataLoader A
    load(42) -> batch loader -> Author 42
    cache A[42] = Author 42

Request B
  DataLoader B
    load(42) -> batch loader -> Author 42
    cache B[42] = Author 42
~~~

The same key does not mean two requests share a single load. Reloading in request B is normal behavior in the absence of a higher-level cache.

Separate scopes ensure:

- Request A never sees cache entries populated during request B.
- A prior request's principal or tenant never inadvertently affects a subsequent request.
- Errors or transient results in one execution never become default cache entries for another execution.
- New requests read fresh data state from the data source per the application's consistency model.

If you want to cache data across multiple requests to reduce database load, use a service/repository cache or distributed cache with explicit keys and invalidation policies. Never turn `DataLoader` into a singleton cache to achieve that goal.

## 8. Request context and caller-dependent data

A batch loader sometimes needs metadata beyond keys, such as:

- Current tenant.
- Principal or access permissions.
- Locale used to translate content.
- Correlation ID for tracing.
- Execution options stable throughout the request.

Spring for GraphQL supports passing execution context to batch loaders via `BatchLoaderEnvironment` and GraphQL context. Obtain request metadata from framework-managed context or configured context propagation mechanisms.

Conceptual example of data scoping:

~~~text
GraphQL request context
  principal = user-17
  tenantId  = tenant-A
  locale    = vi-VN

Batch loader
  keys      = [author-1, author-2, author-3]
  scope     = tenant-A
  result    = authors visible to user-17 in tenant-A
~~~

Never store one request's principal, tenant, or locale in a mutable field on the singleton bean used to register the loader. The registration bean outlives requests; request state must flow through execution context.

If using a reactive pipeline, ensure context propagates via Reactor Context through appropriate mechanisms. Never assume `ThreadLocal` remains automatically populated when a batch loader runs on another scheduler.

## 9. Tenant security and access control in batch loaders

A per-request `DataLoader` isolates caches between requests, but it does not perform authorization on its own. Batch loaders must still restrict data by tenant and caller permissions.

Example of a service receiving a tenant ID resolved from trusted context:

~~~java
@Service
class AuthorService {

    private final AuthorRepository repository;

    AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<UUID, Author> findVisibleByIds(
            Collection<UUID> ids,
            UUID tenantId) {

        return repository.findVisibleByIdsAndTenantId(ids, tenantId)
                .stream()
                .collect(Collectors.toMap(
                        Author::getId,
                        Function.identity()
                ));
    }
}
~~~

The batch loader must read `tenantId` from request context and invoke the service with that scope. Never take a tenant from an arbitrary client-supplied argument and trust it as an authenticated identity.

Even within a single request, a batch loader must account for per-key authorization. Some authors in a batch may be visible while others are out of scope. Never return every record just because one item in the batch is authorized.

Common options:

- Filter directly in the repository query by tenant and permissions.
- Return a map containing only keys the user is allowed to access.
- Map out-of-scope keys to `null` or an error per schema and security policy.
- Never let error messages leak resources belonging to another tenant.

## 10. Cache keys must fully represent the result

DataLoader caches by key. If a result depends on multiple factors yet the key contains only an ID, the cache can return the wrong result even within the same request.

Example of a resolver taking an additional locale:

~~~graphql
type Author {
    id: ID!
    biography(locale: String!): String
}

type Query {
    author(id: ID!): Author
}
~~~

If the loader uses only `authorId` as the key, the following two calls can have different locales:

~~~graphql
query {
    author(id: "author-42") {
        vietnamese: biography(locale: "vi")
        english: biography(locale: "en")
    }
}
~~~

Both fields share the same author ID yet require different outputs. If the cache key is only the ID, the second call may receive the value cached from the first call.

Designing a composite key:

~~~java
public record BiographyKey(UUID authorId, String locale) {
}
~~~

Loader using `BiographyKey`:

~~~java
DataLoader<BiographyKey, String> biographyLoader;
~~~

When calling:

~~~java
biographyLoader.load(new BiographyKey(authorId, locale));
~~~

Keys must capture every dimension that changes the output, such as ID, locale, projection, or view mode. When tenant/principal is constant within a request, scope can come from context; however, if the same loader is invoked within one execution across multiple scopes, that scope must also enter the key or loaders must be separated per scope.

## 11. When to clear or prime the cache?

A per-request cache can become stale when the same operation executes a mutation and then reads the same key via that DataLoader.

Example of a mutation updating an author:

~~~java
@MutationMapping
public Author updateAuthor(
        @Argument("id") UUID id,
        @Argument("input") UpdateAuthorInput input,
        DataLoader<UUID, Author> authorLoader) {

    Author updated = authorService.update(id, input);

    authorLoader.clear(id).prime(id, updated);

    return updated;
}
~~~

After a successful write:

- `clear(id)` removes the old cache entry for the key.
- `prime(id, updated)` puts the new value into the cache.
- Subsequent resolvers in the same execution receive the newly updated value.

If no updated value is available to prime, simply clear the key so the next load re-reads from the data source. When a mutation affects multiple keys or relationships, identify all relevant loaders/cache entries to invalidate the proper scope.

Avoid calling `clearAll()` indiscriminately if only one key changed, as that discards caching benefits for unrelated keys in the request. Conversely, when a mutation alters data affecting a loader's entire output set, clearing multiple keys or the whole cache may be warranted under a clear policy.

## 12. DataLoader in subscriptions and long-lived executions

GraphQL subscriptions outlive standard queries: a single operation can emit many events and produce results over time.

Never retain a `DataLoader` inside a singleton controller or bean to reuse across all events and all subscribers. Each execution needs its own context and registry matching the execution scope managed by Spring GraphQL.

When designing subscriptions:

- Never share subscriber A's cache with subscriber B.
- Never let one subscriber's tenant/principal affect another subscriber.
- Determine which data must be freshly loaded per event.
- Avoid keeping cache entries alive longer than data validity permits.
- Verify registry and context behavior for your transport and version, especially when long-lived connections multiplex multiple operations.

A WebSocket connection may stay open for a long time, yet you should not assume DataLoader caches should last for the connection's lifetime. Connection, subscription operation, and individual GraphQL execution are distinct scopes.

## 13. Batch size and resource limits

Request scope isolates caches, yet a single request can still request a massive number of keys. If a client sends a large operation, one batch can contain a substantial number of keys.

Consider:

- Capping list sizes and selection-set depth.
- Capping batch size via `DataLoaderOptions` or equivalent loader mechanisms.
- Splitting batches into chunks compatible with `IN` clause or downstream API limits.
- Setting timeouts on batch queries.
- Monitoring keys per batch, dispatch counts, and processing times.
- Avoiding keeping huge objects cached for too long during massive operations.

Conceptually: if a database efficiently handles at most a few hundred IDs per query, the batch loader should chunk the key set into smaller groups rather than generating a query with tens of thousands of parameters.

Request scope does not replace query limits. It only defines where caches and `DataLoader` instances are owned.

## 14. Common mistakes with DataLoader scope

| Symptom | Common cause | Solution |
| --- | --- | --- |
| User from another tenant receives stale data | `DataLoader` instance or cache shared across requests | Create `DataLoader` registry/instances per execution |
| Two requests always share results | `DataLoader` stored in a singleton or static field | Inject `DataLoader` only per resolver execution |
| Same ID with different locale returns wrong content | Cache key contains only ID, missing locale | Use a composite key or separate loaders |
| Batch loader returns data for wrong user | Principal/tenant scope not enforced | Read scope from request context and filter in repository |
| Nested field still returns old value after mutation | Per-request cache entry was not invalidated | `clear(key)` then `prime(key, value)` or clear |
| DataLoader caches too many keys | Oversized operation or uncapped inputs | Limit queries, list sizes, and batch sizes |
| Subscription receives another subscriber's data | Shared loader/cache at connection or singleton level | Isolate registries per execution and subscriber |
| Batch loader cannot see tenant or principal | Context propagation not configured | Use GraphQL context/`BatchLoaderEnvironment` and propagate context properly |
| Same key loaded repeatedly | Caching disabled or non-normalized keys | Check cache options and key construction |
| Loader works in dev but fails under concurrency | Mutable request state stored in a singleton bean | Remove request state from singletons and test concurrency |

## 15. Testing cache isolation between two requests

An important test is verifying that the same key across two independent GraphQL requests does not share a DataLoader cache.

You can use a mock service counting batch loads or repository calls. Example scenario:

1. Send request A loading author ID `42`.
2. Send independent request B also loading author ID `42`.
3. Verify the batch loader is called for both requests when no service-level cache is active.
4. Verify each request's result is scoped to its respective tenant/principal.
5. Verify neither request sees values primed into the other's `DataLoader`.

Operation example usable across both requests:

~~~graphql
query {
    book(id: "book-42") {
        author {
            id
            name
        }
    }
}
~~~

The test scenario should supply distinct authentication/context per request, such as tenant A and tenant B. If tests only run with the same principal and data, they may fail to catch cache leakage bugs.

### 15.1. Testing caching within the same request

Also test the complementary behavior: two fields within the same request loading the same key can share a cache entry.

Create an operation requesting the same author from two different branches or multiple books referencing the same author. Verify the batch loader does not reload the same key when caching is enabled.

These two test types complement each other:

- **Same request:** verifies batching and deduplication work.
- **Different requests:** verifies cache isolation and that context does not leak.

## 16. Design rules for DataLoader scope

When implementing DataLoader in Spring for GraphQL, apply these rules:

1. Register batch loader definitions at the application level via `BatchLoaderRegistry`.
2. Let Spring create and manage the `DataLoaderRegistry` per execution.
3. Inject `DataLoader` into resolvers for the current execution.
4. Never store `DataLoader` instances in singletons, static fields, or global caches.
5. Treat DataLoader caches as per-request caches, not cross-request caches.
6. Include every dimension affecting output in cache keys or appropriate context.
7. Enforce tenant and authorization filters inside batch queries.
8. Clear or prime caches after mutations when needed.
9. Cap batch sizes and operation sizes.
10. Test the same key within one request and across two independent requests.

## 17. Summary

Per-request DataLoader scope enables batching and caching data loads within a single GraphQL execution while preserving isolation across independent requests. In Spring for GraphQL, `BatchLoaderRegistry` holds application-level loader configurations; `DataLoaderRegistry` and `DataLoader` instances serve specific executions.

Never share `DataLoader` instances or their caches via singletons, static fields, or across users. When data depends on tenant, principal, locale, or permissions, batch loaders must receive trusted context and cache keys must fully represent the result. After mutations, clear or prime affected keys. Testing both intra-request deduplication and inter-request cache isolation catches stale-data and data-leakage bugs early.
