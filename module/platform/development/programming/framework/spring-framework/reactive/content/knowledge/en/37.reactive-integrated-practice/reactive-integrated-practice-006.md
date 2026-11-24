# Practicing Callbacks, Hot Sources, and Bounded Backpressure

## 1. Problem Statement and Goals

Many external APIs do not return a Publisher. They register a callback and invoke it whenever an event occurs: device listeners, message broker clients, telemetry SDKs, file-reading libraries, or legacy adapters.

In Reactor, we often need to turn callbacks into a Flux to compose with WebFlux, R2DBC, WebClient, and other operators. However, three questions must be solved together:

1. **When is the callback registered and unregistered?** When the subscriber cancels, are the listener, timer, or connection closed?
2. **Is the source hot or cold?** Does a late subscriber receive previously emitted events? Does a new subscriber create an extra listener?
3. **What if the producer is faster than the consumer?** Do we buffer unboundedly, drop data, keep the latest item, or signal an error? Can demand be propagated back to the callback API?

Example push-style API:

~~~java
interface EventListener {
    void onEvent(String event);
    void onError(Throwable error);
    void onComplete();
}

interface LegacyEventSource {
    AutoCloseable register(EventListener listener);
}
~~~

The API invokes the callback whenever an event arrives; it does not receive Reactive Streams `Subscription.request(n)`. Converting it straight into `Flux.create` without choosing a strategy can accumulate huge buffers when the consumer is slow.

**Lesson objectives**

- Distinguish cold Publishers, hot Publishers, multicast, and replay.
- Choose `Flux.generate`, `Flux.create`, or `Flux.push` based on source characteristics.
- Bridge callbacks with `FluxSink`, register listeners, and clean up on complete/error/cancel.
- Understand `onRequest`, `requestedFromDownstream`, and the push/pull hybrid model.
- Choose bounded buffer, drop, latest, or error according to data semantics.
- Use `Sinks.Many` to build shared hot streams with multiple subscribers and handle emit results.
- Test demand using `StepVerifier`, `TestPublisher`, and JUnit.
- Build a Java 17 project using Reactor and Spring Boot 3.5.7 dependency management runnable with Maven.

## 2. Cold vs. Hot Publishers

### 2.1. Cold: Each Subscriber Gets Its Own Execution

A cold Publisher creates the data source upon subscription. Each subscriber typically receives a fresh execution:

~~~java
AtomicInteger runs = new AtomicInteger();

Flux<Integer> cold = Flux.defer(() -> {
    int run = runs.incrementAndGet();
    return Flux.just(run, run + 1);
});
~~~

Two subscribers sequentially receive two independent sequences:

~~~java
cold.subscribe(value -> System.out.println("A: " + value));
cold.subscribe(value -> System.out.println("B: " + value));
~~~

Output:

~~~text
A: 1
A: 2
B: 2
B: 3
~~~

The source is re-created on every subscription. `Flux.defer` delays creating the inner Publisher inside the supplier until subscription; this is useful when each subscriber needs its own listener or request.

Common cold examples: `Flux.fromIterable`, `Mono.fromCallable`, `Mono.defer`, `Flux.defer`, WebClient requests, and most repository queries.

### 2.2. Hot: Events Emitted Over Time

A hot source can emit independently of subscriber count. New subscribers usually receive only events emitted after they subscribe; history is not automatically replayed.

~~~text
Time       ------------------------------------------------>

Hot source:      A       B       C       D       E
Subscriber 1:        subscribe -------------------------->
Received:                    B       C       D       E

Subscriber 2:                            subscribe ----->
Received:                                        E
~~~

Typical examples are market prices, telemetry, notifications, and event buses. If subscriber 2 also needs prior events, you must choose replay or external storage.

### 2.3. Mono.just vs. defer

`Mono.just(value)` captures the value at assembly time. It replays that captured value to subsequent subscribers; the expression producing the value does not re-run.

~~~java
String snapshot = readCurrentValue();
Mono<String> captured = Mono.just(snapshot);

Mono<String> perSubscription = Mono.defer(
    () -> Mono.just(readCurrentValue())
);
~~~

If `readCurrentValue()` must run for each subscriber, use `defer`. If you want to share a single result, consider `cache()` or a sharing mechanism with an explicit lifecycle.

### 2.4. Turning Cold into Hot with share, publish, and replay

- `share()` shares an upstream subscription among active subscribers; fits live streams without history retention.
- `publish().refCount(n)` connects upstream only once the subscriber threshold is met.
- `replay(n)` retains a number of recent items for late subscribers.
- `cache()` stores emitted signals and replays them to later subscribers, potentially retaining terminal signals too; understand cache expiration/lifecycle.

Do not use `share()` as a durable event log. If subscribers need long-term replay, use a broker/log/database with appropriate retention.

## 3. Choosing a Sequence Creation API: generate, create, or push?

| API | Producer style | Emitter threads | Backpressure | Best fit |
| --- | --- | --- | --- | --- |
| Flux.generate | Synchronous, item by item | One callback invocation per item | Step-by-step pull | Stateful sequence generation |
| Flux.create | Asynchronous callbacks | Potentially multiple threads | FluxSink and OverflowStrategy | Bridging multi-threaded listener APIs |
| Flux.push | Asynchronous callbacks | Single producer thread at a time | FluxSink and OverflowStrategy | Listeners guaranteed single-threaded |
| Sinks.Many | Producer actively calls emit | Detects thread contention | Depends on sink flavor | Creating shared hot Publishers |

