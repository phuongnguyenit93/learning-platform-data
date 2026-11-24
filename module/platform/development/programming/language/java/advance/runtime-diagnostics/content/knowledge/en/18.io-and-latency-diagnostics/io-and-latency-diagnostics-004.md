# 18.4. Distinguishing Task Processing Time from Queue Wait Time

A request can take 800 ms to complete while the main processing code runs for only 30 ms. Most of the remaining time may have been spent **before a worker ever picked up the task**, due to a busy thread pool, a full queue, or another unavailable resource. Conversely, a task that starts almost immediately yet spends 800 ms inside `run()` may be waiting on I/O, a database connection, a lock, or an external service. The two symptoms require very different investigations.

In Java, accurate latency diagnostics begins by **defining clear time boundaries**: when work is accepted, when it enters the queue, when a worker actually starts executing it, and when it finishes. Never lump every duration together as "latency" and immediately conclude that business code is slow.

This lesson uses Java 17+ and `ExecutorService` / `ThreadPoolExecutor` as primary examples, while connecting to HTTP requests, asynchronous I/O, message queues, and JVM/JFR tooling. All table figures are illustrative examples unless explicitly noted as verified code output.

## 1. Four fundamental timestamps and three intervals to separate

Suppose a task has been accepted by the system for processing:

- `t_enqueue`: when the task is placed into or submitted to the scheduler/queue at our chosen measurement boundary.
- `t_start`: when a worker begins executing the task's logic (start of `Runnable.run()` or `Callable.call()`).
- `t_finish`: when the logic completes or terminates with an error.
- `t_response`: when the caller receives the final result, if there is a downstream response/network step.

The intervals (using a common clock within one JVM):

```text
     submit/accepted             worker starts                     task finishes
t_enqueue ────────────────────── t_start ────────────────────────── t_finish
           <--- queue wait --->           <--- execution time --->
           <---------------- task residence / sojourn ----------->

task_queue_wait     = t_start  - t_enqueue
task_execution_time = t_finish - t_start
task_total_time     = t_finish - t_enqueue
task_total_time     = task_queue_wait + task_execution_time
```

The final identity **holds for each individual task** when all three timestamps share the same unit/clock and consistent boundaries. If a task never starts (rejected, cancelled, or timed out in the queue), there is no `t_start`/`t_finish` in this sense; never arbitrarily assign `execution = 0` and mix it into statistics for successfully completed tasks.

`task_execution_time` here is **wall-clock elapsed time** during task execution. It includes time spent blocked on I/O, waiting for locks, waiting on downstream calls, descheduled by the OS, or paused by the JVM. It is **not CPU time**. Measuring thread CPU time requires different tools and has a different meaning.

### End-to-end latency also includes segments outside the executor queue

For an HTTP request:

```text
client sends ── network / accept ── server receives ── admission ── executor queue
                                                                          │
                                                                          ▼
                                                                  worker processes
                                                                          │
                                                                          ▼
                                                  serialize/write response ── network ── client receives
```

Client-measured `response_latency` also includes network, middleware, admission, serialization, response writing, and other queue layers. If you measure only `executor_task_total_time`, do not treat it as total response latency. If you start the clock **before the task actually enters the queue**, the measurement also includes wrapper creation, submission overhead, and admission policy; name the metric to match the exact starting point.

## 2. Example of three tasks with identical total time but different causes

| Scenario | `t_enqueue` | `t_start` | `t_finish` | Queue wait | Execution | Task total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A — slow I/O processing, picked up immediately | 0 ms | 5 ms | 805 ms | 5 ms | 800 ms | 805 ms |
| B — busy workers, fast logic | 0 ms | 770 ms | 805 ms | 770 ms | 35 ms | 805 ms |
| C — both queue wait and downstream wait | 0 ms | 400 ms | 805 ms | 400 ms | 405 ms | 805 ms |

If a dashboard only shows "805 ms/task," all three look identical. Separating the two intervals shows:

- **A:** hunt for the source of high `execution_time`: socket reads, file I/O, DB queries, locks, blocking calls, or CPU-bound work.
- **B:** processing code took only 35 ms; investigate why the queue backed up: arrival bursts, too few workers, other tasks holding workers too long, or backlog.
- **C:** address **both**: relieve queue pressure and investigate worker logic/downstream latency.

Users can experience high p99 latency due to queuing even when **p99 execution** of tasks stays low. Optimizing a SQL query that already takes only 10 ms will have little impact if requests wait 900 ms just to start executing.

## 3. Where does queue wait occur in Java's `ThreadPoolExecutor`?

With `ThreadPoolExecutor`, `execute()` accepts a `Runnable` and the executor decides whether to run immediately, create a worker, or place the task in a `BlockingQueue`. Under the Java 17 model:

1. If running workers are below `corePoolSize`, the pool normally prefers creating a worker to run the new task.
2. Once core count is reached, the pool prefers queuing the task (if the queue accepts it).
3. When the queue cannot accept it, the pool can create extra workers up to `maximumPoolSize`; after that, `RejectedExecutionHandler` applies.
4. With `SynchronousQueue`, handoff is direct; there is no task backlog queue the way `ArrayBlockingQueue` works.

Hence, **a positive queue wait is not mandatory for every task**. A task can begin almost at submission time or sit for hundreds of milliseconds. `maximumPoolSize` **will not grow the thread count** if an unbounded queue always accepts incoming tasks. For instance, `Executors.newFixedThreadPool(n)` uses an effectively unbounded queue by design; backlog can build up long before any rejection happens.

| Queue / policy configuration | Typical behavior | Measurement implications |
| --- | --- | --- |
| `ArrayBlockingQueue(capacity)` | Fixed capacity; when full and the pool cannot expand, rejects or runs fallback policy. | Can observe queue length + queue wait + rejected count. |
| Practically unbounded `LinkedBlockingQueue` | Tasks can accumulate long when arrival rate exceeds processing capacity. | `queue wait` and heap/backlog can grow; `maxPoolSize` never helps in this setup. |
| `SynchronousQueue` | Direct handoff, stores no traditional backlog. | Queue size usually hides pressure; watch thread growth/rejections and submit latency. |
| `CallerRunsPolicy` | When unable to accept a task, **the calling thread** executes it. | Runnable queue wait may look very low while **caller latency** spikes; measure submit/admission latency. |
| `AbortPolicy` | Tasks are rejected with `RejectedExecutionException` when not accepted. | Rejected tasks have no execution time; track with a separate metric. |

`getQueue().size()` returns an instantaneous snapshot that changes constantly; `getActiveCount()` and `getTaskCount()` are **instantaneous estimates/observations**, not substitutes for a **per-task queue wait histogram**. A small queue size does not rule out high p99 wait when sampling sparsely, batching, or dealing with hidden upstream queues.

## 4. Measuring accurately with `System.nanoTime()`

Within a single JVM, `System.nanoTime()` is the high-resolution clock meant for measuring **elapsed time**; it has an arbitrary origin, not a Unix timestamp. Correct usage:

```java
long queuedAt = System.nanoTime();

// submit/queue...

long startedAt = System.nanoTime();

// task work...

long finishedAt = System.nanoTime();

long queueWaitNs = startedAt - queuedAt;
long executionNs = finishedAt - startedAt;
long totalNs = finishedAt - queuedAt;
```

The snippet above **illustrates the flow along one task's path**, not a standalone runnable program. Capture `queuedAt` right on the submitting side and `startedAt` at the start of the wrapper inside the worker; if both are recorded inside `run()`, "queue wait" measures only a few instructions in the same worker and completely misses queue residence time.

