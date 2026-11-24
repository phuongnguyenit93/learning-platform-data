# Composing `chain.filter` Instead of Calling `subscribe()` Yourself in Spring WebFlux

## 1. The Problem: A Filter Must Stay Within the Request Lifecycle

`WebFilter` is Spring WebFlux's extension point for handling logic common to the before and after of the rest of an HTTP request. Common examples are correlation ID, logging, timing, CORS, authentication, session, and policies applied to many endpoints.

A `WebFilter` receives a `ServerWebExchange` together with a `WebFilterChain` and returns `Mono<Void>`:

```java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
```

The important point is the return value: `Mono<Void>` represents **the entire processing of the request continuing through the next filter and the final handler**. The filter needs to compose this publisher and return it to Spring.

A very common mistake is calling:

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

This creates a detached subscription. The filter returns `Mono.empty()` as soon as the separate subscription is started, so the framework may consider the filter finished while the handler is still running on another signal path. Downstream errors are no longer propagated correctly through the original pipeline; cancellation from the client is also no longer firmly tied to the detached work; the response may be committed or ended early.

The principle to remember:

> **In a `WebFilter`, call `chain.filter(exchange)` exactly once, compose the needed operators, and return that publisher. Do not call `subscribe()` or `block()` yourself.**

This lesson goes deep into how the filter chain works, before/after order, handling errors and cancellation, using `WebSession` asynchronously, and how to test to detect a subscription detached from the request.

## 2. How Does the WebFlux Filter Chain Work?

Spring WebFlux builds a chain consisting of multiple `WebFilter`s and a target `WebHandler`. Each filter can do work before passing the request on, or attach operators to observe the processing behind it.

```text
HTTP request
     |
     v
WebFilter A
  before logic
     |
     | chain.filter(exchange)
     v
WebFilter B
  before logic
     |
     | chain.filter(exchange)
     v
WebFilter C
  before logic
     |
     | chain.filter(exchange)
     v
DispatcherHandler / WebHandler
  controller or functional endpoint
     |
     v
HTTP response
     |
     v
WebFilter C after logic
     |
     v
WebFilter B after logic
     |
     v
WebFilter A after logic
     |
     v
Response pipeline completes
```

Filters are called in the order of the chain. When filter A calls `chain.filter`, control passes to filter B. When the downstream publisher completes, the callbacks attached in A can run as the signal returns through the pipeline.

This is the "wrap" model:

```java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    // Before: runs in the current filter.

    return chain.filter(exchange)
            .doOnSuccess(ignored -> {
                // After the downstream part completes.
            })
            .doOnError(error -> {
                // Observe errors from downstream.
            })
            .doFinally(signal -> {
                // Observe complete, error, or cancel.
            });
}
```

`chain.filter(exchange)` is not a call that runs an independent request by itself. It returns a publisher representing the rest of the chain. Spring manages the subscription at the request level; returning the publisher lets the framework control demand, terminal signals, and cancellation.

### One Request, One Composed Pipeline

Suppose there are three filters:

- Filter A adds a request ID.
- Filter B reads the session and increments the visit count.
- Filter C records the processing time.

Each filter returns the downstream publisher wrapped with its own behavior. The result is a single pipeline for the request, instead of three independent subscriptions.

If a filter needs to reject a request, it can skip calling `chain.filter` and complete the response itself. For example:

```java
if (!allowed) {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
}

return chain.filter(exchange);
```

This is an intentional short-circuit: the request is blocked, so it does not reach the later filters/handler. In a real application, authentication and authorization should integrate Spring Security; the example above only illustrates the mechanism of stopping the chain.

## 3. Why Is `subscribe()` in a Filter Wrong?

### 3.1. Two Independent Subscriptions

The wrong code:

```java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    chain.filter(exchange).subscribe();

    return Mono.empty();
}
```

There are two different publishers:

1. The publisher subscribed manually inside the filter.
2. The `Mono.empty()` that the framework receives as the filter's result.

The framework only sees the second publisher. The first publisher runs outside the lifecycle the framework is managing.

Consequences:

