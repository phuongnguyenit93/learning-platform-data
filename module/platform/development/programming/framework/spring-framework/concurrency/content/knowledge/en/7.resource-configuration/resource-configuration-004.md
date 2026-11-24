# Sizing Queue Capacity Based on Memory and Acceptable Wait Time

## 1. Why Is Queue Size a Resource Decision?

In a Spring application, many requests may concurrently submit work to a `ThreadPoolTaskExecutor`: generating reports, calling external systems, processing images, recording events, or updating data. When all workers are busy, new tasks may have to **wait in a queue** before a worker picks them up.

The queue limit (`queue capacity`) answers the question: **how many waiting tasks are allowed in the process's memory?** It is neither the number of workers nor the allowed waiting time.

Choosing too large a queue can cause:
- Many `Runnable`/`Callable`, `Future` instances, and objects they reference to remain on the heap for a long time, raising GC pressure or causing `OutOfMemoryError`.
- New tasks to report successful submission yet wait too long before starting, by which time data may already be stale.
- Overload to be hidden: the queue keeps accepting work even when the system cannot keep up.
- Shutdown/redeploy times and reclaiming/cancelling unstarted tasks to become hard to control.

Choosing too small a queue also has a cost: a brief traffic burst can trigger many rejections even though the system could have processed them shortly afterward. Hence a good size is neither "the bigger the safer" nor "always set to 0," but a balance that can be **measured, explained, and verified**.

This lesson walks through choosing an initial bound from a **memory budget** and a **wait-time budget**, understanding how the queue interacts with Spring's worker counts, and validating under real load.

## 2. Model: Workers, Queued Tasks, and Total Time

A task submitted to an executor can go through these stages:

```text
Caller submits work
         |
         v
      execute() / submit()
         |
         v
  Worker available immediately? ---- Yes ---> Running (active)
         |
         | No
         v
  Space left in queue? ------------- Yes ---> Queued (waiting)
         |                                          |
         |                                          v
         |                                    Free worker -> run
         v
  Pool mechanism can add worker? --- Yes ---> Add worker, run
         |
         | No
         v
      REJECTED
```

This diagram helps visualize the flow, while the **actual `ThreadPoolExecutor` rules** are more specific and are explained in Section 3.

Distinguish the metrics:

| Term | Symbol | Meaning |
|---|---|---|
| Active tasks | `A` | Tasks picked up by a worker and not yet finished |
| Queued tasks | `Q_current` | Tasks currently sitting in the work queue |
| Queue capacity | `Q_capacity` | Limit on how many tasks can be queued |
| Runnable workers | `c` | Concurrency level of the pool at the time observed |
| Queue wait time | `Wq` | From task acceptance until a worker starts executing it |
| Execution time | `S` | From worker start until task completion |
| Time in execution system | `T` | Approximately `Wq + S`, excluding caller pre/post-processing |
| Submission rate | `λ` | Tasks arriving per second; distinguish submitted vs. accepted |
| Completion rate | `μ` | Tasks completed per second at the measured load |

**`Q_capacity = 100` means at most 100 waiting tasks, not 100 concurrently running tasks, and not 100 MB.** The system may simultaneously hold running tasks, queued tasks, and data retained in upstream HTTP/message broker layers.

For a request with a 500 ms response target, the time left for the queue might be only 100 ms after subtracting database calls, business logic, network transfer, and other steps. Do not allocate the entire latency budget to `Wq`.

## 3. ThreadPoolExecutor Fills the Queue Before Scaling to maxPoolSize

Spring's `ThreadPoolTaskExecutor` builds on `java.util.concurrent.ThreadPoolExecutor`. Three key settings are:

- `corePoolSize`: core worker count the pool tries to create when receiving work (per worker-creation rules).
- `maxPoolSize`: maximum worker limit.
- `queueCapacity`: number of tasks that can wait in the work queue.

`ThreadPoolExecutor.execute(...)` rules under normal conditions:

1. While the worker count is below `corePoolSize`, the pool prefers creating a new worker to take the task.
2. Once core level is reached, the pool **prefers placing work into the queue**.
3. Only when work **cannot enter the queue** does it attempt to grow workers up to `maxPoolSize`.
4. If the pool cannot accept work via either workers or queue, `RejectedExecutionHandler` decides how to reject/handle it.

Example configuration `corePoolSize=4`, `maxPoolSize=8`, `queueCapacity=20`:

```text
Initial tasks -> create up to 4 core workers
4 workers busy -> subsequent tasks wait (up to 20 slots)
Queue full -> pool can now grow 5th ... 8th worker
8 workers busy + queue full -> reject or apply rejection policy
```

This is an **idealized state diagram when tasks run long enough to load the pool**. In practice, a worker may finish and pull from the queue right as another task is submitted, so you cannot deduce exact outcomes merely from task sequence numbers.

### 3.1. A Very Large Queue Renders maxPoolSize Nearly Ineffective

If the queue has a huge capacity, the pool almost always enqueues after reaching `corePoolSize`. `maxPoolSize` will not be used to add workers under normal conditions because the queue never fills.

Specifically, **`ThreadPoolTaskExecutor` when left unconfigured** defaults in Spring Framework to `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, and `queueCapacity=Integer.MAX_VALUE`. That is the default of **this Spring class itself**; auto-configuration in a particular Spring Boot version may differ and you should inspect the effective configuration. Never rely on defaults when deploying systems with load/latency requirements.

**Technical takeaway:** Raising `maxPoolSize` without understanding `queueCapacity` may fail to increase workers under high load. Check queueing rules before tuning thread counts.

### 3.2. queueCapacity=0 Differs from a Positive queueCapacity

In `ThreadPoolTaskExecutor`:

| `queueCapacity` | Queue Type Created | Impact |
|---|---|---|
| Positive value, e.g. `16` | `LinkedBlockingQueue` with corresponding bound | Allows up to 16 waiting tasks |
| `0` | `SynchronousQueue` | Stores no tasks in a queue; hands off directly to a worker or tries creating another worker |
| Very large/default value | `LinkedBlockingQueue` with huge integer bound | Risks accumulating many tasks on the heap before hitting the count limit |

`SynchronousQueue` stores no tasks and is not a one-slot queue. With `queueCapacity=0`, if all workers are busy and no new worker can be created, work is rejected per policy; a finite `maxPoolSize` is essential to control resources. Do not leave `maxPoolSize` unbounded carelessly just because there is no queue.

`queueCapacity` generally must be set **before the executor is initialized**. Changing the property on an already-running bean does not replace the underlying queue with one of a different capacity.

## 4. First Constraint: How Much Memory Does Each Queued Task Hold?

A queue entry is not just a pointer to a task. It holds a reference to a `Runnable`, a `FutureTask`, or a framework wrapper. The task may retain an entire object graph (`object graph`):

- Lambdas/callbacks capturing a `request`, `byte[]` holding images or files, record lists, JSON parse trees.
- `Future` objects, context, metadata, data created by `TaskDecorator`, and related closures.
- Parameters, collections, temporary caches, or references to beans, documents, and entire request payloads.
- Internal queue structures, such as `LinkedBlockingQueue` nodes, plus executor management overhead.

Example:

```java
byte[] payload = loadPayload();
executor.execute(() -> process(payload));
```

The code above is **only an illustrative snippet**, where `loadPayload()`/`process(...)` are application methods. The lambda captures a reference to `payload`; if the task waits long, the array can stay alive even after the request has returned. A 1,000-element queue can be very light if each task is tiny, or very heavy if each task holds multi-MB arrays.

You cannot take lambda bytecode size or reference size (4/8 bytes) to deduce total memory. You must estimate **memory kept alive by queueing** (`retained heap`), including objects kept alive solely by the task. Use profiling/heap dumps or measure heap consumption under representative load; avoid double-counting objects shared across many tasks.

### 4.1. Building a Practical Heap Budget

Let:

- `M_queue`: heap bytes **allowed for queued tasks**, after subtracting baseline load, active tasks' data, caches, and GC headroom.
- `B_task`: conservative estimate of heap bytes retained by **one waiting task**, including wrapper, queue node, and referenced data.
- `Q_memory`: queue limit derived from the memory budget.

Preliminary formula:

\[
Q_{\text{memory}} = \left\lfloor \frac{M_{\text{queue}}}{B_{\text{task}}} \right\rfloor
\]

For example, allocating 20 MiB of heap for the queue and assuming **each task holds at most around 96 KiB in the test model**:

\[
Q_{\text{memory}} =
\left\lfloor \frac{20 \times 1024}{96} \right\rfloor
= 213\ \text{tasks}
\]

This is only a **memory-based limit**; it does not yet answer whether waiting behind 213 tasks is acceptable. In production, `B_task` varies; measure across multiple payloads and take a realistic upper bound with a safety factor. An average or p95 value is not a hard upper bound and does not guarantee abnormally large tasks will not occur.

The queue budget must also stay separate from memory for: active tasks, thread stacks (mostly off-heap), connections, direct buffers (`direct buffer`), caches, in-flight responses, and other components. Do not allocate all of `-Xmx` to queues.

### 4.2. Reducing Data Retained by Tasks

If a task only needs an ID, rather than capturing a large request/DTO, capture an immutable ID and load required data at execution time (weighing extra I/O cost and potential data changes). Never hold `HttpServletRequest`, open streams, or request-scoped objects in a long queue.

Other optimizations include placing large payloads in an appropriate store and queueing only a durable reference, batching into controlled sizes, or stripping temporary data before submission. When tasks must survive restarts, an in-heap queue is inherently not a durable job store.

## 5. Second Constraint: How Long Can a Task Wait?

The queue latency budget `Wq_budget` should be derived from user/caller requirements:

```text
End-to-end request deadline
  - request creation/intake overhead
  - expected business execution time (especially p95/p99)
  - response return/network transmission time
  - safety margin
