# StepVerifier to Assert Elements, Completion, Errors, and Cancellation

In a reactive application, a method may return `Mono<T>` or `Flux<T>` instead of returning a value immediately. Results are emitted only when a subscriber subscribes. Therefore, testing a publisher is not simply comparing a returned variable; the test must subscribe, observe the emitted signals, and verify that the publisher terminates as expected.

Reactor Test provides `StepVerifier` to describe that behavior as a scenario. The test declares expected signals in order: subscription, elements, errors, or completion. Only when `verify()` is called does `StepVerifier` perform the subscription and verify whether the publisher adheres to the scenario.

## 1. What does StepVerifier check?

A reactive publisher can emit three main groups of signals:

- `onNext`: emits a data element.
- `onComplete`: finishes normally, with no more elements to follow.
- `onError`: terminates due to an error.

The subscription can also receive requests for a number of elements (demand) and can be cancelled (cancel). `StepVerifier` allows tests to verify these signals and interactions in exact order.

For example, a `Flux` emitting two names and then completing can be tested with:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just("An", "Binh"))
    .expectNext("An", "Binh")
    .expectComplete()
    .verify();
```

This scenario requires the publisher to emit `An` and `Binh` in order, followed by a completion signal. If the publisher emits extra elements, emits them out of order, or terminates with an error, the test fails.

## 2. Preparing the Reactor Test dependency

`StepVerifier` resides in the `reactor-test` artifact, separate from `reactor-core`. With Gradle and Spring Boot dependency management, declare the test dependency:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

Let Boot manage the Reactor version in sync with the application; do not manually pick a `reactor-test` version different from the Reactor version in use. If the project does not use Spring Boot dependency management, choose a `reactor-test` version compatible with `reactor-core`.

## 3. Asserting emitted elements

`StepVerifier.create(publisher)` creates a test scenario for a publisher. Some commonly used assertions:

- `expectNext(value...)`: requires one or more elements with exact values and order.
- `assertNext(consumer)`: takes the next element to check multiple properties with standard assertions.
- `expectNextMatches(predicate)`: checks the next element using a boolean predicate.
- `expectNextCount(n)`: verifies there are `n` subsequent elements without inspecting their contents.
- `expectNextSequence(iterable)`: verifies the publisher emits a sequence of values in order.

Example with a business object:

```java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

record Order(String id, int quantity) {
}

Flux<Order> orders = Flux.just(
    new Order("ORD-1", 2),
    new Order("ORD-2", 5)
);

StepVerifier.create(orders)
    .assertNext(order -> {
        assertThat(order.id()).isEqualTo("ORD-1");
        assertThat(order.quantity()).isEqualTo(2);
    })
    .expectNextMatches(order ->
        order.id().equals("ORD-2") && order.quantity() == 5)
    .expectComplete()
    .verify();
```

`assertNext` is suitable when multiple assertions or clear error messages are needed. `expectNextMatches` suits a short condition. If you only need to check the element count without caring about values, use `expectNextCount`; do not use it when the contents of individual elements are part of the business contract.

## 4. Asserting normal publisher completion

A `Mono` can emit a single value and complete, or complete without emitting any value. A `Flux` can also emit multiple elements and complete.

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("saved"))
    .expectNext("saved")
    .expectComplete()
    .verify();

StepVerifier.create(Mono.empty())
    .expectComplete()
    .verify();
```

`expectComplete()` verifies the `onComplete` signal. A shorter form when you only need to verify completion is `verifyComplete()`:

```java
StepVerifier.create(Mono.just(42))
    .expectNext(42)
    .verifyComplete();
```

If a publisher is expected to emit exactly one value, verify both the element and completion. Calling only `expectNext(42)` and stopping the scenario may miss cases where the publisher emits extra data or terminates with an error.

## 5. Asserting errors and error details

When a publisher terminates with an error, the test needs to verify the exception type and relevant details. `StepVerifier` provides several ways:

- `expectError(Class)`: verifies the exception type.
- `expectErrorMessage(message)`: verifies the message.
- `expectErrorMatches(predicate)`: verifies the error with a predicate.
- `expectErrorSatisfies(consumer)`: runs assertions on the actual exception.

Example where a service emits an error when data is not found:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> loadAccount(String id) {
    return Mono.error(new IllegalArgumentException(
        "Account not found: " + id
    ));
}

StepVerifier.create(loadAccount("A-404"))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && error.getMessage().equals("Account not found: A-404"))
    .verify();
```

Or use `expectErrorSatisfies` to check with AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.test.StepVerifier;

StepVerifier.create(loadAccount("A-404"))
    .expectErrorSatisfies(error -> {
        assertThat(error)
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Account not found: A-404");
    })
    .verify();
```

`onError` is a terminal signal of the publisher. Therefore, after `expectError...`, there can be no further elements or `expectComplete()` in the same scenario. If an error is translated into an HTTP response by a WebFlux exception handler, test the response with `WebTestClient`; `StepVerifier` tests the publisher at the reactive layer.

## 6. Testing publishers that emit no elements or never terminate

`Mono.empty()` completes without emitting data. `Mono.never()` emits no data, does not complete, and emits no error. These two cases are different and require separate assertions:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.empty())
    .verifyComplete();

StepVerifier.create(Mono.<String>never())
    .expectSubscription()
    .thenCancel()
    .verify();
```

With `Mono.never()`, the test explicitly cancels the subscription. Do not wait for `expectComplete()` because this publisher does not emit a completion signal.

## 7. Asserting cancellation

Cancellation matters when a consumer no longer needs data. For example, a client disconnects or only reads part of a stream. You can use `doOnCancel(...)` to observe whether the publisher receives the cancel signal:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectSubscription()
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertThat(cancelled).isTrue();
```

The scenario waits for subscription, receives the first element, and then sends cancellation. After `verify(...)` completes, the test checks that the cancel callback was invoked. This is how you verify that a publisher reacts when a consumer stops reading.

Cancellation is not synonymous with `onComplete` or `onError`. Once cancelled, the subscriber no longer asks the publisher to emit further signals to it. Therefore, use `thenCancel()` as the terminal step of the scenario rather than appending `expectComplete()`.

## 8. Testing backpressure and demand

Reactive Streams uses demand so a subscriber can request at most how many elements the publisher may emit. `StepVerifier.create(publisher, initialRequest)` allows setting the initial request amount; `thenRequest(n)` increases demand at a point in the scenario.

Example starting with zero demand, requesting one element, then requesting two more elements:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify();
```

This scenario verifies that the publisher emits data only according to the demand requested by the subscriber. It is useful when testing custom publishers, custom operators, or pipelines that must control consumption volume.

Not every business test needs to verify backpressure. For a simple `Mono` or a finite `Flux` used in ordinary processing, checking elements and the terminal signal is usually enough. Test demand when that behavior is part of the technical requirement.

## 9. Testing time with virtual time

Publishers can depend on time, such as `delayElements`, `interval`, timeouts, or retries with backoff. Waiting in real time makes tests slow and prone to instability. `StepVerifier.withVirtualTime(...)` allows advancing a virtual clock to test time-based behavior without waiting for real-world time to pass.

```java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(1L, 2L)
    .expectComplete()
    .verify();
```

The publisher must be created inside the `Supplier` passed to `withVirtualTime`. This allows StepVerifier to install the virtual scheduler before the publisher is assembled. If the publisher is created beforehand and then passed in, operators may already hold the real scheduler and the test will not benefit from virtual time.

`thenAwait(duration)` advances virtual time without requiring a specific signal during that interval. `expectNoEvent(duration)` also advances time but fails if any signal occurs during the inspected interval. When using `expectNoEvent`, verify subscription first so the subscription event is not treated as an unexpected event.

## 10. Setting a timeout for verify

`verify()` subscribes to the publisher and waits until the scenario completes. If the publisher fails to emit the required signals, the test may wait forever. You can pass a timeout to `verify(Duration)`:

```java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("done"))
    .expectNext("done")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
