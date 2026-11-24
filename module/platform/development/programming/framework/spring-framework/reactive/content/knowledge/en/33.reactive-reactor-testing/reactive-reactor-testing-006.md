# TestPublisher for Controlled Source Scenarios in Project Reactor

## 1. Lesson Objectives

In Spring WebFlux and Project Reactor applications, many behaviors appear only when a data source emits signals at exact moments: a message arrives after the subscriber registers; upstream fails mid-stream; downstream requests only a single element; a fallback is subscribed only when the primary source is empty; or cancellation happens before the publisher completes.

If you use `Flux.just(...)` or `Mono.just(...)` for every test, the data is already fixed, making it difficult to simulate specific timings. `TestPublisher<T>` in `reactor-test` is a **test-controlled Publisher source**. It lets you emit `onNext`, `onComplete`, `onError`, and observe subscription, requests, and cancellation. Place `TestPublisher` at the start of the pipeline, then use `StepVerifier` to assert how downstream operators/services react.

After this lesson, learners will be able to:

1. Create controlled hot/cold sources with `TestPublisher.create()` and `createCold()`.
2. Emit data, completion, and errors at exact moments via `next(...)`, `emit(...)`, `complete()`, and `error(...)`.
3. Verify behavior using `StepVerifier.then(...)`, `thenRequest(...)`, `thenCancel()`, and source assertions.
4. Verify backpressure, cancellation, fallback, timeout, and error recovery without depending on a real network or database.
5. Use `createNoncompliant` to test defenses against Reactive Streams-violating sources.
6. Distinguish `TestPublisher` from `PublisherProbe`, `Sinks`, and virtual time.
7. Write a runnable Java 17+ / JUnit 5 unit test suite with Reactor Core and `reactor-test`.

## 2. Where TestPublisher Sits in a Test

~~~text
               +-------------------------+
               |        JUnit test       |
               |                         |
               |  TestPublisher<T>       |
               |  next / error / complete|
               +-------------+-----------+
                             |
                 Flux<T> or Mono<T>
                             |
                             v
                  Operator / Service
                   map, filter, retry,
                   take, onErrorResume
                             |
                             v
                     StepVerifier
             expectNext / expectError /
             thenRequest / thenCancel
                             |
                             v
                TestPublisher.assertXxx
             subscribed/requested/cancelled
~~~

Two components have distinct responsibilities:

- **TestPublisher** decides *which signals the source emits and when*.
- **StepVerifier** decides *which signals downstream must observe and in what order*.

A test typically creates the source, constructs the pipeline under test, builds `StepVerifier`, emits signals inside `then(...)` callbacks, declares expectations, and calls `verify(...)` to run verification.

**Crucial point:** calling `StepVerifier.create(...)` alone does not subscribe. Subscription happens when `verify(...)` or a shortcut like `verifyComplete()` is called. Therefore, with a hot source, emit data inside `StepVerifier` callbacks after subscription is established.

## 3. Adding the Library to a Java Project

`TestPublisher` lives in `reactor-test`, **not in `reactor-core`**. Typically `reactor-test` is declared only in test scope.

Java 17 Gradle example using versions published in the Javadoc:

~~~groovy
plugins {
    id 'java'
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
    implementation 'io.projectreactor:reactor-core:3.8.7'

    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In Spring Boot, let the Spring Boot BOM manage the compatible `reactor-core` and `reactor-test` pair instead of pinning mismatched versions. With standalone Gradle/Maven, use matching versions as shown.

Common imports:

~~~java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`TestPublisher` is a testing tool, not a message broker or production publisher. Production uses repositories, `WebClient`, `Sinks`, or other adapters as needed; tests replace real sources with `TestPublisher` to reproduce targeted scenarios.

## 4. Core TestPublisher API

| API | Meaning |
| --- | --- |
| `TestPublisher.create()` | Creates the default controlled hot source |
| `TestPublisher.createCold()` | Creates a cold source that buffers and replays for subscribers |
| `createColdNonBuffering()` | Cold source that reports overflow in certain under-requested situations |
| `createNoncompliant(Violation...)` | Creates a hot source permitted to violate specific Reactive Streams rules |
| `source.flux()` | Wraps the source as a `Flux` |
| `source.mono()` | Wraps the source as a `Mono`, suited for at-most-one-value streams |
| `source.next(value)` | Emits one `onNext` |
| `source.next(a, b, ...)` | Emits multiple `onNext` signals in order |
| `source.emit(a, b, ...)` | Emits values then completes |
| `source.complete()` | Emits `onComplete` |
| `source.error(exception)` | Emits `onError` |
| `assertSubscribers(n)` | Asserts the active subscriber count |
| `assertWasSubscribed()` | Verifies it was subscribed to at least once |
| `assertWasRequested()` | Verifies a request occurred |
| `assertCancelled()` | Verifies cancellation occurred |
| `assertNotCancelled()` | Verifies no cancellation occurred |
| `assertMinRequested(n)` | Asserts the current minimum requested demand |
| `assertMaxRequested(n)` | Asserts the current maximum requested demand |
| `assertNoRequestOverflow()` | Asserts no events exceeded granted demand |

Most signal-emitting methods return the `TestPublisher` itself so calls can be chained:

~~~java
source.next(1, 2).next(3).complete();
~~~

Or:

~~~java
source.emit(1, 2, 3);
~~~

Both snippets emit three values and then complete, **provided** the source and subscriber permit the needed demand. `emit(values)` is simply a combination of emitting values and completing; it is not an `onNext(List<T>)` event.

## 5. First Example: Testing map/filter with a Hot Source

Suppose an application normalizes strings: trims whitespace, drops empty strings, and uppercases.

~~~java
public Flux<String> normalize(Flux<String> input) {
    return input.map(String::trim)
        .filter(value -> !value.isEmpty())
        .map(String::toUpperCase);
}
~~~

Test:

~~~java
TestPublisher<String> source = TestPublisher.create();

Flux<String> output = normalize(source.flux());

StepVerifier.create(output)
    .then(() -> source.assertSubscribers(1))
    .then(() -> source.next("  java  ", "   ", " reactor "))
    .expectNext("JAVA", "REACTOR")
    .then(source::complete)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Explanation:

1. `create()` builds a hot source.
2. `normalize(source.flux())` constructs the pipeline without running it yet.
3. `verify(...)` triggers subscription.
4. `then(() -> source.assertSubscribers(1))` confirms the source has a subscriber.
5. `then(() -> source.next(...))` emits three intentional values.
6. The `filter` operator drops the blank string, so `StepVerifier` expects only two values.
7. `then(source::complete)` finishes the source.
8. `expectComplete()` verifies downstream completion, and `verify(Duration)` runs and bounds execution time.

If you reorder things and call `source.next("java")` **before** `verify(...)` on a hot source, the value can be missed because no subscriber exists yet. The test may time out or see only completion after subscribing.

## 6. How Hot and Cold Sources Differ

**Hot** in the default `TestPublisher` means emitted values are delivered to subscribers **present at the time of emission**. It does not replay all prior values to late subscribers. The Javadoc also notes that the first terminal signal may be replayed to subsequent subscribers.

**Cold `TestPublisher`** keeps values passed to `next(...)` in a buffer and replays them per demand to each subscriber. This is useful when constructing a source upfront and testing later subscribers.

| Behavior | `create()` hot | `createCold()` |
| --- | --- | --- |
| Emitting before subscribe | May be missed by later subscribers | Buffered for replay |
| New subscriber | Sees future `onNext`s | Can replay buffered history |
| Demand | Hot must be careful not to emit past demand | Cold buffered source holds values awaiting demand |
| Best for | Races, live sources, post-subscribe events | Replay, demand-controlled scenarios, subscribing after emission |
| Risk | Emitting too early hangs the test | Large buffers make tests diverge from real sources |

### 6.1. Cold Source Emitting Before Subscription

~~~java
TestPublisher<Integer> source = TestPublisher.createCold();
source.emit(10, 20, 30);

StepVerifier.create(source.flux())
    .expectNext(10, 20, 30)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Even though `emit(...)` is called before `StepVerifier` subscribes, the cold publisher replays all three elements and completion. With hot `create()`, this test has no equivalent replay behavior.

### 6.2. Replaying to Multiple Subscribers

~~~java
TestPublisher<String> cold = TestPublisher.createCold();
cold.emit("A", "B");

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();
~~~

Each subscription receives the buffered values again. This does not mean a cold `TestPublisher` re-executes database logic; it replays the values supplied by the test. If you need to simulate a source running fresh logic per subscription, combine `Flux.defer(...)` with an appropriate mock/fake service.

### 6.3. createColdNonBuffering

`createColdNonBuffering()` also has cold/replay characteristics, yet reports overflow if a new subscriber requests fewer items than already buffered, or if a new item arrives when a subscriber has no remaining demand.

Use it when you want fail-fast tests on demand assumptions without a cold buffered source silently holding extra values. It is not a factory that "stores zero values"; the name can be misleading. Check the exact semantics in the Javadoc of your version.

## 7. Using next, emit, complete, and error at the Right Time

### 7.1. next Emits Data Only

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .then(() -> source.next(2, 3))
    .expectNext(2, 3)
    .then(source::complete)
    .verifyComplete();
~~~

`next` does not close the stream. If you forget completion or cancellation, `StepVerifier` waiting for a terminal signal can hang. Prefer a timeout on every test.

### 7.2. emit Sends Values Then Completes

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.emit("a", "b"))
    .expectNext("a", "b")
    .verifyComplete();
~~~

`emit("a","b")` is equivalent to emitting `a`, `b`, and completing in the scenario above. It does not emit a list containing `a`/`b`.

### 7.3. error Terminates with an Error

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next("ok"))
    .expectNext("ok")
    .then(() ->
        source.error(new IllegalStateException("upstream failed"))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "upstream failed".equals(error.getMessage())
    )
    .verify(Duration.ofSeconds(2));
~~~

