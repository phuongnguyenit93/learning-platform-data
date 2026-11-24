# TaskRejectedException and the Contract When Spring TaskExecutor Cannot Accept a Task

When a Spring application submits background work to a `TaskExecutor`, sometimes the executor cannot or will not accept additional tasks. This is a normal operational condition that should be designed for upfront, especially when the system is under heavy load or shutting down. In Spring, `TaskRejectedException` is the key signal for that condition. Understanding this signal properly prevents returning "job accepted" when in reality no component has taken responsibility for executing the work.

This lesson focuses on **the contract at submission time**, causes of rejection, overload policies, and how a Spring application should respond. It does not assume that every `TaskExecutor` runs asynchronously or that tasks are persisted durably.

## 1. What Should You Be Able to Distinguish After This Lesson?

- Distinguish **executor accepts the task**, **task starts**, **task completes**, and **business result is durably persisted**.
- Identify when `TaskExecutor.execute(Runnable)` can throw `TaskRejectedException` and its relationship to `RejectedExecutionException` in the JDK.
- Understand the allocation order across `corePoolSize`, the queue, `maxPoolSize`, and when a pool hits its limit.
- Compare `AbortPolicy`, `CallerRunsPolicy`, `DiscardPolicy`, and `DiscardOldestPolicy` in terms of **work-loss guarantees, latency, and backpressure**.
- Configure a bounded `ThreadPoolTaskExecutor`, catch failures at the submission boundary, and design responses/retries matching actual guarantees.
- Test rejection scenarios **deterministically with latches**, instead of relying on `Thread.sleep()`.

## 2. What Does `TaskExecutor` Promise?

Spring defines `org.springframework.core.task.TaskExecutor` extending `java.util.concurrent.Executor` with the method:

~~~java
void execute(Runnable task);
~~~

The call hands a `Runnable` to the executor. Depending on the implementation, the task may run immediately on the calling thread (`SyncTaskExecutor`), run on a worker thread, or be placed in a queue. The API returns no job ID, result, completion status, or durability guarantee.

Under the `TaskExecutor` contract, when it cannot accept a task, `execute` may throw **`TaskRejectedException`** (unchecked). This is a failure **at the work-handoff boundary**. Do not equate it with exceptions thrown inside `Runnable.run()` after the task has started.

### Four Distinct Milestones

| Milestone | Meaning | What is not yet guaranteed |
| --- | --- | --- |
| `execute` is called | Caller asks the executor to accept work | Not yet known whether it will be accepted |
| No rejection in an explicit-failure configuration | Executor accepted the work per its active policy, or may have run it synchronously | Does not guarantee the task has started, completed, succeeded, or is durable |
| `Runnable.run()` starts | Worker/caller starts executing the work | Work may fail, be cancelled, or stop partway through |
| Task completes and result is committed | An execution outcome exists; durability depends on the storage layer | No duplicate-prevention guarantee if retries are not designed properly |

**Important exception:** if a **silent-drop policy** such as `DiscardPolicy` is configured, `execute` can return normally even though the task was neither run nor queued. Therefore, the claim "no exception thrown means the task was definitely accepted" relies on **a specific rejection policy** (such as `AbortPolicy`), not a universal truth for all executors.

To satisfy "every job must be processed," an in-memory queue and a successful `execute` call **are not enough**. You need durable intake, a job identifier, a recovery mechanism, status tracking, and retry/idempotency rules.

## 3. What Does `TaskRejectedException` Mean?

`org.springframework.core.task.TaskRejectedException` **extends `java.util.concurrent.RejectedExecutionException`**. It is a runtime exception indicating that a `TaskExecutor` did not accept a task under Spring's contract. When `ThreadPoolTaskExecutor` receives `RejectedExecutionException` from the underlying JDK executor, it normally translates it into `TaskRejectedException` so Spring callers see a consistent exception type.

Implications when catching errors:

~~~java
try {
    taskExecutor.execute(task);
} catch (TaskRejectedException ex) {
    // Spring contract: the job was not accepted.
    // Must explicitly expose the non-acceptance status to the caller.
}
~~~

