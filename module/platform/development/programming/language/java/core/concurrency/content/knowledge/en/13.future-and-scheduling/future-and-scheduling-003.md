# Cancellation and States of Future in Java

> **Key Takeaway:** `Future<V>` is a **handle to the result of an asynchronous task**, allowing you to check if it has completed, wait for the result, and **request cancellation**. You must clearly distinguish between **the Future's state/result** and **whether the thread has actually stopped**: `isDone() == true` can be caused by success, failure, or cancellation; `cancel(true)` only *attempts to interrupt* a running task when the implementation supports it; `get(timeout, unit)` only limits **the caller's wait time**, and does not automatically cancel the task. With `ScheduledFuture`, you must also account for scheduled waiting state, periodic execution, and the policy for removing cancelled tasks.

This article belongs to the **Future & Scheduling** group of Java concurrency in general. All standalone examples below use Java SE 17+ (`ExecutorService`, `Future`, `FutureTask`, `ScheduledExecutorService`, and `CompletableFuture` for comparison). Spring mechanisms are not discussed.

## 1. What Does Future Represent?

When a thread calls `ExecutorService.submit(Callable<V>)`, the executor returns a `Future<V>`. A Future can be created **before the worker actually runs**. It represents the ability to receive a result/completion status in the future, not the thread itself and not a promise that "the task will definitely succeed."

~~~text
Thread calling submit()            Executor/worker
-----------------------            ---------------
Future<V> f = submit(task) -----> [ task may be queued ]
       |                                  |
       | f.isDone() = false                v
       |                              [ task starts ]
       |                                  |
       |                       +----------+-----------+
       |                       |          |           |
       |                    success      failure    cancellation
       |                       |          |           |
       +---- f.get() <---------+----------+-----------+
              result / ExecutionException / CancellationException
~~~

`Future` does not provide a `NEW/QUEUED/RUNNING/SUCCEEDED` status enum in the Java 17 interface. Those names are only a **mental model**, not an API. The two key methods to query status are `isDone()` and `isCancelled()`; to get the result or the cause of failure, the caller uses `get()` and handles exceptions.

### Foundational Methods

| API | Meaning and Key Points |
| --- | --- |
| `boolean isDone()` | `true` if the Future has terminated according to contract: **normally, exceptionally, or by cancellation**. Does not mean the task succeeded. |
| `boolean isCancelled()` | `true` if the Future was cancelled before normal completion. Does not mean the thread has completely stopped. |
| `V get()` | Waits if necessary; returns the result or throws the corresponding exception. Does not set a wait deadline. |
| `V get(long timeout, TimeUnit unit)` | Waits at most the specified duration. `TimeoutException` **does not automatically cancel** the task. |
| `boolean cancel(boolean mayInterruptIfRunning)` | Requests cancellation: if not yet started, prevents execution; if running, the parameter determines whether to attempt an interrupt. Outcome may depend on timing/implementation. |

`Future<V>` is an interface; implementations such as `FutureTask`, `ScheduledFuture`, and `CompletableFuture` have specific differences. Do not assume all implementations react identically to interruption or cancellation.

## 2. State Table Observable Through Future

Distinguish between a task's hypothetical internal state and **what can be concluded from the API**:

| Scenario | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Incomplete: queued or running | `false` | Usually `false` | May **block** |
| Normal completion | `true` | `false` | Returns value (may be `null` for `Runnable`) |
| Completed due to an exception in the task | `true` | `false` | Throws `ExecutionException` (get cause via `getCause()`) |
| Transitioned to cancelled | `true` | `true` | Throws `CancellationException` |
| Caller timed out waiting while task is still running | May still be `false` | May still be `false` | `get(timeout)` throws `TimeoutException` on that call; subsequent calls can still succeed |

The table shows typical scenarios, not an "atomically read snapshot" of both flags and the result when a task is completing concurrently. If you read `isDone` and then read `isCancelled` at two points in time, the task can change state in between. **Do not write logic that needs to distinguish multiple scenarios accurately solely by polling the two flags.** When you need the final outcome, use `get()`/`get(timeout)` along with exception handling.

### Distinguishing the Three Termination Paths

1. **Normal completion:** the computation returns a value; `get()` returns that exact value.
2. **Exceptional completion:** the computation throws an exception; for a Future from `submit`, `get()` throws `ExecutionException` wrapping the root cause.
3. **Cancellation:** the Future is successfully cancelled; `get()` throws `CancellationException`, and does not return a normal result, even if the task body has already performed some side effects.

