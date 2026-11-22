# beforeExecute(), afterExecute(), and How to Detect Exceptions from submit() Tasks in Java

> **Scope:** The Executor Framework in **general Java concurrency**, specifically the `ThreadPoolExecutor.beforeExecute(Thread, Runnable)` and `afterExecute(Runnable, Throwable)` hooks, exception propagation across `execute()`, `submit()`, and `Future`, as well as logging, metrics, cleanup, and lifecycle. Spring-specific interception, schedulers, or thread-pool abstractions are not covered here, as those have their own separate chapter.

## 1. The Real-World Problem: A Task Fails, but No Error Appears in the Logs

Suppose an application runs many tasks in a `ThreadPoolExecutor`. When executing a `Runnable` that throws a `RuntimeException` via `execute()`, the exception can escape from the worker's `run()` method, causing the thread to terminate abnormally and appear in the uncaught exception handling path.

However, when submitting a failing task using `submit()`, many developers notice that:

- `afterExecute(r, t)` **is called**, but `t == null`;
- no stack trace automatically appears the way they expected;
- `Future.get()` instead throws an `ExecutionException` wrapping the actual exception.

This is not a bug in Java. `submit()` typically **wraps the Runnable/Callable in a `FutureTask`**. `FutureTask.run()` catches the task's exception, stores the outcome in the Future's state, and **does not rethrow that same exception out of `run()`**. Therefore, `ThreadPoolExecutor` usually sees the wrapper's `task.run()` call return normally and passes `null` for the hook's `Throwable` parameter.

**Key takeaway:** `afterExecute` is not a "catch-all trap for every error" if you only inspect the `Throwable` parameter. When `Runnable r` is a completed `Future<?>`, you must inspect the outcome via `Future.get()` and handle `ExecutionException` / `CancellationException` appropriately.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between `Executor.execute(Runnable)` and `ExecutorService.submit(...)` in terms of task wrapping, results, and exceptions.
2. Explain accurately when `beforeExecute`, `afterExecute`, and `terminated` are invoked by `ThreadPoolExecutor`.
3. Explain what the `Throwable t` parameter of `afterExecute` represents and why it is usually `null` with `submit()` even when the task throws an exception.
4. Write an `afterExecute` hook that detects failures for both tasks submitted directly via `execute()` and completed `Future` tasks.
5. Distinguish between `ExecutionException`, `CancellationException`, `InterruptedException`, rejection, and errors originating inside the hook itself.
6. Understand cases where **hooks do not run**: tasks not yet executed by a worker, rejected tasks, tasks removed from the queue, tasks run by a policy outside a worker, or when `beforeExecute` throws an exception.
7. Design logging, metrics, tracing, and `ThreadLocal` cleanup that are **fast, do not block indefinitely, and do not throw unexpected exceptions**.
8. Test results on Java 17 with a controlled execution schedule and analyze memory consistency and pool lifecycle.

## 3. First, Understand the Two Execution Paths

### 3.1. `execute(Runnable)`: Running a Caller-Provided Task

Example:

```java
pool.execute(() -> {
    throw new IllegalStateException("direct task failed");
});
```

This is an **illustrative snippet**; `pool` must be an `Executor`/`ThreadPoolExecutor` created externally. A `Runnable` directly throws an unchecked exception when `run()` executes. For a standard `ThreadPoolExecutor`, this throwable escapes `task.run()` and is received by `afterExecute(r, t)` via `t`; afterward, the worker may terminate abnormally and be replaced if the executor needs to maintain the pool.

Do not assume every `execute()` call always produces a non-null `t`: a caller can also call `execute(futureTask)` or `execute(wrapper)` where the wrapper catches exceptions itself, in which case `run()` does not throw. What determines this is whether the **actual Runnable invoked by the worker** lets an exception escape from `run()`.

### 3.2. `submit(...)`: Wrapping the Task and Returning a Future

Example:

```java
Future<Integer> result = pool.submit(() -> {
    throw new IllegalArgumentException("submitted task failed");
});
```

This is an illustrative snippet; it requires importing `java.util.concurrent.Future` and a `pool` that is an `ExecutorService`. `submit(Callable<T>)` typically creates a `RunnableFuture<T>` such as `FutureTask`, passes that wrapper to `execute()` internally, and returns the `Future`.

When `Callable.call()` throws `IllegalArgumentException`:

- `FutureTask` catches the throwable and stores the **completed exceptionally** state;
- `Future.get()` throws `ExecutionException`, whose `getCause()` is the original `IllegalArgumentException`;
- `FutureTask.run()` does not rethrow that exception outward;
- therefore, `afterExecute(r, t)` usually receives `t == null`;
- `r` can be an object implementing the `Future<?>` interface, so the hook can read the outcome from the `Future` after `task.run()` completes.

Similarly, `submit(Runnable)` also typically wraps the task to provide a `Future`, even though `Runnable` does not return a value of type `T`.

### 3.3. Core Comparison Table

| Question | Direct `execute(() -> throws)` | `submit(() -> throws)` |
|---|---|---|
| Object executed by worker | Caller-provided `Runnable` (or caller-submitted wrapper) | Usually `FutureTask`/`RunnableFuture` |
| API return type | `void` | `Future<?>` / `Future<T>` |
| When task logic throws an unchecked exception | Can escape `Runnable.run()` | Usually caught and stored by the wrapper |
| `afterExecute(r, t)` | `t` usually contains the throwable if it escaped `run()` | `t` is usually `null` |
| Caller retrieves error via `Future.get()` | No `Future` from the `execute` call itself | `ExecutionException.getCause()` |
| Worker terminated by task exception | Possibly, if the exception actually escapes `run()` | Usually no, because `FutureTask` caught the exception |
| `isDone()` / `isCancelled()` | Not available unless the task itself is a `Future` | Available on the returned `Future` |

