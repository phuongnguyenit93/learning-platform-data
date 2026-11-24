# Checking Cancellation Before Start vs. Cancelling While a Task Is Running

In a Spring Framework application handling concurrent work, a task may be **enqueued but not yet running**, or **already started by a worker**. Calling `Future.cancel(...)` at these two moments has very different meanings. Before starting, a successfully cancelled `FutureTask` will not execute the task body; once running, cancelling is only an **attempt to request stopping**, typically via interruption or a cooperative signal. A `Future` reporting `isCancelled() == true` **does not mean** business code stopped, a transaction rolled back, or all side effects were undone.

This lesson belongs to **Timeouts and Cancellation** in **Spring Framework - concurrency**. The focus is distinguishing the **before-start** and **while-running** boundaries, checking state accurately, handling race conditions, verifying with Java 17+, and integrating cleanly with `ThreadPoolTaskExecutor`, `@Async`, and `CompletableFuture`.

## 1. Learning Outcomes

After completing this lesson, you will be able to:

- Describe task states: queued, running, completed, failed, cancellation requested, and cancelled; never collapse them into one `isDone` flag.
- Use `Future.cancel(false)` and `Future.cancel(true)` at the right times, understanding their boolean return values as well as `isCancelled()`, `isDone()`, and `get()`.
- Prove with deterministic tests that an unstarted task will not run its body after a `FutureTask` is successfully cancelled.
- Explain why an already-running task can keep executing even after the Future is cancelled, even when `cancel(true)` was called.
- Use `InterruptedException`, `Thread.currentThread().isInterrupted()`, and cancellation tokens for cooperative cancellation.
- Distinguish cancelling `FutureTask`/`ExecutorService.submit` from cancelling `CompletableFuture`, especially that `CompletableFuture.cancel(true)` does not drive interruption.
- Design cancellation APIs in Spring to avoid reporting “stopped” when only “cancellation requested” has occurred.
- Test and measure queued cancellation, running cancellation, shutdown, timeouts, and side-effect handling.

## 2. Naming the Stages of Work Accurately

An `ExecutorService` can accept a task via `submit`, yet “accepted” does not mean “started”. For a queued executor, the simplified lifecycle is:

~~~text
SUBMITTED
   |
   v
QUEUED / waiting to be picked up by a worker
   |
   +---- cancelled successfully before start
   |           |
   |           v
   |       CANCELLED
   |       body does not run (for cancelled FutureTask)
   |
   v
RUNNING
   |
   +---- finishes normally ------------> SUCCEEDED
   +---- throws exception -------------> FAILED
   +---- receives cancel request -------+
                                        |
                          cooperates to stop?
                            /        \
                          yes          no
                           |           |
                           v           v
                      exits early    keeps running
~~~

This diagram describes **business job state**, not all internal states of `FutureTask`. A Future may already be marked `CANCELLED` while the method body is still finishing cleanup or continuing execution because it ignores cancel signals. That is why you cannot infer “worker exited” from `isDone()`.

### Distinguishing Three Types of Events

| Event | Meaning | Guarantees the body stopped? |
| --- | --- | --- |
| Caller sends cancel request | Caller wants to cancel work | No |
| `Future.cancel(...)` succeeds | Future handle transitions to cancelled per implementation | No if body already ran; may only block starting |
| Worker confirms exiting the processing region | Executing code stopped or finished cleanup | Yes for the controlled code section, if using a reliable completion signal |

In systems with a job store, persist at least **cancel_requested** separately from **cancelled/stopped**. When an HTTP request triggers cancel, responding “cancel request accepted” is more honest than “work stopped” before worker confirmation exists.

## 3. The Future.cancel(boolean) Contract

`java.util.concurrent.Future<V>` defines:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
boolean isCancelled();
boolean isDone();
V get() throws InterruptedException, ExecutionException;
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

Meaning of `cancel(...)` per the API:

- If the task **has not started** and cancellation succeeds, the task must not be executed afterward.
- If the task **has already started**, `mayInterruptIfRunning` determines whether an attempt should be made to interrupt the running thread **if the implementation knows that thread**.
- If the task **has already completed**, was already cancelled, or could not be cancelled, a new call does not alter the finalized outcome; the boolean may be `false`.
- The Javadoc recommends checking `isCancelled()` to determine status after a cancellation race; do not interpret the boolean return alone as confirmation the worker stopped.
- `isDone()` is `true` when the Future completed **in any manner**: success, failure, or cancellation. It does not mean success.

Once a Future is cancelled, calling `get()` normally throws `CancellationException` (unchecked). If the task failed without cancellation, `get()` throws `ExecutionException`. `get(timeout, unit)` can throw `TimeoutException` simply because the waiter expired; timeout **does not automatically call cancel**.

### Common Outcomes Table

| Call timing | `cancel(false)` | `cancel(true)` |
| --- | --- | --- |
| Task still waiting, not started | Can prevent body execution if cancel succeeds | Can also prevent body before running |
| Task running with FutureTask | Can mark Future cancelled **without interrupt**; body keeps running | Can mark cancelled and attempt to interrupt worker |
| Task already finished before call | Does not change outcome; typically returns `false` | Does not change outcome; typically returns `false` |
| Task running yet ignores interruption | Does not request interrupt | Interrupt may be sent, yet body may still continue |
| Concurrent cancellation from multiple callers | Outcome of each call depends on the race | Do not infer from a single boolean return |

