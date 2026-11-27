# StepVerifier for Reactor Chains and Error Branches in Spring Cloud Gateway

An API Gateway can return HTTP 200 cleanly on the happy path yet hide severe bugs on edge branches: unhandled downstream timeouts, filters swallowing `onError`, attempts to change status after a response commits, retries repeating a POST action, or cancellation failing to propagate when a client closes the connection. These issues matter especially in **SPRING_CLOUD_GATEWAY Server WebFlux**, where request handling and many `GatewayFilter`s are built on **Reactor `Mono`/`Flux`**.

Within the **Testing** chapter, **"StepVerifier for Reactor Chains and Error Branches"** teaches repeatable testing of **reactive signals**: success outcomes, empty sequences, emitted exceptions, fallbacks, retries, timeouts, backpressure, and cancellation. It then applies these principles to custom `GatewayFilter`s, route predicates, header mutation, circuit breakers, rate limiting, service discovery, authentication, and observability in a microservices API Gateway.

Learning objectives:

1. Explain why `StepVerifier` tests **publisher signals**, not just Java method return values.
2. Write assertions for `onNext`, `onComplete`, `onError`, `Mono.empty()`, and multi-element `Flux` streams.
3. Distinguish **propagated errors** from errors **translated into fallbacks/statuses**, and verify each branch.
4. Test timeouts/backoffs with `VirtualTimeScheduler` without waiting in real time.
5. Use `TestPublisher`, `PublisherProbe`, and a mocked `GatewayFilterChain` to simulate controlled downstream behavior.
6. Define the boundary between **unit tests with `StepVerifier`** and **HTTP integration tests with `WebTestClient`**.

> **Scope:** Examples focus on **Spring Cloud Gateway Server WebFlux**, Project Reactor, and `reactor-test`. Gateway **Server Web MVC** uses Servlet/MVC filter abstractions; do not apply `StepVerifier` to an MVC `HandlerFilterFunction` and treat it as the same pipeline. Reactor Test APIs match modern Reactor documentation; use a compatible Reactor/Boot/Cloud BOM release train rather than guessing unverified version numbers. Sample error codes and URIs are for lab use only.

## 1. The Reactor Signal Model: What Does StepVerifier Check?

A reactive `Publisher` does not execute its full business logic as soon as the factory method is called. Execution typically begins upon **subscription**.

Core signals:

| Signal / action | Meaning | Common `StepVerifier` API |
|---|---|---|
| `onSubscribe` | Subscriber receives subscription and can request items | `expectSubscription()` |
| `request(n)` | Subscriber requests up to `n` more items per backpressure | `thenRequest(n)` |
| `onNext(value)` | Emits an item | `expectNext`, `expectNextMatches`, `assertNext` |
| `onComplete` | Completes successfully | `expectComplete()`, `verifyComplete()` |
| `onError(Throwable)` | Terminates with an error | `expectError`, `expectErrorMatches`, `expectErrorSatisfies` |
| `cancel()` | Subscriber stops accepting items | `thenCancel()` |
| No data during interval | No unexpected signals arrive | `expectNoEvent(Duration)` |
| Advance virtual time | Drives scheduler-dependent operators | `thenAwait(Duration)` |

### A Sequence Has One Terminal Signal

Under Reactor/Reactive Streams, `onComplete` and `onError` are **mutually exclusive endings**; a compliant publisher never emits both for the same subscription.

~~~mermaid
flowchart TD
    P["Publisher: Mono / Flux"] --> S["onSubscribe"]
    S --> R["request(n)"]
    R --> N["0..N onNext"]
    N --> T{"How does it terminate?"}
    T -->|Success| C["onComplete"]
    T -->|Failure| E["onError"]
    R -.-> X["Subscriber cancel"]
    N -.-> X
~~~

**`Mono.empty()` is not an error**, nor is it `Mono.just(null)`; Reactor forbids emitting `null` via `onNext`. An empty sequence ends with `onComplete` and no `onNext`. If the API Gateway must return `404` when data is absent, define an explicit mapping rule rather than assuming `empty` is an error.

### Do Not Confuse a Method Returning `Mono` with Completed Side Effects

~~~java
Mono<String> response = Mono.fromSupplier(() -> "ready");

// The line above does not prove subscription occurred.
// StepVerifier creates a subscriber and verifies the signals:
StepVerifier.create(response)
    .expectNext("ready")
    .verifyComplete();
~~~

This snippet is for **tests**; in production, the WebFlux/Gateway framework owns subscription. Never call `subscribe()` yourself inside a filter or controller "just to make it run".

## 2. Adding Test Dependencies Aligned with the Release Train

In a Gateway Server WebFlux app using an appropriate Spring Boot/Spring Cloud BOM:

~~~groovy
dependencies {
    // Starter names vary across release trains.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // JUnit Jupiter, AssertJ, Spring Test, WebTestClient per starter.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // StepVerifier, TestPublisher, PublisherProbe, virtual-time test APIs.
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

**Do not add `reactor-test` to production runtime just to run the Gateway.** It is strictly a unit/integration testing library. `reactor-core` and `reactor-test` must match cleanly; prefer the BOM managed by Spring Boot.

On older Gateway lines, the starter may be `spring-cloud-starter-gateway`; on Gateway Server Web MVC, the web stack differs. Verify artifact names against your exact release train instead of mixing dependencies across generations.

### Common Imports

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.*;
~~~

Not every example needs all of these imports. Treat each code block as a standalone test and include the imports required by that class.

## 3. Basic `StepVerifier`: Successful `Mono` and Ordered `Flux`

A `Mono<T>` emits **at most one value** before completing; a `Flux<T>` can emit multiple values.

~~~java
package example.gateway.testing;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BasicSignalsTest {

    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<String> result =
            Mono.just("catalog").map(String::toUpperCase);

        StepVerifier.create(result)
            .expectNext("CATALOG")
            .verifyComplete();
    }

    @Test
    void fluxEmitsValuesInOrderThenCompletes() {
        Flux<Integer> result =
            Flux.just(1, 2, 3).map(n -> n * 2);

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();
    }
}
~~~

Explanation:

1. `StepVerifier.create(publisher)` defines the script; it subscribes when `verify...` is called.
2. `expectNext(2, 4, 6)` checks both **order and values** of `onNext`.
3. `verifyComplete()` asserts terminal `onComplete` and runs the verification.
4. Changing `Flux.just(1, 2, 3)` to `Flux.just(1, 2, 3, 4)` makes the test **fail**, because an unexpected item precedes completion.

### Never Forget the Verify Step

~~~java
// ANTI-PATTERN: builds the script without executing verification.
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete();

// WITH verify:
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete()
    .verify();
~~~

Many reactive bugs slip past CI simply because a test constructed a `StepVerifier` without **calling `verify()`/`verifyComplete()`/`verifyError()`**.

