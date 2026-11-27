# Using StepVerifier for Errors, Subscriptions, and Timing in Reactive Flows

In Spring Cloud Circuit Breaker applications using Reactor, protected calls are typically represented by `Mono<T>` or `Flux<T>`. A publisher only describes a pipeline until a subscriber attaches; outcomes, errors, fallbacks, and cancellations only occur during subscription. Therefore, reactive testing must verify publisher signals and when they occur, rather than calling a method and assuming the work has completed.

`StepVerifier` belongs to the `reactor-test` library. It subscribes to a publisher and lets you describe an ordered scenario: receiving the subscription, requesting data, checking `onNext`, verifying `onError` or `onComplete`, advancing time, and cancelling the subscription. This tool is especially useful for testing errors, retries, timeouts, and fallbacks of `ReactiveCircuitBreaker` without manually managing `subscribe()` callbacks.

## Adding reactor-test to the Project

Declare `reactor-test` in test scope. If the project uses a Spring Boot or Spring Cloud BOM, let the BOM manage the version compatible with the Reactor version in the application:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

The examples below use JUnit 5, Reactor, and `StepVerifier`. The publisher is tested directly; do not call `.subscribe()` manually in tests because `StepVerifier` creates the subscription when verifying the scenario.

## Checking Values and Completion Signals

For a successful `Mono`, use `expectNext` to check the value and `verifyComplete` to confirm the publisher emits `onComplete` right afterward:

```java
Mono<String> source = Mono.just("catalog-ready");

StepVerifier.create(source)
        .expectNext("catalog-ready")
        .verifyComplete();
```

For `Flux`, check the order and count of elements. `verifyComplete()` also confirms no other elements remain before the completion signal:

```java
Flux<Integer> source = Flux.just(10, 20, 30);

StepVerifier.create(source)
        .expectNext(10)
        .expectNext(20, 30)
        .verifyComplete();
```

Steps in the verifier form an ordered script. If the publisher emits the wrong element, emits extra elements, or terminates with a different signal, the test fails at the corresponding step. You can use `as("step description")` or `StepVerifierOptions` with `scenarioName` to make error messages easier to read in large test suites.

## Verifying Errors and Exceptions

Reactive publishers represent errors with an `onError` signal. `expectError` checks the exception type; `expectErrorMatches` checks a predicate; `expectErrorSatisfies` allows detailed assertions on the exception:

```java
Mono<Product> source = Mono.error(
        new CatalogUnavailableException("catalog timeout"));

StepVerifier.create(source)
        .expectErrorMatches(error ->
                error instanceof CatalogUnavailableException
                        && error.getMessage().contains("timeout"))
        .verify();
```

If you want to inspect the specific exception using JUnit assertions:

```java
StepVerifier.create(source)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(CatalogUnavailableException.class, error);
            assertEquals("catalog timeout", error.getMessage());
        })
        .verify();
```

Do not use `expectNext` to check an error. Once a publisher emits `onError`, it terminates immediately; it cannot emit any more `onNext` or `onComplete` signals in the same subscription. If the application uses `onErrorResume` or a fallback to turn the error into a value, the test must verify the replacement value and completion signal, because the caller no longer receives the original `onError`.

## Verifying Subscription Timing and Lazy Evaluation

Creating a `Mono` does not mean the supplier has run. Use `Mono.defer` and a counter to verify that work starts only when a subscriber subscribes:

```java
AtomicInteger executions = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    executions.incrementAndGet();
    return Mono.just("loaded");
});

assertEquals(0, executions.get()); // No subscription yet.

StepVerifier.create(source)
        .expectSubscription()
        .expectNext("loaded")
        .verifyComplete();

assertEquals(1, executions.get()); // Supplier ran once.
```

`StepVerifier.create` builds the publisher verifier; actual subscription happens when the test invokes `verifyComplete`, `verify`, or a corresponding verify method. The assertion before the verify step proves assembly has not triggered the supplier.

Cold publishers typically re-execute for each subscriber. You can verify that behavior with two separate scenarios:

```java
AtomicInteger calls = new AtomicInteger();
Mono<Integer> cold = Mono.defer(() -> Mono.just(calls.incrementAndGet()));

StepVerifier.create(cold)
        .expectNext(1)
        .verifyComplete();

StepVerifier.create(cold)
        .expectNext(2)
        .verifyComplete();

assertEquals(2, calls.get());
```

