# Reactor Test Adds Verification for Reactive Streams

Reactive applications do not return results by calling a method and immediately receiving a single value. `Mono` and `Flux` describe a publisher that will emit data, complete normally, or emit an error when a subscriber subscribes. A stream can also receive demand, be cancelled, depend on time, or take different processing branches depending on input data.

Reactor Test provides tools to verify these behaviors purposefully. `StepVerifier` describes the expected sequence of signals; `TestPublisher` lets the test control when data is emitted; `PublisherProbe` verifies whether a publisher branch was subscribed to; virtual time enables testing time-based operators without real waiting. These utilities complement JUnit and AssertJ when testing reactive services, operators, and WebFlux components.

## 1. Adding Reactor Test to the Test Classpath

`StepVerifier`, `TestPublisher`, and `PublisherProbe` reside in the `reactor-test` artifact, not in `reactor-core`. With Gradle and Spring Boot dependency management:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

With Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Use a `reactor-test` version compatible with `reactor-core`. If the project uses the Spring Boot BOM, let dependency management select the version rather than declaring a standalone version that could drift from Reactor in the application.

## 2. Choosing a Tool by Behavior to Verify

| Tool | Role | When to use |
|---|---|---|
| `StepVerifier` | Subscribes and verifies the signal sequence | Checking elements, order, completion, errors, demand, and cancellation |
| `TestPublisher` | Publisher that tests can emit data from on command | Controlling emission timing, creating incomplete streams, testing consumer reaction to signals |
| `PublisherProbe` | Tracks subscription, requests, and cancellation of a publisher | Verifying whether `switchIfEmpty`, fallback, or secondary publisher branches were actually used |
| `StepVerifier.withVirtualTime` | Runs the scenario with a virtual clock | Testing `delay`, `interval`, timeout, or timed retries |
| `verifyThenAssertThat` | Inspects side signals after the scenario completes | Verifying elements discarded or dropped in the pipeline |

These tools focus on publishers and Reactive Streams. When you need to verify the HTTP method, URI, headers, status, or JSON of a WebFlux endpoint, use `WebTestClient`; you can combine `WebTestClient` with `StepVerifier` when the response body is a stream whose individual elements must be observed.

## 3. StepVerifier: Verifying Publisher Signals

`StepVerifier.create(publisher)` creates a test scenario. A scenario typically describes:

1. A subscriber subscribing to the publisher.
2. The publisher emitting elements via `onNext`.
3. The publisher terminating with `onComplete` or `onError`, or the subscriber actively cancelling.

Example of a `Flux` emitting two values and completing:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just("red", "blue"))
    .expectNext("red", "blue")
    .verifyComplete();
```

Common assertions include `expectNext`, `assertNext`, `expectNextMatches`, `expectNextCount`, `expectComplete`, `expectError`, `expectErrorMessage`, and `thenCancel`. `verify()` or variants like `verifyComplete()` actually subscribe and run the scenario. If you only build the expectation chain without calling verify, the publisher has not been tested yet.

You can check an element using multiple assertions:

```java
import static org.assertj.core.api.Assertions.assertThat;

StepVerifier.create(orderService.find("ORD-356"))
    .assertNext(order -> {
        assertThat(order.id()).isEqualTo("ORD-356");
        assertThat(order.status()).isEqualTo("CONFIRMED");
    })
    .verifyComplete();
```

Scenarios should check both the data and the terminal signal. If a service is expected to return exactly one element, checking only the first element can miss extra elements or an error emitted afterward.

## 4. TestPublisher: Actively Controlling the Data Source

In many unit tests, `Flux.just(...)` or `Mono.just(...)` emits data immediately upon subscription. That is convenient, but does not let the test decide when the publisher emits elements. `TestPublisher` solves this need: the test creates a publisher, passes it into the component, and then explicitly invokes `next`, `complete`, or `error` as needed.

Example component transforming values from a publisher:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Publisher;

class ScoreService {

    Flux<Integer> doubleScores(Publisher<Integer> scores) {
        return Flux.from(scores).map(score -> score * 2);
    }
}
```

The test creates a `TestPublisher`, passes its stream to the service, and emits data after `StepVerifier` has subscribed:

```java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> source = TestPublisher.create();
ScoreService service = new ScoreService();

StepVerifier.create(service.doubleScores(source.flux()))
    .then(() -> source.next(4))
    .expectNext(8)
    .then(() -> source.next(7))
    .expectNext(14)
    .then(source::complete)
    .verifyComplete();

source.assertWasRequested();
```

