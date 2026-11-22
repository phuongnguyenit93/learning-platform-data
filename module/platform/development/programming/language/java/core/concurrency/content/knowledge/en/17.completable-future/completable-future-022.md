# CompletableFuture.delayedExecutor(): Scheduling Execution Without Blocking the Waiting Thread

## 1. Practical Scenario and Goal

A Java system may need to **start a step after a delay**: wait briefly before retrying a transiently failing operation, delay recording a metric, trigger a processing step when a time condition is met, or space out two service calls. An obvious approach that comes to mind is:

~~~java
// Not a standalone program.
Thread.sleep(500);
doWork();
~~~

`Thread.sleep(500)` **blocks the currently running thread** for the duration of the sleep. If this line is on a request thread, event handler, or a worker pool with few threads, it ties up a thread so it cannot do other work. If thousands of tasks "wait a bit" at the same time, using sleep to delay each task can waste workers and cause bottlenecks.

Since **Java 9**, `CompletableFuture.delayedExecutor(...)` provides another way: **scheduling work to be submitted to an executor after a delay**, instead of forcing the caller thread to sleep until that time.

~~~java
// API signatures; not a standalone program.
static Executor delayedExecutor(long delay, TimeUnit unit);

static Executor delayedExecutor(
    long delay, TimeUnit unit, Executor executor);
~~~

Both overloads return an **`Executor`**; they do not return a `ScheduledFuture`, do not return a business result on their own, and do not create a Future to track a single task. We typically combine the returned executor with `CompletableFuture.runAsync(...)`, `supplyAsync(...)`, or continuations such as `thenApplyAsync(...)`, `thenRunAsync(...)`.

**Key principle:** **Scheduling the start** does not block the caller. However, if the caller proceeds to call `join()` or `get()` immediately on an incomplete Future, **that waiting call itself** can still block the caller.

This article falls within the scope of **general Java concurrency** and uses only standard JDK APIs, without going into framework mechanisms.

### Learning Objectives

After this article, you will be able to:

1. Explain three points in time: **scheduling submission**, **delay expiration**, and **actual execution by a worker**.
2. Distinguish between the two `delayedExecutor` overloads and explain why you should pass a base executor for workloads with operational requirements.
3. Understand that each `execute(...)` call on a delayed executor starts a **separate** delay.
4. Combine `runAsync`, `supplyAsync`, and `thenApplyAsync` with a delayed executor.
5. Write Java 17+ examples that are correct regarding lifecycle, exceptions, timeouts, and stdout output.
6. Avoid using `cancel(true)` on `CompletableFuture` as proof that the supplier was interrupted or that external work stopped.
7. Know when to choose `ScheduledExecutorService`, `ScheduledFuture`, a retry policy with a deadline, or another scheduling construct.
8. Test in a controlled manner without asserting that the scheduler runs at an exact wall-clock timestamp.

## 2. API Contract: What Does delayedExecutor Actually Do?

The `CompletableFuture` Javadoc describes: the method returns an executor that **submits a task to the underlying executor after the given delay**, or **with no delay if the delay value is non-positive**. Each delay begins when `execute` is called on the returned executor.

~~~text
Caller thread                    delayed executor            base executor
     |                                 |                           |
     |-- execute(runnable) ----------->|                           |
     |<--------- returns --------------|                           |
     |                                 |  waits for time condition |
     |     caller does other work      |                           |
     |                                 |---- submit runnable ----->|
     |                                 |                           |
     |                                 |                   worker runs runnable
     |                                 |                           |
     |                                 |                   runnable completes
~~~

Unlike `Thread.sleep()`, waiting for the delay in the diagram **does not force the caller to hold a sleeping thread for each scheduled task**. Internal timer/scheduler details are a JDK implementation matter and you should not rely on the number of internal threads or internal thread names as an API contract.

### 2.1. Three Points in Time to Distinguish

| Milestone | Meaning | Precision You Can Rely On |
| --- | --- | --- |
| **T0 – calling `execute`** | Caller asks the delayed executor to accept the task; the delay timer for that call starts | Logical timestamp of the request |
| **T1 – delay elapsed** | Task becomes eligible to be submitted to the base executor | Not a guarantee that the task has already run |
| **T2 – base worker starts** | Thread assigned by the base executor executes the task | May be later than T1 due to queue/scheduler/load |
| **T3 – task completes** | The associated `CompletableFuture` has an outcome | May be later than T2 due to CPU/I/O or blocking |

Do not equate `delay = 500 ms` with "the task will finish after exactly 500 ms". A delayed executor does not provide millisecond-exact real-time SLAs; the scheduler, OS, CPU, GC, executor queue, and system load can cause the task to execute **after** it becomes eligible.

### 2.2. Two Overloads

**Without providing a base executor:**

~~~java
// Java 17+ snippet, not a standalone program.
Executor delayed =
    CompletableFuture.delayedExecutor(
        250, TimeUnit.MILLISECONDS);
~~~

The task is submitted to the **default executor** according to the `CompletableFuture` contract. You should not assume that blocking I/O tasks are suitable for the default async execution facility. Most typical uses of `CompletableFuture` involve `ForkJoinPool.commonPool()` as specified by the class, along with parallelism exceptions; check the contract of the JDK you are running.

**With an explicit base executor:**

~~~java
// Java 17+ snippet, not a standalone program.
ExecutorService base =
    Executors.newFixedThreadPool(4);

Executor delayed =
    CompletableFuture.delayedExecutor(
        250, TimeUnit.MILLISECONDS, base);
~~~

When the delay expires, work is submitted to `base`; you actively manage pool size, thread names, queue, rejection policy, and shutdown. `delayed` only has type `Executor` and has no `shutdown()`; if the base executor is an `ExecutorService`, it must be managed according to the application's lifetime.

