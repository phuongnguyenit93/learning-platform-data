# Regulating Processing Rate by Consumer Demand

## 1. Why Is Rate Regulation Needed in Reactive Streams?

Imagine a system receiving **10,000 order events per second** while a risk-check service can only handle around **500 events per second** steadily. If you keep reading and firing every event into the check task, pending requests, memory usage, and latency climb rapidly. Eventually the application can exhaust connections, run out of memory, or suffer widespread timeouts.

In the **Reactive Streams** model, **backpressure** allows the receiver to express demand: *“How many more elements am I currently ready to receive?”* A sender capable of honoring this mechanism emits data on demand rather than pushing unboundedly.

The **Reactive Streams** chapter of **Spring Cloud Function** relies heavily on Project Reactor's `Mono` and `Flux`. Java beans such as `Supplier`, `Function`, and `Consumer` can be looked up via `FunctionCatalog`, composed, and exposed over HTTP, message brokers, or serverless environments. However, **having `Flux` in a signature does not automatically guarantee backpressure all the way to an external data source**. Rate regulation takes effect only at pipeline segments and connectors that support it.

For example, a function processing an order stream:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> evaluate =
    orders -> orders.flatMap(
        riskClient::check, // Mono<Decision>
        8                  // At most 8 active inner tasks
    );
~~~

`flatMap(..., 8)` limits **how many inner publishers are processed concurrently within one subscription**. It helps avoid firing too many requests at once, yet it does not inherently cap how many messages a broker delivers to the application, define an overload storage policy, or bound concurrent calls across other instances.

This lesson walks from Reactive Streams **`request(n)`** to practical rate-regulation strategies in Spring Cloud Function.

### Learning Objectives

After this lesson, you will be able to:

1. Explain `Publisher`, `Subscriber`, `Subscription`, and how demand propagates from downstream to upstream.
2. Distinguish **backpressure**, **concurrency limits**, **buffering**, **source throttling**, and **rate limiting**.
3. Observe the effect of `request(n)` using `BaseSubscriber` or `StepVerifier`.
4. Choose among `flatMap`, `concatMap`, `limitRate`, and `onBackpressure...` operators based on whether data loss is acceptable or data must be retained.
5. Identify the limitations of hot sources, time-driven sources, and external sources that do not obey backpressure.
6. Design, test, and monitor reactive functions across HTTP, event binders, and serverless environments.

## 2. Reactive Streams: Demand Comes from the Receiver

Reactive Streams defines interactions among these components:

| Component | Role |
| --- | --- |
| `Publisher<T>` | Source capable of emitting `T` elements and terminal signals |
| `Subscriber<T>` | Party subscribing to receive data and reacting to signals |
| `Subscription` | Link between both sides, enabling `request(n)` and `cancel()` |
| `onNext(T)` | Signal that an element has been emitted |
| `onComplete()` | Normal completion |
| `onError(Throwable)` | Termination due to an error |

When a subscriber subscribes, the publisher provides a `Subscription` via `onSubscribe`. The subscriber can call `request(n)` with `n > 0` to ask for `n` more elements.

~~~mermaid
sequenceDiagram
    participant D as Subscriber (downstream)
    participant S as Subscription
    participant P as Publisher (upstream)

    D->>P: subscribe(...)
    P-->>D: onSubscribe(subscription)
    D->>S: request(2)
    S->>P: propagate demand
    P-->>D: onNext(A)
    P-->>D: onNext(B)
    Note over D,P: Remaining demand exhausted
    D->>S: request(1)
    S->>P: add demand
    P-->>D: onNext(C)
    P-->>D: onComplete
~~~

This illustrates a finite publisher capable of honoring demand. `onComplete` and `onError` are terminal signals; they are not data elements and do not count against `request(n)`.

### 2.1. What Is Outstanding Demand?

If a subscriber calls `request(5)` and then receives three `onNext` signals, on that subscription link there remains demand for two more elements. If it then calls `request(4)`, total unfulfilled demand increases accordingly.

- Positive requests accumulate.
- Calling `request(0)` or `request(n)` with `n < 0` violates the Reactive Streams contract and results in an error per subscription rules.
- `Long.MAX_VALUE` represents **unbounded demand**. It effectively allows upstream to emit as fast as it can instead of waiting for small incremental requests.
- `cancel()` informs upstream that the subscriber no longer wants data, though whether an external I/O operation stops immediately depends on the integration library.

**Demand measures element count, not time.** `request(10)` does not mean “10 elements per second”; it means “able to accept up to 10 more elements under the publisher's contract.” Limiting per-second rate requires a separate time-based throttling mechanism.

### 2.2. Reactor subscribe Overloads Usually Request Unbounded Demand

Convenience overloads such as:

~~~java
flux.subscribe(System.out::println);
~~~

typically request unbounded demand. That is handy for small programs, though it does not show downstream issuing demand in batches.