= maximum budget for queue wait
```

If the end-to-end SLO is 600 ms, workers may need 350 ms at high percentiles, other stages take 100 ms, and 50 ms is reserved as margin, then queue wait has only about 100 ms of budget. Spending 500 ms waiting in the queue makes the 600 ms target nearly impossible.

An **approximate calculation to find a candidate setting**:

\[
Q_{\text{time}} \approx
\left\lfloor \mu_{\text{effective}} \times W_{q,\text{budget}}\right\rfloor
\]

Where `μ_effective` is the **rate at which tasks can actually start/complete** under the measured load and worker configuration, in tasks/second. If the pool is busy and draining steadily, a queue with `Q` tasks ahead needs roughly `Q / μ_effective` seconds to clear; you must factor in active tasks' remaining work, service-time variance, and execution scheduling.

For example, if sustained completion rate is around **80 tasks/second**, and the app allows only **0.20 seconds** of wait:

\[
Q_{\text{time}} \approx \lfloor 80 \times 0.20 \rfloor = 16
\]

The number 16 is a **starting point for load testing**, not a promise that every task starts within 200 ms. With workloads containing very long jobs, uneven distributions, GC pauses, or abnormal downstream slowdowns, even a short queue can exceed the budget.

### 5.1. Do Not Confuse with Little's Law

For a stable system over a sufficiently long window, Little's Law gives **average values**:

\[
L_q = \lambda_{\text{accepted}} \times \overline{W_q}
\]

Where `Lq` is the average number of tasks in the queue, `λ_accepted` is the throughput of tasks **actually accepted** (and completed in steady state), and `Wq_bar` is the **average** wait time. This equation helps cross-check measured metrics: if throughput is 80 tasks/s and average wait is 0.1 s, there are on average about 8 tasks waiting.

**You cannot use Little's Law to guarantee p95/p99 or maximum wait time.** It says nothing about tail latency, and steady-state assumptions cannot hide a queue growing without bound when arrival exceeds serving capacity.

If the requirement is "99% of tasks start within 200 ms," measure `p99 queue wait` directly under representative load instead of calculating from average rates.

## 6. Combining Both Budgets to Choose an Initial Limit

For a relatively homogeneous task type, an auditable starting point is:

\[
Q_{\text{candidate}} =
\max\left(0,\;
\min(Q_{\text{memory}}, Q_{\text{time}})\right)
\]

If you keep a separate safety margin, you can choose **less than** `Q_candidate` and tune via load tests. This formula does not turn the queue into an SLO guarantee; it simply prevents picking a number that violates either budget right at design time.

Using the same example numbers:

| Quantity | Assumed Value |
|---|---|
| Heap allocated to queued tasks | 20 MiB |
| Memory per queued task (estimated with margin) | 96 KiB |
| Memory-based limit | 213 tasks |
| Measured pool completion rate | 80 tasks/s |
| Queue wait budget | 200 ms |
| Time-based limit | 16 tasks |
| **Candidate `queueCapacity`** | **16 tasks** |

**The governing constraint here is latency, not memory.** If you set the queue to 213 just because heap has room, then at 80 tasks/s, sitting behind ~213 tasks can mean waiting roughly 2.66 seconds in the simple model, far exceeding 200 ms.

Conversely, if each task retains 2 MiB and only 20 MiB of heap is allocated to the queue, the memory limit is around 10 tasks, even if wait time would allow 16. In that case pick 10 or fewer, then decide how to reject/shed load.

### 6.1. Java 17 Example Computing Both Limits

**File `QueueBudgetDemo.java` — standalone program, no Spring required**

```java
public class QueueBudgetDemo {
    public static void main(String[] args) {
        long budgetBytes = 20L * 1024 * 1024;
        long estimatedBytesPerQueuedTask = 96L * 1024;

        double measuredThroughputPerSecond = 80.0;
        double queueWaitBudgetSeconds = 0.20;

        long byMemory = budgetBytes / estimatedBytesPerQueuedTask;
        long byTime = (long) Math.floor(
                measuredThroughputPerSecond * queueWaitBudgetSeconds);

        long initialCapacity = Math.max(0L,
                Math.min(byMemory, byTime));

        System.out.println("Memory limit: " + byMemory);
        System.out.println("Time limit: " + byTime);
        System.out.println("Candidate config: " + initialCapacity);
    }
}
```

```bash
javac QueueBudgetDemo.java
java QueueBudgetDemo
```

Deterministic output:

```text
Memory limit: 213
Time limit: 16
Candidate config: 16
```

The program demonstrates the calculation; **it does not measure your heap or system throughput for you**. The inputs in the code are hypothetical for practice; production requires substituting measured data.

## 7. What Happens When Input Load Exceeds Processing Capacity?

Let `λ_in` be the task arrival rate and `μ_effective` be the pool's steady serving rate.

- If `λ_in` is usually below serving capacity, the queue has a chance to drain back down after each burst.
- If `λ_in` persistently exceeds serving capacity, queued work tends to grow by roughly `λ_in - μ_effective` tasks/second until it hits the limit and triggers rejection, caller blocking, or another policy.
- Even if the average rate is close to max capacity, wait times can still climb sharply due to processing-time variance, clustered arrivals, and resource contention.

For example, if input stays at **120 tasks/second** while the pool finishes only **80 tasks/second**, there is an excess of about **40 tasks/second**. Once workers are busy and the queue starts empty, a queue of 16 fills in roughly **0.4 seconds** in a simple continuous model. A queue of 160 only delays saturation to about 4 seconds, **without increasing the pool's real throughput**.

This is a rate-difference argument to understand overload, not an exact fill-time predictor for pools that scale from core to max, handle mixed job types, or face variable arrivals. In practice you must measure `μ_effective` under your actual config and load.

**Solutions for sustained overload:** shed traffic, apply input concurrency limits, optimize tasks, scale processing capacity if resources allow, or offload work to a durable queue. Merely enlarging the queue never fixes a long-term imbalance.

### 7.1. A Short Burst Differs from Sustained Overload

Suppose a pool has 8 idle workers and receives 20 tasks at once, each running long enough not to finish immediately. At most 8 tasks can run right away on the 8 workers; the rest wait or go to expanded workers depending on `core/max/queue`. A queue of 16 can absorb part of the burst, but that does not prove it handles **every** 20-task burst within your desired `p99 Wq`.

Measure **burst amplitude** (how many tasks arrive together), **burst duration**, **quiet intervals for queue recovery**, and **correlation among task runtimes**. A 5-second burst and a 5-minute surge are not equivalent in budget terms.

## 8. Applying This to Spring's ThreadPoolTaskExecutor

The illustrative config uses `corePoolSize=8`, `maxPoolSize=12`, `queueCapacity=16`. This is **a candidate to test**, not a standard configuration valid for every system.

**File `AsyncExecutorConfig.java` — Spring configuration, requires Spring Framework dependencies and ApplicationContext**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfig {

    @Bean("boundedTaskExecutor")
    public ThreadPoolTaskExecutor boundedTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("bounded-worker-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        return executor;
    }
}
```

