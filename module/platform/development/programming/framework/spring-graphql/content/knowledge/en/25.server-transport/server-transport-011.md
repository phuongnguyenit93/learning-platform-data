# `WebGraphQlHandler` in Spring for GraphQL

`WebGraphQlHandler` is the central component for handling a GraphQL request at the web layer of Spring for GraphQL. It connects the `WebGraphQlInterceptor` chain to `ExecutionGraphQlService`, then returns a `WebGraphQlResponse`. Both the HTTP handler and WebSocket handler share this component to execute GraphQL, keeping request-processing logic independent of transport-specific details.

In a typical Spring Boot application, the GraphQL starter auto-configures the necessary components. When you need to understand the processing flow, integrate interceptors, or manually assemble endpoints in a non-Boot application, it is important to understand the roles of `WebGraphQlHandler`, its builder, transport handlers, and the execution service.

## 1. What problem does `WebGraphQlHandler` solve?

GraphQL can be sent over multiple transports, such as HTTP and WebSocket. Each transport receives requests and sends responses differently, yet most GraphQL processing remains the same:

- Read the GraphQL document, operation name, and variables.
- Populate request metadata into `ExecutionInput` or `GraphQLContext`.
- Run shared interceptors.
- Invoke the GraphQL execution service.
- Observe or transform results before returning the response.

`WebGraphQlHandler` consolidates this shared processing behind a single contract. Transport handlers are responsible for translating HTTP or WebSocket requests and responses; `WebGraphQlHandler` orchestrates the interceptor chain and GraphQL execution.

## 2. Position in the server transport architecture

The main components can be visualized as follows:

```text
                  HTTP request
                       |
                       v
                GraphQlHttpHandler
                       |
                       v
                WebGraphQlHandler <----- GraphQlWebSocketHandler
                       |                         ^
                       v                         |
             WebGraphQlInterceptor chain --------+
                       |
                       v
              ExecutionGraphQlService
                       |
                       v
                  GraphQL Java
                       |
                       v
              WebGraphQlResponse
                       |
                       v
           HTTP response / WebSocket message
```

`WebGraphQlHandler` does not open network ports or create HTTP routes by itself. It is the shared processing layer invoked by transport adapters.

| Component | Responsibility |
|---|---|
| `GraphQlSource` | Provides the schema and GraphQL Java configuration such as runtime wiring, scalars, and instrumentation. |
| `ExecutionGraphQlService` | Executes GraphQL requests independently of HTTP or WebSocket. |
| `WebGraphQlInterceptor` | Intercepts web-layer requests and responses before and after execution. |
| `WebGraphQlHandler` | Connects the interceptor chain to `ExecutionGraphQlService`. |
| `GraphQlHttpHandler` | Converts HTTP requests into GraphQL web requests, calls the handler, and writes HTTP responses. |
| `GraphQlWebSocketHandler` | Manages GraphQL operations over WebSocket and passes each request to the handler. |

## 3. Request processing flow

Over HTTP, the flow typically proceeds in this order:

1. Client sends an HTTP request to the GraphQL endpoint.
2. `GraphQlHttpHandler` reads method, headers, media type, and body; then creates a `WebGraphQlRequest`.
3. `WebGraphQlHandler` invokes `WebGraphQlInterceptor` instances in configured order.
4. Interceptors can inspect the request, populate `ExecutionInput` or `GraphQLContext`, and call `chain.next(request)`.
5. The final interceptor forwards the request to `ExecutionGraphQlService`.
6. `ExecutionGraphQlService` calls GraphQL Java to parse, validate, and execute the operation.
7. The result is wrapped into a `WebGraphQlResponse` and flows back through the interceptor chain.
8. `GraphQlHttpHandler` converts the result into an HTTP response.

With WebSocket, the transport handler maintains the connection and manages the protocol. Each GraphQL operation on the connection still passes through `WebGraphQlHandler` and the interceptor chain. Callbacks related to connection lifecycle or cancellation are added by `WebSocketGraphQlInterceptor`.

## 4. API and building a handler with Builder

`WebGraphQlHandler` belongs to package:

```java
import org.springframework.graphql.server.WebGraphQlHandler;
```

Core API:

```java
public interface WebGraphQlHandler {

    static WebGraphQlHandler.Builder builder(
            ExecutionGraphQlService graphQlService);

    Mono<WebGraphQlResponse> handleRequest(WebGraphQlRequest request);
}
```

`builder(...)` accepts `ExecutionGraphQlService`, the component responsible for executing requests. The builder allows adding interceptors and building the handler:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(correlationIdInterceptor)
    .interceptor(timeoutInterceptor)
    .build();
```

Multiple interceptors can also be passed at once:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptors(List.of(
        correlationIdInterceptor,
        tenantContextInterceptor,
        timeoutInterceptor
    ))
    .build();
```

