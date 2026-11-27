# Supplier<Flux<T>> with Finite and Continuous Streams

## 1. Context: How Much Data Can a Supplier Emit?

In **Spring Cloud Function**, `Supplier<T>` represents a data source: it takes no arguments when `get()` is called, yet produces a result. Replacing `T` with Project Reactor's `Flux<T>` gives us a source returning a **publisher** that emits 0, 1, or many elements over time.

~~~java
Supplier<Flux<String>> ids =
    () -> Flux.just("ORD-101", "ORD-102", "ORD-103");
~~~

Calling `ids.get()` returns a `Flux<String>`. In this example, the Flux is a *cold* source: elements are emitted only when there is a subscriber. `Supplier.get()` is not called once per ID. All three IDs belong to the same publisher.

What must be distinguished is that **the `Supplier<Flux<T>>` signature does not determine whether the stream ever ends**:

- A **finite stream** emits a bounded number of elements (or potentially finite even if unknown upfront), and then emits `onComplete`; for instance, a batch of orders to sync once.
- A **continuous stream** can emit events indefinitely until canceled, the source closes, or an error occurs; for instance, sensor metrics, heartbeats, or order status updates.

Both can use the exact same `Supplier<Flux<T>>` type. The difference lies in the **publisher source, subscription mechanism, termination signals, and how the adapter operates**.

Spring Cloud Function lets you package this logic independently of how it is invoked. `FunctionCatalog` is used for looking up and composing functions; adapters can expose the functionality over HTTP, events, or serverless. However, each adapter decides when to call `get()`, when to subscribe, how to turn each `onNext` into a message, and when to cancel the subscription.

### Expected Learning Outcomes

After this lesson, you will know how to:

1. Write `Supplier<Flux<T>>` for both a finite dataset and a continuous emission source.
2. Distinguish `get()`, `subscribe()`, `onNext`, and `onComplete`.
3. Separate **cold/hot** sources from **finite/continuous** streams—two independent pairs of concepts.
4. Choose an implementation approach when you need to emit a data batch, poll periodically, or push real-time events.
5. Evaluate lifecycle, backpressure, retries, duplicate data, and characteristics of HTTP, event binders, and serverless.
6. Test time-driven sources using `StepVerifier.withVirtualTime`.

## 2. Reviewing the Supplier and Flux Contract

### 2.1. Supplier<T> and Supplier<Flux<T>>

Java defines `Supplier<T>` with a single method:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

There are three ways to return data:

| Signature | One `get()` call returns | Suitable scenarios |
| --- | --- | --- |
| `Supplier<Order>` | One `Order` object | Supplying a single value at the moment it is called |
| `Supplier<Mono<Order>>` | A publisher with at most one `Order` per subscription | An asynchronous single result, possibly not found |
| `Supplier<Flux<Order>>` | A publisher emitting 0 to N `Order` values per subscription | Lists, data batches, continuous event streams |

Examples:

~~~java
Supplier<String> single = () -> "ORD-101";

Supplier<Mono<String>> oneAsync =
    () -> Mono.just("ORD-101");

Supplier<Flux<String>> manyAsync =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

`Flux` does not force data to run in parallel, does not automatically make I/O non-blocking, and does not imply all data is already in memory. It represents a signal stream that a caller or adapter must consume via a subscription.

### 2.2. Signals Determining the Lifecycle

A publisher emits the following signals:

- `onSubscribe`: the subscription is established.
- `onNext(value)`: a new element is emitted.
- `onComplete`: normal completion; no further elements will be emitted.
- `onError(error)`: termination due to an error; no `onComplete` follows.

A subscriber can request data via `request(n)` (*backpressure*) and cancel with `cancel()`. Upon cancellation, the publisher is no longer obligated to continue emitting data to that subscriber.

~~~mermaid
flowchart TD
    G["Supplier.get()"] --> P["Flux<T>"]
    P --> S["Subscriber subscribes"]
    S --> N["onNext(T)"]
    N --> D{"Source still active?"}
    D -->|New element available| N
    D -->|Normal completion| C["onComplete"]
    D -->|Error occurred| E["onError"]
    S -->|Unsubscribe| X["cancel"]
