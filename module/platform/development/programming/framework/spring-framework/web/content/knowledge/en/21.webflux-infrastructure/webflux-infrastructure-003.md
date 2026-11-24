# WebFilter, WebFilterChain, and WebExceptionHandler in Spring WebFlux

## 1. Learning objectives

A WebFlux application can serve HTTP via annotated `@RestController`s or functional `RouterFunction`s. Before reaching an endpoint, requests often need authentication/authorization, correlation IDs, safe logging, CORS, tracing, and rate limiting; afterward, they may need standardized error handling and resource cleanup. Spring provides these infrastructure components:

- **`WebFilter`**: intercepts **before, around, and after** request handling at the WebFlux layer. It receives a `ServerWebExchange` and a `WebFilterChain`, returning `Mono<Void>`.
- **`WebFilterChain`**: represents the **remainder** of the pipeline, consisting of subsequent WebFilters and the target `WebHandler`. Call `chain.filter(exchange)` to proceed.
- **`WebExceptionHandler`**: handles error signals from the WebFilter chain or target WebHandler when an error was not handled internally, typically by writing HTTP status/body if the response is not yet committed.

All belong to **Spring WebFlux**, not Spring MVC's Servlet `Filter`. They operate at the `org.springframework.web.server` layer, beneath annotated/functional routing. This article uses **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, and Reactor `Mono`/`Flux`.

After this article, you will be able to:
1. Diagram the ordering and responsibilities of `HttpHandler`, `WebHandler`, filters, exception handlers, and `DispatcherHandler`.
2. Write filters that invoke the chain **exactly once**, implementing "before", "after", "finally", and short-circuit logic.
3. Distinguish errors handled by `@ExceptionHandler` from errors reaching `WebExceptionHandler`.
4. Understand `@Order`, reactive signals (complete/error/cancel), response commit, and limits on modifying status/body.
5. Use `ServerWebExchange` to pass request-scoped attributes and mutate request/response before commit.
6. Avoid manual `block()`/`subscribe()`, double-consuming request bodies, and leaking sensitive data.
7. Build a runnable Spring Boot WebFlux app with two filters, a custom exception handler, a controller, and WebTestClient tests.
8. Test a low-level chain using `WebHttpHandlerBuilder` and mock HTTP objects.
9. Choose appropriate places for Spring Security, CORS, observability, backpressure, and exception policies.

## 2. Map of WebFlux infrastructure

WebFlux defines two HTTP-handling abstraction levels:

- `HttpHandler.handle(ServerHttpRequest, ServerHttpResponse) -> Mono<Void>`: minimal interface between Spring and HTTP server adapters.
- `WebHandler.handle(ServerWebExchange) -> Mono<Void>`: web layer receiving an **exchange** containing request/response and related services.

`WebHttpHandlerBuilder` assembles a target `WebHandler` with WebFilters and WebExceptionHandlers, then uses `HttpWebHandlerAdapter` to produce an `HttpHandler` that can attach to a server.

```text
HTTP Client
   |
   v
Reactor Netty / supported reactive server adapter
   |
   v
HttpHandler
   |
   v
HttpWebHandlerAdapter
   |  creates ServerWebExchange
   v
WebExceptionHandler chain (outer layer)
   |
   +--> WebFilter A
         |
         +--> WebFilter B
                |
                +--> target WebHandler
                       |
                       +--> DispatcherHandler (commonly used)
                              |
                              +--> HandlerMapping
                              +--> HandlerAdapter
                              +--> HandlerResultHandler
   |
   v
Mono<Void> completion/error/cancellation
   |
   v
ServerHttpResponse commit/write
```

The boxes do **not** correspond to separate threads. The reactive pipeline executes when the HTTP runtime subscribes; callback order can be affected by `flatMap`, `publishOn`, `subscribeOn`, and async I/O.

In a typical Spring Boot WebFlux app, the target WebHandler is `DispatcherHandler`. It uses HandlerMapping/HandlerAdapter/HandlerResultHandler for both annotated controllers and WebFlux.fn endpoints. **There is no need to manually create HttpHandler/WebHttpHandlerBuilder in a regular REST app**; Boot/WebFlux auto-configuration does this for you.

## 3. What is WebFilter?

Package and interface:

```java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange,
                      WebFilterChain chain);
}
```

This is an **illustrative signature** of the API, not a file you define yourself.

- `exchange` represents **one HTTP request/response exchange**, providing `getRequest()`, `getResponse()`, `getAttributes()`, `getSession()`, `getPrincipal()`, etc.
- `chain` is the rest of the pipeline. If a filter does not call the chain, the target handler will **not run automatically**.
- `Mono<Void>` signals completion/error/cancel for the entire exchange. It is not a response DTO; the HTTP body is normally written downstream via `ServerHttpResponse`.
- A WebFilter can run for both annotated `@RestController` and WebFlux.fn routes sitting under the application's WebHandler.

### Minimal filter

```java
@Component
public class RequestMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        exchange.getAttributes().put("example.marker", "created");
        return chain.filter(exchange);
    }
}
```

This is a snippet for a Spring WebFlux project requiring imports `Component`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, and `Mono`. When Boot scans `@Component`, it registers the filter bean and the WebFlux builder can add it to the chain.

### A WebFilter is not a Servlet Filter

| Comparison | WebFlux `WebFilter` | Servlet `Filter` |
| --- | --- | --- |
| Package | `org.springframework.web.server` | `jakarta.servlet` |
| API | `Mono<Void> filter(ServerWebExchange, WebFilterChain)` | `void doFilter(ServletRequest, ServletResponse, FilterChain)` |
| Request context | `ServerWebExchange` | `ServletRequest/HttpServletRequest` |
| Chain delegation | `return chain.filter(exchange)` | `chain.doFilter(request,response)` |
| Completion | Reactive signals | Synchronous/async Servlet lifecycle |
| Framework | Spring WebFlux | Servlet/MVC |
| I/O | Reactive streams, usable with non-blocking server adapters | Servlet I/O; separate Servlet async/non-blocking APIs |

**Do not rely solely on the name "Filter".** WebFlux running on Netty does not necessarily have an `HttpServletRequest`, so Servlet filter code is not portable to WebFlux.

## 4. WebFilterChain coordinates the next step

`WebFilterChain` has a single core responsibility:

```java
public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
```

**Invoke once, return the result**:

```java
return chain.filter(exchange);
```

Each filter can choose to:
- **Continue**: `return chain.filter(exchange)`.
- **Block**: set status and `return exchange.getResponse().setComplete()`.
- **Transform**: create an exchange wrapper with `exchange.mutate()`, then pass the wrapper to the chain.
- **Wrap**: attach `doOnError`, `doOnSuccess`, `doFinally`, `onErrorResume`, or `contextWrite` to the Mono returned by the chain.

