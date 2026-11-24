# WebFilter Applying Logic Before and After the Filter Chain in Spring WebFlux

## 1. What Is a WebFilter?

Spring WebFlux handles HTTP requests with a reactive WebHandler. Before a request reaches the final handler (usually DispatcherHandler), it can pass through a chain of WebFilters. Each filter can read the request, add metadata to the exchange, check conditions, block the request, or hand control over to the next filter.

`WebFilter` is the contract for applying logic that cuts across many endpoints, for example:

- Attach a request ID or correlation ID.
- Log processing time and the response result.
- Read the principal or session to put information into the request context.
- Add common headers, apply CORS or access policies.
- Measure metrics, tracing, timeouts, and observe errors.
- Block a request early when a condition is not met.

A WebFilter implements this method:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

The two parameters play different roles:

- `ServerWebExchange` represents one HTTP exchange and provides the request, response, attributes, session, principal, and related information.
- `WebFilterChain` lets the filter pass the request to the next filter with `chain.filter(exchange)`.

The `Mono<Void>` result represents the completion of request/response processing. The filter returns the publisher for WebFlux to manage; there is no need to subscribe yourself or wait with block.

**Before and after:** code that runs before the `chain.filter` call is the before-chain part. Callbacks attached to the chain's publisher can observe when the chain completes, emits an error, or is cancelled. In Reactor, the after part is expressed with operators such as `doOnSuccess`, `doOnError`, `doFinally`, `then`, and `onErrorResume`.

## 2. Position of WebFilter in the Request Lifecycle

~~~text
HTTP request
    |
    v
Reactive Web Server
    |
    v
WebHandler / WebHttpHandlerBuilder
    |
    v
WebFilter A
    |
    v
WebFilter B
    |
    v
WebFilter C
    |
    v
DispatcherHandler
    |
    +--> annotated controller
    |
    +--> functional RouterFunction / HandlerFunction
    |
    v
Response is written
    |
    v
Filter callbacks observe complete/error/cancel
    |
    v
HTTP response completes
~~~

A filter wraps request processing. It runs before the controller or functional handler and can observe the result after the handler's publisher finishes. That is why WebFilter suits policies applied broadly across the whole WebFlux application.

A WebFilter is not a controller and should not contain domain logic such as creating orders or calculating prices. Keep filters at the level of cross-cutting concerns: logging, tracing, security, session, CORS, metrics, or headers.

Spring Boot automatically detects beans of type `WebFilter` in the application context and puts them into the WebFlux processing chain. You can use `@Order` or implement `Ordered` when you need to define the order. The Spring Boot Reactive Web Applications documentation and the WebFilter Javadoc describe this contract.

## 3. WebFilterChain and the Rules for Calling the Chain

~~~java
@Component
public class ExampleWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        // Logic before the next filter
        return chain.filter(exchange);
    }
}
~~~

`chain.filter(exchange)` hands control over to the next part of the chain. The next part can be another WebFilter or the final WebHandler.

| Behavior | Approach | Result |
| --- | --- | --- |
| Let the request continue | `return chain.filter(exchange)` | The next filter and the handler run |
| Block the request | Set status/body, then return a completed publisher | The rest of the chain is not called |
| Observe the result | Attach operators to the chain's publisher | Records success, error, or cancel |

Example of blocking a request:

~~~java
@Component
public class MaintenanceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (exchange.getRequest().getPath().value().startsWith("/admin")) {
            exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

A request whose path starts with `/admin` is blocked. The filter sets status 503 and calls `setComplete()` to complete the response. Because `chain.filter` is not called, the later filters and the handler are not executed.

In a real application, the maintenance condition should be based on configuration or a managed system state. For authentication and authorization, prefer Spring Security reactive.

**Do not call `chain.filter(exchange)` twice for the same request.** Calling the chain repeatedly can cause the handler to run multiple times, read the body multiple times, or perform duplicate side effects.

## 4. Logic Before the Chain

You can run logic before the chain directly inside the filter:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String path = exchange.getRequest().getPath().value();
    log.info("Incoming request: {}", path);

