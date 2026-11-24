# ThreadPoolTaskExecutor Manages a Reusable Thread Pool in Spring Framework

A Spring service may need to generate reports, send notifications, process documents, or call external services without holding the request-receiving thread until the work finishes. Creating `new Thread(...)` for every request is a poor strategy as task counts grow: platform threads require stacks, memory, and scheduling work; uncontrolled thread counts cause resource contention. **`ThreadPoolTaskExecutor`** is Spring's `TaskExecutor` implementation wrapping a **`java.util.concurrent.ThreadPoolExecutor`**, providing a pool of reusable workers, a queue, thread bounds, a rejection policy, and Spring-managed lifecycle.

To **choose the right executor**, you need to understand two things: **how work enters the pool** and **how much work the pool accepts before queuing or rejecting**. Simply putting `@Async` on a method does not guarantee performance, reliability, or thread safety.

## 1. Task, Worker, Executor, and Queue: Four Roles

- **Task:** a unit of work represented by `Runnable` (no direct return value) or `Callable<T>` (produces a result).
- **Worker thread:** the thread executing tasks. Upon completion, a worker normally pulls another task instead of being destroyed and recreated.
- **Executor:** accepts tasks and coordinates execution as configured, allowing the caller to proceed before the task finishes.
- **Queue:** holds accepted tasks that do not yet have an available worker.

```text
Controller / Service / @Async proxy
                  │
                  │ submit(task)
                  ▼
         ThreadPoolTaskExecutor
                  │
                  ▼
          ThreadPoolExecutor
           ├── worker-1: Task A → Task D → Task G
           ├── worker-2: Task B → Task E
           ├── worker-3: Task C → Task F
           └── Waiting queue: [Task H] [Task I] ...
```

Arrows within the same worker illustrate **a thread being reused to run multiple tasks in sequence**, not one task running repeatedly. Reuse reduces platform-thread creation/destruction overhead and enables bounding concurrency.

**Related abstractions:**

| Concept | Component | Responsibility |
| --- | --- | --- |
| Basic JDK executor | `Executor` | `execute(Runnable)` |
| JDK executor with lifecycle/Future | `ExecutorService` | `submit`, `Future`, `shutdown` |
| JDK pool | `ThreadPoolExecutor` | Core/queue/max/rejection algorithm |
| Spring executor | `TaskExecutor` / `AsyncTaskExecutor` | Unified task-submission contract for Spring components |
| Spring pool executor | `ThreadPoolTaskExecutor` | Pool configuration and lifecycle bean backed by JDK ThreadPoolExecutor |
| Spring async invocation | `@EnableAsync`, `@Async` | Proxy dispatching method calls through a chosen executor |
| Spring scheduler | `TaskScheduler`, `@Scheduled` | Triggers tasks on a schedule |

**`@Async` does not automatically mean `ThreadPoolTaskExecutor`.** The annotation only specifies call-interception dispatch; the executor can be another implementation. Conversely, you can inject `ThreadPoolTaskExecutor` and call `execute(...)` or `submit(...)` without using `@Async`.

## 2. The core → queue → max → rejection Algorithm

