# Context is not for shared mutable state

A GraphQL operation can invoke multiple resolvers, access multiple services, and flow through multiple processing layers. Those components sometimes need to share information such as correlation ID, locale, verified tenant, or current principal. Spring for GraphQL provides `GraphQLContext` and context propagation mechanisms to deliver this information to data fetchers.

However, **a request's context is not a place to store mutable state shared across the entire application**. A `GraphQLContext` belongs to a single GraphQL execution and may be read concurrently by multiple resolvers in the same operation. Query fields can execute asynchronously or in parallel. If multiple resolvers mutate a shared mutable object inside context, results can depend on execution order and cause data race bugs.

This lesson focuses on the boundary between request state, `GraphQLContext`, and local context; how to populate metadata into context via `WebGraphQlInterceptor`; how to read context in controllers, DataLoaders, and batch mappings; and common bugs caused by storing request data in singleton beans, static fields, or `ThreadLocal`.

## What is request state?

Request state is information that is only meaningful within the scope of a single request or GraphQL execution. Examples:

- Correlation ID to link logs across resolvers in the same operation.
- Locale determined from the request to select language or formatting.
- Verified tenant to restrict which data the user is permitted to access.
- Principal or authentication details established by Spring Security.
- Metadata for tracing, auditing, or feature evaluation within a single operation.

These values differ from long-lived business data persisted in a database and differ from caches shared across multiple requests. Request state should be created or determined at the request entry boundary, propagated where needed, and end alongside the operation's lifecycle.

A Spring application typically has many singleton beans such as controllers, services, interceptors, and repositories. Singleton beans are invoked concurrently by many requests. Therefore, never store `currentUser`, `tenantId`, `correlationId`, or request data in mutable fields of those beans:

~~~java
@Component
public class RequestStateHolder {

    private String currentTenantId;

    public void setCurrentTenantId(String tenantId) {
        this.currentTenantId = tenantId;
    }

    public String getCurrentTenantId() {
        return currentTenantId;
    }
}
~~~

The code above is unsafe if the bean is a singleton. Request A could write tenant A, and then Request B writes tenant B before A's resolver reads the value. A's resolver could accidentally use tenant B and access the wrong data scope.

Pass request state via parameters or request-scoped context rather than holding it in bean fields.

## What is GraphQLContext?

GraphQL Java provides `GraphQLContext` as a key/value container bound to a GraphQL execution. Spring for GraphQL delivers this context to data fetchers and annotated controllers.

The main `GraphQLContext` is scoped to an entire GraphQL operation. Multiple resolvers in the operation can read the same context. For example, a Query field and child fields can all read the correlation ID or verified tenant.

In an annotated controller, you can accept the full `GraphQLContext`:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public String correlationId(GraphQLContext context) {
        return context.get("correlationId");
    }
}
~~~

Or accept only a single value with `@ContextValue`:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public String correlationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

`@ContextValue` lets the resolver signature declare only the value the method needs. If a key is optional, you can set `required = false` or use `Optional` matching the data type.

`GraphQLContext` exposes APIs for both adding and reading values. However, being able to call `put` does not mean every resolver should mutate the context. Treat the main context as the place where execution metadata is published; populate needed values before GraphQL runs resolvers, and prefer reading only afterward.

## The boundary between GraphQLContext and shared mutable state

`GraphQLContext` is created per execution, so it is not automatically shared across independent HTTP requests. Even so, it can still be shared among multiple field resolvers within the same operation. Query resolvers may execute asynchronously, so two resolvers can read or write context almost simultaneously.

There are three scopes to distinguish:

| Scope | Examples | Should you store shared mutable state? |
| --- | --- | --- |
| Application-wide | Static fields, singleton services | Never store per-request state |
| Single GraphQL execution | Main `GraphQLContext` | Prefer immutable values, set before resolvers run |
| Single child data branch | Local context of a parent result | Only pass data needed by the child branch; avoid sharing unnecessary mutable objects |