This sequence lets the test precisely control the timing of each emission. It is useful when testing whether a component reacts properly when data arrives in waves, when the data source has not yet completed, or when an error occurs after several elements.

### Testing errors from the data source

TestPublisher can emit an error at a moment chosen by the test:

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(service.validateNames(source.flux()))
    .then(() -> source.next("Mai"))
    .expectNext("MAI")
    .then(() -> source.error(new IllegalStateException("source failed")))
    .expectErrorMessage("source failed")
    .verify();
```

This example assumes `validateNames` uppercases names and propagates the source error downstream. If the component translates the error into a different business exception, the assertion must reflect the component's error-translation contract.

### Testing subscription and demand

`TestPublisher` also provides assertions to verify how the consumer subscribes and requests data. For instance, a test can confirm the source was subscribed to and received demand:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(service.doubleScores(source.flux()), 0)
    .expectSubscription()
    .thenRequest(1)
    .then(() -> source.next(5))
    .expectNext(10)
    .then(source::complete)
    .verifyComplete();

source.assertWasSubscribed();
source.assertWasRequested();
```

TestPublisher is well-suited for generating controlled input signals. It does not replace `StepVerifier`: the publisher drives the source, while StepVerifier checks the results and downstream signals.

### Spec-compliant and non-compliant publishers

By default, `TestPublisher.create()` creates a publisher compliant with Reactive Streams rules. Reactor Test also has `createNoncompliant(...)` to simulate certain specification violations, such as emitting beyond demand or emitting null signals in special scenarios. Use this mode only when testing operators or consumers that must guard against a non-compliant publisher; regular business tests should use compliant publishers to reflect the reactive contract accurately.

## 5. PublisherProbe: Verifying Which Processing Branch Was Chosen

A reactive pipeline can have multiple branches. For instance, `switchIfEmpty` subscribes to the fallback publisher only when the primary publisher emits no elements. Checking only the final result is sometimes insufficient to know whether the fallback branch was actually used.

`PublisherProbe` wraps a publisher and records subscription behavior. You can use `PublisherProbe.of(publisher)` to track a publisher with data, or `PublisherProbe.empty()` to track an empty branch.

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("default"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("default")
    .verifyComplete();

fallback.assertWasSubscribed();
```

To verify that the fallback did not run when the primary source has data:

```java
PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("default"));

Mono<String> result = Mono.just("primary")
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("primary")
    .verifyComplete();

fallback.assertWasNotSubscribed();
```

Assertions such as `assertWasSubscribed`, `assertWasNotSubscribed`, `assertWasRequested`, and `assertWasCancelled` help confirm the execution branch. This is especially useful with `switchIfEmpty`, cache-miss fallbacks, retry branches, or a secondary publisher invoked only when a specific condition occurs.

## 6. Virtual Time: Testing Time Without Real Waiting

Operators such as `delayElements`, `interval`, `timeout`, and retries with backoff depend on schedulers and time. If tests use real time, a scenario spanning several minutes can slow down the suite; tests also easily flake when CI is under load.

`StepVerifier.withVirtualTime(...)` creates a virtual time environment for the default schedulers Reactor supports. The publisher must be created inside the supplier passed to `withVirtualTime` so the virtual scheduler is installed before the publisher is assembled:

```java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2))
    .expectSubscription()
    .thenAwait(Duration.ofHours(2))
    .expectNext(0L, 1L)
    .verifyComplete();
```

Two hours in the scenario are advanced via the virtual clock, rather than waiting two real hours. `thenAwait(...)` advances time; `expectNoEvent(...)` advances time and asserts that no signals other than subscription occurred during that window.

Virtual time does not automatically replace every scheduler. If code passes a specific scheduler or uses an executor/timer outside Reactor, that scheduler may not be affected by virtual time. In that case, inject the scheduler so the test can control it or use an appropriate synchronization mechanism.

## 7. Verifying Reactive Context

Reactor `Context` is data attached to a subscription, often used to propagate information such as correlation IDs, tenants, or security context through a chain of operators without embedding it in individual data elements.

`StepVerifier` can verify the context a publisher receives using `expectAccessibleContext()`:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

Mono<String> currentTenant = Mono.deferContextual(context ->
    Mono.just(context.get("tenant"))
);

StepVerifier.create(currentTenant,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenant", "tenant-356")))
    .expectAccessibleContext()
    .contains("tenant", "tenant-356")
    .then()
    .expectNext("tenant-356")
    .verifyComplete();
```

