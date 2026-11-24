# DiscardPolicy, DiscardOldestPolicy, and the Risk of Losing Work

## 1. The Real-World Problem: Task Submitted Yet Never Executed

A Spring application can submit many kinds of work to a `ThreadPoolTaskExecutor`: sending emails, computing reports, refreshing caches, recording events, or handling background work via `@Async`. When tasks arrive faster than they can execute, the thread pool and queue can **saturate**. At that point, the executor must decide what happens to the newly submitted work.

Java's `ThreadPoolExecutor` defines rejection policies via `RejectedExecutionHandler`. Two policies that very easily cause data loss if misunderstood are:

- **`DiscardPolicy`**: silently drops the **newly rejected** task.
- **`DiscardOldestPolicy`**: while the executor is still active, removes the element at the **head of the waiting queue**, then **retries submitting** the new task; if the executor has shut down, drops the new task.

Both can cause the submitting code to **receive no exception**, while a task never runs. In particular, if the task was sent with `submit(...)`, the corresponding `Future` may **never complete and never be cancelled**. Thus a normal return from `execute` or `submit` **is not confirmation that the business task was processed**.

> For work that must complete or leave an audit trail of failure (payments, orders, inventory updates, mandatory notifications, tasks where someone awaits a Future), **do not choose a silent task-dropping policy**. Instead, apply explicit overload responses, ingress throttling, error tracking, and durable persistence when needed.

This lesson focuses on these two policies within the context of **Overload and Rejection** in Spring Framework, while explaining how to verify behavior with Java 17 and apply them safely with `ThreadPoolTaskExecutor`.

## 2. When Is a Task Rejected?

### 2.1. Relationship Between Threads, Queue, and Limits

A `ThreadPoolExecutor` relies on key parameters:

- `corePoolSize`: the core worker target the pool aims to reach as tasks arrive.
- `maximumPoolSize`: the upper limit on workers.
- `workQueue`: the queue holding work that has **not yet started**.
- `RejectedExecutionHandler`: the policy invoked when the executor cannot accept more tasks.
- Lifecycle state: running, shutting down, terminating, terminated.

General flow of `execute(task)`:

~~~text
New task arrives
    |
    v
Running workers < corePoolSize?
    | yes -> try creating a worker to run the task
    | no
    v
Try inserting task into workQueue
    | succeeds -> task waits for a worker
    | fails
    v
Can still create a worker up to maximumPoolSize?
    | yes -> try creating a worker to run the task
    | no / cannot accept
    v
RejectedExecutionHandler.rejectedExecution(task, executor)
~~~

This is an explanatory logic diagram, not a substitute for all state checks and race handling in the JDK source code. For example, a pool can reject a task because **it has shut down**, even when the queue is not full. Distinguish an executor that is saturated from one that no longer accepts work due to its lifecycle.

With `corePoolSize = maximumPoolSize = 1` and an `ArrayBlockingQueue` of capacity 1:

~~~text
Sole worker                 Queue capacity 1            Newly arriving task
┌──────────────────┐        ┌────────────────┐          ┌───────────┐
│ A is executing   │        │ B is waiting   │          │ C         │
└──────────────────┘        └────────────────┘          └───────────┘

A is busy, cannot create another worker, queue is full.
=> C is rejected and the policy is invoked.
~~~

We will use this exact configuration in our example to reproduce **deterministic** results without relying on thread-scheduling luck.

### 2.2. The Queue Determines How Saturation Happens

| Queue | Implications for rejection |
| --- | --- |
| `ArrayBlockingQueue<>(n)` | Bounded FIFO queue, imposing a clear cap on pending tasks; can fill up |
| `LinkedBlockingQueue<>(n)` | Bounded FIFO when capacity `n` is supplied; can fill up |
| `LinkedBlockingQueue<>()` without a small practical bound | Can hold a massive number of tasks, increasing latency/memory; `maximumPoolSize` rarely gets a chance to engage |
| `SynchronousQueue` | Holds no waiting tasks; must hand off directly to a worker or create one; at max workers, rejects immediately when all are busy |
| `PriorityBlockingQueue` | Queue head follows priority order, not necessarily arrival time; typically has no fixed bounded capacity |

