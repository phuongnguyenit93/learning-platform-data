# Lifecycle: Closing an Executor and Avoiding Thread Leaks in Java

## 1. Why Does an Executor Need a Clear Lifecycle?

`ExecutorService` lets you submit `Runnable` or `Callable` tasks for a group of worker threads to execute. Creating an executor means **creating a resource with a lifecycle**, not merely calling a method to run code.

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
executor.submit(() -> performTask());
```

This is **illustrative code**; it requires importing `java.util.concurrent.*` and defining `performTask()`. If you never close the executor, its workers can stay alive and consume thread/stack/system resources; a Java program may fail to exit if non-daemon platform threads remain alive. If an application creates a new executor per request and never closes it, the thread count can grow uncontrollably.

A **thread leak** in this context is not necessarily an unreferenced memory region that the GC fails to reclaim. It usually refers to a situation where **threads continue to exist or resources bound to threads are not released even though the logical work has finished**. Common causes include:

- Creating new `ExecutorService` instances repeatedly without calling `shutdown()`.
- Workers getting stuck on `BlockingQueue.take()`, `Future.get()`, `Lock.lock()`, or I/O without a wakeup/cancellation mechanism.
- Tasks with infinite loops that do not respond to `interrupt()`.
- Creating too many pools with fixed worker counts, causing total threads to exceed system capacity.
- Forgetting to clean up `ThreadLocal` in pooled workers, causing thread-bound data to persist across multiple tasks.
- Tasks blocking each other, deadlocking, or holding locks while waiting for other work in the same pool.
- Scheduled tasks or producers continuing to submit work after a component was supposed to be closed.

The goal of this article is a verifiable contract:

> **Whoever creates an executor must clearly define who owns it, who is allowed to submit work, when it stops accepting tasks, how still-running tasks are handled, and how to confirm that the executor has terminated.**

This article belongs to the **Executor Framework** of **general Java concurrency**, independent of any framework.

## 2. What Phases Does the Lifecycle Have?

An executor does not just have two states, "running" and "closed". The typical usage model is:

```text
       create ExecutorService
                 |
                 v
         RUNNING / ACCEPTING
         - accepts execute/submit
         - workers run and take tasks from queue
                 |
            shutdown()
                 |
                 v
         SHUTDOWN / DRAINING
         - rejects new tasks
         - already-accepted tasks are still allowed to complete
                 |
       workers and queue finish
                 |
                 v
            TERMINATED
         - no workers executing tasks
         - awaitTermination can return true
```

Another branch is:

```text
RUNNING or SHUTDOWN
       |
  shutdownNow()
       |
  requests immediate stop / interrupts workers
  retrieves pending tasks that have not started
       |
  if tasks cooperate and workers finish
       v
   TERMINATED