- **Wrong response lifecycle**: the filter may report completion before the handler writes the response.
- **Detached errors**: an exception from the handler does not necessarily go through the pipeline the framework is waiting on.
- **Cancellation loses its link**: a client disconnect may cancel the returned pipeline, but the self-created subscription continues.
- **Resources held for long**: an HTTP client, database query, session, or stream may keep running after the request has ended.
- **Hard to test**: the test sees the filter complete but background work is still running.
- **Hard to manage context**: Reactor Context and observation hooks may no longer be on the expected subscription.

### 3.2. The Right Way: Compose Then Return

```java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return chain.filter(exchange)
            .doOnError(error ->
                    log.warn("Request failed", error))
            .doFinally(signal ->
                    log.debug("Request finished: {}", signal));
}
```

`doOnError` only observes the error and does not turn the error into success. The error continues downstream per the contract. `doFinally` observes the end signal and does not replace the publisher.

If you need to run an asynchronous task before entering the handler:

```java
return loadPolicy(exchange)
        .flatMap(policy -> {
            exchange.getAttributes().put("policy", policy);
            return chain.filter(exchange);
        });
```

If you need to run an asynchronous task after the handler:

```java
return chain.filter(exchange)
        .then(writeAuditRecord(exchange));
```

In both cases the publisher is joined with `flatMap` or `then`; no extra subscription is created.

### 3.3. Do Not Use `block()` to Wait for the Chain

The following is also wrong:

```java
chain.filter(exchange).block();
return Mono.empty();
```

`block()` waits synchronously on the thread executing the filter. If that thread is a Reactor Netty event loop, it can block the processing of other connections and break the non-blocking model. Instead of waiting with the Java call stack, express the order of work in the reactive chain.

## 4. The `before → chain → after` Pattern

A filter usually has three phases:

1. Perform logic before forwarding.
2. Delegate to the rest with `chain.filter(exchange)`.
3. Attach handling behavior after the downstream completes.

```java
@Component
public class TimingWebFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TimingWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();

        log.debug("before request {}", exchange.getLogPrefix());

        return chain.filter(exchange)
                .doOnSuccess(ignored ->
                        log.debug("downstream completed"))
                .doOnError(error ->
                        log.warn("downstream failed", error))
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);

                    log.info(
                            "request signal={} durationMs={}",
                            signal, elapsedMs);
                });
    }
}
```

The necessary imports:

```java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;
```

This is a filter snippet that can compile in a Spring WebFlux application that already has the corresponding dependencies.

### `doOnSuccess`, `doOnError`, and `doFinally`

`chain.filter` returns `Mono<Void>`:

- `doOnSuccess` is called when the downstream completes successfully; the callback value is `null` because Mono<Void> does not emit a value.
- `doOnError` is called if an error passes through that operator position.
- `doFinally` receives `SignalType.ON_COMPLETE`, `ON_ERROR`, or `CANCEL`.

Cancellation is not complete. If the client disconnects, the filter can observe `CANCEL`; you must not log "request success" just because a cleanup callback ran.

`doFinally` is called after the terminal/cancel signal is propagated through the operator position. Use it for metrics and logging, not to change the response body/header at a time when the response may have already committed.

### Use `Mono.defer` When You Want to Postpone a Side Effect Before the Chain

If you want an action before the request to run only when the publisher is subscribed:

```java
return Mono.defer(() -> {
    log.debug("filter subscribed");
    return chain.filter(exchange);
});
```

`Mono.defer` calls the supplier when the subscription starts. In a normal `WebFilter`, the filter method is called by the framework during request processing; not every line before `return` needs to be wrapped in `defer`. Use `defer` when you need to ensure a side effect or the creation of a publisher only happens per subscription, especially when the publisher may be reused.

## 5. Execution Sequence with Multiple Filters

WebFlux automatically detects `WebFilter` beans in the application context. You can specify the order with `@Order` or by implementing `Ordered`.

A smaller order value has higher precedence and is called earlier. The filter that goes in first wraps the processing of the filter that goes in later; the after-chain callbacks usually happen in the reverse direction.

Example:

```java
@Component
@Order(1)
public class FirstWebFilter implements WebFilter {
    // ...
}

@Component
@Order(2)
public class SecondWebFilter implements WebFilter {
    // ...
}
```

Conceptual sequence:

```text
First.before
  Second.before
    Handler
  Second.after
First.after
```

