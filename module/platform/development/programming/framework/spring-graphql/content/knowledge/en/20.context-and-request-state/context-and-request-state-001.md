# GraphQLContext

## Objectives

After this lesson, you will be able to:

- Explain the role of `GraphQLContext` in a single GraphQL execution.
- Distinguish request-level context from source objects, field arguments, and local context.
- Pass metadata from an HTTP request into GraphQL execution using `WebGraphQlInterceptor`.
- Read context in an annotated controller using `@ContextValue` or `GraphQLContext`.
- Use local context to pass data within a branch of the query tree.
- Pass context to a DataLoader and batch loader.
- Distinguish `GraphQLContext`, Reactor `Context`, and `ThreadLocal`.
- Combine GraphQL context with Spring Security without turning client-supplied data into a trusted identity.
- Keep request state isolated between concurrent GraphQL requests.

## 1. What problem does GraphQLContext solve?

A GraphQL operation can invoke many resolvers. These resolvers often need common metadata such as:

- The authenticated user.
- The active tenant or organization.
- A correlation ID to correlate logs across multiple services.
- Locale or formatting preferences.
- Feature flags or tracing information.
- Access policies already determined at the security layer.

If these values are passed through individual field arguments, the schema becomes mixed between business data and request metadata. If they are stored in mutable fields of a singleton controller, concurrent requests risk accidentally using each other's data.

`GraphQLContext` provides a shared data area scoped to a single GraphQL execution. DataFetchers within the same execution can read this context without adding arguments to the schema.

For example, a query might fetch user information, orders, and transaction history. All of those resolvers may need `tenantId` and `correlationId`, even though those two values are not inputs declared by the client in the SDL.

## 2. Where does GraphQLContext sit in the request lifecycle?

For HTTP or WebSocket, Spring for GraphQL lets you intercept the request before calling GraphQL Java through `WebGraphQlInterceptor`. The interceptor can read transport information, add data to `ExecutionInput`, and then pass the request to the next interceptor and the GraphQL engine.

General flow:

~~~mermaid
flowchart TD
    A[HTTP or WebSocket request] --> B[WebGraphQlInterceptor]
    B --> C[Read headers and metadata]
    C --> D[Add GraphQLContext to ExecutionInput]
    D --> E[ExecutionGraphQlService]
    E --> F[GraphQL Java engine]
    F --> G[Query / Mutation / Subscription resolvers]
    G --> H[Response]
~~~

`GraphQLContext` is bound to a single GraphQL execution. It is not a global application object and should not be stored in a singleton to be reused across requests.

A WebSocket request can carry multiple operations over time. Each operation still has its own execution context; connection-level authentication state must be transferred to each request via the appropriate WebSocket interceptor mechanism.

## 3. Populating GraphQLContext with WebGraphQlInterceptor

`WebGraphQlInterceptor` allows reading HTTP request information and customizing `ExecutionInput` before GraphQL Java executes the operation.

For example, generating or accepting a correlation ID from an HTTP header:

~~~java
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }

        String value = correlationId;

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", value)
                ).build()
        );

        return chain.next(request);
    }
}
~~~

Steps:

1. The interceptor receives `WebGraphQlRequest`.
2. Reads the `X-Correlation-Id` header.
3. Generates a new ID if the client did not send one.
4. Uses `configureExecutionInput` to add the value to `GraphQLContext`.
5. Calls `chain.next(request)` to continue processing.

`correlationId` is tracing metadata. If the client sends this header itself, the server can use it as a correlation label after applying appropriate length and character validation rules. Do not use an arbitrary header such as `X-User-Id` as proof of user authentication.

If multiple interceptors add metadata, standardize the keys and how values are combined so that a later interceptor does not accidentally overwrite data added by an earlier interceptor.

If the application only needs to forward certain HTTP headers into the context, Spring for GraphQL also provides `HttpRequestHeaderInterceptor`:

~~~java
@Configuration
public class GraphQlInterceptorConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Locale")
                .build();
    }
}
~~~

Mapped headers are placed into the GraphQL context so controllers can read them with `@ContextValue`. Only map headers that are actually needed; do not copy all headers into the context.

