# Testing Demand, Backpressure, and Cancellation in Reactive Streams and Project Reactor

## 1. Learning Objectives

A reactive stream can emit the expected values in `StepVerifier.expectNext(...)` and still be broken in critical ways: emitting more items than the subscriber requested, inappropriate prefetching/buffering, failing to cancel upstream when a client disconnects, or continuing to consume resources after `cancel`. That is why **testing demand, backpressure, and cancellation** must inspect both **data** and **subscription lifecycle**.

This lesson focuses on Reactive Streams and Project Reactor (commonly used in Spring WebFlux):

- Understand `Subscription.request(n)`, cumulative outstanding demand, `Long.MAX_VALUE`, and `Subscription.cancel()`.
- Distinguish **downstream** demand from the requests an operator sends **upstream**; never assume they are identical.
- Use `StepVerifier.create(publisher, 0)`, `thenRequest(n)`, `expectNext`, and `thenCancel()` to model a demand-controlling subscriber.
- Use `doOnRequest`, `doOnCancel`, and `doFinally` to observe signals accurately.
- Test request reshaping across `buffer`, `limitRate`, `flatMap`/`publishOn`, and `take`.
- Use `TestPublisher` to actively emit signals and assert request counts/cancellation; use `PublisherProbe` to track subscription, request, and cancel on a branch.
- Distinguish **complete**, **error**, **cancel**, **dispose**, **timeout**, **discard**, and resource cleanup.
- Understand the limits of `WebTestClient`: a passing HTTP response does not automatically prove item-by-item backpressure at the service/`Publisher` layer.
- Work through a complete Maven example on **Java 17, Spring Boot 3.5.16, Reactor 3.7.x, and JUnit Jupiter** covering Publisher unit tests and a WebFlux slice test.

**Core focus:** Proper tests do not ask only "what values did the publisher emit?", but also "what happens when there is zero demand?", "how much did the operator request from upstream?", and "after cancellation, are resources or subscriptions still active?".

## 2. Reactive Streams: Three Signal Types and Two Control Operations

### 2.1. Publisher–Subscriber Model

A `Publisher<T>` supplies a stream of signals to a `Subscriber<T>`. Upon `subscribe`, the Publisher passes a `Subscription` via `onSubscribe`. The Subscriber uses that subscription to control flow:

```text
Publisher<T>                         Subscriber<T>
     |                                      |
     |  onSubscribe(Subscription) --------> |
     |                                      |
     | <-------------------------- request(2)
     |                                      |
     |                 onNext(item1) -----> |
     |                 onNext(item2) -----> |
     |                                      |
     | <-------------------------- request(1)
     |                 onNext(item3) -----> |
     |                                      |
     | <------------------------------- cancel()
     |                                      |
     |    no further signals sent after cancel
```

The three primary signals from publisher to subscriber are `onNext(T)`, `onError(Throwable)`, and `onComplete()`. `onError`/`onComplete` are **mutually exclusive** terminal signals; not every stream terminates unless cancelled. `cancel()` is a control call sent **from subscriber to subscription**, not a special kind of `onComplete`.

### 2.2. What Is Demand?

`Subscription.request(n)` with `n > 0` grants permission to emit up to `n` additional `onNext` values. Demand accumulates as calls arrive and decrements as `onNext` signals are emitted; when the sum reaches the maximum large integer limit, implementations normally apply **saturating arithmetic** capped at `Long.MAX_VALUE` (meaning unbounded demand).

Example subscriber flow:
- Initial `request(2)` → permission for up to two `onNext` items.
- One received → remaining unfulfilled demand is one.
- Send `request(3)` → remaining demand becomes four.
- After receiving four more items → demand drops to zero.
- `request(Long.MAX_VALUE)` → treated as **unbounded**; downstream performs no item-by-item flow control.

`request(0)` and `request(-1)` **violate Reactive Streams rules**. Do not write tests sending negative requests to check business results and treat that as normal usage. `StepVerifier.create(publisher, 0)` is valid because it sets **initial request = 0 without calling `request(0)`**. That is how you test that a publisher does not emit `onNext` before receiving demand.

### 2.3. What Does Cancellation Mean?

`Subscription.cancel()` tells the publisher the subscriber no longer wants data. Publishers and operators must stop associated work and release resources per contract. Cancellation:
- Is neither `onComplete` nor `onError`.
- May be delayed or race with signals running on another thread; never assume instantaneous cancellation across external boundaries.
- Does not automatically "roll back" committed database work, already-dispatched HTTP calls, or completed side effects.
- Must clean up resources such as file handles, scheduled tasks, sockets, consumer registrations, and queue buffers per implementation.
- Can occur when a user aborts an HTTP streaming response, `take(n)` collects enough items, a `timeout` operator expires, or a test calls `thenCancel()`.

### 2.4. Three Termination States Table

| State | Who Initiates? | Downstream Signal | `doFinally` Receives |
| --- | --- | --- | --- |
| Complete | Publisher finishes valid data | `onComplete` | `SignalType.ON_COMPLETE` |
| Error | Publisher/operator signals failure | `onError` | `SignalType.ON_ERROR` |
| Cancel | Subscriber/operator stops early | No required terminal signal sent downstream | `SignalType.CANCEL` at operator positions observing the cancel |

You can use `doOnCancel` to assert cancellation explicitly and `doFinally` to distinguish the three termination/cancellation paths. Where `doFinally` sits in the pipeline determines which signal it observes; do not assume every `doFinally` across all branches sees the exact same signal.

## 3. Why Is a Test with Only `expectNext` Insufficient?

```java
StepVerifier.create(Flux.range(1, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();
```

This is a very useful **value unit test**. However, `StepVerifier.create(publisher)` defaults to **unbounded demand** (`Long.MAX_VALUE`). As a result, it **does not verify**:
- Whether the source waits for `request(1)` before emitting an item.
- Whether, when the subscriber only asks for two items, the source emits a third item.
- Whether an operator sends 256 upstream requests due to prefetching.
- Whether the subscription triggers `cancel`/cleanup when downstream leaves.

To test backpressure, you must **start with bounded or zero demand**, issue `thenRequest(n)`, and inspect request/cancel side effects at the right pipeline points. To test cancellation, end the scenario with `thenCancel()` and assert that the source observed cancellation.

## 4. `StepVerifier`: Scripting Demand Step by Step

### 4.1. Checking Initially Zero Demand

