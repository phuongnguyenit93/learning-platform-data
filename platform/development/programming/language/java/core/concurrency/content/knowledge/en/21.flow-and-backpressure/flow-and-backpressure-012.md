# SubmissionPublisher.submit() vs. offer(): Handling Slow Subscribers and Full Buffers

> Topic: **Flow & Backpressure** in Java, focusing on `java.util.concurrent.Flow` and `SubmissionPublisher<T>` (available since Java 9). The examples use **JDK 17+** and depend only on Java SE; no specific framework is covered.

## 1. The Problem: Producer Faster Than Subscriber

`Flow.Publisher<T>` emits items to `Flow.Subscriber<T>` instances. A subscriber receives a `Flow.Subscription` from `onSubscribe`, then uses `subscription.request(n)` to signal demand. The publisher may only emit `onNext` up to the requested amount; each item delivered to `onNext` consumes one unit of demand.

`SubmissionPublisher<T>` is the JDK's built-in Publisher implementation. It accepts items from a producer and **delivers them asynchronously** to subscribers using an `Executor`. Each subscriber has **its own buffer**, so if a subscriber processes slowly or does not request more data, that subscriber's buffer can fill up.

```text
producer -- submit/offer(item) --> SubmissionPublisher
                                  |              |
                                  v              v
                             buffer S1      buffer S2
                             [full]         [has space]
                                  |              |
                                  v              v
                           subscriber S1  subscriber S2
                           slow/no demand fast/requesting
```

The decision to make: when **at least one subscriber cannot keep up**, should the producer **wait to retain the data** or **accept dropping an item for the overloaded subscriber**? Two primary APIs support these two choices:

- `submit(item)`: waits when buffer resources are insufficient to emit the item to current subscribers.
- `offer(item, ...)`: attempts to emit, potentially dropping for full subscribers; the timed offer variant can wait for a period before dropping.

**Backpressure here is not just buffer size.** `request(n)` indicates the number of `onNext` callbacks allowed to be delivered according to subscriber demand. Buffers handle temporary producer/consumer speed mismatches; when backlog exceeds buffer capacity, the producer must choose a policy: wait, drop, rate-limit, or persist elsewhere.

## 2. Exact Comparison of the Overloads

| API | When a subscriber's buffer is full | Drop capability | When to use |
|---|---|---|---|
| `int submit(T item)` | **Blocks uninterruptibly** until resources are available to accept the item | Does not drop items solely due to a full buffer | Data must be retained in the processing stream, and the producer is allowed to experience backpressure |
| `int offer(T item, BiPredicate onDrop)` | Attempts immediate emission, does not wait for a full buffer; runs drop handler if needed | Yes; handler can retry **once** by returning `true` | Do not want the producer blocked by a slow subscriber, and can handle item loss |
| `int offer(T item, long timeout, TimeUnit unit, BiPredicate onDrop)` | Waits for buffer space **up to the timeout or until interrupted**, then may drop | Yes; handler can retry once | Want a bounded wait before applying the drop policy |

**Not synonymous:** calling `offer` does not mean it will *definitely* drop, and calling `submit` does not mean it will *definitely* block. When buffers have space, both can emit successfully and return very quickly.

One slow subscriber is enough to cause the producer's `submit` to wait, even if other subscribers are keeping up. Conversely, `offer` can emit the item to fast subscribers and drop it only for the overloaded subscriber. Depending on the application contract, having subscribers see different sets of items may be acceptable or a serious bug.

These methods **enqueue items into the asynchronous delivery path**; they do not mean every subscriber's `onNext` has finished executing when the method returns.

## 3. Per-Subscriber Buffers and Demand: Why Do Subscribers Fill Up?

### 3.1. How `request(n)` Affects Item Delivery

Example of a subscriber:

```java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}

@Override
public void onNext(String item) {
    process(item);
    subscription.request(1);
}
```

This is only a **fragment**: it assumes the class already has a `subscription` field and a `process` method. It requests **one item at a time**, then requests the next upon finishing processing. If `process` is slow, the subscriber replenishes demand slowly and backlog can grow. If `request` is never called, `onNext` is not delivered, and already-accepted items can sit in the buffer until it fills up.

If a subscriber calls `request(Long.MAX_VALUE)`, that is a very large demand, **not** an infinite buffer. If `onNext` takes 200 ms while the producer sends 1,000 items per second, the queue can still fill up.

Do not use `request(0)` or `request` with a negative number: these are invalid protocol requests and lead to error signals under the Flow contract. After `cancel()`, the subscriber no longer receives new items for that subscription.