~~~

**Three distinct counters:** one `get()` call can create a publisher, one `subscribe()` call can consume that publisher, and each subscription can result in multiple `onNext` signals. Do not infer the number of `get()` calls from the number of emitted messages.

## 3. Supplier Returning a Finite Stream

Finite streams fit **data seeding**, **exporting a batch of records**, **pushing a list of tasks to run**, or **reading a page of results**. Example emitting three orders once:

~~~java
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<String>> initialOrders =
    () -> Flux.just("ORD-101", "ORD-102", "ORD-103");
~~~

A subscription to this cold publisher receives three `onNext` signals in order followed by one `onComplete`. `get()` does not return a finished `List<String>`; it returns a `Flux<String>` describing the sequence of data.

### 3.1. Several Ways to Create a Finite Stream

~~~java
// Known set of values:
Flux<String> fromValues = Flux.just("A", "B", "C");

// Finite range of integers:
Flux<Integer> fromRange = Flux.range(1, 5);

// Iterable source, acquiring an iterator upon subscription:
Flux<String> fromIterable =
    Flux.fromIterable(java.util.List.of("A", "B", "C"));

// Empty stream: no onNext signals, only onComplete.
Flux<String> empty = Flux.empty();

// Time-based stream that stops after three elements:
Flux<Long> firstThreeTicks =
    Flux.interval(java.time.Duration.ofSeconds(1)).take(3);
~~~

`take(3)` makes the output **finite**, even though the `Flux.interval` source is capable of emitting indefinitely. After receiving three elements, `take` cancels the upstream subscription and completes the resulting publisher.

### 3.2. Want to Read Fresh Data on Subscribe?

The following two approaches differ in when data is fetched:

~~~java
// Calls loadPending() immediately when get() creates the Flux:
Supplier<Flux<Order>> eagerAtGet =
    () -> Flux.fromIterable(loadPending());

// Calls loadPending() only for each subscription:
Supplier<Flux<Order>> deferredToSubscribe =
    () -> Flux.defer(
        () -> Flux.fromIterable(loadPending())
    );
~~~

Here `Order` and `loadPending()` are hypothetical types/methods. `Flux.defer` creates a publisher from a factory for each subscription. It is useful when fresh data is needed at consumption time or when isolating source creation; however, if `loadPending()` is a blocking query, running it directly in the `defer` callback **can still block the subscribing thread**. Prefer a reactive repository or move the blocking source onto an appropriate scheduler such as `boundedElastic` during incremental migration.

With a cold source, subscribing twice can read the data and run side effects twice. Replay is normal Reactor behavior; in broker integrations, add **idempotency** if the same order must not be created twice.

## 4. Supplier Returning a Continuous Stream

A continuous source can emit many events over time and does not terminate on its own under normal conditions. Example heartbeat every second:

~~~java
import java.time.Duration;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<Long>> heartbeat =
    () -> Flux.interval(Duration.ofSeconds(1));
~~~

`Flux.interval(Duration.ofSeconds(1))` emits `0L` roughly one second after subscription, then `1L`, `2L`, and so on periodically. Each subscription to this publisher normally gets its own counter and emission schedule, so this source is **cold per subscription**, even though it can run continuously.

The source will not emit `onComplete` by itself; it stops when the subscription is canceled, an error occurs (such as failing to satisfy `Flux.interval` backpressure demand), or the application lifecycle ends. Do not use `Flux.interval` to emit business records that require durable persistence: ticks are generated in memory and are not recovered by default after a restart.

### 4.1. Each Element Can Be a Business Event

~~~java
record SensorEvent(String sensorId, long sequence) {}

Supplier<Flux<SensorEvent>> sensorEvents =
    () -> Flux.interval(Duration.ofSeconds(2))
        .map(sequence -> new SensorEvent("sensor-01", sequence));
~~~

In this example:

1. `sensorEvents.get()` constructs the stream description.
2. A subscription starts the schedule for the `interval` source.
3. Each tick runs `map` and emits a `SensorEvent`.
4. Emissions continue as long as the subscription remains active.

A real event source may pull data from Kafka, RabbitMQ, WebSocket, or a reactive API. In that case, arrival timing, emission rate, replay capability, message loss, and connection management are governed jointly by the source library and the adapter.

### 4.2. A Continuous Stream Does Not Guarantee Regular Elements

`Flux.never()` is also a publisher that never completes, yet **emits no elements at all**. An SSE/WebSocket source can stay silent for hours before emitting data. Thus, “continuous stream” describes the ability to **keep a subscription open**, not a promise of constant data or a fixed emission rate.

## 5. Complete Spring Cloud Function Example

The configuration below defines two `Supplier<Flux<T>>` beans: one source that emits **two orders and completes**, and one heartbeat source that **stays active until canceled**. The example uses Java 17+ (for `record`), Spring Cloud Function, and Project Reactor.

~~~java
package demo.functions;

import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderSuppliers {

    public record OrderEvent(String orderId, long amountCents) { }

    @Bean
    public Supplier<Flux<OrderEvent>> initialOrders() {
        return () -> Flux.just(
            new OrderEvent("ORD-101", 12_000),
            new OrderEvent("ORD-102", 8_500)
        );
    }

    @Bean
    public Supplier<Flux<Long>> heartbeat() {
        return () -> Flux.interval(Duration.ofSeconds(1));
    }
}
~~~

Both beans have the `Supplier<Flux<...>>` type, but their termination contracts differ:

| Criterion | `initialOrders` | `heartbeat` |
| --- | --- | --- |
| Elements per subscription | 2 | No fixed finite limit |
| Source | `Flux.just` | `Flux.interval` |
| Normal termination signal | `onComplete` after the second element | Never emits `onComplete` unless bounded |
| Emission timing | Driven by subscriber demand | Scheduled every second |
| Data after restart | Both orders may be re-emitted if the source is called/subscribed again | Tick counter starts fresh with the new subscription |
| Stopping consumption | Stream completes on its own | Requires `cancel`, stopping the adapter, or bounding with an operator like `take` |
| Specific risks | Recreating side effects if orders are re-emitted | Lack of backpressure, non-terminating source, overly long lifetime |

### 5.1. Lookup and Transformation via FunctionCatalog

`FunctionCatalog` allows an application to look up functions by name and compose them. Suppose we want to retain only orders with a positive amount:

~~~java
@Bean
public java.util.function.Function<
        Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
    return orders -> orders.filter(order -> order.amountCents() > 0);
}
~~~

The `positiveOrders` bean is added to the same configuration containing `OrderEvent`. When an adapter supports Spring Cloud Function composition, the definition can chain the supplier and function:

~~~properties
spring.cloud.function.definition=initialOrders|positiveOrders
~~~

Logically, `initialOrders` emits a `Flux<OrderEvent>` and `positiveOrders` receives that stream to filter it. The `filter` operator runs per element and does not cause `initialOrders.get()` to re-run for each order.

Check the binding names and output contract of the **selected composition** on the adapter you are using. Declaring `definition` alone does not start a broker, HTTP server, or schedule: those belong to the deployment environment.

## 6. Who Calls Supplier? Who Subscribes? Who Receives Each Element?

These three steps typically live in three different places:

~~~mermaid
flowchart LR
    A["Application / adapter"] -->|get()| S["Supplier<Flux<T>>"]
    S -->|returns| F["Flux<T>"]
    A -->|subscribe| F
    F -->|onNext T1| O["Subscriber / adapter"]
    F -->|onNext T2| O
    F -->|onComplete or onError| O
    O --> R["HTTP response / event output"]
~~~