```

For `ThreadPoolExecutor`, the JVM has more detailed internal execution states, but you should not write code that relies on implementation details. The public API gives us the following observation points:

- `isShutdown()`: the executor has received a shutdown request; it does **not** mean workers have finished.
- `isTerminated()`: the executor has finished after shutdown.
- `awaitTermination(timeout, unit)`: waits for the terminated state, timeout, or interrupt.
- `shutdown()`: orderly shutdown; does not block the caller waiting for completion.
- `shutdownNow()`: attempts to stop/cancel, but is not a command to forcibly kill threads.

If you only call `shutdown()` and return, you have only **started** the shutdown lifecycle. If you need to confirm cleanup, you must wait and handle the case where waiting fails.

## 3. Distinguishing Shutdown, Termination, and Task Completion

These three concepts are not equivalent:

| Event | Meaning | What does it NOT prove? |
| --- | --- | --- |
| `shutdown()` has been called | Executor rejects new work; already-accepted work may continue | Does not prove tasks are done |
| `isShutdown() == true` | Lifecycle has entered shutdown | Does not prove workers have exited |
| `isTerminated() == true` | Executor has terminated its workers per contract | Does not prove every task succeeded business-wise |
| `awaitTermination(...) == true` | Executor terminated within the wait period | Does not return each task's result or exception |
| `Future.get()` returns successfully | Corresponding task returned a result; establishes memory happens-before when reading result | Does not prove other tasks have completed |
| `Future.cancel(true)` succeeds | Future transitions to canceled state and requests interrupt if appropriate | Does not prove worker cleanup has finished |

For example, a `Callable` can throw an exception. The worker still exits, and the executor still terminates; yet the business outcome is **FAILED**. Therefore, for problems that need result guarantees, you must keep the `Future`, wait on `get()`, or use a dedicated error-reporting mechanism. **Waiting for the pool to stop** and **reading task outcomes** are two different checks.

## 4. `shutdown()`: Orderly Shutdown

Calling:

```java
executor.shutdown();
```

prevents new tasks from being accepted and allows tasks already accepted by the executor to continue processing per contract. It **does not wait** for submitted tasks to complete before returning.

Tasks submitted after shutdown are typically rejected via `RejectedExecutionException` when using standard executors with the default rejection policy. If an application configures `ThreadPoolExecutor` with a different `RejectedExecutionHandler`, behavior may differ; do not assume every handler throws an exception.

### Example 1: Graceful Shutdown with Deterministic Results

Create `GracefulLifecycleDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class GracefulLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Future<Integer> first = executor.submit(() -> {
            bothStarted.countDown();
            release.await();
            return 10;
        });
        Future<Integer> second = executor.submit(() -> {
            bothStarted.countDown();
            release.await();
            return 20;
        });

        bothStarted.await(); // Both tasks are waiting on release.
        executor.shutdown();

        System.out.println("shutdown=" + executor.isShutdown());
        System.out.println("terminated before release="
                + executor.isTerminated());

        release.countDown();
        boolean stopped = executor.awaitTermination(
                10, TimeUnit.SECONDS);

        System.out.println("terminated=" + stopped);
        System.out.println("sum=" + (first.get() + second.get()));
    }
}
```

Compile/run with JDK 17+:

```bash
javac GracefulLifecycleDemo.java
java GracefulLifecycleDemo
```

Output when workers are scheduled and finish within the ten-second deadline:

```text
shutdown=true
terminated before release=false
terminated=true
sum=30
```

**Why the output is reliable:**

1. `main` waits for `bothStarted` before shutting down. Both workers have entered their tasks and are waiting on `release`.
2. `shutdown()` forbids new submissions, but does not interrupt these tasks.
3. Because `release` has not been opened yet, the tasks cannot complete; `isTerminated()` at that point is `false`.
4. `main` opens the latch, and the tasks return `10` and `20`.
5. `awaitTermination` waits for the executor to stop; `Future.get()` confirms each task's result and provides memory visibility guarantees when reading the outcome.

The time budget is illustrative: in an abnormally delayed environment, `awaitTermination` can still return `false`. Production code must handle that branch rather than assuming every executor is guaranteed to stop within ten seconds.

### Note on Using Future

`Future.get()` can throw `ExecutionException` when the task fails, `InterruptedException` if the caller is interrupted, or `CancellationException` if the task was canceled. Do not simply call `awaitTermination` and assume every task succeeded.

## 5. `shutdownNow()` Is Not `kill -9` for Java Threads

Calling:

```java
List<Runnable> notStarted = executor.shutdownNow();
```

asks the executor to:

1. Stop accepting new tasks.
2. Attempt to stop currently running tasks (typically via `Thread.interrupt()`).
3. Not start executing tasks that are still in the queue.
4. Return a list of `Runnable`s that had not started, as returned per contract.

**Key point:** interruption is a **cooperative signal**. If a task does not check for interruption, does not call interruptible waiting APIs, and keeps spinning in a CPU loop, `shutdownNow()` does not forcibly terminate it. Running tasks are also **not** included in the returned pending list.

With `submit(Callable)`, the executor typically wraps the task in a `RunnableFuture`, so elements in the pending list may **not be the original object** the caller submitted. If you want to retry them, you must check validity, idempotency, and avoid duplicate processing.

### Example 2: Distinguishing Running Tasks and Unstarted Tasks

Create `ShutdownNowLifecycleDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownNowLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1));

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);

        executor.execute(() -> {
            started.countDown();
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                exited.countDown();
            }
        });

        started.await(); // The single worker is waiting indefinitely.
        executor.execute(() ->
                System.out.println("pending should not run"));

        List<Runnable> pending = executor.shutdownNow();
        exited.await();

        boolean terminated = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("pending=" + pending.size());
        System.out.println("saw interrupt=" + interrupted.get());
        System.out.println("terminated=" + terminated);
    }
}
```

```bash
javac ShutdownNowLifecycleDemo.java
java ShutdownNowLifecycleDemo
```

Output when there is no unexpected interrupt on `main` and the executor stops within the deadline:

```text
pending=1
saw interrupt=true
terminated=true
```

Explanation: the pool has **one** worker; the first task has started and is waiting on a latch that never opens. The second task enters the capacity-1 queue and cannot start. `shutdownNow()` attempts to interrupt the first task; `await()` responds with `InterruptedException` and the task exits. The second task is returned as pending. `exited.await()` lets `main` wait for the first task's cleanup branch before printing.

The program uses a latch that never opens solely to **simulate a blocked task**. You should not use such an indefinite wait in production without a timeout, cancellation path, or explicit stop signal.

## 6. `awaitTermination()`: Confirming Whether Termination Actually Happened

Signature:

```java
boolean awaitTermination(long timeout, TimeUnit unit)
        throws InterruptedException;
