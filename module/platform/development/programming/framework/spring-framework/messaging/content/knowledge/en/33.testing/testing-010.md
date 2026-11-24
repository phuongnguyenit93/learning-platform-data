# Using StepVerifier to Test Reactive Streams, Errors, and Cancellation

## Objectives

In Spring applications, reactive APIs typically return `Mono` or `Flux`. A stream can emit data, complete normally, emit an error, or be canceled before finishing. Checking only the final returned value is not enough: you must verify order, item counts, terminal signals, backpressure, retries, and cancellation behavior.

Project Reactor provides `StepVerifier` in the `reactor-test` module to simulate a subscriber and verify the signals emitted by a `Publisher` in exact sequence. This lesson focuses on how to use `StepVerifier` to test reactive streams, errors, and cancellation, including publishers used in Spring RSocket.

After this lesson, you will be able to:

- Build test scenarios for `Mono` and `Flux` with `StepVerifier`.
- Verify `onNext`, `onComplete`, and `onError`.
- Test errors occurring after a stream has already emitted partial data.
- Control demand to verify backpressure.
- Use virtual time to test delays, intervals, and timeouts without real-time waiting.
- Use `TestPublisher` to actively emit signals in tests.
- Verify that cancellation propagates upstream.
- Apply `StepVerifier` to publishers obtained from `RSocketRequester` and test error scenarios.

## 1. Why Is StepVerifier Needed?

Reactive Streams do not return data synchronously in the usual way. A `Publisher` can emit multiple elements over time and communicate with a subscriber through signals:

- `onSubscribe`: the subscriber receives a `Subscription` and can request data or cancel.
- `onNext`: the publisher emits an item.
- `onError`: the publisher terminates with an error.
- `onComplete`: the publisher terminates normally.
- `cancel`: the subscriber requests to stop the subscription.

With `Mono`, the publisher emits at most one item and then completes or errors. A `Mono` can also complete empty without emitting any item. With `Flux`, the publisher can emit zero or more items before completing or erroring.

A test that merely calls `block()` often misses critical behaviors:

- Cannot verify whether multiple elements were emitted in the right order.
- Cannot verify whether a stream ended normally or with an error.
- Cannot explicitly simulate incremental demand.
- Cannot verify cancellation and cleanup signals.
- Can cause tests to wait in real time when publishers include delays or intervals.

`StepVerifier` subscribes to a `Publisher`, controls demand, and verifies signals according to a scenario. It fits unit tests for reactive services, adapters, handlers, and data-processing pipelines.

### 1.1. Dependency

With Maven and Spring Boot, add `reactor-test` in `test` scope. Spring Boot dependency management usually manages the Reactor version compatible with the Spring stack in use:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If the project uses `spring-boot-starter-test`, JUnit Jupiter is already included. Otherwise, add the JUnit Jupiter dependency matching the project's build. Do not manually pick a `reactor-test` version that differs from the Reactor Core running in the application.

### 1.2. How a StepVerifier Scenario Works

A scenario typically has three parts:

1. Create the `Publisher` under test.
2. Call `StepVerifier.create(publisher)` to create a test subscriber.
3. Declare expected signals and end with `verifyComplete()`, `verify()`, or an appropriate verify method.

Minimal example:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

`StepVerifier` actually subscribes to the publisher. Therefore, lazy Reactor operators are triggered when the test starts. Do not call `subscribe()` separately on the publisher before passing it to `StepVerifier`; doing so creates another subscription and breaks the scenario under test.

## 2. Verifying Emitted Values and Order

### 2.1. Testing Mono

For a `Mono` emitting one value:

~~~java
Mono<String> source = Mono.just("RSocket");

StepVerifier.create(source)
    .expectNext("RSocket")
    .verifyComplete();
~~~

For an empty-completing `Mono`:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
~~~

For a failing `Mono`:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid request"))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Distinguish `Mono.empty()` from `Mono.error()`. The first is normal completion with no data; the second is a terminal error.

### 2.2. Testing Multiple Elements of a Flux

~~~java
Flux<String> source = Flux.just("connect", "request", "close");

