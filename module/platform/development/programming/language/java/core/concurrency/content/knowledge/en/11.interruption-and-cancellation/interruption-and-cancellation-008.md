# How Does Timeout Differ from Cancellation? — Java Concurrency

A Java call can run too long because a thread is waiting for a lock, waiting for an element in a queue, waiting for I/O, or performing a time-consuming computation. In such cases, applications often need two mechanisms that sound similar but are **not synonymous**:

- **Timeout:** sets a **waiting time limit** or time budget for an operation. When the limit is exceeded, the *waiter* may receive an "expired" result, `false`, `null`, or an exception. This **does not by itself confirm that the awaited work has stopped**.
- **Cancellation:** **requests termination of the work** or prevents it from starting, following a cancellation protocol. The request may be accepted, but the task still has to cooperate to stop, handle side effects, and release resources. Not all cancellation APIs do this immediately or via interruption.

A simple example: thread A calls `future.get(100, MILLISECONDS)` to wait for a task on thread B. If 100 ms elapses, A receives a `TimeoutException` and moves on. **B's task may still be running**. If A wants to request that B stop, a separate step is needed, such as `future.cancel(true)` according to the contract of the future/producer in use. Even when calling cancel, one must not assume the task has definitely stopped or that external data has been rolled back.

This article belongs to the **Interruption & Cancellation** section of **general Java concurrency**, focusing on JDK 17+ and `java.util.concurrent`, without using Spring Framework-specific concurrency components.

## 1. A Quick Comparison Table

| Aspect | Timeout | Cancellation |
| --- | --- | --- |
| Primary question | "Did I wait past the time limit?" | "Did I request that the work stop / not run anymore?" |
| Focus | Waiting time, deadline, or operation timeout | Lifecycle and state of the task/operation |
| Java examples | `Future.get(timeout, unit)`, `BlockingQueue.poll(timeout, unit)`, `Lock.tryLock(timeout, unit)` | `Future.cancel(...)`, `Thread.interrupt()`, cancellation token, closing a resource |
| Default impact on another worker | **Not necessarily** | May send a signal/request, but **does not guarantee immediate stop** |
| Common results | `TimeoutException`, `false`, `null`, or a specific I/O exception | `CancellationException` when getting the result of a canceled future; cancel flag/state; interruption depending on the API |
| Can the task still be running? | Yes | Also yes, if it does not cooperate or the API does not support stopping |
| Do external resources auto-rollback? | No | No |
| Required contract | Deadline, time unit, expiration condition | Who owns the task, how the request is propagated, cleanup, completion state |

**Timeout can lead to cancellation**, but that is a **policy actively chosen by code**, not a Java rule that applies to every method.

## 2. Distinguishing Four Events in a Request

In a concurrent system, at least four distinct milestones can occur:

1. **Caller wait expires:** the caller does not want to wait any longer.
2. **Cancellation request is issued:** the caller or coordinator calls cancel/interrupt/close.
3. **Worker observes the cancellation request:** the worker exits a blocking call or checks a cancellation token.
4. **Worker actually finishes cleanup:** no longer doing work, locks/permits/resources have been released according to protocol.

Diagram:

```text
Caller                           Task/worker
------                           -----------
submit task  ------------------> start work
wait up to 100 ms                 |
       |                          | doing work
timeout (caller stops waiting)    |
       |                          | STILL RUNNING possible
optional cancel(true) ----------> interrupt request / cancel flag
       |                          | detects request when/if supported
caller returns                    | stops useful work, runs cleanup
                                  +--> terminated/cleaned up
```

These milestones can be very far apart in time. An API returning `true` from `cancel()` **does not automatically prove** that the final step has completed. A caller wanting to wait for cleanup needs a separate completion protocol if the cancellation contract does not include it.

## 3. At What Layers Can a "Timeout" Live?

The word "timeout" does not define a single behavior:

- **Timeout when waiting for a result:** the caller stops waiting; the task may continue. For example, `Future.get(100, MILLISECONDS)`.
- **Timeout when acquiring a resource:** if the lock/permit/queue item cannot be acquired within the limit, the operation returns failure; the work requiring that resource has not started. For example, `ReentrantLock.tryLock(...)`.
- **Timeout of an I/O operation:** a network read/connection attempt may report timing out per the I/O contract; this does not automatically roll back the remote request or close all resources.
- **Timeout imposed on a future's state:** an API may **complete the future with an error/fallback result**, while the underlying work may still be running. For example, `CompletableFuture.orTimeout(...)`.
- **Deadline for an entire workflow:** a shared end point in time to bound multiple consecutive calls; each step receives the remaining time.

Read the **Javadoc of the exact method** before inferring consequences. A `TimeoutException` from `Future.get` does not carry the same lifecycle meaning as a `SocketTimeoutException` from a network read operation.

## 4. Java 17+ Example: `Future.get(timeout)` Only Limits Wait Time