## 4. Value Assertion Styles

| API | When to use | What to avoid |
|---|---|---|
| `expectNext("ok")` | Exact value known | Expecting objects whose `equals` is unsuitable |
| `expectNextMatches(v -> ...)` | Only a predicate constraint is needed | Overly loose predicates causing false passes |
| `assertNext(v -> ...)` | Multiple JUnit assertions on one value | Unclear messages if assertions fail inside lambda |
| `expectNextCount(n)` | Only item count matters | Missing corrupted item payloads |
| `expectNextSequence(list)` | Compare an ordered list | Source list must hold exact expected values |
| `thenConsumeWhile(...)` | Drain a sequence of unknown length | Accidentally swallowing unexpected items |
| `as("description")` | Label the preceding assertion | Replacing clear domain failure messages |
| `scenarioName(...)` | Name the entire test scenario | Fixing broken test logic |

### Inspect Response Structure Instead of Serializing to Strings

~~~java
record GatewayResult(String routeId, int status, String body) {}

@Test
void checksStructuredResponse() {
    Mono<GatewayResult> response =
        Mono.just(new GatewayResult("catalog-read", 200, "OK"));

    StepVerifier.create(response)
        .assertNext(value -> {
            assertEquals("catalog-read", value.routeId());
            assertEquals(200, value.status());
            assertEquals("OK", value.body());
        })
        .verifyComplete();
}
~~~

A multi-field object should have every key invariant verified. Never use `expectNextCount(1)` to claim a response has the right status.

### Add Scenario Names for Easier Debugging

~~~java
StepVerifier.create(
        Flux.just("A", "B"),
        StepVerifierOptions.create().scenarioName("route-order"))
    .expectNext("A")
    .as("route evaluated first")
    .expectNext("B")
    .as("route evaluated second")
    .verifyComplete();
~~~

Names make failures easier to pinpoint in large route/filter test suites. Note that if `assertNext` throws an `AssertionError` directly, external assertion libraries do not necessarily attach `StepVerifier`'s label to that exception message.

## 5. `Mono.empty`, `switchIfEmpty`, and Not-Found Errors

A "no data" branch must follow the API contract rather than assuming an HTTP error automatically.

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void emptyPublisherCompletesWithoutValue() {
    StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
}

@Test
void missingResourceMapsToDomainError() {
    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(
            Mono.error(new NoSuchElementException("item not found")));

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof NoSuchElementException
            && "item not found".equals(error.getMessage()))
        .verify();
}
~~~

Comparison:

| Publisher | Signals | Expected test |
|---|---|---|
| `Mono.just("item")` | `onNext("item")` → `onComplete` | `expectNext` → `verifyComplete` |
| `Mono.empty()` | `onComplete` | `verifyComplete` |
| `Mono.error(new NotFoundException(...))` | `onError` | `expectError...` → `verify` |
| `Mono.never()` | No terminal signal | Must cancel or set timeout |
| `Mono.justOrEmpty(null)` | `onComplete` | Never expect `onNext(null)` |

In the Gateway, mapping `NoSuchElementException` to HTTP 404 **does not happen automatically in a `GatewayFilter` unit test**. Controller exception handlers, Spring Security, or HTTP response-mapping layers handle that separately; `StepVerifier` verifies only **`Mono` signals**.

## 6. Error Branches: `expectError`, `expectErrorMatches`, and `expectErrorSatisfies`

A sequence can emit `onError` from invalid input, backend faults, network drops, timeouts, or filter bugs. Testing error branches should assert **error type, message/origin, and consequences**, not merely "an exception occurred".

~~~java
import java.io.IOException;
import java.util.concurrent.TimeoutException;

@Test
void checksErrorType() {
    Mono<String> result =
        Mono.error(new IOException("connection reset"));

    StepVerifier.create(result)
        .expectError(IOException.class)
        .verify();
}

@Test
void checksErrorPredicate() {
    Mono<String> result =
        Mono.error(new IllegalArgumentException("invalid route id"));

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
            && error.getMessage().contains("route id"))
        .verify();
}

@Test
void checksErrorFieldsWithAssertions() {
    Mono<String> result =
        Mono.error(new TimeoutException("origin exceeded deadline"));

    StepVerifier.create(result)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(TimeoutException.class, error);
            assertEquals("origin exceeded deadline", error.getMessage());
        })
        .verify();
}
~~~

### Avoid Overly Weak Assertions

~~~java
// Too weak: both IllegalStateException and SecurityException pass.
StepVerifier.create(Mono.error(new IllegalStateException("bug")))
    .expectError()
    .verify();

// Better when the API requires a specific exception:
StepVerifier.create(Mono.error(new IllegalStateException("bug")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

`expectError()` is useful when any terminal error suffices, but for Gateway logic involving retries, circuit breakers, or security, use **contract-specific assertions** to catch misclassified errors.

## 7. Testing `onErrorMap` and Preserving the Root Cause

In a Gateway, an HTTP client exception may be wrapped into a domain exception so higher layers decide between `502`, `503`, or `504`. `onErrorMap` transforms **the emitted error**, never turning it into a success response.

~~~java
import java.io.IOException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void mapsTransportFailureAndPreservesCause() {
    Mono<String> result = Mono.<String>error(
        new IOException("backend reset"))
        .onErrorMap(IOException.class,
            error -> new IllegalStateException(
                "DOWNSTREAM_UNAVAILABLE", error));

    StepVerifier.create(result)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalStateException.class, error);
            assertEquals("DOWNSTREAM_UNAVAILABLE", error.getMessage());
            assertInstanceOf(IOException.class, error.getCause());
        })
        .verify();
}
~~~

**Checks to verify:**

- The original exception remains preserved in `cause` for diagnosis/tracing.
- HTTP client messages containing tokens, sensitive queries, or internal hostnames are not leaked to clients.
- Distinct failures are not collapsed into one generic class if retry policies differentiate retryable errors from 4xx errors.
- `onErrorMap` can change the exception type seen by `Retry`/`CircuitBreaker`; test operator ordering.

### Operator Ordering Changes Behavior

These two chains are not necessarily equivalent:

~~~java
source.onErrorMap(IOException.class, this::wrap)
      .retryWhen(retrySpec);

source.retryWhen(retrySpec)
      .onErrorMap(IOException.class, this::wrap);
~~~

In the first chain, retry inspects the **mapped error**; in the second, retry inspects the **original error** before mapping. If `retrySpec.filter(...)` filters by exception class, this difference determines whether retries happen at all.

## 8. Testing `onErrorResume`: Does Fallback Run on the Right Branch?

`onErrorResume` intercepts an upstream terminal error and **subscribes to an alternate publisher** to supply a fallback value or emit a new error. It is not a blanket safe-recovery operator for every failure.

