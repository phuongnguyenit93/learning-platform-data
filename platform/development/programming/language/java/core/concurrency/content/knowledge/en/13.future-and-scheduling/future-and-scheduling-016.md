# ExecutorService.close() and try-with-resources from Java 21: Termination Waiting Conditions

## 1. The problem: after creating an executor, when do tasks actually finish?

An `ExecutorService` can accept many tasks (`Runnable`, `Callable`) and dispatch them to worker threads or another execution mechanism. When a method no longer needs to submit new work, we must decide **when to stop accepting work**, **whether to wait for submitted tasks to finish**, **whether to cancel them if waiting takes too long**, and **when the pool can be considered truly terminated**.

In Java 21, `ExecutorService` is already an `AutoCloseable` and has a `close()` method. Therefore, you can use:

```java
try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    executor.execute(() -> doWork());
} // close() is called automatically when exiting try.
```

This is a **snippet**; you need to import `ExecutorService`, `Executors`, and define `doWork()`. The complete programs in later sections can be compiled and run with JDK 21.

**Key point:** by default, `close()` initiates an **orderly shutdown** and **waits until previously submitted tasks have completed execution and the executor has terminated**. It does **not** merely set a "closed" flag, nor is it the same as calling `shutdownNow()` right away.

**Exact version milestone:** the `ExecutorService.close()` API and `ExecutorService` extending `AutoCloseable` were added in **Java 19**. Java 21 is an LTS release commonly used to officially adopt this pattern alongside new features such as virtual threads. Therefore, these exercises use **JDK 21+**; the snippet `try (ExecutorService executor = ...)` **does not compile on JDK 17** if the static type of the resource is `ExecutorService`.

This lesson covers **general Java concurrency** only, without tying into Spring or other frameworks.

## 2. States to distinguish in the ExecutorService lifecycle

| Concept/API | Meaning |
| --- | --- |
| `execute()` / `submit()` | Submits a task to the executor |
| `shutdown()` | Requests to stop accepting new tasks while allowing already submitted tasks to continue running |
| `shutdownNow()` | Attempts to stop actively executing tasks (typically via interrupt) and does not start waiting tasks; a **best effort** attempt |
| `isShutdown()` | The executor has initiated shutdown; it does **not** mean it has terminated |
| `isTerminated()` | The executor has actually terminated after shutdown |
| `awaitTermination(timeout, unit)` | The calling thread **waits with a timeout** until the executor is terminated; returns a boolean or throws `InterruptedException` |
| `close()` | Initiates an orderly shutdown and **waits for termination**; handles interrupts according to its own rules, **with no timeout parameter** |

Relationship:

```text
        accepting tasks
               |
      shutdown() / close()
               |
               v
     shut down, draining
      |                    |
      | tasks complete     | if close() is interrupted while waiting:
      |                    | switches to best-effort shutdownNow()
      v                    v
      executor terminated (no running/waiting tasks remain)
               |
        close() returns normally
```

A call to `shutdown()` **returns immediately** after issuing the request; tasks may still be running. A normal call to `close()` **does not return** until the executor has terminated. `awaitTermination()` allows **bounded waiting**, but the caller must decide what to do if the timeout expires.

### "Task has completed" does not necessarily mean "business success"

A `Callable` that finishes with an exception is still a task that has completed execution, which may cause `Future.get()` to throw `ExecutionException`. `close()` does not collect those exceptions and rethrow them to the caller; it waits for the **execution lifecycle** to end, without evaluating business success. When you need results or errors, manage `Future` or another outcome-reporting mechanism.

## 3. What exactly does ExecutorService.close() do?

According to the **JDK 21** contract:

1. **Orderly shutdown:** tasks submitted before shutdown continue to be processed according to the executor's policy; new submissions are rejected.
2. **Wait for termination:** the thread calling `close()` waits until the executor has actually terminated. This is what makes `close()` potentially **blocking**.
3. **If the waiting thread is interrupted:** `close()` switches to attempting to stop executing tasks **as if calling `shutdownNow()`**, and tasks still waiting in the queue **are not executed** per the contract.
4. **Continue waiting for executing tasks to stop:** after requesting the stop, `close()` still waits for active tasks to finish. An interrupt does not make the method abandon waiting immediately.
5. **Restore interrupt status:** before returning, the calling thread's interrupt flag is restored.
6. **If the executor is already terminated:** calling `close()` has no effect.