After `onError`, do not continue calling `next` or emitting another terminal signal on a compliant source. Reactive Streams specifies at most one terminal signal per stream. To test a source violating this rule, use the appropriate noncompliant factory and clearly mark it as an adversarial test.

## 8. Testing Error Recovery with a Controlled Source

Example service falling back when a remote source fails:

~~~java
Flux<String> withFallback(Flux<String> remote) {
    return remote.onErrorResume(
        IllegalStateException.class,
        error -> Flux.just("cached")
    );
}
~~~

Test:

~~~java
TestPublisher<String> remote = TestPublisher.create();

StepVerifier.create(withFallback(remote.flux()))
    .then(() -> remote.next("live-1"))
    .expectNext("live-1")
    .then(() ->
        remote.error(new IllegalStateException("offline"))
    )
    .expectNext("cached")
    .verifyComplete();
~~~

When `remote` emits an error, `onErrorResume` switches to the fallback `Flux`. Downstream sees the item received before the error, then receives `"cached"`, and completes.

If the error is not of a handled type, it must propagate downstream:

~~~java
TestPublisher<String> remote = TestPublisher.create();

StepVerifier.create(withFallback(remote.flux()))
    .then(() ->
        remote.error(new IllegalArgumentException("bad payload"))
    )
    .expectError(IllegalArgumentException.class)
    .verify(Duration.ofSeconds(2));
~~~

Key lesson: `TestPublisher` does not perform recovery itself; it creates a predictable failure scenario so you can test the application's `onErrorResume` logic.

## 9. Testing Empty Streams and Fallback Subscriptions

When `Mono.empty()` completes, operators like `defaultIfEmpty` or `switchIfEmpty` can trigger a fallback branch.

### 9.1. Empty Source

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.mono().defaultIfEmpty("unknown"))
    .then(source::complete)
    .expectNext("unknown")
    .verifyComplete();
~~~

Here the source emits no `onNext`. `defaultIfEmpty` supplies `"unknown"`.

### 9.2. Two Controlled Sources

~~~java
TestPublisher<String> primary = TestPublisher.create();
TestPublisher<String> fallback = TestPublisher.create();

Mono<String> result = primary.mono()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .then(() -> primary.assertSubscribers(1))
    .then(primary::complete)
    .then(() -> fallback.assertSubscribers(1))
    .then(() -> fallback.emit("from-fallback"))
    .expectNext("from-fallback")
    .verifyComplete();
~~~

The steps prove that `fallback` is **only** subscribed to after `primary` completes empty. If `primary` emits a value, `fallback` is never subscribed to.

### 9.3. When You Only Need to Know Whether Fallback Was Used

`PublisherProbe` is a lighter tool when you do not need to emit signals manually:

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.just("fallback"));

StepVerifier.create(
    Mono.<String>empty().switchIfEmpty(probe.mono())
)
    .expectNext("fallback")
    .verifyComplete();

probe.assertWasSubscribed();
probe.assertWasRequested();
~~~

`TestPublisher` also implements `PublisherProbe`, though if your sole goal is verifying subscribe/request/cancel on a branch, `PublisherProbe` expresses intent more clearly.

## 10. Testing Backpressure with request(n)

Reactive Streams uses `request(n)` so downstream tells upstream it may emit up to n more elements. Without checking demand, a test can accidentally run with unbounded requests.

`StepVerifier.create(publisher, initialRequest)` lets you start with zero demand and grant requests in batches:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .then(() -> source.assertSubscribers(1))
    .thenRequest(1)
    .then(() -> source.assertMinRequested(1).next(10))
    .expectNext(10)
    .thenRequest(1)
    .then(() -> source.next(20))
    .expectNext(20)
    .then(source::complete)
    .verifyComplete();

source.assertNoRequestOverflow();
~~~

Explanation:

- Initially the source has a subscriber but no demand has been granted.
- `thenRequest(1)` grants permission to emit one element.
- `TestPublisher` emits 10 and `StepVerifier` expects 10.
- Grant one more unit of demand, then emit 20.
- `assertNoRequestOverflow()` confirms the source did not receive `onNext` at zero demand per `TestPublisher`'s assertion logic.

**Note on operator-generated demand:** `StepVerifier.thenRequest(1)` does not mean a source behind `publishOn`, `flatMap`, or `buffer` sees only `request(1)`. Several operators use their own prefetching, batching, or request strategies. Place demand assertions at the layer you are actually testing and avoid hardcoding request numbers where operators are allowed to alter prefetch.

### 10.1. Checking Whether the Source Was Requested

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .then(source::assertWasSubscribed)
    .thenRequest(1)
    .then(source::assertWasRequested)
    .then(() -> source.emit("one"))
    .expectNext("one")
    .verifyComplete();
~~~

This creates a simple subscription/demand checklist: the subscriber registered first, then requested, then received the item.

### 10.2. Why Not Emit Past Demand on a Compliant Source?

If you create a hot `TestPublisher.create()` and attempt to call `next(value)` when downstream has not requested enough, the implementation can throw `IllegalStateException` because emitting beyond demand violates Reactive Streams. That is protective behavior by the test tool, not necessarily an error produced by the operator under test.

