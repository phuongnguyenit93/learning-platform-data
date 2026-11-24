# Distinguishing TaskExecutor from TaskScheduler in Spring Framework

In Spring Framework, **`TaskExecutor` answers the question "by what mechanism will this work be executed?"**, whereas **`TaskScheduler` answers the question "when should this work be triggered?"**. Both deal with tasks (`Runnable`), yet they differ in API contract, triggering model, timing semantics, return objects, and operational concerns.

For example: a user just confirmed an order and a background email needs to be sent → use `TaskExecutor`. The system must check overdue orders at 09:00 every day → use `TaskScheduler`. If every 5 minutes the system must trigger a time-consuming batch job, you can **use the scheduler to decide when to fire, and an executor to run the heavy work**. Separating these two responsibilities makes pool sizing, load limiting, and failure tracking accurate.

## 1. Core Comparison Table

| Criterion | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Purpose | Accept and execute submitted tasks | Schedule a one-off run or time-based execution rule |
| Trigger timing | Caller explicitly calls `execute(task)`; runs when execution resources allow | Based on `Instant`, `Duration` interval, or `Trigger` |
| Primary contract | `void execute(Runnable task)` | `schedule(Runnable, Instant/Trigger)`, `scheduleAtFixedRate(...)`, `scheduleWithFixedDelay(...)` |
| Scope | A single submission does not become periodic on its own | One-off, fixed-rate, fixed-delay, cron/custom trigger |
| API return value | `TaskExecutor.execute` returns no Future; `AsyncTaskExecutor` APIs can return a Future | Scheduling methods normally return `ScheduledFuture<?>`; for a `Trigger` with no next execution, may return `null` |
| Related annotations | `@Async` and `@EnableAsync` | `@Scheduled` and `@EnableScheduling` |
| Common implementations | `ThreadPoolTaskExecutor`, `SimpleAsyncTaskExecutor` | `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler`, `SimpleAsyncTaskScheduler` |
| Problems when misused | Unbounded queue growth, pool saturation, rejected tasks | Late/missed runs, blocked scheduler threads, overlapping periodic jobs |

**Important point:** a scheduler also needs threads to run callbacks, and an executor may queue tasks rather than promising "instant execution." The difference lies in **the contract and meaning of the call**, not two mutually exclusive kinds of threads. A single implementation class can support multiple interfaces.

## 2. TaskExecutor: "Execute This Task"

Spring defines the minimal interface:

~~~java
public interface TaskExecutor extends java.util.concurrent.Executor {
    void execute(Runnable task);
}
~~~

This is a **condensed API signature for explanation**, not source code to rewrite in your application. The caller invokes `execute` once per unit of work. Depending on implementation and configuration, the call may be processed on another thread, via a pool, or under a specific execution strategy. `TaskExecutor` has no API to express "run at 9 a.m." or "repeat every 10 seconds."

### 2.1. `ThreadPoolTaskExecutor`

`ThreadPoolTaskExecutor` integrates with Java's `ThreadPoolExecutor` and allows configuring:

- `corePoolSize`: number of core workers.
- `maxPoolSize`: upper bound on workers when the pool is allowed to grow.
- `queueCapacity`: maximum tasks waiting in the queue.
- Policy when capacity is exhausted, thread naming, and lifecycle.

With a positive-capacity queue, once core size is reached, tasks normally **enter the queue first**, and the pool only adds workers up to max when the queue is full. Therefore, a large `maxPoolSize` does not guarantee tasks run in parallel immediately. With an unbounded queue, max may never be reached. An overloaded executor may throw `TaskRejectedException`; the caller must handle it rather than assuming every submission succeeds.

`SimpleAsyncTaskExecutor` fits some simple cases, yet fundamentally **is not a pool reusing a fixed group of workers**; you must understand concurrency limits and thread/virtual-thread creation costs per Spring version. Do not choose an implementation based solely on the word "async."

### 2.2. `@Async` Is a Way of Submitting Work to an Executor

