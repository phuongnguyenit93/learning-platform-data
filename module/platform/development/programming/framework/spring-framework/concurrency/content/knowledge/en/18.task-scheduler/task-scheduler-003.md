# scheduleAtFixedRate() and Fixed-Period Schedules in Spring TaskScheduler

A Spring system often needs to run recurring tasks: scanning overdue orders every 10 seconds, refreshing a cache every minute, polling a queue periodically, or recording health metrics for a service. With the `org.springframework.scheduling.TaskScheduler` API, the **`scheduleAtFixedRate()`** method lets you schedule a `Runnable` to repeat at a **fixed rate**.

The key point: **fixed rate anchors planned execution marks to the start time and period length, rather than waiting for the previous run to finish before counting the next interval**. However, “scheduled every 5 seconds” **does not mean guaranteed execution every 5 seconds**, carries no real-time guarantee, does not automatically ensure job success, and does not automatically create transactions or guarantee single cluster-wide execution.

This lesson belongs to the **TaskScheduler** group of the **Spring Framework – concurrency** module. The goal is to use the API properly, understand the execution model, handle long-running tasks, choose between fixed rate, fixed delay, and cron, manage `ScheduledFuture`, and apply it safely in Spring Boot.

## 1. What Is TaskScheduler and How Does It Differ from TaskExecutor?

`TaskExecutor` focuses on **submitting work for execution**; `TaskScheduler` focuses on **deciding when work is executed**, including running once at a scheduled time or repeating according to a policy.

```text
TaskExecutor
  caller --execute(task)--> worker/queue --> runs one task

TaskScheduler
  caller --scheduleAtFixedRate(task, period)-->
       scheduler keeps the schedule in memory
       |   |   |   |   |
       v   v   v   v   v
     run run run run run ... until cancelled/shut down
```

In Spring, `ThreadPoolTaskScheduler` is a common implementation of `TaskScheduler`. It uses the JDK's `ScheduledExecutorService` underneath and adds bean/lifecycle management and integration with Spring triggers. The thread executing the periodic `Runnable` **is usually the scheduler worker itself**, rather than automatically handing off to a separate `ThreadPoolTaskExecutor`.

Therefore:

- If tasks are very short, a small scheduler pool may suffice.
- If a task blocks on I/O for a long time or performs heavy CPU work, a scheduler worker will be occupied; other schedules may be delayed.
- If a task only submits work to another executor, the time the scheduler task “finishes” is the **submission time**, not necessarily when business work on the other executor finishes.
- `TaskScheduler` is not a durable job queue or distributed coordinator; each application/replica can have its own schedule.

### Main Methods in Spring Framework 6.x

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
```

This is an **API signature excerpt for learning**, not a standalone Java program. In Spring 6.x, prefer `Instant` and `Duration`; overloads using `Date`/`long` exist for compatibility and many have been deprecated since Spring 6.0.

Source: Official `TaskScheduler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/TaskScheduler.html

## 2. What Does “Fixed Rate” Mean Exactly?

With period `P` and start mark `T0`, the **planned eligible execution times** follow the form:

```text
T0, T0 + P, T0 + 2P, T0 + 3P, ...
```

For example, starting near 10:00:00, `period = 5 seconds`:

```text
Time            00     05     10     15     20     25  (seconds)
Planned marks   |------|------|------|------|------|
Short execution [job]  [job]  [job]  [job]  [job]
```

If each run takes around 1 second and the scheduler has sufficient resources, runs will generally start near the 0, 5, 10, and 15 second marks. **“Near”** is important: scheduler threads are subject to GC pauses, CPU scheduling, contention, container quotas, and other tasks.

**Fixed rate defines how schedule marks are calculated, not a millisecond-exact guarantee.**

### 2.1. When a Task Runs Longer Than the Period

Suppose the period is 5 seconds, but one run takes 8 seconds:

```text
Planned marks: 0s      5s      10s     15s     20s
              |-------|-------|-------|-------|
Actual:       [Run 1 ---------]
                               [Run 2 ----------]
                                                [Run 3 ...]
```

The next mark arrives while the previous run has not finished. With `ThreadPoolTaskScheduler` backed by `ScheduledThreadPoolExecutor`, **successive runs of the same periodic task do not overlap**: the next run **starts late** and may be dispatched shortly after the previous one completes to catch up. This **does not mean** the scheduler spawns a parallel duplicate of the task just because the pool has multiple threads.

There are several limits to keep in mind:

- The scheduler does not turn “lost time” into a durable transaction list; shutdowns/crashes can drop runs.
- There is no guarantee that under heavy load the system will complete the exact count derived from an ideal timing formula.
- If multiple **different periodic tasks** share the same pool, they can run in parallel when `poolSize > 1`.
- If a run **only submits work to another pool and returns**, the actual dispatched jobs **can overlap**, even though invocations of the periodic Runnable itself do not overlap.
- If there are multiple application replicas, each replica can run **its own schedule**, creating cross-machine concurrency.

### 2.2. When a Task Is Shorter Than the Period

If a task runs for 1 second with a 5-second period:

```text
0s         5s         10s        15s
[job]      [job]      [job]      [job]
|--1s      |--1s      |--1s      |--1s
```

The idle gap between run 1 finishing and run 2 starting is approximately **4 seconds**. That is the defining behavior separating fixed rate from fixed delay.

### 2.3. Do Not Treat Fixed Rate as an “Exact” Timer

A process undergoing stop-the-world GC, CPU throttling, or machine suspension can suffer significant schedule lag. JDK periodic scheduling provides no real-time guarantees; if a task bills customers, closes books, or triggers strictly by business calendar marks, design **around business timestamps and data**, rather than inferring results from how many times a callback was invoked.

## 3. Two `scheduleAtFixedRate()` Overloads to Use

### 3.1. Starting as Soon as Possible

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        Duration.ofSeconds(5));
```

This is a **fragment**, assuming `scheduler` is a `TaskScheduler` bean and `refreshCache` is a no-arg `void refreshCache()` method. It creates a schedule with a **5-second period**, with the first run registered to start **as soon as possible**, rather than waiting 5 seconds before the first run.

If you want a **5-second delay before the first run**, use the overload taking `Instant startTime`:

```java
Instant firstRun = Instant.now().plusSeconds(5);

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        firstRun,
        Duration.ofSeconds(5));