This matters when testing `ReactiveCircuitBreaker`: each subscription to a cold publisher can create a new dependency request. Do not assume that because a `Mono` variable was created once, the HTTP call happens only once.

## Checking Demand and Backpressure

`StepVerifier.create(publisher, initialRequest)` lets you specify the initial number of requested elements. Use `thenRequest(n)` to request more data and verify the publisher respects demand:

```java
Flux<Integer> source = Flux.range(1, 3);

StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
```

The scenario starts with 0 demand. Only after `thenRequest(1)` is the first element requested; the next request fetches the remaining two elements. Testing demand is useful for streaming `Flux` pipelines, because a slow consumer should not be forced to receive more data than it can process.

## Checking Cancellation

Callers can cancel a subscription when a client disconnects, a request is aborted, or data is no longer needed. Use `thenCancel()` to verify the publisher receives cancellation:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
        .expectNext(0L)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

Cancellation is neither `onComplete` nor `onError`. When a subscriber cancels, the publisher stops emitting to that subscriber and operators/resources get a chance to release resources. For requests protected by a Bulkhead or HTTP client, verify that cancellation propagates to the source and permits/resources are released.

## Using Virtual Time for Delays, Retries, and Timeouts

Tests relying on `Thread.sleep` slow down suites and are prone to CI flakiness. `StepVerifier.withVirtualTime` replaces the Reactor scheduler created within the test scope so virtual time can advance without waiting in real time. The publisher must be created inside the supplier passed to `withVirtualTime`; if a scheduler-dependent operator is created beforehand, it may capture the real scheduler.

Example testing `Mono.delay` after one minute without waiting one minute:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofMinutes(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(59))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .verifyComplete();
```

`expectSubscription()` is placed before `expectNoEvent()` because subscription itself counts as an event. After confirming subscription, the test advances 59 seconds and verifies no data has arrived yet; after one more second, `Mono.delay` emits `0L` and completes.

### Testing Retries with Backoff

The example below simulates a dependency failing twice before succeeding. `Retry.backoff` waits one second before the second attempt and two seconds before the third attempt; virtual time lets the test finish quickly:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(new IOException("temporary failure"));
            }
            return Mono.just("recovered");
        }).retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0d))
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext("recovered")
        .verifyComplete();

assertEquals(3, attempts.get());
```

The publisher and `Retry` are constructed inside the `withVirtualTime` supplier, so retry uses the virtual scheduler installed before subscription. `jitter(0d)` makes backoff intervals deterministic so the test does not depend on randomness. In production, jitter is usually helpful to avoid many clients retrying in lockstep.

### Testing Reactive Timeouts

`timeout(Duration)` emits an error if the source does not emit a signal within the deadline. Use virtual time to verify the timeout occurs at the expected point:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(2))
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectError(TimeoutException.class)
        .verify();
```

Here the source requires ten seconds while the timeout allows only two seconds, so the subscriber receives `TimeoutException`. This test checks Reactor's `timeout` operator; it does not automatically verify timeouts in an HTTP client, blocking `TimeLimiter`, or internal timers of every external library.

## Testing ReactiveCircuitBreaker and Fallbacks

Spring Cloud Circuit Breaker provides `ReactiveCircuitBreaker` to wrap publishers. The `run` method accepts a source publisher and a fallback function returning a publisher of the same element type:

```java
public Mono<Product> findProduct(String productId) {
    ReactiveCircuitBreaker breaker =
            circuitBreakerFactory.create("catalog");

    Mono<Product> request = Mono.defer(
            () -> catalogClient.findProduct(productId));

    return breaker.run(
            request,
            error -> Mono.just(Product.unavailable(productId))
    );
}
```

Test the service with `StepVerifier` to confirm the fallback produces the contracted result:

```java
when(catalogClient.findProduct("p-10"))
        .thenReturn(Mono.error(new IOException("catalog offline")));

StepVerifier.create(catalogService.findProduct("p-10"))
        .assertNext(product -> {
            assertEquals("p-10", product.id());
            assertFalse(product.isAvailable());
        })
        .verifyComplete();

verify(catalogClient, times(1)).findProduct("p-10");
```

The fallback result is `onNext` followed by `onComplete`, so the test uses `assertNext` and `verifyComplete`, not `expectError`. If you want the caller to receive the original error, configure no fallback or have the fallback re-emit the error and verify with `expectErrorMatches`.

To check which branch is actually subscribed to, you can use `PublisherProbe` from `reactor-test`:

```java
PublisherProbe<Product> fallbackProbe = PublisherProbe.of(
        Mono.just(Product.unavailable("p-10")));