### What happens when the chain is not called?

```java
if (tooManyRequests(exchange)) {
    exchange.getResponse()
            .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
```

This is a snippet where `tooManyRequests` is a server-side policy. The first branch **short-circuits** the pipeline and skips the controller. Make sure a filter does not simply return `Mono.empty()` while forgetting to set status/body, otherwise the response might accidentally be an empty 200.

### Do not invoke the chain twice

```java
// WRONG: manual subscribe runs the pipeline outside the server-managed lifecycle.
chain.filter(exchange).subscribe();
return chain.filter(exchange);
```

Consequences can include:
- Target handler executes twice, causing duplicate side effects.
- Two subscriptions race to read the HTTP body (usually one-shot).
- Two writers race to write status/body.
- Request cancellation, security context, tracing, and error handling are no longer tied to a single unified subscription.

**Never call `subscribe()` or `block()` inside a WebFilter just to "force" the chain to run.** The server runtime subscribes to the outer Publisher.

## 5. Before, after, errors, and cancellation in Reactor

A WebFilter can run logic **before** `chain.filter` and attach operators to the downstream result.

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    long startedAt = System.nanoTime();
    String route = exchange.getRequest().getPath().value();

    return chain.filter(exchange)
            .doOnError(error ->
                    log.error("Request failed: {}", route, error))
            .doFinally(signalType -> {
                long elapsedNanos =
                        System.nanoTime() - startedAt;
                metrics.record(route, elapsedNanos, signalType);
            });
}
```

This is a **snippet** requiring application-defined `log`/`metrics`. Do not use raw request paths containing PII/secrets as metric tags in production; prefer route templates/low cardinality, and never log raw queries/tokens.

### Understanding the operators properly

| Operator | When triggered | Remember |
| --- | --- | --- |
| `doOnSubscribe` | When the subscriber starts | Does not necessarily run at Mono assembly time |
| `doOnSuccess` | Mono completes successfully; for Void, value is null | Does not mean HTTP status is 2xx |
| `doOnError` | Mono emits an error | Observes, **does not swallow the error** |
| `doFinally` | After termination/cancellation | Sees `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` |
| `onErrorResume` | When an error is emitted | Can replace the error with another Publisher |
| `contextWrite` | Enriches Reactor Context | Subscription context, not exchange attributes |
| `then(...)` | Waits for upstream completion then runs downstream | Requires understanding commit/response-write timing |

**HTTP status is metadata, not a Reactor error signal.** A handler can return HTTP 404 via `ServerResponse.notFound()` and the Publisher still completes normally; `doOnError` will **not** run. Conversely, an error can occur after a 200 body has committed; the HTTP status may not be changeable. Therefore, counting HTTP 4xx/5xx requires inspecting response status, whereas counting reactive failures looks at signals — two distinct concepts.

### Logic before subscribe: defer when needed

If a measurement or side effect must execute at subscription time rather than Mono creation time, use:

```java
return Mono.defer(() -> {
    long start = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal ->
                    recordDuration(System.nanoTime() - start, signal));
});
```

Snippet assuming `recordDuration`. This makes the laziness of the reactive pipeline explicit, useful in tests/retries. Avoid writing request-specific data into singleton fields.

### Setting status/headers before commit

```java
exchange.getResponse().getHeaders()
        .set("X-Request-Scope", "webflux");

return chain.filter(exchange);
```

Set headers **before** delegating downstream. If work needs to happen right before commit, `response.beforeCommit(...)` is available, yet you still must not block or alter headers after commit.

## 6. Ordering multiple WebFilters

Spring discovers `WebFilter` beans and sorts them by `Ordered`, `@Order`, or framework conventions. In a pipeline with:

- `@Order(-20)` — filter A.
- `@Order(-10)` — filter B.

Typically A is **outer** and B is **inner**; A runs before calling B, and B before the handler. After downstream completes, "after" callbacks can run in **reverse order** due to nested publishers:

```text
A before
  B before
    Handler
  B after
A after
```

Exact ordering of multiple `doOnSuccess`/`doFinally` operators and async signal processing should be tested when critical: `doFinally` runs on termination/cancellation and can observe a callback order different from intuitive "stack unwind". The diagram is only a basic model.

### Do not infer order from class names alone

`WebHttpHandlerBuilder.applicationContext(...)` uses ordered discovery. If an app has Spring Security WebFilters, tracing filters, and custom filters, their order is not solely the numbers you wrote. Do not arbitrarily put `@Order(Ordered.HIGHEST_PRECEDENCE)` on a custom filter and assume it should always run before authentication; you could accidentally bypass or break CORS/CSRF/context propagation.

**Security policies** belong in the Spring Security reactive chain, not in a custom filter relying on client-controlled headers. When a specific order is genuinely required, inspect the security chain configuration and integration tests.

### Registering a filter once

`@Component` or `@Bean` is usually enough for the builder to discover the filter. Do not simultaneously register the same object via both bean auto-discovery and manual builder configuration unintentionally — it easily runs twice.

## 7. ServerWebExchange: sharing data between filters and endpoints

`ServerWebExchange` represents **one request–response exchange**.

```java
String path = exchange.getRequest().getPath().value();
HttpMethod method = exchange.getRequest().getMethod();

exchange.getResponse().getHeaders()
        .set("X-Policy", "observed");

exchange.getAttributes().put("audit.tag", "ok");
String tag = exchange.getAttributeOrDefault(
        "audit.tag", "missing");
```

This is a snippet requiring imports `HttpMethod` and `ServerWebExchange`. Other members:
- `exchange.getPrincipal()` → `Mono<Principal>`, may be empty.
- `exchange.getSession()` → `Mono<WebSession>`.
- `exchange.getFormData()`/`getMultipartData()` → Mono holding parsed data.
- `exchange.getLocaleContext()` from the locale resolver.
- `exchange.getResponse().isCommitted()` to inspect the write lifecycle.
- `exchange.mutate()` to wrap request/response.

### Exchange attributes are not request headers

`exchange.getAttributes()` is an internal map **living only within the exchange** and is not automatically sent to the client. Avoid generic keys like `user` that can clash across libraries; choose namespaced keys like `com.example.trace.id`.

### Exchange attributes vs Reactor Context

| Storage | Characteristics | Appropriate use |
| --- | --- | --- |
| HTTP request headers | Provided by client/proxy; spoofable | Accept, content type, correlation ID after validation |
| Exchange attributes | Mutable request-scoped map | Sharing data between WebFilter and Handler |
| Reactor `Context` | Immutable subscription-scoped context | Reactive tracing/security propagation |
| `WebSession` | State across exchanges per session policy | Session attributes when truly needed |
| `ThreadLocal` | Thread-bound state | Not automatically preserved across reactive scheduler switches |

Use `Mono.deferContextual(contextView -> ...)` if you need to read Reactor Context inside a reactive pipeline. Do not use `Thread.currentThread().getName()` as user identity and do not assume custom MDC always propagates cleanly across event loops.

### Reading Principal without blocking

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

This snippet returns `Mono<String>`. Never call `exchange.getPrincipal().block()` on the event loop. With Spring Security, reactive authentication and authorization should use the framework-integrated SecurityContext/Principal; **never treat a client-sent `X-User` header as an authenticated user**.

## 8. Mutating request/exchange to normalize metadata

`exchange.mutate()` lets you create a wrapper view of the exchange:

```java
ServerWebExchange nextExchange = exchange.mutate()
        .request(builder ->
                builder.header("X-Internal-Marker", "server-side"))
        .build();