~~~java
import java.io.IOException;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void timeoutUsesDefinedFallback() {
    Mono<String> result = Mono.<String>error(
        new TimeoutException("orders timeout"))
        .onErrorResume(TimeoutException.class,
            error -> Mono.just("DEGRADED"));

    StepVerifier.create(result)
        .expectNext("DEGRADED")
        .verifyComplete();
}

@Test
void nonTimeoutErrorPropagates() {
    Mono<String> result = Mono.<String>error(
        new IOException("broken pipe"))
        .onErrorResume(TimeoutException.class,
            error -> Mono.just("DEGRADED"));

    StepVerifier.create(result)
        .expectError(IOException.class)
        .verify();
}
~~~

Both tests are equally critical: **supported errors trigger the fallback**, while **errors outside the allowlist are never swallowed**.

### A Succeeding Fallback Can Still Violate the HTTP Contract

If the Gateway hits a timeout on a payment service, returning a synthetic `{"status":"PAID"}` body from a fallback is dangerous. A passing `Mono.just(...)` proves only that the publisher emitted an element—**not that the business state is valid**.

Tests must include **negative assertions**: no fallback on authentication/authorization errors, never return user A's data to user B, never turn 503 into 200 outside the contract, and never replay non-idempotent POSTs.

## 9. Testing Pre/Post Order in `GatewayFilterChain`

A custom `GatewayFilter` may run logic before calling the chain, after the chain completes, or when an error occurs. In Reactor, **operator placement** determines when side effects execute.

~~~mermaid
sequenceDiagram
    participant T as StepVerifier
    participant F as Custom GatewayFilter
    participant C as Fake GatewayFilterChain
    T->>F: subscribe()
    F->>F: pre logic
    F->>C: chain.filter(exchange)
    C-->>F: onComplete or onError
    alt onComplete
        F->>F: post-success
        F-->>T: onComplete
    else onError
        F->>F: doOnError / onErrorResume
        F-->>T: onError or fallback complete
    end
~~~

### Testing Ordering with `Mono.defer` and Local State

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void performsPreThenChainThenPostOnSuccess() {
    List<String> events = new ArrayList<>();

    GatewayFilter filter = (exchange, chain) ->
        Mono.defer(() -> {
            events.add("pre");
            return chain.filter(exchange)
                .doOnSuccess(unused -> events.add("post"));
        });

    GatewayFilterChain downstream = exchange ->
        Mono.fromRunnable(() -> events.add("downstream"));

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/catalog/42"));

    StepVerifier.create(filter.filter(exchange, downstream))
        .expectComplete()
        .verify();

    assertEquals(List.of("pre", "downstream", "post"), events);
}
~~~

`Mono.defer` ensures the `pre` section runs **upon subscription**, not merely when the test calls `filter.filter(exchange, chain)`. `doOnSuccess` fits `Mono<Void>` on completion; on error, that callback **does not execute**.

### Error Branches Must Skip Post-Success

~~~java
@Test
void skipsPostSuccessWhenDownstreamFails() {
    List<String> events = new ArrayList<>();

    GatewayFilter filter = (exchange, chain) ->
        Mono.defer(() -> {
            events.add("pre");
            return chain.filter(exchange)
                .doOnSuccess(unused -> events.add("post"))
                .doOnError(error -> events.add("error"));
        });

    GatewayFilterChain downstream = exchange ->
        Mono.error(new IllegalStateException("downstream failed"));

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/catalog/42"));

    StepVerifier.create(filter.filter(exchange, downstream))
        .expectError(IllegalStateException.class)
        .verify();

    assertEquals(List.of("pre", "error"), events);
}
~~~

In real applications, `doFinally(signal)` observes **onComplete, onError, and cancel**, but be cautious asserting side effects when `doFinally` runs after the terminal signal; avoid racy tests or blocking logging on the event loop.

## 10. Complete Example: Testing a Request-Blocking and Header-Replacing `GatewayFilter`

Suppose the Gateway team develops a lab filter with this policy:

- If a request has `X-Lab-Mode: blocked`, return **403** and **do not call the downstream chain**.
- Otherwise, set header `X-Verified-Lab: yes` and forward.
- `X-Verified-Lab` is Gateway-owned; if the client sends a spoofed value, the filter must **overwrite** it without leaving multiple values.
- Do not read the body or alter path/query.

### Filter Implementation

~~~java
package example.gateway.testing;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;

public final class LabGuardFilter {

    private LabGuardFilter() {}

    public static GatewayFilter create() {
        return (exchange, chain) -> {
            String mode = exchange.getRequest().getHeaders()
                .getFirst("X-Lab-Mode");

            if ("blocked".equals(mode)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                    headers.set("X-Verified-Lab", "yes"))
                .build();

            return chain.filter(
                exchange.mutate().request(request).build());
        };
    }
}
~~~

**Never use `X-Lab-Mode` for real access control in production.** Clients can forge that header. This example exists only to practice filter pass/short-circuit branches; production Bearer token auth and authorization belong to Spring Security and backend checks.

### Success Test: Chain Called and Header Overwritten

~~~java
package example.gateway.testing;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class LabGuardFilterTest {

    @Test
    void forwardsAndOverwritesClientSuppliedHeader() {
        GatewayFilter filter = LabGuardFilter.create();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42?sort=price")
                .header("X-Verified-Lab", "forged"));

        AtomicReference<ServerWebExchange> forwarded =
            new AtomicReference<>();

        GatewayFilterChain chain = nextExchange -> {
            forwarded.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain))
            .expectComplete()
            .verify();

        assertNotNull(forwarded.get());
        assertEquals("yes", forwarded.get()
            .getRequest().getHeaders()
            .getFirst("X-Verified-Lab"));
        assertEquals(1, forwarded.get()
            .getRequest().getHeaders()
            .get("X-Verified-Lab").size());
        assertEquals("/api/orders/42",
            forwarded.get().getRequest().getURI().getPath());
        assertEquals("sort=price",
            forwarded.get().getRequest().getURI().getRawQuery());
    }
}
~~~

**This is a filter unit test** with no Netty server or real backend HTTP calls. The mocked `GatewayFilterChain` lets us verify the **mutated exchange** and confirm path/query preservation.

### Blocking Test: HTTP Status 403 and Chain Skipped

~~~java
@Test
void blockedRequestCompletesWithoutCallingChain() {
    GatewayFilter filter = LabGuardFilter.create();

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders/42")
            .header("X-Lab-Mode", "blocked"));

    AtomicBoolean forwarded = new AtomicBoolean(false);

    GatewayFilterChain chain = next -> {
        forwarded.set(true);
        return Mono.empty();
    };

    StepVerifier.create(filter.filter(exchange, chain))
        .verifyComplete();

    assertFalse(forwarded.get());
    assertEquals(HttpStatus.FORBIDDEN,
        exchange.getResponse().getStatusCode());
}
~~~

