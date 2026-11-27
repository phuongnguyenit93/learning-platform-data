# GraphQLContext Customization in Spring for GraphQL

During a GraphQL operation, multiple resolvers may need shared request information such as the tenant, authenticated user, locale, correlation ID, or feature flags. Passing these values as explicit business parameters quickly makes resolver signatures unwieldy. GraphQL Java provides `GraphQLContext` to hold shared data scoped to a single execution; Spring for GraphQL adds interceptors and controller method binding mechanisms.

A `GraphQLContext` is created per GraphQL execution and is accessible from multiple data fetchers within the same operation. You can populate the context via `ExecutionInput`, `WebGraphQlInterceptor`, or instrumentation, and read it via `GraphQLContext`, `DataFetchingEnvironment`, or `@ContextValue`. For data that only needs to flow down one field branch, use local context via `DataFetcherResult` and `@LocalContextValue`.

After this lesson, you will be able to:

- Understand the lifecycle and scope of `GraphQLContext`.
- Distinguish main context, local context, Reactor Context, and Spring Security context.
- Create context using `ExecutionInput.Builder`.
- Populate metadata into context via `WebGraphQlInterceptor`.
- Use `HttpRequestHeaderInterceptor` for suitable headers.
- Read context in `@QueryMapping`, `@SchemaMapping`, data fetchers, and batch loaders.
- Pass data down a subtree via `DataFetcherResult`.
- Understand context propagation across WebFlux, Spring MVC, DataLoader, WebSocket, and RSocket.
- Design context safely with respect to request isolation, tenant boundaries, and access control.
- Test context injection, local context, and request isolation.

## 1. What Problem Does GraphQLContext Solve?

A single operation can invoke multiple resolvers across multiple nesting levels:

```graphql
query Dashboard {
    currentUser {
        id
        name
        orders {
            id
            total
        }
    }
    recommendations {
        id
        title
    }
}
```

The `currentUser`, `orders`, and `recommendations` resolvers may all need the same tenant, locale, or user info. If each resolver reads HTTP headers directly, reaches into `ThreadLocal`, or duplicates security-context lookup logic, the code becomes transport-coupled and hard to test.

`GraphQLContext` provides one shared place for execution metadata. An interceptor can populate metadata once before GraphQL Java executes; data fetchers then read those values without requiring clients to repeat them across every field argument.

Values well suited for context include:

- Authenticated and verified tenant.
- Actor/user ID or a safe principal snapshot.
- Correlation ID, trace metadata, and request origin.
- Request locale or timezone.
- Server-determined feature flags.
- Request-scoped policy or service facades.

Context is internal execution data. It does not appear automatically in the GraphQL response and is not part of the schema that clients can query directly.

## 2. What Is GraphQLContext?

`graphql.GraphQLContext` is a key-value structure from GraphQL Java. The context is bound to a single execution and can be accessed from `ExecutionInput`, `Instrumentation`, and `DataFetchingEnvironment`.

```java
GraphQLContext context = GraphQLContext.newContext()
        .put("tenantId", "tenant-42")
        .put("correlationId", "req-9f81")
        .build();
```

`GraphQLContext` supports key-based lookup, existence checks, and updates. Its internal structure is designed to be thread-safe so multiple resolvers can access it within one execution. Still, initialize values before resolution starts and prefer immutable value objects. Having multiple resolvers mutate a shared mutable object stored inside the context can still cause race conditions on that object itself.

Keys and values added to the context must be non-`null`. If a value is absent, omit the key from the context, read it as `Optional`, or use an explicit default value. Never call `put(key, null)`.

## 3. Distinguishing Different Types of Context

The word "context" appears across multiple layers of an application. Distinguish them before choosing how to pass data:

| Type | Scope | Purpose |
| --- | --- | --- |
| `GraphQLContext` | Entire GraphQL execution | Shared metadata for resolvers, instrumentation, and batch loaders |
| Local context | One branch of the field tree and its descendants | Data passed only from a parent resolver down to descendants |
| Reactor `Context` | One reactive subscription chain | Propagating metadata across `Mono`/`Flux` without thread affinity |
| Spring Security context | Current authentication | Principal, `Authentication`, and request authorities |
| HTTP request attributes | One HTTP request | Metadata set by web filters/interceptors at the transport layer |
| GraphQL variables/arguments | Operation or field per schema | Business inputs supplied by the client |

