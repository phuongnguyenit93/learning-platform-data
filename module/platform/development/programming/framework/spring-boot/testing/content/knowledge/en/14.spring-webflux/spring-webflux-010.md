# Distinguishing Application Errors from Blocking or Improper Subscription Errors in Spring WebFlux

## 1. Why Distinguish the Three Error Categories?

In Spring WebFlux, an HTTP request can fail because of **business rules**, **infrastructure** (databases, external APIs, timeouts), or **improper Reactive Streams programming**. External symptoms sometimes all look like HTTP 500, empty responses, timeouts, or flaky tests, yet the fixes are completely different.

For example, with `GET /api/orders/42`:

- Order does not exist: the application **intentionally emits a business error** `OrderNotFoundException`. If the API contract specifies 404, controller advice must translate it cleanly to `404 Not Found`.
- Gateway experiences an outage: `Mono.error(new IllegalStateException("gateway unavailable"))` is a **system/downstream error**. Never turn it into 404 just to make a test green.
- Controller calls `.block()` on a **Reactor non-blocking thread**: this can throw `IllegalStateException` because blocking operations are forbidden on that thread. That is a **reactive design bug**, not proof that the order has a problem.
- Controller calls `.subscribe()` manually and returns a different publisher: errors from the manually subscribed publisher flow through **an independent subscription**, no longer part of the HTTP response managed by WebFlux. The client may receive a successful/empty response even though the background work failed.
- Publisher is never subscribed: lazy operations never run; a test that merely sees a `Mono` object and concludes side effects ran is a **false positive**.

**Goal:** classify root causes by origin, `onNext/onError/onComplete` signals, subscription path, and HTTP boundary; then use `StepVerifier`, `WebTestClient`, and scheduler/thread observation to verify the exact behavior.

## 2. Foundational Model: Mono/Flux Is a Work Description

In Reactor, `Mono<T>` represents a publisher emitting **at most one item** (or empty/error), whereas `Flux<T>` can emit many items. Most publishers created from `Mono.defer`, `Mono.fromCallable`, `Flux.defer`, or reactive repository operations are **lazy/cold**: work only begins when a subscriber attaches.

```text
Assembly (building the pipeline)
  Mono.defer(...)
      .map(...)
      .flatMap(...)
      .onErrorResume(...)
          |
          |  Does not necessarily call DB/API yet
          v
Subscription
          |
          +---- request/demand ----> upstream
          |
          +---- onNext(value)  (0 or 1 for Mono)
          |
          +---- onComplete()   (normal termination)
          |
          +---- onError(error) (error termination)
```

For a single subscription, `onError` and `onComplete` are **mutually exclusive terminal signals**. `Mono.empty()` completes without emitting data and **does not automatically mean** HTTP 404. `Mono.error(ex)` describes an error to be emitted to the subscriber; it differs from throwing an exception synchronously before returning a publisher, even though WebFlux can handle both via appropriate mechanisms.

**WebFlux is the party that subscribes to the publisher returned by a controller.** Therefore, controllers should normally **return the pipeline** instead of calling `.subscribe()` or `.block()` themselves. In Reactor unit tests, `StepVerifier` is the asserting subscriber. In web slice/integration tests, `WebTestClient.exchange()` triggers the request path and verifies the HTTP response.

### 2.1. Recognizing Lazy Execution from a Short Example

```java
Mono<String> pending = Mono.defer(() -> {
    System.out.println("executed");
    return Mono.just("OK");
});

// Only the publisher is created here; "executed" has not been printed yet.
StepVerifier.create(pending)
        .expectNext("OK")
        .verifyComplete();
```

This is an **illustrative snippet inside a test importing `Mono` and `StepVerifier`**, not a standalone Java file. When `StepVerifier` subscribes, `Mono.defer` runs and prints one `"executed"` line. Do not assume every `Mono.just(...)` likewise defers evaluating its argument expression: **the argument passed to `just` is evaluated eagerly at pipeline assembly time**.

## 3. Diagnostic Matrix: Application Error or Reactive Misuse?

| Symptom | Likely Category | Evidence to Look For | Resolution |
|---|---|---|---|
| `Mono.error(OrderNotFoundException)` | Business: not found | Exception type, order ID, HTTP mapping | `switchIfEmpty`/advice maps to 404 per contract |
| `IllegalArgumentException` from bad input | Input validation/business | Constraints and actual request | Return 400 for client error; validate before calling gateway |
| `R2dbcException`, connection refused, API call timeout | Infrastructure | Root cause, client logs, retry/timeout config | Return appropriate system error; do not disguise as 404 |
| `IllegalStateException` reporting `block()` disallowed on non-blocking thread | Reactor scheduler/thread misuse | Stack trace at `.block()`, thread name | Return publisher; remove `block` or offload blocking work properly |
| HTTP returns empty 200 despite async operation failing | Possible manual `.subscribe()` detached from response | Search for `.subscribe()`, `doOnError`, terminal response | Return the publisher so WebFlux manages error/completion |
| Side effect never ran despite creating `Mono` | No subscription, lazy publisher | Check with `StepVerifier`, inspect `doOnSubscribe` | Subscribe at the right boundary; never manually subscribe in services/controllers |
| Side effect ran twice | Multiple subscriptions on a cold source | Count subscriptions, network calls, repository calls | Avoid duplicate subscriptions; share/cache deliberately when truly needed |
| Request hangs, times out, low CPU | Non-completing publisher, blocking call, deadlock, or missing demand | Reactor signals, thread dump, timeout config | Locate blocking point and subscription/cancellation boundary |
| `ErrorCallbackNotImplemented` or error dropped | Subscriber lacked error consumer or signal lost consumer | Stack trace, subscribe call, Reactor logs | Return chain with proper error handler; verify terminal signals |
| `NullPointerException` from mock returning `null` instead of `Mono` | Mock/stubbing violates reactive contract | Mockito stubs, method return types | Return `Mono.just`, `Mono.empty`, `Mono.error` per case |

