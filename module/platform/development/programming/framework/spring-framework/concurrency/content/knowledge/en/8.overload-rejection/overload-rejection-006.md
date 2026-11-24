# Never Let Futures Wait Forever Because an Eviction Policy Fails to Complete Tasks

## 1. The Problem: Executor Drops Work While the Future Keeps Waiting

Suppose a Spring API receives a report-generation request, submits the task to a `ThreadPoolTaskExecutor`, and returns a `Future`/`CompletableFuture` for other components to await the result. When the system is overloaded, a configuration such as `DiscardPolicy` can **silently drop the task**. The caller still receives a `Future` object from `submit`, yet the task never ran, nothing triggers completion logic, and no exception or cancellation is recorded on the Future.

When that happens:

- `future.isDone() == false` can persist forever unless some other actor completes or cancels the Future.
- `future.get()` **without a timeout** can block indefinitely.
- `future.get(2, TimeUnit.SECONDS)` lets the caller stop waiting after the bounded interval via `TimeoutException`, yet **does not by itself turn the Future into DONE/CANCELLED**.
- `CompletableFuture.join()` and dependent stages can also wait forever; if the task responsible for completing the Future was dropped, `thenApply`/`allOf` calls may never finish.

This bug is often hard to spot in development because queues rarely fill up. In production, a single slow worker, a bounded queue, and concurrent arrivals are enough to trigger the rejection policy.

**Design principle:** if an external caller is waiting on a result, **every terminal branch** must be observable: success, business failure, submission rejection, cancellation, timeout, and application shutdown. Avoid silent task-dropping policies when the output is a `Future` that others will await.

## 2. Distinguishing Task, Future, and "Submitted"

### 2.1. `execute` Differs from `submit`

With Java's `ThreadPoolExecutor`:

- `execute(Runnable)` asks the executor to run a `Runnable` and returns `void`.
- `submit(Callable<T>)`/`submit(Runnable)` creates a `RunnableFuture` (typically `FutureTask`), dispatches that wrapper through `execute`, and returns a `Future` to the caller.
- When the wrapper actually runs, it marks success or failure. When `Future.cancel(...)` is called, it transitions to cancelled. If the wrapper **never runs and nobody cancels it**, the Future normally remains in its initial state.
- `submit` returning normally **does not guarantee** the executor actually accepted the work: a `RejectedExecutionHandler` configured to stay silent can let `execute` return normally even though the task was just dropped.

Therefore, "having a `Future`" does not mean "the job will complete." When a task is created via `CompletableFuture.supplyAsync(supplier, executor)`, a wrapper must also run to complete the stage; if the executor silently discards the wrapper, the CompletableFuture can stay `isDone() == false`.

### 2.2. States to Distinguish

| Situation | `isDone()` | `get()` | Meaning |
| --- | --- | --- | --- |
| Not started yet, but **validly sitting in the queue** | `false` | Blocks | May execute later |
| Executing | `false` | Blocks | Progress depends on the task |
| Succeeded | `true` | Returns result | Terminal |
| Task threw an exception via `FutureTask` | `true` | `ExecutionException` | Error terminal |
| Successfully cancelled | `true` and `isCancelled() == true` | `CancellationException` | Cancelled terminal |
| Silently dropped by `DiscardPolicy` | Usually `false` forever | Waits forever without timeout | **Completion signal lost** |
| Evicted from queue by `DiscardOldestPolicy` without cancel | Usually `false` forever | Waits forever without timeout | **Old Future orphaned** |

An incomplete Future does not by itself tell you whether it is "queued," "running," or "lost." Combine pool metrics, rejection logs, job status, and submission timestamps.

### 2.3. Why Does an Executor Reject?

`ThreadPoolExecutor` invokes `RejectedExecutionHandler` when it cannot accept more work (typically because worker limits and queue capacity are reached) or when the executor has shut down. With Spring's `ThreadPoolTaskExecutor`, `corePoolSize`, `maxPoolSize`, `queueCapacity`, and the handler determine runtime behavior.