Both approaches are equivalent in purpose. `interceptor(...)` is convenient when adding components one by one; `interceptors(...)` fits when a list is already assembled.

`handleRequest(WebGraphQlRequest)` executes the request and returns `Mono<WebGraphQlResponse>`. This is an asynchronous API; do not call `block()` inside an interceptor or transport adapter to wait for results.

## 5. How the handler collaborates with `ExecutionGraphQlService`

`WebGraphQlHandler` does not parse schemas or configure resolvers itself. It delegates execution to `ExecutionGraphQlService`.

General configuration flow:

```text
schema SDL + runtime wiring
            |
            v
       GraphQlSource
            |
            v
  ExecutionGraphQlService
            |
            v
    WebGraphQlHandler
            |
            v
  HTTP / WebSocket transport
```

`GraphQlSource` is where schemas, scalars, type resolvers, and data fetchers are configured. `ExecutionGraphQlService` uses the GraphQL source to execute requests. Because the execution service is transport-agnostic, it can also be tested directly without creating HTTP or WebSocket requests.

In Spring Boot, the required GraphQL beans are usually auto-configured from schemas and annotated controllers. When configuring manually, you can create `DefaultExecutionGraphQlService` from `GraphQlSource` and pass that service to `WebGraphQlHandler.builder(...)`.

## 6. Adding interceptors to the handler chain

Interceptors are individual components; the handler is where they are combined. An interceptor can read HTTP headers, add metadata to `GraphQLContext`, and continue the request:

```java
@Component
class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put("tenantId", tenantId)
            ).build()
        );

        return chain.next(request);
    }
}
```

A resolver can receive the context value:

```java
@QueryMapping
List<Project> projects(@ContextValue("tenantId") String tenantId) {
    return projectService.findForTenant(tenantId);
}
```

`chain.next(request)` passes the request to the next interceptor or execution service. If an interceptor does not call `chain.next`, the request will not reach GraphQL execution unless the interceptor explicitly produces an alternative response.

Do not trust a client-supplied `X-Tenant-Id` directly when the tenant must be derived from an authenticated identity. The example above illustrates metadata propagation; in real applications, verify permissions and tenant provenance at the security/service layer.

## 7. Handling responses in the interceptor chain

Interceptors can also perform work after GraphQL execution completes. Example adding a correlation ID to an HTTP response header:

```java
@Component
class CorrelationResponseInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");

        return chain.next(request).doOnNext(response -> {
            if (correlationId != null) {
                response.getResponseHeaders()
                    .set("X-Correlation-Id", correlationId);
            }
        });
    }
}
```

`WebGraphQlResponse` holds the GraphQL result along with web-transport metadata, including response headers and the ability to transform the response via `transform(...)`.

For WebSocket, the HTTP handshake already completed before GraphQL operations are sent. Headers added to an operation's response cannot become new HTTP response headers for individual WebSocket messages. If metadata must be sent over the WebSocket protocol, use a protocol-appropriate mechanism or the GraphQL payload.

## 8. Inspecting request validation errors

An important capability of the handler chain is that interceptors can also observe errors occurring before data fetchers run, such as parse or validation errors. `DataFetcherExceptionResolver` only handles exceptions thrown during data fetching; it is not the place to handle all request errors.

Example interceptor logging invalid responses:

```java
@Component
class RequestValidationLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(RequestValidationLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            if (!response.isValid()) {
                log.debug("GraphQL request {} returned {} errors",
                    request.getId(), response.getErrors().size());
            }
        });
    }
}
```

If you need to transform the error list, use `response.transform(builder -> builder.errors(errors).build())`. Preserve necessary `message`, `locations`, `path`, and `extensions`; never strip errors just to make a response look successful.

## 9. Configuring `WebGraphQlHandler` in Spring Boot

With `spring-boot-starter-graphql`, Spring Boot auto-configures the schema, execution service, web handler, and transport endpoints based on the starters present. Applications typically do not need to call `WebGraphQlHandler.builder(...)` manually.

To add an interceptor, simply declare a bean:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlWebConfiguration {

    @Bean
    WebGraphQlInterceptor correlationIdInterceptor() {
        return new CorrelationIdInterceptor();
    }
}
```

Boot detects `WebGraphQlInterceptor` beans and registers them in the web transport chain. Use `@Order` or implement `Ordered` when multiple interceptors depend on execution order.

Common transport configuration points:

| Configuration | Purpose |
|---|---|
| GraphQL HTTP path | HTTP endpoint path; typically `/graphql` by default. |
| `spring.graphql.websocket.path` | Enables and specifies the GraphQL WebSocket endpoint path. |
| HTTP methods | Controls accepted HTTP methods. |
| CORS | Allows browsers from matching origins to access the endpoint. |

The HTTP endpoint is configured by Boot by default. The GraphQL WebSocket endpoint is typically disabled by default; you need the appropriate WebSocket dependency for Spring MVC or use WebFlux, and set `spring.graphql.websocket.path`. The HTTP path property name can vary across Spring Boot lines; check the reference documentation for your exact project version.

## 10. Assembling the handler manually in non-Boot applications

If an application does not use Spring Boot auto-configuration, create the GraphQL and transport components manually. Once you have `ExecutionGraphQlService`, build the handler:

```java
WebGraphQlHandler webGraphQlHandler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptors(List.of(
        correlationIdInterceptor,
        timeoutInterceptor
    ))
    .build();