- **Spring Cloud Function Core:** A `Supplier` bean is a Java function; by itself it creates no scheduler, no broker, and does not subscribe unconditionally. A caller or adapter triggers it.
- **Spring Cloud Stream:** With supported reactive supplier integration, the framework typically calls the supplier to obtain the `Flux` and maintains a subscription to process emitted items. Do not assume the polling model of imperative suppliers applies verbatim to `Supplier<Flux<T>>`.
- **HTTP adapter:** A request can trigger the function and consume the publisher within the scope of the request. Whether the `Flux` turns into a finite JSON response or a stream depends on the adapter, media type, configuration, and client capabilities.
- **Serverless adapter:** An invocation usually has a time limit. A non-terminating `Flux` may be unsuitable if the runtime needs to await results or close the invocation.

**Do not call `subscribe()` manually inside a supplier just to “push data out.”** Return the publisher so the adapter manages subscription, errors, and cancellation. Subscribing internally creates a separate subscription, which can easily cause data to run before the caller is ready or detach errors from the adapter's management mechanism.

## 7. Deploying via Spring Cloud Stream: Finite and Continuous Streams

When an application includes Spring Cloud Stream and a corresponding binder, a supplier can act as the source for an output binding. For example, **selecting only `heartbeat`**:

~~~properties
spring.cloud.function.definition=heartbeat
spring.cloud.stream.bindings.heartbeat-out-0.destination=heartbeat-events
~~~

The value `heartbeat-out-0` is the output binding name following functional naming conventions for a single bean. The destination `heartbeat-events` is a logical name mapped to the broker by the binder. You must install the binder dependency and configure connections and serialization for your environment; these properties alone do not create a broker.

If you want to export only the **finite batch of orders**, you can switch to:

~~~properties
spring.cloud.function.definition=initialOrders
spring.cloud.stream.bindings.initialOrders-out-0.destination=initial-orders
~~~

Pick only one definition in your configuration; these snippets are **two independent alternatives**.

### 7.1. Important Difference in Invocation Schedule

With an imperative supplier `Supplier<T>`, some Spring Cloud Stream integrations use a poller to call `get()` periodically. With a **reactive supplier `Supplier<Flux<T>>`**, the standard handling is to invoke the supplier to get the publisher and subscribe to it, then receive items from the reactive pipeline. Therefore:

- `Flux.just(a, b)` emits `a` and `b` and then completes; do not expect the binder by default to call `get()` again every second to re-emit the batch.
- `Flux.interval(...)` can continue emitting ticks within a single long-lived subscription; no poller needs to call `get()` again for each tick.
- If you need to repeat a batch periodically, **express the time-based repetition directly inside the publisher** or use an explicitly designed scheduler mechanism.
- On restarts, reconnects, or configured retries, a new subscription may be established. Therefore, never assume “at-most-once delivery” merely because a reactive supplier is used internally.

Invocation behavior, lifecycle management, backpressure, and error propagation ultimately depend on the **framework version, binder, and active configuration**. Verify with integration tests against a real broker whenever delivery semantics matter to the business.

### 7.2. What Happens When a Finite Stream Finishes?

When `initialOrders` completes normally, the publisher signals `onComplete`. No further data arrives from that subscription. This **does not mean the Spring Boot application stops automatically** or that the binding is necessarily reinitialized. If the requirement is “push data once at startup,” you must design emission counts, restart conditions, sent-marker tracking, and duplicate-emission handling.

### 7.3. Continuous Streams on Application Shutdown

The `heartbeat` source keeps generating ticks as long as the subscription stays alive. The adapter must cancel the subscription when stopping the binding or shutting down the application to release schedulers, connections, and resources. If the stream uses TCP, WebSocket, or an external SDK, know how the publisher closes resources rather than assuming JVM termination alone suffices.

## 8. Re-Emitting Data Batches Periodically: Designing Explicitly

A common mistake is using a finite supplier and expecting the adapter to “automatically call it again.” If the goal is **every 30 seconds, read pending orders**, express the trigger directly inside the Flux. The following example is a pattern where `repository.findPending()` returns `Flux<OrderEvent>` from a non-blocking API:

~~~java
@Bean
public Supplier<Flux<OrderEvent>> pendingOrdersEvery30Seconds() {
    return () -> Flux.interval(
            Duration.ZERO,
            Duration.ofSeconds(30)
        )
        .concatMap(tick -> repository.findPending());
}
~~~