Never use GraphQL variables as a substitute for internal metadata. For instance, tenant or user identity must be established by the security layer, not accepted blindly from a client-supplied argument.

## 4. Creating GraphQLContext via ExecutionInput

When invoking GraphQL Java directly, you can populate context on `ExecutionInput.Builder`:

```java
ExecutionInput executionInput = ExecutionInput.newExecutionInput()
        .query("{ books { id title } }")
        .graphQLContext(context -> context
                .put("tenantId", "tenant-42")
                .put("correlationId", "req-9f81"))
        .build();

ExecutionResult result = graphQL.execute(executionInput);
```

`graphQLContext(...)` accepts a `Consumer<GraphQLContext.Builder>` or a `Map` of context values. The builder form lets you declare individual keys without allocating temporary maps.

GraphQL Java still retains the older `ExecutionInput.Builder.context(Object)` API, but it is deprecated. When passing context to data fetchers, use `graphQLContext(...)` and `ExecutionInput.getGraphQLContext()`.

In a Spring Boot application, most HTTP/WebSocket requests flow through `WebGraphQlHandler` and `WebGraphQlInterceptor`. You do not need to construct `ExecutionInput` manually per request when an interceptor is the right place to populate context.

## 5. Populating Context with WebGraphQlInterceptor

`WebGraphQlInterceptor` runs before and after GraphQL Java execution for HTTP and WebSocket. An interceptor can inspect transport details, customize `ExecutionInput`, add response headers, or process `ExecutionResult`.

Example adding a correlation ID and locale to context:

```java
import java.util.Locale;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RequestContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");
        Locale locale = request.getLocale() != null ? request.getLocale() : Locale.ROOT;

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    if (correlationId != null && !correlationId.isBlank()) {
                        context.put("correlationId", correlationId);
                    }
                    context.put("requestLocale", locale);
                }).build());

        return chain.next(request);
    }
}
```

`request.configureExecutionInput(...)` updates the `ExecutionInput` that Spring prepares for GraphQL Java. The context is bound to the current operation; resolvers within that operation can read `correlationId` and `requestLocale`.

In this example, the correlation ID is metadata for logging and tracing. If the client omits the header, the context omits that key. Never insert `null` into `GraphQLContext`.

## 6. Using the Built-in HttpRequestHeaderInterceptor

If you only need to copy selected HTTP headers into `GraphQLContext`, Spring for GraphQL provides `HttpRequestHeaderInterceptor`:

```java
@Configuration(proxyBeanMethods = false)
public class GraphQlInterceptorConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Correlation-Id")
                .build();
    }
}
```

Controllers can then read the value using `@ContextValue`:

```java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestInfo(@ContextValue("X-Correlation-Id") String correlationId) {
        return correlationId;
    }
}
```

This interceptor is handy for simple header metadata. When normalization, validation, or combining multiple values is required, write a dedicated `WebGraphQlInterceptor` to control the logic.

Do not trust arbitrary headers automatically. Headers like `X-Tenant-Id`, `X-User-Id`, or `X-Role` can be spoofed by clients. Only put them into context after a gateway or security filter has authenticated and verified the values. For identity, prefer the Spring Security principal over reading headers directly.

## 7. Reading Context in Annotated Controllers

There are two common ways: receiving the full `GraphQLContext` or binding a single key with `@ContextValue`.

Receiving the full context:

```java
@QueryMapping
public List<Book> books(GraphQLContext context) {
    String tenantId = context.get("tenantId");
    return bookService.findVisibleToTenant(tenantId);
}
```

Binding a specific key:

```java
@QueryMapping
public List<Book> books(@ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleToTenant(tenantId);
}
```

`@ContextValue` reads an attribute from the main `GraphQLContext` of `DataFetchingEnvironment`. The key name is specified via `name` or its alias `value`.

By default `required = true`: if the key is absent, Spring raises an error when binding the method argument. If a key is genuinely optional, use `required = false` or `Optional`:

```java
@QueryMapping
public List<Book> books(
        @ContextValue(name = "preferredLocale", required = false)
        Optional<Locale> preferredLocale) {

    return bookService.findAll(preferredLocale.orElse(Locale.ROOT));
}
```

Do not use `@ContextValue` to read GraphQL field arguments. Field arguments belong to `@Argument`; context is server-supplied execution metadata.

## 8. Reading Context from DataFetchingEnvironment