**Never diagnose from HTTP status alone.** A business error can be turned into 500 by a missing advice mapping; a gateway error can be accidentally masked as 200 or 404 by `onErrorResume`; a `.block()` error can also surface as 500. Inspect the **stack trace, signal path, operators, and handler logic**.

## 4. Where Does `.block()` Go Wrong?

`block()` subscribes to a `Mono` and **waits synchronously** for the result/completion. It can be fine at an **intentional synchronous boundary** (such as a CLI app or certain integration tests running on the test thread), yet it is an anti-pattern inside reactive controllers and pipelines running on a Reactor event loop.

### 4.1. Wrong: Blocking Inside a WebFlux Controller

```java
// INTENTIONALLY WRONG illustrative snippet placed in a WebFlux controller.
@GetMapping("/{id}")
public Mono<OrderView> find(@PathVariable String id) {
    OrderView order = reader.find(id).block();
    return Mono.just(order);
}
```

If this method is invoked on a Reactor thread marked non-blocking (common in Reactor Netty), calling `.block()` can throw `IllegalStateException` with a message like `"block()/blockFirst()/blockLast() are blocking, which is not supported in thread ..."`. Exact stack trace/thread names depend on the Reactor version, runtime, and execution path. If the thread is **not** marked non-blocking, `.block()` may still run while **hogging the thread and degrading throughput/latency** instead of throwing that exact exception.

There is another bug too: if `reader.find(id)` returns `Mono.empty()`, `.block()` returns `null`, and `Mono.just(null)` fails immediately. Never call `.block()` just to unwrap a reactive result into a Java value and re-wrap it in `Mono`.

### 4.2. Right: Return the Publisher

```java
// Correct snippet inside a controller with an injected reader.
@GetMapping("/{id}")
public Mono<OrderView> find(@PathVariable String id) {
    return reader.find(id);
}
```

WebFlux subscribes to the publisher and handles `onNext`, completion, or errors within the request lifecycle. As a result, `@ExceptionHandler`/global error handling gets the chance to process response errors properly.

### 4.3. `Thread.sleep` and Blocking JDBC Are Equally Dangerous

Blocking bugs are not limited to `.block()`. `Thread.sleep`, JDBC calls, synchronous `RestTemplate`, synchronous file writes, or a blocking SDK running on the event loop may **not throw `IllegalStateException`**, yet still tie up non-blocking threads and cause other requests to slow down or time out. These are often performance bugs invisible in simple unit tests.

If you must temporarily call a legacy blocking API, wrap the synchronous source:

```java
// Illustrative example: legacyClient.load(id) is a blocking operation
// from an existing dependency in the application.
Mono<OrderView> result =
        Mono.fromCallable(() -> legacyClient.load(id))
                .subscribeOn(Schedulers.boundedElastic());
```

This is a **non-standalone illustrative snippet**, requiring imports `Mono`, `Schedulers`, and a matching `legacyClient` type. `boundedElastic` offloads blocking work to a bounded scheduler; it **does not make the I/O non-blocking**, does not guarantee cancelling an in-flight JDBC call, and does not replace reactive drivers like R2DBC or `WebClient` when architecture permits.

**Wrong timing:**

```java
Mono<OrderView> wrong =
        Mono.just(legacyClient.load(id))
            .subscribeOn(Schedulers.boundedElastic());
```

`legacyClient.load(id)` is evaluated **before the `Mono` is created**, so `subscribeOn` comes too late to move the blocking call off the current thread. Use `Mono.fromCallable` or `Mono.defer` to defer the work properly.

## 5. Manual `.subscribe()` Can Break the HTTP Contract

In WebFlux-managed handlers and services, a common mistake is **subscribing manually** to a child publisher and returning another response:

```java
// INTENTIONALLY WRONG illustrative snippet: fire-and-forget without a clear contract.
@PostMapping("/orders/{id}/confirm")
public Mono<Void> confirm(@PathVariable String id) {
    confirmationService.confirm(id).subscribe();
    return Mono.empty();
}
```

Here the subscription created by `.subscribe()` has its **own independent lifecycle/error/cancellation**, detached from the publisher returned to WebFlux. The client may be told confirmation succeeded while it is still running or already failed. If the error lacks a matching error consumer, Reactor may log an unhandled error or emit `ErrorCallbackNotImplemented`/dropped-error messages depending on the situation.

The **right way when the HTTP contract requires waiting for confirmation to finish**:

```java
@PostMapping("/orders/{id}/confirm")
public Mono<Void> confirm(@PathVariable String id) {
    return confirmationService.confirm(id);
}
```