```

Remember to import `java.time.Instant`, `java.time.Duration`, and `java.util.concurrent.ScheduledFuture`. `Instant` is an absolute timestamp for the **first run**, while `Duration` is the fixed-rate interval for subsequent runs.

### 3.2. Scheduling From a Specific Start Time

```java
Instant startsAt = Instant.parse("2030-01-01T00:00:00Z");

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::reconcile,
        startsAt,
        Duration.ofMinutes(10));
```

This is an illustrative fragment with a specific UTC timestamp. Running every 10 minutes from a start mark **is not the same** as “running at minutes 00, 10, 20, ... of every hour in the company's timezone” if the start mark or offset does not align. If you need schedules based on **dates, days of week, months, holidays, or local time**, consider `CronTrigger` or a scheduler designed for business calendars.

### 3.3. Valid Period

The period must be a **positive Duration**. Do not pass `Duration.ZERO` or a negative value to mean “run as fast as possible”: under `ScheduledExecutorService.scheduleAtFixedRate`, a non-positive period is invalid. If you want continuous processing at resource capacity, use a consumer/worker loop with backpressure instead of turning the scheduler into a busy spin.

### 3.4. What Is `ScheduledFuture` Used For?

`scheduleAtFixedRate` returns `ScheduledFuture<?>`:

- `cancel(false)`: cancels **subsequent periodic runs**, without requesting to interrupt an in-flight run.
- `cancel(true)`: may send an interrupt to the in-flight run depending on implementation; stopping is best-effort.
- `isCancelled()`: checks the Future's cancellation state.
- `isDone()`: for an actively running periodic schedule, usually remains false; becomes true if cancelled or terminated abnormally.
- `get()`: **do not use to “wait for one tick to complete”**. For a JDK periodic future, `get()` does not return normally while the schedule remains active; it waits until the schedule is cancelled or terminates abnormally and may then throw an exception. To observe individual runs, use metrics, job status, or a separate future per tick.

If you do not retain the `ScheduledFuture` and have no reference to the scheduler, it can be hard to cancel a specific job when configuration changes. For a bean lifecycle, store the handle in a safe field and cancel it on stop.

## 4. How Do Fixed Rate, Fixed Delay, Cron, and `@Scheduled` Differ?

| Model | Next Execution Mark | Suitable For |
| --- | --- | --- |
| `scheduleAtFixedRate(task, period)` | At `start + n × period`; may lag when tasks run long | Cadence-based polling, cache refresh, metric collection |
| `scheduleWithFixedDelay(task, delay)` | **After the previous run finishes + delay** | Avoiding back-to-back bunching, tasks needing rest between runs |
| `schedule(task, Instant)` | Once at or after the specified timestamp | One-time future execution |
| `schedule(task, CronTrigger)` | Based on cron/trigger rules | Running at 08:00 on workdays, hourly/daily schedules |
| `@Scheduled(fixedRate = ...)` | Spring registers a fixed-rate schedule for the annotated method | Fixed schedule known from configuration |
| `@Scheduled(fixedDelay = ...)` | Spring registers a fixed-delay schedule | Wait for completion then pause |
| `@Scheduled(cron = ...)` | Spring uses a cron trigger | Calendar-based schedules |

### Numerical Comparison Example

Suppose a task takes **3 seconds**, and the configured period or delay is **5 seconds**, starting at mark 0.

**Fixed rate:**

```text
Run 1: start 0s, end 3s
Run 2: start near 5s, end near 8s
Run 3: start near 10s, end near 13s
```

**Fixed delay:**

```text
Run 1: start 0s, end 3s
Run 2: start near 8s  (3 + 5), end near 11s
Run 3: start near 16s (11 + 5), end near 19s
```

These timings are an **illustrative model without resource contention**, not exact logs from a real JVM.

### Practical Choice

- **Fixed rate:** you want the system to try checking/measuring/syncing on an even cadence, provided occasional lag is acceptable and overload is handled.
- **Fixed delay:** you want to guarantee a pause after each completed run, avoiding piling onto a slow downstream system.
- **Cron:** you want to follow a business wall clock, such as 02:00 daily or Mondays, with explicit timezone/DST rules.

Do not just switch `fixedRate` to `fixedDelay` to cure every bug: if your logic duplicates work across replicas, overlaps via async delegation, or lacks idempotency, changing the cadence **does not fix those root causes**.

## 5. `@Scheduled` Is Declarative, `TaskScheduler` Is the Programmatic Scheduling API

In Spring, two organizational styles are common.

**Declarative style:**

```java
@Configuration
@EnableScheduling
class SchedulingConfig {}

@Component
class CacheRefreshJob {
    @Scheduled(fixedRate = 5, timeUnit = TimeUnit.SECONDS)
    public void refresh() {
        // One processing run.
    }
}
```

This is a **fragment**; it requires imports for `@Configuration`, `@EnableScheduling`, `@Component`, `@Scheduled`, and `TimeUnit`. With this declarative schedule, Spring detects the method and registers scheduling based on metadata. For standard synchronous methods, the return type should be `void` with no parameters.

**Programmatic scheduling via bean:**

```java
ScheduledFuture<?> handle = taskScheduler.scheduleAtFixedRate(
        () -> refreshCache(),
        Duration.ofSeconds(5));
```

This is a fragment: your code controls **when registration begins**, how long the period is, and retains a handle for targeted cancellation. Useful when configuration comes from a DB/feature flag or needs dynamic start/stop.

### 5.1. Is `@EnableScheduling` Needed to Call `scheduleAtFixedRate` Directly?

**Not required.** If the application already has a valid `TaskScheduler` bean and your code calls `scheduleAtFixedRate(...)` directly, registration happens through the API; the `@Scheduled` annotation processor is not needed for that.

`@EnableScheduling` is needed when you want Spring to **detect and register `@Scheduled` methods** automatically. Do not enable both approaches for **the same job** unintentionally, as it is easy to create two independent schedules and double-run.

### 5.2. Understanding `initialDelay` on `@Scheduled`

```java
@Scheduled(
        initialDelay = 2,
        fixedRate = 5,
        timeUnit = TimeUnit.SECONDS)