### 3.1. Flux.generate: Synchronous, One Item Per Turn

~~~java
Flux<Integer> numbers = Flux.generate(
    () -> 0,
    (state, sink) -> {
        sink.next(state);
        if (state == 4) {
            sink.complete();
        }
        return state + 1;
    }
);
~~~

Output:

~~~text
0
1
2
3
4
~~~

Each generator invocation emits at most one `onNext`, may complete/error, and returns the next state. Do not use `generate` to invoke asynchronous callbacks from another thread.

### 3.2. Flux.create: Multiple Items and Multiple Producer Threads

`Flux.create` provides a `FluxSink<T>` to bridge callback APIs that may emit multiple items per callback or from multiple threads.

~~~java
Flux<String> events = Flux.create(sink -> {
    EventListener listener = new EventListener() {
        @Override
        public void onEvent(String event) {
            sink.next(event);
        }

        @Override
        public void onError(Throwable error) {
            sink.error(error);
        }

        @Override
        public void onComplete() {
            sink.complete();
        }
    };

    AutoCloseable registration = source.register(listener);
    sink.onDispose(() -> closeQuietly(registration));
}, FluxSink.OverflowStrategy.ERROR);
~~~

This is an illustrative structure; `source` and `closeQuietly` must be provided by the application. The key point is that terminal callbacks must translate into `sink.error` or `sink.complete`, and listener registrations must be cleaned up.

`Flux.create` does not automatically turn synchronous code into asynchronous code. If the source lambda blocks indefinitely or performs blocking I/O, it can block the subscribing thread and cause deadlock. Bridge real callbacks rather than running infinite loops inside the lambda.

### 3.3. Flux.push: Callbacks Emitting from a Single Thread Only

`Flux.push` has an API similar to `create`, but is suitable only when a single producer thread calls `next`, `error`, and `complete`.

~~~java
Flux<String> singleThreadEvents = Flux.push(sink -> {
    SingleThreadListener listener = new SingleThreadListener() {
        @Override
        public void onEvent(String value) {
            sink.next(value);
        }

        @Override
        public void onComplete() {
            sink.complete();
        }
    };

    AutoCloseable registration = source.register(listener);
    sink.onDispose(() -> closeQuietly(registration));
}, FluxSink.OverflowStrategy.DROP);
~~~

If callbacks can run concurrently from multiple threads, choose `create` or serialize the source before emitting. Do not use `push` and then call `sink.next` concurrently.

### 3.4. FluxSink and Terminal Signals

Main methods:

- `sink.next(value)`: emits an item.
- `sink.error(error)`: terminates with an error.
- `sink.complete()`: completes normally.
- `sink.onRequest(consumer)`: receives demand notifications from downstream.
- `sink.requestedFromDownstream()`: reads remaining demand at query time.
- `sink.isCancelled()`: checks whether the subscriber has cancelled.
- `sink.onCancel(disposable)`: callback solely for cancellation.
- `sink.onDispose(disposable)`: cleanup on complete, error, or cancel.

After `complete()` or `error()`, do not keep emitting items. Late callbacks must be prevented or handled per lifecycle; never emit terminal signals multiple times.

## 4. Callback Cleanup: Registration, Cancel, and Dispose

### 4.1. Listeners Must Have a Registration Handle

Upon subscription, callback adapters typically register a listener. When the sequence ends or is cancelled, the listener must be removed:

~~~java
Flux<String> events = Flux.create(sink -> {
    Registration registration = eventBus.register(sink::next);
    sink.onDispose(registration::close);
});
~~~

If `onDispose` is omitted, the subscriber may leave while the event bus still holds the listener and retains references to the request object graph. This causes listener, background-task, or connection leaks.

### 4.2. onCancel Differs from onDispose

- `onCancel` runs only when downstream sends cancellation.
- `onDispose` runs when the sequence completes, errors, or cancels.
- If a resource needs to cancel a specific subscription on cancel and close fully on termination, you can register both; cleanup operations must be idempotent.
- If a single `close()` suffices for all three cases, `onDispose` alone is enough.

~~~java
Flux<String> events = Flux.create(sink -> {
    Registration registration = eventBus.register(sink::next);

    sink.onCancel(registration::pause);
    sink.onDispose(registration::close);
});
~~~

This snippet applies only when `pause()` and `close()` are distinct operations safe to invoke in order. Do not register both callbacks to invoke the same non-idempotent release.

### 4.3. Guarding Callbacks After Cancellation

~~~java
event -> {
    if (!sink.isCancelled()) {
        sink.next(event);
    }
}
~~~

A guard can avoid unnecessary callback invocations, but it does not replace deregistering the listener. A race still exists between checking `isCancelled()` and emitting; let the sink manage signal lifecycle and stop the source in the cleanup callback.

### 4.4. Cleanup When the Source Emits complete/error

If the callback source completes on its own, `onDispose` is still called. This ensures the listener is removed even without downstream cancellation.

Do not swallow errors during registration or resource closing. If `register` can throw an exception, let it become an error signal or map it to an appropriate business exception. Cleanup failures should be logged/recorded for observability; never attempt to send `sink.error` after the sink has completed/cancelled.

## 5. Backpressure: Consumer Requests, Producer Emits

### 5.1. Reactive Streams Demand

Subscribers call `request(n)` to declare how many items they are ready to receive. Producers should emit no more than the granted demand. `cancel()` signals that no further data is needed.

