# WebFilter, WebExceptionHandler, and Pre- or Post-Handler Processing in Spring WebFlux

## 1. Objectives and Scope

In Spring Boot using Spring WebFlux, handling an HTTP request involves more than just a controller or functional handler. Requests also flow through filters, handler lookup, data conversion, error handling, and response writing. Two extension points at the web-runtime level are especially important: **`WebFilter`**, which wraps request processing, and **`WebExceptionHandler`**, which handles unhandled errors emitted from the WebFlux chain.

After this lesson, you will be able to:

1. Trace a request's path accurately through `HttpHandler`, `WebFilter`, `WebHandler`, and `WebExceptionHandler`.
2. Write pre-handler and post-downstream logic with `WebFilterChain.filter(exchange)`, understanding the difference between *building the pipeline* and *subscribing to the publisher*.
3. Control filter order using `@Order` or `Ordered`, and recognize why pre- and post-processing execution order reverses.
4. Choose `@ExceptionHandler`/`@RestControllerAdvice`, `WebExceptionHandler`, or Spring Security's dedicated mechanisms at the right layer.
5. Handle errors before the response commits without attempting to change HTTP status/headers after data has been sent.
6. Avoid blocking, double subscriptions, double body consumption, or losing request context in reactive pipelines.
7. Run and verify a Java 17+ Spring Boot WebFlux app featuring a filter, handler, error handler, and expected responses.

Examples target **Spring Boot 3.x / Spring Framework 6 / Java 17+** with the `spring-boot-starter-webflux` dependency. Exact API names and registration mechanisms can vary across framework generations; when upgrading Spring Boot, check the target version's documentation.

## 2. Overview of the WebFlux Request Flow

Conceptually, WebFlux's processing flow on a reactive server like Reactor Netty looks like this:

~~~text
HTTP request
   |
Reactor Netty / server adapter
   |
HttpHandler / HttpWebHandlerAdapter
   |
ExceptionHandlingWebHandler -----------------------+
   |                                                |
   v                                                | unhandled error
FilteringWebHandler                                  |
   | WebFilter A (before)                           |
   |   WebFilter B (before)                         |
   |     WebFilterChain.filter(exchange)            |
   |       DispatcherHandler / WebHandler           |
   |         HandlerMapping -> handler/controller   |
   |         HandlerAdapter / HandlerResultHandler  |
   |         write response or emit error ---------+
   |   WebFilter B (completion/error signal)
   | WebFilter A (completion/error signal)
   v
HTTP response (status, headers, body)
~~~

This diagram illustrates processing layers; it does not promise every callback executes once in strict chronological order if errors, cancellation, or async scheduling occur. `WebHttpHandlerBuilder` can assemble `WebFilter`s and `WebExceptionHandler`s from the application context into a web-handler chain. In annotated-controller WebFlux apps, `DispatcherHandler` coordinates `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.

Three interfaces to distinguish:

| Component | Role | Scope |
|---|---|---|
| `WebFilter` | Wraps requests passing through the WebFlux chain: inspects/modifies request/response, logging, correlation, pre-processing policies | Sits outside controller/functional route logic |
| `WebHandler` | Accepts `ServerWebExchange` and returns `Mono<Void>`; core handler is usually framework-managed | Handles requests at the web runtime level |
| `WebExceptionHandler` | Accepts `ServerWebExchange` and an unhandled `Throwable` to build an error HTTP response or propagate the error | Wraps the processing chain; sees errors from filters/handlers unless swallowed |

**Do not confuse WebFlux `WebFilter` with Servlet `Filter` or Spring MVC `HandlerInterceptor`.** They belong to different runtime models. `WebFilter` operates on `ServerWebExchange` and returns a reactive publisher; Servlet filters use `HttpServletRequest`/`HttpServletResponse` with a blocking-style `FilterChain`.

## 3. Contract of WebFilter and WebFilterChain

The WebFlux interface looks like:

~~~java
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}
~~~

Two key parameters:

- `ServerWebExchange` holds the request, response, attributes, and request-associated metadata. From it you can inspect method, path, headers, mutate the response, or share data with downstream steps.
- `WebFilterChain` represents the rest of the chain. `chain.filter(exchange)` returns a `Mono<Void>` describing downstream processing—it is **not** a Java statement that "blocks and waits until the controller finishes."

A filter typically performs light setup and **returns** the downstream publisher, optionally attaching operators to observe termination:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    exchange.getResponse().getHeaders().set("X-Trace", "example");

    return chain.filter(exchange)
            .doOnError(error -> logger.warn("Web request failed", error))
            .doFinally(signal -> logger.debug("Request terminated: {}", signal));
}
~~~

This is a class fragment assuming a logger and imports; it is not a standalone Java program. `doFinally` can receive `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. It works well for lightweight metrics or cleanup, **not** as a safe place to add mandatory headers after the response has already completed.