```

This is a condensed API signature. `awaitTermination`:

- **Returns `true`** if the executor terminated before or during the wait.
- **Returns `false`** if the timeout elapsed and the executor still has not terminated.
- **Throws `InterruptedException`** if the waiting thread is interrupted.

It **does not call `shutdown()` itself**. If the executor is still `RUNNING` and no other thread closes it, `awaitTermination` will simply wait out the timeout and return `false`.

A bounded wait must always have a branch handling `false`. Do not treat logging "shutdown requested" as proof that workers have finished cleaning up.

### Example 3: Timing Out First, Succeeding Later

Create `TerminationTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TerminationTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        executor.execute(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        started.await();
        executor.shutdown();

        boolean before = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("before release=" + before);

        release.countDown();
        boolean after = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("after release=" + after);
    }
}
```

```bash
javac TerminationTimeoutDemo.java
java TerminationTimeoutDemo
```

Output when not interrupted externally and the worker is scheduled to finish within the second deadline:

```text
before release=false
after release=true
```

The task's latch is not yet opened during the first wait, so the executor is definitely not terminated at that moment. After `main` opens `release`, the worker can finish and the executor reaches `terminated`. If a resource has strict deadline requirements, the code must check `after` and have a sensible fallback.

## 7. Recommended Two-Phase Shutdown Pattern

The standard procedure for a pool owned by the application itself:

1. Call `shutdown()` to stop accepting new work and prioritize graceful completion.
2. Call `awaitTermination(graceTimeout)` for a bounded wait.
3. If it has not stopped yet, call `shutdownNow()` to request cancellation.
4. Call `awaitTermination(forceTimeout)` once more to confirm workers have actually exited.
5. If it still has not stopped, **report an incomplete shutdown**; do not claim success.
6. If the caller is interrupted while waiting, call `shutdownNow()` and restore the interrupt flag or propagate the exception per contract.

A Java 17+ helper:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ExecutorStopper {
    private ExecutorStopper() {}

    public static boolean stop(ExecutorService executor) {
        executor.shutdown();
        try {
            if (executor.awaitTermination(5, TimeUnit.SECONDS)) {
                return true;
            }
            executor.shutdownNow();
            return executor.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
```

This class **compiles but has no `main`**; place it in `ExecutorStopper.java` and call it from the code that owns the executor. The two `5`-second timeouts are just examples. The helper returns `false` if termination could not be confirmed or the caller was interrupted. In a real system, the caller should also inspect the pending list from `shutdownNow()` if those jobs need to be retried or persisted.

**Do not confuse `shutdownNow` with a "force stop":** if tasks do not cooperate, the second step can still time out. Do not use `Thread.stop()` to forcibly cut off a worker holding locks; that API is unsafe.

## 8. Ownership: Who Creates It, Who Closes It?

This is the strongest principle for preventing thread leaks:

- A component that **creates an executor** is responsible for managing its lifecycle.
- A component that **borrows an executor** from outside should not unilaterally call `shutdown()` on a shared resource unless the contract allows it.
- Creating a dedicated pool per request easily causes too many threads and makes it hard to close at the right time.
- An executor shared across many tasks usually lives for the lifecycle of the service/application, not a single call.
- If a method creates a temporary pool for local work, there must be a `finally` path that closes the pool even if the computation throws an exception.

Example of proper ownership:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    submitKnownTasks(executor);
    collectResults();
} finally {
    stopExecutor(executor);
}
```

This is **illustrative Java pseudocode** where the methods are application-defined; `stopExecutor` implements two-phase shutdown. If `collectResults` throws an exception, `finally` still triggers resource cleanup. However, `finally` does not mean stopping is guaranteed to succeed: the helper must report status when it cannot terminate.

Example of improper ownership:

```java
void handleRequest() {
    ExecutorService executor = Executors.newFixedThreadPool(8);
    executor.submit(this::process);
    // No handle kept for shutdown.
}
```

This is an illustrative snippet. If called repeatedly, the number of pools and workers can grow. GC is not a reliable lifecycle mechanism for closing executors. An owner must be designated to manage the count, when to stop, and pending tasks.

### When Callers Should Only Submit Work

A good API may expose only `Executor` instead of the full `ExecutorService` to components that only need to call `execute`. `Executor` does not expose `shutdown`, helping prevent callers from arbitrarily closing another component's pool. This is not an absolute security boundary; it is a way to **express ownership in API design**.

## 9. Why Do Pooled Threads Differ from Per-Task Threads?

With `new Thread(task).start()`, a thread normally exits when `run()` returns. With a thread pool, a worker can stay alive after one task finishes to pick up a new task. That enables thread reuse, but without `shutdown`, threads can wait for new work indefinitely.

`Executors.newFixedThreadPool(n)` creates a pool capable of maintaining its worker count when work arrives, typically using an effectively unbounded queue for task submissions. If the task producer is faster than the consumers, the backlog can grow significantly — **not a thread leak, but still a potential resource leak / memory exhaustion**.

`Executors.newCachedThreadPool()` can create many workers as workload increases and keep idle workers for a period before reclaiming them. It does not mean the worker count is always bounded low. If requests arrive rapidly and tasks block for a long time, the thread count can grow very large.

`Executors.newSingleThreadExecutor()` also typically keeps its worker for reuse, so forgetting to shut down a single-thread executor created per request can still accumulate many waiting threads.

### Do Not Use Daemon Threads to Mask a Missing Shutdown

A custom `ThreadFactory` can create daemon threads, but daemon threads are **not a resource-cleanup solution**. The JVM can exit when only daemon threads remain without waiting for those tasks to finish or flush data. What you need is **lifecycle management and controlled completion/cancellation**.

A `ThreadFactory` that gives threads clear names is very useful for diagnostics:

```java
ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable);
    thread.setName("order-worker-" + thread.getId());
    return thread;
};
ExecutorService executor = Executors.newFixedThreadPool(4, factory);
```

This snippet requires importing `ExecutorService`, `Executors`, and `ThreadFactory`. Threads created with clear names are easy to identify in thread dumps. When an application uses multiple pools, you can combine pool/worker numbers to avoid duplicate names. Do not arbitrarily configure daemon threads just to make the process exit.

## 10. Tasks That Ignore Interruption Can Prevent Termination

`shutdownNow()` normally interrupts workers, but `Thread.interrupt()` is a **cooperative request**. A CPU-bound task that does not check the flag or a task stuck in non-interruptible I/O can keep running.

Create `InterruptIgnoringTaskDemo.java` to illustrate a task that deliberately ignores interruption, yet has a **custom stop flag** that lets the program finish:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptIgnoringTaskDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean running = new AtomicBoolean(true);
        CountDownLatch started = new CountDownLatch(1);

        executor.execute(() -> {
            started.countDown();
            while (running.get()) {
                Thread.onSpinWait(); // Deliberately ignores interrupt.
            }
        });

        started.await();
        executor.shutdownNow();

        boolean before = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("terminated while ignoring interrupt=" + before);

        running.set(false);
        boolean after = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("terminated after stop signal=" + after);
    }
}
```

