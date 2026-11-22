# Distinguishing Thread Interruption, `Future` Cancellation, and Forcible Termination in Java

When a task runs for too long or an application needs to stop, three operations are often conflated: **thread interruption** (`Thread.interrupt()`), **task cancellation** (`Future.cancel(...)`), and **forcible termination** (such as `Thread.stop()` or terminating the process). They have **completely different targets, result contracts, and risks**. Neither of the first two calls guarantees that an arbitrary piece of code will stop executing immediately.

This lesson belongs to the **Interruption and Cancellation** section of Java Core Exception, using Java 17+ APIs. After studying it, you should be able to explain: who receives an interrupt, why a `Future` can report being canceled while the worker is still running, how to distinguish exceptions when retrieving a result, and when to use a process boundary instead of trying to force-stop a thread.

## 1. Three Different Levels of Control

| Mechanism | Primary Target | Direct Effect | Guaranteed to Stop Worker Immediately? |
|---|---|---|---|
| `thread.interrupt()` | A specific `Thread` | Sets the interrupt status or wakes up an interruptible waiting operation | **No** |
| `future.cancel(false)` | The state of a `Future` | Requests cancellation of the Future, without requesting interruption of a running worker | **No** |
| `future.cancel(true)` | The state of the `Future` and potential interrupt request to the worker | If canceled, the Future transitions to canceled; the implementation may interrupt the running worker | **No** |
| `executor.shutdown()` | Executor lifecycle | Stops accepting new tasks, continues processing already-submitted tasks | **No** |
| `executor.shutdownNow()` | Executor and running/waiting tasks | Attempts to interrupt running tasks, stops accepting/running queued tasks, and returns the list of unstarted tasks | **No** |
| `Thread.stop()` | A thread | Dangerous asynchronous stop mechanism, deprecated | **Should not be used** |
| Terminating the entire JVM/OS process | Process | Terminates the runtime environment of all threads at once | Destroys the whole process; not a safe way to cancel a Java task |

**Distinguishing the targets:** `Thread` is an execution thread, `Future` is a handle for tracking the result/state of a task, and `ExecutorService` is a manager for executing multiple tasks. Performing an operation on one object does not mean the other objects automatically transition to the same state.

A brief diagram:

```text
Caller holding Future<T>                        Worker Thread
         │                                            │
         ├─ thread.interrupt() ──► interrupt flag ──► │
         │                                      worker handles it
         │
         ├─ future.cancel(false) ─► Future=canceled   │ may continue
         │
         └─ future.cancel(true) ──► Future=canceled   │
                                   + try interrupt ──►│ may stop cooperatively

Already canceled ──► future.get() throws CancellationException
Worker fails while Future is not canceled ──► get() throws ExecutionException
```

This diagram describes how `FutureTask` is commonly used by `ExecutorService.submit(...)`. **Not every `Future` implementation uses interruption to control computation.** For example, `CompletableFuture.cancel(boolean)` ignores the `mayInterruptIfRunning` parameter per its own contract; canceling a `CompletableFuture` does not automatically interrupt the thread running the work.

## 2. Thread Interruption: `Thread.interrupt()` Is a Cooperative Request

Each `Thread` has an interrupt status. When thread A calls `worker.interrupt()`, Java signals to `worker` that an interrupt has been requested:

- If the worker is computing and does not call an interruptible waiting operation, the interrupt flag is set; the worker normally continues running until it checks and reacts on its own.
- If the worker is waiting in `Thread.sleep`, `Object.wait`, `Thread.join`, `BlockingQueue.take`, `CountDownLatch.await`, or many other interruptible waiting operations, the wait call may terminate early with `InterruptedException`.
- Those waiting operations typically **clear the interrupt flag when throwing `InterruptedException`**. Code that catches the exception must decide whether to propagate the signal or restore the flag and finish its work.
- `Thread.currentThread().isInterrupted()` reads the current thread's flag without clearing it; the static method `Thread.interrupted()` reads **and clears the current thread's flag**.

`interrupt()` **does not itself create a `CancellationException`**, does not turn a submitted task into canceled, and does not mean the caller is interrupted as well. If the worker actively catches `InterruptedException`, cleans up resources, and returns a normal result, the `Future` can complete **successfully**.

### Standalone Java 17 Example: Interrupting a Thread Without a Future

Create the file `ThreadInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreadInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean observed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                observed.set(true);
                Thread.currentThread().interrupt();
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("received interrupt = " + observed.get());
        System.out.println("worker alive = " + worker.isAlive());
    }
}
```

