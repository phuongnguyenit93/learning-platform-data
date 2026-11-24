# Reactor TestPublisher: Controlling Data and Signals from Dependencies in Reactive Testing

## 1. Why Control the Source Instead of Only Writing `Flux.just(...)`?

When testing a Spring Boot service built with Project Reactor, outputs are usually `Mono<T>` or `Flux<T>`. That service in turn consumes signals from a repository, Kafka receiver, HTTP client, or another publisher. Each source can:

- Emit one or more `onNext(value)` signals.
- Complete via `onComplete()` with no data.
- Fail via `onError(Throwable)`.
- Emit nothing yet, wait on request/demand, or react to cancellation.
- Emit signals at specific moments affecting `take`, `switchIfEmpty`, `onErrorResume`, or async operators.

With `Flux.just("A", "B")`, the source emits deterministically upon subscription, which fits simple tests. However, there are cases where you must decide **the exact moment upstream sends each signal** after downstream has subscribed. For this, `reactor-test` provides **`TestPublisher<T>`**, a programmatically controlled publisher.

Key concept:

> **`TestPublisher` stands in for a dependency publisher**, while the pipeline of the class under test (SUT) executes for real. **`StepVerifier`** subscribes to that pipeline, triggers signals according to the scenario, and verifies what downstream receives.

Minimal example:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(
        source.flux().map(String::toUpperCase))
    .then(() -> source.next("hello"))
    .expectNext("HELLO")
    .then(source::complete)
    .verifyComplete();
~~~

This is an **illustrative test snippet** importing `TestPublisher`, `StepVerifier`, and `String`. It shows three parts: **controlled source**, **real pipeline**, and **verifier**. `then(...)` runs after `StepVerifier` has subscribed, avoiding lost signals when using a hot publisher.

After this lesson, you will be able to:

1. Understand `TestPublisher.create()`, `createCold()`, `createNoncompliant(...)`, and their appropriate scope.
2. Programmatically emit `next`, `emit`, `complete`, and `error` from a fake dependency.
3. Verify subscription, demand, and cancellation alongside data and terminal signals.
4. Combine `TestPublisher`, `StepVerifier`, and interface injection in Spring Boot/Reactive unit tests.
5. Test empty completion, upstream errors, cancellation via `take(n)`, and backpressure without `Thread.sleep`.
6. Avoid misconceptions about hot/cold semantics, Reactive Streams–noncompliant sources, thread safety, and the boundary between unit tests and integration tests.

## 2. Placing `TestPublisher` in the Reactive Streams Diagram

Reactive Streams defines four fundamental interactions between publisher and subscriber:

~~~text
Subscriber                         Publisher
    |                                 |
    |---------- subscribe() ---------->|
    |<--------- onSubscribe ----------|
    |---------- request(n) ----------->|
    |<--------- onNext(value) ---------|
    |<--------- onNext(value) ---------|
    |<--------- onComplete() ----------|   (or onError)
    |
    +----- may cancel() before termination
~~~

Per the specification, a publisher must respect demand and must not emit `onNext` after a terminal signal; `onError` and `onComplete` are mutually exclusive endings. A normal `TestPublisher` models a test source; **noncompliant** modes intentionally permit specific violations to test downstream resilience.

Look at the three roles:

~~~text
                      SUT (REAL executing code)
TestPublisher ------> normalize/filter/take ------> StepVerifier
   fake source          business pipeline            test subscriber

  .next(...)          .map(...)                    .expectNext(...)
  .complete()         .filter(...)                 .verifyComplete()
  .error(...)         .onErrorResume(...)          .expectError(...)
                      .take(2)                     .thenCancel()
~~~

`TestPublisher` **is not an HTTP testing tool** and **does not replace `WebTestClient`**. It operates at the `Publisher`/`Mono`/`Flux` layer. Use it to simulate a reactive dependency; use `WebTestClient` when verifying routing, status codes, headers, and bodies; use real repositories/databases when verifying persistence.

### `TestPublisher` vs. `StepVerifier`

| Component | Responsibility | Driven By |
| --- | --- | --- |
| `TestPublisher<T>` | Test-managed emitter; records subscription/request/cancel | Test calls `next`/`complete`/`error` |
| `StepVerifier` | Subscriber asserting the signal sequence **after the SUT** | Test describes scenario and calls `verify()` |
| `Flux`/`Mono` in SUT | Real business operators, branching, and signal handling | Application code |
| `PublisherProbe` | Observes whether a source was subscribed/requested/cancelled without manual emission | Test reads probe assertions |
| `VirtualTimeScheduler`/`withVirtualTime` | Controls scheduler clock to test delays/retries/timeouts | Virtual clock, not manual `onNext` |

They complement each other. `StepVerifier` does not generate signals for a waiting dependency; `TestPublisher` does not assert what downstream ultimately produced.

## 3. Essential `TestPublisher` API

Imports:

~~~java
import reactor.test.publisher.TestPublisher;
import reactor.test.StepVerifier;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`TestPublisher` belongs to the **`io.projectreactor:reactor-test` artifact**, in **test dependency scope**. Never import it into `src/main/java` as a production implementation.

### 3.1 Creating Publishers