Save as `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> {
                release.await();
                return 42;
            });

            boolean timedOut = false;
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            System.out.println("Wait timed out: " + timedOut);
            System.out.println("Task done after timeout: "
                    + future.isDone());

            release.countDown();
            System.out.println("Later result: " + future.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Stdout on a normal run:

```text
Wait timed out: true
Task done after timeout: false
Later result: 42
```

**Why is the output deterministic?**

- The task waits on `release`, which has not been opened yet. Therefore, even if the worker is scheduled early, the task still **cannot complete** before `main` opens the latch.
- `get(30, MILLISECONDS)` expires on the `main` thread and throws `TimeoutException`; the code **never calls `cancel`**.
- `future.isDone()` remains `false` because the task has neither completed nor been canceled.
- After `release.countDown()`, the worker can return 42; `main` calls `future.get()` again to retrieve the result.
- `finally` releases the latch even on error to avoid leaving the worker waiting indefinitely, then requests executor shutdown.

A single `get` timing out **does not permanently put the future into a timed-out state**. The same future can be waited on again, return a result, or be canceled according to a separate policy.

## 5. If a Timeout Occurs, What Can the Task Do Next?

After `future.get(timeout)` throws `TimeoutException`:

- The task may **not have started yet** because it is still in the executor queue.
- The task may **be running** and still writing data, invoking callbacks, or sending network requests.
- The task may **complete right after the caller expires**.
- The task may later fail with another exception whose result the caller no longer retrieves.
- Another job may depend on the task's side effects, even though the external request returned "timeout".

Therefore, "the caller expired" and "the task stopped" are not equivalent states. If a timeout is the reason you do not want to use a late-arriving result, you need to define **stale-result handling**, idempotency, or a generation/version token so that a late result does not overwrite newer state.

You should not use `Thread.sleep(...)` to conclude that a task has definitely stopped; only a well-defined completion primitive or lifecycle protocol can tell you that.

## 6. What Does `Future.cancel(boolean)` Actually Promise?

`Future.cancel(mayInterruptIfRunning)` attempts to cancel the associated computation. The parameter:

- `false`: if the computation has already started, do not request interrupting the running thread via this parameter; an implementation may not stop an executing task.
- `true`: if the task is running on an appropriately managed thread, the implementation may **request an interrupt** on that thread to give it an opportunity for cooperative stopping.

When cancellation succeeds under the `Future` contract, calls to `isCancelled()` and `isDone()` may reflect the canceled/done state of the **future**. Calling `get()` on a canceled future throws `CancellationException`. However, **a future's canceled state is not a certificate that the worker has finished cleanup**.

In particular:

- `cancel(true)` **does not forcibly kill** the thread.
- Many blocking calls in Java respond to interruption; some I/O does not do so immediately, or has different exceptions/semantics.
- Code may catch `InterruptedException` and swallow it, allowing the task to continue.
- The task may be in the middle of an external side effect; an HTTP request or file write that has already occurred cannot be automatically undone.
- A task that already completed before the cancel call may not be canceled; you must account for the race between completion and cancellation.

## 7. Java 17+ Example: Cancellation Request and Cooperative Worker Stop

Save as `FutureCancelDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<Integer> future = pool.submit(() -> {
                try {
                    entered.countDown();
                    Thread.sleep(60_000);
                    return 42;
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return -1;
                } finally {
                    stopped.countDown();
                }
            });

            entered.await();
            boolean accepted = future.cancel(true);
            stopped.await();

            boolean canceledOnGet = false;
            try {
                future.get();
            } catch (CancellationException e) {
                canceledOnGet = true;
            }

            System.out.println("Cancellation accepted: " + accepted);
            System.out.println("Worker saw interrupt: "
                    + sawInterrupt.get());
            System.out.println("Future canceled: " + future.isCancelled());
            System.out.println("Get canceled: " + canceledOnGet);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac FutureCancelDemo.java