```java
AtomicInteger observed = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 3)
        .doOnNext(value -> observed.incrementAndGet());

StepVerifier.create(source, 0)
        .expectSubscription()
        .then(() -> assertThat(observed.get()).isZero())
        .thenRequest(1)
        .expectNext(1)
        .then(() -> assertThat(observed.get()).isEqualTo(1))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

This snippet belongs **inside a JUnit test method**, needing Reactor, AssertJ, `AtomicInteger`, and `Duration` imports. With synchronous `Flux.range`, the `observed=0` check runs after subscription but before any request. After `thenRequest(1)`, only one item flows downstream. `thenCancel()` ends the scenario via cancellation rather than expecting `onComplete`.

Note that `expectSubscription()` awaits the subscribe signal without issuing demand. `thenRequest(1)` is what **actually sends a request** from the test subscriber.

### 4.2. Delivering Demand in Two Batches

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

In this scenario, all five elements are delivered so the publisher can emit `onComplete`. Requesting 2 and then calling `expectNext(1, 2, 3)` triggers the verifier's under-requesting guard; that is not a valid way to test if a source "over-emits", because **the verifier itself refuses expectations exceeding granted demand**.

### 4.3. Comparing `initialRequest` and `StepVerifierOptions`

Two nearly equivalent ways to start with zero demand:

```java
StepVerifier.create(source, 0);
```

```java
StepVerifier.create(
        source,
        StepVerifierOptions.create()
                .initialRequest(0)
                .scenarioName("bounded-demand"));
```

With `StepVerifierOptions`, you can also attach a `scenarioName` for clearer error diagnostics and configure `checkUnderRequesting(true)` (enabled by default). Scenario names aid debugging without changing publisher behavior.

**Never** set `checkUnderRequesting(false)` just to silence an error when a test expects more items than it requested: that masks a broken test rather than fixing upstream backpressure.

### 4.4. Always Include a Final `verify` Call

`thenCancel()`, `expectComplete()`, or `expectError()` only declare how the scenario finishes. You still must call `verify()` or a shortcut like `verifyComplete()` / `verifyError()`. Otherwise, nothing subscribes or runs.

Set a timeout:

```java
StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Without a timeout, scenarios can hang indefinitely if a publisher stops emitting or a test forgets to supply demand. Choose timeouts suitable for unit tests; these are not production SLAs.

## 5. Placing `doOnRequest` Properly to Observe Upstream Demand

### 5.1. `doOnRequest` Is Instrumentation, Not a Request Throttle

```java
List<Long> requests = new CopyOnWriteArrayList<>();

Flux<Integer> source = Flux.range(1, 5)
        .doOnRequest(requests::add);

StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();

assertThat(requests).containsExactly(2L, 3L);
```

`doOnRequest` receives the count of **each individual request** passing that operator position. In a simple pipeline like above, batches of 2 and 3 reach the range source directly. With `buffer`, `flatMap`, `publishOn`, or `limitRate`, values observed **upstream** can differ from `thenRequest(...)` at the end of the chain.

### 5.2. Two `doOnRequest` Positions Answer Two Different Questions

```java
Flux<List<Integer>> pipeline = Flux.range(1, 12)
        .doOnRequest(n -> System.out.println("SOURCE demand=" + n))
        .buffer(3)
        .doOnRequest(n -> System.out.println("DOWNSTREAM demand=" + n));
```

This illustrates a declared pipeline; output depends on the subscriber and actual requests. When downstream requests **two buffers**, `buffer(3)` must request **six items** upstream to fill two complete buffers. `doOnRequest` **after `buffer`** sees demand in **lists/buffers**, whereas the one **before `buffer`** sees demand in individual items.

You cannot infer from `doOnRequest(6)` that the application subscriber itself called `request(6)`; it may have only asked for two buffers.

### 5.3. Cold, Hot, and Replay Sources Behave Differently

| Source | Typical Behavior | What to Watch When Testing Demand |
| --- | --- | --- |
| `Flux.range`, `Flux.fromIterable` | Cold, answers requests sequentially | Ideal for deterministically verifying demand contracts |
| `Flux.generate` | Cold, produces one element per demand | Suits custom controlled demand-driven producers |
| `Flux.create` | Callback bridge receiving external events | Requires choosing an overflow strategy and resource cleanup |
| `Sinks.Many` | Can be hot, multicast/replay/buffered depending on flavor | Hot producers may emit independently of a single subscriber's demand |
| `Flux.interval` | Time/scheduler drives ticks | Zero demand on a tick can trigger overflow/error |
| `share`, `publish`, `replay` | Alters subscriptions, caching, multicasting | Do not assume every test is the sole subscriber |

For hot sources, "publisher receives `onNext` before demand" can mean several things: a compliant sink may **buffer, drop, or error** instead of unlawfully delivering `onNext` to the subscriber. Always distinguish **source receiving events**, **operator buffering/dropping events**, and **subscriber receiving `onNext`**.

## 6. Backpressure: How Operators Reshape Requests

### 6.1. `buffer(n)` Changes Demand Units

Suppose:

```java
Flux<List<Integer>> batches =
        Flux.range(1, 8).buffer(2);
```

When a subscriber calls `request(2)` on `batches`, it asks for **two `List`s**; upstream can receive `request(4)` for four integers to assemble those batches. Tests must assert the right **unit** on each side of the operator.

### 6.2. `limitRate` Is Not a Time-Based Throttle

`limitRate(highTide)` splits a large downstream request into smaller upstream batches. `limitRate(highTide, lowTide)` tunes replenishment; `lowTide=0` fetches batches of size `highTide` without early refilling.

```java
Flux<Integer> source = Flux.range(1, 8)
        .limitRate(2, 0);
```

If downstream asks for eight values, upstream is requested in capped chunks rather than one `request(8)`. This is **demand shaping**, **not** a guarantee of "2 events/second"; time-based rate limiting requires separate scheduling/throttling mechanisms.

### 6.3. `flatMap`, `publishOn`, and Prefetch

Some operators use `prefetch` or eagerly demand multiple inner sequences. `flatMap` may request more from upstream and inner publishers than final downstream demand at a given instant; `publishOn` prefetches into a queue. Most of this is perfectly legal as long as emissions delivered to the subscriber stay within downstream demand.

When testing demand at an upstream point:
- Check the exact operator order.
- Know the configured prefetch, concurrency, and `lowTide`.
- Never blindly assert `upstream request == downstream request` across reshaping operators.
- Avoid hardcoding default prefetch numbers that can shift between Reactor releases; set prefetch explicitly when it is part of the contract.

### 6.4. `take(n)` and Cancellation