## 4. Reading context with @ContextValue

In an annotated controller, `@ContextValue` retrieves a value by key from the execution's GraphQLContext.

The SDL does not need to declare a `correlationId` argument:

~~~graphql
type Query {
  requestId: String!
}
~~~

Controller:

~~~java
@Controller
public class RequestMetadataController {

    @QueryMapping
    public String requestId(
            @ContextValue("correlationId") String correlationId) {

        return correlationId;
    }
}
~~~

The client only needs to call:

~~~graphql
query {
  requestId
}
~~~

The resolver receives `correlationId` from the context prepared by the interceptor. The client cannot alter the value by adding a GraphQL argument with the same name, because these are two different data sources.

Use `@ContextValue` when a method only needs one or a few specific keys. This keeps the method signature clear and avoids coupling the resolver to the entire context structure.

## 5. Receiving the entire GraphQLContext in a controller

If a method needs multiple values or needs to read/write the context, it can accept `graphql.GraphQLContext` directly as a parameter.

~~~java
import graphql.GraphQLContext;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public List<Order> orders(GraphQLContext context) {
        String tenantId = context.get("tenantId");
        String correlationId = context.get("correlationId");

        return orderService.findByTenant(tenantId, correlationId);
    }
}
~~~

In this example, `tenantId` and `correlationId` are placed into the context before the resolver runs. The service receives those values for querying and logging.

You can use `DataFetchingEnvironment` if you need access to the context alongside other metadata:

~~~java
@QueryMapping
public List<Order> orders(DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return orderService.findByTenant(tenantId);
}
~~~

For typical controllers, `@ContextValue` or a `GraphQLContext` parameter is usually more readable than accepting the entire `DataFetchingEnvironment`.

## 6. How GraphQLContext differs from source objects and arguments

These values can all appear in a single resolver, yet they carry different meanings:

| Component | Source | Scope | Example |
|---|---|---|---|
| Source object | Result of the parent field | One branch in the query tree | The `Book` currently being resolved |
| `@Argument` | Input for the current field sent by the client | One field | `first = 10` |
| `GraphQLContext` | Transport interceptor or execution setup | Entire GraphQL execution | `correlationId`, `tenantId` |
| Local context | Explicitly passed down by the parent field | One child branch | Author preloaded for Book |
| Reactor Context | Reactive pipeline | A reactive chain | Trace metadata in WebFlux |

Example combining source, argument, and context:

~~~graphql
type Book {
  id: ID!
  reviews(first: Int): [Review!]!
}
~~~

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer first,
        @ContextValue("tenantId") String tenantId) {

    return reviewService.findByBook(
            book.getId(), first, tenantId);
}
~~~

- `Book book` is the source object returned from the parent field.
- `first` is the argument of the `Book.reviews` field.
- `tenantId` is shared metadata for the GraphQL execution.

Do not put data that belongs in an argument into GraphQLContext just to avoid declaring it in the SDL. Arguments describe the input of a field; context describes metadata spanning the execution.

## 7. Using local context for a query branch

The main GraphQLContext is shared across the entire execution. Sometimes a parent field has already loaded data that only child fields of that object need. Putting branch-specific data into the global context makes the context harder to understand and can cause key collisions.

GraphQL Java provides local context. Spring for GraphQL allows a controller to return `DataFetcherResult<T>` to pass both the result object and local context to child fields.

For example, when loading a Book, the service has already loaded the Author:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public DataFetcherResult<Book> book(@Argument Long id) {
        BookAndAuthor result = bookService.findBookAndAuthor(id);

        GraphQLContext localContext = GraphQLContext.getDefault()
                .put("prefetchedAuthor", result.author());

        return DataFetcherResult.<Book>newResult()
                .data(result.book())
                .localContext(localContext)
                .build();
    }

    @SchemaMapping
    public Author author(
            Book book,
            @LocalContextValue("prefetchedAuthor") Author author) {
        return author;
    }
}
~~~

Here:

- The `data` value is the Book source object for child fields.
- `localContext` carries the preloaded Author.
- `@LocalContextValue` reads data from the local context of the current branch.