In a Spring application:

~~~java
@Async("appExecutor")
public CompletableFuture<String> export(String reportId) {
    // Work runs in the executor selected by @Async.
    return CompletableFuture.completedFuture("exported:" + reportId);
}
~~~

This is an **illustrative method inside a Spring-managed bean**, not a standalone program. It requires `@EnableAsync`, an executor bean named `appExecutor`, and invoking the method through the Spring proxy. `@Async` defines no time schedule; each external call to `export("r1")` requests one task execution.

Note: calling `this.export(...)` from the same instance normally **bypasses the proxy in default proxy mode**, so it may not switch to the executor. An `@Async` method returns `void`, `Future`, or `CompletableFuture` (depending on API); with a Future type, the caller can observe results/errors, though waiting with `join()`/`get()` blocks the caller. Exceptions from `void` async methods require an appropriate tracking/error-handling mechanism.

## 3. TaskScheduler: "Trigger Tasks on a Schedule"

`TaskScheduler` provides API groups (condensed signatures as of Spring Framework 6.x):

~~~java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
ScheduledFuture<?> schedule(Runnable task, Trigger trigger);
ScheduledFuture<?> scheduleAtFixedRate(Runnable task, Duration period);
ScheduledFuture<?> scheduleWithFixedDelay(Runnable task, Duration delay);
~~~

These are **illustrative signatures** from Spring's `TaskScheduler` interface, not a standalone Java program. The overloads let you define a start time (`Instant`), an interval (`Duration`), or a strategy computing the next run time (`Trigger`). `CronTrigger` can express hour/day-of-week schedules; `PeriodicTrigger` expresses periods and applies via the `Trigger` interface.

- **One-off at a specific time:** `schedule(task, instant)`. If the timestamp has already passed, execution may be scheduled as soon as possible per implementation; do not treat it as a hard real-time timer.
- **Fixed rate:** schedules target intervals evenly spaced between **start times**; if work runs too long or the scheduler is busy, actual runs may slip late.
- **Fixed delay:** waits for the full delay **after the previous execution finishes** before running again.
- **Cron/custom trigger:** the next run time depends on the time expression or scheduling logic; timezones and daylight-saving transitions can affect behavior.

Scheduling calls return a `ScheduledFuture<?>` handle to inspect or cancel to the extent supported by the implementation. For recurring schedules, Future does not mean "all periodic work has finished"; `cancel(...)` stops future scheduling and may request interrupting an active run, yet **does not guarantee rolling back side effects that already occurred**. For a trigger with no remaining valid fire times, scheduling may return `null`.

### 3.1. Fixed-Rate and Fixed-Delay Are Not the Same

Suppose a single execution takes **8 seconds**, and the configured interval is **5 seconds**, ignoring extra latency:

| Scheduling mode | Meaning | Illustrative timeline |
| --- | --- | --- |
| Fixed rate | Target start times are 5 seconds apart; due runs are delayed if the previous run is still active | Target 0s, 5s, 10s...; if a single job runs sequentially, actual starts might be around 0s, 8s, 16s... |
| Fixed delay | Wait 5 seconds after **each completion** | Start ~0s → finish 8s → start 13s → finish 21s → start 26s |
| Cron | Matches wall-clock schedule per expression, independent of task duration | E.g., 09:00 on weekdays; under overload, understand missed-execution policy |

These timestamps are only for visualization, not real-time guarantees. Traditional `ThreadPoolTaskScheduler` uses `ScheduledThreadPoolExecutor`: runs of **the same registered periodic task** do not overlap each other in that executor; however, **multiple distinct schedule registrations**, multiple application instances, or a callback explicitly dispatching work to another executor can still cause business logic to run concurrently.

### 3.2. `@Scheduled` and Cron

Example method on a Spring-managed bean:

~~~java
@Scheduled(fixedDelay = 10_000, initialDelay = 2_000)
public void pollStatus() {
    // After each pollStatus() finishes, wait another 10 seconds before the next call.
}
~~~