When you want explicit demand control, use `BaseSubscriber`, a custom subscriber, or test with `StepVerifier`. You do not need to manage requests manually inside every function: Reactor operators handle demand regulation themselves.

## 3. Experimenting with request(n) Using BaseSubscriber

The example below performs a subscription that first requests two elements, then requests three more to consume the finite source completely:

~~~java
import org.reactivestreams.Subscription;

import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {

    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(n ->
                System.out.println("Upstream requested: " + n)
            );

        source.subscribe(new BaseSubscriber<>() {
            private int received;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(2);
            }

            @Override
            protected void hookOnNext(Integer value) {
                received++;
                System.out.println("Received: " + value);

                if (received == 2) {
                    request(3);
                }
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("Completed");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.err.println("Failed: " + error);
            }
        });
    }
}
~~~

With `Flux.range(1, 5)`, the subscriber requests 2 and then 3 more; the source emits `1, 2, 3, 4, 5` and completes. `doOnRequest` lets you observe demand signals at that exact point in the pipeline.

Key points to note:

1. `Flux.range` is a finite, cold publisher capable of emitting according to demand.
2. Inside `hookOnSubscribe`, the subscriber begins with `request(2)`.
3. After receiving two elements, the subscriber calls `request(3)` to process the rest.
4. If no further request is made once demand reaches zero, the source can pause at two elements even without emitting `onComplete`.
5. `BaseSubscriber` is not an HTTP or broker consumption framework; the example simply exposes the Reactive Streams mechanism.

**Avoid using `BaseSubscriber` to “await” asynchronous I/O by calling `request(1)` directly inside `hookOnNext`.** When the callback runs, a newly launched async I/O task may not be finished yet. To limit active I/O tasks, compose their publishers with `concatMap` or `flatMap` at an appropriate concurrency level.

### 3.1. Canceling When Data Is No Longer Needed

~~~java
Flux.range(1, 100)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
            cancel();
        }
    });
~~~

The subscriber receives the first element and requests cancellation. With a cancellation-aware source, upstream stops supplying the remaining elements. **Canceling a subscription does not equal successfully committing a transaction or rolling back external operations.**

## 4. Backpressure Changes Across Operators

Look at a Reactor stream:

~~~java
Flux<Integer> result = Flux.range(1, 100)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10);
~~~

If downstream wants 5 even numbers, upstream may have to emit more than 5 numbers initially because `filter` drops odd numbers. Hence:

> **Never assume a `request(1)` at the end of a pipeline always arrives as exactly `request(1)` at the source.**

How some operators transform demand:

| Operator | How it affects upstream demand |
| --- | --- |
| `map` | Usually maps one element to one element; close to a 1–1 relationship |
| `filter` | May request extra elements to make up for filtered-out values |
| `buffer(10)` | One output batch requires up to 10 input elements for a full batch |
| `flatMap` | Can subscribe to multiple inner publishers and prefetch elements |
| `concatMap` | Serializes inner publishers; maintains internal requests/buffers depending on Reactor version |
| `publishOn` | Switches downstream emission to another scheduler and uses a queue/prefetch |
| `limitRate` | Splits a large request into smaller upstream requests |
| `collectList` | Accumulates data to emit one result when upstream completes |

### 4.1. Buffer Example: One Batch Request Differs from One Element Request

~~~java
Flux<java.util.List<Integer>> batches =
    Flux.range(1, 6).buffer(3);
~~~

Suppose a subscriber requests **one batch** from `batches`. `buffer(3)` must consume three integers from upstream to produce a `List<Integer>` of size three. Thus, output demand is measured in **batches**, whereas input demand is measured in **integers**.

For large streams, batch size must be bounded; `collectList()` on a non-terminating stream waits forever and risks unbounded memory growth.

### 4.2. Prefetch and Internal Queues

Asynchronous operators like `flatMap` or `publishOn` commonly use **prefetching**: proactively requesting a chunk of elements to reduce waiting overhead and improve throughput. This means the number of items sitting in queues or in flight can exceed the number downstream just requested directly.

Therefore, when monitoring backpressure, inspect all of these:

- Demand emitted by downstream.
- Demand rewritten by intermediate operators.
- Elements sitting in internal queues/buffers.
- Active inner publishers.
- Speed and capacity of the target I/O system.

Never use `request(n)` at a single point to infer the total amount of data currently inside the system.

## 5. limitRate: Splitting Upstream Requests

`limitRate` alters how a pipeline requests data from a source:

~~~java
Flux<Integer> limited = Flux.range(1, 100)
    .doOnRequest(n ->
        System.out.println("Requested upstream: " + n)
    )
    .limitRate(10);
~~~

If downstream requests a huge number of elements, `limitRate(10)` splits upstream demand into smaller chunks capped at the configured high watermark, instead of forwarding an unbounded request straight to the source. Reactor replenishes demand once a fraction of items has been consumed to keep data flowing smoothly.

