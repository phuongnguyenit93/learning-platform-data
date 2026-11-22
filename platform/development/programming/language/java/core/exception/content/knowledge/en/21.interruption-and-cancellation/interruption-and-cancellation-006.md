# Stopping Processing and Cleanup After Receiving an Interrupt Signal

In Java, an **interrupt** is a cooperative signal to request that a thread stop or change the work it is doing. It is not a forced command to kill a thread, it does not automatically roll back transactions, and it does not automatically close all resources. When code receives an interrupt signal, its responsibilities typically include **stopping accepting or performing work according to policy**, **cleaning up the resources it owns**, **preserving state and interrupt information**, and **terminating or propagating the signal to the orchestration layer**.

This is an important part of exception design: `InterruptedException` can cause control flow to exit a blocking operation at any time. A program that only handles the success path without cleaning up on the interruption path can leak streams/connections, hold onto locks or registrations, leave state updates half-done, or prevent the application from shutting down properly.

This article focuses on Java 17+ with threads, tasks in executors, and blocking APIs. The exact way to stop depends on each library's contract; no single `catch (InterruptedException)` statement solves every scenario.

## 1. Understand the Interrupt Signal Before Cleanup

Every `Thread` has an **interrupted status** (interrupt flag). Another thread can call `worker.interrupt()` to ask it to take note of cancellation/stopping. When that happens:

- If the worker is running normal computational code, Java **does not automatically throw `InterruptedException` at every statement**. The worker must actively check its status or enter an interruptible operation.
- If the worker is waiting on an interruptible API such as `Thread.sleep`, `Object.wait`, `Thread.join`, `BlockingQueue.take`, `CountDownLatch.await`, `Future.get`, or `Lock.lockInterruptibly`, the operation can exit with `InterruptedException`.
- When these common waiting methods throw `InterruptedException` due to an interrupt, the thread's interrupt status has usually been **cleared** according to the API contract. If higher layers still need to know about the interrupt request, you must propagate the checked exception or **restore the flag** when translating it into another form.
- For I/O or library operations that do not guarantee responsiveness to interrupts, `interrupt()` might not make the worker stop immediately. You need to consider timeouts, `close()`, a dedicated cancellation API, or that library's cooperative stopping mechanism.

Calling `Thread.interrupt()` from another thread only sends a request. The authority and obligation to handle the request lie with the **code currently executing and managing the lifecycle** of the worker. Upon receiving an interrupt, the worker can exit its loop, clean up, and terminate; or a specific API may choose to continue if interruption is documented as not applicable there.

### Three Operations on the Interrupt Flag

| API | Effect | Notes |
| --- | --- | --- |
| `thread.interrupt()` | Sets/requests the target thread's interrupted status, which may wake an interruptible wait with an exception | Does not guarantee the thread stops immediately. |
| `thread.isInterrupted()` | Reads the target thread's flag, **without clearing it** | Use to check in a cooperative loop. |
| `Thread.interrupted()` | Reads **and clears** the **current** thread's flag | Do not use as a harmless check if subsequent code still needs the signal. |

`Thread.currentThread().interrupt()` is commonly used inside `catch (InterruptedException ex)` to **restore the current thread's own flag** when you cannot propagate the checked exception.

## 2. Interrupt Signals and Exceptions Occur in Different Places

Consider a worker waiting for jobs:

```java
while (!Thread.currentThread().isInterrupted()) {
    Job job = queue.take();
    process(job);
}
```