This table describes the **standard execution path on `ThreadPoolExecutor` and `FutureTask`**, not a claim about every `Executor` implementation or every custom `Runnable` wrapper.

## 4. Main Hooks of ThreadPoolExecutor

`ThreadPoolExecutor` has three hook methods designed to be overridden by subclasses:

```java
protected void beforeExecute(Thread t, Runnable r)
protected void afterExecute(Runnable r, Throwable t)
protected void terminated()
```

These are **illustrative API signatures**, not a standalone Java class.

### `beforeExecute(Thread thread, Runnable task)`

- Called by the worker thread **right before running `Runnable.run()`** for the task picked up for execution.
- Used to attach instrumentation, capture timestamps, set thread-local context, increment a "task started" metric, or perform lightweight checks.
- The `thread` parameter indicates the executing worker thread; `task` is the actual `Runnable` handed to the worker, **which may be a `FutureTask` wrapper** rather than the original `Callable`.
- The JavaDoc recommends that overrides call `super.beforeExecute(thread, task)`, typically **at the beginning** of the method.

**Danger:** If `beforeExecute` itself throws an exception, the task's `run()` may **not be called**, and `afterExecute` **will not be called for that task** under the standard worker loop structure. Therefore, do not place arbitrary validation that throws exceptions inside this hook if you want consistent completion tracking.

### `afterExecute(Runnable task, Throwable error)`

- Called by the worker **after `task.run()` finishes**, whether normally or by throwing a throwable, **provided `beforeExecute` returned normally**.
- `error` is non-null when a throwable **escapes `task.run()`** into the worker control loop.
- `error` is usually `null` if `run()` returns normally, even when **the logic inside a `FutureTask` failed** and the wrapper caught the exception.
- The `task` parameter is the `Runnable` wrapper that the worker just ran, which may also implement `Future<?>`.
- You can read `Future.get()` if the `Future` **has already completed** to determine a stored exception or cancellation.
- The JavaDoc recommends calling `super.afterExecute(task, error)`, typically **at the end** of the method.

**Do not use `afterExecute` for long-running work or blocking I/O.** The hook runs on the **worker thread** responsible for processing the work queue. If the hook takes several seconds to make a synchronous network or logging call, the worker is not free for the next task; throughput drops, the queue grows, and backpressure or deadlock can occur.

### `terminated()`

Called when the executor **transitions to the terminated state** (after tasks and workers have reached the end of their lifecycle per contract), typically used to record a metric or clean up shared executor-owned state. This is **not a per-task hook**.

`terminated()` does not replace the caller's `shutdown()` or `awaitTermination()`; those serve two different roles.

## 5. Hook Sequence in the Worker Loop

Conceptual model of `ThreadPoolExecutor`:

```text
Worker takes task from workQueue or receives firstTask
             |
             v
    beforeExecute(thread, task)
             |
             v
         task.run()
         /       \
    returns     throws
       \         /
        \       /
             v
   afterExecute(task, throwableOrNull)
             |
             v
     worker continues / terminates
```

This is a **simplified model**; the actual implementation also acquires/releases the worker lock, updates counters, handles interrupts, shutdown, and worker replacement.

**Important detail:** In the standard implementation, the `beforeExecute` call sits outside the `try/finally` block that wraps `task.run()` and `afterExecute`. Therefore, if `beforeExecute` itself throws an exception, `task.run()` never runs and `afterExecute` is not called. In addition, if `afterExecute` itself throws an exception, the worker may also terminate abnormally and complicate exception handling and lifecycle management.

**Do not confuse the second parameter of `afterExecute` with "every `Throwable` that occurred."** It only reflects the throwable that escaped `task.run()` along the execution path delivered to the hook.

## 6. Why Does afterExecute(Throwable) Miss submit() Errors?

`AbstractExecutorService.submit` uses a mechanism like `newTaskFor(...)` to convert a `Runnable`/`Callable` into a `RunnableFuture`, typically `FutureTask`, and then calls `execute` with that wrapper.

The idea of `FutureTask.run()`:

```text
try:
    result = callable.call()
    save successful result
catch Throwable ex:
    save failure ex inside Future
return from run()
```

This description is **pseudocode** only, not bytecode or the complete implementation of `FutureTask`.

If the worker calls `task.run()` and the wrapper returns normally, `ThreadPoolExecutor` does not see an escaping `Throwable`. The hook therefore receives `t == null`. However, **`Future.get()` knows about the failure** because `FutureTask` stored the outcome.

This explains a commonly seen issue:

```java
// Illustrates insufficient error monitoring.
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);
    if (error != null) {
        log(error);
    }
}
```

This is an **illustrative method**, requiring `log(Throwable)` and a subclass of `ThreadPoolExecutor`. It detects throwables directly from `execute(Runnable)`, but can miss most exceptions stored in a `Future` by `submit()`.

The proper approach is to **check both channels**, while handling cancellation, interruption, and non-`Future` tasks.

## 7. Safe Future-Checking Hook Pattern

Pattern used inside a `ThreadPoolExecutor` subclass:

```java
@Override
protected void afterExecute(Runnable task, Throwable thrown) {
    try {
        Throwable failure = thrown;

        if (failure == null && task instanceof Future<?> future
                && future.isDone()) {
            try {
                future.get(); // completed Future: no longer waits for the result
            } catch (CancellationException e) {
                recordCancellation(e);
            } catch (ExecutionException e) {
                failure = e.getCause();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                recordHookInterrupted(e);
            }
        }

        if (failure != null) {
            recordTaskFailure(failure);
        }
    } finally {
        super.afterExecute(task, thrown);
    }
}
```

This is an **illustrative method**, not a standalone class: it requires imports for `Future`, `ExecutionException`, `CancellationException`, the `record...` methods, and a `ThreadPoolExecutor` subclass. Metric/logging operations inside the hook must **not throw unhandled exceptions and must not block for long**.

