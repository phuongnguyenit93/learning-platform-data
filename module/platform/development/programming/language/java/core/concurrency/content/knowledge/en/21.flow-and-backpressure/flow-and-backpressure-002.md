# Publisher, Subscriber, Subscription, and Processor in Java Flow

## 1. What Problem Does Flow Solve?

When a producer generates data faster than a consumer can process it, **unbounded pushing** can cause queues to grow continuously, increasing RAM usage, latency, and eventually leading to overload. In concurrent programming, we need a protocol for the receiver to signal how many elements it is ready to handle. That mechanism is called **backpressure**.

Since Java 9, the `java.util.concurrent` package provides the `Flow` class with four nested interfaces:

- `Flow.Publisher<T>` — produces elements of type `T`.
- `Flow.Subscriber<T>` — receives and processes elements of type `T`.
- `Flow.Subscription` — a dedicated link between one publisher and one subscriber, carrying **demand** signals (requests for more items) and cancellation.
- `Flow.Processor<T,R>` — acts as both a subscriber receiving `T` and a publisher emitting `R`, typically used to transform or filter data in a pipeline.

`Flow` defines **the protocol and responsibilities between components**; it does not provide a complete data-stream processing framework on its own. One built-in JDK implementation is `SubmissionPublisher<T>`. The Flow interfaces correspond to the Reactive Streams model; this article uses only Java SE, without requiring Spring or additional reactive libraries.

Visualizing the pipeline:

```text
        input data                            output data
   ┌────────────────┐   onNext(T)   ┌───────────────────┐   onNext(R)  ┌────────────────┐
   │ Publisher<T>   │ ────────────► │ Processor<T,R>    │ ───────────► │ Subscriber<R>  │
   └────────────────┘               └───────────────────┘             └────────────────┘
            ▲                               ▲                                  │
            │ request(n)                    │ request(n)                       │
            └── Upstream Subscription ──────┘   Downstream Subscription ◄──────┘
```

On the left side, the processor is a **subscriber** to the source publisher; on the right side, it is a **publisher** to the final subscriber. Both sides have **separate subscriptions**. The processor must decide how to balance demand between the two sides; the interface does not do that work automatically.

## 2. The Four Roles and Key APIs

| Role | Method | Primary Responsibility |
| --- | --- | --- |
| `Publisher<T>` | `subscribe(Subscriber<? super T>)` | Accepts a registration and establishes a subscription; emits signals according to the protocol |
| `Subscriber<T>` | `onSubscribe(Subscription)` | Receives the subscription before any other callback for that subscription; typically calls `request(n)` |
| `Subscriber<T>` | `onNext(T)` | Receives one requested element |
| `Subscriber<T>` | `onError(Throwable)` | Receives a terminal error signal; no further callbacks from the subscription will follow |
| `Subscriber<T>` | `onComplete()` | Receives a normal completion signal; no further callbacks from the subscription will follow |
| `Subscription` | `request(long n)` | Increases outstanding demand by `n`; `n` must be positive |
| `Subscription` | `cancel()` | Requests to stop receiving; best-effort |
| `Processor<T,R>` | Inherits both API sets | Receives `T` from upstream, processes it, and emits `R` downstream |

**Note on generic types:** `Publisher<? extends T>` produces data; `Subscriber<? super T>` can consume `T`. `Processor<Integer,String>` receives `Integer` from upstream and emits `String` to downstream. `Subscription` is not parameterized because it only controls the number of elements received.

### One Subscription per Producer–Consumer Relationship

A publisher can have multiple subscribers. Each subscriber typically has its own `Subscription` and independent demand. If subscriber A has requested 10 elements, that **does not grant receive allowance** to subscriber B. The publisher must respect each subscriber's individual demand.

`Publisher.subscribe(...)` may establish the connection asynchronously; you cannot assume that once the method returns, the subscriber has already processed `onSubscribe` or is ready to receive `onNext`. With `SubmissionPublisher`, subscriber notifications are scheduled asynchronously via an `Executor`.

## 3. Lifecycle and Signal Ordering

A typical subscription unfolds as follows:

```text
Publisher                      Subscriber
    │                               │
    │  onSubscribe(subscription)    │
    ├──────────────────────────────►│
    │             request(2)        │
    │◄──────────────────────────────┤
    │                               │
    │  onNext(itemA)                │
    ├──────────────────────────────►│   demand remaining: 1
    │  onNext(itemB)                │
    ├──────────────────────────────►│   demand remaining: 0
    │             request(1)        │
    │◄──────────────────────────────┤
    │  onNext(itemC)                │
    ├──────────────────────────────►│
    │  onComplete()                 │
    ├──────────────────────────────►│
    │                               │   terminated
```

Essential guarantees:

1. `onSubscribe` is delivered before any `onNext`, `onError`, or `onComplete` of the corresponding subscription.
2. `onNext` is only emitted when there is previously requested demand, and each element consumes **one** unit of demand.
3. For a single subscription, callbacks to the subscriber are invoked **sequentially, in strict order**. They have a *happens-before* relationship per the protocol guarantees; a subscriber that receives **multiple** subscriptions or has concurrent external access still needs proper synchronization.
4. A subscription terminates via `onError` **or** `onComplete`, and after the terminal signal no further callbacks arrive from that subscription.
5. `cancel()` requests to stop receiving, but does not imply a promise to receive `onComplete()`; a few callbacks already in flight may still arrive after `cancel`.
6. `onNext` must not be passed `null` as a valid item in Flow; `SubmissionPublisher.submit(null)` throws `NullPointerException`.

For `request(n)`, `n > 0` adds to the number of elements allowed to be sent; calls accumulate demand. `request(0)` or `request(-1)` is a protocol error and the subscriber is sent `onError(IllegalArgumentException)`. `request(Long.MAX_VALUE)` is generally treated as effectively unbounded demand; it **bypasses demand-based throttling**, so use it only when the consumer can truly keep up or other load controls are in place.

### Demand Is a Control Signal, Not a Buffer

If a consumer calls `request(3)`, the producer is **permitted to emit at most three more elements** before new demand arrives, but is not forced to emit all three. The producer may not have data yet, may emit fewer items and complete, or may emit an error signal. Demand does not mean three elements are already buffered somewhere.

Backpressure throttles **the number of `onNext` callbacks allowed to be emitted**, but a publisher may still hold data in an internal buffer or receive data from an external source before downstream processes it. You must also control buffer capacity, overload policies, and upstream ingestion rates.

## 4. Runnable Java 21 Example: All Four Roles in One Pipeline

This example creates the chain:

```text
SubmissionPublisher<Integer>          DoublerProcessor<Integer,String>        PrintSubscriber<String>
           1, 2, 3           ───────►        "value=2", "value=4", ...  ───────► output
                ^                                  ^                                |
                | upstream request(1)              | downstream request(1)          |
                └──────────────────────────────────┘◄───────────────────────────────┘
```

`SubmissionPublisher` is a concrete `Publisher` included in the JDK; `DoublerProcessor` implements `Processor` by receiving each `Integer`, converting it to a `String`, and delegating output subscription management to another `SubmissionPublisher<String>`. `PrintSubscriber` requests **one** element after finishing each previous element.

Save the entire program to `FlowFourRolesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowFourRolesDemo {

    static final class DoublerProcessor
            implements Flow.Processor<Integer, String>, AutoCloseable {

        private final SubmissionPublisher<String> output;
        private Flow.Subscription upstream;

        DoublerProcessor(ExecutorService executor) {
            // output itself will provide the Subscription to downstream.
            this.output = new SubmissionPublisher<>(executor, 4);
        }

        @Override
        public void subscribe(Flow.Subscriber<? super String> subscriber) {
            output.subscribe(subscriber);
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            if (upstream != null) {
                subscription.cancel(); // Example only supports a single upstream.
                return;
            }
            upstream = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            try {
                output.submit("value=" + (item * 2));
                upstream.request(1);
            } catch (RuntimeException ex) {
                upstream.cancel();
                output.closeExceptionally(ex);
            }
        }

        @Override
        public void onError(Throwable throwable) {
            output.closeExceptionally(throwable);
        }

        @Override
        public void onComplete() {
            output.close();
        }

        @Override
        public void close() {
            output.close();
        }
    }

    static final class PrintSubscriber implements Flow.Subscriber<String> {
        private final CountDownLatch terminal = new CountDownLatch(1);
        private Flow.Subscription subscription;
        private volatile Throwable failure;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(String item) {
            System.out.println(item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable throwable) {
            failure = throwable;
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("complete");
            terminal.countDown();
        }

        void awaitResult() throws InterruptedException {
            if (!terminal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Flow pipeline timed out");
            }
            if (failure != null) {
                throw new IllegalStateException("Flow pipeline failed", failure);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newFixedThreadPool(2);
             SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(executor, 4);
             DoublerProcessor processor = new DoublerProcessor(executor)) {

            PrintSubscriber subscriber = new PrintSubscriber();

            // Subscribe downstream first, then connect the source to the processor.
            processor.subscribe(subscriber);
            publisher.subscribe(processor);

            for (int item = 1; item <= 3; item++) {
                publisher.submit(item);
            }

            // No more data emitted; completion signal propagates through the processor.
            publisher.close();

            // publisher.close() does not guarantee the subscriber has finished processing.
            subscriber.awaitResult();
        }
    }
}
```

