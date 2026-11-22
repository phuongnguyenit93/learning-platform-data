# Cancelling Subscriptions and Releasing Resources in Java Flow

## 1. Why is cancelling a subscription part of backpressure?

In Java, `java.util.concurrent.Flow` defines a Publisher–Subscriber model for asynchronous data exchange with flow control (*backpressure*). A `Flow.Subscriber<T>` receives a `Flow.Subscription` object in `onSubscribe`, then calls `request(n)` to request up to `n` more elements. When it no longer needs to consume data, the subscriber can call `cancel()` to unsubscribe.

Cancelling a subscription addresses **a subscriber's right to continue receiving data**. Releasing resources addresses **the lifecycle of objects and work supporting the data stream**: running tasks, buffers, I/O streams, sockets, timers, executors, open files, connections, and objects holding references. The two are related, but one does not automatically replace the other.

For example, once a progress-monitoring screen is closed, the subscriber no longer needs to receive new notifications. Calling `subscription.cancel()` is necessary; if the program also has a periodic file-reading task and its own executor, the component that owns them must still stop and close them.

**Learning Objectives**

- Know when and where to call `cancel()`, including cancellation due to a user leaving a screen, timeouts, reaching the required number of records, or system shutdown.
- Understand the *best-effort* nature of `cancel()`, and the difference between cancellation and the terminal signals `onComplete`/`onError`.
- Identify who owns each resource so it is closed in the right place, at the right time, and only once.
- Write a Java 17+ subscriber with controlled demand, proactive cancellation, and no hanging while waiting for completion events.

## 2. Roles and Lifecycle in `Flow`

| Component | Responsibilities related to cancellation and resources |
| --- | --- |
| `Flow.Publisher<T>` | Emits data according to demand; manages the data source, queues, or tasks created by the publisher itself; must react appropriately when a subscriber cancels. |
| `Flow.Subscriber<T>` | Receives `onSubscribe`, holds the `Subscription`, calls `request`/`cancel`, and handles `onNext`, `onError`, `onComplete`. |
| `Flow.Subscription` | Links **one** subscriber to a publisher; manages demand and cancels that link. |
| `Flow.Processor<T,R>` | Acts as both an upstream subscriber and a downstream publisher; must design how cancellation signals propagate and how resources are cleaned up on both sides. |

A typical lifecycle:

```text
subscribe(subscriber)
    |
    v
onSubscribe(subscription)
    |
    +-- request(n > 0) --> onNext(item) ... --> request(more)
    |                                           |
    |                                           +--> onComplete()
    |                                           +--> onError(error)
    |
    +-- cancel() ------> cancel registration; no terminal signal required
```

Points to distinguish:

1. `request(n)` increases the unfulfilled demand; `n > 0`. Under the Flow contract, `request(n <= 0)` results in `onError(IllegalArgumentException)`.
2. `cancel()` asks the publisher to **eventually** stop sending messages to that subscriber. It is a *best-effort* action: under thread contention, additional messages may still arrive after the call.
3. After `cancel()`, **you must not wait for `onComplete()` or `onError()` as a guarantee**. Cancellation is not a normal terminal signal.
4. `onComplete()` indicates the data source finished normally; `onError(Throwable)` indicates termination due to an error. Both end the signal stream for the subscription; they do not imply that all auxiliary resources have been closed.
5. One publisher can serve multiple subscribers. Cancelling **one** subscription does not implicitly close the publisher or cancel the subscriptions of other consumers.

In real-world applications, it is good practice to model at least the states: **active → cancelling/cancelled** or **terminated**. An atomic state flag makes repeated cleanup and concurrent races safer.

## 3. When to cancel and what must not be assumed?

Cancel when there is no longer a reason to receive more elements: the user closes the monitoring session, enough samples have been collected, a deadline is reached, a processing error makes continuing to receive data meaningless, or the component owning the subscriber is about to close.

Do not use `cancel()` as an absolute, instantaneous interrupt mechanism. The publisher may have already emitted an item; the `onNext` callback may already be executing or queued. With concurrent threads, the observed order between the cancellation operation and a running callback depends on the implementation and the application's synchronization. Therefore:

- Mark the cancelled state before or when calling `cancel()`; late-arriving callbacks should check the state before creating new side effects.
- Do not call `request(1)` again once you have decided to cancel.
- If a callback is still using a file/socket/resource, **do not close the resource mid-flight** without coordination. Use a lock, an in-flight task counter, or a protocol that waits for processing to finish before closing.
- If closing must have a bounded time, use a timeout when waiting for tasks to exit and define a policy for handling unfinished work.
- Distinguish between "cancellation requested" and "all work has actually stopped". If you need to wait for the latter condition, the application must have its own coordination signal such as a `CountDownLatch`, `Future`, or completion stage.

There is no general `Flow.Subscription` API to "await cancelled". Nor does `cancel()` return a `boolean` indicating that resources have finished being released.

## 4. Runnable Example: Subscriber Self-Cancels After Three Elements

This example uses Java's built-in `SubmissionPublisher<Integer>` instead of writing a full custom publisher. The subscriber requests one element at a time; after the third element, it cancels. The `CountDownLatch` is a signal **proactively emitted by the application upon cancellation**, rather than relying on Flow to send `onComplete`.

Create the file `CancelAfterThree.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class CancelAfterThree {
    static final class FirstThreeSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch stopped;
        private Flow.Subscription subscription;
        private int received;
        private boolean cancelled;

        FirstThreeSubscriber(CountDownLatch stopped) {
            this.stopped = stopped;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer value) {
            if (cancelled) {
                return; // Ignore late signals after cancellation.
            }

            System.out.println("Nhận: " + value);
            received++;

            if (received == 3) {
                cancelled = true;
                subscription.cancel();
                System.out.println("Đã hủy subscription");
                stopped.countDown();
            } else {
                subscription.request(1);
            }
        }

        @Override
        public void onError(Throwable error) {
            System.err.println("Lỗi: " + error);
            stopped.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("Publisher hoàn tất");
            stopped.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch stopped = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new FirstThreeSubscriber(stopped));

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }

            if (!stopped.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Chờ subscriber quá lâu");
            }
        } // Close the publisher where the publisher is owned.
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CancelAfterThree.java
java CancelAfterThree
```

When the program runs normally, the output is:

```text
Nhận: 1
Nhận: 2
Nhận: 3
Đã hủy subscription
```

**Key points explained:**

1. `onSubscribe` receives the subscription and requests `request(1)`, allowing the publisher to send one element. After each retained element, the subscriber requests exactly one more; this is backpressure at a basic level.
2. When `received == 3`, the subscriber sets `cancelled = true` and calls `subscription.cancel()`; it does not request more elements. Items `4` and `5` that were already submitted to the publisher will not continue to be delivered to the cancelled subscription.
3. `SubmissionPublisher` delivers callbacks asynchronously and preserves element order in this example. `CountDownLatch` lets `main` wait until the subscriber has executed the cancellation request, instead of exiting right after calling `submit`.
4. Because callbacks for **a single subscription** are delivered sequentially, the `cancelled` flag in this small example is only accessed from that callback chain. In an application that cancels from another thread, `AtomicBoolean` or equivalent synchronization is required.
5. `try-with-resources` closes `SubmissionPublisher` when exiting the block. That is the **publisher** cleanup step, distinct from the subscriber unsubscribing. By default, the publisher uses `ForkJoinPool.commonPool()`; you must not call shutdown on the common pool just because you closed the publisher.
6. After cancelling, the example does **not** wait for `onComplete`. If you omit `stopped.countDown()` in the cancellation branch, the program may wait forever or time out even though `cancel()` worked properly.

The example above assumes no system errors and that the executor is still accepting tasks. `await(5, ...)` guards the wait; the 5-second duration is a demonstration timeout, not a performance guarantee of `Flow`.

## 5. Distinguishing `cancel()`, closing the publisher, and closing application resources