For example, a pool with `core=1`, `max=1`, and a queue holding at most one task: the first task is running; the second task queues; the third task is rejected. If the queue is unbounded, new tasks may queue for a very long time before any rejection occurs; never take "never rejected" as proof that the system has sufficient capacity.

## 3. Four Rejection Policies of ThreadPoolExecutor

| JDK Policy | When pool is saturated | Risk to Future |
| --- | --- | --- |
| `AbortPolicy` (`ThreadPoolExecutor` default) | Throws `RejectedExecutionException` immediately at submission | Caller is notified of rejection and can return an error or fail the Future exceptionally |
| `CallerRunsPolicy` | Runs task on the **submitting thread** if executor has not shut down | No tasks lost to saturation, though it can block HTTP callers; **silently drops when shut down** |
| `DiscardPolicy` | Drops the rejected task, **throws no error** | The `Future` of the just-submitted task may never complete |
| `DiscardOldestPolicy` | Drops the task at the **head of the queue** and retries submitting the new task if not shut down | The Future **of the old task** may wait forever; when shut down, the new task is also dropped |

`DiscardOldestPolicy` is not "reprioritization" in a safe sense. It typically removes the `Runnable` at the head of the queue via `poll()` **without cancelling the corresponding Future**. If the queue held a `FutureTask`, the Future of whoever submitted the older task may never reach a terminal state. Even when the new task is accepted, the system has broken a result promise made to another caller.

**Watch out for shutdown:** `CallerRunsPolicy` and `DiscardOldestPolicy` in the JDK also have branches that drop tasks when the executor has shut down. Thus `CallerRunsPolicy` is not a guarantee that *every submitted task will always complete*. When guaranteed results are needed, prefer **transparent rejection** and explicit terminal state recording.

## 4. Java 17: Reproducing the Bug Deterministically

The standalone example below uses `CountDownLatch` to hold the sole worker busy, places a second task into a single-slot queue, and then submits a third task. It does not rely on `Thread.sleep` "hoping" the pool saturates. Two policies are tested in turn:

1. `DiscardPolicy` drops the **new** task; the new task's Future never completes.
2. `DiscardOldestPolicy` evicts the **older waiting** task; the old Future never completes while the new task runs.