Saying `DiscardOldestPolicy` drops the "oldest" work is **policy shorthand**; the actual operation takes **the element at the head of the queue** via `poll()`. With a FIFO queue, that is usually the longest-waiting task. With a priority queue or another ordering rule, the queue head **is not necessarily** the task that arrived earliest.

## 3. DiscardPolicy: Dropping New Work Without Reporting an Error

`ThreadPoolExecutor.DiscardPolicy` implements `RejectedExecutionHandler` by doing **nothing** when invoked.

~~~java
RejectedExecutionHandler policy =
        new ThreadPoolExecutor.DiscardPolicy();
~~~

This is a declaration snippet (requires importing types from `java.util.concurrent`). When a task is rejected:

1. The executor calls the handler.
2. The handler does not run, enqueue, forward the task elsewhere, or throw an exception.
3. The submission call can return normally, even though the task just submitted **is never executed**.

With the A/B/C diagram:

~~~text
Worker runs A
Queue holds B
submit C -> DiscardPolicy -> C is dropped
After A finishes: B runs, C does not run.
~~~

**Severe consequences:**

- **No clear success/failure signal at the submission point.** Not catching an exception cannot be treated as a sign that work was accepted.
- **Loss of business side effects.** If the task was supposed to write to a database, send an email, or emit an event, that effect may never happen.
- **No default loss log or metric per dropped task.** Operators may only notice sluggish behavior or missing results.
- **With a `Future` from `submit`**, the `FutureTask` of the dropped task usually stays **incomplete**: nobody calls `run()`, `cancel()`, or `complete` on it.
- **`get()` without a timeout can wait forever** if nothing else cancels the Future or interrupts the waiting thread.

`DiscardPolicy` is only suitable when **explicitly designed for loss-tolerant tasks**, where nobody waits for task completion, and with a plan to observe and bound the drop rate. For example, a **non-critical cache refresh** where a subsequent cycle will re-sync anyway, provided the task and service contract genuinely permit skipping. Even then, track drop metrics and ensure cache consistency.

## 4. DiscardOldestPolicy: Saving New Work by Dropping Queued Work

Conceptually, `ThreadPoolExecutor.DiscardOldestPolicy` behaves as follows:

~~~java
// Illustrates core logic; not a complete copy of JDK source.
if (!executor.isShutdown()) {
    executor.getQueue().poll();  // drops queue head without notifying Future owner
    executor.execute(newTask);   // retries executing or enqueuing the new task
}
// If already shut down: the new task is dropped.
~~~

With a worker running A, queue holding B, and task C arriving:

~~~text
Before:
  RUNNING: A
  QUEUED : B
  NEW    : C

C is rejected.
DiscardOldestPolicy:
  1. Queue.poll() drops B.
  2. Retry execute(C).

After (assuming retry succeeds):
  RUNNING: A
  QUEUED : C
  DROPPED: B
~~~

When A finishes, C runs. **B is no longer in the queue and will never run**, even though B had been accepted into the queue earlier.

It is important to understand accurately:

- The policy does not cancel the running task A; it **only removes the head element from the waiting queue**, if one exists.
- The policy **does not guarantee the retry succeeds**. Races with other producers or a shutdown transition can cause the retry to be rejected as well. The JDK warns that retrying can continue to loop.
- When the executor has shut down, the policy **drops the newly rejected task**, without necessarily pulling anything from the queue.
- If using a queue **that holds no waiting elements**, such as `SynchronousQueue`, there is no "oldest waiting task" to poll. The retry can keep failing; do not use this policy assuming it always frees a slot.
- If the queue is **not FIFO**, `poll()` removes the head according to the queue's ordering rules, which is not always the task with the oldest timestamp.
- If task B is a `FutureTask` created by `submit`, **polling it from the queue does not automatically `cancel` that Future**. A caller holding B's Future can wait forever.

