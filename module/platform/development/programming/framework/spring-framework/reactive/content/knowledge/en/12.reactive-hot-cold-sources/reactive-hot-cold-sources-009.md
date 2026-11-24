# Subscriber Lifecycle, Late Subscription, and Leak Risks in Reactor

## 1. The Problem to Understand

In Project Reactor, a publisher describes how data is emitted; a subscriber subscribes to receive data and drive demand. A publisher can be **cold** (each subscription typically starts a separate execution) or **hot** (events are emitted independently of a specific subscriber). This difference determines what happens when someone subscribes late, when a subscriber stops receiving data, and when an application keeps a long-lived event stream.

Three questions must be answered during design:

1. **Who owns the source lifecycle?** A request, a subscriber, an application bean, or a shared event-emitting service?
2. **When does the subscriber arrive?** If it arrives after a hot source has already emitted data, does it receive history?
3. **Who is responsible for terminating?** When a client disconnects or no receivers remain, is upstream cancelled and are resources released?

If these questions are ignored, the application can make unintended repeated API calls, miss events, keep connections or schedulers running after a request has ended, or retain an unbounded data history in the heap.

## 2. Lifecycle of a Subscriber

A Reactive Streams subscription has a general lifecycle:

```text
Publisher.subscribe(subscriber)
          |
          v
Subscriber.onSubscribe(subscription)
          |
          v
Subscriber.request(n)  ----->  Publisher can emit data per demand
          |                              |
          |                         onNext(value)
          |                              |
          |<-----------------------------+
          |
          +---- onComplete()   (completes successfully)
          |
          +---- onError(error) (terminates with error)

At any time before terminal:
Subscriber.cancel()  ----->  requests stopping data / cancelling upstream
```

The rules:

- `onSubscribe` establishes the subscription and normally occurs only once for that subscriber.
- `request(n)` signals demand to receive at most `n` more elements. Intermediate operators may reshape demand before propagating it upstream.
- `onNext` carries data; a `Mono` emits at most one value, while a `Flux` can emit multiple values.
- `onComplete` and `onError` are mutually exclusive terminal signals. After terminal, the subscription emits no more `onNext`.
- `cancel()` is a request from the subscriber. It is **not** an `onComplete` or `onError` sent down to the subscriber.

When a subscriber cancels, operators attempt to propagate cancellation upstream to stop work and release resources. Whether the physical task stops immediately depends on the source, driver, and API being called. A blocking SDK that does not support interruption may keep running even after the caller has cancelled.

### Lifecycle Observation Callbacks

| Operator | Timing |
|---|---|
| `doOnSubscribe` | When a subscriber subscribes |
| `doOnRequest` | When upstream receives demand passing that operator's position |
| `doOnNext` | When an element arrives |
| `doOnComplete` | When completing successfully |
| `doOnError` | When terminating with an error |
| `doOnCancel` | When a cancellation request is received |
| `doFinally` | After complete, error, or cancel; receives the corresponding `SignalType` |

`doFinally` is useful for observing lifecycle, yet its callback is synchronous and is not a mechanism for awaiting asynchronous cleanup. If you need to return a reactive connection, commit/rollback, or close via a publisher, use a resource-scoping mechanism like `usingWhen`.

## 3. Cold Sources: Each Subscriber Can Trigger a Separate Execution

A cold publisher typically begins producing data upon subscription. Each independent subscriber can receive the entire sequence and trigger a new execution.

```java
Flux<String> cold = Flux.defer(() ->
        Flux.just("A", "B", "C")
);

cold.subscribe(System.out::println);
cold.subscribe(System.out::println);
```

Both subscriptions will receive `A, B, C` in turn. `Flux.defer` invokes the supplier whenever a subscriber arrives, so the supplier runs twice.

A typical cold source in an application is a publisher created by `WebClient`:

```java
Mono<Customer> customer = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class);
```

Normally, each subscription to this publisher initiates a new HTTP request. If two places subscribe, two real requests may occur. This is an important point when a publisher is stored in a field and used in multiple places.