```bash
javac InterruptIgnoringTaskDemo.java
java InterruptIgnoringTaskDemo
```

Output when the task exits and the worker is scheduled within the second deadline:

```text
terminated while ignoring interrupt=false
terminated after stop signal=true
```

Because the task does not read the interrupt status, `shutdownNow()` does not make it exit. Setting `running=false` is what ends the loop. `Thread.onSpinWait()` is only an optimization hint for spin loops, **not a cancellation or resource-waiting mechanism**. This example intentionally demonstrates the limit of `shutdownNow`; do not write similar busy-loops in real code.

## 11. How Do Tasks Cooperate with Interruption?

Two basic cases:

**Task waiting on an interruptible API:**

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} finally {
    cleanup();
}
```

This is an illustrative snippet; `Job`, `queue`, `process`, and `cleanup` are application code. `BlockingQueue.take()` can throw `InterruptedException` when the worker is interrupted. The thread should exit the task or propagate the interrupt rather than catching the exception and continuing to wait indefinitely.

**CPU-bound or batch-processing task:**

```java
for (Job job : jobs) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processSafely(job);
}
```

This is an illustrative snippet. Respond to cancellation at **consistent checkpoints**: if processing a job has multiple steps, you must complete or roll back a unit of state so you do not leave broken invariants. Interruption does not automatically roll back changes already made.

Do not assume `Thread.sleep()` inside a `synchronized` block releases the monitor; `sleep` **does not release locks**. A task holding a lock while sleeping for another component that also needs the lock can cause a hang. During shutdown, you must consider both lock ownership and waiting methods.

### `InterruptedException` and the Interrupted Flag

Many waiting APIs throw `InterruptedException` and typically clear the thread's interrupt flag before throwing. If a method cannot propagate the checked exception (such as `Runnable.run()`), the standard practice is to **restore the flag** with `Thread.currentThread().interrupt()` and exit the work.

`Thread.currentThread().isInterrupted()` only reads the status; it **does not clear the flag**. `Thread.interrupted()` is a static method that reads and **clears the current flag**. Do not accidentally consume the interrupt signal and loop forever.

## 12. `Future.cancel(true)` Differs from Shutting Down the Whole Executor

If a single task is no longer needed, `Future.cancel(true)` can send an interrupt request to that specific task without closing the entire pool. In contrast:

- `shutdown()`: closes admission for the **entire executor**, without actively canceling already-accepted tasks.
- `shutdownNow()`: requests stopping the **entire executor** and returns pending tasks.
- `Future.cancel(true)`: attempts to cancel **one task** per the Future/executor contract.

A `Future` marked canceled **does not prove worker cleanup has completed**. If a running thread is canceled, the Future can transition states before the task's `finally` block finishes running; `Future.get()` can throw `CancellationException` without waiting for the cleanup step itself.

Therefore, if a resource's lifecycle requires knowing that cleanup has finished, you can use a `CountDownLatch` in `finally`, a status signal, or wait for executor termination. Do not rely solely on `isCancelled()` to close resources that the task may still be using.

### Pending Tasks After `shutdownNow`

The `List<Runnable>` returned by `shutdownNow()` is not a list of all failed work; it is the unstarted tasks returned by the executor. It may contain `FutureTask` wrappers when work was submitted via `submit`. If retries are needed, you must account for tasks that may have already started, idempotency, deduplication, and durable storage requirements. An in-memory pool **does not replace a durable job queue**.

## 13. Avoiding Thread Leaks via Per-Task Cleanup

A thread pool worker can run **many consecutive tasks on the same thread**. Thus, `ThreadLocal` data can persist after a task finishes and appear in the next task if not removed.

Example of the risk:

```java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

