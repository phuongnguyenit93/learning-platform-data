# Choosing Thread Counts for CPU-Bound and I/O-Waiting Tasks

**Module:** Spring Framework - concurrency  
**Knowledge Group:** Resource Configuration  
**Objectives:** Understand why CPU-intensive tasks and frequent I/O-waiting tasks require two different thread allocation strategies; know how to set `corePoolSize`, `maxPoolSize`, `queueCapacity`, resource limits, measure, and tune systematically in Spring.

## 1. Why Can't Thread Counts Be Chosen by One Fixed Formula?

A Java thread can be in a **CPU-consuming** state or **waiting** on network, database, disk, locks, semaphores, timers, and other resources. With a finite number of CPUs, adding threads can increase throughput when many threads are waiting, yet can slow down an already CPU-saturated system due to context switching, cache contention, and scheduling overhead.

For example, suppose four CPU cores are available:

- **Four continuous computation tasks:** roughly four workers run truly in parallel if each task uses one core and the machine is not heavily loaded by other work. Increasing to 100 workers does not create 100 cores.
- **Four tasks waiting on HTTP/DB for most of their lifecycle:** each worker occupies a thread without continuously using CPU. More workers can keep the CPU busy while others wait, **until** hitting connection, remote service, memory, bandwidth, or timeout limits.
- **Four non-blocking API call tasks:** the number of in-flight network requests can exceed the thread count; do not mechanically apply "one waiting request = one held thread."

Therefore, classify the workload, measure **compute** time and **wait** time, identify resource limits, and configure a pool with an explicit queue and rejection mechanism.

### Two Often-Conflicting Goals

1. **Throughput:** the number of tasks completed per second.
2. **Latency:** the time from accepting a task to returning its result; must be split into **queue wait** and **execution time**.

Adding threads sometimes improves throughput while worsening tail latency when a downstream is overloaded. A pool with a large queue may reject fewer tasks upfront yet stretch queue wait to seconds or minutes. **Thread count cannot be optimized in isolation while ignoring the queue and downstream.**

## 2. Identifying CPU-Bound, Blocking I/O-Bound, and Non-Blocking I/O

| Task Type | Most Time Spent In | Measurement Signals | Concurrency Sizing Direction |
| --- | --- | --- | --- |
| **CPU-bound** | Computation, compression, encryption, heavy parsing, image processing, in-memory data transformation | CPU near saturation; adding workers increases context switches without increasing throughput | Active workers roughly equal to available CPU cores; typically fixed pool, bounded queue |
| **Blocking I/O-bound** | Thread blocked in `InputStream.read`, JDBC, synchronous REST clients, socket calls, lock waits | CPU has headroom while many threads show `WAITING`/`TIMED_WAITING`/blocked in stack traces | Can use more workers than CPU cores, bounded by connection pools and external limits |
| **Non-blocking I/O** | Registering I/O operations and receiving callbacks/signals on data; not holding one worker per request | A few event-loop threads handle very many connections; CPU is not blocked on I/O | Do not scale event-loop threads with request count; avoid CPU-heavy or blocking code on event loops |
| **Mixed workload** | Both heavy computation and blocking I/O calls | CPU fluctuates high and low; shared pool exhibits unstable queueing | Separate CPU and blocking I/O pools or bound each type separately; measure under real load |

A single task can involve *both*: e.g., receiving HTTP, parsing JSON, computing a signature, running a JDBC query, transforming an image. Classify based on where **time is actually spent**, not just method or framework names.

Crucial distinctions:

- Calling `Thread.sleep(...)` **blocks a thread**, but is not real I/O. Use sleep only to simulate wait time in test examples.
- Calling `CompletableFuture.supplyAsync` does not turn a synchronous JDBC call into non-blocking I/O; it merely shifts the blocking work onto another worker.
- WebFlux, Reactor/Netty help structure asynchronous I/O when the driver/client is genuinely non-blocking. Putting long CPU calculations or blocking JDBC on the event loop still causes stalls.
- Java 21+ provides virtual threads: many blocking operations can use virtual threads to reduce the cost of holding *platform threads*. This does **not** make CPU infinite and does not automatically increase DB connection limits, rate limits, or external service capacity.

## 3. Calculating Truly Available CPUs

Use a starting check:

```java
int processors = Runtime.getRuntime().availableProcessors();
System.out.println("reportedProcessors=" + processors);
```

The Java snippet above is **illustrative** of how to obtain the processor count reported by the JVM, not a complete standalone program. The value may reflect affinity/container limits depending on JVM version and environment, yet you must still verify actual **CPU quotas, cgroups, contended cores, SMT/hyper-threading, and infrastructure limits**.

Let:

- `P` = CPU capacity available to **this process** (in equivalent CPU cores, which can be less than physical machine cores).
- `U` = target CPU utilization for the pool, e.g., `0.75` to `0.9` to leave headroom for HTTP, GC, and other tasks.
- `N_cpu` = number of **concurrent workers that can run on CPU**.

A common starting point for pure CPU-bound work:

\[
N_{\mathrm{cpu}} \approx P
\]

If the JVM also runs HTTP, GC, schedulers, or multiple CPU pools, divide the total CPU budget among them. With very few CPUs or fractional quotas, worker count must be an integer of at least one; do not interpret the formula as an optimal throughput guarantee.

### Example

Suppose a container has a CPU budget equivalent to **4 cores**, and tasks perform long calculations without waiting on I/O. Start by testing **3–4 CPU workers** for this dedicated pool with a bounded queue, and measure throughput and p95/p99. Increasing to 8 only helps if tasks actually have significant waiting or CPU headroom remains; if CPU stays at 100%, it can worsen latency due to CPU contention.

**Do not create a 4-worker CPU pool per endpoint** and end up with dozens of pools running at maximum concurrency simultaneously. The combined concurrency across all pools and request threads is what overloads CPU.

### Signs of CPU-Bound Work in Production

- Process/container CPU stays persistently high; more runnable threads than available CPUs.
- Profiling shows cumulative time in math functions, encryption, decompression, JSON conversion, or loops.
- Increasing from 4 to 8 workers: throughput does not increase, CPU stays flat, context switching and p99 rise.
- Multiple workers updating the same data structure or lock may **not** scale with core count: fix contention, shard data, or shrink critical sections.

## 4. Sizing for Blocking I/O: Wait Time Is the Key Factor

For blocking tasks, let:

- `C` = actual CPU time spent per task, e.g., **20 ms**.
- `W` = time the thread spends waiting on I/O, e.g., **80 ms**.
- `P` = available CPU cores.
- `U` = target CPU utilization within the pool's scope.

A heuristic for an **initial experimental estimate**, assuming independent tasks and relatively steady conditions, is:

\[
N_{\mathrm{blocking}} \approx P \times U \times \left(1 + \frac{W}{C}\right)
\]

For example, `P = 4`, `U = 0.8`, `W = 80 ms`, `C = 20 ms`:

\[
N \approx 4 \times 0.8 \times (1+4)=16
\]

Explanation: one worker spends roughly 20% of its time computing and 80% waiting; more active tasks are needed to keep the CPU productive while others wait.

This is an **estimate, not a mandatory answer**. The formula cannot replace load testing, and often breaks down under downstream bottlenecks, shifting W/C ratios, contention, batching, caching, CPU bursts, timeouts, or non-independent tasks.

### Real I/O Limits Matter More Than the Computed 16

Suppose all 16 workers query the same database, but the JDBC pool only has **8 connections**. At most 8 queries can use connections simultaneously; the remaining workers may wait inside the JVM just to acquire a connection. Increasing further to 64 workers can raise wait times, request timeouts, and memory usage without increasing query throughput.

Limits to examine:

- JDBC connection pool, database concurrent connection limits, and transaction duration.
- HTTP connection pool, partner-allowed concurrent requests, rate limits, and network latency.
- File descriptors, sockets, memory/thread stacks, heap pressure, and GC.
- Downstream queueing delay and retry amplification: when a remote service slows down, concurrent task counts can surge.
- SLA: each request has a **deadline**, timeout, and retry policy; queues must not retain already-expired tasks.

Place a **separate concurrency limit** using a semaphore/bulkhead close to the resource if needed. `N_threads = 16` does not necessarily mean allowing 16 simultaneous DB queries.

### Little's Law for Load Sanity Checks

In steady state:

\[
L = \lambda \times T
\]

