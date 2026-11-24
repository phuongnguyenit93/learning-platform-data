# ServerWebExchange and the Reactive Request Lifecycle in Spring WebFlux

## Learning Objectives

Spring WebFlux processes HTTP reactively, unlike the "one thread held per request until completion" mental model common in synchronous programs. **ServerWebExchange** is the request-scoped HTTP context shared across WebFlux components to read the request, prepare the response, and pass data throughout processing.

After this lesson, you will be able to:

- Explain what `ServerWebExchange` is and why it is neither an HTTP session nor a Reactor `Context`.
- Distinguish `ServerHttpRequest`, `ServerHttpResponse`, exchange attributes, `WebSession`, and `Principal`.
- Describe the flow from the HTTP server through `HttpHandler`, `WebFilter`, and `DispatcherHandler` to the controller/handler and response.
- Write reactive `WebFilter`s properly without manual `subscribe()` or `block()` calls.
- Understand when a response is committed, how to attach headers, and the consequences of errors occurring after response emission starts.
- Analyze success, error, timeout, and cancellation lifecycles along with streaming/backpressure considerations.
- Test end-to-end request-to-response behavior with `WebTestClient`.

## 1. What Is ServerWebExchange?

In Spring WebFlux, the **org.springframework.web.server.ServerWebExchange** interface models the context of a single HTTP exchange at the `WebHandler` API level. It provides two core objects:

- **ServerHttpRequest** via `getRequest()`: describes the request received by the server.
- **ServerHttpResponse** via `getResponse()`: represents the response the server will write.

Beyond those two objects, the exchange provides a per-request attribute map, locale details, session, principal, and form/multipart data APIs.

You can picture it as:

~~~text
                       ServerWebExchange
                    (a single HTTP exchange)
                                |
        +-----------------------+-----------------------+
        |                       |                       |
   getRequest()            getResponse()         request context
        |                       |                       |
   method, URI,           status, headers,         attributes,
   headers, cookies,      cookies, response       WebSession,
   query, body            body, commit state      Principal, locale
~~~

**Important distinction:** A `ServerWebExchange` is tied to handling a single request, not to an entire TCP connection. With HTTP keep-alive or HTTP/2, the same connection can serve multiple requests; each request receives its own handling context.

Nor is an exchange an exact one-to-one equivalent of Spring MVC's **HttpServletRequest/HttpServletResponse**. WebFlux provides reactive abstractions and does not require a Servlet container when running on Reactor Netty.

### Commonly Used APIs

| API | Purpose | Notes |
|---|---|---|
| `exchange.getRequest()` | Retrieve `ServerHttpRequest` | Metadata and body are represented for reactive I/O. |
| `exchange.getResponse()` | Retrieve `ServerHttpResponse` | Adjust status/headers before the response commits. |
| `exchange.getAttributes()` | Mutable map tied to the current request | Shares data between filters and handlers. |
| `exchange.getAttribute(name)` | Read an optional attribute | May return `null` if absent. |
| `exchange.getRequiredAttribute(name)` | Read a required attribute | Throws an error if missing; avoid when a value may be absent. |
| `exchange.getSession()` | `Mono<WebSession>` | Does not automatically create or persist a populated session. |
| `exchange.getPrincipal()` | `Mono<Principal>` | May be empty if no user is authenticated. |
| `exchange.getLocaleContext()` | Resolved `LocaleContext` | Depends on the resolver and request. |
| `exchange.getFormData()` | `Mono<MultiValueMap<String,String>>` | For form-urlencoded data; parses and caches form data. |
| `exchange.getMultipartData()` | `Mono<MultiValueMap<String,Part>>` | For multipart requests; manage memory and resource costs. |
| `exchange.getLogPrefix()` | Log prefix tied to the exchange | Useful for correlating request logs. |
| `exchange.mutate()` | Creates a builder for a decorated exchange | Does not mutate the original request in place; forwards a modified request/response downstream. |

API names and details may expand across Spring Framework versions; in the examples below we use common APIs from Spring Framework 6.x and Spring Boot 3.x.

## 2. Where ServerWebExchange Fits in the WebFlux Architecture

WebFlux offers two levels of HTTP server abstraction:

1. **HttpHandler**: minimal contract taking `ServerHttpRequest` and `ServerHttpResponse`, returning `Mono<Void>` representing processing.
2. **WebHandler API**: higher-level abstraction using `ServerWebExchange` and supporting `WebFilter`, `WebExceptionHandler`, sessions, form data, locale, and principal.

A typical WebFlux processing layout with an annotated controller:

~~~text
HTTP client
    |
    v
Reactor Netty / other HTTP server
    |
    v
server adapter / HttpHandler
    |
    v
HttpWebHandlerAdapter
    |  creates ServerWebExchange and bridges HTTP abstractions
    v
WebExceptionHandler / exception-handling wrapper
    |
    v
WebFilter chain
    |  pre-processing + post-processing, or short-circuit
    v
DispatcherHandler (WebFlux's WebHandler)
    |
    +--> HandlerMapping: finds route/handler
    |
    +--> HandlerAdapter: invokes matching controller or handler
    |
    +--> HandlerResultHandler: turns value into response
    |      JSON, view, ResponseEntity, streaming...
    v
ServerHttpResponse writes status/headers/body
    |
    v
HTTP client
~~~

This diagram illustrates architectural structure, not a guarantee that every component executes synchronously in a rigid sequence. Reactive pipelines can run asynchronously, return `Mono`/`Flux`, switch threads via schedulers, and terminate with different signals.

**DispatcherHandler** is Spring WebFlux's front controller, analogous to `DispatcherServlet` in MVC but built on the reactive `WebHandler` API. The framework also supports functional endpoints via `RouterFunction`/`HandlerFunction`; both styles sit on WebFlux infrastructure.

**WebHttpHandlerBuilder** is the component that assembles a `WebHandler`, `WebFilter`s, `WebExceptionHandler`s, and collaborators into an `HttpHandler` to attach to the HTTP server. In Spring Boot applications, most of this wiring is handled by auto-configuration.

## 3. Lifecycle of a Request From Start to Finish

### Stage 1 — The Server Receives an HTTP Request

The HTTP server reads bytes from a socket. The server adapter converts request metadata and payload into reactive abstractions. Headers, URL, and method are typically available immediately; the body is exposed as an unconsumed data stream.

This does not mean the entire body has been buffered into memory as soon as the server receives the request.

### Stage 2 — Creating the Exchange and Context

WebFlux constructs `ServerWebExchange` from `ServerHttpRequest` and `ServerHttpResponse`, along with collaborators such as `WebSessionManager`, codecs, and locale resolvers.

From here on, filters and handlers for the same request operate on that exchange—for example, placing a trace ID in attributes or adding response headers.

### Stage 3 — Executing the WebFilter Chain

Every **WebFilter** follows the contract:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

A filter can:

- Inspect the request method, path, and headers.
- Attach metadata to exchange attributes.
- Add or update response status or headers before response commit.
- Pass a decorated request or exchange to the next component.
- Call `chain.filter(exchange)` to continue.
- Short-circuit when a response should be returned immediately, such as rejecting a request.

The returned `Mono<Void>` represents **HTTP processing completion**, not a controller body value. It is the contract the framework subscribes to, not an invitation to call `subscribe()` manually.

### Stage 4 — DispatcherHandler Selects Route and Handler

When the request proceeds, `HandlerMapping` finds a handler matching the path, HTTP method, and other mapping conditions.

For annotated controllers, `HandlerAdapter` supplies arguments such as `@PathVariable`, `@RequestParam`, `@RequestBody`, or `ServerWebExchange`, then invokes the controller method.

The method can return a plain object, `Mono<T>`, `Flux<T>`, `ResponseEntity<T>`, `Mono<ResponseEntity<T>>`, or other types supported by WebFlux. `HandlerResultHandler` coordinates with codecs to write the appropriate response.

### Stage 5 — The Reactive Stream Actually Executes

A controller returning `Mono` or `Flux` usually only describes the work. When the framework subscribes, data flows according to Reactive Streams signals and demand.

For example, a controller:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> findOne(@PathVariable long id) {
    return repository.findById(id);
}
~~~

There is no reason to call `block()` to extract `Product` and build a response manually. The controller returns a `Publisher`, and WebFlux coordinates subscription, serialization, and writing the response.

Do not assume that **every** statement in a controller method is lazy: Java code executed directly before creating or returning the `Publisher` runs when the controller method is called. Operations inside `Mono.defer`, `Mono.fromCallable`, `flatMap`, and other `Publisher`s depend on subscription timing.

### Stage 6 — Writing and Committing the Response

Before writing the response, the framework determines status, headers, and matching codecs. `ServerHttpResponse` becomes **committed** when status and headers are applied to begin sending the response; this can happen when starting to write the body or upon completing the response.

Once committed, status and header modifications can no longer be expected to take effect. Streaming bodies can continue sending chunks after headers have already been sent.

### Stage 7 — Termination

Three important termination outcomes:

- **ON_COMPLETE**: the pipeline finished normally and the response completed per contract.
- **ON_ERROR**: the publisher emitted an error; the framework and exception handlers can convert it into an HTTP response if still possible.
- **CANCEL**: the subscriber cancelled, e.g., the client disconnected or a timeout cancelled downstream work.

Do not infer that every `ON_COMPLETE` implies HTTP 200; the status could be 201, 204, 404, or anything else depending on logic and handlers.

## 4. Reading Request Information From the Exchange

**ServerHttpRequest** exposes common properties:

| API | Example | Meaning |
|---|---|---|
| `getMethod()` | `GET` | HTTP method. |
| `getURI()` | Full URI seen by the server | May be affected by proxies. |
| `getPath()` | `RequestPath` | Structured path inspection. |
| `getHeaders()` | `HttpHeaders` | Request headers, possibly multi-valued. |
| `getQueryParams()` | `MultiValueMap` | Parsed query parameters. |
| `getCookies()` | `MultiValueMap` | Cookies sent by the client. |
| `getBody()` | `Flux<DataBuffer>` | Body data stream, not a `String` by default. |
| `getId()` | `String` | Request identifier, useful for logging. |

Example reading metadata in a controller:

~~~java
@GetMapping("/request-info")
public Mono<Map<String, String>> requestInfo(ServerWebExchange exchange) {
    ServerHttpRequest request = exchange.getRequest();

    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getPath().pathWithinApplication().value(),
        "requestId", request.getId()
    ));
}
~~~

