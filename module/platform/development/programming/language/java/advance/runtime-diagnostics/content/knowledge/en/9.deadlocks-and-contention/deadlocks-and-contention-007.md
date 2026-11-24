# 9.7 Correlating Active, Completed, Rejected Tasks, and Queue Length

When a Java application shows signs of **hanging, timeouts, growing backlogs, or work rejections**, a thread dump reveals which stacks workers are currently on, yet it does not show how many tasks **have not reached a worker yet**, have already completed, or were rejected right at submission. A JVM might have only eight workers, all eight waiting on the database, while thousands of tasks sit queued. Looking only at CPU and `RUNNABLE` threads makes it very easy to miss the bottleneck.

In Java 21, **ThreadPoolExecutor** provides three direct observability groups: **active executing workers**, **completed tasks**, and the **current work queue**. Rejection counts, however, **have no standard getter**; the application or framework must instrument at the **RejectedExecutionHandler** or submission boundary. What is needed is **correlating metrics from the same executor, same process, and same time window**, then verifying with thread dumps, JFR, request traces, and downstream metrics.

Four core concepts:

- **Active/running:** number of workers currently executing a task. That task may be waiting on a lock, network, or Future; **active does not mean CPU is busy**.
- **Completed:** number of tasks that finished executing in pool workers since the pool was created; **completed does not mean business success**.
- **Rejected:** an event where a submission could not be accepted by the executor per its rejection mechanism. The handler may **throw, run on the caller, or drop the task**; callback count does not always equal lost requests.
- **Queued:** number of tasks sitting in the work queue not yet picked up by a worker. It differs from **upstream backlog**, active tasks, or wait duration.

This lesson belongs to **9. Deadlocks and Contention** in module **Java Advance - runtime-diagnostics**. Examples follow **Java SE 21**, focusing on **ThreadPoolExecutor**; certain frameworks, `ForkJoinPool`, `ScheduledThreadPoolExecutor`, and virtual-thread-per-task executors have different semantics and must be checked separately.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Read **getActiveCount(), getCompletedTaskCount(), getTaskCount(), getPoolSize(), getMaximumPoolSize()**, and **getQueue().size()**.
2. Distinguish **gauges**, **cumulative counters**, **deltas/rates**, and non-simultaneous snapshots.
3. Understand why looking solely at active workers, queue length, or exception counts can lead to wrong diagnoses.
4. Understand **AbortPolicy, CallerRunsPolicy, DiscardPolicy, and DiscardOldestPolicy**, including silent task loss.
5. Write a **RejectedExecutionHandler** with explicit counters, avoiding double counting and separating shutdown rejections from saturation.
6. Use two samples to compute **completion rate**, **rejection rate**, and **queue growth**, without assuming equations not guaranteed by the API.
7. Run a Java 21 lab with one active worker, one queued task, and one rejected task with deterministic stdout.
8. Identify **thread starvation deadlocks**, downstream waits, and CPU bottlenecks by combining executor metrics with thread dumps/JFR.
9. Distinguish bounded queues, unbounded queues, **SynchronousQueue**, delayed tasks, and virtual threads.
10. Build a production-ready inspection runbook that minimizes observer effects.

## 2. Lifecycle of a Task Through ThreadPoolExecutor

~~~text
Request / consumer / scheduler
              |
              v
       execute() or submit()
              |
      +-------+----------+
      |                  |
  Below core         Already has core workers
  workers?           -> try offering to queue
      |                  |
  Spawn worker           +----> Queue waiting for worker
      |                  |
      |               Queue rejects?
      |                  |
      |               If below max, spawn worker
      |                  |
      +------------------+
              |
          Worker executes task
              |
          Execution finishes
              |
       completedTaskCount increases

If already shut down or worker/queue cannot accept:
       RejectedExecutionHandler
          - Abort: throw
          - CallerRuns: caller executes when not shut down
          - Discard: drop task
          - DiscardOldest: drop oldest item, retry
~~~

Per Java 21 documentation:

- When worker count is below **corePoolSize**, the executor normally prefers creating a new worker.
- Once core workers exist, the executor prefers **enqueuing the task into the work queue**.
- If the queue cannot accept it, the executor may grow workers up to **maximumPoolSize**.
- If shut down or unable to accept, **RejectedExecutionHandler** handles it.

**MaximumPoolSize is not an automatic scaling target in every configuration.** For example, with a nearly unbounded work queue, tasks keep entering the queue and the pool may never grow past `corePoolSize`.

One **request** can spawn multiple `Runnable`s, or multiple requests can be batched into one task. Thus pool task count does not inherently equal HTTP requests, messages, or transactions.

## 3. Meaning and Limitations of the Getters

