# Choosing an Execution Strategy by Load, Environment, and Lifecycle Requirements

## 1. Goal and Principles for Executor Selection

A business invocation in Spring can run directly on the current thread, be submitted to a pool, run on a virtual thread, be triggered by a scheduler, continue inside a reactive pipeline, or be turned into a durable job via an external queue. Each approach has distinct resource characteristics, failure responses, and lifecycle behavior.

**Core problem:** choose an **execution strategy** suited to the **workload**, **deployment environment**, and **lifecycle requirements**, then configure bounds, timeouts, observability, and shutdown mechanisms. Do not choose an executor based merely on an API name or the assumption that “more threads always means faster”.

After this lesson, you should be able to:

- Characterize CPU-bound, blocking I/O, non-blocking I/O, bursty, short/long tasks, and latency requirements.
- Distinguish synchronous execution, `TaskExecutor`/`@Async`, `TaskScheduler`/`@Scheduled`, virtual threads, Reactor, and durable jobs.
- Roughly estimate concurrency demand from arrival rate and processing time, while recognizing CPU/connection/downstream limits.
- Design bounded thread pools and queues, overload policies, timeouts, and cancellation; avoid unbounded queues.
- Select appropriate configurations across Spring MVC, WebFlux, batch jobs, Jakarta EE, and multi-instance deployments.
- Clarify who owns the executor, who is allowed to shut it down, how in-flight tasks are handled on stop, and when durable execution across restarts is required.
- Verify choices with metrics, load tests, and failure scenarios.

In this lesson, an “executor” is the component deciding *how a task runs*; a “scheduler” decides *when to submit/run a task*. A scheduler may also use threads to run callbacks, yet these two responsibilities must be kept distinct.

## 2. Three Decision Axes Before Choosing an API

### 2.1. Workload Axis: What Is the Task Actually Using CPU For or Waiting On?

| Workload type | Characteristics | Initial approach |
| --- | --- | --- |
| CPU-bound computation | Little wait time; heavy real CPU usage: encryption, parsing, large data transformation | Pool bounded near measurable CPU capacity; avoid unbounded thread growth |
| Blocking I/O | Threads often wait on JDBC, synchronous HTTP clients, files, or external services | Explicitly bounded pool, or virtual threads (JDK 21+) paired with downstream limits |
| Non-blocking I/O | Drivers/clients signal completion without holding a thread for the entire wait | Keep a reactive/event-driven pipeline; avoid blocking the event loop |
| Very short tasks | Cheaper to execute than queuing, context switching, and synchronization | Can run directly on the caller thread |
| Long jobs, taking minutes/hours | Unsuitable for holding requests waiting; requires status tracking, retries, recovery | Asynchronous job with an ID; use durable storage/queues if work cannot be lost |
| Bursts, rapidly changing traffic | Instantaneous task arrivals exceed processing rate | Bounded queue, backpressure, admission control, and rejection policy |
| Periodic tasks | Runs on a clock/interval | `TaskScheduler` or external scheduler; account for multiple replicas |

A single task can have multiple phases. For example, reading from a DB is blocking I/O, transforming data is CPU-bound, and calling an external API is blocking I/O again. You do not have to force every phase onto the same executor if they have different resource limits and priorities.

### 2.2. Environment Axis: How Does the Runtime Manage Threads?

- **Spring MVC / Servlet:** requests are typically handled by web-container-managed threads. Offloading work to an executor can free request threads in some async styles, yet an HTTP request **waiting** on `Future.get()` right after submission can still block for roughly the same duration; switching threads only adds coordination overhead.
- **Spring WebFlux / Reactor:** event loops must remain unblocked. Calling a blocking client on an event loop is a design flaw that can degrade the entire system; prefer non-blocking APIs. When wrapping an unavoidable blocking API, offload it to an appropriate bounded scheduler such as `Schedulers.boundedElastic()`, and measure its limits.
- **Standalone Spring Boot (embedded server):** Spring manages executor/scheduler beans; auto-configuration behavior depends on the Boot version, declared beans, and whether virtual threads are enabled.
- **Jakarta EE / container-managed threads:** check the container contract; use `ManagedExecutorService` or Spring's managed executor adapter rather than creating unmanaged threads yourself.
- **Batch, CLI, short-lived jobs:** results and exit codes are part of the contract; you must await required tasks and shut down the executor before the process exits.
- **Container / Kubernetes / serverless:** instances can be replaced, scaled to zero, or hit execution time limits. Do not rely on in-process memory/queues if tasks must survive restarts.
- **Multiple replicas:** a `@Scheduled` method inside each instance can run on every replica; a cluster-wide singleton schedule requires coordination/locking or an external scheduler.

### 2.3. Lifecycle Axis: How Long Is a Task Allowed to Live?

Before choosing an executor, write down:

1. **Trigger source:** request, message, timer, startup, batch command, or business event.
2. **Deadline:** how soon does the caller need a response? Does the task have its own timeout?
3. **Ownership:** who creates, uses, and closes the executor? Spring context, application server, or code calling `new`?
4. **Durability:** may the task be lost if the JVM exits? Must the job be persisted to a DB/queue before reporting accepted?
5. **Cancellation:** if the caller times out or disconnects, must the task be cancelled? Does the task support interrupts and I/O timeouts?
6. **Errors/results:** are errors returned to the caller, saved in job state, or sent to a dead-letter queue?
7. **Context:** transactions, security identity, locale, trace IDs, and request context may change across thread boundaries.
8. **Overload:** if the queue is full, does the caller wait, receive an error, perform bounded retries, or degrade service?
9. **Shutdown:** stop admitting tasks, handle in-flight work and grace periods; how are incomplete tasks recovered?