`take(n)` emits at most `n` items, cancels upstream upon reaching `n`, and completes downstream. In Reactor 3.7, `take(n)` caps total upstream demand at `n` by default; `take(n, false)` uses **unbounded upstream request** and cancels once `n` items arrive.

Both can return the exact same items downstream while incurring very different **upstream cost**. Especially with APIs or brokers that perform side effects per produced event, unbounded upstream demand can trigger wasted work prior to cancellation.

### 6.5. `onBackpressureBuffer`/`drop`/`latest`/`error`

Each backpressure operator serves a distinct purpose:

| Operator | When Upstream Outpaces Downstream | Main Trade-off |
| --- | --- | --- |
| `onBackpressureBuffer` | Temporarily stores items in a buffer | Consumes memory; set sensible capacity bounds |
| `onBackpressureDrop` | Discards items that cannot be delivered downstream | Data loss; may need metrics/callbacks |
| `onBackpressureLatest` | Retains only the newest item, dropping older queued ones | Loses intermediate states |
| `onBackpressureError` | Signals an error instead of buffering or silently dropping | Fail-fast; consumer must handle errors |
| `limitRate` | Shapes request batches sent upstream | Does not solve hot producers that ignore demand |
| `take(n)` | Caps required item count and stops early | Usually cancels upstream once `n` arrive |

Understand semantics relative to the source. With a **cold, demand-aware source** like `Flux.range`, zero downstream demand causes the source **not to emit**, leaving drop strategies with nothing to drop. To actually test overflow/dropping, use a **hot source** or `TestPublisher` simulating a demand-ignoring producer, while controlling timing and memory limits.

**Never** assume "adding `onBackpressureBuffer` makes production safe": unbounded buffers risk OOM pressure when upstream persistently outpaces downstream. Bounded buffers, overflow callbacks, and metrics must be verified in an operational context.

## 7. `TestPublisher` and `PublisherProbe`: Actively Controlling Sources

### 7.1. `TestPublisher` Emits Signals Under Test Control

`TestPublisher<T>` belongs to `reactor-test`. It lets tests emit `next`, `complete`, and `error` while asserting subscription and demand state:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
        .expectSubscription()
        .then(() -> source.assertSubscribers(1))
        .thenRequest(2)
        .then(() -> source.assertMinRequested(2))
        .then(() -> source.next(11, 12))
        .expectNext(11, 12)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

source.assertCancelled();
```

This snippet appears in full in Section 9. `TestPublisher.create()` creates a **test-driven hot source**, unlike `Flux.range` which auto-emits on demand. You must call `source.next(...)` inside `then(...)` to emit data at that step.

`assertMinRequested`/`assertMaxRequested` inspect demand per `TestPublisher` semantics at the moment of the check; assert **before emitting all items**, since emissions subtract from outstanding demand. With multiple subscribers, understand aggregate/min/max semantics rather than assuming a single number.

### 7.2. `TestPublisher` Is Not Automatically Production-Like

`TestPublisher.createNoncompliant(TestPublisher.Violation.REQUEST_OVERFLOW)` simulates a Publisher violating demand rules. It is useful for testing operator resilience and overflow paths, **yet it is a resilience test against a deliberately faulty source**, not a standard Reactive Streams model.

Flags like `ALLOW_NULL` or `DEFER_CANCELLATION` carry specific meanings; never enable them indiscriminately just to force a test green. When using noncompliant publishers, clarify whether **source violation** or **expected operator recovery** is under test, and check signals/drop hooks for your Reactor version.

### 7.3. `PublisherProbe` Observes Flows Without Manual Signal Emission

`PublisherProbe<T>` is useful when you want to verify whether a branch was:
- Subscribed?
- Requested?
- Cancelled?

```java
PublisherProbe<Integer> probe =
        PublisherProbe.of(Flux.range(1, 100));

StepVerifier.create(probe.flux(), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasRequested();
probe.assertWasCancelled();
```

No `onComplete` is expected; the subscriber intentionally cancels after two values. `PublisherProbe` fits fallback verification, cancellation checks, and path tracking without scattering `AtomicBoolean` flags everywhere.

### 7.4. `TestPublisher` vs. `PublisherProbe`

| Scenario | Pick | Why |
| --- | --- | --- |
| Must manually push `next`/`error`/`complete` into pipeline | `TestPublisher` | Active signal control |
| Must assert minimum request / overflow | `TestPublisher` | Provides request/subscriber state assertions |
| Only need to confirm fallback was subscribed/requested/cancelled | `PublisherProbe` | Lightweight, focused on path tracking |
| Must check cancellation when stopping a real `Flux` | `PublisherProbe.of(source)` or `doOnCancel` | Wraps the real source |
| Must prove business outputs | `StepVerifier` | Checks `onNext`/`onError`/`onComplete` |
| Must prove both outputs and lifecycle | `StepVerifier + Probe` | Observes both data and control flow |

`verifyComplete()` alone does not prove a fallback ran; `assertWasSubscribed()` alone does not prove the output was right. Combine them when the contract requires both.

## 8. Cancellation, `doFinally`, and Cleanup

### 8.1. Explicitly Cancelling with `StepVerifier`

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> values = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(values, 0)
        .expectSubscription()
        .thenRequest(3)
        .expectNext(1, 2, 3)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(cancelled.get()).isTrue();
```

In this synchronous example, `thenCancel` sends cancel upstream and invokes the `doOnCancel` callback. For async/external producers, wait synchronously for cleanup completion rather than asserting immediately from another thread while async cleanup is still in flight.

### 8.2. `doFinally` Distinguishes Three Termination Reasons

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 100)
        .doFinally(finalSignal::set);
```

When `thenCancel` occurs after a few items, `finalSignal` at that position observes `SignalType.CANCEL`. If the publisher emits everything, it sees `ON_COMPLETE`; if it errors, `ON_ERROR`. Do not equate downstream terminal signals with cancellation: `cancel` does not send `onComplete` to the subscriber.

### 8.3. Resource Cleanup with `Flux.using`

```java
AtomicBoolean closed = new AtomicBoolean();

Flux<Integer> values = Flux.using(
        Object::new,
        handle -> Flux.range(1, 100),
        handle -> closed.set(true));