    return chain.filter(exchange);
}
~~~

If you want to ensure a side effect happens only when the publisher is subscribed, use `Mono.defer`:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return Mono.defer(() -> {
        log.info("Before chain: {} {}",
            exchange.getRequest().getMethod(),
            exchange.getRequest().getURI().getPath());

        return chain.filter(exchange);
    });
}
~~~

`Mono.defer` postpones the body until subscription. This is useful when creating a timer, logging, or obtaining a value on each execution of the publisher.

### 4.1. Measuring Processing Time

~~~java
return Mono.defer(() -> {
    long startedAt = System.nanoTime();

    return chain.filter(exchange)
        .doFinally(signal -> {
            long elapsedNanos = System.nanoTime() - startedAt;
            log.info("Request finished: signal={}, elapsed={}ms",
                signal, elapsedNanos / 1_000_000);
        });
});
~~~

`System.nanoTime()` is suitable for measuring an interval because it is a monotonic clock; it is not used to get a calendar time. `doFinally` observes the terminal signal, including complete, error, and cancel. You should not subtract `System.currentTimeMillis()` values to measure an exact duration because the system clock can be adjusted.

## 5. Logic After the Chain: Success, Error, and Cancel

With `Mono<Void>`, there are three groups of terminal signals to distinguish:

| Signal | Meaning | Suitable operator |
| --- | --- | --- |
| Complete | The chain completes normally | `doOnSuccess`, `doOnTerminate`, `then` |
| Error | The chain ends with an error | `doOnError`, `onErrorResume`, `doFinally` |
| Cancel | The subscription is cancelled | `doOnCancel`, `doFinally` |

### 5.1. After the Chain Completes Successfully

~~~java
return chain.filter(exchange)
    .doOnSuccess(ignored ->
        log.info("Request completed successfully"));
~~~

`doOnSuccess` runs when the Mono completes successfully. With `Mono<Void>`, the emitted value is `null`; the callback should not dereference the parameter.

### 5.2. When the Chain Emits an Error

~~~java
return chain.filter(exchange)
    .doOnError(error ->
        log.error("Request failed", error));
~~~

`doOnError` only observes the error and lets the error continue propagating to the subscriber. This is usually the right choice when you only need logging/metrics and want WebExceptionHandler or Spring Security to handle the error.

If you use `onErrorResume`, the filter can convert the error into another publisher:

~~~java
return chain.filter(exchange)
    .onErrorResume(IllegalArgumentException.class, error -> {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    });
~~~

Only map errors the filter clearly understands. Do not catch every exception and then return 200 or 400; infrastructure errors and programming bugs need to be handled according to the application's error policy.

### 5.3. When the Client Cancels the Request

A client can close the connection, time out, or cancel the subscription. In that case the chain may receive cancel instead of complete/error.

~~~java
return chain.filter(exchange)
    .doOnCancel(() ->
        log.info("Client cancelled request"));
~~~

Cancellation does not mean a business error. You can record it for observability, but avoid trying to write an error response when the client has already disconnected.

### 5.4. Combining Everything

~~~java
return Mono.defer(() -> {
    long startedAt = System.nanoTime();
    log.info("Before chain");

    return chain.filter(exchange)
        .doOnSuccess(ignored ->
            log.info("Chain completed"))
        .doOnError(error ->
            log.warn("Chain failed", error))
        .doFinally(signal -> {
            long elapsedMs =
                (System.nanoTime() - startedAt) / 1_000_000;
            log.info("After chain: signal={}, elapsed={}ms",
                signal, elapsedMs);
        });
});
~~~

The first log runs before the chain; `doOnSuccess` observes completion; `doOnError` observes errors; `doFinally` runs on complete, error, or cancel.

Do not confuse `doFinally` with a callback that runs only on success. If an action should happen only after success, use `then` or `doOnSuccess`. If you need cleanup regardless of the result, use `doFinally` or a suitable cleanup mechanism.