This is an **illustrative snippet placed inside a method** with a valid `taskExecutor` and `task`; the logic inside `catch` must be decided by business requirements. If you call `java.util.concurrent.ThreadPoolExecutor` directly, the corresponding exception is typically `RejectedExecutionException`. Because `TaskRejectedException` is a subclass, `catch (RejectedExecutionException ex)` catches it too, though catching Spring's specific type usually communicates intent more clearly at the Spring application layer.

Never interpret `TaskRejectedException` as "the task ran and failed," "it was already retried," or "it will automatically run later." At that moment, the application must decide whether to return an error, shed load, persist the job for later resubmission, or switch to a fallback mechanism.

### Distinguishing It From Task-Body Exceptions

Suppose a task was accepted:

~~~java
taskExecutor.execute(() -> {
    throw new IllegalStateException("Could not read input file");
});
~~~

In a typical **asynchronous** executor model, an exception from `run()` happens on the worker thread and does **not** return to the original thread's `execute` call the way rejection does. If the implementation runs synchronously, the body exception can surface directly on the calling thread. `Future`/`CompletableFuture` classes have their own channels for propagating results or errors; inspect their completion state properly rather than catching only `TaskRejectedException`.

## 4. When Does a Pool Reject Tasks?

For Spring's commonly used `ThreadPoolTaskExecutor`, the underlying engine is JDK `ThreadPoolExecutor`. Two typical causes:

1. **Load limit reached:** existing workers are busy, the queue is full, and there is no room to grow threads under `maxPoolSize`.
2. **Shut down / shutting down:** the executor has stopped accepting new tasks due to its lifecycle or shutdown policy.

Other implementations may follow different rules. For example, executors with a concurrency limit, blocking submission policy, or synchronous execution have different semantics; **do not** apply `ThreadPoolExecutor`'s formula blindly to every `TaskExecutor`.

### Typical Work-Allocation Sequence in `ThreadPoolExecutor`

1. If the current worker count is less than `corePoolSize`, prefer starting a worker to run the new task.
2. Beyond core size, try to **place the task in the queue**.
3. When the queue cannot accept more items, if worker count is less than `maxPoolSize`, try expanding the pool.
4. When capacity is completely exhausted, invoke `RejectedExecutionHandler`.

Consider `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=3`: under sustained load where running tasks have not finished yet, the pool uses 2 core workers; then 3 tasks wait in the queue; next it can expand to 4 workers; subsequent tasks are rejected if all workers and queue slots remain saturated. This describes behavior **at the instant resources are busy**; in practice, tasks completing concurrently can change the outcome.

### Do Not Ignore Default Settings