### 2.3. A Delayed Executor Does Not Execute Business Logic on Its Own

~~~java
// Illustrative snippet; not a standalone program.
Executor delayed =
    CompletableFuture.delayedExecutor(100, TimeUnit.MILLISECONDS);

// Only creates the Executor; no runnable has been registered yet.
~~~

No task is scheduled merely because you created the executor. The delay for a task actually begins when **`delayed.execute(runnable)` is called** — typically inside `runAsync(...)` or when an async continuation becomes ready to run.

## 3. Example 1 — Positive Delay Without Caller Sleeping (Java 17+)

We use a positive delay and two latches. The first latch signals that the worker has started, and the second latch keeps the worker **unfinished** until main checks `isDone()`. This makes the output deterministic without having to guess OS execution duration.

Create the file `DelayedStartDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedStartDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                30, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> job =
                CompletableFuture.supplyAsync(() -> {
                    entered.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                            "worker interrupted", ex);
                    }
                    return "finished";
                }, delayed);

            // Main does not use sleep to hold a thread waiting for the delay.
            // The latch confirms the worker has actually started.
            entered.await();
            System.out.println("worker started = true");
            System.out.println("done before release = "
                + job.isDone());

            release.countDown();
            System.out.println("result = " + job.join());
        } finally {
            release.countDown();
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac DelayedStartDemo.java
java DelayedStartDemo
~~~

Stdout without spurious interruption:

~~~text
worker started = true
done before release = false
result = finished
~~~

**Explanation:**

1. `supplyAsync(..., delayed)` submits the runnable to the delayed executor; the method returns a `CompletableFuture<String>` **immediately, without the caller sleeping for 30 ms**.
2. After the delay elapses, the runnable is submitted to `base`. The worker calls `entered.countDown()`, then waits on `release`.
3. Main waits for a **verifiable event** `entered`, rather than using `Thread.sleep(...)` to guess whether the worker has started.
4. Main prints `job.isDone() == false` before opening `release`, because the worker is still waiting on the latch.
5. Main releases the latch, `join()` waits for the completed value and prints `finished`.
6. `finally` releases the latch even if an error occurs in the caller, then shuts down the base pool to avoid leaking workers.

The key distinction: the example **has `entered.await()` and `join()` causing main to wait for verification**, but **the scheduling action itself** by the delayed executor does not block main during the delay. These are two different actions. In a real application, the caller can receive the Future and continue processing other work instead of waiting.

## 4. Each execute Call Has Its Own Delay

An `Executor delayed` can be reused for multiple tasks. Do not think of it as a single clock that starts at the moment you call `delayedExecutor(...)`.

~~~java
// Java 17+ snippet, not a standalone program.
Executor delayed = CompletableFuture.delayedExecutor(
    500, TimeUnit.MILLISECONDS, base);

CompletableFuture<Void> a =
    CompletableFuture.runAsync(this::doA, delayed);

// Later, at another point in time:
CompletableFuture<Void> b =
    CompletableFuture.runAsync(this::doB, delayed);
~~~

A's delay starts when A's runnable is submitted via `execute`. B's delay starts **when B's runnable is submitted**, not from when the delayed executor object was created and not from when A was submitted.

This is very important when building retries, deferred callbacks, or multi-stage workflows. Each submission creates a new delay request; a delayed executor does not mean a periodic schedule.

### 4.1. Example 2 — Reusing the Same Delayed Executor Multiple Times (Java 17+)

Create the file `ReuseDelayedExecutorDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ReuseDelayedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newFixedThreadPool(2);
        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<Integer> a =
                CompletableFuture.supplyAsync(() -> 10, delayed);
            CompletableFuture<Integer> b =
                CompletableFuture.supplyAsync(() -> 20, delayed);

            CompletableFuture.allOf(a, b).join();
            System.out.println("results = "
                + List.of(a.join(), b.join()));
            System.out.println("both done = "
                + (a.isDone() && b.isDone()));
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ReuseDelayedExecutorDemo.java
java ReuseDelayedExecutorDemo
~~~

Stdout:

~~~text
results = [10, 20]
both done = true
~~~

Two runnables are submitted through the **same delayed executor object**, but each `supplyAsync` call registers its own task and starts its own delay. `allOf` waits for both Futures to complete, and then values are retrieved in order A, B — **not the completion order on the workers**.

Do not use the elapsed time of this example to infer that the scheduler met 20 ms exactly; it only verifies the **result and coordination contract**.

### 4.2. Non-Positive Delays

The Javadoc allows a delay of **0 or negative**: no positive delay is applied. This is valid when you have a shared pipeline whose delay parameter is computed dynamically.

~~~java
// Java 17+ snippet, not a standalone program.
Executor noDelay = CompletableFuture.delayedExecutor(
    0, TimeUnit.MILLISECONDS, base);
~~~

**Do not infer that `delay <= 0` makes the task run immediately on the caller thread.** It is still an `Executor` mechanism; execution depends on the base executor and the scheduler. "No added delay" is different from "synchronous execution".

If a negative value occurs due to deadline calculation drift, understand it as a request to run without delay, not an error that forces the JDK to throw an exception. However, **null `TimeUnit` or base executor** is not valid; avoid passing null and validate caller-supplied parameters.

## 5. Where Does It Run? The Importance of the Base Executor

With the three-parameter overload:

~~~java
// Java 17+ snippet, not a standalone program.
Executor delayed =
    CompletableFuture.delayedExecutor(
        100, TimeUnit.MILLISECONDS, ioPool);
~~~

The delayed executor is a **forwarding layer**. After the delay, the task is **submitted to `ioPool`**; which thread executes it is decided by `ioPool`.

