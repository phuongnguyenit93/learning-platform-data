# StepVerifier and Expected Signal Scenarios in Reactor

> **Module:** Spring Framework – reactive  
> **Parent topic:** Reactor Testing  
> **Focus:** testing `Mono`/`Flux` with `reactor-test` using `StepVerifier`, accurately describing Reactive Streams signal sequences, verifying completion/error, backpressure, virtual time, cancellation, and Reactor Context. Includes standalone examples, a Spring Boot 4.0.9/Java 17+ project, JUnit 5, `WebTestClient`, `TestPublisher`, and `PublisherProbe`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the signals `onSubscribe`, `onNext`, `onError`, `onComplete` and the actions `request(n)`/`cancel()`.
2. Write a `StepVerifier` scenario in the expected order instead of calling `.block()` to check values manually.
3. Verify the exact count, values, ordering, and terminal signal of `Mono`/`Flux`.
4. Assert errors by type, message, and business condition; avoid mistaking an empty stream for an error.
5. Write custom per-element assertions using `expectNextMatches`, `assertNext`, and `consumeNextWith`.
6. Test demand/backpressure with `initialRequest(0)` and `thenRequest(n)`.
7. Test `delay`, `interval`, `timeout`, and `retry` using **virtual time** instead of waiting real seconds or minutes.
8. Verify Reactor `Context` propagation using `StepVerifierOptions.withInitialContext(...)`.
9. Create a manually controlled upstream with `TestPublisher` and verify fallback branches with `PublisherProbe`.
10. Verify cancellation signals and cleanup, avoiding the assumption that `cancel` is `onComplete`.
11. Set finite timeouts and clear failure messages to prevent hanging tests.
12. Combine service unit tests with HTTP contract tests using `WebTestClient` in a Spring WebFlux application.

**Key takeaway:** a good Reactor test describes the **entire signal sequence**, not just a final value. `StepVerifier` is a test subscriber; it activates the publisher when `verify()` runs and asserts what the subscriber actually receives.

## 2. Before Testing: The Reactive Streams Signal Contract

When subscribed to, a publisher creates a `Subscription`. The subscriber can request data (`request(n)`), receive zero or many values, and finally receive **one** normal completion or error signal.

~~~text
Publisher                      Subscriber / StepVerifier
    |                                    |
    |-------- onSubscribe(s) ----------->|
    |<------- request(1) ----------------|
    |-------- onNext(A) ---------------->|
    |<------- request(2) ----------------|
    |-------- onNext(B) ---------------->|
    |-------- onNext(C) ---------------->|
    |-------- onComplete() ------------->|
    |                                    |
~~~

On error:

~~~text
onSubscribe -> onNext(A) -> onError(IllegalStateException)
~~~

When empty:

~~~text
onSubscribe -> onComplete
~~~

When the subscriber cancels:

~~~text
onSubscribe -> onNext(A) -> cancel
~~~

Rules to remember:

- `Flux<T>` can emit `0..N` elements and one terminal signal.
- `Mono<T>` can emit at most **one** `onNext`, followed by `onComplete`, or terminate with `onError`.
- `onError` and `onComplete` are **mutually exclusive** within a subscription; no valid signals follow a terminal signal.
- `null` is not a valid Reactive Streams `onNext` value. `Mono.empty()` represents the absence of a value, not `Mono.just(null)`.
- `request(n)` regulates downstream demand, not `onNext` signals from the publisher.
- `cancel()` is a subscriber action; do **not** expect the publisher to send `onComplete` after cancellation.
- A cold publisher may run again on each test verification/subscription; operations with side effects need to be controlled.

`StepVerifier` describes signals at the subscriber level. It does not by itself prove that database results were committed or that HTTP traffic passed through a production proxy; those require separate integration tests.

## 3. Dependencies and Getting Started with StepVerifier

`StepVerifier`, `TestPublisher`, and `PublisherProbe` belong to the **`io.projectreactor:reactor-test`** artifact, typically used only in `test` scope. In Spring Boot 4.0.x, you can rely on Boot's dependency management instead of declaring the version manually.

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class FirstStepVerifierTest {

    @Test
    void fluxEmitsTwoValuesThenCompletes() {
        Flux<String> source = Flux.just("A", "B");

        StepVerifier.create(source)
            .expectNext("A")
            .expectNext("B")
            .verifyComplete();
    }

    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<Integer> source = Mono.just(42);

        StepVerifier.create(source)
            .expectNext(42)
            .verifyComplete();
    }
}
~~~

`verifyComplete()` both expects `onComplete` after the declared steps and triggers verification. Equivalent explicit scenario:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A", "B")
    .expectComplete()
    .verify();
~~~

**A terminal trigger step is mandatory**: `verify()`, `verify(Duration)`, `verifyComplete()`, `verifyError()`, or `verifyThenAssertThat()`. Calling only `StepVerifier.create(...).expectNext(...)` without verifying means the test never executes the scenario.

## 4. Structure of a Scenario

~~~java
StepVerifier.create(publisher)
    .expectSubscription()
    .expectNext(expectedValue)
    .expectNextMatches(value -> predicate(value))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Parts:

1. `create` accepts an already-created `Publisher`. `withVirtualTime` accepts a supplier to construct the publisher **inside** the virtual time environment.
2. `expectSubscription` confirms `onSubscribe`.
3. `expectNext`/`assertNext`/`expectNextMatches` checks values or predicates.
4. `expectComplete`, `expectError...`, or `thenCancel` ends the scenario.
5. `verify(Duration.ofSeconds(...))` actually runs and waits within a bounded duration.

### 4.1. From One Value to Terminal

