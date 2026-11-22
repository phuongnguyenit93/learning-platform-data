# When to Build an Event-Driven Pipeline in Java: Flow & Backpressure

An **event-driven pipeline** organizes work into stages that receive, transform, filter, aggregate, or write results as events arrive. Instead of a single function sequentially calling every step and waiting for each return value, stages can run independently, pass messages across asynchronous boundaries, and coordinate processing rates. In Java, `java.util.concurrent.Flow` (since Java 9) provides a **Publisher–Subscriber** protocol with *backpressure* (demand-driven flow control), allowing downstream consumers to explicitly signal how many more items they can accept.

The key decision is not "there are events, so use Flow," but rather **whether the pipeline has enough reason to take on the added complexity of asynchronous execution, buffering, demand signaling, error handling, and cancellation**.

This lesson focuses on pure Java concurrency—specifically `Flow`, `SubmissionPublisher`, and standard `java.util.concurrent` utilities. No framework is required to understand and apply the principles below.

## 1. What Problem Does an "Event-Driven Pipeline" Actually Solve?

Suppose an application continuously receives measurement records:

```text
Event source
    │
    ▼
Validate data ──────► Filter out invalid events
    │
    ▼
Normalize / transform
    │
    ▼
Aggregate by condition
    │
    ▼
Send results to consumer
```

If everything runs sequentially on a single thread, the flow is easy to reason about, but it may not make good use of I/O wait time. If the source produces faster than the sink writes results, an unbounded queue can exhaust memory. When multiple stages run independently, the system needs clear answers to:

1. **Where do events come from?** Does the source produce data when asked (*pull*) or emit continuously even without a receiver (*push/hot source*)?
2. **Who controls the amount of pending work?** Is there a bounded queue/buffer and a policy for when it is full?
3. **What happens if a consumer is slow?** Wait, slow down the source, drop events, persist to durable storage, or fail with an error?
4. **What ordering and correctness guarantees are needed?** Per-source ordering, global ordering, exactly-once processing, or only the final result?
5. **How do errors, cancellation, and resource cleanup propagate across stages?** Are subscriptions, executors, sockets, and other resources closed properly along the lifecycle?

An event-driven pipeline is a good fit when these questions have clear answers and asynchronous boundaries deliver real benefits.

### Events, commands, and batches are not the same

- **Event**: a notification that "something happened," such as `ReadingReceived` or `FileChanged`. It may trigger multiple handlers.
- **Command**: a request to perform an action, which may require a result or acknowledgment, such as `RecalculateInvoice`.
- **Batch**: a bounded dataset processed together, such as reading a file and computing a sum.

These three styles can be combined, but you should not turn a short batch computation into multiple events and callbacks just because a library offers an asynchronous API.

## 2. Signs You SHOULD Consider an Event Pipeline

| Signal in the problem | Potential benefit | What to verify |
|---|---|---|
| Data arrives continuously over time | Incremental processing without waiting for all data to finish | Shutdown mechanism, buffer boundaries |
| Multiple stages are independent in timing or I/O | Separation of concerns, overlapping work | Scheduling overhead, error management |
| Source and destination rates fluctuate | Backpressure can limit the amount of pending work | Can the source actually slow down? |
| Data is large / cannot all fit in RAM | Process item by item or by window | Do aggregations/windows keep bounded state? |
| Each event can be filtered and transformed independently | Easy to structure stages and test in isolation | Side effects, ordering, idempotency |
| Multiple consumers run at different speeds | Publisher can fan out to multiple subscriptions | Per-subscriber buffering and latency |
| Processing stream must be cancellable if the receiver stops | `Subscription.cancel()` provides a cancellation channel | Do stages actually release resources? |
| A blocking step must be isolated from event emission | Avoids holding the source thread on heavy operations | Choosing the right executor/concurrency model |

**Reasonable examples:** continuously processing sensor updates, reading and classifying internal event streams, notification streams, in-app record transformations, or streaming data with unpredictable consumption rates.

"Having many events" is only an initial hint. **The primary value of Flow is the demand contract model** between producer and consumer, especially when downstream can be slow.

## 3. Cases Where You Should NOT Build an Event Pipeline Yet

Do not force a simple workflow into an asynchronous pub/sub pipeline if:

- There are only a few **short, sequential steps with an immediate result**, such as validating input and returning a value.
- All data is already in memory and only needs a batch transformation; a `Stream` or a loop is usually simpler.
- The work is purely CPU-bound and needs data-parallel speedup; consider better algorithms, an `ExecutorService`, or a controlled parallel stream rather than a multi-buffer pipeline.
- A request requires a single atomic transaction spanning all operations; splitting it into asynchronous events changes transaction boundaries.
- You need **durable storage, replay after restart, guaranteed retries, multi-node coordination, or exactly-once processing**. `Flow` by itself is an in-process protocol; it does not provide a message broker, storage, transactions, or exactly-once semantics.
- An external source *cannot slow down* and the business **cannot tolerate data loss**, yet there is no buffering/durability strategy. Adding `request(n)` alone does not make incoming external data disappear.
- Teams cannot clearly assign ownership for lifecycle, cancellation, error handling, and observability. That complexity can outweigh the benefits.

A bounded `BlockingQueue` with a worker can be enough for a simple producer–consumer setup; ordinary method calls or an `ExecutorService` are easier to maintain when you do not need the Publisher–Subscriber protocol. Choose `Flow` when **demand and multi-stage coordination** are real problems, not as a default for every concurrency task.

## 4. What Components Make Up Java Flow?

`Flow` defines interfaces aligned with the **Reactive Streams** specification:

| Component | Core contract |
|---|---|
| `Flow.Publisher<T>` | Allows a `Subscriber` to register via `subscribe(subscriber)` and emits items and terminal signals |
| `Flow.Subscriber<T>` | Receives `onSubscribe`, `onNext`, `onError`, and `onComplete` |
| `Flow.Subscription` | Connects a Publisher to **one Subscriber**, providing `request(long n)` and `cancel()` |
| `Flow.Processor<T,R>` | Acts as both a Subscriber receiving `T` and a Publisher emitting `R`; suited for a transformation stage |

Basic signal flow:

```text
Publisher                          Subscriber
    |                                  |
    | ------- onSubscribe(s) --------> |
    | <------ s.request(2) ----------- |
    | ------- onNext(eventA) --------> |
    | ------- onNext(eventB) --------> |
    |    (must not push more until     |
    |     new demand is signaled)      |
    | <------ s.request(1) ----------- |
    | ------- onNext(eventC) --------> |
    | ------- onComplete() ----------> |
    |                                  |
          or onError(error)
```

**`request(n)` means "you are permitted to send up to n more events,"** not that the Publisher must immediately produce `n` items. Demand is the count of items allowed to be emitted for that subscription, accumulated according to the API's saturation rules. Each `onNext` consumes one unit of demand. `request(Long.MAX_VALUE)` represents unbounded demand; it does not mean the system has infinite buffers or infinite processing speed.

Important rules:

1. After `subscribe`, the Subscriber is given a `Subscription` via `onSubscribe` before receiving normal data signals.
2. A subscription may only emit `onNext` when demand is positive; `request(0)` or a negative value is an invalid request and must be signaled with `onError` per the Flow contract.
3. Signals for **the same subscription** are delivered sequentially and never concurrently overlapped per Publisher rules; this does not guarantee that different subscribers see callbacks at the same time.
4. `onError` or `onComplete` is a terminal signal; no further `onNext` may be sent to that same subscription afterward.
5. `cancel()` is a request to stop the subscription, not a guarantee that the subscriber will receive `onComplete`. Upstream code must actually release its underlying resources.
6. `null` events are not allowed in standard Flow-compliant implementations; with `SubmissionPublisher`, `submit(null)` throws `NullPointerException`.

`Flow` describes a signal-exchange contract; **it does not create threads, store events, or make a computation non-blocking on its own**. Synchronous or asynchronous execution depends on the implementation and executor.

## 5. How Does Backpressure Differ from Queues, Rate Limiting, and Load Shedding?

**Backpressure** is a signal from downstream indicating how much data it can accept, propagated upstream so the producer can pace or adjust emission. A buffer can absorb short bursts, but a buffer **cannot solve a sustained rate mismatch indefinitely**.

Suppose a source generates 1,000 events/second while the processor only completes 100 events/second:

- With an unbounded queue, the backlog grows by roughly 900 events/second and can eventually exhaust the heap.
- With a bounded buffer and a source that can wait, the producer pauses or slows down; the system stays stable, though producer latency may increase.
- If the source cannot wait (for example, a device continuously sending data), you need a policy for dropping, sampling, durable storage, or source-side control.
- If the business cannot lose a single event and the source cannot stop, **you need durable storage with clear operational limits**—RAM and `request(n)` alone cannot solve it.

**Distinguishing the mechanisms:**

| Mechanism | Question it answers |
|---|---|
| `request(n)` | How many more items is the Subscriber allowing upstream to send? |
| Bounded queue/buffer | How many items may wait in memory? |
| Rate limiting | How many requests may be emitted within a time window? |
| Semaphore/concurrency limit | How many operations may use a resource concurrently? |
| Load shedding/drop | Under overload, which items are discarded and is loss acceptable? |
| Durable log/queue | If the process restarts, can already-received events be recovered? |

These mechanisms complement rather than completely replace one another. For instance, a subscriber might request 20 items while the system only has 5 outbound connections; you still must limit actual connection concurrency.

## 6. Runnable Example: Per-Item Demand with `SubmissionPublisher`

`SubmissionPublisher<T>` is the JDK's built-in Publisher: it uses an executor to deliver items asynchronously to current subscribers, maintains a **separate buffer per subscriber**, and provides options for when a buffer is full. The following demo sums 5 events; the subscriber requests only **one more item** each time it finishes processing one.

