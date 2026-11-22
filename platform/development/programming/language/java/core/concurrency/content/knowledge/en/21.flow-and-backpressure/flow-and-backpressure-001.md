# Flow API in java.util.concurrent

## 1. What Problem Does Flow Solve?

When a component produces data faster than the downstream component can process it, pushing data unconditionally can cause queues to grow unboundedly, increase memory usage, slow down the system, or exhaust the heap. **Backpressure** is a mechanism for the receiver to signal its capacity to accept data, allowing the sender to regulate the number of items it emits.

Since **Java 9**, Java provides `java.util.concurrent.Flow`: a set of foundational interfaces for a **demand-controlled Publisher–Subscriber** model. Flow defines the contract for transmitting data signals, completion, errors, and the subscription/demand request mechanism; it does not automatically turn every piece of processing into a non-blocking system, does not provide hundreds of transformation operators, and does not decide how data is stored on behalf of the application.

Flow is useful when building asynchronous pipelines between producers and consumers, processing event streams, connecting processing stages running at different speeds, and learning Reactive Streams principles. This content focuses on **general Java concurrency** and JDK classes, without depending on external frameworks.

### Core Mental Model

Instead of a producer calling `consumer.accept(item)` without rate control, a subscriber can state: **“I am ready to receive n more items.”** The publisher may only emit `onNext` within the unfulfilled demand limit of that subscription.

```text
                  subscribe(subscriber)
  Publisher --------------------------------> Subscriber
             onSubscribe(subscription)
            <--------------------------------
                 request(2)
            <--------------------------------
                   onNext(A)
            -------------------------------->
                   onNext(B)
            -------------------------------->
                 request(1)
            <--------------------------------
                   onNext(C)
            -------------------------------->
           onComplete() or onError(error)
            -------------------------------->
```

The arrows represent the **logical flow of signals**; they do not require every callback to run on a separate thread or on the same thread—that depends on the implementation.

## 2. The Four Core Interfaces

| Interface | Role | Key Methods |
| --- | --- | --- |
| `Flow.Publisher<T>` | Source that emits items of type `T` to subscribers | `subscribe(Subscriber<? super T>)` |
| `Flow.Subscriber<T>` | Receiver of data that determines demand and handles events | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Link between a publisher and a subscriber; carries demand/cancel signals | `request(long n)`, `cancel()` |
| `Flow.Processor<T,R>` | Both a subscriber receiving `T` and a publisher emitting `R`, capable of transforming/filtering data | Extends `Subscriber<T>` and `Publisher<R>` |

### Publisher

`Publisher.subscribe(...)` registers a subscriber. After a valid registration, the subscriber is given a `Subscription` object via `onSubscribe`. A publisher may have one or more subscribers; policies for replay, multicasting, buffering, and starting emission are determined by the implementation—**do not assume that every publisher records history for late subscribers to replay**.

### Subscriber and the Four Signals

A subscriber has a typical lifecycle:

1. **`onSubscribe(subscription)`**: receives the subscription link; usually stores the subscription and calls `request(n)`. Without requesting, it has no right to receive new items.
2. **`onNext(item)`**: processes a requested item; may request additional items after finishing processing.
3. **`onError(throwable)`**: terminates due to an error; no further normal signals follow a terminal signal.
4. **`onComplete()`**: terminates normally when the source has no more items; no further `onNext` calls follow.

For a single subscription, signal calls to the subscriber are strictly ordered and guarantee a *happens-before* relationship, even though the implementation may use multiple different threads. Do not infer a total ordering across **different subscriptions**.

### Subscription

`request(n)` **adds** `n` to the unfulfilled demand; it does not reset demand to `n`. For a positive `n`, the publisher may call `onNext` up to `n` additional times according to the accumulated demand; each `onNext` consumes one unit. If `n <= 0`, the subscriber must receive an `onError` signal with `IllegalArgumentException`. The value `Long.MAX_VALUE` is typically treated as effectively unbounded demand.

`cancel()` requests stopping data delivery on a **best-effort** basis: already-scheduled signals may still arrive after cancellation, and a cancelled subscriber is not guaranteed to receive `onComplete`/`onError`. Therefore, cancellation does not mean all work in the system stops immediately.

### Processor

`Processor<T,R>` both receives input signals and emits output. A pipeline:

```text
Publisher<Integer>
    |
    v
Processor<Integer, String>  (converts integers to strings)
    |
    v
Subscriber<String>
```

