# Lifecycle of commonPool and Private Pools: shutdown, close, and awaitTermination

## 1. Why Does the ForkJoinPool Lifecycle Differ Between Shared and Private Pools?

`java.util.concurrent.ForkJoinPool` is an `ExecutorService` that uses work-stealing: workers process `ForkJoinTask` instances, can steal additional work from each other's queues, and support divide-and-conquer algorithms. Beyond `fork()/join()`, applications can also `execute()`, `submit()`, and `invoke()` tasks.

There are **two kinds of pools to distinguish**:

- `ForkJoinPool.commonPool()` is the **shared pool in the JVM**, which can be used by many different libraries and tasks. Calling code only *borrows* the resource; it does not own its lifecycle.
- `new ForkJoinPool(parallelism)` creates a **private pool**. The component that creates the pool is typically responsible for requesting shutdown, waiting for tasks to finish, and releasing the lifecycle at the right time.

Although both are `ForkJoinPool`, `shutdown()`, `shutdownNow()`, `awaitTermination()`, `awaitQuiescence()`, and `close()` have **very different** consequences on the two types of pools.

**Key point:** `commonPool()` is not shut down by normal shutdown calls; `close()` on Java 21 also neither waits for nor closes the common pool. For a **private pool**, `shutdown()` requests that it stop accepting new work, `awaitTermination()` waits for termination with a timeout, and `close()` on JDK 21+ can wait until the executor is actually terminated.

The basic JDK examples run on **Java 17+**; the `close()` and try-with-resources sections require **JDK 21+**. The content covers general Java concurrency and is framework-independent.

## 2. Three Concepts: shutdown, terminated, quiescent

Before choosing an API, you must know **what you are waiting for**:

| State | Description | Effect on new tasks |
| --- | --- | --- |
| Running | Pool is ready to accept and execute work | Can accept tasks |
| Shutdown requested | Requested to stop accepting new work; already-accepted tasks may still run/wait | Rejects new tasks |
| Terminated | Pool has ended its lifecycle after shutdown | Does not run new tasks |
| Quiescent | Pool is **temporarily idle**, with no tasks available for workers or currently executing according to pool criteria | Can still accept new tasks if not shut down |

**Quiescent is different from terminated.** A pool can be quiescent at 10:00 and then accept more tasks at 10:01. A private pool that has terminated cannot be restarted as the same instance. A specific `Future` completing also does not mean the entire pool has terminated.

Typical lifecycle of a **private pool**:

```text
          RUNNING
             |
         shutdown()
             |
             v
   SHUTDOWN / DRAINING
   rejects new tasks
   accepted tasks continue processing
             |
     no active workers left
             |
             v
         TERMINATED
```

`shutdownNow()` can request early cancellation of tasks on a best-effort basis. However, it does **not** by itself guarantee that every running thread stops immediately.

## 3. API Comparison Table by Pool Type

| API | Private pool | `ForkJoinPool.commonPool()` |
| --- | --- | --- |
| `shutdown()` | Initiates an orderly shutdown | **Does not change execution state** |
| `shutdownNow()` | Attempts to cancel/stop tasks, does not wait until all tasks stop | **Does not change execution state** |
| `isShutdown()` | True after a shutdown request | Does not become true merely from a shutdown attempt |
| `isTerminated()` | True once actually terminated | Does not become true from normal shutdown |
| `awaitTermination(timeout, unit)` | True if terminated, false if timeout elapsed | Has a quiescence-waiting effect but **always returns false** |
| `awaitQuiescence(timeout, unit)` | Waits or helps execute tasks until temporarily quiescent | Appropriate way to observe the common pool becoming temporarily idle |
| `close()`, JDK 21+ | Shuts down and then **waits for termination**, with no timeout | **No-op and does not wait** |
| `submit(task)` after shutdown/close | Rejected | Remains usable after no-op calls |

This table is **specific to `ForkJoinPool`** and must not be applied verbatim to every `ExecutorService` implementation. For example, `ThreadPoolExecutor.shutdownNow()` can return a list of awaiting `Runnable`s; `ForkJoinPool.shutdownNow()` is documented to **always return an empty list**.

## 4. Common Pool: Managed by the JVM, Cannot Be Closed by Application Shutdown Calls

`ForkJoinPool.commonPool()` returns the shared common pool. It typically backs Fork/Join tasks not bound to a private pool as well as many asynchronous usages from JDK libraries. Other components may be sharing it at the same time.

