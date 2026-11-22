# `request(n)` and Demand-Driven Consumption in Java Flow

## 1. The Problem to Solve

Suppose a source emits 100,000 events/second, but the processing component can only keep up with 2,000 events/second. If the source keeps pushing data and the receiver has to accept it, the queue can grow continuously, increasing latency, consuming memory, or overloading the system. The **backpressure** mechanism in the Publisher–Subscriber model allows the receiving side to proactively indicate how many more items it is ready to receive.

In Java, the standard `java.util.concurrent.Flow` API (since Java 9) describes this protocol. The core of this lesson is **`Flow.Subscription.request(long n)`**: the Subscriber grants additional sending permission (demand) to the Publisher. The Publisher may only call `onNext` while the subscription still has demand and must not send more items than the amount requested. This is a mechanism for coordinating the number of items between both sides, not a rate-limiting mechanism per unit of time.

## 2. The Four Roles and the Subscription Lifecycle

| Role | Responsibility |
|---|---|
| `Flow.Publisher<T>` | Accepts registrations via `subscribe(subscriber)`, provides items and completion/error signals. |
| `Flow.Subscriber<T>` | Receives `onSubscribe`, `onNext`, `onError`, `onComplete`; decides when to request more. |
| `Flow.Subscription` | Links a Publisher with a Subscriber; provides `request(n)` and `cancel()`. |
| `Flow.Processor<T,R>` | Acts as both a Subscriber upstream and a Publisher downstream; must coordinate demand across both sides. |

A typical signal flow:

```text
Publisher                   Subscription                  Subscriber
    |                            |                             |
    | -- onSubscribe(s) --------------------------------------> |
    |                            | <-------- request(2) ------- |
    | --------------------- onNext(item 1) ------------------> |
    | --------------------- onNext(item 2) ------------------> |
    |         (remaining demand = 0; stop sending onNext)       |
    |                            | <-------- request(1) ------- |
    | --------------------- onNext(item 3) ------------------> |
    | --------------------- onComplete() --------------------> |
```

`onSubscribe` occurs before data or termination signals. A subscription **starts with demand equal to 0**: merely subscribing does not mean permission has been granted to send items. After `onError` or `onComplete`, the signal stream has terminated and there will be no subsequent `onNext`.

## 3. What Does `request(n)` Mean Exactly?

`subscription.request(n)` with `n > 0` **adds** `n` item-receiving permissions to the *unfulfilled* demand of that subscription. Each time the Publisher successfully emits an `onNext`, it consumes one permission. This is neither a command to “send exactly n items right now” nor a reset of the demand window to n.

Sequential example:

| Action | Unfulfilled demand | Meaning |
|---|---:|---|
| `onSubscribe(s)` | 0 | Not yet permitted to emit `onNext`. |
| `s.request(2)` | 2 | At most two items may be sent. |
| Receive one `onNext` | 1 | One permission has been used. |
| `s.request(3)` | 4 | Adds 3 to the remaining amount of 1. |
| Receive four `onNext` | 0 | Must wait for a new request to send more. |

Rules to remember:

- **`request(n > 0)` is cumulative.** Two consecutive `request(3)` calls can allow up to six items, not three. The Publisher may send fewer if data is not yet available, if it has completed, or if it has been cancelled.
- **`request(0)` and `request(n < 0)` violate the protocol.** According to the `Flow.Subscription` contract, the Subscriber will receive `onError` with `IllegalArgumentException`. To pause granting additional demand, simply *do not call* `request`; do not use `request(0)` to pause.
- **`request(Long.MAX_VALUE)` is generally treated as an unbounded request.** Use it only when the receiver can genuinely handle the data stream or has its own control mechanism.
- **Demand is per subscription.** Two Subscribers of the same Publisher can have different numbers of receiving permissions; Subscriber A's demand must not be used to emit data to B.
- **Terminal signals are not items.** `onComplete`/`onError` do not consume demand; a source can terminate even if no more items are requested. They are only emitted according to the Publisher's lifecycle rules.

You can think of the safety invariant on an active subscription as **the number of `onNext` calls sent does not exceed the total number of items requested** (with saturation handling rules when demand is very large). In a real-world implementation, the counter must prevent integer overflow and be safe against concurrent access; do not naively add `long` values in a way that could overflow into a negative number.

## 4. Example 1 — Observing Demand Open and Close the Data Sending Gate

The following example uses a minimal Publisher, running **synchronously on a single thread**, to observe exactly when items are emitted. It is for learning purposes: do not use this implementation as a multi-threaded production Publisher, as it does not handle concurrency/reentrancy when `request` is called nestedly.