Save as **`DroppedFutureDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class DroppedFutureDemo {
    public static void main(String[] args) throws Exception {
        demonstrate("DiscardPolicy",
                new ThreadPoolExecutor.DiscardPolicy(), false);
        demonstrate("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy(), true);
    }

    private static void demonstrate(
            String name, RejectedExecutionHandler handler,
            boolean dropsQueuedTask) throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                handler);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return "running";
            });

            // Ensure the worker took the first task and is waiting on release.
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Queue capacity = 1: queued sits in the queue.
            Future<String> queued = pool.submit(() -> "queued");

            // Worker busy and queue full: rejection policy runs.
            Future<String> newest = pool.submit(() -> "newest");

            release.countDown();

            System.out.println(name + ": running="
                    + running.get(5, TimeUnit.SECONDS));

            Future<String> kept = dropsQueuedTask ? newest : queued;
            Future<String> dropped = dropsQueuedTask ? queued : newest;

            System.out.println(name + ": kept="
                    + kept.get(5, TimeUnit.SECONDS));

            // Do not use unbounded dropped.get(). This is the caller's wait limit.
            try {
                dropped.get(100, TimeUnit.MILLISECONDS);
                System.out.println(name + ": UNEXPECTED COMPLETION");
            } catch (TimeoutException expected) {
                System.out.println(name + ": dropped TIMEOUT, done="
                        + dropped.isDone());
            }

            // Explicitly move the orphaned Future to cancelled state.
            dropped.cancel(false);
            System.out.println(name + ": canceled="
                    + dropped.isCancelled());
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not stop");
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 DroppedFutureDemo.java
java DroppedFutureDemo
~~~

Stdout of the program (excluding any runtime environment lines):

~~~text
DiscardPolicy: running=running
DiscardPolicy: kept=queued
DiscardPolicy: dropped TIMEOUT, done=false
DiscardPolicy: canceled=true
DiscardOldestPolicy: running=running
DiscardOldestPolicy: kept=newest
DiscardOldestPolicy: dropped TIMEOUT, done=false
DiscardOldestPolicy: canceled=true
~~~

**Why the output is deterministic:** the `started` latch guarantees the worker entered `running` before `queued` is submitted. The `release` latch keeps the worker from pulling another task before the third task is rejected. Because the pool has only one worker and one queue slot, the rejection condition is deterministic. Which task is kept or dropped follows the stated rules; the two `get(5, SECONDS)` calls act as test safety bounds, while `get(100, MILLISECONDS)` proves the dropped Future stays `isDone() == false`. Finally, `cancel(false)` moves the Future to cancelled; it does not "recover" lost work.

After `cancel(false)` succeeds, calling `dropped.get()` raises `CancellationException` instead of waiting forever. `cancel` returns a boolean reflecting the cancellation attempt; to inspect final state, read `isCancelled()`. The example needs no network, DB, or Spring Boot to reproduce the root cause; Spring's executor wrapping the JDK pool carries the same risk if configured with these rejection handlers.

## 5. Preferred Fix: Reject With an Explicit Signal

### 5.1. Use AbortPolicy When the Caller Must Know Whether Work Was Accepted

Replacing `DiscardPolicy` with `AbortPolicy` makes `ThreadPoolExecutor` throw `RejectedExecutionException` when the pool saturates. With `submit`, the exception is thrown **right at submission**, before any Future is returned:

~~~java
// Illustrative snippet when pool is saturated; not a full class.
try {
    Future<String> future = pool.submit(() -> "report");
    // Store future only after submit returns normally.
} catch (java.util.concurrent.RejectedExecutionException ex) {
    // Report overload and mark the request/job as rejected.
}
~~~

Do not use `try { future.get() }` to detect rejection after enabling `DiscardPolicy`: the Future may never yield a result or an error. You must change the **acceptance policy**, not just add a `catch` after `get()`.

In Spring Framework, `ThreadPoolTaskExecutor` can throw `org.springframework.core.task.TaskRejectedException` when rejecting under the abort-style default policy. At the API layer, return HTTP `503 Service Unavailable` or `429 Too Many Requests` depending on semantics and rate-limit policies; never return `202 Accepted` as if the system had durably accepted the work.

### 5.2. Do Not Abandon Futures When Intentionally Evicting Tasks

If business rules allow **shedding low-priority work**, there must be a mechanism to let the submitter know the task will no longer run:

- For an evicted `FutureTask`, call `cancel(false)` or complete it exceptionally via a wrapper/gateway managing results.
- For an application-owned `CompletableFuture`, use `completeExceptionally(new RejectedExecutionException(...))` or an explicit error/cancelled state; not every `Runnable` created by `CompletableFuture` is a `Future<?>` you can cast and cancel.
- Record `REJECTED`, `DROPPED`, or `CANCELLED` in job status, metrics, and logs so upstream can retry or notify users.
- With `DiscardOldestPolicy`, handle **the task just evicted from the queue**, not just a newly rejected task. Because of races (shutdown, worker polling, multiple submitters), custom handlers require thorough testing; if prioritizing newer tasks is not needed, stick with the simpler `AbortPolicy`.

JDK 17's Javadoc for `DiscardOldestPolicy` also illustrates a custom handler pulling the old task from the queue and cancelling it if it is a `Future<?>`. However, merely casting/cancelling the `Runnable` polled from the queue may **not be enough** for `CompletableFuture` wrappers, callbacks, or a job system with separate persisted state. Choose a design that ties task identity to the Future/status that must be completed.

## 6. Second Line of Defense: Wait Deadlines and Terminal States

### 6.1. Future.get(timeout) Only Bounds Wait Time

~~~java
// Illustrative snippet inside a method that may throw InterruptedException.
try {
    String result = future.get(3, TimeUnit.SECONDS);
    consume(result);
} catch (TimeoutException ex) {
    boolean canceled = future.cancel(true);
    recordTimeout(canceled);
} catch (java.util.concurrent.ExecutionException ex) {
    recordFailure(ex.getCause());
} catch (java.util.concurrent.CancellationException ex) {
    recordCancellation();
}
~~~

`consume`/`recordTimeout`/`recordFailure`/`recordCancellation` are hypothetical business methods: this snippet is **not standalone**. The `3 seconds` limit only means the caller waits at most roughly that long in `get`. `cancel(true)` sends a cancellation request and may interrupt the worker, **without guaranteeing** that a running task stops, rolls back DB work, or stops writing files. `Future.get(timeout)` by itself does not cancel the task.

When real SLAs are required, combine a **queue-wait budget**, an **execution timeout**, I/O/DB timeouts, and idempotency so a retried job does not collide with an original attempt still running after the caller timed out.

### 6.2. CompletableFuture.orTimeout() Transitions a Future to a Terminal State

~~~java
// Illustrative snippet: future is created and owned by the application.
CompletableFuture<String> future = new CompletableFuture<>();
future.orTimeout(3, TimeUnit.SECONDS);
~~~

If not completed within 3 seconds, that `CompletableFuture` completes **exceptionally** with `TimeoutException`; `join()` will throw `CompletionException` wrapping the cause. `orTimeout` returns **the same configured future**, not an independent copy. This prevents an in-memory `CompletableFuture` from staying pending forever.

However, `orTimeout` **does not stop the underlying task**, does not remove a queued task from the executor, does not cancel other `FutureTask`s, and does not finalize a DB-persisted job. The task may still keep executing side effects after the future times out; a late `complete(...)` call simply fails to overwrite the existing terminal result.

`completeOnTimeout(value, timeout, unit)` completes normally with a fallback value, suitable for some caches/fallbacks **only when business rules allow it**. Never turn a lost financial report into a fake success result just to hide overload.

### 6.3. Wait Timeouts Do Not Replace Rejection Handling

A solid design has three steps:

1. **Submission:** use a throwing handler and record rejection immediately when `execute/submit` refuses work.
2. **Execution:** have the task complete with a result or exception via `try/catch/finally` so no error path is forgotten.
3. **Deadline:** enforce client wait limits and/or timeouts on `CompletableFuture`, record timeout status, and manage running/queued tasks upon expiration.

Implementing only step 3 **prevents callers from waiting forever**, yet still silently loses tasks and risks leaking inconsistent business state.

## 7. Integrating Properly With Spring ThreadPoolTaskExecutor

### 7.1. Bounded Executor Bean With AbortPolicy

Spring Framework 6.x example running on Java 17, inside a `@Configuration` class (this is a configuration snippet, not a standalone executable application):

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportPoolConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-");
        pool.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(15);
        return pool;
    }
}
~~~

With a Spring-managed `@Bean`, the container handles lifecycle/initialization of `ThreadPoolTaskExecutor`. If instantiated manually outside Spring, call `initialize()` before running tasks. This pool uses at most four workers and a queue of 20 per `ThreadPoolExecutor` rules; when the queue is full and workers are at limit, admitting new tasks fails per `AbortPolicy`.

**Do not equate `maxPoolSize=4` with always having four threads:** the pool initially grows to core=2, then prefers queuing, and only considers extra workers once the queue is full. Under overload, handle the exception at the submission site; otherwise the API may return an unhandled 500 or falsely mark a job as accepted.

### 7.2. Gateway Returning CompletableFuture With Full Terminal Coverage

This example is a **complete Spring service class** designed to pair with `ReportPoolConfig` in the same Spring application with component scanning configured:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportGateway {
    private final ThreadPoolTaskExecutor executor;

    public ReportGateway(
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> submit(String reportId) {
        CompletableFuture<String> outcome = new CompletableFuture<>();

        try {
            executor.execute(() -> {
                try {
                    // Replace with real business logic, with explicit DB/HTTP timeouts.
                    String location = "reports/" + reportId + ".csv";
                    outcome.complete(location);
                } catch (Throwable ex) {
                    // Ensure the failure branch produces an observable outcome.
                    outcome.completeExceptionally(ex);
                }
            });
        } catch (TaskRejectedException ex) {
            // AbortPolicy: error raised immediately when submitting task.
            outcome.completeExceptionally(ex);
        }

        // Last line of defense: Future never stays pending past 30s in memory.
        return outcome.orTimeout(30, TimeUnit.SECONDS);
    }
}
~~~

`execute` can throw `TaskRejectedException` when the pool saturates; in that branch `outcome` completes exceptionally, letting clients detect it and return 503. If business logic inside the worker fails, `completeExceptionally` preserves the error for downstream observation. `orTimeout` guards callers if something unexpectedly stalls or someone swaps the handler to a silent-drop policy.

**Gateway limitations:** the illustrative worker creates a string quickly, does not durably store jobs, and cannot guarantee exactly-once execution. If the future times out after the worker has started, the worker may continue running and produce side effects. For multi-step workflows or DB writes, persist job state in durable storage, enforce deadlines, and prevent late-succeeding jobs from duplicating client retries.

### 7.3. When Using `@Async`

~~~java
// Snippet in a Spring-managed service, called through proxy from another bean.
@Async("reportExecutor")
public CompletableFuture<String> build(String id) {
    String result = createReport(id);
    return CompletableFuture.completedFuture(result);
}
~~~

This is a snippet; `createReport` is defined by the application. `@EnableAsync` must be enabled, and the method must be invoked through the Spring proxy for `@Async` to apply in proxy mode. The executor is selected by bean name, so that bean's rejection/queue policy applies directly.

If the executor throws `TaskRejectedException` on submission, the exception can surface **right at the proxy call**; errors inside the worker propagate per `Future/CompletableFuture` semantics. Do not assume all errors arrive only at `future.join()` or that all errors are always thrown synchronously. With a silent-drop handler, the proxy call may return a Future that nobody ever completes.

## 8. Choosing Result Semantics for Real Requirements

### 8.1. When Results Are Not Required, Dropping Is Possible—Only Explicitly

Non-critical telemetry may be allowed to drop under overload. In that case, fire-and-forget `execute(Runnable)` plus a `dropped_total` metric can be a valid policy choice. However, if the caller requires confirmation such as "audit log saved," "email sent," or "report generated," silently dropped **must never** be treated as success.

If using `DiscardOldestPolicy` for something like a cache refresh (only the latest matters), you must still resolve callbacks/awaiters of the older attempt if they exist. Consider changing the architecture to keep a single "latest" state with coalescing and a controlled `CompletableFuture` completion rather than blind queue eviction.

### 8.2. Guaranteed Processing Across Restarts Requires a Durable Queue

`ThreadPoolTaskExecutor` and `Future` are in-memory structures of **a single process**. When a pod dies, every Future in that JVM vanishes too. If the business cannot lose jobs, persist requests to a DB/message broker with transactions/acks plus retry + idempotency.

A typical sequence:

1. HTTP POST checks an idempotency key and saves a `PENDING` job to the DB.
2. Only after transaction commit does it dispatch via broker/outbox or a reliable worker.
3. Worker transitions the job to `RUNNING` via a conditional claim, records `DONE` or `FAILED`, with retry/backoff.
4. GET API queries job status; on expiration, reconciliation finds stuck jobs and transitions them to retry/failed per policy.

Interacting with a broker/DB does not give exactly-once automatically; design idempotent side effects and conditional state transitions. Regardless of the queue used, monitor wait-time expiration.

## 9. Shutdown and Abandoned Futures

`shutdown()` gives the executor a chance to finish accepted and queued tasks; `shutdownNow()` attempts to interrupt running tasks and returns a list of `Runnable`s that never started. The JDK does not automatically promise to cancel every Future corresponding to those returned Runnables. If an application owns a `ThreadPoolExecutor` and only submits `FutureTask`s, it can cancel the Futures in that returned list:

~~~java
// Illustrative snippet in code managing a ThreadPoolExecutor.
for (Runnable queued : pool.shutdownNow()) {
    if (queued instanceof java.util.concurrent.Future<?> future) {
        future.cancel(false);
    }
}
~~~

This lets `get()` on drained `FutureTask`s observe `CancellationException`, yet **cannot cancel tasks previously discarded** and does not apply universally to every Spring wrapper, `CompletableFuture`, or broker. When using a Spring-managed `ThreadPoolTaskExecutor`, configure appropriate lifecycle/shutdown settings and record unfinished jobs at the application layer; do not call `shutdownNow()` directly on a framework-owned resource without a strategy.

Several rejection handlers discard tasks once the executor has shut down. Therefore, testing the shutdown/redeploy path is just as critical as testing a full queue.

## 10. Testing to Guarantee Zero "Orphaned" Futures

A useful test must **deterministically saturate the pool** using latches instead of submitting many tasks and hoping for a race. With `core=max=1` and `queue=1`:

1. Put task A on the worker and block it with `CountDownLatch`.
2. Enqueue task B, verifying the queue holds one item if needed.
3. Submit task C to trigger the rejection handler.
4. With `AbortPolicy`, assert the caller receives `RejectedExecutionException` (JDK) or `TaskRejectedException` (Spring) and that the job is recorded as `REJECTED`.
5. With an intentional drop policy, verify the dropped Future is `cancel`led or `completeExceptionally`d within a bound; never use unbounded `get()` in tests.
6. Release the latch and verify accepted tasks complete, dropped tasks reach a terminal state, and no ID stays `PENDING` forever.

Beyond unit tests, track at runtime: active workers, `getQueueSize()`, rejection rate, queue wait time, task execution latency, overdue `PENDING` count, `Future` timeouts, retry rate, lost callbacks, and jobs reaching terminal state. Do not count only completed tasks, because dropped tasks **never enter the completion path** to be counted.

### Common Root-Cause Matrix

| Symptom | Cause to check | Remediation |
| --- | --- | --- |
| `submit` returns Future but `get()` never returns | `DiscardPolicy` dropped the new task | Use AbortPolicy; enforce timeouts and terminalize outcomes |
| New task runs yet old task's Future stays pending | `DiscardOldestPolicy` evicted old task from queue | Avoid this policy or cancel/complete evicted jobs |
| `CompletableFuture.allOf(...)` never completes | One child future never reached terminal state | Bound timeouts and resolve each future; trace lost upstream task |
| No `RejectedExecutionException` observed | Silent rejection handler | Audit `setRejectedExecutionHandler` and runtime bean config |
| `get(timeout)` timed out yet `isDone()==false` | Timeout only caps waiting time | Define cancel/terminal state handling and retry policy |
| `orTimeout` fired yet DB was still written | Future timeout does not stop the worker | Cancellation mechanism, transactions, idempotency |
| Waiters still hang after shutdown | Queued tasks drained/dropped without cancelling Futures | Track/cancel outstanding tasks, coordinate shutdown |
| Spring returns 202 despite rejected job | Rejection not mapped to HTTP/job state | Catch `TaskRejectedException` at gateway, return 429/503 |
| Queue stays full and many tasks are dropped | Arrival rate exceeds processing capacity | Bounded queue, backpressure, rate limits, task optimization |

## 11. Self-Check Questions

1. Why does `ExecutorService.submit(...)` returning normally not guarantee the task will run when `DiscardPolicy` is used?
2. In a single-worker, single-slot-queue pool where task A is running, B is queued, and C arrives: which Future can become "orphaned" under `DiscardPolicy` vs `DiscardOldestPolicy`?
3. What is the difference between `future.get(3, SECONDS)` throwing `TimeoutException` and `CompletableFuture.orTimeout(3, SECONDS)`?
4. Does `Future.cancel(true)` guarantee a DB transaction rolls back or the task stops immediately?
5. Why is `CallerRunsPolicy` also not a guarantee of Future completion when the executor has shut down?
6. Spring's `ThreadPoolTaskExecutor` uses `AbortPolicy`: where should rejection be caught, and what should HTTP/job status return?
7. If the application is killed while a job is still in the queue, can an in-memory `Future` replace a durable job store?
8. Why is a "completed tasks" metric insufficient to detect discarded tasks?

**Practical rule:** whenever an API promises a result via `Future`, treat **silent discard** as a design bug unless a matching terminal notification path exists. Use explicit-signal rejection, bounded waits, clear completion/cancellation, and track job status across every branch so no caller blocks indefinitely.

## References

- [Java SE 17 — ThreadPoolExecutor and rejection policies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)