| Actual publisher | Expected scenario | Meaning |
| --- | --- | --- |
| `Mono.just(7)` | `expectNext(7) → verifyComplete()` | One value then completion |
| `Mono.empty()` | `verifyComplete()` | Empty yet successful |
| `Flux.just(1,2,3)` | `expectNext(1,2,3) → verifyComplete()` | Three values in exact order |
| `Mono.error(ex)` | `expectError(...) → verify()` | Terminates with an error |
| `Flux.concat(Flux.just(1), Mono.error(ex))` | `expectNext(1) → expectError(...) → verify()` | Data emitted before error |
| `Flux.never()` | `thenCancel() → verify()` | No terminal; test cancels itself |

If `Flux.just(1,2,3)` is tested with `expectNext(1,2).verifyComplete()`, the test **must fail**, because element `3` arrives before `onComplete`. This is a good check: it prevents accidentally ignoring unexpected elements.

## 5. Value Expectation APIs

### 5.1. `expectNext(T...)`

Checks equality (typically `equals`) against expected values while preserving order.

~~~java
StepVerifier.create(Flux.just("new", "validated", "saved"))
    .expectNext("new", "validated", "saved")
    .verifyComplete();
~~~

With Java `record` types, field-by-field equality is very convenient:

~~~java
record OrderView(long id, String state) {}

StepVerifier.create(Mono.just(new OrderView(3L, "READY")))
    .expectNext(new OrderView(3L, "READY"))
    .verifyComplete();
~~~

### 5.2. `expectNextCount(long)`

When you only care about the number of subsequent elements:

~~~java
StepVerifier.create(Flux.range(1, 100))
    .expectNext(1)
    .expectNextCount(98)
    .expectNext(100)
    .verifyComplete();
~~~

This operator only counts and consumes that exact number of elements; it **does not check the contents** of the 98 elements in the middle. Use it only when individual element contents truly do not matter. For business logic requiring order or value verification, use `expectNextSequence`, `expectNextMatches`, or detailed assertions.

### 5.3. `expectNextMatches(Predicate<T>)`

~~~java
StepVerifier.create(Mono.just(new OrderView(5L, "READY")))
    .expectNextMatches(order ->
        order.id() > 0 && "READY".equals(order.state()))
    .verifyComplete();
~~~

The predicate must return `true`; if it returns `false`, the scenario fails. Do not perform significant side effects inside the predicate, as its purpose is to validate conditions.

### 5.4. `assertNext` / `consumeNextWith`

`assertNext` lets you use JUnit or AssertJ assertions for clearer failure messages:

~~~java
StepVerifier.create(Mono.just(new OrderView(8L, "PAID")))
    .assertNext(order -> {
        org.junit.jupiter.api.Assertions.assertEquals(
            8L, order.id());
        org.junit.jupiter.api.Assertions.assertEquals(
            "PAID", order.state());
    })
    .verifyComplete();
~~~

`consumeNextWith` also accepts a `Consumer<T>` to inspect or process the element. With `assertNext`, an `AssertionError` thrown by an inner assertion is propagated back to the test. StepVerifier's `as("...")` does not necessarily inject its description into an exception thrown directly by an assertion library.

### 5.5. `expectNextSequence(Iterable<T>)`

~~~java
StepVerifier.create(Flux.just("a", "b", "c"))
    .expectNextSequence(java.util.List.of("a", "b", "c"))
    .verifyComplete();
~~~

Useful when you have a pre-built expected collection. Ensure the list has a deterministic order; do not test a SQL query without `ORDER BY` against an assumed ordering.

## 6. Verifying Completion, Empty, and Error

### 6.1. Normal Completion

~~~java
StepVerifier.create(Flux.empty())
    .verifyComplete();
~~~

`Mono.empty()` does not emit `null`; it emits `onComplete` without `onNext`. For a repository `findById`, empty usually means not found rather than a connection failure.

### 6.2. Specific Error Types

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid id")))
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

At a terminal error, do not chain `expectComplete` because a stream has only one terminal type. If you want to verify the message:

~~~java
StepVerifier.create(
        Mono.error(new IllegalStateException("database unavailable")))
    .expectErrorMessage("database unavailable")
    .verify();
~~~

`expectErrorMessage(...)` mainly checks the message; if you need both type and message, use a predicate:

~~~java
StepVerifier.create(
        Mono.<String>error(
            new IllegalStateException("database unavailable")))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "database unavailable".equals(error.getMessage()))
    .verify();
~~~

### 6.3. Data Before Error

~~~java
Flux<String> response = Flux.concat(
    Flux.just("partial"),
    Flux.error(new IllegalStateException("upstream failed"))
);

StepVerifier.create(response)
    .expectNext("partial")
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().contains("upstream failed"))
    .verify();
~~~

Useful for a `Flux` reading an HTTP stream, message broker, or server events. Do not replace this test with `collectList().block()` because it alters how the terminal signal is observed and can lose information about data that arrived before the error.

### 6.4. Testing Fallbacks

~~~java
Mono<String> operation = Mono.<String>error(
        new java.util.concurrent.TimeoutException("slow"))
    .onErrorResume(
        java.util.concurrent.TimeoutException.class,
        ignored -> Mono.just("CACHED"));

StepVerifier.create(operation)
    .expectNext("CACHED")
    .verifyComplete();
~~~

Tests must verify that the fallback applies only to permitted errors. For example, 401/403 should often preserve the error; do not write `onErrorResume(error -> Mono.empty())` for all error types just to make tests appear green.

## 7. Bounding Verification Time and Avoiding Hanging Tests

