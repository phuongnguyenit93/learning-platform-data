# @PollableBean, splittable, and the Responsibility of the External Polling Mechanism

## 1. Why Does a Finite Supplier<Flux<T>> Need @PollableBean?

In Spring Cloud Function, `Supplier<T>` is a zero-argument function that returns a result each time `get()` is called. When the result is a Reactor `Flux<T>`, we have **a publisher** capable of emitting multiple elements. This is a convenient way to build an event source, yet it raises a crucial operational question: **who decides when to call `get()` again after the stream finishes?**

Consider two sources:

~~~java
Supplier<Flux<String>> liveTicks =
    () -> Flux.interval(Duration.ofSeconds(1))
              .map(String::valueOf);

Supplier<Flux<String>> pendingIds =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

- `liveTicks.get()` creates a publisher capable of emitting continuously. In a reactive source adapter, you only need to invoke the supplier and subscribe to the publisher; ticks arrive over time.
- `pendingIds.get()` creates a finite publisher that emits two values and then `onComplete`. If `get()` is called only once, there is no second batch; to read again, **an active mechanism must call the supplier again**.

When integrated with Spring Cloud Stream, the framework normally treats a reactive supplier as a long-lived stream source: it calls `get()` to obtain the `Flux` and subscribes to consume it. Therefore, a source returning a finite `Flux.just(...)` **is not automatically invoked repeatedly** merely because its type is `Supplier<Flux<T>>`.

`@PollableBean` solves the problem of expressing *intent*: **this is a reactive supplier bean whose result is finite and needs to be polled repeatedly**. However, the annotation itself **does not provide a scheduler or polling algorithm**. Spring Cloud Function defines the annotation, while the consuming framework—such as Spring Cloud Stream—must recognize it and execute scheduled invocations.

This lesson focuses on three responsibilities that are often confused:

1. **`@PollableBean`**: marks how a reactive supplier should be consumed.
2. **`splittable`**: indicates whether each element of the result should be split into a separate message.
3. **External poller**: decides the trigger schedule, invocation count, lifecycle, errors, and how results are sent.

Because these responsibilities are separated, business logic can still be packaged with `Supplier`, `Function`, and `Consumer` and looked up via `FunctionCatalog`. The same function can be used by HTTP, event, or serverless adapters, though the triggering mechanism need not be the same.

## 2. Distinguishing get(), subscribe(), and onNext()

One poll does not equal one element. For a supplier returning a finite `Flux`, there are five milestones:

| Milestone | Actor | Meaning |
| --- | --- | --- |
| `get()` | Caller or adapter/poller | Asks the supplier to create a publisher for the current invocation |
| `subscribe()` | Caller, framework, or adapter | Subscribes to receive data from the publisher |
| `onNext(T)` | Publisher when data is available | Emits one element; downstream may convert it into a message |
| `onComplete()` | Finite publisher | Signals that the current subscription ended normally |
| `cancel()` | Subscriber/adapter | Stops consuming the publisher; necessary to release resources of long-lived sources |

Example:

~~~java
AtomicInteger getCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger items = new AtomicInteger();

Supplier<Flux<String>> source = () -> {
    getCalls.incrementAndGet();
    return Flux.just("A", "B", "C")
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doOnNext(value -> items.incrementAndGet());
};

Flux<String> result = source.get();
// getCalls=1; subscriptions=0; items=0

result.subscribe();
// getCalls=1; subscriptions=1; items=3
~~~

This is a pure Reactor example with an explicit subscriber. In a Spring Cloud Stream application, the adapter usually manages the subscription; supplier code only needs to return a `Flux`. If a poller calls `get()` again to fetch a new batch, `getCalls` increases by one. Conversely, subscribing again to the *same* cold publisher can replay the three elements **without calling `get()` again**.

Note that not every publisher is cold. A hot source can miss elements when a subscriber arrives late; an external I/O source has its own retry/acknowledgment rules.

~~~mermaid
flowchart LR
    TIMER["Poller / external trigger"] -->|triggers| GET["Supplier.get()"]
    GET --> FLUX["Finite Flux<T>"]
    FLUX -->|subscribe| SUB["Adapter"]
    SUB -->|onNext A| M1["Message A"]
    SUB -->|onNext B| M2["Message B"]
    FLUX -->|onComplete| DONE["Poll completes"]
    DONE -.->|next schedule: new get()| TIMER