Do not rely on the order in which beans are discovered at random. If logging, security, CORS, session, or tracing depend on each other, declare the order explicitly and check the application's actual order.

### Interaction with Spring Security

Spring Security WebFlux also participates in the filter chain through `WebFilterChainProxy`. The order of the security chain has security significance. Do not place a custom filter before or after security arbitrarily:

- A filter that needs the authenticated principal information should run after the security authentication step.
- A filter that creates a request ID/log metadata can run earlier, as long as it does not treat a header sent by the client as a trustworthy identity.
- CORS preflight needs to be handled in the right order with security.
- Authorization should use Spring Security, not rely only on a header condition in a custom filter.

The specific order depends on the application's Spring Boot/Security configuration. Identify clearly whether the filter is being attached to the server chain or the security chain.

## 6. Changing the Request or Exchange While Keeping the Pipeline

`ServerWebExchange` is the abstraction for the current request-response. If you need to add an internal header or change the request before delegating, create a mutated request/exchange and pass that copy into `chain.filter`.

```java
ServerHttpRequest mutatedRequest = exchange.getRequest()
        .mutate()
        .header("X-Internal-Request", "true")
        .build();

ServerWebExchange mutatedExchange = exchange.mutate()
        .request(mutatedRequest)
        .build();

return chain.filter(mutatedExchange);
```

The main imports:

```java
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
```

This is an example of mutating the request at the boundary. Do not directly modify immutable structures such as the original request headers. Do not overwrite a header sent by the client without a clear policy; internal headers need to be created at the trust boundary.

### Use Request Attributes for Request-Scoped Internal Data

If you only need to share data between filters and handlers in the same exchange, you can use attributes:

```java
exchange.getAttributes().put("requestId", requestId);

return chain.filter(exchange);
```

A controller or handler can read it:

```java
String requestId = exchange.getAttribute("requestId");
```

Request attributes belong to one exchange; they are not the session and do not exist across different HTTP requests. Do not use a static map or singleton map to hold request data because it easily causes leaks, contention, and holding objects for too long.

### Adding a Response Header Before the Response Commits

A header can be set before delegating:

```java
exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);

return chain.filter(exchange);
```

If you need to act right before the response is committed, use the `beforeCommit` callback:

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Processed-By", "webflux");
    return Mono.empty();
});

return chain.filter(exchange);
```

Do not wait for `chain.filter` to complete and then change the header in `doFinally`: the response may already be committed and the header can no longer be changed. `beforeCommit` registers a callback to run before the commit moment.

## 7. Using `WebSession` Asynchronously Inside a Filter

`ServerWebExchange.getSession()` returns `Mono<WebSession>`. This is a reactive operation, so it must be composed into the pipeline before delegating.

### 7.1. Reading and Updating the Session

```java
@Component
@Order(2)
public class VisitCounterWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (!exchange.getRequest().getPath().value().equals("/session")) {
            return chain.filter(exchange);
        }

        return exchange.getSession()
                .flatMap(session -> {
                    Integer current = session.getAttribute("visits");
                    int next = current == null ? 1 : current + 1;

                    session.getAttributes().put("visits", next);

                    return chain.filter(exchange);
                });
    }
}
```

This is the complete filter for the example. How it works:

1. A request that is not `/session` continues immediately.
2. A `/session` request gets the `WebSession` through a publisher.
3. When the session is ready, the filter reads the current visit count.
4. The filter updates the session attribute.
5. The filter delegates to the rest with `chain.filter(exchange)`.

Do not write:

```java
exchange.getSession().subscribe(session -> {
    session.getAttributes().put("visits", 1);
});