Add the matching imports if placing this test into its own class:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
~~~

**A completing `Mono<Void>` does not mean HTTP 200.** On the blocked branch, the publisher emits `onComplete` while the response status is `403` because the filter set it. Thus tests must assert **both the terminal signal and the response status/side effects**.

## 11. Downstream Errors in a Filter: Propagate or Map to HTTP 504?

Suppose a `GatewayFilter` calls `chain.filter(exchange)` and the downstream chain emits a `TimeoutException`. Two contracts are possible:

1. **Propagate the error** so a higher layer decides the response.
2. **Catch a specific error**, set an HTTP status (e.g., 504), and complete the response.

### Without Mapping, `StepVerifier` Must Observe `onError`

~~~java
@Test
void propagatesBackendErrorWithoutSilencingIt() {
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders/42"));

    GatewayFilterChain chain = next ->
        Mono.error(new IllegalStateException("backend failed"));

    StepVerifier.create(
            LabGuardFilter.create().filter(exchange, chain))
        .expectErrorMatches(error ->
            error instanceof IllegalStateException
            && error.getMessage().contains("backend failed"))
        .verify();
}
~~~

**Do not assert the HTTP response will be 500 in this unit test**: you are only calling `GatewayFilter` with a fake chain, not booting WebFlux/Gateway's full exception-to-HTTP-response translation.

### Filter Mapping Timeouts to 504

~~~java
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

GatewayFilter timeoutTo504 = (exchange, chain) ->
    chain.filter(exchange)
        .onErrorResume(TimeoutException.class, error -> {
            // Once committed, changing status is no longer safe.
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(
                HttpStatus.GATEWAY_TIMEOUT);
            return exchange.getResponse().setComplete();
        });
~~~

And the test:

~~~java
var exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/orders/42"));

GatewayFilterChain timeoutChain = next ->
    Mono.error(new TimeoutException("origin timed out"));

StepVerifier.create(timeoutTo504.filter(exchange, timeoutChain))
    .verifyComplete();

assertEquals(HttpStatus.GATEWAY_TIMEOUT,
    exchange.getResponse().getStatusCode());
~~~

These snippets belong to a **test context with imports already present**. `TimeoutException` is a simulated class; actual Reactor Netty timeouts may surface as **different exceptions**. Catch only a known allowlist of exceptions and verify real exception types in integration tests. **Never catch every `Throwable` and return 200/504**, as that hides security failures, coding bugs, and committed-response errors.

## 12. `TestPublisher`: Controlling Downstream Signals Step by Step

`TestPublisher<T>` lets tests manually emit `onNext`, `onComplete`, or `onError` into a publisher subscribed to by your operators. It is useful for simulating a **backend that emits data then fails**, sudden connection drops, or delayed responses without starting a server.

~~~java
package example.gateway.testing;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class ManualSignalTest {

    @Test
    void observesValueThenTransportFailure() {
        TestPublisher<String> upstream = TestPublisher.create();

        Flux<String> pipeline = upstream.flux()
            .map(String::toUpperCase);

        StepVerifier.create(pipeline)
            .then(() -> upstream.next("first"))
            .expectNext("FIRST")
            .then(() -> upstream.error(
                new IOException("connection reset")))
            .expectError(IOException.class)
            .verify();
    }
}
~~~

**Strength:** emissions happen **after `StepVerifier` subscribes** via `then(...)`, avoiding sleeps to "wait for the backend".

**Limitation:** `TestPublisher` models reactive signals; it **does not simulate HTTP statuses, TLS, framing, Netty timeouts, connection pooling, or Gateway filter order**. Those require integration tests or transport-layer tests.

### Avoid `Thread.sleep`

~~~java
// Never make tests depend on CI machine speed.
Thread.sleep(500);
assertEquals(...);
~~~

Async timing fluctuates with CPU contention, GC, and schedulers. Use `TestPublisher`, virtual time, and explicit publisher assertions instead of fixed sleeps when testing Reactor operators.

## 13. `PublisherProbe`: Proving the Right Fallback Branch Was Subscribed

Sometimes the final output looks the same, yet you still need to prove **which branch actually executed**. `PublisherProbe` tracks subscription, requests, and cancellation on a publisher.

~~~java
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

@Test
void fallbackBranchIsSubscribedOnTimeout() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached-safe-value"));

    Mono<String> result = Mono.<String>error(
        new TimeoutException("origin down"))
        .onErrorResume(TimeoutException.class,
            error -> fallback.mono());

    StepVerifier.create(result)
        .expectNext("cached-safe-value")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
~~~

Testing the **non-fallback** branch:

~~~java
@Test
void healthyResponseDoesNotSubscribeToFallback() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached-safe-value"));

    Mono<String> result = Mono.just("fresh")
        .onErrorResume(TimeoutException.class,
            error -> fallback.mono());

    StepVerifier.create(result)
        .expectNext("fresh")
        .verifyComplete();

    fallback.assertWasNotSubscribed();
}
~~~

When a Gateway uses circuit breakers, fallbacks, `switchIfEmpty`, cache lookups, or conditional downstream calls, **`PublisherProbe`** verifies "was the secondary publisher used?" without counting log lines.

### Error Fallback Does Not Mean the Response Should Be HTTP 200

If `"cached-safe-value"` is private data or past its TTL, a succeeding fallback still violates the contract. Tests should verify **freshness, user/tenant isolation, HTTP status, and `Cache-Control`** at the appropriate layer. `PublisherProbe` proves **control flow**, not business correctness.

## 14. Virtual Time: Testing Timeouts Without Waiting in Real Time

A common mistake when testing `Retry`/timeouts is waiting real seconds or minutes, making tests slow and flaky. `StepVerifier.withVirtualTime(...)` controls Reactor's **virtual scheduler**.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void verifiesDelayedSignalWithoutWaitingOneHour() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofHours(1))
                .map(value -> "ready"))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext("ready")
        .verifyComplete();
}
~~~

Key rules:

1. **The publisher containing time operators must be created inside the `() -> ...` supplier.**
2. `expectSubscription()` must precede `expectNoEvent(...)`, because subscription itself counts as an event.
3. `thenAwait(...)` advances the virtual clock; `expectNoEvent(...)` advances time while verifying no premature signal arrives.
4. `verifyComplete()` runs the scenario and checks the terminal signal without waiting a real hour.
5. `withVirtualTime` replaces only schedulers managed by Reactor Test; **it does not simulate Netty sockets, DNS, TLS, Redis, or external custom clocks**.

### Testing the `timeout` Operator

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Test
void timeoutProducesOnErrorAfterFiveVirtualSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(5)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
~~~