java FutureCancelDemo
```

Stdout on a successful run of the program:

```text
Cancellation accepted: true
Worker saw interrupt: true
Future canceled: true
Get canceled: true
```

Why does the program not rely on accidental scheduling?

1. `entered.countDown()` indicates the task has entered the `try` block; `main` does not cancel a task that has not started running.
2. The task attempts to sleep for 60 seconds. If `main` interrupts **before** the worker calls sleep, sleep sees the flag and throws `InterruptedException`; if the interrupt happens **during** sleep, the call is woken up with the exception.
3. The catch block marks `sawInterrupt` and restores the flag with `Thread.currentThread().interrupt()` so as not to lose the cancellation request information at a boundary that cannot throw.
4. `finally` always counts down `stopped` when the task leaves that block; `main` calls `await()` before checking the result, confirming that the demo cleanup has run.
5. Because the future was canceled, `get()` throws `CancellationException` and **does not return -1** even though the task body has a branch returning -1 when interrupted.

Key point: the example uses a task that cooperates with interruption for illustration. **Do not generalize that every `Future.cancel(true)` in every implementation guarantees the worker stops immediately**. `stopped` is a separate completion signal of the demo; real applications should also have a way to observe cleanup if needed.

## 8. `cancel(false)` and `cancel(true)` Are Not Absolute "Light/Heavy" Modes

The parameter only indicates **whether to allow attempting to interrupt a running worker**, not the priority of the request or the completion time.

With `FutureTask` / tasks from `ExecutorService`, `cancel(false)` may transition the future to the canceled state while the running worker continues if there is no other signaling mechanism. `cancel(true)` can help a worker waiting on an interruptible API exit faster, yet the worker can still ignore the interrupt or take time to clean up.

Common selection scenarios:

- A task has started and the work should not continue: consider `cancel(true)` when interruption is documented as safe and the task has proper cleanup.
- An operation must not be interrupted mid-critical-step, or has its own cancellation token: another approach may be used, but you must define how the still-running task behaves after the future is canceled.
- You only want to avoid using a late result, while letting background work finish to populate a cache: **timing out only the wait** and letting the task continue can be a valid policy.

Do not choose `cancel(true)` reflexively if the task holds a resource whose protocol is unsafe to abort mid-flight. **Cooperative cancellation** requires code to define cancellation points and post-cancellation invariants.

## 9. Timeout on `BlockingQueue` Is Bounded Waiting, Not "Canceling the Producer"

`BlockingQueue.poll(timeout, unit)` waits at most the specified duration to retrieve an element. If no element is available when the time limit expires, it returns `null`. It does not send a stop command to any other producer.

Save as `QueueTimeoutDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        Integer first = queue.poll(20, TimeUnit.MILLISECONDS);
        System.out.println("First poll timed out: " + (first == null));

        queue.offer(7);
        Integer second = queue.poll(1, TimeUnit.SECONDS);
        System.out.println("Next item: " + second);
    }
}
```

```bash
javac QueueTimeoutDemo.java
java QueueTimeoutDemo
```

Exact stdout:

```text
First poll timed out: true
Next item: 7
```

No producer added an element before the first `poll`, so the result is `null` after the wait duration. Failing to retrieve an item **does not change the cancellation state of the queue or of any thread**. Afterward, the program adds `7` and retrieves it normally.

A `poll` that times out is different from a `take()` that gets interrupted: `poll` returns `null` per its timeout contract, whereas `take` can throw `InterruptedException` when the waiter is requested to be interrupted. They must be handled in two different logic branches.

## 10. Timeout While Waiting for a Lock Does Not Mean the Lock Holder Is Canceled

`ReentrantLock.tryLock(timeout, unit)` attempts to acquire the lock within a time limit and may return `false` if it cannot acquire it. The caller fails to acquire the lock; it **does not send a cancellation request to the thread holding the lock**.

An example with explicit coordination, saved as `TimedLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedLockDemo {
    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderAcquired = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderAcquired.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "lock-holder");

        holder.start();
        holderAcquired.await();

        boolean acquiredWhileHeld = false;
        try {
            acquiredWhileHeld =
                    lock.tryLock(30, TimeUnit.MILLISECONDS);
        } finally {
            if (acquiredWhileHeld) {
                lock.unlock();
            }
        }

        releaseHolder.countDown();
        holder.join();

        boolean acquiredAfterRelease =
                lock.tryLock(1, TimeUnit.SECONDS);
        try {
            System.out.println("Acquired while held: "
                    + acquiredWhileHeld);
            System.out.println("Acquired after release: "
                    + acquiredAfterRelease);
        } finally {
            if (acquiredAfterRelease) {
                lock.unlock();
            }
        }
    }
}
```

```bash
javac TimedLockDemo.java
java TimedLockDemo
```

Stdout on a normal run:

```text
Acquired while held: false
Acquired after release: true
```

On the first attempt, `holder` definitely owns the lock because `main` waited on `holderAcquired` and has not opened `releaseHolder` yet. Thus the caller cannot acquire the lock within the timeout, unless `holder` is unexpectedly interrupted or a party actively opens the latch. After `main` opens the latch and `join` completes, the lock has been released, so the second attempt succeeds.

**Good to know:** `tryLock(timeout, unit)` is an **interruptible** wait and declares `throws InterruptedException`. If the caller thread is interrupted while waiting, the exception does not mean the holder was canceled. In real code, always release `ReentrantLock` in `finally` when acquired.

## 11. `CompletableFuture.orTimeout` and `completeOnTimeout`

Java 9+ provides two important APIs:

- `future.orTimeout(timeout, unit)`: if not completed in time, **completes that CompletableFuture itself exceptionally** with `TimeoutException`.
- `future.completeOnTimeout(value, timeout, unit)`: if not completed in time, **completes that CompletableFuture itself normally** with a fallback value.

These methods **change the state of the CompletableFuture they are called on**, unlike `Future.get(timeout)` which only expires **the caller's wait**. However, **they do not automatically promise to interrupt or stop the underlying computation** being performed by another worker.

Save as `CompletableFutureTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableFutureTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> timeoutFuture =
                new CompletableFuture<>();

        timeoutFuture.orTimeout(20, TimeUnit.MILLISECONDS);

        boolean sawTimeout = false;
        try {
            timeoutFuture.join();
        } catch (CompletionException e) {
            sawTimeout = e.getCause() instanceof TimeoutException;
        }

        boolean laterCompletionAccepted = timeoutFuture.complete(7);

        CompletableFuture<Integer> fallbackFuture =
                new CompletableFuture<>();

        fallbackFuture.completeOnTimeout(
                99, 20, TimeUnit.MILLISECONDS);

        System.out.println("Exceptional timeout: " + sawTimeout);
        System.out.println("Later completion accepted: "
                + laterCompletionAccepted);
        System.out.println("Fallback: " + fallbackFuture.join());
    }
}
```

```bash
javac CompletableFutureTimeoutDemo.java
java CompletableFutureTimeoutDemo
```

Exact stdout:

```text
Exceptional timeout: true
Later completion accepted: false
Fallback: 99
```

Analysis:

1. `timeoutFuture` is initially not completed by any producer. After the deadline, it completes exceptionally.
2. `join()` throws `CompletionException`, whose cause is `TimeoutException`.
3. `complete(7)` after the future has completed exceptionally returns `false`: an already-completed result cannot be replaced by normal completion.
4. `fallbackFuture` also has no producer; it is completed with 99 after the deadline.
5. **There is no actual computing worker** in this example. This demonstrates separating *future result state* from *task execution state*. When there is an underlying asynchronous task, a timeout on the future **does not by itself prove** that the background task has stopped.

**Note:** `orTimeout` and `completeOnTimeout` return **that same CompletableFuture**. If another caller also holds a reference to it, they will observe the timeout-driven completion state; this is not merely a "temporary wait" like `get(timeout)`.

## 12. `CompletableFuture.cancel(true)` Differs from `FutureTask.cancel(true)`

Although `CompletableFuture` implements `Future`, its cancellation semantics have an important distinction: **the `mayInterruptIfRunning` parameter is not used to control the underlying computation** per `CompletableFuture`'s contract.

For example, with a `CompletableFuture.supplyAsync(...)` running on an executor: canceling the future can put the future into the canceled state and dependent stages may receive exceptional completion, but **it must not be assumed** that the worker was interrupted. If the task needs to stop cooperatively, the design must include a token, handle, or cancellation mechanism for the underlying work source.

Comparison:

| Construct | Timeout | Cancellation |
| --- | --- | --- |
| `Future` from `ExecutorService.submit` | `get(timeout)` expires the wait; task may continue | `cancel(true)` attempts to cancel and may request interrupting the running worker |
| `CompletableFuture` | `orTimeout`/`completeOnTimeout` can complete the future itself | `cancel(...)` transitions future to canceled but does not use the boolean to interrupt computation |
| `BlockingQueue` | `poll(timeout)` or `offer(timeout)` bounds waiting | No concept of canceling all producers/consumers solely from timeout; coordinate via interrupt, close protocol, or token |
| `ReentrantLock` | `tryLock(timeout)` bounds waiting for the lock | Does not cancel another thread holding the lock |

Do not rely on the shared name `cancel` to infer that every implementation affects threads in the same way.

## 13. `ExecutorService.invokeAll(timeout)` Is an Example Combining Both

Not every timeout API means "just stop waiting." `ExecutorService.invokeAll(tasks, timeout, unit)` has its own contract: execute a collection of tasks and wait for them to complete within the time limit; **when the method returns, any tasks that have not completed are canceled**.

Here the timeout of the **overall operation** is tied to the **cancellation policy** specified by the API. Do not project conclusions from `Future.get(timeout)` onto `invokeAll(timeout)`, or vice versa.

Similarly, `invokeAny(tasks, timeout, unit)` returns one successful result per its contract or may throw `TimeoutException` upon expiration; unfinished tasks follow the API's cancellation policy. Read the Javadoc regarding cancellation of remaining tasks and exceptions before using it with non-idempotent side effects.

**Takeaway:** the meaning of a timeout must always be interpreted **per method**, not merely by the exception name.

## 14. Deadlines: Why Use an Overall Time Budget?

Suppose a request has three steps:

```text
A: acquire lock   timeout 200 ms
B: read queue     timeout 200 ms
C: wait future    timeout 200 ms
```

If each step has *its own 200 ms timeout*, the total time can approach **600 ms** excluding overhead. That violates an "overall request at most 200 ms" requirement if that is the actual SLA.

A **deadline** is a shared point in time, while the **remaining budget** is the duration left at each step:

```text
start request
    |
    +--> deadline = start + 200 ms
    |
    +--> step A uses remaining time
    |
    +--> step B recomputes remaining time
    |
    +--> step C recomputes remaining time
    |
    +--> timeout/cancellation policy if budget exhausted