Save as `ManualDemandDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.Flow;

public class ManualDemandDemo {
    static final class FixedPublisher implements Flow.Publisher<Integer> {
        @Override
        public void subscribe(Flow.Subscriber<? super Integer> subscriber) {
            Objects.requireNonNull(subscriber);

            subscriber.onSubscribe(new Flow.Subscription() {
                private int next = 1;
                private boolean stopped;

                @Override
                public void request(long n) {
                    if (stopped) return;

                    if (n <= 0) {
                        stopped = true;
                        subscriber.onError(
                            new IllegalArgumentException("n must be > 0"));
                        return;
                    }

                    long delivered = 0;
                    while (delivered < n && next <= 3 && !stopped) {
                        subscriber.onNext(next++);
                        delivered++;
                    }

                    if (next > 3 && !stopped) {
                        stopped = true;
                        subscriber.onComplete();
                    }
                }

                @Override
                public void cancel() {
                    stopped = true;
                }
            });
        }
    }

    public static void main(String[] args) {
        Flow.Subscription[] subscription = new Flow.Subscription[1];

        new FixedPublisher().subscribe(new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription s) {
                subscription[0] = s;
                System.out.println("Đăng ký; demand = 0");
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("onNext " + item);
            }

            @Override
            public void onError(Throwable error) {
                System.out.println("onError " + error.getClass().getSimpleName());
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
            }
        });

        System.out.println("request(2)");
        subscription[0].request(2);
        System.out.println("request(1)");
        subscription[0].request(1);
    }
}
```

Run with Java 17 or later:

```bash
javac ManualDemandDemo.java
java ManualDemandDemo
```

Expected output in this synchronous example:

```text
Đăng ký; demand = 0
request(2)
onNext 1
onNext 2
request(1)
onNext 3
onComplete
```

After the `request(2)` call, the source only sends 1 and 2 and then stops, even though value 3 is already available. Only the subsequent `request(1)` call opens permission to send value 3. `onComplete` appears when the source has emitted all data. If the final `request(1)` is replaced with `request(0)`, the example emits `onError IllegalArgumentException`, not `onComplete`.

**Limitation of the example:** because `request` executes the loop directly on the calling thread, do not let `onNext` in this example call `request` again or call it from multiple threads. A production Publisher needs to coordinate a drain loop, serialize callbacks, maintain a thread-safe demand counter, and handle cancellation/termination exactly once.

## 5. Example 2 — Consumer Requests the Next Item Only After Finishing Processing

`SubmissionPublisher<T>` is the standard built-in implementation in `java.util.concurrent`. It delivers signals asynchronously to Subscribers and manages a per-Subscriber buffer. A Subscriber can start with `request(1)`, and then call `request(1)` again only after each `onNext` finishes processing.

Save as `OneByOneDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class OneByOneDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // Grant one initial receiving permission
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("Nhận " + item);
                    // Only grant another permission after finishing processing the current item
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("Lỗi: " + error);
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit(1);
            publisher.submit(2);
            publisher.submit(3);
        } // close() signals that no more new items will arrive

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber chưa kết thúc");
        }
    }
}
```

Run:

```bash
javac OneByOneDemo.java
java OneByOneDemo
```

When completing normally, the stdout lines in order are:

```text
Nhận 1
Nhận 2
Nhận 3
onComplete
```

An important distinction: `SubmissionPublisher.submit(item)` **can place items into the buffer even when the Subscriber does not yet have demand to receive them**. It only guarantees that `onNext` callbacks respect demand; it does not mean the Producer's `submit` only runs after each `request(1)`. When the buffer is full, `submit` may block waiting for resources; `offer` has a different handling policy (it may drop items). Therefore, `request(1)` limits the number of items being delivered to the Subscriber, **it does not automatically guarantee that the entire upstream will not produce ahead, have no buffer, or consume no memory**.

In asynchronous code, `CountDownLatch` helps `main` wait for the completion signal. Do not use `Thread.sleep(...)` to “guess” that callbacks have finished running.

## 6. Choosing a Demand-Granting Strategy

**Requesting one item at a time:**

```java
@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(1);
}

@Override
public void onNext(Event event) {
    process(event);        // synchronous processing; may take time
    subscription.request(1); // only request the next one after successful processing
}
```

The snippet above is **illustrative code inside a Subscriber**, not a complete Java class. It is suitable when each item is expensive and tight control is desired, though requesting one by one can reduce throughput. If `process` fails, there must be a clear error-reporting/cancellation or error-handling policy; do not silently drop items and do not unconditionally grant more demand.

**Requesting in batches (window/batch):**

```java
private static final int BATCH_SIZE = 32;
private Flow.Subscription subscription;
private int processedInBatch;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(BATCH_SIZE);
}

@Override
public void onNext(Event event) {
    process(event);
    if (++processedInBatch == BATCH_SIZE) {
        processedInBatch = 0;
        subscription.request(BATCH_SIZE);
    }
}
```