public void tick() {
    // First run after ~2 seconds, then a 5-second cadence.
}
```

This is a fragment, supported in Spring versions that provide the `timeUnit` attribute. It is **conceptually** equivalent to specifying an `Instant` for the first run, but does not give you the same direct control over holding a `ScheduledFuture` inside the annotated method.

`@Scheduled` also supports string/placeholder configuration attributes (depending on version) and cron; choose based on deployment needs, timezone, and whether runtime schedule updates are required.

## 6. `ThreadPoolTaskScheduler` and How Workers Are Used

`ThreadPoolTaskScheduler` manages an underlying `ScheduledExecutorService`. For this implementation, it is essential to understand how it differs from `ThreadPoolTaskExecutor`:

| Attribute | ThreadPoolTaskScheduler | ThreadPoolTaskExecutor |
| --- | --- | --- |
| Purpose | Time/trigger-based scheduling | Submitting work for execution |
| Key parameters | `poolSize`, error handler, shutdown, scheduler policies | `corePoolSize`, `maxPoolSize`, `queueCapacity` |
| Where does work run? | Usually on scheduler workers per schedule | Task executor workers |
| If a task holds a worker too long | Other schedules may be delayed | Queue/other tasks may wait or be rejected |
| Future of a periodic job | Represents the **series of runs**, cancels the schedule | Future usually represents **a single task** |
| Responsible for persistence? | No | No |

### 6.1. What Does Pool Size Mean?

```java
@Bean("billingScheduler")
ThreadPoolTaskScheduler billingScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("billing-schedule-");
    return scheduler;
}
```

This is a fragment for a Spring configuration class. Pool size 2 means the scheduler can run triggered jobs **concurrently on two workers**. However, it **does not** mean a *single fixed-rate registration* will overlap two executions of itself if a run lags. One scheduler pool typically serves multiple distinct schedules, such as invoice scanning and cache refreshing.

`ThreadPoolTaskScheduler` uses a scheduled executor backed by a delay queue; do not equate it with the bounded `queueCapacity` of `ThreadPoolTaskExecutor`. Creating tens of thousands of long-lived schedules can consume memory and become hard to manage, even if quiet schedules do not saturate CPU.

### 6.2. `ThreadPoolTaskScheduler` Runs Work on Scheduler Threads

If a fixed-rate `Runnable` makes a blocking HTTP client call for 10 seconds, it can tie up a scheduler worker for the full 10 seconds. When the pool is small, other schedules have to wait.

You can separate scheduling from processing:

```java
scheduler.scheduleAtFixedRate(
        () -> workExecutor.execute(this::processBatch),
        Duration.ofSeconds(5));
```

In this case, however, **a “tick” only submits work**. Batches inside `workExecutor` can overlap even though the scheduler wrapper runs very quickly. Define clear overlap limits and backpressure:

- Reject submission if the previous batch has not finished, or use a state machine/lease.
- Bound the worker executor's queue and thread count.
- If you must guarantee no jobs are dropped, persist requests to a durable database/broker.
- Do not treat `execute` returning without exception as business completion.
- Do not assume every task runs strictly on cadence if the worker pool is already full.

### 6.3. No Real-Time Guarantee and No Automatic Cluster Leader

Each Spring instance runs its own scheduler bean. Scaling from 1 to 3 replicas with `@Scheduled(fixedRate=5000)` or identical programmatic registration on each replica usually results in **three schedules**; the task may run three times at closely spaced moments.

To have only one instance perform the work cluster-wide, you need leader election, a distributed lock/lease, a coordinator/job store, or an appropriate scheduler platform. You must account for races between replicas, leases expiring before a worker finishes, and idempotency on retries.

## 7. Runnable Java 17: Fixed-Rate Does Not Overlap a Single Periodic Task

To prove this without relying on timing luck, the demo uses a `ScheduledThreadPoolExecutor` with **two workers**, yet only **one recurring schedule**. The third task intentionally waits on a latch, the main thread cancels subsequent repetitions and then releases the latch. We measure the run count and maximum concurrency.

Save as **FixedRateDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedRateDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(2);
        pool.setRemoveOnCancelPolicy(true);

        AtomicInteger runs = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch releaseThird = new CountDownLatch(1);

        try {
            ScheduledFuture<?> schedule = pool.scheduleAtFixedRate(() -> {
                int concurrentlyRunning = active.incrementAndGet();
                maxActive.updateAndGet(
                        previous -> Math.max(previous, concurrentlyRunning));

                try {
                    int number = runs.incrementAndGet();
                    if (number == 3) {
                        thirdStarted.countDown();
                        try {
                            releaseThird.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                        }
                    }
                } finally {
                    active.decrementAndGet();
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            thirdStarted.await();           // Run 3 has entered Runnable
            boolean cancelled = schedule.cancel(false);
            releaseThird.countDown();       // Allow run 3 to finish
            pool.shutdown();

            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not stop");
            }

            System.out.println("runs=" + runs.get());
            System.out.println("maxConcurrent=" + maxActive.get());
            System.out.println("cancelled=" + cancelled);
        } finally {
            releaseThird.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run on Java 17+:

```bash
javac FixedRateDemo.java
java FixedRateDemo
```

**Stdout under normal demo conditions:**

```text
runs=3
maxConcurrent=1
cancelled=true
```

### Why Is This Example Reliable?

1. `scheduleAtFixedRate` creates **one periodic schedule** with 0 initial delay and a 20 ms period. It does not require the callback to finish in exactly 20 ms; that is only the *planned schedule*.
2. `thirdStarted.await()` waits until the third run has actually entered execution; it does not guess using `Thread.sleep`.
3. While the third run is blocked on `releaseThird.await()`, `main` calls `schedule.cancel(false)`. At that moment the schedule has not terminated, so cancellation takes effect for subsequent runs.
4. `cancel(false)` does not interrupt the third run; once the latch opens, the third run completes normally.
5. `pool.shutdown()` and `awaitTermination` ensure workers finish before `main` prints the results. `runs` is exactly 3 because subsequent runs were cancelled.
6. Two available threads do not cause **the same periodic task** to run multiple executions concurrently; `maxConcurrent=1` confirms there was no overlap in the demo.
7. `finally` always releases the latch and shuts down the pool to prevent hanging the process if an earlier step fails.

**Conclusion boundary:** this demo proves the behavior of **`ScheduledThreadPoolExecutor` in Java 17** for a single fixed-rate registration. It does not mean every scheduler/job queue design outside the JDK forbids overlap, especially when the Runnable delegates to another executor or the app runs multiple replicas. Furthermore, **thread names and actual timestamps are not part of the scheduler's contract**.

## 8. Does an Error in One Run Stop the Entire Schedule?

This is a subtle difference between raw JDK periodic scheduling and Spring configuration:

### 8.1. Raw JDK `ScheduledThreadPoolExecutor`

The `ScheduledExecutorService.scheduleAtFixedRate` Javadoc specifies that if any execution throws an unhandled exception, **subsequent executions are suppressed**. The periodic `ScheduledFuture` completes abnormally; calling `get()` may throw `ExecutionException` wrapping the root cause.

```java
ScheduledFuture<?> future = pool.scheduleAtFixedRate(() -> {
    throw new IllegalStateException("tick failed");
}, 0, 1, TimeUnit.SECONDS);
```

This is a fragment; `pool` must be a scheduled executor. Once the task throws an uncaught exception, the JDK periodic sequence stops.

### 8.2. Spring `ThreadPoolTaskScheduler` Has an `ErrorHandler`

Spring provides an error-handling wrapper for periodic tasks. With `ThreadPoolTaskScheduler`, **the default handler for repeating tasks typically logs and suppresses the error** so a single failure does not prevent future runs. Conversely, if you configure a custom handler that **rethrows the exception**, the schedule can terminate just like raw JDK behavior.

Configuration example:

```java
scheduler.setErrorHandler(error ->
        log.error("Recurring task failed", error));