~~~java
TestPublisher<String> hot = TestPublisher.create();
TestPublisher<String> cold = TestPublisher.createCold();
~~~

- `create()` creates a **hot `TestPublisher`**: signals are sent to **currently subscribed** subscribers; values emitted before subscription are generally not replayed. The first terminal signal may be replayed to late subscribers.
- `createCold()` creates a **buffered cold `TestPublisher`**: `next` elements are stored and replayed to subscribers while honoring backpressure.
- `createColdNonBuffering()` is a cold variant for testing overflow edge cases and is **not equivalent** to `createCold()` in buffering/demand behavior.
- `createNoncompliant(Violation...)` creates a hot source intentionally **breaking selected spec rules** to test whether downstream tolerates faulty inputs.

### 3.2 Emitting Signals

~~~java
hot.next("A");                      // 1 onNext
hot.next("B", "C");                 // multiple onNext
hot.complete();                     // onComplete

TestPublisher<String> alternative = TestPublisher.create();
alternative.emit("A", "B");         // onNext(A), onNext(B), onComplete()

TestPublisher<String> failing = TestPublisher.create();
failing.error(new IllegalStateException("upstream failed"));
~~~

Each block above **illustrates a separate publisher**, not interchangeable calls to invoke on an already terminated source. Once a terminal signal is sent, do not emit further `next`/`error`/`complete` on a compliant publisher.

`emit(values...)` is shorthand for **emitting values then completing**. If you need the source to remain alive after the first item, use `next(...)` and emit subsequent signals in a later step. `error(Throwable)` is a terminal signal; it **is not** an exception thrown synchronously at the call site when handled normally downstream.

### 3.3 Plugging `TestPublisher` into a Pipeline

~~~java
Flux<String> upstreamFlux = hot.flux();
Mono<String> upstreamMono = TestPublisher.<String>create().mono();
~~~

`flux()` and `mono()` adapt the test publisher into Reactor types. Pick `Flux` for 0..N items and `Mono` for at most one item. **Do not use `mono()` expecting multiple `onNext` values**, because the `Mono` contract allows at most one value.

### 3.4 Observing Subscribers and Demand

Useful observation assertions:

- `assertWasSubscribed()` / `assertWasNotSubscribed()`: whether the source ever received a subscription.
- `assertWasRequested()` / `assertWasNotRequested()`: whether the source received demand/requests.
- `assertCancelled()` / `assertNotCancelled()`: whether the source observed cancellation.
- `assertSubscribers(1)`: at the **moment of the check**, exactly one subscriber is active.
- `assertNoSubscribers()`: no active subscribers remain.
- `assertMinRequested(n)` / `assertMaxRequested(n)`: checks demand on active subscribers per API semantics.
- `assertRequestOverflow()` / `assertNoRequestOverflow()`: checks whether request overflow occurred.

Several `assertWas...` methods come from the `PublisherProbe` interface implemented by `TestPublisher`. They record **interaction history**, whereas `assertSubscribers(n)` checks the **current** count. Do not call `assertSubscribers(1)` after completion or cancellation if subscriptions were cleared.

## 4. Why Must Data Be Emitted Inside `StepVerifier.then(...)`?

With a hot publisher:

~~~java
TestPublisher<String> source = TestPublisher.create();
source.next("EARLY");  // No subscriber yet: data may be lost.

StepVerifier.create(source.flux())
    .then(() -> source.next("LATE"))
    .expectNext("LATE")
    .then(source::complete)
    .verifyComplete();
~~~

This **illustrates timing**. `"EARLY"` was emitted prior to subscription, so it should not be expected to replay. `StepVerifier.create(...)` merely **builds the scenario**; actual subscription happens when `verify()` / `verifyComplete()` runs. By the time `StepVerifier` reaches `then(...)`, its subscription is established.

Timeline:

~~~text
Test builds scenario              At verify() time
  |                                    |
  | create(upstream.flux())            | subscribe
  | then(source.next("A"))             | ----> TestPublisher has subscriber
  | expectNext("A")                    | receives onNext(A) and asserts
  | then(source.complete())            | receives onComplete
  | verifyComplete()                   | PASS
~~~

**Avoid `Thread.sleep(...)`** to "wait for the source to subscribe"; that is a prime cause of flaky tests. `StepVerifier.then(() -> source.assertSubscribers(1))` verifies the subscription is already active inside the test. If SUT code shifts subscription to another scheduler, account for the async boundary instead of assuming everything is synchronous.

### Three Common Patterns

**Pattern A — emit one item then complete:**

~~~java
StepVerifier.create(source.flux().map(String::toUpperCase))
    .then(() -> source.emit("a"))
    .expectNext("A")
    .verifyComplete();
~~~

**Pattern B — emit an item, then emit an error:**