### `defer` and `just` Differ in Evaluation Timing

```java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> captured = Mono.just(counter.incrementAndGet());
Mono<Integer> perSubscription =
        Mono.defer(() -> Mono.just(counter.incrementAndGet()));
```

- `Mono.just(...)` evaluates its argument **immediately when creating the publisher**. The value is captured once and replayed to subscribers.
- `Mono.defer(...)` runs the supplier on each subscription; new subscribers can receive fresh values.

For example, `Mono.just(loadFromDatabase())` calls `loadFromDatabase()` right at assembly time, potentially causing I/O before subscription and even blocking the thread constructing the publisher. If you want to defer a synchronous call to subscription time, use `Mono.fromCallable(...)` and pick an appropriate scheduler when the operation is blocking. If you want each subscription to execute a reactive request, construct the publisher inside `defer` when the client call needs to be re-initiated.

**Note:** Not every publisher that can be subscribed to multiple times has the same semantics. Read the driver/client contract and check whether it allows multiple subscriptions or if the response body can only be consumed once.

## 4. Hot Sources: Events Exist Independently of a Subscriber

A hot publisher can emit events over time without waiting for a specific subscriber. Examples:

- A continuously updating market price or telemetry source.
- An application event bus.
- A notification stream pushed into `Sinks.Many`.
- A connected source shared across multiple requests.

A hot-source subscriber typically receives only events from the time it joins, unless the source has a replay or history-retention mechanism.

```text
Time:            t1       t2       t3       t4
Hot source:      E1 ------ E2 ------ E3 ------ E4
Subscriber A:    subscribe -------------------->
A receives:               E2       E3       E4

Subscriber B:                         subscribe
B receives:                                    E4
```

A joins before E2 so it sees E2, E3, E4. B joins near t4 so it only sees E4. If E1–E3 matter, a non-replaying hot source cannot automatically recover those events for B.

### Do Not Label Solely Based on Class Name

- `Flux.defer(...)` is usually cold because the supplier runs for each subscriber.
- `Flux.interval(...)` creates a separate emission schedule per subscription; two subscribers can have two independent cadences. To share one clock, share the publisher.
- `Mono.just(value)` captures the value at assembly time and replays the captured value; it is not equivalent to `defer`.
- A `Sinks.Many` is an active signal-emission port; the specific sink type and connection setup determine whether new subscribers see history or only future events.

What must be determined is **when data is created, when subscription happens, and the retention/replay policy**, not merely the class name.

## 5. Late Subscription: Missing History or Receiving Data?

When a subscriber arrives late, the outcome depends on the operator/sink ahead of it:

| Mechanism | What Does a Late Subscriber Receive? | Considerations |
|---|---|---|
| Cold publisher (`defer`, new request) | A new execution from the beginning | May repeat HTTP/DB side effects |
| Non-replaying hot multicast | Only events emitted after subscribing | Earlier events are missed |
| `replay(n)` / bounded replay sink | A number of most recent elements and new elements | Memory, sensitive data, history length |
| `cache(n)` on Flux | Bounded recent history and terminal signal | Runs source once, retains data for later subscribers |
| Unbounded `cache()` on Flux | Can retain all elements | Heap growth risk on long/infinite streams |
| `share()` / `publish().refCount(1)` | Joins the shared stream; no history replay | Upstream lives based on subscriber count |
| `autoConnect(n)` | Joins after the source has connected | Connection does not auto-disconnect when subscribers drop to 0 |

### Timeline Example

Suppose a hot source emits `E1`, `E2`, `E3`, and then B subscribes:

- Non-replaying multicast: B sees only `E4` onward.
- 2-element replay: B sees `E2`, `E3`, then E4...
- Cold source: B starts a new execution and may see E1, E2, E3 of that separate run.
- Cache: B receives cached values, potentially without causing another upstream call.

Do not use replay/cache to replace a durable event store if data must survive restarts, deployments, or process crashes. Cache in one JVM's memory is not durable history.

## 6. Sharing Sources with `publish`, `refCount`, `share`, and `autoConnect`