**`limitRate(10)` does not mean at most 10 elements per second.** It shapes *request sizes* at a pipeline boundary. If both source and downstream are very fast, 100 elements can still finish in a tiny fraction of a second.

Additionally, `limitRate`:

- Does not set a global cap on total messages stored in a broker.
- Does not replace concurrency limits across multiple active HTTP requests.
- Does not replace a bounded queue if the source pushes regardless of demand.
- Does not automatically guarantee ordering or exactly-once semantics in external systems.

### 5.1. When Is It Useful?

`limitRate` helps when you want to observe or pace upstream requests in chunks—for instance, when a publisher reads pages or incurs high cost per request batch. Exact `doOnRequest` numbers also depend on surrounding operators and the Reactor version, so verify actual impact with tests or metrics.

## 6. Regulating Active I/O Tasks with flatMap and concatMap

In asynchronous processing, the biggest bottleneck is often **in-flight operations**: open HTTP requests, JDBC connections, transaction locks, or broker writes. You can use `flatMap` with a concurrency cap.

### 6.1. Spring Cloud Function Bean Processing an Event Stream

The example below uses Java 17+, Spring Cloud Function, and Project Reactor. `RiskClient` is an application interface that can be backed by `WebClient` or an async SDK returning `Mono`.

~~~java
package demo.flowcontrol;

import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class RiskFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public enum RiskStatus {
        APPROVED, REJECTED, UNAVAILABLE
    }

    public record Decision(String orderId, RiskStatus status) {}

    public interface RiskClient {
        Mono<Decision> check(OrderEvent event);
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> assessRisk(
            RiskClient client) {

        return incoming -> incoming.flatMap(
            order -> client.check(order)
                .timeout(Duration.ofSeconds(2)),
            8
        );
    }
}
~~~

Observations:

1. `assessRisk.apply(flux)` builds the pipeline for **one input publisher**; it does not call the risk service for everything immediately.
2. `flatMap` subscribes to `Mono<Decision>` tasks as upstream emits `OrderEvent` items.
3. The argument `8` bounds concurrent inner publishers at that operator.
4. `timeout` sits inside each inner publisher, so it applies per check call.
5. `flatMap` can emit results **out of original order**.
6. If an inner publisher emits an unhandled error, the resulting stream can terminate with `onError`.

If the system must **halt the entire stream when the risk service fails**, letting the error propagate is appropriate. If failed events must be flagged and processing continued, produce an explicit per-element business result.

### 6.2. Handling Errors Inside Each Inner Task

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<Decision>> assessRiskResilient(
        RiskClient client) {

    return incoming -> incoming.flatMap(
        order -> client.check(order)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(
                    order.orderId(),
                    RiskStatus.UNAVAILABLE
                ))
            ),
        8
    );
}
~~~

`UNAVAILABLE` represents **could not verify**, distinct from `REJECTED` determined by business rules. By handling the error inside the **inner publisher**, a transient network error does not necessarily kill the entire `Flux`.

Use this strategy only when downstream accepts an indeterminate status. For payments or safety-critical decisions, you may need to stop the stream, send to a dead-letter queue, or perform bounded retries—never silently treat errors as success.

### 6.3. Need to Preserve Side-Effect Ordering?

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> sequential =
    events -> events.concatMap(client::check);
~~~

`concatMap` subscribes to each inner publisher one at a time, waiting for the previous task to finish before starting the next. This suits ordered state updates, at the cost of lower throughput when I/O is slow.

`flatMapSequential` subscribes to tasks concurrently while emitting **results** in source order. It **does not guarantee external service side effects complete in order**. If write A must complete before write B begins, consider `concatMap`.

### 6.4. A Cap of 8 Is Not a System-Wide Limit

Suppose each instance has 5 active subscriptions, each running `flatMap(..., 8)`. Peak active inner tasks can exceed 8 per instance. When you scale out to more instances, total load grows even further.

Control concurrency at multiple layers: subscription counts, consumer counts, operator concurrency, connection pools, API rate limits, and downstream capacity. When a cluster-wide limit is required, use distributed coordination or centralized throttling; a `flatMap` parameter inside each pipeline is not enough.

## 7. When the Source Ignores Demand: Buffer, Drop, Latest, and Error

Not every source can pause on `request(n)`. Physical sensors, SDK callbacks, WebSocket pushes, or timers may emit data while the subscriber is not ready. That is where an **overload policy** is needed.

Reactor provides `onBackpressure...` operators to handle senders that outpace requested demand.