| API | Meaning | Classification | Limitations |
| --- | --- | --- | --- |
| **getCorePoolSize()** | Configured core worker count | Configuration | Not active count. |
| **getMaximumPoolSize()** | Worker count ceiling | Configuration | Does not guarantee the pool scales up to this. |
| **getPoolSize()** | Current number of workers | Gauge | Includes idle workers. |
| **getActiveCount()** | **Approximate** number of workers executing tasks | Gauge | Includes tasks blocked/waiting. |
| **getLargestPoolSize()** | Peak workers ever reached | Historical gauge | Does not reflect current busyness. |
| **getTaskCount()** | **Approximate** total tasks ever scheduled | Counter | Not synonymous with submission attempts. |
| **getCompletedTaskCount()** | **Approximate** total tasks workers finished | Counter | Not synonymous with business success. |
| **getQueue().size()** | Tasks in the queue when read | Gauge | Excludes active tasks or upstream backlog. |
| **getQueue().remainingCapacity()** | Remaining slots reported by queue | Gauge | Does not guarantee the next submit succeeds. |
| **getRejectedExecutionHandler()** | Currently configured handler | Metadata | Does not return total rejections. |
| **isShutdown()** | Pool no longer accepts new tasks as before | Lifecycle | Explains rejections during deploys. |
| **isTerminating()/isTerminated()** | Shutdown/termination progress | Lifecycle | Needed to separate slow pools from stopping pools. |

**getActiveCount(), getTaskCount(), and getCompletedTaskCount()** are documented by JDK 21 as **approximate**. Values can change right while you call each method. Never use a single read to assert exact pool-wide conservation equations.

### 3.1. Active Does Not Mean RUNNABLE or CPU Busy

If a worker executes a task and then calls **Future.get()**, waits on a database, or waits on a lock, the pool still counts it as **active**. Thread dumps may show that worker in **WAITING/BLOCKED**. Seeing `active=8/8`, rising queue, and low CPU usually points to checking **I/O waits, lock contention, dependencies, or thread starvation** before adding workers.

Conversely, if workers are `RUNNABLE` with high CPU, low completion rate may stem from CPU-bound work, busy loops, or GC/throttling. **Same `active=8`**, completely different cause and fix.

### 3.2. Completed Is Not Successful Requests

**getCompletedTaskCount()** increments when a task’s execution finishes in a worker. A task might:

- Return a valid result.
- Throw a `RuntimeException`/`ExecutionException`.
- Return a business error or HTTP 500.
- Be interrupted/canceled after starting and then exit.
- Return fast via fail-fast while the user’s request fails.

With **submit(Callable)**, exceptions are normally stored in the **Future**; execution finished so the pool still counts it as completed. Therefore **high completion rate** does not guarantee healthy business throughput. Measure **success, failure, timeout, and canceled** at the result layer.

### 3.3. TaskCount Is Not Submit Calls

**getTaskCount()** is an approximate total of tasks ever scheduled. It differs from **submitted attempts** when rejections, retries, `CallerRuns`, `DiscardOldest`, cancellations, or queue removals occur. If one HTTP request submits three tasks, `taskCount` grows by tasks, not by one request. A task rejected upstream at an API gateway is never seen by the executor.

Never name a metric **http_requests_total** from `getTaskCount`. Name it something like **executor_tasks_scheduled** and document how it is measured.

## 4. Queue Length: Seeing Pool-Level Backlog Accurately

Queue length only measures **items waiting in that specific executor’s work queue**:

~~~text
Accepted task in queue       -> counted in queue.size()
Task running in worker       -> counted in active, no longer queued
Request at gateway           -> not necessarily in the pool's queue
Message in broker            -> not necessarily in the pool's queue
Task running via CallerRuns  -> not in worker active/queue as usual
~~~

Example of a pool with 8 workers and queue capacity 100:

| State | Active | Queued | Interpretation Hint |
| --- | ---: | ---: | --- |
| Just idle | 0 | 0 | No overload visible in the pool. |
| Small burst | 8 | 5 | May be normal if the queue drains quickly. |
| Sustained slowdown | 8 | 75 | Workers may be processing too slowly relative to arrivals. |
| At capacity | 8 | 100 | New submissions may be rejected or run on caller. |
| Anomalous | 0 | 100 | Check worker creation, shutdown, queue semantics, and sampling. |

**One snapshot with queue=75 is inconclusive** because 75 tasks could drain in a few milliseconds. Track queue growth, time-in-queue, completion rate, and task duration.

### 4.1. SynchronousQueue: Queue 0 Can Still Be Saturated

**SynchronousQueue** hands off directly between producer and worker; it holds no backlog queue like `ArrayBlockingQueue`. **getQueue().size()** is typically 0 even when the pool is at max threads and rejecting tasks because no worker is free. **Queue=0 does not prove a healthy pool.**

### 4.2. Unbounded LinkedBlockingQueue: Rejected 0 Can Still Mean Overloaded

A typical **Executors.newFixedThreadPool(n)** uses a **LinkedBlockingQueue without a finite capacity**. If arrival rate exceeds completion rate over time, the queue grows without triggering rejections, causing long waits and memory pressure.

