# Choosing Bounded Buffer, Drop, Latest, or Error in Reactor

## 1. The Problem: When the Producer Is Faster Than the Consumer

In a Spring WebFlux application, a data source can emit events faster than the system processes them: continuous telemetry updates, WebSocket notifications, market ticks, logs, database read results, or callback API streams. Keeping every element in RAM can cause memory to grow unboundedly. Dropping elements or terminating the stream arbitrarily can lose critical business information.

Reactive Streams uses **backpressure**: the Subscriber calls `Subscription.request(n)` to declare it is ready to receive up to `n` elements. The Publisher and operators must honor demand on each link. When a source cannot or will not slow down to match downstream, an **explicit overload policy** is required.

This lesson compares four `Flux` choices in Project Reactor:

- **Bounded buffer:** temporarily hold a number of elements; when full, error or apply a chosen eviction policy.
- **Drop:** discard newly arriving elements immediately when there is no downstream demand.
- **Latest:** retain only the newest element while downstream is not ready.
- **Error:** signal an error immediately when an element arrives without demand to forward it.

After this lesson, you should understand the mechanisms, APIs, which data can be lost, impact on memory and business correctness, runnable Java 17+ examples, and how to test with controlled `request` calls.

## 2. Foundation: Demand Does Not Equal Emission Rate

Each `request(n)` with `n > 0` adds demand to the subscription; total `onNext` signals emitted to the Subscriber must not exceed total granted demand. `Long.MAX_VALUE` denotes unbounded demand. `cancel()` requests terminating the subscription, though cancellation does not necessarily eliminate in-flight signals immediately.

~~~text
Subscriber                Boundary                 Upstream
    |                      |                         |
    |---- request(2) ----->|                         |
    |<---- onNext(A) ------|<----- onNext(A) ---------|
    |<---- onNext(B) ------|<----- onNext(B) ---------|
    |    demand = 0        |<----- onNext(C) ---------|
    |                      |                         |
    |  buffer/drop/latest/error is how C is handled  |
~~~

The diagram **illustrates a boundary where upstream may push extra data**; with a Publisher that truly honors demand and propagates demand intact, the source may pause at B until requested again, avoiding data-loss policies altogether.

A core distinction: Reactor's `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest`, and `onBackpressureError` **request unbounded demand from the operator's own upstream**, then handle data according to downstream demand. They provide a policy at **that boundary**; they are not a mechanism for sending slowdown commands to an external producer. That is why these operators can overflow a buffer or drop data even when a source like `Flux.range` natively supports backpressure.

With many lambda-based `subscribe(...)` overloads, Reactor defaults to requesting `Long.MAX_VALUE`. When testing overload, you must **actively constrain demand**, e.g. using `BaseSubscriber` or `StepVerifier.create(publisher, 0)`. If downstream immediately requests unboundedly, overflow/drop situations usually do not appear in examples.

## 3. Policy Comparison Table

| Operator | When Downstream Has No Demand | Extra Memory at Boundary | Data Loss? | Error Signal on Overload? | Suitable Example |
| --- | --- | --- | --- | --- | --- |
| `onBackpressureBuffer(maxSize)` | Queues up to `maxSize` elements, then overflows | Bounded by **element count** | Overflowing element rejected; stream errors | Yes | Short bursts where ordering and threshold detection matter |
| `onBackpressureBuffer(maxSize, DROP_OLDEST)` | When full, drops oldest element, keeps new one | Bounded | Yes | Not due to full buffer | Queues prioritizing recent data |
| `onBackpressureBuffer(maxSize, DROP_LATEST)` | When full, drops **newly arriving element** | Bounded | Yes | Not due to full buffer | Preserving pending batch, rejecting additional events when full |
| `onBackpressureDrop()` | Discards newly arriving element immediately when no demand | Holds no backlog in operator itself | Yes | Not from dropping | Samplable or droppable events |
| `onBackpressureLatest()` | Overwrites held element with newest element | At most one waiting element in this operator | Yes | Not from overwriting | State snapshots, current sensor readings |
| `onBackpressureError()` | Emits `onError` when an element arrives and cannot be forwarded | Holds no backlog in this operator | Stream fails | Yes | Losing even one element is unacceptable |
 
