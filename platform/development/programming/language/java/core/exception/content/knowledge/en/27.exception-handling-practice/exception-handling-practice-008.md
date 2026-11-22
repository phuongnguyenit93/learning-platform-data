# Error and Interruption Handling in ExecutorService Tasks (Java Core)

## 1. Practice Objectives

`ExecutorService` executes tasks via a thread pool, but each call such as `execute()`, `submit()`, `Future.get()`, `cancel(true)`, and `shutdownNow()` has a **different exception and interruption handling contract**. Misunderstanding those contracts can cause a program to lose track of errors, fail to stop workers, or report false success after a task has failed.

After this lesson, you should be able to:

- Choose `execute()` or `submit()` based on how the caller needs to observe errors and results.
- Distinguish **task errors** from **errors of the thread waiting for the result**.
- Accurately observe `ExecutionException`, `CancellationException`, `InterruptedException`, and `RejectedExecutionException`.
- Design tasks that cooperate with cancellation via `interrupt()`, avoiding swallowing `InterruptedException` and continuing execution.
- Cancel a `Future` according to its contract without confusing the "future is cancelled" state with "all side effects have stopped."
- Shut down a pool using `shutdown()`, `awaitTermination()`, and `shutdownNow()` in a bounded sequence.
- Write tests with latches/timeouts to verify failure and cancellation paths without relying solely on `Thread.sleep`.

**General principle:** `ExecutorService` manages scheduling and execution; **it does not automatically turn an exception into a valid business result, does not automatically roll back, and does not forcibly stop every task immediately after an interrupt**. The task, the caller, and the pool owner must have clear responsibilities.

## 2. Task Lifecycle Overview

A common execution flow:

```text
Caller thread
   |
   +-- executor.execute(runnable) --------> worker thread
   |                                          |
   |                                          +-- normal return
   |                                          |
   |                                          +-- throws unchecked exception
   |                                               (worker exits abnormally;
   |                                                uncaught handler may observe)
   |
   +-- Future<T> f = executor.submit(task) -> worker thread
                                              |
                                              +-- normal return
                                              |     -> Future result
                                              |
                                              +-- throws exception
                                              |     -> Future exceptional outcome
                                              |
                                              +-- interrupted/cancelled
                                                    -> cancellation contract
   |
   +-- f.get() -> value / ExecutionException /
                  InterruptedException / CancellationException
```

Two common misconceptions:

1. **The task runs on the worker's call stack.** A `try/catch` around `submit()` in the caller does not automatically catch errors that occur later in the worker.
2. A `Future` is a **completion observation channel**, not necessarily a forced execution stop control. The caller must observe `get()`, `isCancelled()`, policy, or separate state; do not infer from a single boolean that all work has been undone.

A pool can reuse a thread after a successful task. If a task run via `execute` throws an unchecked exception and exits uncaught, the worker may terminate abnormally and the executor handles the worker lifecycle according to its implementation; do not design logic that relies on the thread name or identity remaining unchanged.

## 3. `execute()` and `submit()` Report Errors Differently

### `execute(Runnable)`

`execute()` has a `void` return signature. If `Runnable.run()` throws an unchecked exception that is not handled by the task itself, the error may go to the executing thread's **uncaught exception handler** (for a typical `ThreadPoolExecutor`), or another error-reporting mechanism determined by the executor implementation.

```java
executor.execute(() -> {
    throw new IllegalStateException("work failed");
});
```

This is a code snippet with an already-declared `executor` variable of type `ExecutorService`. A handler in the caller like the following **does not catch** errors occurring asynchronously inside the task:

```java
try {
    executor.execute(() -> doWork());
} catch (RuntimeException ex) {
    // May catch a task submission error at the call site,
    // does not automatically catch subsequent errors inside doWork().
}
```

This is a code snippet with `doWork()` defined by the application. If the pool has already shut down or rejects the task, `execute()` may throw `RejectedExecutionException` on the **submitting** thread. That is different from an exception thrown once the worker has started running.

### `submit(Runnable/Callable)`

`submit()` returns a `Future`. With common executors created from `Executors` or `ThreadPoolExecutor`, exceptions thrown inside the task are recorded in the **Future**. They do not necessarily pass through the thread's uncaught exception handler in the same way as `execute()`.

```java
Future<Integer> future = executor.submit(() -> {
    throw new IllegalArgumentException("bad computation");
});
```

This is a code snippet that requires importing `java.util.concurrent.Future`. When the caller invokes `future.get()`, the task's exception is surfaced as an `ExecutionException` whose `getCause()` contains the original error:

```java
try {
    Integer result = future.get();
    use(result);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

This is a code snippet inside a `void` method where `future`, `use`, and `handleTaskFailure` are defined, with `java.util.concurrent.ExecutionException` imported. **Do not ignore the returned `Future`** when the business logic needs to know whether the task succeeded or failed; if nothing reads or observes the result, errors can become very difficult to detect.

`submit(Runnable)` returns a `Future<?>` whose `get()` returns `null` if the task completes normally. `submit(Runnable, result)` uses the caller-supplied `result` value when the `Runnable` completes normally. `submit(Callable<T>)` allows returning a value or throwing checked exceptions per `Callable.call()`.

## 4. Comparison Table of Key Error Signals

| Type | Where it appears | Meaning |
| --- | --- | --- |
| `IllegalStateException`/`IOException` inside task | Worker call stack | Business, state, or dependency error of the task |
| `ExecutionException` | Thread calling `Future.get()` | Task completed abnormally; inspect `getCause()` |
| `InterruptedException` from `Future.get()` | **Waiting thread**, not automatically from the task | Caller was interrupted while waiting |
| `CancellationException` from `Future.get()` | Thread reading the `Future` | `Future` was cancelled; does not guarantee side effects were rolled back |
| `RejectedExecutionException` at `execute/submit` | Submitting thread | Executor did not accept the task according to policy |
| `TimeoutException` from `get(timeout, unit)` | Waiting thread | Wait timed out; task may still be running |
| `InterruptedException` from `sleep/take/await` in worker | Worker task | Worker received an interrupt request and must decide to stop |
| `CompletionException` from `CompletableFuture.join()` | Thread observing `CompletableFuture` | Wrapper for exceptional completion of a `CompletableFuture` pipeline |

Note that `Future.get()` and `CompletableFuture.join()` differ in wrapping and interruption behavior. Do not funnel everything through a single `catch (Exception)`, log it, and continue as if it succeeded.

## 5. Complete, Runnable Java 17+ Example

The following example intentionally separates four scenarios. Every pool is closed in `finally`, all wait points are bounded in the coordination logic, and `CountDownLatch` establishes ordering without guessing when the scheduler will run a thread.

- **executeFailure:** an `execute` task throws an unchecked exception; `ThreadFactory` configures an uncaught handler to observe it.
- **submitFailure:** a `submit` task throws an exception; the caller reads the cause from `ExecutionException`.
- **cancelCooperatively:** the caller calls `Future.cancel(true)`; the sleeping worker catches `InterruptedException`, restores the flag, and exits.
- **interruptWaiter:** another thread waits on `Future.get()` and gets interrupted; the task in the pool continues waiting on its own and proceeds once the wait condition is released.

Save the file **`ExecutorErrorInterruptDemo.java`**:

```java
import java.util.concurrent.*;

public class ExecutorErrorInterruptDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void stop(ExecutorService pool) throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS), "shutdown timeout");
        }
    }

    static void executeFailure() throws InterruptedException {
        CountDownLatch observed = new CountDownLatch(1);
        ThreadFactory factory = runnable -> {
            Thread thread = new Thread(runnable, "execute-worker");
            thread.setUncaughtExceptionHandler((t, error) -> {
                System.out.println("EXECUTE_HANDLER: "
                        + error.getClass().getSimpleName());
                observed.countDown();
            });
            return thread;
        };
        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });
            check(observed.await(5, TimeUnit.SECONDS), "handler did not run");
            System.out.println("EXECUTE_OBSERVED: true");
        } finally {
            stop(pool);
        }
    }

    static void submitFailure() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = pool.submit(() -> {
                throw new IllegalArgumentException("submit failed");
            });
            try {
                future.get();
                throw new AssertionError("expected failure");
            } catch (ExecutionException ex) {
                System.out.println("SUBMIT_CAUSE: "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            stop(pool);
        }
    }

    static void cancelCooperatively() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    boolean cleared = !Thread.currentThread().isInterrupted();
                    Thread.currentThread().interrupt();
                    System.out.println("CANCEL_WORKER: cleared=" + cleared
                            + " restored="
                            + Thread.currentThread().isInterrupted());
                } finally {
                    finished.countDown();
                }
            });
            check(started.await(5, TimeUnit.SECONDS), "worker not started");
            boolean cancelled = future.cancel(true);
            check(finished.await(5, TimeUnit.SECONDS), "worker did not finish");
            System.out.println("CANCEL_REQUESTED: " + cancelled);
            try {
                future.get();
                throw new AssertionError("expected cancellation");
            } catch (CancellationException expected) {
                System.out.println("CANCEL_GET: CancellationException");
            } catch (ExecutionException unexpected) {
                throw new AssertionError(unexpected);
            }
        } finally {
            stop(pool);
        }
    }

    static void interruptWaiter() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch waiterStarted = new CountDownLatch(1);
        try {
            Future<String> future = pool.submit(() -> {
                workerStarted.countDown();
                release.await();
                return "result";
            });
            check(workerStarted.await(5, TimeUnit.SECONDS),
                    "worker not started");
            Thread waiter = new Thread(() -> {
                waiterStarted.countDown();
                try {
                    future.get();
                    throw new AssertionError("expected waiter interruption");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("WAITER: restored="
                            + Thread.currentThread().isInterrupted()
                            + " taskDone=" + future.isDone());
                } catch (ExecutionException ex) {
                    throw new AssertionError(ex);
                }
            }, "waiter");
            waiter.start();
            check(waiterStarted.await(5, TimeUnit.SECONDS), "waiter not ready");
            waiter.interrupt();
            waiter.join(5_000);
            check(!waiter.isAlive(), "waiter did not stop");
            System.out.println("TASK_NOT_CANCELLED: " + !future.isCancelled());
            release.countDown();
            try {
                System.out.println("TASK_RESULT: " + future.get());
            } catch (ExecutionException ex) {
                throw new AssertionError(ex);
            }
        } finally {
            release.countDown();
            stop(pool);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        executeFailure();
        submitFailure();
        cancelCooperatively();
        interruptWaiter();
        System.out.println("DEMO: PASS");
    }
}
```

Run with JDK 17 or later from the directory containing the file:

```bash
javac -encoding UTF-8 ExecutorErrorInterruptDemo.java
java ExecutorErrorInterruptDemo
```

**Verified standard output:**

```text
EXECUTE_HANDLER: IllegalStateException
EXECUTE_OBSERVED: true
SUBMIT_CAUSE: IllegalArgumentException
CANCEL_WORKER: cleared=true restored=true
CANCEL_REQUESTED: true
CANCEL_GET: CancellationException
WAITER: restored=true taskDone=false
TASK_NOT_CANCELLED: true
TASK_RESULT: result
DEMO: PASS
```

### How to Read Each Case

1. `EXECUTE_HANDLER` proves that an unchecked exception escaped from a `Runnable` run via `execute()` and was observed by the custom handler. Printing the default stack trace is unnecessary, keeping the output stable.
2. `SUBMIT_CAUSE` shows that `Future.get()` does not throw `IllegalArgumentException` directly, but wraps it in `ExecutionException` with a cause.
3. `CANCEL_WORKER` confirms that the sleeping worker reacted to the interrupt. `Thread.sleep` threw `InterruptedException` and cleared the flag; the code verified `cleared=true` and then called `interrupt()` to restore the flag.
4. `CANCEL_REQUESTED: true` indicates that the cancellation request was accepted for the running `Future` in the demo scenario. **It is not a guarantee that every `cancel(true)` returns `true` or that every task will stop.**
5. `CANCEL_GET` receives `CancellationException` directly after the `Future` has been cancelled; there is no successful result to read.
6. `WAITER` shows that the thread waiting on `get()` was interrupted and restored its flag; at that moment, the worker's `Future` had not yet completed.
7. `TASK_NOT_CANCELLED: true` and `TASK_RESULT: result` prove that **interrupting a thread waiting on a `Future` does not automatically cancel the underlying task**.
8. `DEMO: PASS` appears after all four parts have completed their verification paths and the pools have been requested to shut down.

The example uses a 5-second timeout to detect cases that do not behave as expected. On an overloaded machine or in an unusually constrained environment, real-time tests may still need a larger timeout; do not treat the 5-second number itself as a Java guarantee. The program does not access the network or a database and uses no real business data.

## 6. `ThreadFactory` and `UncaughtExceptionHandler`

For `execute()` and workers that do not catch exceptions, a `Thread.UncaughtExceptionHandler` configured via `ThreadFactory` can help record failures:

```java
ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable, "worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        reportUnexpectedFailure(error);
    });
    return thread;
};
```

This is a code snippet requiring `ThreadFactory` to be imported and `reportUnexpectedFailure` to be defined. It is suitable when tasks run through the `execute` channel and the executor implementation allows unchecked exceptions to escape the worker.

**You cannot assume that an uncaught handler will record every error from every `submit()` task.** Implementations typically wrap tasks submitted via `submit` in a `FutureTask` and store the `Throwable` as the exceptional outcome. Relying only on the handler can cause you to miss errors inside a `Future`.

Some executor frameworks have their own error-reporting pipelines. Do not force a `ThreadFactory` pattern onto every library-provided `ExecutorService` without reading the contract of that specific implementation.

Do not let the handler log raw exceptions from dependencies that contain passwords/tokens/PII, or throw another exception that obscures operational diagnostics. Choose safe event codes, operation names, correlation IDs, and an access-controlled log destination.

## 7. Observing `Future.get()` Results Properly

Caller handling pattern:

```java
try {
    Result value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (CancellationException ex) {
    recordCancelled();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    handleTaskFailure(cause);
}
```

This is a **code snippet inside a `void` method**, requiring `Result`, the application methods, and imports from `java.util.concurrent`.

- `InterruptedException`: the **waiting thread** received an interrupt request. Catching and ignoring it and calling `get()` again can break deadlines or shutdown.
- `CancellationException`: the `Future` was cancelled. The caller must report a CANCELLED status rather than treating it as success or a normal computation error.
- `ExecutionException`: the task terminated abnormally due to `cause`. Depending on the cause type, the policy may be validation failure, dependency failure, bug, or retryable failure.
- Normal `get()` result: the `Future` completed successfully according to the task's contract, though that **does not** by itself prove every external side effect was safely committed if the task was written without proper checks.

With `future.get(timeout, TimeUnit.SECONDS)`, you must also handle `TimeoutException`. A **wait** timeout does not automatically cancel the `Future`; if you want to request task cancellation, the caller must decide whether to call `cancel(true)` or another appropriate cancellation mechanism, along with a side-effect reconciliation strategy.

### Failing to Observe a `Future` Is a Form of Losing Errors

```java
executor.submit(() -> sendReport());
```

This is a code snippet with `sendReport` defined. If nothing retains or reads the `Future`, task failures can be hard to spot, especially when there is no dedicated logging inside the task. Consider `Future.get()`, `ExecutorCompletionService`, monitoring callbacks, or a job-result mechanism when the system needs status confirmation.

If the application intentionally uses *fire-and-forget*, it must still have a failure-observation policy and must not confuse "task submitted" with "task completed."

## 8. Handling `InterruptedException` Inside a Worker

Interruption is a **cooperative request** mechanism. When a caller invokes `thread.interrupt()` or `future.cancel(true)`, the worker can receive the signal via the interrupt flag or via an exception from a blocking API.

Blocking APIs such as `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, or `Semaphore.acquire` can throw `InterruptedException`. Many such APIs **clear the interrupt flag when throwing**. Therefore, the following handler is dangerous:

```java
while (true) {
    try {
        Job job = queue.take();
        process(job);
    } catch (InterruptedException ignored) {
        // Wrong: treats it as if no stop request ever occurred.
    }
}
```

This is a code snippet illustrating a bug, with `Job`, `queue`, and `process` defined by the application. After the flag is cleared, the loop can go right back to `take()` and block again, preventing the pool from stopping as intended.

If the method can declare the checked exception:

```java
Job receive(BlockingQueue<Job> queue) throws InterruptedException {
    return queue.take();
}
```

This is a code snippet requiring `BlockingQueue` to be imported and `Job` to be defined. **Propagating** the exception preserves the signal for the managing layer.

In `Runnable.run()`, checked exceptions cannot be declared:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            process(queue.take());
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

This is a class snippet with `queue`, `process`, and `releaseResources`. It **restores the flag and exits the task**, while cleanup is always attempted.

**Restoring the flag and continuing a `while(true)` loop with no exit condition** is also wrong: the next blocking call may immediately throw and clear the flag, the handler sets it again, creating a *busy loop*. Always combine the interrupt policy with lifecycle control.

You do not have to restore the flag everywhere if `InterruptedException` is **propagated according to contract** or that layer truly owns and finishes handling the cancellation request. The problem is swallowing the signal unknowingly.

## 9. Difference Between `Thread.interrupted()` and `isInterrupted()`

When writing a worker loop:

- `Thread.currentThread().isInterrupted()` reads the current thread's status **without clearing the flag**.
- `Thread.interrupted()` is a static method that reads the **current thread's status and clears the flag**.

This snippet can accidentally erase the signal:

```java
if (Thread.interrupted()) {
    logSomething();
}
// Subsequent code may no longer see the interrupted flag.
```

This is a code snippet with `logSomething` defined by the application. If the goal is to check while preserving the cancellation request, use `isInterrupted()`.

However, the interrupt flag **is not a kill command**. If a task only performs CPU work without calling interruptible APIs, it must check the flag periodically at appropriate points. For example:

```java
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processNextChunk();
}
```

This is a code snippet inside a method with `hasMoreWork` and `processNextChunk`. Check frequently enough to respond to cancellation without doing it on every tiny operation.

If a task performs I/O that does not respond quickly to interrupts, use timeouts, the resource's close/cancel API, or an appropriate dependency contract. Do not rely solely on `interrupt()` to promise a hard deadline.

## 10. `Future.cancel(true)` Is a Request, Not a Forced Stop

`Future.cancel(boolean mayInterruptIfRunning)` requests cancellation of the task if it has not yet completed. `true` allows the implementation to attempt interrupting the running thread; `false` does not request interrupting a running task. The actual outcome depends on timing and the implementation.

Key points to understand:

1. If the `Future` is already done, `cancel(...)` normally does not change its state.
2. For a still-running task, `cancel(true)` may set the `Future` state to cancelled and send an interrupt to the worker.
3. **`Future.isCancelled() == true` does not prove the worker has stopped executing instructions at that moment.**
4. A task that swallows `InterruptedException` can keep running after the `Future` has been cancelled.
5. A side effect already written to a DB or sent over the network **does not automatically roll back** upon cancellation.
6. `future.get()` after cancellation throws `CancellationException` directly; it is not wrapped in `ExecutionException`.

Pattern:

```java
boolean accepted = future.cancel(true);
if (accepted) {
    recordCancellationRequested();
}
```

This is a code snippet with `future` and `recordCancellationRequested`. The method name intentionally uses **Requested**: the caller should separate requesting cancellation from confirming that the task has reached a safe terminal state.

For tasks involving payments, uploads, sending emails, writing files, or committing to a database, you need a dedicated idempotency/transaction/compensation policy. Do not automatically retry the entire task after a `Future` is cancelled without knowing whether the operation partially executed.

## 11. Interrupting a Waiting Caller Does Not Cancel the Worker

A commonly misunderstood case:

```java
Future<String> future = executor.submit(this::load);
String result = future.get();
```

This is a code snippet in a class with a matching `load()` method. If the **caller thread** is interrupted while `get()` is blocking, `get()` can throw `InterruptedException`. However, that **does not automatically call `future.cancel(true)`** and does not automatically inform the worker that the caller no longer wants the result.

Actual sequence:

```text
worker: waiting on dependency ............. -> completes later
caller: calls future.get()
another thread: interrupt(caller)
caller: InterruptedException -> stops waiting
worker: not automatically interrupted by that event
```

In the demo, the caller-waiter exited with `taskDone=false`, yet the underlying `Future` could still return `result` after `main` released the latch.

If cancelling the underlying task is the desired policy, the caller can **consider**:

```java
try {
    return future.get();
} catch (InterruptedException ex) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    throw ex;
}
```

This is a **method snippet** declaring `throws InterruptedException` with a matching return type. Calling `cancel(true)` makes sense when the task truly belongs to the caller's cancellation scope and the implementation supports interruption. In a system where work is shared across multiple requests, automatically cancelling the underlying `Future` when one caller stops waiting **can affect other users**; ownership must be decided explicitly.

## 12. `shutdown()`, `shutdownNow()`, and `awaitTermination()`

Three APIs serve the executor lifecycle:

| API | Basic behavior |
| --- | --- |
| `shutdown()` | Rejects new tasks, allows already-submitted tasks to proceed per contract |
| `shutdownNow()` | Attempts to stop running tasks, typically via interrupt, and returns the list of tasks that had not started |
| `awaitTermination(timeout, unit)` | **Calling thread** waits for the executor to terminate or time out; can throw `InterruptedException` |

`shutdown()` does not wait for all tasks to finish. `shutdownNow()` is **best effort**; tasks that ignore interrupts may keep running. The list returned by `shutdownNow()` is not "all failed tasks"; it primarily describes queued tasks that had not started per contract.

Common lifecycle pattern (snippet inside the method that owns the executor):

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            reportPoolDidNotTerminate();
        }
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This snippet assumes `executor`, `reportPoolDidNotTerminate`, and a `TimeUnit` import. The two 30-second values only illustrate policy; choose timeouts based on SLA and task characteristics.

