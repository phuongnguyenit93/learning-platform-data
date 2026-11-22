# Restoring the Interrupt Flag When Exceptions Cannot Be Propagated in Java

In Java, **interruption** is a mechanism that requests a thread to cooperatively stop or alter the work it is currently performing. It does not forcibly terminate the thread. A thread may be waiting in `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()`, or another blocking operation that supports interruption. When the thread is interrupted, these methods typically **throw `InterruptedException` and simultaneously clear the interrupt status** as part of their contract.

If a processing method is allowed to declare `throws InterruptedException`, the simplest approach is usually to **propagate the exception up to the caller** so that layer can decide how to handle cancellation. However, there are API boundaries that **do not permit declaring checked exceptions**, such as `Runnable.run()`, `Consumer.accept()`, many callbacks, overridden interface methods without `throws InterruptedException`, or a public API that intentionally omits that exception.

In cases where **the exception cannot be propagated**, the critical default rule is:

> **After catching `InterruptedException`, if the interrupt request has not been completely handled at the current layer, restore the status using `Thread.currentThread().interrupt()`, then stop or return control appropriately.** Never catch it and silently continue working as if no cancellation request had ever occurred.

This Knowledge article belongs to the **Interrupt & Cancellation** group in **general Java concurrency**, focusing on Java SE 17+ without using Spring Framework-specific mechanisms.

## 1. What is the interrupt flag?

Every `Thread` has an **interrupt status**: a logical state that can be set when someone calls `thread.interrupt()`. The thread being requested to interrupt typically checks the status itself or is calling an API with a contract for handling interruption.

Three calls to distinguish:

| Call | Affected target | Semantics |
| --- | --- | --- |
| `targetThread.interrupt()` | `targetThread` | Sets/requests interrupt; if the target is waiting in an interruptible API, the API may wake it up with an exception |
| `targetThread.isInterrupted()` | `targetThread` | Reads the interrupt status; **does not clear** the status |
| `Thread.interrupted()` | **Current thread** | Reads and **clears** the interrupt status of the current thread when returning true |

`Thread.interrupted()` is a **static method**; it is not a method for checking the status of an arbitrary thread. Avoid writing `otherThread.interrupted()` hoping it checks `otherThread`: that static call still operates on the **current thread**. To inspect the status of a specific thread, use `otherThread.isInterrupted()`.

It is important to distinguish between **request** and **completion**:

- `interrupt()` sets a request; it does not guarantee that the `run()` method has finished.
- `isInterrupted()` returns the flag; it does not prove that the thread has stopped, cleaned up, or that the task succeeded.
- `Thread.join()`, `Future.get()`, or a dedicated completion signal is the appropriate mechanism to know that work has completed according to contract.
- A thread may ignore the interrupt, process it successfully, or terminate; the outcome depends on the code and the blocking API being used.

## 2. Why can `InterruptedException` cause the interrupt flag to be lost?

Many Java blocking APIs support interruption by **throwing a checked exception**. When throwing `InterruptedException` due to being interrupted, typical APIs like `Thread.sleep()` and `Object.wait()` **clear the interrupt status** before control is transferred to `catch`.

Logical example:

```text
Before request:
  interrupt flag = false
  worker is sleeping

Another thread:
  worker.interrupt()

Worker:
  sleep() detects interruption
  sleep() throws InterruptedException
  interrupt status is cleared as part of the contract
  catch (InterruptedException e) { ... }
```

Clearing the status here is intentional: **the exception itself is the way to inform the code that an interruption event occurred**. If the code catches the exception and only logs and ignores it, the signal may have no remaining path to propagate up to the coordinating layer.

You should not generalize that **every** API or **every** interruption always clears the flag. Some operations may preserve the status, respond with a different value, or not accept interruption while blocking. You must read the contract of the specific API.

In particular, `Thread.interrupted()` **actively clears** the flag when used to check it; `Thread.currentThread().isInterrupted()` does not.

## 3. When to propagate, and when to restore?

Three important scenarios:

### Case A — the method declares `throws InterruptedException`

If the method's contract allows it, **propagating the exception** is usually the most appropriate approach:

```java
static String receive(
        java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

This is an illustrative method, not a program with `main`. It does not catch the interruption and does not turn a cancelled task into a successful receive.

In code that requires cleanup:

```java
static String receiveWithCleanup(
        java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    try {
        return queue.take();
    } finally {
        // Release resources belonging to the method's scope, if any.
    }
}
```

This is still an illustrative snippet. If the caller wants to know and decide how to cancel, you can let the exception propagate upward. **It is not mandatory to both call `interrupt()` and propagate `InterruptedException`**; the exception is already the signal for the next layer. Simultaneously restoring the status may be appropriate under a special contract, but it is not a required rule when already propagating.

### Case B — cannot declare `throws InterruptedException`

`Runnable.run()` does not declare this checked exception. A thread running a `Runnable` must catch the exception if it calls APIs like `sleep()` or `take()`. If you want to defer the decision to an outer layer via the flag, use:

```java
@Override
public void run() {
    try {
        doInterruptibleWork();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

This is an illustrative snippet inside a class implementing `Runnable`, where `doInterruptibleWork()` is a hypothetical method. `Thread.currentThread().interrupt()` **restores the status of the executing thread**, and then `return` exits `run`. If you continue into a long processing loop after catch, the flag might be set, yet the task still continues working against the cancellation intent.

### Case C — the current layer has completely handled the interruption by contract

A specialized API may **intentionally consume** the interrupt if its responsibility is to terminate the activity and publish the cancellation result through another mechanism, and the contract clearly specifies this. In that case, there is no absolute rule requiring restoration in every catch block.

However, **do not claim it is "handled" just because you logged the exception**. If the cancellation still needs to be observed by the caller or an executor framework, restoring is the safer choice when you cannot propagate. You must distinguish intentional signal handling from accidentally losing the signal.

## 4. Why is `catch (InterruptedException e) { }` an anti-pattern?

Wrong:

```java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Ignore the cancellation request and keep waiting.
    }
}
```

This is an anti-pattern with a hypothetical `queue` variable. Consequences:

1. `take()` may have cleared the interrupt flag before throwing.
2. An empty catch block discards information about the cancellation request.
3. The loop goes back to `take()` and waits indefinitely, even though the caller expects the worker to exit.
4. `Future.cancel(true)` or cooperative shutdown can become ineffective at stopping the task.
5. The system struggles to distinguish between a busy worker, a stuck worker, and a worker intentionally ignoring cancellation.

It is also insufficient to merely write:

```java
catch (InterruptedException e) {
    System.err.println("Interrupted: " + e);
}
```

Logging does not replace propagation or status restoration. If code continues normally after the catch, API users may assume the task was not cancelled. **Better:** explicitly decide to "propagate", "restore and terminate", or "transition to a cancellation state per contract".

## 5. Java 17+ Example: restoring the interrupt flag in `Runnable`

Save as `InterruptRestoreDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptRestoreDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean clearedWhenCaught = new AtomicBoolean();
        AtomicBoolean restoredInsideCatch = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                Thread.sleep(60_000);
            } catch (InterruptedException e) {
                // sleep() handled the interruption with an exception
                // and cleared the flag per its contract.
                clearedWhenCaught.set(
                        !Thread.currentThread().isInterrupted());

                // Cannot throw InterruptedException from Runnable.run().
                Thread.currentThread().interrupt();
                restoredInsideCatch.set(
                        Thread.currentThread().isInterrupted());
                return;
            }
        }, "interrupt-restore-worker");

        worker.start();
        entered.await();

        worker.interrupt();
        worker.join();

        System.out.println("Flag cleared in catch: "
                + clearedWhenCaught.get());
        System.out.println("Flag restored in catch: "
                + restoredInsideCatch.get());
        System.out.println("Worker terminated: "
                + !worker.isAlive());
    }
}
```

Compile/run:

```bash
javac InterruptRestoreDemo.java
java InterruptRestoreDemo
```

Exact stdout on a normal run:

```text
Flag cleared in catch: true
Flag restored in catch: true
Worker terminated: true
```

Why is this reliable?

- `entered` only signals that the worker has reached the point right before calling `sleep()`. If main interrupts before the worker actually sleeps, sleep still responds to the interrupt status; if the worker is already sleeping, it is woken up with `InterruptedException`. It does not rely on a `Thread.sleep(100)` in main to guess scheduling.
- When `InterruptedException` is thrown from `sleep`, the interrupt flag has been cleared; `clearedWhenCaught` receives true.
- The worker sets the flag again using `Thread.currentThread().interrupt()`, observes true inside catch, and then **exits `run()`**.
- Main calls `join()` to wait for the worker to finish before reading the two `AtomicBoolean` values and thread state.
- **Do not rely on `worker.isInterrupted()` from main after `join()` as a mandatory verification**. Once a thread has terminated, you should not rely on post-lifecycle interrupt status to convey business meaning. The example records the flag directly inside the worker to verify the semantics at the right time.

This is an example of how to **preserve a cancellation request** across an API boundary that does not permit throws; it does not force the thread to be killed.

## 6. `Thread.interrupted()` clears the flag, whereas `isInterrupted()` does not

Save as `InterruptFlagMethodsDemo.java`:

```java
public class InterruptFlagMethodsDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        current.interrupt();

        System.out.println("Before check: "
                + current.isInterrupted());
        System.out.println("Static check: "
                + Thread.interrupted());
        System.out.println("After static check: "
                + current.isInterrupted());

        current.interrupt(); // Restore once more.
        System.out.println("Restored: "
                + current.isInterrupted());

        // Clear the interrupt status to conclude the demo.
        Thread.interrupted();
    }
}
```

```bash
javac InterruptFlagMethodsDemo.java
java InterruptFlagMethodsDemo
```

Exact stdout:

```text
Before check: true
Static check: true
After static check: false
Restored: true
```

`Thread.interrupted()` is a **static** call and checks the **current thread**, then clears the flag if it was set. Conversely, `current.isInterrupted()` does not clear the flag. At the end of the program, there is a `Thread.interrupted()` call purely for **intentional** cleanup in the example; you must not use this "check and accidentally clear" pattern in business code that intends to forward a cancellation request.

For a cooperative processing loop, you can check:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
```

This is an illustrative pattern; `processOneUnit` is undefined. If the inner method can block or throw `InterruptedException`, you must combine it with exception handling to exit the loop at the right time. Checking the flag does not by itself wake up a blocking call.

## 7. Why should you usually exit after restoring, rather than just continuing?

A subtle bug:

```java
while (true) {
    try {
        performBlockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Yet continues running the loop.
    }
}
```

If `performBlockingOperation` responds immediately upon seeing the interrupt flag set, the next iteration may repeatedly throw `InterruptedException`, creating a CPU-consuming **busy loop**. If another API does not check the flag, the code may continue doing work despite having received a cancellation request.

A usually better pattern:

```java
while (!Thread.currentThread().isInterrupted()) {
    try {
        performBlockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
```

Both snippets above are illustrative, with `performBlockingOperation` being hypothetical.

**Separate two decisions:** restoring the flag to preserve the interruption information, and **stopping/rejecting new work** to actually cooperate with cancellation. Performing only the first action without the second can leave the "interrupted" state active on a thread that is still executing business logic.

If the method catching the exception is deep in a call stack, it can restore and `return` a cancellation status to the caller so the caller does not proceed; if the API has a return type, a sentinel or result type representing cancellation must be clearly defined.

## 8. Java 17+ Example: worker waiting on a queue and stopping cooperatively

Save as `CooperativeQueueWorkerDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeQueueWorkerDemo {
    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean stoppedOnInterrupt = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();

            try {
                while (!Thread.currentThread().isInterrupted()) {
                    queue.take(); // May block when the queue is empty.
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                restored.set(Thread.currentThread().isInterrupted());
                stoppedOnInterrupt.set(true);
            }
        }, "queue-worker");

        worker.start();
        started.await();

        worker.interrupt();
        worker.join();

        System.out.println("Stopped: " + stoppedOnInterrupt.get());
        System.out.println("Flag at exit: " + restored.get());
    }
}
```

```bash
javac CooperativeQueueWorkerDemo.java
java CooperativeQueueWorkerDemo
```

Exact stdout:

```text
Stopped: true
Flag at exit: true
```

Scheduling may vary:

- If the worker has already entered `queue.take()`, interruption typically causes `take` to throw `InterruptedException`, the catch block sets the flag again, and control enters `finally`.
- If main interrupts before the worker enters `take()`, the loop may observe the flag and exit directly; or the `take` call may detect the interrupt and throw. Both lead to checking a true status at the exit point.
- The queue is always empty, so there is no case where the worker executes a new task before exiting that would change stdout.
- `join` ensures main waits for the worker to complete before reading the results.

`stoppedOnInterrupt` in the example records true when the worker leaves the processing block; it is an observation flag for the demo, **not a complete completion contract** for a complex application. If you need to retrieve task errors/results, `Future` or an appropriate result type is usually clearer.

In production, you need to distinguish other errors from interruption. A task finishing normally or encountering another exception will also run `finally`; you should not rely solely on "entered finally" to conclude the reason for termination if the code has multiple branches.

## 9. Common boundary: `Runnable.run()`

`Runnable.run()` has the signature:

```java
void run();
```

This is the interface signature, which does not declare the checked `InterruptedException`. Code inside `run` must handle the exception if it calls interruptible APIs.

Common pattern:

```java
final class Worker implements Runnable {
    private final java.util.concurrent.BlockingQueue<String> queue;

    Worker(java.util.concurrent.BlockingQueue<String> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (true) {
                String message = queue.take();
                handle(message);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            // Return from run() to stop the thread/task.
        }
    }

    private void handle(String message) {
        // Non-blocking processing or has its own error policy.
    }
}
```

This class does not have `main`, but uses pure Java SE. If `handle` can block, throw exceptions, or update out-of-process state, it needs an additional cancellation contract and handling for partial side effects.

Because the `Runnable` API is a boundary that does not allow declaring checked exceptions, **restore and then return** is a common choice. If an executor framework has a policy for observing exceptions via a future, you may consider wrapping it into an unchecked exception **when the contract requires it**; you still must define the interrupt status and how errors are reported. Do not automatically turn every interruption into a "business failure" without checking the contract.

## 10. Common boundary: `Consumer<T>`, listeners, and callbacks

Callback example:

```java
import java.util.function.Consumer;

Consumer<String> listener = event -> {
    try {
        Thread.sleep(1_000);
        System.out.println(event);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
```

This is an illustrative snippet within a valid context with imports; not a file with `main`. `Consumer.accept` does not declare the checked `InterruptedException`, so the callback must handle it.

**Two risks:**

1. An interrupted callback may stop only itself while **the publisher continues invoking other callbacks**, depending on the publisher's contract. Therefore, you need to define whether the caller cares about the status of the thread running the callback and how the callback should communicate the cancellation result.
2. If the callback runs on a **shared thread**, the interrupt status is restored on that thread. This is accurate information at the callback boundary, but the caller/dispatcher needs a policy not to continue running normal tasks regardless of the status.

Do not assume a callback necessarily runs on its own dedicated thread. A listener may be invoked **synchronously on the calling thread**, or by an executor; the interaction mechanism determines who owns the thread being interrupted. In a public API, document the threading model, cancellation behavior, and failure propagation.

### Overridden methods that do not allow adding checked exceptions

If an interface specifies:

```java
interface Listener {
    void onMessage(String message);
}
```

the implementation cannot arbitrarily add `throws InterruptedException` to the overridden signature. If the processing must block, you can:

- Catch, restore the flag, and then **return/abort** per contract.
- Change an API under your control to allow checked interruption or return a cancellation status.
- Use a separate callback with a `throws InterruptedException` signature if you actually have the authority to change the interface.
- Offload the blocking work to a layer that can propagate exceptions via `Callable`/future appropriately.

Do not turn a signature constraint into an excuse to **swallow interruption**.

## 11. `Callable<V>` and how it differs when propagation is possible

`Callable.call()` has the signature:

```java
V call() throws Exception;
```

It allows propagating `InterruptedException` (which is a subclass of `Exception`), unlike `Runnable.run()`.

Example:

```java
Callable<String> task = () -> queue.take();
```

This is an illustrative snippet, assuming `queue` is a `BlockingQueue<String>` and `java.util.concurrent.Callable` is imported.

When a task is submitted to `ExecutorService.submit`, exceptions from `call` are captured in the `Future`; a caller using `Future.get()` may encounter `ExecutionException` wrapping the cause. Distinguish between:

- `InterruptedException` thrown **inside the worker task**.
- `InterruptedException` thrown **in the caller waiting on `future.get()`** because the **caller thread** was interrupted.
- `CancellationException` when the future has been cancelled per contract.
- `ExecutionException` when the task terminates with an exception.

These are different execution paths. A caller should not catch an `InterruptedException` from `future.get()` and assume the worker was also interrupted; it signals that **the thread calling `get` was requested to interrupt while waiting**.

If `Callable.call` itself can propagate the exception up to the management layer, **there is no need to catch and restore by default**. If `call` catches only to perform cleanup and then rethrows/propagates, it must preserve the cancellation information and not turn it into a successful result.

## 12. Java 17+ Example: Future and two types of interruption

The following program verifies that **the caller of `Future.get()` is interrupted**, while the task is only released afterward via a separate signal. Do not mistakenly infer that interrupting the caller means interrupting the worker.

Save as `FutureWaitInterruptionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureWaitInterruptionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch allowTaskToFinish = new CountDownLatch(1);
        CountDownLatch aboutToGet = new CountDownLatch(1);
        AtomicBoolean callerRestored = new AtomicBoolean();

        try {
            Future<Integer> future = pool.submit(() -> {
                allowTaskToFinish.await();
                return 42;
            });

            Thread caller = new Thread(() -> {
                try {
                    aboutToGet.countDown();
                    future.get();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    callerRestored.set(
                            Thread.currentThread().isInterrupted());
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }, "future-caller");

            caller.start();
            aboutToGet.await();
            caller.interrupt();
            caller.join();

            // The task was not cancelled or interrupted by the operation on caller.
            allowTaskToFinish.countDown();
            System.out.println("Caller flag restored: "
                    + callerRestored.get());
            System.out.println("Task result: " + future.get());
        } finally {
            allowTaskToFinish.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac FutureWaitInterruptionDemo.java
java FutureWaitInterruptionDemo
```

Exact stdout on a normal run:

```text
Caller flag restored: true
Task result: 42
```

**Why this is deterministic:**

- The worker task waits on `allowTaskToFinish`, so it cannot finish while the caller thread is waiting on `future.get()`.
- The caller signals that it has reached the point right before `get()`; main may interrupt before or during `get()`. If the interrupt arrives before the actual wait call, `get()` still sees the interrupt status when it has to wait on an incomplete future.
- `future.get()` throws `InterruptedException` on the **caller**, and the catch block restores the caller's flag.
- `caller.join()` waits for the caller thread to exit, and then main releases the task. Only then does `future.get()` in main retrieve the result 42.
- `finally` ensures main opens the latch if an error occurs along the way, and then issues a shutdown request.

Do not use this example to conclude that `Future.get()` always responds to interruption at one exact moment: it is a waiting API that can be interrupted, whereas if the future has already completed before the caller begins waiting, conditions may differ. Keeping the task incomplete in the demo makes the outcome stable.

## 13. `Future.cancel(true)` does not mean "already finished handling"

`Future.cancel(true)` is a cancellation request that may allow sending an interrupt to the worker if the task is running and can be interrupted according to the implementation. The return value indicates whether the cancel request was accepted per the future's contract; it **does not guarantee that all side effects have immediately stopped** or that resources have finished cleaning up.

If the worker:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    // Swallow the exception and continue.
    continueWorking();
}
```

then cancellation may not cause the code to stop as the caller expects. The pattern above is an illustrative anti-pattern with hypothetical methods.

If the worker restores and exits, that is **cooperative cancellation** aligned with the goal. Even so, distinguish:

- **Future cancelled** does not mean the executor has completely released all of the task's resources.
- **Thread interrupted** does not mean the task left no partial side effects.
- **Thread terminated** does not mean the operation succeeded.
- When using `CompletableFuture.cancel(...)`, per the contract of `CompletableFuture`, the `mayInterruptIfRunning` parameter is not used to control underlying processing; do not assume cancellation will interrupt a running task the way some executor-managed Futures do.

To wait for the lifecycle to truly complete, you need an explicit completion/cleanup contract, or a separate future or latch if the cancelled state is not sufficient to represent the cleanup point.

## 14. Restoring the flag in a utility method that does not declare throws

A helper sometimes has a signature that cannot be changed, such as:

```java
boolean awaitQuietly(CountDownLatch latch);
```

The word "quietly" easily tempts the author to ignore interruption. If a checked exception cannot be propagated, you can return `false` and restore the flag, **but only when the contract defines `false` as cancelled/incomplete**.

Java pattern:

```java
static boolean awaitOrCancel(
        java.util.concurrent.CountDownLatch latch) {
    try {
        latch.await();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

This is an illustrative method, not a program with `main`.

**Important:** the caller must check the result:

```java
if (!awaitOrCancel(latch)) {
    return; // Do not proceed into the branch that requires the latch to have completed.
}
performAfterCompletion();
```

This is another illustrative snippet with hypothetical `latch` and `performAfterCompletion`. If the caller ignores `false` and continues working anyway, the promise to "return false when not ready" does not help maintain the invariant.

A clearer API might use a result enum `COMPLETED`/`INTERRUPTED`, or separate the interruptible method from a no-throws wrapper with a specific policy.

## 15. Java 17+ Example: returning a cancellation result and preserving the interrupt flag

Save as `NoThrowsBoundaryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class NoThrowsBoundaryDemo {
    static boolean awaitOrCancel(CountDownLatch gate) {
        try {
            gate.await();
            return true;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean result = new AtomicBoolean(true);
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            ready.countDown();
            result.set(awaitOrCancel(gate));
            restored.set(Thread.currentThread().isInterrupted());
        });

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("Gate passed: " + result.get());
        System.out.println("Flag restored: " + restored.get());
    }
}
```

```bash
javac NoThrowsBoundaryDemo.java
java NoThrowsBoundaryDemo
```

Exact stdout:

```text
Gate passed: false
Flag restored: true
```

The gate is **never opened**, so without being interrupted, the worker would keep waiting. Main requests an interrupt; the helper catches, restores, and returns `false`. Both `AtomicBoolean` instances allow main to read after `join`, although `join` itself already establishes a happens-before relationship for reading the results written by the worker.

The example illustrates how to define the **wrapper's contract**: `false` does not mean the gate completed; it means the method could not wait successfully. The calling layer needs to decide to terminate the work when it receives false.

## 16. Should you rethrow with an unchecked exception?

When an API does not allow `throws InterruptedException`, some systems choose:

```java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while working", e);
}
```

This is an illustrative snippet, not a universal formula for every layer.

Pros: **does not pretend to succeed**; error information can reach an exception handler or future. Cons: an unchecked exception may be treated by the system as an application failure rather than cancellation; it can change the public API contract and cause listener dispatching to stop abruptly.

If you choose this approach, the documentation must clearly state:

- Which exception represents interruption/cancellation?
- Does the caller rely on the restored interrupt flag?
- Is there resource cleanup required before throwing?
- Will the task be retried due to a runtime exception; could a retry duplicate side effects?

The simple approach for `Runnable.run()` is usually **restore and then return** when the task only needs to stop. Using an unchecked exception is appropriate when the coordinating layer needs to receive failure via an exception and the contract is clearly defined.

## 17. Cleanup, `finally`, and when to restore the flag

When interrupted, code may still need to release locks, permits, files, or owned resources. Both rules—**do not skip cleanup** and **do not lose the interruption**—are important.

If cleanup is simple and has no blocking operations:

```java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseOwnedResource();
}
```

This is an illustrative example. `finally` runs when control leaves `try/catch`, even when catch executes `return`; however, **it cannot guarantee every cleanup will succeed** if cleanup itself throws an exception.

If cleanup **can block and supports interruption**, restoring the flag **before** cleanup may cause the cleanup call to immediately throw `InterruptedException`, hindering resource release. In some designs, you need to temporarily **remember that an interrupt occurred**, perform bounded cleanup per contract, and then **restore the flag in `finally` after cleanup**:

```java
boolean interrupted = false;

try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    interrupted = true;
    // Do not continue normal business work.
} finally {
    try {
        cleanupWithDefinedPolicy();
    } finally {
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

This is an illustrative pseudo-flow; `doInterruptibleWork` and `cleanupWithDefinedPolicy` are hypothetical methods. It is only appropriate when the current layer **actually owns the cleanup** and delaying restoration is intentional, not swallowing the signal. If cleanup is also interrupted, the policy must decide how to handle timeout/retry/propagation. Never perform **uninterruptible infinite retries** just to "finish cleanup at all costs".

In particular, `synchronized` automatically releases the monitor when leaving the block; a manual `Lock` must call `unlock()` in `finally`. Restoration does not replace releasing the lock.

## 18. How to handle when cleanup itself is interrupted?

Consider a two-phase utility scenario:

1. Wait for work to complete.
2. When interrupted, attempt to record/release resources and exit.

If the cleanup phase also calls blocking APIs, several behaviors depend on the contract:

- **Best-effort cleanup with a deadline:** try within a finite time window, then record failure or return an error state; restore the flag upon completion.
- **Short, uninterruptible cleanup:** execute the guaranteed internal release operation and then restore.
- **Propagate a higher-level exception:** if the current layer is allowed, propagate the interruption or failure with the appropriate cause; avoid losing the original cause.
- **Close the resource to wake waiters:** depending on the specific contract of the queue/channel/resource, do not assume `Thread.interrupt()` stops all I/O.

Another anti-pattern is looping:

```java
while (true) {
    try {
        cleanupBlocking();
        break;
    } catch (InterruptedException ignored) {
        // Attempt to wait indefinitely, without saving status and without timeout.
    }
}
```

This is an incorrect illustrative snippet: it can ignore cancellation requests for a long time with no bound on progress. If cleanup must complete, design a protocol with a deadline and record the interrupt condition; do not assume "cleanup is important, so ignore all interrupts".

## 19. An `AtomicBoolean` flag is not equivalent to the interrupt flag

Many applications have:

```java
AtomicBoolean stopRequested = new AtomicBoolean();
stopRequested.set(true);
```

An atomic/volatile flag helps a worker see a request when it actively checks. However, the flag does not automatically wake up a thread blocked in `BlockingQueue.take()` or `Object.wait()`. Interruption is a dedicated mechanism that many blocking APIs understand in order to **break out of a waiting call**.

Conversely, merely calling `thread.interrupt()` does not by itself define the business outcome: the task might stop partway, ignore the request, or finish normally. You usually need a combination of:

- A task cancellation policy.
- A signaling channel (interrupt, sentinel, close, timeout, or cancellation token).
- A completion signal so the caller knows cleanup is done.
- A way to report errors or cancellation status to the caller.

When restoring the flag, you **preserve the interrupt request information**, not build an entire lifecycle protocol on your own.

## 20. Not all blocking I/O responds to interruption like `sleep()`

Some APIs in `java.nio.channels` have semantics that close the channel when a thread is interrupted, or respond via a different exception. Some legacy I/O operations may not stop promptly when only `interrupt()` is called. Network libraries, drivers, or native code have their own contracts.

Therefore:

- Do not mechanically apply "every blocking I/O throws `InterruptedException`".
- If an API returns a different exception due to interruption, read its contract to decide how to properly preserve the status/cancellation signal.
- Design appropriate timeouts, resource closing, and cancellation paths.
- If an operation cannot be cancelled, document the limitation and monitor stuck threads/resources.
- Avoid holding a monitor while performing potentially long-blocking I/O, because stopping/cleanup may require another thread to enter that monitor.

The lesson on **restoring the interrupt flag** primarily applies to situations where **an interruptible call threw `InterruptedException` and cleared the status**, and your code cannot propagate the checked exception upward. For other APIs, do not guess semantics without reading the contract.

## 21. Interrupt flag and the Java Memory Model

Interruption has happens-before guarantees in the JMM: an `interrupt()` call on a target thread **synchronizes-with** the point where a thread detects it has been interrupted per contract (for example, receiving `InterruptedException`, or checking the status with the appropriate API).

However, an interrupt request **does not replace locks protecting shared mutable state**. If you have:

```java
sharedList.add(item);
worker.interrupt();
```

you cannot rely solely on `interrupt()` to conclude that all concurrent operations on `ArrayList` are safe. The ordering relationship of an interrupt signal does not turn a list into a concurrent collection or create a transaction across multiple operations.

Similarly, the interrupt status does not provide:

- Atomicity for `count++`.
- Mutual exclusion for multiple writers.
- Guaranteed fairness when there are multiple tasks.
- A notification of a successful task result.
- The ability to roll back side effects outside the JVM.

**Restoration is a signal-preservation technique**, not a way to fix an algorithm that has a data race.

## 22. Interaction with executors and thread pools

When a task runs in an executor, the executing thread may be **reused**. Interruption is a state of the **thread**, whereas cancellation/failure/completion of a task is a **separate business state**.

Keep in mind:

1. An interrupted `Runnable` should **exit in a controlled manner**, not continue consuming the next task as if everything were normal.
2. If a task catches `InterruptedException` and ignores it, `shutdownNow()` or `cancel(true)` may not stop the task as quickly as expected.
3. Restoring the flag preserves the cancellation request at the task boundary, but **does not guarantee the executor will expose that flag to the caller**; use a future/result or cancellation state to report lifecycle.
4. Do not rely on leftover interrupt status on a pooled thread for the **next task**; thread-pool implementations may handle/reset the status according to their own logic. Each task must have an independent contract.
5. If a task must stop itself due to interruption, do not perform new I/O, callbacks, or side effects after restoring and realizing it has been cancelled.
6. If the task-management API has its own policy on interruption, follow that policy rather than deciding on your own to "swallow it to reduce logs".

With thread pools, "swallowed interrupt" bugs are especially hard to find because the pool stays alive, the future may already be cancelled, yet the worker may continue holding resources or doing unnecessary work.

## 23. Common mistakes

| Mistake pattern | Why it is wrong | How to handle it |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Clears the signal, continues normally | Propagate if possible; otherwise, restore and stop per contract |
| Catch and only log | Logging does not pass the cancellation request to upper layers | Restore/propagate, define an exit path |
| Restore and continue an infinite while loop | Can busy-loop or do extra work after cancellation | `break`/`return`, or explicit flag-checking logic |
| Calling `Thread.interrupted()` to "check" without wanting to clear | The static method clears the flag | Use `isInterrupted()` |
| Calling `otherThread.interrupted()` | The static method still affects the current thread | Use `otherThread.isInterrupted()` |
| Automatically restoring even when propagating | Can create two unnecessary signal channels and complicate caller handling | If `InterruptedException` can be propagated, usually just propagate it |
| Using `AtomicBoolean` instead of interrupting blocking calls | The flag does not wake up a blocking API | Add interrupt/timeout/close or a signaling protocol |
| Calling interrupt and assuming the worker is dead | Interrupt is only a request | Wait for completion via `join`/future/latch per contract |
| Treating `Future.cancel(true)` as a guarantee that side effects rolled back | Cancellation is not a transaction | Manage idempotency, cleanup, and completion |
| Wrapping into a RuntimeException while dropping the cause | Loses the origin of the interruption | Preserve the cause, document the failure/cancellation policy |
| Restoring before blocking cleanup and looping infinitely | Cleanup may be repeatedly interrupted | Have a cleanup policy and deadline, restore at the right time |
| Ignoring interruption because "it's just a test" | Tests can hang and mask races | Preserve/propagate properly, bound wait times |

## 24. When should you **not** use `Thread.currentThread().interrupt()`?

Not every concurrency-related situation requires restoration:

- **Do not catch `InterruptedException`:** if the method declares `throws InterruptedException`, let the exception propagate upward.
- **A cancellation contract has been completely handled** at the responsible layer, with a clear outcome, and the policy specifies that the signal does not need to be forwarded via the interrupt status; this is an intentional exception, not silence.
- **Handling an exception unrelated to interruption:** do not arbitrarily set the interrupt flag just to "signal an error".
- **Only wanting to stop another task:** do not call `Thread.currentThread().interrupt()` to interrupt a worker on another thread. Call `targetThread.interrupt()` or the cancellation API of the task you want to cancel.
- **Passing a cancellation result via another mechanism that the caller needs to distinguish:** you can choose a specific result-returning protocol, but you must clearly document what happens to the interrupt status at the current boundary.

However, when **you have caught `InterruptedException` from an interruptible call and cannot rethrow it**, restoring is usually the **safest default choice** unless the contract explicitly states it is completely handled.

## 25. Checklist for reviewing an `InterruptedException` catch block

Before accepting the code, ask yourself:

1. **Which statement threw `InterruptedException`?** Does that API clear the interrupt flag when throwing?
2. **Can the current method declare `throws InterruptedException`?** If yes, prefer propagating.
3. **If it cannot declare throws, was `Thread.currentThread().interrupt()` called?**
4. **After restoring, does the execution path terminate or abort work properly?** Or does it go back into a wait loop?
5. **Is cleanup required?** Can cleanup block or be interrupted; was restoring before or after chosen intentionally?
6. **How does the caller know the task was cancelled?** Result/exception/future/state must be documented.
7. **Did any side effects occur before the interrupt?** Do retries or rollbacks require idempotency?
8. **Is caller interruption confused with worker interruption?** `Future.get()` can throw on the waiting thread.
9. **Was `Thread.interrupted()` used, losing the flag?** If you only want to check, use `isInterrupted()`.
10. **Are there blocking operations that do not support interruption?** Separate timeout/close is needed instead of just restoring.
11. **Does a thread pool reuse workers?** Do not rely on the interrupt flag as a completion channel for the next task.
12. **Are both early interrupts and interrupts during blocking tested?** Use latches/conditions to coordinate, not guessed sleeps.
13. **Are tests prevented from hanging indefinitely?** For failure paths, use timeouts in the test harness and explicit shutdown cleanup.
14. **Is the status read at the right time?** To verify restoration, measure inside the worker itself before the task ends; do not rely on post-termination state.

## 26. Self-check questions

**1. Why can `Thread.sleep()` cause `Thread.currentThread().isInterrupted()` to return false inside `catch (InterruptedException e)`?**

Because `sleep` handles interruption by throwing `InterruptedException` and clearing the interrupt status per its contract. If the cancellation request is not yet completely handled, the catch block should restore it before yielding control.

**2. Can `Runnable.run()` declare `throws InterruptedException`?**

You cannot add that checked exception when overriding `Runnable.run()`. Inside `run`, you must catch, restore, and then stop or apply an appropriate failure policy.

**3. Why is `catch (...) { Thread.currentThread().interrupt(); }` not necessarily enough?**

Because the code might still continue executing business logic after the catch or re-enter a blocking call. You also need a `return`, `break`, or explicit cancellation handling path.

**4. How do `Thread.interrupted()` and `isInterrupted()` differ?**

`Thread.interrupted()` checks the **current thread** and clears the status if it is set. `isInterrupted()` reads the receiver's status without clearing it.

**5. If a method already declares `throws InterruptedException`, do you need to catch, restore, and then rethrow?**

Not by default. Propagating the exception to the caller is usually enough to preserve the cancellation signal. Restoring in addition may be required by a specific contract, but it is not a general rule.

**6. Why does `Future.get()` throwing `InterruptedException` not prove that the worker was interrupted?**

Because the exception may have occurred on the **caller waiting on the future**, while the worker task is still running. You must distinguish which thread received the interrupt.

**7. Does restoring the interrupt flag automatically wake up an I/O call that does not support interruption?**

No. You must understand the specific I/O contract and may need timeouts, close/cancel, or another mechanism.

**8. Can an `AtomicBoolean stopRequested` flag completely replace interruption?**

No. The flag helps with visibility of state checked by the application itself; it does not wake up `BlockingQueue.take()` or `Thread.sleep()`.

**9. After restoring the flag, should you keep retrying the same blocking operation indefinitely?**

Usually no. It can create a busy loop or perform work contrary to the cancellation request. You should exit or transition to a documented cancellation policy.

**10. Why might you need to restore **after cleanup** instead of at the very start of catch?**

Because some cleanup operations can block and immediately respond to an active interrupt status. When intentional, retain the interruption information, perform cleanup under a deadline/policy, and then restore in finally.

## 27. Summary

- **Interrupt is a cooperative request**, not a command to forcibly stop a thread or roll back work.
- When a blocking API throws `InterruptedException`, many standard APIs have already **cleared the interrupt flag**; if you catch and ignore it, you may lose the cancellation request.
- **If you can propagate, usually propagate.** For `Runnable`, `Consumer`, callbacks, or methods that do not allow adding checked exceptions, **restore with `Thread.currentThread().interrupt()` and then stop/abort per contract**.
- **`isInterrupted()` reads without clearing; `Thread.interrupted()` reads and clears the current thread.** Do not confuse them.
- Restoring the flag **does not automatically terminate the task**. The control flow must cooperate with cancellation; blocking I/O in particular needs an appropriate policy.
- Cleanup, timeouts, exception propagation, future states, and already-occurred side effects must be designed separately; restoring the signal does not solve the entire lifecycle.
- Do not rely on scheduling or `Thread.sleep` to test interruption. Use latches and appropriate timeouts; verify restoration inside the worker and completion via a guaranteed mechanism.

When encountering `catch (InterruptedException e)` in Java, the central question is **"Who is responsible for handling the cancellation request next, and is the interrupt information preserved up to that boundary?"**. If you can propagate the exception, propagate it. If you cannot, **set the interrupt flag again on the current thread and exit the work according to a clear protocol**, rather than accidentally swallowing the signal.