**Note:** the bounds above apply only to memory/queues managed by that specific operator; upstream, scheduler, network, or downstream buffers can exist independently. A single `onBackpressureBuffer(maxSize)` does not guarantee total memory across the entire pipeline is bounded.

## 4. Bounded Buffer: Retaining Data with a Clear Threshold

Basic API:

~~~java
Flux<T> bounded = source.onBackpressureBuffer(maxSize);
~~~

Reactor requests data eagerly from upstream and queues elements that cannot be forwarded immediately up to `maxSize`. When the next element arrives while the buffer is full, the upstream source is cancelled and the pipeline enters an overflow error state. **This error may be deferred from delivery to the Subscriber until already-buffered elements have been consumed**. Therefore, do not assume every `onBackpressureBuffer` delivers the error immediately downstream.

Conceptual example with five elements `1,2,3,4,5`, zero initial demand, and `maxSize=2`:

~~~text
Upstream:        1   2   3   4   5
Initial buffer: [1]
After item 2:   [1,2]
Item 3:         overflow, source cancelled, pending error emission
Downstream:     request(2) → onNext(1), onNext(2), onError(overflow)
~~~

The source cancelled after item 3, so it does not necessarily emit up to 4, 5. If upstream is asynchronous, cancellation timing and in-flight signals can produce different timing effects; the diagram illustrates the principle.

An overload exists to observe the overflowing element:

~~~java
Flux<T> bounded = source.onBackpressureBuffer(
        256,
        element -> recordOverflow(element)
);
~~~

`recordOverflow` here is an application callback. It runs upon overflow, helping observe or release resources attached to the element. Do not use this callback to divert elements into a secondary stream without ordering, retry, and backpressure policies.

### 4.1. When the Buffer Is Full: Choosing `ERROR`, `DROP_OLDEST`, or `DROP_LATEST`

Reactor provides the enum `reactor.core.publisher.BufferOverflowStrategy`:

~~~java
Flux<T> oldest = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.DROP_OLDEST);

Flux<T> newestRejected = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.DROP_LATEST);

Flux<T> failed = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.ERROR);
~~~

This is an **API illustration** with `source` and `T` supplied by the application; in a Java file, you need `import reactor.core.publisher.BufferOverflowStrategy;` and an appropriate `source` declaration.

When all five elements are emitted while downstream has not requested and the buffer holds at most two elements:

- `DROP_OLDEST`: receives 1, 2; item 3 replaces 1, item 4 replaces 2, item 5 replaces 3 → ultimately **4, 5** remain.
- `DROP_LATEST`: receives 1, 2; new items 3, 4, 5 are all discarded because the buffer is full → ultimately **1, 2** remain.
- `ERROR`: holds 1, 2; upon seeing 3, transitions to overflow state; buffered items may still be delivered downstream before signaling the error.

The name `DROP_LATEST` in `BufferOverflowStrategy` is especially easy to misread: here it **discards the newly arriving element**, not "keep only the latest value" like `onBackpressureLatest()`. To keep one latest value, use `onBackpressureLatest` itself.

Extended overload:

~~~java
source.onBackpressureBuffer(
        2,
        element -> onDiscardedFromFullBuffer(element),
        BufferOverflowStrategy.DROP_OLDEST
);
~~~

The callback is invoked with **the element actually evicted**; with `DROP_OLDEST`, that can be an older element sitting inside the buffer rather than the newly arriving event. When using `ERROR`, the error may only travel downstream after the backlog drains. Having the callback does not replace error handling with `onError`.

### 4.2. Do Not Use an Unbounded Buffer for Uncontrolled Sources

`source.onBackpressureBuffer()` has no concrete capacity bound and can grow RAM indefinitely when the producer stays faster than the consumer. For long-lived event sources or large payloads, avoid this default.

`maxSize` counts **elements**, not bytes. Two buffers with the same `maxSize` can occupy vastly different memory if elements are integers, large strings, or objects wrapping byte buffers. Measure actual payload sizes, set thresholds based on peak handling capacity and burst duration, and monitor queue occupancy, item age, and overflow counts.

Some overloads like `onBackpressureBuffer(Duration ttl, int maxSize, Consumer onBufferEviction)` add a retention time limit; they fit when stale data loses value, though TTL evictions must be handled and eviction behavior clearly understood. A time limit does not substitute for a memory limit.

## 5. Drop: Discard New Elements When There Is No Demand

Syntax:

~~~java
Flux<T> stream = source.onBackpressureDrop();
Flux<T> monitored = source.onBackpressureDrop(
        item -> reportDropped(item)
);
~~~

`onBackpressureDrop` maintains no backlog of its own. If downstream has demand, it forwards the element; if demand is exhausted, it discards the newly arrived element. Dropped data is **not automatically re-sent** when the Subscriber requests more later.

Example requesting zero elements while the source emits `1..5`:

~~~text
Source emits: 1  2  3  4  5
Demand:       0  0  0  0  0
Drop:         1  2  3  4  5
Downstream:   no onNext, may receive onComplete
~~~

Suitable for sampled telemetry updates, verbose debug logs, and signals where users do not have to see every single point. **Unsuitable** if each element is a transaction, payment command, or mandatory audit event.

Count drop occurrences, monitor data-loss rates, keep callbacks lightweight, and avoid blocking on the emission path. If elements hold resources needing release, choose a cleanup hook with discard support and make release safe and idempotent.

## 6. Latest: Keep Exactly the Newest Element While Waiting for the Consumer

`source.onBackpressureLatest()` holds only one pending element; when there is no demand and a new value arrives, it replaces the held element with the newly arrived one. When downstream requests again, it receives the newest value held at the boundary, not the entire history.

With `1..5` emitted while `demand = 0`:

~~~text
After 1: latest = 1
After 2: latest = 2 (drops 1)
After 3: latest = 3 (drops 2)
After 4: latest = 4 (drops 3)
After 5: latest = 5 (drops 4)
On request(1): downstream receives 5, then completes if source already completed
~~~

A new element arriving **while demand exists** can be delivered immediately without necessarily passing through the latest slot. "Latest" also does not mean always emitting one value per second or self-adjusting frequency; it solely defines how to handle arrivals when downstream lacks demand.

Suitable for UIs displaying current CPU usage, last location, gauge readings, or mutually replaceable snapshots. Unsuitable for events representing **state transitions that must all be recorded** (such as "debited 10 units"); keeping only the newest movement loses intermediate changes.

**Distinguish:** `onBackpressureLatest()` holds at most one pending element. `onBackpressureBuffer(2, DROP_OLDEST)` holds the last two elements in our example; `onBackpressureBuffer(2, DROP_LATEST)` holds the first two elements. The three are not equivalent.

## 7. Error: Treating Data Loss as a Violation Requiring Handling

`source.onBackpressureError()` emits `onError` when the source attempts to push an element across the boundary while downstream has no demand. It neither queues to wait nor silently loses data. Reactor raises an overflow exception, typically identifiable via `Exceptions.isOverflow(error)`.

~~~java
import reactor.core.Exceptions;
import reactor.core.publisher.Flux;

Flux<Integer> strict = Flux.range(1, 5)
        .onBackpressureError();

strict.subscribe(
        value -> System.out.println("next=" + value),
        error -> System.out.println("overflow=" + Exceptions.isOverflow(error))
);
~~~

**This snippet only illustrates the callback.** With lambda `subscribe` overloads, downstream usually requests `Long.MAX_VALUE`, so the example above may **not trigger overflow**; to test it genuinely, you need a Subscriber with bounded demand or `StepVerifier` (see Sections 8–9).

`onBackpressureError` fits when data loss is unacceptable and the processing branch must stop to report an error or recover. However, **signaling an error does not itself guarantee transactions are saved**. Once the source is cancelled, you need an explicit business strategy such as controlled retries from a replayable source, a durable queue, a dead-letter queue, or snapshot recovery. Do not blindly use `onErrorResume` to swallow overflow and report success if lost data is critical.

Difference from `onBackpressureBuffer(maxSize)` or `BufferOverflowStrategy.ERROR`: buffered overflow may **wait to drain the backlog before delivering `onError`**, whereas `onBackpressureError()` signals the error upon missing demand with no operator backlog to drain.

## 8. Runnable Java 17+ Program with Zero Initial Demand

The example creates a synchronous `Flux.range(1, 5)` source. `BaseSubscriber` is configured **not to request in `hookOnSubscribe`**. The `onBackpressure*` operators automatically request unboundedly from upstream, so all five elements are pushed to the boundary and the overload policy is triggered. Only after the source finishes emitting does the program call `request(...)` to inspect any pending elements.