~~~java
StepVerifier.create(source.flux())
    .then(() -> source.next("first"))
    .expectNext("first")
    .then(() -> source.error(new IllegalStateException("failed")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

**Pattern C — verify cancellation instead of completion:**

~~~java
StepVerifier.create(source.flux())
    .then(() -> source.next("one"))
    .expectNext("one")
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

These three patterns are **separate test examples**: instantiate a fresh `TestPublisher` for **each** pattern. Do not run all three on an already terminated source. The complete examples in Section 8 use proper variables and are runnable.

## 5. Hot, Cold, Multicast, and Pre-Subscription Signals

This is the most common source of confusion when using `TestPublisher`.

### 5.1 Hot `TestPublisher`: Time-Sensitive Emissions

With `TestPublisher.create()`, data goes to subscribers **already registered at emission time**, mimicking a hot event source. Calling `next("A")` before `verify()` means the test subscriber can miss the event, causing `expectNext("A")` to fail or hang.

Therefore, when testing code while actively subscribed, place emissions inside `StepVerifier.then(...)`. When testing post-subscription replay, pick a cold source or real `replay`/`cache` operators per contract.

### 5.2 Cold `TestPublisher`: Buffering and Replay

`TestPublisher.createCold()` buffers signals and replays them to subsequent subscribers:

~~~java
TestPublisher<String> cold = TestPublisher.createCold();
cold.next("A", "B").complete();

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();
~~~

Here, data is staged **before** `StepVerifier` subscribes and is still received because `cold` buffers and replays. This is convenient for simple fixtures or testing multiple subscribers receiving the same sequence. However, if you want to test behavior sensitive to **when events arrive**, hot + `then(...)` expresses intent more clearly.

`createCold()` also respects backpressure: if a subscriber requests only one element, the source waits for further demand instead of pushing everything downstream.

### 5.3 What Does `createColdNonBuffering` Mean?

The method name is easily misread as "cold while never holding any items". Per the Reactor API, it still buffers/replays under certain conditions, **yet changes how buffer and demand mismatches behave**: it can signal an overflow error if the initial request is smaller than the current buffer or when emissions arrive without demand.

This is an advanced testing tool. When you simply want a straightforward, demand-respecting cold fixture, choose `createCold()`; when testing resilience against non-buffering sources under insufficient demand, read the exact semantics of `createColdNonBuffering()` for your Reactor version.

### 5.4 Multiple Subscribers

A hot source broadcasts simultaneously to current subscribers without replaying full history to latecomers. A cold source can replay its buffer to each subscriber. If your real app uses `share()`, `replay()`, `cache()`, or `publish().refCount(...)`, **test those production operators directly** rather than relying solely on `TestPublisher` simulation.

Nor is `TestPublisher` **designed as a thread-safe concurrent bus across multiple threads by default**. For concurrency testing, manage schedulers, races, subscriptions, and thread safety deliberately; never share a single `TestPublisher` across multiple test methods.

## 6. How Completion, Error, and Cancellation Signals Differ

### `onComplete`

`complete()` signals that upstream ended **successfully**, with or without values. Downstream may execute `defaultIfEmpty(...)` or `switchIfEmpty(...)`.

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().switchIfEmpty(Flux.just("fallback")))
    .then(source::complete)
    .expectNext("fallback")
    .verifyComplete();
~~~

What is tested here is **empty source completion**, not error recovery. `switchIfEmpty` switches only when no `onNext` precedes `onComplete`. If the source emits an error, this fallback branch does not catch it unless `onErrorResume` is also present.

### `onError`

`error(new IllegalStateException(...))` simulates an upstream failure **inside the reactive stream**; it differs from mocking a method to `throw` immediately upon invocation.

~~~java
TestPublisher<String> source = TestPublisher.create();
Flux<String> pipeline = source.flux()
        .onErrorResume(IllegalStateException.class,
                error -> Flux.just("temporary-fallback"));

StepVerifier.create(pipeline)
    .then(() -> source.error(new IllegalStateException("unavailable")))
    .expectNext("temporary-fallback")
    .verifyComplete();
~~~

Here `onErrorResume` runs inside the real pipeline, and the test checks the reactive error branch. For unhandled error types, the pipeline continues propagating `onError`, which tests verify via `expectError(...)`.

**Note:** an exception thrown **before building the Publisher** differs in timing and handling path from `Mono.error(...)` emitted after subscription. Mockito's `thenThrow(...)` on a publisher-returning method fails the SUT at the Java call level, whereas `TestPublisher.error(...)` tests the reactive terminal path.

### Cancellation

`cancel()` is a signal from **downstream to upstream**, typically sent when a subscriber unsubscribes or an operator like `take(n)` receives enough items. Cancellation is **not** `onComplete` from the source. For example:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().take(1))
    .then(() -> source.next("A"))
    .expectNext("A")
    .verifyComplete();

source.assertCancelled();
~~~

Downstream completed because `take(1)` capped the count; upstream was cancelled before calling `complete()` itself. Asserting only `verifyComplete()` without checking cancellation could hide a resource or subscription remaining open.

Never expect external I/O to "roll back all side effects" simply because a subscriber cancelled. Whether cancellation aborts an actual HTTP, JDBC, or broker request belongs to the real adapter and requires integration testing when critical.

## 7. Backpressure: Difference Between `request(n)` and Emitted Item Count

In Reactive Streams, `request(n)` expresses **downstream demand** for up to `n` items. `TestPublisher.createCold()` holds its buffer and waits on demand.

~~~java
TestPublisher<Integer> cold = TestPublisher.createCold();
cold.next(10, 20).complete();

StepVerifier.create(cold.flux(), 0)
    .thenRequest(1)
    .expectNext(10)
    .thenRequest(1)
    .expectNext(20)
    .verifyComplete();
