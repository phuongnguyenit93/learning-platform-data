# CallerRunsPolicy Shifts Work to the Calling Thread and Alters Latency

In Spring applications, `ThreadPoolTaskExecutor` typically uses a group of worker threads to process background work. However, when the pool is busy and the queue is full, a new task can be rejected. `java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy` is a strategy for handling that situation: **if the executor has not shut down, the thread calling `execute()` executes the rejected task itself**.

The result is striking: a call expected to merely "submit work" can turn into a **synchronous call that blocks until the work finishes**. If the caller is an HTTP request thread, that request's response time increases by the task's execution duration. If the caller is a thread dedicated to producing work, the production rate naturally slows down. The latter mechanism is called **caller backpressure**, though it is only suitable when the consequences for latency, thread context, and task execution contracts are acceptable.

One limit must be kept in mind immediately: **if the executor has shut down, `CallerRunsPolicy` drops the task and throws no error**. Therefore, never treat a normal return from `execute()` as proof that a task was accepted for later processing.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain when `ThreadPoolExecutor` delegates to `RejectedExecutionHandler` and when `CallerRunsPolicy` runs the task on the caller thread.
- Distinguish **worker thread**, **caller thread**, **queue**, and **running task**; understand why `maximumPoolSize` does not bound the total number of tasks concurrently running on callers.
- Analyze impacts on `execute()` latency, HTTP response time, throughput, p95/p99, and producer cycles.
- Configure `CallerRunsPolicy` with Spring's `ThreadPoolTaskExecutor` and understand the effects when using `@Async`, `Future`, or `CompletableFuture`.
- Recognize risks: running inside transaction/request contexts, blocking event-loops, deadlocks/reentrancy, exceptions surfacing on the caller, and tasks silently dropped during shutdown.
- Write Java 17+ tests independent of timing to prove a task was pushed onto the caller.
- Choose an overload policy and observability strategy suited to business requirements.

## 2. Why Does an Executor Need a Rejection Policy?

Java's `ThreadPoolExecutor` has at least three capacity-related elements:

1. `corePoolSize`: the core worker level.
2. `maximumPoolSize`: the maximum number of workers **belonging to the pool**.
3. `BlockingQueue<Runnable>`: storage for work that has been accepted but not yet picked up by a worker.

Under standard configuration, `execute(task)` proceeds as follows:

1. If the worker count is below `corePoolSize`, try creating a worker to run the task.
2. If core is reached, try adding the task to the queue.
3. If the queue cannot accept more and workers are below `maximumPoolSize`, try creating an additional worker.
4. If none of those options can accept the task, or the executor is shutting down, call `RejectedExecutionHandler`.

This describes the decision path of `ThreadPoolExecutor`, not the contract of every `Executor`. While handling a call, another worker can finish a task or pull work from the queue, so saturation is a condition that can change very rapidly.

For example, `core=2`, `max=4`, queue holding 3 elements: while two workers are busy, three new jobs can enter the queue; after that, the pool can create two extra workers; if four workers are busy and all three queue slots are occupied, a new task must go to the rejection handler. Having `getActiveCount()==max` does not automatically guarantee rejection, because the queue may still have remaining capacity.

### Queues Need Deliberate Bounds

Spring's `ThreadPoolTaskExecutor` defaults to `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, and `queueCapacity=Integer.MAX_VALUE`. With a huge queue, work usually piles up in the queue before the pool ever needs to expand beyond core; latency can climb steadily while the rejection policy is never triggered.

To evaluate `CallerRunsPolicy` under overload, you must first define **finite capacity**, producer rate, consumer rate, task cost, and maximum permissible response time. Do not increase queue size arbitrarily just to avoid seeing overload signals.

## 3. Exact Contract of CallerRunsPolicy

`CallerRunsPolicy` is a nested class in `ThreadPoolExecutor` implementing `RejectedExecutionHandler`. When the handler is invoked:

| Executor state | Behavior |
| --- | --- |
| Executor has not shut down and is rejecting a task due to saturation | Invokes the task's `run()` directly on the thread calling `execute()` |
| Executor has shut down | **Drops the task**; does not run it and does not throw `RejectedExecutionException` |
| Pool has room and `execute()` accepts the task normally | Handler is not called; the task runs via the normal worker/queue path |