Important:

- `shutdownNow()` does not guarantee that all workers have exited.
- `awaitTermination()` being interrupted is a signal for the **caller managing shutdown**; restore the flag if the handler does not propagate the checked exception.
- For a pool that did not stop, report the status clearly instead of printing "shutdown complete."
- Only shut down a pool when the current component **owns** it; do not close a framework's shared executor on every request.

## 13. Managing a Pool with `try/finally`

A short-lived scope can do:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    Future<Result> first = executor.submit(this::firstJob);
    Future<Result> second = executor.submit(this::secondJob);
    return combine(first.get(), second.get());
} finally {
    executor.shutdown();
}
```

This is a **code snippet** inside a method with an appropriate checked-exception contract and application methods/types. It guarantees **issuing a shutdown request** even if an exception occurs. However, `shutdown()` **does not wait** for workers to finish. If waiting for termination or cancelling still-running tasks is required, use the additional `awaitTermination`/`shutdownNow` pattern.

Some designs use an executor as a long-lived field, initialized at startup and shut down during application lifecycle teardown; do not create a new pool per order and forget to close it. With a shared executor, ownership and shutdown boundaries are even more critical.

Newer JDKs may offer additional lifecycle utilities, but the examples here use only APIs guaranteed to exist in **Java 17**. Do not rely on `ExecutorService.close()` as a universal method on Java 17.

## 14. `RejectedExecutionException` Is Not a Task-Body Error

If the pool is already shut down or the queue/rejection policy refuses additional tasks:

```java
try {
    Future<?> future = executor.submit(task);
    track(future);
} catch (RejectedExecutionException ex) {
    recordNotScheduled();
}
```

This is a code snippet with `task`, `track`, `recordNotScheduled`, and corresponding imports.

`RejectedExecutionException` occurs at **task submission time**, not proving that the task's logic ran or failed. The caller should distinguish:

- **Not accepted:** not taken by the executor; may be routed to another queue per policy.
- **Accepted but failed:** task was submitted and completed abnormally; inspect the `Future`.
- **Accepted then cancelled:** `Future` was cancelled; task may have started and produced side effects.
- **Still running:** final outcome is not yet known.

If a special `RejectedExecutionHandler` such as `CallerRunsPolicy` is configured, a task may execute on the **caller's thread** when rejected from entering the pool (under the policy's conditions). In that case, assuming "every task runs on a separate worker thread" is also false. Always understand the policy and configuration of the executor in use.

Do not retry `submit()` indefinitely when the executor rejects: this can cause a hot loop, increase load, or create reverse backpressure. Solutions need a retry budget and clear responsibility boundaries.

## 15. `invokeAll` and `invokeAny`: Observing Multiple Tasks

Beyond `submit()`, `ExecutorService` provides batch execution APIs.

### `invokeAll(...)`

`invokeAll(tasks)` submits multiple tasks and waits for all to complete according to the overload's contract. It returns a list of `Future`s. **A `Future` can complete exceptionally while `invokeAll` still returns the list.** A caller that wants to detect task errors must call `get()` on each `Future`:

```java
List<Future<String>> futures = executor.invokeAll(tasks);
for (Future<String> f : futures) {
    try {
        consume(f.get());
    } catch (ExecutionException ex) {
        recordTaskFailure(ex.getCause());
    }
}
```

This is a code snippet with `tasks` as a collection of `Callable<String>`, application methods, and imports from `java.util.concurrent` and `java.util.List`; the enclosing method declares or handles `InterruptedException`. With the timeout overload, tasks not completed when time expires may be cancelled per contract; do not read every `Future` as if all succeeded.

### `invokeAny(...)`

`invokeAny(tasks)` seeks **one task that completes successfully** and may cancel the remaining tasks per contract. If no task succeeds, the caller may receive `ExecutionException`; `InterruptedException` from the caller must also be handled. The timeout overload may throw `TimeoutException`.

Do not infer that tasks requested to cancel have rolled back. If those `Callable`s produce side effects, running multiple copies in parallel and taking the first success requires idempotency design, not just `invokeAny`.

## 16. `ExecutorCompletionService` for Collecting Results in Completion Order

When multiple tasks finish at different times, `ExecutorCompletionService<T>` can be used:

```java
ExecutorCompletionService<String> completion =
        new ExecutorCompletionService<>(executor);