~~~

Explanation:

1. `StepVerifier.create(cold.flux(), 0)` starts with **initial request = 0**.
2. `thenRequest(1)` grants demand for one element, delivering `10`.
3. Requesting one more element delivers `20`.
4. Since the cold source already received `complete()`, once the buffer drains, downstream receives terminal `onComplete`.

Placing `expectNext(10)` before issuing the first request causes the test to wait indefinitely for unrequested data. A `StepVerifier` with default unbounded demand requests a huge amount upfront, so **a test that never restricts demand does not prove backpressure**.

### `TestPublisher.assertMinRequested`, `assertMaxRequested`

`assertMinRequested(n)` and `assertMaxRequested(n)` inspect **demand across current subscribers** per `TestPublisher` semantics. They help check that upstream received at least/at most `n` at a given moment, keeping in mind that operators may **prefetch or reshape demand**:

- `map` and `filter` can cause demand to differ from output counts.
- `flatMap` uses concurrency/prefetch; upstream may see larger requests than expected.
- `take`, `limitRate`, and `onBackpressure...` modify demand and cancellation.
- `StepVerifier` defaults to unbounded requests; asserting "exactly 1" under unbounded demand misses the point.

If the goal is simply "two results arrive across two demand requests", the `createCold()` test above suffices. Only assert exact request counters when **request policy itself is the contract**. Avoid turning internal prefetch details into brittle business contracts.

### Cancellation Without Any Demand

A publisher that has emitted nothing can still be cancelled:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

This tests the **downstream → upstream** direction; neither `next` nor `complete` is needed. Still, cancellation on a fake producer does not guarantee a real production network socket or database query stops.

## 8. Complete Java 17+ Example: Fake Event Source and Real Business Pipeline

This hands-on example creates a small **real SUT**: `EventPipeline` consumes an `EventFeed` returning `Flux<String>`. The pipeline trims text, drops blank items, uppercases, and takes up to `limit` results. Data comes from `TestPublisher`, letting tests control exact emission timing, completion, errors, and cancellation.

This example is self-contained in **one Java file** for clarity, requiring no Spring `ApplicationContext`, database, Netty, Docker, or network. In real projects, `EventFeed` and `EventPipeline` live in `src/main/java`; tests must import the **real production code** rather than copying business logic into test classes and mistaking that for production coverage.

### 8.1 Directory Structure

~~~text
src/
  test/
    java/
      example/
        reactive/
          EventPipelineTest.java
~~~

Requirements: Java 17+, JUnit Jupiter, Reactor Core, and `reactor-test` from a compatible release family.

### 8.2 File `EventPipelineTest.java`

~~~java
package example.reactive;

import java.util.Locale;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@DisplayName("TestPublisher controls Reactive dependency")
class EventPipelineTest {

    interface EventFeed {
        Flux<String> events();
    }

    static final class EventPipeline {
        private final EventFeed feed;

        EventPipeline(EventFeed feed) {
            this.feed = feed;
        }

        Flux<String> normalized(int limit) {
            if (limit <= 0) {
                return Flux.error(
                        new IllegalArgumentException(
                                "limit must be positive"));
            }

            return feed.events()
                    .map(String::trim)
                    .filter(value -> !value.isBlank())
                    .map(value -> value.toUpperCase(Locale.ROOT))
                    .take(limit);
        }
    }

    @Test
    @DisplayName("Emits onNext then onComplete: transforms and filters properly")
    void emitsNormalizedValuesThenCompletes() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .then(() -> source.assertSubscribers(1))
                .then(() -> source.next("  apple  ", "  ", " banana "))
                .expectNext("APPLE", "BANANA")
                .then(source::complete)
                .verifyComplete();