Run with JDK 17 or later:

```bash
javac ThreadInterruptDemo.java
java ThreadInterruptDemo
```

Output:

```text
received interrupt = true
worker alive = false
```

`ready` ensures the worker has reached the execution block before `main` sends the signal; even if the worker has not yet called `await()`, the interrupt status will still cause that wait call to throw `InterruptedException`. The worker exits `run()` on its own and therefore terminates, rather than `interrupt()` forcing it to stop. `join()` waits for the worker to finish before printing the results; `AtomicBoolean` records that the worker received the signal.

In the `catch` block, we restore the flag with `Thread.currentThread().interrupt()` because `await()` cleared the flag when throwing the exception. If the method allows `throws InterruptedException`, propagating the exception is usually clearer; when catching at a lifecycle boundary, you can restore the flag and exit.

### CPU Work Must Cooperatively Check the Flag

This is an **illustrative method** that can be placed inside a class, not a standalone runnable file:

```java
static long calculateUntilStopped() {
    long count = 0;
    while (!Thread.currentThread().isInterrupted()) {
        count++;
    }
    return count;
}
```

If you replace the condition with `while (true)` and have no interruptible waiting operations, calling `interrupt()` will not automatically throw `InterruptedException` in that CPU loop. Also, do not use `Thread.interrupted()` as a harmless check: it clears the flag, which can lose the signal for another layer.

## 3. `Future.cancel(false)`: Canceling the Observable Result Without Interrupting the Worker

`Future.cancel(boolean mayInterruptIfRunning)` attempts to cancel the Future:

```java
boolean accepted = future.cancel(false);
```

This is an **illustrative code snippet** assuming a `future` variable of type `Future<?>`. When `cancel(false)` succeeds on a running `FutureTask`, the Future transitions to the **canceled** state, but the worker execution **is not requested to be interrupted**; the worker can continue and even finish the computation. The final result can no longer be retrieved via `get()` on the canceled Future.

After a Future has been successfully canceled:

- `future.isCancelled()` returns `true`.
- `future.isDone()` returns `true` because the Future is in a terminal state per its contract.
- `future.get()` directly throws `CancellationException`.
- `isDone() == true` **does not prove** that the worker has exited and finished cleaning up.

If the task has already completed or was previously canceled, a subsequent `cancel(...)` call typically returns `false` per the `Future` contract. The return value depends on the state at the moment of the race, so **you must use the actual return value** rather than assuming cancellation always succeeds.

Operationally, `cancel(false)` is suitable when you no longer care about the result, want to prevent an unstarted task from running if the implementation supports it, or do not want to request interrupting a worker performing work that is difficult to cancel safely. It is **not** a mechanism for stopping a running worker.

## 4. `Future.cancel(true)`: Canceling the Future and Allowing an Interrupt Request

```java
boolean accepted = future.cancel(true);
```

With a standard `FutureTask` returned by `ExecutorService.submit(...)`, if cancellation succeeds and the task is running, the implementation will attempt to send an interrupt to the thread running it. However:

1. The Future can transition to canceled **before** the worker reacts or exits; the caller sees `CancellationException` from `get()` even while the worker is still cleaning up.
2. The worker may be executing code that does not support interruption or intentionally swallows interrupts; it may still keep running.
3. If the worker has already completed before the cancellation request, `cancel(true)` may return `false` and the Future retains the completed result.
4. Another API implementing `Future` may have its own cancellation rules. In particular, `CompletableFuture.cancel(true)` does not use the `true` parameter to interrupt the background task.

**`cancel(true)` means "allow an interrupt request if appropriate", not "kill the thread immediately".** The worker needs cooperative cancellation handling code to stop safely.

### Standalone Java 17 Example: `cancel(false)` and `cancel(true)`

Create the file `FutureCancelModesDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelModesDemo {
    public static void main(String[] args) throws Exception {
        withoutInterrupt();
        withInterrupt();
    }

    private static void withoutInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);

        try {
            Future<Integer> future = executor.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    return 42;
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(false);

            System.out.println("cancel(false) = " + accepted);
            System.out.println("cancelled = " + future.isCancelled());
            System.out.println("worker still waiting = "
                    + (finished.getCount() == 1));

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get = CancellationException");
            }

            release.countDown();
            finished.await();
            System.out.println("worker finished after release = true");
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }

    private static void withInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                    return "normal";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "worker handled interrupt";
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);
            finished.await();

            System.out.println("cancel(true) = " + accepted);
            System.out.println("worker saw interrupt = "
                    + sawInterrupt.get());
            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get = CancellationException");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac FutureCancelModesDemo.java
java FutureCancelModesDemo
```

