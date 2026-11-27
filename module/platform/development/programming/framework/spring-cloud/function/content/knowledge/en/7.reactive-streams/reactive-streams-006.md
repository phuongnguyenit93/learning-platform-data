# Function<Flux<T>, Mono<Void>> for Asynchronous Processing Without Returning Data

## 1. The Problem: Completing Work Without Returning a Payload

A service receiving order events and recording an audit trail may not need to produce a response record for every event. However, the system still needs to know **whether writing succeeded or failed**. These are two separate questions:

- Do we need to **return business data**? For example, a `Decision`, `Receipt`, or `OrderSummary`.
- Do we need to **propagate a completion or error signal**? For example, simply reporting that all write operations finished.

In **Spring Cloud Function**, functionality can be packaged using Java's `Supplier`, `Function`, and `Consumer`, looked up via `FunctionCatalog`, composed, and exposed with the same logic over HTTP, event binders, or serverless. With Reactor, the signature:

~~~java
Function<Flux<OrderEvent>, Mono<Void>>
~~~

lets you describe an asynchronous workflow that consumes multiple `OrderEvent` items and **emits no output payload**, yet still returns a publisher signaling **`onComplete` or `onError`**.

Conceptual example:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> audit =
    orders -> orders
        .concatMap(order -> auditStore.append(order)) // Mono<Void>
        .then();
~~~

This is a function taking **one input publisher**. For each element, it chains an asynchronous write operation into the pipeline. `then()` creates a `Mono<Void>` that completes when upstream finishes, or terminates with an error if upstream fails. For the work to actually run, **the caller or adapter must subscribe to the returned publisher**.

Key takeaway:

> **“Returning no data” does not mean “no need to wait for the outcome.”** `Mono<Void>` is still an asynchronous contract with completion/error signals and cancellation support.

### Learning Objectives

After this lesson, you will be able to:

1. Explain accurately what `Function<Flux<T>, Mono<Void>>`, `Mono<Void>`, and `then()` mean.
2. Contrast a publisher-returning function with a `void`-returning `Consumer<Flux<T>>`.
3. Use `concatMap` or `flatMap` to await asynchronous operations per element.
4. Choose the right placement for error handling, retries, timeouts, and cancellation based on business rules.
5. Understand the limitations of this signature regarding long-lived streams, message acknowledgments, and transactions.
6. Write Reactor tests verifying side effects, completion, errors, and lazy behavior.
7. Know what to verify when exposing the function over HTTP, events, or serverless.

## 2. Reading the Function<Flux<T>, Mono<Void>> Signature Properly

Java `Function<I,O>` has the method:

~~~java
@FunctionalInterface
public interface Function<I, O> {
    O apply(I input);
}
~~~

In this lesson, `I = Flux<T>` and `O = Mono<Void>`:

| Component | Meaning |
| --- | --- |
| `Function<...>` | Function accepting one input and returning one result when `apply(...)` is called |
| `Flux<T>` | Publisher emitting 0 to N `T` elements per subscription |
| `Mono<Void>` | Publisher emitting no business value, only signaling completion or error |
| `apply(flux)` | Java call constructing the publisher describing the task; does not necessarily process any `T` yet |
| `subscribe()` | Starts consuming the publisher, triggering the operator chain per Reactor semantics |
| `onComplete` | Normal completion signal of the publisher |
| `onError` | Error termination signal; no `onComplete` follows |

Here `Void` is Java's type representing **no result value**. Neither a `Void` instance nor `null` is ever emitted via `onNext`: Reactor forbids emitting `null`.

### 2.1. Distinguishing Mono<Void> from void

~~~java
// No return value for the caller to manage.
Consumer<Flux<OrderEvent>> c = orders -> {
    // accept(...) returns void
};

// Returns a publisher representing the processing.
Function<Flux<OrderEvent>, Mono<Void>> f = orders ->
    orders.then();
~~~

`Consumer.accept` returns as soon as **the Java body of the function** ends. If the consumer launches asynchronous I/O inside via `subscribe()`, `accept` can return `void` before the work finishes. The caller has no returned publisher to track.

By contrast, `Function.apply` returns `Mono<Void>`, and the caller/adapter can subscribe, await completion, receive errors, or cancel the subscription. **Being observable** does not mean every framework automatically awaits it and applies acknowledgments at the right moment: that still depends on the adapter.

### 2.2. Mono.empty(), Mono<Void>, and Signal Value

~~~java
Mono<Void> alreadyDone = Mono.empty();

Mono<Void> failed =
    Mono.error(new IllegalStateException("Cannot persist order"));

Mono<Void> delayed =
    Mono.delay(Duration.ofMillis(200)).then();
~~~

- `alreadyDone`, when subscribed, completes without emitting any element.
- `failed` emits `onError`.
- `delayed` waits for a timed publisher and then only signals completion.