- **Single-worker** base executor: two eligible tasks may have to run sequentially if one task occupies the worker.
- **Multi-worker** base executor: tasks have the opportunity to run concurrently up to pool capacity.
- **Bounded-queue** base executor: under overload, submission may be rejected according to the rejection policy.
- Base executor **already shut down** before submission time: delayed runnables are no longer guaranteed to be accepted.
- Custom base executor running inline: the contract accepts custom base executors, but you must understand how that executor runs runnables. Do not assume a new thread per task.

**Do not promise a completion time equal to the delay** when the base executor has a long queue. Delay only governs when the task is submitted to the base, not when a worker starts it.

### 5.1. Example 3 — Controlling the Execution Thread Name (Java 17+)

Create the file `DelayedBaseExecutorDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedBaseExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "delayed-base-1")
        );

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                25, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> currentThreadName =
                CompletableFuture.supplyAsync(
                    () -> Thread.currentThread().getName(), delayed
                );

            System.out.println("running on = "
                + currentThreadName.join());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac DelayedBaseExecutorDemo.java
java DelayedBaseExecutorDemo
~~~

Stdout:

~~~text
running on = delayed-base-1
~~~

The task actually runs on the thread created by `base`, not on main just because main called `supplyAsync`. When no base is provided, you also should not rely on internal thread names as a public contract.

In production, configure a `ThreadFactory` with pool-based incrementing names instead of a fixed name if there are multiple workers. In addition, manage unhandled task failures and executor lifecycle according to application policy.

## 6. delayedExecutor in a CompletionStage Chain

Beyond `supplyAsync`, a delayed executor can also be used in `...Async(..., Executor)` methods.

For example:

~~~java
// Java 17+ snippet, not a standalone program.
CompletableFuture<String> response =
    firstStage.thenApplyAsync(
        value -> normalize(value),
        CompletableFuture.delayedExecutor(
            200, TimeUnit.MILLISECONDS, base)
    );
~~~

The continuation `normalize(value)` is not submitted to the delayed executor **before `firstStage` completes normally**. Once `firstStage` completes, the dependent stage logic submits the runnable to the delayed executor; **from that moment on**, the continuation's delay begins.

If `firstStage` fails, a normal `thenApplyAsync` does not run the `normalize` function. The dependent Future completes exceptionally per CompletionStage semantics; there is no reason to "sleep 200 ms and then throw" just because you attached a delayed executor to a success-only continuation.

### 6.1. thenApply vs. thenApplyAsync

- `thenApply(fn)` takes no executor; the function may run synchronously on the stage-completing thread or the registering thread if the stage is already done, depending on the situation.
- `thenApplyAsync(fn)` uses the default async executor.
- `thenApplyAsync(fn, delayed)` registers a continuation to be submitted via the delayed executor **after the dependency is ready**.
- `thenRunAsync(action, delayed)` is used when the continuation does not need the input value.
- `handleAsync((value, error) -> ..., delayed)` can run on both normal and exceptional completion, though exception handling must follow a clear policy.

Do not use a `thenApply` without an executor parameter and assume that a delayed executor in an earlier stage will automatically delay **all** subsequent continuations. Each stage has its own execution policy.

### 6.2. Example 4 — Delay Only Starts After Upstream Completes (Java 17+)

Create the file `DelayedContinuationDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedContinuationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> upstream =
                new CompletableFuture<>();

            Executor delayed = CompletableFuture.delayedExecutor(
                30, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> downstream =
                upstream.thenApplyAsync(
                    text -> text + "-after-delay", delayed);

            System.out.println("before upstream = "
                + downstream.isDone());

            upstream.complete("ready");
            System.out.println("result = " + downstream.join());
            System.out.println("upstream = " + upstream.join());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac DelayedContinuationDemo.java
java DelayedContinuationDemo
~~~

Stdout:

~~~text
before upstream = false
result = ready-after-delay
upstream = ready
~~~

Because `upstream` is not yet complete at the first print line, `downstream` cannot complete. When `upstream.complete("ready")` runs, the continuation becomes eligible for submission via the delayed executor. Main's subsequent `join()` **may wait**, but **attaching the continuation** initially does not block the caller.

If upstream never completes, the continuation's delay **never starts**. This is a major difference from an "absolute timer starting from pipeline creation" model.

### 6.3. Cumulative Delays in a Multi-Stage Chain

~~~java
// Java 17+ snippet, not a standalone program.
Executor delayed = CompletableFuture.delayedExecutor(
    100, TimeUnit.MILLISECONDS, base);

CompletableFuture<String> result =
    CompletableFuture.completedFuture("A")
        .thenApplyAsync(s -> s + "B", delayed)
        .thenApplyAsync(s -> s + "C", delayed);
~~~

The two continuations are **not** submitted at the same time. The second stage only becomes eligible after the first stage completes; each submission through `delayed` creates a separate delay. Thus, **two consecutive waiting intervals** plus execution/queue time may occur. Do not assume a total time of exactly 200 ms.

If you want to "delay only once before the whole chain", schedule the first stage with the delayed executor, and then use non-delayed continuations or specify the base executor as desired.

## 7. Common Misconceptions: Delay, Blocking, Completion

### 7.1. Non-Blocking Scheduling Does Not Mean Non-Blocking Business Code

~~~java
// Illustrative, not a standalone program.
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> readBlockingSocket(),
        CompletableFuture.delayedExecutor(
            100, TimeUnit.MILLISECONDS, base)
    );
~~~

The caller does not have to sleep for 100 ms to schedule. However, when the worker eventually runs `readBlockingSocket()`, **that worker can still be blocked by the socket**. `delayedExecutor` does not turn a synchronous I/O API into non-blocking I/O.