### 3.1. Registering Filters

You can annotate a class implementing `WebFilter` with `@Component`, or declare a `@Bean WebFilter` inside `@Configuration`. Spring WebFlux collects filters when assembling the web handler. A registered filter can apply to both annotated controllers and functional endpoints within the same WebFlux application.

Do not use a Servlet-style `FilterRegistrationBean` to register a `WebFilter` in a Reactor Netty app. If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot defaults to Servlet MVC unless you explicitly select the web application type; verify the active runtime before debugging why a filter "isn't running."

## 4. Before Handler, After Handler, and Reactive Subscription

The easiest mistake to make is treating "run after" as Java statements placed after `chain.filter(exchange)`. Example:

~~~java
Mono<Void> downstream = chain.filter(exchange);
log.info("After calling chain.filter");
return downstream;
~~~

That log line executes when the filter method assembles the publisher, **with no guarantee the handler has finished**. To execute work after downstream completes, attach operators to the publisher's signals.

### 4.1. Pre-Processing Before Downstream

Appropriate tasks:

- Inspecting request method, path, headers, correlation ID.
- Storing simple data in `exchange.getAttributes()` for downstream consumption.
- Preparing response headers before body writing begins.
- Rejecting a request early based on simple criteria already available before the handler.
- Starting timers or metric contexts, avoiding blocking I/O in the filter.

Illustrative example:

~~~java
exchange.getAttributes().put("requestStartNanos", System.nanoTime());
exchange.getResponse().getHeaders().set("X-Request-Category", "api");
return chain.filter(exchange);
~~~

Store per-request data in exchange attributes. Never put request-scoped mutable state in singleton fields on the filter bean.

### 4.2. Post-Processing When Downstream Completes

When you only want to run an action after downstream completes successfully:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                metrics.recordCompleted(exchange.getRequest().getPath().value())));
~~~

This fragment assumes `metrics` is available in the bean. `then` runs the action only when downstream **completes normally**; if an error occurs, the error publisher propagates and the post-`then` action does not run. To record success, error, and cancellation alike, consider `doFinally`, keeping callbacks short and non-blocking.

To build a fresh publisher *per subscription*, wrap side-effecting logic in `Mono.defer(() -> { ... })`. Normally WebFlux subscribes once per request; avoid calling `subscribe()` from a filter, as it forks an independent stream and cuts error, cancellation, and backpressure propagation from the main response pipeline.

### 4.3. Before-and-After Execution Order

Suppose filter A wraps filter B, and both use `chain.filter` and `doFinally`:

~~~text
A - pre-processing
  B - pre-processing
    handler / response write
  B - termination signal
A - termination signal
~~~

This is a nested onion model. When errors or cancellations occur, registered operators can receive different signals. Do not assume a `then` post-processing step runs on every outcome.

## 5. Ordering WebFilters With @Order and Ordered

`WebFilter` beans are sorted by order. Spring's standard rule is that **lower order values run earlier on the inbound path**:

~~~java
@Component
@Order(-100)
class FirstFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
~~~

This fragment needs imports for `@Component`, `@Order`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, and `Mono`. If filter X has `@Order(-100)` and filter Y has `@Order(100)`, X generally receives the request before Y. On nested post-processing callbacks, Y typically sees completion before X.

Alternatively, implement the `Ordered` interface and return the order from `getOrder()` instead of using `@Order`. **Do not rely on bean declaration order in source files** or give two filters the same order when strict ordering matters; assign explicit orders and write tests.

### 5.1. Filters Can Short-Circuit Downstream

