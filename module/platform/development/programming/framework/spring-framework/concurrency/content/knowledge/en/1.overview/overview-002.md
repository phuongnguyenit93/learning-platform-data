# Distinguishing Synchronous, Asynchronous, Parallel, and Scheduling in Spring Framework

The four terms **synchronous**, **asynchronous**, **parallel**, and **scheduling** often appear together when building Spring applications, yet they answer **four different questions**. Confusing them easily leads to API designs that cause unnecessary waiting, misconfigured thread pools, duplicate job runs, or assumptions that a task has already completed when it has only been placed into a queue.

After this lesson, you should be able to distinguish caller behavior, how work is executed, when it is triggered, and the appropriate Spring components; while also recognizing when these mechanisms can be combined.

## 1. The Core Nature of Each Concept

### 1.1. Synchronous: The Caller Waits for the Result

A **synchronous** call only completes for the caller when the operation has returned a result or thrown an error. During that time, the caller's execution thread cannot proceed to the next statement. For example:

```java
String report = reportService.generate("R1"); // Waits for generate to finish
sendResponse(report);                         // Runs only after report is available
```

Imagine the sequence:

```text
Caller:  call generate ───────────── wait ───────────── receive result → continue
Work:                  start → process → finish
```

The key point is the **waiting relationship between the call and the result**, not the number of threads. A method may hand work off to another thread yet call `Future.get()` or `CompletableFuture.join()` immediately; from the caller's experience, that code still waits synchronously.

### 1.2. Asynchronous: The Caller Continues Before the Work Finishes

An **asynchronous** operation allows the caller to regain control before the work finishes. The result arrives later via a `CompletableFuture`, callback, event, queue, or another notification mechanism.

```java
CompletableFuture<String> result = reportService.generateAsync("R1");
doOtherWork();                  // Can run while generateAsync is still processing
String report = result.join();  // Only waits here if the result is not ready yet
```

```text
Caller:   call → receive Future → do other work ── join/read result → continue
Worker:          receive task ── execute ── complete Future
```

Asynchronous **does not mean**: running faster, always having a new thread, using no threads, never waiting, or that work definitely runs in parallel. A Future may complete immediately; the caller can also defeat the benefit of asynchrony by calling `join()` right after submitting the work.

In Spring, `@Async` typically delegates a method to a `TaskExecutor`, so the calling thread does not need to perform all the work directly. However, the worker thread can still be blocked by synchronous I/O inside.

### 1.3. Parallel: Multiple Pieces of Work Actually Run at the Same Time

**Parallelism** describes **how execution happens**: two or more pieces of work progress simultaneously at the same moment on different processing resources (usually multiple CPU cores). A common goal is to reduce the total processing time of divisible work.

Distinguish this further from **concurrency**:

- **Concurrency:** multiple tasks are managed within the same time window; on a single CPU core, they may interleave turns without actually executing simultaneously at any single instant.
- **Parallelism:** genuinely simultaneous execution across multiple processing resources.

```text
One core, interleaved (concurrent):
Time →  [A][B][A][B][A][B]

Two cores, parallel:
Core 1 →  [A][A][A][A]
Core 2 →  [B][B][B][B]
```

For example, `list.parallelStream().map(...).toList()` can distribute processing across multiple workers, but the `toList()` call only returns when the necessary processing has finished; that is, **internally it may be parallel, while the caller still waits synchronously**. Conversely, an executor with only one worker can still serve an asynchronous API and run tasks sequentially.

Parallelism does not automatically guarantee speedup: task-splitting/merging overhead, lock contention, I/O, CPU limits, and shared data can make the result slower or incorrect.

### 1.4. Scheduling: Deciding When to Trigger

**Scheduling** describes **when** a piece of work is triggered: at 08:00 every weekday, after 5 seconds, or at a fixed interval. In Spring, `@Scheduled` and `TaskScheduler` are the representative tools.

```java
@Scheduled(fixedDelay = 5_000)
public void refreshCache() {
    refresh();
}
```

Scheduling does not predetermine whether work runs synchronously or asynchronously, or on one thread or many. A job invoked by a scheduler can execute directly on the scheduler thread, or hand off to an executor and return. **A scheduler answers "when?"; an executor answers "where and with which workers does it execute?"**