~~~text
Subscriber (pull)                     Producer (push)
       |                                    |
       | -------- request(2) -------------->|
       |<--------------- item 1 ------------|
       |<--------------- item 2 ------------|
       | -------- request(1) -------------->|
       |<--------------- item 3 ------------|
       | -------- cancel ------------------>|
~~~

Reactor is a hybrid push/pull model: downstream pulls via requests; upstream pushes items when data is available and demand permits.

### 5.2. Callback APIs Are Usually Demand-Unaware

A listener-style event bus typically just invokes `onEvent` whenever data arrives. It does not know whether downstream has requested 0, 1, or 100 items.

If the adapter merely calls `sink.next` when callbacks arrive, Reactor must apply a strategy when the consumer is slow. No strategy can simultaneously buffer infinitely, bound memory, and lose zero data if the producer cannot be throttled. Choose the policy that fits the business domain.

### 5.3. Backpressure Can Propagate Upstream If Supported by the Source

Some APIs support `request(n)`, pause/resume, `fetch(n)`, or batched polling. In that case, `FluxSink.onRequest` can forward demand to the source:

~~~java
Flux<String> bridge = Flux.create(sink -> {
    Registration registration = channel.register(sink::next);

    sink.onRequest(n -> channel.request(n));
    sink.onDispose(registration::close);
}, FluxSink.OverflowStrategy.ERROR);
~~~

`n` is the incremental demand received by the sink. The external API must interpret demand accurately, accumulate it safely, and never emit more than granted. If the source lacks pull/pause capability, `onRequest` cannot force callbacks to stop emitting.

### 5.4. requestedFromDownstream Is Only a Snapshot

~~~java
if (sink.requestedFromDownstream() > 0) {
    sink.next(event);
}
~~~

This only observes demand at the moment of checking. If callbacks arrive from multiple threads or concurrently, multiple callbacks might simultaneously observe positive demand and emit together. Avoid writing racy custom demand counters when unnecessary; prefer `FluxSink` overflow strategies or sources with true pull APIs.

## 6. Overflow Strategies in Flux.create/push

When calling `Flux.create`/`Flux.push`, you can choose `FluxSink.OverflowStrategy`:

| Strategy | When downstream cannot keep up | Consequence |
| --- | --- | --- |
| BUFFER | Buffers all items | Default; unbounded and risks OutOfMemoryError |
| DROP | Drops newly arriving items | Keeps older pending items, discards new data |
| LATEST | Keeps only the latest item | Suitable for snapshots/current state |
| ERROR | Emits IllegalStateException | Signals producer exceeded consumption capacity |
| IGNORE | Ignores demand | Can overflow downstream queues; use only with special justification |

### 6.1. BUFFER: Not Always Safe

~~~java
Flux<Event> events = Flux.create(
    sink -> registerListener(sink),
    FluxSink.OverflowStrategy.BUFFER
);
~~~

BUFFER is the default for `Flux.create`. If a producer emits 10,000 items/sec and the consumer processes only 1,000 items/sec, the backlog grows by ~9,000 items/sec. Eventually, the heap can be exhausted.

Do not pick BUFFER merely because you "do not want to lose data." If data loss is unacceptable, you must have bounds, upstream backpressure capability, a durable queue, or off-heap/external storage.

### 6.2. DROP: Keep Existing Backlog, Discard New Items Without Demand

~~~java
Flux<Integer> values = Flux.create(
    sink -> registerNumbers(sink),
    FluxSink.OverflowStrategy.DROP
);
~~~

Use for signals where new samples can be skipped while the consumer is busy or the source already has a backlog. If you need to know which items were dropped, attach `onBackpressureDrop(consumer)` downstream and record metrics/counters.

### 6.3. LATEST: Only the Most Recent State Matters

~~~java
Flux<Position> positions = Flux.create(
    sink -> registerGpsListener(sink),
    FluxSink.OverflowStrategy.LATEST
);
~~~

If users only need the latest location, keeping every old coordinate is pointless. LATEST overwrites the pending item with a newer one while downstream lacks demand. When downstream requests next, it receives the most recent snapshot.

Never use LATEST for events where every item must be processed: payments, order transitions, audit logs, or messages requiring delivery guarantees.

### 6.4. ERROR: Fail Fast When the Consumer Falls Behind

~~~java
Flux<Event> events = Flux.create(
    sink -> registerCriticalListener(sink),
    FluxSink.OverflowStrategy.ERROR
);
~~~

When demand is lacking, the sink emits an overflow error. This detects slow consumers or producers exceeding limits. Callers need error handling, retry/reconnect, and metrics; ERROR does not save events for later processing.

### 6.5. IGNORE: Not a Safe Shortcut for Speed

IGNORE bypasses backpressure. Downstream queues/operators can overflow or fail elsewhere. Consider it only when source/consumer have separate guarantees on rate and buffering; otherwise avoid it.

## 7. Backpressure Operators: Bounded Buffer, Drop, Latest, and Error

These operators are useful when the source is already a Publisher but emits faster than downstream can consume.

### 7.1. Bounded Buffer

~~~java
Flux<Event> bounded = source.onBackpressureBuffer(
    256,
    event -> metrics.incrementOverflow()
);
~~~

- At most 256 items are held while downstream has not requested enough.
- When an item exceeds capacity, the callback receives the overflowing item.
- The source is cancelled and the sequence terminates with an overflow error.
- The error may be emitted after the existing backlog is consumed.

This buffer is bounded by item count, not by bytes. If each item has a 5 MB payload, capacity 256 can still hold over 1 GB of data. Estimate item sizes and set capacity accordingly.

### 7.2. Drop and Count Discarded Items