This is especially dangerous if the business treats "the job was queued" as a guarantee that it will be processed. When a new task arrives, the policy can **silently revoke that guarantee** for the older task without notifying whoever submitted it.

### 4.1. Why Is "Preferring Newer Work" Not Always Right?

Suppose:

- B is an order status update command.
- C is a temporary report export request.
- The pool is saturated when C arrives.

With `DiscardOldestPolicy`, task B can vanish from the queue even though it is more critical than C. The policy **knows nothing about business value, deadlines, job types, or retry counts**. It only operates on the queue structure.

To prioritize newer work, design **controlled admission/priority/cancellation rules** at the business layer. For example, separate workloads into distinct pools or queues, track task states, and report clearly when a job is superseded.

## 5. Comparing the Four Common JDK Policies

| Policy | When pool is saturated and still running | Does submitter know of rejection? | Primary risk |
| --- | --- | --- | --- |
| `AbortPolicy` (JDK `ThreadPoolExecutor` default) | Throws `RejectedExecutionException` | **Yes**, if caller handles the exception | If caller ignores the error or fails to retry/persist, the business still loses work |
| `CallerRunsPolicy` | Caller executes the task on the submitting thread itself | Usually runs synchronously instead of being dropped | Increases latency, blocks request/event threads; when shut down, this policy also drops tasks |
| `DiscardPolicy` | Silently drops the **new** task | **No** | New task disappears, Future may hang |
| `DiscardOldestPolicy` | Drops the **queue head** then retries submitting the new task | **No feedback guarantee** about the evicted task | Already-**queued** task disappears, older task's Future may hang |

No policy automatically makes work durable across a process crash. `AbortPolicy` merely makes rejection **visible at the caller**; the caller still must decide whether to retry, return an HTTP error, persist to a durable queue, or apply backpressure. `CallerRunsPolicy` slows down producers in some cases, yet can introduce new problems if the caller is a latency-sensitive thread.

## 6. Standalone Java 17 Program Reproducing Work Loss Deterministically

This example **runs standalone on Java 17**, without Spring/Gradle. It controls pool state using `CountDownLatch` so one worker is busy, the queue holds exactly one task, and then a third task is submitted. This clearly demonstrates the difference between the two policies.

