# WebGraphQlHandler in Spring for GraphQL

`WebGraphQlHandler` is the common orchestration point for a GraphQL request entering from the web layer of Spring for GraphQL. It receives a `WebGraphQlRequest`, runs the `WebGraphQlInterceptor` chain, forwards the request to `ExecutionGraphQlService` for GraphQL execution, and returns `Mono<WebGraphQlResponse>`.

Understanding `WebGraphQlHandler` helps you know where to place request inspection logic, propagation of information from HTTP into the GraphQL context, response header additions, error normalization, and testing. It is part of the server-side architecture of Spring for GraphQL alongside SDL schemas, resolvers, DataLoaders, and HTTP or WebSocket transports.

## 1. Position of WebGraphQlHandler in the architecture

A Spring for GraphQL application can receive GraphQL requests over multiple transports. The transport layer converts protocol payloads into Spring request objects; `WebGraphQlHandler` handles the shared processing before calling the GraphQL engine.

~~~mermaid
flowchart TD
    A[GraphQL client] --> B{Transport}
    B --> C[HTTP handler]
    B --> D[WebSocket handler]
    C --> E[WebGraphQlHandler]
    D --> E
    E --> F[WebGraphQlInterceptor chain]
    F --> G[ExecutionGraphQlService]
    G --> H[GraphQL Java engine]
    H --> I[Resolver / DataFetcher]
    I --> J[Service / Repository / DataLoader]
    J --> H
    H --> G
    G --> F
    F --> E
    E --> B
    B --> A
~~~

Each component has a distinct responsibility:

| Component | Responsibility |
| --- | --- |
| `GraphQlHttpHandler` | Receives GraphQL requests over HTTP, translating payloads and responses between HTTP and Spring's GraphQL model |
| `GraphQlWebSocketHandler` | Manages GraphQL requests over WebSocket, including connection lifecycle and subscription streams |
| `WebGraphQlHandler` | Runs the shared interceptor chain and delegates the request to the GraphQL execution service |
| `WebGraphQlInterceptor` | Intercepts requests before execution and responses after execution |
| `ExecutionGraphQlService` | Executes requests in a transport-independent way using GraphQL Java |
| `GraphQlSource` | Provides the configuration and GraphQL schema/runtime used for execution |

`WebGraphQlHandler` does not open HTTP ports itself, does not create the `/graphql` URL by itself, and does not replace the GraphQL engine. It is the bridge between the web transport and `ExecutionGraphQlService`. In a Spring Boot application, the starter typically configures the transport components and handler automatically. When integrating standalone or building a custom pipeline, you can construct the handler using its builder.

## 2. Core API of WebGraphQlHandler

`WebGraphQlHandler` lives in the `org.springframework.graphql.server` package and is an interface. Its most important API members include:

- `builder(ExecutionGraphQlService)`: creates a builder bound to a GraphQL execution service.
- `handleRequest(WebGraphQlRequest)`: processes a request and returns `Mono<WebGraphQlResponse>`.
- `getWebSocketInterceptor()`: retrieves the single `WebSocketGraphQlInterceptor` in the chain if present.

The builder provides two ways to register interceptors:

- `interceptor(WebGraphQlInterceptor...)`: adds one or more interceptors.
- `interceptors(List<WebGraphQlInterceptor>)`: registers a list of interceptors.
- `build()`: creates the `WebGraphQlHandler` instance.

Example of creating a handler:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.WebGraphQlInterceptor;

import java.util.List;

public class GraphQlHandlerConfiguration {

    public WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            WebGraphQlInterceptor tenantInterceptor,
            WebGraphQlInterceptor responseHeaderInterceptor
    ) {
        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptors(List.of(
                        tenantInterceptor,
                        responseHeaderInterceptor
                ))
                .build();
    }
}
~~~

The snippet above demonstrates manual handler creation. In a real application, the configuration method is usually declared with `@Bean` inside a `@Configuration` class. If you are using the Spring Boot starter, prefer auto-configuration and declare `WebGraphQlInterceptor` instances as Spring beans; the starter can discover them and place them into the pipeline according to configured bean order.

## 3. WebGraphQlRequest and WebGraphQlResponse

### 3.1. Reading request information

`WebGraphQlRequest` is the server-side request object for GraphQL over HTTP or WebSocket. In addition to document, operation name, variables, and extensions inherited from `GraphQlRequest`, it provides web request details:

| API | Meaning |
| --- | --- |
| `getHeaders()` | HTTP headers of the request or of the WebSocket handshake |
| `getCookies()` | Cookies of the HTTP request or WebSocket handshake |
| `getUri()` | URL of the HTTP request or WebSocket handshake |
| `getRemoteAddress()` | Client address if provided by the transport |
| `getAttributes()` | Request attributes or WebSocket session attributes |
| `getDocument()` | Contents of the GraphQL document |
| `getOperationName()` | Operation name selected by the client, if any |
| `getVariables()` | Input variables for the operation |
| `getExtensions()` | Extensions of the GraphQL request |

For WebSocket, the headers and URI here come from the HTTP handshake that opened the connection. Subsequent GraphQL messages are transmitted over the WebSocket connection, not as separate HTTP requests.

`WebGraphQlRequest` also lets you customize `ExecutionInput` via `configureExecutionInput(...)`. This is the key point for passing web-layer metadata into `GraphQLContext`, attaching an execution ID, or adjusting execution settings before GraphQL Java processes the request.

### 3.2. Reading and modifying the response

`WebGraphQlResponse` wraps the GraphQL execution result and exposes familiar fields such as data, errors, extensions, and execution input. Commonly used API methods:

- `getData()` and `getErrors()` to read returned data and errors.
- `isValid()` to check whether the response has a valid `data` section according to the GraphQL response model. A response can still contain an error on one field while other fields return data successfully.
- `getExecutionInput()` to access the `ExecutionInput` used during execution.
- `getResponseHeaders()` to add HTTP response headers.
- `transform(...)` to create a new response with a modified `ExecutionResult`.

`getResponseHeaders()` serves GraphQL over HTTP. With WebSocket, the HTTP handshake has already completed before GraphQL operations are sent, so response headers cannot be used to attach individual HTTP headers to each GraphQL message.

## 4. WebGraphQlInterceptor: extending the processing pipeline

`WebGraphQlInterceptor` is the primary extension mechanism orchestrated by `WebGraphQlHandler`. The interface defines the method:

~~~java
Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        WebGraphQlInterceptor.Chain chain
);
~~~

`Chain` represents the remainder of the pipeline, including subsequent interceptors and `ExecutionGraphQlService`. Call `chain.next(request)` to pass the request forward. An interceptor can perform work before that call, process the response once the publisher completes, or short-circuit early if the request is not allowed to proceed.

An interceptor can be used for tasks such as:

- Reading headers, cookies, URI, or attributes to extract request metadata.
- Adding information to `ExecutionInput` and `GraphQLContext`.
- Recording execution duration, correlation IDs, or observability metadata.
- Adding HTTP response headers or cookies.
- Inspecting and normalizing request-level errors in `ExecutionResult`.
- Enforcing timeouts or request-level processing limits.

### 4.1. Passing request metadata into GraphQLContext

Suppose every request includes an `X-Tenant-Id` header to identify the tenant. Resolvers need the tenant ID without directly reading the HTTP request object. An interceptor can place this value into `GraphQLContext`:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import reactor.core.publisher.Mono;

public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        if (tenantId != null && !tenantId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("tenantId", tenantId)
                    ).build()
            );
        }

        return chain.next(request);
    }
}
~~~

A resolver can read the value stored in context using `@ContextValue`:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@ContextValue("tenantId") String tenantId) {
        return bookService.findAllByTenant(tenantId);
    }
}
~~~

This example shows that the controller receives only the context it needs, without depending on Servlet or WebFlux APIs. In a multi-tenant system, the tenant ID must be verified against an authenticated identity or authorized scope. Never treat a header sent by the client as proof that the user is authorized to access that tenant. The interceptor only propagates data into the GraphQL context; it does not create a secure authorization boundary by itself.

### 4.2. Adding HTTP response headers

An interceptor can also inspect or modify the response after the GraphQL engine finishes. The following example adds `Cache-Control` to the HTTP response:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import reactor.core.publisher.Mono;

public class NoStoreResponseInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        return chain.next(request).doOnNext(response ->
                response.getResponseHeaders().add(
                        HttpHeaders.CACHE_CONTROL,
                        "no-store"
                )
        );
    }
}
~~~

`chain.next(request)` returns a `Mono`, so you can use Reactor operators such as `map`, `flatMap`, or `doOnNext` to process the result without blocking the thread with `block()`. Choose headers according to the API's actual caching policy; personal data or authorization-dependent responses should generally not be publicly cached.