        source.assertWasSubscribed();
        source.assertWasRequested();
        source.assertNotCancelled();
    }

    @Test
    @DisplayName("Empty completion produces no items")
    void completesWithoutValues() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(3))
                .then(source::complete)
                .verifyComplete();
    }

    @Test
    @DisplayName("Delivers prior item then propagates upstream error")
    void propagatesUpstreamError() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .then(() -> source.next(" ok "))
                .expectNext("OK")
                .then(() -> source.error(
                        new IllegalStateException("upstream unavailable")))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(IllegalStateException.class, error);
                    assertEquals("upstream unavailable", error.getMessage());
                })
                .verify();

        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("take(2) completes downstream and cancels upstream")
    void takeLimitCancelsSource() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(2))
                .then(() -> source.next(" one ", " two "))
                .expectNext("ONE", "TWO")
                .verifyComplete();

        source.assertCancelled();
        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("Invalid limit does not subscribe to dependency")
    void invalidLimitDoesNotSubscribe() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(0))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "limit must be positive"
                                .equals(error.getMessage()))
                .verify();

        source.assertWasNotSubscribed();
    }

    @Test
    @DisplayName("Cold source replays values buffered before subscription")
    void coldPublisherReplaysBufferedValues() {
        TestPublisher<String> source = TestPublisher.createCold();
        source.next(" cached ").complete();

        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .expectNext("CACHED")
                .verifyComplete();

        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("Cold source honors item-by-item demand")
    void coldSourceHonorsDemand() {
        TestPublisher<Integer> source = TestPublisher.createCold();
        source.next(10, 20).complete();

        StepVerifier.create(source.flux(), 0)
                .thenRequest(1)
                .expectNext(10)
                .thenRequest(1)
                .expectNext(20)
                .verifyComplete();

        source.assertWasRequested();
    }

    @Test
    @DisplayName("Subscriber cancels explicitly and source records cancellation")
    void explicitCancellationIsVisible() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
                .then(() -> source.next("first"))
                .expectNext("first")
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
~~~

**There are 8 `@Test` methods.** Under a compatible configuration, all eight **are expected to PASS**; none print stdout. They test **a pipeline's signals** against a test-controlled upstream without running a web server or calling external systems.

### 8.3 Reading Each Test Accurately

| Test | What Does `TestPublisher` Emit? | What Does `StepVerifier` Expect? | Proof |
| --- | --- | --- | --- |
| `emitsNormalizedValuesThenCompletes` | `next(" apple ", " ", " banana ")`; `complete` | `APPLE`, `BANANA`, complete | Pipeline trims, filters, and uppercases |
| `completesWithoutValues` | `complete` only | No items, complete | Empty ending produces no spurious output |
| `propagatesUpstreamError` | `next(" ok ")`; `error` | `OK` then `IllegalStateException` | Reactive error propagates |
| `takeLimitCancelsSource` | Two items, no upstream complete | Two items then downstream complete; upstream cancelled | `take(2)` releases subscription |
| `invalidLimitDoesNotSubscribe` | Emits nothing | `IllegalArgumentException`; no subscription | Validation avoids wasting dependency |
| `coldPublisherReplaysBufferedValues` | Item and complete **before subscription** | `CACHED`, complete | Cold replay/buffering |
| `coldSourceHonorsDemand` | `10, 20` and complete pre-staged | Two `request(1)` deliver items sequentially | Demand governs delivery |
| `explicitCancellationIsVisible` | One item | Receive item then cancel | `thenCancel` and upstream recording |

**Why no `Thread.sleep`?** Signals are emitted via `then(...)` once `StepVerifier` is subscribed; there is no guessing how many ms a scheduler takes. When real business code uses `publishOn`/`subscribeOn`, account for scheduler boundaries and coordinate cleanly without using sleep as synchronization.

### 8.4 Relationship Between `limit` and Cancellation

In the example, `take(limit)` completes downstream and cancels upstream once enough valid outputs arrive. Because of `filter(value -> !value.isBlank())`, if the source emits `" "` in the middle, that blank item does not count toward the **output count** needed for `take` to finish.

Example:

~~~text
upstream: onNext(" one ") -> onNext(" ") -> onNext(" two ")
                  |                |                |
          trim -> "one"          ""             "two"
          keep & upper         filter           keep & upper
                  |                                 |
downstream:     "ONE"                            "TWO"
                                                       |
                                                take(2) complete
                                                upstream cancel
~~~

If an implementer accidentally puts `take(limit)` **before `filter`**, a test containing a blank element catches the bug: the source gets cut off after 2 raw items, leaving downstream with only one output. That shows the practical value of tests controlling **the exact items emitted by dependencies**.

## 9. Injecting a Dependency into a Spring Boot Service Without Loading `ApplicationContext`

In your application, you can define a production port:

~~~java
package example.reactive;

import reactor.core.publisher.Flux;

public interface EventFeed {
    Flux<String> events();
}
~~~

The production service takes the port via constructor and applies Reactor logic:

~~~java
package example.reactive;

import java.util.Locale;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class EventService {

    private final EventFeed feed;

    public EventService(EventFeed feed) {
        this.feed = feed;
    }

    public Flux<String> normalized(int max) {
        if (max <= 0) {
            return Flux.error(
                    new IllegalArgumentException("max must be positive"));
        }
        return feed.events()
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .take(max);
    }
}
~~~

These are **two separate production files**; if placed in the same project as the self-contained `EventPipelineTest.java` in Section 8, class/interface names do not collide because one uses nested test types and the other top-level types. Real unit tests should **import production `EventService`** and construct `new EventService(publisher::flux)` rather than testing a duplicate copy of the service.

Illustrative test invoking the real production service (placed inside a test with imports):

~~~java
TestPublisher<String> upstream = TestPublisher.create();
EventService service = new EventService(upstream::flux);

StepVerifier.create(service.normalized(1))
    .then(() -> upstream.next("hello"))
    .expectNext("HELLO")
    .verifyComplete();

upstream.assertCancelled();
~~~

A lambda/method reference `upstream::flux` acts as a fake port implementation. **`@SpringBootTest` is unnecessary** when the goal is operator logic and how the SUT reacts to upstream signals.

### When Are `@SpringBootTest` or `@WebFluxTest` Needed?

- **Reactive pipeline unit tests:** JUnit Jupiter + Reactor Test + fake/mocked port; fast and isolated.
- **WebFlux controller contract:** `@WebFluxTest` + `WebTestClient`, replacing the service with `@MockitoBean` or test configuration as needed.
- **Bean wiring, profiles, auto-configuration:** `@SpringBootTest` or an appropriate slice test.
- **Real HTTP servers, R2DBC, Kafka, Redis:** integration tests against real dependencies/resources. `TestPublisher` does not prove TCP, database transactions, or message brokers work properly.

A mock returning `Flux.just(...)` often suffices for simple cases. Yet whenever you must explicitly choose **when the service sees error/complete/cancel**, stub that method to return `testPublisher.flux()`; the service's own reactive pipeline still runs for real.

Illustrative Mockito snippet, not a standalone file:

~~~java
EventFeed feed = Mockito.mock(EventFeed.class);
TestPublisher<String> upstream = TestPublisher.create();

Mockito.when(feed.events()).thenReturn(upstream.flux());

EventService service = new EventService(feed);
StepVerifier.create(service.normalized(2))
    .then(() -> upstream.emit("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

If the service invokes `feed.events()` **when assembling the pipeline** and you stub it to return the Flux, the test works. If the contract requires proving the source is only created/subscribed on downstream subscription, separate checking **method invocation** from checking **Publisher subscription**; never conflate the two moments.

## 10. Lazy Execution Trap: Calling a Method Differs from Subscribing

With Reactor, three phases typically exist:

1. **Java method call:** `service.normalized(...)` runs the method body, creating a pipeline.
2. **Assembly:** operators like `map`/`filter`/`take` construct a potentially lazy `Publisher`.
3. **Subscription:** `StepVerifier.verify()` (or another subscriber) activates the chain, requests items, and processes events.

SUT code might call `feed.events()` in step 1 to get a `Flux`, yet that source **may not be subscribed to** until step 3. Thus:

~~~java
TestPublisher<String> source = TestPublisher.create();
Flux<String> result = source.flux().map(String::trim);

// No subscription to result yet:
// source.assertWasNotSubscribed();

StepVerifier.create(result)
    .then(() -> source.next(" X "))
    .expectNext("X")
    .then(source::complete)
    .verifyComplete();

source.assertWasSubscribed();
~~~

In this example, `assertWasSubscribed` verifies a real subscription occurred. Simply calling `result.toString()` or creating `StepVerifier.create(result)` without `verify()` never executes the scenario.

**Never call `subscribe()` manually inside service code** merely to make signals visible in tests, unless the service genuinely owns a long-lived subscription lifecycle and manages cancel/dispose. Normally, services return `Flux` or `Mono` so downstream decides when to subscribe.

## 11. Noncompliant `TestPublisher`: Testing Downstream Against Bad Sources

Not every real-world publisher strictly obeys Reactive Streams. Reactor lets tests **intentionally violate** specific rules to exercise operators or custom adapters.

Declaration example:

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> noncompliant =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW);
~~~

This is an **API illustration**, not a complete test with assertions. `REQUEST_OVERFLOW` permits pushing `onNext` even when downstream lacks sufficient demand. It helps test `onBackpressureDrop`, `onBackpressureBuffer`, or custom subscribers, provided you target a clear scenario and know which operator regulates demand.

Common violation flags:

| Violation | Testing Purpose |
| --- | --- |
| `REQUEST_OVERFLOW` | Allows emitting more items than current demand |
| `ALLOW_NULL` | Allows emitting `null` against normal Reactive Streams rules |
| `CLEANUP_ON_TERMINATE` | Relaxes terminal signal checks to simulate abnormal completion/error sequences |
| `DEFER_CANCELLATION` | Continues emitting when cancellation is ignored/delayed |

**Caution:**

- A noncompliant publisher **intentionally violates the spec**; never use it as the default fake dependency for ordinary tests.
- Do not assume every Reactor operator must behave "gracefully" for every violation. Read the operator contract and check whether it errors, cancels, or drops signals.
- A `null` `onNext` can cause `map`/`filter` pipelines to error; that can be a legitimate response to a broken source.
- Never let violation tests replace testing compliant sources, completion, errors, and cancellation in normal scenarios.
- If a real bug lives in an external driver/connection/adapter, a noncompliant unit test is only a simulation; add integration tests where needed.

### Request Overflow Tests Differ from Compliant Demand Tests

A compliant demand test uses `createCold()` + `StepVerifier.create(source, 0)` + `thenRequest(1)`. An intentional overflow test uses `createNoncompliant(REQUEST_OVERFLOW)`, emits while demand = 0, and verifies how the operator copes. **The two goals differ**: the first proves a producer honors demand; the second verifies downstream resilience when a producer ignores demand.

### Concurrency Testing Is Not Automatically Solved by `TestPublisher`

`TestPublisher` is generally not thread-safe when driven concurrently from multiple threads. To test races like "cancel racing with `onNext`", use proper concurrency/stress tools, controlled repetition, and avoid assuming exact scheduling outcomes. A sequential test using `then(...)` **does not prove thread safety under real races**.

## 12. When to Use `PublisherProbe` Instead of `TestPublisher`?

Sometimes you do not need to emit individual `onNext` signals—you only need to know whether a reactive branch **was subscribed to or not**. For example, `switchIfEmpty` switching to a fallback:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("FALLBACK"));

Mono<String> result =
        Mono.<String>empty().switchIfEmpty(fallback.mono());

StepVerifier.create(result)
        .expectNext("FALLBACK")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
~~~

This is an **illustrative snippet inside a test method**. `PublisherProbe` observes usage of an existing source without calling `next(...)` manually. With `TestPublisher`, you both emit signals and inspect subscribe/request/cancel.

**Rule of thumb for choosing:**

- Need to verify whether a fallback was used without controlling emission timing → `PublisherProbe`.
- Need to emit success/error/complete along a specific timeline → `TestPublisher`.
- Need to verify item order and downstream terminal signals → `StepVerifier`.
- Need to verify operator delay/retry timing → `StepVerifier.withVirtualTime(...)` or a controlled scheduler.
- Need to verify controller HTTP status/body → `WebTestClient`.

## 13. Virtual Time and `TestPublisher` Solve Two Different Problems

`TestPublisher` solves **which signals occur and when the test explicitly emits them**. `StepVerifier.withVirtualTime(...)` solves **scheduler clocks** for time-based operators like `delayElements`, `timeout`, and `retryWhen` with backoff.

Example needing no `TestPublisher`:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A")
                .delayElements(Duration.ofHours(1)))
    .thenAwait(Duration.ofHours(1))
    .expectNext("A")
    .verifyComplete();