Explanation:

1. `corePoolSize=8` lets the pool scale up to 8 core workers on demand.
2. `maxPoolSize=12` allows at most 12 workers (not always keeping 12 alive).
3. `queueCapacity=16` bounds **waiting tasks** in the `LinkedBlockingQueue`.
4. When core workers are busy, the queue is used first; only when the queue cannot accept more does the pool try creating workers 9–12.
5. `AbortPolicy` lets callers detect rejection. Spring may surface this as `TaskRejectedException` via the `TaskExecutor` interface.

The `@Bean` method returns the object so **Spring manages its lifecycle**; with normal bean registration, Spring invokes the initialization methods needed by the executor. You do not need to call `initialize()` manually inside the `@Bean` method when the bean lifecycle is managed properly. If you manually instantiate `new ThreadPoolTaskExecutor()` outside the container, you must handle initialization and shutdown yourself.

Example service using the registered executor:

**File `ReportService.java` — Spring component, no standalone `main`**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("boundedTaskExecutor")
    public CompletableFuture<String> buildReport(String reportId) {
        String result = "Generated report " + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
```

The method must be called **through the Spring proxy** from another bean for `@Async` to dispatch work to the executor under standard proxy configuration. Internal `this.buildReport(...)` calls usually bypass the proxy. An `@Async` invocation can be rejected right at submission if the pool is full; the caller must have a handling policy.

Do not write tests that depend on log print order from async tasks; scheduling depends on runtime execution. The Spring classes above are configuration/component code to wire into an appropriate Spring app, **not** plain Java SE programs compilable with just `javac`.

## 9. Java 17: Deterministic Experiment for Full Queue and Rejection

To see `queueCapacity` clearly without a Spring server, use standard Java `ThreadPoolExecutor` with **1 worker** and a queue holding **2** tasks. We hold the first task on a `CountDownLatch`; thus the next two tasks are guaranteed to wait in the queue during the check.

**File `BoundedQueueDemo.java` — standalone Java 17 program**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedQueueDemo {
    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch allowWorkerFinish = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    allowWorkerFinish.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();

            pool.execute(() -> {});
            pool.execute(() -> {});
            System.out.println("Queued: "
                    + pool.getQueue().size());

            try {
                pool.execute(() -> {});
                System.out.println("Unexpected: fourth task accepted");
            } catch (RejectedExecutionException rejected) {
                System.out.println("Fourth task rejected");
            }

            System.out.println("Queue after rejection: "
                    + pool.getQueue().size());
        } finally {
            allowWorkerFinish.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

```bash
javac BoundedQueueDemo.java
java BoundedQueueDemo
```

Deterministic output (independent of the order in which the worker executes waiting tasks):

```text
Queued: 2
Fourth task rejected
Queue after rejection: 2
```

Why is the output deterministic?

- `workerStarted.await()` ensures the first task has entered the worker.
- The first worker blocks at `allowWorkerFinish.await()` **before** we submit the second and third tasks.
- The pool has at most one worker, so the next two tasks can only wait in the 2-slot queue.
- The fourth task is rejected by `AbortPolicy` because the worker is busy and the queue is full.
- Only in `finally` is the latch released, letting the worker finish and drain the waiting tasks; `shutdown()`/`awaitTermination(...)` ensures a clean exit.

In production, `getQueue().size()` is only a snapshot at call time and can change immediately. The experiment has fixed output thanks to the latches, which does not mean every system always behaves in strict task 1/2/3/4 order under concurrent load.

Also note: the example uses Java's `ArrayBlockingQueue` to demonstrate the concept. Spring's `ThreadPoolTaskExecutor` with `queueCapacity > 0` uses `LinkedBlockingQueue`; both queues are count-bounded yet differ in internal structure, memory overhead, and performance characteristics.

## 10. When the Queue Is Full: You Need a Backpressure Policy

Choosing a finite `queueCapacity` means **explicitly acknowledging the system has limits**. You must define what callers see when work cannot be accepted.

Some `RejectedExecutionHandler` options in `ThreadPoolExecutor`:

| Policy | Behavior Under Overload | Consequences to Weigh |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | Explicit feedback, letting upper layers decide rejection/throttling |
| `CallerRunsPolicy` | If executor is not shut down, caller runs the task on the submitting thread | Creates backpressure by slowing callers; can block HTTP/request threads |
| `DiscardPolicy` | Drops the rejected task without throwing | Risks silent work loss |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting the new task | Can lose older tasks and break business ordering |

`CallerRunsPolicy` can fit when callers **are allowed to block** and the system accepts backpressure. Yet on request threads needing fast responses, running heavy tasks on the caller can cause timeouts; when the executor has already shut down, this policy can also drop tasks instead of running them. Do not treat `CallerRunsPolicy` as a universal cure.

A possible error-handling flow:

```text
Pool full / rejected
        |
        v
Is this work droppable or must it be guaranteed?
        |
        +-- Droppable --> report metrics/logs per policy, do not swallow silently
        |
        +-- Must be guaranteed --> persist to an appropriate durable store,
        |                         or return a safely retryable error
        |
        +-- Synchronous caller --> return clear overload signal
                                  (e.g. HTTP 429 or 503 per API contract)
```

Retry policies must have limits, backoff intervals, and avoid synchronized retry bursts; tasks with external side effects need idempotency to avoid duplicate execution on timeouts/retries. Continuous retries into the same full pool only amplify overload.

**A bounded queue is where load control starts, not a replacement for rate limiting, bulkheads, circuit breakers, timeouts, or durable queues** when the problem requires them.

## 11. Do Not Use Future Wait Timeouts as a Substitute for Queue Bounds

Callers can specify:

```java
result.get(200, TimeUnit.MILLISECONDS);
```

This is an illustrative snippet where `result` is a `Future<T>`. `get(timeout)` bounds **how long the calling thread waits for the result**, not how long a task may sit in the executor queue.

If `get(...)` times out, the task may still be queued or running; the call does not automatically remove the task from the queue. `cancel(true)` is only a cancellation/interruption request per contract, and whether a cancelled task is immediately purged from the underlying queue depends on the executor/task wrapper mechanism.

Therefore, if work is only valid until a deadline, the task should receive an explicit deadline and check it upon starting. If expired, avoid executing side effects that are no longer valid. When cancelling, monitor cancellation rates and whether the queue still retains unpurged wrappers.

A system with `Wq_budget=200 ms` should not simply call `Future.get(200 ms)` and conclude "the queue meets the SLO"; that only caps caller wait time and can leave unneeded background work behind.

## 12. Two Kinds of Limits Work Together: Pool, Queue, Downstream

Suppose a pool has `maxPoolSize=12` and `queueCapacity=16`. At one moment, the executor can hold up to roughly 12 running tasks and 16 queued tasks (excluding work at other layers). Yet **more threads do not automatically guarantee higher throughput**.

For CPU-bound tasks, exceeding useful cores can increase context switching and CPU contention, making `S` larger. For I/O-bound tasks, adding workers can raise concurrency yet also exhaust connection pools, the DB, or external service quotas. When a downstream is congested, `μ_effective` can actually **drop** even if `maxPoolSize` increases.

Consider related resources:

- CPU cores, per-task processing time, and CPU utilization.
- Heap memory for the queue and active tasks, plus native memory for thread stacks.
- DB connection count, HTTP connections, connection timeouts, and API quotas.
- Other thread pools in the HTTP server, schedulers, or message consumers.
- Queues in brokers, reverse proxies, servlet requests, and the executor itself. Chained queues add up latency.
- Network jitter/GC pauses can make p99 far worse than the average.

If the database pool has only 8 connections while 50 workers all wait on the DB, raising `maxPoolSize` from 12 to 50 may just build another queue **at the connection pool**. Queue sizing must consider end-to-end serving capacity, not just worker count in one bean.

## 13. Measure Queue Wait Instead of Measuring Queue Size Alone

There is no single `queueCapacity` good for all traffic patterns. During load testing, track at least:

| Metric | Question It Helps Answer |
|---|---|
| Current and peak `queue.size` | Is it frequently hitting the cap? |
| `activeCount`, `poolSize`, `maxPoolSize` | How many workers are serving and how much headroom exists to scale? |
| Task wait time p50/p95/p99 | Are tasks starting within budget? |
| Task execution time p50/p95/p99 | Is the bottleneck the queue or the work itself? |
| Completion throughput and arrival rate | Is work accumulating? |
| Rejected task count / rejection rate | Where did the system exceed limits? |
| Heap, GC pauses, retained size by payload | Is the queue holding too many objects? |
| Timeouts, cancellations, deadline-expired | How much work became useless from waiting too long? |

`ThreadPoolTaskExecutor` provides monitoring methods such as `getActiveCount()`, `getPoolSize()`, and `getThreadPoolExecutor()` (after initialization); the underlying executor exposes `getQueue().size()` and related counters. These values are point-in-time observations, not an atomic snapshot of the entire system.

**Measuring queue wait accurately:** record a monotonic timestamp (e.g., `System.nanoTime()`) when the task is accepted/submitted and a timestamp when it **actually starts executing**, then take the difference. Do not measure from HTTP request arrival as queue wait if other steps occur between request intake and submission. For rejected tasks, record them separately since they have no start timestamp.

In Spring you can use `TaskDecorator` to wrap `Runnable` and measure time until execution starts, bearing in mind that the task passed to the decorator may be a framework wrapper (especially with `submit`); do not assume catching exceptions in the wrapper will catch every task failure. Errors from `Future` must be observed through proper mechanisms.

### 13.1. Load Validation Pattern

1. Run at low load to measure processing time and heap retention when the queue is nearly empty.
2. Generate short bursts to measure peak queue depth and drain time.
3. Sustain load near capacity to observe p95/p99 queue wait, GC, and worker counts.
4. Apply controlled sustained overload to verify rejection policy and caller-side error paths.
5. Increase payload sizes and I/O latency to validate `B_task` and `μ_effective` estimates.
6. Test cancellation, shutdown, redeploys, and tasks with side effects; ensure useless work does not occupy slots indefinitely.

Change only one related group of parameters at a time (e.g., queue and thread bounds after measuring), comparing p99 and errors rather than average throughput alone.

## 14. Common Mistakes When Choosing queueCapacity

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Setting a huge queue "to avoid rejecting tasks" | Merely shifts overload to heap and wait time | Set memory/time budgets and handle rejections |
| Counting items while forgetting captured payloads | One task can retain an entire request or large array | Profile retained heap of real tasks |
| Using `-Xmx` as the entire queue budget | Heap also needs GC headroom, caches, and running tasks | Allocate `M_queue` after subtracting other loads |
| Using Little's Law to guarantee p99 | The relation holds for steady-state averages | Measure p99 queue wait directly |
| Raising `maxPoolSize` with a nearly unbounded queue | Pool prefers queueing after core instead of adding workers | Configure an appropriately bounded queue |
| Using `queueCapacity=0` without bounding `maxPoolSize` | Can spawn excessive threads as load grows | Set explicit max and rejection policy |
| Failing to plan for rejected tasks | Critical tasks may be lost or callers fail | Design backpressure, errors, and retry/idempotency |
| Using `CallerRunsPolicy` thinking it stays async | Tasks may run directly on the request thread | Weigh latency contracts and shutdown behavior |
| Measuring only average queue size | Misses bursts, p99, and expired queued tasks | Measure peak queue, wait time, rejections, and GC |
| Enlarging queue when downstream is already overloaded | Adds zero serving capacity | Find the bottleneck and throttle input |
| Using in-memory queue for work that must survive restarts | Heap queues are not durable | Use an appropriate durable job store |
| Picking config once and forgetting it | Traffic and task sizes evolve over time | Monitor, load test, and tune systematically |

## 15. Practice Exercises

**Exercise 1 — Computing Both Budgets.** A pool has a 12 MiB queue budget, tasks retain roughly 64 KiB, measured processing rate is 50 tasks/s, and acceptable wait time is 0.2 s. Compute `Q_memory`, `Q_time`, and the candidate `queueCapacity`. Why would picking based on memory alone be dangerous?

**Suggested Answer:** `Q_memory = floor(12×1024/64)=192`; `Q_time=floor(50×0.2)=10`; candidate is at most 10 in the simple model. Measure p95/p99 and keep margin.

**Exercise 2 — Will Max Pool Grow?** A pool has `corePoolSize=2`, `maxPoolSize=10`, a nearly unbounded queue, and 100 long tasks arrive in a burst. Explain why most tasks may queue and the pool does not jump to 10 workers.

**Suggested Answer:** After creating two core workers, `ThreadPoolExecutor` prefers the queue; while the queue is not full, the algorithm has no reason to grow workers above core.

**Exercise 3 — Analyzing p99.** `QueueCapacity` is 16 and measured throughput is 80 tasks/s. Can you claim 99% of tasks will never wait more than 200 ms? Give at least three reasons why that conclusion fails.

**Suggested Answer:** No. Task duration variance, busy workers, GC, slow I/O, bursts, throughput shifts, or other queues all make p99 diverge from average estimates.

**Exercise 4 — Running the Java 17 Experiment.** Compile `BoundedQueueDemo.java`, change queue size from 2 to 3 while still submitting four tasks. Predict when rejection happens if a fifth task is added while the worker still waits on the latch.

**Suggested Answer:** With 1 worker and queue size 3, tasks 2/3/4 are queued, and the fifth task is rejected while the worker remains blocked.

**Exercise 5 — Adjusting for Larger Payloads.** A new task captures a 2 MiB image in its closure. If the queue still allows 1,000 items, what is the risk? Propose one way to reduce retained heap and one way to prevent work loss when the queue fills.

**Suggested Answer:** The queue could hold several GiB of image data before overhead; pass only an ID or durable reference, bound the queue, and use rejection handling with proper signaling or durable job persistence.

**Exercise 6 — Resource-Dependent Scenario.** Tasks need a DB connection, but the DB pool allows only 8 connections while the executor has 40 workers. If p99 climbs, should you immediately raise `queueCapacity`? Explain what to measure first.

**Suggested Answer:** Not automatically. Measure connection wait time, DB throughput, active workers, and `Wq`; a larger queue only hides the bottleneck if the DB is already saturated.

## 16. Configuration Decision Process in Projects

Apply six steps in order:

1. **Define the contract:** must tasks finish fast, can they be rejected, do they have deadlines, must they survive restarts.
2. **Measure size and timing:** distribution of retained bytes per queued task; distribution of worker execution time; arrival rate and bursts.
3. **Allocate budgets:** heap bound for the queue after reserving space for other components, and queue wait bound derived from SLOs.
4. **Compute candidate:** `min(Q_memory, Q_time)`, factoring in safety margins and burst tolerance. If a larger buffer than the time limit is required, change the design/intake approach or SLO agreement rather than blindly enlarging the queue.
5. **Configure cohesively:** `corePoolSize`, `maxPoolSize`, `queueCapacity`, and rejection policy must align; account for downstreams too.
6. **Test and monitor:** p95/p99 queue wait, queue depth, rejections, heap/GC, timeouts, and burst recovery time; tune based on evidence.

Remember the rule: **a queue is a budget for waiting work, not a source of processing capacity.** Choose capacity from memory headroom **and** acceptable wait time, then verify under real load.

### Official References

- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE 17 Javadoc — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 Javadoc — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html)