`ThreadPoolTaskExecutor` typically defaults to `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, and `queueCapacity=Integer.MAX_VALUE`. With a nearly unbounded queue, the pool rarely scales beyond core and backlogged jobs can grow huge, even risking out-of-memory errors. **Seeing zero rejections does not mean the system is healthy.**

Queue choices to understand:

- `queueCapacity > 0`: Spring uses a `LinkedBlockingQueue` with the declared capacity.
- `queueCapacity = 0`: Spring uses a `SynchronousQueue` with no buffer; tasks must hand off directly to a worker or trigger pool expansion/rejection.
- A bounded queue paired with a bounded `maxPoolSize` establishes clear acceptance thresholds and an overload path.
- Raising `maxPoolSize` will not cure an oversized queue if tasks always enqueue before extra workers are created.

Do not treat configuration numbers as absolute guarantees of latency or throughput. Per-task speed, blocking I/O, dependency wait times, CPU scheduling, and rejection policies determine actual load behavior.

## 5. `RejectedExecutionHandler` Options and Their Trade-Offs

`ThreadPoolTaskExecutor` allows configuring `setRejectedExecutionHandler(...)` to pass a rejection policy down to the JDK pool. Four built-in options on `ThreadPoolExecutor`:

| Policy | When pool is saturated | Fits when | Risks to handle proactively |
| --- | --- | --- | --- |
| `AbortPolicy` (default) | Throws `RejectedExecutionException`; Spring normally converts to `TaskRejectedException` | You want the caller to **know for sure the work was not accepted** and decide retry/HTTP error | If the caller fails to catch/translate it properly, an unhandled error leaks out |
| `CallerRunsPolicy` | Calling thread **runs the task itself** if the pool has not shut down | Willing to increase producer latency to apply backpressure | Can block request threads or event loops, or make execution unexpectedly synchronous; if the pool is shut down, the task can be silently dropped |
| `DiscardPolicy` | Drops the task **without throwing** | Only for best-effort signals that are allowed to be lost by design | Caller may think the task was accepted; any corresponding `Future` may never complete |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting the new task, unless shut down | Special cases where older queued tasks are expendable | Loses older jobs, breaks ordering, leaves the dropped job's `Future` hanging unless cancelled/failed, unsuitable for priority queues |

For orders, traceable report exports, or business data processing, **`AbortPolicy` is usually the safe choice so rejections are never hidden**. For droppable metrics, a discard policy can make sense if you measure drop rates and have explicit agreement with consumers. Never adopt `CallerRunsPolicy` by habit without assessing its impact on response times and the calling thread.

Custom policies can also be implemented via `RejectedExecutionHandler`. If the caller must receive a failure signal, the custom handler must **throw `RejectedExecutionException`**; a handler that only logs and returns risks turning a rejection into a false success at the `execute` boundary.

~~~java
executor.setRejectedExecutionHandler((runnable, pool) -> {
    throw new java.util.concurrent.RejectedExecutionException(
            "Executor unavailable: saturated or shutting down");
});
~~~

The snippet above only illustrates calling the setter while configuring a `ThreadPoolTaskExecutor executor`, not a standalone Java program. In real applications, record rejection metrics while avoiding logging sensitive task payloads or performing heavy I/O inside the rejection handler itself.

## 6. Java 17+ Example: Triggering Rejection Deterministically

The following example uses **plain JDK `ThreadPoolExecutor`** to demonstrate the exact point at which the queue fills. We deliberately hold the first task in a worker, place a second task into a queue of capacity 1, and then submit a third task. Until the latch is released, both the worker and queue have zero space left.

**File `JdkRejectionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class JdkRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            pool.execute(() -> {
                completed.incrementAndGet();
                done.countDown();
            });

            boolean rejected = false;
            try {
                pool.execute(() -> completed.incrementAndGet());
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("rejected=" + rejected);
            if (!rejected) {
                throw new AssertionError("Expected a rejection");
            }

            releaseFirst.countDown();
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }
            System.out.println("completed=" + completed.get());
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run (JDK 17 or newer):

~~~bash
javac JdkRejectionDemo.java
java JdkRejectionDemo
~~~

Standard output of a successful run:

~~~text
rejected=true
completed=2
~~~

**Why is the output deterministic?** `firstStarted.await` proceeds only once the first task holds the worker; `releaseFirst` keeps that worker waiting, so the second task sits in the queue and the third task has no room. After catching the rejection, `releaseFirst.countDown()` lets the two accepted tasks finish; `done.await()` ensures results are read only after both complete. The two 5-second timeouts are safety guards against hanging indefinitely in broken environments, not race-creating delays.

When using **Spring's `ThreadPoolTaskExecutor`** with the same bounds and `AbortPolicy`, the saturation principle is identical, while the exception thrown from Spring's `execute` call is `TaskRejectedException`.

## 7. Configuring Spring `ThreadPoolTaskExecutor` So Rejections Have Clear Meaning

The pattern below uses bounded capacity and `AbortPolicy`. The numbers `2/4/20` are examples only, not recommended sizing for every application.