completion.submit(this::jobA);
completion.submit(this::jobB);

for (int i = 0; i < 2; i++) {
    Future<String> done = completion.take();
    try {
        use(done.get());
    } catch (ExecutionException ex) {
        handleTaskFailure(ex.getCause());
    }
}
```

This is a code snippet with `jobA`, `jobB`, `use`, and `handleTaskFailure` defined by the application. The method must handle or declare `InterruptedException`. `take()` waits for a completed `Future`; calling `get()` on that `Future` reveals the result or error. Do not forget to count/track submitted tasks to avoid waiting for more iterations than actual tasks.

If `take()` is interrupted, that applies to the result-collecting thread; the policy for cancelling underlying tasks must be decided separately. A `Future` becoming done does not guarantee success, because the done state includes result, error, and cancellation.

## 17. Catching Exceptions Inside a Task: When Should You Do It?

You do not always have to let a task throw exceptions. You can handle them inside the task itself if it **has a valid recovery policy**, such as bounded retry of a network operation without duplicate side effects, turning a cache-read error into a valid fallback value, or cleaning up resources:

```java
Callable<Result> task = () -> {
    try {
        return remoteCall();
    } catch (KnownTemporaryFailure ex) {
        return validFallback();
    }
};
```

This is a code snippet with custom-defined `Result`, `KnownTemporaryFailure`, `remoteCall`, and `validFallback`. If the fallback is genuinely valid per contract, the `Future` succeeding with the fallback value is intentional. If the fallback only hides an error, this is a **false success**.

Avoid doing this:

```java
Callable<Boolean> task = () -> {
    try {
        chargeAccount();
        return true;
    } catch (Exception ignored) {
        return false;
    }
};
```

This is a code snippet with custom-defined `chargeAccount`, intentionally illustrating a mistake. If the payment committed and then the response was lost, returning `false` does not prove the account was not charged. A caller retry could create a duplicate transaction.

If a task can throw checked exceptions, `Callable.call()` already permits that. There is no need to wrap every exception in `RuntimeException` just to fit a signature like `Runnable.run()`.

## 18. Propagating Errors via `Future` Does Not Undo Side Effects

A task might perform:

```java
Callable<String> task = () -> {
    database.commit();
    notification.send();
    return "DONE";
};
```

This is an illustrative snippet requiring `database`, `notification`, and their contracts to be defined. If `commit()` succeeds but `notification.send()` throws an exception, `Future.get()` reports failure, yet the database **may already have committed**.

When an error occurs after an operation with side effects:

1. Know which steps definitely completed and which are indeterminate.
2. Use transactions when a single resource supports them; do not treat `Future` cancellation as a rollback.
3. Across two systems, consider outbox/compensation or reconcilable intermediate states.
4. Use bounded retries with idempotency keys where appropriate.
5. Record non-sensitive error codes and correlation IDs for investigation.
6. Do not treat `ExecutionException` as proof that "the task did nothing."

This is why exception/cancellation handling must be tied to the business contract, not merely to the `Throwable` type.

## 19. `ThreadPoolExecutor.afterExecute`: A Specialized Observation Point

When you need to monitor many tasks at the executor level, `ThreadPoolExecutor` provides the `afterExecute(Runnable r, Throwable t)` hook. However, **never assume `t` is always non-null when a `submit()` task fails**: with `FutureTask`, the exception may have been captured inside the `Future`.

Conceptual pattern:

```java
@Override
protected void afterExecute(Runnable runnable, Throwable error) {
    super.afterExecute(runnable, error);
    if (error == null && runnable instanceof Future<?> future
            && future.isDone()) {
        try {
            future.get();
        } catch (CancellationException cancelled) {
            recordCancelled();
        } catch (ExecutionException failed) {
            recordTaskFailure(failed.getCause());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    } else if (error != null) {
        recordTaskFailure(error);
    }
}
```

This is a **snippet inside a `ThreadPoolExecutor` subclass**, not a standalone program; it requires imports and error-recording methods. The hook must be brief, must not block indefinitely, and must not introduce uncontrolled side effects. Checking `future.isDone()` avoids calling `get()` on an incomplete `Future` in non-standard implementations; in normal cases the task has just finished.

This is an advanced technique. For smaller applications, **retaining and observing the `Future`** is usually simpler than subclassing the executor. Also control error logging in the hook to avoid duplicating caller logs or exposing sensitive dependency messages.

## 20. Testing Error and Interruption Paths Deterministically

To test executors, use `CountDownLatch`, `Future`, thread-safe counters, `AtomicBoolean`, and timeouts rather than `Thread.sleep(100)` and guessing what a thread did. A test can place two latches:

- `started`: the worker has reached the waiting/interruptible point.
- `finished`: the worker has passed through cleanup and is about to exit.

Minimal example:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(1);

Future<?> task = executor.submit(() -> {
    started.countDown();
    try {
        Thread.sleep(60_000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        finished.countDown();
    }
});

if (!started.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("task did not start");
}
task.cancel(true);
if (!finished.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("task did not finish");
}
```

This is a **code snippet** inside a method with `executor` and the corresponding imports, declaring or handling `InterruptedException`. It does not actually sleep for a minute: `cancel(true)` causes the worker to react to the interrupt in the demo. However, if another executor implementation or task does not cooperate, the wait will time out and the test will fail.

**Tests should not rely solely on `Future.isDone()` to assert that the worker has exited:** after cancellation, the `Future` may report done earlier than the worker stops. Use a latch or signal from the worker when you genuinely need to prove that cleanup has run.

## 21. Practice Testing Matrix

| Case | What to verify |
| --- | --- |
| `execute` with `Runnable` throwing unchecked exception | Executor's uncaught handler/monitor receives the error per contract |
| `submit` with `Callable` throwing exception | `get()` throws `ExecutionException`, cause is the task error |
| `submit` succeeds | `get()` returns the expected value |
| `submit(Runnable)` succeeds | `get()` typically returns `null` |
| Task `cancel(true)` while in `sleep` | Task is requested to interrupt; worker cooperates and runs cleanup |
| Worker swallows `InterruptedException` | Test detects the worker keeps running contrary to intent |
| Caller `get()` is interrupted | Caller handles interruption, underlying `Future` is not automatically cancelled |
| `Future` is cancelled | `get()` throws `CancellationException` |
| Caller `get(timeout)` expires | Throws `TimeoutException`, task is not automatically cancelled |
| `submit` after executor is shut down | Caller receives rejection per policy |
| `shutdownNow()` with uncooperative worker | Do not assume pool stops immediately; check termination timeout |
| `invokeAll` with one failing task | Iterate over `Future`s and inspect causes, not just the returned list |
| Task commits then fails later | No blind retry; side-effect state matches contract |
| Cleanup itself throws an exception | Cause/suppressed and state are recorded accurately |
| `afterExecute` when `submit` fails | Does not depend on `Throwable t` being non-null |
| Shared executor shut down by mistake | Test ownership/lifecycle, do not close another component's pool |

These tests must have **time bounds** and cleanup. A poorly written worker may refuse to stop; never allow the entire test suite to hang indefinitely. For uncooperative threads, consider test isolation and process-level timeout mechanisms.

## 22. Common Mistakes in Production Code

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Calling `submit()` and discarding the `Future` | Task fails but nothing observes it | Retain the `Future` or use a result-reporting system |
| `catch (Exception ignored)` in task | Hides validation errors, bugs, and interrupts | Classify, handle only errors with a clear policy |
| `catch (InterruptedException ex) {}` | Loses the cancel signal | Propagate or restore and exit |
| Restoring flag then looping back into `while(true)` | Hot loop, task does not stop | `return`/`break` or check the flag |
| Calling `cancel(true)` then claiming "rolled back" | Side effects may already have occurred | Transaction/idempotency/reconciliation |
| Interrupted during `get()` then assuming task is cancelled | Worker may still be running | Decide underlying cancellation based on ownership |
| Calling only `shutdown()` and printing "all tasks done" | `shutdown()` does not wait for termination | `awaitTermination` with timeout |
| Calling `shutdownNow()` then expecting immediate termination | Best effort; tasks may not cooperate | Check termination and report failure |
| Retrying every `ExecutionException` | Bugs and permanent errors also get retried | Classify `getCause()` |
| Using `get(timeout)` without managing the task | Caller times out while task continues | Appropriate cancel/deadline policy |
| Relying only on uncaught handler to monitor `submit` | `FutureTask` captures the error, handler never sees it | Observe the `Future` |
| Logging the full `Throwable` at every layer | Duplicate logs, risk of leaking secrets | One observation boundary and safe logging |
| Shutting down a shared executor in a single request | Other requests get rejected | Define lifecycle ownership |

## 23. Implementation Checklist

1. Identify which component owns the executor and **who has permission to shut it down**.
2. Choose `execute` or `submit` based on the desired error/result observation channel.
3. With `submit`, always have a mechanism to **observe the `Future`** if the task result matters.
4. Distinguish submission-time rejection from failures occurring inside the worker.
5. At `Future.get()`, handle `InterruptedException`, `ExecutionException`, `CancellationException`, and timeouts (if used) separately.
6. Tasks that support cancellation must have interrupt check points or use interruptible APIs.
7. When catching `InterruptedException` in `Runnable`, if stopping the task, restore the flag and **exit the task**; do not swallow and continue.
8. Do not treat `cancel(true)`, `isDone()`, or `shutdownNow()` as proof that cleanup/side effects have finished.
9. Use `try-with-resources`/`finally` for per-task resources, and transactions/idempotency for business state.
10. Shut down with a timeout and report clearly when the pool fails to terminate.
11. In tests, use deterministic latches/signals instead of guesswork timing.
12. Log exceptions safely, avoiding raw tokens, request bodies, PII, and duplicate records.
13. Retries must be conditional, bounded, and governed by a policy that prevents duplicate side effects.
14. Verify success, failure, rejection, timeout, interrupt, cancel, and cleanup paths.

**Conclusion:** When practicing with `ExecutorService`, do not just prove that "the task ran." You must prove that **errors are observed on the right channel**, **interrupts are handled on the right thread**, **cancellation works cooperatively**, and **the executor terminates according to policy**. `execute()`, `submit()`, `Future.get()`, and `cancel(true)` provide distinct mechanisms; understanding them is the key to avoiding swallowed errors, hung workers, or false success reports.
