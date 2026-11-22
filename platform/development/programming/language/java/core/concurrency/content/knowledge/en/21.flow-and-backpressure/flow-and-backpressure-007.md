# Buffer Limits and Slow Consumer Handling Policies in Java Flow

In an asynchronous pipeline, a producer can emit data faster than a consumer can process it. Without limits and throttling rules, pending data accumulates, latency increases, memory is exhausted, or the producer gets blocked. This article focuses on **Java concurrency in general**, specifically the standard **java.util.concurrent.Flow** interfaces and the **SubmissionPublisher** class (since Java 9). The examples use Java 17+ without framework dependencies.

## 1. Buffer, Demand, and Backpressure Are Three Different Concepts

- **Buffer** is where emitted elements are held before their processing is finished. A bounded capacity limits the number of elements that can wait at a point in the pipeline.
- **Demand** is the number of elements a subscriber allows the publisher to send next via calls to **Flow.Subscription.request(n)**. When receiving an element via **onNext**, unfulfilled demand decreases accordingly. Demand is a protocol-level throttling mechanism, not buffer capacity.
- **Backpressure** means that the processing capacity on the receiving side influences the emission/delivery rate, rather than pushing elements unboundedly. In Flow, the subscriber actively requests more elements; the publisher and intermediate layers must also manage the amount of pending data.
- **Slow consumer** is a subscriber that processes slowly, stops requesting more, is blocked on I/O, runs out of resources, or encounters errors that cause the backlog to grow.

Consider this scenario: a publisher produces 1,000 events/second, while a subscriber only handles 600 events/second. If items continue to be accepted without blocking or dropping, the backlog grows by approximately **400 events/second** during that period. After 30 seconds, around 12,000 events are waiting. If each element takes an average of 2 KiB, the payload data alone can be nearly 24 MiB, not counting objects, queue nodes, references, and JVM overhead. This is a design estimation, not an exact guarantee about heap usage.

**Key takeaway:** increasing the buffer only helps absorb short bursts; if the average arrival rate is consistently higher than the processing rate, no finite buffer size can fix the long-term mismatch.

## 2. Java's Standard Flow Model

~~~text
Producer --submit/offer--> Publisher --separate queue--> Subscriber A
                                 |                       request(n)
                                 +--separate queue-----> Subscriber B (slow)
                                                         request(n)
~~~

Four related interfaces:

| Component | Responsibility |
| --- | --- |
| **Flow.Publisher<T>** | Allows subscribing; emits signals according to the Flow contract. |
| **Flow.Subscriber<T>** | Receives **onSubscribe**, **onNext** signals, and then a terminal signal **onError** or **onComplete**. |
| **Flow.Subscription** | Binds a subscriber to a publisher; **request(n)** increases demand, **cancel()** cancels the subscription. |
| **Flow.Processor<T,R>** | Acts as both a subscriber upstream and a publisher downstream; must regulate both directions if implemented manually. |

Important rules:

1. A subscriber must receive **onSubscribe(subscription)** before **onNext**. It typically keeps the subscription and calls **request(n)** with a positive `n`.
2. Each **request(n)** call *adds* `n` to the requested-but-not-yet-received count; it does not reset the window to `n`. **request(0)** or a negative number is a protocol error and results in **onError(IllegalArgumentException)** according to the Subscription contract.
3. A publisher must not send more **onNext** signals than the total remaining effective demand. **Long.MAX_VALUE** usually represents effectively unbounded demand, but **does not mean an infinite buffer**.
4. A subscriber can call **cancel()**; stopping delivery is best-effort, and signals may still be in flight. A cancelled subscriber does not necessarily receive a terminal callback.
5. Signals and callbacks must respect the ordering of each individual subscription. Do not assume multiple subscribers run at the same speed or on the same thread.

**SubmissionPublisher<T>** is the built-in Flow implementation in the JDK: it uses an Executor to deliver events asynchronously to each subscriber; **each subscriber has an independent buffer**. The **maxBufferCapacity** parameter in the constructor is the requested ceiling for *each buffer*, not a shared total quota for the entire publisher. The effective capacity may be rounded up to a power of 2; use **getMaxBufferCapacity()** to check the actual limit. **Flow.defaultBufferSize()** provides a reference starting value, not a configuration suitable for every workload.

**Important distinctions:**
- A subscriber that has requested many items is not necessarily processing fast; the **onNext** callback may take a very long time.
- A producer returning quickly from **submit** does not mean the element has finished processing; the method may only have enqueued the element.
- A per-subscriber buffer protects against local bursts, but with **submit**, a single slow subscriber can still stall the shared submission path when its buffer is full.

