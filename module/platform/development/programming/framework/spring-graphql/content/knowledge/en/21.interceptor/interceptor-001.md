# `WebGraphQlInterceptor` in Spring for GraphQL

`WebGraphQlInterceptor` is a transport-layer extension point in Spring for GraphQL that allows an application to intercept a GraphQL request before GraphQL Java executes it and process the response after execution completes. An interceptor can read HTTP request or WebSocket handshake information, add data to `ExecutionInput`, put metadata into `GraphQLContext`, add HTTP response headers, and observe or transform the GraphQL result.

In a Spring for GraphQL application, controllers such as `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` focus on individual fields. `WebGraphQlInterceptor` handles concerns that span multiple fields and operations, such as correlation IDs, request metadata, timing, passing necessary headers into the context, or normalizing certain request-level errors.

## 1. Where Does the Interceptor Sit in the GraphQL Request Lifecycle?

For HTTP and WebSocket, Spring for GraphQL invokes a chain of zero or more `WebGraphQlInterceptor` instances, then forwards the request to `ExecutionGraphQlService`. This service invokes GraphQL Java to parse, validate, and execute the document.

```text
HTTP request / WebSocket message
              |
              v
      WebGraphQlInterceptor A
              |
              v
      WebGraphQlInterceptor B
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
       response processing
              |
              v
        HTTP / WebSocket
```

An interceptor can perform work before and after `chain.next(request)`:

- Before `chain.next`: read headers, cookies, URI, request attributes, or enrich the context for execution.
- After `chain.next`: read `WebGraphQlResponse`, log results, add HTTP response headers, or transform the execution result when there is a clear reason.

`WebGraphQlInterceptor` applies to GraphQL over HTTP and WebSocket. RSocket has its own interceptor, `RSocketQlInterceptor`. With WebSocket, `WebGraphQlInterceptor` is invoked for each GraphQL request on the connection; to handle connection lifecycle and events such as connection initialization, consider `WebSocketGraphQlInterceptor`.

## 2. Structure of `WebGraphQlInterceptor`

The interface has the main method:

```java
Mono<WebGraphQlResponse> intercept(
    WebGraphQlRequest request,
    WebGraphQlInterceptor.Chain chain
);
```

The two parameters have the following roles:

| Parameter | Role |
|---|---|
| `WebGraphQlRequest request` | Represents the GraphQL request at the web layer; provides the GraphQL document, variables, and transport information such as headers, cookies, URI, remote address, and attributes. |
| `Chain chain` | Represents the rest of the interceptor chain and `ExecutionGraphQlService`; call `chain.next(request)` to pass the request forward. |

The return type is `Mono<WebGraphQlResponse>` because GraphQL processing can be asynchronous. Interceptors should preserve the reactive flow and must not call `block()` or subscribe manually.

Minimal interceptor example:

```java
@Component
class LoggingGraphQlInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(LoggingGraphQlInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        log.debug("GraphQL request id={}", request.getId());

        return chain.next(request)
            .doOnNext(response ->
                log.debug("GraphQL response id={}, errors={}",
                    request.getId(), response.getErrors().size())
            );
    }
}
```

This is how logging is placed at the request/response boundary. In real-world applications, use a structured logger and avoid logging the entire GraphQL document, variables, or sensitive data.

## 3. Reading Information from `WebGraphQlRequest`

`WebGraphQlRequest` provides commonly needed transport information:

| API | Information |
|---|---|
| `getHeaders()` | HTTP headers of the request or WebSocket handshake. |
| `getCookies()` | Cookies of the HTTP request or WebSocket handshake. |
| `getUri()` | URI of the HTTP request or WebSocket handshake. |
| `getRemoteAddress()` | Remote address if provided by the transport; may be absent. |
| `getAttributes()` | Request attributes or WebSocket session attributes. |
| `getId()` | Request ID assigned by the transport. |
| `getLocale()` | Locale if provided by the transport request. |
| `getDocument()` | The submitted GraphQL document. |
| `getVariables()` | Operation variables. |
| `getOperationName()` | Operation name if present. |

Example of reading headers:

```java
String clientVersion = request.getHeaders().getFirst("X-Client-Version");
String language = request.getHeaders().getFirst("Accept-Language");
```

Headers may be missing or contain invalid data. Check for null, format, and length before using them. Do not blindly trust `X-Forwarded-For`, `X-User-Id`, or client-supplied headers if proxies and the security layer have not verified the source of that data.

## 4. Putting Metadata into `GraphQLContext`

A common use of an interceptor is transferring certain transport information into `GraphQLContext`, where data fetchers and annotated controllers can access it.