The snippet above is an **integration outline**; `repository` is an application dependency that must be injected and implemented. `Duration.ZERO` produces the first tick immediately on subscription, then waits 30 seconds between ticks. `concatMap` ensures query runs are not subscribed to concurrently and stay in order; if queries are slow, ticks can pile up, so you must design load limits, timeouts, and error handling.

To illustrate a cycle that **can run standalone without a repository**, use a fixed list:

~~~java
Supplier<Flux<String>> demoEvery30Seconds =
    () -> Flux.interval(Duration.ZERO, Duration.ofSeconds(30))
        .concatMap(tick -> Flux.just("ORD-101", "ORD-102"));
~~~

Each tick emits those exact two IDs again. This is a cadence-testing tool, **not an exactly-once business event source**. If the source is a database, broker, or API, you must have an idempotency key/checkpoint to prevent duplicate processing.

### 8.1. Why Not Use Unconditional repeat()?

~~~java
Supplier<Flux<String>> problematic =
    () -> Flux.just("ORD-101", "ORD-102").repeat();
~~~

`repeat()` re-subscribes after every `onComplete`. With a finite publisher that emits immediately, this can loop extremely fast, causing high CPU load and continuously sending duplicate records. When controlled repetition is needed, use time-based triggers, timers, schedulers, or delay operators matching your requirements.

### 8.2. A Failure in One Poll Should Not Blindly Kill the Whole Stream

If a query fails inside `concatMap`, an unhandled error becomes `onError` for the entire output. A policy to skip a failed poll cycle (appropriate only when business rules allow it) can be placed **inside** the inner publisher:

~~~java
Supplier<Flux<OrderEvent>> resilientPoll = () ->
    Flux.interval(Duration.ZERO, Duration.ofSeconds(30))
        .concatMap(tick ->
            repository.findPending()
                .onErrorResume(error -> {
                    log.warn("Poll failed at tick {}", tick, error);
                    return Flux.empty();
                })
        );
~~~

`log` and `repository` are hypothetical dependencies; the callback sits inside each query execution. If an error must halt further processing due to risk of data loss or ordering corruption, do not convert it into `Flux.empty()`; propagate the error to the system's error handler instead.

## 9. Finite/Infinite Streams and Cold/Hot Are Two Orthogonal Axes

**Finite/continuous** describes whether a stream terminates. **Cold/hot** describes the relationship between the source and subscriptions. You cannot deduce one property from the other.

| Example | Finite or continuous? | Cold or hot? | Key behavior to remember |
| --- | --- | --- | --- |
| `Flux.just("A", "B")` | Finite | Cold | Each subscription can replay A, B |
| `Flux.range(1, 100)` | Finite | Cold | Each subscription reruns the sequence |
| `Flux.interval(Duration.ofSeconds(1))` | Continuous | Cold per subscription | Each subscriber gets its own schedule/counter |
| `Flux.interval(...).take(5)` | Finite | Cold per subscription | Emits five ticks then completes |
| `Sinks.Many<T>.asFlux()` with a push source | Depends on how the source stops | Typically hot | Late subscribers may miss earlier data |
| Publisher using `cache()` | Depends on the underlying source | Can replay cached data | Must consider memory, history, and subscription timing |

### 9.1. Illustrating a Hot Source with Sinks

A source pushing into `Sinks.Many` can back a supplier:

~~~java
import java.util.function.Supplier;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink =
    Sinks.many().multicast().directBestEffort();

Supplier<Flux<String>> liveEvents = sink::asFlux;

// Where external events arrive:
Sinks.EmitResult emitted = sink.tryEmitNext("ORD-201");
if (emitted.isFailure()) {
    // Log error / decide whether to retry or enqueue.
}
~~~

`directBestEffort` is not a durable queue and does not guarantee replay. With multicast, late subscribers miss previously emitted events; when there is insufficient demand or no subscribers, `tryEmitNext` can fail. Production code must inspect `EmitResult` and decide whether to retry, buffer, or drop according to the business contract.