```

With a Spring MVC functional endpoint, `GraphQlHttpHandler` is the HTTP adapter using `WebGraphQlHandler`:

```java
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.webmvc.GraphQlHttpHandler;
import org.springframework.graphql.server.webmvc.GraphQlRequestPredicates;
import org.springframework.web.servlet.function.RequestPredicate;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Bean
RouterFunction<ServerResponse> graphQlRouterFunction(
        WebGraphQlHandler webGraphQlHandler) {

    GraphQlHttpHandler httpHandler = new GraphQlHttpHandler(webGraphQlHandler);
    RequestPredicate predicate = GraphQlRequestPredicates.graphQlHttp("/graphql");

    return RouterFunctions.route()
        .route(predicate, httpHandler::handleRequest)
        .build();
}
```

With Spring WebFlux, use the corresponding adapters in package `org.springframework.graphql.server.webflux`. Do not mix MVC handlers with WebFlux router functions.

This is an example of assembling an HTTP endpoint. If WebSocket is needed, also configure the appropriate WebSocket handler and mapping for MVC or WebFlux. Spring Boot normally simplifies these steps.

## 11. `WebSocketGraphQlInterceptor` in the handler chain

`WebSocketGraphQlInterceptor` extends `WebGraphQlInterceptor` with callbacks for the WebSocket connection lifecycle and client subscription cancellation. It still participates in processing each GraphQL request on the connection.

A handler chain can contain multiple `WebGraphQlInterceptor` instances, but at most one interceptor of type `WebSocketGraphQlInterceptor`. The handler exposes `getWebSocketInterceptor()` so the WebSocket transport can retrieve that specialized interceptor.

Example use cases for a WebSocket interceptor:

- Processing data from the `connection_init` message.
- Authenticating and establishing context for the connection.
- Observing when a connection starts or terminates.
- Detecting client cancellation to release subscription resources.

For HTTP-only applications, there is no need to implement `WebSocketGraphQlInterceptor`. For authentication over WebSocket, you can use Spring for GraphQL's built-in interceptor instead of implementing protocol handling yourself if appropriate.

## 12. Context propagation and `ContextSnapshotFactory`

In reactive applications, a request may switch across multiple threads. Data in Reactor Context does not automatically synchronize with `ThreadLocal` values used by other libraries. `WebGraphQlHandler.Builder` supports configuring `ContextSnapshotFactory` to propagate `ThreadLocal` and Reactor contexts between the transport layer and the GraphQL execution layer.

Example builder with a context snapshot factory:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .contextSnapshotFactory(contextSnapshotFactory)
    .interceptor(correlationIdInterceptor)
    .build();
```

The `contextSnapshotFactory(...)` API was added in Spring for GraphQL 1.3.0. Configure it only when the application genuinely needs context propagation between Reactor and `ThreadLocal`; do not use it in place of `GraphQLContext` to pass business data between data fetchers.

`GraphQLContext` is suited for passing per-GraphQL-execution data, such as authenticated tenant, correlation ID, or locale. Context snapshots primarily support integration with context propagation mechanisms in other layers.

## 13. Timeouts and cancellation

Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to bound request processing time over web transports:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
```

In Spring Boot, declaring the bean is enough for the interceptor to be added to the web chain. If a timeout occurs, the interceptor sends a cancellation signal up the chain; reactive data fetchers can receive cancellation and stop in-flight work if upstream supports it.

Timeouts should be chosen per operation type. A cached read query may use a short timeout; operations querying large datasets may require separate bounds. Long-lived subscriptions should not be given the same short timeout as normal queries if their purpose is to keep a stream open.

## 14. Testing the handler with `WebGraphQlTester`

`WebGraphQlTester` tests requests server-side while still passing through the `WebGraphQlInterceptor` chain. This is a useful way to verify that interceptors read headers, populate context, and handle responses properly.

Create a tester from the handler:

```java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
    .headers(headers -> headers.set("X-Tenant-Id", "tenant-42"))
    .build();