`Mono<Void>` does not mean the operation has already run successfully before being returned. It may still be *waiting to be subscribed to*.

## 3. then(): Turning a Pipeline into a Completion Signal

The `then()` operator ignores `onNext` values from upstream while **still subscribing to upstream** and tracking its terminal signal:

~~~java
Mono<Void> completion = Flux.just("A", "B", "C")
    .map(String::trim)
    .then();
~~~

When subscribed, upstream still processes `A`, `B`, and `C`. However, `completion` does not emit those strings: it only emits `onComplete` once upstream completes normally.

~~~mermaid
flowchart LR
    SOURCE["Flux<T> emits A, B, C"] --> OPERATORS["Operators process each T"]
    OPERATORS --> THEN["then()"]
    THEN --> RESULT["Mono<Void>"]
    RESULT --> OK["onComplete"]
    RESULT --> ERR["onError"]
~~~

`then()` does **not** mean “skip processing upstream.” It only discards the **output values**. Upstream errors still propagate to the result, and cancellation still affects the subscription.

### 3.1. Do Not Confuse then() with doOnNext()

~~~java
Function<Flux<String>, Mono<Void>> logs = input ->
    input
        .doOnNext(System.out::println)
        .then();
~~~

Here `doOnNext` runs a **synchronous side effect** for each element. `then()` simply emits the final completion signal. This works for quick logging, but if you want to perform **asynchronous** writes, `doOnNext` is the wrong tool.

Broken example when a write library returns `Mono<Void>`:

~~~java
// Wrong: creates an inner Mono and discards the publisher; the write is not awaited.
Function<Flux<OrderEvent>, Mono<Void>> wrong = events ->
    events
        .doOnNext(event -> auditStore.append(event))
        .then();
~~~

`auditStore.append(event)` may return a cold publisher with no subscriber, so the data may never be written. You must **chain the inner publisher into the pipeline** using `concatMap` or `flatMap`.

### 3.2. Related then Variants

| Operator | Main behavior | Result |
| --- | --- | --- |
| `flux.then()` | Waits for upstream completion, drops `onNext` | `Mono<Void>` |
| `flux.thenReturn(value)` | Waits for upstream completion, then emits a fixed value | `Mono<R>` |
| `flux.then(mono)` | Waits for upstream completion, then subscribes to `mono` | `Mono<R>` |
| `flux.collectList()` | Collects all elements when the stream completes | `Mono<List<T>>` |
| `flux.ignoreElements()` | Ignores elements, keeps only terminal signal | `Mono<T>` with no value |

`collectList()` requires memory for all elements and must wait for the stream to end. For the use case “persist each event then signal done,” `then()` is usually more direct and avoids buffering payloads.

## 4. Complete Example: Asynchronous Order Auditing

Suppose an application receives `OrderEvent` items and must write them to an audit store with a reactive API. There is no requirement to emit an output message per order. The configuration class below uses Java 17+ (for `record`), Spring Cloud Function/Spring Framework, and Reactor.

