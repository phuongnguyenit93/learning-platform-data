# Thread Safety in Callbacks and Error Handling with the Java Flow API

> Scope: Java SE (Java 17+), specifically `java.util.concurrent.Flow` and `SubmissionPublisher`. This article does not cover Spring or Spring's reactive libraries.

## 1. The Problem to Solve

In the Publisher–Subscriber model, data is delivered through the callbacks `onSubscribe`, `onNext`, `onError`, and `onComplete`. With `SubmissionPublisher`, callbacks are typically invoked asynchronously on threads managed by an `Executor`. Therefore, a consumer must address three issues simultaneously:

1. **Is state thread-safe across threads?** Callbacks may update counters, lists, caches, or results that another thread is reading.
2. **Does it conform to the signal protocol?** Each subscription must properly manage `request(n)`, `cancel()`, and terminal signals.
3. **Where do errors occur, and who is responsible?** An item-level data error, an error originating from upstream, and an exception thrown out of a callback have different consequences.

`Flow` handles signal ordering and demand control; protecting **application state** and defining the **error recovery policy** remain the programmer's responsibility.

## 2. Callback Protocol and Error Semantics

| Method | Meaning | What to Maintain |
| --- | --- | --- |
| `onSubscribe(Subscription s)` | Receives control of the subscription; call `s.request(n)` to request items | `n > 0`; store the subscription according to its lifecycle |
| `onNext(T item)` | Processes a requested item | Do not share mutable state without protection; define how item errors are handled |
| `onError(Throwable error)` | Receives a **terminal** error signal from the publisher | Record the cause, release resources, and notify of the failure result |
| `onComplete()` | Receives a **successful terminal** signal | Finalize the result, release resources, and wake up waiting threads |
| `Subscription.cancel()` | Requests the publisher to stop emitting to the subscriber | Cancellation may not be immediate and is **not guaranteed** to be followed by `onComplete/onError` |

A valid subscription has a signal sequence of the form:

```text
onSubscribe
    |
    +-- request(n > 0) --> onNext --> onNext --> ... --> onComplete
    |                                      \
    |                                       +-----> onError (if upstream fails)
    +-- cancel() --------> stop emitting (best effort; may have no terminal signal)
```

`onError` and `onComplete` are mutually exclusive terminal signals. After a terminal signal, the publisher sends no further signals to that subscription. `request(0)` or `request(n < 0)` violates the protocol: the `Subscription` must result in `onError` with an `IllegalArgumentException`. `cancel()` is not a command synonymous with `onComplete()`.

## 3. What Does Flow Guarantee About Thread Safety?

### 3.1. Signals Are Serialized **Per Subscription**

The `Flow.Publisher` protocol requires that callbacks to the **same subscription** be delivered sequentially with a *happens-before* relationship. Therefore, if a subscriber has only a single valid subscription, does not expose that state to other threads, and does not spawn auxiliary tasks that concurrently modify the state, its callbacks can use ordinary internal fields without needing an explicit lock solely to guard against two concurrent `onNext` calls.

However, **sequential does not mean pinned to a single thread**. Subsequent callbacks may execute on different threads; do not rely on `ThreadLocal`, thread names, or the assumption that "callbacks always run on the main thread." With `SubmissionPublisher`, item delivery is typically executed asynchronously by an `Executor`.

### 3.2. What Flow Does *Not* Automatically Protect

- Two different subscribers/subscriptions can run callbacks in parallel. If they write to a shared `ArrayList`, `HashMap`, or counter, access must be coordinated.
- The thread calling `submit`, a metrics-monitoring thread, and callbacks can execute concurrently. The callback serialization rule does not make operations on external state safe.
- If `onNext` spawns a `CompletableFuture`, a task in a pool, or a new thread, that auxiliary task may run in parallel with the next callback. In that case, shared state requires an independent synchronization mechanism.
- A multi-step operation, such as "check remaining quota then increment count," does not become atomic merely because individual fields are `volatile`.

### 3.3. Choosing a Protection Mechanism by Data Type