If you cannot answer these questions, configuring thread counts is just guesswork.

## 3. Quick Decision Tree

```text
Must it complete within the current call / current transaction?
  ├─ Yes, short work that does not cause prolonged blocking
  │    └─ Run synchronously on the caller thread
  └─ No
       ├─ Must survive restarts, retry durably, or run for many minutes?
       │    └─ Durable job/queue/workflow + bounded workers
       └─ Can be managed within the JVM lifecycle
            ├─ Triggered on a schedule?
            │    └─ TaskScheduler/@Scheduled; offload long callbacks to a worker pool
            └─ Triggered by request/event/task
                 ├─ Reactor non-blocking pipeline?
                 │    ├─ Non-blocking API available → keep pipeline non-blocking
                 │    └─ Only blocking API available → bounded offload
                 ├─ CPU-bound → finite pool sized to CPU and priority
                 └─ Blocking I/O → bounded pool or virtual threads
                                     + timeouts + downstream resource limits
```

This is a starting point, not an algorithm that lets you skip load testing. A request with a short deadline may still require a durable workflow if the business work must execute while the caller only receives a job ID.

## 4. Synchronous Execution: An Intentional Choice

Use direct method calls when the result is needed immediately, the work is fast, steps must share the same transaction, or lifecycle decoupling is unnecessary. Introducing asynchronicity brings no benefit if the caller immediately blocks waiting for the result.

Spring provides `SyncTaskExecutor`, which runs tasks **directly on the calling thread**. It is useful for deterministic tests or when you intentionally do not want to switch threads; the name “executor” does not always imply a pool.