When writing a data fetcher directly or needing broader execution details, use `DataFetchingEnvironment`:

```java
DataFetcher<List<Book>> booksFetcher = environment -> {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");
    return bookService.findVisibleToTenant(tenantId);
};
```

`environment.getGraphQlContext()` returns the main context. `environment.getLocalContext()` returns the local context passed down by the parent field, if any.

In annotated controllers, there is no need to inject `DataFetchingEnvironment` just to read a single key; `@ContextValue` is usually clearer. Use `environment` when you also need the selection set, execution path, source object, arguments, or other GraphQL Java details.

## 9. Passing Data Down a Branch with Local Context

The main `GraphQLContext` fits data shared across the entire operation. When a resolver preloads data needed only by its child fields, consider local context so that data is not exposed query-wide.

A Spring controller can return `DataFetcherResult<T>` and attach local context:

```java
@QueryMapping
public DataFetcherResult<Book> bookById(@Argument Long id) {
    BookAndAuthor result = bookService.findBookAndAuthor(id);

    GraphQLContext localContext = GraphQLContext.newContext()
            .put("prefetchedAuthor", result.author())
            .build();

    return DataFetcherResult.<Book>newResult()
            .data(result.book())
            .localContext(localContext)
            .build();
}
```

The child field reads the local value:

```java
@SchemaMapping(typeName = "Book", field = "relatedBooks")
public List<Book> relatedBooks(
        Book book,
        @LocalContextValue("prefetchedAuthor") Author author) {

    return bookService.findRelatedBooks(book, author);
}
```

Local context propagates down to child fields of the parent result and descendant branches in the execution tree. It is not a request-wide store and does not automatically leak to sibling branches.

## 10. Distinguishing @ContextValue and @LocalContextValue

These two annotations look similar but read from different sources:

| Annotation | Data Source | Scope |
| --- | --- | --- |
| `@ContextValue` | Main `GraphQLContext` | Entire execution |
| `@LocalContextValue` | Local context in `DataFetchingEnvironment` | One field branch and its descendants |

For example, use `@ContextValue` for tenant ID because every resolver in the request needs the authenticated tenant. Use `@LocalContextValue` for `prefetchedAuthor` because only `Book.relatedBooks` and descendants on that branch need the preloaded value.

Do not place data specific to a single parent object into the main context if local context solves it. Doing so can cause collisions when multiple parent fields write the same key or when resolvers run concurrently.

## 11. GraphQLContext in BatchLoaderRegistry

Spring for GraphQL provides `BatchLoaderRegistry` for registering batch loaders. A batch loading function can read the same `GraphQLContext` seen by `@SchemaMapping` methods.

```java
@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    String tenantId = environment.getContext().get("tenantId");
                    return authorService.findVisibleByIds(tenantId, authorIds)
                            .collectMap(Author::id);
                });
    }
}
```

Resolver using the loader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
```

Spring-managed `BatchLoaderRegistry` registers DataLoaders per request and handles context propagation into batch functions. That is why you should use Spring's registry instead of creating a global DataLoader or registering loaders manually and bypassing context integration.

For simple relationships, `@BatchMapping` can also receive `GraphQLContext` or `@ContextValue` directly:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> authors(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {

    Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findVisibleByIds(tenantId, authorIds)
            .collectMap(Author::id)
            .map(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    Author author = authorsById.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
}
```

This method illustrates using tenant context inside a batch mapping. If an author is not found, that book key is omitted from the map and the field resolves to `null`; the schema must allow null or the resolver must enforce the appropriate error contract. Use `BatchLoaderRegistry` when you need finer control over keys, options, or complex batch logic.

Because `Book` serves as the key of `Map<Book, Author>`, the `Book` class must have stable `equals()` and `hashCode()` implementations. For mutable entities, avoid modifying fields involved in equality/hashCode while the object is used as a map key.

## 12. Local Context in Batch Loading

`BatchLoaderEnvironment` exposes two kinds of context data:

- `getContext()` returns the shared main `GraphQLContext` for the execution.
- `getKeyContexts()` provides the per-key local context passed to each `DataLoader` load call.

This is useful when each `DataLoader.load(key, localContext)` call passes parent-specific data. The batch function can read the shared tenant from the main context while using per-key contexts to handle individual loads.