### 3.2. `maxBufferCapacity` Is **Per Subscriber**

```java
ExecutorService delivery = Executors.newFixedThreadPool(4);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(delivery, 16);
```

*Illustrative snippet in a program that imports `java.util.concurrent.*`; in practice, the publisher must be closed and the executor shut down properly according to their lifecycle.*

The number `16` in the constructor is the **requested capacity per subscriber**, not the total item count across the entire publisher. The actual enforced capacity may be rounded up to a power of 2 or capped by implementation limits; call `publisher.getMaxBufferCapacity()` to check the actual capacity.

If there are 100 subscribers, there can be many buffers active concurrently; memory, subscriber count, and the size of each item must be considered. Buffers help absorb short bursts; they **cannot cure** long-term speed mismatches. Setting an enormous buffer may only mask a slow subscriber at the cost of higher RAM usage and latency.

### 3.3. One Item Being Processed and One Item Remaining in the Buffer

A subscriber may be executing `onNext(item1)` for a long time while `item2` waits in the buffer. Even when demand is not exhausted, executor speed and callback execution time still limit how fast the buffer drains. Do not measure only demand while ignoring **`onNext` completion rate**.

## 4. `submit(item)`: Waiting to Retain Items, Trading Off Producer Latency

Syntax:

```java
int lag = publisher.submit(item);
```

- The item must be **non-`null`**; submitting when the publisher is closed throws `IllegalStateException`.
- When there is not enough space in any current subscriber's buffer, `submit` may **block uninterruptibly**. `Thread.interrupt()` is **not** guaranteed to make this call terminate immediately.
- The return value is an **estimate of maximum lag**: the number of items submitted but not yet consumed by the slowest subscriber; at least 1 if there are subscribers, 0 if there are none. It is not the number of items successfully processed and not the number of milliseconds waited.
- If the executor rejects the task (for example, `RejectedExecutionException`), the call may throw an exception; when an executor error occurs, there is no guarantee all subscribers received the item.

**When appropriate:** data must pass through every subscriber in a short pipeline, the producer can wait, upstream bounds are in place, and proper cancellation/shutdown mechanisms exist. The fact that `submit` preserves delivery when **buffers are full** does not mean it guarantees durability if the JVM crashes, a subscriber cancels, a callback fails, or the publisher closes abnormally.

**Risks:** if a subscriber never calls `request` again, hangs in `onNext`, or the executor has no free threads, `submit` can wait for a very long time or indefinitely. Do not call `submit` on a UI thread or a request-handling path with strict deadlines if backpressure cannot be controlled. In particular, avoid repeatedly calling `submit` from inside an `onNext` callback when it is occupying a worker thread the publisher needs to drain the buffer: this can create a wait cycle/deadlock.

`submit` does not take a timeout parameter. If a bounded-latency policy is needed, look at timed `offer`; if stronger cancellation handling is required, build a stop/cancel mechanism across the entire pipeline rather than expecting interrupts alone to unblock the producer.

## 5. `offer(item, onDrop)`: Non-Blocking, Potential Item Loss

Syntax:

```java
int status = publisher.offer(event, (subscriber, rejectedEvent) -> {
    // Record metric / notify overload event.
    return false;  // Do not retry: drop item for the full subscriber.
});
```

*This snippet requires compatible `publisher`, `event`, and generic types; it is not a standalone program.*

When unable to emit to a subscriber due to buffer limits, `onDrop` receives the **specific subscriber** and the rejected item. Boolean return value:

- `false`: do not retry; the item is dropped for this subscriber.
- `true`: request **a single retry** of the offer for this subscriber; this does **not** guarantee the retry will succeed. If still full, the item may be dropped.

If the handler is `null`, the call can still drop items without invoking a handler. The handler should be **very short, non-blocking, and free of complex re-entrant calls back into the publisher**: the API documentation states that other calls to the publisher from other threads will be blocked while the handler runs. A slow handler propagates delays to other producers as well.

A sound strategy can be counting drops, rate-limited logging, choosing to cancel a faulty subscriber, or sending a notification over a side channel. Do not assume `onDrop` is a safe place for infinite retries, long sleeps, or waiting on the very buffer it is handling.

## 6. `offer(item, timeout, unit, onDrop)`: Bounded Wait

Example:

```java
int status = publisher.offer(
        event,
        100, TimeUnit.MILLISECONDS,
        (subscriber, dropped) -> {
            droppedCounter.increment();
            return false;
        }
);
```

*This fragment requires variables `publisher`, `event`, `droppedCounter` and import `java.util.concurrent.TimeUnit`.*