return chain.filter(exchange);
```

In the wrong snippet, the chain may run before the session is read/updated. In addition, the error of getting the session is detached from the request pipeline and cancellation is not linked correctly.

### 7.2. When Is the Session Actually Created and Saved?

You need to distinguish three things:

- `exchange.getSession()` provides a publisher to get the current session or create a new session object when needed; just calling this method **does not automatically start the session**.
- Calling `session.getAttributes().put(...)` starts the session implicitly; calling `session.start()` can also start it explicitly.
- Spring automatically calls `WebSession.save()` right before the response commits. A typical application does not need to call `save()` itself.

Therefore, in the filter above, adding the attribute is composed before `chain.filter`; WebFlux handles saving the session according to the response lifecycle. There is no need for `session.save().subscribe()` or `.block()`.

`WebSession` by default uses an in-memory store of the application. If you need a session shared across multiple instances or persisted across restarts, configure a suitable session store (for example Spring Session with Redis). Do not treat an in-memory session as a durable data store.

### 7.3. Session and Request Attributes Are Not the Same

| Where stored | Lifetime scope | Example |
|---|---|---|
| `exchange.getAttributes()` | One HTTP exchange | request ID, route metadata |
| `WebSession.getAttributes()` | Many requests belonging to the same session | UI choices, a small shopping cart |
| Reactor Context | One reactive subscription | tracing/security context |
| External database/cache | Per the storage policy | long-lived business data |

Do not store important business data only in the session. A session can expire, be invalidated, or not be shared between nodes if the store configuration is unsuitable.

### 7.4. Invalidating and Changing the Session

Operations such as `session.invalidate()` and `session.changeSessionId()` return publishers. They must be composed:

```java
return exchange.getSession()
        .flatMap(WebSession::invalidate)
        .then(chain.filter(exchange));
```

This is an illustrative snippet for when you need to invalidate and then continue the chain. In a real logout endpoint, you usually need to delete the session and return a clear logout response; if a later filter/handler accesses the session, a new session may be created. Design the logout flow according to the proper security contract.

After successful authentication, changing the session ID to protect against session fixation can be expressed as:

```java
return exchange.getSession()
        .flatMap(session -> session.changeSessionId())
        .then(chain.filter(exchange));
```

This is only an API composition example. Changing the session ID should be placed in a suitable authentication flow or left to Spring Security to manage session fixation protection, not added arbitrarily as a filter.

### 7.5. Avoid Unsafe Session Updates with Concurrent Requests

Two concurrent requests sharing one session can both read `visits=4`, both compute `5`, and both write `5`. This is a lost update. A session map does not turn a read-modify-write into an atomic operation.

If you need an accurate counter, use an atomic mechanism in a suitable store or a service that keeps state with synchronization. A session suits a small amount of per-user state; it is not a transactional database.

## 8. How Do Errors and Cancellation Propagate Through the Filter Chain?

Because the filter returns the downstream publisher, errors can be observed and handled with reactive operators.

### Only Log, Keep the Error As-Is

```java
return chain.filter(exchange)
        .doOnError(error ->
                log.warn("Request pipeline failed", error));
```

`doOnError` does not recover from the error. The downstream subscriber still receives `onError`.

### Converting an Error into a Response at the Boundary

```java
return chain.filter(exchange)
        .onErrorResume(DomainException.class, error -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.CONFLICT);
            return exchange.getResponse().setComplete();
        });
```

This is an illustrative snippet. Only handle exception types for which the filter truly owns the mapping policy. Do not catch every `Throwable` and then return 200 or 400; that hides server errors and bugs.

If the response has already committed, the filter cannot change the status/body in the usual way. You need to handle the error before the response commits or use appropriate error handling in the framework.

### Cancellation

If the client disconnects, times out, or an upstream subscriber cancels the request, cancellation is propagated back through the composed publisher. `doFinally` can receive `SignalType.CANCEL`.

This is a big benefit of `return chain.filter(exchange)`: cancellation belongs to the same pipeline. If the filter calls its own `.subscribe()`, the request pipeline no longer owns that work.

Cancellation is still a cancel request. A blocking library or remote server may keep processing physically if it does not support cancellation; a filter cannot guarantee stopping a task outside the client/driver contract.

### Do Not Call the Chain Multiple Times

Do not write:

```java
return chain.filter(exchange)
        .then(chain.filter(exchange));