| Scenario | Appropriate Approach | Reason |
| --- | --- | --- |
| State is only read/written inside callbacks of a single subscription | Plain fields, not shared externally | Signals are already serialized by the protocol |
| Status flag written by one thread and read by another | `volatile` or `AtomicBoolean` | Guarantees visibility of updates; atomic for operations like CAS |
| Concurrent counter | `AtomicLong`, `LongAdder` depending on requirements | Prevents lost updates like `count++` |
| Two fields must satisfy a joint invariant | `synchronized`/lock or atomic replacement of an immutable snapshot | Two separate atomics do not form a transaction |
| List/collection modified concurrently by multiple callbacks | Appropriate concurrent collection or lock | Prevents data races and structural corruption |
| External thread needs to wait for completion before reading the result | `CountDownLatch`, `CompletableFuture`, or a synchronized waiting mechanism | Both waits for the terminal signal and guarantees visibility |

For example, `volatile long count` still does **not** make `count++` an atomic increment. `AtomicLong.incrementAndGet()` is suitable for a single counter; if consistency between `accepted` and `rejected` is needed when taking a report snapshot, a shared lock or snapshot is required.

## 4. Backpressure and Callbacks Must Go Together

A subscriber receives items according to the **demand** granted via `request(n)`. An easy-to-understand and easy-to-verify approach is to keep at most one outstanding request:

1. In `onSubscribe`, call `request(1)`.
2. In `onNext`, finish processing the item.
3. If continuing, call `request(1)` to ask for the next item.

This approach is simple but incurs per-item overhead; high-throughput pipelines typically request in batches and replenish demand based on a threshold. **Demand does not mean the publisher never buffers**: `SubmissionPublisher` has a dedicated buffer per subscriber. `submit(item)` may block when there is no remaining capacity; `offer(...)` may drop items according to the configured policy. Do not use lag/demand estimates as synchronization primitives.

Avoid overly broad locks or slow I/O inside `onNext`: this slows down downstream demand replenishment and can cause backpressure upstream. In particular, do not hold an application-state lock while calling external code that might be reentrant, such as `request`, `cancel`, custom loggers, or third-party callbacks.

## 5. Distinguishing Three Error Categories

| Error | Example | How to Handle |
| --- | --- | --- |
| **Recoverable item error** | A disallowed negative value | `onNext` catches the expected exception, records/skips it or routes it to an error-handling flow, and issues the next demand according to policy |
| **Unrecoverable upstream error** | Corrupted data source that can no longer emit properly | Publisher emits `onError`; with `SubmissionPublisher`, call `closeExceptionally(cause)` |
| **Exception escaping a callback** | `onNext` throws an uncaught `RuntimeException` | Do **not** assume this becomes an upstream `onError`; check the specific publisher's contract. `SubmissionPublisher` cancels the subscription if a subscriber method throws an exception; an optional publisher handler may receive the `onNext` exception before cancellation |

`SubmissionPublisher.close()` signals normal completion via `onComplete()`; `closeExceptionally(error)` signals error completion via `onError(error)`. Once closed, subsequent close calls do not produce another terminal signal.

For a fatal error during item processing, choose a clear policy: cancel the subscription, report failure through a dedicated `CompletableFuture`/status channel, and clean up resources. Because cancellation is **not required** to emit a terminal signal, do not wait solely for `onError()` after `cancel()` to finish an application task. For ignorable errors, catch **the exact expected exception type**; do not indiscriminately `catch(Throwable)`, as doing so can swallow critical JVM errors.

In `onError` and `onComplete`, keep cleanup/finalization simple, controlled, and free of thrown exceptions. If cleanup can fail, log or record the error separately rather than turning the terminal path into a source of unhandled errors.

## 6. Java 17+ Example: Safe Subscriber, Backpressure, and Two Terminal Paths