**File `ExportExecutorConfig.java` in a Spring project with `spring-context`:**

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExportExecutorConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("export-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

When registered as a normal Spring bean, the container manages executor initialization and lifecycle. If you construct `new ThreadPoolTaskExecutor()` manually outside the container and use it directly, you must call `initialize()` before `execute` and manage shutdown appropriately. Never set `setQueueCapacity` to an enormous number solely to mask overload signals.

A service class can let the exception **reach the business decision point**, rather than catching and swallowing it:

**File `ExportSubmissionService.java`:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ExportSubmissionService {
    private final TaskExecutor exportExecutor;

    public ExportSubmissionService(
            @Qualifier("exportExecutor") TaskExecutor exportExecutor) {
        this.exportExecutor = exportExecutor;
    }

    public void submit(String exportId) {
        exportExecutor.execute(
                () -> System.out.println("Processing export " + exportId));
    }
}
~~~

This is an example of a dispatch path where `System.out.println` stands in for a simple observable operation. It **does not** create a durable job, expose queryable status, or perform real file exporting. Job persistence, transactions, retries, and result handling must be added according to business needs.

The caller invoking `submit` must decide what `TaskRejectedException` means. For instance, an API unable to accept more jobs during overload might return HTTP 503, or HTTP 429 when enforcing per-caller rate limits. It may include `Retry-After` if a reliable retry policy exists. **HTTP 202 Accepted** should only be returned with semantics the application truly upholds: if you promise the work will be processed later, persist the request in durable storage before acknowledging.

### Place `catch` at the Right Boundary

~~~java
try {
    exportSubmissionService.submit(exportId);
    // Only report successful handoff under the current executor contract and policy.
} catch (TaskRejectedException ex) {
    // Do not return false success. Translate to an overload response,
    // or persist the work into a reliable fallback channel.
}
~~~

This snippet is an **illustrative handling pattern** that belongs inside a method with `exportSubmissionService`, `exportId`, and an appropriate business response. Do not retry immediately in a tight unbounded loop: while the pool is saturated, continuous retries only add more load.

## 8. `execute`, `submit`, `Future`, and `@Async`: Distinct Error Paths

| Case | Where does the failure surface? | What should the caller do? |
| --- | --- | --- |
| `TaskExecutor.execute` rejected under `AbortPolicy` | At the `execute` call site as `TaskRejectedException` | Handle non-acceptance, return status, or persist for retry |
| Task accepted, then `Runnable.run()` throws | On the execution thread; with an async executor, does not return to `execute` normally | Observe logs/task wrapper/status; add a future if a result handle is needed |
| `AsyncTaskExecutor.submit` accepts task, task fails | `Future.get()` throws `ExecutionException` (cause is original error) | Handle execution failure, distinct from submission rejection |
| `submit` rejected by executor | Can throw `TaskRejectedException` **before returning a `Future`** | Handle at the `submit` caller; do not wait on a nonexistent future |
| `CompletableFuture` created and task fails | Future completes exceptionally; `join()` usually throws `CompletionException` | Observe via `whenComplete/handle/exceptionally` or `join/get` |
| `@Async` via Spring proxy cannot dispatch task | Failure may occur on the calling thread when the proxy dispatches work | Catch at the method call boundary; do not rely on handlers for body errors |
| `@Async void` starts and then throws | Routed to `AsyncUncaughtExceptionHandler` for exceptions without a Future | Configure a handler / record the failed job appropriately |

`@Async` only works via proxy when calls actually pass **through the Spring proxy**; self-invocation on the same bean in default proxy mode normally goes unintercepted. Furthermore, if `CallerRunsPolicy` triggers under saturation, the work may run on the calling thread itself even though the code path is annotated async. Never build business contracts solely on the expectation that "this method always runs on another thread."

**Especially avoid:** pairing `submit` with `DiscardPolicy` or `DiscardOldestPolicy` for work whose result is awaited. A task/Future may be dropped without a corresponding completion or cancellation signal, causing `Future.get()` to hang forever. If tasks are intentionally dropped, ensure a mechanism marks the outcome as "dropped" or cancels the future appropriately.

## 9. Designing the Contract From the Caller's Perspective

Before writing code, answer: **when a job cannot be accepted, what must the system guarantee to the caller?** A decision table helps:

| Workload type | Can it be lost? | Recommended contract on rejection |
| --- | --- | --- |
| Best-effort analytics chart update | Yes, if agreed upon | Measure rejected/dropped counts; may drop with operational alerting |
| Regenerable temporary image rendering | Can be retried | Return "busy," retry with bounds, or store the request in another channel |
| Transactional emails, user-requested reports | Normally must not be lost silently | Persist durable job; reprocess with idempotency and queryable status |
| Debiting money, updating balances or inventory | Must not rely on a RAM queue | Use database transactions/conditional updates and post-commit dispatch |
| Short background HTTP work not requiring durability | Depends on SLA | Clearly notify on non-acceptance; never return false success |

### A Minimal State Machine for Guaranteed Jobs

A system with persisted jobs might track states such as:

~~~text
RECEIVED -> PENDING -> RUNNING -> SUCCEEDED
                     \-> FAILED_RETRYABLE -> PENDING
                     \-> FAILED_FINAL
~~~

If rejected prior to persistence and acceptance, the response must clearly report **NOT_ACCEPTED/REJECTED** or the API's equivalent. If durable persistence succeeds while the executor is full, the job can remain **PENDING** for a worker to pick up later; that is a different architecture from pure in-memory enqueuing.

When database updates and task dispatch must stay consistent, consider the **transactional outbox**: write business data and an outbox record in the same transaction; a worker/dispatcher submits later and marks completion only with proof. This is a common pattern to eliminate losing work between commit and submit. Handlers can still retry, so consumers must enforce idempotency by business key/job ID.

**Do not equate retries with safety:** if a job executed partway and crashed, retrying can repeat external actions. Idempotency, deduplication, and durable state matter far more than a loop calling `execute` again.

## 10. Retry and Backpressure: Controlling Load Instead of Causing a Retry Storm

When the policy signals rejection, several options exist depending on criticality:

1. **Fail fast:** return a busy error to the caller (e.g., 503), with retry hints when grounded in reality. Preserves resources and makes limits visible.
2. **Bounded retry:** enforce max attempts, deadlines, backoff, and jitter; retry only when allowed by contract and when the task is sufficiently idempotent. Avoid holding request threads too long while waiting.
3. **Durable queue / database job table:** acknowledge only after persistence; dedicated workers drain the backlog within execution capacity. Requires operations, monitoring, and dead-letter/failure handling.
4. **Caller-runs backpressure:** deliberately shifts latency onto the caller; fits certain batch producers, but should not be used casually for latency-sensitive request handlers or event loops.
5. **Throttle at the source:** rate limiting, bounded input queues, semaphores/permits, upstream concurrency caps, and circuit breakers for dependencies. Measuring arrival rate versus completion rate beats trying to raise thread counts without limit.

Back-of-the-envelope capacity check: with 4 workers and an average task duration of 200 ms, the **theoretical completion rate** is around 20 tasks/second when all workers stay busy, ignoring overhead and tail latency spread. If producers push 100 tasks/second continuously, a queue of 20 fills quickly; enlarging the queue only delays rejection while increasing latency. In practice, measure actual execution times and p95/p99 distributions rather than treating simple arithmetic as final sizing.

Note regarding `CallerRunsPolicy` during executor shutdown: under the JDK contract, the handler can **drop the task without running it**, so this policy does not reliably solve stopping intake cleanly. If errors must always be raised during shutdown, prefer `AbortPolicy` or a custom throwing handler.

## 11. Shutdown and Races Right When Intake Stops

Difficult edge cases happen not only at peak traffic. When the Spring `ApplicationContext` closes, the executor may stop accepting new tasks even while requests are still arriving or another component is still dispatching. Beyond rejection, whether tasks **already accepted and sitting in the queue** get to run or are cancelled depends on the shutdown configuration.

Distinguish:

- **Not accepting new tasks:** signals rejection when using a throwing policy.
- **Tasks already queued but not yet started:** may finish, be cancelled, or be stopped depending on lifecycle settings; acceptance is not completion.
- **Tasks currently running:** may be interrupted or allowed to finish during graceful shutdown, depending on configuration.
- **Durable jobs:** can recover after restart if persisted state and re-drive protocols are designed properly.

`ThreadPoolTaskExecutor` provides settings for waiting on tasks during shutdown and a termination wait budget (such as `setWaitForTasksToCompleteOnShutdown` and `setAwaitTerminationSeconds`). Consult your exact Spring version and align with your infrastructure's shutdown budget. Never arbitrarily call `shutdownNow()` on a Spring-managed bean just to "free resources."

### Boundary With `@Transactional`

A task running on a worker thread does not automatically inherit the database transaction attached to the submitting thread. If work is submitted before the main transaction commits, the worker may see uncommitted data or act on business state that ultimately rolls back. When "after-commit" semantics are required, use after-commit integration or an outbox, depending on durability needs. Avoid using an in-JVM executor as the source of truth for cross-process transactions.

## 12. Observability: Knowing Why and When Rejections Happen

If you only log each thrown exception without measuring pool state, it is hard to decide whether to shed load or scale capacity. A useful observability set includes:

- **Rejection count/rate** by executor, task type, and saturation/shutdown cause when identifiable; avoid job ID labels that cause cardinality explosions.
- **Pool size / active threads**, **queue size / capacity**, and pending job counts. `ThreadPoolTaskExecutor` exposes `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` for inspection.
- **Queue wait time**, task execution duration, throughput, timeouts, cancellations, retries, and permanently failed jobs.
- **Thread pool/queue utilization** alongside API p95/p99 response times, 429/503 rates, and downstream latency.
- **Shutdown/cancel events** to distinguish overload rejections from lifecycle rejections.

With Micrometer/Actuator, you can instrument executors and publish relevant metrics; do not assume every Spring setup automatically exports every metric you need. If writing a custom rejection counter, remember the handler may run on the caller thread: keep metric recording cheap and non-blocking.

A useful error log typically includes executor name, job type, safe correlation ID or job ID, observed reason, queue size/active threads, and fallback decision. Avoid logging full task payloads or personal data.

## 13. Testing Rejection Properly

**Never use `Thread.sleep(100)` to "hope the pool fills up."** OS schedulers and CI machines vary. Use latches like the JDK example to pin down the exact instant the worker is busy and the queue holds a task.

Scenarios to cover:

| Scenario | What to prove |
| --- | --- |
| Pool with 1 worker, queue 1, first task held by latch, submit third task | `AbortPolicy` signals rejection; in Spring, catch `TaskRejectedException` |
| Pool has available capacity | Task is accepted; do not conclude the task completed solely because `execute` returned |
| Pool is shut down | New submissions are rejected per active policy; no false success |
| Accepted task throws inside body | Not mislabeled as "rejected"; observed via future/status/error handler |
| `CallerRunsPolicy` under load | Third task runs on caller thread; latency increases; pool capacity constraints are respected |
| `DiscardPolicy`/`DiscardOldestPolicy` | Prove the dropped-task path and verify observation/cancellation contracts so futures do not hang forever |
| Concurrent burst requests | No unbounded retry loops, no silent order loss, metrics reflect rejections |
| Graceful shutdown and restart | Durable jobs are not lost; workers reprocess cleanly and idempotency holds |

For Spring integration tests, configure a `ThreadPoolTaskExecutor` with `core=1, max=1, queue=1`, set `AbortPolicy`, and apply the same latch strategy. If instantiating the executor manually in a test, remember to call `initialize()` and close it in `finally`; if using a Spring-managed bean, let the container manage its lifecycle. In HTTP tests, assert the exact response/status and ensure rejected submissions are never marked "accepted."

## 14. Common Implementation Mistakes

1. **Swallowing `TaskRejectedException` and returning HTTP 200/202 unconditionally.** Callers think work was accepted; define what accepted means and report no-capacity clearly.
2. **Leaving an unbounded queue by default and hoping overload vanishes.** This turns early rejection into growing backlogs and memory exhaustion risk.
3. **Raising `maxPoolSize` while keeping a huge queue.** The pool may stay stuck at core size because tasks enqueue first.
4. **Catching errors inside `Runnable.run()` to handle rejections.** Rejection happens at submission time before the `Runnable` ever runs.
5. **Using `@Async void` and assuming `AsyncUncaughtExceptionHandler` catches dispatch rejections.** Submission failures and task-body failures are two different paths.
6. **Using `CallerRunsPolicy` in request/event-loop threads without accounting for latency.** Heavy load can force heavy logic onto the caller's thread, breaking fast-response SLAs.
7. **Using `DiscardPolicy` for work that must complete.** Task loss becomes silent and hard to recover from; awaited futures can hang.
8. **Retrying immediately in a `catch` block.** When the pool is full, hot retries spike CPU/logging and prevent recovery.
9. **Assuming having a `Future` means the task was definitely processed.** A Future represents pending completion, not guaranteed durability or execution if dropped.
10. **Using an in-memory queue instead of a job store after promising durability to users.** Restarts or shutdowns can lose unexecuted work.
11. **Not recording rejection metrics.** Impossible to separate traffic spikes beyond sizing, shutdowns, and misconfiguration.
12. **Testing with random timing.** Use latches/barriers to pin interleaving and assert rejections cleanly.
13. **Configuring an executor bean while `@Async` uses a different executor.** Use `@Async("exportExecutor")` when targeting a specific bean, and verify calls go through the proxy.
14. **Assuming the submitting thread's transaction flows into the worker thread.** Design explicit state persistence, after-commit hooks, or an outbox instead.

## 15. Applied Scenarios

**Scenario A — heavy report generation:** a report pool has `core=2, max=4, queue=20`. Request #27 arrives while workers and queue are at threshold and is rejected. The API must not respond "report is processing" without a durable job ID. It can return 503 for bounded caller retries; even better, if processing must be guaranteed, persist the job first and let workers drain the backlog at their own pace.

**Scenario B — non-critical logs/telemetry:** dropping some events under overload may be acceptable if drop rates are tracked and data loss is agreed upon. `DiscardPolicy` is inappropriate if dashboards or alerting assume every event is delivered.

**Scenario C — batch producer:** a dedicated producer generates tasks faster than the pool completes them. `CallerRunsPolicy` can throttle the producer because the producer must run tasks itself once saturated, though that changes latency, thread context, and shutdown behavior. Use it only if the producer owner accepts those trade-offs.

**Scenario D — rolling deployment shutdown:** an instance stops accepting new work while requests still arrive. `TaskRejectedException` signals the need to route to another instance or return unavailable; if the job is already in a database or message queue, another worker can pick it up. A single local `ThreadPoolTaskExecutor` does not provide cross-replica handoff.

## 16. Self-Check

1. Does `TaskExecutor.execute` returning normally always mean "the task definitely completed"? Which configurations can prevent it from even entering the queue?
2. With `corePoolSize=2, maxPoolSize=4, queueCapacity=3`, why does the third task normally enter the queue instead of immediately growing the pool to 3 workers?
3. Why does a Spring `ThreadPoolTaskExecutor` with `AbortPolicy` throw `TaskRejectedException`, whereas direct JDK `ThreadPoolExecutor` normally throws `RejectedExecutionException`?
4. Why can `CallerRunsPolicy` cause HTTP response times to spike sharply? What happens once the pool has shut down?
5. How do exceptions thrown by `Runnable.run()` and `TaskRejectedException` differ in timing and observation path?
6. Why can submitting work inside an uncommitted transaction cause a worker to read stale or invalid state?
7. When an API returns 202 Accepted, what additional components are required to promise jobs will not be lost across restarts?
8. Design an integration test without `Thread.sleep()` proving that 1 worker + queue 1 rejects the third task.

## 17. Official References

- [Spring Framework — TaskExecutor API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — TaskRejectedException API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/TaskRejectedException.html)
- [Spring Framework — ThreadPoolTaskExecutor API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)

**Practical principle:** A bounded executor needs an **explicit rejection policy**, an observable rejection-handling boundary, and a contract stating accurately what the caller gets back. "Submitted to the pool" is only the first step; durability, results, and retries remain the application architecture's responsibility.