Hence **rejected=0 does not prove sufficient processing capacity**. With unbounded queues, fixes may include **bounded admission, timeouts, concurrency limits, and reducing retries** rather than waiting for an OOM.

### 4.3. Queue Utilization Only Applies to Explicit Bounded Queues

With `ArrayBlockingQueue` capacity=100 and queued=75:

~~~text
queue_utilization = 75 / 100 = 75%
~~~

Do not apply that calculation to **SynchronousQueue capacity=0**, unbounded queues, or delayed queues as if they were the same quantity. **remainingCapacity()** is a snapshot, not a reservation; multiple producers can compete for slots right after the reading is taken.

## 5. Rejection Policies Determine What Numbers Mean

**ThreadPoolExecutor has no getRejectedTaskCount()**. When unable to accept a task, the executor invokes the configured **RejectedExecutionHandler**. Rejections can happen due to **saturation or shutdown**.

| Java 21 Handler | Action | Measurement Consequence |
| --- | --- | --- |
| **AbortPolicy** | Throws `RejectedExecutionException`. | Task not accepted; exception is explicit. |
| **CallerRunsPolicy** | Caller runs the task directly unless the pool is shut down, in which case the task is dropped. | Handler invoked yet task may complete; pool completed count excludes caller executions. |
| **DiscardPolicy** | Silently drops the task. | Counting exceptions alone misses dropped tasks. |
| **DiscardOldestPolicy** | Drops head of queue and retries the new task if not shut down. | An older task is lost; callback count differs from lost task count. |

An undocumented **rejected_total** metric easily misleads. Distinct concepts include:

- **rejection_handler_calls_total**: total times the handler was invoked.
- **submission_exceptions_total**: total times callers caught `RejectedExecutionException`.
- **caller_runs_total**: tasks executed on the submitting thread.
- **dropped_tasks_total**: tasks actually dropped.
- **ingress_rejected_requests_total**: requests rejected upstream at a gateway/rate limiter.

**Do not sum these counters together** if one submission can increment multiple counters.

### 5.1. Simple Handler Instrumentation Example

~~~java
// Illustrative code, rejectedCallbacks is an AtomicLong outside this snippet.
RejectedExecutionHandler handler = (task, pool) -> {
    rejectedCallbacks.incrementAndGet();
    throw new RejectedExecutionException(
            "executor cannot accept task");
};
~~~

With this handler, a callback leads to an exception. Still, the **reason the handler was called** could be pool shutdown rather than saturation. Separating causes requires also checking **isShutdown()**, timestamps, and deployment events.

**Do not arbitrarily swap a production pool’s handler just to add a metric** if that changes semantics from `CallerRuns`/`Discard` to `Abort`. Use a behavior-preserving wrapper, framework integration, or ingress measurement.

### 5.2. CallerRunsPolicy Is Backpressure, Not Pure Failure

`CallerRunsPolicy` can throttle producers by making the **submitting thread** execute the task itself. However, if the caller is an **HTTP event loop, consumer poll thread, scheduler, or a thread holding a lock**, upstream latency and availability can degrade badly.

A dashboard showing only pool active/completed counts can miss CPU or wait time spent running tasks on caller threads. Track **caller_runs_total** and **time_spent_in_submit** to explain it.

### 5.3. Discard Can Create Infinite Future Waits

If the application calls **submit()** returning a **Future**, yet the policy silently drops the `Runnable`/`FutureTask`, a caller waiting on **Future.get()** may never receive completion. **DiscardOldestPolicy** can evict a queued Future without canceling it. Silent discards therefore risk **logical hangs** and missing business metrics.

Never use silent discards for tasks requiring results or acknowledgments without explicit lifecycle, cancellation, and deadline design.

## 6. Two Measurement Samples: Computing Completion Rate and Rejection Rate

**Active/queued** are gauges. **Completed/rejection-handler calls** are counters requiring a delta across two timestamps.

Suppose the same `ThreadPoolExecutor`, 30 seconds apart:

| Metric | t0 | t1 |
| --- | ---: | ---: |
| Active | 8 | 8 |
| Queue | 80 | 100 |
| Completed total | 2,400 | 3,000 |
| Handler calls total | 0 | 200 |
| Maximum workers | 8 | 8 |
| Queue capacity | 100 | 100 |

~~~text
completed delta  = 3000 - 2400 = 600
completion rate  = 600 / 30 = 20 tasks/s

handler delta    = 200 - 0 = 200
handler rate     = 200 / 30 ≈ 6.67 callbacks/s

queue delta      = 100 - 80 = 20
queue growth     = 20 / 30 ≈ 0.67 tasks/s
~~~

Reading: the pool is continuously busy, the queue grew to capacity, and the handler was invoked frequently. This signals saturation, **not yet proof of too few workers**, since task duration may have grown due to DB/lock/network delays.