`verify(Duration.ofSeconds(2))` here is a **real-time safety timeout on the test itself** so a broken script cannot hang CI. It is **separate** from the 5-second virtual timeout being tested inside the publisher.

### Cases Where Virtual Time Can Hang a Test

- Constructing `Mono.delay` or `Retry.backoff` **outside** the `withVirtualTime` supplier, binding the operator to a non-virtual scheduler.
- Calling `expectNext` before advancing the virtual clock far enough.
- Using an operator configured with a dedicated custom scheduler that virtual time does not replace.
- Performing blocking I/O inside the publisher, unaffected by virtual schedulers.
- Complex unbounded/hot sources driven by external wall-clock threads.

Never use virtual time to claim **real downstream connect timeouts** or **TLS handshake timeouts** work; test those with real HTTP clients/runtimes.

## 15. `Retry.backoff`: Counting Attempts and Checking Exhaustion

In the Gateway, `Retry` can turn one client request into multiple outbound attempts. Testing Reactor `Retry` at the publisher level checks **when retries trigger, maximum attempts, and final errors**.

### Succeeding on the Third Attempt

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

@Test
void retrySucceedsOnThirdSubscription() {
    AtomicInteger subscriptions = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                int attempt = subscriptions.incrementAndGet();
                if (attempt < 3) {
                    return Mono.<String>error(
                        new IOException("temporary #" + attempt));
                }
                return Mono.just("ok");
            }).retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .jitter(0d)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("ok")
        .expectComplete()
        .verify(Duration.ofSeconds(2));

    assertEquals(3, subscriptions.get());
}
~~~

**`Retry.backoff(2, ...)` allows at most two retries after the initial attempt**, meaning up to **three subscriptions/attempts**. `jitter(0d)` disables randomness for deterministic virtual-time schedules; production configs usually keep reasonable jitter to avoid synchronized retry storms.

### When Retries Exhaust, the Error Type Can Differ from the Original

~~~java
@Test
void retryExhaustionIsNotAccidentallySuccessful() {
    AtomicInteger subscriptions = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                subscriptions.incrementAndGet();
                return Mono.<String>error(
                    new IOException("always unavailable"));
            }).retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .jitter(0d)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorMatches(error ->
            reactor.core.Exceptions.isRetryExhausted(error))
        .verify(Duration.ofSeconds(2));

    assertEquals(3, subscriptions.get());
}
~~~

Reactor `Retry` can wrap failures in a `retry exhausted` exception when limits are reached; check **`Exceptions.isRetryExhausted(error)`** and the root cause if your contract requires it, rather than assuming the final error is always the raw `IOException`. With Gateway's `Retry` `GatewayFilter`, filtering HTTP status codes and methods adds routing/response semantics; **unit testing `Retry.backoff` does not replace integration testing the actual Retry filter**.

### How HTTP Codes Affect Retry

| Scenario | Do not assume |
|---|---|
| HTTP 503 from backend | Every Reactor `Mono` turns into `onError` automatically |
| HTTP 429 + `Retry-After` | `Retry.backoff` reads HTTP headers on its own |
| POST with partially sent body | The request replays safely |
| Gateway Retry filter | Attempt counts match simple Reactor snippets |
| CircuitBreaker + Retry | Ordering and call counts stay constant |
| Client canceled request | Backend sees zero side effects |

**An HTTP 503 response is a `ResponseEntity`/status**, not necessarily a Reactor `onError`. An HTTP client needs explicit policy to map statuses to errors or let the filter inspect responses and decide whether to retry.

## 16. Backpressure and Cancellation: Beyond `onNext`

When upstream produces faster than downstream consumes, or when clients disconnect, reactive pipelines must respect demand and cancellation. `StepVerifier.create(publisher, initialRequest)` can start with demand 0 to verify backpressure.