**Important consequence:** `close()` does not declare `throws InterruptedException`. Callers **cannot** write `catch (InterruptedException)` just to catch from `close()` if no other API in that block throws that checked exception. When interrupted during the waiting phase, `close()` handles it according to the rules above and restores the flag before returning.

**Do not think of "shutdownNow" as a hard kill:** stopping running tasks is usually requested via `Thread.interrupt()`. If a task is in uninterruptible I/O or intentionally ignores interrupts, the executor may **terminate slowly or never terminate**; `close()` can therefore also wait for a very long time. The API does not provide an automatic hard timeout.

### No promise that "closing the resource stops everything immediately"

Try-with-resources guarantees that `close()` is called when leaving the scope, **not** that closing finishes in a few milliseconds. If a task waits for an event that only code **after the try block** can signal, the calling thread can deadlock itself at `close()`. Dependencies must be designed so that tasks can complete **before control needs to pass the code after try**.

## 4. Java 21+: first program with try-with-resources

Create `CloseWaitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CloseWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch mayFinish = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            executor.execute(() -> {
                started.countDown();
                try {
                    mayFinish.await();
                    completed.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("Inside try, completed: " + completed.get());
            mayFinish.countDown();
        }

        System.out.println("After close, completed: " + completed.get());
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac CloseWaitDemo.java
java CloseWaitDemo
```

Output when there is no external interrupt:

```text
Inside try, completed: 0
After close, completed: 1
```

**Why is the output deterministic?**

- The worker signals that it has started via `started.countDown()` but cannot pass `mayFinish.await()` yet.
- Main waits on `started.await()` and prints the completed task count. The gate is still closed, so the counter is guaranteed to be 0.
- Main opens the gate and exits `try`; `close()` is called automatically. If the worker has not incremented the counter yet, `close()` must also wait for the worker to finish.
- The `After close` line executes **after `close()` returns**, so when the task completes normally, the result is 1.

This example uses a single-worker executor to clearly distinguish **scope exit** and **termination**. In an application with many tasks, `close()` waits for all accepted tasks under the orderly shutdown mechanism, not just the last submitted task.

### Is Future.get() needed before leaving try?

**Not required if you only need to wait for tasks to finish** under the `close()` model. However, if you need the **return value** or **failure cause**, you still need `Future.get()` or a result-reporting mechanism. `close()` only waits for the lifecycle; it does not return a list of results like `invokeAll()`.

## 5. Distinguishing close() from shutdown(), awaitTermination(), and shutdownNow()

| Approach | Stops accepting new tasks? | Waits for termination itself? | Has wait deadline? |
| --- | --- | --- | --- |
| `shutdown()` | Yes | No | No |
| `shutdownNow()` | Yes, and attempts to stop running tasks | No | No |
| `shutdown(); awaitTermination(timeout, unit)` | Yes | Yes, **up to timeout** per await call | Yes |
| `close()` | Yes | Yes, until executor is terminated | **No** |
| `try (ExecutorService e = ...)` | Yes, on scope exit | Yes, via `close()` | **No** |

**Do not call `awaitTermination()` before `shutdown()` expecting the executor to stop on its own:** `awaitTermination` only waits for termination; it does not request shutdown. If the executor is still accepting work and nobody has called shutdown, the call can time out without changing the pool's state.

**Do not assume `shutdownNow()` has already stopped everything:** this method returns the list of **waiting tasks that have not started** per the contract and attempts to interrupt running tasks. It does not wait for threads to actually terminate. To check for termination, use `awaitTermination()` or `isTerminated()`.

### When should you choose close()?

Suitable when a scope owns its own executor, the number of tasks is finite, tasks can finish, and you want to be sure that **no executor tasks are still running when exiting the scope**.

For example, an on-demand fan-out: create an executor, submit three independent Callables, collect the results, and finish the method. Try-with-resources prevents forgetting shutdown even if the execution path throws an exception.

### When should you not use close() directly?

- You need a **bounded termination deadline** (SLA, 5-second graceful shutdown, then fall back to `shutdownNow`).
- The executor is a **shared resource**, owned by another component and used by other requests; a small scope must not close it.
- Tasks may **run periodically indefinitely**, wait for an event that cannot be emitted before leaving the scope, or perform I/O with no cancellation point.
- Code is holding a lock that a task needs in order to finish; calling `close()` while holding the lock can cause a deadlock.
- You need fine-grained control over stop timing/strategy and visibility into unexecuted tasks.