Do not jump immediately to:

~~~text
arrivalRate = completedRate + handlerRate + queueGrowthRate
~~~

because the handler may be `CallerRuns`, tasks may be canceled/dropped, requests differ from tasks, counters have different scopes, and measurements are non-simultaneous.

### 6.1. Counter Resets and Clocks

For time-series metrics:

- Tag with **instance, process start time, and executor identity**; when the JVM/pool restarts, counters reset.
- Never compute ordinary negative deltas when `t1 < t0` due to a reset.
- Use actual elapsed time between samples; scrape intervals can jitter.
- **System.nanoTime()** suits elapsed measurements within the same JVM; wall clocks help align across machines.
- If pool config changes between `t0`/`t1`, record core/max/capacity and deployment events.

### 6.2. Runnable Java 21 Rate Calculator with Deterministic Stdout

**File PoolRateMath.java:**

~~~java
import java.util.Locale;

public final class PoolRateMath {
    record Sample(
            long timeNanos,
            long completed,
            long handlerCalls,
            int queued) {}

    public static void main(String[] args) {
        Sample a = new Sample(0L, 200L, 2L, 10);
        Sample b = new Sample(
                10_000_000_000L, 350L, 12L, 20);

        double seconds = (b.timeNanos() - a.timeNanos())
                / 1_000_000_000.0;
        double completedRate =
                (b.completed() - a.completed()) / seconds;
        double handlerRate =
                (b.handlerCalls() - a.handlerCalls()) / seconds;
        int queueDelta = b.queued() - a.queued();

        System.out.printf(Locale.ROOT,
                "completionRate=%.1f tasks/s%n", completedRate);
        System.out.printf(Locale.ROOT,
                "handlerRate=%.1f callbacks/s%n", handlerRate);
        System.out.println("queueDelta=" + queueDelta);
    }
}
~~~

~~~bash
javac --release 21 PoolRateMath.java
java PoolRateMath
~~~

**Exact stdout:**

~~~text
completionRate=15.0 tasks/s
handlerRate=1.0 callbacks/s
queueDelta=10
~~~

This calculates on hypothetical data. **Handler rate** is measured in callbacks/s—never assume it means lost requests/s when the policy is not `Abort`.

## 7. Runnable Java 21 Lab: One Active Worker, One Queued Task, One Rejected Task

**QueueSaturationLab.java** configures `core=max=1`, `queue capacity=1`, and a custom handler that counts rejections and throws. **CountDownLatch** keeps the first task holding the worker until measurements are printed, avoiding `Thread.sleep` races.

