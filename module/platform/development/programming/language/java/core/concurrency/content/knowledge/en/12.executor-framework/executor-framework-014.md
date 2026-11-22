# Distinguishing User Task Concurrency from Thread Pool Concurrency

In Java, **the number of user requests still being processed** (*user task/request concurrency*) and **the number of tasks currently being executed by workers in a thread pool** (*thread pool concurrency*) are two **different** quantities. A system can have 200 in-flight user requests while an `ExecutorService` has only 8 worker threads. Conversely, a single request can split into 20 subtasks and submit them to an executor, making the number of tasks larger than the number of requests.

The misconception that “100 concurrent users require a pool of 100 threads” can lead to too many threads, queue buildup, CPU/memory pressure, increased latency, or database bottlenecks. A proper understanding requires distinguishing **business requests**, **submitted/accepted tasks**, **queued tasks**, **executing tasks**, **worker threads**, and **CPU parallelism**. These concepts are related, but they are **not interchangeable**.

This article uses general Java concurrency with Java 17+, without depending on any framework or Spring-specific concurrency components.

## 1. Defining User Task Concurrency

“User task concurrency” is not the name of an official property in the `ExecutorService` API. Here it represents **the amount of business-level work existing at the same time**, whose counting method is decided by the program.

A **request/workflow** can be counted as in-flight from the moment it is accepted until it has responded or completed its final work, depending on the contract. During that interval, the request may be:

- Running CPU code.
- Waiting for the queue to have an available worker.
- Waiting on I/O, a database, the network, or an asynchronous result.
- Splitting into multiple subtasks and waiting to aggregate the results.
- Timed out on the caller while the background job is still running, if the application has not cancelled the job.
- Returning a response early and handing off separate background work: the request is done, but the background job is still in-flight.

**An online user** is not **an active request**. One user may send multiple requests concurrently or none at all. Multiple users may also share a single batch job. If a system needs to track “user concurrency,” it must specify clearly **whether it is counting sessions, requests, workflows, or background jobs**.

### In-flight boundaries must be consistent

For example, a request starts when receiving input and ends when the response has been sent:

```text
Request received
    -> validate
    -> submit task A
    -> queue wait
    -> task A runs
    -> wait result
    -> response sent
Request completed
```

If the business workflow continues after the response, a separate **background jobs in-flight** metric is needed. If a request creates parallel subtasks, do not add the number of subtasks to the number of users and call all of them “concurrent users.”

## 2. Defining Thread Pool Concurrency

`ThreadPoolExecutor` manages a set of workers that execute accepted `Runnable` or `Callable` instances. At a given point in time, tasks can be:

1. **Accepted**: the executor has accepted the task, not necessarily running it immediately.
2. **Queued**: waiting in the pool's `BlockingQueue<Runnable>`.
3. **Executing**: a worker is running `run()`/`call()`.
4. **Completed/failed/cancelled**: lifecycle states according to a specific contract.

These are **labels for reasoning**, not a JDK task-state enum. A cancelled task may never have started; cancellation of a `Future` may also be observed before the worker has exited `finally`. Therefore, a clear **completion point** must be defined when measuring.

In a fixed pool with 4 platform workers, **at most 4 task bodies** are typically executing at the same time **on those workers**. However, the number of accepted tasks could be 1,000 because 996 tasks are waiting in the queue. If a worker is waiting on a remote API, it is still **occupied by the task** and cannot run another task yet, even though the CPU may be idle.

**Caution:** `CallerRunsPolicy` or code that creates threads outside the pool can cause a task body to execute **outside the worker pool**. Therefore, you must distinguish between “maximum number of task bodies on pool workers” and “total number of task bodies running concurrently across all threads in the application.”

## 3. Distinguishing Concurrency and Parallelism

| Concept | Question | What not to infer |
| --- | --- | --- |
| **Concurrent business requests** | How many user workflows have not finished yet? | Does not equal the number of Java threads |
| **Outstanding executor tasks** | How many tasks have been accepted but not yet completed? | Does not equal the number of active workers |
| **Queued tasks** | How many tasks do not have a worker yet? | Not CPU work currently running |
| **Active pool workers** | Which workers are executing a task body? | Does not guarantee the worker is using CPU |
| **CPU parallelism** | How many computations are actually running on cores? | Does not equal total threads or futures |
| **Asynchrony** | Can the caller continue without waiting for the result? | Does not mean the supplier inside is non-blocking |