Create file `RejectionLossDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class RejectionLossDemo {

    public static void main(String[] args) throws Exception {
        runCase("DiscardPolicy",
                new ThreadPoolExecutor.DiscardPolicy());
        runCase("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy());
    }

    private static void runCase(
            String label,
            RejectedExecutionHandler handler) throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,                              // corePoolSize
                1,                              // maximumPoolSize
                0L, TimeUnit.MILLISECONDS,       // keepAlive
                new ArrayBlockingQueue<>(1),    // only one waiting task
                handler);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            // Task A starts running and is intentionally blocked.
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Task B takes the sole slot in the queue.
            Future<String> queued = pool.submit(() -> "queued");

            // Task C arrives when 1 worker is busy and queue is full.
            Future<String> incoming = pool.submit(() -> "incoming");

            // Before releasing A, no worker pulls B/C from the queue.
            System.out.println(label + ": queued in queue=" +
                    pool.getQueue().contains(queued));
            System.out.println(label + ": incoming in queue=" +
                    pool.getQueue().contains(incoming));

            release.countDown();
            running.get(5, TimeUnit.SECONDS);

            Future<String> kept = label.equals("DiscardPolicy")
                    ? queued : incoming;
            Future<String> dropped = label.equals("DiscardPolicy")
                    ? incoming : queued;

            System.out.println(label + ": result=" +
                    kept.get(5, TimeUnit.SECONDS));
            System.out.println(label + ": dropped done=" +
                    dropped.isDone());

            // Demo cleanup; neither policy cancels the dropped Future itself.
            dropped.cancel(false);
            System.out.println(label + ": dropped cancelled=" +
                    dropped.isCancelled());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run:

~~~bash
javac RejectionLossDemo.java
java RejectionLossDemo
~~~

**Exact stdout** of the program when both runs complete normally:

~~~text
DiscardPolicy: queued in queue=true
DiscardPolicy: incoming in queue=false
DiscardPolicy: result=queued
DiscardPolicy: dropped done=false
DiscardPolicy: dropped cancelled=true
DiscardOldestPolicy: queued in queue=false
DiscardOldestPolicy: incoming in queue=true
DiscardOldestPolicy: result=incoming
DiscardOldestPolicy: dropped done=false
DiscardOldestPolicy: dropped cancelled=true
~~~

Why are these lines predictable?

1. `started.await(...)` holds main until the worker begins A; A waits on `release`.
2. There is only **one** worker and **one** queue slot, so B sits in the queue when C is submitted.
3. With `DiscardPolicy`, B remains in the queue; C does not enter the queue.
4. With `DiscardOldestPolicy`, B is removed by `poll()` from the queue; C is placed into the freed slot.
5. After releasing A, the retained task runs and `Future.get(...)` returns the corresponding string `queued` or `incoming`.
6. `dropped.isDone()` is `false` even after the retained task completes: the policy neither invokes `run` nor `cancel` on the discarded `FutureTask`.
7. The example calls `cancel(false)` **manually** for cleanup; this proves the Future transitions to cancelled only due to application code, **not due to the policy**.

Do not use `dropped.get()` without a timeout in this program: it could wait forever. With real asynchronous tasks, `get(timeout, unit)` can bound wait time, though **a timeout does not recover lost work**.

### 6.1. What If Submitting a Runnable via execute(...) Instead of submit(...)?

`execute(Runnable)` does not create a Future to return to the caller. With `DiscardPolicy`, the call can return normally even though the Runnable never runs; the caller has no Future to detect that state. `submit(...)` returns a Future, yet the Future may never complete. Therefore, both **no exception** and **having a Future** are not equivalent to "the task is guaranteed to be processed."

Note that `Future.isDone() == false` at an arbitrary moment **does not by itself prove a task was dropped**; it could simply be waiting or running. The example above sets up deterministic conditions to know a task was dropped based on worker/queue state and the configured policy.

## 7. Applying to Spring ThreadPoolTaskExecutor

Spring's `ThreadPoolTaskExecutor` wraps `ThreadPoolExecutor`, allowing configuration of core/max pool, capacity, threadNamePrefix, and `RejectedExecutionHandler`. On the Spring interface side, when the underlying executor **throws** `RejectedExecutionException`, `ThreadPoolTaskExecutor` normally converts it to `TaskRejectedException` per the `TaskExecutor` contract.

However, if **the handler silently drops the task without throwing an exception**, Spring cannot automatically know work was lost just from the handler returning normally. An application using `@Async` or `submit` may receive no rejection signal at the call site, while the associated Future/CompletableFuture stays incomplete if execution was dropped.

Here are two configurations **solely to illustrate the risk**, not recommended for mandatory business work:

~~~java
// Inside a @Configuration class, with imports for @Bean,
// ThreadPoolTaskExecutor, and ThreadPoolExecutor.
@Bean("lossyExecutor")
public ThreadPoolTaskExecutor lossyExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("lossy-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.DiscardPolicy());
    return executor;
}
~~~

Changing `DiscardPolicy` to `DiscardOldestPolicy` allows the executor to drop **already waiting** work to admit new work. Even when naming the bean `lossyExecutor`, only call paths that actually select that bean are affected. For example:

~~~java
// Illustrated in another Spring bean, with @EnableAsync enabled.
@Async("lossyExecutor")
public CompletableFuture<String> generateReport() {
    return CompletableFuture.completedFuture("ready");
}
~~~

The configuration above applies only when the call is intercepted by the Spring proxy and dispatched to the right executor. Self-invocation inside the same bean (`this.generateReport()`) can bypass `@Async` under default proxy mode. Nor should you assume controllers, schedulers, event listeners, Spring Batch, or Integration automatically use `lossyExecutor`: each integration point has its own executor-selection configuration.

### 7.1. A Safer Default Configuration

For most work where silent loss is unacceptable, choose an **explicit error-reporting** strategy:

~~~java
@Bean("importantExecutor")
public ThreadPoolTaskExecutor importantExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("important-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    return executor;
}
~~~

This is also a Spring configuration snippet, not enough to run standalone. `AbortPolicy` lets the submit path know when the pool refuses a task; **it does not retry or persist the task to storage itself**. The application must handle it appropriately. Especially when using `@Async`/Future, test how errors surface at the proxy and caller boundaries in your framework version.

In a Spring Boot application, there may be a `TaskExecutor` created by auto-configuration. Declaring multiple executors can alter default bean selection rules. For critical work, **specify an explicit qualifier or wiring** rather than trusting some arbitrary executor to be picked.

## 8. Boundaries of "accepted", "running", "done", and Work Durability

A common design mistake is collapsing four distinct states into "submitted":

| State | Definition | Guaranteed when execute/submit returns? |
| --- | --- | --- |
| **Accepted** | Executor actually holds the task or is running it | With silent-drop policies: **cannot be inferred** from the absence of an exception |
| **Running** | A worker has begun processing | No; the task may still sit in the queue |
| **Completed** | Task finished; result or error recorded | No; requires proper result/Future/log/ack |
| **Durably recorded** | Work saved somewhere that survives restarts/crashes | No; an in-memory thread pool is not a durable queue |

These two policies are particularly dangerous when callers receive HTTP `202 Accepted` or save status `"PROCESSING"` immediately after submit without reliable confirmation that the task was admitted. An executor can silently drop the task or evict an older task afterward, leaving users seeing the job "processing" forever.

If an application truly promises to process work, **persist the job in a database/outbox or durable broker**, then have consumers/workers pull and process it with clear retry, deduplication, and failure-state strategies. `ThreadPoolTaskExecutor` can serve as the resource running workers, yet **never serves as durable storage**.

### 8.1. Why Doesn't Future Solve Task Loss Automatically?

When calling `ExecutorService.submit`, a `RunnableFuture` (typically `FutureTask`) is created and submitted to the executor. Only when a thread executes the task, or someone calls cancel, does the Future reach a terminal state. If a policy drops the task without running or cancelling it, **the Future can stay pending forever**.

Practical consequences:

- `future.get()` without a timeout can block indefinitely.
- `future.get(3, TimeUnit.SECONDS)` can throw `TimeoutException`, yet that is a **wait timeout**, not proof of whether the cause was being dropped or running too long.
- `CompletableFuture.join()` can also wait indefinitely if the future never completes.
- `CompletableFuture.orTimeout(...)` times out the future's result, but does not re-run or complete business side effects.
- With `DiscardOldestPolicy`, the Future of a task **that was previously accepted into the queue** can get stuck after the task is replaced. This hazard is harder to observe than immediate rejection at new submission time.

Do not assume `shutdown()` or `shutdownNow()` will **automatically complete every Future** that a handler already threw away. A Future previously evicted from the queue may no longer be visible to the executor at all.

## 9. Alternatives and Designing Against Unintended Work Loss

### 9.1. Surface Rejection Errors Immediately at the Producer

For tasks that cannot be dropped, use a throwing handler (typically `AbortPolicy`), catch the error at the submission boundary, and decide:

- Return **429** when enforcing client rate limits, or **503** when the service is overloaded, along with appropriate retry metadata for HTTP.
- Retry **with bounds** using exponential backoff and jitter, only when the operation is safe to retry.
- Persist the task to durable storage for later reprocessing.
- Apply a bounded admission queue, semaphore, or rate limit **before** calling the executor to avoid generating excessive work.

Do not retry endlessly right on the request thread when the pool is saturated. Unbounded retries can choke the very threads needed to clear overload. For tasks with side effects, define **idempotency** to prevent duplicate execution when the caller does not know how far a prior attempt got.

### 9.2. CallerRunsPolicy: Backpressure With Consequences

`CallerRunsPolicy` lets the thread calling `execute` run the work itself when the pool saturates (if the executor has not shut down). This can throttle producers because the producer blocks until the task finishes, acting as a form of **backpressure**.

However, if the caller is an HTTP request thread, message listener, or scheduler thread, heavy work can raise latency, block I/O, or delay schedules. When the executor has shut down, `CallerRunsPolicy` can also **drop** new tasks per its contract. Therefore, evaluate the call path rather than treating CallerRuns as a zero-loss guarantee across all states.

### 9.3. If Dropping Work Is Permitted, Define the Drop Contract

Some workloads can tolerate **lossy execution**, such as:

- Telemetry events meant only for sampling and explicitly marked as droppable.
- Requests to refresh a temporary snapshot where the newest version supersedes older ones.
- Non-critical UI preview updates where the user only needs the latest result.

Even in these cases, **DiscardOldestPolicy does not understand keys or data versions**. Evicting the queue head can drop a task more important than the incoming one. If you want "keep the latest version per key," design an intentional **coalescing queue/last-value-wins mechanism** instead of assuming DiscardOldest provides that contract.

Define the maximum acceptable loss, metric recording, caller communication, and recovery behavior. If anyone is waiting on a task's Future, dropping it must **complete the Future with an observable cancellation/error**; merely removing it from the queue is not enough.

### 9.4. Custom Handler When Every Rejection Must Be Recorded

A small, controllable example is a custom handler that **records a metric and throws an error**, never silently losing work. The snippet below belongs in a configuration class with an executor bean and an `AtomicLong` counter; it is not a standalone Spring application:

~~~java
AtomicLong rejected = new AtomicLong();

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(2);
executor.setQueueCapacity(50);

executor.setRejectedExecutionHandler((task, pool) -> {
    rejected.incrementAndGet();
    throw new RejectedExecutionException(
            "Important task rejected: executor overloaded or stopped");
});
~~~

Requires importing `AtomicLong`, `RejectedExecutionException`, and `ThreadPoolTaskExecutor`. In real applications, use a proper metrics registry, distinguish `shutdown` from `saturation`, rate-limit logging, and include clear error codes; never log sensitive payloads, tokens, or user data.

If the business genuinely needs to evict queued tasks and favor new ones, the handler must **record the evicted task, cancel its Future if present, decide sensible retry logic, handle empty-queue/shutdown cases, and propagate status to the caller**. The Javadoc of `DiscardOldestPolicy` even gives an example checking whether the polled task is a `Future` to call `cancel(false)`. Even so, a handler that calls `execute` again must still account for races and repeated rejections; do not copy queue-replacement logic into production without concurrency and business-contract testing.

## 10. Observing Work Loss and Testing

### 10.1. Operational Metrics to Have

Besides active thread count, queue size, execution time, and wait time, measure:

- **tasks_submitted**: count of tasks producers attempted to send.
- **tasks_accepted**: count of tasks with real proof of admission under the system contract.
- **tasks_started/completed/failed**: recorded at execution time or in the job management system.
- **tasks_rejected/dropped/replaced**: recorded accurately in the admission/rejection policy and whenever tasks are intentionally superseded.
- **task_age / oldest_queue_wait**: helps spot backlog buildup before the queue fills.
- **Future timeout, cancelled, still pending**: investigates work that never produces a result.

`ThreadPoolExecutor.getCompletedTaskCount()` does not replace a reliable loss counter; it counts tasks completed by workers and does not explicitly report Runnables silently dropped by a policy. Counting "submitted" tasks at the producer alone also cannot separate accepted from dropped. Instrument at the exact business boundaries.

### 10.2. Controlled Testing

Tests should pin down state (like `CountDownLatch` in section 6), then verify:

1. Which task is on the worker, which is in the queue, and which just arrived.
2. Whether the policy ran under saturation or shutdown.
3. Whether the new task or the old task was dropped.
4. Whether the caller received an exception, a cancelled Future, or a failure status.
5. After shutdown and restart, whether mandatory work is recovered.
6. Under multiple concurrent producers, whether races occur when a handler polls/retries itself.

When testing with `DiscardPolicy` or `DiscardOldestPolicy`, **never call unbounded `Future.get()` without a timeout** on tasks that might be evicted. Bound wait times, assert exact states, and clean up via cancel and shutdown so tests never hang. Passing once does not prove concurrency safety across all interleavings; combine semantic analysis with bounded stress tests.

## 11. Reasoning Pitfalls to Avoid

| Misleading statement | Truth |
| --- | --- |
| "No RejectedExecutionException thrown means the task was accepted." | Handler may drop the task silently; no exception is not an ACK |
| "DiscardPolicy only slows processing under overload." | It **drops new work**, without waiting or retrying |
| "DiscardOldestPolicy drops the longest-running task." | It calls `poll()` on the **waiting queue head**, not cancelling a running worker |
| "DiscardOldestPolicy guarantees the new task is accepted." | It **retries**, and can still fail/reject again or hit executor shutdown |
| "submit returning a Future means a result will arrive." | The Future can stay pending forever if the task is dropped without cancellation |
| "Future.get(timeout) automatically reruns a lost task." | Timeout only bounds waiting; it never recovers side effects |
| "Spring @Async always reports an error if the pool drops work." | If the handler throws no exception, integrations receive no clear rejection signal |
| "A small queue plus large max threads prevents overload." | Submission rates can still exceed processing capacity and saturate |
| "DiscardOldest keeps the more important work." | The policy knows nothing about business meaning, only the queue head |
| "An in-JVM pool guarantees processing across restarts." | An in-memory executor is not a durable job store |

## 12. Self-Check Questions

1. A pool has one worker running A, a queue of capacity one holding B, and task C arrives. Which task does `DiscardPolicy` drop? **C**, the newly rejected task.
2. In the same scenario, which task does `DiscardOldestPolicy` normally drop? **B** at the head of the queue; then it retries submitting C.
3. With `DiscardOldestPolicy`, is the running task A cancelled? **No**, the policy only operates on the waiting queue.
4. Why can B's `Future` hang after B is polled? **Because B is never executed and the policy neither calls `cancel` nor completes the Future.**
5. If the queue is a `SynchronousQueue` with no waiting element, can you trust `DiscardOldestPolicy` to free up space? **No**; there is no queued task to poll, and the retry can keep being rejected.
6. Does `AbortPolicy` guarantee tasks get processed under saturation? **No**; it only turns rejection into an exception for the caller to handle.
7. A task is submitted via `@Async` to a `ThreadPoolTaskExecutor` using `DiscardPolicy`. Can you conclude the Future is guaranteed to complete? **No**; a dropped task can leave result waiting unfinished forever.
8. When is dropping tasks acceptable? **Only when the business contract explicitly allows loss, with observability and a way to resolve/cancel waiters when needed.**
9. If a payment job must be processed even across application restarts, is switching from DiscardPolicy to CallerRunsPolicy enough? **No**; you need durable job persistence/coordination and idempotency design.
10. If the queue is a priority queue, is the task removed by DiscardOldest guaranteed to be the earliest-arriving one? **No**; the head is determined by queue ordering.

**Conclusion:** `DiscardPolicy` can make **new work** disappear; `DiscardOldestPolicy` can make **already-queued work** disappear. With both, the danger lies in losing work **without an adequate signal**, causing missing results, hanging Futures, and systems mistakenly believing work was accepted. For business logic that cannot lose tasks, choose **explicit admission, observable rejection, backpressure, and durable work persistence** as required.

### Official References

- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java 17 — ThreadPoolExecutor.DiscardPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html)
- [Java 17 — ThreadPoolExecutor.DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