~~~

The final dashed arrow is the **poller's responsibility**, not a built-in feature of Reactor or `@PollableBean`.

## 3. What Is @PollableBean Actually?

Spring Cloud Function provides the annotation:

~~~java
import org.springframework.cloud.function.context.PollableBean;
~~~

It can be used on bean declarations similarly to `@Bean`:

~~~java
@PollableBean
public Supplier<Flux<String>> recentOrders() {
    return () -> Flux.just("ORD-101", "ORD-102");
}
~~~

In this case, `@PollableBean` marks the supplier bean factory method; there is no need to add `@Bean` on the same method just to declare the bean a second time.

**Core boundary:** `@PollableBean` is a *marker annotation*. Spring Cloud Function **does not automatically set up a timer, spawn a thread, schedule `get()` calls, or send messages** simply upon seeing this annotation. Those capabilities must be implemented by the framework using it.

In Spring Cloud Stream, this annotation signals that a reactive supplier—which is normally treated as a continuous source—needs to be invoked repeatedly via a polling mechanism. Each invocation creates a finite publisher; once the subscriber finishes consuming it, the next invocation is performed by the trigger/poller.

### 3.1. Why Do @Bean and @PollableBean Behave Differently?

~~~java
@Bean
Supplier<Flux<String>> continuousSource() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(String::valueOf);
}

@PollableBean
Supplier<Flux<String>> finiteSource() {
    return () -> Flux.just("A", "B");
}
~~~

| Aspect | `@Bean Supplier<Flux<T>>` | `@PollableBean Supplier<Flux<T>>` |
| --- | --- | --- |
| Declaration role | Creates a regular functional bean | Creates a functional bean and marks it as needing polling |
| Java contract | `Supplier.get()` returns `Flux<T>` | Identical |
| Typical assumption in Spring Cloud Stream | Obtain one publisher to consume as a continuous reactive source | Re-poll the reactive supplier to collect finite batches |
| Independent schedule from the annotation alone? | No | No |
| Automatic exactly-once guarantee? | No | No |
| Always emits a separate message per element? | Depends on adapter and data type | Depends on `splittable` and adapter |

A supplier returning `Flux.never()` emits no elements and never completes; even with `@PollableBean`, it does not become a finite data source with results. Conversely, a `@Bean Supplier<Flux<T>>` can return a finite publisher—but if the adapter triggers it only once, that source finishes without being polled again.

### 3.2. What Is Outside the Annotation's Contract?

`@PollableBean` does not itself specify:

- Whether the poll interval is 1 second, 5 seconds, or cron-based.
- The maximum number of elements in each `Flux`.
- Whether polls overlap when one execution runs slowly.
- Whether automatic retries happen if a query fails or the binder fails to send.
- What point counts as “sent,” “acknowledged,” or “committed.”
- Which tasks resume when the application restarts.

Those decisions must be configured and verified at the poller/adapter together with the storage and messaging systems.

## 4. Spring Cloud Function Example: Emitting Finite Batches with @PollableBean

Suppose each poll must emit two inventory change records. This example is database-independent and generates data with an incrementing batch ID so you can easily see that **each `get()` call produces a new batch**.

~~~java
package demo.function;

import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class InventorySuppliers {

    private final AtomicLong batchCounter = new AtomicLong();

    public record StockChange(
        long batchId,
        String sku,
        int quantityDelta
    ) {}

    @PollableBean(splittable = true)
    public Supplier<Flux<StockChange>> stockChanges() {
        return () -> {
            long batchId = batchCounter.incrementAndGet();
            return Flux.just(
                new StockChange(batchId, "SKU-A", 5),
                new StockChange(batchId, "SKU-B", -2)
            );
        };
    }
}
~~~

If the poller invokes the supplier three times, inspecting each subscribed and completed publisher:

| `get()` call # | Publisher emits | Element count |
| ---: | --- | ---: |
| 1 | `StockChange(1, "SKU-A", 5)`, `StockChange(1, "SKU-B", -2)` | 2 |
| 2 | `StockChange(2, "SKU-A", 5)`, `StockChange(2, "SKU-B", -2)` | 2 |
| 3 | `StockChange(3, "SKU-A", 5)`, `StockChange(3, "SKU-B", -2)` | 2 |