The timed offer overload allows the publisher to wait for subscriber resources for the duration of the timeout or until the calling thread is interrupted. If the timeout expires or the thread is interrupted and the subscriber still cannot accept the item, the drop handler is applied; the handler still only has the right to request **one** retry. The API explicitly notes that the handler can distinguish an interrupt from a timeout via the current thread's interrupt flag.

**Note:** the timeout bounds waiting for resources within the `offer` call itself; it does not guarantee that the `onNext` callback finishes before a deadline—business logic needs a separate processing timeout. Actual total elapsed time is also subject to scheduler behavior and handler execution time; do not use this timeout as a substitute for an end-to-end deadline.

Typical policies:

| Loss tolerance | Strategy |
|---|---|
| Cannot drop items | Do not drop silently; consider `submit` with controlled backpressure, or durable storage/ack at another layer |
| Intermediate updates can be dropped (e.g., UI progress) | `offer(..., onDrop -> false)`; record drop metrics |
| Small delay allowed, but not unbounded | Timed `offer` with explicit drop handling |
| Only the latest state matters | Design a coalescing/latest-state mechanism in the application; `offer` itself **does not replace old items with new ones** |

## 7. Reading the Returned `int` Correctly

Both `submit` and `offer` return an `int`, but **their meanings are not identical**.

### `submit`

- Returns an **estimate of maximum lag** across subscribers at the time of measurement.
- No subscribers: `0`.
- With subscribers: at least `1`, including the item just submitted.
- Does not directly reflect exact queue length or the number of items that have actually completed `onNext`.

### `offer` (both overloads)

- `status >= 0`: no drops recorded; the value is the **estimated maximum lag** (`0` if there are no subscribers).
- `status < 0`: its absolute value represents the **number of failed delivery attempts to subscribers** (drops/failed attempts per the API contract), not wait time, not a subscriber ID, and not negative backlog.
- When the handler returns `true` to retry, **you must still check the final status**; never conclude that a retry always succeeds.

```java
int status = publisher.offer(item, (subscriber, rejected) -> false);
if (status < 0) {
    int drops = -status;
    // Record drop count; handle according to business requirements.
} else {
    int estimatedMaxLag = status;
    // Use for monitoring only, not as an exact synchronization signal.
}
```

*This is a fragment and cannot compile standalone without declaring `publisher` and `item`.*

The observation APIs `estimateMaximumLag()` and `estimateMinimumDemand()` also return **estimates**; they can become stale when multiple producers/consumers run concurrently. Use them for **monitoring/tuning**, not as a locking protocol like "if lag is less than X, `submit` will definitely not block."

## 8. Runnable Java 17+ Example: Intentionally Filling the Buffer

The following example makes a subscriber slow using `CountDownLatch` to ensure the first item **is stuck inside `onNext`**. The buffer is configured with capacity 1; the second item waits in it. Therefore, the third item sent via `offer` is dropped, while the fourth item sent via `submit` must wait until the subscriber is unblocked. The code uses two separate executors to avoid blocking the delivery worker itself.

Create the file **`SubmissionPublisherPressureDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.Future;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionPublisherPressureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        ExecutorService producer = Executors.newSingleThreadExecutor();
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch inFirstOnNext = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(delivery, 1);

        Flow.Subscriber<Integer> slow = new Flow.Subscriber<>() {
            private Flow.Subscription subscription;

            @Override
            public void onSubscribe(Flow.Subscription s) {
                subscription = s;
                s.request(Long.MAX_VALUE);
                subscribed.countDown();
            }

            @Override
            public void onNext(Integer value) {
                if (value == 1) {
                    inFirstOnNext.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }

            @Override
            public void onError(Throwable error) {
                System.err.println("Subscriber failed: " + error);
            }

            @Override
            public void onComplete() {
                // Normal completion.
            }
        };

        try {
            publisher.subscribe(slow);
            subscribed.await();

            publisher.submit(1);
            inFirstOnNext.await();  // Ensure onNext(1) is waiting on release.

            publisher.submit(2);    // One buffer slot is now occupied.
            int offered = publisher.offer(3, (s, item) -> false);
            System.out.println("offerDropped=" + (offered < 0));

            Future<Integer> pending =
                    producer.submit(() -> publisher.submit(4));
            // Whether the producer task has started or is waiting its turn,
            // it cannot complete submit(4) while the slot remains full.
            System.out.println("submitFinishedWhileFull=" + pending.isDone());

            release.countDown();    // Release the callback to drain the buffer.
            pending.get(5, TimeUnit.SECONDS);
            System.out.println("submitFinishedAfterRelease=true");
        } finally {
            release.countDown();
            publisher.close();
            producer.shutdown();
            delivery.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac SubmissionPublisherPressureDemo.java
java SubmissionPublisherPressureDemo
```