~~~java
AtomicLong dropped = new AtomicLong();

Flux<Event> bestEffort = source.onBackpressureDrop(
    event -> dropped.incrementAndGet()
);
~~~

The operator drops items when downstream has no demand and invokes the callback for each dropped item. This is a good fit for telemetry, mouse movements, or metric samples when skipping samples does not affect business logic.

### 7.3. Latest

~~~java
Flux<Snapshot> latest = source.onBackpressureLatest();
~~~

When the consumer is slow, the operator retains only the most recent item and discards older waiting items. Suitable for dashboard snapshots, current state, or sensor readings.

### 7.4. Error When Demand Is Missing

~~~java
Flux<Event> strict = source.onBackpressureError();
~~~

If upstream emits an item when downstream has no demand, the operator emits an overflow error. Use when data loss is unacceptable and callers must handle failure explicitly.

### 7.5. Important: These Operators Request Unbounded Upstream

`onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest`, and `onBackpressureError` request unbounded demand from upstream, and handle the demand gap on the downstream side.

Therefore, they do not slow down a callback producer. They are adapters for push sources; buffer/drop/latest/error decide what happens when downstream cannot keep up.

If the source supports `request(n)` or pause/resume, propagate demand upstream with `onRequest` or an equivalent API instead of merely absorbing speed with a queue.

### 7.6. limitRate Is Not a Memory Bound

~~~java
Flux<Event> controlled = source.limitRate(64);
~~~

`limitRate` splits large requests into smaller batches when propagating upstream to a Reactive Streams-compliant source. It helps regulate request/prefetch pace. However, if the source is a demand-ignoring push callback, `limitRate` does not stop the source from emitting more data and does not replace an overflow strategy.

## 8. Hot Sources with Sinks.Many

### 8.1. Why Use Sinks?

`Sinks.Many<T>` is an API for actively emitting signals while exposing a Publisher view via `asFlux()`. It is useful when multiple parts of an application emit events into a shared stream.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

Sinks.EmitResult result = sink.tryEmitNext("order-created");
if (result.isFailure()) {
    log.warn("Could not emit event: {}", result);
}
~~~

Never ignore `EmitResult`. `OK` means the sink accepted the emission given its state at call time; it does not guarantee consumers have finished processing or persisted the event to a database.

### 8.2. Three Many Flavors

| Flavor | Subscribers | Events before subscription | Replay |
| --- | --- | --- | --- |
| unicast().onBackpressureBuffer() | At most one subscriber | Buffered waiting for the first subscriber | No replay to a second subscriber |
| multicast().onBackpressureBuffer() | Multiple subscribers | Forwards events only after subscribers register | No history replay |
| replay().limit(n) | Multiple subscribers | Retains bounded history | Late subscribers receive up to n latest items |

A multicast buffer still respects each subscriber's backpressure, yet that does not mean it retains history for late subscribers. A unicast buffer can retain items before the first subscriber arrives, but only for a single subscriber. A replay sink stores history as configured.

### 8.3. directAllOrNothing and directBestEffort

- `directAllOrNothing()`: if any subscriber lacks demand, the item is dropped for all subscribers.
- `directBestEffort()`: only slow subscribers are dropped; subscribers with demand still receive the item.

Neither flavor buffers backlogs for slow subscribers. Choose based on consistency requirements across recipients.

### 8.4. Concurrent Producers and EmitResult

By default, Sinks detect concurrent calls from multiple producers. `tryEmitNext` can return:

| EmitResult | Meaning |
| --- | --- |
| OK | Emission accepted |
| FAIL_ZERO_SUBSCRIBER | No subscribers and the sink does not buffer for that case |
| FAIL_OVERFLOW | Out of capacity |
| FAIL_NON_SERIALIZED | Concurrent producers collided, emission not serialized |
| FAIL_CANCELLED | Sink was cancelled by subscribers |
| FAIL_TERMINATED | Sink already completed/errored earlier |

When encountering `FAIL_NON_SERIALIZED`, serialize producers, use a queue/single writer, or use an appropriate emission failure handler. Do not spin-loop `tryEmitNext` endlessly. When encountering `FAIL_OVERFLOW`, decide whether to drop, retry, persist, or report an error; never assume the item was received.

### 8.5. Do Not Confuse Sinks with Durable Brokers

Sinks are in-memory. Process restarts can lose unprocessed events. If you need crash recovery replay, acknowledgements, consumer groups, retention, or delivery guarantees, use a durable message broker/log and design for idempotency.

## 9. Callback Adapter Pattern with Cleanup

A realistic adapter should expose a clear registration interface:

~~~java
package example.callback;

import java.util.function.Consumer;

public interface CallbackEventBus {

    interface Registration {
        void close();
    }

    Registration register(Consumer<String> listener);
}
~~~

Adapter:

~~~java
package example.callback;