The `task instanceof Future<?>` check is necessary because with `submit()`, the task is usually a `FutureTask`. However, callers can also pass a `FutureTask` directly to `execute()`, or a subclassed executor overriding `newTaskFor` can return a different `RunnableFuture` type. Therefore, rely on the **`Future` interface** rather than trying to identify tasks solely by which submission method was called.

### Why Check `future.isDone()`?

`afterExecute` is called after `task.run()` completes, and for a standard `FutureTask`, the `Future` is already done. However, to avoid accidentally making a blocking `get()` call on a custom `Runnable` that also implements `Future` with unusual semantics, the pattern checks `isDone()` first. `isDone` returning `true` covers success, failure, and cancellation.

**Note:** A custom `Future` might violate practical instrumentation expectations, or `isDone` might have different semantics; do not use an arbitrary `Future` wrapper without a clear contract. With the JDK's `FutureTask`, the check above is sound.

### Handling Distinct Outcomes

- **Task succeeded:** `future.get()` returns the result; the hook does not need to use the result if it only collects metrics.
- **Task failed:** `future.get()` throws `ExecutionException`; use **`getCause()`** to record the root error, not just log the wrapper.
- **Task cancelled:** `future.get()` throws `CancellationException`; cancellation usually needs a separate metric and should **not be treated as a business failure by default**.
- **Hook interrupted:** `get()` can throw `InterruptedException`. If caught and not propagated, restore the interrupt status and record an appropriate metric without letting the hook throw further.
- **`thrown != null`:** An actual error escaped `Runnable.run()`; there is no need to call `Future.get()` just to look up the error again once the rule defines the priority channel.

**Do not catch `Exception` and silently ignore everything**: doing so hides both task errors and instrumentation errors. State the error-recording policy explicitly and keep the hook simple.

## 8. Runnable Java 17 Example with Both execute() and submit()

The following program creates a `ThreadPoolExecutor` subclass `ObservedPool` with one worker. In `beforeExecute`, the pool counts task starts. In `afterExecute`, the pool checks:

- `Runnable task` that also implements `Future<?>`: reads the outcome via `Future.get()`;
- non-`Future` tasks with `error != null`: records the exception type from direct `execute()`.

A `CountDownLatch` ensures `main` **waits for both `afterExecute` invocations to finish** before printing results. `UncaughtExceptionHandler` is set to an empty handler **only so the demo stdout is deterministic** when the `execute()` task intentionally throws an exception; do not use this error-swallowing pattern in production.

Create **`ExecutorHookDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ExecutorHookDemo {
    static final class ObservedPool extends ThreadPoolExecutor {
        final AtomicInteger beforeCount = new AtomicInteger();
        final AtomicInteger afterCount = new AtomicInteger();
        final AtomicReference<String> executeError = new AtomicReference<>("none");
        final AtomicReference<String> submitError = new AtomicReference<>("none");
        final CountDownLatch completedHooks = new CountDownLatch(2);

        ObservedPool() {
            super(1, 1, 0, TimeUnit.MILLISECONDS, new LinkedBlockingQueue<>());
            setThreadFactory(task -> {
                Thread thread = new Thread(task, "observed-worker");
                thread.setUncaughtExceptionHandler((t, e) -> { });
                return thread;
            });
        }

        @Override
        protected void beforeExecute(Thread thread, Runnable task) {
            super.beforeExecute(thread, task);
            beforeCount.incrementAndGet();
        }

        @Override
        protected void afterExecute(Runnable task, Throwable error) {
            try {
                if (task instanceof Future<?> future) {
                    if (future.isDone()) {
                        try {
                            future.get();
                        } catch (ExecutionException e) {
                            submitError.set(e.getCause().getClass().getSimpleName());
                        } catch (CancellationException e) {
                            submitError.set("cancelled");
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            submitError.set("interrupted");
                        }
                    }
                } else if (error != null) {
                    executeError.set(error.getClass().getSimpleName());
                }
            } finally {
                afterCount.incrementAndGet();
                completedHooks.countDown();
                super.afterExecute(task, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ObservedPool pool = new ObservedPool();
        try {
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalArgumentException("from submit");
            });
            try {
                failed.get();
            } catch (ExecutionException e) {
                System.out.println("callerSaw=" + e.getCause().getClass().getSimpleName());
            }

            pool.execute(() -> {
                throw new IllegalStateException("from execute");
            });

            if (!pool.completedHooks.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("hooks timed out");
            }
            System.out.println("beforeCount=" + pool.beforeCount.get());
            System.out.println("afterCount=" + pool.afterCount.get());
            System.out.println("submitHookError=" + pool.submitError.get());
            System.out.println("executeHookError=" + pool.executeError.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 ExecutorHookDemo.java
java ExecutorHookDemo
```

**Verified stdout:**

```text
callerSaw=IllegalArgumentException
beforeCount=2
afterCount=2
submitHookError=IllegalArgumentException
executeHookError=IllegalStateException
```

### Explaining Why the Output Does Not Depend on the Scheduler

1. `pool.submit(...)` returns a `Future` for a task that **intentionally** throws `IllegalArgumentException`.
2. `main` calls `failed.get()`, receives `ExecutionException`, and reads its cause. Thus `callerSaw=IllegalArgumentException` is always printed once the task runs to the throw statement and the normal demo flow completes.
3. `FutureTask.run()` stores the failure; in `afterExecute`, `task instanceof Future<?>` is true, `future.isDone()` is true, `future.get()` throws `ExecutionException`, and the hook records `submitHookError`.
4. `pool.execute(...)` receives a direct `Runnable`, which throws `IllegalStateException` out of `run()`; the hook receives a non-null `error` and records `executeHookError`.
5. Both tasks go through `beforeExecute` and `afterExecute` in the verified scenario. `AtomicInteger` ensures thread-safe counting, yielding `beforeCount=2` and `afterCount=2`.
6. `completedHooks` counts down after each after-hook processes the outcome. `main` waits via `await(5, SECONDS)`, so it reads hook state **after** both completions rather than guessing with `Thread.sleep`.
7. `CountDownLatch` provides the proper memory-consistency effects, so `main` reliably observes the data written by the hooks before `countDown`.
8. `setUncaughtExceptionHandler((t,e)->{})` intentionally suppresses printing the `execute` error in this lab so stdout can be compared cleanly. **Production code must have proper uncaught exception handling**: logging, metrics, alerts, or escalation. Never copy an empty handler into critical workloads.