**File QueueSaturationLab.java:**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueSaturationLab {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger rejected = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                (task, executor) -> {
                    rejected.incrementAndGet();
                    throw new RejectedExecutionException(
                            "lab capacity reached");
                });

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();
            pool.execute(() -> {});

            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                // Handler already counted the rejection; do not increment again.
            }

            System.out.println(
                    "before active=" + pool.getActiveCount()
                    + " completed=" + pool.getCompletedTaskCount()
                    + " queued=" + pool.getQueue().size()
                    + " rejected=" + rejected.get());

            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Lab pool did not terminate");
            }

            System.out.println(
                    "after active=" + pool.getActiveCount()
                    + " completed=" + pool.getCompletedTaskCount()
                    + " queued=" + pool.getQueue().size()
                    + " rejected=" + rejected.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac --release 21 QueueSaturationLab.java
java QueueSaturationLab
~~~

**Stdout when the program finishes normally:**

~~~text
before active=1 completed=0 queued=1 rejected=1
after active=0 completed=2 queued=0 rejected=1
~~~

**Sequential explanation:**

1. Task 1 started, signaled **started**, and awaits the latch; the sole worker is busy: **active=1**.
2. Task 2 enters the **ArrayBlockingQueue capacity=1**: **queued=1**.
3. Task 3 cannot enter the queue or spawn a worker; the handler increments the counter and throws **RejectedExecutionException**: **rejected=1**.
4. Before release, no worker task has finished: **completed=0**.
5. After `release` and `awaitTermination` succeed, tasks 1 and 2 finish: **completed=2**, with 0 active and 0 queued. Task 3 never ran in a worker.

Calling **shutdown()** lets already accepted tasks complete. **shutdownNow()** in `finally` is solely safety cleanup if control flow fails; it is not called before capturing the normal exit state.

**Note:** the JDK documents these getters as **approximate**. The demo uses two synchronized checkpoints for illustration rather than treating them as atomic snapshots for production. If interrupted or the JVM is starved past the 5-second timeout, the program errors instead of promising full stdout.

### 7.1. Why Does a Thread Dump Not Show the Second Task?

While the first worker awaits `CountDownLatch`, a thread dump shows the stack of **task 1**. Task 2 is sitting in the queue and has not been pulled by any worker yet, so **task 2 has no running call stack in any worker**. That is why thread dumps must be paired with **queue size, time-in-queue, and submission logs**.

Never run saturation demos against a real production application pool; this lab creates its own small isolated pool.

## 8. Avoiding Broken Accounting Equations

A seemingly plausible equation:

~~~text
outstanding = taskCount - completedTaskCount
outstanding = activeCount + queueSize
~~~

**There is no guarantee both sides are equal.** Discrepancies arise because:

- **getTaskCount/getCompletedTaskCount/getActiveCount** are approximate under concurrency.
- Getters are invoked at slightly different moments.
- `CallerRuns` executes outside worker completion counters.
- `DiscardOldest` can evict a queued task.
- Tasks may be canceled/removed, or `shutdownNow` returns pending tasks.
- Submissions are retried or one request spawns multiple tasks.
- The work queue is only one layer; broker/gateway/DB queues may also exist.
- Executor or JVM restarts break counter continuity.

If strict business-level accounting is required, use **task IDs, task lifecycle transitions**, and dedicated counters for **attempted, accepted, started, succeeded, failed, canceled, rejected, and dropped**. Never force approximate pool stats into an identity the API never promised.

## 9. Diagnostic Matrix by Active, Completed, Queued, and Rejected

| Active | Completed Rate | Queue | Rejection | Direction |
| --- | --- | --- | --- | --- |
| High | High | Low | None | Pool is busy yet progressing; check SLA/latency. |
| High | Low/0 | Rising | Rising when full | Workers blocked, slow dependencies, or deadlock/starvation. |
| High | High | At capacity | Rising | Demand exceeds capacity; evaluate backpressure/scaling. |
| Low | Low | Low | None | May be idle, or bottlenecked at ingress outside the pool. |
| Low | Low | High | Unclear | Check worker creation, lifecycle, shutdown, or queue semantics. |
| High | High | 0 | Rising | Likely `SynchronousQueue`. |
| 0 | 0 | 0 | Rising | Likely submissions to an already shut-down executor. |
| High | Progressing | Rising steadily | 0 | Likely unbounded queue not yet triggering rejections. |

**This is a hypothesis-generation table**, not causal proof. The same `active=8, queue=100` can come from a slow DB, CPU throttling, lock contention, a retry storm, or genuinely high valid request rates.

### 9.1. High Active, Low Completed, Low CPU

Workers may be **WAITING/BLOCKED** on DB, HTTP clients, sockets, locks/monitors, or `Future.get()`. Capture timely thread dumps and inspect DB connection pools, external API latency, and dependency cycles.

### 9.2. High Active, Low Completed, High CPU

Likely CPU-bound tasks, expensive loops, thread contention, or cgroup CPU quota throttling. Use JFR/sampling profilers and CPU metrics; never blindly add threads when CPU headroom is exhausted.

### 9.3. Completed Rising While Quality Drops

A pool can finish thousands of fast-failing tasks. Compare **business success rate, error/timeout rate, and p95/p99**, rather than celebrating completion rate alone.

### 9.4. Low Queue Yet High Request Latency

The backlog may sit at the API gateway, rate limiter, broker, connection pool, or `CallerRuns`. **ThreadPoolExecutor’s queue** only sees tasks already admitted into that queue. Instrument the end-to-end request timeline.

## 10. Thread Starvation Deadlock from Future Dependencies

A fixed pool has **2 workers**. Tasks A and B are both running, each submitting child tasks C and D to **that same pool** and waiting on `Future.get()`:

~~~text
Worker 1: Task A -> submit C -> Future.get(C)
Worker 2: Task B -> submit D -> Future.get(D)

Queue: [C, D]
Active: 2/2
Completed rate: 0
Handler calls: 0 if queue still has space
~~~

C/D have no free worker, while A/B refuse to exit. This is a **thread starvation deadlock**, which may not form any monitor-lock cycle detectable by **ThreadMXBean.findDeadlockedThreads()**. Metrics **active=max + queue>0 + completed flat** suggest it, and `Future.get` stacks confirm the investigation path.

**Do not fix this simply by raising queue capacity.** Eliminate blocking joins inside the same fixed pool, separate executors, use async composition, or change the dependency design; then test correctness and load.

## 11. Production Instrumentation

A suggested metric set:

| Metric | Source | Type |
| --- | --- | --- |
| **executor_active_workers** | `getActiveCount` | Gauge |
| **executor_pool_size** | `getPoolSize` | Gauge |
| **executor_max_workers** | `getMaximumPoolSize` | Configuration |
| **executor_queue_size** | `getQueue().size` | Gauge |
| **executor_queue_capacity** | Bounded queue config | Configuration |
| **executor_completed_tasks_total** | `getCompletedTaskCount` | Approximate counter |
| **executor_scheduled_tasks_total** | `getTaskCount` | Approximate counter |
| **executor_rejection_handler_calls_total** | Instrument rejection handler | Custom counter |
| **executor_caller_runs_total** | Instrument `CallerRuns` | Custom counter |
| **executor_dropped_tasks_total** | Instrument drop policy | Custom counter |
| **executor_task_failures_total** | Task result handling | Custom counter |
| **executor_queue_wait_seconds** | Accepted time to task start | Histogram |
| **executor_execution_seconds** | Task start to task end | Histogram |
| **request_success_total** | Application boundary | Business counter |

**These are suggested names**, not a fixed standard of Java 21 or every framework version. Check exact semantics in Micrometer/JMX/Prometheus integrations when adopting.

### 11.1. Counting Failed Tasks Accurately on Submit

When calling **submit(Callable)**, the executor wraps the task in a **FutureTask**. In a subclass override **ThreadPoolExecutor.afterExecute(Runnable, Throwable)**, the `Throwable` parameter can be `null` even if the `Callable` threw, because the exception was captured inside the `Future`. Therefore measure failures at the **business completion boundary** or an appropriate task wrapper; never treat `t == null` as success.

### 11.2. Do Not Double-Count Rejections

If the handler increments **rejection_handler_calls_total** while callers catching `RejectedExecutionException` increment **submission_exceptions_total**, a single submission increments **both metrics**. They have different meanings and must not be summed as total lost tasks. Define one owner per metric and retain policy metadata.

### 11.3. Cardinality, Scope, and Units

Attach labels **service, executor_name, instance, and JVM start time**; avoid task IDs, request IDs, or stack traces as labels due to high cardinality. Use **tasks** for counts, **tasks/s** for rates, and **seconds** for latency. A cluster-wide aggregated queue size can mask a hot instance; inspect per replica before aggregating.

## 12. Executors Without the Same Metrics

### 12.1. Virtual-Thread-Per-Task Executor

**Executors.newVirtualThreadPerTaskExecutor()** in Java 21 creates one virtual thread per task rather than a shared `ThreadPoolExecutor` with `getQueue`/`getActiveCount`. Do not attempt to cast it to `ThreadPoolExecutor`.

~~~java
// Illustrative snippet, not yet a standalone program.
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> processOneRequest());
}
~~~