`cancel(true)` **is not like** `Thread.stop()`; modern Java has no safe API to arbitrarily force-stop Java code. Interruption is a cooperative signal, not a guarantee every I/O operation, lock, or native call stops immediately.

## 4. Cancelling Before Start: Preventing the Body from Running

Suppose an executor has one worker. The worker is busy with job A, while job B is submitted and sits in the queue:

~~~text
Worker 1:  [job A waiting on latch]
Queue:     [job B / FutureTask]
Caller:    jobB.cancel(false)
Queue:     [job B marked cancelled, may still be present]
Worker 1:  when dequeuing job B, FutureTask.run() does not execute body B
~~~

The condition **job B has not started yet** is crucial. If job B already left the queue and started between your observation and your `cancel` call, that is a **race** and you are cancelling a running task, no longer the before-start case.

With `ExecutorService.submit(...)` backed by `ThreadPoolExecutor`, tasks are normally wrapped in a `RunnableFuture` such as `FutureTask`. `FutureTask.run()` checks its state; when the Future is already cancelled, the task body is not invoked. Thus, cancelling before start can avoid unnecessary work.

### Does the Job Automatically Disappear from the Queue?

**Not necessarily.** `ThreadPoolExecutor` typically stores a wrapper in its queue. Once cancelled, that wrapper may **physically remain in the queue** until a worker dequeues it or an explicit purge runs. This has two consequences:

1. `Future.isCancelled() == true` and `getQueue().size() > 0` can both be true at the same time.
2. The number of queued items does not equal the number of jobs still needing to run.

`ThreadPoolExecutor.purge()` attempts to remove cancelled Future tasks from the queue; this is a memory/queue reclamation measure with queue-traversal cost and should not be called constantly as a primary cancellation mechanism. `remove(Runnable)` may fail to remove the wrapper if you hold only the original task rather than the actual queued `Runnable`.

**Do not confuse APIs:** `setRemoveOnCancelPolicy(true)` is a setting on `ScheduledThreadPoolExecutor`, not a setter on standard `ThreadPoolExecutor` or a universal feature of every Spring `TaskExecutor`. Verify the concrete executor type before recommending automatic queue-removal configuration.

### Why Check Right Before Starting?

If the application stores cancellation state in a token or job store, the worker should check **right before the first side-effecting operation**:

~~~java
if (token.isCancellationRequested()) {
    return; // skip useful work that has not started
}
performFirstSideEffect(jobId);
~~~

This is an **illustrative pattern** inside a method with application-supplied `token` and `performFirstSideEffect`. This check avoids work whose cancellation already existed before the worker started, yet **does not create atomicity** between “checking” and “writing the side effect”. A cancel can arrive right between those two lines. If the contract mandates “successful cancel means zero writes”, use transactional state, locking, or an admission/state transition synchronized with the side-effect boundary.

## 5. Cancelling While Running: Interruption Is Only a Suggestion

A task may already be running on a worker:

~~~text
Caller               Worker
  |                     |
  |                task running
  |----cancel(true)----->|
  |  Future cancelled    | receives interrupt (if supported)
  |                      | checks/reacts
  |                      +-- stops early and cleans up
  |                      or
  |                      +-- ignores, keeps running
~~~

With a typical `FutureTask`:

- `cancel(false)` can mark the Future cancelled **without interrupting**. An already-started body can still execute to completion, including producing side effects.
- `cancel(true)` attempts to interrupt the thread running the task. If blocked in `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, or other interruptible APIs, they typically throw `InterruptedException`.
- If running a CPU computation loop that never checks interrupts or tokens, the task can ignore the request and run to completion.
- If running I/O that does not react to interrupts as expected, you need the library's own timeout/cancellation API—for example, HTTP client, database driver, or RPC protocol APIs.
- `cancel(true)` can return `true` **before the worker actually exits**. Never use this boolean to confirm all resources were released.

### InterruptedException and the Interrupt Flag

When an interruptible waiting API throws `InterruptedException`, the interrupt status is normally cleared as the exception is thrown. If the method cannot propagate the exception to its caller due to signature or framework constraints, the standard pattern is to **restore the interrupt** and exit cleanly:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cancel further work, clean up resources, and return/throw appropriately.
    return;
}
~~~

This is **illustrative code**, with an application-defined `blockingOperation()`. Calling `Thread.currentThread().interrupt()` alone does not terminate the method. Catching the exception and continuing the loop as if nothing happened prevents the task from stopping and misleads callers into thinking cancellation worked.

### Checking Without Clearing the Flag

~~~java
if (Thread.currentThread().isInterrupted()) {
    // Cooperatively stop or transition to cleanup logic.
}
~~~

`isInterrupted()` reads the status **without clearing** the flag. In contrast, static `Thread.interrupted()` reads **and clears** the current thread's interrupt status; calling it carelessly inside loops or libraries can wipe out the signal so outer layers miss it. If you intentionally use `Thread.interrupted()` for one-shot handling, understand the effect of clearing the flag.

## 6. Standalone Java 17+ Demo: All Three Cancellation Scenarios

This complete program illustrates:

1. Cancelling a **queued** task before its body starts.
2. Cancelling a **running** task with `cancel(true)` and verifying it observes interruption.
3. Cancelling a **running** task with `cancel(false)`: the Future is cancelled, yet the body still completes a simulated side effect.
4. Cancelling a **`CompletableFuture`**: the handle completes exceptionally, without implying anything about interruption.

All execution paths use `CountDownLatch` and anti-hang timeouts, **without relying on `Thread.sleep()`**.

File **CancellationPhasesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class CancellationPhasesDemo {

    private static void cancelBeforeStart() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger queuedBodyRuns = new AtomicInteger();

        try {
            Future<?> blocker = executor.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Blocker did not start");
            }

            Future<?> queued = executor.submit(() -> {
                queuedBodyRuns.incrementAndGet();
            });

            boolean cancelled = queued.cancel(false);
            release.countDown();

            blocker.get(5, TimeUnit.SECONDS);
            executor.submit(() -> {}).get(5, TimeUnit.SECONDS);

            System.out.println("queuedCancelled=" + cancelled);
            System.out.println("queuedBodyRuns=" + queuedBodyRuns.get());
            System.out.println("queuedIsDone=" + queued.isDone());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelRunningWithInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interruptSeen = new AtomicBoolean();

        try {
            Future<?> running = executor.submit(() -> {
                entered.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException ex) {
                    interruptSeen.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    exited.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            boolean cancelled = running.cancel(true);
            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }

            System.out.println("runningCancelTrue=" + cancelled);
            System.out.println("interruptSeen=" + interruptSeen.get());

            try {
                running.get();
            } catch (CancellationException ex) {
                System.out.println("runningGet=CancellationException");
            }
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelRunningWithoutInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean bodyContinued = new AtomicBoolean();

        try {
            Future<?> running = executor.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                    bodyContinued.set(true);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    exited.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            boolean cancelled = running.cancel(false);
            release.countDown();

            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }

            System.out.println("runningCancelFalse=" + cancelled);
            System.out.println("bodyContinued=" + bodyContinued.get());
            System.out.println("futureCancelled=" + running.isCancelled());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelCompletableFuture() {
        CompletableFuture<String> result = new CompletableFuture<>();
        boolean cancelled = result.cancel(true);
        System.out.println("cfCancel=" + cancelled);
        System.out.println("cfIsCancelled=" + result.isCancelled());

        try {
            result.join();
        } catch (CancellationException ex) {
            System.out.println("cfJoin=CancellationException");
        }
    }

    public static void main(String[] args) throws Exception {
        cancelBeforeStart();
        cancelRunningWithInterrupt();
        cancelRunningWithoutInterrupt();
        cancelCompletableFuture();
    }
}
~~~

Compile and run:

~~~bash
javac CancellationPhasesDemo.java
java CancellationPhasesDemo
~~~

Stdout of a successful run:

~~~text
queuedCancelled=true
queuedBodyRuns=0
queuedIsDone=true
runningCancelTrue=true
interruptSeen=true
runningGet=CancellationException
runningCancelFalse=true
bodyContinued=true
futureCancelled=true
cfCancel=true
cfIsCancelled=true
cfJoin=CancellationException
~~~

### Why Is This Test Deterministic?

**Before-start scenario:** `entered.await()` ensures the first worker entered the blocker task and is waiting on `release`. Since the executor has only one worker, the second task cannot run yet. `queued.cancel(false)` cancels this wrapper; then `blocker` is released. Submitting a final marker and calling `get()` on the marker guarantees the worker passed the cancelled task's slot in the FIFO queue. `queuedBodyRuns=0` proves the second body did not run. `queuedIsDone=true` is the cancelled Future state, not proof the body succeeded.

**Running + interrupt scenario:** the worker records `entered` before entering an unreleased `await()`. `cancel(true)` attempts to interrupt the waiting thread; the task catches `InterruptedException`, sets `interruptSeen`, restores the flag, and exits. `exited.await()` ensures `main` only prints after the body completed cleanup. `running.get()` throws `CancellationException` because **the Future outcome was cancelled**, not because the body threw a business error.

**Running without interrupt scenario:** `cancel(false)` marks the Future cancelled without requesting interruption. `main` releases `release`, and the task still sets `bodyContinued=true` and exits. Thus **`futureCancelled=true` and `bodyContinued=true` are both true**. Remember this when designing side effects.

**CompletableFuture scenario:** `cancel(true)` completes the handle with cancellation; the program creates no computation task for that handle. The example confirms handle semantics only—it is **not a worker-interruption experiment**.

In environments with abnormal resource constraints, the timeouts prevent the test from hanging forever, causing the program to fail loudly instead of printing false “success” stdout.

## 7. Races at the QUEUED -> RUNNING Boundary

No “read `isDone` and be sure the task hasn't started” check is atomic with the scheduler. Events can interleave:

~~~text
Caller                              Worker
  |                                   |
  | reads waiting state                 |
  |                                   | dequeues task
  |                                   | starts body
  |---- cancel(false) ---------------->|
  | Future may turn cancelled          | body keeps running
~~~

This is a **check-then-act race**. Even if `getQueue().contains(task)` just returned true, by the time `cancel` runs the worker may already have picked up the task. Queue size, active count, and “waiting” metrics are only snapshots, not transactional with `cancel`.

If business requirements are only *best effort*, this race is usually accepted and tasks check cancellation signals. If there is a strict requirement that a job cancelled before point X **must not start side effects**, you need a synchronized protocol:

1. A durably persisted **job state** with ID and version.
2. The worker transitions `QUEUED -> RUNNING` via an atomic/conditional operation, e.g., updating the record conditioned on status still being `QUEUED`.
3. The canceller transitions `QUEUED -> CANCELLED` also via a conditional operation.
4. Only one state transition can win; if the worker wins, cancel becomes **`CANCEL_REQUESTED`** and requires cooperative stopping.
5. The worker checks status before each sensitive side-effect region and confirms `STOPPED` upon exiting processing.

Depending on the system, you can use locks, CAS, database optimistic concurrency, message broker semantics, or leases; pick what matches your real storage mechanism. `AtomicBoolean` only synchronizes within **one JVM**, not across other replicas.

## 8. Where FutureTask Differs Fundamentally from CompletableFuture

Both `FutureTask` and `CompletableFuture` implement `Future`, yet their control mechanisms differ:

| Property | `FutureTask` (typically used by `submit`) | `CompletableFuture` |
| --- | --- | --- |
| Directly bound to executing a `Callable/Runnable`? | Yes, directly implements `RunnableFuture` | Not necessarily; primarily a completion handle |
| `cancel(false)` before running | Prevents `FutureTask` body from running when cancel succeeds | Marks handle cancelled; does not guarantee controlling underlying work |
| `cancel(true)` while running | Attempts to interrupt the runner thread if known | `mayInterruptIfRunning` parameter **has no effect** in standard implementation |
| `isCancelled` outcome | Indicates the Future was cancelled | Indicates the `CompletableFuture` completed via cancellation |
| Impact on dependent stages | No standard composition | Dependent stages may complete exceptionally |
| Guarantees stopping task / rolling back side effects | No | No |

Per Java 17's `CompletableFuture` Javadoc, `cancel(boolean)` has the same effect as `completeExceptionally(new CancellationException())`, and `mayInterruptIfRunning` **is not used to control execution interruption**. Thus:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();
future.cancel(true); // cancels completion handle, does not auto-interrupt worker
~~~

This is an **illustrative Java snippet**. If a worker is computing something that will call `future.complete(value)` later, that worker can keep running; its `complete(value)` call will fail to alter the future because it was already terminated by cancellation.

### supplyAsync and cancel Do Not Form a Reliable Interrupt Path

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> performWork(), pool);
future.cancel(true);
~~~

This is **illustrative code**; `performWork` is application-supplied and the pool must be shut down in real code. `CompletableFuture.cancel(true)` **does not promise interrupting the running lambda**, even when you pass an `ExecutorService`. If you must actually stop work, pass a cancellation token to the body or hold a `FutureTask` with a verified interruption path.

**Do not confuse:** some frameworks may wrap `CompletableFuture` differently; cancellation/propagation semantics can be implementation-dependent. With Spring `@Async`, verify the executor and returned Future type rather than inferring from a `CompletableFuture<T>` signature that `cancel(true)` interrupts the worker.

## 9. Cooperative Cancellation in Loops and Blocking Sections

A long task should be split into **small units of work** and check signals before each unit:

~~~java
for (int chunk = 0; chunk < chunks.size(); chunk++) {
    if (token.isCancellationRequested()
            || Thread.currentThread().isInterrupted()) {
        return;
    }

    processChunk(chunks.get(chunk));
}
~~~

This is **illustrative code**; `token`, `chunks`, and `processChunk` are supplied by the application. If `processChunk` blocks indefinitely, checking at the top of the loop cannot help until the call returns. Configure timeouts/cancel APIs on the blocking I/O itself.

### Cancellation Token

A simple single-JVM token:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean();

    public boolean request() {
        return requested.compareAndSet(false, true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }
}
~~~

This code is **standalone valid Java** if saved as `CancellationToken.java` and compiled with JDK 17+. `AtomicBoolean` provides visibility and atomicity for the cancel state. Still, `request()==true` only means **the first caller transitioned the token to requested**; it does not tell you whether the worker observed the token or stopped.

If tasks span multiple JVMs, an in-RAM token is insufficient. Persist cancel requests in a job store, emit events, or poll workers per contract; durable state matters more than API appearance.

### When the Task Catches InterruptedException

A body can use:

~~~java
try {
    blockingClientCall();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    markCancellationObserved();
    return;
} finally {
    closeLocalResources();
}
~~~

This is an **integration pattern** with application-defined methods. Cleanup in `finally` should be idempotent and avoid long blocking. Do not mark `CANCELLED` in the job store before cleanup completes if the system requires confirmation of actual stopping; at the same time, do not hold large transactions open during cleanup that could drag on arbitrarily.

## 10. Integrating in Spring: Picking the Right Handle for Cancellation

Spring's `ThreadPoolTaskExecutor` is backed by `ThreadPoolExecutor` and also supports `submit(...)`. If you want the ability to call `Future.cancel(...)` with executor-task semantics, a clear approach is **explicitly submitting a `Runnable`/`Callable`** and retaining the `Future`. `TaskExecutor.execute(Runnable)` returns no `Future`, so it gives the caller no cancellation handle from that call.

File **CancellableExecutorConfig.java** in a Spring application:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CancellableExecutorConfig {
    @Bean(name = "cancellableExecutor")
    public ThreadPoolTaskExecutor cancellableExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("cancellable-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

This is **Spring configuration**, requiring `spring-context` and not runnable standalone via `java`. Thread/queue numbers are illustrative only, not production sizing recommendations. The Spring-managed bean is initialized and shut down according to the context lifecycle.

### Dispatcher Holding Both Future and Token

File **CancellableJobDispatcher.java**:

~~~java
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class CancellableJobDispatcher {
    private final ThreadPoolTaskExecutor executor;

    public CancellableJobDispatcher(
            @Qualifier("cancellableExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public JobHandle submit(String jobId) {
        CancellationToken token = new CancellationToken();
        Future<?> future = executor.submit(() -> run(jobId, token));
        return new JobHandle(future, token);
    }

    public boolean requestCancellation(JobHandle handle) {
        boolean firstRequest = handle.token().request();
        handle.future().cancel(true);
        return firstRequest; // does NOT mean the worker stopped
    }

    private void run(String jobId, CancellationToken token) {
        for (int part = 0; part < 10; part++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                return;
            }
            processPart(jobId, part);
        }
    }

    private void processPart(String jobId, int part) {
        System.out.println("Processing " + jobId + " part " + part);
    }

    public record JobHandle(
            Future<?> future, CancellationToken token) { }

    public static final class CancellationToken {
        private final AtomicBoolean requested = new AtomicBoolean();

        public boolean request() {
            return requested.compareAndSet(false, true);
        }

        public boolean isCancellationRequested() {
            return requested.get();
        }
    }
}
~~~

This is a **Spring-managed service**, requiring Spring dependencies and a Spring `ApplicationContext`. `CancellationToken` is nested inside `CancellableJobDispatcher`, so **do not** mix it simultaneously with the standalone `CancellationToken.java` from earlier unless you intentionally want two token types. The example is self-contained for API clarity.

Important points:

- `submit` returns a handle bound to the task given to the Spring executor. You can then attempt cancellation both before and after the task starts.
- `requestCancellation` sets the token first and then calls `future.cancel(true)`. This supports both cooperative checks and attempting to interrupt if the underlying Future supports it.
- The method's return value means **“was this the first cancel request”**, not status `STOPPED`.
- If the thread already entered `processPart` before checking the token, part of the work may still execute after the cancel request. I/O needs its own timeouts and cancel APIs.
- Returning a `Future` handle across HTTP boundaries or serialization is unsuitable; in production store a **job ID** and durable metadata, keeping the Future/token as an internal in-JVM handle only.

### Do Not Confuse Rejection with Cancellation

With `AbortPolicy`, if the executor is saturated or shut down during `submit`, Spring's `ThreadPoolTaskExecutor` can throw `TaskRejectedException`. **This is an unaccepted task**, not a task that ran and was later cancelled. Callers must handle overload: appropriate HTTP responses, durable queues, or retries with backoff and idempotency.

If using `CallerRunsPolicy`, the task may run directly on the calling thread when the pool is saturated; `submit` may then wait until the body finishes before returning a Future. “Cancelling right after submit” would arrive too late. The rejection policy is part of the cancellation contract.

## 11. @Async and Cancellation: Do Not Equate Wrapper with Worker

An `@Async` method may return `Future<T>` or `CompletableFuture<T>`. The Spring proxy creates a handle for the caller; the target method typically computes a value on the worker and returns a temporary `Future` matching the signature:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CancellationException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncReportService {
    @Async("cancellableExecutor")
    public CompletableFuture<String> render(
            String reportId, CancellableJobDispatcher.CancellationToken token) {
        for (int part = 0; part < 10; part++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException("Cancellation requested");
            }
            renderPart(reportId, part);
        }
        return CompletableFuture.completedFuture("done:" + reportId);
    }

    private void renderPart(String reportId, int part) {
        System.out.println("Rendering " + reportId + " part " + part);
    }
}
~~~

This is a **Spring service** requiring the token class from the dispatcher example, the executor bean, and `@EnableAsync` in the application configuration. It is not a standalone Java program. `completedFuture` inside the method is a temporary Future on the target; through the proxy, the caller receives a handle representing async execution.

If the caller only writes:

~~~java
CompletableFuture<String> future = reportService.render(id, token);
future.cancel(true);
~~~

then `CompletableFuture.cancel(true)` by itself **is not a reliable mechanism to interrupt work**. The worker may keep running depending on proxy/wrapper mechanics and inner code. Therefore, to stop business execution, invoke `token.request()` and ensure the method checks the token frequently. Throwing `CancellationException` inside the body can cause the proxy's future to complete exceptionally; **do not assume `future.isCancelled()==true` in every variant just because the body threw that exception type**. Verify the Future contract and how Spring/the Executor construct wrappers.

### Why Is @Async void Hard to Cancel by Call?

With `@Async void`, the caller receives no Future handle and cannot call `cancel` directly on the method's result. If cancellation must be supported, provide a dedicated API by job ID/token, or change the design to return a Future or use durable jobs. `AsyncUncaughtExceptionHandler` handles uncaught exceptions of `void` methods; it does not replace a cancellation state machine.

### Self-Invocation and Cancellation

In default proxy mode, `this.render(...)` inside the same bean bypasses the Spring proxy. The body then runs directly on the caller's thread regardless of the annotation. A cancellation test can reach false conclusions if it fails to route calls through the Spring-managed proxy. Choose the right executor and inspect thread identity, especially when `CallerRunsPolicy` is configured.

## 12. Cancellation and Timeout: Two Separate Conditions

`get(timeout, unit)` only sets a time limit **for the thread waiting for the result**. When `TimeoutException` occurs, the task may still be running.

~~~java
Future<?> future = executor.submit(this::doWork);

try {
    future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    boolean cancelRequested = future.cancel(true);
    recordTimeout(cancelRequested);
}
~~~

This is an **integration fragment**, requiring imports for `Future`, `TimeoutException`, `TimeUnit`, and application-defined methods; real code must also handle `InterruptedException` and `ExecutionException`. Calling `cancel(true)` after a timeout is a **separate business decision**. Sometimes the result arrives too late for the request yet the background task should still finish (e.g., writing an audit record), so you may choose not to cancel.

With `CompletableFuture`:

- `orTimeout(duration, unit)` can complete **the `CompletableFuture` itself** exceptionally with `TimeoutException` if not yet finished.
- `completeOnTimeout(fallback, duration, unit)` can complete that Future with a fallback value.
- Neither **automatically interrupts running work**; background work can continue mutating databases or external services.
- When retrying after a timeout, idempotency is mandatory because the first execution may not have stopped.

Distinguish three deadlines: the HTTP request deadline, the worker's I/O call timeout, and the overall job deadline. Connect them intentionally; merely calling `future.get(2, ...)` does not automatically propagate timeouts to every layer.

## 13. Interruption in Blocking APIs, I/O, and Critical Sections

### Interruptible Blocking

APIs like `CountDownLatch.await`, `BlockingQueue.take`, `Thread.sleep`, and many interruptible lock waits support `InterruptedException`. When interrupted, typically:

1. Record the stop request as needed.
2. Release local resources in `finally`.
3. Restore the interrupt flag if `InterruptedException` cannot be propagated upward.
4. Exit work as soon as consistent with data integrity.

### CPU-Bound

For long computations:

~~~java
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()
            || token.isCancellationRequested()) {
        break;
    }
    computeNextChunk();
}
~~~

Functions and variables in the snippet are application components. If `computeNextChunk()` is a 30-second computation loop that never checks the token, cancellation response latency can be 30 seconds or more. Splitting workloads around checkpoints controls cancellation latency.

### I/O and External Resources

Not every I/O operation stops when a Java thread is interrupted. An HTTP client may have its own request-cancel API; JDBC drivers offer `Statement.cancel()` with driver/database-specific behavior; sockets use timeouts or require closing channels. Never treat `cancel(true)` as proof a DB query rolled back. Attach appropriate timeouts to HTTP/JDBC, check transaction boundaries, and use compensation/idempotency for committed side effects.

### Critical Sections

If a task holds a lock or is mid-commit, cancelling does not mean stopping at an arbitrary instruction. Place checkpoints at **safe boundaries** between steps. If a unit of work already wrote partial data, use transactions, checkpoints, or compensation so post-cancellation state is not left half-baked.

## 14. Shutdown and Cancellation Are Two Different Concepts

`ExecutorService.shutdown()` stops accepting new tasks while allowing already-submitted tasks to continue under normal shutdown rules. It **does not mean cancelling all running tasks**.

`shutdownNow()` attempts to stop executing tasks via interruption, prevents queued tasks from running, and returns a list of unstarted `Runnable`s. This is also **best effort**: if a task ignores interrupts, it may not stop. The returned list contains the wrapper `Runnable`s, not necessarily the original business objects.

A safe shutdown structure when managing an executor yourself:

~~~java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        executor.awaitTermination(5, TimeUnit.SECONDS);
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is an **illustrative Java snippet** inside a method with an `ExecutorService executor`, not a standalone class. When Spring manages a shared `ThreadPoolTaskExecutor` bean, let `ApplicationContext` manage its lifecycle per configuration; do not call shutdown yourself when one request ends.

For jobs that must not be lost, drain or durably persist state before shutdown, because pending work in an in-RAM queue can vanish when the JVM exits.

## 15. Designing a Reliable Job Cancellation API

If clients send `POST /jobs/{id}/cancel`, express cancellation outcomes honestly. A usable state diagram:

~~~text
QUEUED ----- claim/start -----> RUNNING ------> SUCCEEDED
   |                                |               ^
   | cancel before claim            | cancel request |
   v                                v               |
CANCELLED_BEFORE_START       CANCEL_REQUESTED       |
                                   |               |
                              worker confirms      |
                                   |               |
                            STOPPED / CANCELLED     |
                                                   |
                                may complete before
                                seeing cancel request
~~~

States must be designed to avoid writing both “CANCELLED and SUCCEEDED” as final results in the job store. When cancellation arrives late, the API can return `ALREADY_COMPLETED` or `CANCELLATION_NOT_GUARANTEED` instead of trying to overwrite success with cancelled.

### Contract Suggestions

| API / state | Meaning |
| --- | --- |
| `202 Accepted` on cancel request | System recorded the cancel request; does not claim worker stopped yet |
| `QUEUED -> CANCELLED` via CAS/transaction | Cancel won the race against worker claim; no side effects started per protocol |
| `RUNNING -> CANCEL_REQUESTED` | Worker must check and cooperate to stop |
| `RUNNING -> SUCCEEDED` | Worker finished before or during the race with the request |
| `CANCEL_REQUESTED -> STOPPED` | Worker confirmed stopping and cleanup |
| `CANCEL_REQUESTED -> FAILED` | Worker stopped due to error; classify root cause |
| `ALREADY_COMPLETED` | Cannot cancel work whose result is already finalized |

`202` is only an API example for asynchronous cancellation. Actual HTTP status choices depend on product contracts, authentication, and durable persistence. Never expose other users' job IDs or let arbitrary callers cancel jobs they do not own.

### Atomicity and Idempotency

A cancellation endpoint normally needs to be idempotent: calling it repeatedly must not produce contradictory states. Use versioning/CAS for state transitions and attach request IDs / correlation IDs for observability. If a task has non-rollbackable side effects (email already sent, transfer executed), cancellation can only block **subsequent steps**, not retract completed steps; use compensation or a “non-cancellable after milestone X” contract.

## 16. Observing Cancellation Properly

Do not count only `Future.isCancelled()`. For substantial workloads, observe:

| Metric | Explanation |
| --- | --- |
| `cancel_requests_total` | Number of user/system requests to cancel |
| `cancel_before_start_total` | Jobs where cancel won before worker claim |
| `cancel_running_requests_total` | Cancel requests while jobs were already running |
| `cancel_acknowledged_total` | Workers that observed the request and entered cleanup |
| `cancel_stopped_total` | Jobs genuinely stopped after cleanup |
| `cancel_too_late_total` | Jobs that finished before cancel won |
| `cancellation_latency` | Time from request to stop confirmation |
| `interrupted_tasks_total` | Bodies that actually observed interrupt, not calls to `cancel(true)` |
| `queued_cancelled_task_count` | Cancelled tasks still physically present in queue, if measurable |
| `partial_side_effects` | Jobs cancelled after writing partial side effects; requires reconciliation |

Metrics must avoid double-counting: a single request may retry cancel, multiple callers may send it, or a Future may be cancelled on timeout. Use job IDs and request IDs, and separate **requested**, **handle cancelled**, and **worker stopped**. Logging thread names helps investigation, but does not replace durable state.

### Misleading Measurements

- `getQueue().size()` is an instantaneous snapshot; it may include cancelled wrappers not yet purged.
- `getActiveCount()` is an estimate; it does not tell you how many workers are cooperating on cancellation.
- `Future.isDone()` is true even when cancelled; it is not a job success metric.
- `cancel(true)` returning true is not `interrupted_tasks_total`.
- `CompletableFuture.isCancelled()` can be true while computation behind the handle keeps running.

## 17. Common Errors

1. **Reading `isDone()==true` and concluding the job succeeded.** The Future may have failed or been cancelled.
2. **Reading `isCancelled()==true` and concluding the worker stopped.** The body may still be cleaning up or running.
3. **Using `cancel(false)` on a running task expecting the body to stop.** It does not request interruption.
4. **Treating `cancel(true)` as a forced thread-kill command.** Interruption requires cooperation.
5. **Swallowing `InterruptedException` and unconditionally continuing.** Loses the stop signal.
6. **Forgetting to restore interrupt when unable to propagate the exception.** Upper layers/libraries will not know interruption occurred.
7. **Calling `Thread.interrupted()` just to “check” without knowing it clears the flag.** Subsequent layers can miss the signal.
8. **Checking the token only once before a long processing loop.** Cancellation arriving after the check will go unseen.
9. **Trusting `getQueue().contains(task)` as proof the task has not started.** A worker may dequeue it right afterward.
10. **Confusing removing a wrapper from the queue with rolling back side effects.** Two independent processes.
11. **Assuming cancel always deletes queue entries immediately.** `ThreadPoolExecutor` may retain cancelled `FutureTask`s until dequeue or purge.
12. **Calling `setRemoveOnCancelPolicy` on a plain `ThreadPoolExecutor`.** That setter belongs to `ScheduledThreadPoolExecutor`.
13. **Calling `CompletableFuture.cancel(true)` and assuming the worker was interrupted.** Standard Java API does not use that parameter to control interruption.
14. **Using `orTimeout` and thinking it interrupts underlying CPU/I/O.** It changes completion, without guaranteeing computation stops.
15. **Using `@Async void` and then looking for a Future to cancel.** You need a job/token interface or a return type with a handle.
16. **Self-invocation bypassing `@Async` proxy.** The body runs on the caller, skewing timing tests.
17. **Ignoring executor rejections.** A rejected task is not a task that was accepted and then cancelled.
18. **Using `CallerRunsPolicy` and assuming submit always returns immediately.** The body can run inline under saturation.
19. **Cancelling a task after it committed external side effects and claiming rollback.** Compensation is needed, not just a Future.
20. **Missing cleanup in `finally`.** Resources/sockets/locks can stay held when interruption occurs.
21. **Using only `AtomicBoolean` in a multi-replica service.** Cancel state is not synchronized across JVMs.
22. **Counting every cancelled Future as a successfully cancelled job.** Can misreport actual execution.
23. **Testing with `Thread.sleep()` to guess that a task started.** Use latches/barriers and timeouts.
24. **Leaving shutdown unbounded.** Uncooperative workers can hold processes or resources indefinitely.
25. **Immediately retrying on cancel for non-idempotent side effects.** Old work may still be running.

## 18. Reliable Testing Process

### Testing Before Start

1. Use a single-thread executor; hold the first worker with a latch.
2. Wait on a latch confirming the worker started and is held.
3. Submit the second task; at this moment it definitely has no free worker.
4. Call `cancel(false)` on the second Future; assert cancelled state.
5. Release the first worker, submit a barrier marker, and wait for the marker to finish.
6. Assert the second task's body **never ran**. Do not rely on `Thread.sleep()`.

### Testing While Running

1. Task signals `entered` once inside its body.
2. Task waits on an unreleased latch using an interruptible API.
3. `main` waits for `entered`, then calls `cancel(true)`.
4. Task catches `InterruptedException`, records it, and exits in `finally`.
5. `main` waits for `exited`, asserts interruption was genuinely observed by the body, and asserts Future is cancelled.

### Testing Running `cancel(false)`

1. Put the task into running state waiting on a latch.
2. Call `cancel(false)` and verify the Future is cancelled.
3. Manually release the latch and verify the body **can still execute past the wait point**.
4. This helps teams understand that “future cancelled” is not identical to “worker stopped”.

### Spring Integration Testing

- Obtain the Spring-managed `ThreadPoolTaskExecutor` and remember `ApplicationContext` lifecycle.
- Test the `submit` path and `@Async` path separately if the system uses both; wrapper semantics may differ.
- Test using real handles/IDs and proper thread contexts, not just calling `new Service()` directly.
- Set up bounded queues and latches to reproduce rejections and queued cancellation.
- Inspect timeout/cancellation states in the job table; assert side effects genuinely do not occur when cancel wins the race per contract.
- In every test with blocked workers, release latches in `finally`, bound wait durations, and close executors to prevent CI hangs.
- Test combined shutdown / rolling deployment to verify whether pending tasks are drained, dropped, or durably persisted.

## 19. When Do You Need Mechanisms Stronger Than Future.cancel?

| Context | Mechanism to use |
| --- | --- |
| Short task, internal to one JVM, discardable if not yet started | Future cancellation may be enough |
| Long task, stoppable between chunks | Future interrupt + cancellation token + checkpoints |
| Task doing blocking HTTP/DB | Library timeout/cancel APIs + token; not interrupt alone |
| Running task that can cause critical side effects | Transactions / state machine / idempotency and safe checkpoints |
| Multiple replicas needing cross-node cancellation | Durable job store and observable cancel state |
| Must strictly prevent a task from starting after cancel | Atomic state transition between worker claim and cancel |
| Client cancels after job already completed | Return too-late / already-completed status |
| Multiple workers sharing one job | Cancellation protocol per child task and completion aggregation |
| Only need UI to stop waiting for response | Can time out the request without cancelling the job if business contract permits |
| Must guarantee jobs are not lost on restart | Durable queue, retries, and outbox/idempotency, independent of Future |

Prioritize according to what *cancel* means: “stop returning a result to me”, “do not start the job”, “stop early if possible”, or “undo all business effects”. These four requirements differ dramatically and cannot all be solved by one `future.cancel(true)` call.

## 20. Self-Check Questions

1. Why might a newly `submit`ted task not have started yet even though a `Future` already exists?
2. When the worker is busy and task B is still in the queue, does successfully cancelling B's `FutureTask` allow B's body to run afterward?
3. Why, after `cancel(false)` on a running task, can `future.isCancelled()==true` while the body still produces side effects?
4. Does `cancel(true)` guarantee the worker stops immediately? When is interruption genuinely useful?
5. When catching `InterruptedException` without rethrowing it, why should you usually call `Thread.currentThread().interrupt()`?
6. How does `Thread.interrupted()` differ from `Thread.currentThread().isInterrupted()`?
7. Why cannot reading `getQueue().size()` or `contains(task)` serve as a barrier guaranteeing the task has not started?
8. Does `CompletableFuture.cancel(true)` automatically interrupt a lambda running in `supplyAsync`?
9. Does `isDone()` distinguish success, failure, and cancellation?
10. Does a `get(timeout)` timeout automatically cancel or stop the task?
11. With Spring `@Async CompletableFuture`, what must you design if users request genuinely stopping the work?
12. In a multi-replica job store, how do you distinguish `QUEUED -> CANCELLED` from `RUNNING -> CANCEL_REQUESTED`?
13. If a money transfer already committed, can `Future.cancel(true)` roll it back? What else must be designed?
14. How does a cancellation endpoint returning “request accepted” differ from “worker stopped”?
15. In tests, how do you prove a body did not run without using random sleeps?
16. During shutdown, does `shutdownNow()` guarantee all running I/O stops instantaneously?

## 21. Official References

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — Thread interruption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)

**Takeaway:** cancelling a task **before start** can prevent body execution if the `FutureTask` is cancelled successfully. Cancelling a task **while running** is primarily a cooperative stop request: `cancel(false)` sends no interrupt, `cancel(true)` only attempts an interrupt, and `CompletableFuture.cancel(true)` does not drive interrupting the computation. For business guarantees, verify **the worker actually stopped** and manage **job state, side effects, and deadlines** independently of Future state.