## 6. Order of Multiple WebFilters: The Request Goes Forward, Callbacks Come Back in Reverse

Suppose there are three filters in the order A, B, C:

~~~text
Request:
A.before
  B.before
    C.before
      Handler
    C.after
  B.after
A.after
~~~

Filters run on the way in following the chain. When the publisher completes and callbacks are attached at each execution layer, the after-chain handling happens as the reactive stack unwinds. Therefore the callback in the innermost filter usually observes the result before the outer filter.

~~~java
@Component
@Order(1)
class FirstFilter implements WebFilter {
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        log.info("A before");
        return chain.filter(exchange)
            .doFinally(signal -> log.info("A after"));
    }
}

@Component
@Order(2)
class SecondFilter implements WebFilter {
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        log.info("B before");
        return chain.filter(exchange)
            .doFinally(signal -> log.info("B after"));
    }
}
~~~

With these two filters, the logs on the way in are A first and then B. When the chain ends, the B callback runs and then A. This is a useful model for understanding tracing, transaction scope, and processing time.

The actual order depends on the configuration and how Spring assembles the filters. Declare the order explicitly when logic depends on order; do not rely on the incidental order in which beans are discovered.

## 7. @Order and Ordered

There are two ways to declare order.

### 7.1. Using @Order

~~~java
@Component
@Order(10)
public class RequestIdWebFilter implements WebFilter {
    // ...
}
~~~

### 7.2. Implementing Ordered

~~~java
@Component
public class AuditWebFilter implements WebFilter, Ordered {
    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
~~~

A smaller order value has higher priority and usually runs earlier on the request path. `Ordered.HIGHEST_PRECEDENCE` is the highest priority value; `Ordered.LOWEST_PRECEDENCE` is the lowest priority value.

If multiple filters have the same order, you should not depend on an unspecified tie-break order in the application configuration. Choose distinct order values when the order matters.

### 7.3. Interaction with Spring Boot and Spring Security

Spring Boot can register internal WebFilters such as observation or Spring Security filters. Some default orders change depending on the Boot version and configuration. The current Spring Boot documentation notes Spring Security's `WebFilterChainProxy` at order -100 in the corresponding configuration.

Do not copy an order number from another project without checking the version and configuration you are using. When a custom filter needs to run before or after Spring Security, identify the goal:

- A request ID/tracing may need to exist before the authentication step so that rejected requests can also be logged.
- Logic that needs the authenticated principal must run after the Security chain.
- CORS preflight needs to be handled according to a CORS configuration compatible with Security.
- A filter that checks permissions should live inside the Spring Security authorization model when possible.

Do not create a manual authenticator in parallel with Spring Security just to place another WebFilter.

## 8. ServerWebExchange: Request, Response, and Attributes

`ServerWebExchange` is the context of one HTTP request-response.

| API | Purpose |
| --- | --- |
| `exchange.getRequest()` | Read the request method, URI, headers, cookies, and body |
| `exchange.getResponse()` | Set the status, headers, and write the response |
| `exchange.getAttributes()` | Store data tied to the current exchange |
| `exchange.getSession()` | Get the WebSession in a reactive way |
| `exchange.getPrincipal()` | Get the current principal in a reactive way |
| `exchange.getLocaleContext()` | Get the locale context |

Attributes are a map attached to one exchange. This is a suitable place to share a request ID or computed data between filters and handlers within the same request.

~~~java
exchange.getAttributes().put("requestId", requestId);
return chain.filter(exchange);
~~~

A later handler or filter can read it:

~~~java
String requestId = exchange.getAttribute("requestId");
~~~

Do not use exchange attributes as a cache shared between requests. Each exchange has its own lifecycle; shared data needs a bean with proper concurrency management and lifecycle.

### 8.1. Exchange Attributes and Reactor Context

| Mechanism | Scope | Suitable for |
| --- | --- | --- |
| Exchange attributes | One ServerWebExchange | Request ID, data that needs to be read directly from the exchange |
| Reactor Context | One reactive subscription chain | Metadata that needs to be passed through operators/subscribers |
| Singleton/service state | Many requests | Shared cache or configuration, must handle concurrency |

Reactor Context is not ThreadLocal. A reactive pipeline can switch threads; use Context or a suitable context propagation mechanism instead of assuming every operator runs on the same thread.

## 9. Modifying the Request Before Passing the Chain

A WebFlux request is designed to be immutable. To change a header/path or create a request wrapper, use the builder of the request and exchange.

~~~java
ServerHttpRequest mutatedRequest = exchange.getRequest()
    .mutate()
    .headers(headers ->
        headers.set("X-Internal-Request", "true"))
    .build();

ServerWebExchange mutatedExchange = exchange.mutate()
    .request(mutatedRequest)
    .build();

return chain.filter(mutatedExchange);
~~~

The next request in the chain sees the internal header. The original request is not changed in place; the filter creates a new exchange wrapping the mutated request.

Use this approach for controlled internal metadata. Do not trust headers sent by the client such as `X-User-Role`, `X-Authenticated`, or `X-Internal-Request`; remove or overwrite sensitive headers at the trust boundary and only create the value after authenticating the source.

If you only need to pass internal data between filters/handlers, exchange attributes are usually simpler than adding a header to the request.

## 10. Adding Response Headers and the Commit Moment

Response headers must be set before the response commits. You can set them directly before calling the chain:

~~~java
exchange.getResponse().getHeaders()
    .set("X-Application", "reactive-demo");

return chain.filter(exchange);
~~~

If you want to register a callback that runs right before commit, use `beforeCommit`:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);
    return Mono.empty();
});