Run on **JDK 21 or later** (no external libraries needed):

```bash
javac FlowFourRolesDemo.java
java FlowFourRolesDemo
```

Output when no error/timeout occurs:

```text
value=2
value=4
value=6
complete
```

This output has a deterministic order because each subscription's `onNext` signals are delivered sequentially. `CountDownLatch` waits for the terminal signal instead of guessing timing with `Thread.sleep(...)`. `try-with-resources` ensures the publisher, processor, and executor are closed upon completion.

**Reading the code by role:**

- **Publisher:** `publisher` emits three integers and allocates a subscription when `processor` subscribes; it does not call `subscriber.onNext(...)` directly.
- **Input Subscriber:** `processor.onSubscribe` receives the upstream subscription and requests one element. After `onNext`, the processor transforms the item and requests the next one.
- **Processor:** transforms `Integer → String`; `output` holds the transformed elements within its buffer limit and manages downstream demand.
- **Final Subscriber:** `PrintSubscriber` receives the downstream subscription, requests one item, processes it, and only then requests the next.
- **Terminal:** `publisher.close()` sends completion in order, `processor.onComplete()` closes `output`, and `PrintSubscriber.onComplete()` releases the latch.

**Intentional limitations of the example:** the processor demonstrates **a single upstream**, a simple transformation path, and delegates buffering to `SubmissionPublisher`. It is not a general-purpose processor handling downstream cancellation edge cases, multiple upstreams, complex error state tracking, or demand coordination across multiple consumers. `output.submit(...)` can still block if downstream is slow and the buffer is full. When building a production processor, you must clearly define cancellation policies, resource closing, retry/drop behavior, and how demand is translated between both sides.

## 5. Publisher: Producing and Emitting Data per Protocol

`Flow.Publisher<T>` only has the `subscribe(...)` method. Actually reading data from a file/socket, fetching DB records, calling APIs, or generating events is the implementation's responsibility.

A compliant publisher must:

- Issue one `Subscription` to each accepted subscriber.
- Never emit more `onNext` signals than the demand that subscription has received.
- Preserve callback ordering per subscription and terminate exactly once.
- Manage data sources, buffers, errors, and cancellations; never wait indefinitely for every consumer without a resource plan.
- Define clearly whether a new subscriber receives data emitted before subscribing or only future data. `SubmissionPublisher` delivers items **submitted after** the subscriber registers, and does not replay history by default.

### What Does SubmissionPublisher Provide?

`java.util.concurrent.SubmissionPublisher<T>` is a built-in asynchronous publisher that emits **non-`null`** items to current subscribers, using an `Executor` to deliver callbacks. Each subscriber has **its own buffer**. The constructor can specify an `Executor` and buffer capacity; the effective capacity may be rounded by the implementation.

```java
// Snippet: executor is an Executor created and managed by the application.
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 32);

publisher.subscribe(subscriber); // subscriber: Flow.Subscriber<String>
publisher.submit("event-1");
publisher.close();
```

The above is a **snippet**, as `executor` and `subscriber` need appropriate declarations/imports. A publisher implementing only the `Flow.Publisher` interface does not necessarily have `submit()` or `close()`; those are APIs specific to `SubmissionPublisher`.

**Differences between `submit` and `offer`:**