void process(String id) {
    REQUEST_ID.set(id);
    // If remove() is forgotten, the worker thread can carry the old id to another task.
}
```

This is an illustrative snippet. Beyond incorrect data: if a `ThreadLocal` points to a large object, session, or resource, a long-lived pooled worker can retain that object longer than intended, causing **memory retention**.

Use `try/finally`:

```java
REQUEST_ID.set(id);
try {
    processRequest();
} finally {
    REQUEST_ID.remove();
}
```

### Example 4: Verifying That `ThreadLocal` Is Cleaned Up

Create `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        Future<?> first = executor.submit(() -> {
            CONTEXT.set("request-123");
            try {
                System.out.println("first=" + CONTEXT.get());
            } finally {
                CONTEXT.remove();
            }
        });
        first.get();

        Future<?> second = executor.submit(() ->
                System.out.println("second=" + CONTEXT.get()));
        second.get();

        executor.shutdown();
        boolean terminated = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("terminated=" + terminated);
    }
}
```

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

Output if the executor finishes within the deadline:

```text
first=request-123
second=null
terminated=true
```

`newSingleThreadExecutor` runs tasks sequentially, reusing the worker to show that the context was removed; `Future.get()` of the first task completes before the second task is submitted. If `CONTEXT.remove()` were forgotten, the second task could see `request-123` instead of `null`. That can leak information between requests.

**Scope:** `ThreadLocal.remove()` cleans up the context set by the task; it does not replace closing sockets, streams, connections, or the executor itself. For resources used inside a task, you still need the corresponding `try-with-resources`/`finally`.

## 14. Safe Shutdown with Exceptions and `try/finally`

Common paths where cleanup is missed:

- Pool construction/initialization succeeds, but subsequent code throws an exception before calling `shutdown()`.
- The caller returns early or is canceled while waiting on `Future.get()`.
- The `shutdown()` call sits after an operation that can throw an unchecked exception.
- A worker finishes a task but forgets to `close()` an opened resource.

Resource ownership pattern:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    runWorkflow(executor);
} finally {
    boolean stopped = ExecutorStopper.stop(executor);
    if (!stopped) {
        System.err.println("executor still not confirmed terminated");
    }
}
```

This illustrative snippet uses the `ExecutorStopper` helper from Section 7 and an application-defined `runWorkflow` method. `finally` runs when leaving the scope normally or via an exception; however, there is no magic that forces uncooperative threads to exit. Cleanup should only be considered successful when termination is confirmed.

### Do Not Accidentally Overwrite the Original Exception

If cleanup code inside `finally` throws its own exception, it can mask the primary exception that caused the workflow to fail. In production code, you must decide how to record shutdown failures (logging, suppressed exceptions, aggregated results) without losing the root cause. `try-with-resources` has built-in suppressed-exception handling for `AutoCloseable` resources, whereas on **JDK 17**, `ExecutorService` ownership is normally managed through explicit shutdown as shown in these examples.

### About `ExecutorService.close()` in Newer JDKs

In newer JDKs, `ExecutorService` can be used as an `AutoCloseable` thanks to the `close()` method added to the interface (starting in Java 19). Do not assume that `try (var executor = ...)` will compile as-is on **JDK 17**. `close()` in newer JDKs has its own shutdown/wait semantics; when specific deadlines and cancellation policies are required, you still need to understand the API contract and manage interruption/timeouts deliberately.

## 15. How Do Thread Leaks and Resource Leaks Differ?

Several closely related phenomena should be distinguished:

| Phenomenon | Symptoms | Common Causes |
| --- | --- | --- |
| **Thread leak** | Live thread count grows, many workers wait forever, JVM fails to exit | Creating pools without shutdown, hung tasks |
| **Intentional thread retention** | Worker threads stay alive even with no tasks | Pool kept by owner for reuse; not necessarily a leak |
| **Queue backlog** | Long queue, growing heap, slow responses | Producer faster than consumer, unbounded queue |
| **`ThreadLocal` memory retention** | Heap retains objects for worker lifetime | Failing to call `ThreadLocal.remove()` |
| **In-task resource leak** | Connections/file descriptors not returned | Missing `try-with-resources`/`finally` |
| **Deadlock or starvation** | Workers alive but making no progress | Wrong lock order, waiting on a Future in too small a pool |
| **Incomplete shutdown** | `isShutdown()==true`, `isTerminated()==false` for a long time | Tasks ignoring cancellation, blocked I/O, wait cycles |