```

Suppose a resolver reads the tenant from `GraphQLContext`:

```java
@QueryMapping
String currentTenant(@ContextValue("tenantId") String tenantId) {
    return tenantId;
}
```

Test:

```java
tester.document("""
        query {
            currentTenant
        }
        """)
    .execute()
    .path("currentTenant")
    .entity(String.class)
    .isEqualTo("tenant-42");
```

This test exercises both the handler and the interceptor chain. It does not open a real HTTP socket; if you need to test HTTP serialization, status codes, CORS, or network behavior, use `HttpGraphQlTester` with `WebTestClient`. If you need to test the WebSocket protocol, use `WebSocketGraphQlTester`.

Scenarios to test:

- Interceptor is called before execution and populates `GraphQLContext` properly.
- Missing or malformed headers are handled per policy.
- Response headers are added properly over HTTP transport.
- Validation errors are observed properly.
- Exceptions from data fetchers are still handled by exception resolvers.
- Interceptor chain executes in the configured order.
- Timeout triggers cancellation without leaving unintended reactive work running.
- WebSocket-specific interceptor receives lifecycle and cancellation callbacks properly.

## 15. Distinguishing `WebGraphQlHandler` from other handlers/interceptors

| Component | Scope | Role |
|---|---|---|
| `WebGraphQlHandler` | HTTP and WebSocket | Coordinates the interceptor chain and execution service. |
| `GraphQlHttpHandler` | HTTP | Translates HTTP requests/responses and invokes the web handler. |
| `GraphQlWebSocketHandler` | WebSocket | Manages the GraphQL WebSocket protocol and invokes the web handler for operations. |
| `WebGraphQlInterceptor` | Web request/response | Intercepts requests/responses in the chain. |
| `WebSocketGraphQlInterceptor` | WebSocket connection and requests | Extends the interceptor with connection lifecycle and cancellation callbacks. |
| `ExecutionGraphQlService` | Transport-agnostic | Executes GraphQL operations using GraphQL Java. |
| `RSocketQlInterceptor` | RSocket | Intercepts GraphQL requests over RSocket; not part of `WebGraphQlHandler`. |

Choose components according to the boundary you need to handle. Do not use `WebGraphQlHandler` to replace `GraphQlSource`, nor use `GraphQlHttpHandler` to hold per-field business logic.

## 16. Common errors

**Confusing the handler with an HTTP endpoint.** `WebGraphQlHandler` does not open ports or create routes by itself. You need a transport adapter such as `GraphQlHttpHandler` and route configuration, or let Spring Boot auto-configure them.

**Passing `GraphQlSource` instead into the builder.** `WebGraphQlHandler.builder(...)` takes `ExecutionGraphQlService`. Create or inject the proper GraphQL execution service.

**Manually creating a handler in Spring Boot unnecessarily.** Boot already auto-configures the handler and transport. If you only need logging, context, or timeouts, declaring a `WebGraphQlInterceptor` bean is usually sufficient.

**Forgetting to call `chain.next(request)`.** The request will not reach the execution service if the interceptor fails to continue the chain and does not produce an alternative response.

**Calling `chain.next` multiple times.** A single request may be executed multiple times, causing duplicate side effects. Normally call `chain.next(request)` exactly once.

**Calling `block()` or `subscribe()` inside an interceptor.** This breaks the reactive flow, can block threads, and prevents cancellation from propagating properly. Compose on the `Mono` returned by the chain instead.

**Putting business logic in an interceptor.** Interceptors fit cross-cutting request concerns such as correlation IDs, metadata, timeouts, or response headers. Domain rules belong in services/resolvers.

**Confusing HTTP response headers with GraphQL response data.** `getResponseHeaders()` modifies transport headers; it does not add fields to the GraphQL `data` section.

**Configuring multiple `WebSocketGraphQlInterceptor` instances.** A single handler chain supports at most one interceptor of this type. Combine the necessary WebSocket callbacks into one interceptor.

**Testing the handler and assuming the real transport was tested.** `WebGraphQlTester` tests the handler and interceptor chain; use HTTP/WebSocket testers when you need to verify serialization and protocol behavior.

## Conclusion

`WebGraphQlHandler` is the shared orchestration layer for GraphQL over HTTP and WebSocket. It accepts an `ExecutionGraphQlService`, builds an interceptor chain via its builder, and processes each `WebGraphQlRequest` to return `Mono<WebGraphQlResponse>`. Transport adapters such as `GraphQlHttpHandler` or `GraphQlWebSocketHandler` handle client communication. In Spring Boot, declaring interceptor beans is usually all that is needed; in standalone setups, construct the handler yourself and attach it to the transport. Understanding the boundaries between the handler, execution service, transport adapters, and interceptors keeps server configuration consistent, testable, and cleanly separated from business logic.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL API — `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
- [Spring for GraphQL — Testing `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