This is an illustrative method snippet; to run, place it inside a `@RestController` with appropriate imports in a WebFlux application.

**Do not equate the request body with request metadata.** Query parameters and headers can be read immediately; the body is a `Flux<DataBuffer>` and should only be consumed appropriately through framework contracts.

## 5. Context Data Types: Attributes, Session, Principal, Reactor Context

These names are often mixed up, yet have distinct lifecycles and responsibilities.

| Mechanism | Scope | Purpose |
|---|---|---|
| `exchange.getAttributes()` | One HTTP exchange/request | Shares metadata across `WebFilter`s, handlers, and infrastructure for the same request. |
| `exchange.getSession()` | Web session bound to client/session ID, may span multiple requests | Stores session state if the app uses sessions. |
| `exchange.getPrincipal()` | Resolved identity for the request | Used by code needing identity; may be empty. |
| Reactor `Context` | One subscription / reactive chain | Propagates metadata along a reactive chain independent of `ThreadLocal`. |
| `ThreadLocal` | One Java thread | Should not be relied on as request context in pipelines that can switch threads. |

### Exchange Attributes

The map returned by `getAttributes()` is writable:

~~~java
exchange.getAttributes().put("example.traceId", traceId);
~~~

Later, another component can read it:

~~~java
String traceId = exchange.getAttribute("example.traceId");
~~~

This is a per-request mutable map. Use namespaced keys to avoid colliding with framework or library attributes; avoid holding references to exchanges in global caches or storing unnecessary sensitive data directly.

### WebSession

`getSession()` returns `Mono<WebSession>`. Accessing the session provides a `WebSession` object, yet merely calling `getSession()` **does not automatically** make the server create or persist stateful session storage. Persistence is governed by configuration and whether session state is modified.

Example reading an attribute:

~~~java
Mono<String> cart = exchange.getSession()
    .map(session -> session.getAttributeOrDefault("cartId", "none"));
~~~