return chain.filter(nextExchange);
```

This is a snippet inside `WebFilter.filter(...)`. Use it when you need to add a server-controlled internal header for downstream handlers. Only `return chain.filter(nextExchange)` passes the wrapper to the next filter; passing the old `exchange` means changes will not reach downstream.

Be careful:
- Do not fabricate authentication identity from unverified headers.
- Changing path, routing, host, or scheme heavily affects authorization and cache keys; enforce trust boundaries/allowlists.
- Mutating metadata does not automatically read, cache, or transform body bytes.
- Never store `ServerWebExchange` in singleton state or long-lived background queues.

## 9. WebExceptionHandler: role and signature

`WebExceptionHandler` sits at the same `org.springframework.web.server` layer as WebFilter:

```java
@FunctionalInterface
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
```

This is the conceptual signature from Javadoc. An exception handler is invoked when the inner pipeline emits an **error signal**. It decides:

1. Does it handle this error type?
2. Is the response already committed?
3. If handleable: what status/headers/body should be returned to the client?
4. If not handleable: return `Mono.error(ex)` so the next handler or runtime handles it.

**Do not return `Mono.empty()` for every error** just to keep logs clean; doing so can leave the client with an incorrect status/body.

### Handling a custom error

```java
WebExceptionHandler handler = (exchange, ex) -> {
    if (!(ex instanceof DemoFailure)) {
        return Mono.error(ex);
    }
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    exchange.getResponse()
            .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
};
```

This is a **snippet**, where `DemoFailure` is an application-defined custom exception. It returns 503 with no body; the runnable version in section 13 returns a JSON error with an explicit content type.

### Where does a WebExceptionHandler catch errors from?

It can handle **unhandled** errors from:
- Inner `WebFilter`s.
- Target `WebHandler`, typically `DispatcherHandler`.
- Handler mapping, controller/handler invocation, and response rendering if the error surfaces as a Publisher error and the response is not too late.
- Certain lifecycle errors inside the WebHandler chain.

It is **not** guaranteed to catch:
- Socket/TLS errors in the HTTP server before an exchange is created.
- Exceptions already handled by `@ExceptionHandler` or another framework handler.
- Errors raised inside a detached `subscribe()` outside the outer pipeline.
- Errors occurring after the HTTP response has sent part of the body and cannot be rewritten as a normal JSON response.

### Error propagation is part of the reactive contract

```java
return chain.filter(exchange)
        .onErrorResume(MyKnownException.class, error ->
                writeKnownError(exchange, error));
```

This is a snippet with `writeKnownError` from the app. It places error handling **inside a WebFilter**, which can prevent the error from reaching `WebExceptionHandler`. Use this sensibly for errors owned by the filter; for an API-wide error policy, choose a properly registered/ordered `WebExceptionHandler`. Avoid having two layers catch the same exception and write twice.

## 10. WebHttpHandlerBuilder builds the filter/error chain

`WebHttpHandlerBuilder` is responsible for:
1. Taking a target `WebHandler`, wrapping it with `WebFilter`s, and then wrapping with `WebExceptionHandler`s.
2. Adapting the chain into an `HttpHandler` via `HttpWebHandlerAdapter`.

It can be built from an ApplicationContext:

```java
HttpHandler handler = WebHttpHandlerBuilder
        .applicationContext(applicationContext)
        .build();
```

Or assembled manually:

```java
HttpHandler handler = WebHttpHandlerBuilder
        .webHandler(targetWebHandler)
        .filter(firstWebFilter, secondWebFilter)
        .exceptionHandler(myWebExceptionHandler)
        .build();
```

These are snippets with existing objects; imports for `HttpHandler` and `WebHttpHandlerBuilder` are required. The manual form does not start an HTTP server. `WebTestClient.bindToHttpHandler(handler)` or mock `MockServerHttpRequest/Response` can test the pipeline without opening a TCP port.

As of Spring 6.1, the builder looks up commonly used beans:

| Type | Discovery/registration | Role |
| --- | --- | --- |
| `WebHandler` | Usually bean named `webHandler` | Request-processing target; typically DispatcherHandler |
| `WebFilter` | Beans by type/ordering | Cross-cutting interception |
| `WebExceptionHandler` | Beans by type/ordering | Unhandled errors |
| `WebSessionManager` | Optional standard-named bean | WebSession |
| `ServerCodecConfigurer` | Optional standard-named bean | Form/multipart, codec integration |
| `LocaleContextResolver` | Optional standard-named bean | Locale |
| `ForwardedHeaderTransformer` | Optional standard-named bean | Trust-aware proxy forwarded headers |
| HTTP decorators/observation | Per version/config | Observability or wrappers |

**Do not define an extra `webHandler` bean in a Boot REST app just to attach a filter.** It can replace DispatcherHandler or cause a bean conflict. Using `WebFilter`/`WebExceptionHandler` beans is the right way to extend most use cases.

### Ordering of exception handlers

When multiple `WebExceptionHandler`s exist, order decides who gets the first chance to handle an error. A handler may handle a custom exception and complete; subsequent handlers do not need to see it. If it does not recognize the error, it must return `Mono.error(ex)` so downstream error handlers can process it.

Spring WebFlux provides `ResponseStatusExceptionHandler` and `WebFluxResponseStatusExceptionHandler`. Spring Boot has its own error handler; the exact ordering of default/custom handlers must be verified in your app. **Do not assume every `ResponseStatusException` passes through a custom WebExceptionHandler** if annotated advice handled it earlier.

## 11. Response commit and error handling limits

A response conceptually goes through these stages:
1. Set HTTP status/headers.
2. Prepare the response body publisher.
3. Commit headers and begin writing the body.
4. Write data chunks (possibly streaming).
5. Complete or fail/cancel.

`exchange.getResponse().isCommitted()` indicates whether the response was committed at the moment of inspection. After commit, you cannot guarantee changing status/headers or starting a new JSON error response.

### beforeCommit hook

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Before-Commit", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
```