```

This is a fragment, assuming `scheduler` and `log` exist; the lambda only logs the error and returns, so it does not propagate. **Do not look solely at the name `scheduleAtFixedRate` and assert that an exception always stops the schedule** across all implementations.

However, continuing to schedule does not mean a business error was fixed. If a job fails 10,000 times, repeatedly logging errors and continuing to run can worsen system health. Track failed attempts, apply backoff/circuit breakers where appropriate, and decide whether to transition to a PAUSED/FAILED state per business rules.

Reference Spring `TaskUtils` and error handling for recurring tasks:
https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/support/TaskUtils.html

### 8.3. Difference Between Logging Errors and Handling Errors

An error handler that only logs does not automatically provide:

- Retries with backoff;
- A guarantee of sending an email once;
- Rolling back already-committed operations;
- Saving the job to a durable queue;
- Operational alerts when errors cross a threshold.

Use dedicated job status, `success/failure` metrics, and alerts. A schedule that keeps ticking only proves **the scheduler is still alive**, not that previous business runs succeeded.

## 9. Complete Spring Boot 3.x: Registering and Cancelling Fixed-Rate at Runtime

The following example uses **Java 17+, Spring Boot 3.x / Spring Framework 6.x**, and the `spring-boot-starter-web` dependency. It creates a Spring-managed `ThreadPoolTaskScheduler` bean, registers a fixed-rate job **when the application is ready**, and retains the `ScheduledFuture` to cancel on context close. An endpoint reads how many runs have started.

**Keep in mind before running:** the job only increments a counter and logs; **it performs no real business operation**. There is no guarantee of millisecond-exact log timestamps or durable job state across restarts.

Place the full contents into **src/main/java/com/example/demo/PeriodicApplication.java**:

```java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PeriodicApplication {
    private static final Logger log =
            LoggerFactory.getLogger(PeriodicApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(PeriodicApplication.class, args);
    }

    @Bean("periodicScheduler")
    ThreadPoolTaskScheduler periodicScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("periodic-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setErrorHandler(error ->
                log.error("Periodic task failed", error));
        return scheduler; // Spring manages bean initialize/shutdown.
    }
}

@Service
class PeriodicJob {
    private static final Logger log =
            LoggerFactory.getLogger(PeriodicJob.class);

    private final TaskScheduler scheduler;
    private final AtomicInteger attempts = new AtomicInteger();
    private volatile ScheduledFuture<?> schedule;

    PeriodicJob(
            @Qualifier("periodicScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void start() {
        if (schedule != null) {
            return; // Avoid duplicate registration in the same bean.
        }
        schedule = scheduler.scheduleAtFixedRate(
                this::runOneTick, Duration.ofSeconds(5));
        log.info("Periodic job registered, period=5s");
    }

    private void runOneTick() {
        int attempt = attempts.incrementAndGet();
        log.info("Tick {} on {}", attempt,
                Thread.currentThread().getName());

        // Only to illustrate the handler; tick 3 intentionally fails.
        if (attempt == 3) {
            throw new IllegalStateException("Simulated tick failure");
        }
    }

    public int attempts() {
        return attempts.get();
    }

    public boolean isScheduled() {
        ScheduledFuture<?> current = schedule;
        return current != null
                && !current.isCancelled()
                && !current.isDone();
    }

    @PreDestroy
    public void stop() {
        ScheduledFuture<?> current = schedule;
        if (current != null) {
            current.cancel(false); // Do not interrupt an in-flight tick.
        }
        log.info("Periodic job cancellation requested");
    }
}

record PeriodicStatus(int attempts, boolean scheduled) {}

@RestController
class PeriodicController {
    private final PeriodicJob job;

    PeriodicController(PeriodicJob job) {
        this.job = job;
    }