~~~

This snippet requires importing `java.time.Duration`, `Flux`, and `StepVerifier`. **Crucially:** construct time operators **inside `withVirtualTime`'s lambda** so they adopt the virtual scheduler properly.

You can combine virtual time with a `TestPublisher`-driven upstream when verifying both data signals and deadlines, yet avoid casually mixing hot publishers emitting from real threads with a virtual scheduler unless you understand the timing interactions. For many small business branches, a test using `then(() -> source.next(...))` is sufficient and simpler.

Never use `Thread.sleep` in unit tests just to wait through a simulated business hour; it slows suites down and makes them flaky. For real HTTP/Kafka/databases, Reactor virtual time **cannot magically fast-forward external systems**; test timeouts at the appropriate adapter boundary.

## 14. Gradle and Running the Example

With **Spring Boot 3.5.x + Java 17+** in a project already configured with the Spring Boot Gradle plugin and dependency management, the needed dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **Gradle configuration snippet**, not a standalone `build.gradle`. `spring-boot-starter-test` may already pull `reactor-test` depending on the starter version; declaring it explicitly clarifies intent, while keeping versions aligned via the Spring Boot BOM to avoid conflicts. In a module using only Reactor Core without a WebFlux server, replace `spring-boot-starter-webflux` with `reactor-core`; the sample code in Section 8 needs no Spring context.