| Strategy | Meaning | Data loss? | Suitable when |
| --- | --- | --- | --- |
| `onBackpressureBuffer(...)` | Temporarily holds excess items in a queue | Can error when full if bounded | Short bursts with budgeted memory |
| `onBackpressureDrop(...)` | Drops items when downstream cannot keep up | Yes | Telemetry where sample loss is acceptable |
| `onBackpressureLatest()` | Retains only the latest value, overwriting older queued items | Yes | UI display status, current position |
| `onBackpressureError()` | Emits an error when demand cannot be satisfied | Stops stream | Fail-fast requirement and explicit overload signaling |
| Source/producer control | Slows data generation or pauses upstream reads | Not necessarily | Critical data that must be retained completely |
| Durable queue | Persists data outside heap memory for later processing | Depends on configuration/durability | Orders, payments, business workflows |

### 7.1. Bounded Buffers

~~~java
Flux<SensorReading> buffered = pushSource
    .onBackpressureBuffer(100);
~~~

With Reactor overloads accepting a capacity, the buffer holds a finite number of items. If data arrives too fast and the buffer fills up, the pipeline can fail with an overflow error. **A buffer does not slow down the source**; it absorbs rate mismatches over a short interval.

Questions to answer before configuring a buffer: how many bytes does one element take? How many concurrent subscriptions exist? What happens when the queue fills? Does data need disk/broker durability? Can data be recovered after a restart?

Avoid unbounded buffers as a default for infinite streams. If upstream stays faster than downstream, the queue will eventually grow to dangerous memory levels.

### 7.2. Dropping Samples with drop/latest

~~~java
Flux<SensorReading> sampled = pushSource
    .onBackpressureLatest();
~~~

If a subscriber only needs the **latest state**, discarding intermediate values can make sense. For instance, a temperature display does not need to render every single reading during a UI stall.

Similarly:

~~~java
Flux<SensorReading> dropWhenBusy = pushSource
    .onBackpressureDrop(reading ->
        metrics.recordDroppedReading()
    );
~~~

This assumes `metrics.recordDroppedReading()` is a lightweight, non-blocking metric call. This policy is **unsuitable** for payment events or writes that must process every element, unless an independent storage/recovery path exists.

### 7.3. Signaling Error on Overload

~~~java
Flux<SensorReading> failWhenBusy = pushSource
    .onBackpressureError();
~~~

Choose `onBackpressureError` when the application must surface overload explicitly rather than silently dropping items. After `onError`, the subscription terminates; recovery requires designing a fresh source, replay, or resume mechanism. Do not treat an outer `onErrorResume` as “resuming the old stream from the next item.”

### 7.4. Note: Operators Cannot Rescue Data Already Lost Upstream

If a driver already dropped an event **before** feeding it into `Flux`, adding `onBackpressureBuffer` downstream cannot recover that event. If a broker delivers a message and the consumer acknowledges it before durable persistence, a disconnect can lose data. Backpressure policies must be designed end-to-end **from the data source to durable storage**, not only inside the in-memory Reactor pipeline.

## 8. Flux.interval and Hot Sources: When Request Is Not Enough

### 8.1. Flux.interval Emits by Time

~~~java
Flux<Long> ticks =
    Flux.interval(Duration.ofMillis(100));
~~~

`Flux.interval` is scheduled to emit periodic ticks. If downstream has no demand when a tick fires, Reactor can terminate the subscription with a backpressure overflow error rather than pausing wall-clock time externally. This illustrates a time-based source that cannot “wait indefinitely” while keeping its cadence.

To observe ticks without letting a test run forever, use `take(n)`:

~~~java
Flux<Long> firstFive = ticks.take(5);
~~~

`take(5)` makes the resulting publisher emit at most five ticks and then complete/cancel the source. It does **not** turn `Flux.interval` into a durable event store.

### 8.2. Hot Sources with Sinks

A callback API can push events into `Sinks.Many<T>`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer(64);

Flux<String> stream = sink.asFlux();

// External callback wants to push an event:
Sinks.EmitResult outcome = sink.tryEmitNext("ORDER-101");

if (outcome.isFailure()) {
    // Choose a policy: report error, retry, enqueue, or reject.
}
~~~

`Sinks` lets external callbacks push data into Reactor without forcing callbacks to be rewritten as cold publishers. However, it does not turn an in-memory queue into a durable message broker. Behavior when there are no subscribers, multiple subscribers, a full queue, or a terminated sink depends on the sink type and configuration.

Avoid spinning in an infinite retry loop calling `emitNext` when a sink reports overflow, as that spikes CPU and blocks the producer thread. For mandatory data, use durable/temporary staging and explicit backoff.

## 9. Distinguishing Backpressure from Rate Limiting and Batching

The techniques below complement one another, yet serve different purposes:

| Mechanism | Question answered | Illustrative tools |
| --- | --- | --- |
| **Backpressure** | How many more elements can downstream accept? | `request(n)`, `Subscription` |
| **Concurrency limit** | At most how many async tasks are currently active? | `flatMap(mapper, 8)`, `concatMap` |
| **Rate limiting** | At most how many requests start per second? | Token/rate limiters at client, gateway, or source |
| **Buffering** | Where are short-term rate mismatches held? | `onBackpressureBuffer`, bounded queues |
| **Batching** | Can N elements be processed in one batch? | `buffer(100)`, `bufferTimeout` |
| **Sampling/drop** | Can data be discarded under overload? | `onBackpressureDrop`, `onBackpressureLatest` |
| **Broker flow control** | Can transport slow down message delivery/emission? | Binder-dependent: consumer prefetch, poll, ack, pause |