Reactor provides `ConnectableFlux` to control when a source starts emitting to multiple subscribers.

### 6.1. `publish()` and `connect()`

```java
ConnectableFlux<Long> connectable =
        Flux.interval(Duration.ofSeconds(1)).publish();

Disposable connection = connectable.connect();
```

`publish()` creates a connectable publisher. `connect()` starts upstream and returns a `Disposable` representing the connection. Subscribers subscribe to the connectable to receive signals; if you connect before subscribers join, events may already be emitted before subscribers participate.

When the application owns the connection manually, keep the `Disposable` and dispose it when no longer needed:

```java
connection.dispose();
```

Do not call `connect()` arbitrarily multiple times. Understand the connection contract and retain the handle of application-managed connections.

### 6.2. `autoConnect(n)`

```java
Flux<Long> sharedAfterTwo =
        Flux.interval(Duration.ofSeconds(1))
                .publish()
                .autoConnect(2);
```

The source only begins connecting once two subscribers arrive. `autoConnect` fits when a minimum subscriber count is the startup condition. After connecting, subscribers leaving **does not automatically disconnect upstream in a ref-count manner**. With an infinite source, it can keep running with nobody observing unless proper connection management is in place.

### 6.3. `refCount(n)` and `share()`

```java
Flux<Long> sharedWhileObserved =
        Flux.interval(Duration.ofSeconds(1))
                .publish()
                .refCount(1);
```

`refCount(1)` starts connecting when at least one subscriber exists and disconnects upstream when the subscriber count drops below the threshold. With threshold 1, the source is shared while listeners remain. This is a better fit when upstream lifecycle should be tied to active observers.

`share()` is shorthand for the common sharing/ref-count pattern:

```java
Flux<Long> shared = Flux.interval(Duration.ofSeconds(1)).share();
```

Do not rely on assuming every new subscriber receives history. `share()` is not a replay cache. Reconnection details after terminal/cancel can depend on version and source state; if reconnect behavior is an important requirement, write tests for the Reactor version in use.

### Quick Comparison

| Operator | Starts Source | When Last Subscriber Leaves | Replay |
|---|---|---|---|
| `publish().connect()` | When `connect()` is called | Not automatic; owner disposes connection | No |
| `publish().autoConnect(n)` | When n subscribers arrive | Does not ref-count down to 0 | No |
| `publish().refCount(n)` | When threshold n is reached | Cancels upstream when dropping below threshold per contract | No |
| `share()` | When the first subscriber arrives | Tied to active observing subscriber count | No |
| `replay(n).autoConnect(...)` | On connect/threshold reached | Depends on connection management | Yes, retains bounded history |

Choose the operator by the desired lifecycle, not merely line count.

## 7. `cache` and `replay`: Avoiding Unbounded History Retention

### Caching a Single Execution

```java
Mono<Product> product = fetchProduct(productId).cache();
```

With `Mono.cache()`, the terminal result is cached so later subscribers can receive it without re-invoking upstream. This can be useful for an immutable, shared result with an appropriate lifetime policy. However, if data depends on user, permissions, tenant, or changes over time, a shared cache can return wrong data or hold information too long.

With `Flux`:

```java
Flux<Event> recent = eventSource.cache(100);
```

The history-bounded overload retains the most recent elements up to the limit. Conversely, unbounded `cache()` can retain every emitted element. With infinite streams, this can lead to unbounded heap growth.

### Bounded Replay

```java
ConnectableFlux<Event> replayed =
        eventSource.replay(50);
```

`replay(50)` keeps a window of at most 50 elements for late subscribers. It can be combined with `autoConnect` or `refCount` per required lifecycle. An element-count limit is not a byte limit: 50 large objects can still occupy significant memory.

### Choosing Cache TTL and Scope

Before caching, determine:

- Does the data change? When does it expire?
- Can it be shared across users/tenants?
- Does the result contain tokens, PII, or sensitive data?
- What is the element count and size of each element?
- Is the cache held until terminal or for a TTL duration?
- On error, should the error be cached or should later subscribers be allowed to retry?