**Note:** The program only has one `submit` task and one `execute` task; the `submitError`/`executeError` fields hold a single latest string, not a full error-collection system for many tasks. In real production systems, use centralized logging/tracing or metric counters rather than writing to a single `AtomicReference`. The demo waits on the latch with a timeout to avoid hanging indefinitely in tests.

## 9. Distinguishing "Hook Finished" from "Task Completed"

With `submit()`, `FutureTask` can mark the `Future` as done **before `afterExecute` finishes**. Therefore:

- `future.get()` confirms that **the task logic has an outcome**, with the memory guarantees of `Future`.
- It **does not necessarily confirm that all logging or cleanup inside `afterExecute` has finished**.
- If the caller needs to observe exact hook completion (for example, when testing a custom pool), it needs a separate signal such as the demo's `CountDownLatch`, or an explicitly designed completion protocol.

This is why the demo does not simply call `failed.get()` and immediately check `submitError`. `main` also waits on `completedHooks`, giving hook verification a clear synchronization boundary.

**Similarly:** `shutdown()` does not wait for hooks or tasks to finish. `awaitTermination()` only returns `true` once the executor has actually terminated, but if you need a specific task's result, `Future.get()` is usually the more direct API.

## 10. When Are Hooks Not Called at All?

Do not treat hooks as an event meaning "every submitted task was accepted and finished." Hooks belong to the **worker execution path** of `ThreadPoolExecutor`, not an audit system for every submission in every state.

| Scenario | Do `beforeExecute` / `afterExecute` run? |
|---|---|
| Task is picked up by a worker and `run()` returns normally | Usually both run |
| Task is picked up by a worker, `run()` throws an unchecked throwable | `beforeExecute` runs, and `afterExecute` receives the throwable if the before-hook returned normally |
| Task runs via `FutureTask` and stores a failure | Hooks still run if the worker actually invoked the wrapper; `t` is usually `null` |
| Task is rejected at `execute`/`submit` | **No**, because no worker executes the task |
| Task is still in the queue, returned by `shutdownNow()`, never run | **No**, because it never entered a worker |
| Task is removed from the queue by `remove`/`purge` before a worker picks it up | **No** |
| `beforeExecute` itself throws an exception | `task.run()` is not called; `afterExecute` **is not called** for that task |
| `CallerRunsPolicy` runs the task in the caller thread when the pool is saturated | Does not go through the worker loop ⇒ do not expect pool hooks to run |
| `DiscardPolicy` silently drops the task | Does not go through the worker loop ⇒ no hooks |
| Caller invokes `Runnable.run()` directly outside the pool | Does not go through a `ThreadPoolExecutor` worker ⇒ no hooks |

**Cancelled tasks (`cancel`) also require distinction:** A `FutureTask` that is cancelled **while still in the queue and later has `run()` called by a worker** may go through the hooks; `run()` sees the cancelled state and returns quickly. However, if it was removed from the queue or never processed by a worker, the hooks will never have a chance to run. Therefore, the `afterExecute` count **does not automatically equal the number of tasks ever submitted**.

### Rejection in `submit()` Has Its Own Caveat

A `submit()` implementation typically creates a `FutureTask` and then calls `execute`. If the executor uses `AbortPolicy` and rejects the task, `RejectedExecutionException` is thrown immediately to the caller. If it uses a handler that silently discards tasks, the caller may receive a `Future` that **is never done**, risking `get()` waiting forever. Do not choose a discard policy for work that requires reliable acknowledgment.

To track the number of tasks **accepted, rejected, completed, failed, and cancelled**, you must instrument both the **admission path** and the **outcome/completion path**, not just the after-hook.

## 11. How Dangerous Are Exceptions Inside the Hooks Themselves?

### `beforeExecute` Throws an Exception

```java
@Override
protected void beforeExecute(Thread t, Runnable r) {
    super.beforeExecute(t, r);
    throw new IllegalStateException("hook failed before task");
}
```

This is an **illustrative bug snippet** and should never go into production. When the before-hook throws, the task may not run and `afterExecute` is not called either. A `Future` for the skipped task may never transition to done without additional failure/cleanup handling. The worker may terminate abnormally.

Therefore, hooks should only perform **fast, bounded, and exception-safe** work. Do not put non-deterministic initialization logic, network queries, or external data parsing that can throw uncaught exceptions inside `beforeExecute`.

### `afterExecute` Throws an Exception

If the after-hook throws, the worker can terminate abnormally even though the task logic already finished. This disrupts metrics, logs, or the worker lifecycle; the pool may create a replacement worker when needed. **Never let logging/metrics throw out of the hook.** If instrumentation fails, handle or record it via a safe, bounded channel rather than breaking the executor.

### Do Not Block the Executor with Synchronous Logging

A hook that calls an HTTP endpoint or performs slow synchronous file writes on every task keeps **the worker occupied**. This can increase queue wait time, cause rejections, or even create a wait cycle if the logging destination also uses the same pool.

Better practices:

- Record simple metrics using counters or non-blocking/bounded telemetry tools.
- Use logging with proper queue/batching configuration; define a policy for when the log backend is full.
- Do not include tokens, passwords, sensitive payloads, or unfiltered exception messages in logs.
- Distinguish real errors from intentional cancellations so you do not trigger alert storms.
- Log an event ID or task ID so you know which work item failed, rather than only a class name as in the demo.