return chain.filter(exchange);
~~~

`beforeCommit` is suitable when a header needs to be set right before the server commits the response. The callback must return a publisher; do not call `block()` inside.

After the response has committed, you cannot change the status or headers that were already sent. A filter can observe the result after the chain, but should not assume every header can still be modified in a post-processing callback.

### 10.1. Response Body and ServerHttpResponseDecorator

If you need to intervene in the response body, you can use `ServerHttpResponseDecorator` to wrap the response and override body-writing methods such as `writeWith` or `writeAndFlushWith`. This is an advanced technique because the body is usually a DataBuffer and it has these requirements:

- Preserve backpressure and do not gather a large stream into RAM.
- Release DataBuffers correctly if you read/write buffers manually.
- Handle both `writeWith` and `writeAndFlushWith` for streaming endpoints.
- Update Content-Length, ETag, or checksum if the content changes.
- Avoid consuming the body before the handler so that the handler no longer has data to read.

If you only need to add a header, status, or log, there is no need to wrap the body. Only use a decorator when the requirement is truly to transform the bytes/body.

## 11. Session and Principal in a WebFilter

WebFlux provides the session and principal through reactive APIs. Do not call block to get them.

Getting the session:

~~~java
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put("lastPath",
            exchange.getRequest().getPath().value());
        return chain.filter(exchange);
    });
~~~

This is an example of storing information in the session. Reading/writing the session is asynchronous; WebFlux's session manager manages storage according to the lifecycle.

Getting the principal:

~~~java
return exchange.getPrincipal()
    .map(principal -> principal.getName())
    .defaultIfEmpty("anonymous")
    .flatMap(name -> {
        exchange.getAttributes().put("principalName", name);
        return chain.filter(exchange);
    });
~~~

This snippet always continues the chain after the principal is resolved; if there is no principal, the anonymous value is used. In a secured application, the principal is usually provided by Spring Security. Do not read the cookie yourself and then conclude that the user is authenticated.

## 12. WebFilter and Spring Security

Spring Security reactive builds security on top of WebFilter. The `SecurityWebFilterChain` chain contains authentication, authorization, exception translation, security context, and other security filter steps.

You should use Spring Security for:

- JWT authentication, OAuth2 Resource Server, or form login.
- Authorization by authority/role.
- SecurityContext management.
- CSRF and CORS with suitable configuration.
- Handling the authentication entry point and access denied.