Where `L` is the average number of tasks in the system, `λ` is throughput (tasks/second), and `T` is total time a task stays in the system (seconds), **including queueing time** if measuring the whole system. For example, at a throughput of 100 tasks/second with an average duration of 0.2 seconds, there are about 20 tasks in-flight on average.

Do not deduce "we always need 20 threads" from that number: work may use non-blocking I/O, many jobs may sit in a queue, and downstream pools may use other resources. Little's Law helps cross-check the relationship between load and latency, not replace per-pool sizing.

## 5. ThreadPool Structure in Spring: How Do `core`, `max`, and Queue Relate?

`ThreadPoolTaskExecutor` is Spring's convenient choice for managing a pool as a bean. With a typical configuration:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(40);
```

These values are **examples to understand the mechanism**, not automatically suitable for every service.

In the `ThreadPoolExecutor` wrapped by Spring, when a new task arrives:

1. If the current worker count is **less than `corePoolSize`**, the executor prefers creating a new worker to handle it.
2. Once core is reached, the executor **prefers placing the task into the queue** if space remains.
3. **Only when the queue cannot accept more tasks** does the executor create workers beyond core, up to `maxPoolSize`.
4. If workers have reached max and the queue cannot accept more, the task is rejected according to `RejectedExecutionHandler`.

```text
Task arrives
  |
  +-- Worker count < core? ---- Yes ----> Create worker, run task
  |
  +-- Queue has space? -------- Yes ----> Enqueue to wait
  |
  +-- Worker count < max? ----- Yes ----> Create worker beyond core
  |
  +-- Reject / execute on caller depending on rejection policy