Output:

```text
cancel(false) = true
cancelled = true
worker still waiting = true
get = CancellationException
worker finished after release = true
cancel(true) = true
worker saw interrupt = true
get = CancellationException
```

In the first branch, `started.await()` guarantees the task has started running; `release` is still closed, so the worker has not finished when `cancel(false)` is called. The Future reports canceled and `get()` throws `CancellationException`, yet the worker continues waiting until `main` releases `release`.

In the second branch, the worker waits on a latch that is never opened. `cancel(true)` requests an interrupt, `await()` throws `InterruptedException`, and the worker records the signal, restores the flag, and exits. Even though the worker returns the string `"worker handled interrupt"`, the caller **cannot retrieve that string** because the Future has been canceled. `finished.await()` is only used to wait for the worker's `finally` block to finish before reading `sawInterrupt`; for real operations, confirming that all workers have terminated may require a lifecycle mechanism such as `awaitTermination(...)`.

**Do not generalize the outcome of this example as a guarantee for all tasks:** the example intentionally uses `CountDownLatch`, worker code that cooperates with interruption, and a single-worker executor. A task blocked on non-interruptible I/O or stuck inside an external library may not stop when `cancel(true)` is called.

## 5. Directly Interrupting the Worker Does Not Necessarily Cancel the `Future`

If a worker receives an interrupt via `worker.interrupt()` or from an executor **without a `Future.cancel(...)` call**, the Future can end in two ways:

- The worker **lets `InterruptedException` escape the `Callable`**: the Future completes **with a failure**; `future.get()` throws `ExecutionException`, and `getCause()` is `InterruptedException`.
- The worker **catches `InterruptedException`, cleans up, and returns a value**: the Future can complete **successfully** and `get()` returns that value.

Both situations differ from a canceled Future, where `get()` throws `CancellationException` even if the worker is still partway through processing.

### Standalone Example: Interrupting a Worker Produces `ExecutionException`, Not Cancellation

Create the file `WorkerInterruptedFailureDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class WorkerInterruptedFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                new CountDownLatch(1).await();
                return "not reached";
            });

            started.await();
            executor.shutdownNow();

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("cause = "
                        + e.getCause().getClass().getSimpleName());
            }

            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Run:

```bash
javac WorkerInterruptedFailureDemo.java
java WorkerInterruptedFailureDemo
```

Output:

```text
cause = InterruptedException
cancelled = false
```

`shutdownNow()` requests interruption of the running worker. When interrupted, the `await()` call throws `InterruptedException` and the `Callable` does not catch it, so `FutureTask` records a **task failure**. The caller reading via `get()` sees `ExecutionException`, not `CancellationException`, because `future.cancel(...)` was never called.

An important point: `executor.shutdownNow()` **is not synonymous** with `future.cancel(true)`. It attempts to interrupt running tasks, while returning tasks that have never started; the Futures corresponding to queued tasks may not have been automatically transitioned to canceled. The application must manage the lifecycle and Futures of those tasks according to the specific executor contract.

## 6. Interrupting the Caller of `Future.get()` Is a Different Matter

Two threads can be involved with the same Future:

```text
Caller/main                               Executor worker
    │                                          │
    ├─ future.get() ───── waits ─────────────► runs Callable
    │
    └─ caller is interrupted
             │
             ▼
      get() throws InterruptedException
             │
      Future/worker may still be running