The Javadoc explicitly states:

- `shutdown()` on the common pool has no effect on execution state.
- `shutdownNow()` on the common pool has no effect on execution state.
- `close()` on the common pool, starting from the API supporting close, does nothing and does not wait.
- `awaitTermination(...)` on the common pool has waiting behavior related to `awaitQuiescence`, **but returns `false` in all cases**, because the common pool does not terminate via normal shutdown.

This is not an error return: **`false` from `awaitTermination(commonPool)` does not confirm that tasks are still running**, and must not be used to warn that a specific task has not finished. If you need to wait for a specific task, hold on to its `Future`.

### Java 17+ Example: Common Pool Still Accepts Tasks After Shutdown

Create the file `CommonPoolLifecycle.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CommonPoolLifecycle {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();

        Future<Integer> first = common.submit(() -> 40 + 2);
        System.out.println("First: " + first.get());

        common.shutdown();
        System.out.println("Shutdown: " + common.isShutdown());

        boolean terminated =
                common.awaitTermination(0, TimeUnit.MILLISECONDS);
        System.out.println("awaitTermination: " + terminated);

        Future<Integer> second = common.submit(() -> 7);
        System.out.println("Second: " + second.get());
    }
}
```

Run on JDK 17+ with a standard common pool configuration:

```bash
javac CommonPoolLifecycle.java
java CommonPoolLifecycle
```

Output:

```text
First: 42
Shutdown: false
awaitTermination: false
Second: 7
```

`get()` waits for each task's result. The `shutdown()` call does not shut down the common pool; `awaitTermination(0, ...)` does not report true; the subsequent `submit` call still runs. If the JVM is configured with no common pool workers capable of making progress, check the environment settings; the demo assumes a standard default configuration.

**Rule of thumb:** Do not use `commonPool` to create a "start → run a batch → close pool" boundary. The common pool does not belong exclusively to your caller.

## 5. Private Pool: shutdown() Does Not Wait Automatically

Creating a private pool:

```java
ForkJoinPool pool = new ForkJoinPool(2);
// ... submit work ...
pool.shutdown();
```

This is a snippet without a class or imports. `shutdown()` only requests that no new tasks be accepted and allows already-accepted tasks to continue running. It does **not** automatically wait until all workers finish.

States that can occur immediately after `shutdown()`:

- `isShutdown() == true`.
- `isTerminated() == false` if tasks are still running or waiting.
- A `Future.get()` can wait for that specific task's result.
- `awaitTermination(timeout, unit)` is the API for waiting on the **termination state of the pool**.

### Java 17+ Example: Observing Before and After Pool Termination

Create the file `PrivatePoolLifecycle.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PrivatePoolLifecycle {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> answer = pool.submit(() -> {
                started.countDown();
                release.await();
                return 42;
            });

            started.await();
            pool.shutdown();

            System.out.println("Shutdown: " + pool.isShutdown());
            System.out.println("Terminated before release: "
                    + pool.awaitTermination(0, TimeUnit.MILLISECONDS));

            release.countDown();
            System.out.println("Answer: " + answer.get());

            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool still running");
            }
            System.out.println("Terminated: " + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac PrivatePoolLifecycle.java
java PrivatePoolLifecycle
```

Output when the worker completes normally without being interrupted:

```text
Shutdown: true
Terminated before release: false
Answer: 42
Terminated: true
```

Explanation:

1. The worker started running and waited on `release.await()`, which `main` confirmed via `started.await()`.
2. `main` called `shutdown()`; the pool transitioned to rejecting new tasks, but the worker was still waiting, so it had not terminated yet.
3. `awaitTermination(0, MILLISECONDS)` cannot return true while the worker is still blocked at the latch.
4. `main` opens the latch, and `Future.get()` receives the value 42.
5. `awaitTermination(30, SECONDS)` waits for the pool to finish; the example deliberately throws an error if the timeout is exceeded rather than recording an inaccurate state.
6. `finally` always opens the latch so that an exception on the `main` thread does not leave the worker blocked.

**Do not treat `answer.get()` of a single task as proof that the entire pool has stopped** if other tasks exist; that is what `awaitTermination` is for. The 30-second duration in the example is a check timeout, not a hard guarantee from the scheduler or operating system.

## 6. awaitTermination(): Proper Use for a Private Pool After Requesting Shutdown

API form:

```java
boolean terminated = pool.awaitTermination(5, TimeUnit.SECONDS);
```

