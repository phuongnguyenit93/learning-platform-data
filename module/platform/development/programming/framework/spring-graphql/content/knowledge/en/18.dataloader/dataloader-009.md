# DataLoader context in Spring for GraphQL

DataLoader batches multiple data loads into a single batch to reduce repeated queries, especially across nested GraphQL fields. When a batch loader needs information about the current request—such as the tenant, locale, or authenticated principal—you must propagate context to the right batch loader.

In Spring for GraphQL, `BatchLoaderRegistry` registers DataLoaders by key/value type and manages DataLoader creation for each GraphQL request. Request context is passed to the batch loader via `BatchLoaderEnvironment`. Consequently, the batch loader can use the same metadata as other resolvers while keeping request data isolated between executions.

## 1. Why does DataLoader need context?

Suppose a query returns many books, each with an author:

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

The `Book.author` field resolver can use DataLoader to batch `authorId`s into a single bulk load. However, in a multi-tenant application, having only the author ID is not enough. The batch loader also needs to know the current tenant so it does not accidentally fetch an author belonging to another tenant.

Other information a batch loader might need:

- Current tenant or organization to scope data.
- Authenticated principal or permission details to filter records.
- Locale to select appropriate content or translations.
- Correlation ID or trace metadata for logging and request observability.
- Server-verified per-request feature flags or configuration.

Context passes this shared metadata without requiring you to add it to every GraphQL argument or stuff it arbitrarily into DataLoader keys.

## 2. Distinguishing GraphQLContext and DataLoader context

There are two related concepts with distinct roles:

| Concept | Scope | Common access point |
| --- | --- | --- |
| `GraphQLContext` | A single GraphQL execution/request | `DataFetchingEnvironment.getGraphQlContext()`, `@ContextValue` |
| DataLoader batch context | Context provided to a DataLoader's batch dispatch | `BatchLoaderEnvironment.getContext()` |
| Per-key context | Metadata attached to a specific `load(key, keyContext)` call | `BatchLoaderEnvironment.getKeyContexts()` in supported GraphQL Java APIs |

`GraphQLContext` is well suited for holding shared request metadata. For DataLoaders registered via Spring for GraphQL's `BatchLoaderRegistry`, the request's `GraphQLContext` is passed to the batch loader through `BatchLoaderEnvironment`.

Per-key context has a narrower scope: each loaded key can carry its own metadata. Use it only when a single batch genuinely contains keys needing different metadata. If the tenant or principal applies uniformly across the whole request, `GraphQLContext` is simpler and more consistent.

Do not confuse context with the key. The key identifies the data to load, such as `authorId`; context supplies the execution environment, such as `tenantId`. If a factor affects the identity of cached data, ensure the cache never returns the wrong result when that factor varies.

## 3. Placing request metadata into GraphQLContext

Spring for GraphQL allows customizing `ExecutionInput` through `WebGraphQlInterceptor`. For example, an application extracts the tenant from authenticated details and puts it into `GraphQLContext`:

```java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    private final TenantResolver tenantResolver;

    public TenantContextInterceptor(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = tenantResolver.resolveAuthorizedTenant(request);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> context.put("tenantId", tenantId))
                        .build());

        return chain.next(request);
    }
}
```

`TenantResolver` is an application component responsible for resolving the tenant from the authenticated principal/session/token and verifying that the user has access to that tenant. Never take an arbitrary header or client-supplied argument and place it straight into context as trusted metadata.

The interceptor runs at the request layer before GraphQL execution begins. Resolvers and batch loaders within the same execution can reuse this context. Use consistent keys, such as a constant `TENANT_ID_CONTEXT_KEY`, to avoid typos.

If you need to pass a principal or locale, place verified values into context in the same way. Store only truly needed metadata; avoid placing tokens, passwords, or large unnecessary objects inside `GraphQLContext`.

## 4. Reading GraphQLContext in a resolver

A resolver can retrieve context using `DataFetchingEnvironment` or `@ContextValue`.

Example using `@ContextValue`:

```java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @ContextValue("tenantId") String tenantId) {
        return bookService.findBooksForTenant(tenantId);
    }
}
```

Or read directly from `DataFetchingEnvironment`:

```java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public List<Book> books(DataFetchingEnvironment environment) {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    return bookService.findBooksForTenant(tenantId);
}
```

`@ContextValue` fits when the method only needs a few specific context values. `DataFetchingEnvironment` is useful when multiple execution metadata entries are needed. In both cases, context is read for the current request; never store it in a mutable field on a singleton controller.

## 5. Registering DataLoader with BatchLoaderRegistry

Spring for GraphQL recommends registering batch loaders via `BatchLoaderRegistry`. The registry automatically registers DataLoaders into the GraphQL execution context for each request and supports context propagation.

Example registering a mapped batch loader for `Author`:

```java
import graphql.GraphQLContext;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    GraphQLContext context =
                            (GraphQLContext) environment.getContext();
                    String tenantId = context.get("tenantId");

                    return authorService.findByTenantAndIds(tenantId, authorIds)
                            .collectMap(Author::id);
                });
    }
}
```

`registerMappedBatchLoader` takes a set of keys and returns a map from key to result. In this example, `environment.getContext()` provides the batch context; Spring for GraphQL passes the request's `GraphQLContext` here when using the default `BatchLoaderRegistry`. `authorService` returns `Flux<Author>`, and `collectMap(Author::id)` builds the `Mono<Map<Long, Author>>` required by the mapped loader.

A mapped loader is convenient because you do not need to sort results to match input key order. For any key without a matching record, the map omits that key; DataLoader returns the corresponding missing result per the mapped loader contract. If using a positional batch loader, you must return a list with the exact element count and order matching the input keys.

The DataLoader name is inferred from the key/value type pair in this example. If there are multiple loaders of the same type or an explicit name is desired, register by name and use that same name when retrieving the DataLoader in resolvers.

## 6. Using DataLoader in a field resolver