- **Subtract** two `nanoTime` readings within the same JVM. Never directly compare `nanoTime` values across two JVMs/containers; each JVM has an arbitrary origin.
- Nanosecond units **do not mean 1 ns clock accuracy**. OS, scheduler, clock resolution, and instrumentation all affect measurements.
- When converting to milliseconds: `double ms = nanos / 1_000_000.0`. Integer division or `TimeUnit.NANOSECONDS.toMillis` truncates sub-millisecond portions downward.
- `Instant.now()`/`currentTimeMillis()` are suitable for attaching **calendar timestamps** and correlating logs, but are subject to clock adjustments. Within the same JVM, `nanoTime` is better suited for intervals.
- For traces across services, use synchronized clocks/timestamps and document clock skew; never subtract machine B's `nanoTime` from machine A's.

To avoid skewing metrics on exceptions, record `finishedAt` in `finally`; if a task has multiple return paths, never instrument only the "happy path."

## 5. Java 17+ — complete example measuring queue wait and execution

The example below creates a `ThreadPoolExecutor` with **one worker** and a bounded queue. The first task holds the worker via a `CountDownLatch`. Meanwhile, a second task is submitted and must wait; when the worker is released, the second task runs for roughly 40 ms. The example uses latches to produce an observable queue wait, not to simulate real I/O.

Save as `QueueTimeDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class QueueTimeDemo {
    record Timing(long queuedNs, long startedNs, long finishedNs) {
        double queueWaitMs() {
            return (startedNs - queuedNs) / 1_000_000.0;
        }

        double executionMs() {
            return (finishedNs - startedNs) / 1_000_000.0;
        }

        double totalMs() {
            return (finishedNs - queuedNs) / 1_000_000.0;
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4));

        CountDownLatch workerOccupied = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            Future<?> blocker = pool.submit(() -> {
                workerOccupied.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            // Ensure the first worker has started running.
            workerOccupied.await();

            // Timestamp taken immediately before submitting the second task.
            long queuedAt = System.nanoTime();
            Future<Timing> measured = pool.submit(() -> {
                long startedAt = System.nanoTime();
                try {
                    Thread.sleep(40);
                } finally {
                    // Do not record metric here since we need to return after try.
                }
                long finishedAt = System.nanoTime();
                return new Timing(queuedAt, startedAt, finishedAt);
            });

            // Keep the worker busy for roughly another 100 ms.
            Thread.sleep(100);
            releaseWorker.countDown();

            Timing t = measured.get();
            blocker.get();

            System.out.printf(
                    "queueWaitMs=%.1f executionMs=%.1f totalMs=%.1f%n",
                    t.queueWaitMs(), t.executionMs(), t.totalMs());
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac QueueTimeDemo.java
java QueueTimeDemo
```

**Illustrative output**, not fixed deterministic numbers:

```text
queueWaitMs=102.7 executionMs=40.3 totalMs=143.0
```

Actual durations depend on the JVM, scheduler, and real `sleep` jitter; the sum of the three printed numbers can differ in the decimal place due to rounding. The exact identity at nanosecond resolution is `totalNs = queueWaitNs + executionNs`.

In the sample code, `queuedAt` is captured **right before `submit`**, so queue wait includes some submission and dispatch overhead. If you need strictly **time spent residing in the queue**, instrument the exact moment the task enters the queue and the moment it is dequeued; across different executors/queues, that boundary can vary. In practice, a pre-`submit` timestamp remains a useful "submission-to-start latency" metric as long as it is named clearly.

The `blocker` task simply occupies the worker for demonstration. In a real service, a preceding task might occupy a worker via DB reads, socket reads, locks, CPU work, or retry sleeps. Analysts must determine **why workers are busy** rather than mechanically adding workers.

### A safer variant covering task failures

In production, the wrapper must measure failed tasks too. General wrapper structure:

```java
static Runnable timed(Runnable delegate, java.util.function.BiConsumer<Long, Long> sink) {
    long queuedAt = System.nanoTime();
    return () -> {
        long startedAt = System.nanoTime();
        try {
            delegate.run();
        } finally {
            long finishedAt = System.nanoTime();
            sink.accept(startedAt - queuedAt, finishedAt - startedAt);
        }
    };
}
```