Hence, a hot source is not inherently better than a cold source. Choose the source model based on requirements for **replay, durability, subscriber count, and overload policy**.

## 10. Backpressure and Resource Pressure

Reactive Streams allows downstream consumers to request a specific amount of data via `request(n)`. This matters for `Supplier<Flux<T>>` because the source can emit faster than processing speed or broker send rates.

### 10.1. With Finite Sources

Suppose a source emits one million records:

~~~java
Supplier<Flux<Integer>> oneMillion =
    () -> Flux.range(1, 1_000_000);
~~~

`Flux.range` can emit according to subscriber demand without pre-allocating a million-element `List`. However, if you add `collectList()`, all elements may be buffered in memory. If you add `flatMap` calling I/O with excessive concurrency, the number of active tasks can overwhelm the system.

### 10.2. With Continuous Sources

`Flux.interval` is a time-driven source: if downstream cannot keep up and has not requested elements, it can signal an overflow error rather than slowing down indefinitely. The following operators carry distinct trade-offs:

| Strategy | What happens? | Best suited when |
| --- | --- | --- |
| `onBackpressureDrop()` | Drops elements when downstream cannot accept them | Telemetry where sample loss is acceptable |
| `onBackpressureLatest()` | Keeps only the latest value, replacing older ones | Current-state updates |
| `onBackpressureBuffer(capacity)` | Temporarily holds elements in a bounded buffer | Short bursts with a capped memory budget |
| Limit concurrency/emission rate | Reduces active tasks or throttles the source | Business data where integrity takes priority |
| Offload to a durable broker/queue | Decouples producer and consumer rates with retention policies | Messages must never be lost |

Do not apply `onBackpressureDrop` to orders, payments, or mandatory tasks unless another mechanism guarantees data recovery. Unbounded `onBackpressureBuffer()` also risks out-of-memory errors. Backpressure signals inside Reactor do not automatically force external brokers or APIs to obey the same limits.

### 10.3. Monitoring and Canceling Subscriptions

Lifecycle milestones can be observed as follows:

~~~java
Supplier<Flux<Long>> observed = () ->
    Flux.interval(Duration.ofSeconds(1))
        .doOnSubscribe(subscription ->
            System.out.println("heartbeat subscribed"))
        .doOnNext(tick ->
            System.out.println("tick=" + tick))
        .doFinally(signal ->
            System.out.println("finished by " + signal));
~~~

`doFinally` can receive `CANCEL` when the subscriber cancels, `ON_COMPLETE` on normal completion, or `ON_ERROR` on failure. Side effects here only illustrate observation; production environments should use logging/metrics with rate-limited log output.

## 11. Errors, Retries, and Delivery Guarantees

If the publisher returned by a supplier emits `onError`, the current subscription ends. Distinguish between **restarting the publisher** and **re-sending business data**:

~~~java
Supplier<Flux<String>> retrying =
    () -> fetchFromRemoteSource()
        .retry(2);
~~~

`fetchFromRemoteSource()` is a hypothetical factory/source returning `Flux<String>`. `retry(2)` allows up to two retries after an error per Reactor semantics, by re-subscribing to upstream. If the source already emitted several elements before failing, those elements **may be emitted again** when the new subscription starts. Design both source and consumer to be idempotent, or use proper resume/checkpoint mechanisms.

For continuous sources, unbounded retries can create a tight recovery loop when an external system is down. Use backoff, retry limits, observability, and decide when failures must be escalated to the adapter.

### 11.1. Message Guarantees Do Not Come from the Flux Type

`Supplier<Flux<T>>` by itself does **not** guarantee exactly-once delivery, at-least-once delivery, durable ordering, or acknowledgments. Those depend on the binder, transactions, producer/consumer design, and external systems. When a finite source replays after a restart, downstream systems may receive duplicates. When a hot source is interrupted, events may be lost without storage/replay mechanisms.

For critical events, explicitly define idempotency keys (e.g., `eventId`), checkpoint locations, retry policies, dead-letter handling, and recovery strategies when the application stops mid-flight.