This is a snippet in a WebFilter. The `beforeCommit` callback runs right before commit when the response lifecycle reaches that point. Do not call blocking database/sync HTTP inside the callback, and do not register the callback too late. When side effects depend on subscription, make sure the code returns a Publisher executed per the API rather than acting outside the chain.

### Errors after partial write

Example streaming CSV:

```text
HTTP/1.1 200 OK
Content-Type: text/csv

id,name
1,Lan
2,Minh
[Flux<DataBuffer> error]
```

The client has already received headers and part of the body. WebExceptionHandler usually cannot turn the response into an intact `500 application/problem+json` anymore. Streaming protocol design must define broken streams, retries, checksums, or error events (SSE) where appropriate. Never swallow the error and treat the CSV as successful.

### ResponseStatusException and @ExceptionHandler

In annotated controllers, `@ExceptionHandler`/`@RestControllerAdvice` can map business errors into HTTP responses **before** the error reaches the WebExceptionHandler layer. In functional routes, handlers/filters can explicitly return an error `ServerResponse`. Thus, the two error mechanisms complement one another rather than obeying a rule that "WebExceptionHandler always runs for every exception".

## 12. Security, CORS, and filter order

Spring Security WebFlux uses reactive filters/`SecurityWebFilterChain` for authentication/authorization. Consequently, requests protected by the security chain must be authenticated before business logic runs. A custom WebFilter should normally **not** decode bearer tokens itself, infer users from `X-User`, or implement admin authorization via path strings.

### Do not use client headers for permissions

```java
// ANTI-PATTERN: client can send X-Role: ADMIN itself.
if ("ADMIN".equals(exchange.getRequest()
        .getHeaders().getFirst("X-Role"))) {
    grantAccess();
}
```

This is an unsafe snippet with a hypothetical `grantAccess`. Encoding/validating a header does not replace signatures, token verification, or role/tenant checks. Use Spring Security and service-level ACL/authorization checks instead.

### CORS is not authentication

Browser `OPTIONS` preflight requests can arrive before the main request and usually carry no credentials. If Security blocks preflight before CORS processing, the app can exhibit CORS errors even when the actual endpoint works. Use Spring WebFlux CORS config/`CorsWebFilter` and integrate Spring Security per the documentation, ensuring origins/methods/headers/credentials match policy. Never add `Access-Control-Allow-Origin: *` to responses carrying cookies.

### Forwarded headers/Host

`Forwarded`/`X-Forwarded-Host`/`X-Forwarded-Proto` can be spoofed if a proxy does not sanitize them. When a filter builds redirects or absolute URLs from an untrusted request host, there is a risk of host header poisoning/phishing/cache poisoning. Trusted proxies must strip incoming forwarded headers and set canonical values; applications need a trust model or configured canonical public origin.

### CSRF and session

With session-cookie auth, POST/PATCH/DELETE in WebFlux still face CSRF risks. Do not disable CSRF simply because "the API is reactive" or to make curl tests quick. `WebSession` does not automatically make a request authenticated; session handling and auth policies must be explicit.

## 13. Runnable Spring Boot WebFlux project

We build a demo app:

- `GET /api/demo/hello/{name}`: controller reads exchange attributes set by a filter.
- `GET /api/demo/async`: returns a Mono emitting a result after a short delay.
- `GET /api/demo/from-controller-error`: raises `DemoFailure` from the handler, mapped by a custom WebExceptionHandler to 503 JSON.
- `GET /api/demo/from-filter-error`: an inner filter raises the same error type, also handled by the custom WebExceptionHandler.
- `GET /api/demo/blocked`: an inner filter intentionally short-circuits with 429, **with no controller method**, proving a filter can complete a request on its own.
- Two WebFilters ordered with `@Order(-20)` and `@Order(-10)`.
- One WebExceptionHandler ordered with `@Order(-2)` to catch `DemoFailure` before some default Boot handlers.
- WebTestClient tests against an embedded server and a low-level mock chain test.

**Demo limitations:** No authentication, database, or high-load benchmarking. The JSON error code is a server-fixed string to avoid injection. Rate-limit policies are illustrated only with a fixed path, **not a production rate-limiting algorithm**.

### 13.1. Project structure

```text
webflux-filter-demo/
├── pom.xml
└── src/
    ├── main/java/demo/filters/
    │   ├── FilterDemoApplication.java
    │   ├── DemoFailure.java
    │   ├── OuterMarkerFilter.java
    │   ├── InnerPolicyFilter.java
    │   ├── DemoErrorHandler.java
    │   └── DemoController.java
    └── test/java/demo/filters/
        ├── DemoWebFluxTest.java
        └── LowLevelChainTest.java
```

### 13.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-filter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

Add only `starter-webflux`, **not `starter-web`**, so Boot starts a normal reactive WebFlux app. When both starter-web and starter-webflux are on the classpath, Boot usually picks Servlet MVC unless explicitly configured; do not test an MVC app and call it WebFlux.

### 13.3. Boot application

**`src/main/java/demo/filters/FilterDemoApplication.java`**

```java
package demo.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
```

### 13.4. Application-owned exception class

**`src/main/java/demo/filters/DemoFailure.java`**

```java
package demo.filters;

public final class DemoFailure extends RuntimeException {
    public DemoFailure(String message) {
        super(message);
    }
}
```

Do not use `IllegalArgumentException` for all errors because an IllegalArgumentException can represent a programming bug rather than a specific business/HTTP 4xx/5xx condition. Here `DemoFailure` is intentionally mapped to 503 Service Unavailable.

### 13.5. Outer WebFilter: attributes and header

**`src/main/java/demo/filters/OuterMarkerFilter.java`**

```java
package demo.filters;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-20)
public class OuterMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();
        if (!path.startsWith("/api/demo/")) {
            return chain.filter(exchange);
        }

        exchange.getAttributes().put(
                "demo.marker", "outer-filter");
        exchange.getResponse().getHeaders()
                .set("X-Demo-Outer", "visited");

        return chain.filter(exchange);
    }
}
```

This filter:
- Operates only on request paths under `/api/demo/`.
- Adds internal attribute `demo.marker`.
- Adds response header `X-Demo-Outer` **before** the body commits.
- Calls `chain.filter(exchange)` exactly once.
- Does not read the body, access network/DB, or spawn new threads.
- Is independent of HTTP handler style: both annotated and functional endpoints under the exchange chain can be filtered.

### 13.6. Inner WebFilter: short-circuit or error signal

**`src/main/java/demo/filters/InnerPolicyFilter.java`**