Both snippets only illustrate controller methods, assuming `confirmationService.confirm` returns `Mono<Void>`; they are not standalone programs. If a product genuinely requires **202 Accepted and background execution**, design a proper queue/job/outbox/error-lifecycle mechanism; never treat manual `subscribe()` in a request handler as durable job management.

### 5.1. Why Can a Second Subscription Trigger Side Effects Twice?

Most reactive sources are **cold**: each subscription can re-trigger DB reads, HTTP calls, or event emissions. Example:

```java
Mono<OrderView> order = reader.find("42");

// An extra subscriber, e.g., for logging:
order.subscribe(value -> audit(value));

// WebFlux also subscribes to the returned publisher:
return order;
```

This is an **anti-pattern snippet** inside a handler with `reader`/`audit`. Two subscriptions can cause **two upstream calls** and inconsistent states if underlying data changed. When you want to log while keeping a single pipeline, typically use:

```java
return reader.find("42")
        .doOnNext(value -> audit(value));
```

`doOnNext` is a side-effect callback when a signal passes through and **does not subscribe itself**. If `audit` performs blocking I/O, do not run it directly on the event loop; pick an appropriate architecture. `doOnNext` also does not await an asynchronous audit — if `audit` returns a publisher, compose it with `flatMap` or a matching operator.

### 5.2. Be Careful with cache/share

`Mono.cache()` can avoid re-executing upstream across multiple subscriptions to **the same cached `Mono`**. However, caching can also retain **empty or error results**, introduce stale data, hold user/tenant-specific results improperly, and alter cancellation semantics. Never blindly patch duplicate subscriptions with `cache()`. The right boundary is structuring the data flow for **one primary subscription** per request; use caching only when the contract permits sharing and lifetimes are designed explicitly.

## 6. Operators That Can Hide Application Errors

### 6.1. `doOnError` Only Observes, Never Handles

```java
return gateway.findById(id)
        .doOnError(error -> logger.warn(
                "order lookup failed", error));
```

This snippet belongs inside a component with `gateway` and `logger`. `doOnError` enables logging/metrics as `onError` passes through; it **does not** turn an error into success or stop the subscriber from receiving `onError`.

### 6.2. `onErrorResume` Swaps the Publisher and Can Change Error Meaning

```java
return gateway.findById(id)
        .onErrorResume(OrderNotFoundException.class,
                error -> Mono.empty());
```

This line turns a **not-found error** into an **empty completion**. That is valid only if the caller contract expects absence as empty; in a controller where the contract requires HTTP 404, empty must still be converted to 404 or `ResponseEntity.notFound()`. Writing `onErrorResume(error -> Mono.empty())` for **all exceptions** can mask DB/API connection failures as an empty 200 — dangerous in production.

### 6.3. `onErrorMap` Translates Error Types Without Swallowing Errors

```java
return gateway.findById(id)
        .onErrorMap(GatewayTimeoutException.class,
                error -> new ServiceUnavailableException(
                        "read service unavailable", error));
```

This illustrates hypothetical application exception classes. Carefully classify which errors may be translated; never map arbitrary `IllegalStateException` or `.block()` failures into "order not found".

### 6.4. `onErrorComplete` Can Cause False-Green Tests

`onErrorComplete()` converts an error terminal signal into a complete terminal signal. If used to "fix" a test failing with `IllegalStateException` due to blocking, you **hid the symptom** rather than fixing the design. Only use it when the contract **explicitly accepts ignoring errors** on a bounded branch with proper logging/monitoring.

### 6.5. `map` Differs from `flatMap` When the Callback Returns a Mono

Structurally wrong:

```java
Mono<Mono<OrderView>> nested =
        Mono.just("42").map(id -> reader.find(id));
```

`nested` emits **an inner `Mono`** without ever subscribing to fetch `OrderView`. Correct when composing async operations:

```java
Mono<OrderView> flattened =
        Mono.just("42").flatMap(id -> reader.find(id));
```

These are snippets within a scope having `reader`. If a test only runs `expectNextMatches(value -> value != null)` on `Mono<Mono<...>>`, it can pass without proving the order lookup **actually executed**. Assert the exact type and final value.

## 7. Runnable Java 17+ Example: Separating Business Errors from Gateway Errors via StepVerifier

### 7.1. Structure and Conditions

The following example models an order-reading service returning `Mono<OrderView>` and distinguishing:

- Blank `id` → `InvalidOrderIdException`.
- Missing order → `OrderNotFoundException`.
- Gateway infrastructure failure → **preserve system error**, never pretend "not found".
- Success → exact `OrderView`.
- Gateway invocation deferred until **subscription**; test proves it with Mockito.
- Two subscriptions to a cold source can invoke the gateway twice.

Uses Java 17+, Spring Boot 3.4/3.5, `spring-boot-starter-webflux`, `spring-boot-starter-test`, and `reactor-test`. Files reside in package `com.example.reactiveerrors`. The `OrderReaderTest` unit test **does not start a Spring context**, using only Reactor + JUnit Jupiter + Mockito.

Illustrative Gradle Groovy DSL configuration in a project already configuring the Boot plugin, Java 17+, and Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a `build.gradle` fragment, not a standalone build script. In Maven, use the Spring Boot BOM/parent to align dependency versions and Surefire for JUnit Jupiter.

### 7.2. Data Types and Exceptions

File `src/main/java/com/example/reactiveerrors/OrderView.java`:

```java
package com.example.reactiveerrors;

public record OrderView(String id, String state) {}
```

File `src/main/java/com/example/reactiveerrors/OrderNotFoundException.java`:

```java
package com.example.reactiveerrors;

public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String id) {
        super("Order " + id + " not found");
    }
}
```

File `src/main/java/com/example/reactiveerrors/InvalidOrderIdException.java`:

```java
package com.example.reactiveerrors;

public final class InvalidOrderIdException extends RuntimeException {
    public InvalidOrderIdException() {
        super("Order id must not be blank");
    }
}
```

Dedicated exception types for business failures allow the API layer to map them to 404 or 400 intentionally. Do not distinguish errors solely by matching substrings of `getMessage()`, as messages can change with locale or refactoring.

### 7.3. Gateway Contract and Real Service

File `src/main/java/com/example/reactiveerrors/OrderGateway.java`:

```java
package com.example.reactiveerrors;

import reactor.core.publisher.Mono;

public interface OrderGateway {
    Mono<OrderView> findById(String id);
}
```

File `src/main/java/com/example/reactiveerrors/OrderReader.java`:

```java
package com.example.reactiveerrors;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReader {

    private final OrderGateway gateway;

    public OrderReader(OrderGateway gateway) {
        this.gateway = gateway;
    }

    public Mono<OrderView> find(String rawId) {
        if (rawId == null || rawId.isBlank()) {
            return Mono.error(new InvalidOrderIdException());
        }

        String normalizedId = rawId.trim();

        return Mono.defer(() -> gateway.findById(normalizedId))
                .switchIfEmpty(Mono.error(
                        () -> new OrderNotFoundException(normalizedId)));
    }
}
```

**Why is this code helpful for diagnosis?**

- Invalid input is represented as an **error signal**. Callers can assert `onError` without catching synchronous exceptions at `find` invocation time.
- `Mono.defer(...)` defers calling `gateway.findById` until the publisher is subscribed. If the gateway method throws synchronously inside `defer`, Reactor converts it into an error signal for the subscriber.
- `switchIfEmpty` only handles **publishers completing with no item**, and never turns `onError` into "not found".
- Gateway errors like `IllegalStateException("gateway unavailable")` **propagate unchanged**; this is an infrastructure error to handle at the appropriate level rather than turning it into 404.
- `OrderReader` is the real service. In the unit test, only `OrderGateway` is mocked.

One subtle point: `Mono.defer` typically produces a cold publisher, so **each subscription** can invoke the gateway again. That is intentional here to teach subscription lifecycle; never assume every publisher runs only once across subscribers.

### 7.4. In-Memory Gateway So the Sample App Can Boot

File `src/main/java/com/example/reactiveerrors/InMemoryOrderGateway.java`:

```java
package com.example.reactiveerrors;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class InMemoryOrderGateway implements OrderGateway {

    @Override
    public Mono<OrderView> findById(String id) {
        return Mono.defer(() -> {
            if ("42".equals(id)) {
                return Mono.just(new OrderView("42", "PAID"));
            }
            return Mono.empty();
        });
    }
}
```

This is a **local fake repository requiring no database**. Do not equate a fake returning `Mono` with a real R2DBC driver. When running the app, ID `42` succeeds; other IDs return empty so `OrderReader` turns them into a business error.

File `src/main/java/com/example/reactiveerrors/ReactiveErrorsApplication.java`:

```java
package com.example.reactiveerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorsApplication.class, args);
    }
}
```

The application sits in the parent package of the example classes so Spring discovers the controller, service, advice, and gateway. It is a minimal runnable WebFlux app when dependencies/runtime are valid, without a real database.

### 7.5. Unit Test: StepVerifier Asserting Terminal Signals

File `src/test/java/com/example/reactiveerrors/OrderReaderTest.java`:

```java
package com.example.reactiveerrors;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderReaderTest {

    @Mock
    OrderGateway gateway;

    @Test
    void gatewayIsNotCalledUntilSubscription() {
        OrderView expected = new OrderView("42", "PAID");
        when(gateway.findById("42"))
                .thenReturn(Mono.just(expected));

        OrderReader reader = new OrderReader(gateway);
        Mono<OrderView> result = reader.find(" 42 ");

        // Assembly only; result has not been subscribed yet.
        verifyNoInteractions(gateway);

        StepVerifier.create(result)
                .expectNext(expected)
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("42");
    }

    @Test
    void emptyGatewayResultBecomesNotFoundError() {
        when(gateway.findById("404"))
                .thenReturn(Mono.empty());

        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find("404"))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            OrderNotFoundException.class, error);
                    assertEquals(
                            "Order 404 not found",
                            error.getMessage());
                })
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("404");
    }

    @Test
    void invalidIdReturnsInputErrorWithoutGatewayCall() {
        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find(" "))
                .expectError(InvalidOrderIdException.class)
                .verify(Duration.ofSeconds(3));

        verifyNoInteractions(gateway);
    }

    @Test
    void gatewayFailureIsNotMisreportedAsNotFound() {
        when(gateway.findById("42")).thenReturn(
                Mono.error(new IllegalStateException(
                        "gateway unavailable")));

        OrderReader reader = new OrderReader(gateway);

        StepVerifier.create(reader.find("42"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "gateway unavailable".equals(
                                error.getMessage()))
                .verify(Duration.ofSeconds(3));

        verify(gateway).findById("42");
    }

    @Test
    void twoSubscriptionsCanRepeatColdSourceWork() {
        AtomicInteger sourceSubscriptions = new AtomicInteger();
        when(gateway.findById("42")).thenAnswer(call ->
                Mono.defer(() -> {
                    sourceSubscriptions.incrementAndGet();
                    return Mono.just(new OrderView("42", "PAID"));
                }));

        OrderReader reader = new OrderReader(gateway);
        Mono<OrderView> pending = reader.find("42");

        StepVerifier.create(pending)
                .expectNext(new OrderView("42", "PAID"))
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        StepVerifier.create(pending)
                .expectNext(new OrderView("42", "PAID"))
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertEquals(2, sourceSubscriptions.get());
        verify(gateway, times(2)).findById("42");
    }
}
```

