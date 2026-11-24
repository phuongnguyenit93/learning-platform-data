# Testing Slow Consumers and Fast Producers in Spring WebFlux and Reactor

## 1. The Problem: Producers Faster Than Consumers

In a reactive system, a publisher can emit data faster than a subscriber processes it. For example:

- A service receives thousands of events per second from a message broker.
- A WebSocket client pushes data continuously while the downstream service processes each message slowly.
- A streaming API reads from a database faster than the HTTP client's network speed.
- A pipeline calls an external service where each request takes a few hundred milliseconds while the source emits thousands of items.
- A `Flux.interval` emits at a fixed cadence while downstream is busy writing files or querying a database.

Without regulation, the system can build up queues, increase latency, grow heap, create GC pressure, or eventually run out of memory. Some sources can be told to pause or slow down; other sources are hot sources or external callbacks that cannot be paused easily.

Reactive Streams defines **backpressure** so a subscriber can tell a publisher how many elements it is ready to receive. Reactor provides operators to buffer, drop, retain the latest item, limit demand, or bound concurrent operations.

This lesson focuses on **testing a slow consumer against a fast producer**, understanding overload-handling policies, and choosing an approach that matches data semantics.

After this lesson, you will be able to:

1. Explain `request(n)` and `cancel()` in Reactive Streams.
2. Distinguish demand-compliant cold sources from hot/external sources that are hard to throttle.
3. Use `StepVerifier` to control demand and simulate a slow consumer.
4. Use `TestPublisher` to verify request propagation and pipeline behavior.
5. Test bounded buffers, overflow, drop, and latest-value policies.
6. Distinguish `limitRate`, `publishOn(prefetch)`, `flatMap(concurrency)`, and `onBackpressure...`.
7. Design adapters for external callback/event sources.
8. Evaluate queues, payload size, concurrency, cancellation, and memory pressure.
9. Test Spring WebFlux streaming endpoints with `WebTestClient`.
10. Build a Java 17+ Spring Boot 3.3.5 project with Reactor tests runnable via Maven.

## 2. Backpressure in Reactive Streams

Reactive Streams has four core roles:

- `Publisher<T>`: emits data.
- `Subscriber<T>`: receives data.
- `Subscription`: connects the two sides, allowing more elements to be requested or cancellation.
- `Processor<T, R>`: both receives and emits, typically represented in Reactor by operators.

Upon subscribing, the publisher calls `onSubscribe(subscription)`. The subscriber can request a number of elements:

```java
subscription.request(1);
```

When more data is needed, the subscriber calls `request(n)` again. When no longer interested, the subscriber calls:

```java
subscription.cancel();
```

Model:

```text
Subscriber                         Publisher
    |                                  |
    |<----------- onSubscribe ---------|
    |                                  |
    |------------- request(2) -------->|
    |<-------------- onNext(A) --------|
    |<-------------- onNext(B) --------|
    |                                  |
    |------------- request(1) -------->|
    |<-------------- onNext(C) --------|
    |                                  |
    |------------- cancel() ---------->|
```

### 2.1. Demand Is the Permitted Element Count

If a subscriber has requested 2 elements, a Reactive Streams-compliant publisher must not arbitrarily emit a 3rd element before receiving additional demand.

Backpressure is not a command to "run slower by 100 ms." It is an item-count demand protocol. A publisher can emit rapidly when demand is large, and must throttle when demand is low.

### 2.2. Do Not Request Unbounded in Every Situation

A subscriber may call:

```java
subscription.request(Long.MAX_VALUE);
```

That signals very large demand. When an operator requests unbounded demand from upstream and then buffers/drops on its own side, upstream no longer receives rate-limiting signals from downstream. Therefore, you must understand what policy each operator applies.

### 2.3. Cancellation Signals the End of Interest

When an HTTP client closes the connection or a subscriber cancels, cancellation should propagate upstream to stop work where possible.

However, cancel does not guarantee that a side effect already started will roll back. If a service has already sent a command to a database or external system, the application must define its own transaction and cancellation semantics.

## 3. Producers and Consumers Have Different Characteristics

### 3.1. Cold Publishers Can Honor Demand

Example:

```java
Flux<Integer> source = Flux.range(1, 5);
```

Each subscriber creates its own subscription. The source can emit according to the subscriber's demand.

Common cold sources:

- `Flux.range(...)`
- `Flux.fromIterable(...)`
- `Mono.fromCallable(...)`
- Certain reactive database/client publishers.
- Publishers created with `defer(...)`.

With a demand-compliant source, a slow subscriber can request one item at a time and upstream paces accordingly.

### 3.2. Hot or External Sources May Not Stop

Examples:

- Device SDK callbacks.
- Listeners from legacy libraries.
- External event buses.
- Message broker consumers already configured with their own pull/push model.
- Telemetry sources emitting on a fixed interval.
- `Flux.create` bridging a callback API.

The source may keep emitting even when downstream is not ready. You must then decide whether to retain data, discard data, keep only the latest value, or signal an overload error.