Run a single test file:

~~~bash
./gradlew test --tests example.reactive.EventPipelineTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.reactive.EventPipelineTest
~~~

**Expected outcome:** there are **8 `@Test` methods**, all expected to PASS in a compatible JUnit Jupiter/Reactor environment. Tests have no `System.out.println(...)`, so there is no specific program stdout; Gradle reports `BUILD SUCCESSFUL` and writes reports to `build/reports/tests/test/index.html`. This is the **expected outcome from the test design**, not a log captured from a verified execution.

### On Package/Import Errors

Ensure the core imports are present:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import org.junit.jupiter.api.Test;
~~~

Do not confuse `reactor.test.publisher.TestPublisher` with `org.reactivestreams.Publisher`. `TestPublisher` is a **test-only utility**, never a live Spring Boot event bus.

### When Tests Hang

Usually a missing signal is the cause:

- Expected `expectNext(...)`, but the source never called `next(...)` after subscription.
- Expected `verifyComplete()`, but the source never called `complete()`, or `take(n)` did not receive enough items.
- A `StepVerifier.create(source, 0)` lacked a matching `thenRequest(n)`.
- Emitted items to a hot source **before subscription**, losing data.
- Used `Flux.never()`/`Mono.never()` in a branch without a timeout or cancel.
- Forgot to call `verify()` after a terminal expectation.
- Async test raced due to unsynchronized shared state or threads.

To avoid indefinite hangs in the test suite, add a deadline via `verify(Duration)` on terminal expectations, or configure an appropriate default timeout for `StepVerifier` and CI. A deadline is a **hang-prevention guard**, not a substitute for a properly defined signal scenario.

## 15. Common Design Mistakes

**1. Mocking the very pipeline under test.**  
Stubbing `service.normalized(...)` to return `Flux.just("A")` and asserting `"A"` never runs filter/transform/take logic. Keep the SUT real; replace the `EventFeed` dependency with `TestPublisher`.

**2. Emitting to a hot source before subscribing.**  
Calling `source.next("A")` before `verify()` usually does not replay, leaving the test waiting forever for `"A"`. Move emissions into `then(...)` or use `createCold()` when pre-buffering is desired.

**3. Using only `Flux.just` for every scenario.**  
It works for happy paths, yet cannot cleanly simulate "subscribed and then failed", "upstream never completes", or "downstream cancels after two items". Use `TestPublisher` when signal timing is the focus of the test.

**4. Confusing `complete()` with `error()`.**  
`switchIfEmpty` handles empty completion, not errors. Write dedicated tests for completion, error, and cancellation.

**5. Checking current state after termination.**  
`assertSubscribers(1)` can fail after completion or cancellation; to check whether a subscription ever occurred, use `assertWasSubscribed()`.