StepVerifier.create(source)
    .expectNext("connect")
    .expectNext("request", "close")
    .verifyComplete();
~~~

`expectNext` checks values in order. If an item differs from the expected value or the stream emits signals out of order, verification fails.

When checking conditions rather than full object equality:

~~~java
StepVerifier.create(Flux.just(
        new Message("m-1", "created"),
        new Message("m-2", "updated")
    ))
    .assertNext(message -> {
        assertEquals("m-1", message.id());
        assertEquals("created", message.type());
    })
    .assertNext(message -> {
        assertEquals("m-2", message.id());
        assertEquals("updated", message.type());
    })
    .verifyComplete();
~~~

This example assumes the application defines `record Message(String id, String type)` and imports `assertEquals` from JUnit. `assertNext` accepts a `Consumer` and allows using your test library's assertions.

### 2.3. Testing Item Counts

When individual values do not need to be checked:

~~~java
StepVerifier.create(Flux.range(1, 5))
    .expectNextCount(5)
    .verifyComplete();
~~~

`expectNextCount` verifies that the publisher emits the exact number of consecutive items, without asserting the content of each item. Use `expectNext` or `assertNext` if the values carry business meaning.

`expectNextMatches` takes a `Predicate` and fits cases where only certain conditions need checking:

~~~java
StepVerifier.create(Mono.just("accepted"))
    .expectNextMatches(value -> value.startsWith("accept"))
    .verifyComplete();
~~~

Avoid overly broad predicates. A condition like `value != null` can let content bugs slip past that the contract truly needs to guard against.

## 3. Testing Errors and Terminal Signals

### 3.1. Checking the Error Type

~~~java
Flux<String> source = Flux.error(
    new IllegalStateException("connection unavailable")
);

StepVerifier.create(source)
    .expectError(IllegalStateException.class)
    .verify();
~~~

`expectError(Class)` verifies the exception type. Checking only the error type without checking the message or attributes may miss errors thrown for the wrong reason.

### 3.2. Checking Error Messages or Conditions

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("quantity must be positive"))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && "quantity must be positive".equals(error.getMessage())
    )
    .verify();
~~~

You can use `expectErrorMessage` if only comparing messages, or `expectErrorSatisfies` when multiple assertions are needed:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid payload"))
    )
    .expectErrorSatisfies(error -> {
        assertInstanceOf(IllegalArgumentException.class, error);
        assertEquals("invalid payload", error.getMessage());
    })
    .verify();
~~~

The assertions above are JUnit Jupiter APIs. Choose the appropriate methods for the JUnit version used in your project.

### 3.3. Streams That Emit Partial Data Before Failing

This is a crucial scenario in messaging. A `Flux` can emit several results before emitting `onError`:

~~~java
Flux<String> source = Flux.concat(
    Flux.just("item-1:accepted", "item-2:accepted"),
    Flux.error(new IllegalStateException("downstream unavailable"))
);

StepVerifier.create(source)
    .expectNext("item-1:accepted")
    .expectNext("item-2:accepted")
    .expectErrorMessage("downstream unavailable")
    .verify();
~~~

The test verifies the two items emitted prior to the error. With RSocket, the client may already have received several payloads before the stream terminates with ERROR. Applications must decide how to retain already-received results, query remaining state, and retry safely.

Do not turn every error into normal completion in production just to make tests pass easily. If a service intentionally turns a business error into a result item, assert that exact DTO and status.

### 3.4. Distinguishing Business Rejections from Reactive Errors

Two representations are common:

- **Business outcome:** a normal payload with status `REJECTED`, `NOT_FOUND`, or `VALIDATION_FAILED`. The publisher can still complete normally.
- **Technical failure:** the publisher emits `onError`, such as connection failures, timeouts, or system errors that cannot be handled within the current contract.

Example business rejection:

~~~java
Mono<OrderResult> source = Mono.just(
    new OrderResult("order-1", "REJECTED", "LIMIT_EXCEEDED")
);

StepVerifier.create(source)
    .assertNext(result -> {
        assertEquals("REJECTED", result.status());
        assertEquals("LIMIT_EXCEEDED", result.code());
    })
    .verifyComplete();