import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public final class CallbackFluxAdapter {

    public Flux<String> events(CallbackEventBus bus) {
        return Flux.create(sink -> {
            CallbackEventBus.Registration registration =
                bus.register(event -> {
                    if (!sink.isCancelled()) {
                        sink.next(event);
                    }
                });

            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }
}
~~~

Each subscriber to this Flux registers its own listener. When the subscriber cancels, completes, or errors, `onDispose` closes the registration. The `ERROR` strategy detects when the producer pushes faster than the consumer.

If you want one callback registration shared across multiple subscribers, do not build a cold adapter like above per subscriber; design a shared source with `Sinks` or `publish`/`share` with an explicit connection/listener lifecycle.

### 9.1. When the Source Supports Demand

~~~java
return Flux.create(sink -> {
    Registration registration = bus.register(sink::next);
    sink.onRequest(bus::request);
    sink.onDispose(registration::close);
}, FluxSink.OverflowStrategy.ERROR);
~~~

This snippet assumes `bus.request(long n)` actually throttles the source. If `register` still emits events arbitrarily, `onRequest` is merely an informational callback and does not guarantee source compliance with demand.

## 10. Complete Maven Example: Java 17, Spring Boot 3.5.7, and Reactor Test

The project demonstrates cold/hot, callback registration, cancellation cleanup, bounded queues, drop/latest, `onRequest`, and sink overflow. Spring Boot parent manages dependency versions; WebFlux provides Reactor Core, while reactor-test and JUnit are used in test scope.

### 10.1. Structure

~~~text
callback-backpressure-demo/
├── pom.xml
├── src/main/java/example/callback/
│   ├── CallbackEventBus.java
│   └── CallbackFluxAdapter.java
└── src/test/java/example/callback/
    └── CallbackBackpressureTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>callback-backpressure-demo</artifactId>
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
~~~

### 10.3. CallbackEventBus.java

~~~java
package example.callback;

import java.util.function.Consumer;

public interface CallbackEventBus {

    interface Registration {
        void close();
    }

    Registration register(Consumer<String> listener);
}
~~~

### 10.4. CallbackFluxAdapter.java

~~~java
package example.callback;

import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public final class CallbackFluxAdapter {

    public Flux<String> events(CallbackEventBus bus) {
        return Flux.create(sink -> {
            CallbackEventBus.Registration registration =
                bus.register(event -> {
                    if (!sink.isCancelled()) {
                        sink.next(event);
                    }
                });

            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }
}
~~~

### 10.5. CallbackBackpressureTest.java

~~~java
package example.callback;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class CallbackBackpressureTest {

    static final class InMemoryEventBus implements CallbackEventBus {
        private final List<Consumer<String>> listeners =
            new CopyOnWriteArrayList<>();

        @Override
        public Registration register(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            listeners.forEach(listener -> listener.accept(event));
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    @Test
    void coldPublisherRunsAgainForEachSubscriber() {
        AtomicInteger runs = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() ->
            Flux.just(runs.incrementAndGet()));

        StepVerifier.create(cold)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(cold)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, runs.get());
    }

    @Test
    void callbackRegistrationIsClosedAfterCancellation() {
        InMemoryEventBus bus = new InMemoryEventBus();
        CallbackFluxAdapter adapter = new CallbackFluxAdapter();

        StepVerifier.create(adapter.events(bus))
            .then(() -> {
                assertEquals(1, bus.listenerCount());
                bus.publish("temperature:25");
            })
            .expectNext("temperature:25")
            .thenCancel()
            .verify();

        assertEquals(0, bus.listenerCount());
    }

    @Test
    void boundedBufferDrainsCapacityThenSignalsOverflow() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> overflow = new ArrayList<>();

        Flux<Integer> guarded =
            source.flux().onBackpressureBuffer(2, overflow::add);

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2, 3))
            .thenRequest(2)
            .expectNext(1, 2)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();

        assertEquals(List.of(3), overflow);
    }

    @Test
    void dropStrategyReportsValuesWithoutDemand() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> dropped = new ArrayList<>();

        Flux<Integer> guarded =
            source.flux().onBackpressureDrop(dropped::add);

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2))
            .thenRequest(1)
            .then(() -> source.next(3))
            .expectNext(3)
            .then(source::complete)
            .verifyComplete();

        assertEquals(List.of(1, 2), dropped);
    }

    @Test
    void latestKeepsOnlyNewestValueWithoutDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        Flux<Integer> guarded =
            source.flux().onBackpressureLatest();

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2, 3))
            .thenRequest(1)
            .expectNext(3)
            .then(source::complete)
            .verifyComplete();
    }

    @Test
    void sinkWithBoundedUnicastQueueReportsOverflow() {
        Sinks.Many<Integer> sink =
            Sinks.many().unicast().onBackpressureBuffer(
                new ArrayBlockingQueue<>(2));

        StepVerifier.create(sink.asFlux(), 0)
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1)))
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2)))
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.FAIL_OVERFLOW,
                    sink.tryEmitNext(3)))
            .thenRequest(2)
            .expectNext(1, 2)
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.OK,
                    sink.tryEmitComplete()))
            .verifyComplete();
    }

    @Test
    void onRequestReceivesIncrementalDemand() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> bridge = Flux.create(
            sink -> sink.onRequest(requested::addAndGet),
            FluxSink.OverflowStrategy.ERROR
        );

        StepVerifier.create(bridge, 0)
            .thenRequest(3)
            .then(() -> assertEquals(3L, requested.get()))
            .thenRequest(2)
            .then(() -> assertEquals(5L, requested.get()))
            .thenCancel()
            .verify();
    }

    @Test
    void multicastSinkDoesNotReplayPastEvents() {
        Sinks.Many<Integer> sink =
            Sinks.many().multicast().onBackpressureBuffer();

        assertEquals(
            Sinks.EmitResult.FAIL_ZERO_SUBSCRIBER,
            sink.tryEmitNext(1)
        );

        StepVerifier.create(sink.asFlux())
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2)))
            .expectNext(2)
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.OK,
                    sink.tryEmitComplete()))
            .verifyComplete();
    }

    @Test
    void replaySinkDeliversConfiguredHistoryToLateSubscriber() {
        Sinks.Many<Integer> sink =
            Sinks.many().replay().limit(1);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(10));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(20));

        StepVerifier.create(sink.asFlux())
            .expectNext(20)
            .thenCancel()
            .verify();
    }
}
~~~