When you intentionally need to test an operator against a non-compliant upstream, use `createNoncompliant(Violation.REQUEST_OVERFLOW)`; never disable validation mindlessly.

## 11. Testing Cancellation

Cancellation matters for `take`, `timeout`, `switchMap`, aborted requests, and resource-backed pipelines. `TestPublisher` can verify that upstream was cancelled.

### 11.1. take(n) Cuts Off the Source

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().take(2))
    .then(() -> source.next("first", "second"))
    .expectNext("first", "second")
    .verifyComplete();

source.assertCancelled();
~~~

`take(2)` completes downstream after two elements and cancels the upstream subscription when no more data is needed. This is essential behavior to test when upstream represents an expensive connection, cursor, or event feed.

### 11.2. Cancelling Directly from StepVerifier

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

`thenCancel()` actively cancels the subscription instead of waiting for the source to complete or error. When production code works with infinite publishers, testing this way is far more natural than forcing the source to complete.

### 11.3. Do Not Confuse Cancellation with Completion

| Scenario | Downstream | Upstream |
| --- | --- | --- |
| `source.complete()` | Receives completion | Completed |
| `source.error(e)` | Receives error or recovery | Terminated with error |
| `take(2)` after two items | Completes normally | May receive cancellation |
| `thenCancel()` | Test actively cancels | Receives cancellation |
| `timeout` with no items | Receives `TimeoutException` if no fallback | Source subscription is cancelled |

Do not use `assertCancelled()` to prove a source `complete()`d normally. Similarly, `assertNoSubscribers()` and `assertCancelled()` ask different questions: one checks current subscriber count, while the other checks cancellation history.

## 12. Testing Timeouts Together with Virtual Time

`TestPublisher` controls events, while to simulate elapsed time without real waiting, use `StepVerifier.withVirtualTime(...)`:

~~~java
TestPublisher<String> slow = TestPublisher.create();

StepVerifier.withVirtualTime(() ->
        slow.flux().timeout(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));

slow.assertCancelled();
~~~

The `timeout` operator is created **inside the `withVirtualTime` supplier** so the virtual scheduler takes effect. The pre-created `TestPublisher` can remain outside because it only emits signals manually; the scheduler for `timeout` is the part that needs lazy assembly.

The distinction:

- `TestPublisher`: decides *which data or errors are emitted*.
- Virtual time: decides *how far Reactor's scheduler clock advances*.
- `StepVerifier`: decides *which outcomes are expected*.

A single test can use all three, yet virtual time is not mandatory for every `TestPublisher` scenario. If code uses a manually constructed scheduler or a non-Reactor clock, virtual time cannot control that clock.

## 13. Non-Compliant Reactive Streams Sources with createNoncompliant

Sometimes you need to test an operator or adapter's defenses against a non-compliant source—for example, an external library emitting items with zero demand, emitting `null`, emitting a second terminal signal, or continuing to emit after cancellation.

`TestPublisher.createNoncompliant(TestPublisher.Violation...)` creates a hot source allowed to violate specific rules.

| Violation | Relaxed behavior | What to watch out for |
| --- | --- | --- |
| `REQUEST_OVERFLOW` | Allows `next` even without sufficient subscriber demand | Can trigger downstream request-overflow detection |
| `ALLOW_NULL` | Allows passing `null` to `next` | `null` violates Reactive Streams; downstream may NPE/drop/error |
| `CLEANUP_ON_TERMINATE` | Allows attempting multiple consecutive terminal signals | Used to test dropping/handling of post-terminal signals |
| `DEFER_CANCELLATION` | Simulates a source continuing to emit after cancel | Simulates races between cancel and upstream emission |

Example demand-violating source:

~~~java
TestPublisher<Integer> misbehaving =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );
~~~

An advanced test can attach a subscriber that **never calls request**, emit an element, and verify `TestPublisher` recorded request overflow. Passing this source through `StepVerifier.create(..., 0)` and emitting `onNext` against zero demand may cause `StepVerifier` to fail verification; that is often the **purpose** of a negative test, not a sign `TestPublisher` is broken.

### 13.1. Positive Test Example Checking a Noncompliant Source

~~~java
TestPublisher<Integer> bad =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );

BaseSubscriber<Integer> zeroDemand = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        // Intentionally do not request.
    }
};

bad.subscribe(zeroDemand);
bad.next(42);
bad.assertRequestOverflow();

zeroDemand.cancel();
bad.assertCancelled();
~~~

Import `reactor.core.publisher.BaseSubscriber` and `org.reactivestreams.Subscription`. This tests a **violating-source scenario**, not how to implement a compliant production publisher.

### 13.2. Do Not Enable All Violations Just to Make Tests Pass

Using `ALLOW_NULL` or `REQUEST_OVERFLOW` as a workaround for normal test assertions hides demand and signal bugs. Enable only the exact violation you intend to simulate and document the invariant under test.

You do not need a noncompliant source to test HTTP 500, Redis timeouts, or a `DomainException`; `source.error(exception)` suffices for those.

## 14. Distinguishing TestPublisher, PublisherProbe, Sinks, and StepVerifier