You can picture the typical branching logic:

~~~java
// Conceptual model of rejectedExecution(), NOT a
// recommendation to reimplement the JDK library code.
if (!executor.isShutdown()) {
    runnable.run(); // runs on the very thread that called execute()
}
// When shut down: do nothing.
~~~

Key points to emphasize:

- `CallerRunsPolicy` does not create a new worker thread.
- It does not place the rejected task back into the queue.
- It does not forward the task to another executor.
- It does not promise to always execute the task: **shutdown is a major exception**.
- When the task runs directly, the `execute()` call typically returns **only after `run()` finishes**. If `run()` throws an unchecked exception, that exception can propagate out on the caller thread.
- This policy does not automatically retry failed tasks, provide durable storage, or guarantee execution ordering relative to tasks already in the queue.

Why is it called **caller-runs**? The "caller" is whichever thread actually invoked `execute()` in that situation; it is not necessarily an HTTP request thread. In a batch producer, it could be a producer thread; in a worker submitting downstream work, it could be a worker of another pool or the current pool itself.

## 4. Backpressure: The Producer Is Forced to Work Instead of the Consumer

Suppose a producer calls:

~~~java
executor.execute(job);
createNextJob();
~~~

When the executor has capacity, `execute(job)` usually returns relatively quickly so the producer can keep generating work. When the pool is saturated and the handler is `CallerRunsPolicy`, `job.run()` executes directly on the producer thread. The producer **cannot reach `createNextJob()` until the job finishes**.

This is a time-based feedback mechanism: the submission rate drops naturally when the system lacks processing capacity. While the producer is busy running the job, pool workers can drain items from the queue, freeing space for subsequent submissions. The JDK describes this as a simple feedback control mechanism.

However, distinguish **slowing down a producer** from **limiting system-wide concurrency**:

- `maximumPoolSize=4` only caps the number of workers **the pool** can create; it does not prevent multiple request threads from running their own tasks concurrently via CallerRuns.
- If 30 request threads simultaneously submit to a saturated 4-worker pool, several request threads can run rejected tasks at the same time. **Total concurrently executing tasks can exceed four**.
- For CPU-heavy or database-connection-heavy tasks, this mechanism can shift overload onto the web thread pool and external dependencies. It is not an application-wide semaphore capping total tasks.

Thus CallerRuns applies backpressure to **the submission source** rather than acting as an absolute resource cap. When a global concurrency cap is needed, consider bounded admission, semaphores, or a durable queue with a fixed number of consumers.

## 5. Java 17+ Example Proving Caller Execution

We create a pool with only **one worker** and a queue capacity of **one task**. The first task holds the worker via a `CountDownLatch`; the second task occupies the queue slot. When the main thread submits the third task, `CallerRunsPolicy` must run that task directly on the main thread.

The example does not use `Thread.sleep()` hoping the pool saturates: latches deterministically establish the state. The example also tests the shut-down executor case.