StepVerifier.create(values, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(closed.get()).isTrue();
```

This simple example uses a dummy resource object; in production it might be a file handle, connection, or stream. `Flux.using` binds resource lifecycle to the subscription and cleans up on complete, error, or cancel as configured. For async resources, use `usingWhen` with dedicated cleanup publishers; never close resources inside `map`, where error or cancel paths easily skip cleanup.

### 8.4. WebFlux HTTP Cancellation Does Not Stop All Side Effects

When a client disconnects from an SSE/NDJSON streaming endpoint, Reactor Netty/WebFlux can cancel the associated subscription. However:
- Network disconnect detection can lag.
- An external HTTP call or blocking JDBC call already started may not be "retractable".
- A hot/shared source may keep emitting to other subscribers.
- `doOnCancel` placed before vs. after `share` observes different signals.
- Committed transactions, published messages, or completed payments do not roll back when a subscriber cancels.

Therefore, test cancellation at the **Publisher boundary** with `StepVerifier`/`PublisherProbe`, and verify server disconnect detection and resource release with controlled **integration tests** and proper instrumentation.

## 9. Complete Maven Project: Java 17 + Spring Boot 3.5.16

The demo separates two goals:
1. Reactor unit tests verifying demand/backpressure/cancellation **without a Spring context**.
2. A WebFlux slice test verifying the controller using the reactive service and JSON response — **not replacing demand unit tests**.

### 9.1. Directory Tree

```text
reactive-demand-lab/
├── pom.xml
├── src/main/java/com/example/reactivelab/
│   ├── ReactiveDemandApplication.java
│   ├── EventView.java
│   ├── StreamService.java
│   └── StreamController.java
└── src/test/java/com/example/reactivelab/
    ├── DemandContractTest.java
    ├── BackpressureOperatorsTest.java
    ├── CancellationContractTest.java
    ├── TestPublisherProbeTest.java
    └── StreamControllerWebFluxTest.java
```

All Java files belong to package `com.example.reactivelab`. There is no database, broker, or external service. Unit tests omit `@SpringBootTest` because Reactive Streams semantics do not require booting a container.

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-demand-lab</artifactId>
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
```

`reactor-test` is declared explicitly in test scope rather than relying on transitive inclusion from any starter. The Spring Boot BOM manages versions. `spring-boot-starter-webflux` provides Reactor Core/WebFlux and Netty runtime; `spring-boot-starter-test` brings JUnit Jupiter, AssertJ, Mockito, and Spring Test.

### 9.3. `ReactiveDemandApplication.java`

`src/main/java/com/example/reactivelab/ReactiveDemandApplication.java`:

```java
package com.example.reactivelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemandApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemandApplication.class, args);
    }
}
```

### 9.4. `EventView.java`

`src/main/java/com/example/reactivelab/EventView.java`:

```java
package com.example.reactivelab;

public record EventView(int id, String name) {}
```

Java records provide structural equality by default; when calling `StepVerifier.expectNext(new EventView(...))`, comparison checks both `id` and `name`.

### 9.5. `StreamService.java`

`src/main/java/com/example/reactivelab/StreamService.java`:

```java
package com.example.reactivelab;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class StreamService {

    public Flux<EventView> events(int count) {
        if (count < 1 || count > 100) {
            return Flux.error(
                    new IllegalArgumentException("count must be 1..100"));
        }
        return Flux.range(1, count)
                .map(i -> new EventView(i, "event-" + i));
    }

    public Flux<Integer> integers(int count) {
        if (count < 0 || count > 100) {
            return Flux.error(
                    new IllegalArgumentException("count must be 0..100"));
        }
        return Flux.range(1, count);
    }
}
```

`Flux.range` is a cold demand-aware source. With `count = 0` in `integers`, Reactor returns an empty `Flux`; `events` requires at least 1 because the HTTP endpoint expects a bounded non-empty range. Validation errors are returned via `Flux.error` **upon subscription**, not thrown synchronously on method call.

### 9.6. `StreamController.java`

`src/main/java/com/example/reactivelab/StreamController.java`:

```java
package com.example.reactivelab;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/streams")
public class StreamController {
    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<EventView> list(
            @RequestParam(defaultValue = "3") int count) {
        return service.events(count);
    }
}
```

`GET /streams?count=3` returns a JSON array with three `EventView` objects. Using `application/json` causes WebFlux to serialize the finite `Flux` into a JSON array, which codecs may buffer/aggregate; never treat the number of JSON items read by an HTTP client as the `Subscription.request(n)` count at the service layer. That is why unit demand tests live separately.

### 9.7. `DemandContractTest.java`

`src/test/java/com/example/reactivelab/DemandContractTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class DemandContractTest {

    @Test
    void emitsNothingUntilFirstDemand() {
        AtomicInteger emitted = new AtomicInteger();
        Flux<Integer> source = Flux.range(1, 4)
                .doOnNext(n -> emitted.incrementAndGet());

        StepVerifier.create(source, 0)
                .expectSubscription()
                .then(() -> assertThat(emitted.get()).isZero())
                .thenRequest(1)
                .expectNext(1)
                .then(() -> assertThat(emitted.get()).isEqualTo(1))
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void fulfillsDemandInTwoBatches() {
        List<Long> requests = new CopyOnWriteArrayList<>();
        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requests::add);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();

        assertThat(requests).containsExactly(2L, 3L);
    }

    @Test
    void serviceEmitsRecordsUsingBoundedRequest() {
        StreamService service = new StreamService();

        StepVerifier.create(service.events(4), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(
                        new EventView(1, "event-1"),
                        new EventView(2, "event-2"))
                .thenRequest(2)
                .expectNext(
                        new EventView(3, "event-3"),
                        new EventView(4, "event-4"))
                .verifyComplete();
    }

    @Test
    void baseSubscriberCanRequestOneByOneThenCancel() {
        List<Integer> seen = new CopyOnWriteArrayList<>();
        AtomicInteger cancels = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 20)
                .doOnCancel(cancels::incrementAndGet);

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                seen.add(value);
                if (value == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }
        };

        source.subscribe(subscriber);

        assertThat(seen).containsExactly(1, 2, 3);
        assertThat(cancels.get()).isEqualTo(1);
    }
}
```

**What this verifies:**
- `initialRequest=0` is not a protocol-violating `request(0)`.
- `thenRequest(2)` and `thenRequest(3)` permit exact two-batch delivery directly on `Flux.range`.
- With `StreamService.events`, downstream receives exact records per batch—without assuming every operator forwards 1:1.
- `BaseSubscriber` demonstrates manual demand control: `hookOnSubscribe` requests 1, and `hookOnNext` requests the next item or cancels. Because `Flux.range` is synchronous, assertions right after `subscribe` are deterministic; async publishers require waiting/synchronization.

### 9.8. `BackpressureOperatorsTest.java`

`src/test/java/com/example/reactivelab/BackpressureOperatorsTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class BackpressureOperatorsTest {

    @Test
    void bufferReshapesRequestIntoItems() {
        List<Long> upstreamRequests = new CopyOnWriteArrayList<>();

        Flux<List<Integer>> pipeline = Flux.range(1, 8)
                .doOnRequest(upstreamRequests::add)
                .buffer(2);

        StepVerifier.create(pipeline, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(List.of(1, 2), List.of(3, 4))
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        // Two requested buffers of size 2 -> four upstream values.
        assertThat(upstreamRequests).contains(4L);
    }

    @Test
    void limitRateSplitsLargeRequestsIntoSmallBatches() {
        List<Long> upstreamRequests = new CopyOnWriteArrayList<>();

        Flux<Integer> source = Flux.range(1, 8)
                .doOnRequest(upstreamRequests::add)
                .limitRate(2, 0);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(8)
                .expectNextCount(8)
                .verifyComplete();

        assertThat(upstreamRequests).isNotEmpty();
        assertThat(upstreamRequests)
                .allMatch(n -> n > 0L && n <= 2L);
        assertThat(upstreamRequests.stream()
                .mapToLong(Long::longValue).sum())
                .isGreaterThanOrEqualTo(8L);
    }

    @Test
    void takeCapsNumberOfDeliveredElements() {
        StepVerifier.create(Flux.range(1, 100).take(3), 0)
                .expectSubscription()
                .thenRequest(3)
                .expectNext(1, 2, 3)
                .verifyComplete();
    }

    @Test
    void badInputIsAnErrorSignalNotAnImmediateThrow() {
        StreamService service = new StreamService();

        Flux<Integer> source = service.integers(-1);

        StepVerifier.create(source)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && error.getMessage().contains("0..100"))
                .verify(Duration.ofSeconds(2));
    }
}
```

In `bufferReshapesRequestIntoItems`, `doOnRequest` sits **upstream of `buffer(2)`** to capture item-level upstream demand. For `limitRate(2, 0)`, avoid overly fragile exact sequence assertions unless required; the key invariant is that every upstream request is between 1 and 2 and their sum suffices for eight items. The `take` test checks output, while upstream cancellation is verified in the next class.

### 9.9. `CancellationContractTest.java`

`src/test/java/com/example/reactivelab/CancellationContractTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.assertj.core.api.Assertions.assertThat;

class CancellationContractTest {

    @Test
    void cancelInvokesCallbackAndFinallySignal() {
        AtomicBoolean cancelled = new AtomicBoolean();
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        Flux<Integer> source = Flux.range(1, 100)
                .doOnCancel(() -> cancelled.set(true))
                .doFinally(finalSignal::set);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        assertThat(cancelled.get()).isTrue();
        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }

    @Test
    void publisherProbeConfirmsUpstreamCancellation() {
        PublisherProbe<Integer> probe =
                PublisherProbe.of(Flux.range(1, 100));

        StepVerifier.create(probe.flux(), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        probe.assertWasSubscribed();
        probe.assertWasRequested();
        probe.assertWasCancelled();
    }

    @Test
    void usingReleasesResourceOnCancel() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<Integer> values = Flux.using(
                Object::new,
                handle -> Flux.range(1, 100),
                handle -> closed.set(true));

        StepVerifier.create(values, 0)
                .expectSubscription()
                .thenRequest(1)
                .expectNext(1)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        assertThat(closed.get()).isTrue();
    }
}
```

This class verifies **observable cancellation** rather than stopping assertions after two items. Replacing `thenCancel()` with `expectComplete()` before the 100-item source finishes causes the test to wait or fail for lack of demand. Using `Flux.range(1, 2)` and requesting two could let upstream complete before cancel; hence the example uses range 100 so cancellation clearly precedes any terminal signal.

### 9.10. `TestPublisherProbeTest.java`

`src/test/java/com/example/reactivelab/TestPublisherProbeTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

class TestPublisherProbeTest {

    @Test
    void testPublisherChecksDemandAndCancellation() {
        TestPublisher<Integer> upstream = TestPublisher.create();

        StepVerifier.create(upstream.flux(), 0)
                .expectSubscription()
                .then(() -> upstream.assertSubscribers(1))
                .thenRequest(2)
                .then(() -> upstream.assertMinRequested(2))
                .then(() -> upstream.next(11, 12))
                .expectNext(11, 12)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        upstream.assertCancelled();
        upstream.assertNoRequestOverflow();
    }

    @Test
    void probeChecksFallbackSubscriptionAndRequest() {
        PublisherProbe<Integer> fallback =
                PublisherProbe.of(Flux.just(99));

        Flux<Integer> pipeline = Flux.<Integer>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(pipeline)
                .expectNext(99)
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }
}
```

**Why separate these two tests:**
- `TestPublisher` emits `next(11, 12)` **after** observing `request(2)`, checking both demand and absence of overflow.
- `PublisherProbe` wraps the fallback branch, confirming it was subscribed/requested and completed normally (not cancelled), instead of merely asserting output `99` and guessing which branch ran.

### 9.11. `StreamControllerWebFluxTest.java`

`src/test/java/com/example/reactivelab/StreamControllerWebFluxTest.java`:

```java
package com.example.reactivelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(StreamController.class)
class StreamControllerWebFluxTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StreamService service;

    @Test
    void controllerDelegatesAndWritesJsonArray() {
        when(service.events(3)).thenReturn(Flux.just(
                new EventView(1, "event-1"),
                new EventView(2, "event-2"),
                new EventView(3, "event-3")));

        client.get()
                .uri("/streams?count=3")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(EventView.class)
                .hasSize(3);

        verify(service).events(3);
    }
}
```

`@WebFluxTest` tests the reactive controller, request binding, and serialization in a WebFlux slice, with `@MockitoBean` supplying the service since slices do not auto-scan `@Service` beans like a full context. This tests the **HTTP contract** and does not verify item-by-item demand on the upstream `Flux`. Protect those semantics by keeping `DemandContractTest`/`CancellationContractTest` at the Publisher layer. To prove cancellation propagates on real client disconnects, write a separate running-server integration test using a streaming media type and instrumentation.

### 9.12. Commands to Run the Project

Requires JDK 17+, Maven, and reachable dependency repositories. From the `reactive-demand-lab` directory:

```bash
mvn -q clean test
mvn -q -Dtest=DemandContractTest test
mvn -q -Dtest=BackpressureOperatorsTest test
mvn -q -Dtest=CancellationContractTest test
mvn -q -Dtest=TestPublisherProbeTest test
mvn -q -Dtest=StreamControllerWebFluxTest test
```

All classes are designed to PASS; a successful Maven run returns **exit code 0**. No fixed stdout/log formatting is assumed because Maven, context startup, and schedulers differ across environments. Inspect `target/surefire-reports` on any FAILURE.

You can run the application with:

```bash
mvn spring-boot:run
```

Then in another terminal:

```bash
curl "http://localhost:8080/streams?count=3"
```

The JSON response contains three objects (`id=1,2,3` and `name="event-1","event-2","event-3"`). However, **cURL receiving the full JSON does not prove `request(1)` or cancellation propagation**; the JSON array may have been aggregated by the WebFlux codec before writing.

## 10. Simulating Hot Sources and Overflow Policies

### 10.1. When Does a Backpressure Conflict Actually Happen?

`Flux.range` knows how to wait for requests, so downstream will not receive extra unrequested items. Understand how other sources behave:
- Kafka receivers/network consumers may maintain internal buffers and prefetching.
- SSE/metrics sources may emit on an independent clock regardless of client speed.
- Callback APIs may push events into `Flux.create`/`Sinks.Many` without consulting demand.
- Prefetching operators may temporarily queue items between upstream and downstream.

Backpressure holds at the **subscriber boundary**, which does not mean **every external producer** slows down automatically. When a producer cannot slow down, define an explicit buffer/drop/latest/error policy and capacity.

### 10.2. Controlled Illustrative Snippets

```java
Flux<String> bounded = incoming
        .onBackpressureBuffer(128);
```

This is an **illustrative snippet assuming `Flux<String> incoming`**. It does not guarantee you can never run out of memory: on sustained streams, producers can exceed capacity and trigger an overflow error depending on the operator overload used. When overflow behavior is part of the contract, use an overload with an explicit overflow callback/strategy and test via `TestPublisher` or a deterministically emitting hot source.

```java
Flux<String> fastChanging = incoming
        .onBackpressureLatest();
```

This keeps only the latest item not yet delivered to the subscriber; it suits UI/telemetry state where skipping intermediate values is acceptable, and does not suit ledger transactions where every event must be preserved.

### 10.3. At Which Boundary Do Noncompliant Publisher Tests Apply?

To test how a custom operator handles a source violating demand:

```java
TestPublisher<Integer> rogue = TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW);
```

The snippet merely constructs a **deliberately noncompliant** publisher; a complete test must define the operator under test, `next` timing, expected error/drop, and cleanup. Never guess a specific exception type without verifying operator and version behavior. `TestPublisher` is suited to verifying **fault tolerance against broken sources**, not proving production publishers comply with Reactive Streams.

### 10.4. Discard Differs from Drop and Cancel

- **Drop**: source or operator drops an unusable signal or post-terminal signal per hook/semantics.
- **Discard**: operator discards queued/buffered data due to `filter`, `cancel`, or `error`; cleanup for resource-bearing elements can hook into `doOnDiscard`.
- **Cancel**: control signal sent to the upstream subscription.
- **Complete**: successful terminal signal sent downstream to the subscriber.

Cancellation can trigger discarding prefetched items in queues; to test memory/resource cleanup, verify discarded objects and close counters/states rather than relying solely on `PublisherProbe.assertWasCancelled()`. With operators that alter paths and async queues, avoid races by using deterministic waits.

## 11. Virtual Time and Demand: Avoiding Real-Time Waits

### 11.1. Example Without Waiting 2 Real Hours

`Flux.interval` emits on a scheduler; use `StepVerifier.withVirtualTime` to control the clock.

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(2),
        0)
        .expectSubscription()
        .thenRequest(2)
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