| Tool | Where it runs | Purpose |
| --- | --- | --- |
| `TestPublisher` | Test source | Manually emit `onNext`/`onComplete`/`onError` and assert request/cancel |
| `StepVerifier` | Test subscriber | Define publisher expectations |
| `PublisherProbe` | Test branch | Verify a fallback/branch was subscribed, requested, cancelled |
| `Sinks.Many` | Usually production or test | Imperative bridge emitting into a `Flux`, with emit results and concurrency semantics |
| `VirtualTimeScheduler` | Test | Control scheduler time |
| `Mockito`/fake repository | Test dependency | Control service/repository calls |

Use `TestPublisher` when **signal ordering** is the focus. Use `PublisherProbe` when **taking a branch** is the focus. Use `StepVerifier` to verify **outputs**. Use `Sinks` when production needs an imperative-to-stream bridge with `Sinks`' multi-threading and backpressure rules.

Never place `TestPublisher` into a production Spring bean as a message bus just because `next()` is convenient; it is a `reactor-test` tool with thread-safety limitations documented in its Javadoc.

## 15. Simulating a Data Source at the Service Layer

Suppose a service reads temperature data and emits alerts only above a high threshold.

Interface:

~~~java
public interface TemperatureSource {
    Flux<Integer> temperatures();
}
~~~

Service:

~~~java
public final class AlertService {
    private final TemperatureSource source;

    public AlertService(TemperatureSource source) {
        this.source = source;
    }

    public Flux<String> alerts() {
        return source.temperatures()
            .filter(value -> value >= 80)
            .map(value -> "HOT:" + value);
    }
}
~~~

Test using `TestPublisher` as a fake source:

~~~java
TestPublisher<Integer> temperatures = TestPublisher.create();
AlertService service = new AlertService(temperatures::flux);

StepVerifier.create(service.alerts())
    .then(() -> temperatures.next(60, 82, 95))
    .expectNext("HOT:82", "HOT:95")
    .then(temperatures::complete)
    .verifyComplete();
~~~

This requires no database, sensor, WebSocket client, or real scheduler. The test focuses on the service's **filtering and mapping logic**. In WebFlux systems, dependencies can be constructor-injected, and tests supply a fake implementation returning `temperatures.flux()`.

If you also need to test HTTP status/headers/security, add `WebTestClient` as a complementary integration test. `TestPublisher` does not completely replace end-to-end testing.

## 16. Testing Empty Sources, Retries, and Re-Subscription

### 16.1. Empty Branch

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().switchIfEmpty(Flux.just(99)))
    .then(source::complete)
    .expectNext(99)
    .verifyComplete();
~~~

The result `99` shows the fallback runs when the source emits no `onNext`.

### 16.2. retry Is Actually Re-Subscription

Suppose:

~~~java
Flux<String> retried = source.flux().retry(1);
~~~

`retry(1)` does not re-emit a signal on the same subscription; it **re-subscribes to the source**. An already-errored hot `TestPublisher` is generally unsuitable for testing "fail first, succeed next" by continuing to call `next(...)` on the same instance. The source is already terminal, and a new subscription does not automatically turn a terminal state into a fresh attempt.

To test retries per attempt, combine `Flux.defer` with a **fresh source per subscription** or an attempt-counting fake service:

~~~java
AtomicInteger attempts = new AtomicInteger();

Flux<String> retried = Flux.defer(() -> {
    int attempt = attempts.incrementAndGet();

    if (attempt == 1) {
        return Flux.error(
            new IllegalStateException("temporary")
        );
    }

    return Flux.just("recovered");
}).retry(1);

StepVerifier.create(retried)
    .expectNext("recovered")
    .verifyComplete();

assertEquals(2, attempts.get());
~~~

`TestPublisher` remains useful when controlling each attempt, but instantiate separate instances or a factory returning the corresponding publisher. Do not bind all retries to an already-terminated hot source and expect valid results.

### 16.3. Testing Subscription Count

`TestPublisher` implements `PublisherProbe`, so `subscribeCount()` can help verify how many times upstream was subscribed to. However, if the model is a hot source with a fixed terminal state, subscription count alone does not prove each attempt re-executed real work. Combine assertions on the adapter/factory when testing retried network or database calls.

## 17. Limitations and Determinism Issues

`TestPublisher` is no magic wand for every asynchronous race. Its Javadoc emphasizes that it is generally not safe for concurrent manipulation from multiple threads.

**Practices that keep tests deterministic:**

1. Emit signals via `StepVerifier.then(...)` after subscription.
2. Drive `TestPublisher` from a single thread unless intentionally testing concurrency.
3. Never use `Thread.sleep` to guess "subscriber has registered".
4. Use `assertSubscribers(1)` inside a callback to prove the subscription exists.
5. Use `thenRequest(n)` when checking demand.
6. Always include a terminal expectation or `thenCancel()`.
7. Set verification timeouts so tests do not wait forever when a bug occurs.
8. Do not depend on cross-thread ordering when operators permit interleaving.
9. Do not assert exact request counts across prefetching operators unless guaranteed by API.
10. Keep sources and subscriptions isolated per test; create a fresh `TestPublisher` in each JUnit method to avoid shared state.