A custom WebFilter can add a correlation ID, audit metadata, or observe requests. If you need the principal, read it from the security context established by Spring Security and set an appropriate order.

You should not write your own authentication filter by comparing a hard-coded token. That approach easily misses the signature, expiry, issuer, audience, rotation, and authorization policy.

## 13. CORS, Forwarded Headers, and Infrastructure Filters

Some functionality is commonly handled at the WebFilter or web infrastructure layer:

- **CORS:** WebFlux supports CORS and `CorsWebFilter`. When using Spring Security, you need to configure CORS so it is handled in the correct order before the related security steps.
- **Observation/metrics:** a filter or instrumentation records request duration, status, and trace context.
- **Session:** `WebSessionManager` provides the reactive session.
- **Forwarded headers:** when running behind a reverse proxy, the public host/scheme/port can differ from the internal connection. Spring provides `ForwardedHeaderTransformer` to handle forwarded headers at the appropriate stage.

Forwarded headers carry a trust boundary risk. If the application trusts every `X-Forwarded-*` or `Forwarded` header sent by the client, an attacker can spoof the host/scheme and affect links, redirects, or security checks. The proxy at the edge must remove spoofed headers and only forward values created by a trusted proxy.

Do not register multiple mechanisms handling the same functionality if they conflict. Check Spring Boot's auto-configuration before adding a custom filter.

## 14. WebFilter, HandlerFilterFunction, and Servlet Filter

| Mechanism | Platform | Scope |
| --- | --- | --- |
| `WebFilter` | Spring WebFlux WebHandler API | The entire reactive HTTP exchange |
| `HandlerFilterFunction` | WebFlux.fn | RouterFunction/functional routes the filter is attached to |
| `jakarta.servlet.Filter` | Servlet API | Servlet container filter chain |

Use `WebFilter` when you want to apply a common policy across the whole WebFlux application, including annotated controllers and functional endpoints.

Use `HandlerFilterFunction` when you only want to filter a group of functional routes. It receives the ServerRequest and the next handler, then returns a ServerResponse publisher.

Use a Servlet Filter for Servlet/Spring MVC applications. Do not replace a Servlet Filter with a WebFilter or vice versa without considering the web application type and runtime.

In addition:

- `@ControllerAdvice` and `@ExceptionHandler` handle errors at the controller layer.
- `WebExceptionHandler` handles exceptions in the WebHandler chain.
- Spring Security reactive manages authentication/authorization with a dedicated filter chain.

Choosing the right layer keeps logic in the right scope and makes it easier to test.

## 15. Common Mistakes When Implementing WebFilter

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Not returning `chain.filter(exchange)` | The request stops and does not reach the handler | Return the chain's publisher or an intentional blocking response |
| Calling `chain.filter(exchange)` twice | The handler/side effects may run twice | Create the downstream publisher once and compose |
| Calling `subscribe()` in a filter | The request lifecycle is detached from the returned publisher; errors are hard to propagate correctly | Return Mono<Void> and compose operators |
| Calling `block()` to get the session/principal | Blocks the event loop | Use flatMap, then, switchIfEmpty |
| Using doOnSuccess and assuming Mono<Void> has an object | The callback receives null | Only record completion, do not dereference |
| Using doFinally as a success-only callback | Cleanup/log can run on both error and cancel | Distinguish SignalType or use doOnSuccess |
| Using onErrorResume to catch every error | Hides server errors and programming errors | Only map specific exceptions |
| Writing response headers after commit | Headers already sent cannot be changed | Set before the chain or use beforeCommit |
| Reading the request body in a filter without wrapping/replaying | A later handler may have no body left to read | Avoid reading the body; if required, use a decorator/cache properly |
| Writing the response body in a filter without handling DataBuffer | Leaks buffers or breaks backpressure | Use a decorator that follows the contract and release buffers |
| Trusting authentication headers sent by the client | The client can spoof identity/permissions | Use Spring Security and overwrite metadata at the trust boundary |
| Using exchange attributes as a global cache | Data scope gets mixed between requests | Use a store with concurrency management for shared data |
| Not declaring order when there is a dependency | Filter order is unclear | Use @Order/Ordered and check the security order |
| Filter logs the entire body/header | May leak tokens, cookies, PII and increase load | Log minimal metadata, mask data |
| Treating cancel as a server error | Wrong metrics/logs and may try to write a response after the client disconnected | Record SignalType.CANCEL separately |
| Putting domain logic into a global filter | Hard to understand, hard to test, and applied too broadly | Put business logic into the handler/service |
| Using WebFilter in place of Spring Security | Lacks a complete authentication/authorization mechanism | Use SecurityWebFilterChain |
| Ignoring requests that do not match a route | The filter still runs but may be misread as the handler having processed it | Separate filter chain observation from endpoint logic |