This is an *illustrative* data-generating example. In real applications, new batches typically come from a repository or API, and you **should not** generate business data with an in-memory counter to simulate durability across restarts.

This code also shows that `@PollableBean(splittable = true)` does not alter the return type: `stockChanges().get()` is still `Flux<StockChange>`. Turning the two elements into two messages is handled by the postprocessor/adapter that understands the annotation.

### 4.1. Fetching a Batch from a Reactive Repository

An application can replace the manual generator with:

~~~java
@PollableBean
public Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPending();
}
~~~

This is an outline: `orderRepository` must be injected, `OrderEvent` is the business type, and `findPending()` must return `Flux<OrderEvent>`. When `get()` returns a fresh publisher, the reactive query typically executes upon subscription.

The biggest risk: if `findPending()` always re-reads orders whose status has not changed, **the same order can be emitted across multiple polls**. You need a strategy such as an outbox, processed flags, checkpoints, record claiming, or consumer-side idempotency; adding `@PollableBean` alone does not prevent duplicates.

If the repository is blocking (synchronous JDBC API), wrapping it in Reactor does not automatically make it non-blocking. Prefer reactive sources, or isolate blocking calls onto an appropriate scheduler and bound concurrency.

## 5. splittable: Split Elements or Keep the Publisher Intact?

`@PollableBean` has a `splittable` attribute, which defaults to **`true`** according to Spring Cloud Stream documentation. This attribute signals framework postprocessors how to handle the publisher produced by the supplier.

### 5.1. splittable = true: Split into Individual Messages

~~~java
@PollableBean(splittable = true)
Supplier<Flux<String>> codes() {
    return () -> Flux.just("A", "B", "C");
}
~~~

With a Spring Cloud Stream adapter that supports splitting, one poll returns a `Flux<String>` of three elements; the adapter can send **three separate messages** with payloads `"A"`, `"B"`, and `"C"`, respectively.

~~~mermaid
flowchart LR
    P["One poll"] --> F["Flux: A, B, C"]
    F --> SPLIT["splittable = true"]
    SPLIT --> A["Message(A)"]
    SPLIT --> B["Message(B)"]
    SPLIT --> C["Message(C)"]
~~~

Setting `splittable = true` does **not** mean the poller calls `get()` three times. It describes how **one Flux result** is forwarded once data arrives.

### 5.2. splittable = false: Do Not Request Splitting

~~~java
@PollableBean(splittable = false)
Supplier<Flux<String>> originalFlux() {
    return () -> Flux.just("A", "B", "C");
}
~~~

Here the annotation tells the postprocessor **not to perform the default step of splitting the Flux into individual messages**. The reactive result is kept intact at that processing boundary.

**Do not infer that every binder will automatically serialize a `Flux` object into a JSON array or automatically send one message containing the list `["A","B","C"]`.** With `splittable = false`, passing the publisher into the pipeline, payload formatting, and where downstream subscribes depend on the adapter and downstream consumers. If no component understands the publisher, you may not get the desired behavior.

### 5.3. What If Business Logic Requires One Message Containing the Whole Batch?

Create an **explicit batch type** and work with a concrete message contract, for example:

~~~java
public record StockBatch(
    String batchId,
    java.util.List<String> skus
) {}

@Bean
public Supplier<StockBatch> batchAsOnePayload() {
    return () -> new StockBatch(
        java.util.UUID.randomUUID().toString(),
        java.util.List.of("SKU-A", "SKU-B")
    );
}
~~~

This is an **imperative supplier** returning one `StockBatch` object on each `get()` call. When using the Spring Cloud Stream poller, the adapter can convert one `StockBatch` into one message payload according to serializer settings. The explicit type tells downstream this is a batch; scheduled polling and message dispatch still belong to the integration framework.

If you want a reactive API for a single batch, `Supplier<Mono<StockBatch>>` is also a valid data contract option. Check publisher handling and scheduling support for your specific adapter.

### 5.4. Choosing splittable

| Intent | Design to consider | What to verify |
| --- | --- | --- |
| Each `T` is an independent event | `@PollableBean(splittable = true) Supplier<Flux<T>>` | Output message count, headers, ordering, errors |
| Downstream receives and handles the whole publisher | `@PollableBean(splittable = false)` on a supporting adapter | Who subscribes, where the publisher flows, serialization |
| One message contains a list of items | Explicit batch/DTO payload type | How many messages per invocation, content type |
| Continuous stream source emitting elements over time | Usually `@Bean Supplier<Flux<T>>` | Subscription lifecycle and backpressure |