```

This can call the downstream twice and cause repeated side effects: database writes, sending emails, creating orders, or consuming the body multiple times. Each request usually needs to delegate once. If you want to run auxiliary work after the downstream, compose the auxiliary work with `then(...)`, do not call the chain again.

## 9. Distinguishing `WebFilter`, `HandlerFilterFunction`, and WebClient's Filter

The name "filter" appears in many different layers:

| Type | Where does it run? | Chain API |
|---|---|---|
| `WebFilter` | WebFlux server, wraps the entire web handler chain | `WebFilterChain.filter(exchange)` |
| `HandlerFilterFunction` | Functional endpoint/WebFlux.fn, wraps the route handler | `next.handle(request)` |
| `ExchangeFilterFunction` | Outbound `WebClient` request/response | `next.exchange(request)` |
| Spring Security `WebFilter` | Server security chain | Security filter chain |

These APIs look similar because they all use composition, but the request/response types and scope differ. Do not use `WebFilterChain` to handle an outbound `WebClient`; do not call `next.exchange` in a server `WebFilter`.

### `HandlerFilterFunction`

With functional endpoints, the router can attach a filter to routes:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> logFilter =
        (request, next) -> {
            log.info("path={}", request.path());
            return next.handle(request)
                    .doOnError(error ->
                            log.warn("handler failed", error));
        };
```

`next.handle(request)` returns `Mono<ServerResponse>`. You also need to return the publisher and not subscribe yourself.

### `ExchangeFilterFunction`

With `WebClient`:

```java
ExchangeFilterFunction clientLogFilter =
        (request, next) -> next.exchange(request)
                .doOnNext(response ->
                        log.debug("status={}", response.statusCode()));
```

This is an outbound client filter. It observes the HTTP response from the service the application calls; it is not a filter for the request coming into the server.

## 10. A Runnable Java 17+ Project: Filter Chain, Request ID, and Session Counter

The example uses Spring Boot 3.3.5, Java 17, and Maven. The application has:

- `RequestIdWebFilter`: creates an ID for the request, sets the response header and the exchange attribute.
- `VisitCounterWebFilter`: updates `WebSession` through `flatMap` and only then calls the chain.
- `DemoController`: returns the request ID or the session visit count.
- `WebTestClient` tests: verify the filters are composed and the session cookie is maintained across two requests.
- A `StepVerifier` test: confirms cancellation goes through the filter's publisher.

### 10.1. Project Structure