| Operation | Scope and meaning | Does it automatically clean up all resources? |
| --- | --- | --- |
| `subscription.cancel()` | Requests stopping data delivery for **that specific subscription**. | No. It does not force closing the publisher, executor, connections, or resources owned by the caller. |
| `publisher.close()` on `SubmissionPublisher` | Stops accepting new items; asynchronously sends `onComplete` to active subscribers. | Only according to that publisher's contract. Does not guarantee callbacks have finished when `close()` returns. |
| `publisher.closeExceptionally(error)` | Closes the publisher and emits `onError(error)` to active subscribers. | Does not replace closing resources outside the publisher. |
| `executor.shutdown()` or `shutdownNow()` | Begins stopping an application-owned executor; `shutdownNow` only attempts to interrupt tasks. | Must coordinate with tasks and time bounds; does not guarantee tasks stop immediately. |
| `resource.close()` | Releases an `AutoCloseable` resource such as a stream/connection according to the resource's contract. | Cleans up only that resource itself; does not decide subscription state. |

Example of a subscriber with a reader and a publisher using its own executor:

```text
Where was the resource created?       Who is responsible for closing
------------------------------------  --------------------------------------------------
Subscription received in onSubscribe  Subscriber calls cancel when no longer needed
SubmissionPublisher created in main   main/service owner calls close
ExecutorService created in main       main/service owner shuts down and awaits
InputStream opened in source adapter  source adapter closes after callbacks/tasks are safe
Timer created by component itself     component cancels timer and shuts down scheduler
```

**Ownership rule:** only the component that created a resource or explicitly received ownership is responsible for deciding when to close it. If an executor is shared across multiple publishers/subscribers, cancelling one consumer must never shut down the shared executor.

If an intermediate `Flow.Processor` is cancelled downstream, whether to cancel upstream immediately depends on the pipeline design: there may be other downstream subscribers or shared processing work. Do not automatically assume that cancelling at one end cleans up the entire chain.

## 6. Idempotent Cleanup, Even on Concurrent Errors or Cancellation

In systems with callbacks, timeouts, and user-initiated stop requests, multiple execution paths may try to clean up resources at the same time: `cancel()`, `onError()`, `onComplete()`, or the service's `close()`. The pattern to apply is **idempotent cleanup**: even if called multiple times, a resource undergoes its closing procedure only once.

The following snippet only **illustrates a cleanup method inside a component** that has already declared the fields `subscription`, `task`, `ownedExecutor`, and `closed`; it is not a standalone program:

```java
private final java.util.concurrent.atomic.AtomicBoolean closed =
        new java.util.concurrent.atomic.AtomicBoolean();

private volatile Flow.Subscription subscription;
private java.util.concurrent.Future<?> task;
private java.util.concurrent.ExecutorService ownedExecutor;

@Override
public void close() {
    if (!closed.compareAndSet(false, true)) {
        return; // Another component has already started cleanup.
    }

    Flow.Subscription current = subscription;
    if (current != null) {
        current.cancel();
    }

    if (task != null) {
        task.cancel(true); // Only requests interruption; the task must cooperate.
    }

    if (ownedExecutor != null) {
        ownedExecutor.shutdown(); // Only when the component owns the executor.
    }
}
```

In a real component, you must also add a way to wait for tasks currently using the resource, a timeout policy, and error handling when calling `close()`. `AtomicBoolean` prevents duplicate cleanup, but it **does not by itself solve** all race conditions: for example, `close()` might arrive before `onSubscribe`, while `subscription` is still `null`. In that case, `onSubscribe` must check the closed state, immediately cancel the newly received subscription, and never issue any demand. If resource initialization happens after cleanup has started, initialization must be synchronized with closing.

In particular, do not rely on `cancel()` alone to guarantee that a thread executing `onNext` has stopped before a socket or file is closed. A safe ordering is typically: mark as no longer accepting new work → cancel subscription → prevent new tasks → wait (with a bound) for tasks currently using the resource to finish → close the resource → record the result.

## 7. Designing Termination Paths for Every Scenario

Depending on the application, each termination path requires a different way to complete:

| Scenario | Subscription handling | Completion/cleanup handling |
| --- | --- | --- |
| Source finishes emitting data | Subscriber receives `onComplete`; no further cancellation needed to stop data. | Clean up subscriber-owned resources and notify the service of completion if needed. |
| Publisher emits an error | Subscriber receives `onError`; that stream ends. | Log the error, clean up resources; retry decisions belong to the orchestration layer. |
| Consumer stops early | Subscriber proactively calls `cancel()`. | Emit the **application's** completion signal; do not wait for `onComplete` from Flow. |
| Deadline / user closes screen | Lifecycle-managing component requests cancellation and stops related tasks. | Unify cleanup paths using atomic state and manage timeouts. |
| Publisher/service shutdown | Owner closes the publisher and the resources it allocated. | If waiting for running callbacks to finish is required, use a separate coordination tool. |
| `onNext` fails | Error policy depends on the publisher and how callbacks are handled. | Avoid throwing unchecked errors blindly; log the cause, request cancellation, and clean up appropriate resources. |