Choosing `splittable` is a choice about the **unit of output processing**, not the polling schedule or supplier invocation count.

## 6. Responsibilities of Spring Cloud Function vs. Spring Cloud Stream

Clarifying responsibilities helps avoid false expectations when running plain Java code:

| Component | Primary responsibility |
| --- | --- |
| **Spring Cloud Function Core** | Defining/registering function beans, `FunctionCatalog`, type-conversion wrappers, composition, providing `@PollableBean` as a marker |
| **Spring Cloud Stream** | Discovering/binding suppliers, orchestrating triggers/polling, accepting output, routing messages to the binder and configured destination |
| **Spring Integration poller** | Providing the trigger mechanism and configuring intervals, max messages per poll, and cadence per contract |
| **Binder (Kafka/RabbitMQ/...)** | Transport connectivity, message dispatch, serialization, and binder-specific delivery options |
| **Data store** | Persisting state, identifying new records, marking read/emitted items, handling failures and duplicates |
| **Application** | Idempotency policies, batching, transactions, retries, monitoring, and operational SLOs |

When an application includes only Spring Cloud Function Core, the following code **does not create a poller**:

~~~java
@PollableBean
Supplier<Flux<String>> changes() {
    return () -> Flux.just("A", "B");
}
~~~

To poll, the caller still has to use `FunctionCatalog` or the bean and schedule `get()`/subscriptions itself. In an environment with Spring Cloud Stream, the framework has its own poller mechanism that consumes that marker. This is the single most important distinction in this lesson.

## 7. Configuring a Pollable Supplier via Spring Cloud Stream

Suppose the application already includes Spring Cloud Stream and a suitable binder (such as Kafka or RabbitMQ), and has the `stockChanges` bean from Section 4. Configuration selecting the function and output destination:

~~~properties
spring.cloud.function.definition=stockChanges
spring.cloud.stream.bindings.stockChanges-out-0.destination=stock-updates
~~~

`stockChanges-out-0` is the output binding name following functional conventions for the `stockChanges` bean. `stock-updates` is the logical destination name; binder, broker, and serializer properties must be configured separately for your environment.

### 7.1. Default Polling Configuration in Spring Cloud Stream

In Spring Cloud Stream 5.1 documentation, poller properties are published under the `spring.integration.poller.` prefix. For example:

~~~properties
# Fixed pause between triggers, in milliseconds
spring.integration.poller.fixed-delay=5000

# Maximum number of receives per polling event
spring.integration.poller.maxMessagesPerPoll=1
~~~

In this documentation version, the stated defaults are `fixedDelay = 1000` milliseconds and `maxMessagesPerPoll = 1`. You can configure `cron`, `initialDelay`, and `timeUnit` when needed.

**Watch out for version differences:** older Spring Cloud Stream documentation may use the `spring.cloud.stream.poller.` prefix. Always check the exact BOM/dependency version you are deploying instead of copying old properties and assuming the schedule changed. The snippet above follows the 5.1 documentation.

`maxMessagesPerPoll` should not be naively read as “a `Flux` can emit at most one element.” With a reactive pollable supplier, one `get()` call can return a finite publisher emitting multiple `T` items; splitting and sending those elements belong to the output processing pipeline.

### 7.2. Dedicated Poller for a Single Output Binding

When multiple suppliers need different cadences, you can configure the poller per binding, for example:

~~~properties
spring.cloud.stream.bindings.stockChanges-out-0.producer.poller.fixed-delay=2000
~~~

This is how Spring Cloud Stream documentation describes configuring a specific output binding rather than modifying the application-wide default poller. In an actual project, verify that the property takes effect for your active version and binder.

### 7.3. Fixed Delay, Cron, and Slow Tasks

A `fixed-delay` setting expresses periodic trigger intent; it is **not** proof that every subscription has finished or that the broker has acknowledged everything before the next cycle starts.

If a query takes 15 seconds while the poll interval is 5 seconds, check whether the framework awaits task completion or only publisher creation. With asynchronous APIs, two cycles may overlap depending on the scheduler/adapter. To guarantee no overlapping polls or duplicate emissions, design and verify one of the following mechanisms:

- Locks/leases on the data source or concurrency bounds.
- Record claiming with leases and processing status.
- Checkpoint-based pagination and published-state marking.
- A self-managed sequential polling stream using `concatMap` if you choose an architecture without `@PollableBean`.

Never treat a poll cycle as a transaction or a single unit of acknowledgment.

## 8. How Do Continuous Sources Work Without @PollableBean?

If the publisher itself is already capable of long-lived emission, a normal reactive supplier usually suffices:

~~~java
@Bean
Supplier<Flux<Long>> ticker() {
    return () -> Flux.interval(Duration.ofSeconds(1));
}
~~~

In Spring Cloud Stream's reactive supplier model, fetching the `Flux` once is enough to start a long-lived subscription. `onNext` signals arrive at the source's pace. No poller needs to call `get()` every second to produce ticks.

Conversely, a finite source:

~~~java
@PollableBean
Supplier<Flux<String>> snapshot() {
    return () -> Flux.just("A", "B");
}
~~~

requires an external poller to invoke it again if the application wants subsequent snapshots.

### 8.1. Two Ways to Design Periodic Polling—Do Not Accidentally Enable Both

**Approach A: the framework re-invokes a finite supplier**

~~~java
@PollableBean
Supplier<Flux<String>> finiteChanges() {
    return () -> readNextFiniteBatch();
}
~~~

`readNextFiniteBatch()` is a hypothetical method returning a finite `Flux<String>`; the poll cadence belongs to Spring Cloud Stream or the caller.

**Approach B: the supplier schedules internally inside a continuous Flux**

~~~java
@Bean
Supplier<Flux<String>> scheduledChanges() {
    return () -> Flux.interval(
            Duration.ZERO,
            Duration.ofSeconds(5)
        )
        .concatMap(tick -> readNextFiniteBatch());
}
~~~

In Approach B, `Flux.interval` is the trigger; `concatMap` subscribes to batches sequentially within a single pipeline. This is an example of designing a continuous reactive source. If you simultaneously add `@PollableBean` and let an external poller re-invoke a `Flux.interval` source, you can create **multiple parallel emission schedules**, causing higher load and duplicate data. Pick one primary mechanism and define scheduler ownership clearly.

### 8.2. A Finite Stream Does Not Mean Data Always Changes

~~~java
@PollableBean
Supplier<Flux<String>> repetitive() {
    return () -> Flux.just("A", "B");
}
~~~

Every time `get()` is called, `A` and `B` appear again. The marker has no idea whether this is stale data. Therefore, business queries need state/checkpoints and consumers need idempotency.

## 9. Errors During a Poll and Subscription Lifecycle

If a poll yields `Flux.error(...)`, that subscription emits `onError` and terminates. Do not assume Spring Cloud Stream will silently retry, or that the poller will stay on schedule while preserving already-sent items; behavior depends on the binder, adapter, and configuration.

Example illustrating a source that can fail:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> changedOrders() {
    return () -> orderRepository.findChangedSinceLastCheckpoint();
}
~~~

When the source fails after already emitting some records:

1. The subscriber may have received several `onNext` signals before `onError`.
2. Whether the binder has already sent/acknowledged those messages is a separate concern.
3. If the next poll reads again from the old checkpoint, the previously emitted messages may be duplicated.
4. If the checkpoint was advanced too early, messages not yet sent successfully may be lost.

### 9.1. Retries Must Accompany Idempotency

~~~java
return () -> orderRepository.findPending()
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            3, Duration.ofMillis(200)
        )
    );
~~~

This outlines a retry strategy for transient failures; it does not fully address broker sends, checkpoints, or transactions. When upstream is re-subscribed, elements emitted before the error **can be emitted again**, so retries can introduce duplicate messages.

For operations with side effects, distinguish **query** failures from **message dispatch** failures. Retrying a data read is not the same as retrying a send that failed after the broker already received the message.

### 9.2. Do Not Use Flux.empty() to Hide Critical Errors

If a source returns `Flux.empty()`, the subscription completes with zero elements. That is a valid outcome when there is no new data. However, if a connection error is unconditionally turned into `Flux.empty()`, monitoring systems can mistakenly think the poll succeeded with no work to do.