## 12. Designing Pre- and Post-Task Metrics

Hooks are commonly useful for:

1. Counting how many times **a worker starts a task** (`beforeExecute`).
2. Measuring **execution time on the worker** until `afterExecute` is called.
3. Counting success, failure, and cancellation outcomes.
4. Collecting thread name, queue depth, and active worker count.
5. Cleaning up `ThreadLocal`/context set for the task.
6. Alerting/tracking abnormal worker cases.

### Measuring Elapsed Time with a Monotonic Clock

An illustrative pattern:

```java
// Member of ThreadPoolExecutor subclass:
private final ThreadLocal<Long> startedNanos = new ThreadLocal<>();

@Override
protected void beforeExecute(Thread thread, Runnable task) {
    super.beforeExecute(thread, task);
    startedNanos.set(System.nanoTime());
}

@Override
protected void afterExecute(Runnable task, Throwable error) {
    try {
        Long start = startedNanos.get();
        if (start != null) {
            long durationNanos = System.nanoTime() - start;
            observeDuration(durationNanos);
        }
        // Can analyze Throwable/Future outcome here.
    } finally {
        startedNanos.remove();
        super.afterExecute(task, error);
    }
}
```

This is **illustrative code**; it requires `observeDuration(long)` to be fast and non-throwing, inside a configured subclass. `System.nanoTime()` is suitable for measuring **elapsed durations**, not wall-clock timestamps. If `beforeExecute` fails before completing, `afterExecute` may not run, so a separate cleanup path should be considered.

**Meaning of the metric:** The interval from before to after is the time the task ran on the worker (plus small hook overhead); **it does not include the time the task waited in the executor queue before a worker picked it up**. To measure queue wait time, you must record the enqueue/submit timestamp and associate it with the `Runnable` executed by the worker, typically via a decorator/wrapper or admission-path instrumentation.

### ThreadLocal Cleanup

`ThreadPoolExecutor` reuses platform worker threads. If a task leaves a `ThreadLocal` behind, a subsequent task running on the same worker may see stale context. Calling `ThreadLocal.remove()` in `afterExecute` is useful, but you must understand:

- Only clean up keys/context that your component **actually owns**.
- The hook is not called if the task runs outside a worker via a handler like `CallerRunsPolicy`.
- The hook is not called if `beforeExecute` throws an exception.
- If cleanup is needed **regardless of execution path**, a per-task wrapper using `try/finally` around the task's own logic is usually more reliable than a pool-level hook.
- If using context tracing in async tasks, you must have explicit rules for propagating context across task boundaries rather than expecting `ThreadLocal` to follow requests automatically.

## 13. Cancellation, Interruption, and Future Outcomes

A `Future` can have several outcome states:

```text
      NEW / running
         |        \
   completed       cancel(true/false)
      /   \              |
  value   failure       cancelled
           |               |
    get throws            get throws
 ExecutionException    CancellationException
```

This is a conceptual diagram; the internal states of `FutureTask`/JDK are more detailed.

### `CancellationException`

If `Future.cancel(...)` succeeds and the caller calls `get()`, the `Future` throws `CancellationException`. In a hook, this should not be lumped indiscriminately into business-logic task failures; it may be a legitimate cancellation during service shutdown.

### `InterruptedException`

With `get()`, a waiting thread can be interrupted and receive `InterruptedException`. If the hook catches it, restore the flag with `Thread.currentThread().interrupt()` if not propagating, and avoid altering status in a way that causes the worker to keep running subsequent tasks unaware it was interrupted.

**Attention:** `future.get()` after `future.isDone()` on a standard `FutureTask` no longer waits for task completion, but its signature still declares `throws InterruptedException` and different interface implementations exist. Handle the exception per the API rather than omitting the catch block thinking "once done, it can never throw."

### `cancel(true)` Is Not a Guaranteed Kill

`cancel(true)` typically requests interrupting the thread running the task. A task performing non-interruptible I/O or deliberately ignoring interrupts can keep running. A `Future` can be in the cancelled state while side effects continue; marking cancellation does not guarantee transactions rolled back or the thread stopped immediately.

### `isDone()` Does Not Mean Success

`isDone()` is `true` for success, failure, and cancellation. To detect a `submit` task failure, you cannot simply write:

```java
if (future.isDone()) {
    metrics.success(); // Wrong if completed exceptionally or cancelled.
}
```

This is an **incorrect illustrative snippet**. You must classify the outcome using `get()` after done or an appropriate result/callback channel. In particular, when `Future.get()` throws `ExecutionException`, **the real cause is in `getCause()`**.

## 14. How Can afterExecute Alter Task Observability?

Several impacts of instrumentation on a system:

- **Latency:** Slow hook processing delays the worker from picking up the next task.
- **Ordering:** Synchronous logging in a hook can let another thread finish first, changing observed ordering.
- **Contention:** Metrics sharing the same monitor/lock across all workers can become a bottleneck.
- **Memory:** Holding references to entire `Runnable` instances, payloads, or stack traces in unbounded collections can cause memory leaks.
- **Privacy/security:** Logging exception messages can expose query strings, tokens, or user data; filter according to security policy.
- **Lifecycle:** Hooks that throw exceptions cause workers to terminate and force the pool to handle replacement.
- **Backpressure:** If the logging pipeline is overloaded, a hook trying to push logs into a bounded queue with `put()` can block workers and propagate congestion back into the executor.

Therefore, hooks should be **observability-oriented**, have minimal side effects, and never alter business outcomes. If tasks need retries or transactions, build that in the job-management layer rather than stuffing arbitrary retry logic into `afterExecute`.

## 15. When Should You Prefer a Per-Task Wrapper?