`WebGraphQlRequest` extends `ExecutionGraphQlRequest`, which provides `configureExecutionInput(...)`. This method accepts a `BiFunction<ExecutionInput, ExecutionInput.Builder, ExecutionInput>` to configure `ExecutionInput` before GraphQL Java executes.

Example of generating a correlation ID, putting it into the context, and adding an HTTP response header:

```java
@Component
@Order(10)
class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String suppliedId = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = isValid(suppliedId)
            ? suppliedId
            : UUID.randomUUID().toString();

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put("correlationId", correlationId)
            ).build()
        );

        return chain.next(request).doOnNext(response -> {
            if (!(request instanceof WebSocketGraphQlRequest)) {
                response.getResponseHeaders()
                    .set("X-Correlation-Id", correlationId);
            }
        });
    }

    private boolean isValid(String value) {
        return value != null && value.matches("[A-Za-z0-9._-]{1,64}");
    }
}
```

Key imports:

```java
import org.springframework.core.annotation.Order;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.graphql.server.WebSocketGraphQlRequest;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

import java.util.UUID;
```

`configureExecutionInput` adds `correlationId` to the GraphQL context of the current execution. `WebGraphQlResponse.getResponseHeaders()` allows adding headers to the HTTP response. With WebSocket, the HTTP handshake has already completed before GraphQL operations are sent, so response headers of individual operations cannot become new HTTP response headers; the example skips this step for `WebSocketGraphQlRequest`.

A correlation ID from the client needs format validation and length limits before being logged or returned. If no valid value is present, the server generates a new ID. This ID is for request tracking, not proof of identity authentication.

## 5. Reading Context in Annotated Controllers

After the interceptor puts data into `GraphQLContext`, a resolver can accept `GraphQLContext` as a parameter:

```java
@Controller
class ProjectController {

    @QueryMapping
    Project project(@Argument("id") String id, GraphQLContext context) {
        String correlationId = context.get("correlationId");
        return projectService.findById(id, correlationId);
    }
}
```

You can use `@ContextValue` to bind a context value directly to a method parameter:

```java
@QueryMapping
Project project(
        @Argument("id") String id,
        @ContextValue("correlationId") String correlationId) {

    return projectService.findById(id, correlationId);
}
```

Choose how to receive the context based on your needs. `GraphQLContext` is suitable when a resolver needs multiple values or wants to control reading manually; `@ContextValue` is more convenient for a specific value.

Do not put the entire HTTP request, headers, or large transport objects into the GraphQL context. Only pass the values needed for GraphQL execution, such as correlation ID, verified tenant, locale, or authenticated principal.

## 6. Distinguishing Interceptors from Authentication and Authorization

`WebGraphQlInterceptor` can read the `Authorization` header and pass necessary information into `GraphQLContext`. However, reading a header does not mean the token has been successfully authenticated.

A commonly used architecture:

1. The Spring Security filter chain handles authentication, validates the token/session, and creates a verified `Authentication`.
2. `WebGraphQlInterceptor` adds metadata for GraphQL execution if needed.
3. The resolver or service performs authorization based on permissions and specific resources.

Do not manually decode a JWT without verifying its signature inside an interceptor and treat its claims as a trusted identity. Also do not use an arbitrary header like `X-User-Id` to make access control decisions.

If you only need to copy certain HTTP headers into the GraphQL context, Spring for GraphQL provides `HttpRequestHeaderInterceptor` out of the box:

```java
@Configuration
class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor headerInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Client-Version")
            .mapHeader("Accept-Language")
            .build();
    }
}
```

Controllers can read the mapped values via `@ContextValue`. For metadata that requires validation, normalization, or extraction from an authenticated principal, writing a custom interceptor or integrating with Spring Security is more appropriate.

## 7. Processing the Response After `chain.next(request)`

`chain.next(request)` returns `Mono<WebGraphQlResponse>`. Use Reactor operators to perform work after GraphQL finishes processing:

- `doOnNext`: log, update metrics, or add response headers without changing the response body.
- `map`: transform the response and return a new response.
- `onErrorResume`: handle errors originating within the interceptor's own reactive chain when an appropriate fallback exists.

Example of adding a processing time header:

```java
@Component
class ProcessingTimeInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();

        return chain.next(request).doOnNext(response -> {
            long elapsedMillis =
                (System.nanoTime() - startedAt) / 1_000_000;

            if (!(request instanceof WebSocketGraphQlRequest)) {
                response.getResponseHeaders().set(
                    "X-GraphQL-Duration-Ms",
                    Long.toString(elapsedMillis)
                );
            }
        });
    }
}
```