### 9.1. Limiting Call Rate Over Time

Suppose an API allows at most **100 requests/second**. `flatMap(..., 8)` only guarantees at most eight in-flight requests **within one subscription**; it does not prevent exceeding 100 requests/second when each request completes in a couple of milliseconds.

You need a rate limiter based on token buckets, semaphores paired with schedulers, or client/gateway rate limiting. A `Flux.interval` publisher can generate timed triggers, though you should not blindly turn every API into “one element per tick” without evaluating buffering, cancellation, and clock precision.

### 9.2. Batching Is Effective When Size Is Controlled

~~~java
Function<Flux<OrderEvent>, Flux<java.util.List<OrderEvent>>> batch100 =
    orders -> orders.buffer(100);
~~~

`buffer(100)` emits a list once 100 elements arrive; a partial batch under 100 emits only when the source completes normally. If the stream is infinite and event density is low, a batch can wait for a very long time.

If a time cap is needed, you can use:

~~~java
Function<Flux<OrderEvent>, Flux<java.util.List<OrderEvent>>> batches =
    orders -> orders.bufferTimeout(
        100,
        Duration.ofSeconds(5)
    );
~~~

This splits by max count or max duration. Verify timer behavior, memory impact, empty windows, or trailing batches on your Reactor version. Batching helps when downstream supports bulk writes, yet overly large batches increase latency, commit times, and retry blast radius.

## 10. Spring Cloud Function's Role in a Backpressure Pipeline

A reactive function typically has the signature:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>>
~~~

Calling `apply(input)` may only **construct the pipeline**, while elements are processed upon subscription. Therefore distinguish:

- **Function invocation:** the adapter passes a `Flux<OrderEvent>` into `Function.apply`.
- **Subscription:** the output subscriber activates the Reactor chain.
- **Demand:** downstream demand travels backward through operators that support it.
- **Business work:** `flatMap`/`concatMap` triggers per-element I/O publishers.
- **Lifecycle:** `onComplete`, `onError`, or `cancel` determines termination.

### 10.1. Separating Filtering from API Calls

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
    return orders -> orders
        .filter(order -> order.amountCents() > 0);
}
~~~

With the `assessRisk` bean from Section 6, Spring Cloud Function can compose:

~~~properties
spring.cloud.function.definition=positiveOrders|assessRisk
~~~

The two signatures are stream-compatible: `positiveOrders` emits `Flux<OrderEvent>`, and `assessRisk` takes `Flux<OrderEvent>` and returns `Flux<Decision>`. `FunctionCatalog` handles name lookup and composition; **it does not create an end-to-end backpressure guarantee just by composing functions**.

### 10.2. Supplier: Does the Source Produce Data on Demand?

~~~java
@Bean
Supplier<Flux<Integer>> orderIds() {
    return () -> Flux.range(1, 1000);
}
~~~

`Flux.range` emits on demand and is finite. Conversely:

~~~java
@Bean
Supplier<Flux<Long>> sensorTicks() {
    return () -> Flux.interval(Duration.ofMillis(100));
}
~~~

`Flux.interval` emits by time. In Spring Cloud Stream, the adapter can obtain the publisher to maintain a long-lived subscription; however, how often the supplier is invoked, how messages are pushed, and how throttling reaches the broker depend on the adapter.

If the source must be read on a schedule in finite batches, `@PollableBean` can be used with a poller-capable Spring Cloud Stream setup. In that case, **polling cadence** decides when to construct a new batch, whereas `request(n)` governs demand inside a subscription when Reactor components are compatible. The two mechanisms are not the same.

### 10.3. Consumer: Who Subscribes and Who Issues Demand?

~~~java
Consumer<Flux<OrderEvent>> loggingConsumer = source ->
    source.subscribe(
        event -> logger.info("{}", event),
        error -> logger.error("stream failed", error)
    );
~~~

With an explicit reactive `Consumer<Flux<T>>`, because `accept` returns `void`, the caller/framework has no resulting publisher to subscribe to. The consumer normally has to subscribe itself while managing `Disposable`, errors, and lifecycle. Convenience `subscribe(...)` overloads usually request unbounded demand; to regulate flow, prefer building concurrency-bounded pipelines or using a demand-aware subscriber.

If completion/error signals must be returned to the caller, consider:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persistOrders = source ->
    source.concatMap(repository::save).then();
~~~

Here `repository.save` is a hypothetical API returning a publisher. The returned `Mono<Void>` can be subscribed to and observed for completion by the caller. For non-terminating sources, the pipeline-wide `Mono<Void>` also may never complete during the app's lifetime; it does not by itself represent **per-message** acknowledgment.