A well-behaved processor must manage **demand on both sides**: it must not accept unbounded upstream data if downstream cannot keep up, unless it has a controlled buffering/dropping strategy of its own. `Flow.Processor` is an interface; **it does not automatically perform map/filter operations or propagate backpressure**.

## 3. How Does Backpressure Work?

Suppose a subscriber starts with `request(2)`:

| Time | Action | Remaining Demand |
| --- | --- | --- |
| Initial | `onSubscribe`, `request` not yet called | 0 |
| T1 | `request(2)` | 2 |
| T2 | Receives `onNext(A)` | 1 |
| T3 | Receives `onNext(B)` | 0 |
| T4 | Producer has item C | C is not emitted via `onNext` without new demand |
| T5 | `request(3)` | 3 |
| T6 | Receives `onNext(C)` | 2 |

At T4, the publisher may hold the item in a buffer, defer the data source, block the producer, apply a drop policy, or take another action according to its implementation contract. **Flow specifies a limit on `onNext` emissions; it does not guarantee that the entire pipeline uses bounded memory in every implementation.**

There are two common requesting strategies:

- **One-by-one:** call `request(1)` in `onSubscribe`, then call `request(1)` again after processing each `onNext`. Easy to understand and tightly controls the number of in-flight items.
- **Batched (batch/prefetch):** request an initial batch, such as 32 or 64 items, and replenish once part of the batch has been processed. Usually reduces coordination overhead compared to requesting one item at a time, but allows more items in flight.

The appropriate batch size depends on source latency, processing cost, item size, and acceptable memory usage. `request(Long.MAX_VALUE)` may be reasonable when data is small and the receiver can genuinely keep up, but it forfeits the ability to use demand to throttle the item stream.

## 4. Java 17+ Example: Subscriber Requesting One Item at a Time

The JDK provides `SubmissionPublisher<T>`, a publisher with a separate buffer per subscriber that delivers signals asynchronously via an `Executor`. We use it to observe the request–onNext–complete cycle.

Save the file **`FlowBasicsDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FlowBasicsDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Flow.Subscriber<Integer> subscriber = new Flow.Subscriber<>() {
            private Flow.Subscription subscription;

            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                this.subscription = subscription;
                subscription.request(1);
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("received=" + item);
                subscription.request(1);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                done.countDown();
            }

            @Override
            public void onComplete() {
                System.out.println("completed");
                done.countDown();
            }
        };

        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>()) {
            publisher.subscribe(subscriber);
            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
        }

        if (!done.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("Subscriber failed", failure.get());
        }
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac -encoding UTF-8 FlowBasicsDemo.java
java FlowBasicsDemo
```

Stdout on a successful run:

```text
received=10
received=20
received=30
completed
```

**Explanation:**

- `SubmissionPublisher` provides a ready-made implementation of `Flow.Publisher`; the subscriber does not have to manage queues or callback synchronization itself.
- `onSubscribe` opens a demand of 1. After each item, `onNext` requests one more item. Thus, the subscriber actively paces the receiving process.
- `submit(...)` may return before the subscriber finishes processing, because delivery is asynchronous. Do not use arbitrary `Thread.sleep(...)` calls to "wait long enough"; the demo uses `CountDownLatch` with a timeout.
- `try-with-resources` closes the publisher and emits `onComplete` after the items have been processed in order for that subscriber. `done.await(...)` keeps the main thread alive until a terminal signal is received.
- `AtomicReference<Throwable>` propagates errors from callbacks back to `main` so failures are not silently reported as success.

Note on output: the three `received` lines have a deterministic order within the **same subscription**; the executor may choose which thread runs each callback without affecting that logical order.

## 5. Java 17+ Example: Demonstrating That No onNext Arrives Without Demand

To see that the subscriber is the party granting permission to receive items, the following example **deliberately delays `request`**. `SubmissionPublisher` can hold submitted items in its buffer even when the subscriber has not requested them yet.

Save the file **`FlowDemandDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FlowDemandDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch firstReceived = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Flow.Subscription> control = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Flow.Subscriber<String> subscriber = new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                control.set(subscription);
                subscribed.countDown();
            }

            @Override
            public void onNext(String item) {
                System.out.println("onNext: " + item);
                if ("A".equals(item)) firstReceived.countDown();
            }

            @Override
            public void onError(Throwable throwable) {
                failure.set(throwable);
                completed.countDown();
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
                completed.countDown();
            }
        };

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>()) {
            publisher.subscribe(subscriber);
            if (!subscribed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No onSubscribe");
            }

            publisher.submit("A");
            publisher.submit("B");

            System.out.println("request(1)");
            control.get().request(1);
            if (!firstReceived.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First item not delivered");
            }

            System.out.println("request(1) again");
            control.get().request(1);
            publisher.close();

            if (!completed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No completion");
            }
        }

        if (failure.get() != null) {
            throw new IllegalStateException("Flow failed", failure.get());
        }
    }
}
```