```java
package demo.filters;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-10)
public class InnerPolicyFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();
        if (!path.startsWith("/api/demo/")) {
            return chain.filter(exchange);
        }

        exchange.getResponse().getHeaders()
                .set("X-Demo-Inner", "visited");

        if (path.equals("/api/demo/blocked")) {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
            return exchange.getResponse().setComplete();
        }

        if (path.equals("/api/demo/from-filter-error")) {
            return Mono.error(new DemoFailure("filter-failed"));
        }

        return chain.filter(exchange);
    }
}
```

The `blocked` branch intentionally has no controller method. The client still receives `429 Too Many Requests` because the filter sets the status and completes **itself**; no target handler is needed. The `from-filter-error` branch returns an error publisher. The outer WebExceptionHandler layer can map it to HTTP 503.

Important:
- This is **not** real key/bucket rate limiting; the fixed path merely demonstrates short-circuiting.
- Do not catch/rewrite an already-committed response.
- Do not manually subscribe.
- If the app later uses Spring Security, policies must be reviewed against reactive security chain ordering; the demo has no Spring Security dependency.

### 13.7. Custom WebExceptionHandler: handles only DemoFailure

**`src/main/java/demo/filters/DemoErrorHandler.java`**

```java
package demo.filters;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class DemoErrorHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable error) {

        if (!(error instanceof DemoFailure)) {
            return Mono.error(error);
        }

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        exchange.getResponse()
                .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        exchange.getResponse().getHeaders()
                .setContentType(MediaType.APPLICATION_JSON);

        // Fixed JSON, without embedding exception details.
        byte[] data = "{\"code\":\"demo_unavailable\"}"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = exchange.getResponse()
                .bufferFactory().wrap(data);

        return exchange.getResponse()
                .writeWith(Mono.just(buffer));
    }
}
```

**Why map to 503 and a fixed body?**

- `DemoFailure` is a known error type with a specific policy.
- Do not pass raw exception messages directly into JSON as they may leak internal details.
- `WebExceptionHandler` is a low-level WebFlux component: it writes directly via `ServerHttpResponse` rather than assuming Jackson will serialize `ApiError` for it.
- `isCommitted` is checked before status/body. The check still does not guarantee no race if the response commits concurrently; async streaming needs its own policy.
- `@Order(-2)` demonstrates participating in error handler ordering. In a real Boot app, audit the entire chain/default handlers and write integration tests; **do not rely solely on an order number as a guarantee across all Spring versions**.
- For other errors, return `Mono.error(error)` so default Spring Boot/WebFlux error mechanisms get a chance to handle them.

### 13.8. Controller using attributes and reactive publishers

**`src/main/java/demo/filters/DemoController.java`**

```java
package demo.filters;

import java.time.Duration;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/hello/{name}")
    public Mono<Map<String, String>> hello(
            @PathVariable String name,
            ServerWebExchange exchange) {

        String marker = exchange.getAttributeOrDefault(
                "demo.marker", "missing");

        return Mono.just(Map.of(
                "name", name,
                "marker", marker));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return Mono.delay(Duration.ofMillis(20))
                .map(ignored -> Map.of("status", "ready"));
    }

    @GetMapping("/from-controller-error")
    public Mono<String> controllerError() {
        return Mono.error(new DemoFailure("controller-failed"));
    }
}
```

**Learning takeaways from the demo:**
- The same `ServerWebExchange` passes through WebFilters and the controller; attribute `demo.marker` can be read back.
- `Mono.delay` uses a scheduler to emit a signal in the future instead of `Thread.sleep` on the event loop.
- Controller `Mono.error(DemoFailure)` shows errors from a handler flowing through the reactive error chain.
- There are no controller endpoints for `/blocked` and `/from-filter-error`; they are handled entirely at the filter/error-handler tiers.
- Do not store the exchange in a bean field, and do not create request-specific mutable state in singletons.

## 14. Running with Maven and curl

In the `webflux-filter-demo` directory, with JDK 17+ and Maven installed:

```bash
mvn test
mvn spring-boot:run
```

These are **two sequential commands**. Spring Boot listens on `localhost:8080` by default unless another port/profile is configured.

### 14.1. Successful request

```bash
curl -i 'http://localhost:8080/api/demo/hello/Lan'
```

Notable parts:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Demo-Outer: visited
X-Demo-Inner: visited

{"name":"Lan","marker":"outer-filter"}
```

JSON key order is not a contract; it depends on Jackson Map serialization, so do not assert exact ordered body strings.

### 14.2. Async endpoint

```bash
curl -i 'http://localhost:8080/api/demo/async'
```

Expected HTTP 200, with both headers from the filters, JSON:

```json
{"status":"ready"}
```

Using Mono.delay does not prove the entire app's event-loop code is non-blocking; the project merely has an illustrative publisher.

### 14.3. Filter short-circuits itself

```bash
curl -i 'http://localhost:8080/api/demo/blocked'
```

Expected:

```http
HTTP/1.1 429 Too Many Requests
X-Demo-Outer: visited
X-Demo-Inner: visited
```

Empty body because `setComplete()` supplies no JSON. There is no controller mapping for this URL yet it still returns 429 — `InnerPolicyFilter` itself completed the exchange.

### 14.4. Errors from filter and controller both reach the exception handler

```bash
curl -i 'http://localhost:8080/api/demo/from-filter-error'
curl -i 'http://localhost:8080/api/demo/from-controller-error'
```

Both expected:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
X-Demo-Outer: visited
X-Demo-Inner: visited

{"code":"demo_unavailable"}
```

This is the contract provided by the **custom `WebExceptionHandler`** for `DemoFailure`. If an exception was already handled into a response by an annotated `@ExceptionHandler` earlier, WebExceptionHandler will not necessarily receive it. Also do not assume default Boot error responses share the same schema.

## 15. WebTestClient integration tests with a real HTTP server

**`src/test/java/demo/filters/DemoWebFluxTest.java`**

```java
package demo.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DemoWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothFiltersRunBeforeAnnotatedController() {
        client.get().uri("/api/demo/hello/Lan")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-Demo-Outer", "visited")
              .expectHeader().valueEquals(
                      "X-Demo-Inner", "visited")
              .expectBody()
              .jsonPath("$.marker").isEqualTo("outer-filter")
              .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void asyncBodyFinishes() {
        client.get().uri("/api/demo/async")
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void filterCanCompleteRequestWithoutController() {
        client.get().uri("/api/demo/blocked")
              .exchange()
              .expectStatus().isEqualTo(429)
              .expectHeader().valueEquals(
                      "X-Demo-Inner", "visited");
    }

    @Test
    void errorFromFilterGoesToWebExceptionHandler() {
        client.get().uri("/api/demo/from-filter-error")
              .exchange()
              .expectStatus().isEqualTo(503)
              .expectBody()
              .jsonPath("$.code")
                  .isEqualTo("demo_unavailable");
    }

    @Test
    void errorFromControllerAlsoReachesHandler() {
        client.get().uri("/api/demo/from-controller-error")
              .exchange()
              .expectStatus().isEqualTo(503)
              .expectBody()
              .jsonPath("$.code")
                  .isEqualTo("demo_unavailable");
    }
}
```