This snippet assumes `pool` is already declared and the enclosing method handles `InterruptedException`.

For a private pool:

- `true`: the executor terminated during the wait.
- `false`: the timeout elapsed without confirming termination.
- `InterruptedException`: the thread **calling `awaitTermination`** was interrupted; do not conflate this with a task failing.
- Calling `awaitTermination` **does not initiate shutdown**. If the pool is still running and nothing else shuts it down, it can wait until the timeout expires.
- The timeout only bounds **the caller's wait**; it does not automatically cancel running tasks.

Two-phase shutdown pattern:

```java
// Snippet: caller owns the private pool.
pool.shutdown();
try {
    if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            System.err.println("Pool still active");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**The two 2-second waits are separate budgets**; the whole process can wait nearly 4 seconds plus processing overhead. If a **single overall deadline** is required, measure elapsed time with `System.nanoTime()` and pass the remaining time to each await call.

### Differences in ForkJoinPool.shutdownNow()

`ForkJoinPool.shutdownNow()` attempts to stop actively executing tasks and cancel waiting tasks, but **always returns an empty `List`** by contract. Therefore, do not use `shutdownNow().size()` to count discarded tasks. There is no guarantee that a task blocked in non-interruptible I/O will stop immediately.

`shutdownNow()` returning also **does not mean `isTerminated()` is true**. If certainty is required, continue waiting with `awaitTermination` under a concrete deadline policy, and have a way to alert if tasks do not cooperate with cancellation.

Do not call `shutdownNow` on the **common pool** to "drain the queue"; it has no effect on the shared pool's execution state.

## 7. awaitQuiescence(): Waiting for Temporary Idleness Without Closing the Pool

`ForkJoinPool.awaitQuiescence(timeout, unit)` waits or **helps execute work** until the pool becomes temporarily quiescent, or the timeout elapses.

- `true`: confirms the quiescent state by contract at a point in time.
- `false`: quiescent condition was not reached before the wait limit.
- Does not trigger shutdown and does not substitute for the terminated state.
- When called from a `ForkJoinTask` in the same pool, behaves equivalently to `ForkJoinTask.helpQuiesce()`.
- When called from an external thread, the caller may participate in executing tasks rather than merely standing by.
- Does not declare `InterruptedException` like `awaitTermination`.

**Quiescence is only a temporary state:** the pool can accept new tasks immediately after returning true, if it has not been shut down.

### Java 17+: Quiescent Yet Still Accepting New Tasks

Create the file `QuiescenceDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;