Gradle project structure:

~~~text
reactor-backpressure-demo/
├── build.gradle
└── src/main/java/BackpressureDemo.java
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'BackpressureDemo'
}
~~~

`src/main/java/BackpressureDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.Exceptions;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;

public class BackpressureDemo {

    private static void run(
            String label, Flux<Integer> stream, long requestAfter) {

        System.out.println("[" + label + "]");

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                // Intentionally do not request here to create an overload situation.
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("onNext=" + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println(
                        "overflow=" + Exceptions.isOverflow(error));
            }
        };

        stream.subscribe(subscriber);

        if (requestAfter > 0) {
            subscriber.request(requestAfter);
        }
    }

    public static void main(String[] args) {
        run("bounded", Flux.range(1, 5)
                .onBackpressureBuffer(2), 2);

        run("drop oldest", Flux.range(1, 5)
                .onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_OLDEST), 2);

        run("drop latest incoming", Flux.range(1, 5)
                .onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_LATEST), 2);

        run("drop", Flux.range(1, 5)
                .onBackpressureDrop(), 1);

        run("latest", Flux.range(1, 5)
                .onBackpressureLatest(), 1);

        run("error", Flux.range(1, 5)
                .onBackpressureError(), 1);
    }
}
~~~

Run with Gradle installed in the project directory:

~~~bash
gradle -q run
~~~

If the project has a Gradle wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. With synchronous `Flux.range` and controlled requests as above, stdout **produced by the program** is:

~~~text
[bounded]
onNext=1
onNext=2
overflow=true
[drop oldest]
onNext=4
onNext=5
onComplete
[drop latest incoming]
onNext=1
onNext=2
onComplete
[drop]
onComplete
[latest]
onNext=5
onComplete
[error]
overflow=true
~~~

Exact interpretation:

1. `bounded` keeps 1 and 2, overflows upon encountering the third element, yet delivers the error downstream **after** the two queued elements are requested and consumed.
2. `drop oldest` replaces buffer contents when full, leaving only 4 and 5.
3. `drop latest incoming` keeps the two older elements 1 and 2, rejecting 3, 4, 5.
4. `drop` retains no elements because demand remained 0 when the source finished emitting; calling `request(1)` afterward cannot recover discarded data.
5. `latest` retains only 5 and completes once the pending element is delivered.
6. `error` overflows immediately upon encountering the first element while `demand = 0`.

These results intentionally use a **synchronous source and deterministic operation ordering**. With network sources, schedulers, hot publishers, or multiple subscriptions, do not deduce multithreaded log order or pending counts from a single ad-hoc run.

## 9. Testing Policies with `StepVerifier`

In a project with JUnit 5, add `reactor-test` from the matching Reactor version family to test scope:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/test/java/BackpressurePolicyTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.Exceptions;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressurePolicyTest {

    @Test
    void boundedBufferErrorsAfterDrainingQueuedValues() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(2), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();
    }

    @Test
    void dropOldestKeepsTwoMostRecentItems() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_OLDEST), 0)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }

    @Test
    void dropLatestRejectsNewItemsWhenFull() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_LATEST), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .verifyComplete();
    }

    @Test
    void dropDiscardsAllWithoutDemand() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureDrop(), 0)
            .verifyComplete();
    }

    @Test
    void latestKeepsOnlyFinalItemWithoutDemand() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureLatest(), 0)
            .thenRequest(1)
            .expectNext(5)
            .verifyComplete();
    }

    @Test
    void errorFailsAtFirstUnrequestedElement() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureError(), 0)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();
    }
}
~~~

`StepVerifier.create(publisher, 0)` creates a Subscriber with **initial request equal to 0**; `thenRequest(n)` grants demand only at explicit test steps. That is why the scenarios above test genuine overload; if you merely use `subscribe(System.out::println)`, the Subscriber usually requests unboundedly and creates no pressure.

When writing tests for real sources with schedulers, control time and emission points, avoiding reliance on `Thread.sleep` or accidental timing order. You can add tests for `cancel`, discarded resources, and varying demand levels if business code requires it.

## 10. Choosing a Policy Based on Data Characteristics

### 10.1. When to Use a Bounded Buffer

Use when there are **short bursts**, downstream still has enough average capacity, element ordering must be preserved, and memory budget allows. Choose `maxSize` from real measurements and specify the full-buffer action: overflow error, keeping older data, or keeping newer data. If not a single event may be lost, let overload **surface explicitly** and plan for durable queuing at the appropriate layer.

Example: processing a job list where items cannot be lost; you may buffer boundedly to absorb short load spikes, yet once the threshold is exceeded, stop accepting new work or return an error rather than silently losing jobs.

### 10.2. When to Use Drop

Use when intermediate values are non-mandatory, such as dense observability metrics or debug messages. The system accepts that while the subscriber is busy, elements arriving then are not seen. Do not choose drop for invoices, balance changes, legal obligation notices, or messages requiring guaranteed processing.

### 10.3. When to Use Latest

Use for **current-state-replaces-previous-state** models: current temperature, last position, latest progress percentage, dashboard status. If users only need to know "what is it right now", discarding stale updates preserves freshness. For streams of cumulative **events** or distinct state transitions, `latest` can corrupt business semantics.

### 10.4. When to Use Error

Use when losing a single element is an error that must be surfaced so the system stops/recovers and must avoid giving a false impression of success. Design the overflow detection point, how errors are returned to clients, retries if the source supports replay, and observability. With HTTP/WebFlux, an `onError` late in a stream may fail the response or close the connection depending on when it occurs; do not promise always converting it into a specific HTTP status code after the response has started sending.

### 10.5. Decision Table

| Question | Recommendation |
| --- | --- |
| Data **cannot be lost**? | Prefer propagating demand back to the source or using a durable queue; consider `onBackpressureError`/bounded buffer with explicit overflow. |
| Overload only for short intervals? | Bounded buffer and monitor queue depth, overflow count. |
| Safe to discard all messages while busy? | `onBackpressureDrop`. |
| Need only the newest state? | `onBackpressureLatest`. |
| Want to retain some recent messages, dropping old ones when full? | `onBackpressureBuffer(maxSize, DROP_OLDEST)`. |
| Want to keep already-accepted backlog, rejecting new messages? | `onBackpressureBuffer(maxSize, DROP_LATEST)`. |
| Want missing demand detected immediately? | `onBackpressureError`. |

## 11. Boundaries with Related APIs

Do not confuse `onBackpressure...` with `Flux.create` and `Flux.push`. When bridging callback APIs yourself, `FluxSink.OverflowStrategy` offers choices such as `BUFFER`, `DROP`, `LATEST`, and `ERROR` at the **source-creation sink level**. Default `FluxSink.OverflowStrategy.BUFFER` can be unbounded; choosing the right sink strategy upfront is a producer-side decision. By contrast, `onBackpressureBuffer/Drop/Latest/Error` are **operators attached to a Flux** to handle demand mismatch at that position.

`limitRate(n)` and `prefetch` settings adjust the **request pattern** propagated upstream; they are not equivalent to drop/latest. `publishOn(scheduler)` passes data through its own queue and prefetch limit; it can shift where backlog accumulates, but does not replace a necessary data-loss policy. Using `subscribeOn`/`publishOn` to pick threads does not by itself solve sustained overload.

Operators like `sample`, `sampleTimeout`, or `throttleLast` (if present in your API/version) represent **time/condition-based sampling**; they are not identical to `onBackpressureDrop`, which is demand-driven. If you need a fixed reporting frequency, do not use drop as a rate throttle in place of sampling.

## 12. Observability, Resource Cleanup, and Real-World Failure Modes

In production, choosing a policy must go hand in hand with metrics and data-loss handling rules:

- **Monitor:** overflow counts, dropped/evicted elements, backlog depth, item age in queue, emission/consumption rates, latency, and actual memory. Do not rely solely on element counts if payload sizes vary.
- **Resource cleanup:** elements may hold resources such as `DataBuffer`, byte buffers, or handles needing release. Reactor supports `doOnDiscard(type, handler)` on operators with discard support; place the hook properly downstream and check each operator's Javadoc. Cleanup should be idempotent and non-blocking; if using both overflow/drop callbacks and `doOnDiscard`, avoid double-releasing.
- **Errors:** treat `onError` as a real error condition; do not use `onErrorComplete` or infinite retries to mask overflow when zero data loss is required. Retries can re-subscribe and re-emit duplicates if the source does not guarantee idempotency.
- **Cancellation:** `cancel()` can lose elements remaining in queues; an element received upstream does not mean it was committed downstream. For business logic requiring confirmation, use acknowledgments or transactions at the proper boundary.
- **Operator placement:** where the policy sits relative to `map`, `flatMap`, `publishOn`, and other buffers affects which elements are retained, work already spent, and demand flow. Measure on the real pipeline instead of guessing from a simple diagram.

Example incrementing a drop metric counter inside a service that already provides a counter:

~~~java
Flux<Event> monitored = events.onBackpressureDrop(
        dropped -> metrics.incrementDroppedEvents()
);
~~~

`Event`, `events`, and `metrics` are application-supplied components; this is a **non-standalone illustrative snippet**. If you need to track object size or cleanup, add handling according to the resource type and actual policy rather than assuming dropping is free.

## 13. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Using unbounded `onBackpressureBuffer()` with an infinite source | Backlog grows continuously, risking OOM. | Set `maxSize`, monitor, and design overflow handling. |
| Thinking a bounded buffer always drops silently when full | Default `onBackpressureBuffer(maxSize)` raises an overflow error. | Know the exact overload and strategy. |
| Confusing `DROP_LATEST` with `onBackpressureLatest` | One drops **newly arriving elements**, the other keeps **the newest**. | Write a zero-demand test distinguishing `1,2` from `5`. |
| Thinking `onBackpressureDrop` holds data for later requests | Discarded values cannot be recovered. | Use only when loss is valid; measure drop rate. |
| Calling `subscribe(System.out::println)` to test drop | Subscriber usually requests unboundedly, hiding overflow. | Use `BaseSubscriber` or `StepVerifier.create(...,0)`. |
| Using `onBackpressureLatest` for financial events | Loses intermediate events, causing wrong calculations. | Use real demand, durable queues, and acks. |
| Thinking `onBackpressureError` fails identically to bounded buffer right on emission | Bounded buffer may drain backlog before delivering the error. | Test the exact item/error sequence. |
| Assuming placing a downstream operator slows down an external producer | These operators request unboundedly from upstream and enforce policy locally. | Prefer end-to-end backpressure or throttling at the producer if possible. |
| Handling drops while forgetting to release pooled buffers | Leaks off-heap resources or handles. | Use proper idempotent discard/cleanup callbacks. |
| Retrying overflow infinitely | Repeated overload; can create duplicates or worsen the situation. | Bounded retries, backoff, idempotency, and replayable sources. |

## 14. Self-Check

1. Upstream emits `1..5` while downstream requests 0; what does `onBackpressureBuffer(2, DROP_OLDEST)` keep? **4, 5**.
2. Same scenario, but `DROP_LATEST`? **1, 2**, because new events are rejected when full.
3. What does `onBackpressureLatest()` keep? **Only 5**.
4. Can `onBackpressureDrop()` recover `1..5` if `request(1)` arrives after the source emitted and completed? **No**.
5. How does `onBackpressureError()` differ from bounded buffer `ERROR`? **Error holds no waiting backlog; bounded buffer may deliver the error after draining its backlog.**
6. Why can `Long.MAX_VALUE` prevent a test from triggering drop? **Because downstream requested unboundedly; there is no lack of demand at the boundary.**
7. Is `maxSize` a memory size in bytes? **No, it is the element count in the buffer; you still must monitor payloads and other queues.**
8. In a transactional system where no event may be lost, is choosing drop/latest to boost throughput safe? **No. You need throttling at the source or durable persistence with controlled retries/acks.**

**Key takeaway:** choosing a backpressure policy is a decision about **data correctness**, **latency**, **memory**, and **failure mode**. Bounded buffers prioritize retaining a bounded backlog; drop accepts losing events while busy; latest keeps only the newest state; error surfaces missing demand explicitly. Decide based on data semantics first, then write tests with controlled demand and measure behavior in the real pipeline.

## References

- [Reactor Flux Javadoc: onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest, onBackpressureError](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Reactor BufferOverflowStrategy Javadoc: ERROR, DROP_OLDEST, DROP_LATEST](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BufferOverflowStrategy.html).
- [Reactor Reference Guide: On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- [Reactor Reference Guide: Programmatically Creating a Sequence and FluxSink OverflowStrategy](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- [Reactor Exceptions Javadoc: isOverflow](https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html).
- [Project Reactor Testing: StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