Do not assume every key in a batch shares the same local context. If batch logic depends on local context, preserve the mapping between each key and its corresponding context. If filter parameters change the loaded result, consider including the filter inside a composite key rather than relying on a shared mutable context.

## 13. GraphQLContext and Reactor Context in WebFlux

`GraphQLContext` and Reactor Context serve two different purposes:

- `GraphQLContext` is GraphQL execution's map and can be read directly inside data fetchers.
- Reactor Context belongs to the reactive subscription chain and is read via `deferContextual` in `Mono`/`Flux`.

Spring for GraphQL supports propagating Reactor Context from the WebFlux request chain down to reactive data fetchers. A `WebGraphQlInterceptor` can add values to Reactor Context using `contextWrite`:

```java
@Component
public class ReactorMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");
        Mono<WebGraphQlResponse> response = chain.next(request);

        if (correlationId == null || correlationId.isBlank()) {
            return response;
        }

        return response.contextWrite(context ->
                context.put("correlationId", correlationId));
    }
}
```

A reactive service can read the value during subscription:

```java
public Mono<Book> findBook(Long id) {
    return Mono.deferContextual(contextView -> {
        String correlationId = contextView.getOrDefault("correlationId", "unknown");
        return bookRepository.findById(id)
                .doOnNext(book -> log.debug("Loaded book, request={}", correlationId));
    });
}
```

If resolvers only need to read metadata such as tenant or locale from GraphQL execution, `GraphQLContext`/`@ContextValue` is usually simpler. Use Reactor Context when a reactive pipeline or downstream library needs metadata across operators.

## 14. Context Propagation in Spring MVC

In Spring MVC, GraphQL Java may invoke data fetchers on a different thread than the initial servlet thread—for instance, when a resolver returns a `CompletableFuture` or an interceptor switches execution threads.

Spring for GraphQL supports propagating `ThreadLocal` values from the request thread to threads invoked by GraphQL. To propagate a custom `ThreadLocal`, implement `io.micrometer.context.ThreadLocalAccessor`:

```java
public class TenantContextAccessor implements ThreadLocalAccessor<TenantContext> {

    @Override
    public Object key() {
        return TenantContextAccessor.class.getName();
    }

    @Override
    public TenantContext getValue() {
        return TenantContextHolder.get();
    }

    @Override
    public void setValue(TenantContext value) {
        TenantContextHolder.set(value);
    }

    @Override
    public void reset() {
        TenantContextHolder.clear();
    }
}
```

Register the accessor at startup:

```java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantContextAccessor());
```

You can also register accessors via `ServiceLoader`. The accessor must reset the value after the snapshot is restored to avoid leaking data across requests sharing pooled threads.

Whenever possible, pass data explicitly via `GraphQLContext`. Reserve `ThreadLocal` for legacy libraries or components that strictly require an imperative request context.

## 15. GraphQlContextAccessor and Micrometer Context Propagation

Spring for GraphQL provides `GraphQlContextAccessor`, a Micrometer Context Propagation `ContextAccessor` that reads and writes values between `GraphQLContext` and contexts managed by Micrometer.

This accessor is automatically registered via `ServiceLoader`. As a result, context propagation can bridge values across `GraphQLContext`, Reactor Context, and `ThreadLocal` when corresponding accessors exist.

Spring for GraphQL also provides `ContextPropagationHelper` to assist with capturing/propagating context and cancellation tied to GraphQL execution. If low-level customization is required, use the API of your active Spring GraphQL version; avoid copying code from snapshot releases into applications running older versions.

## 16. Context and Spring Security

`GraphQLContext` is not a substitute for Spring Security. Spring for GraphQL can inject `Principal` or `@AuthenticationPrincipal` into annotated controllers when a Spring Security context is present:

```java
@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findByOwner(principal.getName());
}
```

If resolvers also need a verified tenant or policy, place an actor snapshot into `GraphQLContext` from the security layer:

```java
public record RequestActor(String userId, String tenantId) {
}
```

Once authentication and tenant membership are verified, the interceptor or integration layer puts `RequestActor` into context. Resolvers read this snapshot to invoke services.

Never take `userId`, `role`, or `tenantId` from client-sent headers and treat them as authenticated identity. Do not place raw bearer tokens into context when resolvers only need a user ID or verified claims. Keep only the minimal required info and continue enforcing authorization at service/domain boundaries.

## 17. GraphQLContext in WebSocket