Local context is propagated down to child fields belonging to that branch. Another field in the Query branch does not automatically see this value.

Use local context when data has a narrow scope and has already been prepared by the parent field. If data needs to be used across multiple independent fields or multiple branches of the operation, consider GraphQLContext or an appropriate DataLoader.

## 8. Distinguishing @ContextValue and @LocalContextValue

The two annotations have similar names, but they read from two different context areas:

| Annotation | Source | Scope |
|---|---|---|
| `@ContextValue` | Main GraphQLContext | Entire execution |
| `@LocalContextValue` | Local GraphQLContext | Branch passed down by the parent field |

Example:

~~~java
@SchemaMapping
public List<Book> relatedBooks(
        Book book,
        @ContextValue("tenantId") String tenantId,
        @LocalContextValue("prefetchedAuthor") Author author) {

    return bookService.findRelated(
            book.getId(), tenantId, author.id());
}
~~~

The resolver receives:

- `tenantId` from the main context, shared across the entire execution.
- `author` from the local context passed down by the parent field.

If a key is missing from the expected context area, parameter binding may fail or produce an unexpected null/absent value depending on configuration. Ensure the parent field always creates the local context when a child field requires it.

## 9. GraphQLContext and DataLoader

Spring for GraphQL integrates `BatchLoaderRegistry` with the execution's GraphQLContext. A batch loader can accept `BatchLoaderEnvironment` and read the same context used by DataFetchers or annotated controllers.

For example, a multi-tenant application needs to load Authors by ID and tenant:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    GraphQLContext context = environment.getContext();
                    String tenantId = context.get("tenantId");

                    return authorService
                            .findAllByIdsAndTenant(authorIds, tenantId)
                            .collectMap(Author::id);
                });
    }
}
~~~

Resolver using the DataLoader:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
~~~

The batch loader receives a set of IDs and the current tenant from the context, then loads data only within that tenant. This is how you keep data partitioning conditions consistent across field resolvers.

Spring registers DataLoaders per GraphQL request. Do not create a singleton DataLoader shared across requests, because the DataLoader's cache could retain data from a previous request.

When local context is passed for each DataLoader call, `BatchLoaderEnvironment` also provides `keyContexts` to access the local context corresponding to each key. This is useful when each parent object has its own metadata that the batch loader needs to keep mapped properly.

## 10. GraphQLContext does not replace Spring Security

GraphQLContext is a mechanism for passing metadata to DataFetchers. It does not authenticate users itself and does not enforce authorization on its own.

Do not take a client-supplied header or argument and treat it as an authenticated identity:

~~~java
// Do not use a client-supplied value as a trusted identity.
@QueryMapping
public List<Order> orders(@Argument String userId) {
    return orderService.findByUserId(userId);
}
~~~

If the client can pass any `userId`, they could attempt to access someone else's data if the service does not check permissions.

With Spring Security, a controller can accept `Principal` or `@AuthenticationPrincipal` from the SecurityContext:

~~~java
@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findVisibleTo(principal.getName());
}
~~~

You can use method security or permission checks in the service to protect data. GraphQLContext can still carry a verified tenant ID, correlation ID, or policies derived from the authenticated identity.

Principles:

- Authenticate at the Spring Security layer or an appropriate authentication mechanism.
- Use Principal or Authentication to obtain a trusted identity.
- Only place verified information into the context.
- Perform authorization checks in the service or field resolver according to business requirements.
- Do not treat the presence of a key in GraphQLContext as proof that the user is authorized to access data.

## 11. Context with WebSocket and Subscriptions

With GraphQL over WebSocket, a connection can be long-lived and carry multiple operations. `WebSocketGraphQlInterceptor` extends `WebGraphQlInterceptor`, supporting handling of the connection lifecycle and the GraphQL requests on that connection.

Spring for GraphQL provides built-in `AuthenticationWebSocketInterceptor` implementations for Spring MVC and WebFlux. They extract authentication credentials from the `connection_init` payload, authenticate them, and propagate `SecurityContext` to subsequent requests on the connection.

Distinguish between:

- WebSocket connection state: information tied to the connection and its lifecycle.
- GraphQLContext: metadata of a single GraphQL execution.
- Subscription publisher: an event stream that lives until completion or cancellation.

Do not assume a single GraphQLContext object can be kept as a global session for the entire connection. The WebSocket interceptor mechanism is responsible for transferring the necessary authentication state to each request. For long-lived subscriptions, consider token expiration, permission revocation, and cancelling the subscription when the identity is no longer valid.

## 12. GraphQLContext and Reactor Context

These two context types do not replace each other.

`GraphQLContext` is the explicit context of a GraphQL execution, passed to DataFetchers and controllers. `Reactor Context` is the context attached to a reactive subscriber chain, commonly used in WebFlux to propagate metadata across reactive operators.

Spring for GraphQL supports propagating Reactor Context from the WebFlux request handling chain to reactive DataFetchers. For example, an interceptor can add metadata to the Reactor Context:

~~~java
@Component
public class TraceReactorContextInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String traceMarker = "graphql-request";

        return chain.next(request)
                .contextWrite(context ->
                        context.put("traceMarker", traceMarker));
    }
}
~~~

A reactive service can read the value within the pipeline:

~~~java
public Mono<Book> findBook(String id) {
    return Mono.deferContextual(contextView -> {
        String traceMarker = contextView.get("traceMarker");
        return repository.findById(id)
                .doOnNext(book -> log.debug(
                        "Loaded book for {}", traceMarker));
    });
}
~~~

This example illustrates reactive chain metadata. If a controller needs explicit access to data by key, GraphQLContext and `@ContextValue` are usually easier to understand.

With Spring MVC, context may rely on `ThreadLocal`. Because GraphQL Java can execute DataFetchers on a thread different from the original HTTP handling thread, propagating ThreadLocal requires a context propagation mechanism. Spring for GraphQL supports Micrometer Context Propagation via `ThreadLocalAccessor` implementations registered by the application.

Do not use ThreadLocal as the default request state store in a reactive pipeline. Threads can switch between processing steps, causing data not to propagate as expected.

## 13. Keeping request state safe under concurrent requests

A Spring application typically uses singleton controllers and services. Multiple GraphQL executions can run concurrently, so each request's state must stay within the proper scope.

Do not do the following:

~~~java
@Controller
public class UnsafeOrderController {

    private String currentTenantId;

    @QueryMapping
    public List<Order> orders(
            @ContextValue("tenantId") String tenantId) {

        this.currentTenantId = tenantId;
        return orderService.findByTenant(this.currentTenantId);
    }
}
~~~

Two requests from two tenants can overwrite each other's `currentTenantId`. As a result, a query could use the wrong tenant.

Pass values via method parameters or the execution context:

~~~java
@Controller
public class OrderController {

    @QueryMapping
    public List<Order> orders(
            @ContextValue("tenantId") String tenantId) {

        return orderService.findByTenant(tenantId);
    }
}
~~~

Some rules:

- Do not store a request's user, tenant, or correlation ID in a mutable singleton field.
- Do not use a static mutable Map to hold request metadata.
- Do not share DataLoaders or request-scoped caches across executions.
- Prefer populating context before the GraphQL engine runs.
- Put immutable objects or objects with a well-defined lifecycle into the context.
- Do not store large payloads or large entity graphs unnecessarily.
- Use local context when data only serves a single branch.
- Use DataLoader for per-request caching and batch loading instead of building your own shared cache.

GraphQL Java describes GraphQLContext as thread-safe, but that does not automatically make every object placed inside the context thread-safe. Prefer immutable data and avoid mutating the context from multiple uncoordinated resolvers.

GraphQL Java requires both keys and values stored in `GraphQLContext` to be non-null. If a value does not exist, omit the key or use a non-null wrapper type and handle the absent state explicitly; do not call `put(key, null)`.

## 14. Testing GraphQLContext

You should test both the interceptor step that populates metadata into the context and that the resolver reads the right value.

Example SDL:

~~~graphql
type Query {
  requestId: String!
}
~~~

Controller:

~~~java
@Controller
public class RequestIdController {

    @QueryMapping
    public String requestId(
            @ContextValue("correlationId") String correlationId) {
        return correlationId;
    }
}
~~~

