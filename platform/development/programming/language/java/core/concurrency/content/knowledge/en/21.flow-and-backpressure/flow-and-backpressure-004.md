# onSubscribe(), onNext(), onError(), onComplete() in Java Flow.Subscriber

## 1. Context: Flow and Backpressure in Java SE

Since Java 9, `java.util.concurrent.Flow` has provided asynchronous data-exchange interfaces following the Reactive Streams model. When a source produces data faster than the receiver can process it, the **backpressure** mechanism gives the receiver control to regulate the number of items delivered.

- `Flow.Publisher<T>`: a source that provides items of type `T`, allowing one or more subscribers to register.
- `Flow.Subscriber<T>`: the receiver of items and lifecycle signals.
- `Flow.Subscription`: the relationship between a Publisher and a specific Subscriber; `request(long n)` asks for more items, and `cancel()` requests to stop receiving.
- `Flow.Processor<T, R>`: both receives data of type `T` and publishes type `R`, though it is not needed to understand a basic Subscriber.

A `Flow.Subscriber<T>` must fully implement four callbacks:

```java
void onSubscribe(Flow.Subscription subscription);
void onNext(T item);
void onError(Throwable throwable);
void onComplete();
```

These callbacks **are invoked by the Publisher/Subscription**. A normal Subscriber does not call them itself to "push" data; instead, it actively calls `request` or `cancel` on the Subscription it is given. Everything below belongs to **general Java concurrency**, without using any Spring APIs.

| Callback | Meaning | Common actions |
| --- | --- | --- |
| `onSubscribe(subscription)` | Data-receiving relationship established | Store the subscription, request initial demand |
| `onNext(item)` | A valid item is available to deliver | Process the item, decide when to request more |
| `onError(error)` | Upstream encountered an unrecoverable error | Log/record the error, release resources, finish |
| `onComplete()` | Upstream completed normally | Clean up resources, signal completion |

## 2. Call Ordering and Subscription States

On **a single subscription**, the callbacks follow this signal flow:

```text
subscribe(subscriber)
       |
       v
onSubscribe(subscription)
       |
       +-- request(n > 0) --> onNext(item) --> onNext(item) --> ...
       |                         ^                   |
       |                         +---- request more -+
       |
       +-- cancel() -------> stop receiving (best-effort)

Normal completion branch: ... -> onComplete()
Error completion branch:  ... -> onError(throwable)
```

Key rules:

1. **`onSubscribe` is called before** any other callbacks for the corresponding subscription. Each subscription has its own demand and lifecycle.
2. **No `onNext` without demand** from `request(n > 0)` for a spec-compliant Publisher. Each `onNext` consumes one unit of demand.
3. **Callback invocations on the same subscription are strictly ordered (happens-before)**. They do not overlap as concurrent callback invocations for the same subscription; however, there is no guarantee that all run on a single fixed thread. Different subscriptions can still run in parallel.
4. **`onError` and `onComplete` are mutually exclusive**: each subscription receives at most one terminal signal; after a terminal signal, no further callbacks occur. A subscription that has not finished or has been cancelled may not receive a terminal signal.
5. **`cancel()` is a best-effort stop request**. Some in-flight messages may still arrive after the cancel call, and cancellation is not required to produce `onComplete` or `onError`.

Suggested state table for receiver-side logic:

| State | Signal / action | Result |
| --- | --- | --- |
| Unsubscribed | `Publisher.subscribe(...)` | Waiting for `onSubscribe` |
| Active | `onSubscribe` → `request(n)` | Authorized to receive up to n items |
| Active | `onNext` | Process item, demand decreases by 1 |
| Active | `request(n > 0)` | Unfulfilled demand increases by n |
| Active | `onError` | Terminates with error |
| Active | `onComplete` | Terminates successfully |
| Active | `cancel()` | Requests stop, no mandatory terminal signal awaited |

A custom Publisher is responsible for maintaining these invariants. If a Publisher violates the contract, the Subscriber cannot assume the signals it receives are still valid.

## 3. onSubscribe(Flow.Subscription): Taking Control

`onSubscribe` is called first, handing the Subscriber a `Flow.Subscription`. The Subscriber stores it so it can request data or cancel. The example below is part of a class that `implements Flow.Subscriber<String>`:

```java
private Flow.Subscription subscription;

@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
```

`request(1)` allows the Publisher to invoke **at most one additional `onNext`**. It does not require the Publisher to immediately produce an item, nor does it guarantee that data is always available. If the Subscriber does not call `request`, a spec-compliant Publisher will not deliver items via `onNext`, even if the source already has data buffered.

### How does request(n) accumulate?

`Flow.Subscription.request(long n)` adds `n` to the unfulfilled demand. If there is currently a demand of 2 and you call `request(3)`, the publisher can deliver up to 5 more items before new demand is needed. Large total demand may be capped at saturation to avoid arithmetic overflow.

- `n > 0`: valid request.
- `n == 0` or `n < 0`: **not a way to pause**. The contract requires signaling `onError` with an `IllegalArgumentException`.
- `n == Long.MAX_VALUE`: is generally treated as effectively unbounded demand; use it only when the consumer accepts this form of authorization.