A task can be **executing** while calling `Thread.sleep`, `Future.get`, `CountDownLatch.await`, or waiting on I/O. The worker is held, but it is not performing CPU computation. A `CompletableFuture.supplyAsync` returns a `Future` to the caller immediately, yet the supplier may execute synchronous blocking I/O on the worker.

## 4. Four Typical Numbers in a Pool

Suppose the caller submits 6 tasks to a `ThreadPoolExecutor` with exactly 2 workers and a queue with 4 slots. Two tasks run/wait on workers; 4 tasks are queued:

```text
                  Executor (pool of 2)
                       |
submit 6 tasks --------+
                       |
                 +-----+------+
                 |            |
              Worker 1     Worker 2
               Task A       Task B
                 |            |
                 +-----+------+
                       |
             queue: [C, D, E, F]

Accepted tasks  = 6
Executing tasks = 2
Queued tasks    = 4
Workers in pool = 2
```

If **each task comes from a separate request**, there may be 6 requests in-flight. If **one request submits all 6 tasks**, there is only 1 request, 6 executor tasks, and 2 executing workers.

A self-defined accounting calculation:

```text
outstanding accepted tasks = accepted tasks - actually completed tasks
roughly: outstanding ≈ queued + executing
```

In production, metrics are often snapshots taken at different times, and cancellation, rejection, task stealing, transfer, and caller-runs change how counts behave. Thus, this is a **reasoning model**, not an invariant that always holds strictly for every executor getter.

## 5. Java 17: Measuring 6 Accepted, 2 Executing, 4 Queued

Instead of using `Thread.sleep(100)` to guess that “two tasks are running,” the program below uses `CountDownLatch` to block two workers at a deterministic checkpoint. `main` captures the numbers **before** opening the gate.

Create the file **`TaskVsPoolConcurrencyDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class TaskVsPoolConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger executing = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4));

        int accepted = 6;
        try {
            for (int i = 0; i < accepted; i++) {
                pool.execute(() -> {
                    executing.incrementAndGet();
                    twoStarted.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        executing.decrementAndGet();
                        completed.incrementAndGet();
                    }
                });
            }

            if (!twoStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }

            System.out.println("accepted=" + accepted);
            System.out.println("executing=" + executing.get());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println(
                    "inFlight=" + (accepted - completed.get()));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
        System.out.println("completed=" + completed.get());
    }
}
```

Compile/run on JDK 17+:

```bash
javac TaskVsPoolConcurrencyDemo.java
java TaskVsPoolConcurrencyDemo
```

Stdout **when the program completes normally before timeout**:

```text
accepted=6
executing=2
queued=4
inFlight=6
completed=6
```

**Why is the output predictable?** The first two tasks increment `executing`, signal `twoStarted`, and then wait on `release`. Because both workers are waiting on the latch, the remaining four tasks **cannot be taken from the queue** before `main` prints the numbers. `main` then releases `release` in `finally`, calls `shutdown`, and then `awaitTermination`. Only after all six tasks complete does it print `completed=6`.

Note that `executing=2` here means “two task bodies have started and have not finished”; in reality both are **WAITING** on the latch and are not using CPU to process business logic. Monitoring getters such as `getActiveCount()` and `getQueue().size()` can be snapshots that change immediately in production, but this test intentionally holds state steady to explain the concept.

This is a coordination experiment, **not a throughput benchmark**.

## 6. Fan-out: One Request Can Spawn Many Executor Tasks

For example, three requests each need two subtasks:

```text
User request A --> subtask A1 + subtask A2
User request B --> subtask B1 + subtask B2
User request C --> subtask C1 + subtask C2

Business requests = 3
Submitted subtasks = 6
Fixed pool workers = 2
```

Depending on the scheduler and execution time, only a subset of subtasks are processed by workers at the same time. If requests create 10 subtasks each and there are 500 requests in-flight, the workload can create up to 5,000 outstanding subtasks, which **does not mean the pool has 5,000 threads**.

### Java 17: CompletableFuture fan-out, fan-in