### 3.3. "Fast Producer" Does Not Mean Only High Item Count

Actual load depends on all of:

- Item rate per second.
- Average size of each payload.
- Number of concurrent subscribers.
- Processing duration per item.
- Number of active sub-tasks.
- Intermediate queues and prefetch.
- Retry rate and downstream wait time.

A stream of 1,000 items/second with 1 KB payloads has a different memory profile from 1,000 items/second with 2 MB payloads.

## 4. Using `StepVerifier` to Simulate a Slow Subscriber

`StepVerifier` from `reactor-test` lets you control subscriber demand inside tests.

Example requesting one element at a time:

```java
StepVerifier.create(Flux.range(1, 3), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(1)
        .expectNext(2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
```

The `0` argument is the initial demand. The subscriber requests nothing until `thenRequest(1)` is called.

The test proves:

1. The publisher does not need to emit all data immediately.
2. The subscriber can raise demand step by step.
3. Elements are emitted in order when the source honors demand.
4. The publisher completes after the final element.

### 4.1. Verifying No Data Is Emitted Before Requesting

```java
StepVerifier.create(Flux.range(1, 3), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify();
```

The test cancels after the first element. If the source has side effects or resources, add cleanup/cancellation checks at the service layer.

### 4.2. `initialRequest(0)` Is Better Than `Thread.sleep`

There is no need to use `Thread.sleep` to artificially slow down a consumer. `StepVerifier` provides deterministic demand control with minimal dependence on machine speed or test runner timing.

`thenAwait(Duration)` is useful when testing clocks/delays, yet it does not replace explicit request control. For time-independent pipelines, prefer explicit demand.

## 5. Using `TestPublisher` to Control the Producer

`TestPublisher<T>` lets tests emit data on demand and inspect subscriptions/demand.

```java
TestPublisher<Integer> source = TestPublisher.create();
```

A test verifying the source has not yet received a request:

```java
StepVerifier.create(source.flux(), 0)
        .then(() -> source.assertNoRequest())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next(10))
        .expectNext(10)
        .thenCancel()
        .verify();
```

Meaning:

- Initially the subscriber requests nothing.
- The test asserts the source has not been requested for data.
- After `thenRequest(1)`, the source receives demand.
- The test explicitly emits element `10`.
- The subscriber receives exactly one element and then cancels.

### 5.1. Useful Assertions

| API | Purpose |
|---|---|
| `assertNoRequest()` | Verifies no upstream demand yet |
| `assertWasRequested()` | Verifies the source was requested |
| `assertMinRequested(n)` | Verifies demand is at least `n` |
| `assertMaxRequested(n)` | Verifies demand does not exceed `n` |
| `assertSubscribers(n)` | Checks subscriber count |
| `assertCancelled()` | Verifies subscription was canceled |
| `assertNotCancelled()` | Verifies not canceled yet |

Use demand assertions to verify whether an operator propagates requests upstream. Avoid asserting a fixed internal prefetch number if your code does not own that contract; prefetch details can change across versions/operators.

### 5.2. Demand-Compliant and Non-Compliant `TestPublisher`

`TestPublisher.create()` creates a test publisher that follows the Reactive Streams contract.

When you need to simulate a source that deliberately emits beyond demand, Reactor Test can create a non-compliant publisher:

```java
TestPublisher<Integer> brokenSource =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW);
```

Use the non-compliant mode only to test adapters or code handling external sources that violate demand. Do not turn a non-compliant test publisher into a standard application design example.

## 6. Choosing a Policy When the Producer Outpaces the Consumer

No single strategy fits every kind of data.

| Policy | Behavior | Best Suited For |
|---|---|---|
| Propagate backpressure | Asks upstream to slow emissions | Sources that can throttle |
| Buffer | Retains elements waiting for consumer | Short bursts where every event must be kept |
| Bounded buffer + error | Retains up to N items, errors on overload | Silent data loss is unacceptable |
| Drop | Discards items when there is no demand | Telemetry or droppable data |
| Latest | Keeps only the newest value | Snapshot state, dashboards |
| Limit rate/demand | Splits upstream requests into batches | Demand-compliant sources |
| Bounded concurrency | Caps concurrently running tasks | Slow downstream I/O |
| Durable queue | Persists data to a durable system | Long bursts requiring recoverability |

Before choosing an operator, answer:

1. Is data loss permitted?
2. If the buffer fills up, should it error, drop oldest, or drop newest?
3. Can the source pause/resume?
4. Can data be persisted to a durable broker/database?
5. How large are payloads?
6. Should one slow subscriber slow down all other subscribers?

## 7. `onBackpressureBuffer`: Retaining Elements When Downstream Is Not Ready

`onBackpressureBuffer()` stores elements when downstream has no demand.

```java
Flux<Integer> buffered = source.onBackpressureBuffer();
```

The unbounded form can retain huge numbers of elements if the producer stays faster than the consumer. Under uncontrolled load, the queue can grow until memory runs out.