This test pattern uses Reactor 3.7 and `Flux`, `Duration`, `StepVerifier` imports. **Construct the publisher inside the lambda** so Reactor can swap the scheduler for the virtual scheduler before building operators. Building `Flux.interval` outside and returning it from the lambda can bypass the virtual clock.

### 11.2. Zero Demand on an Interval Tick

`Flux.interval` has a distinct property: on each clock tick, if downstream has zero demand when the tick fires, it can emit an overflow error rather than "waiting politely until the subscriber asks" like `Flux.range`. Therefore:
- In virtual-time tests, issue requests **before advancing the clock** when expecting values.
- Do not call `expectNoEvent` with demand 0 and advance across multiple ticks expecting the source to stay quiet.
- If business logic needs to drop ticks for slow consumers, choose an explicit operator/policy rather than relying on incidental interval behavior.

### 11.3. Virtual Time Does Not Prove Real Infrastructure

Virtual time verifies operator timing, yet does not faithfully simulate TCP sockets, remote schedulers, blocking callbacks, or external library clocks. Testing real cancellation over HTTP or message brokers still requires integration tests with proper resource cleanup and timeouts.

## 12. Test Scenario Classification Table

| Goal | Primary Setup | Required Assertions |
| --- | --- | --- |
| No emission at `demand=0` | `StepVerifier.create(publisher, 0)` | No `onNext` or side effect before `thenRequest` |
| Emit `n` items on `request(n)` | `thenRequest(n)` + `expectNext` | Exact count, order, and values |
| Multi-step demand increases | `thenRequest(2)`, `thenRequest(3)` | Items arrive per batch |
| Measure upstream demand | `doOnRequest` at exact position | Request list/metrics instead of guessing |
| Buffer reshapes demand units | `buffer(k)` + upstream instrumentation | `request(m buffers)` maps to `m × k items` |
| `limitRate` shapes batches | `limitRate(high, 0)` + trace | Every upstream request stays within cap |
| Subscriber cancellation | `thenCancel` | `doOnCancel`/`doFinally(CANCEL)`/Probe |
| Resource closed on cancel | `Flux.using` or `usingWhen` | Resource closed / cleanup publisher executed |
| Programmatic signal emission | `TestPublisher` | `next` after request, no overflow, cancelled |
| Fallback branch tracking | `PublisherProbe` | subscribed/requested/cancelled flags |
| Time and demand combined | `withVirtualTime` + `thenRequest` | Ticks/items follow virtual clock |
| HTTP JSON contract | `@WebFluxTest + WebTestClient` | Status/JSON/route/delegation |
| HTTP client disconnect | Running-server integration test | Server-side cancel/cleanup instrumentation |
| Hot producer overflow | Hot Sink / intentional noncompliant publisher | Bounded buffer/drop/error/cleanup per contract |