Create `FanOutExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class FanOutExample {
    public static void main(String[] args) throws Exception {
        int requests = 3;
        int subtasksPerRequest = 2;
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            List<CompletableFuture<Integer>> futures =
                    new ArrayList<>();

            for (int r = 0; r < requests; r++) {
                for (int part = 0; part < subtasksPerRequest; part++) {
                    futures.add(CompletableFuture.supplyAsync(
                            () -> 1, pool));
                }
            }

            CompletableFuture.allOf(
                    futures.toArray(new CompletableFuture<?>[0])
            ).join();

            int sum = futures.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("requests=" + requests);
            System.out.println("subtasks=" + futures.size());
            System.out.println("sum=" + sum);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
    }
}
```

Run:

```bash
javac FanOutExample.java
java FanOutExample
```

Stdout:

```text
requests=3
subtasks=6
sum=6
```

Each subtask returns an `int` equal to 1, and `main` aggregates after `allOf` completes. `join()` here is on **`main`**, not on a worker of that same pool; the workers remain free to run the remaining subtasks. `requests=3` is **a simulated request count**, not a metric measured from a real server or a claim that all three occupy workers simultaneously.

**Key takeaway:** `CompletableFuture` provides composition/asynchrony; it does not make a supplier non-blocking by default. If the supplier makes a synchronous HTTP call or calls `Thread.sleep`, it still occupies a worker during the wait.

## 7. `ThreadPoolExecutor` Configuration Determines Whether Tasks Run or Queue

Common constructor:

```java
new ThreadPoolExecutor(
    corePoolSize,
    maximumPoolSize,
    keepAliveTime,
    TimeUnit.MILLISECONDS,
    workQueue,
    rejectionHandler
);
```

This is a snippet without declared variables or concrete numbers. With a standard `ThreadPoolExecutor`:

1. If the number of workers is less than `corePoolSize`, the pool may create a worker to run the new task.
2. Once there are enough core workers, the pool tries to **enqueue the task**.
3. If the queue cannot accept more tasks and the number of workers has not reached `maximumPoolSize`, the pool may create an additional worker.
4. If neither workers nor the queue can accept the task, the rejection handler is invoked.

This is very important: **`maximumPoolSize` is not the number of threads guaranteed to be created immediately**. With an **unbounded queue**, once core workers exist, the pool typically queues tasks and does not need to expand to maximum.

### Common factory methods

| API | Model | Risks/limitations |
| --- | --- | --- |
| `Executors.newFixedThreadPool(n)` | n platform workers; excess tasks typically wait in an unbounded queue | Queue can grow unboundedly and cause long latency/memory pressure |
| `Executors.newSingleThreadExecutor()` | Runs tasks sequentially | One slow task makes all others wait |
| `Executors.newCachedThreadPool()` | Creates more workers when demand increases, with reuse | Thread count can spike sharply if admission is not bounded |
| `Executors.newScheduledThreadPool(n)` | Runs delayed/periodic tasks | Many scheduled items do not mean many workers |
| Custom `ThreadPoolExecutor` | Choose core/max, bounded queue, rejection | Must manage saturation/backpressure explicitly |
| `newVirtualThreadPerTaskExecutor()` (Java 21+) | One virtual thread per task | Not available on Java 17; downstream resources remain finite |

**Do not choose a factory based solely on the API name.** You need to know the number of tasks, CPU/blocking time, burstiness, queue semantics, and business limits.

## 8. Why Increasing `maximumPoolSize` May Not Improve Latency

For example, `corePoolSize=4`, `maximumPoolSize=32`, and a very large queue capacity. Once there are four workers, subsequent tasks are typically **queued**. Only when the queue is full can worker creation up to maximum be triggered. Therefore, increasing maximum while leaving the queue never full may not increase actual concurrency.

Conversely, configuring a pool with a very small queue can create workers up to maximum faster, but **increases concurrent load on downstream systems**. If the DB only allows 10 connections, creating 100 I/O workers will not make the DB process 100 queries at once; those workers may end up queuing for a connection, wasting memory and context switching.

**Pool sizing is not a single-parameter problem.** You must consider:

- CPU cores and compute time.
- I/O/lock wait time.
- Queue waiting latency.
- Submission rate and bursts.
- Connection pools, network, DB rate limits.
- Memory/stack and thread management overhead.
- Timeouts, cancellation, SLAs.
- Behavior when full: reject, caller-runs, load shedding.

