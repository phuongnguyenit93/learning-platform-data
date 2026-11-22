# Closing SubmissionPublisher, Terminal Signals, and the Publisher Executor Lifecycle

## 1. Three Distinct Lifecycles That Are Easily Confused

`SubmissionPublisher<T>` in `java.util.concurrent` is an implementation of `Flow.Publisher<T>`. It emits non-`null` items **asynchronously** to current subscribers, using an `Executor` to run the callbacks. When the source has no more data or fails, the publisher needs to terminate the subscription properly.

You must distinguish **three events**:

1. **The publisher stops accepting data:** `publisher.close()` or `publisher.closeExceptionally(error)` transitions the publisher to the closed state, rejecting new `submit`/`offer` calls.
2. **Subscribers receive the terminal signal:** the `onComplete()` or `onError(Throwable)` callback may be dispatched via the executor **after the close call returns**. The “publisher is closed” state does not prove that “all subscribers have finished running.”
3. **The executor stops running:** the executor passed into the constructor has its own lifecycle. Closing `SubmissionPublisher` **does not mean calling `ExecutorService.shutdown()`**. The executor's owner must decide on its own when to shut it down.

Confusing these three events can cause the program to exit before callbacks run, shut down the executor too early leading to rejected tasks, or leave a dedicated thread pool running forever even though the publisher has closed.

This lesson focuses on **general Java concurrency**: `Flow`, `SubmissionPublisher`, `ExecutorService`, and resource cleanup. This is JDK knowledge independent of Spring.

## 2. Reviewing the Flow Contract Before Discussing Termination

Four core interfaces:

| Interface | Role |
| --- | --- |
| `Flow.Publisher<T>` | Source that allows registering a `Subscriber` and emits data signals. |
| `Flow.Subscriber<T>` | Receives `onSubscribe`, `onNext`, `onError`, and `onComplete`. |
| `Flow.Subscription` | Per-subscriber link; `request(n)` grants demand, `cancel()` requests cancellation. |
| `Flow.Processor<T,R>` | Acts as both an upstream subscriber and a downstream publisher. |

Logical lifecycle of **a single subscription**:

```text
publisher.subscribe(subscriber)
        |
        v
  onSubscribe(subscription)
        |
        +-- subscriber.request(n)  -> opens item quota
        |
        +-- onNext(item)           -> 0..n times according to demand
        |
        +-- ... may request more ...
        |
        +-- onComplete()           -> normal termination
             OR
            onError(error)         -> abnormal termination
```

`onComplete` and `onError` are **terminal signals**: a subscription must not receive any more `onNext` calls after it has terminated. The two terminal signals are mutually exclusive outcomes for the same subscription, not two consecutive steps.

`cancel()` is a *best-effort* request to stop the subscription, **not an `onComplete` signal**. A subscriber that actively cancels is not guaranteed to receive `onComplete`/`onError` afterward. Therefore, a program that wants to wait for termination must account for a cancellation branch that has no terminal callback.

## 3. close(): Normal Termination

`publisher.close()` is used when the publisher **has finished producing all valid data**.

According to the `SubmissionPublisher` contract:

- If not already closed, it begins sending `onComplete` to current subscribers.
- It stops accepting new publish calls; `isClosed()` returns `true`.
- Repeated calls are handled with “if not already closed” semantics (idempotent with respect to the closed state).
- **When `close()` returns, there is no guarantee that all subscribers have finished processing or have received the `onComplete` callback.**
- Submitted items are delivered in order to each current subscriber, unless dropped, cancelled, or an exception occurs. Subscribers still need to supply sufficient demand to consume items remaining in the buffer.

Conceptual ordering:

```text
Producer thread                  Delivery executor / subscriber
    |                                          |
    | submit(A)                                |
    | submit(B)                                |
    | close() --------------------------------> | onNext(A)
    | close() returns                          | onNext(B)
    |                                          | onComplete()
    |  (must wait for terminal separately if needed) |
    +------------------------------------------+
```

The timeline illustration **does not assert** that callbacks always start after `close`: they can run before, during, or after the close call. What is certain is that merely waiting for `close` to return does not prove that subscribers have completed.

When calling `submit(item)` after the publisher is closed, `IllegalStateException` is thrown. Even so, do not use `isClosed()` followed by `submit()` as an atomic check-and-act across producers: another thread may close the publisher after the check step. You need to coordinate producers or handle the race intentionally.

## 4. closeExceptionally(error): Termination Due to Error