| Method | Behavior When Buffer Is Saturated | Things to Note |
| --- | --- | --- |
| `submit(item)` | May block **uninterruptibly by `InterruptedException`** while waiting for buffer space | Simple, but the producer can also stall due to a slow consumer |
| `offer(item, onDrop)` | May drop the item for one or more subscribers when buffer capacity is unavailable | A negative return value indicates the drop count, not "processed" |
| `offer(item, timeout, unit, onDrop)` | Waits for a bounded time, then handles the case where space is still unavailable | The handler can request a single retry; requires a clear drop/retry/error policy |
| `close()` | Rejects further submissions and sends `onComplete` to current subscribers | Does **not** guarantee `onComplete` callbacks have finished executing when `close` returns |
| `closeExceptionally(error)` | Terminates with an `onError` signal | Used when the source cannot continue normally |

`submit` returns an estimated **maximum lag**, not the number of items processed by consumers. Metrics such as `estimateMaximumLag()` and `estimateMinimumDemand()` are mainly for observation; they may reflect stale state and should not be used to make safe check-then-act decisions.

An easily overlooked detail: the buffer limit of 32 is **per subscriber**. A publisher with 200 slow subscribers does not mean total memory is capped at 32 items. Item objects vary in size; many subscribers and active sources can consume far more memory than expected.

## 6. Subscriber: Throttling Demand and Handling Signals

`Flow.Subscriber<T>` consists of four callbacks. You need to design a policy for **when to request more**:

- **`request(1)` in `onSubscribe`, `request(1)` after each `onNext`**: easy to reason about, keeps unacknowledged items small; suited for simple consumers, though throughput may suffer from frequent demand signaling.
- **Batch requests, e.g. `request(32)`**: reduces the frequency of demand signals, suited for high-throughput consumers; however, in-flight items and buffering/storage costs increase and should be measured.
- **`request(Long.MAX_VALUE)`**: applies no demand-based backpressure; only appropriate if another layer already bounds resources and processing always keeps up.

When processing, distinguish between **item received**, **item processing completed**, and **processed successfully**. If `onNext` simply offloads the item to another asynchronous worker and immediately requests more, demand only limits callback delivery rate, **not** the number of running workers. In that case, you need an in-flight work limit and should only request more after the task actually finishes, or apply backpressure through a bounded queue.

Never call `onNext`, `onError`, or `onComplete` directly on someone else's subscriber to "speed up" the pipeline; the protocol requires the publisher/subscription to coordinate callbacks. For a subscriber receiving **one** subscription, callbacks from that subscription are guaranteed sequential; however, the executing thread is not necessarily fixed, and any state shared with other threads still needs appropriate protection.

**Error management in the consumer:** if `onNext` throws an exception, the protocol does not guarantee that every implementation converts it into `onError` the way the application expects; `SubmissionPublisher` cancels the corresponding subscription and provides a handler mechanism for certain errors. Handle business errors proactively, decide whether to fail the stream or keep/retry the item, and ensure resources are closed. Never throw exceptions from `onError`/`onComplete`.

## 7. Subscription: Per-Subscriber Demand and Cancellation

`Flow.Subscription` is the **control channel** for a subscriber to tell upstream "how many more items I can still accept."

For example, a subscriber calls `request(5)`. The publisher emits two `onNext` signals, leaving 3 units of unfulfilled demand. If the subscriber calls `request(4)`, total outstanding demand becomes 7. When demand grows very large, implementations typically use saturating addition to avoid `long` overflow. `Long.MAX_VALUE` effectively represents unbounded demand in many implementations.

- `request(n <= 0)` is an error and will result in `onError(IllegalArgumentException)` for the corresponding subscriber.
- `cancel()` is a **best-effort** request to stop receiving; signals already in flight may still arrive. A cancelled subscription is **not required** to emit `onComplete` or `onError`.
- Only the subscriber owning the subscription is intended to call `request`/`cancel`. Calling them from a non-owner object violates the normal usage contract.
- The subscriber must store the subscription from `onSubscribe` if it wants to request more or cancel later.
- Do not equate `request(n)` with "spawn n threads," "enqueue n items," or "the consumer is guaranteed to receive all n items."

**Example of a subscriber stopping after three elements** (illustrative snippet, not a standalone runnable class):