After registering the loader for `Long` and `Author`, a resolver can accept `DataLoader` as a parameter:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorDataLoader) {
        return authorDataLoader.load(book.authorId());
    }
}
```

The resolver only passes `authorId` as the key. The tenant does not need to be passed on every `load` call because the batch loader already receives the tenant from the request context. When multiple books are resolved in one execution, DataLoader batches the author IDs so the batch loader loads them in bulk.

If a resolver uses `Mono` or `Flux`, Spring for GraphQL supports reactive types during field completion. With DataLoader's Java API, `load` normally returns `CompletableFuture`; you can return that future directly or convert it to a reactive type as needed by the resolver.

## 7. Context in batch loader and GraphQLContext share the request lifecycle

With Spring for GraphQL's default integration:

1. `WebGraphQlInterceptor` adds metadata to `GraphQLContext` before execution.
2. Resolvers read context via `@ContextValue` or `DataFetchingEnvironment`.
3. `BatchLoaderRegistry` creates/registers DataLoaders for the current execution.
4. When DataLoader dispatches a batch, `BatchLoaderEnvironment` exposes the corresponding context.
5. The batch loader uses the context to filter data or apply per-request policies.

This avoids passing the same tenant ID through every GraphQL argument, every resolver, and every DataLoader key. It also keeps per-request data from accidentally leaking between two users.

Context does not replace authorization checks. If a tenant ID is placed into context, ensure it has already been verified by the authentication/authorization layer. The batch loader should still call a tenant-scoped service/repository rather than fetching global data and filtering in Java when the database can enforce that filter directly.

## 8. When to use per-key context?

GraphQL Java supports passing per-load context alongside the shared batch context. This is useful when each key requires distinct metadata, such as:

- Each key requires a different locale.
- Each item requires a distinct projection or display mode.
- Per-load tracing metadata needs to be attached.

With APIs supporting key context, callers invoke `DataLoader.load(key, keyContext)`. The batch loader reads per-key contexts via `BatchLoaderEnvironment.getKeyContexts()`.

Do not use per-key context merely to pass a tenant if all keys in the request belong to the same tenant; request-level `GraphQLContext` is simpler. Also remember that when the same key is loaded multiple times with different key contexts, caching and load-coalescing policies must be carefully evaluated. If context alters the result, cache keys must distinguish those cases or caching must be disabled/adjusted accordingly.

## 9. How does context affect the DataLoader cache?

DataLoader typically caches by key within a single GraphQL request. For example, loading `authorId=10` twice in the same request may require only one batch load. This memoization avoids duplicate loading.

If results depend on context, ensure the cache scope and keys are appropriate:

- If the tenant is fixed throughout the request and the DataLoader is created per request, the `authorId` key is usually sufficient because every load shares the same tenant.
- If a single DataLoader can handle multiple tenants within one execution, the tenant must become part of the key or the context/cache policy must prevent sharing incompatible results.
- If using a cache outside request scope, include tenant/locale/authorization dimensions in the cache key or partition the cache accordingly.
- Never use an application-wide singleton DataLoader with user-specific caching without strict isolation mechanisms.

Spring's `BatchLoaderRegistry` creates DataLoaders per GraphQL execution, keeping the default cache scoped to the request. Do not casually alter this scope when optimizing performance; caches outliving a request require dedicated invalidation, partitioning, and security design.

## 10. Context and security: avoid trusting client data

Context often carries values affecting access scope. Identify the trusted source for every entry:

| Context value | Recommended source | Notes |
| --- | --- | --- |
| `tenantId` | Principal, verified token, or authorization-checking tenant resolver | Never blindly trust unverified headers or arguments. |
| `principal` | Spring Security authentication | Do not store raw credentials or access tokens unnecessarily. |
| `locale` | Locale parsed/validated from the request | Use for content only, never as a basis for authorization. |
| `correlationId` | Normalized request header or gateway-generated ID | Use for tracing, not user identity. |
| Feature flags | Server-side feature service/configuration | Never allow clients to enable internal privileges or features. |

The batch loader should apply the tenant filter directly in the query:

```java
public Flux<Author> findByTenantAndIds(String tenantId, Set<Long> ids) {
    return repository.findAllByTenantIdAndIdIn(tenantId, ids);
}
```

Do not load all authors by ID and filter by tenant in memory when the database can apply that predicate. Tenant-scoped queries reduce data exposure risks and avoid loading unauthorized records.

If users have differing permissions per individual author, a tenant filter alone may not suffice. The service must enforce proper authorization, or the batch loader must receive sufficient context to call an authorization-aware service. Never treat hard-to-guess IDs as a security control.

## 11. Do not use ThreadLocal to pass request context

Reactive execution can hop across threads. Therefore, do not rely on arbitrary `ThreadLocal` variables to carry tenant or principal from an interceptor into a batch loader. A request can resume on a different thread, and thread pools are reused for other requests.

Use intentional context mechanisms instead:

- `GraphQLContext` for metadata attached to GraphQL execution.
- `BatchLoaderEnvironment` for context inside batch loaders.
- Reactor Context for metadata in reactive pipelines when Reactor-level integration is needed.
- Spring Security context propagation per application configuration.

Never store request context in a singleton service field or static variable. Multiple requests can access those concurrently, leading to cross-user data leaks.

## 12. Handling missing or invalid context

A batch loader should clearly define its behavior if context is absent or lacks a tenant:

```java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            Object value = environment.getContext();
            if (!(value instanceof GraphQLContext context)) {
                return Mono.error(new IllegalStateException(
                        "GraphQL request context is missing"));
            }

            String tenantId = context.get("tenantId");
            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(new IllegalStateException(
                        "Authorized tenant is required"));
            }

            return authorService.findByTenantAndIds(tenantId, authorIds)
                    .collectMap(Author::id);
        });