**6. Confusing `request` with `onNext`.**  
A subscriber may have subscribed without requesting yet; a demand-respecting cold publisher withholds data. Use `thenRequest` and do not assume initial demand is always 1.

**7. Calling `block()` or manual `subscribe()` inside services just to test "execution".**  
That hides cancellation/backpressure and breaks composition. Return `Mono`/`Flux`; let `StepVerifier` drive subscriptions.

**8. Omitting cancellation tests.**  
`take(2)` completing downstream is only half the story. When upstream subscriptions/resources must close, also assert `source.assertCancelled()`.

**9. Using `createNoncompliant` as the default fixture.**  
It intentionally permits Reactive Streams violations; failures observed may not reflect normal production sources. Reserve it for specific resilience tests.

**10. Assuming `TestPublisher` is thread-safe across arbitrary async schedulers.**  
It is generally unsuitable for concurrent multi-threaded control. Use a fresh source per test, minimize races, and verify scheduling intentionally.

**11. Using a cold fixture to conclude hot behavior works.**  
`createCold()` buffers and replays; a production hot event bus can drop events on late subscription. Pick a fake source whose semantics match the target.

**12. Thinking `PublisherProbe` and `TestPublisher` are identical.**  
A probe observes subscription/request/cancel; `TestPublisher` adds manual signal emission. You do not need `TestPublisher` when you only want to check whether a fallback was subscribed.

**13. Treating `StepVerifier` as an HTTP client.**  
`StepVerifier` tests `Publisher`s, not HTTP status codes, headers, or codecs. Use `WebTestClient` for web contracts and integration tests when real HTTP transport matters.

**14. Failing to test whether invalid inputs subscribe to dependencies.**  
If a service must fail fast, `assertWasNotSubscribed()` is valuable proof; also note that calling a Java port method at assembly time can still happen without subscribing.

**15. Assuming cancellation automatically aborts all I/O or transactions.**  
Subscriber cancel is a reactive chain signal; external side effects already executed do not roll back automatically. Test real adapters, databases, and brokers when contracts depend on that behavior.

## 16. Workflow for Designing and Writing a `TestPublisher` Test

1. **Identify the real SUT:** the service or operator chain receiving `Mono`/`Flux` from a dependency.
2. **Pick the seam:** an interface or function returning a `Publisher`, without mocking the class under test itself.
3. **List signals to control:** items, empty completion, errors, cancellation, or withheld demand.
4. **Choose hot or cold:** hot when event timing matters; cold when pre-buffering/replay and backpressure matter.
5. **Assemble the pipeline first:** e.g., `Flux<String> result = service.normalized(2)`.
6. **Script `StepVerifier`:** ordered inputs, expected outputs, and terminal expectations.
7. **Emit inside `then(...)`** when using a hot source, after a subscriber is attached.
8. **Terminate cleanly:** `complete`, `error`, `take`, or `thenCancel`; never wait forever.
9. **Assert source interactions:** `assertWasSubscribed`, `assertWasRequested`, `assertCancelled` when part of the contract.
10. **Test dependency error and empty paths:** not just the happy path.
11. **Assess test boundaries:** fake sources do not prove production HTTP, DB, or Kafka work.
12. **Run repeatedly in CI:** avoid shared state, sleeps, races, and timing-fragile tests.

### Final Checklist

- [ ] `TestPublisher` lives in test sources with compatible `reactor-test` dependency.
- [ ] The real business pipeline is invoked, not mocked out.
- [ ] Hot data is emitted **after subscription occurred**, typically inside `then(...)`.
- [ ] Tests cover `onNext`, `onComplete`, and `onError` per business requirements.
- [ ] When using `take` or `thenCancel`, upstream cancellation is verified if important.
- [ ] For cold sources, buffering/replay and `request(n)` behavior are understood.
- [ ] `createNoncompliant` is avoided unless explicitly testing spec-violating sources.
- [ ] `TestPublisher` is not confused with `PublisherProbe`, `WebTestClient`, or `VirtualTimeScheduler`.
- [ ] Tests do not time out from forgotten `complete`/`error`/demand.
- [ ] Mutable `TestPublisher` instances are not shared across test methods or threads.
- [ ] Demand/prefetch is asserted only when it is part of an operator or adapter contract.
- [ ] If the SUT has external side effects, separate integration tests cover cancellation/rollback/driver behavior.
- [ ] Imports, versions, and file paths fit Java 17+/JUnit Jupiter with Gradle `useJUnitPlatform()`.

**Summary:** `TestPublisher` lets you control the **emitter** — from `onNext` to `onComplete`/`onError` — to test how a real reactive pipeline reacts. `StepVerifier` acts as the subscriber checking the resulting sequence. By understanding **hot/cold semantics, subscription timing, demand, and cancellation**, you can write fast tests reproducing tricky scenarios without relying on `Thread.sleep` or external systems.

### Official References

- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, `PublisherProbe`, and virtual time.
- [Reactor TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): `create`/`createCold`/`createNoncompliant`, `next`/`emit`/`complete`/`error`, and assertions.
- [Reactor StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `then`, `thenRequest`, `expectNext`, `expectError`, `thenCancel`, and `verify`.
- [Reactor PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): observing subscribe/request/cancel.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, signals, and cancellation contract.
- [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive applications and HTTP integration.