With `maxBufferCapacity=1` and the `CountDownLatch` checkpoints as written, expected stdout under normal execution is:

```text
offerDropped=true
submitFinishedWhileFull=false
submitFinishedAfterRelease=true
```

Explanation:

1. The subscriber calls `request(Long.MAX_VALUE)`, but `onNext(1)` intentionally waits. Granting unlimited demand **does not** make the consumer process faster.
2. Once item 1 is known to be inside the callback, item 2 can wait in the single buffer slot; `offer(3, handler -> false)` sees no space left and drops it.
3. `submit(4)` runs on another producer thread. While the subscriber is still held by the latch, emitting item 4 cannot complete, so the producer experiences backpressure. After `release.countDown()`, the worker finishes `onNext(1)`, continues draining the buffer, and `submit(4)` can return.
4. `Future.get(5, SECONDS)` is **the demo program's wait limit**, not a way to make the inner `submit` call interruptible or timed. If the environment is abnormally congested, `get` may throw `TimeoutException` instead of printing the final line.
5. `finally` releases the latch and closes the publisher/executors, preventing a demo thread from being held indefinitely by a waiting callback.

In practice, worker count, scheduling, and resource limits cause performance to vary. Do not use this micro-demo as a throughput benchmark. If you modify the code (e.g., removing latches), the return values or output ordering are **no longer** guaranteed to be the same.

## 9. With Multiple Subscribers: What Does One Slow Subscriber Drag Down?

Suppose there are two subscribers `fast` and `slow`, each with its own buffer:

```text
       item X
         |
  SubmissionPublisher
       /       \
   fast          slow
   buffer 0/8    buffer 8/8
   receives X    no space left
```

- With `submit(X)`, the producer can be blocked because of `slow`. `fast` may already have had the item delivered, yet the producer call is still waiting on the other path.
- With `offer(X, handler -> false)`, `fast` can receive X while `slow` has X dropped. `onDrop` identifies the specific subscriber that dropped, allowing you to record metrics or adjust policy.
- If drops are unacceptable, the application must define whether a slow subscriber is allowed to slow down all subscribers or should be isolated from the pipeline. Some systems choose to isolate a subscriber with its own queue/publisher or cancel the slow subscription, but data semantics must be decided explicitly.
- If a new subscriber subscribes after X has already been published, `SubmissionPublisher` does not automatically replay historical X; it is not a message broker with replay/durable logs.

Do not run all subscribers and producers on the same executor with too few threads when callbacks can block and producers also need to wait, as this easily causes **thread starvation**. Choose an executor based on workload, subscriber count, and callback behavior; the Java API has a default option based on `ForkJoinPool.commonPool()`, which does not mean every workload suits the default pool.

## 10. Choosing a Backpressure Policy by Business Requirements

| Workload | Recommendation | Notes |
|---|---|---|
| Events must be complete, no loss allowed | `submit` in a pipeline with upstream bounds or durable storage/ack | If a subscriber stops requesting, the producer may wait indefinitely |
| Telemetry/values that can be resampled | `offer` and count drops | Accept losing data points; do not pretend delivery is guaranteed |
| Price updates/UI refresh, only latest matters | Design intentional coalescing/latest-value | `offer` does not automatically discard older items in favor of newer ones |
| Producer has tight deadlines | Timed `offer`, timeout, and fallback policy | The timeout does not bound `onNext` execution time |
| Multiple subscribers with large speed disparity | Group/isolate subscribers, measure per-subscriber lag/drop | One slow subscriber can stall `submit` for everyone |
| Every item must be retried until acknowledged | Design application-level queue/durable log + ack/retry | `onDrop -> true` only retries once; it does not guarantee delivery |

The goal is **load control**. Whether you choose `submit` or `offer`, measure production rate, consumption rate, drop frequency, `submit` latency, subscriber lag, memory, and thread pool state. Do not increase buffer sizes indefinitely to avoid designing flow control.

## 11. Common Pitfalls

### Pitfall A: Forgetting `request(n)`

The subscriber registers successfully but never requests, so it never receives `onNext`. The producer keeps sending fast, buffers gradually fill up, and `submit` may hang. **Fix:** always store the `Subscription` and call `request` appropriately, replenishing demand as processing completes. If a subscriber intentionally stops receiving, there must be a system-level cancel/timeout/close pipeline mechanism.