## 3. What Happens When the Buffer Is Full?

The JDK provides two API groups with different policy semantics:

| Emission Method | When Subscriber Buffer Is Full | Return Value and Meaning |
| --- | --- | --- |
| **submit(item)** | Waits until space is available; the waiting behavior is *uninterruptible* per the API documentation. | Estimate of the maximum lag among subscribers; not the number of processed items. |
| **offer(item, onDrop)** | Attempts to publish immediately; if space is insufficient, may drop the item for full subscribers. | A negative number is the negated drop count; a non-negative number is the estimated maximum lag. |
| **offer(item, timeout, unit, onDrop)** | Waits for a bounded duration when resources are unavailable, then handles via `onDrop`; may involve thread interruption. | Same convention: negative indicates drops, non-negative indicates estimated lag. |

In both **offer** overloads, the **onDrop(subscriber, item)** callback runs when publishing encounters a full buffer. Returning **false** accepts dropping the element for that subscriber; returning **true** allows retrying delivery **once**, with no guarantee that the retry will succeed. The callback should be short and avoid time-consuming or blocking work because other publisher operations may be blocked while the callback runs. With multiple subscribers, an element may reach one subscriber while being dropped for another; do not infer atomic delivery across the whole group.

**Crucial:** **offer + onDrop** in **SubmissionPublisher** does not automatically implement a "drop oldest element" policy. It handles the failure when publishing the **currently offered element**. To implement **drop-oldest**, coalesce by key, or keep only the latest element, you need to design a custom queue/operator; do not describe `onDrop` as a command that removes from the head of the queue.

An **offerResult < 0** value indicates that drops occurred during that call; you cannot use a non-negative return value to conclude zero lag or fully synchronous processing. The **estimateMaximumLag()** and **estimateMinimumDemand()** methods are intended for observing trends and may return stale approximate snapshots; do not use them as exact synchronization conditions.

## 4. Choosing a Policy for Slow Consumers

There is no single universally optimal policy. The decision depends on data loss tolerance, ordering requirements, latency, and how long the producer is allowed to wait.

| Policy | Behavior | Best For | Trade-offs / Notes |
| --- | --- | --- | --- |
| **Block / backpressure producer** | Producer waits for space, e.g., **submit**. | Workloads that must retain all items and where the producer can tolerate waiting. | Can increase latency; strictly avoid blocking latency-sensitive threads or threads responsible for draining the buffer. |
| **Bounded wait then drop/fail** | Waits up to a limit with **offer(timeout, …)**. | Systems with deadlines that prioritize not hanging the producer indefinitely. | A timeout does not guarantee exact end-to-end latency across multiple subscriptions or stages. |
| **Drop newest** | Discards the new event when full. | Telemetry, sampling, or skippable updates. | Loses events; requires counting drops and clearly documenting semantics for users. |
| **Drop oldest / keep latest** | Discards old values, prioritizing the newest value. | Latest-state values such as progress or sensor readings. | Requires custom queue/logic; unsuitable for transaction logs that must preserve complete ordering. |
| **Coalesce / deduplicate** | Merges multiple updates with the same key into a single state. | UI state, overwritable measurements. | Must define merge logic, synchronization, and preserve semantics. |
| **Sample / throttle** | Reduces frequency before reaching the subscriber. | Dashboards, observability signals. | Intentionally reduces resolution; must distinguish sampling from random overload drops. |
| **Fail fast / cancel** | Stops the subscriber or pipeline when a threshold is exceeded. | Systems that treat overload as an error to detect immediately. | Requires clear error reporting, retry, and recovery mechanisms. |
| **Durable queue / spill to disk** | Writes to durable storage and consumes later. | Events that must not be lost, where producer and consumer lifecycles need decoupling. | Introduces latency, storage limits, synchronization, retries, duplicates, and ordering management. |

You should write down an **overflow contract** before implementing: which elements may be lost, who may block, the maximum block duration, maximum backlog, action on timeout, and how to observe it. For data that requires complete delivery, do not choose silent dropping. For continuously updated state data, keeping the "latest" may be more reasonable than trying to deliver every stale sample.

### Scenario Examples