Some shortcuts such as `verifyComplete()` or `verifyError()` can wait **without a default timeout**. If the publisher is `Flux.never()` or the demand script is insufficient, the test can hang.

Prefer:

~~~java
StepVerifier.create(Flux.just(1, 2))
    .expectNext(1, 2)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Or configure a default timeout for the entire test suite in a centrally managed place:

~~~java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
~~~

`setDefaultTimeout` is a **global setting** of StepVerifier. Do not arbitrarily change it in a single test and forget to reset it, as other tests may be affected. In full project examples, most tests use `verify(Duration)` to stay self-bounded.

### 7.1. `expectNoEvent(Duration)` vs. `thenAwait(Duration)`

- `expectNoEvent(d)` asserts that **no event at all** is received during duration `d`.
- `thenAwait(d)` only waits or advances the virtual clock; it does **not** assert the absence of events.
- `onSubscribe` is also an event: when verifying no `onNext` immediately after subscription, write `.expectSubscription().expectNoEvent(...)`.
- In virtual time, both can advance the virtual clock. Do not use `expectNoEvent` as a timeout handler for an infinite publisher when `thenCancel()` or `expectTimeout(...)` is more appropriate.

Example verifying no data arrives before one second:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
~~~

If an event arrives earlier than 1 second on the virtual scheduler, the test fails. The test does not have to sleep for a real second.

## 8. Testing Backpressure: `initialRequest(0)` and `thenRequest(n)`

`StepVerifier.create(publisher)` by default may request a very large amount. Therefore, a happy-path test **does not prove** that the publisher handles batched demand properly.

To control demand:

~~~java
import reactor.test.StepVerifierOptions;

StepVerifier.create(
        Flux.range(1, 3),
        StepVerifierOptions.create()
            .initialRequest(0)
            .scenarioName("bounded-demand"))
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Meaning:
- The subscriber initially requests `0`, so no valid values should be emitted yet.
- After `thenRequest(1)`, only `1` is expected.
- After `thenRequest(2)`, `2` and `3` are expected.
- When the source runs out of data, `onComplete` is expected.

### 8.1. `checkUnderRequesting` and Deadlocks

`StepVerifierOptions` includes a check to see if the scenario is expecting more elements than the total demand granted. Under-requesting checks are enabled by default. If you configure `initialRequest(0)` but write `expectNextCount(10)` before `thenRequest(10)`, the scenario may be rejected or hang due to insufficient demand.

Always design scripts in the order **request first, receive after**. For `Flux.create` or non-Reactor publishers, demand tests also help uncover adapters that emit too fast and violate flow control.

### 8.2. `thenCancel()`

~~~java
StepVerifier.create(
        Flux.interval(Duration.ofMillis(10)))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

An infinite publisher never emits `onComplete`. This scenario proactively sends cancel after the first element. It does **not** verify that external resources were released; to check that, add `doOnCancel`, `doFinally`, or `PublisherProbe` and assert state.

With tests based on real time, machine/CI load can cause delay timings to vary; use virtual time for time-based logic whenever possible.

## 9. Virtual Time: Fast Testing for Delay, Interval, and Timeout

`StepVerifier.withVirtualTime(Supplier<? extends Publisher<T>>)` installs a `VirtualTimeScheduler` for time-based operators constructed inside the supplier. This lets you simulate hours or days without real waiting.

### 9.1. The Right Way

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(2))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

The key point: `Flux.interval(...)` **is created inside the lambda**. A pipeline created outside the lambda or using a custom scheduler not managed by the virtual scheduler may wait in real time or behave incorrectly.

### 9.2. Incorrect Example

~~~java
Flux<Long> createdTooEarly =
    Flux.interval(Duration.ofHours(1)).take(2);

// Avoid: source created outside the supplier.
StepVerifier.withVirtualTime(() -> createdTooEarly)
    .expectNextCount(2)
    .verifyComplete();
~~~

Depending on the operator/scheduler and initialization timing, this example may not be virtualized properly. Even if some operators work because the scheduler is resolved at subscribe time, the **safe pattern recommended by the Reactor documentation** is to instantiate the pipeline inside the supplier.

### 9.3. Testing Timeout with Virtual Time

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
            .timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
~~~

`Mono.delay` has not emitted an element when the 3-second `timeout` expires. The result is `onError(TimeoutException)` per Reactor's timeout operator.

### 9.4. Testing Retry/Backoff

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.util.retry.Retry;

AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            return attempt < 3
                ? Mono.<String>error(
                    new IllegalStateException("temporary"))
                : Mono.just("OK");
        })
        .retryWhen(
            Retry.fixedDelay(2, Duration.ofSeconds(5))))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(10))
    .expectNext("OK")
    .verifyComplete();

org.junit.jupiter.api.Assertions.assertEquals(3, attempts.get());
~~~

This tests **bounded** retry, retrying twice after the initial error. Because `Mono.defer` produces fresh behavior for each subscription/retry, `attempts` increments exactly three times. Do not use infinite retries or depend on real time in unit tests.

**Note:** virtual time does not replace every dedicated scheduler created by a library; a virtual clock also cannot make a synchronous JDBC or HTTP call faster. For code with real-time dependencies, isolate the clock/scheduler or use appropriate integration tests.

## 10. Reactor Context in Test Scenarios

Reactor `Context` is attached to the subscriber, not an arbitrary `ThreadLocal`. It typically holds data such as trace/correlation IDs, security context, and reactive transaction resources.

### 10.1. `withInitialContext`

~~~java
import reactor.util.context.Context;

Mono<String> currentTrace =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.get("traceId")));