If an endpoint is completely stateless, do not create a session solely to pass data between two steps in the same request; exchange attributes or Reactor `Context` are better fits.

### Principal

`getPrincipal()` returns a `Publisher` for the authenticated user; it may be empty. To handle missing identity:

~~~java
Mono<String> userName = exchange.getPrincipal()
    .map(principal -> principal.getName())
    .defaultIfEmpty("anonymous");
~~~

Actual identity and permissions are determined by the security system. Never trust client-supplied headers as proof of authentication unless verified by Spring Security or a trusted boundary.

### Reactor Context

Reactor `Context` follows a subscription, which is useful when a reactive chain switches threads. Exchange attributes are more convenient for `WebHandler` components sharing per-request data. Both mechanisms can cooperate, but they **are not identical**.

Example passing metadata via Reactor `Context`:

~~~java
Mono<String> operation = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("correlationId", "missing"))
).contextWrite(context -> context.put("correlationId", "req-123"));
~~~

When subscribed, the `Mono` above emits `"req-123"`. This is a standalone Reactor `Context` example and does not mean `exchange` is automatically placed in Reactor `Context` in every environment.

## 6. WebFilter: Proper Role and Reactive Execution

`WebFilter` handles cross-cutting HTTP logic across endpoints—for example, logging, trace metadata, headers, or infrastructure concerns. Its contract must stay wired into the chain and never block the event loop with blocking I/O.

### Complete Example: Trace ID in Filter and Controller

Suppose you generate a **Spring Boot 3.x, Java 17+** project with **spring-boot-starter-webflux** via Spring Initializr. In a Spring Boot 4.x project, use the WebFlux starter managed by that version.

Create three Java files in package **com.example.exchange**.

**File ExchangeApplication.java:**

~~~java
package com.example.exchange;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeApplication.class, args);
    }
}
~~~

**File TraceWebFilter.java:**

~~~java
package com.example.exchange;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class TraceWebFilter implements WebFilter {

    public static final String TRACE_KEY = "example.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        exchange.getAttributes().put(TRACE_KEY, traceId);
        exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);

        return chain.filter(exchange);
    }
}
~~~

**File PingController.java:**

~~~java
package com.example.exchange;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Mono<Map<String, String>> ping(ServerWebExchange exchange) {

        String traceId =
            exchange.getAttributeOrDefault(TraceWebFilter.TRACE_KEY, "none");

        return Mono.just(Map.of(
            "message", "pong",
            "traceId", traceId
        ));
    }
}
~~~

Run from a project that has the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Call the API:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Expected result is HTTP 200, an **X-Trace-Id** header, and JSON containing **message: pong** and **traceId**. The UUID changes on every request, so never write tests comparing the UUID to a hard-coded string.

Illustrative response body (UUID will differ on each run):

~~~json
{
  "message": "pong",
  "traceId": "123e4567-e89b-12d3-a456-426614174000"
}
~~~

Takeaways from the example:

1. The filter generates metadata once per HTTP request and stores it in attributes.
2. The controller reads that metadata from the same exchange.
3. The filter sets the response header **before** the chain starts writing the body.
4. The filter returns the chain's `Mono<Void>`; it never calls `subscribe()` or `block()`.
5. Subsequent steps—security, handler mapping, and response writing—remain orchestrated by the framework.

When multiple `WebFilter`s exist, order is determined by Spring ordering mechanisms and filters registered by the framework/application. Do not assume `@Order(0)` alone guarantees running before every Spring Security filter; inspect the actual filter chain if security policies depend on order.

## 7. Filter Short-Circuiting and Completing the Response

A `WebFilter` is not required to forward every request. A filter can reject a request and complete the response right there. Illustrative method example:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String token = exchange.getRequest()
        .getHeaders()
        .getFirst("X-Demo-Token");

    if (!"allow".equals(token)) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

To compile inside a `WebFilter` class, import the corresponding Spring types including **org.springframework.http.HttpStatus**. This only demonstrates short-circuiting flow and is **not** a production authentication mechanism: secrets/tokens should never be checked with hard-coded comparisons, and production systems should use Spring Security or an appropriate security solution.

Key distinctions:

- Returning **chain.filter(exchange)**: passes the request down to remaining filters and handlers.
- Returning **response.setComplete()**: finishes the response without a body in this example branch.
- Returning a `Mono` not subscribed by the framework or manually calling `subscribe()` in the filter: risks leaving requests incomplete or behaving unexpectedly.
- Omitting `chain.filter(exchange)` without intending to short-circuit prevents controllers from ever running.

## 8. Mutating the Exchange When Modifying a Request Before Forwarding

Most applications do not need to modify incoming requests. When you genuinely need to rewrite headers or URLs for infrastructure rules, use the decorator/builder API rather than mutating immutable-like objects directly.

Illustrative snippet inside a `WebFilter`:

~~~java
ServerHttpRequest updatedRequest = exchange.getRequest()
    .mutate()
    .header("X-Internal-Source", "gateway")
    .build();

ServerWebExchange updatedExchange = exchange.mutate()
    .request(updatedRequest)
    .build();

return chain.filter(updatedExchange);
~~~

To compile inside a `WebFilter`, import **org.springframework.http.server.reactive.ServerHttpRequest**. `exchange.mutate().build()` produces a wrapper/decorator providing the modified request to downstream components. Do not assume this retroactively mutates references already held to the original request.

If your only goal is sharing internal metadata, exchange attributes are less intrusive than adding headers, since headers can leak outward or be mistaken for client-supplied data. In particular, never elevate privileges based on a header clients can forge.

To add or rewrite a request body, calling `mutate().header(...)` is **not enough**. The body is a `Flux<DataBuffer>`, requiring a wrapper/decorator and careful buffer/backpressure management.

## 9. Request Body: Single Consumption, Codecs, and DataBuffer Management

`ServerHttpRequest.getBody()` returns **Flux<DataBuffer>**, reflecting streaming request data. Points to watch:

- Do not assume a synchronous JSON `String` of the request body is readily available.
- The request body is a stream; if a filter consumes it, downstream handlers may fail to read the body.
- If a filter must inspect the body and still forward it to a handler, build a proper caching/decorating mechanism, cap size, and manage reference-counted buffers carefully.
- For large request bodies, buffering everything in RAM just for logging is dangerous. Never log passwords, tokens, personal data, or sensitive payloads.
- When decoding JSON, `@RequestBody Mono<MyDto>` or framework codec APIs are far safer and easier to maintain than assembling raw bytes from `Flux<DataBuffer>`.

Example controller reading the body reactively:

~~~java
public record EchoRequest(String message) {
}

@PostMapping("/api/echo")
public Mono<Map<String, String>> echo(
        @RequestBody Mono<EchoRequest> payload) {

    return payload.map(value ->
        Map.of("echo", value.message())
    );
}
~~~

This is an illustrative snippet for a `@RestController`, requiring imports for `@PostMapping`, `@RequestBody`, `Mono`, and `Map`. When valid `application/json` arrives, WebFlux uses the matching message reader/codec to decode it.

### Form and Multipart

`ServerWebExchange` provides `getFormData()` for `application/x-www-form-urlencoded` and `getMultipartData()` for `multipart/form-data`. Both return `Mono` because parsing may perform I/O and consume the request body.

Do not manually subscribe to `getBody()` and expect the framework to decode the same body again without proper caching. Multipart files can be large: choose streaming or temporary storage models and size limits for resource safety.

## 10. Response Status, Headers, Body, and Commit Timing

`ServerHttpResponse` exposes operations such as:

- **setStatusCode(...)**: sets the HTTP status before commit.
- **getHeaders()**: accesses response headers.
- **getCookies()**: configures response cookies via supported APIs.
- **beforeCommit(...)**: registers a reactive callback executed before the response commits.
- **isCommitted()**: checks whether the response has already committed.
- **writeWith(...)**: writes the body from `Publisher<DataBuffer>`.
- **setComplete()**: signals response completion.

A critical rule: **status and headers should only be changed before commit**. Code executing after the response begins transmitting cannot be expected to change HTTP 200 to 500.

### Using beforeCommit for Last-Minute Header Updates

Example inside a `WebFilter`:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.fromRunnable(() -> {
    response.getHeaders().set("X-Processed", "yes");
}));

return chain.filter(exchange);
~~~