### 7.1. Bounded Buffer

```java
Flux<Integer> buffered = source.onBackpressureBuffer(256);
```

Caps queued elements. When capacity is exceeded, Reactor emits an overflow error under this overload.

A bounded buffer establishes a clear memory limit, but you need a plan when the queue fills:

- Return an error to signal overload.
- Retry at a layer that can retry safely.
- Stop/pause the source if a pause API exists.
- Offload to a durable queue.
- Use drop/latest if business rules allow data loss.

### 7.2. Choosing Which Element Is Dropped When the Buffer Is Full

Reactor provides `BufferOverflowStrategy` to define overflow handling in the corresponding overload:

```java
Flux<Integer> dropOldest = source.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.DROP_OLDEST);

Flux<Integer> dropLatest = source.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.DROP_LATEST);
```

- `DROP_OLDEST`: discards the oldest item in the buffer to admit the new item.
- `DROP_LATEST`: discards the newly arriving item when the buffer is full.
- `ERROR`: signals overflow.

Verify your data semantics before choosing. For latest state, drop-oldest may make sense. For financial or audit events, dropping is likely unacceptable.

### 7.3. A Buffer Is Not Infinite Capacity

If a producer continuously runs twice as fast as a consumer, the queue will climb until full. A buffer only absorbs bursts for a window of time; it does not solve a sustained rate mismatch.

A buffer with a capacity of 1,000 items does not mean the system handles infinite load. When the queue fills, the system must have an overflow policy or source throttling.

### 7.4. Backpressure Buffer Operators Change Upstream Demand

`onBackpressure...` operators must receive upstream signals to enforce their policies, often requesting high (unbounded) upstream demand and managing elements locally. Therefore, do not sprinkle them everywhere without understanding their impact upstream.

## 8. `onBackpressureDrop`: Discarding Elements When There Is No Demand

```java
Flux<Integer> dropped = source.onBackpressureDrop();
```

You can supply a callback invoked when an element is dropped:

```java
Flux<Integer> dropped = source.onBackpressureDrop(
        value -> metrics.incrementDropped(value));
```

`metrics.incrementDropped` is an illustrative application API. Do not log every dropped item under high load because logging can become a new bottleneck; prefer counters and sampling.

Use drop when:

- Data is telemetry that can tolerate loss.
- Intermediate events are non-critical.
- The consumer only needs subsequent samples.
- The system has explicit loss-acceptance rules.

Do not use drop for events requiring guaranteed processing, such as transactions, audits, or non-reproducible state-update commands.

### 8.1. Testing Drop

When the subscriber has not requested, items emitted into the operator can be dropped. Tests should verify both the callback and the elements retained once demand arrives.

```java
List<Integer> dropped = new ArrayList<>();
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(
                source.flux().onBackpressureDrop(dropped::add),
                0)
        .then(() -> source.next(1, 2))
        .then(() -> assertEquals(List.of(1, 2), dropped))
        .thenRequest(1)
        .then(() -> source.next(3))
        .expectNext(3)
        .thenCancel()
        .verify();
```

When the source emits `1` and `2` while downstream has no demand, the callback records two dropped items. After requesting one element, `3` is emitted and received.

## 9. `onBackpressureLatest`: Keeping Only the Most Recent Value

```java
Flux<Integer> latest = source.onBackpressureLatest();
```

If downstream is slow, the operator keeps the most recent value instead of storing the entire backlog of waiting elements.

Example:

```text
Producer:  1  2  3  4  5  6
Consumer:              receives 6
```

This is a useful strategy for:

- Current temperature.
- Device status.
- Progress values.
- Dashboard snapshots.
- Current position of an object.

It is unsuitable when every individual event carries distinct meaning and must be processed.

### 9.1. Testing Latest

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(
                source.flux().onBackpressureLatest(),
                0)
        .then(() -> source.next(1, 2, 3))
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
```

Downstream has no demand while the producer emits three values. Once demand appears, the subscriber receives the last value.

### 9.2. Latest Is Not Debounce

`onBackpressureLatest()` retains the newest value when downstream lacks demand. It does not wait for a quiet period before emitting like `debounce(Duration)`.

- `latest`: policy when downstream has no demand.
- `debounce`: time-based policy that emits only after upstream produces no new items for an interval.

Choose based on the reason throttling is needed.

## 10. `onBackpressureError`: Failing Immediately on Overload

```java
Flux<Integer> strict = source.onBackpressureError();
```

When the source emits while downstream has no demand, the operator signals an overflow error instead of silently buffering or dropping data.

Use when:

- Data loss is disallowed.
- Queues must not grow.
- The caller can handle explicit overload errors.
- Higher layers implement retry/backoff or request rejection.

An overflow error does not automatically solve load problems. If the caller retries immediately without backoff, it can worsen the overload.

## 11. `limitRate`: Shaping Upstream Demand

`limitRate(highTide)` splits downstream demand into smaller batches when requesting from upstream.

```java
Flux<Integer> limited = source.limitRate(32);
```

You can specify both high-tide and low-tide:

```java
Flux<Integer> limited = source.limitRate(64, 48);
```

- High-tide represents the demand batch size.
- Low-tide controls the replenishment threshold before requesting more.

`limitRate` prevents an enormous request from propagating straight upstream and allows batch-based pacing.

### 11.1. `limitRate` Is Not Elements Per Second

Do not interpret:

```java
.limitRate(10)
```

as "emit only 10 items/second." It regulates requests by demand, not as a temporal rate limiter.

If time-based limiting is needed, use a dedicated rate-limiting design or an appropriate time operator. `limitRate` also does not replace bounded queues for unpausable hot sources.

### 11.2. Testing Demand Shaping

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().limitRate(2), 0)
        .then(() -> source.assertNoRequest())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next(7))
        .expectNext(7)
        .thenCancel()
        .verify();
```