## 11. HTTP, Brokers, and Serverless: Where Does Backpressure End?

Reusing the same Spring Cloud Function bean across protocols is a major architectural advantage, yet Reactor's rate regulation only helps where components along the path support it.

~~~mermaid
flowchart LR
    E["Event source / HTTP / broker"] --> A["Adapter"]
    A --> P["Input Flux"]
    P --> F["FunctionCatalog + Function<Flux<T>,Flux<R>>"]
    F --> O["Output Flux"]
    O --> D["Adapter / downstream"]
    D --> DEST["HTTP client / broker / target service"]
    D -.->|"request(n) if supported"| O
    O -.->|"demand propagates backward"| F
    F -.->|"demand propagates backward"| P
    P -.->|"requires connector support"| A
~~~

### 11.1. HTTP

A reactive HTTP stack can represent bodies as publishers and support streaming responses, but real behavior depends on the HTTP adapter, media type, client, and network layer. For example, a server may stream items or buffer results before responding. Reactor backpressure does not necessarily mean TCP/network immediately pauses the upstream business source.

When a client disconnects, cancellation can propagate to the subscription. Still, an already-running external write does not automatically roll back or abort instantaneously; design timeouts and cleanup explicitly.

### 11.2. Spring Cloud Stream and Binders

Spring Cloud Stream documentation states clearly: using reactive APIs **does not automatically provide end-to-end backpressure** if the source or destination is not Reactive Streams compatible. With a non-reactive Kafka or Rabbit binder, message-channel boundaries can break direct propagation of `request(n)` to the broker.

Infrastructure layers have their own throttling mechanisms such as consumer prefetch, records per poll, pause/resume, acks, or credits; names and semantics vary by binder. Those settings **are not automatically controlled by `limitRate(10)` in Java**.

Furthermore, Spring Cloud Stream documentation notes that **the reactive Kafka binder has been marked deprecated as of version 4.3.0**. Always check your Spring Cloud Stream version and connector maintenance roadmap before picking a binder purely for end-to-end reactive behavior; do not treat that binder as a default choice for new projects.

### 11.3. Reactive Functions and Retries

In the reactive model, a function may be applied once to establish a long-lived pipeline. Individual messages then flow through operators; the framework does not necessarily apply the same **per-message** interception and error wrapper as with an imperative `Function<T,R>`.

Consequently, `onErrorResume`, `retryWhen`, timeouts, and error classification **inside the pipeline** are critical. Meanwhile, transport errors, redelivery, and acknowledgments must still be handled according to the actual binder.

### 11.4. Serverless

Serverless environments enforce invocation timeouts and concurrency quotas. An infinite `Flux` is naturally unsuitable when the runtime must await completion. Use finite input boundaries, cap concurrent requests, and finish within allowed limits.

Backpressure does not replace serverless platform concurrency limits, external API quotas, or controlling concurrent invocations. For high-volume event processing, pair queues/brokers with batch consumption and idempotency.

## 12. Message<T>, Partitioning, and Ordering

A payload-only `Flux<T>` may lack information needed to decide how to regulate processing. When you need event IDs, partition keys, or correlation IDs, use `Flux<Message<T>>`:

~~~java
Function<
    Flux<org.springframework.messaging.Message<OrderEvent>>,
    Flux<Decision>
> processMessages = messages -> messages
    .flatMap(message ->
        riskClient.check(message.getPayload()),
        8
    );
~~~

This example illustrates payload processing; the `Decision` output does not automatically carry input headers. If downstream needs correlation IDs, return `Message<Decision>` and copy/select the appropriate business headers.

When a stream interleaves multiple partition keys, parallel execution raises throughput while changing completion order. If events sharing an `orderId` must be processed sequentially, partition streams by key, bound parallelism, and ensure each key is not processed concurrently across multiple instances. **`flatMap(..., 8)` does not automatically preserve per-partition ordering.**

## 13. Observing Demand, Queues, Errors, and Cancellation

Reactor hooks can instrument a pipeline:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> observed =
    source -> source
        .doOnRequest(n ->
            logger.debug("Downstream requested {}", n)
        )
        .flatMap(riskClient::check, 8)
        .doOnError(error ->
            logger.error("Risk stream failed", error)
        )
        .doFinally(signal ->
            logger.info("Risk stream finished by {}", signal)
        );
~~~

Note: `doOnRequest` observes demand **at the exact point where it is placed**. If a downstream operator rewrites demand, requests seen upstream can differ from the final subscriber's original requests.

Metrics worth tracking in production:

| Group | Example metrics | Meaning |
| --- | --- | --- |
| Throughput | Events received/sec, events succeeded/sec | Spot rate mismatches |
| Latency | p50/p95/p99 processing time | Detect slow downstreams |
| Concurrency | Active in-flight I/O requests | Verify `flatMap` bounds and pools |
| Queues | Buffer depth and dwell time | Detect backlogs |
| Overload | Dropped events, buffer overflows | Evaluate data-loss policies |
| Errors | Timeouts, retries, dead-letters, redeliveries | Assess resilience |
| Lifecycle | Subscriptions, completions, cancellations | Verify source closing/cancellation |
| Broker | Lag, offsets, acks, consumer pause/prefetch | Observe transport-side mismatches |

Avoid logging every `onNext` at very high rates; logging itself can bottleneck the pipeline. Use aggregated metrics, sampling, or rate-limited logs.

### 13.1. A Common Mistake When Measuring Demand

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doOnRequest(n -> logger.info("request={}", n))
    .buffer(5);
~~~

If a subscriber requests one **`List`**, `buffer(5)` may request more than one **`Integer`** from upstream. Therefore, `request(n)` observed at `Flux.range` must be interpreted in the source's units; never compare it directly against batch requests at the output.

## 14. Testing Backpressure with StepVerifier

`reactor-test` lets you specify initial demand via `StepVerifier.create(publisher, initialRequest)`. This verifies that a publisher does not emit beyond demand in deterministic tests.

### 14.1. Requesting 2, Then 3 More Elements

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {

    @Test
    void sourceRespectsDemandInTwoRounds() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0L)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();

        assertEquals(5L, requested.get());
    }
}
~~~

The test starts with `0` demand, then explicitly requests `2` and `3`. With a direct `Flux.range` source and no request-rewriting operators, total upstream demand is five elements.

### 14.2. Requesting One Batch Requires Three Source Elements

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BufferDemandTest {

    @Test
    void batchesChangeDemandUnit() {
        Flux<List<Integer>> batches = Flux.range(1, 6).buffer(3);

        StepVerifier.create(batches, 0L)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(List.of(1, 2, 3))
            .thenRequest(1)
            .expectNext(List.of(4, 5, 6))
            .verifyComplete();
    }
}
~~~

This test clarifies that `request(1)` on the output of `buffer(3)` asks for **one list**, not one integer.

### 14.3. Testing Concurrency Limits

For asynchronous I/O, you can track active task counts with a delayed publisher to verify concurrency bounds:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ConcurrencyTest {

    @Test
    void flatMapDoesNotExceedConfiguredConcurrency() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxSeen = new AtomicInteger();

        Flux<Integer> pipeline = Flux.range(1, 10)
            .flatMap(number -> Mono.defer(() -> {
                int now = active.incrementAndGet();
                maxSeen.accumulateAndGet(now, Math::max);

                return Mono.delay(Duration.ofMillis(10))
                    .map(ignored -> number)
                    .doOnTerminate(() -> active.decrementAndGet());
            }), 2);

        StepVerifier.create(pipeline.collectList())
            .assertNext(results -> assertEquals(10, results.size()))
            .verifyComplete();

        assertTrue(maxSeen.get() <= 2);
    }
}
~~~

This test verifies inner-publisher concurrency within one subscription, **not a cluster-wide limit**. To test broker pausing, full queues, retries, or disconnects, run integration tests against the adapter/binder.

### 14.4. Testing Time Sources and Cancellation

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`withVirtualTime` avoids waiting in real time when testing Reactor schedulers. `take(3)` stops after three ticks; it does not mean the underlying `Flux.interval` completes on its own.

When testing a continuous source without `take`, use `thenCancel()` and `verify()` instead of waiting forever for `onComplete`. Also verify cleanup with `doFinally` or real resource-closing tests.

## 15. Real-World Scenario: Processing Orders Without Losing Events

An e-commerce system receives an order event stream. Input can spike sharply during peak hours; the risk-check service is slower than the source. The goal is **never to lose a single order** while keeping latency acceptable.

A production design must address multiple layers:

1. **Durable source:** place events in a broker/outbox or replayable store; never rely on `Flux.interval` or in-RAM buffers as the source of truth.
2. **Ingestion and throttling:** configure message consumption, prefetch/poll, partitions, and acknowledgments per binder; evaluate throttling at the transport boundary.
3. **Reactor pipeline:** use `flatMap(..., concurrency)` for independent I/O, or `concatMap` when ordering is required; never use drop/latest for mandatory orders.
4. **Errors:** set timeouts, bounded retries, dead-letter handling, and distinguish transient errors from business rejections.
5. **Idempotency:** use an `eventId` key so broker redeliveries or upstream resubscriptions are safe.
6. **Observability:** track consumer lag, buffers, throughput, active requests, errors, and latency.
7. **Testing:** test slow brokers, instance shutdowns, mid-batch failures, cancellations, and restarts.

Sample pipeline (assuming `OrderEvent`, `Decision`, and `RiskClient` match Section 6):

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> controlledProcessing(
        RiskClient riskClient) {

    return incoming -> incoming
        .flatMap(order ->
            riskClient.check(order)
                .timeout(Duration.ofSeconds(2))
                .retryWhen(
                    reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(200)
                    )
                ),
            8
        );
}
~~~