If active/queue/concurrency stats are needed in this model, instrument **at application admission, semaphores, request lifecycles, or downstream pools**. **ThreadMXBean.getThreadCount()** in Java 21 counts platform threads only; it does not report live virtual tasks.

### 12.2. ForkJoinPool

**ForkJoinPool** provides `getQueuedTaskCount`, `getQueuedSubmissionCount`, `getActiveThreadCount`, `getRunningThreadCount`, and `getStealCount`; its semantics differ from `ThreadPoolExecutor`:

- **getQueuedTaskCount** estimates tasks waiting in worker queues.
- **getQueuedSubmissionCount** estimates unstarted external submissions.
- **getActiveThreadCount** follows work-stealing semantics.

Do not merge these values with `ThreadPoolExecutor` queue size without tagging **executor_type** and interpreting explicitly.

### 12.3. ScheduledThreadPoolExecutor

The queue can hold many **delayed ScheduledFuture** instances whose trigger time has not arrived. A large queue size does not mean workers are falling behind. Measure **delay past scheduled time, start delay, periodic task outcomes**, and cancel lifecycles.

### 12.4. Framework-Managed Executors

Spring/Netty/Kafka/application servers may wrap or substitute executors. Know whether the framework uses **ThreadPoolExecutor, an event loop, a scheduler, or virtual-thread-per-task**, and before/after which queue rejections happen. Do not guess from thread pool names or a generic `ExecutorService` return type.

## 13. Backpressure, Queue Sizing, and SLAs

An overload-resilient design combines:

1. **Concurrency limits:** max workers, semaphores, DB connection slots.
2. **Backlog limits:** bounded queues or wait limits.
3. **Explicit rejection mechanisms:** 429/503, retry-after/backoff when appropriate, no silent drops.
4. **Measuring queue wait and service time:** not queue length alone.
5. **Scaling and dependency tuning:** only add workers when CPU/I/O/downstream have remaining capacity.

**Growing a queue absorbs bursts yet can push requests past their SLA.** A request with a 200 ms budget that sits in a queue for 1 second will not be saved by adding queue capacity.

### 13.1. Little's Law and Steady-State Assumptions

In a stable system, **Little's Law**:

\[
L = \lambda W
\]

where `L` is average work in the defined boundary, `λ` is steady throughput, and `W` is average time spent in that boundary. However, a **queue snapshot** while backlog is surging **does not prove exact wait times**. Instrument queue wait histograms and end-to-end latency.

### 13.2. Simplified Capacity Calculation Example

With 8 workers and an average task duration of 100 ms, theoretical capacity in a simplified model is roughly **80 tasks/s**. When slow downstream stretches each task to 400 ms, capacity drops to roughly **20 tasks/s**. An arrival rate of 60/s causes the queue to grow.