Caching is not just a performance optimization; it changes execution semantics, upstream invocation count, when data is observed, and how long data stays in memory.

## 8. Using `Sinks.Many` as a Hot Source

`Sinks.Many<T>` is an API for actively emitting data into a `Flux`. An application can hold the sink in a bean and call `tryEmitNext` when events occur.

### Common Sink Types

| Sink Type | Primary Behavior | Suitable Case |
|---|---|---|
| `many().unicast()` | Single subscriber only; can buffer before subscriber arrives per config | One consumer owns the stream |
| `many().multicast().onBackpressureBuffer()` | Multiple subscribers, coordinates demand and buffers | Broadcast with backpressure handling |
| `many().multicast().directAllOrNothing()` | If one subscriber lacks demand, emission can fail for everyone | Need synchronized emission to all receivers or error reporting |
| `many().multicast().directBestEffort()` | Emits to subscribers with demand; slow subscribers may miss emissions | Telemetry/notifications allowing event loss on slow subscribers |
| `many().replay().limit(n)` | New subscribers receive up to the n most recent events | Short-term snapshots/history |

Choosing a sink is a data-policy decision. If losing a single event is unacceptable, `directBestEffort` is unsuitable; buffering, retries, a durable broker, or event persistence is needed.

### Event Emission and Consumption Example

```java
Sinks.Many<String> sink =
        Sinks.many().multicast().directBestEffort();

Flux<String> events = sink.asFlux();

Disposable subscription = events.subscribe(
        value -> System.out.println("received=" + value),
        error -> System.err.println("error=" + error)
);

Sinks.EmitResult result = sink.tryEmitNext("order-created");

if (result.isFailure()) {
    System.err.println("event not delivered: " + result);
}

subscription.dispose();
```

This snippet imports `reactor.core.Disposable`, `reactor.core.publisher.Flux`, and `reactor.core.publisher.Sinks`. `tryEmitNext` returns `EmitResult` so the caller can handle cases where emission is not possible; never ignore the result if events matter.

Common failure reasons:

- No subscribers in a sink type requiring present subscribers.
- Subscribers without demand in a backpressure-enforcing sink.
- Full buffer.
- Concurrent emission calls not serialized per contract; may receive `FAIL_NON_SERIALIZED`.
- Sink already completed/errored or disposed.

Do not call `tryEmitNext` and assume the event definitely reached every client. Choose failure handling per business logic: controlled retry, durable queue, overload reporting, or intentional skip.

### Multiple Concurrent Producers

Safe `Sinks` detect concurrent access and report corresponding failure results. If multiple threads emit concurrently, serialize producers or use a controlled retry/serialization mechanism. Avoid `Sinks.unsafe()` unless the application strictly guarantees only one producer emits at a time.

## 9. Slow Subscribers, Backpressure, and Buffers

When a hot source emits faster than consumption speed, decide what happens to slow subscribers:

1. **Buffer**: hold events waiting for the subscriber. Must bound size and behavior when full.
2. **Drop**: discard events that cannot be delivered in time. Suits telemetry not needing completeness.
3. **Latest**: keep only the newest value. Suits current state like displayed temperature/prices.
4. **Fail**: emit an error or reject emissions when demand is unmet.
5. **Durable queue**: store off-heap (broker/database/log) if events must be redelivered after restart.

No policy is right for every system. Choose by data meaning:

- CPU metrics every 100 ms may accept dropping.
- “Order paid” notifications usually require durable storage and redelivery.
- Dashboard values may use latest.
- High-volume streams need bounds on buffers, subscriber count, and payload size.

**Backpressure does not mean infinite retention.** A subscriber not requesting data cannot force the system to retain every event forever. Buffers must be bounded or have rejection/drop policies.

## 10. Subscription Cancellation and Managing `Disposable`

Each `.subscribe(...)` call typically returns a `Disposable`. For long-lived sources, the application must retain the handle to stop at the right time:

```java
Disposable subscription = source.subscribe(
        this::handleEvent,
        this::handleError
);

// When the bean/request no longer owns the stream:
subscription.dispose();
```

Without retaining `Disposable`, the application can lose the ability to cancel the subscription manually. An interval source or hot event stream can continue emitting, holding callbacks and references to objects no longer in use.

### Multiple Subscriptions: `Disposable.Composite`

```java
Disposable.Composite subscriptions = Disposables.composite();

subscriptions.add(sourceA.subscribe(this::handleA));
subscriptions.add(sourceB.subscribe(this::handleB));

// When the component stops:
subscriptions.dispose();
```

Requires importing `reactor.core.Disposable` and `reactor.core.Disposables`. Composite groups the lifecycle of multiple subscriptions owned by the same component. Do not share one global composite across independent requests without a clear ownership design.

### `dispose()` Is Not Complete

- `dispose()` requests subscription cancellation.
- `onComplete` is the source signaling successful completion.
- `onError` is the source signaling an error.
- `doFinally` can observe `SignalType.CANCEL` when a subscriber cancels.

For an already completed/errored publisher, dispose does not emit a new terminal signal. For asynchronous sources, dispose also does not guarantee an external blocking task stops immediately if that API does not support cancellation.

## 11. Common Leak Patterns

### 11.1. Subscribing in a Controller and Returning Another Publisher

Wrong:

```java
@GetMapping("/events")
Flux<Event> events() {
    eventSource.subscribe(this::process);
    return Flux.empty();
}
```

The controller created a subscription detached from the HTTP response lifecycle, then returned `Flux.empty()`. When the client disconnects, the manual subscription is not automatically cancelled by WebFlux; it can keep running and holding resources.

Right:

```java
@GetMapping("/events")
Flux<Event> events() {
    return eventSource;
}
```

Let WebFlux own the response subscription. When the client cancels/disconnects, cancellation can propagate upstream per contract.

### 11.2. Subscribing Manually Without Keeping the Disposable

```java
source.subscribe(this::handle);
```

If this is a long-lived subscription started by a component, retain the `Disposable` and dispose it when the component stops. If you only want to transform data, return the publisher and compose operators; do not nest subscriptions.

### 11.3. `autoConnect` with an Infinite Source

```java
Flux<Long> clock = Flux.interval(Duration.ofSeconds(1))
        .publish()
        .autoConnect(1);
```

After the first subscriber, the source starts running. If all subscribers leave while upstream has not completed, `autoConnect` does not ref-count back to 0; the timer can keep running. Use `refCount` if the lifecycle must be tied to observers, or manage the connection `Disposable` explicitly.

### 11.4. Unbounded Cache/Replay

```java
Flux<Event> dangerous = eventSource.cache();
```

With long or infinite streams, cache can retain all emitted elements on the heap. Use history limits/TTL or an external store when long-term history is required.

### 11.5. Not Cancelling Sources When Requests Expire

A request fanning out to multiple upstreams can time out while work continues if a subscription was detached via manual `.subscribe()`, or if the source library does not support cancellation. Keep work within the same pipeline; configure client/driver timeouts and observe cancellations.

### 11.6. Retaining References to Subscribers or Request Contexts

A long-lived hot source holding callbacks/closures can keep services, request contexts, buffers, or sensitive data alive. Avoid placing short-lived request objects into singleton structures; store only needed data, and remove listeners/subscriptions when finished.

## 12. Spring WebFlux: Designing Broadcast Streams for HTTP

A bean can provide a shared event source:

```java
@Component
class EventHub {
    private final Sinks.Many<Event> sink =
            Sinks.many().multicast().onBackpressureBuffer(256);

    Flux<Event> events() {
        return sink.asFlux();
    }

    Sinks.EmitResult publish(Event event) {
        return sink.tryEmitNext(event);
    }
}
```

This is a structural snippet; `Event` must be defined and `EmitResult` handled at call sites. Buffer 256 is a limit by **element count**, not bytes; a full-buffer policy and overflow metrics are needed. For critical data, an in-memory sink does not replace a durable message broker.