Mono<Product> protectedCall = breaker.run(
        Mono.error(new IOException("catalog offline")),
        error -> fallbackProbe.mono()
);

StepVerifier.create(protectedCall)
        .assertNext(product -> assertFalse(product.isAvailable()))
        .verifyComplete();

fallbackProbe.assertWasSubscribed();
```

`PublisherProbe` can verify that the fallback was subscribed to, or verify that the source publisher was not subscribed to when the breaker rejects calls. When testing the `OPEN` state, configure a test breaker with small thresholds and trigger the open state deterministically; do not rely on random timing or a breaker shared from another test.

## Separating Publisher Tests from State-Machine Tests

`StepVerifier` verifies reactive behavior: signals, subscriptions, demand, cancellation, and Reactor scheduler time. It does not replace every Resilience4j or Spring context test. Split testing goals as follows:

| Goal | How to test |
|---|---|
| Publisher emits right values and completes | `expectNext`, `verifyComplete` |
| Publisher emits right exception | `expectError`, `expectErrorMatches`, `expectErrorSatisfies` |
| Source runs only on subscription | `Mono.defer`/`Flux.defer` and counter |
| Demand and backpressure | `initialRequest`, `thenRequest` |
| Subscription cancellation | `thenCancel`, `doOnCancel`, or check resource cleanup |
| Delay, retry backoff, Reactor timeout | `withVirtualTime`, `thenAwait`, `expectNoEvent` |
| Whether fallback branch is subscribed | `PublisherProbe` |
| `CLOSED`/`OPEN`/`HALF_OPEN` states and metrics | Inspect Resilience4j instance, events, or metrics with isolated test config |
| Factory wiring, auto-configuration, and WebFlux | Spring integration test or `WebTestClient` |

Virtual time only replaces the Reactor scheduler controlled by the test. It does not advance time inside a real HTTP server, database, thread sleep, another library's custom scheduler, or external system clocks. When testing Resilience4j's `waitDurationInOpenState`, use the clock/scheduler mechanism supported by your Resilience4j version or dedicated test durations; do not assume `thenAwait` advances every timer in the JVM.

## Avoiding Common Mistakes

- **Calling `subscribe()` manually in tests and checking variables:** the test loses control over signal ordering and may finish before callbacks run. Use `StepVerifier` to manage subscription.
- **Constructing the publisher before `withVirtualTime`:** operators may capture the real scheduler. Build the entire time-dependent chain inside the `withVirtualTime` supplier.
- **Using `expectNoEvent` before `expectSubscription`:** subscription counts as an event and fails the assertion. Verify subscription first.
- **Confusing fallback with dependency success:** a fallback can emit normal data to the caller while the circuit breaker still records the source error. Verify the publisher and the breaker's metrics/events separately.
- **Waiting with `Thread.sleep`:** makes tests slow and flaky. Use virtual time for Reactor operators that support a virtual scheduler.
- **Not checking cancellation:** cancelled requests can retain resources if cancellation does not propagate to the source. Add `thenCancel` tests for long streams or resource-holding operations.
- **Mocking only the factory:** mocks do not prove Resilience4j configuration and state transitions work. Add integration tests with the real factory for behaviors that must be verified.

## A Complete Testing Scenario

For a reactive catalog client, you can organize the test suite in this order:

1. Verify a successful publisher returns the expected `Product` and completes.
2. Verify an error publisher emits the expected exception when no fallback is configured.
3. Verify `Mono.defer` does not invoke the client before subscription and invokes it exactly once upon subscription.
4. Verify dependency errors are converted into the contracted fallback response.
5. Use `PublisherProbe` to verify the fallback is subscribed to and the rejected source is not invoked when the breaker is `OPEN`.
6. Use virtual time to verify retry backoff and Reactor timeout.
7. Verify cancellation releases resources and does not hold Bulkhead permits after the subscriber cancels.
8. Use separate integration tests to verify Resilience4j state transitions, HALF_OPEN probe quotas, events, and metrics.

A good reactive test describes precisely what the subscriber observes and when. Combining `StepVerifier` with `PublisherProbe`, virtual time, and circuit breaker integration tests uncovers bugs in pipelines, fallbacks, and protection policies without relying on real-time waits or hard-to-control asynchronous callbacks.