Requires importing **org.springframework.http.server.reactive.ServerHttpResponse** and **reactor.core.publisher.Mono**. The registered callback runs as part of response commit, not immediately when the line executes.

Setting headers via `getHeaders().set(...)` before invoking the chain is also valid when you know nothing has committed the response yet. `beforeCommit` fits when you want to run work right before headers are applied, but never put blocking work or long I/O inside `beforeCommit`.

### When Does isCommitted Matter?

If the response has not committed yet, an error handler may still pick another status and body. Once committed, changing status can fail and the framework cannot "retract" bytes already sent. With streaming in particular, errors can occur after body chunks have already been flushed.

Never call `setComplete()` or `writeWith()` manually inside a controller while also returning an object for WebFlux to serialize, unless intentionally building a custom response handler. Mixing both can trigger double writes or response-committed errors.

## 11. WebFilter's `Mono<Void>` and Signal Ordering

A standard `WebFilter` simply wraps the request lifecycle:

~~~java
return chain.filter(exchange)
    .doOnSubscribe(subscription -> logStart())
    .doOnError(error -> logFailure(error))
    .doFinally(signal -> logFinish(signal.name()));
~~~

This is illustrative pseudocode assuming `logStart`, `logFailure`, and `logFinish` methods exist; it shows where hooks attach rather than a standalone runnable program.

**Operators to understand:**

- **doOnSubscribe**: callback on subscription; not a place for blocking I/O.
- **doOnError**: observes errors without handling or replacing them.
- **onErrorResume**: switches to a fallback `Publisher` according to explicit logic.
- **doFinally**: callback when the stream ends via complete, error, or cancellation.
- **then(...)**: runs a follow-up action after the preceding publisher completes normally, common with `Mono<Void>`.
- **timeout(...)**: emits a timeout error after a threshold; handle or map to a response per requirements.

Note: `doFinally` runs when the inner chain publisher terminates, which does not by itself prove the client finished reading the response. Moreover, an outer `WebExceptionHandler` can convert chain errors into a different HTTP response, so logs inside a filter and the final HTTP outcome may diverge.

Also avoid relying on thread identity when reading logs: reactive execution can switch threads across schedulers and I/O callbacks.

## 12. Error Handling in the Request Lifecycle

Errors can arise at multiple layers:

- Request parsing, JSON decoding, or validation.
- `HandlerMapping` finding no matching route or HTTP method.
- Controller/service throwing an exception or returning `Mono.error`.
- Filter emitting an error or terminating the chain early.
- Response codec failing to encode data.
- Network I/O failure while streaming the response.

Spring WebFlux provides several error-handling points:

| Mechanism | Typical scope |
|---|---|
| `@ExceptionHandler` | Handles exceptions for a controller within annotation scope. |
| `@RestControllerAdvice` | Maps controller exceptions to HTTP responses per business logic. |
| `ResponseStatusException` | Expresses an HTTP status when no normal result is available. |
| `WebExceptionHandler` | Handles errors at the `WebHandler` chain level, covering filters/handlers per registration. |
| Spring Boot reactive error handling | Generates default error responses per app configuration. |

Example converting a missing item into 404 when the service finds nothing:

~~~java
@GetMapping("/api/items/{id}")
public Mono<Item> item(@PathVariable long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Item not found"
            )
        ));
}
~~~

This is an illustrative method requiring Spring imports and a real service. The key point is that **`Mono.empty()` is not the same as `Mono.error()`**. HTTP-layer handlers represent empty per contract; if an API must return 404, express it explicitly via status or exception.

**Post-commit errors** are a different case: HTTP headers or partial body chunks have already been sent, so an error handler cannot always replace the response with a standard JSON error. For SSE or NDJSON streaming, design an application-level protocol to emit error events or close the stream appropriately.

Never turn every exception into HTTP 200 just to "avoid errors." HTTP status codes should reflect actual request outcomes.

## 13. Cancellation, Timeouts, and Backpressure

### Cancellation

When a client closes the connection, times out, or a server-side subscriber cancels, the pipeline can receive a cancellation signal. This lets upstream publishers stop remaining work.

However:

- Cancellation does not guarantee already-dispatched external I/O can be recalled.
- Cancellation does not automatically roll back committed transactions or completed side effects.
- A `CANCEL` signal does not always arrive the instant a socket closes across every server and transport.
- Calling `subscribe()` manually inside a filter/controller creates an independent subscription, severing the link to request cancellation.

Therefore, controllers and filters should usually **return the publisher** so WebFlux owns the subscription and manages the lifecycle.

### Backpressure

Reactive Streams lets subscribers regulate how many items they accept via demand. For large streaming payloads, this helps avoid keeping the entire dataset in RAM.

Backpressure does not mean every network hop runs at the same speed or that external sources can always be throttled; buffers, prefetches, and limits still exist.

Situations to watch:

- Calling `collectList()` on a very large or infinite `Flux` can spike memory usage.
- Logging every `DataBuffer` or request body can cause unexpected memory retention.
- Blocking calls on event-loop threads slow down unrelated requests.
- Streaming writes must respect lifecycle and downstream demand.

### Timeouts

Placing a `timeout` on a `Mono`/`Flux` inside a service produces a reactive error signal. Meanwhile, timeouts on reverse proxies or the HTTP server operate at different layers. Align deadlines across client, gateway, server, and downstream services; never assume a single timeout governs the whole request.

## 14. Distinguishing Exchange From Servlet Requests and WebClient

Three concepts frequently confused:

| Environment | Primary objects | Role |
|---|---|---|
| Spring MVC / Servlet | `HttpServletRequest` and `HttpServletResponse` | Servlet API request/response. |
| Spring WebFlux server | `ServerWebExchange` | Reactive request-response context for the server-side `WebHandler` chain. |
| Spring `WebClient` | `ClientRequest`, `ClientResponse`, `ExchangeFilterFunction` | Reactive HTTP client abstractions; not `ServerWebExchange`. |

**WebFilter** belongs to the HTTP server side of WebFlux. **ExchangeFilterFunction** belongs to `WebClient`. Both follow an interception concept, yet their APIs, positions, and lifecycles differ; do not copy code directly from one to the other.

In WebFlux functional endpoints, you usually work with **ServerRequest** and **ServerResponse** rather than touching `ServerWebExchange` in every method. That does not mean the exchange isn't present underneath.

## 15. Testing the Request Lifecycle With WebTestClient

For the app in Section 6, you can verify clear observable behavior:

- `GET /api/ping` succeeds.
- The response includes the `X-Trace-Id` header.
- The JSON contains `message: pong` and `traceId`.
- The `traceId` value matches between the response header and JSON body within the same request.

### Spring Boot Integration Test

Add **spring-boot-starter-test** (test scope) to the project and use the `WebTestClient` auto-configured by Spring Boot test. Example with Spring Boot 3.x:

~~~java
package com.example.exchange;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void pingHasTraceId() {
        EntityExchangeResult<byte[]> result = client.get()
            .uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody()
            .jsonPath("$.message").isEqualTo("pong")
            .jsonPath("$.traceId").exists()
            .returnResult();

        String header = result.getResponseHeaders()
            .getFirst("X-Trace-Id");

        assertThat(header).isNotBlank();
        assertThat(new String(
            result.getResponseBody(), StandardCharsets.UTF_8
        )).contains(header);
    }
}
~~~

This test verifies behavior across the entire HTTP request. JSON serialization of `Map` and UUID runs without the caller ever invoking `block()`. `assertThat` checks that the header UUID appears in the JSON body instead of hard-coding a fixed UUID.

When upgrading to Spring Boot 4.x, test auto-configuration annotation packages may change; use imports matching your target version. If you only want to test a `WebFilter`'s logic, bind `WebTestClient` directly to a controller/router and filter instead of booting the entire HTTP server.

### Testing Errors and Cancellation

Beyond happy paths, add tests for:

- Unmapped route: status 404.
- Wrong HTTP method: status 405 when another method matches the route.
- Invalid JSON request body: client error per codec/validation configuration.
- `WebFilter` short-circuit: controller is never invoked.
- Error emitted after response commits: do not expect the framework to rewrite an already-sent status.
- Streaming client cancellation: upstream receives cancellation when transport permits; design tests for transport realities without assuming exact timing.

## 16. Common Mistakes