This is an **illustrative method**, not a standalone file; `sink` receives `queueWaitNs` and `executionNs`. It works whenever the task actually runs. If a task is cancelled in the queue or rejected, the callback is never invoked; add `rejected`/`cancelled`/`timed_out_before_start` counters at the submit/admission layer.

In production, prevent `sink` from throwing an exception that masks `delegate`'s original failure; metric sinks should be lightweight with explicit error handling. To measure "task start until success or failure," capture `finishedAt` in `finally` as above so severe exception tails are not dropped.

## 6. Java 17+ — numeric exercise with exact stdout

To verify the formulas without depending on thread scheduling, use **hypothetical** timestamps instead of `System.nanoTime`. Save as `LatencyMath.java`:

```java
public final class LatencyMath {
    public static void main(String[] args) {
        long enqueuedMs = 120;
        long startedMs = 610;
        long finishedMs = 650;

        long waitMs = startedMs - enqueuedMs;
        long executionMs = finishedMs - startedMs;
        long totalMs = finishedMs - enqueuedMs;

        System.out.printf("queue=%dms execution=%dms total=%dms%n",
                waitMs, executionMs, totalMs);
    }
}
```

Run:

```bash
javac LatencyMath.java
java LatencyMath
```

**Exact stdout:**

```text
queue=490ms execution=40ms total=530ms
```

The math shows a task took 530 ms while executing for only 40 ms; shaving 5 ms off processing code will barely matter if the backlog holds tasks for nearly half a second. In real measurements, the three timestamps must share a relative origin; this example solely demonstrates the addition/subtraction logic.

## 7. With I/O, "execution time" can still be mostly waiting

Here is a common pitfall: when a `Runnable` calls `InputStream.read()` and the thread blocks for 500 ms, all 500 ms still lie between `t_start` and `t_finish`. That means **processing/execution wall time** can be high even when actual CPU usage is tiny.

Example of a database-querying task:

```text
t_enqueue → (wait in executor 120 ms) → t_start
    → (wait on connection pool 60 ms)
    → (SQL query / network round-trip 380 ms)
    → (map result 20 ms)
    → t_finish
```

Then:

- Executor queue wait = **120 ms**.
- Execution wall time = `60 + 380 + 20 = 460 ms`.
- Task total = **580 ms**.
- "CPU data processing" in this example is represented only by the 20 ms mapping step, and even that 20 ms can include scheduling/GC and does not necessarily equal CPU time.

**There are multiple nested queues**: executor queues, database connection pool queues, upstream message brokers, servlet accept queues, HTTP client connection pools, network device queues, and OS disk queues. Measuring only one layer misses the rest.

| Waiting point | Where it falls in the model above | Required metric |
| --- | --- | --- |
| Request waiting to be accepted or admitted | May be **before** `t_enqueue`. | ingress/accept/admission latency, pending requests. |
| Task sitting in `ThreadPoolExecutor` queue | `t_enqueue → t_start`. | `executor_queue_wait`, queue depth, active workers. |
| Worker waiting to acquire DB connection | **Inside** the task's `execution_time`. | `db_pool_acquire_wait`, active/idle/pending connections. |
| Worker waiting on socket/file read | **Inside** `execution_time` if synchronous I/O. | `socket_read_duration`, `file_read_duration`, timeouts/bytes. |
| Worker waiting on lock or condition | **Inside** `execution_time`. | lock wait/thread state/JFR contention events. |
| Response waiting for writable socket or transmission | May be **after** `t_finish` depending on boundary. | response write time, client RTT, network wait. |

When using **asynchronous** APIs (`CompletableFuture`, NIO, reactive pipelines), `Runnable.run()` may only register I/O and finish in microseconds. Then the time from request receipt until **the future completes** is the logical operation latency; never treat the first callback's runtime as the whole business operation. Place distinct timestamps for I/O dispatch, completion receipt, callback scheduler queue wait, and response generation.

## 8. Distinguishing queue-induced latency from service-induced latency