Save as **`FlowDemandDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {
    static final class CountingSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch done;
        private Flow.Subscription subscription;
        private int sum;

        CountingSubscriber(CountDownLatch done) {
            this.done = done;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            sum += item;
            subscription.request(1); // Request one more item only after finishing the current one.
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("error=" + error.getClass().getSimpleName());
            done.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("sum=" + sum);
            done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        var executor = Executors.newSingleThreadExecutor();
        var done = new CountDownLatch(1);

        try (var publisher = new SubmissionPublisher<Integer>(executor, 2)) {
            publisher.subscribe(new CountingSubscriber(done));

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }
            publisher.close();

            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile and run with **JDK 21**:

```bash
javac FlowDemandDemo.java
java FlowDemandDemo
```

Output when all items succeed:

```text
sum=15
```

**Explanation:**

- `publisher.subscribe(...)` registers the subscriber; the `onSubscribe` callback provides a `Subscription`.
- `request(1)` permits delivering one item. After finishing work in `onNext`, the subscriber requests one more. Here, `onNext` runs sequentially per subscription.
- `SubmissionPublisher<>(executor, 2)` configures the intended maximum buffer capacity **per subscriber**; the effective capacity may be rounded by the implementation, so check `getMaxBufferCapacity()` if needed.
- `submit` may block the producer thread when any subscriber's buffer is full, waiting for space to publish. Thus it applies **backpressure to the `submit` caller**, rather than always being non-blocking.
- `close()` ends publishing and delivers `onComplete` asynchronously to subscribers after all submitted items; `CountDownLatch` lets `main` wait for completion. Simply calling `close()` and exiting immediately does not guarantee all callbacks have finished.
- The executor is owned by the demo and shut down in `finally`. With multiple slow subscribers, a single-worker executor can become a bottleneck; it is chosen here to keep the example easy to verify, not as a general performance recommendation.

This example performs no network I/O and does not demonstrate throughput gains. It illustrates **demand and signal lifecycle**. In production, `onError` must record or propagate errors according to business policy; merely printing the exception class name is not enough.

## 7. Runnable Example: Data Can Wait in the Buffer Before Delivery Is Permitted

The next example separates **being `submit`ted to the Publisher** from **being delivered via `onNext`**. The Subscriber requests the first 2 items. The Producer submits 3 items; the third item waits until the Subscriber requests more.

Save as **`DemandWindowDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class DemandWindowDemo {
    static final class Consumer implements Flow.Subscriber<Integer> {
        private final CountDownLatch firstTwo;
        private final CountDownLatch terminal;
        volatile Flow.Subscription subscription;
        int received;

        Consumer(CountDownLatch firstTwo, CountDownLatch terminal) {
            this.firstTwo = firstTwo;
            this.terminal = terminal;
        }

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(2);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("item=" + item);
            if (++received == 2) {
                firstTwo.countDown();
            }
        }

        @Override
        public void onError(Throwable failure) {
            System.out.println("error");
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("complete");
            terminal.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        var executor = Executors.newSingleThreadExecutor();
        var firstTwo = new CountDownLatch(1);
        var terminal = new CountDownLatch(1);
        var consumer = new Consumer(firstTwo, terminal);

        try (var publisher = new SubmissionPublisher<Integer>(executor, 4)) {
            publisher.subscribe(consumer);

            for (int i = 1; i <= 3; i++) {
                publisher.submit(i);
            }

            if (!firstTwo.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing first batch");
            }

            System.out.println("request-more");
            consumer.subscription.request(1);
            publisher.close();

            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Not completed");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac DemandWindowDemo.java
java DemandWindowDemo
```

Output:

```text
item=1
item=2
request-more
item=3
complete
```

Here, item 3 **has already been `submit`ted**, but is not delivered via `onNext` once the initial demand of two items is exhausted. Only when `main` calls `request(1)` is the publisher permitted to deliver that remaining item. `CountDownLatch` ensures `"request-more"` is printed only after the subscriber has processed the first two items, avoiding `Thread.sleep` guesswork. `volatile` on `subscription` reflects visibility between the callback thread and `main`, while the latch signal guarantees ordering by the time `main` accesses the reference.

**What not to infer:** zero demand does not prove the producer has stopped generating data, because `SubmissionPublisher` can **buffer** submitted events up to its capacity. Only when the buffer fills—depending on the API called and policy—will the producer block or potentially drop items. For backpressure to reach the true source, that source must be designed to respect the signal.

## 8. Where Does `SubmissionPublisher` Fit, and What Are Its Limits?

`SubmissionPublisher` is very useful for learning or wiring small components **within a single JVM**, not as a full-featured production event-broker infrastructure.

### Two policies when the buffer is full

- **`submit(item)`:** may block **uninterruptibly** until space is available in the buffer of every subscriber that needs to receive the item; easy to understand, but risks holding the producer thread for a long time or indefinitely if a subscriber stops requesting.
- **`offer(item, onDrop)`** (or its timeout overload): may fail to deliver to some subscribers under overload. The handler can handle the drop and request a single retry per the API contract; a negative return value indicates drops. Critical data must never be silently discarded just because `offer` returns quickly.

A publisher with multiple subscribers maintains **independent buffers** for each subscriber. One slow consumer can cause the producer's `submit` to wait, affecting everyone even if other consumers are fast. Creating 100 subscribers with a buffer of 256 is **not** equivalent to one global 256-item buffer; you must budget memory across subscriptions and stage states.

`SubmissionPublisher` does not replay items emitted before a subscriber registered like a durable event log; do not use it as a substitute for historical storage. If you need crash recovery, design dedicated storage/broker infrastructure and an input-throttling adapter. If events are critical, you need ack/idempotency/retry mechanisms at the business layer and durable state; `onNext` does not by default mean "permanently persisted."

### Signs of missing backpressure in a custom `Processor`

A `Flow.Processor<T,R>` bridges upstream `T` and downstream `R`. It can represent a `Publisher -> Processor -> Subscriber` pipeline, but **there is no automatic demand forwarding if you write your own implementation**. For example, a processor that calls `upstream.request(Long.MAX_VALUE)` and stores every input in an unbounded list breaks flow control even if downstream only calls `request(1)`.

A proper processor must coordinate **downstream demand, in-flight input count, bounded buffers, overflow policy, cancellation, completion, and errors**. For filters that drop many items, upstream requests may need to exceed downstream output demand, but still with clear bounds and rules. Do not assume that requesting 10 upstream items guarantees 10 output items after filtering.

### Error and cancellation lifecycle

- `onError(Throwable)` is a terminal signal for the subscriber; clean up resources and report the error within the appropriate scope.
- `onComplete()` only states that the Publisher has finished emitting for that subscription; it does not mean "all external side effects are durable" unless your program establishes that.
- `Subscription.cancel()` asks to stop receiving more items and release related work; upstream/processors must actively support it rather than assuming other threads will stop on their own.
- `SubmissionPublisher.closeExceptionally(error)` signals abnormal termination to current subscribers, unlike a normal `close()`.
- In production, guard against exceptions thrown by code inside `onNext` so callbacks do not burn through workers, leak resources, or mask business errors. If a stage transforms errors, propagate them according to the pipeline contract or explicit monitoring.

## 9. Designing a Bounded Event Pipeline

Example scenario: document status update events are emitted continuously, then validated, enriched, aggregated, and sent to an output sink.

```text
Input source
  ├─ rate limit intake / can the source wait?
  ▼
Bounded buffer
  ▼
Validate/Filter
  ▼
Transform/Enrich  ───> Limit concurrent I/O tasks
  ▼
Aggregate/window  ───> Bound state size and retention time
  ▼
Output
  └─ acknowledge result / handle errors / cancel
```

Answer several questions **before creating a Publisher/Processor**:

1. **Source characteristics:** is emission bounded, bursty, non-blockable, or pull-capable? If it is a hot source, what happens when a subscriber falls behind?
2. **Event unit:** immutable data or mutable object references? Do you need defensive copies to prevent mutation during later stages?
3. **Processing boundaries:** which stages are CPU-bound and which are blocking I/O? How are executors/threads and memory budgets allocated separately?
4. **Buffer limits:** maximum capacity at every boundary, not just a single buffer at the source. When full, do you wait, fail, drop, or spill to storage?
5. **Ordering:** is per-key ordering (e.g., per device) or global ordering required? Could increasing concurrency violate update order?
6. **Correctness:** if duplicates, retries, timeouts, or cancellations occur, could events be duplicated or lost? Is there an idempotency key or transaction boundary?
7. **Fan-out to multiple subscribers:** should one slow subscriber block the producer and other subscribers? Do you need channel isolation or prioritization?
8. **Termination:** conditions for `onComplete`, `onError`, cancellation, and shutdown; who owns the executors and external resources?
9. **Observability:** measure queue depth/lag, unsatisfied demand (treated strictly as a monitoring signal), drop rate, emit/process rates, latency, errors, and GC.

**An essential condition:** backpressure must flow across stages or convert into an intentional overflow policy. If one stage spawns unbounded tasks onto another executor and immediately signals completion of input intake, the entire flow can still blow up in that executor's queue.

## 10. Distinguishing "Suitable for an Event Pipeline" from "Using Flow"

An event pipeline is an **architecture**; `Flow` is a **set of Java interfaces** for connecting demand-aware producers and consumers. You can build an event pipeline with a bounded `BlockingQueue`, an actor/message loop, or custom interfaces; conversely, using `Flow` for a tiny piece of code does not automatically make an entire system an event-driven architecture.

| Need | Initial option to consider |
|---|---|
| Single call needing an immediate result, short logic | Synchronous method / `CompletableFuture` when async is truly needed |
| Bounded in-memory batch processing | Loop or Java `Stream` |
| Single-channel producer–consumer with an explicit queue bound | `ArrayBlockingQueue` or a bounded `BlockingQueue` |
| Multi-stage event stream where the receiver must regulate demand | `Flow.Publisher/Subscriber/Processor` |
| Many independent tasks with a bounded worker pool | `ExecutorService` with controlled backlog and timeouts |
| Large numbers of independent blocking I/O tasks on Java 21 | Virtual threads with limits on real connections/resources |
| Replay, durable delivery, multi-process/multi-host | Purpose-built storage/broker; optionally adapt to Flow inside the JVM |

Mechanisms can be combined, but the more concurrency layers you add, the harder it becomes to reason about termination and failures. Choose the minimal structure that addresses the measured bottleneck.

## 11. Common Mistakes

| Mistake | Why it is dangerous | How to fix |
|---|---|---|
| Assuming using `Flow` automatically slows down the event source | The source knows nothing about demand unless an adapter forwards the signal | Design a pull-based source or an explicit overflow policy |
| Subscriber calls `request(Long.MAX_VALUE)` regardless of load | Loses demand-limiting feedback | Request in batches matching processing capacity |
| Using an unbounded buffer at one stage | Can cause OOM when downstream is slow | Set explicit quotas on every queue/window |
| Assuming `submit` never blocks | Can wait for buffer space to free up | Choose `submit`/`offer` based on data-loss tolerance and timeout needs |
| Ignoring exceptions inside `onNext` | Errors become hard to observe or silently break the subscription | Use clear terminal handling and cleanup |
| Failing to send `onComplete` or call `close()` | Subscriber waits forever after the source finishes | Complete and await terminal signals properly |
| Not handling `cancel` | Sources/stages keep holding resources | Propagate cancellation upstream across stages and close resources |
| Submitting unbounded work to a pool inside `onNext` | Executor queue grows unbounded despite Flow demand | Limit in-flight tasks and throttle upstream |
| Needing replay while using only `SubmissionPublisher` | Data is lost if the JVM stops | Use durable storage, acks, and retries |
| Assuming all subscribers process at the same pace | One slow consumer can backpressure the producer | Measure per-subscription lag and isolate channels when needed |
| Using parallelism to fix a downstream I/O bottleneck | Databases/APIs still have fixed quotas | Bound by resource limits and optimize the real bottleneck |
| Assuming backpressure = exactly-once | Demand does not guarantee durability or idempotency | Design business acknowledgments and deduplication |

## 12. Practical Decision-Making Approach

Start from **the problem and data rates**, not from a library name:

1. **Assess continuity:** is the data truly streaming, or just a finite collection?
2. **Measure rate mismatch:** producer/consumer events per second, peak bursts, average processing latency; if rates match closely and volume is small, a simpler model may suffice.
3. **Analyze backpressure:** can upstream be blocked? If not, is data loss acceptable, and how long must buffers hold data?
4. **Define semantics:** ordering, idempotency, retries, cancellation, delivery guarantees, and persistence.
5. **Choose the abstraction level:** sequential stream, bounded queue, `ExecutorService`, `Flow`, or an external broker/protocol. Add more stages only when there is a clear logical or performance benefit.
6. **Set budgets:** buffer capacity, max in-flight tasks, CPU threads/connections, timeouts, and aggregated state size.
7. **Test overload before production:** slow subscribers, producer bursts, mid-pipeline errors, cancellation, executor shutdown, a stalled subscriber, re-subscription, and downstream logic errors.
8. **Observe:** throughput, end-to-end latency, lag/buffer occupancy, drops, retries, allocations, memory, and executor utilization. Pending event counts must remain bounded by policy.

A pipeline should have a **well-defined contract both when fast and when overloaded**. If throughput looks great in a normal benchmark but a large burst causes an unbounded backlog, the pipeline is incomplete.

### Self-Check Questions

1. A service receives only a few synchronous commands per second and runs 3 in-memory calculations: why is an event pipeline probably unnecessary?
2. Does `Subscriber.request(5)` force a Publisher to send all 5 items immediately?
3. A Subscriber called `request(2)`, and the producer `submit`ted 3 items to `SubmissionPublisher`. Where can item 3 reside before more demand is requested?
4. If upstream produces 500 events/second, downstream processes 100 events/second, and upstream cannot stop, why does simply increasing the RAM buffer not solve the problem long-term?
5. Does `Flow` automatically persist events for replay after a JVM restart?
6. Why should `request(Long.MAX_VALUE)` not be the default for a consumer with a bounded I/O quota?
7. If stage A receives items with demand but submits all inputs to an executor with an unbounded queue, is backpressure preserved to stage B?
8. Two subscribers share the same `SubmissionPublisher`, and one is very slow—what `submit` behavior must be accounted for?

**Suggested answers:** (1) overhead and complexity outweigh benefits; (2) no, it is an upper bound on permission; (3) in the subscription's buffer; (4) the backlog keeps growing—you need source throttling, dropping, a durable queue, or more processing capacity; (5) no; (6) you lose demand bounds while downstream resources remain finite; (7) no; (8) `submit` may block because of the slow subscriber's full buffer.

### Official References

- [Java SE 21 — `Flow`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): Publisher–Subscriber interfaces, demand, and basic guidance.
- [Java SE 21 — `Flow.Publisher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html): emission contract, signal ordering, and terminal signals.
- [Java SE 21 — `Flow.Subscription`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request`, `cancel`, and demand.
- [Java SE 21 — `SubmissionPublisher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): executor, per-subscription buffer, `submit`, `offer`, and `close`.
- [Java SE 21 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): a lighter-weight option for bounded-queue producer–consumer designs.