~~~java
package demo.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderAuditConfiguration {

    public record OrderEvent(String orderId, long amountCents) {}

    // A record is saved once the Mono returned by append emits onComplete.
    public interface AuditStore {
        Mono<Void> append(OrderEvent order);
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Void>> auditOrders(
            AuditStore auditStore) {

        return incoming -> incoming
            .concatMap(auditStore::append)
            .then();
    }
}
~~~

### 4.1. Step-by-Step Pipeline Execution

Suppose a caller supplies two orders:

~~~java
Flux<OrderAuditConfiguration.OrderEvent> input = Flux.just(
    new OrderAuditConfiguration.OrderEvent("ORD-101", 12_000),
    new OrderAuditConfiguration.OrderEvent("ORD-102", 15_000)
);

Function<
    Flux<OrderAuditConfiguration.OrderEvent>,
    Mono<Void>
> function = configuration.auditOrders(auditStore);

Mono<Void> completion = function.apply(input);
~~~

Above, `configuration` and `auditStore` are dependencies instantiated in the application/test. After `apply`, the `completion` variable describes the write operation; it does not yet prove that both orders have been saved.

Once a subscriber subscribes:

1. `concatMap` receives `ORD-101` and subscribes to `auditStore.append(ORD-101)`.
2. When the first operation completes, `concatMap` proceeds to `ORD-102`.
3. When the second operation completes and `input` emits `onComplete`, `then()` completes.
4. If either operation emits an unhandled `onError`, the resulting publisher also emits `onError`.

Sequence diagram:

~~~mermaid
sequenceDiagram
    participant Caller as Caller / adapter
    participant F as auditOrders
    participant Flux as Input Flux
    participant Store as AuditStore

    Caller->>F: apply(input)
    F-->>Caller: Mono<Void>
    Caller->>F: subscribe(result)
    F->>Flux: subscribe input
    Flux-->>F: onNext(ORD-101)
    F->>Store: append(ORD-101)
    Store-->>F: onComplete
    Flux-->>F: onNext(ORD-102)
    F->>Store: append(ORD-102)
    Store-->>F: onComplete
    Flux-->>F: onComplete
    F-->>Caller: onComplete (no payload)
~~~

**Assumption of the example:** `AuditStore.append` must return a publisher that signals success only after the write has finished as required by business rules. If the API emits `onComplete` before data is durably committed, the function's `Mono<Void>` cannot elevate that guarantee on its own.

### 4.2. Why concatMap Instead of map?

~~~java
// Does not execute the inner Mono as intended:
Flux<Mono<Void>> nested = input.map(auditStore::append);

// Chains the operation into the pipeline and awaits each Mono:
Mono<Void> done = input
    .concatMap(auditStore::append)
    .then();
~~~

In the first form, `map` merely emits the **`Mono` object** as an element of `Flux<Mono<Void>>`. `concatMap` actually subscribes to each inner publisher, bringing write completions and errors into the main stream.

### 4.3. What About Empty Input?

~~~java
Mono<Void> emptyBatch = function.apply(Flux.empty());
~~~

Upon subscription, if there are no records, `concatMap` never calls `AuditStore.append`, and `then()` completes. This is valid when “no data” is a legitimate outcome. If business rules require at least one event, add validation or an operator that errors on empty streams.

## 5. Choosing concatMap vs. flatMap for Asynchronous Writes

When per-element I/O returns a publisher, choose the operator based on **ordering, parallelism, and load limits**.

| Operator | Active inner tasks | Processing order | When to use |
| --- | --- | --- | --- |
| `concatMap(mapper)` | Sequential, one inner publisher at a time | Guarantees no two inner tasks overlap within the pipeline | Events sharing a key must be written sequentially, or to keep state simple |
| `flatMap(mapper, concurrency)` | Multiple concurrent inner publishers, bounded | Completion order may differ from input order | Independent I/O where higher throughput is desired |
| `flatMapSequential(mapper, concurrency)` | Concurrent execution, preserves emission order | Does not guarantee **external side effects** finish in order | Result order matters, while inner tasks may run concurrently |

With `Mono<Void>`, there are no inner output values to reorder. Therefore, **never choose `flatMapSequential` expecting database writes to commit strictly in order**.

### 5.1. Running Up to Eight Operations Concurrently

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditInParallel(
        AuditStore auditStore) {

    return incoming -> incoming
        .flatMap(auditStore::append, 8)
        .then();
}
~~~

This is an alternative to the `auditOrders` bean in Section 4; if both exist in the same application, configure function/definition names explicitly. One `apply` builds the pipeline; once subscribed, up to eight inner publishers are subscribed to concurrently inside this operator.

Note:

- Operations may complete out of input order.
- Concurrency only limits inner publishers within one subscription to this operator; if multiple calls or multiple instances run concurrently, total load is higher.
- Even with bounded `flatMap`, the database/HTTP client still needs proper connection pools, timeouts, and load policies.
- For the same business key (e.g., an `orderId`), sequential state updates may still require `concatMap` or key-based partitioning.

### 5.2. Never Block Threads to Wait for I/O

Common mistake:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> blocking = incoming ->
    incoming
        .doOnNext(order -> auditStore.append(order).block())
        .then();
~~~

`block()` turns the call into a synchronous wait and can stall the event loop; furthermore, multiple subscriptions can re-run upstream work.

For JDBC or truly blocking legacy APIs, consider isolating work on `Schedulers.boundedElastic()`:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> legacyAudit = incoming ->
    incoming
        .concatMap(order ->
            Mono.fromRunnable(() -> legacyStore.appendBlocking(order))
                .subscribeOn(
                    reactor.core.scheduler.Schedulers.boundedElastic()
                )
        )
        .then();
~~~

This example assumes `legacyStore.appendBlocking` returns `void`. `boundedElastic` shifts blocking tasks to a dedicated thread pool; **it does not turn a blocking library into a non-blocking one**. You still must manage concurrency, connections, and timeouts.

## 6. Why Is Function<Flux<T>, Mono<Void>> Usually Better Than Consumer<Flux<T>>?

An explicit reactive consumer can be written as:

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditConsumer(AuditStore store) {
    return incoming -> incoming
        .concatMap(store::append)
        .subscribe(
            ignored -> {},
            error -> log.error("Audit stream failed", error)
        );
}
~~~

The issue here is that `Consumer.accept` returns `void`, while the `Disposable` from `subscribe` is discarded. The caller has no result representing the asynchronous task and does not own cancellation. Logging an error internally does not tell the framework that the batch failed.

By contrast:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditFunction(AuditStore store) {
    return incoming -> incoming
        .concatMap(store::append)
        .then();
}
~~~

returns a publisher that the caller/adapter can subscribe to and manage. The function **does not call `subscribe()` itself**; it expresses processing as a pipeline.

| Criterion | Self-subscribing `Consumer<Flux<T>>` | `Function<Flux<T>, Mono<Void>>` |
| --- | --- | --- |
| Java return type | `void` | `Mono<Void>` |
| Completion contract | Mostly inside internal callbacks/handles | Emitted via the returned publisher |
| Error reporting | Consumer must catch and handle inside its own subscription | `onError` can propagate to the caller |
| Cancellation | Consumer must manage the `Disposable` | Caller can cancel the output subscription |
| Composition | Acts as a terminal step returning `void` | Returns a terminal publisher, able to participate in compatible compositions |
| Emits business payload | No | No |
| Exactly-once broker ack | Not guaranteed automatically | Not guaranteed automatically |

**Valid cases for `Consumer<Flux<T>>` still exist**, such as an adapter mandating a consumer signature or a consumer owning a long-lived connection and managing its own lifecycle. In those cases, manage the `Disposable`, errors, cancellation, resources, and recovery explicitly.

### 6.1. Fire-and-Forget Breaks the Completion Contract

Another anti-pattern:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> misleading = input -> {
    input.subscribe(order -> auditStore.append(order).subscribe());
    return Mono.empty();
};
~~~

This function signals `Mono.empty()` completion almost immediately, while write tasks run detached from the pipeline. Errors, cancellation, and write durability are severed from the result. It also creates **nested subscriptions** with unbounded concurrency.

**Rule:** if the caller needs to await or observe the outcome of an asynchronous task, *return a publisher representing that task* and compose inner publishers, instead of subscribing in the background and returning `Mono.empty()`.

## 7. Single-Record Errors vs. Stream-Wide Errors

In Reactive Streams, `onError` is a **terminal** signal for the subscription. If an `append` fails and is not handled, the pipeline terminates and `then()` forwards the error to the subscriber.

### 7.1. Fail-Fast Policy

~~~java
Function<Flux<OrderEvent>, Mono<Void>> failFast = incoming ->
    incoming
        .concatMap(auditStore::append)
        .then();
~~~

If the second order fails, the third order may not be processed. This makes sense when an error requires halting, such as when ordering or consistency cannot be preserved.

### 7.2. Handling Errors Independently Per Element

If business rules allow sending failed records to a dead-letter store and **continuing** with subsequent elements:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> withDeadLetter = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .onErrorResume(error ->
                    deadLetterStore.append(order, error)
                )
        )
        .then();