### 4.3. Normalizing request-level errors

GraphQL has multiple stages where errors can occur. Errors in a data fetcher occur after field execution begins and are typically handled by `DataFetcherExceptionResolver`. By contrast, syntax errors or validation errors in a GraphQL document occur before any data fetcher is called.

`DataFetcherExceptionResolver` cannot handle request-level errors that occur before the field execution phase. When you need to inspect or transform these errors, an interceptor can check `response.isValid()`, inspect `response.getErrors()`, and use `response.transform(...)` to build a new response. When normalizing, preserve useful location, path, and extension details; avoid stripping error causes or exposing internal stack traces.

Do not use an interceptor to turn every error into a fake success response. Error transformations must preserve GraphQL semantics so clients know whether the request itself was invalid or whether only one field in the response failed.

## 5. Configuring interceptors in Spring Boot and standalone setups

### 5.1. Using the Spring Boot starter

In a Spring Boot application already using the Spring for GraphQL starter, you can declare interceptors as beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlWebConfiguration {

    @Bean
    WebGraphQlInterceptor tenantContextInterceptor() {
        return new TenantContextInterceptor();
    }

    @Bean
    WebGraphQlInterceptor noStoreResponseInterceptor() {
        return new NoStoreResponseInterceptor();
    }
}
~~~

The starter discovers `WebGraphQlInterceptor` beans and adds them to the GraphQL web processing chain. You can use `@Order` or Spring's bean ordering mechanism to control order. If ordering affects authentication, logging, or response handling, declare it explicitly and test the behavior of the full chain.

### 5.2. Creating the handler manually without Spring Boot

In a standalone setup, the application must create `ExecutionGraphQlService`, `WebGraphQlHandler`, and the transport handler manually. The snippet below shows creating the handler; `executionGraphQlService` must be configured beforehand with `GraphQlSource` and the corresponding runtime wiring:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlServerConfiguration {

    @Bean
    WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            TenantContextInterceptor tenantInterceptor,
            NoStoreResponseInterceptor responseInterceptor
    ) {
        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptor(tenantInterceptor, responseInterceptor)
                .build();
    }
}
~~~

Next, create the appropriate transport adapter. With Spring MVC, the HTTP handler class resides in the `org.springframework.graphql.server.webmvc` package; with WebFlux, use the variant in the `org.springframework.graphql.server.webflux` package. The adapter receives HTTP requests, converts them into `WebGraphQlRequest`, invokes `WebGraphQlHandler`, and writes responses back to HTTP. If using WebSocket, configure `GraphQlWebSocketHandler` and the corresponding WebSocket endpoint.

Creating `WebGraphQlHandler` alone is not enough for clients to call the API. The application must also register the transport route or endpoint, configure the schema, and ensure the dependencies for the MVC/WebFlux stack in use are present.

## 6. WebSocketGraphQlInterceptor and connection handling

`WebSocketGraphQlInterceptor` extends `WebGraphQlInterceptor` to handle the WebSocket connection lifecycle. In addition to intercepting individual GraphQL requests over the connection, it provides callbacks related to connection start, connection termination, and client subscription cancellation.

Key points to remember:

- `WebGraphQlInterceptor` handles GraphQL requests over HTTP or WebSocket.
- `WebSocketGraphQlInterceptor` adds handling for events at the WebSocket connection level.
- An interceptor chain may contain at most one `WebSocketGraphQlInterceptor`.
- Spring for GraphQL provides `AuthenticationWebSocketInterceptor` implementations for WebMVC and WebFlux to extract authentication details from the `connection_init` message and propagate `SecurityContext` to subsequent requests on the connection.

WebSocket connections can be long-lived and carry multiple concurrent subscriptions. Therefore, you need to manage connection counts, subscription counts, message sizes, authentication, and access permissions throughout the connection lifecycle. Succeeding authentication at handshake time does not mean every subsequent operation is allowed to read all data.

## 7. Timeouts and request cancellation

A GraphQL request can take a long time due to complex queries, external service calls, or slow data fetchers. Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to enforce a time limit on requests over web transports.

Example creating an interceptor with a five-second timeout:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

When a timeout occurs, the interceptor emits a cancellation signal up the pipeline. Reactive tasks that support cancellation can stop ongoing work, helping avoid wasting resources on timed-out requests. However, cancelling a publisher does not automatically roll back side effects already written to a database or external system. Write operations still require transactions, idempotency, and dedicated business-layer timeout policies where needed.