```

In Java SE, `System.nanoTime()` is suitable for measuring **elapsed duration** because it does not depend on wall-clock system time that can be adjusted. Do not use `System.currentTimeMillis()` as the primary clock for durations sensitive to clock adjustments.

### Avoid Naive Deadline Calculations for Very Large Timeouts

A common way to write it:

```java
long deadline = System.nanoTime()
        + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
```

This is an illustrative snippet, not a class with `main`. For normal finite timeouts, it is easy to understand. However, for extremely large intervals, `long` arithmetic can wrap. A library design needs to cap the budget, use **elapsed time** or integer-safe arithmetic, and clearly define zero/negative timeouts.

You cannot simply create a deadline and ignore it: **every blocking operation must be given the appropriate remaining time**. APIs that only wait indefinitely do not automatically become deadline-aware just because the caller holds a deadline variable.

## 15. Deadline Pattern Using Elapsed Time

A helper to compute remaining budget without relying on wall-clock time:

```java
static long remainingNanos(
        long startNanos, long budgetNanos) {
    long elapsed = System.nanoTime() - startNanos;
    if (elapsed >= budgetNanos) {
        return 0L;
    }
    return budgetNanos - elapsed;
}
```

This is an illustrative method inside a Java class, **only valid within durations small enough** that elapsed subtraction under the `System.nanoTime()` model does not hit long-term wrap issues and `budgetNanos` is a valid non-negative number. For timeouts of milliseconds, seconds, or minutes in typical applications, this model is usable.

When step A finishes, recompute `remainingNanos` so that step B is not granted the full budget again. If remaining is 0, the caller can report deadline exceeded instead of continuing to wait.

But remember that **checking the budget** and **canceling a running task** are two different actions. After the budget is exhausted, the caller must **choose a policy**: simply stop waiting, return a fallback, request cancellation, or let it continue to populate a cache.

## 16. Timeouts in Blocking I/O: Read the Specific Contract

In Java network I/O, there are multiple timeout levels:

- **Connection timeout:** limits the time to establish a connection; depends on the API used to connect.
- **Read timeout:** limits a single wait to read data; for example, a socket may throw `SocketTimeoutException` per its configuration contract.
- **Write timeout:** there is no single uniform setting across all traditional stream/socket types; you must check the corresponding API/channel/client.
- **Overall operation deadline:** limits the entire request across multiple connects, writes, reads, decodes, retries, and processing; may require a separate policy.

Illustrative example with `java.net.Socket`:

```java
import java.net.InetSocketAddress;
import java.net.Socket;

Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.org", 80), 2_000);
socket.setSoTimeout(3_000);
// When reading from the socket input stream per contract,
// the read wait may end with a SocketTimeoutException.
```

This is an **illustrative snippet**, not a complete runnable program; no network request is performed in this lesson. `setSoTimeout` sets the **read timeout**; it is not an overall deadline for the entire connection, and certainly not a command to cancel a request that has already reached the server.

When a client times out, the server may **have already received and processed the request** while the response was delayed or lost. Therefore:

- A timeout does not prove that external side effects **have not occurred**.
- Retrying a non-idempotent operation can create duplicate transactions.
- You need a request ID / idempotency key, transaction status, deduplication, or a compensation policy suited to the business logic.
- A timeout usually only tells the caller that it **did not receive a result in time**.

Do not use `Thread.interrupt()` as a generic I/O cancellation mechanism without reading the contract; some APIs explicitly support interruption, while others do not or require closing the channel/socket.

## 17. Timeout and Cancellation When Side Effects Exist

Suppose a payment task:

```text
Client sends payment command -> Service is processing
Client times out -> no response seen
Client retries immediately -> may send the command a second time
```

There are three states to distinguish:

1. **Not started:** can be safely canceled if there is a protocol ensuring the work has not run yet.
2. **In progress:** partial side effects may exist; interrupt/cancel does not automatically roll back.
3. **Committed but response arrived late:** the caller timed out, yet the business action on the other side succeeded.

If the third state is possible, an API should not return "payment failed" solely because the client timed out, but rather return **"unknown / confirmation timed out"** and allow querying status by request ID. This is an example of a general principle, independent of any framework.

Solutions often require:

- **Idempotency token** so multiple retries of the same request do not create multiple side effects.
- **Deadline propagation** down to the execution layer when supported.
- **Cooperative cancellation** for the parts of work that can stop safely.
- **Result reconciliation** when the status outcome is unknown.
- **Cleanup** and resource release even if the caller has given up.

Concurrency mechanisms inside a single JVM cannot replace the transaction semantics of external systems.

## 18. Cancellation Tokens and Cooperative Checkpoints

Java has `Thread.interrupt()` as a thread-level signal. Some tasks also use an operation-level **cancellation token**. Example with `AtomicBoolean`:

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class CancellationToken {
    private final AtomicBoolean canceled = new AtomicBoolean();

    void cancel() {
        canceled.set(true);
    }

    boolean isCanceled() {
        return canceled.get();
    }
}
```