```java
private Flow.Subscription subscription;
private int received;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(1);
}

@Override
public void onNext(String item) {
    use(item); // Application-defined method.
    if (++received == 3) {
        subscription.cancel();
        return; // Do not wait for onComplete after cancel.
    }
    subscription.request(1);
}
```

In a real application, consider what happens if `use(item)` fails: whether to roll back, cancel or report an error, and when to release resources.

## 8. Processor: Bidirectional Demand, Transformation, and Errors

`Processor<T,R>` extends **`Subscriber<T>` and `Publisher<R>`**. It can map, filter, batch, aggregate, validate, or encode data. The hardest part is **not just type transformation**, but maintaining protocol compliance on both sides:

```text
Source Publisher<T>
      │
      │ onNext(T), onComplete(), onError(...)
      ▼
Processor<T,R> [Subscriber<T>]
      │ transform/filter/buffer
      │ [Publisher<R>]
      ▼
Final Subscriber<R>
```

The **upstream subscription** controls how many `T` items the processor can receive; the **downstream subscription** controls how many `R` items are emitted to the consumer. If one `T` produces three `R`s, downstream demand cannot be forwarded 1:1. If the processor filters out many `T`s, it may need to request multiple upstream items to satisfy a single downstream item. If the processor batches 100 records into one batch, memory limits and batch timeouts must be designed explicitly.

Essential responsibilities in a processor:

1. Ensure each downstream subscription has its own demand; never emit beyond demand.
2. Propagate upstream errors downstream consistently when the pipeline cannot continue; emit no more data after an error.
3. When the source completes, process any remaining valid items/buffers and then emit a final `onComplete`.
4. When downstream cancels or no subscribers remain, decide whether to cancel upstream, continue for other subscribers, or close underlying resources.
5. Set buffer capacity and an overload strategy: block the producer, drop intentionally, reject, or halt the source; never allow unbounded queues.
6. Define synchronization if there are multiple upstreams or downstreams, and ensure item ordering is preserved.

The `DoublerProcessor` example above uses `SubmissionPublisher<String>` to manage the publishing side. The `Integer`-receiving side only requests the next item after it has `submit`ted the transformed element. This is a suitable learning pattern for 1:1 mapping, but does not replace custom demand design for more complex processing topologies.

## 9. Practical Backpressure: Slow Processing, Buffers, and Executors

Suppose a publisher produces at 1,000 items/second and a subscriber processes at 100 items/second. The system will accumulate an average gap of around 900 items/second if the source keeps generating data at the same rate. Without a throttling mechanism, the backlog can grow continuously.

**Flow lets you express demand at callback boundaries**, while whether the pipeline actually reduces upstream load depends on how the publisher and processor are implemented. Common strategies:

| Scenario | Approach |
| --- | --- |
| Source can be paused (chunked reads, iterator) | Only read/generate more when demand is available |
| Source rate cannot be controlled (external events) | Bounded buffer, observable drop/reject, or admission throttling at the ingress |
| Slow I/O with a clear SLA | Bounded in-flight work, timeouts, cancel when needed, and latency measurement |
| One very slow subscriber in a multi-subscriber stream | Per-subscriber policy: per-subscriber buffer, drop, isolate subscriber, or cancel subscription |
| Processor with async processing | Request more based on actually completed work, or use a bounded in-flight counter/blocking queue |

### Role of the Executor

`SubmissionPublisher` dispatches callbacks to an `Executor`. Choose an appropriate executor and avoid self-deadlock scenarios where callbacks block because a buffer is full while all threads in the same executor are waiting on the same pipeline. For very slow processing, design separate admission control and downstream resource pools.

Using virtual threads (Java 21+) can fit blocking I/O tasks, but **many virtual threads do not automatically create backpressure or limit external connections**. If a callback offloads work to another virtual thread and immediately requests more, you must enforce a real task and resource limit; otherwise the backlog still grows even though each virtual thread is cheap.

Never use `Thread.sleep` as a backpressure mechanism. Sleeping does not change outstanding demand, does not bound queues, and does not guarantee the source will stop generating data.

## 10. Common Pitfalls

**Forgetting to call `request(n)` after `onSubscribe`.** The subscriber registered but granted no demand, so it receives no `onNext`; the pipeline appears "hung." Start with a small request and observe.