When reading test failures, isolate the **failing phase**: missing Spring context/bean, `StepVerifier` `AssertionError`, publisher `onError`, or timeout from unfulfilled demand. Each has a different root cause and fix.

## 13. Debugging and Common Pitfalls

### 13.1. `StepVerifier` Waits Forever at `expectNext`

Often caused by `initialRequest=0` with a forgotten `thenRequest(n)`, or requesting fewer items than expected. Check:
- The `StepVerifier.create(..., initialRequest)` value.
- Total `thenRequest` issued prior to each `expectNext`.
- `buffer(n)`/prefetch operators affecting signal delivery.
- An async scheduler whose virtual clock hasn't been advanced.

Add a sensible `verify(Duration.ofSeconds(...))` so tests never hang indefinitely. Raising timeouts does not fix missing demand.

### 13.2. Test Expects More `onNext` Than Requested

With `StepVerifierOptions.checkUnderRequesting` enabled by default, the verifier flags scenarios expecting more `onNext` signals than requested. Fix the test script by issuing enough `thenRequest` calls—never disable the check. If a **publisher itself emits past demand**, that is a source/protocol bug; use upstream instrumentation or noncompliant `TestPublisher` when verifying operator fault tolerance.

### 13.3. `doOnRequest` Observes `Long.MAX_VALUE`

