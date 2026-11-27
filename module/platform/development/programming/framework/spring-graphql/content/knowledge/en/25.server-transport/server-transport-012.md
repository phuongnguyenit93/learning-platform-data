# Transport and execution service

Spring for GraphQL separates receiving GraphQL requests over the network from executing operations. HTTP, WebSocket, Server-Sent Events (SSE), and RSocket are different transports; they pass requests into the same GraphQL execution layer so schemas, resolvers, DataLoaders, and error-handling rules can be shared.

Two key components in this architecture are **ExecutionGraphQlService** and **WebGraphQlHandler**. `ExecutionGraphQlService` invokes GraphQL Java to execute requests in a transport-agnostic way. `WebGraphQlHandler` sits at the web layer, runs the interceptor chain for HTTP and WebSocket, and forwards requests to the execution service. Understanding this boundary helps you choose the right transport, place authentication and context logic at the proper layer, and test execution without starting a server.

## 1. GraphQL request processing flow on the server

A request travels from the client to resolvers through several layers:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B{"Transport"}
    B --> C["HTTP handler"]
    B --> D["WebSocket handler"]
    B --> E["SSE handler"]
    B --> F["RSocket handler"]
    C --> G["WebGraphQlHandler"]
    D --> G
    E --> G
    G --> H["WebGraphQlInterceptor chain"]
    H --> I["ExecutionGraphQlService"]
    F --> J["RSocketQlInterceptor chain"]
    J --> I
    I --> K["GraphQlSource / GraphQL Java"]
    K --> L["Parse, validate, coerce"]
    L --> M["Execute DataFetcher / controller"]
    M --> N["ExecutionResult"]
    N --> O["Transport response"]
~~~

This flow can be read as three groups of responsibilities:

- **Transport layer:** receives data over HTTP, WebSocket, SSE, or RSocket; decodes requests; enforces protocol rules; writes responses or streams back to the client.
- **Request interception:** inspects transport-level details, adds context, correlation IDs, headers, or metadata; can adjust execution input and responses.
- **Execution layer:** uses the schema and runtime wiring to parse, validate, and execute queries, mutations, or subscriptions; invokes DataFetchers and aggregates results.

The transport does not dictate how resolvers query a database. Likewise, resolvers should not read HTTP requests directly or care whether the client uses WebSocket or RSocket unless business logic genuinely requires it.

## 2. GraphQlSource and ExecutionGraphQlService

### GraphQlSource

`GraphQlSource` is the abstraction providing the `graphql.GraphQL` object that the server invokes. It offers a builder to construct the GraphQL schema and configure runtime wiring.

In Spring Boot, schemas are typically placed under:

~~~text
src/main/resources/graphql/
~~~

Files with `.graphqls` or `.gqls` extensions under `classpath:graphql/**` are automatically discovered and merged into the schema. `GraphQlSource.Builder` also accepts schema resources from other locations if an application needs custom configuration.

The builder is also where runtime components are wired:

- `RuntimeWiringConfigurer` registers custom scalars, directives, type resolvers, or DataFetchers.
- `AnnotatedControllerConfigurer` detects methods annotated with `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, and `@SchemaMapping` and registers them as DataFetchers.
- `Instrumentation` supports observing and hooking into execution.
- `DataFetcherExceptionResolver` handles exceptions raised while fetching a field.
- `SubscriptionExceptionResolver` handles errors occurring after a subscription's `Publisher` has started emitting data.

Spring Boot auto-detects matching configuration beans and supplies them when building `GraphQlSource`. Most applications using Boot do not need to create a `GraphQL` instance manually.

### ExecutionGraphQlService

`ExecutionGraphQlService` is the central abstraction for executing GraphQL requests via GraphQL Java. This interface is not tied to HTTP, WebSocket, or RSocket.

The default implementation is `DefaultExecutionGraphQlService`. It takes `GraphQlSource`, obtains the `GraphQL` instance from that source, and executes requests. Spring Boot auto-configures this service and its related components.

Responsibilities can be distinguished as follows:

| Component | Responsibility |
| --- | --- |
| `GraphQlSource` | Provides the configured GraphQL schema and GraphQL runtime |
| `ExecutionGraphQlService` | Accepts execution requests and invokes GraphQL Java |
| `DefaultExecutionGraphQlService` | Default implementation of the execution service |
| `WebGraphQlHandler` | Runs the interceptor chain for HTTP/WebSocket and calls the execution service |
| HTTP/WebSocket/SSE handler | Translates requests and responses per transport |
| `GraphQlRSocketHandler` | Translates RSocket requests into GraphQL execution and returns results per interaction model |

Key point: the same `ExecutionGraphQlService` can be shared across multiple transports. Adding WebSocket or SSE does not require rewriting resolvers or schemas.

## 3. Configuring transports with Spring Boot

An application needs `spring-boot-starter-graphql` and at least one starter providing a server transport. Common options:

| Dependency | Transport provided | Foundation |
| --- | --- | --- |
| `spring-boot-starter-graphql` | GraphQL schema and execution | Spring for GraphQL |
| `spring-boot-starter-web` | HTTP | Spring MVC |
| `spring-boot-starter-websocket` | WebSocket | Servlet application |
| `spring-boot-starter-webflux` | HTTP and WebSocket | Spring WebFlux |
| `spring-boot-starter-rsocket` | RSocket over TCP or WebSocket | Reactor Netty / Spring Messaging |

Example of an application using Spring MVC over HTTP:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

If the application uses WebFlux, replace the MVC starter with `spring-boot-starter-webflux`. Add only the transports the system actually needs; there is no reason to install every starter simply because GraphQL supports multiple protocols.

With Boot, the default HTTP endpoint is `POST /graphql`. The path can be changed via `spring.graphql.http.path`. The HTTP endpoint is provided by auto-configuration through a `RouterFunction`.

Example configuration:

~~~yaml
spring:
  graphql:
    http:
      path: /graphql
    websocket:
      path: /graphql
    rsocket:
      mapping: graphql
~~~

These properties configure their respective transports. The WebSocket endpoint is not enabled by default simply because GraphQL is present. You must configure `spring.graphql.websocket.path`; Servlet applications also need `spring-boot-starter-websocket`. With WebFlux, no separate WebSocket starter is needed.

RSocket requires an RSocket server to be configured and the GraphQL route specified via `spring.graphql.rsocket.mapping`.

## 4. HTTP transport

HTTP fits single-response requests, especially queries and mutations. `GraphQlHttpHandler` receives HTTP requests, converts the payload into a GraphQL request, and delegates to the interceptor chain.

Spring for GraphQL provides two HTTP handler implementations: one for Spring MVC and one for Spring WebFlux. They have equivalent GraphQL behavior; the difference lies in how responses are written, with MVC relying on Servlet I/O and WebFlux using non-blocking I/O.

By default, the HTTP endpoint accepts `POST` with:

- `Content-Type: application/json`
- A JSON body containing the GraphQL document and request metadata.

Example request:

~~~http
POST /graphql
Content-Type: application/json
Accept: application/graphql-response+json
~~~

~~~json
{
  "query": "query GetBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "GetBook",
  "variables": {
    "id": "book-42"
  }
}
~~~

Main properties:

| Property | Meaning |
| --- | --- |
| `query` | GraphQL document as a string |
| `operationName` | Name of the operation to execute when the document contains multiple operations |
| `variables` | Values for the variables declared in the document |
| `extensions` | Extended metadata, such as persisted queries if supported by the server |

The response is a GraphQL JSON response, typically containing `data` and optionally `errors`:

~~~json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL"
    }
  }
}
~~~

The HTTP transport supports two notable media types:

- `application/graphql-response+json`: the media type defined by the GraphQL over HTTP specification.
- `application/json`: legacy compatibility format used by many clients.

Once a request passes parsing and validation, errors during field execution are represented in the `errors` section of the GraphQL response. With `application/graphql-response+json`, parse or validation errors can be reflected via HTTP 4xx; with legacy `application/json`, those cases typically still return HTTP 200. Transport errors such as server unavailability, failed HTTP authentication, or invalid JSON bodies can still return 4xx/5xx.

HTTP POST is not intended for streaming subscriptions. Use WebSocket or SSE when clients need to receive multiple events from a subscription.

## 5. HTTP GET and safety restrictions

Spring for GraphQL can enable HTTP GET per the GraphQL over HTTP specification, though GET is disabled by default. To enable it, configure both the handler and the endpoint's request predicate.

Handler-level example:

~~~java
GraphQlHttpHandler httpHandler = GraphQlHttpHandler
        .builder(webGraphQlHandler)
        .httpMethods(HttpMethod.GET, HttpMethod.POST)
        .build();
~~~

With GET, no request body is used. Parameters are passed in the query string:

- `query` and `operationName` are plain strings.
- `variables` and `extensions`, if present, must be JSON encoded as strings.

GET is only suitable for safe operations like queries. If a client sends a mutation via GET, the server rejects it with `405 Method Not Allowed`, even if the mutation document is valid.

Before enabling GET, consider:

- Query strings can appear in access logs, browser history, `Referer` headers, proxies, or caches.
- Do not pass tokens, personal data, or sensitive data inside variables over GET.
- GET is a CORS simple request in many cases and is treated as an HTTP safe method by Spring Security's CSRF filter.
- Query resolvers can still generate load, write audit logs, or cause side effects if poorly designed. Queries should preserve read-only semantics.

If the request URI becomes too long, clients should switch to POST.

## 6. Server-Sent Events (SSE)

`GraphQlSseHandler` delivers subscriptions over HTTP Server-Sent Events. Clients send a GraphQL request via HTTP POST with a JSON body just like the HTTP transport, while setting the header:

~~~http
Accept: text/event-stream
~~~

The server sends results as one or more Server-Sent Events. This is an alternative to WebSocket when an application only needs one-way server-to-client data streaming.

SSE suits subscriptions where clients only need to receive events. It is not suitable for executing queries or mutations; those two operation types should use standard HTTP JSON.

By default SSE uses POST. GET can be enabled if clients use browser `EventSource`, though both the handler and request predicate must be configured. All security considerations for GET also apply to SSE GET.

Spring for GraphQL implements a distinct-connections mode for SSE. When deploying many client subscriptions, evaluate concurrent connection counts, resource limits, and HTTP version impacts. HTTP/2 can help reduce connection overhead in certain architectures.

## 7. WebSocket transport

WebSocket keeps a bidirectional connection open between client and server. GraphQL over WebSocket is commonly chosen for subscriptions because the server can push multiple results over the same connection. The protocol supported by Spring for GraphQL is `graphql-ws`.

`GraphQlWebSocketHandler` handles this protocol. Implementations exist for Spring MVC and Spring WebFlux. Both support asynchronous requests; WebFlux uses non-blocking I/O and backpressure to deliver streams.

WebSocket can also run single-response queries or mutations, though its primary advantage is subscriptions and reusing connections across multiple requests.

### Enabling the WebSocket endpoint

With Spring Boot:

1. Add `spring-boot-starter-websocket` if the application runs on Servlet/Spring MVC.
2. With Spring WebFlux, no separate WebSocket dependency is required.
3. Set `spring.graphql.websocket.path` to enable the endpoint.

Example:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

### Authentication on WebSocket

WebSocket has its own connection lifecycle. Clients can send credentials in the `connection_init` message payload. `WebSocketGraphQlInterceptor` enables handling connection start, connection close, and client subscription cancellation.

Spring for GraphQL includes `AuthenticationWebSocketInterceptor` for WebMVC and WebFlux to extract credentials from `connection_init`, authenticate, and propagate `SecurityContext` to subsequent requests on the same connection.

One `WebSocketGraphQlInterceptor` can be registered per chain. When designing authentication, explicitly define when tokens are checked, how expired tokens are handled, and how permission revocation works on long-lived connections.

### Resource management

One WebSocket session can hold multiple concurrent subscriptions. Limit:

- Maximum WebSocket connections at the server/connector.
- Maximum message buffer size.
- Concurrent subscriptions per session.

`GraphQlWebSocketHandler` provides the `maxSubscriptionsPerSession` option. It is unlimited by default; once the configured limit is hit, the session is closed. Set thresholds appropriate to your server's CPU, memory, and actual load.

## 8. RSocket transport

RSocket supports GraphQL over TCP or WebSocket. The main difference lies in the interaction model:

| GraphQL operation | RSocket interaction |
| --- | --- |
| Query | `request-response` |
| Mutation | `request-response` |
| Subscription | `request-stream` |

`GraphQlRSocketHandler` receives payloads and passes them to GraphQL execution. Applications can delegate to the handler from a Spring Messaging controller:

~~~java
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.graphql.server.GraphQlRSocketHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GraphQlRSocketController {

    private final GraphQlRSocketHandler handler;

    public GraphQlRSocketController(GraphQlRSocketHandler handler) {
        this.handler = handler;
    }

    @MessageMapping("graphql")
    public Mono<Map<String, Object>> handle(Map<String, Object> payload) {
        return handler.handle(payload);
    }

    @MessageMapping("graphql")
    public Flux<Map<String, Object>> handleSubscription(Map<String, Object> payload) {
        return handler.handleSubscription(payload);
    }
}
~~~

In Spring Boot, the corresponding route can be configured via `spring.graphql.rsocket.mapping`. RSocket fits systems needing message-oriented, reactive communication between services or between client and server. If a system only needs simple HTTP request-response, RSocket does not automatically make GraphQL queries faster; choose based on connection and protocol requirements.

## 9. WebGraphQlHandler and the interceptor chain

`WebGraphQlHandler` is the orchestration layer for web transports. HTTP and WebSocket handlers do not invoke resolvers directly; they pass requests to `WebGraphQlHandler`. The handler runs a chain of `WebGraphQlInterceptor` instances, then invokes `ExecutionGraphQlService`.

`WebGraphQlInterceptor` can:

- Read HTTP request details such as headers, URI, or principal.
- Add values to `ExecutionInput` and `GraphQLContext`.
- Add response headers.
- Inspect or modify `ExecutionResult`.
- Log and measure request duration.

Example copying a correlation ID from a header into the GraphQL context:

~~~java
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

        if (correlationId != null && !correlationId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("correlationId", correlationId)
                    ).build()
            );
        }

        return chain.next(request).doOnNext(response -> {
            if (correlationId != null && !correlationId.isBlank()) {
                response.getResponseHeaders()
                        .set("X-Correlation-Id", correlationId);
            }
        });
    }
}
~~~

A resolver can read this value from context:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class TraceController {

    @QueryMapping
    public String traceId(@ContextValue("correlationId") String correlationId) {
        return correlationId;
    }
}
~~~

The example above uses a header for correlation purposes. Do not use a client-supplied header as proof of identity or tenant access rights. Principal and permissions must be verified by Spring Security or a trusted security mechanism before being placed into the GraphQL context.

Spring for GraphQL also provides `HttpRequestHeaderInterceptor` to copy selected HTTP headers into the GraphQL context. If you only need to pass through specific headers, you can use this built-in interceptor instead of writing a custom one.

## 10. Context and request metadata

Each GraphQL operation may need metadata such as:

- Correlation ID or trace ID.
- Request locale.
- Authenticated principal details.
- Tenant or allowed data scope.
- Feature flags or request-scoped configuration.

`ExecutionGraphQlRequest` supplies the data used to build `ExecutionInput`, including document, operation name, variables, extensions, locale, and execution ID. It also allows customizing `ExecutionInput` before invoking GraphQL Java.

Use `GraphQLContext` for data needed by DataFetchers, controller methods, instrumentation, or batch loaders. In annotated controllers, you can inject `GraphQLContext` directly or use `@ContextValue` to read a value by key.

Context belongs to a single request/execution. Never store principal, tenant, or request metadata in mutable fields of a singleton controller, as concurrent requests could leak data across users.

With WebFlux, Spring for GraphQL supports propagating Reactor Context from the transport pipeline to reactive DataFetchers. With Spring MVC, DataFetchers may run on threads different from the initial HTTP thread during asynchronous execution; if custom `ThreadLocal` values must be propagated, register an appropriate context propagation mechanism such as Micrometer's `ThreadLocalAccessor`.

## 11. Transport determines which operations are allowed

Not every transport supports every operation type:

| Transport | Query | Mutation | Subscription |
| --- | --- | --- | --- |
| HTTP POST | Yes | Yes | Not streamed directly |
| HTTP GET | Yes | No | No |
| HTTP SSE | Not used for single-response operations | No | Yes |
| WebSocket | Yes | Yes | Yes |
| RSocket | Request-response | Request-response | Request-stream |

These restrictions are part of the protocols. Spring for GraphQL attaches the list of allowed operation types to the execution request; before executing, GraphQL Java verifies whether the operation matches the transport. If not, the request is rejected with an unsupported operation error.

Do not try to execute mutations over GET. GET is a safe method under HTTP semantics and must not be used for operations with side effects. Similarly, do not send a subscription over ordinary HTTP POST expecting the server to hold the response open as a stream; choose WebSocket or SSE instead.

## 12. Asynchronous execution and reactive return types

GraphQL often needs to fetch multiple nested fields. GraphQL Java uses `AsyncExecutionStrategy` so DataFetchers can run concurrently instead of sequentially whenever possible.

Spring for GraphQL supports DataFetchers and controller methods returning:

- `CompletionStage` or `CompletableFuture`.
- Reactor `Mono` or `Flux`.
- Kotlin coroutines.
- `Callable` in `@SchemaMapping` and `@BatchMapping` methods when an appropriate `Executor` is configured.

Example resolver returning `Mono`:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

During normal execution, `Mono` is adapted into an asynchronous result compatible with GraphQL Java. `Flux` is collected into a list for collection-returning fields. Specifically for subscriptions, the publisher is retained to emit multiple results over time.

Differences between MVC and WebFlux:

- Spring MVC supports asynchronous request execution; responses can complete synchronously for simple operations, or asynchronously when fetchers return futures/reactive types.
- Spring WebFlux uses non-blocking I/O and Reactor pipelines. For subscription streams, backpressure throttles data delivery.

Never call `block()` or perform long-running blocking I/O on WebFlux's event loop. If you must call a blocking library, offload it to an appropriate executor. A reactive transport does not automatically make a blocking call non-blocking.

## 13. Timeouts and request cancellation

GraphQL operations can consume heavy resources if queries are deep, return too much data, or wait too long on dependencies. For web transports, Spring for GraphQL provides `TimeoutWebGraphQlInterceptor`.

Example configuring a 5-second timeout in Spring Boot:

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

On timeout, the interceptor sends a cancellation signal up the processing chain. Reactive DataFetchers can observe cancellation and stop ongoing work if the data source supports cancellation.

GraphQL-layer timeouts do not replace HTTP client timeouts, database timeouts, outbound service HTTP client timeouts, or dedicated timeouts on WebSocket/SSE handlers. Set limits on dependencies so a cancelled request does not keep holding backend resources.

With WebSocket, in addition to request timeouts, manage connection lifetimes, concurrent subscription counts, and event emission rates. A long-lived connection does not mean every subscription should run forever.

## 14. Handling errors at the right layer

Different kinds of errors arise at different stages:

| Error type | Stage | Appropriate mechanism |
| --- | --- | --- |
| Invalid JSON, missing credentials, server unavailable | Transport before GraphQL execution | HTTP/WebSocket/RSocket server and Spring Security |
| Parse, schema validation, input coercion | GraphQL engine before invoking DataFetchers | Request-level handling; web interceptors can inspect the response |
| Exception in DataFetcher/resolver | During field execution | `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` |
| Subscription publisher terminates with an error | After subscription has started streaming | `SubscriptionExceptionResolver` and transport stream |

`DataFetcherExceptionResolver` only handles exceptions thrown by DataFetchers. It does not handle document parse or validation errors because no DataFetcher has been called yet at that point.

With web transports, `WebGraphQlInterceptor` can inspect `WebGraphQlResponse` after `chain.next(request)` completes. This is the right place if you need to adjust request-level errors that resolvers cannot see.

Subscriptions add another asynchronous stage: the DataFetcher returns a `Publisher` first, and then the transport subscribes to that `Publisher`. If the `Publisher` emits an error later, `DataFetcherExceptionResolver` is no longer in the call path to handle it; use `SubscriptionExceptionResolver` for that case.

Separating layers cleanly avoids funneling every exception into one generic handler and returning the same response for errors with completely different causes.

## 15. Manual configuration without Spring Boot

Spring Boot automatically creates many components: `GraphQlSource`, `ExecutionGraphQlService`, `BatchLoaderRegistry`, web handlers, and endpoints. If an application does not use Boot, register the required beans manually.

Example for the execution service:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultBatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultExecutionGraphQlService;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionConfiguration {

    @Bean
    BatchLoaderRegistry batchLoaderRegistry() {
        return new DefaultBatchLoaderRegistry();
    }

    @Bean
    ExecutionGraphQlService executionGraphQlService(
            GraphQlSource graphQlSource,
            BatchLoaderRegistry batchLoaderRegistry) {

        DefaultExecutionGraphQlService service =
                new DefaultExecutionGraphQlService(graphQlSource);

        service.addDataLoaderRegistrar(batchLoaderRegistry);
        return service;
    }
}
~~~

Then create the web handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlWebConfiguration {

    @Bean
    WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            WebGraphQlInterceptor interceptor) {

        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptor(interceptor)
                .build();
    }
}
~~~

`GraphQlSource` still requires schema resources and appropriate runtime wiring. If using annotated controllers, configure `AnnotatedControllerConfigurer` as a `RuntimeWiringConfigurer` and register the corresponding exception resolvers. When assembling the entire stack manually, you must also create the concrete transport endpoints, such as an HTTP `RouterFunction` or WebSocket mapping.

This is advanced configuration. For standard Spring Boot applications, prefer auto-configuration and customize via beans/properties only when specific requirements demand it.

## 16. Testing the execution service and transport

Spring for GraphQL provides `GraphQlTester` with a unified testing API. You can test at different levels:

Add the `spring-graphql-test` dependency in test scope if your project does not already include it via dependency management:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

| Tester | Testing scope |
| --- | --- |
| `ExecutionGraphQlServiceTester` | Calls the execution service directly, no network required |
| `WebGraphQlTester` | Tests server-side web handler and interceptor chain |
| `HttpGraphQlTester` | Sends requests over HTTP; can use `WebTestClient` with a real or mock server |
| `WebSocketGraphQlTester` | Tests WebSocket protocol and connection |
| `RSocketGraphQlTester` | Tests RSocket transport |

Example testing the execution service directly:

~~~java
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("""
        query {
            greeting
        }
        """)
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello");
~~~

This style of testing is fast and great for verifying schemas, resolvers, and execution. It does not check HTTP routes, JSON codecs, CORS, WebSocket handshakes, or RSocket configuration.

When testing the transport, use the corresponding tester. For HTTP, `HttpGraphQlTester` uses `WebTestClient`. You can bind `WebTestClient` to the application context without opening a real port, or bind to a running server for end-to-end tests.

With WebSocket and RSocket, remember to close the tester/connection after tests if the tester provides `stop()`. For subscriptions, test emitted items, client subscription cancellation, and behavior when the publisher terminates with an error.

## 17. Choosing a transport by use case

| Need | Suitable choice | Reason |
| --- | --- | --- |
| Queries/mutations from browsers or standard apps | HTTP POST | Easy integration, one request per response |
| Cacheable queries with no sensitive data | Explicitly enabled HTTP GET | Can leverage caches/proxies; safe operations only |
| Simple server-to-client event tracking | SSE | One-way, uses HTTP, and integrates easily with `EventSource` |
| Bidirectional subscriptions, multiple operations on one connection | WebSocket | Long-lived connection, supports multiplexing multiple subscriptions |
| Message-oriented communication between services or reactive clients | RSocket | `request-response` and `request-stream` over TCP/WebSocket |

No transport replaces proper query design, pagination, depth limits, result size limits, and DataFetcher optimization. The transport only determines how requests and responses travel over the network.

## 18. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `/graphql` returns 404 | Missing transport starter or endpoint path changed | Check MVC/WebFlux starter and `spring.graphql.http.path` |
| WebSocket handshake fails | `spring.graphql.websocket.path` not enabled or missing WebSocket starter for Servlet | Check dependencies and endpoint configuration |
| Subscription over HTTP POST does not stream | HTTP JSON handler returns a single response | Switch to WebSocket or SSE |
| GET mutation is rejected | GET is a safe method and must not run mutations | Use POST |
| Interceptor is not invoked | Bean not detected or request bypasses the expected web handler | Check component scan and transport configuration |
| `DataFetcherExceptionResolver` misses parse errors | Errors happen before DataFetchers are invoked | Handle request-level errors in an appropriate interceptor |
| Subscription terminating with error is not normalized | Error occurs after `Publisher` was returned | Register `SubscriptionExceptionResolver` |
| Context is null inside resolver | Value not added to `GraphQLContext` or key mismatch | Check interceptor and `@ContextValue` |
| Requests are slow despite using WebFlux | Blocking work on the event loop or missing dependency timeouts | Offload blocking I/O to an executor and set timeouts |
| WebSocket server uses excessive memory | Too many connections/subscriptions or large message buffers | Limit connections, message sizes, and subscriptions per session |
| Service tests pass, but HTTP endpoint fails | Tests bypass the transport layer | Add `HttpGraphQlTester` or the appropriate transport tester |

## 19. Workflow for designing server transport

When implementing a Spring for GraphQL server, follow this sequence:

1. Choose Spring MVC or WebFlux based on your application's I/O model.
2. Add `spring-boot-starter-graphql` and the required transport starter.
3. Place schema resources in `classpath:graphql/**` or configure a custom location.
4. Register controllers and `RuntimeWiringConfigurer` beans to create DataFetchers.
5. Let Spring Boot configure `GraphQlSource` and `ExecutionGraphQlService` whenever possible.
6. Use HTTP for queries/mutations; enable WebSocket or SSE if subscriptions are needed.
7. Add interceptors to populate safe metadata into `GraphQLContext`.
8. Configure authentication, authorization, CORS, and CSRF according to the transport.
9. Set timeouts and limits on connections, message sizes, and subscription counts.
10. Test the execution service directly, then test the actual transports.

## 20. Key points to remember

- The transport receives and returns GraphQL requests/responses per protocol; the execution service executes operations using GraphQL Java.
- `GraphQlSource` provides the configured schema and GraphQL runtime.
- `DefaultExecutionGraphQlService` is the default implementation of `ExecutionGraphQlService`.
- HTTP POST fits single-response queries and mutations; HTTP GET is reserved for safe operations.
- SSE and WebSocket support subscription streams; RSocket uses `request-stream` for subscriptions.
- `WebGraphQlHandler` runs the `WebGraphQlInterceptor` chain before the execution service.
- Use `GraphQLContext` for per-request metadata; never store request state in mutable fields of singleton controllers.
- `DataFetcherExceptionResolver` handles field-execution errors; request errors and subscription publisher errors require their own mechanisms.
- WebFlux supports non-blocking I/O and backpressure; avoid blocking on the event loop.
- Testing `ExecutionGraphQlService` does not replace testing HTTP, WebSocket, or RSocket transports.

Separating transports from the execution service lets Spring for GraphQL support multiple protocols while sharing schemas, controllers, DataLoaders, and business logic. Choosing transports by interaction pattern, placing interceptors at the right layer, and testing both execution and network boundaries makes the server easier to scale and operate.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