```bash
javac -encoding UTF-8 FlowDemandDemo.java
java FlowDemandDemo
```

Stdout on a successful run:

```text
request(1)
onNext: A
request(1) again
onNext: B
onComplete
```

`firstReceived.await` forces `main` to wait until A is printed before sending the second demand. This ensures the output order does not depend on executor scheduling. `publisher.close()` indicates no new items will be submitted and sends the completion signal after the items already queued for the subscription. This demo uses an unsaturated buffer: **having no demand only prevents `onNext` callbacks; it does not necessarily stop the producer from calling `submit` immediately**.

## 6. SubmissionPublisher: Buffers, Executors, and Slow-Consumer Policies

`SubmissionPublisher<T>` is the built-in implementation of `Flow.Publisher<T>` since Java 9; it emits items **asynchronously** to currently registered subscribers.

### Initialization

```java
// Illustrative snippet, not a standalone program:
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();

// Or specify an Executor and target buffer capacity per subscriber:
SubmissionPublisher<String> custom =
        new SubmissionPublisher<>(executor, 64);
```

The `executor` variable in the second example is an application-provided `Executor` whose lifecycle must be managed separately when needed; because it is undeclared here, the snippet only illustrates the API. The default constructor typically uses `ForkJoinPool.commonPool()` and the default capacity `Flow.defaultBufferSize()`. Do not hard-code the default value, as it may depend on the JDK version or implementation.

Each subscriber has an **independent buffer**. When the publisher emits faster than a subscriber requests and processes, that subscriber's buffer can fill up; the actual enforced capacity may be rounded up from the number passed to the constructor. `getMaxBufferCapacity()` returns the publisher's actual buffer capacity.

### `submit`, `offer`, and `close`

| API | Behavior and Options |
| --- | --- |
| `submit(item)` | Publishes a non-null item to current subscribers; may **block uninterruptibly** when resources/buffers are not ready for a slow subscriber. The return value is an estimate of the maximum lag, not the number of processed items. |
| `offer(item, onDrop)` | Attempts to publish without unbounded waiting; when space is lacking, it may drop the item for one or more subscribers, invoke the handler, and retry once if the handler returns `true`. |
| `offer(item, timeout, unit, onDrop)` | Allows bounded waiting; then applies the appropriate drop/retry behavior. |
| `close()` | Prevents new submissions and emits `onComplete` to current subscribers. |
| `closeExceptionally(error)` | Terminates with an `onError` signal. |
| `estimateMaximumLag()` | **Estimated observability metric**; must not be used as an exact synchronization lock or condition. |

For `offer`, a **negative** result indicates the number of drops that could not be delivered; a non-negative result is a lag estimate and should not be interpreted as an absolute guarantee of zero data loss. `onDrop` may be invoked while the publisher holds internal locks; avoid heavy work or blocking inside the handler.

**Key Trade-offs:**

- `submit` generally preserves items according to the publisher's semantics, but can cause the producing thread to be blocked by a slow subscriber.
- `offer` lets the producer respond faster when space is unavailable, at the cost of **potentially dropping items**. Only use a drop policy when the product or business requirements allow it.
- Increasing buffer size can reduce blocking/dropping during short bursts, but increases memory usage; a large buffer **cannot solve a persistently slow consumer**.
- Multiple subscribers have different demands, separate buffers, and independent callback schedules. One slow subscriber can affect `submit` calls because the publisher must account for the resource state of each subscription.

**Note:** “The publisher supports backpressure” does not guarantee that the entire system can never run out of memory. You must examine how the producer generates items before submitting, whether there are upstream queues, downstream processing speed, buffer capacities, and overflow policies.

## 7. Processor: Connecting Processing Stages

A pipeline typically consists of source → processing → sink. `Flow.Processor<T,R>` is the contract for a component that receives items of type `T` and emits items of type `R`. It can transform, filter, or aggregate data, but **must manage its own subscriptions, state, demand, errors, and terminal signals**.

### Illustrative Processor Skeleton