`StepVerifier.create(publisher)` defaults to unbounded initial demand. Lambda-based `subscribe()` and `block()` typically issue unbounded demand as well. That is not a Reactor bug, just the subscriber API's default. Use `StepVerifier.create(publisher, 0)` with `thenRequest` to test bounded backpressure.

### 13.4. Expected Upstream Request 2, Observed 6

Downstream requesting 2 buffers from `buffer(3)` sends `request(6)` items upstream. With `flatMap`/`publishOn`, prefetching also increases upstream requests relative to downstream. Inspect the operator chain, `doOnRequest` placement, and buffer/prefetch sizes; do not change assertions to force green if that behavior violates the contract.

### 13.5. `thenCancel` Called, Yet No `onComplete` Observed

That is expected behavior: `cancel` does not ask the publisher for `onComplete`. Check `doOnCancel`, `SignalType.CANCEL`, `PublisherProbe.assertWasCancelled()`, and resource cleanup instead. Never expect `expectComplete` after `thenCancel` on the same subscription.

### 13.6. `take(n)` Completes, Yet Upstream Still Sees Large Requests

This difference can stem from `take(n, false)` or prefetching operators ahead of `take`. In Reactor 3.7, `take(n)` caps upstream demand by default; when protecting resource limits, put `doOnRequest` upstream of the exact operator and verify the real chain. Never infer from `n` output items that the producer did not compute extra items.

### 13.7. `onCancel` Runs, Yet External Work Keeps Running

`doOnCancel` only proves the callback observed cancellation. If the source offloaded work to a thread pool, HTTP client, native API, or broker, the callback must **explicitly cancel/dispose** the underlying handle. Verify the resource or task handle after cancel; if cleanup is asynchronous, synchronize on a cleanup completion signal rather than guessing with sleep.

### 13.8. `Flux.interval` Test Fails with `request(0)`

`Flux.interval` emits on timer ticks and can signal `onError` if zero demand exists when a tick arrives. Issue demand before `thenAwait`, or choose a source/overflow policy suited to the test. Never assume every source behaves like `Flux.range`.

### 13.9. `TestPublisher.next` Called Before Subscriber Request

`TestPublisher.create()` enforces certain demand rules; emitting past demand can error or behave according to API/violation mode. In compliant tests, call `thenRequest(2)` before `source.next(11, 12)`. Reserve `createNoncompliant(REQUEST_OVERFLOW)` for tests **deliberately** modeling protocol violations.

### 13.10. `PublisherProbe` Shows Subscribed but Not Requested

Subscription does not imply demand was sent. With `initialRequest=0` and no `thenRequest`, a probe sees subscription without request. Check the two flags separately. When fallback is skipped, `assertWasNotSubscribed` proves the branch was avoided; when entered and cancelled early, `assertWasCancelled` holds.

### 13.11. `WebTestClient` Passes While Stream Demand Is Wrong

At the HTTP layer, `WebTestClient` consumes responses via codecs with its own prefetching and aggregation. `expectBodyList` only proves the JSON array/response contract. To verify exact `request(n)` behavior at the service Publisher, use `StepVerifier` with bounded demand. To verify client disconnect propagation, write server-bound integration tests with proper subscription instrumentation.

### 13.12. Flaky Tests Caused by Schedulers and Timing

Relying on `Thread.sleep` and real-time `Flux.interval` makes tests flake under CI load. For time-based operators, use `StepVerifier.withVirtualTime` and construct the publisher **inside the supplier**; for async integration tests, use timeouts and explicit latches or publisher completion signals. Avoid asserting cross-thread ordering not guaranteed by contract.

### 13.13. Reused Publisher Carries State Across Tests

Hot `Sinks.Many`, `TestPublisher`, or shared/`cache` `Flux` instances retain subscriber and buffer state. Instantiate fresh Publishers and probes **inside every test method** for isolation; avoid reusing shared mutable sources unless concurrency across subscribers is specifically under test.

### 13.14. Items Discarded After Cancellation Leak Without Cleanup

Many operators hold prefetched queues. When items wrap closeable resources, configure `doOnDiscard` or operator-specific cleanup and verify disposal conditions. Upstream `doOnCancel` alone does not automatically release items already buffered inside downstream operator queues.

### 13.15. Confusing Cancel and Error in Metrics

If subscriber cancellation is miscounted as an "error" in metrics, dashboards and alerts become noisy. Use `doFinally(signalType -> ...)` or Reactor observation/metrics at the right layer. Normal HTTP client disconnects are not necessarily incidents; classify them appropriately before alerting.

## 14. Advanced Scenarios: End-to-End System Backpressure

### 14.1. Reactive HTTP Does Not Map `request(n)` One-to-One Over the Network

Reactive Streams demand governs in-process `Publisher`/`Subscriber` interactions. HTTP/1.1 and HTTP/2 implement their own flow control and buffering, which do **not map one-to-one** by default to domain-event `Subscription.request(n)`. JSON serialization changes framing units; Netty maintains write buffers; TCP manages send/receive windows.

Therefore, observing an HTTP client receive 5 JSON objects does not allow claiming upstream saw exactly 5 requests. When protecting against excessive DB/repository reads, instrument at the data publisher/driver boundary.

### 14.2. R2DBC / Reactive Repositories

A reactive repository returning `Flux<Entity>` may apply driver-level prefetching, fetch sizes, or cursors. `take(10)` limits downstream emissions without guaranteeing the database physically executed at most 10 rows. Inspect query plans, driver settings, and run real database integration tests when performance guarantees matter. Never mistake a `StepVerifier` demand test for a SQL/driver backpressure guarantee.