### 10.6. Explanation of Each Test Result

1. coldPublisherRunsAgainForEachSubscriber: each subscriber triggers the supplier once, and the result increases from 1 to 2.
2. callbackRegistrationIsClosedAfterCancellation: the subscription registers a listener; after receiving an event and cancelling, the listener is removed from the event bus.
3. boundedBufferDrainsCapacityThenSignalsOverflow: the buffer holds 1 and 2; item 3 exceeds capacity and is observed by the callback; after the backlog is requested, the sequence emits an overflow error.
4. dropStrategyReportsValuesWithoutDemand: with initial request equal to 0, 1 and 2 are dropped; after requesting, item 3 is forwarded.
5. latestKeepsOnlyNewestValueWithoutDemand: three items arrive while demand is 0; upon requesting, the subscriber receives 3.
6. sinkWithBoundedUnicastQueueReportsOverflow: a queue of capacity 2 accepts two items; the third item is rejected with FAIL_OVERFLOW.
7. onRequestReceivesIncrementalDemand: request 3 then request 2; the callback receives a cumulative incremental demand of 5.
8. multicastSinkDoesNotReplayPastEvents: emissions before a subscriber are not retained; the subscriber receives only items emitted after registering.
9. replaySinkDeliversConfiguredHistoryToLateSubscriber: replay limit 1 means a late subscriber receives item 20, not item 10.

### 10.7. Running the Project

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn test
~~~

Expected result when all tests pass:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected outcome from the example, not an executed run log. The project needs no HTTP server, database, or Internet access; the tests exercise Reactor directly.

## 11. Backpressure by Data Type

| Data | Strategy usually considered | Why |
| --- | --- | --- |
| GPS position, dashboard snapshot | LATEST | Latest location is more valuable than stale backlog |
| Mouse movement, UI preview | DROP or LATEST | Intermediate samples can be skipped |
| Aggregatable telemetry | DROP + metrics or batching | Processing every sample is not strictly necessary |
| Audit log, payment, order event | Durable queue/broker; bounded buffer + fail | Events must never be silently lost |
| Command needing producer feedback | ERROR/acknowledgement | Producer must know consumer cannot keep up |
| Single sequential consumer | Unicast sink with bounded queue | Single subscriber with clear capacity |
| Multiple live subscribers | Multicast sink | Each subscriber receives new events |
| Late subscriber needing short history | Replay sink limit(n) | Bounded replay |

### 11.1. Bounded Buffers Need an Overflow Policy

A finite queue only answers "how many items can be held." When full, the system still must decide:

- Reject the producer and return an error.
- Drop the new item.
- Drop the oldest item.
- Retain the newest item.
- Persist the item to disk/broker.
- Pause the producer if the source API supports it.

Without a policy, a full buffer turns into random errors or silent data loss.

### 11.2. Item Size Also Matters

A limit of 1,000 items says nothing about maximum memory if payloads vary in size. Estimate:

~~~text
memory ≈ queue capacity × average retained item size + object/queue overhead
~~~

For large payloads, enforce byte limits, message size limits, small streaming chunks, or persist off-heap.

### 11.3. Wait Time and Consumption Rate

If a producer emits an average of λ items/sec, the consumer processes μ items/sec, and λ > μ, the backlog grows by roughly λ − μ items/sec. Capacity B fills in approximately:

~~~text
time to overflow ≈ B / (λ − μ)
~~~

This is only an estimate under steady rates; burst traffic, GC, schedulers, and item sizes alter reality. Use load tests to measure.

### 11.4. Do Not Buffer Unboundedly to Hide Operational Issues

Unbounded buffers only delay the moment of failure and make incidents unpredictable. If the consumer is persistently slow, throttle the producer, scale processing capacity, bound concurrency, or use a durable queue.

## 12. Threading, Concurrency, and Ordering

### 12.1. create and push

- `Flux.create`: suitable for callbacks that may emit from multiple threads; Reactor handles signal serialization.
- `Flux.push`: suitable for callbacks that emit from only one producer thread at a time.
- `Flux.generate`: synchronous, item by item; not a bridge for asynchronous event listeners.

Choosing the wrong abstraction can cause signal races or violate Reactive Streams. If a multi-threaded source requires global ordering, define ordering at the source/queue; serializing signals does not invent business order if callbacks run in parallel.

### 12.2. Sinks Are Safe for Concurrent Access Yet Can Still Fail

By default, Sinks detect concurrent emissions. If multiple threads call `tryEmitNext` simultaneously, one call may return `FAIL_NON_SERIALIZED`. You can:

- Route all emissions through a single-writer queue.
- Serialize producers using an appropriate executor/lock.
- Use `emitNext` with an `EmitFailureHandler` when contention retry policy is explicit.

Never use `Sinks.unsafe()` just to ignore concurrency errors; the unsafe API requires callers to guarantee serialization and the Reactive Streams contract themselves.

### 12.3. Callback Ordering

If an external API can invoke listeners concurrently, `onEvent` order may differ from business timestamp or sequence number order. If ordering is required, attach sequence numbers, sort/reorder in a bounded buffer, or use an ordered source.

### 12.4. Avoid Blocking Inside Callbacks