This is a back-of-the-envelope estimate, not a capacity benchmark. Task duration distributions, GC, CPU, network, DB pools, and concurrency limits alter real results. **Adding workers unconditionally** may only overload the dependency further.

## 14. Gathering Evidence with Thread Dumps and JFR

When active is high, completions stall, and the queue grows:

- Capture two or more timestamped snapshots over time.
- Collect **jcmd Thread.print -l** or a VM-appropriate thread dump to inspect worker stacks.
- If stacks cluster at **Future.get**, check same-pool dependencies.
- If stacks sit in **socket read/DB**, check downstream latency and connection pools.
- If stacks sit at **synchronized/locks**, investigate contention and owners.
- If stacks are CPU-bound, use JFR/CPU profiling and cgroup throttling metrics.
- Correlate **request trace IDs** to avoid reasoning from a single random stack.

Time-bounded JFR example, used only after verifying JVM, permissions, disk space, and overhead:

~~~bash
jcmd 12345 JFR.start name=pool-triage \
  settings=profile duration=60s \
  filename=/diagnostics/pool-triage.jfr
~~~

**12345 and the path are examples only.** The file is written by the target JVM on its own filesystem, not necessarily on the laptop running `jcmd`. JFR helps observe **execution samples, thread parks, monitor blocking, and GC** when events are enabled and the recording window fits. Never take continuous dumps every 100 ms in production.

## 15. Docker/Kubernetes and Lifecycle Metrics

In containers, **active=max** does not mean real CPU is available:

- **CPU quota/throttling** can slow completion rates even while workers are scheduled.
- **Memory limits** plus unbounded queues can trigger Pod OOMKills.
- **CPU-based HPA** may fail to scale out when workloads block on DB with low CPU.
- **Multiple replicas** can experience skewed load; inspect queue/rejection per instance.
- **Rolling deploys/shutdowns** reset pool counters and can cause rejection spikes.
- **PID/mount namespaces** affect how thread dumps/JFR are captured, without changing Java API semantics.

Commands strictly for Pod context, which do not read application queues directly:

~~~bash
kubectl get pod api-worker-0 -o wide
kubectl describe pod api-worker-0
kubectl logs api-worker-0 -c app --since=10m
~~~

**Pod names are illustrative.** To expose queue/rejection stats, the application/framework must provide a metrics exporter or custom MBean. Standard **ThreadMXBean** has no getters for application-created `ThreadPoolExecutor` queues.

## 16. Pool Hang/Contention Investigation Runbook

**Step 1 — Identify the exact target.** Record app/JDK version, Pod/instance, pool name, executor type, core/max/queue capacity, rejection policy, and task classes.

**Step 2 — Capture at least two samples.** Read active, `poolSize`, queue size, completed total, rejection handler total, lifecycle state, and timestamps. Handle counter resets and compute deltas/rates.

**Step 3 — Classify symptoms.** Full active + flat completed + rising queue suggests blocking/starvation. Full queue + rising handler suggests admission limits. Queue 0 + rising handler suggests `SynchronousQueue`. Handler spikes during shutdown suggest lifecycle transitions.

**Step 4 — Cross-check evidence.** Thread dumps/JFR, request traces, DB/socket/lock metrics, CPU/GC, queue wait histograms, ingress rates, and retry behavior.

**Step 5 — Find root cause and minimal action.** Fix blocking dependencies/deadlocks, timeouts, backpressure, retry storms, concurrency limits, or worker counts only with evidence.

**Step 6 — Verify post-fix.** Under comparable load, compare **business success throughput, p95/p99, queue wait, rejection/drop semantics, CPU/memory, and downstream capacity**. A smaller queue alone does not prove user experience improved.

**Step 7 — Clean up instrumentation.** Stop temporary traces/recordings, secure diagnostic files, and archive process/metric definitions.

## 17. Self-Check Scenarios with Answers

**A — Active 12/12, queue 200/200, low completion rate, rising rejections.** Must we definitely add workers?

**Answer:** Not yet. This shows pool limits were reached. Inspect stacks, CPU/downstream, arrival/service times, and rejection policy. If the DB is slow, adding workers can make things worse.

**B — Low CPU, active=max, completions near 0.** What to check?

**Answer:** Worker stacks, locks/connection pools/Future dependencies. I/O waits or thread starvation can keep active high while CPU stays low.

**C — Queue grows to 50,000, rejected=0.** Is that safe?

**Answer:** Likely an unbounded queue leading to memory/latency pressure before any rejection occurs. Bounded admission and timeouts are needed.

**D — Queue always 0, high rejections.** Is the queue getter broken?

**Answer:** Not necessarily; it may be a **SynchronousQueue** that holds no backlog.

**E — High rejection callbacks yet business success rate remains good.** Why?

**Answer:** `CallerRunsPolicy` may be executing work on caller threads. Measure caller latency and run counts rather than labeling every callback a lost request.