Do not overwrite a field holding an active subscription with a new subscription if the implementation can serve multiple registrations. In a simple design, use a separate Subscriber per Subscription. If an unexpected subscription is received, apply an appropriate reject/cancel policy; do not merge the demand state of two streams into a single variable.

## 4. onNext(T): Processing Items and Replenishing Demand

`onNext(T item)` is called for each item authorized via `request`. For synchronous processing, the clearest pattern is **finish processing, then request one more item**:

```java
@Override
public void onNext(String item) {
    System.out.println("Đã nhận: " + item);
    subscription.request(1);
}
```

The snippet above assumes the `subscription` field was already stored in `onSubscribe`; this is a single method inside a Subscriber class, not a complete program.

Example progression:

| Event | Remaining demand |
| --- | ---: |
| `onSubscribe` calls `request(1)` | 1 |
| Receive `onNext("A")` | 0 |
| Finish processing A, call `request(1)` | 1 |
| Receive `onNext("B")` | 0 |
| Finish processing B, call `request(1)` | 1 |
| Source runs out of data, sends `onComplete` | Finished |

Calling `request(1)` after every item helps control the receiving pace, but adds overhead if each item is very small. You can request in batches such as `request(16)` or `request(32)`, track the number of consumed items, and replenish when an appropriate threshold is reached.

**Be careful with asynchronous work:** if `onNext` only enqueues an item or starts a `CompletableFuture` and immediately requests a new item, demand reflects the rate of **enqueueing work**, not the rate of completing work. The queue can grow without bound if downstream is slow. You must bound the number of in-flight tasks, replenish demand when processing capacity becomes available, and synchronize state with the thread completing the work.

Do not block callbacks for too long with I/O or mutual lock contention. Keeping `onNext` busy can stall delivery of subsequent items and terminal signals.

## 5. onError(Throwable): Error Termination from Upstream

The Publisher or Subscription calls `onError` when it cannot continue a subscription due to an error. The `Throwable` carries the cause, after which the subscription is terminated and must not receive any more `onNext` or `onComplete` signals.

```java
@Override
public void onError(Throwable throwable) {
    System.err.println("Nguồn dữ liệu thất bại: " + throwable);
    finished.countDown();
}
```

Here `finished` is assumed to be a `CountDownLatch` in the Subscriber class's scope. Signaling the latch lets the coordinating thread know the subscription has reached a terminal state. In a real application, you might complete a future exceptionally, log with context, and reclaim resources.

Distinguish between:

- **Errors signaled by the Publisher/Subscription**: the Subscriber receives `onError`.
- **Exceptions thrown by the Subscriber's own code in `onNext`**: the Javadoc does not guarantee that such an exception is routed back to the Subscriber's **own** `onError`. For example, `SubmissionPublisher` cancels the subscription if a callback throws an error; its optional error handler may be invoked.
- **Recoverable per-item business errors**: depending on the design, these can be handled or represented as data without necessarily terminating the entire stream.

Do not call `onComplete` from `onError`, and do not continue calling `request` after a terminal signal. Avoid letting `onError` itself throw another exception, because behavior when a terminal callback throws is undefined.

## 6. onComplete(): Normal Termination

`onComplete()` signals that the subscription has completed normally and no further callbacks will occur. The method takes no parameters:

```java
@Override
public void onComplete() {
    System.out.println("Đã nhận hết dữ liệu");
    finished.countDown();
}
```

`onComplete` does not mean "all application work is finished": if `onNext` previously offloaded work to another executor, those tasks may still be running. The application must track those secondary tasks itself.

With `SubmissionPublisher`, `close()` emits the completion signal asynchronously. **Returning from `close()` does not mean `onComplete` has finished running.** Therefore, in the example below, `CountDownLatch` is used to wait for the actual terminal signal.

## 7. Standalone Java 17+ Example: Observing the Full Lifecycle

This example uses only the JDK, consisting of `SubmissionPublisher<String>`, `Flow.Subscriber<String>`, and `CountDownLatch`. `onError` is implemented, though the normal path does not trigger it.

Create the file `FlowLifecycleDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<String> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    System.out.println("onSubscribe");
                    subscription.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("onNext: " + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    System.out.println("onError: " + throwable);
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();
            finished.await();
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac FlowLifecycleDemo.java
java FlowLifecycleDemo
```

Exact output of the example (single Subscriber):

```text
onSubscribe
onNext: A
onNext: B
onComplete
```

This code was tested on JDK 24 (the code uses APIs that run on Java 17+). Key points to note:

1. `subscribe` establishes the subscription; the `onSubscribe` callback receives it and requests 1 item.
2. The two `submit` calls feed "A" then "B" into the publisher. Delivery to the Subscriber is asynchronous; do not assume `submit` waits for `onNext` to finish.
3. Initial demand allows receiving A; after processing A, the Subscriber requests 1 more, so it receives B.
4. `close` signals that no more items will be published; `onComplete` appears after the items on the same subscription.
5. `finished.await()` makes the `main` thread wait until the terminal callback has run.
6. `SubmissionPublisher` may use a different thread from the one calling `submit`; **callback ordering for a single subscription is still preserved**.