If a filter returns a `Mono<Void>` that handles the request directly without calling `chain.filter(exchange)`, downstream handlers will not run:

~~~java
if ("/maintenance".equals(exchange.getRequest().getPath().value())) {
    exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
~~~

This intentionally blocks the request. Ensure the filter produces a valid response and does not accidentally block unintended routes. Do not call `chain.filter` after already returning an early completion response.

## 6. WebExceptionHandler and How Errors Propagate Through the Pipeline

The interface:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

When the inner chain emits an unhandled error signal, the exception-handling layer tries registered `WebExceptionHandler`s in order. A handler has two main options:

- **Handled:** set status/headers, write a body if appropriate, and return a **successfully completing** publisher.
- **Not handled:** return `Mono.error(ex)` to pass the error to the next handler or the runtime.

Minimal example:

~~~java
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    if (!(ex instanceof MissingApiKeyException)) {
        return Mono.error(ex);
    }

    ServerHttpResponse response = exchange.getResponse();
    if (response.isCommitted()) {
        return Mono.error(ex);
    }

    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    return response.setComplete();
}
~~~

This fragment requires the exception class and imports. It demonstrates checking both **exception type** and **response commit state** before changing status. In authenticated APIs, 401 also involves proper challenge headers; do not use this fragment as a direct replacement for Spring Security.

### 6.1. Where Do Errors Come From?

`WebExceptionHandler` can receive:

- Errors emitted via `Mono.error` from a `WebFilter` before any handler runs.
- Errors from handler resolution, request mapping, or WebFlux internals not resolved at a narrower layer.
- Errors from controllers/functional handlers and downstream reactive stages if not already handled by `@ExceptionHandler` or operators.
- Errors during response processing, though this **does not guarantee** status/body can still be changed if the response already committed.

If a filter uses `onErrorResume` to turn a downstream error into a normal completion, that error will **no longer reach** `WebExceptionHandler`. Similarly, an error in an annotated controller handled by `@ExceptionHandler` normally does not reach the global exception handler.

### 6.2. WebExceptionHandler Ordering

`WebExceptionHandler`s are sorted by order. An application handler intended to run before Spring Boot's default error handler should have an earlier (lower) order and only handle **exceptions it owns**.

In Spring Boot 3.x, `DefaultErrorWebExceptionHandler` is typically registered at order `-1`. Thus an example custom `WebExceptionHandler` with `@Order(-2)` is tried beforehand. This applies to Boot 3.x; when upgrading versions, verify the actual order of registered handlers.

Never create a `WebExceptionHandler` that catches every `Throwable` and always returns 200 or 400. Doing so hides bugs and infrastructure failures and violates HTTP semantics. Propagate out-of-scope exceptions.

## 7. Comparing WebExceptionHandler, @ExceptionHandler, and onErrorResume

| Approach | Best suited scope | Key limitation |
|---|---|---|
| `@ExceptionHandler` in a controller | Controller errors and framework-supported handler invocation | Not a global mechanism for pre-routing errors in filters |
| `@RestControllerAdvice` | Standardizing annotated controller errors across classes | Does not replace `WebExceptionHandler` for non-controller errors |
| `WebExceptionHandler` | Unhandled errors from the WebFlux chain, including filters and handlers | Cannot rewrite status/headers after response commit |
| `onErrorResume` in reactive pipelines | Recovering from specific errors where business context exists | Can catch too broadly or mask downstream failures |
| `WebFilter` returning early response | Responding before the handler, e.g., simple gatekeeping checks | Must avoid calling `chain` or double-writing responses |
| Spring Security reactive entry point / denied handler | 401/403 from authentication and authorization | Should follow the security chain's contracts |

### 7.1. Careful With onErrorResume in WebFilter

Example:

~~~java
return chain.filter(exchange)
        .onErrorResume(MyDomainException.class, error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(HttpStatus.CONFLICT);
            return exchange.getResponse().setComplete();
        });
~~~

This fragment is conceptually valid, yet notice the filter just took over error handling for **all of downstream**. If every filter calls `onErrorResume(Throwable.class, ...)`, official error handlers lose visibility and responses become inconsistent. For annotated-controller business errors, keep `@ExceptionHandler` near the controller or use a deliberate advice class.