## 2. Do Not Confuse With Blocking/Non-Blocking

**Blocking** and **non-blocking** form an orthogonal axis: whether a thread has to wait for a resource or result.

- **Blocking I/O:** the thread stands waiting on a network, file, or database operation; calling via `@Async` only moves that wait onto a worker.
- **Non-blocking I/O:** the operation does not hold a thread waiting for the I/O result; the result is handled when data is ready.
- **Asynchronous:** the caller can continue before the operation finishes, whether the underlying operation uses blocking or non-blocking I/O.

For example, Spring MVC can return a `CompletableFuture` to handle HTTP asynchronously while the task inside still uses blocking JDBC. Spring WebFlux can use a reactive/non-blocking pipeline when every component involved supports it; merely wrapping a blocking JDBC call in `Mono` **does not turn JDBC into non-blocking**. Do not place blocking calls onto the WebFlux event loop.

## 3. Quick Comparison Table

| Concept | Primary Question | Observed from Caller/System | Common Tools |
| --- | --- | --- | --- |
| Synchronous | When does the call return? | Caller waits for the operation to complete | Direct Java calls, `get()`/`join()` |
| Asynchronous | Does it return control early? | Result/error arrives later; caller can do other work | Spring `@Async`, `TaskExecutor`, `CompletableFuture` |
| Parallel | Do multiple tasks actually run simultaneously? | Multiple workers/cores process pieces of work at the same time | Multi-worker thread pool, `ForkJoinPool`, parallel stream |
| Scheduling | When is work triggered? | Triggered by time/interval | `@Scheduled`, `TaskScheduler`, cron |

**Completely valid combinations:**

1. **Synchronous and sequential:** call a service, receive the result, then call the next service.
2. **Asynchronous with jobs queued sequentially:** submit multiple tasks to a single-worker executor.
3. **Parallel inside a synchronous call:** split work across multiple workers, then `join()` before returning the result.
4. **Scheduled and processed sequentially:** a scheduler triggers a job, and the next run waits until the job finishes.
5. **Scheduled combined with asynchronous:** the scheduler only submits a task to an executor; a worker processes it later and may overlap with the next trigger.

Therefore, claims such as "using `@Scheduled` automatically makes it multithreaded" or "having `@Async` definitely utilizes multiple CPU cores" are both false.

## 4. Standalone Java 17+ Example: Understanding the Difference from the Caller's Side