This is an illustrative class without `main`. A cooperative task checks:

```java
while (!token.isCanceled()) {
    processOneSmallStep();
}
```

The illustrative snippet assumes `token` and `processOneSmallStep` are declared. A token allows multiple processing steps to see the cancellation request without tying semantics to a specific thread. However:

- If a task is blocked in `BlockingQueue.take()`, the token **does not wake it up automatically**.
- The worker may only check the token between steps, so **cancellation latency** depends on each step.
- If a task has already completed, setting the token late does not undo the result.
- A token needs clear **ownership** and completion paths; callers should not equate `isCanceled()` with cleanup done.
- A token shared across multiple tasks requires **all tasks** to cooperate at their own checkpoints.

When work includes blocking calls, you can combine a token with interruption, short timeouts, closing resources, or sentinel values so the worker gets a chance to re-check.

## 19. Interruption Is Not a Forced Stop

`Thread.interrupt()` is a mechanism requesting that a thread cooperate. If a worker is calling `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()`, or many interruptible APIs, it may be woken up with `InterruptedException`; when the API throws the exception, **the interrupt flag is usually cleared** per that call's contract.

If a method cannot propagate checked exceptions, a good pattern is usually:

```java
try {
    performBlockingWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

This is an illustrative snippet with a hypothetical `performBlockingWork`. Restoring the flag avoids swallowing the interrupt request, and `return` helps the task stop cooperatively. **Merely restoring the flag and then continuing an infinite processing loop can create a busy loop or unintended work**.

If a method is allowed to declare `throws InterruptedException`, it can often **propagate the exception to the caller** instead of catching and restoring. Do not automatically turn interruption into a business error or skip cleanup policies.

### Cancellation Can Happen Before, During, or After an Operation

A task might check a token and then start a side effect; at that exact moment, the caller requests cancellation. You cannot infer that the side effect definitely has not started just because a flag was set. If you need to "guarantee it does not run if canceled before commit," you must establish a properly synchronized **commit/ownership point**, which may require locks, compare-and-set state, or a transaction protocol.

## 20. Race Between Completion, Timeout, and Cancellation

Three milestones can race:

```text
Task completes ----+
                   +--> Outcome observed by caller
Timeout occurs ----+
                   |