This covers only **the Reactor processing layer**. To claim “zero lost orders,” you also need idempotency for `riskClient.check`, broker retry/ack policies, a durable event source, and end-to-end failure tests. `retryWhen` can duplicate side effects if an earlier call succeeded on the target service while its response was lost.

### 15.1. When Is Dropping Data Acceptable?

For monitoring telemetry such as instantaneous temperature or UI frame rates, losing some samples may be acceptable. You can use `onBackpressureLatest` or `onBackpressureDrop`, while recording metrics on dropped items and having rules to refresh state.

For financial transactions, orders, invoices, or compliance events, every item can carry an individual obligation. Dropping items only masks immediate resource pressure while risking data loss; prioritize durable sources, bounded queues, and rate control at producers/consumers.

## 16. Common Misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| “Using `Flux` automatically slows the broker via `request(n)`.” | Only supporting components and compatible connectors propagate demand end-to-end. |
| “`request(10)` means 10 elements per second.” | It is the number of additional elements permitted, not a time-based rate cap. |
| “`subscribe(onNext)` defaults to requesting one element.” | Convenience overloads normally request unbounded demand. |
| “`limitRate(10)` limits throughput to 10 requests/second.” | It chunks upstream demand; it does not impose a time limit. |
| “`flatMap(..., 8)` caps tasks at eight cluster-wide.” | It caps concurrent inner publishers within one subscription to that operator. |
| “`flatMapSequential` makes database writes happen in order.” | It can preserve output value order while still executing side effects concurrently. |
| “An unbounded buffer handles every burst.” | Under sustained rate mismatches, memory can still be exhausted. |
| “`onBackpressureLatest` never loses data.” | It overwrites older queued values with newer ones. |
| “Backpressure recovers events already dropped by an SDK before entering Flux.” | Events lost upstream cannot be recovered by Reactor downstream. |
| “`Mono<Void>` completes after each message in an infinite stream.” | Pipeline completion occurs when **the entire upstream** completes, not after each element. |
| “An outer `onErrorResume` resumes the old subscription.” | It replaces the failed publisher; the errored upstream already terminated its subscription. |
| “A `StepVerifier` unit test proves broker flow control.” | Integration tests at the binder/transport boundary and delivery layer are required. |

## 17. Self-Assessment Questions

1. What is `request(n)`? Why is it not a limit of `n` elements per second?
2. A subscriber requests five elements and then receives three `onNext` signals. Without further requests, how much demand remains on that subscription?
3. Is it valid for a subscriber to call `request(0)`?
4. Why can `filter` or `buffer` make upstream request counts differ from downstream request counts?
5. How do `limitRate(16)` and `flatMap(mapper, 16)` differ in purpose?
6. When do you choose `concatMap` over `flatMap`? Why does `flatMapSequential` not guarantee commit order?
7. Why is `onBackpressureDrop` better suited to certain telemetry data than to payment events?
8. What happens to `Flux.interval` if the subscriber has no demand when a tick needs to fire?
9. Why can a buffered `Sinks.Many` not replace a durable broker?
10. Does using `Function<Flux<T>, Flux<R>>` in Spring Cloud Function automatically guarantee backpressure with Kafka or RabbitMQ?
11. If a function runs across five instances, is `flatMap(..., 8)` enough to cap the whole system at eight concurrent HTTP requests?
12. How would you use `StepVerifier.create(publisher, 0L)` to prove a source honors demand?
13. Which metrics distinguish broker backlog, Reactor pipeline backlog, and external API bottlenecks?
14. When data must be processed completely without loss, how would you combine backpressure, idempotency, retries, and acknowledgments?

## 18. References

- [Reactive Streams — Specification](https://www.reactive-streams.org/) — `Publisher`, `Subscriber`, `Subscription`, and `request(n)` rules.
- [Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) — `BaseSubscriber` and shaping requests.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — operators, prefetch, buffers, errors, and cancellation.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` and demand-based testing.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive function model and backpressure limits with non-reactive binders.
- [Spring Cloud Stream — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html) — notes on deprecation status and binder selection roadmap.

Configuration options and adapter behaviors can vary across library versions. Before deploying to production, verify your BOM/versions of Spring Cloud Function, Spring Cloud Stream, Reactor, binders, and actual transport protocols.

**Key takeaway:** Backpressure in Reactive Streams is **consumption demand** expressed via `request(n)`. It lets compatible publishers and operators regulate how many elements are emitted to a subscriber. `flatMap` bounds concurrent async tasks, `limitRate` chunks demand, while buffer/drop/latest represent overload policies with distinct trade-offs. In Spring Cloud Function, combine Reactor pipelines with source controls, broker throttling, resource limits, retries, and idempotency; reliable end-to-end rate regulation is only achieved when every boundary along the path supports it.