StepVerifier.create(
        currentTrace,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("traceId", "trace-007")))
    .expectAccessibleContext()
    .contains("traceId", "trace-007")
    .then()
    .expectNext("trace-007")
    .verifyComplete();
~~~

`expectAccessibleContext` switches to the Context assertion builder; `.then()` returns to the signal verification steps. If the source is detached via a manual `subscribe()` inside a service, the outer subscriber's Context may not propagate to the detached subscription.

### 10.2. Testing Context in a Pipeline

~~~java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("user")))
        .contextWrite(ctx -> ctx.put("user", "Mai"));

StepVerifier.create(greeting)
    .expectNext("Hello Mai")
    .verifyComplete();
~~~

Tests should verify the **behavior** driven by Context, not merely thread names. Do not put JWTs, access tokens, or PII into test failure messages if they could leak through CI logs.

## 11. TestPublisher: Manually Emitting Each Signal

`TestPublisher` lets a test control when `onNext`, `onComplete`, and `onError` are emitted without needing a network or message broker. It is useful for testing operators that consume an asynchronous/indeterminate upstream.

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<String> upstream = TestPublisher.create();

Flux<String> upper = upstream.flux()
    .map(String::toUpperCase);

StepVerifier.create(upper)
    .then(() -> upstream.next("a", "b"))
    .expectNext("A", "B")
    .then(upstream::complete)
    .verifyComplete();
~~~

`TestPublisher.create()` is typically **hot** and only forwards signals to currently subscribed subscribers. Therefore, emit data inside `.then(...)` **after StepVerifier has subscribed**, rather than calling `upstream.next(...)` before building the verifier.

### 11.1. Testing Upstream-Emitted Errors

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .then(() ->
        source.error(new IllegalStateException("gateway down")))
    .expectErrorMessage("gateway down")
    .verify();
~~~

### 11.2. Testing Non-Compliant Reactive Streams Sources

Some adapters receiving data from callback APIs might attempt to emit `onNext` when demand = 0 or emit `null`. `TestPublisher.createNoncompliant(Violation...)` allows you to intentionally create a violating source to test how an operator handles it.

~~~java
TestPublisher<Integer> misbehaving =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW);
~~~

Use a noncompliant publisher only when the test's goal is **testing resilience against a spec-violating source**. Never use it to replace a compliant source on the happy path, as it can mask real backpressure bugs.

### 11.3. TestPublisher Is Not a Performance Tool

`TestPublisher` is generally not designed for multiple threads concurrently emitting signals without synchronization. If you want to stress test, use controlled load/concurrency testing tools and appropriate thread-safe APIs. In unit tests, keep scenarios deterministic and emit inside `.then(...)` steps.

## 12. PublisherProbe: Verifying Which Branch Was Subscribed

Sometimes you need to know whether a fallback Publisher was actually used, even if it emits no data. With `Mono<Void>` or `Mono.empty()`, checking only the terminal signal does not reveal which branch ran.

~~~java
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("from-cache"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("from-cache")
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

When the input has data, verify the fallback was **not** subscribed:

~~~java
PublisherProbe<String> unused =
    PublisherProbe.of(Mono.just("fallback"));

Mono<String> result =
    Mono.just("primary").switchIfEmpty(unused.mono());

StepVerifier.create(result)
    .expectNext("primary")
    .verifyComplete();

unused.assertWasNotSubscribed();
~~~

### 12.1. Probing for Cancellation

~~~java
PublisherProbe<Long> probe =
    PublisherProbe.of(Flux.<Long>never());

StepVerifier.create(probe.flux())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasCancelled();
~~~

`PublisherProbe` does not replace assertions on data values; it measures subscription/request/cancel. Use it alongside StepVerifier to check both the **execution path** and the **signal sequence**.

## 13. Post-Verification Assertions

`verifyThenAssertThat()` runs the scenario and then lets you inspect signals that were **discarded** or **dropped**.

### 13.1. `discard` vs. `drop`

- **Discard:** an operator intentionally drops values during processing, such as `filter`, `take`, or cleanup after cancellation. Some operators support specific discard hooks.
- **Drop:** a signal arrives too late or is no longer valid given the subscriber/operator state, such as data emitted after a terminal signal from a noncompliant source.
- Not every operator or non-Reactor library produces discards/drops the same way; do not write vague assertions relying solely on final counts.

Example:

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3)
            .filter(n -> n % 2 == 0))
    .expectNext(2)
    .expectComplete()
    .verifyThenAssertThat(Duration.ofSeconds(3))
    .hasDiscarded(1, 3);
~~~

`filter` discards 1 and 3 according to the operator's discard semantics. A passing test does not mean external memory/resources were freed; if elements are `DataBuffer` or reference-counted resources, verify actual cleanup in integration tests.

### 13.2. Additional Assertions

`StepVerifier.Assertions` also supports groups such as:
- `hasDropped(...)`, `hasNotDroppedElements()`.
- `hasDroppedErrors()` and its variants.
- `hasDiscardedElements()`, `hasDiscardedExactly(...)`.
- Checking operator error hooks in special situations.

Avoid engineering dropped signals just to test "something happened"; clearly define the contract to protect before writing post-verification assertions.

## 14. Naming Scenarios and Describing Failing Steps

A test with many expectations easily becomes hard to debug when it only reports "expected next value".

~~~java
StepVerifier.create(
        Flux.just("created", "validated", "saved"),
        StepVerifierOptions.create()
            .scenarioName("order-state-transition"))
    .expectNext("created").as("first state")
    .expectNext("validated").as("validation state")
    .expectNext("saved").as("persisted state")
    .verifyComplete();