In production, metrics should usually be recorded via Micrometer/Observation rather than only returning processing time in a response header. The header above mainly illustrates how to add information to the HTTP response.

## 8. Inspecting and Transforming GraphQL Errors

An interceptor can read `response.getErrors()` after GraphQL Java processes the request. This is useful for request-level errors such as parse or validation errors, which occur before data fetchers are invoked.

`DataFetcherExceptionResolver` handles exceptions thrown by data fetchers during execution. It cannot handle request-level errors that occur before execution begins. When you need to observe or normalize such errors, `WebGraphQlInterceptor` can inspect `WebGraphQlResponse`.

Example of logging GraphQL errors present in the response, including request-level errors or execution errors:

```java
@Component
class InvalidRequestLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(InvalidRequestLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            if (!response.getErrors().isEmpty()) {
                log.debug("GraphQL request {} returned errors: {}",
                    request.getId(), response.getErrors().size());
            }
        });
    }
}
```

If you need to transform the error list, you can use `response.transform(builder -> builder.errors(newErrors).build())`. When doing so, preserve essential metadata such as message, locations, path, and extensions; do not strip errors just to make the response look successful. Changing the error contract directly affects clients and must be tested.

## 9. Ordering Multiple Interceptors

Interceptors are typically declared as Spring beans. Spring for GraphQL retrieves them in order from `ObjectProvider.orderedStream()`, so `@Order` or `Ordered` can be used to define the order.

Example:

```java
@Component
@Order(10)
class CorrelationIdInterceptor implements WebGraphQlInterceptor {
    // ...
}

@Component
@Order(20)
class ProcessingTimeInterceptor implements WebGraphQlInterceptor {
    // ...
}
```

With the two interceptors above:

- The request passes through `CorrelationIdInterceptor` first, then `ProcessingTimeInterceptor`.
- The response travels back through the interceptors in reverse order after the inner chain completes.

Ordering is critical if a later interceptor depends on context added by an earlier one. Place interceptors that create correlation IDs or tenant context before interceptors that need to read those values.

If an interceptor does not require a specific order, you can let Spring use the default order. Avoid using the same order value for interceptors with ordering dependencies unless additional rules are in place.

## 10. Registering Interceptors in Spring Boot

In a Spring Boot application using the Spring for GraphQL Starter, declaring an interceptor as a bean is the standard approach:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlInterceptorConfiguration {

    @Bean
    @Order(10)
    WebGraphQlInterceptor correlationIdInterceptor() {
        return new CorrelationIdInterceptor();
    }
}
```

Or annotate the implementation class with `@Component` as in the earlier examples. The Boot Starter detects interceptor beans and configures them into the `WebGraphQlHandler` chain.

If you create `WebGraphQlHandler` manually, you can configure the chain using its builder:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(correlationIdInterceptor)
    .build();
```

When using Spring Boot auto-configuration, you usually do not need to create a handler manually just to register interceptors. Choose one consistent configuration approach to avoid accidentally creating two GraphQL handlers or bypassing interceptor beans.

## 11. Distinguishing `WebGraphQlInterceptor` from Other Extensions

| Component | Scope | Purpose |
|---|---|---|
| `WebGraphQlInterceptor` | GraphQL over HTTP and per GraphQL request over WebSocket | Read transport requests, modify `ExecutionInput`, process responses, and add HTTP response headers. |
| `WebSocketGraphQlInterceptor` | WebSocket connections and requests | Extends `WebGraphQlInterceptor` with connection lifecycle and cancellation callbacks. |
| `RSocketQlInterceptor` | GraphQL over RSocket | Intercept RSocket transport requests/responses. |
| `DataFetcherExceptionResolver` | Errors from data fetchers | Convert exceptions during field execution into GraphQL errors. |
| GraphQL Java `Instrumentation` | GraphQL Java execution phases | Observe or deeply intervene in execution, validation, data fetchers, and metrics. |
| Spring Security filter chain | HTTP/security layer before the GraphQL handler | Authentication, web-layer authorization, CSRF, and HTTP policies. |

Choose the extension matching the exact boundary where you need to intervene. Do not use an interceptor to replace a resolver for a specific field; likewise, do not use `DataFetcherExceptionResolver` to handle parse/validation errors prior to execution.

## 12. Testing Interceptors with `WebGraphQlTester`

`WebGraphQlTester` lets you send requests through `WebGraphQlHandler`, meaning requests pass through the entire interceptor chain before reaching `ExecutionGraphQlService`. This is a suitable way to test header reading and context propagation.

Suppose a controller reads the correlation ID from the context:

```java
@Controller
class DiagnosticsController {

    @QueryMapping
    String correlationId(GraphQLContext context) {
        return context.get("correlationId");
    }
}
```

In the test, create a handler with the interceptor and use `WebGraphQlTester` with simulated headers:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(new CorrelationIdInterceptor())
    .build();

WebGraphQlTester tester = WebGraphQlTester.builder(handler)
    .headers(headers -> headers.set("X-Correlation-Id", "test-123"))
    .build();

tester.document("""
        query {
            correlationId
        }
        """)
    .execute()
    .path("correlationId")
    .entity(String.class)
    .isEqualTo("test-123");
```

Illustrative example; `executionGraphQlService` needs to be created from the application's schema and runtime wiring. This test verifies that the header is read, put into `GraphQLContext`, and usable by the resolver.

Scenarios that should be tested:

- Valid header values are transferred into the context.
- Missing or malformed headers cause the server to generate a new correlation ID.
- The interceptor still forwards the request and does not unintentionally block the reactive chain.
- The HTTP response has the header added after GraphQL finishes processing.
- Request-level validation errors are observed properly.
- Multiple interceptors run in the right order and context added earlier is used by later interceptors.
- WebSocket requests do not rely on HTTP response headers per operation.

## 13. Security and Performance Considerations

Interceptors run in the path of every request for the configured transport. Therefore, logic here should be concise and bounded.

1. Do not log the Authorization header, cookies, access tokens, or full variables.
2. Do not trust client-sent user IDs, roles, or tenant IDs in headers unless authenticated.
3. Only add necessary data to `GraphQLContext`; avoid putting large request objects or unnecessary mutable objects.
4. Avoid synchronous database or remote service calls inside an interceptor. If data loading is needed, use asynchronous APIs and consider placing the logic in an appropriate service/resolver.
5. Do not call `block()` or subscribe manually inside `intercept`; return the `Mono` created from `chain.next(request)`.
6. Restrict the size, format, and source of client-supplied correlation IDs or metadata.
7. Do not modify GraphQL errors broadly without clearly understanding the impact on clients.
8. For HTTP response headers, consider CORS and do not put sensitive data in headers.

If you need to limit request processing time, Spring for GraphQL also provides `TimeoutWebGraphQlInterceptor`. You can register this interceptor as a bean to apply timeouts to web transports; on timeout, the request is cancelled and reactive work can receive a cancellation signal.

## 14. Common Pitfalls

**Forgetting to call `chain.next(request)`.** If an interceptor neither forwards the request nor actively creates an appropriate response, GraphQL execution does not happen. For a typical interceptor, return `chain.next(request)`.

**Calling `chain.next(request)` multiple times.** This can cause the same GraphQL request to be executed multiple times. Only call the chain once for a normal intercept.

**Calling `block()` or `subscribe()` inside the interceptor.** This breaks the reactive flow, blocks threads, or detaches errors from GraphQL execution. Compose using `map`, `doOnNext`, and appropriate Reactor operators.

**Confusing HTTP response headers with GraphQL response data.** `getResponseHeaders()` holds transport headers; it does not add fields to the GraphQL `data` section. For WebSocket, the HTTP handshake is already complete, so new headers cannot be added per operation.

**Using an interceptor to validate tokens manually.** Reading a header does not verify the signature, issuer, audience, or expiration of a token. Use Spring Security or a dedicated authentication mechanism.

**Setting context after the chain has run.** `ExecutionInput` must be configured before `chain.next(request)` so resolvers can read the values.

**Using an interceptor for a specific field's errors.** Errors from data fetchers should be handled with `DataFetcherExceptionResolver` or an appropriate handler; interceptors are better suited for request-level concerns and transport responses.

**Not specifying interceptor ordering.** An interceptor that depends on another interceptor's context may run before the value is added. Use `@Order`/`Ordered` when an explicit order is needed.

## Conclusion

`WebGraphQlInterceptor` provides an extension point before and after GraphQL execution for HTTP and WebSocket transports. Implement `intercept(request, chain)`, read transport information, use `configureExecutionInput` to enrich `GraphQLContext`, call `chain.next(request)`, and process the response in the reactive pipeline. Register interceptors as Spring beans, define ordering when dependencies exist, and test via `WebGraphQlTester`. Keep interceptors focused on cross-cutting request concerns so authentication, authorization, and field error handling remain in their proper application layers.

## References

- [Spring for GraphQL — Server Transports and Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL API — `WebGraphQlInterceptor`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL API — `WebGraphQlRequest`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlRequest.html)
- [Spring for GraphQL — Testing `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/reference/testing.html)