## 9. When the Queue Is Full: Rejection and Backpressure

A finite fixed pool cannot accept unlimited tasks without a cost. **Backpressure** forces producers to slow down, delay, or reject work when downstream capacity is insufficient.

Some strategies:

- **`AbortPolicy`**: throws `RejectedExecutionException` on saturation; the caller handles it.
- **`CallerRunsPolicy`**: when applicable, the task runs on the thread **calling `submit`/`execute`** instead of a pool worker, slowing the caller down.
- **`DiscardPolicy`**: drops the task; dangerous if the job must complete or carries important data.
- **`DiscardOldestPolicy`**: drops the oldest waiting task and retries accepting the new task; can break fairness or lose data.
- **Semaphore admission**: limits in-flight requests/jobs **before** submitting to the pool.
- **Bounded queue**: protects the heap from an unbounded backlog and provides a clear point to apply policy.

**Important note on CallerRuns:** the pool may have only 4 workers, but the caller **is also executing a task body**, so the application as a whole may have more than 4 tasks executing. This does not give the pool a fifth worker of its own. If the caller is an event-loop thread that must not be blocked, this policy can ruin latency across the entire system. During executor shutdown, `CallerRunsPolicy` makes no promise to always execute the task.

## 10. Java 17: One Worker, One Queue Slot, One Rejected Task

Create **`PoolSaturationExample.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolSaturationExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable task = () -> {
            firstStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                completed.incrementAndGet();
            }
        };

        int accepted = 0;
        int rejected = 0;
        try {
            pool.execute(task);
            accepted++;

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker not started");
            }

            pool.execute(task);
            accepted++;

            try {
                pool.execute(task);
                accepted++;
            } catch (RejectedExecutionException expected) {
                rejected++;
            }

            System.out.println("accepted=" + accepted);
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac PoolSaturationExample.java
java PoolSaturationExample
```

Stdout when the program completes normally:

```text
accepted=2
queued=1
rejected=1
completed=2
```

Explanation: one worker runs the first task and waits on `release`; the second task sits in the capacity-1 queue. The third task has no room left, so `AbortPolicy` throws an exception. `main` measures the queue while the latch is still closed; afterward it lets the two accepted tasks finish and waits for the executor to terminate.

There is no `Thread.sleep` hoping to trigger saturation; the ordering is guaranteed by the latch. This is an **API experiment**, not proof of pool performance under real load.

## 11. User Concurrency Exceeding Pool Concurrency Is Not Necessarily a Bug

Hundreds of outstanding requests can be acceptable when:

- Most requests wait on async results without holding a platform worker.
- There is a bounded queue and clear SLA bounds.
- Downstream has enough capacity to process at the average arrival rate.
- Backpressure/rejection is designed to prevent unbounded backlogs.
- Each request bounds fan-out and total in-flight tasks.

Conversely, **few concurrent requests can still cause overload** if each request creates hundreds of subtasks, slow I/O, unbounded retries, or tasks that hold large amounts of memory. Counting requests alone is not enough; you must count the workloads generated and the resources they are waiting on.

### Measurement units must be explicit

Does “Active=100” mean **100 requests**, **100 executor tasks**, **100 threads**, **100 DB connections**, or **100 subscriptions**? The same number 100 leads to completely different capacity designs.

## 12. CPU-bound vs. I/O-bound

**CPU-bound:** tasks mostly use the CPU. Adding far more workers than useful cores can increase context switches and cache misses, reducing throughput. A compute pool should be sized based on cores and contention levels, then benchmarked in practice.

**I/O-bound:** tasks mostly wait on network/database/file I/O. More workers than cores can be used because waiting threads do not consume CPU continuously. However, connection pool limits, bandwidth, and remote APIs still determine useful concurrency. Adding workers cannot fix an already overloaded downstream.

**Mixed workload:** CPU parsing and long I/O calls in the same pool can cause interference. If needed, separate stages or executors by workload, but total threads/processes and queues must still be managed; do not create many large pools arbitrarily.

**Do not equate `Thread.State.RUNNABLE` with “using CPU.”** A thread can be runnable without being scheduled onto a core; Java thread states and OS states are also not identical. Use a profiler/JFR to distinguish CPU, lock contention, and blocking I/O.