Or a fixed schedule in Vietnam time:

~~~java
@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void prepareDailyReport() {
    // 09:00 Monday through Friday, in the specified timezone.
}
~~~

Both snippets are **illustrative methods** inside Spring beans requiring `@EnableScheduling`; they cannot be compiled standalone with `javac`. Spring cron expressions use **6 fields**: second, minute, hour, day of month, month, day of week. `@Scheduled` is triggered by Spring on a schedule, so such methods normally **take no business parameters from a caller**. Unlike `@Async`, no caller invokes the method on each run.

**Do not mistake `fixedDelay` for the gap between two start times.** The true definition is the gap after **the end of the callback directly managed by the scheduler**. If the callback merely submits a background task and returns, the scheduler considers the callback finished even while the background task is still running; this detail is crucial when combining the two abstractions.

## 4. Relationship Between Interfaces, Implementations, and Annotations

~~~text
A. Business-driven request
HTTP / service method / event
          |
          v
  TaskExecutor.execute(task)
          |
          v
  ThreadPoolTaskExecutor
          |
          v
     Worker executes

B. Time-driven work
Instant / fixed-rate / fixed-delay / CronTrigger
          |
          v
    TaskScheduler
          |
          v
  ThreadPoolTaskScheduler
          |
          v
     Callback triggered

C. Combining for heavy work
TaskScheduler --> short callback --> TaskExecutor --> worker runs job
                         |
                         +--> callback done does NOT mean worker is done
~~~

`@Async` concerns **routing a method invocation to an executor**. `@Scheduled` concerns **registering a schedule to invoke a method**. Both are Spring-managed features, yet they use different beans and policies. `@EnableAsync` does not replace `@EnableScheduling`; enabling scheduling also does not automatically make all methods asynchronous.

### 4.1. Can One Implementation Do Both Jobs?

Yes. For instance, traditional `ThreadPoolTaskScheduler` also supports several task-execution contracts in addition to `TaskScheduler`. Therefore, you should not define the difference as "the two interfaces can never coexist on the same object."

However, using a **separate** `ThreadPoolTaskExecutor` for blocking/CPU-bound workloads and `ThreadPoolTaskScheduler` for time coordination can be easier to reason about and control. Long-running tasks executing directly on the scheduler tie up scheduler workers and delay other schedules. Separating them is a sound architectural choice, not a mandatory Spring constraint.

## 5. Java 17: Standalone Example to Understand "execute" and "schedule"

Before wiring Spring, we can see the equivalent idea in standard Java: `ExecutorService` accepts work, while `ScheduledExecutorService` schedules work. This example **does not use Spring**, allowing you to verify the difference using JDK 17 alone.

Create `ExecutorVsSchedulerDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ExecutorVsSchedulerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
        try {
            CountDownLatch firstDone = new CountDownLatch(1);
            executor.execute(() -> {
                System.out.println("executor: task completed");
                firstDone.countDown();
            });
            if (!firstDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor task timed out");
            }

            ScheduledFuture<?> later = scheduler.schedule(
                    () -> System.out.println("scheduler: task completed"),
                    100, TimeUnit.MILLISECONDS);
            later.get(5, TimeUnit.SECONDS);
            System.out.println("main: finished");
        } finally {
            executor.shutdownNow();
            scheduler.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ExecutorVsSchedulerDemo.java
java ExecutorVsSchedulerDemo
~~~

Verified output on OpenJDK (ordering guaranteed by `CountDownLatch` and `Future.get()`):

~~~text
executor: task completed
scheduler: task completed
main: finished
~~~

`executor.execute(...)` submits a job to run, whereas `scheduler.schedule(..., 100, MILLISECONDS)` schedules the second job to run **after at least the requested delay** (actual timing depends on OS scheduling). `CountDownLatch` ensures the first job completes before scheduling the second; `later.get(...)` awaits completion of the scheduled job. The program releases resources in `finally`. In Spring, implementations may wrap or manage these Java executors, while Spring's API provides an abstraction so business logic is not coupled directly to thread creation.

## 6. Spring Framework Example: Configuring Both Executor and Scheduler

The snippets below target a **Java 17+, Spring Framework 6.x** project with `spring-context` on the classpath and component scanning; they also work in Spring Boot 3.x. They are **multi-file integration code**, so a single file cannot be compiled with `javac` without Spring dependencies.

### 6.1. Configuring Two Beans With Clear Responsibilities

File `ConcurrencyConfig.java`, in example package `example.concurrency`:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableAsync
@EnableScheduling
public class ConcurrencyConfig {
    @Bean("appExecutor")
    public ThreadPoolTaskExecutor appExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("work-");
        return executor;
    }

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        return scheduler;
    }
}
~~~

- The `appExecutor` bean serves `@Async("appExecutor")`; `4/8/32` are illustrative only and must be tuned for load, processing time, memory, and downstream service limits.
- The `taskScheduler` bean is the sole scheduler and carries the conventional name that Spring's `@Scheduled` mechanism discovers. `setPoolSize(2)` bounds concurrency of callbacks running directly in the scheduler pool, not the number of business executions those callbacks might submit to the executor.
- `@EnableAsync` enables async annotation processing; `@EnableScheduling` enables scheduled annotation processing. Explicit naming and bean selection avoid relying on defaults that can shift depending on Spring Boot configuration.
- To let Spring manage lifecycle automatically, register them as beans in the application context. Do not manually create numerous raw schedulers/executors and forget to shut them down when the application stops.

### 6.2. Task Requested Asynchronously

File `ReportWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Illustrates business logic; replace with real work and proper timeouts.
        return CompletableFuture.completedFuture("generated:" + reportId);
    }
}
~~~

When another controller/service calls `reportWorker.generate("R-7")` through the Spring bean, the task is submitted to `appExecutor`. The caller can continue and receive a `CompletableFuture<String>`. There is no periodic schedule on this method; **one call corresponds to one work request**. Even though the example method's return value uses `completedFuture`, the `@Async` invocation itself is routed to the executor by the Spring proxy when wired properly.

### 6.3. Scheduler Decides When to Trigger Work

File `ReportSchedule.java`:

~~~java
package example.concurrency;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedule {
    private final ReportWorker reportWorker;

    public ReportSchedule(ReportWorker reportWorker) {
        this.reportWorker = reportWorker;
    }

    @Scheduled(fixedDelay = 10_000, initialDelay = 2_000)
    public void requestReport() {
        reportWorker.generate("periodic")
                .whenComplete((result, error) -> {
                    if (error != null) {
                        System.err.println("Report failed: " + error.getMessage());
                    } else {
                        System.out.println(result);
                    }
                });
    }
}
~~~

A typical run:

1. `taskScheduler` invokes `requestReport()` after the initial delay.
2. The callback calls **another bean**, `ReportWorker`, so the `@Async` call passes through the Spring proxy.
3. `appExecutor` accepts the task and a worker executes `generate(...)`.
4. `requestReport()` returns after dispatching the task and attaching the completion callback, without waiting for the report to finish.
5. `fixedDelay=10_000` is measured from **when `requestReport()` finishes**; it **does not guarantee** two `generate(...)` executions are 10 seconds apart or non-overlapping.

This example fully demonstrates how the two abstractions collaborate. In production, if **two reports must not process concurrently**, enforce one-job-at-a-time using an `in-flight` state, submission limits, or proper locking rather than relying on `fixedDelay` on the dispatching callback. Likewise, `appExecutor`'s queue can fill up and submissions can be rejected; error observation and explicit handling policies are needed.

### 6.4. Using TaskScheduler Directly When Schedules Come From Business Data

`@Scheduled` is convenient for relatively static annotation-based schedules. When execution times come from runtime data (such as "send a notification at the timestamp chosen by the customer"), use the `TaskScheduler` API:

~~~java
package example.concurrency;

import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Component;

@Component
public class DeferredTaskService {
    private final TaskScheduler scheduler;
    private final TaskExecutor executor;

    public DeferredTaskService(
            @Qualifier("taskScheduler") TaskScheduler scheduler,
            @Qualifier("appExecutor") TaskExecutor executor) {
        this.scheduler = scheduler;
        this.executor = executor;
    }

    public ScheduledFuture<?> scheduleDispatch(Instant when, Runnable job) {
        return scheduler.schedule(() -> executor.execute(job), when);
    }
}
~~~

This is also **Spring integration code**, not a standalone `javac` example. `scheduleDispatch(when, job)` returns the handle of **the dispatch callback**; once the callback submits successfully, `ScheduledFuture<?>` may already be done while `job` is still running inside `appExecutor`. Do not use that handle as proof that business processing succeeded. To track real progress/outcomes, design an additional `Future`, job ID, persisted status, or completion callback on the executor side. Cancelling the schedule only affects unstarted/scheduled state appropriately and does not automatically cancel background tasks already submitted.

In-memory schedules on a scheduler are also not **durable schedules**: an application restart can lose unrecovered one-off registrations. When a schedule is a business commitment, persist schedule records durably and re-drive/reconcile them by design.

## 7. Picking the Right Abstraction for Real Scenarios

| Scenario | What to use? | Why? |
| --- | --- | --- |
| An API receives a file-export request and returns an early response | `TaskExecutor` or `@Async` | Work arises on request; no time trigger is needed |
| Perform an action 30 minutes later | `TaskScheduler.schedule(..., Instant)` | There is a future execution timestamp |
| Poll status every 10 seconds | `@Scheduled(fixedDelay=...)` / `TaskScheduler` | Want automatic repeated triggering |
| Aggregate reports at 09:00 every weekday | Cron on `TaskScheduler` / `@Scheduled(cron=...)` | Wall-clock time and timezone schedule |
| Scheduler detects new data and needs to process many heavy tasks | `TaskScheduler` + `TaskExecutor` | One layer drives cadence; the other manages task concurrency |
| Controller calls multiple independent I/O steps concurrently | `TaskExecutor` or appropriate async mechanism | On-demand parallel orchestration, not a periodic schedule |
| Multiple instances need **exactly one** run cluster-wide | Scheduler **paired with distributed coordination** | `@Scheduled` registers per application context by default and does not provide cluster-wide exactly-once |

Do not turn every background task into `@Scheduled` merely because it runs in the background. Without a **time-triggering requirement**, an executor suffices. Conversely, if something must repeat on a schedule, a plain executor does not manage cron or delays on its own.

## 8. Limitations, Common Bugs, and How to Diagnose Them

### 8.1. "I Used @Async, Yet It Still Runs on the Caller Thread"

Check `@EnableAsync`, whether the bean is Spring-managed, the executor name, and whether calls pass through the proxy. Self-invocation such as `this.generate()` inside the same bean can bypass interception. Adding `@Scheduled` does not make `@Async` work. Logging thread names and inspecting the stack confirm wiring, though you should not depend on thread names as an API contract.

### 8.2. "I Used @Scheduled, Yet the Schedule Never Runs"

Check `@EnableScheduling`, whether the bean is actually registered, whether cron has **6 fields** and the intended timezone, whether the application is running, and whether the scheduler is blocked or stopped. Tasks throwing exceptions must be captured via error handling/metrics. Do not assume millisecond precision or identical catch-up behavior for missed runs across all `Trigger` types.

### 8.3. "Will Increasing the Scheduler Pool Make Async Tasks Faster?"

Not necessarily. `taskScheduler.setPoolSize(...)` increases workers available for scheduler callbacks; `appExecutor.setCorePoolSize(...)`/`setMaxPoolSize(...)` affects the executor running business tasks. If callbacks just quickly submit to the executor, the bottleneck may sit in `appExecutor`, the DB pool, or external services. Measure queues and latencies at every tier; growing one pool does not substitute for diagnosing downstream bottlenecks.