GraphQL over WebSocket has a longer lifecycle than HTTP requests. One connection can carry many queries, mutations, and subscriptions. Consequently, distinguish connection-level metadata from per-operation metadata.

`WebSocketGraphQlInterceptor` extends `WebGraphQlInterceptor` and provides callbacks for connection start/end in addition to intercepting each request on the connection. Spring provides `AuthenticationWebSocketInterceptor` for WebMVC and WebFlux to extract authentication from the `connection_init` message and propagate `SecurityContext` to subsequent operations.

Guidelines:

- Authentication can be associated with the connection, yet `GraphQLContext` should still be prepared separately per operation.
- Never keep one shared mutable `GraphQLContext` across all operations on a socket.
- Handle cancellation and cleanup when a subscription ends or the connection closes.
- Re-check permissions when policies or user status can change during the lifetime of a connection.
- Within an interceptor chain, include at most one interceptor of type `WebSocketGraphQlInterceptor`.

## 18. Context with RSocket

If the application uses GraphQL over RSocket, Spring provides `RSocketQlInterceptor`, analogous to `WebGraphQlInterceptor`. The interceptor can customize `ExecutionInput` before GraphQL Java runs and process `ExecutionResult` afterward.

Do not assume `WebGraphQlInterceptor` is invoked for RSocket. Use the transport-appropriate interceptor and extract shared logic into a common service/helper to avoid divergence across HTTP, WebSocket, and RSocket.

## 19. GraphQLContext in Instrumentation

GraphQL Java `Instrumentation` can read or populate context when execution begins. This is helpful for metadata or options controlling the GraphQL engine.

Example recording the execution start timestamp:

```java
public class ExecutionMetadataInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put("executionStartedAt", Instant.now());
        return SimpleInstrumentationContext.noOp();
    }
}
```

Spring Boot can detect `Instrumentation` beans and add them to `GraphQlSource`. Instrumentation fits GraphQL-engine-level logic such as timing, attaching execution metadata, or configuring subscription options. It does not replace interceptors when reading HTTP headers, cookies, or transport details is needed.

## 20. Returning Context Data in HTTP Responses

Context is not automatically serialized into the response. If you need a value written to context by a resolver to update the HTTP response, an interceptor can inspect the context after execution finishes:

```java
public class ResponseMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        return chain.next(request).doOnNext(response -> {
            GraphQLContext context = response.getExecutionInput().getGraphQLContext();
            String requestTag = context.get("responseTag");
            if (requestTag != null) {
                response.getResponseHeaders().add("X-Request-Tag", requestTag);
            }
        });
    }
}
```

This example illustrates an interceptor reading a value written to context by a resolver. Expose only publicly safe metadata in response headers. Never echo access tokens, tenant secrets, or internal details back to clients.

## 21. Key Naming Conventions and Data Types

When multiple interceptors, controllers, and batch loaders write to context, prevent key collisions:

```java
public final class GraphQlContextKeys {

    public static final String CORRELATION_ID = "app.correlationId";
    public static final String REQUEST_ACTOR = "app.requestActor";
    public static final String REQUEST_LOCALE = "app.requestLocale";

    private GraphQlContextKeys() {
    }
}
```

Use strongly typed value objects instead of scattering many separate fields:

```java
public record RequestMetadata(
        String correlationId,
        Locale locale,
        RequestActor actor) {
}
```

Context can hold any object, but objects should be immutable, scoped to a single execution, and avoid holding references to large request/response objects after the request completes.

## 22. Common Pitfalls

- **Treating `GraphQLContext` like a global variable:** data from one request can leak into another.
- **Putting `null` into context:** `GraphQLContext` requires non-null keys and values.
- **Treating headers as identity:** clients can spoof tenants or users if headers are unverified.
- **Confusing context with GraphQL arguments:** context is internal metadata; arguments are schema inputs.
- **Using main context for branch-only data:** can cause clashes between parent fields; local context fits better.
- **Using local context for request-wide data:** resolvers on sibling branches will not see that value.
- **Confusing Reactor Context with `GraphQLContext`:** they have different lifecycles and access APIs.
- **Relying on `ThreadLocal` in WebFlux:** threads can switch between operators; use Reactor Context or `GraphQLContext`.
- **Forgetting to reset `ThreadLocal`:** risks leaking metadata across requests reusing pooled threads.
- **Registering global DataLoaders manually:** loaders may share caches and contexts across executions; use `BatchLoaderRegistry`.
- **Mutating context concurrently from parallel resolvers:** can cause race conditions in stored object values.
- **Storing raw tokens or sensitive data in context:** widens exposure during logging or debugging.
- **Using `WebGraphQlInterceptor` for RSocket:** that interceptor does not apply to RSocket transport.
- **Testing resolvers directly and assuming interceptors work:** tests must go through `WebGraphQlHandler` to run the interceptor chain.