In those situations, designing an explicit lifecycle with `shutdown`, `awaitTermination`, and `shutdownNow` is more appropriate; or ensure tasks finish before the scope closes.

## 6. Java 21+: values and errors must be retrieved via Future

Even after all tasks have stopped, `close()` has no concept of a task's business "success". For example, if a task fails, try-with-resources still closes the pool, and the caller must inspect the `Future` to report the error.

Create `CloseWithFutureDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CloseWithFutureDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<Integer> ok = executor.submit(() -> 6 * 7);

            Callable<String> failing = () -> {
                throw new IllegalArgumentException("invalid");
            };
            Future<String> bad = executor.submit(failing);

            System.out.println("Value: " + ok.get());

            try {
                System.out.println("Other: " + bad.get());
            } catch (ExecutionException e) {
                System.out.println("Task error: "
                        + e.getCause().getClass().getSimpleName());
            }
        }

        System.out.println("Executor scope ended");
    }
}
```

Compile and run:

```bash
javac CloseWithFutureDemo.java
java CloseWithFutureDemo
```

Output:

```text
Value: 42
Task error: IllegalArgumentException
Executor scope ended
```

- The first task returns 42.
- The second task throws `IllegalArgumentException`; its `Future.get()` throws `ExecutionException` wrapping the cause.
- `close()` is called even if an exception occurs inside the scope. Here the exception from `bad.get()` is handled; if uncaught, try-with-resources still calls `close()` before propagating the exception outward.
- Do not treat reaching the end of `close()` as proof that all tasks returned successful results.

**Notably:** when an exception exits the `try` block, auto-close runs **before** the exception is handled by an outer layer. If tasks are still running for a long time or stuck, propagating the error outward can be delayed while waiting for `close()`.

## 7. Java 21+: close() when the caller has been interrupted

When the thread calling `close()` is waiting and receives an interrupt, the default implementation switches to attempting to stop tasks in the manner of `shutdownNow()`, continues waiting for running tasks to finish, and then restores the interrupt status.

You can verify this with a task waiting on a latch. Create `InterruptedCloseDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedCloseDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverOpens = new CountDownLatch(1);
        AtomicBoolean workerSawInterrupt = new AtomicBoolean();

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            executor.execute(() -> {
                started.countDown();
                try {
                    neverOpens.await();
                } catch (InterruptedException e) {
                    workerSawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            // Interrupt the caller itself right before auto-close.
            Thread.currentThread().interrupt();
        }

        System.out.println("Worker interrupted: "
                + workerSawInterrupt.get());
        System.out.println("Caller flag restored: "
                + Thread.currentThread().isInterrupted());

        // Clear the flag so the demo exits cleanly.
        Thread.interrupted();
    }
}
```

Run with JDK 21+:

```bash
javac InterruptedCloseDemo.java
java InterruptedCloseDemo
```

Output when there is no other interference with the threads:

```text
Worker interrupted: true
Caller flag restored: true
```

Explanation:

1. The worker has started and signaled `started`, and is waiting (or about to wait) on `neverOpens.await()`.
2. The caller sets its own interrupt status before leaving the scope. When `close()` waits for termination, the wait observes the interrupt and switches to a `shutdownNow()`-style stop attempt.
3. The worker receives the interrupt. Even if the interrupt arrives before `await()` actually begins, the next `await()` detects the flag and throws `InterruptedException`.
4. The worker catches the exception and finishes. `close()` **still waits** for the worker to finish executing, then returns with the caller's flag restored.
5. The caller's flag remains `true` after `close()`, not because `close()` threw `InterruptedException`.

**Do not copy the pattern of intentionally interrupting the caller into normal logic:** this example only clarifies the `close()` contract. In real applications, interrupts usually come from cancellation/shutdown requests issued by another component. If a task does not respond to interrupts, `close()` may still wait forever, so `close()` cannot be used as a timeout mechanism.

## 8. Tasks that do not cooperate with interrupts can prevent close() from finishing

A task may:

- Loop in CPU computation **without checking `isInterrupted()`**.
- Block at an uninterruptible point, such as waiting for a `synchronized` monitor held by another thread.
- Encounter I/O with interrupt semantics where the underlying system does not support fast cancellation.
- Wait on a latch/condition whose completion signal is only sent **after `close()` returns**.
- Call `Future.get()` on another task in the same small pool, causing thread starvation deadlock.

In these scenarios, `close()` provides no timeout escape hatch. The caller receiving an interrupt only triggers a `shutdownNow()` request; it **does not guarantee that all task code will be forced to stop**.

### Self-deadlock pattern to avoid

```java
// DANGEROUS snippet, not a standalone program.
CountDownLatch mayFinish = new CountDownLatch(1);

try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
    executor.execute(() -> {
        try {
            mayFinish.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    });
}

// This line is unreachable if close() keeps waiting for the worker:
mayFinish.countDown();
```

Without an interrupt or another signal source, the task waits on the latch; `close()` waits on the task; the code that opens the latch is **after `close()`**. That is a wait cycle that can hang the program indefinitely.

**Fix:** move `mayFinish.countDown()` before exiting the scope, or design the producer/timer/cancellation so it does not depend on the thread blocked in `close()`.

### Holding a lock while closing the executor

If the caller holds `synchronized(lock)` and exits try-with-resources inside that block, while a worker needs the **same lock** to finish, the caller waits for `close()` and the worker waits for the lock. Even though every API is individually "thread-safe," the combination still deadlocks. Before closing an executor, avoid holding locks or resources that tasks need to complete.

## 9. Java 17: equivalent lifecycle management in intent

In Java 17, `ExecutorService` does **not** extend `AutoCloseable` and does not have `close()`. The traditional shutdown pattern must be written explicitly.