Example configuration:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(2);
```

Assume the pool was just initialized and **none of the started tasks have finished yet**. When a new task arrives, `ThreadPoolExecutor` essentially follows this sequence:

1. If the current worker count is less than `corePoolSize`, create a new worker to handle the task.
2. Once core size is reached, try placing the task into the queue.
3. If the queue is full, try expanding workers up to `maxPoolSize`.
4. If the queue is full **and** max is reached, hand off to the rejection policy.

| Incoming task | State | Outcome when prior tasks are still running |
| --- | --- | --- |
| #1 | Below core=2 | Create worker #1 |
| #2 | Below core=2 | Create worker #2 |
| #3 | Core reached, space in queue | Wait in queue (1) |
| #4 | Core reached, space in queue | Wait in queue (2) |
| #5 | Queue full, pool below max=4 | Create worker #3 |
| #6 | Queue full, pool below max=4 | Create worker #4 |
| #7 | Queue full, max reached | Reject according to policy |

This table is not a promise of execution order in a live system. If a worker becomes idle, it can pick up a queued task, changing queue/pool occupancy. The scenario is held fixed to show **task-admission decisions**.

**The hardest point to remember:** the pool prioritizes **queuing once core is full**, and **only scales beyond core when the queue is full**. Thus, with `core=2, max=20, queueCapacity=10_000`, 100 slow tasks will mostly sit waiting behind two workers; `max=20` does not cause 20 workers to appear immediately.

### Why Does a Pool Reuse Threads?

A platform thread requires resources and creation/scheduling work. If every short task creates its own thread, high load can easily spawn thousands of threads. A pool keeps workers around for reuse, both reducing overhead and capping resources. However, workers also have costs: too many threads increase context switching and contention for CPU/heap/stack. Whether a pool is fast depends on the workload and underlying system, not just the thread count.

## 3. Meaning of Configuration Properties

| Property | Mechanism | Notes |
| --- | --- | --- |
| `corePoolSize` | Baseline worker count under load | Not “maximum running tasks” |
| `maxPoolSize` | Upper bound on workers | Only matters once the queue is full or with special queue policies |
| `queueCapacity` | Number of waiting tasks held in memory | Should be bounded based on bursts and acceptable latency |
| `keepAliveSeconds` | Idle time for non-core workers before reclamation | Defaults to 60 seconds |
| `allowCoreThreadTimeOut` | Allows core workers to time out when idle as well | Defaults to `false` |
| `prestartAllCoreThreads` | Pre-creates core threads at initialization | Defaults to `false`; normally created on task arrival |
| `threadNamePrefix` | Sets the worker thread name prefix | Makes logs and thread dumps easier to read |
| `rejectedExecutionHandler` | Behavior when tasks can no longer be accepted | Must not silently lose critical tasks |
| `taskDecorator` | Wraps a task before the worker runs it | Used for context propagation/timing and cleanup |
| Shutdown flags | How the pool closes when context stops | Can wait for or interrupt tasks depending on settings and version |

**Defaults of a bare `new ThreadPoolTaskExecutor()` in Spring Framework 6.x**: `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, `queueCapacity=Integer.MAX_VALUE`, `keepAliveSeconds=60`, and `allowCoreThreadTimeOut=false`. A huge queue means the pool usually runs only one worker under ordinary load; **a huge max does not automatically increase worker count**.

**Distinguish from Spring Boot auto-configuration:** Spring Boot can create `applicationTaskExecutor` with its own defaults; for example, Boot 3.5 documentation describes an auto-configured executor with 8 core threads and `spring.task.execution.*` properties. You cannot take the defaults of a newly instantiated `new` class to guess the defaults of the Boot bean actually in use. When clear load boundaries are needed, configure a named bean and target it explicitly.

### 3.1. `queueCapacity > 0`: Bounded Waiting Queue

`ThreadPoolTaskExecutor` uses a `LinkedBlockingQueue` when queue capacity is positive. The pool tries queuing tasks once core workers are busy, expanding only when the queue fills. An excessively large queue lets tasks linger long before running, still occupying memory and risking OOM.

For example, `core=2, max=16, queue=1_000_000` is unreasonable just “to never reject”: if arrival rate stays above processing rate, the backlog keeps growing. Queue sizing must consider **queue wait latency**, per-task size, and burst load.

### 3.2. `queueCapacity = 0`: Direct Handoff

`queueCapacity=0` uses `SynchronousQueue`: there is no buffer for waiting tasks. A task is handed directly to an idle worker or the executor spawns an extra worker if below max; if all workers are busy and max is reached, the task is rejected. This pattern scales workers rapidly under load, though setting max too high can create very many platform threads.

**`queueCapacity=0` does not mean the executor lacks queuing semantics in scheduling**, nor does it mean “never reject”; it is a handoff mechanism with zero backlog storage.

### 3.3. Timeouts and Fixed Thread Pools

- If `core=max=4`, the pool has at most four workers; excess tasks wait in the queue, then get rejected if the queue fills.
- Workers **beyond core** can expire after being idle for `keepAliveSeconds`. Core workers are normally retained.
- `setAllowCoreThreadTimeOut(true)` lets core workers expire when idle as well (if timeouts are validly configured); useful for bursty workloads with idle periods.
- `setPrestartAllCoreThreads(true)` can reduce worker startup delay for the first few tasks, at the cost of holding resources even before load arrives.

These parameters are **capacity policies**, not per-task time limits. Task timeouts require separate mechanisms, such as client timeouts, deadlines, or controlled task cancellation.