## 23. Testing GraphQLContext

When context is populated by a `WebGraphQlInterceptor`, test through `WebGraphQlTester` so the request passes through the interceptor chain:

```java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
        .headers(headers -> headers.set("X-Correlation-Id", "test-request-42"))
        .build();

tester.document("""
        query {
            requestMetadata
        }
        """)
    .execute()
    .path("requestMetadata")
    .entity(String.class)
    .isEqualTo("test-request-42");
```

This example assumes the schema has a `requestMetadata` field returning the correlation ID from `@ContextValue`. You can use `WebGraphQlTester.create(webGraphQlHandler)` if no custom header setup is required.

If testing `ExecutionGraphQlService` directly, the web interceptor chain does not run. For that style of test, configure `ExecutionInput` or context using `ExecutionGraphQlServiceTester`'s builder.

Scenarios worth testing:

1. Header metadata is placed into `GraphQLContext`.
2. `@ContextValue` and `GraphQLContext` parameters read the same value.
3. Missing required keys produce a clear error.
4. Missing optional keys are handled cleanly via `Optional` or `required = false`.
5. Two requests with different correlation IDs never mix up each other's context.
6. Local context appears only on the intended child branch.
7. Batch loaders receive the correct tenant from the main `GraphQLContext`.
8. Reactive resolvers read Reactor Context when running through WebFlux.
9. `ThreadLocalAccessor` is reset after execution.
10. WebSocket operations receive the proper authentication context.
11. Untrusted headers cannot alter the tenant or principal.
12. Context does not appear in responses unless the server explicitly writes it to headers/extensions.

## 24. GraphQLContext Design Workflow

When sharing metadata across multiple resolvers, follow these steps:

1. Identify which values truly need to be shared execution-wide.
2. Separate internal metadata from GraphQL variables/arguments.
3. Authenticate data sources before placing tenant, actor, or policy into context.
4. Build `GraphQLContext` per `ExecutionInput` or inside a `WebGraphQlInterceptor`.
5. Use namespaced keys and strongly typed value objects.
6. Read values via `GraphQLContext`, `DataFetchingEnvironment`, or `@ContextValue`.
7. Use local context via `DataFetcherResult` when data belongs to a single branch.
8. Use `BatchLoaderRegistry` so batch loaders receive context and context propagation.
9. Use Reactor Context for reactive pipelines and `ThreadLocalAccessor` for legacy MVC `ThreadLocal`s.
10. Handle connection-level and operation-level metadata separately for WebSockets.
11. Test through the appropriate transport/interceptor layer.
12. Avoid keeping sensitive data or unnecessary mutable objects in context.

`GraphQLContext` is the place to share metadata within a single GraphQL execution. Spring for GraphQL lets you populate data via `WebGraphQlInterceptor`, read it via `@ContextValue` or `GraphQLContext`, and pass branch-specific data down child subtrees via local context. When working with WebFlux, MVC, DataLoader, WebSocket, or RSocket, understand each layer's context propagation mechanism. Designing context per request, validating data sources, and testing request isolation keeps metadata sharing across resolvers safe.

## References

- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: Context and Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4.1 — @ContextValue API](https://docs.spring.io/spring-graphql/docs/1.4.1/api/org/springframework/graphql/data/method/annotation/ContextValue.html)
- [Spring for GraphQL 1.4.6 — WebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL 1.4.3 — GraphQlContextAccessor API](https://docs.spring.io/spring-graphql/docs/1.4.3/api/org/springframework/graphql/execution/GraphQlContextAccessor.html)
- [GraphQL Java — ExecutionInput.Builder API](https://javadoc.io/doc/com.graphql-java/graphql-java/23.1/graphql/ExecutionInput.Builder.html)
- [GraphQL Java — GraphQLContext API](https://javadoc.io/doc/com.graphql-java/graphql-java/22.4/graphql/GraphQLContext.html)