`publisher.closeExceptionally(error)` is used when the source **cannot continue to complete normally**. If the publisher is not yet closed, the method sends `onError(error)` to current subscribers and stops accepting new items. Subscribers that register **after the publisher has closed exceptionally** also receive `onSubscribe` followed by the corresponding error signal.

Points to remember:

- `error` must be non-`null`; passing `null` throws `NullPointerException`.
- `getClosedException()` returns the error used to close exceptionally; returns `null` if not closed or closed normally.
- Calling `closeExceptionally` returns **without waiting** for all `onError` callbacks to complete.
- Do not use `closeExceptionally` merely to express that the consumer is no longer interested in data; that is usually the `Subscription.cancel()` branch.
- If the publisher was already closed previously, another close call does not alter the terminal outcome of subscriptions that have already ended. Decide the terminal outcome in one clear place.

Some errors originating solely inside a **subscriber callback** do not mean the publisher must automatically emit `onError` to all remaining subscribers. For example, according to `SubmissionPublisher`, when a subscriber's method throws an exception, that subscription may be cancelled. The constructor has a callback to handle exceptions from `onNext`; it does not automatically turn one subscriber's failure into a global error for all subscribers. A policy for stopping the entire pipeline must be designed separately.

## 5. Java 17+ Example: Closing Normally and Waiting for the Subscriber to Actually Complete

`SubmissionPublisher.consume(Consumer)` creates a subscriber that automatically requests and processes items via the `Consumer`, and returns a `CompletableFuture<Void>` to observe when the subscription finishes or fails. This is a concise way to distinguish `close` from **waiting for the terminal signal**.

Save the file `PublisherNormalCloseDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class PublisherNormalCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        SubmissionPublisher<String> publisher =
                new SubmissionPublisher<>(delivery, 8);

        try {
            CompletableFuture<Void> completed =
                    publisher.consume(item -> System.out.println("onNext: " + item));

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            // close() only marks the end and dispatches the signal asynchronously.
            // get() waits for the consumer to receive the terminal signal.
            completed.get(5, TimeUnit.SECONDS);

            System.out.println("subscriber completed");
            System.out.println("publisher closed: " + publisher.isClosed());
            System.out.println("executor closed by publisher: " + delivery.isShutdown());
        } finally {
            publisher.close();      // Safe to call again if already closed.
            delivery.shutdown();    // Executor is owned by main.
            if (!delivery.awaitTermination(5, TimeUnit.SECONDS)) {
                delivery.shutdownNow();
            }
        }

        System.out.println("executor shutdown: " + delivery.isShutdown());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 PublisherNormalCloseDemo.java
java PublisherNormalCloseDemo
```

Output when executed successfully:

```text
onNext: A
onNext: B
subscriber completed
publisher closed: true
executor closed by publisher: false
executor shutdown: true
```

Because `completed.get(...)` waits for completion before `main` prints the status, this output order does not depend on whether the executor starts the callbacks quickly or slowly. The two `onNext` calls are ordered A then B within the same subscription; the `CompletableFuture` is completed when the subscriber receives `onComplete`.

`delivery.isShutdown()` still returns `false` before `main` itself calls `shutdown()`, proving that closing the publisher **does not own and does not shut down the caller-supplied executor**. `shutdown()` rejects new tasks and allows already-submitted tasks to continue; `awaitTermination` waits for the executor to finish, while `shutdownNow()` is only an emergency stop attempt when the timeout expires.

### Why Not Just Write try-with-resources and Exit main?

`SubmissionPublisher` implements `AutoCloseable`, so you can write:

```java
try (SubmissionPublisher<String> publisher =
             new SubmissionPublisher<>()) {
    publisher.submit("item");
}
```

This is **illustrative code**, not a standalone program. `try-with-resources` calls `close` automatically, but **does not wait for subscribers to finish receiving `onComplete`** and does not let you infer that all callbacks have finished running upon exiting the block. If the subscriber's result matters, an explicit completion signal/future or latch is required.

## 6. Java 17+ Example: closeExceptionally and onError

The following example uses `CountDownLatch` to wait for the error callback, avoiding reliance on `Thread.sleep()`. It does not submit items before closing exceptionally, because the ordering between pending data and an exceptional close decision is a separate concern of cancellation/terminal rules; here we want to observe the `onError` branch purely.

Save the file `PublisherExceptionalCloseDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class PublisherExceptionalCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService delivery = Executors.newSingleThreadExecutor();
        SubmissionPublisher<String> publisher =
                new SubmissionPublisher<>(delivery, 8);

        CountDownLatch terminal = new CountDownLatch(1);
        AtomicReference<String> outcome = new AtomicReference<>();

        try {
            publisher.subscribe(new Flow.Subscriber<>() {
                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    subscription.request(Long.MAX_VALUE);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("unexpected item: " + item);
                }

                @Override
                public void onError(Throwable error) {
                    outcome.set("onError: " + error.getClass().getSimpleName()
                            + ": " + error.getMessage());
                    terminal.countDown();
                }

                @Override
                public void onComplete() {
                    outcome.set("onComplete");
                    terminal.countDown();
                }
            });

            publisher.closeExceptionally(new IOException("source failed"));

            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Terminal signal timed out");
            }

            System.out.println(outcome.get());
            System.out.println("publisher closed: " + publisher.isClosed());
            System.out.println("closed cause: "
                    + publisher.getClosedException().getMessage());
        } finally {
            publisher.close();
            delivery.shutdown();
            if (!delivery.awaitTermination(5, TimeUnit.SECONDS)) {
                delivery.shutdownNow();
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 PublisherExceptionalCloseDemo.java
java PublisherExceptionalCloseDemo
```

Output:

```text
onError: IOException: source failed
publisher closed: true
closed cause: source failed
```

`onSubscribe` arrives before the terminal callback, even though both are executed asynchronously. In this example there is only a source error, so the subscriber enters `onError` instead of `onComplete`. `CountDownLatch` communicates the completion point to the main thread; `AtomicReference` passes the result safely between threads.

In real applications, `onError` should log and propagate the failure signal to the appropriate caller, as well as release resources owned by the subscriber. Simply printing an error message does not guarantee that the caller handles the error properly.

## 7. Subscribing After the Publisher Has Closed

A subscriber can call `subscribe(...)` **after** the publisher has closed. `SubmissionPublisher` handles this according to the closed state:

- **Normal close:** the new subscriber still receives `onSubscribe` followed by `onComplete`.
- **Exceptional close:** the new subscriber receives `onSubscribe` followed by `onError` with the recorded exception.
- There is no mechanism to replay all items submitted before closing. `SubmissionPublisher` is a broadcast mechanism for current subscribers, not a historical event log.
- Callbacks still go through the publisher's executor; therefore, allowing “late” subscribers requires ensuring that **the executor is still capable of executing tasks**.

This explains why you should not shut down the executor immediately when the publisher closes if late registrations or terminal signal observations are still actively allowed afterward. If the program lifecycle permits late subscribers, you must define a policy and deadline for this. A useful management pattern is to **stop creating new subscriptions first**, let all existing subscribers reach their terminal signal, and only then shut down the pipeline's executor.

Do not use `hasSubscribers()` or `getNumberOfSubscribers()` to confirm on your own that all callbacks have completed. These methods are for observing state, not a mechanism to join on all terminal signals.

## 8. Who Is Responsible for Shutting Down the Executor?

`SubmissionPublisher` uses an `Executor` to invoke subscriber methods. There are two main configurations:

### 8.1. Default Publisher

```java
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();
```

Typically the JDK uses `ForkJoinPool.commonPool()`, or creates a thread per task in configurations that do not support a minimum parallelism level. **Never shut down the JVM-wide `ForkJoinPool.commonPool()` as if it were the publisher's private pool.** You cannot assume the default executor is an exclusive thread pool dedicated solely to that publisher.

### 8.2. Application-Supplied Executor

```java
ExecutorService delivery = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(delivery, 64);
```

These two lines **only illustrate initialization**, without complete cleanup logic.

`delivery` belongs to the component that creates/manages the executor. If the application creates a dedicated pool for the publisher, the application must call `shutdown()` and optionally `awaitTermination(...)` when no more tasks need to be accepted. If the executor is shared across multiple publishers or other components, **no individual publisher may shut down the shared executor on its own**; the shared owner decides when to close it after all components have finished.

### Safe Shutdown Sequence

A typical lifecycle management sequence:

1. **Stop producers:** stop timers, loops, or sources calling `submit`/`offer`; synchronize with active producers to avoid racing `submit` with `close`.
2. **Decide the final outcome:** call `close()` when data ends normally; call `closeExceptionally(error)` when the publisher fails and cannot complete.
3. **Wait for data consumption and terminal callbacks:** use the `CompletableFuture` from `consume`, a self-managed latch/future in the subscriber, or an equivalent synchronization mechanism. With multiple subscribers, wait for each required subscriber.
4. **Shut down the owned executor:** call `shutdown()`, then `awaitTermination` with a timeout; handle timeout and interruption according to application policy.
5. **Clean up other resources:** close sources, buffers, or connections according to their ownership.