**File `CallerRunsDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        CountDownLatch queuedFinished = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Worker is still waiting on releaseWorker so this job must sit in the queue.
            pool.execute(queuedFinished::countDown);

            Thread submittingThread = Thread.currentThread();
            AtomicReference<Thread> executedBy = new AtomicReference<>();
            List<String> order = new ArrayList<>();

            order.add("before");
            pool.execute(() -> {
                executedBy.set(Thread.currentThread());
                order.add("inCaller");
            });
            order.add("after");

            System.out.println("onCaller="
                    + (executedBy.get() == submittingThread));
            System.out.println("order=" + String.join(">", order));

            releaseWorker.countDown();
            if (!queuedFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued job did not finish");
            }
            System.out.println("queuedFinished=true");
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        // This policy silently drops tasks after the executor has shut down.
        ThreadPoolExecutor stopped = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        stopped.shutdown();
        AtomicBoolean ran = new AtomicBoolean(false);
        stopped.execute(() -> ran.set(true));
        Future<Integer> future = stopped.submit(() -> 42);

        System.out.println("shutdownTaskRan=" + ran.get());
        System.out.println("futureDoneAfterDiscard=" + future.isDone());
        future.cancel(false);
    }
}
~~~

Compile and run:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

**Stdout of a successful run:**

~~~text
onCaller=true
order=before>inCaller>after
queuedFinished=true
shutdownTaskRan=false
futureDoneAfterDiscard=false
~~~

Explanation:

1. `workerStarted.await()` only proceeds once the first worker has started and is waiting on `releaseWorker`.
2. The second task takes the sole queue slot because the worker cannot pull it yet.
3. The third task cannot enter the pool or queue, so `CallerRunsPolicy` executes it on `submittingThread` itself. Hence `onCaller=true`.
4. The sequence `before>inCaller>after` proves **`execute()` for the third task did not return before the task body completed**.
5. After `releaseWorker.countDown()`, the worker processes the second task, and `queuedFinished.await()` proves it completed.
6. On the other already-shut-down executor, `execute()` drops the task; `shutdownTaskRan=false`. `submit()` can still return an incomplete `Future` because the task wrapped inside `FutureTask` was dropped. We call `cancel(false)` so we do not leave behind a future that could be waited on forever.

**Why does `List<String> order` have no data race here?** Only the main thread modifies the list at the three points `before`, `inCaller`, and `after`: under the test condition, the third task body also runs on the main thread. Do not infer that `ArrayList` is thread-safe in general executor scenarios; in real code, use proper synchronization or a concurrent collection if tasks can run on workers.

An essential condition of the test is **not releasing `releaseWorker` before submitting the third task**. If the worker has time to take the second task off the queue, the policy may not trigger and the test will no longer exercise the caller-runs branch.

## 6. How Does CallerRunsPolicy Alter Latency?

### Latency of the submit Call

Let `T_submit` be the time from the start of `execute(task)` until it returns. When the pool has room, `T_submit` is close to the cost of checking/enqueuing or spawning a worker; **it does not include the full task execution time**. When `CallerRunsPolicy` triggers, the work happens on the caller, so:

~~~text
T_submit ≈ T_pool_check + T_direct_task
~~~

This is only an approximate model. `T_direct_task` also includes CPU time, I/O, lock waiting, GC, scheduling, and downstream calls. If the task is heavy or blocks, `execute()` can block for a very long time, even past the request's deadline.

### Impact on HTTP Requests

Suppose an API takes about 20 ms to validate and prepare a response, then submits a report-generation job taking roughly 400 ms to an executor.

- When the executor has capacity, the request can return a response indicating **accepted under the current contract** without waiting for the report to finish.
- When the pool saturates and caller-runs triggers, the request thread may spend an extra ~400 ms working before the submit call even finishes. Response latency can jump from tens of milliseconds to hundreds of milliseconds or higher.
- If the task calls an external DB or HTTP service, execution time can vary widely, driving p95/p99 up sharply under load.

The figures 20 ms and 400 ms are **illustrative examples of the mechanism**, not measurement guarantees or an additive timing law. If the HTTP client deadline expires while the caller is still working, the server may still burn resources after the client has stopped waiting.

**Important property:** this behavior typically appears **only during saturation**, so a system may look very fast in low-load tests and suddenly develop a long latency tail in production. Never measure only p50.

### Two Types of Latency to Distinguish

| Metric | When pool has space | When CallerRuns triggers |
| --- | --- | --- |
| Time spent in `execute()` | Usually short | Includes task execution time on the caller |
| Queue wait time of the rejected task | Other tasks may have to wait | The caller-runs task does not wait in that queue |
| Request response latency | Minimally impacted directly by task body if truly async | Can increase by the entire task duration |
| Rate at which producer submits new work | Can be fast | Slows down because the producer executes the task |
| Tasks running outside pool workers | Usually 0 | Can grow with the number of redirected callers |
| p95/p99 and ability to meet deadlines | Depends on queue and task | Risk of spiking right during overload |

## 7. Load and Backpressure Analysis Example

Suppose a service has `core=2`, `max=4`, queue capacity 8, and each job takes an average of 250 ms while occupying a worker. If all four workers are busy and the queue is full, the next task falls back to the caller; the producer must spend roughly that time processing it.

Under a simple idealized model, four workers each taking 250 ms per task can complete roughly 16 jobs/sec; this is **not a production forecast** because contention, I/O, jitter, and pool sizing dynamics exist. If upstream steadily pushes 80 jobs/sec, the backlog can fill quickly, forcing multiple callers to do work simultaneously.

This creates two simultaneous effects:

1. **Negative feedback on each caller's submission rate:** that request/producer does not submit again until the task it is running completes.
2. **Increase in total threads executing tasks:** when many callers exist, many tasks run outside the worker pool; overload can spill into HTTP threads, schedulers, or the database.

A producer running a sequential loop can be throttled well by CallerRuns. An HTTP server with hundreds of independent request threads can turn request threads into an unwanted source of extra parallelism. You must evaluate **caller topology**, not just pool configuration.

If you genuinely need fixed total concurrency, use a dedicated admission bound such as a semaphore/bounded queue, or move to an independent queue and fixed-size consumer workers.

## 8. Comparing CallerRunsPolicy with the Other Policies

`ThreadPoolExecutor` provides several standard `RejectedExecutionHandler` implementations:

| Policy | When saturated and not shut down | Notable impact |
| --- | --- | --- |
| `AbortPolicy` (default) | Throws `RejectedExecutionException` | Caller knows it was not accepted; can return an error or fallback |
| `CallerRunsPolicy` | Executes task on caller | No task lost to saturation in this branch, but stalls the caller |
| `DiscardPolicy` | Silently drops the task | Fast, but risks losing work without the system knowing |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting | Can lose already-queued tasks and break ordering expectations |

`CallerRunsPolicy` appears to avoid dropping jobs on **saturation**, yet has two caveats to consider: the task can fail directly on the caller, and on **shutdown** the policy **silently drops jobs**. Thus it cannot be used to guarantee "every job executes successfully."

For data that must be processed, `AbortPolicy` plus a durable queue/job table usually forms a clearer contract. For a sequential batch producer that can tolerate running tasks directly, `CallerRunsPolicy` is a practical, low-complexity tool.

## 9. Configuring CallerRunsPolicy in Spring

`ThreadPoolTaskExecutor` is Spring's adapter over `ThreadPoolExecutor`. You can supply a `RejectedExecutionHandler` to the executor via `setRejectedExecutionHandler(...)`.

**File `ReportExecutorConfig.java`**, used in a Spring Framework project with `spring-context`:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportExecutorConfig {

    @Bean(name = "reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.CallerRunsPolicy());

        return executor;
    }
}
~~~

This is a **Spring configuration class**, not a standalone `javac` program: it requires Spring dependencies and has no `main`. When managed as a Spring bean, the container initializes and shuts down the executor along with the application lifecycle. If you manually instantiate `new ThreadPoolTaskExecutor()` outside the container, you must call `initialize()` before use and `shutdown()` afterward.

With the configuration above, a bounded queue is essential so overload can occur as intended. If you set a massive queue capacity, `CallerRunsPolicy` may rarely trigger while tasks sit waiting for a long time.

### Dispatching Service

**File `ReportDispatchService.java`:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportDispatchService {
    private final TaskExecutor executor;

    public ReportDispatchService(
            @Qualifier("reportExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String reportId) {
        executor.execute(() -> generate(reportId));
    }

    private void generate(String reportId) {
        System.out.println("Generating report " + reportId);
    }
}
~~~

`dispatch` here does not promise to always return quickly. When the pool has capacity, the task usually runs on a worker; when CallerRuns triggers, **`generate(reportId)` runs directly on the thread calling `dispatch`**, and `dispatch` returns only after that work finishes. When the pool has shut down, the task can be dropped while `dispatch` still returns normally.

Do not use the console-printing example above as a real job persistence/recovery mechanism. In real business applications, use a job ID, persisted state, idempotency, and proper error handling if work must not be lost.

### Using Together with `@Async`

If a method is annotated with `@Async("reportExecutor")`, Spring routes the call through the named executor. However, when the handler is `CallerRunsPolicy` and the pool is saturated, **the async task wrapper can run synchronously on the caller thread**. Therefore:

- Treat `@Async` as a request to dispatch work through an executor, not a hard guarantee that the body **always** runs on another thread.
- If the caller is a request thread, the request may wait for the body to execute, lengthening response time.
- Under default proxy mode, `@Async` does not intercept self-invocation within the same bean.
- For methods returning `Future`/`CompletableFuture`, account for both completion and exceptions; if a task is discarded during shutdown, a future from JDK submission may never complete without cancellation or a timeout.
- `@Async void` has its own internal error path via `AsyncUncaughtExceptionHandler`; do not treat this handler as a general solution for all submission-time errors.

In a Spring Boot application, attach the handler only to the specific executor where it is desired. Do not assume every `@Async` or every async HTTP handler selects this bean; when needed, specify the bean via qualifier and verify proxy invocation paths.

## 10. Task Exceptions and Rejection Errors Are Different

### When Using execute(Runnable)

If the pool saturates and uses `AbortPolicy`, the handler throws `RejectedExecutionException`; through Spring's `ThreadPoolTaskExecutor`, this error is usually translated to `TaskRejectedException` at the submission boundary. The caller can catch it and return an overload error.

If the pool saturates and uses `CallerRunsPolicy`, the handler invokes `Runnable.run()` itself on the caller. If the body throws a `RuntimeException`, that exception can escape directly from `execute()` on the calling thread.

~~~java
// Illustrative code inside a method with an appropriate executor.
// If the handler runs the Runnable directly on the caller, the exception
// can reach this execute() call itself.
executor.execute(() -> {
    throw new IllegalStateException("Report generation failed");
});
~~~

Therefore, you must distinguish:

- **Task was not accepted:** the handler reacted to saturation or shutdown.
- **Task executed but failed:** the `run()` body threw an exception in its execution environment.

With `CallerRunsPolicy`, those two situations can merge into the same call stack, yet their business meanings remain different. Do not catch every `RuntimeException` and conclude "the pool is full."

### When Using submit(Callable/Runnable) and Future

In the JDK, `ExecutorService.submit` typically wraps work in a `FutureTask`. If CallerRuns triggers when the pool saturates, `FutureTask.run()` itself runs on the caller: `submit` may take a long time to return the `Future`, and the Future is often already completed once the work finishes. Errors from `Callable` are captured inside the Future so `get()` reports them via `ExecutionException`; they are not necessarily thrown directly from `submit`.

However, when the executor **shuts down**, `CallerRunsPolicy` **drops the `FutureTask`** without cancelling the Future. Hence `submit()` can return a Future still in a pending state; if the caller invokes `get()` without a timeout, it can block forever.

Safer practices when the environment may shut down:

- Do not rely on `CallerRunsPolicy` for reliable notification about job admission during shutdown.
- When you need a "report error if not accepted" contract, prefer `AbortPolicy` or a custom handler that throws an explicit exception.
- When using Futures, apply appropriate deadlines/timeouts and cancellation; a timeout only keeps the waiter from hanging and does not prove the job never executed.
- Do not immediately retry tasks with side effects without a job ID, idempotency key, or confirmed status.

`CompletableFuture.runAsync(task, executor)` must also be evaluated against the passed executor: if the handler runs inline, creating/scheduling the future can execute the body immediately; if it drops the task on shutdown without error, completion may never arrive. This is not an API replacement for a durable queue.

## 11. Thread Context Changes: A Critical Issue in Spring

When a task runs on a worker thread, many values bound to the calling thread **do not automatically transfer**. When running via `CallerRunsPolicy`, the task reuses **the calling thread itself**. This discrepancy can expose bugs that appear only under overload.

### Transactions and Thread-Bound Resources

In Spring, many transaction contexts are bound to the executing thread. Suppose a controller/service is inside a transaction and calls `execute()`:

- While capacity remains, the task on a worker usually does not inherit the sender thread's transaction.
- When CallerRuns triggers, the task can execute **on the thread holding the current transaction**. It may see thread-bound state or interact with thread-bound resources differently than during worker execution.
- The exact same code can exhibit two different behaviors depending on load, which is very hard to test and operate.

Do not assume a task dispatched through an executor is always isolated from the request/transaction. For business data updates, define clear transaction boundaries and durable write points. Use a transactional outbox or post-commit hooks when consistency requirements demand it.

### SecurityContext, MDC, and ThreadLocal

Values such as security principals, trace IDs, or MDC logging may be stored in `ThreadLocal`. Pool worker threads may need a `TaskDecorator` or proper context propagation to receive the right data. Yet when CallerRuns occurs, the task sees the caller's context directly.

This leads to two classes of bugs:

1. Tasks running on workers lack context they expected.
2. Tasks running on callers unexpectedly read or mutate request context when the original design never anticipated it.

Avoid relying on implicit `ThreadLocal` state for business logic or authorization. Pass required data via parameters, define security context scope clearly, and test both worker and caller paths.

### Thread Names, Blocking, and Event-Loops

`setThreadNamePrefix("report-")` only names **pool workers**. When CallerRuns triggers, logs may show names like `http-nio-8080-exec-...` or another caller-owned thread name instead of `report-...`. Do not rely on thread prefixes to prove a job did or did not run.

In Spring MVC (Servlet), the caller may be a request processing thread: running a long job ties up a request-serving thread. In reactive applications using an event-loop, calling an executor with CallerRuns from the event-loop to run blocking tasks can severely degrade many requests. Even with virtual threads, running directly still increases the caller's completion time and requires understanding resource impact.

## 12. Reentrancy, Locks, and Deadlock Risks

CallerRuns turns rejected work into **a nested function call inside `execute()`**, so any state or locks held by the caller remain held while the body runs.

Potential hazards:

- Caller holds a lock; the inline task runs and waits on another worker that needs that lock → deadlock or stall.
- Caller creates a latch/future intending to release or signal it on lines **after `execute()`**, while the inline task waits for that signal from the caller → the same thread blocks itself.
- A task submits more tasks into the same saturated executor; nested tasks also run on the caller, potentially creating deep recursive call chains or reordering side effects.
- Code assuming "cleanup/commit/permit release runs right after `execute`" may be delayed because `execute` is busy running a heavy task.

Conceptual **anti-pattern example**:

~~~java
CountDownLatch ready = new CountDownLatch(1);
executor.execute(() -> {
    try {
        ready.await();  // dangerous if the task hits CallerRuns
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
});
ready.countDown();      // unreachable if execute waits forever
~~~

This is an **illustrative snippet inside a method**, not a standalone program. Under overload, the task can run inline and wait for `countDown()` after the `execute()` call, creating a deadlock. During worker execution, this path works, hiding the bug in low-load tests.

If using CallerRuns, design tasks to be **independent of the caller after submission**, avoid waiting on the caller, avoid holding long locks, and bound recursion.

## 13. Shutdown Is a Blind Spot That Can Lose Work

By JDK contract, `CallerRunsPolicy` executes only when the executor **has not shut down**. Once shut down, the handler drops tasks without throwing an exception. This is especially hazardous during:

- Rolling deployments or when `ApplicationContext` is closing.
- Requests arriving right as the application stops accepting work.
- A producer continuing to submit work after the executor has closed.
- Jobs that must be processed yet live only in RAM or an internal queue.

The Java example above checked both `shutdownTaskRan=false` and `futureDoneAfterDiscard=false`, showing that **`execute`/`submit` returning normally is insufficient proof that work ran or will run**.

For jobs requiring guaranteed execution:

1. Persist the request in durable storage with a job ID and status.
2. Return "accepted" under the contract only when durable persistence actually succeeds.
3. Have workers pull work from that store as capacity allows, with bounded retries, backoff, dead-letter/failure states, and idempotency.
4. If the request cannot be accepted, return an explicit error response (e.g., HTTP 503 or 429 depending on cause).
5. Design drain/shutdown so accepted-but-unrun jobs are not lost.

In multi-replica systems, a `ThreadPoolExecutor` only manages threads of **a single JVM process** and cannot act as a shared durable queue.

## 14. Observing and Measuring CallerRuns in Production

If you measure only active threads and pool-completed task counts, you can **miss tasks executed directly on callers**. Those tasks are not regular worker tasks, so internal pool counters like `getCompletedTaskCount()` or `beforeExecute/afterExecute` hooks do not necessarily cover them.

Metrics to consider:

| Signal | Why it matters |
| --- | --- |
| Count of handler invocations hitting the caller-runs branch | Reveals how often work is actually shifted to callers |
| Total caller task execution time and p95/p99 distribution | Quantifies the latency cost imposed on requests/producers |
| Active workers, current pool size, queue size/capacity | Distinguishes full queues from other misconfigurations |
| Request latency, timeouts, in-flight request count | Detects overload spilling over into HTTP |
| Job wait time, execution duration, job failures | Avoids confusing queue delay with body execution delay |
| Tasks dropped during shutdown | Detects silent job loss |
| CPU, GC, database connections, downstream saturation | Assesses total resource pressure when multiple callers run tasks themselves |

A custom handler can count and time caller-runs executions, while **preserving shutdown semantics** or intentionally replacing them with error-reporting semantics. The example below is an **illustrative snippet during executor configuration**, where `callerRunCount` is a `LongAdder` already initialized and registered as a metric per application design:

~~~java
executor.setRejectedExecutionHandler((task, pool) -> {
    if (pool.isShutdown()) {
        throw new java.util.concurrent.RejectedExecutionException(
                "Executor is shutting down");
    }
    callerRunCount.increment();
    task.run();
});
~~~

This snippet is **not pure `CallerRunsPolicy`**: it alters the shutdown contract by throwing an exception to prevent silent work loss. With Spring's `ThreadPoolTaskExecutor`, an exception from the rejection handler can be converted into `TaskRejectedException` when callers invoke Spring APIs. To measure duration, record `long start = System.nanoTime()` right before `task.run()` and record the metric in `finally`. Keep logging/metrics inside the handler lightweight; heavy I/O in the handler slows callers down even further.

### Do Not Conclude Concurrency From Pool Worker Counts Alone

For example, `pool.getActiveCount()==4` with `maximumPoolSize==4` does not mean only four tasks are running; five request threads might simultaneously be running five other caller-runs tasks. If you need total concurrency statistics, instrument at the task execution boundary itself using appropriate thread-safe counters.

## 15. Testing Must Cover Both Worker and Caller Paths

Tests that run only while the queue is empty miss many issues. A useful test suite covers:

| Scenario | What to verify |
| --- | --- |
| Pool has capacity | Task is picked up by a worker, not run inline just because `CallerRunsPolicy` is set |
| One worker held on a latch, queue full | Next task runs on the exact thread calling `execute()` |
| Caller-runs task takes a long time | Submission call returns only after the body finishes; caller latency rises |
| Caller-runs task throws unchecked exception with `execute(Runnable)` | Error can surface on the caller's call stack |
| `submit(Callable)` under saturation | Future can complete after body runs inline; exceptions follow Future semantics |
| Executor has shut down | New tasks are silently dropped per JDK `CallerRunsPolicy`; normal return is not treated as accepted |
| Multiple request threads submitting concurrently | Multiple caller-runs executions can occur simultaneously beyond pool worker limits |
| Submitting while holding a lock/transaction | No self-deadlock or divergent side effects between worker and caller paths |
| `@Async("reportExecutor")` under overload | Verify response time and target executor; do not assume another thread is always used |
| Graceful shutdown/restart | Jobs accepted under a durable contract are neither lost nor uncontrollably duplicated |

How to saturate a pool **without `Thread.sleep()`**: hold the worker with a latch, wait for `workerStarted`, submit a job to fill the queue, then submit the test job. Use timeouts only as safety guards so failed tests do not hang forever. Tests must release latches and shut down executors in `finally` so CI does not retain non-daemon workers.

In Spring, if you instantiate `ThreadPoolTaskExecutor` manually in an integration test, call `initialize()` and then `shutdown()`. When using a Spring bean, let the container own the lifecycle. When testing web responses, assert both status codes and deadlines under normal load and overload.

## 16. When Should You Use CallerRunsPolicy?

**Suitable scenarios:** a batch process with a **sequential producer**, short/time-bounded jobs, tasks safe to run on the producer itself, no locks creating producer dependencies, no need for thread-context isolation, and a clear shutdown strategy. CallerRuns can throttle queue insertion without complex machinery.

**Scenarios requiring careful thought:** Spring MVC request threads dispatching heavy jobs. CallerRuns strips requests of fast-response capability during saturation; users may hit timeouts precisely when the API is under peak load.

**Scenarios to avoid:** reactive event-loops submitting blocking tasks, work with side effects that must execute at most/exactly once, jobs needing durability across restarts, logic depending on thread-bound transaction context, or tasks waiting on a signal only the caller can provide.

### Selection Matrix

| System goal | Usually more appropriate choice |
| --- | --- |
| Sequential batch producer must self-throttle when downstream slows down | CallerRuns can fit if running the task on the caller is safe |
| API must meet deadlines and must not block on long jobs | Bounded executor + `AbortPolicy` + clear overload response |
| Guarantee jobs are not lost on shutdown or restart | Durable queue/job table and consuming workers, with idempotency |
| Cap total concurrent tasks including callers | Admission control, semaphore, or fixed consumer pool |
| Best-effort metrics data that can be dropped | Observable drop policy, if loss is explicitly accepted |
| Tasks requiring clear transaction/context boundaries | Design execution boundaries and context propagation independently of overload policy |

An overload policy should be **part of the application contract**, reviewed alongside latency and durability requirements. Never swap handlers simply because a benchmark showed higher throughput.

## 17. Common Mistakes

1. **Assuming `CallerRunsPolicy` is still always asynchronous.** The overload branch calls `run()` directly on the submitting thread.
2. **Assuming no exception means the task was definitely accepted.** On shutdown, this policy drops tasks without necessarily signaling an error.
3. **Setting a huge queue and expecting the policy to throttle.** Thousands of tasks may pile up before CallerRuns ever triggers.
4. **Thinking `maximumPoolSize` caps total running tasks.** Caller threads can run work concurrently outside the worker pool.
5. **Using it in latency-sensitive request handlers while testing only low load.** p95/p99 can spike once the queue fills.
6. **Running blocking tasks on a reactive event-loop.** Inline execution can block the event-loop, impacting many requests.
7. **Using `ThreadLocal`/transaction context without testing both branches.** Workers and callers have different execution environments.
8. **Signaling a condition after `execute()` that the task might wait on.** Risks self-deadlock during caller-runs.
9. **Failing to contain exceptions inside tasks.** `run()` can throw directly on the caller, failing the submission path unexpectedly.
10. **Relying solely on `getCompletedTaskCount()` to report total work.** Caller-executed tasks do not belong to standard worker stats.
11. **Calling unbounded `Future.get()` after submitting to a shut-down executor.** With CallerRuns, a dropped Future may never complete.
12. **Thinking the policy enforces global system-wide backpressure.** It slows each individual submitter, yet many submitters can still work in parallel.
13. **Attaching the policy to the wrong Spring executor.** Use qualifiers and verify `@Async`/TaskExecutor selects the intended bean.
14. **Directly retrying tasks with non-idempotent side effects.** Risks duplicate actions when callers or clients do not know the final outcome.
15. **Testing with arbitrary sleep durations.** Use latches to deterministically control busy workers and full queues.

## 18. Self-Check Questions

1. What condition causes `ThreadPoolExecutor` to invoke `RejectedExecutionHandler` instead of queuing the task?
2. Why do `onCaller=true` and `order=before>inCaller>after` in the demo show that `execute()` became synchronous with respect to task runtime?
3. With a pool of at most 4 workers and 20 request threads submitting simultaneously under saturation, can more than 4 tasks run at once? Why?
4. When the executor has shut down, how does `CallerRunsPolicy` handle new tasks? How does this affect `Future.get()`?
5. Why can an API's p95/p99 spike sharply under CallerRuns even when p50 barely changes?
6. If a task relies on a request's transaction, what risks arise from the difference between the worker path and the caller-runs path?
7. How can you test both the worker branch and the caller branch without using `Thread.sleep()`?
8. For a report-export requirement where jobs must not be lost, why is an in-memory queue with CallerRuns insufficient?
9. Why does `getActiveCount()` not reflect all running caller-runs tasks?
10. If you need both bounded concurrency and explicit overload feedback, would you choose CallerRuns or admission control + AbortPolicy? Explain in terms of deadlines and SLAs.

## 19. Official References

- [Java SE 17 — ThreadPoolExecutor.CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Remember:** `CallerRunsPolicy` shifts the execution cost of a rejected task onto **the submitting thread**, which slows down the producer but can also sharply increase request latency and spread load to other callers. Consider **deadlines, context, shutdown, observability, and zero-loss guarantees** before choosing this policy.