The tests run with an embedded `RANDOM_PORT` server, sending HTTP requests via `WebTestClient`. There are **5 test methods**; they verify success, short-circuit, and error flows rather than invoking Java controller methods directly.

What the tests do **not** prove:
- Spring Security authentication/CSRF rules (the demo does not add Security).
- Production-accurate proxy/ingress forwarded headers.
- Backpressure and performance under thousands of slow clients.
- Socket errors after the response has partially streamed.
- Identical HTTP status/body across all Spring Boot versions.

## 16. Low-level unit test for WebFilterChain and WebExceptionHandler

To observe how the builder assembles the web layer **without a controller**, use a custom `WebHandler` with manual filter/error handlers. No Netty server needs to start.

**`src/test/java/demo/filters/LowLevelChainTest.java`**

```java
package demo.filters;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebHandler;
import org.springframework.web.server.adapter.WebHttpHandlerBuilder;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LowLevelChainTest {

    @Test
    void manualChainRunsFilterThenWebHandler() {
        WebHandler target = exchange -> {
            String marker = exchange.getAttributeOrDefault(
                    "marker", "missing");

            exchange.getResponse()
                    .setStatusCode(HttpStatus.OK);
            exchange.getResponse().getHeaders()
                    .setContentType(MediaType.TEXT_PLAIN);

            DataBuffer buffer = exchange.getResponse()
                    .bufferFactory()
                    .wrap(marker.getBytes(StandardCharsets.UTF_8));

            return exchange.getResponse()
                    .writeWith(Mono.just(buffer));
        };

        WebFilter filter = (exchange, chain) -> {
            exchange.getAttributes()
                    .put("marker", "filter-was-here");
            return chain.filter(exchange);
        };

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(filter)
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("filter-was-here",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }

    @Test
    void manualExceptionHandlerCanCatchFilterError() {
        WebHandler target = exchange ->
                exchange.getResponse().setComplete();

        WebFilter broken = (exchange, chain) ->
                Mono.error(new DemoFailure("expected"));

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(broken)
                .exceptionHandler(new DemoErrorHandler())
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw-error").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE,
                response.getStatusCode());
        assertEquals("{\"code\":\"demo_unavailable\"}",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }
}
```

The test class has **2 test methods**. Combined with the 5 tests in section 15, that is **7 test methods**. If the project is created properly and `mvn test` passes all tests, Maven exits with code 0 and typically reports a summary like `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0` (reporting format may vary by plugin/test runner).

**Why is `block()` present in the test?** This is a unit test running outside an event loop that must wait for Mono completion on a mock exchange to assert the body; blocking is **strictly for testing**. Production WebFilters/controllers have no manual `block()` or `subscribe()`.

**Test limitation:** Mock HTTP classes do not reproduce all socket/I/O characteristics, timeouts, or WebFlux controller metadata. Manual chain tests complement integration tests; they do not replace them.

## 17. Writing effective and safe custom WebFilters

### 17.1. Do not read the request body twice

`ServerHttpRequest.getBody()` is a `Flux<DataBuffer>`, typically representing a one-shot network stream. Wrong approach:

```java
// ANTI-PATTERN: manually subscribing to raw body while letting the handler read it again.
exchange.getRequest().getBody()
        .subscribe(buffer -> logRaw(buffer));
return chain.filter(exchange);
```

This is pseudocode since `logRaw` does not exist. It can:
- Consume the body before the controller decoder, causing `@RequestBody` to receive empty/errored data.
- Create two competing subscriptions.
- Expose passwords/tokens/PII in logs.
- Leak pooled DataBuffers if not released.
- Lose backpressure/cancellation of the outer request pipeline.

If you genuinely need body auditing, prefer framework-supported instrumentation, or build a decorator/buffer policy with **byte limits**, preserved backpressure, and proper release ownership. Do not assume a WebFilter is allowed to log every HTTP body.

### 17.2. Avoid blocking I/O inside filters

```java
// ANTI-PATTERN: blocking JDBC on the WebFlux event loop.
User user = jdbcRepository.findById(id);
return chain.filter(exchange);
```

This is an illustrative snippet; `jdbcRepository`/`id` are hypothetical. Returning `Mono<Void>` does not turn synchronous JDBC calls into non-blocking operations.

If a blocking library is temporarily unavoidable:

```java
return Mono.fromCallable(() -> blockingPolicyService.evaluate(id))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(allowed -> {
            if (!allowed) {
                exchange.getResponse()
                        .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        });
```

This is a snippet with undefined service/id imports. `boundedElastic` **offloads blocking work to a bounded thread pool**; it does not make the driver non-blocking. Guard pool size, queues, downstream timeouts, and transactions/contexts. For truly reactive systems, prefer non-blocking drivers/clients for auth/policy lookups.

### 17.3. Do not store request/exchange in singleton fields

A `@Component` WebFilter is normally a singleton serving many concurrent requests. Never do:

```java
private ServerWebExchange currentExchange;
```

and assign it inside the filter for later use. Requests A and B can overwrite state, causing data leaks and holding request resources past completion. Use local variables, exchange attributes, Reactor Context, and request-specific structures that get cleaned up.

### 17.4. Reactive Context and MDC

Trace/user/security data should not rely solely on custom `ThreadLocal`s because reactive work can hop across schedulers. Use Reactor Context / context propagation from Spring/Micrometer/Spring Security; if bridging to MDC, always restore/clear properly. `exchange.getAttributes()` can pass an internal marker, yet it does not replace a full distributed tracing context.

### 17.5. Metrics cardinality

A filter recording request counts by path should not use raw `/users/1000001`, `/users/1000002` as distinct tags. Use **route templates** like `/users/{id}` when available and mind when route mapping is resolved. Never log queries containing access tokens or PII values.

### 17.6. Cancellation

`doFinally(signalType -> ...)` receives `CANCEL` when a subscriber cancels. Client disconnects often trigger cancellation at some level of the reactive pipeline, yet **not every** kind of network failure is observed identically as `CANCEL`. Clean up resources in finally/dispose/usingWhen per contract, not only in `doOnSuccess`.

## 18. CORS, tracing, and auth: where should each go?