Save the entire program to **`SafeFlowCallbacks.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class SafeFlowCallbacks {
    static final class RecordingSubscriber implements Flow.Subscriber<Integer> {
        private final AtomicLong total = new AtomicLong();
        private final AtomicInteger skipped = new AtomicInteger();
        private final AtomicReference<Throwable> terminalError = new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            try {
                if (item < 0) {
                    throw new IllegalArgumentException("negative input: " + item);
                }
                total.addAndGet(item);
            } catch (IllegalArgumentException expected) {
                skipped.incrementAndGet();
            } finally {
                subscription.request(1);
            }
        }

        @Override
        public void onError(Throwable error) {
            terminalError.set(error);
            finished.countDown();
        }

        @Override
        public void onComplete() {
            finished.countDown();
        }

        void awaitTermination() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for terminal signal");
            }
        }

        String report() {
            Throwable error = terminalError.get();
            String terminal = error == null ? "complete" : error.getClass().getSimpleName();
            return "total=" + total.get() + ", skipped=" + skipped.get()
                    + ", terminal=" + terminal;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        RecordingSubscriber success = new RecordingSubscriber();
        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(success);
            publisher.submit(10);
            publisher.submit(-7);
            publisher.submit(20);
        }
        success.awaitTermination();
        System.out.println("success: " + success.report());

        RecordingSubscriber failure = new RecordingSubscriber();
        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(failure);
            publisher.closeExceptionally(new IllegalStateException("source unavailable"));
        }
        failure.awaitTermination();
        System.out.println("failure: " + failure.report());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SafeFlowCallbacks.java
java SafeFlowCallbacks
```

Stdout output (verified on JDK 21; the code uses APIs available in Java 17):

```text
success: total=30, skipped=1, terminal=complete
failure: total=0, skipped=0, terminal=IllegalStateException
```

**Detailed Explanation:**

- `publisher.subscribe(success)` registers the subscriber; `onSubscribe` receives the `Subscription` and requests exactly one item. `submit` calls may occur before the callback executes, but the publisher manages delivery/demand.
- For `10` and `20`, `total.addAndGet` updates the sum. `-7` triggers an `IllegalArgumentException` **due to the example's business rule**, which is caught in `onNext`; the callback does not throw out to the publisher, so the stream continues.
- `finally { subscription.request(1); }` here demonstrates the policy of *continuing after a controlled data error*. For unrecoverable errors, do **not** use `finally` to request unconditionally; instead, branch to cancellation and mark the failure completion yourself.
- `try-with-resources` invokes `SubmissionPublisher.close()` on the success path; the subscriber receives `onComplete` after all valid emitted items.
- The failure path sends no items: `closeExceptionally` forwards `IllegalStateException` through `onError`. `total=0` and `skipped=0`.
- `AtomicLong`, `AtomicInteger`, and `AtomicReference` allow safe snapshot reads if observation from another thread is needed while the stream is running. The example also uses `CountDownLatch` to wait for the terminal signal before printing; writes occurring before `countDown` are visible after a successful `await`.
- `subscription` is a plain field because **only callbacks of a single subscription** access it in the example. If an external thread is allowed to cancel directly, design a safe publication mechanism for the subscription—such as `AtomicReference<Flow.Subscription>`—and coordinate cancel/termination state.

Note on the example's limitations: atomic counters protect individual updates, but they do not guarantee a multi-metric snapshot taken at a single point in time if read **while** data is still arriving. In this example, the report is read **after** the terminal signal, so there is no issue with a mutating snapshot.

## 7. When Multi-Field State Must Be Consistent

If callbacks from multiple subscriptions update aggregate metrics together, use a shared lock for both updates and snapshot reads. The example below is a **helper class snippet** meant to be placed in another program, not a standalone program with `main`:

```java
final class Metrics {
    record Snapshot(long accepted, long rejected) {}

    private long accepted;
    private long rejected;

    synchronized void record(boolean valid) {
        if (valid) {
            accepted++;
        } else {
            rejected++;
        }
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(accepted, rejected);
    }
}
```

Wrapping both `record` and `snapshot` with the lock prevents readers from observing a partially updated state. If you need to store a list of events, `Collections.synchronizedList` only synchronizes **individual operations**; iteration or check-then-act sequences involving multiple operations still require synchronization per the API documentation. Do not turn a lock into a place for I/O or external callbacks.