~~~

The example assumes `record OrderResult(String orderId, String status, String code)`. Tests should verify both `status` and `code` to avoid confusing a valid business rejection with a technical error.

## 4. Controlling Demand and Testing Backpressure

Reactive Streams use demand so the subscriber tells the publisher how many items it is ready to receive. Subscribers should not be forced to process unbounded items immediately.

`StepVerifier.create` can take an initial request count. Passing `0` lets you test a publisher before the subscriber requests any data:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Verification flow:

1. The subscriber starts with demand 0.
2. The test requests one item.
3. The publisher emits 1.
4. The test requests two more items.
5. The publisher emits 2 and 3.
6. The publisher completes.

This helps verify whether custom operators or publishers respect downstream demand.

### 4.1. When Should Backpressure Be Tested?

Verify demand when:

- Writing a custom `Publisher` or adapter.
- Processing large streams from a database, message broker, or remote service.
- Using `buffer`, `window`, `limitRate`, or operators capable of holding many items.
- Ensuring slow consumers are not overwhelmed beyond their processing capacity.
- Integrating a high-throughput data stream over RSocket Channel or Request-Stream.

Not every unit test needs initial demand 0. For standard publishers like `Flux.just` or `Flux.range`, basic checks are usually sufficient. Focus backpressure testing where the application has buffering, concurrency, or custom subscription logic.

### 4.2. Verifying No Events During a Time Window

`expectNoEvent` verifies that the publisher emits no signals during a specified duration:

~~~java
StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(500))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify();
~~~

`expectSubscription` confirms the subscription before verifying the quiet period. Using virtual time advances simulated time without actually sleeping.

## 5. Testing Cancellation

Cancellation occurs when a subscriber no longer needs data—for example, a user leaves a screen, a request hits its deadline, a client closes a stream, or an operator such as `take` caps the item count.

Cancellation is not completion:

- Complete means the publisher ended normally.
- Error means the publisher ended due to failure.
- Cancel means the subscriber requested to stop the subscription.

### 5.1. Verifying Cancellation Propagates Upstream

You can use `doFinally` to observe the terminal signal:

~~~java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.<Long>never()
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .thenCancel()
    .verify(Duration.ofSeconds(5));

assertEquals(SignalType.CANCEL, finalSignal.get());
~~~

`doFinally` receives a `SignalType` when the publisher completes, errors, or is canceled. The test confirms that the subscriber canceled and the cleanup callback executed with `CANCEL`.

If testing a finite stream with `expectNext` followed by `verifyComplete`, the final signal will be `ON_COMPLETE`, not `CANCEL`.

### 5.2. Testing Cleanup

Example where a service must release resources when a stream is canceled:

~~~java
AtomicBoolean cleanedUp = new AtomicBoolean();

Flux<String> source = Flux.<String>never()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            cleanedUp.set(true);
        }
    });

StepVerifier.create(source)
    .thenCancel()
    .verify();

assertTrue(cleanedUp.get());
~~~

In real applications, cleanup may close files, release leases, stop polling, or cancel upstream work. Cleanup should be idempotent so multiple termination paths do not release the same resource in an error-prone way.

Do not place irreversible business side effects in a cancellation callback assuming it always runs before the server commits. Cancellation is a stream-control signal; it is not a transaction rollback.

### 5.3. Cancellation in RSocket

With Request-Stream or Channel, subscriber cancellation is typically transmitted as a `CANCEL` signal on the RSocket stream. The responder can use this signal to stop remaining work if the implementation supports cancellation.

However, cancellation does not prove the server has not already processed data. Any side effect committed before `CANCEL` arrived still persists. Therefore:

- Do not delete business state merely because the client canceled the stream.
- Persist committed results before issuing acknowledgements.
- Use an operation ID so the client can query status after reconnecting.
- Design idempotency for operations that may be retried.
- Test cancellation with real-transport integration tests when `CANCEL` propagation is a critical requirement.

## 6. TestPublisher: Actively Controlling Signals

`TestPublisher` belongs to `reactor-test`. It lets the test explicitly decide when to emit `onNext`, `onError`, or `onComplete`. This is useful when checking how a service reacts to signals arriving step by step.