The test verifies that with no downstream demand, the source has not been requested; once demand arrives, upstream receives a request. It does not rely on a hardcoded internal prefetch number outside the application's contract.

## 12. `publishOn(prefetch)`: Async Boundary and Queue

`publishOn` transfers downstream processing onto a scheduler and uses prefetch to request elements ahead from upstream.

```java
Flux<Result> results = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::cpuWork);
```

Prefetch controls how many elements are requested ahead at the async boundary. A large prefetch can raise throughput when downstream catches up after brief pauses, yet also raises how many items can sit in the queue.

### 12.1. `publishOn` Differs from `subscribeOn`

- `publishOn` affects where operators after it process signals.
- `subscribeOn` affects where upstream subscription/requests start.
- Neither turns a blocking operation into non-blocking I/O.

Using `publishOn(Schedulers.parallel())` for a long blocking call can tie up scheduler threads. Blocking I/O must be isolated on an appropriate scheduler, typically `boundedElastic`, or replaced with a reactive client.

### 12.2. Prefetch Is Not Total Application Capacity

A pipeline can have multiple async boundaries, `flatMap` inner queues, buffering operators, and source queues. Total queued data can far exceed a single prefetch value.

Evaluate the whole pipeline, not just one `publishOn` parameter.

## 13. Bounding Concurrent Operations with `flatMap`

A fast producer can spawn many concurrent I/O operations:

```java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8);
```

The concurrency parameter limits how many inner publishers are subscribed concurrently.

You can also tune per-inner-publisher prefetch:

```java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8,
        16);
```

This helps when downstream is slow by preventing thousands of sub-requests from running simultaneously and retaining responses in memory.

### 13.1. `concatMap` When Order Matters

```java
Flux<Result> results = ids.concatMap(
        id -> remoteClient.fetch(id));
```

`concatMap` processes inner publishers sequentially, waiting for the current inner to complete before moving to the next item. Concurrency is lower, yet ordering stays predictable.

### 13.2. Choosing Concurrency Based on Downstream Capacity

There is no single right concurrency number for every application. Consider:

- HTTP/database client connection pools.
- External service request limits.
- Average and p95/p99 response times.
- Payload size.
- Concurrent requests per instance.
- Number of running instances.
- Retries and timeouts.

If each instance allows concurrency 100 and there are 20 instances, downstream can receive up to 2,000 concurrent operations. Calculate system-wide.

## 14. Bridging External Callback Sources with `Flux.create`

A callback source unaware of Reactive Streams can be adapted into a `Flux` using `Flux.create`.

Illustrative adapter example:

```java
Flux<Event> events = Flux.create(sink -> {
    Listener listener = event -> sink.next(event);

    externalSource.register(listener);

    sink.onDispose(() ->
            externalSource.unregister(listener));
}, FluxSink.OverflowStrategy.ERROR);
```

`Listener`, `externalSource.register`, and `unregister` are hypothetical external SDK APIs. The snippet illustrates adapter lifecycle: registering the listener on subscribe and unregistering it on cancel/terminate.

### 14.1. `Flux.create` Overflow Strategies

| Strategy | Meaning |
|---|---|
| `BUFFER` | Buffers elements; risks unbounded growth |
| `DROP` | Drops elements when there is no demand |
| `LATEST` | Keeps the latest element |
| `ERROR` | Signals an error when unable to emit per demand |
| `IGNORE` | Ignores demand throttling; easily overwhelms downstream |

Do not pick `BUFFER` merely because it makes tests pass. With infinite producers, an unbounded queue can lead to `OutOfMemoryError`.

### 14.2. Use `Flux.push` for Single-Threaded Sources

`Flux.push` fits callbacks emitting signals from a single-threaded producer. `Flux.create` supports multi-threaded producers and coordinates signals across threads. Choose the API matching the source's threading model.

If callbacks can fire from multiple threads, verify the adapter's contract and ensure listener registration/unregistration follows lifecycle rules. Do not retain listeners or resources after cancellation.

## 15. `buffer(...)` Differs from `onBackpressureBuffer(...)`

The two APIs have similar names yet serve different goals.