**F — Completions rise yet HTTP 500s also rise.** Contradiction?

**Answer:** No. Completed only reflects execution finishing, which includes finishing with errors.

**G — Rejection spike right during a rolling deploy.** Is it overload?

**Answer:** Could be pool shutdown, late submissions, and incomplete traffic draining. Check `isShutdown` and deploy timelines.

**H — Two workers await Futures of two tasks in the same pool, queue holds two tasks.** What type of hang?

**Answer:** Thread starvation deadlock. Fix the dependency graph / async composition rather than just enlarging the queue.

**I — A Future is evicted by DiscardOldest while the caller keeps waiting.** What is the problem?

**Answer:** The Future may never complete unless explicitly canceled; explicit rejected/dropped lifecycle handling and timeouts are required.

**J — Long queue in ScheduledThreadPoolExecutor.** Does it mean workers are falling behind?

**Answer:** Not necessarily; the queue may hold delayed tasks waiting for their trigger time. Check deadlines and actual start delays.

**K — newVirtualThreadPerTaskExecutor returns ExecutorService.** Can we cast it to ThreadPoolExecutor to read active count?

**Answer:** No. Measure at application admission/task lifecycles and downstream limits instead.

**L — JVM restarts between two completed samples.** Should we divide the negative difference by elapsed time?

**Answer:** No. Split series by process/pool identity and handle resets properly.

## 18. Common Mistakes and Checklist

**Mistakes to avoid:**

1. Assuming active equals threads actively using CPU.
2. Assuming completed equals total successful requests.
3. Assuming `ThreadPoolExecutor` provides a built-in total rejected getter.
4. Assuming every handler invocation equals a lost task.
5. Assuming no exception means no silent discard.
6. Assuming queue=0 means no saturation.
7. Assuming rejected=0 means arrivals are within capacity.
8. Assuming a large `maxWorkers` means the pool always expands to max.
9. Assuming `active + queued + completed + rejected == submitted` at every sample.
10. Assuming one thread dump shows all tasks waiting in the queue.
11. Assuming raising `maxPoolSize` fixes every timeout.
12. Assuming `CallerRuns` is always safe for HTTP event loops.
13. Assuming `DiscardOldest` leaves queued Futures unaffected.
14. Assuming queue size equals wait duration.
15. Assuming `ThreadMXBean` measures every application executor backlog.
16. Assuming `ForkJoinPool.getQueuedTaskCount` matches `ThreadPoolExecutor.getQueue().size()`.
17. Assuming many delayed tasks in a scheduled queue mean overload.
18. Assuming virtual threads require a shared `ThreadPoolExecutor` queue.
19. Subtracting counters across a JVM restart without reset handling.
20. Relying on cluster-wide average queue size and missing a hot replica.
21. Treating pending tasks returned by `shutdownNow` as rejected tasks.
22. Assuming rising completion rate guarantees healthy end-to-end SLAs.

**Quick checklist when receiving an alert:**

| Check | Evidence to Record |
| --- | --- |
| Pool identity | Name, implementation, instance, JVM start time. |
| Worker config | Core/max/`poolSize`/active. |
| Work queue | Type, capacity, size, `remainingCapacity`. |
| Progress | Completion rate in the same pool/process. |
| Rejection | Handler type and clearly defined counters. |
| Business outcomes | Success/failure/canceled/timeout rates. |
| Latency | Queue wait, service time, end-to-end p95/p99. |
| Other layers | Gateway, broker, DB pool, external APIs. |
| Pool lifecycle | Shutdown state, deployments/restarts. |
| Task dependencies | Thread dumps, Future/lock ownership, JFR. |
| Container limits | CPU throttling, memory/ephemeral capacity. |
| Post-fix check | Before/after under comparable workload. |

## 19. Official References

- [Java SE 21 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queueing mechanics, sizing, rejection, and approximate getters.
- [Java SE 21 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): callback for unaccepted tasks.
- [Java SE 21 — AbortPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html): rejection by exception.
- [Java SE 21 — CallerRunsPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html): execution in caller.
- [Java SE 21 — DiscardPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html): silent discard.
- [Java SE 21 — DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html): dropping oldest queue item and retrying.
- [Java SE 21 — BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `size` and `remainingCapacity`.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): queued tasks/submissions and work stealing.
- [Java SE 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): delayed/periodic queues.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): factory methods and virtual-thread-per-task.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread executors and non-pooled shared worker nature.
- [JDK 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dumps and JFR diagnostics.

**Conclusion:** to understand **hangs and contention**, never treat active, completed, rejected, and queued as four counts of the same kind. **Active/queue are gauges; completed/rejection are counters needing deltas/rates; rejection policies dictate whether tasks throw, run on the caller, or get dropped.** Thread dumps/JFR and business metrics explain why workers stop progressing. A trustworthy conclusion must rest on **the same process, same pool, same time window, and same definitions**.