Create `LegacyShutdownDemo.java`, runnable on Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LegacyShutdownDemo {
    private static void stopWithinBudget(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                    System.err.println("Pool has not terminated");
                }
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = pool.submit(() -> 40 + 2);
            System.out.println("Answer: " + answer.get());
        } finally {
            stopWithinBudget(pool);
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac LegacyShutdownDemo.java
java LegacyShutdownDemo
```

Output when the task completes normally:

```text
Answer: 42
```

Comparison with `close()`:

- `stopWithinBudget` gives the pool **2 seconds for orderly shutdown**, then calls `shutdownNow()` and waits another **2 seconds**. After that, it can **return even if the pool has not terminated** (logging a warning).
- `close()` by default waits for the executor to terminate **with no timeout**, even after switching to `shutdownNow()` due to an interrupt.
- In the Java 17 example, handling `InterruptedException` on the caller thread initiates `shutdownNow()` and **restores the flag**, without continuing to wait indefinitely.
- These are **two different contracts**. Using try-with-resources for brevity is **not equivalent** to a shutdown with a business deadline.

**A separate note on processes:** worker threads of regular executors can keep the JVM alive even after the caller stops waiting; calling `shutdownNow()` also does not guarantee workers have stopped. Shutdown design should monitor and handle tasks that ignore cancellation.

## 10. Virtual threads from Java 21 and try-with-resources

Java 21 made virtual threads an official feature; `Executors.newVirtualThreadPerTaskExecutor()` creates an executor that uses **one virtual thread per task**. This executor is also an `ExecutorService`, so it benefits from `close()` and try-with-resources.

Create `VirtualThreadScopeDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadScopeDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> first = executor.submit(() -> 10);
            Future<Integer> second = executor.submit(() -> 20);

            System.out.println("Total: " + (first.get() + second.get()));
        }

        System.out.println("All scoped tasks ended");
    }
}
```

Run with JDK 21+:

```bash
javac VirtualThreadScopeDemo.java
java VirtualThreadScopeDemo
```

Output:

```text
Total: 30
All scoped tasks ended
```

Key points:

- The executor creates a virtual thread per task; this does not mean the two tasks **run concurrently on CPU at the exact same instant** or must finish in submission order.
- `Future.get()` retrieves task results, while `close()` ensures the executor scope has terminated before the last line runs.
- Virtual threads help scale many blocking-task workloads in many scenarios, but they **do not automatically fix** data races, deadlocks, transactions, or tasks that ignore cancellation.
- Do not create a virtual thread executor at every small layer without understanding ownership and closing time; a scope should only close executors **that the scope itself owns**.

### Why is close() of a virtual-thread-per-task executor worth noting?

Consider fan-out: inside a method, you submit N independent calls, wait for results, and then close the scope. If one task is still running or hung, `close()` can keep the method from returning, even though virtual threads are lighter than platform threads. That is both a benefit (not leaking/forgetting tasks) and a risk (indefinite waiting) if deadlines and cancellation are not designed.

## 11. The case of ScheduledExecutorService and periodic tasks

`ScheduledExecutorService` is also a subtype of `ExecutorService`, but scheduled tasks raise an additional question: **which tasks are allowed to continue after shutdown?**

With `ScheduledThreadPoolExecutor`, policies such as `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)` and `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)` affect periodic/delayed tasks upon shutdown. Default values are defined by the JDK, but when configuration changes, `close()` may have to wait for tasks still permitted to run under those policies.

**Do not assume** that exiting a try-with-resources block around a scheduler will always complete instantaneously. If a delayed task has a long delay remaining or the policy keeps periodic tasks after shutdown, the program may wait a long time or fail to terminate when `close()` is called.

When building a long-lived scheduler, manage its lifecycle at the owner, cancel related `ScheduledFuture` instances at the right time, and define a clear shutdown deadline. Do not close a shared scheduler just because one method finished registering a task.

## 12. Exceptions in try-with-resources and closing order

Try-with-resources automatically calls `close()` when leaving the block **whether exiting normally, via `return`, or via an exception**. Java closes multiple resources in **reverse order of declaration**.

Structural example:

```java
// Snippet: openResource() returns another AutoCloseable.
try (AutoCloseable resource = openResource();
     ExecutorService executor = Executors.newFixedThreadPool(2)) {
    // Submit tasks that work with resource.
}
// executor.close() runs first, then resource.close().
```

This is a **snippet**, because `openResource()` is not defined. Declaring the executor **after** `resource` in this case ensures it is **closed before** `resource`, preventing still-running tasks from accessing a resource that has already been closed.

**If you reverse the resource order**, `resource` may be closed before the executor finishes its tasks, causing errors from using a closed resource. Thus scope structure is not just syntactic sugar—**closing order determines correctness** when tasks depend on files, streams, connections, or other resources.

An exception thrown by code inside `try` may only propagate outward after all resources have finished closing; exceptions thrown during closing follow Java's suppressed exceptions rules. `ExecutorService.close()` does not throw `InterruptedException`, but it can encounter runtime exceptions such as permission or deployment-context issues. When managing multiple resources, you must understand both error paths and how each component closes.

### Using a pre-created resource variable

Since Java 9, try-with-resources can use a **final or effectively final** resource variable created beforehand:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
try (executor) {
    executor.execute(() -> System.out.println("work"));
}
```

This is a snippet inside an appropriate method/class and works on **JDK 21+** because `ExecutorService` is `AutoCloseable` there. If the resource is not owned by the current method (a shared pool), **do not** close it with try-with-resources merely because the syntax allows it.

## 13. Termination waiting conditions and memory visibility

`close()` waits for the executor lifecycle to end, but if you need to use a task's result under the program contract, **`Future.get()` is the explicit result-publication channel**. The `ExecutorService` contract specifies important memory-consistency relationships:

- Actions in a thread prior to submitting a task **happen-before** the corresponding actions inside the task.
- Actions in a task **happen-before** actions subsequent to retrieving the result via `Future.get()`.

When tasks update shared mutable state, you cannot assume that "using ExecutorService and calling close()" makes all updates **atomic** or automatically protects invariants while tasks are running. Two tasks both doing `counter++` on a plain field can still lose updates.

**Proper design:** use `Future` for values/exceptions; use `AtomicInteger`, `synchronized`, `Lock`, or immutable snapshots when tasks share state; use `close`/`awaitTermination` to manage **lifecycle**. These are three related responsibilities, not interchangeable substitutes.

### isShutdown vs. isTerminated

- After `shutdown()`, `isShutdown() == true`, but `isTerminated()` may still be `false`.
- After `close()` **returns normally** with the default implementation and the executor has actually terminated, `isTerminated() == true`.
- Do not busy-spin in a `while (!executor.isTerminated())` loop to wait for the pool to finish; use `awaitTermination(...)` or `close()` according to the appropriate contract.