```

If the **caller** is interrupted while waiting on `get()`, `get()` can throw **`InterruptedException`** directly; there is no automatic implication that the worker was also interrupted or that the Future was canceled. Conversely, when the **worker** throws `InterruptedException` out of `Callable` while the Future is not canceled, the caller of `get()` sees **`ExecutionException`** wrapping `InterruptedException` in `getCause()`.

| What Happens | What the Caller of `Future.get()` Typically Sees |
|---|---|
| `Callable` returns normally | Value `T` |
| `Callable` throws an exception, Future not canceled | `ExecutionException` whose cause is the worker error |
| The waiting caller itself is interrupted | `InterruptedException` directly |
| Future is successfully canceled | `CancellationException` directly |
| `get(timeout, unit)` expires with no result yet | `TimeoutException` |

`InterruptedException`, `ExecutionException`, and `TimeoutException` are checked exceptions; `CancellationException` is an unchecked exception. A timeout on `get(timeout, unit)` **does not automatically cancel** the Future; if stopping is needed, the caller must explicitly decide whether to call `cancel(...)`.

Handling pattern (a snippet inside a method with a valid `future` and matching return type):

```java
try {
    return future.get(2, java.util.concurrent.TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true);           // Policy to proactively request cancellation.
    throw e;
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    future.cancel(true);           // Only when interrupting the caller must also cancel the task.
    throw e;
}
```

If the method's only job is to **wait** and the task should be allowed to continue even if the caller stops waiting, omit `future.cancel(true)` from the `InterruptedException` branch. There is no single policy that fits every case.

## 7. Why `Thread.stop()` Is Not the Solution

Java used to have `Thread.stop()` to stop a thread asynchronously. This API has been **deprecated** because it is dangerous. It can stop a thread at an unpredictable point, release monitors while object state is incomplete, break shared data invariants, and expose inconsistent state to other threads.

Example scenario to avoid:

```java
synchronized (account) {
    account.debit(100);
    // If forcibly stopped here, the related balancing operation may not have finished.
    ledger.recordDebit(100);
}
```

This is an **illustrative code snippet**; `account` and `ledger` are hypothetical objects. A mechanism that forces a stop between two steps can leave the system in a half-finished state; `synchronized` only ensures locks are managed according to JVM rules, not that a sequence of business updates becomes an atomic transaction.

Related mechanisms must also be understood properly:

- `Thread.suspend()`/`resume()` are dangerous obsolete APIs that can cause deadlocks; do not use them for lifecycle management.
- `Thread.stop()` should not be used to handle hung tasks; Java does not provide a general safe API to kill **an arbitrary thread** while preserving all invariants and resources.
- `System.exit(...)` terminates **the entire JVM**, not just a Future or worker. Unflushed data, in-flight requests, and many other resources are all affected.
- Terminating a process using OS tools or `Process.destroyForcibly()` operates at the **process boundary** and does not have the same meaning as `Thread.interrupt()`. If untrusted work requires the ability to be forcibly stopped, consider running it **in a separate process**, communicating over IPC, and explicitly defining timeouts, potential data loss, resource cleanup, retries, and monitoring.

**Architectural choice:** for Java work within the same JVM, prefer cooperative stopping points. For work that cannot be trusted to respond to interruption (such as third-party code that risks hanging), isolating it into a separate process/container provides a stronger kill boundary, though forcible termination still carries business and resource consequences.

## 8. `ExecutorService`: Stopping Submissions, Requesting Stop, and Awaiting Confirmation

Three common operations have distinct meanings:

1. `shutdown()` tells the executor to stop accepting new tasks, while already-submitted tasks are allowed to continue; it **does not wait** for them to finish.
2. `shutdownNow()` attempts to interrupt running tasks, stops processing queued tasks, and returns a list of unstarted tasks; this is a **best-effort** request.
3. `awaitTermination(timeout, unit)` waits for the executor to reach the terminated state within a bounded duration and returns a `boolean`; the **waiting thread** can receive `InterruptedException`.

A timed shutdown pattern (snippet placed inside a method where `executor` already exists):

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS)) {
        executor.shutdownNow();

        if (!executor.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS)) {
            System.err.println("Executor chưa dừng sau khi yêu cầu ngắt");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

The two 3-second intervals **are only examples**: choose values based on response time requirements, the risk of interruption, rollback capability, and data guarantees. This snippet does not prove that all workers have stopped if `awaitTermination` returns `false`. When there is data that must be preserved, the application must have a cleanup, checkpointing, or compensation plan.

If a worker holds a lock or connection, `try/finally` is needed inside the worker itself to clean up resources. Do not rely on a `shutdownNow()` call from the caller to fulfill that responsibility.

## 9. Choosing How to Interrupt or Cancel by Scenario

| Scenario | Appropriate Approach | What to Verify |
|---|---|---|
| Self-managed thread waiting on a queue/latch | `thread.interrupt()`, worker catches/propagates signal and exits | `join()` with timeout or a completion mechanism |
| Unstarted Future whose result is no longer needed | `future.cancel(false)` or a queued-task cancellation policy | Whether `cancel(...)` succeeded; do not read results from a canceled Future |
| Running Callable that supports interruption | `future.cancel(true)` if the business contract allows it | Resources/side effects are cleaned up, worker has stopped if required |
| Caller timed out waiting for result, but worker is still useful | `get(timeout, unit)`, return timeout status, no need to cancel | Avoid assuming a timeout means the task has stopped |
| Caller interrupted while calling `get()` | Propagate or restore the flag; decide separately whether to cancel the task | Caller and worker are two independent threads |
| Stopping an entire executor with a deadline | `shutdown()`, `awaitTermination`, then consider `shutdownNow()` | Unstarted tasks, still-hanging tasks, resources |
| Code does not respond to interrupts, risk of uncontrolled hang | Isolate into a separate process with timeouts and monitoring | Consequences of killing the process, retry/idempotency, partial data |

If a task modifies external data (database writes, HTTP calls, money transfers, etc.), canceling the Future **does not undo** side effects that have already occurred. You need to consider idempotency, transactions, service-side timeouts, compensation, and avoiding duplicate submissions on retry.

### Cooperative Stopping Points in a Worker

A consumer loop typically looks like this (illustrative pattern; `process` and `cleanup` are application-defined):

```java
static void runConsumer(java.util.concurrent.BlockingQueue<String> queue) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanup();
    }
}
```

If `process` also performs blocking operations or mutates shared state, it must have an appropriate error/cancellation contract. Catching `InterruptedException` and restoring the flag while **continuing a `while(true)` loop** often leads to a hot loop: the next interruptible wait may immediately throw the exception again.

Sometimes a task must complete a section that **cannot be safely interrupted** before terminating. The design should explicitly define that boundary, keep critical sections short, roll back where appropriate, and preserve the interrupt signal for the responsible layer. Do not arbitrarily swallow interrupts and hide lifecycle errors.

## 10. Misconceptions to Avoid

### "`isDone()` means the worker has finished running"

False. A canceled Future has `isDone() == true` and `isCancelled() == true` even though the worker may still be running or cleaning up. `isDone()` is only the terminal state of the **Future**, not confirmation that the entire worker has exited.

### "`cancel(true)` always throws `InterruptedException` in the caller"

False. `cancel(true)` returns a `boolean` to the caller. Once the Future is canceled, `get()` throws `CancellationException`. `InterruptedException` can occur **in the worker** at an interrupted wait operation, or **in the caller** if the caller itself is interrupted while waiting on an interruptible API.

### "`cancel(false)` only cancels tasks that have not started"

Incomplete. For a running `FutureTask`, `cancel(false)` can still cancel the **Future** without interrupting the worker; the worker keeps running, but its result can no longer be retrieved through that Future. Details can vary across implementations, so read the specific contract.

### "If the worker throws `InterruptedException`, the Future is definitely canceled"

False. If the `Callable` lets the exception escape and no cancel operation won the race, the Future can report a **failure** via `ExecutionException` whose cause is `InterruptedException`. If the worker catches the exception and returns, the Future can **succeed**.

### "`shutdownNow()` cancels all Futures"

False. `shutdownNow()` is an effort to stop the executor; it returns unstarted tasks and is not automatically equivalent to calling `cancel(true)` on every Future. Managing Futures still held externally is the responsibility of the orchestration layer.

### "Interruption implies rollback"

False. Interruption acts on thread control flow, not as a transaction mechanism. A task that has already written data, sent notifications, or created files may have already produced side effects before the signal arrived.

### "Forcibly stopping a Thread makes the system safer"

False. Stopping at an arbitrary point can break invariants and leave resources half-cleaned. A safer approach is cooperative stopping; when you cannot control the code, change the execution boundary (for example, a separate process) and address process recovery explicitly.

## 11. Checklist for Handling Interruption and Cancellation in Real Applications

Before deciding to cancel a piece of work, answer the following:

1. **Who is in control?** Caller, worker, Future, or executor? Which thread actually receives the interrupt?
2. **Do you want to stop waiting or stop the work?** Does a caller timeout mean the task is no longer valuable?
3. **Is the task cooperative?** Does it have `isInterrupted()` checks, interruptible blocking APIs, or its own stop flag?
4. **What result is reported?** Future return value, `ExecutionException`, `CancellationException`, or does the caller see `InterruptedException`?
5. **Has cleanup finished?** Is there a `finally` block, `join`, `awaitTermination`, latch, or reliable completion signal?
6. **What side effects have occurred?** Do you need rollback, idempotency, compensation, or duplicate-retry protection?
7. **What if the task hangs forever?** Is there an appropriate deadline and process boundary instead of relying on `Thread.stop()`?

**Technical conclusion:** `Thread.interrupt()` is a **cooperative signal sent to a thread**; `Future.cancel(false/true)` is a **request to change the Future's state**, where `true` may allow interrupting the worker depending on the implementation; `shutdownNow()` is only an effort to stop the executor; forcible termination requires a separate boundary and carries risks. Always distinguish between the **stop request signal**, the **result state of the Future**, and **proof that the work has actually finished**.