### 8.4. "Fixed-Delay Is Configured, Yet Jobs Still Overlap"

If the scheduled method **synchronously runs the entire job**, fixed-delay starts counting when that job ends. If the scheduled method **merely calls `@Async`** and returns early, fixed-delay only spans the *dispatch* turn. One job may still be running when the next dispatch arrives. Solutions include bounded waiting where appropriate, `in-flight` guards before submitting, or queuing/idempotency/distributed locks as required. Never block the scheduler indefinitely just to "guarantee no overlap."

### 8.5. "Can TaskScheduler and TaskExecutor Deadlock or Exhaust Threads?"

Yes. If every scheduler thread blocks on `Future.get()` for tasks that the executor lacks resources to run, schedules stall; if workers in the executor wait on the scheduler to free resources, a dependency cycle can arise. Never block executor workers waiting on subtasks submitted to the same pool; avoid holding locks across long blocking I/O; enforce timeouts and queue/connection limits.

### 8.6. "Is It Normal for a Scheduled Job to Run on Multiple Pods?"

It can be completely normal: every Spring instance with `@EnableScheduling` and `@Scheduled` beans registers its own schedules. `TaskScheduler` does not perform leader election on its own. When a cluster-wide single execution is required, design distributed locks, leader election, a job store, or a dedicated orchestrator alongside idempotency protection. Clarify the difference between "running on time per instance" and "processing once system-wide."

### 8.7. What Should You Measure?

- **On the scheduler:** triggered callback count, scheduled vs. actual fire time, trigger lag, callback duration, failed runs, skipped/missed triggers.
- **On the executor:** active threads, pool size, queue depth/wait time, completed tasks, rejections, duration, and exceptions.
- **On business jobs:** in-flight job count, end-to-end duration, success/failure counts, side-effect outcomes, retry counts.
- **On downstream systems:** connection pool usage, timeouts, CPU quota, DB/HTTP latency; adding workers creates zero extra capacity for a constrained downstream service.

With async APIs, failure callbacks must record exceptions. With important one-off schedules, plan for restarts and cancellation. With recurring tasks, define policies for lateness, overlap prevention, retry/backoff, and shutdown explicitly.

## 9. Self-Check Questions

**1. Does TaskExecutor always create a new thread?** No. `TaskExecutor` is a task-submission contract. `ThreadPoolTaskExecutor` normally reuses workers, while other implementations may use their own strategies.

**2. What should you use to run a job at 09:00 Monday–Friday?** `TaskScheduler` with cron / `@Scheduled(cron=...)` and an explicit timezone. An executor can additionally be used if the callback needs to offload heavy work.

**3. Does `@Async` make a method repeat automatically every 10 seconds?** No. It governs submitting each method invocation to an executor, not computing future trigger times.

**4. Does `fixedDelay=10_000` on a callback that only submits an `@Async` task guarantee a 10-second gap after the task *finishes*?** No. The delay starts after the scheduled callback returns; the real worker may still be running.

**5. What does the `ScheduledFuture<?>` returned by `scheduler.schedule(() -> executor.execute(job), when)` represent?** The scheduling and completion of the **job-submission callback**; it does not guarantee `job` finished successfully inside the executor.

**6. If the scheduler has 2 threads and the executor has 8 workers, is the system limited to only 2 concurrent business jobs total?** No. If the scheduler only dispatches briefly, business jobs can run inside the executor up to the limits of the executor and downstream resources. Distinguish running callbacks from submitted jobs.

**7. If multiple replicas all have the same `@Scheduled`, does Spring automatically ensure only one runs cluster-wide?** No. You must add distributed coordination and duplicate-execution protection when business rules require it.

## 10. References

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework API — TaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework API — TaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework API — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework API — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Java SE 17 API — ScheduledExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