### 14.3. Messaging / Brokers

Reactive Kafka/Pulsar/RabbitMQ consumers manage broker queues, prefetch counts, offsets, acknowledgments, and commit semantics distinct from Reactor demand. `cancel` may stop polling or close the stream without undoing committed offsets or acknowledged messages. In integration tests, verify explicitly whether cancel halts consumption and how in-flight messages are handled.

### 14.4. Multicast and Slow Consumers

With a hot shared publisher, two subscribers can have different demand rates. Operators buffer, drop, or apply multicast policies depending on the `Sinks.Many` flavor. Tests must attach **two independent subscriptions**, issue distinct demand rates, and assert events, overflow, and cancellation per subscriber. Never extrapolate multicast slow-consumer behavior from a single `StepVerifier`.

### 14.5. Cancellation Racing with Completion

An async source may be about to emit `onComplete` right as downstream cancels. `doFinally` at different points can observe different terminal signals due to the race; tests must not assume an exact order unless guaranteed by contract. For deterministic checks, use `TestPublisher`, latches, or controlled schedulers, or assert invariants (no leaks, no `onNext` after cancel) instead of a single timing outcome.

## 15. Self-Study Exercises

1. Write `StepVerifier.create(Flux.range(1, 10), 0)`, issue `thenRequest(1)`, expect one item, issue `thenRequest(2)`, expect two items, and cancel. Attach `doOnRequest` upstream to observe requests.
2. Convert the test above to `StepVerifierOptions.create().initialRequest(0).scenarioName(...)`. Deliberately expect beyond granted demand to inspect the error message, then restore protocol compliance.
3. Add `buffer(4)` to a `Flux`. Downstream requests two buffers. Before running, predict the minimum upstream demand at the source and confirm with `doOnRequest`.
4. Apply `limitRate(3, 0)` on a 20-item source with downstream requesting 20. Assert every upstream request is at most three without assuming downstream requests pass unchanged.
5. Wrap `Flux.range(1, 100)` with `PublisherProbe.of(...)`, consume three items, and cancel. Assert `wasSubscribed`, `wasRequested`, and `wasCancelled`.
6. Create `TestPublisher.create()`, emit nothing before demand; after `thenRequest(2)`, call `next(9, 10)`. Assert output, no overflow, and cancellation.
7. Use `Flux.using` to manage a resource with `close`. Exercise complete, error, and cancel paths and verify the resource closes exactly once in each case.
8. Compare `Flux.range` and `Flux.interval` with `initialRequest=0`. Explain why "stay silent while there is no demand" fails if the interval clock keeps ticking.
9. Run `@WebFluxTest` verifying `StreamController` returns a three-item JSON array. Explain why that test does not prove upstream received `request(3)`.
10. Design a cancellation test for a real streaming HTTP server: where would you instrument, how would the client cancel, and how would you synchronize on cleanup without races?
11. Given a hot stream emitting 1000 events/s to a client consuming 10 events/s, propose buffer/drop/latest/error, explain memory/loss/latency trade-offs, and write a test for your chosen policy.
12. A `request(1)` to `buffer(10)` sends `request(10)` upstream. Is this a Reactive Streams violation? Explain using **buffer units** and **item units**.

Mastery means identifying **demand on both sides of the pipeline**, terminal/cancel signals, and resource cleanup—rather than tweaking expected values until tests turn green.

## 16. Checklist Before Merging Reactive Tests

- [ ] Identified whether the Publisher is cold, hot, multicast, or uses queues/prefetch?
- [ ] Aware that `StepVerifier.create(publisher)` defaults to unbounded initial demand?
- [ ] Used `initialRequest=0` when verifying nothing emits before demand?
- [ ] Issued sufficient `thenRequest(n)` before each `expectNext(...)`?
- [ ] Checked both outputs **and** request traces, not just `expectNext`?
- [ ] Placed `doOnRequest` on the right side of the operator being measured?
- [ ] With `buffer`, distinguished buffer demand from item demand?
- [ ] With `limitRate`, avoided claiming it throttles events per second?
- [ ] With `flatMap`/`publishOn`, accounted for prefetching and avoided brittle exact demand assertions?
- [ ] With `thenCancel`, checked `doOnCancel`/`doFinally(CANCEL)`/Probe?
- [ ] Distinguished cancellation from completion, error, and timeout?
- [ ] Verified resource cleanup actually executed on cancel rather than just logging?
- [ ] With `TestPublisher`, avoided emitting past demand in "compliant" tests?
- [ ] With `PublisherProbe`, asserted subscribe/request/cancel on the right branch?
- [ ] With hot producers, defined bounded buffers, drop/error policies, and metrics?
- [ ] For scheduler-driven sources, used virtual time or proper synchronization instead of sleeps/flaky assertions?
- [ ] When testing HTTP with `WebTestClient`, recognized it does not verify source-level `request(n)` counts?
- [ ] When testing external DBs/brokers, accounted for prefetching, acks, and side effects independent of cancellation?
- [ ] Configured sensible timeouts, created fresh sources/probes per test method, and avoided shared state leaks?
- [ ] Executed the JUnit/Maven suite and verified root causes for any failures?

**Conclusion:** Reactive Streams demand is governed by `request(n)`, operators **reshape demand** via buffering and prefetching, and `cancel()` stops a subscription **distinctly** from `onComplete`/`onError`. A strong test suite uses `StepVerifier` with bounded demand, `doOnRequest` to observe demand, `TestPublisher`/`PublisherProbe` to verify signal paths, and `doOnCancel`/cleanup assertions to ensure cancellation takes effect. At the WebFlux HTTP layer, keep HTTP contract tests separate from Publisher semantics tests.

## 17. Official References

- Project Reactor 3.7 — Testing (`StepVerifier`, `TestPublisher`, `PublisherProbe`): https://projectreactor.io/docs/core/3.7.17/reference/testing.html
- Project Reactor 3.7 — On Backpressure and Ways to Reshape Requests: https://projectreactor.io/docs/core/3.7.17/reference/subscribe-backpressure.html
- Project Reactor 3.7 — `Flux` API (`take`, `limitRate`, `buffer`): https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html
- Reactor Test 3.7 — `StepVerifier` API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/StepVerifier.html
- Reactor Test 3.7 — `TestPublisher` API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/publisher/TestPublisher.html
- Reactor Test 3.7 — `PublisherProbe` API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/publisher/PublisherProbe.html
- Reactive Streams Specification v1.0.4: https://www.reactive-streams.org/
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `WebTestClient` for WebFlux testing: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