| API | Purpose |
|---|---|
| `buffer(n)` | Groups N elements into a `List<T>` and emits the list |
| `bufferTimeout(n, duration)` | Groups by size or time |
| `onBackpressureBuffer()` | Retains individual items when downstream lacks demand |
| `onBackpressureBuffer(maxSize)` | Retains up to N waiting items and signals overflow when full |

Batching example:

```java
Flux<List<Integer>> batches = Flux.range(1, 10)
        .buffer(3);
```

Output:

```text
[1, 2, 3]
[4, 5, 6]
[7, 8, 9]
[10]
```

`buffer(3)` changes the data shape to `Flux<List<Integer>>`. `onBackpressureBuffer(3)` still emits individual `Integer` items, queuing only when downstream is slow.

Do not use `buffer(n)` as a general substitute for backpressure.

## 16. WebFlux Streaming: Slow Client and Fast Server

A WebFlux controller can return `Flux<T>` to stream data. With HTTP streaming, connector and network write demand can propagate upstream so a reactive source throttles.

NDJSON example:

```java
@RestController
public class StreamController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

`Flux.range` is a cold source capable of honoring demand. WebFlux does not need to collect the whole result into a `List` before sending the response.

### 16.1. Server-Sent Events with a Paced Source

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Long>> events() {
    return Flux.interval(Duration.ofMillis(250))
            .map(value -> ServerSentEvent.builder(value)
                    .id(Long.toString(value))
                    .event("tick")
                    .build())
            .onBackpressureLatest();
}
```

This illustrates a periodic status stream. If the client is slow, the latest policy retains the newest value; intermediate ticks can be lost. Use only when semantics allow it.

If every event is a transaction or audit record, do not pick latest/drop. Use durable delivery, bounded queues, and proper acknowledgements.

### 16.2. Disconnecting Must Stop Work

When the client disconnects, the response subscription can be canceled. Sources must clean up resources inside `doFinally`, `usingWhen`, or equivalent lifecycle hooks.

Do not launch a detached infinite publisher via `subscribe()` inside a controller. Doing so can keep the source running after the HTTP client has left.

## 17. Estimating Memory and Bounding Queues

A rough queue estimate:

```text
Approximate memory
  ≈ queued items
    × average payload size
    + object/queue/reference overhead
```

For example, 10,000 queued items with a 16 KB average payload already equal roughly 160 MB of raw payload data, before counting object headers, wrappers, buffer copies, queue nodes, and other heap allocations.

Across multiple subscribers:

```text
Total queue memory
  ≈ total capacity across subscribers
    × average payload size
    + overhead
```

This is only an estimate; payloads may be shared or copied depending on operators and connectors.

### 17.1. Size Capacity Based on Burst Budget

If a producer emits 2,000 events/s and the consumer processes 1,500 events/s, the queue grows by roughly 500 events/s during the mismatch. A 5,000-item buffer only absorbs around 10 seconds at that imbalance.

If bursts last longer, slow down the producer, scale the consumer, drop per policy, or switch to a durable queue.

### 17.2. Bound Both Item Count and Size

A 100-item queue may be tiny at 100 bytes per item, yet huge at 20 MB per item. Bound:

- Item count.
- Payload bytes.
- Number of streams/subscribers.
- Concurrency.
- Queue wait duration.
- Retry count.

## 18. Runnable Java 17+ Project: Testing Slow Consumers and Fast Producers

The project uses:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux.
- Reactor Core managed by the Spring Boot BOM.
- `reactor-test` and JUnit 5.
- `WebTestClient` to test the streaming endpoint.

The test suite demonstrates:

1. Subscriber requesting one item at a time.
2. TestPublisher receiving no request before demand.
3. Bounded buffer retaining data for a slow consumer.
4. Bounded buffer emitting overflow when exceeding capacity.
5. Drop policy recording discarded items.
6. Latest policy emitting only the newest value.
7. `limitRate` propagating demand upstream.
8. WebFlux returning a finite NDJSON stream.

### 18.1. Project Structure

```text
webflux-backpressure-tests/
├── pom.xml
└── src/
    ├── main/java/edu/demo/backpressure/
    │   ├── BackpressureApplication.java
    │   ├── BackpressurePolicy.java
    │   └── StreamController.java
    └── test/java/edu/demo/backpressure/
        ├── BackpressurePolicyTests.java
        └── StreamControllerTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-backpressure-tests</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 18.3. `BackpressureApplication.java`

```java
package edu.demo.backpressure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}
```

### 18.4. `BackpressurePolicy.java`

```java
package edu.demo.backpressure;

import java.util.function.Consumer;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

@Component
public class BackpressurePolicy {

    public Flux<Integer> buffer(
            Flux<Integer> source,
            int capacity) {

        if (capacity <= 0) {
            throw new IllegalArgumentException(
                    "capacity must be positive");
        }

        return source.onBackpressureBuffer(capacity);
    }