This is also a snippet inside a Subscriber, with `Event` and `process` defined by the application. It allows up to 32 open receiving permissions, then replenishes 32 permissions after each batch. In practice, you can replenish earlier (for example, when about 75% of the window has been processed) to avoid idle wait time between batches. Choose `BATCH_SIZE` based on memory, per-item cost, latency, and measured throughput.

**Unbounded request:**

```java
subscription.request(Long.MAX_VALUE);
```

This approach is simple but provides no Subscriber-side demand-limiting mechanism. Avoid using it by default for infinite sources or heavy workloads.

A Subscriber can request more in `onSubscribe`, `onNext`, or at another time when resources are ready. With async processing inside `onNext`, only call `request` again **after the async operation actually completes** if the goal is to limit the number of in-flight tasks; calling it immediately after enqueuing the task will only limit immediate callbacks, not the number of enqueued tasks.

## 7. Backpressure Does Not Mean Everything Is Safe

It is necessary to distinguish three quantities:

| Quantity | What does it measure? | Controlled by whom? |
|---|---|---|
| **Demand** | Number of unused `onNext` emission permissions of a subscription. | Granted by Subscriber via `request(n)`; enforced by Publisher. |
| **Buffer/queue size** | Number of items created/received that are waiting for distribution or processing. | Publisher/Processor design, buffer size, overflow policy. |
| **Processing concurrency/rate** | How many tasks are currently running, and how fast they are processed. | Executor, workers, concurrency limits, application algorithm. |

When chaining multiple stages `Publisher -> Processor -> Subscriber`, each link has its own subscription and demand. A Processor must both respect downstream demand and decide when to request more from upstream, and may need a bounded buffer. If a Processor always calls `request(Long.MAX_VALUE)` upstream while downstream requests one item at a time, the internal buffer can still grow rapidly.

With multiple Subscribers, `SubmissionPublisher` manages separate buffers/demand for each receiver; a slow Subscriber can affect submit/offer policies and overall resources. Do not treat “having the Flow API” as automatic proof that overload is impossible.

## 8. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Forgetting `request` in `onSubscribe` and not requesting anywhere else. | No `onNext` received even though the source has items. | Grant positive demand when actually ready. |
| Calling `request(0)` to pause. | Protocol violation, leading to `onError(IllegalArgumentException)`. | Stop requesting more; process the permissions already granted earlier. |
| Interpreting `request(5)` as “must receive exactly 5 items immediately”. | Incorrect waiting logic, easily hangs when the source only has 3 items. | Understand it as allowing **at most** 5 more items; watch for terminal signals. |
| Calling `request(1)` immediately after enqueuing async processing. | Pending work can still accumulate. | Request more after actual completion of the work if limiting in-flight tasks. |
| Using `request(Long.MAX_VALUE)` by default and assuming bounded backpressure is in place. | Loses the ability to limit items via demand. | Use a bounded window when control is needed. |
| Writing a custom Publisher with unlocked/non-atomic `long demand += n`. | Race condition or overflow, emitting beyond demand. | Use a trusted implementation; if writing your own, use atomic/saturating arithmetic and a serialized drain mechanism. |
| Assuming `cancel()` stops all callbacks immediately. | In-flight items may still arrive. | Treat cancel as best-effort; safely handle callbacks arriving close to cancellation time. |

A subtle detail: `onNext` for the same Subscriber must be emitted sequentially according to the `Flow` contract, but `request` and `cancel` can be called from a different thread than the emitting thread. Publisher authors must ensure memory safety, synchronization, and never sending beyond demand; Subscriber authors should not assume callbacks always run on the `main` thread.

## 9. Check Your Understanding

1. Initially demand is 0; call `request(4)`, receive 2 items, then call `request(3)`. **How many permissions remain?** Answer: `4 - 2 + 3 = 5`.
2. Called `request(10)`, but the source only had 3 items left and then completed. **Is this an error?** No. Demand is an upper bound, not a promise that enough data will be available; `onComplete` is valid.
3. Is `request(0)` a way to pause? **No.** It is an invalid request that causes `onError`.
4. Why can a Subscriber using `request(1)` still experience memory pressure? Because the Producer/Processor may produce ahead, buffer data, or create async tasks faster than the completion rate; demand is only one part of the design.

**Takeaway:** `request(n)` is the signal “I allow receiving at most n more items”, and calls accumulate onto the remaining demand. A stable system needs to combine demand rules with buffer bounds, overflow policies, in-flight task limits, and proper terminal/cancel handling.

## Java SE 17 References

- [`Flow` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [`Flow.Subscription` — request/cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`SubmissionPublisher` — buffer, submit, offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