~~~

`.as(...)` describes the immediately preceding expectation; `scenarioName(...)` labels the entire scenario. These labels generally make StepVerifier-generated error messages more meaningful; if a JUnit assertion inside `assertNext` throws an `AssertionError` directly, the StepVerifier label may not appear.

Do not name tests generically like `shouldWork()`. Describe the behavior and scenario instead, such as `emptyRepositoryUsesFallback()` or `clientCancelStopsSource()`.

## 15. Choosing the Right Test Layer

| Goal | Tool | What is needed? |
| --- | --- | --- |
| Pure Reactor operators | `StepVerifier` | `reactor-test` |
| Simulate upstream events/errors | `TestPublisher` | `reactor-test` |
| Verify fallback was subscribed | `PublisherProbe` | `reactor-test` |
| Time-based operators | `withVirtualTime` | Scheduler not created too early |
| WebFlux routes, status, headers, JSON, SSE | `WebTestClient` | Spring WebFlux test support |
| Real R2DBC, WebClient, message broker | Integration test + StepVerifier | Test database/server or suitable container |
| End-to-end slow consumer/backpressure | Load/integration test | Metrics, real driver, and real server |

**Clear distinction:** StepVerifier is a tool for checking **Reactive Streams signals**; WebTestClient is an HTTP client for checking requests/responses. You can use them together, for instance extracting a response `Flux` from WebTestClient and asserting it with StepVerifier.

## 16. Runnable Java 17+ Project: Spring Boot WebFlux

We build a small workflow: each request emits three stages `received → validated → completed`. One endpoint returns a JSON summary, and another streams SSE to the client. Unit tests use StepVerifier; HTTP tests use WebTestClient.

### 16.1. Project Structure

~~~text
step-verifier-demo/
├── pom.xml
├── src/main/java/com/example/verifier/
│   ├── StepVerifierApplication.java
│   ├── WorkEvent.java
│   ├── WorkSummary.java
│   ├── WorkService.java
│   └── WorkController.java
└── src/test/java/com/example/verifier/
    ├── WorkServiceTest.java
    └── WorkControllerTest.java
~~~

### 16.2. `pom.xml`

The example uses the released Spring Boot **4.0.9** (Java 17+); `spring-boot-starter-webflux-test` and `reactor-test` are in test scope.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>step-verifier-demo</artifactId>
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
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

The parent manages dependency versions; do not pin a separate Reactor version to avoid version mismatches with Spring Framework inside Boot.

### 16.3. `StepVerifierApplication.java`

~~~java
package com.example.verifier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StepVerifierApplication {

    public static void main(String[] args) {
        SpringApplication.run(StepVerifierApplication.class, args);
    }
}
~~~

### 16.4. `WorkEvent.java`

~~~java
package com.example.verifier;

public record WorkEvent(long sequence, String id, String stage) {}
~~~

### 16.5. `WorkSummary.java`

~~~java
package com.example.verifier;

public record WorkSummary(
    String id,
    int eventCount,
    String lastStage
) {}
~~~

### 16.6. `WorkService.java`

~~~java
package com.example.verifier;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class WorkService {

    public Flux<WorkEvent> events(String id) {
        return Flux.defer(() -> {
            if (id == null || id.isBlank()) {
                return Flux.<WorkEvent>error(
                    new IllegalArgumentException(
                        "workflow id must not be blank"));
            }

            return Flux.just("received", "validated", "completed")
                .index()
                .map(pair -> new WorkEvent(
                    pair.getT1() + 1, id, pair.getT2()));
        });
    }

    public Mono<WorkSummary> summary(String id) {
        return events(id)
            .collectList()
            .map(list -> new WorkSummary(
                id,
                list.size(),
                list.get(list.size() - 1).stage()));
    }
}
~~~

`events` is a cold `Flux`: each subscription creates a new sequence; validation is deferred until subscription time. `summary` collects the three events to return a single JSON object. Because the demo fixes the event count at three, `collectList()` is clearly bounded; do not use it carelessly on infinite streams.

### 16.7. `WorkController.java`

~~~java
package com.example.verifier;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/workflows")
public class WorkController {

    private final WorkService service;

    public WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}/summary",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<WorkSummary> summary(
            @PathVariable("id") String id) {
        return service.summary(id);
    }

    @GetMapping(
        value = "/{id}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<WorkEvent>> events(
            @PathVariable("id") String id) {

        return service.events(id)
            .map(event ->
                ServerSentEvent.<WorkEvent>builder(event)
                    .event("stage")
                    .id(Long.toString(event.sequence()))
                    .build());
    }
}
~~~

The controller only composes and returns Publishers; WebFlux owns the subscription. SSE is used so browsers can receive each stage individually. There is no need to call `.block()` or `.subscribe()` in the controller.

### 16.8. `WorkServiceTest.java`