Subclassing `ThreadPoolExecutor` is a systematic solution for **every task going through a pool's workers**. However, not every framework or application controls the pool class or guarantees every execution path goes through hooks.

In many cases, a **`Runnable` decorator/wrapper** is clearer:

```java
static Runnable observed(Runnable task) {
    return () -> {
        long started = System.nanoTime();
        try {
            task.run();
        } catch (RuntimeException | Error e) {
            recordFailure(e);
            throw e;
        } finally {
            recordDuration(System.nanoTime() - started);
            cleanupContext();
        }
    };
}
```

This is an **illustrative static method**; `recordFailure`, `recordDuration`, and `cleanupContext` are declared externally. The instrumentation methods must also be exception-safe so they do not mask the original error.

Advantages:

- The `try/finally` block is bound directly to the task logic rather than depending on a hook.
- Can be applied to any executor as long as every task is wrapped.
- If a task runs via `CallerRunsPolicy` on the caller thread, the wrapper still measures and cleans up.
- Context propagation, correlation IDs, and failure policies can be defined explicitly.

Limitations: If a task is **rejected before running**, the wrapper does not run either; rejection must be handled at submission time. For `Callable`, a similar decorator is needed that returns the value and rethrows exceptions.

### Exceptions in a Wrapper When Using submit

If the wrapper throws an exception, the `FutureTask` created by `submit` will still **catch and store** the exception; the caller must observe the `Future` if it needs to know the task failed. Wrapper logging helps surface errors early, but does not replace the completion contract.

## 16. Distinguishing Executor Error Classes

Not every exception around an executor is an error inside `task.run()`:

| Error source | Where it occurs | Does the hook see it? |
|---|---|---|
| Rejection due to saturated/shut-down pool | `execute`/`submit` call | Usually **no**, task is not run by a worker |
| Error inside `beforeExecute` itself | Worker hook before task | `afterExecute` is usually not called for that task |
| Throwable escaping a direct `Runnable` | `task.run()` on worker | `afterExecute` can receive it via `t` |
| Throwable from a `Callable` via `submit` | Stored by `FutureTask` | `t` is usually `null`; check `Future.get()` |
| Task cancelled before worker picks it up | `Future.cancel`, possibly removed from queue | Hook may not run |
| Logging/metrics error inside `afterExecute` | Hook code | Instrumentation error, may terminate the worker |
| Uncaught exception of worker | Thread-level error handling | May reach `UncaughtExceptionHandler` if not caught by `FutureTask` |
| Timeout on `Future.get(timeout)` | Thread calling `get` | **Not a task error by itself**; task may still be running |
| External side effect failing after task outcome | Systems outside the JVM | Requires its own confirmation/transaction protocol |

For complete error reporting, you need at minimum:

- Catch/reject metrics at **admission/submission**.
- Task outcomes via `Future`, a wrapper, or an appropriate `afterExecute`.
- An uncaught exception handler / centralized error reporting at the worker level.
- Separate cancellation and timeout metrics.
- Application-level acknowledgment for side effects/commits if required.

One unit of "completed tasks" from the pool does not automatically mean business success. `ThreadPoolExecutor.getCompletedTaskCount()` reflects tasks completed at the executor level, even when task logic was recorded as failed by `FutureTask`.

## 17. ThreadFactory and UncaughtExceptionHandler

A `ThreadFactory` can create workers with consistent names and handlers:

```java
ThreadFactory factory = runnable -> {
    Thread worker = new Thread(runnable, "business-worker");
    worker.setUncaughtExceptionHandler((thread, error) -> {
        reportUncaught(thread.getName(), error);
    });
    return worker;
};
```

This is a code snippet inside a method that requires importing `java.util.concurrent.ThreadFactory` and defining `reportUncaught`. The reporting function must not throw exceptions or block indefinitely.

**Keep the distinction clear:**

- Unchecked errors escaping `Runnable.run()` when using `execute` can reach the thread's uncaught handler.
- Errors from `Callable.call()` caught by `FutureTask` when using `submit` **do not escape `worker.run()`**, so the uncaught handler usually **does not receive those errors**.
- `afterExecute` lets you monitor tasks at the pool-worker level, but it must inspect the `Future` as shown earlier.
- A worker that dies from an unchecked exception may be replaced by the pool with another worker to keep processing tasks; replacement does not roll back side effects that happened before the error.

In the main demo, the empty handler only serves to produce **verified stdout output**, not as an operational recommendation. In production, use proper logging, alerts, and metrics for uncaught exceptions.

## 18. Liveness and Avoiding Deadlock When Collecting Errors

Inside `afterExecute`, avoid operations such as:

```java
// Illustrates risk: hook runs on a worker of the same pool.
Future<?> next = pool.submit(() -> sendReport());
next.get(); // May wait for a task that needs the very worker currently occupied by the hook.
```

This is a **dangerous illustrative snippet**; `pool`, `sendReport()`, and checked exceptions require external context. With a single-thread pool, the hook holds the only worker and waits for a newly queued task; that new task cannot start, creating a **thread starvation deadlock**.

Similarly, calling `BlockingQueue.put` inside `afterExecute` onto a full queue whose consumer must run on this same pool can hang. Use an independent, non-blocking telemetry channel or one with a deadline/failure policy, without creating circular dependencies.

If the hook calls `Future.get()` on **the exact task that just ran and whose `FutureTask` is already done**, that operation does not wait for another task, so it does not cause this kind of deadlock. That is the difference between "reading the outcome of an already-completed `Future`" and "submitting a new task and waiting for it."

## 19. Java Memory Model and Completion Relationships

The Executor Framework provides memory consistency guarantees per the `java.util.concurrent` documentation:

- Actions in a thread prior to submitting a `Runnable` to `Executor.execute` *happen-before* the actions of that task.
- With `ExecutorService`, actions prior to submitting a task *happen-before* actions in the task; actions in the task *happen-before* actions in the caller **after retrieving the result via `Future.get()`** per contract.
- The demo's `CountDownLatch` establishes a happens-before (HB) boundary for `main` to observe hook state before printing.
- Atomic variables used to store counters/outcomes have their own memory semantics per the API.