    @GetMapping("/schedule/status")
    public PeriodicStatus status() {
        return new PeriodicStatus(job.attempts(), job.isScheduled());
    }
}
```

In a project with the Spring Boot Gradle plugin and wrapper, run:

```bash
./gradlew bootRun
curl -s http://localhost:8080/schedule/status
```

On Windows, use `gradlew.bat bootRun`. Once the context emits `ApplicationReadyEvent` and the schedule is registered, an example response is:

```json
{"attempts":2,"scheduled":true}
```

**This is an illustrative response, not a fixed output**: the tick count depends on when you call the endpoint, execution timing, application shutdown, and environment conditions. On the third tick, the method intentionally throws `IllegalStateException`. Because the `ThreadPoolTaskScheduler` handler in the example **logs the error and returns**, the schedule can continue running subsequent ticks. The endpoint measures **started attempts**, not successes; this intentionally highlights the difference between “the schedule ran” and “business logic succeeded”.

### 9.1. Lifecycle Analysis

1. Spring creates `periodicScheduler` as a **named bean**, configuring its pool and handler.
2. `PeriodicJob` injects `TaskScheduler` via `@Qualifier` so it does not depend on default bean selection.
3. `@EventListener(ApplicationReadyEvent.class)` registers the schedule once the application reaches the ready phase; do not start tasks in the constructor.
4. `scheduleAtFixedRate(this::runOneTick, Duration.ofSeconds(5))` registers **one** periodic task, first run as soon as possible.
5. `ScheduledFuture<?> schedule` is retained to check whether the schedule exists and cancel it on stop.
6. `@PreDestroy` calls `cancel(false)` to prevent future runs. For an in-flight run, `false` does not issue an interrupt.
7. Spring still manages shutting down the scheduler bean; explicit cancellation in the service clarifies schedule ownership boundaries.

**There is no `@EnableScheduling` in this example** because the code **calls the TaskScheduler API directly**, with no `@Scheduled` methods. If you switch to annotations, enable the scheduling annotation infrastructure accordingly.

### 9.2. Why Not Use a Boolean to Tell If a Job Completed?

`isScheduled()` in the example tells you **the periodic future is still active**, not that any tick succeeded. If the task loses DB connectivity 100 times, the schedule may remain active while every business operation fails.

A real system should track:

- When the latest run started/finished;
- Separate success and failure counts;
- Run duration, lag relative to schedule, and skipped runs;
- Downstream health and retry limits;
- A job ID / attempt ID per run if traceability is needed;
- Alerts if too much time passes without a successful run.

### 9.3. Can `@Scheduled` Replace This API?

Yes. If the schedule is fixed in configuration and you do not need to dynamically cancel individual handles, for example:

```java
@Configuration
@EnableScheduling
class EnableJobs {}

@Component
class ReconciliationTick {
    @Scheduled(fixedRate = 5000, initialDelay = 2000)
    public void reconcile() {
        // Job runs at the interval scheduled by Spring.
    }
}
```

This is an **alternative configuration**; do not add it to the same application if the same business task is already registered manually and you want to avoid double scheduling. In Spring, `@Scheduled` cannot by itself make a job **run on only one replica**. If you need Cron, use `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` intentionally accounting for calendar rules and regional DST where needed.

## 10. Fixed-Rate and Overlapping Execution: Where Exactly Is It Safe?

You often hear “fixed rate spawns a new thread whenever the clock hits the mark”. That is **incorrect** for a periodic registration backed by `ScheduledThreadPoolExecutor`.

### 10.1. One Recurring Task Directly on `ThreadPoolTaskScheduler`

```text
scheduleAtFixedRate(task, 5s)
       |
       +-- Runnable run 1 (runs long, 8s)
       +-- Runnable run 2 (starts late after run 1)
       +-- Runnable run 3 (starts when eligible after run 2)
```

Successive executions of **this same periodic task** do not overlap, per `ScheduledThreadPoolExecutor`. A pool size of 4 does not turn one recurring handle into four parallel copies.

### 10.2. Runnable Only Delegates to `@Async` or Another Pool

```java
scheduler.scheduleAtFixedRate(
        () -> reportService.startReportAsync(),
        Duration.ofSeconds(5));
```

This is a fragment; `reportService` must be **another Spring bean** injected and configured with `@Async` appropriately. The scheduler run can return right after submitting. If the report takes 20 seconds, after 5 seconds the scheduler **can still submit another report**. Thus two report operations **can run concurrently**.

To genuinely prevent overlap:

- Do not submit a new run while the previous job is still active, using an appropriate `AtomicBoolean`/state/lease.
- Or run a synchronous task on the scheduler with an appropriate duration and accept delayed runs.
- Or use an independent job store/queue, idempotency, and per-workload concurrency limits.

### 10.3. Multiple Schedules or Multiple Replicas

If registered twice:

```java
scheduler.scheduleAtFixedRate(task, Duration.ofSeconds(5));
scheduler.scheduleAtFixedRate(task, Duration.ofSeconds(5));
```

These are **two independent periodic registrations** even though they share the same `Runnable` object. They can overlap if the scheduler has multiple workers. If a method both uses `@Scheduled` and is also registered manually, side effects can repeat.

If three replicas run, each replica can have its own schedule and touch the DB concurrently. To have only one instance perform the work cluster-wide, distributed coordination **outside** TaskScheduler is required.

**Rule:** the claim “non-overlap” is only meaningful when you specify **one handle, one executor implementation, scoped to one process**.

## 11. Load Pressure, Schedule Lag, and Backpressure Options

Suppose an invoice-scanning task runs for about 12 seconds while fixed rate is set to 2 seconds. One scheduler worker stays occupied nearly continuously because subsequent runs are always overdue. Without controlling how much work gets done, the system can suffer sustained overload or hammer downstream services.

### 11.1. Separating Three Kinds of Latency

| Metric | Meaning |
| --- | --- |
| Scheduled time | The mark when the task was planned to be eligible to run |
| Actual start | When the worker actually began executing |
| Completion time | When that run finished |
| Start lag | Actual start minus scheduled time |
| Run duration | Completion minus actual start |
| End-to-end job latency | Time from trigger until business output is usable |

If you only log `"tick"` without measuring duration/start lag, it is hard to diagnose why a 5-second schedule updates business data 1 minute late.

### 11.2. Ways to Reduce Bottlenecks

- **Keep ticks short:** only select eligible work and hand it to a capacity-controlled pipeline.
- **Bounded batches:** process small groups using state/offsets so one run does not hold a worker for tens of minutes.
- **Backpressure:** use a semaphore/bulkhead, limiting concurrent tasks and queue size.
- **Intentional skipping:** if the previous run is still busy and business rules allow, record a `skipped_due_to_busy` metric without adding more work.
- **Adjust cadence:** a poller waiting on downstream systems may fit fixed delay better.
- **Dependency timeouts:** configure proper HTTP/JDBC timeouts; `scheduleAtFixedRate` does not automatically abort a hung task.
- **Idempotency:** each scan uses a work key to avoid duplicate side effects across restarts/replicas/retries.

### 11.3. Do Not Increase `poolSize` Without Bounds

More scheduler workers keep **independent schedules** from blocking one another, but do not make an old task faster or solve database/API overload. Scaling must be grounded in CPU measurements, latency, downstream concurrency, and processing capacity.

## 12. What Do Cancelling a Schedule and Shutdown Mean?

`ScheduledFuture.cancel(boolean)` cancels the recurring schedule series when accepted. Two cases:

**`cancel(false)`:** does not request interrupting the currently running execution, while preventing subsequent runs per the Future contract.

**`cancel(true)`:** may request interrupting the runner of the current execution in supporting implementations. An interrupt is a **cooperative** signal; if the task is blocked in an uninterruptible API or side effects were already sent externally, immediate stopping or rollback cannot be guaranteed.

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::poll,
        Duration.ofSeconds(5));

// When configuration no longer needs the schedule:
boolean cancellationAccepted = handle.cancel(false);
```

This is a fragment, requiring `scheduler`, `poll`, and imports.

**Do not use `Future.get()`** to wait for “the first run to finish”. On a periodic future, it represents **the entire series**, and may wait indefinitely while the schedule stays active. To know when a single run completes, the task must publish results/metrics or return a separate `CompletableFuture` for that run.

### 12.1. Shutting Down the Scheduler Bean

When the Spring context closes, `ThreadPoolTaskScheduler` performs lifecycle cleanup. Options like waiting for current tasks to finish and whether periodic tasks continue during shutdown depend on implementation configuration. Typically a schedule stops accepting new runs after shutdown; however, never assume shutting down the JVM persists schedules for recovery after restart.

For applications with critical jobs, design shutdown deliberately:

1. Stop accepting/registering new schedules.
2. Cancel handles or mark stop-requested per business rules.
3. Let in-flight runs finish within a reasonable grace period, or send controlled interrupts.
4. Persist progress/job offsets to durable storage.
5. Ensure restart can resume remaining work without relying on ticks lost in RAM.

### 12.2. Remove-on-Cancel Policy

`ScheduledThreadPoolExecutor` by default retains cancelled delayed tasks in its queue until their delay elapses; this can keep references alive for a long time when an application creates and cancels many schedules.

`ThreadPoolTaskScheduler#setRemoveOnCancelPolicy(true)` instructs the underlying implementation to try removing cancelled tasks sooner when possible. It reduces retention in workloads with frequent registration/cancellation, but does not replace **handle management, lifecycle control, and resource monitoring**.

## 13. Periodic Scheduling Does Not Equal Exact Business Calendar Scheduling

### 13.1. Fixed Rate Is a Duration, Not “Every Day at 02:00”

`Duration.ofHours(24)` is a 24-hour span. It is **not** equivalent to “02:00 local time every day”, because timezones and DST transitions can produce 23-hour or 25-hour days in some regions.

If the requirement is “02:00 daily in a timezone”, use cron/trigger with an explicit timezone and define rules for nonexistent or duplicate hours. Do not blindly use fixed rate for schedules that must account for holidays or business calendars.

### 13.2. Do Not Use Tick Count as the Source of Truth

Suppose a scheduler runs every 10 seconds and a machine goes down for 5 minutes. When it restarts, new ticks do not automatically represent all business events from those 5 disconnected minutes.

Instead, each run should **query data by condition**:

```sql
-- Illustrative query only, not a complete schema.
SELECT id
FROM pending_jobs
WHERE next_attempt_at <= CURRENT_TIMESTAMP
  AND status = 'PENDING'
ORDER BY next_attempt_at
LIMIT 100;
```

Processing workers use locks/leases or appropriate conditional updates so multiple replicas do not grab the same job. **The database/job store is the source of truth**, while the fixed-rate tick is merely the wakeup mechanism for the poller.

### 13.3. Idempotency and Multiple Instances

For an invoice-scanning task, if two replicas both detect an unprocessed invoice, both can send requests to the provider. `scheduleAtFixedRate` has no distributed lock. You need optimistic locking, unique constraints, claim/lease, or a reliable job store plus idempotency keys for side effects. Do not treat “only one tick” in a single instance's logs as proof that the whole cluster executed once.

## 14. Observability, Errors, and Execution Context

In production, monitor:

- **Registration count:** how many schedules are registered, and whether duplicates exist;
- **Actual tick count:** how many times the callback started;
- **Success/failure count:** how many runs achieved business success or failed;
- **Duration and start lag:** whether processing runs slower than the period;
- **Skipped ticks/batches:** runs intentionally skipped because the previous job was still busy;
- **Active workers and pool size:** whether other schedules are stalled;
- **Shutdown/cancel:** when schedules are cancelled and whether runs remain in flight;
- **Retries/duplicate processing:** especially across multiple replicas.

### 14.1. Logging Correlation IDs for Scheduled Jobs

A scheduled task usually **has no HTTP request** and should not expect MDC from a servlet thread to carry over automatically. You can generate a `jobRunId` per run, put it in MDC for the scope, and clean it up:

```java
String runId = UUID.randomUUID().toString();
String previous = MDC.get("jobRunId");
try {
    MDC.put("jobRunId", runId);
    log.info("Starting periodic reconciliation");
    reconcile();
} finally {
    if (previous == null) MDC.remove("jobRunId");
    else MDC.put("jobRunId", previous);
}
```

This is a fragment, requiring SLF4J `MDC`, `Logger`, `UUID` imports, and a `reconcile` implementation. Because scheduler workers are reused, missing `finally` can leak the wrong ID into a later run.

If the job is durable, you can keep a stable `jobId` for the logical job and an `attemptId`/`runId` for each execution; do not use a request ID as an idempotency key in place of a job ID.

### 14.2. With `@Async` or `CompletableFuture` Inside a Tick

`@Async` moves execution to another executor through a Spring proxy; `CompletableFuture.supplyAsync` without an explicit executor may use the common pool. MDC, transactions, and security context **do not automatically propagate** across every thread. If needed, use a context-aware executor/`TaskDecorator` or pass metadata explicitly as data.

**The scheduler task returning is not proof that work on an async executor has finished.** This affects both overlap limits and how success is counted.

## 15. Testing `scheduleAtFixedRate` Properly

Timing tests are notoriously flaky. Do not write tests that “sleep 100 ms and assert exactly three runs”; GC and the OS scheduler can introduce large skew.

### 15.1. Tests You Should Have

1. **Registration:** the task is registered once, with the configured period and startTime.
2. **Activation:** at least one tick occurs while the scheduler runs; use `CountDownLatch`/conditions with an overall timeout instead of waiting forever.
3. **Cancellation:** after cancellation, no new runs are scheduled, while an in-flight run with `cancel(false)` can finish.
4. **Non-overlap:** for a single recurring task on `ScheduledThreadPoolExecutor`, verify maximum concurrency is 1 under the test model.
5. **Exception:** verify whether a failing run stops the schedule or is suppressed by the configured handler.
6. **Heavy task:** a tick taking longer than the period increases start lag without creating two overlapping runs of the same handle.
7. **Multiple schedules:** independent jobs can run in parallel according to pool size; a job is not accidentally registered twice.
8. **Shutdown:** when context closes, the scheduler bean cancels tasks and threads are cleaned up.
9. **Cluster idempotency:** if multiple replicas tick together, side effects are not duplicated when claiming one logical job.
10. **Observability:** separate success/failure run metrics and a run ID are emitted.

### 15.2. Do Not Assert Timestamps as Exact Numbers

A test might record:

```java
long startedAtNanos = System.nanoTime();
// Inside callback: measure lag, do not assert start is exactly 5000 ms.
```

This is a fragment. Use `System.nanoTime()` to measure **elapsed intervals**; do not use it as wall-clock time for business schedules. When comparing actual time to target, allow reasonable jitter and do not demand precision the Java scheduler does not promise.

### 15.3. Test Business Logic Separately From the Scheduler

Instead of packing logic into a lambda that cannot be invoked directly:

```java
scheduler.scheduleAtFixedRate(() -> {
    // Hundreds of lines of business code.
}, Duration.ofSeconds(5));
```

Structure it as:

```java
scheduler.scheduleAtFixedRate(
        jobService::runOneBatch,
        Duration.ofSeconds(5));
```

These fragments assume `jobService` is an injected service. Test `runOneBatch` as an independent business unit using fake repositories/clients; test the scheduler only to confirm triggering, cancellation, and lifecycle. That reduces timing-dependent tests and lets you reuse the job for manual runs or retries.

## 16. Common Mistakes

**Mistake 1 — Assuming fixed rate is always exact to the millisecond.** The JVM scheduler is not real-time; GC, CPU, queues, and long tasks cause lag.

**Mistake 2 — Assuming fixed rate always overlaps.** For a single periodic registration on `ScheduledThreadPoolExecutor`, runs do not overlap; they start late instead.

**Mistake 3 — Assuming fixed rate never overlaps system-wide.** If the Runnable submits async work, or there are multiple registrations or replicas, business work can still overlap.

**Mistake 4 — Confusing `fixedRate` with `fixedDelay`.** Fixed rate measures from planned start marks; fixed delay counts from when the previous run finishes.

**Mistake 5 — Passing `Duration.ZERO` or negative values.** Non-positive periods are invalid; a positive period is required.

**Mistake 6 — Thinking `scheduleAtFixedRate(task, period)` waits a full period before the first run.** This overload starts as soon as possible. For an initial delay, use `Instant startTime` or `@Scheduled(initialDelay=...)`.

**Mistake 7 — Calling `ScheduledFuture.get()` to wait for “the current tick”.** The Future represents the periodic series and may wait until cancel/error; use a separate completion handle per run.

**Mistake 8 — Not keeping the handle when you need to cancel a specific schedule.** Without the handle, changing config dynamically or stopping a specific job is difficult.

**Mistake 9 — Failing to distinguish JDK vs. Spring error defaults.** Raw JDK periodic tasks stop after an uncaught exception; Spring usually logs/suppresses for repeating tasks. Check your `ErrorHandler`.

**Mistake 10 — Merely increasing `poolSize` to fix slow tasks.** A larger pool helps independent schedules, but does not speed up a CPU-bound/blocking task or fix downstream bottlenecks.

**Mistake 11 — Creating a new scheduler per HTTP request.** Spawns many pools and long-lived schedules, making shutdown hard and retaining memory/threads. Prefer a shared Spring bean.

**Mistake 12 — Enabling both `@Scheduled` and manual `TaskScheduler` registration for the same job.** Can cause double scheduling.

**Mistake 13 — Assuming `@Scheduled` runs once across the cluster.** Every replica has its own schedule; distributed coordination/idempotency is needed if single execution is required.

**Mistake 14 — Using a 24-hour fixed rate for “02:00 local time daily”.** A 24-hour `Duration` does not handle DST/calendar transitions like cron.

**Mistake 15 — Logging ticks only without measuring success/failure, duration, and lag.** The scheduler may keep running while the business job fails continuously.

**Mistake 16 — Treating `cancel(true)` as a rollback.** Interrupts do not undo external side effects already performed; cooperative cancellation and reconciliation are required.

**Mistake 17 — Confusing `ThreadPoolTaskScheduler` with `ThreadPoolTaskExecutor`.** A scheduler has its own pool size and delay-queue semantics; `queueCapacity` does not describe it accurately.

**Mistake 18 — Using a periodic tick as the source of truth for missing data.** Ticks can be lost on shutdown/crash; use a job store with `next_run`/`next_attempt` timestamps when recovery is needed.

## 17. Production Checklist

- [ ] Decide whether the task needs **fixed rate**, **fixed delay**, or **cron**; document the business meaning.
- [ ] Set a positive `Duration` and accurate start time; do not confuse “run immediately” with “initial delay”.
- [ ] Configure a shared `TaskScheduler`/`ThreadPoolTaskScheduler` bean; size `poolSize` based on independent jobs and blocking duration.
- [ ] Prevent duplicate registration of the same job (from double start callbacks, multiple configs, or alongside `@Scheduled`).
- [ ] Retain `ScheduledFuture<?>` if dynamic cancel/start/stop is needed; cancel deliberately on shutdown.
- [ ] Distinguish `cancel(false)` from best-effort interrupts in `cancel(true)`; include cleanup and dependency timeouts.
- [ ] Understand the error handler of the **actual implementation**, without assuming an exception always stops or always preserves the schedule.
- [ ] Do not equate tick count with success count; log/emit metrics for business outcomes per run.
- [ ] Monitor **start lag**, duration, pool utilization, and ticks skipped due to busy state.
- [ ] If the Runnable dispatches async work, bound active jobs and queue size; block overlap at the business layer.
- [ ] If the app has multiple replicas, use distributed locks/leases/leadership or idempotency when single processing is needed.
- [ ] For work that must recover after restarts, use a persistent job store / message queue; fixed rate only wakes the consumer.
- [ ] For local wall-clock / day-of-week schedules, use cron/triggers with accurate timezones instead of blindly adding `Duration`.
- [ ] Do not rely on request MDC/transaction/security context in scheduler workers; create and clean up appropriate run IDs/context.
- [ ] Write tests with latches and bounded timeouts; avoid asserting exact timestamps or using `Thread.sleep` to infer ordering.

## 18. Self-Check Questions

**Question 1.** Does `scheduleAtFixedRate(task, Duration.ofSeconds(5))` wait 5 seconds before the first run?

**Answer:** Not by default. This overload registers the task to start as soon as possible; use the `Instant startTime` overload if you want to specify the first run 5 seconds later.

**Question 2.** If a task runs for 8 seconds with a 5-second period, does `ThreadPoolTaskScheduler` create two overlapping executions of the same recurring handle?

**Answer:** With that implementation's `ScheduledThreadPoolExecutor` backend, consecutive runs of **the same periodic task** do not overlap; the next run is delayed and may execute promptly after the previous one finishes.

**Question 3.** What if the task only calls `@Async` and returns in 1 ms—can the business job overlap?

**Answer:** Yes. The scheduler has finished the submission; business work in another executor may still be running when the next tick arrives. Concurrency limits or idempotency are needed if overlap is forbidden.

**Question 4.** How do a 5-second fixed-rate period and a 5-second fixed delay differ when a task takes 3 seconds?

**Answer:** Fixed rate generally starts near marks 0, 5, 10,... seconds; fixed delay starts runs near 0, 8, 16,... seconds because it waits for completion and then adds 5 seconds.

**Question 5.** With JDK `ScheduledThreadPoolExecutor`, what happens if a periodic Runnable throws an uncaught `RuntimeException`?

**Answer:** Subsequent runs in the periodic series are prevented; the periodic future may complete exceptionally. However, Spring's `ThreadPoolTaskScheduler` has a default error handler for repeating tasks that usually suppresses/logs, so check your actual configuration.

**Question 6.** Is `ScheduledFuture.get()` the right API to wait for a single tick to succeed?

**Answer:** No. That Future represents the entire recurring schedule series and does not complete normally after each tick. Use per-run status, metrics, or a separate future.

**Question 7.** To make only one replica run a job every 5 seconds, is setting `poolSize=1` enough?

**Answer:** No. Pool size 1 only limits workers **within one scheduler process**. Multiple replicas still maintain separate schedules. Proper distributed coordination or idempotency is required.

**Question 8.** Is `@EnableScheduling` needed to call `taskScheduler.scheduleAtFixedRate(...)` directly?

**Answer:** No. That annotation is for auto-detecting `@Scheduled`. With the direct API and an existing scheduler bean, your code registers the schedule itself.

**Question 9.** Does calling `handle.cancel(false)` guarantee stopping the currently executing run immediately?

**Answer:** No. It does not request interrupting the current run; cancellation prevents subsequent runs per the Future contract. Stopping early requires cooperative deadline/interrupt handling.

**Question 10.** Does a 24-hour fixed rate always mean 02:00 every day in every timezone?

**Answer:** No. A 24-hour `Duration` differs from local wall-clock schedules across DST/calendar transitions. Use cron/triggers with the appropriate timezone for business schedules.

## Conclusion

**`TaskScheduler.scheduleAtFixedRate()` schedules a `Runnable` to execute at marks spaced by a fixed `Duration`**. When a task runs long, subsequent runs of the same periodic registration in `ThreadPoolTaskScheduler` typically **start late rather than overlap**; if the task offloads work to another executor or multiple replicas hold independent schedules, business operations can still overlap.

- Use `scheduleAtFixedRate(task, period)` to start as soon as possible; use the `Instant startTime` overload to set the first run time.
- Distinguish **fixed rate** (fixed marks), **fixed delay** (pause after completion), and **cron** (calendar-based).
- Retain `ScheduledFuture` for cancellation; do not use `get()` as the result of a single tick.
- Control exception handlers, worker capacity, blocking duration, retries/idempotency, and shutdown.
- For distributed systems or critical jobs, periodic scheduling is only the **trigger mechanism**; a source of truth and processing guarantees belong at the business layer.

## References

1. Spring Framework Reference — Task Execution and Scheduling / TaskScheduler: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
2. Spring Framework 6.2 Javadoc — TaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/TaskScheduler.html
3. Spring Framework Javadoc — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
4. Spring Framework Javadoc — TaskUtils error handling: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/support/TaskUtils.html
5. Java SE 17 — ScheduledExecutorService.scheduleAtFixedRate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
6. Java SE 17 — ScheduledThreadPoolExecutor, no-overlap and remove-on-cancel: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
7. Java SE 17 — ScheduledFuture / cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html
8. Spring Framework Javadoc — @Scheduled: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