### 7.2. Do Errors From WebFilter Reach `@RestControllerAdvice`?

Usually **no**. An error raised before reaching an annotated controller—such as inside a `WebFilter`—is outside controller exception handling. Use `WebExceptionHandler` or handle it at the filter/security layer as appropriate.

Conversely, exceptions thrown inside a controller or emitted by its returned publisher can be handled by `@ExceptionHandler` while a response can still be created. Late failures after response writing starts require another strategy.

## 8. ServerHttpResponse Commit Point and beforeCommit

`ServerHttpResponse` in WebFlux tracks commit state. Once headers and status have been flushed down to the HTTP layer, they cannot be rolled back.

Common methods:

- `response.setStatusCode(HttpStatus.BAD_REQUEST)`: requests setting the status code, succeeding if uncommitted.
- `response.getHeaders().set(...)`: prepares headers on an uncommitted response.
- `response.writeWith(Publisher<DataBuffer>)`: writes the body asynchronously and can trigger commit.
- `response.setComplete()`: signals response completion, triggering commit if not already committed.
- `response.isCommitted()`: checks commit state; useful during exception handling.
- `response.beforeCommit(Supplier<? extends Mono<Void>> action)`: registers an async action to execute right before commit.

Example inside a filter:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders().set("X-Response-Ready", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
~~~

`beforeCommit` is useful when setting headers based on final state known right before commit. **Register the callback early** and return a `Mono<Void>` that accurately reflects the work; never call `subscribe()` manually inside the callback.

Do not try to add headers in `doFinally` or `then` after the body has been written. `then` after `chain.filter(exchange)` is not a "pre-commit response modifier." If you need to change status on error, handle it before sending the response; once `isCommitted()` is `true`, propagating/logging and closing the connection are typically the only remaining options.

### 8.1. Mid-Stream Errors

An SSE or large file response may already have sent `200 OK` and initial chunks when a publisher errors. At that point, you cannot switch to `500` and send a fresh Problem Details JSON body. You can emit an application-protocol error signal **if the stream can still write and the protocol supports it**, or terminate the stream, log, and clean up resources.

Seeing `response.isCommitted()` return `false` at moment A does not guarantee it remains uncommitted at moment B. Do not rely on checking `isCommitted()` before a slow async operation to prevent races; design error handling before body writing starts.

## 9. Runnable Java 17+ Example on Spring Boot WebFlux

This example demonstrates three requests:

1. `GET /ok`: filter prepares headers, handler returns normal content.
2. `GET /blocked`: filter emits an error before the handler; `WebExceptionHandler` converts it to status 403.
3. `GET /handler-error`: controller emits an error; `@RestControllerAdvice` returns status 422.

### 9.1. Create the Project

Use Java 17+ and Maven. Create `pom.xml` in the project directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not add `spring-boot-starter-web` because the goal is running with the WebFlux reactive server.

Create `src/main/java/example/webflux/WebFluxChainDemoApplication.java`:

~~~java
package example.webflux;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxChainDemoApplication.class, args);
    }
}

class FilterDeniedException extends RuntimeException {
    FilterDeniedException() {
        super("blocked at filter");
    }
}

class HandlerRuleException extends RuntimeException {
    HandlerRuleException() {
        super("handler rule");
    }
}

@Component
@Order(-100)
class TraceAndGateFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        exchange.getResponse().getHeaders().set("X-Filter", "entered");
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set("X-Commit", "ready");
            return Mono.empty();
        });

        String path = exchange.getRequest().getPath().pathWithinApplication().value();
        if ("/blocked".equals(path)) {
            return Mono.error(new FilterDeniedException());
        }

        return chain.filter(exchange);
    }
}

@Component
@Order(-2)
class FilterExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (!(ex instanceof FilterDeniedException)) {
            return Mono.error(ex);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(ex);
        }

        response.setStatusCode(HttpStatus.FORBIDDEN);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
        byte[] bytes = "blocked at filter\n".getBytes(StandardCharsets.UTF_8);
        DataBuffer body = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(body));
    }
}

@RestController
class ApiController {