**Not every waiting thread is a leak.** A pool that lives for the entire lifecycle of a service can be valid. The issue is the gap between the **threads and resources expected by design** and the **threads/resources still held when the owner no longer needs them**.

A worker waiting on a queue ready to process more tasks is normal while the application is `RUNNING`. It becomes a bug if the owning component has logically "closed" but forgot to stop the executor.

## 16. Locks and Waiting on Futures Can Self-Deadlock a Pool

A bug not strictly caused by forgetting shutdown is **thread-starvation deadlock**: every worker in the pool is waiting for another task **submitted to that same pool**, leaving no free worker to run the new task.

Conceptual example (do not run to induce a hang):

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> {
    Future<Integer> child = pool.submit(() -> 42);
    return child.get(); // The sole worker waits for child, which cannot run.
});
```

This is illustrative code; it requires importing executor/`Future` classes and handling checked exceptions in a `Callable`-style lambda. The sole worker is waiting on `child.get()`; `child` is waiting for its turn to run on that very worker. `shutdown()` will not resolve the cycle by itself; `shutdownNow()` can send an interrupt to the worker, but it requires task cooperation and error-handling code.

A monitor deadlock can also prevent termination from arriving. When debugging, examine **thread dumps**, stack traces, worker counts, queues, and dependencies among Futures/tasks/locks.

Prevention measures include: avoiding having a task block waiting on a child task in the same pool with insufficient workers, separating blocking/CPU workloads where appropriate, structuring tasks without cyclic dependencies, and designing timeouts/cancellation instead of indefinite waits.

## 17. Monitoring: Knowing Whether a Pool Is Leaking or Just Busy

When diagnosing a `ThreadPoolExecutor`, you can observe metrics such as:

- `getPoolSize()`: current number of workers in the pool.
- `getActiveCount()`: **approximate** number of workers currently executing tasks.
- `getQueue().size()`: current queue backlog (a snapshot that can change immediately).
- `getCompletedTaskCount()`: approximate number of completed tasks tracked by the executor.
- `getLargestPoolSize()`: highest pool size recorded.
- `isShutdown()`, `isTerminated()`: lifecycle milestones.

These values are **not a multi-field transactional snapshot**. Reading each metric can reflect slightly different instants, so use them to observe trends rather than as conditions for workflow correctness.

### Supporting JVM Tools

- `jcmd <pid> Thread.print`: captures a thread dump to see where workers are `RUNNABLE`, `WAITING`, `TIMED_WAITING`, or `BLOCKED`.
- Java Flight Recorder (JFR): records threads, blocking, allocations, and related events when needed.
- `jstack` or equivalent tools: assists thread dump analysis in appropriate environments.
- `ThreadMXBean`: observes thread counts, deadlock detection, and JVM thread information.

These are **diagnostic tools**, not runnable code from this article. Clear thread names from a `ThreadFactory` help identify which pool has not stopped. Thread counts over time, shutdown states, and stack traces are usually more informative than a single snapshot.

### Signs That Warrant Investigation

```text
After a test / request / service lifecycle ends:
  the number of threads named "worker-..." keeps increasing across runs;
  many threads wait on queue.take() even though the owner has closed;
  isShutdown() == false on a pool that should have been released;
  or isShutdown() == true but isTerminated() never becomes true.
```

Do not lump all of these cases together as the same bug. A pool still `RUNNING` is a missing shutdown; a shut-down pool with stuck tasks is a cancellation/liveness issue; a growing queue is a backpressure issue.

## 18. Rejected Execution: Race Between `submit` and `shutdown`

Two threads can race:

```text
Thread A                              Thread B
--------                              --------
if (!executor.isShutdown()) ...
                                      executor.shutdown()