## 12. Message<T> and Per-Event Metadata

When a source needs to attach headers such as a correlation ID or event type, `Supplier<Flux<Message<T>>>` lets you attach metadata **per element**:

~~~java
import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Supplier<Flux<Message<Long>>> heartbeatMessages = () ->
    Flux.interval(Duration.ofSeconds(1))
        .map(sequence ->
            MessageBuilder.withPayload(sequence)
                .setHeader("eventType", "HEARTBEAT")
                .setHeader("source", "inventory-service")
                .build()
        );
~~~

Each `Message<Long>` holds the payload and headers for an individual tick. When an adapter converts it into a broker message, which headers pass through intact, data formats, and metadata mapping depend on the binder and serialization. `Flux<Message<T>>` does **not** mean the entire Flux is a single message; in supported binder configurations, individual elements can be translated into separate messages.

If a downstream function consumes `Flux<Message<T>>` to filter/transform items, preserve critical business headers. When composition combines N elements into one result, explicitly specify which metadata must be kept or aggregated.

## 13. Testing Finite and Continuous Sources

In Reactor testing, `StepVerifier` helps assert elements, completion signals, and errors. The following example uses the same `OrderSuppliers` class from Section 5 along with `reactor-test` and JUnit 5.

### 13.1. Testing That a Finite Stream Completes

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class OrderSuppliersTest {

    private final OrderSuppliers suppliers = new OrderSuppliers();

    @Test
    void initialOrdersEmitsTwoThenCompletes() {
        StepVerifier.create(suppliers.initialOrders().get())
            .expectNext(
                new OrderSuppliers.OrderEvent("ORD-101", 12_000),
                new OrderSuppliers.OrderEvent("ORD-102", 8_500)
            )
            .verifyComplete();
    }
}
~~~

`verifyComplete()` asserts that `onComplete` follows the two elements and no `onError` occurs.

### 13.2. Testing a Continuous Stream with Virtual Time

You do not need to wait three real seconds to test the heartbeat. `StepVerifier.withVirtualTime` replaces the time scheduler with a virtual one, provided the publisher is created **inside** the supplier factory passed to `StepVerifier`:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class HeartbeatTest {

    @Test
    void heartbeatCanBeLimitedToThreeTicks() {
        OrderSuppliers suppliers = new OrderSuppliers();

        StepVerifier.withVirtualTime(
                () -> suppliers.heartbeat().get().take(3)
            )
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
    }
}
~~~

`take(3)` makes the tested publisher complete after three ticks by canceling upstream. **Do not conclude** that `heartbeat` itself emits `onComplete` after three seconds; without `take`, it is designed to keep emitting.

### 13.3. Counting get(), Subscriptions, and Elements

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger getCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger items = new AtomicInteger();

Supplier<Flux<String>> feed = () -> {
    getCalls.incrementAndGet();

    return Flux.just("A", "B")
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doOnNext(value -> items.incrementAndGet());
};

Flux<String> result = feed.get();
// getCalls=1; subscriptions=0; items=0

StepVerifier.create(result)
    .expectNext("A", "B")
    .verifyComplete();
// getCalls=1; subscriptions=1; items=2

StepVerifier.create(result)
    .expectNext("A", "B")
    .verifyComplete();
// getCalls=1; subscriptions=2; items=4
~~~

With this cold source, two subscriptions replay `A` and `B` without re-running `feed.get()`. Only if `feed.get()` is called again does `getCalls` increase. On hot sources or shared publishers, emission counts may differ.

### 13.4. Essential Integration Tests

Reactor unit tests only verify the publisher. Before running a supplier through a real adapter, also verify: whether `definition` selects the right bean; whether the output binding targets the right destination; whether a completed finite stream is unintentionally re-subscribed; whether a continuous stream stops on shutdown; how the binder reacts when the broker is slow, failing, or restarting; and whether the system duplicates or drops messages.

## 14. Common Misconceptions