~~~

Suppose `deadLetterStore.append(order, error)` returns `Mono<Void>` and completes only once the failure record is saved. When the audit write fails, the pipeline switches to writing to the dead-letter store. If dead-letter persistence also fails, the error still propagates outward. This policy avoids silently dropping data without a trace.

Whether to continue or halt must follow business rules. For payments, authorizations, or strictly ordered events, a single failed element may require stopping the entire stream. Avoid defaulting to `onErrorResume(... -> Mono.empty())` to swallow all errors.

### 7.3. Why an Outermost onErrorResume Does Not Continue the Rest

~~~java
Mono<Void> hidden = incoming
    .concatMap(auditStore::append)
    .then()
    .onErrorResume(error -> Mono.empty());
~~~

Here an upstream error already terminated the subscription. The outer `onErrorResume` replaces the error with successful completion; it **does not resume consuming elements canceled from the source stream**. It also misleads the caller into seeing success even though not every element was processed. To handle errors per order, place the policy inside each order's inner publisher.

### 7.4. Timeouts on Inner Operations

~~~java
Function<Flux<OrderEvent>, Mono<Void>> boundedWrite = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .timeout(Duration.ofSeconds(3))
        )
        .then();
~~~

`timeout` inside `concatMap` applies to **each individual write**. To bound total duration for **an entire batch**, place `timeout` after `then()`:

~~~java
Mono<Void> batch = boundedWrite.apply(finiteInput)
    .timeout(Duration.ofSeconds(30));
~~~

On timeout, Reactor normally cancels the upstream subscription, but you cannot assume the external transaction rolled back; a write may have completed at the destination service even though the subscriber never received the response.

## 8. Retries, Duplicates, and Idempotency

If you add retry at the end of the entire pipeline:

~~~java
Mono<Void> retryAll = incoming
    .concatMap(auditStore::append)
    .then()
    .retry(2);
~~~

`retry(2)` re-subscribes to upstream on error, up to two retries. With a cold publisher, elements already emitted and written before the failure **may be emitted and written again**. If the input is hot or comes from a broker, replay behavior also depends on the adapter/source.

For order persistence, retrying an operation with non-idempotent side effects is unsafe. Strategies include:

- Giving each event a unique `eventId`; inserting with a unique constraint or upserting by ID.
- Writing audit logs and updating state inside an appropriate transaction.
- Using bounded retries, backoff, and classification of transient errors.
- Advancing checkpoints/offsets only after a clearly defined durable milestone.
- Routing exhausted records to a dead-letter store or reconciliation workflow.

A *per-element* retry pattern, assuming the write is idempotent:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> retryEach = incoming ->
    incoming
        .concatMap(order ->
            auditStore.append(order)
                .retryWhen(
                    reactor.util.retry.Retry.backoff(
                        2, Duration.ofMillis(200)
                    )
                )
        )
        .then();
~~~

This avoids re-subscribing to the **entire** input just because one write failed, though it can still attempt to write the same `order` multiple times. Idempotency at the storage layer remains mandatory.

## 9. Finite vs. Continuous Streams: When Does Mono<Void> Complete?

The `Function<Flux<T>, Mono<Void>>` signature can accept both finite and continuous sources, yet the meaning of **completion** changes dramatically.

### 9.1. Finite Stream: Batch Completion

~~~java
Flux<OrderEvent> batch = Flux.just(firstOrder, secondOrder);

Mono<Void> completed = auditOrders.apply(batch);
~~~

Only once the batch emits all elements, all inner operations complete, and no errors occur does `completed` emit `onComplete`. This makes it a sound choice for **synchronizing a batch of events** or handling a finite HTTP invocation.

### 9.2. Continuous Stream: Per-Task Completion Without Stream Termination

~~~java
Flux<OrderEvent> continuous = eventSource.flux();

Mono<Void> lifetime = auditOrders.apply(continuous);
~~~

If `eventSource.flux()` never emits `onComplete`, `lifetime` **never emits successful completion** while the stream stays alive. However, each individual `auditStore.append(order)` call still completes as events arrive.

**Important consequence:** Never treat the pipeline-wide terminal `Mono<Void>` as proof of completion for **each individual message** in a continuous source. Completion applies to the stream/batch lifecycle; it does not provide per-message acknowledgment.

### 9.3. Breaking Long-Lived Streams into Finite Chunks

When completion is needed per window, you can chunk by count and produce a completion result per window:

~~~java
Function<Flux<OrderEvent>, Flux<Long>> auditInBatches = source ->
    source
        .buffer(100)
        .concatMap(batch ->
            Flux.fromIterable(batch)
                .concatMap(auditStore::append)
                .thenReturn((long) batch.size())
        );
~~~

Here `buffer(100)` emits full batches of 100 elements; a final partial batch is emitted only when upstream completes. `thenReturn` emits the batch size **after all writes in that batch finish**. This function **produces results** rather than a single stream-wide `Mono<Void>`, illustrating how the contract shifts when repeated completion signals are needed on a long-lived source.

If batches must flush on a time interval even when not full, consider `bufferTimeout`. Evaluate memory usage, timeouts, error behavior, and per-batch commit semantics.

## 10. Subscription, Cancellation, and Consumption

### 10.1. Who Is Responsible for Subscribing?

Standard pattern:

~~~java
Mono<Void> result = auditOrders.apply(input);

// In a unit test: StepVerifier subscribes and observes the terminal signal.
StepVerifier.create(result).verifyComplete();
~~~

In Spring Cloud Function, `FunctionCatalog` supplies the function for an adapter to invoke. With publisher-returning functions, **the caller/adapter must subscribe and manage the subscription** so the work runs. Do not call `subscribe()` inside the function body just to trigger data flow.

If a caller truly needs to run manually:

~~~java
Disposable subscription = result.subscribe(
    ignored -> {},
    error -> logger.error("Audit failed", error),
    () -> logger.info("Audit completed")
);
~~~

`Disposable` is the handle used to cancel the subscription; the `ignored` handler receives no `Void` value from `Mono<Void>`. In production code, retain the handle or manage it through an appropriate lifecycle/container; never fire-and-forget a subscription on a long-lived stream.

### 10.2. Cancellation Is a Separate Signal from Completion

~~~java
Mono<Void> monitored = auditOrders.apply(input)
    .doFinally(signalType ->
        metrics.recordTermination(signalType.name())
    );
~~~