## 13. Nested Submission: Thread-Starvation Deadlock

A particularly subtle bug occurs when task A occupies a pool worker, submits task B **to the same pool**, and then blocks on `Future.get()` waiting for B. If all workers do this, no one is left to run B.

**Broken snippet — hangs if there is no timeout:**

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

Future<Integer> outer = pool.submit(() -> {
    Future<Integer> inner = pool.submit(() -> 42);
    return inner.get(); // The only worker waits for a task in the queue!
});

System.out.println(outer.get()); // May wait forever.
```

This is a snippet (requires imports `ExecutorService`, `Executors`, `Future`). The single-worker pool runs `outer`; `inner` is queued, but the worker is waiting for `inner`, so `inner` can never run. This is a **thread-starvation deadlock**, without necessarily having a cycle of intrinsic monitor ownership.

How to avoid it:

- If the work is small, call the sub-logic directly instead of submitting and blocking.
- For fan-out, create subtasks and **join on a coordinator that does not occupy a worker of that same pool**.
- Use asynchronous composition `thenCompose`/`allOf` properly instead of blocking `get` inside a pool worker.
- If using a separate executor for dependencies, calculate capacity/lifecycle clearly rather than simply doubling pools.
- Add timeouts and cancellation, though timeouts only help escape a wait—they do not fix a structural flaw.

**`CompletableFuture.supplyAsync(..., samePool).join()` inside a worker can still cause starvation.** Having `Async` in the method name does not make `join` non-blocking.

## 14. CompletableFuture Does Not Mean Non-blocking

`CompletableFuture.supplyAsync(supplier, executor)` lets the caller receive a future without waiting for the supplier to finish. However, the supplier may:

- Perform heavy CPU computation.
- Call `Thread.sleep`.
- Call a synchronous JDBC or HTTP client.
- Wait on a mutex or another `Future.get`.

If the supplier blocks, it still occupies an executor worker. When using `thenApply`, `thenApplyAsync`, `thenCompose`, and `thenComposeAsync`, you must know **which executor runs the next stage** and which stage may block. If no executor is specified for certain async methods, the JDK may use the common pool; therefore, tracking real resource usage cannot look at only a single application-created pool.

**Request concurrency** can continue to exist while the future is incomplete even though the caller thread has returned. Therefore, count requests by business lifecycle and count executor tasks by task lifecycle—do not use the number of futures as the number of users.

## 15. Limiting Business Concurrency Separately from the Pool

Suppose the business requires at most 100 active user requests and the pool has only 12 workers. You can use **`Semaphore` admission** at the request boundary so no more than 100 are admitted, while the 12-worker pool processes each stage.

Synchronous snippet:

```java
if (!requestPermits.tryAcquire()) {
    rejectBusy();
    return;
}

try {
    handleWholeRequest();
} finally {
    requestPermits.release();
}
```

Here `requestPermits` is a `Semaphore` and the methods represent application logic. If `tryAcquire` fails, **do not release**. If the request executes across **asynchronous stages**, the permit must be held until **the final workflow completes**, not released right after `submit` or as soon as the initiating callback returns.

A limiter for business work **does not replace** limits on database connections. You may need:

1. Max user requests in-flight.
2. Max outstanding tasks / bounded executor queue.
3. Max concurrent downstream I/O calls.
4. Per-user/tenant quota to prevent one source from consuming all resources.

These are four different admission layers, not four ways of setting the same `threadPoolSize` variable.

## 16. Measuring the Right Metrics for Requests and Executors

| Metric | Layer | Notes |
| --- | --- | --- |
| `activeRequests` | Business | Counted from accept to response/workflow completion |
| `inFlightJobs` | Business/background | Counts jobs still running after response, if any |
| `taskSubmitRate` | Executor | Tasks/s submitted to the pool |
| `acceptedTasks` | Executor | Accepted, not necessarily running yet |
| `rejectedTasks` | Executor | Rejected by policy, needs handling |
| `queuedTasks` | Queue | Snapshot of backlog waiting for a worker |
| `activeWorkers` | Executor | Workers executing a task body |
| `poolSize` | Executor | Number of workers currently managed by the pool |
| `largestPoolSize` | Executor | Highest pool size observed |
| `completedTaskCount` | Executor | Completed task count per pool metrics |
| `queueWaitMs` | Latency | Submit → task body start |
| `taskRunMs` | Latency | Task start → task body complete |
| `requestLatencyMs` | End-to-end | Request start → response |
| `blockedTime` | Runtime | I/O/lock/condition wait |
| `CPU load` | Host | Whether CPU is the bottleneck |
| `downstreamInFlight` | Resource | Connections/API calls currently in use |

`ThreadPoolExecutor.getActiveCount()`, `getCompletedTaskCount()`, and `getTaskCount()` are **approximate** monitoring values, not a consistent transactional snapshot. Do not combine them in a strict invariant check. For request accounting, instrument **start/end** according to business ownership and handle rejection, exceptions, timeouts, and cancellation as well.

### Little's Law aids capacity thinking, not thread counts

Under relatively steady load:

```text
Average in-flight requests ≈ completion rate × average request duration