Cancel request ----+
```

Example `future.get(100ms)`:

- Task completes before timeout is observed: `get` may return the result or throw an exception from the task.
- Wait time expires while task is still incomplete: `get` throws `TimeoutException`.
- Task is canceled before caller retrieves the result: `get` may throw `CancellationException`.
- Caller thread is interrupted while waiting: `get` may throw `InterruptedException`.

**Do not promise an absolute ordering when events occur close together** beyond the API's contract. For instance, a task finishing near the deadline may cause different runs to observe different results; a correct program must handle both outcomes without breaking invariants.

In system design, a clear state machine is often needed:

```text
NEW -> RUNNING -> SUCCEEDED
              \-> FAILED
              \-> CANCEL_REQUESTED -> STOPPED
              \-> TIMED_OUT (caller outcome, task may still RUNNING)
```

This is a conceptual model. `TIMED_OUT` is usually a **caller-perspective state** and should not automatically be turned into a terminal task state unless the API actually enforces a cancellation/timeout completion contract.

## 21. Is Timeout a Return Value or an Exception?

Not every timeout throws `TimeoutException`:

| API | When wait time expires |
| --- | --- |
| `Future.get(timeout, unit)` | `TimeoutException` if result is not yet available per contract |
| `BlockingQueue.poll(timeout, unit)` | `null` when no item can be retrieved |
| `BlockingQueue.offer(item, timeout, unit)` | `false` when the item cannot be added |
| `CountDownLatch.await(timeout, unit)` | `false` if count has not reached 0 |
| `ReentrantLock.tryLock(timeout, unit)` | `false` if the lock cannot be acquired |
| `Thread.join(timeout)` | Returns after waiting, but caller must check `isAlive()` to know if thread is still alive |
| `Object.wait(timeout)` | Returns after notify, timeout, or spurious wakeup; must re-check guarded predicate |
| `CompletableFuture.orTimeout(...)` | Completes CompletableFuture exceptionally with `TimeoutException` |
| `CompletableFuture.completeOnTimeout(...)` | Completes CompletableFuture with fallback |
| Socket read with read timeout | May throw `SocketTimeoutException` per I/O contract |

That does not even count **interruption**: waiting methods can throw `InterruptedException` when the caller thread is requested to be interrupted. Timeout and interruption must be handled as **two distinct cases**, rather than catching both and always treating them as "the task was canceled."

## 22. `Thread.join(timeout)` Timeout Does Not Kill the Thread

`Thread.join(timeoutMillis)` only limits how long **the caller waits for the thread to terminate**. When it returns due to timeout, the target thread may still be running. If you need to know whether the worker is still alive, check `thread.isAlive()`, accepting that the state can change right after the check.

Anti-pattern example:

```java
worker.join(100);
System.out.println("Task finished successfully");
```

This is an illustrative snippet with a hypothetical `worker`. The print statement is unfounded: `join` may return due to timeout, and even if the thread terminated, that does not prove the work succeeded from a business perspective.

Proper way of thinking:

```java
worker.join(100);
if (worker.isAlive()) {
    // Caller waited long enough, but worker is still running.
    // Choose policy: keep waiting, request interrupt, or return timeout.
} else {
    // Worker has terminated; success/failure still needs a separate result channel.
}
```

This is an illustrative snippet, not a standalone program. If you want to report results and exceptions, `Future`/`CompletableFuture` is usually more suitable than reading fields manually after a timed join.

**Do not use `Thread.stop()`** as a "hard cancellation"; it does not preserve invariants and has been removed from safe Java programming practices.

## 23. `shutdown()`, `shutdownNow()`, and `awaitTermination`

When managing an `ExecutorService`, three methods have distinct roles:

- `shutdown()`: initiates an **orderly shutdown**, accepts no new tasks, and allows previously submitted tasks to continue per the executor contract.
- `shutdownNow()`: **attempts** to stop actively executing tasks (typically via interruption), halts processing of waiting tasks, and returns a list of tasks that never started per contract; does not guarantee every active task stops immediately.
- `awaitTermination(timeout, unit)`: **waits up to the limit** for the executor to reach the terminated state; returns `true` if terminated, `false` if timed out, and may throw `InterruptedException` if the caller thread is interrupted.

Example:

```java
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
}
```

This is an illustrative snippet where `pool` is an `ExecutorService`, inside a method that can propagate/handle `InterruptedException`.

Key point to understand: `awaitTermination(5s)` returning `false` **does not automatically trigger `shutdownNow`**; the code explicitly chose the `shutdownNow()` step afterward. This is an example of combining **timeout → cancellation attempt** as an **application policy**.

If the caller is interrupted during `awaitTermination`, an appropriate cleanup branch is needed—typically requesting `shutdownNow` when that layer owns the executor, then restoring the flag if it cannot propagate. Not every calling layer has the authority to shut down a shared executor.

## 24. Choosing a Policy When Wait Time Expires

There is no single right action for every timeout:

| Goal | Usually appropriate policy |
| --- | --- |
| Caller only wants a responsive UI | Return timeout/fallback; background task may continue if intentional |
| CPU-only computation no longer needed by anyone | Request cancellation; task checks token/interrupt at checkpoints |
| Task blocked reading a queue | Interrupt if API supports it; or close/sentinel/timeout per lifecycle protocol |
| Remote transaction may have committed | Return "outcome unknown", query status, and use idempotency instead of blind retry |
| Task has mutable data mid-commit | Do not abort mid-invariant; use atomic commit/rollback protocol |
| Task helps warm up a cache | May let it keep running after caller timeout, but bound resources and stale writes |
| Executor is shutting down | Wait within budget, then request `shutdownNow` if calling layer owns executor and policy permits |

Always determine **who owns cancellation rights**. A helper layer handling a single request's timeout does not necessarily have the right to cancel a shared task serving multiple other requests.

For example, when the same `CompletableFuture` is used by multiple callers: caller A timing out should not by default cancel the future if caller B still needs the result. Canceling a shared future can affect all subscribers; instead, each caller can maintain its own wait deadline.

## 25. Nested Timeouts, Retries, and the Risk of Load Amplification

A system with a 200 ms timeout that automatically retries three times in a row can consume 600 ms or more, plus queueing/network and cleanup time. If each retry also spawns a new task while the old task has not stopped, underlying load can **increase** even though the caller thinks it is bounding things with timeouts.

A safer policy should consider:

1. **Total deadline budget** for the entire workflow, without resetting indefinitely.
2. **Maximum retry count** and appropriate backoff intervals.
3. **Idempotency** of the operation (especially with I/O or side effects).
4. **Cancellation/cleanup** of old attempts when they are no longer needed.
5. **Backpressure** on the executor/queue and limits on in-flight tasks.
6. **Distinguishing transient errors from cancellation:** do not retry due to interruption if the policy requires stopping.
7. **Outcome unknown:** for remote side effects that may have committed, query status rather than sending another non-idempotent operation.

Timeout is not automatic backpressure. A caller returning quickly due to timeout can still leave many long-running tasks behind if lifecycle is not managed.

## 26. When Do You Need "canceled", "timed out", "failed" States?

A result API should usually distinguish:

- **SUCCEEDED:** has a valid result per contract.
- **FAILED:** task ran but encountered an error, with an exception/cause.
- **TIMED_OUT:** caller or operation did not receive a result in time; does not automatically conclude the task stopped.
- **CANCEL_REQUESTED:** stop has been requested; worker may not have processed it yet.
- **CANCELED / STOPPED:** a terminal state that must be **precisely defined**: does it mean only future canceled, or also cleanup done?
- **UNKNOWN / PENDING_RECONCILIATION:** external impact could not be determined after timeout.

For Java libraries, `Future` has its own state semantics. For business APIs, avoid borrowing the word `CANCELED` if you intend to promise the worker is no longer executing when the implementation merely calls `future.cancel(true)` and returns immediately.

Do not lump all `TimeoutException`, `InterruptedException`, `ExecutionException`, and `CancellationException` into a single "task failed" branch if callers need different policies.

## 27. Common Mistakes

**1. "`Future.get(timeout)` throwing `TimeoutException` means the task was canceled."** False. That is only a timeout of the wait; the task may still be running.

**2. "`cancel(true)` returning `true` means the worker has stopped."** False. It may only report that the cancel request was accepted and the future transitioned state; the worker needs to cooperate.

**3. "`cancel(false)` is safe because it doesn't touch the task."** You should not assume that. It can transition the future to canceled while the task keeps running and side effects still occur; a clear contract is needed.

**4. "`CompletableFuture.orTimeout` interrupts the background task."** There is no such guarantee. It completes the future exceptionally; the underlying computation may continue.

**5. "`CompletableFuture.cancel(true)` works like `FutureTask.cancel(true)`."** False. `CompletableFuture` does not use the `mayInterruptIfRunning` parameter to control underlying processing.

**6. "Every timeout throws `TimeoutException`."** False. `poll` returns `null`, `tryLock` returns `false`, `awaitTermination` returns a `boolean`, and socket reads have their own exception.

**7. "The task timed out, so the server definitely hasn't processed it."** False. Remote side effects may have already committed while the response arrived late.

**8. "`Thread.interrupt()` always stops network I/O immediately."** No; you must read the contract of the specific channel/socket/client.

**9. "Letting every retry use the same timeout as the first attempt still meets the overall SLA."** False; you must compute the remaining budget from a shared deadline.

**10. "Once a task is canceled, cleanup can be skipped."** False; invariants must be preserved and resources released according to policy.

**11. "A cancellation flag automatically wakes up a blocked thread."** False. A token must be combined with signaling/timeout/interruption or closing.

**12. "`Future.isDone()` being true means the task succeeded."** False. Done includes normal completion, exceptional completion, or cancellation depending on the future.

**13. "`Thread.join(timeout)` returning means the worker is dead."** False. You must check `isAlive` if needed.

**14. "One request timing out allows canceling a shared future for all callers."** False if the task is serving others; ownership and reference/lifecycle management are required.

**15. "A timeout ends a network transaction."** No. Transactions, idempotency, and outcome reconciliation must be designed separately.

## 28. How to Test Timeout and Cancellation Reliably

Do not test by gambling on `Thread.sleep(100)` and assuming the worker is ready. Use **CountDownLatch** or coordination primitives to create deterministic milestones:

- To test `get` timeout, hold the task from completing with an unopened latch; after the timeout, verify the future is still incomplete, then open the latch and retrieve the result.
- To test cancellation, have the worker signal that it has entered the wait region, call `cancel(true)`, and then observe that the worker itself received the interrupt and emitted a separate completion signal.
- To test queue timeout, ensure the queue is definitely empty during the first poll, then insert an item to prove the queue remains usable.
- To test lock timeout, hold the lock in a holder controlled by a latch, then attempt `tryLock` from `main`; only open the latch after the first attempt finishes.
- To test late completion, use a version/generation token to ensure results from an old attempt do not overwrite a new attempt.

In test automation, you can add a **test harness timeout** to prevent hangs when code is buggy; however, a test timeout does not automatically provide cancellation/cleanup for stuck tasks. Use `finally` to release latches, close resources, shut down executors, or interrupt workers according to ownership, with a reasonable cleanup duration.

**Stress tests do not prove absolute correctness**; what matters are API contracts, happens-before relationships, state transitions, and proper invariants.

## 29. API Selection Checklist

Before writing `timeout` or `cancel`, answer:

1. **What needs to expire?** A caller's wait, a blocking operation, or an entire workflow?
2. **Upon expiration, may the task continue running?** If so, why and who still needs the result?
3. **Who has the authority to cancel?** Does the current caller own the task, executor, or shared future?
4. **How does the task receive the request?** Interruption, cancellation token, closing a resource, sentinel, or a specific API?
5. **Does the task have checkpoints and cleanup?** Can it continue causing side effects after a cancellation request?
6. **Does the future state reflect the worker lifecycle?** Do not confuse `isCancelled` with resources being released.
7. **Are there remote side effects?** A timeout can lead to an unknown outcome; is idempotency / status querying needed?
8. **Are there multiple steps or retries?** Pass the remaining deadline instead of resetting the budget at each step.
9. **How should the result be reported?** Return value, `TimeoutException`, `CancellationException`, custom outcome, or future?
10. **Is there a completion-vs-cancel race?** Do you need to accept valid states and atomic transitions?
11. **Can interruption be lost?** Catching `InterruptedException` requires propagating, or restoring and exiting when unable to throw.
12. **Is there blocking I/O that does not support interruption?** A separate timeout/close/cancellation policy is needed.
13. **Is bounded concurrency guaranteed?** Timeouts do not replace queue capacity, semaphores, or in-flight limits.
14. **How will you test it?** Establish conditions with latches, verify cleanup and late completion rather than guessing timing.

## 30. Self-Check Questions

**Q1.** `Future.get(100, MILLISECONDS)` throws `TimeoutException`. Is the task definitely canceled?

**No.** Only the caller's wait timed out. The task may still be running, not yet started, or complete later. If you want to request stopping, a separate cancellation policy and operation are needed.

**Q2.** `Future.cancel(true)` returns `true`. Can you report "worker finished cleanup" to the user?

**Not by default.** The future may be canceled while the worker still needs to receive the interrupt and clean up. If you need a guarantee that cleanup finished, there must be a separate completion signal/contract.

**Q3.** If `BlockingQueue.poll(timeout)` returns `null`, has the producer been canceled?

**No.** It only means the poll did not receive an item in time. The queue and other producers may still be active.

**Q4.** How does `CompletableFuture.orTimeout` differ from `Future.get(timeout)`?

`orTimeout` can **complete the CompletableFuture itself exceptionally** after the deadline if not yet completed; `get(timeout)` only causes the caller's wait to end with `TimeoutException`. Neither API automatically proves the underlying task has stopped.

**Q5.** Why should `CompletableFuture.cancel(true)` not be used as a promise to interrupt the worker?

Because `CompletableFuture` does not use the `mayInterruptIfRunning` parameter to control the underlying computation per its contract. To cancel the worker, proper signaling and execution task management are needed.

**Q6.** If an HTTP request times out, should you immediately retry with a new request?

Only if the operation's semantics allow it. The server may have already committed side effects; an idempotency key or status query/reconciliation is needed to avoid duplicate execution.

**Q7.** Do three steps each with a 100 ms timeout guarantee the workflow completes within 100 ms?

**No.** Total wait time can approach 300 ms plus overhead. If the SLA is 100 ms overall, a shared deadline and remaining budget must be used.

**Q8.** Does `awaitTermination(5s)` returning `false` automatically call `shutdownNow()`?

**No.** It only returns the wait result. The caller must actively choose an escalation policy, and only do so when it owns the executor.

**Q9.** Is `Thread.interrupt()` a cancellation with an immediate-stop guarantee?

**No.** It is a cooperative request; the worker can respond at interruptible blocking calls or checkpoints. Some I/O and side effects cannot stop immediately.

**Q10.** If caller A times out while caller B is still waiting on the same shared future, should A always `cancel` that future?

**No.** A can simply stop waiting; canceling the shared task will affect B. Cancellation authority must be based on ownership and the system's contract.

## 31. Summary

- **Timeout** is primarily a time limit on **waiting** or a deadline for an operation. It is **not synonymous** with the running task having stopped.
- **Cancellation** is a **request to cancel work**; even `cancel(true)` does not force a worker to finish cleanup or roll back side effects.
- `Future.get(timeout)` only times out the **caller wait**; `CompletableFuture.orTimeout` and `completeOnTimeout` can complete the **future state**; `ExecutorService.invokeAll(timeout)` has a policy to cancel unfinished tasks. **Read the exact API contract.**
- `BlockingQueue.poll(timeout)`, `Lock.tryLock(timeout)`, `awaitTermination(timeout)`, and `Thread.join(timeout)` have different timeout semantics and do not automatically cancel other workers.
- Use a **shared deadline** across multiple steps/retries, pass the **remaining budget**, and manage **backpressure** to prevent long-running tasks from piling up after timeouts.
- When timeouts involve I/O or external side effects, the outcome may be **unknown**; use idempotency, status queries, and late-result handling rules as needed.
- A correct system clearly separates **caller stopped waiting**, **cancel requested**, **worker observed cancel**, and **cleanup completed**.

The question to ask when encountering a timeout is: **"Who timed out — the waiter or the running work? If I want to stop the work, which API guarantees that, under what protocol, and when is cleanup truly complete?"**. Answering these questions prevents most confusion between timeout and cancellation in Java concurrency.