Callbacks typically run on threads managed by external libraries. Never call blocking databases, blocking file I/O, or `block()` directly inside a callback. Push events into a Flux/Sink and compose reactive work; if a blocking API must be isolated, use an appropriate scheduler and bound concurrency.

### 12.5. Callbacks Should Not Retain Mutable Payloads

If a callback emits a mutable object and the producer keeps mutating it, downstream may observe unexpected state changes. Emit immutable values/records or copy data before pushing it into the stream.

## 13. Properly Testing Backpressure and Hot Sources

### 13.1. StepVerifier with Initial Request 0

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("first")
    .thenRequest(2)
    .expectNext("second", "third")
    .verifyComplete();
~~~

Initial request 0 creates a situation where downstream has no demand yet. Then `thenRequest(n)` controls the exact timing of when the consumer receives items.

### 13.2. TestPublisher Creates Controlled Emission Sources

`TestPublisher` lets tests actively emit `next`, `complete`, or `error`. It is useful for testing backpressure operators when downstream starts at request 0 and requests later.

Do not use `Thread.sleep` to wait for events in tests. Use `then`, `thenRequest`, `thenCancel`, and verifier timeouts.

### 13.3. Verify Drop/Overflow via Observable Side Effects

With `onBackpressureDrop(consumer)` or `onBackpressureBuffer(maxSize, onOverflow)`, test that the callback receives the exact dropped/overflowed items. Checking only the terminal signal is insufficient because a strategy might run while losing the wrong items.

### 13.4. Test Cleanup After Cancel

A callback bridge test should assert that listener count drops to 0 after `thenCancel()`. This tests resource lifecycle; verifying only that the Flux emits no further items is not enough.

### 13.5. Test Hot Sources and Late Subscribers

Use `Sinks.many().multicast()` to verify late subscribers do not receive old items. Use `replay().limit(n)` to verify history is replayed up to the exact limit.

### 13.6. Test Concurrency

When a source emits from multiple threads or multiple producers call a sink together, test emission results, ordering, and serialization. Avoid tests relying solely on `Thread.sleep`; use `CountDownLatch`, controlled executors, or proper test harnesses, and clean up threads after tests.

## 14. Common Mistakes

**1 — Using default Flux.create with high-frequency callbacks.** The default `BUFFER` strategy is unbounded and can cause `OutOfMemoryError`. Pick an overflow policy or propagate demand to the source.

**2 — Using Flux.push for multi-threaded callbacks.** `push` is for a single producer thread at a time. Use `create` or serialize the source.

**3 — Forgetting to remove listeners on cancel.** The event bus retains the callback and holds references to the subscriber. Use `onDispose`/`onCancel` per lifecycle.

**4 — Removing listeners only on cancel while forgetting complete/error.** Resources remain held if the source finishes naturally. Use `onDispose` for cleanup across all terminal paths.

**5 — Using both onDispose and onCancel to call the same non-idempotent close.** Cancellation can invoke both callbacks. Make `close` idempotent or register only `onDispose`.

**6 — Thinking create automatically makes code asynchronous.** `create` only bridges callbacks; a blocking lambda can block the subscribing thread.

**7 — Thinking onRequest automatically throttles every callback API.** It only signals demand. The source must actually have request/pause/fetch support.

**8 — Using requestedFromDownstream as a synchronization lock.** The value is a snapshot; concurrent callbacks can all observe positive demand at once.

**9 — Using DROP for payments or audits.** Lost data is a business bug. Choose a durable queue or fail/ack policy.

**10 — Using LATEST for events where every item must be processed.** `LATEST` intentionally discards intermediate states.

**11 — Using unbounded replay sinks.** Late subscribers can cause memory to grow across the entire history. Choose a replay limit or time window.

**12 — Using multicast when late subscribers need replay.** Multicast only forwards new events after subscription. Choose `replay` if history is needed.

**13 — Using a unicast sink with multiple subscribers.** Unicast supports only one subscriber.

**14 — Ignoring EmitResult from tryEmitNext.** `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER`, or `FAIL_NON_SERIALIZED` can lose events. Handle each status according to policy.

**15 — Retrying FAIL_NON_SERIALIZED in an infinite loop.** Can spin CPU. Serialize producers or use a bounded failure handler.

**16 — Thinking limitRate bounds a callback source's queue.** `limitRate` only shapes upstream requests; a demand-ignoring push source can still emit too fast.

**17 — Thinking a bounded buffer is a byte limit.** Capacity is usually measured in items. Large payloads can still consume lots of memory.

**18 — Not measuring overflow/drops.** The system loses data without metrics. Record counters, rates, and alerts.

**19 — Not stopping the producer when downstream cancels.** The producer keeps generating events and consuming CPU/network with no subscriber left.

**20 — Performing blocking I/O inside callbacks.** Starves external library threads and delays event dispatch.

**21 — Emitting mutable objects and modifying them afterward.** Downstream may observe mutated data. Use immutable events or copy.

**22 — Assuming Sinks are durable message queues.** Sinks are in-memory; restarts can lose unprocessed data.

## 15. Production Checklist

### Sources and Lifecycle

1. Can the callback source emit from one thread or multiple threads?
2. Should you use `create`, `push`, or `generate`?
3. Does listener registration return a handle to unregister/close?
4. Does cleanup run on complete, error, and cancel?
5. Can a callback race with cancellation while emitting?
6. Does each subscriber create its own listener or share one listener?
7. Does a hot source need to replay history to late subscribers?

### Backpressure and Memory