Example of what not to do:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        GraphQLContext context) {

    context.put("currentBookId", id);
    return bookService.findById(id);
}
~~~

If an operation calls the `book` field multiple times with different IDs, the resolvers can overwrite each other's `currentBookId` key. Child fields or other resolvers cannot tell which call the current value belongs to. If you need to pass per-Book data down to child fields, use local context instead of overwriting a key in the main context.

An immutable value like a correlation ID can be set once in an interceptor and read by many resolvers. If a mutable structure in context is truly unavoidable, it must have explicit synchronization and ownership boundaries; in most cases, you can avoid it by using immutable records or producing separate results per field.

## Populating request metadata into GraphQLContext

An HTTP request may carry headers such as `X-Correlation-Id`. Spring for GraphQL provides `WebGraphQlInterceptor` to read transport details before GraphQL Java executes the operation and place required data into `ExecutionInput`.

For simple headers, you can use the built-in `HttpRequestHeaderInterceptor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration
public class GraphQlRequestContextConfiguration {

    @Bean
    HttpRequestHeaderInterceptor correlationIdInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Correlation-Id")
                .build();
    }
}
~~~

The controller reads the value placed into `GraphQLContext`:

~~~java
@Controller
public class DiagnosticController {

    @QueryMapping
    public String correlationId(
            @ContextValue("X-Correlation-Id") String correlationId) {
        return correlationId;
    }
}
~~~

The example above assumes the header is always present. If the header is optional, you can set `required = false` on `@ContextValue` or use `Optional<String>`, and generate a default correlation ID in one consistent layer.

If you need to validate, normalize, or combine multiple values before putting them into context, write a custom `WebGraphQlInterceptor`. The example below reads the correlation ID from the header, validates its format, and puts it into `GraphQLContext`:

~~~java
import java.util.Map;
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

        String suppliedId = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = isValid(suppliedId)
                ? suppliedId
                : UUID.randomUUID().toString();

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(Map.of(
                        "correlationId", correlationId))
                        .build());

        return chain.next(request);
    }

    private boolean isValid(String value) {
        return value != null && value.length() <= 100
                && value.matches("[A-Za-z0-9._-]+");
    }
}
~~~

This example only uses the header to produce a correlation ID for request observability. For tenant or access permissions, never trust an arbitrary header sent by the client. Derive the tenant from the authenticated principal or verified claims, and enforce authorization in the service or data access layer.

An interceptor is usually registered as a Spring bean and may be invoked for many concurrent requests. Therefore, interceptors should be stateless: use only local variables inside the `intercept` method and never store the correlation ID in a bean field.

## Reading context in resolvers and services

A resolver can receive a context value and pass it down to a service:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public List<Order> myOrders(
            @ContextValue("tenantId") String tenantId) {
        return orderService.findOrdersForTenant(tenantId);
    }
}
~~~

Here `tenantId` must be populated from a trusted source at the security layer or an authenticated interceptor. The service still needs to enforce permissions and data-scope checks; having `tenantId` in context does not by itself guarantee the user is authorized to access that tenant.

If the current principal is needed, Spring for GraphQL supports injecting `java.security.Principal` or `@AuthenticationPrincipal` in annotated controllers:

~~~java
import java.security.Principal;

@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findVisibleTo(principal.getName());
}
~~~

For authentication details, prefer Spring Security rather than storing access tokens or passwords in `GraphQLContext` yourself. Never put credentials into logs, GraphQL responses, or observability metadata.

## GraphQLContext and local context are different

The main `GraphQLContext` fits data shared across the entire execution, such as correlation ID, locale, or security metadata. Sometimes a parent resolver has already loaded data needed only by child fields within that branch. Putting that data into the main context exposes it to every resolver in the operation and parallel calls can overwrite one another.

**Local context** is designed to pass data down to a subtree of child data. Spring for GraphQL lets controllers return `DataFetcherResult<T>` with local context, which child fields then read via `@LocalContextValue`.

Example parent resolver loading Book and Author together:

~~~java
import graphql.GraphQLContext;
import graphql.execution.DataFetcherResult;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.LocalContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public DataFetcherResult<Book> bookById(@Argument String id) {
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

Local context travels with the parent result and applies only within the corresponding child data branch. If an operation queries multiple `Book`s, each parent result can carry its own local context, avoiding storing `prefetchedAuthor` under a shared key in the main `GraphQLContext`.

Use local context only when data truly belongs to a specific branch. If data is metadata shared across the entire operation, the main `GraphQLContext` fits better. If you simply need to query a relational field in batches, `DataLoader` or `@BatchMapping` is usually the right choice.

## Context in DataLoader and batch mapping

DataLoaders are created per GraphQL request through `DataLoaderRegistry` and `BatchLoaderRegistry`. A batch loader can read the execution's `GraphQLContext` to use metadata such as tenant or locale. In annotated controllers, batch mapping supports accepting `GraphQLContext` or `@ContextValue`.

Example:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.stereotype.Controller;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(
            List<Book> books,
            @ContextValue("tenantId") String tenantId) {
        return authorService.findAuthorsFor(books, tenantId);
    }
}
~~~

The batch loader uses the same main context of the GraphQL execution. Therefore, `tenantId` must be populated before resolvers or batch loaders run and must not be mutated while fields are executing.

When using `BatchLoaderWithContext` directly, `BatchLoaderEnvironment` provides the execution's shared `GraphQLContext` and `keyContexts` containing the local context attached to each `load` call. This lets the loader distinguish request-wide metadata from data specific to each source object. If a single batch spans multiple tenants or differing local contexts, the batch function must handle the right scope per key; never apply a single tenant to an entire batch when keys have different access permissions.

## Do not use ThreadLocal as a request state store

An older way of passing request information across layers is storing it in `ThreadLocal`. This breaks easily in GraphQL because resolvers can run asynchronously, switch threads, or run on another executor. In WebFlux, requests typically flow through a Reactor pipeline and are not pinned to a single thread.

Spring for GraphQL supports context propagation from the transport to GraphQL Java and data fetchers:

- With Spring MVC, `ThreadLocal` context can be propagated via Micrometer Context Propagation when an appropriate `ThreadLocalAccessor` is registered.
- With Spring WebFlux, Reactor Context is propagated along the reactive pipeline; interceptors can populate metadata into the operation's `GraphQLContext`.

That does not mean you should invent your own `ThreadLocal` to hold tenant or user. If you use a custom `ThreadLocal`, you must manage the accessor and reset lifecycle accurately; otherwise, values can leak to another task when threads are reused.

Prefer `GraphQLContext` for execution metadata, `@ContextValue` for values read in controllers, Reactor Context for reactive pipeline context, and Spring Security for principals. Only integrate `ThreadLocalAccessor` when a synchronous library genuinely requires `ThreadLocal` and a clear propagation design is in place.

## WebSocket connection state is not GraphQL operation state

Spring for GraphQL supports HTTP and WebSocket. A WebSocket connection can live for a long time and carry many different GraphQL operations or subscriptions. `WebGraphQlRequest` can expose request attributes or WebSocket session attributes, but connection-scoped attributes have a different lifecycle from a single operation's `GraphQLContext`.

Do not store mutable data for an operation inside WebSocket session attributes and treat it as per-operation state. Two operations on the same connection can coexist or execute at different times. If connection-level authentication info is needed, use the appropriate WebSocket authentication mechanism; each GraphQL execution still needs an explicit context, and never use a shared mutable map to pass state across operations.

Subscriptions also outlive ordinary queries. Avoid accumulating unbounded lists of events, user data, or mutable state in a subscription's context. When per-event state is needed, attach data to the corresponding publisher/event and manage cleanup when the subscription is cancelled or completes.

## Anti-patterns to avoid

| Anti-pattern | Why it is dangerous | Alternative |
| --- | --- | --- |
| Storing `currentUser` in a singleton controller field | Another request can overwrite the current user | Accept `Principal` or `@AuthenticationPrincipal` |
| Storing `tenantId` in a static field | Every request and tenant shares the same value | Derive verified tenant and pass via context |
| Multiple resolvers calling `put` on the same `GraphQLContext` key | Parallel resolvers can overwrite each other's data | Set before execution or use local context |
| Using `GraphQLContext` as a global cache | Wrong scope and lifecycle for the data | Use a dedicated cache with explicit TTL, keys, and invalidation |
| Holding mutable request objects in singleton services | Request data leaks between concurrent calls | Use local variables and method parameters |
| Relying on `ThreadLocal` in reactive resolvers | Threads can change between steps | Use `GraphQLContext` or Reactor Context |
| Putting tokens or passwords into context and logging everything | Can expose credentials | Pass minimal metadata only and filter logs |
| Using WebSocket session attributes for individual operations | State can be shared across multiple operations | Create a separate `GraphQLContext` per execution |

## Testing request isolation and context propagation

Testing context is not only about verifying a resolver can read a key. You must also verify that two requests' data do not mix when running concurrently.

Scenarios to include:

| Scenario | What to verify |
| --- | --- |
| Requests A and B have different correlation IDs | Each resolver receives only its corresponding request's ID |
| Two requests from different tenants run concurrently | No data from one tenant appears in the other tenant's response |
| Multiple Query fields read the same `GraphQLContext` | Metadata values remain stable and are not overwritten by resolvers |
| Two parent objects have different local contexts | Child fields receive the local context of their exact parent |
| Batch loader reads `@ContextValue` | Loader uses the context of the right execution |
| WebSocket carries multiple operations | Operation request state does not leak across operations |
| Subscription completes or is cancelled | Resources and state attached to the subscription are released |

You can use `HttpGraphQlTester` or `WebTestClient` to send two requests with different correlation ID headers and inspect the responses. For race conditions, run parallel requests repeatedly to increase the likelihood of catching shared-state bugs. For local context, integration tests should query multiple parents with different data and verify child fields receive their matching data.

Besides responses, inspect logs or mock services to confirm tenant, principal, and correlation ID are passed properly. Never write tokens or sensitive data into assertion logs.

## Design principles for context and request state

When building with Spring for GraphQL, follow these principles:

1. **Determine the right data scope.** Execution-wide data goes in `GraphQLContext`; branch-specific data goes in local context; durable business data lives in services or databases.
2. **Set context at the request boundary.** Use `WebGraphQlInterceptor` or built-in interceptors before GraphQL runs resolvers.
3. **Prefer read-only access after setup.** Put immutable metadata into context and let resolvers read it, avoiding overwrites on shared keys.
4. **Never store request state in singletons.** Controllers, services, and interceptors must be stateless or hold only immutable dependencies.
5. **Use Spring Security for identity and permissions.** Never treat client-sent headers or arguments as proof of authentication.
6. **Use local context for per-parent data.** Never put per-object data into a shared key in the main `GraphQLContext`.
7. **Understand context propagation.** Never assume resolvers run on the same thread; use `GraphQLContext` and Reactor Context appropriately.
8. **Keep DataLoaders per request.** Never build mutable loaders or caches at application-wide scope.
9. **Test isolation.** Send concurrent requests and operations to verify no state leaks.

`GraphQLContext` is a place to pass metadata within the scope of a single GraphQL execution, not an application-wide shared mutable state store. Create context at the request boundary, prefer immutable values, and treat it as read-only in resolvers. When data belongs only to a parent-child branch, use local context; when data pertains to identity and access permissions, use Spring Security; when related data needs to be loaded in batches, use DataLoader. Respecting the scope and lifecycle of each kind of state helps prevent race conditions, cross-request data leaks, and hard-to-reproduce bugs in Spring for GraphQL applications.

## References

- [Spring for GraphQL - Annotated Controllers: Context and Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