### 7.6. What the Tests Actually Prove

| Test Case | Warranted Conclusion |
|---|---|
| `gatewayIsNotCalledUntilSubscription` | Service builds a lazy publisher; gateway is only invoked when `StepVerifier` subscribes |
| `emptyGatewayResultBecomesNotFoundError` | Empty becomes `OrderNotFoundException`, not HTTP 404 directly |
| `invalidIdReturnsInputErrorWithoutGatewayCall` | Bad input emits the right error signal; gateway is never called |
| `gatewayFailureIsNotMisreportedAsNotFound` | Infrastructure failure stays distinct from business errors |
| `twoSubscriptionsCanRepeatColdSourceWork` | Two subscribers can re-trigger upstream and source side effects |

**There is no `System.out.println` in these tests**, so there is no fixed stdout to expect. With compatible dependencies and the example code above, the five tests are designed to pass; actually run them in a project before reporting they passed.

`StepVerifier.verify(Duration.ofSeconds(3))` provides a time bound on verification, failing if the pipeline never finishes. It **does not** turn a blocking operation into non-blocking or automatically detect all deadlocks. When testing complex time operators, use `StepVerifier.withVirtualTime` per Reactor docs, constructing publishers compatibly with the virtual scheduler.

## 8. Testing the HTTP Contract: Mapping Business Errors to 404 via WebFlux

A service test proves `OrderNotFoundException` is emitted as `onError`; it does not yet prove the client receives HTTP 404. That is the job of the controller/advice and is tested with `WebTestClient`.

### 8.1. Controller Returning the Publisher Without Blocking or Subscribing

File `src/main/java/com/example/reactiveerrors/OrderController.java`:

```java
package com.example.reactiveerrors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderReader reader;

    public OrderController(OrderReader reader) {
        this.reader = reader;
    }

    @GetMapping("/{id}")
    public Mono<OrderView> find(@PathVariable("id") String id) {
        return reader.find(id);
    }
}
```

The controller does not call `.block()`, `.subscribe()`, or `.toFuture().get()`: the publisher is managed by WebFlux within the request lifecycle.

### 8.2. Advice Separating Business 404 from Input 400

File `src/main/java/com/example/reactiveerrors/OrderErrorAdvice.java`:

```java
package com.example.reactiveerrors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            OrderNotFoundException error) {
        return ResponseEntity.status(404)
                .body(Map.of("code", "ORDER_NOT_FOUND"));
    }

    @ExceptionHandler(InvalidOrderIdException.class)
    public ResponseEntity<Map<String, String>> invalidId(
            InvalidOrderIdException error) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_ORDER_ID"));
    }
}
```

Only two business exceptions are mapped here. An `IllegalStateException("gateway unavailable")` from the gateway is not turned into 404/400 by this advice; the application delegates unmapped errors to global error handling, typically a server error. The final HTTP code depends on exception handler and error attribute configuration, so never assert a concrete 500 JSON payload without verifying it.

### 8.3. Web Slice Test with WebTestClient

File `src/test/java/com/example/reactiveerrors/OrderControllerWebFluxTest.java`:

```java
package com.example.reactiveerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = OrderController.class)
class OrderControllerWebFluxTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    OrderReader reader;

    @Test
    void successfulPublisherBecomesHttp200WithJson() {
        when(reader.find("42"))
                .thenReturn(Mono.just(
                        new OrderView("42", "PAID")));

        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.state").isEqualTo("PAID");

        verify(reader).find("42");
    }

    @Test
    void businessErrorBecomesHttp404WithStableCode() {
        when(reader.find("404")).thenReturn(
                Mono.error(new OrderNotFoundException("404")));

        client.get()
                .uri("/api/orders/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("ORDER_NOT_FOUND");

        verify(reader).find("404");
    }
}
```

With Spring Boot 3.4/3.5 and Spring Framework 6.2+, `@MockitoBean` belongs to `org.springframework.test.context.bean.override.mockito`. On older Boot versions, that annotation may not exist; use the version's matching mock bean mechanism. `@WebFluxTest` loads the controller/advice within the web slice and usually auto-configures a context-bound `WebTestClient`, **without opening a real HTTP port**.

Both web tests are designed to pass when WebFlux/Jackson and advice are loaded properly. They prove the HTTP status/JSON contract of the reactive handler running with a **mock** reader, not that the real `OrderReader` was invoked. Therefore, keep **both the Section 7 `StepVerifier` service test and the Section 8 `WebTestClient` test** to verify both boundaries.