The controller can return SSE:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Event>> events() {
    return eventHub.events()
            .map(event -> ServerSentEvent.builder(event).build());
}
```

This snippet requires `eventHub`, `MediaType`, `ServerSentEvent`, `GetMapping`, and the `Event` class. Spring manages the subscription tied to the response. When a client disconnects, upstream cancellation can reduce the subscriber count of the sink/share if the pipeline is composed properly.

### Protecting Data Across Tenants/Users

Do not share a stream filtered by a request-specific security context without tight control. If multiple users subscribe to one hot publisher, clearly define:

- Partitioning sinks by tenant/topic or enforcing permission checks per subscriber.
- Never putting tokens or personal data into a shared cache/replay.
- Ensuring new subscribers do not receive history belonging to another tenant.
- Bounding subscriber count, buffers, and emission rate per tenant.
- Defining how permissions are revoked and subscriptions disposed when sessions expire.

A `share()`-d publisher has a shared upstream subscription; do not assume each subscriber gets a separate upstream execution to automatically apply a distinct `Reactor Context`. Place authentication/authorization at the right boundary and test with multiple distinct subscribers.

## 13. Placing `doFinally` Before or After `share`?

Operator placement affects whether the callback runs per subscriber or per shared upstream subscription:

```java
Flux<Event> source = eventSource
        .doFinally(signal -> logUpstreamEnd(signal))
        .share();

Flux<Event> perSubscriberObserved = eventSource
        .share()
        .doFinally(signal -> logSubscriberEnd(signal));