With `WebGraphQlTester`, you can send headers to test the interceptor:

The example assumes the tester is created from a `WebGraphQlHandler` that has registered the interceptor from earlier. When testing over a real HTTP endpoint or test client, you can use `HttpGraphQlTester` with `WebTestClient` and configure the same header.

~~~java
class RequestContextTests {

    @Autowired
    WebGraphQlTester webGraphQlTester;

    @Test
    void shouldExposeCorrelationIdToController() {
        WebGraphQlTester testerWithHeader = webGraphQlTester.mutate()
                .header("X-Correlation-Id", "test-correlation-01")
                .build();

        testerWithHeader.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("test-correlation-01");
    }
}
~~~

Scenarios to test:

1. A header with a value is transferred into GraphQLContext.
2. When the header has no value, the interceptor generates a correlation ID.
3. The resolver correctly reads the context via `@ContextValue`.
4. The resolver receives the full GraphQLContext when multiple keys are needed.
5. Local context only appears in the branch passed down by the parent field.
6. The batch loader receives the right tenant or metadata from GraphQLContext.
7. Two concurrent requests do not mix up each other's context.
8. Principal reflects the identity from Spring Security.
9. The client cannot alter the authenticated tenant or user via a GraphQL argument.
10. Reactor Context is propagated through the reactive chain when running on WebFlux.

Integration tests through the transport layer are useful to verify headers/interceptors. Isolated resolver tests can verify logic that uses context, but they do not replace testing the path from transport to GraphQL execution.

## 15. Common errors

| Symptom | Possible cause | How to fix |
|---|---|---|
| `@ContextValue` cannot find key | Interceptor has not added the key or wrong key name | Check the key and interceptor ordering |
| Context is null in resolver | Value was not added to ExecutionInput | Check `configureExecutionInput` |
| Request uses the wrong tenant | Storing tenant in a mutable singleton field | Pass tenant via GraphQLContext or method argument |
| Local context missing in child field | Parent resolver did not return `DataFetcherResult` with local context | Check the local context propagation path |
| DataLoader does not receive tenant | Batch loader does not read GraphQLContext | Use `BatchLoaderEnvironment.getContext()` |
| Reactor Context missing in service | Code runs outside reactive chain or context was not propagated | Check WebFlux chain and `contextWrite` |
| ThreadLocal loses data | GraphQL DataFetcher runs on a different thread | Register `ThreadLocalAccessor` or use explicit context |
| Client accesses another tenant's data | Trusting client-supplied headers/arguments | Authenticate and check permissions on the server |
| WebSocket uses stale credentials | Token expiration or permission revocation not handled | Check authentication across connection lifecycle and per operation |

## 16. Design principles for context and request state

When implementing GraphQLContext:

- Use context for metadata spanning a single GraphQL execution.
- Populate context from an interceptor or execution setup before resolvers run.
- Use `@ContextValue` when only a single key is needed.
- Accept `GraphQLContext` when multiple keys or context operations are needed.
- Use local context for data belonging only to a single query branch.
- Use `BatchLoaderEnvironment` to access context inside a batch loader.
- Use Principal or Spring Security for authenticated identity.
- Use Reactor Context for metadata that needs to follow a reactive chain.
- Use Micrometer Context Propagation if ThreadLocal must be propagated across threads in Spring MVC.
- Do not store request state in singletons or static mutable state.
- Prefer immutable, compact data with a clear lifecycle.
- Test request isolation, access permissions, and context propagation.

## Conclusion

`GraphQLContext` is the shared metadata area within a single GraphQL execution. Spring for GraphQL lets you populate the context via `WebGraphQlInterceptor`, then access it from controllers using `@ContextValue`, a `GraphQLContext` parameter, or from `DataFetchingEnvironment`.

Local context serves a single branch of the query tree; Reactor Context serves the reactive pipeline; Spring Security provides identity and authentication state. Distinguishing these scopes properly helps pass request state safely, prevents data leaks between concurrent requests, and keeps the schema focused on the business contract.

## References

- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Annotated Controllers, Context and Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — GraphQLContext API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphQLContext.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