Do not apply this recipe mechanically in every system: there are cases where an emergency shutdown must discard data and cannot wait for completion. Distinguish between **graceful shutdown** (prioritizes processing all data) and **forced shutdown** (prioritizes exiting quickly, accepting loss of pending work).

### Why Does Early Shutdown Cause Errors?

If `executor.shutdown()` happens **before** the publisher has queued the final callbacks, the executor may throw `RejectedExecutionException` when the publisher tries to submit tasks. The `SubmissionPublisher` Javadoc allows executor exceptions to be thrown back from publish paths. In that case, data may not have reached all subscribers. Do not assume that merely catching the exception means every subscriber has received `onError`.

In particular, `shutdownNow()` returns tasks that have not started and attempts to interrupt running tasks, **with no guarantee that all callbacks have finished**. Use it as a conditional timeout/forced-shutdown measure, and accept that delivery may be incomplete.

## 9. How to Wait Properly: Futures, Latches, and Avoiding Deadlocks

### CompletableFuture from consume

`publisher.consume(consumer)` returns `CompletableFuture<Void>`:

- Completes normally when the subscriber is delivered `onComplete`.
- Completes exceptionally if the publisher delivers `onError`, the consumer throws an exception, or the future is cancelled.
- `get(timeout, unit)` waits with a bound and lets the caller handle `TimeoutException` or `ExecutionException`.

This pattern is suitable when you only need a subscriber to consume all items via a `Consumer`.

### Custom Subscriber Implementation

For multiple terminal states or complex processing, a subscriber can complete a `CompletableFuture<Result>` in `onComplete` or complete it exceptionally in `onError`. A `CountDownLatch` is simple when only a single completion event is needed. You must think separately about the `cancel()` branch, because cancellation usually does not bring a terminal callback.

### Do Not Wait on the Same Thread That Must Run the Callback

For example: using a **single-thread executor** both to submit items and to wait on a latch that only `onComplete` running on that very same executor can count down. The executor is occupied by the waiting task, so the final callback cannot run → deadlock. Wait on a different coordinating thread or use an asynchronous design that does not block the executor from processing signals.

Do not use `Thread.sleep(1000)` as a substitute for a completion signal. On a fast machine it may be wasteful; on a slow machine it may still be insufficient. A latch/future mechanism with a timeout yields verifiable results.

## 10. When There Are Multiple Subscribers or Multiple Producers

Each subscriber of `SubmissionPublisher` has its own buffer/demand. Closing the publisher delivers termination to **current subscribers**, but they may finish at different times.

If there are three subscribers and the program needs all three to finish, **a single latch on the first subscriber is not enough**. You can use three futures or a `CountDownLatch(3)`, with each subscriber counting down exactly once when it receives its terminal signal. If a subscriber actively cancels and does not receive a terminal signal, there must be a separate cancellation notification mechanism to avoid waiting indefinitely.

When multiple producers share a publisher, decide who has the authority to emit the final signal. One producer calling `close` while another producer is still calling `submit` can cause the other to receive `IllegalStateException`. Coordinate closing in a single lifecycle owner after blocking new emissions and waiting for producers to finish their required submissions.

You should also isolate per-subscriber errors from whole-source errors. One subscriber processing slowly or throwing an exception does not necessarily mean the source is no longer valid for other subscribers. Policies for continuing, cancelling individually, failing the entire pipeline, or retrying must be defined based on business requirements.

## 11. Subtle Points About submit, Buffers, and Backpressure When Closing

`SubmissionPublisher` uses independent per-subscription buffers to smooth out speed differences between producers and consumers. The methods have different behaviors:

| API | Main Behavior |
| --- | --- |
| `submit(item)` | Typically blocks uninterruptibly when a subscriber's buffer is full; delivers items via asynchronous callbacks. |
| `offer(item, onDrop)` | Allows dropping items when space is lacking and invokes the handler if provided; may retry once depending on the handler's result. |
| `Subscription.request(n)` | Subscriber grants positive demand, increasing the `onNext` quota allowed to be received. |
| `Subscription.cancel()` | Requests subscription cancellation, typically with no terminal callback afterward. |
| `close()` | Stops accepting new items; emits the normal completion signal. |
| `closeExceptionally(error)` | Stops accepting new items; emits the error signal. |

A subscriber that has not called `request` enough to receive buffered items can prolong waiting for `onComplete`. Therefore, graceful shutdown design must rely on subscriber progress and demand coordination, not just calling `close` and waiting indefinitely.

If the application allows drops in `offer`, you must not claim that the subscriber received “every single item” just because it received `onComplete`. `onComplete` means **no more new items for the subscription**, not a guarantee of zero data loss regardless of prior overflow policies.