### Trying the onError branch

In the program above, replace **these exact three lines**:

```java
publisher.submit("A");
publisher.submit("B");
publisher.close();
```

with:

```java
publisher.closeExceptionally(new IllegalStateException("upstream failed"));
```

Expected output of the modified run:

```text
onSubscribe
onError: java.lang.IllegalStateException: upstream failed
```

This time the Publisher actively closes with an error, so there is no `onNext` and `onComplete` is not called. This demonstrates an upstream error reported via `onError`, not proof that an exception thrown inside `onNext` produces the same behavior.

## 8. Batch Demand, Cancellation, and Backpressure Limits

**Item-by-item demand:** use `request(1)` in `onSubscribe` and replenish one item at a time. This is easy to reason about and suits slow item processing or tight control over intake capacity.

**Batch demand:** you can start with `request(32)`, then replenish with `request(16)` every time 16 items are processed. Unfulfilled demand then oscillates within a range instead of calling `request` for every single item. The conceptual example below is *pseudocode*, not a complete Java program:

```text
onSubscribe:
    subscription.request(32)
    remaining = 32

onNext(item):
    process(item)
    remaining--
    if remaining == 16:
        subscription.request(16)
        remaining += 16

onError / onComplete:
    cleanup
    stop requesting
```

When using batching, define whether "processing finished" means synchronous processing or actual completion of asynchronous work, as that is the appropriate moment to replenish receiving capacity.

**Mid-stream cancellation:** call `subscription.cancel()` when data is no longer needed, for example when a user cancels a task. `cancel` is best-effort: in-flight signals may still be delivered and the subscription is not required to receive a terminal signal. Therefore, cancellation logic needs its own resource-reclamation path.

**Demand is not buffer size.** `request(n)` only authorizes delivering up to `n` items via `onNext`; it does not force every Publisher to cap its internal state at `n` items. `SubmissionPublisher` uses a separate buffer per subscriber. The `submit` method can block waiting for capacity when the buffer is full, whereas `offer` provides drop/rejection policies. Real-world system design must coordinate demand, buffers, executors, upstream rate, and error-handling policies.

## 9. Common Mistakes

| Error or symptom | Cause | How to fix |
| --- | --- | --- |
| Subscribed but no items received | `request` was never called | Request positive demand in `onSubscribe` |
| Received one item then "stalled" | Only called `request(1)` once | Request again once ready to process more |
| Received `IllegalArgumentException` via `onError` | Called `request(0)` or a negative number | Use only positive `n`; do not use `request(0)` to pause |
| Unbounded queue growth | Requested too much or replenished before async work finished | Limit in-flight tasks and replenish based on actual capacity |
| Program exits before seeing final callback | Publisher emits signals asynchronously | Wait for the terminal signal with a latch/future when appropriate |
| Waiting for `onComplete` after `cancel` | Cancellation does not guarantee a terminal signal | Complete the cancellation path with a dedicated mechanism |
| Assuming callbacks always run on one thread | Publisher uses an executor | Rely only on per-subscription ordering; synchronize shared state with other threads |
| Throwing an exception from `onNext` and expecting `onError` | No guarantee of error forwarding that way | Handle downstream errors and cancellation explicitly |
| Calling `request` after `onComplete` | Not tracking terminal state | Mark as finished and release resources |

## 10. Check Your Understanding

**Q1. Why does `onSubscribe` usually call `request` right away?** Because without demand, a Flow-compliant Publisher will not call `onNext`; this is where the Subscriber takes control of the receiving pace.

**Q2. Does `request(5)` guarantee receiving five items?** No; it only permits **at most five** additional `onNext` calls. The Publisher may have no more data or may terminate earlier.

**Q3. Can `onComplete` be called after `onError`?** No, not if the contract is respected. A subscription has at most one terminal signal.

**Q4. Does `onComplete` wait for all `CompletableFuture` instances created in `onNext`?** No; the application must manage its own asynchronous work.

**Q5. Must an infinite stream ever call `onComplete`?** No. While still active, it may have no terminal signal; the application can use `cancel`, timeouts, or another stopping mechanism.

**Q6. How does this API differ from Java `Stream`?** `Flow` describes asynchronous communication and demand between a source and a receiver; `java.util.stream.Stream` primarily provides pipeline operations over a data set and does not use these four callbacks.

## 11. Key Takeaways and References

- `onSubscribe`: receive the Subscription and request positive demand.
- `onNext`: process one item; replenish demand only when additional processing capacity is available.
- `onError`: terminal signal due to error; no further callbacks afterward.
- `onComplete`: terminal signal for normal completion; no further callbacks afterward.
- `request` regulates how much data can be delivered; `cancel` requests stopping on a best-effort basis.
- Callback ordering is guaranteed **per subscription**, not necessarily on the same thread; do not confuse demand with buffer size, or callback completion with async work completion.

Further reading in the official Java SE Javadoc:

- [`Flow`: model and backpressure examples](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [`Flow.Subscriber`: four-callback contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [`Flow.Subscription`: `request` and `cancel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`SubmissionPublisher`: asynchronous publishing and terminal signals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)