8. Does the source genuinely support request/pause/resume?
9. If not, is `BUFFER`, `DROP`, `LATEST`, or `ERROR` chosen by semantics?
10. What is the item capacity and estimated byte footprint?
11. Does the overflow callback safely record metrics/logs?
12. When the buffer fills, is the producer cancelled or does it keep emitting?
13. Are queues, payloads, concurrency, and wait times bounded?
14. Are shutdown and backlog-drain policies defined?
15. Are slow consumers exercised in load tests?

### Concurrency and Reliability

16. Can Sinks receive concurrent emissions?
17. How are `FAIL_NON_SERIALIZED` and `FAIL_OVERFLOW` handled?
18. Is sequence-number ordering required?
19. Are events immutable and equipped with idempotency keys?
20. Is a durable broker needed instead of an in-memory sink?
21. Are metrics present for active subscribers, queue depth, dropped count, overflow count, and event lag?
22. Do integration tests verify listener cleanup after cancel?

## 16. Review Questions

1. How does a cold Publisher execute? **Re-creates the source for each subscriber.**
2. How does a hot Publisher treat late subscribers? **Usually receives only items emitted after subscribing, unless a replay/cache flavor is used.**
3. When does `Mono.just` capture its value? **At assembly time.**
4. Which operator defers creating a Publisher until subscription? **`defer`.**
5. What kind of source fits `Flux.generate`? **Synchronous, generating at most one item per invocation.**
6. When does `Flux.create` fit? **Bridging asynchronous callbacks, potentially from multiple producer threads.**
7. How does `Flux.push` differ from `create`? **Only one producer thread at a time.**
8. When does `onDispose` run? **Complete, error, or cancel.**
9. When does `onCancel` run? **Cancellation only.**
10. What is the default overflow strategy of `Flux.create`? **Unbounded `BUFFER`.**
11. Which strategy keeps only the newest item? **`LATEST`.**
12. Which strategy discards new items when demand is lacking? **`DROP`.**
13. Which strategy signals an error when the consumer cannot keep up? **`ERROR`.**
14. What is `onRequest` used for? **Propagating demand to the source if the source supports pull/request.**
15. Is `requestedFromDownstream` a lock? **No; it is only a demand snapshot.**
16. What does `onBackpressureBuffer(maxSize)` do when full? **Signals overflow and cancels the source; existing backlog may be drained before the error.**
17. Does `onBackpressureDrop` request unbounded upstream? **Yes; the operator drops items itself when downstream lacks demand.**
18. Does `limitRate` bound memory for a push callback? **No.**
19. Does a multicast sink replay history? **No; it emits new events to registered subscribers.**
20. How many subscribers does a unicast sink allow? **One.**
21. Which API bounds history in a replay sink? **`replay().limit(n)`.**
22. What does `FAIL_NON_SERIALIZED` mean? **Concurrent emissions were not serialized.**
23. Does `OK` from `tryEmitNext` guarantee the consumer finished processing? **No.**
24. Why does a bounded queue need an overflow policy? **When full, you still must decide whether to reject, drop, keep latest, persist, or pause the producer.**

## 17. Summary and References

- Cold Publishers create a new source per subscription; hot sources emit over time and late subscribers usually miss history unless replay is configured.
- `Flux.generate` is for synchronous item-by-item generation; `Flux.create` is for potentially multi-threaded callbacks; `Flux.push` is for a single producer thread.
- `onDispose` cleans up on complete/error/cancel; `onCancel` handles cancellation only.
- Callback sources without pull support cannot be throttled by downstream demand alone. Choose bounded buffer, drop, latest, or error.
- `Flux.create` defaults to unbounded `BUFFER`; do not use it blindly for high-frequency event sources.
- `onBackpressureBuffer(maxSize, callback)` bounds backlog by item count and signals overflow; drop/latest/error have distinct semantics.
- `onRequest` can forward demand to sources with request/pause/fetch APIs.
- `Sinks.Many` provides hot Publishers with unicast/multicast/replay; check `EmitResult` and handle concurrency/overflow.
- Tests must control demand with `StepVerifier`, use `TestPublisher`, verify listener cleanup after cancel, and distinguish multicast from replay.
- In-memory sinks do not replace durable brokers; choose strategies based on data-loss tolerance, ordering, replay, and memory requirements.

**Official references**

1. [Project Reactor 3.7 — Programmatically Creating a Sequence](https://projectreactor.io/docs/core/3.7.17/reference/coreFeatures/programmatically-creating-sequence.html): generate, create, push, overflow strategies, onRequest, onCancel, and onDispose.
2. [Project Reactor 3.7 — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html): cold/hot, defer, share, and replay.
3. [Project Reactor 3.7 — Sinks](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/coreFeatures/sinks.html): unicast, multicast, replay, concurrent producers, and EmitResult.
4. [Project Reactor 3.7 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html): onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest, onBackpressureError, and limitRate.
5. [Project Reactor — FluxSink Javadoc](https://projectreactor.io/docs/core/3.7.10/api/reactor/core/publisher/FluxSink.html): onRequest, onCancel, onDispose, and requestedFromDownstream.
6. [Project Reactor — Sinks.EmitResult Javadoc](https://projectreactor.io/docs/core/3.7.12/api/reactor/core/publisher/Sinks.EmitResult.html): OK, FAIL_OVERFLOW, FAIL_NON_SERIALIZED, FAIL_ZERO_SUBSCRIBER, FAIL_CANCELLED, and FAIL_TERMINATED.
7. [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription, request(n), cancellation, and signal rules.
8. [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): Publisher integration in WebFlux and reactive request handling.