executor.submit(task) -> REJECTED
```

`isShutdown()` is only a point-in-time observation; it does not form a transaction with `submit()`. Therefore, submission code must handle `RejectedExecutionException` or the contract of the configured rejection policy.

Example:

```java
try {
    executor.execute(task);
} catch (RejectedExecutionException e) {
    reportNotAccepted(task);
}
```

This is an illustrative snippet where `executor`, `task`, and `reportNotAccepted` are application-defined. If a task must not be lost, the rejection path may need to persist it durably, retry on another executor in a controlled way, or report an error to the caller.

Avoid designing a "custom accepting flag" separate from the executor without synchronization; it can introduce new races. A sound shutdown protocol typically stops accepting requests at the API/service boundary, while every task-submission path still treats rejection as a valid outcome to handle.

## 19. `ScheduledExecutorService` Also Needs Shutdown

`ScheduledExecutorService` accepts delayed or periodic tasks. If you create `Executors.newSingleThreadScheduledExecutor()` per object/request and never shut it down, workers and scheduled tasks can outlive their intended scope.

Some implementations such as `ScheduledThreadPoolExecutor` have specific policies for **delayed tasks** and **periodic tasks** upon shutdown. Do not assume every scheduled task runs or is canceled identically across all implementations.

Points to check:

- Do any periodic tasks continue or stop when `shutdown()` is called?
- Under what policy are already-submitted delayed tasks that have not yet come due handled?
- When canceling a scheduled future, does the queue retain the pending wrapper until its scheduled execution time?
- With `ScheduledThreadPoolExecutor`, `setRemoveOnCancelPolicy(true)` can help remove canceled tasks from the queue sooner in appropriate situations.
- Only after the policies and tasks finish does the executor become `terminated`.

Also track resources used by scheduled tasks: canceling a timer does not automatically close connections or clear `ThreadLocal` data created by the job.

## 20. Bounded Queues, Pool Size, and Total Resources

Avoiding thread leaks is not only about closing pools. A pool with a proper lifecycle can still face **load exceeding its processing capacity**, leading to many queued tasks and memory retention.

For instance, `Executors.newFixedThreadPool(n)` normally has an effectively unbounded queue. If producers submit 100,000 tasks per second while workers only process 10,000, the backlog will grow. Even if the thread count is stable, heap usage and latency can be pushed to the limit.

When you want load control, you can configure `ThreadPoolExecutor` with a bounded queue and an explicit rejection policy:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4, 4, 0, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100));
```

This is an illustrative snippet requiring imports for `ThreadPoolExecutor`, `TimeUnit`, and `ArrayBlockingQueue`. When all four workers are busy and the queue is full, new requests can be rejected according to the chosen rejection policy. You must handle **backpressure** rather than creating an unbounded number of waiting tasks.

Choose queue capacity, pool size, and task timeouts realistically. A bounded queue does not automatically solve hung tasks: if all workers wait forever, the queue will fill up and submissions will be rejected. You still need timeouts/cancellation and sound liveness design.

## 21. How to Test Lifecycle Behavior

A good test does not rely on `Thread.sleep(100)` and guess that the pool has stopped. It should establish controlled preconditions using `CountDownLatch`, `Future`, or appropriate synchronization primitives.

**Things worth testing:**

1. After `shutdown()`, new task submissions are handled according to the rejection policy.
2. Already-submitted tasks complete on the graceful path when tasks cooperate.
3. `awaitTermination` returns `false` when a task is intentionally prevented from finishing.
4. Once the task's latch is opened or interruption is handled, the executor transitions to `terminated`.
5. `shutdownNow()` sends interrupts to interruptible tasks and returns unstarted pending tasks (in coordinated scenarios).
6. Cleanup code runs in `finally`, even on exceptions or cancellation.
7. After each test run that creates a pool, the owner **must close** the pool so the test suite does not accumulate workers.