`doFinally` observes `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. When the caller cancels the subscription, there is no guarantee that all in-flight operations have finished. Cancellation also does not automatically roll back external I/O operations.

### 10.3. Backpressure and Concurrency Limits

Incoming streams may emit faster than writes can keep up. Reactor supports backpressure via `request(n)`; `concatMap` and `flatMap(concurrency)` manage demand in their own ways. However:

- Backpressure inside Reactor does not automatically throttle a message broker or SDK that ignores demand.
- Large or unbounded buffers can inflate memory usage.
- `flatMap(..., 8)` limits inner tasks within one pipeline, not total load across multiple instances.
- Avoid `onBackpressureDrop()` for events that must all be persisted, unless a recovery/compensation path exists.
- Monitor write latency, error counts, queue depths, and per-batch processing duration.

## 11. What Counts as “No Data Returned”?

`Mono<Void>` emits no payload, yet business requirements sometimes genuinely need a result such as an error code, processed count, or correlation ID. In those cases, **do not force all state into completion signals**.

### 11.1. No Payload Needed, Only Success/Failure

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persist = events ->
    events.concatMap(auditStore::append).then();
~~~

Fits when the caller needs to await the whole batch and errors are represented by `onError`.

### 11.2. Need to Return the Number of Saved Records

~~~java
Function<Flux<OrderEvent>, Mono<Long>> persistAndCount = events ->
    events
        .concatMap(order ->
            auditStore.append(order).thenReturn(1L)
        )
        .reduce(0L, Long::sum);
~~~

This function emits a `Mono<Long>` upon batch completion equal to the count of successful appends. On an infinite stream, `reduce` waits forever for completion. If “received from upstream” differs from “durably committed,” design counting accurately.

### 11.3. Need to Emit Results Per Element

~~~java
Function<Flux<OrderEvent>, Flux<AuditResult>> persistAndReport =
    events -> events.concatMap(order ->
        auditStore.append(order)
            .thenReturn(new AuditResult(order.orderId(), true))
    );
~~~

`AuditResult` is a hypothetical DTO. Returning `Flux<AuditResult>` lets downstream observe the outcome of each event; however, an unhandled error can still stop the whole stream. Match the signature to output requirements and avoid `Mono<Void>` when callers actually need granular feedback.

## 12. FunctionCatalog and Composition of Void-Returning Functions

In Spring Cloud Function, `FunctionCatalog` looks up beans and composes compatible functions. Example separating validation from audit persistence:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validOrders() {
    return orders -> orders.filter(order -> order.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Mono<Void>> auditOrders(AuditStore store) {
    return orders -> orders.concatMap(store::append).then();
}
~~~

If the adapter/version supports the corresponding composition, you can configure:

~~~properties
spring.cloud.function.definition=validOrders|auditOrders
~~~

`validOrders` filters each element and passes `Flux<OrderEvent>` to `auditOrders`, which returns `Mono<Void>`. Because the final result **carries no payload**, this composition is essentially a **terminal side-effect pipeline**.

Do not assume you can chain another business-data function accepting `OrderEvent` **after** `auditOrders`: the output is no longer `Flux<OrderEvent>`. If further transformations or message forwarding are needed, keep the pipeline returning `Flux<R>` or design a concrete result type.

### 12.1. Can It Be Reused Across HTTP, Brokers, and Serverless?

The Java logic in `auditOrders` has no knowledge of HTTP, message binders, or serverless. That is the core value of Spring Cloud Function. Still, adapters **differ in invocation boundaries and publisher handling**:

| Environment | What to verify with `Mono<Void>` |
| --- | --- |
| Direct Java / `FunctionCatalog` call | Caller must subscribe and decide how to await completion/errors |
| HTTP adapter | Response may have no body; check whether the adapter awaits publisher completion before sending status |
| Spring Cloud Stream | Reactive function may receive a long-lived `Flux`; `Mono<Void>` output produces no payload messages |
| Serverless adapter | Invocations are time-bounded; use finite sources and know how long the runtime awaits the publisher |
| Batch job | `Mono<Void>` is a useful signal for whole-batch completion, but does not replace checkpoints or transactions |

Never assume a function returning `Mono<Void>` causes a binder to **acknowledge each message right after the write**. Delivery, errors, retries, offsets, and acknowledgments belong to the adapter/binder; a stream-oriented reactive function may be invoked **once for the entire publisher**, not once per message.

### 12.2. HTTP Status Does Not Reflect Every Completion Semantics

A web adapter may turn completion into an empty-body response, though the exact HTTP status depends on the adapter and error handling. If a function is called with an infinite `Flux` input, an HTTP request awaiting `Mono<Void>` completion can hang or time out. Therefore, for “submit a batch and get an acknowledgment” endpoints, establish clear finite-source boundaries and timeout policies.

### 12.3. Message Conversion and Metadata

If events carry a correlation ID, routing key, or event ID, the input can be `Flux<Message<OrderEvent>>`:

~~~java
Function<Flux<Message<OrderEvent>>, Mono<Void>> auditMessages =
    messages -> messages
        .concatMap(message ->
            auditStore.appendWithId(
                message.getPayload(),
                message.getHeaders().get("eventId")
            )
        )
        .then();
~~~

`appendWithId(...)` is a hypothetical API returning `Mono<Void>`; `Message` is `org.springframework.messaging.Message`. The `eventId` header serves as a business idempotency key. If the framework converts payloads or the binder alters headers, test actual metadata behavior in each adapter.

**There is no `Message<?>` output** when returning `Mono<Void>`. If downstream needs each event's correlation ID to build a response message, choose a function with a corresponding output type.

## 13. Testing with StepVerifier: Asserting the Right Signals

`reactor-test` provides `StepVerifier` to subscribe to a publisher and assert signal counts, completion, or errors. It is the ideal tool for testing `Mono<Void>` since there are no `onNext` values to compare.

### 13.1. Verifying Laziness and That Every Record Was Written

The complete example below uses `OrderAuditConfiguration` from Section 4:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderAuditConfigurationTest {

    @Test
    void waitsUntilAllWritesComplete() {
        AtomicInteger writes = new AtomicInteger();
        OrderAuditConfiguration config = new OrderAuditConfiguration();

        OrderAuditConfiguration.AuditStore store = order ->
            Mono.fromRunnable(writes::incrementAndGet);

        var audit = config.auditOrders(store);

        Flux<OrderAuditConfiguration.OrderEvent> input = Flux.just(
            new OrderAuditConfiguration.OrderEvent("A", 100),
            new OrderAuditConfiguration.OrderEvent("B", 200),
            new OrderAuditConfiguration.OrderEvent("C", 300)
        );

        Mono<Void> completion = audit.apply(input);
        assertEquals(0, writes.get()); // Not subscribed yet.

        StepVerifier.create(completion)
            .verifyComplete();

        assertEquals(3, writes.get());
    }

    @Test
    void propagatesWriteFailure() {
        OrderAuditConfiguration config = new OrderAuditConfiguration();

        OrderAuditConfiguration.AuditStore store = order ->
            "B".equals(order.orderId())
                ? Mono.error(new IllegalStateException("audit failed"))
                : Mono.empty();

        var audit = config.auditOrders(store);

        StepVerifier.create(audit.apply(Flux.just(
                new OrderAuditConfiguration.OrderEvent("A", 100),
                new OrderAuditConfiguration.OrderEvent("B", 200)
            )))
            .expectErrorMessage("audit failed")
            .verify();
    }
}
~~~

In the first test, a cold source and `Mono.fromRunnable` prove that side effects do not happen before subscription. `verifyComplete()` asserts completion rather than `onNext` counts (because `Mono<Void>` emits no values). The second test verifies that repository failures propagate to the caller.

### 13.2. Asserting No Value Is Emitted

~~~java
Mono<Void> completion = Flux.just(1, 2, 3)
    .map(n -> n * 2)
    .then();

StepVerifier.create(completion)
    .expectComplete()
    .verify();
~~~

`expectComplete()` fails if any unexpected `onNext` or `onError` occurs. It accurately expresses the “completion only” contract.

### 13.3. Virtual Time Testing for Delayed Operations

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A", "B")
            .concatMap(s ->
                Mono.delay(Duration.ofSeconds(1)).then()
            )
            .then()
    )
    .thenAwait(Duration.ofSeconds(2))
    .verifyComplete();
~~~

In this `concatMap` example, each simulated operation takes one second, totaling two seconds of virtual time. Create the publisher **inside the factory** passed to `withVirtualTime` so Reactor uses the virtual scheduler; this does not simulate real databases/networks or adapter/binder timers.

### 13.4. Testing Empty Batches and Cancellation

For an empty batch:

~~~java
StepVerifier.create(audit.apply(Flux.empty()))
    .verifyComplete();
~~~

For non-terminating sources, **cancel the subscription** in tests instead of waiting forever for completion:

~~~java
StepVerifier.create(
        Flux.<OrderEvent>never()
            .concatMap(auditStore::append)
            .then()
    )
    .thenCancel()
    .verify();
~~~

`thenCancel()` proves the test can request cancellation; it does **not** prove all external resources or I/O were cleaned up. To verify cleanup, add `doFinally` or integration tests with a real client.

## 14. Common Design Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No database writes appear | Created `Mono<Void>` but caller never subscribed | Return the publisher to the framework/caller and verify subscription |
| Function “succeeds” immediately before writes finish | Called `subscribe()` internally and returned `Mono.empty()` | Chain inner publishers with `concatMap`/`flatMap` and `then()` |
| `Flux<Mono<Void>>` fails to do intended work | Used `map` with a publisher-returning API | Use an appropriate flattening operator |
| Commit order is wrong | `flatMap` runs inner operations concurrently | Use `concatMap` when sequential execution is needed |
| One failed record stops the entire stream | Unhandled `onError` | Choose fail-fast or handle errors inside each inner publisher |
| Data is lost yet completion reports OK | Swallowed errors via `onErrorResume(... -> Mono.empty())` | Only mask errors per approved policy; record dead-letter/metrics |
| Duplicate writes after retry | Re-subscribing a cold publisher or broker redelivery | Use idempotency, transactions, and checkpoints |
| Large batches exhaust resources | Excessive concurrency/buffering | Limit concurrency, paginate, and monitor |
| Continuous stream never emits `onComplete` | `then()` waits for upstream to finish | Chunk into batches/windows if periodic completion is needed |
| HTTP request hangs | Infinite input or operations without timeouts | Design finite invocations, timeouts, and cancellation |
| Broker ack does not align with writes | Equating stream termination with per-message delivery | Verify ack/offset behavior with the actual binder |
| Tests PASS but production does not run | Only tested Reactor without adapter subscription/binding | Add integration tests across HTTP/broker/serverless runtimes |

## 15. Workflow for Choosing the Right Signature

~~~mermaid
flowchart TD
    START["Need to process multiple T events"] --> OUT{"Need to return data after processing?"}
    OUT -->|No| WAIT{"Need to observe completion or errors?"}
    OUT -->|Yes, per element| EACH["Function<Flux<T>,Flux<R>>"]
    OUT -->|Yes, one aggregate result| RESULT["Function<Flux<T>,Mono<R>>"]
    WAIT -->|Yes| VOID["Function<Flux<T>,Mono<Void>>"]
    WAIT -->|No, consumer owns lifecycle| CONS["Consumer<Flux<T>>"]
    VOID --> ASYNC{"Does per-T task return a publisher?"}
    ASYNC -->|Yes| FLAT["concatMap / flatMap + then"]
    ASYNC -->|No, blocking| BLOCK["Reactive adapter or boundedElastic"]
    FLAT --> VERIFY["Verify subscription, errors,\nretry, cancellation, and idempotency"]
    BLOCK --> VERIFY
    CONS --> VERIFY
    EACH --> VERIFY
    RESULT --> VERIFY
~~~

Use the following technical checklist before promoting a function to production:

1. **Unit of processing:** is the input a finite batch or a continuous stream?
2. **I/O:** do APIs used in `concatMap`/`flatMap` genuinely return publishers that complete after commit?
3. **Subscription:** who subscribes to the resulting `Mono<Void>`, and can it be canceled on shutdown/timeout?
4. **Errors:** does one failed event stop the entire stream or go to a dead-letter store and continue?
5. **Duplicates:** can retries, redeliveries, or resubscriptions write the same event multiple times?
6. **Load:** are concurrency, connection pools, item counts, and memory bounded?
7. **Adapter:** does HTTP/broker/serverless handle `Mono<Void>` with the expected completion semantics?
8. **Observability:** do metrics and logs clearly track individual errors, total events, completions, and cancellations?

## 16. Self-Assessment Questions

1. Why is `Mono<Void>` still a useful return type even though it emits no payload?
2. How does `Function<Flux<Order>, Mono<Void>>` differ from `Consumer<Flux<Order>>` in terms of subscription ownership and error observability?
3. Does `then()` skip processing upstream elements, or does it only discard output values?
4. Why does `doOnNext(order -> store.save(order))` fail to ensure that a `Mono<Void>` returned by `save` is executed?
5. When should you pick `concatMap` over `flatMap`? Does `flatMapSequential` guarantee side effects commit in order?
6. Does placing `onErrorResume` after `then()` allow remaining elements in the same subscription to keep running?
7. Why can `retry(2)` cause duplicate writes even though the publisher returns `Mono<Void>`?
8. With a continuous `Flux` that never emits `onComplete`, will the pipeline-wide `Mono<Void>` ever complete normally?
9. Why does subscribing to or completing `Mono<Void>` not automatically guarantee the message broker acknowledged each message?
10. How would you use `StepVerifier` to prove that operations have not run before subscription and have completed after subscription?
11. When should `Mono<Void>` be replaced by `Mono<BatchSummary>` or `Flux<AuditResult>`?
12. Why are adapter integration tests still necessary even when Reactor unit tests pass?

## 17. Recommended Reading

- [Spring Cloud Function: Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — function bean forms and reactive signatures.
- [Spring Cloud Stream: Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive Consumers, bindings, and stream processing boundaries.
- [Project Reactor: Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Mono`, `Flux`, operators, and backpressure.
- [Project Reactor: Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` and virtual time.

Always cross-check against the deployed versions of Spring Cloud Function, Spring Cloud Stream, and your binder. How adapters track publishers, acknowledge messages, or translate errors into responses is not necessarily uniform across versions and environments.

**Key takeaway:** `Function<Flux<T>, Mono<Void>>` is a contract for **asynchronous processing that returns no business payload yet still delivers completion/error signals**. Chain inner tasks with `concatMap` or `flatMap`, end with `then()`, and return the publisher so the caller/adapter manages the subscription. For finite batches, completion can represent whole-batch completion under the publisher contract; for continuous streams, completion is not per-message acknowledgment. Durability, retries, idempotency, and acknowledgments must still be designed at real system boundaries.