    public Flux<Integer> latest(Flux<Integer> source) {
        return source.onBackpressureLatest();
    }

    public Flux<Integer> drop(
            Flux<Integer> source,
            Consumer<? super Integer> dropped) {

        return source.onBackpressureDrop(dropped);
    }

    public Flux<Integer> limit(
            Flux<Integer> source,
            int highTide) {

        if (highTide <= 0) {
            throw new IllegalArgumentException(
                    "highTide must be positive");
        }

        return source.limitRate(highTide);
    }
}
```

The policy class centralizes strategies for isolated testing. In real systems, do not accept arbitrary capacity from client requests; configure via application properties or limits managed by the service owner.

### 18.5. `StreamController.java`

```java
package edu.demo.backpressure;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

The endpoint returns `Flux` directly. `Flux.range` can pace by demand; the controller does not call `collectList()` or `block()`.

### 18.6. `BackpressurePolicyTests.java`

```java
package edu.demo.backpressure;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BackpressurePolicyTests {

    private final BackpressurePolicy policy =
            new BackpressurePolicy();

    @Test
    void subscriberRequestsOneItemAtATime() {
        StepVerifier.create(Flux.range(1, 3), 0)
                .thenRequest(1)
                .expectNext(1)
                .thenRequest(1)
                .expectNext(2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void compliantSourceWaitsForDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
                .then(() -> source.assertNoRequest())
                .thenRequest(1)
                .then(() -> source.assertWasRequested())
                .then(() -> source.next(10))
                .expectNext(10)
                .thenCancel()
                .verify();
    }

    @Test
    void boundedBufferQueuesWhileConsumerHasNoDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.buffer(source.flux(), 2),
                        0)
                .then(() -> source.next(1, 2))
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();
    }

    @Test
    void boundedBufferErrorsWhenCapacityIsExceeded() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.buffer(source.flux(), 2),
                        0)
                .then(() -> source.next(1, 2, 3))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void dropPolicyReportsDiscardedItems() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> dropped = new ArrayList<>();

        StepVerifier.create(
                        policy.drop(source.flux(), dropped::add),
                        0)
                .then(() -> source.next(1, 2))
                .then(() -> assertEquals(
                        List.of(1, 2),
                        dropped))
                .thenRequest(1)
                .then(() -> source.next(3))
                .expectNext(3)
                .thenCancel()
                .verify();
    }

    @Test
    void latestPolicyKeepsOnlyNewestPendingItem() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.latest(source.flux()),
                        0)
                .then(() -> source.next(1, 2, 3))
                .thenRequest(1)
                .expectNext(3)
                .thenCancel()
                .verify();
    }

    @Test
    void limitRatePropagatesDemandToSource() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.limit(source.flux(), 2),
                        0)
                .then(() -> source.assertNoRequest())
                .thenRequest(1)
                .then(() -> source.assertWasRequested())
                .then(() -> source.next(7))
                .expectNext(7)
                .thenCancel()
                .verify();
    }
}
```

The bounded buffer test emits overflow when a third item arrives while the consumer has not requested and capacity is 2. The drop/latest tests deliberately withhold requests when the producer emits to verify operator policies.

### 18.7. `StreamControllerTests.java`

```java
package edu.demo.backpressure;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void numbersEndpointStreamsNdjson() {
        Flux<Integer> body = client.get()
                .uri("/numbers")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Integer.class)
                .getResponseBody();

        assertNotNull(body);

        StepVerifier.create(body)
                .expectNext(1, 2, 3)
                .verifyComplete();
    }

    @Test
    void streamCanBeCancelledBySubscriber() {
        Flux<Integer> body = client.get()
                .uri("/numbers")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Integer.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNext(1)
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
```

`WebTestClient` tests the HTTP endpoint and response body publisher. These tests confirm the streaming response serializes as NDJSON and subscribers can cancel. Detailed demand tests remain in `StepVerifier`/`TestPublisher`, where requests can be controlled precisely.

### 18.8. Running Maven

In the directory containing `pom.xml`:

```bash
mvn test
```

Expected output on success:

```text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
```

In total: 7 unit tests for policies/demand and 2 integration tests for HTTP streaming. This is the expected output; run Maven in an environment with JDK 17 and dependency access to confirm in practice.

## 19. Overload and Load Testing Beyond StepVerifier

`StepVerifier` verifies publisher semantics deterministically. It does not replace multi-client concurrent load testing.

When load testing is needed:

1. Create a producer with realistic emission rates and payload sizes.
2. Create a consumer with latency representative of the real downstream.
3. Run multiple concurrent subscriptions.
4. Track queue capacity, drop count, overflow count, and active tasks.
5. Step up the producer rate incrementally to find where queues start growing continuously.
6. Slow down the consumer to verify backpressure/overflow policies engage.
7. Disconnect clients mid-stream to verify cancellation and cleanup.
8. Run long enough to observe heap, GC, and connection pools.

### 19.1. Metrics to Monitor