## 4. Java 17+ Runnable: Observing Worker Reuse and Queue Capacity

`ThreadPoolTaskExecutor` wraps a JDK pool, so the core behavior can be verified without Spring dependencies. The following example intentionally uses `CountDownLatch` rather than guessing task order with `Thread.sleep`.

Save everything into **PoolBehaviorDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolBehaviorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "reused-worker"));
        try {
            String a = single.submit(
                    () -> Thread.currentThread().getName()).get();
            String b = single.submit(
                    () -> Thread.currentThread().getName()).get();
            System.out.println("same worker: " + a.equals(b));
        } finally {
            single.shutdown();
        }

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2));

        CountDownLatch started = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<?>> jobs = new ArrayList<>();

        try {
            Runnable heldTask = () -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            };

            for (int i = 0; i < 6; i++) {
                jobs.add(pool.submit(heldTask));
            }

            started.await(); // 4 workers are running and waiting on release
            System.out.println("pool=" + pool.getPoolSize()
                    + ", active=" + pool.getActiveCount()
                    + ", queued=" + pool.getQueue().size());

            release.countDown();
            for (Future<?> job : jobs) {
                job.get();
            }
            System.out.println("completed=" + jobs.size());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac PoolBehaviorDemo.java
java PoolBehaviorDemo
```

**Deterministic stdout during normal execution:**

```text
same worker: true
pool=4, active=4, queued=2
completed=6
```

**Why it is deterministic:**

1. `single` has one worker named `reused-worker`. Task A completes via `Future.get()` before task B is submitted; both execute on the same thread, so the first line is `true`.
2. The second pool has core=2, max=4, and queue=2. The first two tasks run, the next two queue up, and the last two trigger workers #3/#4.
3. All started tasks wait on `release`. `started.await()` only completes after four workers have started and cannot yet finish, so at measurement time four workers are active and two tasks sit in the queue.
4. `release.countDown()` frees the workers; the two queued tasks are picked up and processed. `Future.get()` waits for all six results before printing `completed=6`.
5. `shutdownNow()` in `finally` is only there to avoid leaving the pool running on error; normal flow has already finished all work beforehand.

This is a JDK illustration of the **underlying pool mechanism**, not a Spring container auto-initialized example. The Spring example in the next section shows how to declare the bean and select the executor with `@Async`.

## 5. Configuring ThreadPoolTaskExecutor as a Spring Bean

Example using **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, and the `spring-boot-starter-web` dependency. Put all the following code in **src/main/java/com/example/demo/PoolApplication.java**. This is a structurally complete Spring Boot program requiring Spring dependencies to build; do not run it with bare `javac PoolApplication.java`.

```java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class PoolApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        try {
            Thread.sleep(400); // Simulate blocking I/O
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
        System.out.println("Working on " + id
                + " using " + Thread.currentThread().getName());
        return CompletableFuture.completedFuture("report:" + id);
    }
}

@RestController
class ReportController {
    private final ReportService reports;
    private final ThreadPoolTaskExecutor executor;

    ReportController(
            ReportService reports,
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.reports = reports;
        this.executor = executor;
    }

    @GetMapping("/reports/{id}")
    public CompletableFuture<String> report(@PathVariable String id) {
        return reports.generate(id);
    }