## 16. A Complete Java 17+ Spring Boot WebFlux Demo

The example builds a WebFilter that creates a trace ID for each request, puts the ID into exchange attributes, adds the ID to the response header before commit, and records the success/error/cancel of the filter chain.

### 16.1. Project Structure

~~~text
webfilter-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      TraceWebFilter.java
      HelloController.java
    test/java/demo/
      TraceWebFilterTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages the versions of Spring Framework, Reactor, and compatible dependencies. Do not add your own Reactor version unless there is a specific compatibility requirement.

### 16.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 16.4. TraceWebFilter.java

~~~java
package demo;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class TraceWebFilter implements WebFilter {
    public static final String TRACE_ID_ATTRIBUTE =
        TraceWebFilter.class.getName() + ".traceId";

    private static final Logger log =
        LoggerFactory.getLogger(TraceWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        final String traceId = UUID.randomUUID().toString();

        // Before the chain: share the trace ID with the handler in this exchange.
        exchange.getAttributes().put(TRACE_ID_ATTRIBUTE, traceId);

        // Register the header before the response commits.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                .set("X-Trace-Id", traceId);
            return Mono.empty();
        });

        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            log.info("Before chain: {} {}",
                exchange.getRequest().getMethod(),
                exchange.getRequest().getURI().getPath());

            return chain.filter(exchange)
                .doOnSuccess(ignored ->
                    log.info("Chain completed: {}", traceId))
                .doOnError(error ->
                    log.warn("Chain failed: {}", traceId, error))
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt) / 1_000_000;
                    log.info("After chain: traceId={}, signal={}, elapsed={}ms",
                        traceId, signal, elapsedMs);
                });
        });
    }
}
~~~

The filter creates a UUID for each exchange. The attribute lets the controller read the same ID; `beforeCommit` adds the ID to the response header before sending. `doFinally` records complete, error, and cancel. The example does not read the body and does not hold state shared between requests.

### 16.5. HelloController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public Mono<String> hello(ServerWebExchange exchange) {
        String traceId = exchange.getAttribute(
            TraceWebFilter.TRACE_ID_ATTRIBUTE);

        return Mono.just("hello " + traceId);
    }
}
~~~

The controller reads the trace ID that the filter put into the exchange attributes. The body and the response header contain the same ID.

### 16.6. TraceWebFilterTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TraceWebFilterTest {
    @Autowired
    WebTestClient client;

    @Test
    void filterAddsTraceIdToExchangeAndResponse() {
        EntityExchangeResult<String> result = client.get()
            .uri("/hello")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody(String.class)
            .returnResult();

        String traceId =
            result.getResponseHeaders().getFirst("X-Trace-Id");

        assertNotNull(traceId);
        assertEquals("hello " + traceId, result.getResponseBody());
    }

    @Test
    void filterAlsoWrapsNotFoundResponse() {
        client.get()
            .uri("/route-does-not-exist")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().exists("X-Trace-Id");
    }
}
~~~

The first test verifies that the filter runs before the handler, passes the trace ID through exchange attributes, and adds the same value to the response header. The second test verifies that the filter still wraps a request whose route cannot be found.

### 16.7. Running the Application and Checking

Run in the project directory:

~~~bash
./gradlew bootRun
~~~

Or:

~~~bash
gradle bootRun
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/route-does-not-exist
~~~

The first response looks like this:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 5e4e5a6f-6e90-4b25-8d2f-1f4d4f9e5a21
Content-Type: text/plain;charset=UTF-8

hello 5e4e5a6f-6e90-4b25-8d2f-1f4d4f9e5a21
~~~

The trace ID above is only an illustrative value; each real request creates a new UUID. A request to a non-existent route still passes through the WebFilter and receives the trace ID header if the response has not committed earlier.

Run the tests:

~~~bash
./gradlew test
~~~

The two tests focus on the filter's contract: data is added before the handler runs, and the response header is set before commit. The demo needs no Thread.sleep, does not call block, and does not subscribe itself.

## 17. Testing a WebFilter in Isolation

If you do not need to start a Spring Boot server, you can test a WebFilter with a WebTestClient bound to a WebHandler or a mock exchange. Another way is to use Spring's MockServerWebExchange to create a request, then call the filter directly with a fake chain.

Example idea for testing the chain:

~~~java
MockServerWebExchange exchange =
    MockServerWebExchange.from(
        MockServerHttpRequest.get("/hello").build());

WebFilterChain chain = currentExchange ->
    currentExchange.getResponse().setComplete();

StepVerifier.create(filter.filter(exchange, chain))
    .verifyComplete();
~~~

This is a snippet that needs imports from `org.springframework.mock.web.server`, `org.springframework.mock.http.server.reactive`, and `reactor.test.StepVerifier`. It helps test a filter without a controller. If the filter uses `beforeCommit`, the test must trigger the response commit or write the response to verify that the callback ran; just calling `filter()` and verifying complete does not necessarily run the commit callback.

Scenarios worth testing:

- The filter calls the chain exactly once.
- When the filter blocks a request, the rest of the chain is not called.
- The request ID/attributes are passed to the handler.
- The header is added before commit.
- The error is observed and either continues propagating or is mapped correctly.
- Cancellation triggers the appropriate cleanup.
- The configured filter order is verified when there is an order dependency.

## 18. WebFilter Design Checklist

Before implementing, answer these questions:

1. Does the filter need to run for the entire WebFlux request or only a group of routes?
2. Does the logic need to run before the chain, after success, after error, or also on cancel?
3. Does the filter call the chain exactly once and return the correct publisher?
4. Do you need exchange attributes, Reactor Context, or a shared service?
5. Does the request/response need to be mutated; when is the commit moment?
6. Does the filter accidentally read/consume the body before the handler?
7. Is there any blocking I/O, block, or manual subscribe?
8. Do you need @Order/Ordered; what is the order relative to Spring Security/CORS/observation?
9. Is the error propagated or mapped; has the response committed?
10. Is cancellation distinguished from error?
11. Do the logs/metrics expose tokens, cookies, body, or personal data?
12. Have you tested successful requests, errors, unmatched routes, and cancel?

| Need | Solution |
| --- | --- |
| Log before the request continues | Logic before `chain.filter` or `Mono.defer` |
| Log after success | `doOnSuccess` or `then` |
| Log on error | `doOnError` |
| Cleanup on every terminal signal | `doFinally` |
| Block a request | Set the status and return `response.setComplete()` |
| Pass the request ID to the handler | `exchange.getAttributes()` |
| Add a response header | `getResponse().getHeaders()` before commit or `beforeCommit` |
| Change a request header | `request.mutate()` then `exchange.mutate()` |
| Read the session | `exchange.getSession()` |
| Read the principal | `exchange.getPrincipal()` |
| Authentication/authorization | Spring Security reactive |
| A dedicated filter for WebFlux.fn | `HandlerFilterFunction` |
| Testing | WebTestClient, MockServerWebExchange, StepVerifier |

## 19. Self-Check Questions with Answers

**Question 1.** What method does WebFilter have and what type does it return?

**Answer:** `filter(ServerWebExchange, WebFilterChain)`, returning `Mono<Void>` that represents the completion of request/response processing.