```

A surprising consequence: **`maxPoolSize=100` does not mean the pool will scale to 100 when the CPU is busy**. If the queue is large enough or unbounded, once core is reached, tasks may simply pile up in the queue without triggering new workers.

Understand the properties:

| Property | Role | Notes |
| --- | --- | --- |
| `corePoolSize` | Target worker count maintained under normal load | Not the total count of running and queued tasks |
| `maxPoolSize` | Upper limit of pool workers during bursts | Only takes effect when the queue cannot accept additional tasks |
| `queueCapacity` | Number of **waiting** tasks, excluding running tasks | Needs a finite bound based on memory/latency for production |
| `keepAliveSeconds` | Idle duration before workers beyond core are reclaimed | Does not solve an overly large queue |
| `threadNamePrefix` | Helps identify threads in logs/thread dumps | Separate CPU/IO pool names for observability |
| `RejectedExecutionHandler` | Policy when workers/queue have no remaining capacity | `AbortPolicy` throws an error; `CallerRunsPolicy` can run the task on the submitting thread |
| `TaskDecorator` | Wraps task execution callback (context/metrics) | Must clean up `ThreadLocal`; does not automatically propagate transactions |

**Spring's `ThreadPoolTaskExecutor` defaults** have core 1, very large max, and very large queue capacity. Because the default queue is effectively unbounded for practical needs, do not configure only `maxPoolSize` expecting rapid auto-scaling; actively decide core, max, and queue.

A `ThreadPoolTaskExecutor` with queue capacity **0** uses a direct handoff mechanism similar to `SynchronousQueue`, which can scale workers immediately when tasks arrive; if max is too large, it risks sudden thread spikes. Use it only once rejection behavior and load pressure are understood.

## 6. Separating CPU and Blocking I/O Pools in a Spring Application

If one executor is shared for both CPU-heavy file compression and blocking JDBC/HTTP, blocking tasks can occupy all workers so CPU work cannot run even while CPU is idle. Conversely, CPU-bound tasks can monopolize the pool and delay I/O. You can use **two executor beans**, each with its own queue and limits.

Example for **Spring Framework 6.x, Java 17+**, intended for a Spring Boot application using `spring-boot-starter-web` or a Spring setup with `spring-context`.

Save file `src/main/java/com/example/sizing/ExecutorConfiguration.java`:

```java
package com.example.sizing;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ExecutorConfiguration {

    @Bean("cpuExecutor")
    public ThreadPoolTaskExecutor cpuExecutor() {
        int available = Runtime.getRuntime().availableProcessors();

        // Cap of 8 is an illustrative limit for the app, not a general rule.
        int cpuWorkers = Math.max(1, Math.min(8, available));
        return createExecutor("cpu-", cpuWorkers, cpuWorkers, 32);
    }

    @Bean("blockingIoExecutor")
    public ThreadPoolTaskExecutor blockingIoExecutor() {
        // 8/16/64 is only a starting configuration to measure; check DB/API limits.
        return createExecutor("blocking-io-", 8, 16, 64);
    }

    private static ThreadPoolTaskExecutor createExecutor(
            String prefix, int core, int max, int queueCapacity) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(core);
        executor.setMaxPoolSize(max);
        executor.setQueueCapacity(queueCapacity);
        executor.setThreadNamePrefix(prefix);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Save file `src/main/java/com/example/sizing/WorkService.java`:

```java
package com.example.sizing;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WorkService {

    @Async("cpuExecutor")
    public CompletableFuture<Long> calculate(int upperBound) {
        if (upperBound < 0) {
            return CompletableFuture.failedFuture(
                    new IllegalArgumentException("upperBound must be >= 0"));
        }
        long sum = 0;
        for (int i = 1; i <= upperBound; i++) {
            sum += i;
        }
        return CompletableFuture.completedFuture(sum);
    }

    @Async("blockingIoExecutor")
    public CompletableFuture<String> fetchLegacy(String key) {
        try {
            // Simulates 50 ms of blocking I/O only; not a real network call.
            TimeUnit.MILLISECONDS.sleep(50);
            return CompletableFuture.completedFuture("data-" + key);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
```

The two files above are **complete classes within a Spring application**; running them under Spring Boot requires a `@SpringBootApplication` class and corresponding dependencies. You cannot compile them with plain `javac` without Spring on the classpath. In the example, `fetchLegacy` only simulates blocking time; in a real application, replace it with a synchronous JDBC/HTTP client with timeouts and measure actual waiting.

Explaining these decisions:

- `cpuExecutor`: fixed-size pool aligned with a bounded CPU budget, avoiding creating threads beyond useful cores.
- `blockingIoExecutor`: allows higher concurrency because each worker spends time waiting; however, `8`, `16`, `64` are **not default production values**. Measure `W/C` and downstream limits.
- A bounded queue reveals the saturation point; with `AbortPolicy`, Spring reports `TaskRejectedException` when it cannot accept work. The caller must handle busy conditions per the API contract.
- `@Async("cpuExecutor")` and `@Async("blockingIoExecutor")` force Spring to choose an explicitly named bean; avoid defaulting every workload type to one shared pool.
- `@EnableAsync` in default proxy mode only intercepts calls through the **Spring proxy**. Calling `this.calculate()` within the same bean bypasses the proxy and can execute directly on the calling thread.
- `@Async` executes on a different thread: transactions, request context, and custom `ThreadLocal` values do not automatically follow. Workers should have their own transaction boundaries and receive required data explicitly.
- `ThreadPoolTaskExecutor` beans have their lifecycle managed by Spring when registered properly; avoid creating a new pool per request or calling `shutdown` inside a controller.

If an application needs multiple CPU pools, sum the **total** concurrent CPU workers across all pools rather than treating `availableProcessors()` as a separate allowance per bean.

## 7. Standalone Java 17: Same Job Count, Two Workload Types, and Overload

To understand the mechanics without booting Spring, the following JDK program runs:

1. **12 CPU tasks:** each sums numbers from `1` to `100_000`, using a 2-worker pool.
2. **12 simulated blocking I/O tasks:** each sleeps `20 ms`, using a 4-worker pool.
3. **A pool with 1 worker + 1 queue slot:** holds the worker with `CountDownLatch`, queues 1 more job, and verifies the third job is rejected by `AbortPolicy`.

Both pool sizes are purely illustrative. Do not draw benchmark conclusions from the timing of a tiny example. What is verified is **no lost work**, distinct waiting behavior, and that a bounded queue can reject tasks.

Save everything into **`WorkloadSizingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class WorkloadSizingDemo {

    static long cpuWork() {
        long total = 0;
        for (int i = 1; i <= 100_000; i++) {
            total += i;
        }
        return total;
    }

    static long runJobs(int workers, int jobs, Callable<Long> task)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<Long>> futures = new ArrayList<>();
            for (int i = 0; i < jobs; i++) {
                futures.add(pool.submit(task));
            }

            long total = 0;
            for (Future<Long> future : futures) {
                total += future.get();
            }
            return total;
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    static boolean rejectWhenFull() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> first = pool.submit(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!running.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // 1 worker is busy; this job takes the single queue slot.
            Future<?> second = pool.submit(() -> { });

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            first.get();
            second.get();
            return rejected;
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        long cpuTotal = runJobs(2, 12, WorkloadSizingDemo::cpuWork);

        long ioTotal = runJobs(4, 12, () -> {
            TimeUnit.MILLISECONDS.sleep(20); // Simulate I/O wait.
            return 1L;
        });

        System.out.println("cpuTotal=" + cpuTotal);
        System.out.println("ioTotal=" + ioTotal);
        System.out.println("rejected=" + rejectWhenFull());
    }
}
```

Run:

```bash
javac WorkloadSizingDemo.java
java WorkloadSizingDemo
```

**Stdout when the program finishes normally:**

```text
cpuTotal=60000600000
ioTotal=12
rejected=true
```

Why is the output deterministic?

- Each CPU job sums `1 + 2 + ... + 100000 = 5,000,050,000`; multiplied by 12 jobs this gives `60,000,600,000`. Using `long` prevents 32-bit overflow.
- Each simulated I/O job returns `1`, so the sum of 12 is `12`; only task execution order and timing are non-deterministic.
- In `rejectWhenFull`, the latch confirms the sole worker has actually started and is waiting; the second job then enters the 1-slot queue, leaving no worker or queue slot for the third job, which is rejected. `finally` always releases the latch and shuts down the pool so the program does not hang.

**Important note:** `Executors.newFixedThreadPool` uses a queue bounded only by memory, so it is only appropriate here for creating a simple example. In load-bearing services, configure `ThreadPoolExecutor`/Spring `ThreadPoolTaskExecutor` with a **bounded queue** and an appropriate rejection policy. `Future.get()` in `runJobs` serves to wait for test results; production HTTP controllers must carefully consider when blocking is acceptable.

## 8. How to Choose a Verifiable Pool Size?

Instead of looking at CPU count and typing in a fixed number, measure at **target load**, including normal and peak traffic.

### Step 1 — Define a Unit of Work

For example `renderPdf`, `recalculatePrice`, `callPartnerApi`, `sendEmail`. Measure each type separately so CPU and blocking I/O are not mixed. If one task contains multiple stages, measure CPU time and wall time for each stage.

Suggested metrics:

- Arrival rate `λ` (tasks/s) and completion rate (tasks/s).
- Average CPU time/task and wall-clock duration/task.
- Waiting time distribution, especially p95/p99 of JDBC/HTTP calls.
- Running task count, queued count, queue wait p50/p95/p99.
- Active threads, pool size, rejection count.
- CPU utilization against **container quota**, heap/GC, and memory.
- JDBC pool: active, idle, pending acquisitions, acquisition timeouts; HTTP pool and remote errors/timeouts.

### Step 2 — Choose a Starting Point

**CPU tasks:** start with `N ≈ P` for the total corresponding CPU workload budget; if the JVM has multiple other responsibilities, lower or partition the budget. With 4 cores, test 3–4 workers.

**Blocking I/O:** measure `W/C`, use `P×U×(1+W/C)` for a starting point, then **cap by I/O resources**. For example, if the heuristic yields 16 workers while the JDBC pool has only 8 connections, inspect the DB rather than choosing 16 just because the formula returned 16.

**Mixed:** split pools by resource/stage if load isolation benefits are clear. For instance, one CPU pool for image conversion and one I/O pool for uploading. If the cost of splitting and handoff is not worthwhile, you can keep a small shared pool, provided you monitor for starvation.

### Step 3 — Size the Queue by **Wait Budget**

Suppose a CPU pool processes an average of 40 jobs/s during a short peak, and clients cannot tolerate a job waiting more than 0.5 seconds *in the queue alone*. A 20-job queue corresponds to roughly 0.5 seconds of wait at the assumed processing rate under steady saturation (`20/40 = 0.5 s`). This is only a **simplified estimate**: with arrival bursts, variable service times, prioritized tasks, or mixed job types, actual queue latency can differ greatly.

A huge queue does not solve insufficient throughput if the long-term arrival rate exceeds completion rate. In that case, wait times grow without bound until resources are exhausted. Size a bounded queue to match deadlines/SLIs, then define how the system responds when full.

### Step 4 — Matrix Load Test with Acceptance Criteria

For example, for a CPU pool with a 4-core budget: test `2, 3, 4, 6` workers with the same dataset and arrival pattern. For I/O: test `4, 8, 12, 16`, while measuring the connection pool and remote throughput. For each combination, measure:

- Successful throughput and error/rejection rate.
- End-to-end p50/p95/p99 from acceptance to completion, separating queue wait.
- CPU throttling, time in GC, memory, lock contention.
- Downstream timeouts, JDBC pending/connection wait.
- Recovery time after bursts.

Pick the **smallest configuration that meets SLOs** at expected peak, leaving headroom for errors or load shifts. A number that looks good on a dev machine may perform poorly in a 1-CPU throttled container or in production across 20 replicas.

### Step 5 — Monitor to Tune

`ThreadPoolTaskExecutor` supports introspection such as:

```java
int active = cpuExecutor.getActiveCount();
int currentPoolSize = cpuExecutor.getPoolSize();
int queueDepth =
        cpuExecutor.getThreadPoolExecutor().getQueue().size();
```

This is an **illustrative snippet** inside a bean holding a `cpuExecutor` reference; it must be called after the executor is initialized. Combine metrics from Spring Boot Actuator/Micrometer or your existing telemetry to observe queue depth, rejected tasks, performance, and resources. Do not look only at active threads and assume every worker is burning CPU: they may be waiting on I/O or locks.

## 9. Backpressure, Timeouts, and Unacceptable Extra Work

When a pool/queue hits its limit, you need **a response contract**. Depending on the system type:

1. Synchronous APIs can return `429 Too Many Requests` or `503 Service Unavailable` per load policy, with retry hints when appropriate.
2. Job APIs should return `202 Accepted` only after **recording the work** to their durability guarantee. If an in-memory executor rejects it, do not report accepted success.
3. Critical jobs require durable persistence: DB/job queues, message brokers, transactional outbox, bounded retries, and idempotency. Java/Spring thread pools do **not** replace durable queueing systems.
4. Limit concurrent downstream calls via semaphores/bulkheads; if a permit cannot be acquired within the deadline, fail fast instead of holding a worker indefinitely.
5. Set HTTP/JDBC/DB lock timeouts aligned with the overall deadline; retries must include backoff, jitter, and retry limits to avoid amplifying load when external systems are failing.

The JDK's `CallerRunsPolicy` is a form of backpressure: when a task cannot be accepted and the executor is not shut down, the **submitting thread** may execute the task itself. If that is a Servlet request thread, it can get tied up in heavy work; do not treat this policy as "always returns an error when full." With Spring's `ThreadPoolTaskExecutor`, if you want explicit overload signaling, pick `AbortPolicy`, catch `TaskRejectedException` at the submission boundary, and translate it into an appropriate response.

### Do Not Enlarge Pools to Mask Internal Bugs

- I/O pool overflowing due to missing HTTP timeouts: fix timeouts/connection management first.
- CPU pool overloaded because each job holds a global lock: profile and reduce contention first.
- JDBC connection pool exhausted because transactions stay open during remote API calls: shrink transaction scope; adding workers only lengthens wait times.
- Queue growing rapidly because upstream sends faster than long-term capacity: apply rate control or real scaling, do not just raise `queueCapacity`.

## 10. Common Misconfiguration Scenarios

| Symptom | Common Wrong Assumption | Correct Action |
| --- | --- | --- |
| CPU at 100%, raised from 4 to 40 workers | "More threads always process faster" | Cap near useful CPU, measure context switches and throughput |
| Low CPU, many threads waiting on DB | "Just raise threads to a few hundred" | Check connection pool, query latency, locking, and pending acquisitions |
| `maxPoolSize=32`, core=4, very large queue | "Pool will immediately use 32 threads when busy" | Understand queue-before-grow; set bounded queue and proper core |
| Huge `queueCapacity` | "No more overload errors" | Queue waits balloon, memory overflows; choose limits by deadline |
| `@Async` called from same bean via `this.method()` | "Automatically runs on executor" | Route calls through Spring proxy, verify `@EnableAsync` config |
| Running blocking JDBC in Netty event loop | "WebFlux makes every dependency non-blocking" | Use a non-blocking driver or offload blocking work to a bounded scheduler |
| Using virtual threads for thousands of simultaneous queries | "Virtual threads eliminate DB limits" | Still bound connections/rates/deadlines; virtual threads mainly cut thread-holding cost |
| One shared pool for CPU and network-waiting tasks | "A large enough pool will be fair" | Separate or quota by workload type; monitor starvation |
| Creating a new pool on every request | "Per-request pools are more parallel" | Use application-scoped beans/pools and manage lifecycle |
| Returning `202` even when executor rejects task | "API call succeeded so the job was recorded" | Report accepted only when durably accepted, with clear overload errors |
| Treating `availableProcessors()` as physical core guarantee | "This value is stable CPU capacity everywhere" | Check container quotas/CPU throttling and measure real load |
| Choosing thread counts from simple `sleep` benchmarks | "I/O is always an 80% wait ratio" | Measure actual production `W/C` and I/O latency distributions |

## 11. Self-Check

**Q1.** A server has a 4-core CPU budget, running pure non-blocking computation tasks. Will choosing 40 threads achieve 10x the throughput of 4 threads?  
**Answer:** No. Core count limits parallel CPU execution; adding many threads usually increases scheduling/contention overhead, and must be measured if other factors exist.

**Q2.** What does the heuristic `N ≈ P × U × (1 + W/C)` give with `P=4`, `U=0.8`, `W/C=4`?  
**Answer:** 16 workers as an **initial test point**. You must check connection counts, remote quotas, and queue wait times; never treat 16 as a guaranteed optimal setting.

**Q3.** Does Spring's `ThreadPoolTaskExecutor(core=4,max=16,queue=100)` immediately scale up to 16 threads when 5 CPU jobs are running?  
**Answer:** Not necessarily. Once core is reached, the pool prefers enqueuing tasks first; only when the queue cannot accept more will it try expanding past core.

**Q4.** There are 32 workers doing JDBC, yet the connection pool only has 8 and CPU is low. Will increasing to 64 workers definitely boost throughput?  
**Answer:** No. DB/connection serving capacity is the limit; it may just increase wait times and memory. Profile queries, connection wait, and concurrency limits.

**Q5.** Why separate the CPU executor and the blocking I/O executor?  
**Answer:** So I/O-waiting workers do not consume slots meant for CPU work, allowing separate queues/budgets/backpressure and independent measurement.

**Q6.** An API returns `202` right after calling `@Async`, but the executor is full and the task is rejected. Is the contract valid?  
**Answer:** No, unless another durable intake mechanism is in place. You must handle `TaskRejectedException` and report that the system did not accept the job.

**Q7.** Do virtual threads allow removing remote connection limits, request timeouts, and rate limits?  
**Answer:** No. They change the cost of holding threads while blocking; physical resources, CPU, and downstreams remain finite.

**Q8.** `queueDepth` grows continuously while `activeCount == maxPoolSize`; should you raise `queueCapacity` first or investigate throughput?  
**Answer:** Investigate arrival/completion rates, processing time, timeouts, bottlenecks, and downstream limits; a larger queue only extends wait time if long-term arrival exceeds processing capacity.

## 12. Key Takeaways and References

- **CPU-bound:** start near available CPU core budget, avoid oversized pools; prioritize profiling and measuring throughput/tail latency.
- **Blocking I/O-bound:** may need more workers than cores; use wait/compute ratio to estimate, then cap by connection limits, memory, timeouts, and load tests.
- **Non-blocking I/O:** request concurrency can be high without holding one platform thread per call; do not put blocking work on the event loop.
- **In Spring:** explicitly configure `corePoolSize`, `maxPoolSize`, and `queueCapacity`. The queue is filled before scaling past core; use bounded pools, rejection policies, and resource-separated executors where appropriate.
- **In production:** sizing is an iterative loop of **measure → hypothesize → load test → observe → tune**, not a formula yielding one fixed value.

Official references:

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — abstractions, thread pool configuration, queue-before-scaling behavior.
- [Spring Framework – `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — core/max/queue properties, pool state, rejection.
- [Java SE 17 – `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — thread/queue selection rules and rejection policies.
- [Java SE 17 – `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) — submission, shutdown, and lifecycle.
- [Spring Framework – `@Async`](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async) — declaration, proxies, executor selection.