If there are many long-blocking I/O tasks, you need connection limits, pool configuration, timeouts, and cancellation appropriate to the I/O source. A delayed executor only addresses **submission timing**, not all blocking problems.

### 7.2. join() and get() Still Wait

~~~java
// May block the caller until delay + work complete.
String value = CompletableFuture.supplyAsync(
    () -> "done", delayedExecutor).join();
~~~

This snippet is written with an async API, yet the caller still waits for the result. The non-blocking way to use it is to **keep the Future for composition**:

~~~java
// Illustrative snippet, not a standalone program.
CompletableFuture<String> value =
    CompletableFuture.supplyAsync(
        () -> "done", delayedExecutor);

CompletableFuture<Void> useLater =
    value.thenAccept(this::consume);
// Caller can continue with other work.
~~~

Choose the pattern according to the caller's contract: if the result is needed immediately, waiting may be intentional; if you only want to schedule, do not call `join` immediately.

### 7.3. Delay Is Not a Deadline

`delayedExecutor(500, MILLISECONDS)` means **wait before submitting**. `orTimeout(500, MILLISECONDS)` means **if the Future has not completed within that time, complete it exceptionally with TimeoutException**. These are opposite meanings:

| API | Target Behavior |
| --- | --- |
| `delayedExecutor(d, unit)` | Delays submitting the runnable to the base executor |
| `Thread.sleep(d)` | Blocks the current thread for the wait duration |
| `CompletableFuture.orTimeout(d, unit)` | Sets an exceptional completion timeout on the Future if not done |
| `CompletableFuture.completeOnTimeout(v, d, unit)` | Completes the Future with a fallback value if not done |
| `Future.get(d, unit)` | Limits how long the **caller waits** |
| `ScheduledExecutorService.schedule(..., d, unit)` | Schedules a one-shot task and returns a `ScheduledFuture` |
| `scheduleAtFixedRate/scheduleWithFixedDelay` | Periodic schedules; not built into `delayedExecutor` |

`orTimeout` and `completeOnTimeout` return **the same CompletableFuture they are called on**, not an independent copy by default. Both affect **the Future's outcome**, rather than automatically interrupting running work or canceling an already-sent network call.

### 7.4. Why Not Use Delay to "Ensure Task A Has Finished"?

Mistake:

~~~java
// WRONG: does not guarantee A has completed.
startA();
CompletableFuture.runAsync(
    this::startB,
    CompletableFuture.delayedExecutor(
        100, TimeUnit.MILLISECONDS)
);
~~~

If A takes 500 ms, B can still start before A finishes. When B **depends on A's result**, use `thenRun`, `thenCompose`, or a continuation depending on A's Future instead of guessing duration with an arbitrary delay.

Delay is a **time-based scheduling** tool; Future dependencies are the way to express "after another piece of work completes".

## 8. Exceptions and Failure Handling

A task run via `supplyAsync` or `runAsync` may throw an unchecked exception. The corresponding `CompletableFuture` will complete exceptionally.

### Example 5 — Error from a Delayed Task Is Held in the CompletableFuture (Java 17+)

Create the file `DelayedFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalArgumentException("invalid");
                }, delayed);

            try {
                result.join();
            } catch (CompletionException ex) {
                System.out.println("failure = "
                    + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("exceptional = "
                + result.isCompletedExceptionally());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac DelayedFailureDemo.java
java DelayedFailureDemo
~~~

Stdout:

~~~text
failure = IllegalArgumentException
exceptional = true
~~~

`join()` can throw `CompletionException` wrapping the task's cause. If using `get()`, a failed task is normally reported via `ExecutionException`. Do not leave exceptions held in a Future with nobody observing them: if a task is important, the caller must have monitoring, a callback, or future composition.

**Do not treat `delayedExecutor` as an error handler.** It only decides when to hand the task to the base executor. Retries, fallbacks, circuit breaking, logging, and error classification are separate responsibilities.

### 8.1. Base Executor Rejecting a Task

Consider the scenario:

~~~text
T0: delayed.execute(task) is called, delay has not elapsed
T1: application shuts down base executor
T2: delay elapses, delayed executor tries to submit task to base
T3: base refuses the task because it is shut down
~~~

There is no guarantee a task will run successfully if `base` no longer accepts work. `RejectedExecutionException` and the base executor's rejection policy must be observed. **Do not assume every implementation turns all late rejection errors into the exact same exception in the Future**; test against your actual JDK and base executor, set deadlines for awaiting outcomes, and manage shutdown in an orderly manner.

A common operational mistake is shutting down `base` right after registering delayed tasks without waiting for those tasks to be handed off/executed. Lifetime design must cover both the delay wait and the task execution time.

## 9. Cancellation: Canceling a Future Does Not Guarantee Work Stops

### 9.1. CompletableFuture.cancel Has Its Own Limitations

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` marks the Future as completed with a cancellation state if cancellation is accepted. Per the `CompletableFuture` contract, the `mayInterruptIfRunning` parameter **is not used to control task execution**; do not treat `cancel(true)` as a promise that the worker will be interrupted.

For a task that has already started:

- The Future can report cancelled while user code is still running.
- The worker can continue performing side effects after the Future is cancelled.
- Cancellation does not automatically close connections, roll back transactions, or complete cleanup.
- If the task already completed before cancel, `cancel` cannot change the prior terminal outcome.
- If cancelled before the runnable actually runs, the implementation may avoid invoking user code, but **do not rely on that as an external task-cancellation mechanism**.

### 9.2. Example 6 — Future Cancelled, Yet Running Task Still Completes Side Effect (Java 17+)

This example uses a latch to ensure the task **has already started** before cancellation; thus it does not depend on a race of "canceling before the worker picks up the task".