However, distinguish the following:

1. `Future.get()` makes the completed task result visible to the caller, **not necessarily waiting for all hook instrumentation to finish**.
2. Receiving `Throwable` in `afterExecute` does not mean it is safe to read the caller's mutable objects without a proper ownership or synchronization protocol.
3. If multiple tasks concurrently modify a `HashMap` or a plain `int` field without synchronization, having `main` wait on the `Future`s **does not fix data races or lost updates between tasks**.
4. A task result properly published inside the JVM does not mean a database transaction committed or an email was sent exactly once.

Safe design still requires state confinement, immutable objects, `synchronized`/`Lock`, or concurrent collections/atomic operations matching your invariants.

## 20. Testing Hooks, Submit Failures, and Cancellation

A thorough testing strategy:

1. **Success test:** Task runs normally, `beforeExecute`/`afterExecute` are called, `Future.get()` returns the result, and no failure is recorded.
2. **Direct execute failure:** `Runnable` throws `IllegalStateException`, hook sees `t`, and the uncaught handler can receive the throwable.
3. **Submit Callable failure:** `Callable` throws `IllegalArgumentException`, hook sees `t == null`, but `Future.get()` throws `ExecutionException` with the expected cause.
4. **Submit Runnable failure:** `Runnable` wrapped by `submit` in a `FutureTask`; outcome must be analyzed like a `Callable` failure.
5. **Cancellation:** Cancel a `Future` before/during execution, distinguish cancellation from task failure; do not assume hooks are always called if the task is removed before execution.
6. **Rejection:** Configure a pool with a bounded queue, keep the worker busy with a latch, and submit beyond capacity; verify the rejection handler/metric.
7. **Hook itself fails:** In a dedicated test, verify that a before-hook exception can skip the after-hook, then make instrumentation exception-safe. Do not put intentionally throwing hooks into production workloads.
8. **Pool shutdown:** Submit a task after the pool is shut down; rejection is handled at the caller, not via the after-hook.
9. **ThreadLocal cleanup:** Run two tasks sequentially on the same worker and verify that context from the first task does not leak into the second.
10. **Instrumented latency:** Load-test queue depth, task duration, admission latency, and logging overhead; ensure hooks do not push throughput/latency past SLAs.

### Testing Races Deterministically

Use `CountDownLatch` or `CyclicBarrier` to create checkpoints, rather than `Thread.sleep()` and hoping the scheduler runs in the desired order. In the demo, `Future.get()` confirms task logic, while `completedHooks.await(...)` confirms instrumentation processed both tasks. Keeping those two milestones distinct prevents flaky tests.

### Inspecting Errors at the Right Layer

For `ExecutionException`:

```java
try {
    future.get();
} catch (ExecutionException e) {
    Throwable root = e.getCause();
    // report(root), return the error, or decide on retry per contract
}
```

This is an illustrative snippet inside a method with a `Future` named `future`; `InterruptedException` must also be handled or declared. Do not catch `ExecutionException` and only log "future failed" while discarding the root cause. Also do not retry automatically when the task has non-idempotent side effects.

## 21. Common Misconceptions

1. **"`afterExecute` always receives a `Throwable` if a submitted task throws an exception."** False; `FutureTask` usually stores the error and leaves `t == null`.
2. **"`t == null` means the business task definitely succeeded."** False; the `Future` may have completed exceptionally or been cancelled.
3. **"`beforeExecute` and `afterExecute` run for every submitted task."** False; rejection, discarding, unstarted tasks, caller-runs, and hook failures can bypass the worker path.
4. **"`Future.isDone()` means success."** False; `isDone` includes failure and cancellation.
5. **"`Future.get()` throws the task's exact exception directly."** Usually it throws `ExecutionException` wrapping the cause; cancellation uses `CancellationException`.
6. **"An `UncaughtExceptionHandler` alone catches all `submit` errors."** False; `FutureTask` usually catches the exception before it can exit the thread.
7. **"`execute` always delivers errors to `afterExecute.t`."** Not necessarily; a `Runnable` that catches its own exceptions, a `FutureTask` passed to `execute`, or another wrapper can return normally.
8. **"Calling `Future.get()` inside `afterExecute` is always safe."** You must check the type and completed state; never call `get()` on another unfinished task inside a worker hook.
9. **"Putting network logging in `afterExecute` has no performance impact."** False; the hook runs on the worker and can block throughput.
10. **"With hooks in place, the caller can skip `Future.get()`."** Not if the caller needs the result, completion, or cancellation per the business contract.
11. **"`Future.get()` waits for `afterExecute` too."** Do not assume that; `FutureTask` can be done before the hook finishes.
12. **"`Throwable` in `afterExecute` represents every executor error."** False; rejection, before-hook failures, and external side effects follow different paths.
13. **"Cancelling a `Future` stops the task immediately."** No; cancellation/interruption must be supported by the task.
14. **"`ThreadPoolExecutor.getCompletedTaskCount` is a success count."** False; tasks that completed exceptionally can still be counted as completed at the pool level.
15. **"Hooks are called on the submitting thread."** Hooks usually run on the worker; `CallerRunsPolicy` can run the task on the caller thread, but not through the pool hooks.
16. **"Overridden hooks can freely throw to signal errors."** False; exceptions from hooks disrupt the worker lifecycle.
17. **"Logging every exception message is safe."** No; you must avoid leaking secrets/PII and bound payload sizes.
18. **"With the same `ThreadLocal` key, each task gets its own isolated context."** False; pooled workers are reused, so you must clean up and propagate context deliberately.
19. **"Once the hook records an error, side effects are rolled back."** No; task failure and external transactions are independent contracts.
20. **"Seeing no logs means there were no errors."** No; check `Future`s, rejections, task wrappers, and error channels.