```

You can configure a default timeout for scenarios across a test suite with `StepVerifier.setDefaultTimeout(...)`. A timeout is a safeguard protecting the test from waiting forever; set a value generous enough for CI environments and avoid setting it too short, which can cause random failures when machines are busy.

For publishers that never terminate, such as `Mono.never()` or infinite streams, the scenario must explicitly cancel or bound the element count. Setting a timeout does not replace defining the expected termination condition.

## 11. Using StepVerifier with services and WebFlux controllers

In reactive service unit tests, you can directly test the publisher returned by the service:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryService {
    Mono<Integer> availableQuantity(String sku) {
        return Mono.just(12);
    }
}

class InventoryServiceTests {

    private final InventoryService service = new InventoryService();

    @Test
    void returnsAvailableQuantity() {
        StepVerifier.create(service.availableQuantity("SKU-1"))
            .expectNext(12)
            .verifyComplete();
    }
}
```

With WebFlux controllers, there are two common testing scopes:

- Use `StepVerifier` to test publishers returned from reactive services or components, focusing on elements, errors, completion, and cancellation.
- Use `WebTestClient` to test HTTP requests/responses. If you need to inspect a streaming body, retrieve the publisher from `returnResult(...)` and use `StepVerifier` to check emitted elements.

Example with the response body of a streaming endpoint:

```java
import java.time.Duration;

import reactor.test.StepVerifier;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

FluxExchangeResult<String> result = webTestClient.get()
    .uri("/events")
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("created", "updated")
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

Here `WebTestClient` verifies the request and HTTP status; `StepVerifier` verifies the response body publisher. The two tools complement each other at two different layers.

## 12. Common mistakes when writing StepVerifier scenarios

| Symptom | Cause to check |
|---|---|
| Test hangs forever at `verify()` | Publisher does not terminate, or scenario is waiting for a signal that is never emitted; add a timeout and review terminal signals |
| Test reports wrong element | `expectNext` order mismatches, publisher emits different data, or an operator alters the result |
| Test expects completion yet receives an error | Publisher terminates with `onError`; verify the expected error with `expectError...` |
| Test expects an error yet publisher completes | Error condition did not occur, or error was handled into a value/empty publisher |
| Cancellation test does not trigger callback | Scenario did not call `thenCancel()` or publisher has not received subscription |
| Backpressure test emits unexpected data | Initial demand or `thenRequest(...)` steps do not accurately reflect the contract |
| Time-based test runs slowly | Using the real scheduler; check that publisher creation is inside `withVirtualTime(...)` |
| Virtual time test does not advance as expected | Publisher was assembled before virtual scheduler installation, or an operator uses a dedicated scheduler |

When debugging, read the scenario from start to finish as a sequence of signals. Determine whether the test is waiting for `onNext`, `onComplete`, `onError`, or cancellation, then compare against the actual publisher and applied operators.

## 13. Workflow for writing a StepVerifier scenario

1. Identify whether the publisher is a `Mono` or `Flux` and its expected termination behavior.
2. Use `StepVerifier.create(...)`, or `withVirtualTime(...)` if the publisher depends on time.
3. If needed, verify subscription with `expectSubscription()`.
4. Check data using `expectNext`, `assertNext`, `expectNextMatches`, or `expectNextCount`.
5. Check the terminal signal using `expectComplete()` or `expectError...`.
6. If testing backpressure, control demand with `thenRequest(...)`; if testing cancellation, finish with `thenCancel()`.
7. Call `verify(...)` with an appropriate timeout to actually execute the scenario and bound wait time.

`StepVerifier` turns reactive behavior into a readable and verifiable scenario: what data the publisher emits, how it terminates, and how it responds when a subscriber requests more or cancels subscription. When all relevant signals are verified, tests catch bugs in values, ordering, terminal signals, backpressure, and cancellation.