An exception in the `Callable` body **does not** make `isCancelled()` true. It is a failure, not a cancellation. Similarly, a cancelled Future does not mean a business transaction is rolled back.

## 3. Example 1 — Success, Failure, and Post-Completion State

Create the file `FutureOutcomes.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureOutcomes {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> successful = pool.submit(() -> 6 * 7);
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalStateException("broken");
            });

            int value = successful.get(); // Wait for success.
            System.out.println("result = " + value);
            System.out.println("success done = " + successful.isDone());
            System.out.println("success cancelled = "
                    + successful.isCancelled());

            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("failure done = " + failed.isDone());
            System.out.println("failure cancelled = "
                    + failed.isCancelled());
            System.out.println("cancel completed = "
                    + successful.cancel(true));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile/run:

~~~bash
javac FutureOutcomes.java
java FutureOutcomes
~~~

Deterministic output on the normal execution path:

~~~text
result = 42
success done = true
success cancelled = false
failure cause = IllegalStateException
failure done = true
failure cancelled = false
cancel completed = false
~~~

At the time of printing, `successful.get()` and `failed.get()` have confirmed that both Futures have terminated. A failed Future still has `isDone() == true` and `isCancelled() == false`. `cancel(true)` **cannot retroactively cancel a Future that has already completed normally**.

`get()` also provides a *happens-before* relationship from the actions of the computation to the actions after the caller receives completion via `get()`. This makes retrieving work results safe, but **does not make every mutable object shared outside the Future thread-safe**.

## 4. How Do `cancel(false)` and `cancel(true)` Differ?

`cancel(mayInterruptIfRunning)` is a request to change the Future's state and, depending on the situation, prevent or attempt to stop the computation.

### Before the Task Runs

If the task is still waiting in the executor queue and a cancellation succeeds, that task **should not be run**. Both `cancel(false)` and `cancel(true)` can cancel before starting; the interrupt parameter is unnecessary when no thread is executing the task yet.

### Once the Task Has Started

- `cancel(false)`: **does not request an interrupt** on the running worker. An implementation like `FutureTask` can transition the Future to cancelled while the computation **continues running** until it finishes on its own.
- `cancel(true)`: **attempts to interrupt** the running thread, when the implementation knows that thread and supports it. It does not force the thread to stop immediately; the outcome depends on whether the code cooperates with interruption.
- In both cases, if the Future is successfully cancelled, `isDone()`/`isCancelled()` can report true and `get()` throws `CancellationException` **before the task body actually stops executing**.
- If the task has already completed before `cancel`, cancellation does not alter the completed result; the method typically returns `false`.
- When multiple threads call `cancel` on the same Future concurrently, the boolean return value for each caller may differ; afterward, you should check `isCancelled()` if you need to know the final cancellation state.

**Important:** `cancel` returning `true` is an **outcome of the Future cancellation request**, not proof that all side effects of the task have stopped or been rolled back. Java has no safe mechanism to forcibly stop an arbitrary thread at any point in code.

## 5. Example 2 — Cancelling a Queued Task Prevents It from Running

To avoid depending on the scheduler, we use a **single-worker** executor, block the worker with a latch, and cancel the second task while it is guaranteed to still be in the queue.

Create `CancelQueuedFuture.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedFuture {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch occupied = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ran = new AtomicBoolean(false);

        try {
            pool.execute(() -> {
                occupied.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            occupied.await();
            Future<?> pending = pool.submit(() -> ran.set(true));

            boolean acceptedCancel = pending.cancel(false);
            System.out.println("cancel accepted = " + acceptedCancel);
            System.out.println("isDone = " + pending.isDone());
            System.out.println("isCancelled = " + pending.isCancelled());

            try {
                pending.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        System.out.println("task ran = " + ran.get());
    }
}
~~~

Run:

~~~bash
javac CancelQueuedFuture.java
java CancelQueuedFuture
~~~

Output when there is no external interruption:

~~~text
cancel accepted = true
isDone = true
isCancelled = true
get = CancellationException
task ran = false
~~~

At the moment of `cancel(false)`, the sole worker is waiting on `release`; the second task **cannot start yet**. Cancelling the FutureTask created by `submit` prevents its corresponding computation from running. After releasing the latch and shutting down/draining the executor, the `ran` flag remains false.

**Do not conclude:** that a cancelled Future's wrapper immediately disappears from the queue. `ThreadPoolExecutor` may retain the cancelled FutureTask in the queue until it is dequeued or `purge()` is called. `ScheduledThreadPoolExecutor` has its own remove-on-cancel policy covered later.

## 6. Example 3 — `cancel(false)` While Running: Future Done but Worker Not Finished

This is the most important difference between **Future state** and **actual task execution**. With `FutureTask` in a standard executor, a running task can be marked cancelled without being interrupted when `cancel(false)` is called.

Create `CancelRunningWithoutInterrupt.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CancelRunningWithoutInterrupt {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch bodyFinished = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    bodyFinished.countDown();
                }
            });

            started.await();
            boolean cancelled = running.cancel(false);

            System.out.println("cancel(false) = " + cancelled);
            System.out.println("Future done = " + running.isDone());
            System.out.println("Future cancelled = "
                    + running.isCancelled());
            System.out.println("body finished yet = "
                    + (bodyFinished.getCount() == 0));

            try {
                running.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }

            release.countDown();
            bodyFinished.await();
            System.out.println("body finished later = "
                    + (bodyFinished.getCount() == 0));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac CancelRunningWithoutInterrupt.java
java CancelRunningWithoutInterrupt
~~~

Output with `FutureTask` created by the Java SE 17 executor:

~~~text
cancel(false) = true
Future done = true
Future cancelled = true
body finished yet = false
get = CancellationException
body finished later = true
~~~

`started.await()` guarantees the task has started and cannot reach `bodyFinished.countDown()` while `release` has not been opened. `cancel(false)` does not interrupt; the Future transitions to cancelled, but the worker keeps waiting on the latch. Only when main opens `release` does the task reach the `finally` block of its body.

**Practical consequence:** Do not close resources that the body is using **just because `future.isDone()` became true after cancel**, if closing them actually needs to wait for the worker to stop. To confirm a task has stopped, you need a separate completion signal from the task body, appropriate executor/task lifecycle state, or an explicit cancellation/cleanup protocol.

## 7. Interruption Is a Cooperative Mechanism, Not a Forced Stop

`Thread.interrupt()` sets the thread's interrupt status or causes certain blocking methods to respond with `InterruptedException`. Many APIs such as `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, and some `Future.get` implementations can exit waiting when interrupted.

For pure CPU-bound computation without blocking, setting the interrupt flag **does not automatically force a loop to stop**. The task must **check the flag** or have interruptible wait points and decide to exit safely.

Handling pattern:

~~~java
// Illustrative snippet inside Callable/Runnable.
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} finally {
    releaseOwnedResources();
}
~~~

If the work involves blocking operations, catch `InterruptedException` appropriately:

~~~java
// Snippet when the method does not want to propagate InterruptedException.
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore flag.
    return;                              // Do not keep waiting indefinitely.
}
~~~

**Do not swallow interruption** with an empty catch block and continue forever. If you are writing a `Callable` and are allowed to propagate exceptions, you can often propagate `InterruptedException` so the coordinator knows the task did not complete normally.

### What Happens When a Task Ignores Interrupts?

`cancel(true)` can still make the Future cancelled while the task does not stop. For example, the body runs an infinite loop without checking interrupts, calls a non-interruptible native/blocking API, or catches `InterruptedException` and continues. You should not use `Thread.stop()` as a solution: the API is deprecated and dangerous because it can break invariants.

You must design **deadlines, stop tokens, IO timeouts, checkpoints, and cleanup** for your tasks rather than trusting Future cancellation alone to stop every activity.

## 8. Example 4 — `cancel(true)` Wakes Up a Task Waiting on a Latch

Create `CancelInterruptibleTask.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CancelInterruptibleTask {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch interruptionObserved = new CountDownLatch(1);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException e) {
                    interruptionObserved.countDown();
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            interruptionObserved.await(); // Wait for the task body to confirm.
            System.out.println("cancel(true) = " + accepted);
            System.out.println("interrupt observed = true");
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run:

~~~bash
javac CancelInterruptibleTask.java
java CancelInterruptibleTask
~~~

Normal stdout:

~~~text
cancel(true) = true
interrupt observed = true
isDone = true
isCancelled = true
get = CancellationException
~~~

`started.await()` confirms the body has started running. `future.cancel(true)` causes the executor/FutureTask to attempt to interrupt the worker. Even if the interrupt arrives **before** the worker begins `neverReleased.await()`, the interrupt flag will cause that wait to throw `InterruptedException`. `interruptionObserved.await()` is a signal from **the body itself** confirming it observed the interrupt, avoiding guessing from sleep durations or just looking at `isCancelled`.

**Note:** In real code, avoid waiting **indefinitely** on a latch reporting interruption if the implementation/task might not cooperate; use a timeout and a fail-safe branch. The demo intentionally chooses a task guaranteed to be waiting/about to wait on an interruptible primitive so the output is clear.

## 9. `Future.get(timeout)` Does Not Cancel the Computation

If a caller calls `future.get(100, MILLISECONDS)` and the task has not completed before the deadline, the method throws `TimeoutException`. The Future may still be alive and complete afterward. The fact that the caller **no longer wants to wait** does not mean **the task must stop**.

### Example 5 — Timeout, Then the Task Completes Normally

Create `TimeoutNotCancellation.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutNotCancellation {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return "done";
            });

            started.await();
            try {
                future.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                System.out.println("wait = TimeoutException");
            }

            System.out.println("cancelled = " + future.isCancelled());
            System.out.println("done before release = " + future.isDone());

            release.countDown();
            System.out.println("result = " + future.get());
            System.out.println("done after = " + future.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac TimeoutNotCancellation.java
java TimeoutNotCancellation
~~~

Stdout:

~~~text
wait = TimeoutException
cancelled = false
done before release = false
result = done
done after = true
~~~

While main is waiting, the worker cannot return because the latch has not opened; a timeout is guaranteed. After the timeout, `isCancelled()` is still false and `isDone()` is false. When the latch is opened, `future.get()` receives `done` normally.

**Distinguish two timeouts:**
- `get(timeout)`: limits **how long the caller waits**.
- Task deadline/cancellation: separate logic must request stopping or abandoning work, typically with `cancel`, interrupts, I/O deadlines, and deadline checks.

### When to Cancel After a Timeout?

A pattern that may be appropriate:

~~~java
// Illustrative snippet in caller.
try {
    return future.get(timeout, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    future.cancel(true); // Requests cancellation, does not guarantee immediate stop.
    throw e;
}
~~~

However, do not apply this automatically to every business operation. A task writing to a database or sending a message might have already committed side effects before the caller timed out; cancel does not roll back. If the caller retries, there is a risk of duplicate processing. Use idempotency keys, deadlines, transaction boundaries, and reliable job state at the system layer.

## 10. Caller's `InterruptedException` Differs from Future Cancellation

A caller blocked in `future.get()` can be interrupted by another thread. When that happens, `get()` throws `InterruptedException`; this signals that **the waiting thread was interrupted**, not that the computation was cancelled.

~~~java
// Illustrative snippet; the calling method can decide the policy.
try {
    Object value = future.get();
    consume(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Decide whether to cancel the Future or just stop waiting.
}
~~~

When handling this, ask yourself: does the caller stopping its wait mean we want to stop the task? Sometimes a task is a shared computation and other callers still need the result — cancelling it just because one caller was interrupted is the wrong policy.

Do not use `Thread.interrupted()` carelessly in polling because that static method **reads and clears the interrupt status**. `Thread.currentThread().isInterrupted()` only checks the flag without clearing it. Know whether you intend to preserve or consume the signal.

## 11. FutureTask: Common Implementation and Internal States

`FutureTask<V>` is both a `Runnable` and a `Future<V>`. `ExecutorService.submit` typically creates an equivalent `RunnableFuture` for the executor to run and the caller to track completion. It supports `run()`, `cancel`, `get`, `isDone`, and `isCancelled`; its internal states are **implementation details**, not part of the general `Future` contract.

It can be created manually:

~~~java
// API snippet, not standalone.
FutureTask<Integer> task = new FutureTask<>(() -> 42);
new Thread(task).start();
int result = task.get();
~~~

Understand that `FutureTask.cancel(false)` can transition the state to cancelled while the body is running; the body continues executing if not interrupted. This was demonstrated in `CancelRunningWithoutInterrupt`.

### `isDone` Is Not an Acknowledgment That All Side Effects Have Finished

Especially after a successful cancel, `isDone() == true` can occur **before the computation body actually returns**. You should not close files/sockets owned by the body or assume events have finished being written based solely on Future status. You need a separate completion signal or coordination with the lifecycle of the executor/thread owned by the program.

For a `Callable` that throws an exception without being cancelled, the Future typically completes exceptionally; `isDone()` is true, `isCancelled()` is false, and `get()` throws `ExecutionException`. A Future that has completed normally cannot be retroactively cancelled.

## 12. ScheduledFuture: Pending Delay, Running, and Periodic Tasks

`ScheduledExecutorService` supports `schedule`, `scheduleAtFixedRate`, and `scheduleWithFixedDelay`. The result of these calls is a `ScheduledFuture<?>`, which extends `Future` with `getDelay` and `compareTo` from `Delayed`.

For **one-shot** tasks:
- Before the scheduled time, the Future may not be done; `get()` can wait until execution finishes.
- If `cancel` succeeds before the scheduled execution time, the task should not be executed.
- Once the task runs and completes normally/exceptionally, the corresponding `Future.get()` rules apply.

For **periodic tasks**:
- A periodic task that succeeds on each run normally **has no final result** per cycle; `get()` does not return normally just because one execution finished.
- The Future of a periodic task typically remains in a not-done state **while the schedule is still active**.
- If an execution throws an exception, subsequent executions are suppressed according to the scheduler contract; the Future may terminate exceptionally and `get()` throws `ExecutionException`.
- When cancelling a periodic Future, future scheduled runs are cancelled per contract, while an in-progress run may need to cooperate with interruption if it must stop immediately.
- Shutdown and continuation of periodic tasks also depend on `ScheduledThreadPoolExecutor` policies (`continueExistingPeriodicTasksAfterShutdownPolicy`, `executeExistingDelayedTasksAfterShutdownPolicy`).

**Do not define "periodic done" as having run one cycle.** For periodic tasks requiring shutdown, you must manage the Future representing the entire execution sequence and the lifecycle of the scheduler.

### Do Not Confuse `getDelay` with Runtime or Guaranteed Start

`scheduled.getDelay(TimeUnit.MILLISECONDS)` reflects the estimated time until the task is eligible to run according to the scheduler's clock. It does not guarantee the task has started running immediately when the delay reaches 0: workers may still be busy, the scheduler may be shutting down, or other resources may be constrained.

## 13. Example 6 — Cancelling a Scheduled Task Before Its Due Time

Create `CancelScheduledFuture.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelScheduledFuture {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(true);
        AtomicBoolean ran = new AtomicBoolean(false);

        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> ran.set(true), 1, TimeUnit.DAYS);

            boolean cancelled = future.cancel(false);
            System.out.println("cancelled = " + cancelled);
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
            System.out.println("queue entries = "
                    + scheduler.getQueue().size());
            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            scheduler.shutdownNow();
            scheduler.awaitTermination(10, TimeUnit.SECONDS);
        }

        System.out.println("task ran = " + ran.get());
    }
}
~~~

Run:

~~~bash
javac CancelScheduledFuture.java
java CancelScheduledFuture
~~~

Normal output:

~~~text
cancelled = true
isDone = true
isCancelled = true
queue entries = 0
get = CancellationException
task ran = false
~~~

The task is scheduled **one day later**, so cancelling immediately after scheduling happens before the execution time. `setRemoveOnCancelPolicy(true)` causes the cancelled task to be removed **immediately** from the `ScheduledThreadPoolExecutor` work queue instead of remaining retained until its delay expires under the default policy; therefore, the number of queue entries after cancel is 0 in this example.

### Memory Retention of Cancelled Scheduled Tasks

According to the `ScheduledThreadPoolExecutor` documentation, a cancelled delayed task by default may **not be removed from the queue immediately** until its eligible execution time arrives, to allow inspection/tracking, which can cause unnecessary retention. `setRemoveOnCancelPolicy(true)` is useful when many scheduled tasks are cancelled before their due time.

Do not confuse this API with regular `ThreadPoolExecutor`: it is a method on `ScheduledThreadPoolExecutor`. Do not assume every custom scheduler has the same implementation.

## 14. CompletableFuture Is Also a Future, but Cancellation Differs

`CompletableFuture<T>` implements `Future<T>` and `CompletionStage<T>`. However, its cancellation does not control workers the way `FutureTask` does:

- `CompletableFuture.cancel(mayInterruptIfRunning)` completes the CompletableFuture with `CancellationException` if it is not yet completed.
- The **`mayInterruptIfRunning` parameter has no effect** in the `CompletableFuture` implementation itself, because it does not use interrupts to control execution.
- Incomplete dependent stages may complete exceptionally with a `CompletionException` caused by the cancellation.
- `CompletableFuture.join()` throws an unchecked `CompletionException` for normal errors; if that CompletableFuture itself was cancelled, `join()` can throw `CancellationException` directly.
- `isDone()` is true if completed normally, exceptionally, or cancelled; `isCompletedExceptionally()` can be true even when cancelled.

Therefore, do not write code assuming "`future.cancel(true)` always interrupts the computing thread" and apply it to both `FutureTask` and `CompletableFuture`. With `CompletableFuture.supplyAsync(...)`, cancelling the completion stage **does not necessarily stop the running Supplier**.

Simple illustrative example:

~~~java
// Snippet, assuming import java.util.concurrent.CompletableFuture.
CompletableFuture<Integer> cf = new CompletableFuture<>();
boolean cancelled = cf.cancel(true);
System.out.println(cf.isCancelled()); // true
// This does not prove an external executing thread was interrupted.
~~~

If you need to stop actual computational work, design your own cancellation tokens, stop conditions, deadlines, and task management relationships rather than relying solely on the state of the completion stage.

## 15. Future Cancellation and ExecutorService Shutdown Are Not Identical

`ExecutorService` has the lifecycle of the **executor**, separate from the Future of **each individual task**.

| Operation | What It Does | What It Does Not Guarantee |
| --- | --- | --- |
| `future.cancel(false)` | Requests cancellation of a specific Future, without interrupting a running task | Does not interrupt a running body |
| `future.cancel(true)` | Requests cancellation of a Future and attempts to interrupt a running task | Does not force the body to stop immediately |
| `executor.shutdown()` | Stops accepting new tasks; processes already-accepted tasks per contract | Does not automatically cancel all Futures or force workers to exit immediately |
| `executor.shutdownNow()` | Attempts to interrupt executing tasks, returns tasks that had not started | Does not guarantee every task stops or that unstarted Futures are marked cancelled |
| `executor.awaitTermination(timeout, unit)` | Waits for the executor to terminate after shutdown | Does not automatically cancel still-live computations |
| `Future.get(timeout, unit)` | Limits the caller's wait time for a result | Does not cancel, interrupt, or clean up queued tasks |

A subtle bug: **`shutdownNow()` returns a list of `Runnable`s that had not started**. If some items correspond to Futures that callers are holding, you must decide explicitly how to handle them: just because a task was drained from the queue does not mean its Future is automatically completed/cancelled in every implementation. If Futures of unstarted tasks need to be completed, the coordinator must have an appropriate cancellation/result reporting protocol.

For graceful shutdown, a common pattern:

~~~java
// Illustrative snippet; caller has an InterruptedException handling policy.
executor.shutdown();
if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    java.util.List<Runnable> notStarted = executor.shutdownNow();
    // Record/cancel or forward notStarted according to policy.
    executor.awaitTermination(10, TimeUnit.SECONDS);
}
~~~

A worker performing non-interruptible I/O may not stop within the expected time. Stopping Futures and stopping resources are operations that must be coordinated.

## 16. `invokeAll` and Group Task Timeouts

`ExecutorService.invokeAll(tasks)` waits for all tasks in the group to complete and returns a list of Futures, though the caller must still check `get()` on each Future to distinguish success from failure.

`invokeAll(tasks, timeout, unit)` has a notable contract: the method returns when all tasks have completed or when the timeout expires; **tasks that have not completed are cancelled** per the API. This is a key difference from `Future.get(timeout)` — which **does not automatically cancel**.

Conceptual example:

~~~java
// Illustrative snippet inside a method that throws InterruptedException.
java.util.List<java.util.concurrent.Callable<String>> tasks = ...;
java.util.List<Future<String>> futures =
        executor.invokeAll(tasks, 2, TimeUnit.SECONDS);

for (Future<String> future : futures) {
    if (future.isCancelled()) {
        // Task did not finish within the limit or was cancelled for another reason.
    } else {
        // Call get() to retrieve the result or catch ExecutionException.
    }
}
~~~

This snippet is not standalone because `tasks`/`executor` are not fully declared. As with cancellation in general, having the API mark a Future as cancelled **does not strictly guarantee** that every body has stopped or rolled back side effects.

When a group of tasks has dependencies or needs partial results, design how to aggregate success/failure/timeout/cancellation explicitly, avoiding treating every done Future as successful.

## 17. Race Conditions Around Cancellation and Completion

Cancellation **races** with task completion:

~~~text
Thread A: cancel(true)  -------+
                               +--- who updates the state first?
Worker:   return result -------+
~~~

One of the following outcomes can occur:

- The task completed before cancel took effect: `cancel` typically returns false; `get` returns the completed result or error.
- Cancel wins while the Future is not yet completed: `isCancelled` is true and `get` throws `CancellationException`.
- The task already started a side effect, cancel wins the Future state, but the body may continue the side effect if it does not cooperate or if cancellation arrived too late.
- Two concurrent callers calling cancel may receive different boolean values; looking at one caller's return value is not the only way to deduce the final state.

**Design rule:** Cancellation must be **idempotent and observable**, while task side effects need their own protocol. For jobs that send emails, create orders, debit accounts, or write to a database, `cancel(true)` is not a transaction rollback. You may need idempotency keys, stored job status, outbox, post-commit acknowledgment, compensating actions, and a way to resume on restart.

### Business State Machines Differ from Future State

A business API might have `PENDING`, `RUNNING`, `COMMITTED`, `CANCEL_REQUESTED`, `CANCELLED`, `FAILED`. A `Future.isCancelled` alone does not prove a job is in `CANCELLED` in storage or in a system outside the JVM.

For example, if a customer clicks Cancel while a transaction is committing, the coordinator must choose clearly:
- Disallow commit if cancellation wins before the decision point.
- Or accept that the commit completed and return a completed status, even if the caller no longer wants the result.
- Or record a state requiring compensation and handle it asynchronously.
The Future API **does not decide** this policy.

## 18. Cooperative Task Cancellation: Control Points

A task can be cancelled more safely when it:

1. Works in **small units** and frequently checks `isInterrupted()` or a valid stop token.
2. Uses blocking APIs that support interruption/timeouts.
3. When interrupted, **exits** or propagates the exception instead of swallowing the signal.
4. Places resource release in `finally` or try-with-resources.
5. Avoids closing resources shared by other tasks if cancellation applies only to one task.
6. Does not write half-finished updates to shared mutable state; updates invariants in clear atomic/transactional steps.
7. Has explicit deadlines when doing I/O; interrupts are not always effective with every external library.
8. Can track when **the task body actually stopped** if cleanup of resources outside the Future handle is needed.
9. When there are multiple consumers of a Future/shared computation, considers who **has the authority** to cancel.
10. When retrying, controls idempotency so as not to create duplicate side effects after a timeout.

CPU-bound loop pattern:

~~~java
// Snippet of a computational task, not a standalone program.
while (!Thread.currentThread().isInterrupted()) {
    if (workQueueIsEmpty()) {
        break;
    }
    processNextUnit();
}
cleanupAfterLoop();
~~~

In real code, dequeuing/checking the queue must have an appropriate concurrency protocol; this snippet only emphasizes checking the interrupt flag, not providing a queue implementation.

Do not rely on `Thread.sleep(100)` to prove cancellation is received "in time"; the scheduler can change timing. Use latches to control tests or use explicit timeouts.

## 19. Verifying Correctness of Future Cancellation

A valuable test needs to separate **Future state** from **actual worker progress**:

| Question | Verification Technique |
| --- | --- |
| Has the task started? | `CountDownLatch started` decremented at the start of the body |
| Is the task guaranteed to be waiting in the queue? | A single-worker executor is held by a latch, and a second task is submitted |
| Does `cancel(false)` interrupt the worker? | Task waits on a latch and is only released after reading Future status |
| Was `cancel(true)` observed by the body? | Latch `interruptionObserved` decremented in catch `InterruptedException` |
| Caller timed out, is the task still alive? | Only release the latch **after** `get(timeout)` throws `TimeoutException` |
| Has the task actually stopped? | Latch/callback at the end of the body, `join`, or appropriate executor termination |
| Is the task error preserved in the Future? | `get()` and `ExecutionException.getCause()` |
| Is a cancelled scheduled task still in the queue? | Check the remove-on-cancel policy of the specific scheduler |

Do not use a single `isDone() == true` result to confirm resource cleanup after cancel. Do not conclude cancellation stopped side effects just because `Future.get()` threw `CancellationException`.

### Do Not Turn Demos into Hanging Tests

The examples use latches and assume no external interruption to produce deterministic stdout. In a **real automated test suite**, `await()`/`join()` steps should have timeouts, fail-safe branches, and cleanup in `finally`; if the implementation is buggy or the task does not cooperate, the test will not hang indefinitely.

When measuring performance, separate queue wait time, execution time, cancellation latency, and cleanup latency. A high cancelled count can be a sign that deadlines are too short or the executor backlog is too large.

## 20. Common Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| "`isDone()` true means success." | It can be normal, failure, or cancellation |
| "`isCancelled()` true means the worker has definitely stopped." | Future state can be cancelled while the task body is still running |
| "`cancel(false)` cannot cancel a task that has already started." | With FutureTask, it can mark it cancelled without interrupting the worker |
| "`cancel(true)` is like `Thread.stop()`." | Only attempts to interrupt; requires task cooperation |
| "`cancel(true)` rolls back the database." | There is no automatic transaction/compensation |
| "`get(timeout)` timing out will cancel the task." | It only limits the caller's waiting time |
| "Catching `InterruptedException` and ignoring it is fine." | Can make the task unresponsive to cancellation |
| "Caller `get()` being interrupted means the Future was cancelled." | The two states are different |
| "If a Future fails, `isCancelled()` is true." | Task failure and cancellation are different |
| "A cancelled Future automatically disappears from the queue immediately." | A queued wrapper may remain; schedulers/remove-on-cancel policies differ |
| "`ScheduledFuture.get()` of a periodic task returns after one cycle." | Periodic tasks normally do not complete normally after each run |
| "`CompletableFuture.cancel(true)` interrupts the supplier." | The interrupt parameter has no effect on CompletableFuture |
| "`shutdownNow()` cleanly cancels every Future." | Attempts to interrupt and returns queued tasks; does not guarantee all Futures are completed/cancelled |
| "`invokeAll(timeout)` is the same as `get(timeout)`." | Timed invokeAll has a contract to cancel unfinished tasks |
| "After cancelling, you can immediately close resources the body is using." | Must coordinate actual completion/cleanup |
| "`Future` has a RUNNING/QUEUED enum in Java 17." | The Java 17 interface has no such detailed state API |

## 21. Self-Check Questions

**Question 1.** Do `isDone() == true` and `isCancelled() == false` prove the task succeeded?  
**Answer:** No. It might have thrown an exception; call `get()` and handle `ExecutionException`.

**Question 2.** `future.cancel(false)` returns true while a FutureTask is running. Does the body stop immediately on its own?  
**Answer:** Not necessarily; the Future can be cancelled while the body continues running because it was not interrupted.

**Question 3.** `future.cancel(true)` is called while a task is blocked at `CountDownLatch.await()`. What can happen?  
**Answer:** The thread is attempted to be interrupted; `await` can throw `InterruptedException` for the body to handle. You must confirm the body actually observes it and exits.

**Question 4.** If `get(50, MILLISECONDS)` throws `TimeoutException`, does `isCancelled()` automatically become true?  
**Answer:** No. The timeout applies only to that wait call.

**Question 5.** A task throws `IllegalStateException`. Does `Future.get()` throw `IllegalStateException` directly?  
**Answer:** For a Future from `ExecutorService.submit`, `get()` throws `ExecutionException`; the root cause is in `getCause()`.

**Question 6.** Can a Future that has already returned a normal result be successfully cancelled afterward?  
**Answer:** No; the Future is already completed, so cancellation does not change the result.

**Question 7.** A periodic `ScheduledFuture` has run successfully three times; must `isDone()` be true?  
**Answer:** No. As long as a periodic Future has not stopped its schedule, it normally remains not-done; `get()` does not return just because one cycle finished.

**Question 8.** Why should you consider `setRemoveOnCancelPolicy(true)` in `ScheduledThreadPoolExecutor`?  
**Answer:** It reduces retention of cancelled delayed tasks that would otherwise remain in the queue until their due time under the default policy.

**Question 9.** Does `CompletableFuture.cancel(true)` necessarily interrupt the thread running a Supplier?  
**Answer:** No; `mayInterruptIfRunning` has no effect in the CompletableFuture implementation.

**Question 10.** How do `invokeAll(tasks, timeout, unit)` and `future.get(timeout, unit)` differ regarding cancellation?  
**Answer:** Timed `invokeAll` cancels unfinished tasks on timeout; timed `get` does not automatically cancel the Future.

**Question 11.** If a caller is interrupted during `get()`, is the task automatically cancelled?  
**Answer:** No. The caller must decide whether to cancel the task based on ownership/policy.

**Question 12.** After `cancel(true)`, `isDone()==true`; can you assume it is safe to immediately close a socket the task is using?  
**Answer:** No. The body may still be executing; you must have an actual stop/cleanup protocol.

## Official References

- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `isCancelled`, `cancel`, memory consistency.
- [`FutureTask` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): runnable future, cancellation of computation.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `shutdown`, `shutdownNow`.
- [`ScheduledExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay`.
- [`ScheduledFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): Future for scheduled computation.
- [`ScheduledThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): remove-on-cancel and shutdown policies.
- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation/completion stages and interrupt semantics.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic test coordination.

**Remember:** `Future` reports the state of **the computation's result**; it is not a forced thread lock. Safe cancellation requires **defining ownership, cooperative interruption, deadlines, side-effect policies, and a signal that the body has actually finished**, especially with scheduling and executor shutdown.