| Mistake | Consequence | Correct approach |
|---|---|---|
| Calling `block()` inside a `WebFilter` or controller | Holds an event-loop thread and may violate non-blocking contracts | Compose `Mono`/`Flux` with operators and return `Publisher` to WebFlux. |
| Calling `subscribe()` manually to "execute" a request | Detaches work from HTTP subscription and lifecycle | Return `chain.filter(exchange)` or a `Publisher` per contract. |
| Using exchange attributes as a global cache | Leaks request state across requests | Use only for per-request metadata; never hold exchanges in singleton fields. |
| Assuming `getSession()` implies creating a persistent session | Misunderstandings about state and cookies | Distinguish obtaining `WebSession` from persisting session changes. |
| Reading `getBody()` in a filter and expecting handlers to read it again | Body stream is already consumed, breaking decoding | Build a safe caching/decorating wrapper with size limits. |
| Changing headers/status after response commit | Changes fail to apply as expected | Set before the chain or use `beforeCommit`. |
| Catching all errors and always returning HTTP 200 | Misleads clients about API outcomes | Map errors to appropriate HTTP statuses. |
| Using `ThreadLocal` as durable request context | Data disappears or leaks when switching threads | Use Reactor `Context` or exchange attributes as appropriate. |
| Implementing auth from untrusted headers | Spoofing and bypass risks | Use Spring Security and enforce trust boundaries. |
| Logging full bodies or tokens in filters | Data exposure and memory overhead | Log necessary metadata only; redact sensitive fields. |
| Assuming `CANCEL` always rolls back work | Already-executed side effects may remain | Design idempotency, transactions, and layered cancellation. |
| Equating `WebFilter` with `WebClient` filters | Wrong API and lifecycle | Distinguish server-side `WebFilter` from client-side `ExchangeFilterFunction`. |

## 17. Self-Check Exercises

**1.** Does `ServerWebExchange` represent a TCP connection or a single HTTP exchange?  
**2.** What return type must `WebFilter` return, and why shouldn't you call `subscribe()` manually?  
**3.** A filter wants to pass a correlation ID to a controller: should it use exchange attributes or store it in a singleton field?  
**4.** What type does `getSession()` return, and does calling it always create a persistent session?  
**5.** Is a filter guaranteed to succeed if it changes the status code after the response has committed?  
**6.** Why can reading `request.getBody()` for logging and forwarding the unmodified exchange cause downstream JSON decoding to fail?  
**7.** Which three delegate types does `DispatcherHandler` use to find a handler, invoke it, and produce the response?  
**8.** When a streaming `Flux` has already emitted part of the body and then errors, can the already-sent HTTP status be changed to 500?  
**9.** How do exchange attributes differ from Reactor `Context`?  
**10.** Does `CANCEL` guarantee rolling back a committed database write?

### Suggested Answers

1. A single HTTP exchange/request; the underlying connection may be reused.
2. `Mono<Void>`; Spring WebFlux subscribes and manages completion, error, and cancellation for the request.
3. Use per-request attributes; never store request state in a singleton field.
4. `Mono<WebSession>`; merely accessing the session does not automatically create persistent stateful storage.
5. No; commit prevents modifying status/headers as before sending the response.
6. The body is a reactive stream and may already be consumed; re-reading requires proper caching/decoration.
7. `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
8. Already-sent headers cannot be retracted; handle the error at the streaming protocol level or terminate the stream.
9. Attributes are a per-HTTP-exchange map; Reactor `Context` is attached to a reactive subscription.
10. No; cancellation does not automatically undo already-executed side effects.

## 18. Official References

- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, `WebHandler` API, `WebHttpHandlerBuilder`, `WebFilter`, and `WebExceptionHandler`.
- [Spring Framework — DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): reactive front controller, `HandlerMapping`, `HandlerAdapter`, and result handling.
- [Spring Framework — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): contract, request/response, attributes, session, principal, and `mutate`.
- [Spring Framework — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): filter contract and `Mono<Void>`.
- [Spring Framework — ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): status, headers, and commit.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): mapping, argument binding, and return types.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux HTTP requests and responses.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/index.html): `Mono`, `Flux`, subscription, backpressure, cancellation, and Reactor `Context`.