`estimateMaximumLag()` and `estimateMinimumDemand()` are for monitoring, not synchronization barriers to decide that “all callbacks have finished processing.” When certainty is needed, use a real completion protocol.

## 12. Handling Errors, Interruption, and Timeouts Responsibly

A high-quality shutdown procedure must also handle failure branches:

- **Timeout waiting for subscribers:** record which components have not finished; decide whether to `cancel`, close exceptionally, or stop waiting depending on the application. Do not report completion if the terminal callback has not been observed.
- **Interruption:** if the coordinating thread is interrupted during `await` or `get`, restore the interrupt flag with `Thread.currentThread().interrupt()` when catching `InterruptedException`, and terminate or delegate cleanup according to policy. The example code uses `main throws Exception` for simplicity, but production logic needs to handle this proactively.
- **Subscriber throws an exception:** `SubmissionPublisher` may cancel the subscription; the special handler in the constructor applies when `onNext` throws an exception. Do not assume the caller receives subscriber exceptions via `submit`.
- **Executor rejection:** some paths may throw `RejectedExecutionException`; do not assume all subscribers have received the item or terminal signal.
- **Multiple closes:** treat the first close outcome as the lifecycle outcome; calling `close` again is not a technique for resending the terminal signal “just to be sure.”

Never hold an application lock while waiting for a callback if the callback needs that same lock to make progress. Waiting for terminal signals should happen after releasing synchronization locks that could cause deadlocks.

## 13. API Selection Table by Scenario

| Scenario | Appropriate Action |
| --- | --- |
| All items emitted and all producers finished | `close()`, wait for critical subscribers to receive the terminal signal. |
| Source broken, cannot continue | `closeExceptionally(cause)`, record the error, and wait for callbacks as needed. |
| Only one subscriber no longer wants to receive | `Subscription.cancel()`, manage the completion point of the cancelled task yourself. |
| Want to process items via a simple function | `consume(consumer)` and wait on the `CompletableFuture`. |
| Need to know all subscribers completed | Per-subscriber latch/future coordinated at the owner. |
| Dedicated pool for delivery | After completion, owner calls `shutdown` then `awaitTermination`. |
| Executor shared across multiple publishers | Only the shared owner shuts it down after all components finish. |
| System must stop immediately | May use `shutdownNow` or controlled cancellation; accept and report that work may be incomplete. |

## 14. Self-Check Exercises

**Q1:** After calling `publisher.close()`, `publisher.isClosed()` returns `true`. Can we conclude that the subscriber has already run `onComplete()`?  
**A:** No. Callbacks are dispatched asynchronously; a separate completion signal is required if you need to wait.

**Q2:** How does `closeExceptionally(new IOException("failed"))` differ from `close()`?  
**A:** It delivers `onError` with the exception to subscribers, whereas `close()` delivers `onComplete` when data ends normally.

**Q3:** An application creates an `ExecutorService` and passes it to the `SubmissionPublisher` constructor. Does closing the publisher shut down that executor?  
**A:** No. The executor's owner manages its shutdown separately.

**Q4:** What is the risk of awaiting a `CountDownLatch` inside the very same single-thread delivery executor?  
**A:** Deadlock if the callback needed to count down the latch can only run on that occupied executor.

**Q5:** A publisher calls `close` while another producer calls `submit`. What can happen?  
**A:** The other producer may receive `IllegalStateException` once the publisher is closed; lifecycle coordination between producer threads is needed.

**Q6:** If a subscriber calls `cancel()`, is it guaranteed to receive `onComplete`?  
**A:** No. Cancel is a best-effort cancellation request, not a terminal signal.

**Q7:** Does `onComplete` mean no items were dropped earlier?  
**A:** No. An `offer` policy may have dropped items; completion only indicates no more new items for that subscription.

**Q8:** If a publisher uses the default `ForkJoinPool.commonPool()`, should you call `commonPool().shutdownNow()` after `close`?  
**A:** No. The common pool is a shared JVM resource, not the publisher's private executor.

**Key takeaway:** **Close the publisher → wait for terminal signals → shut down the owned executor** are three separate responsibilities. `close()` and `closeExceptionally()` decide how the stream ends; `onComplete`/`onError` confirm the outcome at the subscriber; the executor owner ensures delivery resources are released at the right time.

## Official References

- [Oracle Java 21 API — SubmissionPublisher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [Oracle Java 21 API — Flow.Subscriber](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Oracle Java 21 API — Flow.Subscription](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [Oracle Java 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