```

This example chooses to fail fast if required context is missing. Depending on your application, you can use a dedicated exception and map it to an appropriate GraphQL error. Never silently fall back to an unscoped query when context is missing; doing so can turn a configuration bug into a data leak vulnerability.

If a GraphQL operation can run anonymously, explicitly design which loaders may operate without a principal and which strictly require authenticated context. Never assume every request carries the same privilege level.

## 13. Testing DataLoader context

Tests should prove that context propagates accurately, the batch loader uses the right tenant, and data from other requests never leaks across executions.

Example testing via a GraphQL request with two tenants:

```java
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@Test
void batchLoaderUsesTenantFromGraphQlContext() {
    HttpGraphQlTester tenantGraphQlTester = graphQlTester.mutate()
            .headers(headers -> headers.set("X-Tenant", "tenant-a"))
            .build();
    tenantGraphQlTester.document("""
                    query {
                        books {
                            id
                            author { id name }
                        }
                    }
                    """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Author A");
}
```

This example assumes `graphQlTester` is an `HttpGraphQlTester`, the interceptor reads `X-Tenant`, verifies caller permissions, and sets `tenantId` into `GraphQLContext`, and the `tenant-a` fixture contains an author named `Author A`. Never skip verification steps just to simplify tests.

Additional tests to include:

1. The batch loader receives the right tenant from `GraphQLContext`.
2. Missing context or an invalid tenant fails the request according to policy.
3. Two concurrent requests for different tenants never mix up data.
4. Multiple resolvers loading the same key within one request are batched and cached within the proper scope.
5. Keys with no results do not corrupt the order or results of remaining keys.
6. Locale or feature metadata propagates accurately when the batch loader relies on it.
7. Batch cancellation or errors never leave request state in singletons.

You can check repository call counts to confirm batching, but tests must also assert tenant-scoped results. Counting fewer queries alone is insufficient if the loader accidentally returns another tenant's data.

## 14. Common mistakes

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `environment.getContext()` lacks tenant | Interceptor did not populate `GraphQLContext` or key names differ | Check request interceptor and context key. |
| Resolver reads context, but batch loader cannot | Loader not registered via `BatchLoaderRegistry` or custom context propagation broke | Check the registry used by `GraphQlSource` and `BatchLoaderEnvironment`. |
| Batch loader returns wrong tenant's data | Tenant taken from unverified input/header or cache shared improperly | Read tenant from verified security context, filter in repository, and verify cache scope. |
| Previous request's context leaks into next request | Mutable singleton field or uncleaned `ThreadLocal` | Use per-execution `GraphQLContext` and avoid global state. |
| Same key should yield different results in one request, yet cache returns one value | Result depends on context missing from key/cache policy | Ensure context is fixed per request or include that dimension in the key. |
| Using `@ContextValue` but value is missing | Context key was not added or annotation expects a required value | Check interceptor; configure required/optional per contract. |
| Passing tenant via `@Argument` on every resolver | Mixes request metadata with business inputs and increases spoofing risk | Put verified tenant into `GraphQLContext`. |

## 15. Checklist for designing DataLoader context

1. Identify what metadata is genuinely needed inside the batch loader.
2. Populate request metadata into `GraphQLContext` before GraphQL execution starts.
3. Extract tenant/principal from a verified source and check permissions before placing it into context.
4. Register loaders via `BatchLoaderRegistry` so Spring manages DataLoaders per request.
5. Read context from `BatchLoaderEnvironment` inside the batch loader callback.
6. Use shared request context; only use per-key context when individual keys truly carry distinct metadata.
7. Ensure keys and cache scope never mix results across differing tenants, locales, or permissions.
8. Filter data at the service/repository layer using context and authorization.
9. Never use `ThreadLocal` or mutable singleton fields to hold request metadata.
10. Test missing context, differing contexts across two requests, and duplicate-key loads.

DataLoader context lets batch loaders execute accurately within the current request environment without turning tenant, principal, or locale into repetitive arguments. In Spring for GraphQL, `GraphQLContext` combined with `BatchLoaderRegistry` and `BatchLoaderEnvironment` establishes a clean context propagation path. When context comes from verified sources, caches stay properly scoped, and batch loaders always filter data by permissions, applications reduce N+1 while preventing cross-request data leaks.

References: [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batching) and [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader).