    @GetMapping("/executor/stats")
    public Map<String, Integer> stats() {
        return Map.of(
                "poolSize", executor.getPoolSize(),
                "activeCount", executor.getActiveCount(),
                "queueSize", executor.getThreadPoolExecutor()
                        .getQueue().size(),
                "maxPoolSize", executor.getMaxPoolSize());
    }
}
```

Run using the project's Spring Boot build:

```bash
./gradlew bootRun
curl -s http://localhost:8080/reports/R7
curl -s http://localhost:8080/executor/stats
```

On Windows, use `gradlew.bat bootRun`. Once the Future completes, the response body of `/reports/R7` is:

```text
report:R7
```

The `/executor/stats` endpoint returns JSON containing `poolSize`, `activeCount`, `queueSize`, and `maxPoolSize`. Numbers vary with load and measurement timing; **there is no fixed set of JSON values**. Worker logs start with `report-`, though thread-name numbering and suffixes are not fixed.

### 5.1. How It Connects with `@Async`

1. `@Bean("reportExecutor")` creates **one** Spring-managed executor. Spring calls lifecycle initialization for the bean; there is no need to create a new executor per request.
2. `@EnableAsync` activates `@Async` processing infrastructure. The controller calls the container-managed service bean.
3. `@Async("reportExecutor")` requests the executor named `reportExecutor`, so execution routing is unambiguous even if the context contains other executors.
4. When the proxy handles the call, the `generate` task is submitted to the pool. A worker runs `Thread.sleep` simulating I/O, produces the result, and completes the `CompletableFuture`.
5. Spring MVC can handle a `CompletableFuture` return type asynchronously on the server side, yet **the HTTP client still waits for the response body to complete**. For a client to submit work and receive a job ID immediately, a dedicated API is required (e.g., HTTP 202, a job ID, and a status-polling endpoint).
6. `Thread.sleep` still occupies a worker even though the controller handles the request asynchronously. `@Async` does not turn blocking I/O into non-blocking I/O.

**Important proxy pitfall:** in default proxy mode, calling `this.generate(...)` from within `ReportService` itself will not pass through the `@Async` interceptor. Call it from another bean like the controller above, or place async methods in a dedicated service so calls genuinely traverse the Spring proxy.

### 5.2. Using the Executor Directly

Once you have the bean, besides `@Async`, you can inject `ThreadPoolTaskExecutor` and call `execute(Runnable)`:

```java
@Component
class DispatchService {
    private final ThreadPoolTaskExecutor executor;