| Observation | Priority hypothesis | Evidence to verify |
| --- | --- | --- |
| `queue_wait_p95` rises; `execution_p95` stays relatively stable | Executor backlog/saturation or arrival burst. | Active threads near limit, growing queue depth/oldest age, rejections/timeouts. |
| `queue_wait` low; `execution` rises alongside DB latency | Slow I/O/downstream once the task starts. | DB query duration, pool acquire wait, socket waits, JFR I/O events. |
| `queue_wait` rises after `execution` rises | Slow work holds workers longer, building a backlog. | Timeline: service time rose first; queue rose later; thread dumps show what workers are doing. |
| `execution` low; client latency still high | Time spent before enqueue, after finish, or in another async stage. | HTTP receive/dispatch/write timestamps, network, callback enqueue. |
| Queue depth near 0 yet rejections rise | Direct handoff/`SynchronousQueue` or admission limit, capacity/policy. | Queue config, active threads, `RejectedExecutionException`, rate limiter. |
| Large queue depth, high waiting, low CPU | Workers blocked on I/O/locks or downstream concurrency limit. | Thread states, DB pool pending, JFR `SocketRead`/`ThreadPark`, lock events. |
| Queue wait shifts sharply when worker count increases | Capacity/parallelism affects backlog. | Compare throughput/p95/errors under same load; watch for downstream overload. |
| Some tasks wait very long while others start immediately | Queue discipline, priority, long-running jobs, or starvation. | Break down by task type/priority; check FIFO, scheduled delays, and worker distribution. |

**Do not automatically expand the thread pool when queue wait is high.** If all workers are waiting on a database that only allows 20 connections, increasing workers from 50 to 200 can worsen contention, memory usage, and context switching. If tasks are CPU-bound and cores are already saturated, more threads also increase context-switching overhead. Base interventions on the measured bottleneck.

## 9. Metrics to emit from executors and I/O pipelines

For operations, use three telemetry groups:

**Per-task latency histograms:**

- `task_queue_wait_seconds`: submission/admission-to-start as defined.
- `task_execution_seconds`: start-to-finish wall time, including blocking.
- `task_total_seconds`: submission-to-finish.
- `task_timeout_before_start_total` and `task_rejected_total`: tasks that never started.
- If needed, add `db_connection_acquire_seconds`, `io_read_seconds`, `lock_wait_seconds`.

**Point-in-time gauges:**

- `executor_active_threads`, `executor_pool_size`, `executor_max_threads`.
- `executor_queue_depth`, `executor_queue_capacity`, **age of the oldest waiting task** if safely measurable.
- `db_pool_pending` / `db_pool_active`, connection count and limits.

**Counters and event correlation:**

- Submitted, started, completed, failed, cancelled, rejected, and timed out as separate outcomes.
- Request rate, task type, worker pool name, release version, deployment instance.
- Trace ID/correlation ID linking ingress → queue → start → downstream calls → completion.

Keep **units consistent**: exporters typically use seconds while code measures nanoseconds; `duration_seconds` must never hold millisecond values. Use bounded-cardinality labels such as pool name, task category, and result; never put raw request IDs, user IDs, or full URLs into time-series labels.

**Percentiles** `p50/p95/p99` need enough samples and a clear time window. If a 1-minute window has only 3 tasks, a `p99` number is unstable. Use mergeable histograms to aggregate across instances; never average per-instance p95s as cluster p95.

### An important math trap: p95s do not add

For **each task**: `total = queue + execution`. However, in general:

```text
p95(task_total) ≠ p95(task_queue_wait) + p95(task_execution)
```

Because tasks with high queue wait are not necessarily the same tasks with high execution time, and quantiles are not linear. To know total p95, measure or compute **the per-task sum and build a histogram of total**, rather than adding p95s on a dashboard.

Likewise, if tasks that never started timed out or were rejected, percentiles over **completed tasks** can look "great" while users are seeing errors. Always display rejections, timeouts, and cancellations alongside latency.

## 10. Load analysis using arrival rate and processing capacity

To see why queues grow, separate:

- `λ` (lambda): average task **arrival rate** per second.
- `E[S]`: average execution wall time per task, in seconds.
- `k`: number of workers able to execute tasks in parallel (for a homogeneous worker pool model).
- `ρ ≈ λ × E[S] / k`: relative utilization in a simple model where each task occupies one worker for `S` and the system is near steady state.

Example: 40 tasks/s, each task occupies a worker for 0.2 s on average, with 10 workers ⇒ `ρ ≈ 40 × 0.2 / 10 = 0.8` (80%). If arrivals increase to 55 tasks/s while execution stays 0.2 s, average demand is 11 workers—exceeding the 10-worker capacity; the queue will tend to grow or the system must reject/shed load per policy.

**This is an approximation**, not a p95 latency guarantee. Arrival bursts, service-time distributions, priorities, worker affinity, downstream resources, timeouts, and autoscaling can grow queues well below 100% average utilization. If service time grows because I/O blocks, `ρ` rises even while system CPU remains idle.

### Little's Law, when applied with proper boundaries

In a stable system with matching arrival and departure rates, **Little's Law** states:

```text
L = λ × W
```

Applied **solely to the queue**: `Lq = λ × Wq`, where `Lq` is the **average number of waiting tasks**, `Wq` is the **average wait time**, and `λ` is long-run throughput across the same boundary (tasks/s). Illustrative example: `λ=40 tasks/s` and `Wq=0.25 s` ⇒ `Lq≈10 tasks`.

Do not write `queueDepth_now ≈ rate_now × p95_wait`: Little's Law relates **long-run averages** when steady-state assumptions hold, not an equality between an instantaneous gauge and p95. During bursts or unbounded queue growth, steady-state assumptions break down.

## 11. How do JFR and thread dumps help tell them apart?

JFR reveals **what workers are doing once execution has begun**. Useful event groups (depending on settings/thresholds/collector/JDK):

- `jdk.SocketRead` / `jdk.SocketWrite`: recorded duration of socket I/O operations; only events meeting configuration thresholds are captured.
- `jdk.FileRead` / `jdk.FileWrite`: file I/O operations with durations and metadata.
- `jdk.JavaMonitorEnter`: monitor contention indicator, typically emitted only when wait exceeds threshold.
- `jdk.ThreadPark`: park/wait intervals in `LockSupport`, which can point to synchronizer waits.
- CPU execution samples and stack traces: highlight where workers are burning CPU.

Example starting a short recording on HotSpot JDK 17+:

```bash
# Replace <pid> with the real PID and verify write permission on the target JVM.
jcmd <pid> JFR.start name=queue_diag settings=profile duration=120s filename=/tmp/queue-diag.jfr

# After the file has been written:
jfr summary /tmp/queue-diag.jfr
jfr print --events jdk.SocketRead,jdk.FileRead,jdk.ThreadPark /tmp/queue-diag.jfr
```

Tool output depends on the actual file; **there is no fixed reference table**. A 400 ms `jdk.SocketRead` points to an I/O wait inside the worker, yet **does not tell how long the task waited in the queue before the worker started**. JFR by default does not know `t_enqueue` for arbitrary business `Runnable`s. Measuring queue wait requires **instrumenting the submit/start boundary itself**, as shown earlier.

A thread dump (`jcmd <pid> Thread.print` or `jstack` where supported) is a snapshot of stacks; a `WAITING` or `TIMED_WAITING` worker may be waiting on I/O/a synchronizer or sitting idle waiting for work. Do not conclude from a single thread dump that "all requests are stuck in the queue"; pair stacks with queue metrics and timestamps.

### Recording queue/execution with a custom JFR event

When you want per-task correlation without text-logging every request, you can define a custom JFR event with `queueWaitNanos`, `executionNanos`, task category, and outcome. Measure in the wrapper, commit the event after the task finishes, and choose appropriate thresholds/sampling to limit overhead.

Example **event class snippet**, not a complete program:

```java
@jdk.jfr.Name("demo.TaskLatency")
@jdk.jfr.Label("Task latency")
@jdk.jfr.Category({"Application", "Executor"})
public class TaskLatencyEvent extends jdk.jfr.Event {
    @jdk.jfr.Label("Queue wait nanos")
    public long queueWaitNanos;

    @jdk.jfr.Label("Execution nanos")
    public long executionNanos;

    @jdk.jfr.Label("Task category")
    public String category;
}
```

Inside the real measurement wrapper, populate fields and call `commit()` when the event is enabled. Do not expect a custom event to appear automatically in `.jfr` files unless `demo.TaskLatency` is enabled. Never attach sensitive payloads or arbitrary request IDs into JFR events, because recordings may be saved to disk and shared for investigation.

## 12. Async I/O and message brokers: do not draw boundaries in the wrong place

### 12.1. HTTP async/reactive pipelines

An HTTP handler invoking an async API may finish its initial callback quickly while a `CompletableFuture` continues waiting on the network. To avoid mismeasuring "processing," separate two metrics:

- `callback_execution_seconds`: wall time of a specific callback from worker start until that callback returns.
- `logical_operation_duration_seconds`: from request acceptance until **the future completes / the result is ready**.

You can also emit `callback_scheduler_queue_wait_seconds` if completion callbacks must wait on another executor. Measuring only the first callback can make a dashboard show 2 ms while users wait 900 ms.

### 12.2. Message queues/brokers

In Kafka/RabbitMQ/JMS, multiple milestones exist:

```text
producer creates message
 → sent to broker
 → broker stores/waits
 → consumer receives/polls
 → consumer local executor queue
 → handler starts
 → processing
 → ack/commit
```

**Broker queue age** is the interval from when the message was written to the broker until a consumer fetches it (per broker semantics). **Local executor wait** is from when the consumer submits the task to its executor until the handler starts. **Handler duration** is from handler start to processing finish. **Ack latency** may add time afterward. These are distinct metrics and should not all share the name `message_processing_time`.

For timestamps across two machines, watch out for clock skew, broker timestamp semantics (create time vs. append time), batching, and redelivery. If a message is reprocessed, decide whether to measure from first enqueue or current retry attempt; never mix them blindly.

### 12.3. Batch jobs and scheduled tasks

A scheduled task has `plannedAt`, `eligibleAt`, `actualStartAt`, and `finishedAt`. If the scheduler or workers are busy, `actualStartAt - plannedAt` is **schedule delay**, not necessarily purely executor queue wait. A batch of 1,000 records may wait to be enqueued piecemeal and then run in parallel; specify whether the measurement unit is **per batch** or **per item** so rates and durations remain meaningful.

## 13. Distinguishing three problems in an incident

### Case A — high queue wait, low execution

A service receives a burst of 500 requests/s; a 16-thread worker pool is busy and queue depth climbs. Metrics:

```text
queue_wait_p95 = 650 ms
execution_p95  = 40 ms
task_total_p95 = 675 ms
rejections     = 0
```

Illustrative numbers only. `task_total_p95` **must not be computed** by adding 650 + 40; it is measured independently per task. Investigate arrival bursts, capacity, task mix, and whether a few long tasks hold workers, and set sensible queue bounds and deadlines. If CPU is low while workers block on the network, revisit Case B as the root cause of the backlog.

### Case B — low queue wait, high execution

`queue_wait_p95 = 4 ms`, `execution_p95 = 820 ms`, DB connection acquire time `~300 ms`, socket read `~400 ms`. Expanding the worker pool can make things **worse** if the DB connection pool is already tight. Investigate DB load, timeouts, query plans, connection pools, and downstream dependencies; check which metric rose first.

### Case C — both rise over time

At 10:00 upstream database latency rises, making each task hold a worker longer. By 10:02 executor queue depth and queue wait spike because workers are not being freed. Dashboards show total latency rising, yet the timeline proves **execution rose first and queue wait followed**. Focus fixes on upstream latency and concurrency limits/backpressure; merely enlarging the queue will lengthen wait times and consume resources.

## 14. Common measurement and interpretation mistakes