## 8. Common Races and Lifecycle Bugs

### Reading Results Too Early

`publisher.submit(x)` does not mean `onNext(x)` has completed, because delivery is asynchronous. `Thread.sleep(100)` is not a proof of completion. Use `CountDownLatch`, `CompletableFuture`, or proper lifecycle synchronization. If waiting times out, treat it as an error/timeout that must be handled—do not print results as if they were complete.

### Canceling a Subscription and Waiting Forever

A `cancel()` call may still have a few signals in flight and does not obligate the publisher to emit `onError` or `onComplete`. If the application proactively cancels, complete the lifecycle-managing promise/latch yourself and clean up resources idempotently. Do not assume cancellation is an upstream failure.

### Sharing One Subscriber Across Multiple Subscriptions

Assigning `this.subscription` a second time can cause a callback from the previous subscription to call `request` on the later subscription. The clearest approach: **create one subscriber instance per subscription**, or explicitly design a multi-subscription subscriber with clearly proven state and synchronization.

### Swallowing Errors in `onNext`

`catch(Exception ignored) {}` loses track of errors while `request(1)` continues consuming indefinitely. You should record the failing item, the error type, the retry/skip policy, a failure-count limit, and how to notify the caller. Do not perform unbounded retries inside a callback that holds a delivery thread.

### Throwing an Exception Out of a Callback and Expecting `onError` to Always Run

That is a false assumption about the error channel. With `SubmissionPublisher`, an exception thrown by a subscriber method causes the subscription to be canceled; a handler passed to the constructor can observe errors thrown from `onNext`. Exception handling in a custom publisher may differ, so always read the implementation's contract. To report task failure to the caller, use a separate result channel with an explicit failure state.

### Calling `request(Long.MAX_VALUE)` Everywhere

This effectively removes the subscriber's demand limit and can increase queued work depending on the publisher's buffering mechanism. Choose demand based on processing speed, memory, latency, and queue-full strategy. `request(1)` is a safe pedagogical choice for understanding the lifecycle, not a default throughput optimization.

## 9. Testing Strategy

Verify both **signal ordering** and **observable state**, avoiding tests based on arbitrary sleep durations:

1. **Successful completion:** multiple items, including validly rejected items; verify total and rejected counts are accurate; `onComplete` occurs once; no `onError`.
2. **Upstream error:** publisher terminates with `closeExceptionally`; subscriber records the exact cause and does not treat it as a successful completion.
3. **Backpressure:** subscriber only calls `request(1)`; verify the publisher honors demand and does not deliver more items than requested.
4. **Concurrency:** multiple publishers/subscribers update shared metrics; no updates are lost, and snapshots satisfy invariants.
5. **Cancellation:** trigger `cancel()` while under load; confirm the application terminates its lifecycle on its own without waiting for an unguaranteed terminal signal.
6. **Callback errors:** with `SubmissionPublisher`, verify the subscription is canceled when a callback throws an exception and check the configured error-observation path; do not assert that the publisher must turn that exception into `onError` on the same subscriber.
7. **Timeouts and cleanup:** if the source does not emit a terminal signal, the waiting mechanism must time out/cancel appropriately; application-owned executors and resources must be closed on time.

A worthwhile race test must repeat enough times to uncover issues, though a single passing run does not prove the absence of races. Design shared state using synchronization primitives with clear contracts, then verify invariants rather than relying solely on stress tests.

## 10. Takeaways

- **Per-subscription callback serialization** is a `Flow` guarantee; **thread safety of shared state** is an application design decision.
- **Recoverable data errors**, **stream-terminating upstream errors**, and **exceptions thrown from callbacks** require three distinct policies.
- **`onError` and `onComplete` are terminal signals**; **`cancel()` does not promise to send a terminal signal**.
- Use intentional demand, avoid long-blocking callbacks, and observe completion through reliable synchronization mechanisms.

Official references:
- [Flow — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [Flow.Publisher — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Flow.Subscription — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [SubmissionPublisher — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