| Misconception | Accurate interpretation |
| --- | --- |
| “A `Supplier<Flux<T>>` emits exactly one value.” | One `get()` call returns one **publisher**; the publisher can emit 0 to N values. |
| “`Flux` is always an infinite stream.” | `Flux.just`, `range`, `empty`, or `take` can all be finite. |
| “A continuous stream is definitely hot.” | `Flux.interval` is usually cold per subscription, even though it never terminates on its own. |
| “Calling `get()` means the elements have already been sent.” | For cold publishers, elements are emitted only on subscription and downstream demand. |
| “`Supplier<Flux<T>>` is called again for each message.” | Reactive adapters usually subscribe to one publisher; each `onNext` represents a processed element. |
| “A finite stream will always be polled again after completion.” | There is no such guarantee; inspect your adapter and design explicit re-emission schedules. |
| “`repeat()` is a good way to poll.” | Repeating a stream that completes immediately can spin in a tight loop and flood duplicates. |
| “Backpressure guarantees the broker can never be overloaded.” | Throttling must be supported across the entire pipeline and adapter. |
| “`Flux.interval` fits all critical events.” | In-memory ticks lack durability and replay capabilities like an event log. |
| “`retry` does not affect how many times data is processed.” | Re-subscribing to a source can replay elements emitted before the error. |
| “Serverless can wait for an infinite stream to finish.” | Runtimes enforce invocation limits; design bounded processing or supported streaming. |

## 15. Choosing a Design Based on Business Requirements

| Requirement | Implementation approach to consider |
| --- | --- |
| Emit a fixed dataset | `Supplier<Flux<T>>` with `Flux.just` / `fromIterable`, emitting `onComplete` |
| Reactive query fetching a batch of data | Return the publisher from a reactive repository; control pagination and re-emission |
| Periodic updates | `Flux.interval` or scheduler → `concatMap` to data source; bound errors and load |
| Emit telemetry where sampling loss is acceptable | Continuous stream with an appropriate backpressure policy |
| Emit orders/events requiring durability | Event broker/outbox/checkpoint and idempotency; do not rely on in-memory timers |
| One asynchronous result per invocation | Consider `Supplier<Mono<T>>` |
| Reuse the same logic across HTTP and event binders | Verify subscription lifecycle, response/binding types, and conversion mechanisms |
| Execute within short serverless invocations | Prefer bounded sources or slice streams by time/count boundaries |

A solid design must answer: **Where does the source get data? When does the adapter call `get()`? Who subscribes? What conditions complete or cancel the stream? Are replays or dropped elements acceptable?** The `Supplier<Flux<T>>` signature is the starting point of the data contract, not an automatic answer to those operational questions.

## 16. Self-Assessment Questions

1. A `Supplier<Flux<String>>` returns `Flux.just("A","B")`. If the caller calls `get()` once and subscribes twice to the same cold publisher, how many times does `get()` run? How many times are the elements emitted?
2. Why is `Flux.interval(Duration.ofSeconds(1))` considered a continuous stream yet still a cold source?
3. Is `Flux.interval(...).take(5)` still a continuous stream at its output? When does the subscriber cancel upstream?
4. In Spring Cloud Stream, why should you not expect `Supplier<Flux<Order>>` with `Flux.just(...)` to automatically re-emit the same batch every second?
5. When you need to read 100 new orders every 30 seconds, how would you design the trigger and pipeline to avoid sending duplicates or spawning concurrent overlapping queries?
6. Why can `retry(2)` on a source that emits three messages before failing lead to duplicate messages?
7. For a continuously running heartbeat, how do you use virtual time to test three ticks without waiting in real time and without hanging the test?
8. What must you keep in mind about headers when a supplier emitting `Flux<Message<T>>` passes through a binder or function composition?

**Key takeaway:** `Supplier<Flux<T>>` describes a source returning a **publisher**, while element count, emission timing, and termination depend on the publisher itself. `Flux.just(...)` is a finite example; `Flux.interval(...)` is a continuous example. To deploy safely in Spring Cloud Function, clearly separate `get()` invocations, subscription lifecycles, re-emission policies, and how adapters deliver each element over HTTP, events, or serverless environments.