- **Audit events / payment commands:** must not be silently dropped; use backpressure with a wait limit and/or a durable queue, with retry/idempotency mechanisms.
- **CPU metrics updated 100 times/second for a UI that renders 10 times/second:** sampling or coalescing is appropriate because stale states quickly lose value.
- **Batch analytics pipeline:** bounded queue + upstream concurrency limit; if the consumer is persistently slow, slow down the producer or scale up consumer capacity.
- **Multiple different subscribers:** one subscriber needs complete data, another only needs the latest. Do not force conflicting requirements into a single drop policy.

## 5. Java 17+ Example: Demonstrating a Full Buffer and Controlled Drop

The following program creates a **SubmissionPublisher** with one subscriber, **maxBufferCapacity = 1**, and a single-thread Executor. The subscriber intentionally pauses on element **A** using a `CountDownLatch`, creating a controlled state to demonstrate **B** occupying the buffer while **C** is dropped. This is a test simulation of slowness, not a pattern for blocking **onNext** in real applications.

Save as **BoundedFlowDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedFlowDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch enteredA = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        List<String> received = new CopyOnWriteArrayList<>();
        AtomicInteger drops = new AtomicInteger();

        try {
            try (SubmissionPublisher<String> publisher =
                         new SubmissionPublisher<>(executor, 1)) {

                publisher.subscribe(new Flow.Subscriber<>() {
                    private Flow.Subscription subscription;

                    @Override
                    public void onSubscribe(Flow.Subscription s) {
                        this.subscription = s;
                        s.request(1);
                    }

                    @Override
                    public void onNext(String item) {
                        received.add(item);
                        if (item.equals("A")) {
                            enteredA.countDown();
                            try {
                                releaseA.await();
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                                subscription.cancel();
                                completed.countDown();
                                return;
                            }
                        }
                        subscription.request(1);
                    }

                    @Override
                    public void onError(Throwable error) {
                        completed.countDown();
                    }

                    @Override
                    public void onComplete() {
                        completed.countDown();
                    }
                });

                publisher.submit("A");
                if (!enteredA.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Subscriber chua nhan A");
                }

                publisher.submit("B"); // A is being processed; B is in the buffer.
                int offerResult = publisher.offer("C", (subscriber, item) -> {
                    drops.incrementAndGet();
                    return false;      // Accept dropping C, do not retry.
                });

                releaseA.countDown();
                publisher.close();
                if (!completed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Subscriber chua ket thuc");
                }

                System.out.println("received=" + received);
                System.out.println("drops=" + drops.get());
                System.out.println("offerResult=" + offerResult);
            }
        } finally {
            releaseA.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac BoundedFlowDemo.java
java BoundedFlowDemo
~~~

Stdout on a normal run:

~~~text
received=[A, B]
drops=1
offerResult=-1
~~~

**Step-by-step explanation:**

1. **onSubscribe** requests 1 element, so **A** is delivered to **onNext**. The **enteredA** latch confirms that A has left the queue and the callback is waiting.
2. While A is held in the callback, the publisher emits **B** into the remaining buffer slot. Since the buffer capacity is 1, the buffer is now full.
3. **offer("C", …)** does not wait indefinitely: the callback returns **false**, so C is dropped and the result is **-1** because one subscriber dropped it.
4. Main releases the latch for A; the subscriber requests more demand, processes B, and receives **onComplete** after **close()**. **completed.await** ensures results are printed only after the callbacks finish.
5. **ExecutorService** is shut down in `finally` to avoid thread leaks. Latches have timeouts when waiting for setup/completion; the latch intentionally blocking A is only to create a deterministic test.

In real applications, do not hold the delivery thread in **onNext** just to wait on long I/O or rely on thread scheduling. When processing is slow, consider offloading tasks to a bounded executor, managing demand based on completion, and defining where backpressure is absorbed. If the callback hands off work to another queue and immediately requests more, that secondary queue can grow unboundedly if not capped.

## 6. Window-Based Demand Control

Calling **request(Long.MAX_VALUE)** is appropriate when the subscriber can genuinely receive very fast or the workload is already bounded at another layer. For slow consumers, grant demand in small batches and replenish as elements are processed. A practical approach:

- Choose **window = N** based on the amount of work that can be safely handled.
- In **onSubscribe**, call **request(N)**.
- After every batch of **N/2** processed elements, call **request(N/2)** to replenish. At any point in time, unfulfilled demand is kept controlled by the windowing algorithm.
- If processing asynchronously, only replenish demand **after** the work actually completes or capacity is available in the downstream queue; do not treat simply enqueuing into an internal queue as completion.

Example of **window 8** logic for a synchronous subscriber, written as a separate class in a real program (the snippet below illustrates how demand is granted; the **process** method represents business logic you must implement):

~~~java
final class WindowSubscriber<T> implements Flow.Subscriber<T> {
    private Flow.Subscription subscription;
    private int processedSinceRequest;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(8);
    }

    @Override
    public void onNext(T item) {
        process(item); // Complete synchronously before granting more demand.
        if (++processedSinceRequest == 4) {
            processedSinceRequest = 0;
            subscription.request(4);
        }
    }

    private void process(T item) {
        // Process business logic synchronously, with bounded resources.
    }

    @Override
    public void onError(Throwable error) {
        error.printStackTrace();
    }

    @Override
    public void onComplete() {
        // Completed.
    }
}
~~~