### Pitfall B: Calling `request(Long.MAX_VALUE)` and Believing Backpressure Is Gone

Large demand only grants permission to deliver; it does not make `onNext` run faster. If the callback is slow, buffers still fill up. **Fix:** shed load, scale/change how callbacks are processed appropriately, or choose an explicit drop/backpressure policy.

### Pitfall C: Calling `submit` Inside a Callback That Depends on the Same Publisher

If a callback holds a delivery worker while the producer waits on that callback's own buffer, deadlock/starvation can occur. **Fix:** avoid synchronous call cycles, separate executors and wait paths, or offload tasks to a pipeline that does not depend on the current callback.

### Pitfall D: Assuming `onDrop -> true` Guarantees Retry Until Success

The handler only requests **one** retry attempt; it can still be dropped. **Fix:** check the return code, record metrics, and build a separate retry/ack mechanism if business requirements demand it.

### Pitfall E: Logging or Blocking for Long Periods Inside `onDrop`

Other producers may be blocked while the handler runs. **Fix:** only record lightweight metrics/counters, avoid network I/O or waiting on futures inside the handler; rate-limit logging instead of spamming per item at very high rates.

### Pitfall F: Treating `status < 0` as Milliseconds

That indicates drops; `status >= 0` is the estimated max lag. **Fix:** measure latency with a separate clock/metrics rather than inferring it from status.

### Pitfall G: Treating `getMaxBufferCapacity()` as a Total RAM Limit

Capacity is per subscriber; items can be large and subscriber counts can vary. **Fix:** account for total footprint, memory pressure, and backlogs. Track objects retained in buffers until consumed or canceled.

### Pitfall H: Using `offer` to Transmit Events That Must Not Be Lost

`offer` can drop items for full subscribers; it does not guarantee uniform delivery to all. **Fix:** use a lossless policy with downstream limits or durable storage/ack/replay at the appropriate layer.

### Pitfall I: Forgetting to Close the Publisher and Executor

`close()` marks completion and sends `onComplete` signals to current subscribers when signal-delivery conditions are met; submitting new items afterward is rejected. If a subscriber or executor is stuck, delivering the completion signal can also be delayed. **Fix:** manage executor lifecycle, `Subscription.cancel()`, and an explicit shutdown policy. Do not call `closeExceptionally` for normal completion; when the pipeline encounters a fatal error, `onError` can be emitted via `closeExceptionally(Throwable)`.

### Pitfall J: Using Estimated Metrics as Synchronization Conditions

`estimateMaximumLag()` and `estimateMinimumDemand()` are observational and can drift when multiple threads operate concurrently. **Fix:** use a `Semaphore`/bounded queue or another coordination mechanism if exact admission control is needed.

## 12. Checklist Before Adopting SubmissionPublisher in an Application

1. **Define data requirements**: must every item reach every subscriber, can items be dropped, or is ack/replay needed?
2. **Define demand**: when does the subscriber call `request`, and how are completed/pending/canceled states handled?
3. **Choose a policy**: `submit` (wait) or `offer` (can drop), or timed `offer` (bounded wait). Document the timeout and `onDrop` behavior.
4. **Set resource bounds**: per-subscriber buffer capacity, subscriber count, concurrency level, executor capacity, and total memory footprint.
5. **Test overload interactions**: subscriber not requesting, `onNext` blocking, executor saturation, interrupts, and publisher closing mid-submission.
6. **Monitor metrics**: measure drops, lag estimates, producer and `onNext` latency, subscriber count, and executor saturation.
7. **Write controlled tests**: use explicit latches/conditions to reproduce full buffers; avoid drawing conclusions from arbitrary `Thread.sleep` calls in tests.
8. **Provide real durability**: if durable delivery or retry-until-success is required, add a queue/durable log/ack; `SubmissionPublisher` alone does not do that for you.

## Official Documentation

- [Oracle Java 21 — SubmissionPublisher API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): exact specification of `submit`, both `offer` overloads, `onDrop`, and return codes.
- [Oracle Java 21 — Flow API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): Publisher–Subscriber–Subscription relationship, demand, and signals.
- [Oracle Java 21 — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request` and `cancel`.
- [Oracle Java 21 — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): invocation order of `onSubscribe`, `onNext`, `onError`, and `onComplete`.

**Key takeaway:** `submit()` shifts pressure from a full buffer onto **producer wait time**; `offer()` shifts it into **per-subscriber drop possibility**. `offer(timeout, ...)` allows a bounded wait before applying the drop policy. Neither method by itself solves faulty subscribers, under-provisioned executors, or durable delivery requirements.