~~~java
package com.example.verifier;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WorkServiceTest {

    private final WorkService service = new WorkService();

    @Test
    void eventsHaveExactValuesAndComplete() {
        StepVerifier.create(service.events("w-7"))
            .expectNext(new WorkEvent(1, "w-7", "received"))
            .expectNextMatches(event ->
                event.sequence() == 2
                    && event.stage().equals("validated"))
            .assertNext(event -> {
                assertEquals(3, event.sequence());
                assertEquals("completed", event.stage());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void summaryHasCorrectCardinality() {
        StepVerifier.create(service.summary("w-7"))
            .expectNext(new WorkSummary(
                "w-7", 3, "completed"))
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void blankIdProducesErrorNotEmptyCompletion() {
        StepVerifier.create(service.events(" "))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                    && error.getMessage()
                        .equals("workflow id must not be blank"))
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void sourceIsLazyUntilSubscribed() {
        AtomicInteger calls = new AtomicInteger();

        Mono<Integer> source = Mono.defer(
            () -> Mono.just(calls.incrementAndGet()));

        assertEquals(0, calls.get());

        StepVerifier.create(source)
            .expectNext(1)
            .expectComplete()
            .verify(Duration.ofSeconds(3));

        assertEquals(1, calls.get());
    }

    @Test
    void demandIsGrantedInTwoBatches() {
        StepVerifier.create(
                Flux.range(1, 3),
                StepVerifierOptions.create()
                    .initialRequest(0)
                    .scenarioName("request-1-then-2"))
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void virtualTimeAvoidsRealOneHourWait() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(Duration.ofHours(1))
                    .take(2))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(1))
            .expectNext(0L)
            .thenAwait(Duration.ofHours(1))
            .expectNext(1L)
            .verifyComplete();
    }

    @Test
    void timeoutProducesErrorWithVirtualClock() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void contextIsVisibleToSubscriber() {
        Mono<String> source = Mono.deferContextual(
            ctx -> Mono.just(ctx.get("traceId")));

        StepVerifier.create(
                source,
                StepVerifierOptions.create().withInitialContext(
                    Context.of("traceId", "t-7")))
            .expectAccessibleContext()
            .contains("traceId", "t-7")
            .then()
            .expectNext("t-7")
            .verifyComplete();
    }

    @Test
    void testPublisherControlsUpstreamSignals() {
        TestPublisher<String> upstream = TestPublisher.create();

        StepVerifier.create(
                upstream.flux().map(String::toUpperCase))
            .then(() -> upstream.next("a", "b"))
            .expectNext("A", "B")
            .then(upstream::complete)
            .verifyComplete();
    }

    @Test
    void probeConfirmsFallbackWasSubscribed() {
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("from-cache"));

        Mono<String> source = Mono.<String>empty()
            .switchIfEmpty(fallback.mono());

        StepVerifier.create(source)
            .expectNext("from-cache")
            .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void probeConfirmsCancellation() {
        PublisherProbe<Long> probe =
            PublisherProbe.of(Flux.<Long>never());

        StepVerifier.create(probe.flux())
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(3));

        probe.assertWasCancelled();
    }

    @Test
    void discardedValuesAreVisibleAfterVerify() {
        StepVerifier.create(
                Flux.just(1, 2, 3)
                    .filter(n -> n % 2 == 0))
            .expectNext(2)
            .expectComplete()
            .verifyThenAssertThat(Duration.ofSeconds(3))
            .hasDiscarded(1, 3);
    }
}
~~~

The tests cover terminal signals, demand, context, errors, subscription paths, virtual time, and cancellation. `verify(Duration)` is used in scenarios at risk of hanging; `withVirtualTime` controls the virtual clock for time-based operators.

### 16.9. `WorkControllerTest.java`

~~~java
package com.example.verifier;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WorkControllerTest {

    private final WebTestClient client = WebTestClient
        .bindToController(new WorkController(new WorkService()))
        .build();

    @Test
    void summaryEndpointReturnsExpectedJson() {
        client.get()
            .uri("/api/workflows/w-7/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("w-7")
            .jsonPath("$.eventCount").isEqualTo(3)
            .jsonPath("$.lastStage").isEqualTo("completed");
    }

    @Test
    void sseEventsHaveCorrectOrderAndCompletion() {
        FluxExchangeResult<ServerSentEvent<WorkEvent>> result =
            client.get()
                .uri("/api/workflows/w-7/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<WorkEvent>>() {});

        StepVerifier.create(result.getResponseBody())
            .assertNext(event -> {
                assertEquals("stage", event.event());
                assertEquals("1", event.id());
                assertEquals(
                    new WorkEvent(1, "w-7", "received"),
                    event.data());
            })
            .assertNext(event ->
                assertEquals("validated", event.data().stage()))
            .assertNext(event ->
                assertEquals("completed", event.data().stage()))
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }
}
~~~

`WebTestClient` here binds directly to the WebFlux controller to test mappings, status, Content-Type, and SSE encoding/decoding. In integration tests over a TCP server, `WebTestClient.bindToServer()` can be used to also verify the connector/proxy. `StepVerifier` still verifies the signal stream returned from the HTTP client.

### 16.10. Running and Testing HTTP

Requires JDK 17+ and Maven.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Once the server is running:

~~~bash
curl -i http://localhost:8080/api/workflows/w-7/summary
~~~

Sample JSON response:

~~~json
{
  "id": "w-7",
  "eventCount": 3,
  "lastStage": "completed"
}
~~~

SSE:

~~~bash
curl -N http://localhost:8080/api/workflows/w-7/events
~~~

A valid response has events similar to:

~~~text
id: 1
event: stage
data: {"sequence":1,"id":"w-7","stage":"received"}

id: 2
event: stage
data: {"sequence":2,"id":"w-7","stage":"validated"}

id: 3
event: stage
data: {"sequence":3,"id":"w-7","stage":"completed"}
~~~

**Note:** events may arrive very quickly because the `Flux.just` source is synchronous; this demo proves event framing and ordering rather than simulating the latency of real work. To test timing, use `delayElements` with `withVirtualTime` in unit tests or HTTP streaming integration tests with a controlled-latency source.

## 17. Test Scenarios Needed in Real Projects

### 17.1. Service and Repository

| Scenario | Signal expectation | Action |
| --- | --- | --- |
| Repository returns one row | `onNext(row)`, `onComplete` | Map to DTO properly |
| Repository is empty | `onComplete` with no `onNext` | `switchIfEmpty` or 404 |
| Validation fails | `onError(ValidationException)` | Do not call repository further |
| DB error | `onError(DataAccessException)` | Preserve error type needing mapping |
| Fallback on allowed error | `onNext(cached)`, `onComplete` | Fallback strictly per policy |
| Mid-stream cancellation | `cancel` | Stop upstream/clean up resources |
| Multi-row source | Correct count + order if contracted | Do not buffer entire table |
| Transient retry | N subscriptions, finally success/error | Bound retries and ensure idempotency |

### 17.2. WebClient and Streams

- HTTP 200 + JSON: `Mono<T>` emits one item and completes.
- HTTP 204: `Mono<Void>` completes without elements.
- HTTP 404: by default `retrieve()` may emit `WebClientResponseException.NotFound`.
- HTTP stream: multiple `onNext`, then complete or error.
- Slow response: `timeout` emits error; cancellation propagates upstream depending on the connector.
- Retry: outbound request count must be exact, and do not blindly retry non-idempotent POSTs.
- SSE event stream: events have ID/type/payload in order, terminating when the source completes.

`StepVerifier` does not replace a mock HTTP server; test HTTP status/body/headers with `WebTestClient` or MockWebServer/WireMock to guarantee real mapping.

### 17.3. Transactions

For R2DBC reactive transactions, tests need to verify:
- Operations share the same `TransactionalOperator` or reactive `@Transactional`.
- When an operation errors, the transaction rolls back according to transaction manager semantics.
- There is no stray `subscribe()` inside the service that loses Reactor Context and the transaction.
- On cancel, the driver and transaction manager must clean up; do not assume already-committed external side effects can automatically roll back.

Use integration tests with a real database or production-like database to verify transaction state, not just StepVerifier checking `Mono.error`.

## 18. Debugging StepVerifier Failures

Some typical failure messages:

| Symptom | Common cause | How to investigate |
| --- | --- | --- |
| Expected onNext but received onComplete | Source is empty or filtered out | Check `switchIfEmpty`, filters, and test data |
| Expected onComplete but received onError | Exception in `map`/dependency | Check exception type, stack trace, and error mapper |
| Expected onComplete but received another onNext | More elements emitted than expected | Check `flatMap` concurrency, count, and ordering |
| Test hangs at expectNext | Missing demand, `never` source, or async not emitting | Add `thenRequest`, timeout, and subscriber probe |
| Virtual-time test still waits in real time | Publisher created before supplier or using custom scheduler | Create source inside `withVirtualTime` supplier |
| `expectNoEvent` fails immediately | `onSubscribe` is also an event | Add `.expectSubscription()` first |
| Context not accessible | Non-Reactor publisher or detached subscription | Check `contextWrite`, `deferContextual`, manual subscribe |
| Fallback probe not subscribed | Primary source not empty, branch not taken | Check `switchIfEmpty` |
| `TestPublisher` emits but verifier misses it | Emitted before subscribe on hot source | Emit inside `.then(...)` |
| `verify()` was never called | Scenario never triggered | End with `verify` or shortcut |
| Flaky due to `Thread.sleep` | Timing depends on CI load | Use virtual time/latch/TestPublisher |
| Test results suddenly break in parallel runs | Global hooks/virtual scheduler and shared state | Isolate per-test state, clean up hooks |

### 18.1. Do Not Use `Thread.sleep` to Stabilize Tests

Weak example:

~~~java
// Avoid: timing has no guarantee.
Thread.sleep(500);
assertEquals(2, collected.size());
~~~

Stronger example:

~~~java
StepVerifier.create(
        Flux.just(1, 2).delayElements(Duration.ofMillis(50)))
    .expectNext(1, 2)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

For pure time-based operations, `withVirtualTime` is better because there is no real waiting. For callbacks or active event sources, `TestPublisher` provides far stricter ordering control than sleep.

### 18.2. Checking Logs / `onError`

Do not use `doOnError` as an assertion in place of StepVerifier:

~~~java
source.doOnError(error -> log.warn("failed", error));
~~~

`doOnError` only observes; if the source errors, the test must still use `.expectError(...)`. If the code recovers from errors via `onErrorResume`, the test should verify the output signals and that the fallback branch was invoked; `PublisherProbe` can be used for this.

## 19. Common Anti-Patterns

| Anti-pattern | Consequence | Right approach |
| --- | --- | --- |
| Calling `.block()` on every `Mono` in unit tests | Loses ordering/terminal info, skips demand testing | `StepVerifier` |
| Calling `.subscribe()` then checking mutable variables | Races, test may finish prematurely | StepVerifier as subscriber |
| Missing terminal expectation | Scenario may be incomplete | `expectComplete` / `expectError` / `thenCancel` |
| Using `verifyComplete()` with `Flux.never()` | Test hangs | `thenCancel()` or appropriate timeout |
| Unbounded `verify` duration | CI hangs when source never completes | `verify(Duration)` |
| `expectNextCount(100)` for business data requiring accuracy | Misses wrong contents | `expectNextSequence`/`assertNext` |
| `expectNoEvent` before `expectSubscription` | Receives subscription, test fails immediately | `expectSubscription()` first |
| Creating `Flux.interval` too early | Virtual time may not apply | Create inside supplier |
| Using `Thread.sleep` in every test | Flaky, slow, non-deterministic | Virtual time/TestPublisher |
| Emitting on TestPublisher before subscription | Hot signals get lost | Emit inside `.then(...)` |
| Disabling `checkUnderRequesting` to pass errors | Hides real demand bugs | Fix `thenRequest` and script |
| Confusing cancel with complete | Wrong terminal and cleanup assertions | `thenCancel`, probe/`doFinally` |
| Mocking everything until no real HTTP/DB remains | Fails to test serialization/drivers | Separate unit and integration tests |
| Asserting thread name to prove reactivity | Threads can legitimately change | Assert signals, context, and side effects |
| Coupling tests tightly to internal operators | Refactoring needlessly breaks tests | Test output contract |
| Setting global Hooks/schedulers without cleanup | Cross-test contamination | Scope/clean up all settings |

## 20. Self-Assessment Checklist

- [ ] Understand the valid sequence `onSubscribe → onNext* → onComplete/onError`.
- [ ] Distinguish empty completion from an error.
- [ ] Include a terminal expectation and an actual verify step.
- [ ] Test values, counts, and ordering whenever the contract requires them.
- [ ] Error tests verify type/message per business rules.
- [ ] Set timeouts on scenarios at risk of hanging.
- [ ] Place `expectNoEvent` after `expectSubscription` where appropriate.
- [ ] `withVirtualTime` instantiates the publisher inside the supplier.
- [ ] Include backpressure tests using `initialRequest(0)`/`thenRequest`.
- [ ] Include cancellation tests with `thenCancel` and cleanup/probe signals.
- [ ] Include Reactor Context tests when services depend on Context.
- [ ] Use `TestPublisher` for hard-to-simulate upstream errors/branches.
- [ ] Use `PublisherProbe` for fallback/cancel branches.
- [ ] Use `verifyThenAssertThat` when verifying discards/drops.
- [ ] Use clear scenario/expectation names for debugging in CI.
- [ ] Never use `.subscribe()` followed by sleep in unit tests.
- [ ] Never share mutable TestPublisher/scheduler state across tests.
- [ ] Have WebTestClient/integration tests for real HTTP/DB contracts.
- [ ] Test scenarios do not hide bugs behind catch-all fallbacks.
- [ ] Production code contains no blocking calls on the Netty event-loop.

## 21. Practice Exercises

**Exercise 1 – Single Mono:** create `Mono.just(new WorkSummary("a",3,"completed"))`; verify exactly one `onNext` and `onComplete`.

**Exercise 2 – Empty:** create `Mono.empty()`; verify no `onNext` is emitted, only completion. Add `switchIfEmpty` and verify the fallback.

**Exercise 3 – Error:** emit `IllegalArgumentException("bad input")`; assert type/message; try mistakenly using `expectComplete` to observe the failure.

**Exercise 4 – Data before error:** create a Flux emitting one element then `onError`; verify the order and absence of `onComplete`.

**Exercise 5 – Predicate:** create a Flux of records with dynamic IDs; use `expectNextMatches` or `assertNext` to verify fields without hardcoding the whole object.

**Exercise 6 – Backpressure:** `initialRequest(0)`, then request 1 and 2, verifying `Flux.range(1,3)` emits strictly per demand.

**Exercise 7 – Virtual time:** `Mono.delay(Duration.ofDays(1))`; with virtual time, verify no event occurs before one day and `0L` is emitted when due.

**Exercise 8 – Timeout:** 10-second slow source, 3-second timeout; verify `TimeoutException` is received using the virtual clock.

**Exercise 9 – Retry:** `Mono.defer` fails twice then succeeds; `Retry.fixedDelay` twice; verify attempt count with `AtomicInteger`.

**Exercise 10 – TestPublisher:** drive `next("a")`, `next("b")`, `complete`; verify `map(String::toUpperCase)` preserves exact order.

**Exercise 11 – PublisherProbe:** create an empty primary and a fallback; verify `assertWasSubscribed`. Change primary to emit data and verify `assertWasNotSubscribed`.

**Exercise 12 – Context:** pass a trace ID via `withInitialContext`, read it with `deferContextual`, and assert the value.

**Exercise 13 – Cancel:** create a never source, cancel with `thenCancel`, verify `PublisherProbe.assertWasCancelled`.

**Exercise 14 – Post assertions:** filter out odd numbers, use `verifyThenAssertThat().hasDiscarded(...)`.

**Exercise 15 – HTTP:** run the project, use WebTestClient to check summary JSON and SSE Flux; use StepVerifier to verify event ordering.

## 22. Official References

1. Project Reactor 3.8 – Testing (`StepVerifier`, virtual time, Context, TestPublisher, PublisherProbe): https://projectreactor.io/docs/core/release/reference/testing.html
2. Reactor Test Javadoc – `StepVerifier`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
3. Reactor Test Javadoc – `StepVerifier.Step`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html
4. Reactor Test Javadoc – `StepVerifierOptions`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
5. Reactor Test Javadoc – `StepVerifier.Assertions`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html
6. Reactor Test Javadoc – `TestPublisher`: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
7. Reactor Test Javadoc – `PublisherProbe`: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
8. Spring Framework – WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
9. Spring Framework – `WebTestClient`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
10. Spring Boot 4.0 – Managed dependency coordinates: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Final self-check:** How does `verifyComplete()` differ from `expectNext`? Why are `onError` and `onComplete` mutually exclusive? Why must `expectNoEvent` be placed after `expectSubscription`? When should you use `thenRequest(1)` instead of letting StepVerifier request unbounded? Why does `withVirtualTime` take a supplier rather than an already-created Flux? What does `PublisherProbe` verify that `expectNextCount` cannot? If you can write tests covering values, ordering, errors, demand, time, Context, and cancellation, you know how to use StepVerifier to protect Reactor's signal contract.