```text
webflux-filter-chain/
├── pom.xml
└── src/
    ├── main/java/edu/demo/filter/
    │   ├── FilterApplication.java
    │   ├── RequestIdWebFilter.java
    │   ├── VisitCounterWebFilter.java
    │   └── DemoController.java
    └── test/java/edu/demo/filter/
        └── FilterChainTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-filter-chain</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 10.3. `FilterApplication.java`

```java
package edu.demo.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterApplication.class, args);
    }
}
```

### 10.4. `RequestIdWebFilter.java`

```java
package edu.demo.filter;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(1)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
            RequestIdWebFilter.class.getName() + ".requestId";

    private static final Logger log =
            LoggerFactory.getLogger(RequestIdWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(
                REQUEST_ID_ATTRIBUTE, requestId);

        exchange.getResponse().getHeaders().set(
                "X-Request-Id", requestId);

        long startedAt = System.nanoTime();

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn(
                                "requestId={} failed",
                                requestId,
                                error))
                .doFinally(signal -> {
                    long elapsedMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                            "requestId={} signal={} durationMs={}",
                            requestId,
                            signal,
                            elapsedMs);
                });
    }
}
```

The filter creates a correlation ID on the server side and stores it in the exchange attributes and the response header. The example does not trust an arbitrary ID from the client as identity. In production, you can accept a correlation ID that a gateway has authenticated or create a new ID according to the logging policy.

### 10.5. `VisitCounterWebFilter.java`

```java
package edu.demo.filter;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(2)
public class VisitCounterWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (!exchange.getRequest().getPath().value().equals("/session")) {
            return chain.filter(exchange);
        }

        return exchange.getSession()
                .flatMap(session -> {
                    Integer current = session.getAttribute("visits");
                    int next = current == null ? 1 : current + 1;

                    session.getAttributes().put("visits", next);

                    return chain.filter(exchange);
                });
    }
}
```

The filter only reads the session for the `/session` endpoint. `flatMap` ensures the rest of the chain runs after the session is obtained and updated.

### 10.6. `DemoController.java`

```java
package edu.demo.filter;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/chain")
    public Mono<Map<String, String>> chain(ServerWebExchange exchange) {
        String requestId = exchange.getAttribute(
                RequestIdWebFilter.REQUEST_ID_ATTRIBUTE);

        return Mono.just(Map.of("requestId", requestId));
    }

    @GetMapping("/session")
    public Mono<Map<String, Integer>> session(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    Integer visits = session.getAttribute("visits");
                    return Map.of("visits", visits == null ? 0 : visits);
                });
    }
}
```

The controller reads the same exchange and the same WebSession that the filter has processed. There is no need to create a manual subscription in the controller.

### 10.7. `FilterChainTest.java`

```java
package edu.demo.filter;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockServerHttpRequest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.http.ResponseCookie;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import org.springframework.web.server.WebFilter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterChainTest {

    @Autowired
    WebTestClient client;

    @Test
    void filterComposesWithEndpointAndAddsRequestId() {
        client.get()
                .uri("/chain")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.requestId").exists();
    }

    @Test
    void sessionIsSharedAcrossRequestsWithSameCookie() {
        EntityExchangeResult<byte[]> first = client.get()
                .uri("/session")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(1)
                .returnResult();

        ResponseCookie sessionCookie =
                first.getResponseCookies().getFirst("SESSION");

        assertNotNull(sessionCookie);

        client.get()
                .uri("/session")
                .cookie("SESSION", sessionCookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(2);
    }

    @Test
    void cancellationFlowsThroughFilterPublisher() {
        AtomicReference<SignalType> finalSignal =
                new AtomicReference<>();

        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/never").build());

        WebFilter filter = (currentExchange, chain) ->
                chain.filter(currentExchange)
                        .doFinally(finalSignal::set);

        StepVerifier.create(
                        filter.filter(exchange, currentExchange ->
                                Mono.never()))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

### 10.8. Running the Application and Testing

In the directory containing `pom.xml`:

```bash
mvn test
```

When the dependencies can be downloaded and the assertions are correct, the project has **3 tests**:

1. The filter creates a request ID, the handler receives the exchange attribute, and the response has the corresponding header.
2. The session counter increases from 1 to 2 when the client sends back the same `SESSION` cookie.
3. Cancellation is observed as `SignalType.CANCEL` through the publisher returned from the filter.

Start the application:

```bash
mvn spring-boot:run
```

Call the endpoint that has a request ID:

```bash
curl -i http://localhost:8080/chain
```

The response has a header similar to:

```http
HTTP/1.1 200 OK
X-Request-Id: 4c6d...
Content-Type: application/json

{"requestId":"4c6d..."}
```

The actual UUID value changes per request.

Call the session endpoint the first time:

```bash
curl -i -c cookies.txt http://localhost:8080/session
```

Response body:

```json
{"visits":1}
```

Call again with the saved cookie:

```bash
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/session
```

Response body:

```json
{"visits":2}
```

The example uses the default in-memory WebSession store, so session data only exists for the lifetime of the application/that store. Do not use a session counter as transactional data that needs accuracy under concurrent requests.

The tests and commands above are instructions for running independently. Only confirm that tests PASS after executing `mvn test` in a real environment; the content of this lesson does not claim that Maven has been run.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| `chain.filter(exchange).subscribe()` | The subscription is detached from the request | Return the composed publisher |
| Calling `.block()` in a filter | Blocks the event loop, breaks non-blocking | Use `flatMap`, `then`, `onErrorResume` |
| Calling `chain.filter` twice | The handler runs repeatedly, side effects repeat | Delegate exactly once |
| `exchange.getSession().subscribe(...)` | The chain runs before the session is ready | `getSession().flatMap(session -> chain.filter(...))` |
| Creating an auxiliary `Mono` but not joining it into the return | The task is not managed by the framework | Join with `then`/`flatMap` |
| Writing a header in `doFinally` | The response may have already committed | Write before the chain or use `beforeCommit` |
| Treating cancel as complete | The request status is logged wrongly | Distinguish `ON_COMPLETE`, `ON_ERROR`, `CANCEL` |
| Using request attributes for data across many requests | The data disappears on the next request | Use `WebSession` or a suitable store |
| Using the session as a database | Lost update, data loss on expire/restart | Use a transactional repository/store |
| Not setting the filter order | Behavior depends on an unclear order | Use `@Order`/`Ordered` and test |
| A custom filter authenticating by itself via a header | Identity is easy to spoof | Use Spring Security/WebFlux Security |
| Swallowing errors with an overly broad `onErrorResume` | Hides server errors and bugs | Only handle exceptions with a clear policy |

## 12. Checklist When Writing a `WebFilter`

Before putting a filter into the application:

1. Does the filter return the `Mono<Void>` of `chain.filter(exchange)`?
2. Does it call `chain.filter` exactly once for a delegated request?
3. Is there a hidden `subscribe()` or `block()` in the filter/helper?
4. Has the asynchronous task before the chain been joined with `flatMap`/`then`?
5. Has the task after the chain been joined with `then`/a suitable operator?
6. Does the error continue propagating through the pipeline or is it handled intentionally?
7. Can cancellation propagate upstream?
8. Is the response header set before commit?
9. Is the session obtained/updated in the same chain?
10. Is the filter order declared clearly and compatible with Spring Security?
11. Are request attributes mistakenly used for state across many requests?
12. Are complete, error, cancel, session cookie, and short-circuit tested?
13. Does the filter hold sensitive data or request objects in static/singleton state?
14. Do the logs avoid writing sensitive body/header/token?

## 13. Self-Check Exercises

**Exercise 1.** Why is the following code incorrect?

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

**Answer:** It creates a subscription detached from the publisher the framework is managing. The filter completes early, errors/cancel do not go through the right pipeline, and the response lifecycle may be wrong.

**Exercise 2.** How do you compose to run `loadPolicy()` before the handler?

**Answer:**

```java
return loadPolicy()
        .flatMap(policy -> {
            exchange.getAttributes().put("policy", policy);
            return chain.filter(exchange);
        });
```

**Exercise 3.** What does it mean when `doFinally` receives `CANCEL`?

**Answer:** The subscriber requested cancellation of the subscription. This is not `onComplete`; physical work outside the application may need a driver that supports cancellation to stop immediately.

**Exercise 4.** Does `exchange.getSession()` start the session automatically?

**Answer:** No. It provides a publisher for the current session or a new session. The session is started when `start()` is called or an attribute is added; Spring automatically calls save before the response commits.

**Exercise 5.** To increment a session counter and then run the handler, which operator is suitable?

**Answer:** `exchange.getSession().flatMap(session -> { update; return chain.filter(exchange); })`.

**Exercise 6.** Why shouldn't you change a response header in `doFinally`?

**Answer:** The response may have already committed. Set the header before delegating or register `beforeCommit`.

**Exercise 7.** Should you call `chain.filter(exchange)` twice to rerun the handler after an audit?

**Answer:** No. It may run the business logic and side effects twice. Join the audit publisher with `then(audit)` or design the audit before/after within the same pipeline.

**Exercise 8.** How do a request attribute and a session attribute differ?

**Answer:** A request attribute only lives within one exchange; a session attribute can exist across many requests of the same session, depending on the store and expiration time.

## 14. Key Takeaways

- `WebFilter.filter` returns `Mono<Void>` representing the rest of the HTTP processing chain.
- `chain.filter(exchange)` must be **composed and returned**, not called with `subscribe()` or `block()`.
- The `doOn...`, `doFinally`, `then`, `flatMap`, and `onErrorResume` operators let you add before/after behavior while keeping a single subscription.
- The filter that goes in first wraps the rest; `@Order`/`Ordered` determine the order.
- `ServerWebExchange` has request attributes per exchange; `WebSession` holds attributes across many requests.
- `getSession()` is reactive; use `flatMap` to update the session and then delegate. Spring automatically saves the session before the response commits.
- Errors and cancellation stay in the pipeline when the subscription is not detached.
- Security, CORS, and session fixation need to be coordinated in the right order with Spring Security.
- A filter should have one clear cross-cutting responsibility; do not turn it into a place for business logic.

When reading a filter, check three things: **which publisher is returned, how many times the chain is called, and which task is being detached from the subscription**. Only if all work is composed into the returned publisher can WebFlux manage the request lifecycle correctly.

## Official Documentation

- Spring Framework 6.2, **Reactive Core – WebHandler API and Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **`WebFilter` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework 6.2, **`WebFilterChain` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/WebFilterChain.html
- Spring Framework 6.2, **`ServerWebExchange` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2, **`WebSession` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Boot, **Reactive Web Applications – Web Filters and ordering**: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Project Reactor, **Blocking can be wasteful – subscribe and composition**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/reactiveProgramming.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html