This is an **illustrative** snippet assuming `Job`, `queue`, and `process` are already defined. `queue.take()` can throw `InterruptedException`, so this snippet is not complete enough to compile on its own. Even though the `while` condition checks the interrupt flag, an interrupt request can still arrive **while `take()` is waiting**. Therefore, the loop must handle the exception path:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Exit the loop to clean up owned resources.
} finally {
    releaseOwnedResources();
}
```

This is also an **illustrative fragment**, not a standalone Java program. `releaseOwnedResources()` needs its own contract regarding exceptions and ownership.

If `process(job)` has side effects and cannot be safely stopped mid-way, policy may require completing the current unit of work before stopping taking the next job. Do not arbitrarily inject an `interrupt` in the middle of an operation that requires consistency without a rollback/idempotency design.

## 3. Handling Workflow When Receiving an Interrupt

A cooperative processing flow typically performs the following steps:

1. **Detect the signal** via `InterruptedException` or checking `isInterrupted()`; identify the error type accurately so it is not confused with a business exception.
2. **Transition to a stopping state** if the worker has a lifecycle (for example, stop taking new jobs, notify the coordinator); avoid continuing the loop indefinitely.
3. **Stop or complete in-progress work** according to the contract. If the task has a commit point, ensure no unintended partial writes occur.
4. **Clean up owned resources** in `finally`/`try-with-resources`: close owned streams/connections, release permits, unlock the right locks, unsubscribe listeners, close registration handles, etc.
5. **Preserve information**: propagate `InterruptedException` if the signature allows, or restore the interrupt flag when translating/exiting.
6. **Report shutdown completion** to the owner if needed: via a latch, lifecycle state, or completion stage. This is different from reporting "cancel request sent."

These steps are logical responsibilities, not necessarily a rigid order for every API. In particular, **when to restore the interrupt flag relative to blocking cleanup** must be considered as discussed in section 7.

Do not use `Thread.stop()` to force a thread to stop: this legacy API is unsafe because it can break invariants and release monitors while state is partially updated.

## 4. Try-with-resources: Cleanup Even When Await Is Interrupted

A worker's resources should be closed using a construct that guarantees cleanup on both the normal exit path and the exception path.

With `AutoCloseable`:

```java
try (InputStream input = Files.newInputStream(path)) {
    consume(input);
}
```

This is an illustrative snippet assuming `path` and `consume` exist and `consume` has compatible exception types. The `InputStream` opened by this scope is closed when the `try` block exits, including when the body throws an exception. However, placing a resource in `try-with-resources` means **that scope will call `close()` on it**: only do this when you have ownership.

When the body throws `InterruptedException`:

```java
try (OwnedResource resource = openOwnedResource()) {
    awaitInterruptibly();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // resource.close() has already run before entering this catch block.
}
```

This is **non-standalone illustrative code**, with hypothetical `OwnedResource`, `openOwnedResource`, and `awaitInterruptibly`. Placing `catch` **outside** the try-with-resources block has an advantage: the resource-closing sequence of the `try` block runs before catching and restoring the interrupt. If `close()` needs to perform an interruptible cleanup step, it will not be inadvertently disrupted right away by the newly restored interrupt flag.

If `close()` itself throws an exception, you must account for both the primary exception and suppressed exceptions. Do not assume cleanup certainly succeeded just because `close()` was called.

### Closing According to Ownership

A parser that receives an `InputStream` passed by a caller might only **borrow** the stream. When interrupted, the parser should not close the caller's stream if the contract does not transfer ownership. The caller may have an outer `try-with-resources` responsible for closing it.

Similarly, a request using a shared `HttpClient` or shared database connection pool must not arbitrarily close the application's entire client/pool when the request is cancelled. Only release handles/resources **owned by that request**, per the API contract.

## 5. Standalone Java 17 Example: Stopping a Worker and Cleaning Up Before Exit

This example uses `CountDownLatch` to control ordering between main and the worker, avoiding relying on `Thread.sleep` to hope the worker has started. The worker opens its own resource, waits on a latch that is never released, and then receives an interrupt from main. When `await()` throws `InterruptedException`, try-with-resources closes the resource, `catch` restores the interrupt flag, and finally the worker exits.

Create `InterruptCleanupDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptCleanupDemo {

    private static final class OwnedResource implements AutoCloseable {
        private final List<String> events;
        private boolean closed;

        OwnedResource(List<String> events) {
            this.events = events;
            events.add("resource: opened");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                events.add("resource: closed");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch enteredWait = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean flagRestored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try (OwnedResource resource = new OwnedResource(events)) {
                events.add("task: waiting");
                enteredWait.countDown();
                neverReleased.await();
                events.add("task: completed"); // Does not run in this example.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                flagRestored.set(Thread.currentThread().isInterrupted());
                events.add("task: interrupted");
            } finally {
                events.add("task: finished");
            }
        }, "resource-owner");

        worker.start();
        enteredWait.await();
        worker.interrupt();
        worker.join();

        events.forEach(System.out::println);
        System.out.println("main: flag restored = " + flagRestored.get());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 InterruptCleanupDemo.java
java InterruptCleanupDemo
```

Stdout:

```text
resource: opened
task: waiting
resource: closed
task: interrupted
task: finished
main: flag restored = true
```

Behavior explanation:

- `enteredWait.countDown()` only signals that the worker has created the resource and reached the wait region. Main may call `interrupt()` right before or during `neverReleased.await()`; both cases result in `InterruptedException` at `await()` per the latch contract.
- Java exits the try-with-resources block and calls `OwnedResource.close()` **before** entering the outer `catch`. The `resource: closed` line therefore precedes `task: interrupted`.
- `catch` calls `Thread.currentThread().interrupt()` to preserve the cancellation request for outer code in the same worker (if any), then records that the interrupt status was restored. `finally` records lifecycle exit.
- Main calls `join()` to wait for the worker to finish before printing the full log. `CopyOnWriteArrayList` ensures safe data sharing between the two threads; because the worker is the sole writer of the event entries, ordering is preserved.
- `task: completed` does not appear because the latch is never released. That indicates the worker **stopped due to interruption**, rather than completing the task normally.
- `OwnedResource.close()` in this example is non-blocking and does not throw checked exceptions. In real applications, cleanup can fail or take time; a dedicated policy is needed.

The example uses `throws InterruptedException` in `main` because main itself performs interruptible `await()/join()` operations. This is an error that can occur on the **main thread**, separate from the exception the worker just received.

## 6. Why Should You Not Swallow InterruptedException?

A common mistake:

```java
try {
    queue.take();
} catch (InterruptedException ex) {
    // Ignore and continue working.
}
```

This is an illustrative snippet with a hypothetical `queue`. After `take()` throws `InterruptedException`, the interrupt flag may have been cleared. If you neither propagate it, restore it, nor exit the work, callers or the shutdown coordinator can **lose the cancellation signal**, causing the worker to keep taking jobs and preventing the system from stopping properly.

Common handling approaches:

**Propagate the checked exception** when the API allows:

```java
public static String waitForMessage(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

This method can be placed in a class with `import java.util.concurrent.BlockingQueue`. The decision to stop and clean up is delegated to a caller with higher-level lifecycle context.

**Restore the flag and exit** when inside `Runnable.run()` (which cannot declare checked exceptions):

```java
try {
    waitForMessage(queue);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return; // Enclosing finally/try-with-resources still performs cleanup.
}
```

This illustrative fragment assumes `queue` and `waitForMessage` exist. Returning from `run()` cannot bypass `finally` blocks of active scopes, but resources must be declared in `try-with-resources` or structured cleanup.

**Translate into an API exception while preserving the interrupt**:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException("Processing interrupted", ex);
}
```

`OperationInterruptedException` and `blockingOperation` are hypothetical application components. When translating, preserve `cause` for diagnostics; do not turn an interrupt signal into `IllegalArgumentException` or "invalid input."

Some frameworks/callers **directly expect checked `InterruptedException`**. If you can propagate it, there is no need to wrap it just to "standardize" exceptions.

## 7. Blocking Cleanup: Time Flag Restoration Properly

Restoring the interrupt early is usually right after catching `InterruptedException`, but watch out if subsequent cleanup performs operations that **also react to interrupts**.

Risk example:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} finally {
    // If cleanup uses an interruptible method, the flag is already set.
    waitForCleanupAcknowledgement();
}
```

This is an illustrative snippet; `waitForCleanupAcknowledgement` might throw an exception or observe the interrupt flag. If waiting for cleanup uses `CountDownLatch.await()`, the already-restored interrupt flag can cause `await()` to immediately throw `InterruptedException` instead of waiting for cleanup to run. If cleanup is mandatory to preserve state, this order can be wrong.

One approach is to organize cleanup into an **inner try-with-resources** with `catch` outside, as in the full example in section 5. Another approach is to keep the interrupt request in a local variable when you need to run bounded blocking cleanup, then restore the flag after cleanup:

```java
boolean interrupted = false;
try {
    blockingOperation();
} catch (InterruptedException ex) {
    interrupted = true;
} finally {
    try {
        cleanupWithinDeadline();
    } catch (InterruptedException duringCleanup) {
        interrupted = true;
        // Record that cleanup was interrupted; inspect remaining state.
    } finally {
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

This is an **illustrative** snippet, with `blockingOperation` and `cleanupWithinDeadline` undefined. The `interrupted` variable only records the signal; whether not rethrowing the exception is appropriate depends on the enclosing method's contract. `cleanupWithinDeadline` must genuinely have a clear wait/cancellation bound; do not wait indefinitely during shutdown.

**Do not arbitrarily call `Thread.interrupted()` to clear the flag** just to force cleanup to run without saving and restoring the state. If you use an intentional clearing mechanism, you must understand who owns the cancellation signal and avoid causing callers to lose the stop request.

Also note: if cleanup throws `IOException`, `RuntimeException`, or another exception, the `finally` block can affect the earlier exception. You must check the contract and use error-preserving structures (section 9), not just restore the interrupt flag.

## 8. Stopping a Loop While Preserving State Invariants

A job-processing loop should have a **safe boundary** for stopping:

```java
while (!Thread.currentThread().isInterrupted()) {
    Job job = acquireNextJob();
    processOneJob(job);
}
```

This is an illustrative fragment missing definitions for `Job`, `acquireNextJob`, and `processOneJob`. `acquireNextJob` may be interruptible; you need catch/cleanup for the exception. Even without an exception, the interrupt flag can be set **after the `while` condition**. If stopping is required right before taking a new job, you may need an additional check at the appropriate boundary.

For stateful tasks:

- Before starting a new job, check the stop signal and do not accept more work.
- While processing an atomic unit, choose to roll back, complete up to a safe checkpoint, or record resumable state.
- In `finally`, clean up only resources that were actually acquired. Do not clean up a resource that was not successfully created or is owned by another component.
- After cleanup, report **stopped/cancelled** distinctly from **completed successfully**, if the API allows callers to distinguish them.

If using a lock, note:

```java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This snippet is illustrative with hypothetical `lock` and `updateSharedState`. `lock.lockInterruptibly()` is placed **before** `try` because it can throw `InterruptedException` without having acquired the lock. Only call `unlock()` when acquisition succeeded. Wrapping `lockInterruptibly()` inside `try` and always calling `unlock()` in `finally` can cause `IllegalMonitorStateException` if interrupted before acquiring the lock.

Preserving state does not mean every interrupt rolls back automatically. If a network request was already sent or data was already written, interrupting the wait does not prove the remote service has not processed the request. For operations with side effects, you need idempotency, transactions, or a separate reconciliation step.

## 9. What If Both Interruption and a Close Failure Occur?

A blocking operation can throw `InterruptedException` at the same time resource `close()` also fails. With try-with-resources:

- The exception from the `try` body is the **primary** exception.
- The exception from `close()` is attached as a **suppressed exception**.
- Callers can access it via `Throwable.getSuppressed()`.
- If the body completes normally but `close()` throws an exception, the close exception becomes the primary exception.

Standalone Java 17 example intentionally throwing an exception in `close()`:

Create `InterruptedAndCloseFailureDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;

public class InterruptedAndCloseFailureDemo {

    private static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try (FailingClose resource = new FailingClose()) {
                entered.countDown();
                neverReleased.await();
            } catch (InterruptedException ex) {
                System.out.println("primary: " + ex.getClass().getSimpleName());
                System.out.println(
                    "suppressed: " + ex.getSuppressed().length
                );
                System.out.println(
                    "cleanup: " + ex.getSuppressed()[0].getMessage()
                );
                Thread.currentThread().interrupt();
            } catch (IOException ex) {
                System.out.println("close-only: " + ex.getMessage());
            }
        }, "close-failure-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();
    }
}
```

Commands:

```bash
javac -encoding UTF-8 InterruptedAndCloseFailureDemo.java
java InterruptedAndCloseFailureDemo
```

Stdout:

```text
primary: InterruptedException
suppressed: 1
cleanup: close failed
```

Because `neverReleased` is never opened, the worker exits `await()` via `InterruptedException` after main calls `interrupt()`. `FailingClose.close()` then throws `IOException("close failed")`. Try-with-resources preserves `InterruptedException` as the primary exception, while `IOException` becomes a suppressed exception.

Not every exception on close is harmless. For example, with a buffered output stream, an error during `flush/close` may indicate data was not actually written. You must record and evaluate cleanup consequences, not just call `close()` and assume release succeeded.

In logging, retain the primary, cause, and suppressed exceptions if they are diagnostically meaningful. Avoid printing messages containing sensitive information to end clients if underlying errors include internal paths, tokens, or private data.

## 10. Future.cancel(true): Cancellation Signal vs. Cleanup Completion Time

In `ExecutorService`, callers typically receive a `Future`. If the caller calls `future.cancel(true)`, the implementation may request an interrupt on the worker executing the task. However, **`Future.isCancelled() == true` does not prove that `finally` in the task has finished running**.

These are two distinct milestones:

1. **Cancellation request/status:** The Future is marked cancelled; the caller will no longer receive a normal result via `get()`.
2. **Task stopped and cleanup completed:** The worker has actually traversed its stop branches, closed resources, and exited.

If the caller needs to wait for cleanup, there must be a separate completion/acknowledgement waiting mechanism, or a higher-level abstraction whose contract guarantees it. Calling `Future.get()` after the Future is cancelled throws `CancellationException`; it does not replace waiting for a "cleanup done" signal from the task.

### Complete Java 17 Example: Cancel and Wait for Cleanup

Create `CancelAndCleanupDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CancelAndCleanupDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                try {
                    events.add("task: started");
                    started.countDown();
                    neverReleased.await();
                    events.add("task: completed");
                } catch (InterruptedException ex) {
                    events.add("task: interrupt received");
                    Thread.currentThread().interrupt();
                } finally {
                    events.add("task: cleanup");
                    cleaned.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            // Wait for the task to confirm it has passed through finally;
            // checking isCancelled() alone is not enough.
            cleaned.await();

            events.forEach(System.out::println);
            System.out.println("cancel accepted: " + accepted);
            System.out.println("future cancelled: " + future.isCancelled());
            System.out.println("cleanup confirmed: true");
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CancelAndCleanupDemo.java
java CancelAndCleanupDemo
```

Stdout:

```text
task: started
task: interrupt received
task: cleanup
cancel accepted: true
future cancelled: true
cleanup confirmed: true
```

Why is the output deterministic?

- `started.await()` ensures the worker has started running before main requests cancellation.
- The worker is just before/waiting on `neverReleased.await()`. `cancel(true)` on a `FutureTask` created by a standard executor requests an interrupt on the thread executing the task.
- `CountDownLatch.await()` responds to the interrupt with `InterruptedException`; the worker logs it, restores the flag, and enters `finally`.
- `cleaned.countDown()` is the signal confirming **this example's** cleanup has run. Main waits on `cleaned.await()` before printing results; thus it can independently verify both the Future status and cleanup status.
- `neverReleased` is never released, so there is no `task: completed` line.
- `shutdownNow()` in `finally` requests executor shutdown when exiting the demo; on the success path, the task has already cleaned up beforehand.

**Limitation to remember:** a real task using I/O or a library that does not respond to interrupts might never reach `cleaned.countDown()`; waiting indefinitely is inappropriate for many production shutdown paths. Real designs should use a deadline for waiting on cleanup along with appropriate monitoring/escalation. This example only uses the JDK's interruptible latch, so it has a well-defined stop path.

`CompletableFuture.cancel(true)` has different semantics from `FutureTask`: `mayInterruptIfRunning` is not used to control interruption of a background task in the manner above. Do not mechanically apply a `FutureTask` example to every `Future` implementation.

## 11. Cleanup Does Not Guarantee Rollback

Another source of confusion: "Caught the interrupt and finished closing" does not mean business state was restored to how it was before the task.

| Action needed | Goal | Example |
| --- | --- | --- |
| Stop accepting work | Avoid creating more side effects after a stop request | Stop polling the queue, reject new request registrations. |
| Clean up resources | Avoid holding onto owner resources/registrations | `close` owned streams, `removeListener`, release permits. |
| Preserve invariants | Objects are not left half-initialized or half-closed | Set explicit `STOPPING`/`STOPPED` state, synchronize updates. |
| Rollback/compensation | Undo or compensate for business changes already made | Transaction rollback, delete temp data, compensating action. |
| Report outcome | Callers know cancelled differs from failed and completed | Future/callback/event/job status. |

For a task sending a payment, an interrupt while waiting for an HTTP response **does not prove** the server has not processed the payment. Do not blindly retry or perform a fake rollback without idempotency info or the ability to check status.

For file writes, `close()` may flush data already pushed to a buffer, but it does not revert the write to its initial state. If atomic file updates are needed, you can write to a temporary file, flush/sync appropriately, and perform an atomic swap supported by the filesystem; this decision belongs to consistency design, not something interruption provides automatically.

## 12. Clean Up in the Right Order and Do Not Close Others' Resources

A worker may simultaneously hold:
- A file stream it opened itself.
- A semaphore permit it successfully acquired.
- A connection checked out from a pool.
- A listener registration handle it created.
- A reference to a shared executor or shared HTTP client.

On the interruption path:

1. Clean up resources within the worker's scope in an order consistent with dependencies. Try-with-resources closes multiple resources in **reverse declaration order**.
2. Only release a permit/lock after **successful acquisition**. For example, `Semaphore.acquire()` can throw `InterruptedException` before obtaining a permit; an unconditional `finally { semaphore.release(); }` will corrupt the permit count.
3. Only `unlock()` when the thread actually holds the lock. With `lock.lockInterruptibly()`, an interrupt before acquisition does not permit calling `unlock()`.
4. Only cancel subscriptions owned by the worker. Cancelling a shared registration can cause other subscribers to miss events.
5. Do not shut down a shared executor/pool just because one request/caller was interrupted, unless that worker truly manages the shared component's lifecycle.

Illustrative example handling a permit:

```java
boolean acquired = false;
try {
    semaphore.acquire();
    acquired = true;
    doWork();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
```

This is a non-standalone snippet; `semaphore` and `doWork` are assumed to be declared, and the method must handle/declare `InterruptedException`. The `acquired` variable ensures we do not release an unowned permit if interrupted while waiting in `acquire()`.

With `Lock`:

```java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This snippet illustrates that `unlock()` is only guarded after the successful acquisition point, not called blindly when `lockInterruptibly()` is interrupted before acquiring the lock.

## 13. Partial Initialization and Multiple Cleanup Operations

If initialization acquires A, then B, and then gets interrupted before acquiring C, only A/B need cleanup. A common mistake is writing resource creation code outside `try` and only cleaning up when all creation steps succeed.

With `AutoCloseable`, the construct:

```java
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    runInterruptibleOperation(second);
}
```

is an illustrative snippet. If `openSecond` throws an exception or receives an interrupt, Java closes `first` which was already created. If both are created, Java closes `second` then `first` on exit.

However, if `openSecond` **creates a partial internal resource and throws before returning the object**, the caller has not received an object to close. The implementation of `openSecond` itself must clean up any internal resources it acquired.

The same applies to multiple registrations/listeners: store each handle as soon as subscribing succeeds; if a subsequent subscription fails, cancel the handles already created. When interrupted, cleanup must not miss registrations that succeeded earlier.

If cleaning up multiple resources manually, do not let an error from resource A prevent closing an independent resource B; use try-with-resources where appropriate or an error-collecting cleanup structure so remaining resources are still closed.

## 14. Interrupts in ExecutorService.shutdown and awaitTermination

An executor owner typically follows these steps:
- Stop accepting new jobs via `shutdown()`.
- Wait for running jobs to finish via `awaitTermination(timeout, unit)`.
- If the timeout expires and policy allows, request cancellation of remaining work via `shutdownNow()` or cancel handles.
- Ensure tasks clean up themselves and record which jobs completed/did not complete.

`shutdown()` **does not wait** for tasks to finish; `shutdownNow()` is an attempt to stop running tasks via interruption and returns the list of unstarted jobs, without guaranteeing that tasks have stopped. `awaitTermination(...)` can throw `InterruptedException` if the **shutdown-coordinating thread** is interrupted while waiting. That does not mean all workers failed.

The following pattern is an **illustrative fragment** for a component that genuinely owns an executor:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Here the owner chooses a policy: if the shutdown coordinator is interrupted, tell workers to stop and restore the coordinator's own interrupt flag. Do not copy this policy into code that only **borrows** a framework-managed executor.

Task resources must still be cleaned up close to the task. The executor owner can monitor/enforce deadlines, but should not rely on `shutdownNow()` as proof that every `finally` block has executed. For critical work, you need a channel confirming the task has actually stopped or a shutdown mechanism with a timeout and unresponsiveness handling.

## 15. When an Interrupt Arrives While Cleanup Itself Is Running

Cleanup may include closing sockets, flushing buffers, waiting for callbacks to stop, stopping producers, or returning connections. Some blocking operations may receive another interrupt. Policy must answer:

- Which minimum cleanup **must attempt to complete** so resources do not leak or invariants are not left broken?
- Which cleanup can be skipped or performed asynchronously after a stop request?
- Is there a deadline? If cleanup still does not finish, who receives the alert/escalation?
- Do both the primary work exception and the cleanup exception need to be preserved?
- After a cleanup failure, should the component be `FAILED` or `STOPPED_WITH_ERRORS` instead of claiming a clean stop?

Do not use this loop:

```java
while (true) {
    try {
        waitUntilClean();
        break;
    } catch (InterruptedException ignored) {
        // Ignore indefinitely.
    }
}
```

This snippet illustrates an **anti-pattern**: it can wait forever, mask shutdown signals, and cause deadlocks when another component waits for the thread to exit. If cleanup must wait, use a deadline/bound, preserve interrupt info, and provide a meaningful exit path.

There is no guarantee the JVM always runs `finally` in every situation: the process can be forcefully killed, the JVM can crash, or OS-level resources can be lost. Software requiring high durability needs additional restart recovery, transactions, or bounded leases.

## 16. Distinguishing Worker Interruption from Caller Interruption

For `ExecutorService.submit`, a worker can throw `InterruptedException` out of `Callable.call()`; the task completes exceptionally and `Future.get()` on the caller receives **`ExecutionException` with `InterruptedException` as its cause**. The caller does not automatically become interrupted because of that.

Conversely, if the **caller** is interrupted while waiting on `future.get()`, it receives `InterruptedException` directly. The task may continue running normally.

| Where the interrupt occurs | How it is observed | Cleanup obligation |
| --- | --- | --- |
| Worker interrupted while processing | Worker catches/propagates exception, or Future holds failure | Worker cleans up resources owned by the worker. |
| Caller interrupted during `Future.get()` | `InterruptedException` at caller | Caller cleans up resources owned by the caller; may decide to cancel the task if it is the owner. |
| `get(timeout)` merely times out | `TimeoutException` at waiter | Does not automatically force worker cleanup; policy can keep waiting or request cancel. |
| `Future.cancel(true)` is accepted | Future has cancelled state, worker may be interrupted | Worker must still cooperate and clean up; caller needing cleanup completion needs a separate mechanism. |

Do not call `Thread.currentThread().interrupt()` on the caller **just because** `ExecutionException.getCause() instanceof InterruptedException`. The interrupt status belongs to the **current thread**, not a "global variable representing task failure."

## 17. Checklist for Testing Interruption and Cleanup

Tests should use `CountDownLatch` to control state rather than just calling `Thread.sleep(10)` and hoping the worker is waiting.

| Scenario | What to verify |
| --- | --- |
| Thread interrupted before entering a blocking operation | The blocking API observes the interrupt flag and the worker still runs cleanup properly. |
| Thread interrupted during `await/take/sleep` | `InterruptedException` is handled, and the worker stops per contract. |
| Resource opened successfully before interruption | `close()` on the owner's resource is called. |
| Interrupt during second acquisition | The first opened resource is closed; unacquired resources are not erroneously released. |
| Cleanup also throws an exception | Both primary and suppressed exceptions are preserved for diagnostics. |
| Task owns a permit/lock | Only released/unlocked when acquisition succeeded. |
| `Future.cancel(true)` returns a result | Do not confuse Future cancelled with task cleanup complete. |
| Caller waiting on `get()` is interrupted | Verify the caller itself can propagate/restore the flag; the task is not automatically marked failed. |
| Task processes data with side effects | Invariants, transactions/compensation, and idempotency satisfy the contract. |
| Cleanup does not respond to interrupts | The system has deadlines, metrics, and an escalation policy, rather than hanging indefinitely by accident. |

Tests should assert **observable state**: resource closed, subscription removed, no leaked permits, worker accepts no new jobs, acknowledgement emitted. There is no need to match exact stack traces or rely on coincidental timing if the contract does not promise that order.

## 18. Common Mistakes and How to Fix Them

**Swallowing `InterruptedException` and continuing the loop.** The flag may have been cleared and the interrupt signal lost. Propagate it, or restore the flag and exit intentionally.

**Calling `Thread.interrupted()` just to check, accidentally clearing the flag.** Use `isInterrupted()` when you only need to read; only clear when there is a reason and preserve/restore the signal if the contract requires it.

**Restoring the flag before blocking cleanup without considering the consequences.** Wait calls in cleanup may immediately receive an interrupt. Structure cleanup before the catch outside try-with-resources, or defer restoration in a controlled way and restore it at the right time.

**Putting `close()` only at the end of the happy path.** Exceptions or early `return`s bypass cleanup. Use try-with-resources or structured `finally`.

**Closing borrowed resources.** Ownership is not determined by variable names; do not close a caller's shared pool/client/stream outside the contract.

**Releasing a permit or unlocking when acquisition did not succeed.** If `Semaphore.acquire` or `Lock.lockInterruptibly` is interrupted before acquisition, unconditional release/unlock corrupts state.

**Treating successful cancel as cleanup completion.** `cancel(true)` only requests/marks cancellation per implementation. Use a separate completion/ack if you need to wait for confirmation.

**Immediately retrying when interrupted.** The reason for interruption may be shutdown; retrying can fight cancellation policy, create duplicate side effects, and delay stopping.

**Swallowing `close()` errors or letting them mask the primary exception.** Preserve primary/cause/suppressed exceptions and have a policy when cleanup fails.

**Using `Thread.stop()` or forcing threads in ways that break invariants.** Design cooperative cancellation, timeouts, and safe stop points.

**Using a single status for completed, failed, and cancelled.** Callers need to distinguish success, business/technical failure, and cancellation-driven termination to make the right decisions.

## 19. Self-Check Exercises

**Q1.** A worker runs `queue.take()`, gets `interrupt()` called, and catches `InterruptedException`. If the method cannot declare checked exceptions, should you leave the catch block empty?

**Answer:** No. Normally you need to restore `Thread.currentThread().interrupt()` and exit/enter the stop branch; clean up owned resources using an appropriate construct.

**Q2.** Code catches `InterruptedException` and calls `Thread.currentThread().interrupt()` before cleaning up with `latch.await()`. What can happen?

**Answer:** `await()` can throw `InterruptedException` immediately because the interrupt flag is already set. If bounded blocking cleanup is needed, consider organizing cleanup before the restoration point or saving the signal and restoring it afterward.

**Q3.** A worker is given a connection from a pool, and the caller uses a shared executor. When interrupted, should the worker call `executor.shutdownNow()` and `pool.close()`?

**Answer:** No, if the worker only borrows both the executor and the pool. The worker returns the connection / closes the handle it checked out per contract; the executor/pool lifecycle belongs to the shared owner.

**Q4.** `Future.cancel(true)` returns `true` and `future.isCancelled()` returns `true`. Can you conclude that the task's `finally` block has finished running?

**Answer:** No. The task may still be reacting to the interrupt or performing cleanup. To know it is finished, you must rely on a separate completion signal/abstraction.

**Q5.** One worker holds a semaphore permit when interrupted; another worker is interrupted right inside `semaphore.acquire()` before getting a permit. Do the two workers have the same cleanup?

**Answer:** No. Only the worker that acquired a permit may release it. Use a structure that tracks acquisition state or place `try/finally` after the successful acquisition point.

**Q6.** The body throws `InterruptedException`, and `AutoCloseable.close` throws `IOException`. What does try-with-resources do?

**Answer:** `InterruptedException` from the body is primary; `IOException` from close is suppressed. Callers can inspect `getSuppressed()` to diagnose both, then restore/propagate the interrupt signal per contract.

## 20. Key Takeaways

Receiving an interrupt means the application is being asked to **cooperatively transition to an appropriate stopping state**. For code that owns resources, place cleanup in a scope guaranteed by `try-with-resources` or `finally`, exit loops at safe points, preserve interruption information, and distinguish a cancellation request from actual cleanup completion.

Quick checklist: **Who owns the resource? When an interrupt arrives, where does the task stop? Does cleanup run on the exception path too? Are the interrupt flag and cleanup errors preserved? How does the caller know when stopping is complete?** Answering those five questions clearly helps reduce resource leaks, preserve invariants, and make shutdowns verifiable.