public class QuiescenceDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);

        try {
            System.out.println("First: "
                    + pool.submit(() -> 1).get());

            boolean idle = pool.awaitQuiescence(5, TimeUnit.SECONDS);
            if (!idle) {
                throw new IllegalStateException("Pool did not become idle");
            }

            System.out.println("Quiescent: " + idle);
            System.out.println("Shutdown: " + pool.isShutdown());
            System.out.println("Second: "
                    + pool.submit(() -> 2).get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac QuiescenceDemo.java
java QuiescenceDemo
```

Output when the pool completes normally:

```text
First: 1
Quiescent: true
Shutdown: false
Second: 2
```

The pool only has two tasks submitted sequentially; after the first task finishes, `awaitQuiescence` can observe idleness. `isShutdown` remains false, so the second task is accepted.

### For commonPool: What Does awaitQuiescence Mean?

Since the common pool cannot be shut down via normal APIs, `awaitQuiescence` can be useful when you want to **wait for the entire common pool to become temporarily idle**, for example when an application wants to give asynchronous processing a chance to finish before the JVM exits.

However, the common pool is shared: other components can still submit more work, so a single quiescent observation **does not confirm that your own group of tasks produced their expected results**. To wait for a specific group of tasks accurately, keep a list of their `Future` or `ForkJoinTask` instances and wait on each one.

**Common pitfall:** `commonPool().awaitTermination(1, SECONDS)` can wait with an effect similar to `awaitQuiescence` yet **always returns false**. Do not write `if (!common.awaitTermination(...))` and conclude that tasks are definitely still running. Use the right API for the question you want to answer.

## 8. close() and try-with-resources Since JDK 19, Commonly Used with Java 21+

Starting in **Java 19**, `ExecutorService` extends `AutoCloseable` and provides `close()`. JDK 21 (LTS) clearly supports using pools in try-with-resources; JDK 17 **did not yet have** that contract for `ForkJoinPool`.

### Private Pool: close() Waits for Termination

For a **private pool**, `close()`:

1. Requests an orderly shutdown.
2. **Waits until the executor is terminated**, with no timeout parameter.
3. If the calling thread is interrupted while waiting, switches to a stop attempt like `shutdownNow()`.
4. Continues waiting for executing tasks to stop, then **restores the interrupt status** for the caller before returning.

**Do not misunderstand `close` as "call shutdown and return immediately"**. If a task waits on a resource that never becomes available or ignores interruption, `close` can wait indefinitely. Try-with-resources guarantees that `close` is called, not that closing completes within a time limit.

### Java 21+: Example of Scope-Based Private Pool Closing

Create the file `PrivateClose21.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class PrivateClose21 {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger count = new AtomicInteger();

        try (ForkJoinPool pool = new ForkJoinPool(1)) {
            pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    count.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("Inside try: " + count.get());
            release.countDown();
        }

        System.out.println("After close: " + count.get());
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac PrivateClose21.java
java PrivateClose21
```

Output:

```text
Inside try: 0
After close: 1
```

The `started` latch confirms the task has begun, while `release` is still closed so `count` is 0 when printed inside the `try` block. `main` opens the latch before leaving the scope. Upon exiting `try`, Java calls `pool.close()` and waits for the worker to finish; after `close`, the value is 1.

**Deadlock risk:** Do not place `release.countDown()` **after the `try` block** if the task is waiting on `release`. In that case `close` waits for the task, the task waits for `release`, and the signaling line never executes. Likewise, do not call `close` while holding a lock that the task needs in order to finish.

### Common Pool: close() Does Not Wait and Does Not Close

For `ForkJoinPool.commonPool()`, JDK 21 specifies that `close()` **has no effect on execution and does not wait**. Therefore:

```java
// JDK 21+ snippet, NOT a barrier waiting for the task.
try (ForkJoinPool common = ForkJoinPool.commonPool()) {
    common.execute(() -> doWork());
}
// close() here does not guarantee doWork() has finished.
```

`doWork()` is undeclared, so this is only a snippet. Do not use try-with-resources with the common pool in a way that implies you own its lifecycle.

### Java 21+: Common Pool Remains Usable After close()

Create the file `CommonClose21.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class CommonClose21 {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();
        common.close();

        System.out.println("Shutdown: " + common.isShutdown());
        Future<String> result = common.submit(() -> "still available");
        System.out.println("Result: " + result.get());
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac CommonClose21.java
java CommonClose21
```

Output in a standard common pool configuration:

```text
Shutdown: false
Result: still available
```

This example demonstrates that `close` does not close the common pool. In real applications, **there is no need to call `close` on the common pool**; instead, track your work's results using your own `Future`s.

## 9. Common Pool Uses Daemon Workers: Unfinished Tasks May Be Abandoned on JVM Exit

Standard `ForkJoinPool` workers are created as **daemon threads**. When no non-daemon threads remain, the JVM can exit **without waiting** for daemon workers to finish.

Therefore:

- Do not submit important work to the common pool and let `main` return without synchronization to wait for it.
- If you need the result of a single task, use `Future.get()` or `ForkJoinTask.join()`.
- If you need the results of a batch, use a list of `Future`s, a latch, or coordination with a clear contract.
- `awaitQuiescence` only reports that the pool is **temporarily idle** at a point in time; it does not prevent other components from submitting more work.
- If you need isolation from other workloads, use a private pool and manage its lifecycle.

With `CompletableFuture.supplyAsync(...)` without an explicit executor, typical environments use the common pool; however, some deployments/configurations use a different strategy when parallelism is too low. Do not design around a fixed thread count or worker name: rely on the `Future` contract and the chosen executor.

## 10. Choosing the Right API for Each Need

| Need | Preferred API | Reason |
| --- | --- | --- |
| Wait for a single task | `Future.get()` or `ForkJoinTask.join()` | Does not affect other tasks |
| Wait for your own group of tasks | List of `Future`s / `invokeAll` | Well-defined batch scope |
| Wait for a shut-down private pool to finish | `shutdown()` + `awaitTermination(timeout, unit)` | Has a deadline, returns boolean |
| Close a scope-owned private pool on JDK 21+ | `close()` / try-with-resources | Shuts down + waits for termination |
| Wait for a pool to become temporarily idle while keeping it reusable | `awaitQuiescence(timeout, unit)` | Does not shut down |
| Wait for the common pool to become temporarily idle | `commonPool().awaitQuiescence(...)` | Common pool does not terminate via normal shutdown |
| Interrupt tasks in a private pool on timeout | `shutdownNow()` after graceful deadline | Best effort, continue tracking termination |
| Need a pool with independent shutdown authority | `new ForkJoinPool(...)` | Private ownership, not using common pool |

**Limitation:** `close()` does not provide a timeout. A requirement like "shut down the entire system within 5 seconds" needs a bounded wait plan, a stop request upon expiration, and handling for tasks that do not stop; closing a scope with `close()` may not meet the SLA.

## 11. Timeouts, Interrupts, and Failures During Shutdown

### awaitTermination Interrupted

`awaitTermination` declares `throws InterruptedException`. If the caller is interrupted, propagate it or restore the interrupt flag after performing necessary cleanup. A pattern for a private pool:

```java
// Snippet for a private pool, not for the common pool.
pool.shutdown();
try {
    if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**What this snippet does not do:** it does not wait again after `shutdownNow()`. Production code may need a second `awaitTermination` with a separate budget or remaining time, logging any unresponsive tasks. Never report that the pool has terminated just because `shutdownNow()` returned.

### close Does Not Throw InterruptedException

`ForkJoinPool.close()` on JDK 21 does not declare `InterruptedException`. If the caller is interrupted while waiting to close a **private pool**, `close` switches to a `shutdownNow`-style stop request, continues waiting for running tasks to finish, and then restores the interrupt status.

**Do not catch `InterruptedException` solely around `close()`** when no other call throws that checked exception; the code will fail to compile due to an unreachable catch block.

### Tasks That Do Not Cooperate With Interruption

An infinite CPU loop that never checks the interrupt flag, an I/O call with no cancellation path, or a lock deadlock can prevent the pool from stopping even after `shutdownNow()`. `close()` can also hang because it **has no timeout**.

To handle this, design tasks with safe stopping points, appropriate I/O timeouts, resource cleanup in `finally`, and avoid running long blocking work inside ForkJoin workers when unnecessary. When forced to wait externally inside a ForkJoin algorithm, consider `ForkJoinPool.ManagedBlocker` so the pool is aware of the block and can try to compensate with another worker; it still does not eliminate deadlocks.

## 12. When Should You Avoid the Common Pool?

The common pool is convenient for short, independent work that does not need its own lifecycle. However, consider a private pool if:

1. There are many **blocking I/O** tasks or long-running tasks that contend for resources with other components.
2. You need **isolation**, custom parallelism, a custom thread factory, or workload-specific monitoring.
3. You want genuine **`shutdown` and `awaitTermination`** scoped only to your component's tasks.
4. You need dedicated backpressure, admission, or timeout policies.
5. You have a strict shutdown-time SLA or tasks that require an explicit lifecycle.

**Not every workload needs a private `ForkJoinPool`**: if the workload is primarily blocking I/O, an executor suited to that kind of work may be simpler; on JDK 21+, virtual threads can be considered when appropriate. Creating a private pool also consumes resources and requires shutdown, so ownership must be managed consistently.

## 13. Debugging a Pool That "Refuses to Stop"

If a private pool has been shut down but `isTerminated()` is still false after the timeout:

- Use a thread dump or JFR to see whether workers are waiting on a lock, I/O, latch, or another task.
- Check whether a worker is **waiting on a task queued in the same small pool**; this can be a thread starvation deadlock.
- Check locks held by the caller while waiting for termination.
- Verify whether tasks handle `InterruptedException` and `isInterrupted()` properly.
- Confirm the pool is actually a **private pool** rather than accidentally the common pool.
- Do not use `getQueuedTaskCount()` or `getActiveThreadCount()` as a synchronization barrier; they are rapidly changing status/estimate metrics.
- Check whether submitted tasks failed or were cancelled; `isTerminated` only describes the executor lifecycle, not that all business operations succeeded.
- Ensure resources used by workers remain alive until the workers have stopped.

### Do Not Hold a Lock While Waiting for the Pool

Dangerous example:

```java
// Conceptual snippet: caller holds resourceLock.
synchronized (resourceLock) {
    pool.shutdown();
    pool.awaitTermination(10, TimeUnit.SECONDS);
}
// If a worker needs resourceLock to finish, caller and worker wait for each other.
```

Not a standalone file: `resourceLock` and `pool` are undeclared, and exceptions are unhandled. This is a deadlock that can arise even though each individual API is thread-safe. You must allow workers to complete their work before the caller enters the wait.

## 14. Common Misconceptions

1. **"`shutdown()` on `commonPool` stops everyone's work."** False: it is a no-op on execution state.
2. **"`close()` on `commonPool` waits for all tasks."** False: on JDK 21 it neither waits nor closes.
3. **"`awaitTermination(commonPool)` returning false means no tasks have finished."** False: it is always false by contract, even when quiescent.
4. **"`awaitQuiescence` makes the pool terminated."** False: it only waits for temporary idleness, without shutting down.
5. **"`shutdown()` on a private pool already waits for all workers to finish."** False: `shutdown` is not `awaitTermination`.
6. **"`shutdownNow()` guarantees killing workers immediately."** False: it is best effort.
7. **"`ForkJoinPool.shutdownNow()` returns the list of waiting tasks."** False: `ForkJoinPool` always returns an empty `List`.
8. **"`isShutdown == true` means `isTerminated == true`."** False: there is still a draining phase.
9. **"`Future.get()` on one task means the entire pool has terminated."** False: it only waits for that task.
10. **"Common pool daemon workers will keep the JVM alive until they finish."** False: daemon threads do not keep the JVM alive.
11. **"Java 17 supports try-with-resources for `ForkJoinPool`."** False: `AutoCloseable`/`close` via `ExecutorService` was added in Java 19.
12. **"Closing a private pool has a default timeout."** False: it can wait indefinitely if tasks do not stop.
13. **"If the caller is interrupted, `close` throws `InterruptedException` immediately."** False: `close` requests stop, continues waiting, and restores the interrupt flag.
14. **"Quiescent true guarantees no new tasks will arrive."** False: if not shut down, new tasks can still be submitted.
15. **"`awaitTermination` automatically requests shutdown."** False: it only waits; it does not initiate shutdown.
16. **"Having a private pool solves data races."** False: two tasks modifying shared mutable state still need synchronization.
17. **"Every task submitted to `commonPool` gets an independent worker."** False: the pool schedules tasks across a shared set of workers.
18. **"Simply increasing parallelism fixes deadlocks."** False: lock-ordering cycles and business dependencies must be fixed in the design.

## 15. Lifecycle Selection Checklist

1. Determine whether the **pool is common or private** before calling any shutdown API.
2. Distinguish whether you need to **wait for one `Future`, a batch, quiescence, or termination**.
3. If you own a private pool, place `shutdown` in an explicit lifecycle hook or `finally` block.
4. When a deadline is required, use `awaitTermination(timeout)` and decide the next step if it returns false.
5. Do not infer from `shutdownNow()` returning that tasks have stopped.
6. On JDK 21+, use `close()` / try-with-resources **only for scope-owned private pools**, when waiting until terminated is acceptable.
7. Do not use `close`/`shutdown` on the common pool as a barrier or cleanup mechanism.
8. When using the shared common pool, wait on your own tasks' `Future`s rather than vaguely waiting for "the whole JVM".
9. If using `awaitQuiescence`, remember it is a temporary state that can change as soon as a new task arrives.
10. Distinguish task failures, cancellation, and pool lifecycle; read results through `Future`.
11. Never hold locks or resources needed by workers while calling `awaitTermination` or `close`.
12. Design tasks to respond to interruption and use I/O timeouts where needed.
13. Measure shutdown latency, waiting workers, queues, and thread dumps instead of guessing from a single snapshot.
14. Test shutdown behavior while tasks are still waiting using explicitly coordinated latches or conditions.
15. Ensure resources used by workers are closed **only after** the relevant workers have stopped using them.

## 16. Standard References

- [ForkJoinPool API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [ExecutorService API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [ForkJoinTask API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)

**Takeaway:** `commonPool()` is a shared resource, so `shutdown()`, `shutdownNow()`, and `close()` **do not stop it**; `awaitTermination` on the common pool always returns false. Use `awaitQuiescence` for a temporary idle state, or `Future`s when you need specific task results. For a **private `ForkJoinPool`**, manage ownership explicitly and use `shutdown()` + `awaitTermination()`, or `close()` on JDK 21+, to end its lifecycle. Do not confuse requesting shutdown, the quiescent state, and the terminated state, and do not treat shutdown as a guarantee that all business tasks succeeded.