`StepVerifierOptions` must be imported from `reactor.test`. You can use `withInitialContext(...)` to create the initial context for the subscription. This assertion is useful when code relies on context for tenant routing, reading security details, or logging correlation IDs.

Context is not a property of each `onNext` element. It is bound to the subscription and read via `deferContextual` or corresponding operators. Therefore, verify context at the right reactive boundary where the application consumes it.

## 8. Checking Discarded or Dropped Elements

In some pipelines, an operator may intentionally discard elements. For example, `filter` does not emit elements downstream that fail its predicate. Reactor defines discard semantics so operators or resource-aware pipelines can handle discarded elements.

`verifyThenAssertThat()` lets you inspect side signals after the main scenario finishes running:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just(1, 2, 3).filter(value -> value != 2))
    .expectNext(1, 3)
    .verifyComplete();
```

When you need to verify discarded elements, use `verifyThenAssertThat()`:

```java
StepVerifier.create(Flux.just(1, 2, 3).filter(value -> value != 2))
    .expectNext(1, 3)
    .verifyComplete();
```

For pipelines with discard hooks or operators that must ensure discarded elements are handled, use the `verifyThenAssertThat()` API and assertions such as `hasDiscardedElements()` or `hasDiscarded(...)` according to your project's Reactor Test version. Drop and discard signals have different meanings: discard is typically intentional removal within an operator; drop is a signal arriving after downstream has already terminated or can no longer receive it. Do not treat every element absent downstream as a drop error.

## 9. Using Reactor Test in Service and WebFlux Unit Tests

For reactive services, tests usually inspect the returned publisher directly:

```java
class InventoryServiceTests {

    @Test
    void returnsAvailableQuantity() {
        StepVerifier.create(inventoryService.availableQuantity("SKU-1"))
            .expectNext(12)
            .verifyComplete();
    }
}
```

If the service depends on a reactive data source, `TestPublisher` lets you drive that source. If the service has a fallback branch, `PublisherProbe` confirms which branch was subscribed to. If results depend on time, use virtual time.

With WebFlux controllers, `WebTestClient` checks the HTTP protocol and response. If an endpoint returns a stream, obtain the publisher from `returnResult(...)` and then use `StepVerifier` to verify individual elements or cancellation. Do not use `StepVerifier` in place of HTTP assertions when what you need to verify is status codes, headers, or JSON responses.

## 10. Common Errors and Choosing the Right Scope

| Symptom | Cause to check |
|---|---|
| `StepVerifier` does not execute | Expectations were built without calling `verify()` or a corresponding variant |
| TestPublisher emits data but consumer receives nothing | Consumer has not subscribed, has no demand, or publisher already terminated |
| TestPublisher reports request overflow | Test emitted more elements than the subscriber requested; drive demand in the proper order |
| PublisherProbe was not subscribed to | Condition to enter the fallback branch did not happen or the probe is not in the pipeline under test |
| Virtual time does not advance | Publisher was created before `withVirtualTime` or uses a separate non-virtualized scheduler |
| Test hangs indefinitely | Publisher never terminates; bound element count, call `thenCancel()`, or set a verify timeout |
| Context assertion does not see the key | Context was written at the wrong operator position or the test did not set initial context on the right subscription |
| HTTP assertion missing status/header | Testing the publisher at the service layer; switch to `WebTestClient` if the goal is the HTTP contract |

Do not use `TestPublisher` merely to replace `Flux.just(...)` in every test. Use it when you need to control signals or test consumer reactions. Do not use `PublisherProbe` when you only need to check the output; it adds value when branch selection or subscription itself is what needs verification.

## 11. Reactor Test Tool Selection Workflow

1. Identify the reactive behavior to test: data, terminal signals, time, demand, cancellation, or processing branches.
2. Use `StepVerifier` as the primary tool to verify the downstream signal sequence.
3. Use `TestPublisher` when the test needs to control the input publisher step by step.
4. Use `PublisherProbe` when you need to prove whether a publisher branch was subscribed to.
5. Use `withVirtualTime` when operators depend on Reactor's default time schedulers.
6. Use context and post-verification assertions when the component's contract includes Context, discard, or drop.
7. Use `WebTestClient` for HTTP contracts and combine with `StepVerifier` for response streams when needed.

Reactor Test adds verification tools at the reactive layer: verifying not only which values a publisher emits, but also how it is subscribed to, how it receives demand, which branch it takes, and when it completes or is cancelled. Choosing the right tool for the behavior under observation keeps tests focused on the reactive contract and preserves a clear boundary with Spring WebFlux HTTP testing.