- **"The task ran for 20 ms, so the response must be 20 ms."** False: queue wait, network, admission, serialization, and async callbacks can add substantially.
- **"Execution time equals CPU time."** False: wall time inside `run()` includes I/O blocking, lock waits, GC pauses, and scheduler delays.
- **"Queue wait equals `queue.size()`."** False: size is a count while wait is a duration; measure per task.
- **"Taking `nanoTime()` at the start and end of `run()` is enough to measure queue wait."** False: that measures only execution.
- **"ISO timestamps across two JVMs can always be subtracted accurately."** False: clock skew and adjustments distort results; record clock sync context.
- **"Adding workers always reduces queue wait."** False: it can push more I/O downstream, increasing contention and execution time.
- **"Queue size 0 means zero pressure."** False: `SynchronousQueue`, sparse sampling, and rejections can hide admission overload.
- **"Executor `maxPoolSize` is always exhausted before queuing."** False: behavior depends on core size, queue type, and saturation rules.
- **"`CallerRunsPolicy` means every task still runs on the worker pool."** False: callers end up running tasks, impacting submit latency and upstream callers.
- **"Total p95 equals queue p95 + execution p95."** False: quantiles are not additive; measure per-task totals.
- **"Tasks cancelled in the queue have 0 ms execution so include them in the success histogram."** False: separate tasks that never started and report timeouts/cancellations separately.
- **"A 600 ms JFR `FileRead` means 600 ms queue wait."** False: I/O event durations occur **during execution**; submit-to-start queuing needs its own instrumentation.
- **"Async callback return means the request is done."** False: track completion of the entire logical operation.
- **"A single low `getActiveCount()` means the pool is healthy."** False: snapshots can miss bursts; use time series and histograms.
- **"p99 increased because of slow SQL."** Insufficient: check `queue_wait`, `execution`, DB acquire, socket read, and downstream traces in the same window.
- **"Little's Law applies directly to instantaneous queue depth and p95."** False: it relates averages under specific steady-state conditions.

## 15. Practical investigation checklist

Before changing code or tuning thread pools, answer:

1. **Boundaries:** are you measuring executor queue wait, DB connection wait, broker lag, or full request latency? Where are `enqueue`/`start`/`finish`?
2. **Clocks:** are timestamps within one JVM via `nanoTime` or across machines? What are the units and error margins?
3. **Distributions:** how do `p50/p95/p99` of **queue wait**, **execution**, and **total** move independently? What about rejected/timed-out/cancelled counts?
4. **Queue:** what are the queue type, capacity, `corePoolSize`, `maximumPoolSize`, rejection handler, and oldest waiting task age?
5. **Workers:** do active/idle counts, thread states, CPU usage, and backlog move together?
6. **I/O:** how do DB pool acquire, queries, socket/file I/O, lock waits, timeouts, and downstream latency affect the execution segment?
7. **Async:** if using callbacks/reactive flows, has the logical operation completed or did only one callback return?
8. **Causal order:** did execution rise first causing queuing, or did an arrival burst raise queue wait while execution stayed stable?
9. **Verification:** re-measure under identical load after changing concurrency, queue bounds, backpressure, timeouts, or I/O optimizations; check both latency and errors/rejections.
10. **Reporting:** state instance, time window, sample size, units, formulas, and metric boundaries so others can reproduce your findings.

**Remember:** `queue_wait` answers **"how long did the task wait before a worker started it?"**; `execution_time` answers **"how long did the worker hold the task, including blocked time?"**; task `total_time` is **the per-task sum of the two**, while response latency can be longer still. Measuring these two intervals separately—alongside queue depth, rejections, and I/O telemetry—prevents optimizing the wrong layer and uncovers the true source of latency.

### References

- [Oracle Java 17 — ThreadPoolExecutor (queuing, pool size, rejection, monitoring)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle Java 17 — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java 17 — ThreadMXBean (CPU time vs. wall time)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java 17 — Java Flight Recorder Consumer APIs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html)
- [OpenTelemetry — Messaging semantic conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