A test using `StepVerifier.then(...)` is usually far easier to read than spawning a separate `ExecutorService`, awaiting a latch, and abruptly calling `onNext`. Only bring in threading tools when concurrency/races themselves are the behavior under test.

## 18. Standalone Runnable Java 17+ Gradle Project

Below is a standalone project using Reactor Core 3.8.7, `reactor-test` 3.8.7, and JUnit 5. All test examples live in one class, needing no server, network, database, or Spring Boot.

Structure:

~~~text
reactor-testpublisher-lab/
  settings.gradle
  build.gradle
  src/
    main/java/demo/
      AlertService.java
      TemperatureSource.java
    test/java/demo/
      TestPublisherLabTest.java
~~~

### 18.1. settings.gradle

~~~groovy
rootProject.name = 'reactor-testpublisher-lab'
~~~

### 18.2. build.gradle

~~~groovy
plugins {
    id 'java'
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
    implementation 'io.projectreactor:reactor-core:3.8.7'
    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 18.3. TemperatureSource.java

~~~java
package demo;

import reactor.core.publisher.Flux;

@FunctionalInterface
public interface TemperatureSource {
    Flux<Integer> temperatures();
}
~~~

### 18.4. AlertService.java

~~~java
package demo;

import reactor.core.publisher.Flux;

public final class AlertService {
    private final TemperatureSource source;

    public AlertService(TemperatureSource source) {
        this.source = source;
    }

    public Flux<String> alerts() {
        return source.temperatures()
            .filter(value -> value >= 80)
            .map(value -> "HOT:" + value);
    }
}
~~~

### 18.5. TestPublisherLabTest.java

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TestPublisherLabTest {

    private static final Duration VERIFY_TIMEOUT =
        Duration.ofSeconds(3);

    @Test
    void hotSourceRunsMapAndFilter() {
        TestPublisher<String> source = TestPublisher.create();

        Flux<String> output = source.flux()
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(String::toUpperCase);

        StepVerifier.create(output)
            .then(() -> source.assertSubscribers(1))
            .then(() -> source.next(" java ", "  ", "reactor"))
            .expectNext("JAVA", "REACTOR")
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertNotCancelled();
    }

    @Test
    void emitSendsValuesThenCompletes() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.emit("A", "B"))
            .expectNext("A", "B")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void coldSourceReplaysBufferedValues() {
        TestPublisher<Integer> source = TestPublisher.createCold();
        source.emit(3, 5);

        StepVerifier.create(source.flux(), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(1)
            .expectNext(5)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        StepVerifier.create(source.flux())
            .expectNext(3, 5)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void upstreamErrorTriggersFallback() {
        TestPublisher<String> source = TestPublisher.create();

        Flux<String> output = source.flux()
            .onErrorResume(
                IOException.class,
                error -> Flux.just("cached")
            );

        StepVerifier.create(output)
            .then(() -> source.next("online"))
            .expectNext("online")
            .then(() ->
                source.error(new IOException("down"))
            )
            .expectNext("cached")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void unexpectedErrorIsPropagated() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(
                source.flux().onErrorResume(
                    IOException.class,
                    error -> Flux.just("cached")
                )
            )
            .then(() ->
                source.error(new IllegalArgumentException("invalid"))
            )
            .expectError(IllegalArgumentException.class)
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void emptySourceUsesFallback() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(
                source.mono().defaultIfEmpty("unknown")
            )
            .then(source::complete)
            .expectNext("unknown")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void switchIfEmptySubscribesFallback() {
        TestPublisher<String> primary = TestPublisher.create();
        TestPublisher<String> fallback = TestPublisher.create();

        Mono<String> output = primary.mono()
            .switchIfEmpty(fallback.mono());

        StepVerifier.create(output)
            .then(() -> primary.assertSubscribers(1))
            .then(primary::complete)
            .then(() -> fallback.assertSubscribers(1))
            .then(() -> fallback.emit("from-fallback"))
            .expectNext("from-fallback")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        primary.assertWasSubscribed();
        fallback.assertWasSubscribed();
    }

    @Test
    void publisherProbeShowsFallbackWasNotUsed() {
        TestPublisher<String> primary = TestPublisher.create();
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("cached"));

        StepVerifier.create(
                primary.mono().switchIfEmpty(fallback.mono())
            )
            .then(() -> primary.emit("live"))
            .expectNext("live")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        fallback.assertWasNotSubscribed();
    }

    @Test
    void demandIsGrantedInTwoSteps() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
            .expectSubscription()
            .then(() -> source.assertSubscribers(1))
            .thenRequest(1)
            .then(() -> source.assertMinRequested(1).next(10))
            .expectNext(10)
            .thenRequest(1)
            .then(() -> source.next(20))
            .expectNext(20)
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertNoRequestOverflow();
    }

    @Test
    void takeCancelsUpstreamAfterEnoughItems() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().take(2))
            .then(() -> source.next("first", "second"))
            .expectNext("first", "second")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertCancelled();
    }

    @Test
    void verifierCanCancelExplicitly() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.next(1))
            .expectNext(1)
            .thenCancel()
            .verify(VERIFY_TIMEOUT);

        source.assertCancelled();
    }

    @Test
    void virtualTimeTriggersTimeoutWithoutSleeping() {
        TestPublisher<Integer> silent = TestPublisher.create();

        StepVerifier.withVirtualTime(() ->
                silent.flux().timeout(Duration.ofSeconds(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify(VERIFY_TIMEOUT);

        silent.assertCancelled();
    }

    @Test
    void noncompliantSourceCanRecordRequestOverflow() {
        TestPublisher<Integer> source =
            TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW
            );

        BaseSubscriber<Integer> noDemand = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(
                    Subscription subscription) {
                // Intentionally do not call request.
            }
        };

        source.subscribe(noDemand);
        source.next(42);
        source.assertRequestOverflow();

        noDemand.cancel();
        source.assertCancelled();
    }

    @Test
    void serviceRespondsToControlledSensorEvents() {
        TestPublisher<Integer> source = TestPublisher.create();
        AlertService service = new AlertService(source::flux);

        StepVerifier.create(service.alerts())
            .then(() -> source.next(60, 82, 95))
            .expectNext("HOT:82", "HOT:95")
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void retryResubscribesToFreshDeferredAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        Flux<String> retrying = Flux.defer(() -> {
            if (attempts.incrementAndGet() == 1) {
                return Flux.error(
                    new IllegalStateException("temporary")
                );
            }
            return Flux.just("recovered");
        }).retry(1);

        StepVerifier.create(retrying)
            .expectNext("recovered")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        assertEquals(2, attempts.get());
    }
}
~~~