### Mini Test Using Standard Assertions

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> value = executor.submit(() -> 42);
    if (value.get() != 42) {
        throw new AssertionError("wrong result");
    }
} finally {
    executor.shutdownNow();
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        throw new AssertionError("pool did not stop");
    }
}
```

This illustrative snippet sits inside a method declaring `throws InterruptedException, ExecutionException` (or `throws Exception`), with imports for `ExecutorService`, `Executors`, `Future`, and `TimeUnit`. The key is checking **task outcome** and **termination** separately.

In real production code, instead of calling `shutdownNow()` immediately in `finally`, you usually choose graceful shutdown first and fall back based on data requirements. When a test is interrupted, handle the interrupt flag and cleanup properly so you do not leak pools into subsequent tests.

## 22. A Practical Service Shutdown Procedure

Suppose a service has an executor handling background jobs and a request source submitting work. A safe shutdown needs a clear order:

1. **Stop accepting new requests** at the service's ingress boundary.
2. **Stop producers** from submitting new tasks to the executor; have a protocol to report rejections if races still occur.
3. **Call `shutdown()`** to drain already-accepted tasks.
4. **Wait with a deadline** using `awaitTermination()`. Pick the timeout based on business requirements, not an arbitrary infinite wait.
5. If the graceful deadline expires, **call `shutdownNow()`** to request cancellation of the remainder and inspect pending tasks.
6. **Wait again with a bound**; if not yet terminated, record the incomplete shutdown in metrics/logs and let the process orchestrator handle it.
7. **Close dependent resources** (database pools, files, sockets, etc.) in an order where the owner/tasks no longer need them, except resources that must be closed early to unblock I/O.
8. Reconcile **business outcomes** via `Future`, result channels, idempotency, or durable storage; termination does not replace confirming that a job committed.

**Crucial point:** the closing order must follow the **resource dependency graph**. If the executor still has tasks using the database and you close the database first, tasks can fail. If a task is stuck reading a socket, you may need to close the socket to wake it up; there is no single order that fits every system.

### Overall Deadline

If you call `awaitTermination(5s)` and then another `awaitTermination(5s)`, total waiting time can reach roughly **10 seconds** plus overhead. If the entire service must shut down within one overall deadline, allocate a budget or compute remaining time using `System.nanoTime()`; do not add independent timeouts unboundedly.

An expired timeout **is not a kill command**; it only informs the caller that it has waited long enough. Report the incomplete state rather than pretending workers have stopped.

## 23. Anti-Thread-Leak Checklist

Before shipping a component that uses an executor to production, check:

- **Owner:** Who creates the pool? Who is allowed to call `shutdown()`? Is it closed exactly once when its lifecycle ends?
- **Count:** Is a new pool created per request, per loop, or per retry? Where are thread and queue counts bounded?
- **Admission:** Once shutdown starts, are new task submissions rejected properly?
- **Tasks:** Does every task have an exit path, timeout, interruption contract, and cleanup?
- **Blocking:** Does any task hold a lock while waiting for another task in the same pool?
- **Futures:** Are task outcomes checked via `get()` or an error channel?
- **Queue:** Is there an unbounded backlog lacking backpressure?
- **`ThreadLocal`:** Is `remove()` called in `finally` for per-request data?
- **Resources:** Are files, sockets, streams, and connections closed?
- **Termination:** Is `awaitTermination()` called and its `false` branch handled?
- **Diagnostics:** Does the pool have thread names and metrics to trace hung workers?
- **Testing:** Do tests reliably clean up pools even when a test fails?

These are **lifecycle** checks; you do not need to wait until the JVM grows to thousands of threads before inspecting them.

## 24. Self-Check Questions

**Q1.** After `shutdown()`, is the executor guaranteed to have no remaining threads?

**Answer:** No. `shutdown()` initiates an orderly shutdown without waiting. Already-accepted tasks may continue running.

**Q2.** Are `isShutdown() == true` and `isTerminated() == false` contradictory?

**Answer:** No. The executor has entered shutdown, but some tasks or workers have not finished yet.

**Q3.** Does `shutdownNow()` "kill" a CPU-bound task that does not check for interruption?

**Answer:** Not guaranteed. It sends a cooperative cancellation request; the task can continue running.

**Q4.** What does `awaitTermination(2, SECONDS)` returning `false` mean?

**Answer:** The executor had not reached `terminated` within two seconds. Do not infer that all tasks failed or that all workers have stopped.

**Q5.** A method creates `newSingleThreadExecutor()` on every request without shutting it down. Why is this dangerous?

**Answer:** Each request can leave an idle-but-alive worker behind; total threads and resources grow with the number of requests.

**Q6.** If a task has completed `Future.get()` with the right result, can you skip closing the executor?

**Answer:** No. A `Future` task completing does not mean the worker pool has ended its lifecycle. The owner still needs to shut it down when it is no longer needed.

**Q7.** Why is `ThreadLocal.remove()` needed in `finally`?

**Answer:** Pooled threads can run multiple tasks; old request data can remain retained and be seen by later tasks, causing memory retention or context leaks.

**Q8.** Does `Future.cancel(true)` prove that worker cleanup has finished?

**Answer:** No. The `Future` canceled state can arrive before the task finishes cleanup; you need a separate signal or proper termination.

**Q9.** A task in a single-thread executor submits a child task to the same pool and calls `get()` to wait for it. What is the risk?

**Answer:** Thread-starvation deadlock: the sole worker waits for a task that has no worker available to run it.

**Q10.** After `shutdown()`, thread A checks `!isShutdown()` and then submits while thread B calls `shutdown()`. Is submission guaranteed to succeed?

**Answer:** No. There is a race between the check and the submission; the caller must handle rejection.

**Q11.** Can a `ThreadFactory` creating daemon threads replace proper shutdown?

**Answer:** No. Daemon threads can let the process exit without waiting for tasks to flush/clean up; it is not safe resource management.

**Q12.** Once a pool has terminated, have all jobs necessarily committed to the database successfully?

**Answer:** Not necessarily. Tasks can fail, be canceled, or exit before committing. You must check outcomes and have transaction/recovery handling at the business layer.

## 25. Summary

**`ExecutorService` is a resource with a lifecycle**, not just a function to run tasks. Avoiding thread leaks requires **clear ownership, stopping admission at the right time, time-bounded shutdown, cooperative task cancellation, resource cleanup, and termination confirmation**.

A safe pattern is **`shutdown()` → `awaitTermination()` → if needed `shutdownNow()` → `awaitTermination()` again**. However, `shutdownNow` only attempts interruption rather than forcing tasks to stop; a timed wait only reports whether termination occurred within the wait window; and the terminated state does not replace checking business outcomes.

Good design starts when the pool is created: reuse at the appropriate scope, avoid creating pools indiscriminately per request, name workers, bound backlogs, clean up `ThreadLocal`/resources, avoid tasks waiting on each other in the same pool, and write lifecycle tests. In general Java concurrency, **closing an executor is just as important as submitting tasks to it**.