The snippet requires **import java.util.concurrent.Flow;** and must be used with a publisher to form a complete program; it has no **main** method of its own. **window 8** is not a universal constant. Tune it according to bursts, processing time, concurrency needs, and actual heap. If an **onNext** fails, an appropriate error/cancel policy is needed; do not assume the runtime will safely retry automatically.

### Demand Does Not Replace Every Queue Limit

Suppose Subscriber A calls **request(8)** but takes 2 seconds to process each item; Subscriber B calls **request(Long.MAX_VALUE)** and processes fast. You might choose a buffer of 16 per subscription; these are two limits with different purposes. If the producer exceeds A's processing capacity, A's buffer still fills up and **submit** will have to wait even though B is idle. Furthermore, if A offloads work from **onNext** into an unbounded secondary queue, the small Flow buffer no longer protects total system memory. Bounds must be enforced at **every asynchronous boundary**.

## 7. Calculating Capacity and Wait Thresholds from Workload

First, measure the key quantities:

- **R_in**: average and peak arrival rate, in items/second.
- **R_out**: sustainable consumer processing throughput.
- **T_burst**: burst duration to absorb.
- **S_item**: actual in-memory size of one element; measure it rather than just taking the JSON size on the wire.
- **N_sub**: number of subscribers and fan-out characteristics.
- **L_target**: maximum allowable latency.

When `R_in > R_out` during a burst, estimate the number of accumulated items:

~~~text
backlog_burst ≈ max(0, R_in - R_out) × T_burst
memory_payload ≈ capacity × S_item × N_sub
~~~

For example, with a burst of 1,200 items/second for 5 seconds and a consumer processing 900 items/second, the backlog grows by about **1,500 items**. A buffer of 256 is not enough to hold the entire burst without slowing down or dropping. Choosing 2,048 can absorb this burst, but only makes sense if the consumer can catch up when input subsides. With multiple subscribers, do not mechanically multiply every peak under the same assumption; size each buffer individually and measure heap, because items may be shared by reference while queue structures are separate.

**Latency check:** a queue of 2,000 items with a drain throughput of 500 items/second corresponds to about **4 seconds** just to drain the queue if no new items arrive. Use Little's Law (`L = λW`) for steady-state flows under appropriate conditions, and do not apply it arbitrarily to short bursts. Large buffers help reduce drops but can prolong wait times and retain stale data longer.

Set concrete deadlines—for instance, a producer may only wait 20 ms, then fail/reject or drop depending on the nature of the data. Without wait thresholds, a backlog can turn into unpredictable latency. For systems requiring complete data that cannot catch up, endlessly increasing the queue only delays overload.

## 8. Multi-Subscriber, Executor, and Common Bottlenecks

**Fan-out:** each subscriber of **SubmissionPublisher** has its own buffer and demand. A slow consumer can cause drops only on its own subscription when using **offer**, whereas with **submit**, the entire producer call can block because any single full buffer stalls it. Clearly define the delivery contract: must all subscribers receive complete data, or can each subscriber choose a different loss policy?

**Executor:** `SubmissionPublisher` delivers callbacks asynchronously via an Executor. The thread count, Executor task queue, and callback duration all affect latency. The constructor needs an Executor capable of running tasks independently; do not design a single-thread executor and then block that same thread with a task waiting on another task in the same executor. The executor's thread pool/queue must also be sized and bounded for the workload; do not treat `maxBufferCapacity` as the ceiling for all consumed resources.

**Blocking:** **submit** can block the producer. If the producer runs on a latency-sensitive thread or a callback needs that exact thread to free up space, a stall or deadlock by design will occur. Use timeouts or an appropriate handoff mechanism in such cases. Virtual threads (if using a supported Java version) can make blocking cheaper in terms of OS threads in some scenarios, but they **do not increase consumer throughput, do not replace capacity, and do not make backlogged data disappear**.