    DispatchService(
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    void dispatch(Runnable task) {
        executor.execute(task);
    }
}
```

This is a **fragment** for the same Spring project above; you will need to import `org.springframework.stereotype.Component` and `org.springframework.beans.factory.annotation.Qualifier` if split into its own file. `execute` does not return a business value. If you need a result or error outcome, use `submit(Callable<T>)` and handle `Future<T>` according to your Spring version, or `CompletableFuture.supplyAsync(..., executor)`. Calling `get()`/`join()` right after submit causes the caller to wait actively, losing concurrency overlap benefits.

## 6. Under Overload: Rejection and Backpressure

With `core=2, max=4, queue=16`, if four workers are busy and the queue holds 16 waiting tasks, a new task can be **rejected**. For the `TaskExecutor` API, Spring provides `TaskRejectedException`, reflecting inability to accept the task. When going through annotations/proxies, check the error propagation path of the specific API.

| JDK RejectedExecutionHandler | Behavior | Risk |
| --- | --- | --- |
| `AbortPolicy` | Throws an error when submission is rejected | Caller must handle overload state; usually transparent |
| `CallerRunsPolicy` | Caller runs the task if the executor is not shut down | Creates backpressure, yet can **block HTTP request threads**; `@Async` can become synchronous under overload |
| `DiscardPolicy` | Drops the new task without raising an error | Easily loses work silently |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries | Breaks ordering/reliability and can lose work |

Pick a policy based on business semantics. Do not silently discard work that has a **must-execute** contract such as recording payment events or mandatory updates. If critical work requires durability, an in-RAM queue is no substitute for a message broker or job store.

**Distinguish clearly:**

- **Rejected:** the task was never accepted by the pool.
- **Failed:** the task ran, but code threw an exception.
- **Timed out:** the caller or a dependency exceeded its deadline.
- **Cancelled/interrupted:** cancellation was requested, though effectiveness depends on whether the task cooperates with interruption.
- **Shutdown:** the pool stops accepting new tasks or drains pending tasks according to lifecycle settings.

Count each case separately for operations. Do not report “task succeeded” merely because `execute` did not throw; that means the executor **accepted** the task, not that it finished.

## 7. Sizing Pool Size, Queue, and Partitioning by Workload Type

### 7.1. CPU-Bound Workloads

Encryption, image processing, compression, or heavy CPU computation are usually limited by physical cores and container CPU quotas. Scaling platform threads far beyond core count may only increase context switching and resource contention. You can start near the allocated CPU count and measure throughput/latency with real workloads.

### 7.2. Blocking I/O-Bound Workloads

Work that typically waits on HTTP/database/disk can use more workers than CPU cores to overlap wait times. However, if the DB connection pool only has 12 connections while 100 workers execute JDBC simultaneously, many workers will wait for connections and raise memory/latency. Consider connection pools, timeouts, quotas, and downstream capacity together.

### 7.3. The Queue Determines Wait Latency

Suppose a producer generates 200 tasks/sec while the service steadily completes 100 tasks/sec; if admission continues unbounded, the backlog grows by roughly 100 tasks every second under simplified conditions. After 10 seconds there may be around 1,000 waiting tasks. A large queue only delays surfacing overload.

If the system processes an average of 100 tasks/sec and only tolerates about 0.5 seconds of queue wait, **50 tasks can be a starting benchmark**, not a latency-guaranteeing formula. Traffic bursts, execution-time distributions, and downstream contention can alter outcomes. Load testing is required to pick real settings.

### 7.4. Isolating Pools to Protect SLAs

One separate pool for a slow email API and another for CPU-bound report processing prevents slow load from starving workers needed by critical business flows:

```text
Service A → @Async("emailExecutor")  → email worker pool → external mail API
Service B → @Async("reportExecutor") → report worker pool → CPU / storage
```

This applies the **bulkhead** pattern to isolate failures. However, many pools also increase total thread count and configuration overhead, so partition based on actual load rather than creating a pool for every method by default.

## 8. Lifecycle: From Initialization to Application Shutdown

In a Spring application, define the pool as a **bean** so the container manages its lifecycle:

- Set `core/max/queue` parameters before bean initialization. With a standard `@Bean`, Spring initializes the lifecycle automatically; no manual `initialize()` call is needed.
- If instantiating `new ThreadPoolTaskExecutor()` manually outside the container, calling code must invoke `initialize()` and ensure `shutdown()` when done.
- Do not create a new executor bean per request; pools are meant to be shared across many tasks.
- Do not call `shutdown()` after each submission; subsequent tasks will be rejected.
- When the context closes, waiting/cancelling tasks depends on flags and Spring version. `setWaitForTasksToCompleteOnShutdown(true)` instructs the executor to continue processing running and already-queued tasks during a controlled shutdown.
- `setAwaitTerminationSeconds(10)` limits how long the container waits for termination in the shutdown phase; it does not guarantee every task finishes within 10 seconds.
- In containers/Kubernetes, coordinate readiness, stopping incoming requests, termination grace periods, and dependency shutdown behavior. On abrupt kill/crash, tasks residing only in an in-RAM queue can be lost.

Critical work requiring **at-least-once execution** or recovery after restart must have durable state, idempotency keys, and proper retry/ack mechanisms. `ThreadPoolTaskExecutor` by itself is not a durable job queue and does not coordinate across multiple application replicas.

## 9. Thread-Local Context, Logging, and Concurrency Safety

Workers are **reused**, so each new task may run on the exact same thread just used by an earlier task. That is why care is needed with `ThreadLocal`, MDC logging, and security context.

By default, data on the request thread **is not automatically copied** to workers. Arbitrarily copying transactions or request-scoped state is also dangerous: standard Spring transactions are thread-bound, so `@Async` does not automatically inherit the caller's transaction.

### 9.1. TaskDecorator Propagating MDC with Cleanup

When a project uses SLF4J, you can configure a `TaskDecorator` on the executor bean. Here is a **configuration fragment** added to `reportExecutor()` before returning the bean:

```java
executor.setTaskDecorator(task -> {
    var submitted = org.slf4j.MDC.getCopyOfContextMap();
    return () -> {
        var previous = org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (submitted == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(submitted);
            }
            task.run();
        } finally {
            if (previous == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(previous);
            }
        }
    };
});
```

The decorator captures MDC **at submission time**, applies it to the worker thread **at execution time**, and clears/restores the prior state in `finally`. Without cleanup, a reused worker can leak correlation IDs or sensitive data from one task to the next.

**Exception note:** `TaskDecorator` wraps the actual runnable executed, which may be a `FutureTask` rather than the user's raw runnable. For tasks submitted via `submit`, exceptions are normally captured inside the Future; do not assume a decorator simply needs a `catch` around `task.run()` to see all errors. Observe `Future.get()`, `CompletableFuture.exceptionally/whenComplete`, and dedicated error metrics. For security context, consider wrappers from Spring Security and propagate only the necessary context.

### 9.2. A Thread-Safe Pool Does Not Make Beans Thread-Safe

The pool guarantees thread safety of its own internal structures when accepting/dispatching tasks; **it does not protect shared variables inside services**. For example, two tasks both doing `count++` on a plain singleton field can lose updates; concurrently writing to an unsynchronized `HashMap` is also wrong. Use immutable DTOs, local variables, atomic types, `ConcurrentHashMap`, or synchronized/locks matching the invariant being protected.

## 10. Observing the Pool with Metrics

| Metric | Used to answer |
| --- | --- |
| `getPoolSize()` | How many workers currently exist? |
| `getActiveCount()` | Roughly how many workers are busy? |
| `getThreadPoolExecutor().getQueue().size()` | How many tasks are waiting at measurement time? |
| Queue wait time | How long do tasks wait from submission to execution start? |
| Task run time | How long do tasks occupy a worker? |
| Rejection count | How many tasks did the pool reject? |
| Completion/failure/cancellation count | What are the business outcomes? |
| Downstream latency/connection usage | Is the bottleneck outside the executor? |

The getters `poolSize`, `activeCount`, and `queue.size()` reflect **point-in-time snapshots that can change instantaneously**; do not treat three separate reads as an atomic snapshot. Export metrics via Micrometer/Actuator when the project has observability tooling. Track p95/p99 latency, queue wait, task rejections, and memory—not just CPU.

If CPU is low while `activeCount` stays near max and the queue keeps growing, many workers may be **waiting on I/O or locks**, rather than lacking CPU cores. If CPU is high and CPU-bound tasks slow down as threads increase, the CPU may be oversubscribed.

## 11. Comparison with Other Executors

| Executor | Characteristics | Best suited when |
| --- | --- | --- |
| `SyncTaskExecutor` | Runs on the caller thread | Testing or when synchronous execution is needed |
| `SimpleAsyncTaskExecutor` | Does not reuse platform threads; has a virtual-thread option in supported versions | Wanting a thread-per-task strategy without a traditional platform-thread pool |
| **`ThreadPoolTaskExecutor`** | Reuses workers, explicit core/max/queue/rejection | Background workloads with bounded resources needing isolation |
| `ThreadPoolTaskScheduler` | Triggers on a schedule | `@Scheduled` jobs or time-based triggers |
| JDK `ThreadPoolExecutor` | Plain Java pool | Not using Spring or needing direct JDK-level control |
| Virtual-thread-per-task executor (Java 21+) | New virtual thread per task, not a reusable platform-thread pool as above | High-concurrency blocking I/O suited to virtual threads, still needing downstream limits |

**Virtual threads do not make CPU and DB connections infinite**. Even with virtual threads, you may still need semaphores, admission control, and timeouts. When the requirement is a group of reusable **platform workers** with explicit core/max/queue settings, `ThreadPoolTaskExecutor` is the direct choice.

## 12. Common Mistakes

**Mistake 1 — Raising only `maxPoolSize` and wondering why threads don't grow.** With a large queue, tasks wait before the pool scales past core. Inspect core, max, and queue together.

**Mistake 2 — Setting a huge queue “to avoid rejections”.** Backlogs and wait times can grow practically without bound until memory runs out.

**Mistake 3 — Setting `queueCapacity=0` with a very high max.** Bursts spawn many platform threads, straining resources. Choose an appropriate max.

**Mistake 4 — Sharing one pool for slow I/O and fast CPU tasks.** Slow tasks tie up all workers, starving critical work. Separate by resource/SLA when needed.

**Mistake 5 — Assuming `@Async` always runs on the desired pool.** The framework may pick a different executor; specify `@Async("beanName")` explicitly and verify proxy behavior.

**Mistake 6 — Self-calling `this.asyncMethod()`.** Self-invocation in default proxy mode bypasses the `@Async` interceptor.

**Mistake 7 — Calling `join()` immediately after submit.** The caller blocks itself, losing the benefit of overlapping work with the task.

**Mistake 8 — Ignoring rejections.** Unaccepted tasks need a retry response or overload policy; never treat them as successfully processed.

**Mistake 9 — Ignoring exceptions from `Future`.** A task may have failed on the worker without the caller noticing; collect errors via Future/callbacks or handlers.

**Mistake 10 — Equating `@Async` with non-blocking I/O.** Blocking JDBC/HTTP clients still hold the worker for the entire wait duration.

**Mistake 11 — Leaking `ThreadLocal` between tasks.** Reused workers can retain data from the previous task; clean context in `finally`.

**Mistake 12 — Neglecting shutdown/restart.** Tasks in an in-RAM queue do not survive a crash. Use a job store/broker for durability requirements.

## 13. How to Test Before Going to Production

A meaningful pool test should rely on **controllable** coordination conditions:

1. Submit tasks held by a `CountDownLatch` to reliably reach busy workers and a full queue.
2. With core=2, max=4, queue=2, verify after six tasks that 4 workers are busy and 2 tasks are waiting; a seventh task is rejected while the latch is still held.
3. Release the latch and wait for all `Future` instances to finish. Note that a completed task differs from a submitted task.
4. Intentionally make a task throw an error and verify the error path from Future/callback separately from rejection.
5. Test `CallerRunsPolicy` under overload and measure how long callers block.
6. Test MDC with multiple correlation IDs on the same worker; verify no cross-task leakage.
7. Close the Spring context while tasks are pending to evaluate graceful shutdown, timeouts, and dependent resources.
8. Load test with realistic traffic, measuring CPU, memory, queue wait, p95/p99 latency, active threads, rejections, and downstream capacity.

Do not use `Thread.sleep(100)` as deterministic proof of which task runs first; the OS/JVM scheduler guarantees no ordering. Use latches/barriers to create clear test conditions.

## 14. Self-Check

**Question 1.** `core=2, max=10, queue=100` and 20 slow tasks arrive at once. Why might the pool only have two workers?

**Answer:** Once core workers are busy, tasks are placed in the queue. Because the queue still has capacity, the pool does not need to scale beyond core; max=10 is only an upper bound.

**Question 2.** Does `queueCapacity=0` mean no tasks are accepted?

**Answer:** No. It uses `SynchronousQueue`, requiring direct handoff to an available worker or creating a new worker if below max. Only when it can accept no more does it reject.

**Question 3.** An HTTP request calls `@Async("reportExecutor")` and returns `CompletableFuture<String>`. Does the client receive the response body immediately?

**Answer:** No. The server can free the request-handling thread for other work, yet the response with the result only completes when the Future completes; to return a job ID immediately, design a separate API.

**Question 4.** What can `CallerRunsPolicy` change on the caller side?

**Answer:** Under overload, the caller may run the task directly and block until it finishes, creating backpressure while increasing latency or losing asynchronicity from the caller's perspective.

**Question 5.** Does the pool automatically protect a shared `HashMap` inside a bean?

**Answer:** No. The thread pool only schedules tasks. Shared data must still be made thread-safe.

**Question 6.** Why doesn't the pool's queue guarantee tasks survive a crash?

**Answer:** This queue resides in the process's RAM, not in a persistent job store.

**Question 7.** Why does MDC logging need cleanup after a task completes?

**Answer:** The thread can be reused for another task; uncleared context can leak between two tasks.

**Question 8.** When should you consider another executor instead of `ThreadPoolTaskExecutor`?

**Answer:** When you want synchronous execution (`SyncTaskExecutor`), need time-based triggers (`TaskScheduler`), or choose a virtual-thread-per-task model for suitable I/O; the choice must follow resource constraints.

## 15. Checklist When Choosing an Executor for a Project

- Classify tasks by CPU-bound vs. blocking I/O-bound, runtime duration, burstiness, and downstream quotas.
- Use named executor beans for groups of work needing isolation; never create a pool per request.
- Choose **corePoolSize, maxPoolSize, and queueCapacity together** according to the core → queue → max → reject algorithm.
- Set a finite queue and handle overload; measure queue wait rather than just increasing max.
- Annotate `@Async("executorName")` when proxy-based async is needed, or inject the executor for direct submission.
- Observe Futures/exceptions, and handle timeouts, retries, idempotency, and interruption.
- Protect bean shared state; pass required context and clean `ThreadLocal` when workers are reused.
- Design shutdown lifecycle and task durability; distinguish an in-memory queue from a persistent job system.
- Load test realistically and adjust configuration based on metrics rather than guesswork.

**Key takeaway:** `ThreadPoolTaskExecutor` accepts tasks, **keeps workers for reuse**, queues tasks once core is full, grows workers when the queue fills, and rejects when capacity is exhausted. How it is configured determines concurrency, wait latency, and overload behavior.

## References

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 Javadoc — ExecutorConfigurationSupport: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Java SE 17 — ThreadPoolExecutor API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