Create the file `DelayedCancellationDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayedCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sideEffect = new AtomicBoolean();

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<Void> future =
                CompletableFuture.runAsync(() -> {
                    entered.countDown();
                    try {
                        release.await();
                        sideEffect.set(true);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        finished.countDown();
                    }
                }, delayed);

            entered.await();
            boolean cancelled = future.cancel(true);
            release.countDown();
            finished.await();

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("future cancelled = "
                + future.isCancelled());
            System.out.println("side effect = "
                + sideEffect.get());
        } finally {
            release.countDown();
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac DelayedCancellationDemo.java
java DelayedCancellationDemo
~~~

Stdout in a test run without unintended interrupts:

~~~text
cancel accepted = true
future cancelled = true
side effect = true
~~~

Analysis:

1. `entered.await()` ensures the runnable has started, called `entered.countDown()`, and is waiting on `release` or about to reach the wait call.
2. Main calls `future.cancel(true)` while the Future is not yet complete. `CompletableFuture` marks it cancelled, but **there is no guarantee of interrupting the worker**.
3. Main releases `release`, and the worker proceeds with `sideEffect.set(true)`. `finished` indicates the final code path executed.
4. The Future remains in the cancelled state, even though user code performed the side effect.
5. `finally` ensures the latch is released even if the caller encounters an error, preventing the worker from getting stuck; `base` is shut down.

**Lesson:** If you need to truly cancel work, you must design a cancellation token checked by the worker, use cancellable I/O APIs, enforce deadlines, or use appropriate executor/task ownership. Merely canceling a `CompletableFuture` is not enough to prove resources were released.

### 9.3. Canceling Before the Delay Expires

If the Future is cancelled while the task is still waiting on the schedule, depending on the implementation user code might not be invoked when the runnable eventually reaches `base`. However, a previously registered timer may still exist until expiration, and the cancellation outcome does not guarantee all internal scheduling resources are removed in the way you might expect.

If the requirement is to **precisely cancel an unfired timer**, consider `ScheduledExecutorService.schedule`, where the caller holds a `ScheduledFuture` to call `cancel(...)` per contract. `delayedExecutor` only returns an `Executor`, with no `cancel(taskId)` method.

## 10. Why Isn't delayedExecutor an All-Purpose Scheduler?

### 10.1. It Only Returns an Executor

`Executor.execute(Runnable)` has a `void` return type. You can obtain a `CompletableFuture` when using `runAsync`/`supplyAsync`, but that is the **task's result Future**, not a `ScheduledFuture` for directly managing the schedule.

The following methods do not exist on the object returned by `delayedExecutor`:

~~~java
// Invalid if delayed is declared only as Executor:
// delayed.scheduleAtFixedRate(...);
// delayed.scheduleWithFixedDelay(...);
// delayed.getDelay(...);
// delayed.shutdown();
~~~

For periodic schedules, use `ScheduledExecutorService` or a scheduling mechanism with a clear lifecycle. For delaying **an asynchronous step** in a `CompletableFuture` pipeline, `delayedExecutor` is a natural representation.

### 10.2. Comparison with ScheduledExecutorService

| Feature | `CompletableFuture.delayedExecutor` | `ScheduledExecutorService` |
| --- | --- | --- |
| Scheduling API result | `Executor` | Service supporting `schedule` and periodic APIs |
| Submitting a runnable | `execute`, or via `runAsync` | `schedule(command, delay, unit)` |
| Return handle of a submission | `execute` returns void; `runAsync` returns `CompletableFuture` | `schedule` returns `ScheduledFuture` |
| Delay | Before submitting to base executor | Waits until eligible to run per scheduler |
| Periodic schedules | No built-in periodic methods | `scheduleAtFixedRate`, `scheduleWithFixedDelay` |
| Canceling a specific schedule | No separate timer handle from `Executor` | Has `ScheduledFuture.cancel(...)` |
| Lifecycle | Base executor must be managed separately | Service has `shutdown` and `awaitTermination` |
| Pipeline composition | Very convenient in `thenApplyAsync` / `runAsync` | Needs bridging to Future/CompletableFuture to compose |

Both are affected by the OS scheduler and load; neither API here turns a program into a hard real-time scheduler.

### 10.3. Example 7 — ScheduledFuture with a Cancellation Handle (Java 17+)

Create the file `ScheduledAlternativeDemo.java`:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledAlternativeDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<String> task = scheduler.schedule(
                () -> "scheduled-ok",
                20, TimeUnit.MILLISECONDS
            );

            System.out.println("result = " + task.get());
            System.out.println("done = " + task.isDone());
        } finally {
            scheduler.shutdown();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ScheduledAlternativeDemo.java
java ScheduledAlternativeDemo
~~~

Stdout:

~~~text
result = scheduled-ok
done = true
~~~

`schedule` returns `ScheduledFuture<String>`, allowing you to retrieve the result and observe/cancel pending tasks per contract. In this example we do not cancel because we want to print a deterministic success result, but having this handle is an important design difference from `delayedExecutor`.

**Note:** `cancel(true)` on `ScheduledFuture` also does not guarantee that all side effects were rolled back or that every task running in native I/O stopped immediately; interrupt/cancel capability depends on task state and code.

## 11. Backoff and Retry: Delay Does Not Replace a Retry Policy

An application might want to retry after 100 ms when a service fails transiently. Using sleep in each worker:

~~~java
// Simple, but holds the worker during backoff.
try {
    callRemote();
} catch (TransientFailure ex) {
    Thread.sleep(100);
    retry();
}
~~~

If thousands of tasks are backing off simultaneously, the pool can be occupied by threads doing no useful work. With a delayed executor, you can **turn the retry step into a stage scheduled for later**, without holding the original worker in a sleep.

### 11.1. Single-Retry Asynchronous Pattern

~~~java
// Java 17+ snippet, not a standalone program.
// ioExecutor, first, callRemote() are already defined.
Executor later = CompletableFuture.delayedExecutor(
    200, TimeUnit.MILLISECONDS, ioExecutor);

CompletableFuture<String> recovered =
    first.handle((value, error) -> {
        if (error == null) {
            return CompletableFuture.completedFuture(value);
        }
        return CompletableFuture.supplyAsync(
            () -> callRemote(), later);
    }).thenCompose(next -> next);
~~~

Idea:

1. If `first` succeeds, return an already-completed Future with the same value; **do not delay the success branch**.
2. If `first` fails, create a Future for the **retry attempt** using `supplyAsync(..., later)`. Submitting the retry does not hold a thread waiting for 200 ms.
3. `thenCompose` **flattens** `CompletableFuture<CompletableFuture<String>>` into a single result Future.
4. Errors from the retry are reflected in `recovered`, not turned into a false success.

**This is a conceptual pattern, not a production retry engine.** It only retries once and currently retries **all errors**, including ones that should not be retried. In production, you must classify transient errors, limit attempts, enforce an overall deadline, use jitter/backoff, ensure idempotency, and use real I/O cancellation mechanisms.

### 11.2. Exponential Backoff and Jitter

A policy might compute:

~~~text
attempt 1 -> delay 100 ms
attempt 2 -> delay 200 ms
attempt 3 -> delay 400 ms
attempt 4 -> delay 800 ms
+ bounded jitter so multiple clients do not retry at the exact same instant
~~~

Do not double the delay value indefinitely in `long`; cap it with a ceiling, perform overflow-safe arithmetic, and bound the total time. Do not retry infinitely without a deadline or cancellation token. Retrying tasks with side effects is only safe when the operation is designed to be idempotent or has duplicate suppression.

### 11.3. Queue Growth and Memory Pressure

Delaying submission avoids holding **sleeping** workers, but **does not eliminate waiting state** in the system. If many tasks per second are scheduled minutes into the future, there are still schedule entries, callbacks, Futures, and closures waiting in memory.

Measure pending requests, wait times, enqueue rate, and the base executor's processing capacity. A delayed executor does not enforce a limit on pending tasks on its own. If backpressure is needed, you must design queue/capacity limits or use a scheduler with an explicit policy.

## 12. Lifecycle: Shutting Down at the Right Time to Avoid Losing Work

A common sequence is:

~~~text
T0: create base executor
T1: create delayedExecutor(500 ms, base)
T2: submit CompletableFuture.supplyAsync(..., delayed)
T3: caller wants to shut down the application
T4: task has not yet reached submission time into base
~~~

If `base.shutdown()` happens at T3, it may refuse to accept the task at T4. This differs from a task that **was already accepted by base** before shutdown, which may still be executed under the `ExecutorService.shutdown()` contract.

**Application-level handling pattern:**

- Stop accepting new requests before closing the pool.
- Track deferred tasks that remain the application's responsibility.
- Set a deadline for awaiting completion of critical Futures.
- If the deadline expires, record incomplete tasks and apply a cancellation or recovery policy.
- Only shut down the base executor when no more tasks need to be submitted to it, or once losing/canceling those tasks is acceptable.
- Do not assume `CompletableFuture.cancel(true)` immediately cancels external work.
- When work must survive JVM restarts/crashes, persist the schedule in durable storage rather than relying solely on an in-memory schedule.

### 12.1. Limitations of `finally` in the Examples

The simple examples call `future.join()` before shutting down, so `base` usually stays alive until the task completes. In production, if you **do not await any Future** and instead shut down the pool right after scheduling, that is a lifecycle bug that easily creates hanging Futures or tasks that fail to complete as expected.

Nor should you solve this with `Thread.sleep(delay + 100)` at the end of `main`; that only guesses the schedule and does not confirm work executed. Waiting via Futures, latches, a task registry, or a proper shutdown protocol is much safer.

### 12.2. Critical Tasks Needing Durable Scheduling

`delayedExecutor` is an in-memory JDK mechanism; it does not persist tasks to a database, does not restore them after a process crash, and does not guarantee exactly-once business delivery. For tasks like "send invoice after 24 hours", consider storing the schedule/job in a durable store with ack/retry/idempotency.

This is an architectural boundary, not a flaw to "patch" by adding another `Thread.sleep` or more workers to the pool.

## 13. Performance and Timing Accuracy

### 13.1. Actual Latency Has Multiple Components

Observed latency can be described as:

~~~text
end-to-end latency
  = scheduled delay duration
  + scheduling jitter/error
  + base executor queue wait time
  + task execution time
  + callback / outcome publishing time
~~~

This formula is an analytical model, not a JDK commitment reporting each quantity separately. If the base executor is overloaded, the queue component can be larger than the delay you configured.

### 13.2. How to Benchmark Properly

- Measure `System.nanoTime()` for **duration**; do not use wall-clock `currentTimeMillis()` to compute accurate elapsed time.
- Warm up the JIT and run multiple iterations under representative load.
- Measure median, p95/p99, and the percentage of tasks starting late relative to their expected time.
- Separate the time from `execute` to eligibility from the time spent queuing/starting on a base worker; do not blame all latency on the timer.
- Compare with the same pool size and same workload if evaluating differences against `ScheduledExecutorService`.
- For I/O, monitor connection usage, timeouts, thread pool saturation, and pending task count.
- Do not claim real-time accuracy based on a single run with `delay=10 ms`.
- If a task must not run **earlier than** a business deadline, define the deadline contract using a monotonic clock and request creation time; do not use a chain of sleeps to guess time.

### 13.3. Fairness and Execution Order

Two tasks with the same delay have no guarantee that **completion order** matches submission order. Tasks are handed to `base` after their delay expires, but `base` has multiple workers, its own queue policy, and its own scheduler.

If business logic requires task B to run **after task A succeeds**, create a dependency using `thenCompose`/`thenRun`. If total ordering of events is required, use a queue/single-thread executor under the appropriate contract and analyze failure cases; merely setting the same delay does not turn tasks into a FIFO transaction.

## 14. Common Mistakes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Thinking `delayedExecutor(...)` starts a task by itself | It only creates an Executor; `execute` has not been called | Use `runAsync/supplyAsync` or `execute` |
| Thinking the delay starts when the Executor is created | Delay starts per `execute` call | Associate the timestamp with each submission |
| Using `Thread.sleep` in the caller for scheduling | Blocks caller, does not create deferred submission | Use a delayed executor or scheduler |
| Calling `join()` immediately and claiming it is non-blocking | `join()` still waits on the Future | Return the Future or compose callbacks |
| Thinking `delay=0` runs on the caller | It just adds no delay; `base` still decides | Do not rely on thread identity outside the contract |
| Thinking the task starts at exactly T0 + delay | `base` may be busy or have a long queue | Define SLAs, measure delay and queue separately |
| Using `thenApplyAsync(..., delayed)` and expecting delay from pipeline creation | Delay starts when the continuation is submitted, usually after upstream completes | Distinguish stage readiness from time delay |
| Attaching a delayed executor to stage A and expecting all later stages to be delayed | Each stage has its own executor/scheduling policy | Specify the executor on each stage that needs delay |
| Using delay to replace an A → B dependency | Delay does not guarantee A has finished | Use completion stage dependencies |
| Using delay to replace a timeout | Delay postpones starting, does not bound duration | Use deadlines/`orTimeout`/`get(timeout)` |
| Assuming Future cancel means the worker stopped | `CompletableFuture.cancel` does not mandate interrupting | Use a dedicated cancellation protocol |
| Assuming `runAsync` on delayed always runs after `base` shutdown | `base` may reject the task | Keep `base` alive for the full lifetime, handle failures |
| Using delayed executor for periodic execution | Only delays each `execute`, no periodic API | Use `ScheduledExecutorService` |
| Using delayed executor as a durable scheduler across process restarts | In-memory only, no persistence | Persist jobs/schedules when needed |
| Not bounding pending delayed tasks | Scheduling/closure/GC resources can grow | Apply backpressure and monitor pending count |
| Using the default executor for lots of long-blocking I/O | Can cause contention/starvation | Choose an appropriate base executor |
| Catching Future errors and swallowing them | Loses results/failure visibility | Log cause, propagate/handle per contract |
| Just adding a `sleep` in tests to wait for the delay | Prone to flakiness on CI | Use latches/Futures and verification timeouts |
| Submitting a delayed task and immediately shutting down `base` | Task may not have reached submission time yet | Manage lifecycle to cover the delay |
| Treating `ScheduledFuture.cancel` as a business rollback | Cancel does not undo side effects already performed | Use idempotency and explicit cleanup |

## 15. Testing Properly Without Depending on Absolute Timing

### 15.1. What Should a Good Test Verify?

For `delayedExecutor`, tests should focus on the contract:

1. **Task is invoked after scheduling:** the Future eventually completes and returns a value.
2. **Base executor is used:** worker name or base instrumentation proves the task ran on the configured base.
3. **Continuation waits for upstream:** downstream does not run before upstream completes.
4. **A delayed Executor is reusable:** multiple tasks have independent Futures.
5. **Non-positive delay:** tasks can still execute without waiting for a positive delay.
6. **Exceptions are surfaced:** errors from the supplier/continuation appear in the Future.
7. **Cancellation semantics:** the Future can be cancelled while an already-running task continues.
8. **Shutdown:** `base` is not closed before required delayed tasks, or there is an explicit drop/cancel policy.
9. **Timeout:** observe distinct outcomes between a task that has not reached its delay and a Future timeout.
10. **No thread leaks:** `base` shuts down and awaits termination within a deadline.

### 15.2. Latches Prove Ordering, Elapsed Time Measures Latency

`CountDownLatch` helps order **events** such as task started, task waiting, upstream completed, and task allowed to finish. It cannot make the OS guarantee microsecond-exact scheduling.

When a test genuinely wants to check "delay is at least roughly N", you can measure `System.nanoTime()` and choose a tolerance suitable for CI, but do not enforce a specific timing stdout value across all machines. Nor should you make tests wait for hours just to prove `delayedExecutor` delays.

### 15.3. Do Not Confuse CountDownLatch.await() with Thread.sleep()

In `DelayedStartDemo`, main calls `entered.await()` to set up test state; that **is an intentional wait to verify** that the worker has reached a point. It does not mean `delayedExecutor.execute` itself blocks the caller. The difference lies in **which API path causes the wait**.

In production services, callers typically just hold `CompletableFuture<T>` or return it to another layer; where waiting is actually required can be decided with `join`, `get`, timeouts, or composition.

## 16. Production Deployment Checklist

- Do you distinguish between creating the delayed executor, **calling `execute`**, delay expiration, and worker start?
- Does the delay represent a reasonable backoff/deferral rather than replacing a dependency or timeout?
- For long-blocking I/O, have you chosen an appropriate base executor and bounded concurrency?
- If the goal is not to block the caller, does the code avoid calling `join/get` immediately after `supplyAsync`?
- Is it clear that each submission on the same delayed executor has its own delay?
- For continuations, is it clear that the delay only starts when the preceding stage becomes ready to trigger the continuation?
- Are you aware that a 0/negative delay does not guarantee inline execution on the caller?
- Have you bounded pending tasks, data retained by closures, and overall request deadlines?
- If a task fails, is the `CompletableFuture` observed properly via callbacks/`get`/`join`?
- Do you classify transient vs. permanent failures when using delay for retries?
- Do retries have an attempt limit, jitter, idempotency, and a deadline?
- For cancellation, do you understand `CompletableFuture.cancel(true)` does not guarantee interrupting the worker?
- Is there a protocol to verify side effects/cleanup if a task has already started?
- Do you avoid shutting down `base` before delayed tasks need to be submitted?
- If you need periodic schedules or a timer cancellation handle, have you considered `ScheduledExecutorService`?
- If tasks must survive crashes/restarts, is there durable schedule storage?
- Do tests use latches/Futures instead of sleeps guessing the scheduler?
- Have you checked timeouts and rejections on the executor in use?
- Do you measure queue delay, hold time, p95/p99, and pending task count under representative load?
- Does this layer use only standard Java concurrency mechanisms without mixing in a separate framework?

## 17. Self-Check Questions

**1.** Does calling `CompletableFuture.delayedExecutor(500, MILLISECONDS)` immediately schedule any task?

No. It returns an `Executor`. Each delay starts when `execute(runnable)` is called on that executor, for example via `supplyAsync(..., delayed)`.

**2.** Why can `supplyAsync(..., delayed).join()` still block the caller?

Because `join()` waits for the result of an incomplete Future. Non-blocking scheduling does not exempt the caller from waiting when the caller actively calls `join`.

**3.** The delay expires, but the base executor is busy. Is the task guaranteed to run immediately?

No. The task has only become eligible for submission; when a worker actually runs it still depends on the queue and base capacity.

**4.** Does reusing a delayed executor make all tasks share a single clock started when the executor was created?

No. Each `execute` call starts its own delay.

**5.** `thenApplyAsync(fn, delayed)` is created on an incomplete upstream. Does the delay start when the stage is created?

No. The continuation is only submitted after upstream completes normally; the continuation's delay starts from the time of submission.

**6.** Does a delay of 0 guarantee the function runs on the thread calling `execute`?

No. It only omits a positive delay; the base executor and scheduler still determine how it executes.

**7.** Can `delayedExecutor` be used to run cron/periodic tasks?

There is no periodic API on the returned `Executor`. For recurring schedules, use `ScheduledExecutorService` or an appropriate scheduler system.

**8.** Is `orTimeout` the same as `delayedExecutor`?

No. `orTimeout` sets a deadline on the Future's outcome; `delayedExecutor` delays when the runnable is handed to `base`.

**9.** When `future.cancel(true)` returns true on a `CompletableFuture`, does that prove the supplier was interrupted?

No. `CompletableFuture.cancel` does not use `mayInterruptIfRunning` to control execution per contract. A running supplier can still perform side effects.

**10.** Should you shut down the base executor immediately after submitting a task with a 10-second delay if that task must run?

No. By the time the delay expires, `base` may already be rejecting tasks. Lifecycle management must cover both the waiting period and execution time.

**11.** Why does `Thread.sleep(100)` before starting B not guarantee A has finished?

A's execution time varies with load/scheduler/I/O. If B depends on A, use `thenCompose`/`thenRun` to wait for A's completion.

**12.** If you need to precisely cancel an unfired timer and have a tracking handle, which option is clearer?

`ScheduledExecutorService.schedule(...)` returns a `ScheduledFuture` that supports `cancel(...)` and state inspection per contract.

**13.** Does `delayedExecutor` automatically persist tasks across JVM restarts?

No. It is an in-memory mechanism; durable tasks must be persisted and recovered by an appropriate system.

**14.** Should you assert that a task runs after exactly 25 ms based on a single timing stdout?

No. The scheduler and queue can skew timing; measure duration across multiple runs, use reasonable tolerance, and separate scheduling delay from queue wait.

## 18. JDK Documentation and Conclusion

Official documentation to verify version milestones and API contracts:

- [CompletableFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Executor — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [ScheduledExecutorService — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [ScheduledFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

`CompletableFuture.delayedExecutor` has been available since **Java 9**. The Javadoc states clearly: the delay is applied before submitting the runnable to the default/base executor; **each delay starts when `execute` is called** on the returned executor. Therefore, the API is convenient for building delayed steps and asynchronous continuations without forcing the caller to use `Thread.sleep`.

### Quick Reference

~~~text
delayedExecutor(delay, unit, base):
  Returns Executor, does NOT run tasks by itself.
  execute(task) -> starts that task's own delay.
  Delay expires -> submits task to base executor.
  Base executor -> decides worker, queue, and execution time.

runAsync/supplyAsync(..., delayed):
  Schedules without requiring the caller to sleep.
  Returns CompletableFuture to observe the outcome.

thenApplyAsync(..., delayed):
  Upstream completes -> submits continuation -> starts its own delay.

join()/get():
  CAN STILL block the caller thread when the Future is not yet complete.

cancel(true) on CompletableFuture:
  Does NOT guarantee interrupting running user code.

ScheduledExecutorService:
  Suitable when you need ScheduledFuture and periodic schedules.
~~~

**Conclusion:** `delayedExecutor()` solves **delaying submission** without occupying a caller thread just to sleep. However, it does not guarantee real-time deadlines, does not turn blocking I/O into non-blocking I/O, does not protect executor lifecycle on its own, and does not provide the cancellation or persistence of a dedicated scheduler. Choose an appropriate base executor, compose Futures according to true dependencies, enforce deadlines and observe errors, and clearly separate scheduling from work completion.