```java
// Conceptual skeleton placed inside a class; not a complete program:
final class DoublingProcessor
        extends SubmissionPublisher<Integer>
        implements Flow.Processor<Integer, Integer> {

    private Flow.Subscription upstream;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        upstream = subscription;
        upstream.request(1);
    }

    @Override
    public void onNext(Integer item) {
        submit(item * 2);
        upstream.request(1);
    }

    @Override
    public void onError(Throwable throwable) {
        closeExceptionally(throwable);
    }

    @Override
    public void onComplete() {
        close();
    }
}
```

This illustrates a **one-input → one-output** transformation using `SubmissionPublisher`'s buffering. If downstream is slow and the buffer fills up, `submit` may block before requesting more from upstream. That is a simple way to chain backpressure, but calling `request(1)` per item **does not replace** analyzing buffering, cancellation, lifecycle, and exception handling.

For a production processor, you must also handle cases such as multiple downstream subscribers, how downstream cancellation affects upstream, overflow, rejected executor tasks, races when terminal signals arrive, and cleanup. Flow only provides interfaces; it does not provide built-in full demand propagation across arbitrary processors.

## 8. Safety Principles When Implementing Your Own Publisher/Subscriber

**Never emit `onNext` beyond demand.** A subscriber calling `request(3)` does not mean the publisher can emit four items and sort it out later. A custom publisher must coordinate threads and demand counters; when adding large demands, avoid `long` overflow—typically by using saturating addition capped at `Long.MAX_VALUE`.

**Ensure sequential callbacks per subscription.** Do not invoke `onNext` concurrently or out of order for the same subscriber. The `Flow.Publisher` Javadoc requires strict ordering and a *happens-before* relationship between signals of a single subscription.

**Terminate exactly once.** After `onComplete` or `onError`, no further `onNext` may be sent. An invalid `request(0)` or `request(-1)` must result in `onError(IllegalArgumentException)`.

**Respect cancellation.** When cancelled, stop emitting as soon as practicable, release references, and stop unnecessary work. Because cancellation is best effort, the receiver must also be prepared for callbacks that were already scheduled beforehand.

**Do not block arbitrarily in callbacks.** Long-running work in `onNext` stalls the executor, increases lag, and fills buffers. If processing must be handed off to another queue, that queue also needs a bounded capacity; you cannot bypass backpressure by putting an unbounded queue inside `onNext`.

**Account for callbacks throwing exceptions.** A subscriber should handle application errors intentionally. Do not assume the publisher will automatically recover from an exception in `onNext` or continue delivering subsequent items normally. Cancellation, error handling, and resource-closing policies must be defined.

**Do not extrapolate system-wide behavior from a single subscription.** Item ordering for a single subscriber is guaranteed by the contract; the timing at which another subscriber processes items may differ. Shared data structures must independently ensure thread safety.

## 9. How Does Flow Differ from Stream and BlockingQueue?

| Tool | Data / Interaction Model | Key Differences to Remember |
| --- | --- | --- |
| `java.util.stream.Stream` | Pipeline of operations over a data source, typically evaluated when a terminal operation runs | Has no `Flow`-style subscription/demand contract; not an async event stream just because its name contains "stream". |
| `BlockingQueue` | Producer/consumer exchanging via a bounded or unbounded queue | Receivers can `take`, producers can `put`; backpressure comes from queue capacity rather than `request(n)`. |
| `Flow` | Asynchronous publish/subscribe interfaces driven by subscription and demand | Defines the signal contract; does not choose buffers, executors, or overflow policies for you. |
| `SubmissionPublisher` | Ready-to-use publisher implementation | Supports buffering, executor, `submit`/`offer`, and multicasting to current subscribers. |
| `CompletableFuture<T>` | Represents a single future result or error | Does not provide a multi-item stream with a demand contract. |

If you only need a multi-producer/multi-consumer work queue, `ArrayBlockingQueue` or `LinkedBlockingQueue` may be easier to manage. If you only need to compute over an existing collection, `Stream` is usually more suitable. Flow is useful when you need **multi-item output, receivers that can request quantities, and stages connected by subscriptions**.

## 10. Designing and Monitoring Real-World Pipelines

Before choosing a configuration, clarify:

1. **Source:** where does the data come from, can it be paused, and what ordering and delivery guarantees are required?
2. **Subscriber:** how long does processing each item take; can items be processed in parallel; must order be preserved?
3. **Demand:** request item-by-item or in batches; should demand be replenished at the start or upon completion of processing?
4. **Capacity:** what buffers exist at the publisher and each stage; what is the worst-case total memory across all subscribers?
5. **Overload:** block, wait with timeout, drop, retry, or fail; what is the business impact of dropping items?
6. **Lifecycle:** who closes the publisher, who cancels subscriptions, who owns the `Executor`, and what happens when a subscriber fails?
7. **Observability:** throughput, lag, allocations, callback duration, drop percentage, producer block time, `onError`/`cancel` rates.