## 9. Verifying Whether Blocking Actually Happens: Do Not Equate with Business Errors

When suspecting a hanging request caused by blocking, a useful investigation sequence is:

1. Trace the **path**: WebFlux controller → service → gateway/client → which operators.
2. Search for `.block()`, `.blockFirst()`, `.blockLast()`, `Thread.sleep`, `Future.get()`, sync JDBC, sync SDKs, or `RestTemplate` inside handlers/reactive callbacks.
3. Read the root-cause exception. Reactor messages about `"blocking is not supported in thread ..."` point to calling a blocking Reactor API on a non-blocking thread; a `ReadTimeoutException` may be a network error, not proof that `.block()` occurred.
4. Inspect thread names and thread dumps if latency/timeouts happen **without an exception**. A Netty event-loop thread held by blocking I/O can stall many requests without throwing `IllegalStateException`.
5. Check which operator is subscribed and where work begins. `publishOn`/`subscribeOn` affect scheduling differently; placing a scheduler after an eager call does not fix blocking that already happened.
6. Verify with behavioral tests, timeout bounds, and telemetry; never just add `onErrorResume` to swallow errors.

### 9.1. subscribeOn vs publishOn

- `subscribeOn(scheduler)` affects the execution context of **subscription/upstream requests** and is typically placed near a blocking source wrapped in `fromCallable`. It does not make I/O non-blocking.
- `publishOn(scheduler)` switches **downstream signals** onto the specified scheduler from that operator onward. It cannot "go back in time" to move a blocking call already executed at assembly time.
- Misconfigured schedulers can create bottlenecks or increase latency. Use `boundedElastic` intentionally for hard-to-replace blocking parts, preferring `WebClient`/R2DBC for non-blocking paths where appropriate.

### 9.2. BlockHound Is a Supporting Tool, Not Automatic Proof

In some Reactor projects, **BlockHound** can detect known blocking APIs when they execute on threads marked non-blocking. However, it is an external tool requiring instrumentation and compatibility with your JDK/agent/runtime. Never claim "having Reactor means every JDBC call or `sleep` throws automatically" — that is false. Testing should rely on thread observation, profiling, latency, and call paths, combined with BlockHound where versions/infrastructure permit.

## 10. Diagnosing Subscriptions and Error Timing

A pipeline can be assembled at time A and only executed at time B. That is why stack traces sometimes contain two regions: the **assembly site** and the **subscription/execution site**.

Helpful Reactor tools:

| Tool | What It Tells You | Note |
|---|---|---|
| `doOnSubscribe` | Publisher began receiving a subscriber | For observation, does not create a subscription itself |
| `doOnNext` | `onNext` value passed through | Does not see empty or error signals when no value arrives |
| `doOnError` | Error passed through this operator | Does not handle the error; error continues downstream |
| `doFinally` | Terminated via complete, error, or cancel | Useful for terminal cleanup/metrics |
| `checkpoint("read-order")` | Adds an assembly marker to locate failing pipelines | Has overhead; pick meaningful checkpoints |
| `log()` | Observes subscribe/request/onNext/onError/cancel | Watch log noise and sensitive data |
| `Hooks.onOperatorDebug()` | Captures broad assembly stack information | High overhead; never leave on unconditionally in production |
| `StepVerifier` | Subscriber verifying signals | Does not replace WebFlux HTTP tests |
| `WebTestClient` | Per-request status/headers/body | Does not auto-catch errors inside fire-and-forget side subscriptions |

Illustrative example in a service with `gateway`:

```java
return gateway.findById(id)
        .checkpoint("lookup-order-" + id)
        .doOnSubscribe(subscription ->
                logger.debug("subscribed order lookup"))
        .doOnError(error ->
                logger.warn("lookup failed", error));
```

`logger` is the application's logging dependency (non-standalone snippet). In production, avoid putting secret IDs, tokens, payloads, or sensitive info into checkpoints/logs unnecessarily. Never enable JVM-wide debug hooks as a business fix.

An `ErrorCallbackNotImplemented` exception usually hints a subscriber lacked an error consumer. An `onErrorDropped` message can relate to a signal with no remaining downstream consumer, such as after cancellation or an error inside a publisher outside HTTP management. **Do not jump to a single certainty from a log message**; inspect `.subscribe(...)`, operators, cancellation, and failure conditions.

## 11. Testing Reactive Code Properly: StepVerifier, WebTestClient, and Timeouts

### 11.1. StepVerifier Tests Publishers at the Signal Level

A test writing only:

```java
reader.find("404");
```

usually only **assembles the publisher** without subscribing; if `find` returns `Mono.defer`, the gateway has not even run. That test cannot prove `OrderNotFoundException` was emitted.

A test writing only:

```java
reader.find("404").subscribe();
```

creates a subscription **with no assertions**, no waiting for completion, and no error consumer. It can finish before the error occurs or log an error from another thread.

Use:

```java
StepVerifier.create(reader.find("404"))
        .expectError(OrderNotFoundException.class)
        .verify(Duration.ofSeconds(3));
```

This is an illustrative snippet from a test with a properly constructed `reader` and Reactor Test imports. `StepVerifier` subscribes, receives the terminal signal, and verifies the condition within a time limit. To check messages/causes, use `expectErrorSatisfies` as in the full code in Section 7.