**This structure is a standalone runnable example.** Short snippets in earlier sections sometimes use placeholder variables like `source`, `process(...)`, or `withFallback(...)`; they explain the API rather than replacing the complete files above.

### 18.6. Running the Tests

Requires Java 17 and a Gradle version supporting Java 17, with Reactor dependencies downloadable from Maven Central. If the project includes the Gradle Wrapper:

~~~bash
./gradlew test
~~~

If there is no Wrapper but Gradle is installed:

~~~bash
gradle test
~~~

Running a single test method:

~~~bash
gradle test --tests demo.TestPublisherLabTest.demandIsGrantedInTwoSteps
~~~

When successful, Gradle reports task `:test` succeeded; the tests themselves print no fixed stdout because assertions are the outcome. Do not expect a fixed stdout snapshot with versions/elapsed time, as Gradle output varies by environment.

### 18.7. Reading Failure Output

If a test times out, check:

- Was `verify(...)` actually called?
- Did the source have a subscriber before emitting `next(...)`?
- Was `source.complete()` or `source.error(...)` forgotten?
- Did `StepVerifier` issue enough `thenRequest(n)` calls?
- Was the source triggered before `then(...)` due to mixing up hot/cold?
- Did an operator alter demand or trigger cancellation before the expectation?
- Was a time operator created before the virtual scheduler was enabled?

If `assertSubscribers(1)` fails, review the pipeline subscription and callback order; do not work around it with `Thread.sleep` when `StepVerifier` can control it directly.

## 19. Common Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Calling `next` before `verify` on a hot source | Values get ignored | Use `then(...)` post-subscription or `createCold` |
| Forgetting `verify` | `StepVerifier` is only a builder, test never runs | Call `verify`/`verifyComplete` |
| Forgetting a terminal signal | Test can hang | `complete`/`error`/`thenCancel` plus timeout |
| Calling `emit` then `next` | Source is already completed | Use `next` for ongoing sequences |
| Using `createCold` assuming hot events | Replay distorts timing | Pick factory matching semantics |
| Using `createColdNonBuffering` without understanding overflow | Unexpected failures under low demand | Check Javadoc and request bounds |
| Emitting past demand on a compliant source | `IllegalStateException` from test source | Grant demand or use noncompliant intentionally |
| Using `assertMinRequested(1)` across `publishOn` expecting exact demand | Prefetch alters requests | Test operator contract, do not pin arbitrary demand |
| Using `TestPublisher` to simulate sleep/time | Slow/racy tests | Combine with virtual time |
| Reusing an errored hot `TestPublisher` for a second retry | No independent attempt | `Flux.defer`/new factory per subscription |
| Using noncompliant to mask bugs | Loses Reactive Streams contract testing | Enable only the specified violation |
| Sharing a `TestPublisher` across parallel tests | Races/flakiness | Create a fresh source inside each `@Test` |
| Confusing error with cancellation | Wrong lifecycle assertions | Inspect terminal signals and `assertCancelled` properly |
| Checking fallback subscription by comparing values only | Does not prove execution path | `PublisherProbe` or `TestPublisher` assertions |
| Using `TestPublisher` in production | Unsuitable semantics and concurrency | Use `Sinks` / adapters / appropriate event producers |
| Testing only success cases | Misses errors, empty, cancellation | Add negative/terminal scenarios |
| Using unbounded `verify()` | Suite can hang | `verify(Duration)` or `setDefaultTimeout` |