- Items received/emitted per second.
- Dropped item count.
- Overflow error count.
- Queue depth and time spent waiting in queues.
- Active `flatMap` task count.
- Request latency p50/p95/p99.
- Heap usage and GC pauses.
- Canceled subscription count.
- Active HTTP connections and pending network writes.
- Downstream error/retry rate.

There is no need to log every item. Use Micrometer counters, timers, and gauges with controlled tag cardinality. Do not use user IDs or payloads as metric tags.

### 19.2. Interpreting Load Test Results

| Observation | Likely Cause | Investigation Direction |
|---|---|---|
| Queue grows steadily over time | Consumer cannot keep up with producer | Scale/throttle producer/durable queue |
| Heap grows followed by frequent GC | Queues or payloads retained too long | Bound capacity, payload size, lifecycle |
| Drops rise while latency stays flat | Drop policy is absorbing overload | Confirm whether loss is acceptable |
| Overflows spike rapidly | Capacity too small or burst exceeds budget | Raise carefully, throttle, or reject |
| In-flight requests rise | `flatMap` concurrency too high or slow downstream | Limit concurrency and timeouts |
| Cancel does not stop upstream | Adapter detached subscription or lacks cleanup | Fix lifecycle/`onDispose` |
| Latency rises despite small queues | CPU, lock, network, or database bottleneck | Profile and trace downstream |

## 20. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using unbounded `onBackpressureBuffer()` on an infinite source | Queue grows until heap exhaustion | Bounded buffer and overflow policy |
| Assuming buffers solve sustained rate mismatches | Latency grows without bound | Throttle producer or scale consumer |
| Dropping transaction/audit events | Business data loss | Durable queue and acknowledgements |
| Using latest for events needing full ordering | Intermediate events lost | Buffer/durable log and sequence numbers |
| Thinking `limitRate(10)` means 10 items/second | Misunderstands temporal rate | Use a time-based rate limiter |
| Thinking `publishOn` slows sources infinitely | Prefetch queue is still bounded | Evaluate prefetch and hot sources |
| Unbounded `flatMap` | Too many sub-requests and memory usage | Set concurrency/prefetch |
| Using `concatMap` for high-throughput workloads | Sequential execution limits throughput | Choose bounded concurrency if order permits |
| Using `Thread.sleep` to test slow consumers | Slow and flaky tests | `StepVerifier` initial demand |
| Testing only final output | Misses demand/overflow/drop semantics | Test request propagation and queue policies |
| Using non-compliant TestPublisher everywhere | Tests fail to reflect standard publishers | Use only to simulate faulty sources |
| Failing to test overflow | Full queue causes unhandled errors | Test bounded capacity and error paths |
| Not counting dropped elements | Silent unobserved data loss | Callback/counter and alerts |
| `Flux.create` using default BUFFER for infinite callbacks | Queue can grow unbounded | Choose DROP/LATEST/ERROR or bounded adapter |
| Forgetting to unregister callbacks on cancel | Listener/resource leaks | `sink.onDispose(...)` |
| Blocking the event loop in consumers | Slows all requests on the same scheduler | Reactive I/O or boundedElastic appropriately |
| Creating unbounded per-subscriber queues | Total memory exceeds planned capacity | Sum across subscriber count |
| Bounding item count while ignoring payload bytes | One huge item still causes OOM | Bound payload size |
| Retrying overflows immediately | Amplifies overload | Backoff, jitter, admission control |
| Not testing disconnect | Upstream keeps running after client leaves | Test cancellation and resource cleanup |

## 21. Design and Testing Checklist

### Data Source

- Is the source cold or hot?
- Does it honor Reactive Streams demand?
- Can it pause/resume or pull in batches?
- Does the producer emit from multiple threads?
- Are payload size and rate bounded?

### Overload Policy

- Is data loss permitted?
- Is the buffer bounded by both item count and bytes?
- When full, will it error, drop-oldest, drop-latest, or move to a durable queue?
- Are there metrics for overflow/drop?
- Is there a timeout for items waiting too long?
- Is there admission control to reject new load?

### Consumer and Concurrency

- Is processing sequential or concurrent?
- Does `flatMap` have finite concurrency/prefetch?
- Does `publishOn` have an appropriate prefetch?
- Is there any blocking I/O on the event loop?
- Does cancellation propagate upstream?

### StepVerifier Tests

- Is `initialRequest(0)` used to control demand?
- Are `thenRequest(n)` steps tested incrementally?
- Is `TestPublisher` used to verify upstream requests?
- Are bounded buffers and overflow tested?
- Are drop/latest semantics tested?
- Is cancellation tested?
- Are timeouts/virtual time used when pipelines depend on time?

### Spring WebFlux Integration

- Does the controller return `Flux` directly when streaming is needed?
- Is `collectList()` avoided for large datasets?
- Are content type and serialization tested?
- Does client disconnect clean up upstream?
- Are queue and payload sizes bounded per deployment?

## 22. Self-Check Exercises

**Exercise 1.** Through which APIs is backpressure communicated in Reactive Streams?