You can use `SubmissionPublisher`'s lag-estimation methods for observability alongside application-level metrics, but never as a synchronization mechanism. For long pipelines, measure each stage to locate where data accumulates; merely increasing the buffer at a bottleneck stage may simply shift the pressure to the next stage.

### Do Virtual Threads Replace Backpressure?

No. Virtual threads allow running blocking tasks with many concurrent live threads at lower thread overhead than platform threads, but **they do not make downstream resources infinite**. A million tasks waiting on a DB, API, or queue still consume memory and can overload downstream services. Flow controls emission rate through demand; even with virtual threads, you still need to bound connections, buffers, and other finite resources.

## 11. Common Mistakes and Fixes

**Mistake: calling `subscribe` but forgetting `request`.** The subscriber will generally never receive `onNext`. Fix by issuing an appropriate request in `onSubscribe` or whenever ready to accept more items.

**Mistake: treating `request(n)` as resetting the count.** Requesting adds to remaining demand; it does not clear previous demand. Track total requested, items delivered, and unfulfilled demand.

**Mistake: calling `request(0)` to pause.** Invalid; the contract requires `onError(IllegalArgumentException)`. To pause, simply stop requesting more items after consuming the current demand.

**Mistake: calling `request(Long.MAX_VALUE)` and thinking you have useful backpressure.** This is effectively unbounded; if the consumer is slow, you must rely on the implementation's buffering/overflow behavior rather than bounded demand.

**Mistake: calling `submit` on a latency-sensitive thread while forgetting it can block.** Consider a dedicated publishing task, or `offer` with a timeout/drop policy only if data requirements allow it.

**Mistake: assuming `close()` immediately completes all callbacks.** `close` initiates completion; in asynchronous processing, `main` needs a mechanism such as `CountDownLatch` or equivalent to wait for the terminal signal if the outcome matters.

**Mistake: turning a `Processor` into an unbounded queue.** If an intermediate stage pulls from upstream too fast and pushes into an unbounded queue, backpressure is effectively broken at that stage.

**Mistake: failing to cancel or close resources.** Holding onto a `Subscription` without calling `cancel` when work is abandoned can cause upstream to keep generating items. When the producer finishes, call `close` or `closeExceptionally` as appropriate; manage the lifecycle of any supplied executor.

## 12. Self-Check Questions

**Q:** What are the four components of Flow?  
**A:** `Publisher`, `Subscriber`, `Subscription`, and `Processor`.

**Q:** A subscriber calls `request(5)`, then `request(3)`, and has received two items. What is the remaining demand?  
**A:** Six, assuming no other changes: 5 + 3 − 2 = 6.

**Q:** Can `request(0)` be used to pause temporarily?  
**A:** No; a non-positive value results in `onError` with `IllegalArgumentException`. To stop receiving new items, stop calling `request` after the existing demand has been consumed.

**Q:** Why can `submit` still block even though Flow is an asynchronous API?  
**A:** Delivery to subscribers is asynchronous, but `submit` may have to wait for resources when a subscriber's buffer is full.

**Q:** Must two subscribers receiving the same item from `SubmissionPublisher` process it at the same time?  
**A:** No. Each subscription has its own buffer/demand and independent processing timing; ordering within each subscription is preserved by contract unless drops or errors occur.

**Q:** Does `Flow.Processor` come with built-in map/filter operators and automatic demand propagation?  
**A:** No. It is only an interface; the implementation decides how to process data and propagate backpressure.

**Q:** Why is `CountDownLatch` useful in programs testing `SubmissionPublisher`?  
**A:** Because callbacks may arrive after `submit` returns; a latch lets `main` wait for a completion or error signal with an explicit timeout.

**Key Takeaway:** `Flow` provides a **Publisher → Subscription → Subscriber** contract with backpressure via `request(n)`; `SubmissionPublisher` is a useful implementation to start with. Understanding each signal, demand, buffering, overflow, cancellation, and lifecycle is essential to building pipelines that do not accumulate data out of control.

## Official Documentation

- [Oracle Java 21 API — Flow](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [Oracle Java 21 API — Flow.Publisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Oracle Java 21 API — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Oracle Java 21 API — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Oracle Java 21 API — SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