**Question 2.** What does `chain.filter(exchange)` do?

**Answer:** It passes the request to the next filter or the final WebHandler. If the chain is not called, the filter can block the request with its own response.

**Question 3.** Which operator do you use to log after the chain ends, whether complete, error, or cancel?

**Answer:** `doFinally`, because it receives a `SignalType` for the terminal signals.

**Question 4.** Can `doOnSuccess` on a `Mono<Void>` receive a null value?

**Answer:** Yes. A Mono<Void> completes successfully without emitting an object; the callback must not dereference the parameter.

**Question 5.** Should you call `subscribe()` inside a WebFilter?

**Answer:** No. Return and compose the publisher so WebFlux manages the lifecycle and propagates errors/cancel correctly.

**Question 6.** Filter A has order 1, filter B has order 2. In what order does the request go in?

**Answer:** A first and then B. When the chain unwinds, B's post-processing callback usually runs before A's callback.

**Question 7.** Which API do you use to add a response header right before commit?

**Answer:** `exchange.getResponse().beforeCommit(...)`. The callback must return Mono<Void> and must not block.

**Question 8.** Can exchange attributes be used as a cache across all requests?

**Answer:** No. Attributes belong to one ServerWebExchange. A shared cache needs a separate component with concurrency and lifecycle management.

**Question 9.** If the client cancels the request, should the filter treat that as a server error?

**Answer:** Not by default. Cancel is a subscription-cancellation signal; record it separately with doOnCancel or doFinally.

**Question 10.** Should you use WebFilter or HandlerFilterFunction for a group of WebFlux.fn routes?

**Answer:** HandlerFilterFunction is suitable if you only want to apply it to the router/functional routes the filter is attached to. WebFilter applies at the WebHandler layer and has a broader scope.

**Question 11.** Should you use a WebFilter that checks a JWT itself against a hard-coded string?

**Answer:** No. Use Spring Security reactive for authentication, verifying the signature, issuer, audience, expiry, and authorization.

**Question 12.** Why shouldn't a filter read the entire request body just to log it?

**Answer:** The body is a stream that may be consumed only once; reading it early can leave the later handler with no data, increase RAM, and break backpressure. Only wrap/cache the body when there is a clear requirement and you understand how to manage DataBuffers.

## 20. Key Takeaways and Official Documentation

- `WebFilter` is an interception layer in the WebFlux WebHandler chain, and can apply logic before and after the remaining processing.
- `WebFilterChain.filter(exchange)` passes the request on and returns `Mono<Void>`.
- Use `doOnSuccess`, `doOnError`, and `doFinally` to distinguish success, error, and cancel.
- A smaller filter order runs earlier on the request path; post-processing callbacks usually unwind in the reverse direction.
- Spring Boot automatically registers WebFilter beans; use `@Order` or `Ordered` when the order matters.
- `ServerWebExchange` provides the request, response, attributes, session, and principal.
- Add headers before the response commits; after commit, the sent headers/status cannot be changed.
- Do not block, do not subscribe manually, do not call the chain multiple times.
- Use Spring Security reactive for authentication/authorization; use HandlerFilterFunction for the functional route scope.
- Reading the body or wrapping DataBuffer in a filter requires careful backpressure and lifecycle management.

Official documentation:

1. [Spring Framework Reference — Reactive Core, Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): WebFilter in the WebHandler chain, bean registration, filter order, CORS, and exception handling.
2. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): automatic detection of WebFilter beans and the filter order configured by Boot.
3. [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): the filter(ServerWebExchange, WebFilterChain) contract.
4. [Spring Framework Javadoc — WebFilterChain](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html): delegating to the next filter.
5. [Spring Framework Javadoc — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request, response, attributes, session, and principal.
6. [Spring Framework Javadoc — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): response headers, commit, and body writing.
7. [Spring Security Reference — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): SecurityWebFilterChain, authentication, and authorization on WebFlux.
8. [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): doOnError, onErrorResume, and terminal signals.