```

- `doFinally` **before** `share()` observes the lifecycle of the shared upstream subscription. When the first subscriber joins, upstream is subscribed; when the shared source is cancelled/terminated, the corresponding callback runs.
- `doFinally` **after** `share()` observes the lifecycle of each downstream subscriber. Each subscriber can have its own `CANCEL`, `ON_COMPLETE`, or `ON_ERROR`.

This distinguishes “one client left the stream” from “the entire shared source stopped”. When debugging subscriber leaks, log both layers and do not count upstream callbacks as receiver counts.

## 14. Testing Late Subscription, Replay, and Cancellation

A good test controls subscription and event-emission timing without relying on `Thread.sleep`. Use `Sinks` to drive events synchronously and `StepVerifier` to verify terminal/cancel signals.

### Java 17+ Maven Project

Structure:

```text
reactor-subscriber-lifecycle/
├── pom.xml
└── src/test/java/edu/demo/SubscriberLifecycleTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-subscriber-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/test/java/edu/demo/SubscriberLifecycleTest.java`:

```java
package edu.demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriberLifecycleTest {

    @Test
    void coldDeferStartsOneExecutionPerSubscriber() {
        AtomicInteger executions = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            executions.incrementAndGet();
            return Flux.just(1, 2, 3);
        });

        StepVerifier.create(cold)
                .expectNext(1, 2, 3)
                .verifyComplete();

        StepVerifier.create(cold)
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertEquals(2, executions.get());
    }

    @Test
    void lateSubscriberToHotMulticastMissesPastEvents() {
        Sinks.Many<Integer> sink =
                Sinks.many().multicast().directBestEffort();

        List<Integer> early = new ArrayList<>();
        Disposable first = sink.asFlux().subscribe(early::add);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        first.dispose();

        List<Integer> late = new ArrayList<>();
        Disposable second = sink.asFlux().subscribe(late::add);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        second.dispose();
        sink.tryEmitComplete();

        assertEquals(List.of(1), early);
        assertEquals(List.of(2), late);
    }

    @Test
    void replaySinkGivesLateSubscriberRecentHistory() {
        Sinks.Many<Integer> replay = Sinks.many().replay().limit(2);

        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, replay.tryEmitComplete());

        StepVerifier.create(replay.asFlux())
                .expectNext(2, 3)
                .verifyComplete();
    }

    @Test
    void cacheRunsColdSourceOnceAndReplaysLastTwoValues() {
        AtomicInteger executions = new AtomicInteger();

        Flux<Integer> cached = Flux.defer(() -> {
            executions.incrementAndGet();
            return Flux.just(1, 2, 3);
        }).cache(2);

        StepVerifier.create(cached)
                .expectNext(1, 2, 3)
                .verifyComplete();

        StepVerifier.create(cached)
                .expectNext(2, 3)
                .verifyComplete();

        assertEquals(1, executions.get());
    }

    @Test
    void sharedUpstreamCancelsWhenLastSubscriberLeaves() {
        AtomicReference<SignalType> upstreamEnd = new AtomicReference<>();

        Flux<Long> shared = Flux.<Long>never()
                .doFinally(upstreamEnd::set)
                .share();

        Disposable first = shared.subscribe();
        Disposable second = shared.subscribe();

        first.dispose();
        assertEquals(null, upstreamEnd.get());

        second.dispose();
        assertEquals(SignalType.CANCEL, upstreamEnd.get());
    }

    @Test
    void subscriberCancellationIsNotCompletion() {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        StepVerifier.create(
                        Flux.<Integer>never()
                                .doFinally(finalSignal::set))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

Run in the project directory:

```bash
mvn test
```

Once dependencies are downloaded and assertions hold, **6 tests PASS**. The tests confirm:

1. `defer` executes the supplier once per subscriber.
2. A late hot subscriber does not receive previously emitted events.
3. A replay sink retains the two most recent events for late subscribers.
4. `cache(2)` executes the source only once and replays the last two elements on the subsequent subscription.
5. Shared upstream is cancelled only when the last subscriber leaves.
6. `cancel` is observed as `SignalType.CANCEL`, not completion.

The tests use synchronously emitting sinks so no `Thread.sleep` is needed. In real applications, add integration tests for connection pools, brokers, HTTP clients, and shutdown lifecycles.

## 15. Application Subscriber-Leak Prevention Checklist

Before shipping long-lived streams to production:

- Do you know who creates subscriptions and who owns each `Disposable`?
- Are subscriptions detached from HTTP requests via manual `.subscribe()`?
- When a client disconnects, does cancellation propagate upstream?
- If using `autoConnect`, who disposes the connection?
- If using `share/refCount`, what happens when the last subscriber leaves?
- Do cache/replay have element-count limits or TTLs?
- Does the hot source have policies for slow subscribers and overflow?
- Does the event sink bound subscriber count and buffers?
- Do callbacks retain requests/sessions/large objects for too long?
- Are there metrics for subscriber count, active connections, queues, cancellations, and emit failures?
- Is shutdown handled to dispose subscriptions, schedulers, connections, and sinks?
- Have late subscriptions, repeated subscriptions, cancellations, reconnections, and upstream errors been tested?

### Leak Warning Signs

- Subscriber or connection counts grow over time and do not drop after clients leave.
- Threads/timers keep running after a component has shut down.
- Heap grows with emitted event count due to unbounded replay/cache.
- Callbacks still hold references to requests, sessions, or beans no longer needed.
- A client disconnects yet downstream HTTP calls or database queries continue.
- Sink emissions frequently return `FAIL_OVERFLOW` or `FAIL_NON_SERIALIZED` while the application ignores them.
- A `Flux.never()`/`interval()` source has no clear lifecycle owner.

## 16. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking hot sources replay full history | Late subscribers miss events | Choose bounded replay/cache/durable log |
| Subscribing to a WebClient Mono twice unknowingly | Sends two HTTP requests | Use one composed subscription or TTL cache if semantics fit |
| Using `Mono.just(expensiveCall())` | Call runs immediately when creating the publisher | Use an appropriate lazy publisher (`defer`/`fromCallable`) |
| Calling `.subscribe()` in a controller | Subscription detaches from HTTP lifecycle | Return `Mono`/`Flux` to Spring |
| Discarding the `Disposable` of a long-lived subscription | Unable to stop the source under control | Store and dispose per component lifecycle |
| `autoConnect` on an infinite source without managing the connection | Source keeps running when no subscribers remain | Use refCount or manage the connection Disposable |
| Using unbounded `cache()` on an infinite Flux | Heap grows continuously | `cache(n)`, bounded replay, TTL, or durable store |
| Using `directBestEffort` for lossless events | Slow subscribers may miss events | Use buffers/durable brokers and handle overflow |
| Sharing a publisher with tenant-dependent data | Cross-user data leaks | Partition streams and check authorization at the right boundary |
| Assuming cancel always stops physical work | Blocking SDKs may still continue | Driver timeouts/cancellations, queue bounds, and monitoring |
| Using `doFinally` as async cleanup | Terminal does not await cleanup publishers | Use `usingWhen` or an appropriate lifecycle manager |
| Not checking `EmitResult` | Event loss or concurrency errors go unnoticed | Handle each emit result per policy |

## 17. Self-Check Exercises

**Exercise 1.** A `WebClient` creates a `Mono<Customer>`. Two controllers/services subscribe to that same publisher. How many HTTP requests can occur?

**Answer:** Normally two cold subscriptions create two independent HTTP requests. If sharing one result is needed, you can cache/coalesce, while checking TTL, access permissions, and whether data changes.

**Exercise 2.** A hot multicast emitted `E1`, `E2`, `E3`; subscriber B subscribes after E3. What does B receive?

**Answer:** Without replay, B only receives events emitted after subscribing. For B to see history, the source must have replay/cache or an event store.

**Exercise 3.** `publish().autoConnect(1)` is sharing a `Flux.interval`. The last subscriber disposes. Is the timer guaranteed to stop?

**Answer:** No. `autoConnect` does not ref-count down to 0; the opened connection must be managed separately. Use `refCount` if you want to stop upstream when no subscribers remain.

**Exercise 4.** Why can `Flux.cache()` cause OOM on an infinite source?

**Answer:** Unbounded cache history retains emitted elements so late subscribers can receive them. Use history limits/TTL or off-heap storage.

**Exercise 5.** Why should a controller not call `eventSource.subscribe()` and then return `Flux.empty()`?

**Answer:** The manually created subscription is not tied to the HTTP response. Client disconnection does not automatically cancel that subscription; the stream may keep holding resources.

**Exercise 6.** A sink returns `FAIL_NON_SERIALIZED`. What might that indicate?

**Answer:** Multiple producers are attempting to emit concurrently without being serialized per the sink's contract. Serialize producers or use an emit mechanism with appropriate retry/locking.

**Exercise 7.** How does placing `doFinally` before `share()` differ from placing it after `share()`?

**Answer:** Before `share()` observes the shared upstream lifecycle; after `share()` observes each downstream subscriber's lifecycle. The two layers can terminate at different times.

## 18. Key Takeaways

- **Cold** typically starts one execution per subscription; **hot** emits events independently of specific subscribers.
- **Late subscribers** receive history only if the source has replay/cache; direct multicast typically forwards only new events.
- `share/refCount` tie upstream lifecycle to subscribers; `autoConnect` connects after a threshold yet does not auto-disconnect when subscribers drop to 0.
- `cache/replay` change execution count and data-retention duration semantics; always set appropriate bounds.
- Every long-lived subscription needs **an owner and a dispose mechanism**. WebFlux controllers should return publishers so the framework manages the HTTP lifecycle.
- Shared hot streams must have tenant/security, backpressure, overflow, shutdown, and subscriber-observability policies.

When late subscriptions or suspected leaks happen, trace three milestones: **when the source starts, when subscribers attach, and who cancels the connection when no receivers remain**.

## Official References

- Project Reactor, **Hot Versus Cold**: https://projectreactor.io/docs/core/3.6.6/reference/advancedFeatures/reactor-hotCold.html
- Project Reactor, **ConnectableFlux / publish, replay, refCount, autoConnect**: https://projectreactor.io/docs/core/3.6.6/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Project Reactor, **Sinks**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/sinks.html
- Project Reactor, **Flux API** (`cache`, `share`, `publish`, `replay`, `refCount`): https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Disposable API**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/Disposable.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html