## 22. When Should You Subclass ThreadPoolExecutor?

**Appropriate when:**

- You own the `ThreadPoolExecutor` class and want uniform instrumentation for **every task run by that pool's workers**.
- You want to measure worker execution time, queue/active metrics, tagging, or clean up `ThreadLocal`s created by the pool.
- You can guarantee the hooks are fast, exception-safe, non-blocking, and do not alter business semantics.
- You have a clear outcome policy for `Future`s, cancellations, and direct throwables.

**Do not treat hooks as the sole observation point when:**

- Tasks can run across different `Executor` types.
- Rejections, caller-runs, directly run tasks, or delayed tasks must be tracked uniformly.
- You need end-to-end lifecycle coverage from submission to outcome, not just "task passed through a worker."
- Tasks have external side effects requiring transactions, retries, idempotency, or durable auditing.
- Correlation context must propagate across asynchronous boundaries; a per-task wrapper may be clearer.

A complete observability solution typically combines a **submission wrapper**, a **rejection handler**, **`Future`/callback handling**, pool-level metrics, an error handler, and domain-specific result tracking. Hooks are a useful extension point, not the entire error-management architecture.

## 23. Self-Check Questions and Answers

**Q1.** `afterExecute(r, t)` receives `t == null` after a `submit` task throws `IllegalArgumentException`. Is anything unusual?  
**A:** No. `submit` typically wraps the task in a `FutureTask`, storing the `Throwable` inside the `Future`; the wrapper's `run()` returns normally, so `t` is `null`.

**Q2.** To find the original exception of a failed `Future`, what do you do?  
**A:** `future.get()` throws `ExecutionException`; call `e.getCause()` to retrieve the original throwable.

**Q3.** In `afterExecute`, when can you consider calling `Future.get()`?  
**A:** When `r instanceof Future<?>` and the `Future` is already done, so you do not block the worker indefinitely; catch `ExecutionException`, `CancellationException`, and `InterruptedException` properly.

**Q4.** Does `afterExecute` always run if `beforeExecute` itself throws a `RuntimeException`?  
**A:** No; in `ThreadPoolExecutor`'s worker loop, a before-hook throwing before `task.run()` prevents `afterExecute` from being called for that task.

**Q5.** Does a task rejected by `AbortPolicy` go through `beforeExecute`?  
**A:** No. It is not executed by a worker; the caller typically receives `RejectedExecutionException` at `submit`/`execute`.

**Q6.** A task submitted via `execute(new FutureTask<>(...))` throws an exception inside. Is `afterExecute.t` guaranteed to be non-null?  
**A:** No. `FutureTask.run` catches and stores the error even when submitted via `execute`. What matters is whether the `Runnable` wrapper lets the error escape `run()`.

**Q7.** Why must a test wait on a separate hook latch even after `future.get()`?  
**A:** `FutureTask` can become done before the after-hook finishes; the latch establishes a boundary confirming instrumentation has completed.

**Q8.** When a pool is saturated and not shut down, does `CallerRunsPolicy` run `ThreadPoolExecutor`'s `beforeExecute`?  
**A:** Do not expect it to. The task runs in the caller thread via the handler, not in the pool's worker loop.

**Q9.** `shutdownNow` returns unexecuted tasks; is `afterExecute` called for those tasks?  
**A:** No, because a worker never called `task.run()`. Completion/audit tracking must handle these tasks separately.

**Q10.** Why can calling `pool.submit(...).get()` inside the after-hook of **the same single-thread pool** deadlock?  
**A:** The hook holds the only worker and waits for a newly queued task that has no worker available to run it.

**Q11.** Is `Future.isDone() == true` enough to increment a success counter?  
**A:** No. The `Future` could be a failure or cancellation. You must inspect the actual outcome or follow the result contract.

**Q12.** Once an exception is logged in the after-hook, does that mean the task is definitely safe to retry?  
**A:** No. Logging only observes the error; retrying can duplicate side effects without idempotency or transactions.

**Q13.** Why should hooks avoid network I/O?  
**A:** They run on workers; long blocking prevents the worker from picking up the next task, reducing throughput and increasing queue pressure.

**Q14.** Is a `ThreadLocal` context set in `beforeExecute` guaranteed to be removed by `afterExecute` in all situations?  
**A:** No; if the before-hook throws or the task runs outside the worker loop, the after-hook will not perform cleanup. A separate `try/finally` wrapper may be needed.

**Q15.** If you only have the `ExecutorService` interface and do not control the implementation, can you override `afterExecute` directly?  
**A:** No. That is a hook on `ThreadPoolExecutor`, not a method on the `ExecutorService` interface. Use a wrapper/decorator or control a custom pool.

## 24. Official References

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): **Hook methods** section, `beforeExecute`, `afterExecute`, `terminated`; the JavaDoc specifically notes `submit` and `FutureTask`.
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): `run()`, storing results/exceptions, `done()`, cancellation, and states.
- [Java SE 17 — AbstractExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html): `submit` and `newTaskFor`.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, lifecycle, completion, and memory consistency.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `cancel`, `ExecutionException`, `CancellationException`.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` and memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phase synchronization and memory consistency.
- [Java SE 17 — Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): thread uncaught errors.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, thread lifecycle, and memory model.

**Key takeaways to remember:** `beforeExecute` and `afterExecute` are hooks **of the `ThreadPoolExecutor` worker loop**. `afterExecute` sees throwables **escaping `Runnable.run()`**, rather than automatically unwrapping every error stored by `FutureTask`. When using `submit()`, check `Future<?>` when done and read the outcome via `get()`, classifying success, failure, and cancellation; at the same time, handle rejection, lifecycle, and uncaught exceptions, and ensure instrumentation does not stall workers.