### Controlling `request(n)`

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsOnlyAsDemandIsRequested() {
    Flux<Integer> numbers = Flux.range(1, 3);

    StepVerifier.create(numbers, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
~~~

If your operator **emits beyond demand** (violating Reactive Streams), bugs or runtime-dependent failures can occur; tests should use demand-respecting sources. `Flux.range` honors demand and makes a convenient baseline.

### Testing Cancellation of a Long-Lived Stream

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void cancelsLongLivedStream() {
    StepVerifier.withVirtualTime(
            () -> Flux.interval(Duration.ofSeconds(1)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .thenCancel()
        .verify();
}
~~~

Passing `thenCancel()` proves **the subscriber canceled the subscription** in the test script; it does not by itself prove the TCP socket closed immediately or the backend aborted a file-write job. For Gateway streaming/SSE/WebSocket routes, integration tests must verify connection cleanup, buffer release, and side effects separately.

### Cancellation Is Not a Terminal HTTP Response

If a client closes the connection mid-download, you cannot always emit a fresh HTTP 503 because the response may already be committed or the socket gone. Do not write a global `onErrorResume` returning fallback JSON for every `cancel`: cancellation is a **subscription-control signal**, not `onError`.

## 17. Reactor Context: Correlation IDs and Request Isolation

The Gateway often propagates trace IDs, request IDs, or metadata via Reactor `Context`. It **differs from `ThreadLocal`** and from HTTP headers.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

@Test
void seesContextValueAcrossReactiveOperators() {
    Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("traceId")));

    StepVerifier.create(result,
            StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-lab-123")))
        .expectAccessibleContext()
        .contains("traceId", "trace-lab-123")
        .then()
        .expectNext("trace-lab-123")
        .verifyComplete();
}
~~~

### Key Limitations to Know

- `Context` flows along the **subscriber/reactive chain**, not as a global Map.
- `contextWrite(...)` applies in subscription direction, opposite to operator assembly order.
- A custom filter calling `subscribe()` itself can drop context and break tracing.
- Never place raw access tokens, session cookies, or unnecessary PII into log/metric tags from context.
- `StepVerifier` verifies Reactor `Context`, **not that HTTP trace headers propagated across Reactor Netty**. Use integration tests and observability tooling to verify both hops.

## 18. `verifyThenAssertThat` and Discarded/Dropped Signals

After checking terminal expectations, `verifyThenAssertThat()` lets you inspect verifier state, such as whether items were **dropped** or **discarded**.

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void filteredElementIsDiscarded() {
    StepVerifier.create(
            Flux.just(1, 2, 3)
                .filter(n -> n % 2 == 1))
        .expectNext(1, 3)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscarded(2)
        .hasNotDroppedElements()
        .hasNotDroppedErrors();
}
~~~

**Discarded vs. dropped:**

- **Discarded** can be **normal** behavior when an operator like `filter` rejects an item by predicate, if the operator invokes the discard hook.
- **Dropped** describes signals emitted with no valid active subscriber (e.g., signals after termination), often indicating a specification-violating publisher.
- With pooled `DataBuffer`s in the Gateway, drops/discards may relate to **buffer release**, though `hasDiscarded(...)` on integers **does not prove byte buffers were freed**.

Use `verifyThenAssertThat` and `TestPublisher` hooks carefully in parallel test suites, since hooks/schedulers interact with process-wide state. Never enable or override global Reactor hooks per test without cleanup.

## 19. `StepVerifier` with Body `Flux` in Custom Gateway Filters

In WebFlux, a request body is a `Flux<DataBuffer>`. A filter reading the body to log or inspect JSON can:

- Consume the body so downstream receives nothing.
- Buffer huge uploads into RAM.
- Forget to release pooled `DataBuffer`s when dropping/replacing.
- Subscribe independently, losing cancellation/backpressure.
- Break retries that need to replay the request body.

**`StepVerifier` works well for unit testing pure `Flux` transformation logic**, such as chunk ordering or error handling in a pure Reactor transformer. Verifying actual bytes reaching the backend, `Content-Length`, multipart boundaries, and HTTP `Range`, however, requires end-to-end HTTP tests.

### Example Stateless Transformer Across Requests

~~~java
import reactor.core.publisher.Flux;

static Flux<String> sanitizeEvents(Flux<String> source) {
    return source
        .filter(event -> !event.isBlank())
        .map(String::trim);
}
~~~

Tests:

~~~java
@Test
void removesBlankEventsWithoutChangingOrder() {
    StepVerifier.create(sanitizeEvents(
            Flux.just(" a ", "  ", " b ")))
        .expectNext("a", "b")
        .verifyComplete();
}

@Test
void forwardsSourceErrorAfterValidEvent() {
    Flux<String> source = Flux.just("first")
        .concatWith(Mono.error(
            new IllegalStateException("event source failed")));

    StepVerifier.create(sanitizeEvents(source))
        .expectNext("first")
        .expectError(IllegalStateException.class)
        .verify();
}
~~~

**Code note:** This is a `Flux<String>` transformer for learning signals; it does not read SSE/network bytes. For real `DataBuffer` streams, manage ownership, reference counting, and pooled buffers carefully, and never treat `map(String::trim)` as a production streaming-upload body filter.

## 20. `StepVerifier` Does Not Replace `WebTestClient`: Multi-Layer Testing

To test a Gateway route thoroughly, separate test layers:

~~~mermaid
flowchart TD
    UNIT["Unit: StepVerifier + fake chain"] --> CT["Component: WebFlux codecs, route/filter order"]
    CT --> HTTP["Integration: WebTestClient + real Gateway + mock backend"]
    HTTP --> E2E["End-to-end: ingress/TLS/discovery/security/Redis"]
    UNIT -.->|"Fast, tests reactive signals and filter logic"| S["Reactive signals"]
    HTTP -.->|"Verifies HTTP status/headers/body"| H["Gateway → backend contract"]
    E2E -.->|"Exercises production-like topology"| R["SLOs and fault injection"]
~~~

### What `StepVerifier` Does Well

- Testing `Mono`/`Flux` ordering of `onNext`/`onError`/`onComplete`.
- Testing `onErrorResume`, `switchIfEmpty`, and `Retry.backoff` with virtual time.
- Testing custom `GatewayFilter`s with `MockServerWebExchange` and a fake `GatewayFilterChain`.
- Testing backpressure, cancellation, and `PublisherProbe`.
- Testing Reactor `Context` or operators reading trusted metadata.

### What `WebTestClient`/Integration Tests Do Well

- Verifying `Path`/`Method`/`Host` predicates and live route matching.
- Verifying `StripPrefix`, `RewritePath`, and backend-bound header mutations.
- Verifying **system-level** HTTP 401/403/429/502/503/504 responses.
- Verifying real `Retry` when the backend returns 503, including timing/backoff.
- Verifying `lb://` connections, TLS, connection resets, timeouts, and circuit breakers.
- Verifying request/response bodies, streaming, compression, multipart, and content length.
- Verifying Spring Security filter chains running ahead of/distinct from `GatewayFilter`s.
- Verifying metrics/traces across multiple hops.

**A single subscription in `StepVerifier` does not prove a live HTTP request triggered only one outbound attempt.** Network-level tests must also count backend calls.

## 21. `WebTestClient`: HTTP Integration Testing Outside `StepVerifier`

A realistic test uses a booted Gateway Server WebFlux instance and a fake downstream HTTP server. `WebTestClient` provides fluent HTTP request/response assertions.

Example **illustrating assertions**, assuming an application configured with `/api/catalog/**` pointing to a mock JSON backend:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GatewayHttpContractTest {

    @Autowired
    WebTestClient client;

    @Test
    void catalogRouteReturnsExpectedBody() {
        client.get()
            .uri("/api/catalog/items/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42);
    }
}
~~~

**This test will not run standalone without fixtures**: it needs a matching route, a test/mock backend, and Spring Boot test setup aligned with your release train. `WebTestClient` can bind to a live server or an application context; to test Netty routing, use a **real enough HTTP path** so the Gateway actually forwards downstream.

### HTTP Branches to Simulate

| Backend error/response | HTTP assertion to verify | Complementary signal-level test |
|---|---|---|
| 200 + JSON | Body, `Content-Type`, route ID/log | `Mono` success |
| 404 | Not silently turned into 200 | `switchIfEmpty` or backend status mapping |
| 503 → retry → 200 | Final 200, backend call count, deadline | `Retry.backoff` / error-filtering predicate |
| Backend connection refused | 502/503 per Gateway/client policy | `onErrorMap`/`onErrorResume` |
| Timeout past budget | 504 or contract-defined status | Virtual-time `timeout` |
| 401/403 from security | Backend never called if blocked pre-route | Insufficient if testing `GatewayFilter` alone |
| 429 from limiter | Appropriate `RateLimit` headers/quota | Fake limiter/`KeyResolver` branches |
| CircuitBreaker open | Fallback/5xx per policy | `PublisherProbe` and state machine |
| Body codec failure | 400/413/5xx per contract | `Flux` error/buffer lifecycle |
| Client abort | Socket/stream cleanup | `thenCancel` + integration |
| Committed response | Does not try to overwrite status | Post-commit error propagation |

Final HTTP codes like 502/503/504 **depend on runtime and configuration**; never hardcode an assumption without an explicit contract.

## 22. Security, `RateLimiter`, `CircuitBreaker`, and `Retry`: Writing Negative Tests

### Spring Security

A WebFlux Gateway normally runs `SecurityWebFilterChain`. It can return 401/403 **before a custom `GatewayFilter` is ever reached**. If a unit test only calls `filter.filter(exchange, chain)`, you have **not tested authentication or authorization**.

Negative tests should include:

- Missing Bearer token.
- Expired token or wrong audience.
- Valid token lacking required scope/role.
- User A accessing a resource owned by user/tenant B.
- Spoofed `X-Authenticated-User` header.
- CORS `OPTIONS` preflight per policy and non-matching routes.

**Never treat Reactor Context or hand-crafted test headers as proof that security is enforced.** Write integration tests with real Spring Security and proper identity fixtures.

### `RequestRateLimiter`

A `KeyResolver` returning `Mono.empty()` can trigger **empty-key behavior** distinct from keyed requests. Test keyed, empty-key, and resolver-error branches separately, then HTTP-test 429/403 per policy.

~~~java
Mono<String> resolvedKey = Mono.<String>empty();

StepVerifier.create(resolvedKey)
    .verifyComplete();
~~~

The test above **proves only that the resolver emits no key**; it does not prove which HTTP status `RequestRateLimiter` returns for an empty key. That belongs to filter/route behavior and must be tested separately.

### `CircuitBreaker`/Fallback

A fallback publisher can be checked with `PublisherProbe`, but also verify that fallbacks **never serve private cached responses across tenants** and **never turn every 503 into 200**. If downstream has already flushed part of the response, fallback status/body changes may no longer be possible post-commit.

### `Retry`

Idempotent GETs may allow bounded retries. Side-effecting POST/PATCH requests require a backend idempotency contract; `StepVerifier` counting subscriptions is not enough to prove actions were not duplicated. Integration tests must count **backend attempts and side effects**, not just final status codes.

## 23. Test Matrix for Custom Gateway Filters

| Scenario | Publisher expectation | Non-publisher assertions |
|---|---|---|
| Successful routing | `onComplete` on `Mono<Void>` | Chain invoked; headers/path accurate |
| Blocked by filter | `onComplete` | HTTP 403/429; chain not invoked |
| Invalid input | `onError` or controlled response | Not forwarded; input not leaked |
| Downstream 503 | May `onComplete` with HTTP response or `onError` from client | Status and downstream call count |
| Timeout mapped to 504 | `onComplete` if response finishes | Status 504 and no bad body |
| Unhandled timeout | `onError` | HTTP global error handler follows contract |
| Error outside fallback allowlist | `onError` | Never swallows `SecurityException` |
| Retry succeeds | `onNext`/`onComplete` | Exact attempt count and total latency |
| Retry exhausted | `onError` | Root cause/wrapper and deadline |
| Empty result | `onComplete` without `onNext` | HTTP 404/204 if required by contract |
| Cancellation | `thenCancel` | Buffers/sockets/side effects cleaned up |
| Error after response commit | May emit `onError` | Status/headers already sent remain untouched |
| Multiple concurrent requests | Independent publishers | No user/tenant state leakage |
| Cache hit | Sequence completes | Backend not called and body intact |
| `no-store`/private response | Sequence completes per policy | Not stored in shared cache |
| WebSocket/SSE | Streaming semantics, cancellation | No unbounded buffering; protocol respected |

**Test unexecuted branches too.** When a request is blocked, assert the fake downstream was **not called**. When fallback is disallowed, assert the probe was **never subscribed**. When status stays unchanged, inspect the response rather than checking only the terminal signal.

## 24. Preventing Flaky Tests: Good Practices

| Anti-pattern | Why it breaks | Replace with |
|---|---|---|
| Forgetting `verify()` | Test never subscribes or asserts | `verifyComplete`/`verifyError`/`verify` |
| `Thread.sleep` for async work | Depends on CI machine speed | `TestPublisher`, virtual time, publisher assertions |
| `block()` in production filter | Blocks event loop, breaks non-blocking model | Compose `Mono`/`Flux`; use `StepVerifier` in tests |
| Overly broad `expectError()` | Misses wrong exception types | `expectErrorMatches`/`expectErrorSatisfies` |
| Checking only `onComplete` of `Mono<Void>` | Might have returned 403 or skipped chain | Check status, forwarded flag, and exchange |
| `Mono.never()` without timeout/cancel | Test can hang forever | `thenCancel` or `timeout` + verify bound |
| Creating timed publisher outside supplier | Virtual time misses scheduler | Construct chain inside `withVirtualTime(() -> ...)` |
| Configuring retries without counting subscriptions | Unknown outbound attempt count | `AtomicInteger`/test backend counter |
| `TestPublisher` never emits terminal signal | Verify waits indefinitely | Emit `complete`/`error` or cancel |
| Modifying global schedulers/hooks without cleanup | Tests pollute one another | Isolation and state restoration |
| Asserting in `doFinally` immediately off-thread | Races because callback runs after signal | Use probes/proper sync awaits or `StepVerifier` assertions |
| Testing only GET 200 | Misses auth, timeouts, fallbacks, body bugs | Matrix of success/error/cancel |
| Asserting HTTP status from fake `GatewayFilterChain` | Lacks web exception mapping | Use `WebTestClient` integration tests |
| Mapping every exception to 200 | Hides production failures | Allowlisted recovery, assert status and security |
| Logging full payloads in tests | Leaks JWTs/cookies/sensitive bodies | Synthetic data, scrubbed logs, explicit assertions |

### `StepVerifier`'s Own Timeout

Per Reactor Test, some `verify()` calls **block indefinitely by default**. You can set an explicit bound:

~~~java
import java.time.Duration;

StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

`StepVerifier.setDefaultTimeout(Duration)` also exists, though it mutates **shared global state** and requires careful teardown/restoration, especially under parallel execution.

### Scenario Names and Logs

`StepVerifierOptions.scenarioName(...)` and `as(...)` pinpoint failing expectations. You may enable StepVerifier/Reactor test logging in the lab, but never print raw tokens, request bodies, or sensitive exception messages to shared CI logs.

## 25. Complete Hands-On Lab: A Three-Branch Service

Create a test service stub simulating catalog lookups:

- Non-empty ID `42` → returns success.
- ID `slow` → delayed `Mono`, then returns `ready`.
- ID `fail` → `IOException`.
- Any other ID → empty.

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.time.Duration;
import reactor.core.publisher.Mono;

public final class CatalogClientStub {

    public Mono<String> fetch(String id) {
        if (id == null || id.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("id required"));
        }

        return switch (id) {
            case "42" -> Mono.just("item:42");
            case "slow" -> Mono.delay(Duration.ofSeconds(10))
                .map(ignore -> "ready");
            case "fail" -> Mono.error(
                new IOException("backend unavailable"));
            default -> Mono.empty();
        };
    }
}
~~~

Test each branch:

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class CatalogClientStubTest {

    private final CatalogClientStub client = new CatalogClientStub();

    @Test
    void success() {
        StepVerifier.create(client.fetch("42"))
            .expectNext("item:42")
            .verifyComplete();
    }

    @Test
    void emptyResult() {
        StepVerifier.create(client.fetch("999"))
            .verifyComplete();
    }

    @Test
    void validationError() {
        StepVerifier.create(client.fetch(""))
            .expectError(IllegalArgumentException.class)
            .verify();
    }

    @Test
    void transportError() {
        StepVerifier.create(client.fetch("fail"))
            .expectError(IOException.class)
            .verify();
    }

    @Test
    void delayedResultUsesVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> client.fetch("slow"))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("ready")
            .verifyComplete();
    }
}
~~~

**What branches remain untested?** An extra test should apply `fetch("slow").timeout(Duration.ofSeconds(5))` and expect `TimeoutException` using virtual time; another should wrap `fetch("fail")` with `onErrorResume` recovering only `IOException`, then verify other exception types propagate intact.

### Connecting Back to Real Gateways

This stub models reactive signals like an HTTP client abstraction; **it does not replace full `WebClient`/Gateway routing semantics**. If a real backend returns HTTP 503, the client may return a normal response object instead of `Mono.error`, depending on the API. When applying these lessons to a Gateway, verify **status-to-error translation and routing filter order**.

## 26. Checklist Before Marking Testing Complete

- [ ] Added `reactor-test` in `test` scope, not runtime.
- [ ] Can distinguish `Mono`, `Flux`, `empty`, `error`, and `never`.
- [ ] Always call `verify()` or a matching `verify...` shortcut.
- [ ] Use `expectNext`/`assertNext` for data and `expectComplete`/`expectError` for terminal signals.
- [ ] Understand that a completing `Mono<Void>` **does not prove** HTTP status 200.
- [ ] Check errors by type/message/cause rather than bare `expectError()`.
- [ ] Test both fallback-triggered and fallback-skipped branches with `PublisherProbe`.
- [ ] Use `TestPublisher` to drive controlled downstream signals.
- [ ] Use `withVirtualTime` correctly: create timed publishers inside the supplier.
- [ ] Call `expectSubscription()` before `expectNoEvent`.
- [ ] Distinguish operator timeouts from test-guard timeouts.
- [ ] Count both retries **and** total subscriptions; never confuse retries with total attempts.
- [ ] Know `Retry.backoff` exhaustion can return a wrapper exception.
- [ ] Test `onErrorMap`, `onErrorResume`, and `switchIfEmpty` in the exact operator order.
- [ ] Test backpressure (`thenRequest`) and cancellation (`thenCancel`) for streaming paths.
- [ ] Understand Reactor `Context` is neither HTTP headers nor Spring Security context by default.
- [ ] Never call `subscribe()`, `block()`, or blocking I/O inside a `GatewayFilter`.
- [ ] Test pre/chain/post ordering, header mutations, and short-circuits with a fake chain.
- [ ] Never assert full-pipeline HTTP responses from unit tests invoking only `GatewayFilter`.
- [ ] Have `WebTestClient` integration tests covering route predicates, filter chain, security, and backend.
- [ ] Test 401/403/429, timeouts, retries, fallbacks, caching, response commits, and backend attempts.
- [ ] Never log raw JWTs, cookies, user IDs, request bodies, or secrets in test logs.
- [ ] Keep tests deterministic, avoid sleeps, and clean up process-wide hooks/schedulers.
- [ ] Include at least one negative test proving user/tenant data cannot leak across callers.
- [ ] Run tests on the project's approved **Spring Boot/Spring Cloud/Gateway/Reactor BOM**.
- [ ] Distinguish unit verification PASS from Content QA and unexecuted integration/runtime verification.

## 27. Extension Exercises

**Exercise 1 — Convert empty contract to 404.** Write `Mono<String> findItem(id)` returning empty when missing; apply `switchIfEmpty(Mono.error(...))`. Test before/after and explain why `StepVerifier` does not directly prove HTTP 404.

**Exercise 2 — Wrong error type.** Write an operator that falls back only on `TimeoutException`; use `TestPublisher` to emit `IOException` and then `SecurityException`, verifying neither is **swallowed**.

**Exercise 3 — Short-circuit filter.** Using `LabGuardFilter`, write tests proving spoofed headers are overwritten, blocked requests skip the fake chain, and allowed requests preserve path/query.

**Exercise 4 — Virtual timeout.** Write a test for `Mono.delay(Duration.ofMinutes(30)).timeout(Duration.ofMinutes(1))` using `withVirtualTime` and a test-guard timeout; never sleep 30 minutes.

**Exercise 5 — Retry.** Build a source failing twice before succeeding; assert count 3, success signal, exhaustion, and wrapper exception behavior. Why disable jitter in virtual-time tests while keeping it in production?

**Exercise 6 — Backpressure.** Use `Flux.range(1, 100)` with `initialRequest = 0`, call `thenRequest(10)`, and then `thenCancel()`. Verify `onComplete` is not expected on an unfinished stream.

**Exercise 7 — HTTP fault injection.** Use a mock backend returning 503 twice then 200, combining `WebTestClient` with a backend request counter. Compare the HTTP results with a `StepVerifier` retry unit test and explain why the Gateway `Retry` filter handles statuses differently from Reactor `Mono.error`.

**Exercise 8 — Security.** Test requests with no JWT, wrong-scope JWT, and valid token; verify the backend receives no blocked requests. Why does calling `GatewayFilter.filter(...)` alone not prove `SecurityWebFilterChain` works?

## Official References

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier`, virtual time, `PublisherProbe`, `TestPublisher`, Context, and post-verification assertions.
- [Reactor Test — StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — terminal expectations, `verify`, `thenRequest`, `thenCancel`, `withVirtualTime`.
- [Reactor Test — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html) — `scenarioName` and `withInitialContext`.
- [Reactor Test — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html) — verifying fallback subscription/request/cancellation.
- [Reactor Test — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html) — emitting manual signals in unit tests.
- [Reactor Test — StepVerifier Assertions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html) — dropped/discarded/operator error assertions.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Server WebFlux route predicates, filter chain, Retry, CircuitBreaker, and version-specific testing.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — HTTP assertions, bind-to-server, and bind-to-application-context.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — `@SpringBootTest`, test auto-configuration, and integration fixtures.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — subscription, demand, backpressure, `onNext`/`onError`/`onComplete`, and cancellation semantics.

**Takeaway:** `StepVerifier` lets you prove **a Reactor chain emits the exact sequence of data, errors, completion, or cancellation**. In Spring Cloud Gateway Server WebFlux, use it to test **custom filters, fallbacks, timeouts, retries, Reactor Context, and error branches**, pairing it with `TestPublisher`/`PublisherProbe` to confirm **which branch executed**. Yet a completing `Mono<Void>` **does not equal HTTP 200**, and `StepVerifier` **never replaces `WebTestClient`** when verifying routing, Spring Security, statuses/headers, backend attempts, or live TLS. Testing quality comes from covering **both success paths and negative paths** with assertions at the right layer.