With `SubmissionPublisher`, if an `onNext` callback throws an exception, that subscriber's subscription is cancelled; if you want to log the error and clean up specific resources, you must build the application's own handling path. You cannot assume the subscriber's `onError` will be invoked after every exception thrown inside `onNext` itself.

If you need to detect timeouts, deadlines, or session expiration yourself, you can use a `ScheduledExecutorService` or `Future` managed by the service; cancel the timer when processing finishes. Do not spawn an unbounded background thread without a shutdown path when the subscriber cancels.

## 8. Common Pitfalls

1. **Confusing cancellation with completion:** calling `cancel()` and then waiting for `onComplete` to release resources. This can cause the program to hang. Clean up yourself after requesting cancellation or emit a separate completion signal.
2. **Confusing scope:** cancelling one subscriber but closing a shared publisher or executor, disrupting other subscribers.
3. **Forgetting to cancel data-producing tasks:** the subscription has stopped, but the file-reading loop, socket, timer, or job keeps running and producing data. Custom publishers must wire cancellation requests to the proper source-stopping mechanism.
4. **Releasing too early:** closing a resource while `onNext` is still using it. Synchronization or a protocol to wait for in-flight callbacks/tasks is required.
5. **Assuming cancellation is instantaneous:** late callbacks can still arrive; callbacks must check the stopped state and avoid unintended side effects.
6. **Non-idempotent cleanup:** a timeout and an error branch both close the resource, causing a race or secondary error. Use a single shared cleanup path.
7. **Calling `request(0)` to "pause":** under the Flow contract, non-positive demand is an error. To pause, simply stop requesting more demand; to stop permanently, call `cancel()`.
8. **Requesting too much to bypass backpressure:** `request(Long.MAX_VALUE)` is equivalent to nearly unbounded demand; it is only appropriate when the consumer can truly handle incoming data at full rate.
9. **Not handling close-before-subscribe:** `onSubscribe` arriving after `close()` still requests data or holds onto a subscription that is never cancelled.
10. **Closing an unowned executor:** shutting down a shared pool just because one consumer stream finished.

## 9. Lifecycle Testing Checklist

To verify a real-world Java Flow pipeline, at least the following cases should be covered:

- The subscriber receives `onSubscribe` and proactively cancels before requesting the first item; `onComplete`/`onError` is not required.
- The subscriber calls `request(1)`, receives one item, and cancels; verify no new side effects are processed after cancellation is marked, even if callbacks arrive late.
- Cancelling concurrently with `onNext` or concurrently with shutdown; resources are not closed while a callback is still using them.
- Calling cancel/`close()` multiple times; owned resources are released only once.
- An error occurs in the source or item processing; logging, service completion, and cleanup are not missed.
- The publisher has other subscribers; cancelling one subscriber does not affect the remaining streams.
- Timeout/close before `onSubscribe`; the late-arriving subscription is cancelled immediately.
- After shutdown, no dedicated threads, file descriptors, connections, or scheduled tasks remain held indefinitely.

Asynchronous tests should use `CountDownLatch`/`CompletableFuture` or deterministic synchronization tools; avoid drawing conclusions from `Thread.sleep(...)` and fragile timing assumptions.

## 10. Practical Conclusion

In Java Flow, `Subscription.cancel()` is a command to **stop a single subscriber's demand for data**, not a guarantee that the entire pipeline has shut down. Cancellation can take effect with a delay, and a cancelled subscription does not necessarily receive a terminal signal. To manage the lifecycle properly, identify the resource owner, create a single-execution cleanup path for cancellation/error/completion, coordinate with in-flight work, and use a separate signal if the service must wait for an actual stop.

Official API references:

- [`Flow.Subscription` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`Flow.Subscriber` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [`SubmissionPublisher` (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