Use one of the explicit policies instead: propagate the error and alert, perform bounded retries, translate the error into a business status, or skip the cycle only when business rules genuinely permit it. Errors must be logged and tracked with metrics.

## 10. How Does splittable Affect Headers and Message Conversion?

When `splittable = true`, each `T` element can become a message with its own payload. If per-element metadata is needed, you can emit `Message<T>`:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

@PollableBean(splittable = true)
public Supplier<Flux<Message<String>>> stockUpdates() {
    return () -> Flux.just("SKU-A", "SKU-B")
        .map(sku -> MessageBuilder.withPayload(sku)
            .setHeader("eventType", "STOCK_UPDATE")
            .setHeader("source", "warehouse-service")
            .build());
}
~~~

Each element is a Spring Messaging `Message<String>` carrying a payload and headers. The adapter/binder may map headers onto the transport or retain only headers permitted by configuration.

If `splittable = false`, you cannot assume metadata from **multiple** elements will be automatically merged into metadata for **one** message. When a whole batch must become one message, define a batch payload and its corresponding headers.

### 10.1. Using FunctionCatalog and Composition

Transformation logic should be separated from source-reading logic:

~~~java
@Bean
Function<Flux<StockChange>, Flux<StockChange>> positiveChanges() {
    return source -> source.filter(change ->
        change.quantityDelta() > 0
    );
}
~~~

Spring Cloud Function supports compositions like `stockChanges|positiveChanges` when signatures are compatible. However, how **attaching `@PollableBean` to the root supplier** interacts with **how the adapter recognizes metadata after composition** must be integration-tested on your exact version. Never rely solely on a unit test calling two Java functions to conclude that the scheduler and binder preserve the desired polling/splitting behavior.

With a per-message processing model, a `Function<StockChange, Result>` invoked for each message is sometimes more convenient than `Function<Flux<StockChange>, Flux<Result>>`. Define the pipeline's unit-of-work boundary clearly, especially when splitting is involved.

## 11. HTTP, Events, and Serverless: Same Bean, Different Trigger Ownership

`@PollableBean` does not create a “global schedule” shared across all protocols. In Spring Cloud Function, adapters are responsible for interpreting how invocation happens:

| Environment | Typical trigger unit | Impact on `@PollableBean` |
| --- | --- | --- |
| Direct Java / `FunctionCatalog` call | Caller explicitly invokes `get()` | The marker does not auto-invoke; caller must schedule if desired |
| Spring Cloud Stream | Output binding and poller | Can read the marker to re-poll finite reactive suppliers |
| HTTP adapter | An HTTP request/invocation | HTTP request is usually the trigger; do not assume the annotation triggers an HTTP server on a schedule |
| Serverless adapter | A platform-triggered invocation | External scheduler/trigger such as EventBridge, cron, or event source controls cadence |
| External scheduler + service | External scheduler cadence or job run | External system handles triggering, awaiting results, and controlling retries |

For example, a serverless job invoked every minute can fetch a finite batch and finish the invocation. When moving the same logic to Spring Cloud Stream, Stream's poller can take over the invocation schedule. Do not run an external cron **and** an in-app poller simultaneously unless partitioning or processing locks are explicitly coordinated.

When exposed over HTTP, whether a `Flux` is returned as a JSON array after completion or streamed element by element depends on the web adapter and content negotiation; `splittable` does not configure the media type by itself.

## 12. Threading, Backpressure, and Resource Management

A poller may run on a thread other than a Reactor event loop. Because a supplier takes no input, the triggering thread is chosen by the scheduler or framework; `ThreadLocal` data (such as tracing context) may not automatically cross asynchronous boundaries.

With a blocking source, the following is an **incorrect way to call it inside a reactive pipeline** when running on a sensitive thread:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> blockingRead() {
    return () -> Flux.fromIterable(
        blockingJdbcRepository.findAllPending()
    );
}
~~~

`blockingJdbcRepository.findAllPending()` executes as soon as `get()` is called, potentially blocking the poller thread. If you must use a legacy API, isolate it:

~~~java
@PollableBean
Supplier<Flux<OrderEvent>> boundedBlockingRead() {
    return () -> Mono.fromCallable(
            () -> blockingJdbcRepository.findAllPending()
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
}
~~~

This snippet assumes the repository returns `Iterable<OrderEvent>`; imports for `Mono`, `Flux`, and `Schedulers` must be present in the class. It offloads blocking work to an appropriate scheduler, yet **does not turn blocking JDBC into non-blocking I/O**. You still need timeouts, an appropriately sized connection pool, and concurrency limits.

### 12.1. Backpressure Differs from Polling Schedule

- **Polling** decides when to call `get()` to produce a batch.
- **Backpressure** regulates element demand from a publisher within a subscription.
- **Binder flow control** governs the ability to push messages into the broker and how transport overload is handled.

A stream emitting 100,000 records in a single poll can overload the system even if the poller only runs once per minute. `maxMessagesPerPoll=1` is not a built-in cap of 1 element inside every `Flux`. Add pagination/batch sizes, concurrency limits, backpressure, and real data-volume measurements.

If elements are orders or payments, do not casually use `onBackpressureDrop()` to avoid overload. When zero data loss is required, the solution typically requires durable data sources and delivery/acknowledgment mechanisms.

## 13. Testing Supplier Logic and Poller Behavior

With the `InventorySuppliers` example from Section 4, unit tests for the logic can invoke the supplier bean directly. `StepVerifier` confirms that each finite publisher emits two elements and completes:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Supplier;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class InventorySuppliersTest {

    @Test
    void newGetCreatesNextFiniteBatch() {
        InventorySuppliers config = new InventorySuppliers();
        Supplier<Flux<InventorySuppliers.StockChange>> source =
            config.stockChanges();

        StepVerifier.create(source.get())
            .expectNext(
                new InventorySuppliers.StockChange(1, "SKU-A", 5),
                new InventorySuppliers.StockChange(1, "SKU-B", -2)
            )
            .verifyComplete();

        StepVerifier.create(source.get())
            .expectNext(
                new InventorySuppliers.StockChange(2, "SKU-A", 5),
                new InventorySuppliers.StockChange(2, "SKU-B", -2)
            )
            .verifyComplete();
    }
}
~~~

The test above proves the `Supplier.get()` and `Flux` logic: two calls produce two batches; each batch emits two elements and then `onComplete`. **It does not prove that Spring Cloud Stream's poller runs, nor does it prove splitting into broker messages.**

### 13.1. What Should Integration Tests Verify?

With a test binder or real broker, verify at least the following:

1. `spring.cloud.function.definition` selects the right pollable supplier and output binding.
2. After two polls, the source produces two batches with distinct IDs.
3. With `splittable = true`, the two elements in each batch produce the expected number of output messages.
4. With `splittable = false`, the adapter and downstream actually handle the publisher according to the expected contract.
5. `fixed-delay` / per-binding poller settings take effect; count `get()` calls over an appropriate measurement window.
6. When a query fails, no data is erroneously acknowledged or marked complete.
7. When the broker is slow, restarts, or runs with two instances, duplicates do not exceed acceptable bounds.
8. On shutdown, all subscriptions/resources are released.

Do not write tests that sleep exactly 1,000 ms and expect strictly one poll every time: schedulers and binder startup timing can vary. Use bounded wait conditions with finite timeouts and observe actual outcomes.

### 13.2. When to Test with Reactor StepVerifier.withVirtualTime?

`StepVerifier.withVirtualTime` fits when **the Flux itself** creates the schedule, such as `Flux.interval(...)`. It does not automatically drive the Spring Integration poller scheduler. To test an external polling schedule, you need an integration test with the real poller mechanism or a test harness that controls the trigger directly.

## 14. Common Design Mistakes

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Finite supplier emits one batch and goes silent | `@Bean Supplier<Flux<T>>` was subscribed to once | Use `@PollableBean` with a supporting poller adapter, or organize a trigger explicitly |
| Added `@PollableBean` but no polling occurs | App has only Spring Cloud Function Core, with no scheduler/adapter reading the marker | Configure Spring Cloud Stream or an external scheduler |
| Wanted 1 batch sent but received N messages | `splittable` defaults to `true` | Choose an explicit batch payload contract; consider `false` and verify the adapter |
| Set `splittable = false` but consumer cannot understand payload | Publisher was kept intact without matching conversion | Design a DTO payload and matching converter/downstream |
| One poll produces 50 elements despite `maxMessagesPerPoll=1` | Confusing poll count with `onNext` count | Bound batch size at the source; understand version-specific properties |
| Fast polling causes duplicate data | Source keeps re-reading the same records | Use checkpoints/claiming/idempotency |
| An interval source spawns multiple timers | Both self-scheduling inside Flux and being re-invoked by an external poller | Use only one trigger mechanism |
| Broker outage leaves messages inconsistent | Retries, transactions/acks, and checkpoints are out of sync | Redesign delivery boundaries and test failure modes |
| Blocking JDBC calls slow down the poller | Query runs directly in `get()` or subscribe thread | Use reactive repositories or `boundedElastic` with bounds |
| Poller property has no effect | Wrong version prefix, wrong binding name, or missing Stream binder | Check version docs, binding logs, and integration tests |
| Direct bean test PASSES but broker receives nothing | Unit test did not verify trigger/split/binder | Add integration tests with a real adapter |

## 15. Workflow for Selecting the Right Mechanism

~~~mermaid
flowchart TD
    START["Source needs to emit data"] --> Q{"Self-emits continuously\nafter subscription?"}
    Q -->|Yes| LIVE["Supplier<Flux<T>>\nwith standard @Bean"]
    Q -->|No, finite batches| BATCH{"Who owns the invocation schedule?"}
    BATCH -->|Spring Cloud Stream| POLL["@PollableBean\n+ poller configuration"]
    BATCH -->|Cron, serverless, external app| EXT["External trigger\n+ call Supplier/Function"]
    POLL --> SPLIT{"Desired output unit?"}
    SPLIT -->|Each element| TRUE["splittable=true\n(default value)"]
    SPLIT -->|One batch or raw publisher| FALSE["splittable=false if adapter supports;\nor use explicit batch DTO"]
    LIVE --> VERIFY["Verify lifecycle, errors,\nbackpressure, and idempotency"]
    EXT --> VERIFY
    TRUE --> VERIFY
    FALSE --> VERIFY
~~~

Before deploying, answer five questions with concrete facts:

- **Source:** at most how many records should one poll read, and from where?
- **Trigger:** which component owns the invocation schedule, and which version's configuration applies?
- **Output:** is each element a separate message, or is the entire batch one message?
- **Reliability:** where do checkpoints, retries, idempotency, and delivery acknowledgments live?
- **Lifecycle:** how are overlaps, errors, shutdown, and multiple instances controlled?

Once you can answer these questions and test both the logic and the adapter, `@PollableBean` becomes a clean way to express intent without coupling business logic to a protocol.

## 16. Self-Assessment Questions

1. Why does a `Supplier<Flux<T>>` returning `Flux.just(...)` usually need to be re-invoked, whereas a `Supplier<Flux<T>>` returning `Flux.interval(...)` does not necessarily need per-tick polling?
2. If one `get()` call returns `Flux.just("A", "B", "C")` with `splittable=true`, what can the corresponding `get()` call count and output message count be?
3. Does placing `@PollableBean` in an application using only Spring Cloud Function Core cause a scheduler to appear? Which component must provide that?
4. Why does `splittable=false` not guarantee that downstream receives a JSON array of all elements?
5. Does `maxMessagesPerPoll=1` mean at most one `T` is emitted from each `Flux<T>`?
6. If the database returns the same record across two polls, does the annotation automatically deduplicate it? What do you need to add?
7. What is the risk of using both `@PollableBean` and `Flux.interval(...)` in the same supplier?
8. Why is a passing `StepVerifier` unit test insufficient to confirm that the poller and broker sent the expected number of messages?
9. What differs when running the same supplier via an HTTP request, a serverless schedule, or a Spring Cloud Stream binding?

## 17. References

- [Spring Cloud Function — Programming model, Supplier and PollableBean](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Suppliers and Polling Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)

The examples align with modern Spring Cloud Function/Spring Cloud Stream releases; exact property names and how postprocessors/binders handle publishers must be verified against your **actual library version**. The official documentation above is the starting point for confirming version-specific differences.

**Key takeaway:** `@PollableBean` marks a reactive supplier that may need to **be invoked repeatedly to fetch finite Flux batches**, yet **Spring Cloud Function Core does not poll on its own**. `splittable=true` instructs a supporting integration layer to split each element into a message; `false` keeps the publisher intact from that splitting step and requires an appropriate downstream contract. The **external poller** is what decides when to trigger, while the application itself must design batch limits, error handling, deduplication, checkpoints, and message delivery reliability.