Example:

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
    .then(() -> {
        publisher.next("A", "B");
    })
    .expectNext("A", "B")
    .then(() -> {
        publisher.complete();
    })
    .verifyComplete();
~~~

`TestPublisher` helps create a controllable data source without `Thread.sleep`. The test subscribes first, then emits data and completes at the exact point required by the scenario.

### 6.1. Testing Upstream Errors

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
    .then(() -> {
        publisher.error(new IllegalStateException("source failed"));
    })
    .expectErrorMessage("source failed")
    .verify();
~~~

You can use `TestPublisher` to test how a service maps upstream errors into contract-compliant responses or business errors.

### 6.2. When to Use TestPublisher?

Use `TestPublisher` when you need to:

- Emit data step by step.
- Simulate an error occurring after several elements.
- Test operators handling delayed signals.
- Control a service's input stream.
- Avoid `sleep` or thread-timing dependencies.

`TestPublisher` is strictly a testing tool; do not use it as a production data source. For tests needing to verify exact request/cancel signals on a `Publisher`, you can use assertions provided by `TestPublisher`; when RSocket transport behavior needs verification, write separate integration tests.

## 7. Virtual Time: Testing Timers Without Waiting in Real Time

Publishers such as `Mono.delay`, `Flux.interval`, timeouts, and retry backoffs can slow tests down if waiting in real time. `StepVerifier.withVirtualTime` lets you advance a simulated clock.

### 7.1. Testing Flux.interval

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

The publisher must be constructed inside the `Supplier` passed to `withVirtualTime`. If `Flux.interval` is created beforehand, the publisher may already capture the real scheduler and ignore `StepVerifier`'s virtual scheduler.

### 7.2. Testing Timeouts

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
            .timeout(Duration.ofSeconds(2))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
~~~

The publisher is scheduled to emit data after five seconds, while the timeout is set to two seconds. The test advances time to the deadline and verifies `TimeoutException`.

Import `java.util.concurrent.TimeoutException`. Virtual time controls only schedulers integrated with the virtual scheduler; it does not automatically replace arbitrary clocks, threads, or blocking APIs outside Reactor.

### 7.3. Testing Retry Backoff

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>error(new IllegalStateException("temporary"))
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
            .onErrorReturn("fallback")
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("fallback")
    .verifyComplete();
~~~

`Retry.fixedDelay(2, ...)` performs up to two retries after the initial subscription. When all three attempts fail, `onErrorReturn` turns the final error into the fallback value. The test does not have to wait two real seconds.

If the test uses `Retry.backoff` with jitter, exact timing may be harder to predict. Configure appropriate jitter or advance across a sufficiently wide virtual time window.

## 8. A Complete Test Class

The example below gathers the core techniques into a single JUnit 5 test class. These tests use Reactor Core and `reactor-test`; they do not require starting a Spring Context.

~~~java
package com.example.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import reactor.util.retry.Retry;

class ReactivePublisherTest {

    @Test
    void emitsValuesInOrder() {
        StepVerifier.create(Flux.just("A", "B", "C"))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }

    @Test
    void verifiesErrorAfterPartialData() {
        Flux<String> source = Flux.concat(
            Flux.just("first", "second"),
            Flux.error(
                new IllegalStateException("source unavailable")
            )
        );

        StepVerifier.create(source)
            .expectNext("first", "second")
            .expectErrorMessage("source unavailable")
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void requestsItemsIncrementally() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void cancellationReachesUpstream() {
        AtomicReference<SignalType> finalSignal =
            new AtomicReference<>();

        Flux<Long> source = Flux.<Long>never()
            .doFinally(finalSignal::set);

        StepVerifier.create(source)
            .thenCancel()
            .verify(Duration.ofSeconds(5));

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }

    @Test
    void retriesTransientFailure() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(
                    new IllegalStateException("temporary")
                );
            }
            return Mono.just("ok");
        }).retryWhen(Retry.max(2));

        StepVerifier.create(source)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void verifiesTimeoutWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .timeout(Duration.ofSeconds(2))
            )
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void controlsSignalsWithTestPublisher() {
        TestPublisher<String> publisher = TestPublisher.create();

        StepVerifier.create(publisher.flux())
            .then(() -> {
                publisher.next("A", "B");
            })
            .expectNext("A", "B")
            .then(() -> {
                publisher.complete();
            })
            .verifyComplete();
    }
}
~~~