## 20. Checklist Before Finalizing a Reactor Test

Before committing a test using `TestPublisher`, answer:

1. Does the test verify a specific operator/service behavior or the whole system?
2. Does the scenario need a hot or cold/replaying source?
3. Is `TestPublisher` placed at the right dependency boundary?
4. With a hot source, are signals emitted after subscription?
5. Did you use `then(...)` to order signals and expectations?
6. Does request count need verification; if so, did you use initial request 0 and `thenRequest`?
7. Does any prefetching operator alter upstream demand?
8. Is the terminal outcome defined: complete, error, or cancel?
9. Does the test have a timeout?
10. When testing fallbacks, did you prove the fallback was or was not subscribed appropriately?
11. When testing retries, is a fresh publisher created per attempt?
12. Does a noncompliant source serve a specific rule-violation scenario?
13. Does the test avoid unnecessary scheduler/`Thread.sleep`/race dependencies?
14. Are unit tests separated from DB, WebSocket, and HTTP integration tests?
15. Do assertions check business semantics rather than merely "no error"?

## 21. Review Questions and Answers

**Question 1. What is `TestPublisher` used for?**

It creates a Publisher whose `onNext`, `onComplete`, and `onError` signals the test manually controls, while asserting subscriptions, requests, and cancellations.

**Question 2. How does `TestPublisher` differ from `StepVerifier`?**

`TestPublisher` drives the upstream source; `StepVerifier` declares downstream expectations and executes the subscription on `verify`.

**Question 3. How does hot `create()` differ from cold `createCold()`?**

Hot primarily sends events to currently attached subscribers; cold buffers and replays events for subscribers with demand handling.

**Question 4. How does `next()` differ from `emit()`?**

`next` emits `onNext` without terminating. `emit` emits values and completes.

**Question 5. Why emit `source.next` inside `StepVerifier.then`?**

To ensure the subscriber is registered before the hot source emits events, avoiding races and lost events.

**Question 6. When should `thenRequest(n)` be used?**

When testing backpressure or staged demand distribution.

**Question 7. Why might `assertMinRequested` not equal `thenRequest`?**

Intermediate operators perform prefetching/buffering and can reshape upstream requests.

**Question 8. When does `assertCancelled()` succeed?**

When the publisher had a subscriber that cancelled, e.g., via `take(n)`, `timeout`, or `thenCancel()`.

**Question 9. How is a `Mono.empty` produced from `TestPublisher`?**

Use `source.mono()` in the pipeline and call `source.complete()` without calling `next`.

**Question 10. What is the value of `PublisherProbe`?**

It lets you assert that a branch was or was not subscribed/requested/cancelled without manually emitting signals.

**Question 11. What does `REQUEST_OVERFLOW` mean?**

It lets `TestPublisher` simulate a source emitting `onNext` without enough demand, to test behavior against Reactive Streams-violating sources.

**Question 12. Why can retrying a hot `TestPublisher` that already errored be wrong?**

Retry means re-subscribe; an already-terminal hot source does not automatically rerun a fresh attempt. Use `Flux.defer`/a factory creating a publisher per subscription.

**Question 13. Is `TestPublisher` safe for concurrent `next` calls from multiple threads?**

The Javadoc notes it is generally not thread-safe for concurrent emission; standard tests should drive it sequentially.

**Question 14. When is virtual time needed?**

When the pipeline includes `timeout`/`delay`/`retryBackoff` or logic relying on a Reactor scheduler. `TestPublisher` alone does not create a virtual clock.

## 22. Summary and Official References

- `TestPublisher` lives in `reactor-test` and is a manually controlled Publisher.
- `create()` is hot, `createCold()` is cold replay, and `createNoncompliant(...)` simulates spec-violating sources.
- `next` emits values; `emit` emits values then completes; `complete` and `error` terminate the stream.
- `flux()` and `mono()` integrate with Reactor operators.
- `StepVerifier.then(...)` emits signals after subscription is established.
- `thenRequest` and `thenCancel` test demand and cancellation.
- Assertions on `TestPublisher` check subscriptions, requested demand, cancellation, and request overflow.
- `PublisherProbe` is a concise choice when only checking execution paths.
- Virtual time controls schedulers and does not replace manual signal emission.
- Always set timeouts, avoid races, and never use `TestPublisher` as a production event bus.

References:

1. [Project Reactor — Testing Reference](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, `PublisherProbe`, and virtual time.
2. [Reactor TestPublisher Javadoc 3.8.x](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): factories, signal emission, assertions, and `Violation`.
3. [Reactor StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `then`, `thenRequest`, `thenCancel`, `verify`, and terminal expectations.
4. [Reactor PublisherProbe Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): subscription, request, and cancellation probing.
5. [Project Reactor — Backpressure Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): request and subscription behavior.
6. [Reactive Streams Specification](https://www.reactive-streams.org/): rules for `request(n)`, `onNext`, `onError`, `onComplete`, and cancellation.
7. [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): organizing and executing Java 17 tests.