**Calling `request(0)` or `request(-n)` to pause.** This is a protocol error, and the publisher sends `onError`. To pause, simply **do not request more** and manage the previously granted outstanding demand.

**Using `request(Long.MAX_VALUE)` everywhere.** Loses the ability to limit callbacks based on downstream capacity; easily hides backlogs in other layers.

**Assuming `submit` means the consumer has finished processing.** `SubmissionPublisher.submit` may only have placed the item into a buffer; `close` also does not wait for subscribers to finish. Use terminal signals, `CompletableFuture`, latches, or processing results to wait properly.

**Keeping an unbounded buffer in a processor.** The Flow interfaces do not forbid an implementation from storing unbounded items. Bound capacity and define overflow behavior.

**Failing to propagate errors/cancellations across both sides of a processor.** Downstream may wait forever when upstream has errored or cancelled; establish clear terminal and cleanup rules.

**Sharing mutable state across multiple subscriptions.** Callbacks are serialized **per subscription**, with no synchronization guarantee across different subscribers or other tasks. Each subscription should have isolated state, or shared state must be properly protected.

**Delivering an item to a subscriber without demand.** Custom publishers must track outstanding counts; violating the protocol can overwhelm consumers or cause unpredictable failures.

**Treating `cancel()` like `onComplete()`.** Cancellation is best-effort and does not require a terminal callback. A consumer waiting for `onComplete` after cancelling may wait forever.

**Writing a custom Publisher/Processor too early.** Implementing the protocol yourself requires handling races between request/cancel/terminal signals, buffering, and errors. Prefer JDK components like `SubmissionPublisher` or battle-tested libraries when requirements grow complex.

## 11. Verifying and Observing a Pipeline

Test targeted scenarios:

1. Subscriber makes no requests: must receive no `onNext`.
2. Subscriber calls `request(1)`: must receive at most one `onNext` before requesting again.
3. Calling `request(0)`: a compliant implementation must signal a protocol error rather than silently emitting data.
4. Publisher completes normally: subscriber receives `onComplete` exactly once, with no `onNext` afterward.
5. Publisher terminates with error: subscriber receives `onError`; must not also receive `onComplete`.
6. Mid-stream cancellation: stops emitting on a best-effort basis; avoid waiting for mandatory terminal signals.
7. Fast producer, slow consumer: verify bounded buffers, `submit` blocking duration, or dropped item count with `offer`.
8. Filter/map/batch processor: verify ordering, item counts, and consistency when upstream errors or downstream cancels.
9. Subscriber throws an exception: verify implementation behavior, cleanup, and no leaked subscriptions/resources.
10. Multiple subscribers: demand, errors, and cancellation for each subscription are managed independently.

Metrics to measure: item emission/consumption rates, **outstanding demand** (if the implementation can record it safely), item processing latency, queue/buffer occupancy, dropped/retried item counts, `submit` wait time, active/cancelled subscriptions, and terminal error counts. `SubmissionPublisher`'s `estimate...` APIs only provide **observational estimates**, not an exact synchronization source.

## 12. Key Takeaways

- **Publisher** produces and emits items; **Subscriber** processes items and signals demand; **Subscription** is the control contract for each producer–consumer pair; **Processor** combines both roles to build pipelines.
- `request(n)` is **permission to receive up to n more `onNext` signals**, not a guarantee of receiving all n or that n items are already buffered.
- `onSubscribe` arrives before other callbacks; `onError` and `onComplete` are terminal. `cancel` only requests stopping and does not promise a terminal callback.
- `SubmissionPublisher` provides built-in async delivery and bounded per-subscriber buffering; you must still choose a block/drop/error policy and await completion properly.
- Backpressure is effective when **the entire pipeline** respects demand and bounds sources/buffers/in-flight work. The Flow interfaces alone do not solve every overload problem.

## Official Documentation

- Oracle, [Flow API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): the four interfaces, demand rules, and subscriber example.
- Oracle, [Publisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html) and [Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): callbacks, ordering, and terminal signals.
- Oracle, [Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(long)`, `cancel()`, errors on non-positive demand.
- Oracle, [Processor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Processor.html): combining Subscriber and Publisher.
- Oracle, [SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): per-subscriber buffer, `submit`, `offer`, and lifecycle.