The static imports and classes in the example belong to JUnit Jupiter, Reactor Core, and Reactor Test. `spring-boot-starter-test` typically already provides JUnit Jupiter; `reactor-test` must be added in `test` scope.

Run tests with Maven Wrapper:

~~~bash
./mvnw test
~~~

On Windows PowerShell, use:

~~~powershell
.\mvnw.cmd test
~~~

If the test class resides in a Maven submodule, run the command in that module's directory or specify the module from root according to the project's multi-module layout. Maven Surefire will execute test classes according to the project configuration.

## 9. Testing Publishers from Spring RSocket

`StepVerifier` is not limited to `Flux.just` or `Mono.error`. It can verify publishers returned from `RSocketRequester`.

Request-Response example:

~~~java
Mono<OrderAccepted> response = requester
    .route("orders.submit")
    .data(command)
    .retrieveMono(OrderAccepted.class);

StepVerifier.create(response)
    .assertNext(order -> {
        assertEquals("ACCEPTED", order.status());
    })
    .verifyComplete();
~~~

This test requires a running RSocket server or a test fixture with the corresponding transport and routes configured. Subscribing via `StepVerifier` triggers the request; there is no need to call `block()` beforehand.

Request-Stream and cancellation example:

~~~java
Flux<Notification> notifications = requester
    .route("notifications")
    .retrieveFlux(Notification.class);

StepVerifier.create(notifications)
    .expectNextMatches(notification ->
        notification.id() != null
    )
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

This snippet assumes the `notifications` route emits at least one `Notification` and the record exposes an `id()` accessor. The test ends by canceling after the first item. If the route is not guaranteed to emit an item within the test window, use a controllable fixture or design an explicit test timeout.

### 9.1. Testing Errors from the Responder

A handler may return `Mono.error` or `Flux.error`. Integration tests should verify the error observed by the requester under Spring RSocket's actual error mapping:

~~~java
StepVerifier.create(
        requester
            .route("orders.submit")
            .data(invalidCommand)
            .retrieveMono(OrderAccepted.class)
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
~~~

Do not assert that the client-side exception class is always identical to the server-side exception class. RSocket can translate application exceptions into error frames, which Spring/RSocket Java maps to client-side error types. Contract tests should verify published error codes or semantics rather than depending on internal server classes when those classes are not public API.

### 9.2. Testing SETUP and Connection Lifecycle

`StepVerifier` verifies the `Publisher` produced by the requester; it does not replace tests for handshakes or transport configuration. Requirements around SETUP, authentication, metadata, keepalive, reconnect, and resume need integration tests using a real transport or an appropriate RSocket test fixture.

You can test separately:

- Client sends the right setup metadata.
- Server accepts or rejects connections per authentication policy.
- Routes work after SETUP completes.
- Connection closes and the requester reacts properly.
- Request stream is canceled when the subscriber cancels.
- Reconnect or resume follows published configuration.

Do not lump all of these scenarios into a single `StepVerifier` unit test. Unit tests should focus on `Publisher` semantics; integration tests verify cross-component and transport behavior.

## 10. Best Practices When Writing StepVerifier Tests

### 10.1. Always Verify the Terminal Signal

If a test has only `expectNext` without verifying completion or error, it may miss extra emitted items or streams that never finish. End scenarios with `verifyComplete()`, `expectError...` followed by `verify()`, or `thenCancel()` when intentionally canceling.

### 10.2. Use Timeouts for Tests That May Wait

`verify` methods may block until the publisher emits a terminal signal. For tests depending on networking, schedulers, or external sources, use `verify(Duration.ofSeconds(...))` to keep tests from hanging indefinitely.

Do not add arbitrarily short timeouts that make tests flaky on CI. Pick bounds suitable for the test environment and use virtual time whenever possible.

### 10.3. Do Not Use Thread.sleep

`Thread.sleep` makes tests slow and timing-dependent. For Reactor timers, prefer `withVirtualTime`, `thenAwait`, and `expectNoEvent`. For actively controlled signal sources, use `TestPublisher`.

### 10.4. Do Not Use block to Test Publishers

`block()` only retrieves a single synchronous result and can hide cancellation, ordering, or terminal behavior. `StepVerifier` expresses the exact signal sequence under test.

### 10.5. Test Both Data and Error Paths

A service may return the right data on the happy path while mishandling error paths. Write separate tests for:

- Valid values.
- Empty-completing publishers.
- Validation failures or business rejections.
- Technical failures.
- Errors after emitting partial data.
- Timeouts.
- Retries and retry exhaustion.
- Cancellation.

There is no need to write a separate test for every operator. Focus on the contract and branches with business impact.

### 10.6. Tests Should Not Depend on Order When the Contract Does Not Guarantee It

If an implementation uses `flatMap` and does not guarantee ordering, do not write tests assuming input order. Verify by ID or result set if the contract promises only the final elements, not their order.

Conversely, if the contract requires ordering, tests must assert order explicitly to prevent implementation changes from breaking behavior.

### 10.7. Separate Unit Tests and Integration Tests

Unit tests verify publishers and operators within a service. Integration tests verify serialization, route mapping, metadata, transport, and error mapping. A test using `Flux.just` does not prove a real RSocket connection works.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Forgetting to call `verify` | Scenario never runs and assertions are not checked. | End every scenario with the appropriate `verify` method. |
| Only `expectNext`, no terminal signal check | Misses extra items or incomplete streams. | Use `verifyComplete` or `expectError` then `verify`. |
| Using `block` in reactive tests | Skips demand and cancellation. | Use `StepVerifier`. |
| Using `Thread.sleep` to wait for timers | Slow and flaky tests. | Use virtual time. |
| Creating timers before `withVirtualTime` | Publisher may capture the real scheduler. | Create the publisher inside the `Supplier` of `withVirtualTime`. |
| Not issuing demand in backpressure tests | Does not verify demand-driven emission. | Start with initial request 0 and use `thenRequest`. |
| Confusing cancel with complete | Test misinterprets publisher lifecycle. | Use `thenCancel` and check `SignalType.CANCEL`. |
| Treating cancellation as business rollback | Committed side effects can be lost track of. | Persist durable state and use idempotency. |
| Asserting internal exception classes over RSocket | Test couples to unguaranteed mapping. | Check error codes or published semantics. |
| Treating unit tests as integration tests | Misses transport, codec, or route failures. | Add RSocket tests with a real server/transport. |
| Using `TestPublisher` in production | Mixes test utilities into application logic. | Use `TestPublisher` only in test sources. |

## 12. Checklist for a Solid Reactive Test

- [ ] Test subscribes to the exact `Publisher` under test.
- [ ] Assertions cover values and ordering when required by the contract.
- [ ] Completion or error is explicitly verified.
- [ ] Empty `Mono` is tested if it is a valid outcome.
- [ ] Errors after partial stream emission are tested if that flow can occur.
- [ ] Demand is controlled when backpressure is an important requirement.
- [ ] Cancellation and cleanup are tested when resources are held in the stream.
- [ ] Virtual time is used for timers, timeouts, or retry backoffs.
- [ ] `TestPublisher` is used when upstream signals need explicit control.
- [ ] `verify(Duration)` is used for tests that may wait.
- [ ] Cancellation is not assumed to mean server rollback.
- [ ] Separate integration tests cover RSocket transport, routes, and codecs when needed.

## References

- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, and virtual time.
- [Reactor Test Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): scenario creation, assertion, and verification APIs.
- [Reactor Test Javadoc — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): controllable publisher for tests.
- [Project Reactor Reference — Core Features](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): `Mono`, `Flux`, demand, and cancellation.
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, route mapping, and annotated responders.
- [RSocket Protocol](https://rsocket.io/about/protocol/): request frames, stream lifecycle, `CANCEL`, and `ERROR`.