| Need | Appropriate place | Avoid doing |
| --- | --- | --- |
| Authentication/authorization | Spring Security reactive `SecurityWebFilterChain` + service ACL | Trusting client `X-Role` |
| CORS | Spring WebFlux CORS config/`CorsWebFilter` ordered properly with security | Wildcard allow-origin + credentials |
| Correlation/trace | Observation/Micrometer + Reactor Context | Arbitrarily copying raw `ThreadLocal` |
| Request header policy | Clearly scoped WebFilter | Setting after commit |
| Rate limiting | Gateway/server-side shared policy with trusted keys | Short-circuiting based on user-supplied "admin" header |
| Domain errors | Controller advice/functional handler mapping per scope | WebExceptionHandler catching every Exception and returning 400 |
| Infrastructure errors | Properly ordered WebExceptionHandler with fallback | Ignoring errors when response is already committed |
| Request body logging | Approved redacted bounded instrumentation | Subscribing to body before converter |
| Status/latency logging | Observation or WebFilter with cleanup | High-cardinality tags, logging secrets |
| HTTP response transform | Appropriate codec/result handler or decorator | Editing headers after commit |

### Why not use one filter for everything?

A single filter handling auth, CORS, multipart parsing, caching, tracing, error serialization, and metrics will:
- Be hard to reason about in ordering and trust boundaries.
- Easily cause double subscriptions/repeated body reads.
- Hinder unit/integration testing.
- Easily swallow exceptions or produce wrong statuses.
- Complicate Spring Security/Boot version upgrades.

Use small, single-responsibility filters, compose them via the Spring container, and test their contracts.

## 19. Analyzing differences between 401/403/404/429 and publisher errors

**HTTP 401 Unauthorized**: the client is not properly authenticated, usually handled by Spring Security's authentication entry point, potentially requiring `WWW-Authenticate` per scheme.

**HTTP 403 Forbidden**: the client has an identity yet lacks sufficient permissions (or fails CSRF rules), usually enforced by authorization policy.

**HTTP 404 Not Found**: no matching route/resource exists; can be a completely normal response where the Mono completes normally.

**HTTP 429 Too Many Requests**: rate-limiting policy actively short-circuits; can include `Retry-After` if semantics are clear.

**HTTP 503 Service Unavailable**: backend/dependency temporarily unavailable; in the demo, returned by the custom exception handler for `DemoFailure`.

**Reactive error signal**: the publisher failed. This signal **does not determine the HTTP status by itself**; handlers/error mappings decide the status before the response commits.

An application should distinguish:
- HTTP response status metrics.
- Exceptions/error signals.
- Client cancellations.
- Downstream 5xx errors from WebClient (which can be ordinary ResponseEntities if using exchangeToMono and handling statuses explicitly).
- Body streaming failures after commit.

Do not equate every 4xx with a Java exception and do not assume every Mono.error automatically becomes a 500 JSON with the same schema.

## 20. WebExceptionHandler, @ControllerAdvice, and functional router error handling

The same WebFlux app can combine:
- Annotated controller `@ExceptionHandler`/`@RestControllerAdvice`.
- Functional router `HandlerFilterFunction` or explicit `ServerResponse` for domain errors.
- Outer `WebExceptionHandler` for errors escaping into the WebHandler chain infrastructure.
- Default Spring Boot `ErrorWebExceptionHandler` for remaining exceptions.

**Logical order:** if an exception has already been converted into an HTTP response by an inner layer, outer layers typically only observe normal completion; they have no reason to receive the same exception again. If the inner layer lets the error propagate, WebExceptionHandler can receive it. Once part of the response has committed, modifying body/status is limited.

### Do not swallow unrecognized errors

```java
if (!(error instanceof MyExpectedError)) {
    return Mono.error(error);
}
```

This line plays a critical role in a custom WebExceptionHandler: **letting other handlers/fallbacks handle it**. Always returning `Mono.empty()` for every exception can make a failed request appear successful or leave a partial response body without an appropriate status.

### Do not expose Throwable contents

`error.getMessage()` can contain secrets, SQL fragments, internal hostnames, or stack details. Public error responses should use sanitized codes/messages. Internal logs should use trace IDs, security-safe context, and structured logging, avoiding dumping auth headers/raw request bodies.

## 21. Debugging checklist

When filters or custom exception handling behave unexpectedly:

1. **Identify the real stack**: is Boot running reactive WebFlux or accidentally MVC due to starter-web?
2. Confirm imports are `org.springframework.web.server.WebFilter`/`WebFilterChain`/`WebExceptionHandler`, not Servlet Filter.
3. Verify `@Component`/`@Bean` component scanning without duplicate registrations.
4. Inspect ordering via `@Order`/`Ordered`, especially alongside Spring Security/CORS.
5. Set markers/headers in two filters to prove requests pass through in the expected order.
6. Verify the filter **returns** `chain.filter(exchange)` exactly once.
7. For 429/403 responses, verify the filter short-circuited and the target controller was not invoked.
8. For errors, check whether `Mono.error` propagates or was intercepted by `onErrorResume`.
9. Check whether `@ControllerAdvice` handled the exception before WebExceptionHandler.
10. Inspect `exchange.getResponse().isCommitted()` when a custom handler fails to change the status.
11. If the body is empty, look for code subscribing to/reading `getBody()` in a WebFilter.
12. If the app is slow, look for `block()`/sync JDBC on event loops and queue overload.
13. If response headers are missing, check commit timing and filter scope.
14. If 404 occurs despite an existing route, inspect predicates/method/path, handler mappings, and prefixes.
15. If CORS preflight returns 401/403, check WebFlux CORS/Security ordering and OPTIONS policies.
16. If memory grows, check buffers, sessions, long-lived publishers, and cancellation cleanup.
17. For forwarded headers, verify proxy sanitization/trust policies to prevent Host injection.
18. Test the app with WebTestClient and then through a production-like reverse proxy/runtime.