File `SyncAndAsyncChoiceDemo.java`, running on Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SyncAndAsyncChoiceDemo {
    static int calculate(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("sync=" + calculate(20, 22));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(
                    () -> calculate(20, 22));
            System.out.println("async result=" + future.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac SyncAndAsyncChoiceDemo.java
java SyncAndAsyncChoiceDemo
```

Output:

```text
sync=42
async result=42
```

In the second step, the work is submitted to another thread, yet `future.get()` blocks the main thread to receive the result. For work as trivial as addition, creating an executor/queue adds pure overhead; for heavy work, decoupling from the request is useful **when the caller does not need to wait directly** or when a truly asynchronous response mechanism is in place.

Running synchronously does not mean thread-safe by default: if the method mutates a singleton bean or shared cache, state protection and invariant checks are still required.

## 5. ThreadPoolTaskExecutor: The Familiar Choice for Bounded Load

`ThreadPoolTaskExecutor` wraps `java.util.concurrent.ThreadPoolExecutor` with Spring-integrated lifecycle. Core parameters:

- `corePoolSize`: baseline workers the pool keeps/maintains per policy.
- `maxPoolSize`: ceiling on workers when the executor needs to expand.
- `queueCapacity`: capacity to hold unexecuted tasks.
- `keepAliveSeconds`: time excess idle workers are kept before reclamation; also depends on core timeout policy.
- `RejectedExecutionHandler`: behavior when no more tasks can be accepted due to overload or shutdown.
- `threadNamePrefix`: aids tracing in logs and thread dumps.
- Shutdown/await settings: govern how the application handles running and queued tasks when the context closes.

**Do not ignore defaults.** On Spring Framework's `ThreadPoolTaskExecutor`, the classic defaults are `corePoolSize = 1`, a huge `maxPoolSize`, and an effectively unbounded `queueCapacity`. Because the pool normally **queues tasks after reaching core before scaling to max**, raising `maxPoolSize` alone while leaving an unbounded queue may not increase workers as expected.

### 5.1. Task-Admission Rules of ThreadPoolExecutor

Roughly in standard order:

1. If fewer than `corePoolSize` workers exist, create a worker for the task.
2. Once core workers exist, try placing the task in the queue.
3. If the queue is full and worker count is below `maxPoolSize`, try creating another worker.
4. If it cannot be accepted, apply the rejection policy.

For example, `core = 4`, `max = 8`, `queue = 64`: once four core workers are busy, new tasks normally enter the queue; only when the queue fills are workers 5–8 created. This config does not mean eight threads immediately run the instant eight tasks arrive. Scheduling and races can affect instantaneous state, so treat this as the executor's operating rule rather than a rigid timing diagram.

`queueCapacity = 0` makes the pool use direct handoff; when no worker is free, it tends to scale up faster to max and then reject. A large queue absorbs bursts at the cost of higher wait times and memory; a small queue can reject tasks earlier. Determine which policy satisfies your SLA.

### 5.2. Spring Configuration for Blocking I/O Groups

The following configuration example requires Spring Framework and appropriate dependencies; place it in `AsyncExecutionConfig.java` (this is a Spring application snippet, not runnable standalone with bare `javac`):

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutionConfig {
    @Bean("outboundIoExecutor")
    ThreadPoolTaskExecutor outboundIoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("outbound-io-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

Meaning: under normal load, the executor uses up to four core workers; it can grow to eight once the finite queue is full; when no capacity remains, it rejects rather than holding requests unboundedly. The values 4/8/64/20 **are only samples to illustrate the mechanism**, not a default production configuration.

With `AbortPolicy`, rejected tasks trigger a submission error (which Spring can translate to `TaskRejectedException`); the calling layer must decide whether to return 429/503, persist work durably, reroute, or perform bounded retries. Do not wait until overload occurs to decide handling policy.

`setWaitForTasksToCompleteOnShutdown(true)` prioritizes finishing already-accepted work, including the queue, during shutdown. `setAwaitTerminationSeconds(20)` sets the wait window during the shutdown phase per the API; it **does not** guarantee every task finishes within 20 seconds and does not make tasks durable across a process crash. Exact shutdown behavior also depends on Spring version, how the context is closed, and signal delivery infrastructure; test against your target runtime.

### 5.3. Choosing a Pool for CPU-Bound Work

For pure CPU computation, set the limit on concurrently running tasks near effective CPU capacity, then measure throughput/latency in a real environment (containers may have CPU quotas). More threads than cores do not increase compute capacity; they may only increase context switching and cache contention.

If an API combines heavy computation and blocking I/O, consider separate pools for each type or splitting the pipeline. Avoid sharing one small pool between long CPU tasks and fast-response tasks if that causes starvation.

### 5.4. Under Overload, Where Should Tasks Wait?

A pool with an unbounded queue turns “insufficient capacity” into **accumulating latency and memory**. A safer approach:

- Bound running tasks, queues, and downstream connections.
- Set timeouts/retry limits at the API, DB, and client layers; avoid waiting indefinitely.
- Prefer fail-fast responses when the caller's deadline can no longer be met.
- Use a durable queue when work must be processed later, with idempotency keys and retry policies.
- Monitor rejections, queue length, queue wait, active count, completed count, latency, and errors.
- If applying `CallerRunsPolicy`, understand that tasks run on the caller's thread when the pool/queue is full. That provides backpressure yet can prolong HTTP handling or block an event loop; do not pick it blindly for every environment.

### 5.5. Java 17+: Simulating a Bounded Pool and Rejection

The runnable example below intentionally holds the first task until main releases a latch, so the outcome does not depend on “guessing” thread scheduling.

File `BoundedPoolChoiceDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolChoiceDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            Future<?> running = pool.submit(() -> {
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            Future<?> queued =
                    pool.submit(() -> System.out.println("queued task ran"));

            try {
                pool.execute(() -> {});
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException e) {
                System.out.println("third task rejected");
            }

            release.countDown();
            running.get();
            queued.get();
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

```bash
javac BoundedPoolChoiceDemo.java
java BoundedPoolChoiceDemo
```

Output:

```text
third task rejected
queued task ran
```

One worker is waiting; one queue slot holds the second task; the third task is rejected. The latch guarantees the first task has not freed the worker before main tests rejection. This demonstrates the bounded-load principle of `ThreadPoolExecutor`; in Spring, `ThreadPoolTaskExecutor` provides similar configuration and translates certain errors per its contract.

## 6. Virtual Threads: Higher Concurrency for Blocking I/O, Still Requiring Load Control

Java 21 provides stable virtual threads. They let very many tasks use readable blocking-style code while the JVM schedules them across a smaller number of platform threads. Virtual threads are generally helpful when **tasks spend most of their time waiting on I/O**; they do not solve CPU limits, DB connection pools, or upstream quotas.

In supporting Spring Framework releases (e.g., Spring 6.1+):

- `VirtualThreadTaskExecutor` creates a new virtual thread per task.
- `SimpleAsyncTaskExecutor` can use virtual threads when the corresponding option is enabled on JDK 21+; this executor has no traditional thread-reusing pool.
- Supported Spring Boot versions can enable virtual threads via `spring.threads.virtual.enabled=true`; impact on auto-configured executors/schedulers depends on version and user-declared beans. Do not assume every custom executor automatically converts to virtual threads.

**Virtual threads are not a concurrency-limiting mechanism.** With 50,000 requests simultaneously calling a service that only permits 40 connections, creating 50,000 virtual threads does not turn 40 connections into 50,000. You need semaphores, HTTP connection pools, rate limiters, bounded queues, or admission control at the proper boundaries.

### 6.1. Java 21+ Example with virtual-thread-per-task Executor

File `VirtualThreadChoiceDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadChoiceDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> first = executor.submit(() -> 40);
            Future<Integer> second = executor.submit(() -> 2);
            System.out.println(first.get() + second.get());
        }
    }
}
```

```bash
javac VirtualThreadChoiceDemo.java
java VirtualThreadChoiceDemo
```

Output:

```text
42
```

`try` with the executor (JDK 21+) closes the resource and waits per the `ExecutorService.close()` contract. Do not infer that two tiny calculations run faster simply from using virtual threads; the example illustrates lifecycle and API. When workers access real remote I/O, apply timeouts, connection limits, and concurrent-request caps.

### 6.2. Limiting Downstream Access with a Semaphore

File `SemaphoreLimitDemo.java`, running on Java 17+:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 10; i++) {
                jobs.add(executor.submit(() -> {
                    try {
                        permits.acquire();
                        try {
                            int now = active.incrementAndGet();
                            peak.accumulateAndGet(now, Math::max);
                            // Represents an operation against a limited resource.
                        } finally {
                            active.decrementAndGet();
                            permits.release();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }));
            }
            for (Future<?> job : jobs) {
                job.get();
            }
            System.out.println("underLimit=" + (peak.get() <= 2));
            System.out.println("allFinished=" + (active.get() == 0));
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac SemaphoreLimitDemo.java
java SemaphoreLimitDemo
```

Output during a normal run with no external interruption:

```text
underLimit=true
allFinished=true
```

Even though the executor has up to four workers, the semaphore allows at most two tasks into the resource-using section concurrently. In a real system, `acquire` may need a timeout, excess tasks may need to be rejected, and metrics must track tasks waiting for a permit. This example does not assert that `peak` always equals two.

### 6.3. Practical Issues to Verify

- Blocking I/O: do libraries/drivers support interruption and timeouts as expected?
- Thread-locals: each virtual thread has its own ThreadLocal values; heavy ThreadLocal usage at very high concurrency still incurs memory/context cost.
- CPU-bound: virtual threads do not bypass core-count limits.
- Task volume: unbounded task creation can still exhaust heap, connections, file descriptors, and OS resources.
- Spring Boot with virtual threads: certain pool-size properties no longer govern virtual-thread executors as before; verify exact auto-configuration on your running version.
- JVM lifecycle: virtual threads are daemon threads; in applications with only scheduled/background virtual threads left, an appropriate keep-alive mechanism is needed when the process must stay alive. For supported Spring Boot versions, check `spring.main.keep-alive`.

## 7. Async Methods: Choosing an Executor per Business Category

`@EnableAsync` enables `@Async` support with the proper configuration; `@Async("beanName")` tells Spring to route the method to the designated executor. This is useful when tasks with different profiles should not compete in the same pool.

Spring application example (split each `public class` into its own file, with Spring dependencies):

File `LookupWorker.java`:

```java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LookupWorker {
    @Async("outboundIoExecutor")
    public CompletableFuture<String> normalize(String input) {
        return CompletableFuture.completedFuture(
                input.trim().toUpperCase(Locale.ROOT));
    }
}
```

File `LookupCaller.java`:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LookupCaller {
    private final LookupWorker worker;

    public LookupCaller(LookupWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> run(String text) {
        return worker.normalize(text);
    }
}
```

This is a routing example; the sample work is tiny and **in practice should run synchronously**. It shows Spring selecting the executor bean named `outboundIoExecutor` from the previous config when calls to `LookupWorker.normalize(...)` traverse the Spring proxy. Never assume execution is always on a new thread without confirming the interceptor, scope/proxy, and executor are properly configured.

Three important notes:

1. **Self-invocation:** calling `this.normalize(...)` within the same bean normally bypasses the `@Async` proxy in default mode, so the method is not offloaded as expected.
2. **Results and errors:** use `CompletableFuture`/`Future` when the caller needs to observe success or failure. An async method returning `void` has no channel to return exceptions to the caller; configure `AsyncUncaughtExceptionHandler` and logging if you must use it.
3. **Thread boundary:** transaction, security, MDC, locale, and request-scoped contexts are not propagated by default. A transaction on the caller thread does not automatically cover what happens later on the worker thread.

If the caller immediately invokes `worker.normalize(...).join()` on the request thread, the caller still blocks. Concurrency benefits must come from application structure, such as returning a job ID, composing multiple futures properly, or using async HTTP framework handling.

### 7.1. One Shared Executor or Multiple Executors?

One shared pool is easy to configure yet can cause **head-of-line blocking**: long-running data-sync batches fill all workers and queues while urgent notification tasks sit waiting behind them. Separating pools establishes resource boundaries:

- `cpuExecutor`: worker count matched to CPU, short queue, deadline-bound computations.
- `outboundIoExecutor`: for blocking calls, bounding threads and connections.
- `mailExecutor`: work outside the request-response path, still with rejection/timeouts/monitoring.
- `maintenanceScheduler`: triggers on schedule; heavy work is submitted to an appropriate worker pool.

Conversely, too many pools make total threads, queues, and memory hard to manage. Each pool needs a clear **resource budget** and owner; split only when justified by workload, priority, or fault isolation.

## 8. Scheduling: When to Run and How Often?

Use `TaskScheduler`/`@Scheduled` for time-based triggers: periodic scans, cache refreshes, small reports. Pick among the common trigger modes:

- `fixedDelay`: measures the wait after the previous run finishes before firing the next; does not attempt to keep start times evenly spaced.
- `fixedRate`: fires at a steady cadence; if a task is slow or workers are scarce, actual start times can slip. Do not assert that a single task automatically overlaps with itself across all implementations.
- `cron`: fires on a calendar schedule. Account for time zones, daylight saving time (if applicable), restarts, and missed triggers.
- `TaskScheduler.schedule(...)`: submits callbacks by `Instant`, `Trigger`, or period via API instead of fixed annotations.

`ThreadPoolTaskScheduler` belongs to Spring-managed schedulers. Too few scheduler workers can let one slow callback delay others. Do not assume raising scheduler size suffices when callbacks hold connections for long periods; you may need a **lightweight scheduler strictly for triggering**, with actual work handled by a bounded worker pool.

A Spring configuration fragment (not a standalone runnable Java program):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableScheduling
class SchedulingConfig {
    @Bean
    ThreadPoolTaskScheduler maintenanceScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("maintenance-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(15);
        return scheduler;
    }
}
```

The configuration above makes sense inside a Spring context and needs overlap/shutdown testing. It does not guarantee jobs run exactly once cluster-wide. Each application replica has its own `@Scheduled` bean, so deploying three instances can trigger three concurrent executions on the same schedule. If system-wide single execution is required, use a centralized scheduler, leader election, distributed leases/locks, or coordinated queue consumers; design jobs to be idempotent since distributed systems can still retry or fail mid-way.

**Do not confuse a scheduler with a durable job queue.** In-memory schedules are affected by JVM restarts and node outages. Financial or critical business jobs that must not be lost require state persistence, retries, duplicate protection, and backlog monitoring.

## 9. Reactive / WebFlux: Never Block the Event Loop

In WebFlux, Reactor pipelines support a non-blocking model when all underlying I/O operations are non-blocking. If a reactive endpoint directly calls a blocking JDBC/HTTP client on the event loop, shared threads can be held waiting, impacting many requests.

If a compatible reactive driver/client exists, prefer using it throughout the pipeline. When a blocking dependency cannot yet be replaced, wrap the call with `Mono.fromCallable(...)` and `subscribeOn(Schedulers.boundedElastic())` at the proper boundary:

```java
// Fragment: assumes a Reactor-based service where blockingClient already exists.
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id))
    .subscribeOn(Schedulers.boundedElastic());
```

The snippet above requires importing Reactor, the `Result` type, and the client in the project, so it is **not** a standalone Java program. `boundedElastic` is a bounded scheduler for blocking work; it does not make a blocking API truly non-blocking and still has queue/resource limits. Under high throughput, verify backpressure, connection pools, timeouts, and downstream concurrency.

Do not blindly route every Reactor operator through `@Async` or `parallel()`. `parallel()` is for suitable CPU work, whereas `boundedElastic()` is typically for adapting blocking code; misuse adds context switching without raising throughput.

## 10. Spring Boot, Java, and Container Environments: Verify Which Configuration Actually Applies

Spring Boot provides auto-configuration for task execution/scheduling, yet behavior depends on version, existing executor beans, and integrating components. In applications with custom config:

- Verify which executor `@Async` actually picks—whether `@Async("name")` or an `AsyncConfigurer` is present.
- Verify which executor bean Spring MVC/WebFlux, WebSocket, GraphQL, or other subsystems use; **do not** assume they all share one custom bean simply because an `Executor` bean exists in the context.
- Check application profiles, environment variables, and overrides across local/test/staging/production.
- Check the container's actual CPU quota/memory limits, not just physical host core counts.
- Check JDK version (17/21+), Spring/Boot version, and whether virtual threads are enabled. Pool-tuning properties may no longer carry the same meaning if the executor is replaced by a virtual-thread strategy.

Example Spring Boot properties can configure the auto-configured pool when applicable, **without** guaranteeing they apply to a `@Bean` `ThreadPoolTaskExecutor` you created yourself:

```yaml
spring:
  task:
    execution:
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
      thread-name-prefix: app-task-
    scheduling:
      pool:
        size: 2
```

Verify the beans created in the context and real metrics; a property appearing in YAML does not prove it governs the executor a method actually uses. If the application has multiple executors, prefer explicit bean names/qualifiers over relying on defaults.

**Java 21 and virtual threads:** on supported Boot versions, `spring.threads.virtual.enabled=true` enables a virtual-thread-based execution strategy; platform-thread pool settings may no longer take effect as before. Enabling it must account for library compatibility, blocking behavior, `ThreadLocal` volume, database load, and mechanisms to keep the JVM alive for background tasks.

### 10.1. Inside a Jakarta EE Application Server

When infrastructure manages threads via the container, creating `new Thread` or an unmanaged `Executors.newFixedThreadPool` can violate classloader, context, and shutdown conventions. Spring provides adapters for managed executors/schedulers (such as `DefaultManagedTaskExecutor` and `DefaultManagedTaskScheduler` when supported by the environment); this is an ownership problem, not merely an API swap.

### 10.2. In Tests

A synchronous executor like `SyncTaskExecutor` enables deterministic logic checks when thread boundaries are not under test. However, concurrency bug tests must run with a real asynchronous executor, latches/barriers, and explicit timeouts. Never use synchronous tests to claim race conditions are solved.

### 10.3. In Multi-Replica Container Environments

Total upstream capacity limits must be calculated **system-wide**: if a service has 10 replicas and each instance allows 50 concurrent DB calls, the theoretical maximum is 500 concurrent calls, exceeding DB connection capacity. Per-process semaphores only cap each instance; cluster-wide limits require distributed admission/rate limiting or dividing the total budget across replicas.

## 11. Estimating Capacity: Throughput, Latency, Concurrency, and Queues

Never configure “max = 200 threads” without data. Three foundational quantities:

- **Arrival rate** (λ): tasks/second arriving at the system.
- **Residence/response time** (W): average time each task spends in the system (which may include queue and service time).
- **Average tasks present** (L): for a stable system over the same measurement boundary, Little's Law gives `L = λ × W`.

For example: 100 requests/sec, with each request spending 0.4 seconds in the observed region, means **roughly 40 requests on average** are concurrently present in that region. This **does not** automatically mean 40 CPU threads are needed: if they mostly wait on I/O, required platform threads/virtual threads/connections differ; if all are CPU-bound, CPU capacity will be the bottleneck.

### 11.1. A Minimal Capacity-Planning Process

1. Measure p50/p95/p99 service time and queue wait per task group, separating CPU from blocking wait.
2. Measure average and peak arrival rates, burst durations, deadlines, and fault tolerance.
3. Measure effective CPU, memory, database connection pools, outbound HTTP connection limits, and API quotas.
4. Cap concurrency at the **real bottleneck**, then pick the matching pool/virtual-thread strategy.
5. Size queue capacity for bursts absorbable within the wait budget; never let the queue grow larger than deadlines allow.
6. Set rejection policies, fallbacks, and retry/backoff; verify whether operations are idempotent.
7. Load test steady-state, bursts, and sustained load; measure throughput, p95/p99 latency, queue occupancy, active count, rejections, timeouts, errors, CPU, and memory.
8. Test shutdown, rolling deploys, slow networks, and downstream failures; tune based on observed results.

A queue holding 1,000 tasks at a processing rate of 20 tasks/sec will take about 50 seconds just to drain those tasks even with zero new arrivals and constant throughput. If callers can only wait 2 seconds, such a large queue solves nothing. Use this simple model to catch nonsensical settings, then validate with real load tests.

### 11.2. Rough Formulas for CPU and Blocking I/O

For CPU-bound work, the starting point is typically concurrency equal to effective core count (adjusted for other workloads and the JVM), followed by measurement. For blocking I/O, more threads may be needed since each thread uses CPU only part of the time; however, connection limits and target system latency usually determine the sensible ceiling.

Rules of thumb based on wait/service ratios are only **initial estimates**. Do not apply them rigidly when tasks mix phases, use virtual threads, hit rate-limited downstreams, or experience large queue-wait swings under load.

## 12. Choosing by Priority, Reliability, and Fault Isolation

Beyond classifying CPU vs. I/O, applications have multiple **criticality levels**.

| Workload group | Goal | Solution pattern |
| --- | --- | --- |
| Auth and interactive API responses | Low p95 latency, fast failure on overload | Short sync or bounded offload; small queue, clear timeouts |
| Blocking partner HTTP calls | Control fan-out and quotas | Bounded I/O pool or virtual threads + semaphore/connection pool |
| Heavy report computations | Keep CPU stable, avoid starving requests | Dedicated CPU pool, job ID if long-running |
| Emails/notifications not needed in response | Return response before sending | Durable job queue if non-lossy; retrying workers |
| Periodic cache refreshes | Tolerate slight delay | Scheduler, deadlines, prevent unnecessary overlapping runs |
| Audits/payments/critical business steps | At-least-once with safe duplicate handling and audit | Persistence + transactional outbox/queue/workflow where appropriate |

**Isolation:** if jobs require different recovery guarantees and priorities, partition resources by group or use separate consumer processes. Never let bulk image uploads exhaust the connection pool and cause timeouts for critical transactions.

**Task priority:** default `ThreadPoolExecutor` does not turn a FIFO queue into a strict business-priority scheduler; even with a priority queue you must prevent starvation, ensure thread safety, and align cancellation/metrics. It is usually simpler to separate queues/pools by defined criticality.

## 13. Executor Lifecycle and Controlled Shutdown

Executor ownership determines who may call shutdown:

| Owner | How it is used | When to close |
| --- | --- | --- |
| Spring-managed `@Bean ThreadPoolTaskExecutor` | Inject/`@Async` by name and let Spring coordinate | When the application context closes via built-in lifecycle |
| Spring-managed `ThreadPoolTaskScheduler` | Scheduled triggers via Spring config | On context close, with defined completion/cancellation policy |
| Executor created privately by a method | Used only within a clearly scoped local task | That method itself must call `shutdown`/await in `finally` |
| Jakarta EE container-managed executor | Used via provided abstractions | Lifecycle belongs to the container; app never closes shared resources |
| Out-of-process queue/worker | Publish jobs and get status/results via protocol | Lifecycle controlled by broker/worker manager/cluster |

Ideal shutdown sequence for an in-memory executor:

1. **Stop admitting new work** or transition to not-ready; handle rejections intentionally.
2. **Set a wait limit** for already-accepted tasks; wait for work that must finish within the grace period.
3. **Request cooperative cancellation** for skippable tasks: interrupts, cancellation, client/DB timeouts, and resource cleanup.
4. **Record incomplete work** if business rules require retries; if stored only in RAM, crash recovery cannot be guaranteed.
5. **Wait up to the deadline**, emit final metrics/logs, and exit; infrastructure may kill the process after the grace period.
6. **Verify restarts:** do not re-run already-completed jobs, do not drop unfinished jobs; enforce idempotency/deduplication.

A Spring-managed executor should never have `shutdown()` called mid-flight by individual services. If multiple consumers share the same executor bean, one consumer shutting it down breaks submissions for everyone else.

### 13.1. Java 17+: Shutdown and Cooperative Cancellation Example

File `CooperativeShutdownDemo.java` illustrates sending an interrupt signal via `Future.cancel(true)` and awaiting executor termination:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeShutdownDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean observedInterrupt = new AtomicBoolean(false);

        try {
            Future<?> job = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException e) {
                    observedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            job.cancel(true);
        } finally {
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("terminated=" + terminated);
        System.out.println("interruptSeen=" + observedInterrupt.get());
    }
}
```

```bash
javac CooperativeShutdownDemo.java
java CooperativeShutdownDemo
```

Output in a normal runtime when the worker responds to interruption within five seconds:

```text
terminated=true
interruptSeen=true
```

`cancel(true)` only requests interruption; the task code decides how to respond. If a task is stuck on non-interruptible I/O or ignores interrupt status, it may not stop within the expected window. `awaitTermination` returns a boolean so callers can distinguish finished vs. remaining tasks; never ignore the `false` case in production.

### 13.2. When Is a Durable Job Needed Instead of an In-Process Executor?

Choose a durable job when at least one condition holds:

- The job must complete even across JVM/process restarts.
- It must retry after temporary external DB/API failures.
- You need to inspect `PENDING/RUNNING/SUCCEEDED/FAILED` status, audit, or intentionally replay.
- It may take minutes/hours or exceed HTTP deadlines.
- Workers must scale independently of the web app or regulate consumption rate.

Appropriate pattern: the request persists the work (or transactional outbox), responds `202 Accepted` with a job ID, workers pull jobs from the durable store, update status, and use idempotency keys to prevent duplicate side effects. “Returning 202” only means the server **accepted the request per the defined contract**; without durable persistence, you cannot promise the job survives a restart.

## 14. Timeouts, Retries, Backpressure, and Cancellation Tied to Executor Choice

Many incidents stem from offloading without **deadlines**:

- `Future.get(timeout, unit)` only bounds how long **the calling thread waits**; timing out does not automatically cancel the worker. Calling `cancel(true)` requires an explicit policy.
- `CompletableFuture.orTimeout(...)` sets the future's completion state; it does not automatically stop physical I/O already in progress. You must still configure client/driver timeouts and cancellation if supported by the API.
- HTTP client/DB timeouts typically need at least appropriate connect/read/total deadlines; queue wait must also fit within the overall latency budget.
- Unbounded retries inside tasks holding threads can amplify load right when a downstream is failing. Use bounded retries with backoff/jitter and idempotency whenever side effects are possible.
- `Semaphore`/rate limiters at downstream boundaries remain valuable even when an executor has thousands of virtual threads.
- Rejection policies are part of the API contract: tasks may not be accepted; decide whether to return errors, retry, or persist rather than silently dropping work.

If remaining deadline budget is already smaller than expected queue wait, admitting a task only to let it time out in the queue wastes resources. Backpressure and fail-fast can protect p95 latency better than queuing everything.

### 14.1. Never Accidentally Transfer Transactions or Request State

`@Async` normally switches threads; Spring transaction context and caller-thread request state are not automatically present on the worker. Avoid passing raw `HttpServletRequest`, managed persistence entities, or mutable DTOs into long-running background tasks. Instead pass required IDs/immutable snapshots; the task opens its own transaction at its boundary when needed.

MDC/trace context and security identity require intentional propagation, with cleanup paths tested when worker threads are reused. Spring provides `TaskDecorator` and appropriate context-propagation integrations, yet a decorator does not replace ownership and does not guarantee automatically carrying all thread-locals or transactions.

## 15. Testing All Three Axes: Load, Environment, and Lifecycle

A configuration is only considered suitable after verifying behavior under the system's actual conditions.

### 15.1. Load Testing

- **Steady-state:** arrival rate below processing capacity; is the queue stable, and does p95 meet SLO?
- **Burst:** sudden traffic spikes; how high does the queue peak, and when do rejections occur?
- **Sustained overload:** arrival rate above capacity; does the system fail fast or keep memory stable?
- **Slow/disconnected downstream:** do timeouts prevent tasks from holding workers indefinitely?
- **Reduced CPU quota:** is the app spawning too many workers relative to real CPU?
- **Multi-replica:** are total connections, rate limits, and scheduler duplicates controlled?

### 15.2. Environment Testing

Verify which executor is **actually used** via bean names, thread-name prefixes, metrics, and thread-dump inspection. For Spring Boot, run under the exact profile and runtime version. For WebFlux, use event-loop blocking-detection tools where appropriate. For virtual threads, measure I/O speed, memory, ThreadLocals, and downstream limits together.

### 15.3. Lifecycle Testing

- Close the Spring context while tasks are queued and running; which tasks finish/cancel, and does shutdown finish on time?
- Try submitting tasks after the executor has begun shutting down; how do callers receive rejections?
- Send SIGTERM / perform rolling updates in a production-like environment; verify grace periods and readiness.
- Restart while durable jobs are running; are jobs recovered/retried without duplicate side effects?
- Test cancellation with `CountDownLatch`/barriers and timeouts; never rely on `Thread.sleep` to guess ordering.
- With `@Async`, verify calls actually pass through the proxy and exceptions are observed.

Metrics should be tagged with **workload group/executor name** and trace IDs where appropriate: active workers, pool size, queue depth, queue wait, tasks completed, rejected count, task duration, errors/timeouts/cancellations, CPU, heap, GC, and p95/p99 latency. Never leak personal data in log/metric payloads.

## 16. Reference Choices by Scenario

| Scenario | Execution strategy to try first | Mandatory conditions |
| --- | --- | --- |
| Validate DTO and compute simple fee in a request | Synchronous | Low latency, clear invariants/transaction |
| Call three independent blocking REST APIs in an MVC request | Bounded I/O executor or virtual threads with result aggregation | Per-API timeouts, connection caps, request deadline |
| Encrypt thousands of large files | Dedicated CPU pool, chunkable work | CPU/memory and queue bounds, cancellation |
| WebFlux app using a reactive HTTP client | Reactor non-blocking pipeline | Never block event loop, backpressure |
| WebFlux temporarily forced to use a blocking SDK | `boundedElastic` adapter | Bound blocking, protect downstream, plan SDK replacement |
| Send email after API returns 202, must not be lost | Durable queue/job worker | Persist before ack, retries, idempotency |
| Sync cache at 2 a.m. across three replicas | Cluster-coordinated scheduler | Avoid unintended triple execution, idempotent job |
| Command-line app processes a list and exits | Finite local executor + await | Await results, shut down executor, exit code reflects errors |
| Jakarta EE server provides a managed executor | Managed executor/scheduler | Respect container lifecycle/context |
| Unit tests wanting deterministic behavior | Synchronous executor | Still keep separate concurrency tests |

## 17. Common Mistakes

| Mistake | Why it hurts | Replacement rule |
| --- | --- | --- |
| “Use `@Async` for all slow processing.” | No job ID, timeout, result, or durability; errors may be dropped | Define caller contract and lifetime first |
| “A large `maxPoolSize` automatically spins up many threads.” | A long queue can keep the pool at `corePoolSize` | Understand core → queue → max → rejection |
| “Unbounded queues prevent errors.” | Converts errors into latency/memory bloat and expired deadlines | Bounded queue, explicit admission/rejection |
| “Virtual threads need no concurrency limits.” | DB/API quotas, heap, and file descriptors remain finite | Semaphores/connection pools/rate limits at the resource |
| “Switching to async makes requests non-blocking.” | Callers may still call `get()/join()` right away | Design end-to-end async or return a job ID |
| “`@Async` always runs on another thread.” | Self-invocation can bypass the proxy | Verify call path and executor bean |
| “Raising scheduler pool size ensures cron runs once cluster-wide.” | Every replica has its own scheduler | Distributed coordination or external scheduler |
| “`@Scheduled` is a durable queue.” | Restarts/stops can lose executions | Persist jobs if business rules require it |
| “`shutdownNow()` guarantees stopping all tasks.” | Interruption is cooperative | Timeouts, cancellation, and cleanup inside tasks |
| “YAML config surely applies to the current pool.” | Custom beans/versions/virtual threads can override it | Verify runtime beans and metrics |
| “`Future.get(timeout)` stops the I/O.” | Wait timeout does not cancel the operation | Client timeouts, cancellation, total deadlines |
| “One shared pool is simple and good enough.” | Heavy tasks starve critical business paths | Isolate pools/queues by priority and budget |

## 18. Practice Exercise: Designing Executors for a Three-Workload System

Suppose a Spring application has: (A) an endpoint calling a product API taking 200 ms on average, (B) a CPU-heavy report taking several seconds, and (C) a periodic partner-state sync job that must resume after restarts.

### Implementation Requirements

1. Write a table for each task: CPU vs. I/O, peak concurrency, deadline, downstream quota, result, failure handling, and owner.
2. Propose an execution path for A: blocking request, MVC async, or end-to-end reactive; pick an appropriate bounded I/O pool/virtual threads and connection limits; explain whether the caller waits or receives a future.
3. Propose B: dedicated CPU pool, bounded queue, return job ID if exceeding HTTP deadline, test CPU quotas and cancellation.
4. Propose C: scheduler triggers only, durable job records, and workers with retries; prevent duplicates across multiple replicas.
5. Set hypothetical initial configs: core/max/queue or virtual-thread strategy, timeouts, queue rejection, maximum downstream concurrency, and shutdown grace.
6. Create scenarios for steady-state load, bursts, a hung downstream, rolling restarts, and two requests competing for the same pool.
7. Collect metrics: queue wait, active workers, rejections, errors, p95/p99, CPU, connection count; adjust configuration based on actual bottlenecks.
8. Describe the contract when a task is rejected: what HTTP code the API returns, whether the job was persisted beforehand, and whether clients can safely retry.
9. Verify shutdown: reject new work when not-ready; handle/cancel accepted tasks per SLA; lose zero durable jobs.

### Acceptance Criteria

- [ ] I can explain why “more threads is always better” is wrong for CPU-bound work and quota-limited downstreams.
- [ ] I can choose among synchronous, bounded pool, virtual threads, scheduler, Reactor, and durable worker based on task traits.
- [ ] I understand `corePoolSize`/`maxPoolSize`/`queueCapacity` and when rejection occurs.
- [ ] I do not use unbounded queues to hide overload or let jobs exceed deadlines.
- [ ] I define timeouts, cancellation, results/errors, and retry policies before implementation.
- [ ] I know the differences among MVC, WebFlux, application server, and multi-replica environments.
- [ ] I accurately identify who owns the executor and the graceful shutdown/restart flow.
- [ ] I verify runtime configuration instead of guessing from YAML or bean names.
- [ ] I have load tests and failure tests for my executor selection.

**Key point:** an executor is part of your **resource and lifecycle contract**. The right execution strategy protects CPU, connections, and deadlines under load, matches the environment's threading model, and provides verified paths for completion, errors, overload, cancellation, and restarts.

## 19. Official Documentation to Cross-Check for Your Version

- Spring Framework Reference — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, `@Async`, `@Scheduled`, and implementation choices.
- Spring Framework API — [ThreadPoolTaskExecutor 6.1](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): default queue/pool, core/max/capacity parameters, and lifecycle.
- Spring Boot Reference — [Task Execution and Scheduling (3.4)](https://docs.spring.io/spring-boot/3.4/reference/features/task-execution-and-scheduling.html): auto-configuration principles and distinguishing executors used by components.
- Spring Boot Reference — [Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html): Java 21+ requirements, configuration, and lifecycle/keep-alive considerations.

Spring/Boot and JDK documentation can change across versions. When deploying, check the exact release in use rather than taking defaults from documentation of another release.