Request-level timeouts must also be considered by operation type. A normal query can have a short timeout; a subscription is a long-lived stream and should not use an overall timeout designed for a single HTTP request. For WebSocket or SSE, configure timeouts and connection limits according to transport characteristics.

## 8. Testing WebGraphQlHandler and the interceptor chain

Spring for GraphQL provides `WebGraphQlTester` for server-side testing through `WebGraphQlHandler`. This is useful when verifying the interceptor chain and simulated HTTP details without starting a real HTTP server.

Example creating a tester from a handler:

~~~java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
        .headers(headers -> headers.set("X-Tenant-Id", "tenant-42"))
        .build();

tester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .execute()
    .path("books")
    .entityList(Book.class)
    .hasSize(2);
~~~

The test above can verify that the request header is placed into context by the interceptor and that the resolver returns data for the corresponding tenant. You need to prepare `ExecutionGraphQlService` and appropriate controller/service test fixtures before creating the handler.

Consider including the following test groups:

1. The handler invokes `ExecutionGraphQlService` and returns the expected response for a valid request.
2. The interceptor reads headers or attributes and passes the right values into `GraphQLContext`.
3. The interceptor handles the response properly, including HTTP response headers when the transport is HTTP.
4. Interceptors execute in the configured order; when an interceptor rejects a request, downstream pipeline stages are not invoked.
5. Syntax or validation errors are caught properly; field-level errors still preserve valid data for other fields.
6. Timeouts emit cancellation signals and prevent reactive tasks from continuing needlessly.
7. For WebSocket, separately test `connection_init` authentication, connection termination, subscription cancellation, and subscription count limits.

`WebGraphQlTester` does not replace real transport testing. When you need to verify routing, HTTP status codes, codecs, WebSocket protocol handling, or security filter chain configuration, supplement with `HttpGraphQlTester`, `WebSocketGraphQlTester`, or integration tests suited to your running stack.

## 9. Guidelines when designing interceptors

**Keep interceptors short and focused.** Interceptors fit cross-cutting request logic such as context propagation, correlation IDs, headers, and timeouts. Field-specific business rules belong in resolvers or services.

**Do not block the reactive chain.** `intercept` returns `Mono<WebGraphQlResponse>`. Avoid calling `block()`, waiting synchronously, or performing blocking I/O on WebFlux event loops. If you must call external APIs, use a reactive client or offload blocking work to an appropriate scheduler.

**Do not trust unverified metadata.** Headers, cookies, and request attributes are user inputs. Only place identity or tenant into context after authentication and authorization checks. Resolvers and services must still enforce resource- and field-level authorization.

**Do not overuse response transformation.** Modifying `ExecutionResult` can affect `data`, `errors`, `path`, `locations`, and `extensions` that clients rely on. Only change what is necessary and preserve GraphQL semantics.

**Watch interceptor ordering.** One interceptor may populate context needed by another interceptor or resolver. Declare bean order explicitly and test the full pipeline rather than only testing each interceptor in isolation.

**Separate transport concerns from business logic.** Do not let controllers or services depend on `HttpServletRequest`, `ServerWebExchange`, or WebSocket sessions when they only need tenant, locale, or principal. Passing required data through `GraphQLContext` keeps resolvers independent of the transport.

## 10. Workflow for applying WebGraphQlHandler

When you need to add shared processing for GraphQL requests, you can follow this sequence:

1. Determine whether the logic belongs to the web request layer or to resolver/service business logic.
2. Choose `WebGraphQlInterceptor` for before/after per-request handling; choose `WebSocketGraphQlInterceptor` when connection lifecycle callbacks are needed.
3. Read the needed details from `WebGraphQlRequest` and pass only verified data into `GraphQLContext`.
4. Register interceptors as Spring Boot beans or via `WebGraphQlHandler.builder(...).interceptor(...)` in standalone configurations.
5. Verify how interceptors handle responses, errors, cancellation, and HTTP headers.
6. Use `WebGraphQlTester` to test the handler chain; use transport-specific testers for behaviors that can only be verified over real HTTP or WebSocket.

By clearly separating the responsibilities of transport handlers, `WebGraphQlHandler`, interceptors, and `ExecutionGraphQlService`, you can extend centralized request handling while keeping resolvers and services easy to test and decoupled from transport protocols.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [WebGraphQlHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