**Exceptions and lifecycle:** **close()** signals completion to current subscribers; **closeExceptionally(error)** signals an error. If **onNext** throws an exception or the Executor rejects a task, an error reporting/monitoring path per the API contract is required; never assume an item was successfully delivered to all subscribers. After **close()**, new `submit`/`offer` calls are invalid. Clean up any application-owned Executor resources.

## 9. Observing Overload and Verifying Policies

A complete design needs at least:

1. **Measure input/output rates:** items produced and items successfully processed per second.
2. **Measure latency:** time from creation to completion, including queue wait time; record percentiles rather than just averages.
3. **Measure backlog/lag:** capacity, lag, or pending work at each stage; `SubmissionPublisher`'s **estimate...()** methods are only approximations for monitoring.
4. **Count overflow events:** dropped items, timeouts, retries, cancellations, callback errors, and Executor rejections; tag them with the corresponding policy.
5. **Monitor memory:** heap usage, GC pauses, allocation rate, and the number of auxiliary tasks/queues.
6. **Real load testing:** consumer slower than producer for several minutes; burst then recovery; multiple subscribers at mismatched speeds; one subscriber stopping requests; mid-stream errors; shutdown with remaining backlog.

**Verification checks to have:** when full, does the producer block past its deadline? Is any mandatory data lost? If dropping occurs, is it newest or oldest items? Do remaining subscribers continue operating? When the source slows down, does the backlog return to normal? If you cannot answer these, the overflow policy has not been sufficiently tested.

## 10. Common Pitfalls

- **Confusing `request(100)` with a buffer of capacity 100.** `request` only increases demand, while the buffer is determined by the publisher.
- **Increasing `maxBufferCapacity` indefinitely when the consumer cannot keep up long-term.** That only delays overflow at the cost of higher heap usage and latency.
- **Calling `request(Long.MAX_VALUE)` immediately and pushing to an unbounded internal queue.** Flow has demand, but the overall pipeline still lacks backpressure.
- **Assuming `offer` always delivers to every subscriber.** A negative result indicates drops; each subscription can succeed or fail independently.
- **Assuming returning `true` in `onDrop` guarantees redelivery.** There is only one retry attempt, and it can still fail.
- **Assuming `SubmissionPublisher`'s `onDrop` is drop-oldest.** Evicting older elements requires implementing a specific policy yourself.
- **Blocking in `onNext` or `submit` on a latency-sensitive path without measuring.** This can propagate stalls to other threads or cause deadlocks.
- **Using `estimateMaximumLag` as a synchronization lock or absolute condition.** The API only promises an estimated value for observability.
- **Dropping events that require ordering and completeness without a data contract.** This is a business-logic bug even if the program throws no errors.
- **Forgetting to close the publisher/executor or handle `onError`/`cancel`.** Causes resource leaks or hung pipelines when errors occur.

## 11. Quick Selection Workflow

**Step 1 — classify the data:** does it need to be accurate and complete, or is only the latest update needed? Only choose dropping when you know which data loss is acceptable.

**Step 2 — calculate rates and bursts:** measure `R_in`, `R_out`, processing time, and heap limits; estimate backlog and drain time. You may consider increasing consumer concurrency, but only when business logic allows parallelism and ordering is still preserved.

**Step 3 — set end-to-end bounds:** per-subscriber buffers, executor queues, custom queues, active task counts, and publisher/subscriber counts. A single unbounded queue undermines the entire protection.

**Step 4 — choose the behavior when full:** block, bounded wait, drop latest/newest, drop oldest, coalesce by key, or reject. If data cannot be lost and the consumer is persistently slow, throttle the source or persist durably.

**Step 5 — document and test the contract:** verify request windows, overflow behavior, error callbacks, cancellation, shutdown, and alert metrics. Test with genuinely slow subscribers and multiple subscribers.

## Official Documentation

- Java SE 21 — **Flow**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 21 — **Flow.Subscription**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 21 — **SubmissionPublisher**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html

**Conclusion:** In Java Flow, **request(n)** manages receiving demand, **buffer capacity** limits pending elements, and the **submit/offer/overflow** policy determines what happens when consumers are slow. Clearly define whether waiting or data loss is permitted, measure actual throughput and backlog, and enforce bounds at every queue in the pipeline.