### 11.2. Mono<Void> and Flux Need Matching Assertion Styles

- A successful `Mono<Void>` normally **emits no `onNext`**: use `StepVerifier.create(publisher).verifyComplete()` or `expectComplete().verify(timeout)` as needed.
- `Mono.empty()` completes empty, distinct from `Mono.error`. Do not treat empty completion as proof of not-found unless the contract defines it so.
- `Flux<T>` has multiple `onNext` signals; `expectNext`, `expectNextCount`, `recordWith`, and `consumeRecordedWith` help verify items and ordering. When order is not guaranteed by contract or scheduler, pick a looser assertion that still checks occurrence counts when needed.
- `never()` publishers never finish: tests need intentional cancel/timeout; waiting forever has no value.
- For long-running streams/SSE, clients and tests must handle cancellation, backpressure, and timeouts rather than waiting forever for `verifyComplete()`.

### 11.3. WebTestClient Verifies the API, Not Replacing Service Tests

`WebTestClient` checks HTTP status, headers, and JSON. With `@WebFluxTest` + a mock service, it can prove the 404 mapping of `OrderNotFoundException` yet **cannot prove** the real gateway does not block or double-subscribe. Conversely, `StepVerifier` checks the real `OrderReader`, yet **does not check** the HTTP error schema.

To verify real HTTP over the network, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with a server-bound `WebTestClient`, distinct from a slice's context-bound client. If bugs appear only under load/concurrency due to starving the Netty event loop, add integration/performance tests measuring real latency/throughput in a controlled environment.

### 11.4. Do Not Let Timeouts Become a Way to Hide Bugs

`timeout(Duration)` in a reactive pipeline can emit `TimeoutException` when things take too long. However, it does not fix blocking I/O or detached subscriptions with independent lifecycles. In tests, use `verify(Duration)`/response timeouts to prevent hangs; in production, choose timeouts/retries/bulkheads and error mappings per contract.

**Retries must be conditional:** `retryWhen` on transient network errors can make sense, whereas retrying validation/business errors is usually pointless. On POST order creation, retrying without an idempotency key can duplicate side effects. Never add unbounded retries just to paper over races or broken subscriptions.

## 12. Running the Suite and Inspecting Signals Instead of Only a Green Build

With Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.reactiveerrors.OrderReaderTest"
./gradlew test --tests "com.example.reactiveerrors.OrderControllerWebFluxTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactiveerrors.OrderReaderTest"
.\gradlew.bat test --tests "com.example.reactiveerrors.OrderControllerWebFluxTest"
```

With Maven wrapper on Linux/macOS:

```bash
./mvnw -Dtest=OrderReaderTest test
./mvnw -Dtest=OrderControllerWebFluxTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=OrderReaderTest test
.\mvnw.cmd -Dtest=OrderControllerWebFluxTest test
```

Commands assume the project has wrappers, Java 17+, Spring Boot 3.4/3.5, and compatible Maven/Gradle/JUnit Platform. Gradle's `test` task typically outputs HTML reports at `build/reports/tests/test/index.html`; Maven Surefire puts reports in `target/surefire-reports/`. In multi-module projects, run the appropriate task/module.

When reviewing reports, confirm:
1. The exact **class names and test counts** were discovered (five service tests, two web slice tests in the example).
2. `StepVerifier` subscribed and checked **`onError`/`onComplete`** rather than just building a publisher.
3. `WebTestClient` asserted status/JSON per contract (200 and 404 in the example).
4. No ignored `timeout`, dropped-error, or Reactor scheduler exceptions appeared in logs.
5. No test was **SKIPPED**, `NO-SOURCE`, or relied solely on build cache without an actual execution check.

There is no fixed business stdout in these tests. **Do not claim code was executed** merely because it was written; run it and read the real report for PASS evidence.

## 13. Real-World Scenarios: Is the Bug in Domain, Gateway, or Subscription?

### Scenario A: Order Not Found

**Signals:** gateway `Mono.empty()`, service `switchIfEmpty(Mono.error(OrderNotFoundException))`, advice maps 404.

**Test:** `StepVerifier` asserts `OrderNotFoundException`; `WebTestClient` asserts HTTP 404 and `code=ORDER_NOT_FOUND`.

**Do not fix by:** returning a fake `Mono.just(new OrderView(...))` or swallowing 404 into an empty 200 when the API contract requires 404.

### Scenario B: Temporary Gateway Disconnect

**Signals:** gateway `Mono.error(ConnectionException/TimeoutException)`; service does not turn it into not-found.

**Test:** `StepVerifier` asserts exact type/cause, checks retry policy if present; appropriate integration tests verify 503/500 error mapping.

**Do not fix by:** `onErrorResume(e -> Mono.empty())` across all exceptions, as it hides incidents.

### Scenario C: Controller Calls block() on the Event Loop

**Symptoms:** Reactor blocking-call restriction exception or latency/event-loop stall if the blocking API is not intercepted.

**Test:** audit controller path, stack traces, thread names; test WebFlux with proper publishers and run concurrency/performance tests when needed. Do not expect a single isolated test to catch every blocking source automatically.

**Fix:** return the publisher and keep calls non-blocking, or wrap legacy blocking sources with `fromCallable(...).subscribeOn(boundedElastic())` during architectural migration.

### Scenario D: Manual subscribe() to Send Email/Audit

**Symptoms:** response succeeds before the task finishes; errors appear only in logs detached from the response; unclear retry/cancellation semantics.

**Test:** verify the publisher is composed into the `Mono<Void>` response if the contract waits for it; for true async jobs, verify queue/outbox publishing and job status independently.

**Fix:** `return emailService.send(...)` or use a designed queue/outbox; do not casually fire-and-forget inside handlers.

### Scenario E: Test Never Subscribes and Assumes Everything Ran

**Symptoms:** test is green even though the gateway was never called and loggers inside `Mono.defer` never ran.

**Fix:** use `StepVerifier` with expectations and timeouts; `verify` interactions after subscription when proving side effects.

### Scenario F: Two Subscriptions Trigger Two Charges

**Symptoms:** the same business operation runs twice from a cold publisher; logs/metrics show two subscriptions.

**Fix:** never attach a second subscriber just for logging; use `doOnNext`, `doOnError`, or structure the pipeline with one source and one consumer; if sharing, define explicit idempotency and lifecycle policies. For writes, enforce business-level idempotency rather than relying on local `Mono.cache()`.

## 14. Common Diagnostic Mistakes

| Mistake | Why It Leads to Wrong Conclusions | Fix |
|---|---|---|
| Seeing 500 and assuming it is a business error | 500 can also come from `.block()`, codecs, gateway, or config | Inspect root cause, thread, signal, and mappings |
| `Mono.error` created yet test never subscribes | Error signal may never have been emitted | Use `StepVerifier` and assert terminal signal |
| `subscribe()` in controller then `return Mono.empty()` | Side-task error is detached from the response | Return the proper publisher or design an explicit async job |
| `subscribe()` to "kick off" a cold publisher and still return it | Can execute upstream twice | Keep a single WebFlux-managed subscription |
| `Mono.just(blockingCall())` then `subscribeOn(boundedElastic)` | Blocking already ran at assembly time | Use `Mono.fromCallable` for blocking sources |
| Believing `block()` always throws `IllegalStateException` | On threads not marked non-blocking, it can just stall silently | Never block in handlers; measure threads/latency |
| Using `map` returning `Mono<Mono<T>>` | Inner publisher was never flattened | Use `flatMap` when callbacks return publishers |
| Using `onErrorComplete()` to make tests green | Swallowing errors can hide incidents | Classify and handle errors per contract |
| Treating `doOnError` as an exception handler | It only observes errors | Preserve downstream error or use conditional `onErrorResume` |
| Assuming `Mono.empty()` means HTTP 404 | Empty carries no status code | Map with `switchIfEmpty`/`ResponseEntity` per API |
| Mockito mock reactive method returns null | Handler hits unrelated NPE | Stub with non-null publishers |
| Testing only `WebTestClient` with mock service | Fails to verify whether real reactive service blocks or double-subscribes | Add `StepVerifier` service/integration tests |
| `verifyComplete()` on an infinite `Flux` | Test may never finish | Cancel subscription or bound stream/timeout |
| Relying on stdout/logs as the sole assertion | Logs can be missing or filtered | Assert values, error types, status, and interactions |
| `retryWhen` for every exception | May retry validation or duplicate side effects | Retry only transient errors, enforce idempotency |
| Using single JVM assumptions for `ThreadLocal` context | Reactive execution has its own schedulers/context | Trace execution paths and use Reactor Context properly |

## 15. Checklist Before Concluding a WebFlux Test Protects Against the Right Failures

- [ ] Clearly separated **business validation/not-found**, **downstream infrastructure errors**, and **reactive programming misuse**.
- [ ] Controllers/services return `Mono`/`Flux` to the framework, without gratuitous `.block()` or `.subscribe()` on request paths.
- [ ] When forced to call legacy blocking APIs, placed the call in a lazy publisher on an appropriate scheduler, never eagerly inside `Mono.just`.
- [ ] Service tests use `StepVerifier` that **actually subscribes**, asserts `onNext/onError/onComplete`, and sets an appropriate timeout.
- [ ] HTTP tests use `WebTestClient` asserting status, headers, and error JSON; never conflate mock slice results with real service behavior.
- [ ] `Mono.empty()` is mapped per contract; never assumed to mean 404 automatically.
- [ ] Gateway errors are not swallowed by overly broad `onErrorResume`/`onErrorComplete`.
- [ ] Checked for duplicate subscriptions causing duplicate side effects when business operations are sensitive.
- [ ] `doOnError` or `log` is not treated as error handling or error testing.
- [ ] Checked schedulers/threads when suspecting blocking rather than guessing from status codes.
- [ ] For streaming, handled cancellation/backpressure and avoided unbounded waits.
- [ ] Executed the exact test tasks/classes and inspected reports rather than claiming PASS from illustrative snippets alone.

**Conclusion:** In Spring WebFlux, distinguish **errors intentionally emitted by the application** from **errors caused by improper subscription or thread management**. Domain `Mono.error`, gateway failures, and `IllegalStateException` from `.block()` on the event loop mean very different things. To diagnose reliably, maintain **one WebFlux-subscribed reactive pipeline**, avoid fire-and-forget `.subscribe()` in handlers, never block on the event loop, use `StepVerifier` to check signals and `WebTestClient` to check the HTTP contract, and cross-check threads, stack traces, and emitted data.