Example:
100 requests/second × 0.2 seconds = 20 requests in-flight (average)
```

This is a relationship for **the number of requests in the system**, not a recommendation to create 20 worker threads. A request may wait on I/O, spawn subtasks, or not hold a worker for most of its duration. The formula also does not accurately describe a snapshot during unstable bursts or growing queues.

## 17. Timeouts, Cancellation, and Task Lifecycle

When a request times out after 2 seconds, a thread calling a remote API may keep running for a long time if the API lacks proper timeout/cancellation. In that case:

- The request metric may consider the request finished.
- The background task still holds a worker and a connection.
- The queue may grow even though the caller has abandoned the result.
- `future.cancel(true)` is a **cancellation request**, not a guarantee that the worker stops immediately.
- A cancelled `Future` may be reported before the worker exits `finally` and finishes resource cleanup.

Therefore, propagate deadlines across stages, use I/O APIs with timeouts, write cooperative cancellation with `finally`/try-with-resources, and **observe actual task termination**. Do not use `Thread.stop()` to force termination; it can break invariants and cause resource corruption.

In metrics, distinguish **request completed**, **task cancelled**, **worker stopped**, and **resource closed** when that distinction affects correctness.

## 18. Virtual Threads Change the Thread Type, Not the Demand

Since Java 21, `Executors.newVirtualThreadPerTaskExecutor()` typically creates a virtual thread per task, **not a fixed-size platform worker pool**. It makes scaling many blocking tasks easier in many cases, but:

- Each request can still spawn many virtual tasks.
- Many virtual threads do not equal the same number of OS/carrier threads or cores.
- CPU, heap, file descriptors, DB connections, and remote API quotas are still finite.
- You still need admission limiters/backpressure for downstream systems.
- Shared mutable state must still obey the Java Memory Model.
- Do not assume every blocking call has zero cost; different JDK runtimes/versions can have their own scheduling/pinning behaviors.

Virtual thread APIs are not available on Java 17; all earlier executable examples are compatible with JDK 17+.

## 19. Tuning and Load Testing

Do not increase pool size just because you see many requests. An evidence-based process:

1. **Define** where user/request in-flight starts and ends.
2. **Map fan-out**: how many tasks each request creates, and whether there are retries or nested waits.
3. **Classify workload**: CPU, I/O, mixed, lock contention.
4. **Measure** arrival rate, request latency, task queue wait, task runtime, rejection.
5. **Observe** `poolSize`, `activeCount`, queued tasks, `completedTaskCount`, CPU, heap.
6. **Observe downstream**: DB connection pool, API quota, network throughput.
7. **Choose bounded queue/admission** and define reject/busy/timeout behavior clearly.
8. **Tune** core/max to match queue behavior and deadlines; remember maximum does not always take effect with an unbounded queue.
9. **Load test** at multiple concurrent request levels; inspect p50/p95/p99, queue growth, throughput, starvation/fairness.
10. **Test shutdown/cancellation**: queued tasks, running tasks, and tasks that do not respond to interrupts.
11. **Review nested blocking** to prevent pool starvation.
12. **Check memory/resource limits** when fan-out increases or when moving to virtual threads.

Do not aim for pool `activeCount` to always equal maximum. An idle pool under low load is normal. The real goals are **latency, correctness, throughput, resilience, and resource bounds**.

## 20. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “100 concurrent users need 100 threads” | User sessions ≠ active requests ≠ worker tasks |
| “A 10-thread pool can only accept 10 tasks” | Many more tasks can sit in the queue |
| “`submit` returning means the task is already running” | An accepted task may be queued |
| “Active worker = using CPU” | The task may be waiting on I/O, a lock, or a latch |
| “One request always corresponds to one task” | Fan-out and retries spawn multiple subtasks |
| “More workers always increase throughput” | CPU/downstream may saturate; extra threads add overhead |
| “Increasing `maximumPoolSize` definitely adds workers” | The pool may queue after reaching core |
| “An unbounded queue never rejects, so it is safe” | Queue/memory/latency can grow without bound |
| “An async future is always non-blocking” | The supplier may block; `join()` blocks the caller |
| “Nested `Future.get` in the same pool is always fine” | Easily causes thread-starvation deadlock |
| “CallerRuns does not change execution concurrency” | Tasks run on the caller outside pool workers |
| “`isCancelled()` proves the worker has stopped” | The worker may still be cleaning up or blocked |
| “Virtual threads remove system limits” | Downstream/CPU/memory remain finite |
| “A queue depth snapshot is exact accounting” | Metrics have races and independent snapshots |
| “Many requests from one user will be shared fairly automatically” | Per-user quotas or fair queues may be needed |

## 21. Self-Check Questions

**1. There are 500 in-flight requests and an 8-worker pool—is that a contradiction?** No. Requests may be waiting in a queue or on I/O, and one request may spawn multiple tasks.

**2. One request submits 20 subtasks—are there 20 users?** No. That is one request creating 20 executor tasks.

**3. If `newFixedThreadPool(4)` receives 100 tasks, do 100 task bodies run simultaneously in the pool?** No. Typically at most four tasks run on pool workers; the rest wait in the queue.

**4. Is a worker in `CountDownLatch.await` counted as executing?** It still occupies a worker slot, even though it is not using CPU for computation.

**5. Does increasing `maximumPoolSize` when the queue is not full create more workers immediately?** Usually no. After core, the pool prioritizes the queue.

**6. Why does `CompletableFuture.supplyAsync` not mean completely non-blocking?** Supplier code can still call blocking APIs on the executor thread.

**7. Why can nested `Future.get` in a single-worker pool hang?** The worker waits for a subtask in the same pool's queue, but there is no free worker to run that subtask.

**8. Can `CallerRunsPolicy` run a task body outside a pool worker?** Yes, on the thread calling `execute` when the policy applies.

**9. If Little's Law gives 20 in-flight requests, does that require a 20-thread pool?** No. It measures average requests in the system, not worker count.

**10. When a user response times out, can a background task still occupy a worker?** Yes, if cancellation does not cause the task to actually stop.

**11. Does virtual-thread-per-task automatically limit concurrent DB queries?** No. Separate connection/rate/quota limits are needed.

**12. Is measuring only `activeCount` enough to size a pool?** No. You need queue waits, request latency, CPU, downstream, fan-out, rejection, and demand over time.

## 22. Final Checklist

- **Have you defined whether user task concurrency means requests, sessions, or jobs?**
- Do you count in-flight requests separately from outstanding executor tasks?
- Do you know how many subtasks, futures, and retries one request creates?
- Have you distinguished accepted, queued, executing, completed, and rejected?
- Is the pool using a **bounded or unbounded** queue? How do core/max/rejection behave?
- Are workers CPU-bound or mostly blocking?
- Are there nested submissions to the same pool followed by blocking `get/join`?
- Are there separate admission limiters for workflows and for downstream resources?
- Are there real deadlines, cancellation, and `finally` cleanup?
- Do metrics record units (requests/tasks/threads/cores) and measure over time series?
- When moving to virtual threads, are resource budgets still managed?
- Have load tests checked p95/p99, memory, queue growth, rejection, and shutdown?

**Conclusion:** **User task concurrency** represents the amount of user work currently demanding processing; **thread pool concurrency** represents the number of task bodies being executed by workers in an executor at a given moment; **CPU parallelism** is what actually runs on hardware. The three quantities are related but not equal. For a stable system, count business requests and subtasks accurately, understand queuing and rejection, bound in-flight demand, avoid worker starvation, and tune based on actual bottlenecks rather than deriving thread counts from user counts.