**Answer:** The subscriber calls `Subscription.request(n)` to ask for more elements and `cancel()` to cancel the subscription.

**Exercise 2.** Why is `Flux.range` suitable for testing item-by-item demand?

**Answer:** It is a cold publisher capable of emitting according to demand, letting StepVerifier control requests and observe each item.

**Exercise 3.** What does `StepVerifier.create(publisher, 0)` mean?

**Answer:** StepVerifier's subscriber starts with demand 0; the test must call `thenRequest(n)` to request items.

**Exercise 4.** When should you choose `onBackpressureBuffer(maxSize)`?

**Answer:** When you need to retain a bounded burst while a slow consumer catches up and explicitly cap queued items. Once capacity fills, overflow errors must be handled.

**Exercise 5.** How do `onBackpressureDrop` and `onBackpressureLatest` differ?

**Answer:** Drop discards elements arriving when there is no demand; latest retains the newest value to emit when demand returns.

**Exercise 6.** Does `limitRate(20)` cap throughput at 20 items per second?

**Answer:** No. It shapes upstream request batches; it is not a temporal rate limiter.

**Exercise 7.** What does `publishOn(scheduler, 32)` do?

**Answer:** Creates an async boundary, shifts downstream processing onto the scheduler, and uses a prefetch of 32 to request elements ahead from upstream.

**Exercise 8.** Why does `flatMap(mapper, 8)` help control load?

**Answer:** It caps concurrently running inner publishers at 8, reducing simultaneous downstream operations.

**Exercise 9.** Why are unbounded queues dangerous?

**Answer:** When a producer stays faster than a consumer, the queue grows unbounded, raising latency/heap and risking OutOfMemoryError.

**Exercise 10.** When is `onBackpressureLatest` suitable?

**Answer:** When only the newest state matters, such as temperature or progress, and intermediate values can be skipped.

**Exercise 11.** Is `buffer(10)` equivalent to `onBackpressureBuffer(10)`?

**Answer:** No. `buffer(10)` groups 10 elements into a `List`; `onBackpressureBuffer(10)` buffers individual items waiting for demand up to a bounded capacity.

**Exercise 12.** When an HTTP client closes the connection, what should the application do?

**Answer:** Propagate cancellation upstream and release listeners/resources; do not leave a detached subscription emitting data.

## 23. Key Takeaways

- Backpressure is a demand protocol via `request(n)` and `cancel()`, not a timer.
- Cold publishers can honor demand; hot/external sources may require buffer/drop/latest or adapters.
- `StepVerifier.create(publisher, 0)` lets you simulate a subscriber not yet ready to receive data.
- `TestPublisher` verifies demand propagation and emits data under test control.
- `onBackpressureBuffer(maxSize)` absorbs finite bursts; overflow must be handled.
- `onBackpressureDrop` discards items lacking demand; `onBackpressureLatest` keeps the newest value.
- `onBackpressureError` signals overload instead of silently retaining or discarding data.
- `limitRate` shapes request batches, not items per second.
- `publishOn(prefetch)` introduces a queue/async boundary; prefetch affects queued data volume.
- `flatMap(concurrency, prefetch)` bounds sub-work; `concatMap` preserves order via sequential processing.
- `Flux.create` requires an overflow strategy and cleanup for external listeners.
- `buffer(n)` batches items, unlike `onBackpressureBuffer(n)` which holds items awaiting demand.
- Queues must be bounded by item count, payload size, subscriber count, and wait duration.
- WebFlux streaming should return `Flux` directly, test cancellation, and never block the event loop.
- Load tests must monitor queues, drops, overflows, latency, in-flight work, heap, and GC.

**Quick rule:** if the source can slow down, propagate demand upstream; if the source cannot stop, choose a bounded buffer, drop, latest, or durable queue according to data preservation requirements. Then test with subscriber demand starting at 0, increment demand step by step, and simulate overflow.

## 24. Official Documentation

- Reactive Streams Specification — **Publisher, Subscriber, Subscription and backpressure**: https://www.reactive-streams.org/
- Project Reactor 3.6 Reference — **Backpressure and request shaping**: https://projectreactor.io/docs/core/3.6.11/reference/
- Project Reactor 3.6 Reference — **Handling backpressure**: https://projectreactor.io/docs/core/3.6.11/reference/#_on_backpressure
- Reactor Core 3.6.11 Javadoc — **Flux backpressure operators**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Test 3.6.11 Javadoc — **StepVerifier**: https://projectreactor.io/docs/test/3.6.11/api/reactor/test/StepVerifier.html
- Reactor Test 3.6.11 Javadoc — **TestPublisher**: https://projectreactor.io/docs/test/3.6.11/api/reactor/test/publisher/TestPublisher.html
- Spring Framework 6.1 Reference — **Reactive WebFlux return values and streaming**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/return-types.html
- Spring Framework 6.1 Reference — **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.1/testing/webtestclient.html
- Spring Boot 3.3 — **Dependency versions**: https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html