Save the following as **CallVsExecution.java**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CallVsExecution {
    private static String work(String name) {
        return "done " + name;
    }

    public static void main(String[] args) {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            String first = work("A"); // Synchronous
            System.out.println(first);

            CompletableFuture<String> second =
                    CompletableFuture.supplyAsync(() -> work("B"), worker);

            System.out.println("Caller continues");
            System.out.println(second.join()); // Waits if B is not done yet
        } finally {
            worker.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac CallVsExecution.java
java CallVsExecution
```

**Exact stdout** (only the main thread prints to the console):

```text
done A
Caller continues
done B
```

In step A, the caller receives the result before continuing. In step B, the caller receives a Future and then prints the next line; work B may finish before or after the "Caller continues" line, but the **print order** is deterministic thanks to `join()`. A single worker handles tasks submitted to the executor in turn; an asynchronous API does not require multiple workers. Do not infer the actual execution order solely from log timestamps.

## 5. Related Spring Components

### 5.1. `@Async` and `TaskExecutor`: Submitting Work to Run Later

Spring provides `TaskExecutor` to execute a `Runnable`/task; `ThreadPoolTaskExecutor` is an implementation that manages a pool of threads. When `@EnableAsync` is enabled, Spring can create a proxy to intercept calls to `@Async` methods and submit work to the chosen executor.

Conceptual flow:

```text
HTTP/service caller
      │ calls via Spring proxy
      ▼
@Service @Async("jobExecutor") ── submit ──► executor queue ──► worker
      │                                                     │
      └── returns Future early                              └── completes Future
```

Important note: **calls must go through the Spring proxy**. A method in the same bean calling `this.asyncMethod()` does not go through the proxy in the default mode, so the annotation may not behave as expected. Likewise, do not expect `@Async` to work on direct calls to an object created with `new`, or on `private` methods.

`@Async` is commonly used with return types `void`, `Future`, or `CompletableFuture`. To receive errors and values in a controlled way, prefer `Future`/`CompletableFuture`; if using `void`, pay attention to asynchronous exception handling mechanisms.

### 5.2. `@Scheduled` and `TaskScheduler`: Firing Time-Based Triggers

Spring supports declarative schedules with `@EnableScheduling` and `@Scheduled`. A normal method takes no parameters; the schedule is determined by the annotation configuration rather than a business call from a controller.

- `fixedDelay = 5_000`: waits 5 seconds **after the previous scheduled method invocation finishes** before triggering the next one.
- `fixedRate = 5_000`: targets a 5-second period measured by the **start times** of runs; when a job runs long, punctuality or overlap depends on the scheduler, executor, and implementation, and parallel execution must not be assumed automatically.
- `initialDelay = 2_000`: waits an initial 2 seconds before the first trigger in the corresponding periodic schedule.
- `cron = "0 0 8 * * MON-FRI", zone = "Asia/Ho_Chi_Minh"`: triggers at 08:00 Monday through Friday in the specified time zone. Standard Spring cron expressions have **6 fields**: second, minute, hour, day of month, month, day of week.

If a job directly submits an `@Async` call and returns, `fixedDelay` measures the interval from **when the scheduled method finishes submitting**, not when the asynchronous task completes. Background runs can therefore overlap when processing takes a long time.

For example, under ideal conditions where a job runs for 2 seconds and the configured interval is 5 seconds:

```text
fixedRate:   starts around t = 0s, 5s, 10s, 15s...
fixedDelay:  starts around t = 0s, 7s, 14s, 21s...
```

This is an illustration of timestamps, not a guarantee that the job always runs to the exact millisecond. Busy threads, application pauses, GC pauses, or resource limits can all delay triggering.

## 6. Complete Spring Boot Example: Combining Three Mechanisms

This example uses **Java 17+, Spring Boot 3.x/Spring Framework 6.x** with the `spring-boot-starter-web` dependency and the Spring Boot application runner plugin. Place all of the code below in **src/main/java/com/example/demo/ModesApplication.java**. It is a self-contained demo application in terms of source code, but requires Spring Boot dependencies to compile/run; plain `javac` is not enough.

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModesApplication.class, args);
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("job-");
        executor.initialize();
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.initialize();
        return scheduler;
    }
}

@Service
class ReportService {
    public String createSync(String id) {
        return slowWork(id);
    }

    @Async("jobExecutor")
    public CompletableFuture<String> createAsync(String id) {
        return CompletableFuture.completedFuture(slowWork(id));
    }

    private String slowWork(String id) {
        try {
            Thread.sleep(800); // Simulates blocking I/O only, not a production solution
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Work interrupted", e);
        }
        return "done:" + id;
    }
}

@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/sync/{id}")
    public String sync(@PathVariable String id) {
        return service.createSync(id);
    }

    @GetMapping("/async/{id}")
    public CompletableFuture<String> async(@PathVariable String id) {
        return service.createAsync(id);
    }
}

@Component
class ReportTicker {
    private final ReportService service;

    ReportTicker(ReportService service) {
        this.service = service;
    }

    @Scheduled(initialDelay = 3_000, fixedDelay = 10_000)
    public void tick() {
        service.createAsync("periodic").whenComplete((result, error) -> {
            if (error != null) {
                System.err.println("Scheduled work failed: " + error.getMessage());
            } else {
                System.out.println("Scheduled work result: " + result);
            }
        });
    }
}
```

In a Spring Boot project configured with Gradle, run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), then call:

```bash
curl -s http://localhost:8080/sync/A
curl -s http://localhost:8080/async/B
```

**Corresponding response bodies:**

```text
done:A
done:B
```

Each `curl` command only returns when the HTTP response completes. The two bodies have the same format, but server-side handling differs:

1. `/sync/A`: the request thread directly runs `slowWork` and waits about 800 ms.
2. `/async/B`: the controller returns a `CompletableFuture` to Spring MVC; `slowWork` runs on a `job-*` thread, and Spring MVC completes the response when the Future finishes. This **does not mean the HTTP client receives the result immediately**; the client still waits for the response body.
3. `ReportTicker.tick()`: the scheduler calls the method according to `fixedDelay`; the method hands work off to `jobExecutor`, registers a callback to observe the result, and returns. The scheduler and executor have **two separate roles**.
4. `createAsync` is only called from other beans (`ReportController`, `ReportTicker`), so calls go through the `@Async` proxy. If changed to `this.createAsync(...)` inside `ReportService`, the effect differs.

Job logs and processing order across requests depend on thread scheduling, so there is **no fixed overall stdout order**. Do not use arbitrary log ordering to conclude whether parallelism is present or absent.

### A Common Misconception About Future

Inside the body of `createAsync()`, `CompletableFuture.completedFuture(slowWork(id))` runs `slowWork` **first**, and only then creates an already-completed future. The asynchrony of the external call comes from the **Spring proxy + executor**. If `@Async` is removed and this line is called directly, all of `slowWork` will happen on the caller thread before the Future is returned. Merely seeing a `CompletableFuture` return type is not enough to conclude it runs in the background.

## 7. Combining Mechanisms Based on Real Needs

| Need | Approach | What Needs to Be Controlled |
| --- | --- | --- |
| Reading short data where the result is needed immediately | Synchronous call | Timeouts, dependency latency |
| Generating a time-consuming report that can be retrieved later | Submit work asynchronously; optionally return HTTP 202 with a job ID and status lookup endpoint | State persistence, error handling, retries, idempotency |
| Processing multiple independent CPU-bound parts | Multi-worker executor, controlled data splitting/merging | Core count, shared state, splitting overhead |
| Periodic cache synchronization | `@Scheduled` with `fixedDelay` or cron | Run schedule, schedule delays, overlapping tasks |
| Periodic schedule triggering slow I/O processing | `@Scheduled` calling an `@Async` service via another bean | Queues, backlogs, overlap, lost errors |
| Job that must run once across an entire multi-instance cluster | Scheduler with distributed coordination or a dedicated job/queue system | Ownership, locking, deduplication, crash recovery |

**Do not confuse "returning a Future" with "having a background API"**: an HTTP endpoint that returns a Future and waits for completion still makes the HTTP client wait. If you want the client to submit a request and come back later for the result, you usually need a separate job protocol: return `202 Accepted` and a job ID, persist state, and provide a lookup/result endpoint along with expiration/retry policies.

## 8. Common Mistakes and How to Prevent Them

**Mistake 1 — Calling `@Async` inside the same bean.** Spring AOP intercepts calls via a proxy by default. Extract the asynchronous method into another bean, inject that bean, and call through it. Do not use `this` expecting the annotation to apply.

**Mistake 2 — Creating a Future and waiting immediately.** `supplyAsync(...).join()` at the same spot makes the caller wait for the result. Only switch to a Future when you genuinely have useful work to do before needing the result, or need to combine multiple results.

**Mistake 3 — Assuming `@Scheduled` is parallel by default.** Whether a job overlaps its previous run, and whether jobs are served by different workers, depends on the scheduler, execution duration, and executor handoff. Design around the actual configured behavior and test under load.

**Mistake 4 — Keeping an unbounded thread pool/queue.** Work can arrive faster than it is processed, causing queues to build up, increasing memory/latency, and eventually leading to rejections or overload. With `ThreadPoolTaskExecutor`, set appropriate `corePoolSize`, `maxPoolSize`, and `queueCapacity`; when using a positive-capacity queue, the pool usually prefers queuing tasks before growing beyond the core thread count. Monitor active threads, queue depth, task duration, and rejections.

**Mistake 5 — Adding `@Async` and assuming it is now non-blocking.** A blocking HTTP/JDBC/file I/O call still holds a worker for the duration of the wait. You need concurrency limits, timeouts, and awareness of which resource is waiting. End-to-end non-blocking requires an appropriate pipeline throughout.

**Mistake 6 — Using shared mutable state unsafely.** When multiple workers access the same `HashMap` or counter without synchronization, race conditions and corrupted data can occur. Use immutable data, partitioned ownership, `ConcurrentHashMap`, `AtomicInteger`, or locks when truly needed; parallelism does not replace thread safety.

**Mistake 7 — Forgetting thread-local context and transactions.** Spring transactions are usually bound to the current thread; an `@Async` method running on another thread does not automatically inherit the caller's active transaction. Similarly, MDC logging or security context should not be assumed to propagate to workers. Redefine transaction boundaries and propagate context intentionally.

**Mistake 8 — Swallowing background job exceptions.** Unobserved exceptions from a Future can slip past without the caller knowing; callbacks like `whenComplete`, `exceptionally`, metrics, and logs help capture failures. For periodic jobs, add bounded retry/backoff strategies, alerting, and idempotency before re-running.

**Mistake 9 — Deploying multiple replicas and thinking cron runs only once.** Every Spring instance with scheduling enabled can trigger the same job independently. If the requirement is "once across the entire system," you need a coordination mechanism such as a distributed lock, a queue with consumer ownership, or a distributed scheduler; standalone `@Scheduled` does not guarantee that.

**Mistake 10 — Relying on schedules to guarantee durable delivery.** An in-process trigger may not fire when the application shuts down or may be delayed when the system is overloaded. If you need job persistence, recovery after restarts, history retention, and reliable retries, use a proper storage/coordination solution rather than just an in-memory cron.

## 9. How to Choose a Solution in Spring

Before adding annotations, answer in order:

1. **Must the caller wait for the result immediately?** If yes, synchronous is usually simpler. If not, choose Future/callback/event or a job protocol.
2. **Is the work CPU-heavy or I/O-waiting?** CPU-bound work should consider core count and work splitting; I/O-bound work needs bounded waiting tasks and timeouts. Do not increase threads indefinitely.
3. **Does it need to be triggered on a schedule?** If yes, choose `fixedDelay`, `fixedRate`, or cron based on business semantics; trigger timing is independent of how work is processed.
4. **Is overlapping execution allowed?** If not, you need locks, serialization, or state checks; do not blindly rely on a single-thread pool across all configurations.
5. **Does it require guaranteed retries and single execution in a cluster?** Design retries, idempotency, durable state storage, and cross-instance coordination.
6. **How will failures be measured and handled?** Observe latency, backlog, busy workers, delayed jobs, errors, timeouts, and shutdown behavior.

An easy rule to remember is:

> **Synchronous/asynchronous** describes when the caller continues. **Concurrency/parallelism** describes how much work can progress at the same time. **Scheduling** describes when work starts. **Blocking/non-blocking** describes how a thread waits for resources. These choices can be combined, but they do not replace one another.

## 10. Self-Check

**Question 1.** An `@Async` method returns a `CompletableFuture`, but the caller calls `join()` immediately. Is the caller waiting?

**Answer:** Yes. The work is submitted asynchronously, but the caller then actively waits synchronously at `join()`.

**Question 2.** Does `@Scheduled(fixedRate = 1_000)` definitely create a new thread every second and run executions in parallel?

**Answer:** No. The configuration defines the target trigger timing; threads and overlap depend on the scheduler, pool, and how the job executes.

**Question 3.** Is `parallelStream().toList()` an asynchronous call with respect to the code that follows it?

**Answer:** Not by default. Processing pieces may run in parallel internally, but the terminal call returns the result after completing the required parts.

**Question 4.** If a Spring MVC controller returns `CompletableFuture<String>`, does the browser receive the content immediately?

**Answer:** No. The server can process the request asynchronously, but the HTTP response carrying the result only completes when the Future completes. If you want the client not to wait for a long job, design separate endpoints to submit the job and query the result.

**Question 5.** Three instances all run `@Scheduled(cron = "...")`. Is it guaranteed that only one instance does the work?

**Answer:** No. A coordination mechanism is needed to guarantee single execution across the cluster.

## References

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Reference — Asynchronous Requests in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Java SE — `CompletableFuture`, `ExecutorService`, `ScheduledExecutorService` in package `java.util.concurrent`.