## 14. Common misconceptions

1. **"`close()` was added to ExecutorService in Java 21."** More accurately: it was added **in Java 19**; it is commonly taught/used in JDK 21+ projects.
2. **"JDK 17 also compiles `try (ExecutorService e = ...)`."** False: `ExecutorService` in JDK 17 is not `AutoCloseable`.
3. **"`close()` only calls `shutdown()` and returns immediately."** False: it waits for the executor to terminate.
4. **"`shutdown()` already waits for all tasks to finish."** False: it only requests an orderly shutdown.
5. **"`shutdownNow()` is guaranteed to kill every task."** False: it is best-effort only; tasks that ignore interrupts may keep running.
6. **"`close()` has a default timeout."** False: there is no fixed wait deadline in the API.
7. **"When the caller is interrupted, `close()` immediately throws `InterruptedException`."** False: `close()` attempts a `shutdownNow()`-style stop, continues waiting, and restores the interrupt flag before returning.
8. **"`close()` confirms all tasks succeeded."** False: you need `Future.get()` to know the outcome.
9. **"Exiting the scope means side effects in tasks are rolled back on error."** False: an executor is not a transaction manager.
10. **"A shared pool can be closed anywhere it is called."** False: there must be a clear lifecycle owner.
11. **"Virtual threads make it impossible for `close()` to hang."** False: a virtual thread can wait indefinitely if there is no progress condition.
12. **"As long as a task only needs a signal on the line after `try`, `close()` will let that line run."** False: `close()` waits for the task; this can create a wait cycle.
13. **"A scheduled executor will always close immediately at the end of the `try` block."** False: delay/periodic policies can cause significant waiting.
14. **"One completed `Future` means all tasks in the executor have stopped."** False: a `Future` only represents its corresponding task, whereas `close()`/`awaitTermination()` apply to the executor.
15. **"`close()` is a replacement for designing SLA-based graceful shutdown."** False: you may need `shutdown()` and timed `awaitTermination()` with a fallback.

## 15. Checklist for applying ExecutorService.close and try-with-resources

1. **Which JDK version are you running?** To use `try (ExecutorService...)`, you need `ExecutorService` to implement `AutoCloseable`; in practice, use JDK 21+ as covered in this lesson.
2. **Who owns the executor?** Only the owning scope may close it; shared pools need an owner with a longer lifecycle.
3. **Are tasks finite and able to make progress?** Avoid tasks waiting for a signal that only occurs after `close()`.
4. **Do you need return values and exceptions?** Use `Future.get()` or a result channel; do not rely on `close()` to report task errors.
5. **Is there a bounded shutdown deadline?** If needed, use `shutdown(); awaitTermination(timeout)` and choose the next action; `close()` has no timeout.
6. **Do tasks cooperate with interrupts?** The `shutdownNow` fallback on interrupt is not a hard-kill mechanism.
7. **Are you holding resources that workers need?** Do not close an executor while holding a lock or resource that creates a wait cycle.
8. **If there are multiple `AutoCloseable`s, is the closing order right?** Resources used by workers generally need to stay open until after the executor has stopped.
9. **Are there scheduled/periodic/delayed tasks?** Check post-shutdown policies and cancel futures when needed.
10. **Is there shared mutable state?** Closing the executor does not fix data races; synchronize tasks separately.
11. **Have you tested normal, exception, and interrupt paths?** Use latches to create reproducible schedules, and check flag states and cleanup.
12. **Do you observe lifecycle in operations?** Monitor `isShutdown`, `isTerminated`, shutdown duration, stuck tasks, and thread dumps/JFR if needed.

## 16. Authoritative references

- [JDK 21: ExecutorService API and close()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JDK 21: Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JDK 21: ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

**In summary:** since Java 19, `ExecutorService` has `close()` and is `AutoCloseable`; in **Java 21+** programs, you can use `try-with-resources` to bind an executor's lifecycle to a scope. **`close()` waits for accepted tasks and the executor to terminate**, rather than simply calling `shutdown()` and returning. If the caller is interrupted while waiting, `close()` switches to a `shutdownNow()`-style stop request, **still waits for running tasks to finish**, and then restores the interrupt status. Choose `close()` when you want to wait until completion; choose `shutdown`/`awaitTermination` with a deadline when the system has time limits, and manage results/errors via `Future`.