    @GetMapping(path = "/ok", produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> ok() {
        return Mono.just("ok");
    }

    @GetMapping("/handler-error")
    Mono<String> fail() {
        return Mono.error(new HandlerRuleException());
    }
}

@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(HandlerRuleException.class)
    ResponseEntity<Map<String, String>> handle(HandlerRuleException ex) {
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

All classes sit in a single file with one `public` class matching the filename; the remaining classes have package-private visibility and fall within `@SpringBootApplication` component scanning.

### 9.2. Run and Verify

Requires JDK 17+, Maven, and port 8080 free:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/ok
curl -i http://localhost:8080/blocked
curl -i http://localhost:8080/handler-error
~~~

Key expected outcomes (header order, `Date`, `Content-Length`, and `Transfer-Encoding` vary by runtime):

| Request | Expected status | Key headers | Body |
|---|---:|---|---|
| `GET /ok` | 200 | `X-Filter: entered`, `X-Commit: ready` | `ok` |
| `GET /blocked` | 403 | `X-Filter: entered`, `X-Commit: ready` | `blocked at filter` with newline |
| `GET /handler-error` | 422 | `X-Filter: entered`, `X-Commit: ready` | JSON `{"error":"handler rule"}` |

Observations from the example:

- `TraceAndGateFilter` runs before the handler and registers a `beforeCommit` callback.
- For `/blocked`, the filter returns `Mono.error` **without calling** `chain.filter`; the controller never executes. Custom `FilterExceptionHandler` catches the error and writes 403 plain text.
- For `/handler-error`, the error is emitted from the controller's returned publisher. `@RestControllerAdvice` produces the 422 JSON response; custom `WebExceptionHandler` only sees errors still propagating to its layer and does not overwrite the 422.
- `X-Commit` is applied by the pre-commit callback rather than too late after the response finishes.
- Removing `@Order(-2)` or giving a catch-all error handler a late order can cause the default error handler to run first; always check actual ordering.

This example intentionally checks only the specific `FilterDeniedException`. In systems with authentication, 401/403 handling should use Spring Security hooks such as `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`.

## 10. Testing With WebTestClient

API tests should verify not just status codes, but also distinguish filter-handled errors from controller-advice errors.

For the example project, add the test dependency to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The following example assumes **a test class with `WebTestClient client` injected and configured via Spring Boot test**; it is not a standalone test class:

~~~java
client.get().uri("/ok").exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Filter", "entered")
        .expectHeader().valueEquals("X-Commit", "ready")
        .expectBody(String.class).isEqualTo("ok");

client.get().uri("/blocked").exchange()
        .expectStatus().isForbidden()
        .expectHeader().valueEquals("X-Filter", "entered")
        .expectBody(String.class).isEqualTo("blocked at filter\n");

client.get().uri("/handler-error").exchange()
        .expectStatus().isEqualTo(422)
        .expectBody()
        .jsonPath("$.error").isEqualTo("handler rule");
~~~

You can use `@SpringBootTest(webEnvironment = RANDOM_PORT)` combined with `@AutoConfigureWebTestClient` per your Spring Boot test setup to run against the live application. `WebTestClient` tests reactive APIs without manually subscribing to publishers.

Practical test cases to add:

1. Error in a filter *before* the handler: verify the controller is not called and the right error handler responds.
2. Error inside the controller: verify `@RestControllerAdvice` handles it without being masked by global error handlers.
3. Two filters with different orders: verify headers, attributes, and callbacks run in expected order.
4. Filter calling `setComplete()` to block a request: verify no unexpected response body is emitted.
5. Error after streaming has emitted part of the body: verify code does not attempt to set a new status.
6. Cancellation/timeouts and cleanup, verifying no blocking calls stall the event loop.
7. Filter inspecting body compatibility with downstream controllers, if body reading is genuinely needed.

## 11. Placing Logic at the Right Layer: Decision Table

| Requirement | Start at | Explanation |
|---|---|---|
| Attach correlation ID or common header | `WebFilter` + `beforeCommit` when needed | Runs before handler; sets header prior to commit |
| Validate a common request header across all routes | `WebFilter` | Can reject early; returns matching publisher |
| Handle errors within an annotated controller | `@ExceptionHandler` | Close to business context, easy error mapping |
| Standardize controller errors across controllers | `@RestControllerAdvice` | Reuses annotation-based error policies |
| Unhandled errors from filters/routing | `WebExceptionHandler` | Covers the WebFlux layer outside handlers |
| 401/403 from authentication/authorization | Spring Security reactive entry point / denied handler | Preserves security chain contracts and ordering |
| Specific policy on a functional route | `HandlerFilterFunction` | Applies only to the wrapped router functions |
| Error from a specific outbound API call | `onErrorResume` near the client/service | Has context to distinguish timeout, 404, and fallback |
| Change status/headers after body streams | Redesign data emission point | Post-commit status/headers cannot be altered |

`HandlerFilterFunction` is a filter for functional routing, distinct from `WebFilter` which applies at the web application level. Do not use a global `WebExceptionHandler` for every business error when a targeted advice or handler expresses the contract more clearly.

## 12. WebFilter Pitfalls in Production Applications

### 12.1. Blocking on the Event Loop

Never call synchronous JDBC/JPA, `Thread.sleep`, `Future.get`, or `WebClient.block()` directly inside a filter. Filters sit on the hot path of every request; a single blocking call increases latency and can stall the Reactor Netty event loop.

When forced to invoke a legacy synchronous library, isolate it carefully:

~~~java
return Mono.fromCallable(() -> legacyVerifier.verify(exchange))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(allowed -> allowed
                ? chain.filter(exchange)
                : exchange.getResponse().setComplete());
~~~

This fragment requires a `legacyVerifier` bean and an appropriate rejection status policy. `boundedElastic` only moves where blocking runs to a bounded scheduler; it does not make the library non-blocking and still needs timeouts, concurrency limits, and thread/connection pool monitoring.

### 12.2. Reading the Body Twice

The request body in WebFlux is typically a single-consumption `Flux<DataBuffer>` stream. If a filter subscribes and reads the body first, downstream controllers may see an empty body or fail. Caching/replaying the body requires handling `DataBuffer`s, reference counting, and release properly; mistakes cause memory leaks or OOMs.

If you only need metadata validation, prefer headers, path, or query parameters. When body inspection/transformation is mandatory, use a well-tested caching/decorating wrapper with size limits and avoid detached subscriptions. Never store whole bodies in singleton filter fields.

### 12.3. Context and Tracing

Reactive chains can switch threads. Traditional `ThreadLocal` or MDC does not follow a logical request across every scheduler automatically. Use `exchange.getAttributes()` for simple request-scoped data and Reactor `Context` or compatible context-propagation mechanisms for tracing and security context per your application's libraries.

Never log tokens, cookies, `Authorization` headers, or sensitive content. For tracing, logging request ID, method, route, duration, and status after processing is enough to diagnose most issues.

### 12.4. Error Handler Writing the Response Twice

If a filter calls `response.writeWith(...)` or `response.setComplete()` and also propagates an error, another error handler may try to write another body or alter the status. Ensure each request has a single response owner, propagate only unhandled errors, and check `isCommitted()`.

Never allocate a `DataBuffer` and abandon it, especially with Netty pooled buffers. When working with body `Flux`es, follow framework or API release contracts.

### 12.5. Errors Outside the Reactive Publisher

If a filter calls `subscribe()` manually to launch a secondary task without tying that publisher into the returned `Mono<Void>`, errors in that task may never reach the request's `WebExceptionHandler`. Similarly, background work detached after the response completes leaves the request-response pipeline and needs separate error handling, retries, observability, and lifecycle management.

## 13. Debugging by Failure Location

When seeing unexpected responses, classify by asking:

1. **Did the filter run?** Verify the runtime is WebFlux, the bean is registered, and check its order and path checks. Use `WebTestClient` to check filter-added headers.
2. **Did the handler run?** Check whether a filter returned an early response or `Mono.error` without calling `chain.filter`. Check `HandlerMapping` and routes.
3. **Did code "after `chain.filter`" run too early?** Inspect operators; Java statements executed during publisher assembly do not wait for completion signals.
4. **Did filter errors skip `@RestControllerAdvice`?** That is a scope difference; inspect `WebExceptionHandler` or filter-level handling.
5. **Was `WebExceptionHandler` never invoked?** The error may already have been handled by `onErrorResume` or `@ExceptionHandler`, or a default error handler had higher precedence.
6. **Did the error handler fail to change the status?** The response may have already committed. Identify the first body or SSE write/flush.
7. **Is HTTP 200 returned with an empty body?** Check whether a publisher swallowed an error into `Mono.empty()`, a filter completed early, or body conversion failed.
8. **Does the client get a generic 500 despite a custom handler?** Check exception type, handler order, whether the handler re-emitted `Mono.error`, and Boot's default error response config.
9. **Do errors only appear under high load?** Check for blocking code, connection pool exhaustion, scheduler queues, cancellation, and manual subscriptions.
10. **Is the body missing after a filter?** Check for single-consumption of the request body and caching/decorating logic.

Use logs tagged with correlation IDs, trace spans, metrics, and small `WebTestClient` cases to validate hypotheses; do not reason solely from log line ordering across different threads.

## 14. Common Design Mistakes

1. **Confusing `WebFilter` with Servlet `Filter`:** APIs, configuration, and runtimes differ.
2. **Assuming code after `chain.filter(exchange)` runs after the handler:** false for lazy publishers.
3. **Setting mandatory headers in `doFinally`:** often too late because the response has already committed.
4. **Using identical `@Order` and relying on accidental ordering:** unstable across refactors and runtime changes.
5. **Swallowing all errors with `onErrorResume(Throwable.class, ...)`:** hides bugs and breaks HTTP contracts.
6. **Using `WebExceptionHandler` for all controller errors:** loses controller context and bypasses business advice.
7. **Calling `subscribe()` inside a filter:** detaches work from the request pipeline, breaking error/cancellation propagation.
8. **Blocking the event loop with JDBC or `block()`:** degrades throughput for unrelated requests.
9. **Reading the body without replaying it for the handler:** leaves downstream with an empty body or error.
10. **Attempting to change status after streaming starts:** committed status/headers cannot be undone.
11. **Storing mutable request state in singleton filter fields:** risks cross-request data leaks.
12. **Customizing 401/403 outside Spring Security:** risks missing challenges or broken authorization rules.
13. **Forgetting the difference between pre-handler errors and controller errors:** picks the wrong layer and skews tests.
14. **Ignoring `CANCEL` signals:** causes leaked resources and inaccurate metrics when clients disconnect.

## 15. Pre-Deployment Checklist

- [ ] Verified the application runs on the WebFlux reactive runtime with proper `WebFilter` beans.
- [ ] Key filters have explicit orders and order-verified tests.
- [ ] Pre-handler logic runs before `chain.filter` or inside an appropriate deferred block.
- [ ] Post-processing uses publisher signals like `then`, `doOnError`, `doFinally` rather than Java statement order.
- [ ] No manual `subscribe()` or `block()` inside filters.
- [ ] No request-body consumption without tested caching/replay/release logic.
- [ ] Controller errors handled by `@ExceptionHandler`/`@RestControllerAdvice` where context fits.
- [ ] Unhandled pre-handler errors have an appropriate `WebExceptionHandler` ordered ahead of the default handler if needed.
- [ ] Error handlers match only their target error types and propagate others.
- [ ] No attempts to alter status/headers post-commit; `isCommitted()` checked and `beforeCommit` used where needed.
- [ ] Spring Security retains responsibility for authentication/authorization and 401/403.
- [ ] Tests cover `/ok`, `/blocked`, controller errors, streaming errors, cancellation, and concurrency.
- [ ] Logging/tracing carries correlation IDs without exposing tokens or blocking the event loop.

## 16. Key Takeaways

**`WebFilter` wraps handlers and delegates via `WebFilterChain`; `WebExceptionHandler` catches unhandled errors at the WebFlux layer.** To run logic *before* the handler, execute or set up data when the filter receives the request. To run logic *after* the handler, attach to reactive signals on the publisher returned by the chain. Controller advice handles errors within controller scope, while errors from filters or routing may need `WebExceptionHandler`. Every branch must respect HTTP response commit timing, avoid blocking, and keep errors and cancellation inside the same reactive chain.

## References

- Spring Framework, WebFlux Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework, WebFlux Exceptions: https://docs.spring.io/spring-framework/reference/web/webflux/ann-controller/ann-exceptions.html
- Spring Framework, WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework API, WebExceptionHandler: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework API, ServerHttpResponse: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Boot, Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