## 22. Common pitfalls

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Filter does not seem to run | Wrong Servlet filter import, bean not scanned, wrong path scope | Use WebFlux WebFilter and verify bean registration |
| Filter runs twice | Manually subscribing to chain or registering twice | Return the chain once, register one bean |
| Controller does not run | Filter forgot `chain.filter(exchange)` or short-circuited | Inspect return branches, test intentional 429s |
| WebExceptionHandler misses errors | Error already handled by advice or detached subscription | Check propagation, remove manual subscribe |
| WebExceptionHandler runs but cannot change status | Response already committed | Handle errors early; streaming error policy |
| HTTP 404 yet `doOnError` does not run | 404 is a normal response | Inspect response status, not only error signals |
| `Mono<Void>` returned yet request hangs | Publisher never completes/callbacks missing | Check subscriptions, timeouts, and producers |
| High CPU | Blocking database/calls on the event loop | Non-blocking client or bounded offload |
| Request body lost | WebFilter read one-shot body before decoder | Do not double-read; decorate properly |
| Response written twice | Both filter and handler write/subscribe | One chain, one writer per policy |
| Error body leaks SQL exception | Returning raw Throwable message | Sanitized API errors |
| `@Order` breaks auth | Putting custom filter before/outside security without testing | Spring Security integration + tests |
| Filter cannot see principal | Unauthenticated or empty Mono | Reactive SecurityContext/Principal |
| Lost trace ID | Using ThreadLocal outside Reactor Context | Supported context propagation |
| Excessive session creation | Filter reads/writes session unnecessarily | Use session only when genuinely needed |
| Missing header | Set after commit | Set earlier or use beforeCommit |
| CORS failure | Security blocks OPTIONS/preflight | Configure CORS in proper order |
| Mutable field leaks user data | Singleton filter stores request state | Use locals/exchange attributes |
| Netty buffer leak | Retained DataBuffer not released | `DataBufferUtils.release` with proper ownership |
| Retry causes duplicate POST | Filter retries a publisher with side effects | Use idempotency contracts, avoid blind retries |
| Unexpected 200 empty body | Swallowing errors with `Mono.empty()` or `setComplete` without status | Map errors/statuses explicitly |
| Slow clients spike memory | Unbounded buffers, missing backpressure | Bounded buffering, cancellation, observability |
| WebFilter vs GatewayFilter confusion | Mixing up Spring Cloud Gateway-specific APIs | Distinguish WebFlux vs Gateway |
| Tests pass but prod error status differs | Different default Boot handler/version, proxy/commit | Integration tests on actual stack |

## 23. Production deployment checklist

- [ ] Correct `spring-boot-starter-webflux` and reactive application context.
- [ ] WebFilter beans scanned, clear ordering, no duplicates.
- [ ] Every branch either **returns the chain once** or **short-circuits + completes response**.
- [ ] No manual `block()`/`subscribe()` on the event-loop request pipeline.
- [ ] No logging of sensitive bodies/Authorization/Cookie or sensitive request IDs.
- [ ] Namespaced attributes; no request-specific data stored in singleton fields.
- [ ] Headers/status set before response commit.
- [ ] WebExceptionHandler catches only known error types, preserving fallback for others.
- [ ] Error JSON does not leak raw Throwables and uses appropriate statuses.
- [ ] Streaming errors and cancellations have dedicated cleanup.
- [ ] SecurityWebFilterChain handles authentication/authorization properly.
- [ ] CORS/preflight/CSRF/session policies are accurate when credentials are used.
- [ ] Forwarded headers and Host trust boundaries are restricted.
- [ ] Body/multipart limits, pooled DataBuffers, and backpressure are enforced.
- [ ] Metrics use route templates, avoiding high-cardinality tags.
- [ ] WebTestClient verifies success, blocked, filter error, and handler error flows.
- [ ] Low-level tests cover custom infrastructure without replacing integration tests.
- [ ] Downstream timeouts, rate limiting, retries, circuit breakers, and observability are explicitly designed.

## 24. Self-check exercises

1. What arguments does `WebFilter.filter` take? What type does it return?
2. What part of processing does `WebFilterChain.filter(exchange)` represent?
3. When should a filter not call `chain.filter`?
4. What is the difference between an HTTP 404 response and `Mono.error`?
5. Why can WebExceptionHandler not always return 500 JSON when an error occurs mid-stream?
6. How do `@Order(-20)` and `@Order(-10)` affect chain nesting?
7. Why should you never call `subscribe()` manually on the chain's Mono?
8. How does `doFinally` differ from `doOnError`?
9. How does `ServerWebExchange.getAttributes()` differ from Reactor Context?
10. Why is `getPrincipal()` asynchronous?
11. If a filter wants to attach a header before commit, what must it do?
12. Can `WebExceptionHandler` receive errors from both WebFilter and WebHandler?
13. When does it not catch an error thrown by a controller?
14. Why should a custom exception handler return `Mono.error(ex)` for unrecognized errors?
15. How do Servlet `Filter` and WebFlux `WebFilter` APIs differ?
16. Should authentication be implemented from an `X-User` client header in a custom filter?
17. Can CORS replace access control?
18. Why can the raw body publisher normally not be read twice?
19. Where can pooled `DataBuffer`s leak?
20. How can you test WebFilter and a custom WebExceptionHandler without opening a port?
21. Why must `setComplete()` be distinguished from writing a JSON response?
22. Does `Mono.delay` prove all business logic is non-blocking?
23. Why must cancellation be tested when the server streams long-running data?
24. When adding a WebFilter, why should you not redefine the `webHandler` bean?
25. Is the count of HTTP 5xx responses always equal to the count of Mono.error signals?

**Hints:** (1) Exchange + chain, Mono<Void>. (2) Subsequent filters and final WebHandler. (3) When legitimately short-circuiting. (4) One is response status; the other is an error signal. (5) Response already committed/body written. (6) Outer/inner by order. (7) Runtime subscribes and expects a single pipeline. (8) doFinally also sees cancellation. (9) Request map vs subscription context. (10) Reactive auth/context services. (11) Set early or beforeCommit. (12) Yes, if the error propagates. (13) Already handled by advice/inner handler. (14) Let other fallbacks handle it. (15) Reactive Mono and ServerWebExchange vs Servlet doFilter. (16) No. (17) No. (18) One-shot network stream. (19) Decorators/caching/double subscriptions without releasing. (20) WebHttpHandlerBuilder + mock requests/responses. (21) setComplete writes no body. (22) No. (23) Release subscriptions/buffers/connections. (24) Easily replaces DispatcherHandler. (25) No.

## 25. References

- [Spring Framework — WebFlux Reactive Core: WebHandler API, Filters and Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework 6.1 — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework 6.1 — WebFilterChain Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilterChain.html)
- [Spring Framework 6.1 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html)
- [Spring Framework 6.1 — DefaultWebFilterChain Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/handler/DefaultWebFilterChain.html)
- [Spring Framework 6.1 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [Spring Security — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Conclusion:** `WebFilter` intercepts around a reactive HTTP exchange, `WebFilterChain` continues to subsequent filters and the target WebHandler, and `WebExceptionHandler` handles **unhandled error signals** at the web layer while the response can still be changed. Together, these three abstractions organize logging, policies, error handling, and observability regardless of whether endpoints use annotated controllers or WebFlux.fn. To stay correct and safe, **return a single publisher**, avoid manual subscribe/block calls, control ordering/security, understand response commit and body ownership, and separately test success, short-circuit, error, and cancellation paths.
